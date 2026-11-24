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
from doc_header import deped_header_html

MIN_ROWS = 10
MIN_JR_LINES = 14      # text lines the JR description box always has room for


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
        return date.today().strftime("%m-%d-%Y")
    return raw


# Records keeps the level as Elementary / Junior High / Senior High; the form spells it out.
_LEVEL_LABEL = {"elementary": "Elementary", "junior high": "Junior High School",
                "senior high": "Senior High School"}


def _level_label(plan) -> str:
    """The plan's level from Records as the form wants it (blank when the plan has none)."""
    level = (plan.get("level") or "").strip()
    return _LEVEL_LABEL.get(level.lower(), level)


def _header_common(header, plan, info, is_jr):
    """Fields shared by the PR and JR NGAS templates."""
    school = plan.get("school_name") or info.get("school_name") or ""
    dept = school                              # Department / From: the school
    return {
        "purpose": header["purpose"] or "",
        "project_title": header.get("_project_title", ""),
        "abc": _money(sum(it["amount"] or 0 for it in header.get("_lines", []))),
        "dept": dept,
        "office": _level_label(plan),            # Office/Section: Elementary / JHS / SHS
        "date_txt": _display_date(header["pr_date"]),
        "no_label": "JR No.:" if is_jr else "PR No.:",
        "no_value": header["pr_no"],
        "delivery_period": header["delivery_period"] or "",
        "fund_source": header["fund_source"] or "",
        "stock_no": header["stock_no"] or "",
    }


def build_pr_html(sigs, header, lines, plan, info) -> str:
    is_jr = db.pr_kind(header, lines) == "JR"
    header = dict(header)
    header["_lines"] = lines
    if is_jr:
        return _build_jr_html(header, lines, plan, info, sigs)
    return _build_pr_table_html(header, lines, plan, info, sigs)


# Department / Office rows, the item list and the signature rows share one table: an
# 8-column grid whose column edges line up (widths in %). Project Title and ABC stay
# as plain lines above it.
GRID = (7, 8, 10, 19, 11, 11, 6, 7, 9, 12)
FORM_FONT = "font-family:'Segoe UI',sans-serif; font-size:12pt"


def _spacer_row():
    """First row of the grid: fixes the 8 column widths, takes up no visible height."""
    cells = "".join(
        f"<td width='{w}%' style='border:none; padding:0; font-size:1px'></td>" for w in GRID)
    return f"<tr style='font-size:1px'>{cells}</tr>"


# Purpose cell: 8 of 10 grid columns of the A4 text width (182 mm), less cell padding.
_PURPOSE_W_PT = 182 * 0.8 / 25.4 * 72 - 8


def _two_lines(text):
    """Purpose text, padded with a blank line when it fits on one line so the row always
    has room for two lines (a longer purpose just wraps onto the second line)."""
    from PySide6.QtGui import QFont, QFontMetricsF
    text = text or ""
    font = QFont("Segoe UI")
    font.setPixelSize(16)                       # 12 pt at 96 dpi
    width_pt = QFontMetricsF(font).horizontalAdvance(text) * 72 / 96
    return text + ("<br>&nbsp;" if width_pt <= _PURPOSE_W_PT else "")


def _sig_rows(sigs):
    req_n, req_d = _sig(sigs, "request")
    rec_n, rec_d = _sig(sigs, "recommend")
    app_n, app_d = _sig(sigs, "approve")
    return (
        "<tr><td colspan='2' valign='bottom'><b>Signature :</b></td>"
        "<td colspan='2' valign='top'>Requested By:<br>&nbsp;<br>&nbsp;<br>&nbsp;</td>"
        "<td colspan='3' valign='top'>Recommending Approval:</td>"
        "<td colspan='3' valign='top'>Approved By:</td></tr>"
        f"<tr><td colspan='2'><b>Printed Name :</b></td><td colspan='2'>{req_n}</td>"
        f"<td colspan='3'>{rec_n}</td><td colspan='3'>{app_n}</td></tr>"
        f"<tr><td colspan='2'><b>Designation :</b></td><td colspan='2'>{req_d}</td>"
        f"<td colspan='3'>{rec_d}</td><td colspan='3'>{app_d}</td></tr>"
    )


