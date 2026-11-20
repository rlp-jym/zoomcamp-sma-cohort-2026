@echo off
setlocal
cd /d "%~dp0"
set "ROOT=%~dp0.."

if not exist local_data mkdir local_data

rem "scheduled" is a marker from Task Scheduler, not a python argument
set "PYARGS=%*"
if /i "%~1"=="scheduled" set "PYARGS="

echo Running the daily signal pipeline ...
uv run --project "%ROOT%" python -m deploy.main %PYARGS% >> local_data\run.log 2>&1
set CODE=%ERRORLEVEL%

echo.
echo --- last lines of local_data\run.log ---
powershell -NoProfile -Command "Get-Content 'local_data\run.log' -Tail 14"
echo.

if not "%CODE%"=="0" (
    echo Run failed with code %CODE%.
    if /i not "%~1"=="scheduled" pause
    exit /b %CODE%
)

rem Task Scheduler must not wait for a keypress
if /i not "%~1"=="scheduled" pause
exit /b 0
