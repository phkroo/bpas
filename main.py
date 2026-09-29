import sys

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

import db
from ui.main_window import MainWindow
from ui.style import stylesheet
from ui.splash import SplashScreen
from ui.appicon import make_icon


def _pick_font(candidates, size):
    from PySide6.QtGui import QFontDatabase
    families = set(QFontDatabase.families())
    for name in candidates:
        if name in families:
            f = QFont(name, size)
            f.setStyleHint(QFont.SansSerif)
            return f
    return QFont(candidates[-1], size)


def _set_taskbar_identity():
    """Give the process its own Windows identity so the taskbar shows the BPAS icon
    instead of grouping under python.exe."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "BPAS.BudgetProcurementAutomatedSystem")
    except Exception:
        pass


def main():
    _set_taskbar_identity()
    db.init_db()
    app = QApplication(sys.argv)
    app.setWindowIcon(make_icon(db.get_setting("ui_theme", "light")))
    app.setFont(_pick_font(["Segoe UI", "IBM Plex Sans", "Inter"], 10))
    app.setStyleSheet(stylesheet(db.get_setting("ui_theme", "light")))

    # show the (empty) splash card right away, build the window behind it, then
    # start the animation so building doesn't eat into it.
    splash = SplashScreen()
    splash.show()
    app.processEvents()

    window = MainWindow()
    screen = app.primaryScreen()
    if screen:
        window.setGeometry(screen.availableGeometry())

    def open_main():
        window.showMaximized()
        window.raise_()
        window.activateWindow()

    splash.finished.connect(open_main)
    splash.start()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