def _build_pr_table_html(header, lines, plan, info, sigs=None) -> str:
    f = _header_common(header, plan, info, is_jr=False)

    body = []
    for i, it in enumerate(lines, start=1):
        body.append(
            "<tr>"
            f"<td align='center'>{i}</td>"
            f"<td align='center'>{_num(it['qty'])}</td>"
            f"<td align='center'>{it['unit'] or ''}</td>"
            f"<td colspan='2'><b>{it['item_description'] or ''}</b></td>"
            f"<td align='center'>{f['stock_no']}</td>"
            f"<td colspan='2' align='right'>{_money(it['unit_price'])}</td>"
            f"<td colspan='2' align='right'>{_money(it['amount'])}</td></tr>"
        )
    # "NOTHING FOLLOWS" sits in the Item Description column on the row right after the
    # last item; blank rows then pad the table out to MIN_ROWS.
    body.append(
        "<tr><td>&nbsp;</td><td></td><td></td>"
        "<td colspan='2' align='center'><i>**** NOTHING FOLLOWS ****</i></td>"
        "<td></td><td colspan='2'></td><td colspan='2'></td></tr>"
    )
    for _ in range(max(0, MIN_ROWS - len(lines) - 1)):
        body.append(
            "<tr><td>&nbsp;</td><td></td><td></td><td colspan='2'></td>"
            "<td></td><td colspan='2'></td><td colspan='2'></td></tr>"
        )

    return f"""
<div style="font-family:'Segoe UI',sans-serif; font-size:10pt">NGAS - New Government Accounting System</div>
{deped_header_html(plan, info)}
<br>
<div align='center' style="font-family:'Segoe UI',sans-serif; font-size:14pt"><b>PURCHASE REQUEST</b></div>
<br><br>
<table width='100%' style="{FORM_FONT}">
  <tr><td width='16%' valign='top'><b>Project Title:</b></td><td>{f['project_title']}</td></tr>
</table>
<br>
<table width='100%' style="{FORM_FONT}">
  <tr><td width='16%'><b>ABC:</b></td><td>{f['abc']}</td></tr>
</table>
<br><br>
<table border='3' cellspacing='0' cellpadding='4' width='100%'
       style="border-collapse:collapse; border-color:#444; {FORM_FONT}">
  {_spacer_row()}
  <tr>
    <td colspan='2'><b>Department:</b></td><td colspan='3'>{f['dept']}</td>
    <td><b>{f['no_label']}</b></td><td colspan='2'>{f['no_value']}</td>
    <td><b>Date:</b></td><td>{f['date_txt']}</td>
  </tr>
  <tr>
    <td colspan='2'><b>Office/Section:</b></td><td colspan='3'>{f['office']}</td>
    <td><b>Delivery Period:</b></td><td colspan='2'>{f['delivery_period']}</td>
    <td><b>Fund Source:</b></td><td>{f['fund_source']}</td>
  </tr>
  <tr style='background:#e8e8e8'>
    <td align='center'><b>ITEM<br>NO.</b></td><td align='center'><b>QTY.</b></td>
    <td align='center'><b>UNIT OF<br>ISSUE</b></td>
    <td colspan='2' align='center'><b>ITEM DESCRIPTION</b></td>
    <td align='center'><b>STOCK<br>NO.</b></td>
    <td colspan='2' align='center'><b>EST. UNIT<br>COST</b></td>
    <td colspan='2' align='center'><b>EST. TOTAL<br>COST</b></td>
  </tr>
  {''.join(body)}
  <tr><td colspan='2' valign='top'><b>Purpose:</b></td><td colspan='8' valign='top'>{_two_lines(f['purpose'])}</td></tr>
  {_sig_rows(sigs or [])}
</table>
"""


JR_GRID = (15, 30, 30, 25)


def _jr_spacer_row():
    cells = "".join(
        f"<td width='{w}%' style='border:none; padding:0; font-size:1px'></td>" for w in JR_GRID)
    return f"<tr style='font-size:1px'>{cells}</tr>"


