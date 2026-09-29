"""Default file locations for open/save dialogs — the user's Downloads folder."""

import os
import subprocess
import sys
from datetime import date

from PySide6.QtCore import QStandardPaths


def downloads_dir() -> str:
    d = QStandardPaths.writableLocation(QStandardPaths.DownloadLocation)
    if not d or not os.path.isdir(d):
        d = os.path.join(os.path.expanduser("~"), "Downloads")
    return d if os.path.isdir(d) else os.path.expanduser("~")


def in_downloads(filename: str) -> str:
    return os.path.join(downloads_dir(), filename)


def dated_download_path(stem: str, ext: str = ".pdf") -> str:
    """<Downloads>/<stem> <YYYY-MM-DD>.pdf, adding ' (n)' if it already exists."""
    d = downloads_dir()
    base = f"{stem} {date.today():%Y-%m-%d}"
    path = os.path.join(d, base + ext)
    n = 2
    while os.path.exists(path):
        path = os.path.join(d, f"{base} ({n}){ext}")
        n += 1
    return path


def open_path(path: str):
    """Open a file with the OS default application."""
    try:
        if sys.platform == "win32":
            os.startfile(path)  # noqa: S606
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception:
        pass
