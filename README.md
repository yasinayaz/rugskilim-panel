# RugsKilim Panel

> Bu repo, eski `/Users/yasinayaz/entegrator-hali` projesinin kopyasindan ayrilan yeni projedir. Eski proje korunur; yeni gelisim sadece bu repo icinde yapilacaktir.

---

## Mevcut Durum

### Lokal Proje

- Aktif calisma klasoru: `/Users/yasinayaz/Projeler/rugskilim-panel`
- Eski proje: `/Users/yasinayaz/entegrator-hali`
- Eski projeye dokunulmayacak
- Bu repo yeni ve bagimsiz lokal git deposudur
- Henuz yeni GitHub repo baglanmadi

### Domainler

- `panel.rugskilim.com` -> `145.223.90.56`
- `supabase.rugskilim.com` -> `145.223.90.56`
- `studio.rugskilim.com` -> `145.223.90.56`

### VPS / Deployment

- Hostinger VPS satin alindi
- Coolify kuruldu
- Coolify icinde proje olusturuldu: `rugskilim-panel`
- Environment: `production`
- Uygulama kaynagi: `rugskilim-panel`
- Servis stack: `supabase-rugskilim`
- Tum bilesenler ayni VPS icinde calisiyor, dis servis yok
- Self-host Supabase Coolify icinde kuruldu
- Supabase servisleri healthy durumda

### Supabase Rol Dagilimi

- `supabase.rugskilim.com` -> Supabase API / Kong endpoint
- `studio.rugskilim.com` -> Supabase Studio arayuzu
- `panel.rugskilim.com` -> yeni uygulama paneli icin ayrildi

### Bu Repoda Simdiden Yapilan Temizlikler

- Proje gorunen adi `RugsKilim Panel` olarak guncellenmeye baslandi
- Streamlit panel title/header yeni ada cekildi
- Windows VDS yol ornekleri `C:\\rugskilim-panel\\...` olacak sekilde guncellendi

### Bilerek Henuz Dokunulmayanlar

- `shared/sheets.py` icindeki eski credentials fallback adlari
- Mevcut Streamlit + Sheets + VDS mimarisi
- Etsy/Shopify/SaaS veri modeli henuz kurulmedi

### Siradaki Hedef

Bu repo, mevcut Etsy otomasyon kodunu daha genis bir SaaS panele evirmek icin kullanilacak:

- self-host Supabase
- kullanici girisi / auth
- tenant / magaza ayrimi
- Etsy entegrasyonu
- Shopify entegrasyonu
- panel + worker + API yapisi

### Sonraki Yapilacaklar

1. Yeni `.env.example` ve deployment ayarlarini olustur
2. Supabase baglanti bilgilerini standardize et
3. SaaS veri modelini tasarla
4. Google Sheets bagimliligini azaltip Supabase merkezli mimariye gec
5. Yeni backend katmanini belirle
6. Son asamada yeni GitHub repo bagla

Etsy'de vintage halı satışı için tam otomatik ürün hazırlama ve yayınlama sistemi.

---

## Genel Amaç

pCloud'da depolanan halı fotoğraflarını seçip; Google Gemini AI ile SEO uyumlu Etsy listing metni (başlık, açıklama, tag'lar) üretir. Üretilen veriler Windows VDS'e aktarılır; VDS fotoğrafları indirir, adlandırır ve Etsy API üzerinden yayınlar.

---

## Mimari

### Guncel VPS / Production Topolojisi

```text
Internet
   |
   v
panel.rugskilim.com
   |
   v
Coolify Proxy (VPS icinde)
   |
   v
Coolify
   |
   v
Project: rugskilim-panel
   |
   v
Environment: production
   |
   +-----------------------------+
   |                             |
   v                             v
App: rugskilim-panel             Service Stack: supabase-rugskilim
(Dockerfile ile deploy)          (ayni VPS icinde)
   |                             |
   |                             +--> PostgreSQL
   |                             +--> Supabase Auth
   |                             +--> Supabase API / REST
   |                             +--> Storage
   |                             +--> MinIO
   |                             +--> Diger gerekli Supabase container'lari
   |
   +-----------> Uygulama ic agdan Supabase servislerine baglanir
```

