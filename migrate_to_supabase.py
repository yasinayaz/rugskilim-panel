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
EXCLUDE = {
    "loaded_store_count", "loaded_stores",
    "sold_site", "customer_name", "customer_phone",
    "customer_address", "customer_contact_country",
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
cleaned = [{k: v for k, v in p.items() if k not in EXCLUDE} for p in products]
print(f"Toplam urun: {len(cleaned)}")

ok = 0
for i in range(0, len(cleaned), 100):
    s = post("products?on_conflict=product_code", cleaned[i : i + 100])
    if s in (200, 201):
        ok += len(cleaned[i : i + 100])
        print(f"  Batch {i//100+1}: OK ({ok}/{len(cleaned)})")
    else:
        print(f"  Batch {i//100+1}: HATA {s}")

print(f"\nTAMAMLANDI — {ok}/{len(cleaned)} urun yuklendi")
