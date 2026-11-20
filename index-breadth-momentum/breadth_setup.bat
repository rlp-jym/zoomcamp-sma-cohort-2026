@echo off
setlocal
cd /d "%~dp0"
set "ROOT=%~dp0.."

echo Syncing the shared uv environment ...
uv sync --project "%ROOT%"
if errorlevel 1 goto :fail

echo.
echo Done. Next:
echo   breadth_tests.bat        run the test suite
echo   breadth_notebook.bat     open the notebook
echo   breadth_notebook.bat exec  execute it and export docs\notebook.html
echo   breadth_pipeline.bat     rebuild the dataset from EDGAR
echo   run_app.bat          start the Streamlit dashboard
echo   run_docker.bat       build and run the dashboard in Docker
echo.
pause
exit /b 0

:fail
echo.
echo Setup failed. Is uv installed? https://docs.astral.sh/uv/
pause
exit /b 1
