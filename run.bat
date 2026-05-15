@echo off
title SmartHelmet GUI
color 0A

echo.
echo  =========================================
echo    SmartHelmet -- Xavfsizlik Tizimi
echo  =========================================
echo.

set SCRIPT_DIR=%~dp0
set PYTHON=%SCRIPT_DIR%venv\Scripts\python.exe
set PYTHONW=%SCRIPT_DIR%venv\Scripts\pythonw.exe
set SERVICE_NAME=SmartHelmetGUI

:: ── Windows Service rejimi: run.bat service install / remove ─────────────
if /i "%1"=="service" (
    net session >nul 2>&1
    if errorlevel 1 (
        echo  [!] Service o'rnatish uchun Administrator huquqi kerak.
        echo  [!] O'ng tugma → "Administrator sifatida ishga tushirish"
        pause & exit /b 1
    )
    where nssm >nul 2>&1
    if errorlevel 1 (
        echo  [!] nssm topilmadi. https://nssm.cc/download dan yuklab,
        echo  [!] nssm.exe ni C:\Windows\System32\ ga qo'ying.
        pause & exit /b 1
    )
    if /i "%2"=="remove" (
        nssm stop %SERVICE_NAME% & nssm remove %SERVICE_NAME% confirm
        echo  [*] Xizmat o'chirildi.
        pause & exit /b 0
    )
    nssm status %SERVICE_NAME% >nul 2>&1
    if not errorlevel 1 ( nssm stop %SERVICE_NAME% & nssm remove %SERVICE_NAME% confirm )
    if not exist "%SCRIPT_DIR%logs" mkdir "%SCRIPT_DIR%logs"
    nssm install %SERVICE_NAME% "%PYTHONW%" "%SCRIPT_DIR%main.py"
    nssm set %SERVICE_NAME% DisplayName "SmartHelmet Xavfsizlik Tizimi"
    nssm set %SERVICE_NAME% AppDirectory "%SCRIPT_DIR%"
    nssm set %SERVICE_NAME% Start SERVICE_AUTO_START
    nssm set %SERVICE_NAME% AppStdout "%SCRIPT_DIR%logs\service.log"
    nssm set %SERVICE_NAME% AppStderr "%SCRIPT_DIR%logs\service.log"
    nssm set %SERVICE_NAME% AppRotateFiles 1
    nssm set %SERVICE_NAME% AppRotateBytes 5242880
    nssm set %SERVICE_NAME% AppExit Default Restart
    nssm set %SERVICE_NAME% AppRestartDelay 30000
    nssm start %SERVICE_NAME%
    echo  [*] Xizmat o'rnatildi va ishga tushirildi.
    echo  [*] Boshqarish: services.msc → SmartHelmetGUI
    pause & exit /b 0
)

:: ── Oddiy ishga tushirish ─────────────────────────────────────────────────
if not exist "%PYTHON%" (
    echo  [!] SmartGUI venv topilmadi!
    echo  [!] Avval: python -m venv venv
    pause & exit /b 1
)

echo  [*] Python: %PYTHON%
echo  [*] SmartHelmet GUI ishga tushirilmoqda...
echo.

cd /d "%SCRIPT_DIR%"
"%PYTHON%" main.py

if errorlevel 1 (
    echo.
    echo  [!] Xatolik yuz berdi. Qayta urinib ko'ring.
    pause
)
