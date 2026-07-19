#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
requested_python="${CHUMMER_RELEASE_PYTHON:-}"

for candidate in "$requested_python" python3.13 python3.12 python3.11 python3; do
  [[ -n "$candidate" ]] || continue
  command -v "$candidate" >/dev/null 2>&1 || continue
  if "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1; then
    exec "$candidate" "$script_dir/verify_public_projection.py" "$@"
  fi
done

echo "public projection requires Python 3.11 or newer; set CHUMMER_RELEASE_PYTHON to a reviewed interpreter" >&2
exit 2
