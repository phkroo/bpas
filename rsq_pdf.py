"""Generate Requests for Sealed Quotation (RSQ) as one combined PDF.

One RSQ (2 pages) per saved PR, built from its stored pr_lines.
QTextDocument -> QPdfWriter, A4 portrait.
"""

import db
from doc_header import deped_header_html, resolve_division, resolve_school

MIN_ROWS = 15


def _num(v):
    v = float(v or 0)
    return f"{v:,.0f}" if v == int(v) else f"{v:,.2f}"


def _money(v):
    return f"{float(v or 0):,.2f}"


def _sig_name(sigs, keyword):
    for s in sigs:
        if keyword in (s["role"] or "").lower():
            return s["name"] or "", s["position"] or (s["role"] or "")
    return "", ""


def _sig_by_role(sigs, role_name):
    """Exact (case/space-insensitive) role match — unlike _sig_name's loose
    substring search, this doesn't confuse "BAC Chairperson" with "BAC
    Vice-Chairman" (the latter also contains "chair")."""
    role_name = role_name.strip().lower()
    for s in sigs:
        if (s["role"] or "").strip().lower() == role_name:
            return s["name"] or "", s["position"] or (s["role"] or "")
    return "", ""


def _sig_names(sigs, keyword):
    return [(s["name"] or "", s["position"] or (s["role"] or ""))
            for s in sigs if keyword in (s["role"] or "").lower()]


def general_conditions_html(delivery_period: str = "") -> str:
    delivery_txt = delivery_period.strip() if delivery_period else "________"
    return f"""
<div style='font-size:7.5pt'>
<b>GENERAL CONDITIONS:</b> (It is important that end-users should fill-up below so that supplier's will be guided)<br><br>
1. ALL ENTRIES MUST BE LEGIBLE AND PREFERABLY TYPE WRITTEN. NO ERASURE WHATSOEVER<br><br>
2. DELIVERY PERIOD WITHIN {delivery_txt} CALENDAR DAYS<br><br>
3. WARRANTY SHALL BE FOR A MINIMUM OF THREE (3) MONTHS FOR EXPENDABLE SUPPLIES AND MINIMUM OF ONE YEAR FOR NON-EXPENDABLE SUPPLIES
RECKONED FROM DATE OF ACCEPTANCE OF THE ITEM(S) BY THE PROCURING ENTITY<br><br>
4. PRICE VALIDITY SHALL BE FOR A PERIOD OF ___ THIRTY (30) ___ CALENDAR DAYS FROM DATE OF SUBMISSION OF PRICE QUOTATION<br><br>
5. ALTERNATIVE BIDS, OR BID WITH OPTIONS WILL AUTOMATICALLY BE REJECTED<br><br>
6. MARK &quot;X&quot; ONLY THE APPLICABLE CONDITION WHETHER A,B,C<br>
&nbsp;&nbsp;&nbsp;&nbsp;______ a. Each item to be evaluated and compared with other Bids separately and recommended for contract award separately.<br>
&nbsp;&nbsp;&nbsp;&nbsp;______ b. All items to be grouped to form more complete Lot that will be awarded to one Bidder to form more complete contract.<br>
&nbsp;&nbsp;&nbsp;&nbsp;______ c. Similar items, to be grouped together to form several lots that shall be evaluated and awarded as separate contracts.
</div>
"""


