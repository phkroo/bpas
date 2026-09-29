"""Import a .bpasx (JSON) plan file exported by export_plan.py — creates a new
local `import_batches` row plus its items/signatories/PR headers, so several
schools' plans can be consolidated into one local database.
"""

from dataclasses import dataclass
from datetime import datetime

import db

SUPPORTED_FORMAT_VERSIONS = {1}


class ImportPlanError(Exception):
    pass


@dataclass
class ImportPlanResult:
    batch_id: int
    imported_count: int
    unmatched_pr_lines: int


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

    file_name = batch.get("file_name") or "(imported plan)"
    batch_id = db.create_batch(file_name, batch.get("label", ""))
    db.set_batch_plan(
        batch_id,
        school_name=batch.get("school_name", ""), school_id=batch.get("school_id", ""),
        iu_code=batch.get("iu_code", ""), level_type=batch.get("level_type", ""),
        level=batch.get("level", ""), school_head=batch.get("school_head", ""),
        total_allotment=batch.get("total_allotment", 0),
        gad_allotment=batch.get("gad_allotment", 0),
    )

    if items:
        db.insert_items(batch_id, items)

    # Match freshly-inserted item ids back to the exported rows so PR lines
    # can be relinked to the new local bpas_items ids.
    new_rows = db.query_items({"batch_id": batch_id})
    lookup = {}
    for r in new_rows:
        lookup.setdefault(_item_key(dict(r)), r["id"])

    for doc, rows in signatories.items():
        if doc not in db.PER_PLAN_SIG_DOCS:
            continue
        db.replace_signatories(rows, doc, batch_id)

    unmatched_lines = 0
    if pr_headers:
        conn = db.get_connection()
        try:
            for h in pr_headers:
                cur = conn.execute(
                    """INSERT INTO pr_headers (batch_id, pr_no, pr_date, month, purpose, created_at)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (batch_id, h.get("pr_no", ""), h.get("pr_date", ""), h.get("month", ""),
                     h.get("purpose", ""),
                     h.get("created_at") or datetime.now().isoformat(timespec="seconds")),
                )
                header_id = cur.lastrowid
                for ln in h.get("lines", []):
                    item_id = lookup.get(_item_key(ln))
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
        batch_id=batch_id, imported_count=len(items), unmatched_pr_lines=unmatched_lines)
