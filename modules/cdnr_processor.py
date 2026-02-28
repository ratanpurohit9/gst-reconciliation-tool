# modules/cdnr_processor.py  ── v4.0
# Full 6-step cascade mirroring core_engine.py exactly
# ● abs() all monetary values before matching (sign-agnostic)
# ● Tax Error: CDNR Matched (Tax Error) when IGST/CGST/SGST diff > ₹1
# ● Trade Name auto-filled from GSTR-2B via GSTIN lookup
# ● CDNRA kill-and-replace applied before matching

import pandas as pd
import numpy as np
import streamlit as st

# ────────────────────────────────────────────────────────────
# HARDCODED COLUMN INDICES
# ────────────────────────────────────────────────────────────
G2B_HEADER_ROW  = 5   # pd.read_excel header=5  → Row 6 of Excel
G2B_COL_GSTIN   = 0   # A  – GSTIN of Supplier
G2B_COL_TRADNM  = 1   # B  – Trade/Legal Name
G2B_COL_NOTENO  = 2   # C  – Note Number
G2B_COL_NOTYPE  = 3   # D  – Note Type  ("Credit Note" / "Debit Note")
G2B_COL_DATE    = 5   # F  – Note Date
G2B_COL_TAXVAL  = 10  # K  – Taxable Value
G2B_COL_IGST    = 11  # L  – Integrated Tax
G2B_COL_CGST    = 12  # M  – Central Tax
G2B_COL_SGST    = 13  # N  – State/UT Tax
G2B_COL_CESS    = 14  # O  – Cess

BK_HEADER_ROW   = 3   # pd.read_excel header=3  → Row 4 of Excel
BK_COL_GSTIN    = 0   # A  – GSTIN of Supplier
BK_COL_NOTENO   = 1   # B  – Note/Refund Voucher Number
BK_COL_DATE     = 2   # C  – Note/Refund Voucher date  ← CONFIRMED from raw data
BK_COL_DOCTYPE  = 6   # G  – Document Type  ("D"=Debit Note / "C"=Credit Note)
BK_COL_TAXVAL   = 11  # L  – Taxable Value
BK_COL_IGST     = 12  # M  – Integrated Tax Paid
BK_COL_CGST     = 13  # N  – Central Tax Paid
BK_COL_SGST     = 14  # O  – State/UT Tax Paid


# ────────────────────────────────────────────────────────────
# LOW-LEVEL HELPERS
# ────────────────────────────────────────────────────────────

def _f(v):
    """Safe abs-float conversion – always positive."""
    try:
        return abs(round(float(str(v).replace(',', '').strip()), 2))
    except Exception:
        return 0.0

def _gstin(v):
    return '' if pd.isna(v) else str(v).strip().upper()

def _date(v):
    if pd.isna(v):
        return pd.NaT
    result = pd.to_datetime(v, dayfirst=True, errors='coerce')
    if pd.isna(result):
        return pd.NaT
    return result.normalize()

def _date_str(dt):
    try:
        return pd.Timestamp(dt).strftime('%Y%m%d')
    except Exception:
        return ''

def _type2b(v):
    return '' if pd.isna(v) else str(v).strip().lower()

def _typebk(v):
    return '' if pd.isna(v) else str(v).strip().lower()


# ────────────────────────────────────────────────────────────
# DATASET CLEANER  (mirrors process_dataset / data_cleaner.py)
# ────────────────────────────────────────────────────────────

def _clean(df: pd.DataFrame) -> pd.DataFrame:
    """
    Applies to BOTH Books and GST sides before matching:
      1. abs() all money columns
      2. Normalise Note Date → Date_Str
      3. Round_Taxable for approximate key building
      4. Drop rows with invalid GSTIN (< 15 chars)
    """
    df = df.copy()
    for col in ('Taxable Value', 'IGST', 'CGST', 'SGST', 'Cess'):
        if col in df.columns:
            df[col] = df[col].apply(_f)

    if 'Note Date' in df.columns:
        df['Note Date']    = df['Note Date'].apply(_date)
        df['Date_Str']     = df['Note Date'].apply(_date_str)
    else:
        df['Date_Str'] = ''

    df['Round_Taxable'] = df['Taxable Value'].apply(lambda v: int(round(v, 0)))
    df = df[df['GSTIN'].str.len() == 15].copy()
    df.reset_index(drop=True, inplace=True)
    return df


