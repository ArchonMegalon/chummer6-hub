#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/_env.sh"

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT_DIR"

bash scripts/ai/build_r1_cleanroom.sh
bash scripts/ai/run_services_restore_drill.sh
bash scripts/ai/run_services_verification.sh
bash scripts/audit-ui-parity.sh

release_channel_path="$(
python3 - <<'PY'
import json
from pathlib import Path

receipt = Path("/docker/chummercomplete/chummer6-ui/.codex-studio/published/DESKTOP_WORKFLOW_EXECUTION_GATE.generated.json")
payload = json.loads(receipt.read_text(encoding="utf-8"))
evidence = payload.get("evidence") or {}
print(str(evidence.get("release_channel_path") or evidence.get("releaseChannelPath") or ""))
PY
)"
if [[ -z "$release_channel_path" || ! -f "$release_channel_path" ]]; then
  echo "verify gate failed: expected release channel receipt path from workflow gate evidence." >&2
  exit 1
fi

release_channel_backup="$(mktemp)"
cp "$release_channel_path" "$release_channel_backup"
python3 - "$release_channel_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
payload["releaseProof"]["proofRoutes"] = ["/home/%2e%2e/access"]
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject percent-encoded releaseProof.proofRoutes entries." >&2
  exit 1
fi
mv "$release_channel_backup" "$release_channel_path"

release_channel_backup="$(mktemp)"
cp "$release_channel_path" "$release_channel_backup"
python3 - "$release_channel_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
payload["releaseProof"]["proofRoutes"] = ["/home\\access"]
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject escaped-path releaseProof.proofRoutes entries." >&2
  exit 1
fi
mv "$release_channel_backup" "$release_channel_path"

bash scripts/ai/run_services_smoke.sh
