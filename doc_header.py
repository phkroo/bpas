"""Shared DepEd letterhead block for generated PDFs (PR, RSQ, ...)."""

import os

_OE = "font-family:'Old English Text MT','Blackadder ITC',serif"
_TR = "font-family:'Trajan Pro','Times New Roman',serif; font-size:10pt"
_LOGO_PX = 72   # about 19 mm
_TH = "font-family:'Tahoma','Segoe UI',sans-serif; font-size:10pt"


def _logo_html() -> str:
    """DepEd seal above the letterhead text; "" when data/deped_logo.png is missing."""
    from db import bundled_path
    path = bundled_path("data", "deped_logo.png")
    if not os.path.exists(path):
        return ""
    return f"<img src='{path.replace(chr(92), '/')}' width='{_LOGO_PX}' height='{_LOGO_PX}'><br>"


def resolve_division(info) -> str:
    """The Division exactly as typed in Setup ("Schools Division of Bais City",
    "Tanjay City Division", ...) — nothing is added or reworded."""
    return (info.get("division") or "").strip()


def resolve_school(plan, info) -> str:
    school = plan.get("school_name") or info.get("school_name") or ""
    level = (plan.get("level") or "").strip()
    if school and level and level.lower() not in school.lower():
        school = f"{school} - {level} School"
    return school


def deped_header_html(plan, info, school_font="trajan") -> str:
    region = info.get("region") or ""
    division = resolve_division(info)
    school = resolve_school(plan, info)
    lines = [
        f"<span style=\"{_OE}; font-size:12pt\"><b>Republic of the Philippines</b></span>",
        f"<span style=\"{_OE}; font-size:18pt\"><b>Department of Education</b></span>",
    ]
    if region:
        lines.append(f"<span style=\"{_TR}\"><b>{region}</b></span>")
    if division:
        lines.append(f"<span style=\"{_TR}\"><b>{division}</b></span>")
    if school:
        style = _TH if school_font == "tahoma" else _TR
        lines.append(f"<span style=\"{style}\"><b>{school}</b></span>")
    return f"<div align='center' style='line-height:135%'>{_logo_html()}{'<br>'.join(lines)}</div>"
