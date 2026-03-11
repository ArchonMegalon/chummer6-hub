#!/usr/bin/env bash
set -euo pipefail

usage() {
    cat <<'EOF'
Usage:
  bash scripts/repo_inspect.sh files [path...]
  bash scripts/repo_inspect.sh search <pattern> [path...]
  bash scripts/repo_inspect.sh show <file> [start] [end]
  bash scripts/repo_inspect.sh tracked [path...]
  bash scripts/repo_inspect.sh status
EOF
}

command_name="${1:-}"
shift || true

case "${command_name}" in
    files)
        if [ "$#" -eq 0 ]; then
            rg --files
        else
            rg --files "$@"
        fi
        ;;
    search)
        pattern="${1:-}"
        if [ -z "${pattern}" ]; then
            usage
            exit 1
        fi
        shift || true
        if [ "$#" -eq 0 ]; then
            rg -n -- "${pattern}"
        else
            rg -n -- "${pattern}" "$@"
        fi
        ;;
    show)
        file="${1:-}"
        start="${2:-1}"
        end="${3:-200}"
        if [ -z "${file}" ]; then
            usage
            exit 1
        fi
        sed -n "${start},${end}p" "${file}"
        ;;
    tracked)
        if [ "$#" -eq 0 ]; then
            git ls-files
        else
            git ls-files -- "$@"
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
