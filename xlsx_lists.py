"""Dropdown (data-validation) lists for the 14-column BPAS xlsx template.

Used by both the APP-CSE download (appcse_convert) and Records -> Export to Excel
(export_excel). Lists are written to a hidden 'Lists' sheet the validations reference.
"""

import os

import openpyxl
from openpyxl.comments import Comment
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.workbook.defined_name import DefinedName
from openpyxl.worksheet.datavalidation import DataValidation

import db
from export_excel import FIELDS, HEADERS

MIN_TABLE_ROWS = 1000                 # blank data rows in a fresh template
LAST_ROW = MIN_TABLE_ROWS + 1
# Month choice meaning "this same entry, every month" (imported as 12 monthly rows).
ALL_MONTHS = "All Months"
RATE_NAME = "BPAS_RATE"             # defined name holding the Amount multiplier (1.10 = +10%)
TOTAL_LABEL = "Total"               # column A of the totals row (files from the earlier build)
GAD_PAP = "Gender and Development (GAD) Program"   # the only PAP NAME that takes a GAD Category
MONTHS_LIST_NAME = "BPAS_MONTHS"            # January-December
MONTHS_ALL_LIST_NAME = "BPAS_MONTHS_ALL"    # January-December + All Months
GAD_LIST_NAME = "BPAS_GAD_LIST"
NO_LIST_NAME = "BPAS_NO_LIST"
AMOUNT_COL = FIELDS.index("total_amount") + 1   # column N

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
        "mode_of_procurement": db.list_procurement_modes(),
        "app_for": ["CSE", "NON CSE"],
        "app_cs": ["PART I", "PART II", "OTHER ITEMS"],
        "unit": db.list_units(),
        "month": list(db.MONTH_ORDER) + [ALL_MONTHS],
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


def table_last_row(n_rows: int) -> int:
    """Last data row for `n_rows` records (at least MIN_TABLE_ROWS)."""
    return max(n_rows, MIN_TABLE_ROWS) + 1


def add_amount_table(wb, ws, last_row: int, multiplier: float = 1.0):
    """Write the Amount formula (column N) on every data row down to `last_row`, plus a
    header filter, frozen header row and light row banding.

    This is deliberately NOT an Excel Table: typing a formula (e.g. =500/1.1 in Unit
    Price) into a Table column makes Excel copy it down the whole column ("calculated
    column"), which filled all 1000 rows. A plain range keeps each formula in its own
    cell. Amount is not protected; instead the importer re-computes Amount from Unit
    Price x Qty x the rate stored in the file and rejects mismatches.

    `multiplier` (e.g. 1.10 for a 10% provision rate) is stored once as the defined
    name BPAS_RATE, used by the formula and read back by the importer. It applies
    uniformly to every row. A line item that needs an exact fixed amount (e.g. a flat
    monthly allowance) is handled by dividing that amount by the multiplier when
    entering Unit Price (type a formula like =6000/1.1, which Unit Price validation
    allows), not by exempting the row."""
    wb.defined_names[RATE_NAME] = DefinedName(RATE_NAME, attr_text=f"{multiplier:.10g}")

    price_col = get_column_letter(FIELDS.index("unit_price") + 1)
    qty_col = get_column_letter(FIELDS.index("qty") + 1)
    for r in range(2, last_row + 1):
        cell = ws.cell(row=r, column=AMOUNT_COL)
        cell.value = (f'=IF(OR({price_col}{r}="",{qty_col}{r}=""),"",'
                      f'ROUND({price_col}{r}*{qty_col}{r}*{RATE_NAME},2))')
        cell.number_format = ACCOUNTING_FMT

    last_col = get_column_letter(len(FIELDS))
    for c in range(1, len(FIELDS) + 1):          # header labels centered (wrapped if long)
        ws.cell(row=1, column=c).alignment = Alignment(
            horizontal="center", vertical="center", wrap_text=True)
    month_header = ws.cell(row=1, column=FIELDS.index("month") + 1)
    month_header.comment = Comment(
        'Pick a month. "All Months" appears only when the Unit is "Month" and the Quantity '
        "is 12: that one row is then imported as 12 monthly rows (Qty 1 each). "
        "Enter the Unit and Quantity before the Month.", "BPAS", width=300, height=110)
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{last_col}{last_row}"
    ws.conditional_formatting.add(
        f"A2:{last_col}{last_row}",
        FormulaRule(formula=["MOD(ROW(),2)=0"], fill=PatternFill("solid", bgColor="F2F5F4")))


