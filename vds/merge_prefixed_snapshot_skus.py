"""
Belirli magazalarda historical Etsy snapshot importundan gelen prefix'li SKU'lari
gercek canonical urun kodlarina tasir.

Yapilanlar:
  - Sheet A/N kolonlarini canonical urun koduna cevirir
  - Sheet B kolonuna Etsy'deki ham SKU'yu yazar
  - product_store_status kaydini wrong -> canonical olarak tasir
  - Artik store_status'i kalmayan wrong product kayitlarini products tablosundan siler
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import requests


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


_STORE_CONFIG = {
    "RugsShopTurkey": {
        "csv_path": "/Users/yasinayaz/Downloads/Rugsshopturkey1.csv",
        "skip_canonical": set(),
    },
    "WovenLoomRugs": {
        "csv_path": "/Users/yasinayaz/Downloads/Wovenloomrugs1.csv",
        "skip_canonical": {"694"},
    },
    "LoomixRugs": {
        "csv_path": "/Users/yasinayaz/Downloads/Loomix.csv",
        "skip_canonical": {"682"},
    },
    "LoopRug": {
        "csv_path": "/Users/yasinayaz/Downloads/Looprug1.csv",
        "skip_canonical": {"567", "82", "857", "892", "896", "955"},
    },
}


def _mappings_for_store(store_id: str) -> dict[str, dict]:
    from vds.import_etsy_listing_snapshot import _snapshot_sku_coz

    config = _STORE_CONFIG[store_id]
    rows = csv.DictReader(Path(config["csv_path"]).open("r", encoding="utf-8-sig", newline=""))
    mapping = {}
    for row in rows:
        raw_sku = str(row.get("SKU") or "").strip()
        canonical, ham_sku = _snapshot_sku_coz(raw_sku, store_id)
        compact_raw = re.sub(r"\s+", "", raw_sku)
        if not canonical or not ham_sku or canonical in config["skip_canonical"]:
            continue
        mapping[compact_raw] = {
            "wrong_code": compact_raw,
            "canonical_code": canonical,
            "ham_sku": ham_sku,
        }

    target_counts = Counter(item["canonical_code"] for item in mapping.values())
    duplicates = [code for code, count in target_counts.items() if count > 1]
    if duplicates:
        raise RuntimeError(f"{store_id} icin tek canonical koda birden fazla wrong SKU eslesiyor: {duplicates[:20]}")

    return mapping


def _update_sheet(store_id: str, mapping: dict[str, dict]) -> dict:
    from shared.sheets import SheetsKatmani, _baslik_pozisyonlari, _kolon_no_from_positions, _yeniden_dene
    from gspread.utils import rowcol_to_a1

    sk = SheetsKatmani(store_id)
    sk.sheet_hazirla()
    ws = sk._baglanti()
    satir_map = sk._satir_haritasi_al(ws, force_refresh=True)
    pozisyonlar = _baslik_pozisyonlari(ws)

    batch = []
    updated = 0
    missing_rows = []

    for wrong_code, item in sorted(mapping.items()):
        satir_no = satir_map.get(wrong_code)
        if not satir_no:
            missing_rows.append(wrong_code)
            continue
        for alan, deger, occurrence in [
            ("urun_id", item["canonical_code"], 0),
            ("pcloud_klasor_yolu", item["ham_sku"], 0),
            ("urun_id", item["canonical_code"], 1),
        ]:
            kolon = _kolon_no_from_positions(pozisyonlar, alan, occurrence=occurrence)
            if kolon:
                batch.append({"range": rowcol_to_a1(satir_no, kolon), "values": [[deger]]})
        updated += 1

    if batch:
        _yeniden_dene("Prefixli SKU sheet merge guncelleme", ws.batch_update, batch)
        sk._satir_haritasini_gecersiz_kil()

    return {"sheet_updated": updated, "sheet_missing": missing_rows}


def _store_status_rows_for_store(store_id: str) -> list[dict]:
    from shared.product_catalog import StoreCatalog

    return StoreCatalog().list_by_store(store_id)


def _move_store_status(store_id: str, mapping: dict[str, dict]) -> dict:
    from shared.product_catalog import StoreCatalog

    rows = _store_status_rows_for_store(store_id)
    row_map = {str(row.get("product_code") or "").strip(): row for row in rows}

    upsert_rows = []
    delete_pairs = []
    moved = 0
    missing = []

    for wrong_code, item in sorted(mapping.items()):
        current = row_map.get(wrong_code)
        if not current:
            missing.append(wrong_code)
            continue
        new_row = dict(current)
        new_row["product_code"] = item["canonical_code"]
        upsert_rows.append(new_row)
        delete_pairs.append((store_id, wrong_code))
        moved += 1

    if upsert_rows:
        StoreCatalog().upsert(upsert_rows)

    if delete_pairs:
        from shared.product_catalog import SUPABASE_STORE_TABLE, _base_url, _headers

        url = f"{_base_url()}/rest/v1/{SUPABASE_STORE_TABLE}"
        for sid, wrong_code in delete_pairs:
            resp = requests.delete(
                url,
                headers={**_headers(), "Prefer": "return=representation"},
                params={"store_id": f"eq.{sid}", "product_code": f"eq.{wrong_code}"},
                timeout=45,
            )
            if not resp.ok:
                raise RuntimeError(f"store_status silme basarisiz: {sid} {wrong_code} -> {resp.status_code} {resp.text}")

    return {"status_moved": moved, "status_missing": missing}


def _all_store_rows_paginated() -> list[dict]:
    from shared.product_catalog import SUPABASE_STORE_TABLE, _base_url, _headers

    rows = []
    offset = 0
    page_size = 1000
    url = f"{_base_url()}/rest/v1/{SUPABASE_STORE_TABLE}"

    while True:
        resp = requests.get(
            url,
            headers={**_headers(), "Accept": "application/json", "Range-Unit": "items", "Range": f"{offset}-{offset + page_size - 1}"},
            params={"select": "product_code,store_id,status,renk"},
            timeout=45,
        )
        if not resp.ok:
            raise RuntimeError(f"store_status sayfalama okunamadi: {resp.status_code} {resp.text}")
        page = resp.json() or []
        rows.extend(page)
        if len(page) < page_size:
            break
        offset += page_size
    return rows


def _delete_orphan_wrong_products(all_mappings: dict[str, dict[str, dict]]) -> dict:
    from shared.product_catalog import ProductCatalog

    all_rows = _all_store_rows_paginated()
    by_code = defaultdict(list)
    for row in all_rows:
        code = str(row.get("product_code") or "").strip()
        if code:
            by_code[code].append(row)

    deletable = []
    kept = []
    for mapping in all_mappings.values():
        for wrong_code in mapping:
            if by_code.get(wrong_code):
                kept.append(wrong_code)
            else:
                deletable.append(wrong_code)

    deleted = ProductCatalog().delete_products(sorted(set(deletable))) if deletable else 0
    return {"products_deleted": deleted, "products_kept_with_refs": sorted(set(kept))}


def _verify(store_id: str, mapping: dict[str, dict]) -> dict:
    from shared.sheets import SheetsKatmani

    sk = SheetsKatmani(store_id)
    green = sk.urun_renk_durumlari_al()
    green_ids = {str(uid).strip() for uid, color in green.items() if color == "green"}

    wrong_left = sorted([wrong for wrong in mapping if wrong in green_ids])
    canonical_present = sum(1 for item in mapping.values() if item["canonical_code"] in green_ids)
    return {
        "wrong_green_remaining": wrong_left,
        "canonical_green_count": canonical_present,
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prefixli Etsy SKU merge araci")
    parser.add_argument(
        "--stores",
        nargs="*",
        default=list(_STORE_CONFIG.keys()),
        help="Islenecek store_id listesi",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    _load_env()
    args = parse_args(argv)

    all_mappings = {store_id: _mappings_for_store(store_id) for store_id in args.stores}
    results = []

    for store_id in args.stores:
        mapping = all_mappings[store_id]
        sheet_res = _update_sheet(store_id, mapping)
        status_res = _move_store_status(store_id, mapping)
        verify_res = _verify(store_id, mapping)
        results.append({
            "store_id": store_id,
            "mapping_count": len(mapping),
            **sheet_res,
            **status_res,
            **verify_res,
        })

    orphan_res = _delete_orphan_wrong_products({sid: all_mappings[sid] for sid in args.stores})

    for item in results:
        print(f"store_id={item['store_id']}")
        print(f"mapping_count={item['mapping_count']}")
        print(f"sheet_updated={item['sheet_updated']}")
        print(f"status_moved={item['status_moved']}")
        print(f"canonical_green_count={item['canonical_green_count']}")
        print(f"wrong_green_remaining={len(item['wrong_green_remaining'])}")
        if item["sheet_missing"]:
            print("sheet_missing=" + ",".join(item["sheet_missing"]))
        if item["status_missing"]:
            print("status_missing=" + ",".join(item["status_missing"]))
        if item["wrong_green_remaining"]:
            print("wrong_green_remaining_codes=" + ",".join(item["wrong_green_remaining"]))
    print(f"products_deleted={orphan_res['products_deleted']}")
    if orphan_res["products_kept_with_refs"]:
        print("products_kept_with_refs=" + ",".join(orphan_res["products_kept_with_refs"]))

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
