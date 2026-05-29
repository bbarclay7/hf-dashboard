"""
app.py — HF Propagation Dashboard
Streamlit dashboard combining ionosonde data (IF843/GIRO) with NOAA SWPC space weather.

Run with:
    streamlit run app.py
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timezone
import time
import math

from fetch import (
    fetch_ionosonde,
    fetch_ionosonde_history,
    fetch_kp,
    fetch_sfi,
    fetch_solar_wind,
    fetch_xray,
    fetch_tides,
    fetch_sky_tonight,
    estimate_band_conditions,
    BANDS,
)

# ──────────────────────────────────────────────────────────────
# Page config
# ──────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="HF Propagation · AK6MJ",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ──────────────────────────────────────────────────────────────
# Theme — read from URL query param so the choice is bookmarkable
# ──────────────────────────────────────────────────────────────

_PALETTES = {
    "dark": {
        "app_bg":       "#0d0f14",
        "sidebar_bg":   "#151821",
        "card_bg":      "#151821",
        "border":       "#2a2f3e",
        "text":         "#c8d3e0",
        "text_bright":  "#e8f0fa",
        "text_dim":     "#5a6478",
        "text_faint":   "#3a4458",
        "accent":       "#3a8fbf",
        "grid":         "#1e2535",
        "needle":       "#d0dae8",
        "gauge_track":  "#1a2030",
        "nvis_zone":    "#1a3a1a",
        "dx_zone":      "#0f1e2e",
        "ruler_bar":    "#111318",
        "best_nvis_bg": "#0a1a0e",
        "plot_bg":      "#151821",
        "plot_paper":   "#0d0f14",
    },
    "light": {
        "app_bg":       "#f5f7fa",
        "sidebar_bg":   "#eef1f6",
        "card_bg":      "#ffffff",
        "border":       "#d0d8e4",
        "text":         "#1a2030",
        "text_bright":  "#0d1520",
        "text_dim":     "#6b7c96",
        "text_faint":   "#9ba8b8",
        "accent":       "#1a6fa0",
        "grid":         "#dde5ee",
        "needle":       "#1a2030",
        "gauge_track":  "#e0e5ed",
        "nvis_zone":    "#d4eeda",
        "dx_zone":      "#d4e5f5",
        "ruler_bar":    "#e8ecf2",
        "best_nvis_bg": "#edf7ef",
        "plot_bg":      "#ffffff",
        "plot_paper":   "#f5f7fa",
    },
}

theme = st.query_params.get("colormode", "dark")
if theme not in _PALETTES:
    theme = "dark"
P = _PALETTES[theme]

# ──────────────────────────────────────────────────────────────
# Styling
# ──────────────────────────────────────────────────────────────

st.markdown(f"""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Inter:wght@300;400;600&display=swap');

  .stApp {{ background-color: {P['app_bg']}; color: {P['text']}; }}
  [data-testid="stSidebar"] {{ background-color: {P['sidebar_bg']}; }}

  /* Metric cards */
  .metric-card {{
    background: {P['card_bg']};
    border: 1px solid {P['border']};
    border-radius: 6px;
    padding: 16px 20px;
    font-family: 'Space Mono', monospace;
    margin-bottom: 8px;
  }}
  .metric-label {{
    font-size: 10px;
    letter-spacing: 0.15em;
    text-transform: uppercase;
    color: {P['text_dim']};
    margin-bottom: 4px;
  }}
  .metric-value {{
    font-size: 28px;
    font-weight: 700;
    color: {P['text_bright']};
    line-height: 1;
  }}
  .metric-unit {{
    font-size: 12px;
    color: {P['text_dim']};
    margin-left: 4px;
  }}
  .metric-time {{
    font-size: 10px;
    color: {P['text_faint']};
    margin-top: 6px;
  }}

  /* Band status pills */
  .band-open    {{ color: #00e676; }}
  .band-marginal{{ color: #ffc107; }}
  .band-closed  {{ color: #ef5350; }}
  .band-unknown {{ color: #607d8b; }}

  /* Section headers */
  .section-header {{
    font-family: 'Space Mono', monospace;
    font-size: 11px;
    letter-spacing: 0.2em;
    text-transform: uppercase;
    color: {P['accent']};
    border-bottom: 1px solid {P['grid']};
    padding-bottom: 6px;
    margin: 24px 0 16px 0;
  }}

  /* Kp color badge */
  .kp-low    {{ color: #00e676; }}
  .kp-mid    {{ color: #ffc107; }}
  .kp-high   {{ color: #ef5350; }}

  /* Sidebar text and widgets */
  [data-testid="stSidebar"] p,
  [data-testid="stSidebar"] label,
  [data-testid="stSidebar"] .stMarkdown,
  [data-testid="stSidebar"] span {{ color: {P['text']} !important; }}

  [data-testid="stSidebar"] button {{
    background-color: {P['card_bg']} !important;
    color: {P['text']} !important;
    border: 1px solid {P['border']} !important;
  }}

  /* Selectbox, slider, and other widget inputs in sidebar */
  [data-testid="stSidebar"] [data-baseweb="select"] > div,
  [data-testid="stSidebar"] [data-baseweb="select"] span,
  [data-testid="stSidebar"] [data-baseweb="popover"] li,
  [data-testid="stSidebar"] input {{
    background-color: {P['card_bg']} !important;
    color: {P['text']} !important;
  }}
  [data-testid="stSidebar"] [data-baseweb="select"] > div {{
    border-color: {P['border']} !important;
  }}

  /* Hide Streamlit chrome */
  #MainMenu, footer, header {{ visibility: hidden; }}
  .block-container {{ padding-top: 1.5rem; }}
</style>
""", unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────
# Sidebar
# ──────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown(f"## 📡 HF Dashboard")
    st.markdown("**AK6MJ** · CN88 · Freeland WA")
    st.markdown("---")

    _other_theme = "light" if theme == "dark" else "dark"
    _toggle_label = "☀️ Light mode" if theme == "dark" else "🌙 Dark mode"
    if st.button(_toggle_label, use_container_width=True):
        st.query_params["colormode"] = _other_theme
        st.rerun()

    refresh_interval = st.select_slider(
        "Auto-refresh (sec)",
        options=[0, 60, 120, 300, 600, 900],
        value=300,
    )

    hours_history = st.slider("History (hours)", 6, 48, 24, step=6)

    st.markdown("---")
    st.markdown("""
    **Useful Links**
    - [DX View CN88](https://hf.dxview.org/perspective/CN88RA) — Propagation map
    - [PSK Reporter](https://www.pskreporter.info/pskmap.html) — Live spots
    - [DX Maps](https://www.dxmaps.com) — Cluster map
    - [NOAA Space Wx](https://www.swpc.noaa.gov) — Alerts & forecasts
    - [SpaceWeatherLive](https://www.spaceweatherlive.com) — Aurora alerts
    """)

    st.markdown("---")
    st.markdown("""
    **Data Sources**
    - [GIRO IonoWeb](https://giro.uml.edu) — Ionosonde (OCR)
    - [NOAA SWPC](https://www.swpc.noaa.gov) — Kp, SFI, wind, X-ray
    - [NOAA Tides](https://tidesandcurrents.noaa.gov) — Port Townsend
    - [Open-Meteo](https://open-meteo.com) — Sky forecast
    """)

    manual_refresh = st.button("🔄 Refresh Now", use_container_width=True)

station = "IF843"

# ──────────────────────────────────────────────────────────────
# Data loading with caching
# ──────────────────────────────────────────────────────────────

@st.cache_data(ttl=240)  # 4-minute cache
def load_ionosonde(station, hours_history):
    latest = fetch_ionosonde(station=station, hours_back=min(hours_history, 2))
    history = fetch_ionosonde_history(station=station, hours_back=hours_history)
    return latest, history


@st.cache_data(ttl=60)   # 1-minute cache
def load_space_weather():
    kp   = fetch_kp()
    sfi  = fetch_sfi()
    wind = fetch_solar_wind()
    xray = fetch_xray()
    return kp, sfi, wind, xray


@st.cache_data(ttl=3600)  # 1-hour cache
def load_tonight():
    return fetch_tides(), fetch_sky_tonight()


if manual_refresh:
    st.cache_data.clear()

# Load data
with st.spinner("Fetching data..."):
    latest_iono, iono_history = load_ionosonde(station, hours_history)
    kp_data, sfi_data, wind_data, xray_data = load_space_weather()
    tides_data, sky_data = load_tonight()

utc_now = datetime.now(timezone.utc)

# Only warn if data is genuinely stale (>30 min) or missing entirely
if latest_iono and latest_iono.get("_cached"):
    _age = latest_iono.get("_cache_age_min") or 0
    if _age > 30:
        _age_str = f"{_age // 60}h {_age % 60}m" if _age >= 60 else f"{_age}m"
        st.warning(f"⚠️ Ionosonde data is {_age_str} old — pipeline may be stalled.")
elif not latest_iono:
    st.warning("⚠️ No ionosonde data available.")


# ──────────────────────────────────────────────────────────────
# Helper: format value with fallback
# ──────────────────────────────────────────────────────────────

def fmt(val, decimals=2, fallback="—"):
    if val is None:
        return fallback
    try:
        return f"{float(val):.{decimals}f}"
    except Exception:
        return str(val)


def kp_color_class(kp):
    if kp is None:
        return "kp-low"
    if kp >= 5:
        return "kp-high"
    if kp >= 3:
        return "kp-mid"
    return "kp-low"


# ──────────────────────────────────────────────────────────────
# HEADER
# ──────────────────────────────────────────────────────────────

col_title, col_time = st.columns([3, 1])
with col_title:
    st.markdown(f"# 📡 HF Propagation Dashboard")
    st.markdown(
        f"Ionosonde **{station}** (Idaho NL, 112.7°W) · "
        f"QTH Freeland WA (122.5°W) · "
        f"Solar offset **−40 min** applied · "
        f"Updated {utc_now.strftime('%Y-%m-%d %H:%M')} UTC"
    )
with col_time:
    if refresh_interval > 0:
        st.markdown(
            f"<div style='text-align:right; padding-top:24px; font-size:12px; color:{P['text_faint']};'>"
            f"Auto-refresh: {refresh_interval}s</div>",
            unsafe_allow_html=True,
        )

st.markdown("---")


# ──────────────────────────────────────────────────────────────
# ROW 1: Key metrics
# ──────────────────────────────────────────────────────────────

st.markdown("<div class='section-header'>Ionospheric Conditions — IF843</div>", unsafe_allow_html=True)

fof2  = latest_iono.get("foF2")  if latest_iono else None
mufd  = latest_iono.get("MUFD")  if latest_iono else None
md    = latest_iono.get("MD")    if latest_iono else None
iono_time = latest_iono.get("time") if latest_iono else None
iono_age = ""
if iono_time:
    try:
        age_min = int((utc_now - iono_time.replace(tzinfo=timezone.utc) if iono_time.tzinfo is None else utc_now - iono_time).total_seconds() / 60)
        iono_age = f"~{age_min} min ago"
    except Exception:
        iono_age = ""

c1, c2, c3 = st.columns(3)

with c1:
    st.markdown(f"""
    <div class="metric-card" title="NVIS ceiling — the highest frequency that reflects straight up off the F2 layer. Bands above foF2 punch through the ionosphere and cannot support NVIS. Higher foF2 = more bands open for near-vertical skywave. Driven by solar UV and time of day.">
      <div class="metric-label">foF2 — F2 Critical Freq</div>
      <div class="metric-value">{fmt(fof2)}<span class="metric-unit">MHz</span></div>
      <div class="metric-time">{iono_age}</div>
    </div>""", unsafe_allow_html=True)

with c2:
    st.markdown(f"""
    <div class="metric-card" title="DX ceiling for a ~3000 km one-hop path — highest frequency that reflects off F2 at the oblique angle needed for ~1800 mi skip. Bands above MUF escape to space. MUF = foF2 x M(D). Higher MUF = more bands open for long-distance DX.">
      <div class="metric-label">MUF(3000) — Max Usable</div>
      <div class="metric-value">{fmt(mufd)}<span class="metric-unit">MHz</span></div>
      <div class="metric-time">3000 km path</div>
    </div>""", unsafe_allow_html=True)

with c3:
    st.markdown(f"""
    <div class="metric-card" title="DX multiplier — ratio of MUF(3000) to foF2. The oblique path geometry lets you use M(D) times higher frequency for DX than for straight-up NVIS. M(D) ~ 3 is normal; higher is better DX geometry. MUF = foF2 x M(D).">
      <div class="metric-label">M(D) — DX Multiplier</div>
      <div class="metric-value">{fmt(md)}<span class="metric-unit"></span></div>
      <div class="metric-time">MUF = foF2 &times; M(D)</div>
    </div>""", unsafe_allow_html=True)

st.html(f"""
<details style="font-family:Space Mono,monospace;font-size:11px;color:{P['text']};
  background:{P['card_bg']};padding:8px 12px;border-radius:4px;border:1px solid {P['border']};
  margin-top:4px;line-height:1.65">
<summary style="cursor:pointer;color:{P['accent']};font-size:11px;
  letter-spacing:.05em;padding:2px 0;user-select:none">ⓘ Ionospheric parameters explained</summary>
<div style="margin-top:8px">
<p><b>foF2</b> — F2 critical frequency. The highest frequency reflected straight up by the F2 layer.
Acts as the <b>NVIS ceiling</b>: bands above foF2 punch through — no near-vertical reflection.
Higher foF2 = more bands open for regional (0–500 km) contacts. Peaks near local solar noon,
collapses at night. Driven by solar UV ionizing the upper atmosphere.</p>
<p><b>MUF(3000)</b> — Maximum Usable Frequency for a ~3000 km path. The highest frequency that
bounces off F2 at the shallow angle needed for a one-hop ~1800 mi skip. <b>DX ceiling.</b>
MUF = foF2 × M(D). Higher MUF = more bands open for long-haul DX.</p>
<p><b>M(D)</b> — Propagation multiplier (MUF ÷ foF2). Typical value ~2.8–3.2. MUF = foF2 × M(D).</p>
<p><em>Data from <a href="https://giro.uml.edu" target="_blank" style="color:{P['accent']}">GIRO DIDBase</a>,
station IF843 (Idaho National Lab, 112.7°W), solar-offset −40 min for CN88.</em></p>
</div></details>
""")


# ──────────────────────────────────────────────────────────────
# ROW 2: Space weather metrics
# ──────────────────────────────────────────────────────────────

st.markdown("<div class='section-header'>Space Weather — NOAA SWPC</div>", unsafe_allow_html=True)

kp_val   = kp_data.get("kp")   if kp_data   else None
sfi_val  = sfi_data.get("sfi") if sfi_data  else None
wind_spd = wind_data.get("speed") if wind_data else None
wind_bz  = wind_data.get("bz")   if wind_data else None
xray_cls = xray_data.get("class") if xray_data else None
xray_flux = xray_data.get("flux") if xray_data else None

# Needle positions (0–100%) for TOS gauges
_kp_pct  = min(100, max(0, (kp_val  or 0) / 9 * 100))                                  if kp_val   is not None else None
_sfi_pct = min(100, max(0, ((sfi_val or 65) - 65) / 155 * 100))                        if sfi_val  is not None else None
_bz_pct  = min(100, max(0, ((wind_bz or 0) + 25) / 50 * 100))                          if wind_bz  is not None else None
_xr_pct  = min(100, max(0, (math.log10(max(xray_flux, 1e-9)) + 9) / 5 * 100))          if xray_flux else None


def _tos_gauge(pct, value_str, unit_str, label_str, segments, tick_labels,
               tooltip="", value_color=None, palette=None):
    """TOS-style SVG arc gauge. pct=0–100 needle position (None = no data)."""
    Q = palette or P
    if value_color is None:
        value_color = Q["text_bright"]

    CX, CY, R = 100, 88, 60
    START, SWEEP = 150, 240  # SVG-convention degrees: start, clockwise sweep

    def ang(p):
        return START + (p / 100.0) * SWEEP

    def pt(deg, radius=R):
        a = math.radians(deg)
        return CX + radius * math.cos(a), CY + radius * math.sin(a)

    def arc(p0, p1, radius=R):
        x0, y0 = pt(ang(p0), radius)
        x1, y1 = pt(ang(p1), radius)
        lg = 1 if (p1 - p0) / 100.0 * SWEEP > 180 else 0
        return f"M{x0:.1f} {y0:.1f} A{radius} {radius} 0 {lg} 1 {x1:.1f} {y1:.1f}"

    bg   = (f'<path d="{arc(0,100)}" fill="none" stroke="{Q["gauge_track"]}" '
            f'stroke-width="10" stroke-linecap="butt"/>')
    segs = "".join(
        f'<path d="{arc(p0,p1)}" fill="none" stroke="{c}" '
        f'stroke-width="7" stroke-linecap="butt"/>'
        for p0, p1, c in segments
    )

    ticks_svg = ""
    for tp, tl in tick_labels:
        xo, yo = pt(ang(tp), R + 2)
        xi, yi = pt(ang(tp), R - 9)
        xl, yl = pt(ang(tp), R + 17)
        ticks_svg += (
            f'<line x1="{xo:.1f}" y1="{yo:.1f}" x2="{xi:.1f}" y2="{yi:.1f}" '
            f'stroke="{Q["text_faint"]}" stroke-width="1.5"/>'
            f'<text x="{xl:.1f}" y="{yl:.1f}" text-anchor="middle" '
            f'dominant-baseline="middle" font-family="Space Mono,monospace" '
            f'font-size="8" fill="{Q["text_faint"]}">{tl}</text>'
        )

    ndl = ""
    if pct is not None:
        pc = max(0.0, min(100.0, float(pct)))
        a  = math.radians(ang(pc))
        xt = CX + (R - 4) * math.cos(a)
        yt = CY + (R - 4) * math.sin(a)
        perp = a + math.pi / 2
        bw   = 3.5
        pts  = (f"{xt:.1f},{yt:.1f} "
                f"{CX + bw*math.cos(perp):.1f},{CY + bw*math.sin(perp):.1f} "
                f"{CX - bw*math.cos(perp):.1f},{CY - bw*math.sin(perp):.1f}")
        ndl  = (f'<polygon points="{pts}" fill="{Q["needle"]}" opacity="0.95"/>'
                f'<line x1="{CX}" y1="{CY}" x2="{xt:.1f}" y2="{yt:.1f}" '
                f'stroke="{Q["needle"]}" stroke-width="1" opacity="0.35"/>')

    tt = tooltip.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")

    return (
        f'<div style="max-width:190px;margin:0 auto;">'
        f'<svg viewBox="0 0 200 148" xmlns="http://www.w3.org/2000/svg" '
        f'width="200" height="148" style="width:100%;height:auto;display:block;" title="{tt}">'
        f'<rect width="200" height="148" fill="{Q["card_bg"]}" rx="6" '
        f'stroke="{Q["border"]}" stroke-width="1"/>'
        f'{bg}{segs}{ticks_svg}{ndl}'
        f'<circle cx="{CX}" cy="{CY}" r="4" fill="{Q["accent"]}" stroke="{Q["card_bg"]}" stroke-width="1.5"/>'
        f'<text x="{CX}" y="{CY-9}" text-anchor="middle" font-family="Space Mono,monospace" '
        f'font-size="22" font-weight="700" fill="{value_color}">{value_str}</text>'
        f'<text x="{CX}" y="{CY+7}" text-anchor="middle" font-family="Space Mono,monospace" '
        f'font-size="9" fill="{Q["text_dim"]}">{unit_str}</text>'
        f'<text x="{CX}" y="142" text-anchor="middle" font-family="Space Mono,monospace" '
        f'font-size="8" fill="{Q["accent"]}" letter-spacing="2">{label_str}</text>'
        f'</svg>'
        f'</div>'
    )


c5, c6, c7, c8 = st.columns(4)

_kp_color = "#00e676" if (kp_val or 0) < 3 else "#ffc107" if (kp_val or 0) < 5 else "#ef5350"
with c5:
    st.markdown(_tos_gauge(
        pct=_kp_pct, value_str=fmt(kp_val, 1), unit_str="", label_str="KP INDEX",
        segments=[(0, 22, "#00e676"), (22, 55, "#ffc107"), (55, 100, "#ef5350")],
        tick_labels=[(0, "0"), (22, "2"), (55, "5"), (100, "9")],
        tooltip="Planetary K-index, 0-9 scale (3-hr). 0-2: quiet, best HF. 3-4: unsettled. 5+: storm, severe HF disruption at high latitudes like CN88.",
        value_color=_kp_color,
        palette=P,
    ), unsafe_allow_html=True)

with c6:
    st.markdown(_tos_gauge(
        pct=_sfi_pct, value_str=fmt(sfi_val, 0), unit_str="sfu", label_str="SOLAR FLUX",
        segments=[(0, 24, "#ef5350"), (24, 57, "#ffc107"), (57, 100, "#00e676")],
        tick_labels=[(0, "65"), (24, "100"), (57, "150"), (100, "220")],
        tooltip="Solar Flux Index (F10.7 cm). Primary driver of foF2 and MUF. 70=solar minimum, 150+=solar maximum. Each +10 sfu adds ~0.5-1 MHz to foF2.",
        palette=P,
    ), unsafe_allow_html=True)

with c7:
    _bz_color = "#ef5350" if (wind_bz is not None and wind_bz < -5) else P["text_bright"]
    _spd_str  = f"{fmt(wind_spd, 0)} km/s" if wind_spd is not None else "— km/s"
    st.markdown(_tos_gauge(
        pct=_bz_pct, value_str=fmt(wind_bz), unit_str=f"nT  {_spd_str}", label_str="SOLAR WIND",
        segments=[(0, 30, "#ef5350"), (30, 40, "#ffc107"), (40, 100, "#00e676")],
        tick_labels=[(0, "-25"), (30, "-10"), (40, "-5"), (50, "0"), (100, "+25")],
        tooltip="Solar wind Bz from DSCOVR (~1 hr upstream). Bz negative = southward field couples to Earth magnetosphere, storm develops. Bz < -5 nT sustained: watch for rising Kp.",
        value_color=_bz_color,
        palette=P,
    ), unsafe_allow_html=True)

_xray_colors = {"A": "#607d8b", "B": "#00acc1", "C": "#ffc107", "M": "#ff7043", "X": "#ef5350"}
_xr_vc = _xray_colors.get(xray_cls, P["text_bright"]) if xray_cls else P["text_bright"]
with c8:
    st.markdown(_tos_gauge(
        pct=_xr_pct, value_str=xray_cls or "—",
        unit_str=f"{xray_flux:.1e} W/m²" if xray_flux else "",
        label_str="X-RAY FLUX",
        segments=[(0, 40, "#607d8b"), (40, 60, "#00acc1"), (60, 80, "#ffc107"), (80, 100, "#ef5350")],
        tick_labels=[(0, "A"), (40, "B"), (60, "C"), (80, "M"), (100, "X")],
        tooltip="GOES X-ray flux (log scale). A/B: background. C: minor absorption. M: moderate, 1-2 grade penalty. X: major, possible HF blackout on daytime side.",
        value_color=_xr_vc,
        palette=P,
    ), unsafe_allow_html=True)

st.html(f"""
<details style="font-family:Space Mono,monospace;font-size:11px;color:{P['text']};
  background:{P['card_bg']};padding:8px 12px;border-radius:4px;border:1px solid {P['border']};
  margin-top:4px;line-height:1.65">
<summary style="cursor:pointer;color:{P['accent']};font-size:11px;
  letter-spacing:.05em;padding:2px 0;user-select:none">ⓘ Space weather parameters explained</summary>
<div style="margin-top:8px">
<p><b>Kp</b> — Planetary K-index (0–9 scale, 3-hour intervals). Geomagnetic disturbance level.
<br>0–2: quiet — best HF &nbsp;|&nbsp; 3–4: unsettled &nbsp;|&nbsp; 5+: storm, severe disruption at CN88 latitude.
<br>Penalizes band grades here, extra penalty above 14 MHz.
<a href="https://www.swpc.noaa.gov/products/planetary-k-index" target="_blank" style="color:{P['accent']}">NOAA Kp</a></p>
<p><b>SFI</b> — Solar Flux Index (F10.7 cm). Primary long-term driver of foF2 and MUF.
<br>~70: solar minimum &nbsp;|&nbsp; 150+: solar maximum. Each +10 sfu ≈ +0.5–1 MHz to foF2.
<a href="https://www.swpc.noaa.gov/phenomena/f107-cm-radio-emissions" target="_blank" style="color:{P['accent']}">NOAA F10.7</a></p>
<p><b>Bz</b> — Solar wind Z-field (DSCOVR, ~1 hr upstream). <b>Negative = southward</b> = couples
into magnetosphere → storm. Bz &lt; −5 nT sustained: watch for rising Kp over next 1–3 hrs.</p>
<p><b>X-ray</b> — GOES flare flux. Causes sudden D-region absorption on the sunlit side.
<br>A/B: none &nbsp;|&nbsp; C: minor &nbsp;|&nbsp; M: 1–2 grade penalty &nbsp;|&nbsp; X: possible blackout.
<a href="https://www.swpc.noaa.gov/phenomena/solar-flares-radio-blackouts" target="_blank" style="color:{P['accent']}">NOAA flares</a></p>
</div></details>
""")


# ──────────────────────────────────────────────────────────────
# ROW 3: Band conditions + foF2 trend
# ──────────────────────────────────────────────────────────────

def _freq_ruler(fof2_val, mufd_val, bands_list, palette=None):
    """SVG frequency ruler showing NVIS/DX/closed zones across 1.8–30 MHz (log scale)."""
    Q = palette or P
    W, H = 340, 56
    BAR_Y, BAR_H = 20, 13
    F_MIN, F_MAX = 1.8, 30.0
    LOG_MIN  = math.log10(F_MIN)
    LOG_RNG  = math.log10(F_MAX) - LOG_MIN

    def xp(f):
        return (math.log10(max(F_MIN, min(F_MAX, float(f)))) - LOG_MIN) / LOG_RNG * W

    x_fof2 = xp(fof2_val) if fof2_val else None
    x_mufd = xp(mufd_val) if (mufd_val and mufd_val < F_MAX) else (W if mufd_val else None)

    svg = (f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" '
           f'width="{W}" height="{H}" style="width:100%;height:auto;display:block;">'
           f'<rect width="{W}" height="{H}" fill="{Q["app_bg"]}"/>'
           f'<rect x="0" y="{BAR_Y}" width="{W}" height="{BAR_H}" fill="{Q["ruler_bar"]}" rx="2"/>')

    # Colour zones
    if x_fof2:
        svg += f'<rect x="0" y="{BAR_Y}" width="{x_fof2:.1f}" height="{BAR_H}" fill="{Q["nvis_zone"]}" rx="2"/>'
    if x_fof2 and x_mufd and x_mufd > x_fof2:
        svg += (f'<rect x="{x_fof2:.1f}" y="{BAR_Y}" width="{x_mufd - x_fof2:.1f}" '
                f'height="{BAR_H}" fill="{Q["dx_zone"]}"/>')

    # Zone labels
    if x_fof2 and x_fof2 > 22:
        svg += (f'<text x="{x_fof2/2:.1f}" y="{BAR_Y + BAR_H/2 + 1:.1f}" '
                f'text-anchor="middle" dominant-baseline="middle" '
                f'font-family="Space Mono,monospace" font-size="6" fill="#00e676" opacity="0.7">NVIS</text>')
    if x_fof2 and x_mufd and (x_mufd - x_fof2) > 22:
        svg += (f'<text x="{(x_fof2 + x_mufd)/2:.1f}" y="{BAR_Y + BAR_H/2 + 1:.1f}" '
                f'text-anchor="middle" dominant-baseline="middle" '
                f'font-family="Space Mono,monospace" font-size="6" fill="{Q["accent"]}" opacity="0.7">DX</text>')

    # Band ticks
    band_lkp = {b["band"]: b for b in (bands_list or [])}
    TICKS = [("160m",1.9),("80m",3.75),("60m",5.35),("40m",7.15),
             ("30m",10.12),("20m",14.175),("17m",18.1),("15m",21.2),
             ("12m",24.94),("10m",28.85)]
    for bname, fcenter in TICKS:
        bx = xp(fcenter)
        bi = band_lkp.get(bname, {})
        if fof2_val and fcenter <= fof2_val:
            tc = bi.get("nvis_color", Q["text_dim"])
        elif mufd_val and fcenter <= mufd_val:
            tc = bi.get("dx_color", Q["text_dim"])
        else:
            tc = Q["border"]
        label = bname.replace("m", "")
        svg += (f'<line x1="{bx:.1f}" y1="{BAR_Y}" x2="{bx:.1f}" y2="{BAR_Y+BAR_H}" '
                f'stroke="{tc}" stroke-width="1" opacity="0.6"/>'
                f'<text x="{bx:.1f}" y="{BAR_Y+BAR_H+9}" text-anchor="middle" '
                f'font-family="Space Mono,monospace" font-size="6.5" fill="{tc}">{label}</text>')

    # foF2 marker
    if x_fof2:
        svg += (f'<line x1="{x_fof2:.1f}" y1="{BAR_Y-3}" x2="{x_fof2:.1f}" y2="{BAR_Y+BAR_H+2}" '
                f'stroke="{Q["text_bright"]}" stroke-width="1.5"/>'
                f'<text x="{x_fof2:.1f}" y="{BAR_Y-6}" text-anchor="middle" '
                f'font-family="Space Mono,monospace" font-size="6.5" fill="{Q["text_bright"]}">'
                f'foF2 {fof2_val:.1f}</text>')

    # MUF marker
    if x_mufd and mufd_val and mufd_val < F_MAX:
        svg += (f'<line x1="{x_mufd:.1f}" y1="{BAR_Y-3}" x2="{x_mufd:.1f}" y2="{BAR_Y+BAR_H+2}" '
                f'stroke="{Q["accent"]}" stroke-width="1.5"/>'
                f'<text x="{x_mufd:.1f}" y="{BAR_Y-6}" text-anchor="middle" '
                f'font-family="Space Mono,monospace" font-size="6.5" fill="{Q["accent"]}">'
                f'MUF {mufd_val:.1f}</text>')

    svg += '</svg>'
    return svg


# Compute band conditions before layout split (needed for quick pick + ruler)
bands = estimate_band_conditions(fof2, mufd, kp_val, sfi_val, xray_class=xray_data.get("class") if xray_data else None)

# Best NVIS band quick pick — full width, above the fold
_best_nvis = next(
    (b for b in reversed(bands) if b["nvis_label"] in ("Excellent", "Good")), None
)
if _best_nvis:
    _qp_col  = _best_nvis["nvis_color"]
    _kp_note = (f" &nbsp;·&nbsp; Kp {kp_val:.1f} — watch absorption" if kp_val and kp_val >= 3 else "")
    st.markdown(
        f'<div style="font-family:Space Mono,monospace; background:{P["best_nvis_bg"]}; '
        f'border-left:3px solid {_qp_col}; border-radius:4px; '
        f'padding:8px 14px; margin-bottom:6px; font-size:12px;">'
        f'<span style="color:{P["accent"]}; font-size:9px; letter-spacing:.1em">Best NVIS / VARA HF Band Now</span><br>'
        f'<span style="color:{_qp_col}; font-size:22px; font-weight:700">{_best_nvis["band"]}</span>'
        f'<span style="color:{P["text"]}; margin-left:10px">{_best_nvis["nvis_label"]}</span>'
        f'<span style="color:{P["text_dim"]}; margin-left:10px; font-size:10px">NVIS ≈ 50–500 km{_kp_note}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

st.markdown("<div class='section-header'>Band Conditions — NVIS &amp; DX · Freeland WA (CN88)</div>", unsafe_allow_html=True)

col_bands, col_chart = st.columns([1, 2])

# Band conditions table — NVIS and DX grades
with col_bands:
    # Frequency ruler
    st.markdown(_freq_ruler(fof2, mufd, bands, palette=P), unsafe_allow_html=True)

    # Build styled HTML table
    band_md = f"""
    <div style='font-family: Space Mono, monospace; font-size: 12px; background:{P['app_bg']}; color:{P['text']};'>
    <table style='width:100%; border-collapse:collapse;'>
    <tr style='color:{P['accent']}; font-size:10px; letter-spacing:0.08em; border-bottom:1px solid {P['border']};'>
      <th style='text-align:left; padding:4px 6px'>BAND</th>
      <th style='text-align:left; padding:4px 6px'>NVIS</th>
      <th style='text-align:left; padding:4px 6px'>DX</th>
      <th style='text-align:left; padding:4px 6px; color:{P['text_faint']}'>NOTE</th>
    </tr>
    """
    for b in bands:
        nvis_color = b["nvis_color"]
        dx_color   = b["dx_color"]
        nvis_lbl   = b["nvis_label"]
        dx_lbl     = b["dx_label"]
        freq       = b["freq_mhz"]
        # N/A bands get muted style
        nvis_style = f"color:{nvis_color}" if nvis_lbl not in ("N/A", "Unknown") else f"color:{P['text_dim']}"
        dx_style   = f"color:{dx_color}"   if dx_lbl   not in ("N/A", "Unknown") else f"color:{P['text_dim']}"
        # Short note for the visible NOTE column
        if mufd and fof2 and freq > fof2 and freq <= mufd * 1.05:
            _md = mufd / fof2
            _d_min = max(0, int(3000 * (freq / fof2 - 1) / (_md - 1))) if _md > 1 else 0
            _pct = int(freq / mufd * 100)
            short_note = f"~{_d_min:,}&ndash;3,500 km &middot; {_pct}% MUF"
        elif mufd and freq > mufd * 1.05:
            short_note = f"above MUF {mufd:.1f} MHz"
        elif fof2 and freq <= fof2:
            _pct = int(freq / fof2 * 100)
            short_note = f"{_pct}% of foF2 {fof2:.1f} MHz"
        else:
            short_note = ""
        _is_best = _best_nvis and b["band"] == _best_nvis["band"]
        _band_cell = (
            f'{b["band"]} <span style="color:#00e676; font-size:9px">★</span>'
            if _is_best else b["band"]
        )
        band_md += f"""
        <tr style='border-bottom:1px solid {P['border']}; cursor:default'
            title='NVIS: {b["nvis_note"]} | DX: {b["dx_note"]}'>
          <td style='padding:5px 6px; color:{P['text']}'>{_band_cell}</td>
          <td style='padding:5px 6px; {nvis_style}'>{nvis_lbl}</td>
          <td style='padding:5px 6px; {dx_style}'>{dx_lbl}</td>
          <td style='padding:5px 6px; font-size:10px; color:{P['text_dim']}'>{short_note}</td>
        </tr>"""
    band_md += "</table>"

    # Legend
    band_md += f"""
    <div style='margin-top:10px; font-size:10px; color:{P['text_faint']}; line-height:1.8'>
      <span style='color:#00e676'>■</span> Excellent &nbsp;
      <span style='color:#69f0ae'>■</span> Good &nbsp;
      <span style='color:#ffc107'>■</span> Fair<br>
      <span style='color:#ff7043'>■</span> Poor &nbsp;
      <span style='color:#ef5350'>■</span> Closed &nbsp;
      <span style='color:#607d8b'>■</span> N/A
    </div>
    <div style='margin-top:6px; font-size:9px; color:{P['text_faint']}'>
      Hover row for detail · foF2={f"{fof2:.2f}" if fof2 else "—"} MHz · MUF(3000)={f"{mufd:.1f}" if mufd else "—"} MHz
    </div>
    </div>
    """
    st.html(band_md)

    st.html(f"""
<details style="font-family:Space Mono,monospace;font-size:11px;color:{P['text']};
  background:{P['card_bg']};padding:8px 12px;border-radius:4px;border:1px solid {P['border']};
  margin-top:4px;line-height:1.65">
<summary style="cursor:pointer;color:{P['accent']};font-size:11px;
  letter-spacing:.05em;padding:2px 0;user-select:none">ⓘ How to read band conditions</summary>
<div style="margin-top:8px">
<p><b>NVIS</b> — Regional 0–500 km. Signal goes nearly vertical, reflects off F2, returns nearby.
Ceiling = foF2. Floor ≈ 2 MHz daytime. Best bands: 80m/60m/40m day, 160m night.</p>
<p><b>DX (F2 Skip)</b> — Long distance via oblique reflection.
Ceiling = MUF(3000). NOTE column shows skip distance. Higher % of MUF = longer skip.
Multi-hop ≈ ×2 or ×3 distance. Bands below foF2 reflect before they can skip — NVIS only.</p>
<p><b>Grades</b>: Excellent → Good → Fair → Poor → Closed</p>
<p><b>Penalties</b>: High Kp reduces grades (absorption), extra above 14 MHz at CN88.
X-ray C/M/X class reduces daytime bands via D-region absorption.
Tap any row for live values.</p>
</div></details>
""")

# foF2 & MUF history chart
with col_chart:
    if iono_history:
        df = pd.DataFrame(iono_history)
        df = df.dropna(subset=["foF2"]) if "foF2" in df.columns else df
        df = df.sort_values("time") if "time" in df.columns else df

        fig = go.Figure()

        if "foF2" in df.columns:
            fig.add_trace(go.Scatter(
                x=df["time"], y=df["foF2"],
                name="foF2 (MHz)",
                line=dict(color=P["accent"], width=2),
                fill="tozeroy", fillcolor=f"rgba(58,143,191,0.08)",
            ))

        if "MUFD" in df.columns:
            df_mufd = df.dropna(subset=["MUFD"])
            if not df_mufd.empty:
                fig.add_trace(go.Scatter(
                    x=df_mufd["time"], y=df_mufd["MUFD"],
                    name="MUF(3000) (MHz)",
                    line=dict(color="#00e676", width=1.5, dash="dot"),
                ))

        # Band frequency reference lines
        for band, freq in [("20m", 14.2), ("40m", 7.1), ("10m", 28.5)]:
            fig.add_hline(
                y=freq, line_dash="dash", line_color=P["border"],
                annotation_text=band, annotation_position="right",
                annotation_font=dict(color=P["text_faint"], size=10),
            )

        fig.update_layout(
            paper_bgcolor=P["plot_paper"],
            plot_bgcolor=P["plot_bg"],
            font=dict(family="Space Mono, monospace", color=P["text"], size=11),
            legend=dict(bgcolor=P["card_bg"], bordercolor=P["border"], borderwidth=1,
                        font=dict(color=P["text"])),
            margin=dict(l=0, r=60, t=10, b=40),
            height=300,
            xaxis=dict(gridcolor=P["grid"], showgrid=True, title=None),
            yaxis=dict(gridcolor=P["grid"], showgrid=True, title="MHz"),
            hovermode="x unified",
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No ionosonde history available. Data may be delayed or station offline.")


# ──────────────────────────────────────────────────────────────
# ROW 4: Kp history sparkline
# ──────────────────────────────────────────────────────────────

st.markdown("<div class='section-header'>Kp History (last 96 min)</div>", unsafe_allow_html=True)
if kp_data and kp_data.get("history"):
    kp_hist = kp_data["history"]
    kp_df = pd.DataFrame(kp_hist)
    kp_df = kp_df.dropna(subset=["kp"])

    def kp_bar_color(k):
        if k >= 5: return "#ef5350"
        if k >= 3: return "#ffc107"
        return "#00e676"

    colors = [kp_bar_color(k) for k in kp_df["kp"]]

    fig2 = go.Figure(go.Bar(
        x=kp_df["time"],
        y=kp_df["kp"],
        marker_color=colors,
        name="Kp",
    ))
    fig2.add_hline(y=5, line_dash="dash", line_color="#ef5350",
                   annotation_text="G1 storm", annotation_font=dict(color="#ef5350", size=10))
    fig2.update_layout(
        paper_bgcolor=P["plot_paper"],
        plot_bgcolor=P["plot_bg"],
        font=dict(family="Space Mono, monospace", color=P["text"], size=11),
        margin=dict(l=0, r=20, t=10, b=40),
        height=200,
        yaxis=dict(range=[0, 9], gridcolor=P["grid"], title="Kp"),
        xaxis=dict(gridcolor=P["grid"], title=None),
        showlegend=False,
    )
    st.plotly_chart(fig2, use_container_width=True)
else:
    st.info("Kp data unavailable.")


# ──────────────────────────────────────────────────────────────
# ROW 5: Tonight — Aurora & Tides
# ──────────────────────────────────────────────────────────────

st.markdown("<div class='section-header'>Tonight — Aurora &amp; Tides · CN88</div>", unsafe_allow_html=True)

col_aurora, col_tides = st.columns([1, 1])

# ── Aurora likelihood ──────────────────────────────────────────
with col_aurora:
    # Moon phase (pure math, no library)
    _moon_ref = datetime(2000, 1, 6, 18, 14, tzinfo=timezone.utc)
    _moon_days = (utc_now - _moon_ref).total_seconds() / 86400
    _moon_phase = (_moon_days % 29.530588853) / 29.530588853
    _moon_illum = round((1 - math.cos(2 * math.pi * _moon_phase)) / 2 * 100)
    _moon_names = ["New", "Waxing Crescent", "First Quarter", "Waxing Gibbous",
                   "Full", "Waning Gibbous", "Last Quarter", "Waning Crescent"]
    _moon_name  = _moon_names[min(7, int(_moon_phase * 8))]

    # Aurora likelihood from Kp at ~48°N (CN88)
    _kp = kp_val or 0
    if _kp >= 7:
        _aur_label, _aur_color = "Good", "#00e676"
    elif _kp >= 6:
        _aur_label, _aur_color = "Possible", "#69f0ae"
    elif _kp >= 5:
        _aur_label, _aur_color = "Low", "#ffc107"
    elif _kp >= 4:
        _aur_label, _aur_color = "Very low", "#ff7043"
    else:
        _aur_label, _aur_color = "Unlikely", P["text_dim"]

    # Moon impact on viewing
    if _moon_illum > 75:
        _moon_note = f"{_moon_illum}% — bright, reduces visibility"
        _moon_col  = "#ff7043"
    elif _moon_illum > 40:
        _moon_note = f"{_moon_illum}% — moderate impact"
        _moon_col  = "#ffc107"
    else:
        _moon_note = f"{_moon_illum}% — minimal impact"
        _moon_col  = "#69f0ae"

    # Sky conditions
    if sky_data:
        _cloud = sky_data["avg_cloud_pct"]
        _precip = sky_data["max_precip_pct"]
        if _cloud > 70:
            _sky_label, _sky_col = f"Overcast ({_cloud}%)", "#ef5350"
        elif _cloud > 40:
            _sky_label, _sky_col = f"Partly cloudy ({_cloud}%)", "#ffc107"
        else:
            _sky_label, _sky_col = f"Mostly clear ({_cloud}%)", "#00e676"
        if _precip > 30:
            _sky_label += f" · rain {_precip}%"
    else:
        _sky_label, _sky_col = "Unknown", P["text_dim"]

    st.html(f"""
<div style="font-family:Space Mono,monospace;font-size:12px;color:{P['text']};
  background:{P['card_bg']};border:1px solid {P['border']};border-radius:6px;padding:14px 16px;">
  <div style="font-size:9px;letter-spacing:.12em;color:{P['accent']};margin-bottom:8px">AURORA TONIGHT</div>
  <div style="font-size:20px;font-weight:700;color:{_aur_color};margin-bottom:10px">
    {_aur_label} <span style="font-size:12px;color:{P['text_dim']}">Kp {fmt(kp_val,1)}</span>
  </div>
  <div style="display:grid;grid-template-columns:auto 1fr;gap:4px 10px;font-size:11px;line-height:1.7">
    <span style="color:{P['text_dim']}">Moon</span>
    <span><span style="color:{_moon_col}">{_moon_name}</span>
      <span style="color:{P['text_faint']};margin-left:6px">{_moon_note}</span></span>
    <span style="color:{P['text_dim']}">Sky</span>
    <span style="color:{_sky_col}">{_sky_label}</span>
  </div>
  <div style="font-size:9px;color:{P['text_faint']};margin-top:8px">Kp ≥ 5 needed for CN88 · Kp ≥ 6 reliable</div>
</div>
""")

# ── Tides ─────────────────────────────────────────────────────
with col_tides:
    # Filter to upcoming tides only
    _now_str = utc_now.strftime("%Y-%m-%d %H:%M")  # NOAA times are local but close enough for filtering
    _upcoming = [t for t in tides_data if t["time"] > _now_str][:4]

    _tide_rows = ""
    for _t in _upcoming:
        _type_label = "High" if _t["type"] == "H" else "Low "
        _type_color = "#3a8fbf" if _t["type"] == "H" else P["text_dim"]
        _ht = f"{_t['height_ft']:+.1f} ft"
        _time_str = _t["time"][11:16]  # HH:MM local
        _tide_rows += f"""
    <tr style="border-bottom:1px solid {P['border']}">
      <td style="padding:5px 8px;color:{_type_color};font-weight:700">{_type_label}</td>
      <td style="padding:5px 8px;color:{P['text']}">{_time_str}</td>
      <td style="padding:5px 8px;color:{P['text_dim']};text-align:right">{_ht}</td>
    </tr>"""

    st.html(f"""
<div style="font-family:Space Mono,monospace;font-size:12px;color:{P['text']};
  background:{P['card_bg']};border:1px solid {P['border']};border-radius:6px;padding:14px 16px;">
  <div style="font-size:9px;letter-spacing:.12em;color:{P['accent']};margin-bottom:8px">
    TIDES · PORT TOWNSEND
    <span style="color:{P['text_faint']};margin-left:8px">local time · saltwater amplifier</span>
  </div>
  <table style="width:100%;border-collapse:collapse">
    {_tide_rows if _tide_rows else f'<tr><td style="color:{P["text_dim"]}">No data</td></tr>'}
  </table>
</div>
""")

# ── Footer ────────────────────────────────────────────────────
# ──────────────────────────────────────────────────────────────
# Footer
# ──────────────────────────────────────────────────────────────

st.markdown("---")
st.markdown(
    f"<div style='font-size:10px; color:{P['text_faint']}; font-family: Space Mono, monospace;'>"
    f"AK6MJ · Freeland WA CN88 · HF Dashboard · "
    f"GIRO DIDBase (CC-BY-NC-SA 4.0) · NOAA SWPC · NOAA Tides · Open-Meteo · IF843 −40 min solar offset · "
    f"Generated {utc_now.strftime('%Y-%m-%dT%H:%MZ')}"
    f"</div>",
    unsafe_allow_html=True,
)

# ──────────────────────────────────────────────────────────────
# Auto-refresh
# ──────────────────────────────────────────────────────────────

if refresh_interval > 0:
    time.sleep(0.5)
    st.markdown(
        f"<meta http-equiv='refresh' content='{refresh_interval};url=?colormode={theme}'>",
        unsafe_allow_html=True,
    )
