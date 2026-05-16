# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Çalıştırma Komutları

```bash
# macOS — Streamlit UI başlat
bash run.sh
# veya:
cd streamlit && python3 -m streamlit run streamlit_app.py

# Windows VDS — Orkestratör başlat
vds\baslat.bat
# veya:
cd vds && python orkestrator.py

# Etsy OAuth (VDS'te bir kez, token.json oluşturur)
cd vds && python oauth_baslat.py
```

## Mimari

İki bağımsız ortam, Google Sheets üzerinden haberleşir:

- **streamlit/** → Kullanıcı arayüzü (Streamlit). pCloud'dan ürün seçilir, `parser.py` boyut/fiyat çıkarır, `ai_icerik.py` Gemini ile listing metni üretir, `shared/sheets.py` ile Sheets kuyruğuna yazar.
- **vds/** → Arka plan işçisi (Windows). `orkestrator.py` Sheets'ten `status=ready` ürünleri alır, `pcloud_indirici.py` ile dosyaları indirir, adlandırır, `etsy_api.py` ile Etsy'e yükler.
- **shared/sheets.py** → Her iki ortamın ortak Sheets katmanı. Kuyruk yönetimi, status geçişleri, config okuma/yazma burada.

## Mevcut VPS / Coolify Mimarisi

Bu repoda calisirken varsayilacak guncel production topolojisi budur. Claude, mimariyle ilgili sorularda ve deployment kararlarinda bunu birincil gercek kabul etmelidir.

```text
Internet
  -> panel.rugskilim.com
  -> Coolify Proxy (VPS icinde)
  -> Coolify
  -> Project: rugskilim-panel
  -> Environment: production
     -> Application: rugskilim-panel
     -> Service Stack: supabase-rugskilim
```

Detaylar:

- Tek VPS vardir; dis servis yoktur.
- `Coolify v4` ayni VPS uzerinde calisir.
- Coolify projesi: `rugskilim-panel`
- Environment: `production`
- Application: `rugskilim-panel`
- Domain: `https://panel.rugskilim.com`
- App deployment tipi: `Dockerfile`
- Ayri bir Coolify worker application'i su an varsayilmamali.
- Self-hosted Supabase ayni VPS icinde `supabase-rugskilim` service stack'i olarak calisir.
- Supabase tarafinda PostgreSQL, Auth, API/REST, Storage, MinIO ve ilgili diger container'lar ayni stack icindedir.
- Uygulama ile Supabase ayni Coolify projesi ve ayni sunucu icinde konusur.
- Proxy request'i `panel.rugskilim.com` alan adindan `rugskilim-panel` uygulamasina yonlendirir.

## Ajan Kurali

Bu repo icin gorev alirken veya soru cevaplarken:

- Varsayilan production mimarisi olarak bu Coolify + tek VPS + ayni makinede Supabase yapisini baz al.
- "dis servis", "ayri veritabani sunucusu", "ayri worker app'i" gibi varsayimlari sadece kullanici acikca isterse veya kod bunu zorunlu kilarsa kullan.
- Deployment, env, networking ve servis baglantilari hakkinda cevap verirken once bu topolojiye gore dusun.
- Eski Google Sheets + Windows VDS akisi kod tabaninda halen vardir; ancak production hosting yorumlarinda bunu Coolify icindeki uygulama topolojisiyle karistirma.

## Status Akışı

```
pending → ready → downloading → downloaded → uploading → done / error
```

`status` değeri Sheets'te tutulur. Mac `ready` yazar, VDS oradan alır.

## Kritik Davranışlar

**sheets.py — satır yazma:**
`gspread`'in `append_row` response'u güvenilmez. Satır numarası için: tüm satırları oku → `len() + 1` → `update()` ile yaz. `append_row`'un döndürdüğü indekse güvenme.

**pcloud_indirici.py — host seçimi:**
`api.pcloud.com` ve `eapi.pcloud.com` arasında otomatik fallback var. Her iki host'u deneyen `_host_sec()` fonksiyonu kullanılıyor.

**ai_icerik.py — boyut formatı:**
Gemini prompt'a ft boyutu yuvarlanmış gitmeli: `2.8x9.9 → 3x10 ft`. Başlıkta daima yuvarlak ft değeri olur.

**etsy_api.py — onay durumu:**
Etsy API henüz production onayı bekliyor. Bu modüle dokunulurken `status=downloaded`'dan sonraki kısmın henüz aktif olmadığını unutma.

## Ortam Değişkenleri

`streamlit/.env`:
```
GEMINI_API_KEY
GOOGLE_SHEET_ID
GOOGLE_CREDS_JSON   # Service account JSON dosyasının tam yolu
PCLOUD_TOKEN        # Sheets config'den de okunabilir (otomatik sync)
```

`vds/baslat.bat` veya sistem env:
```
GOOGLE_SHEET_ID
GOOGLE_CREDS_JSON
PCLOUD_TOKEN
TEMP_DIR            # İndirilen dosyalar için (varsayılan: C:\etsy_temp)
```

## Ürün Kodu Normalizasyon Kuralları

Tüm mağaza CSV'lerinden gelen SKU'lar panele yazılmadan önce bu kurallara göre normalize edilir.
Araç: `vds/normalize_product_codes.py`

### 1. Mağaza Prefix Stripping (CSV'den okurken)

Her mağazanın Etsy SKU'sunda bir prefix olabilir. Canonical koda geçmeden önce çıkarılır:

| Mağaza | Çıkarılacak Prefix |
|--------|-------------------|
| LoomixRugs | `LMX ` |
| LoopRug | `LR `, `LP ` |
| RugsShopTurkey | `RST `, `RSH ` |
| WovenLoomRugs | `WLR `, `WLB ` |
| İlmekRug | `ilmek ` (büyük/küçük harf farkı yok) |
| BohoRugHouse | — (prefix yok) |
| WovenTurkishRugs | — (prefix yok) |
| WoolCottonRugs | — (prefix yok) |
| OldNewRugs | — (prefix yok) |
| PatchArts | — (prefix yok) |
| RugsKilimLLC | — (prefix yok) |
| LoomAntikRugs | — (prefix yok) |

### 2. Canonical Format (Panel / Sheet / Supabase'de saklanan kod)

Prefix çıkarıldıktan sonra şu dönüşümler uygulanır:

```
1. Büyük harfe çevir
2. Tire (-) → boşluk ( )
3. Çoklu boşlukları teke indir
4. Harf+rakam arasına boşluk ekle (D149 → D 149, KLM62 → KLM 62)
```

**Örnekler:**

| Ham SKU | Prefix çıkar | Canonical |
|---------|-------------|-----------|
| `LMX D 149` | `D 149` | `D 149` |
| `LMX İ-11` | `İ-11` | `İ 11` |
| `RST 3340` | `3340` | `3340` |
| `WLR D-706` | `D-706` | `D 706` |
| `LR D 730` | `D 730` | `D 730` |
| `ilmek D 977` | `D 977` | `D 977` |
| `d149` | `d149` | `D 149` |
| `D-520` | `D-520` | `D 520` |
| `h152` | `h152` | `H 152` |
| `3340` | `3340` | `3340` |

**Sonuç format:** `HARF BOŞLUK SAYI` veya sadece `SAYI`
- `D 149` ✅ `İ 11` ✅ `KLM 62` ✅ `3340` ✅
- `D149` ❌ `d 149` ❌ `D-149` ❌ `İ-11` ❌

### 3. İstisna: Adet Kodu (x2)

`4120 x2` gibi `SAYI x SAYI` formatındaki kodlar normalize edilmez — `x` burada adet anlamı taşır.

### 4. Merge Kuralı (Aynı Canonical'a Düşen Birden Fazla Ürün)

`D149`, `d149`, `D-149`, `D 149` hepsi → canonical `D 149`

Çakışma varsa **master seçim önceliği:**
1. `product_store_status` referansı olan
2. `products.category` dolu olan
3. Canonical formatta olan
4. Alfabetik olarak ilk gelen

**Uygulama sırası:**
1. Orphan store_status satırları master'a taşı (upsert)
2. Eski store_status satırlarını sil
3. Orphan product kayıtlarını sil

### 5. CSV Otoritesi

CSV'de bir ürün varsa panelde ve sheet'te de olmalı.
- CSV'deki duplicate SKU'lar (aynı canonical): ilk geçen alınır, ikincisi atlanır
- `products.status=sold` olsa bile Etsy'de aktifse `product_store_status`'ta görünmeli
- Sheet'te sadece green (aktif) satırlar kalır; green olmayanlar silinir

### 6. Sync Araçları

```bash
# Tüm ürün kodlarını normalize et (dry-run)
python3 vds/normalize_product_codes.py

# Uygula
python3 vds/normalize_product_codes.py --apply

# Mağaza store_status → Sheet sync
python3 vds/sync_store_status_to_sheet.py <store_id> --include-sold
```

## Bağımlılıklar

```bash
pip install streamlit httpx gspread google-auth pandas openpyxl requests
```
