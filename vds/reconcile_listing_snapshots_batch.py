"""
Birden fazla Etsy export CSV'sini magazalara eslestirip:
  - ilgili sheet tab'larinda yuklu urunleri son CSV'ye gore uzlastirir
  - CSV'de olmayan eski green kayitlari temizler
  - Supabase product_store_status tarafinda CSV disi kayitlari siler
  - magaza ici ve magazalar arasi tekrarlayan SKU raporu uretir
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


sys.path.insert(0, str(_repo_root()))


def _normalize(text: str) -> str:
    text = str(text or "").strip().lower()
    text = "".join(
        ch for ch in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(ch)
    )
    text = re.sub(r"\.csv$", "", text)
    text = re.sub(r"[\s_-]+", "", text)
    text = re.sub(r"\d+$", "", text)
    return text


def _load_store_ids() -> list[str]:
    data = json.loads((_repo_root() / "shared" / "stores.json").read_text(encoding="utf-8"))
    return [str(item["store_id"]) for item in data["stores"]]


def _store_candidates() -> dict[str, str]:
    candidates = {}
    for store_id in _load_store_ids():
        key = _normalize(store_id)
        candidates[key] = store_id
        candidates[_normalize(store_id.replace("Rugs", "Rug"))] = store_id
        candidates[_normalize(store_id.replace("Rug", "Rugs"))] = store_id
    manual = {
        "bohorughouse": "BohoRugHouse",
        "ilmekrugs": "İlmekRug",
        "ilmekrug": "İlmekRug",
        "loomix": "LoomixRugs",
        "looprug": "LoopRug",
        "oldnewrugs": "OldNewRugs",
        "rugsshopturkey": "RugsShopTurkey",
        "woolcottonrugs": "WoolCottonRugs",
        "wovenloomrugs": "WovenLoomRugs",
        "woventurkishrug": "WovenTurkishRugs",
        "woventurkishrugs": "WovenTurkishRugs",
        "rugskilimllc": "RugsKilimLLC",
    }
    candidates.update(manual)
    return candidates


def _match_store(csv_path: Path) -> str | None:
    return _store_candidates().get(_normalize(csv_path.name))


def _sku_set(csv_path: Path, store_id: str) -> tuple[list[str], list[str]]:
    from vds.import_etsy_listing_snapshot import _csv_kayitlari

    kayitlar = _csv_kayitlari(csv_path, store_id)
    sku_list = [str(item.get("urun_id") or "").strip() for item in kayitlar if str(item.get("urun_id") or "").strip()]

    import csv
    raw_seen = []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            raw = str(row.get("SKU") or "").strip()
            if raw:
                raw_seen.append(raw)
    raw_counts = Counter(raw_seen)
    raw_dupes = sorted([sku for sku, count in raw_counts.items() if count > 1])
    return sku_list, raw_dupes


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="CSV snapshot batch uzlastirma")
    parser.add_argument("csv_paths", nargs="+", help="Etsy export CSV dosyalari")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    repo_root = _repo_root()

    eslesmeler: list[tuple[str, Path]] = []
    eslesmeyen: list[str] = []
    store_to_skus: dict[str, list[str]] = {}
    store_to_internal_dupes: dict[str, list[str]] = {}

    for raw_path in args.csv_paths:
        csv_path = Path(raw_path).expanduser().resolve()
        if not csv_path.exists():
            print(f"Eksik dosya: {csv_path}", file=sys.stderr)
            return 1
        store_id = _match_store(csv_path)
        if not store_id:
            eslesmeyen.append(csv_path.name)
            continue
        eslesmeler.append((store_id, csv_path))
        sku_list, raw_dupes = _sku_set(csv_path, store_id)
        store_to_skus[store_id] = sku_list
        store_to_internal_dupes[store_id] = raw_dupes

    if eslesmeyen:
        print("Eslesmeyen dosyalar:", ", ".join(eslesmeyen), file=sys.stderr)
        return 2

    cross_store_map: dict[str, list[str]] = defaultdict(list)
    for store_id, sku_list in store_to_skus.items():
        for sku in sorted(set(sku_list)):
            cross_store_map[sku].append(store_id)
    cross_store_dupes = {
        sku: sorted(stores)
        for sku, stores in cross_store_map.items()
        if len(stores) > 1
    }

    import_script = repo_root / "vds" / "import_etsy_listing_snapshot.py"
    run_results = []
    for store_id, csv_path in eslesmeler:
        cmd = [sys.executable, str(import_script), store_id, str(csv_path)]
        proc = subprocess.run(cmd, cwd=repo_root, text=True, capture_output=True)
        run_results.append({
            "store_id": store_id,
            "csv_path": str(csv_path),
            "returncode": proc.returncode,
            "stdout": proc.stdout.strip(),
            "stderr": proc.stderr.strip(),
        })
        if proc.returncode != 0:
            print(proc.stdout)
            print(proc.stderr, file=sys.stderr)
            return proc.returncode

    print("=== MAGAZA OZET ===")
    for item in run_results:
        print(f"[{item['store_id']}] {item['csv_path']}")
        print(item["stdout"])
        if item["stderr"]:
            print(item["stderr"])

    print("=== MAGAZA ICI TEKRARLI SKU ===")
    any_internal = False
    for store_id in sorted(store_to_internal_dupes):
        dupes = store_to_internal_dupes[store_id]
        if not dupes:
            continue
        any_internal = True
        print(f"{store_id}: {', '.join(dupes)}")
    if not any_internal:
        print("Yok")

    print("=== MAGAZALAR ARASI TEKRARLI SKU ===")
    if not cross_store_dupes:
        print("Yok")
    else:
        for sku in sorted(cross_store_dupes):
            print(f"{sku}: {', '.join(cross_store_dupes[sku])}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
