#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
repo_root="$(cd "$script_dir/.." && pwd -P)"
bootstrap_path="$repo_root/Chummer.Run.Api/wwwroot/artifacts/mac-codex-release-pipeline/bootstrap.sh"

if [[ ! -f "$bootstrap_path" ]]; then
  cat >&2 <<EOF
[chummer-mac-release-wrapper] ERROR: bootstrap template not found at:
  $bootstrap_path

Run this wrapper from a real chummer.run-services checkout, or use one of the hosted entry points instead:

  Signed-in release upload handoff:
    https://chummer.run/downloads/release-upload

  Public bootstrap:
    bash <(curl -fsSL https://chummer.run/artifacts/mac-codex-release-pipeline/bootstrap.sh)
EOF
  exit 1
fi

exec bash "$bootstrap_path" "$@"
