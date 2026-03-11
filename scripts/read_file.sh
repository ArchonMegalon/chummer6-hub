#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -lt 1 ]; then
    echo "usage: $0 <path> [start_line] [line_count]" >&2
    exit 64
fi

path="$1"
start_line="${2:-1}"
line_count="${3:-200}"

sed -n "${start_line},$((start_line + line_count - 1))p" "$path"
