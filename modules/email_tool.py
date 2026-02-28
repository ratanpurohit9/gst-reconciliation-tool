# modules/email_tool.py
import pandas as pd

def get_vendors_with_issues(df):
    """
    Filter vendors who have 'Not in' or 'Mismatch' status.
    """
    issue_mask = df['Recon_Status'].str.contains('Not in|Mismatch', na=False)
    vendors = df[issue_mask]['Name of Party'].unique().tolist()
    vendors = [v for v in vendors if v and str(v) != 'nan']
    return sorted(vendors)

def fc(val): 
    """Format Currency: Returns string like 1,234.00"""
    if pd.isna(val) or val == '': return "0.00"
    try: return f"{float(val):,.2f}"
    except: return "0.00"

def get_date_str(val):
    """Format Date: Returns string dd-mm-yyyy"""
    try: return pd.to_datetime(val).strftime('%d-%m-%Y')
    except: return str(val) if pd.notna(val) else "N/A"

def generate_email_draft(df, vendor_name, company_name):
    """
    Generates a professional, table-like email without emojis.
    """
    vendor_df = df[
        (df['Name of Party'] == vendor_name) & 
        (df['Recon_Status'].str.contains('Not in|Mismatch', na=False))
    ].copy()
    
    if vendor_df.empty: return "No discrepancies found.", "No email needed."

    subject = f"Immediate Attention Required: GST Reconciliation Discrepancy Notice - {vendor_name}"

    body = f"""Dear Finance Team,

We are writing to bring to your attention certain discrepancies observed during our routine GST reconciliation process between our Purchase Records and your GSTR-1 filings for {company_name}.

To ensure seamless Input Tax Credit (ITC) flow and maintain statutory compliance, we kindly request you to review the following invoice-wise details and take the necessary corrective actions:

"""
    for idx, row in vendor_df.iterrows():
        status = row.get('Recon_Status', '')
        
        # Books Data
        inv_b = row.get('Invoice Number_BOOKS', '')
        date_b = get_date_str(row.get('Invoice Date_BOOKS', ''))
        tb = row.get('Taxable Value_BOOKS', 0)
        ib = row.get('IGST_BOOKS', 0)
        cb = row.get('CGST_BOOKS', 0)
        sb = row.get('SGST_BOOKS', 0)
        tot_b = tb + ib + cb + sb

        # GST Data
        inv_g = row.get('Invoice Number_GST', '')
        date_g = get_date_str(row.get('Invoice Date_GST', ''))
        tg = row.get('Taxable Value_GST', 0)
        ig = row.get('IGST_GST', 0)
        cg = row.get('CGST_GST', 0)
        sg = row.get('SGST_GST', 0)
        tot_g = tg + ig + cg + sg

        # Determine Display Invoice/Date
        d_inv = inv_g if inv_g and str(inv_g) != 'nan' else inv_b
        d_date = date_g if date_g and str(date_g) != 'nan' else date_b

        body += "----------------------------------------------------------------------\n"
        body += f"INVOICE: {d_inv}  |  DATE: {d_date}\n"
        body += "----------------------------------------------------------------------\n"

        if "Not in GSTR-2B" in status:
            body += "ISSUE: RECORD NOT REFLECTING IN GSTR-2B\n"
            body += "The following invoice is currently missing from the GST portal. Please ensure this is uploaded:\n"
            body += f"   Taxable Value : {fc(tb)}\n"
            body += f"   Tax Amount    : IGST: {fc(ib)} | CGST: {fc(cb)} | SGST: {fc(sb)}\n"
            body += f"   Total Invoice : {fc(tot_b)}\n"
            
        elif "Not in Purchase Books" in status:
            body += "ISSUE: UNRECONCILED ENTRY IN GST PORTAL\n"
            body += "The following entry appears in the GST portal but is not recorded in our purchase books. Kindly verify the validity:\n"
            body += f"   Taxable Value : {fc(tg)}\n"
            body += f"   Total Invoice : {fc(tot_g)}\n"

        else: # Mismatch
            body += "ISSUE: DATA MISMATCH\n"
            body += "A discrepancy has been noted between your filing and our records.\n"
            body += f"   [As per your filing] Taxable: {fc(tg)} | Total: {fc(tot_g)}\n"
            body += f"   [As per our records] Taxable: {fc(tb)} | Total: {fc(tot_b)}\n"
            body += "   ACTION: Please amend the filing to match our records.\n"
        
        body += "\n"

    body += f"Kindly confirm once the rectification or amendment has been processed.\n\nRegards,\nAccounts Department\n{company_name}"
    return subject, body

