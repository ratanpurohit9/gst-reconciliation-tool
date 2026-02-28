# modules/pre_processor.py
import pandas as pd
import streamlit as st
import re

def normalize_text(series):
    """
    Standardizes text for matching (Removes spaces, .0, makes uppercase).
    """
    return series.astype(str).str.strip().str.upper().str.replace(r'\.0$', '', regex=True)

def get_col_name(df, possible_names):
    """
    Finds the actual column name in a dataframe from a list of possibilities.
    Case-insensitive search.
    """
    existing_cols = [str(c).strip().lower() for c in df.columns]
    for candidate in possible_names:
        clean_candidate = candidate.strip().lower()
        # Exact match
        if clean_candidate in existing_cols:
            return df.columns[existing_cols.index(clean_candidate)]
        # Partial match
        for i, ex_col in enumerate(existing_cols):
            if clean_candidate in ex_col:
                return df.columns[i]
    return None

def smart_read_b2ba(file_obj):
    """
    Reads B2BA sheet using STRICT POSITIONAL MAPPING based on user layout.
    Original: Col A (Inv), Col B (Date), Col C (GSTIN)
    Revised:  Col E (Inv), Col G (Date), Col L (Taxable), M, N, O (Taxes)
    """
    try:
        xls = pd.ExcelFile(file_obj)
        # Find sheet name containing 'b2ba'
        sheet_name = next((s for s in xls.sheet_names if 'b2ba' in s.lower()), None)
        if not sheet_name: return None, "No B2BA sheet found."

        # 1. Find Header Row (Anchor: "Original Details")
        df_scan = pd.read_excel(file_obj, sheet_name=sheet_name, header=None, nrows=20)
        anchor_idx = -1
        for idx, row in df_scan.iterrows():
            row_str = " ".join([str(x) for x in row.values])
            if "Original Details" in row_str:
                anchor_idx = idx
                break
        
        if anchor_idx == -1: return None, "Critical: 'Original Details' header not found."

        # 2. Read Data (Data starts 2 rows below Anchor)
        # Example: Anchor at Row 6 -> Headers at 7 -> Data at 8
        data_start_row = anchor_idx + 2 
        
        # Read without headers so we can access by Index (0, 1, 2...)
        df_raw = pd.read_excel(file_obj, sheet_name=sheet_name, header=None, skiprows=data_start_row)
        
        # 3. Rename Columns manually by Index (A=0, B=1, C=2, E=4...)
        # Verify we have enough columns (At least up to Col O which is index 14)
        if df_raw.shape[1] < 15:
            # If sheet is cut off, we can't map taxes, but let's try mapping what we have
            pass 

        # MAPPING DICTIONARY (Based on your blue text request)
        # A(0): OLD_INV_NO
        # C(2): GSTIN (Shared)
        # E(4): NEW_INV_NO
        # G(6): NEW_DATE
        # L(11): NEW_TAXABLE
        # M(12): NEW_IGST
        # N(13): NEW_CGST
        # O(14): NEW_SGST
        
        rename_map = {
            0: 'OLD_INV_NO',
            2: 'GSTIN',
            4: 'NEW_INV_NO',
            6: 'NEW_DATE',
            11: 'NEW_TAXABLE',
            12: 'NEW_IGST',
            13: 'NEW_CGST',
            14: 'NEW_SGST'
        }
        
        df_raw.rename(columns=rename_map, inplace=True)

        # 4. Filter empty rows (Must have GSTIN and Old Inv)
        df_raw = df_raw.dropna(subset=['GSTIN', 'OLD_INV_NO'])
        
        # 5. Ensure numeric columns are actually numbers (handle potential header junk)
        num_cols = ['NEW_TAXABLE', 'NEW_IGST', 'NEW_CGST', 'NEW_SGST']
        for c in num_cols:
            if c in df_raw.columns:
                df_raw[c] = pd.to_numeric(df_raw[c], errors='coerce').fillna(0.0)

        # Try to find Name (Trade/Legal name) - usually Col D (Index 3)
        if 3 in df_raw.columns:
            df_raw.rename(columns={3: 'Name of Party'}, inplace=True)
        else:
            df_raw['Name of Party'] = 'Amendment'

        return df_raw, "Success"

    except Exception as e:
        return None, f"Error processing B2BA: {e}"

