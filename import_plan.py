"""Import a .bpasx (JSON) plan file exported by export_plan.py — creates a new
local `import_batches` row plus its items/signatories/PR headers, so several
schools' plans can be consolidated into one local database.
"""

from dataclasses import dataclass, field
from datetime import datetime

import db

SUPPORTED_FORMAT_VERSIONS = {1}

# True: a plan file is imported even when its rows break the validation rules; every such
# problem is reported as a warning instead (the rows stay red in Records).
# False: any rule problem blocks the import, as before.
IMPORT_FLAGGED_ROWS = True

# Even with IMPORT_FLAGGED_ROWS, a row whose price or quantity is missing, not a number or
# not above 0 still blocks the file (same as the Excel import).
HARD_FAIL_PREFIXES = ("Unit Price is not a number", "Quantity is not a number",
                      "Unit Price must be greater than 0", "Quantity must be greater than 0")


class ImportPlanError(Exception):
    pass


@dataclass
class ImportPlanResult:
    batch_id: int
    imported_count: int
    unmatched_pr_lines: int
    # non-blocking issues found in the file ("Item 129: APP CSE must be blank ..."),
    # shown to the user after a successful import
    warnings: list = field(default_factory=list)


def _item_key(row):
    """Identifies a bpas_item for relinking PR/JR lines. Deliberately excludes
    `qty` (a PR line's qty is the requested portion, not the item's full qty)
    and `month` (not carried on exported PR lines) — matches on description +
    accounting title + unit + unit price, which is unique in practice."""
    return (row.get("item_description") or "", row.get("general_description") or "",
            row.get("accounting_title") or "", row.get("unit") or "",
            round(float(row.get("unit_price") or 0), 2))


