#!/usr/bin/env bash
set -euo pipefail

PROFILE=${1:-smoke}
shift || true

case "$PROFILE" in
  smoke|load|stress|soak) ;;
  *)
    echo "Unknown profile '$PROFILE'. Use smoke, load, stress, or soak." >&2
    exit 2
    ;;
esac

if [[ "$PROFILE" != "smoke" && "${K6_ALLOW_LOAD_TEST:-}" != "true" ]]; then
  echo "Refusing to run $PROFILE without K6_ALLOW_LOAD_TEST=true." >&2
  echo "Set it only when K6_BASE_URL points to a target authorized for performance testing." >&2
  exit 3
fi

if ! command -v k6 >/dev/null 2>&1; then
  echo "k6 is not installed. Install k6 or run the pinned Docker image." >&2
  exit 1
fi

mkdir -p reports
echo "profile=$PROFILE target=${K6_BASE_URL:-https://jsonplaceholder.typicode.com} runId=${K6_RUN_ID:-local}"
k6 run "tests/${PROFILE}.js" "$@"
