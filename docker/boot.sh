#!/bin/sh
set -eu

mkdir -p /app/.runtime/secrets /tmp/etsy_temp

if [ -n "${GOOGLE_CREDS_JSON_CONTENT:-}" ]; then
  printf '%s' "$GOOGLE_CREDS_JSON_CONTENT" > /app/.runtime/secrets/google-creds.json
  export GOOGLE_CREDS_JSON=/app/.runtime/secrets/google-creds.json
fi

if [ -n "${ETSY_TOKEN_JSON_CONTENT:-}" ]; then
  printf '%s' "$ETSY_TOKEN_JSON_CONTENT" > /app/vds/token.json
fi

case "${1:-panel}" in
  panel)
    shift || true
    exec /app/docker/start-panel.sh "$@"
    ;;
  worker)
    shift || true
    exec /app/docker/start-worker.sh "$@"
    ;;
  *)
    exec "$@"
    ;;
esac
