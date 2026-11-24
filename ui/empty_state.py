"""The one 'no plan imported yet' note shown by every screen that needs a plan."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

NO_PLAN_NOTE = "No plan yet.\n\nImport your B+ Template to get started."


def no_plan_label(text: str = NO_PLAN_NOTE) -> QLabel:
    label = QLabel(text)
    label.setAlignment(Qt.AlignCenter)
    label.setObjectName("emptyNote")
    return label


class NoPlanWidget(QWidget):
    """No-plan note plus an 'Import File...' button; emits import_requested when clicked."""
    import_requested = Signal()

    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignCenter)
        lay.setSpacing(16)
        lay.addWidget(no_plan_label())
        btn = QPushButton("Import File...")
        btn.setMinimumSize(180, 44)
        btn.clicked.connect(self.import_requested.emit)
        lay.addWidget(btn, alignment=Qt.AlignCenter)
