@echo off
chcp 65001 >nul
cd /d "%~dp0"
title buildScanner

where py >nul 2>nul && (set "PY=py -3") || (set "PY=python")
%PY% --version >nul 2>nul
if errorlevel 1 (
  echo Chua cai Python. Hay tai Python 3.10+ tai https://www.python.org/downloads/
  echo Khi cai, nho tick o "Add python.exe to PATH".
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo [1/2] Tao moi truong Python lan dau...
  %PY% -m venv .venv || (pause & exit /b 1)
)

".venv\Scripts\python.exe" -c "import flask, waitress, cv2, img2pdf, qrcode, pillow_heif" >nul 2>nul
if errorlevel 1 (
  echo [2/2] Cai thu vien can thiet - chi lam lan dau, mat vai phut...
  ".venv\Scripts\python.exe" -m pip install --upgrade pip
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt || (pause & exit /b 1)
)

".venv\Scripts\python.exe" app.py %*
pause
