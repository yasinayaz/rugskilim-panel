"""
sheets.py
Google Sheets ile iş kuyruğu yönetimi.

Sheet yapısı (1. satır başlık):
A  urun_id
B  pcloud_klasor_yolu
C  boyut_cm
D  boyut_ft
E  metrekare
F  fotograf_sayisi
G  baslik
H  aciklama
I  taglar_virgul     (tüm tagler virgülle — manuel yükleme için)
J  renk1
K  renk2
L  pattern_etsy      (Etsy pattern: Geometric, Floral, Oriental, vb.)
M  fiyat_usd
N  urun_id           (kopya — görsel referans)
O  shop_section
P  status            (pending → ready → downloading → downloaded → uploading → done / error)
Q  tip               (Etsy type: Accent / Area / Runner)
R  etsy_draft_url
S  hata_mesaji
T  islem_tarihi
U  pcloud_klasor_id  (sayısal folder ID — VDS navigasyon için)
V  ana_resim_tag     (uzun kuyruklu SEO tag — ana resim dosya adı için)
W  tag1 ... AI tag13
"""

import os
import json
import time
import random
from datetime import datetime
from pathlib import Path
from threading import Lock
import requests
import gspread
from gspread.exceptions import APIError, WorksheetNotFound
from google.auth.transport.requests import Request
from google.oauth2.service_account import Credentials
from gspread.utils import rowcol_to_a1

# Sabitler
SHEET_ID         = os.environ.get("GOOGLE_SHEET_ID", "")
CREDENTIALS_JSON = os.environ.get("GOOGLE_CREDS_JSON", "credentials.json")

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

RENK_TANIMLARI = {
    "green": {"green": 1},
    "yellow": {"red": 0.98, "green": 0.93, "blue": 0.67},
    "red": {"red": 0.96, "green": 0.80, "blue": 0.80},
    "none": None,
}

QUEUE_SHEET_MIN_ROWS = 5000
QUEUE_SHEET_MIN_COLS = 37

# Kolon indeksleri (1-tabanlı, gspread için)
KOL = {
    "urun_id":          1,
    "pcloud_klasor":    2,
    "boyut_cm":         3,
    "boyut_ft":         4,
    "metrekare":        5,
    "fotograf_sayisi":  6,
    "baslik":           7,
    "aciklama":         8,
    "taglar_virgul":    9,
    "renk1":            10,
    "renk2":            11,
    "pattern_etsy":     12,
    "fiyat_usd":        13,
    "urun_id_kopya":    14,
    "shop_section":     15,
    "status":           16,
    "tip":              17,
    "etsy_draft_url":   18,
    "hata_mesaji":      19,
    "islem_tarihi":     20,
    "pcloud_klasor_id": 21,
    "ana_resim_tag":    22,
    # tag1-tag13: kolonlar 23-35
    "tag_baslangic":    23,
}

BASLIK_SATIRI = [
    "urun_id", "pcloud_klasor_yolu", "boyut_cm", "boyut_ft", "metrekare",
    "fotograf_sayisi", "baslik", "aciklama", "taglar_virgul",
    "renk1", "renk2", "pattern_etsy", "fiyat_usd", "urun_id",
    "shop_section", "status", "tip", "etsy_draft_url", "hata_mesaji", "islem_tarihi",
    "pcloud_klasor_id", "ana_resim_tag",
    "tag1", "tag2", "tag3", "tag4", "tag5", "tag6", "tag7",
    "tag8", "tag9", "tag10", "tag11", "tag12", "tag13",
]

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
RETRY_SLEEP_BASE = 2.0
RETRY_SLEEP_MAX = 30.0
RETRY_MAX_ATTEMPTS = 6

_CLIENT_CACHE = {}
_SPREADSHEET_CACHE = {}
_CACHE_LOCK = Lock()


def _client():
    creds_path = _credentials_json_yolu()
    with _CACHE_LOCK:
        client = _CLIENT_CACHE.get(creds_path)
        if client is not None:
            return client

        creds = Credentials.from_service_account_file(
            creds_path,
            scopes=SCOPES,
        )
        client = gspread.authorize(creds)
        _CLIENT_CACHE[creds_path] = client
        return client


def _spreadsheet(sheet_id: str):
    if not sheet_id:
        raise ValueError("Google Sheet ID boş olamaz.")

    creds_path = _credentials_json_yolu()
    cache_key = (creds_path, sheet_id)
    with _CACHE_LOCK:
        spreadsheet = _SPREADSHEET_CACHE.get(cache_key)
        if spreadsheet is not None:
            return spreadsheet

    spreadsheet = _yeniden_dene("Spreadsheet açma", _client().open_by_key, sheet_id)

    with _CACHE_LOCK:
        _SPREADSHEET_CACHE[cache_key] = spreadsheet

    return spreadsheet


def drive_file_degisim_imzasi(file_id: str) -> str:
    """
    Google Drive dosyasinin hafif degisim imzasini doner.
    Sheet icerigini okumadan once bu imza degismediyse agir sync atlanabilir.
    """
    temiz_id = str(file_id or "").strip()
    if not temiz_id:
        return ""

    creds = Credentials.from_service_account_file(
        _credentials_json_yolu(),
        scopes=SCOPES,
    )
    creds.refresh(Request())
    response = requests.get(
        f"https://www.googleapis.com/drive/v3/files/{temiz_id}",
        headers={"Authorization": f"Bearer {creds.token}"},
        params={"fields": "id,modifiedTime,version"},
        timeout=20,
    )
    if not response.ok:
        raise RuntimeError(f"Drive metadata okunamadi: {response.status_code} {response.text}")
    data = response.json() or {}
    return f"{data.get('id','')}|{data.get('modifiedTime','')}|{data.get('version','')}"


def _api_hata_kodu(exc: Exception) -> int | None:
    resp = getattr(exc, "response", None)
    if resp is not None:
        status = getattr(resp, "status_code", None)
        if status:
            return int(status)
    return None


def _yeniden_dene(op_name: str, func, *args, **kwargs):
    """Geçici Sheets/Drive API hatalarında exponential backoff uygular."""
    son_exc = None
    for deneme in range(1, RETRY_MAX_ATTEMPTS + 1):
        try:
            return func(*args, **kwargs)
        except APIError as exc:
            son_exc = exc
            kod = _api_hata_kodu(exc)
            mesaj = str(exc)
            tekrar_dene = (
                kod in RETRYABLE_STATUS_CODES or
                "Quota exceeded" in mesaj or
                "rate limit" in mesaj.lower()
            )
            if not tekrar_dene or deneme >= RETRY_MAX_ATTEMPTS:
                raise
            bekleme = min(RETRY_SLEEP_MAX, RETRY_SLEEP_BASE * (2 ** (deneme - 1)))
            bekleme += random.uniform(0, 0.75)
            print(
                f"[Sheets] {op_name} geçici hataya takıldı "
                f"(deneme {deneme}/{RETRY_MAX_ATTEMPTS}, kod={kod or '?'}) → "
                f"{bekleme:.1f} sn bekleniyor..."
            )
            time.sleep(bekleme)
    raise son_exc


