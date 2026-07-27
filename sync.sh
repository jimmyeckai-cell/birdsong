#!/usr/bin/env bash
# Run this when you SIT DOWN at a machine: pull the latest catalog before you
# start working, so the two computers never diverge.
set -euo pipefail
cd "$(dirname "$0")"

echo "Pulling latest from GitHub..."
git pull --rebase
echo "Up to date. Ready to work."
