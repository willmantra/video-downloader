import os
import shutil
import sys
from pathlib import Path

APP_NAME = "Video Downloader"


def app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def resource_path(name: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", app_root()))
    return base / name


def default_downloads() -> str:
    return str(Path.home() / "Downloads")


def bundled_executable(name: str):
    exe_name = name
    if os.name == "nt" and not exe_name.lower().endswith(".exe"):
        exe_name += ".exe"
    candidate = app_root() / "bin" / exe_name
    if candidate.is_file():
        return str(candidate)
    return None


def find_executable(name: str):
    return bundled_executable(name) or shutil.which(name)


def dependency_status():
    return {
        "yt-dlp": find_executable("yt-dlp"),
        "ffmpeg": find_executable("ffmpeg"),
        "ffprobe": find_executable("ffprobe"),
    }


def base_yt_dlp_command(cookie_file: str = ""):
    ytdlp = find_executable("yt-dlp") or "yt-dlp"
    cmd = [ytdlp, "--newline", "--progress", "--no-colors"]
    ffmpeg = find_executable("ffmpeg")
    if ffmpeg:
        cmd += ["--ffmpeg-location", str(Path(ffmpeg).resolve().parent)]
    if cookie_file.strip():
        cmd += ["--cookies", cookie_file.strip()]
    return cmd
