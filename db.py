import re
import hashlib
import hmac
import os
import secrets
import shutil
import sqlite3
import sys
from datetime import date, datetime

SCHEMA = """
CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS import_batches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_name TEXT NOT NULL,
    imported_at TEXT NOT NULL,
    label TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS bpas_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id INTEGER NOT NULL REFERENCES import_batches(id) ON DELETE CASCADE,
    category_uacs_school TEXT,
    pap_name TEXT,
    general_description TEXT,
    item_description TEXT,
    gad_category TEXT,
    accounting_title TEXT,
    mode_of_procurement TEXT,
    app_for TEXT,
    app_cs TEXT,
    unit_price REAL DEFAULT 0,
    qty REAL DEFAULT 0,
    unit TEXT,
    month TEXT,
    total_amount REAL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS signatories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc TEXT NOT NULL DEFAULT 'ppmp',
    batch_id INTEGER,            -- NULL = global (PPMP, SOBP); set = per-plan (PR, RSQ)
    role TEXT NOT NULL DEFAULT '',
    name TEXT NOT NULL DEFAULT '',
    position TEXT NOT NULL DEFAULT '',
    sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS account_codes (
    accounting_title TEXT PRIMARY KEY,
    code TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS schools (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    level_type TEXT NOT NULL,
    iu_code TEXT NOT NULL DEFAULT '',
    school_id TEXT NOT NULL DEFAULT '',
    name TEXT NOT NULL,
    level TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_schools_name ON schools(name);

CREATE TABLE IF NOT EXISTS procurement_modes (
    mode TEXT PRIMARY KEY,
    sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS units (
    unit TEXT PRIMARY KEY,
    sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS fund_sources (
    fund_source TEXT PRIMARY KEY,
    sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS app_row_details (
    batch_id INTEGER NOT NULL REFERENCES import_batches(id) ON DELETE CASCADE,
    accounting_title TEXT NOT NULL,
    general_description TEXT NOT NULL,
    project_title TEXT NOT NULL DEFAULT '',
    early_procurement TEXT NOT NULL DEFAULT '',
    bid_criteria TEXT NOT NULL DEFAULT '',
    start_date TEXT NOT NULL DEFAULT '',
    end_date TEXT NOT NULL DEFAULT '',
    procurement_strategy TEXT NOT NULL DEFAULT '',
    remarks TEXT NOT NULL DEFAULT '',
    end_user_unit TEXT NOT NULL DEFAULT '',
    source_of_fund TEXT NOT NULL DEFAULT '',
    description_override TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (batch_id, accounting_title, general_description)
);

CREATE TABLE IF NOT EXISTS mooe_accounts (
    title TEXT PRIMARY KEY,
    code TEXT NOT NULL DEFAULT '',
    sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS pr_headers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id INTEGER NOT NULL REFERENCES import_batches(id) ON DELETE CASCADE,
    pr_no TEXT NOT NULL DEFAULT '',
    pr_date TEXT NOT NULL DEFAULT '',
    month TEXT NOT NULL DEFAULT '',
    purpose TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT '',
    delivery_period TEXT NOT NULL DEFAULT '',
    fund_source TEXT NOT NULL DEFAULT '',
    stock_no TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS pr_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pr_header_id INTEGER NOT NULL REFERENCES pr_headers(id) ON DELETE CASCADE,
    bpas_item_id INTEGER NOT NULL REFERENCES bpas_items(id) ON DELETE CASCADE,
    qty REAL NOT NULL DEFAULT 0,
    unit_price REAL NOT NULL DEFAULT 0,
    amount REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_prlines_header ON pr_lines(pr_header_id);
CREATE INDEX IF NOT EXISTS idx_prlines_item ON pr_lines(bpas_item_id);

CREATE INDEX IF NOT EXISTS idx_items_batch ON bpas_items(batch_id);
CREATE INDEX IF NOT EXISTS idx_items_pap ON bpas_items(pap_name);
CREATE INDEX IF NOT EXISTS idx_items_gad ON bpas_items(gad_category);
"""


