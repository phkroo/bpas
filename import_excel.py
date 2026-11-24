"""Import a BPAS Excel file (strict fixed template, columns A-N) into the database.

Problems come in two kinds:
- "error"   -> blocks the import (nothing is written)
- "warning" -> shown to the user, but the import still goes ahead:
                * GAD Category empty on a GAD-program row  (row is imported as is)
                * a row with no Item Description           (row is imported with "Blank")
"""

import os
from dataclasses import dataclass, field as dc_field

import warnings

import openpyxl
# the files we read are never re-saved, so dropping their extension-based dropdowns is harmless
warnings.filterwarnings("ignore", message="Data Validation extension", category=UserWarning)

import db

# Fixed column order matching the BPAS template (1-indexed, columns A-N)
COLUMNS = [
    "category_uacs_school",   # A
    "pap_name",                # B
    "general_description",     # C
    "item_description",        # D
    "gad_category",             # E
    "accounting_title",         # F
    "mode_of_procurement",       # G
    "app_for",                    # H
    "app_cs",                      # I
    "unit_price",                   # J
    "qty",                           # K
    "unit",                           # L
    "month",                          # M
    "amount",                          # N
]

FIRST_DATA_ROW = 2
REQUIRED_TEXT_FIELDS = ["item_description"]

# Row-level reasons from _parse() that only warn: the row is still imported.
BLANK_ITEM_TEXT = "Blank"
SOFT_ROW_REASONS = ("Item Description is empty",)


@dataclass
class Problem:
    kind: str          # "blank_a" | "mixed_a" | "unknown_school" | "not_in_list" | "row_error" | "gad_missing" | ...
    field: str         # COLUMNS key ("category_uacs_school", "unit", ...)
    value: str         # offending value ("" for blank)
    rows: list[int]    # excel row numbers
    severity: str = "error"     # "error" blocks the import, "warning" does not


@dataclass
class ImportResult:
    batch_id: int
    imported_count: int
    skipped_rows: list[tuple[int, str]]  # (excel_row_number, reason)
    warnings: list = dc_field(default_factory=list)   # list[Problem] shown after import


def describe(p: Problem) -> str:
    """Plain-language one-liner for a Problem (use it to show warnings)."""
    rows = ", ".join(str(r) for r in p.rows)
    if p.kind == "gad_missing":
        return f"GAD Category (column E) is empty on a GAD-program row — rows {rows}"
    if p.kind == "gad_not_allowed":
        return f"GAD Category (column E) is filled but PAP Name is not the GAD program — rows {rows}"
    if p.kind == "row_error":
        return f"Row {rows}: {p.value}"
    where = f" ({p.field})" if p.field else ""
    return f"{p.kind}{where} {p.value} — rows {rows}".replace("  ", " ")


def detect_school_text(path: str) -> str:
    """First non-empty column-A value in the data rows (the Category/UACS/School cell)."""
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    try:
        ws = wb.active
        for row in ws.iter_rows(min_row=FIRST_DATA_ROW, max_col=1, values_only=True):
            val = row[0]
            if val is not None and str(val).strip() and str(val).strip().lower() != "total":
                return str(val).strip()
        return ""
    finally:
        wb.close()


# dropdown columns re-checked at import (blank is allowed for all of these).
# Unit is excluded on purpose — any typed value is allowed (see xlsx_lists.SOFT_FIELDS).
DROPDOWN_FIELDS = ["pap_name", "gad_category", "accounting_title", "mode_of_procurement",
                   "app_for", "app_cs", "month"]