# ────────────────────────────────────────────────────────────
# MERGE PASS  (mirrors perform_merge_pass from core_engine.py)
# ────────────────────────────────────────────────────────────

def _merge(df_b, df_g, key, status, logic,
           value_tol=False, tolerance=5.0, one_to_one=False):
    """
    Outer-merge on key(s).  Returns (matched_df, books_remain, gst_remain).
    Identical behaviour to core_engine.perform_merge_pass.
    """
    if df_b.empty or df_g.empty:
        return pd.DataFrame(), df_b, df_g

    db, dg = df_b.copy(), df_g.copy()

    # Remove any stale cross-side ID cols to prevent suffix collision
    db.drop(columns=['Unique_ID_BOOKS', 'Unique_ID_GST'], errors='ignore', inplace=True)
    dg.drop(columns=['Unique_ID_BOOKS', 'Unique_ID_GST'], errors='ignore', inplace=True)

    if one_to_one:
        db['_dd'] = db.groupby(key).cumcount()
        dg['_dd'] = dg.groupby(key).cumcount()
        keys = [key, '_dd']
    else:
        keys = key

    merged = pd.merge(db, dg, on=keys, how='outer',
                      suffixes=('_BOOKS', '_GST'), indicator=True)

    both     = merged[merged['_merge'] == 'both'].copy()
    matched  = pd.DataFrame()
    failed   = pd.DataFrame()

    if not both.empty:
        both['_diff_tax'] = abs(
            both['Taxable Value_BOOKS'].fillna(0) -
            both['Taxable Value_GST'].fillna(0)
        )
        mask = both['_diff_tax'] <= tolerance if value_tol else pd.Series(True, index=both.index)
        matched = both[mask].copy()
        matched['Recon_Status_CDNR'] = status
        matched['Match_Logic']       = logic
        failed  = both[~mask].copy()

    left_only  = merged[merged['_merge'] == 'left_only'].copy()
    right_only = merged[merged['_merge'] == 'right_only'].copy()
    if not failed.empty:
        left_only  = pd.concat([left_only,  failed], ignore_index=True)
        right_only = pd.concat([right_only, failed], ignore_index=True)

    def _restore(side_df, suffix, uid_col):
        # uid_col is e.g. 'Unique_ID_BOOKS' — created automatically by merge suffix
        cols_map = {c: c.replace(suffix, '') for c in side_df.columns if c.endswith(suffix)}
        keep = [c for c in cols_map if '_dd' not in c] + ([uid_col] if uid_col in side_df.columns else [])
        keep = list(dict.fromkeys([c for c in keep if c in side_df.columns]))  # dedupe, preserve order
        out  = side_df[keep].rename(columns=cols_map)
        if uid_col in out.columns:
            out = out.rename(columns={uid_col: 'Unique_ID'})
        elif uid_col.replace('_BOOKS','').replace('_GST','') in out.columns:
            out = out.rename(columns={uid_col.replace('_BOOKS','').replace('_GST',''): 'Unique_ID'})
        return out

    b_remain = _restore(left_only,  '_BOOKS', 'Unique_ID_BOOKS')
    g_remain = _restore(right_only, '_GST',   'Unique_ID_GST')

    if one_to_one:
        matched.drop(columns=['_dd'], errors='ignore', inplace=True)
    matched.drop(columns=['_diff_tax', '_merge'], errors='ignore', inplace=True)

    return matched, b_remain, g_remain


# ────────────────────────────────────────────────────────────
# FILE READERS
# ────────────────────────────────────────────────────────────