def get_app_dir():
    """Directory the .exe (or script) lives in, so the .db sits next to it."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def bundled_path(*parts):
    """Path to a read-only bundled resource (works inside a PyInstaller onefile)."""
    base = getattr(sys, "_MEIPASS", None) or get_app_dir()
    return os.path.join(base, *parts)


def get_db_path():
    new = os.path.join(get_app_dir(), "bpas_data.db")
    old = os.path.join(get_app_dir(), "wfp_data.db")
    if not os.path.exists(new) and os.path.exists(old):
        # one-time move from the pre-BPAS name; the original is kept as a backup
        shutil.copy2(old, new)
        try:
            os.replace(old, old + ".pre-bpas.bak")
        except OSError:
            pass    # still in use elsewhere; harmless, the new file is what we open
    return new


def get_connection():
    conn = sqlite3.connect(get_db_path())
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


_BATCH_PLAN_COLS = {
    "school_name": "TEXT", "school_id": "TEXT", "iu_code": "TEXT",
    "level_type": "TEXT", "level": "TEXT", "school_head": "TEXT",
    "total_allotment": "REAL", "gad_allotment": "REAL",
    "provision_rate": "REAL",     # Amount multiplier this plan was built with (NULL = unknown)
}

_LEVEL_FROM_TYPE = {
    "ES": "Elementary", "IS-ES": "Elementary",
    "JHS": "Junior High", "JHS-IU": "Junior High", "IS-JHS": "Junior High",
    "SHS": "Senior High", "SHS-IU": "Senior High", "IS-SHS": "Senior High",
}


def _migrate_wfp_names(conn):
    """Databases created before the BPAS rename: wfp_items -> bpas_items and
    pr_lines.wfp_item_id -> bpas_item_id. SQLite rewrites the foreign keys/indexes."""
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "wfp_items" in tables and "bpas_items" not in tables:
        # the removed cash-advance tables were never populated; drop them so they
        # don't keep pointing at the old table name
        for t in ("cashadv_lines", "cashadv_headers"):
            if t in tables and conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] == 0:
                conn.execute(f"DROP TABLE {t}")
        conn.execute("ALTER TABLE wfp_items RENAME TO bpas_items")
    if "pr_lines" in tables:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(pr_lines)")}
        if "wfp_item_id" in cols:
            conn.execute("ALTER TABLE pr_lines RENAME COLUMN wfp_item_id TO bpas_item_id")
    conn.commit()


def init_db():
    conn = get_connection()
    try:
        _migrate_wfp_names(conn)
        conn.executescript(SCHEMA)
        cols = {r[1] for r in conn.execute("PRAGMA table_info(bpas_items)").fetchall()}
        if "month" not in cols:
            conn.execute("ALTER TABLE bpas_items ADD COLUMN month TEXT")

        bcols = {r[1] for r in conn.execute("PRAGMA table_info(import_batches)").fetchall()}
        for name, typ in _BATCH_PLAN_COLS.items():
            if name not in bcols:
                conn.execute(f"ALTER TABLE import_batches ADD COLUMN {name} {typ}")
                if name == "provision_rate":      # plans made before this column: today's rate
                    conn.execute("UPDATE import_batches SET provision_rate = ?",
                                 (_multiplier_from(conn),))

        scols = {r[1] for r in conn.execute("PRAGMA table_info(signatories)").fetchall()}
        if "doc" not in scols:
            conn.execute(
                "ALTER TABLE signatories ADD COLUMN doc TEXT NOT NULL DEFAULT 'ppmp'")
        if "batch_id" not in scols:
            conn.execute("ALTER TABLE signatories ADD COLUMN batch_id INTEGER")
            # PR/RSQ signatories are per-plan now; any that were entered globally
            # belong to whichever plan is currently active.
            act = conn.execute(
                "SELECT value FROM app_settings WHERE key = 'active_batch'").fetchone()
            if act and str(act[0]).isdigit():
                conn.execute(
                    "UPDATE signatories SET batch_id = ? "
                    "WHERE doc IN ('pr', 'rsq') AND batch_id IS NULL", (int(act[0]),))

        prcols = {r[1] for r in conn.execute("PRAGMA table_info(pr_headers)").fetchall()}
        for name in ("delivery_period", "fund_source", "stock_no", "kind"):
            if name not in prcols:
                conn.execute(f"ALTER TABLE pr_headers ADD COLUMN {name} TEXT NOT NULL DEFAULT ''")

        # Requests saved before the type was stored keep the type they always had
        # (all items under R & M titles = JR), whatever the JR title list is later.
        conn.execute(
            """UPDATE pr_headers SET kind = CASE
                 WHEN EXISTS (SELECT 1 FROM pr_lines l WHERE l.pr_header_id = pr_headers.id)
                  AND NOT EXISTS (
                        SELECT 1 FROM pr_lines l JOIN bpas_items w ON w.id = l.bpas_item_id
                        WHERE l.pr_header_id = pr_headers.id
                          AND UPPER(TRIM(w.accounting_title)) NOT LIKE 'R & M%')
                 THEN 'JR' ELSE 'PR' END
               WHERE kind = ''""")

        ardcols = {r[1] for r in conn.execute("PRAGMA table_info(app_row_details)").fetchall()}
        for name in ("end_user_unit", "source_of_fund", "description_override"):
            if name not in ardcols:
                conn.execute(
                    f"ALTER TABLE app_row_details ADD COLUMN {name} TEXT NOT NULL DEFAULT ''")

        if conn.execute("SELECT COUNT(*) FROM schools").fetchone()[0] == 0:
            _seed_schools(conn)
        elif not conn.execute("SELECT 1 FROM app_settings WHERE key = 'schools_seal'").fetchone():
            _seal_schools(conn)
        if conn.execute("SELECT COUNT(*) FROM mooe_accounts").fetchone()[0] == 0:
            _seed_mooe_accounts(conn)
        if conn.execute("SELECT COUNT(*) FROM procurement_modes").fetchone()[0] == 0:
            _seed_procurement_modes(conn)
        if conn.execute("SELECT COUNT(*) FROM units").fetchone()[0] == 0:
            _seed_units(conn)
        if conn.execute("SELECT COUNT(*) FROM fund_sources").fetchone()[0] == 0:
            _seed_fund_sources(conn)
        _seed_default_signatories(conn)

        conn.commit()
    finally:
        conn.close()

    if not has_admin_password():
        set_admin_password(DEFAULT_ADMIN_PASSWORD)

    # Region and Division are kept in capitals; convert what was saved before (once)
    if get_setting("region_division_caps", "") != "1":
        for key in ("region", "division"):
            v = get_setting(key, "")
            if v:
                set_setting(key, v.strip().upper())
        set_setting("region_division_caps", "1")


def _seed_mooe_accounts(conn):
    path = bundled_path("data", "mooe_accounts.txt")
    if not os.path.exists(path):
        return
    rows = []
    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f):
            line = line.rstrip("\n")
            if not line.strip():
                continue
            code, _, title = line.partition("\t")
            rows.append((title.strip(), code.strip(), i))
    conn.executemany(
        "INSERT OR IGNORE INTO mooe_accounts (title, code, sort_order) VALUES (?, ?, ?)",
        rows,
    )


def list_mooe_accounts():
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT title, code FROM mooe_accounts ORDER BY sort_order"
        ).fetchall()
    finally:
        conn.close()


def _seed_procurement_modes(conn):
    """One-time seed from the bundled reference list — admin can then edit the
    live (DB-backed) list in Setup > Procurement Modes; the .txt file is never
    read again after this."""
    path = bundled_path("data", "procurement_modes.txt")
    if not os.path.exists(path):
        return
    rows = []
    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f):
            line = line.strip()
            if line:
                rows.append((line, i))
    conn.executemany(
        "INSERT OR IGNORE INTO procurement_modes (mode, sort_order) VALUES (?, ?)", rows)


def list_procurement_modes() -> list[str]:
    conn = get_connection()
    try:
        return [r[0] for r in conn.execute(
            "SELECT mode FROM procurement_modes ORDER BY sort_order")]
    finally:
        conn.close()


def replace_procurement_modes(modes: list[str]):
    """modes: plain list of mode strings, in display order. Replaces the whole
    list — removing one here means it's simply gone from every dropdown/template
    generated afterward."""
    seen, clean = set(), []
    for m in modes:
        m = (m or "").strip()
        if m and m not in seen:
            seen.add(m)
            clean.append((m, len(clean)))
    conn = get_connection()
    try:
        conn.execute("DELETE FROM procurement_modes")
        conn.executemany(
            "INSERT INTO procurement_modes (mode, sort_order) VALUES (?, ?)", clean)
        conn.commit()
    finally:
        conn.close()


def _seed_units(conn):
    """One-time seed from the bundled reference list — admin can then edit the
    live (DB-backed) list in Setup > Units; the .txt file is never read again."""
    path = bundled_path("data", "units.txt")
    if not os.path.exists(path):
        return
    rows = []
    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f):
            line = line.strip()
            if line:
                rows.append((line, i))
    conn.executemany(
        "INSERT OR IGNORE INTO units (unit, sort_order) VALUES (?, ?)", rows)


def list_units() -> list[str]:
    conn = get_connection()
    try:
        return [r[0] for r in conn.execute("SELECT unit FROM units ORDER BY sort_order")]
    finally:
        conn.close()


def replace_units(units: list[str]):
    """units: plain list of unit strings, in display order. Replaces the whole
    list — removing one here means it's simply gone from every dropdown/template
    generated afterward (the Unit column itself stays a soft/suggestion dropdown,
    so a value typed that isn't on the list is still allowed)."""
    seen, clean = set(), []
    for u in units:
        u = (u or "").strip()
        if u and u not in seen:
            seen.add(u)
            clean.append((u, len(clean)))
    conn = get_connection()
    try:
        conn.execute("DELETE FROM units")
        conn.executemany("INSERT INTO units (unit, sort_order) VALUES (?, ?)", clean)
        conn.commit()
    finally:
        conn.close()


def _seed_default_signatories(conn):
    """Once per database: give each global document (PPMP, SOB/MDP, APP) its preloaded
    signatories if it has none yet. A school that later clears or edits them is never
    re-seeded, and documents that already have rows are left exactly as they are."""
    done = conn.execute(
        "SELECT value FROM app_settings WHERE key = 'sig_defaults_seeded'").fetchone()
    if done:
        return
    import sig_defaults
    for doc in sig_defaults.GLOBAL_ROLES:
        have = conn.execute(
            "SELECT COUNT(*) FROM signatories WHERE doc = ? AND batch_id IS NULL",
            (doc,)).fetchone()[0]
        if have:
            continue
        for i, (role, name, position) in enumerate(sig_defaults.global_default_rows(doc)):
            conn.execute(
                "INSERT INTO signatories (doc, batch_id, role, name, position, sort_order) "
                "VALUES (?, NULL, ?, ?, ?, ?)", (doc, role, name, position, i))
    conn.execute("INSERT INTO app_settings (key, value) VALUES ('sig_defaults_seeded', '1') "
                 "ON CONFLICT(key) DO UPDATE SET value = excluded.value")


DEFAULT_FUND_SOURCE = "MOOE"


def _seed_fund_sources(conn):
    """One-time seed (MOOE) - more (SPED, SNED, ...) are added in Setup > Fund Sources."""
    path = bundled_path("data", "fund_sources.txt")
    names = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            names = [ln.strip() for ln in f if ln.strip()]
    names = names or [DEFAULT_FUND_SOURCE]
    conn.executemany("INSERT OR IGNORE INTO fund_sources (fund_source, sort_order) VALUES (?, ?)",
                     [(n, i) for i, n in enumerate(names)])


def list_fund_sources() -> list[str]:
    conn = get_connection()
    try:
        return [r[0] for r in conn.execute(
            "SELECT fund_source FROM fund_sources ORDER BY sort_order")]
    finally:
        conn.close()


def default_fund_source() -> str:
    """The first fund source in Setup > Fund Sources (MOOE unless you reordered it)."""
    names = list_fund_sources()
    return names[0] if names else DEFAULT_FUND_SOURCE


def replace_fund_sources(names: list[str]):
    """Replaces the whole list, in display order. Never left empty - MOOE is the fallback."""
    seen, clean = set(), []
    for n in names:
        n = (n or "").strip()
        if n and n.lower() not in seen:
            seen.add(n.lower())
            clean.append((n, len(clean)))
    if not clean:
        clean = [(DEFAULT_FUND_SOURCE, 0)]
    conn = get_connection()
    try:
        conn.execute("DELETE FROM fund_sources")
        conn.executemany("INSERT INTO fund_sources (fund_source, sort_order) VALUES (?, ?)", clean)
        conn.commit()
    finally:
        conn.close()


# ---------- school list seal (tamper check) ----------
# The school list is signed whenever B+ saves it. If the table is edited outside B+
# the signature no longer matches and imports fall back to the original bundled list.
_SEAL_KEY = b"bpas-school-list-seal::7c1e4b9a"


def _schools_digest(rows) -> str:
    """rows: (level_type, iu_code, school_id, name) tuples; order does not matter"""
    text = "\n".join("|".join(str(x or "").strip() for x in r) for r in sorted(tuple(x) for x in rows))
    return hmac.new(_SEAL_KEY, text.encode("utf-8"), hashlib.sha256).hexdigest()


def _seal_schools(conn):
    rows = conn.execute("SELECT level_type, iu_code, school_id, name FROM schools").fetchall()
    conn.execute(
        "INSERT INTO app_settings (key, value) VALUES ('schools_seal', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (_schools_digest(rows),))


def schools_seal_ok() -> bool:
    conn = get_connection()
    try:
        rows = conn.execute("SELECT level_type, iu_code, school_id, name FROM schools").fetchall()
        row = conn.execute("SELECT value FROM app_settings WHERE key = 'schools_seal'").fetchone()
    finally:
        conn.close()
    return bool(row) and hmac.compare_digest(row[0], _schools_digest(rows))


def _bundled_schools():
    path = bundled_path("data", "schools.txt")
    out = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split(maxsplit=3)
                if len(parts) == 4:
                    out.append({"level_type": parts[0], "iu_code": parts[1],
                                "school_id": parts[2], "name": parts[3]})
    return out


def _seed_schools(conn):
    path = bundled_path("data", "schools.txt")
    if not os.path.exists(path):
        return
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split(maxsplit=3)
            if len(parts) < 4:
                continue
            level_type, iu_code, school_id, name = parts
            rows.append((level_type, iu_code, school_id, name,
                         _LEVEL_FROM_TYPE.get(level_type, "")))
    conn.executemany(
        "INSERT INTO schools (level_type, iu_code, school_id, name, level) "
        "VALUES (?, ?, ?, ?, ?)", rows,
    )
    _seal_schools(conn)


def list_schools():
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT * FROM schools ORDER BY name, level"
        ).fetchall()
    finally:
        conn.close()


SCHOOL_LEVEL_TYPES = tuple(_LEVEL_FROM_TYPE)


def replace_schools(rows):
    """rows: (level_type, iu_code, school_id, name) tuples. Replaces the whole list
    (Setup > Schools, admin only), so adding, renaming (typo fixes) and removing a
    school all flow into the next generated template and the import check.
    Blank rows are skipped; duplicates on (school_id, level_type) keep the first."""
    seen, clean = set(), []
    for level_type, iu_code, school_id, name in rows:
        level_type, iu_code = (level_type or "").strip(), (iu_code or "").strip()
        school_id, name = (school_id or "").strip(), (name or "").strip()
        if not (school_id and name and level_type):
            continue
        key = (school_id, level_type)
        if key in seen:
            continue
        seen.add(key)
        clean.append((level_type, iu_code, school_id, name,
                      _LEVEL_FROM_TYPE.get(level_type, "")))
    conn = get_connection()
    try:
        conn.execute("DELETE FROM schools")
        conn.executemany(
            "INSERT INTO schools (level_type, iu_code, school_id, name, level) "
            "VALUES (?, ?, ?, ?, ?)", clean)
        _seal_schools(conn)
        conn.commit()
    finally:
        conn.close()


def match_school(text: str):
    """Match a 'LEVEL_TYPE IU_CODE SCHOOL_ID NAME' string to a schools row."""
    parts = (text or "").split(maxsplit=3)
    if len(parts) < 3:
        return None
    return match_school_parts(parts[0], parts[1], parts[2], parts[3] if len(parts) > 3 else "")


def match_school_parts(level_type, iu_code, school_id, name=""):
    """Strict: the school ID, the level type or IU code, and the name (when given)
    must all agree with the Setup school list, so a made-up school ID or a real ID
    with a different school name is not accepted. If the school table was changed
    outside B+ (seal broken) the original bundled list is used instead."""
    level_type, iu_code, school_id = (level_type or "").strip(), (iu_code or "").strip(), (school_id or "").strip()
    name = " ".join((name or "").split()).casefold()
    if not school_id:
        return None
    if schools_seal_ok():
        conn = get_connection()
        try:
            rows = conn.execute("SELECT * FROM schools WHERE school_id = ?", (school_id,)).fetchall()
        finally:
            conn.close()
    else:                                # list was changed outside B+: use the original list
        rows = [r for r in _bundled_schools() if r["school_id"] == school_id]
    for key in (lambda r: level_type and r["level_type"] == level_type,
                lambda r: iu_code and r["iu_code"] == iu_code):
        for r in rows:
            if key(r) and (not name or " ".join((r["name"] or "").split()).casefold() == name):
                return r
    return None


MONTH_ORDER = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def _month_case(column="month"):
    whens = " ".join(
        f"WHEN '{m}' THEN {i}" for i, m in enumerate(MONTH_ORDER, start=1)
    )
    return f"CASE lower({column}) {whens.lower()} ELSE 99 END"


def _batch_where(batch_id, column="batch_id"):
    """batch_id may be a single id, a list/tuple of ids, or None/falsy (no filter).
    Returns (where_clause_or_'', params_tuple)."""
    if isinstance(batch_id, (list, tuple, set)):
        ids = [b for b in batch_id if b is not None]
        if not ids:
            return "", ()
        placeholders = ", ".join("?" for _ in ids)
        return f"{column} IN ({placeholders})", tuple(ids)
    if batch_id:
        return f"{column} = ?", (batch_id,)
    return "", ()


def monthly_totals(batch_id: int | None = None):
    where = "WHERE batch_id = ?" if batch_id else ""
    params = (batch_id,) if batch_id else ()
    conn = get_connection()
    try:
        return conn.execute(
            f"""SELECT COALESCE(NULLIF(month, ''), '(unspecified)') AS label,
                       SUM(total_amount) AS total
                FROM bpas_items {where}
                GROUP BY label
                ORDER BY {_month_case("label")}, label""",
            params,
        ).fetchall()
    finally:
        conn.close()


# ---------- app_settings ----------

def get_setting(key: str, default: str = "") -> str:
    conn = get_connection()
    try:
        row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
        return row[0] if row else default
    except sqlite3.OperationalError:
        return default
    finally:
        conn.close()


def money(unit_price, qty, rate=1.0) -> float:
    """unit price x qty x rate to the centavo, rounded half-up like Excel's ROUND (plain
    Python round() would turn 2,495.625 into 2,495.62 where the template shows 2,495.63)."""
    from decimal import Decimal, ROUND_HALF_UP
    d = Decimal(str(unit_price or 0)) * Decimal(str(qty or 0)) * Decimal(str(rate))
    return float(d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _multiplier_from(conn) -> float:
    def val(key, default):
        r = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
        return r[0] if r else default
    if val("provision_enabled", "1") != "1":
        return 1.0
    try:
        pct = float(val("provision_pct", "10"))
    except ValueError:
        pct = 10.0
    return 1.0 + max(pct, 0.0) / 100.0


def get_batch_rate(batch_id) -> float | None:
    """The Amount multiplier stored with a plan, or None when the plan has none
    (a template without BPAS_RATE or an old plan file)."""
    if batch_id is None:
        return None
    conn = get_connection()
    try:
        row = conn.execute("SELECT provision_rate FROM import_batches WHERE id = ?",
                           (batch_id,)).fetchone()
    finally:
        conn.close()
    return row[0] if row and row[0] is not None else None


def get_provision_multiplier() -> float:
    """The Amount multiplier from Setup > Tools ("Add provision for price changes"):
    1.10 for a +10% provision, 1.00 when the provision is switched off."""
    if get_setting("provision_enabled", "1") != "1":
        return 1.0
    try:
        pct = float(get_setting("provision_pct", "10"))
    except ValueError:
        pct = 10.0
    return 1.0 + max(pct, 0.0) / 100.0


def set_setting(key: str, value: str):
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO app_settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        conn.commit()
    finally:
        conn.close()


# ---------- admin password (gates the Consolidation tab) ----------

DEFAULT_ADMIN_PASSWORD = "depedbpas123"


def has_admin_password() -> bool:
    return bool(get_setting("admin_pw_hash", ""))


def set_admin_password(password: str):
    salt = secrets.token_hex(16)
    digest = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
    set_setting("admin_pw_salt", salt)
    set_setting("admin_pw_hash", digest)


def check_admin_password(password: str) -> bool:
    salt = get_setting("admin_pw_salt", "")
    stored = get_setting("admin_pw_hash", "")
    if not stored:
        return False
    digest = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
    return secrets.compare_digest(digest, stored)


PLAN_OVERRIDE_SIG_DOCS = {"ppmp", "sobp", "app"}   # global, but an imported plan can carry its own set
PER_PLAN_SIG_DOCS = {"pr", "rsq", "cashadv"}   # scoped to the active plan; ppmp/sobp are global


def list_signatories(doc: str | None = None, batch_id: int | None = None):
    conn = get_connection()
    try:
        if doc is None:
            return conn.execute(
                "SELECT * FROM signatories ORDER BY sort_order, id").fetchall()
        if doc in PER_PLAN_SIG_DOCS:
            if batch_id is None:
                return []
            return conn.execute(
                "SELECT * FROM signatories WHERE doc = ? AND batch_id = ? "
                "ORDER BY sort_order, id", (doc, batch_id)).fetchall()
        if doc in PLAN_OVERRIDE_SIG_DOCS and batch_id is not None:
            own = conn.execute(
                "SELECT * FROM signatories WHERE doc = ? AND batch_id = ? "
                "ORDER BY sort_order, id", (doc, batch_id)).fetchall()
            if own:
                return own
        return conn.execute(
            "SELECT * FROM signatories WHERE doc = ? AND batch_id IS NULL "
            "ORDER BY sort_order, id", (doc,)).fetchall()
    finally:
        conn.close()


def set_plan_signatories(rows: list[dict], doc: str, batch_id: int):
    """Give one plan its own PPMP / SOB / APP signatories (from an imported .bpasx), so its
    printouts show that school's people. The Setup set stays the default for other plans."""
    if doc not in PLAN_OVERRIDE_SIG_DOCS or not rows:
        return
    conn = get_connection()
    try:
        conn.execute("DELETE FROM signatories WHERE doc = ? AND batch_id = ?", (doc, batch_id))
        conn.executemany(
            "INSERT INTO signatories (doc, batch_id, role, name, position, sort_order) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [(doc, batch_id, (r.get("role") or "").strip(), (r.get("name") or "").strip(),
              (r.get("position") or "").strip(), i) for i, r in enumerate(rows)])
        conn.commit()
    finally:
        conn.close()


