@echo off
setlocal
title RugsShopTurkey - Kurulum ve Baslatici

echo =======================================================
echo   RugsShopTurkey - Otomatik Kurulum ve Baslatici
echo =======================================================
echo.

REM ── Python kontrol ──────────────────────────────────────
set "PYTHON_CMD="
where python >nul 2>nul && set "PYTHON_CMD=python"
if not defined PYTHON_CMD (
  where py >nul 2>nul && set "PYTHON_CMD=py"
)
if not defined PYTHON_CMD (
  echo HATA: Python kurulu degil!
  echo Lutfen https://www.python.org/downloads/windows/ adresinden indirin.
  echo Kurulumda "Add Python to PATH" kutusunu isaretleyin.
  pause
  exit /b 1
)
echo [OK] Python bulundu: %PYTHON_CMD%

REM ── Git kontrol ─────────────────────────────────────────
where git >nul 2>nul
if errorlevel 1 (
  echo HATA: Git kurulu degil!
  echo Lutfen https://git-scm.com/download/win adresinden indirin.
  pause
  exit /b 1
)
echo [OK] Git bulundu.

REM ── Repo indir veya guncelle ────────────────────────────
if exist "C:\rugskilim-panel\.git" (
  echo [..] Repo guncelleniyor...
  cd /d C:\rugskilim-panel
  git pull
) else (
  echo [..] Repo indiriliyor...
  cd /d C:\
  git clone https://github.com/yasinayaz/rugskilim-panel.git
)
echo [OK] Repo hazir.

REM ── Python bagimliliklar ─────────────────────────────────
echo [..] Python paketleri kuruluyor...
%PYTHON_CMD% -m pip install --quiet gspread google-auth httpx opencv-python numpy requests
echo [OK] Paketler hazir.

REM ── Gecici klasor ────────────────────────────────────────
if not exist "C:\etsy_temp\RugsShopTurkey" mkdir "C:\etsy_temp\RugsShopTurkey"
echo [OK] Klasor hazir: C:\etsy_temp\RugsShopTurkey

REM ── .env kontrol ─────────────────────────────────────────
if not exist "C:\rugskilim-panel\vds\.env" (
  copy "C:\rugskilim-panel\vds\RUGSSHOPTURKEY_env.txt" "C:\rugskilim-panel\vds\.env" >nul
  echo [OK] .env olusturuldu.
  echo.
  echo !! DIKKAT: C:\rugskilim-panel\vds\.env dosyasini Not Defteri ile acip
  echo !! PCLOUD_TOKEN satirina gercek token degerini yazin, sonra tekrar calistirin.
  pause
  exit /b 0
)
echo [OK] .env mevcut.

REM ── Worker baslat ────────────────────────────────────────
echo.
echo =======================================================
echo   Baslatiliyor...
echo =======================================================
set "STORE_ID=RugsShopTurkey"
set "GOOGLE_SHEET_ID=12zcGd3Ila-y_aZWCldNZUeJp-1yBrz_Uvh4Yf3U0f7o"
set "GOOGLE_CREDS_JSON=C:\rugskilim-panel\streamlit\credentials.json"
set "TEMP_DIR=C:\etsy_temp\RugsShopTurkey"

call "C:\rugskilim-panel\vds\baslat.bat"
