# modules/db_handler.py  — v4.0
# Architecture improvements:
#   - Stores CDNR results alongside B2B in the same history record
#   - Adds audit_log table for traceability
#   - Auto-migrates existing DB (adds columns without breaking old data)

import sqlite3
import pandas as pd
import json
import datetime
import io
import numpy as np

DB_NAME = "recon_history.db"


# ── JSON encoder that handles numpy int64 / float64 / bool ──────────────────
class _SafeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, (np.bool_,)):
            return bool(obj)
        if isinstance(obj, (np.ndarray,)):
            return obj.tolist()
        return super().default(obj)

def _dumps(obj) -> str:
    """json.dumps using the numpy-safe encoder."""
    return json.dumps(obj, cls=_SafeEncoder)


def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    c.execute('''
        CREATE TABLE IF NOT EXISTS history (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            gstin           TEXT,
            company_name    TEXT,
            fy              TEXT,
            period          TEXT,
            timestamp       DATETIME,
            data_json       TEXT,
            cdnr_json       TEXT,
            cdnr_summary_json TEXT,
            b2b_summary_json  TEXT
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS audit_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            recon_id    INTEGER,
            timestamp   DATETIME,
            action_type TEXT,
            details     TEXT
        )
    ''')

    # Migrate older DBs that don't have new columns
    existing_cols = [row[1] for row in c.execute("PRAGMA table_info(history)").fetchall()]
    for col, coltype in [
        ("cdnr_json",          "TEXT"),
        ("cdnr_summary_json",  "TEXT"),
        ("b2b_summary_json",   "TEXT"),
    ]:
        if col not in existing_cols:
            c.execute(f"ALTER TABLE history ADD COLUMN {col} {coltype}")

    conn.commit()
    conn.close()
    init_followup_table()


def _build_b2b_summary(df):
    try:
        return {
            "total_books_taxable": float(df['Taxable Value_BOOKS'].fillna(0).sum()),
            "total_gst_taxable":   float(df['Taxable Value_GST'].fillna(0).sum()),
            "status_counts":       df['Recon_Status'].value_counts().to_dict(),
            "total_rows":          len(df),
        }
    except Exception:
        return {}


def save_reconciliation(meta, df):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    data_json    = df.to_json(orient='split', date_format='iso')
    b2b_summary  = _dumps(_build_b2b_summary(df))
    c.execute('''
        INSERT INTO history
            (gstin, company_name, fy, period, timestamp, data_json, b2b_summary_json)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (meta['gstin'], meta['name'], meta['fy'], meta['period'],
          datetime.datetime.now().isoformat(), data_json, b2b_summary))
    record_id = c.lastrowid
    conn.commit()
    conn.close()
    return record_id


def get_history_list():
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql(
        "SELECT id, company_name, gstin, period, fy, timestamp FROM history ORDER BY id DESC",
        conn)
    conn.close()
    return df


def load_reconciliation(record_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute(
        "SELECT gstin, company_name, fy, period, data_json, cdnr_json, cdnr_summary_json FROM history WHERE id=?",
        (record_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        return None, None, None, None
    meta = {'gstin': row[0], 'company_name': row[1], 'fy': row[2], 'period': row[3]}
    df_b2b = pd.read_json(io.StringIO(row[4]), orient='split') if row[4] else pd.DataFrame()
    df_cdnr, cdnr_summary = None, None
    if row[5]:
        try:
            df_cdnr = pd.read_json(io.StringIO(row[5]), orient='split')
        except Exception:
            df_cdnr = None
    if row[6]:
        try:
            cdnr_summary = json.loads(row[6])
        except Exception:
            cdnr_summary = None
    return meta, df_b2b, df_cdnr, cdnr_summary


def delete_reconciliation(record_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("DELETE FROM history   WHERE id=?", (record_id,))
    c.execute("DELETE FROM audit_log WHERE recon_id=?", (record_id,))
    conn.commit()
    conn.close()


def save_cdnr_to_history(record_id, df_cdnr, cdnr_summary):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute(
        "UPDATE history SET cdnr_json=?, cdnr_summary_json=? WHERE id=?",
        (df_cdnr.to_json(orient='split', date_format='iso'),
         _dumps(cdnr_summary),
         record_id))
    conn.commit()
    conn.close()


def log_action(recon_id, action_type, details):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute(
        "INSERT INTO audit_log (recon_id, timestamp, action_type, details) VALUES (?,?,?,?)",
        (recon_id, datetime.datetime.now().isoformat(), action_type, _dumps(details)))
    conn.commit()
    conn.close()


def get_audit_log(recon_id):
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql(
        "SELECT timestamp, action_type, details FROM audit_log WHERE recon_id=? ORDER BY id DESC",
        conn, params=(recon_id,))
    conn.close()
    return df


# ══════════════════════════════════════════════════════════════════════════════
# VENDOR FOLLOW-UP TRACKER
# ══════════════════════════════════════════════════════════════════════════════

def init_followup_table():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS vendor_followups (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            recon_id        INTEGER,
            vendor_name     TEXT,
            gstin           TEXT,
            notice_sent_date TEXT,
            status          TEXT DEFAULT 'Pending',
            notes           TEXT DEFAULT '',
            issue_count     INTEGER DEFAULT 0,
            itc_at_risk     REAL DEFAULT 0.0,
            last_updated    DATETIME
        )
    ''')
    conn.commit()
    conn.close()


