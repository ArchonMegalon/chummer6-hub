#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -lt 1 ]; then
    echo "usage: $0 <pattern> [path...]" >&2
    exit 64
fi

pattern="$1"
shift || true

if [ "$#" -eq 0 ]; then
    rg -n --hidden --glob '!.git' -- "$pattern"
else
    rg -n --hidden --glob '!.git' -- "$pattern" "$@"
fi
