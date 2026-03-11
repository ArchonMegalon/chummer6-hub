#!/usr/bin/env bash
set -euo pipefail

echo "[audit] running hosted boundary verification"
docker compose --profile test run --build --rm chummer-tests

echo "[audit] compliance checks passed"
