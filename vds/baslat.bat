@echo off
REM ── Ortak ayarlar (tüm VDS'lerde aynı) ──────────────────────────────────
set GOOGLE_SHEET_ID=1927qUbprn8NEK3-tYFddelZNfxGzCQsiJ8sl_usLHV4
set GOOGLE_CREDS_JSON=C:\rugskilim-panel\streamlit\credentials.json
set TEMP_DIR=C:\etsy_temp

REM ── Bu VDS'e özel ayarlar → vds\.env dosyasına yaz (git pull etkilemez) ──
REM vds\.env içeriği örneği:
REM   STORE_ID=RugsShopTurkey
REM
REM orkestrator.py başlangıçta vds\.env'i otomatik okur.

cd /d C:\rugskilim-panel\vds
python orkestrator.py
pause
