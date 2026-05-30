#!/usr/bin/env bash
# update_iono.sh — cron wrapper: scrape ionogram, commit updated JSON to repo.
#
# Crontab (every 15 min):
#   */15 * * * * /path/to/hf_dashboard/scripts/update_iono.sh >> /tmp/iono_update.log 2>&1
#
# One-time setup:
#   sudo apt install tesseract-ocr
#   curl -LsSf https://astral.sh/uv/install.sh | sh
#   ssh-keygen -t ed25519 && cat ~/.ssh/id_ed25519.pub  # add to GitHub deploy keys

set -euo pipefail
export PATH="$HOME/.local/bin:$PATH"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"

echo "--- $(date -u +%Y-%m-%dT%H:%MZ) ---"

uvx --quiet \
    --with Pillow \
    --with pytesseract \
    --with requests \
    python3 scripts/scrape_iono.py

# Commit only if data files changed
git add data/iono_cache.json data/iono_history.json
if git diff --cached --quiet; then
    echo "No change in data."
else
    git commit -m "auto: ionosonde $(date -u +%H:%MZ)"
    git push
    echo "Pushed."
fi
