#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(/usr/bin/dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
ROOT_DIR="$(cd -- "$script_dir/../.." && pwd -P)"

exec /usr/bin/python3 -I -S \
  "$ROOT_DIR/scripts/materialize_campaign_os_local_proof.py" \
  run
