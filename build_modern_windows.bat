@echo off
setlocal

rem Support repositories stored on UNC/network paths by temporarily mapping a drive.
pushd "%~dp0"
if errorlevel 1 (
  echo Could not access the project folder.
  pause
  exit /b 1
)

where python >nul 2>nul
if errorlevel 1 (
  echo Python was not found. Install Python 3 first.
  goto :fail
)

python -m pip install --upgrade -r requirements.txt pyinstaller
if errorlevel 1 goto :fail

python -m PyInstaller --noconfirm --clean --onedir --windowed --name "Video Downloader 0.5 Dev" --add-data "version.txt;." modern_app.py
if errorlevel 1 goto :fail

powershell -NoProfile -ExecutionPolicy Bypass -File "%CD%\bundle_dependencies.ps1" -Destination "%CD%\dist\Video Downloader 0.5 Dev\bin"
if errorlevel 1 goto :fail

echo.
echo Modern development build complete:
echo %CD%\dist\Video Downloader 0.5 Dev\
popd
pause
exit /b 0

:fail
echo.
echo Build failed. Review the messages above.
popd
pause
exit /b 1
