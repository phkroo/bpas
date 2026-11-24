from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QLineEdit, QComboBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QPushButton,
    QMessageBox, QDialog, QDialogButtonBox,
)

import db
from ui import style
import app_pdf
from ui.empty_state import NoPlanWidget

# Matches app_pdf.py's PDF header text exactly.
COLS = [
    "Project Title",
    "End-User or Implementing Unit",
    "General Description of the Project",
    "Mode of Procurement",
    "To be covered by an Early Procurement Activity? (Yes/No)",
    "Criteria for Bid Evaluation (Including Sustainability and Domestic Preference)",
    "Start of Procurement Activity",
    "End of Procurement Activity",
    "Source of Fund",
    "Estimated Budget / Approved Budget for the Contract (PhP)",
    "PROCUREMENT STRATEGY OR TOOLS",
    "REMARKS (Other relevant descriptions of the procurement project, if applicable)",
]

# Compact two-line headers for the on-screen table (full text shown as a tooltip).
SHORT_COLS = [
    "Project Title",
    "End-User /\nImplementing Unit",
    "General Description\nof the Project",
    "Mode of\nProcurement",
    "Early Procurement\nActivity? (Yes/No)",
    "Criteria for\nBid Evaluation",
    "Start of\nProcurement",
    "End of\nProcurement",
    "Source\nof Fund",
    "Estimated Budget\n(PhP)",
    "Procurement\nStrategy / Tools",
    "Remarks",
]
COL_WIDTHS = [230, 170, 240, 150, 150, 150, 120, 120, 100, 150, 160, 220]

EARLY_PROCUREMENT_OPTIONS = ["", "Yes", "No"]
BID_CRITERIA_OPTIONS = ["", "LCRB", "MEARB", "MARB/HRRB/SRRB", "LCCRB"]
PROCUREMENT_STRATEGY_OPTIONS = [
    "",
    "LCA and LCCA",
    "Subcontracting",
    "Multi-Year Contracting",
    "Design-and-Build Scheme for Infrastructure Projects",
    "Engagement of a Procurement Agent",
    "Use of Framework Agreement Section",
    "Pooled Procurement Section 17",
    "Renewal of Regular and Recurring Services",
    "Warehousing and Inventory Activities",
]


class APPRowDialog(QDialog):
    """Edit the per-project fields for one APP row. Project Title, End-User,
    Source of Fund, Early Procurement, Criteria, Start/End, Procurement
    Strategy and Remarks are all editable and saved to db.app_row_details.
    General Description is only editable for the CSE summary row — for a
    regular row it's tied to the actual Records item, so it stays read-only."""

    def __init__(self, batch_id, row, school, parent=None):
        super().__init__(parent)
        self.batch_id = batch_id
        self.accounting_title = row["accounting_title"]
        self.general_description = row["description"] if not row.get("is_cse_summary") \
            else row.get("cse_desc_key", db.CSE_SUMMARY_DESC)
        # Project view: one row stands for several APP rows (one per account title)
        self.members = row.get("members") or [(self.accounting_title, self.general_description)]
        self.is_cse_summary = bool(row.get("is_cse_summary"))
        self._fitted = False

        self.setWindowTitle("Edit APP Project")
        self.resize(560, 560)

        form = QFormLayout(self)
        form.setSpacing(10)

        self.project_title_edit = QLineEdit(row["project_title"])
        form.addRow("Project Title:", self.project_title_edit)

        def readonly(text):
            lbl = QLineEdit(text)
            lbl.setReadOnly(True)
            lbl.setProperty("locked", True)
            return lbl

        self.end_user_edit = QLineEdit(row["end_user_unit"] or school)
        form.addRow("End-User or Implementing Unit:", self.end_user_edit)

        if self.is_cse_summary:
            self.description_edit = QLineEdit(row["description"])
            form.addRow("General Description of the Project:", self.description_edit)
        else:
            self.description_edit = None
            form.addRow("General Description of the Project:", readonly(row["description"]))

        form.addRow("Mode of Procurement:", readonly(row["modes"]))

        self.early_combo = QComboBox()
        self.early_combo.addItems(EARLY_PROCUREMENT_OPTIONS)
        self.early_combo.setCurrentText(row["early_procurement"])
        form.addRow("To be covered by an Early Procurement Activity? (Yes/No):", self.early_combo)

        self.criteria_combo = QComboBox()
        self.criteria_combo.addItems(BID_CRITERIA_OPTIONS)
        self.criteria_combo.setCurrentText(row["bid_criteria"])
        form.addRow("Criteria for Bid Evaluation:", self.criteria_combo)

        self.start_edit = QLineEdit(row["start_date"])
        self.start_edit.setPlaceholderText("MM/YYYY")
        form.addRow("Start of Procurement Activity:", self.start_edit)

        self.end_edit = QLineEdit(row["end_date"])
        self.end_edit.setPlaceholderText("MM/YYYY")
        form.addRow("End of Procurement Activity:", self.end_edit)

        # dropdown of the fund sources set up in Setup > Fund Sources
        self.fund_edit = QComboBox()
        fund_names = db.list_fund_sources()
        current_fund = (row["source_of_fund"] or db.default_fund_source()).strip()
        self.fund_edit.addItems(fund_names)
        if current_fund and current_fund not in fund_names:
            self.fund_edit.addItem(current_fund)      # keep a value saved earlier
        self.fund_edit.setCurrentText(current_fund)
        form.addRow("Source of Fund:", self.fund_edit)

        form.addRow("Estimated Budget / Approved Budget for the Contract (PhP):",
                    readonly(f"{row['amount']:,.2f}"))

        self.strategy_combo = QComboBox()
        self.strategy_combo.addItems(PROCUREMENT_STRATEGY_OPTIONS)
        self.strategy_combo.setCurrentText(row["procurement_strategy"])
        form.addRow("Procurement Strategy or Tools:", self.strategy_combo)

        self.remarks_edit = QLineEdit(row["remarks"])
        form.addRow("Remarks:", self.remarks_edit)

        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._save)
        btns.rejected.connect(self.reject)
        form.addRow(btns)

    def _save(self):
        fields = dict(
            project_title=self.project_title_edit.text(),
            end_user_unit=self.end_user_edit.text(),
            early_procurement=self.early_combo.currentText(),
            bid_criteria=self.criteria_combo.currentText(),
            start_date=self.start_edit.text(),
            end_date=self.end_edit.text(),
            source_of_fund=self.fund_edit.currentText(),
            procurement_strategy=self.strategy_combo.currentText(),
            remarks=self.remarks_edit.text(),
        )
        if self.description_edit is not None:
            fields["description_override"] = self.description_edit.text()
        for title, gd in self.members:
            db.save_app_row_detail(self.batch_id, title, gd, **fields)
        self.accept()

    def showEvent(self, event):
        super().showEvent(event)
        if self._fitted:
            return
        self._fitted = True
        from ui.dialog_utils import fit_to_host
        fit_to_host(self)


