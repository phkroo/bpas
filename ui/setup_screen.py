from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit, QLabel, QPushButton,
    QListWidget, QStackedWidget, QScrollArea, QFrame, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QMessageBox, QTabWidget,
)

import db
from sig_defaults import SIG_DEFAULT_NAMES
from ui import style
from ui.tools_screen import ToolsScreen

SIG_COLUMNS = ["Role", "Name", "Designation"]
SECTIONS = ["School Information", "Signatories", "Fund Sources",
            "Account Codes", "Procurement Modes", "Units", "Schools", "Tools", "Admin Access"]
NO_SAVE_SECTIONS = ["Tools", "Admin Access"]
ADMIN_ONLY_SECTIONS = ["Fund Sources", "Account Codes", "Procurement Modes", "Units", "Schools"]

# (doc, tab title, default roles, per_plan). per_plan groups (PR, RSQ) are stored
# against the active plan; PPMP / SOBP / APP are one global set.
# 5th item (optional, defaults True): whether the Designation column is shown
# for that doc group — RSQ signatories don't carry a designation.
SIG_GROUPS = [
    ("ppmp", "PPMP", ["Prepared by", "Reviewed by", "Okay as to Fund",
                      "Recommending Approval", "Approved by"], False),
    ("sobp", "SOB / MDP", ["Prepared by", "Reviewed by", "Okay as to Fund",
                           "Recommending Approval", "Approved by"], False),
    ("app", "APP", ["Prepared by", "Reviewed by", "Recommended by", "Approved by"], False),
    ("pr", "PR", ["Requested By", "Recommending Approval", "Approved By"], True),
    ("rsq", "RSQ",
     ["BAC Chairperson", "BAC Vice-Chairperson", "BAC Member", "BAC Member", "BAC Member",
      "Canvassed By"], True, False),
    ("cashadv", "SBR", ["SH", "Approved By"], True),
]

# Preloaded signatories live in sig_defaults.py (also used to seed a fresh database).
# Roles that always track the active plan's School Head — read-only in Setup,
# because editing them wouldn't do anything (the plan overrides it every load).
_AUTO_NAME_ROLES = {(doc, role) for (doc, role), v in SIG_DEFAULT_NAMES.items()
                    if v.get("auto_name")}


def _sig_group_cols(group):
    """SIG_GROUPS entries are 4-tuples by default; a 5th item, if present,
    is the show_position flag."""
    return group[4] if len(group) > 4 else True


