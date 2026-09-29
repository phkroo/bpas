from PySide6.QtCore import Qt
from PySide6.QtGui import QDoubleValidator
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QCheckBox, QLineEdit,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QFileDialog, QMessageBox,
)

import appcse_convert
from appcse_convert import PROVISION_RATE

PREVIEW_COLS = ["General Description", "Item Description", "Unit", "Unit Price",
                "Qty", "Month", "Amount", "Part"]


class APPCSEScreen(QWidget):
    def __init__(self):
        super().__init__()
        self._raw = []
        self._skipped = 0
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(10)

        intro = QLabel(
            "Import a PS-DBM APP-CSE Excel. Its Part I / Part II items become BPAS rows "
            "(APP FORM = CSE). Download the result, add your Non-CSE items to balance the "
            "allotment, then import that file as a plan in Records.")
        intro.setObjectName("onBg")
        intro.setWordWrap(True)
        root.addWidget(intro)

        row = QHBoxLayout()
        self.import_btn = QPushButton("Import APP-CSE (PS-DBM)…")
        self.import_btn.clicked.connect(self._import)
        row.addWidget(self.import_btn)

        self.download_btn = QPushButton("Download as BPAS format")
        self.download_btn.setEnabled(False)
        self.download_btn.clicked.connect(self._download)
        row.addWidget(self.download_btn)
        row.addStretch()
        root.addLayout(row)

        prov_row = QHBoxLayout()
        prov_row.setSpacing(6)
        self.provision_cb = QCheckBox("Add provision for price changes (per item):")
        self.provision_cb.setObjectName("onBg")
        self.provision_cb.setChecked(True)
        self.provision_cb.toggled.connect(self._on_provision_toggle)
        prov_row.addWidget(self.provision_cb)

        self.rate_edit = QLineEdit(f"{PROVISION_RATE * 100:g}")
        self.rate_edit.setValidator(QDoubleValidator(0.0, 100.0, 2))
        self.rate_edit.setFixedWidth(56)
        self.rate_edit.setAlignment(Qt.AlignRight)
        self.rate_edit.textChanged.connect(self._render)
        prov_row.addWidget(self.rate_edit)
        pct = QLabel("%")
        pct.setObjectName("onBg")
        prov_row.addWidget(pct)
        prov_row.addStretch()
        root.addLayout(prov_row)

        self.status = QLabel("No APP-CSE imported yet.")
        self.status.setObjectName("onBg")
        self.status.setStyleSheet("font-weight: bold;")
        root.addWidget(self.status)

        self.table = QTableWidget(0, len(PREVIEW_COLS))
        self.table.setHorizontalHeaderLabels(PREVIEW_COLS)
        hh = self.table.horizontalHeader()
        for c in range(len(PREVIEW_COLS)):
            hh.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(24)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        root.addWidget(self.table, stretch=1)

    def refresh(self):
        pass

    # ---------- helpers ----------

    def _on_provision_toggle(self, on):
        self.rate_edit.setEnabled(on)
        self._render()

    def _rate_pct(self):
        try:
            return float(self.rate_edit.text().replace(",", "").strip() or 0)
        except ValueError:
            return 0.0

    def _rate(self):
        return self._rate_pct() / 100.0 if self.provision_cb.isChecked() else 0.0

    def _rows(self):
        if self._rate() > 0:
            return appcse_convert.apply_provision(self._raw, self._rate())
        return self._raw

    @staticmethod
    def _part_total(rows, part):
        return appcse_convert._money(
            appcse_convert._dsum(r["total_amount"] for r in rows
                                 if r["app_cs"] == part))

    # ---------- actions ----------

    def _import(self):
        from ui.filepaths import downloads_dir
        path, _ = QFileDialog.getOpenFileName(
            self, "Select PS-DBM APP-CSE Excel", downloads_dir(),
            "Excel Files (*.xlsx)")
        if not path:
            return
        try:
            rows, stats = appcse_convert.parse(path)
        except Exception as exc:
            QMessageBox.critical(self, "APP-CSE Import Failed",
                                 f"Could not read the file:\n{exc}")
            return
        self._raw = rows
        self._skipped = stats.get("skipped", 0)
        self.download_btn.setEnabled(bool(rows))
        self._render()

    def _render(self):
        rows = self._rows()
        p1 = self._part_total(rows, "PART I")
        p2 = self._part_total(rows, "PART II")
        note = f" (incl. {self._rate_pct():g}% provision)" if self._rate() else ""
        skip = f"   ·   {self._skipped} non-item row(s) skipped" if self._skipped else ""
        self.status.setText(
            f"{len(rows)} BPAS row(s){note}   ·   "
            f"Part I: ₱{p1:,.2f}   ·   Part II: ₱{p2:,.2f}   ·   "
            f"Overall: ₱{p1 + p2:,.2f}{skip}")
        self._load_table(rows)

    def _load_table(self, rows):
        self.table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            q = float(r["qty"])
            qty_txt = f"{q:,.0f}" if q == int(q) else f"{q:,.2f}"
            vals = [
                r["general_description"], r["item_description"], r["unit"],
                f"{r['unit_price']:,.2f}", qty_txt, r["month"],
                f"{r['total_amount']:,.2f}", r["app_cs"],
            ]
            for c, text in enumerate(vals):
                it = QTableWidgetItem(text)
                if c in (3, 4, 6):
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(i, c, it)

    def _download(self):
        if not self._raw:
            return
        rows = self._rows()
        from ui.filepaths import in_downloads
        path, _ = QFileDialog.getSaveFileName(
            self, "Save BPAS file", in_downloads("BPAS - APP-CSE start.xlsx"),
            "Excel Files (*.xlsx)")
        if not path:
            return
        try:
            appcse_convert.write_template(rows, path)
        except Exception as exc:
            QMessageBox.critical(self, "Save Failed", f"Could not write the file:\n{exc}")
            return
        QMessageBox.information(
            self, "Saved",
            f"Saved to:\n{path}\n\nAdd your Non-CSE items to balance the allotment, "
            "then import this file as a plan in Records.")