def replace_signatories(rows: list[dict], doc: str = "ppmp",
                        batch_id: int | None = None):
    """rows: [{role, name, position}] in display order. Replaces that doc's set
    (global, or scoped to `batch_id` for PR / RSQ)."""
    per_plan = doc in PER_PLAN_SIG_DOCS
    if per_plan and batch_id is None:
        return
    conn = get_connection()
    try:
        if per_plan:
            conn.execute("DELETE FROM signatories WHERE doc = ? AND batch_id = ?",
                         (doc, batch_id))
        else:
            conn.execute("DELETE FROM signatories WHERE doc = ? AND batch_id IS NULL",
                         (doc,))
        conn.executemany(
            "INSERT INTO signatories (doc, batch_id, role, name, position, sort_order) "
            "VALUES (:doc, :batch_id, :role, :name, :position, :sort_order)",
            [
                {
                    "doc": doc,
                    "batch_id": batch_id if per_plan else None,
                    "role": (r.get("role") or "").strip(),
                    "name": (r.get("name") or "").strip(),
                    "position": (r.get("position") or "").strip(),
                    "sort_order": i,
                }
                for i, r in enumerate(rows)
            ],
        )
        conn.commit()
    finally:
        conn.close()


def get_school_info() -> dict:
    return {
        "school_name": get_setting("school_name", ""),
        "school_head": get_setting("school_head", ""),
        "division": get_setting("division", ""),
        "region": get_setting("region", ""),
        "gaa_pap": get_setting("gaa_pap", ""),
    }


