"""
Etsy listing export CSV'sini ilgili magazanin sheet sekmesine ekler/gunceller.

Bu arac, eski yukleme kayitlarini sheet'te yesil isaretli "Etsy'de yuklu"
olarak kaydetmek icin kullanilir.

Yazilan alanlar:
  - A / urun_id
  - G / baslik
  - I / taglar_virgul
  - N / urun_id (kopya)
  - P / status
  - T / islem_tarihi

Diger alanlar yeni satirlarda bos birakilir. Mevcut satirlarda sadece yukaridaki
alanlar guncellenir. Son olarak A sutunu repo icindeki standart yesil ile boyanir
ve product_store_status tablosuna upsert yapilir.
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import sys
from datetime import datetime
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


sys.path.insert(0, str(_repo_root()))


def _load_env() -> None:
    env_path = _repo_root() / "streamlit" / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line or line.startswith("export "):
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def _store_aliases(store_id: str) -> list[str]:
    raw = re.sub(r"[^a-z]", "", str(store_id or "").lower())
    aliases = {raw}
    for suffix in ("rugs", "rug", "shop", "house", "llc", "turkey"):
        if raw.endswith(suffix) and len(raw) > len(suffix):
            aliases.add(raw[: -len(suffix)])
    return sorted(a for a in aliases if a)


_STORE_PREFIX_RULES = {
    "RugsShopTurkey": ("RST",),
    "WovenLoomRugs": ("WLR", "WLB"),
    "LoomixRugs": ("LMX",),
    "LoopRug": ("LR", "LP"),
}


def _snapshot_sku_coz(raw_sku: str, store_id: str) -> tuple[str, str]:
    """
    Etsy snapshot importu icin ham SKU'dan:
      - canonical urun_id
      - sheet B kolonuna yazilabilecek ham SKU
    bilgilerini uretir.
    """
    sku = str(raw_sku or "").strip()
    if not sku:
        return "", ""

    compact = re.sub(r"\s+", " ", sku).strip()

    for prefix in _STORE_PREFIX_RULES.get(store_id, ()):
        match = re.match(rf"^{prefix}\s*(.*)$", compact, re.I)
        if match:
            suffix = str(match.group(1) or "").strip()
            if suffix.startswith("-"):
                suffix = suffix[1:].strip()
            if suffix:
                return suffix, compact

    return _urun_id_normallestir(compact, store_id), ""


def _urun_id_normallestir(raw_sku: str, store_id: str) -> str:
    sku = str(raw_sku or "").strip()
    if not sku:
        return ""

    compact = re.sub(r"\s+", " ", sku).strip()
    lowered = compact.lower()

    for alias in _store_aliases(store_id):
        if lowered == alias:
            return ""
        if lowered.startswith(alias + " "):
            compact = compact[len(alias):].strip()
            lowered = compact.lower()
            break

    compact = re.sub(r"\s+", " ", compact).strip()

    # "00_2200", "00-2200" gibi anlamsiz lider sifir + ayrac bloklarini at
    compact = re.sub(r"^0+[_\-\s]+(?=\d)", "", compact).strip()

    alpha_num = re.match(r"^([A-Za-z]{1,5})\s*(\d+)\b", compact)
    if alpha_num:
        return f"{alpha_num.group(1)}{alpha_num.group(2)}"

    numeric = re.match(r"^(\d+)\b", compact)
    if numeric:
        return numeric.group(1)

    return compact.strip()


def _csv_kayitlari(csv_path: Path, store_id: str) -> list[dict]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        rows = csv.DictReader(f)
        kayitlar = []
        seen = set()
        for row in rows:
            urun_id, ham_sku = _snapshot_sku_coz(row.get("SKU") or "", store_id)
            if not urun_id or urun_id in seen:
                continue
            seen.add(urun_id)
            kayitlar.append({
                "urun_id": urun_id,
                "ham_sku": ham_sku,
                "baslik": str(row.get("TITLE") or "").strip(),
                "taglar_virgul": str(row.get("TAGS") or "").strip(),
            })
        return kayitlar


def _process_sheet_rows(store_id: str, kayitlar: list[dict]) -> dict:
    from shared.sheets import BASLIK_SATIRI, SheetsKatmani, _baslik_pozisyonlari, _basliklar_al, _kolon_no_from_positions, _yeniden_dene
    from gspread.utils import rowcol_to_a1

    sk = SheetsKatmani(store_id)
    sk.sheet_hazirla()
    ws = sk._baglanti()
    basliklar = _basliklar_al(ws)
    pozisyonlar = _baslik_pozisyonlari(ws)
    satir_map = sk._satir_haritasi_al(ws, force_refresh=True)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    def _bos_satir() -> list[str]:
        return [""] * max(len(basliklar), len(BASLIK_SATIRI))

    def _satira_yaz(satir: list[str], alan: str, deger: str, occurrence: int = 0) -> None:
        kolon = _kolon_no_from_positions(pozisyonlar, alan, occurrence=occurrence)
        if kolon:
            satir[kolon - 1] = deger

    guncelleme_batch = []
    yeni_satirlar = []
    islenen_urun_idler = []

    for kayit in kayitlar:
        urun_id = str(kayit.get("urun_id") or "").strip()
        if not urun_id:
            continue

        islenen_urun_idler.append(urun_id)
        satir_no = satir_map.get(urun_id)
        baslik = str(kayit.get("baslik") or "")
        taglar = str(kayit.get("taglar_virgul") or "")
        ham_sku = str(kayit.get("ham_sku") or "")

        if satir_no:
            for alan, deger, occurrence in [
                ("urun_id", urun_id, 0),
                ("urun_id", urun_id, 1),
                ("pcloud_klasor_yolu", ham_sku, 0),
                ("baslik", baslik, 0),
                ("taglar_virgul", taglar, 0),
                ("status", "done", 0),
                ("islem_tarihi", now_str, 0),
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
        _satira_yaz(satir, "pcloud_klasor_yolu", ham_sku)
        _satira_yaz(satir, "baslik", baslik)
        _satira_yaz(satir, "taglar_virgul", taglar)
        _satira_yaz(satir, "status", "done")
        _satira_yaz(satir, "islem_tarihi", now_str)
        yeni_satirlar.append(satir)

    if guncelleme_batch:
        _yeniden_dene("Snapshot alanlarini guncelleme", ws.batch_update, guncelleme_batch)

    eklenen = 0
    if yeni_satirlar:
        tum = _yeniden_dene("Snapshot yeni satirlar icin son indeks okuma", ws.get_all_values)
        baslangic_satiri = len(tum) + 1
        bitis_satiri = baslangic_satiri + len(yeni_satirlar) - 1
        sk._worksheet_kapasitesini_guvenceye_al(
            ws,
            hedef_satir=bitis_satiri,
            hedef_kolon=len(yeni_satirlar[0]) if yeni_satirlar else len(BASLIK_SATIRI),
        )
        _yeniden_dene("Snapshot yeni satirlari yazma", ws.update, yeni_satirlar, f"A{baslangic_satiri}")
        eklenen = len(yeni_satirlar)
        sk._satir_haritasini_gecersiz_kil()

    renk_sonuc = sk.urunleri_renklendir(islenen_urun_idler, "green")
    satir_map_son = sk._satir_haritasi_al(ws, force_refresh=True)
    sk._satir_yuksekliklerini_sabitle(
        [satir_map_son[uid] for uid in islenen_urun_idler if uid in satir_map_son],
        pixel_size=21,
    )

    return {
        "toplam": len(islenen_urun_idler),
        "eklenen": eklenen,
        "alan_guncellenen": len(guncelleme_batch),
        "green_yapilan": renk_sonuc["guncellenen"],
        "bulunamayan": renk_sonuc["bulunamayan"],
        "islem_tarihi": now_str,
    }


def _clear_missing_loaded_marks(store_id: str, aktif_urun_idler: set[str]) -> dict:
    from shared.sheets import SheetsKatmani, _baslik_pozisyonlari, _kolon_no_from_positions, _yeniden_dene
    from gspread.utils import rowcol_to_a1

    sk = SheetsKatmani(store_id)
    sk.sheet_hazirla()
    ws = sk._baglanti()
    renkler = sk.urun_renk_durumlari_al()
    yesil_olanlar = {
        str(urun_id).strip()
        for urun_id, renk in renkler.items()
        if str(renk).strip() == "green"
    }
    temizlenecek = sorted(yesil_olanlar - {str(x).strip() for x in aktif_urun_idler if str(x).strip()})
    temiz_sonuc = sk.urun_renklerini_temizle(temizlenecek)

    if temizlenecek:
        satir_map = sk._satir_haritasi_al(ws, force_refresh=True)
        pozisyonlar = _baslik_pozisyonlari(ws)
        batch = []
        for urun_id in temizlenecek:
            satir_no = satir_map.get(urun_id)
            if not satir_no:
                continue
            status_col = _kolon_no_from_positions(pozisyonlar, "status")
            if status_col:
                batch.append({"range": rowcol_to_a1(satir_no, status_col), "values": [[""]]})
        if batch:
            _yeniden_dene("Silinen yuklu durumlarini temizleme", ws.batch_update, batch)

    return {
        "sheet_green_onceki": len(yesil_olanlar),
        "sheet_green_temizlenen": temiz_sonuc["guncellenen"],
        "sheet_green_kalan": len(yesil_olanlar) - temiz_sonuc["guncellenen"],
        "sheet_green_fazlalar": temizlenecek,
    }


def _upsert_supabase(store_id: str, kayitlar: list[dict], islem_tarihi: str) -> int:
    from shared.product_catalog import ProductCatalog, StoreCatalog, _supabase_ready

    if not _supabase_ready():
        return 0

    product_rows = []
    rows = []
    for kayit in kayitlar:
        urun_id = str(kayit.get("urun_id") or "").strip()
        if not urun_id:
            continue
        product_rows.append({
            "product_code": urun_id,
            "status": "active",
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })
        rows.append({
            "product_code": urun_id,
            "store_id": store_id,
            "status": "done",
            "renk": "green",
            "islem_tarihi": islem_tarihi,
        })

    if not rows:
        return 0

    ProductCatalog().upsert_products(product_rows)
    StoreCatalog().upsert(rows)
    return len(rows)


def _delete_supabase_missing(store_id: str, aktif_urun_idler: set[str]) -> dict:
    from shared.product_catalog import SUPABASE_STORE_TABLE, _base_url, _headers, _supabase_ready
    import requests

    if not _supabase_ready():
        return {"supabase_onceki": 0, "supabase_silinen": 0, "supabase_fazlalar": []}

    url = f"{_base_url()}/rest/v1/{SUPABASE_STORE_TABLE}"
    r = requests.get(
        url,
        headers={**_headers(), "Accept": "application/json"},
        params={"select": "product_code,status,renk", "store_id": f"eq.{store_id}"},
        timeout=45,
    )
    if not r.ok:
        raise RuntimeError(f"store_status okunamadi: {r.status_code} {r.text}")

    rows = r.json() or []
    yuklu_kodlar = {
        str(row.get("product_code") or "").strip()
        for row in rows
        if str(row.get("product_code") or "").strip()
        and (
            str(row.get("renk") or "").strip() == "green"
            or str(row.get("status") or "").strip() == "done"
        )
    }
    aktifler = {str(x).strip() for x in aktif_urun_idler if str(x).strip()}
    silinecek = sorted(yuklu_kodlar - aktifler)
    silinen = 0

    for kod in silinecek:
        d = requests.delete(
            url,
            headers={**_headers(), "Prefer": "return=representation"},
            params={"store_id": f"eq.{store_id}", "product_code": f"eq.{kod}"},
            timeout=45,
        )
        if not d.ok:
            raise RuntimeError(f"store_status silme basarisiz: {d.status_code} {d.text}")
        try:
            silinen += len(d.json() or [])
        except Exception:
            silinen += 1

    return {
        "supabase_onceki": len(yuklu_kodlar),
        "supabase_silinen": silinen,
        "supabase_fazlalar": silinecek,
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Etsy export snapshot'unu sheet'e ve Supabase'e isler.")
    parser.add_argument("store_id", help="stores.json icindeki magaza ID'si")
    parser.add_argument("csv_path", help="Etsy listings export CSV yolu")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    _load_env()

    csv_path = Path(args.csv_path).expanduser().resolve()
    if not csv_path.exists():
        print(f"Hata: CSV bulunamadi: {csv_path}", file=sys.stderr)
        return 1

    kayitlar = _csv_kayitlari(csv_path, args.store_id)
    if not kayitlar:
        print("Hata: CSV icinde gecerli SKU bulunamadi.", file=sys.stderr)
        return 1

    sonuc = _process_sheet_rows(args.store_id, kayitlar)
    aktif_urun_idler = {str(k.get("urun_id") or "").strip() for k in kayitlar if str(k.get("urun_id") or "").strip()}
    temiz_sheet = _clear_missing_loaded_marks(args.store_id, aktif_urun_idler)
    supabase_rows = _upsert_supabase(args.store_id, kayitlar, sonuc["islem_tarihi"])
    temiz_supabase = _delete_supabase_missing(args.store_id, aktif_urun_idler)

    print(f"store_id={args.store_id}")
    print(f"csv_sku={sonuc['toplam']}")
    print(f"eklenen={sonuc['eklenen']}")
    print(f"alan_guncellenen={sonuc['alan_guncellenen']}")
    print(f"green_yapilan={sonuc['green_yapilan']}")
    print(f"sheet_green_temizlenen={temiz_sheet['sheet_green_temizlenen']}")
    print(f"supabase_upsert={supabase_rows}")
    print(f"supabase_silinen={temiz_supabase['supabase_silinen']}")
    print(f"islem_tarihi={sonuc['islem_tarihi']}")
    if sonuc["bulunamayan"]:
        print("bulunamayan_sku=" + ",".join(sorted(sonuc["bulunamayan"])))
    if temiz_sheet["sheet_green_fazlalar"]:
        print("sheet_fazla_sku=" + ",".join(temiz_sheet["sheet_green_fazlalar"]))
    if temiz_supabase["supabase_fazlalar"]:
        print("supabase_fazla_sku=" + ",".join(temiz_supabase["supabase_fazlalar"]))

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
