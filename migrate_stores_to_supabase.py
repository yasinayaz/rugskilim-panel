import json, urllib.request, urllib.error
from pathlib import Path

URL = "http://localhost:8001"
KEY = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJpc3MiOiJzdXBhYmFzZSIsImlhdCI6MTc3ODI3MzA0MCwiZXhwIjo0OTMzOTQ2NjQwLCJyb2xlIjoic2VydmljZV9yb2xlIn0.T8HU3AH1IVEMQaVK4GM-5-8e_ug68Z-xq4UJQiCf15Y"
HEADERS = {
    "apikey": KEY,
    "Authorization": f"Bearer {KEY}",
    "Content-Type": "application/json",
    "Prefer": "resolution=merge-duplicates,return=minimal",
}

def post(endpoint, data):
    body = json.dumps(data, default=str).encode()
    req = urllib.request.Request(
        f"{URL}/rest/v1/{endpoint}", data=body, headers=HEADERS, method="POST"
    )
    try:
        with urllib.request.urlopen(req) as r:
            return r.status
    except urllib.error.HTTPError as e:
        print("HATA:", e.code, e.read()[:300])
        return e.code

products = json.loads(Path(".runtime/streamlit/panel_products.json").read_text())
known_codes = {str(p.get("product_code", "")).strip() for p in products}

inv = json.loads(Path(".runtime/streamlit/store_inventory.json").read_text())
stores = inv.get("stores", {})

rows = []
for store_id, store_data in stores.items():
    for product_code, urun in store_data.get("urunler", {}).items():
        if str(product_code).strip() not in known_codes:
            continue
        rows.append({
            "product_code": str(product_code).strip(),
            "store_id": store_id,
            "status": urun.get("status", ""),
            "renk": urun.get("renk", ""),
            "etsy_draft_url": urun.get("etsy_draft_url", ""),
            "hata_mesaji": "",
            "islem_tarihi": urun.get("islem_tarihi", ""),
        })

print(f"Toplam store kaydı: {len(rows)}")

ok = 0
for i in range(0, len(rows), 100):
    s = post("product_store_status?on_conflict=product_code,store_id", rows[i:i+100])
    if s in (200, 201):
        ok += len(rows[i:i+100])
        print(f"  Batch {i//100+1}: OK ({ok}/{len(rows)})")
    else:
        print(f"  Batch {i//100+1}: HATA {s}")

print(f"\nTAMAMLANDI — {ok}/{len(rows)} store kaydı yüklendi")
