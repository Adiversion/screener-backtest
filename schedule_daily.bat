@echo off
setlocal
title NSE Backtest - daily scheduler
cd /d "%~dp0"

REM  schedule_daily.bat install [HH:MM]   -> create the daily task (default 19:00)
REM  schedule_daily.bat remove            -> delete the task
REM  schedule_daily.bat run               -> run the job right now
REM  schedule_daily.bat status            -> show the task

set "TASK=NSE Backtest Engine"
set "ACTION=%1"
set "WHEN=%2"
if "%WHEN%"=="" set "WHEN=19:00"

if /i "%ACTION%"=="remove" goto remove
if /i "%ACTION%"=="run" goto run
if /i "%ACTION%"=="status" goto status
if /i "%ACTION%"=="install" goto install
goto usage

:install
echo Creating the daily task "%TASK%" at %WHEN% ...
schtasks /Create /F /SC DAILY /ST %WHEN% /TN "%TASK%" /TR "\"%~dp0run_daily.bat\""
if errorlevel 1 (
  echo.
  echo [ERROR] Could not create the task. Try running this file as Administrator.
  pause
  exit /b 1
)
echo.
echo Installed. The PC will refresh data and rebuild the dashboard every day at %WHEN%.
echo It only runs when the PC is on and the user is logged in.
echo Remove it any time with:  schedule_daily.bat remove
echo.
pause
exit /b 0

:remove
schtasks /Delete /F /TN "%TASK%"
echo.
echo Removed "%TASK%".
pause
exit /b 0

:run
echo Running the job now (unattended)...
cmd /c ""%~dp0run_daily.bat""
echo Done. See reports\scheduled_run.log
pause
exit /b 0

:status
schtasks /Query /TN "%TASK%" /V /FO LIST
pause
exit /b 0

:usage
echo Usage:
echo   schedule_daily.bat install [HH:MM]   create the daily task (default 19:00)
echo   schedule_daily.bat remove            delete the task
echo   schedule_daily.bat run               run the job now
echo   schedule_daily.bat status            show the task
echo.
pause
exit /b 1
