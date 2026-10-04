import io
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import tkinter as tk
import tempfile
import hashlib
import urllib.error
import urllib.request
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from urllib.parse import parse_qs, urlparse

try:
    from PIL import Image, ImageTk
except Exception:
    Image = None
    ImageTk = None

APP_NAME = "Video Downloader"
DEFAULT_UPDATE_API_URL = "https://api.github.com/repos/willmantra/video-downloader/releases/latest"
INSTALL_DIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Programs" / APP_NAME


def resource_path(name: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / name


def get_app_version() -> str:
    try:
        return resource_path("version.txt").read_text(encoding="utf-8").strip() or "0.0.0"
    except Exception:
        return "0.0.0"


APP_VERSION = get_app_version()


def default_downloads() -> str:
    return str(Path.home() / "Downloads")


def app_root() -> Path:
    """Return the folder containing the installed application executable."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def bundled_executable(name: str):
    """Prefer a dependency bundled beside the installed app."""
    exe_name = name
    if os.name == "nt" and not exe_name.lower().endswith(".exe"):
        exe_name += ".exe"
    candidate = app_root() / "bin" / exe_name
    if candidate.is_file():
        return str(candidate)
    return None


def find_executable(name: str):
    return bundled_executable(name) or shutil.which(name)


class DownloaderApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("1040x820")
        self.minsize(880, 700)

        self.proc = None
        self.worker = None
        self.events = queue.Queue()
        self.preview_entries = []
        self.preview_is_playlist = False
        self.preview_url = ""
        self.preview_photo = None
        self.update_check_in_progress = False
        self.settings = self._load_settings()

        self.url_var = tk.StringVar()
        self.mode_var = tk.StringVar(value="video_audio")
        self.video_quality_var = tk.StringVar(value="Best available")
        self.audio_quality_var = tk.StringVar(value="Best available")
        self.container_var = tk.StringVar(value="Maximum quality (automatic container)")
        self.output_dir_var = tk.StringVar(value=self.settings.get("output_dir", default_downloads()))
        self.cookie_file_var = tk.StringVar(value=self.settings.get("cookie_file", ""))
        self.auto_update_var = tk.BooleanVar(value=bool(self.settings.get("auto_update_check", True)))
        self.update_api_url = self.settings.get("update_api_url", DEFAULT_UPDATE_API_URL) or DEFAULT_UPDATE_API_URL
        self.number_playlist_var = tk.BooleanVar(value=True)
        self.folder_playlist_var = tk.BooleanVar(value=True)
        self.status_var = tk.StringVar(value="Ready")
        self.progress_var = tk.DoubleVar(value=0)
        self.detail_var = tk.StringVar(value="")
        self.selection_var = tk.StringVar(value="No playlist loaded")
        self.preview_title_var = tk.StringVar(value="Select a video to preview")
        self.preview_detail_var = tk.StringVar(value="")

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(100, self._poll_events)
        self.after(250, self._check_dependencies)
        if self.auto_update_var.get():
            self.after(1200, lambda: self.check_for_updates(manual=False))

    def _build_ui(self):
        pad = {"padx": 12, "pady": 7}

        menubar = tk.Menu(self)
        settings_menu = tk.Menu(menubar, tearoff=False)
        settings_menu.add_command(label="Update settings...", command=self.show_update_settings)
        menubar.add_cascade(label="Settings", menu=settings_menu)
        help_menu = tk.Menu(menubar, tearoff=False)
        help_menu.add_command(label="Check for updates", command=lambda: self.check_for_updates(manual=True))
        help_menu.add_separator()
        help_menu.add_command(label="About", command=self.show_about)
        menubar.add_cascade(label="Help", menu=help_menu)
        self.config(menu=menubar)

        outer = ttk.Frame(self)
        outer.pack(fill="both", expand=True, padx=16, pady=12)

        ttk.Label(outer, text="YouTube / yt-dlp Downloader", font=("Segoe UI", 18, "bold")).pack(anchor="w")
        ttk.Label(
            outer,
            text="Paste a video or playlist link, preview the contents, choose what to download, and save it without using Command Prompt.",
            wraplength=960,
        ).pack(anchor="w", pady=(2, 10))

        url_frame = ttk.LabelFrame(outer, text="Video or playlist")
        url_frame.pack(fill="x")
        ttk.Label(url_frame, text="URL").grid(row=0, column=0, sticky="w", **pad)
        self.url_entry = ttk.Entry(url_frame, textvariable=self.url_var)
        self.url_entry.grid(row=0, column=1, sticky="ew", **pad)
        self.inspect_btn = ttk.Button(url_frame, text="Load preview", command=self.inspect_link)
        self.inspect_btn.grid(row=0, column=2, sticky="e", **pad)
        url_frame.columnconfigure(1, weight=1)

        preview_frame = ttk.LabelFrame(outer, text="Preview and playlist selection")
        preview_frame.pack(fill="both", expand=True, pady=(10, 0))
        preview_frame.columnconfigure(0, weight=3)
        preview_frame.columnconfigure(1, weight=2)
        preview_frame.rowconfigure(1, weight=1)

        toolbar = ttk.Frame(preview_frame)
        toolbar.grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 4))
        ttk.Button(toolbar, text="Select all", command=self.select_all).pack(side="left")
        ttk.Button(toolbar, text="Select none", command=self.select_none).pack(side="left", padx=(6, 0))
        ttk.Label(toolbar, textvariable=self.selection_var).pack(side="right")

        columns = ("pick", "num", "title", "duration")
        self.tree = ttk.Treeview(preview_frame, columns=columns, show="headings", selectmode="browse", height=10)
        self.tree.heading("pick", text="Use")
        self.tree.heading("num", text="#")
        self.tree.heading("title", text="Title")
        self.tree.heading("duration", text="Length")
        self.tree.column("pick", width=48, anchor="center", stretch=False)
        self.tree.column("num", width=48, anchor="center", stretch=False)
        self.tree.column("title", width=480, anchor="w")
        self.tree.column("duration", width=72, anchor="center", stretch=False)
        tree_scroll = ttk.Scrollbar(preview_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll.set)
        self.tree.grid(row=1, column=0, sticky="nsew", padx=(10, 0), pady=(0, 10))
        tree_scroll.grid(row=1, column=0, sticky="nse", padx=(0, 0), pady=(0, 10))
        self.tree.bind("<Button-1>", self._tree_click)
        self.tree.bind("<<TreeviewSelect>>", self._tree_selected)

        card = ttk.Frame(preview_frame, padding=10)
        card.grid(row=0, column=1, rowspan=2, sticky="nsew", padx=10, pady=8)
        card.columnconfigure(0, weight=1)
        self.thumb_label = ttk.Label(card, text="Thumbnail preview", anchor="center", relief="groove")
        self.thumb_label.grid(row=0, column=0, sticky="nsew")
        self.thumb_label.configure(width=34)
        ttk.Label(card, textvariable=self.preview_title_var, font=("Segoe UI", 10, "bold"), wraplength=330).grid(row=1, column=0, sticky="w", pady=(8, 2))
        ttk.Label(card, textvariable=self.preview_detail_var, wraplength=330).grid(row=2, column=0, sticky="w")

        middle = ttk.Frame(outer)
        middle.pack(fill="x", pady=(10, 0))
        middle.columnconfigure(0, weight=1)
        middle.columnconfigure(1, weight=1)

        options = ttk.LabelFrame(middle, text="Download options")
        options.grid(row=0, column=0, sticky="nsew", padx=(0, 5))

        ttk.Label(options, text="Download").grid(row=0, column=0, sticky="nw", **pad)
        modes = ttk.Frame(options)
        modes.grid(row=0, column=1, columnspan=3, sticky="w", **pad)
        ttk.Radiobutton(modes, text="Video + audio", variable=self.mode_var, value="video_audio", command=self._mode_changed).pack(side="left", padx=(0, 12))
        ttk.Radiobutton(modes, text="Video only", variable=self.mode_var, value="video", command=self._mode_changed).pack(side="left", padx=(0, 12))
        ttk.Radiobutton(modes, text="Audio only", variable=self.mode_var, value="audio", command=self._mode_changed).pack(side="left")

        ttk.Label(options, text="Video quality").grid(row=1, column=0, sticky="w", **pad)
        self.video_combo = ttk.Combobox(
            options,
            textvariable=self.video_quality_var,
            state="readonly",
            values=("Best available", "2160p / 4K", "1440p", "1080p", "720p", "480p", "360p"),
            width=20,
        )
        self.video_combo.grid(row=1, column=1, sticky="w", **pad)

        ttk.Label(options, text="Audio").grid(row=2, column=0, sticky="w", **pad)
        self.audio_combo = ttk.Combobox(
            options,
            textvariable=self.audio_quality_var,
            state="readonly",
            values=("Best available", "MP3 320 kbps", "MP3 256 kbps", "MP3 192 kbps", "M4A", "Opus", "WAV"),
            width=20,
        )
        self.audio_combo.grid(row=2, column=1, sticky="w", **pad)

        ttk.Label(options, text="Video output").grid(row=3, column=0, sticky="w", **pad)
        self.container_combo = ttk.Combobox(
            options,
            textvariable=self.container_var,
            state="readonly",
            values=("Maximum quality (automatic container)", "MP4 compatibility"),
            width=32,
        )
        self.container_combo.grid(row=3, column=1, columnspan=2, sticky="w", **pad)

        ttk.Checkbutton(options, text="Create folder using playlist title", variable=self.folder_playlist_var).grid(row=4, column=1, columnspan=2, sticky="w", **pad)
        ttk.Checkbutton(options, text="Number playlist videos", variable=self.number_playlist_var).grid(row=5, column=1, columnspan=2, sticky="w", **pad)

        paths = ttk.LabelFrame(middle, text="Save and authentication")
        paths.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
        paths.columnconfigure(1, weight=1)

        ttk.Label(paths, text="Save to").grid(row=0, column=0, sticky="w", **pad)
        ttk.Entry(paths, textvariable=self.output_dir_var).grid(row=0, column=1, sticky="ew", **pad)
        ttk.Button(paths, text="Browse", command=self.choose_output).grid(row=0, column=2, **pad)

        ttk.Label(paths, text="cookies.txt").grid(row=1, column=0, sticky="w", **pad)
        ttk.Entry(paths, textvariable=self.cookie_file_var).grid(row=1, column=1, sticky="ew", **pad)
        ttk.Button(paths, text="Browse", command=self.choose_cookie).grid(row=1, column=2, **pad)
        ttk.Label(paths, text="Useful when YouTube asks you to sign in to confirm you're not a bot.", foreground="#666", wraplength=360).grid(row=2, column=1, columnspan=2, sticky="w", padx=12, pady=(0, 8))

        actions = ttk.Frame(outer)
        actions.pack(fill="x", pady=(10, 0))
        self.download_btn = ttk.Button(actions, text="Download selected", command=self.start_download)
        self.download_btn.pack(side="left")
        self.cancel_btn = ttk.Button(actions, text="Cancel", command=self.cancel_download, state="disabled")
        self.cancel_btn.pack(side="left", padx=(8, 0))
        ttk.Button(actions, text="Open download folder", command=self.open_output_folder).pack(side="right")

        status = ttk.LabelFrame(outer, text="Progress")
        status.pack(fill="x", pady=(10, 0))
        ttk.Label(status, textvariable=self.status_var, font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=12, pady=(8, 2))
        self.progress = ttk.Progressbar(status, variable=self.progress_var, maximum=100)
        self.progress.pack(fill="x", padx=12, pady=4)
        ttk.Label(status, textvariable=self.detail_var).pack(anchor="w", padx=12, pady=(2, 8))

        log_frame = ttk.LabelFrame(outer, text="Activity")
        log_frame.pack(fill="both", expand=False, pady=(10, 0))
        self.log = tk.Text(log_frame, height=7, wrap="word", font=("Consolas", 9), state="disabled")
        scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=scroll.set)
        self.log.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=8)
        scroll.pack(side="right", fill="y", padx=(0, 8), pady=8)

        self._mode_changed()

    def _check_dependencies(self):
        ytdlp = find_executable("yt-dlp")
        ffmpeg = find_executable("ffmpeg")
        missing = []
        if not ytdlp:
            missing.append("yt-dlp")
        if not ffmpeg:
            missing.append("FFmpeg")
        if missing:
            self._append_log("Missing: " + ", ".join(missing))
            self.status_var.set("Dependency check failed")
            messagebox.showwarning(
                "Dependency missing",
                "This app could not find: " + ", ".join(missing) + ".\n\n"
                "The installer normally includes these components. Reinstall the latest version, "
                "or make sure they are available on your Windows PATH, then restart the app.",
            )
        else:
            source = "bundled with the app" if bundled_executable("yt-dlp") and bundled_executable("ffmpeg") else "available on Windows"
            self._append_log(f"yt-dlp and FFmpeg found ({source}).")
        if Image is None:
            self._append_log("Pillow not found: thumbnail images will be disabled until Pillow is installed.")

    def _mode_changed(self):
        mode = self.mode_var.get()
        if mode == "audio":
            self.video_combo.configure(state="disabled")
            self.audio_combo.configure(state="readonly")
            self.container_combo.configure(state="disabled")
        elif mode == "video":
            self.video_combo.configure(state="readonly")
            self.audio_combo.configure(state="disabled")
            self.container_combo.configure(state="readonly")
        else:
            self.video_combo.configure(state="readonly")
            self.audio_combo.configure(state="readonly")
            self.container_combo.configure(state="readonly")

    def choose_output(self):
        chosen = filedialog.askdirectory(initialdir=self.output_dir_var.get() or default_downloads())
        if chosen:
            self.output_dir_var.set(chosen)
            self._save_settings()

    def choose_cookie(self):
        chosen = filedialog.askopenfilename(
            title="Select cookies.txt",
            initialdir=default_downloads(),
            filetypes=[("Cookie files", "*.txt"), ("All files", "*.*")],
        )
        if chosen:
            self.cookie_file_var.set(chosen)
            self._save_settings()

    def _base_command(self):
        ytdlp = find_executable("yt-dlp") or "yt-dlp"
        cmd = [ytdlp, "--newline", "--progress", "--no-colors"]
        ffmpeg = find_executable("ffmpeg")
        if ffmpeg:
            cmd += ["--ffmpeg-location", str(Path(ffmpeg).resolve().parent)]
        cookie = self.cookie_file_var.get().strip()
        if cookie:
            cmd += ["--cookies", cookie]
        return cmd

    def _normalise_url(self, url):
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

    def _output_template(self, is_playlist=False):
        root = self.output_dir_var.get().strip() or default_downloads()
        if is_playlist and self.folder_playlist_var.get():
            folder = "%(playlist_title)s"
            name = "%(playlist_index)02d - %(title)s.%(ext)s" if self.number_playlist_var.get() else "%(title)s.%(ext)s"
            return str(Path(root) / folder / name)
        return str(Path(root) / "%(title)s.%(ext)s")

    def _video_selector(self):
        q = self.video_quality_var.get()
        if q == "Best available":
            return "bestvideo*"
        m = re.search(r"(2160|1440|1080|720|480|360)", q)
        height = m.group(1) if m else "1080"
        return f"bestvideo*[height<={height}]"

    def _selected_playlist_items(self):
        if not self.preview_is_playlist or not self.preview_entries:
            return []
        return [str(i + 1) for i, item in enumerate(self.preview_entries) if item.get("selected", True)]

    def build_command(self):
        url = self.url_var.get().strip()
        if not url:
            raise ValueError("Paste a video or playlist URL first.")
        out_dir = self.output_dir_var.get().strip()
        if not out_dir:
            raise ValueError("Choose a download folder.")
        Path(out_dir).mkdir(parents=True, exist_ok=True)

        url, is_playlist = self._normalise_url(url)
        if is_playlist:
            self._append_log("Playlist detected: using canonical playlist URL.")

        cmd = self._base_command()
        mode = self.mode_var.get()
        aq = self.audio_quality_var.get()

        if mode == "video_audio":
            cmd += ["-f", f"{self._video_selector()}+bestaudio/best"]
        elif mode == "video":
            cmd += ["-f", f"{self._video_selector()}/bestvideo"]
        else:
            cmd += ["-x"]
            if aq == "Best available":
                cmd += ["-f", "bestaudio/best"]
            elif aq.startswith("MP3"):
                bitrate = re.search(r"(320|256|192)", aq).group(1)
                cmd += ["--audio-format", "mp3", "--audio-quality", f"{bitrate}K"]
            elif aq == "M4A":
                cmd += ["--audio-format", "m4a"]
            elif aq == "Opus":
                cmd += ["--audio-format", "opus"]
            elif aq == "WAV":
                cmd += ["--audio-format", "wav"]

        if mode in ("video_audio", "video") and self.container_var.get() == "MP4 compatibility":
            cmd += ["--merge-output-format", "mp4"]

        if is_playlist and self.preview_is_playlist and self.preview_url == url:
            selected = self._selected_playlist_items()
            if not selected:
                raise ValueError("Select at least one video from the playlist.")
            if len(selected) != len(self.preview_entries):
                cmd += ["--playlist-items", ",".join(selected)]

        cmd += ["-o", self._output_template(is_playlist=is_playlist), url]
        return cmd

    def inspect_link(self):
        if self.worker and self.worker.is_alive():
            return
        url = self.url_var.get().strip()
        if not url:
            messagebox.showinfo("URL needed", "Paste a video or playlist URL first.")
            return
        self.status_var.set("Loading preview...")
        self.detail_var.set("")
        self.inspect_btn.configure(state="disabled")
        self._clear_preview()
        self.worker = threading.Thread(target=self._inspect_worker, daemon=True)
        self.worker.start()

    def _inspect_worker(self):
        inspect_url, is_playlist = self._normalise_url(self.url_var.get().strip())
        cmd = self._base_command() + ["--dump-single-json", "--flat-playlist", inspect_url]
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
            if p.returncode != 0:
                raise RuntimeError(p.stderr.strip() or p.stdout.strip() or "Could not inspect link.")
            data = json.loads(p.stdout)
            title = data.get("title") or data.get("fulltitle") or "Link recognised"
            entries = data.get("entries")
            if isinstance(entries, list):
                cleaned = []
                for idx, entry in enumerate(entries, start=1):
                    if not entry:
                        continue
                    cleaned.append({
                        "index": idx,
                        "id": entry.get("id") or "",
                        "title": entry.get("title") or entry.get("id") or f"Video {idx}",
                        "duration": entry.get("duration"),
                        "url": entry.get("url") or entry.get("webpage_url") or "",
                        "thumbnail": entry.get("thumbnail") or self._best_thumbnail(entry),
                        "selected": True,
                    })
                self.events.put(("inspect_playlist", {"title": title, "entries": cleaned, "url": inspect_url}))
            else:
                entry = {
                    "index": 1,
                    "id": data.get("id") or "",
                    "title": title,
                    "duration": data.get("duration"),
                    "url": data.get("webpage_url") or inspect_url,
                    "thumbnail": data.get("thumbnail") or self._best_thumbnail(data),
                    "selected": True,
                }
                self.events.put(("inspect_video", {"entry": entry, "url": inspect_url}))
        except Exception as exc:
            self.events.put(("inspect_error", str(exc)))

    @staticmethod
    def _best_thumbnail(entry):
        thumbs = entry.get("thumbnails") or []
        if not thumbs:
            return ""
        for thumb in reversed(thumbs):
            if thumb and thumb.get("url"):
                return thumb["url"]
        return ""

    def _clear_preview(self):
        self.preview_entries = []
        self.preview_is_playlist = False
        self.preview_url = ""
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.selection_var.set("No playlist loaded")
        self.preview_title_var.set("Select a video to preview")
        self.preview_detail_var.set("")
        self.preview_photo = None
        self.thumb_label.configure(image="", text="Thumbnail preview")

    def _populate_playlist(self, title, entries, url):
        self.preview_is_playlist = True
        self.preview_entries = entries
        self.preview_url = url
        for item in self.tree.get_children():
            self.tree.delete(item)
        for idx, entry in enumerate(entries):
            self.tree.insert("", "end", iid=str(idx), values=("☑", entry["index"], entry["title"], self._format_duration(entry.get("duration"))))
        self._update_selection_label()
        self.status_var.set("Playlist loaded")
        self.detail_var.set(f"{title} — {len(entries)} videos")
        if entries:
            self.tree.selection_set("0")
            self.tree.focus("0")
            self._show_preview_entry(0)

    def _populate_video(self, entry, url):
        self.preview_is_playlist = False
        self.preview_entries = [entry]
        self.preview_url = url
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.tree.insert("", "end", iid="0", values=("☑", 1, entry["title"], self._format_duration(entry.get("duration"))))
        self.selection_var.set("Single video")
        self.status_var.set("Video loaded")
        self.detail_var.set(entry["title"])
        self.tree.selection_set("0")
        self._show_preview_entry(0)

    def _tree_click(self, event):
        region = self.tree.identify("region", event.x, event.y)
        column = self.tree.identify_column(event.x)
        row = self.tree.identify_row(event.y)
        if region == "cell" and column == "#1" and row:
            idx = int(row)
            if 0 <= idx < len(self.preview_entries) and self.preview_is_playlist:
                item = self.preview_entries[idx]
                item["selected"] = not item.get("selected", True)
                values = list(self.tree.item(row, "values"))
                values[0] = "☑" if item["selected"] else "☐"
                self.tree.item(row, values=values)
                self._update_selection_label()
            return "break"
        return None

    def _tree_selected(self, _event=None):
        sel = self.tree.selection()
        if not sel:
            return
        try:
            idx = int(sel[0])
        except Exception:
            return
        self._show_preview_entry(idx)

    def select_all(self):
        if not self.preview_is_playlist:
            return
        for idx, entry in enumerate(self.preview_entries):
            entry["selected"] = True
            values = list(self.tree.item(str(idx), "values"))
            values[0] = "☑"
            self.tree.item(str(idx), values=values)
        self._update_selection_label()

    def select_none(self):
        if not self.preview_is_playlist:
            return
        for idx, entry in enumerate(self.preview_entries):
            entry["selected"] = False
            values = list(self.tree.item(str(idx), "values"))
            values[0] = "☐"
            self.tree.item(str(idx), values=values)
        self._update_selection_label()

    def _update_selection_label(self):
        if not self.preview_is_playlist:
            self.selection_var.set("Single video")
            return
        selected = sum(1 for item in self.preview_entries if item.get("selected", True))
        self.selection_var.set(f"{selected} of {len(self.preview_entries)} selected")

    def _show_preview_entry(self, idx):
        if not (0 <= idx < len(self.preview_entries)):
            return
        entry = self.preview_entries[idx]
        self.preview_title_var.set(entry.get("title") or "Untitled")
        details = []
        if entry.get("duration"):
            details.append(self._format_duration(entry["duration"]))
        if entry.get("id"):
            details.append(f"YouTube ID: {entry['id']}")
        self.preview_detail_var.set(" • ".join(details))
        thumb = entry.get("thumbnail")
        if thumb and Image is not None:
            self.thumb_label.configure(text="Loading thumbnail...", image="")
            threading.Thread(target=self._thumbnail_worker, args=(thumb, idx), daemon=True).start()
        else:
            self.preview_photo = None
            self.thumb_label.configure(image="", text="No thumbnail available")

    def _thumbnail_worker(self, url, idx):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as response:
                data = response.read()
            self.events.put(("thumbnail", {"data": data, "idx": idx}))
        except Exception:
            self.events.put(("thumbnail_error", idx))

    def _apply_thumbnail(self, data, idx):
        sel = self.tree.selection()
        if not sel or int(sel[0]) != idx or Image is None:
            return
        try:
            img = Image.open(io.BytesIO(data))
            img.thumbnail((340, 190), Image.LANCZOS)
            self.preview_photo = ImageTk.PhotoImage(img)
            self.thumb_label.configure(image=self.preview_photo, text="")
        except Exception:
            self.preview_photo = None
            self.thumb_label.configure(image="", text="Thumbnail unavailable")

    @staticmethod
    def _format_duration(seconds):
        if seconds in (None, "", 0):
            return ""
        try:
            seconds = int(seconds)
            h, rem = divmod(seconds, 3600)
            m, s = divmod(rem, 60)
            return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
        except Exception:
            return ""

    def start_download(self):
        if self.worker and self.worker.is_alive():
            return
        try:
            cmd = self.build_command()
        except Exception as exc:
            messagebox.showerror("Cannot start", str(exc))
            return

        self.progress_var.set(0)
        self.status_var.set("Starting download...")
        self.detail_var.set("")
        self.download_btn.configure(state="disabled")
        self.cancel_btn.configure(state="normal")
        self.inspect_btn.configure(state="disabled")
        self._append_log("\n> " + subprocess.list2cmdline(cmd))
        self.worker = threading.Thread(target=self._download_worker, args=(cmd,), daemon=True)
        self.worker.start()

    def _download_worker(self, cmd):
        try:
            creationflags = 0
            if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW"):
                creationflags = subprocess.CREATE_NO_WINDOW
            self.proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=creationflags,
            )
            for line in self.proc.stdout:
                self.events.put(("line", line.rstrip()))
            code = self.proc.wait()
            if code == 0:
                self.events.put(("done", "Download complete"))
            else:
                self.events.put(("error", f"yt-dlp exited with code {code}"))
        except Exception as exc:
            self.events.put(("error", str(exc)))
        finally:
            self.proc = None

    def cancel_download(self):
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
                self.status_var.set("Cancelling...")
            except Exception:
                pass

    def _poll_events(self):
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "line":
                    self._handle_output_line(payload)
                elif kind == "done":
                    self.progress_var.set(100)
                    self.status_var.set(payload)
                    self.detail_var.set("Finished")
                    self._set_idle()
                    messagebox.showinfo("Finished", "Download complete.")
                elif kind == "error":
                    self.status_var.set("Download stopped")
                    self.detail_var.set(payload)
                    self._set_idle()
                    messagebox.showerror("Download error", payload + "\n\nSee Activity for details.")
                elif kind == "inspect_playlist":
                    self._populate_playlist(payload["title"], payload["entries"], payload["url"])
                    self.inspect_btn.configure(state="normal")
                elif kind == "inspect_video":
                    self._populate_video(payload["entry"], payload["url"])
                    self.inspect_btn.configure(state="normal")
                elif kind == "inspect_error":
                    self.status_var.set("Could not load preview")
                    self.detail_var.set(payload)
                    self.inspect_btn.configure(state="normal")
                elif kind == "thumbnail":
                    self._apply_thumbnail(payload["data"], payload["idx"])
                elif kind == "thumbnail_error":
                    sel = self.tree.selection()
                    if sel and int(sel[0]) == payload:
                        self.thumb_label.configure(image="", text="Thumbnail unavailable")
                elif kind == "update_available":
                    self.update_check_in_progress = False
                    self._prompt_update(payload)
                elif kind == "update_current":
                    self.update_check_in_progress = False
                    if payload.get("manual"):
                        messagebox.showinfo("No update available", f"You already have the latest version ({APP_VERSION}).")
                elif kind == "update_error":
                    self.update_check_in_progress = False
                    if payload.get("manual"):
                        messagebox.showwarning("Update check failed", payload.get("message", "Could not check for updates."))
                    else:
                        self._append_log("Update check skipped: " + payload.get("message", "unknown error"))
                elif kind == "update_progress":
                    self.status_var.set(f"Downloading update — {payload:.0f}%")
                    self.progress_var.set(payload)
                elif kind == "update_downloaded":
                    self.status_var.set("Update downloaded")
                    self._launch_update_installer(payload)
        except queue.Empty:
            pass
        self.after(100, self._poll_events)

    def _handle_output_line(self, line):
        self._append_log(line)

        m_item = re.search(r"Downloading item\s+(\d+)\s+of\s+(\d+)", line)
        if m_item:
            self.detail_var.set(f"Playlist item {m_item.group(1)} of {m_item.group(2)}")

        m = re.search(r"\[download\]\s+([0-9.]+)%.*?at\s+([^ ]+).*?ETA\s+([^ ]+)", line)
        if m:
            pct = float(m.group(1))
            self.progress_var.set(pct)
            self.status_var.set(f"Downloading — {pct:.1f}%")
            current = self.detail_var.get()
            speed_eta = f"{m.group(2)} • ETA {m.group(3)}"
            self.detail_var.set((current + " • " if current else "") + speed_eta)
            return

        m2 = re.search(r"\[download\]\s+([0-9.]+)%", line)
        if m2:
            pct = float(m2.group(1))
            self.progress_var.set(pct)
            self.status_var.set(f"Downloading — {pct:.1f}%")

        if "[Merger]" in line or "Merging formats" in line:
            self.status_var.set("Merging video and audio...")
        elif "[ExtractAudio]" in line:
            self.status_var.set("Converting audio...")
        elif "ERROR:" in line:
            self.status_var.set("yt-dlp reported an error")

    def _set_idle(self):
        self.download_btn.configure(state="normal")
        self.cancel_btn.configure(state="disabled")
        self.inspect_btn.configure(state="normal")

    def _append_log(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")


    @staticmethod
    def _version_tuple(value):
        nums = [int(x) for x in re.findall(r"\d+", str(value))[:4]]
        return tuple(nums + [0] * (4 - len(nums)))

    def _settings_path(self):
        root = Path(os.environ.get("APPDATA", str(Path.home()))) / APP_NAME
        root.mkdir(parents=True, exist_ok=True)
        return root / "settings.json"

    def _load_settings(self):
        try:
            path = self._settings_path()
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                return data if isinstance(data, dict) else {}
        except Exception:
            pass
        return {}

    def _save_settings(self):
        try:
            data = {
                "output_dir": self.output_dir_var.get().strip() or default_downloads(),
                "cookie_file": self.cookie_file_var.get().strip(),
                "auto_update_check": bool(self.auto_update_var.get()),
                "update_api_url": self.update_api_url,
            }
            self._settings_path().write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as exc:
            self._append_log(f"Could not save settings: {exc}")

    def _on_close(self):
        self._save_settings()
        if self.proc and self.proc.poll() is None:
            if not messagebox.askyesno("Download in progress", "A download is still running. Close the app and stop it?"):
                return
            try:
                self.proc.terminate()
            except Exception:
                pass
        self.destroy()

    def show_about(self):
        messagebox.showinfo(
            "About Video Downloader",
            f"{APP_NAME}\nVersion {APP_VERSION}\n\nPowered by yt-dlp and FFmpeg.",
        )

    def show_update_settings(self):
        win = tk.Toplevel(self)
        win.title("Update settings")
        win.transient(self)
        win.grab_set()
        win.resizable(False, False)
        frame = ttk.Frame(win, padding=16)
        frame.pack(fill="both", expand=True)
        ttk.Checkbutton(frame, text="Automatically check for app updates when the programme starts", variable=self.auto_update_var).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))
        ttk.Label(frame, text="Update source").grid(row=1, column=0, sticky="w", pady=4)
        api_var = tk.StringVar(value=self.update_api_url)
        entry = ttk.Entry(frame, textvariable=api_var, width=72)
        entry.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(0, 4))
        ttk.Label(frame, text="Normally this is the GitHub Releases 'latest' API address.", foreground="#666").grid(row=3, column=0, columnspan=2, sticky="w", pady=(0, 12))
        buttons = ttk.Frame(frame)
        buttons.grid(row=4, column=0, columnspan=2, sticky="e")

        def save():
            value = api_var.get().strip()
            if not value.startswith(("https://", "http://")):
                messagebox.showerror("Invalid update source", "Enter a valid http:// or https:// address.", parent=win)
                return
            self.update_api_url = value
            self._save_settings()
            win.destroy()

        ttk.Button(buttons, text="Cancel", command=win.destroy).pack(side="right")
        ttk.Button(buttons, text="Save", command=save).pack(side="right", padx=(0, 8))
        win.bind("<Escape>", lambda _e: win.destroy())
        entry.focus_set()

    def check_for_updates(self, manual=True):
        if self.update_check_in_progress:
            if manual:
                messagebox.showinfo("Update check", "An update check is already running.")
            return
        self.update_check_in_progress = True
        if manual:
            self.status_var.set("Checking for updates...")
        threading.Thread(target=self._update_check_worker, args=(manual,), daemon=True).start()

    def _update_check_worker(self, manual):
        try:
            req = urllib.request.Request(
                self.update_api_url,
                headers={
                    "User-Agent": f"VideoDownloader/{APP_VERSION}",
                    "Accept": "application/vnd.github+json",
                },
            )
            with urllib.request.urlopen(req, timeout=15) as response:
                data = json.loads(response.read().decode("utf-8"))
            latest = str(data.get("tag_name") or data.get("name") or "").lstrip("vV")
            if not latest:
                raise RuntimeError("The update service did not return a version number.")
            assets = data.get("assets") or []
            installer = None
            checksum = None
            for asset in assets:
                name = str(asset.get("name") or "").lower()
                if name.endswith(".exe") and ("setup" in name or "installer" in name):
                    installer = asset
                elif name.endswith(".sha256"):
                    checksum = asset
            if self._version_tuple(latest) > self._version_tuple(APP_VERSION):
                if not installer or not installer.get("browser_download_url"):
                    raise RuntimeError(f"Version {latest} is available, but no Windows installer was attached to the release.")
                self.events.put(("update_available", {
                    "version": latest,
                    "url": installer["browser_download_url"],
                    "name": installer.get("name") or f"VideoDownloaderSetup-{latest}.exe",
                    "checksum_url": checksum.get("browser_download_url") if checksum else "",
                    "notes": data.get("body") or "",
                    "page": data.get("html_url") or "",
                    "manual": manual,
                }))
            else:
                self.events.put(("update_current", {"manual": manual}))
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                msg = "The update repository or release has not been published yet."
            else:
                msg = f"Update service returned HTTP {exc.code}."
            self.events.put(("update_error", {"message": msg, "manual": manual}))
        except Exception as exc:
            self.events.put(("update_error", {"message": str(exc), "manual": manual}))

    def _prompt_update(self, info):
        notes = (info.get("notes") or "").strip()
        if len(notes) > 1200:
            notes = notes[:1200].rstrip() + "..."
        text = f"Version {info['version']} is available.\nYou currently have {APP_VERSION}."
        if notes:
            text += "\n\nWhat's new:\n" + notes
        text += "\n\nDownload and install the update now?"
        if messagebox.askyesno("Update available", text):
            self.status_var.set(f"Downloading version {info['version']}...")
            self.progress_var.set(0)
            threading.Thread(target=self._download_update_worker, args=(info,), daemon=True).start()

    def _download_update_worker(self, info):
        try:
            target = Path(tempfile.gettempdir()) / info.get("name", f"VideoDownloaderSetup-{info['version']}.exe")
            req = urllib.request.Request(info["url"], headers={"User-Agent": f"VideoDownloader/{APP_VERSION}"})
            with urllib.request.urlopen(req, timeout=60) as response, target.open("wb") as out:
                total = int(response.headers.get("Content-Length") or 0)
                got = 0
                while True:
                    chunk = response.read(1024 * 256)
                    if not chunk:
                        break
                    out.write(chunk); got += len(chunk)
                    if total:
                        self.events.put(("update_progress", min(100.0, got * 100.0 / total)))
            if target.stat().st_size < 100000:
                raise RuntimeError("The downloaded installer is unexpectedly small.")
            checksum_url = info.get("checksum_url") or ""
            if not checksum_url:
                raise RuntimeError("This release has no SHA-256 checksum, so it will not be installed automatically.")
            creq = urllib.request.Request(checksum_url, headers={"User-Agent": f"VideoDownloader/{APP_VERSION}"})
            with urllib.request.urlopen(creq, timeout=30) as response:
                expected = response.read().decode("utf-8", errors="replace").strip().split()[0].lower()
            actual = hashlib.sha256(target.read_bytes()).hexdigest().lower()
            if not re.fullmatch(r"[0-9a-f]{64}", expected) or actual != expected:
                target.unlink(missing_ok=True)
                raise RuntimeError("The downloaded update failed SHA-256 verification and was deleted.")
            self.events.put(("update_downloaded", {"path": str(target), "version": info["version"]}))
        except Exception as exc:
            self.events.put(("update_error", {"message": f"Could not download the update: {exc}", "manual": True}))

    def _launch_update_installer(self, info):
        installer = Path(info["path"])
        if not installer.exists():
            messagebox.showerror("Update error", "The downloaded installer could not be found.")
            return
        self._save_settings()
        if not messagebox.askokcancel("Install update", "The update has been downloaded and its SHA-256 checksum verified.\n\nWindows will open the installer normally. Complete it, then reopen Video Downloader."):
            return
        try:
            os.startfile(str(installer))
            self.after(500, self.destroy)
        except Exception as exc:
            messagebox.showerror("Update error", str(exc))

    def open_output_folder(self):
        path = Path(self.output_dir_var.get().strip() or default_downloads())
        path.mkdir(parents=True, exist_ok=True)
        try:
            if os.name == "nt":
                os.startfile(str(path))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except Exception as exc:
            messagebox.showerror("Could not open folder", str(exc))


if __name__ == "__main__":
    app = DownloaderApp()
    app.mainloop()
