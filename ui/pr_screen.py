from PySide6.QtCore import Qt

from ui import style
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget, QTableWidgetItem,
    QHeaderView, QPushButton, QFileDialog, QMessageBox, QDialog, QComboBox,
    QDialogButtonBox, QAbstractItemView, QCheckBox, QFormLayout, QLineEdit,
)

import db
import pr_pdf
import cashadv_pdf

COLS = ["PR No.", "Items", "Total", "Purpose"]

BUILD_COLS = ["Include", "Item Description", "Qty", "Unit", "Unit Price", "Amount"]
INC_COL, DESC_COL, QTY_COL, UNIT_COL, PRICE_COL, AMT_COL = range(6)


def _join_purposes(descs):
    seen = []
    for d in descs:
        d = (d or "").strip()
        if d and d not in seen:
            seen.append(d)
    return " / ".join(seen)


def _qty_txt(v):
    v = float(v or 0)
    return f"{v:,.0f}" if v == int(v) else f"{v:,.2f}"


class PRBuilderDialog(QDialog):
    def __init__(self, batch_id, parent=None):
        super().__init__(parent)
        self.batch_id = batch_id
        self._fitted = False
        self.setWindowTitle("New PR/JR")
        self.resize(940, 620)

        root = QVBoxLayout(self)

        top = QHBoxLayout()
        top.addWidget(QLabel("Month:"))
        self.month_combo = QComboBox()
        self.month_combo.addItems(db.pr_months(batch_id))
        self.month_combo.currentTextChanged.connect(self._load_items)
        top.addWidget(self.month_combo)
        top.addStretch()
        self.total_lbl = QLabel("PR total: ₱0.00")
        self.total_lbl.setStyleSheet("font-weight: bold;")
        top.addWidget(self.total_lbl)
        root.addLayout(top)

        hint = QLabel("Tick <b>Include</b> to add an item. Each item is requisitioned "
                      "at its full remaining quantity. R & M items are issued as a Job "
                      "Request (JR) and can't be combined with regular PR items.")
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {style.current_palette()['muted']};")
        root.addWidget(hint)

        self.table = QTableWidget(0, len(BUILD_COLS))
        self.table.setHorizontalHeaderLabels(BUILD_COLS)
        hh = self.table.horizontalHeader()
        for c in range(len(BUILD_COLS)):
            hh.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(DESC_COL, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        root.addWidget(self.table, stretch=1)

        prow = QHBoxLayout()
        prow.addWidget(QLabel("Purpose:"))
        self.purpose_combo = QComboBox()
        self.purpose_combo.setEditable(True)
        self.purpose_combo.addItem("")
        self.purpose_combo.addItems(db.pr_purposes(batch_id))
        self.purpose_combo.setCurrentText("")
        self._purpose_dirty = False
        self._setting_purpose = False
        self.purpose_combo.editTextChanged.connect(self._on_purpose_edited)
        prow.addWidget(self.purpose_combo, stretch=1)
        root.addLayout(prow)

        extra = QFormLayout()
        extra.setSpacing(6)
        self.delivery_edit = QLineEdit()
        self.delivery_edit.setPlaceholderText("e.g. 5 calendar days")
        self.fund_source_edit = QLineEdit()
        self.fund_source_edit.setPlaceholderText("e.g. MOOE")
        self.stock_no_edit = QLineEdit()
        self.stock_no_edit.setPlaceholderText("optional")
        extra.addRow("Delivery Period:", self.delivery_edit)
        extra.addRow("Fund Source:", self.fund_source_edit)
        extra.addRow("Stock No.:", self.stock_no_edit)
        root.addLayout(extra)

        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._save)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

        self._load_items()

    def _load_items(self):
        self._purpose_dirty = False
        month = self.month_combo.currentText()
        self._rows = db.pr_buildable_items(self.batch_id, month) if month else []
        self._checks = []
        self.table.setRowCount(len(self._rows))
        for i, r in enumerate(self._rows):
            box = QCheckBox()
            box.stateChanged.connect(self._recalc)
            holder = QWidget()
            hl = QHBoxLayout(holder)
            hl.setContentsMargins(0, 0, 0, 0)
            hl.setAlignment(Qt.AlignCenter)
            hl.addWidget(box)
            self.table.setCellWidget(i, INC_COL, holder)
            self._checks.append(box)

            amt = round(r["remaining_qty"] * (r["unit_price"] or 0), 2)
            for c, text in (
                (DESC_COL, r["item_description"] or ""),
                (QTY_COL, _qty_txt(r["remaining_qty"])),
                (UNIT_COL, r["unit"] or ""),
                (PRICE_COL, f"{r['unit_price']:,.2f}"),
                (AMT_COL, f"{amt:,.2f}"),
            ):
                it = QTableWidgetItem(text)
                it.setFlags(Qt.ItemIsEnabled)
                if c in (QTY_COL, PRICE_COL, AMT_COL):
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(i, c, it)
        self._recalc()

    def _on_purpose_edited(self, _text):
        if not self._setting_purpose:
            self._purpose_dirty = True

    def _row_qty(self, i, r):
        return r["remaining_qty"] if self._checks[i].isChecked() else 0.0

    def _auto_purpose(self):
        if self._purpose_dirty:
            return
        descs = [r["general_description"] for i, r in enumerate(self._rows)
                 if self._row_qty(i, r) > 0]
        self._setting_purpose = True
        self.purpose_combo.setCurrentText(_join_purposes(descs))
        self._setting_purpose = False

    def _recalc(self, *_):
        total = sum(round(self._row_qty(i, r) * (r["unit_price"] or 0), 2)
                    for i, r in enumerate(self._rows))
        self.total_lbl.setText(f"PR total: ₱{total:,.2f}")
        self._auto_purpose()

    def _save(self):
        month = self.month_combo.currentText()
        if not month:
            QMessageBox.warning(self, "No month", "Pick a month.")
            return
        lines = []
        included_rows = []
        for i, r in enumerate(self._rows):
            qty = self._row_qty(i, r)
            if qty <= 0:
                continue
            lines.append({"bpas_item_id": r["bpas_item_id"], "qty": qty})
            included_rows.append(r)
        if not lines:
            QMessageBox.warning(self, "Nothing to save",
                                "Tick at least one item to include.")
            return
        kinds = {db.is_jr_title(r["accounting_title"]) for r in included_rows}
        if len(kinds) > 1:
            QMessageBox.warning(
                self, "Can't combine PR and JR",
                "You've ticked both regular items (Purchase Request) and R & M "
                "items (Job Request). These can't be saved together — untick "
                "one group and save it as its own PR/JR.")
            return
        db.create_pr(self.batch_id, month, self.purpose_combo.currentText(), lines,
                    delivery_period=self.delivery_edit.text(),
                    fund_source=self.fund_source_edit.text(),
                    stock_no=self.stock_no_edit.text())
        self.accept()

    def showEvent(self, event):
        super().showEvent(event)
        if self._fitted:
            return
        self._fitted = True
        from ui.dialog_utils import fit_to_host
        fit_to_host(self)


