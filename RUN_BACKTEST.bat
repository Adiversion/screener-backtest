@echo off
setlocal enabledelayedexpansion
title NSE Backtest and Stock-Quality Engine
cd /d "%~dp0"

REM  Usage:  RUN_BACKTEST.bat            -> interactive menu (double-click)
REM          RUN_BACKTEST.bat auto       -> refresh data + stock picks, no UI
REM          RUN_BACKTEST.bat full       -> everything, unattended
REM          RUN_BACKTEST.bat screen     -> stock picks only, unattended
set "ARG=%~1"
set "NOUI="
set "choice="
if /i "%ARG%"=="auto" set "NOUI=1"
if /i "%ARG%"=="screen" set "NOUI=1"
if /i "%ARG%"=="full" set "NOUI=1"
if /i "%ARG%"=="auto" set "choice=3"
if /i "%ARG%"=="screen" set "choice=3"
if /i "%ARG%"=="full" set "choice=4"

if defined NOUI goto setup

echo ============================================================
echo    NSE Backtest + Stock-Quality Engine
echo    folder: %CD%
echo ============================================================
echo.

:setup
set "PY=python"
where py >nul 2>nul && set "PY=py"
%PY% --version >nul 2>nul
if errorlevel 1 goto nopython
if not defined NOUI for /f "delims=" %%v in ('%PY% --version 2^>^&1') do echo Using %%v

echo.
echo [1/4] Installing / updating dependencies...
%PY% -m pip install --quiet --disable-pip-version-check -r requirements.txt
if errorlevel 1 echo [WARN] pip reported a problem - continuing with what is installed.

echo.
echo [2/4] Downloading the latest Nifty-500 daily data...
echo       (this replaces data\universe_history.parquet)
%PY% scripts\fetch_data.py --source nifty500 --start 2018-01-01 --limit 501
if errorlevel 1 echo [WARN] data refresh failed - using the data already in the data folder.

if defined choice goto dispatch

echo.
echo [3/4] What should I run?
echo    1  Quick backtest   - protocol strategies only  (about 5 min)
echo    2  Full backtest    - ALL strategies, full universe  (about 15 min)
echo    3  Stock picks     - ranked quality shortlist + evidence  (recommended)
echo    4  Everything       - full backtest + stock picks  (recommended)
echo.
set "choice=4"
set /p "choice=Enter 1-4 [4]: "
if "!choice!"=="" set "choice=4"

:dispatch
if /i "!choice!"=="3" goto screen
if /i "!choice!"=="1" %PY% scripts\run_backtest.py --strategies protocol --capital 1000
if /i "!choice!"=="2" %PY% scripts\run_backtest.py --strategies all --capital 1000
if /i "!choice!"=="4" %PY% scripts\run_backtest.py --strategies all --capital 1000
if /i "!choice!"=="1" %PY% scripts\build_report.py
if /i "!choice!"=="2" %PY% scripts\build_report.py
if /i "!choice!"=="4" %PY% scripts\build_report.py

:screen
echo.
echo [4/4] Ranking stocks and building the candidate board...
%PY% scripts\decisions.py --top 10
%PY% scripts\screen_candidates.py

if defined NOUI goto finished
echo.
echo Opening the dashboards...
if exist "reports\dashboard.html" start "" "reports\dashboard.html"
if exist "reports\REPORT.html" start "" "reports\REPORT.html"
echo.
echo ============================================================
echo  Done. Everything is in the "reports" folder:
echo    REPORT.html    - strategy comparison (dynamic)
echo    REPORT.md      - same, in text
echo    report.json    - machine readable (metrics only)
echo    dashboard.html - trap / safe / organic board
echo    DECISIONS.md   - ranked good stocks + why + historical evidence
echo    CANDIDATES.md  - full session tag board
echo ============================================================
echo.
pause
exit /b 0

:finished
echo.
echo Unattended run finished at %DATE% %TIME%.
exit /b 0

:nopython
echo [ERROR] Python was not found on this PC.
echo         Install it from https://www.python.org/downloads/ and tick
echo         "Add python.exe to PATH", then run this file again.
if not defined NOUI pause
exit /b 1
