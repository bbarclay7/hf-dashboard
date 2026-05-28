"""
fetch.py — Data retrieval for HF propagation dashboard.

Sources:
  - GIRO DIDBase  : ionosonde scaled data (foF2, MUF(D), M(D), D)
  - NOAA SWPC     : Kp index, SFI/F10.7, solar wind, X-ray flux
  - WWV text      : backup SFI/A/K from NOAA geophysical alert
"""

import requests
import re
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

log = logging.getLogger(__name__)

TIMEOUT = 12  # seconds


# ──────────────────────────────────────────────────────────────
# GIRO DIDBase — ionosonde data
# ──────────────────────────────────────────────────────────────

GIRO_URL = "https://lgdc.uml.edu/common/DIDBGetValues"


def fetch_ionosonde(
    station: str = "IF843",
    chars: str = "foF2,MD,MUFD,D",
    hours_back: float = 2.0,
    solar_offset_min: int = 40,
) -> Optional[dict]:
    """
    Return the most recent ionosonde observation from GIRO DIDBase.

    solar_offset_min: IF843 is ~39 min ahead of Freeland WA in solar time
    (112.7°W vs 122.5°W = 9.8° × 4 min/° ≈ 39 min). We fetch observations
    from ~40 min ago so the reading reflects current conditions at our QTH.

    Returns dict with keys matching the requested chars, plus 'time' (UTC datetime).
    Returns None on failure.
    """
    now = datetime.now(timezone.utc)
    # Shift window back by solar_offset_min to get the sounding that reflects
    # current local solar conditions (IF843 is ahead of us in solar time)
    effective_now = now - timedelta(minutes=solar_offset_min)
    t1 = (effective_now - timedelta(hours=hours_back)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    t2 = effective_now.strftime("%Y-%m-%dT%H:%M:%S.000Z")

    params = {
        "ursiCode": station,
        "charName": chars,
        "DMUF": 3000,
        "date1": t1,
        "date2": t2,
    }

    try:
        r = requests.get(GIRO_URL, params=params, timeout=TIMEOUT)
        r.raise_for_status()
    except Exception as e:
        log.warning("GIRO fetch failed: %s", e)
        return None

    return _parse_giro_text(r.text, chars)


def fetch_ionosonde_history(
    station: str = "IF843",
    chars: str = "foF2,MD,MUFD,D",
    hours_back: float = 24.0,
    solar_offset_min: int = 40,
) -> list[dict]:
    """Return all observations in the past N hours as a list of dicts.
    Applies solar_offset_min so the window is aligned to local solar conditions."""
    now = datetime.now(timezone.utc)
    effective_now = now - timedelta(minutes=solar_offset_min)
    t1 = (effective_now - timedelta(hours=hours_back)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    t2 = effective_now.strftime("%Y-%m-%dT%H:%M:%S.000Z")

    params = {
        "ursiCode": station,
        "charName": chars,
        "DMUF": 3000,
        "date1": t1,
        "date2": t2,
    }

    try:
        r = requests.get(GIRO_URL, params=params, timeout=TIMEOUT)
        r.raise_for_status()
    except Exception as e:
        log.warning("GIRO history fetch failed: %s", e)
        return []

    return _parse_giro_text_all(r.text, chars)


def _parse_giro_text(text: str, chars: str) -> Optional[dict]:
    """Parse GIRO tab-delimited response; return the most recent row."""
    rows = _parse_giro_text_all(text, chars)
    return rows[-1] if rows else None


def _parse_giro_text_all(text: str, chars: str) -> list[dict]:
    """Parse GIRO tab-delimited response; return all data rows."""
    lines = text.strip().splitlines()
    char_list = [c.strip() for c in chars.split(",")]

    # Find header line (starts with '#' or 'Time')
    header_idx = None
    col_names = None
    for i, line in enumerate(lines):
        stripped = line.lstrip("#").strip()
        if stripped.lower().startswith("time") or "time" in stripped.lower():
            col_names = stripped.split()
            header_idx = i
            break

    if col_names is None:
        # Try to infer: first non-comment line with many tokens
        for i, line in enumerate(lines):
            if line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) >= 2:
                # Assume first field is datetime-like
                col_names = ["time"] + char_list
                header_idx = i - 1
                break

    results = []
    data_start = (header_idx + 1) if header_idx is not None else 0

    for line in lines[data_start:]:
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        try:
            # First token is ISO timestamp
            ts_str = parts[0]
            # Handle formats like 2026-05-28T17:45:00.000Z or 2026-05-28 17:45:00
            ts_str = ts_str.replace("Z", "+00:00")
            if "T" not in ts_str and len(parts) > 1:
                # Maybe date + time are separate tokens
                ts_str = parts[0] + "T" + parts[1] + "+00:00"
                raw_values = parts[2:]
            else:
                raw_values = parts[1:]

            # GIRO format: CS(confidence) val1 // val2 // val3 // val4 flags
            # Skip parts[1] (CS confidence score), strip '//' quality delimiters
            value_parts = [p for p in raw_values[1:] if p != '//']

            ts = datetime.fromisoformat(ts_str)
            row = {"time": ts}
            for j, char in enumerate(char_list):
                if j < len(value_parts):
                    try:
                        v = float(value_parts[j])
                        # GIRO uses 999.x as missing
                        row[char] = None if v > 900 else v
                    except ValueError:
                        row[char] = None
                else:
                    row[char] = None
            results.append(row)
        except Exception as e:
            log.debug("Skipping GIRO line '%s': %s", line[:60], e)

    return results


# ──────────────────────────────────────────────────────────────
# NOAA SWPC — Kp, SFI, solar wind, X-ray
# ──────────────────────────────────────────────────────────────

SWPC_BASE = "https://services.swpc.noaa.gov"


def fetch_kp() -> Optional[dict]:
    """Return most recent Kp estimate and a short history list."""
    url = f"{SWPC_BASE}/json/planetary_k_index_1m.json"
    try:
        r = requests.get(url, timeout=TIMEOUT)
        r.raise_for_status()
        data = r.json()
        if not data:
            return None
        # data is list of [time_tag, kp_index, estimated_kp, kp_status]
        # or [[time, kp], ...]  — handle both
        last = data[-1]
        if isinstance(last, list):
            kp_val = float(last[1]) if len(last) > 1 else None
            time_str = last[0]
        elif isinstance(last, dict):
            # Prefer estimated_kp (always a float); kp_index=0 is falsy so avoid `or` chain
            _kp = last.get("estimated_kp") if last.get("estimated_kp") is not None else last.get("kp_index")
            kp_val = float(_kp) if _kp is not None else None
            time_str = last.get("time_tag") or last.get("time")
        else:
            return None

        # Build short history (last 96 points = 96 min at 1-min cadence)
        history = []
        for row in data[-96:]:
            if isinstance(row, list):
                history.append({"time": row[0], "kp": float(row[1]) if row[1] is not None else None})
            elif isinstance(row, dict):
                _kp = row.get("estimated_kp") if row.get("estimated_kp") is not None else row.get("kp_index", 0)
                history.append({
                    "time": row.get("time_tag") or row.get("time"),
                    "kp": float(_kp) if _kp is not None else 0.0,
                })

        return {"kp": kp_val, "time": time_str, "history": history}
    except Exception as e:
        log.warning("Kp fetch failed: %s", e)
        return None


def fetch_sfi() -> Optional[dict]:
    """Return latest F10.7 solar flux index."""
    url = f"{SWPC_BASE}/json/f107_cm_flux.json"
    try:
        r = requests.get(url, timeout=TIMEOUT)
        r.raise_for_status()
        data = r.json()
        if not data:
            return None
        last = data[-1]
        if isinstance(last, list):
            return {"sfi": float(last[1]), "time": last[0]}
        elif isinstance(last, dict):
            return {
                "sfi": float(last.get("flux") or last.get("f107") or 0),
                "time": last.get("time_tag") or last.get("time"),
            }
    except Exception as e:
        log.warning("SFI fetch failed: %s", e)

    # Fallback: parse WWV geophysical alert text
    return fetch_sfi_from_wwv()


def fetch_sfi_from_wwv() -> Optional[dict]:
    """Parse NOAA geophysical alert (WWV) text for SFI, A, K."""
    url = "https://services.swpc.noaa.gov/text/wwv.txt"
    try:
        r = requests.get(url, timeout=TIMEOUT)
        r.raise_for_status()
        text = r.text
        result = {}

        for line in text.splitlines():
            # Solar Flux 173
            m = re.search(r"Solar Flux\s+(\d+)", line, re.I)
            if m:
                result["sfi"] = int(m.group(1))
            # Planetary A Index 8
            m = re.search(r"Planetary A Index\s+(\d+)", line, re.I)
            if m:
                result["a_index"] = int(m.group(1))
            # Planetary K Index 2
            m = re.search(r"Planetary K Index\s+(\d+)", line, re.I)
            if m:
                result["kp"] = int(m.group(1))

        result["time"] = datetime.now(timezone.utc).isoformat()
        return result if result else None
    except Exception as e:
        log.warning("WWV fetch failed: %s", e)
        return None


def fetch_solar_wind() -> Optional[dict]:
    """Return latest solar wind speed and Bz from DSCOVR."""
    url = f"{SWPC_BASE}/products/summary/solar-wind-mag-field.json"
    try:
        r = requests.get(url, timeout=TIMEOUT)
        r.raise_for_status()
        d = r.json()
        return {
            "speed": d.get("WindSpeed"),
            "bz": d.get("Bz"),
            "bt": d.get("Bt"),
            "time": d.get("TimeStamp"),
        }
    except Exception as e:
        log.warning("Solar wind fetch failed: %s", e)

    # Try alternate endpoint
    url2 = f"{SWPC_BASE}/json/rtsw/rtsw_wind_1m.json"
    try:
        r = requests.get(url2, timeout=TIMEOUT)
        r.raise_for_status()
        data = r.json()
        if data:
            last = data[-1]
            if isinstance(last, dict):
                return {
                    "speed": last.get("proton_speed") or last.get("speed"),
                    "bz": last.get("bz_gsm") or last.get("bz"),
                    "bt": last.get("bt"),
                    "time": last.get("time_tag"),
                }
    except Exception as e2:
        log.warning("Solar wind alt fetch failed: %s", e2)

    return None


def fetch_xray() -> Optional[dict]:
    """Return latest GOES X-ray flux (for flare detection)."""
    url = f"{SWPC_BASE}/json/goes/primary/xrays-7-day.json"
    try:
        r = requests.get(url, timeout=TIMEOUT)
        r.raise_for_status()
        data = r.json()
        if not data:
            return None
        # Find most recent 1-min entries for both channels
        short = [d for d in data if d.get("energy") == "0.05-0.4nm"]
        long_ = [d for d in data if d.get("energy") == "0.1-0.8nm"]
        latest_long = long_[-1] if long_ else None
        if latest_long:
            flux = float(latest_long.get("flux", 0))
            return {
                "flux": flux,
                "class": _xray_class(flux),
                "time": latest_long.get("time_tag"),
            }
    except Exception as e:
        log.warning("X-ray fetch failed: %s", e)
    return None


def _xray_class(flux: float) -> str:
    if flux >= 1e-4:
        return "X"
    elif flux >= 1e-5:
        return "M"
    elif flux >= 1e-6:
        return "C"
    elif flux >= 1e-7:
        return "B"
    else:
        return "A"


# ──────────────────────────────────────────────────────────────
# Band condition estimator — NVIS + DX
# ──────────────────────────────────────────────────────────────
#
# Solar offset rationale:
#   IF843 (Idaho NL) is at 112.7°W; Freeland WA is at 122.5°W.
#   Longitude delta ≈ 9.8° → 9.8 * 4 min/° ≈ 39 min solar time.
#   We treat IF843 as representing conditions ~40 min ahead of Freeland.
#   Fetch the sounding from ~40 min ago so it reflects current Freeland sky.
#
# NVIS: near-vertical incidence skywave. Works when band freq < foF2.
#   Best for 0–500 km regional paths. 80m/60m/40m are the prime NVIS bands.
#   foF2 is the hard ceiling — above it, NVIS fails.
#   Below foF2 but above D-region absorption cutoff (~2 MHz day, ~1 MHz night)
#   = good NVIS. Well below foF2 (freq << foF2) = absorption risk on lower bands.
#
# DX: oblique F2 skip. Works when freq < MUF(3000).
#   MUF(3000) from GIRO is the 3000 km one-hop oblique MUF.
#   Operating near 85–95% of MUF is the sweet spot; above MUF = no F2 path.
#   Below ~50% MUF on a given band = likely not the limiting factor,
#   other propagation modes (E, Es) may dominate.
#
# Grades: Excellent / Good / Fair / Poor / Closed / Unknown

BANDS = [
    # (label,  center_freq_MHz, nvis_capable, dx_capable)
    ("160m",  1.9,  True,  False),  # NVIS only when foF2 > 2; DX via surface wave only
    ("80m",   3.6,  True,  True),   # Prime NVIS band; DX at night
    ("60m",   5.3,  True,  True),   # Good NVIS; DX possible
    ("40m",   7.1,  True,  True),   # NVIS day; DX dusk/dawn/night
    ("30m",  10.1,  False, True),   # DX; marginal NVIS
    ("20m",  14.2,  False, True),   # DX workhorse
    ("17m",  18.1,  False, True),
    ("15m",  21.2,  False, True),
    ("12m",  24.9,  False, True),
    ("10m",  28.5,  False, True),
    ("6m",   50.0,  False, True),   # Sporadic-E / F2 openings only
]

# Grade scale: 5=Excellent, 4=Good, 3=Fair, 2=Poor, 1=Closed, 0=Unknown
GRADE_LABELS = {5: "Excellent", 4: "Good", 3: "Fair", 2: "Poor", 1: "Closed", 0: "Unknown"}
GRADE_COLORS = {5: "#00e676", 4: "#69f0ae", 3: "#ffc107", 2: "#ff7043", 1: "#ef5350", 0: "#607d8b"}


def _kp_penalty(kp: Optional[float]) -> int:
    """Grade penalty from geomagnetic activity. Higher Kp = worse HF, esp. high bands."""
    if kp is None:
        return 0
    if kp >= 8:
        return 4
    if kp >= 6:
        return 3
    if kp >= 5:
        return 2
    if kp >= 4:
        return 1
    return 0


def _xray_penalty(xray_class: Optional[str]) -> int:
    """Grade penalty from solar X-ray flux (flare-driven D-region absorption)."""
    if not xray_class:
        return 0
    return {"A": 0, "B": 0, "C": 1, "M": 2, "X": 3}.get(xray_class[0], 0)


def grade_nvis(freq: float, fof2: float, kp: Optional[float], xray_class: Optional[str]) -> tuple[int, str]:
    """
    Grade NVIS suitability for a given band frequency.

    Returns (grade 0–5, note string).

    Physics:
      freq < foF2          → wave reflected at F2, good NVIS
      freq ≈ foF2 * 0.9   → approaching critical angle, still useful
      freq > foF2          → wave punches through, NVIS fails
      freq < ~2 MHz (day)  → D-region absorption kills it on 160m during daylight
    """
    note_parts = []

    if freq > fof2:
        # Above foF2 — NVIS is impossible, wave passes through
        margin = (freq - fof2) / fof2
        if margin > 0.3:
            grade = 1  # Closed
        else:
            grade = 2  # Poor — barely above, some near-vertical may still reflect
        note_parts.append(f"f={freq} MHz > foF2 {fof2:.2f} MHz — wave punches through F2, no NVIS return")
    elif freq > fof2 * 0.90:
        grade = 4   # Good — near critical, strong reflection
        note_parts.append(f"f={freq} MHz near foF2 ceiling {fof2:.2f} MHz — strong near-vertical reflection")
    elif freq > fof2 * 0.60:
        grade = 5   # Excellent — well below foF2, robust reflection
        note_parts.append(f"f={freq} MHz well below foF2 {fof2:.2f} MHz — robust F2 reflection, excellent NVIS")
    elif freq > fof2 * 0.35:
        grade = 4   # Good — lower frequency, some D-region absorption risk
        note_parts.append(f"f={freq} MHz below foF2 {fof2:.2f} MHz — good NVIS, D-region absorption possible")
    else:
        grade = 3   # Fair — well below foF2, likely D-region absorbed (esp. 160m day)
        note_parts.append(f"f={freq} MHz — D-region absorption likely at this frequency")

    # Apply penalties
    penalty = _kp_penalty(kp) + _xray_penalty(xray_class)
    if penalty:
        note_parts.append(f"Kp/flare -{'⬇' * min(penalty, 3)}")
    grade = max(1, grade - penalty)

    return grade, " · ".join(note_parts)


def grade_dx(freq: float, fof2: float, muf3000: float,
             kp: Optional[float], xray_class: Optional[str]) -> tuple[int, str]:
    """
    Grade DX (oblique F2 skip) suitability.

    Returns (grade 0–5, note string).

    Physics:
      MUF(3000) is one-hop oblique MUF for a 3000 km path.
      Operating at 85–95% of MUF is sweet spot (lower angle, stronger signal).
      Above MUF: skip zone — no F2 path.
      Well below MUF: the band is "open" but may have long skip (dead zone nearby).
      Below foF2: wave reflects nearly vertically — very short skip, no DX.

    We also estimate a rough MUF for shorter paths (1000 km) as ≈ 0.75 * MUF(3000),
    giving a sense of whether even regional DX (1000–2000 km) is available.
    """
    note_parts = []

    pct_of_muf = freq / muf3000  # 0..1+ where 1.0 = exactly at MUF

    # Estimated one-hop skip range via linear M(D) interpolation
    _md = muf3000 / fof2
    _d_min = max(0, int(3000 * (freq / fof2 - 1) / (_md - 1))) if _md > 1 and freq > fof2 else 0
    _d_max = 3500

    if freq > muf3000 * 1.05:
        grade = 1  # Closed — above MUF, no F2 return
        note_parts.append(f"f={freq} MHz > MUF {muf3000:.1f} MHz — no F2 skip on this band")
    elif freq > muf3000 * 0.95:
        grade = 4  # Good — right at MUF, low-angle strong path but unstable
        note_parts.append(f"f={freq} MHz at MUF {muf3000:.1f} MHz ({pct_of_muf*100:.0f}%) — low-angle path, skip ~{_d_max} km/hop")
    elif freq > muf3000 * 0.80:
        grade = 5  # Excellent — sweet spot
        note_parts.append(f"f={freq} MHz = {pct_of_muf*100:.0f}% of MUF {muf3000:.1f} MHz — skip ~{_d_min}–{_d_max} km/hop")
    elif freq > muf3000 * 0.55:
        grade = 4  # Good — open, longer skip zone
        note_parts.append(f"f={freq} MHz = {pct_of_muf*100:.0f}% of MUF {muf3000:.1f} MHz — skip ~{_d_min}–{_d_max} km/hop")
    elif freq > muf3000 * 0.35:
        grade = 3  # Fair — open but F2 may be sharing with other modes
        note_parts.append(f"f={freq} MHz = {pct_of_muf*100:.0f}% of MUF {muf3000:.1f} MHz — skip ~{_d_min}–{_d_max} km/hop (multi-mode)")
    elif freq > fof2:
        grade = 2  # Poor — above foF2 so some oblique path exists, but very low angle
        note_parts.append(f"f={freq} MHz > foF2 {fof2:.2f} MHz — oblique path exists but skip ~{_d_min}–500 km only")
    else:
        grade = 2  # Poor — below foF2, NVIS dominates, no real DX
        note_parts.append(f"f={freq} MHz < foF2 {fof2:.2f} MHz — wave reflects vertically, NVIS only, no DX skip")

    # Apply penalties (Kp hits high bands harder at high latitudes like CN88)
    # Extra Kp penalty for high bands at high latitude (polar cap absorption)
    kp_pen = _kp_penalty(kp)
    if kp is not None and kp >= 4 and freq >= 14:
        kp_pen += 1   # high-lat auroral absorption bites harder above 14 MHz
    penalty = kp_pen + _xray_penalty(xray_class)
    if penalty:
        note_parts.append(f"Kp/flare -{'⬇' * min(penalty, 3)}")
    grade = max(1, grade - penalty)

    return grade, " · ".join(note_parts)


def estimate_band_conditions(
    fof2: Optional[float],
    muf: Optional[float],
    kp: Optional[float],
    sfi: Optional[float],
    xray_class: Optional[str] = None,
) -> list[dict]:
    """
    Return NVIS and DX grades for each band.

    Each entry:
      band, freq_mhz,
      nvis_grade (0–5), nvis_label, nvis_note, nvis_color,
      dx_grade (0–5), dx_label, dx_note, dx_color
    """
    results = []

    for band, freq, nvis_capable, dx_capable in BANDS:
        row = {
            "band": band,
            "freq_mhz": freq,
            "nvis_grade": 0, "nvis_label": "N/A", "nvis_note": "Not a NVIS band", "nvis_color": GRADE_COLORS[0],
            "dx_grade":   0, "dx_label":   "N/A", "dx_note":   "Not a DX band",   "dx_color":   GRADE_COLORS[0],
        }

        if fof2 is None or muf is None:
            row["nvis_label"] = "Unknown"
            row["nvis_note"]  = "No ionosonde data"
            row["dx_label"]   = "Unknown"
            row["dx_note"]    = "No ionosonde data"
            results.append(row)
            continue

        if nvis_capable:
            g, note = grade_nvis(freq, fof2, kp, xray_class)
            row["nvis_grade"] = g
            row["nvis_label"] = GRADE_LABELS[g]
            row["nvis_note"]  = note
            row["nvis_color"] = GRADE_COLORS[g]

        if dx_capable:
            g, note = grade_dx(freq, fof2, muf, kp, xray_class)
            row["dx_grade"] = g
            row["dx_label"] = GRADE_LABELS[g]
            row["dx_note"]  = note
            row["dx_color"] = GRADE_COLORS[g]

        results.append(row)

    return results
