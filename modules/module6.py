"""Module 06: E-Way Bill vs Sales Register.

The user logs into the official portal and completes CAPTCHA themselves, downloads
the monthly report, and uploads it here. No credentials or CAPTCHA are automated.
"""
from __future__ import annotations

import io
import re
import html

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from modules.core_engine import run_reconciliation


PORTAL_URL = "https://ewaybillgst.gov.in/"
ROLE_ALIASES = {
    "GSTIN": ("gstin", "gstin of recipient", "gstin uin of recipient", "recipient gstin", "recipient gstin uin", "to gstin", "party gstin", "customer gstin"),
    "Invoice Number": ("invoice number", "invoice no", "document number", "document no", "doc no", "bill no"),
    "Invoice Date": ("invoice date", "document date", "doc date", "bill date", "date"),
    "Amount": ("invoice value", "total invoice value", "total value", "document value", "total amount", "invoice amount", "gross amount"),
    "Name of Party": ("party name", "recipient name", "to trade name", "customer name", "receiver name", "name"),
    "Status": ("status", "eway status", "e-way bill status", "ewb status"),
    "Invoice Type": ("invoice type", "type of invoice"),
}
CANONICAL_COLUMNS = ["GSTIN", "Name of Party", "Invoice Number", "Invoice Date",
                     "Taxable Value", "IGST", "CGST", "SGST", "Cess", "Invoice Value"]


def _norm(value):
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def _is_html_xls(upload):
    if not upload.name.lower().endswith(".xls"):
        return False
    sample = upload.getvalue()[:2048].lstrip()
    sample_lower = sample.lower()
    return sample_lower.startswith((b"<table", b"<!doctype html", b"<html")) or b"<table" in sample_lower[:512]


def _read(upload, sheet):
    content = upload.getvalue()
    if upload.name.lower().endswith(".csv"):
        return pd.read_csv(io.BytesIO(content), header=None)
    if _is_html_xls(upload):
        html_text = content.decode("utf-8-sig", errors="replace")
        tables = pd.read_html(io.StringIO(html_text), header=None)
        if not tables:
            raise ValueError(f"{upload.name} contains no readable HTML table.")
        return tables[0]
    return pd.read_excel(io.BytesIO(content), sheet_name=sheet, header=None)


def _sheets(upload):
    if upload.name.lower().endswith(".csv"):
        return ["CSV"]
    if _is_html_xls(upload):
        return ["E-Way Bill report"]
    return pd.ExcelFile(io.BytesIO(upload.getvalue())).sheet_names


def _guess_header(raw):
    best_row, best_score = 0, -1
    for i, row in raw.head(15).iterrows():
        text = " ".join(_norm(value) for value in row.tolist())
        score = sum(term in text for term in ("gstin", "invoice", "document", "date", "value"))
        if score > best_score:
            best_row, best_score = int(i), score
    return best_row


def _guess_column(columns, role):
    normalized = {_norm(col): col for col in columns}
    for alias in ROLE_ALIASES[role]:
        if _norm(alias) in normalized:
            return normalized[_norm(alias)]
    return None


def _load_with_header(upload, sheet, key):
    raw = _read(upload, sheet)
    header_row = st.number_input(
        f"{key}: header row (1-based)", min_value=1, max_value=30,
        value=_guess_header(raw) + 1, step=1, key=f"{key}_header"
    )
    if upload.name.lower().endswith(".csv"):
        df = pd.read_csv(io.BytesIO(upload.getvalue()), header=int(header_row) - 1)
    elif _is_html_xls(upload):
        header_index = int(header_row) - 1
        if header_index >= len(raw):
            raise ValueError("Selected header row is outside the E-Way Bill table.")
        df = raw.iloc[header_index + 1:].copy()
        df.columns = raw.iloc[header_index].astype(str).str.strip().tolist()
    else:
        df = pd.read_excel(io.BytesIO(upload.getvalue()), sheet_name=sheet, header=int(header_row) - 1)
    df = df.loc[:, ~df.columns.astype(str).str.match(r"^Unnamed")]
    return df


