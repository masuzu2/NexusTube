@echo off
chcp 65001 >nul 2>&1
title NexusTube -- Build MSI Installer
cd /d "%~dp0"

echo.
echo  NexusTube MSI Installer  v3.4.0
echo.

set "NODE_CMD="
if exist "%LOCALAPPDATA%\Programs\cursor\resources\app\resources\helpers\node.exe" (
  set "NODE_CMD=%LOCALAPPDATA%\Programs\cursor\resources\app\resources\helpers\node.exe"
)
if not defined NODE_CMD where node >nul 2>&1 && set "NODE_CMD=node"
if not defined NODE_CMD (
  echo  [ERROR] Node.js was not found.
  pause
  exit /b 1
)

"%NODE_CMD%" "%~dp0build_msi.js"
if errorlevel 1 (
  echo.
  echo  [!] Build failed.
  pause
  exit /b 1
)

echo.
echo  [OK] MSI: %~dp0NexusTube_Setup_v3.4.0.msi
pause
