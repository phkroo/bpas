"""Generate the PPMP (Project Procurement Management Plan) as a PDF.

Uses QTextDocument -> QPdfWriter (A4 landscape). No external dependency.
"""

from PySide6.QtCore import QMarginsF, QSizeF
from PySide6.QtGui import QPdfWriter, QPageSize, QPageLayout, QTextDocument

import db

MONTHS = [
    ("JANUARY", "Jan"), ("FEBRUARY", "Feb"), ("MARCH", "Mar"), ("APRIL", "Apr"),
    ("MAY", "May"), ("JUNE", "Jun"), ("JULY", "Jul"), ("AUGUST", "Aug"),
    ("SEPTEMBER", "Sept"), ("OCTOBER", "Oct"), ("NOVEMBER", "Nov"), ("DECEMBER", "Dec"),
]
SHADE = "#4CAF50"


def _peso(v):
    return f"{float(v or 0):,.2f}"


def _months_set(concat):
    return {m.strip().upper() for m in (concat or "").split(",") if m.strip()}


def _single(concat):
    """A GROUP_CONCAT(DISTINCT ...) value -> the lone entry, or '' if mixed/empty."""
    parts = [p.strip() for p in (concat or "").split(",") if p.strip()]
    return parts[0] if len(parts) == 1 else ""


def _qty_size(qty, units_concat):
    q = f"{float(qty or 0):g}"
    unit = _single(units_concat)
    return f"{q} / {unit}" if unit else q


def _modes(modes_concat):
    parts = [p.strip() for p in (modes_concat or "").split(",") if p.strip()]
    return " / ".join(sorted(set(parts)))


def _end_user_unit(school_info):
    school = school_info.get("school_name", "")
    division = school_info.get("division", "")
    right = "Department of Education"
    if division:
        right += f" - {division}"
    return f"{school} / {right}" if school else right


