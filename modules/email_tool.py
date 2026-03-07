# modules/email_tool.py — Smart notice generator for ALL Recon_Status types

import pandas as pd

ISSUE_MASK = 'Not in|Mismatch|Suggestion|Manual|Tax Error'

STATUS_MSG = {
    "Invoices Not in GSTR-2B": {
        "short":   "MISSING IN PORTAL",
        "email":   "Invoice recorded in our Purchase Books is NOT reflecting in GSTR-2B.\n   Action: Upload this invoice in your GSTR-1 immediately.",
        "wa":      "Missing in Portal - Please upload in GSTR-1",
        "notice":  "MISSING INVOICE: Invoice exists in our books but not in GSTR-2B. Please upload in GSTR-1 immediately.",
        "action":  "Upload in GSTR-1 at the earliest",
    },
    "Invoices Not in Purchase Books": {
        "short":   "UNIDENTIFIED IN OUR BOOKS",
        "email":   "Invoice appears in GSTR-2B (Portal) but is NOT in our Purchase Register.\n   Action: Provide invoice copy / proof of delivery, or issue Credit Note if uploaded in error.",
        "wa":      "Not in our Books - Provide invoice copy or issue Credit Note",
        "notice":  "UNIDENTIFIED RECORD: Invoice in portal but not in our books. Please provide invoice copy or issue Credit Note.",
        "action":  "Provide invoice copy or issue Credit Note",
    },
    "AI Matched (Date Mismatch)": {
        "short":   "DATE MISMATCH",
        "email":   "Invoice matched by value but Date differs between GSTR-1 and our records.\n   Action: Amend the invoice date in your GSTR-1 to match our Purchase Records.",
        "wa":      "Date Mismatch - Please amend invoice date in GSTR-1",
        "notice":  "DATE DISCREPANCY: Invoice date in your GSTR-1 does not match our records. Please amend.",
        "action":  "Amend invoice date in GSTR-1",
    },
    "AI Matched (Invoice Mismatch)": {
        "short":   "INVOICE NO. MISMATCH",
        "email":   "Invoice matched by value & date but Invoice Number differs.\n   Action: Amend the invoice number in your GSTR-1 to match our Purchase Records.",
        "wa":      "Invoice No. Mismatch - Please amend invoice number in GSTR-1",
        "notice":  "REFERENCE DISCREPANCY: Invoice number in your GSTR-1 does not match our records. Please amend.",
        "action":  "Amend invoice number in GSTR-1",
    },
    "AI Matched (Mismatch)": {
        "short":   "VALUE MISMATCH",
        "email":   "Invoice identified but taxable value / tax amounts do not match.\n   Action: Amend the taxable value and tax amounts in your GSTR-1.",
        "wa":      "Value Mismatch - Please amend invoice amounts in GSTR-1",
        "notice":  "VALUE DISCREPANCY: Taxable/tax values in GSTR-1 don't match our books. Please amend.",
        "action":  "Amend taxable value/tax in GSTR-1",
    },
    "Matched (Tax Error)": {
        "short":   "TAX BREAKUP ERROR",
        "email":   "Taxable value matches but IGST/CGST/SGST breakup shows a discrepancy. May cause ITC mismatch.\n   Action: Correct the tax breakup in your GSTR-1.",
        "wa":      "Tax Error - Please correct IGST/CGST/SGST breakup in GSTR-1",
        "notice":  "TAX ERROR: Tax breakup doesn't match. IGST/CGST/SGST correction required.",
        "action":  "Correct tax breakup (IGST/CGST/SGST) in GSTR-1",
    },
    "Suggestion": {
        "short":   "POSSIBLE MATCH",
        "email":   "A possible match was identified but requires manual verification.\n   Action: Please confirm if this invoice matches and amend if required.",
        "wa":      "Possible Match - Please verify and confirm",
        "notice":  "POSSIBLE MATCH: System identified a potential match. Manual verification needed.",
        "action":  "Verify and confirm or amend",
    },
    "Suggestion (Group Match)": {
        "short":   "GROUP MATCH",
        "email":   "A group of invoices may collectively match a consolidated entry.\n   Action: Please verify these entries and amend accordingly.",
        "wa":      "Group Match Suggestion - Please verify these invoices",
        "notice":  "GROUP MATCH: Multiple invoices may match a consolidated entry. Verify and amend.",
        "action":  "Verify group entries and amend",
    },
    "Manually Linked": {
        "short":   "MANUALLY LINKED",
        "email":   "Invoice was manually linked during reconciliation. Values should be verified.\n   Action: Confirm values match your GSTR-1 and amend if discrepancy found.",
        "wa":      "Manually Linked - Please verify amounts match your GSTR-1",
        "notice":  "MANUAL LINK: Invoice was manually matched. Verify values match your filing.",
        "action":  "Verify and amend if discrepancy found",
    },
    "DEFAULT": {
        "short":   "DISCREPANCY",
        "email":   "A discrepancy has been identified. Action required.\n   Action: Please review and rectify at the earliest.",
        "wa":      "Discrepancy found - Please review",
        "notice":  "DISCREPANCY: Please review and take corrective action.",
        "action":  "Review and rectify",
    },
}

