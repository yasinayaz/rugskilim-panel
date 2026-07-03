"""
product_catalog.py
Supabase uzerinden panel urun stok yonetimi.
"""

from __future__ import annotations

import os
import re
import threading
from datetime import datetime

import requests
from requests.adapters import HTTPAdapter

_SESSION: requests.Session | None = None
_SESSION_LOCK = threading.Lock()


def _session() -> requests.Session:
    """Supabase REST istekleri icin paylasilan, keep-alive'li bir Session dondurur.

    Her cagrida yeni _session().get(...) acmak TCP+TLS handshake'i tekrarlatiyordu;
    ayni process icindeki tum threadler (Streamlit oturumlari) bu tek Session'i
    paylasarak baglanti havuzunu yeniden kullanir.
    """
    global _SESSION
    if _SESSION is None:
        with _SESSION_LOCK:
            if _SESSION is None:
                session = requests.Session()
                adapter = HTTPAdapter(pool_connections=20, pool_maxsize=20)
                session.mount("https://", adapter)
                session.mount("http://", adapter)
                _SESSION = session
    return _SESSION

SUPABASE_URL_ENV = "SUPABASE_URL"
SUPABASE_SERVICE_KEY_ENV = "SUPABASE_SERVICE_ROLE_KEY"
SUPABASE_PRODUCTS_TABLE_ENV = "SUPABASE_PRODUCTS_TABLE"
DEFAULT_PRODUCTS_TABLE = "products"
CATEGORY_DOORMAT_MAX_AREA_M2 = 0.59
CATEGORY_RUNNER_RATIO = 3.0
CM_PER_FOOT = 30.48
OPTIONAL_PRODUCT_FIELDS = {
    "loaded_store_count",
    "loaded_stores",
    "sold_site",
    "customer_name",
    "customer_phone",
    "customer_address",
    "customer_contact_country",
}


def _env(name: str) -> str:
    return os.environ.get(name, "").strip()


def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _clean(value) -> str:
    return str(value or "").strip()


def _to_float(value):
    try:
        if value in ("", None):
            return None
        return float(str(value).replace(",", "."))
    except Exception:
        return None


def _size_parts(size: str) -> tuple[float | None, float | None]:
    text = _clean(size).replace(",", ".").lower()
    if "x" not in text:
        return None, None
    left, right = text.split("x", 1)
    return _to_float(left), _to_float(right)


def cm_to_ft_value(cm) -> float | None:
    value = _to_float(cm)
    if value is None or value <= 0:
        return None
    return value / CM_PER_FOOT


def derive_category(width_ft=None, length_ft=None, area_m2=None, source_tab: str = "") -> str:
    tab = _clean(source_tab).upper()
    area_value = _to_float(area_m2)
    if area_value is not None and area_value < CATEGORY_DOORMAT_MAX_AREA_M2:
        return "Doormat"
    if tab.startswith("DOOR"):
        return "Doormat"

    short_edge = min(v for v in [_to_float(width_ft), _to_float(length_ft)] if v and v > 0) if any(
        v and v > 0 for v in [_to_float(width_ft), _to_float(length_ft)]
    ) else None
    long_edge = max(v for v in [_to_float(width_ft), _to_float(length_ft)] if v and v > 0) if any(
        v and v > 0 for v in [_to_float(width_ft), _to_float(length_ft)]
    ) else None
    if short_edge and long_edge and (long_edge / short_edge) >= CATEGORY_RUNNER_RATIO:
        return "Runner"
    if short_edge and long_edge:
        return "Area"
    return ""


def derive_category_from_dimensions(
    width_cm=None,
    length_cm=None,
    width_ft=None,
    length_ft=None,
    area_m2=None,
    source_tab: str = "",
) -> str:
    width_ft_value = _to_float(width_ft)
    length_ft_value = _to_float(length_ft)
    if width_ft_value is None:
        width_ft_value = cm_to_ft_value(width_cm)
    if length_ft_value is None:
        length_ft_value = cm_to_ft_value(length_cm)

    area_value = _to_float(area_m2)
    width_cm_value = _to_float(width_cm)
    length_cm_value = _to_float(length_cm)
    if area_value is None and width_cm_value and length_cm_value:
        area_value = (width_cm_value * length_cm_value) / 10000

    return derive_category(
        width_ft=width_ft_value,
        length_ft=length_ft_value,
        area_m2=area_value,
        source_tab=source_tab,
    )


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


def _schema_missing_column(response_text: str) -> str | None:
    match = re.search(r"'([^']+)' column", response_text or "")
    if match:
        return match.group(1)
    return None


