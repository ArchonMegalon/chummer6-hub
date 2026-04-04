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
payload["releaseProof"]["proofRoutes"] = ["/home/access#recap"]
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject query/fragment releaseProof.proofRoutes entries." >&2
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
payload["releaseProof"]["baseUrl"] = "https://example.com"
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject releaseProof.baseUrl outside allowed canonical release origins." >&2
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
payload["releaseProof"]["baseUrl"] = "https://Chummer.run/"
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject non-canonical releaseProof.baseUrl origin casing/trailing slash." >&2
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
payload["releaseProof"].pop("baseUrl", None)
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject missing releaseProof.baseUrl origin." >&2
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

release_channel_backup="$(mktemp)"
cp "$release_channel_path" "$release_channel_backup"
python3 - "$release_channel_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
payload["releaseProof"]["proofRoutes"] = ["/home/./access"]
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject dot-segment traversal releaseProof.proofRoutes entries." >&2
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
payload["releaseProof"]["proofRoutes"] = ["/home/access", "/home/access/"]
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject duplicate-normalized releaseProof.proofRoutes entries." >&2
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
payload["releaseProof"]["proofRoutes"] = ["/home/access"]
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject missing required releaseProof.proofRoutes flagship routes." >&2
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
payload["releaseProof"]["proofRoutes"] = [
    "/downloads/install/avalonia-linux-x64-installer",
    "/home/access",
    "/home/work",
    "/account/work",
    "/account/support",
    "/contact",
    "/home/bonus-noncanonical-route",
]
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject unexpected releaseProof.proofRoutes flagship routes." >&2
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
payload["releaseProof"]["journeysPassed"] = [
    "install_claim_restore_continue",
    "build_explain_publish",
    "campaign_session_recover_recap",
    "report_cluster_release_notify",
    "install_claim_restore_continue",
]
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject duplicate releaseProof.journeysPassed journey ids." >&2
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
payload["releaseProof"]["journeysPassed"] = ["launch-and-link"]
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject missing required releaseProof.journeysPassed baseline journey ids." >&2
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
payload["releaseProof"]["journeysPassed"] = [
    "launch-and-link",
    "create-and-advance-character",
    "run-and-log-session",
    "publish-and-install-content",
    "recover-and-resync",
    "bonus-noncanonical-journey",
]
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject unexpected releaseProof.journeysPassed journey ids." >&2
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
payload["releaseProof"]["journeysPassed"] = [
    "Launch-and-link",
    "create-and-advance-character",
    "run-and-log-session",
    "publish-and-install-content",
    "recover-and-resync",
]
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject non-canonical lowercase releaseProof.journeysPassed journey ids." >&2
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
payload["releaseProof"]["journeysPassed"] = [
    "launch and link",
    "create-and-advance-character",
    "run-and-log-session",
    "publish-and-install-content",
    "recover-and-resync",
]
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject non-canonical token shape in releaseProof.journeysPassed journey ids." >&2
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
payload["releaseProof"]["status"] = "failed"
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject non-passing releaseProof.status values." >&2
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
payload["releaseProof"]["generatedAt"] = "2000-01-01T00:00:00Z"
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject stale releaseProof.generatedAt timestamps." >&2
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
payload["releaseProof"]["generatedAt"] = "2099-01-01T00:00:00Z"
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject releaseProof.generatedAt timestamps with excessive future skew." >&2
  exit 1
fi
mv "$release_channel_backup" "$release_channel_path"

bash scripts/ai/run_services_smoke.sh
