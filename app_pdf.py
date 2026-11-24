"""Annual Procurement Plan (APP) as a PDF.

Built on the fly from the active plan's PPMP data. QTextDocument -> QPdfWriter,
8.5 x 13 in landscape.
"""

from PySide6.QtCore import QMarginsF, QSizeF
from PySide6.QtGui import QPdfWriter, QPageSize, QPageLayout, QTextDocument

import db
from doc_header import deped_header_html, resolve_school
from pdf_layout import paginate
from pdf_theme import HEADER_STYLE, NOTE_FG, SECTION_BG, BORDER, TITLE_PT, BODY_PT

NCOLS = 12


def _num(v):
    return f"{float(v or 0):,.2f}"


def _n(v):
    """Same as _num, but shows '-' for exactly zero (no data yet)."""
    v = float(v or 0)
    return _num(v) if v else "-"


def _sig(sigs, keyword):
    for s in sigs:
        if keyword in (s["role"] or "").lower():
            return (s["name"] or "").strip(), (s["position"] or "").strip()
    return "", ""


def build_html(batch_id) -> str:
    info = db.get_school_info()
    plan = db.get_plan(batch_id)
    allot = db.get_allotment()
    sigs = db.list_signatories("app", batch_id)
    data = db.app_data(batch_id)

    year = (allot["calendar_year"] or "").strip()
    school = resolve_school(plan, info)
    fund = db.default_fund_source()

    def row_html(r):
        return (
            "<tr>"
            f"<td>{r['project_title']}</td>"
            f"<td align='center'>{r['end_user_unit'] or school}</td>"
            f"<td>{r['description']}</td>"
            f"<td align='center'>{r['modes']}</td>"
            f"<td align='center'>{r['early_procurement']}</td>"
            f"<td>{r['bid_criteria']}</td>"
            f"<td align='center'>{r['start_date']}</td>"
            f"<td align='center'>{r['end_date']}</td>"
            f"<td align='center'>{r['source_of_fund'] or fund}</td>"
            f"<td align='right'>{_num(r['amount'])}</td>"
            f"<td>{r['procurement_strategy']}</td>"
            f"<td>{r['remarks']}</td></tr>"
        )

    body = []
    for g in data["groups"]:
        body.append(f"<tr style='background:{SECTION_BG}'><td colspan='{NCOLS}'>"
                    f"<b>{g['title']}</b></td></tr>")
        for r in g["rows"]:
            body.append(row_html(r))
        body.append(
            f"<tr><td colspan='9' align='right'><i>Sub-total</i></td>"
            f"<td align='right'><i>{_num(g['subtotal'])}</i></td><td></td><td></td></tr>")

    if data["cse_rows"]:                     # no CSE items -> no CSE section
        body.append(
            f"<tr style='background:{SECTION_BG}'><td colspan='{NCOLS}'>"
            f"<b>Common Use Supplies and Equipment (CSE) to be purchased from PS-DBM "
            f"(kindly indicate the summary/total amounts only)</b></td></tr>")
        for r in data["cse_rows"]:           # one row per part that has items
            body.append(row_html(r))
        body.append(
            f"<tr><td colspan='9' align='right'><i>Sub-Total</i></td>"
            f"<td align='right'><i>{_num(data['cse_total'])}</i></td><td></td><td></td></tr>")
    body.append(
        f"<tr><td colspan='9' align='right'><b>Grand Total</b></td>"
        f"<td align='right'><b>{_num(data['total'])}</b></td><td></td><td></td></tr>")

    def sig_cell(label, keyword):
        name, position = _sig(sigs, keyword)
        if keyword == "recommended":         # always the plan's School Head, as on the PPMP
            name, position = (plan.get("school_head") or "").strip(), "School Head"
        return (
            "<td width='25%' valign='top' style='padding-top:6px'>"
            f"{label}<br><br><br>"
            f"<b style='border-bottom:1px solid #000'>&nbsp;{name.upper() or '&nbsp;' * 30}&nbsp;</b><br>"
            f"{position}<br><br>Date : ________________</td>"
        )

    box = "<td width='22' style='border:1px solid #000'>&nbsp;</td>"
    checks = (
        f"<table align='center' cellspacing='8' style='font-size:{BODY_PT}pt'><tr>"
        f"{box}<td><b>INDICATIVE</b></td><td width='24'></td>"
        f"{box}<td><b>FINAL</b></td><td width='24'></td>"
        f"{box}<td><b>UPDATED [Version No. ______]</b></td></tr></table>"
    )

    cse_line = (
        "<tr><td align='right'><b>Total Amount of CSEs to be purchased from PS-DBM:</b></td>"
        f"<td align='right'>{_num(data['cse_total'])}</td></tr>"
    ) if data["cse_rows"] else ""
    th = f"style='{HEADER_STYLE}'"
    return f"""
{deped_header_html(plan, info, school_font="tahoma")}
<br>
<div align='center' style='font-size:{TITLE_PT}pt'><b>ANNUAL PROCUREMENT PLAN FOR FY {year}</b></div>
{checks}
<br>
<table border='3' cellspacing='0' cellpadding='2' width='100%'
       style='border-collapse:collapse; border-color:{BORDER}; font-size:{BODY_PT}pt'>
  <thead>
  <tr align='center' {th}>
    <th colspan='6'>PROCUREMENT PROJECT DETAILS</th>
    <th colspan='2'>PROJECTED TIMELINE (MM/YYYY)</th>
    <th colspan='2'>FUNDING DETAILS</th>
    <th rowspan='2' width='9.5%'>PROCUREMENT STRATEGY OR TOOLS</th>
    <th rowspan='2' width='8.5%'>REMARKS<br>(Other relevant descriptions of the
        procurement project, if applicable)</th></tr>
  <tr align='center' {th}>
    <th width='10.5%'>Project Title</th>
    <th width='9%'>End-User or Implementing Unit</th>
    <th width='11%'>General Description of the Project</th>
    <th width='9%'>Mode of Procurement</th>
    <th width='7%'>To be covered by an Early Procurement Activity? (Yes/No)</th>
    <th width='8%'>Criteria for Bid Evaluation (Including Sustainability and Domestic Preference)</th>
    <th width='7%'>Start of Procurement Activity</th>
    <th width='7%'>End of Procurement Activity</th>
    <th width='5%'>Source of Fund</th>
    <th width='9%'>Estimated Budget / Approved Budget for the Contract (PhP)</th></tr>
  <tr align='center'>{''.join(f'<td><b>Column {i}</b></td>' for i in range(1, NCOLS + 1))}</tr>
  </thead>
  {''.join(body)}
</table>
<div style='font-size:{BODY_PT}pt; color:{NOTE_FG}'><i>Note: Insert additional rows as necessary</i></div>
<br>
<table width='100%' style='font-size:{BODY_PT}pt'>
  <tr><td align='right' width='80%'><b>Total Amount of Estimated Budget for EPA Projects:</b></td>
      <td align='right'>{_n(0)}</td></tr>
  {cse_line}
  <tr><td align='right'><b>Total Amount of Estimated Budget:</b></td>
      <td align='right'><b>{_num(data['total'])}</b></td></tr>
</table>
<br>
<!--KEEP--><table width='100%' style='font-size:{BODY_PT}pt'>
  <tr>{sig_cell('Prepared by:', 'prepared')}{sig_cell('Reviewed by:', 'reviewed')}
      {sig_cell('Recommended by:', 'recommended')}{sig_cell('Approved by:', 'approved')}</tr>
</table><!--/KEEP-->
"""


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