def save_school_info(school_name: str, school_head: str, division: str = "",
                     gaa_pap: str = "", region: str = ""):
    set_setting("school_name", school_name)
    set_setting("school_head", school_head)
    set_setting("division", (division or "").strip().upper())      # printed in capitals
    set_setting("gaa_pap", gaa_pap)
    set_setting("region", (region or "").strip().upper())


# ---------- account_codes ----------

def list_account_codes() -> dict:
    """{accounting title: UACS code} from the master list (mooe_accounts)."""
    return {r["title"]: r["code"] for r in list_mooe_accounts()}


def get_account_code(accounting_title: str) -> str:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT code FROM mooe_accounts WHERE title = ?", (accounting_title,)
        ).fetchone()
        return row[0] if row else ""
    finally:
        conn.close()


def replace_mooe_accounts(rows: list[tuple[str, str]]):
    """rows: [(code, title)] in display order. Replaces the whole master list."""
    seen, clean = set(), []
    for code, title in rows:
        code, title = (code or "").strip(), (title or "").strip()
        if title and title not in seen:
            seen.add(title)
            clean.append((title, code, len(clean)))
    conn = get_connection()
    try:
        conn.execute("DELETE FROM mooe_accounts")
        conn.executemany(
            "INSERT INTO mooe_accounts (title, code, sort_order) VALUES (?, ?, ?)", clean)
        conn.commit()
    finally:
        conn.close()


def _to_amount(text: str) -> float:
    text = (text or "").replace(",", "").replace("₱", "").replace("PHP", "").strip()
    try:
        return float(text)
    except ValueError:
        return 0.0


ALLOTMENT_KEYS = (
    "calendar_year", "school_id", "allotment_class",
    "total_allotment", "gad_allotment",
)


def get_allotment() -> dict:
    return {
        "calendar_year": get_setting("calendar_year", ""),
        "school_id": get_setting("school_id", ""),
        "allotment_class": get_setting(
            "allotment_class", "Maintenance and Other Operating Expenses (MOOE)"
        ),
        "total_allotment": _to_amount(get_setting("total_allotment", "")),
        "gad_allotment": _to_amount(get_setting("gad_allotment", "")),
    }


def save_allotment(**fields):
    for key, value in fields.items():
        if key in ALLOTMENT_KEYS:
            set_setting(key, str(value).strip())


def checking_summary(batch_id: int) -> dict:
    conn = get_connection()
    try:
        row = conn.execute(
            """SELECT COUNT(*) AS items,
                      COALESCE(SUM(total_amount), 0) AS allocated,
                      COALESCE(SUM(CASE WHEN COALESCE(gad_category, '') <> ''
                                        THEN total_amount END), 0) AS gad_allocated,
                      COALESCE(SUM(CASE WHEN COALESCE(gad_category, '') <> ''
                                        THEN 1 END), 0) AS gad_items
               FROM bpas_items WHERE batch_id = ?""",
            (batch_id,),
        ).fetchone()
        return dict(row)
    finally:
        conn.close()


def checking_status(batch_id: int | None) -> dict:
    """Balance state of a plan: targets, allocated, balances, and a `balanced` flag."""
    plan = get_plan(batch_id)
    total_target = plan["total_allotment"]
    gad_target = plan["gad_allotment"]
    allotment_set = total_target > 0 and gad_target > 0

    if batch_id is None:
        allocated = gad_allocated = 0.0
    else:
        s = checking_summary(batch_id)
        allocated = s["allocated"]
        gad_allocated = s["gad_allocated"]

    balance = round(total_target - allocated, 2)
    gad_balance = round(gad_target - gad_allocated, 2)
    if abs(balance) < 0.005:
        balance = 0.0
    if abs(gad_balance) < 0.005:
        gad_balance = 0.0

    return {
        "total_allotment": total_target,
        "gad_allotment": gad_target,
        "allocated": allocated,
        "gad_allocated": gad_allocated,
        "balance": balance,
        "gad_balance": gad_balance,
        "allotment_set": allotment_set,
        "has_plan": batch_id is not None,
        "balanced": allotment_set and batch_id is not None
                    and balance == 0.0 and gad_balance == 0.0,
    }


