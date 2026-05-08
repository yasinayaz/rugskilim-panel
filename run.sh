#!/bin/bash

set -u

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$ROOT_DIR/streamlit"

cd "$APP_DIR" || exit 1

run_streamlit() {
  "$@" run streamlit_app.py
}

if [ -x "$ROOT_DIR/.venv/bin/streamlit" ]; then
  run_streamlit "$ROOT_DIR/.venv/bin/streamlit"
  exit $?
fi

if [ -x "$HOME/Library/Python/3.9/bin/streamlit" ]; then
  run_streamlit "$HOME/Library/Python/3.9/bin/streamlit"
  exit $?
fi

if command -v streamlit >/dev/null 2>&1; then
  run_streamlit streamlit
  exit $?
fi

if python3 -m streamlit --version >/dev/null 2>&1; then
  python3 -m streamlit run streamlit_app.py
  exit $?
fi

echo "Streamlit bulunamadi."
echo "Calistirmak icin asagidakilerden birini yap:"
echo "1. Proje kokunde .venv olusturup icine streamlit kur"
echo "2. Veya: python3 -m pip install --user streamlit"
read -r -p "Kapatmak icin Enter'a basin..." _
