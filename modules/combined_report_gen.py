# modules/combined_report_gen.py
# Combined B2B + CDNR Reconciliation Excel Report
# Shows Executive Summary covering both, individual summary tabs, and all data sheets.

import io
import numpy as np
import pandas as pd
import xlsxwriter


def _safe_date(series):
    temp = pd.to_datetime(series, dayfirst=True, errors='coerce')
    return temp.fillna(series)


def _money(df_s, col):
    return float(df_s[col].fillna(0).sum()) if col in df_s.columns else 0.0


def _row8(df_s, use_books=True):
    sx = '_BOOKS' if use_books else '_GST'
    tv = _money(df_s, 'Taxable Value' + sx)
    ig = _money(df_s, 'IGST' + sx)
    cg = _money(df_s, 'CGST' + sx)
    sg = _money(df_s, 'SGST' + sx)
    tg = ig + cg + sg
    return [len(df_s), tv, ig, cg, sg, 0.0, tg, tv + tg]


def _vv(val):
    """Safe value — converts NaT/nan/timestamps to safe types for xlsxwriter."""
    if val is None:
        return ''
    if isinstance(val, float) and np.isnan(val):
        return ''
    try:
        import pandas as _pd
        if _pd.isnull(val):
            return ''
    except (TypeError, ValueError):
        pass
    try:
        if hasattr(val, 'strftime'):
            return val.strftime('%d/%m/%Y')
    except Exception:
        return ''
    return val


def _nn(val):
    try:
        return float(val) if val is not None and not (isinstance(val, float) and np.isnan(val)) else 0.0
    except Exception:
        return 0.0


