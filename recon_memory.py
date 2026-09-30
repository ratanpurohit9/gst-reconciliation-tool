"""Portable, user-held reconciliation memory for Streamlit deployments.

This database is meant to be uploaded/downloaded by the user.  The app should
keep only a per-session temporary copy and must never use a shared server path.
"""
from __future__ import annotations

import hashlib
import math
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


def memory_filename(client: str, financial_year: str, on_date: date | None = None) -> str:
    """Build the portable download name requested by the memory-file workflow."""
    safe_client = re.sub(r"[^A-Za-z0-9._-]+", "_", str(client).strip()).strip("._-") or "Client"
    years = re.findall(r"\d{4}", str(financial_year))
    fy = f"{years[0]}-{years[-1][-2:]}" if len(years) >= 2 else re.sub(r"\s+", "", str(financial_year))
    return f"{safe_client}_FY{fy}_memory_{(on_date or date.today()).isoformat()}.db"


def result_to_run_lines(result, financial_year: str) -> list[dict[str, Any]]:
    """Convert engine output into compact, one-row-per-side invoice snapshots."""
    lines: list[dict[str, Any]] = []
    for _, row in result.iterrows():
        engine_status = row.get("Recon_Status", "")
        match_method = row.get("Match_Logic", "")
        for side, suffix in (("B", "_BOOKS"), ("G", "_GST")):
            gstin = row.get("GSTIN" + suffix)
            invoice = row.get("Invoice Number" + suffix)
            if gstin is None or invoice is None:
                continue
            if _is_missing(gstin) or _is_missing(invoice):
                continue
            doc = next((row.get(k + suffix) for k in ("Document Type", "Invoice Type", "Doc Type")
                        if row.get(k + suffix) is not None), "")
            def value(name):
                v = row.get(name + suffix)
                return None if _is_missing(v) else v
            inv_date = value("Invoice Date")
            if hasattr(inv_date, "isoformat"):
                inv_date = inv_date.isoformat()
            taxable = value("Taxable Value")
            lines.append({
                "row_id": make_row_id(gstin, invoice, side, doc, financial_year),
                "side": side, "gstin": str(gstin), "inv_no": str(invoice),
                "inv_date": str(inv_date) if inv_date is not None else None,
                "taxable": taxable, "igst": value("IGST"), "cgst": value("CGST"),
                "sgst": value("SGST"), "cess": value("Cess"),
                "engine_status": str(engine_status), "final_status": str(engine_status),
                "match_method": str(match_method), "amount_then": taxable,
            })
    return lines



def cdnr_result_to_run_lines(result, financial_year: str) -> list[dict[str, Any]]:
    """Convert CDNR output into the same portable row-ID format used by its report."""
    lines: list[dict[str, Any]] = []
    for _, row in result.iterrows():
        engine_status = row.get("Recon_Status_CDNR", row.get("Recon_Status", ""))
        for side, suffix in (("B", "_BOOKS"), ("G", "_GST")):
            gstin = row.get("GSTIN" + suffix)
            note = row.get("Note Number" + suffix)
            if gstin is None or note is None or _is_missing(gstin) or _is_missing(note):
                continue
            doc = next((row.get(k + suffix) for k in ("Doc Type", "Note Type", "Document Type")
                        if row.get(k + suffix) is not None and not _is_missing(row.get(k + suffix))), "")
            def value(name):
                v = row.get(name + suffix)
                return None if _is_missing(v) else v
            note_date = value("Note Date")
            if hasattr(note_date, "isoformat"):
                note_date = note_date.isoformat()
            taxable = value("Taxable Value")
            lines.append({
                "row_id": make_row_id(gstin, note, side, doc, financial_year),
                "side": side, "gstin": str(gstin), "inv_no": str(note),
                "inv_date": str(note_date) if note_date is not None else None,
                "taxable": taxable, "igst": value("IGST"), "cgst": value("CGST"),
                "sgst": value("SGST"), "cess": value("Cess"),
                "engine_status": str(engine_status), "final_status": str(engine_status),
                "match_method": str(row.get("Match_Logic", "")), "amount_then": taxable,
            })
    return lines


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        return bool(math.isnan(value))
    except (TypeError, ValueError):
        try:
            return bool(value != value)
        except (TypeError, ValueError):
            return str(value) in {"<NA>", "NaT"}


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


