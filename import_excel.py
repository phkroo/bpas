"""Import a BPAS Excel file (strict fixed template, columns A-L) into the database."""

import os
from dataclasses import dataclass

import openpyxl

import db

# Fixed column order matching the BPAS template (1-indexed, columns A-L)
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

HEADER_ROW = 1
FIRST_DATA_ROW = 2
REQUIRED_TEXT_FIELDS = ["item_description"]


@dataclass
class ImportResult:
    batch_id: int
    imported_count: int
    skipped_rows: list[tuple[int, str]]  # (excel_row_number, reason)


def detect_school_text(path: str) -> str:
    """First non-empty column-A value in the data rows (the Category/UACS/School cell)."""
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    try:
        ws = wb.active
        for row in ws.iter_rows(min_row=FIRST_DATA_ROW, max_col=1, values_only=True):
            val = row[0]
            if val is not None and str(val).strip():
                return str(val).strip()
        return ""
    finally:
        wb.close()


def find_unknown_titles(path: str) -> dict[str, int]:
    """Accounting Titles used in the file that are not in the Account Codes list
    (Setup), as {title: number of rows}. Blank titles are not counted."""
    known = {r["title"] for r in db.list_mooe_accounts()}
    idx = COLUMNS.index("accounting_title")
    counts: dict[str, int] = {}
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    try:
        for row in wb.active.iter_rows(min_row=FIRST_DATA_ROW, values_only=True):
            if row is None or len(row) <= idx:
                continue
            title = _clean_text(row[idx])
            if title and title not in known:
                counts[title] = counts.get(title, 0) + 1
    finally:
        wb.close()
    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))


@dataclass
class Problem:
    kind: str          # "blank_a" | "mixed_a" | "unknown_school" | "not_in_list"
    field: str         # COLUMNS key ("category_uacs_school", "unit", ...)
    value: str         # offending value ("" for blank)
    rows: list[int]    # excel row numbers


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
      (so the app's own exports can always be re-imported). Case-insensitive."""
    import xlsx_lists

    extra = {f: db.distinct_values(f) for f in DROPDOWN_FIELDS}
    extra["category_uacs_school"] = db.distinct_values("category_uacs_school")
    allowed = {f: {v.lower() for v in vals}
               for f, vals in xlsx_lists.allowed_values(extra).items()}

    idx = {f: COLUMNS.index(f) for f in ["category_uacs_school", "item_description"]
           + DROPDOWN_FIELDS}

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
            if not _clean_text(row[idx["item_description"]]):
                continue                       # not an importable row
            a = _clean_text(row[idx["category_uacs_school"]])
            if not a:
                blank_a.append(row_no)
            else:
                a_values.setdefault(a, []).append(row_no)
            for f in DROPDOWN_FIELDS:
                v = _clean_text(row[idx[f]])
                if v and v.lower() not in allowed.get(f, set()):
                    bad.setdefault((f, v), []).append(row_no)
    finally:
        wb.close()

    problems: list[Problem] = []
    if blank_a:
        problems.append(Problem("blank_a", "category_uacs_school", "", blank_a))
    if len(a_values) > 1:
        for v, rows in sorted(a_values.items(), key=lambda kv: -len(kv[1])):
            problems.append(Problem("mixed_a", "category_uacs_school", v, rows))
    for v, rows in a_values.items():
        if v.lower() not in allowed["category_uacs_school"] and db.match_school(v) is None:
            problems.append(Problem("unknown_school", "category_uacs_school", v, rows))
    for (f, v), rows in sorted(bad.items(), key=lambda kv: (kv[0][0], -len(kv[1]))):
        problems.append(Problem("not_in_list", f, v, rows))
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


def import_file(path: str, label: str = "") -> ImportResult:
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb.active

    rows_to_insert = []
    skipped_rows = []

    for row_idx, row in enumerate(
        ws.iter_rows(min_row=FIRST_DATA_ROW, values_only=True), start=FIRST_DATA_ROW
    ):
        # Skip fully blank rows
        if row is None or all(cell is None or str(cell).strip() == "" for cell in row):
            continue

        values = list(row) + [None] * (len(COLUMNS) - len(row))
        record = dict(zip(COLUMNS, values[: len(COLUMNS)]))

        for key in ["category_uacs_school", "pap_name", "general_description",
                    "item_description", "gad_category", "accounting_title",
                    "mode_of_procurement", "app_for", "app_cs", "unit", "month"]:
            record[key] = _clean_text(record.get(key))

        record["unit_price"] = _to_float(record.get("unit_price"))
        record["qty"] = _to_float(record.get("qty"))
        amount = _to_float(record.pop("amount", None))

        missing = [f for f in REQUIRED_TEXT_FIELDS if not record.get(f)]
        if missing:
            skipped_rows.append((row_idx, f"missing required field(s): {', '.join(missing)}"))
            continue
        if record["unit_price"] is None:
            skipped_rows.append((row_idx, "unit_price is not a valid number"))
            continue
        if record["qty"] is None:
            skipped_rows.append((row_idx, "qty is not a valid number"))
            continue

        record["unit_price"] = round(record["unit_price"], 2)
        record["qty"] = round(record["qty"], 2)

        if amount is not None:
            record["total_amount"] = round(amount, 2)
        else:
            record["total_amount"] = round(record["unit_price"] * record["qty"], 2)
        rows_to_insert.append(record)

    file_name = os.path.basename(path)
    batch_id = db.create_batch(file_name, label)
    if rows_to_insert:
        db.insert_items(batch_id, rows_to_insert)

    return ImportResult(
        batch_id=batch_id,
        imported_count=len(rows_to_insert),
        skipped_rows=skipped_rows,
    )
