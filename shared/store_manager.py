"""
store_manager.py
Mağaza konfigürasyonlarını stores.json üzerinden yönetir.

stores.json alanları:
  store_id        – benzersiz tanımlayıcı (sheet sekme adıyla aynı olmalı)
  store_name      – görünen ad
  sheet_tab       – Google Sheets sekme başlığı
  google_sheet_id – null = GOOGLE_SHEET_ID env kullan; override için doldur
  price_per_m2    – bu mağazanın varsayılan m² fiyatı
  template        – streamlit/templates veya magaza klasorundeki template adi
  active          – VDS bu mağazayı işlesin mi
"""

import json
from pathlib import Path

_STORES_JSON = Path(__file__).parent / "stores.json"
_STORE_ID_ALIASES = {
    "IlmekRug": "İlmekRug",
    "ilmekrug": "İlmekRug",
}


def _validate_store(store: dict):
    store_id = str(store.get("store_id") or "").strip()
    sheet_tab = str(store.get("sheet_tab") or store_id).strip()
    if not store_id:
        raise ValueError("store_id zorunlu")
    if sheet_tab != store_id:
        raise ValueError("sheet_tab, panelde kullanilan store_id ile birebir ayni olmali")


def _yukle() -> dict:
    with open(_STORES_JSON, encoding="utf-8") as f:
        data = json.load(f)
    for store in data["stores"]:
        _validate_store(store)
    return {s["store_id"]: s for s in data["stores"]}


def _kaydet(stores_dict: dict):
    data = {"stores": list(stores_dict.values())}
    with open(_STORES_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _resolve_store_id(store_id: str) -> str:
    raw = str(store_id or "").strip()
    if not raw:
        return raw
    return _STORE_ID_ALIASES.get(raw, raw)


def get_store(store_id: str) -> dict:
    stores = _yukle()
    store_id = _resolve_store_id(store_id)
    if store_id not in stores:
        raise ValueError(f"Mağaza bulunamadı: '{store_id}'. Mevcut: {list(stores)}")
    return stores[store_id]


def tum_magazalar() -> list:
    return list(_yukle().values())


def aktif_magazalar() -> list:
    return [s for s in _yukle().values() if s.get("active")]


def magaza_ekle(store: dict):
    """Yeni mağaza ekler. sheet_tab zorunlu."""
    _validate_store(store)
    stores = _yukle()
    if store["store_id"] in stores:
        raise ValueError(f"'{store['store_id']}' zaten mevcut")
    stores[store["store_id"]] = {
        "store_id":       store["store_id"],
        "store_name":     store.get("store_name", store["store_id"]),
        "sheet_tab":      store.get("sheet_tab", store["store_id"]),
        "google_sheet_id": store.get("google_sheet_id"),
        "price_per_m2":   store.get("price_per_m2", 300),
        "template":       store.get("template", "default_v1"),
        "active":         store.get("active", False),
    }
    _kaydet(stores)


def magaza_guncelle(store_id: str, guncellemeler: dict):
    stores = _yukle()
    store_id = _resolve_store_id(store_id)
    if store_id not in stores:
        raise ValueError(f"Mağaza bulunamadı: '{store_id}'")
    guncel = dict(stores[store_id])
    guncel.update(guncellemeler)
    _validate_store(guncel)
    stores[store_id] = guncel
    _kaydet(stores)
