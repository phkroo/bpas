"""Signatories that come preloaded in a fresh install (and on the Setup screen when a
document has none saved). Names/positions here are real, known values only; anything that
differs per school (APP Prepared / Reviewed / Recommended, PR, RSQ) is left empty for the
end user to fill in.

"auto_name": True means that role always follows the ACTIVE PLAN's School Head (Records),
so it is never a fixed person and is read-only in Setup.
"""

SDS_NAME = "BERNADETTE A. SUSVILLA EdD, CESO V"
SDS_POSITION = "Schools Division Superintendent"

SIG_DEFAULT_NAMES = {
    ("ppmp", "prepared by"): {"auto_name": True, "position": "School Head"},
    ("ppmp", "reviewed by"): {"name": "NICE C. ILARA",
                              "position": "Administrative Officer IV - Procurement Officer"},
    ("ppmp", "okay as to fund"): {"name": "JOHANNA MARIE B. SARABIA LPT",
                                  "position": "Administrative Officer V - Budget Officer"},
    ("ppmp", "recommending approval"): {
        "name": "NILITA L. RAGAY EdD",
        "position": "OIC - Assistant Schools Division Superintendent"},
    ("ppmp", "approved by"): {"name": SDS_NAME, "position": SDS_POSITION},

    ("sobp", "prepared by"): {"auto_name": True, "position": "School Head"},
    ("sobp", "reviewed by"): {"name": "EMMANUEL B. GARCIA", "position": "SGOD Chief"},
    ("sobp", "okay as to fund"): {"name": "JOHANNA MARIE B. SARABIA LPT",
                                  "position": "Administrative Officer V - Budget Officer"},
    ("sobp", "recommending approval"): {
        "name": "NILITA L. RAGAY EdD",
        "position": "OIC - Assistant Schools Division Superintendent"},
    ("sobp", "approved by"): {"name": SDS_NAME, "position": SDS_POSITION},

    # APP: only the Approved by is preloaded; the rest differ per school.
    ("app", "approved by"): {"name": SDS_NAME, "position": SDS_POSITION},

    # SBR: SH follows the active plan's School Head (display only); Approved By is the SDS.
    ("cashadv", "sh"): {"auto_name": True, "position": "School Head"},
    ("cashadv", "approved by"): {"name": SDS_NAME, "position": SDS_POSITION},
}

# Documents whose signatories are global (not per plan) and their roles, in print order.
GLOBAL_ROLES = {
    "ppmp": ["Prepared by", "Reviewed by", "Okay as to Fund",
             "Recommending Approval", "Approved by"],
    "sobp": ["Prepared by", "Reviewed by", "Okay as to Fund",
             "Recommending Approval", "Approved by"],
    "app": ["Prepared by", "Reviewed by", "Recommended by", "Approved by"],
}


def global_default_rows(doc: str):
    """[(role, name, position)] to store for a global document in a fresh install."""
    rows = []
    for role in GLOBAL_ROLES[doc]:
        d = SIG_DEFAULT_NAMES.get((doc, role.strip().lower()), {})
        name = "" if d.get("auto_name") else d.get("name", "")
        rows.append((role, name, d.get("position", "")))
    return rows
