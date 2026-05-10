import streamlit as st
import httpx
import os
import asyncio
import json
from datetime import datetime
from httpx_sse import aconnect_sse

# ─────────────────────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="MedVault",
    page_icon="🧬",
    layout="wide",
)

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000/api/v1")

# ─────────────────────────────────────────────────────────────
# FONTS
# ─────────────────────────────────────────────────────────────
st.markdown(
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">',
    unsafe_allow_html=True,
)

# ─────────────────────────────────────────────────────────────
# CSS
# ─────────────────────────────────────────────────────────────
_CSS = """
* { box-sizing: border-box; }
html, body, [data-testid="stApp"] {
    font-family: 'Inter', sans-serif !important;
    background-color: #f1f5f9 !important;
    color: #0f172a !important;
}
.main .block-container { padding: 1.75rem 2.25rem !important; max-width: 100% !important; }
#MainMenu, footer, header { visibility: hidden; }
[data-testid="stDecoration"] { display: none; }

/* ── Sidebar ── */
[data-testid="stSidebar"] {
    background: #ffffff !important;
    border-right: 1px solid #e2e8f0 !important;
    box-shadow: 2px 0 12px rgba(0,0,0,0.04) !important;
}
[data-testid="stSidebar"] > div:first-child { padding-top: 0 !important; }

.sidebar-logo {
    padding: 1.4rem 1.1rem 1rem;
    border-bottom: 1px solid #f1f5f9;
    margin-bottom: 0.75rem; display: flex; align-items: center; gap: 0.6rem;
}
.sidebar-logo-icon { font-size: 1.7rem; }
.sidebar-logo-text h2 {
    font-size: 1rem; font-weight: 800; color: #1e40af; margin: 0; letter-spacing: -0.02em;
}
.sidebar-logo-text span { font-size: 0.75rem; color: #3b82f6; font-weight: 600; letter-spacing: 0.1em; text-transform: uppercase; }

.user-badge {
    display: flex; align-items: center; gap: 0.55rem;
    padding: 0.6rem 0.85rem;
    background: #eff6ff; border: 1px solid #bfdbfe;
    border-radius: 12px; margin: 0 0.2rem 0.75rem;
}
.user-avatar {
    width: 32px; height: 32px; border-radius: 50%;
    background: linear-gradient(135deg,#3b82f6,#6366f1);
    display:flex; align-items:center; justify-content:center;
    font-size:0.8rem; font-weight:700; color:white; flex-shrink:0;
}
.user-name { font-size:0.875rem; font-weight:600; color:#1e40af; }
.user-role { font-size:0.78rem; color:#64748b; }

.sidebar-label {
    font-size: 0.75rem; font-weight: 700; color: #64748b;
    letter-spacing: 0.1em; text-transform: uppercase;
    padding: 0 0.5rem; margin: 0.7rem 0 0.35rem;
}

/* ── Buttons ── */
.stButton > button,
[data-testid="stDownloadButton"] > button {
    font-family: 'Inter', sans-serif !important;
    font-weight: 500 !important; font-size: 0.875rem !important;
    border-radius: 10px !important; border: 1px solid #e2e8f0 !important;
    background: #ffffff !important; color: #475569 !important;
    padding: 0.4rem 1rem !important; transition: all 0.15s ease !important;
    width: 100% !important; text-align: left !important;
    box-shadow: 0 1px 2px rgba(0,0,0,0.05) !important;
}
.stButton > button:hover,
[data-testid="stDownloadButton"] > button:hover {
    background: #f8fafc !important; color: #1e293b !important;
    border-color: #cbd5e1 !important; box-shadow: 0 2px 6px rgba(0,0,0,0.08) !important;
    transform: translateX(2px) !important;
}
.stButton > button[kind="primary"],
[data-testid="stFormSubmitButton"] > button,
[data-testid="baseButton-primary"],
[data-testid="stBaseButton-primary"] {
    background: linear-gradient(135deg,#2563eb,#4f46e5) !important;
    border: none !important; color: #ffffff !important; font-weight: 600 !important;
    box-shadow: 0 2px 8px rgba(37,99,235,0.3) !important;
}
.stButton > button[kind="primary"]:hover,
[data-testid="stFormSubmitButton"] > button:hover,
[data-testid="baseButton-primary"]:hover,
[data-testid="stBaseButton-primary"]:hover {
    background: linear-gradient(135deg,#1d4ed8,#4338ca) !important;
    box-shadow: 0 4px 16px rgba(37,99,235,0.4) !important;
    transform: translateY(-1px) !important;
}

/* ── Inputs — broad reset so Streamlit dark-mode internals don't bleed through ── */
input, textarea, select {
    background: #ffffff !important;
    color: #0f172a !important;
    font-family: 'Inter', sans-serif !important;
}
.stTextInput > div > div > input,
[data-baseweb="input"] input,
[data-baseweb="base-input"] input {
    font-family: 'Inter', sans-serif !important;
    background: #ffffff !important;
    color: #0f172a !important;
    caret-color: #2563eb !important;
    font-size: 0.9rem !important;
    padding: 0.55rem 0.9rem !important;
    border: none !important;
    outline: none !important;
    box-shadow: none !important;
}
[data-baseweb="input"],
[data-baseweb="base-input"] {
    background: #ffffff !important;
    /*border: 1px solid #e2e8f0 !important;*/
    border-radius: 10px !important;
    box-shadow: 0 1px 2px rgba(0,0,0,0.04) !important;
    transition: border-color 0.2s, box-shadow 0.2s !important;
}
[data-baseweb="input"]:focus-within,
[data-baseweb="base-input"]:focus-within {
    border-color: #3b82f6 !important;
    box-shadow: 0 0 0 3px rgba(59,130,246,0.12) !important;
}
[data-baseweb="input"] button,
[data-baseweb="base-input"] button {
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
    color: #94a3b8 !important;
    cursor: pointer !important;
}
[data-baseweb="input"] button:hover,
[data-baseweb="base-input"] button:hover {
    color: #475569 !important;
    background: transparent !important;
}
input:-webkit-autofill,
input:-webkit-autofill:hover,
input:-webkit-autofill:focus {
    -webkit-box-shadow: 0 0 0px 1000px #ffffff inset !important;
    -webkit-text-fill-color: #0f172a !important;
    transition: background-color 5000s ease-in-out 0s !important;
}
.stTextInput label, .stSelectbox label, .stTextArea label {
    font-size: 0.875rem !important; font-weight: 600 !important;
    color: #374151 !important; letter-spacing: 0.01em !important;
}
.stTextArea textarea {
    font-family: 'Inter', sans-serif !important;
    background: #ffffff !important; border: none !important;
    border-radius: 10px !important; color: #0f172a !important; font-size: 0.9rem !important;
    box-shadow: none !important;
}
.stSelectbox > div > div,
[data-testid="stSelectbox"] > div > div {
    background: #ffffff !important; border: 1px solid #e2e8f0 !important;
    border-radius: 10px !important; color: #0f172a !important; font-size: 0.875rem !important;
}

/* ── Tabs ── */
.stTabs [data-baseweb="tab-list"] {
    background: #e2e8f0 !important; border-radius: 12px !important;
    padding: 3px !important; gap: 2px !important; border: none !important;
}
.stTabs [data-baseweb="tab"] {
    background: transparent !important; border-radius: 9px !important;
    color: #64748b !important; font-size: 0.875rem !important;
    font-weight: 500 !important; padding: 0.35rem 1.1rem !important; border: none !important;
}
.stTabs [aria-selected="true"] {
    background: #ffffff !important; color: #1e40af !important; font-weight: 600 !important;
    box-shadow: 0 1px 4px rgba(0,0,0,0.1) !important;
}

/* ── Forms & uploaders ── */
[data-testid="stForm"] {
    background: #ffffff !important; border: 1px solid #e2e8f0 !important;
    border-radius: 16px !important; padding: 1.5rem !important;
    box-shadow: 0 2px 8px rgba(0,0,0,0.06) !important;
}
[data-testid="stFileUploader"] {
    background: #f8fafc !important;
    border: 1.5px dashed #bfdbfe !important;
    border-radius: 12px !important; padding: 0.6rem !important;
    transition: all 0.2s !important;
}
[data-testid="stFileUploader"]:hover { border-color: #3b82f6 !important; background: #eff6ff !important; }
[data-testid="stFileUploader"] section,
[data-testid="stFileUploader"] section > div { background: transparent !important; }
[data-testid="stFileUploader"] label { color: #475569 !important; font-size: 0.82rem !important; }
[data-testid="stFileUploaderDropzoneInstructions"] { color: #64748b !important; font-size: 0.8rem !important; }
/* Upload browse button inside file uploader */
[data-testid="stFileUploader"] button {
    background: #ffffff !important; color: #2563eb !important;
    border: 1px solid #bfdbfe !important; border-radius: 8px !important;
    font-size: 0.82rem !important; font-weight: 600 !important;
    padding: 0.35rem 0.85rem !important; cursor: pointer !important;
    transition: all 0.15s !important;
}
[data-testid="stFileUploader"] button:hover {
    background: #eff6ff !important; border-color: #3b82f6 !important;
    color: #1d4ed8 !important; transform: none !important;
}

/* ── Progress ── */
.stProgress > div > div > div {
    background: linear-gradient(90deg,#2563eb,#6366f1) !important;
    border-radius: 4px !important;
}

/* ── Divider ── */
hr { border-color: #e2e8f0 !important; margin: 0.6rem 0 !important; }

/* ── Cards ── */
.metric-card {
    background: #ffffff; border: 1px solid #e2e8f0; border-radius: 14px;
    padding: 1.2rem 1.3rem; transition: all 0.2s ease;
    box-shadow: 0 1px 4px rgba(0,0,0,0.05);
    position: relative; overflow: hidden;
}
.metric-card::before {
    content:''; position:absolute; top:0; left:0; right:0; height:3px;
    background: linear-gradient(90deg,#2563eb,#6366f1);
}
.metric-card:hover { box-shadow: 0 6px 20px rgba(0,0,0,0.1); transform: translateY(-1px); border-color: #bfdbfe; }
.metric-label { font-size: 0.78rem; color: #64748b; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 0.5rem; }
.metric-value { font-size: 1.7rem; font-weight: 800; color: #0f172a; letter-spacing: -0.03em; }
.metric-sub { font-size: 0.82rem; color: #64748b; margin-top: 0.25rem; }

.doc-card {
    background: #ffffff; border: 1px solid #e2e8f0; border-radius: 14px;
    padding: 1.1rem 1.2rem; margin-bottom: 0; transition: all 0.2s ease;
    box-shadow: 0 1px 4px rgba(0,0,0,0.05);
}
.doc-card:hover {
    border-color: #93c5fd; box-shadow: 0 6px 20px rgba(37,99,235,0.1);
    transform: translateY(-1px);
}
.doc-title { font-size: 0.9rem; font-weight: 600; color: #0f172a; margin-bottom: 0.3rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.doc-meta { font-size: 0.82rem; color: #64748b; }
.doc-badge {
    display: inline-block; padding: 0.18rem 0.6rem; border-radius: 20px;
    font-size: 0.74rem; font-weight: 700; letter-spacing: 0.04em; margin-bottom: 0.55rem; text-transform: uppercase;
}
.badge-blood { background:#fef2f2; color:#dc2626; border:1px solid #fecaca; }
.badge-guideline { background:#eff6ff; color:#2563eb; border:1px solid #bfdbfe; }
.badge-patent { background:#faf5ff; color:#7c3aed; border:1px solid #ddd6fe; }
.badge-research { background:#f0fdf4; color:#16a34a; border:1px solid #bbf7d0; }
.badge-clinical { background:#fffbeb; color:#d97706; border:1px solid #fde68a; }

.page-header {
    padding: 0 0 1.25rem; border-bottom: 1px solid #e2e8f0; margin-bottom: 1.5rem;
}
.page-title { font-size: 1.25rem; font-weight: 800; color: #0f172a; letter-spacing: -0.03em; }
.page-subtitle { font-size: 0.875rem; color: #64748b; margin-top: 0.2rem; }
.status-dot {
    display:inline-flex; align-items:center; gap:0.4rem;
    font-size:0.75rem; color:#16a34a; font-weight:600;
    background:#f0fdf4; padding:0.25rem 0.7rem;
    border-radius:20px; border:1px solid #bbf7d0;
}
.status-dot::before { content:''; width:6px; height:6px; background:#16a34a; border-radius:50%; animation:pulse 2s infinite; }
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.3} }

/* ── Chat bottom bar ── */
[data-testid="stBottom"],
[data-testid="stBottom"] > div,
[data-testid="stBottom"] > div > div,
[data-testid="stBottom"] > div > div > div,
[data-testid="stBottom"] > div > div > div > div,
[data-testid="stBottom"] > div > div > div > div > div,
.stChatFloatingInputContainer,
div:has(> [data-testid="stChatInputContainer"]),
div:has([data-testid="stChatInputContainer"]) {
    background: #f1f5f9 !important;
    background-color: #f1f5f9 !important;
}
[data-testid="stBottom"] {
    border-top: 1px solid #e2e8f0 !important;
    padding: 1rem 1.5rem 1.25rem !important;
}

/* ── Chat messages ── */
[data-testid="stChatMessage"] {
    padding: 0.5rem 0 !important;
    background: transparent !important;
}
[data-testid="stChatMessage"] [data-testid="stMarkdownContainer"],
[data-testid="stChatMessage"] > div,
[data-testid="stChatMessage"] > div > div {
    background: transparent !important;
}
/* User message bubble */
[data-testid="stChatMessage"][data-testid*="user"] > div:last-child,
div[class*="stChatMessage"] > div:nth-child(2) {
    background: #eff6ff !important;
    border-radius: 12px !important;
}
[data-testid="chatAvatarIcon-user"] {
    background: linear-gradient(135deg,#0891b2,#2563eb) !important;
    border: none !important;
    font-size: 1.1rem !important;
}
[data-testid="chatAvatarIcon-assistant"] {
    background: linear-gradient(135deg,#7c3aed,#a855f7) !important;
    border: none !important;
    font-size: 1.1rem !important;
}

/* ── Chat input box ── */
[data-testid="stChatInputContainer"] {
    background: #ffffff !important;
    border: 1.5px solid #bfdbfe !important;
    border-radius: 20px !important;
    padding: 0.45rem 0.6rem 0.45rem 1rem !important;
    box-shadow: 0 4px 24px rgba(37,99,235,0.10), 0 1px 4px rgba(0,0,0,0.06) !important;
    transition: box-shadow 0.2s, border-color 0.2s !important;
}
[data-testid="stChatInputContainer"]:focus-within {
    border-color: #2563eb !important;
    box-shadow: 0 0 0 3px rgba(37,99,235,0.14), 0 4px 24px rgba(37,99,235,0.12) !important;
}
/* Every element inside the chat box → white, regardless of nesting depth */
[data-testid="stChatInputContainer"] *:not(button):not(svg):not(path) {
    background: #ffffff !important;
    background-color: #ffffff !important;
    color: #0f172a !important;
}
[data-testid="stChatInputContainer"] textarea {
    background: #ffffff !important;
    color: #0f172a !important;
    caret-color: #2563eb !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 0.92rem !important;
    border: none !important;
    box-shadow: none !important;
    outline: none !important;
    padding: 0.35rem 0 !important;
}
[data-testid="stChatInputContainer"] textarea::placeholder {
    color: #93c5fd !important;
    font-style: italic !important;
}
/* Submit button */
[data-testid="stChatInputSubmitButton"] > button {
    background: linear-gradient(135deg,#2563eb,#7c3aed) !important;
    border: none !important;
    border-radius: 12px !important;
    color: #ffffff !important;
    width: 38px !important;
    height: 38px !important;
    box-shadow: 0 2px 8px rgba(37,99,235,0.35) !important;
    transition: opacity 0.15s, transform 0.15s !important;
}
[data-testid="stChatInputSubmitButton"] > button:hover {
    opacity: 0.88 !important;
    transform: scale(1.06) !important;
    box-shadow: 0 4px 14px rgba(37,99,235,0.45) !important;
}
[data-testid="stChatInputSubmitButton"] > button svg {
    fill: #ffffff !important;
    stroke: #ffffff !important;
}

/* ── Tool badge ── */
.tool-badge {
    display:inline-flex; align-items:center; gap:0.45rem;
    padding:0.3rem 0.8rem; border-radius:20px; font-size:0.8rem; font-weight:500;
    animation:fadeSlide 0.2s ease;
}
.tool-badge.searching { background:#fffbeb; border:1px solid #fde68a; color:#d97706; }
.tool-badge.done { background:#f0fdf4; border:1px solid #bbf7d0; color:#16a34a; }
@keyframes fadeSlide { from{opacity:0;transform:translateY(4px)} to{opacity:1;transform:none} }

/* ── Thinking dots ── */
.thinking-dots { display:inline-flex; align-items:center; gap:5px; padding:0.4rem 0.75rem; }
.thinking-dots span {
    width:6px; height:6px; background:#3b82f6; border-radius:50%;
    animation:bounce 1.2s infinite ease-in-out;
}
.thinking-dots span:nth-child(2) { animation-delay:0.15s; background:#6366f1; }
.thinking-dots span:nth-child(3) { animation-delay:0.3s; background:#0ea5e9; }
@keyframes bounce { 0%,80%,100%{transform:translateY(0)} 40%{transform:translateY(-6px)} }

/* ── Metrics bar ── */
.metrics-bar { display:flex; gap:1rem; padding:0.3rem 0; font-size:0.78rem; color:#94a3b8; }
.metrics-bar span { display:flex; align-items:center; gap:0.25rem; }

/* ── Info & result boxes ── */
.info-banner {
    background:#eff6ff; border:1px solid #bfdbfe;
    border-radius:12px; padding:0.75rem 1.1rem; font-size:0.875rem; color:#1d4ed8; margin-bottom:1rem;
}
.summary-box {
    background: #f8fafc; border: 1px solid #e2e8f0; border-left: 3px solid #2563eb;
    border-radius: 0 12px 12px 0; padding: 1.1rem 1.3rem;
    font-size: 0.82rem; color: #334155; line-height: 1.75; margin-top: 0.75rem;
}
.compare-header {
    font-size: 0.78rem; font-weight: 700; color: #94a3b8;
    letter-spacing: 0.1em; text-transform: uppercase; margin-bottom: 0.5rem;
}

/* ── Auth page ── */
.auth-logo { text-align:center; margin-bottom:1.75rem; }
.auth-logo .icon {
    font-size: 3rem; display:block; margin-bottom:0.75rem;
    animation: float 3s ease-in-out infinite;
}
@keyframes float { 0%,100%{transform:translateY(0)} 50%{transform:translateY(-5px)} }
.auth-logo h1 { font-size: 1.6rem; font-weight: 800; margin: 0 0 0.3rem; color: #1e40af; letter-spacing: -0.03em; }
.auth-logo p { font-size: 0.875rem; color: #94a3b8; margin: 0; }

/* ── Prompt chips ── */
.welcome-title { font-size:1.1rem; font-weight:700; color:#0f172a; text-align:center; margin-bottom:0.25rem; }
.welcome-sub { font-size:0.875rem; color:#94a3b8; text-align:center; margin-bottom:1.25rem; }

/* ── Activity ── */
.activity-row {
    display:flex; align-items:center; justify-content:space-between;
    padding:0.65rem 0; border-bottom:1px solid #f1f5f9; font-size:0.84rem;
}
.activity-row:last-child { border-bottom:none; }
.activity-type { color:#64748b; }
.activity-cost { color:#2563eb; font-weight:600; }
.activity-time { color:#64748b; font-size:0.8rem; }

/* ── Checkbox ── */
.stCheckbox label { font-size:0.875rem !important; color:#475569 !important; }

/* ── Scrollbar ── */
::-webkit-scrollbar { width:4px; height:4px; }
::-webkit-scrollbar-track { background:#f1f5f9; }
::-webkit-scrollbar-thumb { background:#cbd5e1; border-radius:4px; }
::-webkit-scrollbar-thumb:hover { background:#94a3b8; }
"""

