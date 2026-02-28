# modules/cdnr_report_gen.py
import io
import numpy as np
import pandas as pd
import xlsxwriter

def _safe_date(series):
    temp = pd.to_datetime(series, dayfirst=True, errors='coerce')
    return temp.fillna(series)

DISPLAY_COLS = [
    'GSTIN_BOOKS','Name of Party',
    'Note Number_BOOKS','Note Date_BOOKS','Doc Type_BOOKS',
    'Taxable Value_BOOKS','IGST_BOOKS','CGST_BOOKS','SGST_BOOKS',
    'GSTIN_GST',
    'Note Number_GST','Note Date_GST','Note Type_GST',
    'Taxable Value_GST','IGST_GST','CGST_GST','SGST_GST',
    'Diff_Taxable','Diff_IGST','Diff_CGST','Diff_SGST',
    'Recon_Status_CDNR','Match_Logic',
]
HEADERS = [
    'GSTIN','Name of Party',
    'Note No (Books)','Note Date (Books)','Type',
    'Taxable','IGST','CGST','SGST',
    'GSTIN (2B)',
    'Note No (2B)','Note Date (2B)','Type (2B)',
    'Taxable (2B)','IGST (2B)','CGST (2B)','SGST (2B)',
    'Diff Taxable','Diff IGST','Diff CGST','Diff SGST',
    'Status','Match Logic',
]
BK_S,BK_E=2,8; GT_S,GT_E=9,16; DF_S,DF_E=17,20; ST_I=21; ML_I=22
DATE_BK=3; DATE_GT=11

SUG_DISPLAY_COLS = [
    'GSTIN_BOOKS','Name of Party',
    'Note Number_BOOKS','Note Date_BOOKS','Doc Type_BOOKS',
    'Taxable Value_BOOKS','IGST_BOOKS','CGST_BOOKS','SGST_BOOKS',
    'GSTIN_GST','Name of Party_GST','_GSTIN_Status',
    'Note Number_GST','Note Date_GST','Note Type_GST',
    'Taxable Value_GST','IGST_GST','CGST_GST','SGST_GST',
    'Diff_Taxable','Diff_IGST','Diff_CGST','Diff_SGST',
    'Recon_Status_CDNR','Match_Logic',
]
SUG_HEADERS = [
    'GSTIN','Name of Party',
    'Note No (Books)','Note Date (Books)','Type',
    'Taxable','IGST','CGST','SGST',
    'GSTIN (2B)','Name (2B)','GSTIN Status',
    'Note No (2B)','Note Date (2B)','Type (2B)',
    'Taxable (2B)','IGST (2B)','CGST (2B)','SGST (2B)',
    'Diff Taxable','Diff IGST','Diff CGST','Diff SGST',
    'Status','Match Logic',
]
SUG_BK_S,SUG_BK_E=2,8; SUG_GT_S,SUG_GT_E=9,17
SUG_DF_S,SUG_DF_E=18,21; SUG_ST_I=22; SUG_ML_I=23
SUG_DATE_BK=3; SUG_DATE_GT=13


