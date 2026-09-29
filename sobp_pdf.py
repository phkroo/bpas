"""School Operating Budget Proposal / Monthly Distribution Program as a PDF.

QTextDocument -> QPdfWriter, A4 landscape.
"""

from PySide6.QtCore import QMarginsF
from PySide6.QtGui import QPdfWriter, QPageSize, QPageLayout, QTextDocument

import db
from ppmp_pdf import _peso

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _n(v):
    v = float(v or 0)
    return _peso(v) if v else "-"


def build_html(batch_id) -> str:
    info = db.get_school_info()
    plan = db.get_plan(batch_id)
    allot = db.get_allotment()
    d = db.sobp_data(batch_id)

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
                         d["gad_row"]["monthly"], gad_pct))
    rows.append(
        f"<tr style='background:#e8e8e8'><td colspan='{3 + 13}'>"
        f"<b>Account Title / Description</b></td></tr>")
    for r in d["rows"]:
        rows.append(data_row(r["title"], r["amount"], r["monthly"], r["pct"]))
    rows.append(data_row("Total Allotment", d["total_row"]["amount"],
                         d["total_row"]["monthly"], 100.0, bold=True))
    rows.append(
        f"<tr><td><b>5% Tax of the Total Proposed MOOE Budget</b></td><td></td>"
        f"<td align='right'><b>{_n(round(total_allot * 0.05, 2))}</b></td>"
        f"<td colspan='13'></td></tr>")

    head = ["<div align='center'>"]
    head.append("<div>Republic of the Philippines</div>")
    head.append("<div><b>Department of Education</b></div>")
    if info.get("region"):
        head.append(f"<div>{info['region']}</div>")
    if info.get("division"):
        head.append(f"<div>{info['division']}</div>")
    head.append("<br><div style='font-size:13pt'><b>SCHOOL OPERATING BUDGET "
                "PROPOSAL</b></div></div><br>")
    head.append(f"<div><b>Name of School:</b> {school}</div>")
    head.append(f"<div><b>School ID No.:</b> {school_id}</div>")
    head.append(f"<div><b>Calendar Year:</b> {year}</div>")
    head.append(f"<div><b>Allotment Class:</b> "
                f"{allot['allotment_class']}</div><br>")

    return (
        "".join(head)
        + "<table border='1' cellspacing='0' cellpadding='2' width='100%' "
        "style='border-collapse:collapse; font-size:7pt'>"
        "<thead>"
        "<tr style='background:#1f3864; color:#ffffff'>"
        "<th align='left'>PARTICULAR</th><th>PERCENTAGE</th><th>AMOUNT</th>"
        f"<th colspan='13'>MONTHLY DISTRIBUTION PROGRAM {year}</th></tr>"
        f"<tr style='background:#1f3864; color:#ffffff'><th colspan='3'></th>{mth}"
        "<th>TOTAL</th></tr>"
        "</thead>"
        + "".join(rows)
        + "</table>"
    )


def generate(batch_id: int, out_path: str):
    writer = QPdfWriter(out_path)
    writer.setPageSize(QPageSize(QPageSize.A4))
    writer.setPageOrientation(QPageLayout.Landscape)
    writer.setPageMargins(QMarginsF(8, 8, 8, 8), QPageLayout.Millimeter)
    writer.setResolution(150)

    doc = QTextDocument()
    doc.setHtml("<html><body>" + build_html(batch_id) + "</body></html>")
    doc.setPageSize(writer.pageLayout().paintRectPixels(writer.resolution()).size())
    doc.print_(writer)
    return out_path
