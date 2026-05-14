"""
Tum urun kodlarini panel kurali: 'HARF BOSLUK SAYI' formatina normalize eder.

Kural ornekleri:
  d149   -> D 149
  D-520  -> D 520
  D520   -> D 520
  i-11   -> İ 11  (NOT: i harfi yoksa canonicalde ayni kalir)
  E-220  -> E 220
  h152   -> H 152

Ayni canonical'a dusen birden fazla urun (merge):
  1. Master secilir: store_status ref sahibi > kategorili > canonical formattaki > ilk alfabetik
  2. Orphan store_status satirlari master'a tasınır (upsert) ve eski satir silinir
  3. Orphan urun karti, hic store_status kalmadiysa silinir

Basit rename (cakismasiz):
  1. products tablosunda yeni satir upsert (kopya + yeni kod), eski silinir
  2. store_status satirlari ayni sekilde tasınır

Varsayilan mod: dry-run. Degisiklik uygulamak icin --apply.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict
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
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def _clean(value) -> str:
    return str(value or "").strip()


def _should_normalize(code: str) -> bool:
    """4120 x2 gibi 'sayi x sayi' formatli kodlara dokunma — x burada adet anlami tasir."""
    return not re.search(r"\d+\s*[xX]\d*$", _clean(code))


def canonical(code: str) -> str:
    """'HARF BOSLUK SAYI' kurali: D-520 -> D 520, d149 -> D 149, İ-11 -> İ 11"""
    code = _clean(code).upper().replace("-", " ")
    code = re.sub(r"\s+", " ", code).strip()
    # Harf+rakam arasında boşluk yoksa ekle: D149 -> D 149, KLM62 -> KLM 62
    code = re.sub(r"([A-ZÇĞİÖŞÜ]+)([0-9])", r"\1 \2", code)
    return code


def _is_canonical(code: str) -> bool:
    return _clean(code) == canonical(code)


def _load_all_products() -> list[dict]:
    import requests
    from shared.product_catalog import _rest_url, _headers

    products = []
    offset = 0
    while True:
        resp = requests.get(
            _rest_url(),
            headers={**_headers(), "Range-Unit": "items", "Range": f"{offset}-{offset+999}"},
            params={"select": "*", "order": "product_code.asc"},
            timeout=45,
        )
        if not resp.ok:
            raise RuntimeError(f"products okunamadi: {resp.status_code} {resp.text}")
        page = resp.json()
        products.extend(page)
        if len(page) < 1000:
            break
        offset += 1000
    return products


def _load_all_store_rows() -> list[dict]:
    import requests
    from shared.product_catalog import SUPABASE_STORE_TABLE, _base_url, _headers

    rows = []
    offset = 0
    url = f"{_base_url()}/rest/v1/{SUPABASE_STORE_TABLE}"
    while True:
        resp = requests.get(
            url,
            headers={**_headers(), "Range-Unit": "items", "Range": f"{offset}-{offset+999}"},
            params={"select": "*", "order": "product_code.asc"},
            timeout=45,
        )
        if not resp.ok:
            raise RuntimeError(f"store_status okunamadi: {resp.status_code} {resp.text}")
        page = resp.json()
        rows.extend(page)
        if len(page) < 1000:
            break
        offset += 1000
    return rows


def _pick_master(group: list[dict], ss_refs: dict[str, list[str]]) -> tuple[dict, list[dict]]:
    """Master urunü sec: store_ref > kategori > canonical format > alfabetik."""

    def priority(p: dict) -> tuple[int, int, int, str]:
        code = _clean(p.get("product_code"))
        return (
            0 if ss_refs.get(code) else 1,
            0 if _clean(p.get("category")) else 1,
            0 if _is_canonical(code) else 1,
            code.lower(),
        )

    ordered = sorted(group, key=priority)
    return ordered[0], ordered[1:]


def build_plan(products: list[dict], store_rows: list[dict]) -> dict:
    """
    Tam normalize planini uretir.
    Donus:
      renames: [(old_code, new_code, product_row)]  - merge yok, sadece yeniden adlandirma
      merges:  [(master_code, [orphan_codes])]        - ayni canonical altinda birden fazla urun
      ss_moves: [(store_id, old_code, new_code, full_row)]
      product_deletes: [code]
    """
    # store_status indeksi: product_code -> [store_id]
    ss_refs: dict[str, list[str]] = defaultdict(list)
    ss_by_key: dict[tuple[str, str], dict] = {}
    for row in store_rows:
        code = _clean(row.get("product_code"))
        sid = _clean(row.get("store_id"))
        if code and sid:
            ss_refs[code].append(sid)
            ss_by_key[(code, sid)] = row

    # canonical gruplama
    canon_groups: dict[str, list[dict]] = defaultdict(list)
    for p in products:
        code = _clean(p.get("product_code"))
        if not code:
            continue
        c = canonical(code)
        canon_groups[c].append(p)

    renames: list[tuple[str, str, dict]] = []
    merges: list[tuple[str, list[str]]] = []   # (master_code, [orphan_codes])
    ss_moves: list[tuple[str, str, str, dict]] = []
    product_deletes: list[str] = []
    seen_new_codes: set[str] = set()
    # master_code_map: her hangi bir eski kod -> nihai master canonical kodu
    code_to_master: dict[str, str] = {}

    for canon_code, group in sorted(canon_groups.items()):
        if len(group) == 1:
            p = group[0]
            old_code = _clean(p.get("product_code"))
            if _is_canonical(old_code) or not _should_normalize(old_code):
                # Zaten dogru veya normalize edilmemeli
                code_to_master[old_code] = old_code
            else:
                # Basit rename
                new_code = canon_code
                renames.append((old_code, new_code, p))
                code_to_master[old_code] = new_code
                seen_new_codes.add(new_code)
        else:
            # Merge grubu
            master, orphans = _pick_master(group, ss_refs)
            master_old_code = _clean(master.get("product_code"))
            master_new_code = canon_code  # hedef her zaman canonical

            if master_old_code != master_new_code:
                # Master'in kendisi de rename gerektiriyor
                renames.append((master_old_code, master_new_code, master))
                seen_new_codes.add(master_new_code)

            code_to_master[master_old_code] = master_new_code

            orphan_codes = []
            for orp in orphans:
                old_code = _clean(orp.get("product_code"))
                code_to_master[old_code] = master_new_code
                orphan_codes.append(old_code)
                product_deletes.append(old_code)

            if orphan_codes:
                merges.append((master_new_code, orphan_codes))

    # store_status tasima planını kur
    processed_ss: set[tuple[str, str]] = set()
    for row in store_rows:
        old_code = _clean(row.get("product_code"))
        sid = _clean(row.get("store_id"))
        if not old_code or not sid:
            continue
        new_code = code_to_master.get(old_code, old_code)
        if new_code == old_code:
            continue
        key = (old_code, sid)
        if key in processed_ss:
            continue
        processed_ss.add(key)
        ss_moves.append((sid, old_code, new_code, row))

    return {
        "renames": renames,
        "merges": merges,
        "ss_moves": ss_moves,
        "product_deletes": product_deletes,
        "code_to_master": code_to_master,
    }


def write_report(plan: dict, report_path: Path) -> None:
    renames = plan["renames"]
    merges = plan["merges"]
    ss_moves = plan["ss_moves"]
    product_deletes = plan["product_deletes"]

    # merge + rename ayrimi
    merge_renames = {orp for _, orphans in merges for orp in orphans}
    simple_renames = [(o, n, p) for o, n, p in renames if o not in merge_renames]
    master_renames = [(o, n, p) for o, n, p in renames if o in {plan["code_to_master"].get(o, o) for _, orphans in merges for orp in orphans} or o not in merge_renames]

    # store_status hareketi mağaza bazında
    store_move_counts: dict[str, int] = defaultdict(int)
    for sid, _, _, _ in ss_moves:
        store_move_counts[sid] += 1

    lines = [
        "# Product Code Normalization Plan",
        "",
        f"Tarih: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## Ozet",
        "",
        f"- Basit rename (tekil, yanlış format): {len(simple_renames)}",
        f"- Merge grubu sayısı: {len(merges)}",
        f"- Toplam silincek orphan ürün: {len(product_deletes)}",
        f"- store_status satır hareketi: {len(ss_moves)}",
        "",
        "Mağaza bazında store_status hareketi: " + ", ".join(f"{k}={v}" for k, v in sorted(store_move_counts.items())),
        "",
        "## Basit Rename Listesi (ilk 100)",
        "",
        "| Eski kod | Yeni kod |",
        "|---|---|",
    ]
    for old, new, _ in sorted(simple_renames, key=lambda x: x[0].lower())[:100]:
        lines.append(f"| `{old}` | `{new}` |")

    lines += [
        "",
        "## Merge Grupları",
        "",
        "| Master (hedef) | Orphanlar | Orphan store_status |",
        "|---|---|---|",
    ]
    for master_code, orphan_codes in sorted(merges, key=lambda x: x[0].lower()):
        orp_str = ", ".join(f"`{o}`" for o in orphan_codes)
        # orphan'ların store_status satırlarını bul
        orp_ss = [(sid, old) for sid, old, new, _ in ss_moves if old in orphan_codes]
        orp_ss_str = ", ".join(f"{sid}:{old}" for sid, old in orp_ss) or "-"
        lines.append(f"| `{master_code}` | {orp_str} | {orp_ss_str} |")

    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Rapor: {report_path}")


def apply_plan(plan: dict) -> dict:
    import requests
    from shared.product_catalog import ProductCatalog, StoreCatalog, SUPABASE_STORE_TABLE, _base_url, _headers

    renames = plan["renames"]
    merges = plan["merges"]
    ss_moves = plan["ss_moves"]
    product_deletes = plan["product_deletes"]

    stats = {
        "products_upserted": 0,
        "products_deleted": 0,
        "ss_upserted": 0,
        "ss_deleted": 0,
    }

    ss_url = f"{_base_url()}/rest/v1/{SUPABASE_STORE_TABLE}"

    # 1) Rename gereken urunleri upsert et (yeni kod ile)
    if renames:
        new_products = []
        for old_code, new_code, p in renames:
            row = dict(p)
            row["product_code"] = new_code
            row["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            # product_id guncelle
            row["product_id"] = f"PRD-{new_code.upper().replace(' ', '')}"
            new_products.append(row)
        ProductCatalog().upsert_products(new_products)
        stats["products_upserted"] += len(new_products)
        print(f"  [products] {len(new_products)} urun upsert edildi (yeni kod)")

    # 2) store_status: yeni satırları upsert et
    # Ayni (new_code, store_id) ciftine birden fazla eski kod merge olabilir;
    # posta gonderilecek satirlari dedup et — store_status olan satiri yoksa olmayan satiri sec.
    if ss_moves:
        dedup: dict[tuple[str, str], dict] = {}
        for sid, old_code, new_code, row in ss_moves:
            key = (new_code, sid)
            new_row = dict(row)
            new_row["product_code"] = new_code
            if key not in dedup:
                dedup[key] = new_row
            else:
                # Mevcut satiri koru, ama renk/status bilgisi daha iyiyse guncelle
                if new_row.get("renk") == "green" and dedup[key].get("renk") != "green":
                    dedup[key] = new_row

        unique_ss_rows = list(dedup.values())
        chunk_size = 500
        for i in range(0, len(unique_ss_rows), chunk_size):
            chunk = unique_ss_rows[i:i+chunk_size]
            r = requests.post(
                ss_url,
                headers={**_headers(), "Prefer": "resolution=merge-duplicates,return=minimal"},
                params={"on_conflict": "product_code,store_id"},
                json=[{k: v for k, v in row.items() if k != "updated_at"} for row in chunk],
                timeout=60,
            )
            if not r.ok:
                raise RuntimeError(f"store_status upsert basarisiz: {r.status_code} {r.text}")
        stats["ss_upserted"] += len(unique_ss_rows)
        print(f"  [store_status] {len(unique_ss_rows)} satir yeni kodla upsert edildi (dedup: {len(ss_moves) - len(unique_ss_rows)} atlanda)")

    # 3) store_status: eski satirlari toplu sil (mağaza bazında batch)
    if ss_moves:
        # store_id bazında eski kodları grupla → tek DELETE isteği per mağaza
        by_store: dict[str, set[str]] = defaultdict(set)
        for sid, old_code, new_code, _ in ss_moves:
            by_store[sid].add(old_code)

        total_deleted_ss = 0
        for sid, old_codes in sorted(by_store.items()):
            codes_filter = ",".join(old_codes)
            r = requests.delete(
                ss_url,
                headers={**_headers(), "Prefer": "return=minimal"},
                params={"store_id": f"eq.{sid}", "product_code": f"in.({codes_filter})"},
                timeout=60,
            )
            if not r.ok:
                raise RuntimeError(f"store_status silme basarisiz ({sid}): {r.status_code} {r.text}")
            total_deleted_ss += len(old_codes)
            print(f"    {sid}: {len(old_codes)} satir silindi")

        stats["ss_deleted"] += total_deleted_ss
        print(f"  [store_status] toplam {total_deleted_ss} eski satir silindi")

    # 4) Orphan product'ları sil (eski rename kodları + merge orphanları)
    old_rename_codes = [old for old, new, _ in renames]
    all_deletes = sorted(set(old_rename_codes + product_deletes))
    if all_deletes:
        deleted = ProductCatalog().delete_products(all_deletes)
        stats["products_deleted"] += deleted
        print(f"  [products] {deleted} orphan urun silindi")

    return stats


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Urun kodlarini HARF BOSLUK SAYI formatina normalize et")
    p.add_argument("--apply", action="store_true", help="Degisiklikleri uygula (varsayilan: dry-run)")
    p.add_argument("--report-path", default="", help="Rapor dosya yolu")
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    _load_env()
    args = parse_args(argv)

    print("Veriler yukleniyor...")
    products = _load_all_products()
    store_rows = _load_all_store_rows()
    print(f"  products: {len(products)}, store_status: {len(store_rows)}")

    print("Plan olusturuluyor...")
    plan = build_plan(products, store_rows)

    renames = plan["renames"]
    merges = plan["merges"]
    ss_moves = plan["ss_moves"]
    product_deletes = plan["product_deletes"]

    merge_renames = {orp for _, orphans in merges for orp in orphans}
    simple_renames = [(o, n, p) for o, n, p in renames if o not in merge_renames]

    summary = {
        "mode": "apply" if args.apply else "dry-run",
        "simple_renames": len(simple_renames),
        "merge_groups": len(merges),
        "orphan_products_to_delete": len(product_deletes),
        "ss_moves": len(ss_moves),
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))

    report_path = (
        Path(args.report_path)
        if args.report_path
        else _repo_root() / "reports" / f"normalize-product-codes-{datetime.now().strftime('%Y-%m-%d')}.md"
    )
    write_report(plan, report_path)

    if args.apply:
        print("\nUygulanıyor...")
        stats = apply_plan(plan)
        print(json.dumps(stats, indent=2, ensure_ascii=False))
    else:
        print("\nDry-run tamamlandi. Uygulamak icin: --apply")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
