# GST Reconciliation Tool v4.0

A professional GST B2B & CDNR reconciliation tool built with Python + Streamlit.

## Features
- B2B Reconciliation (Books vs GSTR-2B)
- CDNR Processing
- Excel & PDF Report Generation
- History & Audit Log
- Vendor-wise Email/WhatsApp Draft Generator

## How to Run (Cloud)
This app is deployed on Streamlit Cloud.
Open the app link shared with you — no installation needed.

## How to Run (Local)
```bash
pip install -r requirements.txt
streamlit run app.py
```

## Note
- On cloud: history is session-based (resets on server restart)
- On local EXE: history is saved permanently to local database
