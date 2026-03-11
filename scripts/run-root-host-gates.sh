#!/usr/bin/env bash
set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run this script as root (for example: sudo bash scripts/run-root-host-gates.sh)." >&2
  exit 1
fi

REPO_ROOT="${1:-/docker/chummer5a}"
if [[ ! -d "$REPO_ROOT" ]]; then
  echo "Repository path not found: $REPO_ROOT" >&2
  exit 1
fi

cd "$REPO_ROOT"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOG_DIR="${LOG_DIR:-/var/log/chummer-host-gates/$STAMP}"
mkdir -p "$LOG_DIR"

TEST_FILTER_VALUE="${TEST_FILTER:-${2:-}}"
TEST_FRAMEWORK_VALUE="${TEST_FRAMEWORK:-${3:-net10.0}}"

echo "== chummer root host gate run =="
echo "repo: $REPO_ROOT"
echo "logs: $LOG_DIR"
echo "timestamp: $STAMP"
echo "framework: $TEST_FRAMEWORK_VALUE"
echo

echo "== quick diagnostics =="
dotnet --version || true
docker --version || true
python3 --version || true
echo "api.nuget.org DNS:"
getent hosts api.nuget.org || true
echo

echo "== host prerequisites (strict) =="
RUNBOOK_LOG_DIR="$LOG_DIR" \
RUNBOOK_MODE=host-prereqs \
PREREQ_LOG_FILE="$LOG_DIR/host-prereqs.log" \
CHECK_DOCKER=1 \
CHECK_NUGET=1 \
bash scripts/runbook.sh | tee "$LOG_DIR/host-prereqs.console.log"

echo
echo "== strict host gates =="
RUNBOOK_LOG_DIR="$LOG_DIR" \
TEST_FILTER="$TEST_FILTER_VALUE" \
TEST_FRAMEWORK="$TEST_FRAMEWORK_VALUE" \
DOCKER_TESTS_BUILD="${DOCKER_TESTS_BUILD:-1}" \
bash scripts/runbook-strict-host-gates.sh "$TEST_FILTER_VALUE" "$TEST_FRAMEWORK_VALUE" \
  | tee "$LOG_DIR/strict-host-gates.console.log"

echo
echo "Strict host gates completed successfully."
echo "Log directory: $LOG_DIR"