def process_amendments(df_b2b, df_b2ba):
    """
    Kill & Replace Logic.
    1. Finds target columns in df_b2b dynamically.
    2. Deletes rows matching (GSTIN + OLD_INV_NO).
    3. Maps B2BA columns to B2B columns and Adds them.
    """
    if df_b2ba is None or df_b2ba.empty:
        return df_b2b, 0, 0

    # --- STEP 1: Find the Columns in B2B (Target) ---
    b2b_inv_col = get_col_name(df_b2b, ["Invoice number", "Invoice Number", "Inv No", "Invoice No."])
    b2b_gst_col = get_col_name(df_b2b, ["GSTIN", "GSTIN of supplier"])
    b2b_date_col = get_col_name(df_b2b, ["Invoice Date", "Inv Date", "Date"])
    
    # Value Columns
    b2b_taxable = get_col_name(df_b2b, ["Taxable Value", "Taxable"])
    b2b_igst = get_col_name(df_b2b, ["Integrated Tax", "IGST"])
    b2b_cgst = get_col_name(df_b2b, ["Central Tax", "CGST"])
    b2b_sgst = get_col_name(df_b2b, ["State/UT Tax", "State Tax", "SGST"])

    if not b2b_inv_col or not b2b_gst_col:
        st.error(f"⚠️ Amendment Failed: Could not identify Invoice/GSTIN columns in B2B data. Found: {list(df_b2b.columns)}")
        return df_b2b, 0, 0
    
    # --- STEP 2: Normalize Keys for Matching ---
    df_b2b['Key_GSTIN'] = normalize_text(df_b2b[b2b_gst_col])
    df_b2b['Key_Inv']   = normalize_text(df_b2b[b2b_inv_col])
    df_b2b['Unique_Match_Key'] = df_b2b['Key_GSTIN'] + "_" + df_b2b['Key_Inv']
    
    df_b2ba['Key_GSTIN'] = normalize_text(df_b2ba['GSTIN'])
    df_b2ba['Key_Old_Inv'] = normalize_text(df_b2ba['OLD_INV_NO'])
    kill_list = (df_b2ba['Key_GSTIN'] + "_" + df_b2ba['Key_Old_Inv']).unique().tolist()
    
    # --- STEP 3: DELETE OLD RECORDS ---
    initial_count = len(df_b2b)
    df_clean = df_b2b[~df_b2b['Unique_Match_Key'].isin(kill_list)].copy()
    deleted_count = initial_count - len(df_clean)
    
    # Cleanup temp keys
    df_clean = df_clean.drop(columns=['Key_GSTIN', 'Key_Inv', 'Unique_Match_Key'])

    # --- STEP 4: PREPARE & INJECT NEW RECORDS ---
    df_to_add = df_b2ba.copy()
    
    # MAP B2BA Internal Names -> B2B Actual Names
    final_rename_map = {
        'NEW_INV_NO': b2b_inv_col,
        'GSTIN': b2b_gst_col
    }
    if b2b_date_col: final_rename_map['NEW_DATE'] = b2b_date_col
    if b2b_taxable: final_rename_map['NEW_TAXABLE'] = b2b_taxable
    if b2b_igst: final_rename_map['NEW_IGST'] = b2b_igst
    if b2b_cgst: final_rename_map['NEW_CGST'] = b2b_cgst
    if b2b_sgst: final_rename_map['NEW_SGST'] = b2b_sgst
    
    df_to_add.rename(columns=final_rename_map, inplace=True)
    
    # Ensure all B2B columns exist in the new data
    for col in df_b2b.columns:
        if col in ['Key_GSTIN', 'Key_Inv', 'Unique_Match_Key']: continue 
        
        if col not in df_to_add.columns:
            # Default values
            if 'Value' in str(col) or 'Tax' in str(col):
                df_to_add[col] = 0.0
            else:
                df_to_add[col] = ""
    
    # Select matching columns
    cols_to_keep = [c for c in df_b2b.columns if c not in ['Key_GSTIN', 'Key_Inv', 'Unique_Match_Key']]
    df_to_add = df_to_add[cols_to_keep]
    
    # --- STEP 5: MERGE ---
    df_final = pd.concat([df_clean, df_to_add], ignore_index=True)
    
    return df_final, deleted_count, len(df_to_add)