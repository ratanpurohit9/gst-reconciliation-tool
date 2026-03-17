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
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import os as _os

# Font chain: Segoe UI (₹ native) → DejaVuSans (₹ support) → Helvetica (fallback)
_BASE_FONT = _BASE_FONT_BOLD = None
_SEGOE_REG  = 'C:/Windows/Fonts/segoeui.ttf'
_SEGOE_BOLD = 'C:/Windows/Fonts/segoeuib.ttf'
_DEJAVU_REG  = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
_DEJAVU_BOLD = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'

def _reg(name, bname, rpath, bpath):
    try:
        pdfmetrics.registerFont(TTFont(name,  rpath))
        pdfmetrics.registerFont(TTFont(bname, bpath))
        pdfmetrics.registerFontFamily(name, normal=name, bold=bname)
        return True
    except: return False

if _os.path.exists(_SEGOE_REG) and _os.path.exists(_SEGOE_BOLD):
    if _reg('SegoeUI','SegoeUI-Bold', _SEGOE_REG, _SEGOE_BOLD):
        _BASE_FONT, _BASE_FONT_BOLD = 'SegoeUI', 'SegoeUI-Bold'
if not _BASE_FONT and _os.path.exists(_DEJAVU_REG):
    if _reg('DejaVu','DejaVu-Bold', _DEJAVU_REG, _DEJAVU_BOLD):
        _BASE_FONT, _BASE_FONT_BOLD = 'DejaVu', 'DejaVu-Bold'
