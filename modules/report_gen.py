# modules/report_gen.py
import pandas as pd
import io
import xlsxwriter
import numpy as np
import zipfile

def safe_date_format(series):
    temp = pd.to_datetime(series, dayfirst=True, errors='coerce')
    return temp.fillna(series)

def generate_vendor_split_zip(full_df):
    issue_mask = full_df['Recon_Status'].str.contains('Not in|Mismatch|Suggestion|Manual|Tax Error', na=False)
    vendors = full_df[issue_mask]['Name of Party'].unique().tolist()
    vendors = [v for v in vendors if v and str(v) != 'nan']
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
        for vendor in vendors:
            sub_df = full_df[full_df['Name of Party'] == vendor].copy()
            export_data = []
            for idx, row in sub_df.iterrows():
                status = row.get('Recon_Status', '')
                b_inv=row.get('Invoice Number_BOOKS',''); b_date=row.get('Invoice Date_BOOKS','')
                b_tax=row.get('Taxable Value_BOOKS',0); b_igst=row.get('IGST_BOOKS',0)
                b_cgst=row.get('CGST_BOOKS',0); b_sgst=row.get('SGST_BOOKS',0)
                b_total=b_tax+b_igst+b_cgst+b_sgst
                g_inv=row.get('Invoice Number_GST',''); g_date=row.get('Invoice Date_GST','')
                g_tax=row.get('Taxable Value_GST',0); g_igst=row.get('IGST_GST',0)
                g_cgst=row.get('CGST_GST',0); g_sgst=row.get('SGST_GST',0)
                g_total=g_tax+g_igst+g_cgst+g_sgst
                ref_inv=g_inv if pd.notna(g_inv) and str(g_inv)!='nan' else b_inv
                export_data.append({'Status':status,'Inv No':ref_inv,
                    'Portal Date':g_date,'Portal Taxable':g_tax,'Portal IGST':g_igst,
                    'Portal CGST':g_cgst,'Portal SGST':g_sgst,'Portal Total':g_total,
                    'Books Date':b_date,'Books Taxable':b_tax,'Books IGST':b_igst,
                    'Books CGST':b_cgst,'Books SGST':b_sgst,'Books Total':b_total,
                    'Diff Total':round(b_total-g_total,2)})
            export_df = pd.DataFrame(export_data)
            if 'Portal Date' in export_df.columns: export_df['Portal Date']=safe_date_format(export_df['Portal Date'])
            if 'Books Date'  in export_df.columns: export_df['Books Date'] =safe_date_format(export_df['Books Date'])
            excel_buffer = io.BytesIO()
            with pd.ExcelWriter(excel_buffer,engine='xlsxwriter',datetime_format='dd/mm/yyyy') as writer:
                export_df.to_excel(writer,index=False,startrow=2,sheet_name='Discrepancy Report')
                wb=writer.book; ws=writer.sheets['Discrepancy Report']
                # Formats
                fmt_portal_hdr = wb.add_format({'bold':True,'bg_color':'#1F3864','font_color':'white','border':1,'align':'center','valign':'vcenter'})
                fmt_books_hdr  = wb.add_format({'bold':True,'bg_color':'#C00000','font_color':'white','border':1,'align':'center','valign':'vcenter'})
                fmt_info_hdr   = wb.add_format({'bold':True,'bg_color':'#2E75B6','font_color':'white','border':1,'align':'center','valign':'vcenter'})
                fmt_diff_hdr   = wb.add_format({'bold':True,'bg_color':'#7030A0','font_color':'white','border':1,'align':'center','valign':'vcenter'})
                # Status row formats
                STATUS_ROW_COLORS = {
                    'Invoices Not in GSTR-2B':       ('#FFF2F2','#C00000'),
                    'Invoices Not in Purchase Books': ('#FFFBEA','#B8860B'),
                    'AI Matched (Mismatch)':          ('#FFF0F0','#C00000'),
                    'Matched (Tax Error)':            ('#FFFBEA','#B8860B'),
                    'AI Matched (Date Mismatch)':     ('#EBF3FB','#2E75B6'),
                    'AI Matched (Invoice Mismatch)':  ('#EBF3FB','#2E75B6'),
                    'Suggestion':                     ('#EBF3FB','#2E75B6'),
                    'Suggestion (Group Match)':       ('#EBF3FB','#2E75B6'),
                    'Manually Linked':                ('#F0FFF4','#1E6B3C'),
                }
                row_fmts = {}
                for st,(bg,fc_c) in STATUS_ROW_COLORS.items():
                    row_fmts[st] = {
                        'normal': wb.add_format({'bg_color':bg,'border':1,'valign':'vcenter'}),
                        'number': wb.add_format({'bg_color':bg,'border':1,'valign':'vcenter','num_format':'#,##0.00'}),
                        'bold':   wb.add_format({'bg_color':bg,'border':1,'valign':'vcenter','bold':True,'num_format':'#,##0.00','font_color':fc_c}),
                    }
                default_fmts = {
                    'normal': wb.add_format({'border':1,'valign':'vcenter'}),
                    'number': wb.add_format({'border':1,'valign':'vcenter','num_format':'#,##0.00'}),
                    'bold':   wb.add_format({'border':1,'valign':'vcenter','bold':True,'num_format':'#,##0.00'}),
                }
                # Header row 1: group labels
                ws.merge_range(0,0,0,1,'INVOICE DETAILS',fmt_info_hdr)
                ws.merge_range(0,2,0,7,'GST PORTAL DATA (GSTR-1 Filed by Supplier)',fmt_portal_hdr)
                ws.merge_range(0,8,0,13,'PURCHASE BOOKS DATA (Our Records)',fmt_books_hdr)
                ws.write(0,14,'DIFFERENCE',fmt_diff_hdr)
                # Header row 2: column names
                cols = list(export_df.columns)
                for cn,v in enumerate(cols):
                    fmt = fmt_portal_hdr if 'Portal' in v else fmt_books_hdr if 'Books' in v else fmt_diff_hdr if 'Diff' in v else fmt_info_hdr
                    ws.write(2,cn,v,fmt)
                # Data rows with status coloring
                num_cols = {'Portal Taxable','Portal IGST','Portal CGST','Portal SGST','Portal Total',
                            'Books Taxable','Books IGST','Books CGST','Books SGST','Books Total','Diff Total'}
                for rn, (_, row) in enumerate(export_df.iterrows()):
                    st = str(row.get('Status',''))
                    fmts = row_fmts.get(st, default_fmts)
                    for cn, col in enumerate(cols):
                        val = row[col]
                        is_diff = col == 'Diff Total'
                        if col in num_cols:
                            try:
                                ws.write_number(rn+3, cn, float(val) if pd.notna(val) else 0, fmts['bold'] if is_diff else fmts['number'])
                            except:
                                ws.write(rn+3, cn, val or '', fmts['normal'])
                        else:
                            ws.write(rn+3, cn, str(val) if pd.notna(val) else '', fmts['normal'])
                # Column widths
                ws.set_column(0,0,18); ws.set_column(1,1,14); ws.set_column(2,14,13)
                ws.set_row(0,20); ws.set_row(2,18)
                ws.freeze_panes(3,2)
            zip_file.writestr(f"{vendor}_Discrepancy.xlsx".replace('/','_'),excel_buffer.getvalue())
    return zip_buffer


