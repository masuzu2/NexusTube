@echo off
cd /d "%~dp0"
where node >nul 2>&1
if %errorlevel%==0 (
  node src\main\web-download.js --open
  exit /b %errorlevel%
)
set "NODE=%LOCALAPPDATA%\Programs\cursor\resources\app\resources\helpers\node.exe"
if exist "%NODE%" (
  "%NODE%" src\main\web-download.js --open
  exit /b %errorlevel%
)
echo Node.js is required to open the download site.
pause
