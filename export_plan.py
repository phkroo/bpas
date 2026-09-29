"""Export a single plan (import_batches row + its items/signatories/PRs) to a
portable .bpasx (JSON) file, so it can be imported on another BPAS install —
e.g. by a division office consolidating several schools' plans.
"""

import json
from datetime import datetime

import db

FORMAT_VERSION = 1

_ITEM_COLS = [
    "category_uacs_school", "pap_name", "general_description", "item_description",
    "gad_category", "accounting_title", "mode_of_procurement", "app_for", "app_cs",
    "unit_price", "qty", "unit", "month", "total_amount",
]


def export_plan(batch_id: int, out_path: str) -> str:
    conn = db.get_connection()
    try:
        batch_row = conn.execute(
            "SELECT * FROM import_batches WHERE id = ?", (batch_id,)
        ).fetchone()
        if not batch_row:
            raise ValueError("Plan not found.")
        batch = dict(batch_row)
    finally:
        conn.close()

    items = [
        {c: r[c] for c in _ITEM_COLS}
        for r in db.query_items({"batch_id": batch_id})
    ]

    signatories = {}
    for doc in sorted(db.PER_PLAN_SIG_DOCS):
        rows = db.list_signatories(doc, batch_id)
        signatories[doc] = [
            {"role": r["role"], "name": r["name"], "position": r["position"],
             "sort_order": r["sort_order"]}
            for r in rows
        ]

    pr_headers = []
    for h in db.pr_list(batch_id):
        lines = db.pr_lines_for(h["id"])
        pr_headers.append({
            "pr_no": h["pr_no"], "pr_date": h["pr_date"], "month": h["month"],
            "purpose": h["purpose"], "created_at": h["created_at"],
            "lines": [
                {"accounting_title": ln["accounting_title"],
                 "item_description": ln["item_description"],
                 "general_description": ln["general_description"],
                 "unit": ln["unit"], "qty": ln["qty"],
                 "unit_price": ln["unit_price"], "amount": ln["amount"]}
                for ln in lines
            ],
        })

    payload = {
        "format_version": FORMAT_VERSION,
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "batch": {
            "file_name": batch.get("file_name", ""),
            "label": batch.get("label", ""),
            "school_name": batch.get("school_name", ""),
            "school_id": batch.get("school_id", ""),
            "iu_code": batch.get("iu_code", ""),
            "level_type": batch.get("level_type", ""),
            "level": batch.get("level", ""),
            "school_head": batch.get("school_head", ""),
            "total_allotment": batch.get("total_allotment", 0),
            "gad_allotment": batch.get("gad_allotment", 0),
        },
        "items": items,
        "signatories": signatories,
        "pr_headers": pr_headers,
        "item_count": len(items),
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    return out_path
