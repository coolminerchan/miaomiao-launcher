@echo off
setlocal DisableDelayedExpansion
chcp 65001 >nul
if "%~1"=="" (
    echo Drag a .pcapng file onto this script, or pass it as the first argument.
    pause
    exit /b 2
)
set "backup_python=%~dp0tools\python\python.exe"
if defined OVERFIELD_BACKUP_PYTHON set "backup_python=%OVERFIELD_BACKUP_PYTHON%"
"%backup_python%" -B -X utf8 "%~dp0parse_pcap.py" "%~1"
set "backup_exit=%ERRORLEVEL%"
pause
exit /b %backup_exit%
