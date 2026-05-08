"""
etsy_api.py
Etsy Open API v3 ile listing oluşturma ve fotoğraf yükleme.

Gereksinimler:
  pip install requests

Kurulum (bir kez):
  1. vds/oauth_baslat.py çalıştır → tarayıcıda Etsy'yi authorize et
  2. token.json oluşur → orkestratör otomatik kullanır

Durum: API onayı bekleniyor (Pending Personal Approval)
  Onay gelince ETSY_API_KEY ve ETSY_SHARED_SECRET .env'e ekle,
  ardından bu modül aktif olur.
"""

import os
import json
import time
import requests
from pathlib import Path

# ── Ayarlar ──────────────────────────────────────────────────────────────────
ETSY_API_KEY     = os.environ.get("ETSY_API_KEY", "")
ETSY_SHARED_SECRET = os.environ.get("ETSY_SHARED_SECRET", "")
ETSY_SHOP_ID     = os.environ.get("ETSY_SHOP_ID", "")
TOKEN_DOSYASI    = Path(__file__).parent.parent / "token.json"

BASE_URL = "https://openapi.etsy.com/v3"

# Etsy API rate limit: 5 QPS — istekler arası minimum bekleme
_ISTEK_ARASI = 0.25  # saniye


# ── Token Yönetimi ────────────────────────────────────────────────────────────

def token_yukle() -> dict:
    """token.json'dan access/refresh token okur."""
    if not TOKEN_DOSYASI.exists():
        raise FileNotFoundError(
            "token.json bulunamadı. Önce 'python oauth_baslat.py' çalıştırın."
        )
    return json.loads(TOKEN_DOSYASI.read_text())


def token_kaydet(token_data: dict):
    TOKEN_DOSYASI.write_text(json.dumps(token_data, indent=2))


def token_yenile() -> str:
    """Access token süresi dolduysa refresh token ile yeniler. Güncel token döner."""
    token_data = token_yukle()
    access_token = token_data.get("access_token", "")
    expires_at   = token_data.get("expires_at", 0)

    if time.time() < expires_at - 60:
        return access_token

    print("[Etsy API] Token yenileniyor...")
    r = requests.post(
        "https://api.etsy.com/v3/public/oauth/token",
        data={
            "grant_type":    "refresh_token",
            "client_id":     ETSY_API_KEY,
            "refresh_token": token_data["refresh_token"],
        },
        timeout=15,
    )
    r.raise_for_status()
    yeni = r.json()
    yeni["expires_at"] = time.time() + yeni.get("expires_in", 3600)
    token_kaydet(yeni)
    print("[Etsy API] ✓ Token yenilendi.")
    return yeni["access_token"]


def _headers() -> dict:
    return {
        "x-api-key":     ETSY_API_KEY,
        "Authorization": f"Bearer {token_yenile()}",
        "Content-Type":  "application/json",
    }


# ── Listing İşlemleri ─────────────────────────────────────────────────────────

