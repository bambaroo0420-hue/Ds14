@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Virtual environment missing. Run install_windows.bat once.
  pause
  exit /b 1
)
echo Open http://127.0.0.1:8765 in your browser.
".venv\Scripts\python.exe" run.py --port 8765
pause

