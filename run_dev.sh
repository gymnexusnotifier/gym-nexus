#!/usr/bin/env bash
# Development run helper - uses the venv python to start uvicorn
# Usage: ./run_dev.sh

set -euo pipefail

# Default venv folder name (adjust if your venv is named differently)
VENV_DIR="env"

if [ ! -x "${VENV_DIR}/bin/python" ]; then
  echo "Warning: ${VENV_DIR}/bin/python not found or not executable.\nMake sure you created a virtualenv named '${VENV_DIR}' or edit this script to point to your venv." >&2
  echo "Suggested commands to create venv:\n  python3 -m venv ${VENV_DIR}\n  source ${VENV_DIR}/bin/activate\n  pip install -r requirements.txt" >&2
  exit 1
fi

# Use venv python to run uvicorn so child processes inherit same interpreter
exec "${VENV_DIR}/bin/python" -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
