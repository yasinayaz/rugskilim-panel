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


def _urun_sec_rozet_cache_yolu(store_id: str) -> Path:
    temiz = str(store_id or "").strip() or "default"
    return _RUNTIME_DIR / f"urun_sec_badges__{temiz}.json"


def _urun_sec_sheet_imza_yolu(store_id: str) -> Path:
    temiz = str(store_id or "").strip() or "default"
    return _RUNTIME_DIR / f"urun_sec_badges_sig__{temiz}.json"


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


def _template_config_key(template_id: str) -> str:
    return f"TEMPLATE_JSON__{str(template_id or '').strip()}"


def _template_json_oku(template_id: str) -> dict:
    try:
        from shared.sheets import config_oku as _config_oku

        raw = str((_config_oku() or {}).get(_template_config_key(template_id), "") or "").strip()
        if raw:
            return json.loads(raw)
    except Exception:
        pass

    _tmpl_path = _template_yolu(template_id)
    if _tmpl_path.exists():
        try:
            return json.loads(_tmpl_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _template_session_overlay(template_cfg: dict, store_id: str, store_name: str = "") -> tuple[dict, str]:
    cfg = json.loads(json.dumps(template_cfg or {}, ensure_ascii=False)) if template_cfg else {}
    source = "saved_template"
    draft_description = str(st.session_state.get(f"editor_{store_id}_description_example_template", "") or "").strip()
    draft_description_brief = str(st.session_state.get(f"editor_{store_id}_description_brief", "") or "")
    if draft_description or draft_description_brief:
        cfg.setdefault("prompt_rules", {})
        if draft_description:
            cfg["prompt_rules"]["description_example_template"] = draft_description
        cfg["prompt_rules"]["description_brief"] = draft_description_brief
        cfg["template_id"] = cfg.get("template_id") or store_id
        cfg["template_name"] = cfg.get("template_name") or store_name or store_id
        source = "session_draft"
    return cfg, source


def _template_json_kaydet(template_id: str, payload: dict) -> tuple:
    """Template'i JSON dosyasına ve Sheets config'e kaydeder.
    Döndürür: (Path, sheets_ok: bool, sheets_hata: str)
    """
    _tmpl_path = _template_yolu(template_id)
    _text = json.dumps(payload, ensure_ascii=False, indent=2)
    _tmpl_path.write_text(_text, encoding="utf-8")
    _sheets_ok = False
    _sheets_hata = ""
    try:
        from shared.sheets import config_yaz as _config_yaz
        _config_yaz(_template_config_key(template_id), _text)
        _sheets_ok = True
    except Exception as _e:
        _sheets_hata = str(_e)
    return _tmpl_path, _sheets_ok, _sheets_hata


@st.cache_data(show_spinner=False, ttl=30)
def _sheet_baglanti_durumu(store_id: str, google_sheet_id: str, sheet_tab: str):
    """Magazanin hedef Google Sheet/sekmesine erisilebiliyor mu kontrol eder."""
    hedef_sheet_id = str(google_sheet_id or os.environ.get("GOOGLE_SHEET_ID", "")).strip()
    hedef_tab = str(sheet_tab or store_id).strip()

    if not hedef_sheet_id:
        return {
            "ok": False,
            "reason": "Google Sheet ID tanimli degil",
        }

    try:
        from shared.sheets import _spreadsheet as _spreadsheet_fn

        spreadsheet = _spreadsheet_fn(hedef_sheet_id)
        worksheetler = spreadsheet.worksheets()
        basliklar = [str(ws.title).strip() for ws in worksheetler]

        if hedef_tab in basliklar:
            return {
                "ok": True,
                "reason": f"'{hedef_tab}' sekmesine bagli",
            }

        if any(str(ad).lower() == hedef_tab.lower() for ad in basliklar):
            return {
                "ok": True,
                "reason": f"'{hedef_tab}' sekmesi buyuk/kucuk harf farkiyla bulundu",
            }

        return {
            "ok": False,
            "reason": f"'{hedef_tab}' sekmesi sheet icinde yok",
        }
    except Exception as exc:
        return {
            "ok": False,
            "reason": f"Sheet baglantisi kurulamadı: {type(exc).__name__}: {exc}",
        }


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
.stButton > button *,
[data-testid="stButton"] > button * {
  color: var(--text-1) !important;
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

.urun-sec-status {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 46px;
  font-size: 1rem;
  text-align: center;
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
    ("_olcu_magaza_klasor_haritasi", {}), ("_olcu_magaza_kontrol_sonucu", []),
    ("kuyruk_yuklendi", False), ("stok_indiriliyor", False),
    ("stok_indir_hata", None), ("_cikis_yapildi", False),
    ("magaza_id", None), ("magaza_ad", None),
    ("klasor_ad", None),
    ("hedef_magaza_id", "PatchArts"), ("kuyruk_magaza_id", None), ("ayar_magaza_id", None),
    ("tum_magaza_sekmeleri_hazir", False),
    ("urun_formu_acik", False),
    ("satilan_urun_formu_acik", False),
    ("_urunler_pending_refresh", False),
    ("urun_alt_tab", "liste"),
    ("_kuyruk_loading_ui", False),
    ("_kuyruk_refresh_istek", False),
    ("_secim_limit_hatasi", None),
    ("_kaldirilacak_secim_id", None),
    ("_urun_katalog_cache", None),
    ("_urun_katalog_cache_ts", 0.0),
    ("_urun_katalog_cache_stok_mtime", 0.0),
    ("_urun_katalog_cache_refresh_started_at", 0.0),
    ("_urun_katalog_bekleyen_override", {}),
    ("_urunler_magaza_refresh_started_at", 0.0),
    ("_urunler_seen_sync_version", ""),
    ("_urunler_pending_sync_version", ""),
    ("_urunler_last_auto_sync_request_ts", 0.0),
    ("_urunler_last_sheet_sync_request_ts", 0.0),
    ("_urunler_last_sheet_signature", ""),
    ("_urun_edit_dialog_acik", False),
    ("_urun_sec_badge_refresh_started_at", 0.0),
    ("_urun_sec_badge_refresh_store_id", ""),
    ("_urun_sec_badge_cache_seen_ts", 0.0),
    ("_urun_sec_sig_check_started_at", 0.0),
    ("_urun_sec_sig_check_store_id", ""),
    ("active_main_tab", "urun_sec"),
    ("_pending_main_tab_render", None),
    ("_pending_urunler_alt_tab_render", None),
    ("_suppress_tab_autorefresh_once", False),
]:
    if k not in st.session_state:
        st.session_state[k] = v

if not st.session_state.pcloud_token and not st.session_state.get("_cikis_yapildi"):
    _tok = os.environ.get("PCLOUD_TOKEN", "")
    if _tok:
        st.session_state.pcloud_token = _tok
        st.session_state.setdefault("pcloud_host", "https://api.pcloud.com")

def _pcloud_token_dogrula(token):
    """Token'ı her iki pCloud host'unda dener; (çalışan_host, None) veya (None, hata) döner."""
    son_hata = "Bağlantı hatası"
    for h in ["https://api.pcloud.com", "https://eapi.pcloud.com"]:
        try:
            r = httpx.get(f"{h}/userinfo", params={"auth": token}, timeout=15)
            d = r.json()
            if d.get("result") == 0:
                return h, None
            son_hata = d.get("error", "Hata")
        except Exception as e:
            son_hata = str(e)
    return None, son_hata

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
                with st.spinner("Token doğrulanıyor..."):
                    _dogru_host, _tok_hata = _pcloud_token_dogrula(_tok_input.strip())
                if not _dogru_host:
                    st.error(f"❌ Token doğrulanamadı: {_tok_hata}")
                else:
                    st.session_state.pcloud_token = _tok_input.strip()
                    st.session_state["pcloud_host"] = _dogru_host
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
_CANLI_HARITA_DB = _RUNTIME_DIR / "canli_magaza_haritasi.json"
_CANLI_HARITA_TTL_SN = 60
_CANLI_HARITA_LOCK = _threading.Lock()
_STORE_BG_SYNC_GUARD = _threading.Lock()
_STORE_BG_SYNC_LOCKS: dict[str, _threading.Lock] = {}
_STORE_STATUS_BG_SYNC_LOCK = _threading.Lock()
_STORE_STATUS_BG_SYNC_TS = 0.0
_STORE_BG_SYNC_TS: dict[str, float] = {}

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


def _urunler_kullanici_mesgul_mu() -> bool:
    """
    Sessiz veri yenileme aktif kullanicinin formunu veya dialogunu bozmamali.
    """
    return bool(
        st.session_state.get("urun_formu_acik")
        or st.session_state.get("satilan_urun_formu_acik")
        or st.session_state.get("_urun_edit_dialog_acik")
        or st.session_state.get("_edit_urun")
        or st.session_state.get("_sil_onay")
    )


def _urunler_sync_versiyonu_al() -> str:
    envanter_ts = float((_envanter_cache_dosyadan_yukle() or {}).get("updated_at") or 0.0)
    harita_ts = float((_canli_magaza_haritasi_dosyadan_yukle() or {}).get("updated_at") or 0.0)
    return f"{envanter_ts:.6f}|{harita_ts:.6f}"


def _urunler_sheet_degisim_imzasi_al() -> str:
    try:
        from shared.sheets import drive_file_degisim_imzasi
        from shared.store_manager import tum_magazalar as _tum_magazalar_imza

        varsayilan_sheet_id = str(os.environ.get("GOOGLE_SHEET_ID", "")).strip()
        sheet_ids = sorted({
            str(m.get("google_sheet_id") or varsayilan_sheet_id).strip()
            for m in _tum_magazalar_imza()
            if str(m.get("google_sheet_id") or varsayilan_sheet_id).strip()
        })
        if not sheet_ids:
            return ""
        return "||".join(drive_file_degisim_imzasi(sheet_id) for sheet_id in sheet_ids)
    except Exception:
        return ""


def _urunler_sync_degisikligini_uygula() -> bool:
    """
    Arka plan sync tamamlandiginda sadece veri cache'ini yeniler.
    Kullanici aktif islemdeyse apply ertelenir; session state korunur.
    """
    mevcut_versiyon = _urunler_sync_versiyonu_al()
    gorulen_versiyon = str(st.session_state.get("_urunler_seen_sync_version") or "").strip()
    bekleyen_versiyon = str(st.session_state.get("_urunler_pending_sync_version") or "").strip()

    if not gorulen_versiyon:
        st.session_state["_urunler_seen_sync_version"] = mevcut_versiyon
        if bekleyen_versiyon == mevcut_versiyon:
            st.session_state["_urunler_pending_sync_version"] = ""
        return False

    hedef_versiyon = bekleyen_versiyon or mevcut_versiyon
    if hedef_versiyon == gorulen_versiyon:
        if bekleyen_versiyon:
            st.session_state["_urunler_pending_sync_version"] = ""
        return False

    if _urunler_kullanici_mesgul_mu():
        st.session_state["_urunler_pending_sync_version"] = mevcut_versiyon
        return False

    st.session_state["_urunler_seen_sync_version"] = mevcut_versiyon
    st.session_state["_urunler_pending_sync_version"] = ""
    # Arka plan senkronu kullaniciya gorunmeden toplansin.
    # Yeni veri bir sonraki dogal rerun'da uygulanir; tam sayfa yenileme yapilmaz.
    st.session_state["_urunler_loading_ui"] = False
    st.session_state["_urunler_pending_refresh"] = True
    return False


def _urunler_sessiz_sync_nabzi():
    """
    Urunler ekranindayken belirli araliklarla sheet -> runtime cache sync tetikler.
    Baska bir kullanicinin yaptigi degisiklikler arkada toplanir; apply yalnizca uygun anda olur.
    """
    if st.session_state.get("active_main_tab") != "urunler":
        return

    _aktif_magaza = str(st.session_state.get("hedef_magaza_id") or "").strip()
    if _aktif_magaza:
        _magaza_hizli_arka_plan_sync_baslat(_aktif_magaza, force=False)

    try:
        from shared.store_manager import tum_magazalar as _tum_magazalar_sync

        store_ids = [
            str(m.get("store_id") or "").strip()
            for m in _tum_magazalar_sync()
            if str(m.get("store_id") or "").strip()
        ]
    except Exception:
        store_ids = []

    simdi = _time.time()
    son_istek = float(st.session_state.get("_urunler_last_auto_sync_request_ts") or 0.0)
    if (simdi - son_istek) >= 30:
        st.session_state["_urunler_last_auto_sync_request_ts"] = simdi
        yeni_imza = _urunler_sheet_degisim_imzasi_al()
        son_imza = str(st.session_state.get("_urunler_last_sheet_signature") or "").strip()
        if store_ids:
            _store_status_auto_sync_all_stores_async(store_ids, force=False)
        if yeni_imza:
            if not son_imza:
                st.session_state["_urunler_last_sheet_signature"] = yeni_imza
            elif yeni_imza != son_imza:
                st.session_state["_urunler_last_sheet_signature"] = yeni_imza
                _urunler_magaza_yenilemesini_baslat(force=False)
                if store_ids:
                    _canli_magaza_haritasi_bg_guncelle(store_ids)

    _urunler_sync_degisikligini_uygula()


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


def _kargo_para_str(value) -> str:
    """Kargo tutarini Sheet/Supabase icin sade string'e cevir. 0/boş -> ''."""
    num = _float_or_none(value)
    if not num:
        return ""
    return f"{num:.2f}".rstrip("0").rstrip(".")


_TR_AYLAR = [
    "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
    "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık",
]


def _satilan_ay_etiketi(sold_at) -> str:
    """Satış tarihinden '<yıl> <ay>' etiketi (Sheet'teki aylık ayraçla aynı biçim)."""
    raw = str(sold_at or "").strip()
    if raw:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(raw, fmt)
                return f"{dt.year} {_TR_AYLAR[dt.month - 1]}"
            except Exception:
                pass
    return "Tarih Yok"


def _satilan_stoga_geri_al(urun: dict):
    """Satılan ürünü tekrar stoğa (active) al; satış/müşteri/kargo alanlarını temizle.

    Supabase + panel cache + ürün Sheet'i (Satılanlar tabından düşer) paralel güncellenir."""
    kod = str((urun or {}).get("product_code") or "").strip()
    if not kod:
        return
    guncel = dict(urun)
    guncel["status"] = "active"
    for _alan in (
        "sold_at", "sold_site", "customer_name", "customer_phone",
        "customer_address", "customer_contact_country",
        "shipping_carrier", "shipping_cost_try", "shipping_cost_usd",
    ):
        guncel[_alan] = ""
    guncel["updated_at"] = _time.strftime("%Y-%m-%d %H:%M")
    _urunleri_cachede_uste_tut(guncel)
    _bekleyen_urun_override_kaydet(guncel)
    _urun_guncelle_arkaplanda(guncel)


def _satilan_edit_dialog(urun: dict):
    """Satılan ürün düzenleme + kalıcı silme (aktif ürün edit senaryosunun satış karşılığı)."""
    import time as _t

    kod0 = str((urun or {}).get("product_code") or "").strip()
    st.markdown(f"##### ✏️ Satılan ürün düzenle — **{kod0}**")

    try:
        from shared.store_manager import tum_magazalar as _tm
        _site_ops = [
            str(m.get("store_name") or m.get("store_id") or "").strip()
            for m in _tm()
            if str(m.get("store_name") or m.get("store_id") or "").strip()
        ]
    except Exception:
        _site_ops = []
    _mevcut_siteler = [p.strip() for p in str(urun.get("sold_site", "")).split(",") if p.strip()]
    for _s in _mevcut_siteler:
        if _s not in _site_ops:
            _site_ops.append(_s)

    _c1, _c2, _c3 = st.columns(3)
    _e_site = _c1.multiselect("Satılan site", options=_site_ops, default=_mevcut_siteler)
    _e_musteri = _c2.text_input("Müşteri adı", value=urun.get("customer_name", ""))
    _e_tarih = _c3.text_input("Satılan tarih", value=urun.get("sold_at", ""))
    _c4, _c5 = st.columns(2)
    _e_tel = _c4.text_input("Telefon", value=urun.get("customer_phone", ""))
    _e_ulke = _c5.text_input("İletişim & ülke", value=urun.get("customer_contact_country", ""))
    _k1, _k2, _k3 = st.columns(3)
    _carriers = ["FEDEX", "UPS"]
    _cur_carrier = str(urun.get("shipping_carrier", "")).strip().upper()
    _carrier_index = _carriers.index(_cur_carrier) if _cur_carrier in _carriers else None
    _e_kargo = _k1.selectbox(
        "Kargo firması", options=_carriers, index=_carrier_index, placeholder="Seçin (opsiyonel)..."
    )
    _e_ktl = _k2.number_input(
        "Kargo (TL)", min_value=0.0, step=1.0, format="%.2f",
        value=_float_or_none(urun.get("shipping_cost_try")) or 0.0,
    )
    _e_kusd = _k3.number_input(
        "Kargo (USD)", min_value=0.0, step=1.0, format="%.2f",
        value=_float_or_none(urun.get("shipping_cost_usd")) or 0.0,
    )
    _e_adres = st.text_area("Adres", value=urun.get("customer_address", ""), height=90)
    _e_not = st.text_input("Not", value=urun.get("note", ""))

    _b1, _b2, _b3 = st.columns([2, 1.4, 1])
    if _b1.button("Kaydet", type="primary", use_container_width=True, key="satilan_edit_kaydet"):
        if not _e_site:
            st.error("Satılan site zorunlu.")
            return
        guncel = dict(urun)
        guncel["status"] = "sold"
        guncel["sold_site"] = ", ".join(_e_site)
        guncel["customer_name"] = _e_musteri.strip()
        guncel["sold_at"] = _e_tarih.strip() or urun.get("sold_at", "")
        guncel["customer_phone"] = _e_tel.strip()
        guncel["customer_contact_country"] = _e_ulke.strip()
        guncel["customer_address"] = _e_adres.strip()
        guncel["shipping_carrier"] = (_e_kargo or "").strip()
        guncel["shipping_cost_try"] = _kargo_para_str(_e_ktl)
        guncel["shipping_cost_usd"] = _kargo_para_str(_e_kusd)
        guncel["note"] = _e_not.strip()
        guncel["updated_at"] = _t.strftime("%Y-%m-%d %H:%M")
        _urunleri_cachede_uste_tut(guncel)
        _bekleyen_urun_override_kaydet(guncel)
        _urun_guncelle_arkaplanda(guncel)
        st.session_state["_edit_satilan"] = None
        st.session_state.pop("_satilan_sil_onay", None)
        st.success("Kaydedildi. Kalıcı kayıt arka planda tamamlanıyor.")
        st.rerun()
    if _b2.button("İptal", use_container_width=True, key="satilan_edit_iptal"):
        st.session_state["_edit_satilan"] = None
        st.session_state.pop("_satilan_sil_onay", None)
        st.rerun()

    st.divider()
    if not st.session_state.get("_satilan_sil_onay"):
        if _b3.button("🗑️ Sil", use_container_width=True, key="satilan_edit_sil"):
            st.session_state["_satilan_sil_onay"] = True
            st.rerun()
    else:
        st.warning(f"**{kod0}** kalıcı silinecek (satılanlardan da çıkar). Emin misiniz?")
        _d1, _d2 = st.columns(2)
        if _d1.button("Evet, sil", type="primary", use_container_width=True, key="satilan_sil_evet"):
            try:
                _silinen_urune_ekle(kod0)
                mevcut = [
                    item
                    for item in (st.session_state.get("_urun_katalog_cache") or [])
                    if str(item.get("product_code") or "").strip() != kod0
                ]
                st.session_state["_urun_katalog_cache"] = [dict(i) for i in mevcut]
                st.session_state["_urun_katalog_cache_ts"] = _time.time()
                st.session_state["_urun_katalog_cache_stok_mtime"] = 0.0
                _urun_sil_arkaplanda(kod0, mevcut_snapshot=mevcut)
                st.session_state.pop("_satilan_sil_onay", None)
                st.session_state["_edit_satilan"] = None
                st.rerun()
            except Exception as exc:
                st.error(f"{kod0} silinemedi: {exc}")
        if _d2.button("Vazgeç", use_container_width=True, key="satilan_sil_vazgec"):
            st.session_state.pop("_satilan_sil_onay", None)
            st.rerun()


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

    satilanlar = set(satilan_kayitlari)
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
    from shared.product_sheet import ProductSheet

    if not _supabase_ready():
        return False

    kaynak = kaynak_urunler or ProductSheet().read_products()
    kaynak = _silinenleri_filtrele(kaynak)
    kaynak_fingerprint = hash(tuple(
        (
            str(item.get("product_code") or "").strip(),
            str(item.get("status") or "").strip(),
            str(item.get("size_cm") or "").strip(),
            str(item.get("size_ft") or "").strip(),
            str(item.get("sold_at") or "").strip(),
            str(item.get("sold_site") or "").strip(),
            str(item.get("updated_at") or "").strip(),
        )
        for item in kaynak
    ))
    sync_bilgi = _urun_kaynak_sync_bilgisi()
    if not force and sync_bilgi.get("sheet_fingerprint") == kaynak_fingerprint:
        return False

    ProductCatalog().replace_from_source(kaynak)
    _json_kaydet(
        _PRODUCT_SOURCE_SYNC_DB,
        {
            "sheet_fingerprint": kaynak_fingerprint,
            "updated_at": _time.time(),
            "source_count": len(kaynak),
        },
    )
    return True


def _urunleri_yukle(
    force_source_sync: bool = False,
    force_store_refresh: bool = False,
    _ignore_cache: bool = False,
):
    from shared.product_catalog import ProductCatalog, _supabase_ready
    from shared.product_sheet import ProductSheet

    def _kaynak_oku() -> list[dict]:
        if _supabase_ready():
            _force_env = force_store_refresh
            _aktif_magaza = str(st.session_state.get("hedef_magaza_id") or "").strip()

            def _envanter_sync_job():
                try:
                    hedefler = [_aktif_magaza] if _aktif_magaza else None
                    _magaza_envanterini_topla(force=_force_env, store_ids=hedefler)
                except Exception:
                    pass

            _threading.Thread(target=_envanter_sync_job, daemon=True, name="magaza-envanter-sync").start()
            if _aktif_magaza:
                _magaza_hizli_arka_plan_sync_baslat(_aktif_magaza, force=force_store_refresh)

        try:
            mevcut_liste = ProductCatalog().list_products() if _supabase_ready() else ProductSheet().read_products()
        except Exception:
            mevcut_liste = _panel_urunleri_yerden_yukle()

        mevcut_liste = _silinenleri_filtrele(mevcut_liste)
        mevcut_liste = _bekleyen_urun_override_uygula(mevcut_liste)
        _satilan_kodlarini_oturumda_guncelle(mevcut_liste)
        st.session_state["_urun_katalog_cache"] = [dict(item) for item in mevcut_liste]
        st.session_state["_urun_katalog_cache_ts"] = _time.time()
        st.session_state["_urun_katalog_cache_stok_mtime"] = 0.0
        st.session_state["_urun_katalog_cache_refresh_started_at"] = 0.0
        _disk_snap = [dict(item) for item in mevcut_liste]
        def _disk_warmup_job():
            try:
                _json_kaydet(_RUNTIME_DIR / "panel_products.json", _disk_snap)
            except Exception:
                pass
        _threading.Thread(target=_disk_warmup_job, daemon=True, name="disk-warmup").start()
        return mevcut_liste

    cache_ts = float(st.session_state.get("_urun_katalog_cache_ts") or 0.0)
    cache_data = st.session_state.get("_urun_katalog_cache")
    cache_var = cache_data is not None
    cache_taze = cache_var and (_time.time() - cache_ts) <= 300

    if cache_var and not _ignore_cache and not force_source_sync and not force_store_refresh:
        if not cache_taze:
            _urunler_cache_yenilemesini_baslat(
                force_source_sync=True,
                force_store_refresh=False,
            )
        return [dict(item) for item in cache_data]

    if cache_var and not _ignore_cache and (force_source_sync or force_store_refresh):
        if force_store_refresh:
            _urunler_magaza_yenilemesini_baslat(force=True)
        _urunler_cache_yenilemesini_baslat(
            force_source_sync=True,
            force_store_refresh=False,
            min_interval_seconds=20,
        )
        return [dict(item) for item in cache_data]

    return _kaynak_oku()


def _urun_sheet_sync_arkaplanda(force: bool = True, products: list | None = None):
    _products_snap = [dict(u) for u in products] if products is not None else None

    def _job():
        try:
            from shared.product_sheet_sync import sync_product_sheet
            sync_product_sheet(force=force, products=_products_snap)
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
    _satilan_kodlarini_oturumda_guncelle(products)
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

    st.session_state["_urun_katalog_cache"] = [dict(item) for item in yeni_liste]
    st.session_state["_urun_katalog_cache_ts"] = 0.0 if mevcut_cache is None else _time.time()
    st.session_state["_urun_katalog_cache_stok_mtime"] = 0.0
    _satilan_kodlarini_oturumda_guncelle(yeni_liste)


def _urun_override_eslesti(mevcut: dict | None, override: dict | None) -> bool:
    if not mevcut or not override:
        return False
    alanlar = (
        "status",
        "sold_at",
        "sold_site",
        "customer_name",
        "customer_phone",
        "customer_address",
        "customer_contact_country",
        "note",
    )
    for alan in alanlar:
        if str(mevcut.get(alan) or "").strip() != str(override.get(alan) or "").strip():
            return False
    return True


def _bekleyen_urun_override_kaydet(urun: dict, *, ttl_seconds: int = 180):
    kod = str((urun or {}).get("product_code") or "").strip()
    if not kod:
        return
    overrides = dict(st.session_state.get("_urun_katalog_bekleyen_override") or {})
    overrides[kod] = {
        "product": dict(urun),
        "expires_at": _time.time() + max(30, int(ttl_seconds)),
    }
    st.session_state["_urun_katalog_bekleyen_override"] = overrides


def _bekleyen_urun_override_uygula(products: list[dict]) -> list[dict]:
    overrides = dict(st.session_state.get("_urun_katalog_bekleyen_override") or {})
    if not overrides:
        return products

    simdi = _time.time()
    kalan_overrides = {}
    kaynak = [dict(item) for item in (products or [])]
    index_map = {
        str(item.get("product_code") or "").strip(): idx
        for idx, item in enumerate(kaynak)
        if str(item.get("product_code") or "").strip()
    }

    for kod, kayit in overrides.items():
        if not kod:
            continue
        expires_at = float((kayit or {}).get("expires_at") or 0.0)
        if expires_at <= simdi:
            continue
        override = dict((kayit or {}).get("product") or {})
        mevcut_idx = index_map.get(kod)
        mevcut = kaynak[mevcut_idx] if mevcut_idx is not None else None
        if _urun_override_eslesti(mevcut, override):
            continue
        kalan_overrides[kod] = {
            "product": dict(override),
            "expires_at": expires_at,
        }
        birlesik = {**(mevcut or {}), **override}
        if mevcut_idx is None:
            kaynak.insert(0, birlesik)
            index_map = {
                str(item.get("product_code") or "").strip(): idx
                for idx, item in enumerate(kaynak)
                if str(item.get("product_code") or "").strip()
            }
        else:
            kaynak[mevcut_idx] = birlesik

    st.session_state["_urun_katalog_bekleyen_override"] = kalan_overrides
    return kaynak


def _urunleri_kaydet_arkaplanda(products: list[dict], *, incremental: bool = False, sync_sheet: bool = True, disk_snapshot: list[dict] | None = None):
    payload = [dict(item) for item in (products or [])]
    _disk_snap = [dict(item) for item in disk_snapshot] if disk_snapshot is not None else None

    def _job():
        from shared.product_catalog import ProductCatalog, _supabase_ready

        try:
            if _supabase_ready():
                ProductCatalog().upsert_products(payload)
                if _disk_snap is not None:
                    _json_kaydet(_RUNTIME_DIR / "panel_products.json", _disk_snap)
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


def _urun_sil_arkaplanda(kod: str, mevcut_snapshot: list[dict] | None = None):
    silinecek_kod = str(kod or "").strip()
    _disk_snap = [dict(item) for item in mevcut_snapshot] if mevcut_snapshot is not None else None

    def _job():
        from shared.product_catalog import ProductCatalog as _PC_DEL, _supabase_ready as _supabase_ready_del

        try:
            if _supabase_ready_del():
                _store_delete_kuyruguna_ekle([silinecek_kod], reason="deleted")
                _PC_DEL().delete_products([silinecek_kod])
                if _disk_snap is not None:
                    _json_kaydet(_RUNTIME_DIR / "panel_products.json", _disk_snap)
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
            cache = _magaza_envanterini_topla(force=force)
            tum_store_ids = sorted({
                str(store_id or "").strip()
                for store_id in (((cache or {}).get("stores") or {}).keys())
                if str(store_id or "").strip()
            })
            envanter_haritasi = _envanter_cacheden_canli_magaza_haritasi(tum_store_ids, cache)
            if envanter_haritasi:
                _json_kaydet(_CANLI_HARITA_DB, {
                    "updated_at": _time.time(),
                    "data": {
                        kod: sorted(magazalar)
                        for kod, magazalar in sorted(envanter_haritasi.items())
                    },
                    "store_ids": tum_store_ids,
                    "source": "store-inventory-refresh",
                })
        except Exception:
            pass

    _threading.Thread(target=_job, daemon=True, name="urunler-magaza-refresh").start()


def _urunler_cache_yenilemesini_baslat(
    *,
    force_source_sync: bool = False,
    force_store_refresh: bool = False,
    min_interval_seconds: int = 20,
) -> bool:
    simdi = _time.time()
    son_baslangic = float(st.session_state.get("_urun_katalog_cache_refresh_started_at") or 0.0)
    if son_baslangic and (simdi - son_baslangic) < max(3, int(min_interval_seconds)):
        return False

    st.session_state["_urun_katalog_cache_refresh_started_at"] = simdi

    def _job():
        try:
            _urunleri_yukle(
                force_source_sync=force_source_sync,
                force_store_refresh=force_store_refresh,
                _ignore_cache=True,
            )
        except Exception:
            pass

    _threading.Thread(target=_job, daemon=True, name="urunler-katalog-refresh").start()
    return True


def _urunler_alt_tab_sec(tab_id: str):
    yeni_tab = str(tab_id or "").strip()
    if not yeni_tab or st.session_state.get("urun_alt_tab") == yeni_tab:
        return

    _overlay_state_temizle()
    st.session_state.urun_alt_tab = yeni_tab
    st.session_state["_pending_urunler_alt_tab_render"] = None

    if yeni_tab != "liste":
        st.session_state.urun_formu_acik = False
    if yeni_tab != "satilan":
        st.session_state.satilan_urun_formu_acik = False

    st.session_state["_urunler_loading_ui"] = False


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


def _magaza_kaydi_fiziksel_yuklu_mu(renk: str | None = None, durum: str | None = None) -> bool:
    renk_norm = str(renk or "").strip().lower()
    durum_norm = str(durum or "").strip().lower()
    if renk_norm in {"red", "yellow"}:
        return False
    return renk_norm == "green" or durum_norm == "done"


def _magaza_kaydi_ui_yuklu_mu(kod: str, renk: str | None = None, durum: str | None = None) -> bool:
    norm_kod = _urun_kodu_normalize(kod) or _urun_kodu_al(kod)
    if norm_kod and norm_kod in _satilan_kodlar_kumesi():
        return False
    return _magaza_kaydi_fiziksel_yuklu_mu(renk, durum)


@st.cache_data(ttl=90, show_spinner=False)
def _magaza_kuyruk_yuklu_sayisi_cached(store_id: str) -> int:
    from shared.product_catalog import _supabase_ready
    from shared.sheets import SheetsKatmani as _SK_QUEUE_COUNT

    store_id = str(store_id or "").strip()
    if not store_id:
        return 0

    satirlar = _kuyruk_satirlari_cached(store_id)
    if not satirlar:
        return 0

    _sk = _SK_QUEUE_COUNT(store_id)
    _yuklu_kodlar = _magaza_yuklu_kodlari_al(store_id, include_blocked=True)
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
            else _sk.urun_renk_durumlari_al()
        ).items()
    }

    toplam = 0
    for row in satirlar:
        kod = _urun_kodu_normalize(row.get("urun_id", "")) or _urun_kodu_al(row.get("urun_id", ""))
        if not kod:
            continue
        renk = str(row.get("renk") or _renk_durumlari.get(kod) or "").strip().lower()
        mevcut_status = str(row.get("status", "")).strip().lower()
        if kod in _satilan_kodlar_kumesi():
            continue
        if kod in _yuklu_kodlar or _magaza_kaydi_ui_yuklu_mu(kod, renk, mevcut_status):
            toplam += 1
            continue
        if _magaza_kaydi_ui_yuklu_mu(kod, "", mevcut_status):
            toplam += 1
    return toplam


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

