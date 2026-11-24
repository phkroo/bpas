from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QBrush
from PySide6.QtWidgets import (
    QAbstractItemView,
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget, QTableWidgetItem,
    QHeaderView, QPushButton, QFileDialog, QMessageBox,
)

import db
from ui import style
import ppmp_pdf
from ui.empty_state import NoPlanWidget

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

        self.banner = style.make_banner()
        root.addWidget(self.banner)

        bar = QHBoxLayout()
        title = QLabel("Project Procurement Management Plan")
        title.setObjectName("pageTitle")
        bar.addWidget(title)
        bar.addStretch()
        self.gen_btn = QPushButton("Generate PPMP")
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
        # text columns get the room; the 12 month columns are narrow shade cells
        hh.setSectionResizeMode(QHeaderView.Fixed)
        hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.Fixed)       # sized in _fit_description (min 170 px)
        hh.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(4, QHeaderView.Fixed)       # long modes are cut (hover shows all)
        self.table.setColumnWidth(4, 180)                    # so the description keeps its room
        for c in range(5, len(COLS)):
            self.table.setColumnWidth(c, 42)
        self.table.setShowGrid(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(False)
        hh.setDefaultAlignment(Qt.AlignCenter | Qt.AlignVCenter)
        hh.setMinimumHeight(40)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(28)
        root.addWidget(self.table, stretch=1)

        self.empty = NoPlanWidget()
        root.addWidget(self.empty, stretch=1)

    # ---------- data ----------

    def refresh(self):
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, self._fit_description)      # after the rows are in
        self.batch_id = db.get_active_batch()
        has = self.batch_id is not None
        self.empty.setVisible(not has)
        self.bar_widget.setVisible(False)
        if not has:
            self.banner.setVisible(False)
            self.table.setVisible(False)
            self.gen_btn.setEnabled(False)
            return

        status = db.checking_status(self.batch_id)
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
                tint = QColor(style.current_palette()["header_bg"])
                hdr.setBackground(QBrush(tint))
                blank = QTableWidgetItem("")
                blank.setFlags(Qt.NoItemFlags)
                blank.setBackground(QBrush(tint))
                self.table.setItem(ri, 0, blank)

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
        from ui.signatory_check import confirm_signatories
        if not confirm_signatories(self, "ppmp", self.batch_id, "PPMP"):
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

    def _fit_description(self):
        """Description takes the room left over, but never less than 170 px: in a narrow
        window (half screen) the table scrolls sideways instead of squeezing it."""
        t = self.table
        others = sum(t.columnWidth(c) for c in range(t.columnCount()) if c != 1 and not t.isColumnHidden(c))
        t.setColumnWidth(1, max(170, t.width() - 2 * t.frameWidth() - t.verticalScrollBar().sizeHint().width() - others))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, self._fit_description)      # after the table has its new size