Not:

- Bu repo icin production varsayimi budur.
- Ayri bir dis veritabani veya ayri bir barindirma katmani varsayilmamalidir.
- Kod tabanindaki eski Google Sheets + Windows VDS akisi halen vardir, ancak hosting mimarisi yorumlanirken bu Coolify topolojisi esas alinmalidir.

```
┌──────────────────────────────────────┐
│         macOS — Streamlit UI         │
│  Ürün seç → Parser → Gemini AI       │
│  → Google Sheets'e yaz (status=ready)│
└──────────────┬───────────────────────┘
               │ Google Sheets (Kuyruk / DB)
┌──────────────▼───────────────────────┐
│      Windows VDS — Orkestrator       │
│  ready al → pCloud indir → adlandır  │
│  → Etsy API yükle → status=done      │
└──────────────────────────────────────┘
```

---

## Proje Yapısı

```
rugskilim-panel/
├── streamlit/                    # macOS — Streamlit arayüzü
│   ├── streamlit_app.py          # Ana uygulama (4 sekme)
│   ├── modules/
│   │   ├── parser.py             # Dosya adından boyut/fiyat çıkarır
│   │   └── ai_icerik.py          # Gemini Vision → Etsy listing metni
│   ├── .env                      # API key'ler ve token'lar (gizli)
│   └── credentials-*.json        # Google Service Account (gizli)
│
├── loomantikrugs/                # LoomAntikRugs mağazasına özel dosyalar
│   ├── Ready_Indir.command       # Mac'te çift tık ile ready indirici
│   ├── run_ready_download.sh     # Tek seferlik store worker
│   └── templates/
│       └── LoomAntikRugs_v1.json # Store template'i
│
├── vds/                          # Windows VDS — Arka plan otomasyon
│   ├── orkestrator.py            # Ana döngü (indir → adlandır → yükle)
│   ├── oauth_baslat.py           # Etsy OAuth 2.0 (bir kez çalıştırılır)
│   ├── modules/
│   │   ├── pcloud_indirici.py    # pCloud API ile dosya indirme
│   │   └── etsy_api.py           # Etsy Open API v3 entegrasyonu
│   └── baslat.bat                # Windows başlatıcı
│
├── shared/                       # Her iki ortamda ortak kod
│   └── sheets.py                 # Google Sheets API (kuyruk yönetimi)
│
└── run.sh                        # macOS başlatıcı
```

---

## Teknoloji Stack

| Katman | Teknoloji |
|--------|-----------|
| UI | Python · Streamlit |
| AI | Google Gemini 2.5-flash (Vision) |
| Veri tabanı | Google Sheets API v4 |
| Dosya depolama | pCloud API |
| Yayınlama | Etsy Open API v3 (OAuth 2.0 PKCE) |
| HTTP | httpx (async) · requests |
| Diğer | gspread · google-auth · pandas · openpyxl |

## Ajanlara Not

Bu repoda gorev alan ajanlar ve kod asistanlari:

- deployment, domain, env, network ve servis baglantilarini bu Coolify topolojisine gore yorumlamali
- dis servis varsaymamalı
- `rugskilim-panel` uygulamasi ile `supabase-rugskilim` stack'inin ayni VPS icinde oldugunu baz almalidir

---

## Veri Akışı (Uçtan Uca)

### 1. macOS — Kullanıcı Arayüzü

1. **pCloud Giriş** — Token ile bağlanır, halı klasörlerini listeler
2. **Ürün Seçimi** — Max 15 ürün seçilebilir; sağ panelde resim önizlemesi
3. **Parser** — Dosya adından boyut, m², ürün kodu ve fiyat hesaplar
   ```
   "4102-- 65x119 = 0,77 m2 2,1x3,9 ft.jpg"
   → boyut_cm: 65x119, boyut_ft: 2.1x3.9, m²: 0.77, fiyat: $231
   ```
