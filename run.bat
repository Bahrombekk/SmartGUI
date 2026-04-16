@echo off
title SmartHelmet GUI
color 0A

echo.
echo  =========================================
echo    SmartHelmet -- Xavfsizlik Tizimi
echo  =========================================
echo.

:: SmartHelmet venv ishlatish (agar mavjud bo'lsa)
set VENV_PATH=C:\Users\User\Desktop\SmartHelmet\venv\Scripts\activate.bat

if exist "%VENV_PATH%" (
    echo  [*] SmartHelmet venv aktivlashtirilmoqda...
    call "%VENV_PATH%"
) else (
    echo  [!] SmartHelmet venv topilmadi, tizim Python ishlatiladi
)

echo  [*] SmartHelmet GUI ishga tushirilmoqda...
echo.

cd /d "%~dp0"
python main.py

if errorlevel 1 (
    echo.
    echo  [!] Xatolik yuz berdi. Qayta urinib ko'ring.
    pause
)
