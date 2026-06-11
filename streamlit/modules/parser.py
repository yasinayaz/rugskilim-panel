"""
parser.py
Klasör adı ve dosya adından ürün bilgilerini çeker.

Örnek dosya adı: "4102-- 65x119 = 0,77 m2 2,1x3,9 ft.jpg"
Örnek klasör adı: "4102"
"""

import re
import os
from pathlib import Path


def _kod_cikart(metin: str) -> str:
    """Metinden baştaki ürün kodunu çıkarır. Örn: '4102 +' → '4102', 'd10 rst' → 'd10'"""
    m = re.match(r'^([A-Za-zİĞŞÜÖÇıiğşüöç]{0,3}\d+)', metin.strip())
    return m.group(1) if m else metin.strip()


def parse_urun_bilgisi(klasor_adi: str, dosyalar: list[str]) -> dict:
    """
    Klasör adı ve içindeki dosya listesinden ürün bilgilerini çıkarır.

    Returns:
        dict: {
            urun_id, boyut_cm, genislik_cm, uzunluk_cm,
            metrekare, boyut_ft, genislik_ft, uzunluk_ft,
            fiyat_usd, ana_fotograf, fotograf_listesi
        }
    """
    # Tepe fotoğrafından (m2 içeren bilgi dosyası) kodu al, yoksa klasör adından temizle
    urun_id = None
    for dosya in dosyalar:
        if 'm2' in dosya.lower():
            urun_id = _kod_cikart(Path(dosya).stem)
            break
    if not urun_id:
        urun_id = _kod_cikart(klasor_adi)
    
    # Bilgi dosyasını bul (klasör adıyla başlayan JPG)
    # Örn: "C 280--89X338 = 3,01 M2 2,9X11,1 FT.jpg"
    bilgi_dosyasi = None
    fotograf_listesi = []

    for dosya in dosyalar:
        ad = Path(dosya).stem  # uzantısız ad
        # Bilgi dosyası: urun_id ile başlar ve içinde "m2" geçer
        if ad.startswith(urun_id) and 'm2' in dosya.lower():
            bilgi_dosyasi = dosya
        else:
            fotograf_listesi.append(dosya)

    if not bilgi_dosyasi:
        # Fallback 1: klasöründe herhangi bir "m2" içeren dosya var mı?
        for dosya in dosyalar:
            if 'm2' in dosya.lower():
                bilgi_dosyasi = dosya
                if dosya in fotograf_listesi:
                    fotograf_listesi.remove(dosya)
                break
    
    # Bilgi dosyası yoksa fotolar içinden çıkar
    if bilgi_dosyasi and bilgi_dosyasi in fotograf_listesi:
        fotograf_listesi.remove(bilgi_dosyasi)

    # Boyutları parse et — önce bilgi dosyası, yoksa klasör adından dene
    kaynak = bilgi_dosyasi or ""
    boyut_cm, genislik_cm, uzunluk_cm = _parse_cm(kaynak)
    if not boyut_cm:
        boyut_cm, genislik_cm, uzunluk_cm = _parse_cm(klasor_adi)
    boyut_ft, genislik_ft, uzunluk_ft = _parse_ft(kaynak)
    if not boyut_ft:
        boyut_ft, genislik_ft, uzunluk_ft = _parse_ft(klasor_adi)
    metrekare = _parse_m2(kaynak)
    if not metrekare:
        metrekare = _parse_m2(klasor_adi)
    
    # Fallback: cm'den m2 hesapla
    if not metrekare and genislik_cm and uzunluk_cm:
        metrekare = round((genislik_cm * uzunluk_cm) / 10000, 2)
    
    # Fiyat: m2 x 300 USD
    fiyat_usd = round(metrekare * 300) if metrekare else None

    # Fotoğrafları sırala (1C4A... gibi kamera adlarına göre)
    fotograf_listesi = sorted(fotograf_listesi)
    
    # Etsy max 10 fotoğraf
    etsy_fotograflar = fotograf_listesi[:10]

    return {
        "urun_id": urun_id,
        "boyut_cm": boyut_cm,           # "65x119"
        "genislik_cm": genislik_cm,     # 65
        "uzunluk_cm": uzunluk_cm,       # 119
        "boyut_ft": boyut_ft,           # "2.1x3.9"
        "genislik_ft": genislik_ft,     # 2.1
        "uzunluk_ft": uzunluk_ft,       # 3.9
        "metrekare": metrekare,         # 0.77
        "fiyat_usd": fiyat_usd,         # 77
        "bilgi_dosyasi": bilgi_dosyasi,
        "fotograf_listesi": etsy_fotograflar,
        "fotograf_sayisi": len(etsy_fotograflar),
    }


