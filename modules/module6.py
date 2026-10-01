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
    "GSTIN": ("gstin", "gstin of recipient", "recipient gstin", "to gstin", "party gstin", "customer gstin"),
    "Invoice Number": ("invoice number", "invoice no", "document number", "document no", "doc no", "bill no"),
    "Invoice Date": ("invoice date", "document date", "doc date", "bill date", "date"),
    "Amount": ("invoice value", "total invoice value", "total value", "document value", "total amount", "invoice amount", "gross amount"),
    "Name of Party": ("party name", "recipient name", "to trade name", "customer name", "receiver name", "name"),
    "Status": ("status", "eway status", "e-way bill status", "ewb status"),
}
CANONICAL_COLUMNS = ["GSTIN", "Name of Party", "Invoice Number", "Invoice Date",
                     "Taxable Value", "IGST", "CGST", "SGST", "Cess", "Invoice Value"]


def _norm(value):
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def _read(upload, sheet):
    data = io.BytesIO(upload.getvalue())
    if upload.name.lower().endswith(".csv"):
        return pd.read_csv(data, header=None)
    return pd.read_excel(data, sheet_name=sheet, header=None)


def _sheets(upload):
    if upload.name.lower().endswith(".csv"):
        return ["CSV"]
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


def _labels(result):
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
            "Invoices Not in GSTR-2B": "In Sales Register — no E-Way Bill match",
            "Invoices Not in Purchase Books": "In E-Way Bill report — no Sales Register match",
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


def render_module6():
    st.title("Module 06 · E-Way Bill vs Sales Register")
    st.caption("Manual portal login and CAPTCHA. Download the official monthly report, then upload it here with your Sales Register.")
    if st.button("← Dashboard", key="m6_dashboard"):
        st.session_state["show_dashboard"] = True
        st.session_state["app_stage"] = "setup"
        st.session_state.pop("module6_results", None)
        st.rerun()

    portal_col, instructions_col = st.columns([1, 2])
    with portal_col:
        st.link_button("Open official E-Way Bill portal", PORTAL_URL, type="primary", use_container_width=True)
    with instructions_col:
        st.info("In the new tab, log in and complete the CAPTCHA yourself. Download the outward/monthly E-Way Bill Excel report, then return here. This app does not read the portal session or download files from it.")

    saved = st.session_state.get("module6_results")
    if saved:
        frame = saved["frame"]
        st.success(f"Reconciliation complete · {len(frame):,} rows · amount tolerance ₹{saved['tolerance']:,.2f}")
        summary = frame["Reconciliation Status"].value_counts().rename("Rows").rename_axis("Status").reset_index()
        st.dataframe(summary, use_container_width=True, hide_index=True)
        st.caption("Showing up to five example rows.")
        st.dataframe(frame.head(5), use_container_width=True, hide_index=True)
        st.download_button("Download E-Way Bill vs Sales reconciliation", _xlsx(frame, summary),
                           file_name="EWayBill_vs_Sales_Reconciliation.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           type="primary", use_container_width=True)
        if st.button("Start another reconciliation", key="m6_reset"):
            st.session_state.pop("module6_results", None)
            st.rerun()
        return

    sales_file = st.file_uploader("Upload Sales Register", type=["xlsx", "csv"], key="m6_sales")
    eway_files = st.file_uploader("Upload monthly E-Way Bill Excel file(s)", type=["xlsx", "csv"],
                                  accept_multiple_files=True, key="m6_eway")
    if not sales_file or not eway_files:
        st.info("Upload the Sales Register and one or more monthly E-Way Bill reports to continue.")
        return

    try:
        sales_sheet = st.selectbox("Sales Register sheet", _sheets(sales_file), key="m6_sales_sheet")
        sales_df = _load_with_header(sales_file, sales_sheet, "m6_sales")
        st.caption(f"Sales Register preview · {len(sales_df):,} rows")
        st.dataframe(sales_df.head(5), use_container_width=True, hide_index=True)
        with st.expander("Map Sales Register columns", expanded=True):
            sales = _map_side(sales_df, "Sales Register", "m6_sales_map")

        eway_parts = []
        for i, upload in enumerate(eway_files):
            with st.expander(f"E-Way Bill report: {html.escape(upload.name)}", expanded=i == 0):
                sheet = st.selectbox(f"Sheet in {upload.name}", _sheets(upload), key=f"m6_eway_sheet_{i}")
                raw_df = _load_with_header(upload, sheet, f"m6_eway_{i}")
                status_guess = _guess_column(raw_df.columns, "Status")
                status_options = ["(no status filter)"] + list(raw_df.columns)
                status_index = status_options.index(status_guess) if status_guess in status_options else 0
                status_col = st.selectbox(
                    "E-Way Bill status column (optional)", status_options,
                    index=status_index, key=f"m6_eway_status_{i}"
                )
                if status_col != "(no status filter)":
                    status_values = raw_df[status_col].astype(str).str.strip().str.casefold()
                    active_mask = status_values.eq("active")
                    st.caption(f"Keeping {int(active_mask.sum()):,} Active E-Way Bills; excluding {int((~active_mask).sum()):,} other-status row(s), such as cancelled bills.")
                    raw_df = raw_df.loc[active_mask].copy()
                else:
                    st.warning("No status column selected. Cancelled bills may be included; map a status column if present.")
                st.caption(f"Active report preview · {len(raw_df):,} rows")
                st.dataframe(raw_df.head(5), use_container_width=True, hide_index=True)
                mapped = _map_side(raw_df, "E-Way Bill report", f"m6_eway_map_{i}")
                if mapped is not None:
                    eway_parts.append(mapped)

        tolerance = st.number_input("Invoice amount tolerance (₹)", min_value=0.0, value=5.0, step=1.0, key="m6_tolerance")
        smart = st.checkbox("Enable existing Smart Match rules", value=True, key="m6_smart")
        st.caption("The existing matcher checks GSTIN, invoice number, date, and the selected amount field. Verify suggested and smart matches before acting on them.")
        if st.button("Run E-Way Bill vs Sales reconciliation", type="primary", use_container_width=True, key="m6_run"):
            if sales is None or len(eway_parts) != len(eway_files):
                st.error("Complete all required column mappings before running reconciliation.")
                return
            eway = pd.concat(eway_parts, ignore_index=True)
            with st.spinner("Applying the existing reconciliation rules..."):
                result, _, _ = run_reconciliation(sales, eway, tolerance, [], smart)
            result = _labels(result)
            st.session_state["module6_results"] = {"frame": result, "tolerance": tolerance, "smart": smart}
            st.rerun()
    except Exception as exc:
        st.error(f"Could not prepare these workbooks: {exc}")
