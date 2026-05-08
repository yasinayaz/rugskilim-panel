"""
oauth_baslat.py
Etsy OAuth 2.0 — bir kez çalıştırılır, token.json oluşturur.

Adımlar:
  1. Bu scripti çalıştır: python oauth_baslat.py
  2. Tarayıcıda Etsy'ye giriş yap, "Allow Access" tıkla
  3. Tarayıcı localhost'a yönlendirir → kod otomatik alınır
  4. token.json oluşur → orkestratör kullanır

Gereksinim:
  pip install requests

Ortam değişkenleri (.env):
  ETSY_API_KEY=8pbwtinee6blq6qz8hseonjt
  ETSY_SHARED_SECRET=...
  ETSY_SHOP_ID=...
  ETSY_SHIPPING_PROFILE_ID=...
"""

import os
import sys
import json
import time
import secrets
import hashlib
import base64
import webbrowser
import requests
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlencode, urlparse, parse_qs

# ── Ayarlar ──────────────────────────────────────────────────────────────────
ETSY_API_KEY      = os.environ.get("ETSY_API_KEY", "")
ETSY_SHARED_SECRET = os.environ.get("ETSY_SHARED_SECRET", "")
REDIRECT_URI      = "http://localhost:8080/callback"
TOKEN_DOSYASI     = Path(__file__).parent / "token.json"

SCOPES = [
    "listings_w",   # listing oluştur/düzenle
    "listings_r",   # listing oku
]

# ── PKCE ─────────────────────────────────────────────────────────────────────

def _pkce_olustur():
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b"=").decode()
    return verifier, challenge


# ── Callback Sunucu ───────────────────────────────────────────────────────────

_alinan_kod = None

class _CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global _alinan_kod
        params = parse_qs(urlparse(self.path).query)
        _alinan_kod = params.get("code", [None])[0]
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"<h2>Etsy yetkilendirmesi tamamlandi. Bu sekmeyi kapatabilirsiniz.</h2>")

    def log_message(self, *args):
        pass  # konsolu kirletme


# ── Ana Akış ─────────────────────────────────────────────────────────────────

def oauth_baslat():
    if not ETSY_API_KEY or not ETSY_SHARED_SECRET:
        print("HATA: ETSY_API_KEY ve ETSY_SHARED_SECRET ortam değişkenlerini set edin.")
        print("  Windows: set ETSY_API_KEY=...")
        print("  Windows: set ETSY_SHARED_SECRET=...")
        sys.exit(1)

    verifier, challenge = _pkce_olustur()
    state = secrets.token_urlsafe(16)

    auth_url = "https://www.etsy.com/oauth/connect?" + urlencode({
        "response_type":         "code",
        "redirect_uri":          REDIRECT_URI,
        "scope":                 " ".join(SCOPES),
        "client_id":             ETSY_API_KEY,
        "state":                 state,
        "code_challenge":        challenge,
        "code_challenge_method": "S256",
    })

    print("\n" + "="*55)
    print("  ETSY OAuth BAŞLADI")
    print("="*55)
    print(f"\nTarayıcı açılıyor...")
    webbrowser.open(auth_url)
    print("Etsy'de 'Allow Access' tıkla, tarayıcı localhost'a dönecek.\n")

    # Callback sunucu — kodu yakala
    sunucu = HTTPServer(("localhost", 8080), _CallbackHandler)
    sunucu.timeout = 120
    sunucu.handle_request()

    global _alinan_kod
    if not _alinan_kod:
        print("HATA: Kod alınamadı. Süre dolmuş olabilir, tekrar dene.")
        sys.exit(1)

    print(f"✓ Kod alındı, token isteniyor...")

    # Token al
    r = requests.post(
        "https://api.etsy.com/v3/public/oauth/token",
        data={
            "grant_type":          "authorization_code",
            "client_id":           ETSY_API_KEY,
            "redirect_uri":        REDIRECT_URI,
            "code":                _alinan_kod,
            "code_verifier":       verifier,
        },
        timeout=15,
    )

    if r.status_code != 200:
        print(f"HATA: Token alınamadı — {r.status_code}: {r.text}")
        sys.exit(1)

    token_data = r.json()
    token_data["expires_at"] = time.time() + token_data.get("expires_in", 3600)

    TOKEN_DOSYASI.write_text(json.dumps(token_data, indent=2))

    print(f"\n✅ token.json oluşturuldu: {TOKEN_DOSYASI}")
    print("Orkestratör artık bu token'ı otomatik kullanacak.")


if __name__ == "__main__":
    oauth_baslat()
