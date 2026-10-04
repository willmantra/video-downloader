import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from PySide6.QtCore import Qt, QThread, Signal, QUrl
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QFileDialog, QFrame,
    QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton,
    QProgressBar, QScrollArea, QSizePolicy, QSplitter, QListWidget, QListWidgetItem,
    QVBoxLayout, QWidget,
)

APP_NAME = "Video Downloader"
APP_VERSION = "0.5.0-dev"


def app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def default_downloads() -> str:
    return str(Path.home() / "Downloads")


def bundled_executable(name: str):
    exe = name + (".exe" if os.name == "nt" and not name.lower().endswith(".exe") else "")
    candidate = app_root() / "bin" / exe
    return str(candidate) if candidate.is_file() else None


def find_executable(name: str):
    return bundled_executable(name) or shutil.which(name)


def base_command(cookie_file=""):
    ytdlp = find_executable("yt-dlp") or "yt-dlp"
    cmd = [ytdlp, "--newline", "--progress", "--no-colors"]
    ffmpeg = find_executable("ffmpeg")
    if ffmpeg:
        cmd += ["--ffmpeg-location", str(Path(ffmpeg).resolve().parent)]
    if cookie_file.strip():
        cmd += ["--cookies", cookie_file.strip()]
    return cmd


def normalise_url(url: str):
    try:
        parsed = urlparse(url)
        playlist_id = parse_qs(parsed.query).get("list", [None])[0]
        if playlist_id and ("youtube.com" in parsed.netloc.lower() or "youtu.be" in parsed.netloc.lower()):
            return f"https://www.youtube.com/playlist?list={playlist_id}", True
    except Exception:
        pass
    return url, False


def format_duration(value):
    try:
        seconds = int(value)
    except Exception:
        return ""
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


