#!/usr/bin/env bash
# Cross-platform Python launcher for AI log hooks.
# Tries python3 → python → py -3 on PATH; on Windows, falls back to common
# Python install locations because Git Bash launched by some hooks gets a
# stripped PATH that omits the Windows Python directory.
# Designed to be sourced or called as: bash scripts/_pyrun.sh <script> [args...]
#
# Exits 0 silently if no Python is found — hooks must never block the AI tool.
set -u

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

# Prefer the repository virtual environment. This avoids the Windows Store
# `python.exe` app-execution alias, which is visible on PATH but is not a real
# interpreter when Python was installed elsewhere.
for cand in \
  "$SCRIPT_DIR/../.venv/Scripts/python.exe" \
  "$SCRIPT_DIR/../.venv/bin/python"; do
  if [ -x "$cand" ] && "$cand" -c "import sys" >/dev/null 2>&1; then
    exec "$cand" "$@"
  fi
done

# A command being present on PATH is not enough on Windows: verify that it can
# actually start before selecting it.
for cmd in python3 python; do
  if command -v "$cmd" >/dev/null 2>&1 &&
     "$cmd" -c "import sys" >/dev/null 2>&1; then
    exec "$cmd" "$@"
  fi
done

if command -v py >/dev/null 2>&1 && py -3 -c "import sys" >/dev/null 2>&1; then
  exec py -3 "$@"
fi

# PATH lookup failed — probe common Windows installation locations.
shopt -s nullglob 2>/dev/null || true
for cand in \
  /c/Users/*/AppData/Local/Programs/Python/Python*/python.exe \
  "/c/Program Files/Python"*/python.exe \
  "/c/Program Files (x86)/Python"*/python.exe \
  /c/Python*/python.exe; do
  if [ -x "$cand" ] && "$cand" -c "import sys" >/dev/null 2>&1; then
    exec "$cand" "$@"
  fi
done
shopt -u nullglob 2>/dev/null || true

# Logging must never block the AI tool or git push when Python is unavailable.
exit 0