class APPScreen(QWidget):
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
        title = QLabel("Annual Procurement Plan")
        title.setObjectName("pageTitle")
        bar.addWidget(title)
        bar.addStretch()
        self.gen_btn = QPushButton("Generate APP")
        self.gen_btn.clicked.connect(self._generate)
        bar.addWidget(self.gen_btn)
        self.bar_widget = QWidget()
        bar.setContentsMargins(0, 0, 0, 0)
        self.bar_widget.setLayout(bar)
        root.addWidget(self.bar_widget)

        self.table = QTableWidget(0, len(COLS))
        self.table.setHorizontalHeaderLabels(SHORT_COLS)
        hh = self.table.horizontalHeader()
        hh.setDefaultAlignment(Qt.AlignCenter | Qt.AlignVCenter)
        hh.setMinimumHeight(56)
        for c in range(len(COLS)):
            hh.setSectionResizeMode(c, QHeaderView.Interactive)
        for c, width in enumerate(COL_WIDTHS):
            self.table.setColumnWidth(c, width)
        for c, full in enumerate(COLS):
            self.table.horizontalHeaderItem(c).setToolTip(full)
        self.table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.table.setTextElideMode(Qt.ElideRight)
        self.table.setWordWrap(False)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(28)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.cellDoubleClicked.connect(self._on_row_double_clicked)
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
            kind, msg = "bad", "APP is locked until the plan balances — see the Dashboard."
        self.banner.setVisible(True)
        self.banner.setStyleSheet(banner_qss(kind))
        self.banner.setText(msg)

    def _school(self):
        from doc_header import resolve_school
        return resolve_school(db.get_plan(self.batch_id), db.get_school_info())

    def _load_table(self):
        data = db.app_data(self.batch_id)
        school = self._school()
        self.table.setRowCount(0)
        n = 0
        # one flat list, A-Z by project title; the same title can repeat when its
        # description or mode of procurement differs
        for r in db.app_projects(self.batch_id):
            n += 1
            self._add_project_row(r, school)

        if data["cse_rows"]:                 # no CSE items -> no CSE section
            cse_ri = self.table.rowCount()
            self.table.insertRow(cse_ri)
            head = QTableWidgetItem(
                "Common Use Supplies and Equipment (CSE) to be purchased from PS-DBM "
                "(kindly indicate the summary/total amounts only)")
            f = head.font(); f.setBold(True); head.setFont(f)
            self.table.setItem(cse_ri, 0, head)
            self.table.setSpan(cse_ri, 0, 1, len(COLS))
            for r in data["cse_rows"]:       # one row per part that has items
                n += 1
                self._add_project_row(r, school)


    def _add_project_row(self, r, school):
        ri = self.table.rowCount()
        self.table.insertRow(ri)
        amt = QTableWidgetItem(f"{r['amount']:,.2f}")
        amt.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        values = {
            0: QTableWidgetItem(r["project_title"]),
            1: QTableWidgetItem(r["end_user_unit"] or school),
            2: QTableWidgetItem(r["description"]),
            3: QTableWidgetItem(r["modes"]),
            4: QTableWidgetItem(r["early_procurement"]),
            5: QTableWidgetItem(r["bid_criteria"]),
            6: QTableWidgetItem(r["start_date"]),
            7: QTableWidgetItem(r["end_date"]),
            8: QTableWidgetItem(r["source_of_fund"] or db.default_fund_source()),
            9: amt,
            10: QTableWidgetItem(r["procurement_strategy"]),
            11: QTableWidgetItem(r["remarks"]),
        }
        for c in range(len(COLS)):
            it = values[c]
            it.setToolTip(it.text())
            self.table.setItem(ri, c, it)
        # identity for double-click editing, kept on the row's first cell
        self.table.item(ri, 0).setData(Qt.UserRole, r)

    def _on_row_double_clicked(self, row, _col):
        it = self.table.item(row, 0)
        if it is None or self.table.columnSpan(row, 0) > 1:
            return   # a group-header row, not a project row
        row_data = it.data(Qt.UserRole)
        if row_data is None:
            return
        dlg = APPRowDialog(self.batch_id, row_data, self._school(), self)
        if dlg.exec() == QDialog.Accepted:
            self._load_table()

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