def _credentials_json_yolu() -> str:
    """
    Credentials yolunu bulur.
    Öncelik:
      1. GOOGLE_CREDS_JSON env
      2. legacy mac/ yolu varsa yeni streamlit/ yoluna çevir
      3. repo içindeki bilinen credential dosyaları
      4. mevcut varsayılan credentials.json
    """
    adaylar = []
    denenmis = []
    env_yol = os.environ.get("GOOGLE_CREDS_JSON", CREDENTIALS_JSON)
    if env_yol:
        env_path = Path(env_yol).expanduser()
        adaylar.append(env_path)
        if not env_path.is_absolute():
            repo_kok = Path(__file__).resolve().parent.parent
            adaylar.append((repo_kok / env_path).resolve())

        # Klasor adi mac -> streamlit tasinmis olabilir.
        legacy = str(env_yol)
        if "/mac/" in legacy:
            adaylar.append(Path(legacy.replace("/mac/", "/streamlit/")).expanduser())

    repo_kok = Path(__file__).resolve().parent.parent
    adaylar.extend([
        repo_kok / "streamlit" / "entegra-hali-8ead6e6f99fe.json",
        repo_kok / "vds" / "entegra-hali-8ead6e6f99fe.json",
        repo_kok / "credentials.json",
    ])

    for aday in adaylar:
        denenmis.append(str(aday))
        if aday and aday.exists():
            os.environ["GOOGLE_CREDS_JSON"] = str(aday)
            return str(aday)

    raise FileNotFoundError(
        "Google credentials JSON bulunamadi. "
        f"GOOGLE_CREDS_JSON icin denenmis yollar: {', '.join(denenmis)}"
    )


def _tum_satirlar_al(ws) -> list:
    """Boş/yinelenen başlıklara karşı güvenli kayıt okuma."""
    degerler = _yeniden_dene("Tüm satırları okuma", ws.get_all_values)
    if len(degerler) < 2:
        return []
    basliklar = degerler[0]
    goruldu = {}
    temiz = []
    for b in basliklar:
        if not b or b in goruldu:
            b = (b or "_") + f"_{goruldu.get(b, 0) + 1}"
        goruldu[b] = goruldu.get(b, 0) + 1
        temiz.append(b)
    return [dict(zip(temiz, satir)) for satir in degerler[1:] if any(satir)]


def _satirda_veri_var_mi(satir) -> bool:
    return any(str(hucre or "").strip() for hucre in (satir or []))


def _son_dolu_satir_no(ws) -> int:
    """
    Başlık satırı dahil worksheet'teki son gerçekten dolu satırı döndürür.
    Sadece biçimlendirilmiş ya da formülden boş string dönen satırlar dolu sayılmaz.
    """
    tum = _yeniden_dene("Son dolu satır için tüm satırları okuma", ws.get_all_values)
    for idx in range(len(tum) - 1, -1, -1):
        if _satirda_veri_var_mi(tum[idx]):
            return idx + 1
    return 1


def _siradaki_yazilabilir_satir_no(ws) -> int:
    return max(_son_dolu_satir_no(ws) + 1, 2)


def _basliklar_al(ws) -> list:
    return _yeniden_dene("Başlık satırını okuma", ws.row_values, 1)


def _baslik_pozisyonlari(ws) -> dict:
    pozisyonlar = {}
    for idx, baslik in enumerate(_basliklar_al(ws), start=1):
        anahtar = str(baslik or "").strip()
        if not anahtar:
            continue
        pozisyonlar.setdefault(anahtar, []).append(idx)
    return pozisyonlar


def _kolon_no(ws, baslik: str, occurrence: int = 0, default=None):
    pozisyonlar = _baslik_pozisyonlari(ws).get(baslik, [])
    if occurrence < len(pozisyonlar):
        return pozisyonlar[occurrence]
    return default


def _kolon_no_from_positions(pozisyonlar: dict, baslik: str, occurrence: int = 0, default=None):
    eslesmeler = pozisyonlar.get(baslik, [])
    if occurrence < len(eslesmeler):
        return eslesmeler[occurrence]
    return default


