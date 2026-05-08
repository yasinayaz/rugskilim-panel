# Coolify Kurulumu

Bu repo Coolify'da iki ayri servis olarak kurulmaya hazirlandi:

- `rugskilim-panel` -> Streamlit web paneli
- `rugskilim-worker` -> arka plan indirici / isci

## 1. Kaynak tipi

Coolify'da bu repoyu `Dockerfile` ile deploy edin.

- Build context: repo koku
- Dockerfile: `Dockerfile`

## 2. Panel servisi

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

## 3. Worker servisi

Ayni repodan ikinci bir Application olusturun.

- Name: `rugskilim-worker`
- Port expose etmeniz gerekmez
- Command / Start command:
  `worker`

Gerekli environment variable'lar:

```env
GOOGLE_SHEET_ID=...
GOOGLE_CREDS_JSON_CONTENT={...service-account-json...}
PCLOUD_TOKEN=...
TEMP_DIR=/tmp/etsy_temp
RUN_ONCE=0
STORE_ID=
```

Notlar:

- `STORE_ID` bos birakilirsa `shared/stores.json` icindeki `active=true` magazalar islenir.
- Belirli bir magazayi ayri worker ile calistirmak icin `STORE_ID=LoomAntikRugs` gibi set edebilirsiniz.
- Worker web trafigi almaz; sadece arka planda surekli calisir.

## 4. Etsy API acilinca eklenecekler

Su anda repo mantigina gore Etsy sonrasi kisim tam aktif degil. Onay geldikten sonra worker'a sunlari ekleyin:

```env
ETSY_API_KEY=...
ETSY_SHARED_SECRET=...
ETSY_SHOP_ID=...
ETSY_SHIPPING_PROFILE_ID=...
ETSY_TOKEN_JSON_CONTENT={...token.json...}
```

`ETSY_TOKEN_JSON_CONTENT`, `vds/token.json` dosyasinin tam icerigidir.

## 5. Coolify icin pratik ayarlar

- Health check path gerekli degil; Streamlit port kontrolu yeterli.
- Auto deploy acabilirsiniz.
- İlk deploy sonrasi panel acilmiyorsa loglarda `GOOGLE_CREDS_JSON` ve `GOOGLE_SHEET_ID` eksiklerini kontrol edin.
- Worker loglarinda `Hazir urun yok.` goruyorsaniz servis calisiyor demektir.

## 6. Mimari notu

Bu deployment, mevcut Google Sheets tabanli mimariyi Coolify'ya tasir. Supabase'e gecis ayrica yapilacak; bu kurulum onu bozmaz.
