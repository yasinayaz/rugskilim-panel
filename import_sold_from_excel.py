from __future__ import annotations

import argparse
import shutil
from datetime import datetime
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree as ET
from zipfile import ZipFile


ROOT_DIR = Path(__file__).resolve().parent
ENV_FILE = ROOT_DIR / "streamlit" / ".env"
RUNTIME_STOK = ROOT_DIR / ".runtime" / "streamlit" / "stok.xlsx"
REPO_STOK = ROOT_DIR / "streamlit" / "stok.xlsx"
NS = {
    "a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "pr": "http://schemas.openxmlformats.org/package/2006/relationships",
}


def load_env_file(path: Path) -> None:
    import os

    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" not in line or line.startswith("#"):
            continue
        key, value = line.split("=", 1)
        os.environ[key.strip()] = value.strip()


def clean(value) -> str:
    return str(value or "").strip()


def decimal_str(value: str | float | int | None, digits: int) -> str:
    try:
        num = float(str(value).replace(",", "."))
    except Exception:
        return ""
    return f"{num:.{digits}f}".rstrip("0").rstrip(".")


def float_or_none(value):
    try:
        if value in ("", None):
            return None
        return float(str(value).replace(",", "."))
    except Exception:
        return None


def fmt_size(a, b, digits: int) -> str:
    left = decimal_str(a, digits)
    right = decimal_str(b, digits)
    if left and right:
        return f"{left}x{right}"
    return ""


def normalize_product_code(value: str) -> str | None:
    import re

    text = clean(value)
    if not text:
        return None
    match = re.match(r"^([A-Za-z]{0,3})\s*[-]?\s*(\d+)\b", text)
    if not match:
        return None
    prefix = (match.group(1) or "").lower()
    number = match.group(2)
    return f"{prefix}{number}"


def fallback_product_code(value: str) -> str:
    import re

    text = clean(value)
    match = re.match(r"(\d+)", text)
    return match.group(1) if match else text


def product_id_for_code(code: str) -> str:
    return f"PRD-{clean(code).upper()}"


def infer_category(code: str, width_ft, length_ft) -> str:
    code_clean = clean(code).lower()
    if code_clean.startswith("d"):
        return "Doormat"
    short_edge = min(float_or_none(width_ft) or 0, float_or_none(length_ft) or 0)
    long_edge = max(float_or_none(width_ft) or 0, float_or_none(length_ft) or 0)
    if short_edge > 0 and long_edge / short_edge >= 2.0:
        return "Runner"
    if short_edge > 0 and long_edge > 0:
        return "Area"
    return ""


def workbook_parts(xlsx_path: Path):
    with ZipFile(xlsx_path) as zf:
        shared = []
        if "xl/sharedStrings.xml" in zf.namelist():
            shared_root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
            for si in shared_root.findall("a:si", NS):
                shared.append("".join(node.text or "" for node in si.iterfind(".//a:t", NS)))

        wb_root = ET.fromstring(zf.read("xl/workbook.xml"))
        rels_root = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
        rel_map = {
            rel.attrib["Id"]: rel.attrib["Target"]
            for rel in rels_root.findall("pr:Relationship", NS)
        }

        def normalize_target(target: str) -> str:
            target = target.lstrip("/")
            return target if target.startswith("xl/") else f"xl/{target}"

        for sheet in wb_root.find("a:sheets", NS):
            name = sheet.attrib["name"]
            rel_id = sheet.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"]
            target = normalize_target(rel_map[rel_id])
            yield zf, shared, name, target


def cell_value(cell, shared: list[str]) -> str:
    cell_type = cell.attrib.get("t")
    if cell_type == "s":
        value = cell.find("a:v", NS)
        return shared[int(value.text)] if value is not None and value.text is not None else ""
    if cell_type == "inlineStr":
        return "".join(node.text or "" for node in cell.iterfind(".//a:t", NS))
    value = cell.find("a:v", NS)
    return value.text if value is not None and value.text is not None else ""


