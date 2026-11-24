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

    # APP: the people differ per school, so only the designations are preloaded
    # (plus the SDS as Approved by).
    ("app", "prepared by"): {"position": "ADAS/AO"},
    ("app", "reviewed by"): {"position": "BAC Chair"},
    ("app", "recommended by"): {"auto_name": True, "position": "School Head"},   # the plan's SH
    ("app", "approved by"): {"name": SDS_NAME, "position": SDS_POSITION},

    # PR/JR: designations only; the names differ per school. (RSQ has none: anyone can sign.)
    ("pr", "requested by"): {"position": "ADAS/AO"},
    ("pr", "recommending approval"): {"position": "School Treasurer"},
    ("pr", "approved by"): {"position": "School Head"},

    # SBR: SH follows the active plan's School Head (display only); Approved By is the SDS.
    ("cashadv", "sh"): {"auto_name": True, "position": "School Head"},
    ("cashadv", "approved by"): {"name": SDS_NAME, "position": SDS_POSITION},
}

# Designations only (no names), used to fill a blank Designation on signatories saved before
# these defaults existed. Never overwrites a designation someone typed.
POSITION_DEFAULTS = {k: v["position"] for k, v in SIG_DEFAULT_NAMES.items()
                     if k[0] in ("app", "pr") and "name" not in v and v.get("position")}

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
