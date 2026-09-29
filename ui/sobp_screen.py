from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QPushButton, QFileDialog, QMessageBox,
)

import db
import sobp_pdf

COLS = ["Particular", "%", "Amount"] + sobp_pdf.MONTHS + ["Total"]


class SOBPScreen(QWidget):
    def __init__(self):
        super().__init__()
        self.batch_id = None
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(10)

        self.banner = QLabel()
        self.banner.setWordWrap(True)
        self.banner.setStyleSheet(
            "font-size: 14px; font-weight: bold; padding: 8px 12px; border-radius: 6px;"
        )
        root.addWidget(self.banner)

        bar = QHBoxLayout()
        bar.addStretch()
        self.gen_btn = QPushButton("Generate SOB / MDP PDF")
        self.gen_btn.clicked.connect(self._generate)
        bar.addWidget(self.gen_btn)
        root.addLayout(bar)

        self.table = QTableWidget(0, len(COLS))
        self.table.setHorizontalHeaderLabels(COLS)
        hh = self.table.horizontalHeader()
        hh.setDefaultAlignment(Qt.AlignCenter | Qt.AlignVCenter)
        hh.setMinimumHeight(30)
        # every column shows its full content; horizontal scroll for the rest
        for c in range(len(COLS)):
            hh.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        self.table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.table.setTextElideMode(Qt.ElideRight)
        self.table.setWordWrap(False)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(24)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        root.addWidget(self.table, stretch=1)

        self.empty = QLabel("No plan loaded. Import a plan in Records first.")
        self.empty.setObjectName("onBg")
        self.empty.setAlignment(Qt.AlignCenter)
        root.addWidget(self.empty)

    def refresh(self):
        self.batch_id = db.get_active_batch()
        has = self.batch_id is not None
        self.empty.setVisible(not has)
        if not has:
            self.banner.setText("")
            self.banner.setVisible(False)
            self.table.setVisible(False)
            self.gen_btn.setEnabled(False)
            return

        status = db.checking_status(self.batch_id)
        self.banner.setVisible(True)
        self._set_banner(status)
        balanced = bool(status["balanced"])
        self.gen_btn.setEnabled(balanced)
        self.table.setVisible(balanced)

        if balanced:
            self._load_table()
        else:
            self.table.setRowCount(0)

    def _set_banner(self, status):
        from ui.status import banner_qss
        if not status["allotment_set"]:
            kind, msg = "warn", "Set Total & GAD Allotment in Setup first."
        elif not status["has_plan"]:
            kind, msg = "warn", "Import a plan first."
        elif status["balanced"]:
            self.banner.setVisible(False)
            return
        else:
            kind, msg = "bad", "SOB / MDP is locked until the plan balances — see the Dashboard."
        self.banner.setVisible(True)
        self.banner.setStyleSheet(banner_qss(kind))
        self.banner.setText(msg)

    def _load_table(self):
        d = db.sobp_data(self.batch_id)
        self.table.setRowCount(0)
        total_allot = d["total_allotment"]

        def add(label, amount, monthly, pct=None, bold=False, header=False):
            ri = self.table.rowCount()
            self.table.insertRow(ri)
            if header:
                it = QTableWidgetItem(label)
                f = it.font(); f.setBold(True); it.setFont(f)
                self.table.setItem(ri, 0, it)
                self.table.setSpan(ri, 0, 1, len(COLS))
                return
            vals = [label,
                    f"{pct:.2f}%" if pct is not None else "",
                    f"{amount:,.2f}" if amount else "-"]
            vals += [f"{x:,.2f}" if x else "-" for x in monthly]
            vals.append(f"{amount:,.2f}" if amount else "-")
            for c, text in enumerate(vals):
                it = QTableWidgetItem(text)
                it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                if c == 0:
                    it.setToolTip(label)
                if c >= 1:
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if bold:
                    f = it.font(); f.setBold(True); it.setFont(f)
                self.table.setItem(ri, c, it)

        add("Total Allotment", total_allot, d["total_row"]["monthly"], bold=True)
        gad_pct = (d["gad_allotment"] / total_allot * 100) if total_allot else 0.0
        add("Gender and Development (GAD)", d["gad_allotment"],
            d["gad_row"]["monthly"], gad_pct)
        add("Account Title / Description", 0, [], header=True)
        for r in d["rows"]:
            add(r["title"], r["amount"], r["monthly"], r["pct"])
        add("Total Allotment", d["total_row"]["amount"],
            d["total_row"]["monthly"], 100.0, bold=True)
        add("5% Tax of the Total Proposed MOOE Budget",
            round(total_allot * 0.05, 2), [], bold=True)

    def _generate(self):
        if self.batch_id is None:
            return
        from ui.filepaths import dated_download_path, open_path
        from ui.toast import toast
        import os
        path = dated_download_path("SOB-MDP")
        try:
            sobp_pdf.generate(self.batch_id, path)
        except Exception as exc:
            QMessageBox.critical(self, "PDF Failed", f"Could not generate PDF:\n{exc}")
            return
        open_path(path)
        toast(self, f"Saved to Downloads · {os.path.basename(path)}")