def generate_combined_excel(b2b_df, cdnr_df, company_gstin, company_name, fy, period):
    """
    Generates a single Excel workbook combining B2B + CDNR reconciliation results.

    Sheets:
      1. Executive Summary  — unified B2B + CDNR financial grid
      2. B2B Summary        — individual B2B invoice rows (Books vs Portal)
      3. CDNR Summary       — individual CDNR note rows (Books vs Portal)
      4. Combined Issues    — all non-matched rows from both modules
      5. B2B All Data       — full B2B dataset
      6. CDNR All Data      — full CDNR dataset
    """
    output = io.BytesIO()
    writer = pd.ExcelWriter(output, engine='xlsxwriter', datetime_format='dd/mm/yyyy')
    wb = writer.book

    def _f(**kw):
        return wb.add_format(kw)

    # ── Shared formats ────────────────────────────────────────────────────────
    FMETA   = _f(bold=True)
    FHDR    = _f(bold=True, bg_color='#0D47A1', font_color='white', border=1,
                 align='center', valign='vcenter', font_size=9)
    FBANNER = _f(bold=True, bg_color='#1A237E', font_color='white', border=1,
                 align='center', valign='vcenter', font_size=13)
    FSEC_B  = _f(bold=True, bg_color='#2E7D32', font_color='white', border=1,
                 align='center', valign='vcenter', font_size=10)
    FSEC_G  = _f(bold=True, bg_color='#1565C0', font_color='white', border=1,
                 align='center', valign='vcenter', font_size=10)
    FSEC_D  = _f(bold=True, bg_color='#37474F', font_color='white', border=1,
                 align='center', valign='vcenter', font_size=10)
    FBK_L   = _f(bg_color='#E8F5E9', font_color='#1B5E20', border=1, align='left', valign='vcenter', font_size=9)
    FBK_V   = _f(bg_color='#E8F5E9', font_color='#37474F', border=1, align='right', valign='vcenter', font_size=9, num_format='#,##0.00')
    FBK_TL  = _f(bold=True, bg_color='#C8E6C9', font_color='#1B5E20', border=1, align='left', valign='vcenter', font_size=9)
    FBK_TV  = _f(bold=True, bg_color='#C8E6C9', font_color='#1B5E20', border=1, align='right', valign='vcenter', font_size=9, num_format='#,##0.00')
    FGT_L   = _f(bg_color='#E3F2FD', font_color='#0D47A1', border=1, align='left', valign='vcenter', font_size=9)
    FGT_V   = _f(bg_color='#E3F2FD', font_color='#37474F', border=1, align='right', valign='vcenter', font_size=9, num_format='#,##0.00')
    FGT_NA  = _f(bg_color='#E3F2FD', font_color='#9E9E9E', border=1, align='center', valign='vcenter', font_size=9, italic=True)
    FGT_TL  = _f(bold=True, bg_color='#BBDEFB', font_color='#0D47A1', border=1, align='left', valign='vcenter', font_size=9)
    FGT_TV  = _f(bold=True, bg_color='#BBDEFB', font_color='#0D47A1', border=1, align='right', valign='vcenter', font_size=9, num_format='#,##0.00')
    FDF_L   = _f(bg_color='#FFF9C4', font_color='#37474F', border=1, align='left', valign='vcenter', font_size=9)
    FDF_PL  = _f(bold=True, bg_color='#DCEDC8', font_color='#2E7D32', border=1, align='right', valign='vcenter', font_size=9, num_format='#,##0.00')
    FDF_NG  = _f(bold=True, bg_color='#FFCDD2', font_color='#C62828', border=1, align='right', valign='vcenter', font_size=9, num_format='#,##0.00')
    FDF_ZR  = _f(bold=True, bg_color='#FFF9C4', font_color='#757575', border=1, align='right', valign='vcenter', font_size=9, num_format='#,##0.00')
    FNOTE   = _f(italic=True, font_color='#607D8B', font_size=8, align='left', valign='vcenter', text_wrap=True)
    FTOT    = _f(bold=True, bg_color='#1F3864', font_color='white', border=1, align='right', valign='vcenter', font_size=9, num_format='#,##0.00')
    FTOT_L  = _f(bold=True, bg_color='#1F3864', font_color='white', border=1, align='center', valign='vcenter', font_size=9)

    def dfmt(v):
        return FDF_PL if v > 0.01 else FDF_NG if v < -0.01 else FDF_ZR

    # ── Source totals ─────────────────────────────────────────────────────────
    b2b_bk = _row8(b2b_df[b2b_df['Taxable Value_BOOKS'].notna()] if 'Taxable Value_BOOKS' in b2b_df.columns else b2b_df.iloc[0:0])
    b2b_gt = _row8(b2b_df[b2b_df['Taxable Value_GST'].notna()] if 'Taxable Value_GST' in b2b_df.columns else b2b_df.iloc[0:0], False)

    cdnr_bk = _row8(cdnr_df[cdnr_df['Taxable Value_BOOKS'].notna()] if 'Taxable Value_BOOKS' in cdnr_df.columns else cdnr_df.iloc[0:0])
    cdnr_gt = _row8(cdnr_df[cdnr_df['Taxable Value_GST'].notna()] if 'Taxable Value_GST' in cdnr_df.columns else cdnr_df.iloc[0:0], False)

    total_bk = [b2b_bk[i] + cdnr_bk[i] for i in range(8)]
    total_gt = [b2b_gt[i] + cdnr_gt[i] for i in range(8)]
    diff_b2b = [b2b_gt[i] - b2b_bk[i] for i in range(8)]
    diff_cdn = [cdnr_gt[i] - cdnr_bk[i] for i in range(8)]
    diff_tot = [total_gt[i] - total_bk[i] for i in range(8)]

    # ═════════════════════════════════════════════════════════════════════════
    # SHEET 1 — EXECUTIVE SUMMARY
    # ═════════════════════════════════════════════════════════════════════════
    ws_ex = wb.add_worksheet('Executive Summary')
    ws_ex.set_column(0, 0, 20); ws_ex.set_column(1, 1, 10)
    ws_ex.set_column(2, 2, 20); ws_ex.set_column(3, 8, 16)

    for r in range(4):
        ws_ex.set_row(r, 16)
    ws_ex.write(0, 0, 'GSTIN:',      FMETA); ws_ex.write(0, 1, company_gstin)
    ws_ex.write(1, 0, 'Trade Name:', FMETA); ws_ex.write(1, 1, company_name)
    ws_ex.write(2, 0, 'F.Y.:',       FMETA); ws_ex.write(2, 1, fy)
    ws_ex.write(3, 0, 'Period:',     FMETA); ws_ex.write(3, 1, period)

    ws_ex.set_row(4, 6)
    ws_ex.merge_range(5, 0, 5, 8, '  COMBINED RECONCILIATION  (B2B + CDNR)  —  Executive Summary', FBANNER)
    ws_ex.set_row(5, 28)

    COL_H = ['', '', 'TAXABLE (₹)', 'IGST (₹)', 'CGST (₹)', 'SGST (₹)', 'CESS (₹)', 'TOTAL TAX (₹)', 'TOTAL (₹)']
    ws_ex.set_row(6, 26)
    for ci, h in enumerate(COL_H):
        ws_ex.write(6, ci, h, FHDR)

    # BOOKS section
    ws_ex.set_row(7, 22)
    ws_ex.merge_range(7, 0, 7, 8, '  BOOKS  (Purchase Register)', FSEC_B)
    for row_i, l1, l2, vals in [(8, 'Books', 'B2B', b2b_bk), (9, '', 'CDNR', cdnr_bk)]:
        ws_ex.set_row(row_i, 20)
        ws_ex.write(row_i, 0, l1, FBK_L); ws_ex.write(row_i, 1, l2, FBK_L)
        for ci, v in enumerate(vals[1:], 2):
            ws_ex.write(row_i, ci, v, FBK_V)
    ws_ex.set_row(10, 22)
    ws_ex.write(10, 0, 'TOTAL BOOKS', FBK_TL); ws_ex.write(10, 1, '', FBK_TL)
    for ci, v in enumerate(total_bk[1:], 2):
        ws_ex.write(10, ci, v, FBK_TV)

    # GSTR-2B section
    ws_ex.set_row(11, 6); ws_ex.set_row(12, 22)
    ws_ex.merge_range(12, 0, 12, 8, '  GSTR-2B  (Portal Data)', FSEC_G)
    for row_i, l1, l2, vals, is_na in [
            (13, 'GSTR-2B', 'B2B',  b2b_gt,  False),
            (14, '',        'B2BA', [0]*8,    True),
            (15, '',        'CDNR', cdnr_gt,  False),
            (16, '',        'CDNRA',[0]*8,    True)]:
        ws_ex.set_row(row_i, 20)
        ws_ex.write(row_i, 0, l1, FGT_L); ws_ex.write(row_i, 1, l2, FGT_L)
        for ci, v in enumerate(vals[1:], 2):
            ws_ex.write(row_i, ci, '—' if is_na and v == 0 else v,
                        FGT_NA if is_na and v == 0 else FGT_V)
    ws_ex.set_row(17, 22)
    ws_ex.write(17, 0, 'TOTAL GSTR-2B', FGT_TL); ws_ex.write(17, 1, '', FGT_TL)
    for ci, v in enumerate(total_gt[1:], 2):
        ws_ex.write(17, ci, v, FGT_TV)

    # DIFFERENCE section
    ws_ex.set_row(18, 6); ws_ex.set_row(19, 22)
    ws_ex.merge_range(19, 0, 19, 8, '  DIFFERENCE  (GSTR-2B  −  Books)', FSEC_D)
    for row_i, l1, l2, vals in [
            (20, 'Diff', 'B2B',  diff_b2b),
            (21, 'Diff', 'CDNR', diff_cdn),
            (22, 'TOTAL DIFF', '', diff_tot)]:
        ws_ex.set_row(row_i, 20)
        ws_ex.write(row_i, 0, l1, FDF_L); ws_ex.write(row_i, 1, l2, FDF_L)
        for ci, v in enumerate(vals[1:], 2):
            ws_ex.write(row_i, ci, v, dfmt(v))
    ws_ex.set_row(23, 6); ws_ex.set_row(24, 28)
    ws_ex.merge_range(24, 0, 24, 8,
        '🔴 Red = GSTR-2B < Books (ITC at risk)   '
        '🟢 Green = GSTR-2B > Books (supplier reported more)   '
        '⬜ Yellow = No difference', FNOTE)

    # KPI scorecard on the right
    _FKPI_T = _f(bold=True, bg_color='#E8EAF6', font_color='#1A237E', border=1,
                 align='center', valign='vcenter', font_size=9)
    _FKPI_V = _f(bold=True, bg_color='#F3F4F6', font_color='#111827', border=1,
                 align='right', valign='vcenter', font_size=11, num_format='#,##0')
    _FKPI_G = _f(bold=True, bg_color='#ECFDF5', font_color='#065F46', border=1,
                 align='right', valign='vcenter', font_size=11, num_format='#,##0')
    _FKPI_R = _f(bold=True, bg_color='#FFF1F2', font_color='#9F1239', border=1,
                 align='right', valign='vcenter', font_size=11, num_format='#,##0')

    def _cnt(df, pat, col='Recon_Status'):
        try:    return int(df[df[col].str.contains(pat, na=False)][col].count())
        except: return 0

    b2b_st = b2b_df.get('Recon_Status', pd.Series(dtype=str)) if 'Recon_Status' in b2b_df.columns else pd.Series(dtype=str)
    cdnr_st_col = 'Recon_Status_CDNR' if 'Recon_Status_CDNR' in cdnr_df.columns else 'Recon_Status'

    kpis = [
        ('B2B Matched',          _cnt(b2b_df, r'Matched')),
        ('B2B Not in GSTR-2B',   _cnt(b2b_df, 'Not in GSTR-2B')),
        ('B2B Mismatched',       _cnt(b2b_df, 'Mismatch')),
        ('CDNR Matched',         _cnt(cdnr_df, r'CDNR Matched', cdnr_st_col)),
        ('CDNR Not in GSTR-2B',  _cnt(cdnr_df, 'Not in GSTR-2B', cdnr_st_col)),
        ('CDNR Mismatched',      _cnt(cdnr_df, 'Mismatch', cdnr_st_col)),
    ]
    ws_ex.merge_range(5, 10, 5, 12, 'QUICK STATS', _FKPI_T)
    for ki, (lbl, val) in enumerate(kpis):
        r = 6 + ki
        ws_ex.write(r, 10, lbl, _FKPI_T)
        fmt = _FKPI_G if 'Matched' in lbl else _FKPI_R
        ws_ex.write(r, 11, val, fmt)
    ws_ex.set_column(10, 10, 22); ws_ex.set_column(11, 11, 10)

    # ═════════════════════════════════════════════════════════════════════════
    # SHEET 2 — B2B Individual Records
    # ═════════════════════════════════════════════════════════════════════════
    _write_individual_sheet(wb, writer, b2b_df, 'B2B Summary',
                            company_gstin, company_name, fy, period,
                            id_col='Recon_Status', note_col='Invoice',
                            bk_inv='Invoice Number_BOOKS', bk_date='Invoice Date_BOOKS',
                            gt_inv='Invoice Number_GST',  gt_date='Invoice Date_GST')

    # ═════════════════════════════════════════════════════════════════════════
    # SHEET 3 — CDNR Individual Records
    # ═════════════════════════════════════════════════════════════════════════
    _write_individual_sheet(wb, writer, cdnr_df, 'CDNR Summary',
                            company_gstin, company_name, fy, period,
                            id_col='Recon_Status_CDNR', note_col='Note',
                            bk_inv='Note Number_BOOKS', bk_date='Note Date_BOOKS',
                            gt_inv='Note Number_GST',  gt_date='Note Date_GST')

    # ═════════════════════════════════════════════════════════════════════════
    # SHEET 4 — Combined Issues (all non-Matched rows from both modules)
    # ═════════════════════════════════════════════════════════════════════════
    _write_combined_issues(wb, writer, b2b_df, cdnr_df,
                           company_gstin, company_name, fy, period)

    # ═════════════════════════════════════════════════════════════════════════
    # SHEET 5 — B2B All Data (raw)
    # ═════════════════════════════════════════════════════════════════════════
    b2b_export = b2b_df.copy()
    for dc in ['Invoice Date_BOOKS', 'Invoice Date_GST']:
        if dc in b2b_export.columns:
            b2b_export[dc] = _safe_date(b2b_export[dc])
    b2b_export.to_excel(writer, sheet_name='B2B All Data', index=False)

    # ═════════════════════════════════════════════════════════════════════════
    # SHEET 6 — CDNR All Data (raw)
    # ═════════════════════════════════════════════════════════════════════════
    cdnr_export = cdnr_df.copy()
    for dc in ['Note Date_BOOKS', 'Note Date_GST']:
        if dc in cdnr_export.columns:
            cdnr_export[dc] = _safe_date(cdnr_export[dc])
    cdnr_export.to_excel(writer, sheet_name='CDNR All Data', index=False)

    writer.close()
    return output.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _write_individual_sheet(wb, writer, df, sheet_name,
                             gstin, name, fy, period,
                             id_col, note_col,
                             bk_inv, bk_date, gt_inv, gt_date):
    """Write a side-by-side Books vs Portal individual record sheet."""
    ws = wb.add_worksheet(sheet_name)
    def _f(**kw): return wb.add_format(kw)

    FBANNER = _f(bold=True, bg_color='#1A237E', font_color='white', border=1,
                 align='center', valign='vcenter', font_size=12)
    FMETA   = _f(bold=True)
    FGRP_BK = _f(bold=True, bg_color='#ED7D31', font_color='white', border=1, align='center', valign='vcenter', font_size=9)
    FGRP_GT = _f(bold=True, bg_color='#70AD47', font_color='white', border=1, align='center', valign='vcenter', font_size=9)
    FGRP_DF = _f(bold=True, bg_color='#9E9E9E', font_color='white', border=1, align='center', valign='vcenter', font_size=9)
    FGRP_ST = _f(bold=True, bg_color='#4472C4', font_color='white', border=1, align='center', valign='vcenter', font_size=9)
    FHDR    = _f(bold=True, bg_color='#4472C4', font_color='white', border=1, align='center', valign='vcenter', font_size=8, text_wrap=True)
    FIDX    = _f(bg_color='#F5F5F5', font_color='#9E9E9E', border=1, align='center', valign='vcenter', font_size=8)
    FTOT    = _f(bold=True, bg_color='#1F3864', font_color='white', border=1, align='right', valign='vcenter', font_size=9, num_format='#,##0.00')
    FTOT_L  = _f(bold=True, bg_color='#1F3864', font_color='white', border=1, align='center', valign='vcenter', font_size=9)

    _STATUS_COLORS = {
        'Not in GSTR-2B': ('#FFF2F2', '#C00000'),
        'Not in Books':    ('#FFFBEA', '#B8860B'),
        'Mismatch':        ('#FFF0F0', '#C00000'),
        'AI Matched':      ('#EBF3FB', '#2E75B6'),
        'Suggestion':      ('#EFF4FF', '#1D4ED8'),
        'Matched':         ('#F0FFF4', '#1E6B3C'),
    }

    def _rf(status, num=False, bold=False):
        bg, fc = '#FFFFFF', '#37474F'
        for k, (b, f) in _STATUS_COLORS.items():
            if k in str(status):
                bg, fc = b, f
                break
        kw = dict(bg_color=bg, font_color=fc, border=1, valign='vcenter', font_size=9)
        if bold: kw['bold'] = True
        kw['align'] = 'right' if num else 'left'
        if num: kw['num_format'] = '#,##0.00'
        return _f(**kw)

    ws.write(0, 0, 'GSTIN:',      FMETA); ws.write(0, 1, gstin)
    ws.write(1, 0, 'Trade Name:', FMETA); ws.write(1, 1, name)
    ws.write(2, 0, 'F.Y.:',       FMETA); ws.write(2, 1, fy)
    ws.write(3, 0, 'Period:',     FMETA); ws.write(3, 1, period)

    ws.set_row(4, 6)
    ws.merge_range(5, 0, 5, 17, f'  {sheet_name}  —  Individual Record View', FBANNER)
    ws.set_row(5, 26)
    ws.set_row(7, 6)
    ws.set_row(8, 18)
    ws.write(8, 0, '#', FHDR)
    ws.merge_range(8, 1, 8, 2, 'PARTY', FGRP_ST)
    ws.merge_range(8, 3, 8, 7, f'BOOKS  ({note_col})', FGRP_BK)
    ws.merge_range(8, 8, 8, 12, 'GSTR-2B  (Portal)', FGRP_GT)
    ws.merge_range(8, 13, 8, 14, 'DIFFERENCE', FGRP_DF)
    ws.write(8, 15, 'STATUS', FGRP_ST)
    ws.write(8, 16, 'CONFIDENCE %', FGRP_ST)

    hdrs = ['#', 'Party Name', 'GSTIN',
            f'{note_col} No (Books)', 'Date (Books)', 'Taxable (B)', 'IGST (B)', 'CGST (B)', 'SGST (B)',
            f'{note_col} No (Portal)', 'Date (Portal)', 'Taxable (P)', 'IGST (P)', 'CGST (P)', 'SGST (P)',
            'Diff Taxable', 'Diff GST', 'Status', 'Confidence %']
    ws.set_row(9, 18)
    for ci, h in enumerate(hdrs):
        ws.write(9, ci, h, FHDR)

    df_sorted = df.copy()
    if id_col in df_sorted.columns:
        _priority = {'Not in GSTR-2B': 1, 'Not in Books': 2, 'Mismatch': 3,
                     'AI Matched': 4, 'Suggestion': 5, 'Matched': 6}
        def _sp(s):
            for k, v in _priority.items():
                if k in str(s): return v
            return 7
        df_sorted['_p'] = df_sorted[id_col].apply(_sp)
        df_sorted = df_sorted.sort_values(['_p', 'Name of Party']).reset_index(drop=True)

    ws.freeze_panes(10, 3)
    data_start = 10

    for ri, row in df_sorted.iterrows():
        er = data_start + ri
        ws.set_row(er, 16)
        status = str(row.get(id_col, ''))
        confidence = _nn(row.get('Match_Confidence', None))
        ft = _rf(status)
        fn = _rf(status, num=True)
        fi = FIDX

        b_tax  = _nn(row.get('Taxable Value_BOOKS')); b_igst = _nn(row.get('IGST_BOOKS'))
        b_cgst = _nn(row.get('CGST_BOOKS'));           b_sgst = _nn(row.get('SGST_BOOKS'))
        g_tax  = _nn(row.get('Taxable Value_GST'));    g_igst = _nn(row.get('IGST_GST'))
        g_cgst = _nn(row.get('CGST_GST'));             g_sgst = _nn(row.get('SGST_GST'))
        d_tax  = b_tax - g_tax
        d_gst  = (b_igst + b_cgst + b_sgst) - (g_igst + g_cgst + g_sgst)

        gstin_val = _vv(row.get('GSTIN', row.get('GSTIN_BOOKS', '')))

        ws.write(er, 0,  ri + 1,          fi)
        ws.write(er, 1,  _vv(row.get('Name of Party', '')), ft)
        ws.write(er, 2,  gstin_val,        ft)
        ws.write(er, 3,  _vv(row.get(bk_inv, '')),  ft)
        ws.write(er, 4,  _vv(row.get(bk_date, '')), ft)
        ws.write(er, 5,  b_tax,  fn); ws.write(er, 6,  b_igst, fn)
        ws.write(er, 7,  b_cgst, fn); ws.write(er, 8,  b_sgst, fn)
        ws.write(er, 9,  _vv(row.get(gt_inv, '')),  ft)
        ws.write(er, 10, _vv(row.get(gt_date, '')), ft)
        ws.write(er, 11, g_tax,  fn); ws.write(er, 12, g_igst, fn)
        ws.write(er, 13, g_cgst, fn); ws.write(er, 14, g_sgst, fn)

        def _df2(v):
            bg, fc = '#FFFFFF', '#37474F'
            for k, (b, fcc) in _STATUS_COLORS.items():
                if k in status: bg, fc = b, fcc; break
            kw = dict(bg_color=bg, font_color='#C00000' if v > 0.5 else '#2E7D32' if v < -0.5 else '#757575',
                      border=1, align='right', valign='vcenter', font_size=9, num_format='#,##0.00', bold=abs(v) > 0.5)
            return _f(**kw)

        ws.write(er, 15, d_tax, _df2(d_tax))
        ws.write(er, 16, d_gst, _df2(d_gst))
        ws.write(er, 17, status, _rf(status, bold=True))

        # Confidence cell — colour coded
        if confidence > 0:
            conf_bg = '#F0FDF4' if confidence >= 90 else '#FFFBEB' if confidence >= 75 else '#FFF1F2'
            conf_fc = '#166534' if confidence >= 90 else '#92400E' if confidence >= 75 else '#9F1239'
            ws.write(er, 18, confidence, _f(bg_color=conf_bg, font_color=conf_fc, border=1,
                                            align='center', valign='vcenter', font_size=9,
                                            bold=True, num_format='0.0'))
        else:
            ws.write(er, 18, '—', _f(bg_color='#F5F5F5', font_color='#BDBDBD', border=1,
                                      align='center', valign='vcenter', font_size=9, italic=True))

    total_rows = len(df_sorted)
    tot_r = data_start + total_rows
    ws.merge_range(tot_r, 0, tot_r, 4, 'TOTALS', FTOT_L)
    def _cs(c): return float(df[c].fillna(0).sum()) if c in df.columns else 0.0
    for ci, col in enumerate(['Taxable Value_BOOKS', 'IGST_BOOKS', 'CGST_BOOKS', 'SGST_BOOKS'], 5):
        ws.write(tot_r, ci, _cs(col), FTOT)
    ws.write(tot_r, 9, '', FTOT_L); ws.write(tot_r, 10, '', FTOT_L)
    for ci, col in enumerate(['Taxable Value_GST', 'IGST_GST', 'CGST_GST', 'SGST_GST'], 11):
        ws.write(tot_r, ci, _cs(col), FTOT)
    ws.write(tot_r, 15, _cs('Taxable Value_BOOKS') - _cs('Taxable Value_GST'), FTOT)
    gst_diff = (_cs('IGST_BOOKS')+_cs('CGST_BOOKS')+_cs('SGST_BOOKS')) - (_cs('IGST_GST')+_cs('CGST_GST')+_cs('SGST_GST'))
    ws.write(tot_r, 16, gst_diff, FTOT)
    ws.write(tot_r, 17, f'{total_rows} records', FTOT_L)
    ws.write(tot_r, 18, '', FTOT_L)
    ws.set_row(tot_r, 20)

    # Column widths
    ws.set_column(0, 0, 5);  ws.set_column(1, 1, 24); ws.set_column(2, 2, 18)
    ws.set_column(3, 3, 16); ws.set_column(4, 4, 12); ws.set_column(5, 8, 13)
    ws.set_column(9, 9, 16); ws.set_column(10, 10, 12); ws.set_column(11, 14, 13)
    ws.set_column(15, 16, 14); ws.set_column(17, 17, 26); ws.set_column(18, 18, 12)


