#!/usr/bin/env python3
"""
scrape_iono.py — Extract ionosonde scaled parameters from GIRO ionogram images.

Uses PIL to crop the parameter panel on the left of each ARTIST-5 ionogram,
then Tesseract OCR to read the values. No cloud API calls.

Run every 15 minutes via cron. Updates:
  data/iono_cache.json   — latest single reading
  data/iono_history.json — rolling ~48h of readings

Dependencies (local machine only, not needed on Streamlit Cloud):
  sudo apt install tesseract-ocr
  pip install Pillow pytesseract requests   (or: uvx --with Pillow --with pytesseract ...)
"""

import json
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests
from PIL import Image, ImageFilter
import pytesseract

REPO_ROOT = Path(__file__).parent.parent
CACHE_FILE = REPO_ROOT / "data" / "iono_cache.json"
HISTORY_FILE = REPO_ROOT / "data" / "iono_history.json"
STATION = "IF843"
MAX_HISTORY = 200  # ~50 hours at 15-min cadence

IONOWEB_LIST = "https://lgdc.uml.edu/ionoweb/ionolist"
IONOWEB_IMG  = "https://lgdc.uml.edu/ionoweb/ionoimage"

# Left-panel crop: x=0..165, y=35..490 captures the parameter table
# on a 900x600 ARTIST-5 / DIDBase ionogram.
CROP_BOX = (0, 35, 165, 490)


def fetch_latest_ionogram(station: str) -> tuple[bytes | None, str | None, int | None]:
    """Return (image_bytes, iso_timestamp, mid) for the most recent ionogram."""
    now = datetime.now(timezone.utc)
    from_date = (now - timedelta(days=1)).strftime("%Y.%m.%d")
    to_date = now.strftime("%Y.%m.%d")
    try:
        r = requests.get(
            IONOWEB_LIST,
            params={"ursiCode": station, "from": from_date, "to": to_date},
            timeout=12,
        )
        r.raise_for_status()
        ionograms = r.json().get("IonogramList", [])
    except Exception as e:
        print(f"ionolist fetch failed: {e}", file=sys.stderr)
        return None, None, None

    if not ionograms:
        print("No ionograms in list", file=sys.stderr)
        return None, None, None

    # Walk backwards to find one marked as scaled (C == "SI")
    for entry in reversed(ionograms):
        if entry.get("C") != "SI":
            continue
        ts = entry["T"]            # "2026-05-28T00:00:00.000Z"
        mid = entry["mid"]
        time_no_z = ts.replace("Z", "").replace("+00:00", "")
        try:
            ir = requests.get(
                IONOWEB_IMG,
                params={"ursiCode": station, "mid": mid, "time": time_no_z},
                timeout=15,
            )
            ir.raise_for_status()
            return ir.content, ts, mid
        except Exception as e:
            print(f"ionoimage fetch failed for mid={mid}: {e}", file=sys.stderr)
            continue

    return None, None, None


def extract_values(image_bytes: bytes) -> dict:
    """
    Crop the parameter panel and OCR it.
    Returns dict with foF2, MUFD, MD (floats or None).
    """
    from io import BytesIO
    img = Image.open(BytesIO(image_bytes)).convert("L")  # greyscale
    panel = img.crop(CROP_BOX)

    # Scale up 2x for better Tesseract accuracy on small text
    w, h = panel.size
    panel = panel.resize((w * 2, h * 2), Image.LANCZOS)

    # Binarize: the text is dark on white, threshold at 128
    panel = panel.point(lambda p: 0 if p < 128 else 255, "1")

    text = pytesseract.image_to_string(
        panel, config="--psm 6 --oem 1 -c tessedit_char_whitelist=foF12EesMUDdhmyBCvst().0123456789- "
    )

    def grab(pattern: str) -> float | None:
        m = re.search(pattern + r"[\s:]+([0-9]+(?:\.[0-9]+)?)", text, re.IGNORECASE)
        return float(m.group(1)) if m else None

    return {
        "foF2": grab(r"foF2"),
        "MUFD": grab(r"MUF\(D\)") or grab(r"MUFD"),
        "MD":   grab(r"M\(D\)")   or grab(r"\bMD\b"),
    }


def load_history() -> list:
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text())
        except Exception:
            pass
    return []


def run():
    image_bytes, timestamp, mid = fetch_latest_ionogram(STATION)
    if not image_bytes:
        print("Could not fetch ionogram image.", file=sys.stderr)
        sys.exit(1)

    values = extract_values(image_bytes)
    if values.get("foF2") is None:
        print("OCR failed to extract foF2.", file=sys.stderr)
        print("Raw OCR output saved to /tmp/iono_ocr_debug.png", file=sys.stderr)
        sys.exit(1)

    fetched_at = datetime.now(timezone.utc).isoformat()
    record = {
        "station":    STATION,
        "time":       timestamp,
        "mid":        mid,
        "foF2":       values["foF2"],
        "MUFD":       values["MUFD"],
        "MD":         values["MD"],
        "D":          None,
        "fetched_at": fetched_at,
    }

    CACHE_FILE.parent.mkdir(exist_ok=True)
    CACHE_FILE.write_text(json.dumps(record, indent=2))

    history = load_history()
    # Avoid duplicate timestamps
    history = [h for h in history if h.get("time") != timestamp]
    history.append({"time": timestamp, "foF2": values["foF2"],
                    "MUFD": values["MUFD"], "MD": values["MD"]})
    history = history[-MAX_HISTORY:]
    HISTORY_FILE.write_text(json.dumps(history, indent=2))

    print(f"OK  {timestamp}  foF2={values['foF2']}  MUF={values['MUFD']}  M(D)={values['MD']}")


if __name__ == "__main__":
    run()
