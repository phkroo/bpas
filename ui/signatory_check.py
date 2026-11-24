"""Before a PDF is made: if its document has no signatory name at all, ask first.
One name is enough to skip the prompt."""

from PySide6.QtWidgets import QMessageBox

import db
from sig_defaults import SIG_DEFAULT_NAMES


def has_signatory_name(doc: str, batch_id) -> bool:
    rows = db.list_signatories(doc, batch_id)
    if not rows:
        # nothing saved: the document falls back to its fixed default names, if it has any
        return any(k[0] == doc and v.get("name") for k, v in SIG_DEFAULT_NAMES.items())
    for s in rows:
        role = (s["role"] or "").strip().lower()
        if (s["name"] or "").strip() and not SIG_DEFAULT_NAMES.get((doc, role), {}).get("auto_name"):
            return True        # a typed name; the School Head that follows the plan doesn't count
    return False


def confirm_signatories(parent, doc: str, batch_id, label: str) -> bool:
    """True = go ahead and make the PDF."""
    if has_signatory_name(doc, batch_id):
        return True
    answer = QMessageBox.question(
        parent, "No signatory names",
        f"No signatory name has been entered for the {label}, so its signature lines will "
        "print blank.\n\nSet them in Setup \u2192 Signatories.\n\nMake the PDF anyway?",
        QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
    return answer == QMessageBox.Yes
