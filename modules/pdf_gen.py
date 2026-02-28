# modules/pdf_gen.py
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.platypus import Table, TableStyle
import io
import pandas as pd

def format_curr(val):
    if pd.isna(val) or val == '': return "0.00"
    try: return f"{float(val):,.2f}"
    except: return "0.00"

def draw_header(c, width, height, company_name, gst_in_company):
    """Draws the professional letterhead on every page"""
    # Navy Blue Top Bar
    c.setFillColorRGB(0.1, 0.1, 0.4) 
    c.rect(0, height - 80, width, 80, fill=1, stroke=0)
    
    # Company Name & GSTIN
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 20)
    c.drawString(40, height - 35, company_name)
    c.setFont("Helvetica", 10)
    c.drawString(40, height - 55, f"GSTIN: {gst_in_company}")
    
    # Document Title
    c.setFont("Helvetica-Bold", 12)
    c.drawRightString(width - 40, height - 35, "DISCREPANCY NOTE")
    c.setFont("Helvetica", 9)
    c.drawRightString(width - 40, height - 55, "Strictly Confidential")

def create_vendor_pdf(df, vendor_name, company_name, gst_in_company):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    y = height - 120 # Start writing below header
    
    # Filter Data for Vendor
    vendor_df = df[
        (df['Name of Party'] == vendor_name) & 
        (df['Recon_Status'].str.contains('Not in|Mismatch', na=False))
    ].copy()
    
    if vendor_df.empty: return buffer

    # --- PAGE 1 SETUP ---
    draw_header(c, width, height, company_name, gst_in_company)
    
    # --- LETTER BODY ---
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(40, y, f"TO: {vendor_name}")
    y -= 20
    
    c.setFont("Helvetica-Bold", 10)
    c.drawString(40, y, "Subject: Discrepancies in GSTR-2B vs Purchase Register - Action Required")
    y -= 25
    
    c.setFont("Helvetica", 10)
    intro_text = [
        "Dear Sir/Madam,",
        "",
        f"This is to bring to your immediate attention that upon reconciliation of our Purchase Register for",
        f"{company_name} with the data reflected in GSTR-2B on the GST Portal, we have observed specific",
        "discrepancies listed below.",
        "",
        "These mismatches directly impact our Input Tax Credit (ITC) eligibility. We request you to verify your",
        "records and process the necessary amendments or uploads in your upcoming GSTR-1 filing.",
    ]
    
    for line in intro_text:
        c.drawString(40, y, line)
        y -= 14
    
    y -= 15 # Gap before table

    # --- TABLE DATA PREPARATION ---
    # Columns: Inv No | Date | Issue Type | GSTR-1 (You) | Books (Us) | Diff
    table_data = [[
        "Invoice No", "Date", "Discrepancy Type", "GSTR-1 (You)", "Books (Us)", "Diff"
    ]]
    
    total_diff = 0.0
    
    for idx, row in vendor_df.iterrows():
        status = row.get('Recon_Status', '')
        
        # Calculate Totals
        tot_b = row.get('Taxable Value_BOOKS', 0) + row.get('IGST_BOOKS', 0) + row.get('CGST_BOOKS', 0) + row.get('SGST_BOOKS', 0)
        tot_g = row.get('Taxable Value_GST', 0) + row.get('IGST_GST', 0) + row.get('CGST_GST', 0) + row.get('SGST_GST', 0)

        # Get Identifiers
        inv_g = str(row.get('Invoice Number_GST', ''))
        inv_b = str(row.get('Invoice Number_BOOKS', ''))
        date_g = str(row.get('Invoice Date_GST', ''))
        date_b = str(row.get('Invoice Date_BOOKS', ''))

        # Clean Date (remove time)
        date_g = date_g.split(' ')[0] if date_g != 'nan' else ''
        date_b = date_b.split(' ')[0] if date_b != 'nan' else ''

        d_inv = inv_g if inv_g and inv_g != 'nan' else inv_b
        d_date = date_g if date_g else date_b
        
        diff = tot_b - tot_g
        total_diff += diff
        
        # Categorize Issue
        if "Not in GSTR-2B" in status: 
            issue_type = "Missing in Portal"
            val_you = "Not Found"
        elif "Not in Purchase Books" in status: 
            issue_type = "Not in Books"
            val_you = format_curr(tot_g)
        else: 
            issue_type = "Value Mismatch"
            val_you = format_curr(tot_g)
        
        val_us = format_curr(tot_b) if "Not in Books" not in status else "Not Found"

        table_data.append([
            d_inv, d_date, issue_type, val_you, val_us, format_curr(diff)
        ])

    # --- TABLE DRAWING LOGIC ---
    col_widths = [90, 70, 100, 90, 90, 80]
    
    # 1. Define Header Style
    header_style = TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.Color(0.2, 0.2, 0.2)), # Dark Grey Header
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('ALIGN', (0,0), (-1,0), 'CENTER'),
        ('FONTSIZE', (0,0), (-1,0), 9),
        ('BOTTOMPADDING', (0,0), (-1,0), 8),
    ])

    # 2. Define Data Row Style (Zebra Striping)
    row_style = TableStyle([
        ('FONTNAME', (0,0), (-1,-1), 'Helvetica'),
        ('FONTSIZE', (0,0), (-1,-1), 8),
        ('ALIGN', (0,0), (2, -1), 'LEFT'),   # Left align text cols
        ('ALIGN', (3,0), (-1, -1), 'RIGHT'), # Right align numbers
        ('GRID', (0,0), (-1,-1), 0.5, colors.lightgrey),
        ('ROWBACKGROUNDS', (0,0), (-1,-1), [colors.white, colors.whitesmoke])
    ])

    # 3. Draw Header Row First
    t_header = Table([table_data[0]], colWidths=col_widths)
    t_header.setStyle(header_style)
    w, h_header = t_header.wrapOn(c, width, height)
    
    # Ensure space for header
    if y < h_header + 50:
        c.showPage()
        draw_header(c, width, height, company_name, gst_in_company)
        y = height - 100
    
    t_header.drawOn(c, 40, y - h_header)
    y -= h_header

    # 4. Draw Data Rows (Handle Pagination)
    for row_data in table_data[1:]:
        row_table = Table([row_data], colWidths=col_widths)
        row_table.setStyle(row_style)
        w, h_row = row_table.wrapOn(c, width, height)
        
        # Check for page break
        if y < 50: 
            c.showPage()
            draw_header(c, width, height, company_name, gst_in_company)
            y = height - 100
            # Redraw header on new page for clarity
            t_header.drawOn(c, 40, y - h_header)
            y -= h_header
            
        row_table.drawOn(c, 40, y - h_row)
        y -= h_row

    # --- FOOTER ---
    y -= 30
    if y < 80: # Ensure footer fits
        c.showPage()
        draw_header(c, width, height, company_name, gst_in_company)
        y = height - 100

    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(40, y, f"Total Discrepancy Value: {format_curr(total_diff)}")
    y -= 20
    
    c.setFont("Helvetica", 9)
    c.drawString(40, y, "We look forward to your prompt action on this matter.")
    y -= 40
    
    c.setFont("Helvetica-Bold", 9)
    c.drawString(40, y, "Authorized Signatory")
    c.setFont("Helvetica", 9)
    c.drawString(40, y-12, company_name)
    
    c.save()
    buffer.seek(0)
    return buffer