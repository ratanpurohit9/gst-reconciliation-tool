# modules/notice_importer.py
# Parses a manually-reconciled/exported Excel result file and maps its
# columns to the internal DataFrame format expected by the notice generators.
# Supports both the tool's own exported format AND custom column names.

import pandas as pd
import io
import re

# ─── Column mapping rules ─────────────────────────────────────────────────────
# Each internal column → list of keywords to search for in the file's header row
# Matching is case-insensitive, partial (uses 'in').
# First match wins.  Columns marked optional=True won't cause a failure.

_COL_MAP = [
    # ( internal_name,           keywords_to_match,                           optional )
    ("GSTIN",                   ["gstin"],                                    False),
    ("Name of Party",           ["name of party", "party name", "vendor", "supplier name"], False),
    ("Invoice Number_BOOKS",    ["inv no (books)", "invoice number_books", "books inv", "books invoice", "inv no books", "invoice no books",
                                  "invoice number", "invoice no", "inv no", "invoice_no", "bill no", "bill number"], True),
    ("Invoice Date_BOOKS",      ["date_books", "books date", "date (books)", "invoice date_books", "date books"], True),
    ("Taxable Value_BOOKS",     ["taxable_books", "taxable value_books", "books taxable", "taxable (books)"], True),
    ("IGST_BOOKS",              ["igst_books", "igst (books)", "books igst"],  True),
    ("CGST_BOOKS",              ["cgst_books", "cgst (books)", "books cgst"],  True),
    ("SGST_BOOKS",              ["sgst_books", "sgst (books)", "books sgst"],  True),
    ("Invoice Number_GST",      ["inv no (gstr", "invoice number_gst", "gstr-2b inv", "portal inv", "inv no gstr", "invoice no gstr", "gstr inv"], True),
    ("Invoice Date_GST",        ["date_gst", "gstr date", "portal date", "date (gstr", "invoice date_gst", "date2"], True),
    ("Taxable Value_GST",       ["taxable_gst", "taxable value_gst", "gstr taxable", "portal taxable", "taxable2", "taxable3"], True),
    ("IGST_GST",                ["igst_gst", "igst (gstr", "portal igst", "igst2", "igst4"],  True),
    ("CGST_GST",                ["cgst_gst", "cgst (gstr", "portal cgst", "cgst2", "cgst5"],  True),
    ("SGST_GST",                ["sgst_gst", "sgst (gstr", "portal sgst", "sgst2", "sgst6"],  True),
    ("Diff_Taxable",            ["diff taxable", "diff_taxable"],              True),
    ("Diff_IGST",               ["diff igst", "diff_igst"],                   True),
    ("Diff_CGST",               ["diff cgst", "diff_cgst"],                   True),
    ("Diff_SGST",               ["diff sgst", "diff_sgst"],                   True),
    ("Recon_Status",            ["status", "recon_status", "reconciliation status", "recon status"], False),
]

# ─── Ambiguous single-word columns (taxable/igst etc. appear multiple times) ─
# When a generic keyword matches multiple columns, we use positional context:
# Books columns appear before GSTR columns in the output Excel.
_POSITIONAL_GROUPS = {
    "taxable": [("Taxable Value_BOOKS", False), ("Taxable Value_GST", True)],
    "igst":    [("IGST_BOOKS", False),          ("IGST_GST", True)],
    "cgst":    [("CGST_BOOKS", False),          ("CGST_GST", True)],
    "sgst":    [("SGST_BOOKS", False),          ("SGST_GST", True)],
    "date":    [("Invoice Date_BOOKS", False),  ("Invoice Date_GST", True)],
}


def _find_header_row(df_raw):
    """
    Scan first 10 rows to find the actual header row.
    Returns the row index (0-based) of the best candidate.
    Heuristic: row with most string-type cells that contain 'gstin' or 'status' or 'party'.
    """
    keywords = {"gstin", "status", "party", "taxable", "invoice", "inv no"}
    best_row, best_score = 0, 0
    for i in range(min(10, len(df_raw))):
        row = df_raw.iloc[i]
        score = sum(1 for v in row if isinstance(v, str) and any(kw in v.lower() for kw in keywords))
        if score > best_score:
            best_score, best_row = score, i
    return best_row


def _normalise(s):
    return str(s).strip().lower() if pd.notna(s) else ""


def _match_column(col_name, keywords):
    """True if any keyword is contained in the normalised column name."""
    n = _normalise(col_name)
    return any(kw in n for kw in keywords)


