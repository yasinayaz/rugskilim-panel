"""
product_catalog.py
Supabase uzerinden panel urun stok yonetimi.
"""

from __future__ import annotations

import os
import json
from datetime import datetime
from pathlib import Path

SUPABASE_URL_ENV = "SUPABASE_URL"
SUPABASE_SERVICE_KEY_ENV = "SUPABASE_SERVICE_ROLE_KEY"
SUPABASE_PRODUCTS_TABLE_ENV = "SUPABASE_PRODUCTS_TABLE"
DEFAULT_PRODUCTS_TABLE = "products"
LOCAL_PRODUCTS_DB = Path(__file__).resolve().parent.parent / ".runtime" / "streamlit" / "panel_products.json"


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


def _supabase_ready() -> bool:
    return bool(_env(SUPABASE_URL_ENV) and _env(SUPABASE_SERVICE_KEY_ENV))


def _json_load() -> list[dict]:
    try:
        if not LOCAL_PRODUCTS_DB.exists():
            return []
        data = json.loads(LOCAL_PRODUCTS_DB.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _json_save(rows: list[dict]):
    LOCAL_PRODUCTS_DB.parent.mkdir(parents=True, exist_ok=True)
    LOCAL_PRODUCTS_DB.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


class ProductCatalog:
    def list_products(self) -> list[dict]:
        if not _supabase_ready():
            return sorted(_json_load(), key=lambda x: _clean(x.get("product_code")))
        import requests
        response = requests.get(
            _rest_url(),
            headers={**_headers(), "Accept": "application/json"},
            params={"select": "*", "order": "product_code.asc"},
            timeout=45,
        )
        if not response.ok:
            raise RuntimeError(f"Supabase ürünleri okunamadı: {response.status_code} {response.text}")
        products = response.json()

        # Mağaza bilgilerini product_store_status'tan ekle
        try:
            store_rows = requests.get(
                f"{_base_url()}/rest/v1/{SUPABASE_STORE_TABLE}",
                headers={**_headers(), "Accept": "application/json"},
                params={"select": "product_code,store_id,status,renk"},
                timeout=30,
            ).json()
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

        def _json_fallback(rows_to_merge: list[dict]) -> list[dict]:
            existing = {
                _clean(item.get("product_code")): dict(item)
                for item in _json_load()
                if _clean(item.get("product_code"))
            }
            for row in rows_to_merge:
                existing[_clean(row.get("product_code"))] = row
            rows = sorted(existing.values(), key=lambda x: _clean(x.get("product_code")))
            _json_save(rows)
            return rows

        if not _supabase_ready():
            return _json_fallback(payload)

        try:
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
        except ValueError:
            return _json_fallback(payload)

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

        if not _supabase_ready():
            rows = _json_load()
            updated = None
            for row in rows:
                if _clean(row.get("product_code")) == code:
                    row["status"] = "sold"
                    row["sold_at"] = _now_str()
                    row["updated_at"] = _now_str()
                    updated = row
                    break
            _json_save(rows)
            return updated

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
        if not _supabase_ready():
            return []
        import requests
        params: dict = {"select": "*", "order": "product_code.asc"}
        if store_id:
            params["store_id"] = f"eq.{store_id}"
        r = requests.get(self._url(), headers={**_headers(), "Accept": "application/json"}, params=params, timeout=45)
        if not r.ok:
            raise RuntimeError(f"store_status okunamadı: {r.status_code} {r.text}")
        return r.json()

    def upsert(self, rows: list[dict]) -> None:
        if not _supabase_ready() or not rows:
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
        """Supabase'den okunan veriyi store_inventory.json formatına çevirir."""
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
