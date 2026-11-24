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
CONSOLIDATION_INDEX = VIEW_TABS.index("Consolidation")


APP_VERSION = "1.1"   # shown in the title bar


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.resize(1200, 760)
        # Standard native title bar (minimize / maximize / close) so Windows snap layouts
        # and Win+Arrow work for side-by-side use with Excel.
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
        # Only the visible screen is refreshed on a change; _select_view refreshes
        # whichever screen is opened next, so hidden ones never go stale.
        self.records_screen.changed.connect(self._refresh_unless_records)
        self.dashboard_screen.plan_changed.connect(self._refresh_visible)
        self.records_screen.changed.connect(self._refresh_title)
        self.dashboard_screen.plan_changed.connect(self._refresh_title)
        self.records_screen.import_requested.connect(self._open_import)
        for w in (self.dashboard_screen.empty_widget, self.consolidation_screen.empty_widget,
                  self.ppmp_screen.empty, self.sobp_screen.empty,
                  self.app_screen.empty, self.pr_screen.empty):
            w.go_to_records.connect(lambda: self._select_view(RECORDS_INDEX))

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

    # ---------- navigation ----------

    def _current_theme(self):
        return db.get_setting("ui_theme", "light")

    def _toggle_theme(self):
        new = "dark" if self._current_theme() == "light" else "light"
        db.set_setting("ui_theme", new)
        QApplication.instance().setStyleSheet(style.stylesheet(new))
        self.navbar.reload_theme()
        self._apply_theme_chrome()
        self._refresh_visible()

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

    def _refresh_unless_records(self):
        # Records refreshes itself before emitting `changed`.
        if self.views.currentWidget() is not self.records_screen:
            self._refresh_visible()

    def _refresh_visible(self, *_):
        widget = self.views.currentWidget()
        if hasattr(widget, "refresh"):
            widget.refresh()

    def _on_admin_activated(self):
        """Fired by Setup > Admin Access once the right password was entered —
        reveals the Consolidation tab for the rest of this session."""
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
        parts = [f"BPAS - Budget and Procurement Automated System v{APP_VERSION}"]
        plan = db.get_plan(db.get_active_batch())
        if plan["school_name"]:
            tag = plan["school_name"]
            if plan["level"]:
                tag += f" — {plan['level']}"
            parts.append(tag)
        self.setWindowTitle("  |  ".join(parts))

    def _open_import(self):
        dlg = ImportDialog(self)
        dlg.imported.connect(self._refresh_visible)
        dlg.imported.connect(self._refresh_title)
        dlg.exec()

    def _on_setup_saved(self):
        self._refresh_title()
        self._refresh_visible()
