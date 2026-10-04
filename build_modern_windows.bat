@echo off
setlocal

rem Support repositories stored on UNC/network paths by temporarily mapping a drive.
pushd "%~dp0"
if errorlevel 1 (
  echo Could not access the project folder.
  pause
  exit /b 1
)

set "PROJECT_DIR=%CD%"
set "LOCAL_BUILD_ROOT=%LOCALAPPDATA%\VideoDownloaderDevBuild"
set "LOCAL_WORK=%LOCAL_BUILD_ROOT%\work"
set "LOCAL_DIST=%LOCAL_BUILD_ROOT%\dist"
set "LOCAL_SPEC=%LOCAL_BUILD_ROOT%\spec"
set "LOCAL_CACHE=%LOCAL_BUILD_ROOT%\tool-cache"
set "TARGET_DIST=%PROJECT_DIR%\dist\Video Downloader 0.5 Dev"
set "LOCAL_EXE=%LOCAL_DIST%\Video Downloader 0.5 Dev\Video Downloader 0.5 Dev.exe"

where python >nul 2>nul
if errorlevel 1 (
  echo Python was not found. Install Python 3 first.
  goto :fail
)

rem Close any previous dev build so Windows releases files before we rebuild.
taskkill /IM "Video Downloader 0.5 Dev.exe" /F >nul 2>nul
timeout /T 1 /NOBREAK >nul

python -m pip install --upgrade -r requirements.txt pyinstaller
if errorlevel 1 goto :fail

echo.
echo Building locally to avoid network-drive file locking issues...
if exist "%LOCAL_WORK%" rmdir /S /Q "%LOCAL_WORK%"
if exist "%LOCAL_DIST%" rmdir /S /Q "%LOCAL_DIST%"
if exist "%LOCAL_SPEC%" rmdir /S /Q "%LOCAL_SPEC%"

if exist "%LOCAL_DIST%" (
  echo.
  echo The previous development build is still locked by Windows.
  echo Close any open Video Downloader 0.5 Dev windows and run this build again.
  goto :fail
)

mkdir "%LOCAL_WORK%" >nul 2>nul
mkdir "%LOCAL_DIST%" >nul 2>nul
mkdir "%LOCAL_SPEC%" >nul 2>nul

python -m PyInstaller --noconfirm --clean --onedir --windowed ^
  --name "Video Downloader 0.5 Dev" ^
  --workpath "%LOCAL_WORK%" ^
  --distpath "%LOCAL_DIST%" ^
  --specpath "%LOCAL_SPEC%" ^
  --add-data "%PROJECT_DIR%\version.txt;." ^
  "%PROJECT_DIR%\modern_app.py"
if errorlevel 1 goto :fail

if not exist "%LOCAL_CACHE%\yt-dlp.exe" goto :refresh_tools
if not exist "%LOCAL_CACHE%\ffmpeg.exe" goto :refresh_tools
if not exist "%LOCAL_CACHE%\ffprobe.exe" goto :refresh_tools

echo Using cached yt-dlp and FFmpeg...
goto :copy_tools_local

:refresh_tools
echo Cached tools not found. Downloading them once...
if not exist "%LOCAL_CACHE%" mkdir "%LOCAL_CACHE%"
powershell -NoProfile -ExecutionPolicy Bypass -File "%PROJECT_DIR%\bundle_dependencies.ps1" -Destination "%LOCAL_CACHE%"
if errorlevel 1 goto :fail

:copy_tools_local
if not exist "%LOCAL_DIST%\Video Downloader 0.5 Dev\bin" mkdir "%LOCAL_DIST%\Video Downloader 0.5 Dev\bin"
copy /Y "%LOCAL_CACHE%\yt-dlp.exe" "%LOCAL_DIST%\Video Downloader 0.5 Dev\bin\yt-dlp.exe" >nul
copy /Y "%LOCAL_CACHE%\ffmpeg.exe" "%LOCAL_DIST%\Video Downloader 0.5 Dev\bin\ffmpeg.exe" >nul
copy /Y "%LOCAL_CACHE%\ffprobe.exe" "%LOCAL_DIST%\Video Downloader 0.5 Dev\bin\ffprobe.exe" >nul

echo.
echo Copying completed build back to the repository...
if exist "%TARGET_DIST%" rmdir /S /Q "%TARGET_DIST%"
robocopy "%LOCAL_DIST%\Video Downloader 0.5 Dev" "%TARGET_DIST%" /E /NFL /NDL /NJH /NJS /NP >nul
if errorlevel 8 goto :fail

echo.
echo Modern development build complete:
echo %TARGET_DIST%
echo Launching development build from local disk...
if not exist "%LOCAL_EXE%" (
  echo Could not find the local development executable:
  echo %LOCAL_EXE%
  goto :fail
)

start "" /D "%LOCAL_DIST%\Video Downloader 0.5 Dev" "%LOCAL_EXE%"
popd
exit /b 0

:fail
echo.
echo Build failed. Review the messages above.
popd
pause
exit /b 1
