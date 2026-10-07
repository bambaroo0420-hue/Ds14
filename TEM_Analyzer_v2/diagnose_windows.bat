@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Virtual environment missing. Run install_windows.bat once.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" check_environment.py --verbose
".venv\Scripts\python.exe" -m pip check
echo No settings, projects, or packages were changed.
pause
