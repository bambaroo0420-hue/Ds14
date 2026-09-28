@echo off
cd /d "%~dp0"
python -m venv .venv
if errorlevel 1 goto fail
.venv\Scripts\python -m pip install -r requirements.txt
if errorlevel 1 goto fail
echo Installed. Run start_windows.bat
pause
exit /b 0
:fail
echo Installation failed. Check Python 3.10+ and network or offline wheel folder.
pause
exit /b 1
