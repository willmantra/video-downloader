import sys
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QMainWindow, QPushButton, QProgressBar, QSplitter,
    QTableWidget, QVBoxLayout, QWidget,
)

DARK_STYLE = """
QWidget { background:#111318; color:#edf0f6; font-family:'Segoe UI'; font-size:10pt; }
QMainWindow { background:#0c0e12; }
QFrame#panel { background:#171a21; border:1px solid #2a2f3a; border-radius:12px; }
QLineEdit, QComboBox, QTableWidget { background:#101218; border:1px solid #343a46; border-radius:8px; padding:7px; }
QPushButton { background:#252a34; border:1px solid #383f4d; border-radius:8px; padding:8px 13px; }
QPushButton#primary { background:#4f7cff; color:white; border:none; font-weight:600; }
QLabel#hero { font-size:22pt; font-weight:700; }
QLabel#section { font-size:12pt; font-weight:650; }
QLabel#muted { color:#98a1b2; }
QProgressBar { background:#232833; border:none; border-radius:5px; height:9px; }
QProgressBar::chunk { background:#4f7cff; border-radius:5px; }
"""

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Video Downloader 0.5.0-dev")
        self.resize(1250, 840)
        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(22, 18, 22, 18)
        outer.setSpacing(14)

        header = QHBoxLayout()
        titlebox = QVBoxLayout()
        title = QLabel("Video Downloader")
        title.setObjectName("hero")
        subtitle = QLabel("A cleaner, modern interface for video, audio and playlist downloads.")
        subtitle.setObjectName("muted")
        titlebox.addWidget(title)
        titlebox.addWidget(subtitle)
        header.addLayout(titlebox, 1)
        header.addWidget(QPushButton("Check for updates"))
        header.addWidget(QPushButton("Light mode"))
        header.addWidget(QPushButton("Settings"))
        outer.addLayout(header)

        link = QFrame()
        link.setObjectName("panel")
        ll = QVBoxLayout(link)
        lab = QLabel("Paste a link")
        lab.setObjectName("section")
        ll.addWidget(lab)
        row = QHBoxLayout()
        self.url = QLineEdit()
        self.url.setPlaceholderText("YouTube video or playlist URL")
        load = QPushButton("Load preview")
        load.setObjectName("primary")
        row.addWidget(self.url, 1)
        row.addWidget(load)
        ll.addLayout(row)
        outer.addWidget(link)

        split = QSplitter(Qt.Orientation.Horizontal)
        left = QFrame()
        left.setObjectName("panel")
        l = QVBoxLayout(left)
        lh = QHBoxLayout()
        sec = QLabel("Playlist / video")
        sec.setObjectName("section")
        lh.addWidget(sec)
        lh.addStretch()
        lh.addWidget(QPushButton("Select all"))
        lh.addWidget(QPushButton("Select none"))
        l.addLayout(lh)
        table = QTableWidget(0, 3)
        table.setHorizontalHeaderLabels(["Use", "Title", "Length"])
        l.addWidget(table)

        right = QFrame()
        right.setObjectName("panel")
        r = QVBoxLayout(right)
        sec2 = QLabel("Preview & options")
        sec2.setObjectName("section")
        r.addWidget(sec2)
        thumb = QLabel("Thumbnail preview")
        thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        thumb.setMinimumHeight(190)
        r.addWidget(thumb)
        for text, values in [
            ("Download", ["Video + audio", "Video only", "Audio only"]),
            ("Video quality", ["Best available", "2160p / 4K", "1440p", "1080p", "720p"]),
            ("Audio", ["Best available", "MP3 320 kbps", "M4A", "Opus"]),
            ("Output format", ["Automatic", "MKV", "MP4"]),
        ]:
            r.addWidget(QLabel(text))
            combo = QComboBox()
            combo.addItems(values)
            r.addWidget(combo)
        r.addWidget(QCheckBox("Create folder using playlist title"))
        r.addWidget(QCheckBox("Keep original playlist numbering"))
        buttons = QHBoxLayout()
        buttons.addWidget(QPushButton("Add to queue"))
        go = QPushButton("Download now")
        go.setObjectName("primary")
        buttons.addWidget(go)
        r.addLayout(buttons)
        r.addStretch()

        split.addWidget(left)
        split.addWidget(right)
        split.setSizes([760, 390])
        outer.addWidget(split, 1)

        queue = QFrame()
        queue.setObjectName("panel")
        q = QVBoxLayout(queue)
        qh = QHBoxLayout()
        qsec = QLabel("Download queue")
        qsec.setObjectName("section")
        qh.addWidget(qsec)
        qh.addStretch()
        qh.addWidget(QPushButton("Clear finished"))
        qh.addWidget(QPushButton("Open download folder"))
        q.addLayout(qh)
        q.addWidget(QLabel("Queued downloads will appear here as progress cards."))
        bar = QProgressBar()
        bar.setValue(0)
        q.addWidget(bar)
        outer.addWidget(queue)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet(DARK_STYLE)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
