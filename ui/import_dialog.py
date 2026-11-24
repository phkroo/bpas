from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QComboBox, QCompleter, QPushButton, QLabel,
    QLineEdit, QFileDialog, QMessageBox, QDialogButtonBox,
)

import db
import import_excel
import xlsx_lists


def _amount(text):
    text = (text or "").replace(",", "").replace("₱", "").strip()
    try:
        return round(float(text), 2)
    except ValueError:
        return None


class ImportDialog(QDialog):
    imported = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Import a Plan")
        self.setModal(True)
        self.setMinimumWidth(620)
        self._path = None
        self._kind = None          # "xlsx" | "bpasx" | "bpasx_many"
        self._paths = None         # the selected files when several plan files are imported

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        self.choose_btn = QPushButton("Import File (.xlsx or .bpasx)...")
        self.choose_btn.setToolTip(
            "An Excel file in the BPAS template, or a plan file (.bpasx) another "
            "school exported from Records — e.g. to consolidate several schools' plans.")
        self.choose_btn.clicked.connect(self.on_choose)
        layout.addWidget(self.choose_btn)

        self.file_label = QLabel("No file chosen.")
        self.file_label.setObjectName("onBg")
        layout.addWidget(self.file_label)

        self.detect_label = QLabel()
        self.detect_label.setObjectName("onBg")
        self.detect_label.setWordWrap(True)
        layout.addWidget(self.detect_label)

        form = QFormLayout()
        form.setSpacing(10)

        self.school_combo = QComboBox()
        self.school_combo.setEditable(True)
        self.school_combo.setInsertPolicy(QComboBox.NoInsert)
        self.school_combo.addItem("— detected from the file after you choose it —", None)
        for s in db.list_schools():
            self.school_combo.addItem(f"{s['name']}  —  {s['level']}", s["id"])
        comp = self.school_combo.completer()
        comp.setFilterMode(Qt.MatchContains)
        comp.setCompletionMode(QCompleter.PopupCompletion)
        self.school_combo.setEnabled(False)

        # Deliberately blank, not prefilled from db.get_school_info()/get_allotment()
        # — those are single GLOBAL settings, so prefilling from them would show
        # whichever school's head/allotment was last active, for every new import,
        # regardless of which school this actually is.
        self.head_edit = QLineEdit("")
        self.head_edit.setPlaceholderText("School head for this plan")
        self.total_edit = QLineEdit("")
        self.total_edit.setPlaceholderText("e.g. 3913000")
        self.gad_edit = QLineEdit("")
        self.gad_edit.setPlaceholderText("e.g. 195650")

        form.addRow("School:", self.school_combo)
        form.addRow("School Head:", self.head_edit)
        form.addRow("Total Allotment:", self.total_edit)
        form.addRow("GAD Allotment:", self.gad_edit)
        layout.addLayout(form)

        self.import_btn = QPushButton("Save Plan")
        self.import_btn.setEnabled(False)
        self.import_btn.clicked.connect(self.on_import)
        layout.addWidget(self.import_btn)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

    def on_choose(self):
        from ui.filepaths import downloads_dir
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Select BPAS File(s)", downloads_dir(),
            "BPAS files (*.xlsx *.bpasx);;Excel Files (*.xlsx);;BPAS Plan Files (*.bpasx)"
        )
        if not paths:
            return
        if len(paths) > 1:
            plans = [p for p in paths if p.lower().endswith(".bpasx")]
            if len(plans) != len(paths):
                QMessageBox.information(
                    self, "Several files",
                    "Excel templates are imported one at a time (each needs its own school "
                    "head and allotments). Only the plan files (.bpasx) you selected "
                    "were kept.")
            paths = plans
            if not paths:
                return
        if len(paths) > 1:
            self._show_many(paths)
            return
        self._paths = None
        path = paths[0]
        self._path = path
        self._kind = "bpasx" if path.lower().endswith(".bpasx") else "xlsx"
        self.file_label.setText(path)
        self.import_btn.setEnabled(True)

        if self._kind == "bpasx":
            self._show_bpasx_info(path)
            return

        for w in (self.head_edit, self.total_edit, self.gad_edit):
            w.setEnabled(True)
        try:
            text = import_excel.detect_school_text(path)
        except Exception:
            text = ""
        school = db.match_school(text) if text else None
        if school:
            idx = self.school_combo.findData(school["id"])
            if idx >= 0:
                self.school_combo.setCurrentIndex(idx)
            self.school_combo.setEnabled(False)
            self.detect_label.setText(
                f"School: {school['name']} — {school['level']}  "
                f"(School ID {school['school_id']})")
        else:
            self.school_combo.setEnabled(True)
            self.detect_label.setText(
                "Could not detect the school from the file — please pick it above.")

    def _show_many(self, paths):
        """Several plan files at once: each carries its own school, head and allotments."""
        self._paths = list(paths)
        self._path = paths[0]
        self._kind = "bpasx_many"
        self.file_label.setText(f"{len(paths)} plan files selected.")
        self.detect_label.setText(
            "Each school's name, head and allotments come from its own file. "
            "Click Save Plan to import them one after another.")
        for w in (self.school_combo, self.head_edit, self.total_edit, self.gad_edit):
            w.setEnabled(False)
        self.school_combo.setCurrentIndex(0)
        for e in (self.head_edit, self.total_edit, self.gad_edit):
            e.clear()
        self.import_btn.setEnabled(True)

    def _import_many(self):
        """Import every selected plan file. A bad file never stops the others, and a school
        that is already in the database is asked about (Replace / Keep both / Skip)."""
        import json
        import os
        import import_plan
        from PySide6.QtWidgets import QCheckBox

        apply_all = None            # "replace" | "keep" | "skip" once the user ticks "apply to all"
        report = []                 # (file name, text)
        counts = {"imported": 0, "replaced": 0, "skipped": 0, "rejected": 0}
        last_ok = None
        items_total = 0
        for path in self._paths:
            name = os.path.basename(path)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    b = (json.load(f).get("batch") or {})
                existing = db.find_batches_for_school(b.get("school_id"), b.get("level_type"))
            except Exception as exc:
                counts["rejected"] += 1
                report.append((name, f"REJECTED: not a readable plan file ({exc})"))
                continue

            choice = "keep"
            if existing:
                choice = apply_all
                if choice is None:
                    box = QMessageBox(self)
                    box.setIcon(QMessageBox.Question)
                    box.setWindowTitle("School already imported")
                    box.setText(f"{b.get('school_name') or name} is already in your plans "
                                f"({len(existing)}).")
                    box.setInformativeText("Replace it with this file, keep both, or skip this file?")
                    replace_btn = box.addButton("Replace", QMessageBox.AcceptRole)
                    keep_btn = box.addButton("Keep both", QMessageBox.ActionRole)
                    skip_btn = box.addButton("Skip", QMessageBox.RejectRole)
                    all_cb = QCheckBox("Do the same for the remaining schools already imported")
                    box.setCheckBox(all_cb)
                    box.exec()
                    clicked = box.clickedButton()
                    choice = ("replace" if clicked is replace_btn
                              else "keep" if clicked is keep_btn else "skip")
                    if all_cb.isChecked():
                        apply_all = choice
            if choice == "skip":
                counts["skipped"] += 1
                report.append((name, "SKIPPED: school already imported"))
                continue

            try:
                result = import_plan.import_plan(path)
            except import_plan.ImportPlanError as exc:
                counts["rejected"] += 1
                report.append((name, "REJECTED: " + str(exc).replace("\n", " ")[:300]))
                continue
            except Exception as exc:
                counts["rejected"] += 1
                report.append((name, f"REJECTED: {exc}"))
                continue

            items_total += result.imported_count
            last_ok = result.batch_id
            if choice == "replace" and existing:
                for old in existing:
                    db.delete_batch(old)
                counts["replaced"] += 1
                report.append((name, f"REPLACED: {result.imported_count} item(s)"))
            else:
                counts["imported"] += 1
                msg = f"IMPORTED: {result.imported_count} item(s)"
                if result.unmatched_pr_lines:
                    msg += f" ({result.unmatched_pr_lines} PR/JR line(s) could not be relinked)"
                report.append((name, msg))

        if last_ok is not None:
            db.set_active_batch(last_ok)
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning if counts["rejected"] else QMessageBox.Information)
        box.setWindowTitle("Plans imported")
        box.setText(f"{counts['imported']} imported, {counts['replaced']} replaced, "
                    f"{counts['skipped']} skipped, {counts['rejected']} rejected "
                    f"({items_total:,} item(s)).")
        box.setDetailedText("\n".join(f"{n}\n    {t}" for n, t in report))
        box.exec()
        if last_ok is not None:
            self.imported.emit()
            self.accept()

    def _show_bpasx_info(self, path):
        """A plan file carries its own school / head / allotment — show them and
        lock the form instead of asking again."""
        import json
        for w in (self.school_combo, self.head_edit, self.total_edit, self.gad_edit):
            w.setEnabled(False)
        try:
            with open(path, "r", encoding="utf-8") as f:
                b = (json.load(f).get("batch") or {})
            self.detect_label.setText(
                f"Plan file — {b.get('school_name') or '(unnamed school)'}"
                f"{' — ' + b['level'] if b.get('level') else ''}. "
                "School, head and allotment come from the file.")
            # show what the file holds in the (locked) fields, so nothing looks missing
            school = db.match_school_parts(b.get("level_type"), b.get("iu_code"),
                                           b.get("school_id"), b.get("school_name"))
            idx = self.school_combo.findData(school["id"]) if school else -1
            if idx >= 0:
                self.school_combo.setCurrentIndex(idx)
            else:
                self.school_combo.setCurrentText(b.get("school_name") or "")
            self.head_edit.setText(b.get("school_head") or "")
            self.total_edit.setText(f"{float(b.get('total_allotment') or 0):,.2f}")
            self.gad_edit.setText(f"{float(b.get('gad_allotment') or 0):,.2f}")
        except Exception:
            self.detect_label.setText(
                "Could not read this plan file — importing it will report the problem.")

    def _import_bpasx(self):
        import import_plan
        try:
            result = import_plan.import_plan(self._path)
        except import_plan.ImportPlanError as exc:
            QMessageBox.critical(self, "Import Failed", str(exc))
            return
        except Exception as exc:
            QMessageBox.critical(self, "Import Failed", f"Could not import plan file:\n{exc}")
            return

        db.set_active_batch(result.batch_id)
        msg = f"Imported {result.imported_count} item(s)."
        if result.unmatched_pr_lines:
            msg += (f"\n\n{result.unmatched_pr_lines} PR/JR line(s) could not be relinked "
                    "and were skipped (the PR/JR headers themselves were still imported).")
        QMessageBox.information(self, "Plan Imported", msg)
        self.imported.emit()
        self.accept()

    _FIELD_LABELS = {
        "pap_name": "PAP Name", "gad_category": "GAD Category",
        "accounting_title": "Accounting Title", "mode_of_procurement": "Mode of Procurement",
        "app_for": "APP Form", "app_cs": "APP CSE", "unit": "Unit", "month": "Month",
    }

    @staticmethod
    def _rows_txt(rows, cap=6):
        shown = ", ".join(str(r) for r in rows[:cap])
        return f"row {shown}" if len(rows) == 1 else (
            f"rows {shown}" + (f" … +{len(rows) - cap} more" if len(rows) > cap else ""))

    def _check_excel(self) -> bool:
        """Strict pre-import check. Any problem blocks the import. True = clean."""
        import difflib
        try:
            problems = import_excel.validate_file(self._path)
        except Exception:
            return True          # the real import will report file problems
        if not problems:
            return True

        titles = [r["title"] for r in db.list_mooe_accounts()]
        lines = []
        for p in problems:
            if p.kind == "blank_a":
                lines.append(f"• Column A is blank — {self._rows_txt(p.rows)} "
                             f"({len(p.rows)} row{'s' if len(p.rows) != 1 else ''})")
            elif p.kind == "mixed_a":
                lines.append(f"• Column A has a different school/input: “{p.value}” — "
                             f"{len(p.rows)} row{'s' if len(p.rows) != 1 else ''} "
                             f"({self._rows_txt(p.rows)})")
            elif p.kind == "row_error":
                lines.append(f"• Row {p.rows[0]}: {p.value}")
            elif p.kind == "unknown_school":
                lines.append(f"• Column A is not a known school: “{p.value}” — "
                             f"{self._rows_txt(p.rows)}")
            elif p.kind == "gad_missing":
                lines.append("• GAD Category (column E) is required when PAP Name is "
                             f"“{xlsx_lists.GAD_PAP}” — {self._rows_txt(p.rows)}")
            elif p.kind == "gad_not_allowed":
                lines.append("• GAD Category (column E) must be blank unless PAP Name is "
                             f"“{xlsx_lists.GAD_PAP}” — {self._rows_txt(p.rows)}")
            else:
                hint = ""
                if p.field == "accounting_title":
                    near = difflib.get_close_matches(p.value, titles, n=1, cutoff=0.75)
                    if near:
                        hint = f"   → did you mean “{near[0]}”?"
                lines.append(f"• {self._FIELD_LABELS.get(p.field, p.field)} not in the "
                             f"dropdown list: “{p.value}” — {self._rows_txt(p.rows)}{hint}")

        cap = 15
        shown = lines[:cap] + ([f"• … and {len(lines) - cap} more"] if len(lines) > cap else [])
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Critical)
        box.setWindowTitle("Can't import — fix the file first")
        box.setText(f"{len(problems)} problem(s) found in this file:")
        box.setInformativeText(
            "\n".join(shown) + "\n\nNothing was imported. Fix the Excel file and import it "
            "again. Column A must be filled on every row with one consistent school, every "
            "dropdown column must use a value from its list, and each row's Amount must "
            "equal unit price x quantity x rate.")
        box.addButton("OK", QMessageBox.AcceptRole)
        box.exec()
        return False

    def on_import(self):
        if not self._path:
            return
        if self._kind == "bpasx_many":
            self._import_many()
            return
        if self._kind == "bpasx":
            self._import_bpasx()
            return
        school_id = self.school_combo.currentData()
        if school_id is None:
            QMessageBox.warning(self, "School Required", "Select a school first.")
            return
        total = _amount(self.total_edit.text())
        gad = _amount(self.gad_edit.text())
        if total is None or gad is None:
            QMessageBox.warning(self, "Invalid Number",
                                "Total Allotment and GAD Allotment must be numbers.")
            return

        if not self._check_excel():
            return

        try:
            result = import_excel.import_file(self._path, "")
        except import_excel.ImportBlocked:
            self._check_excel()          # shows the problems; nothing was imported
            return
        except Exception as exc:
            QMessageBox.critical(self, "Import Failed", f"Could not import file:\n{exc}")
            return

        school = next(s for s in db.list_schools() if s["id"] == school_id)
        db.set_batch_plan(
            result.batch_id,
            school_name=school["name"], school_id=school["school_id"],
            iu_code=school["iu_code"], level_type=school["level_type"],
            level=school["level"], school_head=self.head_edit.text().strip(),
            total_allotment=total, gad_allotment=gad,
        )
        db.set_active_batch(result.batch_id)

        if result.skipped_rows:
            n = len(result.skipped_rows)
            preview = "\n".join(f"  Row {rn}: {why}"
                                for rn, why in result.skipped_rows[:15])
            QMessageBox.warning(
                self, "Imported with skipped rows",
                f"Imported {result.imported_count} row(s); skipped {n}.\n\n{preview}"
                + ("\n  ..." if n > 15 else ""))

        if result.warnings:
            lines = ["• " + import_excel.describe(p) for p in result.warnings]
            more = "\n  … and %d more" % (len(lines) - 15) if len(lines) > 15 else ""
            QMessageBox.information(
                self, "Imported with warnings",
                f"Imported {result.imported_count} row(s). These rows were imported as they "
                "are and show red in Records until fixed:\n\n" + "\n".join(lines[:15]) + more)

        self.import_btn.setEnabled(False)
        self.imported.emit()
        self.accept()