def export_exceptions(path: str | Path) -> bytes:
    """Create an editable exception workbook with a protected-looking gray ID column."""
    import xlsxwriter
    rows = unresolved_rows(path)
    columns = ["Row ID", "GSTIN", "Invoice Number", "Invoice Date", "Taxable",
               "Engine Status", "Decision", "Linked To", "Reason"]
    output = io.BytesIO()
    book = xlsxwriter.Workbook(output, {"in_memory": True})
    sheet = book.add_worksheet("Exceptions")
    header = book.add_format({"bold": True, "bg_color": "#DCE6F1", "border": 1})
    grey = book.add_format({"bg_color": "#E7E6E6", "font_color": "#666666"})
    for col, label in enumerate(columns):
        sheet.write(0, col, label, header)
    sheet.set_column(0, 0, 34, grey)
    sheet.set_column(1, 8, 20)
    for r, row in enumerate(rows, start=1):
        values = [row.get("row_id"), row.get("gstin"), row.get("inv_no"), row.get("inv_date"),
                  row.get("taxable"), row.get("engine_status"), "", "", ""]
        for col, value in enumerate(values):
            if value is not None:
                sheet.write(r, col, value, grey if col == 0 else None)
    sheet.freeze_panes(1, 1)
    sheet.autofilter(0, 0, max(1, len(rows)), len(columns) - 1)
    sheet.data_validation(1, 6, max(1, len(rows) + 100), 6,
                          {"validate": "list", "source": ["Link", "Accept", "Action"]})
    book.close()
    return output.getvalue()


def import_decisions(path: str | Path, workbook_bytes: bytes) -> dict[str, Any]:
    """Import controlled decisions from exception, B2B, CDNR, or combined workbooks.

    All nonblank decision values are validated before any database writes, so one
    typo rejects the upload atomically instead of partially applying decisions.
    """
    import pandas as pd
    try:
        sheets = pd.read_excel(io.BytesIO(workbook_bytes), sheet_name=None, dtype=object)
    except Exception as exc:
        raise ValueError(f"Could not read decision workbook: {exc}") from exc
    frames = []
    for sheet_name, frame in sheets.items():
        normalized = {re.sub(r"[^a-z0-9]", "", str(col).casefold()): col for col in frame.columns}
        decision_col = next((normalized[k] for k in ("decision", "memorydecision", "userdecision", "statusdecision")
                             if k in normalized), None)
        if decision_col is not None:
            frames.append((sheet_name, frame, normalized, decision_col))
    if not frames:
        raise ValueError("Workbook must include a Memory Decision column on a report data sheet")

    allowed = {"link": "Link", "accept": "Accept", "action": "Action"}

    def cell(row, col):
        if col is None:
            return ""
        value = row.get(col, "")
        return "" if _is_missing(value) else str(value).strip()

    bad_values = []
    for sheet_name, frame, normalized, decision_col in frames:
        for idx, row in frame.iterrows():
            raw = cell(row, decision_col)
            if raw and raw.casefold() not in allowed:
                bad_values.append({"sheet": sheet_name, "row": int(idx) + 2, "value": raw})
    if bad_values:
        examples = "; ".join(
            f"{item['sheet']} row {item['row']}: {item['value']!r}" for item in bad_values[:8]
        )
        raise ValueError(
            "Upload rejected. Memory Decision accepts only Link, Accept, or Action. "
            f"Correct these cells and upload again: {examples}"
        )

    with _connect(path) as db:
        current_rows = db.execute("""SELECT l.row_id,l.side,l.gstin,l.inv_no,l.taxable
            FROM run_lines l JOIN runs r USING(run_id)
            ORDER BY r.run_date DESC""").fetchall()
        known: dict[str, dict[str, Any]] = {}
        for row in current_rows:
            known.setdefault(row["row_id"], dict(row))
        saved, unrecognized = 0, []
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        for sheet_name, frame, normalized, decision_col in frames:
            generic_id_col = normalized.get("rowid")
            books_id_col = next((normalized[k] for k in ("memorybooksrowid", "booksrowid", "rowidbooks")
                                 if k in normalized), None)
            gst_id_col = next((normalized[k] for k in ("memory2browid", "memorygstr2browid", "2browid",
                                                        "gstr2browid", "rowid2b")
                               if k in normalized), None)
            linked_col = normalized.get("linkedto")
            reason_col = normalized.get("reason")
            for idx, row in frame.iterrows():
                decision_text = cell(row, decision_col)
                if not decision_text:
                    continue
                decision = allowed[decision_text.casefold()]
                books_id = cell(row, books_id_col)
                gst_id = cell(row, gst_id_col)
                row_id = cell(row, generic_id_col) or (books_id if books_id in known else gst_id)
                reason = cell(row, reason_col)
                if not row_id or row_id not in known:
                    unrecognized.append({"sheet": sheet_name, "row": int(idx) + 2, "row_id": row_id,
                                         "reason": "Row ID missing or not found in this memory"})
                    continue

                linked_id = None
                if decision == "Link":
                    link_value = cell(row, linked_col)
                    if not link_value and books_id in known and gst_id in known and books_id != gst_id:
                        linked_id = gst_id if row_id == books_id else books_id
                    elif link_value in known:
                        linked_id = link_value
                    else:
                        source = known[row_id]
                        candidates = [rid for rid, target in known.items()
                            if target["side"] != source["side"]
                            and str(target.get("gstin") or "").casefold() == str(source.get("gstin") or "").casefold()
                            and normalize_invoice_number(target.get("inv_no")) == normalize_invoice_number(link_value)]
                        if len(candidates) == 1:
                            linked_id = candidates[0]
                    if (not linked_id or linked_id == row_id or linked_id not in known
                            or known[linked_id]["side"] == known[row_id]["side"]):
                        unrecognized.append({"sheet": sheet_name, "row": int(idx) + 2, "row_id": row_id,
                                             "reason": "Linked To did not identify one opposite-side invoice"})
                        continue

                target_ids = [row_id]
                if decision in {"Accept", "Action"}:
                    for candidate in (books_id, gst_id):
                        if candidate in known and candidate not in target_ids:
                            target_ids.append(candidate)
                elif decision == "Link":
                    target_ids = [row_id, linked_id]
                for target_id in target_ids:
                    target = known[target_id]
                    target_link = (linked_id if target_id == row_id else row_id) if decision == "Link" else None
                    db.execute("""INSERT INTO decisions(row_id,decision,linked_row_id,amount_then,reason,decided_on)
                        VALUES(?,?,?,?,?,?) ON CONFLICT(row_id) DO UPDATE SET
                        decision=excluded.decision,linked_row_id=excluded.linked_row_id,
                        amount_then=excluded.amount_then,reason=excluded.reason,decided_on=excluded.decided_on""",
                        (target_id, decision, target_link, target.get("taxable"), reason, now))
                saved += 1
        if saved:
            db.execute("UPDATE meta SET value=? WHERE key='last_updated'", (now,))
    return {"saved": saved, "unrecognized": unrecognized}