def generate_excel(full_df, company_gstin, company_name, fy, period, cdnr_df=None):
    output = io.BytesIO()
    writer = pd.ExcelWriter(output, engine='xlsxwriter', datetime_format='dd/mm/yyyy')
    wb = writer.book

    # ── Base formats ──────────────────────────────────────────────────────────
    def _f(**kw): return wb.add_format(kw)
    fmt_orange   = _f(bold=True,bg_color='#ED7D31',border=1,font_color='white',align='center',valign='vcenter',text_wrap=True)
    fmt_green    = _f(bold=True,bg_color='#70AD47',border=1,font_color='white',align='center',valign='vcenter',text_wrap=True)
    fmt_gray     = _f(bold=True,bg_color='#D9D9D9',border=1,align='center',valign='vcenter',text_wrap=True)
    fmt_blue     = _f(bold=True,bg_color='#4472C4',border=1,font_color='white',align='center',valign='vcenter',text_wrap=True)
    fmt_yellow   = _f(bold=True,bg_color='#FFD966',border=1,align='center',valign='vcenter',text_wrap=True)
    fmt_red_hdr  = _f(bold=True,bg_color='#C00000',border=1,font_color='white',align='center')
    fmt_bold     = _f(bold=True)
    fmt_date_col = _f(align='center',valign='vcenter')

    def write_meta(ws, title, cols):
        ws.write(0,4,"GSTIN:",fmt_bold);     ws.write(0,5,company_gstin)
        ws.write(1,4,"Trade Name:",fmt_bold);ws.write(1,5,company_name)
        ws.write(2,4,"F.Y.",fmt_bold);       ws.write(2,5,fy)
        ws.write(3,4,"Period:",fmt_bold);    ws.write(3,5,period)
        ws.merge_range(4,0,4,cols,title,_f(bold=True,bg_color='#BDD7EE',border=1,align='center'))

    def _money(df_s, col):
        return float(df_s[col].fillna(0).sum()) if col in df_s.columns else 0.0

    def _row8(df_s, use_books=True):
        suffix = '_BOOKS' if use_books else '_GST'
        tv=_money(df_s,'Taxable Value'+suffix); ig=_money(df_s,'IGST'+suffix)
        cg=_money(df_s,'CGST'+suffix);          sg=_money(df_s,'SGST'+suffix)
        tg=ig+cg+sg
        return [len(df_s), tv, ig, cg, sg, 0.0, tg, tv+tg]

    def _sub(pat):
        try:    return full_df[full_df['Recon_Status'].str.contains(pat, na=False)]
        except: return full_df.iloc[0:0]

    # Pull source totals for grid
    bk_df  = full_df[full_df['Taxable Value_BOOKS'].notna()] if 'Taxable Value_BOOKS' in full_df.columns else full_df.iloc[0:0]
    gst_df = full_df[full_df['Taxable Value_GST'].notna()]   if 'Taxable Value_GST'   in full_df.columns else full_df.iloc[0:0]
    bk_b2b  = _row8(bk_df,  True)
    gst_b2b = _row8(gst_df, False)

    if cdnr_df is not None and not cdnr_df.empty:
        cdnr_bk_df  = cdnr_df[cdnr_df['Taxable Value_BOOKS'].notna()] if 'Taxable Value_BOOKS' in cdnr_df.columns else cdnr_df.iloc[0:0]
        cdnr_gst_df = cdnr_df[cdnr_df['Taxable Value_GST'].notna()]   if 'Taxable Value_GST'   in cdnr_df.columns else cdnr_df.iloc[0:0]
        bk_cdnr  = _row8(cdnr_bk_df,  True)
        gst_cdnr = _row8(cdnr_gst_df, False)
    else:
        bk_cdnr  = [0]*8
        gst_cdnr = [0]*8

    bk_total  = [bk_b2b[i]  + bk_cdnr[i]  for i in range(8)]
    gst_grand = [gst_b2b[i] + gst_cdnr[i] for i in range(8)]
    b2ba_row  = [0]*8
    cdnra_row = [0]*8

    # ── EXECUTIVE SUMMARY ─────────────────────────────────────────────────────
    ws_exec = wb.add_worksheet('Executive Summary')
    for r in range(4): ws_exec.set_row(r,16)
    ws_exec.write(0,0,"GSTIN:",fmt_bold);     ws_exec.write(0,1,company_gstin)
    ws_exec.write(1,0,"Trade Name:",fmt_bold);ws_exec.write(1,1,company_name)
    ws_exec.write(2,0,"F.Y.:",fmt_bold);      ws_exec.write(2,1,fy)
    ws_exec.write(3,0,"Period:",fmt_bold);    ws_exec.write(3,1,period)

    FBK_T =_f(bold=True,bg_color='#2E7D32',font_color='white',border=1,align='center',valign='vcenter',font_size=10)
    FBK_L =_f(bg_color='#E8F5E9',font_color='#1B5E20',border=1,align='left',valign='vcenter',font_size=9)
    FBK_V =_f(bg_color='#E8F5E9',font_color='#37474F',border=1,align='right',valign='vcenter',font_size=9,num_format='#,##0.00')
    FBK_TL=_f(bold=True,bg_color='#C8E6C9',font_color='#1B5E20',border=1,align='left',valign='vcenter',font_size=9)
    FBK_TV=_f(bold=True,bg_color='#C8E6C9',font_color='#1B5E20',border=1,align='right',valign='vcenter',font_size=9,num_format='#,##0.00')
    FGT_T =_f(bold=True,bg_color='#1565C0',font_color='white',border=1,align='center',valign='vcenter',font_size=10)
    FGT_L =_f(bg_color='#E3F2FD',font_color='#0D47A1',border=1,align='left',valign='vcenter',font_size=9)
    FGT_V =_f(bg_color='#E3F2FD',font_color='#37474F',border=1,align='right',valign='vcenter',font_size=9,num_format='#,##0.00')
    FGT_NA=_f(bg_color='#E3F2FD',font_color='#9E9E9E',border=1,align='center',valign='vcenter',font_size=9,italic=True)
    FGT_TL=_f(bold=True,bg_color='#BBDEFB',font_color='#0D47A1',border=1,align='left',valign='vcenter',font_size=9)
    FGT_TV=_f(bold=True,bg_color='#BBDEFB',font_color='#0D47A1',border=1,align='right',valign='vcenter',font_size=9,num_format='#,##0.00')
    FDF_T =_f(bold=True,bg_color='#37474F',font_color='white',border=1,align='center',valign='vcenter',font_size=10)
    FDF_L =_f(bg_color='#FFF9C4',font_color='#37474F',border=1,align='left',valign='vcenter',font_size=9)
    FDF_PL=_f(bold=True,bg_color='#DCEDC8',font_color='#2E7D32',border=1,align='right',valign='vcenter',font_size=9,num_format='#,##0.00')
    FDF_NG=_f(bold=True,bg_color='#FFCDD2',font_color='#C62828',border=1,align='right',valign='vcenter',font_size=9,num_format='#,##0.00')
    FDF_ZR=_f(bold=True,bg_color='#FFF9C4',font_color='#757575',border=1,align='right',valign='vcenter',font_size=9,num_format='#,##0.00')
    FHDR  =_f(bold=True,bg_color='#0D47A1',font_color='white',border=1,align='center',valign='vcenter',font_size=9)
    FNOTE =_f(italic=True,font_color='#607D8B',font_size=8,align='left',valign='vcenter',text_wrap=True)

    def dfmt(v):
        return FDF_PL if v>0.01 else FDF_NG if v<-0.01 else FDF_ZR

    ws_exec.set_column(0,0,20); ws_exec.set_column(1,1,10)
    ws_exec.set_column(2,2,20); ws_exec.set_column(3,6,16)
    ws_exec.set_column(7,7,18); ws_exec.set_column(8,8,20)

    ws_exec.set_row(4,6)
    COL_H=['','','TAXABLE (₹)','IGST (₹)','CGST (₹)','SGST (₹)','CESS (₹)','TOTAL TAX (₹)','TOTAL (₹)']
    ws_exec.set_row(5,26)
    for ci,h in enumerate(COL_H): ws_exec.write(5,ci,h,FHDR)

    cdnr_available = cdnr_df is not None and not (hasattr(cdnr_df,'empty') and cdnr_df.empty)
    FNA = _f(bg_color='#F5F5F5',font_color='#BDBDBD',border=1,align='center',valign='vcenter',font_size=9,italic=True)

    # BOOKS
    ws_exec.set_row(6,22); ws_exec.merge_range(6,0,6,8,'  BOOKS  (Purchase Register)',FBK_T)
    for row,l1,l2,vals,is_cdnr in [(7,'Books','B2B',bk_b2b,False),(8,'','CDNR',bk_cdnr,True)]:
        ws_exec.set_row(row,20)
        ws_exec.write(row,0,l1,FBK_L); ws_exec.write(row,1,l2,FBK_L)
        for ci,v in enumerate(vals[1:],2):
            if is_cdnr and not cdnr_available:
                ws_exec.write(row,ci,'—',FNA)
            else:
                ws_exec.write(row,ci,v,FBK_V)
    ws_exec.set_row(9,22)
    ws_exec.write(9,0,'TOTAL BOOKS',FBK_TL); ws_exec.write(9,1,'',FBK_TL)
    for ci,v in enumerate(bk_total[1:],2): ws_exec.write(9,ci,v,FBK_TV)

    # GSTR-2B
    ws_exec.set_row(10,6); ws_exec.set_row(11,22)
    ws_exec.merge_range(11,0,11,8,'  GSTR-2B  (Portal Data)',FGT_T)
    for row,l1,l2,vals,amend,is_cdnr in [
            (12,'GSTR-2B','B2B', gst_b2b,  False, False),
            (13,'',       'B2BA',b2ba_row, True,  False),
            (14,'',       'CDNR',gst_cdnr, False, True),
            (15,'',       'CDNRA',cdnra_row,True, False)]:
        ws_exec.set_row(row,20)
        ws_exec.write(row,0,l1,FGT_L); ws_exec.write(row,1,l2,FGT_L)
        for ci,v in enumerate(vals[1:],2):
            if is_cdnr and not cdnr_available:
                ws_exec.write(row,ci,'—',FNA)
            elif amend and v==0:
                ws_exec.write(row,ci,'—',FGT_NA)
            else:
                ws_exec.write(row,ci,v,FGT_V)
    ws_exec.set_row(16,22)
    ws_exec.write(16,0,'TOTAL GSTR-2B',FGT_TL); ws_exec.write(16,1,'',FGT_TL)
    for ci,v in enumerate(gst_grand[1:],2): ws_exec.write(16,ci,v,FGT_TV)

    # DIFFERENCE
    ws_exec.set_row(17,6); ws_exec.set_row(18,22)
    ws_exec.merge_range(18,0,18,8,'  DIFFERENCE  (GSTR-2B  −  Books)',FDF_T)
    diff_b2b =[gst_b2b[i]-bk_b2b[i]   for i in range(8)]
    diff_cdn =[gst_cdnr[i]-bk_cdnr[i] for i in range(8)]
    diff_tot =[gst_grand[i]-bk_total[i] for i in range(8)]
    for row,l1,l2,vals in [(19,'Diff','B2B',diff_b2b),(20,'Diff','CDNR',diff_cdn),(21,'TOTAL DIFF','',diff_tot)]:
        ws_exec.set_row(row,20)
        ws_exec.write(row,0,l1,FDF_L); ws_exec.write(row,1,l2,FDF_L)
        for ci,v in enumerate(vals[1:],2): ws_exec.write(row,ci,v,dfmt(v))
    ws_exec.set_row(22,6); ws_exec.set_row(23,28)
    ws_exec.merge_range(23,0,23,8,
        '🔴 Red = GSTR-2B < Books (ITC may be at risk)   '
        '🟢 Green = GSTR-2B > Books (supplier reported more)   '
        '⬜ Yellow = No difference',FNOTE)
    if not cdnr_available:
        ws_exec.set_row(24,20)
        FNOTE2 = _f(italic=True,bold=True,font_color='#E65100',font_size=8,align='left',valign='vcenter',
                    bg_color='#FFF8E1',border=1,text_wrap=True)
        ws_exec.merge_range(24,0,24,8,
            '⚠️  CDNR rows show  —  because Credit Note reconciliation has not been run yet. '
            'Run CDNR Reconciliation and re-download this report to see complete data.',FNOTE2)

    # ── RECO SUMMARY — Individual B2B Record Reconciliation ──────────────────
    # Each row = one invoice pair (Books ↔ Portal), sorted by status priority
    ws_sum = wb.add_worksheet('Reco Summary')

    # ── Formats ──────────────────────────────────────────────────────────────
    FBANNER  = _f(bold=True,bg_color='#1F3864',font_color='white',align='center',valign='vcenter',font_size=13,border=1)
    FKPI_L   = _f(bold=True,bg_color='#EFF4FF',font_color='#0D47A1',border=1,align='left',  valign='vcenter',font_size=9)
    FKPI_V   = _f(bold=True,bg_color='#EFF4FF',font_color='#0D47A1',border=1,align='center',valign='vcenter',font_size=11,num_format='#,##0')
    FGRP_BK  = _f(bold=True,bg_color='#ED7D31',font_color='white',  border=1,align='center',valign='vcenter',font_size=9)
    FGRP_GT  = _f(bold=True,bg_color='#70AD47',font_color='white',  border=1,align='center',valign='vcenter',font_size=9)
    FGRP_DF  = _f(bold=True,bg_color='#9E9E9E',font_color='white',  border=1,align='center',valign='vcenter',font_size=9)
    FGRP_ST  = _f(bold=True,bg_color='#4472C4',font_color='white',  border=1,align='center',valign='vcenter',font_size=9)
    FHDR_COL = _f(bold=True,bg_color='#4472C4',font_color='white',  border=1,align='center',valign='vcenter',font_size=8,text_wrap=True)
    FHDR_IDX = _f(bold=True,bg_color='#263238',font_color='white',  border=1,align='center',valign='vcenter',font_size=8)
    # Per-status row formats  (bg_color, font_color)
    _STATUS_FMT = {
        'Invoices Not in GSTR-2B':       ('#FFF2F2','#C00000'),
        'Invoices Not in Purchase Books': ('#FFFBEA','#B8860B'),
        'AI Matched (Mismatch)':          ('#FFF0F0','#C00000'),
        'Matched (Tax Error)':            ('#FFFBEA','#B8860B'),
        'AI Matched (Date Mismatch)':     ('#EBF3FB','#2E75B6'),
        'AI Matched (Invoice Mismatch)':  ('#EBF3FB','#2E75B6'),
        'AI Matched':                     ('#EBF3FB','#2E75B6'),
        'Suggestion (Group Match)':       ('#F3E5F5','#7C3AED'),
        'Suggestion':                     ('#EFF4FF','#1D4ED8'),
        'Manually Linked':                ('#F0FFF4','#1E6B3C'),
        'Matched':                        ('#F0FFF4','#1E6B3C'),
    }
    _STATUS_PRIORITY = {
        'Invoices Not in GSTR-2B': 1, 'Invoices Not in Purchase Books': 2,
        'AI Matched (Mismatch)': 3,   'Matched (Tax Error)': 4,
        'AI Matched': 5,              'Suggestion (Group Match)': 6,
        'Suggestion': 7,              'Manually Linked': 8,
        'Matched': 9,
    }
    def _row_fmt(status, num=False, bold=False):
        bg,fc='#FFFFFF','#37474F'
        for k,(b,f) in _STATUS_FMT.items():
            if k in str(status): bg,fc=b,f; break
        kw=dict(bg_color=bg,font_color=fc,border=1,valign='vcenter',font_size=9)
        if bold: kw['bold']=True
        if num:  kw['num_format']='#,##0.00'; kw['align']='right'
        else:    kw['align']='left'
        return _f(**kw)
    def _status_priority(s):
        for k,v in _STATUS_PRIORITY.items():
            if k in str(s): return v
        return 10

    import pandas as _pd
    def _v(val):
        if val is None: return ''
        if isinstance(val, float) and np.isnan(val): return ''
        try:
            if _pd.isnull(val): return ''
        except (TypeError, ValueError):
            pass
        try:
            if hasattr(val, 'strftime'):
                return val.strftime('%d/%m/%Y')
        except Exception:
            pass
        return val
    def _n(val):
        try:    return float(val) if val is not None and not (isinstance(val,float) and np.isnan(val)) else 0.0
        except: return 0.0

    # ── Meta header ──────────────────────────────────────────────────────────
    ws_sum.write(0,0,'GSTIN:',fmt_bold);     ws_sum.write(0,1,company_gstin)
    ws_sum.write(1,0,'Trade Name:',fmt_bold);ws_sum.write(1,1,company_name)
    ws_sum.write(2,0,'F.Y.:',fmt_bold);      ws_sum.write(2,1,fy)
    ws_sum.write(3,0,'Period:',fmt_bold);    ws_sum.write(3,1,period)

    # ── Compact KPI row ───────────────────────────────────────────────────────
    bkdf_s  = full_df[full_df['Taxable Value_BOOKS'].notna()] if 'Taxable Value_BOOKS' in full_df.columns else full_df.iloc[0:0]
    gstdf_s = full_df[full_df['Taxable Value_GST'].notna()]   if 'Taxable Value_GST'   in full_df.columns else full_df.iloc[0:0]

    def _bsub(pat):
        try:    return full_df[full_df['Recon_Status'].str.contains(pat,na=False)]
        except: return full_df.iloc[0:0]

    kpi_data = [
        ('Books Invoices',      len(bkdf_s)),
        ('Portal Invoices',     len(gstdf_s)),
        ('Matched',             len(_bsub(r'Matched'))),
        ('Mismatched',          len(_bsub(r'Mismatch'))),
        ('Not in GSTR-2B',      len(_bsub(r'Not in GSTR-2B'))),
        ('Not in Books',        len(_bsub(r'Not in.*Books'))),
        ('Suggestions',         len(_bsub(r'Suggestion'))),
        ('AI Matched',          len(_bsub(r'AI Matched'))),
    ]
    ws_sum.set_row(4,6)
    ws_sum.merge_range(5,0,5,15,'B2B Reconciliation — Individual Record View',FBANNER)
    ws_sum.set_row(5,26)
    for ki,(lbl,val) in enumerate(kpi_data):
        col = ki * 2
        ws_sum.write(6, col,   lbl, FKPI_L)
        ws_sum.write(6, col+1, val, FKPI_V)
    ws_sum.set_row(6,22)

    # ── Column group headers (row 8) ──────────────────────────────────────────
    # Columns layout:  #  | Name | GSTIN | -- BOOKS (4 cols) -- | -- PORTAL (4 cols) -- | Diff Taxable | Diff GST | Status
    REC_COLS = [
        '#', 'Name of Party', 'GSTIN',
        'Inv No (Books)', 'Date (Books)', 'Taxable (Books)', 'IGST (B)', 'CGST (B)', 'SGST (B)',
        'Inv No (Portal)', 'Date (Portal)', 'Taxable (Portal)', 'IGST (P)', 'CGST (P)', 'SGST (P)',
        'Diff Taxable', 'Diff GST', 'Status',
    ]
    TOTAL_COLS = len(REC_COLS)  # 18
    ws_sum.set_row(7,6)
    ws_sum.set_row(8,18)
    ws_sum.write(8, 0,'#',       FHDR_IDX)
    ws_sum.merge_range(8,1,8,2,  'PARTY DETAILS',  FGRP_ST)
    ws_sum.merge_range(8,3,8,8,  'BOOKS  (Purchase Register)', FGRP_BK)
    ws_sum.merge_range(8,9,8,14, 'GSTR-2B  (Portal)',          FGRP_GT)
    ws_sum.merge_range(8,15,8,16,'DIFFERENCE (Books − Portal)', FGRP_DF)
    ws_sum.write(8,17, 'STATUS', FGRP_ST)
    ws_sum.set_row(9,18)
    for ci,h in enumerate(REC_COLS):
        ws_sum.write(9, ci, h, FHDR_COL)

    # ── Sort full_df by status priority ───────────────────────────────────────
    df_for_reco = full_df.copy()
    df_for_reco['_priority'] = df_for_reco['Recon_Status'].apply(_status_priority)
    df_for_reco = df_for_reco.sort_values(['_priority','Name of Party']).reset_index(drop=True)

    # ── Write individual records ───────────────────────────────────────────────
    data_start_row = 10
    ws_sum.freeze_panes(10, 3)

    for ri, row in df_for_reco.iterrows():
        excel_row = data_start_row + ri
        status = str(row.get('Recon_Status',''))
        ws_sum.set_row(excel_row, 16)

        fmt_txt = _row_fmt(status, num=False)
        fmt_num = _row_fmt(status, num=True)
        fmt_idx = _f(bg_color='#F5F5F5', font_color='#9E9E9E', border=1, align='center', valign='vcenter', font_size=8)

        b_tax  = _n(row.get('Taxable Value_BOOKS'));  b_igst = _n(row.get('IGST_BOOKS'))
        b_cgst = _n(row.get('CGST_BOOKS'));           b_sgst = _n(row.get('SGST_BOOKS'))
        g_tax  = _n(row.get('Taxable Value_GST'));    g_igst = _n(row.get('IGST_GST'))
        g_cgst = _n(row.get('CGST_GST'));             g_sgst = _n(row.get('SGST_GST'))
        d_tax  = b_tax - g_tax
        d_gst  = (b_igst+b_cgst+b_sgst) - (g_igst+g_cgst+g_sgst)

        ws_sum.write(excel_row,  0, ri+1,                               fmt_idx)
        ws_sum.write(excel_row,  1, _v(row.get('Name of Party','')),    fmt_txt)
        ws_sum.write(excel_row,  2, _v(row.get('GSTIN','')),            fmt_txt)
        ws_sum.write(excel_row,  3, _v(row.get('Invoice Number_BOOKS','')), fmt_txt)
        ws_sum.write(excel_row,  4, _v(row.get('Invoice Date_BOOKS','')),   fmt_txt)
        ws_sum.write(excel_row,  5, b_tax,   fmt_num)
        ws_sum.write(excel_row,  6, b_igst,  fmt_num)
        ws_sum.write(excel_row,  7, b_cgst,  fmt_num)
        ws_sum.write(excel_row,  8, b_sgst,  fmt_num)
        ws_sum.write(excel_row,  9, _v(row.get('Invoice Number_GST','')),  fmt_txt)
        ws_sum.write(excel_row, 10, _v(row.get('Invoice Date_GST','')),    fmt_txt)
        ws_sum.write(excel_row, 11, g_tax,   fmt_num)
        ws_sum.write(excel_row, 12, g_igst,  fmt_num)
        ws_sum.write(excel_row, 13, g_cgst,  fmt_num)
        ws_sum.write(excel_row, 14, g_sgst,  fmt_num)

        # Diff columns — colour based on sign
        def _diff_fmt(v, stat):
            bg,fc = '#FFFFFF','#37474F'
            for k,(b,f) in _STATUS_FMT.items():
                if k in stat: bg,fc=b,f; break
            if   v > 0.5:  return _f(bold=True,bg_color=bg,font_color='#C00000',border=1,align='right',valign='vcenter',font_size=9,num_format='#,##0.00')
            elif v < -0.5: return _f(bold=True,bg_color=bg,font_color='#2E7D32',border=1,align='right',valign='vcenter',font_size=9,num_format='#,##0.00')
            else:           return _f(bg_color=bg,font_color='#757575',border=1,align='right',valign='vcenter',font_size=9,num_format='#,##0.00')

        ws_sum.write(excel_row, 15, d_tax, _diff_fmt(d_tax,  status))
        ws_sum.write(excel_row, 16, d_gst, _diff_fmt(d_gst,  status))

        # Status pill
        fmt_st = _row_fmt(status, num=False, bold=True)
        ws_sum.write(excel_row, 17, status, fmt_st)

    total_data_rows = len(df_for_reco)

    # ── Totals row ────────────────────────────────────────────────────────────
    tot_row = data_start_row + total_data_rows
    FTOT = _f(bold=True,bg_color='#1F3864',font_color='white',border=1,align='right',valign='vcenter',font_size=9,num_format='#,##0.00')
    FTOT_L = _f(bold=True,bg_color='#1F3864',font_color='white',border=1,align='center',valign='vcenter',font_size=9)
    ws_sum.merge_range(tot_row,0,tot_row,4,'TOTALS',FTOT_L)
    def _col_sum(col):
        return float(full_df[col].fillna(0).sum()) if col in full_df.columns else 0.0
    for ci,col in enumerate(['Taxable Value_BOOKS','IGST_BOOKS','CGST_BOOKS','SGST_BOOKS'],5):
        ws_sum.write(tot_row, ci, _col_sum(col), FTOT)
    ws_sum.write(tot_row, 9,  '', FTOT_L)
    ws_sum.write(tot_row, 10, '', FTOT_L)
    for ci,col in enumerate(['Taxable Value_GST','IGST_GST','CGST_GST','SGST_GST'],11):
        ws_sum.write(tot_row, ci, _col_sum(col), FTOT)
    d_tax_tot = _col_sum('Taxable Value_BOOKS') - _col_sum('Taxable Value_GST')
    d_gst_tot = (_col_sum('IGST_BOOKS')+_col_sum('CGST_BOOKS')+_col_sum('SGST_BOOKS')) - \
                (_col_sum('IGST_GST')  +_col_sum('CGST_GST')  +_col_sum('SGST_GST'))
    ws_sum.write(tot_row,15, d_tax_tot, FTOT)
    ws_sum.write(tot_row,16, d_gst_tot, FTOT)
    ws_sum.write(tot_row,17, f'{total_data_rows} records', FTOT_L)
    ws_sum.set_row(tot_row,20)

    # ── Column widths ──────────────────────────────────────────────────────────
    ws_sum.set_column(0, 0,  5)   # #
    ws_sum.set_column(1, 1, 24)   # Name
    ws_sum.set_column(2, 2, 18)   # GSTIN
    ws_sum.set_column(3, 3, 16)   # Inv No Books
    ws_sum.set_column(4, 4, 12)   # Date Books
    ws_sum.set_column(5, 8, 13)   # Taxable IGST CGST SGST Books
    ws_sum.set_column(9, 9, 16)   # Inv No Portal
    ws_sum.set_column(10,10,12)   # Date Portal
    ws_sum.set_column(11,14,13)   # Taxable IGST CGST SGST Portal
    ws_sum.set_column(15,16,14)   # Diff
    ws_sum.set_column(17,17,28)   # Status

    row_ptr = tot_row + 2

    # ── DATA SHEETS ───────────────────────────────────────────────────────────
    display_cols=['GSTIN','Name of Party',
        'Invoice Number_BOOKS','Invoice Date_BOOKS','Taxable Value_BOOKS','IGST_BOOKS','CGST_BOOKS','SGST_BOOKS',
        'Invoice Number_GST','Invoice Date_GST','Taxable Value_GST','IGST_GST','CGST_GST','SGST_GST',
        'Diff_Taxable','Diff_IGST','Diff_CGST','Diff_SGST','Recon_Status','Match_Logic']
    headers=['GSTIN','Name of Party',
        'Inv No (Books)','Date','Taxable','IGST','CGST','SGST',
        'Inv No (GSTR-2B)','Date','Taxable','IGST','CGST','SGST',
        'Diff Taxable','Diff IGST','Diff CGST','Diff SGST','Status','Match Logic']
    sug_display_cols=['GSTIN','Name of Party',
        'Invoice Number_BOOKS','Invoice Date_BOOKS','Taxable Value_BOOKS','IGST_BOOKS','CGST_BOOKS','SGST_BOOKS',
        'GSTIN_GST','Name of Party_GST','GST_Remark',
        'Invoice Number_GST','Invoice Date_GST','Taxable Value_GST','IGST_GST','CGST_GST','SGST_GST',
        'Diff_Taxable','Diff_IGST','Diff_CGST','Diff_SGST','Recon_Status','Match_Logic']
    sug_headers=['GSTIN','Name of Party',
        'Inv No (Books)','Date','Taxable','IGST','CGST','SGST',
        'GSTIN (2B)','Name (2B)','GSTIN Status',
        'Inv No (GSTR-2B)','Date','Taxable','IGST','CGST','SGST',
        'Diff Taxable','Diff IGST','Diff CGST','Diff SGST','Status','Match Logic']

    sheets={
        'All Data':      full_df,
        'Matched':       full_df[full_df['Recon_Status'].str.contains('Matched',na=False)&~full_df['Recon_Status'].str.contains('AI',na=False)],
        'Mismatch':      full_df[full_df['Recon_Status'].str.contains('Mismatch',na=False)],
        'AI Matched':    full_df[full_df['Recon_Status'].str.contains('AI Matched',na=False)],
        'Suggestions':   full_df[full_df['Recon_Status'].str.contains('Suggestion',na=False)],
        'Manual':        full_df[full_df['Recon_Status'].str.contains('Manual',na=False)],
        'Not In GSTR-2B':full_df[full_df['Recon_Status'].str.contains('Not in GSTR-2B',na=False)],
        'Not In Books':  full_df[full_df['Recon_Status'].str.contains('Not in Books|Not in Purchase Books',na=False)],
    }
    for name,df_sub in sheets.items():
        if df_sub.empty: continue
        df_sub=df_sub.copy()
        if 'Invoice Date_BOOKS' in df_sub.columns: df_sub['Invoice Date_BOOKS']=safe_date_format(df_sub['Invoice Date_BOOKS'])
        if 'Invoice Date_GST'   in df_sub.columns: df_sub['Invoice Date_GST']  =safe_date_format(df_sub['Invoice Date_GST'])
        df_sub['Diff_Taxable']=df_sub['Taxable Value_BOOKS'].fillna(0)-df_sub['Taxable Value_GST'].fillna(0)
        df_sub['Diff_IGST']=df_sub['IGST_BOOKS'].fillna(0)-df_sub['IGST_GST'].fillna(0)
        df_sub['Diff_CGST']=df_sub['CGST_BOOKS'].fillna(0)-df_sub['CGST_GST'].fillna(0)
        df_sub['Diff_SGST']=df_sub['SGST_BOOKS'].fillna(0)-df_sub['SGST_GST'].fillna(0)
        if name=='Suggestions':
            df_sub['GST_Remark']=np.where(df_sub['GSTIN']==df_sub['GSTIN_GST'],'✅ Match','❌ Mismatch')
            cols=sug_display_cols; heads=sug_headers
        else:
            cols=display_cols; heads=headers
        for c in cols:
            if c not in df_sub.columns: df_sub[c]=np.nan
        df_export=df_sub[cols].copy(); df_export.columns=heads
        df_export.to_excel(writer,sheet_name=name,startrow=7,header=False,index=False)
        ws=writer.sheets[name]
        write_meta(ws,f"Report :: {name}",len(heads)-1)
        ws.freeze_panes(7,4)
        if name=='Suggestions':
            ws.merge_range('C6:H6',"As Per Books [A]",fmt_orange)
            ws.merge_range('I6:Q6',"As Per GSTR-2B [B] (Details)",fmt_green)
            ws.merge_range('R6:U6',"Difference [A-B]",fmt_gray)
            for i,h in enumerate(heads):
                ws.write(6,i,h,fmt_orange if 2<=i<=7 else fmt_green if 8<=i<=16 else fmt_gray if 17<=i<=20 else fmt_yellow if i==22 else fmt_blue)
            ws.set_column(3,3,12,fmt_date_col); ws.set_column(12,12,12,fmt_date_col); ws.set_column(8,10,18)
        else:
            ws.merge_range('C6:H6',"As Per Books [A]",fmt_orange)
            ws.merge_range('I6:N6',"As Per GSTR-2B [B]",fmt_green)
            ws.merge_range('O6:R6',"Difference [A-B]",fmt_gray)
            for i,h in enumerate(heads):
                ws.write(6,i,h,fmt_orange if 2<=i<=7 else fmt_green if 8<=i<=13 else fmt_gray if 14<=i<=17 else fmt_yellow if i==19 else fmt_blue)
            ws.set_column(3,3,12,fmt_date_col); ws.set_column(9,9,12,fmt_date_col)
        ws.set_column(0,1,20); ws.set_column(2,2,18); ws.set_column(8,8,18)

    writer.close()
    return output.getvalue()
