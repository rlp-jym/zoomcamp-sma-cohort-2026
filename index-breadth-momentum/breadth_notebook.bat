@echo off
setlocal
cd /d "%~dp0"
set "ROOT=%~dp0.."

uv sync --project "%ROOT%"
if errorlevel 1 goto :fail

if /i "%~1"=="exec" (
    echo Executing the notebook and writing docs\notebook.html ...
    uv run --project "%ROOT%" python -m nbconvert --to html --execute ^
        --output-dir docs --output notebook ^
        --ExecutePreprocessor.timeout=1800 notebook.ipynb
    if errorlevel 1 goto :fail
    echo.
    echo Done: docs\notebook.html
    pause
    exit /b 0
)

uv run --project "%ROOT%" python -m jupyterlab notebook.ipynb
exit /b 0

:fail
echo.
echo Something failed. Run breadth_setup.bat first.
pause
exit /b 1
