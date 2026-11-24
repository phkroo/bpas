from PySide6.QtCore import Qt
from PySide6.QtGui import QDoubleValidator
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QCheckBox, QLineEdit,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QFileDialog, QMessageBox,
)

import db
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
            "Import a PS-DBM APP-CSE Excel. Its Part I / Part II items become B+ rows "
            "(APP FORM = CSE). Download the result, add your Non-CSE items to balance the "
            "allotment, then import that file as a plan in Records. No APP-CSE? Download a "
            "blank B+ Template instead.")
        intro.setObjectName("onBg")
        intro.setWordWrap(True)
        root.addWidget(intro)

        row = QHBoxLayout()
        self.import_btn = QPushButton("Import APP-CSE (PS-DBM)…")
        self.import_btn.clicked.connect(self._import)
        row.addWidget(self.import_btn)

        self.download_btn = QPushButton()
        self.download_btn.clicked.connect(self._download)
        row.addWidget(self.download_btn)

        row.addStretch()
        root.addLayout(row)

        prov_row = QHBoxLayout()
        prov_row.setSpacing(6)
        self.provision_cb = QCheckBox("Add provision for price changes (per item):")
        self.provision_cb.setObjectName("onBg")
        self.provision_cb.setChecked(db.get_setting("provision_enabled", "1") == "1")
        self.provision_cb.toggled.connect(self._on_provision_toggle)
        prov_row.addWidget(self.provision_cb)

        self.rate_edit = QLineEdit(
            db.get_setting("provision_pct", f"{PROVISION_RATE * 100:g}"))
        self.rate_edit.setEnabled(self.provision_cb.isChecked())
        self.rate_edit.setValidator(QDoubleValidator(0.0, 100.0, 2))
        self.rate_edit.setFixedWidth(56)
        self.rate_edit.setAlignment(Qt.AlignRight)
        self.rate_edit.textChanged.connect(self._save_provision)
        self.rate_edit.textChanged.connect(self._render)
        prov_row.addWidget(self.rate_edit)
        pct = QLabel("%")
        pct.setObjectName("onBg")
        prov_row.addWidget(pct)
        prov_row.addStretch()
        root.addLayout(prov_row)

        self.status = QLabel("No APP-CSE imported yet.")
        self.status.setObjectName("onBg")
        self.status.setObjectName("bold")
        status_row = QHBoxLayout()
        status_row.addWidget(self.status)
        status_row.addStretch()
        self.remove_btn = QPushButton("Remove Imported APP-CSE")
        self.remove_btn.setObjectName("danger")
        self.remove_btn.clicked.connect(self._remove_import)
        status_row.addWidget(self.remove_btn)
        root.addLayout(status_row)

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
        self._sync_buttons()

    def refresh(self):
        pass

    # ---------- helpers ----------

    def _save_provision(self, *_):
        """Records edit uses this same rate, so it is remembered between sessions."""
        db.set_setting("provision_enabled", "1" if self.provision_cb.isChecked() else "0")
        db.set_setting("provision_pct", f"{self._rate_pct():g}")

    def _on_provision_toggle(self, on):
        self.rate_edit.setEnabled(on)
        self._save_provision()
        self._render()

    def _sync_buttons(self):
        """Download is always available: blank template with no import, the imported
        rows once an APP-CSE is loaded. Remove only makes sense after an import."""
        imported = bool(self._raw)
        self.download_btn.setText("Download B+ Template (APP-CSE)" if imported
                                  else "Download B+ Template (Blank)")
        self.remove_btn.setEnabled(imported)

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
        self._sync_buttons()
        self._render()

    def _remove_import(self):
        if QMessageBox.question(
                self, "Remove Imported APP-CSE",
                "Remove the imported APP-CSE rows from this screen?\n\n"
                "Your original file and any template you already saved are not touched.",
        ) != QMessageBox.Yes:
            return
        self._raw = []
        self._skipped = 0
        self.table.setRowCount(0)
        self.status.setText("No APP-CSE imported yet.")
        self._sync_buttons()

    def _render(self):
        rows = self._rows()
        p1 = self._part_total(rows, "PART I")
        p2 = self._part_total(rows, "PART II")
        note = f" (incl. {self._rate_pct():g}% provision)" if self._rate() else ""
        skip = f"   ·   {self._skipped} non-item row(s) skipped" if self._skipped else ""
        self.status.setText(
            f"{len(rows)} B+ row(s){note}   ·   "
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
        blank = not self._raw
        rows = [] if blank else self._rows()
        from ui.filepaths import in_downloads
        path, _ = QFileDialog.getSaveFileName(
            self, "Save B+ Template",
            in_downloads("B+ Template (blank).xlsx" if blank else "B+ Template.xlsx"),
            "Excel Files (*.xlsx)")
        if not path:
            return
        try:
            appcse_convert.write_template(rows, path, self._rate())
        except Exception as exc:
            QMessageBox.critical(self, "Save Failed", f"Could not write the file:\n{exc}")
            return
        QMessageBox.information(
            self, "Saved",
            f"Saved to:\n{path}\n\n"
            + ("Fill in your items" if blank else "Add your Non-CSE items to balance the allotment")
            + ", then import this file as a plan in Records.")
