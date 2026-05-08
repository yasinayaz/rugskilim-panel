#!/bin/sh
set -eu

cd /app/vds

exec python orkestrator.py
