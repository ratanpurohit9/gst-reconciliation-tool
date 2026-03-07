# modules/pdf_gen.py  — Professional GST Notice Generator (v2)
# Handles ALL Recon_Status types with tailored messaging + boxed table layout

import io
import pandas as pd
from datetime import date

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, KeepTogether
)

# ─── Palette ──────────────────────────────────────────────────────────────────
DARK_NAVY   = colors.HexColor("#1F3864")
MID_BLUE    = colors.HexColor("#2E75B6")
LIGHT_BLUE  = colors.HexColor("#D6E4F0")
ACCENT_RED  = colors.HexColor("#C00000")
ACCENT_GOLD = colors.HexColor("#B8860B")
ACCENT_GRN  = colors.HexColor("#1E6B3C")
BG_GRAY     = colors.HexColor("#F5F7FA")
BG_WARN     = colors.HexColor("#FFF2F2")
BG_INFO     = colors.HexColor("#EBF3FB")
WHITE       = colors.white
TEXT_DARK   = colors.HexColor("#1A1A2E")

STATUS_CONFIG = {
    "Invoices Not in GSTR-2B": {
        "label":  "MISSING FROM GSTR-2B PORTAL",
        "color":  ACCENT_RED,
        "bg":     BG_WARN,
        "icon":   "!",
        "desc":   "Invoice recorded in our Purchase Books is NOT reflecting in GSTR-2B. This directly blocks our ITC claim under Section 16(2)(aa) of the CGST Act, 2017.",
        "action": "Kindly upload this invoice in your GSTR-1 at the earliest and confirm once done.",
    },
    "Invoices Not in Purchase Books": {
        "label":  "UNIDENTIFIED PORTAL ENTRY",
        "color":  ACCENT_GOLD,
        "bg":     colors.HexColor("#FFFBEA"),
        "icon":   "?",
        "desc":   "Invoice is reflecting in GSTR-2B (Portal) but is NOT found in our Purchase Register. This is an unreconciled entry requiring verification.",
        "action": "Please provide proof of delivery / invoice copy. If uploaded in error, issue a Credit Note immediately.",
    },
    "AI Matched (Date Mismatch)": {
        "label":  "DATE MISMATCH",
        "color":  MID_BLUE,
        "bg":     BG_INFO,
        "icon":   "~",
        "desc":   "Invoice matched by value but the Invoice Date differs between your GSTR-1 filing and our Purchase Records.",
        "action": "Please amend the invoice date in your GSTR-1 to match our Purchase Records.",
    },
    "AI Matched (Invoice Mismatch)": {
        "label":  "INVOICE NUMBER MISMATCH",
        "color":  MID_BLUE,
        "bg":     BG_INFO,
        "icon":   "~",
        "desc":   "Invoice matched by value & date but the Invoice Number differs between your filing and our records.",
        "action": "Please amend the invoice number in your GSTR-1 to match our Purchase Records.",
    },
    "AI Matched (Mismatch)": {
        "label":  "VALUE MISMATCH",
        "color":  ACCENT_RED,
        "bg":     BG_WARN,
        "icon":   "!",
        "desc":   "Invoice identified but taxable value / tax amounts do not match between GSTR-1 and our Purchase Books.",
        "action": "Please amend the taxable value and tax amounts in your GSTR-1 to match our records.",
    },
    "Matched (Tax Error)": {
        "label":  "TAX AMOUNT ERROR",
        "color":  ACCENT_GOLD,
        "bg":     colors.HexColor("#FFFBEA"),
        "icon":   "!",
        "desc":   "Taxable value matches but IGST/CGST/SGST amounts show a discrepancy. This may cause ITC mismatch.",
        "action": "Please verify and correct the tax breakup (IGST/CGST/SGST) in your GSTR-1 filing.",
    },
    "Suggestion": {
        "label":  "POSSIBLE MATCH - VERIFICATION NEEDED",
        "color":  MID_BLUE,
        "bg":     BG_INFO,
        "icon":   "~",
        "desc":   "Our system has identified a possible match but it requires manual verification due to partial data alignment.",
        "action": "Please review and confirm whether this invoice matches your records. Amend if required.",
    },
    "Suggestion (Group Match)": {
        "label":  "GROUP MATCH SUGGESTION",
        "color":  MID_BLUE,
        "bg":     BG_INFO,
        "icon":   "~",
        "desc":   "A group of invoices may collectively match a consolidated entry. Manual confirmation is needed.",
        "action": "Please verify these entries match your filing and confirm or amend accordingly.",
    },
    "Manually Linked": {
        "label":  "MANUALLY LINKED - PLEASE VERIFY",
        "color":  ACCENT_GRN,
        "bg":     colors.HexColor("#F0FFF4"),
        "icon":   "V",
        "desc":   "This invoice was manually linked during reconciliation. Please confirm values match your GSTR-1 filing.",
        "action": "Kindly verify the details and amend your GSTR-1 if any discrepancy is found.",
    },
    "DEFAULT": {
        "label":  "DISCREPANCY NOTED",
        "color":  ACCENT_RED,
        "bg":     BG_WARN,
        "icon":   "!",
        "desc":   "A discrepancy has been identified during GST reconciliation for this invoice.",
        "action": "Please review and take corrective action at the earliest.",
    },
}