def read_raw_cdnr_2b(file_obj):
    try:
        file_obj.seek(0)
        xls = pd.ExcelFile(file_obj)
        sheet = None
        for s in xls.sheet_names:
            if s.strip().lower() == 'b2b-cdnr':
                sheet = s; break
        if not sheet:
            for s in xls.sheet_names:
                sl = s.strip().lower()
                if 'cdnr' in sl and 'cdnra' not in sl:
                    sheet = s; break
        if not sheet:
            return None

        raw = pd.read_excel(file_obj, sheet_name=sheet, header=G2B_HEADER_ROW)
        if raw.shape[1] <= G2B_COL_CESS:
            return None

        df = pd.DataFrame({
            'GSTIN'        : raw.iloc[:, G2B_COL_GSTIN].apply(_gstin),
            'Trade Name'   : raw.iloc[:, G2B_COL_TRADNM].astype(str).str.strip(),
            'Note Number'  : raw.iloc[:, G2B_COL_NOTENO].astype(str).str.strip(),
            'Note Type'    : raw.iloc[:, G2B_COL_NOTYPE].apply(_type2b),
            'Note Date'    : raw.iloc[:, G2B_COL_DATE].apply(_date),
            'Taxable Value': raw.iloc[:, G2B_COL_TAXVAL].apply(_f),
            'IGST'         : raw.iloc[:, G2B_COL_IGST].apply(_f),
            'CGST'         : raw.iloc[:, G2B_COL_CGST].apply(_f),
            'SGST'         : raw.iloc[:, G2B_COL_SGST].apply(_f),
            'Cess'         : raw.iloc[:, G2B_COL_CESS].apply(_f),
        })
        df = df[df['GSTIN'].str.len() == 15].reset_index(drop=True)
        return df
    except Exception as e:
        st.warning(f'[CDNR-2B Reader] {e}')
        return None


def read_books_cdnr(file_obj):
    try:
        file_obj.seek(0)
        xls = pd.ExcelFile(file_obj)
        sheet = None
        for s in xls.sheet_names:
            if s.strip().lower() in ('cdnr', 'cndr'):
                sheet = s; break
        if not sheet:
            return None

        raw = pd.read_excel(file_obj, sheet_name=sheet, header=BK_HEADER_ROW)
        if raw.shape[1] <= BK_COL_SGST:
            return None

        doc_type = raw.iloc[:, BK_COL_DOCTYPE].apply(_typebk)
        note_type_map = {'d': 'credit note', 'c': 'debit note'}

        df = pd.DataFrame({
            'GSTIN'        : raw.iloc[:, BK_COL_GSTIN].apply(_gstin),
            'Note Number'  : raw.iloc[:, BK_COL_NOTENO].astype(str).str.strip(),
            'Note Date'    : raw.iloc[:, BK_COL_DATE].apply(_date),
            'Doc Type'     : doc_type,
            'Note Type'    : doc_type.map(note_type_map).fillna(''),
            'Taxable Value': raw.iloc[:, BK_COL_TAXVAL].apply(_f),
            'IGST'         : raw.iloc[:, BK_COL_IGST].apply(_f),
            'CGST'         : raw.iloc[:, BK_COL_CGST].apply(_f),
            'SGST'         : raw.iloc[:, BK_COL_SGST].apply(_f),
            'Cess'         : 0.0,
            'Trade Name'   : '',   # filled after reading 2B
        })
        df = df[(df['GSTIN'].str.len() == 15) & (df['Note Date'].notna())].reset_index(drop=True)
        return df
    except Exception as e:
        st.warning(f'[Books-CDNR Reader] {e}')
        return None


