"""Annual Procurement Plan (APP) as a PDF.

Built on the fly from the active plan's PPMP data. QTextDocument -> QPdfWriter,
A4 landscape.
"""

from PySide6.QtCore import QMarginsF
from PySide6.QtGui import QPdfWriter, QPageSize, QPageLayout, QTextDocument

import db
from doc_header import deped_header_html, resolve_school

NCOLS = 12


def _num(v):
    return f"{float(v or 0):,.2f}"


def _sig(sigs, keyword):
    for s in sigs:
        if keyword in (s["role"] or "").lower():
            return (s["name"] or "").strip(), (s["position"] or "").strip()
    return "", ""


def build_html(batch_id) -> str:
    info = db.get_school_info()
    plan = db.get_plan(batch_id)
    allot = db.get_allotment()
    sigs = db.list_signatories("app")
    data = db.app_data(batch_id)

    year = (allot["calendar_year"] or "").strip()
    school = resolve_school(plan, info)
    start, end = f"01/{year}", f"12/{year}"
    fund = "MOOE"

    body = []
    for g in data["groups"]:
        body.append(f"<tr style='background:#f2f2f2'><td colspan='{NCOLS}'>"
                    f"<b>{g['title']}</b></td></tr>")
        for r in g["rows"]:
            body.append(
                "<tr>"
                f"<td>{r['description']}</td>"
                f"<td align='center'>{school}</td>"
                f"<td>{r['description']}</td>"
                f"<td align='center'>{r['modes']}</td>"
                "<td align='center'>NO</td>"
                "<td></td>"
                f"<td align='center'>{start}</td>"
                f"<td align='center'>{end}</td>"
                f"<td align='center'>{fund}</td>"
                f"<td align='right'>{_num(r['amount'])}</td>"
                "<td></td><td></td></tr>"
            )
        body.append(
            f"<tr><td colspan='9' align='right'><i>Sub-total</i></td>"
            f"<td align='right'><i>{_num(g['subtotal'])}</i></td><td></td><td></td></tr>")
    body.append(
        f"<tr><td colspan='9' align='right'><i>Grand-total</i></td>"
        f"<td align='right'><b>{_num(data['total'])}</b></td><td></td><td></td></tr>")

    def sig_cell(label, keyword):
        name, position = _sig(sigs, keyword)
        return (
            "<td width='25%' valign='top' style='padding-top:6px'>"
            f"{label}<br><br><br>"
            f"<b style='border-bottom:1px solid #000'>&nbsp;{name.upper() or '&nbsp;' * 30}&nbsp;</b><br>"
            f"{position}<br><br>Date : ________________</td>"
        )

    box = "<td width='22' style='border:1px solid #000'>&nbsp;</td>"
    checks = (
        "<table align='center' cellspacing='8' style='font-size:11pt'><tr>"
        f"{box}<td><b>INDICATIVE</b></td><td width='24'></td>"
        f"{box}<td><b>FINAL</b></td><td width='24'></td>"
        f"{box}<td><b>UPDATED [Version No. ______]</b></td></tr></table>"
    )

    th = "style='background:#e8e8e8'"
    return f"""
{deped_header_html(plan, info)}
<br>
<div align='center' style='font-size:13pt'><b>ANNUAL PROCUREMENT PLAN FOR FY {year}</b></div>
{checks}
<br>
<table border='1' cellspacing='0' cellpadding='2' width='100%'
       style='border-collapse:collapse; font-size:7pt'>
  <thead>
  <tr align='center' {th}>
    <th colspan='6'>PROCUREMENT PROJECT DETAILS</th>
    <th colspan='2'>PROJECTED TIMELINE (MM/YYYY)</th>
    <th colspan='2'>FUNDING DETAILS</th>
    <th rowspan='2' width='6%'>PROCUREMENT STRATEGY OR TOOLS</th>
    <th rowspan='2' width='8%'>REMARKS<br>(Other relevant descriptions of the
        procurement project, if applicable)</th></tr>
  <tr align='center' {th}>
    <th width='14%'>Project Title</th>
    <th width='10%'>End-User or Implementing Unit</th>
    <th width='15%'>General Description of the Project</th>
    <th width='10%'>Mode of Procurement</th>
    <th width='6%'>To be covered by an Early Procurement Activity? (Yes/No)</th>
    <th width='7%'>Criteria for Bid Evaluation (Including Sustainability and Domestic Preference)</th>
    <th width='6%'>Start of Procurement Activity</th>
    <th width='6%'>End of Procurement Activity</th>
    <th width='6%'>Source of Fund</th>
    <th width='9%'>Estimated Budget / Approved Budget for the Contract (PhP)</th></tr>
  <tr align='center'>{''.join(f'<td><b>Column {i}</b></td>' for i in range(1, NCOLS + 1))}</tr>
  </thead>
  {''.join(body)}
</table>
<br>
<table width='100%' style='font-size:8pt'>
  <tr><td align='right' width='80%'><b>Total Amount of Estimated Budget for EPA Projects:</b></td>
      <td align='right'>{_num(0)}</td></tr>
  <tr><td align='right'><b>Total Amount of CSEs to be purchased from PS-DBM:</b></td>
      <td align='right'>{_num(data['cse_total'])}</td></tr>
  <tr><td align='right'><b>Total Amount of Estimated Budget:</b></td>
      <td align='right'><b>{_num(data['total'])}</b></td></tr>
</table>
<br>
<table width='100%' style='font-size:8pt'>
  <tr>{sig_cell('Prepared by:', 'prepared')}{sig_cell('Reviewed by:', 'reviewed')}
      {sig_cell('Recommended by:', 'recommended')}{sig_cell('Approved by:', 'approved')}</tr>
</table>
"""


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
