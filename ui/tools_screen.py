from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QListWidget, QStackedWidget, QFrame,
)

from ui.appcse_screen import APPCSEScreen

TOOLS = [
    ("APP-CSE Import", APPCSEScreen),
]


class ToolsScreen(QWidget):
    def __init__(self):
        super().__init__()
        row = QHBoxLayout(self)
        row.setSpacing(14)

        self.nav = QListWidget()
        self.nav.setObjectName("setupNav")
        self.nav.setFixedWidth(220)
        self.nav.setVisible(len(TOOLS) > 1)   # no sidebar while there is only one tool
        self.nav.addItems([name for name, _ in TOOLS])
        self.nav.currentRowChanged.connect(self._select)
        row.addWidget(self.nav)

        self.pages = QStackedWidget()
        row.addWidget(self.pages, stretch=1)
        self._widgets = []
        for _, cls in TOOLS:
            w = cls()
            self._widgets.append(w)
            self.pages.addWidget(w)

        self.nav.setCurrentRow(0)

    def _select(self, i):
        if i >= 0:
            self.pages.setCurrentIndex(i)

    def refresh(self):
        for w in self._widgets:
            if hasattr(w, "refresh"):
                w.refresh()
