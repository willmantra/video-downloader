@echo off
setlocal
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (echo Python was not found. Install Python 3 first.& pause & exit /b 1)
python -m pip install --upgrade pyinstaller Pillow
if errorlevel 1 goto :fail
python -m PyInstaller --noconfirm --clean --onedir --windowed --name "Video Downloader" --collect-all PIL --add-data "version.txt;." app.py
if errorlevel 1 goto :fail
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0bundle_dependencies.ps1"
if errorlevel 1 goto :fail
echo.
echo Application build complete: %CD%\dist\Video Downloader\
pause
exit /b 0
:fail
echo. & echo Build failed. Review the messages above. & pause & exit /b 1
