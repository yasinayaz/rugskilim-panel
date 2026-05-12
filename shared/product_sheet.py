"""
product_sheet.py
Panel urunlerinin ayri Google Sheet uzerinden yonetimi.

Sekmeler:
  - Area
  - Runner
  - DoorMat
  - Satilanlar
"""

from __future__ import annotations

import os
from datetime import datetime

from shared.sheets import _spreadsheet, _yeniden_dene, _tum_satirlar_al

DEFAULT_PRODUCT_SHEET_ID = "1BBee1OXjGWXeh30wIA7E0WCmkf8qJLm6updvRkXQ1Y8"
PRODUCT_SHEET_ENV_KEY = "PRODUCT_CATALOG_SHEET_ID"

PRODUCT_HEADERS = [
    "product_id",
    "product_code",
    "category",
    "width_cm",
    "length_cm",
    "size_cm",
    "area_m2",
    "width_ft",
    "length_ft",
    "size_ft",
    "status",
    "source_tab",
    "source_row",
    "loaded_store_count",
    "loaded_stores",
    "sold_at",
    "sold_site",
    "customer_name",
    "customer_phone",
    "customer_address",
    "customer_contact_country",
    "note",
    "updated_at",
]

CATEGORY_TABS = {
    "Area": "Area",
    "Runner": "Runner",
    "DoorMat": "DoorMat",
}

ALL_TABS = ["Area", "Runner", "DoorMat", "Satilanlar"]


def product_sheet_id() -> str:
    return os.environ.get(PRODUCT_SHEET_ENV_KEY, "").strip() or DEFAULT_PRODUCT_SHEET_ID


def _clean_str(value) -> str:
    return str(value or "").strip()


def _to_float(value):
    try:
        if value in ("", None):
            return None
        return float(str(value).replace(",", "."))
    except Exception:
        return None


def _product_row(product: dict) -> list:
    return [
        _clean_str(product.get("product_id")),
        _clean_str(product.get("product_code")),
        _clean_str(product.get("category")),
        _clean_str(product.get("width_cm")),
        _clean_str(product.get("length_cm")),
        _clean_str(product.get("size_cm")),
        _clean_str(product.get("area_m2")),
        _clean_str(product.get("width_ft")),
        _clean_str(product.get("length_ft")),
        _clean_str(product.get("size_ft")),
        _clean_str(product.get("status")),
        _clean_str(product.get("source_tab")),
        _clean_str(product.get("source_row")),
        _clean_str(product.get("loaded_store_count")),
        _clean_str(product.get("loaded_stores")),
        _clean_str(product.get("sold_at")),
        _clean_str(product.get("sold_site")),
        _clean_str(product.get("customer_name")),
        _clean_str(product.get("customer_phone")),
        _clean_str(product.get("customer_address")),
        _clean_str(product.get("customer_contact_country")),
        _clean_str(product.get("note")),
        _clean_str(product.get("updated_at")),
    ]


