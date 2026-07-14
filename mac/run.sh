#!/bin/bash
# device v2 — run the Mac simulator with one command:
#
#     bash mac/run.sh              # the simulator window
#     bash mac/run.sh --selftest   # headless scripted checkout
#
# Idempotent: creates .venv and installs deps on first run, reuses after.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

UV="$(command -v uv || true)"
[ -z "$UV" ] && [ -x "$HOME/.local/bin/uv" ] && UV="$HOME/.local/bin/uv"

if [ ! -d .venv ]; then
    # newest Python >= 3.10 wins; uv is the fallback provider
    PY=""
    for c in python3.13 python3.12 python3.11 python3.10 python3; do
        if command -v "$c" >/dev/null 2>&1 \
           && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
            PY="$c"
            break
        fi
    done
    if [ -n "$PY" ]; then
        echo "==> Creating virtualenv with $PY (first run only)"
        "$PY" -m venv .venv
    elif [ -n "$UV" ]; then
        echo "==> Creating virtualenv with uv (first run only)"
        "$UV" venv --python 3.12 --seed .venv
    else
        echo "Need Python 3.10+ (macOS ships 3.9 — try 'brew install python'"
        echo "or uv: curl -LsSf https://astral.sh/uv/install.sh | sh)."
        exit 1
    fi
fi
echo "==> Installing dependencies"
if [ -x .venv/bin/pip ]; then
    .venv/bin/pip install --quiet -r requirements-mac.txt
elif [ -n "$UV" ]; then
    # uv-created venvs ship without pip; drive uv at the venv instead
    VIRTUAL_ENV="$PWD/.venv" "$UV" pip install --quiet -r requirements-mac.txt
else
    .venv/bin/python -m ensurepip --upgrade >/dev/null
    .venv/bin/python -m pip install --quiet -r requirements-mac.txt
fi
echo "==> Launching"
exec .venv/bin/python mac/prototype.py "$@"
