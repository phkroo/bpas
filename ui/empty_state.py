"""The one 'no plan imported yet' note shown by every screen that needs a plan."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

NO_PLAN_NOTE = ("No plan yet.\n\nGo to Records and import your B+ Template.")


def no_plan_label(text: str = NO_PLAN_NOTE) -> QLabel:
    label = QLabel(text)
    label.setAlignment(Qt.AlignCenter)
    label.setObjectName("emptyNote")
    return label


class NoPlanWidget(QWidget):
    """No-plan note plus a 'Go to Records' button; emits go_to_records when clicked."""
    go_to_records = Signal()

    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignCenter)
        lay.setSpacing(16)
        lay.addWidget(no_plan_label())
        btn = QPushButton("Go to Records")
        btn.setMinimumSize(180, 44)
        btn.clicked.connect(self.go_to_records.emit)
        lay.addWidget(btn, alignment=Qt.AlignCenter)
