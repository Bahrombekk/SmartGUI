@echo off
title SafeZone - exe build
cd /d "%~dp0"

set PYTHON=%~dp0venv\Scripts\python.exe
if not exist "%PYTHON%" (
    echo  [!] venv topilmadi: %PYTHON%
    pause & exit /b 1
)

"%PYTHON%" -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
    echo  [*] PyInstaller o'rnatilmoqda...
    "%PYTHON%" -m pip install "pyinstaller>=6.16" || (pause & exit /b 1)
)

echo  [*] Yig'ilmoqda: dist\SafeZone\SafeZone.exe
"%PYTHON%" -m PyInstaller SmartGUI.spec --noconfirm --clean
if errorlevel 1 (
    echo  [!] Build xato bilan tugadi.
    pause & exit /b 1
)

echo  [*] Exe tayyor: dist\SafeZone\SafeZone.exe

:: ── Inno Setup installer (bitta setup exe) ──────────────────────────────
set ISCC=
for %%P in ("%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" "%ProgramFiles%\Inno Setup 6\ISCC.exe") do (
    if exist %%P set ISCC=%%P
)
if not defined ISCC (
    echo  [!] Inno Setup 6 topilmadi - installer yig'ilmadi.
    echo  [!] O'rnatish: winget install JRSoftware.InnoSetup
    pause & exit /b 1
)
echo  [*] Installer yig'ilmoqda (bir necha daqiqa)...
%ISCC% /Q installer\SafeZone.iss
if errorlevel 1 (
    echo  [!] Installer xato bilan tugadi.
    pause & exit /b 1
)

echo.
echo  [*] Tayyor: installer\Output\SafeZone-Setup-1.1.0.exe
pause
