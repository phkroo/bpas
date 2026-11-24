from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QPushButton, QFileDialog, QMessageBox,
)

import db
from ui import style
import sobp_pdf
from ui.empty_state import NoPlanWidget

COLS = ["Particular", "%", "Amount"] + sobp_pdf.MONTHS + ["Total"]


class SOBPScreen(QWidget):
    def __init__(self):
        super().__init__()
        self.batch_id = None
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(10)

        self.banner = style.make_banner()
        root.addWidget(self.banner)

        bar = QHBoxLayout()
        title = QLabel("School Operating Budget / Monthly Disbursement Program")
        title.setObjectName("pageTitle")
        title.setWordWrap(True)          # wraps instead of forcing a wide window
        bar.addWidget(title, 1)
        self.gen_btn = QPushButton("Generate SOB / MDP")
        self.gen_btn.clicked.connect(self._generate)
        bar.addWidget(self.gen_btn)
        self.bar_widget = QWidget()
        bar.setContentsMargins(0, 0, 0, 0)
        self.bar_widget.setLayout(bar)
        root.addWidget(self.bar_widget)

        self.table = QTableWidget(0, len(COLS))
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
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
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(28)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        root.addWidget(self.table, stretch=1)

        self.empty = NoPlanWidget()
        root.addWidget(self.empty, stretch=1)

    def refresh(self):
        self.batch_id = db.get_active_batch()
        has = self.batch_id is not None
        self.empty.setVisible(not has)
        self.bar_widget.setVisible(False)
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
        self.bar_widget.setVisible(balanced)
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

        def add(label, amount, monthly, pct=None, bold=False, header=False, spacer=False):
            ri = self.table.rowCount()
            self.table.insertRow(ri)
            if spacer:
                self.table.setSpan(ri, 0, 1, len(COLS))
                self.table.setRowHeight(ri, 10)
                return
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
            d["gad_row"]["monthly"], gad_pct, bold=True)
        add("", 0, [], spacer=True)
        add("Account Title / Description", 0, [], header=True)
        for r in d["rows"]:
            add(r["title"], r["amount"], r["monthly"], r["pct"])
        add("Total Allotment", d["total_row"]["amount"],
            d["total_row"]["monthly"], 100.0, bold=True)

        non_taxable = sum(r["amount"] for r in d["rows"]
                          if r["title"] in sobp_pdf.NON_TAXABLE_TITLES)
        taxable_base = total_allot - non_taxable
        add("5% Tax of the Taxable MOOE Budget",
            round(taxable_base * 0.05, 2), [], bold=True)

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
