"""Shared DepEd letterhead block for generated PDFs (PR, RSQ, ...)."""

_OE = "font-family:'Old English Text MT','Blackadder ITC',serif"
_TR = "font-family:'Trajan Pro','Times New Roman',serif; font-size:10pt"
_TH = "font-family:'Tahoma','Segoe UI',sans-serif; font-size:10pt"


def resolve_division(info) -> str:
    d = (info.get("division") or "").strip()
    if d and "division" not in d.lower():
        d = f"Schools Division of {d}"
    return d


def resolve_school(plan, info) -> str:
    school = plan.get("school_name") or info.get("school_name") or ""
    level = (plan.get("level") or "").strip()
    if school and level and level.lower() not in school.lower():
        school = f"{school} - {level} School"
    return school


def deped_header_html(plan, info) -> str:
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
        lines.append(f"<span style=\"{_TH}\"><b>{school}</b></span>")
    return f"<div align='center' style='line-height:135%'>{'<br>'.join(lines)}</div>"