def get_status_config(status):
    for key in STATUS_CONFIG:
        if key != "DEFAULT" and key in str(status):
            return STATUS_CONFIG[key]
    return STATUS_CONFIG["DEFAULT"]

def fc(val, show_zero=False, abs_val=False):
    """Format currency with Indian number system and rupee symbol"""
    if val is None or val == '':
        return "-"
    try:
        if isinstance(val, float) and pd.isna(val):
            return "-"
        f = float(val)
        if abs_val:
            f = abs(f)
        if f == 0 and not show_zero:
            return "-"
        # Indian number format: 1,00,000.00
        neg = f < 0
        f = abs(f)
        s = f"{f:,.2f}"
        parts = s.split('.')
        n = parts[0].replace(',', '')
        if len(n) > 3:
            last3 = n[-3:]
            rest = n[:-3]
            grps = []
            while len(rest) > 2:
                grps.append(rest[-2:])
                rest = rest[:-2]
            if rest:
                grps.append(rest)
            grps.reverse()
            n = ','.join(grps) + ',' + last3
        result = f"\u20b9{n}.{parts[1]}"
        return f"-{result}" if neg else result
    except:
        return "-"

def fd(val):
    try:
        return pd.to_datetime(val).strftime('%d-%m-%Y')
    except:
        s = str(val) if pd.notna(val) else ''
        return s.split(' ')[0] if s and s != 'nan' else '-'

def S(name, **kwargs):
    defaults = {
        "title":     dict(fontName="Helvetica-Bold", fontSize=12, textColor=WHITE, alignment=TA_CENTER),
        "subtitle":  dict(fontName="Helvetica", fontSize=8, textColor=colors.HexColor("#AACCEE"), alignment=TA_CENTER),
        "body":      dict(fontName="Helvetica", fontSize=9, textColor=TEXT_DARK, leading=14),
        "bold":      dict(fontName="Helvetica-Bold", fontSize=9, textColor=TEXT_DARK, leading=14),
        "small":     dict(fontName="Helvetica", fontSize=7.5, textColor=colors.HexColor("#555555")),
        "tbl_hdr":   dict(fontName="Helvetica-Bold", fontSize=8, textColor=WHITE, alignment=TA_CENTER),
        "tbl_cell":  dict(fontName="Helvetica", fontSize=8, textColor=TEXT_DARK),
        "tbl_num":   dict(fontName="Helvetica", fontSize=8, textColor=TEXT_DARK, alignment=TA_RIGHT),
        "tbl_bold":  dict(fontName="Helvetica-Bold", fontSize=8, textColor=DARK_NAVY, alignment=TA_RIGHT),
        "lbl_stat":  dict(fontName="Helvetica", fontSize=7, textColor=colors.HexColor("#555555")),
        "val_stat":  dict(fontName="Helvetica-Bold", fontSize=10, textColor=DARK_NAVY),
    }
    kw = {**defaults.get(name, {}), **kwargs}
    return ParagraphStyle(name, **kw)


