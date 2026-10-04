@echo off
setlocal
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (echo Python was not found. Install Python 3 first.& pause & exit /b 1)

python -m pip install --upgrade -r requirements.txt pyinstaller
if errorlevel 1 goto :fail

python -m PyInstaller --noconfirm --clean --onedir --windowed --name "Video Downloader 0.5 Dev" --add-data "version.txt;." modern_app.py
if errorlevel 1 goto :fail

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0bundle_dependencies.ps1" -Destination "%~dp0dist\Video Downloader 0.5 Dev\bin"
if errorlevel 1 goto :fail

echo.
echo Modern development build complete:
echo %CD%\dist\Video Downloader 0.5 Dev\
pause
exit /b 0

:fail
echo.
echo Build failed. Review the messages above.
pause
exit /b 1
