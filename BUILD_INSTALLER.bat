@echo off
chcp 65001 >nul 2>&1
title NexusTube -- Build MSI Installer
color 0B

echo.
echo  =====================================================
echo   NexusTube  MSI Installer Builder  v3.2.0
echo   Build .msi Windows Installer
echo  =====================================================
echo.

set PYTHON_CMD=
where python >nul 2>&1 && set PYTHON_CMD=python
if "%PYTHON_CMD%"=="" (
    where python3 >nul 2>&1 && set PYTHON_CMD=python3
)
if "%PYTHON_CMD%"=="" (
    where py >nul 2>&1 && set PYTHON_CMD=py
)

if "%PYTHON_CMD%"=="" (
    echo  [ERROR] Python is not found on this system!
    echo  Please download and install Python 3.11+:
    echo  https://www.python.org/downloads/
    pause
    exit /b 1
)

echo  [OK] Python: %PYTHON_CMD%
echo.
echo  Building MSI Installer with WiX Toolset...
echo.

%PYTHON_CMD% "%~dp0build_installer.py"

if errorlevel 1 (
    echo.
    echo  [!] Build failed -- please check the errors above.
    echo.
    pause
) else (
    echo.
    echo  [OK] Build completed successfully!
    echo  MSI location: %~dp0NexusTube_Setup_v3.2.0.msi
    echo.
    pause
)
