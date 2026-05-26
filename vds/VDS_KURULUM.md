# VDS Kurulum Kılavuzu

Her mağazanın VDS'i ayrıdır. Kod aynı git repo'dan gelir, mağaza ayrımı sadece `vds\.env` dosyasıyla yapılır.

---

## Gereksinimler

- Windows Server (VDS)
- Python 3.10+ kurulu
- Git kurulu
- Google Service Account JSON dosyası (`credentials.json`)

---

## İlk Kurulum (Bir Kez)

### 1. Repoyu klonla
```
git clone <repo_url> C:\rugskilim-panel
```

### 2. Python bağımlılıklarını yükle
```
cd C:\rugskilim-panel
pip install gspread google-auth httpx opencv-python numpy
```

### 3. Google credentials dosyasını kopyala
Service account JSON dosyasını şu konuma koy:
```
C:\rugskilim-panel\streamlit\credentials.json
```

### 4. `vds\.env` dosyasını oluştur (Notepad ile)

Bu dosya git'te YOK — `git pull` hiç dokunmaz.

```
C:\rugskilim-panel\vds\.env
```

İçeriği (bu VDS hangi mağazayı işliyorsa):
```
STORE_ID=PatchArts
```

`OldNewRugs` bilgisayari icin ornek:
```
STORE_ID=OldNewRugs
GOOGLE_SHEET_ID=12zcGd3Ila-y_aZWCldNZUeJp-1yBrz_Uvh4Yf3U0f7o
GOOGLE_CREDS_JSON=C:\rugskilim-panel\streamlit\credentials.json
TEMP_DIR=C:\etsy_temp\OldNewRugs
```

Hazir ornek dosya repo icinde vardir:
`C:\rugskilim-panel\vds\.env.example`

Windows'ta `.env.example` dosyasi acilmazsa veya ugrastirirsa su kolay acilan dosyayi kullan:
`C:\rugskilim-panel\vds\OLDNEWRUGS_env.txt`

LoomixRugs bilgisayari icin hazir dosya:
`C:\rugskilim-panel\vds\LOOMIXRUGS_env.txt`

WovenTurkishRugs bilgisayari icin hazir dosya:
`C:\rugskilim-panel\vds\WOVENTURKISHRUGS_env.txt`

WovenLoomRugs bilgisayari icin hazir dosya:
`C:\rugskilim-panel\vds\WOVENLOOMRUGS_env.txt`

Yapilacak islem:
1. `OLDNEWRUGS_env.txt` dosyasini ac
2. `Farkli Kaydet` ile ayni klasore `.env` olarak kaydet
3. Gerekirse sadece degerleri duzenle

### 5. `baslat.bat` içindeki ortak ayarları kontrol et

`C:\rugskilim-panel\vds\baslat.bat` dosyasında şunların doğru olduğundan emin ol:
```
GOOGLE_SHEET_ID=12zcGd3Ila-y_aZWCldNZUeJp-1yBrz_Uvh4Yf3U0f7o
GOOGLE_CREDS_JSON=C:\rugskilim-panel\streamlit\credentials.json
TEMP_DIR=C:\etsy_temp
```

### 6. Çalıştır
```
C:\rugskilim-panel\vds\baslat.bat
```

OldNewRugs bilgisayari icin personel komut yazmayacaksa dogrudan su dosyaya cift tiklayabilir:
```
C:\rugskilim-panel\vds\OLDNEWRUGS_BASLAT.bat
```

Bu dosya `STORE_ID=OldNewRugs` ile otomatik baslatir.

LoomixRugs bilgisayari icin ilk kurulum / guncelleme baslaticisi:
```
C:\rugskilim-panel\vds\LOOMIXRUGS_KUR_VE_BASLAT.bat
```

Bu dosya:
- repo'yu `git pull` ile gunceller
- gerekli Python paketlerini kurar
- `C:\etsy_temp\LoomixRugs` klasorunu hazirlar
- `C:\etsy_temp\LoomixRugs_INDIR.bat` kisayolunu olusturur
- worker'i `STORE_ID=LoomixRugs` ile baslatir

WovenTurkishRugs bilgisayari icin ilk kurulum / guncelleme baslaticisi:
```
C:\rugskilim-panel\vds\WOVENTURKISHRUGS_KUR_VE_BASLAT.bat
```