def generate_cdnr_excel(full_df, company_gstin, company_name, fy, period,
                        b2b_full_df=None):
    output = io.BytesIO()
    writer = pd.ExcelWriter(output, engine='xlsxwriter', datetime_format='dd/mm/yyyy')
    wb     = writer.book

    def _f(**kw): return wb.add_format(kw)

    FMT = {
        'orange' : _f(bold=True,bg_color='#ED7D31',border=1,font_color='white',align='center',valign='vcenter',text_wrap=True),
        'green'  : _f(bold=True,bg_color='#70AD47',border=1,font_color='white',align='center',valign='vcenter',text_wrap=True),
        'gray'   : _f(bold=True,bg_color='#D9D9D9',border=1,align='center',valign='vcenter',text_wrap=True),
        'blue'   : _f(bold=True,bg_color='#4472C4',border=1,font_color='white',align='center',valign='vcenter',text_wrap=True),
        'yellow' : _f(bold=True,bg_color='#FFD966',border=1,align='center',valign='vcenter',text_wrap=True),
        'red'    : _f(bold=True,bg_color='#C00000',border=1,font_color='white',align='center'),
        'bold'   : _f(bold=True),
        'date'   : _f(align='center',valign='vcenter'),
        'banner' : _f(bold=True,bg_color='#BDD7EE',border=1,align='center'),
        'sum_title':_f(bold=True,bg_color='#1F3864',font_color='white',align='center',valign='vcenter',font_size=12,border=1),
        'sum_head' :_f(bold=True,bg_color='#4472C4',font_color='white',border=1,align='center',valign='vcenter',text_wrap=True),
        'sum_yellow':_f(bold=True,bg_color='#FFD966',border=1,align='left',valign='vcenter'),
        'sum_label' :_f(bg_color='#F2F2F2',border=1,align='left',valign='vcenter'),
        'sum_val'   :_f(border=1,align='right',valign='vcenter',num_format='#,##0.00'),
        'sum_cnt'   :_f(border=1,align='center',valign='vcenter',num_format='#,##0'),
    }

    def _meta(ws, title, n_cols):
        ws.write(0,4,'GSTIN:',     FMT['bold']); ws.write(0,5,company_gstin)
        ws.write(1,4,'Trade Name:',FMT['bold']); ws.write(1,5,company_name)
        ws.write(2,4,'F.Y.',       FMT['bold']); ws.write(2,5,fy)
        ws.write(3,4,'Period:',    FMT['bold']); ws.write(3,5,period)
        ws.merge_range(4,0,4,n_cols,title,FMT['banner'])

    def _money(df_s, col):
        return float(df_s[col].fillna(0).sum()) if col in df_s.columns else 0.0

    def _row8(df_s, use_books=True):
        sx='_BOOKS' if use_books else '_GST'
        tv=_money(df_s,'Taxable Value'+sx); ig=_money(df_s,'IGST'+sx)
        cg=_money(df_s,'CGST'+sx); sg=_money(df_s,'SGST'+sx); tg=ig+cg+sg
        return [len(df_s),tv,ig,cg,sg,0.0,tg,tv+tg]

    # Source totals for grid
    cdnr_bk_df  = full_df[full_df['Taxable Value_BOOKS'].notna()] if 'Taxable Value_BOOKS' in full_df.columns else full_df.iloc[0:0]
    cdnr_gst_df = full_df[full_df['Taxable Value_GST'].notna()]   if 'Taxable Value_GST'   in full_df.columns else full_df.iloc[0:0]
    bk_cdnr  = _row8(cdnr_bk_df,  True)
    gst_cdnr = _row8(cdnr_gst_df, False)

    if b2b_full_df is not None and not b2b_full_df.empty:
        b2b_bk_df  = b2b_full_df[b2b_full_df['Taxable Value_BOOKS'].notna()] if 'Taxable Value_BOOKS' in b2b_full_df.columns else b2b_full_df.iloc[0:0]
        b2b_gst_df = b2b_full_df[b2b_full_df['Taxable Value_GST'].notna()]   if 'Taxable Value_GST'   in b2b_full_df.columns else b2b_full_df.iloc[0:0]
        bk_b2b  = _row8(b2b_bk_df,  True)
        gst_b2b = _row8(b2b_gst_df, False)
    else:
        bk_b2b  = [0]*8
        gst_b2b = [0]*8

    b2ba_row  = [0]*8
    cdnra_row = [0]*8
    bk_total  = [bk_b2b[i]+bk_cdnr[i]   for i in range(8)]
    gst_grand = [gst_b2b[i]+gst_cdnr[i] for i in range(8)]

    # ── EXECUTIVE SUMMARY ─────────────────────────────────────────────────────
    ws_ex = wb.add_worksheet('Executive Summary')
    for r in range(4): ws_ex.set_row(r,16)
    ws_ex.write(0,0,'GSTIN:',     FMT['bold']); ws_ex.write(0,1,company_gstin)
    ws_ex.write(1,0,'Trade Name:',FMT['bold']); ws_ex.write(1,1,company_name)
    ws_ex.write(2,0,'F.Y.:',      FMT['bold']); ws_ex.write(2,1,fy)
    ws_ex.write(3,0,'Period:',    FMT['bold']); ws_ex.write(3,1,period)

    FBK_T=_f(bold=True,bg_color='#2E7D32',font_color='white',border=1,align='center',valign='vcenter',font_size=10)
    FBK_L=_f(bg_color='#E8F5E9',font_color='#1B5E20',border=1,align='left',valign='vcenter',font_size=9)
    FBK_V=_f(bg_color='#E8F5E9',font_color='#37474F',border=1,align='right',valign='vcenter',font_size=9,num_format='#,##0.00')
    FBK_TL=_f(bold=True,bg_color='#C8E6C9',font_color='#1B5E20',border=1,align='left',valign='vcenter',font_size=9)
    FBK_TV=_f(bold=True,bg_color='#C8E6C9',font_color='#1B5E20',border=1,align='right',valign='vcenter',font_size=9,num_format='#,##0.00')
    FGT_T=_f(bold=True,bg_color='#1565C0',font_color='white',border=1,align='center',valign='vcenter',font_size=10)
    FGT_L=_f(bg_color='#E3F2FD',font_color='#0D47A1',border=1,align='left',valign='vcenter',font_size=9)
    FGT_V=_f(bg_color='#E3F2FD',font_color='#37474F',border=1,align='right',valign='vcenter',font_size=9,num_format='#,##0.00')
    FGT_NA=_f(bg_color='#E3F2FD',font_color='#9E9E9E',border=1,align='center',valign='vcenter',font_size=9,italic=True)
    FGT_TL=_f(bold=True,bg_color='#BBDEFB',font_color='#0D47A1',border=1,align='left',valign='vcenter',font_size=9)
    FGT_TV=_f(bold=True,bg_color='#BBDEFB',font_color='#0D47A1',border=1,align='right',valign='vcenter',font_size=9,num_format='#,##0.00')
    FDF_T=_f(bold=True,bg_color='#37474F',font_color='white',border=1,align='center',valign='vcenter',font_size=10)
    FDF_L=_f(bg_color='#FFF9C4',font_color='#37474F',border=1,align='left',valign='vcenter',font_size=9)
    FDF_PL=_f(bold=True,bg_color='#DCEDC8',font_color='#2E7D32',border=1,align='right',valign='vcenter',font_size=9,num_format='#,##0.00')
    FDF_NG=_f(bold=True,bg_color='#FFCDD2',font_color='#C62828',border=1,align='right',valign='vcenter',font_size=9,num_format='#,##0.00')
    FDF_ZR=_f(bold=True,bg_color='#FFF9C4',font_color='#757575',border=1,align='right',valign='vcenter',font_size=9,num_format='#,##0.00')
    FHDR=_f(bold=True,bg_color='#0D47A1',font_color='white',border=1,align='center',valign='vcenter',font_size=9)
    FNOTE=_f(italic=True,font_color='#607D8B',font_size=8,align='left',valign='vcenter',text_wrap=True)

    def dfmt(v): return FDF_PL if v>0.01 else FDF_NG if v<-0.01 else FDF_ZR

    ws_ex.set_column(0,0,20); ws_ex.set_column(1,1,10)
    ws_ex.set_column(2,2,20); ws_ex.set_column(3,6,16)
    ws_ex.set_column(7,7,18); ws_ex.set_column(8,8,20)

    ws_ex.set_row(4,6)
    COL_H=['','','TAXABLE (₹)','IGST (₹)','CGST (₹)','SGST (₹)','CESS (₹)','TOTAL TAX (₹)','TOTAL (₹)']
    ws_ex.set_row(5,26)
    for ci,h in enumerate(COL_H): ws_ex.write(5,ci,h,FHDR)

    # BOOKS
    ws_ex.set_row(6,22); ws_ex.merge_range(6,0,6,8,'  BOOKS  (Purchase Register)',FBK_T)
    for row,l1,l2,vals in [(7,'Books','B2B',bk_b2b),(8,'','CDNR',bk_cdnr)]:
        ws_ex.set_row(row,20)
        ws_ex.write(row,0,l1,FBK_L); ws_ex.write(row,1,l2,FBK_L)
        for ci,v in enumerate(vals[1:],2): ws_ex.write(row,ci,v,FBK_V)
    ws_ex.set_row(9,22)
    ws_ex.write(9,0,'TOTAL BOOKS',FBK_TL); ws_ex.write(9,1,'',FBK_TL)
    for ci,v in enumerate(bk_total[1:],2): ws_ex.write(9,ci,v,FBK_TV)

    # GSTR-2B
    ws_ex.set_row(10,6); ws_ex.set_row(11,22)
    ws_ex.merge_range(11,0,11,8,'  GSTR-2B  (Portal Data)',FGT_T)
    for row,l1,l2,vals,amend in [(12,'GSTR-2B','B2B',gst_b2b,False),(13,'','B2BA',b2ba_row,True),
                                  (14,'','CDNR',gst_cdnr,False),(15,'','CDNRA',cdnra_row,True)]:
        ws_ex.set_row(row,20)
        ws_ex.write(row,0,l1,FGT_L); ws_ex.write(row,1,l2,FGT_L)
        for ci,v in enumerate(vals[1:],2):
            ws_ex.write(row,ci,'—' if amend and v==0 else v, FGT_NA if amend and v==0 else FGT_V)
    ws_ex.set_row(16,22)
    ws_ex.write(16,0,'TOTAL GSTR-2B',FGT_TL); ws_ex.write(16,1,'',FGT_TL)
    for ci,v in enumerate(gst_grand[1:],2): ws_ex.write(16,ci,v,FGT_TV)

    # DIFFERENCE
    ws_ex.set_row(17,6); ws_ex.set_row(18,22)
    ws_ex.merge_range(18,0,18,8,'  DIFFERENCE  (GSTR-2B  −  Books)',FDF_T)
    diff_b2b =[gst_b2b[i]-bk_b2b[i]    for i in range(8)]
    diff_cdnr=[gst_cdnr[i]-bk_cdnr[i]  for i in range(8)]
    diff_tot =[gst_grand[i]-bk_total[i] for i in range(8)]
    for row,l1,l2,vals in [(19,'Diff','B2B',diff_b2b),(20,'Diff','CDNR',diff_cdnr),(21,'TOTAL DIFF','',diff_tot)]:
        ws_ex.set_row(row,20)
        ws_ex.write(row,0,l1,FDF_L); ws_ex.write(row,1,l2,FDF_L)
        for ci,v in enumerate(vals[1:],2): ws_ex.write(row,ci,v,dfmt(v))
    ws_ex.set_row(22,6); ws_ex.set_row(23,28)
    ws_ex.merge_range(23,0,23,8,
        '🔴 Red = GSTR-2B < Books (ITC may be at risk)   '
        '🟢 Green = GSTR-2B > Books (supplier reported more)   '
        '⬜ Yellow = No difference',FNOTE)

    # ── RECO SUMMARY ─────────────────────────────────────────────────────────
    ws_sum = wb.add_worksheet('Reco Summary')
    ws_sum.write(0,4,'GSTIN:',     FMT['bold']); ws_sum.write(0,5,company_gstin)
    ws_sum.write(1,4,'Trade Name:',FMT['bold']); ws_sum.write(1,5,company_name)
    ws_sum.write(2,4,'F.Y.',       FMT['bold']); ws_sum.write(2,5,fy)
    ws_sum.write(3,4,'Period:',    FMT['bold']); ws_sum.write(3,5,period)

    SUM_COLS=['Description','No of Invoices','Taxable Value','IGST','CGST','SGST','CESS','Total GST','Total Invoice Value']
    NC=len(SUM_COLS)

    def _r8(df_s, use_books=True):
        sx='_BOOKS' if use_books else '_GST'
        tv=_money(df_s,'Taxable Value'+sx); ig=_money(df_s,'IGST'+sx)
        cg=_money(df_s,'CGST'+sx); sg=_money(df_s,'SGST'+sx); tg=ig+cg+sg
        return [len(df_s),tv,ig,cg,sg,0.0,tg,tv+tg]

    def _block(ws, rp, title, specs):
        ws.merge_range(rp,0,rp,NC-1,title,FMT['sum_title']); rp+=1
        for ci,h in enumerate(SUM_COLS): ws.write(rp,ci,h,FMT['sum_head'])
        rp+=1
        for i,(desc,vals) in enumerate(specs):
            ws.write(rp,0,desc,FMT['sum_yellow'] if i==0 else FMT['sum_label'])
            ws.write(rp,1,vals[0],FMT['sum_cnt'])
            for ci,v in enumerate(vals[1:],2): ws.write(rp,ci,v,FMT['sum_val'])
            rp+=1
        return rp+1

    row_ptr=5

    if b2b_full_df is not None and not b2b_full_df.empty:
        bdf=b2b_full_df; bst=bdf.get('Recon_Status',pd.Series(dtype=str))
        def _b2b_sub(pat,bk=False,gt=False):
            if bk:  return bdf[bdf['Taxable Value_BOOKS'].notna()] if 'Taxable Value_BOOKS' in bdf.columns else bdf.iloc[0:0]
            if gt:  return bdf[bdf['Taxable Value_GST'].notna()]   if 'Taxable Value_GST'   in bdf.columns else bdf.iloc[0:0]
            try:    return bdf[bst.str.contains(pat,na=False)]
            except: return bdf.iloc[0:0]
        b2b_specs=[
            ('Total Invoices As Per Books',   _r8(_b2b_sub(None,bk=True))),
            ('Total Invoices As Per GSTR-2B', _r8(_b2b_sub(None,gt=True),False)),
            ('Total Matched Invoices',        _r8(_b2b_sub('Matched'))),
            ('Total AI-Matched Invoices',     _r8(_b2b_sub('AI'))),
            ('Total MisMatched Invoices',     _r8(_b2b_sub('Mismatch'))),
            ('Total MisMatched POS',          _r8(_b2b_sub('POS'))),
            ('Total MisMatched RCM',          _r8(_b2b_sub('RCM'))),
            ('Total Invoices Not In Books',   _r8(_b2b_sub('Not in.*Books'),False)),
            ('Total Invoices Not In GSTR-2B', _r8(_b2b_sub('Not in GSTR-2B'))),
        ]
        row_ptr=_block(ws_sum,row_ptr,'B2B Reconciliation Report',b2b_specs)

    s=full_df['Recon_Status_CDNR']
    def _cs(pat,bk=False,gt=False):
        if bk:  return full_df[full_df['Taxable Value_BOOKS'].notna()] if 'Taxable Value_BOOKS' in full_df.columns else full_df.iloc[0:0]
        if gt:  return full_df[full_df['Taxable Value_GST'].notna()]   if 'Taxable Value_GST'   in full_df.columns else full_df.iloc[0:0]
        return full_df[s.str.contains(pat,na=False)]
    cdnr_specs=[
        ('Total Invoice As Per Books',    _r8(_cs(None,bk=True))),
        ('Total Invoices As Per GSTR-2B', _r8(_cs(None,gt=True),False)),
        ('Total Matched Invoices',        _r8(_cs(r'CDNR Matched$'))),
        ('Total AI-Matched Invoices',     _r8(_cs('AI Matched'))),
        ('Total MisMatched Invoices',     _r8(_cs('Mismatch'))),
        ('Total Invoices Not In Books',   _r8(_cs('Not in Books'),False)),
        ('Total Invoices Not In GSTR-2B', _r8(_cs('Not in GSTR-2B'))),
    ]
    row_ptr=_block(ws_sum,row_ptr,'Credit Note Reconciliation Report',cdnr_specs)

    # Risk sidebar
    n2b=full_df[s.str.contains('Not in GSTR-2B',na=False)]
    if not n2b.empty and 'Name of Party' in n2b.columns:
        risk=(n2b.groupby('Name of Party').size().reset_index(name='Missing Notes')
               .sort_values('Missing Notes',ascending=False).head(5))
        ws_sum.write(7,NC+1,'🚨 Top 5 Missing Notes (Not in 2B)',FMT['red'])
        ws_sum.write(8,NC+1,'Vendor Name',FMT['gray']); ws_sum.write(8,NC+2,'Missing Notes',FMT['gray'])
        for ri,row in risk.iterrows():
            ws_sum.write(9+ri,NC+1,row['Name of Party']); ws_sum.write(9+ri,NC+2,row['Missing Notes'])

    # ── DIFF TABLE ────────────────────────────────────────────────────────────
    row_ptr+=1
    FDB=_f(bold=True,bg_color='#37474F',font_color='white',border=1,align='left',valign='vcenter',font_size=10)
    FDH=_f(bold=True,bg_color='#0D47A1',font_color='white',border=1,align='center',valign='vcenter',font_size=9)
    FGL=_f(bold=True,bg_color='#E3F2FD',font_color='#1565C0',border=1,align='left',valign='vcenter',font_size=9)
    FGV=_f(bg_color='#E3F2FD',font_color='#37474F',border=1,align='right',valign='vcenter',font_size=9,num_format='#,##0.00')
    FBL=_f(bold=True,bg_color='#E8F5E9',font_color='#2E7D32',border=1,align='left',valign='vcenter',font_size=9)
    FBV=_f(bg_color='#E8F5E9',font_color='#37474F',border=1,align='right',valign='vcenter',font_size=9,num_format='#,##0.00')
    FDL=_f(bold=True,bg_color='#FFF9C4',font_color='#37474F',border=1,align='left',valign='vcenter',font_size=9)
    FPV=_f(bold=True,bg_color='#DCEDC8',font_color='#2E7D32',border=1,align='right',valign='vcenter',font_size=9,num_format='#,##0.00')
    FNV=_f(bold=True,bg_color='#FFCDD2',font_color='#C62828',border=1,align='right',valign='vcenter',font_size=9,num_format='#,##0.00')
    FZV=_f(bold=True,bg_color='#FFF9C4',font_color='#757575',border=1,align='right',valign='vcenter',font_size=9,num_format='#,##0.00')
    FEB=_f(bold=True,bg_color='#546E7A',font_color='white',border=1,align='left',valign='vcenter',font_size=9)
    FEH=_f(bold=True,bg_color='#546E7A',font_color='white',border=1,align='center',valign='vcenter',font_size=8)
    FEF=_f(bold=True,border=1,align='left',valign='vcenter',font_size=9)
    FEG=_f(bg_color='#E3F2FD',font_color='#1565C0',border=1,align='right',valign='vcenter',font_size=9,num_format='#,##0.00')
    FEB2=_f(bg_color='#E8F5E9',font_color='#2E7D32',border=1,align='right',valign='vcenter',font_size=9,num_format='#,##0.00')
    FOP=_f(bold=True,border=1,align='center',valign='vcenter',font_size=11)
    FEP=_f(bold=True,bg_color='#DCEDC8',font_color='#2E7D32',border=1,align='right',valign='vcenter',font_size=9,num_format='#,##0.00')
    FEN=_f(bold=True,bg_color='#FFCDD2',font_color='#C62828',border=1,align='right',valign='vcenter',font_size=9,num_format='#,##0.00')
    FEZ=_f(bold=True,bg_color='#FFF9C4',font_color='#757575',border=1,align='right',valign='vcenter',font_size=9,num_format='#,##0.00')
    FSP=_f(bg_color='#DCEDC8',font_color='#2E7D32',border=1,align='center',valign='vcenter',font_size=9)
    FSN=_f(bg_color='#FFCDD2',font_color='#C62828',border=1,align='center',valign='vcenter',font_size=9)
    FSZ=_f(bg_color='#FFF9C4',font_color='#757575',border=1,align='center',valign='vcenter',font_size=9)
    FCP=_f(bold=True,bg_color='#DCEDC8',font_color='#2E7D32',border=1,align='center',valign='vcenter',font_size=9,num_format='#,##0')
    FCN=_f(bold=True,bg_color='#FFCDD2',font_color='#C62828',border=1,align='center',valign='vcenter',font_size=9,num_format='#,##0')
    FCZ=_f(bold=True,bg_color='#FFF9C4',font_color='#757575',border=1,align='center',valign='vcenter',font_size=9,num_format='#,##0')
    FCP0=_f(border=1,align='center',valign='vcenter',font_size=9,num_format='#,##0')

    def _dvf(v): return FPV if v>0.01 else FNV if v<-0.01 else FZV
    def _evf(v): return FEP if v>0.01 else FEN if v<-0.01 else FEZ
    def _svf(v): return FSP if v>0.01 else FSN if v<-0.01 else FSZ
    def _cvf(v): return FCP if v>0 else FCN if v<0 else FCZ
    def _st(v):  return '🟢 More in Portal' if v>0.01 else '🔴 ITC Risk' if v<-0.01 else '✅ Match'

    def _write_diff_block(ws, rp, label, bk_v, gst_v):
        ws.merge_range(rp,0,rp,NC-1,f'📊  {label}  —  GSTR-2B vs Books  Difference  (B − A)',FDB)
        ws.set_row(rp,22); rp+=1
        for ci,h in enumerate(['Description','Count','Taxable','IGST','CGST','SGST','CESS','Total GST','Total']):
            ws.write(rp,ci,h,FDH)
        ws.set_row(rp,20); rp+=1
        ws.write(rp,0,'GSTR-2B (B)',FGL); ws.write(rp,1,gst_v[0],FCP0)
        for ci,v in enumerate(gst_v[1:],2): ws.write(rp,ci,v,FGV)
        ws.set_row(rp,20); rp+=1
        ws.write(rp,0,'Books (A)',FBL); ws.write(rp,1,bk_v[0],FCP0)
        for ci,v in enumerate(bk_v[1:],2): ws.write(rp,ci,v,FBV)
        ws.set_row(rp,20); rp+=1
        ws.write(rp,0,'Difference (B − A)',FDL)
        dc=int(gst_v[0])-int(bk_v[0]); ws.write(rp,1,dc,_cvf(dc))
        for ci in range(2,9):
            dv=gst_v[ci-1]-bk_v[ci-1]; ws.write(rp,ci,dv,_dvf(dv))
        ws.set_row(rp,22); rp+=2
        ws.merge_range(rp,0,rp,6,'📐  Equation Detail  (GSTR-2B  −  Books  =  Difference)',FEB)
        ws.set_row(rp,18); rp+=1
        for ci,h in enumerate(['Field','GSTR-2B (B)','  −  ','Books (A)','  =  ','Difference','Status']):
            ws.write(rp,ci,h,FEH)
        ws.set_row(rp,18); rp+=1
        for fname,idx in [('Taxable',1),('IGST',2),('CGST',3),('SGST',4),('CESS',5),('Total GST',6),('Total',7)]:
            gv=gst_v[idx]; bv=bk_v[idx]; dv=gv-bv
            ws.write(rp,0,fname,FEF); ws.write(rp,1,gv,FEG); ws.write(rp,2,'−',FOP)
            ws.write(rp,3,bv,FEB2); ws.write(rp,4,'=',FOP); ws.write(rp,5,dv,_evf(dv))
            ws.write(rp,6,_st(dv),_svf(dv)); ws.set_row(rp,18); rp+=1
        return rp+1

    row_ptr=_write_diff_block(ws_sum,row_ptr,'CDNR',bk_cdnr,gst_cdnr)
    if b2b_full_df is not None and not b2b_full_df.empty:
        row_ptr=_write_diff_block(ws_sum,row_ptr,'B2B',bk_b2b,gst_b2b)
        row_ptr=_write_diff_block(ws_sum,row_ptr,'Overall (B2B + CDNR)',bk_total,gst_grand)

    ws_sum.set_column(0,0,34); ws_sum.set_column(1,1,14); ws_sum.set_column(2,8,15)

    # ── DATA SHEETS ───────────────────────────────────────────────────────────
    sheets_cfg=[
        ('All Data',              full_df,                                                 False),
        ('CDNR Matched',          full_df[s.str.contains(r'CDNR Matched$',regex=True,na=False)], False),
        ('CDNR Matched (Tax Error)',full_df[s=='CDNR Matched (Tax Error)'],                False),
        ('CDNR Mismatch',         full_df[s.str.contains('Mismatch',na=False)],           False),
        ('CDNR AI Matched',       full_df[s.str.contains('AI Matched',na=False)],         False),
        ('Not In GSTR-2B',        full_df[s.str.contains('Not in GSTR-2B',na=False)],    False),
        ('Not In Books',          full_df[s.str.contains('Not in Books',na=False)],       False),
        ('CDNR Suggestions',      full_df[s.str.contains('Suggestion',na=False)],         True),
    ]

    for sheet_name,df_sub,is_sug in sheets_cfg:
        if df_sub.empty: continue
        df_sub=df_sub.copy()
        for dc in ('Note Date_BOOKS','Note Date_GST'):
            if dc in df_sub.columns: df_sub[dc]=_safe_date(df_sub[dc])
        if is_sug:
            gb=df_sub.get('GSTIN_BOOKS',pd.Series(dtype=str))
            gg=df_sub.get('GSTIN_GST',  pd.Series(dtype=str))
            df_sub['_GSTIN_Status']=np.where(gb==gg,'✅ Same GSTIN','❌ Different GSTIN')
            use_cols=SUG_DISPLAY_COLS; use_heads=SUG_HEADERS
            bk_s,bk_e=SUG_BK_S,SUG_BK_E; gt_s,gt_e=SUG_GT_S,SUG_GT_E
            df_s2,df_e2=SUG_DF_S,SUG_DF_E; st_i=SUG_ST_I
            d_bk=SUG_DATE_BK; d_gt=SUG_DATE_GT
            sug_note='⚠️ Suggestions — Cross-GSTIN matches. Verify GSTIN Status column before accepting.'
            banner_label=f'CDNR Report :: {sheet_name} — As Per GSTR-2B [B] (Details)'
        else:
            use_cols=DISPLAY_COLS; use_heads=HEADERS
            bk_s,bk_e=BK_S,BK_E; gt_s,gt_e=GT_S,GT_E
            df_s2,df_e2=DF_S,DF_E; st_i=ST_I
            d_bk=DATE_BK; d_gt=DATE_GT
            sug_note=None; banner_label=f'CDNR Report :: {sheet_name}'
        for c in use_cols:
            if c not in df_sub.columns: df_sub[c]=np.nan
        df_export=df_sub[use_cols].copy(); df_export.columns=use_heads
        df_export.to_excel(writer,sheet_name=sheet_name,startrow=7,header=False,index=False)
        ws=writer.sheets[sheet_name]
        _meta(ws,banner_label,len(use_heads)-1)
        ws.freeze_panes(7,5)
        if sug_note:
            ws.merge_range(5,0,5,len(use_heads)-1,sug_note,
                           _f(bold=True,bg_color='#FFC7CE',font_color='#9C0006',border=1,align='left',valign='vcenter'))
        if not is_sug:
            ws.merge_range(5,bk_s,5,bk_e,'As Per Books (CDNR) [A]',FMT['orange'])
            ws.merge_range(5,gt_s,5,gt_e,'As Per GSTR-2B (CDNR) [B]',FMT['green'])
            ws.merge_range(5,df_s2,5,df_e2,'Difference [A-B]',FMT['gray'])
        for ci,h in enumerate(use_heads):
            ws.write(6,ci,h,FMT['orange'] if bk_s<=ci<=bk_e else FMT['green'] if gt_s<=ci<=gt_e else FMT['gray'] if df_s2<=ci<=df_e2 else FMT['yellow'] if ci==st_i else FMT['blue'])
        ws.set_column(d_bk,d_bk,12,FMT['date']); ws.set_column(d_gt,d_gt,12,FMT['date'])
        ws.set_column(0,0,20); ws.set_column(1,1,22); ws.set_column(2,2,18)
        ws.set_column(4,4,8); ws.set_column(5,8,11); ws.set_column(gt_s,gt_s,20)
        if is_sug:
            ws.set_column(10,10,22); ws.set_column(11,11,16); ws.set_column(12,12,18)
            ws.set_column(14,14,8); ws.set_column(15,18,11)
            ws.set_column(SUG_DF_S,SUG_DF_E,12); ws.set_column(SUG_ST_I,SUG_ST_I,30); ws.set_column(SUG_ML_I,SUG_ML_I,22)
        else:
            ws.set_column(10,10,18); ws.set_column(12,12,8); ws.set_column(13,16,11)
            ws.set_column(DF_S,DF_E,12); ws.set_column(ST_I,ST_I,30); ws.set_column(ML_I,ML_I,22)

    writer.close()
    return output.getvalue()