def _jr_sig_rows(sigs):
    req_n, req_d = _sig(sigs, "request")
    rec_n, rec_d = _sig(sigs, "recommend")
    app_n, app_d = _sig(sigs, "approve")
    return (
        "<tr><td valign='bottom'><b>Signature :</b></td>"
        "<td valign='top'>Requested By:<br>&nbsp;<br>&nbsp;<br>&nbsp;</td>"
        "<td valign='top'>Recommending Approval:</td>"
        "<td valign='top'>Approved By:</td></tr>"
        f"<tr><td><b>Printed Name :</b></td><td>{req_n}</td><td>{rec_n}</td><td>{app_n}</td></tr>"
        f"<tr><td><b>Designation :</b></td><td>{req_d}</td><td>{rec_d}</td><td>{app_d}</td></tr>"
    )


def _build_jr_html(header, lines, plan, info, sigs=None) -> str:
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
    n_lines = 0
    if f["purpose"]:
        desc_parts.append(f"<div>{f['purpose']}</div><br>")
        n_lines += 2
    for gd in order:
        if gd:
            desc_parts.append(f"<div><b>{gd}</b></div>")
            n_lines += 1
        desc_parts.append("<div>" + "<br>".join(groups[gd]) + "</div><br>")
        n_lines += len(groups[gd]) + 1
    desc_parts.append("<div align='center'><i>**** NOTHING FOLLOWS ****</i></div>")
    n_lines += 1
    # like the PR's minimum rows: a short job still prints as a full-size form
    desc_parts.append("<br>&nbsp;" * max(0, MIN_JR_LINES - n_lines))
    description_html = "".join(desc_parts)

    return f"""
<div style="font-family:'Segoe UI',sans-serif; font-size:10pt">NGAS - New Government Accounting System</div>
{deped_header_html(plan, info)}
<br>
<div align='center' style="font-family:'Segoe UI',sans-serif; font-size:14pt"><b>JOB REQUEST</b></div>
<br><br>
<table width='100%' style="{FORM_FONT}">
  <tr><td width='16%' valign='top'><b>Project:</b></td><td><b>{f['project_title']}</b></td></tr>
</table>
<br>
<table width='100%' style="{FORM_FONT}">
  <tr><td width='16%'><b>ABC:</b></td><td><b>{f['abc']}</b></td></tr>
</table>
<br><br>
<table border='0' width='100%' style="{FORM_FONT}">
  <tr>
    <td width='14%'><b>From:</b></td>
    <td width='61%'><u>{f['dept']}</u></td>
    <td width='10%'><b>{f['no_label']}</b></td>
    <td width='15%'>{f['no_value']}</td>
  </tr>
  <tr>
    <td><b>Section/Unit:</b></td>
    <td><u>{f['office']}</u></td>
    <td><b>DATE:</b></td>
    <td>{f['date_txt']}</td>
  </tr>
</table>
<br>
<table border='3' cellspacing='0' cellpadding='6' width='100%'
       style="border-collapse:collapse; border-color:#444; {FORM_FONT}">
  {_jr_spacer_row()}
  <tr style='background:#e8e8e8'>
    <td colspan='3' align='center'><b>DESCRIPTION OF JOB and / ORDER SERVICES</b></td>
    <td align='center'><b>Estimated / Total Amount</b></td>
  </tr>
  <tr>
    <td colspan='3' valign='top'>{description_html}</td>
    <td valign='top' align='right'>&nbsp;</td>
  </tr>
  <tr>
    <td colspan='3' align='right'><b>Total</b></td>
    <td align='right'><b>{_money(total)}</b></td>
  </tr>
  <tr><td valign='top'><b>Purpose:</b></td><td colspan='3' valign='top'>{f['purpose']}</td></tr>
  <tr><td colspan='4'><b>TERMS &amp; CONDITIONS:</b> Delivery Period - {f['delivery_period']}</td></tr>
  {_jr_sig_rows(sigs or [])}
</table>
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
        h = dict(h)
        h["_project_title"] = db.pr_project_title(batch_id, lines)
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