class ProductSheet:
    def __init__(self, sheet_id: str | None = None):
        self.sheet_id = (sheet_id or product_sheet_id()).strip()
        if not self.sheet_id:
            raise ValueError("PRODUCT_CATALOG_SHEET_ID bos olamaz.")
        self._sp = _spreadsheet(self.sheet_id)

    def _worksheet(self, title: str):
        self.ensure_structure()
        return _yeniden_dene("Product worksheet acma", self._sp.worksheet, title)

    def ensure_structure(self):
        mevcut = {ws.title: ws for ws in _yeniden_dene("Product worksheet listesi", self._sp.worksheets)}
        for title in ALL_TABS:
            ws = mevcut.get(title)
            if ws is None:
                ws = _yeniden_dene(
                    "Product worksheet olusturma",
                    self._sp.add_worksheet,
                    title=title,
                    rows=1000,
                    cols=max(len(PRODUCT_HEADERS), 18),
                )
            baslik = _yeniden_dene("Product baslik okuma", ws.row_values, 1)
            if baslik != PRODUCT_HEADERS:
                _yeniden_dene("Product baslik yazma", ws.update, [PRODUCT_HEADERS], "A1")

    def read_products(self) -> list[dict]:
        self.ensure_structure()
        products = []
        for title in ALL_TABS:
            ws = self._worksheet(title)
            for row in _tum_satirlar_al(ws):
                product = {key: _clean_str(value) for key, value in row.items() if key in PRODUCT_HEADERS}
                if not product.get("product_code"):
                    continue
                product["source_sheet_tab"] = title
                if title == "Satilanlar":
                    product["status"] = "sold"
                products.append(product)
        return products

    def write_products(self, products: list[dict]):
        self.ensure_structure()
        grouped = {title: [] for title in ALL_TABS}

        for product in products:
            category = _clean_str(product.get("category"))
            status = _clean_str(product.get("status")).lower()
            if status == "sold":
                grouped["Satilanlar"].append(product)
                continue
            tab = CATEGORY_TABS.get(category)
            if not tab:
                continue
            grouped[tab].append(product)

        for title, rows in grouped.items():
            ws = self._worksheet(title)
            body = [PRODUCT_HEADERS]
            for product in sorted(rows, key=lambda x: (_clean_str(x.get("product_code")), _clean_str(x.get("product_id")))):
                copy = dict(product)
                copy["updated_at"] = copy.get("updated_at") or datetime.now().strftime("%Y-%m-%d %H:%M")
                if title == "Satilanlar" and not copy.get("sold_at"):
                    copy["sold_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                body.append(_product_row(copy))
            _yeniden_dene("Product sheet temizleme", ws.clear)
            _yeniden_dene("Product sheet yazma", ws.update, body, "A1")


def merge_products(source_products: list[dict], existing_products: list[dict]) -> list[dict]:
    existing_map = {
        _clean_str(item.get("product_code")): dict(item)
        for item in existing_products
        if _clean_str(item.get("product_code"))
    }
    merged = {}

    for source in source_products:
        code = _clean_str(source.get("product_code"))
        if not code:
            continue
        current = dict(existing_map.get(code, {}))
        current.update({
            "product_id": current.get("product_id") or source.get("product_id"),
            "product_code": code,
            "category": current.get("category") or source.get("category"),
            "width_cm": source.get("width_cm"),
            "length_cm": source.get("length_cm"),
            "size_cm": source.get("size_cm"),
            "area_m2": source.get("area_m2"),
            "width_ft": source.get("width_ft"),
            "length_ft": source.get("length_ft"),
            "size_ft": source.get("size_ft"),
            "source_tab": source.get("source_tab"),
            "source_row": source.get("source_row"),
            "status": "sold" if str(source.get("status", "")).lower() == "sold" else current.get("status", "active"),
            "loaded_store_count": current.get("loaded_store_count", source.get("loaded_store_count", "")),
            "loaded_stores": current.get("loaded_stores", source.get("loaded_stores", "")),
            "sold_at": current.get("sold_at", ""),
            "sold_site": current.get("sold_site", source.get("sold_site", "")),
            "customer_name": current.get("customer_name", source.get("customer_name", "")),
            "customer_phone": current.get("customer_phone", source.get("customer_phone", "")),
            "customer_address": current.get("customer_address", source.get("customer_address", "")),
            "customer_contact_country": current.get("customer_contact_country", source.get("customer_contact_country", "")),
            "note": current.get("note", source.get("note", "")),
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        })
        if not current.get("category"):
            current["category"] = source.get("category") or "Area"
        merged[code] = current

    for code, existing in existing_map.items():
        if code in merged:
            continue
        status = _clean_str(existing.get("status")).lower() or "active"
        if status == "sold":
            existing["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            merged[code] = existing
            continue
        if _clean_str(existing.get("source_tab")).lower() == "manual":
            existing["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            merged[code] = existing

    return sorted(merged.values(), key=lambda x: _clean_str(x.get("product_code")))


def update_store_presence(products: list[dict], store_map: dict[str, set[str]]) -> list[dict]:
    updated = []
    for product in products:
        code = _clean_str(product.get("product_code"))
        stores = sorted([name for name, codes in store_map.items() if code in codes])
        copy = dict(product)
        copy["loaded_store_count"] = len(stores)
        copy["loaded_stores"] = ", ".join(stores)
        copy["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        updated.append(copy)
    return updated


def guess_category(source_tab: str, width_ft, length_ft) -> str:
    if _clean_str(source_tab).upper().startswith("DOOR"):
        return "DoorMat"

    a = _to_float(width_ft) or 0
    b = _to_float(length_ft) or 0
    short_edge = min(a, b)
    long_edge = max(a, b)
    if short_edge > 0 and (long_edge / short_edge) >= 2.0:
        return "Runner"
    return "Area"
