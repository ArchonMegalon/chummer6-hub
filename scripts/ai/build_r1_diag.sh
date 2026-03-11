#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/_env.sh"
ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT_DIR"

dotnet msbuild Chummer.Run.sln /t:Restore /v:diag /nologo
