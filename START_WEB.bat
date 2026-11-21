@echo off
cd /d "%~dp0"
where node >nul 2>&1
if %errorlevel%==0 (
  start "" http://127.0.0.1:8787
  node src\main\web-download.js
  exit /b %errorlevel%
)
set "APP=%LOCALAPPDATA%\Programs\nexustube\NexusTube.exe"
if not exist "%APP%" set "APP=%LOCALAPPDATA%\Programs\NexusTube\NexusTube.exe"
if exist "%APP%" (
  start "" "%APP%" --web-server --open
  exit /b %errorlevel%
)
echo ไม่พบ Node.js หรือ NexusTube ที่ติดตั้งไว้ — ติดตั้ง NexusTube ก่อนใช้เว็บโหลดเพลง
pause