# Eski lokal stok.xlsx akisi kullanilmiyor; urun kaynagi artik sheet + Supabase.

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
    for eslesme in _re.finditer(r"([A-Za-zİĞŞÜÖÇıiğşüöç]{0,3})[\s-]*(\d{2,})", metin):
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
    eslesme = _re.match(r"^([A-Za-zİĞŞÜÖÇıiğşüöç]{0,3})[\s-]*(\d+)\b", metin)
    if not eslesme:
        return None

    harf = (eslesme.group(1) or "").lower()
    rakam = eslesme.group(2)
    return f"{harf}{rakam}"


def _klasor_urun_kodu_al(klasor_adi: str):
    metin = str(klasor_adi or "").strip()
    if not metin:
        return None

    # Magaza icindeki ana navigasyon klasorleri (01-PATCH..., 05-RUGS KILIM vb.)
    # urun klasoru gibi yorumlanmamali.
    if _re.match(r"^\d{1,2}\s*[-–]\s*[A-Za-zİIŞŞĞÜÖÇ]", metin):
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
        # Bilgi dosyaları en önce: "--" içeren ve (m2 veya ft) içeren dosyalar
        aday_metinler.extend(
            str(ad or "").strip()
            for ad in dosya_adlari
            if "--" in str(ad or "") and ("m2" in str(ad or "").lower() or "ft" in str(ad or "").lower())
        )
    # Klasör adı kamera dosyalarından önce — kamera adları (1C4Axxxx) yanlış kod verir
    aday_metinler.append(str(klasor_adi or "").strip())
    if dosya_adlari:
        aday_metinler.extend(str(ad or "").strip() for ad in dosya_adlari)

    for metin in aday_metinler:
        adaylar = _urun_kodu_adaylari(metin)
        if adaylar:
            return adaylar[0]

    return _klasor_urun_kodu_al(klasor_adi) or _urun_kodu_al(klasor_adi) or str(klasor_adi or "").strip()


def _urun_sec_renk_durumu(klasor_adi: str, *, klasor_id=None, kuyruk_status: str | None = None):
    """
    Urun Sec ekranindaki tek gercek renk semantigi:
    red   -> satildi (tum magazalarda)
    green -> secili magazada yuklendi
    blue  -> secili magazanin sheet/kuyrugunda var ama yuklenmedi
    none  -> renk yok / urun klasoru degil
    """
    kod = _klasor_urun_kodu_al(klasor_adi)
    if not kod:
        return None

    store_id = str(st.session_state.get("hedef_magaza_id") or "").strip()
    kid = str(klasor_id or "").strip()
    return _urun_sec_magaza_durumu(
        kod,
        store_id=store_id,
        klasor_id=kid,
        kuyruk_status=kuyruk_status,
    )


def _urun_sec_magaza_durumu(
    kod: str,
    *,
    store_id: str,
    klasor_id: str = "",
    kuyruk_status: str | None = None,
) -> str | None:
    key = str(kod or "").strip()
    if not key:
        return None

    if key in _satilan_kodlar_kumesi():
        return "red"

    sheet_renk = ""
    kid = str(klasor_id or "").strip()
    if kid and kid in st.session_state.klasor_id_durumlari:
        sheet_renk = str(st.session_state.klasor_id_durumlari.get(kid) or "").strip().lower()
    if not sheet_renk:
        sheet_renk = str(st.session_state.sheet_renk_durumlari.get(key) or "").strip().lower()

    kuyruk_status_norm = str(kuyruk_status or "").strip().lower()
    session_queue_status = str(st.session_state.get("kuyruga_eklenenler", {}).get(key) or "").strip().lower()

    if (
        key in _sheet_yuklu_kodlari_al(store_id)
        or sheet_renk == "green"
    ):
        return "green"

    if kuyruk_status_norm or session_queue_status or sheet_renk in {"yellow", "red"}:
        return "blue"

    return None


def _urun_magazada_yuklu_mu(kod: str, store_id: str, canli_magaza_haritasi: dict[str, set[str]]) -> bool:
    key = str(kod or "").strip()
    sid = str(store_id or "").strip()
    if not key or not sid:
        return False
    if key in _satilan_kodlar_kumesi():
        return False
    return sid in (canli_magaza_haritasi.get(key, set()) or set())


@st.cache_data(ttl=300, show_spinner=False)
def _magaza_ad_haritasi() -> dict[str, str]:
    try:
        from shared.store_manager import tum_magazalar as _tum_magaza_liste
        return {
            str(m.get("store_id") or "").strip(): str(m.get("store_name") or m.get("store_id") or "").strip()
            for m in _tum_magaza_liste()
            if str(m.get("store_id") or "").strip()
        }
    except Exception:
        return {}


def _urun_yuklu_magaza_adlari(
    kod: str,
    *,
    canli_magaza_haritasi: dict[str, set[str]] | None = None,
    haric_magazalar: list[str] | set[str] | tuple[str, ...] | None = None,
) -> list[str]:
    norm_kod = _urun_kodu_normalize(kod) or _urun_kodu_al(kod)
    if not norm_kod:
        return []

    if canli_magaza_haritasi is None:
        try:
            tum_magazalar = list(_magaza_ad_haritasi().keys())
        except Exception:
            tum_magazalar = []
        canli_magaza_haritasi, _ = _canli_magaza_haritasi_hazir(tum_magazalar)

    dislanacak = {
        str(m or "").strip().lower()
        for m in (haric_magazalar or [])
        if str(m or "").strip()
    }
    ad_haritasi = _magaza_ad_haritasi()
    magazalar = sorted(canli_magaza_haritasi.get(norm_kod, set()) or set())
    return [
        ad_haritasi.get(store_id, store_id)
        for store_id in magazalar
        if str(store_id or "").strip().lower() not in dislanacak
    ]


def _store_status_delete_reason(status: str | None) -> str:
    durum = str(status or "").strip().lower()
    if durum == "needs_delete_sold":
        return "sold"
    if durum == "needs_delete_deleted":
        return "deleted"
    return ""


def _store_status_is_loaded(row_or_status, renk: str | None = None) -> bool:
    if isinstance(row_or_status, dict):
        status = str(row_or_status.get("status") or "").strip().lower()
        renk = str(row_or_status.get("renk") or "").strip().lower()
    else:
        status = str(row_or_status or "").strip().lower()
        renk = str(renk or "").strip().lower()
    if renk in {"red", "yellow"}:
        return False
    if status in {"deleted", "removed"}:
        return False
    if status.startswith("needs_delete_"):
        return True
    return renk == "green" or status == "done"


def _store_status_is_active_loaded(row: dict) -> bool:
    status = str((row or {}).get("status") or "").strip().lower()
    if _store_status_delete_reason(status):
        return False
    kod = _urun_kodu_normalize((row or {}).get("product_code", "")) or _urun_kodu_al((row or {}).get("product_code", ""))
    renk = str((row or {}).get("renk") or "").strip().lower()
    return _magaza_kaydi_ui_yuklu_mu(kod, renk, status)


def _sheet_renk_durumu(klasor_adi: str):
    return _urun_sec_renk_durumu(klasor_adi)


def _sheet_renk_durumu_klasor(klasor_id, klasor_adi: str, kuyruk_status: str | None = None):
    return _urun_sec_renk_durumu(klasor_adi, klasor_id=klasor_id, kuyruk_status=kuyruk_status)


def _satilan_kod_cache_yenile():
    satilan = _satilan_kodlar()
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
        if _magaza_kaydi_ui_yuklu_mu(kod, renk, durum):
            yuklu_kodlar.add(kod)

    st.session_state[cache_key] = sorted(yuklu_kodlar)
    st.session_state[ts_key] = _time.time()
    return yuklu_kodlar


def _sheet_yuklu_kodlari_al(store_id: str, force: bool = False, include_blocked: bool = False) -> set[str]:
    store_id = str(store_id or "").strip()
    if not store_id:
        return set()

    cache_key = f"sheet_loaded_codes::{store_id}"
    ts_key = f"{cache_key}::ts"
    try:
        son_okuma = float(st.session_state.get(ts_key) or 0)
    except Exception:
        son_okuma = 0
    if son_okuma and (_time.time() - son_okuma) <= 60:
        yuklu_kodlar = set(st.session_state.get(cache_key) or [])
    elif not force:
        # Urun sec tabinda render thread'i sheet okumasi ile bloklama.
        # Sheet cache henuz bellekte yoksa bos donup hizli ac; manuel/arka plan
        # yenileme cache'i doldurdugunda rozetler dogal olarak duzelir.
        yuklu_kodlar = set(st.session_state.get(cache_key) or [])
    else:
        try:
            yuklu_kodlar = set(_sheet_green_kodlari_cached(store_id))
        except Exception:
            yuklu_kodlar = set()

    if not include_blocked:
        yuklu_kodlar = {kod for kod in yuklu_kodlar if not _urun_kodu_bloklu_mu(kod)}

    st.session_state[cache_key] = sorted(yuklu_kodlar)
    st.session_state[ts_key] = _time.time()
    return yuklu_kodlar


