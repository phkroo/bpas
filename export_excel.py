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


def export_items(rows, path: str):
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

    last_row = xlsx_lists.table_last_row(len(rows))

    xlsx_lists.apply_validations(wb, ws, last_row=last_row, extra=xlsx_lists.data_values(rows))
    xlsx_lists.add_amount_table(wb, ws, last_row)
    # Amount: this export carries the plan's own figures (each row keeps the rate it was built
    # with, and different schools may differ), so write the stored values, not a formula
    # that re-computes them with one rate. The file then has no BPAS_RATE, like an older template.
    for r, item in enumerate(rows, start=2):
        ws.cell(row=r, column=xlsx_lists.AMOUNT_COL).value = xlsx_lists.money(item["total_amount"])
    for r in range(len(rows) + 2, last_row + 1):
        ws.cell(row=r, column=xlsx_lists.AMOUNT_COL).value = None
    if xlsx_lists.RATE_NAME in wb.defined_names:
        del wb.defined_names[xlsx_lists.RATE_NAME]

    wb.save(path)
