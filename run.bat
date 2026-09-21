@echo off
chcp 65001 >nul
cd /d "%~dp0"
if exist ".venv\Scripts\pythonw.exe" (
  start "" ".venv\Scripts\pythonw.exe" -m capcut_draft_studio.app
  exit /b 0
)
python -m capcut_draft_studio.app
if errorlevel 1 pause
