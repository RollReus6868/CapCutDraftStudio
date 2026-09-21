@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
cd /d "%~dp0"
title Build CapCut Draft Studio

set "LOG=%CD%\build.log"
set "PYTMP=%TEMP%\ccds_pycheck.txt"
if exist "%LOG%" del /q "%LOG%" >nul 2>&1

echo. > "%LOG%"
echo ========== CapCut Draft Studio - build log ========== >> "%LOG%"
echo Thu muc: %CD% >> "%LOG%"
echo Ngay gio: %DATE% %TIME% >> "%LOG%"
echo. >> "%LOG%"

echo.
echo ==========================================================
echo   CapCut Draft Studio - dong goi thanh file .exe
echo ==========================================================
echo.
echo   Nhat ky chi tiet se duoc ghi vao: build.log
echo.

REM ---------- 1. Tim Python ----------
REM Khong dung "where" de quyet dinh: tren nhieu may Windows, python.exe/py.exe
REM chi la file gia (App Execution Alias) mo Microsoft Store, "where" van thay
REM no ton tai nhung chay thi khong ra gi ca. Phai GOI THU va doc ket qua that.
set "PY="
set "PYVER="

call :try_python "py -3"
if not defined PY call :try_python "python"
if not defined PY call :try_python "python3"

if not defined PY (
  echo [LOI] Khong tim thay Python that su hoat dong. >> "%LOG%"
  echo [LOI] Khong tim thay Python that su hoat dong.
  echo.
  echo   Nguyen nhan thuong gap NHAT: Windows dang chan lenh "python"/"py"
  echo   bang mot file gia mo Microsoft Store, ke ca khi ban da cai Python.
  echo.
  echo   CACH SUA - chon 1 trong 2:
  echo.
  echo   1^) Chua cai Python:
  echo      - Vao https://www.python.org/downloads/ , tai ban 3.10-3.12 (64-bit)
  echo      - Luc cai, TICK vao "Add python.exe to PATH"
  echo      - Cai xong thi dong cua so nay va chay lai BUILD_EXE.bat
  echo.
  echo   2^) Da cai Python roi ma van thay loi nay:
  echo      - Mo Settings ^> Apps ^> Advanced app settings ^> App execution aliases
  echo        (go "app execution aliases" vao o tim kiem cua Windows cung duoc)
  echo      - TAT 2 cong tac "python.exe" va "python3.exe"
  echo      - Chay lai BUILD_EXE.bat
  echo.
  if exist "%PYTMP%" del /q "%PYTMP%" >nul 2>&1
  pause
  exit /b 1
)
if exist "%PYTMP%" del /q "%PYTMP%" >nul 2>&1

echo [1/5] Python %PYVER% (dung lenh: %PY%)
echo [1/5] Python %PYVER% qua lenh "%PY%" >> "%LOG%"
%PY% -c "import sys;print('  executable:',sys.executable);print('  64-bit:',sys.maxsize>2**32)" >> "%LOG%" 2>&1

%PY% -c "import sys;sys.exit(0 if sys.version_info[:2]>=(3,10) else 1)" >nul 2>&1
if errorlevel 1 (
  echo [LOI] Can Python 3.10 tro len. Ban dang dung %PYVER%.
  echo [LOI] Python qua cu: %PYVER% >> "%LOG%"
  pause
  exit /b 1
)
%PY% -c "import tkinter" >>"%LOG%" 2>&1
if errorlevel 1 (
  echo [LOI] Ban Python nay thieu tkinter. Cai lai Python tu python.org
  echo       va tick muc "tcl/tk and IDLE".
  echo [LOI] Thieu tkinter >> "%LOG%"
  pause
  exit /b 1
)

REM ---------- 2. Moi truong ao ----------
echo [2/5] Chuan bi moi truong ao (.venv)...
echo. >> "%LOG%"
echo ===== [2/5] Moi truong ao ===== >> "%LOG%"

REM .venv cu co the hong (build do dang, doi phien ban Python, copy tu may khac).
REM Kiem tra bang cach chay thu; hong thi xoa lam lai tu dau.
set "VPY=%CD%\.venv\Scripts\python.exe"
if exist "%VPY%" (
  "%VPY%" -c "import sys" >>"%LOG%" 2>&1
  if errorlevel 1 (
    echo   - .venv cu bi hong, dang xoa de tao lai...
    echo   .venv cu hong -^> xoa >> "%LOG%"
    rmdir /s /q ".venv" >>"%LOG%" 2>&1
  )
)
if not exist "%VPY%" (
  %PY% -m venv .venv >>"%LOG%" 2>&1
  if errorlevel 1 (
    echo   - Tao .venv that bai, thu lai sau khi xoa sach...
    echo   venv lan 1 that bai >> "%LOG%"
    if exist ".venv" rmdir /s /q ".venv" >>"%LOG%" 2>&1
    %PY% -m venv --without-pip .venv >>"%LOG%" 2>&1
    if exist "%VPY%" "%VPY%" -m ensurepip --upgrade >>"%LOG%" 2>&1
  )
)
if not exist "%VPY%" (
  call :fail "Khong tao duoc moi truong ao .venv."
  exit /b 1
)

