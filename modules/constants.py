# modules/constants.py

REQUIRED_FIELDS = {
    'GSTIN': 'GSTIN',
    'Name of Party': 'Party Name',
    'Invoice Number': 'Invoice No',
    'Invoice Date': 'Date',
    'Invoice Value': 'Inv Value',
    'Taxable Value': 'Taxable',
    'IGST': 'IGST',
    'CGST': 'CGST',
    'SGST': 'SGST',
    'Cess': 'Cess',
    'Place of Supply': 'POS',
    'Reverse Charge': 'RCM'
}

FIXED_BOOKS_MAPPING = {
    'GSTIN': 'GSTIN of Supplier',
    'Name of Party': '<No Column / Blank>',
    'Invoice Number': 'Invoice Number',
    'Invoice Date': 'Invoice date',
    'Invoice Value': 'Invoice Value',
    'Taxable Value': 'Taxable Value',
    'IGST': 'Integrated Tax Paid',
    'CGST': 'Central Tax Paid',
    'SGST': 'State/UT Tax Paid',
    'Cess': 'Cess Paid',
    'Place of Supply': 'Place Of Supply',
    'Reverse Charge': 'Reverse Charge'
}

FIXED_GST_MAPPING = {
    'GSTIN': 'GSTIN',
    'Name of Party': 'Trade/Legal name',
    'Invoice Number': 'Invoice number',
    'Invoice Date': 'Invoice Date',
    'Invoice Value': 'Invoice Value(₹)',
    'Taxable Value': 'Taxable Value (₹)',
    'IGST': 'Integrated Tax(₹)',
    'CGST': 'Central Tax(₹)',
    'SGST': 'State/UT Tax(₹)',
    'Cess': 'Cess(₹)',
    'Place of Supply': 'Place of supply',
    'Reverse Charge': 'Supply Attract Reverse Charge'
}