def generate_whatsapp_message(df, vendor_name, company_name):
    """
    Generates a short, crisp WhatsApp message with minimal emojis.
    """
    vendor_df = df[
        (df['Name of Party'] == vendor_name) & 
        (df['Recon_Status'].str.contains('Not in|Mismatch', na=False))
    ].copy()
    
    if vendor_df.empty: return ""

    msg = f"*GST Compliance Notification*\n"
    msg += f"Dear Team {vendor_name},\n\n"
    msg += f"During our reconciliation for *{company_name}*, we noted discrepancies in GSTR-1 filings:\n"
    msg += "━━━━━━━━━━━━━━━━━━\n"

    for idx, row in vendor_df.iterrows():
        status = row.get('Recon_Status', '')
        
        # Books Totals
        tb = row.get('Taxable Value_BOOKS', 0)
        tot_b = tb + row.get('IGST_BOOKS', 0) + row.get('CGST_BOOKS', 0) + row.get('SGST_BOOKS', 0)

        # GST Totals
        tg = row.get('Taxable Value_GST', 0)
        tot_g = tg + row.get('IGST_GST', 0) + row.get('CGST_GST', 0) + row.get('SGST_GST', 0)

        # Identifiers
        inv_b, inv_g = row.get('Invoice Number_BOOKS', ''), row.get('Invoice Number_GST', '')
        date_b, date_g = get_date_str(row.get('Invoice Date_BOOKS', '')), get_date_str(row.get('Invoice Date_GST', ''))
        d_inv = inv_g if inv_g and str(inv_g) != 'nan' else inv_b
        d_date = date_g if date_g and str(date_g) != 'nan' else date_b

        msg += f"*📄 Inv: {d_inv} | {d_date}*\n"
        
        if "Not in GSTR-2B" in status:
            msg += f"⚠️ Issue: Missing in Portal\n"
            msg += f"✅ Required: Please upload (Taxable: {fc(tb)} | Total: {fc(tot_b)})\n"
            
        elif "Not in Purchase Books" in status:
            msg += f"⚠️ Issue: Unreconciled in Books\n"
            msg += f"✅ Required: Verify validity (Portal Total: {fc(tot_g)})\n"

        else: # Mismatch
            msg += f"⚠️ Issue: Portal Mismatch\n"
            msg += f"✅ Required: Amend to match Total {fc(tot_b)} (Current: {fc(tot_g)})\n"
        
        msg += "━━━━━━━━━━━━━━━━━━\n"

    msg += "\nKindly review and confirm rectification date. Thanks."
    return msg

def generate_notice_content(df, vendor_name, company_name):
    """
    Generates a formal text block suitable for pasting onto a Letterhead/PDF.
    """
    vendor_df = df[
        (df['Name of Party'] == vendor_name) & 
        (df['Recon_Status'].str.contains('Not in|Mismatch', na=False))
    ].copy()
    
    if vendor_df.empty: return "No discrepancies found."

    notice = "RECONCILIATION NOTICE: DISCREPANCIES IN GST FILINGS\n"
    notice += "====================================================\n\n"
    notice += f"To: {vendor_name}\n"
    notice += f"From: {company_name}\n"
    notice += "Subject: Notification regarding GSTR-2B vs. Purchase Books Mismatch\n\n"

    notice += "This is a formal communication regarding the statutory reconciliation of Goods and Services Tax (GST) data. "
    notice += "Upon comparing our internal Purchase Register with the data auto-populated in our GSTR-2B, "
    notice += "we have identified certain inconsistencies pertaining to supplies provided by your organization.\n\n"
    
    notice += "We highlight the following cases for your immediate verification and rectification:\n\n"

    for idx, row in vendor_df.iterrows():
        status = row.get('Recon_Status', '')
        
        # Books Data
        inv_b = row.get('Invoice Number_BOOKS', '')
        date_b = get_date_str(row.get('Invoice Date_BOOKS', ''))
        tot_b = row.get('Taxable Value_BOOKS', 0) + row.get('IGST_BOOKS', 0) + row.get('CGST_BOOKS', 0) + row.get('SGST_BOOKS', 0)

        # GST Data
        inv_g = row.get('Invoice Number_GST', '')
        tot_g = row.get('Taxable Value_GST', 0) + row.get('IGST_GST', 0) + row.get('CGST_GST', 0) + row.get('SGST_GST', 0)

        d_inv = inv_g if inv_g and str(inv_g) != 'nan' else inv_b
        d_date = date_g if (date_g := get_date_str(row.get('Invoice Date_GST', ''))) != 'N/A' else date_b

        notice += f"--- Invoice No: {d_inv} (Dated: {d_date}) ---\n"

        if "Not in GSTR-2B" in status:
            notice += f"Category: MISSING INVOICE\n"
            notice += f"Details: Invoice recorded in our books (Total: {fc(tot_b)}) is not reflecting in GSTR-2B.\n"
            notice += "Action: Kindly upload in GSTR-1 immediately.\n"
            
        elif "Not in Purchase Books" in status:
            notice += f"Category: UNIDENTIFIED RECORD\n"
            notice += f"Details: Invoice reflecting in GSTR-2B (Total: {fc(tot_g)}) is not found in our Purchase Register.\n"
            notice += "Action: Please provide proof of delivery or issue credit note if uploaded in error.\n"

        else: # Mismatch
            notice += f"Category: DATA MISMATCH\n"
            notice += f"Details: Portal value ({fc(tot_g)}) does not match our Books value ({fc(tot_b)}).\n"
            notice += "Action: Please amend the taxable/tax amounts to match our records.\n"
        
        notice += "\n"

    notice += "We request you to treat this matter with priority. Kindly reconcile these entries and carry out "
    notice += "the necessary amendments in your upcoming GSTR-1 filing.\n\n"
    notice += f"For {company_name}\n\n"
    notice += "(Authorized Signatory)\n"
    notice += "Accounts & Finance Department"

    return notice