def _resolve_positional(raw_cols, already_mapped):
    """
    For generic duplicate keywords (taxable/igst/cgst/sgst/date),
    assign them in order of appearance in the header row.
    already_mapped: dict { raw_col → internal_name }
    Returns updated already_mapped.
    """
    for keyword, targets in _POSITIONAL_GROUPS.items():
        # Find raw columns not yet mapped that match this keyword
        candidates = [
            c for c in raw_cols
            if keyword in _normalise(c) and c not in already_mapped
        ]
        # Also check if the targets were already matched by the detailed rules
        # Only apply positional logic for unresolved targets
        remaining_targets = [t for t in targets if t[0] not in already_mapped.values()]
        for i, raw_col in enumerate(candidates):
            if i < len(remaining_targets):
                already_mapped[raw_col] = remaining_targets[i][0]
    return already_mapped


def parse_uploaded_result_excel(file_bytes, sheet_name=None):
    """
    Parse a reconciled-result Excel file and return:
      - df       : DataFrame with internal column names (ready for notice generators)
      - mapped   : dict { raw_col → internal_col } of what was found
      - missing  : list of required internal columns that could not be found
      - warnings : list of human-readable info messages
    """
    warnings = []

    # ── 1. Read raw ───────────────────────────────────────────────────────────
    try:
        xl = pd.ExcelFile(io.BytesIO(file_bytes))
    except Exception as e:
        return None, {}, ["Could not read file"], [f"File read error: {e}"]

    # Pick sheet: prefer first non-hidden that contains data keywords
    if sheet_name and sheet_name in xl.sheet_names:
        chosen = sheet_name
    else:
        chosen = xl.sheet_names[0]
        for s in xl.sheet_names:
            try:
                tmp = xl.parse(s, header=None, nrows=5)
                flat = " ".join(str(v).lower() for v in tmp.values.flatten() if pd.notna(v))
                if "gstin" in flat or "status" in flat:
                    chosen = s
                    break
            except Exception:
                pass
    if chosen != xl.sheet_names[0]:
        warnings.append(f"Using sheet: '{chosen}'")

    df_raw = xl.parse(chosen, header=None)

    # ── 2. Find header row ────────────────────────────────────────────────────
    hdr_row = _find_header_row(df_raw)
    if hdr_row > 0:
        warnings.append(f"Header detected at row {hdr_row + 1} (skipping {hdr_row} title row(s))")

    raw_headers = df_raw.iloc[hdr_row].tolist()
    df = df_raw.iloc[hdr_row + 1:].copy()
    df.columns = [str(h) if pd.notna(h) else f"_col{i}" for i, h in enumerate(raw_headers)]
    df = df.reset_index(drop=True)
    df = df.dropna(how='all')

    # ── 3. Map columns ────────────────────────────────────────────────────────
    raw_cols = list(df.columns)
    col_mapping = {}   # raw → internal

    for internal_name, keywords, optional in _COL_MAP:
        if internal_name in col_mapping.values():
            continue   # already assigned
        for raw in raw_cols:
            if raw in col_mapping:
                continue   # raw already used
            if _match_column(raw, keywords):
                col_mapping[raw] = internal_name
                break

    # ── 4. Positional resolution for ambiguous duplicates ─────────────────────
    col_mapping = _resolve_positional(raw_cols, col_mapping)

    # ── 5. Rename and build output DataFrame ──────────────────────────────────
    rename_map = {raw: internal for raw, internal in col_mapping.items()}
    df = df.rename(columns=rename_map)

    # ── 6. Check required columns ─────────────────────────────────────────────
    required = [c for c, _, opt in _COL_MAP if not opt]
    missing  = [c for c in required if c not in df.columns]

    # ── 7. Add GSTIN convenience alias ────────────────────────────────────────
    if "GSTIN" in df.columns and "GSTIN_BOOKS" not in df.columns:
        df["GSTIN_BOOKS"] = df["GSTIN"]

    # ── 8. Numeric coercion for tax/value columns ────────────────────────────
    num_cols = [
        "Taxable Value_BOOKS", "IGST_BOOKS", "CGST_BOOKS", "SGST_BOOKS",
        "Taxable Value_GST",   "IGST_GST",   "CGST_GST",   "SGST_GST",
        "Diff_Taxable", "Diff_IGST", "Diff_CGST", "Diff_SGST",
    ]
    for c in num_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(
                df[c].astype(str).str.replace(",", "").str.strip(),
                errors='coerce'
            ).fillna(0.0)

    # ── 9. Ensure Final_Taxable exists (used by notice functions) ─────────────
    if "Final_Taxable" not in df.columns:
        if "Taxable Value_BOOKS" in df.columns:
            df["Final_Taxable"] = df["Taxable Value_BOOKS"]
        elif "Taxable Value_GST" in df.columns:
            df["Final_Taxable"] = df["Taxable Value_GST"]

    return df, col_mapping, missing, warnings


def get_available_sheets(file_bytes):
    """Return list of sheet names from an uploaded Excel."""
    try:
        xl = pd.ExcelFile(io.BytesIO(file_bytes))
        return xl.sheet_names
    except Exception:
        return []