def check_file(path: str) -> list[Problem]:
    """Strict pre-import check, no DB writes. Only rows that would actually be
    imported (they have an Item Description) are looked at, so a signature block
    or notes below the data don't count.

    - column A must be filled on every such row, hold ONE value, and be a known school
    - every dropdown column must hold a value from its list (blank is fine);
      "the list" = the template dropdowns plus whatever the database already uses
      (so the app's own exports can always be re-imported). Case-insensitive.
    - GAD Category empty on a GAD row is only a WARNING (the row still imports).
    - a row with numbers but no Item Description is checked too (it imports as "Blank")."""
    import xlsx_lists

    extra = {f: db.distinct_values(f) for f in DROPDOWN_FIELDS}
    extra["category_uacs_school"] = db.distinct_values("category_uacs_school")
    allowed = {f: {v.lower() for v in vals}
               for f, vals in xlsx_lists.allowed_values(extra).items()}

    idx = {f: COLUMNS.index(f) for f in ["category_uacs_school", "item_description"]
           + DROPDOWN_FIELDS}

    gad_missing: list[int] = []
    gad_not_allowed: list[int] = []
    blank_a: list[int] = []
    a_values: dict[str, list[int]] = {}
    bad: dict[tuple[str, str], list[int]] = {}

    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    try:
        # The file's own hidden 'Lists' sheet (written by the app's exports and the
        # APP-CSE download) also counts as "the list", so e.g. a PS-DBM catalogue unit
        # the app itself put in the dropdown never blocks re-import. Values typed or
        # pasted into cells are still checked against it.
        if "Lists" in wb.sheetnames:
            grid = list(wb["Lists"].iter_rows(values_only=True))
            for ci, head in enumerate(grid[0] if grid else ()):
                field = str(head).strip() if head else ""
                if field in allowed:
                    allowed[field] |= {str(r[ci]).strip().lower()
                                       for r in grid[1:] if ci < len(r) and r[ci]}
        for row_no, row in enumerate(
                wb.active.iter_rows(min_row=FIRST_DATA_ROW, values_only=True),
                start=FIRST_DATA_ROW):
            if row is None:
                continue
            row = list(row) + [None] * (len(COLUMNS) - len(row))
            if _is_total_row(row):
                continue
            if not _clean_text(row[idx["item_description"]]):
                # no item text: still a data row if it carries numbers (imported as "Blank");
                # otherwise a note / signature line, not importable
                if not (_to_float(row[COLUMNS.index("unit_price")])
                        or _to_float(row[COLUMNS.index("qty")])
                        or _to_float(row[COLUMNS.index("amount")])):
                    continue
            a = _clean_text(row[idx["category_uacs_school"]])
            if not a:
                blank_a.append(row_no)
            else:
                a_values.setdefault(a, []).append(row_no)
            for f in DROPDOWN_FIELDS:
                v = _clean_text(row[idx[f]])
                if v and v.lower() not in allowed.get(f, set()):
                    bad.setdefault((f, v), []).append(row_no)
            # GAD Category belongs to the GAD program only (Excel's validation can be
            # bypassed by pasting, so it is enforced here too)
            is_gad = _clean_text(row[idx["pap_name"]]).lower() == xlsx_lists.GAD_PAP.lower()
            has_cat = bool(_clean_text(row[idx["gad_category"]]))
            if is_gad and not has_cat:
                gad_missing.append(row_no)
            elif has_cat and not is_gad:
                gad_not_allowed.append(row_no)
    finally:
        wb.close()

    problems: list[Problem] = []
    if blank_a:
        problems.append(Problem("blank_a", "category_uacs_school", "", blank_a))
    if len(a_values) > 1:
        for v, rows in sorted(a_values.items(), key=lambda kv: -len(kv[1])):
            problems.append(Problem("mixed_a", "category_uacs_school", v, rows))
    for v, rows in a_values.items():
        # only the school list decides: not the file's own hidden Lists sheet or past data
        if db.match_school(v) is None:
            problems.append(Problem("unknown_school", "category_uacs_school", v, rows))
    for (f, v), rows in sorted(bad.items(), key=lambda kv: (kv[0][0], -len(kv[1]))):
        problems.append(Problem("not_in_list", f, v, rows))
    if gad_missing:
        # warning only: the rows are imported with GAD Category left empty
        problems.append(Problem("gad_missing", "gad_category", "", gad_missing,
                                severity="warning"))
    if gad_not_allowed:
        problems.append(Problem("gad_not_allowed", "gad_category", "", gad_not_allowed,
                                severity="warning"))
    return problems


