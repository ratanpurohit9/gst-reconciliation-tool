"""Module 04: Sales Register vs GSTR-1.

This module adapts sales-side workbooks to the existing reconciliation engines.
It deliberately does not alter Module 02 or the shared matching algorithms.
"""
from __future__ import annotations

import io
import re

import pandas as pd
import streamlit as st

from modules.core_engine import run_reconciliation
from modules.cdnr_processor import run_cdnr_reconciliation


REQUIRED = {
    "GSTIN": ("gstin/uin of recipient", "gstin of recipient", "customer gstin", "party gstin", "gstin"),
    "Name of Party": ("receiver name", "customer name", "party name", "trade/legal name", "name"),
    "Invoice Number": ("invoice number", "invoice no.", "invoice no", "bill no", "document number"),
    "Invoice Date": ("invoice date", "date of invoice", "date of invoie", "bill date", "date"),
    "Invoice Value": ("invoice value", "invoice value(₹)", "total invoice value", "total amount", "bill amount"),
    "Taxable Value": ("taxable value", "taxable value (₹)", "taxable amount"),
    "IGST": ("integrated tax paid", "integrated tax(₹)", "igst", "igst amount"),
    "CGST": ("central tax paid", "central tax(₹)", "cgst", "cgst amount"),
    "SGST": ("state/ut tax paid", "state/ut tax(₹)", "sgst", "sgst/utgst", "sgst amount"),
    "Cess": ("cess paid", "cess amount", "cess"),
    "Place of Supply": ("place of supply", "place of supply state", "place of supply name", "pos"),
    "Reverse Charge": ("reverse charge", "rcm applicable", "supply attract reverse charge", "rcm"),
}
CDNR_ALIASES = {
    "GSTIN": REQUIRED["GSTIN"],
    "Trade Name": REQUIRED["Name of Party"],
    "Note Number": ("note number", "cr. / dr. note no.", "note no", "document number", "voucher number"),
    "Note Date": ("note date", "cr. / dr. note date", "date"),
    "Note Type": ("note type", "type of note", "debit/credit", "credit/debit"),
    "Taxable Value": REQUIRED["Taxable Value"],
    "IGST": REQUIRED["IGST"],
    "CGST": REQUIRED["CGST"],
    "SGST": REQUIRED["SGST"],
    "Cess": ("cess amount", "cess", "cess paid"),
}


def _norm(value):
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def _find_column(columns, aliases):
    normalized = {_norm(col): col for col in columns}
    for alias in aliases:
        if _norm(alias) in normalized:
            return normalized[_norm(alias)]
    for alias in aliases:
        alias_tokens = _norm(alias).split()
        for normalized_col, original in normalized.items():
            column_tokens = normalized_col.split()
            if len(alias_tokens) > 1 and any(
                column_tokens[i:i + len(alias_tokens)] == alias_tokens
                for i in range(len(column_tokens) - len(alias_tokens) + 1)
            ):
                return original
            if len(alias_tokens) == 1 and len(alias_tokens[0]) >= 5 and alias_tokens[0] in column_tokens:
                return original
    return None


def list_sheets(upload):
    if upload.name.lower().endswith(".csv"):
        return ["CSV"]
    return pd.ExcelFile(io.BytesIO(upload.getvalue())).sheet_names


def _header_row(upload, sheet):
    if sheet == "CSV":
        raw = pd.read_csv(io.BytesIO(upload.getvalue()), header=None, nrows=12)
    else:
        raw = pd.read_excel(io.BytesIO(upload.getvalue()), sheet_name=sheet, header=None, nrows=12)
    best_row, best_score = 0, -1
    signals = ("gstin", "invoice", "note", "taxable")
    for i, row in raw.iterrows():
        words = " ".join(_norm(v) for v in row.tolist())
        score = sum(1 for signal in signals if signal in words)
        if score > best_score:
            best_row, best_score = int(i), score
    return best_row


def read_sheet(upload, sheet, header=None):
    if sheet == "CSV":
        return pd.read_csv(io.BytesIO(upload.getvalue()), header=header if header is not None else _header_row(upload, sheet))
    if header is None:
        header = _header_row(upload, sheet)
    return pd.read_excel(io.BytesIO(upload.getvalue()), sheet_name=sheet, header=header)


def choose_sheet(sheets, candidates):
    for candidate in candidates:
        for sheet in sheets:
            if sheet.strip().casefold() == candidate.casefold():
                return sheet
    for candidate in candidates:
        for sheet in sheets:
            if candidate.casefold() in sheet.casefold():
                return sheet
    return sheets[0]


