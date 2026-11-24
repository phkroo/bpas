"""School Operating Budget / Monthly Disbursement Program as a PDF.

QTextDocument -> QPdfWriter, 8.5 x 13 in landscape.
"""

from PySide6.QtCore import QMarginsF, QSizeF
from PySide6.QtGui import QPdfWriter, QPageSize, QPageLayout, QTextDocument

import db
from doc_header import deped_header_html
from pdf_layout import keep, paginate
from pdf_theme import HEADER_STYLE, SECTION_BG, BORDER, TITLE_PT, BODY_PT
from ppmp_pdf import _peso, signatures_html

TABLE_PT = 10          # the 16-column table; everything else on the page is 12 pt

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# Accounting titles excluded from the 5% tax base — non-taxable per policy.
NON_TAXABLE_TITLES = {
    "Traveling Expenses - Local",
    "Accountable Forms Expenses",
    "Mobile",
    "Postage and Courier Services",
    "Other General Services",
    "Transportation and Delivery Expenses",
    "Fidelity Bond Premiums",
}


def _n(v):
    v = float(v or 0)
    return _peso(v) if v else "-"


def build_html(batch_id) -> str:
    info = db.get_school_info()
    plan = db.get_plan(batch_id)
    allot = db.get_allotment()
    d = db.sobp_data(batch_id)

    sig_info = dict(info)          # "Prepared by" follows the active plan's School Head
    if plan["school_head"]:
        sig_info["school_head"] = plan["school_head"]

    school = plan["school_name"] or info["school_name"]
    school_id = plan["school_id"] or allot["school_id"]
    year = allot["calendar_year"]
    total_allot = d["total_allotment"]

    mth = "".join(f"<th style='width:34px'>{m}</th>" for m in MONTHS)

    def data_row(label, amount, monthly, pct=None, bold=False):
        b0, b1 = ("<b>", "</b>") if bold else ("", "")
        cells = "".join(f"<td align='right'>{_n(x)}</td>" for x in monthly)
        return (
            "<tr>"
            f"<td>{b0}{label}{b1}</td>"
            f"<td align='center'>{('%.2f%%' % pct) if pct is not None else ''}</td>"
            f"<td align='right'>{b0}{_n(amount)}{b1}</td>"
            f"{cells}"
            f"<td align='right'>{b0}{_n(amount)}{b1}</td></tr>"
        )

    rows = [data_row("Total Allotment", total_allot, d["total_row"]["monthly"], bold=True)]
    gad_pct = (d["gad_allotment"] / total_allot * 100) if total_allot else 0.0
    rows.append(data_row("Gender and Development (GAD)", d["gad_allotment"],
                         d["gad_row"]["monthly"], gad_pct, bold=True))
    rows.append(f"<tr><td colspan='{3 + 13}' style='height:10px'></td></tr>")
    rows.append(
        f"<tr style='background:{SECTION_BG}'><td colspan='{3 + 13}'>"
        f"<b>Account Title / Description</b></td></tr>")
    for r in d["rows"]:
        rows.append(data_row(r["title"], r["amount"], r["monthly"], r["pct"]))
    rows.append(data_row("Total Allotment", d["total_row"]["amount"],
                         d["total_row"]["monthly"], 100.0, bold=True))

    non_taxable = sum(r["amount"] for r in d["rows"] if r["title"] in NON_TAXABLE_TITLES)
    taxable_base = total_allot - non_taxable
    rows.append(
        f"<tr><td><b>5% Tax of the Taxable MOOE Budget</b></td><td></td>"
        f"<td align='right'><b>{_n(round(taxable_base * 0.05, 2))}</b></td>"
        f"<td colspan='13'></td></tr>")

    head = [deped_header_html(plan, info), "<br>"]
    head.append(f"<div align='center' style='font-size:{TITLE_PT}pt'><b>SCHOOL OPERATING BUDGET / "
                "MONTHLY DISBURSEMENT PROGRAM</b></div><br>")
    head.append(f"<div style='font-size:{BODY_PT}pt'><b>Name of School:</b> {school}</div>")
    head.append(f"<div style='font-size:{BODY_PT}pt'><b>School ID No.:</b> {school_id}</div>")
    head.append(f"<div style='font-size:{BODY_PT}pt'><b>Calendar Year:</b> {year}</div>")
    head.append(f"<div style='font-size:{BODY_PT}pt'><b>Allotment Class:</b> "
                f"{allot['allotment_class']}</div><br>")

    return (
        "".join(head)
        + "<table border='3' cellspacing='0' cellpadding='2' width='100%' "
        f"style='border-collapse:collapse; border-color:{BORDER}; font-size:{TABLE_PT}pt'>"
        "<thead>"
        f"<tr style='{HEADER_STYLE}'>"
        "<th rowspan='2' align='center' valign='middle'>PARTICULAR</th>"
        "<th rowspan='2' valign='middle'>PERCENTAGE</th>"
        "<th rowspan='2' valign='middle'>AMOUNT</th>"
        f"<th colspan='13'>MONTHLY DISBURSEMENT PROGRAM {year}</th></tr>"
        f"<tr style='{HEADER_STYLE}'>{mth}"
        "<th>TOTAL</th></tr>"
        "</thead>"
        + "".join(rows)
        + "</table>"
        + keep(signatures_html("sobp", sig_info, first_row_roles=5, col_pct=19, batch_id=batch_id))   # one row, 5 across
    )


def generate(batch_id: int, out_path: str):
    writer = QPdfWriter(out_path)
    writer.setPageSize(QPageSize(QSizeF(8.5, 13), QPageSize.Inch, "Legal (8.5 x 13 in)"))
    writer.setPageOrientation(QPageLayout.Landscape)
    writer.setPageMargins(QMarginsF(8, 8, 8, 8), QPageLayout.Millimeter)
    writer.setResolution(150)

    doc = QTextDocument()
    page_size = writer.pageLayout().paintRectPixels(writer.resolution()).size()
    doc.setHtml("<html><body>" + paginate(build_html(batch_id), page_size) + "</body></html>")
    doc.setPageSize(page_size)
    doc.print_(writer)
    return out_path
