"""Generate a Request for Cash Advance (RCA) as a PDF.

Built on the fly from a batch + month — no saved request needed. 2 pages: the
request letter, then the Breakdown of Expenses. QTextDocument -> QPdfWriter,
A4 portrait.
"""

import db
from doc_header import deped_header_html, resolve_division, resolve_school

MIN_ROWS = 8


def _num(v):
    v = float(v or 0)
    return f"{v:,.2f}"


def _sig_name(sigs, keyword):
    for s in sigs:
        if keyword in (s["role"] or "").lower():
            return s["name"] or "", s["position"] or (s["role"] or "")
    return "", ""


def build_cashadv_html(sigs, month, ca_date, lines, breakdown, plan, info) -> str:
    division = resolve_division(info)
    school = resolve_school(plan, info)
    year = db.get_allotment()["calendar_year"] or ""
    month = (month or "").title()

    head_n = plan.get("school_head") or ""
    head_d = "School Head"
    appr_n, appr_d = _sig_name(sigs, "approved")
    superintendent = appr_n or "SCHOOLS DIVISION SUPERINTENDENT"

    # ---------- breakdown of expenses ----------
    b_rows = []
    for r in breakdown["rows"]:
        b_rows.append(
            "<tr>"
            f"<td align='center'>{r['code']}</td>"
            f"<td>{r['title']}</td>"
            f"<td align='right'>{_num(r['amount'])}</td></tr>"
        )
    breakdown_table = f"""
<div align='center' style='font-size:12pt'><b>BREAKDOWN OF EXPENSES</b></div>
<br>
<table border='1' cellspacing='0' cellpadding='4' width='100%'
       style='border-collapse:collapse; font-size:9pt'>
  <thead>
  <tr align='center' style='background:#e8e8e8'>
    <th width='16%'>Account Code</th><th>Account Title/Description</th>
    <th width='18%'>Amount</th></tr>
  </thead>
  {''.join(b_rows)}
  <tr><td colspan='2' align='right'><b>GRAND TOTAL</b></td>
      <td align='right'><b>{_num(breakdown['total'])}</b></td></tr>
</table>
"""

    # ---------- letter ----------
    period = f"{month} {year}".strip() if month else ""

    # group consecutive lines sharing a PAP (Program/Project) so both the
    # No. and Program/Project cells print once, spanning that PAP's activities.
    groups = []
    for ln in lines:
        pap = ln["program_project"] or ""
        if groups and groups[-1]["pap"] == pap:
            groups[-1]["items"].append(ln)
        else:
            groups.append({"pap": pap, "items": [ln]})

    # within each PAP, merge rows sharing the same activity text (sum amounts).
    for g in groups:
        merged = []
        for ln in g["items"]:
            act = ln["activity"] or ""
            if merged and merged[-1]["activity"] == act:
                merged[-1] = {**merged[-1], "amount": (merged[-1]["amount"] or 0) + (ln["amount"] or 0)}
            else:
                merged.append(dict(ln))
        g["items"] = merged

    l_rows = []
    for g_no, g in enumerate(groups, start=1):
        n = len(g["items"])
        for j, ln in enumerate(g["items"]):
            no_cell = (f"<td align='center' valign='middle' rowspan='{n}'>{g_no}</td>"
                      if j == 0 else "")
            pap_cell = (f"<td valign='middle' rowspan='{n}'>{g['pap']}</td>"
                       if j == 0 else "")
            l_rows.append(
                "<tr>"
                f"{no_cell}"
                f"{pap_cell}"
                f"<td>{ln['activity'] or ''}</td>"
                f"<td align='right'>{_num(ln['amount'])}</td>"
                f"<td align='center'>{period}</td></tr>"
            )
    for _ in range(max(0, MIN_ROWS - len(lines))):
        l_rows.append(
            "<tr><td>&nbsp;</td><td></td><td></td><td></td><td></td></tr>"
        )
    total = sum(ln["amount"] or 0 for ln in lines)

    return f"""
{deped_header_html(plan, info)}
<br>
<table width='100%' style='font-size:9pt'>
  <tr><td></td><td align='right'>Date: <b>{ca_date}</b></td></tr>
</table>
<br>
<div style='font-size:9pt'>
DR. {superintendent}<br>
Schools Division Superintendent<br>
{division}
</div>
<br>
<div style='font-size:9pt'>Ma'am/Sir:</div>
<br>
<div style='font-size:9pt' align='justify'>
&nbsp;&nbsp;&nbsp;&nbsp;May I have the honor to request from your good office to <b>DRAW CASH
ADVANCE</b> for our SCHOOL MOOE (Maintenance and Other Operating Expenses)
({school}) for the month of <b>{month} CY {year}</b> as tabulated below:
</div>
<br>
<table border='1' cellspacing='0' cellpadding='3' width='100%'
       style='border-collapse:collapse; font-size:8pt'>
  <thead>
  <tr align='center' style='background:#e8e8e8'>
    <th width='4%'>No.</th><th width='16%'>Program/Project</th><th>Activities</th>
    <th width='15%'>Amount</th>
    <th width='15%'>Period to<br>Utilize</th></tr>
  </thead>
  {''.join(l_rows)}
  <tr><td colspan='3' align='right'><b>Total</b></td>
      <td align='right'><b>{_num(total)}</b></td>
      <td></td></tr>
</table>
<br><br>
<table width='100%' style='font-size:9pt'>
  <tr><td width='55%'></td>
      <td align='center'>Very truly yours,</td></tr>
  <tr><td></td>
      <td align='center' style='padding-top:28px'>
        <b style='border-bottom:1px solid #000'>&nbsp;{head_n.upper()}&nbsp;</b><br>
        <i>{head_d or 'School Head'}</i></td></tr>
</table>
<br>
<div style='font-size:9pt'><b>APPROVED:</b></div>
<table width='100%' style='font-size:9pt'>
  <tr><td width='55%'></td>
      <td align='center' style='padding-top:28px'>
        <b style='border-bottom:1px solid #000'>&nbsp;{appr_n.upper()}&nbsp;</b><br>
        <i>{appr_d or 'Schools Division Superintendent'}</i></td></tr>
</table>
<div style='page-break-before: always;'></div>
{deped_header_html(plan, info)}
<br>
{breakdown_table}
"""


def generate(batch_id: int, out_path: str, month: str, ca_date: str = ""):
    from PySide6.QtCore import QMarginsF
    from PySide6.QtGui import QPdfWriter, QPageSize, QPageLayout, QTextDocument

    plan = db.get_plan(batch_id)
    info = db.get_school_info()
    sigs = db.list_signatories("cashadv", batch_id)

    items = db.cashadv_buildable_items(batch_id, month)
    if not items:
        raise ValueError(f"No PPMP line items planned for {month}.")
    lines = [{
        "program_project": r["pap_name"] or "",
        "activity": r["general_description"] or "",
        "amount": r["total_amount"] or 0,
    } for r in items]
    breakdown = db.cashadv_breakdown(batch_id, month)

    html = build_cashadv_html(sigs, month, ca_date, lines, breakdown, plan, info)

    writer = QPdfWriter(out_path)
    writer.setPageSize(QPageSize(QPageSize.A4))
    writer.setPageOrientation(QPageLayout.Portrait)
    writer.setPageMargins(QMarginsF(14, 12, 14, 12), QPageLayout.Millimeter)
    writer.setResolution(150)

    doc = QTextDocument()
    doc.setHtml("<html><body>" + html + "</body></html>")
    doc.setPageSize(writer.pageLayout().paintRectPixels(writer.resolution()).size())
    doc.print_(writer)
    return out_path