def _get_msg(status, key):
    for k in STATUS_MSG:
        if k != "DEFAULT" and k in str(status):
            return STATUS_MSG[k][key]
    return STATUS_MSG["DEFAULT"][key]

def get_vendors_with_issues(df):
    issue_mask = df['Recon_Status'].str.contains(ISSUE_MASK, na=False)
    vendors = df[issue_mask]['Name of Party'].unique().tolist()
    return sorted([v for v in vendors if v and str(v) != 'nan'])

def fc(val):
    if pd.isna(val) or val == '': return "0.00"
    try: return f"{float(val):,.2f}"
    except: return "0.00"

def fi(val):
    """Format Indian rupee for WhatsApp (no unicode issues, uses Rs.)"""
    if pd.isna(val) or val == '' or val is None: return "0.00"
    try:
        f = abs(float(val))
        if f == 0: return "0.00"
        s = f"{f:,.2f}".split('.')
        n = s[0].replace(',','')
        if len(n) > 3:
            last3 = n[-3:]; rest = n[:-3]; grps = []
            while len(rest) > 2: grps.append(rest[-2:]); rest = rest[:-2]
            if rest: grps.append(rest)
            grps.reverse(); n = ','.join(grps) + ',' + last3
        return f"Rs.{n}.{s[1]}"
    except: return "0.00"

def fd(val):
    try: return pd.to_datetime(val).strftime('%d-%m-%Y')
    except:
        s = str(val) if pd.notna(val) else ''
        return s.split(' ')[0] if s and s != 'nan' else 'N/A'

def _get_row_data(row):
    inv_b  = str(row.get('Invoice Number_BOOKS','')) if pd.notna(row.get('Invoice Number_BOOKS')) else ''
    inv_g  = str(row.get('Invoice Number_GST',''))   if pd.notna(row.get('Invoice Number_GST'))   else ''
    date_b = fd(row.get('Invoice Date_BOOKS',''))
    date_g = fd(row.get('Invoice Date_GST',''))
    d_inv  = inv_g if inv_g and inv_g != 'nan' else inv_b
    d_date = date_g if date_g and date_g != 'N/A' else date_b
    tb = float(row.get('Taxable Value_BOOKS', 0) or 0)
    ib = float(row.get('IGST_BOOKS', 0) or 0)
    cb = float(row.get('CGST_BOOKS', 0) or 0)
    sb = float(row.get('SGST_BOOKS', 0) or 0)
    tg = float(row.get('Taxable Value_GST', 0) or 0)
    ig = float(row.get('IGST_GST', 0) or 0)
    cg = float(row.get('CGST_GST', 0) or 0)
    sg = float(row.get('SGST_GST', 0) or 0)
    return dict(inv=d_inv, date=d_date, tb=tb, ib=ib, cb=cb, sb=sb,
                tg=tg, ig=ig, cg=cg, sg=sg,
                tot_b=tb+ib+cb+sb, tot_g=tg+ig+cg+sg)


def generate_email_draft(df, vendor_name, company_name):
    vendor_df = df[
        (df['Name of Party'] == vendor_name) &
        df['Recon_Status'].str.contains(ISSUE_MASK, na=False)
    ].copy()

    if vendor_df.empty:
        return "No discrepancies found.", "No email needed."

    # Group by status
    groups = {}
    for _, row in vendor_df.iterrows():
        st = row.get('Recon_Status','DEFAULT')
        groups.setdefault(st, []).append(row)

    subject = f"Urgent: GST Reconciliation Discrepancy Notice — {vendor_name}"

    body  = f"Dear Finance Team ({vendor_name}),\n\n"
    body += f"We have completed reconciliation of our Purchase Register for {company_name} "
    body += f"with GSTR-2B data. We have identified {sum(len(v) for v in groups.values())} invoice(s) "
    body += f"with discrepancies across {len(groups)} issue type(s). Details below:\n\n"

    for status, rows in groups.items():
        short = _get_msg(status, "short")
        body += f"{'='*60}\n"
        body += f"ISSUE TYPE: {short} ({len(rows)} invoice(s))\n"
        body += f"{'='*60}\n"

        for row in rows:
            d = _get_row_data(row)
            body += f"\n  Invoice: {d['inv']}  |  Date: {d['date']}\n"
            body += f"  {_get_msg(status, 'email')}\n"

            if 'Not in Purchase Books' in status:
                body += f"  [Portal]  Taxable: {fc(d['tg'])} | IGST: {fc(d['ig'])} | CGST: {fc(d['cg'])} | SGST: {fc(d['sg'])} | Total: {fc(d['tot_g'])}\n"
            elif 'Not in GSTR-2B' in status:
                body += f"  [Books]   Taxable: {fc(d['tb'])} | IGST: {fc(d['ib'])} | CGST: {fc(d['cb'])} | SGST: {fc(d['sb'])} | Total: {fc(d['tot_b'])}\n"
            else:
                body += f"  [Books]   Taxable: {fc(d['tb'])} | IGST: {fc(d['ib'])} | CGST: {fc(d['cb'])} | SGST: {fc(d['sb'])} | Total: {fc(d['tot_b'])}\n"
                body += f"  [Portal]  Taxable: {fc(d['tg'])} | IGST: {fc(d['ig'])} | CGST: {fc(d['cg'])} | SGST: {fc(d['sg'])} | Total: {fc(d['tot_g'])}\n"
                diff = d['tot_b'] - d['tot_g']
                if abs(diff) > 0.01:
                    body += f"  Difference: {fc(abs(diff))}\n"
        body += "\n"

    body += f"Kindly confirm once all rectifications / amendments have been processed.\n\n"
    body += f"Regards,\nAccounts & Finance Department\n{company_name}"
    return subject, body