Bu dosya:
- repo'yu `git pull` ile gunceller
- gerekli Python paketlerini kurar
- `C:\etsy_temp\WovenTurkishRugs` klasorunu hazirlar
- `C:\etsy_temp\WovenTurkishRugs_INDIR.bat` kisayolunu olusturur
- worker'i `STORE_ID=WovenTurkishRugs` ile baslatir

WovenLoomRugs bilgisayari icin ilk kurulum / guncelleme baslaticisi:
```
C:\rugskilim-panel\vds\WOVENLOOMRUGS_KUR_VE_BASLAT.bat
```

Bu dosya:
- repo'yu `git pull` ile gunceller
- gerekli Python paketlerini kurar
- `C:\etsy_temp\WovenLoomRugs` klasorunu hazirlar
- `C:\etsy_temp\WovenLoomRugs_INDIR.bat` kisayolunu olusturur
- worker'i `STORE_ID=WovenLoomRugs` ile baslatir

---

## Streamlit ile ortaklik mantigi

Bu yapida Streamlit ile Windows worker ortak bir yerel klasor kullanmak zorunda degil.
Gercek ortak alanlar sunlardir:

- ayni `GOOGLE_SHEET_ID`
- ayni magaza/store kimligi
- ayni pCloud kaynagi

OldNewRugs bilgisayari icin eslesme soyle olmalidir:

- Streamlit'te `Hedef Magaza` = `OldNewRugs`
- Windows `STORE_ID` = `OldNewRugs`
- Sheet sekmesi = `OldNewRugs`
- Gerekirse `google_sheet_id` ayni sheet'i gostermeli

Yani Streamlit `ready` yazdigi zaman, Windows worker ayni sheet'teki `OldNewRugs` sekmesinden bu urunleri alip isler.

`TEMP_DIR` altindaki klasor sadece Windows worker'indir. Streamlit bu klasoru okumaz.
Eger bir gun ayni fiziksel Windows makinede Streamlit de calisacaksa, yine ortak nokta sheet olacaktir; dosya klasoru entegrasyonu su anki kodda yoktur.

---

## Mağaza → STORE_ID Tablosu

| VDS | `STORE_ID` | Sheet Sekmesi |
|-----|------------|---------------|
| VDS-1 | `PatchArts` | PatchArts |
| VDS-2 | `OldNewRugs` | OldNewRugs |
| VDS-3 | `LoopRug` | LoopRug |
| VDS-4 | `LoomixRugs` | LoomixRugs |
| VDS-5 | `RugsShopTurkey` | RugsShopTurkey |
| VDS-6 | `WovenTurkishRugs` | WovenTurkishRugs |
| VDS-7 | `BohoRugHouse` | BohoRugHouse |
| VDS-8 | `İlmekRug` | İlmekRug |
| VDS-9 | `WoolCottonRugs` | WoolCottonRugs |
| VDS-10 | `WowenLoomRugs` | WowenLoomRugs |
| VDS-11 | `RugskilimLLC` | RugskilimLLC |
| VDS-12 | `LoomAntikRugs` | LoomAntikRugs |

---

## Güncelleme (git pull Sonrası)

```
cd C:\rugskilim-panel
git pull
vds\baslat.bat
```

`vds\.env` gitignore'da olduğu için `git pull` bu dosyaya dokunmaz.  
`STORE_ID` her güncellemeden sonra korunur — hiçbir şey değiştirmene gerek yok.

---

## Google Hesabı Değişirse

Yeni hesap için:
1. Google Cloud'da yeni service account oluştur → JSON indir
2. JSON dosyasını `C:\rugskilim-panel\streamlit\` altına koy
3. `baslat.bat` içinde `GOOGLE_CREDS_JSON` yolunu güncelle
4. Yeni service account'u Google Sheet'e editör olarak ekle

Kod değişmez. Tüm VDS'lerde aynı adımlar uygulanır.

---

## Sorun Giderme

**"Mağaza bulunamadı" hatası:**  
`vds\.env` dosyasındaki `STORE_ID` değeri `shared/stores.json`'daki `store_id` ile birebir aynı olmalı (büyük/küçük harf dahil).

**"GOOGLE_SHEET_ID eksik" hatası:**  
`baslat.bat` çalıştırılmadan `orkestrator.py` doğrudan çalıştırılmış olabilir. Daima `baslat.bat` üzerinden çalıştır.

**pCloud indirme hatası:**  
Token süresi dolmuş olabilir. Mac paneli → Ayarlar → pCloud token güncelle. Token Sheets config sekmesine yazılır, VDS otomatik okur.
