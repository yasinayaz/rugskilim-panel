"""
Kalan prefix'li loaded SKU'lari, prefix sonrasi tam suffix'i kullanarak
olculu (gercek) urun kodlariyla eslestirir ve guvenli merge uygular.

Kurallar:
  - Prefixler: LR, LP, LMX, RST, WLR, WLB
  - Canonical aday: prefix atildiktan sonra kalan tum ifade
  - Sadece measured product katalogunda tekil eslesenler merge edilir
  - Soft eslesme sadece tire/bosluk farki icin kullanilir (E 73 -> E-73 gibi)
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from collections import defaultdict
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


STORE_PATTERNS = {
    "RugsShopTurkey": r"^(RST)\s*(.*)$",
    "WovenLoomRugs": r"^(WLR|WLB)\s*(.*)$",
    "LoomixRugs": r"^(LMX)\s*(.*)$",
    "LoopRug": r"^(LR|LP)\s*(.*)$",
}


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip())


def _soft_norm(text: str) -> str:
    text = _norm(text).replace("-", " ")
    return re.sub(r"\s+", " ", text).strip()


def _compact_norm(text: str) -> str:
    return re.sub(r"[-\s]+", "", _norm(text)).strip()


def _measured_products() -> tuple[dict[str, list[str]], dict[str, list[str]], dict[str, list[str]]]:
    from shared.product_catalog import ProductCatalog

    exact = defaultdict(list)
    soft = defaultdict(list)
    compact = defaultdict(list)

    for product in ProductCatalog().list_products():
        code = str(product.get("product_code") or "").strip()
        if not code:
            continue
        dims = [str(product.get(k) or "").strip() for k in ("width_cm", "length_cm", "size_cm", "width_ft", "length_ft", "size_ft", "area_m2")]
        if not any(value and value not in {"0", "0.0"} for value in dims):
            continue
        exact[_norm(code).casefold()].append(code)
        soft[_soft_norm(code).casefold()].append(code)
        compact[_compact_norm(code).casefold()].append(code)

    return exact, soft, compact


def _build_safe_mapping(store_id: str) -> tuple[dict[str, dict], list[dict]]:
    from shared.sheets import SheetsKatmani

    exact_map, soft_map, compact_map = _measured_products()
    sk = SheetsKatmani(store_id)
    green = {
        str(urun_id).strip()
        for urun_id, renk in sk.urun_renk_durumlari_al().items()
        if str(renk).strip() == "green"
    }

    tentative = {}
    unresolved = []
    pattern = STORE_PATTERNS[store_id]

    for current in sorted(green):
        match = re.match(pattern, current, re.I)
        if not match:
            continue
        suffix = str(match.group(2) or "").strip()
        if suffix.startswith("-"):
            suffix = suffix[1:].strip()
        if not suffix:
            unresolved.append({"current": current, "reason": "empty_suffix"})
            continue

        exact_hits = exact_map.get(_norm(suffix).casefold(), [])
        soft_hits = soft_map.get(_soft_norm(suffix).casefold(), [])
        compact_hits = compact_map.get(_compact_norm(suffix).casefold(), [])

        if len(exact_hits) == 1:
            tentative[current] = {
                "wrong_code": current,
                "canonical_code": exact_hits[0],
                "raw_sku": current,
                "match_type": "exact",
            }
            continue
        if len(exact_hits) == 0 and len(soft_hits) == 1:
            tentative[current] = {
                "wrong_code": current,
                "canonical_code": soft_hits[0],
                "raw_sku": current,
                "match_type": "soft",
            }
            continue
        if len(exact_hits) == 0 and len(soft_hits) == 0 and len(compact_hits) == 1:
            tentative[current] = {
                "wrong_code": current,
                "canonical_code": compact_hits[0],
                "raw_sku": current,
                "match_type": "compact",
            }
            continue

        unresolved.append({
            "current": current,
            "suffix": suffix,
            "exact_hits": exact_hits[:10],
            "soft_hits": soft_hits[:10],
            "compact_hits": compact_hits[:10],
            "reason": "ambiguous_or_missing",
        })

    by_canonical = defaultdict(list)
    for current, item in tentative.items():
        by_canonical[item["canonical_code"]].append(current)

    safe = {}
    for canonical_code, wrong_codes in by_canonical.items():
        if len(wrong_codes) == 1:
            wrong_code = wrong_codes[0]
            safe[wrong_code] = tentative[wrong_code]
            continue
        unresolved.append({
            "reason": "duplicate_canonical_target",
            "canonical_code": canonical_code,
            "wrong_codes": sorted(wrong_codes),
        })

    return safe, unresolved


def _update_sheet(store_id: str, mapping: dict[str, dict]) -> int:
    from shared.sheets import SheetsKatmani, _baslik_pozisyonlari, _kolon_no_from_positions, _yeniden_dene
    from gspread.utils import rowcol_to_a1

    sk = SheetsKatmani(store_id)
    sk.sheet_hazirla()
    ws = sk._baglanti()
    satir_map = sk._satir_haritasi_al(ws, force_refresh=True)
    pozisyonlar = _baslik_pozisyonlari(ws)
    batch = []
    updated = 0

    for wrong_code, item in sorted(mapping.items()):
        satir_no = satir_map.get(wrong_code)
        if not satir_no:
            continue
        current_b = ""  # preserve raw if already present? raw current is enough for this migration
        for alan, deger, occurrence in [
            ("urun_id", item["canonical_code"], 0),
            ("pcloud_klasor_yolu", item["raw_sku"] or current_b, 0),
            ("urun_id", item["canonical_code"], 1),
        ]:
            kolon = _kolon_no_from_positions(pozisyonlar, alan, occurrence=occurrence)
            if kolon:
                batch.append({"range": rowcol_to_a1(satir_no, kolon), "values": [[deger]]})
        updated += 1

    if batch:
        _yeniden_dene("Kalan prefixli SKU sheet guncelleme", ws.batch_update, batch)
        sk._satir_haritasini_gecersiz_kil()

    return updated


def _store_rows(store_id: str) -> list[dict]:
    from shared.product_catalog import StoreCatalog

    return StoreCatalog().list_by_store(store_id)


def _move_store_status(store_id: str, mapping: dict[str, dict]) -> int:
    from shared.product_catalog import StoreCatalog, SUPABASE_STORE_TABLE, _base_url, _headers

    rows = _store_rows(store_id)
    row_map = {str(row.get("product_code") or "").strip(): row for row in rows}
    upsert_rows = []
    delete_codes = []

    for wrong_code, item in sorted(mapping.items()):
        current = row_map.get(wrong_code)
        if not current:
            continue
        new_row = dict(current)
        new_row["product_code"] = item["canonical_code"]
        upsert_rows.append(new_row)
        delete_codes.append(wrong_code)

    if upsert_rows:
        StoreCatalog().upsert(upsert_rows)

    if delete_codes:
        url = f"{_base_url()}/rest/v1/{SUPABASE_STORE_TABLE}"
        for wrong_code in delete_codes:
            resp = requests.delete(
                url,
                headers={**_headers(), "Prefer": "return=representation"},
                params={"store_id": f"eq.{store_id}", "product_code": f"eq.{wrong_code}"},
                timeout=45,
            )
            if not resp.ok:
                raise RuntimeError(f"store_status silme basarisiz: {store_id} {wrong_code} -> {resp.status_code} {resp.text}")

    return len(delete_codes)


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


def _delete_orphan_products(all_mappings: dict[str, dict[str, dict]]) -> int:
    from shared.product_catalog import ProductCatalog

    rows = _all_store_rows_paginated()
    refs = defaultdict(int)
    for row in rows:
        code = str(row.get("product_code") or "").strip()
        if code:
            refs[code] += 1

    deletable = []
    for mapping in all_mappings.values():
        for wrong_code in mapping:
            if refs.get(wrong_code, 0) == 0:
                deletable.append(wrong_code)

    return ProductCatalog().delete_products(sorted(set(deletable))) if deletable else 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Kalan prefixli suffix SKU merge araci")
    parser.add_argument("--stores", nargs="*", default=list(STORE_PATTERNS.keys()))
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    _load_env()
    args = parse_args(argv)
    all_mappings = {}
    unresolved_by_store = {}

    for store_id in args.stores:
        safe, unresolved = _build_safe_mapping(store_id)
        all_mappings[store_id] = safe
        unresolved_by_store[store_id] = unresolved

    for store_id in args.stores:
        sheet_updated = _update_sheet(store_id, all_mappings[store_id])
        status_moved = _move_store_status(store_id, all_mappings[store_id])
        print(f"store_id={store_id}")
        print(f"safe_mapping={len(all_mappings[store_id])}")
        print(f"sheet_updated={sheet_updated}")
        print(f"status_moved={status_moved}")
        print(f"unresolved_remaining={len(unresolved_by_store[store_id])}")
        if unresolved_by_store[store_id]:
            print("unresolved_samples=" + ",".join(item["current"] for item in unresolved_by_store[store_id][:20]))

    deleted = _delete_orphan_products(all_mappings)
    print(f"products_deleted={deleted}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
