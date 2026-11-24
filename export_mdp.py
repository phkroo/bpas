"""Consolidation report: one row per school with the amount for each month (the Monthly
Disbursement Program), the plans' allotments and the balance."""

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

import db
import xlsx_lists

MONTH_HEADERS = [m.upper() for m in db.MONTH_ORDER]
PINK = PatternFill("solid", fgColor="F2D0F0")       # school column header (as in the sample)
BLUE = PatternFill("solid", fgColor="C9E9FB")       # month / amount headers
GREY = PatternFill("solid", fgColor="E7ECEB")       # totals row
THIN = Side(style="thin", color="999999")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)


def school_label(plan: dict, file_name: str = "") -> str:
    """The same text as column A of the item export / template:
    LEVEL_TYPE IU_CODE SCHOOL_ID SCHOOL_NAME."""
    parts = [plan.get("level_type"), plan.get("iu_code"), plan.get("school_id"),
             plan.get("school_name")]
    text = " ".join(str(p).strip() for p in parts if p and str(p).strip())
    return text or file_name or "(unknown school)"


def summary_rows(batch_ids) -> list[dict]:
    """One dict per plan: label, allotment, gad, monthly[12], planned, balance."""
    rows = []
    conn = db.get_connection()
    try:
        files = {r["id"]: r["file_name"] for r in conn.execute("SELECT id, file_name FROM import_batches")}
    finally:
        conn.close()
    for bid in batch_ids:
        plan = db.get_plan(bid)
        monthly = db.sobp_data(bid)["total_row"]["monthly"]          # same numbers as the SOB/MDP
        planned = round(sum(monthly), 2)
        allot = float(plan["total_allotment"] or 0)
        rows.append({
            "label": school_label(plan, files.get(bid, "")),
            "name": (plan.get("school_name") or "").lower(),
            "allotment": allot,
            "gad": float(plan["gad_allotment"] or 0),
            "monthly": monthly,
            "planned": planned,
            "balance": round(allot - planned, 2),
        })
    rows.sort(key=lambda r: (r["name"], r["label"]))
    return rows


def export_mdp_summary(batch_ids, path: str) -> int:
    """Write the summary workbook; returns the number of schools in it."""
    rows = summary_rows(batch_ids)
    year = (db.get_allotment().get("calendar_year") or "").strip()

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "MDP"

    headers = (["CATEGORY/UACS CODE/SCHOOL ID/SCHOOL NAME", "TOTAL ALLOTMENT", "GAD ALLOTMENT"]
               + MONTH_HEADERS + ["TOTAL PLANNED", "BALANCE"])
    ncols = len(headers)
    last_col = get_column_letter(ncols)

    ws.cell(row=1, column=1, value="MONTHLY DISBURSEMENT PROGRAM"
            + (f" - CALENDAR YEAR {year}" if year else "")).font = Font(bold=True, size=13)
    ws.cell(row=2, column=1, value="Amount per month, as in each school's SOB / MDP "
            "(the 5% tax is shown on the school's own SOB, not deducted here).").font = Font(italic=True, size=9)

    head_row = 4
    for c, text in enumerate(headers, start=1):
        cell = ws.cell(row=head_row, column=c, value=text)
        cell.font = Font(bold=True)
        cell.fill = PINK if c == 1 else BLUE
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = BOX

    money = lambda v: xlsx_lists.money(v)
    first = head_row + 1
    for i, r in enumerate(rows):
        row = first + i
        values = [r["label"], money(r["allotment"]), money(r["gad"])] \
            + [money(v) for v in r["monthly"]] + [money(r["planned"]), money(r["balance"])]
        for c, v in enumerate(values, start=1):
            cell = ws.cell(row=row, column=c, value=v)
            cell.border = BOX
            if c > 1:
                cell.number_format = xlsx_lists.ACCOUNTING_FMT
    last = first + len(rows) - 1

    total_row = last + 1
    totals = ["TOTAL", sum(r["allotment"] for r in rows), sum(r["gad"] for r in rows)] \
        + [sum(r["monthly"][m] for r in rows) for m in range(12)] \
        + [sum(r["planned"] for r in rows), sum(r["balance"] for r in rows)]
    for c, v in enumerate(totals, start=1):
        cell = ws.cell(row=total_row, column=c, value=v if c == 1 else money(v))
        cell.font = Font(bold=True)
        cell.fill = GREY
        cell.border = BOX
        if c > 1:
            cell.number_format = xlsx_lists.ACCOUNTING_FMT

    ws.column_dimensions["A"].width = 62
    for c in range(2, ncols + 1):
        ws.column_dimensions[get_column_letter(c)].width = 17
    ws.row_dimensions[head_row].height = 32
    ws.freeze_panes = ws.cell(row=head_row + 1, column=2)
    if rows:
        ws.auto_filter.ref = f"A{head_row}:{last_col}{last}"
    wb.save(path)
    return len(rows)