def apply_number_rules(ws, last_row: int = LAST_ROW):
    """Unit Price / Quantity must be numbers, not negative, at most 2 decimals.
    Amount (column N) is excluded — it's a calculated column, not user-entered."""
    for field in (f for f in NUMBER_FIELDS if f != "total_amount"):
        col = openpyxl.utils.get_column_letter(FIELDS.index(field) + 1)
        dv = DataValidation(
            type="custom",
            formula1=(f"AND(ISNUMBER({col}2),{col}2>=0,ROUND({col}2,2)={col}2)"
                      if field != "unit_price" else
                      f"AND(ISNUMBER({col}2),{col}2>=0,OR(ISFORMULA({col}2),ROUND({col}2,2)={col}2))"),
            allow_blank=True,
        )
        dv.showErrorMessage = True
        dv.errorStyle = "stop"
        dv.errorTitle = "Not a valid number"
        dv.error = ("Enter a number (0 or more) with at most 2 decimal places."
                    + (" A formula such as =6000/1.1 is also allowed." if field == "unit_price" else ""))
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
        if field == "month":      # "All Months" always last, so the plain list is all but it
            values = [v for v in values if v != ALL_MONTHS] + [ALL_MONTHS]
        lcol = openpyxl.utils.get_column_letter(i + 1)
        lw.cell(row=1, column=i + 1, value=field)
        for r, v in enumerate(values, start=2):
            lw.cell(row=r, column=i + 1, value=v)

        col = openpyxl.utils.get_column_letter(FIELDS.index(field) + 1)
        list_ref = f"Lists!${lcol}$2:${lcol}${1 + len(values)}"
        allow_blank = True
        if field == "gad_category":
            # GAD Category is only for the GAD program: the dropdown lists the categories
            # on those rows and an empty list everywhere else, so typing is rejected there.
            # Ignore-blank must be off, or Excel accepts anything against an empty list.
            none_col = openpyxl.utils.get_column_letter(len(sources) + 2)    # never written to
            wb.defined_names[GAD_LIST_NAME] = DefinedName(GAD_LIST_NAME, attr_text=list_ref)
            wb.defined_names[NO_LIST_NAME] = DefinedName(
                NO_LIST_NAME, attr_text=f"Lists!${none_col}$2")
            pap = openpyxl.utils.get_column_letter(FIELDS.index("pap_name") + 1)
            list_ref = f'IF(${pap}2="{GAD_PAP}",{GAD_LIST_NAME},{NO_LIST_NAME})'
            allow_blank = False
            ws.conditional_formatting.add(
                f"{col}2:{col}{last_row}",
                FormulaRule(formula=[f'AND(${pap}2="{GAD_PAP}",${col}2="")'],
                            fill=PatternFill(start_color="FFC7CE", end_color="FFC7CE",
                                             fill_type="solid")))
        if field == "month":
            # "All Months" is offered only on a row whose Unit is "Month" and Quantity is 12
            plain_ref = f"Lists!${lcol}$2:${lcol}${len(values)}"
            wb.defined_names[MONTHS_LIST_NAME] = DefinedName(MONTHS_LIST_NAME, attr_text=plain_ref)
            wb.defined_names[MONTHS_ALL_LIST_NAME] = DefinedName(
                MONTHS_ALL_LIST_NAME, attr_text=list_ref)
            unit = openpyxl.utils.get_column_letter(FIELDS.index("unit") + 1)
            qty = openpyxl.utils.get_column_letter(FIELDS.index("qty") + 1)
            list_ref = (f'IF(AND(LOWER(TRIM(${unit}2))="month",${qty}2=12),'
                        f'{MONTHS_ALL_LIST_NAME},{MONTHS_LIST_NAME})')
        dv = DataValidation(type="list", formula1=list_ref, allow_blank=allow_blank)
        if field in SOFT_FIELDS:
            dv.showErrorMessage = False       # soft: typing / pasting still allowed
        else:
            dv.showErrorMessage = True        # strict: anything off-list is rejected
            dv.errorStyle = "stop"
            dv.errorTitle = "Not in the list"
            dv.error = ("GAD Category is only for the Gender and Development (GAD) Program. "
                        "Otherwise leave it blank." if field == "gad_category"
                        else "Pick a value from the dropdown list.")
        dv.add(f"{col}2:{col}{last_row}")
        ws.add_data_validation(dv)
