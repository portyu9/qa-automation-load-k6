#!/usr/bin/env bash
# Helper script to run k6 test scripts.
# Usage: ./run_k6.sh [path_to_script] [additional k6 args]
set -e

SCRIPT=${1:-tests/load.js}

# Check if k6 is installed
if ! command -v k6 >/dev/null 2>&1; then
  echo "k6 is not installed. Please install k6 or run via Docker." >&2
  exit 1
fi

echo "Running k6 script: $SCRIPT"
# Shift first argument so that remaining arguments pass through to k6
shift || true
k6 run "$SCRIPT" "$@"
