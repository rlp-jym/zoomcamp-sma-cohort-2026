@echo off
setlocal

rem Launch the read-only dashboard.
rem   run_app.bat            -> http://localhost:8511
rem   run_app.bat 8600       -> http://localhost:8600
rem   set CRYPTO_HEADLESS=1  -> do not open a browser

cd /d "%~dp0"

set "PORT=%~1"
if "%PORT%"=="" set "PORT=8511"

set "HEADLESS=false"
if "%CRYPTO_HEADLESS%"=="1" set "HEADLESS=true"

echo.
echo   crypto-cross-pred dashboard
echo   http://localhost:%PORT%
echo.
echo   Ctrl+C to stop.
echo.

uv run streamlit run app/streamlit_app.py --server.port %PORT% --server.headless %HEADLESS%

if errorlevel 1 (
    echo.
    echo The app exited with an error.
    echo If the port is busy, try:  run_app.bat 8600
    pause
)

endlocal
