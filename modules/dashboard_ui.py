# modules/dashboard_ui.py
# ─────────────────────────────────────────────────────────────────────────────
# Renders the main GST Suite Dashboard (module selector landing page)
# Called from app.py before any reconciliation tool logic.
# ─────────────────────────────────────────────────────────────────────────────

import streamlit as st

# ── CSS ───────────────────────────────────────────────────────────────────────
DASH_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500;600&display=swap');

/* Reset Streamlit defaults for dashboard look */
.stApp { background: #F1F4F9 !important; font-family: 'Outfit', sans-serif !important; }
.main .block-container {
    padding-top: 0 !important;
    padding-left: 0 !important;
    padding-right: 0 !important;
    max-width: 100% !important;
}

/* ── DASHBOARD TOPBAR ── */
.d-topbar {
    background: #FFFFFF;
    border-bottom: 1px solid #E2E8F0;
    padding: 0 32px;
    height: 56px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    box-shadow: 0 1px 4px rgba(0,0,0,.05);
    margin-bottom: 0;
}
.d-brand { display: flex; align-items: center; gap: 11px; }
.d-logo {
    width: 36px; height: 36px; border-radius: 10px;
    background: #2563EB;
    display: flex; align-items: center; justify-content: center;
    font-size: 17px;
}
.d-appname { font-size: 1rem; font-weight: 800; color: #0F172A; letter-spacing: -.02em; }
.d-ver { font-size: .62rem; color: #94A3B8; font-family: 'JetBrains Mono', monospace; }
.d-topright { display: flex; align-items: center; gap: 12px; }
.d-fy {
    padding: 5px 13px; border-radius: 7px;
    background: #FFFBEB; border: 1px solid rgba(217,119,6,.22);
    color: #D97706; font-size: .72rem; font-weight: 700;
    font-family: 'JetBrains Mono', monospace;
}
.d-bell {
    width: 32px; height: 32px; border-radius: 7px;
    border: 1px solid #E2E8F0; background: #fff;
    display: flex; align-items: center; justify-content: center;
    font-size: 15px; position: relative; cursor: pointer;
}
.d-bell-dot {
    position: absolute; top: -3px; right: -3px;
    width: 10px; height: 10px; border-radius: 50%;
    background: #DC2626; border: 2px solid #fff;
}

/* ── PAGE BODY ── */
.d-body { padding: 28px 32px 60px; }

/* ── WELCOME ── */
.d-welcome { margin-bottom: 28px; }
.d-welcome-title {
    font-size: 1.5rem; font-weight: 800;
    color: #0F172A; letter-spacing: -.025em; margin-bottom: 5px;
}
.d-welcome-sub { font-size: .88rem; color: #475569; }

/* ── MODULE SECTION HEADER ── */
.d-mod-header {
    display: flex; align-items: center; justify-content: space-between;
    margin-bottom: 18px;
}
.d-mod-title { font-size: 1rem; font-weight: 800; color: #0F172A; display: flex; align-items: center; gap: 9px; }
.d-mod-badge {
    padding: 3px 11px; border-radius: 20px;
    background: #FFFBEB; border: 1px solid rgba(217,119,6,.2);
    color: #D97706; font-size: .68rem; font-weight: 700;
    font-family: 'JetBrains Mono', monospace;
}

/* ── MODULE CARDS ── */
.mod-card {
    background: #FFFFFF;
    border: 1.5px solid #E2E8F0;
    border-radius: 16px;
    padding: 22px 20px 18px;
    box-shadow: 0 1px 4px rgba(0,0,0,.04);
    transition: all .18s;
    height: 100%;
    position: relative;
    overflow: hidden;
}
.mod-card:hover {
    transform: translateY(-3px);
    box-shadow: 0 8px 24px rgba(0,0,0,.09);
    border-color: #CBD5E1;
}
.mod-card.active-card {
    border: 2px solid #2563EB;
    background: linear-gradient(145deg, #EFF6FF 0%, #DBEAFE 100%);
    box-shadow: 0 4px 20px rgba(37,99,235,.15);
}
.mod-card.active-card:hover {
    box-shadow: 0 8px 28px rgba(37,99,235,.22);
}
.mod-num {
    font-size: .64rem; font-weight: 800; letter-spacing: .08em;
    color: #94A3B8; font-family: 'JetBrains Mono', monospace;
    margin-bottom: 10px;
}
.mod-card.active-card .mod-num { color: #93C5FD; }
.mod-icon-wrap {
    width: 46px; height: 46px; border-radius: 13px;
    display: flex; align-items: center; justify-content: center;
    font-size: 21px; margin-bottom: 14px;
    border: 1px solid rgba(0,0,0,.06);
}
.mod-name {
    font-size: .92rem; font-weight: 800; color: #0F172A;
    letter-spacing: -.015em; line-height: 1.3; margin-bottom: 6px;
}
.mod-card.active-card .mod-name { color: #1D4ED8; }
.mod-desc {
    font-size: .74rem; color: #64748B;
    line-height: 1.55; margin-bottom: 14px;
}
.mod-card.active-card .mod-desc { color: #3B82F6; opacity: .85; }
.mod-tag-row { display: flex; flex-wrap: wrap; gap: 5px; margin-bottom: 14px; }
.mod-tag {
    padding: 2px 8px; border-radius: 4px;
    font-size: .62rem; font-weight: 700;
    background: #F1F5F9; color: #64748B;
    font-family: 'JetBrains Mono', monospace;
}
.mod-card.active-card .mod-tag {
    background: rgba(37,99,235,.1); color: #2563EB;
}

/* Active card label */
.current-badge {
    position: absolute; top: 14px; right: 14px;
    background: #2563EB; color: #fff;
    font-size: .6rem; font-weight: 800; letter-spacing: .08em;
    padding: 3px 9px; border-radius: 20px;
    font-family: 'JetBrains Mono', monospace;
    text-transform: uppercase;
}
.soon-badge {
    position: absolute; top: 14px; right: 14px;
    background: #F1F5F9; color: #94A3B8;
    font-size: .6rem; font-weight: 800; letter-spacing: .08em;
    padding: 3px 9px; border-radius: 20px;
    font-family: 'JetBrains Mono', monospace;
    text-transform: uppercase;
}

/* ── ACTIVITY PANEL ── */
.activity-panel {
    background: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 16px;
    padding: 20px 22px;
    box-shadow: 0 1px 3px rgba(0,0,0,.04);
    margin-top: 22px;
}
.activity-title {
    font-size: .88rem; font-weight: 800; color: #0F172A;
    margin-bottom: 14px; display: flex; align-items: center; gap: 8px;
}
.act-row {
    display: flex; align-items: center; gap: 12px;
    padding: 9px 0; border-bottom: 1px solid #F8FAFC;
}
.act-row:last-child { border: none; }
.act-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.act-info { flex: 1; }
.act-name { font-size: .8rem; font-weight: 700; color: #0F172A; }
.act-sub { font-size: .7rem; color: #94A3B8; margin-top: 1px; }
.act-time { font-size: .68rem; color: #CBD5E1; font-family: 'JetBrains Mono', monospace; }

/* ── STREAMLIT BUTTON OVERRIDES for module cards ── */
.mod-open-btn > div > button {
    background: #2563EB !important;
    color: white !important;
    border: none !important;
    border-radius: 9px !important;
    font-weight: 700 !important;
    font-size: 13px !important;
    width: 100% !important;
    box-shadow: 0 2px 8px rgba(37,99,235,.3) !important;
    transition: all .15s !important;
}
.mod-open-btn > div > button:hover {
    background: #1D4ED8 !important;
    box-shadow: 0 4px 14px rgba(37,99,235,.4) !important;
    transform: none !important;
}
.mod-soon-btn > div > button {
    background: #F1F5F9 !important;
    color: #94A3B8 !important;
    border: 1px solid #E2E8F0 !important;
    border-radius: 9px !important;
    font-weight: 600 !important;
    font-size: 12px !important;
    width: 100% !important;
    cursor: default !important;
}
</style>
"""

# ── MODULE DATA ────────────────────────────────────────────────────────────────
MODULES = [
    {
        "num": "MODULE 01",
        "icon": "📊",
        "icon_bg": "#F0F9FF",
        "name": "GSTR-2B vs GSTR-2A",
        "desc": "Compare portal GSTR-2B with GSTR-2A to identify ITC mismatches and filing gaps.",
        "tags": ["B2B", "ITC Reconciliation", "Portal"],
        "active": False,
    },
    {
        "num": "MODULE 02",
        "icon": "📘",
        "icon_bg": "#EFF6FF",
        "name": "GSTR-2B vs Purchase Register",
        "desc": "Match GSTR-2B portal data against your Purchase Register with fuzzy AI matching and group invoice detection.",
        "tags": ["B2B", "B2BA", "CDNR", "Fuzzy AI", "Group Match"],
        "active": True,
    },
    {
        "num": "MODULE 03",
        "icon": "🚚",
        "icon_bg": "#FFFBEB",
        "name": "GSTR-1 vs E-Way Bill",
        "desc": "Reconcile outward supplies in GSTR-1 against E-Way Bills for compliance checks.",
        "tags": ["GSTR-1", "E-Way Bill", "Outward"],
        "active": False,
    },
    {
        "num": "MODULE 04",
        "icon": "📋",
        "icon_bg": "#F0FDF4",
        "name": "Sales Register vs GSTR-1",
        "desc": "Cross-check your Sales Register with GSTR-1 filed data to catch unreported sales.",
        "tags": ["GSTR-1", "Sales", "B2C"],
        "active": False,
    },
    {
        "num": "MODULE 05",
        "icon": "⚡",
        "icon_bg": "#FDF4FF",
        "name": "GSTR-1 vs E-Invoice",
        "desc": "Validate GSTR-1 return against e-invoices generated during the period.",
        "tags": ["GSTR-1", "IRN", "E-Invoice"],
        "active": False,
    },
]

# ── MAIN RENDER FUNCTION ───────────────────────────────────────────────────────
def render_dashboard():
    """
    Renders the full GSTSuite landing dashboard.
    Returns the key of whichever module button was clicked (or None).
    """
    from datetime import date

    # Inject CSS
    st.markdown(DASH_CSS, unsafe_allow_html=True)

    # ── Compute current FY dynamically ───────────────────────────────────────
    _today = date.today()
    _fy_start = _today.year if _today.month >= 4 else _today.year - 1
    _fy_label = f"FY {_fy_start}–{str(_fy_start + 1)[2:]}"

    # ── Load real recent history from DB ─────────────────────────────────────
    try:
        from modules.db_handler import get_history_list, get_overdue_followups
        _hist_df    = get_history_list()
        _overdue_df = get_overdue_followups(days=7)
    except Exception:
        _hist_df    = None
        _overdue_df = None

    # ── TOPBAR ────────────────────────────────────────────────────────────────
    _overdue_count = len(_overdue_df) if _overdue_df is not None and not _overdue_df.empty else 0
    _bell_dot_html = '<div class="d-bell-dot"></div>' if _overdue_count > 0 else ''

    st.markdown(f"""
    <div class="d-topbar">
        <div class="d-brand">
            <div class="d-logo">🛡️</div>
            <div>
                <div class="d-appname">GSTSuite</div>
                <div class="d-ver">Enterprise v9.0</div>
            </div>
        </div>
        <div class="d-topright">
            <div class="d-fy">📅 {_fy_label}</div>
            <div class="d-bell" title="{_overdue_count} overdue follow-up(s)">🔔{_bell_dot_html}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Show overdue alert below topbar if any
    if _overdue_count > 0:
        st.warning(
            f"⚠️ **{_overdue_count} vendor follow-up(s) overdue** (7+ days without response). "
            f"Open a reconciliation and go to **Tab 7 — Follow-up Tracker** to review.",
            icon=None
        )

    # ── PAGE BODY ─────────────────────────────────────────────────────────────
    st.markdown('<div class="d-body">', unsafe_allow_html=True)

    # Welcome
    st.markdown("""
    <div class="d-welcome">
        <div class="d-welcome-title">👋 Welcome to Your Reconciliation Dashboard</div>
        <div class="d-welcome-sub">Select a module below to begin reconciliation. More modules are coming soon.</div>
    </div>
    """, unsafe_allow_html=True)

    # Section header
    st.markdown("""
    <div class="d-mod-header">
        <div class="d-mod-title">🗂️ Available Modules</div>
        <div class="d-mod-badge">1 Module Live · 4 Coming Soon</div>
    </div>
    """, unsafe_allow_html=True)

    # ── 3+2 grid layout for 5 modules ────────────────────────────────────────
    clicked_module = None

    row1_cols = st.columns(3, gap="medium")
    row2_cols = st.columns([1, 3, 3, 1], gap="medium")
    # Row 2: use only the middle 2 columns (indices 1 and 2)
    all_cols = list(row1_cols) + [row2_cols[1], row2_cols[2]]

    for i, (col, mod) in enumerate(zip(all_cols, MODULES)):
        with col:
            is_active = mod["active"]
            card_class = "mod-card active-card" if is_active else "mod-card"
            badge_html = '<div class="current-badge">CURRENT MODULE</div>' if is_active else '<div class="soon-badge">COMING SOON</div>'

            st.markdown(f"""
            <div class="{card_class}">
                {badge_html}
                <div class="mod-num">{mod['num']}</div>
                <div class="mod-icon-wrap" style="background:{mod['icon_bg']}">{mod['icon']}</div>
                <div class="mod-name">{mod['name']}</div>
                <div class="mod-desc">{mod['desc']}</div>
                <div class="mod-tag-row">
                    {''.join(f'<span class="mod-tag">{t}</span>' for t in mod['tags'])}
                </div>
            </div>
            """, unsafe_allow_html=True)

            # Button below the card
            if is_active:
                st.markdown('<div class="mod-open-btn">', unsafe_allow_html=True)
                if st.button("🚀 Open Workspace", key=f"mod_btn_{i}", use_container_width=True):
                    clicked_module = mod["num"]
                st.markdown('</div>', unsafe_allow_html=True)
            else:
                st.markdown('<div class="mod-soon-btn">', unsafe_allow_html=True)
                st.button("🔒 Coming Soon", key=f"mod_btn_{i}", use_container_width=True, disabled=True)
                st.markdown('</div>', unsafe_allow_html=True)

    # ── RECENT ACTIVITY — pulled from real DB ─────────────────────────────────
    st.markdown('<div class="activity-panel"><div class="activity-title">🕐 Recent Activity</div>', unsafe_allow_html=True)

    if _hist_df is not None and not _hist_df.empty:
        _recent = _hist_df.head(4)
        _act_rows_html = ""
        for _, _row in _recent.iterrows():
            _ts = str(_row.get('timestamp', ''))[:16]
            _act_rows_html += f"""
            <div class="act-row">
                <div class="act-dot" style="background:#059669"></div>
                <div class="act-info">
                    <div class="act-name">B2B Reconciliation — {_row.get('company_name', '—')}</div>
                    <div class="act-sub">Module 02 · {_row.get('period','—')} {_row.get('fy','—')} · {_row.get('gstin','—')}</div>
                </div>
                <div class="act-time">{_ts}</div>
            </div>"""

        if _overdue_count > 0:
            _overdue_names = ", ".join(_overdue_df['vendor_name'].head(3).tolist())
            _act_rows_html += f"""
            <div class="act-row">
                <div class="act-dot" style="background:#D97706"></div>
                <div class="act-info">
                    <div class="act-name">{_overdue_count} Follow-up Notice(s) Overdue</div>
                    <div class="act-sub">{_overdue_names}</div>
                </div>
                <div class="act-time">7+ days</div>
            </div>"""

        st.markdown(_act_rows_html + '</div>', unsafe_allow_html=True)
    else:
        st.markdown("""
        <div class="act-row">
            <div class="act-dot" style="background:#94A3B8"></div>
            <div class="act-info">
                <div class="act-name">No reconciliations run yet</div>
                <div class="act-sub">Open Module 02 to run your first reconciliation</div>
            </div>
            <div class="act-time">—</div>
        </div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)  # close d-body

    return clicked_module
