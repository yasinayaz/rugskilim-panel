"""
Public Etsy shop pagesinden listing ID'lerini toplar.

Kullanim:
  python3 vds/etsy_shop_listing_ids.py https://www.etsy.com/shop/LoopRug
  python3 vds/etsy_shop_listing_ids.py LoopRug --csv looprug_listing_ids.csv

Not:
  - Public shop sayfasindan genelde seller SKU'su degil, Etsy listing_id cekilebilir.
  - Script sayfalari page=1..N seklinde gezer ve /listing/<id>/ pattern'lerini toplar.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import requests


USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

LISTING_RE = re.compile(r"/listing/(\d+)(?:/|\?|\"|')")
SHOP_NAME_RE = re.compile(r"/shop/([^/?#]+)")
COUNT_RE = re.compile(r"All\s*\(([\d,]+)\)")


@dataclass
class ListingRecord:
    listing_id: str
    page: int
    url: str


def _normalize_shop_input(shop: str) -> str:
    if shop.startswith(("http://", "https://")):
        return shop
    return f"https://www.etsy.com/shop/{shop.strip('/')}"


def _shop_name_from_url(url: str) -> str:
    match = SHOP_NAME_RE.search(url)
    if not match:
        raise ValueError(f"Magaza adi anlasilamadi: {url}")
    return match.group(1)


def _with_page(url: str, page: int) -> str:
    parsed = urlparse(url)
    query = parse_qs(parsed.query, keep_blank_values=True)
    query["page"] = [str(page)]
    new_query = urlencode(query, doseq=True)
    return urlunparse(parsed._replace(query=new_query))


def _extract_total_count(html: str) -> int | None:
    match = COUNT_RE.search(html)
    if not match:
        return None
    return int(match.group(1).replace(",", ""))


def _extract_listing_ids(html: str) -> list[str]:
    return list(dict.fromkeys(LISTING_RE.findall(html)))


def iter_shop_listing_ids(
    shop_url: str,
    *,
    cookie: str | None = None,
    delay_seconds: float = 0.4,
    timeout: int = 30,
    max_pages: int = 300,
) -> tuple[list[ListingRecord], int | None]:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"})
    if cookie:
        session.headers["Cookie"] = cookie

    records: list[ListingRecord] = []
    seen: set[str] = set()
    empty_streak = 0
    total_count: int | None = None

    for page in range(1, max_pages + 1):
        url = _with_page(shop_url, page)
        response = session.get(url, timeout=timeout)
        response.raise_for_status()
        html = response.text

        if total_count is None:
            total_count = _extract_total_count(html)

        page_ids = _extract_listing_ids(html)
        new_ids = [listing_id for listing_id in page_ids if listing_id not in seen]

        for listing_id in new_ids:
            seen.add(listing_id)
            records.append(
                ListingRecord(
                    listing_id=listing_id,
                    page=page,
                    url=f"https://www.etsy.com/listing/{listing_id}",
                )
            )

        if not new_ids:
            empty_streak += 1
        else:
            empty_streak = 0

        if total_count is not None and len(seen) >= total_count:
            break
        if empty_streak >= 2:
            break

        time.sleep(delay_seconds)

    return records, total_count


def write_csv(path: Path, records: Iterable[ListingRecord]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["listing_id", "page", "url"])
        writer.writeheader()
        for record in records:
            writer.writerow(
                {
                    "listing_id": record.listing_id,
                    "page": record.page,
                    "url": record.url,
                }
            )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Public Etsy shop'tan listing ID toplar.")
    parser.add_argument("shop", help="Magaza adi veya tam Etsy shop URL'si")
    parser.add_argument("--csv", dest="csv_path", help="CSV cikti yolu")
    parser.add_argument(
        "--max-pages",
        type=int,
        default=300,
        help="Gezilecek maksimum sayfa sayisi (varsayilan: 300)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.4,
        help="Istekler arasi bekleme saniyesi (varsayilan: 0.4)",
    )
    parser.add_argument(
        "--cookie",
        help="Opsiyonel browser Cookie header degeri. Etsy 403 verirse gerekebilir.",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    shop_url = _normalize_shop_input(args.shop)
    shop_name = _shop_name_from_url(shop_url)

    try:
        records, total_count = iter_shop_listing_ids(
            shop_url,
            cookie=args.cookie,
            delay_seconds=args.delay,
            max_pages=args.max_pages,
        )
    except Exception as exc:
        print(f"Hata: {exc}", file=sys.stderr)
        return 1

    print(f"shop={shop_name}")
    print(f"gorunen_toplam={total_count if total_count is not None else 'bilinmiyor'}")
    print(f"cekilen_listing_id={len(records)}")

    for record in records:
        print(record.listing_id)

    if args.csv_path:
        csv_path = Path(args.csv_path).expanduser().resolve()
        write_csv(csv_path, records)
        print(f"csv_yazildi={csv_path}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