def _header_table(company_name, gstin, today, W):
    left  = [[Paragraph(company_name.upper(), S("title"))],
              [Paragraph(f"GSTIN: {gstin}", S("subtitle"))]]
    right = [[Paragraph("GST RECONCILIATION NOTICE", S("title"))],
              [Paragraph(f"Date: {today}", S("subtitle"))]]

    lt = Table(left,  colWidths=[W * 0.55])
    rt = Table(right, colWidths=[W * 0.45])
    for t in [lt, rt]:
        t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),DARK_NAVY),
                                ('TOPPADDING',(0,0),(-1,-1),2),('BOTTOMPADDING',(0,0),(-1,-1),2),
                                ('LEFTPADDING',(0,0),(-1,-1),8),('RIGHTPADDING',(0,0),(-1,-1),8)]))
    rt.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),DARK_NAVY),('ALIGN',(0,0),(-1,-1),'RIGHT'),
                              ('TOPPADDING',(0,0),(-1,-1),2),('BOTTOMPADDING',(0,0),(-1,-1),2),
                              ('LEFTPADDING',(0,0),(-1,-1),8),('RIGHTPADDING',(0,0),(-1,-1),8)]))

    outer = Table([[lt, rt]], colWidths=[W * 0.55, W * 0.45])
    outer.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),DARK_NAVY),
                                ('TOPPADDING',(0,0),(-1,-1),10),('BOTTOMPADDING',(0,0),(-1,-1),10),
                                ('LEFTPADDING',(0,0),(-1,-1),0),('RIGHTPADDING',(0,0),(-1,-1),0),
                                ('VALIGN',(0,0),(-1,-1),'MIDDLE')]))
    return outer


def _to_box(vendor_name, vendor_gstin, W):
    rows = [[Paragraph("To,", S("small"))],
             [Paragraph("The Accounts / GST Department", S("bold"))],
             [Paragraph(vendor_name, ParagraphStyle("vn", fontName="Helvetica-Bold", fontSize=11, textColor=DARK_NAVY))],
             [Paragraph(f"GSTIN: {vendor_gstin}", S("small"))]]
    t = Table(rows, colWidths=[W - 16])
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),BG_INFO),
                             ('TOPPADDING',(0,0),(-1,-1),4),('BOTTOMPADDING',(0,0),(-1,-1),4),
                             ('LEFTPADDING',(0,0),(-1,-1),12),('RIGHTPADDING',(0,0),(-1,-1),8),
                             ('LINEBEFORE',(0,0),(0,-1),4,MID_BLUE),
                             ('BOX',(0,0),(-1,-1),0.5,MID_BLUE)]))
    return t


