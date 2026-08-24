#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
repo_root="$(cd -- "$script_dir/../.." && pwd -P)"
verify_root="$(mktemp -d)"
cleanup() {
    rm -rf -- "$verify_root"
}
trap cleanup EXIT HUP INT TERM

python3 -m pytest -q \
    "$repo_root/tests/test_build_ghost_cloudflare_access_edge.py" \
    "$repo_root/tests/test_build_ghost_private_nonprod_compose.py"

(
    cd -- "$verify_root"
    dotnet run \
        --project "$script_dir/cloudflare-access-edge.tests/Chummer.BuildGhost.CloudflareAccessEdge.Tests.csproj" \
        --configuration Release \
        --artifacts-path "$verify_root/artifacts"
)

git -C "$repo_root" diff --check
printf '%s\n' 'build_ghost_cloudflare_access_edge_verifier=pass'
