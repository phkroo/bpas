"""Dropdown (data-validation) lists for the 14-column BPAS xlsx template.

Used by both the APP-CSE download (appcse_convert) and Records -> Export to Excel
(export_excel). Lists are written to a hidden 'Lists' sheet the validations reference.
"""

import os

import openpyxl
from openpyxl.worksheet.datavalidation import DataValidation

import db
from export_excel import FIELDS

LAST_ROW = 1000

# Unit accepts a suggestion dropdown but any typed value is allowed — units are too
# varied (pcs, rope by the meter, pax, box, lot, ...) to force onto a fixed list.
SOFT_FIELDS = {"unit"}

# Accounting number format without a currency sign: thousands separators, 2 decimals,
# negatives in parentheses, zero shown as "-".
ACCOUNTING_FMT = r'_(* #,##0.00_);_(* \(#,##0.00\);_(* "-"??_);_(@_)'
NUMBER_FIELDS = ("unit_price", "qty", "total_amount")     # columns J, K, N


def cap_first(value) -> str:
    """'pcs' -> 'Pcs', 'month' -> 'Month'. Only the first letter changes, so
    'kg' -> 'Kg' but an already-capitalised 'PCS' / 'Ream' is left alone."""
    s = str(value).strip() if value is not None else ""
    return s[:1].upper() + s[1:]


def money(value):
    """A cell number: float rounded to 2 decimals (None stays None)."""
    if value is None or value == "":
        return None
    return round(float(value), 2)


def _file_lines(name):
    path = db.bundled_path("data", name)
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [ln.strip() for ln in f if ln.strip()]


def list_sources() -> dict:
    """field -> list of allowed values."""
    schools = [f"{s['level_type']} {s['iu_code']} {s['school_id']} {s['name']}"
               for s in db.list_schools()]
    accounts = [r["title"] for r in db.list_mooe_accounts()]
    return {
        "category_uacs_school": schools,
        "pap_name": _file_lines("pap_names.txt"),
        "gad_category": _file_lines("gad_categories.txt"),
        "accounting_title": accounts,
        "mode_of_procurement": _file_lines("procurement_modes.txt"),
        "app_for": ["CSE", "NON CSE"],
        "app_cs": ["PART I", "PART II", "OTHER ITEMS"],
        "unit": _file_lines("units.txt"),
        "month": list(db.MONTH_ORDER),
    }


def allowed_values(extra: dict | None = None) -> dict:
    """field -> allowed values: the dropdown lists, plus anything `extra` says
    the data being written already uses (so a file never contradicts itself)."""
    out = {f: list(v) for f, v in list_sources().items()}
    for field, values in (extra or {}).items():
        have = out.setdefault(field, [])
        seen = {x.lower() for x in have}
        for v in values:
            v = (str(v).strip() if v is not None else "")
            if v and v.lower() not in seen:
                have.append(v)
                seen.add(v.lower())
    return out


def data_values(rows, fields=None) -> dict:
    """Distinct non-blank values per dropdown field found in `rows`
    (dict-like records), for use as `extra`."""
    fields = fields or list(list_sources().keys())
    out = {f: [] for f in fields}
    seen = {f: set() for f in fields}
    for r in rows:
        for f in fields:
            try:
                v = r[f]
            except (KeyError, IndexError):
                continue
            v = cap_first(v) if f == "unit" else (str(v).strip() if v is not None else "")
            if v and v not in seen[f]:
                seen[f].add(v)
                out[f].append(v)
    return out


def format_number_columns(ws, last_row: int = LAST_ROW):
    """Unit Price / Quantity / Amount: accounting format (no currency sign), 2 decimals,
    for every row down to `last_row` so rows typed later look the same."""
    for field in NUMBER_FIELDS:
        col = FIELDS.index(field) + 1
        for r in range(2, last_row + 1):
            ws.cell(row=r, column=col).number_format = ACCOUNTING_FMT


def apply_number_rules(ws, last_row: int = LAST_ROW):
    """Unit Price / Quantity / Amount must be numbers, not negative, at most 2 decimals."""
    for field in NUMBER_FIELDS:
        col = openpyxl.utils.get_column_letter(FIELDS.index(field) + 1)
        dv = DataValidation(
            type="custom",
            formula1=f"AND(ISNUMBER({col}2),{col}2>=0,ROUND({col}2,2)={col}2)",
            allow_blank=True,
        )
        dv.showErrorMessage = True
        dv.errorStyle = "stop"
        dv.errorTitle = "Not a valid number"
        dv.error = "Enter a number (0 or more) with at most 2 decimal places."
        dv.add(f"{col}2:{col}{last_row}")
        ws.add_data_validation(dv)


def apply_validations(wb, ws, last_row: int = LAST_ROW, extra: dict | None = None):
    """Strict dropdowns (typing a value that isn't in the list is rejected) and
    strict, accounting-formatted number columns."""
    format_number_columns(ws, last_row)
    apply_number_rules(ws, last_row)
    sources = {f: v for f, v in allowed_values(extra).items() if v}
    if not sources:
        return

    lw = wb.create_sheet("Lists")
    lw.sheet_state = "hidden"

    for i, (field, values) in enumerate(sources.items()):
        lcol = openpyxl.utils.get_column_letter(i + 1)
        lw.cell(row=1, column=i + 1, value=field)
        for r, v in enumerate(values, start=2):
            lw.cell(row=r, column=i + 1, value=v)

        col = openpyxl.utils.get_column_letter(FIELDS.index(field) + 1)
        dv = DataValidation(
            type="list",
            formula1=f"Lists!${lcol}$2:${lcol}${1 + len(values)}",
            allow_blank=True,
        )
        if field in SOFT_FIELDS:
            dv.showErrorMessage = False       # soft: typing / pasting still allowed
        else:
            dv.showErrorMessage = True        # strict: anything off-list is rejected
            dv.errorStyle = "stop"
            dv.errorTitle = "Not in the list"
            dv.error = "Pick a value from the dropdown list."
        dv.add(f"{col}2:{col}{last_row}")
        ws.add_data_validation(dv)
