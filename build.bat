@echo off
chcp 936 >nul
title Build PixInsight Auto Clicker EXE

cd /d "%~dp0"

echo ============================================
echo   Building standalone EXE...
echo ============================================
echo.

where pyinstaller >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    python -m PyInstaller --version >nul 2>&1
    if %ERRORLEVEL% NEQ 0 (
        echo [ERROR] PyInstaller not found.
        echo Install: pip install pyinstaller
        pause
        exit /b 1
    )
    set "PYINSTALLER=python -m PyInstaller"
) else (
    set "PYINSTALLER=pyinstaller"
)

echo Building, please wait 2-5 minutes...
echo.

%PYINSTALLER% --onefile --windowed --name "PixInsightAutoClicker" pixinsight_auto_clicker.py

echo.
echo ============================================
if exist "dist\PixInsightAutoClicker.exe" (
    echo [SUCCESS] Output: dist\PixInsightAutoClicker.exe
    for %%f in ("dist\PixInsightAutoClicker.exe") do echo Size: %%~zf bytes
) else (
    echo [FAILED] Check errors above.
)
echo ============================================
echo.
pause
