@echo off
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo Python was not found.
  echo Install Python 3 from https://www.python.org/downloads/windows/
  echo During setup, tick "Add python.exe to PATH".
  pause
  exit /b 1
)

python -m pip install -r requirements.txt
if errorlevel 1 goto :fail
python app.py
exit /b %errorlevel%

:fail
echo.
echo Could not install the required Python packages.
pause
exit /b 1
