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

from fetch import (
    fetch_ionosonde,
    fetch_ionosonde_history,
    fetch_kp,
    fetch_sfi,
    fetch_solar_wind,
    fetch_xray,
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
# Styling
# ──────────────────────────────────────────────────────────────

st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Inter:wght@300;400;600&display=swap');

  /* Dark terminal aesthetic */
  .stApp { background-color: #0d0f14; color: #c8d3e0; }
  
  /* Metric cards */
  .metric-card {
    background: #151821;
    border: 1px solid #2a2f3e;
    border-radius: 6px;
    padding: 16px 20px;
    font-family: 'Space Mono', monospace;
    margin-bottom: 8px;
  }
  .metric-label {
    font-size: 10px;
    letter-spacing: 0.15em;
    text-transform: uppercase;
    color: #5a6478;
    margin-bottom: 4px;
  }
  .metric-value {
    font-size: 28px;
    font-weight: 700;
    color: #e8f0fa;
    line-height: 1;
  }
  .metric-unit {
    font-size: 12px;
    color: #5a6478;
    margin-left: 4px;
  }
  .metric-time {
    font-size: 10px;
    color: #3a4458;
    margin-top: 6px;
  }

  /* Band status pills */
  .band-open    { color: #00e676; }
  .band-marginal{ color: #ffc107; }
  .band-closed  { color: #ef5350; }
  .band-unknown { color: #607d8b; }

  /* Section headers */
  .section-header {
    font-family: 'Space Mono', monospace;
    font-size: 11px;
    letter-spacing: 0.2em;
    text-transform: uppercase;
    color: #3a8fbf;
    border-bottom: 1px solid #1e2535;
    padding-bottom: 6px;
    margin: 24px 0 16px 0;
  }

  /* Kp color badge */
  .kp-low    { color: #00e676; }
  .kp-mid    { color: #ffc107; }
  .kp-high   { color: #ef5350; }

  /* Hide Streamlit chrome */
  #MainMenu, footer, header { visibility: hidden; }
  .block-container { padding-top: 1.5rem; }
</style>
""", unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────
# Sidebar
# ──────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown(f"## 📡 HF Dashboard")
    st.markdown("**AK6MJ** · CN88 · Freeland WA")
    st.markdown("---")

    station = st.selectbox(
        "Ionosonde Station",
        options=["IF843", "BC840", "MHJ45", "EG931", "GA762", "PA836"],
        index=0,
        help="URSI station code. IF843 = Idaho National Lab (nearest to CM58)"
    )

    refresh_interval = st.select_slider(
        "Auto-refresh (sec)",
        options=[0, 60, 120, 300, 600, 900],
        value=300,
    )

    hours_history = st.slider("History (hours)", 6, 48, 24, step=6)

    st.markdown("---")
    st.markdown("""
    **Data Sources**
    - [GIRO DIDBase](https://giro.uml.edu) — Ionosonde  
    - [NOAA SWPC](https://www.swpc.noaa.gov) — Space weather  
    - Cadence: ~15 min (ionosonde), ~1 min (Kp)
    """)

    manual_refresh = st.button("🔄 Refresh Now", use_container_width=True)


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


if manual_refresh:
    st.cache_data.clear()

# Load data
with st.spinner("Fetching data..."):
    latest_iono, iono_history = load_ionosonde(station, hours_history)
    kp_data, sfi_data, wind_data, xray_data = load_space_weather()

utc_now = datetime.now(timezone.utc)


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
        st.markdown(f"<div style='text-align:right; padding-top:24px; font-size:12px; color:#3a4458;'>Auto-refresh: {refresh_interval}s</div>", unsafe_allow_html=True)

st.markdown("---")


# ──────────────────────────────────────────────────────────────
# ROW 1: Key metrics
# ──────────────────────────────────────────────────────────────

st.markdown("<div class='section-header'>Ionospheric Conditions — IF843</div>", unsafe_allow_html=True)

fof2  = latest_iono.get("foF2")  if latest_iono else None
mufd  = latest_iono.get("MUFD")  if latest_iono else None
md    = latest_iono.get("MD")    if latest_iono else None
d_val = latest_iono.get("D")     if latest_iono else None
iono_time = latest_iono.get("time") if latest_iono else None
iono_age = ""
if iono_time:
    try:
        age_min = int((utc_now - iono_time.replace(tzinfo=timezone.utc) if iono_time.tzinfo is None else utc_now - iono_time).total_seconds() / 60)
        iono_age = f"~{age_min} min ago"
    except Exception:
        iono_age = ""

c1, c2, c3, c4 = st.columns(4)

with c1:
    st.markdown(f"""
    <div class="metric-card">
      <div class="metric-label">foF2 — F2 Critical Freq</div>
      <div class="metric-value">{fmt(fof2)}<span class="metric-unit">MHz</span></div>
      <div class="metric-time">{iono_age}</div>
    </div>""", unsafe_allow_html=True)

with c2:
    st.markdown(f"""
    <div class="metric-card">
      <div class="metric-label">MUF(3000) — Max Usable</div>
      <div class="metric-value">{fmt(mufd)}<span class="metric-unit">MHz</span></div>
      <div class="metric-time">3000 km path</div>
    </div>""", unsafe_allow_html=True)

with c3:
    st.markdown(f"""
    <div class="metric-card">
      <div class="metric-label">M(D) — MUF/foF2 Ratio</div>
      <div class="metric-value">{fmt(md)}<span class="metric-unit"></span></div>
      <div class="metric-time">propagation factor</div>
    </div>""", unsafe_allow_html=True)

with c4:
    st.markdown(f"""
    <div class="metric-card">
      <div class="metric-label">D — Virtual Height</div>
      <div class="metric-value">{fmt(d_val, 0)}<span class="metric-unit">km</span></div>
      <div class="metric-time">at 3000 km</div>
    </div>""", unsafe_allow_html=True)


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

c5, c6, c7, c8 = st.columns(4)

kp_css = kp_color_class(kp_val)
with c5:
    st.markdown(f"""
    <div class="metric-card">
      <div class="metric-label">Kp — Geomagnetic Index</div>
      <div class="metric-value {kp_css}">{fmt(kp_val, 1)}</div>
      <div class="metric-time">0=quiet · 5+=storm</div>
    </div>""", unsafe_allow_html=True)

with c6:
    st.markdown(f"""
    <div class="metric-card">
      <div class="metric-label">SFI — Solar Flux (F10.7)</div>
      <div class="metric-value">{fmt(sfi_val, 0)}<span class="metric-unit">sfu</span></div>
      <div class="metric-time">70=low · 150=high</div>
    </div>""", unsafe_allow_html=True)

with c7:
    bz_color = "#ef5350" if (wind_bz is not None and wind_bz < -5) else "#e8f0fa"
    st.markdown(f"""
    <div class="metric-card">
      <div class="metric-label">Solar Wind Bz / Speed</div>
      <div class="metric-value" style="color:{bz_color}">{fmt(wind_bz)}<span class="metric-unit">nT</span></div>
      <div class="metric-time">{fmt(wind_spd, 0)} km/s · Bz- = storm risk</div>
    </div>""", unsafe_allow_html=True)

xray_colors = {"A": "#607d8b", "B": "#00acc1", "C": "#ffc107", "M": "#ff7043", "X": "#ef5350"}
xray_color = xray_colors.get(xray_cls, "#e8f0fa") if xray_cls else "#e8f0fa"
with c8:
    st.markdown(f"""
    <div class="metric-card">
      <div class="metric-label">GOES X-ray Flux</div>
      <div class="metric-value" style="color:{xray_color}">{xray_cls or "—"}<span class="metric-unit">class</span></div>
      <div class="metric-time">{f"{xray_flux:.1e}" if xray_flux else ""} W/m²</div>
    </div>""", unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────
# ROW 3: Band conditions + foF2 trend
# ──────────────────────────────────────────────────────────────

st.markdown("<div class='section-header'>Band Conditions — NVIS & DX · Freeland WA (CN88)</div>", unsafe_allow_html=True)

col_bands, col_chart = st.columns([1, 2])

# Band conditions table — NVIS and DX grades
with col_bands:
    bands = estimate_band_conditions(fof2, mufd, kp_val, sfi_val, xray_class=xray_data.get("class") if xray_data else None)

    # Build styled HTML table
    band_md = """
    <div style='font-family: Space Mono, monospace; font-size: 12px;'>
    <table style='width:100%; border-collapse:collapse;'>
    <tr style='color:#3a8fbf; font-size:10px; letter-spacing:0.08em; border-bottom:1px solid #2a2f3e;'>
      <th style='text-align:left; padding:4px 6px'>BAND</th>
      <th style='text-align:left; padding:4px 6px'>NVIS</th>
      <th style='text-align:left; padding:4px 6px'>DX</th>
    </tr>
    """
    for b in bands:
        nvis_color = b["nvis_color"]
        dx_color   = b["dx_color"]
        nvis_lbl   = b["nvis_label"]
        dx_lbl     = b["dx_label"]
        # N/A bands get muted style
        nvis_style = f"color:{nvis_color}" if nvis_lbl not in ("N/A", "Unknown") else "color:#2a3040"
        dx_style   = f"color:{dx_color}"   if dx_lbl   not in ("N/A", "Unknown") else "color:#2a3040"
        band_md += f"""
        <tr style='border-bottom:1px solid #151821; cursor:default'
            title='NVIS: {b["nvis_note"]} | DX: {b["dx_note"]}'>
          <td style='padding:5px 6px; color:#c8d3e0'>{b["band"]}</td>
          <td style='padding:5px 6px; {nvis_style}'>{nvis_lbl}</td>
          <td style='padding:5px 6px; {dx_style}'>{dx_lbl}</td>
        </tr>"""
    band_md += "</table>"

    # Legend
    band_md += """
    <div style='margin-top:10px; font-size:10px; color:#3a4458; line-height:1.8'>
      <span style='color:#00e676'>■</span> Excellent &nbsp;
      <span style='color:#69f0ae'>■</span> Good &nbsp;
      <span style='color:#ffc107'>■</span> Fair<br>
      <span style='color:#ff7043'>■</span> Poor &nbsp;
      <span style='color:#ef5350'>■</span> Closed &nbsp;
      <span style='color:#607d8b'>■</span> N/A
    </div>
    <div style='margin-top:6px; font-size:9px; color:#2a3040'>
      Hover row for detail · foF2={fof2_str} MHz · MUF(3000)={muf_str} MHz
    </div>
    </div>
    """.format(
        fof2_str=f"{fof2:.2f}" if fof2 else "—",
        muf_str=f"{mufd:.1f}" if mufd else "—",
    )
    st.markdown(band_md, unsafe_allow_html=True)

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
                line=dict(color="#3a8fbf", width=2),
                fill="tozeroy", fillcolor="rgba(58,143,191,0.08)",
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
                y=freq, line_dash="dash", line_color="#2a2f3e",
                annotation_text=band, annotation_position="right",
                annotation_font=dict(color="#3a4458", size=10),
            )

        fig.update_layout(
            paper_bgcolor="#0d0f14",
            plot_bgcolor="#151821",
            font=dict(family="Space Mono, monospace", color="#c8d3e0", size=11),
            legend=dict(bgcolor="#151821", bordercolor="#2a2f3e", borderwidth=1),
            margin=dict(l=0, r=60, t=10, b=40),
            height=300,
            xaxis=dict(gridcolor="#1e2535", showgrid=True, title=None),
            yaxis=dict(gridcolor="#1e2535", showgrid=True, title="MHz"),
            hovermode="x unified",
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No ionosonde history available. Data may be delayed or station offline.")


# ──────────────────────────────────────────────────────────────
# ROW 4: Kp history sparkline + ionosonde details
# ──────────────────────────────────────────────────────────────

col_kp, col_raw = st.columns([2, 1])

with col_kp:
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
            paper_bgcolor="#0d0f14",
            plot_bgcolor="#151821",
            font=dict(family="Space Mono, monospace", color="#c8d3e0", size=11),
            margin=dict(l=0, r=20, t=10, b=40),
            height=200,
            yaxis=dict(range=[0, 9], gridcolor="#1e2535", title="Kp"),
            xaxis=dict(gridcolor="#1e2535", title=None),
            showlegend=False,
        )
        st.plotly_chart(fig2, use_container_width=True)
    else:
        st.info("Kp data unavailable.")

with col_raw:
    st.markdown("<div class='section-header'>Raw Ionosonde Values</div>", unsafe_allow_html=True)
    if latest_iono:
        rows = []
        for k, v in latest_iono.items():
            if k == "time":
                rows.append({"Parameter": "Time (UTC)", "Value": str(v)[:19]})
            else:
                rows.append({"Parameter": k, "Value": fmt(v) if v is not None else "—"})
        df_raw = pd.DataFrame(rows)
        st.dataframe(df_raw, hide_index=True, use_container_width=True,
                     column_config={"Parameter": st.column_config.TextColumn(width="medium"),
                                    "Value": st.column_config.TextColumn(width="small")})
    else:
        st.warning(f"No data from {station}. Station may be offline or GIRO unreachable.")
        st.markdown("""
        **Manual check:**
        ```
        curl "https://lgdc.uml.edu/common/DIDBGetValues?ursiCode=IF843&charName=foF2,MUFD,MD,D&DMUF=3000&date1=2026-05-28T15:00:00Z&date2=2026-05-28T18:00:00Z"
        ```
        """)

# ──────────────────────────────────────────────────────────────
# Footer
# ──────────────────────────────────────────────────────────────

st.markdown("---")
st.markdown(
    f"<div style='font-size:10px; color:#3a4458; font-family: Space Mono, monospace;'>"
    f"AK6MJ · Freeland WA CN88 · HF Dashboard · "
    f"GIRO DIDBase (CC-BY-NC-SA 4.0) · NOAA SWPC · IF843 −40 min solar offset · "
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
        f"<meta http-equiv='refresh' content='{refresh_interval}'>",
        unsafe_allow_html=True,
    )