def iter_sheet_rows(xlsx_path: Path, sheet_name: str) -> Iterable[list[str]]:
    for zf, shared, name, target in workbook_parts(xlsx_path):
        if name != sheet_name:
            continue
        root = ET.fromstring(zf.read(target))
        for row in root.findall(".//a:sheetData/a:row", NS):
            values = []
            last_col = 0
            for cell in row.findall("a:c", NS):
                ref = cell.attrib.get("r", "")
                col_letters = "".join(ch for ch in ref if ch.isalpha())
                col_index = 0
                for ch in col_letters:
                    col_index = col_index * 26 + (ord(ch.upper()) - 64)
                while last_col and col_index - last_col > 1:
                    values.append("")
                    last_col += 1
                values.append(cell_value(cell, shared))
                last_col = col_index or last_col
            yield values
        return
    raise ValueError(f"Sheet bulunamadi: {sheet_name}")


def parse_sold_products(xlsx_path: Path) -> list[dict]:
    sold_map: dict[str, dict] = {}
    for row_index, row in enumerate(iter_sheet_rows(xlsx_path, "SATILANLAR"), start=1):
        if row_index == 1:
            continue
        raw_code = row[0] if len(row) > 0 else ""
        code = normalize_product_code(raw_code) or fallback_product_code(raw_code)
        if not code:
            continue

        width_cm = float_or_none(row[1] if len(row) > 1 else None)
        if width_cm is None:
            continue
        sold_marker = clean(row[2] if len(row) > 2 else "").upper()
        length_cm = float_or_none(row[3] if len(row) > 3 else None)
        area_m2 = float_or_none(row[4] if len(row) > 4 else None)
        width_ft = float_or_none(row[5] if len(row) > 5 else None)
        length_ft = float_or_none(row[6] if len(row) > 6 else None)
        sold_site = clean(row[7] if len(row) > 7 else "")
        customer_name = clean(row[8] if len(row) > 8 else "")
        customer_contact_country = clean(row[9] if len(row) > 9 else "")
        note = clean(row[10] if len(row) > 10 else "")

        if not (
            sold_marker == "X"
            or sold_site
            or customer_name
            or customer_contact_country
            or note
        ):
            continue

        row_data = {
            "product_id": product_id_for_code(code),
            "product_code": code,
            "category": infer_category(code, width_ft, length_ft),
            "width_cm": decimal_str(width_cm, 0),
            "length_cm": decimal_str(length_cm, 0),
            "size_cm": fmt_size(width_cm, length_cm, 0),
            "area_m2": decimal_str(area_m2, 2),
            "width_ft": decimal_str(width_ft, 1),
            "length_ft": decimal_str(length_ft, 1),
            "size_ft": fmt_size(width_ft, length_ft, 1),
            "status": "sold",
            "source_tab": "SATILANLAR",
            "source_row": str(row_index),
            "loaded_store_count": "",
            "loaded_stores": "",
            "sold_at": "",
            "sold_site": sold_site,
            "customer_name": customer_name,
            "customer_phone": "",
            "customer_address": "",
            "customer_contact_country": customer_contact_country,
            "note": note,
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        current = sold_map.get(code)
        if not current:
            sold_map[code] = row_data
            continue
        for key, value in row_data.items():
            if clean(value):
                current[key] = value
        current["source_row"] = str(row_index)
        current["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return sorted(sold_map.values(), key=lambda item: item["product_code"])


def parse_catalog_products(xlsx_path: Path) -> dict[str, dict]:
    sheet_specs = [
        ("VİNTAGE RUG", "Vintage"),
        ("VINTAGE RUG", "Vintage"),
        ("DOOR MAT RUGS", "Doormat"),
        ("KILIM RUG", "Kilim"),
    ]
    products: dict[str, dict] = {}
    for sheet_name, _label in sheet_specs:
        try:
            rows = list(iter_sheet_rows(xlsx_path, sheet_name))
        except Exception:
            continue
        for row_index, row in enumerate(rows, start=1):
            if row_index == 1:
                continue
            raw_code = row[0] if len(row) > 0 else ""
            code = normalize_product_code(raw_code) or fallback_product_code(raw_code)
            if not code:
                continue
            width_cm = float_or_none(row[1] if len(row) > 1 else None)
            length_cm = float_or_none(row[3] if len(row) > 3 else None)
            area_m2 = float_or_none(row[4] if len(row) > 4 else None)
            width_ft = float_or_none(row[5] if len(row) > 5 else None)
            length_ft = float_or_none(row[6] if len(row) > 6 else None)
            if not any(v is not None for v in [width_cm, length_cm, area_m2, width_ft, length_ft]):
                continue
            products[code] = {
                "product_id": product_id_for_code(code),
                "product_code": code,
                "category": infer_category(code, width_ft, length_ft),
                "width_cm": decimal_str(width_cm, 0),
                "length_cm": decimal_str(length_cm, 0),
                "size_cm": fmt_size(width_cm, length_cm, 0),
                "area_m2": decimal_str(area_m2, 2),
                "width_ft": decimal_str(width_ft, 1),
                "length_ft": decimal_str(length_ft, 1),
                "size_ft": fmt_size(width_ft, length_ft, 1),
                "status": "active",
                "source_tab": sheet_name,
                "source_row": str(row_index),
                "loaded_store_count": "",
                "loaded_stores": "",
                "sold_at": "",
                "sold_site": "",
                "customer_name": "",
                "customer_phone": "",
                "customer_address": "",
                "customer_contact_country": "",
                "note": "",
                "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
    return products


def merge_sold_with_existing(sold_products: list[dict]) -> list[dict]:
    from shared.product_catalog import ProductCatalog

    existing = ProductCatalog().list_products()
    existing_map = {
        clean(item.get("product_code")): dict(item)
        for item in existing
        if clean(item.get("product_code"))
    }

    merged = []
    for sold in sold_products:
        code = clean(sold.get("product_code"))
        current = existing_map.get(code, {})
        merged.append(
            {
                "product_id": current.get("product_id") or sold.get("product_id"),
                "product_code": code,
                "category": current.get("category") or sold.get("category") or "",
                "width_cm": current.get("width_cm") or sold.get("width_cm") or "",
                "length_cm": current.get("length_cm") or sold.get("length_cm") or "",
                "size_cm": current.get("size_cm") or sold.get("size_cm") or "",
                "area_m2": current.get("area_m2") or sold.get("area_m2") or "",
                "width_ft": current.get("width_ft") or sold.get("width_ft") or "",
                "length_ft": current.get("length_ft") or sold.get("length_ft") or "",
                "size_ft": current.get("size_ft") or sold.get("size_ft") or "",
                "status": "sold",
                "source_tab": current.get("source_tab") or sold.get("source_tab") or "SATILANLAR",
                "source_row": sold.get("source_row") or current.get("source_row") or "",
                "loaded_store_count": current.get("loaded_store_count") or "",
                "loaded_stores": current.get("loaded_stores") or "",
                "sold_at": current.get("sold_at") or sold.get("sold_at") or "",
                "sold_site": sold.get("sold_site") or current.get("sold_site") or "",
                "customer_name": sold.get("customer_name") or current.get("customer_name") or "",
                "customer_phone": sold.get("customer_phone") or current.get("customer_phone") or "",
                "customer_address": sold.get("customer_address") or current.get("customer_address") or "",
                "customer_contact_country": sold.get("customer_contact_country") or current.get("customer_contact_country") or "",
                "note": sold.get("note") or current.get("note") or "",
                "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        )
    return merged


def reconcile_existing_products(xlsx_path: Path, sold_products: list[dict]) -> tuple[list[dict], list[str]]:
    from shared.product_catalog import ProductCatalog

    desired_sold_map = {clean(item.get("product_code")): item for item in sold_products if clean(item.get("product_code"))}
    catalog_products = parse_catalog_products(xlsx_path)
    existing = ProductCatalog().list_products()

    rows_to_upsert: list[dict] = []
    codes_to_delete: list[str] = []

    for item in existing:
        code = clean(item.get("product_code"))
        if not code or str(item.get("status", "")).lower() != "sold":
            continue
        if code in desired_sold_map:
            continue
        if code in catalog_products:
            base = catalog_products[code]
            rows_to_upsert.append({
                **item,
                "status": "active",
                "category": base.get("category") or item.get("category") or "",
                "width_cm": base.get("width_cm") or item.get("width_cm") or "",
                "length_cm": base.get("length_cm") or item.get("length_cm") or "",
                "size_cm": base.get("size_cm") or item.get("size_cm") or "",
                "area_m2": base.get("area_m2") or item.get("area_m2") or "",
                "width_ft": base.get("width_ft") or item.get("width_ft") or "",
                "length_ft": base.get("length_ft") or item.get("length_ft") or "",
                "size_ft": base.get("size_ft") or item.get("size_ft") or "",
                "source_tab": base.get("source_tab") or item.get("source_tab") or "",
                "source_row": base.get("source_row") or item.get("source_row") or "",
                "sold_at": "",
                "sold_site": "",
                "customer_name": "",
                "customer_phone": "",
                "customer_address": "",
                "customer_contact_country": "",
                "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            })
        else:
            codes_to_delete.append(code)

    return rows_to_upsert, codes_to_delete


def sync_excel_copy(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)


def main() -> int:
    parser = argparse.ArgumentParser(description="SATILANLAR tabini Supabase products tablosuna aktarir.")
    parser.add_argument("excel_path", help="Kaynak xlsx dosya yolu")
    parser.add_argument("--sync-runtime-stok", action="store_true", help="Dosyayi .runtime/streamlit/stok.xlsx olarak da kopyala")
    parser.add_argument("--sync-repo-stok", action="store_true", help="Dosyayi streamlit/stok.xlsx olarak da kopyala")
    args = parser.parse_args()

    load_env_file(ENV_FILE)

    excel_path = Path(args.excel_path).expanduser().resolve()
    if not excel_path.exists():
        raise SystemExit(f"Excel bulunamadi: {excel_path}")

    sold_products = parse_sold_products(excel_path)
    print(f"SATILANLAR tabindan okunan kayit: {len(sold_products)}")
    if not sold_products:
        raise SystemExit("SATILANLAR tabindan aktarilacak kayit bulunamadi.")

    cleanup_rows, delete_codes = reconcile_existing_products(excel_path, sold_products)
    merged = merge_sold_with_existing(sold_products)
    from shared.product_catalog import ProductCatalog, _supabase_ready

    if not _supabase_ready():
        raise SystemExit("SUPABASE_URL veya SUPABASE_SERVICE_ROLE_KEY hazir degil.")

    catalog = ProductCatalog()
    if cleanup_rows:
        cleaned = catalog.upsert_products(cleanup_rows)
        print(f"Active'a donen kayit: {len(cleaned)}")
    if delete_codes:
        deleted = catalog.delete_products(delete_codes)
        print(f"Silinen yalniz-satilan kayit: {deleted}")

    result = catalog.upsert_products(merged)
    print(f"Supabase upsert tamamlandi: {len(result)} kayit")

    if args.sync_runtime_stok:
        sync_excel_copy(excel_path, RUNTIME_STOK)
        print(f"Runtime stok guncellendi: {RUNTIME_STOK}")

    if args.sync_repo_stok:
        sync_excel_copy(excel_path, REPO_STOK)
        print(f"Repo stok guncellendi: {REPO_STOK}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
