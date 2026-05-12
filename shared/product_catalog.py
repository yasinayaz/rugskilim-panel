"""
product_catalog.py
Supabase uzerinden panel urun stok yonetimi.
"""

from __future__ import annotations

import os
from datetime import datetime

SUPABASE_URL_ENV = "SUPABASE_URL"
SUPABASE_SERVICE_KEY_ENV = "SUPABASE_SERVICE_ROLE_KEY"
SUPABASE_PRODUCTS_TABLE_ENV = "SUPABASE_PRODUCTS_TABLE"
DEFAULT_PRODUCTS_TABLE = "products"


def _env(name: str) -> str:
    return os.environ.get(name, "").strip()


def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _clean(value) -> str:
    return str(value or "").strip()


def _headers() -> dict:
    key = _env(SUPABASE_SERVICE_KEY_ENV)
    if not key:
        raise ValueError("SUPABASE_SERVICE_ROLE_KEY tanımlı değil.")
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }


def _base_url() -> str:
    url = _env(SUPABASE_URL_ENV)
    if not url:
        raise ValueError("SUPABASE_URL tanımlı değil.")
    return url.rstrip("/")


def _table_name() -> str:
    return _env(SUPABASE_PRODUCTS_TABLE_ENV) or DEFAULT_PRODUCTS_TABLE


def _rest_url() -> str:
    return f"{_base_url()}/rest/v1/{_table_name()}"


class ProductCatalog:
    def list_products(self) -> list[dict]:
        import requests
        products = []
        page_size = 1000
        offset = 0
        while True:
            response = requests.get(
                _rest_url(),
                headers={**_headers(), "Accept": "application/json", "Range-Unit": "items", "Range": f"{offset}-{offset + page_size - 1}"},
                params={"select": "*", "order": "product_code.asc"},
                timeout=45,
            )
            if not response.ok:
                raise RuntimeError(f"Supabase ürünleri okunamadı: {response.status_code} {response.text}")
            page = response.json()
            products.extend(page)
            if len(page) < page_size:
                break
            offset += page_size

        # Mağaza bilgilerini product_store_status'tan ekle (sayfalama ile)
        try:
            store_rows = []
            s_offset = 0
            while True:
                page = requests.get(
                    f"{_base_url()}/rest/v1/{SUPABASE_STORE_TABLE}",
                    headers={**_headers(), "Accept": "application/json", "Range-Unit": "items", "Range": f"{s_offset}-{s_offset + 999}"},
                    params={"select": "product_code,store_id,status,renk"},
                    timeout=30,
                ).json()
                store_rows.extend(page)
                if len(page) < 1000:
                    break
                s_offset += 1000
            store_map: dict[str, list[str]] = {}
            for row in store_rows:
                if row.get("renk") == "green" or row.get("status") == "done":
                    store_map.setdefault(row["product_code"], []).append(row["store_id"])
            for p in products:
                code = p.get("product_code", "")
                stores = store_map.get(code, [])
                p["loaded_stores"] = ", ".join(sorted(stores))
                p["loaded_store_count"] = len(stores)
        except Exception:
            pass

        return products

    def upsert_products(self, products: list[dict]) -> list[dict]:
        payload = []
        for product in products:
            row = dict(product)
            row["product_code"] = _clean(row.get("product_code"))
            if not row["product_code"]:
                continue
            row["updated_at"] = row.get("updated_at") or _now_str()
            payload.append(row)

        if not payload:
            return []

        import requests
        response = requests.post(
            _rest_url(),
            headers={
                **_headers(),
                "Prefer": "resolution=merge-duplicates,return=representation",
            },
            params={"on_conflict": "product_code"},
            json=payload,
            timeout=60,
        )
        if not response.ok:
            raise RuntimeError(f"Supabase ürün upsert başarısız: {response.status_code} {response.text}")
        return response.json()

    def replace_from_source(self, source_products: list[dict]) -> list[dict]:
        existing = self.list_products()
        existing_map = {
            _clean(item.get("product_code")): dict(item)
            for item in existing
            if _clean(item.get("product_code"))
        }
        merged = []

        for source in source_products:
            code = _clean(source.get("product_code"))
            if not code:
                continue
            current = existing_map.get(code, {})
            merged.append({
                "product_id": current.get("product_id") or source.get("product_id"),
                "product_code": code,
                "category": current.get("category") or source.get("category") or "",
                "width_cm": source.get("width_cm") or "",
                "length_cm": source.get("length_cm") or "",
                "size_cm": source.get("size_cm") or "",
                "area_m2": source.get("area_m2") or "",
                "width_ft": source.get("width_ft") or "",
                "length_ft": source.get("length_ft") or "",
                "size_ft": source.get("size_ft") or "",
                "status": "sold" if _clean(source.get("status")).lower() == "sold" else _clean(current.get("status")) or "active",
                "source_tab": source.get("source_tab") or "",
                "source_row": source.get("source_row") or "",
                "sold_at": current.get("sold_at") or "",
                "sold_site": current.get("sold_site") or "",
                "customer_name": current.get("customer_name") or "",
                "customer_phone": current.get("customer_phone") or "",
                "customer_address": current.get("customer_address") or "",
                "customer_contact_country": current.get("customer_contact_country") or "",
                "note": current.get("note") or source.get("note") or "",
                "updated_at": _now_str(),
            })

        for code, current in existing_map.items():
            if code in {_clean(p.get("product_code")) for p in merged}:
                continue
            if _clean(current.get("source_tab")).lower() == "manual" or _clean(current.get("status")).lower() == "sold":
                current["updated_at"] = _now_str()
                merged.append(current)

        return self.upsert_products(merged)

    def mark_sold(self, product_code: str) -> dict | None:
        code = _clean(product_code)
        if not code:
            return None

        import requests
        response = requests.patch(
            _rest_url(),
            headers={**_headers(), "Prefer": "return=representation"},
            params={"product_code": f"eq.{code}"},
            json={"status": "sold", "sold_at": _now_str(), "updated_at": _now_str()},
            timeout=45,
        )
        if not response.ok:
            raise RuntimeError(f"Supabase satış güncellemesi başarısız: {response.status_code} {response.text}")
        data = response.json()
        return data[0] if data else None

    def refresh_store_presence(self, store_map: dict[str, set[str]]) -> None:
        """Mağaza varlığını product_store_status tablosuna yazar."""
        rows = []
        for store_id, codes in store_map.items():
            for code in codes:
                rows.append({
                    "product_code": _clean(code),
                    "store_id": store_id,
                    "status": "done",
                    "renk": "green",
                })
        if rows:
            StoreCatalog().upsert(rows)