def upsert_followup(recon_id, vendor_name, gstin, issue_count=0, itc_at_risk=0.0):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute(
        "SELECT id FROM vendor_followups WHERE recon_id=? AND vendor_name=?",
        (recon_id, vendor_name)
    )
    if not c.fetchone():
        c.execute('''
            INSERT INTO vendor_followups
                (recon_id, vendor_name, gstin, notice_sent_date, status, notes, issue_count, itc_at_risk, last_updated)
            VALUES (?,?,?,?,?,?,?,?,?)
        ''', (recon_id, vendor_name, gstin, None, 'Pending', '',
              issue_count, itc_at_risk, datetime.datetime.now().isoformat()))
    conn.commit()
    conn.close()


def save_followup_notice_sent(recon_id, vendor_name):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    today = datetime.date.today().isoformat()
    c.execute(
        "UPDATE vendor_followups SET notice_sent_date=?, status='Pending', last_updated=? WHERE recon_id=? AND vendor_name=?",
        (today, datetime.datetime.now().isoformat(), recon_id, vendor_name)
    )
    conn.commit()
    conn.close()


def update_followup_status(recon_id, vendor_name, status, notes=''):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute(
        "UPDATE vendor_followups SET status=?, notes=?, last_updated=? WHERE recon_id=? AND vendor_name=?",
        (status, notes, datetime.datetime.now().isoformat(), recon_id, vendor_name)
    )
    conn.commit()
    conn.close()


def get_followups(recon_id):
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql(
        "SELECT * FROM vendor_followups WHERE recon_id=? ORDER BY itc_at_risk DESC",
        conn, params=(recon_id,)
    )
    conn.close()
    return df


def get_overdue_followups(days=7):
    conn = sqlite3.connect(DB_NAME)
    cutoff = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
    df = pd.read_sql('''
        SELECT f.vendor_name, f.notice_sent_date, f.status, f.itc_at_risk,
               h.company_name, h.period, f.recon_id
        FROM vendor_followups f
        JOIN history h ON h.id = f.recon_id
        WHERE f.notice_sent_date <= ? AND f.status IN ('Pending','Escalated')
        ORDER BY f.notice_sent_date ASC
    ''', conn, params=(cutoff,))
    conn.close()
    return df


# ══════════════════════════════════════════════════════════════════════════════
# MULTI-CLIENT ITC DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════

def get_all_clients_itc_summary():
    conn = sqlite3.connect(DB_NAME)
    try:
        df_hist = pd.read_sql(
            "SELECT id, company_name, gstin, period, fy, timestamp, b2b_summary_json FROM history ORDER BY id DESC",
            conn
        )
    except Exception:
        conn.close()
        return pd.DataFrame()
    conn.close()

    if df_hist.empty:
        return pd.DataFrame()

    rows = []
    seen = set()
    for _, row in df_hist.iterrows():
        key = (str(row['company_name']).strip(), str(row['gstin']).strip())
        if key in seen:
            continue
        seen.add(key)
        unmatched = 0
        try:
            summary = json.loads(row['b2b_summary_json'] or '{}')
            sc = summary.get('status_counts', {})
            unmatched = sum(sc.get(k, 0) for k in sc if 'Not in' in k)
        except Exception:
            pass
        rows.append({
            'Client':        row['company_name'],
            'GSTIN':         row['gstin'],
            'Last Period':   f"{row.get('fy','—')} | {row['period']}",
            'Last Recon':    str(row['timestamp'])[:10],
            'Unmatched Inv': unmatched,
            'recon_id':      row['id'],
        })
    return pd.DataFrame(rows)


# ══════════════════════════════════════════════════════════════════════════════
# MONTH-OVER-MONTH COMPARISON
# ══════════════════════════════════════════════════════════════════════════════

def compare_two_recons(id1, id2):
    def _vendor_summary(df):
        mask = df['Recon_Status'].str.contains('Not in|Mismatch|Suggestion|Manual|Tax Error', na=False)
        sub  = df[mask].copy()
        return sub.groupby('Name of Party').agg(
            issue_count=('Recon_Status', 'count'),
            itc_value  =('Final_Taxable', 'sum')
        ).reset_index()

    _, df1, _, _ = load_reconciliation(id1)
    _, df2, _, _ = load_reconciliation(id2)

    if df1 is None or df2 is None:
        return pd.DataFrame()

    s1 = _vendor_summary(df1).rename(columns={'issue_count': 'issues_old', 'itc_value': 'itc_old'})
    s2 = _vendor_summary(df2).rename(columns={'issue_count': 'issues_new', 'itc_value': 'itc_new'})

    merged = pd.merge(s1, s2, on='Name of Party', how='outer').fillna(0)
    merged['delta'] = merged['issues_new'] - merged['issues_old']
    merged['trend'] = merged['delta'].apply(
        lambda d: '✅ Improved' if d < 0 else ('🆕 New Issue' if d > 0 else '➡️ No Change')
    )
    return merged.sort_values('issues_new', ascending=False)