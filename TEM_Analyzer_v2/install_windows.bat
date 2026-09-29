@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" python -m venv .venv
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 exit /b 1
@echo SAM 추론을 위해 torch와 torchvision, 체크포인트는 별도 설치해야 합니다.
pause

