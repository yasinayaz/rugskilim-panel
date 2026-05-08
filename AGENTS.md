# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

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

## Bağımlılıklar

```bash
pip install streamlit httpx gspread google-auth pandas openpyxl requests
```
