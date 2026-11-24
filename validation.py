"""One set of row rules for B+ items, shared by the Excel import, the plan-file (.bpasx)
import, the Add/Edit dialog and the red-row check in Records.

Each rule is either an ERROR (blocks an import) or a WARNING (shown to the user, but the
import still goes ahead).

- row_problems(...)  -> errors + warnings together. Records uses this, so a row is still
                        flagged red when it has either kind.
- row_issues(...)    -> (errors, warnings) in one pass."""

import db
import xlsx_lists

# Amount may differ from unit price x qty x rate by a centavo (Excel and B+ both round
# half-up, but typed unit prices can carry hidden decimals). "All Months" rows put the
# leftover centavos of the year on December, so those get a little more room.
TOL = 0.01
TOL_MONTHLY = 0.12

DROPDOWNS = (
    ("pap_name", "PAP Name"),
    ("gad_category", "GAD Category"),
    ("accounting_title", "Accounting Title"),
    ("mode_of_procurement", "Mode of Procurement"),
    ("app_for", "APP Form"),
    ("app_cs", "APP CSE"),
    ("month", "Month"),
)

def _get(item, key):
    try:
        v = item[key]
    except (KeyError, IndexError):
        return None
    return v


def _text(item, key) -> str:
    v = _get(item, key)
    return "" if v is None else str(v).strip()


def _num(item, key):
    v = _get(item, key)
    if v is None or str(v).strip() == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def canon_lists(allow_all_months: bool = False, extra: dict | None = None) -> dict:
    """{field: {lower-case value: value spelled as in the list}} for the dropdown fields.
    `extra` adds values a file legitimately carries (its own hidden Lists sheet)."""
    src = xlsx_lists.list_sources()
    out = {}
    for field, _label in DROPDOWNS:
        values = list(src.get(field, []))
        if field == "mode_of_procurement":      # names used by older B+ installs stay valid
            values += xlsx_lists._file_lines("procurement_modes_legacy.txt")
        for v in (extra or {}).get(field, []):
            values.append(v)
        d = {}
        for v in values:
            v = (str(v).strip() if v is not None else "")
            if v:
                d.setdefault(v.lower(), v)
        out[field] = d
    if not allow_all_months:
        out["month"].pop(xlsx_lists.ALL_MONTHS.lower(), None)
    return out


def canonical(field: str, value, canon: dict) -> str:
    """The list's own spelling of `value` (so 'office supplies expenses' is stored the same
    way as everyone else's); unchanged when it is not in the list."""
    v = (str(value).strip() if value is not None else "")
    return canon.get(field, {}).get(v.lower(), v)


def is_gad_program(pap_name) -> bool:
    return (pap_name or "").strip().lower() == xlsx_lists.GAD_PAP.lower()


def row_issues(item, canon: dict, rate: float | None,
               check_amount: bool = True) -> tuple[list[str], list[str]]:
    """(errors, warnings) for a row, in plain language. ([], []) = fine.

    item: dict / sqlite row with the item fields (`total_amount` or `amount` for Amount)
    rate: the plan's Amount multiplier; None = unknown, so Amount is not compared."""
    errors: list[str] = []
    warnings: list[str] = []

    if not _text(item, "item_description"):
        errors.append("Item Description is missing")

    price, qty = _num(item, "unit_price"), _num(item, "qty")
    if price is None:
        errors.append("Unit Price is not a number")
    elif price <= 0:
        errors.append("Unit Price must be greater than 0")
    if qty is None:
        errors.append("Quantity is not a number")
    elif qty <= 0:
        errors.append("Quantity must be greater than 0")

    for field, label in DROPDOWNS:
        v = _text(item, field)
        if v and v.lower() not in canon.get(field, {}):
            errors.append(f"{label} “{v}” is not in the list")

    gad = _text(item, "gad_category")
    if is_gad_program(_text(item, "pap_name")):
        if not gad:
            warnings.append("GAD Category is required when PAP Name is the GAD program")
    elif gad:
        warnings.append("GAD Category must be blank unless PAP Name is the GAD program")

    # Warning only: shown (and the row stays red in Records) but never blocks an import.
    if _text(item, "app_cs") and _text(item, "app_for").upper() != "CSE":
        warnings.append("APP CSE must be blank unless APP Form is CSE")

    amount = _num(item, "total_amount")
    if amount is None:
        amount = _num(item, "amount")
    if (check_amount and rate is not None and amount is not None
            and price is not None and qty is not None):
        expected = db.money(price, qty, rate)
        monthly = _text(item, "unit").lower() == "month" and qty == 1
        # unit prices are kept to the centavo (a price like 6000/1.1 loses up to half a
        # centavo per unit), so the allowance grows with the quantity
        allow = max(TOL + 0.005 * qty * rate, TOL_MONTHLY if monthly else 0)
        if round(abs(amount - expected), 2) > round(allow, 2):
            errors.append(f"Amount {amount:,.2f} does not match unit price x qty x rate "
                          f"({expected:,.2f})")

    return errors, warnings


def row_problems(item, canon: dict, rate: float | None, check_amount: bool = True) -> list[str]:
    """Every reason a row is flagged, errors first then warnings ([] = fine)."""
    errors, warnings = row_issues(item, canon, rate, check_amount)
    return errors + warnings