def app_checking(batch_id: int | None) -> dict:
    """Annual Procurement Plan checking: CSE (Part I / II / Other) vs Non-CSE vs allotment."""
    plan = get_plan(batch_id)
    out = {
        "part1": 0.0, "part2": 0.0, "other_cse": 0.0,
        "total_cse": 0.0, "total_noncse": 0.0, "total_procurement": 0.0,
        "total_allotment": plan["total_allotment"],
    }
    if batch_id is None:
        out["balance"] = round(out["total_allotment"], 2)
        return out
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT UPPER(TRIM(COALESCE(app_for, ''))) AS af,
                      UPPER(TRIM(COALESCE(app_cs, ''))) AS ac,
                      COALESCE(SUM(total_amount), 0) AS amt
               FROM bpas_items WHERE batch_id = ?
               GROUP BY af, ac""",
            (batch_id,),
        ).fetchall()
    finally:
        conn.close()
    for r in rows:
        af, ac, amt = r["af"], r["ac"], r["amt"]
        if af == "CSE":
            out["total_cse"] += amt
            if ac == "PART I":
                out["part1"] += amt
            elif ac == "PART II":
                out["part2"] += amt
            else:
                out["other_cse"] += amt
        else:
            out["total_noncse"] += amt
    out["total_procurement"] = out["total_cse"] + out["total_noncse"]
    for k in list(out):
        out[k] = round(out[k], 2)
    bal = round(out["total_allotment"] - out["total_procurement"], 2)
    out["balance"] = 0.0 if abs(bal) < 0.005 else bal
    return out


# ---------- SOBP / MDP ----------

def _month_index(m: str) -> int:
    try:
        return MONTH_ORDER.index((m or "").strip().title())
    except ValueError:
        return -1


def sobp_data(batch_id: int | None) -> dict:
    """School Operating Budget Proposal / Monthly Distribution Program for a plan.

    Returns { total_allotment, gad_allotment, months (12 labels),
              total_row: {amount, monthly[12]},
              gad_row:   {amount, monthly[12]},
              rows: [ {title, code, amount, monthly[12], pct} ... ] }  (fixed account list
              + any extra titles present in the data but not in the master list). """
    plan = get_plan(batch_id)
    total_allot = plan["total_allotment"]
    z = [0.0] * 12
    out = {
        "total_allotment": total_allot,
        "gad_allotment": plan["gad_allotment"],
        "months": [m[:3].upper() for m in MONTH_ORDER],
        "total_row": {"amount": 0.0, "monthly": list(z)},
        "gad_row": {"amount": plan["gad_allotment"], "monthly": list(z)},
        "rows": [],
    }
    master = [(r["title"], r["code"]) for r in list_mooe_accounts()]
    by_title = {t: {"code": c, "amount": 0.0, "monthly": list(z)} for t, c in master}
    order = list(by_title.keys())

    if batch_id is not None:
        conn = get_connection()
        try:
            grp = conn.execute(
                """SELECT COALESCE(NULLIF(TRIM(accounting_title), ''), '(unclassified)') AS title,
                          TRIM(month) AS month,
                          CASE WHEN COALESCE(gad_category,'') <> '' THEN 1 ELSE 0 END AS is_gad,
                          COALESCE(SUM(total_amount), 0) AS amt
                   FROM bpas_items WHERE batch_id = ?
                   GROUP BY title, month, is_gad""",
                (batch_id,),
            ).fetchall()
        finally:
            conn.close()
        for r in grp:
            title, mi, amt = r["title"], _month_index(r["month"]), r["amt"]
            if title not in by_title:
                by_title[title] = {"code": get_account_code(title),
                                   "amount": 0.0, "monthly": list(z)}
                order.append(title)
            slot = by_title[title]
            slot["amount"] += amt
            out["total_row"]["amount"] += amt
            if 0 <= mi < 12:
                slot["monthly"][mi] += amt
                out["total_row"]["monthly"][mi] += amt
                if r["is_gad"]:
                    out["gad_row"]["monthly"][mi] += amt

    for title in order:
        s = by_title[title]
        out["rows"].append({
            "title": title, "code": s["code"],
            "amount": round(s["amount"], 2),
            "monthly": [round(x, 2) for x in s["monthly"]],
            "pct": (s["amount"] / total_allot * 100) if total_allot else 0.0,
        })
    out["total_row"]["amount"] = round(out["total_row"]["amount"], 2)
    out["total_row"]["monthly"] = [round(x, 2) for x in out["total_row"]["monthly"]]
    out["gad_row"]["monthly"] = [round(x, 2) for x in out["gad_row"]["monthly"]]
    return out


# ---------- APP (Annual Procurement Plan) ----------

# CSE items are consolidated into ONE summary row (PS-DBM convention: "kindly
# indicate the summary/total amounts only"), stored under this reserved key
# rather than a real accounting_title/general_description pair.
CSE_SUMMARY_TITLE = "__CSE_SUMMARY__"
CSE_SUMMARY_DESC = "__CSE_SUMMARY__"          # the Part I row (so earlier edits stay on it)
# One CSE row per part that has items: key under the reserved title, Records label.
CSE_PARTS = (
    ("PART I", CSE_SUMMARY_DESC),
    ("PART II", "__CSE_PART_II__"),
    ("OTHER ITEMS", "__CSE_OTHER__"),
)
CSE_PART_I_MODE = "Negotiated Procurement - Agency to Agency"
CSE_DEFAULT_MODE = "Small Value Procurement"
CSE_DEFAULT_PROJECT_TITLE = "Procurement of CSE"
CSE_DEFAULT_DESCRIPTION = ("Goods, material, supply, equipment, or service used repetitively "
                          "or frequently in the day-to-day operations.")


def app_data(batch_id: int | None) -> dict:
    """Annual Procurement Plan rows, grouped by Accounting Title — Non-CSE items
    only; CSE items are consolidated into a single `cse_row` summary instead of
    being itemized (matches the real PS-DBM APP form convention).

    Returns { groups: [ {title, code, rows: [...], subtotal} ], cse_row: {...},
              total, cse_total }. `total` = Non-CSE + CSE (the whole budget)."""
    out = {"groups": [], "cse_rows": [], "total": 0.0, "cse_total": 0.0}
    if batch_id is None:
        return out
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT COALESCE(NULLIF(TRIM(accounting_title), ''), '(unclassified)') AS title,
                      COALESCE(NULLIF(TRIM(general_description), ''), '(no description)') AS gd,
                      GROUP_CONCAT(DISTINCT NULLIF(TRIM(mode_of_procurement), '')) AS modes,
                      COALESCE(SUM(total_amount), 0) AS amt
               FROM bpas_items
               WHERE batch_id = ? AND UPPER(TRIM(COALESCE(app_for, ''))) <> 'CSE'
               GROUP BY title, gd
               ORDER BY gd""",
            (batch_id,),
        ).fetchall()
        cse_items = conn.execute(
            """SELECT CASE UPPER(TRIM(COALESCE(app_cs, '')))
                        WHEN 'PART I' THEN 'PART I' WHEN 'PART II' THEN 'PART II'
                        ELSE 'OTHER ITEMS' END AS part,
                      GROUP_CONCAT(DISTINCT NULLIF(TRIM(mode_of_procurement), '')) AS modes,
                      COALESCE(SUM(total_amount), 0) AS amt
               FROM bpas_items
               WHERE batch_id = ? AND UPPER(TRIM(COALESCE(app_for, ''))) = 'CSE'
               GROUP BY part""",
            (batch_id,),
        ).fetchall()
    finally:
        conn.close()

    order = {r["title"]: i for i, r in enumerate(list_mooe_accounts())}
    details = get_app_row_details(batch_id)
    by_title = {}
    non_cse_total = 0.0
    for r in rows:
        g = by_title.setdefault(r["title"], {
            "title": r["title"], "code": get_account_code(r["title"]),
            "rows": [], "subtotal": 0.0})
        amt = round(r["amt"], 2)
        det = details.get((r["title"], r["gd"]), {})
        g["rows"].append({
            "description": r["gd"],
            "modes": (r["modes"] or "").replace(",", ", "),
            "amount": amt,
            "accounting_title": r["title"],
            "project_title": det.get("project_title") or r["gd"],
            "early_procurement": det.get("early_procurement", ""),
            "bid_criteria": det.get("bid_criteria", ""),
            "start_date": det.get("start_date", ""),
            "end_date": det.get("end_date", ""),
            "procurement_strategy": det.get("procurement_strategy", ""),
            "remarks": det.get("remarks", ""),
            "end_user_unit": det.get("end_user_unit", ""),
            "source_of_fund": det.get("source_of_fund", ""),
        })
        g["subtotal"] = round(g["subtotal"] + amt, 2)
        non_cse_total += amt
    out["groups"] = sorted(by_title.values(),
                           key=lambda g: (order.get(g["title"], len(order)), g["title"]))

    by_part = {r["part"]: r for r in cse_items}
    cse_total = 0.0
    for part, desc_key in CSE_PARTS:
        r = by_part.get(part)
        if r is None:
            continue                     # only the parts that actually have items
        det = details.get((CSE_SUMMARY_TITLE, desc_key), {})
        # the Records items are the APP data; the defaults only fill a blank mode
        # (Part I is Agency-to-Agency unless someone set something else in Records)
        modes = (r["modes"] or "").replace(",", ", ") or (
            CSE_PART_I_MODE if part == "PART I" else CSE_DEFAULT_MODE)
        amt = round(r["amt"] or 0, 2)
        cse_total += amt
        out["cse_rows"].append({
            "description": det.get("description_override") or CSE_DEFAULT_DESCRIPTION,
            "modes": modes,
            "amount": amt,
            "accounting_title": CSE_SUMMARY_TITLE,
            "is_cse_summary": True,
            "cse_desc_key": desc_key,
            "cse_part": part,
            "project_title": det.get("project_title") or CSE_DEFAULT_PROJECT_TITLE,
            "early_procurement": det.get("early_procurement", ""),
            "bid_criteria": det.get("bid_criteria", ""),
            "start_date": det.get("start_date", ""),
            "end_date": det.get("end_date", ""),
            "procurement_strategy": det.get("procurement_strategy", ""),
            "remarks": det.get("remarks", ""),
            "end_user_unit": det.get("end_user_unit", ""),
            "source_of_fund": det.get("source_of_fund", ""),
        })
    cse_total = round(cse_total, 2)
    out["cse_total"] = cse_total
    out["total"] = round(non_cse_total + cse_total, 2)
    return out


