@echo off
setlocal

REM ── Dizinler ──────────────────────────────────────────────────────────────
set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "REPO_DIR=%%~fI"
set "ENV_FILE=%SCRIPT_DIR%.env"

REM ── vds\.env oku (varsa) ─────────────────────────────────────────────────
if exist "%ENV_FILE%" (
  for /f "usebackq tokens=1,* delims==" %%A in ("%ENV_FILE%") do (
    if not "%%~A"=="" (
      if /I not "%%~A:~0,1%%"=="#" (
        set "%%~A=%%~B"
      )
    )
  )
)

REM ── Ortak / varsayılan ayarlar ───────────────────────────────────────────
if not defined GOOGLE_SHEET_ID set "GOOGLE_SHEET_ID=1927qUbprn8NEK3-tYFddelZNfxGzCQsiJ8sl_usLHV4"
if not defined GOOGLE_CREDS_JSON set "GOOGLE_CREDS_JSON=%REPO_DIR%\streamlit\credentials.json"
if not defined TEMP_DIR set "TEMP_DIR=C:\etsy_temp"

echo =======================================================
echo   RugsKilim VDS Baslatici
echo =======================================================
echo   STORE_ID          = %STORE_ID%
echo   GOOGLE_SHEET_ID   = %GOOGLE_SHEET_ID%
echo   GOOGLE_CREDS_JSON = %GOOGLE_CREDS_JSON%
echo   TEMP_DIR          = %TEMP_DIR%
echo =======================================================

if not defined STORE_ID (
  echo HATA: STORE_ID tanimli degil.
  echo Cozum: %ENV_FILE% dosyasina STORE_ID=OldNewRugs gibi bir satir ekleyin.
  pause
  exit /b 1
)

if not exist "%GOOGLE_CREDS_JSON%" (
  echo HATA: Google credentials dosyasi bulunamadi:
  echo   %GOOGLE_CREDS_JSON%
  pause
  exit /b 1
)

where python >nul 2>nul
if errorlevel 1 (
  echo HATA: Python bulunamadi. Python 3.10+ kurulu olmali ve PATH'te olmali.
  pause
  exit /b 1
)

cd /d "%SCRIPT_DIR%"
python orkestrator.py
pause
