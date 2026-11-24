from PySide6.QtCore import Qt, QPoint

from ui import style
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget, QTableWidgetItem,
    QHeaderView, QPushButton, QFileDialog, QMessageBox, QDialog, QComboBox,
    QDialogButtonBox, QAbstractItemView, QCheckBox, QFormLayout, QLineEdit, QMenu,
)

import db
import pr_pdf
from ui.empty_state import NoPlanWidget
import cashadv_pdf

COLS = ["PR/JR No.", "Items", "Total", "Purpose"]

BUILD_COLS = ["Include", "Item Description", "Project Title", "Qty", "Unit", "Unit Price", "Amount"]
INC_COL, DESC_COL, PURP_COL, QTY_COL, UNIT_COL, PRICE_COL, AMT_COL = range(7)


LABEL_W = 112   # shared label column so the boxes of stacked rows line up


def _field_row(label, edit, label_w=LABEL_W):
    """Label beside its input: [label][input]."""
    row = QHBoxLayout()
    row.setSpacing(8)
    lbl = QLabel(label)
    if label_w:
        lbl.setFixedWidth(label_w)
    row.addWidget(lbl)
    row.addWidget(edit, stretch=1)
    return row


def _delivery_fund_row(delivery_edit, fund_edit):
    """Delivery Period and Fund Source side by side, each label beside its box."""
    row = QHBoxLayout()
    row.setSpacing(16)
    row.addLayout(_field_row("Delivery Period:", delivery_edit), stretch=1)
    row.addLayout(_field_row("Fund Source:", fund_edit, None), stretch=1)
    return row


def _fund_source_combo(current=""):
    """Dropdown of the fund sources set up in Setup > Fund Sources. A saved value that
    is no longer on the list is kept so an old PR/JR doesn't silently change."""
    box = QComboBox()
    names = db.list_fund_sources()
    box.addItems(names)
    current = (current or "").strip()
    if current and current not in names:
        box.addItem(current)
    box.setCurrentText(current or (names[0] if names else ""))
    return box


PR_KINDS = (("Purchase Request", "PR"), ("Job Request", "JR"))