def import_plan(path: str) -> ImportPlanResult:
    import json
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)

    version = payload.get("format_version")
    if version not in SUPPORTED_FORMAT_VERSIONS:
        raise ImportPlanError(f"Unsupported plan file version: {version!r}")

    batch = payload.get("batch") or {}
    items = payload.get("items") or []
    signatories = payload.get("signatories") or {}
    pr_headers = payload.get("pr_headers") or []

    # the school in the file must be on the Setup school list (same rule as the Excel import)
    if db.match_school_parts(batch.get("level_type"), batch.get("iu_code"),
                             batch.get("school_id"), batch.get("school_name")) is None:
        raise ImportPlanError(
            "This plan file is for a school that is not on the school list "
            f"({batch.get('school_name') or 'no school'}, ID {batch.get('school_id') or 'none'}). "
            "It was not imported.")

    # every item must pass the same rules as the Excel import. Errors block the file;
    # warnings (e.g. APP CSE filled while APP Form is not CSE) are kept and shown after import.
    import validation
    rate = batch.get("provision_rate")
    rate = float(rate) if rate not in (None, "") else None     # old files: Amount not compared
    canon = validation.canon_lists()
    flagged = []
    warnings = []
    for n, it in enumerate(items, start=1):
        errors, warns = validation.row_issues(it, canon, rate)
        for why in errors:
            if IMPORT_FLAGGED_ROWS and not why.startswith(HARD_FAIL_PREFIXES):
                warnings.append(f"  • Item {n}: {why}")
            else:
                flagged.append(f"  • Item {n}: {why}")
        for why in warns:
            warnings.append(f"  • Item {n}: {why}")
    if flagged:
        shown = flagged[:15] + ([f"  • … and {len(flagged) - 15} more"] if len(flagged) > 15 else [])
        raise ImportPlanError(
            f"{len(flagged)} problem(s) found in this plan file, so nothing was imported:\n"
            + "\n".join(shown)
            + "\n\nAsk the school to fix the red rows in Records and export the plan file again.")

    file_name = batch.get("file_name") or "(imported plan)"
    batch_id = db.create_batch(file_name, batch.get("label", ""))
    db.set_batch_plan(
        batch_id,
        school_name=batch.get("school_name", ""), school_id=batch.get("school_id", ""),
        iu_code=batch.get("iu_code", ""), level_type=batch.get("level_type", ""),
        level=batch.get("level", ""), school_head=batch.get("school_head", ""),
        total_allotment=batch.get("total_allotment", 0),
        gad_allotment=batch.get("gad_allotment", 0),
        provision_rate=rate,
    )

    if items:
        db.insert_items(batch_id, [{k: v for k, v in it.items() if k != "ref"} for it in items])

    # Match freshly-inserted item ids back to the exported rows so PR lines
    # can be relinked to the new local bpas_items ids.
    new_rows = db.query_items({"batch_id": batch_id})
    lookup = {}
    for r in new_rows:
        lookup.setdefault(_item_key(dict(r)), r["id"])
    # exact link: items were inserted in file order, so the n-th new id is the n-th exported item
    new_ids = sorted(r["id"] for r in new_rows)
    ref_map = {it["ref"]: new_ids[i] for i, it in enumerate(items)
               if "ref" in it and i < len(new_ids)}
    # fallback for files without refs: the line's PR month is its item's month
    by_loose = {}
    for r in new_rows:
        d = dict(r)
        by_loose.setdefault((d["item_description"] or "", d["general_description"] or "",
                             d["accounting_title"] or "", d["unit"] or "", d["month"] or ""), r["id"])
    by_loose_nomonth = {}
    for r in new_rows:
        d = dict(r)
        by_loose_nomonth.setdefault((d["item_description"] or "", d["general_description"] or "",
                                     d["accounting_title"] or "", d["unit"] or ""), r["id"])

    for doc, rows in signatories.items():
        if doc in db.PLAN_OVERRIDE_SIG_DOCS:
            db.set_plan_signatories(rows, doc, batch_id)
        elif doc in db.PER_PLAN_SIG_DOCS:
            db.replace_signatories(rows, doc, batch_id)

    for d in payload.get("app_row_details") or []:
        db.save_app_row_detail(batch_id, d.get("accounting_title", ""), d.get("general_description", ""),
                               **{k: v for k, v in d.items()
                                  if k not in ("accounting_title", "general_description")})

    unmatched_lines = 0
    if pr_headers:
        conn = db.get_connection()
        try:
            for h in pr_headers:
                cur = conn.execute(
                    """INSERT INTO pr_headers (batch_id, pr_no, pr_date, month, purpose, created_at,
                                               delivery_period, fund_source, stock_no, kind)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (batch_id, h.get("pr_no", ""), h.get("pr_date", ""), h.get("month", ""),
                     h.get("purpose", ""),
                     h.get("created_at") or datetime.now().isoformat(timespec="seconds"),
                     h.get("delivery_period", ""), h.get("fund_source", ""),
                     h.get("stock_no", ""), h.get("kind", "")),
                )
                header_id = cur.lastrowid
                for ln in h.get("lines", []):
                    item_id = ref_map.get(ln.get("item_ref"))
                    if item_id is None:
                        item_id = lookup.get(_item_key(ln))
                    if item_id is None:
                        base = (ln.get("item_description") or "", ln.get("general_description") or "",
                                ln.get("accounting_title") or "", ln.get("unit") or "")
                        item_id = by_loose.get(base + (h.get("month") or "",)) or by_loose_nomonth.get(base)
                    if item_id is None:
                        unmatched_lines += 1
                        continue
                    conn.execute(
                        """INSERT INTO pr_lines (pr_header_id, bpas_item_id, qty, unit_price, amount)
                           VALUES (?, ?, ?, ?, ?)""",
                        (header_id, item_id, ln.get("qty", 0), ln.get("unit_price", 0),
                         ln.get("amount", 0)),
                    )
            conn.commit()
        finally:
            conn.close()

    return ImportPlanResult(
        batch_id=batch_id, imported_count=len(items), unmatched_pr_lines=unmatched_lines,
        warnings=warnings)