SUPABASE_STORE_TABLE = "product_store_status"


class StoreCatalog:
    def _url(self) -> str:
        return f"{_base_url()}/rest/v1/{SUPABASE_STORE_TABLE}"

    def list_by_store(self, store_id: str | None = None) -> list[dict]:
        import requests
        params: dict = {"select": "*", "order": "product_code.asc"}
        if store_id:
            params["store_id"] = f"eq.{store_id}"
        r = requests.get(self._url(), headers={**_headers(), "Accept": "application/json"}, params=params, timeout=45)
        if not r.ok:
            raise RuntimeError(f"store_status okunamadı: {r.status_code} {r.text}")
        return r.json()

    def upsert(self, rows: list[dict]) -> None:
        if not rows:
            return
        import requests
        r = requests.post(
            self._url(),
            headers={**_headers(), "Prefer": "resolution=merge-duplicates,return=minimal"},
            params={"on_conflict": "product_code,store_id"},
            json=[{k: v for k, v in row.items() if k != "updated_at"} for row in rows],
            timeout=60,
        )
        if not r.ok:
            raise RuntimeError(f"store_status upsert başarısız: {r.status_code} {r.text}")

    def as_inventory_cache(self) -> dict:
        rows = self.list_by_store()
        stores: dict = {}
        for row in rows:
            sid = row.get("store_id", "")
            code = row.get("product_code", "")
            if not sid or not code:
                continue
            if sid not in stores:
                stores[sid] = {"store_name": sid, "count": 0, "urunler": {}}
            stores[sid]["urunler"][code] = {
                "urun_id": code,
                "status": row.get("status", ""),
                "etsy_draft_url": row.get("etsy_draft_url", ""),
                "islem_tarihi": row.get("islem_tarihi", ""),
                "renk": row.get("renk", ""),
            }
        for sid in stores:
            stores[sid]["count"] = len(stores[sid]["urunler"])
        import time
        return {"updated_at": time.time(), "stores": stores, "errors": {}}


def guess_category(source_tab: str) -> str:
    tab = _clean(source_tab).upper()
    if tab.startswith("DOOR"):
        return "Doormat"
    return ""


def guess_category_by_size(size: str) -> str:
    """'2,3x7' veya '2.3x7' gibi WxL formatından Runner/Area Rug döndürür."""
    size = _clean(size).replace(",", ".")
    if "x" not in size:
        return ""
    parts = size.lower().split("x", 1)
    try:
        width = float(parts[0])
        length = float(parts[1])
    except (ValueError, IndexError):
        return ""
    if width <= 0:
        return ""
    return "Runner" if (length / width) >= 3 else "Area Rug"