def etsy_draft_olustur(urun: dict) -> dict:
    """
    Etsy'de draft listing oluşturur.

    Args:
        urun: Sheets'ten gelen dict — baslik, aciklama, taglar, fiyat_usd, vb.

    Returns:
        {"basarili": bool, "listing_id": int, "hata": str|None}
    """
    if not ETSY_API_KEY or not ETSY_SHOP_ID:
        return {"basarili": False, "listing_id": None,
                "hata": "ETSY_API_KEY veya ETSY_SHOP_ID eksik"}

    taglar = [urun.get(f"tag{i}", "") for i in range(1, 14) if urun.get(f"tag{i}", "")][:13]

    payload = {
        "quantity":          1,
        "title":             urun.get("baslik", "")[:140],
        "description":       urun.get("aciklama", ""),
        "price":             float(urun.get("fiyat_usd", 0)),
        "who_made":          "someone_else",
        "when_made":         "before_2000",
        "taxonomy_id":       170,        # Rugs & Carpets
        "state":             "draft",
        "shipping_profile_id": int(os.environ.get("ETSY_SHIPPING_PROFILE_ID", 0)),
        "tags":              taglar,
        "materials":         [],
        "processing_min":    1,
        "processing_max":    3,
    }

    try:
        time.sleep(_ISTEK_ARASI)
        r = requests.post(
            f"{BASE_URL}/application/shops/{ETSY_SHOP_ID}/listings",
            headers=_headers(),
            json=payload,
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
        listing_id = data["listing_id"]
        print(f"[Etsy API] ✓ Draft oluşturuldu: listing_id={listing_id}")
        return {"basarili": True, "listing_id": listing_id, "hata": None}

    except requests.HTTPError as e:
        hata = f"HTTP {e.response.status_code}: {e.response.text[:200]}"
        print(f"[Etsy API] ✗ {hata}")
        return {"basarili": False, "listing_id": None, "hata": hata}

    except Exception as e:
        print(f"[Etsy API] ✗ {e}")
        return {"basarili": False, "listing_id": None, "hata": str(e)}


def etsy_fotograf_yukle(listing_id: int, dosya_yolu: str, sira: int = 1) -> bool:
    """
    Listing'e tek fotoğraf yükler.

    Args:
        listing_id: etsy_draft_olustur'dan dönen ID
        dosya_yolu: yerel dosya yolu (C:\\etsy_temp\\4102\\foto.jpg)
        sira:       1-10 arası sıra numarası

    Returns:
        True = başarılı
    """
    try:
        time.sleep(_ISTEK_ARASI)
        headers = {
            "x-api-key":     ETSY_API_KEY,
            "Authorization": f"Bearer {token_yenile()}",
            # Content-Type multipart olduğu için header'a eklenmez
        }
        with open(dosya_yolu, "rb") as f:
            r = requests.post(
                f"{BASE_URL}/application/shops/{ETSY_SHOP_ID}/listings/{listing_id}/images",
                headers=headers,
                files={"image": (Path(dosya_yolu).name, f, "image/jpeg")},
                data={"rank": sira, "overwrite": "true"},
                timeout=60,
            )
        r.raise_for_status()
        print(f"[Etsy API] ✓ Fotoğraf yüklendi: {Path(dosya_yolu).name} (sıra {sira})")
        return True

    except Exception as e:
        print(f"[Etsy API] ✗ Fotoğraf yüklenemedi ({Path(dosya_yolu).name}): {e}")
        return False


def etsy_urun_yukle(urun: dict, fotograflar: list[str]) -> dict:
    """
    Tek ürün için tam yükleme: draft oluştur + tüm fotoğrafları yükle.

    Args:
        urun:       Sheets'ten gelen dict
        fotograflar: yerel dosya yolları listesi (max 10)

    Returns:
        {"basarili": bool, "listing_id": int, "etsy_url": str, "hata": str|None}
    """
    # 1. Draft oluştur
    draft = etsy_draft_olustur(urun)
    if not draft["basarili"]:
        return {"basarili": False, "listing_id": None, "etsy_url": "", "hata": draft["hata"]}

    listing_id = draft["listing_id"]

    # 2. Fotoğrafları yükle (max 10)
    foto_listesi = sorted(fotograflar)[:10]
    basarisiz = 0
    for sira, yol in enumerate(foto_listesi, start=1):
        if not etsy_fotograf_yukle(listing_id, yol, sira):
            basarisiz += 1

    etsy_url = f"https://www.etsy.com/your/shops/me/tools/listings/{listing_id}"
    print(f"[Etsy API] ✓ Yükleme tamamlandı: {len(foto_listesi)-basarisiz}/{len(foto_listesi)} fotoğraf")

    return {
        "basarili":   True,
        "listing_id": listing_id,
        "etsy_url":   etsy_url,
        "hata":       None,
    }
