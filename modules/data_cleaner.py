# modules/data_cleaner.py  — v4.0
# Bug fix: consolidate_invoices now preserves Unique_ID column
#          so Manual Matcher links stay stable across re-runs.

import pandas as pd
import numpy as np


def clean_currency_val(val):
    """Robust conversion to float."""
    if pd.isna(val) or str(val).strip() == '': return 0.0
    try:
        return float(str(val).replace(',', '').replace(' ', ''))
    except:
        return 0.0


def smart_invoice_clean(val):
    """Standardizes Invoice Numbers."""
    if pd.isna(val) or str(val).strip() == '': return ''
    s_val = str(val).strip()
    try:
        f_val = float(s_val)
        if f_val.is_integer(): return str(int(f_val))
    except:
        pass
    return "".join(char for char in s_val if char.isalnum()).upper()


def clean_date_col(series):
    """
    Robust Date Parsing.
    1. If already datetime, keep it.
    2. Try Day-First (India).
    3. If fail, keep original text (Don't delete data).
    """
    if pd.api.types.is_datetime64_any_dtype(series):
        return series
    temp = pd.to_datetime(series, dayfirst=True, errors='coerce')
    return temp.fillna(series)


def consolidate_invoices(df):
    """
    Merges Multi-Rate Invoices (e.g. 1GIRL LIFESTYLE Fix).
    BUG FIX v4.0: Unique_ID is now preserved (takes 'first' value per group).
    """
    if 'GSTIN' not in df.columns or 'Clean_Inv' not in df.columns:
        return df

    sum_cols = ['Taxable Value', 'IGST', 'CGST', 'SGST', 'Cess', 'Invoice Value']
    for c in sum_cols:
        if c not in df.columns:
            df[c] = 0.0
        df[c] = df[c].apply(clean_currency_val)

    # Build aggregation dict for non-numeric columns
    keep_cols = {}
    for col in ['Invoice Date', 'Name of Party', 'Invoice Number', 'Date_Str',
                'Place of Supply', 'Reverse Charge', 'Unique_ID']:
        if col in df.columns:
            keep_cols[col] = 'first'

    df_clean = df[df['Clean_Inv'] != ''].copy()

    # Build a single agg dict and pass it as positional arg (works in all pandas versions)
    agg_dict = {c: 'sum' for c in sum_cols if c in df_clean.columns}
    agg_dict.update(keep_cols)

    df_grouped = df_clean.groupby(['GSTIN', 'Clean_Inv'], as_index=False).agg(agg_dict)
    return df_grouped


def process_dataset(df):
    """Master Pipeline"""
    df = df.copy()

    # A. Clean Date
    if 'Invoice Date' in df.columns:
        df['Invoice Date'] = clean_date_col(df['Invoice Date'])
        df['Date_Str'] = pd.to_datetime(df['Invoice Date'], errors='coerce').dt.strftime('%Y%m%d').fillna('')

    # B. Clean Invoice
    if 'Invoice Number' in df.columns:
        df['Clean_Inv'] = df['Invoice Number'].apply(smart_invoice_clean)

    # C. Merge Multi-Rate (preserves Unique_ID)
    if 'GSTIN' in df.columns and 'Clean_Inv' in df.columns:
        df = consolidate_invoices(df)

    return df
