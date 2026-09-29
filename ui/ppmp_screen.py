from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QBrush
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget, QTableWidgetItem,
    QHeaderView, QPushButton, QFileDialog, QMessageBox,
)

import db
import ppmp_pdf

MONTH_ABBR = [a for _, a in ppmp_pdf.MONTHS]
SHADE = QColor(13, 116, 144, 48)
COLS = ["Code", "General\nDescription", "Quantity /\nSize", "Estimated\nBudget",
        "Mode of\nProcurement"] + MONTH_ABBR


class PPMPScreen(QWidget):
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
        title = QLabel("Project Procurement Management Plan")
        title.setObjectName("onBg")
        title.setStyleSheet("font-size: 16px; font-weight: 700;")
        bar.addWidget(title)
        bar.addStretch()
        self.gen_btn = QPushButton("Generate PPMP PDF")
        self.gen_btn.clicked.connect(self._generate)
        bar.addWidget(self.gen_btn)
        root.addLayout(bar)

        self.table = QTableWidget(0, len(COLS))
        self.table.setHorizontalHeaderLabels(COLS)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        hh.setDefaultAlignment(Qt.AlignCenter | Qt.AlignVCenter)
        hh.setMinimumHeight(40)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(26)
        root.addWidget(self.table, stretch=1)

    # ---------- data ----------

    def refresh(self):
        self.batch_id = db.get_active_batch()

        status = db.checking_status(self.batch_id)
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
            kind, msg = "bad", "PPMP is locked until the plan balances — see the Dashboard."
        self.banner.setVisible(True)
        self.banner.setStyleSheet(banner_qss(kind))
        self.banner.setText(msg)

    def _load_table(self):
        self.table.setRowCount(0)
        if self.batch_id is None:
            return

        codes = db.list_account_codes()
        rows = db.ppmp_rows(self.batch_id)
        current_gd = object()
        total = 0.0
        for r in rows:
            gd = r["general_description"] or "(no general description)"
            if gd != current_gd:
                current_gd = gd
                ri = self.table.rowCount()
                self.table.insertRow(ri)
                hdr = QTableWidgetItem(gd)
                f = hdr.font(); f.setBold(True); hdr.setFont(f)
                hdr.setFlags(hdr.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(ri, 1, hdr)
                self.table.setSpan(ri, 1, 1, len(COLS) - 1)

            ri = self.table.rowCount()
            self.table.insertRow(ri)
            occurring = ppmp_pdf._months_set(r["months"])
            total += r["budget"] or 0
            code = codes.get(ppmp_pdf._single(r["titles"]), "")
            values = [
                code,
                r["item_description"] or "",
                ppmp_pdf._qty_size(r["qty"], r["units"]),
                ppmp_pdf._peso(r["budget"]),
                ppmp_pdf._modes(r["modes"]),
            ]
            for c, text in enumerate(values):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                if text:
                    item.setToolTip(text)
                if c == 3:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                elif c in (0, 2):
                    item.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
                self.table.setItem(ri, c, item)
            for mi, (key, _) in enumerate(ppmp_pdf.MONTHS):
                cell = QTableWidgetItem("")
                cell.setFlags(cell.flags() & ~Qt.ItemIsEditable)
                if key in occurring:
                    cell.setBackground(QBrush(SHADE))
                self.table.setItem(ri, 5 + mi, cell)

        ri = self.table.rowCount()
        self.table.insertRow(ri)
        ti = QTableWidgetItem("TOTAL")
        tf = ti.font(); tf.setBold(True); ti.setFont(tf)
        self.table.setItem(ri, 1, ti)
        amt = QTableWidgetItem(ppmp_pdf._peso(total))
        af = amt.font(); af.setBold(True); amt.setFont(af)
        amt.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.table.setItem(ri, 3, amt)

    # ---------- generate ----------

    def _generate(self):
        if self.batch_id is None:
            return
        from ui.filepaths import dated_download_path, open_path
        from ui.toast import toast
        import os
        path = dated_download_path("PPMP")
        try:
            ppmp_pdf.generate(self.batch_id, path)
        except Exception as exc:
            QMessageBox.critical(self, "PDF Failed", f"Could not generate PDF:\n{exc}")
            return
        open_path(path)
        toast(self, f"Saved to Downloads · {os.path.basename(path)}")
