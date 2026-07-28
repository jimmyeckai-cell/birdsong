#!/usr/bin/env bash
# Run this when you're DONE working at a machine: rebuild the HTML page from the
# catalog, then commit and push everything so the other computer can pull it.
#
# Usage:  ./save.sh ["optional commit message"]
set -euo pipefail
cd "$(dirname "$0")"

PY=./venv/bin/python
[ -x "$PY" ] || PY=python3

# 1. Extract any new top-song clips (needs the source recording locally; songs
#    whose recording isn't on this machine are skipped), then regenerate the
#    page so bird_catalog.html matches the JSON.
echo "Extracting top-song clips..."
"$PY" extract_clips.py
echo "Building spectrograms..."
"$PY" build_spectrograms.py
echo "Rendering bird watercolors (uses cache when offline)..."
"$PY" fetch_watercolors.py || echo "  (watercolor render skipped/failed — cached art still used)"
echo "Regenerating bird_catalog.html..."
"$PY" generate_catalog_html.py

# 2. Stage everything (catalog data, page, new recordings, code changes).
git add -A

# 3. Nothing changed? Stop cleanly.
if git diff --cached --quiet; then
  echo "No changes to save."
  exit 0
fi

# 4. Commit.
MSG="${1:-Update catalog ($(date +%Y-%m-%d\ %H:%M))}"
git commit -q -m "$MSG"
echo "Committed: $MSG"

# 5. Rebase on any remote changes, then push. If a push target exists.
if git remote get-url origin >/dev/null 2>&1; then
  echo "Syncing with GitHub..."
  git pull --rebase
  git push
  echo "Pushed. The other machine can now run ./sync.sh to get this."
else
  echo "No 'origin' remote set yet — committed locally only."
fi
