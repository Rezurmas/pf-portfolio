#!/usr/bin/env bash
# PF - portfolio fotograficzne. Jeden plik = instalacja (pierwszy raz) + start.
set -e
cd "$(dirname "$0")"

PY=python3
command -v python3 >/dev/null 2>&1 || PY=python

if [ ! -x ".venv/bin/python" ]; then
  echo "[PF] Pierwsze uruchomienie - tworze .venv i instaluje zaleznosci..."
  "$PY" -m venv .venv
  .venv/bin/pip install --upgrade pip --no-cache-dir
  .venv/bin/pip install -r requirements.txt --no-cache-dir
fi

echo "[PF] Start serwera na http://0.0.0.0:8000 (panel: /admin)"
exec .venv/bin/uvicorn app:app --host 0.0.0.0 --port 8000
