"""Export currently filtered BPAS records back to an .xlsx file."""

import openpyxl
from openpyxl.styles import Font

HEADERS = [
    "CATEGORY/UACS CODE/SCHOOL ID/SCHOOL NAME",
    "PAP NAME",
    "GENERAL DESCRIPTION",
    "ITEM DESCRIPTION",
    "GENDER AND DEVELOPMENT CATEGORY",
    "ACCOUNTING TITLE",
    "MODE OF PROCUREMENT",
    "APP FORM",
    "APP CSE",
    "UNIT PRICE",
    "QUANTITY",
    "UNIT",
    "MONTH",
    "AMOUNT",
]

FIELDS = [
    "category_uacs_school", "pap_name", "general_description", "item_description",
    "gad_category", "accounting_title", "mode_of_procurement", "app_for", "app_cs",
    "unit_price", "qty", "unit", "month", "total_amount",
]


def export_items(rows, path: str, signatories=None, school_info=None):
    """rows: iterable of sqlite3.Row (or dict-like) records from db.query_items()."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "BPAS"

    rows = list(rows)

    for col_idx, header in enumerate(HEADERS, start=1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.font = Font(bold=True)

    import xlsx_lists
    for row_idx, item in enumerate(rows, start=2):
        for col_idx, field in enumerate(FIELDS, start=1):
            value = item[field]
            if field in xlsx_lists.NUMBER_FIELDS:
                value = xlsx_lists.money(value)         # real number, 2 decimals
            elif field == "unit":
                value = xlsx_lists.cap_first(value)     # "pcs" -> "Pcs"
            ws.cell(row=row_idx, column=col_idx, value=value)

    for col_idx in range(1, len(HEADERS) + 1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(col_idx)].width = 22

    _write_signature_block(ws, len(rows) + 2, signatories or [], school_info or {})

    xlsx_lists.apply_validations(
        wb, ws, last_row=max(xlsx_lists.LAST_ROW, len(rows) + 1),
        extra=xlsx_lists.data_values(rows))

    wb.save(path)


def _write_signature_block(ws, last_data_row, signatories, school_info):
    if not signatories:
        return
    r = last_data_row + 3
    if school_info.get("school_name"):
        ws.cell(row=r, column=1, value=school_info["school_name"]).font = Font(bold=True)
        r += 2

    for sig in signatories:
        role = sig["role"]
        ws.cell(row=r, column=1, value=f"{role}:" if role else "")
        name_cell = ws.cell(row=r + 2, column=1, value=(sig["name"] or "").upper())
        name_cell.font = Font(bold=True, underline="single")
        ws.cell(row=r + 3, column=1, value=sig["position"] or "")
        r += 5