def _template_json_yukle(template_id: str) -> dict:
    template_id = str(template_id or "").strip() or "default_v1"
    try:
        raw = str((config_oku() or {}).get(f"TEMPLATE_JSON__{template_id}", "") or "").strip()
        if raw:
            return json.loads(raw)
    except Exception:
        pass

    repo_kok = Path(__file__).resolve().parent.parent
    aday = repo_kok / "streamlit" / "templates" / f"{template_id}.json"
    if aday.exists():
        try:
            return json.loads(aday.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _sayiyi_float_yap(value):
    try:
        temiz = str(value or "").strip().replace(",", ".")
        return float(temiz) if temiz else 0.0
    except Exception:
        return 0.0


def _row_dict_from_ws(ws, satir_no: int) -> dict:
    basliklar = _basliklar_al(ws)
    satir = _yeniden_dene("Satır okuma", ws.row_values, satir_no)
    veri = {}
    for idx, baslik in enumerate(basliklar):
        anahtar = str(baslik or "").strip()
        if not anahtar:
            continue
        veri.setdefault(anahtar, satir[idx] if idx < len(satir) else "")
    return veri


def _eksik_aciklamayi_uret(store_id: str, row_data: dict, ai_sonuc: dict, default_template: bool = False) -> str:
    try:
        from shared.store_manager import get_store
        repo_kok = Path(__file__).resolve().parent.parent
        streamlit_kok = str((repo_kok / "streamlit").resolve())
        import sys
        if streamlit_kok not in sys.path:
            sys.path.insert(0, streamlit_kok)
        from modules.ai_icerik import (
            _ai_sonuc_normallestir,
            _etsy_alanlarini_tamamla,
            _rate_limit_fallback_ai,
            _rounded_ft_etiketi,
            description_olustur,
            template_config_normallestir,
        )

        store = get_store(store_id)
        template_id = "default_v1" if default_template else store.get("template", "default_v1")
        template_name = "Default (Standart)" if default_template else store.get("store_name", store_id)
        template_config = template_config_normallestir(_template_json_yukle(template_id), template_id=template_id, template_name=template_name)

        boyut_ft = str((row_data or {}).get("boyut_ft") or "")
        boyut_cm = str((row_data or {}).get("boyut_cm") or "")
        metrekare = _sayiyi_float_yap((row_data or {}).get("metrekare"))
        fiyat_usd = int(round(_sayiyi_float_yap((row_data or {}).get("fiyat_usd"))))
        urun_id = str((row_data or {}).get("urun_id") or "")

        temel = _rate_limit_fallback_ai(
            urun_id=urun_id,
            boyut_ft=boyut_ft,
            boyut_cm=boyut_cm,
            metrekare=metrekare,
            fiyat_usd=fiyat_usd,
            genislik_cm=None,
            uzunluk_cm=None,
            template_config=template_config,
        )
        temel.pop("aciklama", None)
        temel.pop("basarili", None)
        temel.pop("hata", None)
        temel.pop("fallback_kullanildi", None)
        temel.pop("uyari", None)

        birlesik = dict(temel)
        birlesik.update(ai_sonuc or {})
        if not str(birlesik.get("baslik") or "").strip():
            birlesik["baslik"] = str((row_data or {}).get("baslik") or "")
        if not birlesik.get("taglar"):
            taglar_virgul = str((row_data or {}).get("taglar_virgul") or "")
            birlesik["taglar"] = [p.strip() for p in taglar_virgul.split(",") if p.strip()]
        for alan in ["renk1", "renk2", "pattern_etsy", "shop_section", "tip", "ana_resim_tag"]:
            if not str(birlesik.get(alan) or "").strip():
                birlesik[alan] = str((row_data or {}).get(alan) or "")

        rounded_ft = _rounded_ft_etiketi(boyut_ft)
        tip = str(birlesik.get("tip") or "Area").strip() or "Area"
        tip_lower = tip.lower()
        renk_scheme = str(birlesik.get("renk_scheme") or "Neutral tones").strip()
        style_hint = str(birlesik.get("stil") or "vintage Turkish").strip()
        room_hint = {
            "Runner": "hallways, kitchens, and entry corridors",
            "Accent": "entryways, bedsides, and layered corners",
            "Area": "living rooms, bedrooms, and collected sitting areas",
        }.get(tip, "collected interiors")
        kaynak_opening = str((ai_sonuc or {}).get("opening") or "").strip()
        kaynak_hikaye = str((ai_sonuc or {}).get("hikaye") or "").strip()
        if not kaynak_opening:
            birlesik["opening"] = (
                f"This {rounded_ft} ft Turkish {tip_lower} stands out with its {renk_scheme.lower()} palette "
                f"and the one-of-a-kind vintage character collectors look for in an authentic handmade piece."
            )
        if not kaynak_hikaye:
            birlesik["hikaye"] = "\n\n".join([
                f"Its time-softened look and {style_hint.lower()} spirit give the piece an easy, collected presence rather than a mass-produced feel.",
                f"With its {rounded_ft} ft proportions, it works especially well in {room_hint} where texture and authentic age make the strongest impact.",
                "Handmade construction adds tactile warmth and a durable, lived-in surface that layers naturally into everyday interiors.",
                "It blends comfortably with bohemian, rustic, farmhouse, and softly traditional rooms while still reading as a true one-of-a-kind vintage find.",
            ])

        birlesik = _ai_sonuc_normallestir(birlesik, template_config)
        birlesik = _etsy_alanlarini_tamamla(birlesik, boyut_ft, metrekare)
        return description_olustur(
            birlesik,
            boyut_ft,
            boyut_cm,
            metrekare,
            None,
            None,
            template_config,
            urun_id=urun_id,
        )
    except Exception as exc:
        print(f"[Sheets:{store_id}] ⚠ Açıklama backfill üretilemedi: {type(exc).__name__}: {exc}")
        return ""


def _supabase_store_status_upsert(store_id: str, row: dict):
    try:
        from shared.product_catalog import StoreCatalog, _supabase_ready
        if not _supabase_ready():
            return
        payload = {
            "product_code": str(row.get("product_code") or "").strip(),
            "store_id": str(store_id or "").strip(),
            "status": str(row.get("status") or "").strip(),
            "islem_tarihi": str(row.get("islem_tarihi") or "").strip(),
        }
        if not payload["product_code"] or not payload["store_id"]:
            return
        etsy_draft_url = str(row.get("etsy_draft_url") or "").strip()
        if etsy_draft_url:
            payload["etsy_draft_url"] = etsy_draft_url
        renk = str(row.get("renk") or "").strip()
        if renk:
            payload["renk"] = renk
        StoreCatalog().upsert([payload])
    except Exception:
        pass


def _supabase_store_status_delete(store_id: str, product_codes: list[str] | None = None):
    try:
        from shared.product_catalog import StoreCatalog, _supabase_ready
        if not _supabase_ready():
            return
        StoreCatalog().delete(store_id, product_codes)
    except Exception:
        pass


def _supabase_store_status_sync_green(store_id: str, product_codes: list[str], *, status: str = "done"):
    """Sheet'te green olan urunleri store_status tablosuna da aninda yansit."""
    try:
        from shared.product_catalog import StoreCatalog, _supabase_ready
        if not _supabase_ready():
            return
        temiz_kodlar = sorted({
            str(code or "").strip()
            for code in (product_codes or [])
            if str(code or "").strip()
        })
        if not temiz_kodlar:
            return
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        StoreCatalog().upsert([
            {
                "product_code": code,
                "store_id": str(store_id or "").strip(),
                "status": status,
                "renk": "green",
                "islem_tarihi": now_str,
            }
            for code in temiz_kodlar
        ])
    except Exception:
        pass


def _urun_satir_bul(ws, urun_id: str) -> int:
    """urun_id'ye göre satır numarası döndürür (1-tabanlı)."""
    urun_id_kol = _kolon_no(ws, "urun_id", default=KOL["urun_id"])
    tum_id = _yeniden_dene("Ürün ID kolonu okuma", ws.col_values, urun_id_kol)
    for i, v in enumerate(tum_id):
        if str(v) == str(urun_id):
            return i + 1
    return None


def _cell_str(cell: dict) -> str:
    ev = (cell or {}).get("effectiveValue", {})
    if "stringValue" in ev:
        return str(ev["stringValue"])
    if "numberValue" in ev:
        num = ev["numberValue"]
        return str(int(num) if float(num).is_integer() else num)
    if "boolValue" in ev:
        return "TRUE" if ev["boolValue"] else "FALSE"
    if "formulaValue" in ev:
        return str(ev["formulaValue"])
    return ""


def _bg_color(cell: dict) -> dict:
    fmt = (cell or {}).get("effectiveFormat", {}) or {}
    color = fmt.get("backgroundColor")
    if color:
        return color
    user_fmt = (cell or {}).get("userEnteredFormat", {}) or {}
    return user_fmt.get("backgroundColor", {}) or {}


def _renk_sinifi(color: dict) -> str | None:
    if not color:
        return None
    r = float(color.get("red", 0))
    g = float(color.get("green", 0))
    b = float(color.get("blue", 0))

    # Google Sheets tonlari birebir saf yesil/sari olmayabiliyor; baskin renge gore toleransli algila.
    if r >= 0.75 and g <= 0.88 and b <= 0.88 and r >= g + 0.08 and r >= b + 0.08:
        return "red"
    if g >= 0.55 and g >= r + 0.12 and g >= b + 0.12:
        return "green"
    if r >= 0.70 and g >= 0.70 and b <= 0.45:
        return "yellow"
    return None


def _satir_renk_sinifi(cells: list[dict]) -> str | None:
    """
    Satırın durum rengini çıkarır.
    Öncelik:
      1. A / urun_id hücresi  (manuel red/yellow işaretler burada)
      2. B / pcloud_klasor_yolu
      3. İlk veri kolonları (C-E vb.) — bazı sheet'lerde green row-highlight burada tutuluyor
    """
    aday_indeksleri = [
        KOL["urun_id"] - 1,
        KOL["pcloud_klasor"] - 1,
        KOL["boyut_cm"] - 1,
        KOL["boyut_ft"] - 1,
        KOL["metrekare"] - 1,
    ]
    for idx in aday_indeksleri:
        if idx < len(cells):
            renk = _renk_sinifi(_bg_color(cells[idx]))
            if renk:
                return renk
    return None


def _satir_haritasi(ws) -> dict:
    """urun_id -> satir_no (1-tabanli) map'i döner."""
    urun_id_kol = _kolon_no(ws, "urun_id", default=KOL["urun_id"])
    tum_id = _yeniden_dene("Satır haritası okuma", ws.col_values, urun_id_kol)
    sonuc = {}
    for i, v in enumerate(tum_id[1:], start=2):
        key = str(v or "").strip()
        if key:
            sonuc[key] = i
    return sonuc


# ── Ana sınıf ─────────────────────────────────────────────────────────────────

class SheetsKatmani:
    """
    Belirli bir mağazanın Google Sheets sekmesine bağlı kuyruk yöneticisi.
    Her mağaza kendi sheet_tab'ına yazar — veri izolasyonu bu sınıfla sağlanır.
    """

    def __init__(self, store_id: str):
        from shared.store_manager import get_store
        self.store_id = store_id
        store = get_store(store_id)
        self.sheet_tab = store["sheet_tab"]
        sheet_id = store.get("google_sheet_id") or os.environ.get("GOOGLE_SHEET_ID", "")
        if not sheet_id:
            raise ValueError("GOOGLE_SHEET_ID env değişkeni eksik ve stores.json'da google_sheet_id yok.")
        self._gc = _client()
        self._sp = _spreadsheet(sheet_id)
        self._sheet = None
        self._satir_map_cache = None
        print(f"[Sheets] Bağlandı → mağaza={store_id} sekme={self.sheet_tab}")

    def _baglanti(self):
        def _eslesen_ws_bul(worksheetler):
            for ws in worksheetler:
                if str(ws.title).strip() == self.sheet_tab:
                    return ws
            for ws in worksheetler:
                if str(ws.title).strip().lower() == self.sheet_tab.lower():
                    if str(ws.title).strip() != self.sheet_tab:
                        _yeniden_dene("Worksheet yeniden adlandirma", ws.update_title, self.sheet_tab)
                    return ws
            return None

        if self._sheet is None:
            try:
                self._sheet = _yeniden_dene("Worksheet açma", self._sp.worksheet, self.sheet_tab)
            except WorksheetNotFound:
                mevcutlar = _yeniden_dene("Worksheet listesi okuma", self._sp.worksheets)
                self._sheet = _eslesen_ws_bul(mevcutlar)

                if self._sheet is None:
                    try:
                        # Yeni mağaza eklendiyse sekmeyi otomatik açarak mimariyi tutarlı tut.
                        self._sheet = _yeniden_dene(
                            "Worksheet oluşturma",
                            self._sp.add_worksheet,
                            title=self.sheet_tab,
                            rows=QUEUE_SHEET_MIN_ROWS,
                            cols=max(len(BASLIK_SATIRI), QUEUE_SHEET_MIN_COLS),
                        )
                        _yeniden_dene("Başlık satırını yazma", self._sheet.update, [BASLIK_SATIRI], "A1")
                        print(f"[Sheets:{self.store_id}] ✓ Eksik sekme otomatik oluşturuldu: {self.sheet_tab}")
                    except APIError as exc:
                        if "already exists" not in str(exc):
                            raise
                        mevcutlar = _yeniden_dene("Worksheet listesi yeniden okuma", self._sp.worksheets)
                        self._sheet = _eslesen_ws_bul(mevcutlar)
                        if self._sheet is None:
                            raise
        return self._sheet

    def _satir_haritasi_al(self, ws=None, force_refresh: bool = False) -> dict:
        if force_refresh or self._satir_map_cache is None:
            self._satir_map_cache = _satir_haritasi(ws or self._baglanti())
        return self._satir_map_cache

    def _satir_haritasini_gecersiz_kil(self):
        self._satir_map_cache = None

    def _worksheet_kapasitesini_guvenceye_al(
        self,
        ws,
        hedef_satir: int | None = None,
        hedef_kolon: int | None = None,
        satir_bufferi: int = 200,
    ):
        """
        Hedef yazma araligi mevcut grid'i asiyorsa worksheet'i onceden buyutur.
        Google Sheets 1000 satirlik varsayilan limitte takilmasin diye yazmadan once cagrilir.
        """
        yeni_satir_sayisi = ws.row_count
        yeni_kolon_sayisi = ws.col_count
        degisti = False

        if hedef_satir and hedef_satir > ws.row_count:
            yeni_satir_sayisi = max(hedef_satir + satir_bufferi, ws.row_count + satir_bufferi)
            degisti = True

        if hedef_kolon and hedef_kolon > ws.col_count:
            yeni_kolon_sayisi = hedef_kolon
            degisti = True

        if not degisti:
            return

        _yeniden_dene(
            "Worksheet kapasitesini buyutme",
            ws.resize,
            rows=yeni_satir_sayisi,
            cols=yeni_kolon_sayisi,
        )
        print(
            f"[Sheets:{self.store_id}] ✓ Worksheet buyutuldu: "
            f"rows={ws.row_count}->{yeni_satir_sayisi}, cols={ws.col_count}->{yeni_kolon_sayisi}"
        )

    def _satir_yuksekliklerini_sabitle(self, satir_nolari: list[int], pixel_size: int = 21):
        """Verilen satırların yüksekliğini PatchArts görünümüyle aynı olacak şekilde sabitler."""
        ws = self._baglanti()
        satirlar = sorted({int(s) for s in satir_nolari if int(s) >= 2})
        if not satirlar:
            return

        bloklar = []
        baslangic = onceki = satirlar[0]
        for satir_no in satirlar[1:]:
            if satir_no == onceki + 1:
                onceki = satir_no
                continue
            bloklar.append((baslangic, onceki))
            baslangic = onceki = satir_no
        bloklar.append((baslangic, onceki))

        requests = []
        for start_row, end_row in bloklar:
            requests.append({
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": ws.id,
                        "dimension": "ROWS",
                        "startIndex": start_row - 1,
                        "endIndex": end_row,
                    },
                    "properties": {"pixelSize": pixel_size},
                    "fields": "pixelSize",
                }
            })

        _yeniden_dene("Satır yüksekliği sabitleme", ws.spreadsheet.batch_update, {"requests": requests})

    def _kolon_formatlarini_normallestir(self):
        """
        Görsel stabilite için bazı kolonlarda hücre davranışını sabitler.
        - H(aciklama): PatchArts gibi taşabilir kalsın
        - I(taglar_virgul): sağ hücreye taşmasın, kendi hücresinde clip olsun
        """
        ws = self._baglanti()
        requests = [
            {
                "repeatCell": {
                    "range": {
                        "sheetId": ws.id,
                        "startRowIndex": 1,
                        "startColumnIndex": KOL["aciklama"] - 1,
                        "endColumnIndex": KOL["aciklama"],
                    },
                    "cell": {"userEnteredFormat": {"wrapStrategy": "OVERFLOW_CELL"}},
                    "fields": "userEnteredFormat.wrapStrategy",
                }
            },
            {
                "repeatCell": {
                    "range": {
                        "sheetId": ws.id,
                        "startRowIndex": 1,
                        "startColumnIndex": KOL["taglar_virgul"] - 1,
                        "endColumnIndex": KOL["taglar_virgul"],
                    },
                    "cell": {"userEnteredFormat": {"wrapStrategy": "CLIP"}},
                    "fields": "userEnteredFormat.wrapStrategy",
                }
            },
        ]
        _yeniden_dene("Kolon formatlarını normallestirme", ws.spreadsheet.batch_update, {"requests": requests})

    # ── Okuma ──────────────────────────────────────────────────────────────────

    def tum_satirlar_al(self) -> list:
        return _tum_satirlar_al(self._baglanti())

    def urun_renk_durumlari_al(self) -> dict:
        """
        Satırdaki durum renginden ürün durumu çıkarır.
        green  -> Etsy'e gerçekten yüklendi
        yellow -> Yüklenemedi / manuel uyarı
        red    -> Etsy'den manuel silindi / silinmiş olarak işaretlendi
        """
        meta = _yeniden_dene(
            "Satır renk metadata okuma",
            self._sp.fetch_sheet_metadata,
            params={
                "includeGridData": "true",
                "ranges": self.sheet_tab,
            },
        )
        sheets = meta.get("sheets", [])
        if not sheets:
            return {}

        data = sheets[0].get("data", [])
        if not data:
            return {}

        row_data = data[0].get("rowData", [])
        sonuc = {}

        for row in row_data[1:]:
            cells = row.get("values", [])
            if not cells:
                continue

            urun_id = _cell_str(cells[KOL["urun_id"] - 1]) if len(cells) >= KOL["urun_id"] else ""
            urun_id = str(urun_id or "").strip()
            if not urun_id:
                continue

            renk = _satir_renk_sinifi(cells)
            if renk:
                sonuc[urun_id] = renk

        return sonuc

    def ready_urunleri_al(self, limit: int = 100) -> list:
        tum = _tum_satirlar_al(self._baglanti())
        renk_durumlari = self.urun_renk_durumlari_al()
        ready = [
            s for s in tum
            if s.get("status") == "ready"
            and renk_durumlari.get(str(s.get("urun_id", "")).strip()) not in {"green", "yellow"}
        ]
        return ready[:limit]

    def downloaded_urunleri_al(self, limit: int = 100) -> list:
        tum = _tum_satirlar_al(self._baglanti())
        return [s for s in tum if s.get("status") == "downloaded"][:limit]

    def pending_urunleri_al(self) -> list:
        tum = _tum_satirlar_al(self._baglanti())
        return [s for s in tum if s.get("status") == "pending"]

    # ── Yazma ──────────────────────────────────────────────────────────────────

    def urun_ekle(self, urun_bilgisi: dict, pcloud_klasor_yolu: str,
                  pcloud_klasor_id: int = 0) -> int:
        """
        Yeni ürün satırı ekler, status=pending olarak.
        Returns: satir_no (1-tabanlı)
        """
        self.sheet_hazirla()
        ws = self._baglanti()
        basliklar = _basliklar_al(ws)

        def _v(key, default=""):
            val = urun_bilgisi.get(key)
            return val if val is not None else default

        satir = [""] * max(len(basliklar), len(BASLIK_SATIRI))
        alanlar = {
            ("urun_id", 0): _v("urun_id"),
            ("urun_id", 1): _v("urun_id"),
            ("pcloud_klasor_yolu", 0): pcloud_klasor_yolu,
            ("boyut_cm", 0): _v("boyut_cm"),
            ("boyut_ft", 0): _v("boyut_ft"),
            ("metrekare", 0): _v("metrekare"),
            ("fotograf_sayisi", 0): _v("fotograf_sayisi"),
            ("fiyat_usd", 0): _v("fiyat_usd"),
            ("shop_section", 0): "",
            ("status", 0): "pending",
            ("tip", 0): "",
            ("etsy_draft_url", 0): "",
            ("hata_mesaji", 0): "",
            ("islem_tarihi", 0): datetime.now().strftime("%Y-%m-%d %H:%M"),
            ("pcloud_klasor_id", 0): str(pcloud_klasor_id) if pcloud_klasor_id else "",
            ("ana_resim_tag", 0): "",
        }

        for (baslik, occurrence), deger in alanlar.items():
            kolon = _kolon_no(ws, baslik, occurrence=occurrence)
            if kolon:
                satir[kolon - 1] = deger

        # append_row table-detection'ı bozuk olduğunda yanlış kolona yazıyor.
        # Bunun yerine ilk gerçekten boş satırı bulup update() ile doğrudan yaz.
        satir_no = _siradaki_yazilabilir_satir_no(ws)
        self._worksheet_kapasitesini_guvenceye_al(
            ws,
            hedef_satir=satir_no,
            hedef_kolon=len(satir),
        )
        _yeniden_dene("Yeni ürün satırı yazma", ws.update, [satir], f"A{satir_no}")
        self._satir_haritasini_gecersiz_kil()

        # Emniyet payı: hızlı bulk girişte Sheets API rate limit aşılmasın
        time.sleep(0.8)

        _supabase_store_status_upsert(
            self.store_id,
            {
                "product_code": urun_bilgisi.get("urun_id"),
                "status": "pending",
                "islem_tarihi": datetime.now().strftime("%Y-%m-%d %H:%M"),
            },
        )

        print(f"[Sheets:{self.store_id}] ✓ Ürün eklendi: {urun_bilgisi['urun_id']} → satır {satir_no}")
        return satir_no

    def ai_verileri_yaz(self, urun_id: str, ai_sonuc: dict, satir_no: int = None):
        """
        AI'dan gelen başlık, açıklama, taglar vs. Sheet'e yazar.
        status → ready yapar.
        satir_no verilirse arama yapmadan doğrudan o satıra yazar.
        """
        self.sheet_hazirla()
        ws = self._baglanti()

        if not satir_no:
            satir_no = self._satir_haritasi_al(ws).get(str(urun_id))
        if not satir_no:
            tum_id = _yeniden_dene("Mevcut ürün ID listesi okuma", ws.col_values, _kolon_no(ws, "urun_id", default=KOL["urun_id"]))
            raise ValueError(f"Sheet'te '{urun_id}' bulunamadı. Mevcut ID'ler: {tum_id[1:]}")

        pozisyonlar = _baslik_pozisyonlari(ws)
        row_data = _row_dict_from_ws(ws, satir_no)
        taglar = ai_sonuc.get("taglar", [])
        taglar = (taglar + [""] * 13)[:13]

        renkler = [r.strip() for r in str(ai_sonuc.get("renk1", ai_sonuc.get("renk", ""))).split(",")]
        aciklama = str(ai_sonuc.get("aciklama", "") or "").strip()
        if not aciklama:
            aciklama = _eksik_aciklamayi_uret(self.store_id, row_data, ai_sonuc)

        guncellemeler = {
            "baslik": ai_sonuc.get("baslik", ""),
            "aciklama": aciklama,
            "taglar_virgul": ", ".join([t for t in taglar if t]),
            "renk1": renkler[0] if renkler else "",
            "renk2": renkler[1] if len(renkler) > 1 else ai_sonuc.get("renk2", ""),
            "pattern_etsy": ai_sonuc.get("pattern_etsy", ""),
            "shop_section": ai_sonuc.get("shop_section", ""),
            "status": "ready",
            "tip": ai_sonuc.get("tip", ""),
            "islem_tarihi": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "ana_resim_tag": ai_sonuc.get("ana_resim_tag", ""),
        }
        batch_veri = []
        for baslik, deger in guncellemeler.items():
            kolon = _kolon_no_from_positions(pozisyonlar, baslik)
            if kolon:
                batch_veri.append({
                    "range": rowcol_to_a1(satir_no, kolon),
                    "values": [[deger]],
                })

        for idx, tag in enumerate(taglar, start=1):
            kolon = _kolon_no_from_positions(pozisyonlar, f"tag{idx}")
            if kolon:
                batch_veri.append({
                    "range": rowcol_to_a1(satir_no, kolon),
                    "values": [[tag]],
                })

        _yeniden_dene("AI verilerini yazma", ws.batch_update, batch_veri)

        _supabase_store_status_upsert(
            self.store_id,
            {
                "product_code": urun_id,
                "status": "ready",
                "islem_tarihi": datetime.now().strftime("%Y-%m-%d %H:%M"),
            },
        )

        # Satır yüksekliğini 21px sabit tut (description açılmasın)
        self._satir_yuksekliklerini_sabitle([satir_no], pixel_size=21)

        print(f"[Sheets:{self.store_id}] ✓ AI verileri yazıldı: {urun_id}")

    def bos_aciklamalari_onar(self, limit: int | None = None, only_statuses: set[str] | None = None, default_template: bool = False) -> dict:
        self.sheet_hazirla()
        ws = self._baglanti()
        satirlar = _tum_satirlar_al(ws)
        pozisyonlar = _baslik_pozisyonlari(ws)
        requests = []
        onarilan = []

        for idx, row in enumerate(satirlar, start=2):
            urun_id = str((row or {}).get("urun_id") or "").strip()
            baslik = str((row or {}).get("baslik") or "").strip()
            aciklama = str((row or {}).get("aciklama") or "").strip()
            status = str((row or {}).get("status") or "").strip().lower()
            if not urun_id or not baslik or aciklama:
                continue
            if only_statuses and status not in only_statuses:
                continue
            yeni_aciklama = _eksik_aciklamayi_uret(self.store_id, row, row, default_template=default_template)
            if not str(yeni_aciklama or "").strip():
                continue
            kolon = _kolon_no_from_positions(pozisyonlar, "aciklama", default=KOL["aciklama"])
            if not kolon:
                continue
            requests.append({
                "range": rowcol_to_a1(idx, kolon),
                "values": [[yeni_aciklama]],
            })
            onarilan.append(urun_id)
            if limit and len(onarilan) >= limit:
                break

        if requests:
            _yeniden_dene("Boş açıklamaları onarma", ws.batch_update, requests)
            satir_map = self._satir_haritasi_al(ws, force_refresh=True)
            satir_nolari = [satir_map.get(uid) for uid in onarilan if satir_map.get(uid)]
            if satir_nolari:
                self._satir_yuksekliklerini_sabitle(satir_nolari, pixel_size=21)

        print(f"[Sheets:{self.store_id}] ✓ Boş açıklama onarımı: {len(onarilan)}")
        return {"onarilan": onarilan, "adet": len(onarilan)}

    def status_guncelle(self, urun_id: str, yeni_status: str,
                        etsy_url: str = "", hata: str = ""):
        """Ürün durumunu günceller."""
        self.sheet_hazirla()
        ws = self._baglanti()
        satir_no = self._satir_haritasi_al(ws).get(str(urun_id))
        if not satir_no:
            self._satir_haritasini_gecersiz_kil()
            satir_no = self._satir_haritasi_al(ws, force_refresh=True).get(str(urun_id))
        if not satir_no:
            tum_id = _yeniden_dene("Mevcut ürün ID listesi okuma", ws.col_values, _kolon_no(ws, "urun_id", default=KOL["urun_id"]))
            print(f"[Sheets:{self.store_id}] ⚠ '{urun_id}' bulunamadı! Mevcut: {tum_id[1:6]}")
            return

        print(f"[Sheets:{self.store_id}] Yazılıyor → satır:{satir_no} status:{yeni_status}")
        pozisyonlar = _baslik_pozisyonlari(ws)
        batch_veri = [{
            "range": rowcol_to_a1(satir_no, _kolon_no_from_positions(pozisyonlar, "status", default=KOL["status"])),
            "values": [[yeni_status]],
        }]
        if etsy_url:
            batch_veri.append({
                "range": rowcol_to_a1(satir_no, _kolon_no_from_positions(pozisyonlar, "etsy_draft_url", default=KOL["etsy_draft_url"])),
                "values": [[etsy_url]],
            })
        if hata:
            batch_veri.append({
                "range": rowcol_to_a1(satir_no, _kolon_no_from_positions(pozisyonlar, "hata_mesaji", default=KOL["hata_mesaji"])),
                "values": [[hata]],
            })
        batch_veri.append({
            "range": rowcol_to_a1(satir_no, _kolon_no_from_positions(pozisyonlar, "islem_tarihi", default=KOL["islem_tarihi"])),
            "values": [[datetime.now().strftime("%Y-%m-%d %H:%M")]],
        })
        _yeniden_dene("Status güncelleme", ws.batch_update, batch_veri)
        _renk = "green" if yeni_status == "done" else ""
        _supabase_store_status_upsert(
            self.store_id,
            {
                "product_code": urun_id,
                "status": yeni_status,
                "islem_tarihi": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "etsy_draft_url": etsy_url,
                "renk": _renk,
            },
        )
        print(f"[Sheets:{self.store_id}] ✓ Status: {urun_id} → {yeni_status}")

    def urunleri_renklendir(self, urun_idler: list[str], renk: str) -> dict:
        """
        Verilen urun_id'lerin A sütunundaki hücresini topluca renklendirir.

        Returns:
            {"guncellenen": int, "bulunamayan": list[str]}
        """
        if renk not in RENK_TANIMLARI:
            raise ValueError(f"Bilinmeyen renk: {renk}")

        self.sheet_hazirla()
        ws = self._baglanti()
        satir_map = _satir_haritasi(ws)
        bulunamayan = []
        requests = []

        for urun_id in urun_idler:
            key = str(urun_id or "").strip()
            if not key:
                continue
            satir_no = satir_map.get(key)
            if not satir_no:
                bulunamayan.append(key)
                continue

            cell_fmt = {}
            bg = RENK_TANIMLARI[renk]
            if bg is not None:
                cell_fmt["backgroundColor"] = bg

            requests.append({
                "repeatCell": {
                    "range": {
                        "sheetId": ws.id,
                        "startRowIndex": satir_no - 1,
                        "endRowIndex": satir_no,
                        "startColumnIndex": KOL["urun_id"] - 1,
                        "endColumnIndex": KOL["urun_id"],
                    },
                    "cell": {"userEnteredFormat": cell_fmt},
                    "fields": "userEnteredFormat.backgroundColor",
                }
            })

        if requests:
            _yeniden_dene("Renk güncelleme", ws.spreadsheet.batch_update, {"requests": requests})

        guncellenen_kodlar = [
            str(urun_id or "").strip()
            for urun_id in urun_idler
            if str(urun_id or "").strip() and str(urun_id or "").strip() not in bulunamayan
        ]
        if renk == "green":
            _supabase_store_status_sync_green(self.store_id, guncellenen_kodlar, status="done")
        elif renk == "none":
            _supabase_store_status_delete(self.store_id, guncellenen_kodlar)

        print(
            f"[Sheets:{self.store_id}] ✓ Renk güncellendi: "
            f"renk={renk} guncellenen={len(requests)} bulunamayan={len(bulunamayan)}"
        )
        return {"guncellenen": len(requests), "bulunamayan": bulunamayan}

    def etsy_csv_kayitlarini_isle(
        self,
        kayitlar: list[dict],
        renk: str = "green",
        durum: str = "done",
    ) -> dict:
        """
        Etsy CSV'den gelen kayıtları sheet'e yazar/günceller.

        Beklenen alanlar:
          urun_id, baslik, aciklama, taglar_virgul

        Davranış:
          - urun_id sheet'te varsa ilgili satırın sadece A/G/H/I/P alanlarını günceller
          - yoksa yeni satır ekler
          - en sonda A sütununu verilen renkle işaretler
        """
        if renk not in RENK_TANIMLARI:
            raise ValueError(f"Bilinmeyen renk: {renk}")

        self.sheet_hazirla()
        ws = self._baglanti()
        basliklar = _basliklar_al(ws)
        pozisyonlar = _baslik_pozisyonlari(ws)
        satir_map = self._satir_haritasi_al(ws, force_refresh=True)

        def _bos_satir():
            return [""] * max(len(basliklar), len(BASLIK_SATIRI))

        def _satira_yaz(satir: list, alan: str, deger, occurrence: int = 0):
            kolon = _kolon_no_from_positions(pozisyonlar, alan, occurrence=occurrence)
            if kolon:
                satir[kolon - 1] = deger

        yeni_satirlar = []
        guncelleme_batch = []
        islenen_urun_idler = []

        for kayit in kayitlar:
            urun_id = str(kayit.get("urun_id") or "").strip()
            if not urun_id:
                continue

            islenen_urun_idler.append(urun_id)
            baslik = str(kayit.get("baslik") or "")
            aciklama = str(kayit.get("aciklama") or "")
            taglar_virgul = str(kayit.get("taglar_virgul") or "")
            satir_no = satir_map.get(urun_id)

            if satir_no:
                for alan, deger, occurrence in [
                    ("urun_id", urun_id, 0),
                    ("urun_id", urun_id, 1),
                    ("baslik", baslik, 0),
                    ("aciklama", aciklama, 0),
                    ("taglar_virgul", taglar_virgul, 0),
                    ("status", durum, 0),
                    ("islem_tarihi", datetime.now().strftime("%Y-%m-%d %H:%M"), 0),
                ]:
                    kolon = _kolon_no_from_positions(pozisyonlar, alan, occurrence=occurrence)
                    if kolon:
                        guncelleme_batch.append({
                            "range": rowcol_to_a1(satir_no, kolon),
                            "values": [[deger]],
                        })
                continue

            satir = _bos_satir()
            _satira_yaz(satir, "urun_id", urun_id, occurrence=0)
            _satira_yaz(satir, "urun_id", urun_id, occurrence=1)
            _satira_yaz(satir, "baslik", baslik)
            _satira_yaz(satir, "aciklama", aciklama)
            _satira_yaz(satir, "taglar_virgul", taglar_virgul)
            _satira_yaz(satir, "status", durum)
            _satira_yaz(satir, "islem_tarihi", datetime.now().strftime("%Y-%m-%d %H:%M"))
            yeni_satirlar.append(satir)

        if guncelleme_batch:
            _yeniden_dene("CSV alanlarını güncelleme", ws.batch_update, guncelleme_batch)

        eklenen = 0
        if yeni_satirlar:
            baslangic_satiri = _siradaki_yazilabilir_satir_no(ws)
            bitis_satiri = baslangic_satiri + len(yeni_satirlar) - 1
            self._worksheet_kapasitesini_guvenceye_al(
                ws,
                hedef_satir=bitis_satiri,
                hedef_kolon=len(yeni_satirlar[0]) if yeni_satirlar else len(BASLIK_SATIRI),
            )
            _yeniden_dene("CSV yeni satırları yazma", ws.update, yeni_satirlar, f"A{baslangic_satiri}")
            eklenen = len(yeni_satirlar)
            self._satir_haritasini_gecersiz_kil()

        renk_sonuc = self.urunleri_renklendir(islenen_urun_idler, renk)
        satir_map_son = self._satir_haritasi_al(ws, force_refresh=True)
        self._satir_yuksekliklerini_sabitle(
            [satir_map_son[uid] for uid in islenen_urun_idler if uid in satir_map_son],
            pixel_size=21,
        )

        return {
            "toplam": len(islenen_urun_idler),
            "eklenen": eklenen,
            "guncellenen": len(guncelleme_batch),
            "renk_guncellenen": renk_sonuc["guncellenen"],
            "bulunamayan": renk_sonuc["bulunamayan"],
        }

    def urun_renklerini_temizle(self, urun_idler: list[str]) -> dict:
        """Verilen urun_id'lerin A sütunundaki arka plan rengini temizler."""
        return self.urunleri_renklendir(urun_idler, "none")

    def satirlari_sil(self, urun_idler: list) -> int:
        """
        Belirtilen urun_id listesindeki satırları siler.
        Büyükten küçüğe sıralar — üstten silince index kaymasın.
        """
        self.sheet_hazirla()
        ws = self._baglanti()
        tum_id = _yeniden_dene("Silme öncesi ürün ID listesi okuma", ws.col_values, _kolon_no(ws, "urun_id", default=KOL["urun_id"]))

        satir_nolari = []
        for urun_id in urun_idler:
            for i, v in enumerate(tum_id):
                if str(v) == str(urun_id):
                    satir_nolari.append(i + 1)
                    break

        for satir_no in sorted(satir_nolari, reverse=True):
            _yeniden_dene("Satır silme", ws.delete_rows, satir_no)

        self._satir_haritasini_gecersiz_kil()

        print(f"[Sheets:{self.store_id}] {len(satir_nolari)} satır silindi.")
        return len(satir_nolari)

    def sheet_hazirla(self):
        """Sheet boşsa başlık satırı ekler, eksik kolonları günceller."""
        ws = self._baglanti()
        ilk_satir = _yeniden_dene("İlk satırı okuma", ws.row_values, 1)
        ikinci_satir = _yeniden_dene("İkinci satırı okuma", ws.row_values, 2)
        ilk_hucre = str((ilk_satir[0] if ilk_satir else "") or "").strip()

        if ilk_satir == BASLIK_SATIRI and ikinci_satir == BASLIK_SATIRI:
            _yeniden_dene("Yinelenen başlık satırını silme", ws.delete_rows, 2)
            ikinci_satir = []
            print(f"[Sheets:{self.store_id}] ✓ Yinelenen başlık satırı temizlendi.")

        if ws.row_count == 0 or not ilk_satir:
            _yeniden_dene("Başlık satırı yazma", ws.update, [BASLIK_SATIRI], "A1")
            print(f"[Sheets:{self.store_id}] ✓ Başlık satırı oluşturuldu.")
        elif ilk_hucre != "urun_id":
            _yeniden_dene("Başlık satırı ekleme", ws.insert_row, BASLIK_SATIRI, index=1)
            print(f"[Sheets:{self.store_id}] ✓ Başlık satırı üste eklendi.")
        else:
            mevcut = ilk_satir
            eksik = [b for b in BASLIK_SATIRI if b not in mevcut]
            if eksik:
                for baslik in eksik:
                    hedef_kol = BASLIK_SATIRI.index(baslik)
                    if hedef_kol < len(mevcut) and mevcut[hedef_kol] != baslik:
                        _yeniden_dene(
                            "Eksik kolon ekleme",
                            ws.spreadsheet.batch_update,
                            {"requests": [{"insertDimension": {
                                "range": {"sheetId": ws.id, "dimension": "COLUMNS",
                                          "startIndex": hedef_kol, "endIndex": hedef_kol + 1},
                                "inheritFromBefore": False
                            }}]},
                        )
                        mevcut.insert(hedef_kol, baslik)
                    _yeniden_dene("Başlık hücresi yazma", ws.update_cell, 1, hedef_kol + 1, baslik)
                print(f"[Sheets:{self.store_id}] ✓ Eksik kolonlar eklendi: {eksik}")
            else:
                print(f"[Sheets:{self.store_id}] Başlık zaten güncel.")

        self._worksheet_kapasitesini_guvenceye_al(
            ws,
            hedef_satir=QUEUE_SHEET_MIN_ROWS,
            hedef_kolon=max(len(BASLIK_SATIRI), QUEUE_SHEET_MIN_COLS),
            satir_bufferi=0,
        )
        self._kolon_formatlarini_normallestir()