def read_raw_cdnra(file_obj):
    try:
        file_obj.seek(0)
        xls  = pd.ExcelFile(file_obj)
        sheet = next((s for s in xls.sheet_names if 'cdnra' in s.strip().lower()), None)
        if not sheet:
            return None, None

        raw = pd.read_excel(file_obj, sheet_name=sheet, header=G2B_HEADER_ROW)
        if raw.shape[1] <= G2B_COL_CESS:
            return None, None

        df = pd.DataFrame({
            'GSTIN'        : raw.iloc[:, G2B_COL_GSTIN].apply(_gstin),
            'Trade Name'   : raw.iloc[:, G2B_COL_TRADNM].astype(str).str.strip(),
            'Note Number'  : raw.iloc[:, G2B_COL_NOTENO].astype(str).str.strip(),
            'Note Type'    : raw.iloc[:, G2B_COL_NOTYPE].apply(_type2b),
            'Note Date'    : raw.iloc[:, G2B_COL_DATE].apply(_date),
            'Taxable Value': raw.iloc[:, G2B_COL_TAXVAL].apply(_f),
            'IGST'         : raw.iloc[:, G2B_COL_IGST].apply(_f),
            'CGST'         : raw.iloc[:, G2B_COL_CGST].apply(_f),
            'SGST'         : raw.iloc[:, G2B_COL_SGST].apply(_f),
            'Cess'         : raw.iloc[:, G2B_COL_CESS].apply(_f),
        })
        orig = df[['GSTIN', 'Note Number']].rename(columns={'Note Number': 'Orig_Note'})
        df   = df[df['GSTIN'].str.len() == 15].reset_index(drop=True)
        return df, orig
    except Exception as e:
        st.warning(f'[CDNRA Reader] {e}')
        return None, None


def _apply_cdnra(df_gst, df_revised, orig_refs):
    del_n = add_n = 0
    if df_revised is None or orig_refs is None:
        return df_gst, 0, 0
    if not orig_refs.empty:
        kill = set(zip(orig_refs['GSTIN'], orig_refs['Orig_Note']))
        mask = df_gst.apply(
            lambda r: (_gstin(r['GSTIN']), str(r['Note Number']).strip()) in kill, axis=1
        )
        del_n = int(mask.sum())
        df_gst = df_gst[~mask].copy()
    if not df_revised.empty:
        df_gst = pd.concat([df_gst, df_revised], ignore_index=True)
        add_n  = len(df_revised)
    return df_gst, del_n, add_n


def _trade_map(df_gst):
    out = {}
    if df_gst is None or df_gst.empty:
        return out
    for _, r in df_gst.iterrows():
        g = _gstin(r.get('GSTIN', ''))
        n = str(r.get('Trade Name', '')).strip()
        if g and n and n.lower() not in ('', 'nan', 'none'):
            out[g] = n
    return out


# ────────────────────────────────────────────────────────────
# 6-STEP CASCADE ENGINE
# ────────────────────────────────────────────────────────────