def _map_side(df, side, key):
    st.markdown(f"**{side} column mapping**")
    fields = {}
    for role in ("GSTIN", "Invoice Number", "Invoice Date", "Amount", "Name of Party"):
        guess = _guess_column(df.columns, role)
        options = ["(skip)"] + list(df.columns)
        index = options.index(guess) if guess in options else 0
        fields[role] = st.selectbox(role, options, index=index, key=f"{key}_{role}")
    missing = [role for role in ("GSTIN", "Invoice Number", "Invoice Date", "Amount") if fields[role] == "(skip)"]
    if missing:
        st.warning(f"Choose columns for: {', '.join(missing)}")
        return None

    out = pd.DataFrame(index=df.index)
    for role, source in fields.items():
        out[role] = df[source] if source != "(skip)" else ""
    out["GSTIN"] = out["GSTIN"].astype(str).str.strip().str.upper()
    out["Invoice Number"] = out["Invoice Number"].astype(str).str.strip()
    out["Invoice Date"] = pd.to_datetime(out["Invoice Date"], dayfirst=True, errors="coerce")
    amount = (out["Amount"].astype(str).str.replace(",", "", regex=False)
              .str.replace("₹", "", regex=False).str.strip())
    out["Amount"] = pd.to_numeric(amount, errors="coerce")
    out = out[out["GSTIN"].str.match(r"^\d{2}[A-Z0-9]{13}$", na=False)]
    out = out[~out["Invoice Number"].str.casefold().isin(("", "nan", "none"))]
    out = out[out["Amount"].notna()].copy()

    canonical = pd.DataFrame(index=out.index)
    canonical["GSTIN"] = out["GSTIN"]
    canonical["Name of Party"] = out["Name of Party"]
    canonical["Invoice Number"] = out["Invoice Number"]
    canonical["Invoice Date"] = out["Invoice Date"]
    # The common matcher compares this numeric field; here it represents the
    # user-selected invoice/e-way bill amount, not taxable value.
    canonical["Taxable Value"] = out["Amount"].astype(float)
    canonical["Invoice Value"] = out["Amount"].astype(float)
    for col in ("IGST", "CGST", "SGST", "Cess"):
        canonical[col] = 0.0
    return canonical[CANONICAL_COLUMNS].reset_index(drop=True)


def _labels(result, mode="sales"):
    frame = result.copy()
    status_col = "Recon_Status" if "Recon_Status" in frame.columns else None
    if status_col:
        frame["Reconciliation Status"] = frame[status_col].map({
            "Matched": "Matched",
            "Smart Matched (Date Mismatch)": "Smart Matched — date differs",
            "Smart Matched (Invoice Mismatch)": "Smart Matched — invoice number differs",
            "Smart Matched (Mismatch)": "Smart Matched — amount differs",
            "Suggestion": "Suggested match — review",
            "Suggestion (Group Match)": "Suggested group match — review",
            "Manually Linked": "Manually linked — review",
            "Invoices Not in GSTR-2B": ("In GSTR-1 B2B — no active E-Way Bill" if mode == "gstr1" else "In Sales Register — no active E-Way Bill"),
            "Invoices Not in Purchase Books": ("In active E-Way Bill report — not in GSTR-1 B2B" if mode == "gstr1" else "In active E-Way Bill report — not in Sales Register"),
        }).fillna(frame[status_col].astype(str))
    return frame


def _xlsx(result, summary):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter", datetime_format="dd/mm/yyyy") as writer:
        summary.to_excel(writer, index=False, sheet_name="Summary")
        result.to_excel(writer, index=False, sheet_name="Reconciliation")
        for name in ("Summary", "Reconciliation"):
            ws = writer.sheets[name]
            ws.freeze_panes(1, 0)
            ws.autofilter(0, 0, max(len(summary if name == "Summary" else result), 1), max(len(summary.columns if name == "Summary" else result.columns) - 1, 0))
    return output.getvalue()


