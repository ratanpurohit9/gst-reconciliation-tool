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
    if pd.isna(val) or val == '' or val is None: return "Rs.0.00"
    try:
        f = abs(float(val))
        if f == 0: return "Rs.0.00"
        s = f"{f:,.2f}".split('.')
        n = s[0].replace(',','')
        if len(n) > 3:
            last3 = n[-3:]; rest = n[:-3]; grps = []
            while len(rest) > 2: grps.append(rest[-2:]); rest = rest[:-2]
            if rest: grps.append(rest)
            grps.reverse(); n = ','.join(grps) + ',' + last3
        return f"Rs.{n}.{s[1]}"
    except: return "Rs.0.00"

def fd(val):
    try: return pd.to_datetime(val).strftime('%d-%m-%Y')
    except:
        s = str(val) if pd.notna(val) else ''
        return s.split(' ')[0] if s and s != 'nan' else 'N/A'

def _get_row_data(row):
    # Try suffixed columns first, then fall back to plain names
    def _get_inv(row, *cols):
        for c in cols:
            v = row.get(c)
            if v is not None and pd.notna(v) and str(v).strip() not in ('', 'nan', 'None'):
                return str(v).strip()
        return ''

    inv_b  = _get_inv(row, 'Invoice Number_BOOKS', 'Invoice Number', 'Invoice No', 'Invoice No.', 'Inv No', 'bill_no', 'Bill No')
    inv_g  = _get_inv(row, 'Invoice Number_GST', 'Invoice Number_GSTR')
    date_b = fd(row.get('Invoice Date_BOOKS') or row.get('Invoice Date') or row.get('Date') or '')
    date_g = fd(row.get('Invoice Date_GST') or '')
    d_inv  = inv_g if inv_g else inv_b
    d_date = date_g if date_g and date_g != 'N/A' else date_b
    tb = float(row.get('Taxable Value_BOOKS', 0) or row.get('Taxable Value', 0) or 0)
    ib = float(row.get('IGST_BOOKS', 0) or row.get('IGST', 0) or 0)
    cb = float(row.get('CGST_BOOKS', 0) or row.get('CGST', 0) or 0)
    sb = float(row.get('SGST_BOOKS', 0) or row.get('SGST', 0) or 0)
    tg = float(row.get('Taxable Value_GST', 0) or 0)
    ig = float(row.get('IGST_GST', 0) or 0)
    cg = float(row.get('CGST_GST', 0) or 0)
    sg = float(row.get('SGST_GST', 0) or 0)
    return dict(inv_b=inv_b, inv_g=inv_g, inv=d_inv, date=d_date,
                tb=tb, ib=ib, cb=cb, sb=sb,
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
        st = row.get('Recon_Status', 'DEFAULT')
        groups.setdefault(st, []).append(row)

    total_inv   = sum(len(v) for v in groups.values())
    total_tax_b = sum(float(r.get('Taxable Value_BOOKS', 0) or 0)
                      for rows in groups.values() for r in rows)
    today = pd.Timestamp.now().strftime('%d %b %Y')

    # ── STATUS CONFIG ─────────────────────────────────────────────────────────
    STATUS_ICONS  = {
        'Invoices Not in GSTR-2B':        '🔴',
        'Invoices Not in Purchase Books':  '🟠',
        'AI Matched (Mismatch)':           '🔴',
        'Matched (Tax Error)':             '🟠',
        'AI Matched (Date Mismatch)':      '🔵',
        'AI Matched (Invoice Mismatch)':   '🔵',
        'Old ITC (Previous Year)':         '🟣',
        'Suggestion':                      '🔵',
        'Manually Linked':                 '🟢',
    }
    STATUS_ACTION = {
        'Invoices Not in GSTR-2B':        'Upload in GSTR-1',
        'Invoices Not in Purchase Books':  'Provide invoice copy / issue CN',
        'AI Matched (Mismatch)':          'Amend invoice values in GSTR-1',
        'Matched (Tax Error)':            'Correct IGST/CGST/SGST breakup',
        'AI Matched (Date Mismatch)':     'Amend invoice date in GSTR-1',
        'AI Matched (Invoice Mismatch)':  'Amend invoice number in GSTR-1',
        'Suggestion':                     'Verify and confirm or amend',
        'Manually Linked':                'Verify amounts match your GSTR-1',
    }

    # ── HEADER ────────────────────────────────────────────────────────────────
    msg  = f"*📋 GST Reconciliation Notice*\n"
    msg += f"{'─' * 30}\n"
    msg += f"*From :* {company_name}\n"
    msg += f"*To   :* {vendor_name}\n"
    msg += f"*Date :* {today}\n"
    msg += f"{'─' * 30}\n\n"
    msg += (f"Our GSTR-2B reconciliation identified *{total_inv} invoice(s)* "
            f"requiring your attention (Taxable: *{fi(total_tax_b)}*).\n\n")

    # ── ISSUE GROUPS ──────────────────────────────────────────────────────────
    for grp_no, (status, rows) in enumerate(groups.items(), 1):
        icon  = STATUS_ICONS.get(status, '⚪')
        short = _get_msg(status, 'short')
        action = STATUS_ACTION.get(status, 'Review and rectify')

        # Group taxable subtotal
        grp_taxable = sum(
            float(r.get('Taxable Value_BOOKS') or r.get('Taxable Value_GST') or 0)
            for r in rows
        )
        grp_tax_gst = sum(float(r.get('Taxable Value_GST', 0) or 0) for r in rows)
        if grp_taxable == 0:
            grp_taxable = grp_tax_gst

        msg += f"{icon} *{grp_no}. {short}*  ({len(rows)} invoice{'s' if len(rows) > 1 else ''})\n"

        # Invoice lines
        for row in rows:
            d = _get_row_data(row)
            inv_str = str(d['inv']) if d['inv'] and str(d['inv']) not in ('', 'nan') else '—'

            if 'Not in GSTR-2B' in status:
                val_line = f"Taxable {fi(d['tb'])}  |  Total *{fi(d['tot_b'])}*"
            elif 'Not in Purchase Books' in status or 'Old ITC' in status:
                val_line = f"Portal Taxable {fi(d['tg'])}  |  Total *{fi(d['tot_g'])}*"
            else:
                diff = abs(d['tot_b'] - d['tot_g'])
                if diff > 0.5:
                    val_line = (f"Books {fi(d['tot_b'])}  Portal {fi(d['tot_g'])}"
                                f"  ⚠ *Diff {fi(diff)}*")
                else:
                    val_line = f"Total *{fi(d['tot_b'])}*  ✓ values match"

            msg += f"   • Inv *{inv_str}*  |  {d['date']}\n"
            msg += f"     {val_line}\n"

        msg += f"   _Subtotal: {fi(grp_taxable)}  |  Action: {action}_\n\n"

    # ── FOOTER ────────────────────────────────────────────────────────────────
    msg += f"{'─' * 30}\n"
    msg += (f"⚠ *Kindly action all the above before your next GSTR-1 filing "
            f"and reply to confirm once done.*\n\n")
    msg += f"_Auto-generated by GST Reconciliation Tool — {company_name}_"
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



# ══════════════════════════════════════════════════════════════════════════════
# TARGETED NOTICE GENERATORS — Category-specific, all 3 languages
# ══════════════════════════════════════════════════════════════════════════════

_CAT_STATUS = {
    'not_in_2b':    'Invoices Not in GSTR-2B',
    'not_in_books': 'Invoices Not in Purchase Books',
}

_CAT_TEMPLATES = {
    'not_in_2b': {
        'en': {
            'title':   '📋 *GST Notice — Invoices Missing from GSTR-2B*',
            'intro':   'During our GSTR-2B reconciliation, we found *{n} invoice(s)* recorded in our Purchase Books that are *NOT reflecting in your GSTR-2B / GSTR-1 filing* (Total Taxable: *{tax}*).',
            'col_label': 'Inv No. (Our Books)',
            'action':  '⚠ *Please upload all listed invoices in your GSTR-1 at the earliest and reply to confirm.*',
            'footer':  '🔴 Failure to upload may result in ITC reversal under Section 16(2)(aa) of the CGST Act.',
            'auto':    '_Auto-generated by GST Reconciliation Tool — {company}_',
            'row_fmt': '   • Inv *{inv}*  |  Date: {date}\n     Books Taxable *{tb}*  |  Total *{tot}*',
        },
        'hi': {
            'title':   '📋 *GST नोटिस — GSTR-2B में चालान अनुपस्थित*',
            'intro':   'हमारे GSTR-2B सुलह में *{n} चालान* हमारी खरीद बही में हैं परंतु *आपके GSTR-2B/GSTR-1 में नहीं मिले* (कुल कर योग्य: *{tax}*)।',
            'col_label': 'चालान नं. (हमारी बही)',
            'action':  '⚠ *कृपया नीचे दिए सभी चालान GSTR-1 में अपलोड करें और पुष्टि करें।*',
            'footer':  '🔴 अपलोड न करने पर CGST अधिनियम धारा 16(2)(aa) के अंतर्गत ITC वापस लिया जा सकता है।',
            'auto':    '_ऑटो-जनरेटेड — {company}_',
            'row_fmt': '   • चालान *{inv}*  |  दिनांक: {date}\n     कर योग्य *{tb}*  |  कुल *{tot}*',
        },
        'gu': {
            'title':   '📋 *GST નોટિસ — GSTR-2B માં ઇન્વૉઇસ ગેરહાજર*',
            'intro':   'અમારા GSTR-2B સમાધાનમાં *{n} ઇન્વૉઇસ* અમારી ખરીદ બહી માં છે પરંતુ *તમારા GSTR-2B/GSTR-1 માં નથી* (કુલ કરપાત્ર: *{tax}*).',
            'col_label': 'ઇન્વૉઇસ નં. (અમારી બહી)',
            'action':  '⚠ *કૃપા કરીને નીચેના તમામ ઇન્વૉઇસ GSTR-1 માં અપલોડ કરો અને પુષ્ટિ આપો.*',
            'footer':  '🔴 અપલોડ ન કરવાથી CGST અધિનિયમ કલમ 16(2)(aa) હેઠળ ITC રિવર્સ થઈ શકે.',
            'auto':    '_ઑટો-જનરેટ — {company}_',
            'row_fmt': '   • ઇન્વૉઇસ *{inv}*  |  તારીખ: {date}\n     કરપાત્ર *{tb}*  |  કુલ *{tot}*',
        },
    },
    'not_in_books': {
        'en': {
            'title':   '📋 *GST Notice — Invoices Not Found in Our Purchase Books*',
            'intro':   'During our GSTR-2B reconciliation, we found *{n} invoice(s)* appearing in the *GST Portal / GSTR-2B* that are *NOT recorded in our Purchase Books* (Total Taxable: *{tax}*).',
            'col_label': 'Inv No. (GST Portal)',
            'action':  '⚠ *Please send us the invoice copy / proof of delivery, OR issue a Credit Note for incorrect entries.*',
            'footer':  '🟠 Without confirmation, we cannot claim ITC for these entries. Please respond at the earliest.',
            'auto':    '_Auto-generated by GST Reconciliation Tool — {company}_',
            'row_fmt': '   • Inv *{inv}*  |  Date: {date}\n     Portal Taxable *{tb}*  |  Total *{tot}*',
        },
        'hi': {
            'title':   '📋 *GST नोटिस — हमारी खरीद बही में चालान अनुपस्थित*',
            'intro':   'हमारे GSTR-2B सुलह में *{n} चालान* GST पोर्टल में दर्ज हैं परंतु *हमारी खरीद बही में नहीं मिले* (कुल कर योग्य: *{tax}*)।',
            'col_label': 'चालान नं. (GST पोर्टल)',
            'action':  '⚠ *कृपया चालान की प्रति / डिलीवरी का प्रमाण भेजें, या गलत प्रविष्टि के लिए क्रेडिट नोट जारी करें।*',
            'footer':  '🟠 पुष्टि के बिना हम इन प्रविष्टियों पर ITC दावा नहीं कर सकते।',
            'auto':    '_ऑटो-जनरेटेड — {company}_',
            'row_fmt': '   • चालान *{inv}*  |  दिनांक: {date}\n     पोर्टल कर योग्य *{tb}*  |  कुल *{tot}*',
        },
        'gu': {
            'title':   '📋 *GST નોટિસ — અમારી ખરીદ બહી માં ઇન્વૉઇસ ગેરહાજર*',
            'intro':   'અમારા GSTR-2B સમાધાનમાં *{n} ઇન્વૉઇસ* GST પોર્ટલ પર છે પરંતુ *અમારી ખરીદ બહી માં નથી* (કુલ કરપાત્ર: *{tax}*).',
            'col_label': 'ઇન્વૉઇસ નં. (GST પોર્ટલ)',
            'action':  '⚠ *કૃપા કરીને ઇન્વૉઇસ નકલ / ડિલિવરી પ્રૂફ મોકલો, અથવા ભૂલ ભરેલ એન્ટ્રી માટે ક્રેડિટ નોટ ઇશ્યૂ કરો.*',
            'footer':  '🟠 પુષ્ટિ વગર અમે આ એન્ટ્રીઓ પર ITC ક્લેઇમ કરી શકીએ નહીં.',
            'auto':    '_ઑટો-જનરેટ — {company}_',
            'row_fmt': '   • ઇન્વૉઇસ *{inv}*  |  તારીખ: {date}\n     પોર્ટલ કરપાત્ર *{tb}*  |  કુલ *{tot}*',
        },
    },
}


def generate_targeted_notice(df, vendor_name, company_name, category='not_in_2b', lang='en'):
    """
    Generate a focused WhatsApp/notice message for a specific category only.
    category: 'not_in_2b' or 'not_in_books'
    lang:     'en', 'hi', 'gu'
    """
    status_filter = _CAT_STATUS[category]
    T = _CAT_TEMPLATES[category][lang]

    vendor_df = df[
        (df['Name of Party'] == vendor_name) &
        df['Recon_Status'].str.contains(status_filter.replace('(','\\(').replace(')','\\)'), na=False, regex=True)
    ].copy()

    if vendor_df.empty:
        return ""

    today = pd.Timestamp.now().strftime('%d %b %Y')
    total_inv = len(vendor_df)

    # Value column depends on category
    if category == 'not_in_2b':
        total_tax = float(vendor_df.apply(
            lambda r: float(r.get('Taxable Value_BOOKS') or r.get('Taxable Value') or 0), axis=1
        ).sum())
    else:
        total_tax = float(vendor_df.apply(
            lambda r: float(r.get('Taxable Value_GST') or r.get('Taxable Value') or 0), axis=1
        ).sum())

    msg  = f"{T['title']}\n"
    msg += f"{'─' * 32}\n"
    msg += f"*From :* {company_name}\n"
    msg += f"*To   :* {vendor_name}\n"
    msg += f"*Date :* {today}\n"
    msg += f"{'─' * 32}\n\n"
    msg += T['intro'].format(n=total_inv, tax=fi(total_tax)) + "\n\n"
    msg += f"*{T['col_label']}:*\n"

    for _, row in vendor_df.iterrows():
        d = _get_row_data(row)
        inv_str = d['inv_b'] if category == 'not_in_2b' else (d['inv_g'] or d['inv'])
        if not inv_str or inv_str in ('', 'nan', '—'):
            inv_str = '—'
        if category == 'not_in_2b':
            tb_str  = fi(d['tb'])
            tot_str = fi(d['tot_b'])
        else:
            tb_str  = fi(d['tg'])
            tot_str = fi(d['tot_g'])

        msg += T['row_fmt'].format(inv=inv_str, date=d['date'],
                                   tb=tb_str, tot=tot_str) + "\n"

    msg += f"\n{T['action']}\n\n"
    msg += f"{'─' * 32}\n"
    msg += T['footer'] + "\n\n"
    msg += T['auto'].format(company=company_name)
    return msg


def get_vendors_by_category(df, category='not_in_2b'):
    """Return sorted list of vendors who have issues in the given category only."""
    status_filter = _CAT_STATUS.get(category, '')
    if not status_filter:
        return []
    mask = df['Recon_Status'].str.contains(
        status_filter.replace('(','\\(').replace(')','\\)'), na=False, regex=True
    )
    vendors = df[mask]['Name of Party'].dropna().unique().tolist()
    return sorted([v for v in vendors if v and str(v) != 'nan'])



_HINDI = {
    'title':      '📋 *GST सुलह (Reconciliation) नोटिस*',
    'from':       'से',
    'to':         'को',
    'date_lbl':   'दिनांक',
    'intro':      'हमारे GSTR-2B सुलह में *{n} चालान* में विसंगति पाई गई (कर योग्य: *{tax}*)।',
    'subtotal':   'उप-योग: {tax}  |  कार्रवाई: {action}',
    'footer':     '⚠ *कृपया अगली GSTR-1 दाखिल करने से पहले उपरोक्त सभी प्रविष्टियों पर कार्रवाई करें और पुष्टि करें।*',
    'auto':       'ऑटो-जनरेटेड — {company}',
    'actions': {
        'Invoices Not in GSTR-2B':        'GSTR-1 में अपलोड करें',
        'Invoices Not in Purchase Books':  'चालान प्रति / CN जारी करें',
        'AI Matched (Mismatch)':          'GSTR-1 में मूल्य संशोधित करें',
        'Matched (Tax Error)':            'IGST/CGST/SGST सुधारें',
        'AI Matched (Date Mismatch)':     'GSTR-1 में दिनांक संशोधित करें',
        'AI Matched (Invoice Mismatch)':  'GSTR-1 में चालान संख्या सुधारें',
        'Suggestion':                     'सत्यापित करें और पुष्टि करें',
        'Manually Linked':                'राशि सत्यापित करें',
        'DEFAULT':                        'समीक्षा करें और सुधारें',
    },
}

_GUJARATI = {
    'title':      '📋 *GST સમાધાન (Reconciliation) નોટિસ*',
    'from':       'તરફથી',
    'to':         'માટે',
    'date_lbl':   'તારીખ',
    'intro':      'અમારા GSTR-2B સમાધાનમાં *{n} ઇન્વૉઇસ* માં વિસંગતતા જોવા મળી (કરપાત્ર: *{tax}*).',
    'subtotal':   'પેટા-સરવાળો: {tax}  |  ક્રિયા: {action}',
    'footer':     '⚠ *કૃપા કરીને આગામી GSTR-1 ફાઇલ કરતા પહેલા ઉપરોક્ત તમામ પ્રવિષ્ટિઓ પર કાર્ય કરો અને પુષ્ટિ આપો.*',
    'auto':       'ઑટો-જનરેટ — {company}',
    'actions': {
        'Invoices Not in GSTR-2B':        'GSTR-1 માં અપલોડ કરો',
        'Invoices Not in Purchase Books':  'ઇન્વૉઇસ નકલ / CN આપો',
        'AI Matched (Mismatch)':          'GSTR-1 માં મૂલ્ય સુધારો',
        'Matched (Tax Error)':            'IGST/CGST/SGST સુધારો',
        'AI Matched (Date Mismatch)':     'GSTR-1 માં તારીખ સુધારો',
        'AI Matched (Invoice Mismatch)':  'GSTR-1 માં ઇન્વૉઇસ નં. સુધારો',
        'Suggestion':                     'ચકાસો અને પુષ્ટિ આપો',
        'Manually Linked':                'રકમ ચકાસો',
        'DEFAULT':                        'સમીક્ષા કરો અને સુધારો',
    },
}


def _get_action_lang(status, lang_dict):
    for k in lang_dict['actions']:
        if k != 'DEFAULT' and k in str(status):
            return lang_dict['actions'][k]
    return lang_dict['actions']['DEFAULT']


def generate_whatsapp_message_multilang(df, vendor_name, company_name, lang='hi'):
    """
    lang: 'hi' = Hindi, 'gu' = Gujarati
    Produces same structure as English version but in the chosen language.
    """
    L = _HINDI if lang == 'hi' else _GUJARATI

    vendor_df = df[
        (df['Name of Party'] == vendor_name) &
        df['Recon_Status'].str.contains(ISSUE_MASK, na=False)
    ].copy()

    if vendor_df.empty:
        return ""

    groups = {}
    for _, row in vendor_df.iterrows():
        st = row.get('Recon_Status', 'DEFAULT')
        groups.setdefault(st, []).append(row)

    total_inv   = sum(len(v) for v in groups.values())
    total_tax_b = sum(float(r.get('Taxable Value_BOOKS', 0) or 0)
                      for rows in groups.values() for r in rows)
    today = pd.Timestamp.now().strftime('%d %b %Y')

    STATUS_ICONS = {
        'Invoices Not in GSTR-2B':        '🔴',
        'Invoices Not in Purchase Books':  '🟠',
        'AI Matched (Mismatch)':           '🔴',
        'Matched (Tax Error)':             '🟠',
        'AI Matched (Date Mismatch)':      '🔵',
        'AI Matched (Invoice Mismatch)':   '🔵',
        'Suggestion':                      '🔵',
        'Manually Linked':                 '🟢',
    }

    msg  = f"{L['title']}\n"
    msg += f"{'─' * 30}\n"
    msg += f"*{L['from']} :* {company_name}\n"
    msg += f"*{L['to']}   :* {vendor_name}\n"
    msg += f"*{L['date_lbl']}:* {today}\n"
    msg += f"{'─' * 30}\n\n"
    msg += L['intro'].format(n=total_inv, tax=fi(total_tax_b)) + "\n\n"

    for grp_no, (status, rows) in enumerate(groups.items(), 1):
        icon   = STATUS_ICONS.get(status, '⚪')
        short  = _get_msg(status, 'short')
        action = _get_action_lang(status, L)

        grp_taxable = sum(
            float(r.get('Taxable Value_BOOKS') or r.get('Taxable Value_GST') or 0)
            for r in rows
        ) or sum(float(r.get('Taxable Value_GST', 0) or 0) for r in rows)

        msg += f"{icon} *{grp_no}. {short}*  ({len(rows)})\n"
        for row in rows:
            d = _get_row_data(row)
            inv_str = str(d['inv']) if d['inv'] and str(d['inv']) not in ('', 'nan') else '—'
            if 'Not in GSTR-2B' in status:
                val_line = f"Taxable {fi(d['tb'])}  |  Total *{fi(d['tot_b'])}*"
            elif 'Not in Purchase Books' in status:
                val_line = f"Portal Taxable {fi(d['tg'])}  |  Total *{fi(d['tot_g'])}*"
            else:
                diff = abs(d['tot_b'] - d['tot_g'])
                val_line = (f"Books {fi(d['tot_b'])}  Portal {fi(d['tot_g'])}"
                            + (f"  ⚠ *Diff {fi(diff)}*" if diff > 0.5 else ""))
            msg += f"   • Inv *{inv_str}*  |  {d['date']}\n"
            msg += f"     {val_line}\n"

        msg += f"   _{L['subtotal'].format(tax=fi(grp_taxable), action=action)}_\n\n"

    msg += f"{'─' * 30}\n"
    msg += L['footer'] + "\n\n"
    msg += f"_{L['auto'].format(company=company_name)}_"
    return msg