REM ---------- 3. Thu vien ----------
echo [3/5] Cai thu vien can thiet (lan dau se hoi lau)...
echo. >> "%LOG%"
echo ===== [3/5] Cai thu vien ===== >> "%LOG%"
"%VPY%" -m pip install --upgrade pip --disable-pip-version-check >>"%LOG%" 2>&1
"%VPY%" -m pip install -r requirements.txt --disable-pip-version-check >>"%LOG%" 2>&1
if errorlevel 1 (
  call :fail "Cai thu vien that bai. Kiem tra ket noi mang roi chay lai."
  exit /b 1
)
"%VPY%" -m pip install pyinstaller --disable-pip-version-check >>"%LOG%" 2>&1
if errorlevel 1 (
  call :fail "Cai PyInstaller that bai."
  exit /b 1
)
"%VPY%" -m pip list >>"%LOG%" 2>&1

REM ---------- 4. Dong goi ----------
echo [4/5] Dang dong goi... (thuong mat 1-3 phut)
echo. >> "%LOG%"
echo ===== [4/5] PyInstaller ===== >> "%LOG%"
if exist "build" rmdir /s /q "build" >nul 2>&1
if exist "dist" rmdir /s /q "dist" >nul 2>&1
"%VPY%" -m PyInstaller --noconfirm --clean --log-level INFO CapCutDraftStudio.spec >>"%LOG%" 2>&1
if errorlevel 1 (
  call :fail "PyInstaller dong goi that bai."
  exit /b 1
)

REM ---------- 5. Ket qua ----------
if not exist "dist\CapCut Draft Studio.exe" (
  call :fail "Chay xong nhung khong thay file .exe trong thu muc dist."
  exit /b 1
)
if exist "assets" (
  if not exist "dist\assets" mkdir "dist\assets"
  xcopy "assets" "dist\assets" /e /i /y /q >>"%LOG%" 2>&1
)
echo [5/5] Hoan tat. >> "%LOG%"

echo.
echo ==========================================================
echo   XONG!
echo.
echo   File chay:  %CD%\dist\CapCut Draft Studio.exe
echo.
echo   Copy ca thu muc "dist" sang may khac la dung duoc,
echo   khong can cai Python.
echo ==========================================================
echo.
start "" "%CD%\dist"
pause
exit /b 0

REM ---------- Ham phu: bao loi + in phan cuoi cua log ----------
:fail
echo.
echo [LOI] %~1
echo [LOI] %~1 >> "%LOG%"
echo.
echo   --- 25 dong cuoi cua build.log ---
powershell -NoProfile -Command "Get-Content -LiteralPath '%LOG%' -Tail 25" 2>nul
if errorlevel 1 (
  echo   (Khong doc duoc log tu dong. Hay mo file build.log.)
)
echo   ----------------------------------
echo.
echo   Nhat ky day du: %LOG%
echo   Gui file build.log nay de duoc ho tro sua dut diem.
echo.
echo   Trong luc cho, ban van dung tool duoc binh thuong:
echo   chay install.bat mot lan, sau do nhap dup run.bat
echo.
pause
exit /b 1

REM ---------- Ham phu: kiem tra 1 lenh Python co that su chay duoc khong ----------
REM %1 = lenh can thu (vi du "py -3", "python"). Neu hop le thi dat bien
REM PY va PYVER o pham vi ngoai (goi la tu script chinh, khong phai subshell).
:try_python
set "CAND=%~1"
%CAND% --version >"%PYTMP%" 2>&1
set "RC=%errorlevel%"
set "LINE="
if exist "%PYTMP%" (
  for /f "usebackq delims=" %%L in ("%PYTMP%") do if not defined LINE set "LINE=%%L"
)
echo   thu "%CAND%" -^> rc=%RC% out=%LINE% >> "%LOG%"
if not defined LINE exit /b 1
echo %LINE% | findstr /i "was not found" >nul
if not errorlevel 1 exit /b 1
if not "%RC%"=="0" exit /b 1
echo %LINE% | findstr /r /c:"^Python [0-9]" >nul
if errorlevel 1 exit /b 1
for /f "tokens=2" %%v in ("%LINE%") do set "PY=%CAND%" & set "PYVER=%%v"
exit /b 0
