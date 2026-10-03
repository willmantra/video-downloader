@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (echo Python was not found. Install Python 3 first.& pause & exit /b 1)
python -m pip install --upgrade pyinstaller Pillow
if errorlevel 1 goto :fail
python -m PyInstaller --noconfirm --clean --onedir --windowed --name "Video Downloader" --collect-all PIL --add-data "version.txt;." app.py
if errorlevel 1 goto :fail
set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if exist "%ISCC%" goto :have_iscc
set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist "%ISCC%" goto :have_iscc
set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if exist "%ISCC%" goto :have_iscc
echo Inno Setup 6 was not found. Attempting to install it with winget...
where winget >nul 2>nul
if errorlevel 1 (echo Install Inno Setup 6, then run this file again.& pause & exit /b 1)
winget install --id JRSoftware.InnoSetup -e --scope user --accept-source-agreements --accept-package-agreements
set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" (echo Inno Setup could not be located after installation.& pause & exit /b 1)
:have_iscc
set /p APP_VERSION=<version.txt
"%ISCC%" /DMyAppVersion=!APP_VERSION! installer.iss
if errorlevel 1 goto :fail
certutil -hashfile "installer_output\VideoDownloaderSetup-!APP_VERSION!.exe" SHA256 | findstr /R /V "hash CertUtil" > "installer_output\VideoDownloaderSetup-!APP_VERSION!.exe.sha256"
echo.
echo Installer build complete: %CD%\installer_output\VideoDownloaderSetup-!APP_VERSION!.exe
echo SHA-256: %CD%\installer_output\VideoDownloaderSetup-!APP_VERSION!.exe.sha256
pause
exit /b 0
:fail
echo. & echo Build failed. Review the messages above. & pause & exit /b 1
