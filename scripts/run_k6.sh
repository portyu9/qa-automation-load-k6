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

if [[ "$PROFILE" != "smoke" ]]; then
  if [[ "${K6_ALLOW_LOAD_TEST:-}" != "true" ]]; then
    echo "Refusing to run $PROFILE without K6_ALLOW_LOAD_TEST=true." >&2
    exit 3
  fi

  if [[ -z "${K6_ALLOWED_HOSTS:-}" ]]; then
    echo "Refusing to run $PROFILE without K6_ALLOWED_HOSTS." >&2
    echo "List the exact authorized target hostname; the k6 runtime verifies the match." >&2
    exit 4
  fi
fi

if [[ -z "${K6_BASE_URL:-}" ]]; then
  echo "Refusing to run $PROFILE without an explicit K6_BASE_URL." >&2
  exit 5
fi

if ! command -v k6 >/dev/null 2>&1; then
  echo "k6 is not installed. Install k6 or run the pinned Docker image." >&2
  exit 1
fi

mkdir -p reports
echo "profile=$PROFILE runId=${K6_RUN_ID:-local} target=<validated-by-k6>"
k6 run "tests/${PROFILE}.js" "$@"
