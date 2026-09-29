"""Lightweight transient status message overlaid on a widget."""

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QLabel


def toast(parent, text: str, ms: int = 4000):
    lbl = QLabel(text, parent)
    lbl.setObjectName("toast")
    lbl.setStyleSheet(
        "background: rgba(15, 23, 42, 0.92); color: #ffffff;"
        " padding: 8px 16px; border-radius: 8px; font-size: 12px;"
    )
    lbl.setAttribute(Qt.WA_TransparentForMouseEvents)
    lbl.adjustSize()
    x = max(12, (parent.width() - lbl.width()) // 2)
    y = parent.height() - lbl.height() - 20
    lbl.move(x, y)
    lbl.show()
    lbl.raise_()
    QTimer.singleShot(ms, lbl.deleteLater)
    return lbl
