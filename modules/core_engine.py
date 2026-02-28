# modules/core_engine.py — v4.1
# Based on original working engine uploaded by user.
# Only structural change: Unique_ID assigned BEFORE process_dataset()
# so consolidate_invoices() preserves them (data_cleaner v4 fix).

import pandas as pd
import streamlit as st
import re
from .data_utils import clean_currency
from .data_cleaner import process_dataset

# --- HELPERS ---
def smart_invoice_clean(val):
    """Standardizes Invoice Numbers (Keep Alphanumeric)."""
    if pd.isna(val) or str(val).strip() == '': return ''
    s_val = str(val).strip()
    try:
        f_val = float(s_val)
        if f_val.is_integer(): return str(int(f_val))
    except: pass
    return "".join(char for char in s_val if char.isalnum()).upper()

def numeric_invoice_clean(val):
    """
    [ENHANCED] Aggressive Cleaning: Keeps ONLY Digits.
    Fixes cases like '82' vs 'BB/82'.
    """
    val = smart_invoice_clean(val)
    return "".join(char for char in val if char.isdigit())

def perform_merge_pass(df_left, df_right, key_col, status_label, logic_label,
                       check_value_tolerance=False, tolerance=5.0, enforce_one_to_one=False,
                       check_fy=False):

    if enforce_one_to_one:
        df_left  = df_left.copy()
        df_right = df_right.copy()
        df_left['dedup_id']  = df_left.groupby(key_col).cumcount()
        df_right['dedup_id'] = df_right.groupby(key_col).cumcount()
        merge_keys = [key_col, 'dedup_id']
    else:
        merge_keys = key_col

    merged    = pd.merge(df_left, df_right, on=merge_keys, how='outer',
                         suffixes=('_BOOKS', '_GST'), indicator=True)
    potential = merged[merged['_merge'] == 'both'].copy()

    matched       = pd.DataFrame()
    failed_matches = pd.DataFrame()

    if not potential.empty:
        potential['Diff'] = abs(
            potential['Taxable Value_BOOKS'].fillna(0) - potential['Taxable Value_GST'].fillna(0)
        )

        mask_val = potential['Diff'] <= tolerance if check_value_tolerance else \
                   pd.Series([True] * len(potential), index=potential.index)

        if check_fy:
            if 'Date_Str_BOOKS' in potential.columns and 'Date_Str_GST' in potential.columns:
                fy_b    = potential['Date_Str_BOOKS'].astype(str).str[:4]
                fy_g    = potential['Date_Str_GST'].astype(str).str[:4]
                mask_fy = (fy_b == fy_g)
            else:
                mask_fy = pd.Series([True] * len(potential), index=potential.index)
        else:
            mask_fy = pd.Series([True] * len(potential), index=potential.index)

        valid_mask = mask_val & mask_fy

        matched = potential[valid_mask].copy()
        matched['Recon_Status'] = status_label
        matched['Match_Logic']  = logic_label

        failed_matches = potential[~valid_mask].copy()

    left_only = merged[merged['_merge'] == 'left_only'].copy()
    if not failed_matches.empty:
        left_only = pd.concat([left_only, failed_matches], ignore_index=True)

    b_cols         = {c: c.replace('_BOOKS', '') for c in left_only.columns if '_BOOKS' in c}
    cols_to_keep_b = [c for c in b_cols.keys() if 'dedup_id' not in c and 'Unique_ID' not in c] + ['Unique_ID_BOOKS']
    cols_to_keep_b = [c for c in cols_to_keep_b if c in left_only.columns]
    df_books_out   = left_only[cols_to_keep_b].rename(columns=b_cols).rename(columns={'Unique_ID_BOOKS': 'Unique_ID'})

    right_only = merged[merged['_merge'] == 'right_only'].copy()
    if not failed_matches.empty:
        right_only = pd.concat([right_only, failed_matches], ignore_index=True)

    g_cols         = {c: c.replace('_GST', '') for c in right_only.columns if '_GST' in c}
    cols_to_keep_g = [c for c in g_cols.keys() if 'dedup_id' not in c and 'Unique_ID' not in c] + ['Unique_ID_GST']
    cols_to_keep_g = [c for c in cols_to_keep_g if c in right_only.columns]
    df_gst_out     = right_only[cols_to_keep_g].rename(columns=g_cols).rename(columns={'Unique_ID_GST': 'Unique_ID'})

    if enforce_one_to_one and 'dedup_id' in matched.columns:
        matched.drop(columns=['dedup_id'], inplace=True)

    return matched, df_books_out, df_gst_out