def _write_combined_issues(wb, writer, b2b_df, cdnr_df, gstin, name, fy, period):
    """Combined issues sheet — only non-matched records from both modules."""
    ws = wb.add_worksheet('Combined Issues')
    def _f(**kw): return wb.add_format(kw)

    FBANNER = _f(bold=True, bg_color='#7B1FA2', font_color='white', border=1,
                 align='center', valign='vcenter', font_size=12)
    FMETA   = _f(bold=True)
    FHDR    = _f(bold=True, bg_color='#1B2035', font_color='white', border=1,
                 align='center', valign='vcenter', font_size=8, text_wrap=True)
    FMOD    = _f(bold=True, bg_color='#E8EAF6', font_color='#1A237E', border=1,
                 align='center', valign='vcenter', font_size=9)
    FIDX    = _f(bg_color='#F5F5F5', font_color='#9E9E9E', border=1, align='center', valign='vcenter', font_size=8)

    _STATUS_COLORS = {
        'Not in GSTR-2B': ('#FFF2F2', '#C00000'),
        'Not in Books':    ('#FFFBEA', '#B8860B'),
        'Mismatch':        ('#FFF0F0', '#C00000'),
        'AI Matched':      ('#EBF3FB', '#2E75B6'),
        'Suggestion':      ('#EFF4FF', '#1D4ED8'),
        'Tax Error':       ('#FFFBEA', '#B8860B'),
    }
    def _rf(status, num=False, bold=False):
        bg, fc = '#FFFDE7', '#37474F'
        for k, (b, fcc) in _STATUS_COLORS.items():
            if k in str(status): bg, fc = b, fcc; break
        kw = dict(bg_color=bg, font_color=fc, border=1, valign='vcenter', font_size=9, bold=bold)
        kw['align'] = 'right' if num else 'left'
        if num: kw['num_format'] = '#,##0.00'
        return _f(**kw)

    ws.write(0, 0, 'GSTIN:',      FMETA); ws.write(0, 1, gstin)
    ws.write(1, 0, 'Trade Name:', FMETA); ws.write(1, 1, name)
    ws.write(2, 0, 'F.Y.:',       FMETA); ws.write(2, 1, fy)
    ws.write(3, 0, 'Period:',     FMETA); ws.write(3, 1, period)

    ws.set_row(4, 6)
    ws.merge_range(5, 0, 5, 17, '  COMBINED ISSUES  —  All Unresolved Items (B2B + CDNR)', FBANNER)
    ws.set_row(5, 26)

    hdrs = ['#', 'Module', 'Party Name', 'GSTIN',
            'Doc No (Books)', 'Date (Books)', 'Taxable (Books)', 'IGST (Books)', 'CGST (Books)', 'SGST (Books)',
            'Doc No (Portal)', 'Date (Portal)', 'Taxable (Portal)', 'IGST (Portal)', 'CGST (Portal)', 'SGST (Portal)',
            'Diff Taxable', 'Diff IGST', 'Diff CGST', 'Diff SGST', 'Status']
    ws.set_row(7, 18)
    for ci, h in enumerate(hdrs):
        ws.write(7, ci, h, FHDR)
    ws.freeze_panes(8, 3)

    # Filter only issues — show ALL issue types from both B2B and CDNR
    ISSUE_MASK = 'Not in|Mismatch|Suggestion|Manual|Tax Error'
    rows_out = []
    if 'Recon_Status' in b2b_df.columns:
        b2b_issues = b2b_df[b2b_df['Recon_Status'].str.contains(ISSUE_MASK, na=False)].copy()
        b2b_issues['_module'] = 'B2B'
        b2b_issues['_id_col'] = b2b_issues['Recon_Status']
        b2b_issues['_inv_b']  = b2b_issues.get('Invoice Number_BOOKS', '')
        b2b_issues['_date_b'] = b2b_issues.get('Invoice Date_BOOKS', '')
        b2b_issues['_inv_g']  = b2b_issues.get('Invoice Number_GST', '')
        b2b_issues['_date_g'] = b2b_issues.get('Invoice Date_GST', '')
        rows_out.append(b2b_issues)

    cdnr_st_col = 'Recon_Status_CDNR' if 'Recon_Status_CDNR' in cdnr_df.columns else 'Recon_Status'
    if cdnr_st_col in cdnr_df.columns:
        cdnr_issues = cdnr_df[cdnr_df[cdnr_st_col].str.contains(ISSUE_MASK, na=False)].copy()
        cdnr_issues['_module'] = 'CDNR'
        cdnr_issues['_id_col'] = cdnr_issues[cdnr_st_col]
        cdnr_issues['_inv_b']  = cdnr_issues.get('Note Number_BOOKS', '')
        cdnr_issues['_date_b'] = cdnr_issues.get('Note Date_BOOKS', '')
        cdnr_issues['_inv_g']  = cdnr_issues.get('Note Number_GST', '')
        cdnr_issues['_date_g'] = cdnr_issues.get('Note Date_GST', '')
        rows_out.append(cdnr_issues)

    if not rows_out:
        ws.write(8, 0, 'No issues found — all records matched!',
                 _f(bold=True, font_color='#065F46', font_size=11))
        ws.set_column(0, 20, 16)
        return

    all_issues = pd.concat(rows_out, ignore_index=True)

    data_row = 8
    for ri, row in all_issues.iterrows():
        ws.set_row(data_row, 16)
        status = str(row.get('_id_col', ''))
        mod    = str(row.get('_module', ''))

        # Books values
        bt  = _nn(row.get('Taxable Value_BOOKS'))
        bi  = _nn(row.get('IGST_BOOKS'))
        bc  = _nn(row.get('CGST_BOOKS'))
        bs  = _nn(row.get('SGST_BOOKS'))
        # Portal values
        gt  = _nn(row.get('Taxable Value_GST'))
        gi  = _nn(row.get('IGST_GST'))
        gc  = _nn(row.get('CGST_GST'))
        gs  = _nn(row.get('SGST_GST'))
        # Diffs
        dt  = bt - gt
        di  = bi - gi
        dc  = bc - gc
        ds  = bs - gs

        mod_fmt = _f(bold=True, bg_color='#E3F2FD' if mod=='B2B' else '#F3E5F5',
                     font_color='#1565C0' if mod=='B2B' else '#7B1FA2',
                     border=1, align='center', valign='vcenter', font_size=9)

        ws.write(data_row, 0,  ri + 1, FIDX)
        ws.write(data_row, 1,  mod,    mod_fmt)
        ws.write(data_row, 2,  _vv(row.get('Name of Party', '')), _rf(status))
        ws.write(data_row, 3,  _vv(row.get('GSTIN', row.get('GSTIN_BOOKS', ''))), _rf(status))
        ws.write(data_row, 4,  _vv(row.get('_inv_b', '')),  _rf(status))
        ws.write(data_row, 5,  _vv(row.get('_date_b', '')), _rf(status))
        ws.write(data_row, 6,  bt, _rf(status, num=True))
        ws.write(data_row, 7,  bi, _rf(status, num=True))
        ws.write(data_row, 8,  bc, _rf(status, num=True))
        ws.write(data_row, 9,  bs, _rf(status, num=True))
        ws.write(data_row, 10, _vv(row.get('_inv_g', '')),  _rf(status))
        ws.write(data_row, 11, _vv(row.get('_date_g', '')), _rf(status))
        ws.write(data_row, 12, gt, _rf(status, num=True))
        ws.write(data_row, 13, gi, _rf(status, num=True))
        ws.write(data_row, 14, gc, _rf(status, num=True))
        ws.write(data_row, 15, gs, _rf(status, num=True))

        def _dfc(v):
            return _f(bold=abs(v)>0.5, bg_color='#FFF2F2' if v>0.5 else '#F0FFF4' if v<-0.5 else '#FAFAFA',
                      font_color='#C00000' if v>0.5 else '#166534' if v<-0.5 else '#757575',
                      border=1, align='right', valign='vcenter', font_size=9, num_format='#,##0.00')
        ws.write(data_row, 16, dt, _dfc(dt))
        ws.write(data_row, 17, di, _dfc(di))
        ws.write(data_row, 18, dc, _dfc(dc))
        ws.write(data_row, 19, ds, _dfc(ds))
        ws.write(data_row, 20, status, _rf(status, bold=False))
        data_row += 1

    ws.write(data_row, 0, f'Total: {data_row - 8} issue records',
             _f(bold=True, font_color='#374151', font_size=10))

    ws.set_column(0, 0, 5);  ws.set_column(1, 1, 8);   ws.set_column(2, 2, 24)
    ws.set_column(3, 3, 18); ws.set_column(4, 4, 16);  ws.set_column(5, 5, 12)
    ws.set_column(6, 9, 13); ws.set_column(10, 10, 16); ws.set_column(11, 11, 12)
    ws.set_column(12, 15, 13); ws.set_column(16, 19, 13); ws.set_column(20, 20, 28)