4. **Sheets'e Ekle** — `status=pending` ile kuyruğa yazar
5. **Gemini AI** — Ana resim URL'si alınır, base64 kodlanır, Gemini'ye gönderilir:
   - Başlık (120–140 karakter, SEO uyumlu)
   - 13 Etsy tag'ı
   - Renk1/2, stil, köken, desen
   - 4–5 paragraf Etsy açıklama metni
6. **Sheets Güncelle** — AI verileri yazılır, `status=ready`

### 2. Windows VDS — Orkestrator (24/7)

1. Sheets'ten `status=ready` ürünleri alır (limit: 50/gün)
2. pCloud'dan tüm resim dosyalarını `C:\etsy_temp\{urun_id}\` altına indirir
3. Dosyaları SEO-friendly adlandırır:
   ```
   1C4A9318.jpg → 5x8-ft-vintage-turkish-oushak-rug_01.jpg  (ana resim)
   1C4A9319.jpg → 3x10-runner-rug_02.jpg                    (tag1)
   1C4A9320.jpg → 3x10-cream-rug_03.jpg                     (tag2)
   ```
4. `status=downloaded` yapar
5. Etsy API onayı gelince: draft listing oluştur → fotoğrafları yükle → `status=done`

### 3. Etsy (Manuel Yayın — API Onayı Gelene Kadar)

