"""Animated startup splash: Be Proactive -> Be Productive -> Be Positive -> B+ mark
-> "Budget + Procurement Automated System". Custom-painted, no image assets."""

from PySide6.QtCore import Qt, QTimer, QElapsedTimer, QRectF, Signal
from PySide6.QtGui import QPainter, QColor, QFont, QLinearGradient, QPen, QGuiApplication
from PySide6.QtWidgets import QWidget

from ui.appicon import make_pixmap

W, H = 680, 380

# (text, start_ms) — each phrase fades in, holds, fades out over PHRASE_MS
PHRASES = [("Be Proactive", 250), ("Be Productive", 1300), ("Be Positive", 2350)]
PHRASE_MS = 1050
LOGO_START = 3500
TAGLINE_START = 4250
TOTAL_MS = 6300
FADE_OUT_MS = 350


def _ease_out(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def _window(t, start, fade_in, hold, fade_out) -> float:
    """0..1 opacity of an element that fades in, holds, then fades out."""
    x = t - start
    if x < 0:
        return 0.0
    if x < fade_in:
        return x / fade_in
    if x < fade_in + hold:
        return 1.0
    x -= fade_in + hold
    return max(0.0, 1 - x / fade_out) if fade_out else 1.0


class SplashScreen(QWidget):
    finished = Signal()

    def __init__(self):
        super().__init__(None, Qt.SplashScreen | Qt.FramelessWindowHint
                         | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(W, H)
        scr = QGuiApplication.primaryScreen()
        if scr:
            g = scr.availableGeometry()
            self.move(g.center().x() - W // 2, g.center().y() - H // 2)

        self._clock = QElapsedTimer()
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)
        self._done = False
        self._logo = make_pixmap(400, QColor("#ffffff"), QColor("#0a556a"))

    def start(self):
        if not self.isVisible():
            self.show()
        self._clock.start()
        self._timer.start()

    def _tick(self):
        if self._clock.elapsed() >= TOTAL_MS + FADE_OUT_MS:
            self.finish()
            return
        self.update()

    def finish(self):
        if self._done:
            return
        self._done = True
        self._timer.stop()
        self.hide()
        self.finished.emit()

    def mousePressEvent(self, _):
        self.finish()

    def keyPressEvent(self, _):
        self.finish()

    # ------------------------------------------------------------------ paint --

    def paintEvent(self, _):
        t = self._clock.elapsed() if self._clock.isValid() else 0
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)

        out = 1.0
        if t > TOTAL_MS:
            out = max(0.0, 1 - (t - TOTAL_MS) / FADE_OUT_MS)
        p.setOpacity(out)

        # card
        grad = QLinearGradient(0, 0, W, H)
        grad.setColorAt(0.0, QColor("#0a556a"))
        grad.setColorAt(1.0, QColor("#0d7490"))
        p.setPen(Qt.NoPen)
        p.setBrush(grad)
        p.drawRoundedRect(QRectF(6, 6, W - 12, H - 12), 22, 22)

        # soft moving highlight
        sweep = ((t % 3200) / 3200.0)
        hl = QLinearGradient(W * (sweep * 1.6 - 0.4), 0, W * (sweep * 1.6 - 0.1), H)
        hl.setColorAt(0.0, QColor(255, 255, 255, 0))
        hl.setColorAt(0.5, QColor(255, 255, 255, 22))
        hl.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.setBrush(hl)
        p.drawRoundedRect(QRectF(6, 6, W - 12, H - 12), 22, 22)

        # rotating phrases
        f = QFont("Segoe UI", 34)
        f.setWeight(QFont.DemiBold)
        f.setLetterSpacing(QFont.AbsoluteSpacing, 1.5)
        p.setFont(f)
        for text, start in PHRASES:
            a = _window(t, start, 300, PHRASE_MS - 600, 300)
            if a <= 0:
                continue
            rise = (1 - _ease_out((t - start) / 380)) * 14
            self._text(p, text, QRectF(0, H / 2 - 40 + rise, W, 80), a)

        # B+ mark
        la = _ease_out((t - LOGO_START) / 550)
        if la > 0:
            scale = 0.72 + 0.28 * la
            size = 150 * scale
            lift = _ease_out((t - TAGLINE_START) / 450)
            cy = (H / 2 - 22) + (-20 * lift)
            p.setOpacity(out * la)
            p.drawPixmap(QRectF(W / 2 - size / 2, cy - size / 2, size, size),
                         self._logo, QRectF(self._logo.rect()))
            p.setOpacity(out)

        # tagline
        ta = _ease_out((t - TAGLINE_START) / 650)
        if ta > 0:
            f2 = QFont("Segoe UI", 15)
            f2.setLetterSpacing(QFont.AbsoluteSpacing, 3)
            p.setFont(f2)
            self._text(p, "Budget + Procurement Automated System",
                       QRectF(0, H / 2 + 62 + (1 - ta) * 10, W, 40), ta)

        # loading bar
        prog = min(1.0, t / TOTAL_MS)
        bar_w = W - 120
        p.setOpacity(out * 0.25)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#ffffff"))
        p.drawRoundedRect(QRectF(60, H - 46, bar_w, 4), 2, 2)
        p.setOpacity(out * 0.95)
        p.drawRoundedRect(QRectF(60, H - 46, bar_w * _ease_out(prog) if prog < 1 else bar_w, 4),
                          2, 2)
        p.end()

    @staticmethod
    def _text(p, text, rect, alpha):
        base = p.opacity()
        p.setOpacity(base * alpha)
        p.setPen(QPen(QColor("#ffffff")))
        p.drawText(rect, Qt.AlignCenter, text)
        p.setOpacity(base)
