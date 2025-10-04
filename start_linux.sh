#!/usr/bin/env bash

set -Eeuo pipefail

# Environment isolation
export PYTHONNOUSERSITE=1
unset PYTHONPATH || true
unset PYTHONHOME || true

# Move to repo root (directory of this script)
cd "$(dirname "${BASH_SOURCE[0]}")"

# Choose Python interpreter: prefer python3.11, fallback to python3
PYTHON_BIN=${PYTHON_BIN:-python3.11}
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  PYTHON_BIN=python3
fi

# Create virtual environment if missing
if [ ! -d ".venv" ]; then
  echo "Creating virtual environment in .venv using $PYTHON_BIN"
  "$PYTHON_BIN" -m venv .venv
fi

# Activate venv
source .venv/bin/activate

# Basic tooling
python -m pip install --upgrade pip setuptools wheel >/dev/null

# Ensure Poetry is available inside the venv
if ! command -v poetry >/dev/null 2>&1; then
  python -m pip install "poetry==1.8.*"
fi

# Install dependencies via Poetry into current venv
if [ -f "pyproject.toml" ]; then
  poetry config virtualenvs.create false
  poetry install --no-interaction --no-ansi --no-root
else
  echo "pyproject.toml not found. If you use requirements.txt, installing with pip..."
  if [ -f "requirements.txt" ]; then
    python -m pip install -r requirements.txt
  else
    echo "No dependency file found. Continuing..."
  fi
fi

# Load environment variables from .env if present
set -a
if [ -f ".env" ]; then
  . ./.env
fi
set +a

# Defaults can be overridden by env or CLI
HOST=${HOST:-0.0.0.0}
PORT=${PORT:-8000}

# Start the app
exec uvicorn app.main:app --host "$HOST" --port "$PORT" "$@"