def build_html(school_info, rows, account_codes) -> str:
    month_headers = "".join(f"<th style='width:26px'>{a}</th>" for _, a in MONTHS)

    parts = [
        "<div style='font-size:13pt; text-align:center'><b>Project Procurement "
        "Management Plan (PPMP)</b></div><br>",
        f"<div><b>END USER / UNIT:</b> {_end_user_unit(school_info)}</div>",
        "<div><b>Charged to GAA Projects, Programs and Activities (PAPs):</b> "
        f"{school_info.get('gaa_pap', '')}</div><br>",
        "<table border='1' cellspacing='0' cellpadding='3' width='100%' "
        "style='border-collapse:collapse; font-size:8pt'>",
        "<thead>"
        "<tr style='background:#d9d9d9'>"
        "<th rowspan='2'>CODE</th>"
        "<th rowspan='2' align='left'>GENERAL DESCRIPTION</th>"
        "<th rowspan='2'>QUANTITY / SIZE</th>"
        "<th rowspan='2'>ESTIMATED BUDGET</th>"
        "<th rowspan='2'>Mode of Procurement</th>"
        "<th colspan='12'>SCHEDULE / MILESTONE OF ACTIVITIES</th></tr>"
        f"<tr style='background:#d9d9d9'>{month_headers}</tr>"
        "</thead>",
    ]

    total = 0.0
    current_gd = object()
    for r in rows:
        gd = r["general_description"] or "(no general description)"
        if gd != current_gd:
            current_gd = gd
            parts.append(
                f"<tr><td></td><td colspan='16'><b>{gd}</b></td></tr>"
            )
        code = account_codes.get(_single(r["titles"]), "")
        occurring = _months_set(r["months"])
        month_cells = "".join(
            f"<td style='background:{SHADE}'></td>" if key in occurring else "<td></td>"
            for key, _ in MONTHS
        )
        total += r["budget"] or 0
        parts.append(
            "<tr>"
            f"<td align='center'>{code}</td>"
            f"<td>{r['item_description'] or ''}</td>"
            f"<td align='center'>{_qty_size(r['qty'], r['units'])}</td>"
            f"<td align='right'>{_peso(r['budget'])}</td>"
            f"<td>{_modes(r['modes'])}</td>"
            f"{month_cells}</tr>"
        )

    parts.append(
        f"<tr style='background:#d9d9d9'><td colspan='3'><b>TOTAL</b></td>"
        f"<td align='right'><b>{_peso(total)}</b></td><td colspan='13'></td></tr>"
    )
    parts.append("</table>")
    parts.append(
        "<br><div style='font-size:8pt'><b>NOTE:</b> Technical Specifications for each "
        "Item/Project being proposed shall be submitted as part of the PPMP.</div>"
    )

    sigs = db.list_signatories("ppmp")
    if sigs:
        # "Prepared by" always follows the active plan's School Head (Records) —
        # never a name saved earlier for a different school.
        sigs = [
            {**s, "name": school_info.get("school_head") or "", "position": "School Head"}
            if (s["role"] or "").strip().lower() == "prepared by"
            else s
            for s in sigs
        ]
        # distinct roles in order of first appearance — the first 3 roles'
        # people go on row 1 (however many that is, e.g. 2 "Reviewed by"
        # people each get their own column), the rest on row 2.
        role_order = []
        for s in sigs:
            if not role_order or role_order[-1] != s["role"]:
                role_order.append(s["role"])
        row1_roles = set(role_order[:3])

        SIG_COL_PCT = 24   # one fixed block width for every signature, every row

        def cell(s, show_role):
            label = f"{s['role']}:" if show_role else "&nbsp;"
            return (
                f"<td width='{SIG_COL_PCT}%' align='left' valign='top' "
                f"style='padding:20px 24px 0 0'>"
                f"{label}<br><br><br>"
                f"<b><u>{(s['name'] or '').upper()}</u></b><br>{s['position'] or ''}</td>"
            )

        def row_html(people):
            n = len(people)
            if n == 0:
                return ""
            # every block is the same fixed width; the leftover space is
            # split into n+1 equal gaps (before/between/after the blocks)
            # instead of only two outer margins, so fewer items on a row
            # spread apart instead of just floating closer together.
            gap_pct = (100 - n * SIG_COL_PCT) / (n + 1)
            cells = [f"<td width='{gap_pct}%'></td>"]
            prev_role = None
            for s in people:
                cells.append(cell(s, s["role"] != prev_role))
                cells.append(f"<td width='{gap_pct}%'></td>")
                prev_role = s["role"]
            return f"<table border='0' width='100%'><tr>{''.join(cells)}</tr></table>"

        row1 = [s for s in sigs if s["role"] in row1_roles]
        row2 = [s for s in sigs if s["role"] not in row1_roles]
        tables = [t for t in (row_html(row1), row_html(row2)) if t]
        parts.append("<br><br>" + "<br><br><br>".join(tables))

    return "".join(parts)


def generate(batch_id: int, out_path: str):
    school_info = dict(db.get_school_info())
    plan = db.get_plan(batch_id)
    if plan["school_name"]:
        school_info["school_name"] = plan["school_name"]
    if plan["school_head"]:
        school_info["school_head"] = plan["school_head"]
    rows = db.ppmp_rows(batch_id)
    account_codes = db.list_account_codes()

    writer = QPdfWriter(out_path)
    writer.setPageSize(QPageSize(QSizeF(8.5, 13), QPageSize.Inch, "Legal (8.5 x 13 in)"))
    writer.setPageOrientation(QPageLayout.Landscape)
    writer.setPageMargins(QMarginsF(10, 10, 10, 10), QPageLayout.Millimeter)
    writer.setResolution(150)

    doc = QTextDocument()
    doc.setHtml("<html><body>" + build_html(school_info, rows, account_codes)
                + "</body></html>")
    doc.setPageSize(writer.pageLayout().paintRectPixels(writer.resolution()).size())
    doc.print_(writer)
    return out_path
