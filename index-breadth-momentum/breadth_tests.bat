@echo off
setlocal
cd /d "%~dp0"
set "ROOT=%~dp0.."

uv run --project "%ROOT%" pytest -q
pause
exit /b %errorlevel%
