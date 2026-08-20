#!/usr/bin/env sh
set -eu

PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
PYTHON=${VIDEO_QUICK_EVAL_PYTHON:-"$PROJECT_DIR/.venv/bin/python"}

if [ ! -x "$PYTHON" ]; then
  printf '%s\n' 'No project environment found. Run ./scripts/setup.sh first.' >&2
  exit 2
fi

exec "$PYTHON" "$PROJECT_DIR/transcribe.py" "$@"
