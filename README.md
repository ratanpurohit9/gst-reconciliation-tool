GST Reconciliation Tool — Quick README

Purpose
- Reconcile Purchase Register vs GSTR-2B (B2B, B2BA, CDNR).
- Produce reports, per-vendor notices, and store reconciliation history.

Quick run
1. Install dependencies:
```bash
python -m pip install -r requirements.txt
```
2. Launch the app:
```bash
python run_app.py
# or
streamlit run app.py
```

High-level execution steps (what happens when you run)
1. `run_app.py` -> launches Streamlit to run `app.py`.
2. `app.py` initializes DB (`modules/db_handler.py:init_db`) and session state.
3. Upload files in UI; files passed as file-like objects to the app.
4. Loader: `modules/data_utils.py:load_data_preview` locates sheet/header and returns DataFrame.
5. CDNR handlers (`modules/cdnr_processor.py`) detect credit notes and flip amounts (negative).
6. Amendments: `modules/pre_processor.py:smart_read_b2ba` reads B2BA; `process_amendments` kills & replaces originals.
7. Column mapping: UI suggests mappings using `modules/constants.py` and `modules/data_utils.py:find_best_match`.
8. Normalize invoice numbers: `modules/data_utils.py:standardize_invoice_numbers`.
9. Preprocess: `modules/data_cleaner.py:process_dataset` parses dates, creates `Clean_Inv`, aggregates multi-rate invoices.
10. Reconciliation: `modules/core_engine.py:run_reconciliation`
    - Applies manual links (if any).
    - Creates keys (K1..K5) and runs ordered merge passes via `perform_merge_pass`:
      - Exact (GSTIN+Invoice+Date) → `Matched`.
      - Date mismatch → `AI Matched (Date Mismatch)`.
      - Invoice mismatch → `AI Matched (Invoice Mismatch)`.
      - Numeric/value-based matches → `AI Matched (Mismatch)`.
      - Optional smart suggestions (Inv+Value, Date+Value, value-neighbors) → `Suggestion`.
      - Group matching by GSTIN totals → `Suggestion (Group Match)`.
    - Leftovers labelled: "Invoices Not in GSTR-2B" or "Invoices Not in Purchase Books".
    - Post-process: coalesce GSTIN/Name columns, mark tax errors, drop helper keys.
11. Persist: `modules/db_handler.py:save_reconciliation` stores JSON of result in `recon_history.db`.
12. UI: dashboard, tables, manual matcher, vendor comms generated from `modules/email_tool.py` and `modules/pdf_gen.py`.
13. Export: `modules/report_gen.py` produces Excel workbook(s) and vendor ZIPs; `modules/pdf_gen.py` produces PDF notices.
14. Files saved to `GST_Clients_Data/<Client>_<GSTIN>/<FY>/<Period>` via `modules/file_manager.py`.

Key files
- App: [app.py](app.py) and launcher [run_app.py](run_app.py)
- Engine: [modules/core_engine.py](modules/core_engine.py)
- Preprocessing: [modules/pre_processor.py](modules/pre_processor.py), [modules/cdnr_processor.py](modules/cdnr_processor.py)
- Cleaning: [modules/data_cleaner.py](modules/data_cleaner.py)
- I/O & utils: [modules/data_utils.py](modules/data_utils.py), [modules/file_manager.py](modules/file_manager.py)
- Persistence & reports: [modules/db_handler.py](modules/db_handler.py), [modules/report_gen.py](modules/report_gen.py), [modules/pdf_gen.py](modules/pdf_gen.py)
- Comms: [modules/email_tool.py](modules/email_tool.py)
- Config: [modules/constants.py](modules/constants.py)

Troubleshooting tips
- If sheet detection fails, use the UI column-mapping panel to manually map columns.
- If B2BA parsing fails, inspect the "Read me" or the B2BA sheet format — `smart_read_b2ba` uses positional mapping.
- For unknown vendor names, use the Vendor Comms tab to correct names or use the GST portal captcha helper (requires `modules/gst_scraper.py`).
- Inspect `recon_history.db` (SQLite) for saved results.

Optional next steps
- Create `requirements.txt` (provided) and unit-tests for `run_reconciliation`.
- Add a visual flowchart (Mermaid) or PNG for quick onboarding.

Contact / Notes
- The codebase uses Streamlit UI; most heavy logic is in `modules/core_engine.py`.
- For fixes, start by adding tests that exercise each matching pass.

