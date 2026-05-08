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

### 5. `baslat.bat` içindeki ortak ayarları kontrol et

`C:\rugskilim-panel\vds\baslat.bat` dosyasında şunların doğru olduğundan emin ol:
```
GOOGLE_SHEET_ID=1927qUbprn8NEK3-tYFddelZNfxGzCQsiJ8sl_usLHV4
GOOGLE_CREDS_JSON=C:\rugskilim-panel\streamlit\credentials.json
TEMP_DIR=C:\etsy_temp
```

### 6. Çalıştır
```
C:\rugskilim-panel\vds\baslat.bat
```

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
