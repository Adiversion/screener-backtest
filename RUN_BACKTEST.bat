@echo off
setlocal enabledelayedexpansion
title NSE Strategy Backtest ^& Rotation Engine
cd /d "%~dp0"

echo ============================================================
echo    NSE Strategy Backtest + Rotation Engine
echo    folder: %CD%
echo ============================================================
echo.

REM ---------- 1. locate Python ----------
set "PY=python"
where py >nul 2>nul && set "PY=py"
%PY% --version >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python was not found on this PC.
  echo         Install it from https://www.python.org/downloads/ and tick
  echo         "Add python.exe to PATH", then run this file again.
  echo.
  pause
  exit /b 1
)
for /f "delims=" %%v in ('%PY% --version 2^>^&1') do echo Using %%v

REM ---------- 2. dependencies ----------
echo.
echo [1/4] Installing / updating dependencies...
%PY% -m pip install --quiet --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
  echo [WARN] pip install reported a problem - continuing with what is installed.
)

REM ---------- 3. fresh market data ----------
echo.
echo [2/4] Downloading the latest Nifty-500 daily data...
echo       (this replaces data\universe_history.parquet)
%PY% scripts\fetch_data.py --source nifty500 --start 2018-01-01 --limit 501
if errorlevel 1 (
  echo [WARN] data refresh failed - using the data already in the data folder.
)

REM ---------- 4. what to run ----------
echo.
echo [3/4] What should I run?
echo    1  Quick backtest   - protocol strategies only  (~5 min)
echo    2  Full backtest    - ALL strategies, full universe  (~15 min)
echo    3  Rotation screen  - "what to hold today" + dashboard
echo    4  Everything       - full backtest + rotation screen  (recommended)
echo.
set "choice=4"
set /p "choice=Enter 1-4 [4]: "
if "%choice%"=="" set "choice=4"

if "%choice%"=="3" goto screen
if "%choice%"=="1" %PY% scripts\run_backtest.py --strategies protocol --capital 1000
if "%choice%"=="2" %PY% scripts\run_backtest.py --strategies all --capital 1000
if "%choice%"=="4" %PY% scripts\run_backtest.py --strategies all --capital 1000

if "%choice%"=="1" goto report
if "%choice%"=="2" goto report
if "%choice%"=="4" goto report
goto screen

:report
%PY% scripts\build_report.py

:screen
echo.
echo [4/4] Building the rotation screen...
%PY% scripts\screen_candidates.py

echo.
echo Opening the dashboards...
if exist "reports\dashboard.html" start "" "reports\dashboard.html"
if exist "reports\REPORT.html" start "" "reports\REPORT.html"

echo.
echo ============================================================
echo  Done. Everything is in the "reports" folder:
echo    REPORT.html    - strategy comparison (dynamic)
echo    REPORT.md      - same, in text
echo    report.json    - machine readable
echo    dashboard.html - trap / safe / organic board
echo    ROTATION.md    - what to rotate into
echo ============================================================
echo.
pause
