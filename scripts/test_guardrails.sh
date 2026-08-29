#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT

cat >"$TMP_DIR/k6" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >"${K6_STUB_OUTPUT:?}"
STUB
chmod +x "$TMP_DIR/k6"

export PATH="$TMP_DIR:$PATH"
export K6_STUB_OUTPUT="$TMP_DIR/invocation.txt"

assert_refused() {
  local expected_exit=$1
  shift
  set +e
  "$@" >/dev/null 2>&1
  local actual_exit=$?
  set -e
  if [[ "$actual_exit" -ne "$expected_exit" ]]; then
    echo "expected exit $expected_exit, got $actual_exit: $*" >&2
    exit 1
  fi
}

assert_refused 3 env -u K6_ALLOW_LOAD_TEST -u K6_ALLOWED_HOSTS \
  "$ROOT/scripts/run_k6.sh" load
assert_refused 4 env -u K6_ALLOWED_HOSTS K6_ALLOW_LOAD_TEST=true \
  "$ROOT/scripts/run_k6.sh" load
assert_refused 5 env -u K6_BASE_URL \
  "$ROOT/scripts/run_k6.sh" smoke
assert_refused 5 env -u K6_BASE_URL K6_ALLOW_LOAD_TEST=true K6_ALLOWED_HOSTS=example.test \
  "$ROOT/scripts/run_k6.sh" load

K6_ALLOW_LOAD_TEST=true \
K6_ALLOWED_HOSTS=example.test \
K6_BASE_URL=https://example.test \
  "$ROOT/scripts/run_k6.sh" load --quiet >/dev/null

grep -Fxq 'run tests/load.js --quiet' "$K6_STUB_OUTPUT"

sensitive_target='https://user:password@example.test/api?access_token=secret'
wrapper_output=$(K6_BASE_URL="$sensitive_target" "$ROOT/scripts/run_k6.sh" smoke --quiet)
if grep -Fq "$sensitive_target" <<<"$wrapper_output"; then
  echo 'unvalidated k6 target leaked to wrapper output' >&2
  exit 1
fi
if grep -Fq 'password' <<<"$wrapper_output" || grep -Fq 'access_token' <<<"$wrapper_output"; then
  echo 'sensitive k6 target material leaked to wrapper output' >&2
  exit 1
fi

echo 'k6 shell guardrail contract: ok'
