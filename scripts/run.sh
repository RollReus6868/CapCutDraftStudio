#!/usr/bin/env bash
# Mo CapCut Draft Studio tren macOS / Linux.
set -e
cd "$(dirname "$0")/.."
if [ -x ".venv/bin/python" ]; then
  exec .venv/bin/python -m capcut_draft_studio.app
fi
for c in python3.12 python3.11 python3.10 python3; do
  if command -v "$c" >/dev/null 2>&1; then exec "$c" -m capcut_draft_studio.app; fi
done
echo "[LOI] Chua cai dat. Chay ./scripts/install.sh truoc."
exit 1