# ── Software-specific column name mappings ────────────────────────────────────
# Each key = software name shown to user
# Each value = dict mapping our REQUIRED_FIELDS keys → column names in that software's export
SOFTWARE_COLUMN_PROFILES = {

    "Standard / GST Portal": {
        'GSTIN': ['GSTIN of Supplier', 'GSTIN', 'Supplier GSTIN'],
        'Name of Party': ['Trade/Legal name', 'Party Name', 'Supplier Name', 'Name'],
        'Invoice Number': ['Invoice Number', 'Invoice No', 'Bill No', 'Inv No'],
        'Invoice Date': ['Invoice date', 'Invoice Date', 'Bill Date', 'Date'],
        'Invoice Value': ['Invoice Value', 'Invoice Value(₹)', 'Bill Amount', 'Total Amount'],
        'Taxable Value': ['Taxable Value', 'Taxable Value (₹)', 'Taxable Amount', 'Assessable Value'],
        'IGST': ['Integrated Tax Paid', 'Integrated Tax(₹)', 'IGST', 'IGST Amount'],
        'CGST': ['Central Tax Paid', 'Central Tax(₹)', 'CGST', 'CGST Amount'],
        'SGST': ['State/UT Tax Paid', 'State/UT Tax(₹)', 'SGST', 'SGST Amount'],
        'Cess': ['Cess Paid', 'Cess(₹)', 'Cess Amount', 'Cess'],
        'Place of Supply': ['Place Of Supply', 'Place of supply', 'POS', 'State'],
        'Reverse Charge': ['Reverse Charge', 'Supply Attract Reverse Charge', 'RCM', 'RC'],
    },

    "Tally Prime / ERP 9": {
        'GSTIN': ['Party GSTIN', 'GSTIN/UIN', 'Supplier GSTIN', 'GSTIN'],
        'Name of Party': ['Party Name', 'Ledger Name', 'Party', 'Name'],
        'Invoice Number': ['Voucher No', 'Bill No', 'Reference No', 'Invoice No', 'Ref No'],
        'Invoice Date': ['Date', 'Voucher Date', 'Bill Date'],
        'Invoice Value': ['Total Amount', 'Grand Total', 'Bill Amount', 'Amount'],
        'Taxable Value': ['Taxable Value', 'Assessable Value', 'Taxable Amount', 'Basic Amount'],
        'IGST': ['IGST', 'Integrated Tax', 'IGST Amount'],
        'CGST': ['CGST', 'Central Tax', 'CGST Amount'],
        'SGST': ['SGST', 'State Tax', 'SGST Amount', 'UTGST'],
        'Cess': ['Cess', 'Cess Amount'],
        'Place of Supply': ['Place of Supply', 'State', 'POS'],
        'Reverse Charge': ['Reverse Charge', 'RCM Applicable', 'RCM'],
    },

    "Zoho Books": {
        'GSTIN': ['GSTIN/UIN', 'Vendor GSTIN', 'Contact GSTIN', 'GSTIN'],
        'Name of Party': ['Vendor Name', 'Contact Name', 'Supplier Name'],
        'Invoice Number': ['Bill Number', 'Purchase Order#', 'Invoice#', 'Reference#'],
        'Invoice Date': ['Bill Date', 'Invoice Date', 'Date'],
        'Invoice Value': ['Total', 'Bill Amount', 'Invoice Amount'],
        'Taxable Value': ['Sub Total', 'Taxable Amount', 'Subtotal'],
        'IGST': ['IGST', 'Integrated GST', 'IGST Amount'],
        'CGST': ['CGST', 'Central GST', 'CGST Amount'],
        'SGST': ['SGST', 'State GST', 'SGST Amount'],
        'Cess': ['Cess', 'Cess Amount'],
        'Place of Supply': ['Place of Supply', 'State', 'Destination State'],
        'Reverse Charge': ['Reverse Charge', 'RCM'],
    },

    "BUSY Accounting": {
        'GSTIN': ['GSTIN No', 'Party GSTIN', 'GSTIN'],
        'Name of Party': ['Party Name', 'Account Name', 'Ledger'],
        'Invoice Number': ['Bill No', 'Voucher No', 'Invoice No'],
        'Invoice Date': ['Bill Date', 'Date', 'Voucher Date'],
        'Invoice Value': ['Bill Amount', 'Total', 'Net Amount'],
        'Taxable Value': ['Taxable Value', 'Basic Amount', 'Taxable Amt'],
        'IGST': ['IGST Amt', 'IGST', 'Integrated Tax'],
        'CGST': ['CGST Amt', 'CGST', 'Central Tax'],
        'SGST': ['SGST Amt', 'SGST', 'State Tax'],
        'Cess': ['Cess Amt', 'Cess'],
        'Place of Supply': ['Place Of Supply', 'State', 'POS'],
        'Reverse Charge': ['Reverse Charge', 'RCM'],
    },

    "EasyGST / ClearTax": {
        'GSTIN': ['Supplier GSTIN', 'GSTIN of Supplier', 'GSTIN'],
        'Name of Party': ['Supplier Name', 'Trade Name', 'Legal Name'],
        'Invoice Number': ['Invoice Number', 'Document Number', 'Inv No'],
        'Invoice Date': ['Invoice Date', 'Document Date', 'Date'],
        'Invoice Value': ['Invoice Value', 'Total Invoice Value', 'Document Value'],
        'Taxable Value': ['Taxable Value', 'Taxable Amount'],
        'IGST': ['Integrated Tax', 'IGST', 'IGST Amount'],
        'CGST': ['Central Tax', 'CGST', 'CGST Amount'],
        'SGST': ['State Tax', 'SGST', 'SGST Amount'],
        'Cess': ['Cess', 'Cess Amount'],
        'Place of Supply': ['Place of Supply', 'POS'],
        'Reverse Charge': ['Reverse Charge', 'RCM'],
    },

    "Marg ERP": {
        'GSTIN': ['Party GSTIN', 'GST No', 'GSTIN'],
        'Name of Party': ['Account Name', 'Party Name', 'Customer/Supplier Name'],
        'Invoice Number': ['Bill No', 'Voucher No', 'Invoice No'],
        'Invoice Date': ['Bill Date', 'Voucher Date', 'Date'],
        'Invoice Value': ['Net Amount', 'Bill Amount', 'Total'],
        'Taxable Value': ['Taxable Amount', 'Taxable Value', 'Basic Amount'],
        'IGST': ['IGST', 'I.G.S.T'],
        'CGST': ['CGST', 'C.G.S.T'],
        'SGST': ['SGST', 'S.G.S.T'],
        'Cess': ['Cess', 'Cess Amount'],
        'Place of Supply': ['Place of Supply', 'State'],
        'Reverse Charge': ['Reverse Charge', 'RCM'],
    },

    "Custom / Local Software": {
        # Generic fallback — uses all common aliases
        'GSTIN': ['GSTIN', 'GST No', 'GSTIN No', 'Party GSTIN', 'Supplier GSTIN', 'GSTIN/UIN'],
        'Name of Party': ['Name', 'Party Name', 'Supplier Name', 'Vendor Name', 'Account Name', 'Ledger'],
        'Invoice Number': ['Invoice No', 'Bill No', 'Voucher No', 'Inv No', 'Reference No', 'Doc No'],
        'Invoice Date': ['Date', 'Invoice Date', 'Bill Date', 'Voucher Date', 'Doc Date'],
        'Invoice Value': ['Amount', 'Total', 'Net Amount', 'Bill Amount', 'Invoice Value', 'Grand Total'],
        'Taxable Value': ['Taxable', 'Taxable Value', 'Taxable Amount', 'Basic Amount', 'Assessable Value'],
        'IGST': ['IGST', 'Integrated Tax', 'IGST Amt', 'I-GST'],
        'CGST': ['CGST', 'Central Tax', 'CGST Amt', 'C-GST'],
        'SGST': ['SGST', 'State Tax', 'SGST Amt', 'S-GST', 'UTGST'],
        'Cess': ['Cess', 'Cess Amount', 'Cess Amt'],
        'Place of Supply': ['Place of Supply', 'State', 'POS', 'Destination'],
        'Reverse Charge': ['RCM', 'Reverse Charge', 'RCM Applicable'],
    },
}