def build_rsq_html(rsq_sigs, pr_sigs, header, lines, plan, info) -> str:
    region = info.get("region") or ""
    division = resolve_division(info)
    school = resolve_school(plan, info)
    project = header["purpose"] or ""

    # The label under each name is the role as written in Setup, so renaming "BAC
    # Vice-Chairperson" to "BAC Member" there makes it print as a BAC MEMBER.
    def is_chair(role):
        r = (role or "").lower()
        return "chair" in r and "vice" not in r

    chair = next((x for x in rsq_sigs if is_chair(x["role"])), None)
    chair_n = (chair["name"] if chair else "") or ""
    chair_label = ((chair["role"] if chair else "") or "BAC Chairperson").strip().upper()
    canv_n, _ = _sig_name(rsq_sigs, "canvass")
    req_n, _ = _sig_name(pr_sigs, "request")
    total_abc = sum(it["amount"] or 0 for it in lines)

    # RSQ signatories carry no Designation — the label under each name is
    # always its role, never a leftover/stale position value.
    chair_d = chair_label

    # Under the Chairperson's "Very truly yours" block: everyone else who is filled in,
    # in Setup order with any Vice-Chairperson last. An empty row prints nothing.
    others = [x for x in rsq_sigs
              if not is_chair(x["role"]) and "canvass" not in (x["role"] or "").lower()
              and (x["name"] or "").strip()]
    others.sort(key=lambda x: "vice" in (x["role"] or "").lower())    # stable: vice last
    row_people = [(x["name"], (x["role"] or "").strip().upper()) for x in others]

    body = []
    for i, it in enumerate(lines, start=1):
        body.append(
            "<tr>"
            f"<td align='center'>{i}</td>"
            f"<td>{it['item_description'] or ''}</td>"
            f"<td align='center'>{_num(it['qty'])}</td>"
            f"<td align='center'>{it['unit'] or ''}</td>"
            "<td></td><td></td></tr>"
        )
    for _ in range(max(0, MIN_ROWS - len(lines))):
        body.append("<tr><td>&nbsp;</td><td></td><td></td><td></td><td></td><td></td></tr>")

    # only the people actually filled in, sharing the row's width evenly
    col_w = 100 // max(len(row_people), 1)
    member_cells = "".join(
        f"<td width='{col_w}%' align='center' style='padding-top:18px'>"
        f"{n.upper()}<br>{d}</td>" for n, d in row_people
    )

    _line = "____________________"
    return f"""
{deped_header_html(plan, info)}
<br>
<table width='100%' style='font-size:9pt'>
  <tr>
    <td width='55%' valign='bottom'>&nbsp;</td>
    <td width='45%' align='right'>Date: <u>&nbsp;{_line}&nbsp;</u></td>
  </tr>
  <tr><td valign='bottom'>&nbsp;</td>
      <td align='right'>Canvass No.: <u>&nbsp;{_line}&nbsp;</u></td></tr>
  <tr>
    <td>Company Name: <u>&nbsp;{_line * 2}&nbsp;</u></td>
    <td align='right'>Sheet No.: <u>&nbsp;{_line}&nbsp;</u></td>
  </tr>
  <tr><td>Address: <u>&nbsp;{_line * 2}&nbsp;</u></td><td></td></tr>
</table>
<br>
<div align='center' style='font-size:12pt'><b>REQUEST FOR SEALED QUOTATION</b></div>
<br>
<div style='font-size:9pt'>Gentlemen:</div>
<div style='font-size:9pt' align='justify'>
&nbsp;&nbsp;&nbsp;&nbsp;Please quote your lowest price on the items listed below, subject to the
General Conditions enumerated hereunder, stating the shortest time of delivery and submit
your quotation duly signed by you or your representative within THREE (3) days from receipt.
Return quotation in SEALED ENVELOPE to be opened on ____________________, at
<b>{school}, {division}</b>.
</div>
<br>
<table width='100%' style='font-size:9pt'>
  <tr><td width='55%'></td>
      <td align='center'>Very truly yours,</td></td></td></td></tr>
  <tr><td></td>
      <td align='center' style='padding-top:28px'>
        <b style='border-bottom:1px solid #000'>&nbsp;{chair_n.upper()}&nbsp;</b><br>
        <i>{chair_d}</i></td></tr>
</table>
<br>
<table width='100%' style='font-size:8pt'><tr>{member_cells}</tr></table>
<br>
<table border='1' cellspacing='0' cellpadding='3' width='100%'
       style='border-collapse:collapse; font-size:8.5pt'>
  <thead>
  <tr align='center' style='background:#e8e8e8'>
    <th width='7%'>ITEM<br>NO.</th><th>ARTICLES AND DESCRIPTION</th>
    <th width='11%'>QUANTITY</th><th width='10%'>UNIT</th>
    <th width='15%'>ESTIMATED COST /<br>ABC</th><th width='15%'>UNIT PRICE (PhP)</th></tr>
  </thead>
  {''.join(body)}
</table>
<table border='1' cellspacing='0' cellpadding='3' width='100%'
       style='border-collapse:collapse; font-size:8.5pt'>
  <tr><td width='16%'><b>Requested By:</b></td><td>{req_n}</td>
      <td width='16%' rowspan='3' valign='middle' align='center'><b>TOTAL ABC</b></td>
      <td width='18%' rowspan='3' valign='middle' align='center'><b>{_money(total_abc)}</b></td></tr>
  <tr><td valign='top'><b>Project/Activity Name:</b></td><td>{project}</td></tr>
  <tr><td><b>Place of delivery:</b></td><td>{school}</td></tr>
</table>
{general_conditions_html(header["delivery_period"])}
<br>
<div style='font-size:8pt'>After having carefully read and accepted your General Conditions,
I hereby quote and offer the following prices for the items listed above</div>
<table width='100%' style='font-size:8pt'>
  <tr><td width='50%' valign='top'>&nbsp;&nbsp;&nbsp;&nbsp;NOTE<br>
      1. For Suppliers who are not yet accredited, please enclosed documents required per attached checklist<br>
      2. Please enclose RFQ in return envelope duly sealed and return to end-user's office</td>
      <td valign='top' align='right'>
        <br><u>&nbsp;{_line * 2}&nbsp;</u><br>PRINTED NAME AND SIGNATURE<br><br>
        <u>&nbsp;{_line * 2}&nbsp;</u><br>TEL. NO/CELLPHONE NO /EMAIL ADDRESS</td></tr>
</table>
<br>
<table width='100%' style='font-size:8pt'>
  <tr><td width='50%'>CANVASSED  BY: &nbsp; <b>{canv_n}</b></td>
      <td align='right'><u>&nbsp;{_line}&nbsp;</u><br>DATE</td></tr>
</table>
<table border='1' cellspacing='0' cellpadding='4' width='100%'
       style='border-collapse:collapse; font-size:8pt'>
  <tr align='center' style='background:#d9d9d9'><td colspan='2'><b>FOR BAC SECRETARIAT USE</b></td></tr>
  <tr>
    <td width='50%'>DATE OPENED &nbsp; <u>&nbsp;{_line}&nbsp;</u> &nbsp; OPENED BY: <u>&nbsp;{_line}&nbsp;</u><br><br>
        TIME OPENED: &nbsp; <u>&nbsp;{_line}&nbsp;</u></td>
    <td>PHILGEPS/WEBSITE/CONSPICUOUS POSTED BY: <u>&nbsp;{_line}&nbsp;</u><br>
        DATE: <u>&nbsp;{_line}&nbsp;</u></td>
  </tr>
  <tr><td style='height:44px'></td>
      <td valign='top'>SPECIMEN SIGNATURE OF SUPPLIER CERTIFIED CORRECT</td></tr>
</table>"""


def generate(batch_id: int, out_path: str, pr_ids=None):
    from PySide6.QtCore import QMarginsF
    from PySide6.QtGui import QPdfWriter, QPageSize, QPageLayout, QTextDocument

    plan = db.get_plan(batch_id)
    info = db.get_school_info()
    rsq_sigs = db.list_signatories("rsq", batch_id)
    pr_sigs = db.list_signatories("pr", batch_id)

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
        html = build_rsq_html(rsq_sigs, pr_sigs, h, lines, plan, info)
        blocks.append(f"<div style='{brk}'>{html}</div>")

    if not blocks:
        raise ValueError("No saved Purchase Requests to build an RSQ from.")

    writer = QPdfWriter(out_path)
    writer.setPageSize(QPageSize(QPageSize.A4))
    writer.setPageOrientation(QPageLayout.Portrait)
    writer.setPageMargins(QMarginsF(14, 12, 14, 12), QPageLayout.Millimeter)
    writer.setResolution(150)

    doc = QTextDocument()
    doc.setHtml("<html><body>" + "".join(blocks) + "</body></html>")
    doc.setPageSize(writer.pageLayout().paintRectPixels(writer.resolution()).size())
    doc.print_(writer)
    return out_path
