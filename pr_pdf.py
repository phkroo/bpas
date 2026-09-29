"""Generate Purchase Requests / Job Requests (NGAS-style form) as one combined
PDF. One page per saved PR/JR (pr_headers row), built from its stored
pr_lines. PR uses an itemized qty x price table; JR (R & M items) uses a
free-text "Description of Job/Order Services" summarized from the same
ticked items, plus a single combined amount — matching how the real NGAS
Job Request form reads, while still keeping the underlying budget-tracking
(ticked items, deducted from the remaining-quantity pool) identical to PR.

QTextDocument -> QPdfWriter, A4 portrait.
"""

from datetime import date

import db

MIN_ROWS = 10


def _num(v):
    v = float(v or 0)
    return f"{v:,.0f}" if v == int(v) else f"{v:,.2f}"


def _money(v):
    return f"{float(v or 0):,.2f}"


def _sig(sigs, keyword):
    for s in sigs:
        if keyword in (s["role"] or "").lower():
            return s["name"] or "", s["position"] or ""
    return "", ""


def _display_date(raw):
    if not raw:
        return date.today().strftime("%d-%b-%y")
    return raw


def _header_common(header, plan, info, is_jr):
    """Fields shared by the PR and JR NGAS templates."""
    division = (info.get("division") or "").strip()
    if division and "division" not in division.lower():
        division = f"Schools Division of {division}"
    school = plan.get("school_name") or info.get("school_name") or ""
    dept = f"DepEd-{division or school}"
    return {
        "purpose": header["purpose"] or "",
        "abc": _money(sum(it["amount"] or 0 for it in header.get("_lines", []))),
        "dept": dept,
        "office": school,
        "date_txt": _display_date(header["pr_date"]),
        "no_label": "JR #.:" if is_jr else "PR No.:",
        "no_value": header["pr_no"],
        "delivery_period": header["delivery_period"] or "",
        "fund_source": header["fund_source"] or "",
        "stock_no": header["stock_no"] or "",
    }


def build_pr_html(sigs, header, lines, plan, info) -> str:
    is_jr = bool(lines) and all(db.is_jr_title(it["accounting_title"]) for it in lines)
    header = dict(header)
    header["_lines"] = lines
    req_n, req_d = _sig(sigs, "request")
    rec_n, rec_d = _sig(sigs, "recommend")
    app_n, app_d = _sig(sigs, "approve")
    sig_block = (
        "<table border='1' cellspacing='0' cellpadding='6' width='100%'"
        " style='border-collapse:collapse; font-size:9pt'>"
        "<tr><td width='15%' style='white-space:nowrap'></td><td>Requested By:</td>"
        "<td>Recommending Approval:</td><td>Approved By:</td></tr>"
        "<tr><td style='white-space:nowrap'><b>Signature :</b></td>"
        "<td></td><td></td><td></td></tr>"
        "<tr><td style='white-space:nowrap'><b>Printed Name :</b></td>"
        f"<td width='33%'>{req_n}</td><td width='33%'>{rec_n}</td>"
        f"<td width='33%'>{app_n}</td></tr>"
        "<tr><td style='white-space:nowrap'><b>Designation :</b></td>"
        f"<td width='33%'>{req_d}</td><td width='33%'>{rec_d}</td>"
        f"<td width='33%'>{app_d}</td></tr>"
        "</table>"
    )
    if is_jr:
        return _build_jr_html(header, lines, plan, info, sig_block)
    return _build_pr_table_html(header, lines, plan, info, sig_block)