_APP_DETAIL_FIELDS = ("early_procurement", "bid_criteria", "start_date", "end_date",
                      "procurement_strategy", "remarks", "end_user_unit", "source_of_fund")


def app_projects(batch_id: int | None) -> list[dict]:
    """The Non-CSE APP rows as one flat list, A-Z by Project Title (no account-title
    groups). The same project title can appear on several rows when its contents differ
    (another description or mode of procurement). Rows with the same project title,
    description and mode — which only differ by account title — are merged into one
    row with their amounts added. `members` lists the (accounting_title,
    general_description) APP rows a row stands for, so an edit is saved to all of them."""
    merged = {}
    for g in app_data(batch_id)["groups"]:
        for r in g["rows"]:
            key = ((r["project_title"] or "").strip().lower(),
                   (r["description"] or "").strip().lower(),
                   (r["modes"] or "").strip().lower())
            m = merged.get(key)
            if m is None:
                m = merged[key] = {
                    "project_title": (r["project_title"] or "").strip(),
                    "description": r["description"], "modes": r["modes"],
                    "accounting_title": r["accounting_title"],
                    "amount": 0.0, "members": [],
                    **{f: "" for f in _APP_DETAIL_FIELDS},
                }
            m["amount"] = round(m["amount"] + r["amount"], 2)
            m["members"].append((r["accounting_title"], r["description"]))
            for f in _APP_DETAIL_FIELDS:
                if not m[f] and r.get(f):
                    m[f] = r[f]
    return sorted(merged.values(), key=lambda m: (
        m["project_title"].lower(), m["description"].lower(), m["modes"].lower()))


def get_app_row_details(batch_id: int) -> dict:
    """{(accounting_title, general_description): {project_title, early_procurement,
    bid_criteria, start_date, end_date, procurement_strategy, remarks, end_user_unit,
    source_of_fund, description_override}}"""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM app_row_details WHERE batch_id = ?", (batch_id,)).fetchall()
        return {(r["accounting_title"], r["general_description"]): dict(r) for r in rows}
    finally:
        conn.close()


def _app_project_title(details: dict, accounting_title, general_description) -> str:
    """The Project Title the APP shows for an item: the one typed for its APP row, else
    its General Description (same key normalisation as app_data)."""
    title = (accounting_title or "").strip() or "(unclassified)"
    gd = (general_description or "").strip() or "(no description)"
    return (details.get((title, gd), {}).get("project_title") or gd).strip()


def pr_project_title(batch_id: int, lines: list[dict]) -> str:
    """Project Title of a PR/JR = the APP project title(s) of its items, joined with
    " / " when the items belong to more than one project."""
    details = get_app_row_details(batch_id)
    seen = []
    for ln in lines:
        t = _app_project_title(details, ln.get("accounting_title"), ln.get("general_description"))
        if t and t not in seen:
            seen.append(t)
    return " / ".join(seen)


def save_app_row_detail(batch_id: int, accounting_title: str, general_description: str,
                        **fields):
    """fields: any of project_title, early_procurement, bid_criteria, start_date,
    end_date, procurement_strategy, remarks, end_user_unit, source_of_fund,
    description_override (the last is only meaningful for the CSE summary row)."""
    allowed = {"project_title", "early_procurement", "bid_criteria", "start_date",
              "end_date", "procurement_strategy", "remarks", "end_user_unit",
              "source_of_fund", "description_override"}
    cols = {k: (v or "").strip() for k, v in fields.items() if k in allowed}
    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT 1 FROM app_row_details WHERE batch_id = ? AND accounting_title = ? "
            "AND general_description = ?", (batch_id, accounting_title, general_description)
        ).fetchone()
        if existing:
            if cols:
                set_clause = ", ".join(f"{c} = ?" for c in cols)
                conn.execute(
                    f"UPDATE app_row_details SET {set_clause} "
                    "WHERE batch_id = ? AND accounting_title = ? AND general_description = ?",
                    [*cols.values(), batch_id, accounting_title, general_description])
        else:
            keys = ["batch_id", "accounting_title", "general_description", *cols.keys()]
            placeholders = ", ".join("?" for _ in keys)
            conn.execute(
                f"INSERT INTO app_row_details ({', '.join(keys)}) VALUES ({placeholders})",
                [batch_id, accounting_title, general_description, *cols.values()])
        conn.commit()
    finally:
        conn.close()


# ---------- PPMP ----------

def ppmp_rows(batch_id: int):
    """One aggregated line per (General Description, Item) for the whole plan.

    Items sharing a general_description are grouped under it (bold header row in
    the PPMP); each item aggregates its monthly rows.
    """
    conn = get_connection()
    try:
        return conn.execute(
            """SELECT general_description,
                      item_description,
                      GROUP_CONCAT(DISTINCT NULLIF(TRIM(accounting_title), '')) AS titles,
                      GROUP_CONCAT(DISTINCT NULLIF(TRIM(unit), '')) AS units,
                      GROUP_CONCAT(DISTINCT NULLIF(TRIM(mode_of_procurement), '')) AS modes,
                      COALESCE(SUM(total_amount), 0) AS budget,
                      COALESCE(SUM(qty), 0) AS qty,
                      GROUP_CONCAT(DISTINCT UPPER(TRIM(month))) AS months
               FROM bpas_items
               WHERE batch_id = ?
               GROUP BY general_description, item_description
               ORDER BY general_description, item_description""",
            (batch_id,),
        ).fetchall()
    finally:
        conn.close()


# ---------- Purchase Request ----------

_PR_MONTH = "COALESCE(NULLIF(TRIM(month), ''), '(no month)')"
_PR_ACCT = "COALESCE(NULLIF(TRIM(accounting_title), ''), '(no account)')"
_PR_NOT_DIRECT = "TRIM(LOWER(COALESCE(mode_of_procurement, ''))) <> 'direct contracting'"


# Legacy only: requests saved before the PR/JR type was stored are treated as JR when all
# their items are under these titles. New requests: the user picks the type freely.
JR_TITLE_PREFIXES = ("R & M", "TRAINING EXPENSES")


def is_jr_title(accounting_title: str) -> bool:
    """R & M (Repair and Maintenance) and Training Expenses titles can be requisitioned
    as a Job Request (JR) instead of a Purchase Request (PR)."""
    return (accounting_title or "").strip().upper().startswith(JR_TITLE_PREFIXES)


def pr_kind(header, lines) -> str:
    """"JR" or "PR" for a saved request. The type is chosen when the request is made
    (the same account title can be labor or materials); requests saved before that
    choice existed fall back to the old rule: all items under R & M titles = JR."""
    kind = (header.get("kind") or "").strip().upper() if header else ""
    if kind in ("PR", "JR"):
        return kind
    return "JR" if lines and all(is_jr_title(ln["accounting_title"]) for ln in lines) else "PR"


def update_pr_kind(pr_header_id: int, kind: str):
    conn = get_connection()
    try:
        conn.execute("UPDATE pr_headers SET kind = ? WHERE id = ?",
                     ((kind or "").strip().upper(), pr_header_id))
        conn.commit()
    finally:
        conn.close()


def pr_months(batch_id: int) -> list[str]:
    """Distinct planned months for this batch, in calendar order."""
    conn = get_connection()
    try:
        rows = conn.execute(
            f"""SELECT DISTINCT TRIM(month) AS m
                FROM bpas_items
                WHERE batch_id = ? AND {_PR_NOT_DIRECT}
                  AND TRIM(COALESCE(month, '')) <> ''
                ORDER BY {_month_case("month")}""",
            (batch_id,),
        ).fetchall()
        return [r["m"] for r in rows]
    finally:
        conn.close()


# A PR/JR is priced at the item's Amount / Qty, not its raw Unit Price: Amount carries the
# provision for price changes (e.g. unit price 100 today -> 110 next year at +10%).
_EFFECTIVE_PRICE_SQL = ("CASE WHEN COALESCE(qty, 0) > 0 AND COALESCE(total_amount, 0) > 0 "
                        "THEN total_amount * 1.0 / qty ELSE COALESCE(unit_price, 0) END")


