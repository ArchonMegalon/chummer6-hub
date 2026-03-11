#!/usr/bin/env bash
set -euo pipefail

usage() {
    cat <<'EOF'
Usage:
  bash scripts/repo_tool.sh show <path>
  bash scripts/repo_tool.sh show-range <path> <start-line> <end-line>
  bash scripts/repo_tool.sh search <pattern> [path...]
  bash scripts/repo_tool.sh files [pattern]
  bash scripts/repo_tool.sh status
EOF
}

if [ "$#" -lt 1 ]; then
    usage
    exit 1
fi

command="$1"
shift

case "$command" in
    show)
        if [ "$#" -ne 1 ]; then
            usage
            exit 1
        fi

        sed -n '1,240p' "$1"
        ;;
    show-range)
        if [ "$#" -ne 3 ]; then
            usage
            exit 1
        fi

        sed -n "$2,$3"p "$1"
        ;;
    search)
        if [ "$#" -lt 1 ]; then
            usage
            exit 1
        fi

        pattern="$1"
        shift
        if [ "$#" -eq 0 ]; then
            rg -n --hidden --glob '!.git' "$pattern"
        else
            rg -n --hidden --glob '!.git' "$pattern" "$@"
        fi
        ;;
    files)
        if [ "$#" -eq 0 ]; then
            rg --files
        else
            rg --files | rg "$1"
        fi
        ;;
    status)
        git status --short
        ;;
    *)
        usage
        exit 1
        ;;
esac
