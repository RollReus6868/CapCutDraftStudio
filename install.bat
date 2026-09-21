@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Cai thu vien cho CapCut Draft Studio...
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo.
  echo [LOI] Cai that bai. Kiem tra Python 3.10-3.12 64-bit da cai chua.
)
pause
