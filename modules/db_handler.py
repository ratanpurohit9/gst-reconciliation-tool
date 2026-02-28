# modules/db_handler.py — v4.1 (Cloud-compatible)
# Uses /tmp for DB on cloud (writable), local path on Windows EXE

import sqlite3
import pandas as pd
import json
import datetime
import io
import os
import platform
import numpy as np


# ── DB Path: writable on both Cloud (Linux /tmp) and Local (same folder) ─────
def _get_db_path() -> str:
    if platform.system() == "Linux":
        # Streamlit Cloud — use /tmp which is always writable
        return "/tmp/recon_history.db"
    else:
        # Local Windows EXE — keep DB next to the app
        base = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(base, '..', 'recon_history.db')

DB_PATH = _get_db_path()


# ── JSON encoder that handles numpy int64 / float64 / bool ──────────────────
class _SafeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (np.integer,)):   return int(obj)
        if isinstance(obj, (np.floating,)):  return float(obj)
        if isinstance(obj, (np.bool_,)):     return bool(obj)
        if isinstance(obj, (np.ndarray,)):   return obj.tolist()
        return super().default(obj)

def _dumps(obj) -> str:
    return json.dumps(obj, cls=_SafeEncoder)


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute('''
        CREATE TABLE IF NOT EXISTS history (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            gstin             TEXT,
            company_name      TEXT,
            fy                TEXT,
            period            TEXT,
            timestamp         DATETIME,
            data_json         TEXT,
            cdnr_json         TEXT,
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

    # Migrate older DBs
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
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    data_json   = df.to_json(orient='split', date_format='iso')
    b2b_summary = _dumps(_build_b2b_summary(df))
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
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql(
        "SELECT id, company_name, gstin, period, fy, timestamp FROM history ORDER BY id DESC",
        conn)
    conn.close()
    return df


def load_reconciliation(record_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "SELECT gstin, company_name, fy, period, data_json, cdnr_json, cdnr_summary_json FROM history WHERE id=?",
        (record_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        return None, None, None, None
    meta   = {'gstin': row[0], 'company_name': row[1], 'fy': row[2], 'period': row[3]}
    df_b2b = pd.read_json(io.StringIO(row[4]), orient='split') if row[4] else pd.DataFrame()
    df_cdnr, cdnr_summary = None, None
    if row[5]:
        try:   df_cdnr = pd.read_json(io.StringIO(row[5]), orient='split')
        except: df_cdnr = None
    if row[6]:
        try:   cdnr_summary = json.loads(row[6])
        except: cdnr_summary = None
    return meta, df_b2b, df_cdnr, cdnr_summary


def delete_reconciliation(record_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM history   WHERE id=?", (record_id,))
    c.execute("DELETE FROM audit_log WHERE recon_id=?", (record_id,))
    conn.commit()
    conn.close()


def save_cdnr_to_history(record_id, df_cdnr, cdnr_summary):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "UPDATE history SET cdnr_json=?, cdnr_summary_json=? WHERE id=?",
        (df_cdnr.to_json(orient='split', date_format='iso'),
         _dumps(cdnr_summary),
         record_id))
    conn.commit()
    conn.close()


def log_action(recon_id, action_type, details):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT INTO audit_log (recon_id, timestamp, action_type, details) VALUES (?,?,?,?)",
        (recon_id, datetime.datetime.now().isoformat(), action_type, _dumps(details)))
    conn.commit()
    conn.close()


def get_audit_log(recon_id):
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql(
        "SELECT timestamp, action_type, details FROM audit_log WHERE recon_id=? ORDER BY id DESC",
        conn, params=(recon_id,))
    conn.close()
    return df
