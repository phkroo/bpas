import re

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QComboBox, QCompleter, QLineEdit,
    QLabel, QMessageBox, QVBoxLayout, QWidget, QScrollArea, QFrame,
)

import db

_GAD_RE = re.compile(r"\bGAD\b", re.IGNORECASE)


class NoScrollComboBox(QComboBox):
    """A QComboBox that always ignores the mouse wheel — scrolling over a
    dropdown (focused or not) scrolls the dialog's scroll area instead of
    silently changing the field's value. Use the dropdown arrow or keyboard
    to change the value."""

    def wheelEvent(self, event):
        event.ignore()

# (field, label, kind) — kind: "combo" (dropdown you can also type in) | "text" | "number"
# Order matches the requested field sequence; GAD Category and APP CSE sit right
# after the field that governs whether they're usable.
FORM_FIELDS = [
    ("category_uacs_school", "Category / UACS / School", "combo"),
    ("pap_name", "PAP Name", "combo"),
    ("gad_category", "GAD Category", "combo"),
    ("general_description", "General Description", "combo"),
    ("item_description", "Item Description", "text"),
    ("accounting_title", "Accounting Title", "combo"),
    ("app_for", "APP Form", "combo"),
    ("app_cs", "APP CSE", "combo"),
    ("mode_of_procurement", "Mode of Procurement", "combo"),
    ("unit_price", "Unit Price", "number"),
    ("qty", "Quantity", "number"),
    ("unit", "Unit", "combo"),
    ("month", "Month", "combo"),
]

# always offered even if no row uses them yet
_BASELINE = {"app_for": ["CSE", "NON CSE"], "app_cs": ["PART I", "PART II", "OTHER ITEMS"]}


def _num(text):
    try:
        return round(float((text or "").replace(",", "").strip() or 0), 2)
    except ValueError:
        return None


def _month_options(existing):
    """Every month, written in the same case as the plan's own data."""
    upper = bool(existing) and existing[0].isupper()
    names = [m.upper() if upper else m for m in db.MONTH_ORDER]
    extra = [m for m in existing if m.lower() not in {n.lower() for n in names}]
    return names + extra


def _options(batch_id) -> dict:
    """Dropdown values come from what is already in the database."""
    out = {}
    for field in ("category_uacs_school", "pap_name", "gad_category",
                  "accounting_title", "mode_of_procurement", "app_for", "app_cs",
                  "unit", "month"):
        out[field] = db.distinct_values(field)
    out["general_description"] = db.distinct_values("general_description", batch_id)

    for field, values in _BASELINE.items():
        out[field] += [v for v in values if v not in out[field]]
    # titles from the Account Codes list stay selectable before any row uses them
    known = set(out["accounting_title"])
    out["accounting_title"] += sorted(
        r["title"] for r in db.list_mooe_accounts() if r["title"] not in known)
    out["month"] = _month_options(out["month"])
    return out


