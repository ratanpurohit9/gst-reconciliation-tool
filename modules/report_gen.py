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
    issue_mask = full_df['Recon_Status'].str.contains('Not in|Mismatch', na=False)
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
                export_df.to_excel(writer,index=False,startrow=1,sheet_name='Discrepancy Report')
                wb=writer.book; ws=writer.sheets['Discrepancy Report']
                fg=wb.add_format({'bold':True,'bg_color':'#70AD47','font_color':'white','border':1,'align':'center'})
                fb=wb.add_format({'bold':True,'bg_color':'#ED7D31','font_color':'white','border':1,'align':'center'})
                fd=wb.add_format({'bold':True,'bg_color':'#4472C4','font_color':'white','border':1,'align':'center'})
                for cn,v in enumerate(list(export_df.columns)):
                    ws.write(1,cn,v,fg if "Portal" in v else fb if "Books" in v else fd)
                ws.merge_range('C1:H1',"UPLOADED BY YOU (GSTR-1)",fg)
                ws.merge_range('I1:N1',"CORRECT RECORD (OUR BOOKS)",fb)
                ws.set_column(0,1,20); ws.set_column(2,14,12)
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

    # BOOKS
    ws_exec.set_row(6,22); ws_exec.merge_range(6,0,6,8,'  BOOKS  (Purchase Register)',FBK_T)
    for row,l1,l2,vals in [(7,'Books','B2B',bk_b2b),(8,'','CDNR',bk_cdnr)]:
        ws_exec.set_row(row,20)
        ws_exec.write(row,0,l1,FBK_L); ws_exec.write(row,1,l2,FBK_L)
        for ci,v in enumerate(vals[1:],2): ws_exec.write(row,ci,v,FBK_V)
    ws_exec.set_row(9,22)
    ws_exec.write(9,0,'TOTAL BOOKS',FBK_TL); ws_exec.write(9,1,'',FBK_TL)
    for ci,v in enumerate(bk_total[1:],2): ws_exec.write(9,ci,v,FBK_TV)

    # GSTR-2B
    ws_exec.set_row(10,6); ws_exec.set_row(11,22)
    ws_exec.merge_range(11,0,11,8,'  GSTR-2B  (Portal Data)',FGT_T)
    for row,l1,l2,vals,amend in [(12,'GSTR-2B','B2B',gst_b2b,False),(13,'','B2BA',b2ba_row,True),
                                  (14,'','CDNR',gst_cdnr,False),(15,'','CDNRA',cdnra_row,True)]:
        ws_exec.set_row(row,20)
        ws_exec.write(row,0,l1,FGT_L); ws_exec.write(row,1,l2,FGT_L)
        for ci,v in enumerate(vals[1:],2):
            ws_exec.write(row,ci,'—' if amend and v==0 else v, FGT_NA if amend and v==0 else FGT_V)
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

    # ── RECO SUMMARY ─────────────────────────────────────────────────────────
    ws_sum = wb.add_worksheet('Reco Summary')
    ws_sum.write(0,4,'GSTIN:',fmt_bold);     ws_sum.write(0,5,company_gstin)
    ws_sum.write(1,4,'Trade Name:',fmt_bold);ws_sum.write(1,5,company_name)
    ws_sum.write(2,4,'F.Y.',fmt_bold);       ws_sum.write(2,5,fy)
    ws_sum.write(3,4,'Period:',fmt_bold);    ws_sum.write(3,5,period)

    FST=_f(bold=True,bg_color='#1F3864',font_color='white',align='center',valign='vcenter',font_size=12,border=1)
    FSH=_f(bold=True,bg_color='#4472C4',font_color='white',border=1,align='center',valign='vcenter',text_wrap=True)
    FSY=_f(bold=True,bg_color='#FFD966',border=1,align='left',valign='vcenter')
    FSL=_f(bg_color='#F2F2F2',border=1,align='left',valign='vcenter')
    FSV=_f(border=1,align='right',valign='vcenter',num_format='#,##0.00')
    FSC=_f(border=1,align='center',valign='vcenter',num_format='#,##0')

    SUM_COLS=['Description','No of Invoices','Taxable Value','IGST','CGST','SGST','CESS','Total GST','Total Invoice Value']
    NC=len(SUM_COLS)

    def _r8(df_s, use_books=True):
        sx='_BOOKS' if use_books else '_GST'
        tv=_money(df_s,'Taxable Value'+sx); ig=_money(df_s,'IGST'+sx)
        cg=_money(df_s,'CGST'+sx); sg=_money(df_s,'SGST'+sx); tg=ig+cg+sg
        return [len(df_s),tv,ig,cg,sg,0.0,tg,tv+tg]

    def _bsub(pat):
        try:    return full_df[full_df['Recon_Status'].str.contains(pat,na=False)]
        except: return full_df.iloc[0:0]

    def _block(ws, rp, title, specs):
        ws.merge_range(rp,0,rp,NC-1,title,FST); rp+=1
        for ci,h in enumerate(SUM_COLS): ws.write(rp,ci,h,FSH)
        rp+=1
        for i,(desc,vals) in enumerate(specs):
            ws.write(rp,0,desc,FSY if i==0 else FSL)
            ws.write(rp,1,vals[0],FSC)
            for ci,v in enumerate(vals[1:],2): ws.write(rp,ci,v,FSV)
            rp+=1
        return rp+1

    bkdf  = full_df[full_df['Taxable Value_BOOKS'].notna()] if 'Taxable Value_BOOKS' in full_df.columns else full_df.iloc[0:0]
    gstdf = full_df[full_df['Taxable Value_GST'].notna()]   if 'Taxable Value_GST'   in full_df.columns else full_df.iloc[0:0]
    b2b_specs=[
        ('Total Invoices As Per Books',   _r8(bkdf)),
        ('Total Invoices As Per GSTR-2B', _r8(gstdf,False)),
        ('Total Matched Invoices',        _r8(_bsub('Matched'))),
        ('Total AI-Matched Invoices',     _r8(_bsub('AI'))),
        ('Total MisMatched Invoices',     _r8(_bsub('Mismatch'))),
        ('Total MisMatched POS',          _r8(_bsub('POS'))),
        ('Total MisMatched RCM',          _r8(_bsub('RCM'))),
        ('Total Invoices Not In Books',   _r8(_bsub('Not in.*Books'),False)),
        ('Total Invoices Not In GSTR-2B', _r8(_bsub('Not in GSTR-2B'))),
    ]
    row_ptr=_block(ws_sum,5,'B2B Reconciliation Report',b2b_specs)

    if cdnr_df is not None and not cdnr_df.empty and 'Recon_Status_CDNR' in cdnr_df.columns:
        cs=cdnr_df['Recon_Status_CDNR']
        def _cr8(df_s,use_books=True):
            sx='_BOOKS' if use_books else '_GST'
            tv=_money(df_s,'Taxable Value'+sx); ig=_money(df_s,'IGST'+sx)
            cg=_money(df_s,'CGST'+sx); sg=_money(df_s,'SGST'+sx); tg=ig+cg+sg
            return [len(df_s),tv,ig,cg,sg,0.0,tg,tv+tg]
        def _cs(pat):
            try:    return cdnr_df[cs.str.contains(pat,na=False)]
            except: return cdnr_df.iloc[0:0]
        cdnr_bkdf  = cdnr_df[cdnr_df['Taxable Value_BOOKS'].notna()] if 'Taxable Value_BOOKS' in cdnr_df.columns else cdnr_df.iloc[0:0]
        cdnr_gstdf = cdnr_df[cdnr_df['Taxable Value_GST'].notna()]   if 'Taxable Value_GST'   in cdnr_df.columns else cdnr_df.iloc[0:0]
        cdnr_specs=[
            ('Total Invoice As Per Books',    _cr8(cdnr_bkdf)),
            ('Total Invoices As Per GSTR-2B', _cr8(cdnr_gstdf,False)),
            ('Total Matched Invoices',        _cr8(_cs(r'CDNR Matched$'))),
            ('Total AI-Matched Invoices',     _cr8(_cs('AI Matched'))),
            ('Total MisMatched Invoices',     _cr8(_cs('Mismatch'))),
            ('Total Invoices Not In Books',   _cr8(_cs('Not in Books'),False)),
            ('Total Invoices Not In GSTR-2B', _cr8(_cs('Not in GSTR-2B'))),
        ]
        row_ptr=_block(ws_sum,row_ptr,'Credit Note Reconciliation Report',cdnr_specs)

    # Risk sidebar
    n2b=full_df[full_df['Recon_Status'].str.contains('Not in GSTR-2B',na=False)]
    if not n2b.empty and 'Name of Party' in n2b.columns:
        risk=(n2b.groupby('Name of Party').size().reset_index(name='Missing Count')
               .sort_values('Missing Count',ascending=False).head(5))
        ws_sum.write(7,NC+1,'🚨 Top 5 Non-Compliant (Not in 2B)',fmt_red_hdr)
        ws_sum.write(8,NC+1,'Vendor Name',fmt_gray); ws_sum.write(8,NC+2,'Missing Invoices',fmt_gray)
        for ri,row in risk.iterrows():
            ws_sum.write(9+ri,NC+1,row['Name of Party']); ws_sum.write(9+ri,NC+2,row['Missing Count'])

    # ── DIFF TABLE in Reco Summary ────────────────────────────────────────────
    row_ptr+=1
    FDB=_f(bold=True,bg_color='#37474F',font_color='white',border=1,align='left',valign='vcenter',font_size=10)
    FDH=_f(bold=True,bg_color='#0D47A1',font_color='white',border=1,align='center',valign='vcenter',font_size=9)
    FGL=_f(bold=True,bg_color='#E3F2FD',font_color='#1565C0',border=1,align='left',valign='vcenter',font_size=9)
    FGV=_f(bg_color='#E3F2FD',font_color='#37474F',border=1,align='right',valign='vcenter',font_size=9,num_format='#,##0.00')
    FBL=_f(bold=True,bg_color='#E8F5E9',font_color='#2E7D32',border=1,align='left',valign='vcenter',font_size=9)
    FBV=_f(bg_color='#E8F5E9',font_color='#37474F',border=1,align='right',valign='vcenter',font_size=9,num_format='#,##0.00')
    FDL=_f(bold=True,bg_color='#FFF9C4',font_color='#37474F',border=1,align='left',valign='vcenter',font_size=9)
    FDC=_f(bold=True,bg_color='#FFF9C4',font_color='#37474F',border=1,align='center',valign='vcenter',font_size=9)
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
        # GSTR-2B row
        ws.write(rp,0,'GSTR-2B (B)',FGL); ws.write(rp,1,gst_v[0],FCP0)
        for ci,v in enumerate(gst_v[1:],2): ws.write(rp,ci,v,FGV)
        ws.set_row(rp,20); rp+=1
        # Books row
        ws.write(rp,0,'Books (A)',FBL); ws.write(rp,1,bk_v[0],FCP0)
        for ci,v in enumerate(bk_v[1:],2): ws.write(rp,ci,v,FBV)
        ws.set_row(rp,20); rp+=1
        # Diff row
        ws.write(rp,0,'Difference (B − A)',FDL)
        dc=int(gst_v[0])-int(bk_v[0]); ws.write(rp,1,dc,_cvf(dc))
        for ci in range(2,9):
            dv=gst_v[ci-1]-bk_v[ci-1]; ws.write(rp,ci,dv,_dvf(dv))
        ws.set_row(rp,22); rp+=2
        # Equation table
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

    row_ptr=_write_diff_block(ws_sum,row_ptr,'B2B',bk_b2b,gst_b2b)
    if cdnr_df is not None and not cdnr_df.empty:
        row_ptr=_write_diff_block(ws_sum,row_ptr,'CDNR',bk_cdnr,gst_cdnr)
        row_ptr=_write_diff_block(ws_sum,row_ptr,'Overall (B2B + CDNR)',bk_total,gst_grand)

    ws_sum.set_column(0,0,34); ws_sum.set_column(1,1,14); ws_sum.set_column(2,8,15)

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