# ── Config (tüm mağazalar için ortak) ────────────────────────────────────────

CONFIG_ALANLARI = [
    ("PCLOUD_TOKEN",             "pCloud oturum token'ı"),
    ("GEMINI_API_KEY",           "Google Gemini API anahtarı"),
    ("ETSY_API_KEY",             "Etsy API anahtarı"),
    ("ETSY_SHARED_SECRET",       "Etsy API gizli anahtarı"),
    ("ETSY_SHOP_ID",             "Etsy mağaza ID'si"),
    ("ETSY_SHIPPING_PROFILE_ID", "Etsy kargo profil ID'si"),
]


def _config_ws():
    """Config sekmesine bağlanır — yoksa oluşturur."""
    spreadsheet = _spreadsheet(os.environ.get("GOOGLE_SHEET_ID", SHEET_ID))
    try:
        return _yeniden_dene("Config worksheet açma", spreadsheet.worksheet, "config")
    except gspread.WorksheetNotFound:
        ws = _yeniden_dene("Config worksheet oluşturma", spreadsheet.add_worksheet, title="config", rows=50, cols=3)
        _yeniden_dene("Config başlığı yazma", ws.append_row, ["key", "value", "aciklama"])
        return ws


def config_oku() -> dict:
    """Config sekmesindeki tüm key-value çiftlerini dict olarak döner."""
    ws = _config_ws()
    satirlar = _yeniden_dene("Config okuma", ws.get_all_values)
    return {
        str(s[0]).strip(): str(s[1]).strip()
        for s in satirlar[1:]
        if len(s) >= 2 and s[0] and s[1]
    }


