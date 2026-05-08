"""
migrate_kolonlar.py — TEK SEFERLİK kolon yeniden düzenleme scripti.

Çalıştırmadan önce:
  1. GOOGLE_SHEET_ID ve GOOGLE_CREDS_JSON env var'larını set et
  2. Script önce CSV yedek alır, sonra sheet'i yeniden yazar
  3. Yanlış giderse migration_yedek_TARIH.csv ile geri yüklenebilir

Kullanım:
  python migrate_kolonlar.py
"""

import os
import csv
import sys
import time
from datetime import datetime
from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials

SHEET_ID         = os.environ.get("GOOGLE_SHEET_ID", "")
CREDENTIALS_JSON = os.environ.get("GOOGLE_CREDS_JSON", "credentials.json")

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# ── Yeni başlık satırı (35 kolon) ─────────────────────────────────────────────
YENI_BASLIK = [
    "urun_id",           # 1
    "pcloud_klasor_yolu",# 2
    "boyut_cm",          # 3
    "boyut_ft",          # 4
    "metrekare",         # 5
    "fotograf_sayisi",   # 6  (eskiden 7)
    "baslik",            # 7  (eskiden 8)
    "aciklama",          # 8  (eskiden 9)
    "taglar_virgul",     # 9  (eskiden 10)
    "renk1",             # 10 (eskiden 24)
    "renk2",             # 11 (eskiden 25)
    "pattern_etsy",      # 12 (eskiden 34)
    "fiyat_usd",         # 13 (eskiden 6)
    "urun_id",           # 14 (kopya — görsel referans)
    "shop_section",      # 15 (eskiden 37)
    "status",            # 16 (eskiden 28)
    "tip",               # 17 (eskiden 35)
    "etsy_draft_url",    # 18 (eskiden 29)
    "hata_mesaji",       # 19 (eskiden 30)
    "islem_tarihi",      # 20 (eskiden 31)
    "pcloud_klasor_id",  # 21 (eskiden 32)
    "ana_resim_tag",     # 22 (eskiden 33)
    "tag1",              # 23 (eskiden 11)
    "tag2",              # 24
    "tag3",              # 25
    "tag4",              # 26
    "tag5",              # 27
    "tag6",              # 28
    "tag7",              # 29
    "tag8",              # 30
    "tag9",              # 31
    "tag10",             # 32
    "tag11",             # 33
    "tag12",             # 34
    "tag13",             # 35
]


def _donustur(eski_satir: list) -> list:
    """Eski 37 kolonlu satırı yeni 35 kolonlu sıraya çevirir."""
    def _al(idx: int) -> str:
        try:
            return eski_satir[idx]
        except IndexError:
            return ""

    return [
        _al(0),   # urun_id
        _al(1),   # pcloud_klasor_yolu
        _al(2),   # boyut_cm
        _al(3),   # boyut_ft
        _al(4),   # metrekare
        _al(6),   # fotograf_sayisi  (eskiden 7. kolon = index 6)
        _al(7),   # baslik
        _al(8),   # aciklama
        _al(9),   # taglar_virgul
        _al(23),  # renk1            (eskiden 24. kolon = index 23)
        _al(24),  # renk2
        _al(33),  # pattern_etsy     (eskiden 34. kolon = index 33)
        _al(5),   # fiyat_usd        (eskiden 6. kolon = index 5)
        _al(0),   # urun_id kopya
        _al(36),  # shop_section     (eskiden 37. kolon = index 36)
        _al(27),  # status           (eskiden 28. kolon = index 27)
        _al(34),  # tip              (eskiden 35. kolon = index 34)
        _al(28),  # etsy_draft_url
        _al(29),  # hata_mesaji
        _al(30),  # islem_tarihi
        _al(31),  # pcloud_klasor_id
        _al(32),  # ana_resim_tag
        _al(10),  # tag1             (eskiden 11. kolon = index 10)
        _al(11),  # tag2
        _al(12),  # tag3
        _al(13),  # tag4
        _al(14),  # tag5
        _al(15),  # tag6
        _al(16),  # tag7
        _al(17),  # tag8
        _al(18),  # tag9
        _al(19),  # tag10
        _al(20),  # tag11
        _al(21),  # tag12
        _al(22),  # tag13
    ]


def main():
    if not SHEET_ID:
        print("HATA: GOOGLE_SHEET_ID env var eksik.")
        sys.exit(1)

    creds = Credentials.from_service_account_file(CREDENTIALS_JSON, scopes=SCOPES)
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_key(SHEET_ID)
    ws = spreadsheet.sheet1

    print("Sheet okunuyor...")
    tum_veri = ws.get_all_values()

    if not tum_veri:
        print("Sheet boş, çıkılıyor.")
        return

    baslik = tum_veri[0]
    veri_satirlari = tum_veri[1:]
    print(f"  {len(veri_satirlari)} veri satırı bulundu.")
    print(f"  Mevcut kolon sayısı: {len(baslik)}")

    # ── 1. CSV Yedek ──────────────────────────────────────────────────────────
    tarih = datetime.now().strftime("%Y%m%d_%H%M%S")
    yedek_dosya = Path(__file__).parent / f"migration_yedek_{tarih}.csv"
    with open(yedek_dosya, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerows(tum_veri)
    print(f"\n✓ Yedek alındı: {yedek_dosya}")
    print("  Bir şey yanlış giderse bu dosyayla geri yükleyebilirsin.")

    # ── 2. Onay ───────────────────────────────────────────────────────────────
    print(f"\nSheet şu an {len(baslik)} kolon → {len(YENI_BASLIK)} kolona dönüştürülecek.")
    print("Kaldırılan kolonlar: stil, koken, home_style")
    print("Eklenen kolon: urun_id kopya (14. sıra)")
    onay = input("\nDevam edilsin mi? (evet / hayır): ").strip().lower()
    if onay != "evet":
        print("İptal edildi.")
        return

    # ── 3. Dönüşüm ────────────────────────────────────────────────────────────
    print("\nSatırlar dönüştürülüyor...")
    yeni_satirlar = [_donustur(satir) for satir in veri_satirlari]

    # ── 4. Sheet temizle + yeni veriyi yaz ────────────────────────────────────
    print("Sheet temizleniyor...")
    ws.clear()
    time.sleep(1)  # API rate limit

    print("Başlık satırı yazılıyor...")
    ws.update([YENI_BASLIK], "A1")
    time.sleep(0.5)

    if yeni_satirlar:
        print(f"{len(yeni_satirlar)} satır yazılıyor...")
        # Büyük sheetlerde 500'er satırda yaz
        PARCA = 500
        for i in range(0, len(yeni_satirlar), PARCA):
            parca = yeni_satirlar[i:i + PARCA]
            baslangic = i + 2  # 1. satır başlık
            ws.update(parca, f"A{baslangic}")
            time.sleep(0.5)
            print(f"  {min(i + PARCA, len(yeni_satirlar))}/{len(yeni_satirlar)} satır yazıldı")

    print(f"\n✓ Migration tamamlandı!")
    print(f"  Toplam: {len(yeni_satirlar)} satır, {len(YENI_BASLIK)} kolon")
    print(f"  Yedek: {yedek_dosya}")


if __name__ == "__main__":
    main()