def _magaza_renk_cache_yenile(store_id: str):
    from shared.sheets import SheetsKatmani as _SK_REFRESH

    store_id = str(store_id or "").strip()
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
    _sheet_yuklu_kodlar = {
        kod for kod, renk in _renkler_refresh.items()
        if str(renk or "").strip().lower() == "green"
    }
    st.session_state[f"sheet_loaded_codes::{store_id}"] = sorted(_sheet_yuklu_kodlar)
    st.session_state[f"sheet_loaded_codes::{store_id}::ts"] = _time.time()
    st.session_state.sheet_renk_magaza_id = store_id
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


def _urun_sec_sheet_degisim_imzasi_al(store_id: str) -> str:
    try:
        from shared.sheets import drive_file_degisim_imzasi
        from shared.store_manager import get_store as _get_store_sig

        store = _get_store_sig(store_id)
        sheet_id = str(store.get("google_sheet_id") or os.environ.get("GOOGLE_SHEET_ID", "")).strip()
        if not sheet_id:
            return ""
        return drive_file_degisim_imzasi(sheet_id)
    except Exception:
        return ""


def _urun_sec_rozet_cache_uygula(store_id: str) -> bool:
    store_id = str(store_id or "").strip()
    if not store_id:
        return False

    payload = _json_yukle(_urun_sec_rozet_cache_yolu(store_id), {})
    if not isinstance(payload, dict):
        return False

    updated_at = float(payload.get("updated_at") or 0.0)
    seen_ts = float(st.session_state.get("_urun_sec_badge_cache_seen_ts") or 0.0)
    if updated_at and updated_at <= seen_ts and st.session_state.get("sheet_renk_magaza_id") == store_id:
        return False

    st.session_state.kuyruga_eklenenler = dict(payload.get("kuyruga_eklenenler") or {})
    st.session_state.kuyruk_klasor_durumlari = dict(payload.get("kuyruk_klasor_durumlari") or {})
    st.session_state.sheet_renk_durumlari = dict(payload.get("sheet_renk_durumlari") or {})
    st.session_state.klasor_id_durumlari = dict(payload.get("klasor_id_durumlari") or {})
    st.session_state[f"sheet_loaded_codes::{store_id}"] = list(payload.get("sheet_loaded_codes") or [])
    st.session_state[f"sheet_loaded_codes::{store_id}::ts"] = updated_at or _time.time()
    st.session_state.kuyruk_magaza_id = store_id
    st.session_state.kuyruk_yuklendi = bool(payload.get("kuyruk_yuklendi", True))
    st.session_state.sheet_renk_magaza_id = store_id
    st.session_state.sheet_renk_cache_ts = updated_at or _time.time()
    st.session_state["_urun_sec_badge_cache_seen_ts"] = updated_at or _time.time()
    return True


def _urun_sec_rozet_payload_uret(store_id: str, sheet_signature: str = "") -> dict:
    from shared.sheets import SheetsKatmani

    _sk = SheetsKatmani(store_id)
    _satirlar = _sk.tum_satirlar_al()
    _renkler = {
        (_urun_kodu_normalize(k) or _urun_kodu_al(k)): v
        for k, v in _sk.urun_renk_durumlari_al().items()
    }

    def _ilk_kod(_deger):
        _metin = str(_deger or "").strip()
        _es = _re.match(r"^([A-Za-z]{0,3})\s*(\d+)\b", _metin)
        if _es:
            return f"{(_es.group(1) or '').lower()}{_es.group(2)}"
        return _metin

    return {
        "updated_at": _time.time(),
        "store_id": store_id,
        "sheet_signature": str(sheet_signature or "").strip(),
        "kuyruga_eklenenler": {
            _ilk_kod(str(s.get("urun_id", ""))): str(s.get("status", "pending"))
            for s in _satirlar if s.get("urun_id")
        },
        "kuyruk_klasor_durumlari": {
            str(s.get("pcloud_klasor_id", "")).strip(): str(s.get("status", "pending")).strip().lower()
            for s in _satirlar
            if str(s.get("pcloud_klasor_id", "")).strip()
        },
        "sheet_renk_durumlari": _renkler,
        "klasor_id_durumlari": {
            str(s.get("pcloud_klasor_id", "")).strip(): _renkler.get(_urun_kodu_normalize(s.get("urun_id", "")) or _urun_kodu_al(s.get("urun_id", "")))
            for s in _satirlar
            if str(s.get("pcloud_klasor_id", "")).strip()
            and _renkler.get(_urun_kodu_normalize(s.get("urun_id", "")) or _urun_kodu_al(s.get("urun_id", "")))
        },
        "sheet_loaded_codes": sorted({
            kod for kod, renk in _renkler.items()
            if str(renk or "").strip().lower() == "green"
        }),
        "kuyruk_yuklendi": True,
    }


def _urun_sec_rozet_yenilemesini_baslat(store_id: str, force: bool = False) -> bool:
    store_id = str(store_id or "").strip()
    if not store_id:
        return False

    simdi = _time.time()
    son_magaza = str(st.session_state.get("_urun_sec_badge_refresh_store_id") or "").strip()
    son_baslangic = float(st.session_state.get("_urun_sec_badge_refresh_started_at") or 0.0)
    if not force and son_magaza == store_id and son_baslangic and (simdi - son_baslangic) < 20:
        return False

    st.session_state["_urun_sec_badge_refresh_store_id"] = store_id
    st.session_state["_urun_sec_badge_refresh_started_at"] = simdi

    def _job():
        try:
            mevcut_sig = _urun_sec_sheet_degisim_imzasi_al(store_id)
            payload = _urun_sec_rozet_payload_uret(store_id, sheet_signature=mevcut_sig)
            _json_kaydet(_urun_sec_rozet_cache_yolu(store_id), payload)
            _json_kaydet(_urun_sec_sheet_imza_yolu(store_id), {
                "updated_at": _time.time(),
                "store_id": store_id,
                "sheet_signature": mevcut_sig,
            })
        except Exception:
            pass

    _threading.Thread(target=_job, daemon=True, name=f"urun-sec-badges-{store_id}").start()
    return True


def _urun_sec_sheet_imza_kontrolunu_baslat(store_id: str, force: bool = False) -> bool:
    store_id = str(store_id or "").strip()
    if not store_id:
        return False

    simdi = _time.time()
    son_magaza = str(st.session_state.get("_urun_sec_sig_check_store_id") or "").strip()
    son_baslangic = float(st.session_state.get("_urun_sec_sig_check_started_at") or 0.0)
    if not force and son_magaza == store_id and son_baslangic and (simdi - son_baslangic) < 60:
        return False

    st.session_state["_urun_sec_sig_check_store_id"] = store_id
    st.session_state["_urun_sec_sig_check_started_at"] = simdi

    def _job():
        try:
            mevcut_sig = _urun_sec_sheet_degisim_imzasi_al(store_id)
            if not mevcut_sig:
                return
            sig_payload = _json_yukle(_urun_sec_sheet_imza_yolu(store_id), {})
            onceki_sig = str((sig_payload or {}).get("sheet_signature") or "").strip()
            if onceki_sig == mevcut_sig:
                return
            payload = _urun_sec_rozet_payload_uret(store_id, sheet_signature=mevcut_sig)
            _json_kaydet(_urun_sec_rozet_cache_yolu(store_id), payload)
            _json_kaydet(_urun_sec_sheet_imza_yolu(store_id), {
                "updated_at": _time.time(),
                "store_id": store_id,
                "sheet_signature": mevcut_sig,
            })
        except Exception:
            pass

    _threading.Thread(target=_job, daemon=True, name=f"urun-sec-badges-sig-{store_id}").start()
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
    durum_haritasi, meta = _sheetten_magaza_store_status_detayi_oku(store_id, store_name)

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
        "count": int(meta.get("loaded_row_count") or 0),
        "urunler": urunler,
        "updated_at": _time.time(),
    }


def _sheetten_magaza_store_status_detayi_oku(store_id: str, store_name: str = "") -> tuple[dict[str, dict], dict]:
    from shared.sheets import SheetsKatmani as _SK_STATUS

    sk = _SK_STATUS(store_id)
    satirlar = sk.tum_satirlar_al()
    renkler_raw = {
        str(k or "").strip(): str(v or "").strip().lower()
        for k, v in sk.urun_renk_durumlari_al().items()
        if str(k or "").strip()
    }
    renkler_norm = {
        (_urun_kodu_normalize(k) or _urun_kodu_al(k)): str(v or "").strip().lower()
        for k, v in renkler_raw.items()
        if (_urun_kodu_normalize(k) or _urun_kodu_al(k))
    }

    sonuc = {}
    loaded_row_count = 0
    for satir in satirlar:
        raw_urun_id = str(satir.get("urun_id", "")).strip()
        kod = _urun_kodu_normalize(raw_urun_id) or _urun_kodu_al(raw_urun_id)
        if not kod:
            continue

        renk = str(renkler_raw.get(raw_urun_id) or renkler_norm.get(kod) or "").strip().lower()
        status = str(satir.get("status", "") or "").strip().lower()
        if not renk and status not in {"pending", "ready", "downloading", "downloaded", "uploading", "done", "error"}:
            continue

        if renk == "green":
            status = "done"
        elif renk == "red" and not status:
            status = "deleted"
        elif renk == "yellow" and not status:
            status = "error"

        if _magaza_kaydi_ui_yuklu_mu(kod, renk, status):
            loaded_row_count += 1

        yeni_kayit = {
            "store_id": str(store_id or "").strip(),
            "store_name": str(store_name or store_id or "").strip(),
            "urun_id": raw_urun_id or kod,
            "status": status,
            "renk": renk,
            "etsy_draft_url": str(satir.get("etsy_draft_url", "")).strip(),
            "islem_tarihi": str(satir.get("islem_tarihi", "")).strip(),
            "pcloud_klasor_id": str(satir.get("pcloud_klasor_id", "")).strip(),
        }
        mevcut = sonuc.get(kod)
        if mevcut:
            mevcut_done = str(mevcut.get("renk") or "").strip().lower() == "green" or str(mevcut.get("status") or "").strip().lower() == "done"
            yeni_done = renk == "green" or status == "done"
            if mevcut_done and not yeni_done:
                continue
        sonuc[kod] = yeni_kayit

    return sonuc, {"loaded_row_count": loaded_row_count}

def _sheetten_magaza_store_status_oku(store_id: str, store_name: str = "") -> dict[str, dict]:
    sonuc, _ = _sheetten_magaza_store_status_detayi_oku(store_id, store_name)
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
        if _magaza_kaydi_ui_yuklu_mu(kod, renk, durum):
            yuklu_kodlar.append(kod)
    return sorted(set(yuklu_kodlar))


_STORE_STATUS_AUTO_SYNC_TTL = 60.0


def _sheet_green_kodlari_taze(store_id: str) -> list[str]:
    """
    `_sheet_green_kodlari_cached` ile ayni mantigi uygular ama st.cache_data
    katmanindan TAMAMEN bagimsizdir; dogrudan Sheet'i okur. Sadece
    `_store_status_auto_sync_green` icin kullanilir, boylece sync'in
    dogrulugu UI-goruntuleme cache'lerinin TTL'ine bagli kalmaz.
    """
    sid = str(store_id or "").strip()
    if not sid:
        return []
    durumlar = _sheetten_magaza_store_status_oku(sid, "")
    yuklu_kodlar = []
    for raw_code, satir in durumlar.items():
        kod = _urun_kodu_normalize(raw_code) or _urun_kodu_al(raw_code)
        if not kod:
            continue
        renk = str((satir or {}).get("renk") or "").strip().lower()
        durum = str((satir or {}).get("status") or "").strip().lower()
        if _magaza_kaydi_ui_yuklu_mu(kod, renk, durum):
            yuklu_kodlar.append(kod)
    return sorted(set(yuklu_kodlar))


def _store_status_auto_sync_green(store_id: str) -> None:
    """
    Sheet'te green olarak isaretlenmis ama Supabase product_store_status'ta
    eksik/bayat (green/done degil) olan kayitlari otomatik olarak senkronlar.

    Streamlit her etkilesimde script'i yeniden calistirdigi icin, ayni magaza
    icin _STORE_STATUS_AUTO_SYNC_TTL saniyede bir defadan fazla calismaz
    (session_state uzerinde son calisma zamani tutulur).
    """
    sid = str(store_id or "").strip()
    if not sid:
        return

    throttle_map = st.session_state.setdefault("_store_status_auto_sync_ts", {})
    simdi = _time.time()
    son = throttle_map.get(sid, 0.0)
    if (simdi - son) < _STORE_STATUS_AUTO_SYNC_TTL:
        return
    throttle_map[sid] = simdi

    try:
        from shared.product_catalog import _supabase_ready
        if not _supabase_ready():
            return
        from shared.sheets import _supabase_store_status_sync_green

        green_codes = [
            kod for kod in _sheet_green_kodlari_taze(sid)
            if kod and not str(kod).startswith("__row__:")
        ]
        if not green_codes:
            return

        _store_status_rows_cached.clear()
        mevcut_satirlar = {
            str(row.get("product_code") or "").strip(): str(row.get("status") or "").strip().lower()
            for row in _store_status_rows_cached()
            if str(row.get("store_id") or "").strip() == sid
        }
        eksik_veya_bayat = [
            kod for kod in green_codes
            if mevcut_satirlar.get(kod, "") not in {"done", "green"}
        ]
        if not eksik_veya_bayat:
            print(
                f"[auto_sync_green] {sid}: {len(green_codes)} green kod bulundu, eksik yok",
                file=sys.stderr,
            )
            return

        print(
            f"[auto_sync_green] {sid}: eksik/bayat {len(eksik_veya_bayat)} kod tespit edildi -> {eksik_veya_bayat}",
            file=sys.stderr,
        )

        try:
            _supabase_store_status_sync_green(sid, eksik_veya_bayat, status="done")
            print(f"[auto_sync_green] {sid}: upsert basarili ({len(eksik_veya_bayat)} kod)", file=sys.stderr)
        except Exception as exc:
            print(f"[auto_sync_green] {sid}: upsert HATASI: {exc!r}", file=sys.stderr)
            raise

        # Guncel sayilarin hemen yansimasi icin ilgili tum cache'leri temizle
        _store_status_rows_cached.clear()
        _store_status_loaded_counts_cached.clear()
        _sheet_green_kodlari_cached.clear()
        try:
            _sheet_green_haritasi_cached.clear()
        except Exception:
            pass
        # _magaza_yuklu_kodlari_al kendi session_state TTL'ini kullanir; zorla yenile
        try:
            st.session_state.pop(f"loaded_codes::{sid}::ts", None)
            st.session_state.pop(f"loaded_codes::{sid}", None)
        except Exception:
            pass
    except Exception as exc:
        print(f"[auto_sync_green] {sid}: genel HATA: {exc!r}", file=sys.stderr)


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


def _canli_magaza_haritasi_dosyadan_yukle() -> dict:
    return _json_yukle(_CANLI_HARITA_DB, {"updated_at": 0, "data": {}, "store_ids": []})


def _envanter_cacheden_canli_magaza_haritasi(
    store_ids: list[str],
    cache: dict | None = None,
) -> dict[str, set[str]]:
    hedef_magazalar = {
        str(store_id or "").strip()
        for store_id in (store_ids or [])
        if str(store_id or "").strip()
    }
    if not hedef_magazalar:
        return {}

    kaynak = cache if isinstance(cache, dict) else _envanter_cache_dosyadan_yukle()
    stores = (kaynak or {}).get("stores") or {}
    harita: dict[str, set[str]] = {}
    for store_id in sorted(hedef_magazalar):
        store_data = stores.get(store_id) or {}
        for raw_code in ((store_data.get("urunler") or {}).keys()):
            kod = _urun_kodu_normalize(raw_code) or _urun_kodu_al(raw_code)
            if not kod:
                continue
            harita.setdefault(kod, set()).add(store_id)
    return harita


def _canli_magaza_haritalarini_birlestir(
    *haritalar: dict[str, list[str] | tuple[str, ...] | set[str]] | None,
) -> dict[str, set[str]]:
    sonuc: dict[str, set[str]] = {}
    for harita in haritalar:
        for kod, magazalar in (harita or {}).items():
            temiz_kod = str(kod or "").strip()
            if not temiz_kod:
                continue
            hedef = sonuc.setdefault(temiz_kod, set())
            for magaza in (magazalar or []):
                temiz_magaza = str(magaza or "").strip()
                if temiz_magaza:
                    hedef.add(temiz_magaza)
    return sonuc


def _canli_magaza_haritasi_store_birlestir(store_id: str, product_codes: set[str] | list[str]) -> None:
    sid = str(store_id or "").strip()
    if not sid:
        return

    kodlar = {
        str(code).strip()
        for code in (product_codes or [])
        if str(code).strip()
    }
    mevcut = _canli_magaza_haritasi_dosyadan_yukle()
    ham_data = {
        str(k): list(v or [])
        for k, v in ((mevcut or {}).get("data") or {}).items()
        if str(k).strip()
    }

    yeni_data: dict[str, list[str]] = {}
    for kod, magazalar in ham_data.items():
        kalan = [magaza for magaza in magazalar if str(magaza).strip() != sid]
        if kalan:
            yeni_data[kod] = kalan

    for kod in sorted(kodlar):
        yeni_data.setdefault(kod, []).append(sid)

    store_ids = {
        str(s).strip()
        for s in ((mevcut or {}).get("store_ids") or [])
        if str(s).strip()
    }
    store_ids.add(sid)
    _json_kaydet(_CANLI_HARITA_DB, {
        "updated_at": _time.time(),
        "data": {kod: sorted(set(magazalar)) for kod, magazalar in yeni_data.items()},
        "store_ids": sorted(store_ids),
        "source": "supabase-bg-sync",
    })


def _canli_magaza_haritasindan_magaza_kodlarini_cikar(store_id: str, product_codes: set[str] | list[str]) -> None:
    sid = str(store_id or "").strip()
    if not sid:
        return

    kodlar = {
        str(code).strip()
        for code in (product_codes or [])
        if str(code).strip()
    }
    if not kodlar:
        return

    mevcut = _canli_magaza_haritasi_dosyadan_yukle()
    ham_data = {
        str(k): list(v or [])
        for k, v in ((mevcut or {}).get("data") or {}).items()
        if str(k).strip()
    }
    yeni_data: dict[str, list[str]] = {}
    for kod, magazalar in ham_data.items():
        filtreli = list(magazalar or [])
        if kod in kodlar:
            filtreli = [magaza for magaza in filtreli if str(magaza).strip() != sid]
        if filtreli:
            yeni_data[kod] = filtreli

    _json_kaydet(_CANLI_HARITA_DB, {
        "updated_at": _time.time(),
        "data": {kod: sorted(set(magazalar)) for kod, magazalar in yeni_data.items()},
        "store_ids": sorted({
            str(s).strip()
            for s in ((mevcut or {}).get("store_ids") or [])
            if str(s).strip()
        }),
        "source": "local-red-sync",
    })


@st.cache_data(ttl=30, show_spinner=False)
def _supabase_magaza_yuklu_sayilari_cached() -> dict[str, int]:
    sayilar: dict[str, int] = {}
    for row in _store_status_rows_cached():
        sid = str(row.get("store_id") or "").strip()
        # Fiziksel olarak Etsy'de duran ama silinmesi beklenen kayitlari da
        # magazada yuklu say; ayri sekmede temizlenecekler olarak gosteriyoruz.
        if not sid or not _store_status_is_loaded(row):
            continue
        sayilar[sid] = sayilar.get(sid, 0) + 1
    return sayilar


@st.cache_data(ttl=30, show_spinner=False)
def _store_status_rows_cached() -> list[dict]:
    from shared.product_catalog import StoreCatalog, _supabase_ready

    if not _supabase_ready():
        return []
    try:
        return StoreCatalog().list_by_store()
    except Exception:
        return []


@st.cache_data(ttl=30, show_spinner=False)
def _store_status_loaded_counts_cached() -> dict[str, int]:
    sayilar: dict[str, int] = {}
    for row in _store_status_rows_cached():
        sid = str(row.get("store_id") or "").strip()
        if not sid or not _store_status_is_loaded(row):
            continue
        sayilar[sid] = sayilar.get(sid, 0) + 1
    return sayilar


