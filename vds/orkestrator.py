"""
orkestrator.py
VDS'te çalışan ana döngü — tüm aktif mağazaları işler.

Akış:
  1. stores.json'dan aktif mağazaları al
  2. Her mağaza için ready ürünleri çek
  3. pCloud'dan fotoğrafları indir  (status: downloading)
  4. Dosyaları SEO uyumlu adlandır
  5. status → downloaded

Çalıştırma (Windows VDS):
  python orkestrator.py
"""

import asyncio
import random
import re as _re
import os
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

# vds/.env dosyasından yükle (varsa) — git pull bu dosyaya dokunmaz
_env_path = Path(__file__).parent / ".env"
if _env_path.exists():
    for _line in _env_path.read_text().splitlines():
        if "=" in _line and not _line.startswith("#"):
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())

from modules.pcloud_indirici import pcloud_klasor_indir
from shared.sheets import SheetsKatmani, config_oku
from shared.store_manager import aktif_magazalar
try:
    from video_generator import generate_product_video as _gen_video
    _VIDEO_OK = True
except ImportError:
    _VIDEO_OK = False

TEMP_DIR            = Path(os.environ.get("TEMP_DIR", r"C:\etsy_temp"))
ISLEMLER_ARASI_MIN  = 3    # saniye
ISLEMLER_ARASI_MAX  = 10   # saniye
_VDS_DIR            = Path(__file__).parent
_INTRO_LOGO_CANDIDATES = {
    "loomantikrugs": [
        _VDS_DIR / "assets" / "loomantikrugs_logo.png",
        _VDS_DIR / "Loom.png",
    ],
}


def _mockup_mu(path_or_name: str) -> bool:
    ad = Path(path_or_name).name.lower()
    anahtarlar = [
        "mockup",
        "mock-up",
        "roomview",
        "room-view",
        "room_view",
        "lifestyle",
        "styled",
        "in-situ",
        "insitu",
    ]
    return any(anahtar in ad for anahtar in anahtarlar)


def _mockup_skoru(path_or_name: str) -> int:
    ad = Path(path_or_name).name.lower()
    skor = 0
    if "mockup" in ad or "mock-up" in ad:
        skor += 100
    if "roomview" in ad or "room-view" in ad or "room_view" in ad:
        skor += 80
    if "lifestyle" in ad:
        skor += 60
    if "styled" in ad:
        skor += 40
    if "in-situ" in ad or "insitu" in ad:
        skor += 30
    return skor


def _mockup_yolunu_bul(dosyalar: list) -> str:
    adaylar = [str(yol) for yol in dosyalar if _mockup_mu(yol)]
    if adaylar:
        return max(adaylar, key=lambda yol: (_mockup_skoru(yol), Path(yol).name.lower()))
    return str(dosyalar[0]) if dosyalar else ""


def _intro_logo_yolu(store_id: str):
    for aday in _INTRO_LOGO_CANDIDATES.get(store_id, []):
        if aday.exists():
            return aday
    return None


def _video_uret(klasor: str, store_id: str, urun_id: str, dosyalar: list, mockup_path: str = ""):
    """İndirilen görseller için 2 MP4 video üretir. Hata ürün akışını durdurmaz."""
    if not _VIDEO_OK:
        print("  [Video] opencv-python kurulu değil, atlanıyor.")
        return

    SUPPORTED = {".jpg", ".jpeg", ".png"}
    safe_store = _re.sub(r"[^\w-]", "_", store_id).lower()
    intro_logo = _intro_logo_yolu(safe_store)

    all_images = [
        p for p in dosyalar
        if Path(p).suffix.lower() in SUPPORTED
    ]

    if not all_images:
        print(f"  [Video] Görsel bulunamadı, atlanıyor.")
        return

    if mockup_path and Path(mockup_path).exists():
        mockup_path = str(mockup_path)
    else:
        mockup_path = _mockup_yolunu_bul(all_images)

    print(f"  [Video] Mockup secildi: {Path(mockup_path).name}")

    product_images = [str(p) for p in all_images if str(p) != str(mockup_path) and not _mockup_mu(p)]

    for vname, include_mockup in [
        (f"{urun_id}_{safe_store}_mockuplu.mp4",  True),
        (f"{urun_id}_{safe_store}_mockupsuz.mp4", False),
    ]:
        out_path = os.path.join(klasor, vname)
        if os.path.exists(out_path):
            os.remove(out_path)
            print(f"  [Video] Eski dosya silindi, yeniden üretilecek: {vname}")
        label = "mockuplu" if include_mockup else "mockupsuz"
        print(f"  [Video] Oluşturuluyor ({label})...")
        try:
            _gen_video(
                mockup_path=mockup_path,
                product_image_paths=product_images,
                output_path=out_path,
                include_mockup=include_mockup,
                max_product_images=7,
                resolution=(1080, 1080),
                fps=30,
                total_seconds=10,
                intro_image_path=str(intro_logo) if intro_logo and intro_logo.exists() else None,
                intro_seconds=1.0,
            )
            print(f"  [Video] ✓ {vname}")
        except Exception as e:
            print(f"  [Video] ✗ Hata ({label}): {e}")