def render_module6(mode="sales"):
    is_gstr1 = mode == "gstr1"
    module_no = "03" if is_gstr1 else "06"
    prefix = "m3" if is_gstr1 else "m6"
    left_label = "GSTR-1 B2B" if is_gstr1 else "Sales Register / GSTR-1 B2B"
    left_upload_label = "Upload GSTR-1 workbook (B2B)" if is_gstr1 else "Upload Sales Register or GSTR-1 workbook (B2B)"
    result_key = f"module{module_no}_results"

    if is_gstr1:
        st.title("Module 03 · GSTR-1 B2B vs E-Way Bill")
        st.caption("Compare filed GSTR-1 B2B invoices against active outward E-Way Bills using the existing reconciliation rules.")
    else:
        st.title("Module 06 · E-Way Bill vs Sales Register")
        st.caption("Manual portal login and CAPTCHA. Download the official monthly report, then upload it here with your Sales Register.")
    if st.button("← Dashboard", key=f"{prefix}_dashboard"):
        st.session_state["show_dashboard"] = True
        st.session_state["app_stage"] = "setup"
        st.session_state.pop(result_key, None)
        st.rerun()

    portal_col, instructions_col = st.columns([1, 2])
    with portal_col:
        st.link_button("Open official E-Way Bill portal", PORTAL_URL, type="primary", use_container_width=True)
    with instructions_col:
        st.info("Open the portal in the new tab, log in and complete CAPTCHA yourself. Download the outward/monthly E-Way Bill Excel report, then return and upload it here. The app does not automate login or CAPTCHA.")

    saved = st.session_state.get(result_key)
    if saved:
        frame = saved["frame"]
        st.success(f"Reconciliation complete · {len(frame):,} rows · amount tolerance ₹{saved['tolerance']:,.2f}")
        summary = frame["Reconciliation Status"].value_counts().rename("Rows").rename_axis("Status").reset_index()
        st.dataframe(summary, use_container_width=True, hide_index=True)
        st.caption("Showing up to five example rows.")
        st.dataframe(frame.head(5), use_container_width=True, hide_index=True)
        report_label = "GSTR-1 B2B vs E-Way Bill" if is_gstr1 else "E-Way Bill vs Sales"
        file_label = "GSTR1_B2B_vs_EWayBill" if is_gstr1 else "EWayBill_vs_Sales"
        st.download_button(f"Download {report_label} reconciliation", _xlsx(frame, summary),
                           file_name=f"{file_label}_Reconciliation.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           type="primary", use_container_width=True)
        if st.button("Start another reconciliation", key=f"{prefix}_reset"):
            st.session_state.pop(result_key, None)
            st.rerun()
        return

    left_file = st.file_uploader(left_upload_label, type=["xlsx", "xls", "csv"], key=f"{prefix}_left")
    eway_files = st.file_uploader("Upload monthly E-Way Bill Excel file(s)", type=["xlsx", "csv"],
                                  accept_multiple_files=True, key=f"{prefix}_eway")
    if not left_file or not eway_files:
        st.info(f"Upload the {left_label} workbook and one or more monthly E-Way Bill reports to continue.")
        return

    try:
        left_sheets = _sheets(left_file)
        default_sheet = 0
        for candidate in ("b2b,sez,de", "b2b", "b2b invoices"):
            match = next((i for i, name in enumerate(left_sheets) if name.strip().casefold() == candidate), None)
            if match is not None:
                default_sheet = match
                break
        left_sheet = st.selectbox(f"{left_label} sheet", left_sheets, index=default_sheet, key=f"{prefix}_left_sheet")
        left_df = _load_with_header(left_file, left_sheet, f"{prefix}_left")
        type_col = _guess_column(left_df.columns, "Invoice Type")
        if type_col:
            b2b_mask = left_df[type_col].astype(str).str.contains("B2B", case=False, na=False)
            left_df = left_df.loc[b2b_mask].copy()
            st.caption(f"B2B-only filter using '{type_col}': {len(left_df):,} invoice row(s) retained.")
        elif is_gstr1:
            st.warning("Could not find an Invoice Type column to isolate B2B rows. Select a B2B-only sheet or provide a workbook with an Invoice Type column.")
        st.caption(f"{left_label} preview · {len(left_df):,} rows")
        st.dataframe(left_df.head(5), use_container_width=True, hide_index=True)
        with st.expander(f"Map {left_label} columns", expanded=True):
            left = _map_side(left_df, left_label, f"{prefix}_left_map")

        eway_parts = []
        for i, upload in enumerate(eway_files):
            with st.expander(f"E-Way Bill report: {html.escape(upload.name)}", expanded=i == 0):
                sheet = st.selectbox(f"Sheet in {upload.name}", _sheets(upload), key=f"{prefix}_eway_sheet_{i}")
                raw_df = _load_with_header(upload, sheet, f"{prefix}_eway_{i}")
                status_guess = _guess_column(raw_df.columns, "Status")
                status_options = ["(no status filter)"] + list(raw_df.columns)
                status_index = status_options.index(status_guess) if status_guess in status_options else 0
                status_col = st.selectbox("E-Way Bill status column (optional)", status_options,
                                          index=status_index, key=f"{prefix}_eway_status_{i}")
                if status_col != "(no status filter)":
                    status_values = raw_df[status_col].astype(str).str.strip().str.casefold()
                    active_mask = status_values.eq("active")
                    st.caption(f"Keeping {int(active_mask.sum()):,} Active E-Way Bills; excluding {int((~active_mask).sum()):,} other-status row(s), such as cancelled bills.")
                    raw_df = raw_df.loc[active_mask].copy()
                else:
                    st.warning("No status column selected. Cancelled bills may be included; map a status column if present.")
                st.caption(f"Active report preview · {len(raw_df):,} rows")
                st.dataframe(raw_df.head(5), use_container_width=True, hide_index=True)
                mapped = _map_side(raw_df, "E-Way Bill report", f"{prefix}_eway_map_{i}")
                if mapped is not None:
                    eway_parts.append(mapped)

        tolerance = st.number_input("Invoice amount tolerance (₹)", min_value=0.0, value=5.0, step=1.0, key=f"{prefix}_tolerance")
        smart = st.checkbox("Enable existing Smart Match rules", value=True, key=f"{prefix}_smart")
        st.caption("The existing matcher checks GSTIN, invoice number, date, and the selected invoice amount. Review smart and suggested matches before acting on them.")
        if st.button(f"Run Module {module_no} reconciliation", type="primary", use_container_width=True, key=f"{prefix}_run"):
            if left is None or len(eway_parts) != len(eway_files) or (is_gstr1 and len(left_df) == 0):
                st.error("Complete the column mappings and confirm B2B rows are available before running reconciliation.")
                return
            eway = pd.concat(eway_parts, ignore_index=True)
            if eway.empty:
                st.error("No active E-Way Bill rows remain after the status filter.")
                return
            with st.spinner("Applying the existing reconciliation rules..."):
                result, _, _ = run_reconciliation(left, eway, tolerance, [], smart)
            result = _labels(result, mode=mode)
            st.session_state[result_key] = {"frame": result, "tolerance": tolerance, "smart": smart}
            st.rerun()
    except Exception as exc:
        st.error(f"Could not prepare these workbooks: {exc}")