def run_cdnr_reconciliation(df_books_raw, df_gst_raw, tolerance=5.0):
    """
    Mirrors core_engine.run_reconciliation step-for-step:

    Step 1 – Exact:          GSTIN + Date_Str + Round_Taxable  (value tol)
    Step 2 – Date Mismatch:  GSTIN + Round_Taxable             (value tol)
    Step 3 – Taxable Mis.:   GSTIN + Date_Str                  (any value)
    Step 4 – AI Mismatch:    GSTIN + Note_Type + Round_Tax     (value tol)
    Step 5 – Suggestion:     Note_Type + Round_Taxable          (cross-GSTIN)
    Step 6 – Group Match:    GSTIN total value ≈ same

    Post:  flag CDNR Matched (Tax Error) when Taxable ok but IGST/CGST/SGST diff > ₹1
    """
    if df_books_raw is None or df_books_raw.empty:
        return pd.DataFrame()

    tmap = _trade_map(df_gst_raw)

    # ── Clean both sides ────────────────────────────────────
    df_b = _clean(df_books_raw.copy())
    df_b['Trade Name'] = df_b['GSTIN'].map(tmap).fillna('Unknown')

    if df_gst_raw is None or df_gst_raw.empty:
        df_b = df_b.add_suffix('_BOOKS')
        df_b['Recon_Status_CDNR'] = 'CDNR Not in GSTR-2B'
        df_b['Match_Logic']       = 'Unmatched'
        return _post_process(df_b, tmap)

    df_g = _clean(df_gst_raw.copy())
    df_g['Trade Name'] = df_g['GSTIN'].map(tmap).fillna(df_g.get('Trade Name', 'Unknown'))

    # ── Unique IDs — ONE column per side only ──────────────
    df_b['Unique_ID'] = ['B_' + str(i) for i in range(len(df_b))]
    df_g['Unique_ID'] = ['G_' + str(i) for i in range(len(df_g))]
    # Do NOT add Unique_ID_BOOKS / Unique_ID_GST here —
    # the merge suffixes will create them automatically from 'Unique_ID'

    prog    = st.progress(0, text='CDNR Step 1: Exact Match…')
    results = []

    # ── STEP 1: Exact ───────────────────────────────────────
    df_b['K1'] = df_b['GSTIN'] + '_' + df_b['Date_Str'] + '_' + df_b['Round_Taxable'].astype(str)
    df_g['K1'] = df_g['GSTIN'] + '_' + df_g['Date_Str'] + '_' + df_g['Round_Taxable'].astype(str)
    m1, bL, gL = _merge(df_b, df_g, 'K1',
                        'CDNR Matched', 'Exact: GSTIN+Date+Taxable',
                        value_tol=True, tolerance=tolerance, one_to_one=True)
    results.append(m1)

    # ── STEP 2: Date Mismatch ───────────────────────────────
    prog.progress(20, text='CDNR Step 2: Date Mismatch…')
    bL['K2'] = bL['GSTIN'] + '_' + bL['Round_Taxable'].astype(str)
    gL['K2'] = gL['GSTIN'] + '_' + gL['Round_Taxable'].astype(str)
    m2, bL, gL = _merge(bL, gL, 'K2',
                        'CDNR AI Matched (Date Mismatch)', 'Date Mismatch',
                        value_tol=True, tolerance=tolerance, one_to_one=True)
    results.append(m2)

    # ── STEP 3: Taxable Mismatch (same GSTIN+Date) ─────────
    prog.progress(40, text='CDNR Step 3: Taxable Mismatch…')
    bL['K3'] = bL['GSTIN'] + '_' + bL['Date_Str']
    gL['K3'] = gL['GSTIN'] + '_' + gL['Date_Str']
    m3, bL, gL = _merge(bL, gL, 'K3',
                        'CDNR AI Matched (Taxable Mismatch)', 'Taxable Mismatch',
                        value_tol=False, one_to_one=True)
    results.append(m3)

    # ── STEP 4: AI Mismatch (GSTIN + Type + Value) ─────────
    prog.progress(58, text='CDNR Step 4: AI Mismatch…')
    bL['K4'] = bL['GSTIN'] + '_' + bL['Note Type'].astype(str) + '_' + bL['Round_Taxable'].astype(str)
    gL['K4'] = gL['GSTIN'] + '_' + gL['Note Type'].astype(str) + '_' + gL['Round_Taxable'].astype(str)
    m4, bL, gL = _merge(bL, gL, 'K4',
                        'CDNR AI Matched (Mismatch)', 'Type+Value Match',
                        value_tol=True, tolerance=tolerance, one_to_one=True)
    results.append(m4)

    # ── STEP 5: Suggestion (cross-GSTIN, Type+Value) ───────
    prog.progress(73, text='CDNR Step 5: Suggestions…')
    bL['K5'] = bL['Note Type'].astype(str) + '_' + bL['Round_Taxable'].astype(str)
    gL['K5'] = gL['Note Type'].astype(str) + '_' + gL['Round_Taxable'].astype(str)
    m5, bL, gL = _merge(bL, gL, 'K5',
                        'CDNR Suggestion', 'Cross-GSTIN Type+Value',
                        value_tol=True, tolerance=tolerance, one_to_one=True)
    results.append(m5)

    # ── STEP 6: Group Match ─────────────────────────────────
    prog.progress(86, text='CDNR Step 6: Group Match…')
    b_sums = bL.groupby('GSTIN')['Taxable Value'].sum()
    g_sums = gL.groupby('GSTIN')['Taxable Value'].sum()
    common = b_sums.index.intersection(g_sums.index)
    grp_gstins = [g for g in common if abs(b_sums[g] - g_sums[g]) <= tolerance]

    if grp_gstins:
        bG = bL[bL['GSTIN'].isin(grp_gstins)].copy().add_suffix('_BOOKS')
        gG = gL[gL['GSTIN'].isin(grp_gstins)].copy().add_suffix('_GST')
        for df_side in (bG, gG):
            df_side['Recon_Status_CDNR'] = 'CDNR Suggestion (Group Match)'
            df_side['Match_Logic']       = 'Total Value Matches'
        results.extend([bG, gG])
        bL = bL[~bL['GSTIN'].isin(grp_gstins)]
        gL = gL[~gL['GSTIN'].isin(grp_gstins)]

    # ── Leftovers ───────────────────────────────────────────
    prog.progress(94, text='CDNR Finalizing…')
    if not bL.empty:
        bU = bL.add_suffix('_BOOKS')
        bU['Recon_Status_CDNR'] = 'CDNR Not in GSTR-2B'
        bU['Match_Logic']       = 'Unmatched'
        results.append(bU)
    if not gL.empty:
        gU = gL.add_suffix('_GST')
        gU['Recon_Status_CDNR'] = 'CDNR Not in Books'
        gU['Match_Logic']       = 'Unmatched'
        results.append(gU)

    final = pd.concat([r for r in results if not r.empty], ignore_index=True)
    final = _post_process(final, tmap)
    prog.progress(100, text='CDNR Done ✓')
    return final