def _summary_box(inv_count, tot_tax, tot_igst, tot_cgst, tot_sgst, status_counts, W):
    total_tax = tot_igst + tot_cgst + tot_sgst

    # Row 1: 3 stat cells
    def stat_cell(lbl, val, vc=DARK_NAVY, cw=0):
        t = Table([[Paragraph(lbl, S("lbl_stat"))],[Paragraph(val, ParagraphStyle("sv",fontName="Helvetica-Bold",fontSize=11,textColor=vc))]],
                  colWidths=[cw or (W/3 - 8)])
        t.setStyle(TableStyle([('TOPPADDING',(0,0),(-1,-1),4),('BOTTOMPADDING',(0,0),(-1,-1),4),
                                ('LEFTPADDING',(0,0),(-1,-1),6),('RIGHTPADDING',(0,0),(-1,-1),6)]))
        return t

    cw3 = W / 3
    row1 = [[stat_cell("Total Invoices", str(inv_count), MID_BLUE, cw3-8),
              stat_cell("Total Taxable Value", fc(tot_tax, show_zero=True), DARK_NAVY, cw3-8),
              stat_cell("Total Tax (IGST+CGST+SGST)", fc(total_tax, show_zero=True), ACCENT_RED, cw3-8)]]

    t1 = Table(row1, colWidths=[cw3]*3)
    t1.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),BG_GRAY),
                              ('LINEAFTER',(0,0),(1,0),0.5,colors.HexColor("#CCCCCC")),
                              ('TOPPADDING',(0,0),(-1,-1),8),('BOTTOMPADDING',(0,0),(-1,-1),8),
                              ('LEFTPADDING',(0,0),(-1,-1),0),('RIGHTPADDING',(0,0),(-1,-1),0),
                              ('VALIGN',(0,0),(-1,-1),'MIDDLE')]))

    # Row 2: Issue breakdown chips
    STATUS_LABELS = {
        "Invoices Not in GSTR-2B":        ("NOT IN 2B",    ACCENT_RED),
        "Invoices Not in Purchase Books":  ("NOT IN BOOKS", ACCENT_GOLD),
        "AI Matched (Mismatch)":           ("VALUE MISMATCH", ACCENT_RED),
        "AI Matched (Date Mismatch)":      ("DATE MISMATCH",  MID_BLUE),
        "AI Matched (Invoice Mismatch)":   ("INV NO. MISMATCH",MID_BLUE),
        "Matched (Tax Error)":             ("TAX ERROR",    ACCENT_GOLD),
        "Suggestion":                      ("SUGGESTION",   MID_BLUE),
        "Suggestion (Group Match)":        ("GROUP MATCH",  MID_BLUE),
        "Manually Linked":                 ("MANUAL LINK",  ACCENT_GRN),
    }
    chips = []
    for st, cnt in status_counts.items():
        lbl, clr = STATUS_LABELS.get(st, (st[:12].upper(), MID_BLUE))
        chip_t = Table([[Paragraph(f"{cnt}x {lbl}",
                          ParagraphStyle("chip",fontName="Helvetica-Bold",fontSize=7.5,textColor=WHITE,alignment=TA_CENTER))]],
                        colWidths=[max(60, len(lbl)*5.5 + 20)])
        chip_t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),clr),
                                     ('TOPPADDING',(0,0),(-1,-1),4),('BOTTOMPADDING',(0,0),(-1,-1),4),
                                     ('LEFTPADDING',(0,0),(-1,-1),6),('RIGHTPADDING',(0,0),(-1,-1),6),
                                     ('ROUNDEDCORNERS',[4,4,4,4])]))
        chips.append(chip_t)
    # Pad to fill row
    chip_row = chips + [Paragraph("",S("small"))] * max(0, 6-len(chips))
    chip_data = [chip_row[:6]]
    t2 = Table(chip_data, colWidths=[W/6]*6)
    t2.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),WHITE),
                              ('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6),
                              ('LEFTPADDING',(0,0),(-1,-1),6),('RIGHTPADDING',(0,0),(-1,-1),6),
                              ('VALIGN',(0,0),(-1,-1),'MIDDLE')]))

    outer = Table([[t1],[t2]], colWidths=[W])
    outer.setStyle(TableStyle([('BOX',(0,0),(-1,-1),0.8,MID_BLUE),
                                ('LINEBELOW',(0,0),(-1,0),0.5,colors.HexColor("#CCCCCC")),
                                ('LEFTPADDING',(0,0),(-1,-1),0),('RIGHTPADDING',(0,0),(-1,-1),0),
                                ('TOPPADDING',(0,0),(-1,-1),0),('BOTTOMPADDING',(0,0),(-1,-1),0)]))
    return outer