class SetupScreen(QWidget):
    saved = Signal()
    admin_activated = Signal()

    def __init__(self):
        super().__init__()
        self._dirty = False
        self._loading = False
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(10)

        self.header_widget = QWidget()
        header = QHBoxLayout(self.header_widget)
        header.setContentsMargins(0, 0, 0, 0)
        self.dirty_label = QLabel("Unsaved changes")
        self.dirty_label.setObjectName("onBg")
        self.dirty_label.setObjectName("muted")
        self.dirty_label.setVisible(False)
        header.addWidget(self.dirty_label)
        header.addStretch()
        self.save_btn = QPushButton("Save Changes")
        self.save_btn.clicked.connect(self._save)
        self.save_btn.setEnabled(False)
        sp = self.save_btn.sizePolicy()
        sp.setRetainSizeWhenHidden(True)
        self.save_btn.setSizePolicy(sp)
        header.addWidget(self.save_btn)
        root.addWidget(self.header_widget)

        body = QHBoxLayout()
        body.setSpacing(14)
        root.addLayout(body, stretch=1)

        self.nav = QListWidget()
        self.nav.setObjectName("setupNav")
        self.nav.setFixedWidth(230)
        self.nav.addItems(SECTIONS)
        self.nav.currentRowChanged.connect(self._on_section)
        body.addWidget(self.nav)
        # Admin-only sections stay hidden from normal users until admin mode is
        # activated (Admin Access tab), same session-only reveal as Consolidation.
        for name in ADMIN_ONLY_SECTIONS:
            self.nav.setRowHidden(SECTIONS.index(name), True)

        self.pages = QStackedWidget()
        body.addWidget(self.pages, stretch=1)
        for builder in (self._page_school,
                        self._page_signatories, self._page_fund_sources,
                        self._page_account_codes,
                        self._page_procurement_modes, self._page_units,
                        self._page_schools,
                        self._page_tools, self._page_admin_access):
            self.pages.addWidget(self._scroll(builder()))

        self.nav.setCurrentRow(0)
        self._watch_edits()

    def _scroll(self, w):
        s = QScrollArea()
        s.setWidgetResizable(True)
        s.setFrameShape(QFrame.Shape.NoFrame)
        s.setWidget(w)
        return s

    def _on_section(self, row):
        if row >= 0:
            # Unsaved edits on the tab being left are dropped, not carried along.
            if self._dirty:
                self._dirty = False
                self.refresh()
            self.pages.setCurrentIndex(row)
            self._update_dirty_ui()

    # ---------- pages ----------

    def _page_school(self):
        w = QWidget()
        form = QFormLayout(w)
        form.setContentsMargins(6, 6, 12, 12)
        form.setSpacing(12)
        form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.region_edit = QLineEdit()
        self.division_edit = QLineEdit()
        self.name_edit = QLineEdit()
        self.head_edit = QLineEdit()
        self.region_edit.setPlaceholderText("e.g. REGION VII - CENTRAL VISAYAS")
        self.division_edit.setPlaceholderText("e.g. SCHOOLS DIVISION OF BAIS CITY")
        for e in (self.region_edit, self.division_edit):      # always capitals, as they print
            e.textEdited.connect(lambda text, e=e: self._force_upper(e, text))
        p = style.current_palette()
        for e in (self.name_edit, self.head_edit):
            e.setReadOnly(True)
            e.setProperty("locked", True)
        self.year_edit = QLineEdit()
        self.year_edit.setPlaceholderText("e.g. 2026")

        form.addRow("Region:", self.region_edit)
        form.addRow("Division:", self.division_edit)
        form.addRow("School Name:", self.name_edit)
        form.addRow("School Head:", self.head_edit)
        form.addRow("Calendar Year:", self.year_edit)
        note = QLabel("School Name and School Head follow the active plan (School ID "
                      "shown in parentheses) — switch or edit it in Records.")
        note.setWordWrap(True)
        note.setObjectName("muted")
        form.addRow("", note)
        return w

    def _page_signatories(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(6, 6, 12, 12)
        tabs = QTabWidget()
        v.addWidget(tabs)
        self.sig_tables = {}
        self.sig_scope_labels = {}
        self.sig_show_position = {}
        for g in SIG_GROUPS:
            doc, title, _roles, per_plan = g[:4]
            show_position = _sig_group_cols(g)
            self.sig_show_position[doc] = show_position
            cols = SIG_COLUMNS if show_position else SIG_COLUMNS[:2]

            page = QWidget()
            pv = QVBoxLayout(page)
            pv.setContentsMargins(4, 10, 4, 4)

            scope = QLabel()
            scope.setWordWrap(True)
            scope.setObjectName("muted")
            self.sig_scope_labels[doc] = scope
            pv.addWidget(scope)
            scope.setVisible(per_plan)      # after parenting, or it flashes as its own window

            table = QTableWidget(0, len(cols))
            table.setHorizontalHeaderLabels(cols)
            table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
            table.setSelectionBehavior(QAbstractItemView.SelectRows)
            table.verticalHeader().setVisible(False)
            table.verticalHeader().setDefaultSectionSize(30)
            self.sig_tables[doc] = table
            pv.addWidget(table)

            row = QHBoxLayout()
            add_btn = QPushButton("Add Row")
            add_btn.setObjectName("secondary")
            add_btn.clicked.connect(lambda _=False, d=doc: self._add_sig_row(d))
            rm_btn = QPushButton("Remove Selected")
            rm_btn.setObjectName("danger")
            rm_btn.clicked.connect(lambda _=False, d=doc: self._remove_sig_row(d))
            row.addStretch()
            row.addWidget(add_btn)
            row.addWidget(rm_btn)
            pv.addLayout(row)

            tabs.addTab(page, title)
        return w

    def _page_account_codes(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(6, 6, 12, 12)
        hint = QLabel("UACS Object Codes used in BPAS. Edit, add or remove rows, then Save Changes.")
        hint.setWordWrap(True)
        hint.setObjectName("muted")
        v.addWidget(hint)
        self.acct_code_table = QTableWidget(0, 2)
        self.acct_code_table.setHorizontalHeaderLabels(
            ["UACS Object Code", "Accounting Title"])
        self.acct_code_table.horizontalHeader().setDefaultAlignment(Qt.AlignCenter)
        self.acct_code_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.acct_code_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.acct_code_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.acct_code_table.verticalHeader().setVisible(False)
        self.acct_code_table.verticalHeader().setDefaultSectionSize(30)
        v.addWidget(self.acct_code_table)

        row = QHBoxLayout()
        add_btn = QPushButton("Add Row")
        add_btn.setObjectName("secondary")
        add_btn.clicked.connect(self._add_acct_row)
        rm_btn = QPushButton("Remove Selected")
        rm_btn.setObjectName("danger")
        rm_btn.clicked.connect(self._remove_acct_rows)
        row.addStretch()
        row.addWidget(add_btn)
        row.addWidget(rm_btn)
        v.addLayout(row)
        return w

    def _page_procurement_modes(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(6, 6, 12, 12)
        hint = QLabel("Procurement modes offered in every Excel template and enforced on import.")
        hint.setWordWrap(True)
        hint.setObjectName("muted")
        v.addWidget(hint)
        self.procurement_mode_table = QTableWidget(0, 1)
        self.procurement_mode_table.setHorizontalHeaderLabels(["Mode of Procurement"])
        self.procurement_mode_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.procurement_mode_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.procurement_mode_table.verticalHeader().setVisible(False)
        self.procurement_mode_table.verticalHeader().setDefaultSectionSize(30)
        v.addWidget(self.procurement_mode_table)

        row = QHBoxLayout()
        add_btn = QPushButton("Add Row")
        add_btn.setObjectName("secondary")
        add_btn.clicked.connect(self._add_procurement_mode_row)
        rm_btn = QPushButton("Remove Selected")
        rm_btn.setObjectName("danger")
        rm_btn.clicked.connect(self._remove_procurement_mode_rows)
        row.addStretch()
        row.addWidget(add_btn)
        row.addWidget(rm_btn)
        v.addLayout(row)
        return w

    def _add_procurement_mode_row(self, mode=""):
        t = self.procurement_mode_table
        r = t.rowCount()
        t.insertRow(r)
        t.setItem(r, 0, QTableWidgetItem(mode))
        if not mode:
            t.setCurrentCell(r, 0)
            t.editItem(t.item(r, 0))

    def _remove_procurement_mode_rows(self):
        t = self.procurement_mode_table
        rows = sorted({i.row() for i in t.selectedItems()}, reverse=True)
        for r in rows:
            t.removeRow(r)
        if rows:
            self._mark_dirty()

    def _collect_procurement_modes(self):
        t = self.procurement_mode_table
        out = []
        for r in range(t.rowCount()):
            item = t.item(r, 0)
            if item and item.text().strip():
                out.append(item.text().strip())
        return out

    def _page_fund_sources(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(6, 6, 12, 12)
        hint = QLabel("Fund sources offered in PR/JR (e.g. MOOE, SPED, SNED). "
                      "Add a row for a new one, then click Save Changes.")
        hint.setWordWrap(True)
        hint.setObjectName("muted")
        v.addWidget(hint)
        self.fund_table = QTableWidget(0, 1)
        self.fund_table.setHorizontalHeaderLabels(["Fund Source"])
        self.fund_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.fund_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.fund_table.verticalHeader().setVisible(False)
        self.fund_table.verticalHeader().setDefaultSectionSize(30)
        v.addWidget(self.fund_table)

        row = QHBoxLayout()
        add_btn = QPushButton("Add Row")
        add_btn.setObjectName("secondary")
        add_btn.clicked.connect(lambda: self._add_fund_row())
        rm_btn = QPushButton("Remove Selected")
        rm_btn.setObjectName("danger")
        rm_btn.clicked.connect(self._remove_fund_rows)
        row.addStretch()
        row.addWidget(add_btn)
        row.addWidget(rm_btn)
        v.addLayout(row)
        return w

    def _add_fund_row(self, name=""):
        t = self.fund_table
        r = t.rowCount()
        t.insertRow(r)
        t.setItem(r, 0, QTableWidgetItem(name))
        if not name:
            t.setCurrentCell(r, 0)
            t.editItem(t.item(r, 0))

    def _remove_fund_rows(self):
        t = self.fund_table
        rows = sorted({i.row() for i in t.selectedItems()}, reverse=True)
        for r in rows:
            t.removeRow(r)
        if rows:
            self._mark_dirty()

    def _collect_fund_sources(self):
        t = self.fund_table
        return [t.item(r, 0).text().strip() for r in range(t.rowCount())
                if t.item(r, 0) and t.item(r, 0).text().strip()]

    def _page_units(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(6, 6, 12, 12)
        hint = QLabel("Unit suggestions for the Excel templates. Other values can still be typed.")
        hint.setWordWrap(True)
        hint.setObjectName("muted")
        v.addWidget(hint)
        self.unit_table = QTableWidget(0, 1)
        self.unit_table.setHorizontalHeaderLabels(["Unit"])
        self.unit_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.unit_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.unit_table.verticalHeader().setVisible(False)
        self.unit_table.verticalHeader().setDefaultSectionSize(30)
        v.addWidget(self.unit_table)

        row = QHBoxLayout()
        add_btn = QPushButton("Add Row")
        add_btn.setObjectName("secondary")
        add_btn.clicked.connect(self._add_unit_row)
        rm_btn = QPushButton("Remove Selected")
        rm_btn.setObjectName("danger")
        rm_btn.clicked.connect(self._remove_unit_rows)
        row.addStretch()
        row.addWidget(add_btn)
        row.addWidget(rm_btn)
        v.addLayout(row)
        return w

    def _add_unit_row(self, unit=""):
        t = self.unit_table
        r = t.rowCount()
        t.insertRow(r)
        t.setItem(r, 0, QTableWidgetItem(unit))
        if not unit:
            t.setCurrentCell(r, 0)
            t.editItem(t.item(r, 0))

    def _remove_unit_rows(self):
        t = self.unit_table
        rows = sorted({i.row() for i in t.selectedItems()}, reverse=True)
        for r in rows:
            t.removeRow(r)
        if rows:
            self._mark_dirty()

    def _collect_units(self):
        t = self.unit_table
        out = []
        for r in range(t.rowCount()):
            item = t.item(r, 0)
            if item and item.text().strip():
                out.append(item.text().strip())
        return out

    def _page_schools(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(6, 6, 12, 12)
        hint = QLabel("Schools accepted on import and offered in templates. Level Type: "
                      + ", ".join(db.SCHOOL_LEVEL_TYPES) + ".")
        hint.setWordWrap(True)
        hint.setObjectName("muted")
        v.addWidget(hint)
        self.school_table = QTableWidget(0, 4)
        self.school_table.setHorizontalHeaderLabels(
            ["Level Type", "IU Code", "School ID", "School Name"])
        hh = self.school_table.horizontalHeader()
        for c in range(3):
            hh.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(3, QHeaderView.Stretch)
        self.school_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.school_table.verticalHeader().setVisible(False)
        self.school_table.verticalHeader().setDefaultSectionSize(30)
        v.addWidget(self.school_table)

        row = QHBoxLayout()
        add_btn = QPushButton("Add Row")
        add_btn.setObjectName("secondary")
        add_btn.clicked.connect(lambda: self._add_school_row())
        rm_btn = QPushButton("Remove Selected")
        rm_btn.setObjectName("danger")
        rm_btn.clicked.connect(self._remove_school_rows)
        row.addStretch()
        row.addWidget(add_btn)
        row.addWidget(rm_btn)
        v.addLayout(row)
        return w

    def _add_school_row(self, level_type="", iu_code="", school_id="", name=""):
        t = self.school_table
        r = t.rowCount()
        t.insertRow(r)
        for c, text in enumerate((level_type, iu_code, school_id, name)):
            t.setItem(r, c, QTableWidgetItem(text))
        if not (level_type or school_id or name):
            t.setCurrentCell(r, 0)
            t.editItem(t.item(r, 0))

    def _remove_school_rows(self):
        t = self.school_table
        rows = sorted({i.row() for i in t.selectedItems()}, reverse=True)
        for r in rows:
            t.removeRow(r)
        if rows:
            self._mark_dirty()

    def _collect_schools(self):
        """Rows as (level_type, iu_code, school_id, name); blank rows are skipped."""
        t = self.school_table
        out = []
        for r in range(t.rowCount()):
            vals = [(t.item(r, c).text().strip() if t.item(r, c) else "") for c in range(4)]
            if any(vals):
                out.append(tuple(vals))
        return out

    def _school_problem(self, schools):
        """First problem in the school rows as a message, or None if all are fine."""
        for n, (level_type, _iu, school_id, name) in enumerate(schools, start=1):
            if level_type not in db.SCHOOL_LEVEL_TYPES:
                return (f"Schools, row {n}: Level Type “{level_type}” is not valid. "
                        f"Use one of: {', '.join(db.SCHOOL_LEVEL_TYPES)}.")
            if not school_id or not name:
                return f"Schools, row {n}: School ID and School Name are both required."
        return None
    def _page_admin_access(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(6, 6, 12, 12)
        v.setSpacing(16)

        hint = QLabel(
            "The Consolidation tab is hidden from everyone by default. Enter the "
            "admin password below to reveal it for the rest of this session.")
        hint.setWordWrap(True)
        hint.setObjectName("muted")
        v.addWidget(hint)

        activate_form = QFormLayout()
        activate_form.setSpacing(12)
        activate_form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        v.addLayout(activate_form)
        self.admin_activate_pw = QLineEdit()
        self.admin_activate_pw.setEchoMode(QLineEdit.Password)
        self.admin_activate_pw.setPlaceholderText("Admin password")
        self.admin_activate_pw.returnPressed.connect(self._activate_admin_mode)
        activate_form.addRow("Password:", self.admin_activate_pw)
        activate_btn = QPushButton("Activate Admin Mode")
        activate_btn.clicked.connect(self._activate_admin_mode)
        activate_form.addRow("", activate_btn)

        v.addStretch()
        return w

    def _activate_admin_mode(self):
        pw = self.admin_activate_pw.text()
        if not db.check_admin_password(pw):
            QMessageBox.warning(self, "Incorrect Password", "That password is incorrect.")
            return
        self.admin_activate_pw.clear()
        for name in ADMIN_ONLY_SECTIONS:
            self.nav.setRowHidden(SECTIONS.index(name), False)
        self.admin_activated.emit()
        from ui.toast import toast
        toast(self, "Admin mode activated — Consolidation, Account Codes, "
                    "Procurement Modes, Units and Schools are now visible")

    def _page_tools(self):
        self.tools_screen = ToolsScreen()
        return self.tools_screen

    def _add_acct_row(self, code="", title=""):
        t = self.acct_code_table
        r = t.rowCount()
        t.insertRow(r)
        code_item = QTableWidgetItem(code if isinstance(code, str) else "")
        code_item.setTextAlignment(Qt.AlignCenter)
        t.setItem(r, 0, code_item)
        t.setItem(r, 1, QTableWidgetItem(title))
        if not title:
            t.setCurrentCell(r, 0)
            t.editItem(t.item(r, 0))

    def _remove_acct_rows(self):
        t = self.acct_code_table
        rows = sorted({i.row() for i in t.selectedItems()}, reverse=True)
        for r in rows:
            t.removeRow(r)
        if rows:
            self._mark_dirty()

    # ---------- signatory helpers ----------

    def _add_sig_row(self, doc, role="", name="", position="", read_only=False):
        table = self.sig_tables[doc]
        r = table.rowCount()
        table.insertRow(r)
        values = (role, name, position) if self.sig_show_position.get(doc, True) else (role, name)
        p = style.current_palette()
        for c, value in enumerate(values):
            item = QTableWidgetItem(value)
            if read_only and c in (1, 2):
                # Name/Designation for a role that always tracks the active
                # plan's School Head — editing it here would do nothing, since
                # it's recomputed from Records on every load.
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                item.setBackground(QColor(p["disabled_bg"]))
                item.setForeground(QColor(p["muted"]))
                item.setToolTip("Follows the active plan's School Head (Records) — "
                                "not editable here.")
            table.setItem(r, c, item)

    def _remove_sig_row(self, doc):
        table = self.sig_tables[doc]
        rows = sorted({i.row() for i in table.selectedItems()}, reverse=True)
        for r in rows:
            table.removeRow(r)
        if rows:
            self._mark_dirty()

    def _collect_signatories(self, doc):
        table = self.sig_tables[doc]
        has_position = self.sig_show_position.get(doc, True)
        out = []
        for r in range(table.rowCount()):
            def cell(c):
                item = table.item(r, c)
                return item.text().strip() if item else ""
            role, name = cell(0), cell(1).upper()
            position = cell(2) if has_position else ""
            if role or name or position:
                out.append({"role": role, "name": name, "position": position})
        return out

    def _collect_account_codes(self):
        t = self.acct_code_table
        out = []
        for r in range(t.rowCount()):
            code = t.item(r, 0)
            title = t.item(r, 1)
            out.append((code.text() if code else "", title.text() if title else ""))
        return out

    # ---------- load / save ----------

    def refresh(self):
        if self._dirty:
            return          # never overwrite edits the user hasn't saved/discarded
        self._loading = True
        try:
            self._load()
        finally:
            self._loading = False
            self._dirty = False
            self._update_dirty_ui()

    def _load(self):
        info = db.get_school_info()
        plan = db.get_plan(db.get_active_batch())
        self.region_edit.setText((info.get("region", "") or "").upper())
        self.division_edit.setText((info.get("division", "") or "").upper())
        school = plan["school_name"] or ""
        level = (plan["level"] or "").strip()
        if school and level and level.lower() not in school.lower():
            school = f"{school} - {level} School"
        if school and plan["school_id"]:
            school = f"{school} ({plan['school_id']})"
        self.name_edit.setText(school)
        self.head_edit.setText(plan["school_head"] or "")
        self.name_edit.setPlaceholderText("— no active plan —")
        self.head_edit.setPlaceholderText("— no active plan —")

        a = db.get_allotment()
        self.year_edit.setText(a["calendar_year"])

        active = db.get_active_batch()
        for doc, _title, default_roles, per_plan in (g[:4] for g in SIG_GROUPS):
            table = self.sig_tables[doc]
            table.setRowCount(0)
            if per_plan:
                scope = self.sig_scope_labels[doc]
                if active is None:
                    scope.setText("Import a plan in Records first — PR / RSQ "
                                  "signatories are set per plan.")
                    # No plan yet: show the roles only (no names/designations);
                    # the table stays locked and nothing is saved until a plan
                    # is imported.
                    table.setEnabled(False)
                    for role in default_roles:
                        self._add_sig_row(doc, role)
                    continue
                scope.setText(f"For the active plan: {plan['school_name'] or '(unnamed plan)'}"
                              f"{('  —  ' + plan['level']) if plan['level'] else ''}")
                table.setEnabled(True)
            existing = db.list_signatories(doc, active if per_plan else None)
            if existing:
                existing_roles = {(s["role"] or "").strip().lower() for s in existing}
                # An auto-name role (Prepared by / SH) always shows even if it
                # isn't saved yet — it's computed live from the plan, not read
                # from the DB, so a doc that only ever had other roles saved
                # (e.g. SBR's "Approved By") still gets it added on top.
                for role in default_roles:
                    role_key = (doc, role.strip().lower())
                    if role_key in _AUTO_NAME_ROLES and role.strip().lower() not in existing_roles:
                        default = SIG_DEFAULT_NAMES[role_key]
                        self._add_sig_row(doc, role, (plan["school_head"] or "").upper(),
                                          default.get("position", ""), read_only=True)
                for s in existing:
                    name = s["name"]
                    position = s["position"]
                    role_key = (doc, (s["role"] or "").strip().lower())
                    default = SIG_DEFAULT_NAMES.get(role_key, {})
                    if default.get("auto_name"):
                        # always the ACTIVE plan's School Head — never a name
                        # saved earlier for a different school
                        name = (plan["school_head"] or "").upper()
                        position = default.get("position", "")
                    self._add_sig_row(doc, s["role"], name, position,
                                      read_only=role_key in _AUTO_NAME_ROLES)
            else:
                for role in default_roles:
                    role_key = (doc, role.strip().lower())
                    default = SIG_DEFAULT_NAMES.get(role_key, {})
                    if default.get("auto_name"):
                        name = (plan["school_head"] or "").upper()
                    else:
                        name = default.get("name", "")
                    position = default.get("position", "")
                    self._add_sig_row(doc, role, name, position,
                                      read_only=role_key in _AUTO_NAME_ROLES)

        self.acct_code_table.setRowCount(0)
        for a in sorted(db.list_mooe_accounts(), key=lambda r: r["code"]):
            self._add_acct_row(a["code"], a["title"])

        self.procurement_mode_table.setRowCount(0)
        for m in db.list_procurement_modes():
            self._add_procurement_mode_row(m)

        self.fund_table.setRowCount(0)
        for f in db.list_fund_sources():
            self._add_fund_row(f)

        self.unit_table.setRowCount(0)
        for u in db.list_units():
            self._add_unit_row(u)

        self.school_table.setRowCount(0)
        for s in db.list_schools():
            self._add_school_row(s["level_type"], s["iu_code"], s["school_id"], s["name"])

    def _save(self):
        schools = self._collect_schools()
        problem = self._school_problem(schools)
        if problem:
            QMessageBox.warning(self, "Can't save schools", problem)
            return
        plan = db.get_plan(db.get_active_batch())
        # school_head is deliberately NOT written here — it's a single global
        # setting, so saving the currently-active plan's head into it would make
        # that one school's head "stick" as the default for every future import
        # (see ui/import_dialog.py). Each plan already keeps its own school_head
        # (import_batches.school_head); this global slot is an unused fallback.
        db.save_school_info(
            plan["school_name"] or "", "",
            self.division_edit.text().strip(), "",
            self.region_edit.text().strip())
        db.save_allotment(calendar_year=self.year_edit.text())
        active = db.get_active_batch()
        for doc, _title, _roles, per_plan in (g[:4] for g in SIG_GROUPS):
            if per_plan and active is None:
                continue
            db.replace_signatories(self._collect_signatories(doc), doc,
                                   active if per_plan else None)
        db.replace_mooe_accounts(self._collect_account_codes())
        db.replace_procurement_modes(self._collect_procurement_modes())
        db.replace_fund_sources(self._collect_fund_sources())
        db.replace_units(self._collect_units())
        db.replace_schools(schools)

        self._dirty = False
        self.refresh()
        self.saved.emit()
        from ui.toast import toast
        toast(self, "Setup saved")

    # ---------- unsaved-changes handling ----------

    def _update_dirty_ui(self):
        self.dirty_label.setVisible(self._dirty)
        self.save_btn.setEnabled(self._dirty)
        # Tools / Admin Access have nothing to save — hide the button, but the header
        # row keeps its height so the sidebar and page don't jump between tabs.
        row = self.nav.currentRow()
        self.save_btn.setVisible(
            not (row >= 0 and SECTIONS[row] in NO_SAVE_SECTIONS))

    @staticmethod
    def _force_upper(edit, text):
        up = text.upper()
        if up != text:
            pos = edit.cursorPosition()
            edit.setText(up)
            edit.setCursorPosition(pos)

    def _mark_dirty(self, *_):
        if not self._loading:
            self._dirty = True
            self._update_dirty_ui()

    def _watch_edits(self):
        for e in (self.region_edit, self.division_edit, self.year_edit):
            e.textEdited.connect(self._mark_dirty)
        for t in (self.acct_code_table, self.procurement_mode_table, self.unit_table,
                  self.fund_table,
                  self.school_table, *self.sig_tables.values()):
            t.itemChanged.connect(self._mark_dirty)
        for t in self.sig_tables.values():
            t.itemChanged.connect(self._force_name_uppercase)

    def _force_name_uppercase(self, item):
        """Signatory Name column: forced to ALL CAPS as soon as it's typed,
        not just on save."""
        if self._loading or item.column() != 1:
            return
        upper = item.text().upper()
        if item.text() != upper:
            table = item.tableWidget()
            table.blockSignals(True)
            item.setText(upper)
            table.blockSignals(False)

    def confirm_leave(self) -> bool:
        """Leaving Setup drops any unsaved edits (no prompt); always fine to leave."""
        if self._dirty:
            self._dirty = False
            self.refresh()
        return True
