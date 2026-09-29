from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel


class PlaceholderScreen(QWidget):
    def __init__(self, name: str):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        label = QLabel(f"{name} — coming soon")
        label.setAlignment(Qt.AlignCenter)
        label.setObjectName("onBg")
        label.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(label)

    def refresh(self):
        pass
