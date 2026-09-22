@echo off
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 Install.py %*
) else (
  python Install.py %*
)
if errorlevel 1 pause
