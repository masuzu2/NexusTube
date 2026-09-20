@echo off
chcp 65001 >nul 2>&1
title NexusTube -- Auto Setup
color 0B

echo.
echo  ======================================================
echo            NexusTube  Auto Setup  v3.2.0
echo      Check and auto-install all dependencies
echo  ======================================================
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
    echo  [ERROR] Python was not found on this system!
    echo.
    echo  Please download and install Python 3.11+:
    echo  https://www.python.org/downloads/
    echo.
    echo  IMPORTANT: Check "Add Python to PATH" during installation!
    echo.
    pause
    start https://www.python.org/downloads/
    exit /b 1
)

echo  [OK] Found Python: %PYTHON_CMD%

%PYTHON_CMD% -c "import sys; exit(0 if sys.version_info >= (3,11) else 1)" >nul 2>&1
if errorlevel 1 (
    echo  [WARN] Python version is lower than 3.11 -- recommend upgrading!
    echo  Download: https://www.python.org/downloads/
    echo.
    pause
)

echo.
echo  Running setup.py ...
echo  -----------------------------------------------------
echo.

%PYTHON_CMD% "%~dp0setup.py"

echo.
if errorlevel 1 (
    echo  [!] Setup encountered issues -- see details above.
    echo.
    pause
) else (
    echo  [OK] Setup finished successfully!
    ping 127.0.0.1 -n 4 >nul 2>&1
)