def _to_float(value):
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _clean_text(value):
    if value is None:
        return ""
    return str(value).strip()


def _file_rate(wb):
    """The Amount multiplier stored in the file (defined name BPAS_RATE, 1.10 = +10%),
    or None for a file that doesn't carry one (older templates, hand-made files)."""
    import xlsx_lists
    try:
        name = wb.defined_names.get(xlsx_lists.RATE_NAME)
        return float(name.attr_text) if name is not None else None
    except (TypeError, ValueError, AttributeError):
        return None


def _is_total_row(values) -> bool:
    """A 'Total' row (older files): 'Total' in column A and no item description."""
    import xlsx_lists
    return (_clean_text(values[0]).lower() == xlsx_lists.TOTAL_LABEL.lower()
            and not _clean_text(values[COLUMNS.index("item_description")]))


def _is_all_months(month) -> bool:
    import xlsx_lists
    return (month or "").strip().lower() == xlsx_lists.ALL_MONTHS.lower()


def _parse(path: str):
    """Read every importable row (no database writes). Returns (rows, problems, rate): rows are
    ready to insert, problems are (excel_row, reason) for every row that is not acceptable."""
    import validation
    canon = validation.canon_lists(allow_all_months=True)
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb.active
    rate = _file_rate(wb)

    rows_to_insert = []
    skipped_rows = []

    for row_idx, row in enumerate(
        ws.iter_rows(min_row=FIRST_DATA_ROW, values_only=True), start=FIRST_DATA_ROW
    ):
        # Skip fully blank rows
        if row is None or all(cell is None or str(cell).strip() == "" for cell in row):
            continue

        values = list(row) + [None] * (len(COLUMNS) - len(row))
        if _is_total_row(values):
            continue
        record = dict(zip(COLUMNS, values[: len(COLUMNS)]))

        for key in ["category_uacs_school", "pap_name", "general_description",
                    "item_description", "gad_category", "accounting_title",
                    "mode_of_procurement", "app_for", "app_cs", "unit", "month"]:
            record[key] = _clean_text(record.get(key))

        record["unit_price"] = _to_float(record.get("unit_price"))
        record["qty"] = _to_float(record.get("qty"))
        # Amount may carry a provision rate (unit_price x qty x rate) that isn't
        # otherwise stored anywhere, so unit_price x qty alone would silently drop it.
        # BPAS files hold that rate (BPAS_RATE) and Amount is not protected, so Amount
        # is re-computed below and a row whose Amount was typed/pasted over is rejected.
        # Files without a rate (older templates) keep the old behaviour: Amount trusted.
        amount = _to_float(record.pop("amount", None))

        # a note or signature line under the table: no item, no numbers -> not a data row
        # (an Amount formula in an unused row shows 0, which counts as empty too)
        if (not record["item_description"] and not record["unit_price"]
                and not record["qty"] and not amount):
            continue

        if not record["item_description"]:
            # not skipped: imported with "Blank" and reported as a warning
            record["item_description"] = BLANK_ITEM_TEXT
            skipped_rows.append((row_idx, f"Item Description is empty — imported as “{BLANK_ITEM_TEXT}”"))
        if record["unit_price"] is None:
            skipped_rows.append((row_idx, "Unit Price is not a valid number (if it is a formula, open the file in Excel and save it first)"))
            continue
        if record["qty"] is None:
            skipped_rows.append((row_idx, "Quantity is not a valid number"))
            continue

        if record["unit_price"] <= 0:
            skipped_rows.append((row_idx, "Unit Price must be greater than 0"))
            continue
        if record["qty"] <= 0:
            skipped_rows.append((row_idx, "Quantity must be greater than 0"))
            continue

        # store the list's own spelling ("office supplies expenses" -> "Office Supplies Expenses")
        for key in ("pap_name", "gad_category", "accounting_title", "mode_of_procurement",
                    "app_for", "app_cs"):
            record[key] = validation.canonical(key, record[key], canon)
        if not _is_all_months(record["month"]):
            record["month"] = validation.canonical("month", record["month"], canon)

        all_months = _is_all_months(record["month"])
        if all_months and not (record["unit"].strip().lower() == "month"
                               and record["qty"] == 12):
            skipped_rows.append((row_idx, '"All Months" only works when the Unit is "Month" '
                                          "and the Quantity is exactly 12"))
            continue

        # unrounded price: it may be a formula like =6000/1.1 whose exact value is what
        # makes Amount come out whole
        expected = (db.money(record["unit_price"], record["qty"], rate)
                    if rate is not None else None)
        if expected is not None and amount is not None and round(abs(amount - expected), 2) > 0.01:   # a 1-centavo rounding gap is fine
            skipped_rows.append((row_idx, f"Amount {amount:,.2f} does not match unit price x "
                                          f"qty x rate ({expected:,.2f})"))
            continue

        record["unit_price"] = round(record["unit_price"], 2)
        record["qty"] = round(record["qty"], 2)

        if amount is not None:
            record["total_amount"] = round(amount, 2)
        elif expected is not None:
            record["total_amount"] = expected
        else:
            record["total_amount"] = round(record["unit_price"] * record["qty"], 2)
        if all_months:
            # 12 months of a monthly price: this row's Amount is the whole year, so it is
            # spread over Jan-Dec as 12 rows of Qty 1 at the same unit price. Leftover
            # centavos go to December so the year still adds up exactly.
            share = round(record["total_amount"] / 12, 2)
            for i, m in enumerate(db.MONTH_ORDER):
                amt = share if i < 11 else round(record["total_amount"] - share * 11, 2)
                rows_to_insert.append({**record, "month": m, "qty": 1.0,
                                       "unit": "Month", "total_amount": amt})
        else:
            rows_to_insert.append(record)

    return rows_to_insert, skipped_rows, rate