def pr_buildable_items(batch_id: int, month: str) -> list[dict]:
    """Line items for a month with quantity still available to requisition.

    remaining = planned qty - sum(qty already taken on every PR for that item).
    Items with nothing remaining are dropped. Direct-Contracting items excluded.
    """
    conn = get_connection()
    try:
        rows = conn.execute(
            f"""SELECT w.id AS bpas_item_id, w.item_description, w.unit,
                       CASE WHEN COALESCE(w.qty, 0) > 0 AND COALESCE(w.total_amount, 0) > 0
                            THEN w.total_amount * 1.0 / w.qty
                            ELSE COALESCE(w.unit_price, 0) END AS unit_price,
                       w.general_description, w.accounting_title,
                       w.qty AS planned_qty,
                       COALESCE((SELECT SUM(l.qty) FROM pr_lines l
                                 WHERE l.bpas_item_id = w.id), 0) AS taken_qty
                FROM bpas_items w
                WHERE w.batch_id = ? AND {_PR_NOT_DIRECT}
                  AND TRIM(LOWER(COALESCE(w.month, ''))) = TRIM(LOWER(?))
                ORDER BY w.general_description, w.item_description""",
            (batch_id, month),
        ).fetchall()
        out = []
        details = get_app_row_details(batch_id)
        for r in rows:
            d = dict(r)
            d["project_title"] = _app_project_title(
                details, d["accounting_title"], d["general_description"])
            d["remaining_qty"] = round((d["planned_qty"] or 0) - (d["taken_qty"] or 0), 2)
            if d["remaining_qty"] > 0:
                out.append(d)
        return out
    finally:
        conn.close()


