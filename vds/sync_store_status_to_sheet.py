"""
Supabase product/store-status verisini Google Sheet ile senkronlar.

Kullanim:
  python3 vds/sync_store_status_to_sheet.py BohoRugHouse

Varsayilan davranis:
  - store_status icindeki urunleri okur
  - products tablosunda status=sold olanlari disarida birakir
  - sheet'e master product_code ile yazar/gunceller
  - ilgili satirlari green yapar
  - sheet'te green olup canli listede olmayan kayitlarin green'ini temizler
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
    parser = argparse.ArgumentParser(description="Store-status -> Google Sheet green sync")
    parser.add_argument("store_id", help="Stores.json icindeki store_id")
    parser.add_argument("--include-sold", action="store_true", help="sold urunleri de green sete dahil et")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    _load_env()
    args = parse_args(argv)

    from shared.product_catalog import ProductCatalog, StoreCatalog
    from shared.sheets import SheetsKatmani

    products = ProductCatalog().list_products()
    product_map = {_clean(item.get("product_code")): dict(item) for item in products if _clean(item.get("product_code"))}
    store_rows = StoreCatalog().list_by_store(args.store_id)

    kayitlar = []
    active_codes = set()
    for row in store_rows:
        code = _clean(row.get("product_code"))
        if not code:
            continue
        product = product_map.get(code, {})
        status = _clean(product.get("status")).lower()
        if status == "sold" and not args.include_sold:
            continue
        active_codes.add(code)
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
    onceki_renkler = sk.urun_renk_durumlari_al()
    mevcut_green = {
        _clean(urun_id)
        for urun_id, renk in onceki_renkler.items()
        if _clean(renk) == "green"
    }

    sonuc = sk.etsy_csv_kayitlarini_isle(kayitlar, renk="green", durum="done")
    temizlenecek = sorted(mevcut_green - active_codes)
    temiz_sonuc = sk.urun_renklerini_temizle(temizlenecek) if temizlenecek else {"guncellenen": 0}

    payload = {
        "store_id": args.store_id,
        "include_sold": args.include_sold,
        "active_codes": len(active_codes),
        "sheet_written": sonuc["toplam"],
        "sheet_added": sonuc["eklenen"],
        "sheet_cells_updated": sonuc["guncellenen"],
        "sheet_green_updated": sonuc["renk_guncellenen"],
        "sheet_green_cleared": temiz_sonuc["guncellenen"],
        "sheet_not_found": len(sonuc["bulunamayan"]),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
