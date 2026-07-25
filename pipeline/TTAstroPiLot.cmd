@echo off
REM TTAstroPiLot - one-click launcher (double-click on Windows)
cd /d "%~dp0"
python -m orchestrator.app_ui
if errorlevel 1 (
  echo.
  echo [Launch failed] Make sure Python and PyQt5 are installed:  pip install PyQt5
  pause
)
