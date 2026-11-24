"""Convert a PS-DBM APP-CSE Excel (FY2027 form layout) into the 14-column BPAS template.

Fixed column layout (0-indexed):
  A0 line no · B1 item code · C2 item description · D3 unit of measure
  E4  Jan  F5  Feb  G6  Mar   (H7 Q1, I8 Q1-amount — skipped)
  J9  Apr  K10 May  L11 Jun   (M12 Q2, N13 Q2-amount — skipped)
  O14 Jul  P15 Aug  Q16 Sep   (R17 Q3, S18 Q3-amount — skipped)
  T19 Oct  U20 Nov  V21 Dec   (W22 Q4, X23 Q4-amount — skipped)
  Y24 total quantity for the year · Z25 unit price · AA26 total amount (skipped)

Rows: "PART I" / "PART II" markers switch section. An item row has a Unit (col D);
a category band has text in A/B/C but no Unit -> its text is the General Description
for the items beneath it. For every item with a yearly quantity > 0 we emit one BPAS
row per month that has a quantity.
"""

import re
from decimal import Decimal, ROUND_HALF_UP

import warnings

import openpyxl
# the files we read are never re-saved, so dropping their extension-based dropdowns is harmless
warnings.filterwarnings("ignore", message="Data Validation extension", category=UserWarning)
from openpyxl.styles import Font

from export_excel import HEADERS, FIELDS

DESC_COL, UNIT_COL, TOTQTY_COL, PRICE_COL = 2, 3, 24, 25

# A row is a section banner only when a cell *starts* with "PART I" / "PART II"
# (the real headings read "PART I. AVAILABLE AT PS-DBM ..."). This keeps the
# reminder prose ("... not included on the list of PART II ...") from flipping it.
_PART_RE = re.compile(r"^\s*PART\s+(II|I)\b", re.I)

# A month/total column holding a value this large is a UACS / reference number
# that leaked out of the identity block, not a quantity.
_QTY_SANITY_CAP = 1_000_000

_CENT = Decimal("0.01")
MONTH_COLS = {
    4: "January", 5: "February", 6: "March",
    9: "April", 10: "May", 11: "June",
    14: "July", 15: "August", 16: "September",
    19: "October", 20: "November", 21: "December",
}


def _num(v):
    try:
        return float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return 0.0


def _text(v):
    return "" if v is None else str(v).strip()


def _money(x) -> float:
    """Round a peso value to centavos, half-up — the way the APP-CSE form rounds."""
    return float(Decimal(str(x)).quantize(_CENT, rounding=ROUND_HALF_UP))


def _mul_money(a, b) -> float:
    """a * b in exact decimal, then rounded to centavos half-up."""
    return float((Decimal(str(a)) * Decimal(str(b))).quantize(
        _CENT, rounding=ROUND_HALF_UP))


def _dsum(values) -> Decimal:
    """Exact decimal sum — avoids float drift when totalling many amounts."""
    return sum((Decimal(str(v)) for v in values), Decimal(0))


PROVISION_RATE = 0.10   # 10% provision for price changes (APP-CSE), applied per item


def apply_provision(rows, rate: float = PROVISION_RATE):
    """Amount = unit_price * qty * (1 + rate), half-up, per line. Unit Price is never
    touched. If a Part's rows don't add up to the APP-CSE Part GRAND TOTAL, 1 centavo is
    moved on as many lines as needed: lines rounded down the most go up, lines rounded
    up the most go down."""
    fdec = Decimal(str(1.0 + rate))
    out = [dict(r) for r in rows]
    for part in ("PART I", "PART II"):
        idxs = [i for i, r in enumerate(out) if r["app_cs"] == part]
        if not idxs:
            continue
        exact = {i: Decimal(str(rows[i]["unit_price"])) * Decimal(str(rows[i]["qty"])) * fdec
                 for i in idxs}
        for i in idxs:
            out[i]["total_amount"] = float(exact[i].quantize(_CENT, rounding=ROUND_HALF_UP))

        raw_total = _dsum(rows[i]["total_amount"] for i in idxs)
        target = Decimal(str(_money(raw_total * fdec)))          # form GRAND TOTAL
        steps = int((target - _dsum(out[i]["total_amount"] for i in idxs)) / _CENT)
        if not steps:
            continue
        if abs(steps) > len(idxs):
            raise ValueError(f"{part}: rows differ from the APP-CSE total by {steps} "
                             "centavos. This is not rounding, check prices/quantities.")
        ranked = sorted(idxs, reverse=steps > 0,
                        key=lambda i: exact[i] - Decimal(str(out[i]["total_amount"])))
        for i in ranked[:abs(steps)]:
            out[i]["total_amount"] = float(
                Decimal(str(out[i]["total_amount"])) + (_CENT if steps > 0 else -_CENT))
    return out


