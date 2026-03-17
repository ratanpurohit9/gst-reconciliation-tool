# modules/utils.py  — v5.0
import streamlit as st
import time

def show_processing_animation():
    placeholder = st.empty()

    steps = [
        (8,  "🔍",  "Loading & Validating Data",      "Parsing Books and GSTR-2B files, checking column structure…"),
        (18, "🧹",  "Cleaning & Normalising",          "Standardising invoice numbers, dates, GSTIN formats…"),
        (32, "🔗",  "Exact Match  (Pass 1)",            "Matching invoice number + date + tax amount exactly…"),
        (44, "📅",  "Date-Mismatch Match  (Pass 2)",    "Same invoice, different dates — flagging for review…"),
        (55, "🤖",  "AI Invoice Match  (Pass 3)",       "Fuzzy invoice-number matching using similarity scoring…"),
        (66, "🔢",  "Numeric Key Match  (Pass 4)",      "Matching by taxable value + GST combinations…"),
        (76, "💡",  "Smart Suggestions  (Pass 5)",      "Cross-GSTIN suggestions for potential matches…"),
        (86, "🔗",  "Group Match  (Pass 6)",            "Grouping invoices by GSTIN for bulk reconciliation…"),
        (94, "📊",  "Computing KPIs & Summary",         "Calculating totals, differences and compliance metrics…"),
        (100,"✅",  "Reconciliation Complete!",         "All passes finished — preparing results…"),
    ]

    CSS = """
<style>
@keyframes spin   { to{transform:rotate(360deg)} }
@keyframes fadein { from{opacity:0;transform:translateY(5px)} to{opacity:1;transform:translateY(0)} }
@keyframes pulse  { 0%,100%{opacity:1} 50%{opacity:.35} }
.rw { background:linear-gradient(135deg,#0D1B2A 0%,#152232 60%,#0D1B2A 100%);
      border-radius:16px; padding:32px 38px; margin:4px 0;
      border:1px solid #1E3A5F; box-shadow:0 8px 32px rgba(0,0,0,.45); }
.rb { font-size:10px; letter-spacing:3px; color:#4FC3F7; font-weight:700;
      text-transform:uppercase; margin-bottom:4px; }
.rt { font-size:21px; font-weight:700; color:#fff; margin-bottom:2px; }
.rs { font-size:12px; color:#78909C; margin-bottom:24px; }
.dots span { display:inline-block; width:5px; height:5px; border-radius:50%;
             background:#42A5F5; margin:0 2px; animation:pulse 1.4s ease infinite; }
.dots span:nth-child(2){animation-delay:.22s} .dots span:nth-child(3){animation-delay:.44s}
.bar-bg  { background:#1B2E42; border-radius:99px; height:9px; overflow:hidden; margin-bottom:6px; }
.bar-fill{ height:9px; border-radius:99px;
           background:linear-gradient(90deg,#1565C0 0%,#42A5F5 60%,#80DEEA 100%);
           box-shadow:0 0 10px rgba(66,165,245,.55); }
.pct { font-size:11px; color:#64B5F6; text-align:right; margin-bottom:18px; }
.si  { font-size:26px; margin-right:11px; }
.sn  { font-size:14px; font-weight:600; color:#E3F2FD; animation:fadein .35s ease; }
.sd  { font-size:11px; color:#607D8B; margin-top:2px; }
.spinner { display:inline-block; width:14px; height:14px; border:2px solid #1E3A5F;
           border-top-color:#42A5F5; border-radius:50%; animation:spin .75s linear infinite;
           vertical-align:middle; margin-left:8px; }
.log { margin-top:20px; border-top:1px solid #1E3A5F; padding-top:12px; }
.lr  { font-size:11px; padding:2px 0; animation:fadein .3s ease; color:#546E7A; }
.lr.d{ color:#4CAF50; } .lr.a{ color:#42A5F5; font-weight:600; }
</style>"""

    def _html(pct, icon, name, desc, done):
        log = "".join(f'<div class="lr d">✓ {n}</div>' for _,_,n,_ in done)
        log += f'<div class="lr a"><span class="spinner"></span>&nbsp; {name}</div>'
        return f"""{CSS}
<div class="rw">
  <div class="rb">GSTSuite Enterprise · Reconciliation Engine</div>
  <div class="rt">Processing Your Data</div>
  <div class="rs">Multi-pass AI matching in progress &nbsp;<span class="dots"><span></span><span></span><span></span></span></div>
  <div class="bar-bg"><div class="bar-fill" style="width:{pct}%;transition:width .55s cubic-bezier(.4,0,.2,1)"></div></div>
  <div class="pct">{pct}% complete</div>
  <div style="display:flex;align-items:flex-start">
    <span class="si">{icon}</span>
    <div><div class="sn">{name}</div><div class="sd">{desc}</div></div>
  </div>
  <div class="log">{log}</div>
</div>"""

    done = []
    for pct, icon, name, desc in steps:
        placeholder.markdown(_html(pct, icon, name, desc, done), unsafe_allow_html=True)
        time.sleep(0.15 if pct < 90 else 0.28)
        done.append((pct, icon, name, desc))

    time.sleep(0.35)
    placeholder.empty()
