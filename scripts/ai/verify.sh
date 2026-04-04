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
payload["releaseProof"].pop("baseUrl", None)
payload["releaseProof"]["base_url"] = "ftp://chummer.run"
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject non-http(s) releaseProof.base_url alias schemes." >&2
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
payload["releaseProof"].pop("baseUrl", None)
payload["releaseProof"]["base_url"] = "https://chummer.run/home?preview=1"
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject non-origin releaseProof.base_url alias path/query segments." >&2
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
payload["releaseProof"].pop("baseUrl", None)
payload["releaseProof"]["base_url"] = "https://operator@chummer.run"
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject userinfo credentials in releaseProof.base_url alias origins." >&2
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
payload["releaseProof"]["baseUrl"] = "https://chummer.run"
payload["releaseProof"]["base_url"] = "https://chummer.test"
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject conflicting alias values between releaseProof.baseUrl and releaseProof.base_url." >&2
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
]
payload["releaseProof"]["proof_routes"] = ["/home/access"]
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject conflicting alias values between releaseProof.proofRoutes and releaseProof.proof_routes." >&2
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
payload["releaseProof"].pop("proofRoutes", None)
payload["releaseProof"]["proof_routes"] = [" /home/access "]
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject whitespace-padded releaseProof.proof_routes entries." >&2
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
]
payload["releaseProof"]["journeys_passed"] = ["install_claim_restore_continue"]
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject conflicting alias values between releaseProof.journeysPassed and releaseProof.journeys_passed." >&2
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
payload["releaseProof"].pop("journeysPassed", None)
payload["releaseProof"]["journeys_passed"] = ["launch and link"]
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject non-canonical token shape in releaseProof.journeys_passed journey ids." >&2
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
payload["releaseProof"]["baseUrl"] = "ftp://chummer.run"
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject non-http(s) releaseProof.baseUrl schemes." >&2
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
payload["releaseProof"]["baseUrl"] = "https://chummer.run/home?preview=1"
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject non-origin releaseProof.baseUrl path/query segments." >&2
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
payload["releaseProof"]["baseUrl"] = "https://"
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject hostless releaseProof.baseUrl origins." >&2
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
payload["releaseProof"]["base_url"] = "https://"
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject hostless releaseProof.base_url alias origins." >&2
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
payload["releaseProof"]["baseUrl"] = "https://operator@chummer.run"
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject userinfo credentials in releaseProof.baseUrl origins." >&2
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
payload["releaseProof"]["baseUrl"] = " https://chummer.run"
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject whitespace-padded releaseProof.baseUrl values." >&2
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
payload["releaseProof"]["base_url"] = " https://chummer.run"
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject whitespace-padded releaseProof.base_url alias values." >&2
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
payload["releaseProof"]["proofRoutes"] = [" /home/access"]
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject whitespace-padded releaseProof.proofRoutes entries." >&2
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
payload["releaseProof"]["proofRoutes"] = ["home/access"]
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject non-slash-led releaseProof.proofRoutes entries." >&2
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
payload["releaseProof"]["proofRoutes"] = ["/Home/access"]
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject non-canonical uppercase releaseProof.proofRoutes entries." >&2
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
payload["releaseProof"]["proofRoutes"] = ["/home//access"]
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject empty-segment releaseProof.proofRoutes entries." >&2
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
    "install_claim_restore_continue",
    "build_explain_publish",
    "campaign_session_recover_recap",
    "report_cluster_release_notify",
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
payload["releaseProof"]["uiLocalizationReleaseGate"] = "pass"
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject non-object releaseProof.uiLocalizationReleaseGate payloads." >&2
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
payload["releaseProof"]["uiLocalizationReleaseGate"]["status"] = "failed"
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject non-passing releaseProof.uiLocalizationReleaseGate.status values." >&2
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
payload["releaseProof"]["uiLocalizationReleaseGate"].pop("generatedAt", None)
payload["releaseProof"]["uiLocalizationReleaseGate"].pop("generated_at", None)
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject missing releaseProof.uiLocalizationReleaseGate.generatedAt timestamps." >&2
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
payload["releaseProof"]["uiLocalizationReleaseGate"]["generatedAt"] = "not-an-iso-timestamp"
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject invalid-format releaseProof.uiLocalizationReleaseGate.generatedAt timestamps." >&2
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
payload["releaseProof"]["uiLocalizationReleaseGate"].pop("generatedAt", None)
payload["releaseProof"]["uiLocalizationReleaseGate"]["generated_at"] = "not-an-iso-timestamp"
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject invalid-format releaseProof.uiLocalizationReleaseGate.generated_at timestamps." >&2
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
payload["releaseProof"]["uiLocalizationReleaseGate"]["generatedAt"] = "2000-01-01T00:00:00Z"
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject stale releaseProof.uiLocalizationReleaseGate.generatedAt timestamps." >&2
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
payload["releaseProof"]["uiLocalizationReleaseGate"].pop("generatedAt", None)
payload["releaseProof"]["uiLocalizationReleaseGate"]["generated_at"] = "2000-01-01T00:00:00Z"
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject stale releaseProof.uiLocalizationReleaseGate.generated_at timestamps." >&2
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
payload["releaseProof"]["uiLocalizationReleaseGate"]["generatedAt"] = "2026-01-01T00:00:00Z"
payload["releaseProof"]["uiLocalizationReleaseGate"]["generated_at"] = "2026-01-01T00:05:00Z"
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject conflicting alias values between releaseProof.uiLocalizationReleaseGate.generatedAt and releaseProof.uiLocalizationReleaseGate.generated_at." >&2
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
payload["releaseProof"]["uiLocalizationReleaseGate"].pop("generatedAt", None)
payload["releaseProof"]["uiLocalizationReleaseGate"]["generated_at"] = "2099-01-01T00:00:00Z"
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject releaseProof.uiLocalizationReleaseGate.generated_at timestamps with excessive future skew." >&2
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
payload["releaseProof"]["uiLocalizationReleaseGate"]["generatedAt"] = "2099-01-01T00:00:00Z"
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject releaseProof.uiLocalizationReleaseGate.generatedAt timestamps with excessive future skew." >&2
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
payload["releaseProof"].pop("uiLocalizationReleaseGate", None)
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject missing releaseProof.uiLocalizationReleaseGate payloads." >&2
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
gate = payload["releaseProof"]["uiLocalizationReleaseGate"]
gate["defaultKeyCount"] = 383
gate["default_key_count"] = 384
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject conflicting alias values between releaseProof.uiLocalizationReleaseGate.defaultKeyCount and releaseProof.uiLocalizationReleaseGate.default_key_count." >&2
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
payload["releaseProof"]["uiLocalizationReleaseGate"]["explicitFallbackRuntime"] = "failed"
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject non-passing releaseProof.uiLocalizationReleaseGate.explicitFallbackRuntime status." >&2
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
gate = payload["releaseProof"]["uiLocalizationReleaseGate"]
gate["translationBacklogFindingsCount"] = 1
gate["translationBacklogFindings"] = []
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject releaseProof.uiLocalizationReleaseGate.translationBacklogFindings length/count mismatches." >&2
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
for row in payload["releaseProof"]["uiLocalizationReleaseGate"]["localeSummary"]:
    if isinstance(row, dict) and row.get("locale") == "de-de":
        row["untranslatedKeyCount"] = 1
        break
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject non-zero releaseProof.uiLocalizationReleaseGate.localeSummary untranslatedKeyCount values." >&2
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
payload.pop("releaseProof", None)
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject missing releaseProof payloads." >&2
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
payload["releaseProof"]["journeysPassed"] = "install_claim_restore_continue"
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject non-array releaseProof.journeysPassed payloads." >&2
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
payload["releaseProof"]["proofRoutes"] = "/home/access"
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject non-array releaseProof.proofRoutes payloads." >&2
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
    " install_claim_restore_continue",
    "build_explain_publish",
    "campaign_session_recover_recap",
    "report_cluster_release_notify",
]
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject whitespace-padded releaseProof.journeysPassed journey ids." >&2
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
    42,
    "campaign_session_recover_recap",
    "report_cluster_release_notify",
]
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject non-string releaseProof.journeysPassed entries." >&2
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
    "",
    "build_explain_publish",
    "campaign_session_recover_recap",
    "report_cluster_release_notify",
]
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject blank releaseProof.journeysPassed journey ids." >&2
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
payload["releaseProof"]["proofRoutes"] = ["/home/access", 42]
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject non-string releaseProof.proofRoutes entries." >&2
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
payload["releaseProof"].pop("generatedAt", None)
payload["releaseProof"]["generated_at"] = "2000-01-01T00:00:00Z"
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject stale releaseProof.generated_at timestamps." >&2
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
payload["releaseProof"]["generatedAt"] = "2026-01-01T00:00:00Z"
payload["releaseProof"]["generated_at"] = "2026-01-01T00:05:00Z"
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject conflicting alias values between releaseProof.generatedAt and releaseProof.generated_at." >&2
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
payload["releaseProof"].pop("generatedAt", None)
payload["releaseProof"].pop("generated_at", None)
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject missing releaseProof.generatedAt timestamps." >&2
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
payload["releaseProof"]["generatedAt"] = "not-an-iso-timestamp"
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject invalid-format releaseProof.generatedAt timestamps." >&2
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
payload["releaseProof"].pop("generatedAt", None)
payload["releaseProof"]["generated_at"] = "not-an-iso-timestamp"
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject invalid-format releaseProof.generated_at timestamps." >&2
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
payload["releaseProof"].pop("generatedAt", None)
payload["releaseProof"]["generated_at"] = "2099-01-01T00:00:00Z"
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
if bash scripts/audit-ui-parity.sh; then
  mv "$release_channel_backup" "$release_channel_path"
  echo "verify gate failed: parity audit should reject releaseProof.generated_at timestamps with excessive future skew." >&2
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