def choose_optional_sheet(sheets, candidates):
    for candidate in candidates:
        for sheet in sheets:
            if sheet.strip().casefold() == candidate.casefold():
                return sheet
    for candidate in candidates:
        for sheet in sheets:
            if candidate.casefold() in sheet.casefold():
                return sheet
    return "(Skip CDNR)"


def _amount(series):
    return pd.to_numeric(series.astype(str).str.replace(",", "", regex=False).str.replace("₹", "", regex=False).str.strip(), errors="coerce").fillna(0.0)


def _state_code(value):
    match = re.match(r"\s*(\d{2})", str(value or ""))
    return match.group(1) if match else ""


def _tax_components(df, taxable, rate, pos, seller_state, invoice_type=None):
    amount = _amount(df[taxable])
    rate_values = _amount(df[rate]) if rate else pd.Series(0.0, index=df.index)
    tax = (amount * rate_values / 100).round(2)
    interstate = df[pos].map(_state_code).ne(seller_state) if pos else pd.Series(False, index=df.index)
    if invoice_type:
        interstate |= df[invoice_type].astype(str).str.contains(r"SEZ|deemed", case=False, na=False)
    return tax.where(interstate, 0.0), (tax / 2).where(~interstate, 0.0), (tax / 2).where(~interstate, 0.0)


def map_b2b(df, side, seller_state):
    cols = df.columns
    found = {field: _find_column(cols, aliases) for field, aliases in REQUIRED.items()}
    missing = [name for name in ("GSTIN", "Invoice Number", "Invoice Date", "Taxable Value") if not found[name]]
    if missing:
        raise ValueError(f"{side} sheet is missing required columns: {', '.join(missing)}")
    out = pd.DataFrame(index=df.index)
    for field, source in found.items():
        out[field] = df[source] if source else ("" if field in ("Name of Party", "Place of Supply", "Reverse Charge") else 0)
    if not found["IGST"] or not found["CGST"] or not found["SGST"]:
        rate_col = _find_column(cols, ("rate", "gst rate", "tax rate", "gst %"))
        pos_col = found["Place of Supply"]
        invoice_type_col = _find_column(cols, ("invoice type", "supply type"))
        if not rate_col or not pos_col:
            raise ValueError(f"{side} has no complete tax split: provide IGST/CGST/SGST columns or both Rate and Place of Supply.")
        i, c, s = _tax_components(df, found["Taxable Value"], rate_col, pos_col, seller_state, invoice_type_col)
        out["IGST"] = df[found["IGST"]] if found["IGST"] else i
        out["CGST"] = df[found["CGST"]] if found["CGST"] else c
        out["SGST"] = df[found["SGST"]] if found["SGST"] else s
    return _clean_canonical(out)


def _clean_canonical(df):
    out = df.copy()
    out["GSTIN"] = out["GSTIN"].astype(str).str.strip().str.upper()
    out["Invoice Number"] = out["Invoice Number"].astype(str).str.strip()
    out = out[out["GSTIN"].str.match(r"^\d{2}[A-Z0-9]{13}$", na=False)]
    out = out[~out["Invoice Number"].str.casefold().isin(("", "nan", "none"))]
    for field in ("Taxable Value", "IGST", "CGST", "SGST", "Cess", "Invoice Value"):
        out[field] = _amount(out[field])
    return out.reset_index(drop=True)


def map_cdnr(df, side, seller_state):
    cols = df.columns
    found = {field: _find_column(cols, aliases) for field, aliases in CDNR_ALIASES.items()}
    needed = ("GSTIN", "Note Number", "Note Date", "Note Type", "Taxable Value")
    missing = [name for name in needed if not found[name]]
    if missing:
        raise ValueError(f"{side} CDNR sheet is missing required columns: {', '.join(missing)}")
    out = pd.DataFrame(index=df.index)
    for field, source in found.items():
        out[field] = df[source] if source else 0
    vals = out["Note Type"].astype(str).str.strip().str.lower()
    out["Note Type"] = vals.replace({"c": "credit note", "d": "debit note", "cr": "credit note", "dr": "debit note"})
    if not found["IGST"] or not found["CGST"] or not found["SGST"]:
        rate_col = _find_column(cols, ("rate", "gst rate", "tax rate", "gst %"))
        pos_col = _find_column(cols, ("place of supply", "pos"))
        if not rate_col or not pos_col:
            raise ValueError(f"{side} CDNR has no complete tax split: provide IGST/CGST/SGST columns or both Rate and Place of Supply.")
        i, c, s = _tax_components(df, found["Taxable Value"], rate_col, pos_col, seller_state)
        out["IGST"] = df[found["IGST"]] if found["IGST"] else i
        out["CGST"] = df[found["CGST"]] if found["CGST"] else c
        out["SGST"] = df[found["SGST"]] if found["SGST"] else s
    out["GSTIN"] = out["GSTIN"].astype(str).str.strip().str.upper()
    out["Note Number"] = out["Note Number"].astype(str).str.strip()
    out = out[out["GSTIN"].str.match(r"^\d{2}[A-Z0-9]{13}$", na=False)]
    out = out[~out["Note Number"].str.casefold().isin(("", "nan", "none"))]
    for field in ("Taxable Value", "IGST", "CGST", "SGST", "Cess"):
        out[field] = _amount(out[field])
    return out.reset_index(drop=True)


