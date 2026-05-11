# Coolify Kurulumu

Bu repo icin guncel production kurulumu tek VPS uzerindeki Coolify projesi icinde yonetilir:

- `rugskilim-panel` -> uygulama
- `supabase-rugskilim` -> ayni VPS icindeki self-hosted Supabase service stack

Su an icin dis servis yoktur. Tum production bilesenleri ayni VPS icindedir.

## Guncel topoloji

```text
Internet
  -> panel.rugskilim.com
  -> Coolify Proxy
  -> Coolify Project: rugskilim-panel
  -> Environment: production
     -> Application: rugskilim-panel
     -> Service Stack: supabase-rugskilim
```

## 1. Kaynak tipi

Coolify'da uygulama kaynagini `Dockerfile` ile deploy edin.

- Build context: repo koku
- Dockerfile: `Dockerfile`

## 2. Uygulama servisi

Yeni bir Application olusturun.

- Name: `rugskilim-panel`
- Port: `8501`
- Command / Start command:
  `panel`

Gerekli environment variable'lar:

```env
GOOGLE_SHEET_ID=...
GOOGLE_CREDS_JSON_CONTENT={...service-account-json...}
GEMINI_API_KEY=...
PCLOUD_TOKEN=...
PORT=8501
```

Notlar:

- Domain olarak `panel.rugskilim.com` baglayin.
- `GOOGLE_CREDS_JSON_CONTENT` alanina Google service account JSON'unun tam icerigini yapistirin.
- `PCLOUD_TOKEN` panelden de sheet config'e yazilabiliyor ama ilk acilis icin env'de vermek daha saglikli.
- Bu uygulama Coolify proxy arkasinda yayinlanir.

## 3. Supabase servisi

Supabase ayri bir dis servis degil, ayni Coolify projesi icindeki service stack olarak calisir:

- Service stack name: `supabase-rugskilim`
- Ayni VPS / ayni Coolify server icinde calisir
- PostgreSQL, Auth, API, Storage, MinIO ve ilgili Supabase container'larini barindirir

## 4. Worker gercekligi

Mevcut kod tabaninda `vds/` altinda Windows worker mantigi vardir; ancak bu worker su an ekran goruntulerindeki production Coolify topolojisinde ayri bir application olarak tanimlanmamis kabul edilmelidir.

Eger ileride worker Coolify icine alinacaksa, bu dokuman o degisiklige gore ayrica guncellenmelidir.

## 5. Etsy API acilinca eklenecekler

Su anda repo mantigina gore Etsy sonrasi kisim tam aktif degil. Onay geldikten sonra ilgili calisma ortamina sunlari ekleyin:

```env
ETSY_API_KEY=...
ETSY_SHARED_SECRET=...
ETSY_SHOP_ID=...
ETSY_SHIPPING_PROFILE_ID=...
ETSY_TOKEN_JSON_CONTENT={...token.json...}
```

`ETSY_TOKEN_JSON_CONTENT`, `vds/token.json` dosyasinin tam icerigidir.

## 6. Coolify icin pratik ayarlar

- Health check path gerekli degil; Streamlit port kontrolu yeterli.
- Auto deploy acabilirsiniz.
- İlk deploy sonrasi panel acilmiyorsa loglarda `GOOGLE_CREDS_JSON` ve `GOOGLE_SHEET_ID` eksiklerini kontrol edin.
- Supabase tarafinda servislerin healthy olmasi ayni VPS mimarisinin dogru ayakta oldugunu gosterir.

## 7. Mimari notu

Bu deployment notu, guncel Coolify gercegini esas alir: tek VPS, tek Coolify projesi, ayni ortamda uygulama + self-hosted Supabase stack. Kod tabanindaki eski Google Sheets + Windows VDS akisi halen mevcut olsa da production topolojisi yorumlanirken once bu kurulum baz alinmalidir.