def _dosyalari_adlandir(dosyalar: list, urun: dict) -> list:
    """
    İndirilen dosyaları VDS'te yerel olarak tag'lara göre yeniden adlandırır.
    pCloud'daki dosyalara kesinlikle dokunulmaz — sadece VDS'teki geçici kopyalar.

    Kural:
      Ana resim (01): [ana_resim_tag]_01.jpg   ← uzun kuyruklu SEO
      Diğerleri:      [tag1]_02.jpg, [tag2]_03.jpg, ...
    """
    def _temizle(s: str) -> str:
        s = (s or "").lower().strip()
        s = _re.sub(r"[^\w\s-]", "", s)
        s = _re.sub(r"[\s_]+", "-", s)
        return s.strip("-") or "rug"

    ana_tag = _temizle(urun.get("ana_resim_tag") or "rug")
    taglar  = [_temizle(urun.get(f"tag{i}") or "") for i in range(1, 14)]

    foto_dosyalar = sorted(
        [Path(d) for d in dosyalar if Path(d).suffix.lower() in (".jpg", ".jpeg", ".png")],
        key=lambda p: (0 if _mockup_mu(p.name) else 1, -_mockup_skoru(p.name), p.name.lower())
    )

    yeni_dosyalar = []
    for idx, dosya in enumerate(foto_dosyalar):
        uzanti  = dosya.suffix.lower()
        num     = f"{idx + 1:02d}"
        if idx == 0 and _mockup_mu(dosya.name):
            yeni_ad = f"{ana_tag}_mockup_{num}{uzanti}"
        elif idx == 0:
            yeni_ad = f"{ana_tag}_{num}{uzanti}"
        else:
            tag     = taglar[idx - 1] if (idx - 1) < len(taglar) else "rug-photo"
            yeni_ad = f"{tag}_{num}{uzanti}"

        yeni_yol = dosya.parent / yeni_ad
        if yeni_yol.exists():
            yeni_yol.unlink()
        dosya.rename(yeni_yol)
        yeni_dosyalar.append(str(yeni_yol))
        print(f"  ✎  {dosya.name}  →  {yeni_ad}")

    return yeni_dosyalar


async def isle_bir_urun(urun: dict, sk: SheetsKatmani) -> bool:
    urun_id     = str(urun["urun_id"])
    klasor_yolu = urun["pcloud_klasor_yolu"]

    print(f"\n{'='*55}")
    print(f"  [{sk.store_id}] ÜRÜN: {urun_id}  |  {datetime.now().strftime('%H:%M:%S')}")
    print(f"{'='*55}")

    # ── ADIM 1: pCloud'dan indir ─────────────────────────────────────────────
    print(f"\n[1/4] pCloud'dan indiriliyor...")
    sk.status_guncelle(urun_id, "downloading")

    klasor_id = urun.get("pcloud_klasor_id") or urun.get("pcloud_klasor_id ")
    sonuc = await pcloud_klasor_indir(
        klasor_yolu, urun_id,
        klasor_id=int(klasor_id) if klasor_id else None
    )

    if not sonuc["basarili"]:
        hata = f"pCloud indirme hatası: {sonuc['hata']}"
        print(f"  ✗ {hata}")
        sk.status_guncelle(urun_id, "error", hata=hata)
        return False

    dosyalar = sonuc["dosyalar"]
    print(f"  ✓ {len(dosyalar)} dosya indirildi → {sonuc['temp_klasor']}")

    # ── ADIM 2: Videolar üret ────────────────────────────────────────────────
    print(f"\n[2/4] Videolar üretiliyor...")
    mockup_yolu = _mockup_yolunu_bul(dosyalar)
    _video_uret(sonuc["temp_klasor"], sk.store_id, urun_id, dosyalar, mockup_path=mockup_yolu)

    # ── ADIM 3: Dosyaları adlandır ───────────────────────────────────────────
    print(f"\n[3/4] Dosyalar yeniden adlandırılıyor...")
    dosyalar = _dosyalari_adlandir(dosyalar, urun)
    print(f"  ✓ {len(dosyalar)} dosya adlandırıldı")

    # ── ADIM 4: Sheets güncelle ──────────────────────────────────────────────
    print(f"\n[4/4] Sheets güncelleniyor...")
    sk.status_guncelle(urun_id, "downloaded")
    print(f"  ✓ Status: downloaded")
    print(f"\n  📁 Klasör: {sonuc['temp_klasor']}")
    print(f"  → Etsy'ye manuel veya API ile yüklenmeyi bekliyor.")

    return True