Draft listing Etsy arayüzünde açılır, incelenir ve "Publish" ile yayınlanır. Tüm alanlar (başlık, açıklama, fiyat, tag'lar, fotoğraflar) zaten doldurulmuş gelir.

---

## Status Geçişleri

```
pending → ready → downloading → downloaded → uploading → done
                                                        ↘ error
```

---

## Google Sheets Kolon Yapısı (37 Kolon)

| # | Kolon | Açıklama |
|---|-------|----------|
| 1 | urun_id | Ürün kodu (dosya adından) |
| 2 | pcloud_klasor_yolu | pCloud'daki tam yol |
| 3–5 | boyut_cm / boyut_ft / metrekare | Parser çıktısı |
| 6–7 | fiyat_usd / foto_sayisi | Hesaplanan fiyat ve resim adedi |
| 8 | baslik | AI üretimi Etsy başlığı |
| 9 | aciklama | AI üretimi tam açıklama metni |
| 10 | taglar_virgul | Virgülle ayrılmış 13 tag |
| 11–23 | tag1 – tag13 | Ayrı tag kolonları |
| 24–27 | renk1 / renk2 / stil / koken | Etsy kategori alanları |
| 28 | status | İş akışı durumu |
| 29 | etsy_draft_url | Oluşturulan draft linki |
| 30 | hata_mesaji | Hata varsa açıklaması |
| 31 | islem_tarihi | Son güncelleme zamanı |
| 32 | pcloud_klasor_id | pCloud klasör ID'si |
| 33 | ana_resim_tag | Ana resim dosya adı tag'ı |
| 34–37 | pattern / tip / home_style / shop_section | Etsy sınıflandırma |

---

## Kurulum

### Gereksinimler

```bash
pip install streamlit httpx gspread google-auth pandas openpyxl requests
```

### macOS — Streamlit

```bash
# 1. Repo'yu clone et
git clone <yeni_repo_url> rugskilim-panel
cd rugskilim-panel

# 2. streamlit/.env dosyasını doldur:
GEMINI_API_KEY=...
GOOGLE_SHEET_ID=...
GOOGLE_CREDS_JSON=/tam/yol/credentials.json
PCLOUD_TOKEN=...

# 3. Başlat
bash run.sh
# Tarayıcıda: http://localhost:8501
```

### Windows VDS — Orkestrator

```batch
# 1. System ortam değişkenlerini ayarla:
set GOOGLE_SHEET_ID=...
set GOOGLE_CREDS_JSON=C:\rugskilim-panel\streamlit\credentials.json
set PCLOUD_TOKEN=...
set TEMP_DIR=C:\etsy_temp

# 2. Etsy OAuth (bir kez)
python vds/oauth_baslat.py
# Tarayıcıda Etsy authorize → token.json oluşur

# 3. Orkestratörü başlat
vds\baslat.bat
```

### Etsy Mağazadan Listing ID Çekme

Public Etsy mağaza sayfasındaki ürünlerin `listing_id` değerlerini almak için:

```bash
python3 vds/etsy_shop_listing_ids.py https://www.etsy.com/shop/LoopRug
python3 vds/etsy_shop_listing_ids.py LoopRug --csv looprug_listing_ids.csv
python3 vds/etsy_shop_listing_ids.py LoopRug --cookie 'uaid=...; user_prefs=...'
```

Not: Public sayfadan genellikle Etsy `listing_id` çekilir; seller'ın private SKU/kendi iç ürün kodu herkese açık değilse alınamaz. Etsy bazen anonim istekleri `403` ile engeller; bu durumda browser oturum cookie'si gerekebilir.

### Etsy CSV ile Green Senkron

Etsy'den indirilen listing CSV'sindeki `SKU` alanlarini, ilgili magazanin sheet'indeki
`urun_id` ile eslestirip A sutununu yesile boyamak icin:

```bash
python3 vds/sync_etsy_csv_to_green.py LoomAntikRugs "/path/EtsyListingsDownload.csv"
python3 vds/sync_etsy_csv_to_green.py LoomAntikRugs "/path/EtsyListingsDownload.csv" --clear-missing-green
```

`--clear-missing-green` verilirse CSV'de olmayan ama daha once green olan urunlerin yesili temizlenir.

### Kurulum Kontrol Listesi

- [ ] Google Cloud: Service Account oluştur, Sheets API + Drive API aktif et
- [ ] Google Sheets: Başlık satırını `Tab 3 → Başlık Satırı Oluştur` ile oluştur
- [ ] Gemini API: Google AI Studio'dan API key al
- [ ] pCloud Token: Tarayıcı console'dan `document.cookie.match(/pcauth=([^;]+)/)[1]` ile al
- [ ] Etsy App: Etsy Developer Portal'dan App ID + Secret (onay gerekli)

---

## Konfigürasyon Dosyaları

| Dosya | Ortam | İçerik |
|-------|-------|--------|
| `streamlit/.env` | macOS | GEMINI_API_KEY, GOOGLE_SHEET_ID, GOOGLE_CREDS_JSON, PCLOUD_TOKEN |
| `vds/baslat.bat` | Windows | GOOGLE_SHEET_ID, GOOGLE_CREDS_JSON, TEMP_DIR |
| `vds/token.json` | Windows | Etsy OAuth token (runtime'da oluşur) |
| `streamlit/credentials*.json` | Her ikisi | Google Service Account credentials |

---

## API'ler ve Rate Limiting

| API | Auth | Rate Limit |
|-----|------|------------|
| pCloud | Token | Yok (direkt) |
| Google Sheets | Service Account | 100 req/100sn |
| Google Gemini 2.5-flash | API Key | 15 RPM (ücretsiz) |
| Etsy Open API v3 | OAuth 2.0 PKCE | 5 QPS |

---

## Hata Yönetimi

| Hata | Sebep | Çözüm |
|------|-------|-------|
| `GEMINI_API_KEY eksik` | .env okunmadı | `streamlit/.env` yolunu kontrol et |
| Gemini 429 | Rate limit | 10 sn bekle, retry otomatik |
| pCloud timeout | API endpoint down | Fallback host otomatik: `eapi.pcloud.com` |
| Sheets yanlış kolona yazıyor | gspread detection bug | Satır sayısını `len()` ile al, `update()` kullan |
| Etsy upload yok | API onayı bekleniyor | `oauth_baslat.py` çalıştır, onay sonrası aktif |

---

## Önemli Notlar

- `.env` ve `*.json` credential dosyaları `.gitignore`'dadır, asla commit edilmez
- pCloud token süresi dolabilir — dolunca Streamlit'ten yeni token gir, Sheets config'e otomatik kaydedilir
- Etsy API onayı gelene kadar `status=downloaded` kalır, manuel yayın gerekir
- VDS'te günde max 50 ürün işlenir (Etsy rate limit koruması)
- Gemini prompt'u boyutu ft cinsinden yuvarlar: 2.8x9.9 → 3x10 ft (başlıkta)