def _build_pr_table_html(header, lines, plan, info, sig_block) -> str:
    f = _header_common(header, plan, info, is_jr=False)

    body = []
    total = 0.0
    for i, it in enumerate(lines, start=1):
        total += it["amount"] or 0
        body.append(
            "<tr>"
            f"<td align='center'>{i}</td>"
            f"<td align='center'>{_num(it['qty'])}</td>"
            f"<td align='center'>{it['unit'] or ''}</td>"
            f"<td><b>{it['item_description'] or ''}</b></td>"
            f"<td align='center'>{f['stock_no']}</td>"
            f"<td align='right'>{_money(it['unit_price'])}</td>"
            f"<td align='right'>{_money(it['amount'])}</td></tr>"
        )
    for _ in range(max(0, MIN_ROWS - len(lines))):
        body.append(
            "<tr><td>&nbsp;</td><td></td><td></td><td></td><td></td>"
            "<td></td><td></td></tr>"
        )
    body.append(
        "<tr><td colspan='7' align='center'><i>**** NOTHING FOLLOWS ****</i></td></tr>"
    )

    return f"""
<div style='font-size:9pt'>NGAS - New Government Accounting System</div>
<br>
<div align='center' style='font-size:14pt'><b>PURCHASE REQUEST</b></div>
<div align='center' style='font-size:11pt'>DEPARTMENT OF EDUCATION</div>
<div align='center' style='font-size:11pt'>{f['dept']}</div>
<br>
<table width='100%' style='font-size:9pt'>
  <tr><td width='16%' valign='top'><b>Project Title:</b></td><td>{f['purpose']}</td></tr>
</table>
<br>
<table width='100%' style='font-size:9pt'>
  <tr><td width='16%'><b>ABC:</b></td><td>{f['abc']}</td></tr>
</table>
<br>
<table border='1' cellspacing='0' cellpadding='4' width='100%'
       style='border-collapse:collapse; font-size:9pt'>
  <tr>
    <td width='16%'><b>Department:</b></td><td width='17%'>{f['dept']}</td>
    <td width='16%'><b>{f['no_label']}</b></td><td width='17%'>{f['no_value']}</td>
    <td width='16%'><b>Date:</b></td><td width='18%'>{f['date_txt']}</td>
  </tr>
  <tr>
    <td><b>Office/Section:</b></td><td>{f['office']}</td>
    <td><b>Delivery Period:</b></td><td>{f['delivery_period']}</td>
    <td><b>Fund Source:</b></td><td>{f['fund_source']}</td>
  </tr>
</table>
<table border='1' cellspacing='0' cellpadding='4' width='100%'
       style='border-collapse:collapse; font-size:9pt'>
  <thead>
  <tr align='center' style='background:#e8e8e8'>
    <th width='7%'>ITEM<br>NO.</th><th width='8%'>QTY.</th>
    <th width='12%'>UNIT OF<br>ISSUE</th><th>ITEM DESCRIPTION</th>
    <th width='10%'>STOCK<br>NO.</th><th width='13%'>EST. UNIT<br>COST</th>
    <th width='13%'>EST. TOTAL<br>COST</th></tr>
  </thead>
  {''.join(body)}
</table>
<br>
{sig_block}
"""