def _invoice_table(rows_data, status, W):
    cfg      = get_status_config(status)
    has_both = any(r.get('has_gst') for r in rows_data)

    if has_both:
        headers = ["Sr.","Inv No.","Date","Books Taxable","Books Tax","Portal Taxable","Portal Tax","Diff"]
        cw_list = [20,55,48,72,62,72,62,62]
    else:
        headers = ["Sr.","Inv No.","Date","Taxable (Rs.)","IGST (Rs.)","CGST (Rs.)","SGST (Rs.)","Total (Rs.)"]
        cw_list = [20,58,52,76,62,62,62,61]

    scale = (W - 2) / sum(cw_list)
    cw_list = [c * scale for c in cw_list]

    hdr_row  = [Paragraph(h, S("tbl_hdr")) for h in headers]
    tbl_data = [hdr_row]

    tot_taxable=tot_igst=tot_cgst=tot_sgst=0.0
    tot_gtax=tot_gigst=tot_gcgst=tot_gsgst=0.0

    for i, r in enumerate(rows_data):
        tb=float(r.get('taxable',0) or 0); ib=float(r.get('igst',0) or 0)
        cb=float(r.get('cgst',0) or 0);   sb=float(r.get('sgst',0) or 0)
        tg=float(r.get('gst_taxable',0) or 0); ig=float(r.get('gst_igst',0) or 0)
        cg=float(r.get('gst_cgst',0) or 0);    sg=float(r.get('gst_sgst',0) or 0)
        tot_taxable+=tb; tot_igst+=ib; tot_cgst+=cb; tot_sgst+=sb
        tot_gtax+=tg; tot_gigst+=ig; tot_gcgst+=cg; tot_gsgst+=sg
        btax=ib+cb+sb; gtax=ig+cg+sg; diff=(tb+btax)-(tg+gtax)

        if has_both:
            if tb == 0 and tg > 0:
                # Not in Books: show portal total, diff = "EXTRA"
                diff_txt  = "EXTRA"
                diff_clr  = ACCENT_GOLD
            elif tg == 0 and tb > 0:
                # Not in 2B: show "-" for diff
                diff_txt  = "-"
                diff_clr  = ACCENT_RED
            elif abs(diff) < 0.5:
                diff_txt  = "-"
                diff_clr  = ACCENT_GRN
            else:
                diff_txt  = fc(diff, abs_val=True)
                diff_clr  = ACCENT_RED
            diff_style = ParagraphStyle("df",fontName="Helvetica-Bold",fontSize=8,textColor=diff_clr,alignment=TA_RIGHT)
            row=[Paragraph(str(i+1),S("tbl_cell")), Paragraph(str(r.get('inv_no','—')),S("tbl_cell")),
                 Paragraph(str(r.get('date','—')),S("tbl_cell")),
                 Paragraph(fc(tb) if tb else "-",S("tbl_num")), Paragraph(fc(btax) if btax else "-",S("tbl_num")),
                 Paragraph(fc(tg) if tg else "-",S("tbl_num")), Paragraph(fc(gtax) if gtax else "-",S("tbl_num")),
                 Paragraph(diff_txt, diff_style)]
        else:
            row=[Paragraph(str(i+1),S("tbl_cell")), Paragraph(str(r.get('inv_no','—')),S("tbl_cell")),
                 Paragraph(str(r.get('date','—')),S("tbl_cell")),
                 Paragraph(fc(tb),S("tbl_num")), Paragraph(fc(ib),S("tbl_num")),
                 Paragraph(fc(cb),S("tbl_num")), Paragraph(fc(sb),S("tbl_num")),
                 Paragraph(fc(tb+ib+cb+sb),S("tbl_bold"))]
        tbl_data.append(row)

    # Total row
    if has_both:
        tot_row=[Paragraph("",S("tbl_hdr")),Paragraph("TOTAL",S("tbl_hdr")),
                 Paragraph(f"{len(rows_data)} inv.",S("tbl_hdr")),
                 Paragraph(fc(tot_taxable),S("tbl_bold")), Paragraph(fc(tot_igst+tot_cgst+tot_sgst),S("tbl_bold")),
                 Paragraph(fc(tot_gtax),S("tbl_bold")), Paragraph(fc(tot_gigst+tot_gcgst+tot_gsgst),S("tbl_bold")),
                 Paragraph("",S("tbl_hdr"))]
    else:
        tot_row=[Paragraph("",S("tbl_hdr")),Paragraph("TOTAL",S("tbl_hdr")),
                 Paragraph(f"{len(rows_data)} inv.",S("tbl_hdr")),
                 Paragraph(fc(tot_taxable),S("tbl_bold")), Paragraph(fc(tot_igst),S("tbl_bold")),
                 Paragraph(fc(tot_cgst),S("tbl_bold")), Paragraph(fc(tot_sgst),S("tbl_bold")),
                 Paragraph(fc(tot_taxable+tot_igst+tot_cgst+tot_sgst),S("tbl_bold"))]
    tbl_data.append(tot_row)

    n=len(tbl_data)
    style=TableStyle([
        ('BACKGROUND',(0,0),(-1,0),DARK_NAVY),
        ('TEXTCOLOR',(0,0),(-1,0),WHITE),
        ('ALIGN',(0,0),(-1,0),'CENTER'),
        ('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),
        ('FONTSIZE',(0,0),(-1,0),8),
        ('TOPPADDING',(0,0),(-1,0),6),('BOTTOMPADDING',(0,0),(-1,0),6),
        ('FONTNAME',(0,1),(-1,n-2),'Helvetica'),
        ('FONTSIZE',(0,1),(-1,n-2),8),
        ('TOPPADDING',(0,1),(-1,n-2),4),('BOTTOMPADDING',(0,1),(-1,n-2),4),
        ('LEFTPADDING',(0,0),(-1,-1),4),('RIGHTPADDING',(0,0),(-1,-1),4),
        *[('BACKGROUND',(0,r),(-1,r),BG_GRAY) for r in range(2,n-1,2)],
        ('BACKGROUND',(0,n-1),(-1,n-1),LIGHT_BLUE),
        ('FONTNAME',(0,n-1),(-1,n-1),'Helvetica-Bold'),
        ('FONTSIZE',(0,n-1),(-1,n-1),8),
        ('TOPPADDING',(0,n-1),(-1,n-1),6),('BOTTOMPADDING',(0,n-1),(-1,n-1),6),
        ('GRID',(0,0),(-1,-1),0.5,colors.HexColor("#AAAAAA")),
        ('BOX',(0,0),(-1,-1),1.2,MID_BLUE),
        ('VALIGN',(0,0),(-1,-1),'MIDDLE'),
    ])
    t=Table(tbl_data, colWidths=cw_list, repeatRows=1)
    t.setStyle(style)
    return t


def _section(status, rows_data, W):
    cfg=get_status_config(status)
    elems=[]

    badge_data=[[Paragraph(f"  [{cfg['icon']}]  {cfg['label']}",
                            ParagraphStyle("bh",fontName="Helvetica-Bold",fontSize=9,textColor=WHITE)),
                  Paragraph(f"{len(rows_data)} Invoice(s)",
                             ParagraphStyle("bc",fontName="Helvetica-Bold",fontSize=8,textColor=WHITE,alignment=TA_RIGHT))]]
    badge=Table(badge_data, colWidths=[W*0.75, W*0.25])
    badge.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),cfg["color"]),
                                ('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7),
                                ('LEFTPADDING',(0,0),(-1,-1),10),('RIGHTPADDING',(0,0),(-1,-1),10),
                                ('BOX',(0,0),(-1,-1),0.5,cfg["color"])]))
    elems.append(badge)
    elems.append(Spacer(1,3))
    elems.append(Paragraph(cfg["desc"], S("body")))
    elems.append(Spacer(1,4))
    elems.append(_invoice_table(rows_data, status, W))
    elems.append(Spacer(1,6))

    # Action box
    act_rows=[[Paragraph("Action Required:", ParagraphStyle("ar",fontName="Helvetica-Bold",fontSize=9,textColor=cfg["color"]))],
               [Paragraph(cfg["action"], S("body"))],
               [Paragraph("Note: Delayed action may result in ITC reversal and interest liability at our end.", S("small"))]]
    act=Table(act_rows, colWidths=[W-16])
    act.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),cfg["bg"]),
                               ('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5),
                               ('LEFTPADDING',(0,0),(-1,-1),10),('RIGHTPADDING',(0,0),(-1,-1),8),
                               ('LINEBEFORE',(0,0),(0,-1),4,cfg["color"]),
                               ('LINEABOVE',(0,0),(-1,0),0.5,cfg["color"]),
                               ('LINEBELOW',(0,-1),(-1,-1),0.5,cfg["color"])]))
    elems.append(act)
    elems.append(Spacer(1,14))
    return elems


