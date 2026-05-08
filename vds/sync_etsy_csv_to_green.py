"""
Etsy listing CSV'sindeki SKU / TITLE / DESCRIPTION / TAGS alanlarini ilgili
magazanin sheet'ine yazar, gerekirse yeni satir acar ve A sutunundaki hucreleri
green yapar.

Kullanim:
  python3 vds/sync_etsy_csv_to_green.py LoomAntikRugs "/path/EtsyListingsDownload.csv"

Opsiyonel:
  --clear-missing-green
    CSV'de olmayan ama sheet'te green olan urunlerin yesilini temizler.
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import sys
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
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key, value)


def _store_aliases(store_id: str) -> list[str]:
    raw = re.sub(r"[^a-z]", "", str(store_id or "").lower())
    aliases = {raw}
    for suffix in ("rugs", "rug", "shop", "house", "llc", "turkey"):
        if raw.endswith(suffix) and len(raw) > len(suffix):
            aliases.add(raw[: -len(suffix)])
    return sorted(a for a in aliases if a)


def _urun_id_normallestir(raw_sku: str, store_id: str) -> str:
    sku = str(raw_sku or "").strip()
    if not sku:
        return ""

    compact = re.sub(r"\s+", " ", sku).strip()
    lowered = compact.lower()

    for alias in _store_aliases(store_id):
        if lowered == alias:
            return ""
        if lowered.startswith(alias + " "):
            compact = compact[len(alias):].strip()
            lowered = compact.lower()
            break

    compact = re.sub(r"\s+", " ", compact).strip()

    # "E 139" -> "E139", "RST 2029 extra" -> "RST2029", "3810 i" -> "3810"
    alpha_num = re.match(r"^([A-Za-z]{1,5})\s*(\d+)\b", compact)
    if alpha_num:
        return f"{alpha_num.group(1)}{alpha_num.group(2)}"

    numeric = re.match(r"^(\d+)\b", compact)
    if numeric:
        return numeric.group(1)

    return compact.strip()


def _csv_kayitlari(csv_path: Path, store_id: str) -> list[dict]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        rows = csv.DictReader(f)
        kayitlar = []
        seen = set()
        for row in rows:
            sku = _urun_id_normallestir(row.get("SKU") or "", store_id)
            if not sku or sku in seen:
                continue
            seen.add(sku)
            kayitlar.append({
                "urun_id": sku,
                "baslik": str(row.get("TITLE") or "").strip(),
                "aciklama": str(row.get("DESCRIPTION") or "").strip(),
                "taglar_virgul": str(row.get("TAGS") or "").strip(),
            })
        return kayitlar


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Etsy CSV SKU'larini green isaretler.")
    parser.add_argument("store_id", help="stores.json icindeki magaza ID'si")
    parser.add_argument("csv_path", help="Etsy listings export CSV yolu")
    parser.add_argument(
        "--clear-missing-green",
        action="store_true",
        help="CSV'de olmayan mevcut green urunlerin yesilini temizle",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    _load_env()

    csv_path = Path(args.csv_path).expanduser().resolve()
    if not csv_path.exists():
        print(f"Hata: CSV bulunamadi: {csv_path}", file=sys.stderr)
        return 1

    kayitlar = _csv_kayitlari(csv_path, args.store_id)
    if not kayitlar:
        print("Hata: CSV icinde SKU bulunamadi.", file=sys.stderr)
        return 1

    from shared.sheets import SheetsKatmani

    sk = SheetsKatmani(args.store_id)
    sk.sheet_hazirla()
    renk_durumlari = sk.urun_renk_durumlari_al()
    sonuc = sk.etsy_csv_kayitlarini_isle(kayitlar, renk="green", durum="done")
    sku_ids = {k["urun_id"] for k in kayitlar}
    print(f"store_id={args.store_id}")
    print(f"csv_sku={len(sku_ids)}")
    print(f"eklenen={sonuc['eklenen']}")
    print(f"alan_guncellenen={sonuc['guncellenen']}")
    print(f"green_yapilan={sonuc['renk_guncellenen']}")
    print(f"sheette_bulunamayan={len(sonuc['bulunamayan'])}")
    if sonuc["bulunamayan"]:
        print("bulunamayan_sku=" + ",".join(sorted(sonuc["bulunamayan"])))

    if args.clear_missing_green:
        mevcut_green = {
            str(urun_id).strip()
            for urun_id, renk in renk_durumlari.items()
            if renk == "green"
        }
        temizlenecek = sorted(mevcut_green - sku_ids)
        temiz_sonuc = sk.urun_renklerini_temizle(temizlenecek)
        print(f"green_temizlenen={temiz_sonuc['guncellenen']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
