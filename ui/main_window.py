import ctypes
from ctypes import wintypes

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QMainWindow, QApplication, QStackedWidget, QVBoxLayout, QMessageBox, QWidget,
)

import db
from ui import style
from ui.appicon import make_icon
from ui.navbar import NavBar
from ui.records_screen import RecordsScreen
from ui.dashboard_screen import DashboardScreen
from ui.ppmp_screen import PPMPScreen
from ui.pr_screen import PRScreen
from ui.sobp_screen import SOBPScreen
from ui.app_screen import APPScreen
from ui.setup_screen import SetupScreen
from ui.consolidation_screen import ConsolidationScreen
from ui.import_dialog import ImportDialog

VIEW_TABS = ["Dashboard", "Records", "Consolidation", "PPMP", "SOB/MDP", "APP",
             "PR/JR/RSQ", "Setup"]
DASHBOARD_INDEX = VIEW_TABS.index("Dashboard")
RECORDS_INDEX = VIEW_TABS.index("Records")
SETUP_INDEX = VIEW_TABS.index("Setup")
CONSOLIDATION_INDEX = VIEW_TABS.index("Consolidation")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self._consolidation_unlocked = False
        self.resize(1200, 760)
        # Title bar with minimize + close only — no maximize/restore button.
        # The app is meant to run maximized, and removing the button (not just
        # guarding against it) also removes the native double-click-title-bar
        # -to-maximize gesture, which is what could leave the window in a
        # broken chrome-less fullscreen state. Spelled out explicitly (rather
        # than subtracting from self.windowFlags()) so minimize/close/title
        # are always present regardless of Qt's platform-specific defaults.
        self.setWindowFlags(
            Qt.Window | Qt.CustomizeWindowHint | Qt.WindowTitleHint
            | Qt.WindowSystemMenuHint | Qt.WindowMinimizeButtonHint
            | Qt.WindowCloseButtonHint
        )
        self._refresh_title()
        self._apply_theme_chrome()

        self.bg = QWidget()
        self.bg.setObjectName("appRoot")
        self.setCentralWidget(self.bg)
        root = QVBoxLayout(self.bg)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        self.records_screen = RecordsScreen()
        self.dashboard_screen = DashboardScreen()
        self.ppmp_screen = PPMPScreen()
        self.sobp_screen = SOBPScreen()
        self.app_screen = APPScreen()
        self.pr_screen = PRScreen()
        self.consolidation_screen = ConsolidationScreen()
        self.setup_screen = SetupScreen()
        self.setup_screen.saved.connect(self._on_setup_saved)
        self.setup_screen.admin_activated.connect(self._on_admin_activated)
        for sig in (self.records_screen.changed, self.dashboard_screen.plan_changed):
            sig.connect(self.dashboard_screen.refresh)
            sig.connect(self.ppmp_screen.refresh)
            sig.connect(self.sobp_screen.refresh)
            sig.connect(self.app_screen.refresh)
            sig.connect(self.pr_screen.refresh)
            sig.connect(self.consolidation_screen.refresh)
            sig.connect(self._refresh_title)
        self.dashboard_screen.plan_changed.connect(self.records_screen.refresh)
        self.records_screen.import_requested.connect(self._open_import)
        self.dashboard_screen.go_to_records.connect(
            lambda: self._select_view(RECORDS_INDEX))

        self.views = QStackedWidget()
        self.views.addWidget(self.dashboard_screen)             # 0
        self.views.addWidget(self.records_screen)               # 1
        self.views.addWidget(self.consolidation_screen)          # 2
        self.views.addWidget(self.ppmp_screen)                  # 3
        self.views.addWidget(self.sobp_screen)                  # 4
        self.views.addWidget(self.app_screen)                   # 5
        self.views.addWidget(self.pr_screen)                    # 6
        self.views.addWidget(self.setup_screen)                 # 7

        self.navbar = NavBar(VIEW_TABS, hidden_names={"Consolidation"})
        self.navbar.toggleTheme.connect(self._toggle_theme)
        self.navbar.viewSelected.connect(self._select_view)
        root.addWidget(self.navbar)
        root.addWidget(self.views)

        self._select_view(DASHBOARD_INDEX)

    # ---------- theme chrome (icon + native title bar) ----------

    def _apply_theme_chrome(self):
        theme = self._current_theme()
        icon = make_icon(theme)
        self.setWindowIcon(icon)
        app = QApplication.instance()
        if app:
            app.setWindowIcon(icon)
        try:
            hwnd = int(self.winId())
            val = ctypes.c_int(1 if theme == "dark" else 0)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                wintypes.HWND(hwnd), 20,           # DWMWA_USE_IMMERSIVE_DARK_MODE
                ctypes.byref(val), ctypes.sizeof(val))
            # force the non-client area to repaint so the change shows immediately
            ctypes.windll.user32.SetWindowPos(
                hwnd, 0, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0004 | 0x0020)
        except Exception:
            pass

    def showEvent(self, event):
        super().showEvent(event)
        self._apply_theme_chrome()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == event.Type.WindowStateChange \
                and self.windowState() & Qt.WindowFullScreen:
            # true fullscreen strips the title bar (no minimize/close) — snap
            # back to maximized-with-chrome instead, however it was triggered.
            # Deferred: correcting the state synchronously, mid-transition,
            # fights Windows' own native frame update and can leave the frame
            # broken (no chrome at all) instead of properly maximized.
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, self._decline_fullscreen)

    def _decline_fullscreen(self):
        if self.windowState() & Qt.WindowFullScreen:
            self.setWindowState(self.windowState() & ~Qt.WindowFullScreen
                                | Qt.WindowMaximized)

    def nativeEvent(self, eventType, message):
        # Belt-and-braces on top of removing the maximize button: swallow a
        # double-click on the title bar itself at the Win32 message level, so
        # it can never toggle maximize/restore no matter what Qt's own hint
        # handling does on a given Windows build.
        if eventType == b"windows_generic_MSG":
            try:
                msg = wintypes.MSG.from_address(int(message))
                WM_NCLBUTTONDBLCLK = 0x00A3
                HTCAPTION = 2
                if msg.message == WM_NCLBUTTONDBLCLK and msg.wParam == HTCAPTION:
                    return True, 0
            except Exception:
                pass
        return super().nativeEvent(eventType, message)

    # ---------- navigation ----------

    def _current_theme(self):
        return db.get_setting("ui_theme", "light")

    def _toggle_theme(self):
        new = "dark" if self._current_theme() == "light" else "light"
        db.set_setting("ui_theme", new)
        QApplication.instance().setStyleSheet(style.stylesheet(new))
        self.navbar.reload_theme()
        self._apply_theme_chrome()
        for w in (self.dashboard_screen, self.records_screen, self.ppmp_screen,
                  self.sobp_screen, self.app_screen, self.pr_screen, self.setup_screen):
            w.refresh()

    def _select_view(self, index):
        current = self.views.currentIndex()
        if (self.views.currentWidget() is self.setup_screen and index != current
                and not self.setup_screen.confirm_leave()):
            self.navbar.set_active_view(current)     # stay on Setup
            return
        self.views.setCurrentIndex(index)
        self.navbar.set_active_view(index)
        widget = self.views.currentWidget()
        if hasattr(widget, "refresh"):
            widget.refresh()

    def _on_admin_activated(self):
        """Fired by Setup > Admin Access once the right password was entered —
        reveals the Consolidation tab for the rest of this session."""
        self._consolidation_unlocked = True
        self.navbar.show_view("Consolidation")
        self._select_view(CONSOLIDATION_INDEX)

    def closeEvent(self, event):
        on_setup = self.views.currentWidget() is self.setup_screen
        if on_setup and not self.setup_screen.confirm_leave():
            event.ignore()
            return
        super().closeEvent(event)

    # ---------- actions ----------

    def _refresh_title(self):
        parts = ["BPAS - Budget + Procurement Automated System"]
        plan = db.get_plan(db.get_active_batch())
        if plan["school_name"]:
            tag = plan["school_name"]
            if plan["level"]:
                tag += f" — {plan['level']}"
            parts.append(tag)
        self.setWindowTitle("  |  ".join(parts))

    def _open_import(self):
        dlg = ImportDialog(self)
        dlg.imported.connect(self.records_screen.refresh)
        dlg.imported.connect(self.dashboard_screen.refresh)
        dlg.imported.connect(self.ppmp_screen.refresh)
        dlg.imported.connect(self.sobp_screen.refresh)
        dlg.imported.connect(self.app_screen.refresh)
        dlg.imported.connect(self.pr_screen.refresh)
        dlg.imported.connect(self.consolidation_screen.refresh)
        dlg.imported.connect(self._refresh_title)
        dlg.exec()

    def _on_setup_saved(self):
        self._refresh_title()
        self.dashboard_screen.refresh()
        self.ppmp_screen.refresh()
        self.sobp_screen.refresh()
        self.app_screen.refresh()
        self.pr_screen.refresh()
