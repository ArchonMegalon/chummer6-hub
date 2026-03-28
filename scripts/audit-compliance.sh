#!/usr/bin/env bash
set -euo pipefail

echo "[audit] running hosted boundary verification"
bash scripts/ai/verify.sh

echo "[audit] compliance checks passed"