class ItemDialog(QDialog):
    """Add a record (row=None) or edit one (row=<db record>). Fixed size,
    fixed position — not resizable, not draggable."""

    def __init__(self, batch_id, row=None, parent=None):
        super().__init__(parent)
        self.batch_id = batch_id
        self.setWindowTitle("Add Record" if row is None else "Edit Record")
        self.setModal(True)
        self.values = None
        self._locked_pos = None

        options = _options(batch_id)
        self._titles = set(db.list_account_codes())

        self.widgets = {}
        self._form = form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        for field, label, kind in FORM_FIELDS:
            form.addRow(label + ":", self._make(field, kind, row, options))

        self.amount_lbl = QLabel()
        self.amount_lbl.setStyleSheet("font-weight: bold; font-size: 15px;")
        form.addRow("Amount:", self.amount_lbl)

        body = QWidget()
        body.setLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)

        # initial load: gray out a mismatched field without erasing whatever
        # value the row already had (only live edits clear it — see below)
        self._apply_gad_gate(self.widgets["pap_name"].currentText(), clear=False)
        self._apply_app_cs_gate(self.widgets["app_for"].currentText(), clear=False)
        self._recalc()

        # the natural (unclamped) content size, measured before it's wrapped in
        # a scroll area below — that's what decides whether we need to scroll
        natural = body.sizeHint()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(body)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.addWidget(scroll, 1)
        root.addWidget(buttons)

        self._fit_and_lock(natural, buttons.sizeHint().height())

    def _fit_and_lock(self, natural_body_size, buttons_height):
        host = self.parent().window() if self.parent() else None
        scr = host.screen() if host else QGuiApplication.primaryScreen()
        avail = scr.availableGeometry() if scr else None
        margin = 80   # dialog chrome + breathing room, so it never touches screen edges

        want_w = natural_body_size.width() + margin
        want_h = natural_body_size.height() + buttons_height + margin

        if avail is not None:
            max_w = max(300, avail.width() - 80)
            max_h = max(300, avail.height() - 80)
            want_w = min(want_w, max_w)
            want_h = min(want_h, max_h)

        # not resizable
        self.setFixedSize(want_w, want_h)

        # not movable: any attempt to move it snaps back to its initial spot,
        # which is centered within the *available* area — never under the
        # taskbar or off the top of the screen, even when the host is maximized
        if avail is not None:
            self.move(avail.center() - self.rect().center())
        elif host is not None:
            self.move(host.frameGeometry().center() - self.rect().center())
        self._locked_pos = self.pos()

    def moveEvent(self, event):
        super().moveEvent(event)
        if self._locked_pos is not None and self.pos() != self._locked_pos:
            self.move(self._locked_pos)

    def _make(self, field, kind, row, options):
        current = "" if row is None or row[field] is None else str(row[field])
        if kind == "combo":
            w = NoScrollComboBox()
            w.setEditable(True)
            w.setInsertPolicy(QComboBox.NoInsert)
            w.setMaxVisibleItems(14)
            w.addItem("")
            w.addItems([str(v) for v in options.get(field, [])])
            w.setCurrentText(current)
            comp = w.completer()
            comp.setFilterMode(Qt.MatchContains)
            comp.setCaseSensitivity(Qt.CaseInsensitive)
            comp.setCompletionMode(QCompleter.PopupCompletion)
            w.currentTextChanged.connect(self._recalc)
            if field == "pap_name":
                w.currentTextChanged.connect(self._apply_gad_gate)
            elif field == "app_for":
                w.currentTextChanged.connect(self._apply_app_cs_gate)
        else:
            if kind == "number" and row is not None and row[field] is not None:
                current = f"{float(row[field]):.2f}"
            w = QLineEdit(current)
            w.textChanged.connect(self._recalc)
        self.widgets[field] = w
        return w

    # ---- conditional visibility / enable ----

    def _apply_gad_gate(self, pap_text, clear=True):
        is_gad = bool(_GAD_RE.search(pap_text or ""))
        w = self.widgets["gad_category"]
        self._form.setRowVisible(w, is_gad)
        if not is_gad and clear:
            w.setCurrentText("")

    def _apply_app_cs_gate(self, app_for_text, clear=True):
        is_cse = (app_for_text or "").strip().upper() == "CSE"
        w = self.widgets["app_cs"]
        self._form.setRowVisible(w, is_cse)
        if not is_cse and clear:
            w.setCurrentText("")

    def _text(self, field):
        w = self.widgets[field]
        return (w.currentText() if isinstance(w, QComboBox) else w.text()).strip()

    def _recalc(self, *_):
        if "qty" not in self.widgets or not hasattr(self, "amount_lbl"):
            return
        price, qty = _num(self._text("unit_price")), _num(self._text("qty"))
        if price is None or qty is None:
            self.amount_lbl.setText("—")
        else:
            self.amount_lbl.setText(f"{round(price * qty, 2):,.2f}")

    def _accept(self):
        if not self._text("item_description"):
            QMessageBox.warning(self, "Missing Item", "Item Description is required.")
            return
        price, qty = _num(self._text("unit_price")), _num(self._text("qty"))
        if price is None or qty is None:
            QMessageBox.warning(self, "Invalid Number",
                                "Unit Price and Quantity must be numbers.")
            return
        title = self._text("accounting_title")
        if title and self._titles and title not in self._titles:
            if QMessageBox.question(
                    self, "Unknown Accounting Title",
                    f"'{title}' is not in the Account Codes list, so no UACS code will "
                    "be found for it.\n\nSave anyway?") != QMessageBox.Yes:
                return

        values = {f: self._text(f) for f, _l, k in FORM_FIELDS if k != "number"}
        values.update(unit_price=price, qty=qty, total_amount=round(price * qty, 2))
        self.values = values
        self.accept()
