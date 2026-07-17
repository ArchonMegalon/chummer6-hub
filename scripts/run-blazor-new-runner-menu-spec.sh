#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "${script_dir}/.." && pwd)"

base_url="${BASE_URL:-${CHUMMER_PUBLIC_BASE_URL:-https://chummer.run}}"
reporter="${PLAYWRIGHT_REPORTER:-line}"

cd "$repo_root"
BASE_URL="$base_url" ./node_modules/.bin/playwright test \
  tests/public/blazor-new-runner-menu.spec.ts \
  --reporter="$reporter" \
  "$@"