class ImportBlocked(Exception):
    """The file has problems; nothing was imported. `.problems` lists every blocking one."""
    def __init__(self, problems):
        super().__init__(f"{len(problems)} problem(s) in the file")
        self.problems = problems


def _validate(path: str):
    """(problems, rows, rate): the whole-file checks plus the row-by-row checks, together.
    `problems` holds both errors and warnings; look at each Problem's `.severity`."""
    problems = list(check_file(path))
    rows, skipped, rate = _parse(path)
    for row_no, why in skipped:
        soft = why.startswith(SOFT_ROW_REASONS)
        if soft:
            problems.append(Problem("row_error", "", why, [row_no], severity="warning"))
        else:
            problems.append(Problem("row_error", "", why, [row_no]))
    return problems, rows, rate


def validate_file(path: str) -> list:
    """Every BLOCKING problem found in the file (empty = it can be imported). Writes nothing.
    Warnings do not count here; use validate_file_all() to see them too."""
    return [p for p in _validate(path)[0] if p.severity == "error"]


def validate_file_all(path: str) -> list:
    """Errors and warnings together. Writes nothing."""
    return _validate(path)[0]


def import_file(path: str, label: str = "") -> ImportResult:
    """Import the file unless it has a blocking problem (then raise ImportBlocked and
    write nothing). Warnings are returned on the result so they can be shown afterwards."""
    problems, rows_to_insert, rate = _validate(path)
    errors = [p for p in problems if p.severity == "error"]
    warnings = [p for p in problems if p.severity == "warning"]
    if errors:
        raise ImportBlocked(errors)

    file_name = os.path.basename(path)
    batch_id = db.create_batch(file_name, label)
    if rows_to_insert:
        db.insert_items(batch_id, rows_to_insert)
    db.set_batch_plan(batch_id, provision_rate=rate)

    return ImportResult(batch_id=batch_id, imported_count=len(rows_to_insert),
                        skipped_rows=[], warnings=warnings)