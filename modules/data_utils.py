# modules/data_utils.py
import pandas as pd
import re
import streamlit as st

def standardize_invoice_numbers(df, col_name):
    """
    Standardizes invoice number column to ensure text matching.
    Handles '2364' (int) vs '2364' (text) vs '2364.0' (float from Excel).
    """
    if col_name in df.columns:
        # 1. Force to String (Fixes Green Triangle / Number mismatch)
        df[col_name] = df[col_name].astype(str)
        # 2. Remove decimals if they exist (e.g. "2364.0" -> "2364")
        df[col_name] = df[col_name].str.replace(r'\.0$', '', regex=True)
        # 3. Strip spaces
        df[col_name] = df[col_name].str.strip()
    return df

def normalize_invoice_number(inv_num):
    if pd.isna(inv_num): return ""
    clean = re.sub(r'[^0-9]', '', str(inv_num)) 
    return clean.lstrip('0')

def clean_currency(x):
    try:
        if isinstance(x, str): x = x.replace(',', '')
        return float(x)
    except: return 0.0

def normalize_pos(pos):
    if pd.isna(pos): return ""
    return re.sub(r'[^A-Z]', '', str(pos).upper())

def get_financial_year(date_obj):
    if pd.isna(date_obj): return 0
    try:
        return date_obj.year if date_obj.month >= 4 else date_obj.year - 1
    except: return 0

# --- UPDATED: STRICT SHEET FINDER WITH EXCLUSION LOGIC ---
def find_sheet_by_keyword(xls, keywords, exclude_keywords=None):
    """
    Finds a sheet matching keywords but STRICTLY SKIPS those matching exclude_keywords.
    This prevents 'B2B-CDNR' from being matched when looking for 'B2B'.
    """
    if exclude_keywords is None: exclude_keywords = []
    
    # Normalize keywords for case-insensitive matching
    keywords = [k.lower() for k in keywords]
    exclude_keywords = [e.lower() for e in exclude_keywords]
    
    found_sheet = None
    
    for sheet in xls.sheet_names:
        sheet_lower = sheet.lower()
        
        # 1. Check Exclusion: If sheet name contains ANY excluded keyword, SKIP IT.
        if any(exc in sheet_lower for exc in exclude_keywords):
            continue
            
        # 2. Check Inclusion: If sheet name contains ANY target keyword, pick it.
        if any(k in sheet_lower for k in keywords):
            # Prioritize exact "B2B" if found (best match)
            if sheet_lower == "b2b":
                return sheet
            found_sheet = sheet # Keep looking for a better match, but save this one
            
    # Return the best match found, or the first sheet as a fallback (risky but standard)
    return found_sheet if found_sheet else xls.sheet_names[0]

def extract_meta_from_readme(file):
    try:
        xls = pd.ExcelFile(file)
        if 'Read me' in xls.sheet_names:
            df = pd.read_excel(file, sheet_name='Read me', header=None)
            
            def get_val(r, c):
                try:
                    val = str(df.iloc[r, c]).strip()
                    if val == 'nan': return ""
                    return val
                except: return ""

            fy_raw = get_val(3, 2)      # C4
            period_raw = get_val(4, 2)  # C5
            gstin = get_val(5, 2)       # C6
            name = get_val(7, 2)        # C8
            
            if "Financial Year" in fy_raw: fy = fy_raw.replace("Financial Year", "").strip()
            else: fy = fy_raw
            
            if "Tax Period" in period_raw: period = period_raw.replace("Tax Period", "").strip()
            else: period = period_raw

            return fy, period, gstin, name
            
    except Exception as e:
        print(f"Meta Extract Error: {e}")
    
    return None, None, None, None

@st.cache_data
def load_data_preview(file):
    try:
        xls = pd.ExcelFile(file)
        
        # --- KEY FIX: EXCLUDE 'CDNR' TO PREVENT FALSE POSITIVE ---
        # This tells the loader: Find 'B2B' but DO NOT touch anything with 'CDNR'
        sheet_name = find_sheet_by_keyword(
            xls, 
            ['b2b', 'sales', 'purchase'], 
            exclude_keywords=['cdnr', 'credit', 'debit', 'cdnra'] 
        )
        # ---------------------------------------------------------
        
        df_scan = pd.read_excel(file, sheet_name=sheet_name, header=None, nrows=25)
        header_idx = 0
        found = False
        for idx, row in df_scan.iterrows():
            row_str = " ".join([str(x).lower() for x in row.values])
            if 'invoice number' in row_str or 'invoice no' in row_str:
                header_idx = idx
                found = True
                break
        if not found:
             for idx, row in df_scan.iterrows():
                row_str = " ".join([str(x).lower() for x in row.values])
                if 'gstin' in row_str and 'date' in row_str:
                    header_idx = idx
                    break
        file.seek(0)
        df = pd.read_excel(file, sheet_name=sheet_name, header=header_idx)
        if header_idx > 0:
            row_above = df_scan.iloc[header_idx - 1]
            new_columns = []
            for i, col in enumerate(df.columns):
                if "Unnamed" in str(col) or pd.isna(col) or str(col).strip() == "":
                    val_above = row_above[i]
                    if pd.notna(val_above) and str(val_above).strip() != "":
                        new_columns.append(str(val_above).strip())
                    else:
                        new_columns.append(col)
                else:
                    new_columns.append(col)
            df.columns = new_columns
        rename_map = {}
        for c in df.columns:
            if "GSTIN" in str(c) and "supplier" in str(c).lower(): rename_map[c] = "GSTIN"
            if "Trade" in str(c) and "Legal" in str(c): rename_map[c] = "Name of Party"
        df.rename(columns=rename_map, inplace=True)
        return df
    except Exception as e:
        st.error(f"Error loading file: {e}")
        return None

def find_best_match(col_name, candidates, fixed_map=None):
    if fixed_map and col_name in fixed_map:
        target = fixed_map[col_name]
        if target in candidates: return target
        if target == "<No Column / Blank>": return target
    col_lower = col_name.lower()
    for c in candidates:
        if str(c).strip().lower() == col_lower: return c
    for c in candidates:
        if col_lower in str(c).strip().lower(): return c
    return None