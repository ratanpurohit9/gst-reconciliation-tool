# modules/dashboard_ui.py
# Renders the GSTSuite landing dashboard / module selector.

from datetime import date

import streamlit as st


DASH_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&display=swap');

.stApp { background: #fcf8fa !important; font-family: 'Inter', sans-serif !important; color: #1b1b1d !important; }
.main .block-container {
    padding: 0 32px 32px !important;
    max-width: 1440px !important;
}
[data-testid="stSidebar"] { display: none !important; }
[data-testid="collapsedControl"] { display: none !important; }
.material-symbols-outlined {
    font-family: 'Material Symbols Outlined';
    font-weight: normal;
    font-style: normal;
    font-size: 24px;
    line-height: 1;
    letter-spacing: normal;
    text-transform: none;
    display: inline-block;
    white-space: nowrap;
    word-wrap: normal;
    direction: ltr;
    -webkit-font-feature-settings: 'liga';
    -webkit-font-smoothing: antialiased;
}

.home-topbar {
    position: sticky;
    top: 0;
    z-index: 50;
    margin: 0 -32px 24px;
    padding: 10px 32px;
    background: #ffffff;
    border-bottom: 1px solid #c6c6cd;
    display: flex;
    align-items: center;
    justify-content: space-between;
}
.home-brand { display: flex; align-items: center; gap: 12px; min-width: 210px; }
.home-logo {
    width: 40px; height: 40px; border-radius: 8px;
    background: #0058be; color: #fff; display: grid; place-items: center;
    box-shadow: 0 8px 18px rgba(0,88,190,.16);
}
.home-app { font-size: 22px; line-height: 24px; color: #0058be; font-weight: 800; }
.home-ver { font-size: 12px; color: #1b1b1d; letter-spacing: .08em; }
.home-nav { display: flex; gap: 40px; align-items: center; }
.home-nav span { color: #1b1b1d; font-size: 15px; }
.home-nav .active { color: #0058be; font-weight: 800; border-bottom: 2px solid #0058be; padding-bottom: 8px; }
.home-actions { display: flex; align-items: center; gap: 16px; }
.home-search {
    width: 240px; height: 44px; border-radius: 22px;
    background: #f0edef; border: 1px solid #c6c6cd; color: #45464d;
    display: flex; align-items: center; gap: 10px; padding: 0 16px; font-size: 13px;
}
.home-fy {
    height: 36px; border: 1px solid #c6c6cd; border-radius: 18px; background: #f6f3f5;
    display: flex; align-items: center; gap: 8px; padding: 0 14px; font-size: 13px; font-weight: 700;
}
.home-icon-btn { width: 36px; height: 36px; display: grid; place-items: center; border-radius: 50%; color: #1b1b1d; }
.home-user { background: #2170e4; color: #fff; }

.trial-banner {
    background: #fcdeb5;
    color: #271901;
    border: 1px solid #dec29a;
    border-radius: 12px;
    padding: 13px 24px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    margin-bottom: 38px;
}
.trial-left { display: flex; align-items: center; gap: 13px; font-size: 16px; }
.trial-key {
    border: 1px solid #c6c6cd;
    background: #fff;
    border-radius: 8px;
    padding: 8px 18px;
    font-weight: 600;
    white-space: nowrap;
}
.home-hero { margin-bottom: 34px; }
.home-hero h1 { font-size: 30px; line-height: 38px; margin: 0 0 4px; color: #000; font-weight: 800; letter-spacing: 0 !important; }
.home-hero p { font-size: 16px; color: #45464d; margin: 0; }
.module-heading { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.module-title { display: flex; align-items: center; gap: 8px; font-size: 24px; font-weight: 800; color: #000; }
.module-live-badge { background: #2170e4; color: #fff; border-radius: 999px; padding: 5px 13px; font-size: 12px; font-weight: 800; }
.module-card {
    min-height: 372px;
    border: 1px solid #c6c6cd;
    border-radius: 12px;
    background: #f6f3f5;
    padding: 28px 28px 24px;
    display: flex;
    flex-direction: column;
    position: relative;
}
.module-card.active {
    background: #fff;
    border: 2px solid #0058be;
    box-shadow: 0 12px 20px -16px rgba(0,88,190,.9);
}
.module-state {
    position: absolute; top: 28px; right: 28px;
    color: #76777d; font-size: 15px; letter-spacing: .14em; text-transform: uppercase;
}
.module-card.active .module-state {
    background: #0058be; color: #fff; border-radius: 4px;
    padding: 4px 7px; font-size: 14px; letter-spacing: 0;
}
.module-num { color: #76777d; font-size: 16px; letter-spacing: .08em; margin-bottom: 18px; text-transform: uppercase; }
.module-card.active .module-num { color: #0058be; }
.module-icon { color: #55779e; font-size: 40px; margin-bottom: 28px; }
.module-card.active .module-icon { color: #0058be; }
.module-card h3 { color: #1b1b1d; font-size: 20px; line-height: 28px; margin: 0 0 8px; letter-spacing: 0 !important; }
.module-card p { color: #66666d; font-size: 14px !important; line-height: 20px !important; margin: 0 0 24px; flex: 1; }
.module-tags { display: flex; flex-wrap: wrap; gap: 5px; margin-bottom: 24px; }
.module-tag {
    border: 1px solid #c6c6cd;
    background: #eae7e9;
    color: #5f6067;
    border-radius: 4px;
    padding: 2px 5px;
    font-size: 10px;
    font-weight: 800;
    text-transform: uppercase;
}
.module-card.active .module-tag { background: #2170e4; color: #fff; border-color: #2170e4; }
.module-open-btn > div > button, .module-soon-btn > div > button {
    border-radius: 8px !important;
    height: 42px !important;
    font-weight: 700 !important;
    font-size: 15px !important;
}
.module-open-btn > div > button {
    background: #0058be !important;
    color: #fff !important;
    border: 1px solid #0058be !important;
}
.module-soon-btn > div > button {
    background: transparent !important;
    color: #8d8e95 !important;
    border: 1px solid #c6c6cd !important;
}
.enterprise-panel {
    margin-top: 24px;
    background: #fff;
    border: 1px solid #c6c6cd;
    border-radius: 12px;
    padding: 40px;
    display: grid;
    grid-template-columns: 2fr 1fr;
    gap: 40px;
}
.enterprise-panel h2 { margin: 0 0 24px; font-size: 24px; color: #000; letter-spacing: 0 !important; }
.enterprise-panel p { font-size: 15px !important; color: #1b1b1d; line-height: 1.65 !important; }
.feature-row { display: grid; grid-template-columns: 1fr 1fr; gap: 50px; margin-top: 36px; }
.feature-item { display: flex; gap: 14px; align-items: flex-start; }
.feature-item .material-symbols-outlined { color: #0058be; font-size: 22px; }
.feature-title { font-size: 15px; font-weight: 800; color: #1b1b1d; }
.feature-sub { font-size: 13px; color: #45464d; line-height: 1.25; }
.support-box {
    border: 1px solid #c6c6cd;
    border-radius: 12px;
    background: #f6f3f5;
    display: grid;
    place-items: center;
    text-align: center;
    padding: 28px;
}
.support-icon {
    width: 64px; height: 64px; border-radius: 50%; background: #fff;
    display: grid; place-items: center; color: #0058be; margin: 0 auto 16px;
}
.support-box h3 { font-size: 20px; margin: 0 0 12px; color: #000; letter-spacing: 0 !important; }
.support-box p { font-size: 13px !important; color: #45464d; margin: 0 0 14px; }
.support-link { color: #0058be; font-weight: 800; }
.home-footer {
    margin: 42px -32px 0;
    padding: 26px 32px 0;
    border-top: 1px solid #c6c6cd;
    display: flex;
    justify-content: space-between;
    color: #1b1b1d;
    font-size: 12px;
}
.home-footer-links { display: flex; gap: 42px; }
@media (max-width: 900px) {
    .home-nav, .home-search { display: none; }
    .trial-banner, .enterprise-panel, .feature-row { display: block; }
    .trial-key { margin-top: 12px; display: inline-block; }
    .support-box { margin-top: 24px; }
}
</style>
"""


MODULES = [
    {
        "num": "Module 01",
        "icon": "bar_chart",
        "name": "GSTR-2B vs GSTR-2A",
        "desc": "Compare portal GSTR-2B with GSTR-2A to identify ITC mismatches and filing gaps.",
        "tags": ["B2B", "ITC Reconciliation", "Portal"],
        "active": False,
    },
    {
        "num": "Module 02",
        "icon": "query_stats",
        "name": "GSTR-2B vs Purchase Register",
        "desc": "Match GSTR-2B portal data against your Purchase Register with fuzzy AI matching and group invoice detection.",
        "tags": ["B2B", "B2BA", "CDNR", "Fuzzy AI"],
        "active": True,
    },
    {
        "num": "Module 03",
        "icon": "local_shipping",
        "name": "GSTR-1 vs E-Way Bill",
        "desc": "Reconcile outward supplies in GSTR-1 against E-Way Bills for compliance checks and movement tracking.",
        "tags": ["GSTR-1", "E-Way Bill", "Outward"],
        "active": False,
    },
    {
        "num": "Module 04",
        "icon": "description",
        "name": "Sales Register vs GSTR-1",
        "desc": "Cross-check your internal Sales Register with GSTR-1 filed data to catch unreported or mismatched sales.",
        "tags": ["Sales", "GSTR-1", "B2C"],
        "active": False,
    },
    {
        "num": "Module 05",
        "icon": "bolt",
        "name": "GSTR-1 vs E-Invoice",
        "desc": "Validate GSTR-1 return against e-invoices generated during the period to ensure auto-population accuracy.",
        "tags": ["GSTR-1", "IRN", "E-Invoice"],
        "active": False,
    },
]


def _fy_label():
    today = date.today()
    fy_start = today.year if today.month >= 4 else today.year - 1
    return f"FY {fy_start}-{str(fy_start + 1)[2:]}"


def render_dashboard():
    """Render the landing page and return the clicked module id."""
    st.markdown(DASH_CSS, unsafe_allow_html=True)

    try:
        from modules.db_handler import get_overdue_followups
        overdue_df = get_overdue_followups(days=7)
        overdue_count = len(overdue_df) if overdue_df is not None and not overdue_df.empty else 0
    except Exception:
        overdue_count = 0

    bell_dot = (
        '<span style="position:absolute;top:4px;right:5px;width:8px;height:8px;border-radius:50%;background:#ba1a1a;"></span>'
        if overdue_count else ""
    )

    st.markdown(f"""
    <div class="home-topbar">
        <div class="home-brand">
            <div class="home-logo"><span class="material-symbols-outlined">account_balance_wallet</span></div>
            <div><div class="home-app">GSTSuite</div><div class="home-ver">Enterprise v9.0</div></div>
        </div>
        <div class="home-nav">
            <span class="active">Dashboard</span><span>Reconciliation</span><span>Returns</span><span>Settings</span>
        </div>
        <div class="home-actions">
            <div class="home-search"><span class="material-symbols-outlined">search</span><span>Search modules...</span></div>
            <div class="home-fy"><span class="material-symbols-outlined" style="font-size:19px">calendar_today</span>{_fy_label()}</div>
            <div class="home-icon-btn" style="position:relative"><span class="material-symbols-outlined">notifications</span>{bell_dot}</div>
            <div class="home-icon-btn home-user"><span class="material-symbols-outlined">person</span></div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    if "lic_banner" in st.session_state and st.session_state["lic_banner"][0] == "trial":
        _msg = st.session_state["lic_banner"][1]
        trial_text = _msg.replace("Trial active -", "Trial active —")
    else:
        trial_text = "Trial active — 7 day(s) remaining. | Enter an activation key to unlock full access."

    st.markdown(f"""
    <div class="trial-banner">
        <div class="trial-left"><span class="material-symbols-outlined">hourglass_empty</span>
            <span><strong>Trial Mode</strong> — {trial_text}</span>
        </div>
        <div class="trial-key">⌁ Enter Activation Key</div>
    </div>
    <div class="home-hero">
        <h1>👋 Welcome to Your Reconciliation Dashboard</h1>
        <p>Select a module below to begin reconciliation. More modules are coming soon.</p>
    </div>
    <div class="module-heading">
        <div class="module-title"><span class="material-symbols-outlined" style="color:#0058be">folder_open</span>Available Modules</div>
        <div class="module-live-badge">1 Module Live • 4 Coming Soon</div>
    </div>
    """, unsafe_allow_html=True)

    clicked_module = None
    row1 = st.columns(3, gap="large")
    row2 = st.columns([1, 1, 1], gap="large")
    card_cols = list(row1) + [row2[0], row2[1]]

    for i, (col, mod) in enumerate(zip(card_cols, MODULES)):
        with col:
            state = "Current Module" if mod["active"] else "Coming Soon"
            card_class = "module-card active" if mod["active"] else "module-card"
            st.markdown(f"""
            <div class="{card_class}">
                <div class="module-state">{state}</div>
                <div class="module-num">{mod['num']}</div>
                <span class="material-symbols-outlined module-icon">{mod['icon']}</span>
                <h3>{mod['name']}</h3>
                <p>{mod['desc']}</p>
                <div class="module-tags">{''.join(f'<span class="module-tag">{tag}</span>' for tag in mod['tags'])}</div>
            </div>
            """, unsafe_allow_html=True)
            if mod["active"]:
                st.markdown('<div class="module-open-btn">', unsafe_allow_html=True)
                if st.button("🚀 Open Workspace", key=f"mod_btn_{i}", use_container_width=True):
                    clicked_module = "MODULE 02"
                st.markdown("</div>", unsafe_allow_html=True)
            else:
                st.markdown('<div class="module-soon-btn">', unsafe_allow_html=True)
                st.button("⌘ Coming Soon", key=f"mod_btn_{i}", use_container_width=True, disabled=True)
                st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("""
    <div class="enterprise-panel">
        <div>
            <h2>Why GSTSuite Enterprise?</h2>
            <p>Our platform is designed for high-stakes financial environments where precision is paramount. We reduce the cognitive load of complex tax reconciliations by leveraging advanced algorithms and a professional-grade interface that ensures no data point is missed.</p>
            <div class="feature-row">
                <div class="feature-item">
                    <span class="material-symbols-outlined">verified_user</span>
                    <div><div class="feature-title">Compliance First</div><div class="feature-sub">Built following the latest GST regulatory frameworks.</div></div>
                </div>
                <div class="feature-item">
                    <span class="material-symbols-outlined">psychology</span>
                    <div><div class="feature-title">AI Matching</div><div class="feature-sub">Fuzzy logic algorithms match records even with minor discrepancies.</div></div>
                </div>
            </div>
        </div>
        <div class="support-box">
            <div>
                <div class="support-icon"><span class="material-symbols-outlined">help</span></div>
                <h3>Need Assistance?</h3>
                <p>Access our priority support line for Enterprise users.</p>
                <div class="support-link">Visit Help Center</div>
            </div>
        </div>
    </div>
    <div class="home-footer">
        <div>© 2024 GSTSuite Enterprise. All rights reserved.</div>
        <div class="home-footer-links"><span>Privacy Policy</span><span>Terms of Service</span><span>Support</span></div>
    </div>
    """, unsafe_allow_html=True)

    return clicked_module
