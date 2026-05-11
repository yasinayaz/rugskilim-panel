# RugsKilim Panel - Current Status

Bu dosya, projeyi yeni bir sohbette veya daha sonra hızlıca devralmak icin kisa durum ozeti tutar.

## Active Project

- Local working project: `/Users/yasinayaz/Projeler/rugskilim-panel`
- Old project kept untouched: `/Users/yasinayaz/entegrator-hali`
- `entegrator-hali` projesine dokunulmayacak
- `rugskilim-panel`, eski projenin kopyasindan ayrilmis yeni projedir

## Git Status

- `rugskilim-panel` icinde yeni ve bagimsiz bir lokal git deposu baslatildi
- Eski projenin `.git` gecmisi tasinmadi
- Henuz ilk commit atilmadi
- Henuz yeni GitHub repo baglanmadi

## Domains

- `panel.rugskilim.com` -> `145.223.90.56`
- `supabase.rugskilim.com` -> `145.223.90.56`
- `studio.rugskilim.com` -> `145.223.90.56`

## VPS / Coolify

- Hostinger VPS satin alindi
- Coolify kuruldu
- Coolify uzerinde proje adi: `rugskilim-panel`
- Production environment aktif: `production`
- Uygulama resource'u: `rugskilim-panel`
- Supabase resource'u: `supabase-rugskilim`
- Tum production bilesenleri ayni VPS icinde, dis servis yok

## Supabase

- Coolify icinde self-host Supabase kuruldu
- Supabase service healthy durumda
- Supabase Studio aciliyor
- `supabase.rugskilim.com` Kong/API giris noktasi olarak dusunuluyor
- `studio.rugskilim.com` Supabase Studio arayuzu icin ayrildi

## Important Notes About Domains

- `supabase.rugskilim.com` tarayicida normal bir ana sayfa gostermek zorunda degil
- Bu domain daha cok API/Kong endpoint olarak kullanilacak
- `studio.rugskilim.com` tarayicidan rahat yonetim arayuzu icin daha uygundur

## Project Renaming Done

Asagidaki yerlerde yeni proje kimligi uygulanmaya baslandi:

- `README.md` -> `RugsKilim Panel`
- `streamlit/streamlit_app.py` -> panel title ve header `RugsKilim Panel`
- `vds/baslat.bat` -> Windows yol ornekleri `C:\\rugskilim-panel\\...`
- `vds/VDS_KURULUM.md` -> yeni proje klasor ismiyle guncellendi

## Intentionally Left As-Is For Now

- `shared/sheets.py` icindeki eski credentials fallback dosya isimleri simdilik duruyor
- Sebep: mevcut credential dosyasi varsa geciste sistemi hemen kirmamak
- Bunlar daha sonra yeni mimariye gecerken temizlenecek

## Current Architecture Reality

Eski kod tabani halen bu mantikta:

- `streamlit/` -> panel
- `shared/sheets.py` -> Google Sheets tabanli veri akisi
- `vds/orkestrator.py` -> worker mantigi

Yeni hedef mimari:

- `panel.rugskilim.com` -> yeni uygulama paneli
- `supabase.rugskilim.com` -> self-host Supabase backend
- `studio.rugskilim.com` -> Supabase Studio
- ileride Etsy + Shopify + auth + SaaS mantigi

## Confirmed Production Topology

Bu yapi ekran goruntulerinden teyit edildi ve bundan sonra varsayilan production gercegi olarak ele alinmali:

```text
VPS
 -> Coolify
 -> Project: rugskilim-panel
 -> Environment: production
    -> Application: rugskilim-panel
    -> Service Stack: supabase-rugskilim
```

Ek notlar:

- Domain `panel.rugskilim.com`, Coolify proxy uzerinden `rugskilim-panel` uygulamasina yonlenir.
- Supabase ayni sunucu icinde service stack olarak calisir.
- Ayri bir external database, hosted Supabase veya ayri production worker application'i varsayilmamali.

## What Was Decided

- Eski proje oldugu gibi korunacak
- Yeni urun `rugskilim-panel` olarak gelisecek
- Self-host Supabase ile devam edilecek
- Coolify ana deployment araci olacak
- Bu proje SaaS mantigina gore evrilecek

## Recommended Next Steps

1. `rugskilim-panel` icinde yeni `.env.example` ve deployment ayarlarini olustur
2. Supabase baglanti bilgilerini netlestir
3. SaaS veri modelini cikar:
   - users
   - organizations / tenants
   - stores
   - products
   - store_listings
   - jobs
   - oauth_tokens
4. Mevcut Streamlit/Sheets akisini yeni Supabase tabanli yapuya tasima plani yap
5. Yeni backend sec:
   - FastAPI veya
   - mevcut Python tabanini evrimlestirme
6. Sonra GitHub icin yeni repo ac ve bu projeyi ona bagla

## Suggested Rule For Next Chats

Yeni sohbette su sekilde devam etmek en sagliklisi:

- Calisma klasoru: `/Users/yasinayaz/Projeler/rugskilim-panel`
- `entegrator-hali` projesine dokunma
- Yeni mimariyi `rugskilim-panel` icinde kur
- Supabase self-host + Coolify + SaaS hedefiyle ilerle
- Production mimarisini tek VPS uzerindeki `Coolify -> rugskilim-panel app + supabase-rugskilim stack` yapisi olarak kabul et