if not _BASE_FONT:
    _BASE_FONT, _BASE_FONT_BOLD = 'Helvetica', 'Helvetica-Bold'

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
        "desc":   "Invoice matched by value & date but the Invoice Number differs between your GSTR-1 filing and our Purchase Records. Each row shows: 📘 Our Books Inv No. (top, in blue) and 📋 Your Portal Inv No. as filed in GSTR-1 (below, in red). Please amend your GSTR-1 to use the Books invoice number.",
        "action": "Please amend the invoice number in your GSTR-1. Use the 📘 Books number (shown in blue) instead of the 📋 Portal number (shown in red) in the table above.",
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
    "Old ITC (Previous Year)": {
        "label":  "OLD ITC — PREVIOUS YEAR INVOICE",
        "color":  colors.HexColor("#5B4FCF"),
        "bg":     colors.HexColor("#F0EEFF"),
        "icon":   "Y",
        "desc":   "This invoice date falls before the current reconciliation period. It appears to be ITC of the previous financial year uploaded in GSTR-1 this year. Since this was likely recorded in the previous year's books, no action may be needed — but please verify.",
        "action": "Verify whether this invoice was already accounted for in your previous year's ITC. If yes, no action needed. If it is a new/duplicate entry, issue a Credit Note.",
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
        "title":     dict(fontName=_BASE_FONT_BOLD, fontSize=12, textColor=WHITE, alignment=TA_CENTER),
        "subtitle":  dict(fontName=_BASE_FONT, fontSize=8, textColor=colors.HexColor("#AACCEE"), alignment=TA_CENTER),
        "body":      dict(fontName=_BASE_FONT, fontSize=9, textColor=TEXT_DARK, leading=14),
        "bold":      dict(fontName=_BASE_FONT_BOLD, fontSize=9, textColor=TEXT_DARK, leading=14),
        "small":     dict(fontName=_BASE_FONT, fontSize=7.5, textColor=colors.HexColor("#555555")),
        "tbl_hdr":   dict(fontName=_BASE_FONT_BOLD, fontSize=8, textColor=WHITE, alignment=TA_CENTER),
        "tbl_cell":  dict(fontName=_BASE_FONT, fontSize=8, textColor=TEXT_DARK),
        "tbl_num":   dict(fontName=_BASE_FONT, fontSize=8, textColor=TEXT_DARK, alignment=TA_RIGHT),
        "tbl_bold":  dict(fontName=_BASE_FONT_BOLD, fontSize=8, textColor=DARK_NAVY, alignment=TA_RIGHT),
        "lbl_stat":  dict(fontName=_BASE_FONT, fontSize=7, textColor=colors.HexColor("#555555")),
        "val_stat":  dict(fontName=_BASE_FONT_BOLD, fontSize=10, textColor=DARK_NAVY),
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
             [Paragraph(vendor_name, ParagraphStyle("vn", fontName=_BASE_FONT_BOLD, fontSize=11, textColor=DARK_NAVY))],
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
        t = Table([[Paragraph(lbl, S("lbl_stat"))],[Paragraph(val, ParagraphStyle("sv",fontName=_BASE_FONT_BOLD,fontSize=11,textColor=vc))]],
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
                          ParagraphStyle("chip",fontName=_BASE_FONT_BOLD,fontSize=7.5,textColor=WHITE,alignment=TA_CENTER))]],
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
    is_inv_mismatch = 'Invoice Mismatch' in str(status)

    if is_inv_mismatch:
        # Combined cell: Sr | Inv No (Books → Portal) | Date | BooksTax | BooksTax$ | PortalTax | PortalTax$ | Diff
        headers = ["Sr.", "Invoice Numbers\n(Books → Portal)", "Date",
                   "Books\nTaxable", "Books\nTax", "Portal\nTaxable", "Portal\nTax", "Diff"]
        cw_list = [14, 90, 46, 66, 54, 66, 54, 54]
    elif has_both:
        # 8 cols: Sr | InvNo | Date | BooksTax | BooksTaxAmt | PortalTax | PortalTaxAmt | Diff
        headers = ["Sr.","Inv No.","Date","Books\nTaxable","Books\nTax","Portal\nTaxable","Portal\nTax","Diff"]
        cw_list = [16, 48, 46, 72, 60, 72, 60, 60]
    else:
        # 8 cols: Sr | InvNo | Date | Taxable | IGST | CGST | SGST | Total
        # Total must fit ₹12,99,168.50 = 14 chars at 8pt DejaVu ≈ 68pt minimum
        headers = ["Sr.","Inv No.","Date","Taxable","IGST","CGST","SGST","Total"]
        cw_list = [16, 52, 46, 76, 56, 56, 56, 80]

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

        if is_inv_mismatch:
            # Show both Books & Portal invoice numbers in one stacked cell
            inv_b_val = str(r.get('inv_b', '—'))
            inv_g_val = str(r.get('inv_g', '—'))
            combined_inv = Table([
                [Paragraph('📘 ' + inv_b_val,
                           ParagraphStyle("ib",fontName=_BASE_FONT_BOLD,fontSize=8,textColor=colors.HexColor("#1A3C6E")))],
                [Paragraph('📋 ' + inv_g_val,
                           ParagraphStyle("ig",fontName=_BASE_FONT,fontSize=7.5,textColor=colors.HexColor("#B91C1C")))],
            ], colWidths=[86])
            combined_inv.setStyle(TableStyle([
                ('TOPPADDING',(0,0),(-1,-1),1),('BOTTOMPADDING',(0,0),(-1,-1),1),
                ('LEFTPADDING',(0,0),(-1,-1),0),('RIGHTPADDING',(0,0),(-1,-1),0),
            ]))
            diff_mismatch = "-"
            diff_mismatch_clr = ACCENT_GRN
            diff_val = (tb+ib+cb+sb) - (tg+ig+cg+sg)
            if abs(diff_val) >= 0.5:
                diff_mismatch = fc(diff_val, abs_val=True)
                diff_mismatch_clr = ACCENT_RED
            diff_style_m = ParagraphStyle("dfm",fontName=_BASE_FONT_BOLD,fontSize=8,textColor=diff_mismatch_clr,alignment=TA_RIGHT)
            btax_m = ib+cb+sb; gtax_m = ig+cg+sg
            row=[Paragraph(str(i+1),S("tbl_cell")),
                 combined_inv,
                 Paragraph(str(r.get('date','—')),S("tbl_cell")),
                 Paragraph(fc(tb) if tb else "-",S("tbl_num")), Paragraph(fc(btax_m) if btax_m else "-",S("tbl_num")),
                 Paragraph(fc(tg) if tg else "-",S("tbl_num")), Paragraph(fc(gtax_m) if gtax_m else "-",S("tbl_num")),
                 Paragraph(diff_mismatch, diff_style_m)]
        elif has_both:
            if tb == 0 and tg > 0:
                diff_txt = "EXTRA"; diff_clr = ACCENT_GOLD
            elif tg == 0 and tb > 0:
                diff_txt = "-"; diff_clr = ACCENT_RED
            elif abs(diff) < 0.5:
                diff_txt = "-"; diff_clr = ACCENT_GRN
            else:
                diff_txt = fc(diff, abs_val=True); diff_clr = ACCENT_RED
            diff_style = ParagraphStyle("df",fontName=_BASE_FONT_BOLD,fontSize=8,textColor=diff_clr,alignment=TA_RIGHT)
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
    if is_inv_mismatch:
        tot_row=[Paragraph("",S("tbl_hdr")),Paragraph("TOTAL",S("tbl_hdr")),
                 Paragraph(f"{len(rows_data)} inv.",S("tbl_hdr")),
                 Paragraph(fc(tot_taxable),S("tbl_bold")), Paragraph(fc(tot_igst+tot_cgst+tot_sgst),S("tbl_bold")),
                 Paragraph(fc(tot_gtax),S("tbl_bold")), Paragraph(fc(tot_gigst+tot_gcgst+tot_gsgst),S("tbl_bold")),
                 Paragraph("",S("tbl_hdr"))]
    elif has_both:
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
        ('FONTNAME',(0,0),(-1,0),_BASE_FONT_BOLD),
        ('FONTSIZE',(0,0),(-1,0),8),
        ('TOPPADDING',(0,0),(-1,0),6),('BOTTOMPADDING',(0,0),(-1,0),6),
        ('FONTNAME',(0,1),(-1,n-2),_BASE_FONT),
        ('FONTSIZE',(0,1),(-1,n-2),8),
        ('TOPPADDING',(0,1),(-1,n-2),4),('BOTTOMPADDING',(0,1),(-1,n-2),4),
        ('LEFTPADDING',(0,0),(-1,-1),4),('RIGHTPADDING',(0,0),(-1,-1),4),
        *[('BACKGROUND',(0,r),(-1,r),BG_GRAY) for r in range(2,n-1,2)],
        ('BACKGROUND',(0,n-1),(-1,n-1),LIGHT_BLUE),
        ('FONTNAME',(0,n-1),(-1,n-1),_BASE_FONT_BOLD),
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
                            ParagraphStyle("bh",fontName=_BASE_FONT_BOLD,fontSize=9,textColor=WHITE)),
                  Paragraph(f"{len(rows_data)} Invoice(s)",
                             ParagraphStyle("bc",fontName=_BASE_FONT_BOLD,fontSize=8,textColor=WHITE,alignment=TA_RIGHT))]]
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
    act_rows=[[Paragraph("Action Required:", ParagraphStyle("ar",fontName=_BASE_FONT_BOLD,fontSize=9,textColor=cfg["color"]))],
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

    # Group by status — with date-sorted rows
    groups = {}
    for _, row in vendor_df.iterrows():
        st = row.get('Recon_Status', 'DEFAULT')
        if st not in groups:
            groups[st] = []
        inv_b  = str(row.get('Invoice Number_BOOKS', '')) if pd.notna(row.get('Invoice Number_BOOKS')) else ''
        inv_g  = str(row.get('Invoice Number_GST',   '')) if pd.notna(row.get('Invoice Number_GST'))   else ''
        inv_no = inv_g if inv_g and inv_g != 'nan' else inv_b
        date_g = fd(row.get('Invoice Date_GST',   ''))
        date_b = fd(row.get('Invoice Date_BOOKS', ''))
        # Store raw date for sorting
        raw_date_g = row.get('Invoice Date_GST',   None)
        raw_date_b = row.get('Invoice Date_BOOKS', None)
        sort_date  = raw_date_g if pd.notna(raw_date_g) and raw_date_g not in (None, '') else raw_date_b
        try:
            sort_dt = pd.to_datetime(sort_date, dayfirst=True, errors='coerce')
        except Exception:
            sort_dt = pd.NaT
        groups[st].append({
            'inv_no': inv_no, 'inv_b': inv_b if inv_b and inv_b != 'nan' else '—',
            'inv_g': inv_g if inv_g and inv_g != 'nan' else '—',
            'date': date_g if date_g != '-' else date_b,
            '_sort_dt': sort_dt, '_sort_inv': str(inv_no),
            'taxable':     row.get('Taxable Value_BOOKS', 0) or 0,
            'igst':        row.get('IGST_BOOKS',          0) or 0,
            'cgst':        row.get('CGST_BOOKS',          0) or 0,
            'sgst':        row.get('SGST_BOOKS',          0) or 0,
            'gst_taxable': row.get('Taxable Value_GST',   0) or 0,
            'gst_igst':    row.get('IGST_GST',            0) or 0,
            'gst_cgst':    row.get('CGST_GST',            0) or 0,
            'gst_sgst':    row.get('SGST_GST',            0) or 0,
            'has_gst':     bool(inv_g and inv_g != 'nan'),
        })

    # Sort each group: Date oldest first, then Invoice Number A→Z
    for st in groups:
        groups[st].sort(key=lambda r: (
            r['_sort_dt'] if pd.notna(r['_sort_dt']) else pd.Timestamp('2099-12-31'),
            r['_sort_inv']
        ))

    # Use whichever side has data (books for Not in 2B, portal for Not in Books, books for mismatches)
    tot_tax  = sum(max(r['taxable'],     r['gst_taxable'])  for g in groups.values() for r in g)
    tot_igst = sum(max(r['igst'],        r['gst_igst'])     for g in groups.values() for r in g)
    tot_cgst = sum(max(r['cgst'],        r['gst_cgst'])     for g in groups.values() for r in g)
    tot_sgst = sum(max(r['sgst'],        r['gst_sgst'])     for g in groups.values() for r in g)
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
        canvas.setFont(_BASE_FONT, 7)
        canvas.setFillColor(colors.HexColor("#888888"))
        canvas.drawCentredString(A4[0]/2, 10*mm,
            f"{company_name}  |  GSTIN: {gst_in_company}  |  Page {doc.page}  |  Generated: {today}")
        canvas.restoreState()

    doc.build(elements, onFirstPage=footer, onLaterPages=footer)
    buffer.seek(0)
    return buffer

# ══════════════════════════════════════════════════════════════════════════════
# ITC AT-RISK SUMMARY PDF  (Feature 5)
# ══════════════════════════════════════════════════════════════════════════════

def create_itc_risk_pdf(df, company_name, gstin, period, fy):
    """
    Single-page ITC At-Risk summary PDF.
    ITC BLOCKED = Only 'Invoices Not in GSTR-2B' (Section 16(2)(aa)).
    Other categories shown as discrepancies but NOT counted in ITC blocked total.
    """
    buffer = io.BytesIO()
    doc    = SimpleDocTemplate(buffer, pagesize=A4,
                                leftMargin=18*mm, rightMargin=18*mm,
                                topMargin=14*mm, bottomMargin=14*mm)
    W     = A4[0] - 36*mm
    today = date.today().strftime('%d-%m-%Y')

    # ITC BLOCKED = only Not in GSTR-2B
    itc_blocked_df = df[df['Recon_Status'] == 'Invoices Not in GSTR-2B'].copy()

    # All issues (for discrepancy breakdown table)
    ISSUE_MASK = 'Not in|Mismatch|Suggestion|Manual|Tax Error'
    issue_df   = df[df['Recon_Status'].str.contains(ISSUE_MASK, na=False)].copy()

    STATUS_LABELS = {
        "Invoices Not in GSTR-2B":        ("ITC BLOCKED — Missing from Portal",  ACCENT_RED),
        "AI Matched (Mismatch)":           ("Value Mismatch",                     ACCENT_RED),
        "Matched (Tax Error)":             ("Tax Breakup Error",                  ACCENT_GOLD),
        "Invoices Not in Purchase Books":  ("Unidentified Portal Entry",          ACCENT_GOLD),
        "AI Matched (Date Mismatch)":      ("Date Mismatch",                      MID_BLUE),
        "AI Matched (Invoice Mismatch)":   ("Invoice No. Mismatch",               MID_BLUE),
        "Suggestion":                      ("Possible Match — Needs Review",      MID_BLUE),
        "Manually Linked":                 ("Manually Linked",                    ACCENT_GRN),
    }

    elements = []

    # ── Header ────────────────────────────────────────────────────────────────
    elements.append(_header_table(company_name, gstin, today, W))
    elements.append(Spacer(1, 8))

    title_row = [[
        Paragraph("ITC BLOCKED SUMMARY REPORT",
                  ParagraphStyle("rpt", fontName=_BASE_FONT_BOLD, fontSize=13,
                                 textColor=DARK_NAVY, alignment=TA_CENTER)),
        Paragraph(f"{fy} | {period}",
                  ParagraphStyle("per", fontName=_BASE_FONT, fontSize=9,
                                 textColor=MID_BLUE, alignment=TA_CENTER)),
    ]]
    title_tbl = Table(title_row, colWidths=[W * 0.65, W * 0.35])
    title_tbl.setStyle(TableStyle([
        ('BACKGROUND',  (0, 0), (-1, -1), BG_GRAY),
        ('TOPPADDING',  (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING',(0,0),(-1,-1), 10),
        ('LEFTPADDING', (0, 0), (-1, -1), 12),
        ('RIGHTPADDING',(0, 0), (-1, -1), 12),
        ('BOX',         (0, 0), (-1, -1), 1, MID_BLUE),
        ('VALIGN',      (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    elements.append(title_tbl)
    elements.append(Spacer(1, 10))

    # ── KPI row — ITC Blocked only ────────────────────────────────────────────
    total_blocked_inv     = len(itc_blocked_df)
    total_blocked_taxable = itc_blocked_df['Final_Taxable'].sum() if 'Final_Taxable' in itc_blocked_df.columns else 0
    total_vendors_blocked = itc_blocked_df['Name of Party'].nunique() if not itc_blocked_df.empty else 0

    def kpi(label, value, color):
        t = Table([[Paragraph(label, ParagraphStyle("kl", fontName=_BASE_FONT, fontSize=8, textColor=colors.HexColor("#666666"), alignment=TA_CENTER))],
                   [Paragraph(value, ParagraphStyle("kv", fontName=_BASE_FONT_BOLD, fontSize=13, textColor=color, alignment=TA_CENTER))]],
                  colWidths=[W / 3 - 6])
        t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1), WHITE),
                                ('BOX',(0,0),(-1,-1),0.8, color),
                                ('TOPPADDING',(0,0),(-1,-1),8),('BOTTOMPADDING',(0,0),(-1,-1),8)]))
        return t

    kpi_row = [[kpi("ITC Blocked Invoices (Not in 2B)", str(total_blocked_inv),          ACCENT_RED),
                kpi("Total ITC Blocked (₹)",            fc(total_blocked_taxable, True),  DARK_NAVY),
                kpi("Vendors with Blocked ITC",          str(total_vendors_blocked),       MID_BLUE)]]
    kpi_tbl = Table(kpi_row, colWidths=[W / 3] * 3)
    kpi_tbl.setStyle(TableStyle([('LEFTPADDING',(0,0),(-1,-1),3),('RIGHTPADDING',(0,0),(-1,-1),3),
                                  ('TOPPADDING',(0,0),(-1,-1),0),('BOTTOMPADDING',(0,0),(-1,-1),0)]))
    elements.append(kpi_tbl)
    elements.append(Spacer(1, 10))

    # ── Category breakdown table (all issues, ITC blocked clearly flagged) ────
    elements.append(Paragraph("Issue Category Breakdown", S("bold")))
    elements.append(Spacer(1, 4))

    cat_hdr = [Paragraph(h, S("tbl_hdr")) for h in ["Issue Category", "Invoices", "Taxable Value (₹)", "ITC Impact"]]
    cat_data = [cat_hdr]
    status_grp = issue_df.groupby('Recon_Status').agg(
        count=('Recon_Status', 'count'),
        taxable=('Final_Taxable', 'sum')
    ).reset_index().sort_values('taxable', ascending=False)

    for _, row in status_grp.iterrows():
        lbl, clr = STATUS_LABELS.get(row['Recon_Status'], (row['Recon_Status'][:30], MID_BLUE))
        # Only "Not in GSTR-2B" = ITC blocked; rest = discrepancy
        if row['Recon_Status'] == 'Invoices Not in GSTR-2B':
            impact_txt = "ITC BLOCKED"
            impact_clr = ACCENT_RED
        else:
            impact_txt = "Discrepancy"
            impact_clr = ACCENT_GOLD
        cat_data.append([
            Paragraph(lbl, S("tbl_cell")),
            Paragraph(str(int(row['count'])), S("tbl_num")),
            Paragraph(fc(row['taxable'], True), S("tbl_num")),
            Paragraph(impact_txt, ParagraphStyle("il", fontName=_BASE_FONT_BOLD, fontSize=8, textColor=impact_clr, alignment=TA_CENTER)),
        ])

    # Total row — ITC blocked only
    cat_data.append([
        Paragraph("TOTAL ITC BLOCKED (Not in 2B)", S("tbl_hdr")),
        Paragraph(str(total_blocked_inv), S("tbl_bold")),
        Paragraph(fc(total_blocked_taxable, True), S("tbl_bold")),
        Paragraph("", S("tbl_hdr")),
    ])

    n = len(cat_data)
    cat_tbl = Table(cat_data, colWidths=[W * 0.45, W * 0.12, W * 0.25, W * 0.18])
    cat_tbl.setStyle(TableStyle([
        ('BACKGROUND',  (0, 0), (-1, 0), DARK_NAVY),
        ('TEXTCOLOR',   (0, 0), (-1, 0), WHITE),
        ('FONTNAME',    (0, 0), (-1, 0), _BASE_FONT_BOLD),
        ('FONTSIZE',    (0, 0), (-1, -1), 8),
        ('BACKGROUND',  (0, n-1), (-1, n-1), LIGHT_BLUE),
        ('FONTNAME',    (0, n-1), (-1, n-1), _BASE_FONT_BOLD),
        *[('BACKGROUND',(0, r), (-1, r), BG_GRAY) for r in range(2, n-1, 2)],
        ('GRID',        (0, 0), (-1, -1), 0.5, colors.HexColor("#AAAAAA")),
        ('BOX',         (0, 0), (-1, -1), 1.2, MID_BLUE),
        ('TOPPADDING',  (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING',(0,0),(-1,-1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING',(0, 0), (-1, -1), 6),
        ('VALIGN',      (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    elements.append(cat_tbl)
    elements.append(Spacer(1, 12))

    # ── Top 5 vendors with blocked ITC (Not in 2B only) ─────────────────────
    elements.append(Paragraph("Top Vendors — ITC Blocked (Not in GSTR-2B)", S("bold")))
    elements.append(Spacer(1, 4))

    vendor_risk = itc_blocked_df.groupby('Name of Party').agg(
        inv_count=('Recon_Status', 'count'),
        taxable  =('Final_Taxable', 'sum')
    ).reset_index().sort_values('taxable', ascending=False).head(5)

    v_hdr = [Paragraph(h, S("tbl_hdr")) for h in ["#", "Vendor Name", "Blocked Invoices", "ITC Blocked (₹)"]]
    v_data = [v_hdr]
    for i, (_, vrow) in enumerate(vendor_risk.iterrows(), 1):
        v_data.append([
            Paragraph(str(i), S("tbl_cell")),
            Paragraph(str(vrow['Name of Party'])[:40], S("tbl_cell")),
            Paragraph(str(int(vrow['inv_count'])), S("tbl_num")),
            Paragraph(fc(vrow['taxable'], True), S("tbl_bold")),
        ])

    v_tbl = Table(v_data, colWidths=[W * 0.06, W * 0.50, W * 0.18, W * 0.26])
    v_tbl.setStyle(TableStyle([
        ('BACKGROUND',  (0, 0), (-1, 0), DARK_NAVY),
        ('TEXTCOLOR',   (0, 0), (-1, 0), WHITE),
        ('FONTNAME',    (0, 0), (-1, 0), _BASE_FONT_BOLD),
        ('FONTSIZE',    (0, 0), (-1, -1), 8),
        *[('BACKGROUND',(0, r), (-1, r), BG_GRAY) for r in range(2, len(v_data), 2)],
        ('GRID',        (0, 0), (-1, -1), 0.5, colors.HexColor("#AAAAAA")),
        ('BOX',         (0, 0), (-1, -1), 1.2, MID_BLUE),
        ('TOPPADDING',  (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING',(0,0),(-1,-1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING',(0, 0), (-1, -1), 6),
        ('VALIGN',      (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    elements.append(v_tbl)
    elements.append(Spacer(1, 14))

    # ── Party-wise "Not in GSTR-2B" Invoice Detail ───────────────────────────
    not_in_2b_df = df[df['Recon_Status'] == 'Invoices Not in GSTR-2B'].copy()
    if not not_in_2b_df.empty:
        # Section header
        hdr_2b = Table([[
            Paragraph("PARTY-WISE INVOICES NOT IN GSTR-2B",
                      ParagraphStyle("s2b", fontName=_BASE_FONT_BOLD, fontSize=10,
                                     textColor=WHITE)),
            Paragraph("(Action Required: Vendor must upload in GSTR-1)",
                      ParagraphStyle("s2b2", fontName=_BASE_FONT, fontSize=8,
                                     textColor=colors.HexColor("#FFCCCC"), alignment=TA_RIGHT)),
        ]], colWidths=[W * 0.60, W * 0.40])
        hdr_2b.setStyle(TableStyle([
            ('BACKGROUND',   (0, 0), (-1, -1), ACCENT_RED),
            ('TOPPADDING',   (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING',(0, 0), (-1, -1), 8),
            ('LEFTPADDING',  (0, 0), (-1, -1), 12),
            ('RIGHTPADDING', (0, 0), (-1, -1), 12),
            ('VALIGN',       (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        elements.append(hdr_2b)
        elements.append(Spacer(1, 4))

        # Sort: party name, then date oldest first
        not_in_2b_df['_sort_date'] = pd.to_datetime(
            not_in_2b_df.get('Invoice Date_BOOKS', pd.Series(dtype=str)),
            dayfirst=True, errors='coerce'
        )
        not_in_2b_df = not_in_2b_df.sort_values(
            ['Name of Party', '_sort_date',
             not_in_2b_df.columns[not_in_2b_df.columns.get_loc('Invoice Number_BOOKS')
                                   if 'Invoice Number_BOOKS' in not_in_2b_df.columns else 0]],
            na_position='last'
        )

        parties = not_in_2b_df['Name of Party'].unique()
        for party in parties:
            p_df = not_in_2b_df[not_in_2b_df['Name of Party'] == party]
            p_gstin = str(p_df['GSTIN'].iloc[0]) if 'GSTIN' in p_df.columns else ''

            # Party sub-header
            p_hdr = Table([[
                Paragraph(f"  {party}",
                          ParagraphStyle("ph", fontName=_BASE_FONT_BOLD, fontSize=9,
                                         textColor=DARK_NAVY)),
                Paragraph(f"GSTIN: {p_gstin}  |  {len(p_df)} invoice(s)",
                          ParagraphStyle("pg", fontName=_BASE_FONT, fontSize=8,
                                         textColor=colors.HexColor("#666666"), alignment=TA_RIGHT)),
            ]], colWidths=[W * 0.60, W * 0.40])
            p_hdr.setStyle(TableStyle([
                ('BACKGROUND',   (0, 0), (-1, -1), LIGHT_BLUE),
                ('TOPPADDING',   (0, 0), (-1, -1), 5),
                ('BOTTOMPADDING',(0, 0), (-1, -1), 5),
                ('LEFTPADDING',  (0, 0), (-1, -1), 8),
                ('RIGHTPADDING', (0, 0), (-1, -1), 8),
                ('LINEBEFORE',   (0, 0), (0, -1), 4, ACCENT_RED),
                ('VALIGN',       (0, 0), (-1, -1), 'MIDDLE'),
            ]))
            elements.append(p_hdr)

            # Invoice rows
            inv_hdr = [Paragraph(h, S("tbl_hdr")) for h in
                       ["Sr.", "Invoice No.", "Date", "Taxable (₹)", "CGST (₹)", "SGST (₹)", "IGST (₹)", "Total (₹)"]]
            inv_data = [inv_hdr]
            p_tot_tax = p_tot_cgst = p_tot_sgst = p_tot_igst = 0.0

            for sr, (_, row) in enumerate(p_df.iterrows(), 1):
                inv_no = str(row.get('Invoice Number_BOOKS', '')) if pd.notna(row.get('Invoice Number_BOOKS')) else '—'
                inv_dt = fd(row.get('Invoice Date_BOOKS', ''))
                tax    = float(row.get('Taxable Value_BOOKS', 0) or 0)
                igst   = float(row.get('IGST_BOOKS', 0) or 0)
                cgst   = float(row.get('CGST_BOOKS', 0) or 0)
                sgst   = float(row.get('SGST_BOOKS', 0) or 0)
                total  = tax + igst + cgst + sgst
                p_tot_tax += tax; p_tot_igst += igst
                p_tot_cgst += cgst; p_tot_sgst += sgst

                inv_data.append([
                    Paragraph(str(sr), S("tbl_cell")),
                    Paragraph(inv_no,  S("tbl_cell")),
                    Paragraph(inv_dt,  S("tbl_cell")),
                    Paragraph(fc(tax),  S("tbl_num")),
                    Paragraph(fc(cgst), S("tbl_num")),
                    Paragraph(fc(sgst), S("tbl_num")),
                    Paragraph(fc(igst), S("tbl_num")),
                    Paragraph(fc(total, show_zero=True), S("tbl_bold")),
                ])

            # Party total row
            p_total = p_tot_tax + p_tot_igst + p_tot_cgst + p_tot_sgst
            inv_data.append([
                Paragraph("", S("tbl_hdr")),
                Paragraph("TOTAL", S("tbl_hdr")),
                Paragraph(f"{len(p_df)} inv.", S("tbl_hdr")),
                Paragraph(fc(p_tot_tax,  True), S("tbl_bold")),
                Paragraph(fc(p_tot_cgst, True), S("tbl_bold")),
                Paragraph(fc(p_tot_sgst, True), S("tbl_bold")),
                Paragraph(fc(p_tot_igst, True), S("tbl_bold")),
                Paragraph(fc(p_total,    True), S("tbl_bold")),
            ])

            n_inv = len(inv_data)
            inv_tbl = Table(inv_data,
                            colWidths=[c * (W - 2) / 434 for c in [18, 60, 46, 76, 56, 56, 56, 66]],
                            repeatRows=1)
            inv_tbl.setStyle(TableStyle([
                ('BACKGROUND',  (0, 0), (-1, 0),    DARK_NAVY),
                ('TEXTCOLOR',   (0, 0), (-1, 0),    WHITE),
                ('FONTNAME',    (0, 0), (-1, 0),    _BASE_FONT_BOLD),
                ('FONTSIZE',    (0, 0), (-1, -1),   7.5),
                ('BACKGROUND',  (0, n_inv-1), (-1, n_inv-1), LIGHT_BLUE),
                ('FONTNAME',    (0, n_inv-1), (-1, n_inv-1), _BASE_FONT_BOLD),
                *[('BACKGROUND', (0, r), (-1, r), BG_GRAY) for r in range(2, n_inv-1, 2)],
                ('GRID',        (0, 0), (-1, -1),   0.4, colors.HexColor("#CCCCCC")),
                ('BOX',         (0, 0), (-1, -1),   0.8, ACCENT_RED),
                ('TOPPADDING',  (0, 0), (-1, -1),   3),
                ('BOTTOMPADDING',(0,0), (-1, -1),   3),
                ('LEFTPADDING', (0, 0), (-1, -1),   4),
                ('RIGHTPADDING',(0, 0), (-1, -1),   4),
                ('VALIGN',      (0, 0), (-1, -1),   'MIDDLE'),
            ]))
            elements.append(inv_tbl)
            elements.append(Spacer(1, 8))

        elements.append(Spacer(1, 6))

    # ── Disclaimer ────────────────────────────────────────────────────────────
    disc = Table([[Paragraph(
        "⚠  Disclaimer: This report is based on GSTR-2B vs Purchase Register reconciliation data as of "
        f"{today}. ITC eligibility is subject to Section 16 of CGST Act, 2017 and applicable rules. "
        "Consult your CA/Tax Advisor before taking any action based on this report.",
        ParagraphStyle("disc", fontName=_BASE_FONT, fontSize=7.5, textColor=colors.HexColor("#555555"), leading=11)
    )]], colWidths=[W])
    disc.setStyle(TableStyle([
        ('BACKGROUND',  (0, 0), (-1, -1), colors.HexColor("#FFF8E1")),
        ('TOPPADDING',  (0, 0), (-1, -1), 7),
        ('BOTTOMPADDING',(0,0),(-1,-1), 7),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING',(0, 0), (-1, -1), 10),
        ('BOX',         (0, 0), (-1, -1), 0.8, ACCENT_GOLD),
    ]))
    elements.append(disc)

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont(_BASE_FONT, 7)
        canvas.setFillColor(colors.HexColor("#888888"))
        canvas.drawCentredString(A4[0] / 2, 10 * mm,
            f"{company_name}  |  GSTIN: {gstin}  |  ITC Risk Report  |  Generated: {today}")
        canvas.restoreState()

    doc.build(elements, onFirstPage=footer, onLaterPages=footer)
    buffer.seek(0)
    return buffer


# ══════════════════════════════════════════════════════════════════════════════
# ACTION REPORT PDF — Detailed Issues + Recommended Actions (for Owner / CA)
# ══════════════════════════════════════════════════════════════════════════════

_ACTION_MAP = {
    "Invoices Not in GSTR-2B": {
        "label":  "ITC BLOCKED — Invoice not uploaded by supplier in GSTR-1",
        "color":  "#C7000A",
        "action": (
            "ACTION: Contact supplier immediately and ask them to upload this invoice in their GSTR-1 "
            "for the current or next filing period. Do NOT claim ITC on this invoice until it appears "
            "in GSTR-2B. Risk: ITC disallowance under Section 16(2)(aa) of CGST Act."
        ),
    },
    "AI Matched (Mismatch)": {
        "label":  "VALUE MISMATCH — Invoice found but amounts differ",
        "color":  "#D97706",
        "action": (
            "ACTION: Verify invoice copy with supplier. If Books value is correct, request supplier "
            "to file an amendment (GSTR-1A) to correct the portal value. If portal value is correct, "
            "update your Books. Excess ITC claimed = liable for interest + penalty."
        ),
    },
    "Matched (Tax Error)": {
        "label":  "TAX BREAKUP ERROR — Taxable value matches but IGST/CGST/SGST differs",
        "color":  "#D97706",
        "action": (
            "ACTION: Verify whether the transaction is inter-state (IGST) or intra-state (CGST+SGST). "
            "Cross-check with supplier's invoice. If supplier filed wrong tax type, ask them to amend "
            "GSTR-1. Wrong ITC head claimed can cause IGST/CGST ledger mismatch in GSTR-3B."
        ),
    },
    "AI Matched (Date Mismatch)": {
        "label":  "DATE MISMATCH — Invoice matched but date differs between Books and Portal",
        "color":  "#1352C9",
        "action": (
            "ACTION: Check original invoice and confirm correct date. If Books date is wrong, update "
            "your purchase register. If supplier filed wrong date in GSTR-1, request amendment. "
            "Financial Year assignment may be affected if date crosses April boundary."
        ),
    },
    "AI Matched (Invoice Mismatch)": {
        "label":  "INVOICE NUMBER MISMATCH — Amounts match but invoice numbers differ",
        "color":  "#1352C9",
        "action": (
            "ACTION: Each row in the table above shows two numbers — 📘 Our Books Inv No. (blue, top) "
            "and 📋 Your Portal Inv No. (red, below). Please amend your GSTR-1 to replace the "
            "Portal number with the Books number shown above. "
            "Mismatched invoice numbers can cause ITC disallowance during GST audit."
        ),
    },
    "Invoices Not in Purchase Books": {
        "label":  "NOT IN BOOKS — Supplier uploaded invoice but not recorded in your Books",
        "color":  "#7C3AED",
        "action": (
            "ACTION: Verify whether this purchase was actually made. If yes, locate the original "
            "invoice and record it in your Purchase Register. If this invoice is not yours, "
            "report to your CA — possible GSTIN misuse or fraudulent upload."
        ),
    },
    "Suggestion": {
        "label":  "POSSIBLE MATCH — Needs manual review",
        "color":  "#0F6B3C",
        "action": (
            "ACTION: Manually verify this invoice pair. If they are the same invoice with minor "
            "differences, use the Manual Matcher in the tool to link them. Unresolved suggestions "
            "may cause ITC mismatch in GSTR-3B reconciliation."
        ),
    },
}


def create_action_report_pdf(df, company_name, gstin, period, fy):
    """
    Detailed Action Report PDF for Owner / CA.
    One section per vendor with all issues and specific recommended actions.
    """
    buffer = io.BytesIO()
    doc    = SimpleDocTemplate(buffer, pagesize=A4,
                                leftMargin=18*mm, rightMargin=18*mm,
                                topMargin=14*mm, bottomMargin=18*mm)
    W     = A4[0] - 36*mm
    today = date.today().strftime('%d-%m-%Y')

    ISSUE_MASK = 'Not in|Mismatch|Suggestion|Manual|Tax Error'
    issue_df   = df[df['Recon_Status'].str.contains(ISSUE_MASK, na=False)].copy() if 'Recon_Status' in df.columns else df.copy()

    elements = []

    # ── Cover Header ──────────────────────────────────────────────────────────
    elements.append(_header_table(company_name, gstin, today, W))
    elements.append(Spacer(1, 10))

    cover_title = Table([[
        Paragraph("GST RECONCILIATION — ACTION REPORT",
                  ParagraphStyle("ct", fontName=_BASE_FONT_BOLD, fontSize=14,
                                 textColor=DARK_NAVY, alignment=TA_CENTER)),
    ]], colWidths=[W])
    cover_title.setStyle(TableStyle([
        ('BACKGROUND',   (0,0),(-1,-1), LIGHT_BLUE),
        ('TOPPADDING',   (0,0),(-1,-1), 10),
        ('BOTTOMPADDING',(0,0),(-1,-1), 10),
        ('BOX',          (0,0),(-1,-1), 1.5, MID_BLUE),
    ]))
    elements.append(cover_title)
    elements.append(Spacer(1, 6))

    # Period / FY info row
    info_row = Table([[
        Paragraph(f"Financial Year: <b>{fy}</b>", ParagraphStyle("ir", fontName=_BASE_FONT, fontSize=9, textColor=DARK_NAVY)),
        Paragraph(f"Period: <b>{period}</b>",     ParagraphStyle("ir2", fontName=_BASE_FONT, fontSize=9, textColor=DARK_NAVY, alignment=TA_CENTER)),
        Paragraph(f"Report Date: <b>{today}</b>", ParagraphStyle("ir3", fontName=_BASE_FONT, fontSize=9, textColor=DARK_NAVY, alignment=TA_RIGHT)),
    ]], colWidths=[W/3]*3)
    info_row.setStyle(TableStyle([
        ('BACKGROUND',   (0,0),(-1,-1), BG_GRAY),
        ('TOPPADDING',   (0,0),(-1,-1), 6),('BOTTOMPADDING',(0,0),(-1,-1), 6),
        ('LEFTPADDING',  (0,0),(-1,-1), 8),('RIGHTPADDING',  (0,0),(-1,-1), 8),
        ('BOX',          (0,0),(-1,-1), 0.5, colors.HexColor("#AAAAAA")),
    ]))
    elements.append(info_row)
    elements.append(Spacer(1, 10))

    # ── Executive Summary KPIs ────────────────────────────────────────────────
    total_issues = len(issue_df)
    total_itc    = float(issue_df['Final_Taxable'].sum()) if 'Final_Taxable' in issue_df.columns else 0.0
    n_vendors    = issue_df['Name of Party'].nunique() if 'Name of Party' in issue_df.columns else 0

    not_in_2b    = issue_df[issue_df.get('Recon_Status', pd.Series(dtype=str)) == 'Invoices Not in GSTR-2B'] if 'Recon_Status' in issue_df.columns else pd.DataFrame()
    itc_blocked  = float(not_in_2b['Final_Taxable'].sum()) if 'Final_Taxable' in not_in_2b.columns and not not_in_2b.empty else 0.0

    def _kpi(lbl, val, clr):
        inner = Table([[
            Paragraph(lbl, ParagraphStyle("kl", fontName=_BASE_FONT, fontSize=7.5, textColor=colors.HexColor("#555555"), alignment=TA_CENTER)),
            Paragraph(val, ParagraphStyle("kv", fontName=_BASE_FONT_BOLD, fontSize=12, textColor=clr, alignment=TA_CENTER)),
        ]], colWidths=[W/4]*2)
        inner.setStyle(TableStyle([('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5)]))
        return inner

    kpi_tbl = Table([[
        _kpi("Total Issues Found",    str(total_issues),      ACCENT_RED),
        _kpi("ITC Blocked (Not in 2B)", fc(itc_blocked, True), DARK_NAVY),
        _kpi("Total Taxable at Risk", fc(total_itc, True),    MID_BLUE),
        _kpi("Vendors with Issues",   str(n_vendors),         ACCENT_GOLD),
    ]], colWidths=[W/4]*4)
    kpi_tbl.setStyle(TableStyle([
        ('BACKGROUND',  (0,0),(-1,-1), WHITE),
        ('BOX',         (0,0),(-1,-1), 1, MID_BLUE),
        ('INNERGRID',   (0,0),(-1,-1), 0.5, colors.HexColor("#E2E8F0")),
        ('TOPPADDING',  (0,0),(-1,-1), 0),('BOTTOMPADDING',(0,0),(-1,-1), 0),
    ]))
    elements.append(kpi_tbl)
    elements.append(Spacer(1, 14))

    # ── Intro note ────────────────────────────────────────────────────────────
    intro = Paragraph(
        "This report details all reconciliation discrepancies identified between your Purchase Register (Books) "
        "and GSTR-2B portal data. Each section below covers one vendor with the specific issues found and the "
        "recommended action to be taken. Please review with your CA before filing GSTR-3B.",
        ParagraphStyle("intro", fontName=_BASE_FONT, fontSize=8.5, textColor=colors.HexColor("#444444"), leading=13)
    )
    elements.append(intro)
    elements.append(Spacer(1, 12))

    # ── Per-Vendor Sections ───────────────────────────────────────────────────
    vendors = issue_df['Name of Party'].dropna().unique() if 'Name of Party' in issue_df.columns else []
    vendor_summary = issue_df.groupby('Name of Party').agg(
        total_issues=('Recon_Status', 'count'),
        total_taxable=('Final_Taxable', 'sum')
    ).reset_index().sort_values('total_taxable', ascending=False) if 'Name of Party' in issue_df.columns else pd.DataFrame()

    for _, vs_row in vendor_summary.iterrows():
        vname      = str(vs_row['Name of Party'])
        vdf        = issue_df[issue_df['Name of Party'] == vname]
        v_gstin    = str(vdf['GSTIN'].iloc[0]) if 'GSTIN' in vdf.columns and not vdf.empty else '—'
        v_total    = float(vs_row['total_taxable'])
        v_count    = int(vs_row['total_issues'])

        # Vendor header bar
        v_hdr = Table([[
            Paragraph(f"{vname}", ParagraphStyle("vh", fontName=_BASE_FONT_BOLD, fontSize=10, textColor=WHITE)),
            Paragraph(f"GSTIN: {v_gstin}   |   {v_count} issue(s)   |   Taxable: {fc(v_total, True)}",
                      ParagraphStyle("vi", fontName=_BASE_FONT, fontSize=8, textColor=colors.HexColor("#BBDEFB"), alignment=TA_RIGHT)),
        ]], colWidths=[W*0.5, W*0.5])
        v_hdr.setStyle(TableStyle([
            ('BACKGROUND',   (0,0),(-1,-1), DARK_NAVY),
            ('TOPPADDING',   (0,0),(-1,-1), 7),('BOTTOMPADDING',(0,0),(-1,-1), 7),
            ('LEFTPADDING',  (0,0),(-1,-1), 10),('RIGHTPADDING',(0,0),(-1,-1), 8),
            ('VALIGN',       (0,0),(-1,-1), 'MIDDLE'),
        ]))
        elements.append(v_hdr)

        # Group by status
        for status, sdf in vdf.groupby('Recon_Status'):
            amap     = _ACTION_MAP.get(status, {
                "label": status, "color": "#333333",
                "action": "Review this item with your CA and reconcile manually."
            })
            s_clr    = colors.HexColor(amap["color"])
            s_label  = amap["label"]
            s_action = amap["action"]

            # Status label row
            elements.append(Table([[
                Paragraph(s_label,
                          ParagraphStyle("sl", fontName=_BASE_FONT_BOLD, fontSize=8,
                                         textColor=s_clr, leftIndent=4))
            ]], colWidths=[W], style=[
                ('BACKGROUND',(0,0),(-1,-1), BG_GRAY),
                ('TOPPADDING',(0,0),(-1,-1),4),('BOTTOMPADDING',(0,0),(-1,-1),4),
                ('LEFTPADDING',(0,0),(-1,-1),8),
            ]))

            # Invoice detail table
            inv_cols = ['Invoice Number_BOOKS','Invoice Number_GST','Invoice Date_BOOKS',
                        'Taxable Value_BOOKS','Taxable Value_GST','Final_Taxable']
            avail    = [c for c in inv_cols if c in sdf.columns]
            if avail:
                hdr_labels = {
                    'Invoice Number_BOOKS': 'Inv No (Books)',
                    'Invoice Number_GST':   'Inv No (Portal)',
                    'Invoice Date_BOOKS':   'Date',
                    'Taxable Value_BOOKS':  'Taxable (Books)',
                    'Taxable Value_GST':    'Taxable (Portal)',
                    'Final_Taxable':        'Final Taxable',
                }
                inv_hdr  = [Paragraph(hdr_labels.get(c,c), S("tbl_hdr")) for c in avail]
                inv_data = [inv_hdr]
                for _, irow in sdf[avail].head(10).iterrows():
                    inv_data.append([Paragraph(str(irow[c])[:25] if pd.notna(irow[c]) else '—', S("tbl_cell")) for c in avail])
                if len(sdf) > 10:
                    inv_data.append([Paragraph(f"... and {len(sdf)-10} more invoice(s)", S("tbl_cell"))] + [''] * (len(avail)-1))

                cw = W / len(avail)
                inv_tbl = Table(inv_data, colWidths=[cw]*len(avail))
                inv_tbl.setStyle(TableStyle([
                    ('BACKGROUND',  (0,0),(-1,0), colors.HexColor("#1E293B")),
                    ('TEXTCOLOR',   (0,0),(-1,0), WHITE),
                    ('FONTNAME',    (0,0),(-1,0), _BASE_FONT_BOLD),
                    ('FONTSIZE',    (0,0),(-1,-1), 7.5),
                    *[('BACKGROUND',(0,r),(-1,r), BG_GRAY) for r in range(2, len(inv_data), 2)],
                    ('GRID',        (0,0),(-1,-1), 0.4, colors.HexColor("#CCCCCC")),
                    ('TOPPADDING',  (0,0),(-1,-1), 3),('BOTTOMPADDING',(0,0),(-1,-1), 3),
                    ('LEFTPADDING', (0,0),(-1,-1), 4),('RIGHTPADDING', (0,0),(-1,-1), 4),
                ]))
                elements.append(inv_tbl)

            # Action box
            action_tbl = Table([[
                Paragraph(s_action,
                          ParagraphStyle("act", fontName=_BASE_FONT, fontSize=8,
                                         textColor=colors.HexColor("#1E293B"), leading=12, leftIndent=4))
            ]], colWidths=[W])
            action_tbl.setStyle(TableStyle([
                ('BACKGROUND',  (0,0),(-1,-1), colors.HexColor("#FFF8E1")),
                ('BOX',         (0,0),(-1,-1), 0.8, s_clr),
                ('TOPPADDING',  (0,0),(-1,-1), 6),('BOTTOMPADDING',(0,0),(-1,-1), 6),
                ('LEFTPADDING', (0,0),(-1,-1), 8),('RIGHTPADDING', (0,0),(-1,-1), 8),
            ]))
            elements.append(action_tbl)
            elements.append(Spacer(1, 4))

        elements.append(Spacer(1, 10))

    # ── Final Disclaimer ──────────────────────────────────────────────────────
    disc = Table([[Paragraph(
        f"Disclaimer: This action report is based on GSTR-2B vs Purchase Register data as of {today}. "
        "All recommended actions are general guidance under CGST Act 2017. Consult your Chartered "
        "Accountant before taking any corrective action. This is a computer-generated report.",
        ParagraphStyle("disc", fontName=_BASE_FONT, fontSize=7.5,
                       textColor=colors.HexColor("#555555"), leading=11)
    )]], colWidths=[W])
    disc.setStyle(TableStyle([
        ('BACKGROUND',   (0,0),(-1,-1), colors.HexColor("#FFF8E1")),
        ('BOX',          (0,0),(-1,-1), 0.8, ACCENT_GOLD),
        ('TOPPADDING',   (0,0),(-1,-1), 7),('BOTTOMPADDING',(0,0),(-1,-1), 7),
        ('LEFTPADDING',  (0,0),(-1,-1), 10),('RIGHTPADDING', (0,0),(-1,-1), 10),
    ]))
    elements.append(disc)

    def _footer(canvas, doc):
        canvas.saveState()
        canvas.setFont(_BASE_FONT, 7)
        canvas.setFillColor(colors.HexColor("#888888"))
        canvas.drawCentredString(A4[0]/2, 8*mm,
            f"{company_name}  |  GSTIN: {gstin}  |  Action Report  |  {today}  |  Page {doc.page}")
        canvas.restoreState()

    doc.build(elements, onFirstPage=_footer, onLaterPages=_footer)
    buffer.seek(0)
    return buffer