def _etsy_csv_sku_normalize(raw_sku: str, store_id: str) -> str:
    _prefix_map = {
        "LoomixRugs":     ["LMX "],
        "LoopRug":        ["LR ", "LP "],
        "RugsShopTurkey": ["RST ", "RSH "],
        "WovenLoomRugs":  ["WLR ", "WLB "],
        "İlmekRug":       ["ilmek "],
        "IlmekRug":       ["ilmek "],
    }
    sku = str(raw_sku or "").strip()
    for p in _prefix_map.get(store_id, []):
        if sku.upper().startswith(p.upper()):
            sku = sku[len(p):].strip()
            break
    # Canonical: büyük harf, tire→boşluk, harf+rakam arası boşluk (D149→D 149, KLM62→KLM 62)
    sku = sku.upper().replace("-", " ").strip()
    sku = _re.sub(r"\s+", " ", sku)
    sku = _re.sub(r"([A-ZÇĞİÖŞÜ]+)(\d)", r"\1 \2", sku)
    return _re.sub(r"\s+", " ", sku).strip()


def _etsy_csv_import_ui(tum_magazalar: list, magaza_ad_haritasi: dict):
    """Etsy CSV içe aktarma — kendi mağaza seçicisiyle bağımsız bölüm."""
    import io
    import csv as _csv_mod

    with st.expander("📥 Etsy CSV İçe Aktar", expanded=False):
        magaza_secenekleri = [
            m["store_id"] for m in tum_magazalar
            if str(m.get("store_id") or "").strip()
        ]
        store_id = st.selectbox(
            "Mağaza seçin",
            options=magaza_secenekleri,
            format_func=lambda sid: magaza_ad_haritasi.get(sid, sid),
            key="etsy_csv_import_magaza_sec",
        )
        store_name = magaza_ad_haritasi.get(store_id, store_id)

        st.warning(f"⚠️ Yalnızca **{store_name}** mağazasının Sheet sekmesi ve Supabase kayıtları etkilenir.")

        uploaded = st.file_uploader(
            f"{store_name} Etsy CSV (SKU kolonu gerekli)",
            type=["csv"],
            key=f"etsy_csv_upload_{store_id}",
        )

        if not uploaded:
            return

        try:
            content = uploaded.read().decode("utf-8-sig")
            reader = list(_csv_mod.DictReader(io.StringIO(content)))
        except Exception as exc:
            st.error(f"CSV okunamadı: {exc}")
            return

        if not reader:
            st.warning("CSV boş.")
            return

        sku_col = next((c for c in reader[0].keys() if c.strip().upper() == "SKU"), None)
        if not sku_col:
            st.error("CSV'de SKU kolonu bulunamadı.")
            return

        # Duplicate SKU tespiti
        from collections import Counter as _Counter
        _sku_sayac = _Counter(
            _etsy_csv_sku_normalize(row.get(sku_col, ""), store_id)
            for row in reader
            if _etsy_csv_sku_normalize(row.get(sku_col, ""), store_id)
        )
        duplicate_skular = {k: v for k, v in _sku_sayac.items() if v > 1}

        csv_kodlar: set[str] = set(_sku_sayac.keys())

        if not csv_kodlar:
            st.warning("CSV'de geçerli SKU bulunamadı.")
            return

        if duplicate_skular:
            with st.expander(f"⚠️ {len(duplicate_skular)} tekrarlı SKU — CSV'de aynı ürün kodu birden fazla listing'e atanmış", expanded=True):
                st.caption("Bu SKU'lar Etsy'de birden fazla listing olarak yüklenmiş. Import'ta her SKU 1 kez işlenir; Etsy'de duplicate listingleri kontrol edin.")
                import pandas as _pd_dup
                st.dataframe(
                    _pd_dup.DataFrame([{"SKU": k, "Tekrar sayısı": v} for k, v in sorted(duplicate_skular.items())]),
                    hide_index=True,
                    width="stretch",
                )

        # Sheet'teki TÜM satırları oku — karşılaştırma kaynağı Sheet'in kendisi
        with st.spinner("Sheet okunuyor..."):
            try:
                from shared.sheets import SheetsKatmani as _SK_PREV
                _sk_prev = _SK_PREV(store_id)
                _sk_prev.sheet_hazirla()
                _ws_prev = _sk_prev._baglanti()
                from shared.sheets import _kolon_no as _kno, KOL as _KOL_P
                _uid_kol = _kno(_ws_prev, "urun_id", default=_KOL_P["urun_id"])
                _tum_sheet_idler = _ws_prev.col_values(_uid_kol)
                _sheet_raw_idler = [str(v).strip() for v in _tum_sheet_idler[1:] if str(v).strip() and str(v).strip() != "urun_id"]
            except Exception as exc:
                st.error(f"Sheet okunamadı: {exc}")
                return

        # normalize → ham kod eşlemesi (silme için ham ID lazım)
        # CSV ile aynı canonical format: büyük harf, tire→boşluk, harf+rakam arası boşluk
        def _sheet_kod_normalize(raw: str) -> str:
            s = str(raw or "").upper().replace("-", " ").strip()
            s = _re.sub(r"\s+", " ", s)
            s = _re.sub(r"([A-ZÇĞİÖŞÜ]+)(\d)", r"\1 \2", s)
            return _re.sub(r"\s+", " ", s).strip()

        _norm_to_raw: dict[str, str] = {}
        for raw in _sheet_raw_idler:
            norm = _sheet_kod_normalize(raw)
            if norm:
                _norm_to_raw.setdefault(norm, raw)

        sheet_kodlar: set[str] = set(_norm_to_raw.keys())
        sheet_kodlar.discard("")

        eklenecek = csv_kodlar - sheet_kodlar
        silinecek = sheet_kodlar - csv_kodlar
        zaten_yuklu = csv_kodlar & sheet_kodlar

        _c1, _c2, _c3 = st.columns(3)
        _c1.metric("Yeni eklenecek", len(eklenecek))
        _c2.metric("Sheet'te mevcut", len(zaten_yuklu))
        _c3.metric("Sheet'ten silinecek", len(silinecek))

        if silinecek:
            with st.expander(f"Silinecek {len(silinecek)} ürün"):
                st.write(", ".join(sorted(silinecek)))

        # Son import sonucu — st.rerun'dan önce session_state'e kaydedilir, silinmez
        _sonuc_key = f"etsy_csv_import_sonuc_{store_id}"
        if st.session_state.get(_sonuc_key):
            _s = st.session_state[_sonuc_key]
            st.success(
                f"✅ Son import tamamlandı — "
                f"Eklenen: {_s.get('eklenen', 0)}, "
                f"Yeşillenen: {_s.get('guncellenen', 0)}, "
                f"Silinen: {_s.get('silinen', 0)}"
            )

        if st.button(f"İçe Aktar → {store_name}", type="primary", key=f"etsy_csv_import_btn_{store_id}"):
            from shared.sheets import SheetsKatmani as _PS_IMP
            _ps_imp = _PS_IMP(store_id)
            with st.spinner("İçe aktarılıyor..."):
                try:
                    silinen = 0
                    if silinecek:
                        ham_silinecek = [_norm_to_raw.get(k, k) for k in silinecek]
                        silinen = _ps_imp.satirlari_sil(ham_silinecek)
                        from shared.product_catalog import StoreCatalog as _SC_IMP, _supabase_ready as _sr_imp
                        if _sr_imp():
                            _SC_IMP().delete(store_id, ham_silinecek)

                    kayitlar = [{"urun_id": kod} for kod in sorted(csv_kodlar)]
                    sonuc = _ps_imp.etsy_csv_kayitlarini_isle(kayitlar, renk="green", durum="done")

                    _store_status_caches_temizle()
                    _urun_katalog_cache_temizle()
                    try:
                        _sheet_green_kodlari_cached.clear()
                        _sheet_green_haritasi_cached.clear()
                    except Exception:
                        pass

                    st.session_state[_sonuc_key] = {
                        "eklenen": sonuc.get("eklenen", 0),
                        "guncellenen": sonuc.get("guncellenen", 0),
                        "silinen": silinen,
                    }
                    st.rerun()
                except Exception as exc:
                    st.error(f"İçe aktarma hatası: {exc}")


@st.cache_data(ttl=30, show_spinner=False)
def _store_status_pending_delete_rows_cached() -> list[dict]:
    rows = []
    seen: set[tuple[str, str]] = set()

    for row in _store_status_rows_cached():
        reason = _store_status_delete_reason(row.get("status"))
        if not reason:
            continue
        copy = dict(row)
        copy["delete_reason"] = reason
        kod = _urun_kodu_normalize(copy.get("product_code", "")) or _urun_kodu_al(copy.get("product_code", ""))
        sid = str(copy.get("store_id") or "").strip()
        if kod and sid:
            seen.add((kod, sid))
        rows.append(copy)

    sold_codes = _satilan_kodlar()
    if not sold_codes:
        return rows

    for row in _store_status_rows_cached():
        if not _store_status_is_loaded(row):
            continue
        kod = _urun_kodu_normalize(row.get("product_code", "")) or _urun_kodu_al(row.get("product_code", ""))
        sid = str(row.get("store_id") or "").strip()
        if not kod or not sid or kod not in sold_codes or (kod, sid) in seen:
            continue
        copy = dict(row)
        copy["status"] = "needs_delete_sold"
        copy["delete_reason"] = "sold"
        rows.append(copy)
        seen.add((kod, sid))

    return rows


def _store_status_caches_temizle():
    try:
        _store_status_rows_cached.clear()
        _store_status_loaded_counts_cached.clear()
        _store_status_pending_delete_rows_cached.clear()
        _supabase_magaza_yuklu_sayilari_cached.clear()
        _supabase_store_haritasi_cached.clear()
        _kuyruk_satirlari_cached.clear()
        _magaza_kuyruk_yuklu_sayisi_cached.clear()
    except Exception:
        pass


def _store_status_auto_sync_all_stores(store_ids: list[str]) -> None:
    for store_id in store_ids or []:
        sid = str(store_id or "").strip()
        if not sid:
            continue
        try:
            _store_status_auto_sync_green(sid)
        except Exception:
            pass


def _store_status_auto_sync_all_stores_async(
    store_ids: list[str],
    *,
    min_interval_seconds: int = 120,
    force: bool = False,
) -> bool:
    temiz = [
        str(store_id or "").strip()
        for store_id in (store_ids or [])
        if str(store_id or "").strip()
    ]
    if not temiz:
        return False

    global _STORE_STATUS_BG_SYNC_TS
    simdi = _time.time()
    if _STORE_STATUS_BG_SYNC_LOCK.locked():
        return False
    if not force and _STORE_STATUS_BG_SYNC_TS and (simdi - _STORE_STATUS_BG_SYNC_TS) < max(10, int(min_interval_seconds)):
        return False
    _STORE_STATUS_BG_SYNC_TS = simdi

    def _job():
        with _STORE_STATUS_BG_SYNC_LOCK:
            _store_status_auto_sync_all_stores(temiz)

    _threading.Thread(target=_job, daemon=True, name="store-status-all-sync").start()
    return True


def _urunun_tum_yuklu_magazalari(kod: str, *, include_store_ids: bool = False) -> list[str]:
    norm_kod = _urun_kodu_normalize(kod) or _urun_kodu_al(kod)
    if not norm_kod:
        return []

    store_map = _supabase_store_haritasi_cached()
    store_ids = list(store_map.get(norm_kod, ()) or ())
    if include_store_ids:
        return store_ids

    ad_haritasi = _magaza_ad_haritasi()
    return [ad_haritasi.get(store_id, store_id) for store_id in store_ids]


def _supabase_store_haritasi_yukle() -> dict[str, set[str]]:
    """Supabase product_store_status cache'inden store map döndürür."""
    harita: dict[str, set[str]] = {}
    for row in _store_status_rows_cached():
        raw_code = str(row.get("product_code") or "").strip()
        kod = _urun_kodu_normalize(raw_code) or _urun_kodu_al(raw_code)
        if not kod or not _store_status_is_loaded(row):
            continue
        harita.setdefault(kod, set()).add(str(row.get("store_id") or ""))
    return harita


@st.cache_data(ttl=15, show_spinner=False)
def _supabase_store_haritasi_cached() -> dict[str, tuple[str, ...]]:
    harita = _supabase_store_haritasi_yukle()
    return {
        str(kod): tuple(sorted(set(magazalar)))
        for kod, magazalar in (harita or {}).items()
        if str(kod).strip()
    }


def _canli_magaza_haritasi_filtrele(
    harita: dict[str, list[str] | tuple[str, ...] | set[str]] | None,
    store_ids: list[str],
) -> dict[str, set[str]]:
    izinli = {
        str(store_id or "").strip()
        for store_id in (store_ids or [])
        if str(store_id or "").strip()
    }
    if not izinli:
        return {}

    sonuc: dict[str, set[str]] = {}
    for kod, magazalar in (harita or {}).items():
        temiz_kod = str(kod or "").strip()
        if not temiz_kod:
            continue
        eslesen = {
            str(magaza or "").strip()
            for magaza in (magazalar or [])
            if str(magaza or "").strip() in izinli
        }
        if eslesen:
            sonuc[temiz_kod] = eslesen
    return sonuc


def _supabase_haritayi_urunler_cacheine_yaz(store_ids: list[str]) -> dict[str, set[str]]:
    try:
        from shared.product_catalog import _supabase_ready
    except Exception:
        return {}

    if not _supabase_ready():
        return {}

    harita = _canli_magaza_haritasi_filtrele(_supabase_store_haritasi_cached(), store_ids)
    if not harita:
        return {}

    _json_kaydet(_CANLI_HARITA_DB, {
        "updated_at": _time.time(),
        "data": {kod: sorted(magazalar) for kod, magazalar in harita.items()},
        "store_ids": sorted({
            str(store_id or "").strip()
            for store_id in (store_ids or [])
            if str(store_id or "").strip()
        }),
        "source": "supabase-inline",
    })
    return harita


def _canli_magaza_haritasi_bg_guncelle(store_ids: list[str]):
    """
    Background thread: önce Supabase'den hızlıca (aynı VPS, ~100ms), ardından
    Sheets'ten otoriter veriyle dosyayı günceller. İki adım → iki dosya yazımı →
    fragment her birini ayrı ayrı yakalar ve sayfayı günceller.
    """
    if _CANLI_HARITA_LOCK.locked():
        return
    temiz = [str(s or "").strip() for s in store_ids if str(s or "").strip()]
    if not temiz:
        return

    def _job():
        with _CANLI_HARITA_LOCK:
            from shared.product_catalog import _supabase_ready

            # Adım 1 — Supabase'den hızlı yükleme (aynı VPS, ~100ms)
            if _supabase_ready():
                try:
                    supabase_harita = _supabase_store_haritasi_yukle()
                    if supabase_harita:
                        _json_kaydet(_CANLI_HARITA_DB, {
                            "updated_at": _time.time(),
                            "data": {k: list(v) for k, v in supabase_harita.items()},
                            "store_ids": sorted(temiz),
                            "source": "supabase",
                        })
                except Exception:
                    pass

            # Adım 2 — Arka plandaki sheet sync tamamlandıktan sonra tekrar Supabase'e bak.
            # Yuklu urun gercegi artik panelin kendi store_status kaydidir; sheet sadece
            # yeni yukleri iceri tasiyan giris noktasi olarak kalir.
            try:
                supabase_harita = _supabase_store_haritasi_yukle()
                if supabase_harita:
                    _json_kaydet(_CANLI_HARITA_DB, {
                        "updated_at": _time.time(),
                        "data": {k: list(v) for k, v in supabase_harita.items()},
                        "store_ids": sorted(temiz),
                        "source": "supabase-post-sync",
                    })
            except Exception:
                pass

    _threading.Thread(target=_job, daemon=True, name="canli-harita-sync").start()


def _magaza_hizli_arka_plan_sync_baslat(store_id: str, *, min_interval_seconds: int = 12, force: bool = False) -> bool:
    sid = str(store_id or "").strip()
    if not sid:
        return False

    try:
        from shared.product_catalog import _supabase_ready
    except Exception:
        return False

    if not _supabase_ready():
        return False

    simdi = _time.time()
    with _STORE_BG_SYNC_GUARD:
        kilit = _STORE_BG_SYNC_LOCKS.setdefault(sid, _threading.Lock())
        son = float(_STORE_BG_SYNC_TS.get(sid) or 0.0)
        if kilit.locked():
            return False
        if not force and son and (simdi - son) < max(3, int(min_interval_seconds)):
            return False
        _STORE_BG_SYNC_TS[sid] = simdi

    def _job():
        with kilit:
            try:
                cache = _magaza_envanterini_topla(force=True, store_ids=[sid])
                store_data = ((cache or {}).get("stores") or {}).get(sid) or {}
                urunler = (store_data.get("urunler") or {})
                _canli_magaza_haritasi_store_birlestir(sid, set(urunler.keys()))
                _supabase_magaza_yuklu_sayilari_cached.clear()
                _kuyruk_satirlari_cached.clear()
                _magaza_kuyruk_yuklu_sayisi_cached.clear()
            except Exception:
                pass

    _threading.Thread(target=_job, daemon=True, name=f"store-bg-sync-{sid}").start()
    return True


def _canli_magaza_haritasi_hazir(store_ids: list[str]) -> tuple[dict[str, set[str]], bool]:
    """
    Anında dosyadan okur. Stale ise arka planda güncelleme başlatır.
    Ana thread'i hiç bloklamaz — her zaman dosyadaki son veriyi döndürür.
    """
    cached = _canli_magaza_haritasi_dosyadan_yukle()
    cached_ts = float((cached or {}).get("updated_at") or 0)
    cache_store_ids = {
        str(store_id or "").strip()
        for store_id in ((cached or {}).get("store_ids") or [])
        if str(store_id or "").strip()
    }
    is_stale = (_time.time() - cached_ts) > _CANLI_HARITA_TTL_SN
    missing_store = any(
        str(store_id or "").strip() and str(store_id or "").strip() not in cache_store_ids
        for store_id in (store_ids or [])
    )
    file_harita = _canli_magaza_haritasi_filtrele((cached or {}).get("data") or {}, store_ids)
    envanter_harita = _envanter_cacheden_canli_magaza_haritasi(store_ids)
    file_harita = _canli_magaza_haritalarini_birlestir(file_harita, envanter_harita)

    # Urunler sekmesi ilk acilista dosya cache'i bos/stale ise beklemeden
    # Supabase store_status ile hizli bootstrap yap; Sheets dogrulamasi arka planda aksin.
    supabase_bootstrap = False
    if (not file_harita or is_stale or missing_store):
        hizli_harita = _supabase_haritayi_urunler_cacheine_yaz(store_ids)
        if hizli_harita:
            file_harita = _canli_magaza_haritalarini_birlestir(hizli_harita, envanter_harita)
            supabase_bootstrap = True

    bg_sync_gerekli = is_stale or missing_store or supabase_bootstrap
    if bg_sync_gerekli:
        _canli_magaza_haritasi_bg_guncelle(store_ids)
    return file_harita, bg_sync_gerekli


@st.fragment(run_every=10)
def _harita_degisim_izleyici():
    """
    Ürünler sekmesinde 10 saniyede bir dosya timestamp'ini kontrol eder.
    Arka plan güncelleme tamamlanınca tam uygulama yenileme (scope='app') tetikler.
    Kullanıcı form dolduruyorsa rerun ertelenir — pending_refresh flag koyulur.
    """
    _urunler_sessiz_sync_nabzi()
    _ts = float((_canli_magaza_haritasi_dosyadan_yukle() or {}).get("updated_at") or 0)
    _shown = float(st.session_state.get("_canli_harita_shown_ts") or 0)
    if _ts > _shown:
        st.session_state["_canli_harita_shown_ts"] = _ts
        _form_acik = bool(st.session_state.get("urun_formu_acik") or st.session_state.get("_edit_urun"))
        if _form_acik:
            st.session_state["_urunler_pending_refresh"] = True
        else:
            st.rerun(scope="app")