def _display_direction(status):
    return {
        "Invoices Not in GSTR-2B": "Invoice in Sales Register — not in GSTR-1",
        "Invoices Not in Purchase Books": "Invoice in GSTR-1 — not in Sales Register",
        "CDNR Not in GSTR-2B": "CDNR in Sales Register — not in GSTR-1",
        "CDNR Not in Books": "CDNR in GSTR-1 — not in Sales Register",
    }.get(str(status), str(status))


def _make_xlsx(b2b, cdnr):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter", datetime_format="dd/mm/yyyy") as writer:
        summary = []
        for label, df, col in (("B2B", b2b, "Recon_Status"), ("CDNR", cdnr, "Recon_Status_CDNR")):
            if df is not None and not df.empty and col in df:
                for status, count in df[col].fillna("Unknown").value_counts().items():
                    summary.append({"Section": label, "Status": _display_direction(status), "Rows": int(count)})
        pd.DataFrame(summary, columns=["Section", "Status", "Rows"]).to_excel(writer, index=False, sheet_name="Summary")
        for name, df, col in (("B2B", b2b, "Recon_Status"), ("CDNR", cdnr, "Recon_Status_CDNR")):
            if df is None or df.empty:
                continue
            frame = df.copy()
            if col in frame:
                frame["Status"] = frame[col].map(_display_direction)
            frame.to_excel(writer, index=False, sheet_name=name)
            ws = writer.sheets[name]
            ws.freeze_panes(1, 0)
            ws.autofilter(0, 0, len(frame), max(len(frame.columns) - 1, 0))
    output.seek(0)
    return output.getvalue()


