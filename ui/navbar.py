"""Banking-app style tab bar: icon-over-label items in a rounded card,
active item tinted with an underline."""

from PySide6.QtCore import Qt, QRectF, QSize, Signal
from PySide6.QtGui import QPainter, QColor, QPen, QFont, QPainterPath
from PySide6.QtWidgets import QWidget, QHBoxLayout, QAbstractButton, QButtonGroup

import db
from ui import style


class NavItem(QAbstractButton):
    def __init__(self, text, icon_key, parent=None):
        super().__init__(parent)
        self.icon_key = icon_key
        self.setText(text)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumSize(58, 58)

    def sizeHint(self):
        from PySide6.QtGui import QFontMetrics
        w = QFontMetrics(self.font()).horizontalAdvance(self.text()) + 22
        return QSize(max(56, w), 58)

    def enterEvent(self, e):
        self.update()

    def leaveEvent(self, e):
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        pal = style.current_palette()

        if self.isChecked():
            col = QColor(pal["accent"])
        elif self.underMouse():
            col = QColor(pal["text"])
        else:
            col = QColor(pal["muted"])

        r = self.rect()
        icon_box = QRectF(r.center().x() - 11, r.top() + 8, 22, 22)
        self._draw_icon(p, icon_box, col)

        f = QFont(self.font())
        f.setPointSize(9)
        f.setBold(self.isChecked())
        p.setFont(f)
        p.setPen(col)
        p.drawText(QRectF(r.left(), r.top() + 32, r.width(), 18),
                   Qt.AlignHCenter | Qt.AlignVCenter, self.text())

        if self.isChecked():
            p.setPen(QPen(QColor(pal["accent"]), 3, Qt.SolidLine, Qt.RoundCap))
            cx = r.center().x()
            p.drawLine(cx - 16, r.bottom() - 3, cx + 16, r.bottom() - 3)
        p.end()

    # ------------------------------------------------------------- icons ----

    def _draw_icon(self, p, b, color):
        p.save()
        pen = QPen(color, 1.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        x, y, w, h = b.x(), b.y(), b.width(), b.height()
        k = self.icon_key

        if k == "home":
            path = QPainterPath()
            path.moveTo(x + 1, y + h * 0.45)
            path.lineTo(x + w / 2, y + 1)
            path.lineTo(x + w - 1, y + h * 0.45)
            p.drawPath(path)
            p.drawRect(QRectF(x + w * 0.18, y + h * 0.42, w * 0.64, h * 0.55))
        elif k == "grid":
            s = w * 0.4
            for dx in (0, w - s):
                for dy in (0, h - s):
                    p.drawRoundedRect(QRectF(x + dx, y + dy, s, s), 2, 2)
        elif k == "list":
            for i in range(3):
                yy = y + 3 + i * (h - 6) / 2
                p.drawEllipse(QRectF(x, yy - 1.5, 3, 3))
                p.drawLine(x + 7, yy, x + w, yy)
        elif k == "tools":
            for frac, kx in ((0.28, 0.7), (0.55, 0.32), (0.82, 0.6)):
                yy = y + h * frac
                p.drawLine(x, yy, x + w, yy)
                p.drawEllipse(QRectF(x + w * kx - 3, yy - 3, 6, 6))
        elif k == "doc":
            path = QPainterPath()
            path.moveTo(x + 2, y + 1)
            path.lineTo(x + w * 0.68, y + 1)
            path.lineTo(x + w - 2, y + h * 0.28)
            path.lineTo(x + w - 2, y + h - 1)
            path.lineTo(x + 2, y + h - 1)
            path.closeSubpath()
            p.drawPath(path)
            for i in range(3):
                yy = y + h * 0.45 + i * 4
                p.drawLine(x + 5, yy, x + w - 5, yy)
        elif k == "bars":
            for i, fh in enumerate((0.45, 0.75, 1.0)):
                bx = x + 2 + i * (w - 6) / 3
                p.drawLine(bx, y + h, bx, y + h * (1 - fh) + 1)
        elif k == "calendar":
            p.drawRoundedRect(QRectF(x + 1, y + 3, w - 2, h - 4), 2, 2)
            p.drawLine(x + 1, y + h * 0.4, x + w - 1, y + h * 0.4)
            p.drawLine(x + w * 0.3, y + 1, x + w * 0.3, y + 5)
            p.drawLine(x + w * 0.7, y + 1, x + w * 0.7, y + 5)
        elif k == "receipt":
            path = QPainterPath()
            path.moveTo(x + 2, y + 1)
            path.lineTo(x + w - 2, y + 1)
            path.lineTo(x + w - 2, y + h - 1)
            for i in range(4):
                path.lineTo(x + w - 2 - (i + 0.5) * (w - 4) / 4, y + h - 4)
                path.lineTo(x + w - 2 - (i + 1) * (w - 4) / 4, y + h - 1)
            path.lineTo(x + 2, y + h - 1)
            path.closeSubpath()
            p.drawPath(path)
            p.drawLine(x + 5, y + h * 0.35, x + w - 5, y + h * 0.35)
            p.drawLine(x + 5, y + h * 0.55, x + w - 5, y + h * 0.55)
        elif k == "gear":
            cx, cy, rr = x + w / 2, y + h / 2, w * 0.28
            import math
            for i in range(8):
                a = i * math.pi / 4
                p.drawLine(cx + rr * math.cos(a), cy + rr * math.sin(a),
                           cx + (rr + 3) * math.cos(a), cy + (rr + 3) * math.sin(a))
            p.drawEllipse(QRectF(cx - rr, cy - rr, rr * 2, rr * 2))
            p.drawEllipse(QRectF(cx - 2, cy - 2, 4, 4))
        elif k == "sun":
            import math
            from PySide6.QtCore import QPointF, QLineF
            cx, cy = round(x + w / 2) + 0.5, round(y + h / 2) + 0.5
            rr = round(w * 0.20)
            p.drawEllipse(QPointF(cx, cy), rr, rr)
            r_in, r_out = rr + 3, rr + 6
            for i in range(8):
                a = i * math.pi / 4
                ca, sa = math.cos(a), math.sin(a)
                p.drawLine(QLineF(cx + r_in * ca, cy + r_in * sa,
                                  cx + r_out * ca, cy + r_out * sa))
        elif k == "moon":
            path = QPainterPath()
            path.addEllipse(QRectF(x + 1, y + 1, w - 2, h - 2))
            sub = QPainterPath()
            sub.addEllipse(QRectF(x + w * 0.35, y, w - 2, h - 2))
            p.drawPath(path.subtracted(sub))
        else:
            p.drawEllipse(b)
        p.restore()


class NavBar(QWidget):
    """Emits toggleTheme(), and viewSelected(index)."""

    toggleTheme = Signal()
    viewSelected = Signal(int)

    def __init__(self, view_tabs, hidden_names=None, parent=None):
        super().__init__(parent)
        self.setObjectName("navBar")
        self.setFixedHeight(66)

        row = QHBoxLayout(self)
        row.setContentsMargins(14, 0, 14, 0)
        row.setSpacing(10)

        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self._view_buttons = []
        self._items_by_name = {}
        hidden_names = hidden_names or set()

        icon_map = {"Dashboard": "grid", "Records": "list", "PPMP": "doc",
                    "SOB/MDP": "bars", "SOB": "bars", "APP": "calendar", "MDP": "calendar",
                    "PR": "receipt", "PR/JR/RSQ": "receipt", "APP-CSE": "doc",
                    "Consolidation": "grid",
                    "Tools": "tools",
                    "Setup": "gear"}
        for vidx, name in enumerate(view_tabs):
            item = NavItem(name, icon_map.get(name, "doc"))
            item.setCheckable(True)
            self.group.addButton(item, vidx)
            item.clicked.connect(lambda _=False, i=vidx: self.viewSelected.emit(i))
            self._view_buttons.append(item)
            self._items_by_name[name] = item
            row.addWidget(item)
            if name in hidden_names:
                item.setVisible(False)

        row.addStretch()

        self.theme_item = NavItem("", "moon")
        self.theme_item.setToolTip("Toggle light / dark theme")
        self.theme_item.setFixedWidth(48)
        self.theme_item.clicked.connect(self.toggleTheme.emit)
        row.addWidget(self.theme_item)

        self.reload_theme()

    def set_active_view(self, index):
        btn = self.group.button(index)
        if btn and not btn.isChecked():
            btn.setChecked(True)

    def show_view(self, name):
        item = self._items_by_name.get(name)
        if item:
            item.setVisible(True)

    def hide_view(self, name):
        item = self._items_by_name.get(name)
        if item:
            item.setVisible(False)

    def reload_theme(self):
        dark = db.get_setting("ui_theme", "light") == "dark"
        self.theme_item.icon_key = "sun" if dark else "moon"
        p = style.current_palette()
        self.setStyleSheet(
            f"#navBar {{ background: {p['surface']};"
            f" border: 1px solid {p['surface_border']}; border-radius: 16px; }}"
        )
        for b in self.findChildren(NavItem):
            b.update()
