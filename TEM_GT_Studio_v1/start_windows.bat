@echo off
cd /d "%~dp0"
if exist .venv\Scripts\python.exe (
 .venv\Scripts\python app.py
) else (
 python app.py
)
pause
