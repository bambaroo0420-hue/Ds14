@echo off
cd /d "%~dp0"
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
@echo SAM 추론을 위해 torch와 torchvision, 체크포인트는 별도 설치해야 합니다.
pause

