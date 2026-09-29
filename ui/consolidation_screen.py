"""Consolidated, multi-school view — mirrors Records, but instead of switching
between individual plans, groups every imported plan by school level
(Elementary / Junior High / Senior High / ...). Defaults to all levels."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QLineEdit,
    QComboBox, QTableWidget, QTableWidgetItem, QFileDialog, QMessageBox,
    QHeaderView, QAbstractItemView,
)

import db
import export_excel
from ui.records_screen import FIELDS, HEADERS_WRAPPED

ALL_LEVELS = None   # sentinel combo-data value for "All School Levels"


class ConsolidationScreen(QWidget):
    changed = Signal()

    def __init__(self):
        super().__init__()
        self._loading = False
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # ---- empty state ----
        self.empty_widget = QWidget()
        empty_layout = QVBoxLayout(self.empty_widget)
        empty_layout.setAlignment(Qt.AlignCenter)
        empty_label = QLabel(
            "No plans imported yet.\n\nImport plans in Records (Excel or "
            "BPAS Plan Files) to see a consolidated view here."
        )
        empty_label.setAlignment(Qt.AlignCenter)
        empty_label.setObjectName("onBg")
        empty_label.setStyleSheet("font-size: 16px;")
        empty_layout.addWidget(empty_label)
        layout.addWidget(self.empty_widget)

        # ---- school level switcher ----
        self.level_widget = QWidget()
        level_row = QHBoxLayout(self.level_widget)
        level_row.setContentsMargins(0, 0, 0, 0)
        level_row.setSpacing(8)
        level_lbl = QLabel("School Level:")
        level_lbl.setObjectName("onBg")
        level_lbl.setStyleSheet("font-weight: bold;")
        level_row.addWidget(level_lbl)
        self.level_combo = QComboBox()
        self.level_combo.setMinimumWidth(280)
        self.level_combo.currentIndexChanged.connect(self._on_level_changed)
        level_row.addWidget(self.level_combo, 1)
        layout.addWidget(self.level_widget)

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
        layout.addWidget(self.table)

        self.bottom_widget = QWidget()
        bottom_row = QHBoxLayout(self.bottom_widget)
        bottom_row.setContentsMargins(0, 0, 0, 0)
        self.total_label = QLabel("Total: 0.00")
        self.total_label.setObjectName("onBg")
        self.total_label.setStyleSheet("font-weight: bold;")
        bottom_row.addWidget(self.total_label)
        bottom_row.addStretch()

        export_btn = QPushButton("Export Current View to Excel")
        export_btn.clicked.connect(self.on_export)
        bottom_row.addWidget(export_btn)

        layout.addWidget(self.bottom_widget)

        self._loading = False

    def _autofit(self):
        self.table.resizeColumnsToContents()
        for i in range(self.table.columnCount()):
            self.table.setColumnWidth(i, max(60, min(self.table.columnWidth(i), 320)))

    def _current_batch_ids(self):
        level = self.level_combo.currentData()
        if level is ALL_LEVELS:
            return None
        return [b["id"] for b in db.batches_for_level(level)]

    def _current_filters(self):
        return {
            "search": self.search_input.text().strip() or None,
            "batch_id": self._current_batch_ids(),
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

    def _on_level_changed(self, _idx):
        if self._loading:
            return
        self.refresh()

    def _reload_level_options(self):
        current = self.level_combo.currentData()
        self.level_combo.blockSignals(True)
        self.level_combo.clear()
        self.level_combo.addItem("All School Levels", ALL_LEVELS)
        for lvl in db.list_levels():
            n = len(db.batches_for_level(lvl))
            self.level_combo.addItem(f"{lvl} ({n} school{'s' if n != 1 else ''})", lvl)
        idx = self.level_combo.findData(current)
        self.level_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.level_combo.blockSignals(False)

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

        ids = self._current_batch_ids()
        fill(self.pap_combo, db.distinct_values("pap_name", ids), self.pap_combo.currentData())
        fill(self.gad_combo, db.distinct_values("gad_category", ids), self.gad_combo.currentData())
        fill(self.accounting_combo, db.distinct_values("accounting_title", ids), self.accounting_combo.currentData())
        fill(self.procurement_combo, db.distinct_values("mode_of_procurement", ids), self.procurement_combo.currentData())

        self._loading = False

    def refresh(self):
        if self._loading:
            return

        has_data = bool(db.list_batches())
        self.empty_widget.setVisible(not has_data)
        for w in (self.level_widget, self.filter_widget, self.table, self.bottom_widget):
            w.setVisible(has_data)
        if not has_data:
            self._current_rows = []
            return

        self._reload_level_options()
        self._reload_filter_options()

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

    def on_export(self):
        if not getattr(self, "_current_rows", None):
            QMessageBox.information(self, "Nothing to Export", "No rows in the current view.")
            return
        from ui.filepaths import in_downloads
        path, _ = QFileDialog.getSaveFileName(
            self, "Export to Excel", in_downloads("bpas_consolidated_export.xlsx"),
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
