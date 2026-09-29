"""The BPAS "B+" mark — window/taskbar icon and splash logo, drawn at runtime."""

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QPainterPath, QFont, QTransform

from ui import style


def _mark_path(s: float) -> QPainterPath:
    """A bold 'B' with a '+' of the same height fused onto its right edge, as one shape."""
    font = QFont("Segoe UI Black")
    font.setStyleHint(QFont.SansSerif)
    font.setWeight(QFont.Black)
    font.setPixelSize(100)
    b = QPainterPath()
    b.addText(0, 0, font, "B")

    target_h = s * 0.42
    br = b.boundingRect()
    k = target_h / br.height()
    b = QTransform().scale(k, k).map(b)
    br = b.boundingRect()

    size = br.height()                  # the + is as tall/wide as the B
    half = size / 2
    arm = size * 0.27                   # arm thickness
    overlap = arm * 0.55                # tuck into the B's solid right edge
    cx = br.right() - overlap + half
    cy = br.center().y()
    horiz = QPainterPath()
    horiz.addRoundedRect(QRectF(cx - half, cy - arm / 2, size, arm), arm * 0.25, arm * 0.25)
    vert = QPainterPath()
    vert.addRoundedRect(QRectF(cx - arm / 2, cy - half, arm, size), arm * 0.25, arm * 0.25)
    plus = horiz.united(vert)

    joined = b.united(plus)
    jr = joined.boundingRect()
    dx = s / 2 - jr.center().x()
    dy = s / 2 - jr.center().y()
    return QTransform().translate(dx, dy).map(joined)


def make_pixmap(size: int, bg: QColor, fg: QColor) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(bg)
    p.drawRoundedRect(QRectF(size * 0.04, size * 0.04, size * 0.92, size * 0.92),
                      size * 0.22, size * 0.22)
    p.setBrush(fg)
    p.drawPath(_mark_path(float(size)))
    p.end()
    return pm


def make_icon(theme: str = "light") -> QIcon:
    pal = style.PALETTES.get(theme, style.PALETTES["light"])
    icon = QIcon()
    for s in (16, 20, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(make_pixmap(s, QColor(pal["accent"]), QColor("#ffffff")))
    return icon