# ────────────────────────────────────────────────────────────
# POST-PROCESSING  (mirrors core_engine post-processing block)
# ────────────────────────────────────────────────────────────

def _get(df, col, default=0):
    return df[col] if col in df.columns else pd.Series(default, index=df.index)

def _post_process(df: pd.DataFrame, tmap: dict) -> pd.DataFrame:
    if df.empty:
        return df

    # ── Tax Error flag (identical logic to B2B engine) ─────
    matched_mask    = df['Recon_Status_CDNR'].str.contains(r'CDNR Matched$', regex=True, na=False)
    taxable_ok_mask = abs(_get(df, 'Taxable Value_BOOKS').fillna(0) -
                          _get(df, 'Taxable Value_GST').fillna(0)) < 1.0
    tax_diff_mask   = (
        (abs(_get(df, 'IGST_BOOKS').fillna(0) - _get(df, 'IGST_GST').fillna(0)) > 1.0) |
        (abs(_get(df, 'CGST_BOOKS').fillna(0) - _get(df, 'CGST_GST').fillna(0)) > 1.0) |
        (abs(_get(df, 'SGST_BOOKS').fillna(0) - _get(df, 'SGST_GST').fillna(0)) > 1.0)
    )
    df.loc[matched_mask & taxable_ok_mask & tax_diff_mask, 'Recon_Status_CDNR'] = 'CDNR Matched (Tax Error)'

    # ── Coalesce GSTIN + Name ───────────────────────────────
    df['GSTIN'] = _get(df, 'GSTIN_BOOKS', '').replace('', np.nan).fillna(
                  _get(df, 'GSTIN_GST',   ''))

    name_b = _get(df, 'Trade Name_BOOKS', '').astype(str).replace({'': np.nan, 'nan': np.nan, 'Unknown': np.nan})
    name_g = _get(df, 'Trade Name_GST',   '').astype(str).replace({'': np.nan, 'nan': np.nan, 'Unknown': np.nan})
    df['Name of Party'] = name_b.fillna(name_g).fillna(df['GSTIN'].map(tmap)).fillna('Unknown')

    # ── Diff columns (mirrors report_gen compute) ───────────
    df['Diff_Taxable'] = (_get(df,'Taxable Value_BOOKS').fillna(0) - _get(df,'Taxable Value_GST').fillna(0)).round(2)
    df['Diff_IGST']    = (_get(df,'IGST_BOOKS').fillna(0) - _get(df,'IGST_GST').fillna(0)).round(2)
    df['Diff_CGST']    = (_get(df,'CGST_BOOKS').fillna(0) - _get(df,'CGST_GST').fillna(0)).round(2)
    df['Diff_SGST']    = (_get(df,'SGST_BOOKS').fillna(0) - _get(df,'SGST_GST').fillna(0)).round(2)

    # ── ITC Impact ──────────────────────────────────────────
    def _itc(row):
        val   = row.get('Taxable Value_BOOKS') or row.get('Taxable Value_GST') or 0
        dtype = str(row.get('Doc Type_BOOKS', '')).strip().upper()
        gtype = str(row.get('Note Type_GST',  '')).strip().lower()
        # D in Books = Credit Note received by buyer → reduces ITC
        return -abs(val) if dtype == 'D' or 'credit' in gtype else abs(val)

    df['ITC_Impact'] = df.apply(_itc, axis=1).round(2)

    # Final_Taxable for summary calcs (same pattern as B2B)
    df['Final_Taxable'] = _get(df,'Taxable Value_BOOKS').fillna(_get(df,'Taxable Value_GST')).fillna(0)

    # ── Drop noise columns ──────────────────────────────────
    _drop = ['K1','K2','K3','K4','K5','_dd','_diff_tax','_merge',
             'Round_Taxable_BOOKS','Round_Taxable_GST',
             'Date_Str_BOOKS','Date_Str_GST',
             'Note Type_BOOKS','Unique_ID_BOOKS','Unique_ID_GST','Unique_ID']
    df.drop(columns=[c for c in _drop if c in df.columns], inplace=True, errors='ignore')
    return df


