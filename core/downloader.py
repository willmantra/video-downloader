import json
import re
import subprocess
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from PySide6.QtCore import QThread, Signal

from .tools import base_yt_dlp_command


def normalise_url(url: str):
    try:
        parsed = urlparse(url)
        host = parsed.netloc.lower()
        qs = parse_qs(parsed.query)
        playlist_id = qs.get("list", [None])[0]
        if playlist_id and ("youtube.com" in host or "youtu.be" in host):
            return f"https://www.youtube.com/playlist?list={playlist_id}", True
    except Exception:
        pass
    return url, False


def format_duration(seconds):
    if seconds in (None, ""):
        return ""
    try:
        seconds = int(seconds)
    except Exception:
        return ""
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


class InspectWorker(QThread):
    loaded = Signal(dict)
    failed = Signal(str)

    def __init__(self, url, cookie_file=""):
        super().__init__()
        self.url = url
        self.cookie_file = cookie_file

    def run(self):
        inspect_url, is_playlist = normalise_url(self.url)
        cmd = base_yt_dlp_command(self.cookie_file)
        cmd += ["--dump-single-json", "--flat-playlist", inspect_url]
        try:
            p = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=180,
            )
            if p.returncode != 0:
                raise RuntimeError(p.stderr.strip() or p.stdout.strip() or "Could not inspect this link.")
            data = json.loads(p.stdout)
            entries = []
            raw_entries = data.get("entries")
            if isinstance(raw_entries, list):
                for idx, entry in enumerate(raw_entries, start=1):
                    if not entry:
                        continue
                    thumbs = entry.get("thumbnails") or []
                    thumbnail = entry.get("thumbnail") or ""
                    if not thumbnail and thumbs:
                        thumbnail = (thumbs[-1] or {}).get("url") or ""
                    entries.append({
                        "index": idx,
                        "id": entry.get("id") or "",
                        "title": entry.get("title") or entry.get("id") or f"Video {idx}",
                        "duration": entry.get("duration"),
                        "url": entry.get("url") or entry.get("webpage_url") or "",
                        "thumbnail": thumbnail,
                        "selected": True,
                    })
            else:
                thumbs = data.get("thumbnails") or []
                thumbnail = data.get("thumbnail") or ""
                if not thumbnail and thumbs:
                    thumbnail = (thumbs[-1] or {}).get("url") or ""
                entries = [{
                    "index": 1,
                    "id": data.get("id") or "",
                    "title": data.get("title") or data.get("fulltitle") or "Video",
                    "duration": data.get("duration"),
                    "url": data.get("webpage_url") or inspect_url,
                    "thumbnail": thumbnail,
                    "selected": True,
                }]
            self.loaded.emit({
                "title": data.get("title") or data.get("fulltitle") or "Link recognised",
                "url": inspect_url,
                "is_playlist": bool(is_playlist or isinstance(raw_entries, list)),
                "entries": entries,
            })
        except Exception as exc:
            self.failed.emit(str(exc))


def video_selector(quality):
    if quality == "Best available":
        return "bestvideo*"
    m = re.search(r"(2160|1440|1080|720|480|360)", quality or "")
    height = m.group(1) if m else "1080"
    return f"bestvideo*[height<={height}]"


def build_download_command(job):
    url, is_playlist = normalise_url(job["url"])
    cmd = base_yt_dlp_command(job.get("cookie_file", ""))
    mode = job.get("mode", "Video + audio")
    vq = job.get("video_quality", "Best available")
    aq = job.get("audio_quality", "Best available")

    if mode == "Video + audio":
        cmd += ["-f", f"{video_selector(vq)}+bestaudio/best"]
    elif mode == "Video only":
        cmd += ["-f", f"{video_selector(vq)}/bestvideo"]
    else:
        cmd += ["-x"]
        if aq == "Best available":
            cmd += ["-f", "bestaudio/best"]
        elif aq.startswith("MP3"):
            bitrate = re.search(r"(320|256|192)", aq)
            cmd += ["--audio-format", "mp3", "--audio-quality", f"{bitrate.group(1) if bitrate else '192'}K"]
        elif aq == "M4A":
            cmd += ["--audio-format", "m4a"]
        elif aq == "Opus":
            cmd += ["--audio-format", "opus"]
        elif aq == "WAV":
            cmd += ["--audio-format", "wav"]

    container = job.get("container", "Automatic")
    if mode != "Audio only":
        if container == "MKV":
            cmd += ["--merge-output-format", "mkv"]
        elif container == "MP4":
            cmd += ["--merge-output-format", "mp4"]

    selected = job.get("playlist_items") or []
    total_items = int(job.get("playlist_total") or 0)
    if is_playlist and selected and len(selected) != total_items:
        cmd += ["--playlist-items", ",".join(str(x) for x in selected)]

    root = job.get("output_dir") or str(Path.home() / "Downloads")
    Path(root).mkdir(parents=True, exist_ok=True)
    if is_playlist and job.get("playlist_folder", True):
        filename = "%(playlist_index)02d - %(title)s.%(ext)s" if job.get("playlist_numbering", True) else "%(title)s.%(ext)s"
        template = str(Path(root) / "%(playlist_title)s" / filename)
    else:
        template = str(Path(root) / "%(title)s.%(ext)s")

    cmd += ["-o", template, url]
    return cmd


class DownloadWorker(QThread):
    output = Signal(str)
    progress = Signal(float)
    detail = Signal(str)
    completed = Signal()
    failed = Signal(str)

    def __init__(self, job):
        super().__init__()
        self.job = job
        self.proc = None
        self._cancelled = False

    def cancel(self):
        self._cancelled = True
        try:
            if self.proc and self.proc.poll() is None:
                self.proc.terminate()
        except Exception:
            pass

    def run(self):
        try:
            cmd = build_download_command(self.job)
            self.proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
            )
            for raw in self.proc.stdout or []:
                line = raw.rstrip()
                if not line:
                    continue
                self.output.emit(line)
                m = re.search(r"Downloading item\s+(\d+)\s+of\s+(\d+)", line)
                if m:
                    self.detail.emit(f"Playlist item {m.group(1)} of {m.group(2)}")
                p = re.search(r"\[download\]\s+([0-9.]+)%", line)
                if p:
                    self.progress.emit(float(p.group(1)))
                if "[Merger]" in line or "Merging formats" in line:
                    self.detail.emit("Merging video and audio")
                elif "[ExtractAudio]" in line:
                    self.detail.emit("Converting audio")
            code = self.proc.wait()
            if self._cancelled:
                self.failed.emit("Cancelled")
            elif code == 0:
                self.progress.emit(100.0)
                self.completed.emit()
            else:
                self.failed.emit(f"yt-dlp exited with code {code}")
        except Exception as exc:
            self.failed.emit(str(exc))
