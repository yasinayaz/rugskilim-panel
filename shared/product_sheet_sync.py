"""
Supabase -> urun sheet senkronizasyonu.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from pathlib import Path

from shared.product_catalog import ProductCatalog, _supabase_ready
from shared.product_sheet import ProductSheet

_ROOT_DIR = Path(__file__).resolve().parent.parent
_RUNTIME_DIR = _ROOT_DIR / ".runtime" / "shared"
_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
_SYNC_STATE_PATH = _RUNTIME_DIR / "product_sheet_sync.json"
_SYNC_LOCK = threading.Lock()
_WORKER_LOCK = threading.Lock()
_WORKER_THREAD: threading.Thread | None = None


def _load_state() -> dict:
    try:
        return json.loads(_SYNC_STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_state(state: dict) -> None:
    _SYNC_STATE_PATH.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _fingerprint_rows(rows: list[dict]) -> str:
    payload = json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _clean(value) -> str:
    return str(value or "").strip()


def _now_str() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _product_id_for_code(code: str) -> str:
    return f"PRD-{_clean(code).upper()}"


def sync_supabase_from_product_sheet(force: bool = False) -> bool:
    if not _supabase_ready():
        return False

    with _SYNC_LOCK:
        state = _load_state()
        sheet_rows = ProductSheet().read_products()
        sheet_fingerprint = _fingerprint_rows(sheet_rows)
        if not force and state.get("last_sheet_fingerprint") == sheet_fingerprint:
            return False

        catalog = ProductCatalog()
        current_rows = catalog.list_products()
        current_map = {
            _clean(item.get("product_code")): dict(item)
            for item in current_rows
            if _clean(item.get("product_code"))
        }

        sold_codes = {
            _clean(item.get("product_code"))
            for item in sheet_rows
            if _clean(item.get("product_code")) and _clean(item.get("status")).lower() == "sold"
        }

        upserts: list[dict] = []
        missing_sold_codes: list[str] = []

        for row in sheet_rows:
            code = _clean(row.get("product_code"))
            if not code:
                continue
            current = dict(current_map.get(code, {}))
            status = _clean(row.get("status")).lower() or "active"

            if status == "sold":
                if not current:
                    missing_sold_codes.append(code)
                    continue
                current.update({
                    "status": "sold",
                    "sold_site": _clean(row.get("sold_site")) or _clean(current.get("sold_site")),
                    "sold_at": _clean(row.get("sold_at")) or _clean(current.get("sold_at")) or _now_str(),
                    "updated_at": _now_str(),
                })
                upserts.append(current)
                continue

            if _clean(current.get("status")).lower() == "sold" and code not in sold_codes:
                # Aktif tablara kopyalanan satilan urunler yanlislikla re-activate olmasin.
                continue

            current.update({
                "product_id": _clean(current.get("product_id")) or _product_id_for_code(code),
                "product_code": code,
                "category": _clean(row.get("category")) or _clean(current.get("category")) or _clean(row.get("source_tab")),
                "width_cm": _clean(row.get("width_cm")) or _clean(current.get("width_cm")),
                "length_cm": _clean(row.get("length_cm")) or _clean(current.get("length_cm")),
                "size_cm": _clean(row.get("size_cm")) or _clean(current.get("size_cm")),
                "area_m2": _clean(row.get("area_m2")) or _clean(current.get("area_m2")),
                "width_ft": _clean(row.get("width_ft")) or _clean(current.get("width_ft")),
                "length_ft": _clean(row.get("length_ft")) or _clean(current.get("length_ft")),
                "size_ft": _clean(row.get("size_ft")) or _clean(current.get("size_ft")),
                "status": "active",
                "source_tab": _clean(row.get("source_tab")) or _clean(current.get("source_tab")) or "manual",
                "source_row": _clean(row.get("source_row")) or _clean(current.get("source_row")),
                "loaded_store_count": _clean(row.get("loaded_store_count")) or _clean(current.get("loaded_store_count")),
                "loaded_stores": _clean(row.get("loaded_stores")) or _clean(current.get("loaded_stores")),
                "sold_at": _clean(current.get("sold_at")) if _clean(current.get("status")).lower() == "sold" else "",
                "sold_site": _clean(current.get("sold_site")) if _clean(current.get("status")).lower() == "sold" else "",
                "updated_at": _clean(row.get("updated_at")) or _now_str(),
            })
            upserts.append(current)

        if upserts:
            catalog.upsert_products(upserts)

        report = {
            "updated_at": _now_str(),
            "sheet_row_count": len(sheet_rows),
            "upsert_count": len(upserts),
            "missing_sold_codes": missing_sold_codes,
        }
        _save_state({
            **state,
            "last_sheet_fingerprint": sheet_fingerprint,
            "last_import_report": report,
        })
        return bool(upserts or missing_sold_codes)


def sync_product_sheet(force: bool = False, products: list[dict] | None = None, throttle_seconds: int = 45) -> bool:
    """
    Supabase'teki mevcut urunleri kategori sheet'ine aynalar.
    force=False iken kisa aralikli tekrar yazimlari throttle eder.
    """
    if not _supabase_ready():
        return False

    now = time.time()
    state = _load_state()
    last_synced_at = float(state.get("last_synced_at") or 0)
    if not force and throttle_seconds > 0 and (now - last_synced_at) < throttle_seconds:
        return False

    with _SYNC_LOCK:
        state = _load_state()
        rows = products if products is not None else ProductCatalog().list_products()
        fingerprint = _fingerprint_rows(rows)
        if state.get("last_fingerprint") == fingerprint:
            _save_state({
                **state,
                "last_synced_at": now,
                "product_count": len(rows),
                "last_fingerprint": fingerprint,
            })
            return False
        ProductSheet().write_products(rows)
        _save_state({
            "last_synced_at": now,
            "product_count": len(rows),
            "last_fingerprint": fingerprint,
        })
        return True


def _worker_loop(interval_seconds: int) -> None:
    while True:
        try:
            sync_supabase_from_product_sheet(force=False)
        except Exception:
            pass
        try:
            sync_product_sheet(force=True)
        except Exception:
            pass
        time.sleep(max(5, int(interval_seconds)))


def start_product_sheet_sync_worker(interval_seconds: int = 30) -> bool:
    global _WORKER_THREAD
    if not _supabase_ready():
        return False

    with _WORKER_LOCK:
        if _WORKER_THREAD is not None and _WORKER_THREAD.is_alive():
            return False
        _WORKER_THREAD = threading.Thread(
            target=_worker_loop,
            args=(interval_seconds,),
            daemon=True,
            name="product-sheet-sync",
        )
        _WORKER_THREAD.start()
        return True