def apply_decisions(path: str | Path, run_id: str) -> dict[str, str]:
    """Set final_status for one run without changing the engine's original verdict."""
    with _connect(path) as db:
        current = {r["row_id"]: dict(r) for r in db.execute(
            "SELECT row_id,taxable,engine_status FROM run_lines WHERE run_id=?", (run_id,))}
        decisions = {r["row_id"]: dict(r) for r in db.execute("SELECT * FROM decisions")}
        final = {rid: row["engine_status"] for rid, row in current.items()}

        def amount_changed(rid: str, decision: dict[str, Any]) -> bool:
            now_amount, old_amount = current[rid].get("taxable"), decision.get("amount_then")
            try:
                return abs(float(now_amount) - float(old_amount)) > 0.01
            except (TypeError, ValueError):
                return now_amount != old_amount

        processed: set[str] = set()
        for row_id, decision in decisions.items():
            if row_id not in current or row_id in processed:
                continue
            kind = decision.get("decision")
            if amount_changed(row_id, decision):
                final[row_id] = "Needs review"
            elif kind == "Accept":
                final[row_id] = "Accepted difference"
            elif kind == "Action":
                final[row_id] = "Needs review"
            elif kind == "Link":
                target_id = decision.get("linked_row_id")
                paired = decisions.get(target_id, {})
                if (target_id in current and not amount_changed(target_id, paired)
                        and paired.get("decision") == "Link"
                        and paired.get("linked_row_id") == row_id):
                    final[row_id] = final[target_id] = "Matched (manual)"
                    processed.add(target_id)
                else:
                    final[row_id] = "Needs review"
            processed.add(row_id)
        for rid, status in final.items():
            db.execute("UPDATE run_lines SET final_status=? WHERE run_id=? AND row_id=?", (status, run_id, rid))
    return final



