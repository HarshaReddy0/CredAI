@echo off
REM Windows: double-click to run. Creates a virtual env on first run.
cd /d %~dp0
if not exist .venv (
  python -m venv .venv
  call .venv\Scripts\activate
  python -m pip install --upgrade pip
  pip install -r requirements.txt
) else (
  call .venv\Scripts\activate
)
echo Open http://127.0.0.1:8000 in Chrome or Edge
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