def _kind_combo(kind="PR"):
    box = QComboBox()
    for label, code in PR_KINDS:
        box.addItem(label, code)
    box.setCurrentIndex(1 if kind == "JR" else 0)
    return box


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
        top.addSpacing(16)
        top.addWidget(QLabel("Type:"))
        self.kind_combo = _kind_combo()
        top.addWidget(self.kind_combo)
        top.addStretch()
        self.total_lbl = QLabel("PR total: ₱0.00")
        self.total_lbl.setObjectName("bold")
        top.addWidget(self.total_lbl)
        root.addLayout(top)

        hint = QLabel("Tick <b>Include</b> to add an item. Each item is requisitioned "
                      "at its full remaining quantity. Choose the <b>Type</b> "
                      "(Purchase Request or Job Request) for the request.")
        hint.setWordWrap(True)
        hint.setObjectName("muted")
        root.addWidget(hint)

        self.table = QTableWidget(0, len(BUILD_COLS))
        self.table.setHorizontalHeaderLabels(BUILD_COLS)
        hh = self.table.horizontalHeader()
        for c in range(len(BUILD_COLS)):
            hh.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(DESC_COL, QHeaderView.Stretch)
        hh.setSectionResizeMode(PURP_COL, QHeaderView.Interactive)
        self.table.setColumnWidth(PURP_COL, 340)
        self.table.setTextElideMode(Qt.ElideRight)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        root.addWidget(self.table, stretch=1)

        self.purpose_combo = QLineEdit()
        self.purpose_combo.setPlaceholderText("Required")
        root.addLayout(_field_row("Purpose:", self.purpose_combo))

        self.delivery_edit = QLineEdit()
        self.delivery_edit.setPlaceholderText("e.g. 5 calendar days")
        self.fund_source_edit = _fund_source_combo()
        root.addLayout(_delivery_fund_row(self.delivery_edit, self.fund_source_edit))

        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._save)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

        self._load_items()

    def _load_items(self):
        month = self.month_combo.currentText()
        self._rows = db.pr_buildable_items(self.batch_id, month) if month else []
        self._checks = []
        self.table.setRowCount(len(self._rows))
        for i, r in enumerate(self._rows):
            box = QCheckBox()
            box.toggled.connect(self._recalc)
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
                (PURP_COL, r["project_title"] or ""),
                (QTY_COL, _qty_txt(r["remaining_qty"])),
                (UNIT_COL, r["unit"] or ""),
                (PRICE_COL, f"{r['unit_price']:,.2f}"),
                (AMT_COL, f"{amt:,.2f}"),
            ):
                it = QTableWidgetItem(text)
                it.setFlags(Qt.ItemIsEnabled)
                it.setToolTip(text)
                if c in (QTY_COL, PRICE_COL, AMT_COL):
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(i, c, it)
        self._recalc()

    def _row_qty(self, i, r):
        return r["remaining_qty"] if self._checks[i].isChecked() else 0.0

    def _recalc(self, *_):
        total = sum(round(self._row_qty(i, r) * (r["unit_price"] or 0), 2)
                    for i, r in enumerate(self._rows))
        self.total_lbl.setText(f"PR total: ₱{total:,.2f}")

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
        if not self.purpose_combo.text().strip():
            QMessageBox.warning(self, "Purpose required", "Enter the Purpose first.")
            self.purpose_combo.setFocus()
            return
        db.create_pr(self.batch_id, month, self.purpose_combo.text(), lines,
                    delivery_period=self.delivery_edit.text(),
                    fund_source=self.fund_source_edit.currentText(),
                    kind=self.kind_combo.currentData())
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
        self.resize(1200, 680)

        root = QVBoxLayout(self)

        self.pr_no_edit = QLineEdit(header["pr_no"] or "")
        self.purpose_edit = QLineEdit(header["purpose"] or "")
        self.purpose_edit.setPlaceholderText("Required")
        existing_lines = db.pr_lines_for(pr_header_id)
        self.kind_combo = _kind_combo(db.pr_kind(header, existing_lines))
        self.pr_no_edit.setFixedWidth(200)
        no_row = _field_row("PR/JR No.:", self.pr_no_edit)
        no_row.addSpacing(24)
        no_row.addWidget(QLabel("Type:"))
        no_row.addWidget(self.kind_combo)
        no_row.addStretch()
        root.addLayout(no_row)
        root.addSpacing(12)

        left = QVBoxLayout()
        left.addWidget(QLabel(f"<b>Already in this PR/JR</b> — {self.month.title()} only"))
        self.existing_table = QTableWidget(0, 4)
        self.existing_table.setHorizontalHeaderLabels(
            ["Item Description", "Qty", "Unit Price", "Amount"])
        hh = self.existing_table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        for c in (1, 2, 3):
            hh.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        self.existing_table.verticalHeader().setVisible(False)
        self.existing_table.verticalHeader().setDefaultSectionSize(30)
        self.existing_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.existing_table.setSelectionMode(QAbstractItemView.NoSelection)
        self.existing_table.setFocusPolicy(Qt.NoFocus)      # no focus rectangle on a read-only table
        self.existing_table.setShowGrid(False)
        left.addWidget(self.existing_table, stretch=1)

        right = QVBoxLayout()
        top = QHBoxLayout()
        top.addWidget(QLabel(f"<b>Add more items</b> ({self.month.title()} only):"))
        top.addSpacing(12)
        self.select_all = QCheckBox("Select all")
        self.select_all.toggled.connect(self._toggle_all)
        top.addWidget(self.select_all)
        top.addStretch()
        self.total_lbl = QLabel("Adding: ₱0.00")
        self.total_lbl.setObjectName("bold")
        top.addWidget(self.total_lbl)
        right.addLayout(top)

        self.table = QTableWidget(0, len(BUILD_COLS))
        self.table.setHorizontalHeaderLabels(BUILD_COLS)
        hh2 = self.table.horizontalHeader()
        for c in range(len(BUILD_COLS)):
            hh2.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        hh2.setSectionResizeMode(DESC_COL, QHeaderView.Stretch)
        hh2.setSectionResizeMode(PURP_COL, QHeaderView.Interactive)
        self.table.setColumnWidth(PURP_COL, 150)
        self.table.setTextElideMode(Qt.ElideRight)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setShowGrid(False)
        right.addWidget(self.table, stretch=1)
        panes = QHBoxLayout()
        panes.setSpacing(14)
        panes.addLayout(left, stretch=5)
        panes.addLayout(right, stretch=7)
        root.addLayout(panes, stretch=1)

        root.addLayout(_field_row("Purpose:", self.purpose_edit))

        self.delivery_edit = QLineEdit(header["delivery_period"] or "")
        self.delivery_edit.setPlaceholderText("e.g. 5 calendar days")
        self.fund_source_edit = _fund_source_combo(header["fund_source"] or "")
        root.addLayout(_delivery_fund_row(self.delivery_edit, self.fund_source_edit))

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
            box.toggled.connect(self._recalc)
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
                (PURP_COL, r["project_title"] or ""),
                (QTY_COL, _qty_txt(r["remaining_qty"])),
                (UNIT_COL, r["unit"] or ""),
                (PRICE_COL, f"{r['unit_price']:,.2f}"),
                (AMT_COL, f"{amt:,.2f}"),
            ):
                it = QTableWidgetItem(text)
                it.setFlags(Qt.ItemIsEnabled)
                it.setToolTip(text)
                if c in (QTY_COL, PRICE_COL, AMT_COL):
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(i, c, it)
        self._recalc()

    def _toggle_all(self, on):
        for box in self._checks:
            box.setChecked(on)

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
        if not self.purpose_edit.text().strip():
            QMessageBox.warning(self, "Purpose required", "Enter the Purpose first.")
            self.purpose_edit.setFocus()
            return
        new_no = self.pr_no_edit.text().strip()
        if not new_no:
            QMessageBox.warning(self, "PR/JR No. required", "PR/JR No. can't be blank.")
            return
        if db.pr_no_taken(self.batch_id, new_no, self.pr_header_id):
            QMessageBox.warning(self, "PR/JR No. already used",
                                f"{new_no} is already used by another PR/JR in this plan.")
            return
        unchanged = (
            new_no == (current["pr_no"] or "")
            and self.kind_combo.currentData() == db.pr_kind(
                current, db.pr_lines_for(self.pr_header_id))
            and not lines
            and self.purpose_edit.text() == (current["purpose"] or "")
            and self.delivery_edit.text() == (current["delivery_period"] or "")
            and self.fund_source_edit.currentText() == (current["fund_source"] or "")
        )
        if unchanged:
            QMessageBox.information(self, "Nothing changed",
                                    "Tick at least one item to add, or edit a field.")
            return
        if lines:
            db.add_pr_lines(self.pr_header_id, self.batch_id, lines)
        db.update_pr_no(self.pr_header_id, new_no)
        db.update_pr_kind(self.pr_header_id, self.kind_combo.currentData())
        db.update_pr_purpose(self.pr_header_id, self.purpose_edit.text())
        db.update_pr_extra(self.pr_header_id, delivery_period=self.delivery_edit.text(),
                           fund_source=self.fund_source_edit.currentText(),
                           stock_no=current["stock_no"] or "")
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
        self._months = []
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(10)

        self.banner = style.make_banner()
        root.addWidget(self.banner)

        bar = QHBoxLayout()
        self.new_btn = QPushButton("New PR/JR…")
        self.new_btn.clicked.connect(self._new_pr)
        bar.addWidget(self.new_btn)
        bar.addStretch()
        self.gen_btn = QPushButton("Generate  ▾")
        self.gen_btn.setObjectName("secondary")
        self.gen_btn.clicked.connect(self._show_generate_menu)
        bar.addWidget(self.gen_btn)
        self.bar_widget = QWidget()
        bar.setContentsMargins(0, 0, 0, 0)
        self.bar_widget.setLayout(bar)
        root.addWidget(self.bar_widget)

        self.table = QTableWidget(0, len(COLS))
        self.table.setHorizontalHeaderLabels(COLS)
        hh = self.table.horizontalHeader()
        for _c in range(len(COLS)):
            hh.setSectionResizeMode(_c, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(3, QHeaderView.Stretch)
        hh.setDefaultAlignment(Qt.AlignCenter | Qt.AlignVCenter)
        hh.setMinimumHeight(34)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(28)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.cellDoubleClicked.connect(self._on_row_double_clicked)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_row_menu)
        root.addWidget(self.table, stretch=1)

        self.empty = NoPlanWidget()
        root.addWidget(self.empty, stretch=1)

    def refresh(self):
        self.batch_id = db.get_active_batch()
        has = self.batch_id is not None
        self.empty.setVisible(not has)
        self.bar_widget.setVisible(False)
        if not has:
            self.banner.setVisible(False)
            self.table.setVisible(False)
            self.table.setRowCount(0)
            for b in (self.new_btn, self.gen_btn):
                b.setEnabled(False)
            return

        status = db.checking_status(self.batch_id)
        self._set_banner(status)
        balanced = bool(status["balanced"])
        self.bar_widget.setVisible(balanced)

        self.new_btn.setEnabled(balanced)
        self.table.setVisible(balanced)
        if balanced:
            self._load_table()
        else:
            self.table.setRowCount(0)
            self.gen_btn.setEnabled(False)

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
        self._months = []
        for g in prs:
            month = g["month"] or ""
            if month != last_month:
                self._insert_month_header(month)
                self._months.append(month)
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

        self.gen_btn.setEnabled(bool(prs))

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
        self.table.setCellWidget(ri, 0, row)
        self.table.setRowHeight(ri, 34)

    def _show_generate_menu(self):
        menu = QMenu(self)
        menu.addAction("PR/JR", self._generate)
        menu.addAction("RSQ", self._generate_rsq)
        if self._months:
            sbr = menu.addMenu("SBR (cash advance)")
            for m in self._months:
                sbr.addAction((m or "(no month)").title(),
                              lambda _=False, m=m: self._generate_rca(m))
        menu.exec(self.gen_btn.mapToGlobal(QPoint(0, self.gen_btn.height())))

    def _show_row_menu(self, pos):
        row = self.table.rowAt(pos.y())
        it = self.table.item(row, 0) if row >= 0 else None
        if it is None or it.data(Qt.UserRole) is None:
            return
        self.table.selectRow(row)
        menu = QMenu(self)
        menu.addAction("Edit PR/JR", self._edit_pr)
        menu.addAction("Delete PR/JR", self._delete_pr)
        menu.exec(self.table.viewport().mapToGlobal(pos))

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

    def _pr_ids_choice(self, what):
        """-> (proceed, pr_ids). A selected row: just that PR/JR, no question. Nothing
        selected: ask whether to generate everything; No means don't generate at all."""
        sel = self._selected_pr_id()
        if sel is not None:
            return True, [sel]
        yes = QMessageBox.question(
            self, "Generate all?",
            f"No PR/JR is selected. Generate {what} for all PR/JRs?") == QMessageBox.Yes
        return yes, None

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
        from ui.signatory_check import confirm_signatories
        if not confirm_signatories(self, "pr", self.batch_id, "PR/JR"):
            return
        proceed, pr_ids = self._pr_ids_choice("the PR/JR")
        if not proceed:
            return
        self._emit_pdf("Purchase Requests",
                       lambda p: pr_pdf.generate(self.batch_id, p, pr_ids))

    def _generate_rsq(self):
        if self.batch_id is None:
            return
        import rsq_pdf
        from ui.signatory_check import confirm_signatories
        if not confirm_signatories(self, "rsq", self.batch_id, "RSQ"):
            return
        proceed, pr_ids = self._pr_ids_choice("the RSQ")
        if not proceed:
            return
        self._emit_pdf("Request for Sealed Quotation",
                       lambda p: rsq_pdf.generate(self.batch_id, p, pr_ids))

    def _generate_rca(self, month):
        if self.batch_id is None:
            return
        from ui.signatory_check import confirm_signatories
        if not confirm_signatories(self, "cashadv", self.batch_id, "SBR"):
            return
        self._emit_pdf(f"Request for Cash Advance - {(month or '').title()}",
                       lambda p: cashadv_pdf.generate(self.batch_id, p, month, ""))