def parse(appcse_path: str, school_text: str = ""):
    """-> (wfp_rows: list[dict], stats: dict)"""
    wb = openpyxl.load_workbook(appcse_path, data_only=True)
    ws = wb.active

    wfp_rows = []
    counts = {"PART I": 0, "PART II": 0}
    section = ""
    general = ""
    skipped = 0

    for row in ws.iter_rows(values_only=True):
        row = list(row)

        def cell(i):
            return _text(row[i]) if i < len(row) else ""

        if not any(_text(c) for c in row):
            continue

        banner = next((_PART_RE.match(_text(c)) for c in row
                       if _PART_RE.match(_text(c))), None)
        if banner:
            section = "PART II" if banner.group(1).upper() == "II" else "PART I"
            general = ""
            continue
        if not section:                       # still in the identity / notes block
            continue

        unit = cell(UNIT_COL)
        desc = cell(DESC_COL)

        if not unit:                          # category band (may be merged into A/B/C)
            band = desc or cell(1) or cell(0)
            if band and not band.rstrip().endswith(":") \
                    and not band.lower().startswith("note"):
                general = band
            continue
        if not desc or desc.rstrip().endswith(":"):   # "Agency Code/UACS:" style label
            continue

        price = _num(row[PRICE_COL]) if PRICE_COL < len(row) else 0.0
        if price <= 0:                         # every real PS-DBM catalogue item is priced
            continue

        monthly = {m: _num(row[ci]) for ci, m in MONTH_COLS.items() if ci < len(row)}
        year_qty = sum(monthly.values())
        if TOTQTY_COL < len(row):
            year_qty = max(year_qty, _num(row[TOTQTY_COL]))
        if year_qty <= 0:
            continue
        if year_qty > _QTY_SANITY_CAP:         # a reference number leaked into a qty column
            skipped += 1
            continue

        for month, qty in monthly.items():
            if qty <= 0:
                continue
            wfp_rows.append({
                "category_uacs_school": school_text,
                "pap_name": "",
                "general_description": general,
                "item_description": desc,
                "gad_category": "",
                "accounting_title": "",
                "mode_of_procurement": "Negotiated Procurement - Agency to Agency"
                                      if section == "PART I" else "",
                "app_for": "CSE",
                "app_cs": section,
                "unit_price": _money(price),
                "qty": round(qty, 2),
                "unit": unit,
                "month": month,
                "total_amount": _mul_money(price, qty),
            })
            counts[section] = counts.get(section, 0) + 1

    p1 = _money(_dsum(r["total_amount"] for r in wfp_rows if r["app_cs"] == "PART I"))
    p2 = _money(_dsum(r["total_amount"] for r in wfp_rows if r["app_cs"] == "PART II"))
    stats = {
        "rows": len(wfp_rows),
        "part1": counts.get("PART I", 0),
        "part2": counts.get("PART II", 0),
        "part1_total": p1,
        "part2_total": p2,
        "total": _money(Decimal(str(p1)) + Decimal(str(p2))),
        "skipped": skipped,
    }
    return wfp_rows, stats


def write_template(rows, path, rate: float = 0.0):
    import xlsx_lists
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "BPAS"
    for ci, h in enumerate(HEADERS, start=1):
        ws.cell(row=1, column=ci, value=h).font = Font(bold=True)
    for ri, r in enumerate(rows, start=2):
        for ci, field in enumerate(FIELDS, start=1):
            value = r[field]
            if field in xlsx_lists.NUMBER_FIELDS:
                value = xlsx_lists.money(value)         # real number, 2 decimals
            elif field == "unit":
                value = xlsx_lists.cap_first(value)
            ws.cell(row=ri, column=ci, value=value)
    for ci in range(1, len(HEADERS) + 1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(ci)].width = 22
    last_row = xlsx_lists.table_last_row(len(rows))
    xlsx_lists.apply_validations(wb, ws, last_row=last_row, extra=xlsx_lists.data_values(rows))
    xlsx_lists.add_amount_table(wb, ws, last_row, multiplier=1.0 + rate)
    # the stored Amount (with the centavo adjustment) overrides the formula on data rows
    for ri, r in enumerate(rows, start=2):
        ws.cell(row=ri, column=xlsx_lists.AMOUNT_COL).value = xlsx_lists.money(r["total_amount"])
    wb.save(path)
