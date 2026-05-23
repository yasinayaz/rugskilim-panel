"""
Sheet'te basligi dolu ama aciklamasi bos kalan urunler icin description backfill araci.

Kullanim:
  python3 vds/backfill_blank_descriptions.py
  python3 vds/backfill_blank_descriptions.py RugsShopTurkey PatchArts
  python3 vds/backfill_blank_descriptions.py --default-template
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from shared.sheets import SheetsKatmani
from shared.store_manager import tum_magazalar


def main(argv: list[str]) -> int:
    args = list(argv[1:])
    default_template = False
    if "--default-template" in args:
        args.remove("--default-template")
        default_template = True

    hedef_magazalar = args or [str(s.get("store_id") or "").strip() for s in tum_magazalar() if str(s.get("store_id") or "").strip()]
    toplam = 0
    for store_id in hedef_magazalar:
        sonuc = SheetsKatmani(store_id).bos_aciklamalari_onar(default_template=default_template)
        print(f"{store_id}: {sonuc['adet']} aciklama onarildi")
        toplam += int(sonuc["adet"])
    print(f"TOPLAM: {toplam}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
