# HF Propagation Dashboard · AK6MJ

Real-time HF propagation conditions for **Freeland WA (CN88)** combining ionospheric data from GIRO DIDBase with space weather from NOAA SWPC.

## Features

- **foF2 / MUF(3000) / M(D)** from ionosonde IF843 (Idaho National Lab), solar-offset corrected −40 min for CN87
- **Band conditions table** (NVIS + DX grades) for 160m–6m based on live ionospheric parameters
- **Space weather**: Kp, F10.7 SFI, solar wind speed/Bz, GOES X-ray class
- Historical trend charts (configurable 6–48 h window)
- Auto-refresh (60 s – 15 min, configurable)

## Data Sources

| Source | What | URL |
|--------|------|-----|
| GIRO DIDBase | Ionosonde scaled data (foF2, MUF, MD, D) | lgdc.uml.edu |
| NOAA SWPC | Kp, F10.7, solar wind, X-ray | services.swpc.noaa.gov |

License: GIRO data under CC-BY-NC-SA 4.0 · NOAA SWPC data is public domain.

## Running locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploy

[![Open in Streamlit](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://share.streamlit.io)

Deploy via [Streamlit Community Cloud](https://share.streamlit.io) — point to `app.py` at repo root.