def _supabase_kuyruk_satirlari(store_id: str):
    from shared.product_catalog import ProductCatalog, StoreCatalog, _supabase_ready

    if not _supabase_ready():
        return None

    store_id = str(store_id or "").strip()
    if not store_id:
        return []

    store_rows = StoreCatalog().list_by_store(store_id)
    product_codes = [
        str(item.get("product_code") or "").strip()
        for item in store_rows
        if str(item.get("product_code") or "").strip()
    ]
    product_map = {
        str(item.get("product_code") or "").strip(): dict(item)
        for item in ProductCatalog().list_products_by_codes(product_codes)
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

    sig_alanlari = (
        "product_code",
        "status",
        "size_cm",
        "size_ft",
        "category",
        "loaded_store_count",
        "loaded_stores",
        "note",
        "width_ft",
        "length_ft",
        "width_cm",
        "length_cm",
        "area_m2",
        "source_tab",
    )

    arama_kaynaklari = []
    atlanan_ft = 0
    toplam = 0
    satilan = 0
    for item in (urunler_sig or []):
        if isinstance(item, dict):
            urun = dict(item)
        elif isinstance(item, (list, tuple)) and len(item) == len(sig_alanlari):
            # Performans refactor'inda gelen tuple imzayi alan adlariyla tekrar eslestir.
            urun = dict(zip(sig_alanlari, item))
        else:
            urun = dict(item)

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


@st.cache_data(ttl=180, show_spinner=False)
def _urun_sheet_urunleri_yukle_cached():
    from shared.product_sheet import ProductSheet

    return _silinenleri_filtrele(ProductSheet().read_products())


@st.cache_data(ttl=180, show_spinner=False)
def _olcu_ara_urunleri_yukle_cached(force_store_refresh: bool = False):
    """Olcu Ara icin katalogu dogrudan Supabase'ten, gerekirse urun sheet'inden okur."""
    from shared.product_catalog import ProductCatalog, _supabase_ready

    if _supabase_ready():
        if force_store_refresh:
            try:
                _magaza_envanterini_topla(force=True)
            except Exception:
                pass
        urunler = ProductCatalog().list_products(include_store_presence=False)
        return {
            "source": "supabase",
            "products": _silinenleri_filtrele(urunler),
        }

    return {
        "source": "product_sheet",
        "products": _urun_sheet_urunleri_yukle_cached(),
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
                mevcut_rows = {
                    str(row.get("product_code") or "").strip(): dict(row)
                    for row in store_catalog.list_by_store(sid)
                    if str(row.get("product_code") or "").strip()
                }
                rows = []
                for code, urun in tum_durumlar.items():
                    code = str(code).strip()
                    if not code:
                        continue
                    mevcut_row = mevcut_rows.get(code, {})
                    mevcut_status = str(mevcut_row.get("status") or "").strip().lower()
                    yeni_status = urun.get("status", "")
                    if mevcut_status.startswith("needs_delete_"):
                        yeni_status = mevcut_status
                    rows.append({
                        "product_code": code,
                        "store_id": sid,
                        "status": yeni_status,
                        "renk": urun.get("renk", ""),
                        "etsy_draft_url": urun.get("etsy_draft_url", ""),
                        "islem_tarihi": urun.get("islem_tarihi", ""),
                    })
                if rows:
                    store_catalog.upsert(rows)
                    _store_status_caches_temizle()
    except Exception:
        pass

    if yeni_cache.get("stores"):
        return yeni_cache
    return dosya_cache if dosya_cache.get("stores") else yeni_cache


def _satilan_notlarini_uret(force_refresh: bool = False):
    satilanlar = _satilan_kodlar()
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


def _magaza_kayitlarini_kirmizi_isaretle(magaza_urunleri: dict[str, set[str]]) -> tuple[int, list[str]]:
    if not magaza_urunleri:
        return 0, []

    hatalar = []
    toplam = 0

    try:
        from shared.sheets import SheetsKatmani as _SK_NOTE_UPDATE
        from shared.product_catalog import StoreCatalog as _STORE_CATALOG_RED, _supabase_ready as _supabase_ready_red
    except Exception as exc:
        return 0, [str(exc)]

    store_catalog = _STORE_CATALOG_RED() if _supabase_ready_red() else None

    for store_id, urun_idleri in magaza_urunleri.items():
        kodlar = sorted({
            _urun_kodu_normalize(urun_id) or _urun_kodu_al(urun_id)
            for urun_id in (urun_idleri or set())
            if str(urun_id or "").strip()
        })
        kodlar = [kod for kod in kodlar if kod]
        if not kodlar:
            continue

        try:
            sonuc = _SK_NOTE_UPDATE(store_id).urunleri_renklendir(kodlar, "red")
            toplam += int(sonuc.get("guncellenen") or 0)

            if store_catalog is not None:
                store_catalog.upsert([
                    {
                        "product_code": kod,
                        "store_id": store_id,
                        "status": "deleted",
                        "renk": "red",
                        "islem_tarihi": _time.strftime("%Y-%m-%d %H:%M"),
                    }
                    for kod in kodlar
                ])

            _canli_magaza_haritasindan_magaza_kodlarini_cikar(store_id, kodlar)
        except Exception as exc:
            hatalar.append(f"{store_id}: {exc}")

    try:
        _supabase_magaza_yuklu_sayilari_cached.clear()
        _kuyruk_satirlari_cached.clear()
        _magaza_kuyruk_yuklu_sayisi_cached.clear()
        _supabase_store_haritasi_cached.clear()
        _sheet_green_kodlari_cached.clear()
        _sheet_green_haritasi_cached.clear()
    except Exception:
        pass

    _global_kirmizi_kodlari_yenile()
    if st.session_state.get("hedef_magaza_id"):
        try:
            _magaza_renk_cache_yenile(st.session_state.hedef_magaza_id)
        except Exception:
            pass

    return toplam, hatalar


def _store_delete_kuyruguna_ekle(urun_kodlari: list[str] | set[str], *, reason: str) -> dict[str, list[str]]:
    kodlar = sorted({
        _urun_kodu_normalize(kod) or _urun_kodu_al(kod)
        for kod in (urun_kodlari or [])
        if str(kod or "").strip()
    })
    kodlar = [kod for kod in kodlar if kod]
    if not kodlar or reason not in {"sold", "deleted"}:
        return {}

    try:
        from shared.product_catalog import StoreCatalog as _STORE_CATALOG_BG, _supabase_ready as _supabase_ready_bg
    except Exception:
        return {}

    if not _supabase_ready_bg():
        return {}

    status_degeri = f"needs_delete_{reason}"
    magaza_map: dict[str, list[str]] = {}
    rows = _STORE_CATALOG_BG().list_by_store()
    payload = []
    for row in rows:
        kod = _urun_kodu_normalize(row.get("product_code", "")) or _urun_kodu_al(row.get("product_code", ""))
        if kod not in kodlar or not _store_status_is_loaded(row):
            continue
        sid = str(row.get("store_id") or "").strip()
        if not sid:
            continue
        magaza_map.setdefault(kod, []).append(sid)
        payload.append({
            "product_code": kod,
            "store_id": sid,
            "status": status_degeri,
            "renk": "green",
            "etsy_draft_url": row.get("etsy_draft_url", ""),
            "islem_tarihi": row.get("islem_tarihi", "") or _time.strftime("%Y-%m-%d %H:%M"),
        })

    if payload:
        _STORE_CATALOG_BG().upsert(payload)
        _store_status_caches_temizle()
        st.session_state["_urunler_store_refresh"] = True
    return {kod: sorted(set(store_ids)) for kod, store_ids in magaza_map.items()}


def _store_delete_kuyruguna_ekle_arkaplanda(urun_kodlari: list[str] | set[str], *, reason: str):
    def _job():
        try:
            _store_delete_kuyruguna_ekle(urun_kodlari, reason=reason)
        except Exception:
            pass

    _threading.Thread(target=_job, daemon=True, name=f"store-delete-queue-{reason}").start()


def _store_kaydini_yukluden_cikar_arkaplanda(entries: list[dict]):
    temiz_girdiler = [
        {
            "product_code": str(item.get("product_code") or "").strip(),
            "store_id": str(item.get("store_id") or "").strip(),
        }
        for item in (entries or [])
        if str(item.get("product_code") or "").strip() and str(item.get("store_id") or "").strip()
    ]
    if not temiz_girdiler:
        return

    def _job():
        try:
            from shared.product_catalog import StoreCatalog as _STORE_CATALOG_CLR, _supabase_ready as _supabase_ready_clr

            if not _supabase_ready_clr():
                return
            store_map: dict[str, list[str]] = {}
            for item in temiz_girdiler:
                store_map.setdefault(item["store_id"], []).append(item["product_code"])
            catalog = _STORE_CATALOG_CLR()
            for store_id, product_codes in store_map.items():
                catalog.delete(store_id, product_codes)
            _store_status_caches_temizle()
            st.session_state["_urunler_store_refresh"] = True
        except Exception:
            pass

    _threading.Thread(target=_job, daemon=True, name="store-loaded-clear").start()


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
    toplam, hatalar = _magaza_kayitlarini_kirmizi_isaretle(magaza_urunleri)

    if not hatalar:
        for note_key in note_keyler:
            _not_status_guncelle(note_key, "deleted")

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

def _satilan_kodlarini_ayikla(products: list[dict] | None) -> set[str]:
    sonuc = set()
    for urun in (products or []):
        try:
            durum = str((urun or {}).get("status") or "").strip().lower()
            if durum != "sold":
                continue
            norm = _urun_kodu_normalize((urun or {}).get("product_code", ""))
            if norm:
                sonuc.add(norm)
        except Exception:
            continue
    return sonuc


def _satilan_kodlarini_hizli_yukle() -> set[str]:
    cache_urunler = st.session_state.get("_urun_katalog_cache")
    if isinstance(cache_urunler, list) and cache_urunler:
        satilan = _satilan_kodlarini_ayikla(cache_urunler)
        if satilan:
            return satilan

    yerel = _panel_urunleri_yerden_yukle()
    if yerel:
        return _satilan_kodlarini_ayikla(yerel)
    return set()


def _satilan_kodlarini_oturumda_guncelle(products: list[dict] | None) -> set[str]:
    satilan = _satilan_kodlarini_ayikla(products)
    st.session_state.satilan_kodlar_cache = sorted(satilan)
    try:
        _satilan_kodlar_cached.clear()
    except Exception:
        pass
    return satilan


@st.cache_data(ttl=300, show_spinner=False)
def _satilan_kodlar_cached() -> set[str]:
    hizli = _satilan_kodlarini_hizli_yukle()
    if hizli:
        return hizli
    try:
        from shared.product_catalog import list_sold_product_codes, _supabase_ready
        if _supabase_ready():
            return list_sold_product_codes()
    except Exception:
        pass
    try:
        return _satilan_kodlarini_ayikla(_urun_sheet_urunleri_yukle_cached())
    except Exception:
        return set()

def _satilan_kodlar() -> set:
    return _satilan_kodlar_cached()


if not st.session_state.get("satilan_kodlar_cache"):
    st.session_state.satilan_kodlar_cache = sorted(_satilan_kodlarini_hizli_yukle())

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
def _klasor_icerigi_getir(token, klasor_id, *, _host_hint="https://api.pcloud.com"):
    # _host_hint cache key'e dahil edilmez (Streamlit _ prefix kuralı).
    # host değişse bile aynı klasör cache'ten gelir.
    for h in [_host_hint, "https://eapi.pcloud.com", "https://api.pcloud.com"]:
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
                            "entry_type": "folder",
                            "is_product_folder": False,
                        }
                    )
                else:
                    dosyalar.append(item)

            return h, klasorler, dosyalar
        except Exception:
            continue
    return _host_hint, [], []


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
            has_images = any(
                (not item.get("isfolder")) and str(item.get("name") or "").lower().endswith((".jpg", ".jpeg", ".png", ".webp"))
                for item in contents
            )
            return h, {
                # Bazi urun klasorlerinde alt klasor olsa bile secim yapilabilsin;
                # asil kriter kullanilabilir gorsel dosya bulunmasi.
                "is_product_folder": has_images or (has_files and not has_subfolders),
                "has_subfolders": has_subfolders,
                "has_files": has_files,
                "has_images": has_images,
            }
        except Exception:
            continue
    return host, {
        "is_product_folder": False,
        "has_subfolders": False,
        "has_files": False,
        "has_images": False,
    }

@st.cache_data(ttl=1800, show_spinner=False)
def _magazalari_otomatik_bul_cached(token, host):
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

def _magazalari_otomatik_bul(token, host):
    vintage_id, magazalar = _magazalari_otomatik_bul_cached(token, host)
    if not magazalar:
        # Boş/başarısız sonuç cache'te kalırsa geçici bir ağ hatası 30 dakika
        # boyunca "Klasörler otomatik bulunamadı" olarak yapışıp kalıyor.
        try:
            _magazalari_otomatik_bul_cached.clear(token, host)
        except Exception:
            _magazalari_otomatik_bul_cached.clear()
    return vintage_id, magazalar

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


def _magaza_klasor_haritasi(token, host, magaza_id):
    """Mağaza klasörlerini {normalize(kod): {"id": folder_id, "ad": folder_name}} olarak döner.
    Aynı zamanda başarılı olan host'u ("_host" key'i ile) döner."""
    def _traverse(contents, result):
        for item in contents:
            if item.get("isfolder"):
                norm = _kod_normalize(item["name"])
                fid = item.get("folderid") or item.get("id")
                if norm and fid and norm not in result:
                    result[norm] = {"id": fid, "ad": item["name"]}
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
                harita = _traverse(d["metadata"].get("contents", []), {})
                harita["_host"] = h
                return harita
        except: continue
    return {}


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


def _overlay_state_temizle():
    """
    Sekme degisimi sirasinda onceki ekrandan kalan dialog/form state'lerini temizler.
    Streamlit bazen ayni rerun icinde eski DOM'u bir kare daha tuttugu icin,
    gecis oncesi state sifirlama kalinti riskini belirgin azaltir.
    """
    st.session_state["_edit_urun"] = None
    st.session_state["_urun_edit_dialog_acik"] = False
    st.session_state.pop("_sil_onay", None)
    st.session_state.pop("_onizleme_klasor", None)
    st.session_state.pop("_product_copy_preview", None)
    st.session_state.pop("_clipboard_copy_request", None)


def _tab_gecisinde_otomatik_yenilemeyi_atla() -> bool:
    """
    Ana tab degisiminden sonraki ilk render'da otomatik veri cekimini baskilar.
    Boylece kullanici once son bilinen veriyi gorur; arka plan sync bir sonraki
    dogal rerun'da veya manuel yenilemede calisir.
    """
    if not st.session_state.get("_suppress_tab_autorefresh_once"):
        return False
    st.session_state["_suppress_tab_autorefresh_once"] = False
    return True


def _main_tab_sec(tab_id: str):
    yeni_tab = str(tab_id or "").strip()
    if not yeni_tab or st.session_state.get("active_main_tab") == yeni_tab:
        return

    _overlay_state_temizle()
    st.session_state.urun_formu_acik = False
    st.session_state.satilan_urun_formu_acik = False
    st.session_state["_pending_urunler_alt_tab_render"] = None
    st.session_state["_pending_main_tab_render"] = yeni_tab
    st.session_state["_suppress_tab_autorefresh_once"] = True
    st.session_state.active_main_tab = yeni_tab


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


def _main_tab_gecis_ekrani():
    _tab_labels = {
        "urun_sec": "Ürün Seç",
        "urunler": "Ürünler",
        "olcu_ara": "Ölçü Ara",
        "kuyruk": "Kuyruk",
        "ayarlar": "Ayarlar",
        "notlar": "Notlar",
    }
    aktif_tab = str(st.session_state.get("active_main_tab") or "").strip()
    hedef_tab = str(st.session_state.get("_pending_main_tab_render") or "").strip()
    if not aktif_tab or hedef_tab != aktif_tab:
        return False

    baslik = _tab_labels.get(aktif_tab, "Sekme")
    with st.container(key=f"main_tab_transition_{aktif_tab}"):
        st.markdown(
            f"<div style='padding:4px 0 10px;font-size:0.95rem;font-weight:600;color:#e6edf3;'>{baslik}</div>",
            unsafe_allow_html=True,
        )
        _tab_loading_gostergesi(
            baslik,
            12,
            "Sekme hazırlanıyor. Eski içerik temizlenip yeni görünüm yüklenecek.",
            ready=False,
        )
        st.markdown(
            """
            <div style="min-height:520px;background:#0d1117;border:1px solid #21262d;border-radius:18px;
                        box-shadow:inset 0 1px 0 rgba(255,255,255,0.02);"></div>
            """,
            unsafe_allow_html=True,
        )

    st.session_state["_pending_main_tab_render"] = None
    _time.sleep(0.06)
    st.rerun()
    return True


def _urunler_alt_tab_gecis_ekrani():
    aktif_tab = str(st.session_state.get("urun_alt_tab") or "").strip()
    hedef_tab = str(st.session_state.get("_pending_urunler_alt_tab_render") or "").strip()
    if aktif_tab and hedef_tab == aktif_tab:
        st.session_state["_pending_urunler_alt_tab_render"] = None
    return False


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

if _main_tab_gecis_ekrani():
    st.stop()

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

    try:
        from shared.store_manager import get_store as _gs2
        _store_cfg = _gs2(st.session_state.hedef_magaza_id)
        _tmpl_id = _store_cfg.get("template", "default_v1")
        _template_cfg_raw = _template_json_oku(_tmpl_id)
        _template_cfg, _template_source = _template_session_overlay(
            _template_cfg_raw,
            st.session_state.hedef_magaza_id,
            _store_cfg.get("store_name", st.session_state.hedef_magaza_id),
        )
    except Exception:
        _template_cfg = {}
        _template_source = "fallback_empty"

    try:
        from shared.store_manager import get_store as _gs
        price_per_m2 = int(_gs(st.session_state.hedef_magaza_id).get("price_per_m2", 300))
    except Exception:
        price_per_m2 = 300

    ana_yol = ""
    _sk = SheetsKatmani(st.session_state.hedef_magaza_id)
    _sk.sheet_hazirla()
    _mevcut_sheet_kayitlari: dict[str, list[dict]] = {}
    for _sheet_satiri in _sk.tum_satirlar_al():
        _sheet_urun_id = str(_sheet_satiri.get("urun_id") or "").strip()
        _sheet_kod = _urun_kodu_normalize(_sheet_urun_id) or _urun_kodu_al(_sheet_urun_id)
        if not _sheet_kod:
            continue
        _mevcut_sheet_kayitlari.setdefault(_sheet_kod, []).append(_sheet_satiri)
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
                    _item_host = k.get("_pcloud_host") or host
                    r = httpx.get(f"{_item_host}/listfolder",
                                  params={"auth": token, "folderid": k["id"]},
                                  timeout=15)
                    d = r.json()
                    if d.get("result") != 0:
                        raise Exception(
                            f"pCloud klasörü açılamadı — result={d.get('result')}, "
                            f"hata='{d.get('error', '?')}', klasör_id={k['id']}"
                        )
                    dosyalar     = [f for f in d["metadata"].get("contents", []) if not f.get("isfolder")]
                    dosya_adlari = [f["name"] for f in dosyalar]

                    # Ürün kodu: Ölçü Ara'dan geldiyse direkt kullan.
                    # Yoksa: klasör içinde "KOD--...M2...FT.ext" kalıbında dosya ara,
                    # bulamazsan klasör adını kullan.
                    if k.get("_urun_kodu"):
                        secili_urun_kodu = str(k["_urun_kodu"]).strip()
                    else:
                        _bilgi_dosya_kodu = None
                        for _fn in dosya_adlari:
                            # Bilgi dosyası = ürün-kodu-- ile başlayan (m2 içersin ya da içermesin)
                            if "--" in _fn and ("m2" in _fn.lower() or "ft" in _fn.lower()):
                                _bilgi_prefix = _fn.split("--")[0].strip()
                                # "00_2259" gibi prefix'lerde gerçek kodu çıkar (00_ gibi sahte prefix'ler atlanır)
                                _bilgi_adaylar = _urun_kodu_adaylari(_bilgi_prefix)
                                _bilgi_dosya_kodu = _bilgi_adaylar[0] if _bilgi_adaylar else _bilgi_prefix
                                break
                        secili_urun_kodu = _bilgi_dosya_kodu if _bilgi_dosya_kodu else _guvenli_urun_kodu_bul(k["ad"], dosya_adlari)

                    secili_urun_kodu_norm = (
                        _urun_kodu_normalize(secili_urun_kodu)
                        or _urun_kodu_al(secili_urun_kodu)
                    )
                    mevcut_kayitlar = _mevcut_sheet_kayitlari.get(secili_urun_kodu_norm, [])
                    if mevcut_kayitlar:
                        mevcut_durumlar = sorted({
                            str((_kayit or {}).get("status") or "").strip().lower()
                            for _kayit in mevcut_kayitlar
                            if str((_kayit or {}).get("status") or "").strip()
                        })
                        durum_ozeti = ", ".join(mevcut_durumlar) if mevcut_durumlar else "bilinmeyen durum"
                        raise Exception(
                            f"{secili_urun_kodu}, {st.session_state.hedef_magaza_id} sheet'inde zaten mevcut "
                            f"({durum_ozeti}). Tekrar eklenemez."
                        )
                    st.write(f"✅ {len(dosyalar)} dosya bulundu")

                    st.write("📐 Boyut ve fiyat hesaplanıyor...")
                    urun_bilgisi = parse_urun_bilgisi(k["ad"], dosya_adlari)
                    urun_bilgisi["urun_id"] = secili_urun_kodu

                    # Boyut: parser bulamazsa ölçü ara tablosundaki bilinen değerleri kullan
                    if not urun_bilgisi.get("boyut_ft") and k.get("_size_ft"):
                        _ft_raw = str(k["_size_ft"]).replace("x", "x").strip()
                        urun_bilgisi["boyut_ft"] = _ft_raw
                        try:
                            _parts = _re.split(r"[xX×]", _ft_raw)
                            urun_bilgisi["genislik_ft"] = float(_parts[0].strip())
                            urun_bilgisi["uzunluk_ft"] = float(_parts[1].strip())
                        except Exception:
                            pass
                    if not urun_bilgisi.get("boyut_cm") and k.get("_size_cm"):
                        _cm_raw = str(k["_size_cm"]).strip()
                        urun_bilgisi["boyut_cm"] = _cm_raw
                        try:
                            _parts_cm = _re.split(r"[xX×]", _cm_raw)
                            _g_cm = float(_parts_cm[0].strip())
                            _u_cm = float(_parts_cm[1].strip())
                            urun_bilgisi["genislik_cm"] = _g_cm
                            urun_bilgisi["uzunluk_cm"] = _u_cm
                            if not urun_bilgisi.get("metrekare"):
                                urun_bilgisi["metrekare"] = round((_g_cm / 100) * (_u_cm / 100), 2)
                        except Exception:
                            pass

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
                        _satilan = _satilan_kodlar()
                        if _urun_kodu in _satilan:
                            raise Exception(f"⛔ Bu ürün SATILMIŞ ve klasörde resim yok. (KOD: {k['ad']})")
                        else:
                            raise Exception(f"⚠️ Klasörde resim bulunamadı! (KOD: {k['ad']})")
                    lr = httpx.get(f"{_item_host}/getfilelink",
                                   params={"auth": token, "fileid": foto_dosyalar[0]["fileid"]},
                                   timeout=10)
                    ld = lr.json()
                    resim_url = f"https://{ld['hosts'][0]}{ld['path']}"
                    st.write(f"✅ Fotoğraf: {foto_dosyalar[0]['name']}")

                    _satilan = _satilan_kodlar()
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
                        if ai.get("rate_limit"):
                            raise Exception(ai["hata"])
                        raise Exception(f"AI zorunlu alanlari gecemedi: {ai['hata']}")
                    if _template_source == "session_draft":
                        st.info("Bu ürün için ayarlardaki kaydedilmemiş description taslağı kullanıldı.")
                    st.write(f"✅ Başlık: {ai['baslik'][:60]}...")

                    st.write(f"📋 Sheets'e ekleniyor → {st.session_state.hedef_magaza_id}...")
                    pcloud_yol = f"{ana_yol}/{k['ad']}" if ana_yol else k["ad"]
                    satir_no = _sk.urun_ekle(urun_bilgisi, pcloud_yol, pcloud_klasor_id=k["id"])
                    st.write(f"💾 AI verileri yazılıyor (satır {satir_no})...")
                    _sk.ai_verileri_yaz(urun_bilgisi["urun_id"], ai, satir_no=satir_no)
                    _norm_key = _urun_kodu_normalize(secili_urun_kodu) or _urun_kodu_al(secili_urun_kodu)
                    st.session_state.kuyruga_eklenenler[_norm_key or secili_urun_kodu] = "ready"
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
    st.session_state["_reset_checkbox_ids"] = [
        str(_item["id"]) for _item in st.session_state.secilen
    ]
    st.session_state.secilen = []
    st.session_state["_secim_limit_hatasi"] = None
    if basarili:
        st.rerun(scope="app")
    # Tümü hata ise rerun yok — hata mesajları ekranda kalır