class Store:
    def __init__(self):
        root = Path(os.environ.get("APPDATA", str(Path.home()))) / APP_NAME
        root.mkdir(parents=True, exist_ok=True)
        self.settings_path = root / "settings-v05.json"
        self.queue_path = root / "queue-v05.json"

    def load_settings(self):
        data = {
            "theme": "dark",
            "output_dir": default_downloads(),
            "cookie_file": "",
            "container": "Automatic",
            "playlist_folder": True,
            "playlist_numbering": True,
        }
        try:
            if self.settings_path.exists():
                loaded = json.loads(self.settings_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    data.update(loaded)
        except Exception:
            pass
        return data

    def save_settings(self, data):
        self.settings_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def load_queue(self):
        try:
            if self.queue_path.exists():
                data = json.loads(self.queue_path.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    for job in data:
                        if job.get("status") == "Downloading":
                            job["status"] = "Queued"
                    return data
        except Exception:
            pass
        return []

    def save_queue(self, data):
        self.queue_path.write_text(json.dumps(data, indent=2), encoding="utf-8")


class InspectWorker(QThread):
    loaded = Signal(dict)
    failed = Signal(str)

    def __init__(self, url, cookie):
        super().__init__()
        self.url = url
        self.cookie = cookie

    def run(self):
        url, is_playlist = normalise_url(self.url)
        cmd = base_command(self.cookie) + ["--dump-single-json", "--flat-playlist", url]
        try:
            p = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=180,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
            )
            if p.returncode != 0:
                raise RuntimeError(p.stderr.strip() or p.stdout.strip() or "Could not inspect link.")
            data = json.loads(p.stdout)
            raw_entries = data.get("entries")
            source = raw_entries if isinstance(raw_entries, list) else [data]
            entries = []
            for idx, entry in enumerate(source, start=1):
                if not entry:
                    continue
                thumbs = entry.get("thumbnails") or []
                thumb = entry.get("thumbnail") or ((thumbs[-1] or {}).get("url") if thumbs else "")
                entries.append({
                    "index": idx,
                    "title": entry.get("title") or entry.get("id") or f"Video {idx}",
                    "duration": entry.get("duration"),
                    "thumbnail": thumb or "",
                })
            self.loaded.emit({
                "title": data.get("title") or data.get("fulltitle") or "Link recognised",
                "url": url,
                "is_playlist": bool(is_playlist or isinstance(raw_entries, list)),
                "entries": entries,
            })
        except Exception as exc:
            self.failed.emit(str(exc))


def build_command(job):
    url, is_playlist = normalise_url(job["url"])
    cmd = base_command(job.get("cookie_file", ""))

    mode = job.get("mode", "Video + audio")
    quality = job.get("video_quality", "Best available")
    if quality == "Best available":
        selector = "bestvideo*"
    else:
        match = re.search(r"(2160|1440|1080|720|480|360)", quality)
        selector = f"bestvideo*[height<={match.group(1) if match else '1080'}]"

    if mode == "Video + audio":
        cmd += ["-f", f"{selector}+bestaudio/best"]
    elif mode == "Video only":
        cmd += ["-f", f"{selector}/bestvideo"]
    else:
        cmd += ["-x"]
        aq = job.get("audio_quality", "Best available")
        if aq == "Best available":
            cmd += ["-f", "bestaudio/best"]
        elif aq.startswith("MP3"):
            bit = re.search(r"(320|256|192)", aq)
            cmd += ["--audio-format", "mp3", "--audio-quality", f"{bit.group(1) if bit else '192'}K"]
        else:
            cmd += ["--audio-format", aq.lower()]

    container = job.get("container", "Automatic")
    if mode != "Audio only" and container in ("MKV", "MP4"):
        cmd += ["--merge-output-format", container.lower()]

    selected = job.get("playlist_items") or []
    total = int(job.get("playlist_total") or 0)
    if is_playlist and selected and len(selected) != total:
        cmd += ["--playlist-items", ",".join(str(x) for x in selected)]

    root = Path(job.get("output_dir") or default_downloads())
    root.mkdir(parents=True, exist_ok=True)
    if is_playlist and job.get("playlist_folder", True):
        filename = "%(playlist_index)02d - %(title)s.%(ext)s" if job.get("playlist_numbering", True) else "%(title)s.%(ext)s"
        template = str(root / "%(playlist_title)s" / filename)
    else:
        template = str(root / "%(title)s.%(ext)s")
    cmd += ["-o", template, url]
    return cmd


class DownloadWorker(QThread):
    progress = Signal(float)
    detail = Signal(str)
    done = Signal()
    failed = Signal(str)

    def __init__(self, job):
        super().__init__()
        self.job = job
        self.proc = None
        self.cancelled = False

    def cancel(self):
        self.cancelled = True
        try:
            if self.proc and self.proc.poll() is None:
                self.proc.terminate()
        except Exception:
            pass

    def run(self):
        try:
            self.proc = subprocess.Popen(
                build_command(self.job),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
            )
            for raw in self.proc.stdout or []:
                line = raw.rstrip()
                p = re.search(r"\[download\]\s+([0-9.]+)%", line)
                if p:
                    self.progress.emit(float(p.group(1)))
                item = re.search(r"Downloading item\s+(\d+)\s+of\s+(\d+)", line)
                if item:
                    self.detail.emit(f"Playlist item {item.group(1)} of {item.group(2)}")
                elif "[Merger]" in line or "Merging formats" in line:
                    self.detail.emit("Merging video and audio")
                elif "[ExtractAudio]" in line:
                    self.detail.emit("Converting audio")
            code = self.proc.wait()
            if self.cancelled:
                self.failed.emit("Cancelled")
            elif code == 0:
                self.progress.emit(100)
                self.done.emit()
            else:
                self.failed.emit(f"yt-dlp exited with code {code}")
        except Exception as exc:
            self.failed.emit(str(exc))


class SettingsDialog(QDialog):
    def __init__(self, parent, settings):
        super().__init__(parent)
        self.settings = dict(settings)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(520)
        lay = QVBoxLayout(self)

        lay.addWidget(QLabel("Theme"))
        self.theme = QComboBox()
        self.theme.addItems(["Dark", "Light"])
        self.theme.setCurrentText(self.settings.get("theme", "dark").title())
        lay.addWidget(self.theme)

        lay.addWidget(QLabel("Default download folder"))
        row = QHBoxLayout()
        self.output = QLineEdit(self.settings.get("output_dir", default_downloads()))
        browse = QPushButton("Browse")
        browse.clicked.connect(self.pick_output)
        row.addWidget(self.output, 1)
        row.addWidget(browse)
        lay.addLayout(row)

        lay.addWidget(QLabel("cookies.txt"))
        crow = QHBoxLayout()
        self.cookie = QLineEdit(self.settings.get("cookie_file", ""))
        cbrowse = QPushButton("Browse")
        cbrowse.clicked.connect(self.pick_cookie)
        crow.addWidget(self.cookie, 1)
        crow.addWidget(cbrowse)
        lay.addLayout(crow)

        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton("Cancel")
        save = QPushButton("Save")
        save.setObjectName("primary")
        cancel.clicked.connect(self.reject)
        save.clicked.connect(self.accept)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        lay.addLayout(buttons)

    def pick_output(self):
        path = QFileDialog.getExistingDirectory(self, "Choose download folder", self.output.text() or default_downloads())
        if path:
            self.output.setText(path)

    def pick_cookie(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose cookies.txt", str(Path.home()), "Text files (*.txt);;All files (*.*)")
        if path:
            self.cookie.setText(path)

    def values(self):
        return {
            **self.settings,
            "theme": self.theme.currentText().lower(),
            "output_dir": self.output.text().strip() or default_downloads(),
            "cookie_file": self.cookie.text().strip(),
        }


class PlaylistRow(QFrame):
    def __init__(self, entry):
        super().__init__()
        self.setObjectName("playlistRow")
        self.entry = entry
        self.checkbox = QCheckBox()
        self.checkbox.setChecked(True)

        self.thumb = QLabel(str(entry.get("index", "")))
        self.thumb.setObjectName("playlistThumb")
        self.thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumb.setFixedSize(96, 54)

        text_box = QVBoxLayout()
        text_box.setSpacing(2)
        title = QLabel(entry.get("title") or "Untitled")
        title.setObjectName("playlistTitle")
        title.setWordWrap(False)
        meta = QLabel(f"#{entry.get('index', '')}   {format_duration(entry.get('duration'))}")
        meta.setObjectName("muted")
        text_box.addWidget(title)
        text_box.addWidget(meta)

        duration = QLabel(format_duration(entry.get("duration")))
        duration.setObjectName("durationPill")
        duration.setAlignment(Qt.AlignmentFlag.AlignCenter)
        duration.setFixedWidth(58)

        row = QHBoxLayout(self)
        row.setContentsMargins(10, 8, 10, 8)
        row.setSpacing(10)
        row.addWidget(self.checkbox)
        row.addWidget(self.thumb)
        row.addLayout(text_box, 1)
        row.addWidget(duration)

    def set_thumbnail(self, pixmap):
        if pixmap and not pixmap.isNull():
            self.thumb.setPixmap(pixmap.scaled(
                self.thumb.width(), self.thumb.height(),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            ))
            self.thumb.setText("")


class QueueCard(QFrame):
    cancel_requested = Signal(int)

    def __init__(self, idx, job):
        super().__init__()
        self.setObjectName("queueCard")
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        title = QLabel(job.get("title") or "Download")
        title.setObjectName("queueTitle")
        self.status = QLabel(job.get("status", "Queued"))
        self.status.setObjectName("muted")
        cancel = QPushButton("Cancel")
        cancel.setMaximumWidth(84)
        cancel.clicked.connect(lambda: self.cancel_requested.emit(idx))
        if job.get("status") in ("Complete", "Failed", "Cancelled"):
            cancel.hide()
        top.addWidget(title, 1)
        top.addWidget(self.status)
        top.addWidget(cancel)
        lay.addLayout(top)
        self.bar = QProgressBar()
        self.bar.setValue(int(job.get("progress", 0)))
        lay.addWidget(self.bar)
        self.detail = QLabel(job.get("detail", "Waiting"))
        self.detail.setObjectName("muted")
        lay.addWidget(self.detail)


DARK_STYLE = """
QWidget { background:#111318; color:#edf0f6; font-family:'Segoe UI'; font-size:10pt; }
QMainWindow { background:#0c0e12; }
QFrame#panel, QFrame#queueCard { background:#171a21; border:1px solid #2a2f3a; border-radius:12px; }
QFrame#mediaCard, QFrame#optionsCard { background:#13161c; border:1px solid #282e38; border-radius:10px; }
QFrame#playlistRow { background:#151820; border:1px solid #282e38; border-radius:10px; }
QFrame#playlistRow:hover { background:#1d222c; border-color:#3a4352; }
QLabel#playlistThumb { background:#0b0d11; border:1px solid #303744; border-radius:7px; color:#7f899a; font-weight:700; }
QLabel#playlistTitle { font-weight:600; }
QLabel#durationPill { background:#252b35; border-radius:8px; padding:4px 6px; color:#cbd2dd; }
QLabel#fieldLabel { color:#aeb6c5; font-size:9pt; margin-top:2px; }
QListWidget#playlist { background:transparent; border:none; padding:2px; }
QListWidget#playlist::item { background:transparent; border:none; }
QListWidget#playlist::item:selected { background:transparent; border:none; }
QLineEdit, QComboBox, QTableWidget { background:#101218; border:1px solid #343a46; border-radius:8px; padding:7px; }
QTableWidget { gridline-color:#262b34; }
QHeaderView::section { background:#171a21; color:#aeb6c5; padding:7px; border:none; }
QPushButton { background:#252a34; border:1px solid #383f4d; border-radius:8px; padding:8px 13px; }
QPushButton:hover { background:#303744; }
QPushButton#primary { background:#4f7cff; color:white; border:none; font-weight:600; }
QLabel#hero { font-size:22pt; font-weight:700; }
QLabel#section { font-size:12pt; font-weight:650; }
QLabel#muted { color:#98a1b2; }
QLabel#queueTitle { font-weight:600; }
QLabel#previewTitle { font-weight:600; padding:2px 0 4px 0; }
QLabel#thumbnail { background:#0b0d11; border:1px solid #2d3340; border-radius:10px; color:#7f899a; }
QProgressBar { background:#232833; border:none; border-radius:5px; height:9px; }
QProgressBar::chunk { background:#4f7cff; border-radius:5px; }
"""

LIGHT_STYLE = """
QWidget { background:#f4f6fa; color:#171a21; font-family:'Segoe UI'; font-size:10pt; }
QMainWindow { background:#eef1f6; }
QFrame#panel, QFrame#queueCard { background:white; border:1px solid #d8dde7; border-radius:12px; }
QFrame#mediaCard, QFrame#optionsCard { background:#f9fafc; border:1px solid #dce1ea; border-radius:10px; }
QFrame#playlistRow { background:#ffffff; border:1px solid #dce1ea; border-radius:10px; }
QFrame#playlistRow:hover { background:#f6f8fb; border-color:#c6cedb; }
QLabel#playlistThumb { background:#e9edf3; border:1px solid #ccd2dd; border-radius:7px; color:#697386; font-weight:700; }
QLabel#playlistTitle { font-weight:600; }
QLabel#durationPill { background:#edf1f6; border-radius:8px; padding:4px 6px; color:#566071; }
QLabel#fieldLabel { color:#6e7788; font-size:9pt; margin-top:2px; }
QListWidget#playlist { background:transparent; border:none; padding:2px; }
QListWidget#playlist::item { background:transparent; border:none; }
QListWidget#playlist::item:selected { background:transparent; border:none; }
QLineEdit, QComboBox, QTableWidget { background:white; border:1px solid #ccd2dd; border-radius:8px; padding:7px; }
QHeaderView::section { background:#f6f7f9; color:#586173; padding:7px; border:none; }
QPushButton { background:#f6f7f9; border:1px solid #ccd2dd; border-radius:8px; padding:8px 13px; }
QPushButton#primary { background:#315fe8; color:white; border:none; font-weight:600; }
QLabel#hero { font-size:22pt; font-weight:700; }
QLabel#section { font-size:12pt; font-weight:650; }
QLabel#muted { color:#6e7788; }
QLabel#queueTitle { font-weight:600; }
QLabel#previewTitle { font-weight:600; padding:2px 0 4px 0; }
QLabel#thumbnail { background:#e9edf3; border:1px solid #ccd2dd; border-radius:10px; color:#697386; }
QProgressBar { background:#e5e8ef; border:none; border-radius:5px; height:9px; }
QProgressBar::chunk { background:#315fe8; border-radius:5px; }
"""


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.store = Store()
        self.settings = self.store.load_settings()
        self.queue = self.store.load_queue()
        self.preview = None
        self.inspect_worker = None
        self.download_worker = None
        self.current_queue_index = None
        self.net = QNetworkAccessManager(self)

        self.setWindowTitle(f"{APP_NAME} {APP_VERSION}")
        self.resize(1250, 840)
        self.setMinimumSize(980, 700)
        self.build_ui()
        self.apply_theme()
        self.render_queue()
        self.check_dependencies()

    def panel(self):
        frame = QFrame()
        frame.setObjectName("panel")
        return frame

    def label(self, text, object_name=""):
        label = QLabel(text)
        if object_name:
            label.setObjectName(object_name)
        return label

    def build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(22, 18, 22, 18)
        outer.setSpacing(14)

        header = QHBoxLayout()
        titlebox = QVBoxLayout()
        titlebox.addWidget(self.label("Video Downloader", "hero"))
        titlebox.addWidget(self.label("Video, audio and playlists in a cleaner Windows app.", "muted"))
        header.addLayout(titlebox, 1)
        self.theme_btn = QPushButton()
        self.theme_btn.clicked.connect(self.toggle_theme)
        settings_btn = QPushButton("Settings")
        settings_btn.clicked.connect(self.open_settings)
        header.addWidget(self.theme_btn)
        header.addWidget(settings_btn)
        outer.addLayout(header)

        link = self.panel()
        ll = QVBoxLayout(link)
        ll.addWidget(self.label("Paste a link", "section"))
        row = QHBoxLayout()
        self.url = QLineEdit()
        self.url.setPlaceholderText("YouTube video or playlist URL")
        self.url.setClearButtonEnabled(True)
        self.load_btn = QPushButton("Load preview")
        self.load_btn.setObjectName("primary")
        self.load_btn.clicked.connect(self.load_preview)
        row.addWidget(self.url, 1)
        row.addWidget(self.load_btn)
        ll.addLayout(row)
        outer.addWidget(link)

        split = QSplitter(Qt.Orientation.Horizontal)

        left = self.panel()
        l = QVBoxLayout(left)
        l.setContentsMargins(12, 12, 12, 12)
        l.setSpacing(8)

        lh = QHBoxLayout()
        lh.addWidget(self.label("Playlist / video", "section"))
        lh.addStretch()
        all_btn = QPushButton("Select all")
        none_btn = QPushButton("Select none")
        all_btn.clicked.connect(lambda: self.set_all(True))
        none_btn.clicked.connect(lambda: self.set_all(False))
        lh.addWidget(all_btn)
        lh.addWidget(none_btn)
        l.addLayout(lh)

        self.preview_title = self.label("Paste a link and load a preview", "muted")
        l.addWidget(self.preview_title)

        self.playlist = QListWidget()
        self.playlist.setObjectName("playlist")
        self.playlist.setSpacing(7)
        self.playlist.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.playlist.currentRowChanged.connect(self.selection_changed)
        l.addWidget(self.playlist, 1)

        right = self.panel()
        right.setMinimumWidth(390)
        r = QVBoxLayout(right)
        r.setContentsMargins(12, 12, 12, 12)
        r.setSpacing(9)
        r.addWidget(self.label("Preview & options", "section"))

        media = QFrame()
        media.setObjectName("mediaCard")
        media_layout = QVBoxLayout(media)
        media_layout.setContentsMargins(10, 10, 10, 10)
        media_layout.setSpacing(7)

        self.thumb = QLabel("Select an item to preview")
        self.thumb.setObjectName("thumbnail")
        self.thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumb.setFixedHeight(178)
        self.thumb.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        media_layout.addWidget(self.thumb)

        self.selected_title = QLabel("No item selected")
        self.selected_title.setObjectName("previewTitle")
        self.selected_title.setWordWrap(True)
        self.selected_title.setMaximumHeight(44)
        media_layout.addWidget(self.selected_title)
        r.addWidget(media)

        options_card = QFrame()
        options_card.setObjectName("optionsCard")
        ol = QVBoxLayout(options_card)
        ol.setContentsMargins(10, 10, 10, 10)
        ol.setSpacing(5)

        self.mode = QComboBox()
        self.mode.addItems(["Video + audio", "Video only", "Audio only"])
        self.video_quality = QComboBox()
        self.video_quality.addItems(["Best available", "2160p / 4K", "1440p", "1080p", "720p", "480p", "360p"])
        self.audio_quality = QComboBox()
        self.audio_quality.addItems(["Best available", "MP3 320 kbps", "MP3 256 kbps", "MP3 192 kbps", "M4A", "Opus", "WAV"])
        self.container = QComboBox()
        self.container.addItems(["Automatic", "MKV", "MP4"])
        self.container.setCurrentText(self.settings.get("container", "Automatic"))

        for title, widget in [
            ("Download", self.mode), ("Video quality", self.video_quality),
            ("Audio", self.audio_quality), ("Output format", self.container),
        ]:
            label = QLabel(title)
            label.setObjectName("fieldLabel")
            ol.addWidget(label)
            ol.addWidget(widget)

        self.folder_box = QCheckBox("Create folder using playlist title")
        self.folder_box.setChecked(bool(self.settings.get("playlist_folder", True)))
        self.number_box = QCheckBox("Keep original playlist numbering")
        self.number_box.setChecked(bool(self.settings.get("playlist_numbering", True)))
        ol.addWidget(self.folder_box)
        ol.addWidget(self.number_box)
        r.addWidget(options_card)

        actions = QHBoxLayout()
        add = QPushButton("Add to queue")
        add.clicked.connect(self.add_to_queue)
        go = QPushButton("Download now")
        go.setObjectName("primary")
        go.clicked.connect(self.download_now)
        actions.addWidget(add)
        actions.addWidget(go)
        r.addLayout(actions)
        r.addStretch()

        split.addWidget(left)
        split.addWidget(right)
        split.setSizes([760, 410])
        outer.addWidget(split, 1)

        queue_panel = self.panel()
        q = QVBoxLayout(queue_panel)
        qh = QHBoxLayout()
        qh.addWidget(self.label("Download queue", "section"))
        qh.addStretch()
        clear = QPushButton("Clear finished")
        clear.clicked.connect(self.clear_finished)
        open_folder = QPushButton("Open download folder")
        open_folder.clicked.connect(self.open_folder)
        qh.addWidget(clear)
        qh.addWidget(open_folder)
        q.addLayout(qh)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.queue_host = QWidget()
        self.queue_layout = QVBoxLayout(self.queue_host)
        self.queue_layout.setContentsMargins(0, 0, 0, 0)
        self.queue_layout.addStretch()
        self.scroll.setWidget(self.queue_host)
        self.scroll.setMinimumHeight(165)
        q.addWidget(self.scroll)
        outer.addWidget(queue_panel)

        self.statusBar().showMessage("Ready")

    def apply_theme(self):
        dark = self.settings.get("theme", "dark") == "dark"
        QApplication.instance().setStyleSheet(DARK_STYLE if dark else LIGHT_STYLE)
        self.theme_btn.setText("Light mode" if dark else "Dark mode")

    def toggle_theme(self):
        self.settings["theme"] = "light" if self.settings.get("theme") == "dark" else "dark"
        self.store.save_settings(self.settings)
        self.apply_theme()

    def open_settings(self):
        dialog = SettingsDialog(self, self.settings)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.settings = dialog.values()
            self.store.save_settings(self.settings)
            self.apply_theme()

    def check_dependencies(self):
        missing = [name for name in ("yt-dlp", "ffmpeg") if not find_executable(name)]
        if missing:
            QMessageBox.warning(self, "Dependency missing", "Could not find: " + ", ".join(missing))
        else:
            self.statusBar().showMessage("Bundled download tools ready", 4000)

    def load_preview(self):
        url = self.url.text().strip()
        if not url:
            QMessageBox.information(self, "Link needed", "Paste a video or playlist URL first.")
            return
        self.load_btn.setEnabled(False)
        self.preview_title.setText("Loading preview…")
        self.table.setRowCount(0)
        self.inspect_worker = InspectWorker(url, self.settings.get("cookie_file", ""))
        self.inspect_worker.loaded.connect(self.preview_loaded)
        self.inspect_worker.failed.connect(self.preview_failed)
        self.inspect_worker.start()

    def preview_loaded(self, data):
        self.preview = data
        self.url.setText(data["url"])
        self.preview_title.setText(f"{data['title']}  •  {len(data['entries'])} item(s)")
        self.playlist.clear()
        self.playlist_rows = []

        for entry in data["entries"]:
            item = QListWidgetItem()
            item.setSizeHint(self._playlist_item_size())
            row = PlaylistRow(entry)
            self.playlist.addItem(item)
            self.playlist.setItemWidget(item, row)
            self.playlist_rows.append(row)

            thumb_url = entry.get("thumbnail")
            if thumb_url:
                reply = self.net.get(QNetworkRequest(QUrl(thumb_url)))
                reply.finished.connect(lambda r=reply, w=row: self.playlist_thumbnail_ready(r, w))

        if data["entries"]:
            self.playlist.setCurrentRow(0)

        self.load_btn.setEnabled(True)
        self.statusBar().showMessage("Preview loaded", 2500)

    def _playlist_item_size(self):
        from PySide6.QtCore import QSize
        return QSize(0, 72)

    def playlist_thumbnail_ready(self, reply, row_widget):
        try:
            pix = QPixmap()
            if pix.loadFromData(reply.readAll().data()):
                row_widget.set_thumbnail(pix)
        finally:
            reply.deleteLater()

    def preview_failed(self, message):
        self.load_btn.setEnabled(True)
        self.preview_title.setText("Could not load preview")
        QMessageBox.warning(self, "Preview failed", message)

    def set_all(self, checked):
        for row in getattr(self, "playlist_rows", []):
            row.checkbox.setChecked(checked)

    def selection_changed(self, row):
        if not self.preview:
            return
        if row < 0 or row >= len(self.preview["entries"]):
            return

        entry = self.preview["entries"][row]
        self.selected_title.setText(entry.get("title") or "Selected item")
        url = entry.get("thumbnail")
        if not url:
            self.thumb.setPixmap(QPixmap())
            self.thumb.setText("Thumbnail unavailable")
            return

        reply = self.net.get(QNetworkRequest(QUrl(url)))
        reply.finished.connect(lambda r=reply, expected=row: self.thumbnail_ready(r, expected))

    def thumbnail_ready(self, reply, expected):
        try:
            if expected != self.playlist.currentRow():
                return
            pix = QPixmap()
            if pix.loadFromData(reply.readAll().data()):
                target_w = max(300, self.thumb.width() - 8)
                target_h = self.thumb.height() - 8
                self.thumb.setPixmap(pix.scaled(
                    target_w, target_h,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                ))
                self.thumb.setText("")
            else:
                self.thumb.setPixmap(QPixmap())
                self.thumb.setText("Thumbnail unavailable")
        finally:
            reply.deleteLater()


    def make_job(self):
        if not self.preview:
            raise ValueError("Load a preview first.")
        selected = [idx + 1 for idx, row in enumerate(getattr(self, "playlist_rows", [])) if row.checkbox.isChecked()]
        if not selected:
            raise ValueError("Select at least one item.")
        return {
            "title": self.preview["title"],
            "url": self.preview["url"],
            "mode": self.mode.currentText(),
            "video_quality": self.video_quality.currentText(),
            "audio_quality": self.audio_quality.currentText(),
            "container": self.container.currentText(),
            "output_dir": self.settings.get("output_dir", default_downloads()),
            "cookie_file": self.settings.get("cookie_file", ""),
            "playlist_items": selected,
            "playlist_total": len(self.preview["entries"]),
            "playlist_folder": self.folder_box.isChecked(),
            "playlist_numbering": self.number_box.isChecked(),
            "status": "Queued",
            "progress": 0,
            "detail": "Waiting",
        }

    def add_to_queue(self):
        try:
            self.queue.append(self.make_job())
            self.save_state()
            self.render_queue()
        except Exception as exc:
            QMessageBox.information(self, "Cannot add download", str(exc))

    def download_now(self):
        try:
            self.queue.insert(0, self.make_job())
            self.save_state()
            self.render_queue()
            self.start_next()
        except Exception as exc:
            QMessageBox.information(self, "Cannot start download", str(exc))

    def save_state(self):
        self.settings["container"] = self.container.currentText()
        self.settings["playlist_folder"] = self.folder_box.isChecked()
        self.settings["playlist_numbering"] = self.number_box.isChecked()
        self.store.save_settings(self.settings)
        self.store.save_queue(self.queue)

    def render_queue(self):
        while self.queue_layout.count() > 1:
            item = self.queue_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.cards = []
        for idx, job in enumerate(self.queue):
            card = QueueCard(idx, job)
            card.cancel_requested.connect(self.cancel_item)
            self.queue_layout.insertWidget(self.queue_layout.count() - 1, card)
            self.cards.append(card)
        if self.download_worker is None:
            self.start_next()

    def start_next(self):
        if self.download_worker is not None:
            return
        idx = next((i for i, job in enumerate(self.queue) if job.get("status") == "Queued"), None)
        if idx is None:
            return
        self.current_queue_index = idx
        self.queue[idx]["status"] = "Downloading"
        self.queue[idx]["detail"] = "Starting…"
        self.save_state()
        self.render_queue_without_start()
        self.download_worker = DownloadWorker(self.queue[idx])
        self.download_worker.progress.connect(self.on_progress)
        self.download_worker.detail.connect(self.on_detail)
        self.download_worker.done.connect(lambda: self.finish_current("Complete", "Finished"))
        self.download_worker.failed.connect(lambda msg: self.finish_current("Cancelled" if msg == "Cancelled" else "Failed", msg))
        self.download_worker.start()

    def render_queue_without_start(self):
        worker = self.download_worker
        while self.queue_layout.count() > 1:
            item = self.queue_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.cards = []
        for idx, job in enumerate(self.queue):
            card = QueueCard(idx, job)
            card.cancel_requested.connect(self.cancel_item)
            self.queue_layout.insertWidget(self.queue_layout.count() - 1, card)
            self.cards.append(card)
        self.download_worker = worker

    def on_progress(self, value):
        idx = self.current_queue_index
        if idx is None:
            return
        self.queue[idx]["progress"] = value
        if idx < len(self.cards):
            self.cards[idx].bar.setValue(int(value))
        self.store.save_queue(self.queue)

    def on_detail(self, text):
        idx = self.current_queue_index
        if idx is None:
            return
        self.queue[idx]["detail"] = text
        if idx < len(self.cards):
            self.cards[idx].detail.setText(text)
        self.store.save_queue(self.queue)

    def finish_current(self, status, detail):
        idx = self.current_queue_index
        if idx is not None:
            self.queue[idx]["status"] = status
            self.queue[idx]["detail"] = detail
            if status == "Complete":
                self.queue[idx]["progress"] = 100
        self.download_worker = None
        self.current_queue_index = None
        self.save_state()
        self.render_queue_without_start()
        self.start_next()

    def cancel_item(self, idx):
        if idx == self.current_queue_index and self.download_worker:
            self.download_worker.cancel()
        elif 0 <= idx < len(self.queue):
            self.queue[idx]["status"] = "Cancelled"
            self.queue[idx]["detail"] = "Cancelled"
            self.save_state()
            self.render_queue_without_start()

    def clear_finished(self):
        self.queue = [job for job in self.queue if job.get("status") not in ("Complete", "Failed", "Cancelled")]
        self.save_state()
        self.render_queue_without_start()

    def open_folder(self):
        path = Path(self.settings.get("output_dir", default_downloads()))
        path.mkdir(parents=True, exist_ok=True)
        if os.name == "nt":
            os.startfile(str(path))
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def closeEvent(self, event):
        if self.download_worker:
            if QMessageBox.question(self, "Download in progress", "Stop the current download and close?") != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self.download_worker.cancel()
        self.save_state()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
