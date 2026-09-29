from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QPushButton, QMessageBox,
)

import db
import app_pdf

COLS = ["Project Title / General Description", "Mode of Procurement", "Estimated Budget"]


class APPScreen(QWidget):
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

        self.count_label = QLabel()
        self.count_label.setObjectName("onBg")
        self.count_label.setStyleSheet("font-size: 13px;")
        root.addWidget(self.count_label)

        bar = QHBoxLayout()
        bar.addStretch()
        self.gen_btn = QPushButton("Generate APP PDF")
        self.gen_btn.clicked.connect(self._generate)
        bar.addWidget(self.gen_btn)
        root.addLayout(bar)

        self.table = QTableWidget(0, len(COLS))
        self.table.setHorizontalHeaderLabels(COLS)
        hh = self.table.horizontalHeader()
        hh.setDefaultAlignment(Qt.AlignCenter | Qt.AlignVCenter)
        hh.setMinimumHeight(30)
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        hh.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(24)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
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
            self.banner.setVisible(False)
            self.table.setVisible(False)
            self.count_label.setVisible(False)
            self.gen_btn.setEnabled(False)
            return

        status = db.checking_status(self.batch_id)
        self._set_banner(status)
        balanced = bool(status["balanced"])
        self.gen_btn.setEnabled(balanced)
        self.table.setVisible(balanced)
        self.count_label.setVisible(balanced)
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
            kind, msg = "bad", "APP is locked until the plan balances — see the Dashboard."
        self.banner.setVisible(True)
        self.banner.setStyleSheet(banner_qss(kind))
        self.banner.setText(msg)

    def _load_table(self):
        data = db.app_data(self.batch_id)
        self.table.setRowCount(0)
        n = 0
        for g in data["groups"]:
            ri = self.table.rowCount()
            self.table.insertRow(ri)
            head = QTableWidgetItem(g["title"])
            f = head.font(); f.setBold(True); head.setFont(f)
            self.table.setItem(ri, 0, head)
            self.table.setSpan(ri, 0, 1, len(COLS))
            for r in g["rows"]:
                n += 1
                ri = self.table.rowCount()
                self.table.insertRow(ri)
                amt = QTableWidgetItem(f"{r['amount']:,.2f}")
                amt.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                for c, it in enumerate((QTableWidgetItem(r["description"]),
                                        QTableWidgetItem(r["modes"]), amt)):
                    it.setToolTip(r["description"])
                    self.table.setItem(ri, c, it)
        self.count_label.setText(
            f"{n} project(s)  ·  Total ₱{data['total']:,.2f}")

    def _generate(self):
        if self.batch_id is None:
            return
        from ui.filepaths import dated_download_path, open_path
        from ui.toast import toast
        import os
        path = dated_download_path("Annual Procurement Plan")
        try:
            app_pdf.generate(self.batch_id, path)
        except Exception as exc:
            QMessageBox.critical(self, "PDF Failed", f"Could not generate PDF:\n{exc}")
            return
        open_path(path)
        toast(self, f"Saved to Downloads · {os.path.basename(path)}")
