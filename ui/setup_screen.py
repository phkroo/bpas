from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit, QLabel, QPushButton,
    QListWidget, QStackedWidget, QScrollArea, QFrame, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QMessageBox, QTabWidget,
)

import db
from ui import style
from ui.tools_screen import ToolsScreen

SIG_COLUMNS = ["Role", "Name", "Designation"]
SECTIONS = ["School Information", "Signatories",
            "Account Codes", "Tools", "Admin Access"]

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

# Real, known default values only (no guessed designations/placeholders — those
# are documented in the user manual instead). Only used when a doc group has NO
# signatories saved yet; never overwrites an already-saved row.
# "auto_name": True means that role always tracks the ACTIVE PLAN's School Head
# (Records) live — not a fixed person, so it's never overwritten and never stale
# when the plan changes. Everything else here is one fixed person who does NOT
# change when the active plan/school changes (signatories are stored once,
# globally, and simply don't move when you switch plans).
SIG_DEFAULT_NAMES = {
    ("ppmp", "prepared by"): {"auto_name": True, "position": "School Head"},
    ("ppmp", "reviewed by"): {"name": "NICE C. ILARA",
                              "position": "Administrative Officer IV - Procurement Officer"},
    ("ppmp", "okay as to fund"): {"name": "JOHANNA MARIE B. SARABIA LPT",
                                  "position": "Administrative Officer V - Budget Officer"},
    ("ppmp", "recommending approval"): {
        "name": "NILITA L. RAGAY EdD",
        "position": "OIC - Assistant Schools Division Superintendent"},
    ("ppmp", "approved by"): {"name": "BERNADETTE A. SUSVILLA EdD, CESO V",
                              "position": "Schools Division Superintendent"},

    ("sobp", "prepared by"): {"auto_name": True, "position": "School Head"},
    ("sobp", "reviewed by"): {"name": "Emmanuel B. Garcia"},

    # SBR (RCA) doesn't actually read this from the signatories table — the
    # generated report already pulls the School Head straight from the active
    # plan (cashadv_pdf.py). This row is display-only, so whoever is filling
    # in Setup can see which SH name that report will use.
    ("cashadv", "sh"): {"auto_name": True, "position": "School Head"},
}

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

        header = QHBoxLayout()
        self.dirty_label = QLabel("Unsaved changes")
        self.dirty_label.setObjectName("onBg")
        self.dirty_label.setStyleSheet(f"color: {style.current_palette()['muted']};")
        self.dirty_label.setVisible(False)
        header.addWidget(self.dirty_label)
        header.addStretch()
        self.save_btn = QPushButton("Save Changes")
        self.save_btn.clicked.connect(self._save)
        self.save_btn.setEnabled(False)
        header.addWidget(self.save_btn)
        root.addLayout(header)

        body = QHBoxLayout()
        body.setSpacing(14)
        root.addLayout(body, stretch=1)

        self.nav = QListWidget()
        self.nav.setObjectName("setupNav")
        self.nav.setFixedWidth(230)
        self.nav.addItems(SECTIONS)
        self.nav.currentRowChanged.connect(self._on_section)
        body.addWidget(self.nav)
        # Account Codes stays hidden from normal users until admin mode is
        # activated (Admin Access tab), same session-only reveal as Consolidation.
        self.nav.setRowHidden(SECTIONS.index("Account Codes"), True)

        self.pages = QStackedWidget()
        body.addWidget(self.pages, stretch=1)
        for builder in (self._page_school,
                        self._page_signatories, self._page_account_codes,
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
            self.pages.setCurrentIndex(row)

    # ---------- pages ----------

    def _page_school(self):
        w = QWidget()
        form = QFormLayout(w)
        form.setContentsMargins(6, 6, 12, 12)
        form.setSpacing(12)
        self.region_edit = QLineEdit()
        self.division_edit = QLineEdit()
        self.name_edit = QLineEdit()
        self.head_edit = QLineEdit()
        self.region_edit.setPlaceholderText("e.g. Region VII - Central Visayas")
        self.division_edit.setPlaceholderText("e.g. Schools Division of Bais City")
        p = style.current_palette()
        for e in (self.name_edit, self.head_edit):
            e.setReadOnly(True)
            e.setStyleSheet(f"background: {p['disabled_bg']}; color: {p['muted']};")
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
        note.setStyleSheet(f"color: {p['muted']};")
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
            scope.setStyleSheet(f"color: {style.current_palette()['muted']};")
            scope.setVisible(per_plan)
            self.sig_scope_labels[doc] = scope
            pv.addWidget(scope)

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
        hint = QLabel("UACS Object Codes used in BPAS. Edit any cell, add a row, or remove "
                      "selected rows — you'll be asked to save when you leave.")
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {style.current_palette()['muted']};")
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

    def _page_admin_access(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(6, 6, 12, 12)
        v.setSpacing(16)

        hint = QLabel(
            "The Consolidation tab is hidden from everyone by default. Enter the "
            "admin password below to reveal it for the rest of this session.")
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {style.current_palette()['muted']};")
        v.addWidget(hint)

        activate_form = QFormLayout()
        activate_form.setSpacing(12)
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
        self.nav.setRowHidden(SECTIONS.index("Account Codes"), False)
        self.admin_activated.emit()
        from ui.toast import toast
        toast(self, "Admin mode activated — Consolidation tab and Account Codes are now visible")

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
            role, name = cell(0), cell(1)
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

    def _collect_pr_config(self):
        return {k: e.text().strip() for k, e in self.pr_edits.items()}

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
        self.region_edit.setText(info.get("region", ""))
        self.division_edit.setText(info.get("division", ""))
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
                    table.setEnabled(False)
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

    def _save(self):
        plan = db.get_plan(db.get_active_batch())
        db.save_school_info(
            plan["school_name"] or "", plan["school_head"] or "",
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

        self._dirty = False
        self.refresh()
        self.saved.emit()
        from ui.toast import toast
        toast(self, "Setup saved")

    # ---------- unsaved-changes handling ----------

    def _update_dirty_ui(self):
        self.dirty_label.setVisible(self._dirty)
        self.save_btn.setEnabled(self._dirty)

    def _mark_dirty(self, *_):
        if not self._loading:
            self._dirty = True
            self._update_dirty_ui()

    def _watch_edits(self):
        for e in (self.region_edit, self.division_edit, self.year_edit):
            e.textEdited.connect(self._mark_dirty)
        for t in (self.acct_code_table, *self.sig_tables.values()):
            t.itemChanged.connect(self._mark_dirty)

    def confirm_leave(self) -> bool:
        """True if it's fine to leave Setup: nothing pending, or the user chose."""
        if not self._dirty:
            return True
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle("Unsaved changes")
        box.setText("You have unsaved changes in Setup.")
        box.setInformativeText("Save them before leaving?")
        save = box.addButton("Save", QMessageBox.AcceptRole)
        box.addButton("Don't Save", QMessageBox.DestructiveRole)
        cancel = box.addButton("Cancel", QMessageBox.RejectRole)
        box.setDefaultButton(save)
        box.exec()
        clicked = box.clickedButton()
        if clicked is cancel:
            return False
        if clicked is save:
            self._save()
        else:
            self._dirty = False
            self.refresh()
        return True
