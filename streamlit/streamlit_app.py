"""
streamlit_app.py  —  RugsKilim Panel
Dark SaaS theme · pCloud klasör gezgini · Google Sheets kuyruk yönetimi
"""

import sys
import streamlit as st
import streamlit.components.v1 as components
import httpx
import os
import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

_APP_DIR = Path(__file__).resolve().parent
_ROOT_DIR = _APP_DIR.parent
_RUNTIME_DIR = _ROOT_DIR / ".runtime" / "streamlit"
_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
_LEGACY_STOK_DOSYA = _APP_DIR / "stok.xlsx"
_TEMPLATE_DIRS = [
    _APP_DIR / "templates",
    _ROOT_DIR / "loomantikrugs" / "templates",
]


def _template_yollari():
    return [p for p in _TEMPLATE_DIRS if p.exists()]


def _template_listesi():
    ids = []
    for klasor in _template_yollari():
        ids.extend(p.stem for p in klasor.glob("*.json"))
    return list(dict.fromkeys(ids)) or ["default_v1"]


def _template_yolu(template_id: str) -> Path:
    for klasor in _template_yollari():
        aday = klasor / f"{template_id}.json"
        if aday.exists():
            return aday
    return _TEMPLATE_DIRS[0] / f"{template_id}.json"


sys.path.insert(0, str(_ROOT_DIR))

_env_path = _APP_DIR / ".env"
if _env_path.exists():
    for _line in _env_path.read_text().splitlines():
        if "=" in _line and not _line.startswith("#"):
            _k, _v = _line.split("=", 1)
            # .env, ayni terminal oturumunda kalmis eski env degerlerini ezsin.
            os.environ[_k.strip()] = _v.strip()

