"""Signatories as cards: one card per role (Name + Designation), laid out in a grid.
Used by the Setup screen in place of a table; it keeps the same add / collect / clear
shape the screen already used."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea,
    QVBoxLayout, QWidget,
)

COLUMNS = 2


class SigCard(QFrame):
    removed = Signal(object)
    edited = Signal()

    def __init__(self, role, name, position, show_position, read_only, removable=True):
        super().__init__()
        self.setObjectName("sigCard")
        self.setProperty("locked", bool(read_only))
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 14)
        lay.setSpacing(6)

        head = QHBoxLayout()
        head.setSpacing(6)
        self.role_edit = QLineEdit(role)
        self.role_edit.setObjectName("sigRole")
        self.role_edit.setPlaceholderText("Role, e.g. Prepared by")
        self.role_edit.textEdited.connect(lambda *_: self.edited.emit())
        head.addWidget(self.role_edit, 1)
        if not read_only and removable:
            rm = QPushButton("×")
            rm.setObjectName("sigRemove")
            rm.setToolTip("Remove this signatory")
            rm.setFixedSize(26, 26)
            rm.setCursor(Qt.PointingHandCursor)
            rm.clicked.connect(lambda: self.removed.emit(self))
            head.addWidget(rm)
        lay.addLayout(head)

        self.name_edit = QLineEdit(name)
        self.name_edit.setPlaceholderText("Name")
        self.name_edit.textEdited.connect(self._upper_name)
        lay.addWidget(self.name_edit)

        self.position_edit = None
        if show_position:
            self.position_edit = QLineEdit(position)
            self.position_edit.setPlaceholderText("Designation")
            self.position_edit.textEdited.connect(lambda *_: self.edited.emit())
            lay.addWidget(self.position_edit)

        if read_only:
            # follows the active plan's School Head (Records); editing here would do nothing
            for e in (self.name_edit, self.position_edit):
                if e is not None:
                    e.setReadOnly(True)
                    e.setProperty("locked", True)
                    e.setToolTip("Follows the active plan's School Head (Records) — "
                                 "not editable here.")

    def _upper_name(self, text):
        upper = text.upper()
        if text != upper:                       # names always print in capitals
            pos = self.name_edit.cursorPosition()
            self.name_edit.setText(upper)
            self.name_edit.setCursorPosition(pos)
        self.edited.emit()

    def values(self):
        return {"role": self.role_edit.text().strip(),
                "name": self.name_edit.text().strip().upper(),
                "position": self.position_edit.text().strip() if self.position_edit else ""}


class SigCards(QScrollArea):
    edited = Signal()

    def __init__(self, show_position=True):
        super().__init__()
        self.show_position = show_position
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self._body = QWidget()
        self._body.setObjectName("viewBg")
        outer = QVBoxLayout(self._body)
        outer.setContentsMargins(2, 2, 6, 2)
        self._grid = QGridLayout()
        self._grid.setSpacing(12)
        for c in range(COLUMNS):
            self._grid.setColumnStretch(c, 1)
        outer.addLayout(self._grid)
        outer.addStretch(1)
        self.setWidget(self._body)
        self._cards = []

    def clear(self):
        for card in self._cards:
            card.setParent(None)
            card.deleteLater()
        self._cards = []

    def add_card(self, role="", name="", position="", read_only=False):
        card = SigCard(role, name, position, self.show_position, read_only)
        card.removed.connect(self._remove)
        card.edited.connect(self.edited.emit)
        self._cards.append(card)
        self._relayout()
        return card

    def _remove(self, card):
        if card in self._cards:
            self._cards.remove(card)
            card.setParent(None)
            card.deleteLater()
            self._relayout()
            self.edited.emit()

    def _relayout(self):
        for i, card in enumerate(self._cards):
            self._grid.addWidget(card, i // COLUMNS, i % COLUMNS)

    def collect(self):
        out = []
        for card in self._cards:
            v = card.values()
            if v["role"] or v["name"] or v["position"]:
                out.append(v)
        return out