class PREditDialog(QDialog):
    """Add more items to an already-saved PR — same month only, existing
    lines shown read-only."""

    def __init__(self, batch_id, pr_header_id, parent=None):
        super().__init__(parent)
        self.batch_id = batch_id
        self.pr_header_id = pr_header_id
        self._fitted = False
        header = db.get_pr_header(pr_header_id)
        self.month = header["month"]

        self.setWindowTitle(f"Edit PR/JR {header['pr_no']} — {self.month.title()}")
        self.resize(960, 680)

        root = QVBoxLayout(self)

        root.addWidget(QLabel(f"<b>Already in this PR</b> — {self.month.title()} only"))
        self.existing_table = QTableWidget(0, 4)
        self.existing_table.setHorizontalHeaderLabels(
            ["Item Description", "Qty", "Unit Price", "Amount"])
        hh = self.existing_table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        for c in (1, 2, 3):
            hh.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        self.existing_table.verticalHeader().setVisible(False)
        self.existing_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.existing_table.setSelectionMode(QAbstractItemView.NoSelection)
        self.existing_table.setMaximumHeight(160)
        root.addWidget(self.existing_table)

        top = QHBoxLayout()
        top.addWidget(QLabel(f"<b>Add more items</b> ({self.month.title()} only):"))
        top.addStretch()
        self.total_lbl = QLabel("Adding: ₱0.00")
        self.total_lbl.setStyleSheet("font-weight: bold;")
        top.addWidget(self.total_lbl)
        root.addLayout(top)

        self.table = QTableWidget(0, len(BUILD_COLS))
        self.table.setHorizontalHeaderLabels(BUILD_COLS)
        hh2 = self.table.horizontalHeader()
        for c in range(len(BUILD_COLS)):
            hh2.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        hh2.setSectionResizeMode(DESC_COL, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        root.addWidget(self.table, stretch=1)

        prow = QHBoxLayout()
        prow.addWidget(QLabel("Purpose:"))
        self.purpose_edit = QComboBox()
        self.purpose_edit.setEditable(True)
        self.purpose_edit.addItem("")
        self.purpose_edit.addItems(db.pr_purposes(batch_id))
        self.purpose_edit.setCurrentText(header["purpose"] or "")
        prow.addWidget(self.purpose_edit, stretch=1)
        root.addLayout(prow)

        extra = QFormLayout()
        extra.setSpacing(6)
        self.delivery_edit = QLineEdit(header["delivery_period"] or "")
        self.delivery_edit.setPlaceholderText("e.g. 5 calendar days")
        self.fund_source_edit = QLineEdit(header["fund_source"] or "")
        self.fund_source_edit.setPlaceholderText("e.g. MOOE")
        self.stock_no_edit = QLineEdit(header["stock_no"] or "")
        self.stock_no_edit.setPlaceholderText("optional")
        extra.addRow("Delivery Period:", self.delivery_edit)
        extra.addRow("Fund Source:", self.fund_source_edit)
        extra.addRow("Stock No.:", self.stock_no_edit)
        root.addLayout(extra)

        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._save)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

        self._load_existing()
        self._load_items()

    def _load_existing(self):
        lines = db.pr_lines_for(self.pr_header_id)
        self.existing_table.setRowCount(len(lines))
        for i, ln in enumerate(lines):
            vals = [ln["item_description"] or "", _qty_txt(ln["qty"]),
                    f"{ln['unit_price']:,.2f}", f"{ln['amount']:,.2f}"]
            for c, text in enumerate(vals):
                it = QTableWidgetItem(text)
                it.setFlags(Qt.ItemIsEnabled)
                if c in (1, 2, 3):
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.existing_table.setItem(i, c, it)

    def _load_items(self):
        self._rows = db.pr_buildable_items(self.batch_id, self.month)
        self._checks = []
        self.table.setRowCount(len(self._rows))
        for i, r in enumerate(self._rows):
            box = QCheckBox()
            box.stateChanged.connect(self._recalc)
            holder = QWidget()
            hl = QHBoxLayout(holder)
            hl.setContentsMargins(0, 0, 0, 0)
            hl.setAlignment(Qt.AlignCenter)
            hl.addWidget(box)
            self.table.setCellWidget(i, INC_COL, holder)
            self._checks.append(box)

            amt = round(r["remaining_qty"] * (r["unit_price"] or 0), 2)
            for c, text in (
                (DESC_COL, r["item_description"] or ""),
                (QTY_COL, _qty_txt(r["remaining_qty"])),
                (UNIT_COL, r["unit"] or ""),
                (PRICE_COL, f"{r['unit_price']:,.2f}"),
                (AMT_COL, f"{amt:,.2f}"),
            ):
                it = QTableWidgetItem(text)
                it.setFlags(Qt.ItemIsEnabled)
                if c in (QTY_COL, PRICE_COL, AMT_COL):
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(i, c, it)
        self._recalc()

    def _row_qty(self, i, r):
        return r["remaining_qty"] if self._checks[i].isChecked() else 0.0

    def _recalc(self, *_):
        total = sum(round(self._row_qty(i, r) * (r["unit_price"] or 0), 2)
                    for i, r in enumerate(self._rows))
        self.total_lbl.setText(f"Adding: ₱{total:,.2f}")

    def _save(self):
        lines = []
        included_rows = []
        for i, r in enumerate(self._rows):
            qty = self._row_qty(i, r)
            if qty <= 0:
                continue
            lines.append({"bpas_item_id": r["bpas_item_id"], "qty": qty})
            included_rows.append(r)
        current = db.get_pr_header(self.pr_header_id)
        unchanged = (
            not lines
            and self.purpose_edit.currentText() == (current["purpose"] or "")
            and self.delivery_edit.text() == (current["delivery_period"] or "")
            and self.fund_source_edit.text() == (current["fund_source"] or "")
            and self.stock_no_edit.text() == (current["stock_no"] or "")
        )
        if unchanged:
            QMessageBox.information(self, "Nothing changed",
                                    "Tick at least one item to add, or edit a field.")
            return
        if included_rows:
            existing = db.pr_lines_for(self.pr_header_id)
            existing_kinds = {db.is_jr_title(ln["accounting_title"]) for ln in existing}
            new_kinds = {db.is_jr_title(r["accounting_title"]) for r in included_rows}
            if len(existing_kinds | new_kinds) > 1:
                QMessageBox.warning(
                    self, "Can't combine PR and JR",
                    "This PR/JR already contains items of one type. The item(s) "
                    "you ticked belong to the other type (regular vs. R & M / "
                    "Job Request) and can't be added here — save them as a "
                    "separate PR/JR instead.")
                return
        if lines:
            db.add_pr_lines(self.pr_header_id, self.batch_id, lines)
        db.update_pr_purpose(self.pr_header_id, self.purpose_edit.currentText())
        db.update_pr_extra(self.pr_header_id, delivery_period=self.delivery_edit.text(),
                           fund_source=self.fund_source_edit.text(),
                           stock_no=self.stock_no_edit.text())
        self.accept()

    def showEvent(self, event):
        super().showEvent(event)
        if self._fitted:
            return
        self._fitted = True
        from ui.dialog_utils import fit_to_host
        fit_to_host(self)


