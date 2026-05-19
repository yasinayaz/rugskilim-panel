@echo off
setlocal
title LoopRug - Kurulum ve Baslatici

echo =======================================================
echo   LoopRug - Otomatik Kurulum ve Baslatici
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

REM ── Gecici klasor ve INDIR butonu ───────────────────────
if not exist "C:\etsy_temp\LoopRug" mkdir "C:\etsy_temp\LoopRug"
echo [OK] Klasor hazir: C:\etsy_temp\LoopRug

if not exist "C:\etsy_temp\LoopRug\INDIR.bat" (
  (
    echo @echo off
    echo title LoopRug - Otomasyon
    echo call "C:\rugskilim-panel\vds\LOOPRUG_KUR_VE_BASLAT.bat"
  ) > "C:\etsy_temp\LoopRug\INDIR.bat"
  echo [OK] INDIR.bat olusturuldu: C:\etsy_temp\LoopRug\INDIR.bat
)

REM ── .env kontrol ─────────────────────────────────────────
if not exist "C:\rugskilim-panel\vds\.env" (
  copy "C:\rugskilim-panel\vds\LOOPRUG_env.txt" "C:\rugskilim-panel\vds\.env" >nul
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
set "STORE_ID=LoopRug"
set "GOOGLE_SHEET_ID=12zcGd3Ila-y_aZWCldNZUeJp-1yBrz_Uvh4Yf3U0f7o"
set "GOOGLE_CREDS_JSON=C:\rugskilim-panel\streamlit\credentials.json"
set "TEMP_DIR=C:\etsy_temp\LoopRug"

call "C:\rugskilim-panel\vds\baslat.bat"
