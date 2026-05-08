"""
Birden fazla Etsy CSV export dosyasini magaza bazli tek komutta isler.

Kullanim:
  python3 vds/import_store_csv_batch.py /path/BohoRugHouse.csv /path/LoomixRugs.csv

Kural:
  - store_id, dosya adinin uzantisiz hali kabul edilir
  - store_id ile stores.json icindeki kimlik birebir eslesmelidir
  - her magaza kendi sheet sekmesinde batch update ile islenir
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Birden fazla Etsy CSV export dosyasini import eder.")
    parser.add_argument("csv_paths", nargs="+", help="Import edilecek CSV dosya yollari")
    parser.add_argument(
        "--clear-missing-green",
        action="store_true",
        help="Her CSV icin sheet'te olup CSV'de olmayan green kayitlari temizle",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    repo_root = Path(__file__).resolve().parent.parent
    sync_script = repo_root / "vds" / "sync_etsy_csv_to_green.py"

    exit_code = 0
    for raw_path in args.csv_paths:
        csv_path = Path(raw_path).expanduser().resolve()
        store_id = csv_path.stem
        cmd = [sys.executable, str(sync_script), store_id, str(csv_path)]
        if args.clear_missing_green:
            cmd.append("--clear-missing-green")

        print(f"\n=== {store_id} ===")
        sonuc = subprocess.run(cmd, cwd=repo_root)
        if sonuc.returncode != 0:
            exit_code = sonuc.returncode

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