# ────────────────────────────────────────────────────────────
# SUMMARY BUILDER
# ────────────────────────────────────────────────────────────

def _build_summary(df, df_b, df_g, del_n, add_n):
    if df is None or df.empty:
        return {}
    s = df['Recon_Status_CDNR']
    return {
        'total_books'        : len(df_b) if df_b is not None else 0,
        'total_gst'          : len(df_g) if df_g is not None else 0,
        'matched_count'      : s.str.contains(r'CDNR Matched$',       regex=True, na=False).sum(),
        'tax_error_count'    : (s == 'CDNR Matched (Tax Error)').sum(),
        'mismatch_count'     : s.str.contains('Mismatch',             na=False).sum(),
        'ai_matched_count'   : s.str.contains('AI Matched',           na=False).sum(),
        'not_in_2b_count'    : (s == 'CDNR Not in GSTR-2B').sum(),
        'not_in_books_count' : (s == 'CDNR Not in Books').sum(),
        'net_itc_impact'     : df.get('ITC_Impact', pd.Series(dtype=float)).sum(),
        'not_in_2b_value'    : df.loc[s == 'CDNR Not in GSTR-2B',
                                      'Taxable Value_BOOKS'].fillna(0).sum()
                               if 'Taxable Value_BOOKS' in df.columns else 0,
        'not_in_books_value' : df.loc[s == 'CDNR Not in Books',
                                      'Taxable Value_GST'].fillna(0).sum()
                               if 'Taxable Value_GST' in df.columns else 0,
        'amendments_deleted' : del_n,
        'amendments_added'   : add_n,
    }


# ────────────────────────────────────────────────────────────
# PUBLIC ORCHESTRATOR  (called from app.py Tab 6)
# ────────────────────────────────────────────────────────────

def process_cdnr_reconciliation(file_books, file_gst, tolerance=5.0, smart_mode=False):
    """
    Full pipeline:
      1. Read Books CDNR (hardcoded indices, header=3)
      2. Read GSTR-2B CDNR (hardcoded indices, header=5)
      3. CDNRA amendments — SKIPPED for now (to be added later)
      4. Run 6-step cascade engine
      5. Return (result_df, summary_dict)
    """
    df_b = read_books_cdnr(file_books)
    df_g = read_raw_cdnr_2b(file_gst)

    # CDNRA disabled — will be enabled in a future release
    del_n = add_n = 0

    result  = run_cdnr_reconciliation(df_b, df_g, tolerance)
    summary = _build_summary(result, df_b, df_g, del_n, add_n)
    return result, summary
