"""
Harfle baslayan Etsy/store SKU kodlarini katalogdaki gercek urun kodlariyla
eslestirir, store-status kayitlarini master urune tasir ve gerektiginde yeni
urun karti olusturur.

Temel kurallar:
  - Buyuk/kucuk harf farki yok sayilir.
  - Bosluk / tire farki canonical eslesmede yok sayilir.
  - Ayni canonical koda dusen adaylarda once kategorili, sonra olculu urun
    master secilir.
  - Master urun yoksa standart gorunumle yeni urun olusturulur: B111 -> B 111
  - Yanlis store kodu master'a tasinir, eski store-status kaydi silinir.
  - Yanlis product kaydi varsa ve artik hic store referansi kalmadiysa silinir.

Varsayilan calisma modu dry-run'dir; rapor uretir ama veri degistirmez.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
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


def _clean(value) -> str:
    return str(value or "").strip()


_LETTER_CODE_RE = re.compile(r"^([A-Za-z]{1,5})\s*-?\s*(\d+)\b")


def _canonical_code(value: str) -> str:
    text = _clean(value)
    match = _LETTER_CODE_RE.match(text)
    if not match:
        return ""
    return f"{match.group(1)}{match.group(2)}".lower()


def _standard_code(value: str) -> str:
    text = _clean(value)
    match = _LETTER_CODE_RE.match(text)
    if not match:
        return ""
    return f"{match.group(1).upper()} {match.group(2)}"


def _product_id_for_code(code: str) -> str:
    canonical = _canonical_code(code).upper()
    return f"PRD-{canonical}" if canonical else f"PRD-{_clean(code).upper()}"


def _has_category(product: dict) -> bool:
    return bool(_clean(product.get("category")))


def _has_measurements(product: dict) -> bool:
    for key in ("width_cm", "length_cm", "size_cm", "area_m2", "width_ft", "length_ft", "size_ft"):
        value = _clean(product.get(key))
        if value and value not in {"0", "0.0"}:
            return True
    return False


@dataclass
class MergeDecision:
    wrong_code: str
    canonical: str
    master_code: str
    action: str
    reason: str
    category: str
    size_ft: str
    size_cm: str


def _csv_sku_map(csv_path: str) -> dict[str, str]:
    path = Path(csv_path).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"CSV bulunamadi: {path}")

    canonical_to_display: dict[str, str] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            sku = _clean(row.get("SKU"))
            canonical = _canonical_code(sku)
            if not canonical or canonical in canonical_to_display:
                continue
            canonical_to_display[canonical] = sku
    return canonical_to_display


def _select_master(canonical: str, products: list[dict], wrong_code: str, preferred_display_code: str = "") -> tuple[dict | None, str]:
    if not products:
        return None, "create_new_standard_product"

    standard = _clean(preferred_display_code) or _standard_code(wrong_code)
    categorized = [p for p in products if _has_category(p)]
    measured = [p for p in products if _has_measurements(p)]
    exact_standard = [p for p in products if _clean(p.get("product_code")) == standard]

    if len(categorized) == 1:
        return categorized[0], "single_categorized_match"
    if len(exact_standard) == 1:
        return exact_standard[0], "single_standard_match"
    if len(measured) == 1:
        return measured[0], "single_measured_match"
    if len(products) == 1:
        return products[0], "single_existing_match"

    def _priority(product: dict) -> tuple[int, int, int, str]:
        code = _clean(product.get("product_code"))
        return (
            0 if _has_category(product) else 1,
            0 if code == standard else 1,
            0 if _has_measurements(product) else 1,
            code.lower(),
        )

    chosen = sorted(products, key=_priority)[0]
    return chosen, "best_effort_priority_match"


def _create_product_payload(product_code: str) -> dict:
    return {
        "product_id": _product_id_for_code(product_code),
        "product_code": product_code,
        "category": "",
        "width_cm": "",
        "length_cm": "",
        "size_cm": "",
        "area_m2": "",
        "width_ft": "",
        "length_ft": "",
        "size_ft": "",
        "status": "active",
        "source_tab": "manual",
        "source_row": "",
        "loaded_store_count": 0,
        "loaded_stores": "",
        "sold_at": "",
        "sold_site": "",
        "customer_name": "",
        "customer_phone": "",
        "customer_address": "",
        "customer_contact_country": "",
        "note": "Auto-created from letter-prefixed store SKU merge",
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def _decisions_for_store(store_id: str, csv_display_map: dict[str, str] | None = None) -> tuple[list[MergeDecision], list[dict], list[dict], list[dict]]:
    from shared.product_catalog import ProductCatalog, StoreCatalog

    products = ProductCatalog().list_products()
    all_store_rows = _all_store_rows_paginated()
    store_rows = StoreCatalog().list_by_store(store_id)
    csv_display_map = csv_display_map or {}

    products_by_canonical: dict[str, list[dict]] = defaultdict(list)
    for product in products:
        canonical = _canonical_code(product.get("product_code"))
        if canonical:
            products_by_canonical[canonical].append(product)

    decisions: list[MergeDecision] = []
    creates: list[dict] = []
    moves: list[dict] = []
    deletes: list[dict] = []
    moved_pairs: set[tuple[str, str, str]] = set()
    delete_pairs: set[tuple[str, str]] = set()
    seen_masters: set[str] = set()
    move_plan_by_wrong_code: dict[str, str] = {}

    for row in sorted(store_rows, key=lambda item: _clean(item.get("product_code")).lower()):
        wrong_code = _clean(row.get("product_code"))
        canonical = _canonical_code(wrong_code)
        if not canonical:
            continue

        preferred_display_code = _clean(csv_display_map.get(canonical))
        master, reason = _select_master(canonical, products_by_canonical.get(canonical, []), wrong_code, preferred_display_code)
        desired_master_code = preferred_display_code or _standard_code(wrong_code)

        if master is None:
            master_code = desired_master_code
            if not master_code:
                continue
            if master_code not in seen_masters:
                creates.append(_create_product_payload(master_code))
                seen_masters.add(master_code)
            decision_reason = reason
            category = ""
            size_ft = ""
            size_cm = ""
        else:
            original_master_code = _clean(master.get("product_code"))
            if desired_master_code and desired_master_code.lower() != original_master_code.lower():
                renamed_master = dict(master)
                renamed_master["product_id"] = _product_id_for_code(desired_master_code)
                renamed_master["product_code"] = desired_master_code
                if desired_master_code not in seen_masters:
                    creates.append(renamed_master)
                    seen_masters.add(desired_master_code)
                master_code = desired_master_code
                move_plan_by_wrong_code[original_master_code] = desired_master_code
                decision_reason = f"{reason}_csv_display_preferred"
            else:
                master_code = original_master_code
                decision_reason = reason
            category = _clean(master.get("category"))
            size_ft = _clean(master.get("size_ft"))
            size_cm = _clean(master.get("size_cm"))

        decisions.append(
            MergeDecision(
                wrong_code=wrong_code,
                canonical=canonical,
                master_code=master_code,
                action="merge" if wrong_code.lower() != master_code.lower() else "normalize_case",
                reason=decision_reason,
                category=category,
                size_ft=size_ft,
                size_cm=size_cm,
            )
        )

        if wrong_code.lower() != master_code.lower():
            new_row = dict(row)
            new_row["product_code"] = master_code
            moves.append(new_row)
            move_key = (_clean(new_row.get("store_id")), wrong_code, master_code)
            if move_key not in moved_pairs:
                moved_pairs.add(move_key)
            delete_pairs.add((store_id, wrong_code))
            move_plan_by_wrong_code[wrong_code] = master_code

    # Hedef magazadaki yanlis kodlar baska magazalarda da varsa ayni master'a tasinmali.
    for row in all_store_rows:
        wrong_code = _clean(row.get("product_code"))
        master_code = move_plan_by_wrong_code.get(wrong_code)
        if not master_code:
            continue
        store_code = _clean(row.get("store_id"))
        if not store_code:
            continue
        if wrong_code.lower() == master_code.lower():
            continue
        move_key = (store_code, wrong_code, master_code)
        if move_key in moved_pairs:
            continue
        new_row = dict(row)
        new_row["product_code"] = master_code
        moves.append(new_row)
        moved_pairs.add(move_key)
        delete_pairs.add((store_code, wrong_code))

    deletes = [
        {"store_id": sid, "product_code": code}
        for sid, code in sorted(delete_pairs, key=lambda item: (item[0].lower(), item[1].lower()))
    ]
    return decisions, creates, moves, deletes


def _all_store_codes() -> Counter:
    rows = _all_store_rows_paginated()
    counts: Counter = Counter()
    for row in rows:
        code = _clean(row.get("product_code"))
        if code:
            counts[code] += 1
    return counts


def _all_store_rows_paginated() -> list[dict]:
    import requests
    from shared.product_catalog import SUPABASE_STORE_TABLE, _base_url, _headers

    rows = []
    offset = 0
    page_size = 1000
    url = f"{_base_url()}/rest/v1/{SUPABASE_STORE_TABLE}"

    while True:
        resp = requests.get(
            url,
            headers={**_headers(), "Accept": "application/json", "Range-Unit": "items", "Range": f"{offset}-{offset + page_size - 1}"},
            params={"select": "*", "order": "product_code.asc"},
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


def _write_report(store_id: str, decisions: list[MergeDecision], creates: list[dict], moves: list[dict], report_path: Path) -> None:
    prefix_counter: Counter = Counter()
    reason_counter: Counter = Counter()
    merge_rows = []
    create_rows = []

    for item in decisions:
        match = re.match(r"^([A-Za-z]{1,5})", item.wrong_code)
        if match:
            prefix_counter[match.group(1).upper()] += 1
        reason_counter[item.reason] += 1
        if item.wrong_code.lower() != item.master_code.lower():
            merge_rows.append(item)

    for payload in creates:
        create_rows.append((_clean(payload.get("product_code")), _clean(payload.get("note"))))

    lines = [
        f"# {store_id} Harfli Kod Merge Uygulama Raporu",
        "",
        f"Tarih: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## Ozet",
        "",
        f"- Analiz edilen harfli store-status kaydi: {len(decisions)}",
        f"- Master urune tasinacak yanlis kod: {len(merge_rows)}",
        f"- Yeni olusturulacak standart urun karti: {len(create_rows)}",
        "",
        "Reason dagilimi: " + ", ".join(f"{key}={value}" for key, value in sorted(reason_counter.items())),
        "",
        "Prefix dagilimi: " + ", ".join(f"{key}={value}" for key, value in sorted(prefix_counter.items())),
        "",
        "## Merge Edilecek Store Kodlari",
        "",
        "| Eski kod | Master kod | Kategori | ft | cm | Sebep |",
        "|---|---|---|---|---|---|",
    ]
    for item in merge_rows:
        lines.append(
            f"| {item.wrong_code} | {item.master_code} | {item.category or '-'} | "
            f"{item.size_ft or '-'} | {item.size_cm or '-'} | {item.reason} |"
        )

    lines.extend(
        [
            "",
            "## Diger Magazalara Yansiyacak Tasimalar",
            "",
            "| Magaza | Eski kod | Master kod |",
            "|---|---|---|",
        ]
    )
    move_plan = {item.wrong_code: item.master_code for item in decisions if item.wrong_code.lower() != item.master_code.lower()}
    cross_lines = []
    for wrong_code, master_code in sorted(move_plan.items(), key=lambda item: item[0].lower()):
        touched_stores = sorted(
            {
                _clean(row.get("store_id"))
                for row in moves
                if _clean(row.get("product_code")) == master_code
            },
            key=str.lower,
        )
        for sid in touched_stores:
            cross_lines.append((sid, wrong_code, master_code))
    for sid, wrong_code, master_code in cross_lines:
        lines.append(f"| {sid} | {wrong_code} | {master_code} |")

    lines.extend(
        [
            "",
            "## Yeni Urun Karti Acilacak Kodlar",
            "",
            "| Yeni kod | Not |",
            "|---|---|",
        ]
    )
    for product_code, note in create_rows:
        lines.append(f"| {product_code} | {note} |")

    report_path.write_text("\n".join(lines), encoding="utf-8")


def _apply_changes(store_id: str, decisions: list[MergeDecision], creates: list[dict], moves: list[dict], deletes: list[dict]) -> dict:
    import requests
    from shared.product_catalog import ProductCatalog, StoreCatalog, SUPABASE_STORE_TABLE, _base_url, _headers

    created = 0
    moved = 0
    deleted_store_rows = 0
    deleted_products = 0

    if creates:
        ProductCatalog().upsert_products(creates)
        created = len(creates)

    if moves:
        StoreCatalog().upsert(moves)
        moved = len(moves)

    if deletes:
        url = f"{_base_url()}/rest/v1/{SUPABASE_STORE_TABLE}"
        for item in deletes:
            resp = requests.delete(
                url,
                headers={**_headers(), "Prefer": "return=representation"},
                params={"store_id": f"eq.{item['store_id']}", "product_code": f"eq.{item['product_code']}"},
                timeout=45,
            )
            if not resp.ok:
                raise RuntimeError(
                    f"store_status silme basarisiz: {item['store_id']} {item['product_code']} -> {resp.status_code} {resp.text}"
                )
            deleted_store_rows += len(resp.json() or [])

    wrong_codes = sorted(
        {
            item.wrong_code
            for item in decisions
            if item.wrong_code.lower() != item.master_code.lower()
        }
    )
    if wrong_codes:
        remaining_refs = _all_store_codes()
        orphan_products = [code for code in wrong_codes if remaining_refs.get(code, 0) == 0]
        if orphan_products:
            deleted_products = ProductCatalog().delete_products(orphan_products)

    return {
        "products_created": created,
        "store_rows_moved": moved,
        "store_rows_deleted": deleted_store_rows,
        "orphan_products_deleted": deleted_products,
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Harfle baslayan store SKU merge araci")
    parser.add_argument("--store", default="BohoRugHouse", help="Islenecek store_id")
    parser.add_argument("--csv-path", default="", help="Opsiyonel Etsy CSV yolu; SKU gorunumunu otorite kabul eder")
    parser.add_argument("--apply", action="store_true", help="Degisiklikleri Supabase'e uygula")
    parser.add_argument(
        "--report-path",
        default="",
        help="Opsiyonel markdown rapor yolu. Bossa reports altina tarihli dosya yazilir.",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    _load_env()
    args = parse_args(argv)

    csv_display_map = _csv_sku_map(args.csv_path) if args.csv_path else {}
    decisions, creates, moves, deletes = _decisions_for_store(args.store, csv_display_map=csv_display_map)
    report_path = Path(args.report_path) if args.report_path else _repo_root() / "reports" / f"{args.store.lower()}-letter-merge-apply-{datetime.now().strftime('%Y-%m-%d')}.md"
    _write_report(args.store, decisions, creates, moves, report_path)

    result = {
        "store": args.store,
        "report_path": str(report_path),
        "decision_count": len(decisions),
        "merge_count": sum(1 for item in decisions if item.wrong_code.lower() != item.master_code.lower()),
        "create_count": len(creates),
        "mode": "apply" if args.apply else "dry-run",
    }

    if args.apply:
        result.update(_apply_changes(args.store, decisions, creates, moves, deletes))

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
