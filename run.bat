@echo off
chcp 936 >nul
title PixInsight Auto Clicker

cd /d "%~dp0"

echo ============================================
echo   PixInsight AnnotateImage Auto Clicker
echo   Starting...
echo ============================================
echo.

where python >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    python pixinsight_auto_clicker.py
    if %ERRORLEVEL% EQU 0 goto end
)

for %%p in (
    "C:\Python314\python.exe"
    "C:\Python313\python.exe"
    "C:\Python312\python.exe"
    "C:\Program Files\Python314\python.exe"
    "C:\Program Files\Python313\python.exe"
    "C:\Program Files\Python312\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python314\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
) do (
    if exist %%p (
        echo Using: %%p
        "%%~fp" pixinsight_auto_clicker.py
        goto end
    )
)

echo.
echo [ERROR] Python not found. Install Python 3.11+ then:
echo     pip install pywin32 PyQt5
echo.
pause
exit /b 1

:end
pause