if hasattr(st, "html"):
    st.html(f"<style>{_CSS}</style>")
else:
    st.markdown(f"<style>{_CSS}</style>", unsafe_allow_html=True)

_JS = """
<script>
(function() {
    // Inject placeholder + focus styles that JS can't set directly
    const _s = document.createElement('style');
    _s.textContent = `
        [data-testid="stChatInputContainer"] textarea::placeholder {
            color: #93c5fd !important; font-style: italic !important;
        }
        [data-testid="stChatInputContainer"]:focus-within {
            border-color: #2563eb !important;
            box-shadow: 0 0 0 3px rgba(37,99,235,0.14),
                        0 4px 24px rgba(37,99,235,0.14) !important;
        }
    `;
    document.head.appendChild(_s);

    function styleChat() {
        // ── Bottom bar background ──────────────────────────────
        const bottom = document.querySelector('[data-testid="stBottom"]');
        if (bottom) {
            [bottom, ...bottom.querySelectorAll('*')].forEach(el => {
                const tid = el.getAttribute('data-testid');
                if (tid === 'stChatInputContainer' || el.closest('[data-testid="stChatInputContainer"]')) return;
                el.style.setProperty('background', '#f1f5f9', 'important');
                el.style.setProperty('background-color', '#f1f5f9', 'important');
            });
        }

        // ── Chat input container ───────────────────────────────
        const box = document.querySelector('[data-testid="stChatInputContainer"]');
        if (box && !box._styled) {
            box.style.setProperty('background', '#ffffff', 'important');
            box.style.setProperty('border', '1.5px solid #bfdbfe', 'important');
            box.style.setProperty('border-radius', '20px', 'important');
            box.style.setProperty('padding', '0.35rem 0.5rem 0.35rem 0.85rem', 'important');
            box.style.setProperty('box-shadow', '0 4px 24px rgba(37,99,235,0.10), 0 1px 4px rgba(0,0,0,0.06)', 'important');
            box.style.setProperty('transition', 'box-shadow 0.2s, border-color 0.2s', 'important');
            box._styled = true;
        }

        // ── Submit button ──────────────────────────────────────
        const btnWrap = document.querySelector('[data-testid="stChatInputSubmitButton"]');
        const btn = btnWrap
            ? (btnWrap.tagName === 'BUTTON' ? btnWrap : btnWrap.querySelector('button'))
            : document.querySelector('[data-testid="stChatInputContainer"] button');
        if (btn && !btn._styled) {
            btn.style.setProperty('background', 'linear-gradient(135deg,#2563eb,#7c3aed)', 'important');
            btn.style.setProperty('border', 'none', 'important');
            btn.style.setProperty('border-radius', '12px', 'important');
            btn.style.setProperty('box-shadow', '0 2px 8px rgba(37,99,235,0.40)', 'important');
            btn.style.setProperty('width', '38px', 'important');
            btn.style.setProperty('height', '38px', 'important');
            btn.querySelectorAll('svg, path').forEach(el => {
                el.style.setProperty('fill', '#ffffff', 'important');
                el.style.setProperty('stroke', '#ffffff', 'important');
            });
            btn._styled = true;
        }
    }

    const obs = new MutationObserver(styleChat);
    obs.observe(document.documentElement, { childList: true, subtree: true });
    styleChat();
})();
</script>
"""
st.markdown(_JS, unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────
# SESSION STATE
# ─────────────────────────────────────────────────────────────
defaults = {
    "auth_token": None,
    "user_info": {},
    "messages": [],
    "thread_id": None,
    "active_page": "chat",
    "compare_mode": False,
    "lit_review_result": None,
    "prompt_prefill": None,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ─────────────────────────────────────────────────────────────
# API HELPERS
# ─────────────────────────────────────────────────────────────
def headers():
    return {"Authorization": f"Bearer {st.session_state.auth_token}"} if st.session_state.auth_token else {}

def run(coro):
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)

async def _post(path, **kwargs):
    async with httpx.AsyncClient(timeout=30) as c:
        return await c.post(f"{API_BASE_URL}{path}", headers=headers(), **kwargs)

async def _get(path):
    async with httpx.AsyncClient(timeout=30) as c:
        return await c.get(f"{API_BASE_URL}{path}", headers=headers())

async def _delete(path):
    async with httpx.AsyncClient(timeout=30) as c:
        return await c.delete(f"{API_BASE_URL}{path}", headers=headers())

async def login(username, password):
    async with httpx.AsyncClient() as c:
        r = await c.post(f"{API_BASE_URL}/auth/token", data={"username": username, "password": password})
        return r.json(), r.status_code

async def register(username, password, team):
    async with httpx.AsyncClient() as c:
        r = await c.post(f"{API_BASE_URL}/auth/register", json={"username": username, "password": password, "team_code": team})
        return r.json(), r.status_code

async def fetch_threads():
    try:
        r = await _get("/chat/threads")
        return r.json().get("threads", [])
    except:
        return []

async def fetch_history(thread_id):
    try:
        r = await _get(f"/chat/history/{thread_id}")
        return r.json().get("messages", [])
    except:
        return []

async def fetch_papers():
    try:
        r = await _get("/vault/papers")
        return r.json().get("papers", [])
    except:
        return []

async def fetch_usage():
    try:
        r = await _get("/stats/usage")
        return r.json()
    except:
        return {}

async def delete_paper(filename):
    import urllib.parse
    r = await _delete(f"/vault/papers/{urllib.parse.quote(filename, safe='')}")
    return r.status_code == 200

async def get_summary(filename):
    r = await _post("/vault/summary", json={"filename": filename})
    if r.status_code == 200:
        return r.json().get("summary", "")
    return None

async def get_comparison(file_a, file_b, question):
    r = await _post("/vault/compare", json={"file_a": file_a, "file_b": file_b, "question": question})
    if r.status_code == 200:
        return r.json().get("comparison", "")
    return None

async def run_smart_research(topic: str, n_papers: int = 3):
    """Calls the streaming /vault/research endpoint and collects all SSE events."""
    events = []
    answer_tokens = []
    async with httpx.AsyncClient(timeout=300) as client:
        async with client.stream(
            "POST",
            f"{API_BASE_URL}/vault/research",
            headers=headers(),
            json={"topic": topic, "n_papers": n_papers}
        ) as resp:
            async for line in resp.aiter_lines():
                if not line.startswith("data:"):
                    continue
                raw = line[5:].strip()
                if not raw:
                    continue
                try:
                    ev = json.loads(raw)
                    events.append(ev)
                    if ev.get("type") == "token":
                        answer_tokens.append(ev["content"])
                except Exception:
                    pass
    return events, "".join(answer_tokens)

async def search_guideline(condition: str):
    r = await _post("/vault/guideline-search", json={"condition": condition})
    if r.status_code == 200:
        return r.json()
    return None

async def run_literature_review(topic: str, filenames: list):
    r = await _post("/vault/literature-review", json={"topic": topic, "filenames": filenames})
    if r.status_code == 200:
        return r.json()
    d = r.json().get("detail", "Review failed.")
    return {"error": d}

async def search_protocol(procedure: str):
    r = await _post("/vault/protocol-search", json={"procedure": procedure})
    if r.status_code == 200:
        return r.json()
    return None

# Each tuple: (label, progress_value_at_which_this_stage_is_complete)
_PIPELINE_STAGES = [("Extract", 10), ("Clean", 35), ("Chunk", 45), ("Embed", 80), ("Index", 100)]

def _render_pipeline(placeholder, value: int):
    html = '<div style="display:flex;align-items:center;padding:0.75rem 0 0.25rem;">'
    for i, (label, threshold) in enumerate(_PIPELINE_STAGES):
        if value >= threshold:
            bg, bc, fc, dt = "#16a34a", "#16a34a", "white", "✓"
            lc, fw = "#16a34a", "700"
            line_bg = "#16a34a"
        elif i == 0 or value >= _PIPELINE_STAGES[i - 1][1]:
            bg, bc, fc, dt = "#2563eb", "#2563eb", "white", str(i + 1)
            lc, fw = "#2563eb", "700"
            line_bg = "linear-gradient(90deg,#2563eb,#e2e8f0)"
        else:
            bg, bc, fc, dt = "#f1f5f9", "#cbd5e1", "#94a3b8", str(i + 1)
            lc, fw = "#94a3b8", "500"
            line_bg = "#e2e8f0"
        html += (
            f'<div style="display:flex;flex-direction:column;align-items:center;gap:4px;">'
            f'<div style="width:28px;height:28px;border-radius:50%;background:{bg};border:2px solid {bc};'
            f'color:{fc};display:flex;align-items:center;justify-content:center;font-size:0.72rem;font-weight:700;">{dt}</div>'
            f'<div style="font-size:0.68rem;color:{lc};font-weight:{fw};white-space:nowrap;">{label}</div>'
            f'</div>'
        )
        if i < len(_PIPELINE_STAGES) - 1:
            html += f'<div style="flex:1;height:2px;background:{line_bg};margin-bottom:22px;min-width:16px;"></div>'
    html += '</div>'
    placeholder.markdown(html, unsafe_allow_html=True)

async def ingest_file(file):
    try:
        async with httpx.AsyncClient(timeout=120) as c:
            files = {"file": (file.name, file.getvalue(), "application/pdf")}
            pipeline_box = st.empty()
            _render_pipeline(pipeline_box, 0)
            async with aconnect_sse(c, "POST", f"{API_BASE_URL}/ingest", files=files, headers=headers()) as es:
                async for ev in es.aiter_sse():
                    d = json.loads(ev.data)
                    if d.get("type") == "progress":
                        _render_pipeline(pipeline_box, d["value"])
                    elif d.get("type") == "completed":
                        pipeline_box.empty()
                        return d["result"]
                    elif d.get("type") == "error":
                        pipeline_box.empty()
                        st.error(d["message"])
                        return None
    except Exception as e:
        st.error(f"Ingestion failed: {e}")
        return None

async def stream_query(prompt):
    payload = {
        "query": prompt,
        "thread_id": st.session_state.thread_id,
        "tenant_id": st.session_state.user_info.get("tenant_id")
    }
    async with httpx.AsyncClient(timeout=120) as c:
        async with aconnect_sse(c, "POST", f"{API_BASE_URL}/query", json=payload, headers=headers()) as es:
            async for ev in es.aiter_sse():
                if ev.data == "[DONE]":
                    break
                yield json.loads(ev.data)

# ─────────────────────────────────────────────────────────────
# UTILS
# ─────────────────────────────────────────────────────────────
def doc_category(filename: str, title: str = "") -> tuple:
    text = (filename + " " + (title or "")).lower()
    if any(k in text for k in ["blood", "cbc", "hematol", "lab", "serum", "urine", "pathol", "report"]):
        return "Blood Work", "badge-blood"
    if any(k in text for k in ["guideline", "protocol", "who", "nhs", "nice", "clinical practice"]):
        return "Guideline", "badge-guideline"
    if any(k in text for k in ["patent", "us2", "us1", "ep2", "wo2"]):
        return "Patent", "badge-patent"
    if any(k in text for k in ["arxiv", "journal", "study", "trial", "cohort", "meta-analysis"]):
        return "Research", "badge-research"
    return "Clinical Doc", "badge-clinical"

def export_chat_md(messages: list) -> str:
    lines = [f"# MedVault — Chat Export\n*{datetime.now().strftime('%Y-%m-%d %H:%M')}*\n"]
    for m in messages:
        role = "You" if m["role"] == "user" else "Assistant"
        lines.append(f"**{role}:** {m['content']}\n")
        if "metrics" in m and m["metrics"]:
            mt = m["metrics"]
            lines.append(f"*⚡ {mt['latency_ms']}ms · {mt['tokens_in']+mt['tokens_out']} tokens*\n")
    return "\n".join(lines)

TOOL_ICONS = {
    "rag_tool": "🔬",
    "list_vault_papers_tool": "🗂️",
    "arxiv_search_tool": "🌐",
    "python_repl_tool": "🐍",
    "auto_ingest_paper_tool": "📥",
}

# ─────────────────────────────────────────────────────────────
# AUTH PAGE
# ─────────────────────────────────────────────────────────────
if not st.session_state.auth_token:
    _, col, _ = st.columns([1, 1.15, 1])
    with col:
        st.markdown("""
        <div class="auth-logo">
            <span class="icon">🧬</span>
            <h1>MedVault</h1>
            <p>Secure clinical research platform</p>
        </div>
        """, unsafe_allow_html=True)

        tab1, tab2 = st.tabs(["Sign In", "Create Account"])
        with tab1:
            with st.form("login_form"):
                user = st.text_input("Username", placeholder="Enter username")
                pw   = st.text_input("Password", type="password", placeholder="••••••••")
                if st.form_submit_button("Sign In →", use_container_width=True, type="primary"):
                    res, code = run(login(user, pw))
                    if code == 200:
                        st.session_state.auth_token = res["access_token"]
                        st.session_state.user_info  = res
                        st.rerun()
                    else:
                        err = res.get("detail", "Login failed")
                        if isinstance(err, list): err = err[0].get("msg", "Validation error")
                        st.error(err)
        with tab2:
            with st.form("reg_form"):
                nu = st.text_input("Username",  placeholder="Choose a username")
                np = st.text_input("Password",  type="password", placeholder="Min. 8 characters")
                tc = st.text_input("Team Code", placeholder="Organisation code")
                if st.form_submit_button("Create Account", use_container_width=True, type="primary"):
                    res, code = run(register(nu, np, tc))
                    if code == 200:
                        st.success("Account created — please sign in.")
                    else:
                        err = res.get("detail", "Registration failed")
                        if isinstance(err, list):
                            loc = err[0].get("loc", [""])[-1]
                            err = f"{loc.capitalize()}: {err[0].get('msg','Validation error')}"
                        st.error(err)
    st.stop()

# ─────────────────────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div class="sidebar-logo">
        <div class="sidebar-logo-icon">🧬</div>
        <div class="sidebar-logo-text">
            <h2>Clinical Intel</h2>
            <span>Research Platform</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    uname = st.session_state.user_info.get("username", "User")
    st.markdown(f"""
    <div class="user-badge">
        <div class="user-avatar">{uname[0].upper()}</div>
        <div><div class="user-name">{uname}</div><div class="user-role">Clinician</div></div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="sidebar-label">Navigation</div>', unsafe_allow_html=True)

    pages = [
        ("chat",       "💬", "Research Chat"),
        ("smart",      "🔬", "Smart Research"),
        ("vault",      "🗂️", "Document Vault"),
        ("guideline",  "📋", "Guideline Reference"),
        ("literature", "📚", "Literature Review"),
        ("protocol",   "🏥", "Protocol Reference"),
        ("analytics",  "📊", "Analytics"),
        ("compare",    "⚖️",  "Compare Docs"),
    ]
    for page_id, icon, label in pages:
        is_active = st.session_state.active_page == page_id
        btn_type  = "primary" if is_active else "secondary"
        if st.button(f"{icon}  {label}", key=f"nav_{page_id}", type=btn_type, use_container_width=True):
            st.session_state.active_page = page_id
            st.rerun()

    st.divider()

    st.markdown('<div class="sidebar-label">Quick Ingest</div>', unsafe_allow_html=True)
    uploaded = st.file_uploader("upload", type=["pdf"], label_visibility="collapsed",
                                 help="PDF, guidelines, lab reports, patents",
                                 accept_multiple_files=True)
    if uploaded:
        n = len(uploaded)
        btn_label = f"⬆ Index {n} Document{'s' if n > 1 else ''}"
        if st.button(btn_label, use_container_width=True, type="primary"):
            for f in uploaded:
                res = run(ingest_file(f))
                if res:
                    title = res.get("metadata", {}).get("title") or f.name
                    st.success(f"✓ {title[:35]}")
            st.rerun()

    st.divider()

    if st.session_state.active_page == "chat":
        c1, c2 = st.columns(2)
        with c1:
            if st.button("＋ New Chat", use_container_width=True):
                st.session_state.messages  = []
                st.session_state.thread_id = None
                st.rerun()
        with c2:
            if st.button("Sign Out", use_container_width=True):
                for k in defaults: st.session_state[k] = defaults[k]
                st.rerun()

        if st.session_state.messages:
            st.download_button(
                "⬇ Export Chat",
                data=export_chat_md(st.session_state.messages),
                file_name=f"chat_{datetime.now().strftime('%Y%m%d_%H%M')}.md",
                mime="text/markdown",
                use_container_width=True
            )

        st.markdown('<div class="sidebar-label">Chat History</div>', unsafe_allow_html=True)
        threads = run(fetch_threads())
        if threads:
            sel = st.selectbox("Threads", ["Current"] + threads, label_visibility="collapsed")
            if sel != "Current" and sel != st.session_state.thread_id:
                st.session_state.messages  = run(fetch_history(sel))
                st.session_state.thread_id = sel
                st.rerun()
        else:
            st.caption("No previous chats")
    else:
        if st.button("Sign Out", use_container_width=True):
            for k in defaults: st.session_state[k] = defaults[k]
            st.rerun()

# ─────────────────────────────────────────────────────────────
# PAGE: CHAT
# ─────────────────────────────────────────────────────────────
if st.session_state.active_page == "chat":
    st.markdown("""
    <div class="page-header" style="display:flex;align-items:center;justify-content:space-between">
        <div>
            <div class="page-title">Research Assistant</div>
            <div class="page-subtitle">Ask anything about the documents in your vault</div>
        </div>
        <div class="status-dot">Ready</div>
    </div>
    """, unsafe_allow_html=True)

    # Welcome screen with prompt chips
    if not st.session_state.messages:
        st.markdown("""
        <div style="text-align:center;padding:1.5rem 0 0.5rem">
            <div class="welcome-title">How can I help you today?</div>
            <div class="welcome-sub">Upload a document from the sidebar, then try one of these prompts</div>
        </div>
        """, unsafe_allow_html=True)

        chips = [
            ("🩸", "Analyze abnormal blood values", "Analyze the uploaded blood report and highlight any abnormal or critical values. Explain what each means clinically."),
            ("📋", "Key findings from report",       "What are the key findings and diagnosis from the uploaded report?"),
            ("🔍", "Search Arxiv for research",      "Search Arxiv for recent research on SGLT2 inhibitors and cardiovascular outcomes."),
            ("💊", "Drug interaction check",          "What do the clinical guidelines say about first-line treatment for Type 2 Diabetes?"),
        ]
        cols = st.columns(2)
        for i, (icon, short, full_prompt) in enumerate(chips):
            with cols[i % 2]:
                if st.button(f"{icon}  {short}", key=f"chip_{i}", use_container_width=True):
                    st.session_state.prompt_prefill = full_prompt
                    st.rerun()

        st.markdown("<br>", unsafe_allow_html=True)

    # Handle prefilled prompt from chips
    if st.session_state.prompt_prefill:
        prefill = st.session_state.prompt_prefill
        st.session_state.prompt_prefill = None
        st.session_state.messages.append({"role": "user", "content": prefill})
        st.rerun()

    _AVATAR = {"user": "🧑‍⚕️", "assistant": "🧬"}
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"], avatar=_AVATAR.get(msg["role"])):
            st.markdown(msg["content"])
            if "metrics" in msg and msg["metrics"]:
                m = msg["metrics"]
                st.markdown(
                    f'<div class="metrics-bar">'
                    f'<span>⚡ {m["latency_ms"]}ms</span>'
                    f'<span>🪙 {m["tokens_in"] + m["tokens_out"]} tokens</span>'
                    f'</div>',
                    unsafe_allow_html=True
                )

    if prompt := st.chat_input("Ask a clinical question..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user", avatar="🧑‍⚕️"):
            st.markdown(prompt)

        with st.chat_message("assistant", avatar="🧬"):
            status_ph   = st.empty()
            response_ph = st.empty()
            metrics_ph  = st.empty()

            async def handle_stream():
                full_text = ""
                metrics   = None
                async for ev in stream_query(prompt):
                    kind   = ev.get("type")
                    status = ev.get("status")
                    if status == "agent_started":
                        st.session_state.thread_id = ev.get("thread_id")
                        status_ph.markdown(
                            '<div class="tool-badge searching">'
                            '<div class="thinking-dots"><span></span><span></span><span></span></div>'
                            'Thinking…</div>',
                            unsafe_allow_html=True
                        )
                    elif kind == "token":
                        full_text += ev.get("content", "")
                        response_ph.markdown(full_text + "▌")
                        status_ph.empty()
                    elif kind == "tool_start":
                        tool_name = ev.get("tool", "tool")
                        icon = TOOL_ICONS.get(tool_name, "🔧")
                        label = tool_name.replace("_tool", "").replace("_", " ").title()
                        status_ph.markdown(
                            f'<div class="tool-badge searching">{icon} Using {label}…</div>',
                            unsafe_allow_html=True
                        )
                    elif kind == "tool_end":
                        tool_name = ev.get("tool", "tool")
                        icon = TOOL_ICONS.get(tool_name, "🔧")
                        label = tool_name.replace("_tool", "").replace("_", " ").title()
                        status_ph.markdown(
                            f'<div class="tool-badge done">✓ {icon} {label} complete</div>',
                            unsafe_allow_html=True
                        )
                    elif kind == "metrics":
                        metrics = ev
                response_ph.markdown(full_text)
                status_ph.empty()
                if metrics:
                    metrics_ph.markdown(
                        f'<div class="metrics-bar">'
                        f'<span>⚡ {metrics["latency_ms"]}ms</span>'
                        f'<span>🪙 {metrics["tokens_in"] + metrics["tokens_out"]} tokens</span>'
                        f'</div>',
                        unsafe_allow_html=True
                    )
                st.session_state.messages.append({"role": "assistant", "content": full_text, "metrics": metrics})

            run(handle_stream())
            st.rerun()

# ─────────────────────────────────────────────────────────────
# PAGE: DOCUMENT VAULT
# ─────────────────────────────────────────────────────────────
elif st.session_state.active_page == "vault":
    st.markdown("""
    <div class="page-header">
        <div class="page-title">Document Vault</div>
        <div class="page-subtitle">All indexed clinical documents</div>
    </div>
    """, unsafe_allow_html=True)

    papers = run(fetch_papers())

    if not papers:
        st.markdown("""
        <div class="info-banner">
            📂 Your vault is empty. Upload a PDF from the sidebar to get started.
        </div>
        """, unsafe_allow_html=True)
    else:
        st.caption(f"{len(papers)} document{'s' if len(papers) != 1 else ''} indexed")
        st.markdown("<br>", unsafe_allow_html=True)

        # 2-column grid
        col_left, col_right = st.columns(2, gap="medium")
        for idx, paper in enumerate(papers):
            fname    = paper.get("filename", "Unknown")
            title    = paper.get("title")   or fname
            ingested = paper.get("ingested_at", "")[:10]
            cat_label, cat_cls = doc_category(fname, title)

            target_col = col_left if idx % 2 == 0 else col_right
            with target_col:
                st.markdown(f"""
                <div class="doc-card">
                    <div class="doc-badge {cat_cls}">{cat_label}</div>
                    <div class="doc-title" title="{title}">{title}</div>
                    <div class="doc-meta">📄 {fname} &nbsp;·&nbsp; 📅 {ingested}</div>
                </div>
                """, unsafe_allow_html=True)

                c1, c2, c3 = st.columns([5, 5, 3])
                with c1:
                    if st.button("📝 Summary", key=f"sum_{fname}", use_container_width=True):
                        with st.spinner("Generating summary..."):
                            summary = run(get_summary(fname))
                        if summary:
                            with st.container(border=True):
                                st.markdown(summary)
                        else:
                            st.error("Could not generate summary.")
                with c2:
                    if st.button("🔍 Analyze", key=f"ab_{fname}", use_container_width=True):
                        st.session_state.active_page = "chat"
                        st.session_state.messages.append({
                            "role": "user",
                            "content": f"Analyze '{fname}' and highlight any abnormal or critical values. Explain what each means clinically."
                        })
                        st.rerun()
                with c3:
                    if st.button("🗑️", key=f"del_{fname}", use_container_width=True):
                        if run(delete_paper(fname)):
                            st.success(f"Deleted")
                            st.rerun()
                        else:
                            st.error("Delete failed.")
                st.markdown("<br>", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────
# PAGE: ANALYTICS
# ─────────────────────────────────────────────────────────────
elif st.session_state.active_page == "analytics":
    st.markdown("""
    <div class="page-header">
        <div class="page-title">Analytics</div>
        <div class="page-subtitle">Usage metrics and cost overview</div>
    </div>
    """, unsafe_allow_html=True)

    usage  = run(fetch_usage())
    papers = run(fetch_papers())

    total_tokens = usage.get("total_tokens", 0)
    total_cost   = usage.get("total_cost_usd", 0.0)
    avg_faith    = usage.get("avg_faithfulness", 1.0)
    history      = usage.get("history", [])
    doc_count    = len(papers)

    c1, c2, c3, c4 = st.columns(4)
    cards = [
        (c1, "Documents Indexed", str(doc_count),               "In your vault"),
        (c2, "Total Queries",     str(len([h for h in history if h.get("type") == "query"])), "Last 10 shown below"),
        (c3, "Tokens Used",       f"{total_tokens:,}",          "Input + output"),
        (c4, "Total Cost",        f"${total_cost:.4f}",         f"Avg faithfulness: {avg_faith:.0%}"),
    ]
    for col, label, value, sub in cards:
        with col:
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-label">{label}</div>
                <div class="metric-value">{value}</div>
                <div class="metric-sub">{sub}</div>
            </div>""", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    if papers:
        st.markdown('<div class="page-subtitle" style="margin-bottom:0.75rem">Vault Breakdown</div>', unsafe_allow_html=True)
        from collections import Counter
        cats = Counter(doc_category(p.get("filename",""), p.get("title",""))[0] for p in papers)
        cols = st.columns(len(cats))
        for i, (cat, cnt) in enumerate(cats.items()):
            _, cat_cls = doc_category(cat)
            with cols[i]:
                st.markdown(f"""
                <div class="metric-card" style="text-align:center">
                    <div class="doc-badge {cat_cls}" style="margin-bottom:0.5rem">{cat}</div>
                    <div class="metric-value" style="font-size:1.4rem">{cnt}</div>
                </div>""", unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)

    if history:
        st.markdown('<div class="page-subtitle" style="margin-bottom:0.75rem">Recent Activity</div>', unsafe_allow_html=True)
        for item in reversed(history):
            t = item.get("time", "")[:16].replace("T", " ")
            st.markdown(f"""
            <div class="activity-row">
                <span class="activity-type">{'🔍 Query' if item.get('type')=='query' else '📥 Ingest'}</span>
                <span class="activity-cost">${item.get('cost', 0):.6f}</span>
                <span class="activity-time">{t}</span>
            </div>""", unsafe_allow_html=True)
    else:
        st.caption("No activity recorded yet.")

# ─────────────────────────────────────────────────────────────
# PAGE: GUIDELINE REFERENCE
# ─────────────────────────────────────────────────────────────
elif st.session_state.active_page == "guideline":
    st.markdown("""
    <div class="page-header">
        <div class="page-title">Guideline Reference</div>
        <div class="page-subtitle">WHO / NHS / NICE — find recommendations without reading 200 pages</div>
    </div>
    """, unsafe_allow_html=True)

    papers = run(fetch_papers())
    guideline_papers = [p for p in papers if any(
        k in (p.get("filename","") + p.get("title","")).lower()
        for k in ["guideline","protocol","who","nhs","nice","recommendation","consensus","standard"]
    )]

    if not papers:
        st.markdown('<div class="info-banner">📋 Upload a clinical guideline PDF from the sidebar first.</div>',
                    unsafe_allow_html=True)
    else:
        if guideline_papers:
            st.markdown(f'<div class="info-banner">📋 {len(guideline_papers)} guideline document(s) detected. '
                        f'All {len(papers)} documents will be searched.</div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="info-banner">📋 {len(papers)} document(s) will be searched. '
                        f'Upload WHO/NHS/NICE guidelines for best results.</div>', unsafe_allow_html=True)

        condition = st.text_input(
            "Condition, drug, or topic",
            placeholder="e.g. Type 2 Diabetes management, Hypertension first-line treatment, Sepsis protocol"
        )

        col1, col2 = st.columns([1, 4])
        with col1:
            search_clicked = st.button("Search Guidelines", use_container_width=True, type="primary")

        if search_clicked and condition.strip():
            with st.spinner("Searching guidelines..."):
                result = run(search_guideline(condition.strip()))

            if result:
                st.markdown("<br>", unsafe_allow_html=True)
                sources_html = " ".join(
                    f'<span class="doc-badge badge-guideline">{s}</span>'
                    for s in result.get("sources", [])
                )
                st.markdown(f'<div style="margin-bottom:0.75rem">{sources_html}</div>', unsafe_allow_html=True)
                with st.container(border=True):
                    st.markdown(result["result"])
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("Continue discussion in Chat →", type="primary"):
                    st.session_state.active_page = "chat"
                    st.session_state.messages.append({"role": "user", "content": f"What do the clinical guidelines say about: {condition}?"})
                    st.session_state.messages.append({"role": "assistant", "content": result["result"]})
                    st.rerun()
            else:
                st.error("No relevant guideline content found. Make sure you have uploaded relevant guidelines.")
        elif search_clicked:
            st.warning("Please enter a condition or topic to search.")

# ─────────────────────────────────────────────────────────────
# PAGE: LITERATURE REVIEW
# ─────────────────────────────────────────────────────────────
elif st.session_state.active_page == "literature":
    st.markdown("""
    <div class="page-header">
        <div class="page-title">Literature Review Assistant</div>
        <div class="page-subtitle">Find agreements, contradictions, and gaps across multiple research papers</div>
    </div>
    """, unsafe_allow_html=True)

    papers = run(fetch_papers())

    if len(papers) < 2:
        st.markdown('<div class="info-banner">📚 Upload at least 2 research papers to run a literature review.</div>',
                    unsafe_allow_html=True)
    else:
        st.markdown('<div class="info-banner">📚 Select papers, enter your research question, and the AI will synthesise findings across them.</div>',
                    unsafe_allow_html=True)

        topic = st.text_input(
            "Research question / topic",
            placeholder="e.g. Efficacy of metformin in pre-diabetic patients, SGLT2 inhibitors and cardiovascular outcomes"
        )

        st.markdown('<div class="sidebar-label" style="margin:0.75rem 0 0.4rem">Select Papers to Review</div>',
                    unsafe_allow_html=True)

        selected_files = []
        cols = st.columns(2)
        for i, paper in enumerate(papers):
            fname = paper.get("filename", "")
            title = paper.get("title") or fname
            cat_label, cat_cls = doc_category(fname, title)
            with cols[i % 2]:
                if st.checkbox(
                    f"{title[:55]}{'…' if len(title) > 55 else ''}",
                    key=f"lit_{fname}",
                    help=f"{fname} — {cat_label}"
                ):
                    selected_files.append(fname)

        st.markdown("<br>", unsafe_allow_html=True)
        col1, col2, col3 = st.columns([2, 1, 2])
        with col2:
            review_clicked = st.button("Run Review", use_container_width=True, type="primary")

        if review_clicked:
            if not topic.strip():
                st.warning("Please enter a research question.")
            elif len(selected_files) < 2:
                st.warning("Select at least 2 papers.")
            else:
                with st.spinner(f"Reviewing {len(selected_files)} papers..."):
                    result = run(run_literature_review(topic.strip(), selected_files))
                if result and "error" not in result:
                    st.session_state.lit_review_result = result
                elif result:
                    st.error(result["error"])

        if st.session_state.lit_review_result:
            r = st.session_state.lit_review_result
            st.markdown("<br>", unsafe_allow_html=True)
            col_a, col_b = st.columns(2)
            with col_a:
                st.markdown(f'<div class="doc-meta">✓ Reviewed: {len(r.get("papers_reviewed",[]))} paper(s)</div>', unsafe_allow_html=True)
            with col_b:
                nf = r.get("papers_not_found", [])
                if nf:
                    st.markdown(f'<div class="doc-meta" style="color:#f87171">⚠ Not found: {", ".join(nf)}</div>', unsafe_allow_html=True)

            with st.container(border=True):
                st.markdown(r["review"])
            st.markdown("<br>", unsafe_allow_html=True)
            col1, col2 = st.columns(2)
            with col1:
                st.download_button(
                    "⬇ Export Review (.md)",
                    data=f"# Literature Review\n\n**Topic:** {r.get('topic','')}\n\n{r['review']}",
                    file_name=f"literature_review_{datetime.now().strftime('%Y%m%d')}.md",
                    mime="text/markdown",
                    use_container_width=True
                )
            with col2:
                if st.button("Continue in Chat →", use_container_width=True, type="primary"):
                    st.session_state.active_page = "chat"
                    st.session_state.messages.append({"role": "user", "content": f"Literature review on: {r.get('topic', '')}"})
                    st.session_state.messages.append({"role": "assistant", "content": r["review"]})
                    st.session_state.lit_review_result = None
                    st.rerun()

# ─────────────────────────────────────────────────────────────
# PAGE: PROTOCOL REFERENCE
# ─────────────────────────────────────────────────────────────
elif st.session_state.active_page == "protocol":
    st.markdown("""
    <div class="page-header">
        <div class="page-title">Protocol Reference</div>
        <div class="page-subtitle">Step-by-step procedure guidance from your uploaded SOPs</div>
    </div>
    """, unsafe_allow_html=True)

    papers = run(fetch_papers())

    if not papers:
        st.markdown('<div class="info-banner">🏥 Upload hospital SOPs or clinical protocols from the sidebar first.</div>',
                    unsafe_allow_html=True)
    else:
        st.markdown('<div class="info-banner">🏥 Search your uploaded protocols for step-by-step procedure guidance. '
                    'Always refer to the full source document before performing any procedure.</div>',
                    unsafe_allow_html=True)

        procedure = st.text_input(
            "Procedure or task",
            placeholder="e.g. Central venous catheter insertion, Blood culture collection, Wound debridement"
        )

        col1, col2 = st.columns([1, 4])
        with col1:
            proto_clicked = st.button("Find Protocol", use_container_width=True, type="primary")

        if proto_clicked and procedure.strip():
            with st.spinner("Searching protocols..."):
                result = run(search_protocol(procedure.strip()))
            if result:
                st.markdown("<br>", unsafe_allow_html=True)
                sources_html = " ".join(
                    f'<span class="doc-badge badge-clinical">{s}</span>'
                    for s in result.get("sources", [])
                )
                st.markdown(f'<div style="margin-bottom:0.75rem">{sources_html}</div>', unsafe_allow_html=True)
                with st.container(border=True):
                    st.markdown(result["result"])
                st.markdown("<br>", unsafe_allow_html=True)
                col1, col2 = st.columns(2)
                with col1:
                    st.download_button(
                        "⬇ Export Protocol (.md)",
                        data=f"# Protocol Reference\n\n**Procedure:** {procedure}\n\n{result['result']}",
                        file_name=f"protocol_{procedure[:20].replace(' ','_')}.md",
                        mime="text/markdown",
                        use_container_width=True
                    )
                with col2:
                    if st.button("Continue in Chat →", use_container_width=True, type="primary"):
                        st.session_state.active_page = "chat"
                        st.session_state.messages.append({"role": "user", "content": f"What are the protocol steps for: {procedure}?"})
                        st.session_state.messages.append({"role": "assistant", "content": result["result"]})
                        st.rerun()
            else:
                st.error("No matching protocol found. Upload relevant SOPs from the sidebar.")
        elif proto_clicked:
            st.warning("Please enter a procedure name.")

# ─────────────────────────────────────────────────────────────
# PAGE: COMPARE DOCUMENTS
# ─────────────────────────────────────────────────────────────
elif st.session_state.active_page == "compare":
    st.markdown("""
    <div class="page-header">
        <div class="page-title">Compare Documents</div>
        <div class="page-subtitle">Side-by-side AI comparison of two vault documents</div>
    </div>
    """, unsafe_allow_html=True)

    papers = run(fetch_papers())

    if len(papers) < 2:
        st.markdown("""
        <div class="info-banner">
            ⚖️ You need at least 2 documents in your vault to compare. Upload more files from the sidebar.
        </div>
        """, unsafe_allow_html=True)
    else:
        filenames = [p.get("filename", "") for p in papers]

        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown('<div class="compare-header">Document A</div>', unsafe_allow_html=True)
            file_a = st.selectbox("Document A", filenames, key="cmp_a", label_visibility="collapsed")
        with col_b:
            st.markdown('<div class="compare-header">Document B</div>', unsafe_allow_html=True)
            remaining = [f for f in filenames if f != file_a]
            file_b = st.selectbox("Document B", remaining, key="cmp_b", label_visibility="collapsed")

        question = st.text_area(
            "Comparison question",
            value="Compare the key findings, diagnoses, and recommendations between these two documents.",
            height=80
        )

        if st.button("⚖️  Compare Documents", use_container_width=True, type="primary"):
            if file_a == file_b:
                st.warning("Please select two different documents.")
            else:
                with st.spinner("Comparing documents..."):
                    result = run(get_comparison(file_a, file_b, question))

                if result:
                    st.markdown("<br>", unsafe_allow_html=True)
                    col1, col2 = st.columns(2)
                    with col1:
                        st.markdown(f'<div class="compare-header">📄 {file_a}</div>', unsafe_allow_html=True)
                    with col2:
                        st.markdown(f'<div class="compare-header">📄 {file_b}</div>', unsafe_allow_html=True)
                    with st.container(border=True):
                        st.markdown(result)
                    if st.button("Continue this comparison in Chat →", type="primary"):
                        st.session_state.active_page = "chat"
                        st.session_state.messages.append({"role": "user", "content": question})
                        st.session_state.messages.append({"role": "assistant", "content": result})
                        st.rerun()
                else:
                    st.error("Comparison failed. Make sure both documents are indexed.")

# ── SMART RESEARCH PAGE ───────────────────────────────────────
elif st.session_state.active_page == "smart":
    st.markdown("""
    <div class="page-header">
        <div class="page-title">Smart Research</div>
        <div class="page-subtitle">Type any clinical question — top papers are auto-fetched, indexed, and used to answer</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div class="info-banner">
    🔬 <strong>How it works:</strong>
    Type your question &rarr; App finds top research papers on Arxiv &rarr; Indexes them into your vault &rarr; Answers from those papers with citations.
    </div>
    """, unsafe_allow_html=True)

    # Apply prefill from a quick-example click before the widget renders
    if "smart_topic_prefill" in st.session_state:
        st.session_state["smart_topic"] = st.session_state.pop("smart_topic_prefill")

    topic = st.text_input(
        "Research question or topic",
        placeholder="e.g. how to treat rickets, causes of vitamin B12 deficiency, management of sepsis in children",
        key="smart_topic"
    )

    n_papers = st.slider("Number of papers to fetch", min_value=1, max_value=5, value=3, key="smart_n")

    examples = [
        "How to treat rickets in children",
        "Causes of vitamin B12 deficiency",
        "Management of iron deficiency anemia",
        "Treatment of sepsis in ICU patients",
        "Vitamin D deficiency and bone health",
    ]
    st.markdown("**Quick examples:**")
    cols = st.columns(len(examples))
    for i, ex in enumerate(examples):
        with cols[i]:
            if st.button(ex, key=f"smart_ex_{i}", use_container_width=True):
                st.session_state["smart_topic_prefill"] = ex
                st.rerun()

    if st.button("🔬  Start Smart Research", type="primary", use_container_width=True, disabled=not topic):
        if topic:
            # Progress containers
            status_box   = st.empty()
            papers_box   = st.empty()
            progress_bar = st.progress(0)
            answer_box   = st.empty()

            status_box.info("🔍 Searching Arxiv for relevant papers...")
            progress_bar.progress(10)

            events, answer = run(run_smart_research(topic.strip(), n_papers))

            # Parse events
            papers_found = []
            indexed      = []
            errors       = []
            for ev in events:
                t = ev.get("type")
                if t == "papers_found":
                    papers_found = ev.get("papers", [])
                    progress_bar.progress(30)
                    # Show paper cards
                    with papers_box.container():
                        st.markdown("#### Papers Found on Arxiv")
                        for p in papers_found:
                            authors = ", ".join(p.get("authors", []))
                            year    = p.get("year", "")
                            st.markdown(
                                f'<div class="summary-box" style="margin-bottom:8px;">'
                                f'<strong>{p["title"]}</strong><br>'
                                f'<span style="color:#64748b;font-size:0.82rem;">{authors} ({year}) &bull; {p.get("source","")} &bull; {p.get("pmcid", p.get("arxiv_id",""))}</span><br>'
                                f'<span style="font-size:0.8rem;">{p.get("summary","")}</span>'
                                f'</div>',
                                unsafe_allow_html=True
                            )
                elif t == "indexed":
                    paper_id = ev.get("pmcid") or ev.get("arxiv_id", "")
                    if ev.get("success"):
                        indexed.append(ev.get("title", ""))
                        pct = 30 + int(50 * len(indexed) / max(n_papers, 1))
                        progress_bar.progress(pct)
                        status_box.success(f"Indexed: {ev.get('title','')[:70]} [{paper_id}]")
                    else:
                        errors.append(ev.get("title", ""))
                        status_box.warning(f"Could not index: {ev.get('title','')[:60]} — PDF may not be open access")
                elif t == "status" and ev.get("step") == "answering":
                    progress_bar.progress(85)
                    status_box.info("🧠 Generating cited answer from indexed papers...")
                elif t == "error":
                    st.error(ev.get("message", "An error occurred."))

            progress_bar.progress(100)

            if answer:
                status_box.success(f"✅ Done! Indexed {len(indexed)} paper(s). Answer generated with citations.")
                st.markdown("---")
                st.markdown("#### Answer")
                st.markdown(answer)

                # Button to continue in chat
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("💬  Continue this research in Chat", type="primary"):
                    st.session_state.active_page = "chat"
                    st.session_state.messages.append({"role": "user",      "content": topic})
                    st.session_state.messages.append({"role": "assistant", "content": answer})
                    st.rerun()
            elif errors:
                st.error("Could not generate an answer. Some papers failed to index.")
