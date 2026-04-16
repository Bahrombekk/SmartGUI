@echo off
title SmartHelmet GUI
color 0A

echo.
echo  =========================================
echo    SmartHelmet -- Xavfsizlik Tizimi
echo  =========================================
echo.

:: SmartGUI venv Python ni to'g'ridan-to'g'ri ishlatish
set PYTHON=%~dp0venv\Scripts\python.exe

if not exist "%PYTHON%" (
    echo  [!] SmartGUI venv topilmadi!
    echo  [!] Avval: python -m venv venv
    pause
    exit /b 1
)

echo  [*] Python: %PYTHON%
echo  [*] SmartHelmet GUI ishga tushirilmoqda...
echo.

cd /d "%~dp0"
"%PYTHON%" main.py

if errorlevel 1 (
    echo.
    echo  [!] Xatolik yuz berdi. Qayta urinib ko'ring.
    pause
)
