from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QComboBox, QCompleter, QLineEdit,
    QMessageBox,
)

import db
from ui.import_dialog import _amount


class PlanDialog(QDialog):
    """Edit an imported plan's school / head / allotment."""

    def __init__(self, batch_id, parent=None):
        super().__init__(parent)
        self.batch_id = batch_id
        self.setWindowTitle("Plan Details")
        self.setModal(True)
        self.setMinimumWidth(560)

        plan = db.get_plan(batch_id)

        form = QFormLayout(self)
        form.setContentsMargins(20, 20, 20, 20)
        form.setSpacing(12)

        self.school_combo = QComboBox()
        self.school_combo.setEditable(True)
        self.school_combo.setInsertPolicy(QComboBox.NoInsert)
        current_idx = 0
        for i, s in enumerate(db.list_schools()):
            self.school_combo.addItem(f"{s['name']}  —  {s['level']}", dict(s))
            if s["school_id"] == plan["school_id"] and s["level"] == plan["level"]:
                current_idx = i
        self.school_combo.setCurrentIndex(current_idx)
        comp = self.school_combo.completer()
        comp.setFilterMode(Qt.MatchContains)
        comp.setCompletionMode(QCompleter.PopupCompletion)

        self.head_edit = QLineEdit(plan["school_head"])
        self.total_edit = QLineEdit(
            f"{plan['total_allotment']:.2f}" if plan["total_allotment"] else "")
        self.gad_edit = QLineEdit(
            f"{plan['gad_allotment']:.2f}" if plan["gad_allotment"] else "")

        form.addRow("School:", self.school_combo)
        form.addRow("School Head:", self.head_edit)
        form.addRow("Total Allotment:", self.total_edit)
        form.addRow("GAD Allotment:", self.gad_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def _accept(self):
        total = _amount(self.total_edit.text())
        gad = _amount(self.gad_edit.text())
        if total is None or gad is None:
            QMessageBox.warning(self, "Invalid Number",
                                "Total Allotment and GAD Allotment must be numbers.")
            return
        s = self.school_combo.currentData()
        fields = dict(
            school_head=self.head_edit.text().strip(),
            total_allotment=total, gad_allotment=gad,
        )
        if isinstance(s, dict):
            fields.update(
                school_name=s["name"], school_id=s["school_id"],
                iu_code=s["iu_code"], level_type=s["level_type"], level=s["level"],
            )
        db.set_batch_plan(self.batch_id, **fields)
        self.accept()