class PRScreen(QWidget):
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
        self.new_btn = QPushButton("New PR/JR…")
        self.new_btn.clicked.connect(self._new_pr)
        bar.addWidget(self.new_btn)
        self.edit_btn = QPushButton("Edit PR/JR")
        self.edit_btn.setObjectName("secondary")
        self.edit_btn.clicked.connect(self._edit_pr)
        bar.addWidget(self.edit_btn)
        self.del_btn = QPushButton("Delete PR/JR")
        self.del_btn.clicked.connect(self._delete_pr)
        bar.addWidget(self.del_btn)
        bar.addStretch()
        self.gen_btn = QPushButton("Generate PR/JR")
        self.gen_btn.clicked.connect(self._generate)
        bar.addWidget(self.gen_btn)
        self.rsq_btn = QPushButton("Generate RSQ")
        self.rsq_btn.clicked.connect(self._generate_rsq)
        bar.addWidget(self.rsq_btn)
        root.addLayout(bar)

        self.table = QTableWidget(0, len(COLS))
        self.table.setHorizontalHeaderLabels(COLS)
        hh = self.table.horizontalHeader()
        for _c in range(len(COLS)):
            hh.setSectionResizeMode(_c, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(3, QHeaderView.Stretch)
        hh.setDefaultAlignment(Qt.AlignCenter | Qt.AlignVCenter)
        hh.setMinimumHeight(34)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(26)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.cellDoubleClicked.connect(self._on_row_double_clicked)
        root.addWidget(self.table, stretch=1)

    def refresh(self):
        self.batch_id = db.get_active_batch()

        status = db.checking_status(self.batch_id)
        self._set_banner(status)
        balanced = bool(status["balanced"])

        self.new_btn.setEnabled(balanced)
        self.table.setVisible(balanced)
        self.count_label.setVisible(balanced)
        if balanced:
            self._load_table()
        else:
            self.table.setRowCount(0)
            self.count_label.clear()
            self.edit_btn.setEnabled(False)
            self.del_btn.setEnabled(False)
            self.gen_btn.setEnabled(False)
            self.rsq_btn.setEnabled(False)

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
            kind, msg = "bad", "PR/JR / RSQ is locked until the plan balances — see the Dashboard."
        self.banner.setVisible(True)
        self.banner.setStyleSheet(banner_qss(kind))
        self.banner.setText(msg)

    def _load_table(self):
        self.table.setRowCount(0)
        if self.batch_id is None:
            return
        prs = db.pr_list(self.batch_id)
        grand = 0.0
        last_month = None
        for g in prs:
            month = g["month"] or ""
            if month != last_month:
                self._insert_month_header(month)
                last_month = month

            ri = self.table.rowCount()
            self.table.insertRow(ri)
            grand += g["total"] or 0
            values = [
                g["pr_no"],
                str(g["items"]),
                f"{g['total']:,.2f}",
                g["purpose"] or "",
            ]
            for c, text in enumerate(values):
                item = QTableWidgetItem(text)
                item.setData(Qt.UserRole, g["id"])
                if text:
                    item.setToolTip(text)
                if c in (1, 2):
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                elif c == 0:
                    item.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
                self.table.setItem(ri, c, item)

        have = bool(prs)
        self.edit_btn.setEnabled(have)
        self.del_btn.setEnabled(have)
        self.gen_btn.setEnabled(have)
        self.rsq_btn.setEnabled(have)
        self.count_label.setText(f"{len(prs)} PR(s)  ·  Total ₱{grand:,.2f}")

    def _insert_month_header(self, month):
        ri = self.table.rowCount()
        self.table.insertRow(ri)
        self.table.setSpan(ri, 0, 1, len(COLS))

        p = style.current_palette()
        row = QWidget()
        row.setObjectName("monthHeaderRow")
        row.setStyleSheet(f"#monthHeaderRow {{ background: {p['header_bg']}; }}")
        lay = QHBoxLayout(row)
        lay.setContentsMargins(8, 4, 8, 4)
        label = QLabel(f"<b>{(month or '(no month)').title()}</b>")
        label.setStyleSheet(f"color: {p['header_text']}; background: transparent;")
        lay.addWidget(label)
        lay.addStretch()
        rca_btn = QPushButton("Generate RCA")
        rca_btn.clicked.connect(lambda _=False, m=month: self._generate_rca(m))
        lay.addWidget(rca_btn)
        self.table.setCellWidget(ri, 0, row)
        self.table.setRowHeight(ri, 50)

    def _selected_pr_id(self):
        row = self.table.currentRow()
        if row < 0:
            return None
        it = self.table.item(row, 0)
        return it.data(Qt.UserRole) if it else None

    def _new_pr(self):
        if self.batch_id is None:
            return
        if not db.pr_months(self.batch_id):
            QMessageBox.information(self, "No months",
                                   "This plan has no line items with a month set.")
            return
        dlg = PRBuilderDialog(self.batch_id, self)
        if dlg.exec() == QDialog.Accepted:
            self._load_table()

    def _edit_pr(self):
        pr_id = self._selected_pr_id()
        if pr_id is None:
            QMessageBox.information(self, "Select a PR/JR", "Pick a PR/JR row to edit.")
            return
        dlg = PREditDialog(self.batch_id, pr_id, self)
        if dlg.exec() == QDialog.Accepted:
            self._load_table()

    def _on_row_double_clicked(self, row, _col):
        it = self.table.item(row, 0)
        pr_id = it.data(Qt.UserRole) if it else None
        if pr_id is None:
            return
        dlg = PREditDialog(self.batch_id, pr_id, self)
        if dlg.exec() == QDialog.Accepted:
            self._load_table()

    def _delete_pr(self):
        pr_id = self._selected_pr_id()
        if pr_id is None:
            QMessageBox.information(self, "Select a PR/JR", "Pick a PR/JR row to delete.")
            return
        if QMessageBox.question(
                self, "Delete PR/JR",
                "Delete this Purchase Request / Job Request? Its quantities return to the pool.") \
                != QMessageBox.Yes:
            return
        db.delete_pr(pr_id)
        self._load_table()

    def _pr_ids_choice(self, verb):
        sel = self._selected_pr_id()
        if sel is not None and QMessageBox.question(
                self, "Which PR/JRs?",
                f"{verb} only the selected PR/JR?  (No = all)") == QMessageBox.Yes:
            return [sel]
        return None

    def _emit_pdf(self, stem, fn):
        from ui.filepaths import dated_download_path, open_path
        from ui.toast import toast
        import os
        path = dated_download_path(stem)
        try:
            fn(path)
        except Exception as exc:
            QMessageBox.critical(self, "PDF Failed", f"Could not generate PDF:\n{exc}")
            return
        open_path(path)
        toast(self, f"Saved to Downloads · {os.path.basename(path)}")

    def _generate(self):
        if self.batch_id is None:
            return
        pr_ids = self._pr_ids_choice("Export PR/JR PDF for")
        self._emit_pdf("Purchase Requests",
                       lambda p: pr_pdf.generate(self.batch_id, p, pr_ids))

    def _generate_rsq(self):
        if self.batch_id is None:
            return
        import rsq_pdf
        pr_ids = self._pr_ids_choice("Export RSQ for")
        self._emit_pdf("Request for Sealed Quotation",
                       lambda p: rsq_pdf.generate(self.batch_id, p, pr_ids))

    def _generate_rca(self, month):
        if self.batch_id is None:
            return
        self._emit_pdf(f"Request for Cash Advance - {(month or '').title()}",
                       lambda p: cashadv_pdf.generate(self.batch_id, p, month, ""))
