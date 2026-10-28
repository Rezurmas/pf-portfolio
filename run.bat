@echo off
title PF - Portfolio Fotograficzne
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo [PF] Pierwsze uruchomienie - tworze srodowisko i instaluje zaleznosci...
  python -m venv .venv
  .venv\Scripts\python.exe -m pip install --upgrade pip
  .venv\Scripts\python.exe -m pip install -r requirements.txt
)

echo [PF] Start serwera na porcie 8000...
echo [PF] Strona: http://localhost:8000
echo [PF] Panel: http://localhost:8000/admin
start "" http://localhost:8000
.venv\Scripts\python.exe -m uvicorn app:app --host 0.0.0.0 --port 8000
pause
