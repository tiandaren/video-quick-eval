#!/usr/bin/env sh
set -eu

PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)

is_compatible_python() {
  command -v "$1" >/dev/null 2>&1 &&
    "$1" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >/dev/null 2>&1
}

if [ "${PYTHON:-}" ]; then
  if ! is_compatible_python "$PYTHON"; then
    printf '%s\n' "PYTHON must point to Python 3.11 or newer: $PYTHON" >&2
    exit 2
  fi
  PYTHON_CMD=$PYTHON
else
  PYTHON_CMD=
  for candidate in python3.14 python3.13 python3.12 python3.11 python3; do
    if is_compatible_python "$candidate"; then
      PYTHON_CMD=$candidate
      break
    fi
  done
  if [ -z "$PYTHON_CMD" ]; then
    printf '%s\n' 'Python 3.11 or newer was not found. Install it with your system package manager, then run this script again.' >&2
    exit 2
  fi
fi

printf '%s\n' "Using Python: $PYTHON_CMD"
"$PYTHON_CMD" --version
"$PYTHON_CMD" -m venv "$PROJECT_DIR/.venv"
"$PROJECT_DIR/.venv/bin/python" -m pip install --upgrade pip
"$PROJECT_DIR/.venv/bin/python" -m pip install "$PROJECT_DIR"
printf '%s\n' 'Installed. Run: ./scripts/run.sh --help'
