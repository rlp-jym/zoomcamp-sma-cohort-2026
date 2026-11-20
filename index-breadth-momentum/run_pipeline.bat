@echo off
setlocal
cd /d "%~dp0"
set "ROOT=%~dp0.."

uv sync --project "%ROOT%"
if errorlevel 1 goto :fail

for %%M in (edgar tickers holdings exclusions prices verify constituents) do (
    echo.
    echo === breadth.%%M ===
    uv run --project "%ROOT%" python -m breadth.%%M
    if errorlevel 1 goto :fail
)

echo.
echo Pipeline done: data\constituents\sp500_constituents_daily.parquet
pause
exit /b 0

:fail
echo.
echo Pipeline stopped. Check the message above.
pause
exit /b 1
