Video Downloader GUI v0.4.0
===========================

WHAT'S NEW
- Built-in application update checking.
- Help > Check for updates.
- Optional automatic update check when the app starts.
- Downloads a newer Windows installer, closes the old app, installs silently and reopens it.
- Remembers the download folder and cookies.txt location between runs.
- Proper per-user Windows installer with Start-menu shortcut and uninstall support.
- GitHub Actions release workflow included so future versions can build themselves in the cloud.
- Keeps all v3 features: playlist preview, thumbnails, Select All/None, individual video selection, quality options and cookies.txt support.

RUNNING THE DEVELOPMENT VERSION
1. Ensure yt-dlp and FFmpeg are installed and available on PATH.
2. Double-click run_windows.bat.

BUILDING A PORTABLE EXE
Double-click build_windows.bat.
Result:
  dist\Video Downloader.exe

BUILDING THE INSTALLER
Double-click build_installer.bat.
The script will install Inno Setup with winget if needed.
Result:
  installer_output\VideoDownloaderSetup-0.4.0.exe

INSTALL LOCATION
The installer installs for the current Windows user at:
  %LOCALAPPDATA%\Programs\Video Downloader\
This deliberately avoids requiring administrator rights for normal installs and updates.

HOW SELF-UPDATES WORK
The app checks this GitHub Releases endpoint by default:
  https://api.github.com/repos/willmantra/video-downloader/releases/latest

When a newer release is present and has a Windows setup EXE attached, the app:
1. Shows the new version and release notes.
2. Downloads the installer to the Windows temporary folder.
3. Closes itself.
4. Runs the installer silently.
5. Reopens the installed app.

ONE-TIME GITHUB SETUP
A public GitHub repository named video-downloader must exist under the willmantra account before update checks can work.
See GITHUB_RELEASE_SETUP.txt.

IMPORTANT
- cookies.txt contains sensitive session data. Do not commit or share it.
- yt-dlp and FFmpeg are still external dependencies and need to be installed on the PC.
