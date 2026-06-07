"""
Sheet'teki green kayitlari Supabase product_store_status ile hizalar.

Kullanim:
  python3 vds/repair_store_status_from_sheet.py LoopRug
  python3 vds/repair_store_status_from_sheet.py --all

Davranis:
  - Secilen magazanin sheet'inden green urunleri okur
  - product_store_status icindeki green/done/needs_delete_ kayitlari okur
  - Sheet'te olup DB'de eksik olan kayitlari upsert eder
  - Istege bagli olarak DB'de fazla kalanlari temizler
"""

from __future__ import annotations

import argparse
import json
import os
import sys
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


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sheet green -> Supabase store_status onarimi")
    parser.add_argument("store_id", nargs="?", help="stores.json icindeki store_id")
    parser.add_argument("--all", action="store_true", help="Tum magazalari tara")
    parser.add_argument("--clear-extra", action="store_true", help="DB'de olup sheet green'de olmayanlari sil")
    return parser.parse_args(argv)


def _store_ids(args: argparse.Namespace) -> list[str]:
    if args.all:
        from shared.store_manager import tum_magazalar

        return [
            _clean(item.get("store_id"))
            for item in tum_magazalar()
            if _clean(item.get("store_id"))
        ]
    if not _clean(args.store_id):
        raise SystemExit("Hata: store_id verin veya --all kullanin.")
    return [_clean(args.store_id)]


def _sheet_green_codes(store_id: str) -> set[str]:
    from shared.sheets import SheetsKatmani

    renkler = SheetsKatmani(store_id).urun_renk_durumlari_al()
    codes = {
        _clean(code)
        for code, renk in (renkler or {}).items()
        if _clean(code) and _clean(renk).lower() == "green"
    }
    # "__row__:N" satir-numarasi placeholder anahtarlaridir, gercek urun kodu
    # degildir (bkz. shared/sheets.py urun_renk_durumlari_al). Bunlari sahte
    # kod olarak DB'ye yazmamak icin filtrele.
    placeholder = {c for c in codes if c.startswith("__row__:")}
    if placeholder:
        print(
            f"[uyari] {store_id}: {len(placeholder)} adet placeholder kod "
            f"(__row__:N) sheet renk haritasindan filtrelendi - gercek urun "
            f"kodu degil, atlandi: {sorted(placeholder)[:5]}{'...' if len(placeholder) > 5 else ''}",
            file=sys.stderr,
        )
    return codes - placeholder


def _db_active_codes(store_id: str) -> set[str]:
    """DB'de zaten green/done olan (gercekten yuklu/aktif) urun kodlari.

    needs_delete_* statusundeki satirlar burada SAYILMAZ: sheet'te green
    olarak goruluyorlarsa urun yeniden yuklenmis demektir ve stale
    needs_delete kaydinin uzerine green/done yazilarak guncellenmesi gerekir.
    """
    from shared.product_catalog import StoreCatalog

    rows = StoreCatalog().list_by_store(store_id)
    return {
        _clean(row.get("product_code"))
        for row in (rows or [])
        if _clean(row.get("product_code"))
        and (
            _clean(row.get("renk")).lower() == "green"
            or _clean(row.get("status")).lower() == "done"
        )
    }


def _upsert_missing(store_id: str, codes: list[str]) -> int:
    from shared.product_catalog import ProductCatalog, StoreCatalog

    if not codes:
        return 0

    # Guvenlik agi: placeholder/malformed kodlari asla gercek urun olarak yazma.
    safe_codes = [c for c in codes if not _clean(c).startswith("__row__:")]
    skipped = [c for c in codes if c not in safe_codes]
    if skipped:
        print(
            f"[uyari] {store_id}: {len(skipped)} adet placeholder/malformed kod "
            f"upsert'ten atlandi: {skipped[:5]}{'...' if len(skipped) > 5 else ''}",
            file=sys.stderr,
        )
    codes = safe_codes
    if not codes:
        return 0

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ProductCatalog().upsert_products([
        {
            "product_code": code,
            "status": "active",
            "updated_at": now_str,
        }
        for code in codes
    ])
    StoreCatalog().upsert([
        {
            "product_code": code,
            "store_id": store_id,
            "status": "done",
            "renk": "green",
            "islem_tarihi": now_str,
        }
        for code in codes
    ])
    return len(codes)


def _clear_extra(store_id: str, codes: list[str]) -> int:
    from shared.product_catalog import StoreCatalog

    if not codes:
        return 0
    return StoreCatalog().delete(store_id, codes)


def main(argv: list[str]) -> int:
    _load_env()
    args = parse_args(argv)

    rapor = []
    for store_id in _store_ids(args):
        sheet_codes = _sheet_green_codes(store_id)
        db_codes = _db_active_codes(store_id)
        missing = sorted(sheet_codes - db_codes)
        extra = sorted(db_codes - sheet_codes)

        upserted = _upsert_missing(store_id, missing)
        cleared = _clear_extra(store_id, extra) if args.clear_extra else 0
        rapor.append({
            "store_id": store_id,
            "sheet_green": len(sheet_codes),
            "db_loaded_before": len(db_codes),
            "missing_in_db": len(missing),
            "upserted": upserted,
            "extra_in_db": len(extra),
            "cleared": cleared,
            "missing_codes": missing,
            "extra_codes": extra,
        })

    print(json.dumps(rapor, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
