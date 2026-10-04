import json
import os
from pathlib import Path

from .tools import APP_NAME, default_downloads


DEFAULTS = {
    "theme": "dark",
    "output_dir": default_downloads(),
    "cookie_file": "",
    "auto_update_check": True,
    "output_container": "Automatic",
    "playlist_folder": True,
    "playlist_numbering": True,
}


class SettingsStore:
    def __init__(self):
        root = Path(os.environ.get("APPDATA", str(Path.home()))) / APP_NAME
        root.mkdir(parents=True, exist_ok=True)
        self.path = root / "settings.json"
        self.queue_path = root / "queue.json"

    def load(self):
        data = dict(DEFAULTS)
        try:
            if self.path.exists():
                loaded = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    data.update(loaded)
        except Exception:
            pass
        return data

    def save(self, data):
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def load_queue(self):
        try:
            if self.queue_path.exists():
                data = json.loads(self.queue_path.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    return data
        except Exception:
            pass
        return []

    def save_queue(self, items):
        self.queue_path.write_text(json.dumps(items, indent=2), encoding="utf-8")