def run_reconciliation(df_books, df_gst, tolerance, manual_pairs, smart_mode_enabled):
    progress_bar = st.progress(0, text="Initializing...")

    # STRUCTURAL CHANGE: Assign Unique_IDs BEFORE process_dataset
    # so consolidate_invoices() can preserve them (data_cleaner v4).
    if 'Unique_ID' not in df_books.columns:
        df_books = df_books.copy()
        df_books['Unique_ID'] = ["B_" + str(i) for i in range(len(df_books))]
    if 'Unique_ID' not in df_gst.columns:
        df_gst = df_gst.copy()
        df_gst['Unique_ID'] = ["G_" + str(i) for i in range(len(df_gst))]

    df_books = process_dataset(df_books)
    df_gst   = process_dataset(df_gst)

    # MANUAL MATCHES
    manual_book_ids = [m[0] for m in manual_pairs]
    manual_gst_ids  = [m[1] for m in manual_pairs]

    manual_rows = []
    for b_id, g_id in manual_pairs:
        b_row = df_books[df_books['Unique_ID'] == b_id]
        g_row = df_gst[df_gst['Unique_ID'] == g_id]
        if not b_row.empty and not g_row.empty:
            combined = {k + "_BOOKS": v for k, v in b_row.iloc[0].to_dict().items()}
            for k, v in g_row.iloc[0].to_dict().items():
                combined[k + "_GST"] = v
            combined['Recon_Status'] = "Manually Linked"
            combined['Match_Logic']  = "User Selection"
            manual_rows.append(combined)

    matched_manual = pd.DataFrame(manual_rows) if manual_rows else pd.DataFrame()
    df_books = df_books[~df_books['Unique_ID'].isin(manual_book_ids)]
    df_gst   = df_gst[~df_gst['Unique_ID'].isin(manual_gst_ids)]

    # DATA CLEANING
    for c in ['Taxable Value', 'IGST', 'CGST', 'SGST', 'Cess', 'Invoice Value']:
        df_books[c] = df_books[c].apply(clean_currency).fillna(0)
        df_gst[c]   = df_gst[c].apply(clean_currency).fillna(0)

    df_books['Invoice Date'] = pd.to_datetime(df_books['Invoice Date'], dayfirst=True, errors='coerce')
    df_gst['Invoice Date']   = pd.to_datetime(df_gst['Invoice Date'],   dayfirst=True, errors='coerce')

    df_books['Date_Str'] = df_books['Invoice Date'].dt.strftime('%Y%m%d').fillna('')
    df_gst['Date_Str']   = df_gst['Invoice Date'].dt.strftime('%Y%m%d').fillna('')

    df_books['Clean_Inv'] = df_books['Invoice Number'].apply(smart_invoice_clean)
    df_gst['Clean_Inv']   = df_gst['Invoice Number'].apply(smart_invoice_clean)

    # [ENHANCED] Numeric Invoices (Digits Only) for Prerana Case
    df_books['Num_Inv'] = df_books['Invoice Number'].apply(numeric_invoice_clean)
    df_gst['Num_Inv']   = df_gst['Invoice Number'].apply(numeric_invoice_clean)

    df_books['Round_Taxable'] = df_books['Taxable Value'].round(0).astype(int)
    df_gst['Round_Taxable']   = df_gst['Taxable Value'].round(0).astype(int)

    # Ensure Name Map exists for final cleanup
    all_parties = pd.concat([df_books[['GSTIN', 'Name of Party']], df_gst[['GSTIN', 'Name of Party']]])
    name_map    = (all_parties.dropna(subset=['Name of Party'])
                              .drop_duplicates('GSTIN')
                              .set_index('GSTIN')['Name of Party'].to_dict())

    results = []
    if not matched_manual.empty:
        results.append(matched_manual)

    # Step 1: Exact Match
    progress_bar.progress(10, text="Step 1: Exact Match...")
    df_books['K1'] = df_books['GSTIN'].astype(str) + "_" + df_books['Clean_Inv'] + "_" + df_books['Date_Str']
    df_gst['K1']   = df_gst['GSTIN'].astype(str)   + "_" + df_gst['Clean_Inv']   + "_" + df_gst['Date_Str']
    matched_1, books_left, gst_left = perform_merge_pass(
        df_books, df_gst, 'K1', 'Matched', 'Exact Match',
        check_value_tolerance=True, tolerance=tolerance, enforce_one_to_one=True
    )
    results.append(matched_1)

    # Step 2: Date Mismatch
    progress_bar.progress(30, text="Step 2: Date Mismatch...")
    books_left['K2'] = books_left['GSTIN'].astype(str) + "_" + books_left['Clean_Inv']
    gst_left['K2']   = gst_left['GSTIN'].astype(str)   + "_" + gst_left['Clean_Inv']
    matched_2, books_left, gst_left = perform_merge_pass(
        books_left, gst_left, 'K2', 'AI Matched (Date Mismatch)', 'Date Mismatch',
        check_value_tolerance=True, tolerance=tolerance, enforce_one_to_one=True, check_fy=True
    )
    results.append(matched_2)

    # Step 3: Invoice Mismatch
    progress_bar.progress(50, text="Step 3: Invoice Mismatch...")
    books_left['K3'] = books_left['GSTIN'].astype(str) + "_" + books_left['Date_Str']
    gst_left['K3']   = gst_left['GSTIN'].astype(str)   + "_" + gst_left['Date_Str']
    matched_3, books_left, gst_left = perform_merge_pass(
        books_left, gst_left, 'K3', 'AI Matched (Invoice Mismatch)', 'Invoice Mismatch',
        check_value_tolerance=True, tolerance=tolerance, enforce_one_to_one=True
    )
    results.append(matched_3)

    # Step 4: Value Mismatch ([ENHANCED] PRERANA FIX)
    progress_bar.progress(70, text="Step 4: Value Mismatch...")
    books_left['K4'] = books_left['GSTIN'].astype(str) + "_" + books_left['Num_Inv']
    gst_left['K4']   = gst_left['GSTIN'].astype(str)   + "_" + gst_left['Num_Inv']
    b_valid   = books_left[books_left['Num_Inv'] != '']
    g_valid   = gst_left[gst_left['Num_Inv'] != '']
    b_invalid = books_left[books_left['Num_Inv'] == '']
    g_invalid = gst_left[gst_left['Num_Inv'] == '']
    matched_4, b_rem, g_rem = perform_merge_pass(
        b_valid, g_valid, 'K4', 'AI Matched (Mismatch)', 'Value Mismatch',
        check_value_tolerance=False, enforce_one_to_one=True
    )
    results.append(matched_4)
    books_left = pd.concat([b_rem, b_invalid], ignore_index=True)
    gst_left   = pd.concat([g_rem, g_invalid], ignore_index=True)

    # Step 5: Smart Suggestions
    if smart_mode_enabled:
        progress_bar.progress(85, text="Step 5: Smart Suggestions...")

        # 5a. Inv + Value
        b_valid   = books_left[books_left['Clean_Inv'] != '']
        g_valid   = gst_left[gst_left['Clean_Inv'] != '']
        b_invalid = books_left[books_left['Clean_Inv'] == '']
        g_invalid = gst_left[gst_left['Clean_Inv'] == '']
        b_valid = b_valid.copy(); b_valid['K5a'] = b_valid['Clean_Inv'] + "_" + b_valid['Round_Taxable'].astype(str)
        g_valid = g_valid.copy(); g_valid['K5a'] = g_valid['Clean_Inv'] + "_" + g_valid['Round_Taxable'].astype(str)
        matched_5a, b_left_valid, g_left_valid = perform_merge_pass(
            b_valid, g_valid, 'K5a', 'Suggestion', 'Inv No + Val Match',
            check_value_tolerance=True, tolerance=tolerance, enforce_one_to_one=True
        )
        results.append(matched_5a)
        books_left = pd.concat([b_left_valid, b_invalid], ignore_index=True)
        gst_left   = pd.concat([g_left_valid, g_invalid], ignore_index=True)

        # 5b. Date + Value
        b_valid   = books_left[books_left['Date_Str'] != '']
        g_valid   = gst_left[gst_left['Date_Str'] != '']
        b_invalid = books_left[books_left['Date_Str'] == '']
        g_invalid = gst_left[gst_left['Date_Str'] == '']
        b_valid = b_valid.copy(); b_valid['K5b'] = b_valid['Date_Str'] + "_" + b_valid['Round_Taxable'].astype(str)
        g_valid = g_valid.copy(); g_valid['K5b'] = g_valid['Date_Str'] + "_" + g_valid['Round_Taxable'].astype(str)
        matched_5b, b_left_valid, g_left_valid = perform_merge_pass(
            b_valid, g_valid, 'K5b', 'Suggestion', 'Date + Val Match',
            check_value_tolerance=True, tolerance=tolerance, enforce_one_to_one=True
        )
        results.append(matched_5b)
        books_left = pd.concat([b_left_valid, b_invalid], ignore_index=True)
        gst_left   = pd.concat([g_left_valid, g_invalid], ignore_index=True)

        # 5c. Value Only ([ENHANCED] Neighbor Match)
        g_exact    = gst_left.copy(); g_exact['K5c']  = g_exact['Round_Taxable'].astype(str)
        g_plus     = gst_left.copy(); g_plus['K5c']   = (g_plus['Round_Taxable'] + 1).astype(str)
        g_minus    = gst_left.copy(); g_minus['K5c']  = (g_minus['Round_Taxable'] - 1).astype(str)
        g_combined = pd.concat([g_exact, g_plus, g_minus], ignore_index=True)
        books_left = books_left.copy()
        books_left['K5c'] = books_left['Round_Taxable'].astype(str)
        matched_5c, books_left, _ = perform_merge_pass(
            books_left, g_combined, 'K5c', 'Suggestion', 'Value Match (Approx)',
            check_value_tolerance=True, tolerance=tolerance, enforce_one_to_one=True
        )
        if not matched_5c.empty:
            matched_gst_ids = matched_5c['Unique_ID_GST'].unique()
            gst_left = gst_left[~gst_left['Unique_ID'].isin(matched_gst_ids)]
        results.append(matched_5c)

    # Step 6: Group Matching ([ENHANCED] VENUS MILL FIX)
    progress_bar.progress(90, text="Step 6: Group Matching...")

    b_grp = books_left.groupby('GSTIN')['Taxable Value'].sum()
    g_grp = gst_left.groupby('GSTIN')['Taxable Value'].sum()
    common_gstins = b_grp.index.intersection(g_grp.index)
    match_gstins  = [g for g in common_gstins if abs(b_grp[g] - g_grp[g]) <= tolerance]

    if match_gstins:
        b_group_match = books_left[books_left['GSTIN'].isin(match_gstins)].copy()
        g_group_match = gst_left[gst_left['GSTIN'].isin(match_gstins)].copy()

        # Add Suffix FIRST, then status columns (prevents Recon_Status_BOOKS)
        b_group_match = b_group_match.add_suffix('_BOOKS')
        b_group_match['Recon_Status'] = "Suggestion (Group Match)"
        b_group_match['Match_Logic']  = "Total Value Matches"

        g_group_match = g_group_match.add_suffix('_GST')
        g_group_match['Recon_Status'] = "Suggestion (Group Match)"
        g_group_match['Match_Logic']  = "Total Value Matches"

        results.append(b_group_match)
        results.append(g_group_match)

        books_left = books_left[~books_left['GSTIN'].isin(match_gstins)]
        gst_left   = gst_left[~gst_left['GSTIN'].isin(match_gstins)]

    # Finalize Leftovers — Add Suffix FIRST
    progress_bar.progress(95, text="Finalizing...")
    books_left = books_left.add_suffix('_BOOKS')
    books_left['Recon_Status'] = "Invoices Not in GSTR-2B"
    books_left['Match_Logic']  = "Unmatched"

    gst_left = gst_left.add_suffix('_GST')
    gst_left['Recon_Status'] = "Invoices Not in Purchase Books"
    gst_left['Match_Logic']  = "Unmatched"

    results.append(books_left)
    results.append(gst_left)

    final_df = pd.concat(results, ignore_index=True)

    # POST-PROCESSING
    mask_match      = final_df['Recon_Status'].str.contains('Matched', na=False)
    mask_taxable_ok = abs(final_df['Taxable Value_BOOKS'].fillna(0) - final_df['Taxable Value_GST'].fillna(0)) < 1.0
    mask_tax_diff   = (
        (abs(final_df['IGST_BOOKS'].fillna(0) - final_df['IGST_GST'].fillna(0)) > 1.0) |
        (abs(final_df['CGST_BOOKS'].fillna(0) - final_df['CGST_GST'].fillna(0)) > 1.0)
    )
    final_df.loc[mask_match & mask_taxable_ok & mask_tax_diff, 'Recon_Status'] = "Matched (Tax Error)"

    # Coalesce Columns
    final_df['GSTIN'] = final_df['GSTIN_BOOKS'].fillna(final_df['GSTIN_GST'])

    if 'Name of Party_BOOKS' in final_df.columns:
        final_df['Name of Party'] = final_df['Name of Party_BOOKS'].fillna(final_df['Name of Party_GST'])
    else:
        final_df['Name of Party'] = final_df.get('Name of Party_GST', '')

    final_df['Name of Party'] = final_df['Name of Party'].fillna(
        final_df['GSTIN'].map(name_map)).fillna('Unknown')

    drop_cols = ['K1','K2','K3','K4','K5a','K5b','K5c','Diff','dedup_id','Num_Inv_BOOKS','Num_Inv_GST']
    final_df.drop(columns=[c for c in drop_cols if c in final_df.columns], inplace=True)

    progress_bar.progress(100, text="Done!")
    return final_df, df_books, df_gst