def _config_yukle():
    """Sheet'teki config sekmesinden env değişkenlerini yükler."""
    try:
        cfg = config_oku()
        for key, val in cfg.items():
            if val:
                os.environ[key] = val
        if cfg.get("PCLOUD_TOKEN"):
            print(f"[Config] ✓ PCLOUD_TOKEN Sheet'ten yüklendi")
        print(f"[Config] ✓ {len(cfg)} değişken yüklendi")
    except Exception as e:
        print(f"[Config] ⚠ Sheet'ten config okunamadı: {e} — env değişkenleri kullanılıyor")


def _islenecek_magazalar() -> list:
    """
    STORE_ID env varsa sadece o mağazayı döner (tek VDS = tek mağaza).
    STORE_ID yoksa stores.json'daki tüm aktif mağazaları döner (tek VDS = çok mağaza).
    """
    from shared.store_manager import get_store
    store_id = os.environ.get("STORE_ID", "").strip()
    if store_id:
        try:
            return [get_store(store_id)]
        except ValueError as e:
            print(f"[Config] ✗ STORE_ID geçersiz: {e}")
            return []
    return aktif_magazalar()


def _tek_sefer_modu() -> bool:
    return "--once" in sys.argv[1:] or os.environ.get("RUN_ONCE", "").strip() == "1"


async def ana_dongu():
    print("\n" + "="*55)
    print("  İNDİRME OTOMASYON BAŞLADI")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("="*55)

    tek_sefer = _tek_sefer_modu()
    _config_yukle()
    TEMP_DIR.mkdir(parents=True, exist_ok=True)

    magazalar = _islenecek_magazalar()
    if not magazalar:
        print("✗ İşlenecek mağaza yok. STORE_ID veya stores.json active=true kontrol edin.")
        return

    print(f"\n  İşlenecek mağazalar: {[m['store_id'] for m in magazalar]}")
    if tek_sefer:
        print("  Mod: tek sefer calis, mevcut ready urunleri bitir ve cik")

    while True:
        herhangi_bir_is = False

        for store in magazalar:
            store_id = store["store_id"]
            try:
                sk = SheetsKatmani(store_id)
                ready = sk.ready_urunleri_al()
            except Exception as e:
                print(f"[{store_id}] ⚠ Bağlantı hatası: {e}")
                continue

            if not ready:
                print(f"[{store_id}] Hazır ürün yok.")
                continue

            herhangi_bir_is = True
            urun = ready[0]
            basarili = await isle_bir_urun(urun, sk)

            if basarili and len(ready) > 1:
                bekleme = random.randint(ISLEMLER_ARASI_MIN, ISLEMLER_ARASI_MAX)
                print(f"\n⏳ Sonraki ürün için {bekleme} sn bekleniyor...")
                await asyncio.sleep(bekleme)

        if not herhangi_bir_is:
            if tek_sefer:
                print(f"\n[{datetime.now().strftime('%H:%M')}] Hazır ürün kalmadı. Program kapanıyor...")
                return
            etiket = magazalar[0]["store_id"] if len(magazalar) == 1 else "Tüm mağazalar"
            print(f"\n[{datetime.now().strftime('%H:%M')}] {etiket}: hazır ürün yok. 5 dk bekleniyor...")
            await asyncio.sleep(5 * 60)


if __name__ == "__main__":
    asyncio.run(ana_dongu())
