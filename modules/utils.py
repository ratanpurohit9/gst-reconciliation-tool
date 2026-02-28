# modules/utils.py  — v4.0
# Removed streamlit_lottie / requests dependency entirely.
# Uses native Streamlit progress bar — no external packages needed.

import streamlit as st
import time

def show_processing_animation():
    """
    Shows a clean native progress animation during reconciliation.
    No external dependencies required.
    """
    steps = [
        (15,  "🔍 Loading and cleaning data..."),
        (30,  "🧹 Normalizing invoice numbers and dates..."),
        (50,  "🔗 Step 1-2: Exact match & date mismatch passes..."),
        (65,  "🤖 Step 3-4: Invoice & numeric key AI passes..."),
        (80,  "💡 Step 5-6: Smart suggestions & group matching..."),
        (92,  "📊 Finalizing results and computing KPIs..."),
        (100, "✅ Reconciliation complete!"),
    ]
    bar = st.progress(0, text="Initializing reconciliation engine...")
    for pct, msg in steps:
        time.sleep(0.2)
        bar.progress(pct, text=msg)
    time.sleep(0.3)
    bar.empty()