def apply_memory_final_statuses(frame, financial_year: str, statuses: Mapping[str, str],
                                return_type: str = "GSTR2B"):
    """Apply saved decisions to an in-memory result frame for reports and notice filters."""
    out = frame.copy()
    is_cdnr = str(return_type).upper() == "CDNR"
    status_col = "Recon_Status_CDNR" if is_cdnr and "Recon_Status_CDNR" in out.columns else "Recon_Status"
    if status_col not in out.columns:
        return out
    original_col = "_Engine_Status_Original"
    if original_col not in out.columns:
        out[original_col] = out[status_col]

    def outcome(row):
        found = []
        for side, suffix in (("B", "_BOOKS"), ("G", "_GST")):
            gstin = row.get("GSTIN" + suffix)
            invoice_col = ("Note Number" if is_cdnr else "Invoice Number") + suffix
            invoice = row.get(invoice_col)
            if _is_missing(gstin) or _is_missing(invoice):
                continue
            if is_cdnr:
                doc = next((row.get(k + suffix) for k in ("Doc Type", "Note Type", "Document Type")
                            if row.get(k + suffix) is not None and not _is_missing(row.get(k + suffix))), "")
            else:
                doc = next((row.get(k + suffix) for k in ("Document Type", "Invoice Type", "Doc Type")
                            if row.get(k + suffix) is not None and not _is_missing(row.get(k + suffix))), "")
            row_id = make_row_id(gstin, invoice, side, doc, financial_year)
            value = statuses.get(row_id)
            if value:
                found.append(value)
        priority = {"Matched (manual)": 3, "Accepted difference": 2, "Needs review": 1}
        return max(found, key=lambda value: priority.get(value, 0)) if found else None

    applied = out.apply(outcome, axis=1)
    for idx, final_status in applied.items():
        if final_status == "Matched (manual)":
            out.at[idx, status_col] = final_status
            if "Match_Confidence" in out.columns:
                out.at[idx, "Match_Confidence"] = 100.0
            if "Match_Logic" in out.columns:
                out.at[idx, "Match_Logic"] = "Memory Link"
            if "Match_Reason" in out.columns:
                out.at[idx, "Match_Reason"] = "Manually linked from the uploaded reconciliation report."
        elif final_status == "Accepted difference":
            out.at[idx, status_col] = final_status
            if "Match_Reason" in out.columns:
                out.at[idx, "Match_Reason"] = "Difference accepted from the uploaded reconciliation report."
        elif final_status == "Needs review":
            out.at[idx, status_col] = final_status
            if "Match_Confidence" in out.columns:
                out.at[idx, "Match_Confidence"] = 0.0
            if "Match_Logic" in out.columns:
                out.at[idx, "Match_Logic"] = "Needs review"
            if "Match_Reason" in out.columns:
                out.at[idx, "Match_Reason"] = "Marked for action from the uploaded reconciliation report."
    return out



def open_items(path: str | Path, gstin: str = "", min_age_days: int = 0) -> list[dict[str, Any]]:
    """Return the latest snapshot for each month/return, oldest unresolved first."""
    with _connect(path) as db:
        rows = db.execute("""WITH latest AS (
            SELECT month,return_type,MAX(run_date) AS run_date FROM runs GROUP BY month,return_type
        ) SELECT l.*,r.month,r.return_type,r.run_date FROM run_lines l JOIN runs r USING(run_id)
          JOIN latest x ON x.month=r.month AND x.return_type=r.return_type AND x.run_date=r.run_date
          ORDER BY l.first_seen ASC,l.gstin,l.inv_no""").fetchall()
    today = date.today()
    result = []
    for row in rows:
        item = dict(row)
        if item.get("final_status") in {"Matched", "Matched (manual)", "Accepted difference"}:
            continue
        if gstin and gstin.casefold() not in str(item.get("gstin") or "").casefold():
            continue
        try:
            age = (today - date.fromisoformat(str(item["first_seen"])[:10])).days
        except (ValueError, TypeError):
            age = 0
        if age < max(0, int(min_age_days)):
            continue
        item["age_days"] = age
        result.append(item)
    return result


def search_invoice(path: str | Path, query: str) -> list[dict[str, Any]]:
    """Search invoice number, GSTIN or amount across snapshots, ordered by month."""
    q = str(query or "").strip()
    if not q:
        return []
    qnorm = normalize_invoice_number(q)
    with _connect(path) as db:
        rows = db.execute("""SELECT l.*,r.month,r.return_type,r.run_date FROM run_lines l
            JOIN runs r USING(run_id) ORDER BY r.run_date,l.inv_date,l.gstin,l.inv_no""").fetchall()
    found = []
    seen = set()
    for row in rows:
        item = dict(row)
        token = f"{item.get('gstin') or ''} {item.get('inv_no') or ''} {item.get('taxable') or ''}"
        amount_match = q in str(item.get("taxable") or "")
        invoice_match = qnorm and qnorm in normalize_invoice_number(item.get("inv_no"))
        if q.casefold() in token.casefold() or invoice_match or amount_match:
            key = (item["run_id"], item["row_id"])
            if key not in seen:
                seen.add(key)
                found.append(item)
    return found


def touch_updated(path: str | Path) -> None:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with _connect(path) as db:
        db.execute("UPDATE meta SET value=? WHERE key='last_updated'", (now,))


