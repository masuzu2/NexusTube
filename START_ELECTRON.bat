@echo off
title NexusTube Electron Desktop Player
cd /d "%~dp0"

echo [NexusTube] Launching NexusTube Studio Desktop (Electron)...
if exist "dist_electron\win-unpacked\NexusTube.exe" (
    start "" "dist_electron\win-unpacked\NexusTube.exe"
) else (
    npm start
)
exit
