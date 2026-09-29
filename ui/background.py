"""Finance-themed painted background (gradient + subtle chart/coin motif)."""

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QLinearGradient, QPainter, QPainterPath, QColor, QBrush, QFont, QPen
from PySide6.QtWidgets import QWidget

import db
from ui import style


class FinanceBackground(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, False)
        self._pal = None
        self.reload_theme()

    def reload_theme(self):
        theme = db.get_setting("ui_theme", "light")
        self._pal = style.PALETTES.get(theme, style.PALETTES["light"])
        self._dark = theme == "dark"
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()

        g0, g1, g2 = self._pal["grad"]
        grad = QLinearGradient(0, 0, w, h)
        grad.setColorAt(0.0, QColor(g0))
        grad.setColorAt(0.5, QColor(g1))
        grad.setColorAt(1.0, QColor(g2))
        p.fillRect(self.rect(), grad)

        ink = QColor("#ffffff") if self._dark else QColor("#0f172a")
        accent = QColor(self._pal["accent"])

        # faint chart grid
        grid = QColor(ink); grid.setAlpha(10 if self._dark else 8)
        p.setPen(QPen(grid, 1))
        step = 52
        for y in range(step, h, step):
            p.drawLine(0, y, w, y)
        for x in range(step, w, step):
            p.drawLine(x, 0, x, h)

        # large ascending area-chart silhouette along the bottom
        pts = [0.0, 0.32, 0.20, 0.46, 0.36, 0.58, 0.5, 0.7, 0.62, 0.82, 0.95, 1.0]
        base_y = h * 0.98
        amp = h * 0.42
        path = QPainterPath()
        path.moveTo(0, base_y)
        n = len(pts)
        for i, frac in enumerate(pts):
            x = w * i / (n - 1)
            path.lineTo(x, base_y - amp * frac)
        path.lineTo(w, base_y)
        path.closeSubpath()
        fill = QColor(accent); fill.setAlpha(26 if self._dark else 20)
        p.fillPath(path, QBrush(fill))
        line = QColor(accent); line.setAlpha(70 if self._dark else 55)
        p.setPen(QPen(line, 2))
        p.drawPath(path)

        # candlesticks bottom-right
        p.setPen(Qt.NoPen)
        cx = w - 320
        for i in range(9):
            up = i % 3 != 1
            col = QColor(accent if up else QColor("#dc2626"))
            col.setAlpha(38 if self._dark else 30)
            p.setBrush(col)
            bx = cx + i * 34
            bh = 26 + (i * 13) % 60
            by = h - 90 - ((i * 17) % 40)
            p.drawRect(QRectF(bx, by, 12, bh))
            wick = QColor(col); wick.setAlpha(col.alpha())
            p.setPen(QPen(wick, 2))
            p.drawLine(QPointF(bx + 6, by - 14), QPointF(bx + 6, by + bh + 12))
            p.setPen(Qt.NoPen)

        # big peso watermark, top-right
        mark = QColor(ink); mark.setAlpha(12 if self._dark else 7)
        f = QFont(); f.setPointSize(220); f.setBold(True)
        p.setFont(f)
        p.setPen(mark)
        p.drawText(QRectF(w - 460, -70, 440, 380), Qt.AlignRight | Qt.AlignTop, "₱")

        p.end()