def render_module4():
    st.title("Module 04 · Sales Register vs GSTR-1")
    st.caption("Separate Module 4 workspace. It uses the existing B2B Smart Match engine and CDNR matching cascade; Module 2 stays unchanged.")
    if st.button("← Dashboard", key="m4_dashboard"):
        st.session_state["show_dashboard"] = True
        st.session_state["app_stage"] = "setup"
        st.session_state.pop("module4_results", None)
        st.rerun()

    saved = st.session_state.get("module4_results")
    if saved:
        b2b, cdnr = saved["b2b"], saved["cdnr"]
        st.success(f"Reconciliation complete · tolerance ₹{saved['tolerance']:,.2f} · smart matching {'on' if saved['smart'] else 'off'}")
        c1, c2 = st.columns(2)
        for container, label, frame, col in ((c1, "B2B", b2b, "Recon_Status"), (c2, "CDNR", cdnr, "Recon_Status_CDNR")):
            with container:
                st.subheader(label)
                if frame is None or frame.empty or col not in frame:
                    st.metric("Rows", 0)
                    continue
                counts = frame[col].fillna("Unknown").map(_display_direction).value_counts()
                st.metric("Rows", len(frame))
                st.dataframe(counts.rename("Count").rename_axis("Status").reset_index(), use_container_width=True, hide_index=True)
                st.dataframe(frame.head(5), use_container_width=True, hide_index=True)
        st.download_button("Download Module 4 reconciliation (Excel)", _make_xlsx(b2b, cdnr),
                           file_name="Sales_Register_vs_GSTR1_Reconciliation.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           type="primary")
        if st.button("Start another reconciliation", key="m4_reset"):
            st.session_state.pop("module4_results", None)
            st.rerun()
        return

    left, right = st.columns(2)
    with left:
        st.subheader("Sales Register (Books)")
        books_upload = st.file_uploader("Upload Books workbook", type=["xlsx", "csv"], key="m4_books")
    with right:
        st.subheader("GSTR-1 (Filed)")
        portal_upload = st.file_uploader("Upload GSTR-1 workbook", type=["xlsx", "csv"], key="m4_portal")
    if not books_upload or not portal_upload:
        st.info("Upload both workbooks. Module 4 will read the selected B2B and CDNR sheets.")
        return

    try:
        books_sheets, portal_sheets = list_sheets(books_upload), list_sheets(portal_upload)
    except Exception as exc:
        st.error(f"Could not open workbooks: {exc}")
        return
    b2b_col1, b2b_col2 = st.columns(2)
    with b2b_col1:
        b2b_books_sheet = st.selectbox("Books B2B sheet", books_sheets, index=books_sheets.index(choose_sheet(books_sheets, ("b2b,sez,de", "b2b", "sales register"))) if choose_sheet(books_sheets, ("b2b,sez,de", "b2b", "sales register")) in books_sheets else 0, key="m4_b2b_books_sheet")
    with b2b_col2:
        b2b_portal_sheet = st.selectbox("GSTR-1 B2B sheet", portal_sheets, index=portal_sheets.index(choose_sheet(portal_sheets, ("b2b invoices", "b2b"))) if choose_sheet(portal_sheets, ("b2b invoices", "b2b")) in portal_sheets else 0, key="m4_b2b_portal_sheet")
    cdnr_books_choices = ["(Skip CDNR)"] + books_sheets
    cdnr_portal_choices = ["(Skip CDNR)"] + portal_sheets
    cc1, cc2 = st.columns(2)
    with cc1:
        default = choose_optional_sheet(books_sheets, ("cdnr", "credit debit note"))
        cdnr_books_sheet = st.selectbox("Books CDNR sheet (optional)", cdnr_books_choices, index=cdnr_books_choices.index(default) if default in cdnr_books_choices else 0, key="m4_cdnr_books_sheet")
    with cc2:
        default = choose_optional_sheet(portal_sheets, ("cdnr", "cdn", "credit debit note"))
        cdnr_portal_sheet = st.selectbox("GSTR-1 CDNR sheet (optional)", cdnr_portal_choices, index=cdnr_portal_choices.index(default) if default in cdnr_portal_choices else 0, key="m4_cdnr_portal_sheet")

    c1, c2, c3 = st.columns(3)
    with c1:
        seller_gstin = st.text_input("Your GSTIN (used to derive tax split if Books has only rate)", key="m4_seller_gstin", max_chars=15)
    with c2:
        tolerance = st.number_input("Matching tolerance (₹)", min_value=0.0, value=5.0, step=1.0, key="m4_tolerance")
    with c3:
        smart = st.checkbox("Enable Smart Matching", value=True, key="m4_smart")
    if seller_gstin and not re.match(r"^\d{2}[A-Z0-9]{13}$", seller_gstin.strip().upper()):
        st.warning("Enter a valid 15-character GSTIN; its first two digits are used as the seller state.")
        return
    if not seller_gstin:
        st.info("Enter the seller GSTIN so books tax components can be derived correctly when the workbook has only a tax rate.")
        return

    if st.button("Run Module 4 reconciliation", type="primary", use_container_width=True, key="m4_run"):
        try:
            books_b2b_raw = read_sheet(books_upload, b2b_books_sheet)
            portal_b2b_raw = read_sheet(portal_upload, b2b_portal_sheet)
            books_b2b = map_b2b(books_b2b_raw, "Books", seller_gstin[:2])
            portal_b2b = map_b2b(portal_b2b_raw, "GSTR-1", seller_gstin[:2])
            with st.spinner("Running the existing Smart Match rules..."):
                b2b_result, _, _ = run_reconciliation(books_b2b, portal_b2b, tolerance, [], smart)

            cdnr_result = pd.DataFrame()
            if cdnr_books_sheet != "(Skip CDNR)" and cdnr_portal_sheet != "(Skip CDNR)":
                books_cdnr_raw = read_sheet(books_upload, cdnr_books_sheet)
                portal_cdnr_raw = read_sheet(portal_upload, cdnr_portal_sheet)
                books_cdnr = map_cdnr(books_cdnr_raw, "Books", seller_gstin[:2])
                portal_cdnr = map_cdnr(portal_cdnr_raw, "GSTR-1", seller_gstin[:2])
                cdnr_result = run_cdnr_reconciliation(books_cdnr, portal_cdnr, tolerance)
            st.session_state["module4_results"] = {"b2b": b2b_result, "cdnr": cdnr_result, "tolerance": tolerance, "smart": smart}
            st.rerun()
        except Exception as exc:
            st.error(f"Module 4 could not run: {exc}")


