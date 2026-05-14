"""
Store sheet'ini DB'deki store-status kayitlarindan sifirdan kurar.

Davranis:
  - Secilen magazanin sheet'inde baslik disindaki tum urun satirlarini siler
  - Supabase product_store_status kayitlarini okur
  - Products tablosundaki final product_code'lara gore yeniden yazar
  - Tum yazilan satirlari green yapar

Kullanim:
  python3 vds/rebuild_store_sheet_from_db.py BohoRugHouse
"""

from __future__ import annotations

import argparse
import json
import os
import sys
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


def _clean(value) -> str:
    return str(value or "").strip()


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Store sheet'ini DB'den sifirdan kur")
    parser.add_argument("store_id", help="Stores.json icindeki store_id")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    _load_env()
    args = parse_args(argv)

    from shared.product_catalog import ProductCatalog, StoreCatalog
    from shared.sheets import SheetsKatmani, _tum_satirlar_al, _yeniden_dene

    products = ProductCatalog().list_products()
    product_map = {
        _clean(item.get("product_code")): dict(item)
        for item in products
        if _clean(item.get("product_code"))
    }
    store_rows = StoreCatalog().list_by_store(args.store_id)
    final_codes = sorted(
        {
            _clean(row.get("product_code"))
            for row in store_rows
            if _clean(row.get("product_code"))
        },
        key=str.lower,
    )

    kayitlar = []
    for code in final_codes:
        product = product_map.get(code, {})
        kayitlar.append(
            {
                "urun_id": code,
                "baslik": _clean(product.get("note")),
                "aciklama": "",
                "taglar_virgul": "",
            }
        )

    sk = SheetsKatmani(args.store_id)
    sk.sheet_hazirla()
    ws = sk._baglanti()

    # Baslik disindaki tum mevcut urun satirlarini temizle.
    mevcut = _tum_satirlar_al(ws)
    mevcut_kodlar = []
    for row in mevcut:
        code = _clean(row.get("urun_id") or row.get("urun_id_2"))
        if code:
            mevcut_kodlar.append(code)
    if mevcut_kodlar:
        sk.satirlari_sil(mevcut_kodlar)
        sk._satir_haritasini_gecersiz_kil()

    # Eski yesilleri de topluca temizle.
    renkler = sk.urun_renk_durumlari_al()
    yesiller = [_clean(code) for code, renk in renkler.items() if _clean(renk) == "green"]
    if yesiller:
        sk.urun_renklerini_temizle(yesiller)

    sonuc = sk.etsy_csv_kayitlarini_isle(kayitlar, renk="green", durum="done")
    son_satirlar = _tum_satirlar_al(ws)
    payload = {
        "store_id": args.store_id,
        "db_codes": len(final_codes),
        "sheet_rows_after": len(son_satirlar),
        "sheet_written": sonuc["toplam"],
        "sheet_added": sonuc["eklenen"],
        "sheet_cells_updated": sonuc["guncellenen"],
        "sheet_green_updated": sonuc["renk_guncellenen"],
        "sheet_not_found": len(sonuc["bulunamayan"]),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
