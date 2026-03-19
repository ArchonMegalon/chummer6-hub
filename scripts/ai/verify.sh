#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/_env.sh"

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT_DIR"

bash scripts/ai/build_r1_cleanroom.sh
bash scripts/ai/run_services_restore_drill.sh
bash scripts/ai/run_services_verification.sh
bash scripts/ai/run_services_smoke.sh
