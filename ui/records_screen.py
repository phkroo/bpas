from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QLineEdit,
    QComboBox, QTableWidget, QTableWidgetItem, QFileDialog, QMessageBox,
    QHeaderView, QAbstractItemView,
)

import db
import export_excel

FIELDS = [
    "id", "category_uacs_school", "pap_name", "general_description", "item_description",
    "gad_category", "accounting_title", "mode_of_procurement", "app_for", "app_cs",
    "unit_price", "qty", "unit", "month", "total_amount",
]
HEADERS = [
    "ID", "Category/UACS/School", "PAP Name", "General Description", "Item Description",
    "GAD Category", "Accounting Title", "Mode of Procurement", "APP Form", "APP CSE",
    "Unit Price", "Quantity", "Unit", "Month", "Amount",
]
HEADERS_WRAPPED = [
    "ID", "Category / UACS /\nSchool", "PAP Name", "General\nDescription",
    "Item\nDescription", "GAD\nCategory", "Accounting\nTitle", "Mode of\nProcurement",
    "APP\nForm", "APP\nCSE", "Unit\nPrice", "Quantity", "Unit", "Month", "Amount",
]


class RecordsScreen(QWidget):
    changed = Signal()
    import_requested = Signal()

    def __init__(self):
        super().__init__()
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # ---- empty state ----
        self.empty_widget = QWidget()
        empty_layout = QVBoxLayout(self.empty_widget)
        empty_layout.setAlignment(Qt.AlignCenter)
        empty_layout.setSpacing(16)
        empty_label = QLabel(
            "No plan yet.\n\nClick \"Import File...\" and choose your BPAS Excel or plan "
            "file (.bpasx) — the school is read from the file."
        )
        empty_label.setAlignment(Qt.AlignCenter)
        empty_label.setObjectName("onBg")
        empty_label.setStyleSheet("font-size: 16px;")
        empty_import_btn = QPushButton("Import File...")
        empty_import_btn.setMinimumSize(200, 44)
        empty_import_btn.clicked.connect(self.import_requested.emit)
        empty_layout.addWidget(empty_label)
        empty_layout.addWidget(empty_import_btn, alignment=Qt.AlignCenter)
        layout.addWidget(self.empty_widget)

        # ---- plan switcher ----
        self.plan_widget = QWidget()
        plan_row = QHBoxLayout(self.plan_widget)
        plan_row.setContentsMargins(0, 0, 0, 0)
        plan_row.setSpacing(8)
        plan_lbl = QLabel("Plan:")
        plan_lbl.setObjectName("onBg")
        plan_lbl.setStyleSheet("font-weight: bold;")
        plan_row.addWidget(plan_lbl)
        self.batch_combo = QComboBox()
        self.batch_combo.setMinimumWidth(280)
        self.batch_combo.currentIndexChanged.connect(self._on_plan_changed)
        plan_row.addWidget(self.batch_combo, 1)

        import_btn = QPushButton("Import New Plan")
        import_btn.clicked.connect(self.import_requested.emit)
        plan_row.addWidget(import_btn)

        edit_btn = QPushButton("Edit")
        edit_btn.setObjectName("secondary")
        edit_btn.clicked.connect(self._edit_plan)
        plan_row.addWidget(edit_btn)

        delete_plan_btn = QPushButton("Delete Plan")
        delete_plan_btn.setObjectName("danger")
        delete_plan_btn.clicked.connect(self._delete_plan)
        plan_row.addWidget(delete_plan_btn)
        layout.addWidget(self.plan_widget)

        # ---- filters ----
        self.filter_widget = QWidget()
        filter_row = QHBoxLayout(self.filter_widget)
        filter_row.setContentsMargins(0, 0, 0, 0)
        filter_row.setSpacing(8)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search...")
        self.search_input.returnPressed.connect(self.refresh)
        filter_row.addWidget(self.search_input, 1)

        self.pap_combo = QComboBox()
        self.gad_combo = QComboBox()
        self.accounting_combo = QComboBox()
        self.procurement_combo = QComboBox()
        for combo, label in [
            (self.pap_combo, "All PAP Names"),
            (self.gad_combo, "All GAD Categories"),
            (self.accounting_combo, "All Accounting Titles"),
            (self.procurement_combo, "All Procurement Modes"),
        ]:
            combo.addItem(label, None)
            combo.currentIndexChanged.connect(self.refresh)
            filter_row.addWidget(combo, 1)

        apply_btn = QPushButton("Search")
        apply_btn.clicked.connect(self.refresh)
        filter_row.addWidget(apply_btn)

        clear_btn = QPushButton("Clear Filters")
        clear_btn.setObjectName("secondary")
        clear_btn.clicked.connect(self.clear_filters)
        filter_row.addWidget(clear_btn)

        for w in (self.search_input, self.pap_combo, self.gad_combo,
                  self.accounting_combo, self.procurement_combo):
            w.setMinimumWidth(120)
            w.setMaximumWidth(16777215)

        layout.addWidget(self.filter_widget)

        self.table = QTableWidget(0, len(FIELDS))
        self.table.setHorizontalHeaderLabels(HEADERS_WRAPPED)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.Interactive)
        hh.setDefaultAlignment(Qt.AlignCenter | Qt.AlignVCenter)
        hh.setMinimumHeight(42)
        self.table.setColumnHidden(0, True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.table.setTextElideMode(Qt.ElideRight)
        self.table.setWordWrap(False)
        self.table.verticalHeader().setDefaultSectionSize(28)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.cellDoubleClicked.connect(lambda *_: self.on_edit_row())
        layout.addWidget(self.table)

        self.bottom_widget = QWidget()
        bottom_row = QHBoxLayout(self.bottom_widget)
        bottom_row.setContentsMargins(0, 0, 0, 0)
        self.total_label = QLabel("Total: 0.00")
        self.total_label.setObjectName("onBg")
        self.total_label.setStyleSheet("font-weight: bold;")
        bottom_row.addWidget(self.total_label)
        bottom_row.addStretch()

        add_btn = QPushButton("Add Row")
        add_btn.clicked.connect(self.on_add_row)
        bottom_row.addWidget(add_btn)

        edit_row_btn = QPushButton("Edit Row")
        edit_row_btn.setObjectName("secondary")
        edit_row_btn.clicked.connect(self.on_edit_row)
        bottom_row.addWidget(edit_row_btn)

        delete_btn = QPushButton("Delete Row")
        delete_btn.setObjectName("danger")
        delete_btn.clicked.connect(self.on_delete_row)
        bottom_row.addWidget(delete_btn)

        export_btn = QPushButton("Export Current View to Excel")
        export_btn.clicked.connect(self.on_export)
        bottom_row.addWidget(export_btn)

        self.export_plan_btn = QPushButton("Export Plan (.bpasx)…")
        self.export_plan_btn.clicked.connect(self.on_export_plan)
        bottom_row.addWidget(self.export_plan_btn)

        layout.addWidget(self.bottom_widget)

        self._loading = False

    def _autofit(self):
        self.table.resizeColumnsToContents()
        for i in range(self.table.columnCount()):
            self.table.setColumnWidth(i, max(60, min(self.table.columnWidth(i), 320)))

    def _current_filters(self):
        return {
            "search": self.search_input.text().strip() or None,
            "batch_id": db.get_active_batch(),
            "pap_name": self.pap_combo.currentData(),
            "gad_category": self.gad_combo.currentData(),
            "accounting_title": self.accounting_combo.currentData(),
            "mode_of_procurement": self.procurement_combo.currentData(),
        }

    def clear_filters(self):
        self.search_input.clear()
        for combo in [self.pap_combo, self.gad_combo,
                      self.accounting_combo, self.procurement_combo]:
            combo.setCurrentIndex(0)
        self.refresh()

    def _on_plan_changed(self, _idx):
        if self._loading:
            return
        bid = self.batch_combo.currentData()
        if bid is not None:
            db.set_active_batch(bid)
        self.refresh()
        self.changed.emit()

    def _reload_filter_options(self):
        self._loading = True

        def fill(combo, items, current):
            combo.blockSignals(True)
            combo.clear()
            combo.addItem(combo.property("placeholder") or "All", None)
            for item in items:
                combo.addItem(str(item), item)
            idx = combo.findData(current)
            combo.setCurrentIndex(idx if idx >= 0 else 0)
            combo.blockSignals(False)

        self.pap_combo.setProperty("placeholder", "All PAP Names")
        self.gad_combo.setProperty("placeholder", "All GAD Categories")
        self.accounting_combo.setProperty("placeholder", "All Accounting Titles")
        self.procurement_combo.setProperty("placeholder", "All Procurement Modes")

        active = db.get_active_batch()
        self.batch_combo.blockSignals(True)
        self.batch_combo.clear()
        for b in db.list_batches():
            plan = db.get_plan(b["id"])
            parts = []
            if plan["school_name"]:
                parts.append(plan["school_name"]
                             + (f" — {plan['level']}" if plan["level"] else ""))
            if b["label"]:
                parts.append(b["label"])
            self.batch_combo.addItem("  ·  ".join(parts) or b["file_name"], b["id"])
        idx = self.batch_combo.findData(active)
        self.batch_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.batch_combo.blockSignals(False)

        fill(self.pap_combo, db.distinct_values("pap_name", active), self.pap_combo.currentData())
        fill(self.gad_combo, db.distinct_values("gad_category", active), self.gad_combo.currentData())
        fill(self.accounting_combo, db.distinct_values("accounting_title", active), self.accounting_combo.currentData())
        fill(self.procurement_combo, db.distinct_values("mode_of_procurement", active), self.procurement_combo.currentData())

        self._loading = False

    def _edit_plan(self):
        bid = self.batch_combo.currentData()
        if bid is None:
            return
        from ui.plan_dialog import PlanDialog
        if PlanDialog(bid, self).exec() == PlanDialog.Accepted:
            self.refresh()
            self.changed.emit()

    def _delete_plan(self):
        bid = self.batch_combo.currentData()
        if bid is None:
            return
        name = self.batch_combo.currentText()
        if QMessageBox.question(
            self, "Delete Plan",
            f"Delete the plan '{name}' and all its records?\nThis cannot be undone.",
        ) != QMessageBox.Yes:
            return
        db.delete_batch(bid)
        self.refresh()
        self.changed.emit()

    def refresh(self):
        if self._loading:
            return

        has_data = bool(db.list_batches())
        self.empty_widget.setVisible(not has_data)
        for w in (self.plan_widget, self.filter_widget, self.table, self.bottom_widget):
            w.setVisible(has_data)
        if not has_data:
            self._current_rows = []
            return

        self._reload_filter_options()
        self._update_export_plan_btn()

        rows = db.query_items(self._current_filters())
        self.table.blockSignals(True)
        self.table.setRowCount(len(rows))
        total = 0.0
        for row_idx, item in enumerate(rows):
            for col_idx, field in enumerate(FIELDS):
                value = item[field]
                if value is None:
                    text = ""
                elif field in ("unit_price", "total_amount"):
                    text = f"{float(value):,.2f}"
                elif field == "qty":
                    v = float(value)
                    text = f"{v:,.0f}" if v == int(v) else f"{v:,.2f}"
                else:
                    text = str(value)
                cell = QTableWidgetItem(text)
                if text:
                    cell.setToolTip(text)
                if field in ("unit_price", "qty", "total_amount"):
                    cell.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(row_idx, col_idx, cell)
            total += item["total_amount"] or 0
        self.table.blockSignals(False)
        self._autofit()
        self.total_label.setText(f"Total: {total:,.2f}  ({len(rows)} row(s))")
        self._current_rows = rows

    _EXPORT_PLAN_TIP = (
        "Export the whole active plan (all items, signatories, PR/JR history) to a "
        "single file — for sharing with a division office for consolidation.")
    _EXPORT_PLAN_LOCKED_TIP = (
        "The plan must be balanced (Total and GAD allotment fully allocated — see the "
        "Dashboard) before it can be exported.")

    def _plan_balanced(self):
        return bool(db.checking_status(db.get_active_batch())["balanced"])

    def _update_export_plan_btn(self):
        ok = self._plan_balanced()
        self.export_plan_btn.setEnabled(ok)
        self.export_plan_btn.setToolTip(
            self._EXPORT_PLAN_TIP if ok else self._EXPORT_PLAN_LOCKED_TIP)

    def _selected_id(self):
        selected = self.table.selectedItems()
        if not selected:
            return None
        return int(self.table.item(selected[0].row(), 0).text())

    def on_add_row(self):
        batch_id = db.get_active_batch()
        if batch_id is None:
            return
        from ui.item_dialog import ItemDialog
        dlg = ItemDialog(batch_id, parent=self)
        if dlg.exec() == ItemDialog.Accepted:
            db.insert_items(batch_id, [dlg.values])
            self.refresh()
            self.changed.emit()

    def on_edit_row(self):
        item_id = self._selected_id()
        if item_id is None:
            QMessageBox.information(self, "No Selection", "Select a row to edit.")
            return
        record = next((r for r in self._current_rows if r["id"] == item_id), None)
        if record is None:
            return
        from ui.item_dialog import ItemDialog
        dlg = ItemDialog(db.get_active_batch(), row=record, parent=self)
        if dlg.exec() == ItemDialog.Accepted:
            db.update_item(item_id, dlg.values)
            self.refresh()
            self.changed.emit()

    def on_delete_row(self):
        selected = self.table.selectedItems()
        if not selected:
            QMessageBox.information(self, "No Selection", "Select a row to delete.")
            return
        row = selected[0].row()
        item_id = int(self.table.item(row, 0).text())
        confirm = QMessageBox.question(self, "Confirm Delete", f"Delete record #{item_id}?")
        if confirm != QMessageBox.Yes:
            return
        db.delete_item(item_id)
        self.refresh()
        self.changed.emit()

    def on_export(self):
        if not getattr(self, "_current_rows", None):
            QMessageBox.information(self, "Nothing to Export", "No rows in the current view.")
            return
        from ui.filepaths import in_downloads
        path, _ = QFileDialog.getSaveFileName(
            self, "Export to Excel", in_downloads("bpas_export.xlsx"),
            "Excel Files (*.xlsx)"
        )
        if not path:
            return
        try:
            export_excel.export_items(
                self._current_rows, path,
                signatories=db.list_signatories("ppmp"),
                school_info=db.get_school_info(),
            )
        except Exception as exc:
            QMessageBox.critical(self, "Export Failed", f"Could not export:\n{exc}")
            return
        QMessageBox.information(self, "Export Complete", f"Exported to:\n{path}")

    def on_export_plan(self):
        batch_id = db.get_active_batch()
        if batch_id is None:
            QMessageBox.information(self, "No Plan", "Import a plan first.")
            return
        if not self._plan_balanced():
            QMessageBox.information(self, "Plan Not Balanced", self._EXPORT_PLAN_LOCKED_TIP)
            return
        import export_plan
        from ui.filepaths import in_downloads
        plan = db.get_plan(batch_id)
        default_name = f"{(plan.get('school_name') or 'plan').replace(' ', '_')}.bpasx"
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Plan File", in_downloads(default_name),
            "BPAS Plan Files (*.bpasx)"
        )
        if not path:
            return
        try:
            export_plan.export_plan(batch_id, path)
        except Exception as exc:
            QMessageBox.critical(self, "Export Failed", f"Could not export plan:\n{exc}")
            return
        QMessageBox.information(self, "Export Complete", f"Plan exported to:\n{path}")