def _parse_cm(dosya_adi: str) -> tuple:
    """
    "4102-- 65x119 = 0,77 m2 2,1x3,9 ft.jpg" → ("65x119", 65, 119)
    """
    # Pattern: rakam x rakam (cm)
    # Dosya adında "-- 65x119" şeklinde geçiyor
    pattern = r'(\d{2,3})[xX×](\d{2,3})'
    match = re.search(pattern, dosya_adi)
    if match:
        g = int(match.group(1))
        u = int(match.group(2))
        return f"{g}x{u}", g, u
    return None, None, None


def _parse_ft(dosya_adi: str) -> tuple:
    """
    "4102-- 65x119 = 0,77 m2 2,1x3,9 ft.jpg" → ("2.1x3.9", 2.1, 3.9)
    """
    # Pattern: ondalıklı sayı x ondalıklı sayı ft
    pattern = r'(\d+[.,]\d+)[xX×](\d+[.,]\d+)\s*ft'
    match = re.search(pattern, dosya_adi, re.IGNORECASE)
    if match:
        g = float(match.group(1).replace(',', '.'))
        u = float(match.group(2).replace(',', '.'))
        return f"{g}x{u}", g, u
    
    # Fallback: ft yoksa cm'den çevir
    return None, None, None


def _parse_m2(dosya_adi: str) -> float:
    """
    "4102-- 65x119 = 0,77 m2 2,1x3,9 ft.jpg" → 0.77
    """
    # "= 0,77 m2 ..." veya "= 11,29 9,7x..." (m2 yazısı olmasa da = sonrası alan değeri)
    pattern = r'=\s*(\d+[.,]\d+)(?:\s*m2)?(?=\s|\.|$)'
    match = re.search(pattern, dosya_adi, re.IGNORECASE)
    if match:
        return float(match.group(1).replace(',', '.'))
    return None


def cm_to_ft(cm: int) -> str:
    """65 cm → "2'1\"""  (feet'inches formatı, opsiyonel)"""
    total_inches = cm / 2.54
    feet = int(total_inches // 12)
    inches = int(round(total_inches % 12))
    return f"{feet}'{inches}\""


# ── Test ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    test_dosyalar = [
        "1C4A9318.jpg",
        "1C4A9319.jpg",
        "1C4A9320.jpg",
        "1C4A9321.jpg",
        "1C4A9322.jpg",
        "1C4A9323.jpg",
        "1C4A9324.jpg",
        "1C4A9325.jpg",
        "4102-- 65x119 = 0,77 m2 2,1x3,9 ft.jpg",
    ]
    
    sonuc = parse_urun_bilgisi("4102", test_dosyalar)
    
    print("=" * 50)
    print("PARSE SONUCU")
    print("=" * 50)
    for k, v in sonuc.items():
        print(f"  {k:20s}: {v}")
    print()
    print(f"  Title için    : {sonuc['boyut_ft']} ft rug")
    print(f"  Tag için      : {sonuc['boyut_ft'].replace('.', '')} ft" if sonuc['boyut_ft'] else "  ft yok")
    print(f"  Description   : {sonuc['genislik_cm']}x{sonuc['uzunluk_cm']} cm / {sonuc['boyut_ft']} ft")
    print(f"  Fiyat         : ${sonuc['fiyat_usd']}")
