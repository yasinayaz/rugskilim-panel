@echo off
setlocal

REM PatchArts bilgisayari icin tek tik baslatici.
set "STORE_ID=PatchArts"
set "GOOGLE_SHEET_ID=12zcGd3Ila-y_aZWCldNZUeJp-1yBrz_Uvh4Yf3U0f7o"
set "GOOGLE_CREDS_JSON=C:\rugskilim-panel\streamlit\credentials.json"
set "TEMP_DIR=C:\etsy_temp\PatchArts"
set "PYTHON_CMD=py"

call "%~dp0baslat.bat"