def config_yaz(key: str, value: str):
    """Config sekmesinde key'i günceller, yoksa ekler."""
    ws = _config_ws()
    satirlar = _yeniden_dene("Config satırlarını okuma", ws.get_all_values)
    for i, s in enumerate(satirlar):
        if s and str(s[0]).strip() == key:
            _yeniden_dene("Config hücresi güncelleme", ws.update_cell, i + 1, 2, value)
            print(f"[Config] ✓ {key} güncellendi")
            return
    aciklama = next((a for k, a in CONFIG_ALANLARI if k == key), "")
    _yeniden_dene("Config satırı ekleme", ws.append_row, [key, value, aciklama])
    print(f"[Config] ✓ {key} eklendi")


def tum_magaza_sekmelerini_hazirla() -> list[str]:
    """stores.json içindeki tüm mağazaların sekmelerini hazırlar."""
    from shared.store_manager import tum_magazalar

    hazirlanan = []
    for magaza in tum_magazalar():
        store_id = str(magaza.get("store_id") or "").strip()
        if not store_id:
            continue
        SheetsKatmani(store_id).sheet_hazirla()
        hazirlanan.append(store_id)
    return hazirlanan


# ── Backwards-compat wrappers (PatchArts varsayılanı) ────────────────────────
# Bu fonksiyonlar eski çağrı noktaları için korunur.

