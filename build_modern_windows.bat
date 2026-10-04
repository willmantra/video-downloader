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

if not exist "%CD%\.build-cache\bin\yt-dlp.exe" goto :refresh_tools
if not exist "%CD%\.build-cache\bin\ffmpeg.exe" goto :refresh_tools
if not exist "%CD%\.build-cache\bin\ffprobe.exe" goto :refresh_tools

echo Using cached yt-dlp and FFmpeg...
if not exist "%CD%\dist\Video Downloader 0.5 Dev\bin" mkdir "%CD%\dist\Video Downloader 0.5 Dev\bin"
copy /Y "%CD%\.build-cache\bin\yt-dlp.exe" "%CD%\dist\Video Downloader 0.5 Dev\bin\yt-dlp.exe" >nul
copy /Y "%CD%\.build-cache\bin\ffmpeg.exe" "%CD%\dist\Video Downloader 0.5 Dev\bin\ffmpeg.exe" >nul
copy /Y "%CD%\.build-cache\bin\ffprobe.exe" "%CD%\dist\Video Downloader 0.5 Dev\bin\ffprobe.exe" >nul
goto :tools_ready

:refresh_tools
echo Cached tools not found. Downloading them once...
if not exist "%CD%\.build-cache\bin" mkdir "%CD%\.build-cache\bin"
powershell -NoProfile -ExecutionPolicy Bypass -File "%CD%\bundle_dependencies.ps1" -Destination "%CD%\.build-cache\bin"
if errorlevel 1 goto :fail
if not exist "%CD%\dist\Video Downloader 0.5 Dev\bin" mkdir "%CD%\dist\Video Downloader 0.5 Dev\bin"
copy /Y "%CD%\.build-cache\bin\yt-dlp.exe" "%CD%\dist\Video Downloader 0.5 Dev\bin\yt-dlp.exe" >nul
copy /Y "%CD%\.build-cache\bin\ffmpeg.exe" "%CD%\dist\Video Downloader 0.5 Dev\bin\ffmpeg.exe" >nul
copy /Y "%CD%\.build-cache\bin\ffprobe.exe" "%CD%\dist\Video Downloader 0.5 Dev\bin\ffprobe.exe" >nul

:tools_ready
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