# ══ TAB 1 ════════════════════════════════════════════════════════════════════
if st.session_state.active_main_tab == "urun_sec":
    _aktif_magaza = str(st.session_state.get("hedef_magaza_id") or "").strip()
    if _aktif_magaza and st.session_state.get("pcloud_token"):
        _cache_var = _urun_sec_rozet_cache_uygula(_aktif_magaza)
        _rozet_hazir = (
            st.session_state.get("sheet_renk_magaza_id") == _aktif_magaza
            and bool(st.session_state.get("kuyruk_yuklendi"))
        )
        if not _rozet_hazir:
            _urun_sec_rozet_yenilemesini_baslat(_aktif_magaza, force=False)
        else:
            # _cache_var sadece dosya yeni uygulandiginda bir kerelik True olur;
            # periyodik sheet-degisim kontrolu buna bagli kalirsa rozetler donar kalir.
            _urun_sec_sheet_imza_kontrolunu_baslat(_aktif_magaza, force=False)

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
                        with st.spinner("Token doğrulanıyor..."):
                            _dogru_host, _tok_hata = _pcloud_token_dogrula(token_input.strip())
                        if not _dogru_host:
                            st.error(f"❌ Token doğrulanamadı: {_tok_hata}")
                        else:
                            st.session_state.pcloud_token = token_input.strip()
                            st.session_state["pcloud_host"] = _dogru_host
                            _token_kaydet(token_input.strip())
                            try:
                                from shared.sheets import config_yaz
                                config_yaz("PCLOUD_TOKEN", token_input.strip())
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
        @st.fragment
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

            def _klasorleri_yenile():
                _klasorleri_getir.clear()
                _klasor_icerigi_getir.clear()
                _klasor_meta_getir.clear()
                st.session_state.kuyruk_yuklendi = False
                st.session_state.kuyruk_klasor_durumlari = {}
                st.session_state.sheet_renk_durumlari = {}
                st.session_state.klasor_id_durumlari = {}
                _sheet_green_kodlari_cached.clear()
                _sheet_green_haritasi_cached.clear()
                _mevcut_magaza = str(st.session_state.get("hedef_magaza_id") or "").strip()
                if _mevcut_magaza:
                    st.session_state.pop(f"sheet_loaded_codes::{_mevcut_magaza}", None)
                    st.session_state.pop(f"sheet_loaded_codes::{_mevcut_magaza}::ts", None)
                    _urun_sec_rozet_yenilemesini_baslat(_mevcut_magaza, force=True)

            # Modül seviyesinde tanımlı _ai_kuyruga_ekle() kullanılır.

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
                    st.warning(
                        "Klasörler otomatik bulunamadı. pCloud'a geçici olarak ulaşılamamış "
                        "veya token yetkisiz olabilir. Tekrar deneyin; sorun sürerse çıkış yapıp "
                        "yeni token ile bağlanın."
                    )
                    st.button("🔄 Tekrar dene", key="magaza_bul_tekrar")
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
                    st.session_state.klasor_id,
                    _host_hint=host,
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
                                inferred_product_code = _klasor_urun_kodu_al(k["ad"])
                                is_folder_entry = str(k.get("entry_type") or "folder").strip().lower() == "folder"
                                is_product_folder = bool(
                                    is_folder_entry and (
                                        k.get("is_product_folder") is True
                                        or inferred_product_code is not None
                                        or known_folder_status is not None
                                        or known_sheet_color is not None
                                    )
                                )
                                row_item = {**k, "is_product_folder": is_product_folder}
                                _chk_key = f"chk_form_{k['id']}"
                                zaten_secili = k["id"] in secilen_ids
                                urun_kodu = inferred_product_code
                                satilmis_global = is_product_folder and _klasor_satilan_mi(k["ad"])
                                kuyruk_status = None
                                if is_product_folder:
                                    kuyruk_status = st.session_state.kuyruga_eklenenler.get(urun_kodu)
                                    if kuyruk_status is None:
                                        kuyruk_status = known_folder_status
                                sheet_renk = (
                                    _sheet_renk_durumu_klasor(k["id"], k["ad"], kuyruk_status)
                                    if is_product_folder
                                    else None
                                )
                                zaten_kuyrukta = (kuyruk_status is not None) or (sheet_renk is not None)
                                if satilmis_global or sheet_renk == "red":
                                    _ikon = "🔴"
                                elif sheet_renk == "green":
                                    _ikon = "✅"
                                elif sheet_renk == "blue":
                                    _ikon = "🔵"
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
                                st.caption("Klasör listesi hazır. Mağaza durum işaretleri arka planda yükleniyor; görünmeleri birkaç saniye sürebilir.")

                            for _row in _satir_meta:
                                k = _row["item"]
                                _c_chk, _c_name, _c_prev = st.columns([0.7, 9, 0.9], vertical_alignment="center")

                                with _c_chk:
                                    if _row["zaten_kuyrukta"]:
                                        st.markdown(
                                            f"<div class='urun-sec-status'>{_row['ikon']}</div>",
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
                                            label_visibility="collapsed",
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

                            _secili_harita = {
                                str(s.get("id")): s
                                for s in st.session_state.secilen
                                if str(s.get("id", "")).strip()
                            }
                            _senk_degisti = False
                            for _row in _satir_meta:
                                if _row["zaten_kuyrukta"]:
                                    continue
                                _item = dict(_row["item"])
                                _item_id = str(_item.get("id") or "").strip()
                                if not _item_id:
                                    continue
                                _is_checked = bool(st.session_state.get(_row["chk_key"]))
                                if _is_checked:
                                    mevcut = _secili_harita.get(_item_id)
                                    if mevcut is None or bool(mevcut.get("is_product_folder")) != bool(_item.get("is_product_folder")):
                                        _secili_harita[_item_id] = _item
                                        _senk_degisti = True
                                elif _item_id in _secili_harita:
                                    _secili_harita.pop(_item_id, None)
                                    _senk_degisti = True
                            if _senk_degisti:
                                st.session_state.secilen = list(_secili_harita.values())

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
        _tab_gecisinde_bekletme = _tab_gecisinde_otomatik_yenilemeyi_atla()
        if not _tab_gecisinde_bekletme:
            _magaza_hizli_arka_plan_sync_baslat(st.session_state.hedef_magaza_id, force=False)
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
            try:
                _store_status_auto_sync_green(st.session_state.hedef_magaza_id)
            except Exception:
                pass
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

        st.session_state["_urun_edit_dialog_acik"] = True
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
            st.session_state["_urun_edit_dialog_acik"] = False
            st.session_state["_edit_urun"] = None
            st.success("Kaydedildi. Kalıcı kayıt arka planda tamamlanıyor.")
            st.rerun()
        if _es2.button("İptal", use_container_width=True):
            st.session_state["_urun_edit_dialog_acik"] = False
            st.session_state["_edit_urun"] = None
            st.session_state.pop("_sil_onay", None)
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
                    st.session_state["_urun_katalog_cache_stok_mtime"] = 0.0
                    _urun_sil_arkaplanda(_silinecek_kod, mevcut_snapshot=mevcut)
                    st.session_state.pop("_sil_onay", None)
                    st.session_state["_urun_edit_dialog_acik"] = False
                    st.session_state["_edit_urun"] = None
                    st.session_state["_son_silinen_urun_kodu"] = _silinecek_kod
                    st.rerun()
                except Exception as exc:
                    st.error(f"{_silinecek_kod} silinemedi: {exc}")
            if _so2.button("Vazgeç", use_container_width=True):
                st.session_state.pop("_sil_onay", None)
                st.rerun()

    def _tab3_urunler():
        _tab_gecisinde_bekletme = _tab_gecisinde_otomatik_yenilemeyi_atla()
        # Bekleyen yenileme: form kapandıysa sessizce uygula
        _form_kapali = (
            not st.session_state.get("urun_formu_acik")
            and not st.session_state.get("_edit_urun")
        )
        if st.session_state.get("_urunler_pending_refresh") and _form_kapali:
            st.session_state["_urunler_pending_refresh"] = False

        _harita_file_ts = float((_canli_magaza_haritasi_dosyadan_yukle() or {}).get("updated_at") or 0)
        st.session_state.setdefault("_canli_harita_shown_ts", _harita_file_ts)
        _harita_stale_su_an = (_time.time() - _harita_file_ts) > _CANLI_HARITA_TTL_SN
        st.session_state["_urun_edit_dialog_acik"] = False

        _force_store_refresh = bool(st.session_state.pop("_urunler_store_refresh", False))
        _envanter_cache = _envanter_cache_dosyadan_yukle()
        _refresh_started = float(st.session_state.get("_urunler_magaza_refresh_started_at") or 0.0)
        _cache_updated = float((_envanter_cache or {}).get("updated_at") or 0.0)
        _magaza_refresh_suruyor = bool(_refresh_started and _refresh_started > _cache_updated)
        _urunler_loading_ui = bool(st.session_state.get("_urunler_loading_ui"))
        if st.session_state.get("_urun_katalog_cache") is None:
            _yerel_hizli_katalog = _panel_urunleri_yerden_yukle()
            if _yerel_hizli_katalog:
                st.session_state["_urun_katalog_cache"] = [dict(item) for item in _yerel_hizli_katalog]
                st.session_state["_urun_katalog_cache_ts"] = _time.time()
                st.session_state["_urun_katalog_cache_stok_mtime"] = 0.0
        _urunler_cache_var = st.session_state.get("_urun_katalog_cache") is not None
        _ilk_yukleme_bekleniyor = _urunler_loading_ui and not _urunler_cache_var
        if _ilk_yukleme_bekleniyor:
            _loading_percent = 20 if not _urunler_cache_var else 55
            _loading_mesaj = (
                "Mağaza yük durumları yükleniyor..."
                if not _urunler_cache_var
                else "Ürün listesi arka planda güncelleniyor."
            )
            _tab_loading_gostergesi("Ürünler", _loading_percent, _loading_mesaj, ready=False)
        if (
            not _tab_gecisinde_bekletme
            and (
                _force_store_refresh
                or _envanter_cache_stale_mi(_envanter_cache)
                or not ((_envanter_cache or {}).get("stores") or {})
            )
        ):
            _urunler_magaza_yenilemesini_baslat(force=_force_store_refresh)
            _refresh_started = float(st.session_state.get("_urunler_magaza_refresh_started_at") or 0.0)
            _magaza_refresh_suruyor = bool(_refresh_started and _refresh_started > float((_envanter_cache_dosyadan_yukle() or {}).get("updated_at") or 0.0))

        try:
            _katalog_cache_gecerli = (
                st.session_state.get("_urun_katalog_cache") is not None
                and (_time.time() - float(st.session_state.get("_urun_katalog_cache_ts") or 0)) <= 300
            )
            if _katalog_cache_gecerli:
                urunler = _urunleri_yukle(force_source_sync=False, force_store_refresh=_force_store_refresh)
            else:
                with st.spinner("Ürünler yükleniyor..."):
                    urunler = _urunleri_yukle(force_source_sync=False, force_store_refresh=_force_store_refresh)
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
            st.caption("Mağaza yük durumları güncelleniyor; yeşil noktalar ve yüklü sayıları birazdan tazelenecek.")
        if st.session_state.get("_urunler_pending_refresh"):
            st.caption("🔄 Arka planda yeni mağaza verisi hazır. Form kapandığında otomatik uygulanacak.")

        aktifler = [u for u in urunler if str(u.get("status", "")).lower() != "sold"]
        satilanlar = [u for u in urunler if str(u.get("status", "")).lower() == "sold"]

        _liste_aktif = st.session_state.urun_alt_tab == "liste"
        _satilan_aktif = st.session_state.urun_alt_tab == "satilan"
        _magazalar_aktif = st.session_state.urun_alt_tab == "magazalar"
        _silinecekler_aktif = st.session_state.urun_alt_tab == "silinecekler"
        _tabs_col, _stats_col, _refresh_col, _btn_col = st.columns(
            [4.8, 2.3, 1.15, 1.35], vertical_alignment="center"
        )
        with _tabs_col:
            _b1, _b2, _b3, _b4 = st.columns([1.05, 1.05, 1.0, 1.1], vertical_alignment="center")
            if _b1.button(
                "Ürün Listesi",
                key="urun_alt_tab_liste",
                width="stretch",
                type="primary" if _liste_aktif else "secondary",
                on_click=_urunler_alt_tab_sec,
                args=("liste",),
            ):
                pass
            if _b2.button(
                "Satılan Ürünler",
                key="urun_alt_tab_satilan",
                width="stretch",
                type="primary" if _satilan_aktif else "secondary",
                on_click=_urunler_alt_tab_sec,
                args=("satilan",),
            ):
                pass
            if _b3.button(
                "Mağazalar",
                key="urun_alt_tab_magazalar",
                width="stretch",
                type="primary" if _magazalar_aktif else "secondary",
                on_click=_urunler_alt_tab_sec,
                args=("magazalar",),
            ):
                pass
            if _b4.button(
                "Silinmesi Gerekenler",
                key="urun_alt_tab_silinecekler",
                width="stretch",
                type="primary" if _silinecekler_aktif else "secondary",
                on_click=_urunler_alt_tab_sec,
                args=("silinecekler",),
            ):
                pass
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
                _store_status_caches_temizle()
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

        if _urunler_alt_tab_gecis_ekrani():
            return

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
                                _urunleri_kaydet_arkaplanda([eklenen], incremental=True, sync_sheet=True, disk_snapshot=st.session_state.get("_urun_katalog_cache"))
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
                raw_id = str(urun.get("id", "")).strip()
                if raw_id.isdigit():
                    return (3, int(raw_id))
                raw_updated = str(urun.get("updated_at", "")).strip()
                if raw_updated:
                    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
                        try:
                            return (2, datetime.strptime(raw_updated, fmt).timestamp())
                        except Exception:
                            pass
                raw_source = str(urun.get("source_row", "")).strip()
                if raw_source.isdigit():
                    return (1, int(raw_source))
                return (0, 0)

            gosterilecek = sorted(gosterilecek, key=_aktif_urun_siralama, reverse=True)

            _sayfa_limiti = 500
            _filtre_aktif = bool(filtre.strip()) or kategori_filtre != "Tümü"
            _tumunu_goster = bool(st.session_state.get("_urunler_tumunu_goster"))
            if not _filtre_aktif and not _tumunu_goster and len(gosterilecek) > _sayfa_limiti:
                gosterilecek_render = gosterilecek[:_sayfa_limiti]
                _pg1, _pg2 = st.columns([5, 1])
                _pg1.caption(f"İlk {_sayfa_limiti} ürün gösteriliyor — toplam **{len(gosterilecek)}** aktif.")
                if _pg2.button("Tümünü Göster", key="tumunu_goster_btn", use_container_width=True):
                    st.session_state["_urunler_tumunu_goster"] = True
                    st.rerun()
            else:
                gosterilecek_render = gosterilecek

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

            canli_magaza_haritasi, _harita_guncelleniyor = _canli_magaza_haritasi_hazir(magaza_adlari)
            if _harita_guncelleniyor:
                st.caption("Mağaza yük durumları güncelleniyor, liste hazır...")

            try:
                import pandas as pd

                satirlar = []
                loaded_count_map = _store_status_loaded_counts_cached()
                gorunen_magaza_yuklu_sayilari = {magaza: 0 for magaza in magaza_adlari}
                _satilan_kumesi = set(st.session_state.get("satilan_kodlar_cache") or [])
                for urun in gosterilecek_render:
                    kod = _urun_kodu_normalize(urun.get("product_code", "")) or _urun_kodu_al(urun.get("product_code", ""))
                    _magaza_yuklu = {}
                    for magaza in magaza_adlari:
                        _sid = str(magaza or "").strip()
                        _magaza_yuklu[magaza] = bool(
                            kod and _sid
                            and kod not in _satilan_kumesi
                            and _sid in (canli_magaza_haritasi.get(kod, set()) or set())
                        )
                    satir = {
                        "Ürün Kodu": urun.get("product_code", ""),
                        "cm": urun.get("size_cm", ""),
                        "m2": urun.get("area_m2", ""),
                        "ft": urun.get("size_ft", ""),
                        "kategori": urun.get("category", ""),
                        "yüklü": sum(1 for v in _magaza_yuklu.values() if v),
                    }
                    for magaza in magaza_adlari:
                        yuklu_mu = _magaza_yuklu[magaza]
                        satir[magaza] = "🟢" if yuklu_mu else "⚪"
                        if yuklu_mu:
                            gorunen_magaza_yuklu_sayilari[magaza] += 1
                    satirlar.append(satir)

                if satirlar:
                    kolon_etiketleri = {}
                    for magaza in magaza_adlari:
                        kolon_sayisi = loaded_count_map.get(magaza)
                        if kolon_sayisi is None:
                            kolon_sayisi = gorunen_magaza_yuklu_sayilari.get(magaza, 0)
                        kolon_etiketleri[magaza] = f"{magaza} ({int(kolon_sayisi or 0)})"
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
                _urun_edit_dialog(st.session_state.get("_edit_urun"))

        if st.session_state.urun_alt_tab == "magazalar":
            st.markdown("##### Mağaza Yük Durumu")
            try:
                import pandas as pd
                from shared.store_manager import tum_magazalar as _tum_magaza_liste

                tum_magazalar = _tum_magaza_liste()
                magaza_ad_haritasi = {
                    str(item.get("store_id") or "").strip(): str(item.get("store_name") or item.get("store_id") or "").strip()
                    for item in tum_magazalar
                    if str(item.get("store_id") or "").strip()
                }
                store_rows = _store_status_rows_cached()
                loaded_counts = _store_status_loaded_counts_cached()
                pending_rows = _store_status_pending_delete_rows_cached()
                pending_counts: dict[str, int] = {}
                for row in pending_rows:
                    sid = str(row.get("store_id") or "").strip()
                    if sid:
                        pending_counts[sid] = pending_counts.get(sid, 0) + 1

                toplam_yuklu = sum(loaded_counts.values())
                toplam_silinecek = len(pending_rows)
                _m1, _m2 = st.columns(2)
                _m1.metric("Toplam Yüklü", toplam_yuklu)
                _m2.metric("Silinmesi Gereken", toplam_silinecek)

                magaza_ozet = []
                for store_id, store_name in sorted(magaza_ad_haritasi.items(), key=lambda item: item[1].lower()):
                    magaza_ozet.append({
                        "store_id": store_id,
                        "Mağaza": store_name,
                        "Yüklü": int(loaded_counts.get(store_id, 0)),
                        "Silinmesi Gereken": int(pending_counts.get(store_id, 0)),
                    })

                if magaza_ozet:
                    st.dataframe(pd.DataFrame([
                        {k: v for k, v in row.items() if k != "store_id"}
                        for row in magaza_ozet
                    ]), width="stretch", hide_index=True)

                secili_store = st.selectbox(
                    "Mağaza detayı",
                    options=[row["store_id"] for row in magaza_ozet],
                    format_func=lambda sid: f"{magaza_ad_haritasi.get(sid, sid)} ({loaded_counts.get(sid, 0)})",
                    index=0 if magaza_ozet else None,
                    placeholder="Bir mağaza seçin...",
                    key="urunler_magaza_detay_sec",
                )

                if secili_store:
                    urun_map = {
                        str(item.get("product_code") or "").strip(): dict(item)
                        for item in urunler
                        if str(item.get("product_code") or "").strip()
                    }
                    detay_satirlari = []
                    for row in store_rows:
                        sid = str(row.get("store_id") or "").strip()
                        if sid != secili_store or not _store_status_is_loaded(row):
                            continue
                        kod = _urun_kodu_normalize(row.get("product_code", "")) or _urun_kodu_al(row.get("product_code", ""))
                        urun = urun_map.get(kod, {})
                        reason = _store_status_delete_reason(row.get("status"))
                        if not reason and str(urun.get("status", "")).strip().lower() == "sold":
                            reason = "sold"
                        detay_satirlari.append({
                            "Ürün Kodu": kod,
                            "Durum": "Silinmeli" if reason else "Yüklü",
                            "Sebep": "Satıldı" if reason == "sold" else ("Panelden silindi" if reason == "deleted" else ""),
                            "Kategori": urun.get("category", ""),
                            "ft": urun.get("size_ft", ""),
                            "cm": urun.get("size_cm", ""),
                            "Güncelleme": row.get("islem_tarihi", ""),
                        })

                    detay_satirlari = sorted(detay_satirlari, key=lambda item: (item["Durum"], item["Ürün Kodu"]))
                    st.markdown(f"###### {magaza_ad_haritasi.get(secili_store, secili_store)}")

                    if secili_store == "DigerMagazalar":
                        st.caption("Bu sanal mağaza otomatik yükleme yapmaz. Dışarıda (Etsy harici) satışta olan ürünleri burada manuel işaretleyin.")
                        from shared.product_catalog import StoreCatalog as _StoreCatalogDM
                        _dm1, _dm2 = st.columns([3, 1])
                        with _dm1.form("diger_magazalar_ekle_form", clear_on_submit=True):
                            _dm_kod = st.text_input("Ürün kodu ekle", placeholder="Örn: D 149")
                            if st.form_submit_button("Yüklü olarak işaretle"):
                                _dm_kod_norm = _urun_kodu_normalize(_dm_kod) or _urun_kodu_al(_dm_kod)
                                if _dm_kod_norm:
                                    _StoreCatalogDM().upsert([{
                                        "product_code": _dm_kod_norm,
                                        "store_id": "DigerMagazalar",
                                        "status": "done",
                                        "renk": "green",
                                        "islem_tarihi": _time.strftime("%Y-%m-%d %H:%M"),
                                    }])
                                    _supabase_store_haritasi_cached.clear()
                                    st.success(f"{_dm_kod_norm} Diğer Mağazalar'da yüklü olarak işaretlendi.")
                                    st.rerun()
                                else:
                                    st.error("Geçerli bir ürün kodu girin.")
                        if detay_satirlari:
                            _dm_kaldir_secim = _dm2.selectbox(
                                "Kaldır",
                                options=[row["Ürün Kodu"] for row in detay_satirlari],
                                key="diger_magazalar_kaldir_sec",
                                label_visibility="visible",
                            )
                            if _dm2.button("Kaldır", key="diger_magazalar_kaldir_btn"):
                                _StoreCatalogDM().delete("DigerMagazalar", [_dm_kaldir_secim])
                                _supabase_store_haritasi_cached.clear()
                                st.success(f"{_dm_kaldir_secim} Diğer Mağazalar'dan kaldırıldı.")
                                st.rerun()

                    if detay_satirlari:
                        df_detay = pd.DataFrame(detay_satirlari)
                        st.dataframe(df_detay, width="stretch", hide_index=True)
                        st.download_button(
                            "CSV indir",
                            data=df_detay.to_csv(index=False).encode("utf-8-sig"),
                            file_name=f"{secili_store.lower()}-aktif-yuklu-urunler.csv",
                            mime="text/csv",
                            use_container_width=False,
                            key=f"indir_magaza_{secili_store}",
                        )
                    else:
                        st.info("Bu mağazada panelde yüklü ürün görünmüyor.")

                st.markdown("---")
                _etsy_csv_import_ui(tum_magazalar, magaza_ad_haritasi)

            except Exception as exc:
                st.warning(f"Mağazalar görünümü hazırlanamadı: {exc}")

        if st.session_state.urun_alt_tab == "silinecekler":
            st.markdown("##### Silinmesi Gerekenler")
            try:
                import pandas as pd
                from shared.store_manager import tum_magazalar as _tum_magaza_liste

                magaza_ad_haritasi = {
                    str(item.get("store_id") or "").strip(): str(item.get("store_name") or item.get("store_id") or "").strip()
                    for item in _tum_magaza_liste()
                    if str(item.get("store_id") or "").strip()
                }
                urun_map = {
                    str(item.get("product_code") or "").strip(): dict(item)
                    for item in urunler
                    if str(item.get("product_code") or "").strip()
                }
                pending_rows = _store_status_pending_delete_rows_cached()
                operasyon_satirlari = []
                operasyon_index = []
                for row in pending_rows:
                    kod = _urun_kodu_normalize(row.get("product_code", "")) or _urun_kodu_al(row.get("product_code", ""))
                    sid = str(row.get("store_id") or "").strip()
                    if not kod or not sid:
                        continue
                    urun = urun_map.get(kod, {})
                    reason = _store_status_delete_reason(row.get("status"))
                    operasyon_index.append({"product_code": kod, "store_id": sid})
                    operasyon_satirlari.append({
                        "Ürün Kodu": kod,
                        "Mağaza": magaza_ad_haritasi.get(sid, sid),
                        "Sebep": "Satıldı" if reason == "sold" else "Panelden silindi",
                        "Kategori": urun.get("category", ""),
                        "ft": urun.get("size_ft", ""),
                        "cm": urun.get("size_cm", ""),
                        "Satılan Site": _site_label(urun.get("sold_site", "")) if reason == "sold" else "",
                        "Kayıt": row.get("islem_tarihi", ""),
                    })

                if not operasyon_satirlari:
                    st.success("Silinmesi gereken bekleyen mağaza kaydı yok.")
                else:
                    df_ops = pd.DataFrame(operasyon_satirlari)
                    _op1, _op2 = st.columns([1.3, 4])
                    _op1.metric("Bekleyen kayıt", len(operasyon_satirlari))
                    _op2.caption("Kullanıcı Etsy'de sildikten sonra ilgili satırları seçip `Etsy'de sildim` ile aktif yükten düşürün.")
                    secim = st.dataframe(
                        df_ops,
                        width="stretch",
                        hide_index=True,
                        on_select="rerun",
                        selection_mode="multi-row",
                    )
                    st.download_button(
                        "CSV indir",
                        data=df_ops.to_csv(index=False).encode("utf-8-sig"),
                        file_name="silinmesi-gerekenler.csv",
                        mime="text/csv",
                        use_container_width=False,
                        key="indir_silinmesi_gerekenler",
                    )
                    secilen_indexler = secim.selection.rows if secim and getattr(secim, "selection", None) else []
                    if secilen_indexler:
                        if st.button("Etsy'de sildim", type="primary", width="stretch", key="etsyde_sildim_btn"):
                            _store_kaydini_yukluden_cikar_arkaplanda([
                                operasyon_index[idx]
                                for idx in secilen_indexler
                                if 0 <= idx < len(operasyon_index)
                            ])
                            st.success("Seçili kayıtlar aktif yüklü listesinden çıkarılıyor.")
                            st.rerun()
            except Exception as exc:
                st.warning(f"Silinmesi gerekenler görünümü hazırlanamadı: {exc}")

        if st.session_state.urun_alt_tab == "satilan":
            try:
                from shared.store_manager import tum_magazalar as _tum_satilan_magazalar
                satilan_site_opsiyonlari = [m.get("store_name") or m.get("store_id") for m in _tum_satilan_magazalar()]
            except Exception:
                satilan_site_opsiyonlari = []

            _satilan_form_acik = bool(st.session_state.satilan_urun_formu_acik)
            with st.container(border=True, key=f"satilan_urun_panel_{'open' if _satilan_form_acik else 'closed'}"):
                _sold_hdr, _sold_btn = st.columns([6, 1.4], vertical_alignment="center")
                _sold_hdr.markdown("##### Satılan Ürün Ekle")
                _sold_hdr.caption(
                    "Kapalıyken yer kaplamaz, gerektiğinde açıp kayıt girebilirsiniz."
                    if not _satilan_form_acik
                    else "Form açık. Kaydettikten sonra otomatik kapanır."
                )
                if _sold_btn.button(
                    "Aç" if not _satilan_form_acik else "Kapat",
                    key="satilan_urun_form_toggle_btn",
                    use_container_width=True,
                ):
                    st.session_state.satilan_urun_formu_acik = not _satilan_form_acik
                    st.rerun()

            if _satilan_form_acik:
                with st.container(border=True, key="satilan_urun_form_panel"):
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
                        _sk1, _sk2, _sk3 = st.columns(3)
                        kargo_firma = _sk1.selectbox(
                            "Kargo firması",
                            options=["FEDEX", "UPS"],
                            index=None,
                            placeholder="Seçin (opsiyonel)...",
                        )
                        kargo_tl = _sk2.number_input("Kargo (TL)", min_value=0.0, step=1.0, format="%.2f")
                        kargo_usd = _sk3.number_input("Kargo (USD)", min_value=0.0, step=1.0, format="%.2f")
                        musteri_adres = st.text_area("Adres", height=90)
                        satilan_not = st.text_input("Not")
                        submit_sold = st.form_submit_button("🟥 Satılan Ürünü Kaydet", type="primary", width="stretch")

                if submit_sold:
                    kod = secili.split("|", 1)[0].strip() if secili else None
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
                                copy["shipping_carrier"] = (kargo_firma or "").strip()
                                copy["shipping_cost_try"] = _kargo_para_str(kargo_tl)
                                copy["shipping_cost_usd"] = _kargo_para_str(kargo_usd)
                                if satilan_not.strip():
                                    copy["note"] = satilan_not.strip()
                                copy["updated_at"] = _time.strftime("%Y-%m-%d %H:%M")
                                secili_urun = copy
                                yeni_liste.append(copy)
                            else:
                                yeni_liste.append(urun)
                        if secili_urun:
                            from shared.product_catalog import ProductCatalog, _supabase_ready
                            _kayit_hatasi = None
                            if _supabase_ready():
                                try:
                                    # PATCH: sadece satış alanlarını güncelle (upsert'ten daha güvenilir)
                                    ProductCatalog().sell_product(
                                        kod,
                                        sold_at=secili_urun.get("sold_at"),
                                        sold_site=secili_urun.get("sold_site"),
                                        customer_name=secili_urun.get("customer_name"),
                                        customer_phone=secili_urun.get("customer_phone"),
                                        customer_address=secili_urun.get("customer_address"),
                                        customer_contact_country=secili_urun.get("customer_contact_country"),
                                        note=secili_urun.get("note"),
                                        shipping_carrier=secili_urun.get("shipping_carrier"),
                                        shipping_cost_try=secili_urun.get("shipping_cost_try"),
                                        shipping_cost_usd=secili_urun.get("shipping_cost_usd"),
                                    )
                                except Exception as _e:
                                    _kayit_hatasi = str(_e)
                            else:
                                try:
                                    _urunleri_kaydet(yeni_liste)
                                except Exception as _e:
                                    _kayit_hatasi = str(_e)
                            if _kayit_hatasi:
                                # st.toast reruns'da da görünür
                                st.toast(f"⚠️ Kayıt hatası: {_kayit_hatasi}", icon="🔴")
                                st.error(f"Supabase kayıt hatası: {_kayit_hatasi}")
                                st.stop()
                            _urunleri_cachede_uste_tut(secili_urun)
                            _bekleyen_urun_override_kaydet(secili_urun)
                            _urun_sheet_sync_arkaplanda(
                                force=True,
                                products=st.session_state.get("_urun_katalog_cache"),
                            )
                            _supabase_store_haritasi_cached.clear()
                            _store_delete_kuyruguna_ekle_arkaplanda([kod], reason="sold")
                            st.session_state.satilan_urun_formu_acik = False
                            st.success(f"{kod} satılan ürünlere eklendi.")
                            diger_yuklu_magazalar = [
                                magaza for magaza in _urunun_tum_yuklu_magazalari(kod)
                                if str(magaza or "").strip() not in {str(item or "").strip() for item in satilan_site}
                            ]
                            if diger_yuklu_magazalar:
                                st.info(f"Diğer yüklü mağazalar: {', '.join(diger_yuklu_magazalar)}")
                            else:
                                st.info("Başka yüklü mağaza görünmüyor.")
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

                ad_haritasi = _magaza_ad_haritasi()
                store_map = _supabase_store_haritasi_cached()

                satilan_satirlar = []
                for urun in satilan_goster:
                    kod = _urun_kodu_normalize(urun.get("product_code", "")) or _urun_kodu_al(urun.get("product_code", ""))
                    satilan_site_listesi = [
                        str(parca or "").strip()
                        for parca in str(urun.get("sold_site", "")).split(",")
                        if str(parca or "").strip()
                    ]
                    satilan_site_kumesi = {
                        str(site or "").strip()
                        for site in satilan_site_listesi
                        if str(site or "").strip()
                    }
                    diger_yuklu_magazalar = [
                        ad_haritasi.get(store_id, store_id)
                        for store_id in (store_map.get(kod, ()) or ())
                        if str(store_id or "").strip() not in satilan_site_kumesi
                        and str(ad_haritasi.get(store_id, store_id) or "").strip() not in satilan_site_kumesi
                    ]
                    satilan_satirlar.append({
                        "Ürün Kodu": urun.get("product_code", ""),
                        "cm": urun.get("size_cm", ""),
                        "m2": urun.get("area_m2", ""),
                        "ft": urun.get("size_ft", ""),
                        "kategori": urun.get("category", ""),
                        "satılan_tarih": urun.get("sold_at", ""),
                        "site": _site_label(urun.get("sold_site", "")),
                        "kargo": urun.get("shipping_carrier") or "",
                        "kargo_TL": urun.get("shipping_cost_try") or "",
                        "kargo_USD": urun.get("shipping_cost_usd") or "",
                        "müşteri": urun.get("customer_name", ""),
                        "telefon": urun.get("customer_phone", ""),
                        "iletişim_ülke": urun.get("customer_contact_country", ""),
                        "adres": urun.get("customer_address", ""),
                        "diğer_yüklü_mağazalar": ", ".join(diger_yuklu_magazalar),
                        "not": urun.get("note", ""),
                    })

                if satilan_satirlar:
                    # Aylik kargo ozeti (Excel'deki aylik toplamlarin panel karsiligi)
                    _aylik_ozet = {}
                    _aylik_sira = []
                    for urun in satilan_goster:
                        _ay_key = _satilan_ay_etiketi(urun.get("sold_at", ""))
                        if _ay_key not in _aylik_ozet:
                            _aylik_ozet[_ay_key] = {"adet": 0, "tl": 0.0, "usd": 0.0}
                            _aylik_sira.append(_ay_key)
                        _aylik_ozet[_ay_key]["adet"] += 1
                        _aylik_ozet[_ay_key]["tl"] += _float_or_none(urun.get("shipping_cost_try")) or 0.0
                        _aylik_ozet[_ay_key]["usd"] += _float_or_none(urun.get("shipping_cost_usd")) or 0.0
                    if _aylik_sira:
                        _ozet_satirlar = [
                            {
                                "Ay": _ay,
                                "Satış Adedi": _aylik_ozet[_ay]["adet"],
                                "Kargo Toplam (TL)": round(_aylik_ozet[_ay]["tl"], 2),
                                "Kargo Toplam (USD)": round(_aylik_ozet[_ay]["usd"], 2),
                            }
                            for _ay in _aylik_sira
                        ]
                        with st.expander("📊 Aylık satış & kargo özeti", expanded=False):
                            st.dataframe(pd.DataFrame(_ozet_satirlar), width="stretch", hide_index=True)

                    _sat_secim = st.dataframe(
                        pd.DataFrame(satilan_satirlar),
                        width="stretch",
                        hide_index=True,
                        on_select="rerun",
                        selection_mode="single-row",
                        key="satilan_urun_tablosu",
                    )
                    _sat_secili_satirlar = (
                        _sat_secim.selection.rows
                        if _sat_secim and hasattr(_sat_secim, "selection")
                        else []
                    )
                    if _sat_secili_satirlar:
                        _sat_kod = satilan_satirlar[_sat_secili_satirlar[0]]["Ürün Kodu"]
                        _sat_urun = next(
                            (u for u in satilanlar if u.get("product_code") == _sat_kod),
                            None,
                        )
                        if _sat_urun:
                            st.markdown("<div style='height:6px;'></div>", unsafe_allow_html=True)
                            _sab1, _sab2, _sab3 = st.columns([1.4, 1.6, 3.0])
                            if _sab1.button(
                                f"✏️ {_sat_kod} Düzenle",
                                type="primary",
                                use_container_width=True,
                                key="satilan_duzenle_btn",
                            ):
                                st.session_state["_edit_satilan"] = _sat_urun
                                st.session_state.pop("_satilan_stok_onay", None)
                                st.rerun()
                            if not st.session_state.get("_satilan_stok_onay"):
                                if _sab2.button(
                                    "📦 Stoğa Geri Al",
                                    use_container_width=True,
                                    key="satilan_stoga_al_btn",
                                ):
                                    st.session_state["_satilan_stok_onay"] = _sat_kod
                                    st.rerun()
                            elif st.session_state.get("_satilan_stok_onay") == _sat_kod:
                                _so1, _so2 = _sab2.columns(2)
                                if _so1.button("Evet", type="primary", use_container_width=True, key="satilan_stok_evet"):
                                    _satilan_stoga_geri_al(_sat_urun)
                                    st.session_state.pop("_satilan_stok_onay", None)
                                    st.success(f"{_sat_kod} tekrar stoğa alındı.")
                                    st.rerun()
                                if _so2.button("Vazgeç", use_container_width=True, key="satilan_stok_vazgec"):
                                    st.session_state.pop("_satilan_stok_onay", None)
                                    st.rerun()
                            if st.session_state.get("_satilan_stok_onay") == _sat_kod:
                                st.warning(
                                    f"**{_sat_kod}** satılanlardan çıkarılıp tekrar stokta görünecek; "
                                    "satış/müşteri/kargo bilgileri temizlenir. Excel'de de otomatik güncellenir."
                                )
                else:
                    st.info("Satılan ürün bulunamadı.")

                if st.session_state.get("_edit_satilan"):
                    _satilan_edit_dialog(st.session_state.get("_edit_satilan"))
            except Exception as exc:
                st.warning(f"Satılan ürün listesi çizilemedi: {exc}")

        # Arka planda harita güncellenince otomatik rerun (her 5 saniyede dosya mtime kontrolü)
        if not _tab_gecisinde_bekletme:
            _harita_degisim_izleyici()
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
            from modules.ai_icerik import (
                template_config_normallestir as _tmpl_norm,
                _ornek_desci_dinamik_sablona_cevir as _desc_to_dynamic_template,
            )
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

            def _preview_text_to_template(_text, _cfg):
                _raw = str(_text or "")
                if "{" in _raw and "}" in _raw:
                    return _raw

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
                _hikaye = "\n\n".join([
                    "Some rugs just fill a space. This brings soul. Its faded palette and floral movement feel quietly collected rather than loud.",
                    _story_size,
                    "Handwoven wool gives it an honest, tactile surface that feels warm underfoot and visually rich in layered interiors.",
                    "It suits bohemian, antique, collected, and soft traditional spaces while still feeling easy to place in daily life.",
                ])
                _replacements = [
                    (_opening, "{opening}"),
                    (_details, "{details_block}"),
                    (_hikaye, "{hikaye}"),
                    (_render_preview_text(_cfg["static_texts"].get("no_extra_fees", ""), _ctx), "{no_extra_fees_block}"),
                    (_render_preview_text(_cfg["static_texts"].get("easy_returns", ""), _ctx), "{easy_returns_block}"),
                    (_render_preview_text(_cfg["static_texts"].get("footer", ""), _ctx), "{footer_block}"),
                    (_story_size, "{story_size_paragraph}"),
                    (_ctx["rounded_ft_label"], "{rounded_ft_label}"),
                    (_ctx["rounded_ft"], "{rounded_ft}"),
                    (_ctx["boyut_ft"], "{boyut_ft}"),
                    (_ctx["boyut_cm"], "{boyut_cm}"),
                    (_ctx["metrekare"], "{metrekare}"),
                    (_ctx["sqft"], "{sqft}"),
                    (_ctx["urun_id"], "{urun_id}"),
                    (_ctx["tip_lower"], "{tip_lower}"),
                    (_ctx["tip"], "{tip}"),
                    (_ctx["renk_scheme"], "{renk_scheme}"),
                    (_ctx["renk1"], "{renk1}"),
                    (_ctx["renk2"], "{renk2}"),
                    (_ctx["pattern"], "{pattern}"),
                    (_ctx["tahmini_yil"], "{tahmini_yil}"),
                    (_ctx["stil"], "{stil}"),
                    (_ctx["koken"], "{koken}"),
                    (_ctx["home_style"], "{home_style}"),
                    (_ctx["shop_section"], "{shop_section}"),
                    (_ctx["ana_resim_tag"], "{ana_resim_tag}"),
                    (_ctx["baslik"], "{baslik}"),
                ]
                _converted = _raw
                for _from, _to in sorted(_replacements, key=lambda item: len(item[0]), reverse=True):
                    if _from:
                        _converted = _converted.replace(_from, _to)
                if any(token in _converted for token in [
                    "{opening}", "{hikaye}", "{urun_id}", "{boyut_cm}", "{boyut_ft}",
                    "{rounded_ft_label}", "{renk_scheme}", "{pattern}", "{tip}",
                ]):
                    return _converted
                return _desc_to_dynamic_template(_converted)

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
                    "description_brief": _pr.get("description_brief", ""),
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
                    # Mağazaya özel template kaydederken normalize şişirmesini engelle:
                    # _tmpl_text zaten normalize edilmiş config (tüm default kurallar yüklü).
                    # Bunun yerine ham dosyayı oku; sadece description alanlarını güncelle.
                    _template_id = str(_kayit.get("template_id") or "").strip()
                    _ham = _template_json_oku(_template_id) if _template_id else {}
                    if not _ham:
                        # Ham dosya okunamazsa normalize versiyonu kullan ama küçült
                        _ham = {
                            "template_id": _kayit.get("template_id", _template_id),
                            "template_name": _kayit.get("template_name", _store_id),
                        }
                        # static_texts: sabit_* (eski format) → static_texts'e aktar
                        for _eski, _yeni in [
                            ("sabit_no_extra_fees", "no_extra_fees"),
                            ("sabit_easy_returns",  "easy_returns"),
                            ("sabit_alt",           "footer"),
                        ]:
                            if _eski in _kayit:
                                _ham.setdefault("static_texts", {})[_yeni] = _kayit[_eski]
                        if "static_texts" in _kayit and isinstance(_kayit["static_texts"], dict):
                            _ham.setdefault("static_texts", {}).update(_kayit["static_texts"])
                        # Mağaza özel prompt kurallarını (varsa) taşı
                        for _kural in ("title_brief", "tag_strategy", "opening_rules", "story_rules"):
                            _v = str((_kayit.get("prompt_rules") or {}).get(_kural, "") or "").strip()
                            if _v:
                                _ham.setdefault("prompt_rules", {})[_kural] = _v

                    # Eski sabit_* format varsa static_texts'e dönüştür (migration)
                    for _eski, _yeni in [
                        ("sabit_no_extra_fees", "no_extra_fees"),
                        ("sabit_easy_returns",  "easy_returns"),
                        ("sabit_alt",           "footer"),
                    ]:
                        if _eski in _ham:
                            _ham.setdefault("static_texts", {})[_yeni] = _ham.pop(_eski)

                    # Sadece description alanlarını güncelle
                    _desc_tmpl = _preview_text_to_template(
                        st.session_state.get(f"editor_{_store_id}_description_example_template", ""),
                        _kayit,  # normalize edilmiş config — placeholder context için
                    )
                    _ham.setdefault("prompt_rules", {})
                    _ham["prompt_rules"]["description_brief"] = st.session_state.get(
                        f"editor_{_store_id}_description_brief", ""
                    )
                    _ham["prompt_rules"]["description_example_template"] = _desc_tmpl
                    return _ham
                return _kayit

            def _json_editor_key(_store_id, _template_id):
                return f"tj_{_store_id}_{_template_id}"

            def _aktif_template_taslagi(_tmpl_text, _store_id, _template_id):
                _json_key = _json_editor_key(_store_id, _template_id)
                _json_text = str(st.session_state.get(_json_key, "") or "").strip()
                if _json_text and _json_text != str(_tmpl_text or "").strip():
                    return _json2.loads(_json_text)
                return _template_editor_payload(_tmpl_text, _store_id)

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
                        "description_brief": st.session_state.get(
                            f"editor_{_store_id}_description_brief",
                            _cfg["prompt_rules"].get("description_brief", "")
                        ),
                        "description_example_template": _preview_text_to_template(
                            st.session_state.get(
                                f"editor_{_store_id}_description_example_template",
                                _cfg["prompt_rules"].get("description_example_template", "") or _default_preview_framework(_cfg)
                            ),
                            _cfg,
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
                    _tmpl_raw = _template_json_oku(_secili.get("template", "default_v1"))
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
                st.caption(
                    "Soldaki yesil durum sadece Google Sheet erisimini gosterir: "
                    "magaza ortak sheet icindeki kendi sekmesine baglanabiliyor demektir. "
                    "Worker aktif/pasif durumu ayri gosterilir."
                )
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
                    _sheet_durum = _sheet_baglanti_durumu(
                        _m["store_id"],
                        _m.get("google_sheet_id") or "",
                        _m.get("sheet_tab", _m["store_id"]),
                    )
                    _aktif_ikon = "🟢" if _sheet_durum.get("ok") else "⬜"
                    _worker_etiket = "aktif" if _m.get("active") else "pasif"
                    _is_selected = st.session_state.ayar_magaza_id == _m["store_id"]
                    st.button(
                        f"{_aktif_ikon} {_m['store_name']} · worker {_worker_etiket}",
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
                        _sheet_durum = _sheet_baglanti_durumu(
                            _secili["store_id"],
                            _secili.get("google_sheet_id") or "",
                            _secili.get("sheet_tab", _secili["store_id"]),
                        )
                        if _sheet_durum.get("ok"):
                            st.success(f"Google Sheet baglantisi hazir: {_sheet_durum.get('reason')}")
                        else:
                            st.warning(f"Google Sheet bagli degil: {_sheet_durum.get('reason')}")
                        st.caption(
                            "Worker durumu ayridir: "
                            + ("aktif" if _secili.get("active") else "pasif")
                            + " (`stores.json > active`)."
                        )
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
                                if _tmpl_path is not None:
                                    _norm = _tmpl_norm(
                                        _aktif_template_taslagi(_tmpl_json, _secili["store_id"], _secili.get("template", "default_v1")),
                                        template_id=_nt,
                                        template_name=_m_name.strip() or _secili["store_id"],
                                    )
                                    _, _s_ok, _s_err = _template_json_kaydet(_nt, _norm)
                                    if not _s_ok:
                                        st.warning(f"⚠️ Template JSON dosyasına kaydedildi ancak Sheets config güncellenemedi: {_s_err or 'bilinmeyen hata'}")
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
                                    _aktif_template_taslagi(_tmpl_json, _secili["store_id"], _secili.get("template", "default_v1")),
                                    template_id=_tmpl_cfg["template_id"],
                                    template_name=_tmpl_cfg["template_name"],
                                )
                                _kaydedilen_path, _s_ok, _s_err = _template_json_kaydet(_tmpl_cfg["template_id"], _norm)
                                if not _s_ok:
                                    st.warning(f"⚠️ Dosyaya kaydedildi ancak Sheets config güncellenemedi: {_s_err or 'bilinmeyen hata'}")
                                st.success(f"✅ Template kaydedildi: {_kaydedilen_path.name}")
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
                                    help=(
                                        "Şablona her zaman {opening} ve {hikaye} ekle — bunlar AI'dan gelir ve ürüne özeldir.\n"
                                        "Diğer bloklar: {no_extra_fees_block}, {details_block}, {easy_returns_block}, {footer_block}\n"
                                        "Ürün alanları: {tip}, {renk_scheme}, {pattern}, {koken}, {rounded_ft_label}, {boyut_cm}, {urun_id}, {pile_bullet}"
                                    )
                                )
                                st.caption(
                                    "**Zorunlu (AI üretir):** `{opening}` `{hikaye}` — "
                                    "**Bloklar:** `{no_extra_fees_block}` `{details_block}` `{easy_returns_block}` `{footer_block}` — "
                                    "**Ürün:** `{tip}` `{renk_scheme}` `{pattern}` `{koken}` `{rounded_ft_label}` `{boyut_cm}` `{urun_id}` `{pile_bullet}`"
                                )
                                _pe1, _pe2 = st.columns([1, 1])
                                _kaydetildi = _pe1.form_submit_button("💾 Ön İzlemeyi Kaydet", type="primary")
                                _iptal = _pe2.form_submit_button("Vazgeç")
                                if _kaydetildi:
                                    _norm = _tmpl_norm(
                                        _aktif_template_taslagi(_tmpl_json, _secili["store_id"], _secili.get("template", "default_v1")),
                                        template_id=_tmpl_cfg["template_id"],
                                        template_name=_tmpl_cfg["template_name"],
                                    )
                                    _kp, _s_ok, _s_err = _template_json_kaydet(_tmpl_cfg["template_id"], _norm)
                                    if not _s_ok:
                                        st.warning(f"⚠️ Dosyaya kaydedildi ancak Sheets config güncellenemedi: {_s_err or 'bilinmeyen hata'}")
                                    _toggle_preview_edit(_secili["store_id"], False)
                                    st.success(f"✅ Ön izleme şablonu kaydedildi: {_tmpl_cfg['template_id']}.json")
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
                            st.info("Bu mağaza için description brief ve beklenen description şeması ayrı yönetilir. Title, tag ve diğer AI kuralları ortak `default_v1` üzerinden gelir.")
                            st.text_area(
                                "Mağazaya Özel Description Talimatı",
                                key=f"editor_{_secili['store_id']}_description_brief",
                                height=110,
                                help="Bu mağazanın description tonu, vurgu alanı ve anlatım tarzı için AI'ye özel not bırakın."
                            )
                            st.markdown("##### Description Yapısı")
                            st.caption("Bu mağaza için AI'nin beklediği description şeması burada özelleşir. Düzenlemek için Ön İzleme sekmesindeki Edit butonunu kullan.")

                        if st.button("💾 AI Metin Ayarlarını Kaydet", key=f"save_text_editor_{_secili['store_id']}", type="primary"):
                            _norm = _tmpl_norm(
                                _aktif_template_taslagi(_tmpl_json, _secili["store_id"], _secili.get("template", "default_v1")),
                                template_id=_tmpl_cfg["template_id"],
                                template_name=_tmpl_cfg["template_name"],
                            )
                            _kaydedilen_path, _s_ok, _s_err = _template_json_kaydet(_tmpl_cfg["template_id"], _norm)
                            if not _s_ok:
                                st.warning(f"⚠️ Dosyaya kaydedildi ancak Sheets config güncellenemedi: {_s_err or 'bilinmeyen hata'}")
                            st.success(f"✅ Template kaydedildi: {_kaydedilen_path.name}")
                            st.rerun()

                    if st.session_state.ayarlar_template_tab == "json":
                        st.caption("İleri seviye düzenleme. Gerekmedikçe Text Gör sekmesini kullanın.")
                        _tmpl_text = st.text_area(
                            "Template JSON",
                            value=_tmpl_json,
                            height=620,
                            key=_json_editor_key(_secili['store_id'], _secili.get('template', 'default_v1')),
                        )
                        if st.button("💾 JSON Template Kaydet", key=f"mts_{_secili['store_id']}"):
                            try:
                                _kaydedilecek = _json2.loads(_tmpl_text)
                                _norm = _tmpl_norm(
                                    _kaydedilecek,
                                    template_id=_secili.get("template", "default_v1"),
                                    template_name=_secili.get("store_name", _secili["store_id"]),
                                )
                                _kaydedilen_path, _s_ok, _s_err = _template_json_kaydet(_secili.get("template", "default_v1"), _norm)
                                if not _s_ok:
                                    st.warning(f"⚠️ Dosyaya kaydedildi ancak Sheets config güncellenemedi: {_s_err or 'bilinmeyen hata'}")
                                st.success(f"✅ Template kaydedildi: {_kaydedilen_path.name}")
                                st.rerun()
                            except Exception as _e_tmpl:
                                st.error(f"❌ Template kaydedilemedi: {_e_tmpl}")

        except Exception as _e3:
            st.error(f"Mağaza yönetimi yüklenemedi: {_e3}")


# ══ TAB 5 ════════════════════════════════════════════════════════════════════
if st.session_state.active_main_tab == "olcu_ara":
    def _tab5_ara():
        import pandas as pd
        _tab_gecisinde_bekletme = _tab_gecisinde_otomatik_yenilemeyi_atla()

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
            _olcu_ara_urunleri_yukle_cached.clear()
            _olcu_ara_kaynaklari_cached.clear()
            st.rerun()
        _gc2.caption("Kaynak: Supabase `products` tablosu. Supabase yoksa urun katalog sheet fallback kullanilir.")

        try:
            if _tab_gecisinde_bekletme and st.session_state.get("_urun_katalog_cache") is not None:
                _olcu_payload = {
                    "source": "session_product_cache",
                    "products": _silinenleri_filtrele(st.session_state.get("_urun_katalog_cache") or []),
                }
            else:
                _olcu_payload = _olcu_ara_urunleri_yukle_cached()
            katalog_urunleri = list(_olcu_payload.get("products") or [])
            _olcu_source = str(_olcu_payload.get("source") or "supabase")
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

        _toplam = int(_olcu_kaynak.get("toplam") or len(katalog_urunleri))
        _satilan = int(_olcu_kaynak.get("satilan") or 0)
        _aktif_toplam = max(_toplam - _satilan, len(arama_kaynaklari))
        _kaynak_etiketi = (
            "session urun cache"
            if _olcu_source == "session_product_cache"
            else ("Supabase products" if _olcu_source == "supabase" else "urun katalog sheet")
        )
        st.caption(
            f"Kaynak: {_kaynak_etiketi}"
            f"  |  Aktif katalog: **{_aktif_toplam}**"
            f"  |  Olcu aramaya uygun: {len(arama_kaynaklari)}"
            f"  |  Ft olcusu eksik oldugu icin atlanan: {atlanan_ft}"
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
                                klasor_harita = _magaza_klasor_haritasi(token_t4, host_t4, magaza_id)

                            if not klasor_harita:
                                st.warning(f"{secilen_magaza_adi} içinde ürün bulunamadı.")
                            else:
                                kontrol = [
                                    {
                                        "Seç": False,
                                        **e,
                                        "Mağaza Durumu": "✅ Var" if _kod_normalize(e["KOD"]) in klasor_harita else "❌ Yok",
                                    }
                                    for e in eslesmeler
                                ]
                                var_sayisi = sum(1 for s in kontrol if "✅" in s["Mağaza Durumu"])
                                st.success(f"**{secilen_magaza_adi}**: {var_sayisi}/{len(kontrol)} ürün mevcut")
                                st.session_state["_olcu_magaza_klasor_haritasi"] = klasor_harita
                                st.session_state["_olcu_magaza_kontrol_sonucu"] = kontrol

                        kontrol_sonucu = st.session_state.get("_olcu_magaza_kontrol_sonucu") or []
                        if kontrol_sonucu:
                            df_kontrol = pd.DataFrame(kontrol_sonucu)
                            disabled_cols = [c for c in df_kontrol.columns if c != "Seç"]
                            edited = st.data_editor(
                                df_kontrol,
                                width="stretch",
                                hide_index=True,
                                column_config={
                                    "Seç": st.column_config.CheckboxColumn("Seç", width="small"),
                                    "KOD": st.column_config.TextColumn("KOD", width="small"),
                                    "CM": st.column_config.TextColumn("CM", width="small"),
                                    "FT": st.column_config.TextColumn("FT", width="medium"),
                                    "Tür": st.column_config.TextColumn("Tür", width="small"),
                                    "Yüklü": st.column_config.NumberColumn("Yüklü", format="%d", width="small"),
                                    "Yüklü Mağazalar": st.column_config.TextColumn("Yüklü Mağazalar", width="medium"),
                                    "Not": st.column_config.TextColumn("Not", width="medium"),
                                    "Δ (ft)": st.column_config.NumberColumn("Δ ft", format="%.2f", width="small"),
                                    "Mağaza Durumu": st.column_config.TextColumn("Mağaza Durumu", width="small"),
                                },
                                disabled=disabled_cols,
                                key="olcu_kontrol_editor",
                            )

                            secilen_satirlar = edited[
                                (edited["Seç"] == True) & (edited["Mağaza Durumu"] == "✅ Var")
                            ]
                            secilen_yok = edited[
                                (edited["Seç"] == True) & (edited["Mağaza Durumu"] == "❌ Yok")
                            ]
                            if not secilen_yok.empty:
                                st.caption("⚠️ Mağazada ❌ Yok olan ürünler seçildi — bunlar pCloud klasörü bulunamadığı için kuyruğa eklenemez, atlanacak.")

                            if not secilen_satirlar.empty:
                                _klasor_harita = st.session_state.get("_olcu_magaza_klasor_haritasi") or {}
                                _pcloud_host = _klasor_harita.get("_host") or st.session_state.get("pcloud_host", "https://api.pcloud.com")
                                _secilecek = []
                                for _, satir in secilen_satirlar.iterrows():
                                    _norm = _kod_normalize(str(satir["KOD"]))
                                    _klasor = _klasor_harita.get(_norm)
                                    if _klasor:
                                        _secilecek.append({
                                            "id": _klasor["id"],
                                            "ad": _klasor["ad"],
                                            "_pcloud_host": _pcloud_host,
                                            "_urun_kodu": str(satir["KOD"]).strip(),
                                            "_size_cm": str(satir.get("CM") or "").strip(),
                                            "_size_ft": str(satir.get("FT") or "").strip(),
                                        })

                                if _secilecek:
                                    if st.button(
                                        f"🤖 AI ile Kuyruğa Ekle ({len(_secilecek)} ürün) → {st.session_state.hedef_magaza_id}",
                                        key="olcu_ai_kuyruga_ekle_btn",
                                        type="primary",
                                        width="stretch",
                                    ):
                                        st.session_state.secilen = _secilecek
                                        _ai_kuyruga_ekle()
        elif ara_btn:
            st.warning("Eşleşen ürün bulunamadı.")

        _son_islem_raporu_goster()

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
