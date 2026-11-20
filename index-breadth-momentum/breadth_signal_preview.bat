@echo off
setlocal
cd /d "%~dp0"
set "ROOT=%~dp0.."

echo Preview only: no Telegram, no price refresh.
uv run --project "%ROOT%" python -m deploy.main --dry-run --offline
if errorlevel 1 (
    echo.
    echo Preview failed. Run breadth_setup.bat first.
    pause
    exit /b 1
)

pause
exit /b 0
