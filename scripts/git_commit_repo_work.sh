#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -lt 1 ]; then
    echo "usage: bash scripts/git_commit_repo_work.sh <commit message>" >&2
    exit 64
fi

message="$1"

git add -A -- . \
    ':(exclude)Chummer/NLog.xsd' \
    ':(exclude)Chummer/data/priorities.xml' \
    ':(exclude)Chummer/data/priorities.xml.bak' \
    ':(exclude)docker-compose.override.yml'

if git diff --cached --quiet; then
    echo "no staged changes"
    exit 0
fi

git commit -m "$message"
