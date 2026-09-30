"""Stable identity helpers for user-held GST reconciliation memory."""
from __future__ import annotations
import hashlib
import re
import unicodedata
from typing import Any


def normalize_invoice_number(value: Any) -> str:
    """Normalize case, Unicode variants and punctuation (INV/0458 == inv-0458)."""
    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", str(value)).strip().upper()
    text = re.sub(r"\.0+$", "", text)
    return re.sub(r"[^A-Z0-9]", "", text)


def make_row_id(gstin: Any, invoice_number: Any, side: str,
                document_type: Any = "", financial_year: Any = "") -> str:
    """Create an amount-independent ID from supplier, invoice, side, doc type and FY."""
    side = str(side).strip().upper()
    if side not in {"B", "G"}:
        raise ValueError("side must be 'B' (books) or 'G' (GSTR)")
    fields = [str(gstin or "").strip().upper(), normalize_invoice_number(invoice_number),
              side, normalize_invoice_number(document_type), str(financial_year or "").strip()]
    return hashlib.sha256("\x1f".join(fields).encode("utf-8")).hexdigest()[:32]


def assign_row_ids(frame, *, side: str, gstin_col: str = "GSTIN",
                   invoice_col: str = "Invoice Number", document_col: str | None = None,
                   fy_col: str | None = None, row_id_col: str = "Row ID"):
    """Return a copy with IDs independent of dataframe positions."""
    missing = [c for c in (gstin_col, invoice_col) if c not in frame.columns]
    if missing:
        raise KeyError(f"Missing identity column(s): {', '.join(missing)}")
    out = frame.copy()
    out[row_id_col] = [make_row_id(row[gstin_col], row[invoice_col], side,
        row.get(document_col, "") if document_col else "",
        row.get(fy_col, "") if fy_col else "") for _, row in out.iterrows()]
    return out