def _build_jr_html(header, lines, plan, info, sig_block) -> str:
    f = _header_common(header, plan, info, is_jr=True)

    # Group ticked items by their general_description (matches how the real
    # NGAS JR groups a job's items under one narrative heading), each line
    # summarized as "- description (qty unit x unit price = amount)".
    groups = {}
    order = []
    total = 0.0
    for it in lines:
        gd = it["general_description"] or ""
        if gd not in groups:
            groups[gd] = []
            order.append(gd)
        amt = it["amount"] or 0
        total += amt
        groups[gd].append(
            f"- {it['item_description'] or ''} "
            f"({_num(it['qty'])} {it['unit'] or ''} x {_money(it['unit_price'])} "
            f"= {_money(amt)})"
        )

    desc_parts = []
    if f["purpose"]:
        desc_parts.append(f"<div>{f['purpose']}</div><br>")
    for gd in order:
        if gd:
            desc_parts.append(f"<div><b>{gd}</b></div>")
        desc_parts.append("<div>" + "<br>".join(groups[gd]) + "</div><br>")
    desc_parts.append("<div align='center'><i>**** NOTHING FOLLOWS ****</i></div>")
    description_html = "".join(desc_parts)

    return f"""
<div style='font-size:9pt'>NGAS - New Government Accounting System</div>
<br>
<div align='center' style='font-size:14pt'><b>JOB REQUEST</b></div>
<div align='center' style='font-size:11pt'>DEPARTMENT OF EDUCATION</div>
<div align='center' style='font-size:11pt'>{f['dept']}</div>
<br>
<table width='100%' style='font-size:9pt'>
  <tr><td width='16%' valign='top'><b>Project:</b></td><td><b>{f['purpose']}</b></td></tr>
</table>
<br>
<table width='100%' style='font-size:9pt'>
  <tr><td width='16%'><b>ABC:</b></td><td><b>{f['abc']}</b></td></tr>
</table>
<br>
<table border='0' width='100%' style='font-size:9pt'>
  <tr>
    <td width='16%'><b>From:</b></td>
    <td width='34%'><u>{f['dept']}</u></td>
    <td width='16%'><b>{f['no_label']}</b></td>
    <td width='34%'>{f['no_value']}</td>
  </tr>
  <tr>
    <td><b>Section/Unit:</b></td>
    <td><u>{f['office']}</u></td>
    <td><b>DATE:</b></td>
    <td>{f['date_txt']}</td>
  </tr>
</table>
<br>
<table border='1' cellspacing='0' cellpadding='6' width='100%'
       style='border-collapse:collapse; font-size:9pt'>
  <thead>
  <tr align='center' style='background:#e8e8e8'>
    <th width='75%'>DESCRIPTION OF JOB and / ORDER SERVICES</th>
    <th width='25%'>Estimated / Total Amount</th>
  </tr>
  </thead>
  <tr>
    <td valign='top'>{description_html}</td>
    <td valign='top' align='right'>&nbsp;</td>
  </tr>
  <tr>
    <td align='right'><b>Total</b></td>
    <td align='right'><b>{_money(total)}</b></td>
  </tr>
</table>
<br>
<table width='100%' style='font-size:9pt'>
  <tr><td width='16%' valign='top'><b>Purpose:</b></td><td>{f['purpose']}</td></tr>
</table>
<div style='font-size:9pt'>
  <b>TERMS &amp; CONDITIONS:</b> Delivery Period - {f['delivery_period']}
</div>
<br>
{sig_block}
"""


def generate(batch_id: int, out_path: str, pr_ids=None):
    from PySide6.QtCore import QMarginsF
    from PySide6.QtGui import QPdfWriter, QPageSize, QPageLayout, QTextDocument

    plan = db.get_plan(batch_id)
    info = db.get_school_info()
    sigs = db.list_signatories("pr", batch_id)

    headers = db.pr_list(batch_id)
    if pr_ids is not None:
        wanted = set(pr_ids)
        headers = [h for h in headers if h["id"] in wanted]

    blocks = []
    for h in headers:
        lines = db.pr_lines_for(h["id"])
        if not lines:
            continue
        brk = "page-break-before: always;" if blocks else ""
        html = build_pr_html(sigs, h, lines, plan, info)
        blocks.append(f"<div style='{brk}'>{html}</div>")

    if not blocks:
        raise ValueError("No saved PR/JR requests to export.")

    writer = QPdfWriter(out_path)
    writer.setPageSize(QPageSize(QPageSize.A4))
    writer.setPageOrientation(QPageLayout.Portrait)
    writer.setPageMargins(QMarginsF(14, 14, 14, 14), QPageLayout.Millimeter)
    writer.setResolution(150)

    doc = QTextDocument()
    doc.setHtml("<html><body>" + "".join(blocks) + "</body></html>")
    doc.setPageSize(writer.pageLayout().paintRectPixels(writer.resolution()).size())
    doc.print_(writer)
    return out_path
