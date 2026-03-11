#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 2 ]; then
    echo "usage: $0 <file> <variable_name>" >&2
    echo "requires VALUE environment variable" >&2
    exit 64
fi

file="$1"
variable_name="$2"

: "${VALUE:?VALUE is required}"

tmp_file="$(mktemp)"
trap 'rm -f "$tmp_file"' EXIT

if [ -f "$file" ]; then
    found=0
    while IFS= read -r line || [ -n "$line" ]; do
        if [[ "$line" == "${variable_name}="* ]]; then
            printf '%s=%s\n' "$variable_name" "$VALUE" >> "$tmp_file"
            found=1
        else
            printf '%s\n' "$line" >> "$tmp_file"
        fi
    done < "$file"

    if [ "$found" -eq 0 ]; then
        printf '%s=%s\n' "$variable_name" "$VALUE" >> "$tmp_file"
    fi
else
    printf '%s=%s\n' "$variable_name" "$VALUE" > "$tmp_file"
fi

mv "$tmp_file" "$file"