def generate_whatsapp_message(df, vendor_name, company_name):
    vendor_df = df[
        (df['Name of Party'] == vendor_name) &
        df['Recon_Status'].str.contains(ISSUE_MASK, na=False)
    ].copy()

    if vendor_df.empty:
        return ""

    groups = {}
    for _, row in vendor_df.iterrows():
        st = row.get('Recon_Status','DEFAULT')
        groups.setdefault(st, []).append(row)

    total_inv = sum(len(v) for v in groups.values())

    msg  = f"*GST Reconciliation Notice*\n"
    msg += f"Dear Team {vendor_name},\n\n"
    msg += f"Reconciliation for *{company_name}* identified *{total_inv} invoice(s)* needing attention:\n"
    msg += "━━━━━━━━━━━━━━━━━━━━━\n"

    for status, rows in groups.items():
        short = _get_msg(status, "short")
        msg += f"\n*[{short}]* ({len(rows)} inv.)\n"
        for row in rows:
            d = _get_row_data(row)
            msg += f"  Inv: *{d['inv']}* | {d['date']}\n"
            msg += f"  {_get_msg(status, 'wa')}\n"
            if 'Not in GSTR-2B' in status:
                msg += f"  Taxable: *{fi(d['tb'])}* | Total: *{fi(d['tot_b'])}*\n"
            elif 'Not in Purchase Books' in status:
                msg += f"  Portal Taxable: *{fi(d['tg'])}* | Total: *{fi(d['tot_g'])}*\n"
            else:
                diff = d['tot_b'] - d['tot_g']
                msg += f"  Books: {fi(d['tot_b'])} | Portal: {fi(d['tot_g'])} | *Diff: {fi(abs(diff))}*\n"
        msg += "━━━━━━━━━━━━━━━━━━━━━\n"

    msg += "\nKindly review and confirm rectification date. Thanks."
    return msg


def generate_notice_content(df, vendor_name, company_name):
    """Plain-text formal notice for letterhead use"""
    vendor_df = df[
        (df['Name of Party'] == vendor_name) &
        df['Recon_Status'].str.contains(ISSUE_MASK, na=False)
    ].copy()

    if vendor_df.empty:
        return "No discrepancies found."

    groups = {}
    for _, row in vendor_df.iterrows():
        st = row.get('Recon_Status','DEFAULT')
        groups.setdefault(st, []).append(row)

    total_inv = sum(len(v) for v in groups.values())
    notice  = f"GST RECONCILIATION NOTICE\n{'='*50}\n\n"
    notice += f"To:      {vendor_name}\nFrom:    {company_name}\n"
    notice += f"Subject: GSTR-2B vs Purchase Books Discrepancy — {total_inv} Invoice(s)\n\n"
    notice += "This is a formal notice regarding discrepancies identified during GST reconciliation.\n\n"

    for status, rows in groups.items():
        short = _get_msg(status, "short")
        notice += f"--- {short} ({len(rows)} invoice(s)) ---\n"
        for row in rows:
            d = _get_row_data(row)
            notice += f"  Invoice: {d['inv']} | Date: {d['date']}\n"
            notice += f"  {_get_msg(status, 'notice')}\n"
            notice += f"  Action Required: {_get_msg(status, 'action')}\n\n"

    notice += "Kindly process all corrections and confirm in writing.\n\n"
    notice += f"For {company_name}\n(Authorized Signatory)\nAccounts & Finance Department"
    return notice
