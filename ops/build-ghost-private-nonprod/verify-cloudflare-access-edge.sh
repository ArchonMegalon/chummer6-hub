#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
repo_root="$(cd -- "$script_dir/../.." && pwd -P)"
verify_root="$(mktemp -d)"
cleanup() {
    rm -rf -- "$verify_root"
}
trap cleanup EXIT HUP INT TERM

expected_sdk="10.0.103"
locked_sdk="$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["sdk"]["version"])' "$repo_root/global.json")"
locked_roll_forward="$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["sdk"]["rollForward"])' "$repo_root/global.json")"
if [[ "$locked_sdk" != "$expected_sdk" || "$locked_roll_forward" != "disable" ]]; then
    printf '%s\n' \
        "ERROR: global.json must lock SDK ${expected_sdk} with rollForward=disable." >&2
    exit 1
fi
if ! selected_sdk="$(cd -- "$repo_root" && dotnet --version)"; then
    printf '%s\n' \
        "ERROR: exact repo-locked SDK ${expected_sdk} is unavailable; managed verification is required." >&2
    exit 1
fi
if [[ "$selected_sdk" != "$expected_sdk" ]]; then
    printf '%s\n' \
        "ERROR: selected SDK ${selected_sdk} does not equal repo-locked SDK ${expected_sdk}." >&2
    exit 1
fi

python3 -m pytest -q \
    "$repo_root/tests/test_build_ghost_cloudflare_access_edge.py" \
    "$repo_root/tests/test_build_ghost_private_nonprod_compose.py"

(
    cd -- "$repo_root"
    dotnet run \
        --project "ops/build-ghost-private-nonprod/cloudflare-access-edge.tests/Chummer.BuildGhost.CloudflareAccessEdge.Tests.csproj" \
        --configuration Release \
        --artifacts-path "$verify_root/artifacts"
)

git -C "$repo_root" diff --check
printf '%s\n' 'build_ghost_cloudflare_access_edge_verifier=pass'
