#!/usr/bin/env bash
set -euo pipefail

echo "[audit] running hosted boundary verification"
COMPOSE_FILE=legacy/tooling/docker/docker-compose.yml docker compose --profile test run --build --rm chummer-tests

echo "[audit] compliance checks passed"