def create_vendor_pdf(df, vendor_name, company_name, gst_in_company):
    buffer=io.BytesIO()
    doc=SimpleDocTemplate(buffer, pagesize=A4,
                           leftMargin=18*mm, rightMargin=18*mm,
                           topMargin=14*mm, bottomMargin=14*mm)
    W=A4[0]-36*mm
    today=date.today().strftime('%d-%m-%Y')

    issue_mask=df['Recon_Status'].str.contains('Not in|Mismatch|Suggestion|Manual|Tax Error',na=False)
    vendor_df=df[(df['Name of Party']==vendor_name)&issue_mask].copy()
    if vendor_df.empty:
        buffer.seek(0)
        return buffer

    vendor_gstin=str(vendor_df['GSTIN'].iloc[0]) if 'GSTIN' in vendor_df.columns else '-'

    # Group by status
    groups={}
    for _,row in vendor_df.iterrows():
        st=row.get('Recon_Status','DEFAULT')
        if st not in groups: groups[st]=[]
        inv_b=str(row.get('Invoice Number_BOOKS','')) if pd.notna(row.get('Invoice Number_BOOKS')) else ''
        inv_g=str(row.get('Invoice Number_GST',''))   if pd.notna(row.get('Invoice Number_GST'))   else ''
        inv_no=inv_g if inv_g and inv_g!='nan' else inv_b
        date_g=fd(row.get('Invoice Date_GST',''))
        date_b=fd(row.get('Invoice Date_BOOKS',''))
        groups[st].append({
            'inv_no':inv_no, 'date': date_g if date_g!='-' else date_b,
            'taxable':row.get('Taxable Value_BOOKS',0) or 0,
            'igst':row.get('IGST_BOOKS',0) or 0,
            'cgst':row.get('CGST_BOOKS',0) or 0,
            'sgst':row.get('SGST_BOOKS',0) or 0,
            'gst_taxable':row.get('Taxable Value_GST',0) or 0,
            'gst_igst':row.get('IGST_GST',0) or 0,
            'gst_cgst':row.get('CGST_GST',0) or 0,
            'gst_sgst':row.get('SGST_GST',0) or 0,
            'has_gst': bool(inv_g and inv_g!='nan'),
        })

    tot_tax   = sum(r['taxable'] for g in groups.values() for r in g)
    tot_igst  = sum(r['igst']    for g in groups.values() for r in g)
    tot_cgst  = sum(r['cgst']    for g in groups.values() for r in g)
    tot_sgst  = sum(r['sgst']    for g in groups.values() for r in g)
    tot_inv   = sum(len(g) for g in groups.values())
    st_counts = {k:len(v) for k,v in groups.items()}

    elements=[]
    elements.append(_header_table(company_name, gst_in_company, today, W))
    elements.append(Spacer(1,10))
    elements.append(_to_box(vendor_name, vendor_gstin, W))
    elements.append(Spacer(1,8))
    elements.append(Paragraph(
        f"<b>Subject:</b> GSTR-2B vs Purchase Books Reconciliation — Discrepancy Notice",
        S("body")))
    elements.append(Spacer(1,4))
    elements.append(Paragraph(
        f"Dear Sir / Madam,<br/>Upon reconciliation of our Purchase Register with GSTR-2B data, "
        f"we have identified <b>{tot_inv} invoice(s)</b> with discrepancies across "
        f"<b>{len(st_counts)} issue type(s)</b>. These directly impact our ITC eligibility. "
        f"Please review each section below and take prompt corrective action.",
        S("body")))
    elements.append(Spacer(1,6))
    elements.append(_summary_box(tot_inv,tot_tax,tot_igst,tot_cgst,tot_sgst,st_counts,W))
    elements.append(Spacer(1,10))
    elements.append(HRFlowable(width=W, thickness=1.5, color=MID_BLUE))
    elements.append(Spacer(1,8))

    ORDER=["Invoices Not in GSTR-2B","AI Matched (Mismatch)","Matched (Tax Error)",
            "Invoices Not in Purchase Books","AI Matched (Date Mismatch)",
            "AI Matched (Invoice Mismatch)","Suggestion (Group Match)","Suggestion","Manually Linked"]
    for st in sorted(groups.keys(), key=lambda s: ORDER.index(s) if s in ORDER else 99):
        for el in _section(st, groups[st], W):
            elements.append(el)

    elements.append(HRFlowable(width=W, thickness=1, color=colors.HexColor("#CCCCCC")))
    elements.append(Spacer(1,6))
    elements.append(Paragraph(
        "We request you to treat this matter with priority. Kindly reconcile all entries and "
        "carry out necessary amendments in your upcoming GSTR-1 filing. Please confirm in writing "
        "once all corrections have been made.", S("body")))
    elements.append(Spacer(1,16))

    # Signature
    sig_rows=[[Paragraph("Yours faithfully,",S("body"))],
               [Spacer(1,28)],
               [Paragraph("_"*35,S("body"))],
               [Paragraph("[Authorized Signatory]",S("bold"))],
               [Paragraph(company_name,S("bold"))],
               [Paragraph(f"GSTIN: {gst_in_company}",S("small"))]]
    sig=Table(sig_rows, colWidths=[W/2])
    sig.setStyle(TableStyle([('TOPPADDING',(0,0),(-1,-1),2),('BOTTOMPADDING',(0,0),(-1,-1),2),
                               ('LEFTPADDING',(0,0),(-1,-1),0),('RIGHTPADDING',(0,0),(-1,-1),0),
                               ('LINEABOVE',(0,2),(0,2),0.8,colors.HexColor("#AAAAAA"))]))
    elements.append(sig)

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont('Helvetica',7)
        canvas.setFillColor(colors.HexColor("#888888"))
        canvas.drawCentredString(A4[0]/2, 10*mm,
            f"{company_name}  |  GSTIN: {gst_in_company}  |  Page {doc.page}  |  Generated: {today}")
        canvas.restoreState()

    doc.build(elements, onFirstPage=footer, onLaterPages=footer)
    buffer.seek(0)
    return buffer
