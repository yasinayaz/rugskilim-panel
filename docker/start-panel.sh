#!/bin/sh
set -eu

cd /app/streamlit

exec python -m streamlit run streamlit_app.py \
  --server.address=0.0.0.0 \
  --server.port="${PORT:-8501}" \
  --server.headless=true \
  --browser.gatherUsageStats=false
