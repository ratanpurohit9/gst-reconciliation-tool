"""Portable, user-held reconciliation memory for Streamlit deployments.

This database is meant to be uploaded/downloaded by the user.  The app should
keep only a per-session temporary copy and must never use a shared server path.
"""
from __future__ import annotations

import hashlib
import io
import re
import sqlite3
import tempfile
import unicodedata
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping
from contextlib import contextmanager

SCHEMA_VERSION = 1
TABLES = ("meta", "decisions", "run_lines", "runs")


def normalize_invoice_number(value: Any) -> str:
    """Normalize common punctuation/case differences without dropping letters."""
    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", str(value)).strip().upper()
    text = re.sub(r"\.0+$", "", text)
    return re.sub(r"[^A-Z0-9]", "", text)


def make_row_id(gstin: Any, invoice_number: Any, side: str,
                document_type: Any = "", financial_year: Any = "") -> str:
    """Stable ID: identity fields only; amounts and dataframe positions are excluded."""
    side = str(side).strip().upper()
    if side not in {"B", "G"}:
        raise ValueError("side must be 'B' (books) or 'G' (GSTR)")
    parts = [str(gstin or "").strip().upper(), normalize_invoice_number(invoice_number),
             side, normalize_invoice_number(document_type), str(financial_year or "").strip()]
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:32]


def assign_row_ids(frame, *, side: str, gstin_col: str = "GSTIN",
                   invoice_col: str = "Invoice Number", document_col: str | None = None,
                   fy_col: str | None = None, row_id_col: str = "Row ID"):
    """Return a copy with stable Row IDs, never using dataframe indexes as keys."""
    missing = [c for c in (gstin_col, invoice_col) if c not in frame.columns]
    if missing:
        raise KeyError(f"Missing identity column(s): {', '.join(missing)}")
    out = frame.copy()
    out[row_id_col] = [make_row_id(row[gstin_col], row[invoice_col], side,
                                   row.get(document_col, "") if document_col else "",
                                   row.get(fy_col, "") if fy_col else "")
                       for _, row in out.iterrows()]
    return out


@contextmanager
def _connect(path: str | Path):
    db = sqlite3.connect(str(path))
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def create_memory(path: str | Path, client: str, financial_year: str) -> None:
    """Create a new, compact memory file for one client and FY."""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with _connect(path) as db:
        db.executescript("""
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE runs (
            run_id TEXT PRIMARY KEY, month TEXT NOT NULL, return_type TEXT NOT NULL,
            run_date TEXT NOT NULL
        );
        CREATE TABLE run_lines (
            run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
            row_id TEXT NOT NULL, side TEXT NOT NULL, gstin TEXT, inv_no TEXT,
            inv_date TEXT, taxable REAL, igst REAL, cgst REAL, sgst REAL, cess REAL,
            engine_status TEXT, final_status TEXT, match_method TEXT,
            first_seen TEXT NOT NULL, amount_then REAL,
            PRIMARY KEY (run_id, row_id)
        );
        CREATE INDEX run_lines_row_id ON run_lines(row_id);
        CREATE TABLE decisions (
            row_id TEXT PRIMARY KEY, decision TEXT NOT NULL, linked_row_id TEXT,
            amount_then REAL, reason TEXT, decided_on TEXT NOT NULL
        );
        """)
        db.executemany("INSERT INTO meta(key,value) VALUES (?,?)", [
            ("client", str(client).strip()), ("financial_year", str(financial_year).strip()),
            ("schema_version", str(SCHEMA_VERSION)), ("created_date", now), ("last_updated", now),
        ])


def validate_memory(path: str | Path, client: str, financial_year: str) -> dict[str, str]:
    with _connect(path) as db:
        meta = dict(db.execute("SELECT key,value FROM meta"))
    if int(meta.get("schema_version", -1)) != SCHEMA_VERSION:
        raise ValueError(f"Unsupported memory schema version: {meta.get('schema_version', 'missing')}")
    if meta.get("client", "").casefold() != str(client).strip().casefold():
        raise ValueError(f"Memory belongs to {meta.get('client', 'unknown client')!r}, not {client!r}")
    if meta.get("financial_year", "").casefold() != str(financial_year).strip().casefold():
        raise ValueError("Memory financial year does not match the selected financial year")
    return meta


def open_uploaded_memory(uploaded_bytes: bytes, client: str, financial_year: str,
                         directory: str | Path | None = None) -> str:
    """Write an upload to a unique temp path, validate it, and return that path."""
    root = Path(directory) if directory else Path(tempfile.gettempdir())
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix="gst-memory-", suffix=".db", dir=root, delete=False) as f:
        f.write(uploaded_bytes)
        path = f.name
    try:
        validate_memory(path, client, financial_year)
    except Exception:
        Path(path).unlink(missing_ok=True)
        raise
    return path


def export_memory(path: str | Path) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def save_run(path: str | Path, run_id: str, month: str, return_type: str,
             rows: Iterable[Mapping[str, Any]], run_date: str | None = None) -> None:
    """Replace one month/return snapshot; preserve first-seen dates across reruns."""
    run_date = run_date or date.today().isoformat()
    return_type = str(return_type).upper()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with _connect(path) as db:
        db.execute("""DELETE FROM runs WHERE month=? AND return_type=?""", (month, return_type))
        db.execute("INSERT INTO runs VALUES (?,?,?,?)", (run_id, month, return_type, run_date))
        for row in rows:
            row_id = str(row["row_id"])
            prev = db.execute("""SELECT MIN(first_seen) FROM run_lines
                JOIN runs USING(run_id) WHERE row_id=? AND month<>?""", (row_id, month)).fetchone()[0]
            first_seen = prev or run_date
            db.execute("""INSERT INTO run_lines
                (run_id,row_id,side,gstin,inv_no,inv_date,taxable,igst,cgst,sgst,cess,
                 engine_status,final_status,match_method,first_seen,amount_then)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
                run_id, row_id, row.get("side", ""), row.get("gstin"), row.get("inv_no"),
                row.get("inv_date"), row.get("taxable"), row.get("igst"), row.get("cgst"),
                row.get("sgst"), row.get("cess"), row.get("engine_status"),
                row.get("final_status", row.get("engine_status")), row.get("match_method"),
                first_seen, row.get("amount_then", row.get("taxable"))))
        db.execute("UPDATE meta SET value=? WHERE key='last_updated'", (now,))


def list_decisions(path: str | Path) -> list[dict[str, Any]]:
    with _connect(path) as db:
        return [dict(r) for r in db.execute("SELECT * FROM decisions ORDER BY decided_on DESC")]


def unresolved_rows(path: str | Path) -> list[dict[str, Any]]:
    with _connect(path) as db:
        rows = db.execute("""SELECT l.*, r.month, r.return_type FROM run_lines l
            JOIN runs r USING(run_id) WHERE r.run_date=(SELECT MAX(run_date) FROM runs)
            ORDER BY l.inv_date, l.gstin, l.inv_no""").fetchall()
        return [dict(r) for r in rows if r["final_status"] not in
                {"Matched", "Matched (manual)", "Accepted difference"}]


def touch_updated(path: str | Path) -> None:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with _connect(path) as db:
        db.execute("UPDATE meta SET value=? WHERE key='last_updated'", (now,))