def list_sold_product_codes() -> set[str]:
    """Supabase'den sadece status=sold olan urunlerin product_code'larini ceker."""
    codes: set[str] = set()
    page_size = 1000
    offset = 0
    while True:
        response = _session().get(
            _rest_url(),
            headers={**_headers(), "Accept": "application/json", "Range-Unit": "items", "Range": f"{offset}-{offset + page_size - 1}"},
            params={"select": "product_code", "status": "eq.sold", "order": "product_code.asc"},
            timeout=30,
        )
        if not response.ok:
            raise RuntimeError(f"Supabase sold kodlari okunamadi: {response.status_code} {response.text}")
        page = response.json()
        for row in page:
            code = _clean(row.get("product_code"))
            if code:
                codes.add(code)
        if len(page) < page_size:
            break
        offset += page_size
    return codes


class ProductCatalog:
    def list_products(self, include_store_presence: bool = False) -> list[dict]:
        products = []
        page_size = 1000
        offset = 0
        while True:
            response = _session().get(
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

        if include_store_presence:
            # Bu ek tarama binlerce store_status satiri oldugunda pahali oldugu icin
            # varsayilan olarak kapali tutulur; urun listesi tek API ile acilsin.
            try:
                store_rows = []
                s_offset = 0
                while True:
                    page = _session().get(
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

    def list_products_by_codes(self, product_codes: list[str]) -> list[dict]:
        codes = sorted({_clean(code) for code in (product_codes or []) if _clean(code)})
        if not codes:
            return []

        products = []
        chunk_size = 200
        for start in range(0, len(codes), chunk_size):
            chunk = codes[start:start + chunk_size]
            response = _session().get(
                _rest_url(),
                headers={**_headers(), "Accept": "application/json"},
                params={
                    "select": "*",
                    "product_code": f"in.({','.join(chunk)})",
                    "order": "product_code.asc",
                },
                timeout=45,
            )
            if not response.ok:
                raise RuntimeError(f"Supabase ürünleri okunamadı: {response.status_code} {response.text}")
            products.extend(response.json() or [])
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

        headers = {
            **_headers(),
            "Prefer": "resolution=merge-duplicates,return=representation",
        }
        dropped_fields = set()
        while True:
            request_payload = [
                {k: v for k, v in row.items() if k not in dropped_fields}
                for row in payload
            ]
            response = _session().post(
                _rest_url(),
                headers=headers,
                params={"on_conflict": "product_code"},
                json=request_payload,
                timeout=60,
            )
            if response.ok:
                return response.json()

            missing_column = _schema_missing_column(response.text)
            if missing_column and missing_column in OPTIONAL_PRODUCT_FIELDS and missing_column not in dropped_fields:
                dropped_fields.add(missing_column)
                continue

            raise RuntimeError(f"Supabase ürün upsert başarısız: {response.status_code} {response.text}")

    def replace_from_source(self, source_products: list[dict]) -> list[dict]:
        existing = self.list_products()
        existing_map = {
            _clean(item.get("product_code")): dict(item)
            for item in existing
            if _clean(item.get("product_code"))
        }
        merged = []
        merged_codes: set[str] = set()

        for source in source_products:
            code = _clean(source.get("product_code"))
            if not code:
                continue
            current = existing_map.get(code, {})
            merged_codes.add(code)
            merged.append({
                "product_id": current.get("product_id") or source.get("product_id"),
                "product_code": code,
                "category": source.get("category") or current.get("category") or "",
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
                "sold_at": source.get("sold_at") or current.get("sold_at") or "",
                "sold_site": source.get("sold_site") or current.get("sold_site") or "",
                "customer_name": source.get("customer_name") or current.get("customer_name") or "",
                "customer_phone": source.get("customer_phone") or current.get("customer_phone") or "",
                "customer_address": source.get("customer_address") or current.get("customer_address") or "",
                "customer_contact_country": source.get("customer_contact_country") or current.get("customer_contact_country") or "",
                "note": source.get("note") or current.get("note") or "",
                "updated_at": _now_str(),
            })

        for code, current in existing_map.items():
            if code in merged_codes:
                continue
            if _clean(current.get("source_tab")).lower() == "manual" or _clean(current.get("status")).lower() == "sold":
                current["updated_at"] = _now_str()
                merged.append(current)

        return self.upsert_products(merged)

    def mark_sold(self, product_code: str) -> dict | None:
        code = _clean(product_code)
        if not code:
            return None

        response = _session().patch(
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

    def sell_product(
        self,
        product_code: str,
        *,
        sold_at: str | None = None,
        sold_site: str | None = None,
        customer_name: str | None = None,
        customer_phone: str | None = None,
        customer_address: str | None = None,
        customer_contact_country: str | None = None,
        note: str | None = None,
    ) -> dict | None:
        """Ürünü satıldı olarak işaretle ve müşteri bilgilerini güncelle (PATCH)."""
        code = _clean(product_code)
        if not code:
            return None

        payload: dict = {
            "status": "sold",
            "sold_at": sold_at or _now_str(),
            "updated_at": _now_str(),
        }
        if sold_site is not None:
            payload["sold_site"] = sold_site
        if customer_name is not None:
            payload["customer_name"] = customer_name
        if customer_phone is not None:
            payload["customer_phone"] = customer_phone
        if customer_address is not None:
            payload["customer_address"] = customer_address
        if customer_contact_country is not None:
            payload["customer_contact_country"] = customer_contact_country
        if note is not None:
            payload["note"] = note

        response = _session().patch(
            _rest_url(),
            headers={**_headers(), "Prefer": "return=representation"},
            params={"product_code": f"eq.{code}"},
            json=payload,
            timeout=45,
        )
        if not response.ok:
            raise RuntimeError(
                f"Supabase satış güncellemesi başarısız: {response.status_code} {response.text}"
            )
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

    def delete_products(self, product_codes: list[str]) -> int:
        codes = sorted({_clean(code) for code in product_codes if _clean(code)})
        if not codes:
            return 0

        deleted = 0
        chunk_size = 200
        for start in range(0, len(codes), chunk_size):
            chunk = codes[start:start + chunk_size]
            code_filter = ",".join(chunk)
            response = _session().delete(
                _rest_url(),
                headers={**_headers(), "Prefer": "return=representation"},
                params={"product_code": f"in.({code_filter})"},
                timeout=60,
            )
            if not response.ok:
                raise RuntimeError(f"Supabase ürün silme başarısız: {response.status_code} {response.text}")
            try:
                deleted += len(response.json() or [])
            except Exception:
                deleted += len(chunk)
        return deleted


SUPABASE_STORE_TABLE = "product_store_status"


class StoreCatalog:
    def _url(self) -> str:
        return f"{_base_url()}/rest/v1/{SUPABASE_STORE_TABLE}"

    def list_by_store(self, store_id: str | None = None) -> list[dict]:
        rows = []
        page_size = 1000
        offset = 0
        while True:
            params: dict = {"select": "*", "order": "product_code.asc"}
            if store_id:
                params["store_id"] = f"eq.{store_id}"
            r = _session().get(
                self._url(),
                headers={
                    **_headers(),
                    "Accept": "application/json",
                    "Range-Unit": "items",
                    "Range": f"{offset}-{offset + page_size - 1}",
                },
                params=params,
                timeout=45,
            )
            if not r.ok:
                raise RuntimeError(f"store_status okunamadı: {r.status_code} {r.text}")
            page = r.json()
            rows.extend(page)
            if len(page) < page_size:
                break
            offset += page_size
        return rows

    def upsert(self, rows: list[dict]) -> None:
        if not rows:
            return
        r = _session().post(
            self._url(),
            headers={**_headers(), "Prefer": "resolution=merge-duplicates,return=minimal"},
            params={"on_conflict": "product_code,store_id"},
            json=[{k: v for k, v in row.items() if k != "updated_at"} for row in rows],
            timeout=60,
        )
        if not r.ok:
            raise RuntimeError(f"store_status upsert başarısız: {r.status_code} {r.text}")

    def delete(self, store_id: str, product_codes: list[str] | None = None) -> int:
        sid = _clean(store_id)
        if not sid:
            return 0

        deleted = 0
        if not product_codes:
            response = _session().delete(
                self._url(),
                headers={**_headers(), "Prefer": "return=representation"},
                params={"store_id": f"eq.{sid}"},
                timeout=60,
            )
            if not response.ok:
                raise RuntimeError(f"store_status silme başarısız: {response.status_code} {response.text}")
            try:
                return len(response.json() or [])
            except Exception:
                return 0

        codes = sorted({_clean(code) for code in product_codes if _clean(code)})
        chunk_size = 200
        for start in range(0, len(codes), chunk_size):
            chunk = codes[start:start + chunk_size]
            code_filter = ",".join(chunk)
            response = _session().delete(
                self._url(),
                headers={**_headers(), "Prefer": "return=representation"},
                # needs_delete_deleted kayıtlar sheet temizlemesinden korunur — panelde görünmeleri gerekir
                params={"store_id": f"eq.{sid}", "product_code": f"in.({code_filter})", "status": "neq.needs_delete_deleted"},
                timeout=60,
            )
            if not response.ok:
                raise RuntimeError(f"store_status silme başarısız: {response.status_code} {response.text}")
            try:
                deleted += len(response.json() or [])
            except Exception:
                deleted += len(chunk)
        return deleted

    def as_inventory_cache(self) -> dict:
        def _row_is_loaded(row: dict) -> bool:
            renk = _clean(row.get("renk")).lower()
            durum = _clean(row.get("status")).lower()
            if renk in {"red", "yellow"}:
                return False
            if durum in {"deleted", "removed"}:
                return False
            if durum.startswith("needs_delete_"):
                return True
            return renk == "green" or durum == "done"

        rows = self.list_by_store()
        stores: dict = {}
        for row in rows:
            sid = row.get("store_id", "")
            code = row.get("product_code", "")
            if not sid or not code:
                continue
            if not _row_is_loaded(row):
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
    """'2,3x7' veya '2.3x7' gibi WxL formatından Runner/Area döndürür."""
    width, length = _size_parts(size)
    return derive_category(width_ft=width, length_ft=length)
