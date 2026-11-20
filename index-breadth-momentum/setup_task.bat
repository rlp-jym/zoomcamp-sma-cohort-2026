@echo off
setlocal
cd /d "%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_task.ps1"
if errorlevel 1 goto :fail

echo.
pause
exit /b 0

:fail
echo.
echo Registration failed. Run this file as Administrator, or create the task by hand.
pause
exit /b 1