def pr_list(batch_id: int) -> list[dict]:
    """Existing PR headers for a batch, each with item count and total."""
    conn = get_connection()
    try:
        rows = conn.execute(
            f"""SELECT h.id, h.pr_no, h.pr_date, h.month, h.purpose, h.created_at,
                       h.delivery_period, h.fund_source, h.stock_no, h.kind,
                       COUNT(l.id) AS items,
                       COALESCE(SUM(l.amount), 0) AS total
                FROM pr_headers h
                LEFT JOIN pr_lines l ON l.pr_header_id = h.id
                WHERE h.batch_id = ?
                GROUP BY h.id
                ORDER BY {_month_case("h.month")}, h.pr_no""",
            (batch_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def pr_lines_for(pr_header_id: int) -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT l.id, l.bpas_item_id, l.qty, l.unit_price, l.amount,
                      w.item_description, w.unit, w.general_description,
                      w.accounting_title
               FROM pr_lines l
               JOIN bpas_items w ON w.id = l.bpas_item_id
               WHERE l.pr_header_id = ?
               ORDER BY w.general_description, w.item_description""",
            (pr_header_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def next_pr_no(batch_id: int, month: str) -> str:
    """YYYY-MM-NNN — the month part follows the PR/JR's month, but NNN is one running
    sequence for the whole plan/year: it carries over from month to month and never
    restarts at 001. It is one more than the highest number already used, so
    deleting a PR/JR leaves a gap (1,2,3 -> delete 2 -> next is 4)."""
    year = (get_allotment()["calendar_year"] or "").strip() or str(date.today().year)
    try:
        mnum = MONTH_ORDER.index((month or "").strip().title()) + 1
    except ValueError:
        mnum = 0
    conn = get_connection()
    try:
        used = {r[0] for r in conn.execute(
            "SELECT pr_no FROM pr_headers WHERE batch_id = ?", (batch_id,))}
    finally:
        conn.close()
    top = 0
    for no in used:
        m = re.fullmatch(rf"{re.escape(year)}-\d{{2}}-(\d+)", (no or "").strip())
        if m:
            top = max(top, int(m.group(1)))
    return f"{year}-{mnum:02d}-{top + 1:03d}"


def create_pr(batch_id: int, month: str, purpose: str, lines: list[dict],
              delivery_period: str = "", fund_source: str = "", stock_no: str = "",
              kind: str = "") -> int:
    """lines = [{bpas_item_id, qty}, ...]. Returns the new pr_headers.id."""
    now = datetime.now().isoformat(timespec="seconds")
    pr_no = next_pr_no(batch_id, month)
    conn = get_connection()
    try:
        prices = {
            r["id"]: r["unit_price"] or 0
            for r in conn.execute(
                f"SELECT id, {_EFFECTIVE_PRICE_SQL} AS unit_price FROM bpas_items WHERE batch_id = ?",
                (batch_id,)
            )
        }
        cur = conn.execute(
            """INSERT INTO pr_headers (batch_id, pr_no, pr_date, month, purpose, created_at,
                                       delivery_period, fund_source, stock_no, kind)
               VALUES (?, ?, '', ?, ?, ?, ?, ?, ?, ?)""",
            (batch_id, pr_no, month, (purpose or "").strip(), now,
             (delivery_period or "").strip(), (fund_source or "").strip(),
             (stock_no or "").strip(), (kind or "").strip().upper()),
        )
        header_id = cur.lastrowid
        for ln in lines:
            qty = round(float(ln["qty"] or 0), 2)
            if qty <= 0:
                continue
            price = prices.get(ln["bpas_item_id"], 0)
            conn.execute(
                """INSERT INTO pr_lines (pr_header_id, bpas_item_id, qty, unit_price, amount)
                   VALUES (?, ?, ?, ?, ?)""",
                (header_id, ln["bpas_item_id"], qty, price, money(price, qty)),
            )
        conn.commit()
        return header_id
    finally:
        conn.close()


def get_pr_header(pr_header_id: int) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM pr_headers WHERE id = ?", (pr_header_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def add_pr_lines(pr_header_id: int, batch_id: int, lines: list[dict]):
    """lines = [{bpas_item_id, qty}, ...]. Appends items to an existing PR
    (same month/pool rules as create_pr — caller must source them from
    pr_buildable_items for that PR's month)."""
    conn = get_connection()
    try:
        prices = {
            r["id"]: r["unit_price"] or 0
            for r in conn.execute(
                f"SELECT id, {_EFFECTIVE_PRICE_SQL} AS unit_price FROM bpas_items WHERE batch_id = ?",
                (batch_id,)
            )
        }
        for ln in lines:
            qty = round(float(ln["qty"] or 0), 2)
            if qty <= 0:
                continue
            price = prices.get(ln["bpas_item_id"], 0)
            conn.execute(
                """INSERT INTO pr_lines (pr_header_id, bpas_item_id, qty, unit_price, amount)
                   VALUES (?, ?, ?, ?, ?)""",
                (pr_header_id, ln["bpas_item_id"], qty, price, round(qty * price, 2)),
            )
        conn.commit()
    finally:
        conn.close()


def pr_no_taken(batch_id: int, pr_no: str, exclude_id: int | None = None) -> bool:
    """True if another PR/JR in this plan already uses `pr_no` (case-insensitive)."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT 1 FROM pr_headers WHERE batch_id = ? AND LOWER(TRIM(pr_no)) = LOWER(?) "
            "AND id <> ?", (batch_id, (pr_no or "").strip(), exclude_id or -1)).fetchone()
        return row is not None
    finally:
        conn.close()


def update_pr_no(pr_header_id: int, pr_no: str):
    conn = get_connection()
    try:
        conn.execute("UPDATE pr_headers SET pr_no = ? WHERE id = ?",
                     ((pr_no or "").strip(), pr_header_id))
        conn.commit()
    finally:
        conn.close()


def update_pr_purpose(pr_header_id: int, purpose: str):
    conn = get_connection()
    try:
        conn.execute("UPDATE pr_headers SET purpose = ? WHERE id = ?",
                     ((purpose or "").strip(), pr_header_id))
        conn.commit()
    finally:
        conn.close()


def update_pr_extra(pr_header_id: int, delivery_period: str = "", fund_source: str = "",
                    stock_no: str = ""):
    conn = get_connection()
    try:
        conn.execute(
            """UPDATE pr_headers SET delivery_period = ?, fund_source = ?, stock_no = ?
               WHERE id = ?""",
            ((delivery_period or "").strip(), (fund_source or "").strip(),
             (stock_no or "").strip(), pr_header_id),
        )
        conn.commit()
    finally:
        conn.close()


def delete_pr(pr_header_id: int):
    conn = get_connection()
    try:
        conn.execute("DELETE FROM pr_headers WHERE id = ?", (pr_header_id,))
        conn.commit()
    finally:
        conn.close()


# ---------- MOOE Request for Cash Advance ----------

def cashadv_buildable_items(batch_id: int, month: str) -> list[dict]:
    """PPMP line items planned for a month — source rows for the cash advance letter."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT id AS bpas_item_id, pap_name, general_description, item_description,
                      accounting_title, total_amount
               FROM bpas_items
               WHERE batch_id = ? AND TRIM(LOWER(COALESCE(month, ''))) = TRIM(LOWER(?))
               ORDER BY pap_name, general_description, item_description""",
            (batch_id, month),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def cashadv_breakdown(batch_id: int, month: str) -> dict:
    """Breakdown of Expenses for a month: account-code totals + grand total."""
    conn = get_connection()
    try:
        grp = conn.execute(
            """SELECT COALESCE(NULLIF(TRIM(accounting_title), ''), '(unclassified)') AS title,
                      COALESCE(SUM(total_amount), 0) AS amt
               FROM bpas_items
               WHERE batch_id = ? AND TRIM(LOWER(COALESCE(month, ''))) = TRIM(LOWER(?))
               GROUP BY title
               ORDER BY title""",
            (batch_id, month),
        ).fetchall()
    finally:
        conn.close()
    rows = [{"title": r["title"], "code": get_account_code(r["title"]),
             "amount": round(r["amt"], 2)} for r in grp]
    return {"rows": rows, "total": round(sum(r["amount"] for r in rows), 2)}


# ---------- import_batches ----------

def create_batch(file_name: str, label: str = "") -> int:
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO import_batches (file_name, imported_at, label) VALUES (?, ?, ?)",
            (file_name, datetime.now().isoformat(timespec="seconds"), label),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def list_batches():
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT * FROM import_batches ORDER BY imported_at DESC"
        ).fetchall()
    finally:
        conn.close()


# ---------- active plan (one imported batch is "active" at a time) ----------

def find_batches_for_school(school_id, level_type) -> list[int]:
    """Ids of plans already in the database for this school ID + level type."""
    school_id, level_type = (school_id or "").strip(), (level_type or "").strip()
    if not school_id:
        return []
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id FROM import_batches WHERE school_id = ? AND COALESCE(level_type, '') = ? "
            "ORDER BY imported_at", (school_id, level_type)).fetchall()
        return [r["id"] for r in rows]
    finally:
        conn.close()


def get_active_batch() -> int | None:
    batches = list_batches()
    if not batches:
        return None
    ids = [b["id"] for b in batches]
    raw = get_setting("active_batch", "")
    try:
        current = int(raw)
    except ValueError:
        current = None
    if current not in ids:
        current = batches[0]["id"]           # most recent
        set_setting("active_batch", str(current))
    return current


def set_active_batch(batch_id: int):
    set_setting("active_batch", str(batch_id))


def set_batch_plan(batch_id: int, **fields):
    cols = [k for k in fields if k in _BATCH_PLAN_COLS]
    if not cols:
        return
    conn = get_connection()
    try:
        conn.execute(
            f"UPDATE import_batches SET {', '.join(f'{c} = ?' for c in cols)} WHERE id = ?",
            [fields[c] for c in cols] + [batch_id],
        )
        conn.commit()
    finally:
        conn.close()


def get_plan(batch_id: int | None) -> dict:
    """Plan-scoped context for a batch, with fallback to the global Setup values."""
    info = get_school_info()
    allot = get_allotment()
    plan = {
        "school_name": "", "school_id": allot["school_id"], "iu_code": "",
        "level_type": "", "level": "", "school_head": info["school_head"],
        "total_allotment": allot["total_allotment"],
        "gad_allotment": allot["gad_allotment"],
    }
    if batch_id is None:
        return plan
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM import_batches WHERE id = ?", (batch_id,)
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return plan
    row = dict(row)
    for k in ("school_name", "school_id", "iu_code", "level_type", "level"):
        if row.get(k):
            plan[k] = row[k]
    if row.get("school_head"):
        plan["school_head"] = row["school_head"]
    if row.get("total_allotment"):
        plan["total_allotment"] = row["total_allotment"]
    if row.get("gad_allotment"):
        plan["gad_allotment"] = row["gad_allotment"]
    return plan


def delete_batch(batch_id: int):
    conn = get_connection()
    try:
        conn.execute("DELETE FROM signatories WHERE batch_id = ?", (batch_id,))
        conn.execute("DELETE FROM import_batches WHERE id = ?", (batch_id,))
        conn.commit()
    finally:
        conn.close()
    if get_setting("active_batch", "") == str(batch_id):
        set_setting("active_batch", "")   # get_active_batch() will fall back


# ---------- bpas_items ----------

def insert_items(batch_id: int, rows: list[dict]):
    conn = get_connection()
    try:
        conn.executemany(
            """
            INSERT INTO bpas_items (
                batch_id, category_uacs_school, pap_name, general_description,
                item_description, gad_category, accounting_title, mode_of_procurement,
                app_for, app_cs, unit_price, qty, unit, month, total_amount
            ) VALUES (
                :batch_id, :category_uacs_school, :pap_name, :general_description,
                :item_description, :gad_category, :accounting_title, :mode_of_procurement,
                :app_for, :app_cs, :unit_price, :qty, :unit, :month, :total_amount
            )
            """,
            [{**r, "batch_id": batch_id} for r in rows],
        )
        conn.commit()
    finally:
        conn.close()


def query_items(filters: dict | None = None):
    """filters: batch_id (int or list, for consolidated views), pap_name, gad_category,
    accounting_title, mode_of_procurement, search"""
    filters = filters or {}
    clauses = []
    params = []

    bclause, bparams = _batch_where(filters.get("batch_id"), "bpas_items.batch_id")
    if bclause:
        clauses.append(bclause)
        params.extend(bparams)
    if filters.get("pap_name"):
        clauses.append("bpas_items.pap_name = ?")
        params.append(filters["pap_name"])
    if filters.get("gad_category"):
        clauses.append("bpas_items.gad_category = ?")
        params.append(filters["gad_category"])
    if filters.get("accounting_title"):
        clauses.append("bpas_items.accounting_title = ?")
        params.append(filters["accounting_title"])
    if filters.get("mode_of_procurement"):
        clauses.append("bpas_items.mode_of_procurement = ?")
        params.append(filters["mode_of_procurement"])
    if filters.get("search"):
        clauses.append(
            "(bpas_items.pap_name LIKE ? OR bpas_items.item_description LIKE ? "
            "OR bpas_items.general_description LIKE ?)"
        )
        like = f"%{filters['search']}%"
        params.extend([like, like, like])

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    sql = f"""
        SELECT bpas_items.*, import_batches.label AS batch_label,
               import_batches.file_name AS batch_file_name
        FROM bpas_items
        JOIN import_batches ON import_batches.id = bpas_items.batch_id
        {where}
        ORDER BY bpas_items.id
    """
    conn = get_connection()
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def update_item(item_id: int, fields: dict):
    if not fields:
        return
    set_clause = ", ".join(f"{k} = ?" for k in fields.keys())
    params = list(fields.values()) + [item_id]
    conn = get_connection()
    try:
        conn.execute(f"UPDATE bpas_items SET {set_clause} WHERE id = ?", params)
        conn.commit()
    finally:
        conn.close()


def delete_item(item_id: int):
    conn = get_connection()
    try:
        conn.execute("DELETE FROM bpas_items WHERE id = ?", (item_id,))
        conn.commit()
    finally:
        conn.close()


def distinct_values(column: str, batch_id: int | list | None = None):
    allowed = {
        "pap_name", "gad_category", "accounting_title", "mode_of_procurement",
        "general_description", "category_uacs_school", "app_for", "app_cs", "unit",
        "month",
    }
    if column not in allowed:
        raise ValueError(f"Column not filterable: {column}")
    clause, params = _batch_where(batch_id)
    where = f"WHERE {clause} AND " if clause else "WHERE "
    conn = get_connection()
    try:
        rows = conn.execute(
            f"SELECT DISTINCT {column} FROM bpas_items "
            f"{where}{column} IS NOT NULL AND {column} != '' ORDER BY {column}",
            params,
        ).fetchall()
        return [r[0] for r in rows]
    finally:
        conn.close()


def totals_by(column: str, batch_id: int | list | None = None):
    allowed = {
        "pap_name", "gad_category", "accounting_title", "mode_of_procurement",
    }
    if column not in allowed:
        raise ValueError(f"Column not groupable: {column}")
    clause, params = _batch_where(batch_id)
    where = f"WHERE {clause}" if clause else ""
    conn = get_connection()
    try:
        rows = conn.execute(
            f"SELECT {column} AS label, SUM(total_amount) AS total "
            f"FROM bpas_items {where} GROUP BY {column} ORDER BY total DESC",
            params,
        ).fetchall()
        return rows
    finally:
        conn.close()


# ---------- consolidation (multi-batch, grouped by school level) ----------

def list_levels() -> list[str]:
    """Distinct non-empty `level` values across all imported batches, in a
    sensible school-progression order."""
    order = ["Elementary", "Junior High", "Senior High", "Integrated"]
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT DISTINCT level FROM import_batches "
            "WHERE level IS NOT NULL AND level != '' ORDER BY level"
        ).fetchall()
        levels = [r[0] for r in rows]
    finally:
        conn.close()
    return sorted(levels, key=lambda l: (order.index(l) if l in order else len(order), l))


def batches_for_level(level: str) -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, school_name, school_id, level FROM import_batches "
            "WHERE level = ? ORDER BY school_name, id", (level,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