st.set_page_config(
    page_title="RugsKilim Panel",
    page_icon="🪄",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Design System CSS ────────────────────────────────────────────────────────
st.markdown("""
<style>
/* ── Reset & Base ── */
:root {
  --bg-0:       #0d1117;
  --bg-1:       #161b22;
  --bg-2:       #21262d;
  --bg-3:       #2d333b;
  --border:     #30363d;
  --accent:     #f59e0b;
  --accent-dim: #78350f;
  --success:    #22c55e;
  --success-bg: #052e16;
  --error:      #ef4444;
  --error-bg:   #450a0a;
  --warning:    #fbbf24;
  --text-1:     #e6edf3;
  --text-2:     #8b949e;
  --text-3:     #6e7681;
  --radius:     8px;
  --radius-lg:  12px;
}

/* hide Streamlit chrome */
header, [data-testid="stToolbar"], [data-testid="stDecoration"],
[data-testid="stHeader"], #MainMenu { display:none !important; }
.stApp > header { height:0 !important; }
.main .block-container {
  padding-top: 0.75rem !important;
  padding-bottom: 1.5rem !important;
  max-width: 1400px;
}
div[data-testid="stMainBlockContainer"] { padding-top: 0.75rem !important; }

/* ── App background ── */
.stApp, body { background-color: var(--bg-0) !important; color: var(--text-1) !important; }
section.main { background-color: var(--bg-0) !important; }

/* ── Tabs — pill style ── */
.stTabs [data-baseweb="tab-list"] {
  display: inline-flex !important;
  width: auto !important;
  gap: 2px;
  background: var(--bg-1);
  border: 1px solid var(--border);
  padding: 4px;
  border-radius: var(--radius-lg);
  border-bottom: none !important;
}
.stTabs [data-baseweb="tab"] {
  height: 40px;
  border-radius: var(--radius);
  padding: 4px 22px;
  font-weight: 600;
  font-size: 0.96rem;
  color: var(--text-2) !important;
  background: transparent !important;
  border: 1px solid transparent !important;
  box-shadow: none !important;
  transition: all 0.15s ease;
}
.stTabs [data-baseweb="tab"][aria-selected="true"] {
  background: var(--bg-3) !important;
  color: var(--text-1) !important;
  box-shadow: 0 2px 10px rgba(0,0,0,0.45);
  border: 1px solid #4b5563 !important;
}
.stTabs [data-baseweb="tab-highlight"],
.stTabs [data-baseweb="tab-border"] { display:none !important; }
.stTabs [data-baseweb="tab-panel"] { padding-top: 1rem !important; }

.compact-stats {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.compact-stat {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  background: #1b2230;
  border: 1px solid #3b4556;
  border-radius: 999px;
  padding: 12px 18px;
  box-shadow: 0 6px 18px rgba(0,0,0,0.22);
}
.compact-stat-label {
  font-size: 0.9rem;
  color: #cbd5e1;
  font-weight: 600;
}
.compact-stat-value {
  font-size: 1.35rem;
  font-weight: 700;
  color: #ffffff;
  line-height: 1;
}

.loading-panel {
  position: relative;
  overflow: hidden;
  background: linear-gradient(135deg, #161b22 0%, #1f2937 100%);
  border: 1px solid #374151;
  border-radius: 18px;
  padding: 18px 20px;
  margin: 10px 0 18px;
  box-shadow: 0 12px 28px rgba(0,0,0,0.28);
}
.loading-panel::after {
  content: "";
  position: absolute;
  inset: 0;
  transform: translateX(-100%);
  background: linear-gradient(90deg, transparent, rgba(255,255,255,0.06), transparent);
  animation: loading-sweep 1.4s ease-in-out infinite;
}
.loading-title {
  position: relative;
  z-index: 1;
  font-size: 1rem;
  font-weight: 700;
  color: #f8fafc;
  margin-bottom: 6px;
}
.loading-text {
  position: relative;
  z-index: 1;
  font-size: 0.92rem;
  color: #cbd5e1;
  line-height: 1.5;
}
.loading-dots {
  position: relative;
  z-index: 1;
  display: flex;
  gap: 10px;
  margin-top: 14px;
}
.loading-dot {
  width: 12px;
  height: 12px;
  border-radius: 999px;
  background: #334155;
  animation: loading-pulse 1.2s ease-in-out infinite;
}
.loading-dot:nth-child(1) { background: #60a5fa; }
.loading-dot:nth-child(2) { background: #fbbf24; animation-delay: 0.15s; }
.loading-dot:nth-child(3) { background: #22c55e; animation-delay: 0.3s; }
@keyframes loading-sweep {
  100% { transform: translateX(100%); }
}
@keyframes loading-pulse {
  0%, 100% { transform: scale(0.9); opacity: 0.55; }
  50% { transform: scale(1.15); opacity: 1; }
}

.req-star {
  color: #ef4444;
  font-weight: 700;
}

.subtab-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 0;
  flex-wrap: wrap;
}
.subtab-buttons {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  background: var(--bg-1);
  border: 1px solid var(--border);
  border-radius: 18px;
  padding: 6px;
}
.subtab-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 170px;
  height: 48px;
  padding: 0 18px;
  border-radius: 14px;
  font-size: 0.98rem;
  font-weight: 600;
  border: 1px solid transparent;
}
.subtab-btn-active {
  background: var(--bg-3);
  color: var(--text-1);
  border-color: #4b5563;
  box-shadow: 0 2px 10px rgba(0,0,0,0.35);
}
.subtab-btn-idle {
  background: transparent;
  color: var(--text-2);
}

/* ── Buttons ── */
.stButton > button,
[data-testid="stButton"] > button {
  appearance: none !important;
  -webkit-appearance: none !important;
  background: var(--bg-2) !important;
  background-image: none !important;
  border: 1px solid var(--border) !important;
  color: var(--text-1) !important;
  border-radius: var(--radius) !important;
  font-size: 0.82rem !important;
  font-weight: 500 !important;
  box-shadow: none !important;
  opacity: 1 !important;
  transition: all 0.12s ease !important;
}
.stButton > button:hover,
[data-testid="stButton"] > button:hover {
  background: var(--bg-3) !important;
  border-color: var(--text-3) !important;
}
.stButton > button[kind="primary"],
[data-testid="stButton"] > button[kind="primary"] {
  background: var(--accent) !important;
  border-color: var(--accent) !important;
  color: #000 !important;
  font-weight: 600 !important;
}
.stButton > button[kind="primary"]:hover,
[data-testid="stButton"] > button[kind="primary"]:hover {
  background: #d97706 !important;
  border-color: #d97706 !important;
}

[data-testid="stCheckbox"] input {
  accent-color: var(--success);
}

/* ── Inputs ── */
.stTextInput input,
.stNumberInput input,
.stTextArea textarea,
.stSelectbox div[data-baseweb="select"] > div,
.stMultiSelect div[data-baseweb="select"] > div {
  background: var(--bg-1) !important;
  border-color: var(--border) !important;
  color: var(--text-1) !important;
  border-radius: var(--radius) !important;
}
.stTextInput input,
.stNumberInput input,
.stTextArea textarea {
  min-height: 42px !important;
}
.stTextArea textarea {
  line-height: 1.45 !important;
}
.stSelectbox div[data-baseweb="select"] > div,
.stMultiSelect div[data-baseweb="select"] > div {
  min-height: 42px !important;
  box-shadow: none !important;
}
.stTextInput input:focus,
.stNumberInput input:focus,
.stTextArea textarea:focus {
  border-color: var(--accent) !important;
  box-shadow: none !important;
}
.stTextInput input::placeholder,
.stTextArea textarea::placeholder,
.stNumberInput input::placeholder,
.stSelectbox [data-baseweb="select"] input::placeholder,
.stMultiSelect [data-baseweb="select"] input::placeholder {
  color: var(--text-2) !important;
  -webkit-text-fill-color: var(--text-2) !important;
}
.stSelectbox [data-baseweb="select"] span,
.stMultiSelect [data-baseweb="select"] span,
.stSelectbox [data-baseweb="select"] div,
.stMultiSelect [data-baseweb="select"] div {
  color: var(--text-1) !important;
}
.stMultiSelect [data-baseweb="tag"] {
  background: var(--bg-2) !important;
  border: 1px solid var(--border) !important;
  color: var(--text-1) !important;
}
[data-testid="stWidgetLabel"] p {
  color: var(--text-1) !important;
}

/* ── Containers / Cards ── */
[data-testid="stVerticalBlockBorderWrapper"] > div {
  background: var(--bg-1) !important;
  border: 1px solid var(--border) !important;
  border-radius: var(--radius-lg) !important;
}

/* ── Metrics ── */
[data-testid="stMetric"] {
  background: var(--bg-1);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 12px 16px !important;
}
[data-testid="stMetricLabel"] { color: var(--text-2) !important; font-size: 0.78rem !important; }
[data-testid="stMetricValue"] { color: var(--text-1) !important; font-size: 1.5rem !important; font-weight: 700 !important; }

/* ── Dataframe ── */
[data-testid="stDataFrame"] { border: 1px solid var(--border) !important; border-radius: var(--radius) !important; }

/* ── Alert / Info boxes ── */
[data-testid="stAlert"] {
  border-radius: var(--radius) !important;
  border-width: 1px !important;
}

/* ── Expander ── */
details summary {
  background: var(--bg-1) !important;
  color: var(--text-1) !important;
  border-radius: var(--radius) !important;
  border: 1px solid var(--border) !important;
}
details[open] { border: 1px solid var(--border) !important; border-radius: var(--radius) !important; }

/* ── Caption ── */
.stCaption, [data-testid="stCaptionContainer"] { color: var(--text-2) !important; }

/* ── Divider ── */
hr { border-color: var(--border) !important; }

/* ── Scrollbar ── */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: var(--bg-0); }
::-webkit-scrollbar-thumb { background: var(--bg-3); border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: var(--text-3); }

/* ── Folder row ── */
.folder-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 6px;
  border-radius: var(--radius);
  transition: background 0.1s;
  min-height: 34px;
}
.folder-row:hover { background: var(--bg-2); }
.folder-name {
  flex: 1;
  font-size: 0.83rem;
  color: var(--text-1);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.folder-badge {
  font-size: 0.7rem;
  padding: 1px 7px;
  border-radius: 20px;
  font-weight: 600;
  white-space: nowrap;
}
.badge-done     { background:#052e16; color:#22c55e; }
.badge-pending  { background:#1c1c00; color:#fbbf24; }
.badge-ready    { background:#0c2748; color:#60a5fa; }
.badge-error    { background:#450a0a; color:#ef4444; }
.badge-other    { background:var(--bg-2); color:var(--text-2); }

/* ── Store header pill ── */
.store-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: var(--accent-dim);
  border: 1px solid var(--accent);
  color: var(--accent);
  font-weight: 700;
  font-size: 0.88rem;
  padding: 5px 14px;
  border-radius: 20px;
  letter-spacing: 0.3px;
}

/* ── Selected chips ── */
.chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  background: var(--bg-2);
  border: 1px solid var(--border);
  color: var(--text-1);
  font-size: 0.77rem;
  padding: 3px 10px;
  border-radius: 20px;
  margin: 2px;
  font-weight: 500;
}

/* ── pCloud connected ── */
.pcloud-ok {
  display: inline-flex; align-items: center; gap: 5px;
  color: var(--success); font-size: 0.78rem; font-weight: 500;
}

/* ── Section label ── */
.section-label {
  font-size: 0.72rem;
  font-weight: 600;
  letter-spacing: 0.8px;
  text-transform: uppercase;
  color: var(--text-3);
  margin-bottom: 6px;
}

/* ── Thumbnail grid ── */
.thumb-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(130px, 1fr));
  gap: 8px;
  padding: 4px 0;
}
.thumb-item img {
  width: 100%;
  height: 110px;
  object-fit: cover;
  border-radius: var(--radius);
  border: 1px solid var(--border);
  transition: border-color 0.15s;
}
.thumb-item img:hover { border-color: var(--accent); }
.thumb-caption {
  font-size: 0.68rem;
  color: var(--text-3);
  text-align: center;
  margin-top: 3px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.preview-card {
  background: var(--bg-1);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 16px 18px;
  color: var(--text-1);
  white-space: pre-wrap;
  line-height: 1.55;
  font-size: 0.9rem;
}
</style>
""", unsafe_allow_html=True)

# ── Session state ─────────────────────────────────────────────────────────────
for k, v in [
    ("pcloud_token", None), ("klasorler", []), ("secilen", []), ("klasor_id", 0),
    ("klasor_gecmisi", []), ("kuyruga_eklenenler", {}), ("onizleme", None),
    ("kuyruk_klasor_durumlari", {}),
    ("sheet_renk_durumlari", {}),
    ("sheet_renk_cache_ts", 0.0),
    ("global_kirmizi_kodlar", []),
    ("global_kirmizi_cache_yuklendi", False),
    ("global_kirmizi_cache_ts", 0.0),
    ("satilan_kodlar_cache", []),
    ("klasor_id_durumlari", {}),
    ("son_islem_raporu", []),
    ("aktif_islem_urunleri", []),
    ("aktif_islem_durumlari", {}),
    ("aktif_islem_ozeti", {}),
    ("stok_son_indirme", 0), ("ara_sonuclari", []), ("magazalar_root_id", None),
    ("kuyruk_yuklendi", False), ("stok_indiriliyor", False),
    ("stok_indir_hata", None), ("_cikis_yapildi", False),
    ("magaza_id", None), ("magaza_ad", None),
    ("klasor_ad", None),
    ("hedef_magaza_id", "PatchArts"), ("kuyruk_magaza_id", None), ("ayar_magaza_id", None),
    ("tum_magaza_sekmeleri_hazir", False),
    ("urun_formu_acik", False),
    ("satilan_urun_formu_acik", False),
    ("urun_alt_tab", "liste"),
    ("_kuyruk_loading_ui", False),
    ("_kuyruk_refresh_istek", False),
    ("_secim_limit_hatasi", None),
    ("_kaldirilacak_secim_id", None),
    ("_urun_katalog_cache", None),
    ("_urun_katalog_cache_ts", 0.0),
    ("_urun_katalog_cache_stok_mtime", 0.0),
    ("_urunler_magaza_refresh_started_at", 0.0),
    ("active_main_tab", "urun_sec"),
]:
    if k not in st.session_state:
        st.session_state[k] = v

if not st.session_state.pcloud_token and not st.session_state.get("_cikis_yapildi"):
    _tok = os.environ.get("PCLOUD_TOKEN", "")
    if _tok:
        st.session_state.pcloud_token = _tok
        st.session_state.setdefault("pcloud_host", "https://api.pcloud.com")

@st.cache_data(ttl=600, show_spinner=False)
def _token_kaydet(token: str):
    try:
        satirlar = _env_path.read_text().splitlines() if _env_path.exists() else []
        yeni = [l for l in satirlar if not l.startswith("PCLOUD_TOKEN=")]
        yeni.append(f"PCLOUD_TOKEN={token}")
        _env_path.write_text("\n".join(yeni) + "\n")
        os.environ["PCLOUD_TOKEN"] = token
    except Exception:
        pass

# ── Logout ────────────────────────────────────────────────────────────────────
if st.query_params.get("logout") == "1":
    for _k in ["pcloud_token", "klasorler", "secilen"]:
        st.session_state[_k] = None if _k == "pcloud_token" else []
    st.session_state.klasor_id = 0
    st.session_state.magaza_id = None
    st.session_state.magaza_ad = None
    st.session_state.klasor_ad = None
    st.session_state["_cikis_yapildi"] = True
    st.query_params.clear()
    st.rerun()

# ── Mağaza listesi ────────────────────────────────────────────────────────────
try:
    from shared.store_manager import tum_magazalar as _tum_mag
    _mag_ids = [m["store_id"] for m in _tum_mag()]
except Exception:
    _mag_ids = ["PatchArts"]

if st.session_state.hedef_magaza_id not in _mag_ids:
    st.session_state.hedef_magaza_id = _mag_ids[0]

# ── Header ────────────────────────────────────────────────────────────────────
_hc1, _hc2, _hc3 = st.columns([3, 2, 3])

_hc1.markdown(
    "<div style='display:flex;align-items:center;gap:10px;padding:4px 0;'>"
    "<span style='font-size:1.2rem;'>🪄</span>"
    "<span style='font-size:1rem;font-weight:700;color:#e6edf3;'>RugsKilim Panel</span>"
    "</div>",
    unsafe_allow_html=True
)

# Mağaza seçici — orta
_mag_idx = _mag_ids.index(st.session_state.hedef_magaza_id)
def _hedef_magaza_degisti():
    st.session_state.hedef_magaza_id = st.session_state.top_hedef_magaza
    st.session_state.kuyruk_yuklendi = False

_sec_mag = _hc2.selectbox(
    "Hedef Mağaza",
    options=_mag_ids,
    index=_mag_idx,
    key="top_hedef_magaza",
    label_visibility="collapsed",
    on_change=_hedef_magaza_degisti,
)

# pCloud durumu — sağ
if st.session_state.pcloud_token:
    _hc3.markdown(
        f'<div style="display:flex;align-items:center;justify-content:flex-end;gap:12px;padding:4px 0;">'
        f'<span class="store-pill">🏪 {st.session_state.hedef_magaza_id}</span>'
        f'<span class="pcloud-ok">✅ pCloud</span>'
        f'<a href="?logout=1" style="color:#6e7681;font-size:0.75rem;text-decoration:none;">çıkış</a>'
        f'</div>',
        unsafe_allow_html=True
    )
else:
    with _hc3.popover("⚠️ pCloud bağlı değil", width="stretch"):
        st.markdown("##### pCloud Bağlantısı")
        st.caption("**Token nasıl alınır?**  \n"
                   "1. [pcloud.com](https://www.pcloud.com)'a giriş yapın  \n"
                   "2. F12 → Console → kodu çalıştırın:")
        st.code("document.cookie.match(/pcauth=([^;]+)/)[1]", language="javascript")
        _tok_input = st.text_input("Auth Token", placeholder="Token yapıştırın")
        if st.button("🔗 Bağlan", type="primary", width="stretch"):
            if _tok_input.strip():
                st.session_state.pcloud_token = _tok_input.strip()
                st.session_state["pcloud_host"] = "https://api.pcloud.com"
                _token_kaydet(_tok_input.strip())
                try:
                    from shared.sheets import config_yaz
                    config_yaz("PCLOUD_TOKEN", _tok_input.strip())
                except Exception:
                    pass
                st.rerun()
            else:
                st.warning("Token girin.")

st.markdown("<div style='border-bottom:1px solid #30363d;margin:4px 0 12px;'></div>", unsafe_allow_html=True)

# ── Stok otomatik güncelleme ───────────────────────────────────────────────────
import time as _time
import threading as _threading
import re as _re

_STOK_DOSYA   = _RUNTIME_DIR / "stok.xlsx"
_ONEDRIVE_DOWNLOAD_URL = (
    "https://onedrive.live.com/:x:/g/personal/1757a2096148ff8c/"
    "IQCM_0hhCaJXIIAXbgAAAAAAARFeUDCYxPUqlbzQ1a_pyqg"
    "?rtime=dDQIJaur3kg&redeem=aHR0cHM6Ly8xZHJ2Lm1zL3gvYy8xNzU3YTIwOTYxNDhmZjhjL0lRQ01fMGhoQ2FKWElJQVhiZ0FBQUFBQUFSRmVVRENZeFBVcWxielExYV9weXFnP2U9cHlUOXpD&download=1"
)
_ONEDRIVE_FALLBACK_URL = (
    "https://onedrive.live.com/:x:/g/personal/1757A2096148FF8C/"
    "IQCM_0hhCaJXIIAXbgAAAAAAARFeUDCYxPUqlbzQ1a_pyqg"
    "?resid=1757A2096148FF8C!110&ithint=file%2Cxlsx"
    "&e=4%3A6e320296bc824c8199267660515614e4&at=9&download=1"
)
_STOK_LOG = _RUNTIME_DIR / "stok_indir.log"
_STOK_INDIR_BEKLEME_SN = 90
_STORE_INVENTORY_DB = _RUNTIME_DIR / "store_inventory.json"
_SOLD_NOTES_DB = _RUNTIME_DIR / "sold_notes.json"
_GLOBAL_KIRMIZI_DB = _RUNTIME_DIR / "global_kirmizi.json"
_PRODUCT_SOURCE_SYNC_DB = _RUNTIME_DIR / "product_source_sync.json"
_DELETED_PRODUCTS_DB = _RUNTIME_DIR / "deleted_products.json"
_STORE_INVENTORY_TTL_SN = 1800

_SOLD_SITE_LABELS: dict[str, str] = {
    "lmx":   "LoomixRugs",
    "wcr":   "WoolCottonRugs",
    "wtr":   "WovenTurkishRugs",
    "wlr":   "WovenLoomRugs",
    "lr":    "LoopRug",
    "llc":   "RugsKilimLLC",
    "rst":   "RugsShopTurkey",
    "rks":   "RugsKilimStore",
    "bhr":   "BohoRugHouse",
    "old":   "OldNewRugs",
    "pacht": "PatchArts",
    "ilmek": "İlmekRug",
}


def _site_label(raw: str) -> str:
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    return ", ".join(_SOLD_SITE_LABELS.get(p.lower(), p) for p in parts)


def _stok_log_yaz(durum: str, detay: str = ""):
    ts = str(int(_time.time()))
    satir = f"{durum}|{ts}"
    if detay:
        satir += f"|{detay}"
    _STOK_LOG.write_text(satir, encoding="utf-8")


def _stok_log_oku() -> dict:
    if not _STOK_LOG.exists():
        return {"durum": "yok", "ts": None, "detay": ""}
    icerik = _STOK_LOG.read_text(encoding="utf-8").strip()
    if not icerik:
        return {"durum": "yok", "ts": None, "detay": ""}
    if "|" not in icerik:
        if icerik == "INDIRILIYOR":
            return {"durum": "indiriliyor", "ts": None, "detay": ""}
        if icerik == "OK":
            return {"durum": "ok", "ts": None, "detay": ""}
        if icerik.startswith("HATA:"):
            return {"durum": "hata", "ts": None, "detay": icerik[5:].strip()}
        return {"durum": "yok", "ts": None, "detay": icerik}

    parcalar = icerik.split("|", 2)
    durum_raw = parcalar[0].strip().upper()
    ts_raw = parcalar[1].strip() if len(parcalar) > 1 else ""
    detay = parcalar[2].strip() if len(parcalar) > 2 else ""
    durum = {
        "INDIRILIYOR": "indiriliyor",
        "OK": "ok",
        "HATA": "hata",
    }.get(durum_raw, "yok")
    try:
        ts = float(ts_raw) if ts_raw else None
    except ValueError:
        ts = None
    return {"durum": durum, "ts": ts, "detay": detay}


def _stok_dosya_yolu() -> Path:
    if _STOK_DOSYA.exists():
        return _STOK_DOSYA
    if _LEGACY_STOK_DOSYA.exists():
        return _LEGACY_STOK_DOSYA
    return _STOK_DOSYA


def _decimal_str(value, digits: int = 2) -> str:
    try:
        num = float(str(value).replace(",", "."))
    except Exception:
        return ""
    return f"{num:.{digits}f}".rstrip("0").rstrip(".")


def _float_or_none(value):
    try:
        if value in ("", None):
            return None
        return float(str(value).replace(",", "."))
    except Exception:
        return None


def _fmt_size(a, b, digits: int = 1) -> str:
    left = _decimal_str(a, digits=digits)
    right = _decimal_str(b, digits=digits)
    if left and right:
        return f"{left}x{right}"
    return ""


def _derived_product_fields(width_cm, length_cm) -> dict:
    from shared.product_catalog import cm_to_ft_value, derive_category_from_dimensions

    width_cm_value = _float_or_none(width_cm)
    length_cm_value = _float_or_none(length_cm)
    area_m2 = None
    if width_cm_value and length_cm_value:
        area_m2 = (width_cm_value * length_cm_value) / 10000
    width_ft = cm_to_ft_value(width_cm_value)
    length_ft = cm_to_ft_value(length_cm_value)
    return {
        "width_cm": _decimal_str(width_cm_value, digits=0) if width_cm_value else "",
        "length_cm": _decimal_str(length_cm_value, digits=0) if length_cm_value else "",
        "size_cm": _fmt_size(width_cm_value, length_cm_value, digits=0),
        "area_m2": _decimal_str(area_m2, digits=2) if area_m2 else "",
        "width_ft": _decimal_str(width_ft, digits=1) if width_ft else "",
        "length_ft": _decimal_str(length_ft, digits=1) if length_ft else "",
        "size_ft": _fmt_size(width_ft, length_ft, digits=1),
        "category": derive_category_from_dimensions(
            width_cm=width_cm_value,
            length_cm=length_cm_value,
            width_ft=width_ft,
            length_ft=length_ft,
            area_m2=area_m2,
        ),
    }


def _kategori_etiketi(value: str) -> str:
    temiz = str(value or "").strip()
    return temiz or "Boş"


def _product_id_for_code(code: str) -> str:
    clean = (_urun_kodu_normalize(code) or _urun_kodu_al(code) or _kod_normalize(code)).upper()
    return f"PRD-{clean}"


def _copy_display_upper(value: str) -> str:
    return str(value or "").strip().replace("x", "X")


def _copy_display_decimal(value) -> str:
    text = _decimal_str(value, digits=2)
    return text.replace(".", ",") if text else ""


def _copy_display_ft(value: str) -> str:
    return _copy_display_upper(str(value or "").strip().replace(".", ","))


def _build_product_copy_text(product: dict) -> str:
    kod = str(product.get("product_code") or "").strip()
    size_cm = _copy_display_upper(product.get("size_cm"))
    area_m2 = _copy_display_decimal(product.get("area_m2"))
    size_ft = _copy_display_ft(product.get("size_ft"))
    parts = []
    if kod or size_cm:
        parts.append(f"{kod}--{size_cm}".strip("-"))
    if area_m2:
        parts.append(f"= {area_m2} M2")
    if size_ft:
        parts.append(f"{size_ft} FT")
    return " ".join(parts).strip()


@st.cache_data(ttl=600, show_spinner=False)
def _kaynak_stok_urunleri_yukle(dosya_yolu: str, dosya_mtime: float):
    _ = dosya_mtime
    import pandas as pd
    from shared.product_catalog import derive_category_from_dimensions

    satilan_kayitlari = {}
    try:
        sold_df = pd.read_excel(dosya_yolu, sheet_name="SATILANLAR")
        for row_index, row in sold_df.iterrows():
            row_values = list(row.tolist())
            if not row_values:
                continue

            raw_code = row_values[0] if len(row_values) > 0 else ""
            code = _urun_kodu_normalize(raw_code) or _urun_kodu_al(raw_code)
            if not code:
                continue

            width_cm = _float_or_none(row_values[1]) if len(row_values) > 1 else None
            sold_marker = str(row_values[2] or "").strip().upper() if len(row_values) > 2 else ""
            length_cm = _float_or_none(row_values[3]) if len(row_values) > 3 else None
            area_m2 = _float_or_none(row_values[4]) if len(row_values) > 4 else None
            width_ft = _float_or_none(row_values[5]) if len(row_values) > 5 else None
            length_ft = _float_or_none(row_values[6]) if len(row_values) > 6 else None
            sold_site = str(row_values[7] or "").strip() if len(row_values) > 7 else ""
            customer_name = str(row_values[8] or "").strip() if len(row_values) > 8 else ""
            customer_contact_country = str(row_values[9] or "").strip() if len(row_values) > 9 else ""
            note = str(row_values[10] or "").strip() if len(row_values) > 10 else ""

            if not any(v is not None for v in [width_cm, length_cm, area_m2, width_ft, length_ft]) and not (
                sold_marker == "X" or sold_site or customer_name or customer_contact_country or note
            ):
                continue

            category = derive_category_from_dimensions(
                width_cm=width_cm,
                length_cm=length_cm,
                width_ft=width_ft,
                length_ft=length_ft,
                area_m2=area_m2,
                source_tab="SATILANLAR",
            )
            satilan_kayitlari[code] = {
                "product_id": _product_id_for_code(code),
                "product_code": code,
                "category": category or "",
                "width_cm": _decimal_str(width_cm, digits=0),
                "length_cm": _decimal_str(length_cm, digits=0),
                "size_cm": _fmt_size(width_cm, length_cm, digits=0),
                "area_m2": _decimal_str(area_m2, digits=2),
                "width_ft": _decimal_str(width_ft, digits=1),
                "length_ft": _decimal_str(length_ft, digits=1),
                "size_ft": _fmt_size(width_ft, length_ft, digits=1),
                "status": "sold",
                "source_tab": "SATILANLAR",
                "source_row": str(int(row_index) + 2),
                "loaded_store_count": "",
                "loaded_stores": "",
                "sold_at": "",
                "sold_site": sold_site,
                "customer_name": customer_name,
                "customer_phone": "",
                "customer_address": "",
                "customer_contact_country": customer_contact_country,
                "note": note,
                "updated_at": "",
                "_kaynak": "Satilanlar",
            }
    except Exception:
        pass

    satilanlar = set(satilan_kayitlari) | _satilan_kodlar(dosya_yolu)
    urunler = []
    eklenen_kodlar = set()
    sheet_specs = [
        ("VİNTAGE RUG", "Vintage"),
        ("VINTAGE RUG", "Vintage"),
        ("DOOR MAT RUGS", "Doormat"),
        ("KILIM RUG", "Kilim"),
    ]

    for tab_adi, kaynak_etiketi in sheet_specs:
        try:
            df = pd.read_excel(dosya_yolu, sheet_name=tab_adi)
        except Exception:
            continue

        for row_index, row in df.iterrows():
            row_values = list(row.tolist())
            if len(row_values) < 7:
                continue

            raw_code = row_values[0]
            code = _urun_kodu_normalize(raw_code) or _urun_kodu_al(raw_code)
            if not code:
                continue

            width_cm = _float_or_none(row_values[1])
            sold_marker = str(row_values[2] or "").strip().upper()
            length_cm = _float_or_none(row_values[3])
            area_m2 = _float_or_none(row_values[4])
            width_ft = _float_or_none(row_values[5])
            length_ft = _float_or_none(row_values[6])

            if not any(v is not None for v in [width_cm, length_cm, area_m2, width_ft, length_ft]):
                continue

            status = "sold" if sold_marker == "X" or code in satilanlar else "active"
            size_ft = _fmt_size(width_ft, length_ft, digits=1)
            satilan_bilgi = satilan_kayitlari.get(code, {})
            urunler.append({
                "product_id": _product_id_for_code(code),
                "product_code": code,
                "category": derive_category_from_dimensions(
                    width_cm=width_cm,
                    length_cm=length_cm,
                    width_ft=width_ft,
                    length_ft=length_ft,
                    area_m2=area_m2,
                    source_tab=tab_adi,
                ),
                "width_cm": _decimal_str(width_cm, digits=0),
                "length_cm": _decimal_str(length_cm, digits=0),
                "size_cm": _fmt_size(width_cm, length_cm, digits=0),
                "area_m2": _decimal_str(area_m2, digits=2),
                "width_ft": _decimal_str(width_ft, digits=1),
                "length_ft": _decimal_str(length_ft, digits=1),
                "size_ft": size_ft,
                "status": status,
                "source_tab": tab_adi,
                "source_row": str(int(row_index) + 2),
                "loaded_store_count": "",
                "loaded_stores": "",
                "sold_at": satilan_bilgi.get("sold_at", ""),
                "sold_site": satilan_bilgi.get("sold_site", ""),
                "customer_name": satilan_bilgi.get("customer_name", ""),
                "customer_phone": satilan_bilgi.get("customer_phone", ""),
                "customer_address": satilan_bilgi.get("customer_address", ""),
                "customer_contact_country": satilan_bilgi.get("customer_contact_country", ""),
                "note": satilan_bilgi.get("note", ""),
                "updated_at": "",
                "_kaynak": kaynak_etiketi,
            })
            eklenen_kodlar.add(code)

    for code, satilan_urun in satilan_kayitlari.items():
        if code in eklenen_kodlar:
            continue
        urunler.append(dict(satilan_urun))
    return urunler


def _urun_kaynak_sync_bilgisi():
    return _json_yukle(_PRODUCT_SOURCE_SYNC_DB, {"stok_mtime": 0, "updated_at": 0, "source_count": 0})


def _urun_katalogunu_esitle(force: bool = False, kaynak_urunler: list[dict] | None = None):
    from shared.product_catalog import ProductCatalog, _supabase_ready

    if not _supabase_ready():
        return False

    stok = _stok_dosya_yolu()
    if not stok.exists():
        return False

    stok_mtime = float(stok.stat().st_mtime)
    sync_bilgi = _urun_kaynak_sync_bilgisi()
    if not force and float(sync_bilgi.get("stok_mtime") or 0) == stok_mtime:
        return False

    kaynak = kaynak_urunler or _kaynak_stok_urunleri_yukle(str(stok), stok_mtime)
    kaynak = _silinenleri_filtrele(kaynak)
    ProductCatalog().replace_from_source(kaynak)
    _json_kaydet(
        _PRODUCT_SOURCE_SYNC_DB,
        {"stok_mtime": stok_mtime, "updated_at": _time.time(), "source_count": len(kaynak)},
    )
    return True


def _urunleri_yukle(force_source_sync: bool = False, force_store_refresh: bool = False):
    from shared.product_catalog import ProductCatalog, _supabase_ready
    stok = _stok_dosya_yolu()
    stok_mtime = float(stok.stat().st_mtime) if stok.exists() else 0.0
    cache_ts = float(st.session_state.get("_urun_katalog_cache_ts") or 0.0)
    cache_stok_mtime = float(st.session_state.get("_urun_katalog_cache_stok_mtime") or 0.0)
    cache_data = st.session_state.get("_urun_katalog_cache")

    if (
        not force_source_sync
        and cache_data is not None
        and cache_stok_mtime == stok_mtime
        and (_time.time() - cache_ts) <= 300
    ):
        return [dict(item) for item in cache_data]

    if _supabase_ready():
        _force_env = force_store_refresh
        def _envanter_sync_job():
            try:
                _magaza_envanterini_topla(force=_force_env)
            except Exception:
                pass
        _threading.Thread(target=_envanter_sync_job, daemon=True, name="magaza-envanter-sync").start()

    kaynak = []
    if stok.exists():
        kaynak = _kaynak_stok_urunleri_yukle(str(stok), stok_mtime)
        if _supabase_ready():
            try:
                _urun_katalogunu_esitle(force=force_source_sync, kaynak_urunler=kaynak)
            except Exception:
                pass

    try:
        mevcut = ProductCatalog().list_products() if _supabase_ready() else _panel_urunleri_yerden_yukle()
    except Exception:
        mevcut = _panel_urunleri_yerden_yukle()

    if force_source_sync and stok.exists() and (not _supabase_ready() or not mevcut):
        mevcut_map = {
            str(item.get("product_code") or "").strip(): dict(item)
            for item in mevcut
            if str(item.get("product_code") or "").strip()
        }
        for item in kaynak:
            kod = str(item.get("product_code") or "").strip()
            if not kod:
                continue
            onceki = mevcut_map.get(kod, {})
            yeni = dict(item)
            yeni["category"] = item.get("category") or onceki.get("category") or ""
            yeni["loaded_store_count"] = onceki.get("loaded_store_count", 0)
            yeni["loaded_stores"] = onceki.get("loaded_stores", "")
            yeni["sold_at"] = item.get("sold_at") or onceki.get("sold_at", "")
            yeni["sold_site"] = item.get("sold_site") or onceki.get("sold_site", "")
            yeni["customer_name"] = item.get("customer_name") or onceki.get("customer_name", "")
            yeni["customer_phone"] = item.get("customer_phone") or onceki.get("customer_phone", "")
            yeni["customer_address"] = item.get("customer_address") or onceki.get("customer_address", "")
            yeni["customer_contact_country"] = item.get("customer_contact_country") or onceki.get("customer_contact_country", "")
            yeni["note"] = item.get("note") or onceki.get("note", "")
            yeni["status"] = "sold" if str(item.get("status", "")).lower() == "sold" else str(onceki.get("status", "")).lower() or "active"
            mevcut_map[kod] = yeni
        mevcut = sorted(mevcut_map.values(), key=lambda x: str(x.get("product_code") or ""))
        _json_kaydet(_RUNTIME_DIR / "panel_products.json", mevcut)

    mevcut = _silinenleri_filtrele(mevcut)
    st.session_state["_urun_katalog_cache"] = [dict(item) for item in mevcut]
    st.session_state["_urun_katalog_cache_ts"] = _time.time()
    st.session_state["_urun_katalog_cache_stok_mtime"] = stok_mtime
    return mevcut


def _urun_sheet_sync_arkaplanda(force: bool = True):
    def _job():
        try:
            from shared.product_sheet_sync import sync_product_sheet
            sync_product_sheet(force=force)
        except Exception:
            pass

    _threading.Thread(target=_job, daemon=True, name="urun-sheet-sync").start()


def _urunleri_kaydet(products: list[dict], *, incremental: bool = False, sync_sheet: bool = True):
    from shared.product_catalog import ProductCatalog, _supabase_ready

    if _supabase_ready():
        ProductCatalog().upsert_products(products)
        if sync_sheet:
            _urun_sheet_sync_arkaplanda(force=True)
    else:
        if incremental:
            mevcut = _panel_urunleri_yerden_yukle()
            mevcut_map = {
                str(item.get("product_code") or "").strip(): dict(item)
                for item in mevcut
                if str(item.get("product_code") or "").strip()
            }
            for urun in products:
                kod = str(urun.get("product_code") or "").strip()
                if kod:
                    mevcut_map[kod] = dict(urun)
            products = list(mevcut_map.values())
        _json_kaydet(_RUNTIME_DIR / "panel_products.json", products)
        st.toast("Yerel JSON'a kaydedildi (Supabase yapılandırılmamış)", icon="💾")
    st.session_state["_urun_katalog_cache"] = None
    st.session_state["_urun_katalog_cache_ts"] = 0.0
    st.session_state["_urun_katalog_cache_stok_mtime"] = 0.0


def _urunleri_cachede_uste_tut(urun: dict, *, remove_code: str | None = None):
    kod = str((urun or {}).get("product_code") or "").strip()
    if not kod:
        return
    silinecek_eski = str(remove_code or "").strip()

    mevcut_cache = st.session_state.get("_urun_katalog_cache")
    if mevcut_cache is None:
        mevcut = _panel_urunleri_yerden_yukle()
    else:
        mevcut = [dict(item) for item in mevcut_cache]

    yeni_liste = [dict(urun)]
    yeni_liste.extend(
        item for item in mevcut
        if str(item.get("product_code") or "").strip() not in {kod, silinecek_eski}
    )
    yeni_liste = _silinenleri_filtrele(yeni_liste)

    stok = _stok_dosya_yolu()
    st.session_state["_urun_katalog_cache"] = [dict(item) for item in yeni_liste]
    st.session_state["_urun_katalog_cache_ts"] = _time.time()
    st.session_state["_urun_katalog_cache_stok_mtime"] = float(stok.stat().st_mtime) if stok.exists() else 0.0
    _json_kaydet(_RUNTIME_DIR / "panel_products.json", yeni_liste)


def _urunleri_kaydet_arkaplanda(products: list[dict], *, incremental: bool = False, sync_sheet: bool = True):
    payload = [dict(item) for item in (products or [])]

    def _job():
        from shared.product_catalog import ProductCatalog, _supabase_ready

        try:
            if _supabase_ready():
                ProductCatalog().upsert_products(payload)
                if sync_sheet:
                    from shared.product_sheet_sync import sync_product_sheet
                    sync_product_sheet(force=True)
            elif incremental:
                mevcut = _json_yukle(_RUNTIME_DIR / "panel_products.json", [])
                mevcut_map = {
                    str(item.get("product_code") or "").strip(): dict(item)
                    for item in mevcut
                    if str(item.get("product_code") or "").strip()
                }
                for urun in payload:
                    kod = str(urun.get("product_code") or "").strip()
                    if kod:
                        mevcut_map[kod] = dict(urun)
                _json_kaydet(_RUNTIME_DIR / "panel_products.json", list(mevcut_map.values()))
        except Exception:
            pass

    _threading.Thread(target=_job, daemon=True, name="urun-kaydet").start()


def _urun_guncelle_arkaplanda(urun: dict, *, old_code: str | None = None):
    payload = dict(urun or {})
    eski_kod = str(old_code or "").strip()

    def _job():
        from shared.product_catalog import ProductCatalog as _PC_BG, _supabase_ready as _supabase_ready_bg
        import requests as _req_bg

        try:
            if _supabase_ready_bg():
                yeni_kod = str(payload.get("product_code") or "").strip()
                if eski_kod and yeni_kod and eski_kod != yeni_kod:
                    _supa_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
                    _supa_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
                    _rename_resp = _req_bg.patch(
                        f"{_supa_url}/rest/v1/products",
                        headers={
                            "apikey": _supa_key,
                            "Authorization": f"Bearer {_supa_key}",
                            "Content-Type": "application/json",
                            "Prefer": "return=minimal",
                        },
                        params={"product_code": f"eq.{eski_kod}"},
                        json={"product_code": yeni_kod},
                        timeout=30,
                    )
                    _rename_resp.raise_for_status()
                _PC_BG().upsert_products([payload])
                _urun_sheet_sync_arkaplanda(force=True)
            else:
                _urunleri_kaydet([payload], incremental=True, sync_sheet=False)
        except Exception:
            pass

    _threading.Thread(target=_job, daemon=True, name="urun-guncelle").start()


def _urun_sil_arkaplanda(kod: str):
    silinecek_kod = str(kod or "").strip()

    def _job():
        from shared.product_catalog import ProductCatalog as _PC_DEL, StoreCatalog as _SC_DEL, _supabase_ready as _supabase_ready_del

        try:
            if _supabase_ready_del():
                _PC_DEL().delete_products([silinecek_kod])
                try:
                    for _magaza in _SC_DEL().as_inventory_cache().get("stores", {}).keys():
                        _SC_DEL().delete(_magaza, [silinecek_kod])
                except Exception:
                    pass
                _urun_sheet_sync_arkaplanda(force=True)
            else:
                _yerel = [
                    item for item in _panel_urunleri_yerden_yukle()
                    if str(item.get("product_code") or "").strip() != silinecek_kod
                ]
                _json_kaydet(_RUNTIME_DIR / "panel_products.json", _yerel)
        except Exception:
            pass

    _threading.Thread(target=_job, daemon=True, name="urun-sil").start()


def _urunler_magaza_yenilemesini_baslat(force: bool = False):
    dosya_cache = _envanter_cache_dosyadan_yukle()
    son_baslangic = float(st.session_state.get("_urunler_magaza_refresh_started_at") or 0.0)
    cache_updated = float((dosya_cache or {}).get("updated_at") or 0.0)
    if not force and son_baslangic and son_baslangic > cache_updated:
        return

    baslangic = _time.time()
    st.session_state["_urunler_magaza_refresh_started_at"] = baslangic

    def _job():
        try:
            _magaza_envanterini_topla(force=force)
        except Exception:
            pass

    _threading.Thread(target=_job, daemon=True, name="urunler-magaza-refresh").start()


def _urun_katalog_cache_temizle():
    st.session_state["_urun_katalog_cache"] = None
    st.session_state["_urun_katalog_cache_ts"] = 0.0
    st.session_state["_urun_katalog_cache_stok_mtime"] = 0.0


@st.cache_data(ttl=90, show_spinner=False)
def _kuyruk_satirlari_cached(store_id: str):
    from shared.product_catalog import _supabase_ready
    from shared.sheets import SheetsKatmani as _SK_QUEUE_CACHE

    store_id = str(store_id or "").strip()
    if not store_id:
        return []

    satirlar = _supabase_kuyruk_satirlari(store_id) if _supabase_ready() else None
    if satirlar is None:
        satirlar = _SK_QUEUE_CACHE(store_id).tum_satirlar_al()
    return satirlar or []


@st.cache_data(ttl=600, show_spinner=False)
def _tum_magaza_kod_haritasi(token: str, host: str):
    _, magazalar = _magazalari_otomatik_bul(token, host)
    sonuc = {}
    for magaza in magazalar:
        kodlar = _magaza_tum_kodlar(token, host, magaza["id"])
        temiz = set()
        for kod in kodlar:
            norm = _urun_kodu_normalize(kod) or _urun_kodu_al(kod)
            if norm:
                temiz.add(norm)
        sonuc[magaza["ad"]] = temiz
    return sonuc


def _stok_son_guncelleme_ts() -> float:
    _dosya = _stok_dosya_yolu()
    if _dosya.exists():
        return _dosya.stat().st_mtime
    return 0.0


def _stok_dosyayi_kaydet(kaynak: Path | bytes, kaynak_etiketi: str):
    gecici = _RUNTIME_DIR / "stok.xlsx.tmp"
    if isinstance(kaynak, Path):
        shutil.copyfile(kaynak, gecici)
    else:
        gecici.write_bytes(kaynak)
    gecici.replace(_STOK_DOSYA)
    _stok_log_yaz("OK", kaynak_etiketi)


def _stok_indirme_url_listesi():
    adaylar = [_ONEDRIVE_DOWNLOAD_URL, _ONEDRIVE_FALLBACK_URL]
    return list(dict.fromkeys(adaylar))


def _downloads_klasorleri():
    return [
        Path.home() / "Downloads",
        Path.home() / "downloads",
    ]


def _downloads_excel_adaylari():
    desenler = [
        "Anatolian Rugs Excel*.xlsx",
        "anatolian rugs excel*.xlsx",
        "*.xlsx",
    ]
    adaylar = []
    for klasor in _downloads_klasorleri():
        if not klasor.exists():
            continue
        for desen in desenler:
            adaylar.extend(klasor.glob(desen))
    adaylar = [p for p in adaylar if p.is_file() and not p.name.startswith("~$")]
    return sorted(set(adaylar), key=lambda p: p.stat().st_mtime, reverse=True)


def _downloads_stok_dosyasi_bul(baslangic_ts: float) -> Path | None:
    for aday in _downloads_excel_adaylari():
        try:
            if aday.stat().st_mtime >= baslangic_ts and aday.stat().st_size > 0:
                return aday
        except FileNotFoundError:
            continue
    return None


def _tarayicidan_stok_indir_ve_kaydet() -> bool:
    baslangic_ts = _time.time() - 2
    try:
        subprocess.run(["open", _ONEDRIVE_DOWNLOAD_URL], check=True)
    except Exception as exc:
        raise RuntimeError(f"Tarayici acilamadi: {exc}") from exc

    son_hata = "Downloads klasorunde yeni Excel bulunamadi"
    bitis = _time.time() + _STOK_INDIR_BEKLEME_SN
    while _time.time() < bitis:
        aday = _downloads_stok_dosyasi_bul(baslangic_ts)
        if aday is not None:
            try:
                _stok_dosyayi_kaydet(aday, f"downloads:{aday}")
                return True
            except Exception as exc:
                son_hata = f"Downloads dosyasi kopyalanamadi: {exc}"
                break
        _time.sleep(2)
    raise RuntimeError(son_hata)


def _stok_indirme_gerekli(force: bool = False) -> bool:
    if force:
        return True
    son_guncelleme = _stok_son_guncelleme_ts()
    if not son_guncelleme:
        return True
    return (_time.time() - son_guncelleme) > 43200


def _stok_indirmeyi_baslat(force: bool = False) -> bool:
    if _stok_log_durumu() == "indiriliyor":
        return False
    if not _stok_indirme_gerekli(force=force):
        return False

    _stok_log_yaz("INDIRILIYOR")
    st.session_state.stok_son_indirme = _time.time()

    def _stok_indir():
        son_hata = "Bilinmeyen hata"
        for url in _stok_indirme_url_listesi():
            try:
                r = httpx.get(
                    url,
                    follow_redirects=True,
                    timeout=60,
                    headers={"User-Agent": "Mozilla/5.0"},
                )
                r.raise_for_status()
                content = r.content
                if content[:4] != b'PK\x03\x04':
                    snippet = content[:300].decode("utf-8", errors="replace")
                    raise ValueError(f"XLSX değil. Yanıt: {snippet}")
                _stok_dosyayi_kaydet(content, url)
                return
            except Exception as _e:
                son_hata = str(_e)
        try:
            if _tarayicidan_stok_indir_ve_kaydet():
                return
        except Exception as _e:
            son_hata = str(_e)
        _stok_log_yaz("HATA", son_hata)

    _threading.Thread(target=_stok_indir, daemon=True).start()
    return True

def _stok_log_durumu():
    log = _stok_log_oku()
    if log["durum"] == "hata":
        return f"HATA: {log['detay']}" if log["detay"] else "HATA"
    return log["durum"]

_stok_indirmeyi_baslat()

# Mağaza değişince kuyruk sıfırla
if st.session_state.get("kuyruk_magaza_id") != st.session_state.hedef_magaza_id:
    st.session_state.kuyruk_yuklendi = False

if not st.session_state.get("sheet_renk_durumlari") and st.session_state.get("kuyruga_eklenenler"):
    st.session_state.kuyruk_yuklendi = False


def _kuyruk_cache_hazirla(store_id: str | None = None, force: bool = False):
    hedef_magaza = str(store_id or st.session_state.hedef_magaza_id or "").strip()
    if not hedef_magaza:
        return
    if not force and st.session_state.get("kuyruk_yuklendi") and st.session_state.get("kuyruk_magaza_id") == hedef_magaza:
        return
    try:
        from shared.sheets import SheetsKatmani
        _sk_init = SheetsKatmani(hedef_magaza)
        _sk_init.sheet_hazirla()
        _satirlar_init = _sk_init.tum_satirlar_al()

        def _ilk_kod(_deger):
            _metin = str(_deger or "").strip()
            _es = _re.match(r"^([A-Za-z]{0,3})\s*(\d+)\b", _metin)
            if _es:
                return f"{(_es.group(1) or '').lower()}{_es.group(2)}"
            return _metin

        st.session_state.kuyruga_eklenenler = {
            _ilk_kod(str(s.get("urun_id", ""))): str(s.get("status", "pending"))
            for s in _satirlar_init if s.get("urun_id")
        }
        st.session_state.kuyruk_klasor_durumlari = {
            str(s.get("pcloud_klasor_id", "")).strip(): str(s.get("status", "pending")).strip().lower()
            for s in _satirlar_init
            if str(s.get("pcloud_klasor_id", "")).strip()
        }
        st.session_state.sheet_renk_durumlari = {}
        st.session_state.klasor_id_durumlari = {}
        st.session_state.kuyruk_magaza_id = hedef_magaza
    except Exception:
        pass
    st.session_state["kuyruk_yuklendi"] = True

# ── Helpers ───────────────────────────────────────────────────────────────────
def _eslesen_deger_al(mapping: dict, klasor_adi: str):
    klasor_adi = str(klasor_adi or "")
    for anahtar, deger in mapping.items():
        if anahtar and (klasor_adi == anahtar or klasor_adi.startswith(anahtar) or anahtar.startswith(klasor_adi)):
            return deger
    return None


def _urun_kodu_al(deger: str) -> str:
    metin = str(deger or "").strip()
    eslesme = _re.match(r"(\d+)", metin)
    return eslesme.group(1) if eslesme else _kod_normalize(metin)


def _urun_kodu_adaylari(deger: str) -> list[str]:
    metin = str(deger or "").strip()
    if not metin:
        return []

    adaylar = []
    for eslesme in _re.finditer(r"([A-Za-z]{0,3})\s*(\d{2,})", metin):
        harf = (eslesme.group(1) or "").strip().lower()
        rakam = (eslesme.group(2) or "").strip()
        if not rakam or set(rakam) == {"0"}:
            continue
        adaylar.append((f"{harf}{rakam}" if harf else rakam, len(rakam), len(harf)))

    adaylar.sort(key=lambda item: (item[1], item[2], len(item[0])), reverse=True)
    return list(dict.fromkeys(item[0] for item in adaylar))


def _urun_kodu_normalize(deger: str):
    metin = str(deger or "").strip()
    if not metin:
        return None

    # Ürün kodu sadece baştan alınır; sonrasındaki llc/rst/+/! gibi ekler yok sayılır.
    eslesme = _re.match(r"^([A-Za-z]{0,3})\s*(\d+)\b", metin)
    if not eslesme:
        return None

    harf = (eslesme.group(1) or "").lower()
    rakam = eslesme.group(2)
    return f"{harf}{rakam}"


def _klasor_urun_kodu_al(klasor_adi: str):
    metin = str(klasor_adi or "").strip()
    if not metin:
        return None

    # Ara navigasyon klasorleri (2025, 24,03,2025, 27,03,2025 yeni mallar) urun gibi boyanmasin.
    if _re.fullmatch(r"20\d{2}", metin):
        return None
    if _re.match(r"^\d{1,2}[,./-]\d{1,2}[,./-]\d{2,4}(?:\b|[\s_-].*)?$", metin):
        return None

    kod = _urun_kodu_normalize(metin)
    return kod or None


def _guvenli_urun_kodu_bul(klasor_adi: str, dosya_adlari: list[str] | None = None) -> str:
    aday_metinler = []
    if dosya_adlari:
        aday_metinler.extend(
            str(ad or "").strip()
            for ad in dosya_adlari
            if "m2" in str(ad or "").lower()
        )
        aday_metinler.extend(str(ad or "").strip() for ad in dosya_adlari)
    aday_metinler.append(str(klasor_adi or "").strip())

    for metin in aday_metinler:
        adaylar = _urun_kodu_adaylari(metin)
        if adaylar:
            return adaylar[0]

    return _klasor_urun_kodu_al(klasor_adi) or _urun_kodu_al(klasor_adi) or str(klasor_adi or "").strip()


def _sheet_renk_durumu(klasor_adi: str):
    if _klasor_satilan_mi(klasor_adi):
        return "red"
    kod = _klasor_urun_kodu_al(klasor_adi)
    if not kod:
        return None
    if kod in _manuel_kirmizi_kodlar():
        return "red"
    if kod in _magaza_yuklu_kodlari_al(st.session_state.get("hedef_magaza_id", "")):
        return "green"
    return st.session_state.sheet_renk_durumlari.get(kod)


def _sheet_renk_durumu_klasor(klasor_id, klasor_adi: str):
    if _klasor_satilan_mi(klasor_adi):
        return "red"
    kod = _klasor_urun_kodu_al(klasor_adi)
    if kod and kod in _manuel_kirmizi_kodlar():
        return "red"
    if kod and kod in _magaza_yuklu_kodlari_al(st.session_state.get("hedef_magaza_id", "")):
        return "green"
    kid = str(klasor_id or "").strip()
    if kid and kid in st.session_state.klasor_id_durumlari:
        return st.session_state.klasor_id_durumlari.get(kid)
    return _sheet_renk_durumu(klasor_adi)


def _satilan_kod_cache_yenile():
    stok_yolu = _stok_dosya_yolu()
    satilan = _satilan_kodlar(str(stok_yolu)) if stok_yolu.exists() else set()
    st.session_state.satilan_kodlar_cache = sorted(satilan)
    return satilan


def _satilan_kodlar_kumesi() -> set[str]:
    return set(st.session_state.get("satilan_kodlar_cache") or [])


def _manuel_kirmizi_kodlar() -> set[str]:
    return set(st.session_state.get("global_kirmizi_kodlar") or [])


def _urun_kodu_bloklu_mu(kod: str) -> bool:
    key = str(kod or "").strip()
    if not key:
        return False
    return key in _manuel_kirmizi_kodlar() or key in _satilan_kodlar_kumesi()


def _klasor_satilan_mi(klasor_adi: str) -> bool:
    key = _klasor_urun_kodu_al(klasor_adi)
    if not key:
        return False
    return key in _satilan_kodlar_kumesi()


def _klasor_bloklu_mu(klasor_adi: str) -> bool:
    if _klasor_satilan_mi(klasor_adi):
        return True
    kod = _klasor_urun_kodu_al(klasor_adi)
    return bool(kod and kod in _manuel_kirmizi_kodlar())


def _secili_item_bloklu_mu(item: dict) -> bool:
    if not item.get("is_product_folder", True):
        return False
    return _klasor_bloklu_mu(item.get("ad", ""))


def _global_kirmizi_kodlari_yenile():
    try:
        from shared.store_manager import tum_magazalar as _tum_magazalar
        from shared.sheets import SheetsKatmani as _SK_GLOBAL
    except Exception:
        return set(st.session_state.get("global_kirmizi_kodlar") or [])

    kirmizilar = set()
    for magaza in _tum_magazalar():
        store_id = str(magaza.get("store_id") or "").strip()
        if not store_id:
            continue
        try:
            renkler = _SK_GLOBAL(store_id).urun_renk_durumlari_al()
            for urun_id, renk in renkler.items():
                if renk == "red":
                    kod = _urun_kodu_normalize(urun_id) or _urun_kodu_al(urun_id)
                    if kod:
                        kirmizilar.add(kod)
        except Exception:
            continue

    st.session_state.global_kirmizi_kodlar = sorted(kirmizilar)
    st.session_state.global_kirmizi_cache_yuklendi = True
    st.session_state.global_kirmizi_cache_ts = _time.time()
    _global_kirmizi_db_kaydet(kirmizilar)
    return kirmizilar


def _global_kirmizi_cache_bayatti(ttl_sn: int = 300) -> bool:
    try:
        return (_time.time() - float(st.session_state.get("global_kirmizi_cache_ts") or 0)) > ttl_sn
    except Exception:
        return True


def _magaza_yuklu_kodlari_al(store_id: str, force: bool = False, include_blocked: bool = False) -> set[str]:
    store_id = str(store_id or "").strip()
    if not store_id:
        return set()

    cache_key = f"loaded_codes::{store_id}"
    ts_key = f"{cache_key}::ts"
    if not force:
        try:
            son_okuma = float(st.session_state.get(ts_key) or 0)
        except Exception:
            son_okuma = 0
        if son_okuma and (_time.time() - son_okuma) <= 60:
            return set(st.session_state.get(cache_key) or [])

    try:
        envanter = _envanter_cache_yukle()
    except Exception:
        envanter = {"stores": {}}

    store_data = (envanter.get("stores") or {}).get(store_id) or {}
    urunler = store_data.get("urunler") or {}
    yuklu_kodlar = set()
    for raw_code, urun in urunler.items():
        kod = _urun_kodu_normalize(raw_code) or _urun_kodu_al(raw_code)
        if not kod:
            continue
        if not include_blocked and _urun_kodu_bloklu_mu(kod):
            continue
        renk = str((urun or {}).get("renk", "")).strip().lower()
        durum = str((urun or {}).get("status", "")).strip().lower()
        if renk == "green" or durum == "done":
            yuklu_kodlar.add(kod)

    st.session_state[cache_key] = sorted(yuklu_kodlar)
    st.session_state[ts_key] = _time.time()
    return yuklu_kodlar


def _magaza_renk_cache_yenile(store_id: str):
    from shared.sheets import SheetsKatmani as _SK_REFRESH

    _sk_refresh = _SK_REFRESH(store_id)
    _satirlar_refresh = _sk_refresh.tum_satirlar_al()
    _renkler_refresh = {
        (_urun_kodu_normalize(k) or _urun_kodu_al(k)): v for k, v in _sk_refresh.urun_renk_durumlari_al().items()
    }
    st.session_state.sheet_renk_durumlari = _renkler_refresh
    st.session_state.klasor_id_durumlari = {
        str(s.get("pcloud_klasor_id", "")).strip(): _renkler_refresh.get(_urun_kodu_normalize(s.get("urun_id", "")) or _urun_kodu_al(s.get("urun_id", "")))
        for s in _satirlar_refresh
        if str(s.get("pcloud_klasor_id", "")).strip()
        and _renkler_refresh.get(_urun_kodu_normalize(s.get("urun_id", "")) or _urun_kodu_al(s.get("urun_id", "")))
    }
    st.session_state.kuyruk_klasor_durumlari = {
        str(s.get("pcloud_klasor_id", "")).strip(): str(s.get("status", "")).strip().lower()
        for s in _satirlar_refresh
        if str(s.get("pcloud_klasor_id", "")).strip() and str(s.get("status", "")).strip()
    }
    st.session_state.sheet_renk_cache_ts = _time.time()
    _magaza_yuklu_kodlari_al(store_id, force=True)
    if _global_kirmizi_cache_bayatti():
        _global_kirmizi_kodlari_yenile()
    return _satirlar_refresh, _renkler_refresh


def _sheet_renk_cache_bayatti(ttl_sn: int = 90) -> bool:
    try:
        return (_time.time() - float(st.session_state.get("sheet_renk_cache_ts") or 0)) > ttl_sn
    except Exception:
        return True


def _json_yukle(path: Path, default):
    try:
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _json_kaydet(path: Path, veri):
    try:
        path.write_text(json.dumps(veri, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def _panel_urunleri_yerden_yukle() -> list[dict]:
    # Yerel fallback kaynagi da silinen urunler listesini dikkate almali;
    # aksi halde canli katalog okunamadiginda silinmis kodlar tekrar gorunebiliyor.
    return _silinenleri_filtrele(_json_yukle(_RUNTIME_DIR / "panel_products.json", []))


def _kod_key(value) -> str:
    return str(value or "").strip().lower()


def _silinen_urunler_db_yukle():
    return _json_yukle(_DELETED_PRODUCTS_DB, {"updated_at": 0, "codes": []})


def _silinen_urun_kodlari() -> set[str]:
    return {
        _kod_key(code)
        for code in (_silinen_urunler_db_yukle().get("codes") or [])
        if _kod_key(code)
    }


def _silinen_urun_kodlari_kaydet(kodlar) -> None:
    temiz = sorted({_kod_key(kod) for kod in kodlar if _kod_key(kod)})
    _json_kaydet(
        _DELETED_PRODUCTS_DB,
        {"updated_at": _time.time(), "codes": temiz},
    )


def _silinen_urune_ekle(kod: str) -> None:
    kodlar = _silinen_urun_kodlari()
    key = _kod_key(kod)
    if not key:
        return
    kodlar.add(key)
    _silinen_urun_kodlari_kaydet(kodlar)


def _silinen_urunden_cikar(kod: str) -> None:
    kodlar = _silinen_urun_kodlari()
    key = _kod_key(kod)
    if key in kodlar:
        kodlar.remove(key)
        _silinen_urun_kodlari_kaydet(kodlar)


def _silinenleri_filtrele(products: list[dict]) -> list[dict]:
    silinenler = _silinen_urun_kodlari()
    if not silinenler:
        return products
    return [
        urun for urun in products
        if _kod_key(urun.get("product_code")) not in silinenler
    ]


def _zorunlu_label(text: str) -> str:
    return f"{text} <span class='req-star'>*</span>"


def _envanter_cache_yukle():
    from shared.product_catalog import StoreCatalog, _supabase_ready
    dosya_cache = _envanter_cache_dosyadan_yukle()
    if not _envanter_cache_stale_mi(dosya_cache):
        return dosya_cache
    if _supabase_ready():
        try:
            return StoreCatalog().as_inventory_cache()
        except Exception:
            pass
    return dosya_cache


def _envanter_cache_dosyadan_yukle():
    return _json_yukle(_STORE_INVENTORY_DB, {"updated_at": 0, "stores": {}, "errors": {}})


def _notlar_db_yukle():
    return _json_yukle(_SOLD_NOTES_DB, {"updated_at": 0, "notes": {}})


def _global_kirmizi_db_yukle():
    return _json_yukle(_GLOBAL_KIRMIZI_DB, {"updated_at": 0, "kodlar": []})


def _global_kirmizi_db_kaydet(kodlar):
    _json_kaydet(
        _GLOBAL_KIRMIZI_DB,
        {"updated_at": _time.time(), "kodlar": sorted({str(k).strip() for k in kodlar if str(k).strip()})},
    )


if not st.session_state.get("global_kirmizi_cache_yuklendi"):
    _global_db = _global_kirmizi_db_yukle()
    st.session_state.global_kirmizi_kodlar = sorted(_global_db.get("kodlar") or [])
    st.session_state.global_kirmizi_cache_yuklendi = True
    st.session_state.global_kirmizi_cache_ts = float(_global_db.get("updated_at") or 0)


def _envanter_cache_stale_mi(cache: dict, ttl_sn: int = _STORE_INVENTORY_TTL_SN) -> bool:
    try:
        updated_at = float(cache.get("updated_at") or 0)
    except Exception:
        updated_at = 0
    if not updated_at:
        return True
    return (_time.time() - updated_at) > ttl_sn


def _magaza_cache_stale_mi(cache: dict, store_id: str, ttl_sn: int = 120) -> bool:
    try:
        store_cache = ((cache or {}).get("stores") or {}).get(store_id) or {}
        updated_at = float(store_cache.get("updated_at") or cache.get("updated_at") or 0)
    except Exception:
        updated_at = 0
    if not updated_at:
        return True
    return (_time.time() - updated_at) > ttl_sn


def _sheetten_magaza_envanteri_oku(store_id: str, store_name: str) -> dict:
    durum_haritasi = _sheetten_magaza_store_status_oku(store_id, store_name)

    urunler = {}
    for kod, satir in durum_haritasi.items():
        if str(satir.get("renk") or "").strip().lower() != "green":
            continue
        urunler[kod] = {
            "urun_id": str(satir.get("urun_id", "")).strip(),
            "status": str(satir.get("status", "")).strip(),
            "etsy_draft_url": str(satir.get("etsy_draft_url", "")).strip(),
            "islem_tarihi": str(satir.get("islem_tarihi", "")).strip(),
            "renk": "green",
        }

    return {
        "store_name": store_name or store_id,
        "count": len(urunler),
        "urunler": urunler,
        "updated_at": _time.time(),
    }


def _sheetten_magaza_store_status_oku(store_id: str, store_name: str = "") -> dict[str, dict]:
    from shared.sheets import SheetsKatmani as _SK_STATUS

    sk = _SK_STATUS(store_id)
    satirlar = sk.tum_satirlar_al()
    renkler = {
        (_urun_kodu_normalize(k) or _urun_kodu_al(k)): str(v or "").strip().lower()
        for k, v in sk.urun_renk_durumlari_al().items()
        if (_urun_kodu_normalize(k) or _urun_kodu_al(k))
    }

    sonuc = {}
    for satir in satirlar:
        kod = _urun_kodu_normalize(satir.get("urun_id", "")) or _urun_kodu_al(satir.get("urun_id", ""))
        if not kod:
            continue

        renk = str(renkler.get(kod) or "").strip().lower()
        status = str(satir.get("status", "") or "").strip().lower()
        if not renk and status not in {"pending", "ready", "downloading", "downloaded", "uploading", "done", "error"}:
            continue

        if renk == "green":
            status = "done"
        elif renk == "red" and not status:
            status = "deleted"
        elif renk == "yellow" and not status:
            status = "error"

        sonuc[kod] = {
            "store_id": str(store_id or "").strip(),
            "store_name": str(store_name or store_id or "").strip(),
            "urun_id": str(satir.get("urun_id", "")).strip() or kod,
            "status": status,
            "renk": renk,
            "etsy_draft_url": str(satir.get("etsy_draft_url", "")).strip(),
            "islem_tarihi": str(satir.get("islem_tarihi", "")).strip(),
            "pcloud_klasor_id": str(satir.get("pcloud_klasor_id", "")).strip(),
        }

    return sonuc


@st.cache_data(ttl=90, show_spinner=False)
def _sheet_green_kodlari_cached(store_id: str) -> list[str]:
    """
    Urunler tabinda magazaya yuklu urunleri gorurken tek gercek kaynak olarak
    Sheet'teki green satirlari baz alir. Kisa sureli cache ile UI'yi bloklamamaya
    calisir, ama cache bayatlayinca yeniden Sheet okur.
    """
    durumlar = _sheetten_magaza_store_status_oku(store_id, "")
    yuklu_kodlar = []
    for raw_code, satir in durumlar.items():
        kod = _urun_kodu_normalize(raw_code) or _urun_kodu_al(raw_code)
        if not kod:
            continue
        renk = str((satir or {}).get("renk") or "").strip().lower()
        durum = str((satir or {}).get("status") or "").strip().lower()
        if renk == "green" or durum == "done":
            yuklu_kodlar.append(kod)
    return sorted(set(yuklu_kodlar))


@st.cache_data(ttl=90, show_spinner=False)
def _sheet_green_haritasi_cached(store_ids: tuple[str, ...]) -> dict[str, tuple[str, ...]]:
    sonuc: dict[str, set[str]] = {}
    for store_id in store_ids:
        sid = str(store_id or "").strip()
        if not sid:
            continue
        try:
            for kod in _sheet_green_kodlari_cached(sid):
                sonuc.setdefault(kod, set()).add(sid)
        except Exception:
            continue
    return {
        kod: tuple(sorted(magazalar))
        for kod, magazalar in sonuc.items()
    }


def _urunler_tab_canli_magaza_haritasi(store_ids: list[str]) -> dict[str, set[str]]:
    """
    Sheet'te yesil olan urunleri magaza bazinda urunler tabi icin haritalar.
    Boylesi envanter cache eksik/stale olsa bile urunler tabi dogru magazalari gosterir.
    """
    temiz_store_ids = tuple(
        sid for sid in (str(store_id or "").strip() for store_id in store_ids)
        if sid
    )
    if not temiz_store_ids:
        return {}
    return {
        kod: set(magazalar)
        for kod, magazalar in _sheet_green_haritasi_cached(temiz_store_ids).items()
    }


def _supabase_kuyruk_satirlari(store_id: str):
    from shared.product_catalog import StoreCatalog, _supabase_ready

    if not _supabase_ready():
        return None

    store_id = str(store_id or "").strip()
    if not store_id:
        return []

    try:
        _magaza_envanterini_topla(force=False, store_ids=[store_id])
    except Exception:
        pass

    store_rows = StoreCatalog().list_by_store(store_id)
    product_map = {
        str(item.get("product_code") or "").strip(): dict(item)
        for item in _urunleri_yukle(force_source_sync=False)
        if str(item.get("product_code") or "").strip()
    }

    sheet_map = {}
    sheet_renkleri = {}
    try:
        from shared.sheets import SheetsKatmani as _SK_QUEUE_META

        _sheet = _SK_QUEUE_META(store_id)
        for row in _sheet.tum_satirlar_al():
            kod = _urun_kodu_normalize(row.get("urun_id", "")) or _urun_kodu_al(row.get("urun_id", ""))
            if kod:
                sheet_map[kod] = row
        sheet_renkleri = {
            (_urun_kodu_normalize(k) or _urun_kodu_al(k)): str(v or "").strip().lower()
            for k, v in _sheet.urun_renk_durumlari_al().items()
            if (_urun_kodu_normalize(k) or _urun_kodu_al(k))
        }
    except Exception:
        sheet_map = {}
        sheet_renkleri = {}

    satirlar = []
    eklenen_kodlar = set()
    for row in store_rows:
        kod = _urun_kodu_normalize(row.get("product_code", "")) or _urun_kodu_al(row.get("product_code", ""))
        if not kod:
            continue
        product = product_map.get(str(row.get("product_code") or "").strip(), {})
        sheet_row = sheet_map.get(kod, {})
        renk = str(row.get("renk") or sheet_renkleri.get(kod) or "").strip().lower()
        satirlar.append({
            "urun_id": str(row.get("product_code") or sheet_row.get("urun_id") or "").strip(),
            "boyut_ft": str(sheet_row.get("boyut_ft") or product.get("size_ft") or "").strip(),
            "fiyat_usd": str(sheet_row.get("fiyat_usd") or "").strip(),
            "baslik": str(sheet_row.get("baslik") or product.get("note") or "").strip(),
            "durum": str(row.get("status") or sheet_row.get("status") or "").strip(),
            "status": str(row.get("status") or sheet_row.get("status") or "").strip(),
            "islem_tarihi": str(row.get("islem_tarihi") or sheet_row.get("islem_tarihi") or "").strip(),
            "etsy_draft_url": str(row.get("etsy_draft_url") or sheet_row.get("etsy_draft_url") or "").strip(),
            "pcloud_klasor_id": str(sheet_row.get("pcloud_klasor_id") or "").strip(),
            "renk": renk,
        })
        eklenen_kodlar.add(kod)

    # Gecmiste sadece Google Sheet'te kalmis yuklu/silinmis satirlari da gorunumde tut.
    for kod, sheet_row in sheet_map.items():
        if kod in eklenen_kodlar:
            continue
        renk = str(sheet_renkleri.get(kod) or "").strip().lower()
        status = str(sheet_row.get("status") or "").strip().lower()
        if renk not in {"green", "red", "yellow"} and status not in {"pending", "ready", "downloading", "downloaded", "uploading", "done", "error"}:
            continue
        product = product_map.get(str(sheet_row.get("urun_id") or "").strip(), {})
        satirlar.append({
            "urun_id": str(sheet_row.get("urun_id") or "").strip(),
            "boyut_ft": str(sheet_row.get("boyut_ft") or product.get("size_ft") or "").strip(),
            "fiyat_usd": str(sheet_row.get("fiyat_usd") or "").strip(),
            "baslik": str(sheet_row.get("baslik") or product.get("note") or "").strip(),
            "durum": status,
            "status": status,
            "islem_tarihi": str(sheet_row.get("islem_tarihi") or "").strip(),
            "etsy_draft_url": str(sheet_row.get("etsy_draft_url") or "").strip(),
            "pcloud_klasor_id": str(sheet_row.get("pcloud_klasor_id") or "").strip(),
            "renk": renk,
        })

    satirlar.sort(
        key=lambda item: (
            str(item.get("islem_tarihi") or ""),
            str(item.get("urun_id") or ""),
        ),
        reverse=True,
    )
    return satirlar


@st.cache_data(ttl=180, show_spinner=False)
def _olcu_ara_kaynaklari_cached(urunler_sig):
    from shared.product_catalog import derive_category_from_dimensions

    arama_kaynaklari = []
    atlanan_ft = 0
    toplam = 0
    satilan = 0
    for urun in [dict(item) for item in (urunler_sig or [])]:
        toplam += 1
        if str(urun.get("status", "")).strip().lower() == "sold":
            satilan += 1
            continue

        width_ft = _float_or_none(urun.get("width_ft"))
        length_ft = _float_or_none(urun.get("length_ft"))
        if width_ft is None or length_ft is None:
            atlanan_ft += 1
            continue

        category = str(urun.get("category") or "").strip() or derive_category_from_dimensions(
            width_cm=urun.get("width_cm"),
            length_cm=urun.get("length_cm"),
            width_ft=width_ft,
            length_ft=length_ft,
            area_m2=urun.get("area_m2"),
            source_tab=urun.get("source_tab", ""),
        )
        arama_kaynaklari.append({
            "kod": str(urun.get("product_code") or "").strip(),
            "cm": str(urun.get("size_cm") or "").strip(),
            "ft": str(urun.get("size_ft") or _fmt_size(width_ft, length_ft, digits=1)).strip(),
            "ft1": width_ft,
            "ft2": length_ft,
            "tur": _kategori_etiketi(category),
            "loaded_store_count": int(urun.get("loaded_store_count") or 0),
            "loaded_stores": str(urun.get("loaded_stores") or "").strip(),
            "note": str(urun.get("note") or "").strip(),
        })
    return {
        "arama_kaynaklari": arama_kaynaklari,
        "atlanan_ft": atlanan_ft,
        "toplam": toplam,
        "satilan": satilan,
    }


def _magaza_envanterini_topla(force: bool = False, store_ids: list[str] | None = None):
    dosya_cache = _envanter_cache_dosyadan_yukle()
    hedef_store_ids = [str(s or "").strip() for s in (store_ids or []) if str(s or "").strip()]

    if hedef_store_ids:
        if not force and all(not _magaza_cache_stale_mi(dosya_cache, sid) for sid in hedef_store_ids):
            return dosya_cache
    elif not force and not _envanter_cache_stale_mi(dosya_cache):
        return dosya_cache

    yeni_cache = {
        "updated_at": _time.time(),
        "stores": dict((dosya_cache or {}).get("stores") or {}),
        "errors": dict((dosya_cache or {}).get("errors") or {}),
    }
    try:
        from shared.store_manager import tum_magazalar as _tum_magazalar
        from shared.product_catalog import StoreCatalog, _supabase_ready
    except Exception as exc:
        yeni_cache["errors"]["global"] = str(exc)
        return dosya_cache if dosya_cache.get("stores") else yeni_cache

    tum_magazalar = {
        str(magaza.get("store_id") or "").strip(): magaza
        for magaza in _tum_magazalar()
        if str(magaza.get("store_id") or "").strip()
    }
    islenecek_store_ids = hedef_store_ids or list(tum_magazalar)

    for store_id in islenecek_store_ids:
        magaza = tum_magazalar.get(store_id)
        if not magaza:
            yeni_cache["errors"][store_id] = "Magaza bulunamadi."
            continue
        store_name = str(magaza.get("store_name") or store_id)
        store_id = str(magaza.get("store_id") or "").strip()
        try:
            yeni_cache["stores"][store_id] = _sheetten_magaza_envanteri_oku(store_id, store_name)
            yeni_cache["errors"].pop(store_id, None)
        except Exception as exc:
            yeni_cache["errors"][store_id] = str(exc)

    _json_kaydet(_STORE_INVENTORY_DB, yeni_cache)

    try:
        if _supabase_ready():
            store_catalog = StoreCatalog()
            for sid in islenecek_store_ids:
                smeta = tum_magazalar.get(sid) or {}
                tum_durumlar = _sheetten_magaza_store_status_oku(
                    sid,
                    str(smeta.get("store_name") or sid),
                )
                current_codes = {
                    str(code).strip()
                    for code in tum_durumlar.keys()
                    if str(code).strip()
                }
                existing_codes = {
                    str(row.get("product_code") or "").strip()
                    for row in store_catalog.list_by_store(sid)
                    if str(row.get("product_code") or "").strip()
                }
                silinecek = sorted(existing_codes - current_codes)
                if silinecek:
                    store_catalog.delete(sid, silinecek)

                rows = []
                for code, urun in tum_durumlar.items():
                    code = str(code).strip()
                    if not code:
                        continue
                    rows.append({
                        "product_code": code,
                        "store_id": sid,
                        "status": urun.get("status", ""),
                        "renk": urun.get("renk", ""),
                        "etsy_draft_url": urun.get("etsy_draft_url", ""),
                        "islem_tarihi": urun.get("islem_tarihi", ""),
                    })
                if rows:
                    store_catalog.upsert(rows)
    except Exception:
        pass

    if yeni_cache.get("stores"):
        return yeni_cache
    return dosya_cache if dosya_cache.get("stores") else yeni_cache


def _satilan_notlarini_uret(force_refresh: bool = False):
    stok_yolu = _stok_dosya_yolu()
    satilanlar = _satilan_kodlar(str(stok_yolu)) if stok_yolu.exists() else set()
    if not force_refresh:
        return _notlar_db_yukle(), _envanter_cache_yukle(), satilanlar

    envanter = _magaza_envanterini_topla(force=force_refresh)
    onceki = _notlar_db_yukle()
    onceki_notlar = onceki.get("notes", {}) if isinstance(onceki, dict) else {}
    yeni_notlar = {}

    for urun_kodu in sorted(satilanlar):
        magaza_kayitlari = []
        for store_id, store_data in (envanter.get("stores") or {}).items():
            urun = (store_data.get("urunler") or {}).get(urun_kodu)
            if not urun:
                continue
            magaza_kayitlari.append({
                "store_id": store_id,
                "store_name": store_data.get("store_name") or store_id,
                "urun_id": urun.get("urun_id") or urun_kodu,
                "status": urun.get("status") or "",
                "etsy_draft_url": urun.get("etsy_draft_url") or "",
                "islem_tarihi": urun.get("islem_tarihi") or "",
                "renk": "green",
            })

        if not magaza_kayitlari:
            continue

        magaza_kayitlari = sorted(magaza_kayitlari, key=lambda x: (x["store_name"], x["store_id"]))
        not_key = urun_kodu
        onceki_not = onceki_notlar.get(not_key, {})
        onceki_magazalar = sorted([m.get("store_id", "") for m in onceki_not.get("stores", [])])
        yeni_magazalar = sorted([m["store_id"] for m in magaza_kayitlari])
        status = onceki_not.get("status", "unread")
        if onceki_magazalar != yeni_magazalar:
            status = "unread"

        yeni_notlar[not_key] = {
            "note_key": not_key,
            "urun_kodu": urun_kodu,
            "stores": magaza_kayitlari,
            "status": status,
            "created_at": onceki_not.get("created_at") or _time.time(),
            "updated_at": _time.time(),
            "mesaj": (
                f"{urun_kodu} kodlu urun SATILANLAR listesinde. "
                f"SILINECEK MAGAZALAR: {', '.join((m['store_name'] or m['store_id']).upper() for m in magaza_kayitlari)}"
            ),
        }

    sonuc = {"updated_at": _time.time(), "notes": yeni_notlar}
    _json_kaydet(_SOLD_NOTES_DB, sonuc)
    return sonuc, envanter, satilanlar


def _not_status_guncelle(note_key: str, yeni_status: str):
    db = _notlar_db_yukle()
    note = (db.get("notes") or {}).get(note_key)
    if not note:
        return
    note["status"] = yeni_status
    note["updated_at"] = _time.time()
    _json_kaydet(_SOLD_NOTES_DB, db)


def _notlari_silindi_isaretle(note_keyler: list[str]) -> tuple[int, list[str]]:
    db = _notlar_db_yukle()
    note_map = db.get("notes") or {}
    magaza_urunleri = {}

    for note_key in note_keyler:
        note = note_map.get(note_key) or {}
        for store in note.get("stores", []):
            store_id = str(store.get("store_id") or "").strip()
            urun_id = str(store.get("urun_id") or "").strip()
            if store_id and urun_id:
                magaza_urunleri.setdefault(store_id, set()).add(urun_id)

    if not magaza_urunleri:
        return 0, []

    hatalar = []
    toplam = 0

    try:
        from shared.sheets import SheetsKatmani as _SK_NOTE_UPDATE
    except Exception as exc:
        return 0, [str(exc)]

    for store_id, urun_idleri in magaza_urunleri.items():
        try:
            sonuc = _SK_NOTE_UPDATE(store_id).urunleri_renklendir(sorted(urun_idleri), "red")
            toplam += int(sonuc.get("guncellenen") or 0)
        except Exception as exc:
            hatalar.append(f"{store_id}: {exc}")

    if not hatalar:
        for note_key in note_keyler:
            _not_status_guncelle(note_key, "deleted")

    _global_kirmizi_kodlari_yenile()
    if st.session_state.get("hedef_magaza_id"):
        try:
            _magaza_renk_cache_yenile(st.session_state.hedef_magaza_id)
        except Exception:
            pass

    return toplam, hatalar


def _okunmamis_not_sayisi_hesapla(force_refresh: bool = False):
    notlar_db, _, _ = _satilan_notlarini_uret(force_refresh=force_refresh)
    return sum(1 for note in (notlar_db.get("notes") or {}).values() if note.get("status") != "read")


def _okunmamis_not_sayisi_cacheden_al() -> int:
    db = _notlar_db_yukle()
    return sum(1 for note in (db.get("notes") or {}).values() if note.get("status") != "read")


def _aktif_islem_panelini_sifirla():
    st.session_state.aktif_islem_urunleri = []
    st.session_state.aktif_islem_durumlari = {}
    st.session_state.aktif_islem_ozeti = {}


def _aktif_islem_kaydi_yaz(item: dict, durum: str, mesaj: str = ""):
    item_id = str(item.get("id") or "")
    if not item_id:
        return
    kayit = {
        "id": item_id,
        "ad": str(item.get("ad") or "").strip(),
        "durum": durum,
        "mesaj": str(mesaj or "").strip(),
    }
    mevcutlar = list(st.session_state.get("aktif_islem_urunleri") or [])
    guncellendi = False
    for idx, mevcut in enumerate(mevcutlar):
        if str(mevcut.get("id") or "") == item_id:
            mevcutlar[idx] = kayit
            guncellendi = True
            break
    if not guncellendi:
        mevcutlar.append(kayit)
    st.session_state.aktif_islem_urunleri = mevcutlar
    durumlar = dict(st.session_state.get("aktif_islem_durumlari") or {})
    durumlar[item_id] = kayit
    st.session_state.aktif_islem_durumlari = durumlar


def _son_islem_raporu_goster():
    rapor = st.session_state.get("son_islem_raporu") or []
    if not rapor:
        return

    st.markdown(
        "<div class='section-label' style='margin-top:12px;'>Son işlem sonuçları</div>",
        unsafe_allow_html=True
    )
    with st.container(border=True):
        for item in rapor:
            ikon = "✅" if item.get("durum") == "ok" else "❌"
            baslik = item.get("urun_ad") or "Ürün"
            mesaj = item.get("mesaj") or ""
            st.markdown(f"**{ikon} {baslik}**")
            if mesaj:
                st.caption(mesaj)
        if st.button("Son işlem sonuçlarını temizle", key="clear_last_run_results"):
            st.session_state.son_islem_raporu = []
            st.rerun()


def _kod_normalize(kod: str) -> str:
    return _re.sub(r'[\+\!\*\s]+$', '', str(kod).strip()).strip()

@st.cache_data(ttl=1800, show_spinner=False)
def _satilan_kodlar_cached(dosya_yolu: str, mtime: float) -> set[str]:
    # Excel'i her rerun'da yeniden parse etmeyelim; mtime degisince cache otomatik yenilenir.
    _ = mtime
    try:
        import pandas as pd
        df = pd.read_excel(dosya_yolu, sheet_name='SATILANLAR')
        kodlar = df.iloc[:, 0].dropna().astype(str).str.strip()
        sonuc = set()
        for k in kodlar:
            if not k or k == 'nan':
                continue
            norm = _urun_kodu_normalize(k)
            if norm:
                sonuc.add(norm)
        return sonuc
    except Exception:
        return set()

def _satilan_kodlar(dosya_yolu: str) -> set:
    try:
        mtime = Path(dosya_yolu).stat().st_mtime
        return _satilan_kodlar_cached(dosya_yolu, mtime)
    except Exception:
        return set()


_satilan_kod_cache_yenile()

# ── pCloud API ────────────────────────────────────────────────────────────────
def pcloud_giris(email, sifre, kod=""):
    son_hata = "Bağlantı hatası"
    for host in ["https://api.pcloud.com", "https://eapi.pcloud.com"]:
        try:
            params = {"getauth": 1, "logout": 1, "username": email, "password": sifre}
            if kod: params["code"] = kod
            r = httpx.get(f"{host}/userinfo", params=params, timeout=15)
            d = r.json()
            if d.get("result") == 0:
                st.session_state["pcloud_host"] = host
                return True, d.get("auth", "")
            son_hata = d.get("error", "Hata")
        except Exception as e:
            son_hata = str(e)
    return False, son_hata

@st.cache_data(ttl=3600, show_spinner=False)
def _klasorleri_getir(token, host, klasor_id):
    for h in [host, "https://eapi.pcloud.com", "https://api.pcloud.com"]:
        try:
            r = httpx.get(f"{h}/listfolder",
                          params={"auth": token, "folderid": klasor_id, "nofiles": 1},
                          timeout=15)
            d = r.json()
            if d.get("result") == 0:
                return h, [{"id": i["folderid"], "ad": i["name"]}
                            for i in d["metadata"].get("contents", []) if i.get("isfolder")]
        except: continue
    return host, []

@st.cache_data(ttl=3600, show_spinner=False)
def _klasor_icerigi_getir(token, host, klasor_id):
    for h in [host, "https://eapi.pcloud.com", "https://api.pcloud.com"]:
        try:
            r = httpx.get(
                f"{h}/listfolder",
                params={"auth": token, "folderid": klasor_id},
                timeout=15,
            )
            d = r.json()
            if d.get("result") != 0:
                continue

            contents = d.get("metadata", {}).get("contents", []) or []
            klasorler = []
            dosyalar = []

            for item in contents:
                if item.get("isfolder"):
                    klasorler.append(
                        {
                            "id": item["folderid"],
                            "ad": item["name"],
                            "is_product_folder": False,
                        }
                    )
                else:
                    dosyalar.append(item)

            return h, klasorler, dosyalar
        except Exception:
            continue
    return host, [], []


@st.cache_data(ttl=3600, show_spinner=False)
def _klasor_meta_getir(token, host, klasor_id):
    for h in [host, "https://eapi.pcloud.com", "https://api.pcloud.com"]:
        try:
            r = httpx.get(
                f"{h}/listfolder",
                params={"auth": token, "folderid": klasor_id},
                timeout=15,
            )
            d = r.json()
            if d.get("result") != 0:
                continue

            contents = d.get("metadata", {}).get("contents", []) or []
            has_subfolders = any(item.get("isfolder") for item in contents)
            has_files = any(not item.get("isfolder") for item in contents)
            return h, {
                "is_product_folder": has_files and not has_subfolders,
                "has_subfolders": has_subfolders,
                "has_files": has_files,
            }
        except Exception:
            continue
    return host, {
        "is_product_folder": False,
        "has_subfolders": False,
        "has_files": False,
    }

@st.cache_data(ttl=1800, show_spinner=False)
def _magazalari_otomatik_bul(token, host):
    def _alt(h, folderid):
        for _h in [h, "https://eapi.pcloud.com", "https://api.pcloud.com"]:
            try:
                r = httpx.get(f"{_h}/listfolder",
                              params={"auth": token, "folderid": folderid, "nofiles": 1},
                              timeout=15)
                d = r.json()
                if d.get("result") == 0:
                    return [{"id": i["folderid"], "ad": i["name"]}
                            for i in d["metadata"].get("contents", []) if i.get("isfolder")]
            except: continue
        return []

    def _bul(liste, *anahtarlar):
        for k in liste:
            ad = k["ad"].upper().replace("İ", "I").replace("Ş", "S").replace("Ğ", "G")
            for anahtar in anahtarlar:
                if anahtar.upper() in ad:
                    return k
        return None

    l1 = _alt(host, 0)
    anatolian = _bul(l1, "ANATOLIAN")
    if not anatolian: return None, []
    l2 = _alt(host, anatolian["id"])
    arsiv = _bul(l2, "ARSIV")
    if not arsiv: return None, []
    l3 = _alt(host, arsiv["id"])
    vintage = _bul(l3, "VINTAGE RUG")
    if not vintage: return None, []
    magazalar = _alt(host, vintage["id"])
    return vintage["id"], magazalar

@st.cache_data(ttl=600, show_spinner=False)
def _magaza_tum_kodlar(token, host, magaza_id):
    def _traverse(contents, result):
        for item in contents:
            if item.get("isfolder"):
                result.add(_kod_normalize(item["name"]))
                _traverse(item.get("contents") or [], result)
        return result
    for h in [host, "https://eapi.pcloud.com", "https://api.pcloud.com"]:
        try:
            r = httpx.get(f"{h}/listfolder",
                          params={"auth": token, "folderid": magaza_id,
                                  "nofiles": 1, "recursive": 1},
                          timeout=60)
            d = r.json()
            if d.get("result") == 0:
                return _traverse(d["metadata"].get("contents", []), set())
        except: continue
    return set()


def _resimleri_getir(token, host, klasor_id, dosyalar=None):
    # pCloud getfilelink gecici URL uretir; bunlari cache'lemek bir sure sonra
    # kirik gorsellere neden olur. Onizleme her acildiginda taze link aliyoruz.
    try:
        if dosyalar is None:
            r = httpx.get(f"{host}/listfolder",
                          params={"auth": token, "folderid": klasor_id},
                          timeout=15)
            d = r.json()
            if d.get("result") != 0:
                return [], d.get("error", "Hata")
            dosyalar = d["metadata"].get("contents", [])

        dosyalar = [f for f in dosyalar
                    if not f.get("isfolder")
                    and f.get("parentfolderid") == klasor_id
                    and f.get("name", "").lower().endswith((".jpg", ".jpeg", ".png", ".webp"))]

        def _link_al(dosya):
            try:
                lr = httpx.get(f"{host}/getfilelink",
                               params={"auth": token, "fileid": dosya["fileid"]},
                               timeout=10)
                ld = lr.json()
                if ld.get("result") == 0:
                    return {"url": f"https://{ld['hosts'][0]}{ld['path']}", "ad": dosya["name"]}
            except Exception:
                pass
            return None

        import concurrent.futures as _cf
        urls = []
        with _cf.ThreadPoolExecutor(max_workers=6) as _pool:
            for sonuc in _pool.map(_link_al, dosyalar):
                if sonuc:
                    urls.append(sonuc)
        return urls, None
    except Exception as e:
        return [], str(e)

# ── Kuyruk badge helper ───────────────────────────────────────────────────────
_KUYRUK_BADGE = {
    "pending":     ("badge-pending",  "bekliyor"),
    "ready":       ("badge-ready",    "hazır"),
    "downloading": ("badge-other",    "indiriliyor"),
    "downloaded":  ("badge-other",    "indirildi"),
    "uploading":   ("badge-other",    "yükleniyor"),
    "done":        ("badge-done",     "yüklendi"),
    "error":       ("badge-error",    "hata"),
}

def _kuyruk_badge(status: str) -> str:
    cls, lbl = _KUYRUK_BADGE.get(status, ("badge-other", status))
    return f'<span class="folder-badge {cls}">{lbl}</span>'


def _main_tab_sec(tab_id: str):
    st.session_state.active_main_tab = tab_id


def _tab_loading_gostergesi(title: str, percent: int, detail: str, ready: bool = False):
    if ready:
        return
    durum = "Hazır" if ready else f"%{max(0, min(100, int(percent)))}"
    renk = "#22c55e" if ready else "#f59e0b"
    oran = max(0, min(100, int(percent)))
    st.markdown(
        f"""
        <div style="display:flex;justify-content:flex-end;margin:0 0 10px;">
          <div style="min-width:250px;max-width:320px;background:#111827;border:1px solid #374151;
                      border-radius:12px;padding:10px 12px;box-shadow:0 6px 18px rgba(0,0,0,0.22);">
            <div style="display:flex;align-items:center;justify-content:space-between;gap:12px;">
              <div style="font-size:0.82rem;font-weight:700;color:#e5e7eb;">{title}</div>
              <div style="font-size:0.78rem;font-weight:700;color:{renk};">{durum}</div>
            </div>
            <div style="margin-top:8px;height:6px;border-radius:999px;background:#1f2937;overflow:hidden;">
              <div style="width:{oran}%;height:100%;background:{renk};transition:width .18s ease;"></div>
            </div>
            <div style="margin-top:7px;font-size:0.74rem;color:#9ca3af;line-height:1.3;">{detail}</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ── Image preview dialog ──────────────────────────────────────────────────────
@st.dialog("🖼️ Resim Önizleme", width="large")
def _onizleme_dialog(token, host, klasor):
    st.markdown(
        f"<div style='font-size:0.85rem;color:#8b949e;margin-bottom:12px;'>"
        f"📁 <strong style='color:#e6edf3;'>{klasor['ad']}</strong></div>",
        unsafe_allow_html=True
    )
    with st.spinner("Resimler yükleniyor..."):
        urls, hata = _resimleri_getir(token, host, klasor["id"])
    if hata:
        st.error(f"Hata: {hata}")
    elif not urls:
        st.info("Bu klasörde resim yok.")
    else:
        st.caption(f"{len(urls)} resim")
        # 4 kolonlu thumbnail grid
        cols_per_row = 4
        for row_start in range(0, len(urls), cols_per_row):
            row_urls = urls[row_start:row_start + cols_per_row]
            img_cols = st.columns(len(row_urls))
            for col, resim in zip(img_cols, row_urls):
                col.image(resim["url"], caption=resim["ad"], width="stretch")

# ── TABLAR ────────────────────────────────────────────────────────────────────
_okunmamis_not_sayisi = _okunmamis_not_sayisi_cacheden_al()
_notlar_etiketi = f"📝  Notlar ({_okunmamis_not_sayisi})" if _okunmamis_not_sayisi else "📝  Notlar"

_main_tabs = [
    ("urun_sec", "📦  Ürün Seç"),
    ("urunler", "🗂️  Ürünler"),
    ("olcu_ara", "🔍  Ölçü Ara"),
    ("kuyruk", "📋  Kuyruk"),
    ("ayarlar", "⚙️  Ayarlar"),
    ("notlar", _notlar_etiketi),
]
_tab_cols = st.columns(len(_main_tabs))
for _col, (_tab_id, _tab_label) in zip(_tab_cols, _main_tabs):
    _is_active = st.session_state.active_main_tab == _tab_id
    _col.button(
        _tab_label,
        key=f"main_tab_btn_{_tab_id}",
        width="stretch",
        type="primary" if _is_active else "secondary",
        on_click=_main_tab_sec,
        args=(_tab_id,),
    )

# ══ TAB 1 ════════════════════════════════════════════════════════════════════
if st.session_state.active_main_tab == "urun_sec":
    if not st.session_state.pcloud_token:
        with st.container(key="main_tab_content_urun_sec"):
            _tab_loading_gostergesi("Ürün Seç", 100, "pCloud bağlantısı bekleniyor. Giriş ekranı hazır.", ready=True)
            # ── Login formu ──
            st.markdown("<div style='max-width:480px;margin:40px auto;'>", unsafe_allow_html=True)
            st.markdown("### pCloud Bağlantısı")
            giris_yontemi = st.radio("Giriş yöntemi", ["Token yapıştır", "E-posta / Şifre"], horizontal=True)
            if giris_yontemi == "Token yapıştır":
                token_input = st.text_input("pCloud Auth Token", placeholder="Tarayıcı konsolundan kopyalayın")
                st.caption("Chrome: F12 → Console → `document.cookie.match(/pcauth=([^;]+)/)[1]`")
                if st.button("🔗 Token ile Bağlan", type="primary", width="stretch"):
                    if token_input:
                        st.session_state.pcloud_token = token_input
                        st.session_state["pcloud_host"] = "https://api.pcloud.com"
                        _token_kaydet(token_input)
                        try:
                            from shared.sheets import config_yaz
                            config_yaz("PCLOUD_TOKEN", token_input)
                        except Exception: pass
                        st.rerun()
                    else:
                        st.warning("Token girin.")
            else:
                col1, col2 = st.columns(2)
                email = col1.text_input("E-posta")
                sifre = col2.text_input("Şifre", type="password")
                kod = st.text_input("2FA Kodu (varsa)")
                if st.button("🔗 Bağlan", type="primary", width="stretch"):
                    if email and sifre:
                        with st.spinner("Bağlanıyor..."):
                            ok, sonuc = pcloud_giris(email, sifre, kod)
                        if ok:
                            st.session_state.pcloud_token = sonuc
                            _token_kaydet(sonuc)
                            try:
                                from shared.sheets import config_yaz
                                config_yaz("PCLOUD_TOKEN", sonuc)
                            except Exception: pass
                            st.rerun()
                        else:
                            st.error(f"❌ {sonuc}")
                    else:
                        st.warning("E-posta ve şifre girin.")
            st.markdown("</div>", unsafe_allow_html=True)
    else:
        def _tab1_gezgin():
            token = st.session_state.pcloud_token

            def _kaynak_magaza_sec(_magaza_id, _magaza_ad):
                st.session_state.magaza_id = _magaza_id
                st.session_state.magaza_ad = _magaza_ad
                st.session_state.klasor_id = _magaza_id
                st.session_state.klasor_ad = _magaza_ad
                st.session_state.klasor_gecmisi = []

            def _magaza_secimine_don():
                st.session_state.magaza_id = None
                st.session_state.magaza_ad = None
                st.session_state.klasor_id = 0
                st.session_state.klasor_ad = None
                st.session_state.klasor_gecmisi = []

            def _klasorde_geri_git():
                _gecmis = list(st.session_state.klasor_gecmisi)
                if not _gecmis:
                    return
                _onceki = _gecmis.pop()
                st.session_state.klasor_gecmisi = _gecmis
                st.session_state.klasor_id = _onceki["id"]
                st.session_state.klasor_ad = _onceki.get("ad") or st.session_state.magaza_ad

            def _klasoru_ac(_folder_id, _folder_ad):
                _mevcut_klasor_ad = st.session_state.get("klasor_ad") or st.session_state.magaza_ad or ""
                st.session_state.klasor_gecmisi = [
                    *st.session_state.klasor_gecmisi,
                    {"id": st.session_state.klasor_id, "ad": _mevcut_klasor_ad},
                ]
                st.session_state.klasor_id = _folder_id
                st.session_state.klasor_ad = _folder_ad
                st.rerun(scope="app")

            def _klasorleri_yenile():
                _klasorleri_getir.clear()
                _klasor_icerigi_getir.clear()
                _klasor_meta_getir.clear()
                st.session_state.kuyruk_yuklendi = False
                st.session_state.kuyruk_klasor_durumlari = {}
                st.session_state.sheet_renk_durumlari = {}
                st.session_state.klasor_id_durumlari = {}

            def _ai_kuyruga_ekle():
                bloklu_secimler = [
                    k for k in st.session_state.secilen
                    if _secili_item_bloklu_mu(k)
                ]
                if bloklu_secimler:
                    st.session_state.secilen = [
                        k for k in st.session_state.secilen
                        if not _secili_item_bloklu_mu(k)
                    ]
                    st.error("SATILANLAR veya silindi olarak işaretli ürünler AI kuyruğuna gönderilemez.")
                    st.rerun()

                host  = st.session_state.get("pcloud_host", "https://api.pcloud.com")
                token = st.session_state.pcloud_token
                from shared.sheets import SheetsKatmani
                from modules.ai_icerik import ai_icerik_url
                from modules.parser import parse_urun_bilgisi
                import json as _json

                try:
                    from shared.store_manager import get_store as _gs2
                    _tmpl_id = _gs2(st.session_state.hedef_magaza_id).get("template", "default_v1")
                    _tmpl_path = _template_yolu(_tmpl_id)
                    _template_cfg = _json.loads(_tmpl_path.read_text(encoding="utf-8")) if _tmpl_path.exists() else {}
                except Exception:
                    _template_cfg = {}

                try:
                    from shared.store_manager import get_store as _gs
                    price_per_m2 = int(_gs(st.session_state.hedef_magaza_id).get("price_per_m2", 300))
                except Exception:
                    price_per_m2 = 300

                ana_yol = ""
                _sk = SheetsKatmani(st.session_state.hedef_magaza_id)
                _sk.sheet_hazirla()
                prog = st.progress(0)
                hatalar = []
                islem_raporu = []
                toplam  = len(st.session_state.secilen)
                log     = st.container(border=True)
                st.session_state.aktif_islem_urunleri = []
                st.session_state.aktif_islem_durumlari = {}
                st.session_state.aktif_islem_ozeti = {
                    "durum": "running",
                    "toplam": toplam,
                    "basarili": 0,
                    "hatali": 0,
                }
                for _secili in st.session_state.secilen:
                    _aktif_islem_kaydi_yaz(_secili, "bekliyor", "Sırada bekliyor")

                for i, k in enumerate(st.session_state.secilen):
                    prog.progress((i + 1) / toplam, text=f"{i+1}/{toplam} — {k['ad']}")
                    with log:
                        with st.status(f"📦 {k['ad']}  ({i+1}/{toplam})", expanded=True) as durum:
                            try:
                                _aktif_islem_kaydi_yaz(k, "isleniyor", "İşleniyor...")
                                st.write("📂 pCloud'dan dosyalar alınıyor...")
                                r = httpx.get(f"{host}/listfolder",
                                              params={"auth": token, "folderid": k["id"]},
                                              timeout=15)
                                d = r.json()
                                dosyalar     = [f for f in d["metadata"].get("contents", []) if not f.get("isfolder")]
                                dosya_adlari = [f["name"] for f in dosyalar]
                                secili_urun_kodu = _guvenli_urun_kodu_bul(k["ad"], dosya_adlari)
                                st.write(f"✅ {len(dosyalar)} dosya bulundu")

                                st.write("📐 Boyut ve fiyat hesaplanıyor...")
                                urun_bilgisi = parse_urun_bilgisi(k["ad"], dosya_adlari)
                                # Queue sheet'te A kolonu her zaman panelde secilen urun kodunu tutsun.
                                urun_bilgisi["urun_id"] = secili_urun_kodu
                                if urun_bilgisi.get("metrekare"):
                                    urun_bilgisi["fiyat_usd"] = round(float(urun_bilgisi["metrekare"]) * price_per_m2)
                                boyut = urun_bilgisi.get("boyut_ft") or "?"
                                fiyat = urun_bilgisi.get("fiyat_usd") or "?"
                                if boyut == "?" or fiyat == "?":
                                    st.warning(f"⚠ Boyut/fiyat okunamadı. Bilgi dosyası: {urun_bilgisi.get('bilgi_dosyasi') or 'BULUNAMADI'}")
                                    st.caption(f"Klasördeki dosyalar: {dosya_adlari}")
                                else:
                                    st.write(f"✅ {boyut} ft — ${fiyat}")

                                st.write("🖼️ Ana fotoğraf hazırlanıyor...")
                                bilgi_adi = urun_bilgisi.get("bilgi_dosyasi") or ""
                                foto_dosyalar = [f for f in dosyalar
                                                 if f["name"].lower().endswith((".jpg", ".jpeg", ".png"))
                                                 and f["name"] != bilgi_adi]
                                if not foto_dosyalar:
                                    _urun_kodu = _kod_normalize(k["ad"])
                                    _stok_yolu = _stok_dosya_yolu()
                                    _satilan = _satilan_kodlar(str(_stok_yolu)) if _stok_yolu.exists() else set()
                                    if _urun_kodu in _satilan:
                                        raise Exception(f"⛔ Bu ürün SATILMIŞ ve klasörde resim yok. (KOD: {k['ad']})")
                                    else:
                                        raise Exception(f"⚠️ Klasörde resim bulunamadı! (KOD: {k['ad']})")
                                lr = httpx.get(f"{host}/getfilelink",
                                               params={"auth": token, "fileid": foto_dosyalar[0]["fileid"]},
                                               timeout=10)
                                ld = lr.json()
                                resim_url = f"https://{ld['hosts'][0]}{ld['path']}"
                                st.write(f"✅ Fotoğraf: {foto_dosyalar[0]['name']}")

                                _stok_yolu = _stok_dosya_yolu()
                                if _stok_yolu.exists():
                                    _satilan   = _satilan_kodlar(str(_stok_yolu))
                                    _urun_kodu = _kod_normalize(k["ad"])
                                    if _urun_kodu in _satilan:
                                        raise Exception(f"⛔ Bu ürün SATILMIŞ! (KOD: {k['ad']})")

                                st.write("🤖 Gemini analiz ediyor...")
                                ai = ai_icerik_url(
                                    resim_url=resim_url,
                                    urun_id=secili_urun_kodu,
                                    boyut_ft=urun_bilgisi.get("boyut_ft") or "?",
                                    boyut_cm=urun_bilgisi.get("boyut_cm") or "?",
                                    metrekare=urun_bilgisi.get("metrekare") or 0,
                                    fiyat_usd=urun_bilgisi.get("fiyat_usd") or 0,
                                    genislik_cm=urun_bilgisi.get("genislik_cm"),
                                    uzunluk_cm=urun_bilgisi.get("uzunluk_cm"),
                                    template_config=_template_cfg,
                                )
                                if not ai["basarili"]:
                                    raise Exception(f"AI zorunlu alanlari gecemedi: {ai['hata']}")
                                st.write(f"✅ Başlık: {ai['baslik'][:60]}...")

                                st.write(f"📋 Sheets'e ekleniyor → {st.session_state.hedef_magaza_id}...")
                                pcloud_yol = f"{ana_yol}/{k['ad']}" if ana_yol else k["ad"]
                                satir_no = _sk.urun_ekle(urun_bilgisi, pcloud_yol, pcloud_klasor_id=k["id"])
                                st.write(f"💾 AI verileri yazılıyor (satır {satir_no})...")
                                _sk.ai_verileri_yaz(urun_bilgisi["urun_id"], ai, satir_no=satir_no)
                                st.session_state.kuyruga_eklenenler[secili_urun_kodu] = "ready"
                                st.session_state.kuyruk_klasor_durumlari[str(k["id"])] = "ready"
                                st.write(f"✅ Renk: {ai.get('renk1','')} / {ai.get('renk2','')} — Stil: {ai.get('stil','')}")
                                islem_raporu.append({
                                    "urun_ad": k["ad"],
                                    "durum": "ok",
                                    "mesaj": f"Tamamlandı • {boyut} ft • ${fiyat}",
                                })
                                _aktif_islem_kaydi_yaz(k, "ok", f"Tamamlandı • {boyut} ft • ${fiyat}")
                                durum.update(label=f"✅ {k['ad']} tamamlandı", state="complete", expanded=False)

                            except Exception as e:
                                hatalar.append(f"{k['ad']}: {e}")
                                islem_raporu.append({
                                    "urun_ad": k["ad"],
                                    "durum": "error",
                                    "mesaj": str(e),
                                })
                                _aktif_islem_kaydi_yaz(k, "error", str(e))
                                st.write(f"❌ Hata: {e}")
                                durum.update(label=f"❌ {k['ad']} — hata", state="error", expanded=False)

                prog.empty()
                basarili = toplam - len(hatalar)
                st.session_state.aktif_islem_ozeti = {
                    "durum": "done",
                    "toplam": toplam,
                    "basarili": basarili,
                    "hatali": len(hatalar),
                }
                st.session_state.son_islem_raporu = islem_raporu
                if basarili:
                    st.success(f"✅ {basarili}/{toplam} ürün tamamlandı!")
                st.session_state["_reset_checkbox_ids"] = [
                    str(_item["id"]) for _item in st.session_state.secilen
                ]
                st.session_state.secilen = []
                st.session_state["_secim_limit_hatasi"] = None
                st.rerun(scope="app")

            def _secim_aksiyon_paneli(button_key: str, ustte: bool = False):
                try:
                    from shared.store_manager import get_store as _gs
                    price_per_m2 = int(_gs(st.session_state.hedef_magaza_id).get("price_per_m2", 300))
                except Exception:
                    price_per_m2 = 300

                if ustte:
                    st.markdown(
                        f"<div style='margin:8px 0 12px;padding:10px 14px;background:#111827;"
                        f"border:1px solid #374151;border-radius:10px;'>"
                        f"<div style='font-size:0.82rem;color:#93c5fd;'>Seçilen ürünler hazır</div>"
                        f"<div style='margin-top:2px;font-size:0.95rem;color:#e5e7eb;'>"
                        f"{len(st.session_state.secilen)}/15 ürün seçildi"
                        f"&nbsp;&nbsp;·&nbsp;&nbsp;🏪 {st.session_state.hedef_magaza_id}"
                        f"&nbsp;&nbsp;·&nbsp;&nbsp;${price_per_m2}/m²"
                        f"</div></div>",
                        unsafe_allow_html=True,
                    )
                else:
                    st.markdown(
                        f"<div style='margin:10px 0 6px;padding:10px 14px;"
                        f"background:#78350f;border:1px solid #f59e0b;border-radius:8px;"
                        f"font-size:0.85rem;color:#fde68a;'>"
                        f"🏪 <strong>{st.session_state.hedef_magaza_id}</strong> mağazasına yüklenecek"
                        f"&nbsp;&nbsp;·&nbsp;&nbsp;${price_per_m2}/m²"
                        f"</div>",
                        unsafe_allow_html=True
                    )

                if st.button(
                    f"🤖  AI ile Kuyruğa Ekle  ({len(st.session_state.secilen)} ürün)",
                    key=button_key,
                    type="primary",
                    width="stretch",
                ):
                    _ai_kuyruga_ekle()

            def _secim_toggle(item, chk_key: str):
                secimler = [
                    s for s in st.session_state.secilen
                    if str(s.get("id")) != str(item["id"])
                ]

                if st.session_state.get(chk_key):
                    _item = dict(item)
                    if not _item.get("is_product_folder"):
                        _meta_host, _meta = _klasor_meta_getir(
                            st.session_state.pcloud_token,
                            st.session_state.get("pcloud_host", "https://api.pcloud.com"),
                            _item["id"],
                        )
                        st.session_state["pcloud_host"] = _meta_host
                        if not _meta.get("is_product_folder"):
                            st.session_state[chk_key] = False
                            st.session_state["_secim_limit_hatasi"] = "Sadece resim içeren ürün klasörleri seçilebilir. Ara klasörleri açarak devam edin."
                            st.session_state.secilen = secimler
                            return
                        _item["is_product_folder"] = True

                    if _secili_item_bloklu_mu(_item):
                        st.session_state[chk_key] = False
                        return
                    if len(secimler) >= 15:
                        st.session_state[chk_key] = False
                        st.session_state["_secim_limit_hatasi"] = "En fazla 15 ürün seçebilirsiniz. Lütfen bazı seçimleri kaldırın."
                        st.session_state.secilen = secimler
                        return
                    secimler.append(_item)

                st.session_state["_secim_limit_hatasi"] = None
                st.session_state.secilen = secimler

            # ── KAYNAK MAĞAZA SEÇİMİ ──────────────────────────────────────────
            if not st.session_state.magaza_id:
                _host_m = st.session_state.get("pcloud_host", "https://api.pcloud.com")
                st.markdown("<div class='section-label'>pCloud Kaynak Klasörü</div>", unsafe_allow_html=True)
                st.caption(f"Hedef: **{st.session_state.hedef_magaza_id}** — Ürünlerin bulunduğu pCloud mağaza klasörünü seçin.")
                with st.spinner("Mağazalar yükleniyor..."):
                    _, magazalar = _magazalari_otomatik_bul(token, _host_m)
                if not magazalar:
                    st.warning("Klasörler otomatik bulunamadı.")
                else:
                    cols_m = st.columns(4)
                    for i, m in enumerate(magazalar):
                        cols_m[i % 4].button(
                            f"📂  {m['ad']}",
                            key=f"mag1_{m['id']}",
                            width="stretch",
                            on_click=_kaynak_magaza_sec,
                            args=(m["id"], m["ad"]),
                        )

            else:
                _queue_badges_ready = (
                    bool(st.session_state.get("kuyruk_yuklendi"))
                    and st.session_state.get("kuyruk_magaza_id") == st.session_state.hedef_magaza_id
                )
                # ── KLASÖR GEZGİNİ ────────────────────────────────────────────
                gecmis = st.session_state.klasor_gecmisi

                # ── Nav bar ──────────────────────────────────────────────────
                _magaza_adi = st.session_state.magaza_ad or ""
                _nav_c_back, _nav_c_crumbs, _nav_c_pin, _nav_c_ref = st.columns([1, 8, 0.7, 0.7])

                if len(gecmis) == 0:
                    _nav_c_back.button(
                        "◀ Mağaza",
                        key="nav_magaza",
                        on_click=_magaza_secimine_don,
                    )
                else:
                    _nav_c_back.button(
                        "◀ Geri",
                        key="nav_geri",
                        on_click=_klasorde_geri_git,
                    )

                # Breadcrumb — metin olarak göster; link kullanma yoksa tarayici yeni sekme aciyor.
                _aktif_klasor_adi = st.session_state.get("klasor_ad") or _magaza_adi
                _crumb_items = [_magaza_adi] + [g["ad"] for g in gecmis if str(g.get("ad") or "").strip()]
                if _aktif_klasor_adi and (_crumb_items[-1] if _crumb_items else None) != _aktif_klasor_adi:
                    _crumb_items.append(_aktif_klasor_adi)
                _bc_parts = []
                for _ci, _label in enumerate(_crumb_items):
                    _short = (_label[:18] + "…") if len(_label) > 19 else _label
                    if _ci == len(_crumb_items) - 1:
                        _bc_parts.append(f"<span style='color:#e6edf3;font-weight:600;'>{_short}</span>")
                    else:
                        _bc_parts.append(f"<span style='color:#8b949e;'>{_short}</span>")
                _bc_html = " <span style='color:#30363d;margin:0 2px;'>›</span> ".join(_bc_parts)
                _nav_c_crumbs.markdown(
                    f"<div style='padding:6px 4px;font-size:0.82rem;line-height:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;'>{_bc_html}</div>",
                    unsafe_allow_html=True
                )

                _root_ayarli = (st.session_state.magazalar_root_id == st.session_state.klasor_id
                                and st.session_state.klasor_id != 0)
                if _nav_c_pin.button("📌" + (" ✓" if _root_ayarli else ""),
                                     help="Tab 4 için mağaza kökü olarak ayarla"):
                    st.session_state.magazalar_root_id = st.session_state.klasor_id
                    st.toast(f"Kök ayarlandı: ID {st.session_state.klasor_id}")
                _nav_c_ref.button("🔄", help="Klasörleri yenile", on_click=_klasorleri_yenile)

                # Klasör içeriğini tek istekle yükle; satır başına ek ağ çağrısını önle.
                host = st.session_state.get("pcloud_host", "https://api.pcloud.com")
                yeni_host, klasorler, mevcut_dosyalar = _klasor_icerigi_getir(
                    token,
                    host,
                    st.session_state.klasor_id,
                )
                st.session_state["pcloud_host"] = yeni_host

                _kaldirilacak_secim_id = st.session_state.get("_kaldirilacak_secim_id")
                if _kaldirilacak_secim_id is not None:
                    st.session_state.secilen = [
                        s for s in st.session_state.secilen
                        if str(s.get("id")) != str(_kaldirilacak_secim_id)
                    ]
                    st.session_state.pop(f"chk_form_{_kaldirilacak_secim_id}", None)
                    st.session_state["_kaldirilacak_secim_id"] = None

                _mevcut_secimler = list(st.session_state.secilen)
                _bu_sayfa_ids = {str(k["id"]) for k in klasorler}
                _reset_checkbox_ids = {
                    str(_id) for _id in st.session_state.pop("_reset_checkbox_ids", [])
                }
                _diger_sayfalar = [
                    s for s in _mevcut_secimler
                    if str(s.get("id")) not in _bu_sayfa_ids
                ]
                _eski_secim_sayisi = len(_mevcut_secimler)
                _diger_sayfalar = [
                    s for s in _diger_sayfalar
                    if not _secili_item_bloklu_mu(s)
                ]
                st.session_state.secilen = [
                    s for s in _mevcut_secimler
                    if not _secili_item_bloklu_mu(s)
                ]
                if len(st.session_state.secilen) < _eski_secim_sayisi:
                    st.warning("SATILANLAR listesinde olan ürünler seçimden çıkarıldı ve AI kuyruğuna gönderilmez.")

                _urun_sec_sol, _urun_sec_sag = st.columns([1.8, 1], gap="large")

                with _urun_sec_sol:
                    with st.container(border=True, height=720):
                        if klasorler:
                            st.markdown(
                                f"<div class='section-label'>{len(klasorler)} klasör</div>",
                                unsafe_allow_html=True
                            )
                            secilen_ids = {s["id"] for s in st.session_state.secilen}
                            _satir_meta = []
                            for k in klasorler:
                                folder_id = str(k["id"])
                                known_folder_status = st.session_state.kuyruk_klasor_durumlari.get(folder_id)
                                known_sheet_color = st.session_state.klasor_id_durumlari.get(folder_id)
                                is_product_folder = bool(
                                    k.get("is_product_folder") is True
                                    or known_folder_status is not None
                                    or known_sheet_color is not None
                                )
                                row_item = {**k, "is_product_folder": is_product_folder}
                                _chk_key = f"chk_form_{k['id']}"
                                zaten_secili = k["id"] in secilen_ids
                                urun_kodu = _klasor_urun_kodu_al(k["ad"])
                                satilmis_global = is_product_folder and _klasor_bloklu_mu(k["ad"])
                                kuyruk_status = None
                                if is_product_folder:
                                    kuyruk_status = st.session_state.kuyruga_eklenenler.get(urun_kodu)
                                    if kuyruk_status is None:
                                        kuyruk_status = known_folder_status
                                sheet_renk = (
                                    known_sheet_color
                                    if is_product_folder and known_sheet_color is not None
                                    else (_sheet_renk_durumu_klasor(k["id"], k["ad"]) if is_product_folder else None)
                                )
                                zaten_kuyrukta = (kuyruk_status is not None) or (sheet_renk is not None)
                                if sheet_renk == "red":
                                    _ikon = "🔴"
                                elif sheet_renk == "green" or kuyruk_status == "done":
                                    _ikon = "✅"
                                elif sheet_renk == "yellow":
                                    _ikon = "🟡"
                                elif kuyruk_status == "error":
                                    _ikon = "❌"
                                elif zaten_kuyrukta:
                                    _ikon = "🔵"
                                else:
                                    _ikon = ""
                                _satir_meta.append({
                                    "item": row_item,
                                    "chk_key": _chk_key,
                                    "zaten_secili": zaten_secili,
                                    "satilmis_global": satilmis_global,
                                    "zaten_kuyrukta": zaten_kuyrukta,
                                    "ikon": _ikon,
                                })

                            if not _queue_badges_ready:
                                st.caption("Klasör listesi hazır. Mağaza durum işaretleri son bilinen veriden gösteriliyor.")

                            for _row in _satir_meta:
                                k = _row["item"]
                                _c_chk, _c_name, _c_prev = st.columns([0.7, 9, 0.9], vertical_alignment="center")

                                with _c_chk:
                                    if _row["zaten_kuyrukta"]:
                                        st.markdown(
                                            f"<div style='padding:6px 0;font-size:1rem;text-align:center;'>{_row['ikon']}</div>",
                                            unsafe_allow_html=True,
                                        )
                                    else:
                                        if str(k["id"]) in _reset_checkbox_ids:
                                            st.session_state[_row["chk_key"]] = False
                                        elif _row["chk_key"] not in st.session_state:
                                            st.session_state[_row["chk_key"]] = _row["zaten_secili"]
                                        st.checkbox(
                                            "seç",
                                            key=_row["chk_key"],
                                            disabled=_row["satilmis_global"],
                                            label_visibility="hidden",
                                            on_change=_secim_toggle,
                                            args=(_row["item"], _row["chk_key"]),
                                        )

                                with _c_name:
                                    st.button(
                                        f"📁  {k['ad']}",
                                        key=f"open_folder_{k['id']}",
                                        width="stretch",
                                        help="Klasoru ac",
                                        on_click=_klasoru_ac,
                                        args=(k["id"], k["ad"]),
                                    )

                                with _c_prev:
                                    if st.button("🖼", key=f"oniz{k['id']}", help="Resimleri gör"):
                                        st.session_state._onizleme_klasor = k
                                        st.rerun(scope="app")

                            if st.session_state.get("_secim_limit_hatasi"):
                                st.error(st.session_state["_secim_limit_hatasi"])

                            if st.session_state.secilen:
                                _secim_aksiyon_paneli("queue_selected_inline")
                        else:
                            with st.spinner("Fotoğraflar yükleniyor..."):
                                _urls, _hata = _resimleri_getir(
                                    token,
                                    yeni_host,
                                    st.session_state.klasor_id,
                                    dosyalar=mevcut_dosyalar,
                                )
                            if _hata:
                                st.error(f"Hata: {_hata}")
                            elif not _urls:
                                st.info("Bu klasörde içerik yok.")
                            else:
                                st.caption(f"{len(_urls)} fotoğraf")
                                _cols_n = 3
                                for _rs in range(0, len(_urls), _cols_n):
                                    _row = _urls[_rs:_rs + _cols_n]
                                    _img_cols = st.columns(len(_row))
                                    for _c, _r in zip(_img_cols, _row):
                                        _c.image(_r["url"], caption=_r["ad"], width="stretch")

                with _urun_sec_sag:
                    with st.container(border=True, height=720):
                        _aktif_islem_urunleri = list(st.session_state.get("aktif_islem_urunleri") or [])
                        _aktif_islem_ozeti = dict(st.session_state.get("aktif_islem_ozeti") or {})
                        _gosterilecekler = list(st.session_state.secilen) if st.session_state.secilen else _aktif_islem_urunleri
                        st.markdown(
                            f"<div class='section-label'>Seçilen ürünler — {len(_gosterilecekler)}/15</div>",
                            unsafe_allow_html=True
                        )

                        if st.session_state.secilen:
                            _secim_aksiyon_paneli("queue_selected_sidebar", ustte=True)

                            for i, k in enumerate(st.session_state.secilen):
                                _sa, _sb, _sc = st.columns([0.4, 4, 0.6])
                                _sa.markdown(
                                    "<div style='padding:5px 0;font-size:0.85rem;text-align:center;'>📦</div>",
                                    unsafe_allow_html=True
                                )
                                _sb.markdown(
                                    f"<div style='padding:5px 2px;font-size:0.83rem;color:#e6edf3;'>{k['ad']}</div>",
                                    unsafe_allow_html=True
                                )
                                if _sc.button("✕", key=f"sil{i}", help="Kaldır"):
                                    removed = st.session_state.secilen[i]
                                    st.session_state["_kaldirilacak_secim_id"] = removed["id"]
                                    st.rerun()
                        elif _aktif_islem_urunleri:
                            if _aktif_islem_ozeti.get("durum") == "running":
                                st.info("Seçilen ürünler işleniyor. Durumlar bu panelde canlı olarak görünür.")
                            elif _aktif_islem_ozeti.get("durum") == "done":
                                _toplam = int(_aktif_islem_ozeti.get("toplam") or len(_aktif_islem_urunleri))
                                _basarili = int(_aktif_islem_ozeti.get("basarili") or 0)
                                _hatali = int(_aktif_islem_ozeti.get("hatali") or 0)
                                if _hatali:
                                    st.warning(f"İşlem tamamlandı. {_basarili}/{_toplam} başarılı, {_hatali} ürün hatalı.")
                                else:
                                    st.success(f"Tüm ürünlerin işlemi tamamlandı. {_basarili}/{_toplam} başarılı.")

                            for i, item in enumerate(_aktif_islem_urunleri):
                                _durum = str(item.get("durum") or "").strip().lower()
                                if _durum == "ok":
                                    _ikon = "✅"
                                elif _durum == "error":
                                    _ikon = "❌"
                                elif _durum == "isleniyor":
                                    _ikon = "⏳"
                                else:
                                    _ikon = "📦"
                                _sa, _sb = st.columns([0.5, 4.5])
                                _sa.markdown(
                                    f"<div style='padding:5px 0;font-size:0.9rem;text-align:center;'>{_ikon}</div>",
                                    unsafe_allow_html=True
                                )
                                _sb.markdown(
                                    f"<div style='padding:4px 2px;font-size:0.83rem;color:#e6edf3;'>{item.get('ad','')}</div>",
                                    unsafe_allow_html=True
                                )
                                if item.get("mesaj"):
                                    st.caption(item.get("mesaj"))

                            if _aktif_islem_ozeti.get("durum") == "done":
                                if st.button("İşlem panelini temizle", key="clear_active_batch_panel"):
                                    _aktif_islem_panelini_sifirla()
                                    st.session_state.son_islem_raporu = []
                                    st.rerun()
                        else:
                            st.caption("Soldaki listeden ürün seçin. Bu panelde seçilen ürünler ve AI kuyruğa gönder butonu görünecek.")

                if not st.session_state.get("aktif_islem_urunleri"):
                    _son_islem_raporu_goster()

        with st.container(key="main_tab_content_urun_sec"):
            _tab1_gezgin()

        # Dialog fragment dışında tetiklenmeli (Streamlit @fragment + @dialog uyumsuzluğu)
        if "_onizleme_klasor" in st.session_state:
            _ok = st.session_state["_onizleme_klasor"]
            del st.session_state["_onizleme_klasor"]
            _onizleme_dialog(
                st.session_state.pcloud_token,
                st.session_state.get("pcloud_host", "https://api.pcloud.com"),
                _ok,
            )


# ══ TAB 2 ════════════════════════════════════════════════════════════════════
if st.session_state.active_main_tab == "kuyruk":
    def _tab2_kuyruk():
        _force_queue_refresh = bool(st.session_state.pop("_kuyruk_refresh_istek", False))
        _queue_loading_ui = bool(st.session_state.get("_kuyruk_loading_ui")) or _force_queue_refresh
        if _queue_loading_ui:
            _tab_loading_gostergesi(
                "Kuyruk",
                45,
                "Sheets ve mağaza durumları yenileniyor. Son bilinen tablo korunuyor.",
                ready=False,
            )
        _t2h1, _t2h2 = st.columns([5, 1])
        _t2h1.markdown(
            f"<div style='padding:4px 0;font-size:0.95rem;font-weight:600;color:#e6edf3;'>"
            f"Kuyruk — <span style='color:#f59e0b;'>{st.session_state.hedef_magaza_id}</span></div>",
            unsafe_allow_html=True
        )
        yenile_btn = _t2h2.button("🔄 Yenile", width="stretch")

        if yenile_btn:
            st.session_state["_kuyruk_loading_ui"] = True
            st.session_state["_kuyruk_refresh_istek"] = True
            _kuyruk_satirlari_cached.clear()
            st.rerun()

        try:
            import pandas as pd
            from shared.product_catalog import _supabase_ready
            from shared.sheets import SheetsKatmani as _SK2

            if _force_queue_refresh:
                _kuyruk_cache_hazirla(st.session_state.hedef_magaza_id, force=True)
                try:
                    _magaza_renk_cache_yenile(st.session_state.hedef_magaza_id)
                except Exception:
                    pass

            satirlar = _kuyruk_satirlari_cached(st.session_state.hedef_magaza_id)
            _sk2 = _SK2(st.session_state.hedef_magaza_id)
            _yuklu_kodlar = _magaza_yuklu_kodlari_al(
                st.session_state.hedef_magaza_id,
                include_blocked=True,
            )
            _renk_durumlari = {
                (_urun_kodu_normalize(k) or _urun_kodu_al(k)): v
                for k, v in (
                    (
                        {
                            str(item.get("urun_id") or "").strip(): str(item.get("renk") or "").strip().lower()
                            for item in satirlar
                            if str(item.get("renk") or "").strip()
                        }
                    )
                    if _supabase_ready() and satirlar is not None
                    else (st.session_state.get("sheet_renk_durumlari") or _sk2.urun_renk_durumlari_al())
                ).items()
            }
            st.session_state.sheet_renk_durumlari = _renk_durumlari
            st.session_state.klasor_id_durumlari = {
                str(s.get("pcloud_klasor_id", "")).strip(): _renk_durumlari.get(_urun_kodu_normalize(s.get("urun_id", "")) or _urun_kodu_al(s.get("urun_id", "")))
                for s in satirlar
                if str(s.get("pcloud_klasor_id", "")).strip()
                and _renk_durumlari.get(_urun_kodu_normalize(s.get("urun_id", "")) or _urun_kodu_al(s.get("urun_id", "")))
            }
            st.session_state.kuyruk_klasor_durumlari = {
                str(s.get("pcloud_klasor_id", "")).strip(): str(s.get("status", "")).strip().lower()
                for s in satirlar
                if str(s.get("pcloud_klasor_id", "")).strip() and str(s.get("status", "")).strip()
            }
            if satirlar:
                df = pd.DataFrame(satirlar)
                if "status" in df.columns and "urun_id" in df.columns:
                    def _gorunen_status(row):
                        kod = _urun_kodu_normalize(row.get("urun_id", "")) or _urun_kodu_al(row.get("urun_id", ""))
                        renk = str(row.get("renk") or _renk_durumlari.get(kod) or "").strip().lower()
                        mevcut_status = str(row.get("status", "")).strip().lower()
                        if kod in _yuklu_kodlar:
                            return "done"
                        if renk == "green":
                            return "done"
                        if renk == "yellow":
                            return "error"
                        if renk == "red":
                            return "deleted"
                        return mevcut_status or row.get("status", "")

                    df["gosterim_status"] = df.apply(_gorunen_status, axis=1)
                else:
                    df["gosterim_status"] = df.get("status", "")

                sayim = df["gosterim_status"].value_counts() if "gosterim_status" in df else {}

                # Metric kartları
                mc = st.columns(7)
                for col, (label, key, color) in zip(mc, [
                    ("⏳ Bekleyen",    "pending",     "#fbbf24"),
                    ("🟢 Hazır",       "ready",       "#4ade80"),
                    ("⬇️ İndiriliyor", "downloading", "#60a5fa"),
                    ("📁 İndirildi",   "downloaded",  "#a78bfa"),
                    ("✅ Yüklendi",    "done",        "#22c55e"),
                    ("🔴 Silindi",     "deleted",     "#ef4444"),
                    ("❌ Hata",        "error",       "#ef4444"),
                ]):
                    val = int(sayim.get(key, 0))
                    col.markdown(
                        f"<div style='background:#161b22;border:1px solid #30363d;border-radius:8px;"
                        f"padding:12px 16px;text-align:center;'>"
                        f"<div style='font-size:0.72rem;color:#8b949e;margin-bottom:4px;'>{label}</div>"
                        f"<div style='font-size:1.6rem;font-weight:700;color:{color};'>{val}</div>"
                        f"</div>",
                        unsafe_allow_html=True
                    )

                st.markdown("<div style='height:12px;'></div>", unsafe_allow_html=True)

                _status_icon = {
                    "pending":"🔵","ready":"🔵","downloading":"⬇️",
                    "downloaded":"📁","uploading":"🔄","done":"✅","deleted":"🔴","error":"🟡"
                }
                if "gosterim_status" in df.columns:
                    df["🔘"] = df["gosterim_status"].map(_status_icon).fillna("⚪")
                    df["durum"] = df["gosterim_status"].map({
                        "pending": "hazır",
                        "ready": "hazır",
                        "downloading": "indiriliyor",
                        "downloaded": "indirildi",
                        "uploading": "yükleniyor",
                        "done": "yüklendi",
                        "deleted": "silindi",
                        "error": "yüklenmedi",
                    }).fillna(df["gosterim_status"])
                goster = [c for c in ["🔘","urun_id","boyut_ft","fiyat_usd","baslik","durum","islem_tarihi"] if c in df.columns]

                st.caption("Satırları seçmek için tıklayın (Shift ile çoklu), ardından sil butonuna basın.")
                secim = st.dataframe(
                    df[goster],
                    width="stretch",
                    hide_index=True,
                    on_select="rerun",
                    selection_mode="multi-row",
                )

                secilen_indexler = secim.selection.rows if secim.selection else []
                if secilen_indexler:
                    secilen_idler = df.iloc[secilen_indexler]["urun_id"].tolist()
                    _s1, _s2, _ = st.columns([3, 1, 4])
                    _s1.info(f"{len(secilen_idler)} satır seçildi")
                    if _s2.button(f"🗑 Sil ({len(secilen_idler)})", type="primary"):
                        try:
                            from shared.sheets import SheetsKatmani as _SK3
                            silinen = _SK3(st.session_state.hedef_magaza_id).satirlari_sil(secilen_idler)
                            for uid in secilen_idler:
                                _uid = _urun_kodu_normalize(uid) or _urun_kodu_al(uid)
                                st.session_state.kuyruga_eklenenler.pop(_uid, None)
                                st.session_state.sheet_renk_durumlari.pop(_uid, None)
                            st.session_state.kuyruk_klasor_durumlari = {}
                            st.session_state.klasor_id_durumlari = {}
                            st.session_state.kuyruk_yuklendi = False
                            _kuyruk_satirlari_cached.clear()
                            st.success(f"✅ {silinen} satır silindi.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ {e}")
            else:
                st.info("Kuyruk boş.")
            st.session_state["_kuyruk_loading_ui"] = False
        except Exception as e:
            st.session_state["_kuyruk_loading_ui"] = False
            st.warning(f"Sheets bağlantısı yok: {e}")

    with st.container(key="main_tab_content_kuyruk"):
        _tab2_kuyruk()


# ══ TAB 3 ════════════════════════════════════════════════════════════════════
if st.session_state.active_main_tab == "urunler":
    @st.dialog("Ürün Düzenle", width="large")
    def _urun_edit_dialog(urun: dict):
        import time as _t

        st.markdown(f"**{urun.get('product_code', '')}**")
        _ef1, _ef2, _ef3 = st.columns(3)
        _yeni_kod = _ef1.text_input("Ürün Kodu", value=urun.get("product_code", ""))
        _cm_gen = _ef2.number_input("Genişlik (cm)", value=_float_or_none(urun.get("width_cm")) or 0.0, min_value=0.0, step=1.0, format="%.0f")
        _cm_uz = _ef3.number_input("Uzunluk (cm)", value=_float_or_none(urun.get("length_cm")) or 0.0, min_value=0.0, step=1.0, format="%.0f")
        st.caption("Kategori, ft ölçüleri ve m² kayıt sırasında otomatik hesaplanır.")

        _es1, _es2, _es3 = st.columns([2, 2, 1])
        if _es1.button("Kaydet", type="primary", use_container_width=True):
            _new_code = _yeni_kod.strip()
            _derived = _derived_product_fields(_cm_gen, _cm_uz)
            if not _new_code:
                st.error("Ürün Kodu zorunlu.")
                return
            if _cm_gen <= 0 or _cm_uz <= 0:
                st.error("Genişlik cm ve Uzunluk cm zorunlu.")
                return
            if not _derived["category"]:
                st.error("Kategori otomatik hesaplanamadı; ölçüleri kontrol edin.")
                return
            _updated = {
                **urun,
                **_derived,
                "updated_at": _t.strftime("%Y-%m-%d %H:%M"),
            }
            _old_code = urun.get("product_code", "")
            if _new_code and _new_code != _old_code:
                _updated["product_code"] = _new_code
            _silinen_urunden_cikar(_updated.get("product_code", ""))
            _urunleri_cachede_uste_tut(_updated, remove_code=_old_code)
            _urun_guncelle_arkaplanda(_updated, old_code=_old_code)
            st.success("Kaydedildi. Kalıcı kayıt arka planda tamamlanıyor.")
            st.rerun()
        if _es2.button("İptal", use_container_width=True):
            st.rerun()

        # ── Silme ───────────────────────────────────────────────────────────
        st.divider()
        if not st.session_state.get("_sil_onay"):
            if _es3.button("🗑️ Sil", use_container_width=True):
                st.session_state["_sil_onay"] = True
                st.rerun()
        else:
            st.warning(f"**{urun.get('product_code')}** silinecek. Emin misiniz?")
            _so1, _so2 = st.columns(2)
            if _so1.button("Evet, sil", type="primary", use_container_width=True):
                _silinecek_kod = str(urun.get("product_code") or "").strip()
                try:
                    _silinen_urune_ekle(_silinecek_kod)
                    mevcut = [
                        item for item in (_panel_urunleri_yerden_yukle() if st.session_state.get("_urun_katalog_cache") is None else st.session_state.get("_urun_katalog_cache") or [])
                        if str(item.get("product_code") or "").strip() != _silinecek_kod
                    ]
                    st.session_state["_urun_katalog_cache"] = [dict(item) for item in mevcut]
                    st.session_state["_urun_katalog_cache_ts"] = _time.time()
                    st.session_state["_urun_katalog_cache_stok_mtime"] = float(_stok_dosya_yolu().stat().st_mtime) if _stok_dosya_yolu().exists() else 0.0
                    _json_kaydet(_RUNTIME_DIR / "panel_products.json", mevcut)
                    _urun_sil_arkaplanda(_silinecek_kod)
                    st.session_state.pop("_sil_onay", None)
                    st.session_state["_son_silinen_urun_kodu"] = _silinecek_kod
                    st.rerun()
                except Exception as exc:
                    st.error(f"{_silinecek_kod} silinemedi: {exc}")
            if _so2.button("Vazgeç", use_container_width=True):
                st.session_state.pop("_sil_onay", None)
                st.rerun()

    def _tab3_urunler():
        _force_store_refresh = bool(st.session_state.pop("_urunler_store_refresh", False))
        _envanter_cache = _envanter_cache_dosyadan_yukle()
        _refresh_started = float(st.session_state.get("_urunler_magaza_refresh_started_at") or 0.0)
        _cache_updated = float((_envanter_cache or {}).get("updated_at") or 0.0)
        _magaza_refresh_suruyor = bool(_refresh_started and _refresh_started > _cache_updated)
        _urunler_loading_ui = bool(st.session_state.get("_urunler_loading_ui")) or _magaza_refresh_suruyor
        _urunler_cache_var = st.session_state.get("_urun_katalog_cache") is not None
        if _urunler_loading_ui:
            _tab_loading_gostergesi(
                "Ürünler",
                55 if _urunler_cache_var else 20,
                "Ürün listesi ve mağaza yük durumları arka planda güncelleniyor.",
                ready=False,
            )
        if _force_store_refresh or _envanter_cache_stale_mi(_envanter_cache) or not ((_envanter_cache or {}).get("stores") or {}):
            _urunler_magaza_yenilemesini_baslat(force=_force_store_refresh)
            _refresh_started = float(st.session_state.get("_urunler_magaza_refresh_started_at") or 0.0)
            _magaza_refresh_suruyor = bool(_refresh_started and _refresh_started > float((_envanter_cache_dosyadan_yukle() or {}).get("updated_at") or 0.0))
            _urunler_loading_ui = bool(st.session_state.get("_urunler_loading_ui")) or _magaza_refresh_suruyor

        try:
            with st.spinner("Urunler ve magaza durumlari yenileniyor..."):
                urunler = _urunleri_yukle(
                    force_source_sync=False,
                    force_store_refresh=_force_store_refresh,
                )
            st.session_state["_urunler_loading_ui"] = False
        except Exception as exc:
            st.session_state["_urunler_loading_ui"] = False
            urunler = _panel_urunleri_yerden_yukle()
            if urunler:
                st.warning(f"Canlı katalog okunamadı, yerel stok gösteriliyor: {exc}")
            else:
                st.error(f"Ürün verisi yüklenemedi: {exc}")
                return

        if _magaza_refresh_suruyor:
            st.caption("Magaza yuk durumlari guncelleniyor. Liste hazir; yesil noktalar ve yuklu sayilari birazdan tazelenecek.")

        aktifler = [u for u in urunler if str(u.get("status", "")).lower() != "sold"]
        satilanlar = [u for u in urunler if str(u.get("status", "")).lower() == "sold"]

        _liste_aktif = st.session_state.urun_alt_tab == "liste"
        _satilan_aktif = st.session_state.urun_alt_tab == "satilan"
        _tabs_col, _stats_col, _refresh_col, _btn_col = st.columns(
            [4.0, 2.6, 1.6, 1.9], vertical_alignment="center"
        )
        with _tabs_col:
            _b1, _b2 = st.columns(2, vertical_alignment="center")
            if _b1.button(
                "Ürün Listesi",
                key="urun_alt_tab_liste",
                width="stretch",
                type="primary" if _liste_aktif else "secondary",
            ):
                st.session_state.urun_alt_tab = "liste"
                st.rerun()
            if _b2.button(
                "Satılan Ürünler",
                key="urun_alt_tab_satilan",
                width="stretch",
                type="primary" if _satilan_aktif else "secondary",
            ):
                st.session_state.urun_alt_tab = "satilan"
                st.rerun()
        with _stats_col:
            st.markdown(
                "<div class='compact-stats' style='justify-content:flex-start; flex-wrap:nowrap; margin:0;'>"
                f"<div class='compact-stat'><span class='compact-stat-label'>Aktif</span>"
                f"<span class='compact-stat-value'>{len(aktifler)}</span></div>"
                f"<div class='compact-stat'><span class='compact-stat-label'>Satılan</span>"
                f"<span class='compact-stat-value'>{len(satilanlar)}</span></div>"
                "</div>",
                unsafe_allow_html=True,
            )
        with _refresh_col:
            if st.button("🔄 Yenile", width="stretch", key="urun_list_refresh_btn"):
                _urun_katalog_cache_temizle()
                st.session_state["_urunler_loading_ui"] = True
                st.session_state["_urunler_store_refresh"] = True
                st.rerun()
        with _btn_col:
            if _liste_aktif:
                if st.button(
                    "➕ Yeni Ürün Ekle" if not st.session_state.urun_formu_acik else "✖ Kapat",
                    width="stretch",
                    key="urun_form_toggle_btn",
                ):
                    st.session_state.urun_formu_acik = not st.session_state.urun_formu_acik
                    st.rerun()

        if st.session_state.urun_alt_tab == "liste":
            if st.session_state.urun_formu_acik:
                _NUF = {
                    "nuf_kod": "",
                    "nuf_cm_gen": 0.0, "nuf_cm_uz": 0.0,
                }
                for _k, _dv in _NUF.items():
                    if _k not in st.session_state:
                        st.session_state[_k] = _dv

                _cm_g = float(st.session_state.get("nuf_cm_gen") or 0)
                _cm_u = float(st.session_state.get("nuf_cm_uz") or 0)
                _yeni_m2_raw = (_cm_g * _cm_u) / 10000 if _cm_g > 0 and _cm_u > 0 else None

                with st.container(border=True):
                    _fhdr, _fclr = st.columns([6, 1])
                    _fhdr.markdown("##### Yeni Ürün Ekle")
                    if _fclr.button("🗑 Temizle", key="nuf_temizle_btn", use_container_width=True):
                        for _k, _dv in _NUF.items():
                            st.session_state[_k] = _dv
                        st.rerun()

                    with st.form("new_product_quick_add_form", clear_on_submit=True):
                        _f1, _f2, _f3 = st.columns(3)
                        _f1.markdown(_zorunlu_label("Ürün kodu"), unsafe_allow_html=True)
                        _f1.text_input("Ürün kodu", key="nuf_kod", label_visibility="collapsed")
                        _f2.markdown(_zorunlu_label("Genişlik cm"), unsafe_allow_html=True)
                        _f2.number_input("Genişlik cm", min_value=0.0, step=1.0, format="%.0f", key="nuf_cm_gen", label_visibility="collapsed")
                        _f3.markdown(_zorunlu_label("Uzunluk cm"), unsafe_allow_html=True)
                        _f3.number_input("Uzunluk cm", min_value=0.0, step=1.0, format="%.0f", key="nuf_cm_uz", label_visibility="collapsed")

                        if _yeni_m2_raw is not None:
                            st.caption(f"m², ft ölçüleri ve kategori kayıt sırasında otomatik hesaplanır. Tahmini alan: **{_yeni_m2_raw:.2f} m²**")
                        else:
                            st.caption("3 zorunlu alanı girip kaydedin; ürün hemen listeye eklenir. ft ölçüleri, m² ve kategori otomatik hesaplanır.")

                        _quick_add_submit = st.form_submit_button(
                            "➕ Ürün Ekle",
                            type="primary",
                            width="stretch",
                        )

                    if _quick_add_submit:
                        _nuf_kod = st.session_state.nuf_kod
                        _nuf_cmg = float(st.session_state.nuf_cm_gen or 0)
                        _nuf_cmu = float(st.session_state.nuf_cm_uz or 0)
                        _nuf_m2 = (_nuf_cmg * _nuf_cmu) / 10000 if _nuf_cmg > 0 and _nuf_cmu > 0 else None
                        _nuf_derived = _derived_product_fields(_nuf_cmg, _nuf_cmu)
                        kod = _urun_kodu_normalize(_nuf_kod) or _urun_kodu_al(_nuf_kod)
                        mevcut_kodlar = {
                            str(u.get("product_code") or "").strip().lower()
                            for u in urunler
                            if str(u.get("product_code") or "").strip()
                        }
                        if not kod:
                            st.error("Ürün Kodu zorunlu.")
                        elif str(kod).strip().lower() in mevcut_kodlar:
                            st.error(f"{kod} ürün kodu zaten mevcut, tekrar eklenemez.")
                        elif _nuf_cmg <= 0 or _nuf_cmu <= 0:
                            st.error("cm ölçüleri zorunlu.")
                        elif _nuf_m2 is None or _nuf_m2 <= 0:
                            st.error("m² hesaplanamadı; cm ölçülerini kontrol edin.")
                        elif not _nuf_derived["category"]:
                            st.error("Kategori otomatik hesaplanamadı; ölçüleri kontrol edin.")
                        else:
                            eklenen = dict(
                                product_id=_product_id_for_code(kod),
                                product_code=kod,
                                **_nuf_derived,
                                status="active",
                                source_tab="manual",
                                source_row="",
                                loaded_store_count="",
                                loaded_stores="",
                                sold_at="",
                                sold_site="",
                                customer_name="",
                                customer_phone="",
                                customer_address="",
                                customer_contact_country="",
                                note="",
                                updated_at=_time.strftime("%Y-%m-%d %H:%M:%S"),
                            )
                            try:
                                _silinen_urunden_cikar(kod)
                                _urunleri_cachede_uste_tut(eklenen)
                                _urunleri_kaydet_arkaplanda([eklenen], incremental=True, sync_sheet=True)
                                st.session_state["_son_eklenen_urun_kodu"] = kod
                                st.session_state["_urun_listesi_oncele_kod"] = kod
                                st.rerun()
                            except Exception as exc:
                                st.error(f"{kod} eklenemedi: {exc}")

            _son_eklenen_urun = st.session_state.pop("_son_eklenen_urun_kodu", "")
            if _son_eklenen_urun:
                st.success(f"{_son_eklenen_urun} eklendi. Liste yenilenirken en ustte gorunmeli.")
            _son_silinen_urun = st.session_state.pop("_son_silinen_urun_kodu", "")
            if _son_silinen_urun:
                st.success(f"{_son_silinen_urun} silindi. Satirdan tamamen kaldirildi.")

            st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
            _l1, _l2 = st.columns([3.7, 1.9])
            filtre = _l1.text_input("Ara", placeholder="Ürün kodu veya not")
            kategori_opsiyonlari = ["Tümü", "Boş", "Doormat", "Area", "Runner"]
            kategori_filtre = _l2.selectbox("Kategori", kategori_opsiyonlari, index=0)
            _urun_aksiyon_alani = st.container()

            gosterilecek = aktifler
            if filtre.strip():
                needle = filtre.strip().lower()
                gosterilecek = [
                    u for u in gosterilecek
                    if needle in str(u.get("product_code", "")).lower()
                    or needle in str(u.get("note", "")).lower()
                    or needle in str(u.get("category", "")).lower()
                ]

            if kategori_filtre == "Boş":
                gosterilecek = [u for u in gosterilecek if not str(u.get("category", "")).strip()]
            elif kategori_filtre != "Tümü":
                gosterilecek = [u for u in gosterilecek if str(u.get("category", "")).strip() == kategori_filtre]

            def _aktif_urun_siralama(urun: dict):
                oncelikli_kod = str(st.session_state.get("_urun_listesi_oncele_kod") or "").strip()
                urun_kodu = str(urun.get("product_code") or "").strip()
                if oncelikli_kod and urun_kodu == oncelikli_kod:
                    return (4, float("inf"))
                raw_updated = str(urun.get("updated_at", "")).strip()
                if raw_updated:
                    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
                        try:
                            return (3, datetime.strptime(raw_updated, fmt).timestamp())
                        except Exception:
                            pass
                raw_source = str(urun.get("source_row", "")).strip()
                if raw_source.isdigit():
                    return (2, int(raw_source))
                return (1, 0)

            gosterilecek = sorted(gosterilecek, key=_aktif_urun_siralama, reverse=True)

            try:
                from shared.store_manager import tum_magazalar as _tum_mag_liste
                magaza_adlari = sorted(m.get("store_id") or m.get("store_name") for m in _tum_mag_liste())
            except Exception:
                magaza_adlari = sorted({
                    magaza.strip()
                    for urun in urunler
                    for magaza in str(urun.get("loaded_stores", "")).split(",")
                    if magaza.strip()
                })

            canli_magaza_haritasi = _urunler_tab_canli_magaza_haritasi(magaza_adlari)

            try:
                import pandas as pd

                satirlar = []
                magaza_yuklu_sayilari = {magaza: 0 for magaza in magaza_adlari}
                for urun in gosterilecek:
                    stores = {
                        s.strip()
                        for s in str(urun.get("loaded_stores", "")).split(",")
                        if s.strip()
                    }
                    kod = _urun_kodu_normalize(urun.get("product_code", "")) or _urun_kodu_al(urun.get("product_code", ""))
                    stores.update(canli_magaza_haritasi.get(kod, set()))
                    satir = {
                        "Ürün Kodu": urun.get("product_code", ""),
                        "cm": urun.get("size_cm", ""),
                        "m2": urun.get("area_m2", ""),
                        "ft": urun.get("size_ft", ""),
                        "kategori": urun.get("category", ""),
                        "yüklü": len(stores),
                    }
                    for magaza in magaza_adlari:
                        yuklu_mu = magaza in stores
                        satir[magaza] = "🟢" if yuklu_mu else "⚪"
                        if yuklu_mu:
                            magaza_yuklu_sayilari[magaza] += 1
                    satirlar.append(satir)

                if satirlar:
                    kolon_etiketleri = {
                        magaza: f"{magaza} ({magaza_yuklu_sayilari.get(magaza, 0)})"
                        for magaza in magaza_adlari
                    }
                    tablo_satirlari = [
                        {
                            (kolon_etiketleri.get(anahtar, anahtar)): deger
                            for anahtar, deger in satir.items()
                        }
                        for satir in satirlar
                    ]
                    _secim = st.dataframe(
                        pd.DataFrame(tablo_satirlari),
                        use_container_width=True,
                        hide_index=True,
                        on_select="rerun",
                        selection_mode="single-row",
                    )
                    _secilen_satirlar = _secim.selection.rows if _secim and hasattr(_secim, "selection") else []
                    if _secilen_satirlar:
                        _sec_kod = satirlar[_secilen_satirlar[0]]["Ürün Kodu"]
                        _secili_urun = next((u for u in urunler if u.get("product_code") == _sec_kod), None)
                        with _urun_aksiyon_alani:
                            if _secili_urun:
                                st.markdown("<div style='height:6px;'></div>", unsafe_allow_html=True)
                                _ab1, _ab2, _ab3 = st.columns([1.35, 1.0, 3.65])
                                if _ab1.button(
                                    f"✏️ {_sec_kod} Düzenle",
                                    type="primary",
                                    use_container_width=True,
                                    key="duzenle_btn",
                                ):
                                    st.session_state["_edit_urun"] = _secili_urun
                                if _ab2.button(
                                    "📋 Kopyala",
                                    use_container_width=True,
                                    key="kopyala_btn",
                                ):
                                    _copy_text = _build_product_copy_text(_secili_urun)
                                    st.session_state["_clipboard_copy_request"] = {
                                        "text": _copy_text,
                                        "nonce": datetime.now().isoformat(),
                                    }
                                    st.session_state["_product_copy_preview"] = {
                                        "code": str(_sec_kod),
                                        "text": _copy_text,
                                    }
                                _copy_preview = st.session_state.get("_product_copy_preview")
                                if _copy_preview and str(_copy_preview.get("code")) == str(_sec_kod):
                                    st.caption("Hazır kopya. Otomatik pano engellenirse aşağıdaki metni seçip Cmd/Ctrl+C yapabilirsiniz.")
                                    st.text_area(
                                        "Hazır kopya",
                                        value=_copy_preview.get("text", ""),
                                        key=f"kopya_hazir_{_sec_kod}",
                                        height=120,
                                    )
                    else:
                        st.session_state.pop("_product_copy_preview", None)
                        with _urun_aksiyon_alani:
                            _urun_aksiyon_alani.empty()
                else:
                    _secilen_satirlar = []
                    st.info("Gösterilecek ürün bulunamadı.")
            except Exception as exc:
                _secilen_satirlar = []
                st.warning(f"Ürün listesi çizilemedi: {exc}")

            _clipboard_req = st.session_state.pop("_clipboard_copy_request", None)
            if _clipboard_req and _clipboard_req.get("text"):
                _clipboard_text = json.dumps(_clipboard_req["text"], ensure_ascii=False)
                components.html(
                    f"""
                    <script>
                    const copyText = {_clipboard_text};
                    async function writeClipboard(text) {{
                      try {{
                        if (navigator.clipboard && window.isSecureContext) {{
                          await navigator.clipboard.writeText(text);
                          return true;
                        }}
                      }} catch (e) {{}}
                      try {{
                        const area = document.createElement("textarea");
                        area.value = text;
                        area.setAttribute("readonly", "");
                        area.style.position = "fixed";
                        area.style.left = "-9999px";
                        document.body.appendChild(area);
                        area.focus();
                        area.select();
                        const ok = document.execCommand("copy");
                        document.body.removeChild(area);
                        return ok;
                      }} catch (e) {{
                        return false;
                      }}
                    }}
                    writeClipboard(copyText);
                    </script>
                    <!-- {_clipboard_req.get("nonce", "")} -->
                    """,
                    height=0,
                )
                st.toast("Kopya hazır", icon="📋")

            if st.session_state.get("_edit_urun"):
                _edit_data = st.session_state.pop("_edit_urun")
                _urun_edit_dialog(_edit_data)

        if st.session_state.urun_alt_tab == "satilan":
            try:
                from shared.store_manager import tum_magazalar as _tum_satilan_magazalar
                satilan_site_opsiyonlari = [m.get("store_name") or m.get("store_id") for m in _tum_satilan_magazalar()]
            except Exception:
                satilan_site_opsiyonlari = []

            with st.container(border=True):
                _sold_hdr, _sold_btn = st.columns([6, 1.4], vertical_alignment="center")
                _sold_hdr.markdown("##### Satılan Ürün Ekle")
                _sold_hdr.caption(
                    "Kapalıyken yer kaplamaz, gerektiğinde açıp kayıt girebilirsiniz."
                    if not st.session_state.satilan_urun_formu_acik
                    else "Form açık. Kaydettikten sonra otomatik kapanır."
                )
                if _sold_btn.button(
                    "Aç" if not st.session_state.satilan_urun_formu_acik else "Kapat",
                    key="satilan_urun_form_toggle_btn",
                    use_container_width=True,
                ):
                    st.session_state.satilan_urun_formu_acik = not st.session_state.satilan_urun_formu_acik
                    st.rerun()

                if st.session_state.satilan_urun_formu_acik:
                    st.divider()
                    aktif_opsiyonlar = [
                        f"{u.get('product_code')}  |  {u.get('category') or 'Boş'}  |  {u.get('size_ft') or u.get('size_cm')}"
                        for u in aktifler
                    ]
                    with st.form("satilan_urun_form", clear_on_submit=False):
                        st.markdown(_zorunlu_label("Ürün seç"), unsafe_allow_html=True)
                        secili = st.selectbox(
                            "Ürün seç",
                            options=aktif_opsiyonlar,
                            index=None,
                            placeholder="Bir aktif ürün seçin...",
                            key="satilan_urun_form_secimi",
                            label_visibility="collapsed",
                        )
                        _s1, _s2, _s3 = st.columns(3)
                        _s1.markdown(_zorunlu_label("Satılan site"), unsafe_allow_html=True)
                        satilan_site = _s1.multiselect(
                            "Satılan site",
                            options=satilan_site_opsiyonlari,
                            placeholder="Bir veya daha fazla mağaza seçin...",
                            label_visibility="collapsed",
                        )
                        musteri_adi = _s2.text_input("Müşteri adı")
                        satilan_tarih = _s3.text_input("Satılan tarih", value=_time.strftime("%Y-%m-%d %H:%M"))
                        _s4, _s5 = st.columns(2)
                        musteri_telefon = _s4.text_input("Telefon")
                        iletisim_ulke = _s5.text_input("İletişim & ülke")
                        musteri_adres = st.text_area("Adres", height=90)
                        satilan_not = st.text_input("Not")
                        submit_sold = st.form_submit_button("🟥 Satılan Ürünü Kaydet", type="primary", width="stretch")

                    if submit_sold:
                        kod = _urun_kodu_normalize(secili.split("|", 1)[0]) or _urun_kodu_al(secili) if secili else None
                        if not kod:
                            st.error("Ürün seçimi zorunlu.")
                        elif not satilan_site:
                            st.error("Satılan site zorunlu.")
                        else:
                            yeni_liste = []
                            secili_urun = None
                            for urun in urunler:
                                if str(urun.get("product_code")) == kod:
                                    copy = dict(urun)
                                    copy["status"] = "sold"
                                    copy["sold_at"] = satilan_tarih.strip() or _time.strftime("%Y-%m-%d %H:%M")
                                    copy["sold_site"] = ", ".join(satilan_site)
                                    copy["customer_name"] = musteri_adi.strip()
                                    copy["customer_phone"] = musteri_telefon.strip()
                                    copy["customer_address"] = musteri_adres.strip()
                                    copy["customer_contact_country"] = iletisim_ulke.strip()
                                    if satilan_not.strip():
                                        copy["note"] = satilan_not.strip()
                                    copy["updated_at"] = _time.strftime("%Y-%m-%d %H:%M")
                                    secili_urun = copy
                                    yeni_liste.append(copy)
                                else:
                                    yeni_liste.append(urun)
                            if secili_urun:
                                _urunleri_kaydet(yeni_liste)
                                st.session_state.satilan_urun_formu_acik = False
                                yuklu = secili_urun.get("loaded_stores") or "Yüklü mağaza bulunamadı."
                                st.success(f"{kod} satılan ürünlere eklendi.")
                                st.info(f"Yüklü mağazalar: {yuklu}")
                                st.rerun()

            st.markdown("##### Satılan Ürünler")
            try:
                from shared.store_manager import tum_magazalar as _tum_filtre_magazalar
                _tum_magaza_kayitlari = _tum_filtre_magazalar()
                _satilan_magaza_ops = [
                    str(m.get("store_name") or m.get("store_id") or "").strip()
                    for m in _tum_magaza_kayitlari
                    if str(m.get("store_name") or m.get("store_id") or "").strip()
                ]
                _magaza_alias_map = {
                    str(m.get("store_name") or m.get("store_id") or "").strip(): {
                        str(m.get("store_name") or "").strip(),
                        str(m.get("store_id") or "").strip(),
                    }
                    for m in _tum_magaza_kayitlari
                    if str(m.get("store_name") or m.get("store_id") or "").strip()
                }
            except Exception:
                _satilan_magaza_ops = sorted({
                    parca.strip()
                    for urun in satilanlar
                    for parca in str(urun.get("sold_site", "")).split(",")
                    if parca.strip()
                })
                _magaza_alias_map = {
                    magaza: {magaza}
                    for magaza in _satilan_magaza_ops
                }
            _ss1, _ss2, _ss3 = st.columns([3, 1.4, 1.8])
            satilan_ara = _ss1.text_input("Satılanlarda ara", placeholder="Kod, müşteri adı, site...")
            satilan_kategori = _ss2.selectbox("Kategori filtresi", ["Tümü", "Boş", "Doormat", "Area", "Runner"], index=0)
            satilan_magazalar = _ss3.multiselect(
                "Mağaza filtresi",
                options=_satilan_magaza_ops,
                placeholder="Tümü",
            )

            satilan_goster = list(satilanlar)
            if satilan_ara.strip():
                needle = satilan_ara.strip().lower()
                satilan_goster = [
                    u for u in satilan_goster
                    if needle in str(u.get("product_code", "")).lower()
                    or needle in str(u.get("customer_name", "")).lower()
                    or needle in str(u.get("sold_site", "")).lower()
                    or needle in str(u.get("customer_phone", "")).lower()
                ]
            if satilan_kategori == "Boş":
                satilan_goster = [u for u in satilan_goster if not str(u.get("category", "")).strip()]
            elif satilan_kategori != "Tümü":
                satilan_goster = [u for u in satilan_goster if str(u.get("category", "")).strip() == satilan_kategori]
            if satilan_magazalar:
                _secili_magazalar = {
                    alias.strip()
                    for magaza in satilan_magazalar
                    for alias in _magaza_alias_map.get(magaza, {magaza})
                    if alias.strip()
                }
                satilan_goster = [
                    u for u in satilan_goster
                    if _secili_magazalar.intersection({
                        parca.strip()
                        for parca in str(u.get("sold_site", "")).split(",")
                        if parca.strip()
                    })
                ]
            def _satilan_siralama(urun: dict):
                raw_dt = str(urun.get("sold_at", "")).strip()
                if raw_dt:
                    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
                        try:
                            return (2, datetime.strptime(raw_dt, fmt).timestamp())
                        except Exception:
                            pass
                try:
                    return (1, int(str(urun.get("source_row", "")).strip() or 0))
                except Exception:
                    return (0, 0)
            satilan_goster = sorted(satilan_goster, key=_satilan_siralama, reverse=True)

            try:
                import pandas as pd

                satilan_satirlar = []
                for urun in satilan_goster:
                    satilan_satirlar.append({
                        "Ürün Kodu": urun.get("product_code", ""),
                        "cm": urun.get("size_cm", ""),
                        "m2": urun.get("area_m2", ""),
                        "ft": urun.get("size_ft", ""),
                        "kategori": urun.get("category", ""),
                        "satılan_tarih": urun.get("sold_at", ""),
                        "site": _site_label(urun.get("sold_site", "")),
                        "müşteri": urun.get("customer_name", ""),
                        "telefon": urun.get("customer_phone", ""),
                        "iletişim_ülke": urun.get("customer_contact_country", ""),
                        "adres": urun.get("customer_address", ""),
                        "yüklü_mağazalar": urun.get("loaded_stores", ""),
                        "not": urun.get("note", ""),
                    })

                if satilan_satirlar:
                    st.dataframe(pd.DataFrame(satilan_satirlar), width="stretch", hide_index=True)
                else:
                    st.info("Satılan ürün bulunamadı.")
            except Exception as exc:
                st.warning(f"Satılan ürün listesi çizilemedi: {exc}")

    with st.container(key="main_tab_content_urunler"):
        _tab3_urunler()


# ══ TAB 4 ════════════════════════════════════════════════════════════════════
if st.session_state.active_main_tab == "ayarlar":
    st.session_state.setdefault("ayarlar_alt_tab", "magaza")
    _ayar_btn1, _ayar_btn2 = st.columns(2)
    if _ayar_btn1.button(
        "Mağaza Yönetimi",
        key="ayarlar_alt_magaza",
        width="stretch",
        type="primary" if st.session_state.ayarlar_alt_tab == "magaza" else "secondary",
    ):
        st.session_state.ayarlar_alt_tab = "magaza"
        st.rerun()
    if _ayar_btn2.button(
        "API",
        key="ayarlar_alt_api",
        width="stretch",
        type="primary" if st.session_state.ayarlar_alt_tab == "api" else "secondary",
    ):
        st.session_state.ayarlar_alt_tab = "api"
        st.rerun()

    if st.session_state.ayarlar_alt_tab == "api":
        st.markdown("#### API Ayarları")
        with st.form("env_form"):
            gemini = st.text_input("GEMINI_API_KEY", value=os.environ.get("GEMINI_API_KEY", ""), type="password")
            sheet = st.text_input("GOOGLE_SHEET_ID", value=os.environ.get("GOOGLE_SHEET_ID", ""))
            supabase_url = st.text_input("SUPABASE_URL", value=os.environ.get("SUPABASE_URL", ""))
            supabase_key = st.text_input(
                "SUPABASE_SERVICE_ROLE_KEY",
                value=os.environ.get("SUPABASE_SERVICE_ROLE_KEY", ""),
                type="password",
            )
            supabase_table = st.text_input("SUPABASE_PRODUCTS_TABLE", value=os.environ.get("SUPABASE_PRODUCTS_TABLE", "products"))
            creds = st.text_input("GOOGLE_CREDS_JSON", value=os.environ.get("GOOGLE_CREDS_JSON", ""),
                                  placeholder="/Users/.../credentials.json")
            if st.form_submit_button("💾 Kaydet", type="primary"):
                satirlar = []
                for k, v in [
                    ("GEMINI_API_KEY", gemini),
                    ("GOOGLE_SHEET_ID", sheet),
                    ("SUPABASE_URL", supabase_url),
                    ("SUPABASE_SERVICE_ROLE_KEY", supabase_key),
                    ("SUPABASE_PRODUCTS_TABLE", supabase_table),
                    ("GOOGLE_CREDS_JSON", creds),
                ]:
                    if v:
                        os.environ[k] = v
                        satirlar.append(f"{k}={v}")
                    else:
                        os.environ.pop(k, None)
                _env_path.write_text("\n".join(satirlar))
                st.success("✅ Kaydedildi!")
                st.rerun()

        st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
        for key in [
            "GEMINI_API_KEY",
            "GOOGLE_SHEET_ID",
            "SUPABASE_URL",
            "SUPABASE_SERVICE_ROLE_KEY",
            "SUPABASE_PRODUCTS_TABLE",
            "GOOGLE_CREDS_JSON",
        ]:
            val = os.environ.get(key, "")
            if val:
                st.markdown(
                    f"<div style='background:#052e16;border:1px solid #166534;border-radius:6px;"
                    f"padding:6px 12px;font-size:0.8rem;color:#4ade80;margin-bottom:4px;'>"
                    f"✅ {key}: {val[:6]}****</div>",
                    unsafe_allow_html=True
                )
            else:
                st.markdown(
                    f"<div style='background:#450a0a;border:1px solid #7f1d1d;border-radius:6px;"
                    f"padding:6px 12px;font-size:0.8rem;color:#fca5a5;margin-bottom:4px;'>"
                    f"❌ {key}: tanımsız</div>",
                    unsafe_allow_html=True
                )

    if st.session_state.ayarlar_alt_tab == "magaza":
        try:
            from shared.store_manager import tum_magazalar as _tm, magaza_guncelle as _mg, magaza_ekle as _me
            import json as _json2
            from modules.ai_icerik import template_config_normallestir as _tmpl_norm
            from pathlib import Path as _Path2

            class _SafeDict(dict):
                def __missing__(self, key):
                    return "{" + key + "}"

            def _render_preview_text(_text, _ctx):
                try:
                    return str(_text or "").format_map(_SafeDict(_ctx)).strip()
                except Exception:
                    return str(_text or "").strip()

            def _preview_context():
                return {
                    "urun_id": "RUG-2048",
                    "boyut_ft": "2.8x9.9",
                    "rounded_ft": "3x10",
                    "rounded_ft_label": "3x10 ft",
                    "boyut_cm": "85x301",
                    "metrekare": "2.56",
                    "sqft": "27.56",
                    "tip": "Runner",
                    "tip_lower": "runner",
                    "renk1": "Blue",
                    "renk2": "Orange",
                    "renk_scheme": "Soft Peach, Muted Teal",
                    "pattern": "Floral",
                    "tahmini_yil": "Mid-Century",
                    "stil": "Vintage Oushak",
                    "koken": "Turkish",
                    "home_style": "Bohemian & eclectic",
                    "shop_section": "Runner Rugs",
                    "ana_resim_tag": "3x10-ft-vintage-turkish-runner-rug-soft-peach-muted-teal",
                    "baslik": "3x10 ft Vintage Turkish Runner Rug | Soft Peach Floral Wool Hallway Rug | Antique Decor Accent",
                }

            def _description_preview(_cfg):
                _ctx = _preview_context()
                _opening = (
                    f"This {_ctx['boyut_ft']} ft Vintage Turkish {_ctx['tip']} with its faded "
                    f"{_ctx['renk_scheme']} {_ctx['pattern']} pattern carries the quiet confidence "
                    f"of a piece that has traveled decades to find the right room."
                )
                _details = (
                    "📋 Product Details:\n"
                    f"Color Scheme: {_ctx['renk_scheme']}\n"
                    f"Size: {_ctx['boyut_ft']} ft - {_ctx['boyut_cm']} cm\n"
                    f"Total SQFT: {_ctx['sqft']}\n"
                    f"Total SQM: {_ctx['metrekare']}\n"
                    f"Made in: {_ctx['tahmini_yil']}\n"
                    f"Pattern: {_ctx['pattern']}\n"
                    "Pile: 0.50 cm"
                )
                _story_template = _cfg["static_texts"].get("story_size_template", "")
                _story_size = _render_preview_text(_story_template, _ctx) if _story_template else (
                    f"Measuring {_ctx['boyut_ft']} ft, this versatile {_ctx['rounded_ft']} {_ctx['tip_lower']} "
                    "works beautifully in a hallway, kitchen aisle, or entryway."
                )
                _framework = _cfg["prompt_rules"].get("description_example_template", "").strip()
                if _framework:
                    _ctx.update({
                        "opening": _opening,
                        "details_block": _details,
                        "hikaye": "\n\n".join([
                            "Some rugs just fill a space. This brings soul. Its faded palette and floral movement feel quietly collected rather than loud.",
                            _story_size,
                            "Handwoven wool gives it an honest, tactile surface that feels warm underfoot and visually rich in layered interiors.",
                            "It suits bohemian, antique, collected, and soft traditional spaces while still feeling easy to place in daily life.",
                        ]),
                        "story_size_paragraph": _story_size,
                        "no_extra_fees_block": _render_preview_text(_cfg["static_texts"].get("no_extra_fees", ""), _ctx),
                        "easy_returns_block": _render_preview_text(_cfg["static_texts"].get("easy_returns", ""), _ctx),
                        "footer_block": _render_preview_text(_cfg["static_texts"].get("footer", ""), _ctx),
                    })
                    return _render_preview_text(_framework, _ctx)
                else:
                    _story = "\n\n".join([
                        "Some rugs just fill a space. This brings soul. Its faded palette and floral movement feel quietly collected rather than loud.",
                        _story_size,
                        "Handwoven wool gives it an honest, tactile surface that feels warm underfoot and visually rich in layered interiors.",
                        "It suits bohemian, antique, collected, and soft traditional spaces while still feeling easy to place in daily life.",
                    ])
                return "\n\n".join(filter(None, [
                    _opening,
                    _render_preview_text(_cfg["static_texts"].get("no_extra_fees", ""), _ctx),
                    _details,
                    _render_preview_text(_cfg["static_texts"].get("easy_returns", ""), _ctx),
                    _story,
                    _render_preview_text(_cfg["static_texts"].get("footer", ""), _ctx),
                ]))

            def _default_preview_framework(_cfg):
                _blocks = ["{opening}"]
                if _cfg["static_texts"].get("no_extra_fees", "").strip():
                    _blocks.append("{no_extra_fees_block}")
                _blocks.append("{details_block}")
                if _cfg["static_texts"].get("easy_returns", "").strip():
                    _blocks.append("{easy_returns_block}")
                _blocks.append("{hikaye}")
                if _cfg["static_texts"].get("footer", "").strip():
                    _blocks.append("{footer_block}")
                return "\n\n".join(_blocks)

            def _is_global_ai_template(_cfg):
                return str((_cfg or {}).get("template_id") or "").strip() == "default_v1"

            def _editor_defaults(_cfg):
                _pr = _cfg["prompt_rules"]
                _preview_template = (_pr.get("description_example_template", "") or "").strip()
                _defaults = {
                    "description_example_template": _preview_template or _default_preview_framework(_cfg),
                }
                if not _is_global_ai_template(_cfg):
                    return _defaults
                _defaults.update({
                    "title_brief": _pr.get("title_brief", ""),
                    "title_target_min": int(_pr.get("title_target_min", 120)),
                    "title_target_max": int(_pr.get("title_target_max", 140)),
                    "title_max_length": int(_pr.get("title_max_length", 140)),
                    "title_rules": _pr.get("title_rules", ""),
                    "description_brief": _pr.get("description_brief", ""),
                    "opening_rules": _pr.get("opening_rules", ""),
                    "story_rules": _pr.get("story_rules", ""),
                    "tag_strategy": _pr.get("tag_strategy", ""),
                    "tag_rules": _pr.get("tag_rules", ""),
                    "prompt_extra": _cfg.get("prompt_extra_instructions", ""),
                    "tag_count": int(_pr.get("tag_count", 13)),
                    "tag_max_length": int(_pr.get("tag_max_length", 20)),
                })
                return _defaults

            def _ensure_editor_state(_store_id, _cfg):
                _defaults = _editor_defaults(_cfg)
                _sig_key = f"editor_sig_{_store_id}"
                _new_sig = _json2.dumps(_defaults, ensure_ascii=False, sort_keys=True)
                if st.session_state.get(_sig_key) != _new_sig:
                    for _k, _v in _defaults.items():
                        st.session_state[f"editor_{_store_id}_{_k}"] = _v
                    st.session_state[_sig_key] = _new_sig

            def _editor_dirty(_store_id, _cfg):
                _defaults = _editor_defaults(_cfg)
                for _k, _v in _defaults.items():
                    if st.session_state.get(f"editor_{_store_id}_{_k}", _v) != _v:
                        return True
                return False

            def _template_editor_payload(_tmpl_text, _store_id):
                _kayit = _json2.loads(_tmpl_text)
                if str(_kayit.get("template_id") or "").strip() == "default_v1":
                    _kayit["prompt_extra_instructions"] = st.session_state[f"editor_{_store_id}_prompt_extra"]
                    _kayit.setdefault("prompt_rules", {})
                    _kayit["prompt_rules"].update({
                        "title_target_min": int(st.session_state[f"editor_{_store_id}_title_target_min"]),
                        "title_target_max": int(st.session_state[f"editor_{_store_id}_title_target_max"]),
                        "title_max_length": int(st.session_state[f"editor_{_store_id}_title_max_length"]),
                        "tag_count": int(st.session_state[f"editor_{_store_id}_tag_count"]),
                        "tag_max_length": int(st.session_state[f"editor_{_store_id}_tag_max_length"]),
                        "title_brief": st.session_state[f"editor_{_store_id}_title_brief"],
                        "title_rules": st.session_state[f"editor_{_store_id}_title_rules"],
                        "tag_strategy": st.session_state[f"editor_{_store_id}_tag_strategy"],
                        "tag_rules": st.session_state[f"editor_{_store_id}_tag_rules"],
                        "description_brief": st.session_state[f"editor_{_store_id}_description_brief"],
                        "opening_rules": st.session_state[f"editor_{_store_id}_opening_rules"],
                        "story_rules": st.session_state[f"editor_{_store_id}_story_rules"],
                        "description_example_template": st.session_state[f"editor_{_store_id}_description_example_template"],
                    })
                else:
                    _kayit["prompt_extra_instructions"] = ""
                    _kayit["prompt_rules"] = {
                        "description_example_template": st.session_state[f"editor_{_store_id}_description_example_template"]
                    }
                return _kayit

            def _toggle_preview_edit(_store_id, _value=None):
                _key = f"preview_edit_mode_{_store_id}"
                _mevcut = bool(st.session_state.get(_key, False))
                st.session_state[_key] = (not _mevcut) if _value is None else bool(_value)

            def _open_preview_edit(_store_id, _cfg):
                _editor_key = f"editor_{_store_id}_description_example_template"
                _mevcut = str(st.session_state.get(_editor_key, "") or "").strip()
                if not _mevcut:
                    st.session_state[_editor_key] = _editor_defaults(_cfg)["description_example_template"]
                st.session_state[f"preview_edit_mode_{_store_id}"] = True

            def _select_settings_store(_store_id):
                st.session_state.ayar_magaza_id = _store_id

            def _draft_cfg(_base_cfg, _store_id):
                _cfg = _json2.loads(_json2.dumps(_base_cfg, ensure_ascii=False))
                _cfg.setdefault("prompt_rules", {})
                if _is_global_ai_template(_cfg):
                    _cfg["prompt_extra_instructions"] = st.session_state.get(
                        f"editor_{_store_id}_prompt_extra",
                        _cfg.get("prompt_extra_instructions", "")
                    )
                    _cfg["prompt_rules"].update({
                        "title_target_min": int(st.session_state.get(f"editor_{_store_id}_title_target_min", _cfg["prompt_rules"].get("title_target_min", 120))),
                        "title_target_max": int(st.session_state.get(f"editor_{_store_id}_title_target_max", _cfg["prompt_rules"].get("title_target_max", 140))),
                        "title_max_length": int(st.session_state.get(f"editor_{_store_id}_title_max_length", _cfg["prompt_rules"].get("title_max_length", 140))),
                        "tag_count": int(st.session_state.get(f"editor_{_store_id}_tag_count", _cfg["prompt_rules"].get("tag_count", 13))),
                        "tag_max_length": int(st.session_state.get(f"editor_{_store_id}_tag_max_length", _cfg["prompt_rules"].get("tag_max_length", 20))),
                        "title_brief": st.session_state.get(f"editor_{_store_id}_title_brief", _cfg["prompt_rules"].get("title_brief", "")),
                        "title_rules": st.session_state.get(f"editor_{_store_id}_title_rules", _cfg["prompt_rules"].get("title_rules", "")),
                        "tag_strategy": st.session_state.get(f"editor_{_store_id}_tag_strategy", _cfg["prompt_rules"].get("tag_strategy", "")),
                        "tag_rules": st.session_state.get(f"editor_{_store_id}_tag_rules", _cfg["prompt_rules"].get("tag_rules", "")),
                        "description_brief": st.session_state.get(f"editor_{_store_id}_description_brief", _cfg["prompt_rules"].get("description_brief", "")),
                        "opening_rules": st.session_state.get(f"editor_{_store_id}_opening_rules", _cfg["prompt_rules"].get("opening_rules", "")),
                        "story_rules": st.session_state.get(f"editor_{_store_id}_story_rules", _cfg["prompt_rules"].get("story_rules", "")),
                        "description_example_template": st.session_state.get(
                            f"editor_{_store_id}_description_example_template",
                            _cfg["prompt_rules"].get("description_example_template", "") or _default_preview_framework(_cfg)
                        ),
                    })
                else:
                    _cfg["prompt_extra_instructions"] = ""
                    _cfg["prompt_rules"] = {
                        "description_example_template": st.session_state.get(
                            f"editor_{_store_id}_description_example_template",
                            _cfg["prompt_rules"].get("description_example_template", "") or _default_preview_framework(_cfg)
                        )
                    }
                return _tmpl_norm(_cfg, template_id=_cfg.get("template_id", "default_v1"), template_name=_cfg.get("template_name", "Default"))

            _tum_magazalar = _tm()
            _tmpl_listesi = _template_listesi()
            _global_ai_id = "__DEFAULT_AI__"
            _global_ai_secili = {
                "store_id": _global_ai_id,
                "store_name": "Default AI Rules",
                "sheet_tab": "",
                "google_sheet_id": None,
                "price_per_m2": 0,
                "template": "default_v1",
                "active": True,
            }

            _kaynak_magaza_ids = [m["store_id"] for m in _tum_magazalar] or ["PatchArts"]
            _secilebilir_ids = [_global_ai_id] + [m["store_id"] for m in _tum_magazalar]
            if st.session_state.ayar_magaza_id not in _secilebilir_ids:
                st.session_state.ayar_magaza_id = st.session_state.hedef_magaza_id if st.session_state.hedef_magaza_id in _kaynak_magaza_ids else _global_ai_id

            _secili = next((m for m in _tum_magazalar if m["store_id"] == st.session_state.ayar_magaza_id), None)
            if st.session_state.ayar_magaza_id == _global_ai_id:
                _secili = _global_ai_secili
            _tmpl_cfg = None
            _tmpl_raw = {}
            _tmpl_json = "{}"
            _tmpl_path = None
            _editor_is_dirty = False
            if _secili:
                _tmpl_path = _template_yolu(_secili.get("template", "default_v1"))
                try:
                    _tmpl_raw = _json2.loads(_tmpl_path.read_text(encoding="utf-8")) if _tmpl_path.exists() else {}
                except Exception as _tmpl_err:
                    _tmpl_raw = {}
                    st.warning(f"Template okunamadi, varsayilan sema gosteriliyor: {_tmpl_err}")
                _tmpl_cfg = _tmpl_norm(_tmpl_raw, template_id=_secili.get("template", "default_v1"),
                                       template_name=_secili.get("store_name", _secili["store_id"]))
                _tmpl_json = _json2.dumps(_tmpl_cfg, ensure_ascii=False, indent=2)
                _ensure_editor_state(_secili["store_id"], _tmpl_cfg)
                _editor_is_dirty = _editor_dirty(_secili["store_id"], _tmpl_cfg)

            _left, _right = st.columns([1.1, 3.2])

            with _left:
                st.markdown("#### Mağazalar")
                _global_selected = st.session_state.ayar_magaza_id == _global_ai_id
                st.button(
                    f"{'🧠' if _global_selected else '⚙️'} Default AI Rules",
                    key="sel_default_ai_rules",
                    width="stretch",
                    type="primary" if _global_selected else "secondary",
                    disabled=(_editor_is_dirty and not _global_selected),
                    on_click=_select_settings_store,
                    args=(_global_ai_id,),
                )
                for _m in _tum_magazalar:
                    _aktif_ikon = "🟢" if _m.get("active") else "⬜"
                    _is_selected = st.session_state.ayar_magaza_id == _m["store_id"]
                    st.button(
                        f"{_aktif_ikon} {_m['store_name']}",
                        key=f"sel_store_{_m['store_id']}",
                        width="stretch",
                        type="primary" if _is_selected else "secondary",
                        disabled=(_editor_is_dirty and not _is_selected),
                        on_click=_select_settings_store,
                        args=(_m["store_id"],),
                    )

                st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
                with st.expander("➕ Yeni Mağaza Ekle"):
                    with st.form("yeni_magaza_form"):
                        _varsayilan_kaynak_id = st.session_state.ayar_magaza_id if st.session_state.ayar_magaza_id in _kaynak_magaza_ids else (
                            "PatchArts" if "PatchArts" in _kaynak_magaza_ids else _kaynak_magaza_ids[0]
                        )
                        _kaynak_idx = _kaynak_magaza_ids.index(_varsayilan_kaynak_id)
                        _kaynak_id = st.selectbox("Varsayılanları Kopyala", options=_kaynak_magaza_ids, index=_kaynak_idx)
                        _kaynak_magaza = next((m for m in _tum_magazalar if m["store_id"] == _kaynak_id), None) or {
                            "store_id": "PatchArts",
                            "store_name": "PatchArts",
                            "sheet_tab": "PatchArts",
                            "google_sheet_id": None,
                            "price_per_m2": 300,
                            "template": "default_v1",
                            "active": True,
                        }
                        _nid = st.text_input("Mağaza ID", placeholder="MyStore")
                        _nname = st.text_input("Görünen Ad", placeholder="My Store")
                        _nprice = st.number_input("m²/$ fiyat", value=int(_kaynak_magaza.get("price_per_m2", 300)),
                                                  min_value=1, max_value=9999, step=10)
                        _onerilen_tmpl = f"{(_nid or '').strip()}_v1"
                        _tmpl_default = _onerilen_tmpl if _onerilen_tmpl in _tmpl_listesi else _kaynak_magaza.get("template", "default_v1")
                        _nt2_idx = _tmpl_listesi.index(_tmpl_default) if _tmpl_default in _tmpl_listesi else 0
                        _nt2 = st.selectbox("Template", options=_tmpl_listesi, index=_nt2_idx)
                        _ngsid = st.text_input("Google Sheet ID", value=_kaynak_magaza.get("google_sheet_id") or "",
                                               placeholder="Boş = env GOOGLE_SHEET_ID")
                        _na2 = st.checkbox("Aktif başlat", value=bool(_kaynak_magaza.get("active", False)))
                        if st.form_submit_button("➕ Ekle", type="primary"):
                            _nid_clean = _nid.strip()
                            _nname_clean = _nname.strip()
                            if _nid_clean and _nname_clean:
                                _mevcut_ids = [m["store_id"] for m in _tum_magazalar]
                                if _nid_clean in _mevcut_ids:
                                    st.error(f"'{_nid_clean}' zaten mevcut!")
                                else:
                                    try:
                                        _me({
                                            "store_id": _nid_clean,
                                            "store_name": _nname_clean,
                                            "sheet_tab": _nid_clean,
                                            "google_sheet_id": _ngsid.strip() or _kaynak_magaza.get("google_sheet_id"),
                                            "price_per_m2": _nprice,
                                            "template": _nt2,
                                            "active": _na2,
                                        })
                                        from shared.sheets import (
                                            _client as _gc_fn,
                                            BASLIK_SATIRI as _BS,
                                            QUEUE_SHEET_MIN_COLS as _QSMC,
                                            QUEUE_SHEET_MIN_ROWS as _QSMR,
                                        )
                                        _gc2 = _gc_fn()
                                        _sheet_key = (_ngsid.strip() or _kaynak_magaza.get("google_sheet_id")
                                                      or os.environ.get("GOOGLE_SHEET_ID", ""))
                                        _sp2 = _gc2.open_by_key(_sheet_key)
                                        _mevcut_tab = [w.title for w in _sp2.worksheets()]
                                        if _nid_clean not in _mevcut_tab:
                                            _ws_new = _sp2.add_worksheet(title=_nid_clean, rows=_QSMR, cols=_QSMC)
                                            _ws_new.append_row(_BS)
                                        st.success(f"✅ '{_nid_clean}' eklendi.")
                                        st.session_state.ayar_magaza_id = _nid_clean
                                        st.rerun()
                                    except Exception as _e:
                                        st.error(f"❌ {_e}")
                            else:
                                st.warning("ID ve Ad zorunlu!")

            with _right:
                if not _secili:
                    st.info("Düzenlemek için bir mağaza seçin.")
                else:
                    st.markdown(f"#### {_secili['store_name']}")
                    if _secili["store_id"] != _global_ai_id:
                        with st.form(f"store_main_form_{_secili['store_id']}"):
                            _c1, _c2 = st.columns(2)
                            _m_name = _c1.text_input("Görünen Ad", value=_secili.get("store_name", _secili["store_id"]))
                            _m_tab = _c2.text_input("Sheet Tab", value=_secili.get("sheet_tab", _secili["store_id"]))
                            _c3, _c4, _c5 = st.columns(3)
                            _m_sheet_id = _c3.text_input("Google Sheet ID", value=_secili.get("google_sheet_id") or "",
                                                         placeholder="Boş = env GOOGLE_SHEET_ID")
                            _np = _c4.number_input("m²/$", value=int(_secili.get("price_per_m2", 300)),
                                                   min_value=1, max_value=9999, step=10)
                            _nt_idx = _tmpl_listesi.index(_secili.get("template", "default_v1")) if _secili.get("template") in _tmpl_listesi else 0
                            _nt = _c5.selectbox("Template", options=_tmpl_listesi, index=_nt_idx)
                            _na = st.checkbox("Aktif", value=bool(_secili.get("active")))
                            if st.form_submit_button("💾 Mağaza Ayarlarını Kaydet", type="primary"):
                                _mg(_secili["store_id"], {
                                    "store_name": _m_name.strip() or _secili["store_id"],
                                    "sheet_tab": _m_tab.strip() or _secili["store_id"],
                                    "google_sheet_id": _m_sheet_id.strip() or None,
                                    "price_per_m2": _np,
                                    "template": _nt,
                                    "active": _na,
                                })
                                try:
                                    from shared.sheets import SheetsKatmani as _SettingsSheets
                                    _SettingsSheets(_secili["store_id"]).sheet_hazirla()
                                except Exception as _sheet_err:
                                    st.warning(f"Sheet sekmesi kontrol edilemedi: {_sheet_err}")
                                st.success("✅ Mağaza ayarları kaydedildi!")
                                st.rerun()
                    else:
                        st.info("Buradaki ayarlar tüm mağazaların ortak AI kurallarını belirler. Mağaza bazlı fiyat ve template seçimi mağaza kartlarında kalır.")

                    st.session_state.setdefault("ayarlar_template_tab", "preview")
                    _tb1, _tb2, _tb3 = st.columns(3)
                    if _tb1.button(
                        "Ön İzleme",
                        key=f"ayar_template_preview_{_secili['store_id']}",
                        width="stretch",
                        type="primary" if st.session_state.ayarlar_template_tab == "preview" else "secondary",
                    ):
                        st.session_state.ayarlar_template_tab = "preview"
                        st.rerun()
                    if _tb2.button(
                        "AI Kurallar",
                        key=f"ayar_template_rules_{_secili['store_id']}",
                        width="stretch",
                        type="primary" if st.session_state.ayarlar_template_tab == "rules" else "secondary",
                    ):
                        st.session_state.ayarlar_template_tab = "rules"
                        st.rerun()
                    if _tb3.button(
                        "JSON Gör",
                        key=f"ayar_template_json_{_secili['store_id']}",
                        width="stretch",
                        type="primary" if st.session_state.ayarlar_template_tab == "json" else "secondary",
                    ):
                        st.session_state.ayarlar_template_tab = "json"
                        st.rerun()

                    if st.session_state.ayarlar_template_tab == "preview":
                        _preview_cfg = _draft_cfg(_tmpl_cfg, _secili["store_id"])
                        if _editor_is_dirty:
                            st.warning("Kaydedilmemiş değişiklikler var. Kaydetmeden başka mağazaya geçemezsin.")
                            _wd1, _wd2 = st.columns([1, 1])
                            if _wd1.button("💾 Taslağı Kaydet", key=f"save_dirty_{_secili['store_id']}", type="primary"):
                                _norm = _tmpl_norm(
                                    _template_editor_payload(_tmpl_json, _secili["store_id"]),
                                    template_id=_tmpl_cfg["template_id"],
                                    template_name=_tmpl_cfg["template_name"],
                                )
                                _tmpl_path.write_text(_json2.dumps(_norm, ensure_ascii=False, indent=2), encoding="utf-8")
                                st.success(f"✅ Template kaydedildi: {_tmpl_path.name}")
                                st.rerun()
                            if _wd2.button("↺ Değişiklikleri Geri Al", key=f"reset_dirty_{_secili['store_id']}"):
                                _defaults = _editor_defaults(_tmpl_cfg)
                                for _k, _v in _defaults.items():
                                    st.session_state[f"editor_{_secili['store_id']}_{_k}"] = _v
                                st.rerun()

                        _ph1, _ph2 = st.columns([5, 1])
                        _ph1.markdown("##### Ön İzleme")
                        if f"preview_edit_mode_{_secili['store_id']}" not in st.session_state:
                            st.session_state[f"preview_edit_mode_{_secili['store_id']}"] = False
                        _ph2.button(
                            "👁 Önizleme" if st.session_state[f"preview_edit_mode_{_secili['store_id']}"] else "✏️ Edit",
                            key=f"preview_edit_btn_{_secili['store_id']}",
                            width="stretch",
                            on_click=_toggle_preview_edit if st.session_state[f"preview_edit_mode_{_secili['store_id']}"] else _open_preview_edit,
                            args=(_secili["store_id"],) if st.session_state[f"preview_edit_mode_{_secili['store_id']}"] else (_secili["store_id"], _tmpl_cfg),
                        )

                        st.caption("Son kullanıcının göreceğine yakın description önizlemesi")

                        if st.session_state[f"preview_edit_mode_{_secili['store_id']}"]:
                            st.info("Ön izleme alanını doğrudan burada düzenleyebilirsin. Boş satır, metin ve blok sırası serbest.")
                            with st.form(f"preview_inline_form_{_secili['store_id']}"):
                                st.text_area(
                                    "Ön İzleme Şablonu",
                                    key=f"editor_{_secili['store_id']}_description_example_template",
                                    height=340,
                                    help="Örn: {opening}, {details_block}, {hikaye}, {footer_block} gibi blokları kullanabilirsin."
                                )
                                st.caption("Kullanılabilir bloklar: {opening}, {no_extra_fees_block}, {details_block}, {easy_returns_block}, {hikaye}, {footer_block}, {story_size_paragraph}")
                                _pe1, _pe2 = st.columns([1, 1])
                                _kaydetildi = _pe1.form_submit_button("💾 Ön İzlemeyi Kaydet", type="primary")
                                _iptal = _pe2.form_submit_button("Vazgeç")
                                if _kaydetildi:
                                    _norm = _tmpl_norm(
                                        _template_editor_payload(_tmpl_json, _secili["store_id"]),
                                        template_id=_tmpl_cfg["template_id"],
                                        template_name=_tmpl_cfg["template_name"],
                                    )
                                    _tmpl_path.write_text(_json2.dumps(_norm, ensure_ascii=False, indent=2), encoding="utf-8")
                                    _toggle_preview_edit(_secili["store_id"], False)
                                    st.success(f"✅ Ön izleme şablonu kaydedildi: {_tmpl_path.name}")
                                    st.rerun()
                                if _iptal:
                                    st.session_state[f"editor_{_secili['store_id']}_description_example_template"] = _editor_defaults(_tmpl_cfg)["description_example_template"]
                                    _toggle_preview_edit(_secili["store_id"], False)
                                    st.rerun()

                            st.markdown("##### Canlı Sonuç")
                            st.markdown(
                                f"<div class='preview-card'>{_description_preview(_preview_cfg)}</div>",
                                unsafe_allow_html=True
                            )
                        else:
                            st.markdown(
                                f"<div class='preview-card'>{_description_preview(_preview_cfg)}</div>",
                                unsafe_allow_html=True
                            )

                    if st.session_state.ayarlar_template_tab == "rules":
                        if _is_global_ai_template(_tmpl_cfg):
                            st.info("Bu template ortak AI merkezidir. Title, tag, renk/pattern sınıflandırma ve genel prompt kuralları tüm mağazalar için buradan yönetilir.")
                            st.text_area(
                                "Title Talimatı",
                                key=f"editor_{_secili['store_id']}_title_brief",
                                height=95,
                                help="Uzun kuyruklu olsun, ilk 40 karakter güçlü olsun gibi doğal talimatlar yazın."
                            )
                            st.text_area(
                                "Description Talimatı",
                                key=f"editor_{_secili['store_id']}_description_brief",
                                height=95,
                                help="SEO uyumlu, bizim yapıdan ayrılmadan kaliteli içerik üret gibi yönlendirmeler."
                            )
                            st.text_area(
                                "Tag Talimatı",
                                key=f"editor_{_secili['store_id']}_tag_strategy",
                                height=110,
                                help="Örn: 3 tag renk, 3 tag ölçü, 2 tag oda kullanımı, tekrar kalıp olmasın."
                            )
                            st.text_area(
                                "Title Base Rules",
                                key=f"editor_{_secili['store_id']}_title_rules",
                                height=240,
                                help="AI'in gerçekten okuduğu detaylı title kuralları. Karakter, tekrar, yapı ve keyword yerleşimi burada tanımlanır."
                            )
                            st.text_area(
                                "Tag Base Rules",
                                key=f"editor_{_secili['store_id']}_tag_rules",
                                height=240,
                                help="AI'in gerçekten okuduğu detaylı tag kuralları. Ölçü dağılımı, room fit, color/pattern dengesi gibi ana mantık burada tanımlanır."
                            )
                            st.text_area(
                                "Genel AI Talimatı",
                                key=f"editor_{_secili['store_id']}_prompt_extra",
                                height=90,
                                help="Ton, marka dili, kaçınmasını istediğiniz ifade tipi gibi genel notlar."
                            )
                            st.text_area(
                                "Opening Rules",
                                key=f"editor_{_secili['store_id']}_opening_rules",
                                height=140,
                                help="Description açılış cümlesi için detaylı prompt kuralları."
                            )
                            st.text_area(
                                "Story Rules",
                                key=f"editor_{_secili['store_id']}_story_rules",
                                height=220,
                                help="Description hikaye paragrafları için detaylı prompt kuralları."
                            )

                            _mini1, _mini2, _mini3, _mini4, _mini5 = st.columns([0.9, 0.9, 0.9, 0.8, 1])
                            _mini1.number_input("Title min", min_value=10, max_value=140, key=f"editor_{_secili['store_id']}_title_target_min")
                            _mini2.number_input("Title hedef", min_value=10, max_value=140, key=f"editor_{_secili['store_id']}_title_target_max")
                            _mini3.number_input("Title max", min_value=10, max_value=140, key=f"editor_{_secili['store_id']}_title_max_length")
                            _mini4.number_input("Tag adet", min_value=1, max_value=13, key=f"editor_{_secili['store_id']}_tag_count")
                            _mini5.number_input("Tag max", min_value=1, max_value=20, key=f"editor_{_secili['store_id']}_tag_max_length")
                            st.markdown("##### Description Yapısı")
                            st.caption("Description yerleşimini Ön İzleme sekmesindeki Edit butonundan düzenleyebilirsin. Bu ortak şablon tüm mağazaların temel AI kurallarını belirler.")
                        else:
                            st.info("Bu mağaza template'inde yalnızca description yerleşimi özelleştirilir. Title, tag ve diğer AI kuralları ortak `default_v1` üzerinden gelir.")
                            st.markdown("##### Description Yapısı")
                            st.caption("Bu mağaza için sadece blok sırası ve description akışı değişir. Düzenlemek için Ön İzleme sekmesindeki Edit butonunu kullan.")

                        if st.button("💾 AI Metin Ayarlarını Kaydet", key=f"save_text_editor_{_secili['store_id']}", type="primary"):
                            _norm = _tmpl_norm(
                                _template_editor_payload(_tmpl_json, _secili["store_id"]),
                                template_id=_tmpl_cfg["template_id"],
                                template_name=_tmpl_cfg["template_name"],
                            )
                            _tmpl_path.write_text(_json2.dumps(_norm, ensure_ascii=False, indent=2), encoding="utf-8")
                            st.success(f"✅ Template kaydedildi: {_tmpl_path.name}")
                            st.rerun()

                    if st.session_state.ayarlar_template_tab == "json":
                        st.caption("İleri seviye düzenleme. Gerekmedikçe Text Gör sekmesini kullanın.")
                        _tmpl_text = st.text_area(
                            "Template JSON",
                            value=_tmpl_json,
                            height=620,
                            key=f"tj_{_secili['store_id']}_{_secili.get('template', 'default_v1')}",
                        )
                        if st.button("💾 JSON Template Kaydet", key=f"mts_{_secili['store_id']}"):
                            try:
                                _kaydedilecek = _json2.loads(_tmpl_text)
                                _norm = _tmpl_norm(
                                    _kaydedilecek,
                                    template_id=_secili.get("template", "default_v1"),
                                    template_name=_secili.get("store_name", _secili["store_id"]),
                                )
                                _tmpl_path.write_text(_json2.dumps(_norm, ensure_ascii=False, indent=2), encoding="utf-8")
                                st.success(f"✅ Template kaydedildi: {_tmpl_path.name}")
                                st.rerun()
                            except Exception as _e_tmpl:
                                st.error(f"❌ Template kaydedilemedi: {_e_tmpl}")

        except Exception as _e3:
            st.error(f"Mağaza yönetimi yüklenemedi: {_e3}")


# ══ TAB 5 ════════════════════════════════════════════════════════════════════
if st.session_state.active_main_tab == "olcu_ara":
    def _tab5_ara():
        import pandas as pd

        _olcu_loading = bool(st.session_state.get("_olcu_ara_loading_ui"))
        if _olcu_loading:
            _tab_loading_gostergesi(
                "Ölçü Ara",
                35,
                "Aktif ürün ölçüleri hazırlanıyor. Sonuçlar yerel kaynakla hızla açılacak.",
                ready=False,
            )

        _gc1, _gc2, _ = st.columns([2, 3, 3])
        if _gc1.button("🔄 Ürünleri Yenile"):
            st.session_state.ara_sonuclari = []
            st.session_state["_olcu_ara_loading_ui"] = True
            st.rerun()
        _gc2.caption("Kaynak: Supabase `products` tablosundaki aktif ürünler")

        try:
            katalog_urunleri = _urunleri_yukle(force_source_sync=False)
        except Exception as exc:
            st.error(f"Ürün kataloğu yüklenemedi: {exc}")
            return

        _olcu_sig = tuple(
            (
                str(urun.get("product_code") or "").strip(),
                str(urun.get("status") or "").strip(),
                str(urun.get("size_cm") or "").strip(),
                str(urun.get("size_ft") or "").strip(),
                str(urun.get("category") or "").strip(),
                str(urun.get("loaded_store_count") or "").strip(),
                str(urun.get("loaded_stores") or "").strip(),
                str(urun.get("note") or "").strip(),
                str(urun.get("width_ft") or "").strip(),
                str(urun.get("length_ft") or "").strip(),
                str(urun.get("width_cm") or "").strip(),
                str(urun.get("length_cm") or "").strip(),
                str(urun.get("area_m2") or "").strip(),
                str(urun.get("source_tab") or "").strip(),
            )
            for urun in katalog_urunleri
        )
        _olcu_kaynak = _olcu_ara_kaynaklari_cached(_olcu_sig)
        arama_kaynaklari = list(_olcu_kaynak.get("arama_kaynaklari") or [])
        atlanan_ft = int(_olcu_kaynak.get("atlanan_ft") or 0)
        st.session_state["_olcu_ara_loading_ui"] = False

        if not arama_kaynaklari:
            st.warning("Ölçü arama için kullanılabilir aktif ürün bulunamadı.")
            return

        kategori_opsiyonlari = ["Tümü"] + sorted({
            satir["tur"] for satir in arama_kaynaklari if satir["tur"]
        })
        kategori_sayimlari = {}
        for satir in arama_kaynaklari:
            kategori_sayimlari[satir["tur"]] = kategori_sayimlari.get(satir["tur"], 0) + 1

        st.caption(
            f"Aktif ürün: **{len(arama_kaynaklari)}**"
            f"  |  Toplam katalog: {_olcu_kaynak.get('toplam', len(katalog_urunleri))}"
            f"  |  Satılan: {_olcu_kaynak.get('satilan', 0)}"
            f"  |  Ft ölçüsü eksik olduğu için atlanan: {atlanan_ft}"
        )
        st.caption(
            "  |  ".join(
                [f"{kategori}: {kategori_sayimlari[kategori]}" for kategori in sorted(kategori_sayimlari)]
            )
        )
        st.divider()

        _fa, _fb, _fc, _fd, _fe = st.columns([2, 2, 2, 2, 1])
        hedef_g = _fa.number_input("Genişlik (ft)", min_value=0.1, max_value=30.0, value=2.0, step=0.1, format="%.1f")
        hedef_u = _fb.number_input("Uzunluk (ft)", min_value=0.1, max_value=50.0, value=3.0, step=0.1, format="%.1f")
        tolerans = _fc.slider("Tolerans (±ft)", min_value=0.1, max_value=2.0, value=0.3, step=0.1)
        tur_sec = _fd.selectbox("Kategori", kategori_opsiyonlari)
        ara_btn = _fe.button("🔍 Ara", type="primary", width="stretch")

        if ara_btn:
            filtre = [
                satir for satir in arama_kaynaklari
                if tur_sec == "Tümü" or satir["tur"] == tur_sec
            ]
            eslesmeler = []
            for row in filtre:
                g, u = float(row["ft1"]), float(row["ft2"])
                fark = min(
                    ((g - hedef_g) ** 2 + (u - hedef_u) ** 2) ** 0.5,
                    ((g - hedef_u) ** 2 + (u - hedef_g) ** 2) ** 0.5,
                )
                if fark <= tolerans * 1.41:
                    eslesmeler.append({
                        "KOD": row["kod"],
                        "CM": row["cm"],
                        "FT": f"{g:.2f} x {u:.2f}",
                        "Tür": row["tur"],
                        "Yüklü": row["loaded_store_count"],
                        "Yüklü Mağazalar": row["loaded_stores"],
                        "Not": row["note"],
                        "Δ (ft)": round(fark, 2),
                    })
            eslesmeler.sort(key=lambda x: x["Δ (ft)"])
            st.session_state.ara_sonuclari = eslesmeler

        if st.session_state.ara_sonuclari:
            eslesmeler = st.session_state.ara_sonuclari
            if ara_btn:
                if eslesmeler:
                    st.success(f"**{len(eslesmeler)} sonuç** — {hedef_g}x{hedef_u} ft, ±{tolerans} ft")
                else:
                    st.warning("Eşleşen ürün bulunamadı. Toleransı artırın.")

            if eslesmeler:
                st.dataframe(
                    pd.DataFrame(eslesmeler),
                    width="stretch",
                    hide_index=True,
                    column_config={
                        "KOD": st.column_config.TextColumn("KOD", width="small"),
                        "CM": st.column_config.TextColumn("CM", width="small"),
                        "FT": st.column_config.TextColumn("FT", width="medium"),
                        "Tür": st.column_config.TextColumn("Tür", width="small"),
                        "Yüklü": st.column_config.NumberColumn("Yüklü", format="%d", width="small"),
                        "Yüklü Mağazalar": st.column_config.TextColumn("Yüklü Mağazalar", width="medium"),
                        "Not": st.column_config.TextColumn("Not", width="medium"),
                        "Δ (ft)": st.column_config.NumberColumn("Δ ft", format="%.2f", width="small"),
                    },
                )

                if st.session_state.pcloud_token:
                    st.divider()
                    st.markdown("#### 🏪 Mağazada Kontrol Et")
                    token_t4 = st.session_state.pcloud_token
                    host_t4 = st.session_state.get("pcloud_host", "https://api.pcloud.com")

                    with st.spinner("Mağazalar yükleniyor..."):
                        _, magazalar = _magazalari_otomatik_bul(token_t4, host_t4)

                    mag_root_id = st.session_state.get("magazalar_root_id")
                    if mag_root_id and not magazalar:
                        with st.spinner("Manuel köke bakılıyor..."):
                            _, magazalar = _klasorleri_getir(token_t4, host_t4, mag_root_id)

                    if not magazalar:
                        st.warning("Mağaza klasörleri bulunamadı.")
                        st.caption("Tab 1'de 01-VİNTAGE RUG klasörüne gidin → **📌** butonuna basın.")
                    else:
                        _mt4c1, _mt4c2 = st.columns([5, 1])
                        secilen_magaza_adi = _mt4c1.selectbox(
                            "Mağaza seç",
                            options=[m["ad"] for m in magazalar],
                            index=None,
                            placeholder="Bir mağaza seçin...",
                            key="magaza_sec",
                        )
                        magaza_ara_btn = _mt4c2.button(
                            "🔍 Ara",
                            key="magaza_ara_btn",
                            type="primary",
                            width="stretch",
                            disabled=not secilen_magaza_adi,
                        )

                        if magaza_ara_btn and secilen_magaza_adi:
                            magaza_id = next(m["id"] for m in magazalar if m["ad"] == secilen_magaza_adi)
                            with st.spinner(f"{secilen_magaza_adi} taranıyor..."):
                                magaza_kodlar = _magaza_tum_kodlar(token_t4, host_t4, magaza_id)

                            if not magaza_kodlar:
                                st.warning(f"{secilen_magaza_adi} içinde ürün bulunamadı.")
                            else:
                                kontrol = [
                                    {**e, "Mağaza Durumu": "✅ Var" if _kod_normalize(e["KOD"]) in magaza_kodlar else "❌ Yok"}
                                    for e in eslesmeler
                                ]
                                var_sayisi = sum(1 for s in kontrol if "✅" in s["Mağaza Durumu"])
                                st.success(f"**{secilen_magaza_adi}**: {var_sayisi}/{len(kontrol)} ürün mevcut")
                                st.dataframe(
                                    pd.DataFrame(kontrol),
                                    width="stretch",
                                    hide_index=True,
                                )
        elif ara_btn:
            st.warning("Eşleşen ürün bulunamadı.")

    with st.container(key="main_tab_content_olcu_ara"):
        _tab5_ara()


# ══ TAB 6 ════════════════════════════════════════════════════════════════════
if st.session_state.active_main_tab == "notlar":
    def _tab6_notlar():
        st.markdown("#### Satılan Ürün Notları")
        st.caption("SATILANLAR tabındaki ürünler ile mağaza envanteri eşleştirilir. Sadece `green` olan ürünler mağazada yüklü kabul edilir.")
        st.caption("Bu tab üstte seçilen `Hedef Mağaza` filtresinden bağımsız çalışır; tüm mağazalar birlikte kontrol edilir.")

        _n1, _n2, _n3 = st.columns([2, 1, 4])
        zorla_yenile = _n1.button("🔄 Envanteri Yenile", width="stretch")
        okunmamis_goster = _n2.toggle("Sadece okunmamış", value=False)
        if zorla_yenile:
            _tab_loading_gostergesi(
                "Notlar",
                50,
                "Satılan kodlar ile mağaza envanteri yeniden eşleştiriliyor.",
                ready=False,
            )

        notlar_db, envanter, satilanlar = _satilan_notlarini_uret(force_refresh=zorla_yenile)
        notes = list((notlar_db.get("notes") or {}).values())
        notes = sorted(
            notes,
            key=lambda n: (
                0 if n.get("status") != "read" else 1,
                n.get("urun_kodu", ""),
            )
        )
        if okunmamis_goster:
            notes = [n for n in notes if n.get("status") != "read"]

        yuklu_magaza_sayisi = sum(len(n.get("stores") or []) for n in notes)
        okunmamis = sum(1 for n in notes if n.get("status") != "read")
        hatali_magazalar = len((envanter.get("errors") or {}))

        _m1, _m2, _m3, _m4 = st.columns(4)
        _m1.metric("Satılan kod", len(satilanlar))
        _m2.metric("Silinmeli notu", len(notes))
        _m3.metric("Okunmamış", okunmamis)
        _m4.metric("Yüklü mağaza", yuklu_magaza_sayisi)

        if hatali_magazalar:
            st.caption(f"⚠️ {hatali_magazalar} mağazanın envanteri bu turda okunamadı. Son başarılı yerel cache kullanılıyor olabilir.")

        if not notes:
            st.success("Silinmesi gereken yüklü ürün notu yok.")
            return

        st.warning("SATILANLAR listesinde olan ve mağazada `green` görünen ürünler silinmelidir.")

        try:
            import pandas as pd
            satirlar = []
            for note in notes:
                magaza_adlari = ", ".join(s["store_name"] for s in note.get("stores", []))
                note_status = note.get("status")
                satirlar.append({
                    "durum": "silindi" if note_status == "deleted" else ("okundu" if note_status == "read" else "okunmamis"),
                    "urun_kodu": note.get("urun_kodu", ""),
                    "silinecek_magazalar": magaza_adlari,
                    "magaza_sayisi": len(note.get("stores") or []),
                    "not": note.get("mesaj", ""),
                    "note_key": note.get("note_key", ""),
                })

            df_notes = pd.DataFrame(satirlar)
            goster = [c for c in ["durum", "urun_kodu", "silinecek_magazalar", "magaza_sayisi", "not"] if c in df_notes.columns]
            secim = st.dataframe(
                df_notes[goster],
                width="stretch",
                hide_index=True,
                on_select="rerun",
                selection_mode="multi-row",
            )

            secilen_indexler = secim.selection.rows if secim.selection else []
            if secilen_indexler:
                secilen_keyler = df_notes.iloc[secilen_indexler]["note_key"].tolist()
                _a1, _a2, _a3, _a4 = st.columns([2, 2, 2, 4])
                if _a1.button("✅ Okundu işaretle", type="primary", width="stretch"):
                    for note_key in secilen_keyler:
                        _not_status_guncelle(note_key, "read")
                    st.rerun()
                if _a2.button("↩ Okunmadı yap", width="stretch"):
                    for note_key in secilen_keyler:
                        _not_status_guncelle(note_key, "unread")
                    st.rerun()
                if _a3.button("🔴 Silindi işaretle", width="stretch"):
                    guncellenen, hatalar = _notlari_silindi_isaretle(secilen_keyler)
                    if hatalar:
                        st.error(" ; ".join(hatalar))
                    else:
                        st.success(f"{guncellenen} mağaza kaydı kırmızı olarak işaretlendi.")
                    st.rerun()

            with st.expander("Detaylı mağaza eşleşmeleri", expanded=False):
                for note in notes:
                    if note.get("status") == "deleted":
                        durum_ikon = "🔴"
                    elif note.get("status") != "read":
                        durum_ikon = "🟠"
                    else:
                        durum_ikon = "✅"
                    st.markdown(f"**{durum_ikon} {note.get('urun_kodu', '')}**")
                    silinecek_magazalar = ", ".join(
                        f"`{(store.get('store_name') or store.get('store_id', '')).upper()}`"
                        for store in note.get("stores", [])
                    )
                    st.markdown(
                        f"<span style='color:#fca5a5;font-weight:700;'>Silinecek mağazalar:</span> {silinecek_magazalar}",
                        unsafe_allow_html=True,
                    )
                    for store in note.get("stores", []):
                        st.caption(
                            f"{store.get('store_name', store.get('store_id', ''))}  |  "
                            f"urun_id: {store.get('urun_id', '')}  |  "
                            f"status: {store.get('status', '')}"
                        )
        except Exception as exc:
            st.error(f"Notlar tabı hazırlanamadı: {exc}")

    with st.container(key="main_tab_content_notlar"):
        _tab6_notlar()
