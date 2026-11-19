#!/usr/bin/env sh
# macOS / Linux: ./run.sh
set -e
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  python3 -m venv .venv
  . .venv/bin/activate
  pip install --upgrade pip
  pip install -r requirements.txt
else
  . .venv/bin/activate
fi
echo "Open http://127.0.0.1:8000 in Chrome or Edge"
exec uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