def _baglanti():
    return SheetsKatmani("PatchArts")._baglanti()


def tum_satirlar_al(ws=None) -> list:
    if ws is None:
        return SheetsKatmani("PatchArts").tum_satirlar_al()
    return _tum_satirlar_al(ws)


def sheet_hazirla():
    SheetsKatmani("PatchArts").sheet_hazirla()


def urun_ekle(urun_bilgisi: dict, pcloud_klasor_yolu: str,
              pcloud_klasor_id: int = 0) -> int:
    return SheetsKatmani("PatchArts").urun_ekle(urun_bilgisi, pcloud_klasor_yolu, pcloud_klasor_id)


def ai_verileri_yaz(urun_id: str, ai_sonuc: dict, satir_no: int = None):
    SheetsKatmani("PatchArts").ai_verileri_yaz(urun_id, ai_sonuc, satir_no)


def status_guncelle(urun_id: str, yeni_status: str, etsy_url: str = "", hata: str = ""):
    SheetsKatmani("PatchArts").status_guncelle(urun_id, yeni_status, etsy_url, hata)


def ready_urunleri_al(limit: int = 100) -> list:
    return SheetsKatmani("PatchArts").ready_urunleri_al(limit)


def downloaded_urunleri_al(limit: int = 100) -> list:
    return SheetsKatmani("PatchArts").downloaded_urunleri_al(limit)


def pending_urunleri_al() -> list:
    return SheetsKatmani("PatchArts").pending_urunleri_al()


def satirlari_sil(urun_idler: list) -> int:
    return SheetsKatmani("PatchArts").satirlari_sil(urun_idler)


# ── Kurulum testi ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Sheets bağlantısı test ediliyor...")
    if not os.environ.get("GOOGLE_SHEET_ID"):
        print("HATA: GOOGLE_SHEET_ID environment variable eksik.")
    else:
        sk = SheetsKatmani("PatchArts")
        sk.sheet_hazirla()
        print("✓ PatchArts sekmesi hazır.")
