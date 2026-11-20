@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    where py >nul 2>&1
    if errorlevel 1 (
        python -m venv .venv
    ) else (
        py -3 -m venv .venv
    )
    if errorlevel 1 exit /b 1
)

".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" make_demo_db.py
if errorlevel 1 exit /b 1

echo Dashboard: http://127.0.0.1:8080
echo Press Ctrl+C to stop the server.
".venv\Scripts\python.exe" dashboard.py --host 127.0.0.1 --port 8080 --db demo_zever.db