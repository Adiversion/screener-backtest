@echo off
REM  Unattended daily job: refresh data, rebuild the stock-pick report and dashboard.
REM  Appends to reports\scheduled_run.log so you can see what happened.
cd /d "%~dp0"
echo ============================================================ >> "%~dp0reports\scheduled_run.log"
echo  Scheduled run started %DATE% %TIME% >> "%~dp0reports\scheduled_run.log"
echo ============================================================ >> "%~dp0reports\scheduled_run.log"
call "%~dp0RUN_BACKTEST.bat" auto >> "%~dp0reports\scheduled_run.log" 2>&1
echo  Scheduled run finished %DATE% %TIME% >> "%~dp0reports\scheduled_run.log"
exit /b 0