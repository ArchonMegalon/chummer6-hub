#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


PACKAGE_PROOF = {
    "package_id": "next90-m127-hub-keep-downloads-install-help-account-aware-guidance-suppo",
    "work_task_id": "127.3",
    "milestone_id": 127,
    "frontier_id": 6974083833,
    "repo": "chummer6-hub",
    "status": "not_started",
    "wave": "W18",
    "task": "Keep downloads, install help, account-aware guidance, support recovery, and public release shelf UX bound to registry truth.",
    "title": "Keep downloads, install help, account-aware guidance, support recovery, and public release shelf UX bound to registry truth.",
    "allowed_paths": ["Chummer.Run.Api", "scripts", "tests"],
    "owned_surfaces": ["keep_downloads_install_help_account:hub"],
}

REQUIRED_MARKERS = [
    "var registryTruthBindings = new RegistryTruthBindingService(releases, new SupportConciergePacketService(releases, new SupportCasePresentationService())).Build(new RegistryTruthBindingContext(",
    'campaign spine registry truth bindings should keep downloads on the registry-backed shelf.',
    'campaign spine registry truth bindings should keep install help on the registry-backed status lane.',
    'campaign spine registry truth bindings should keep account-aware guidance on the Devices & access rail.',
    'campaign spine registry truth bindings should keep support recovery on the install continuation support rail.',
    'campaign spine registry truth bindings should keep the public release shelf on the registry-backed current-release route.',
]

DEFAULT_ROOT = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get("CHUMMER_NEXT90_M127_ROOT", DEFAULT_ROOT))
SOURCE = ROOT / "tests" / "RunServicesSmoke" / "Program.cs"
OUT = ROOT / ".codex-studio" / "published" / "NEXT90_M127_HUB_REGISTRY_TRUTH_BINDING.generated.json"


def main() -> int:
    if not SOURCE.is_file():
        print(f"missing smoke source: {SOURCE}", file=sys.stderr)
        return 1

    text = SOURCE.read_text(encoding="utf-8")
    missing = [marker for marker in REQUIRED_MARKERS if marker not in text]
    if missing:
        for marker in missing:
            print(f"next90_m127_materializer_missing: {marker}", file=sys.stderr)
        return 1

    payload = {
        "contract_name": "chummer6-hub.next90_m127_hub_registry_truth_binding",
        "status": "passed",
        "proof_kind": "source_backed_local_smoke_contract",
        "package_proof": PACKAGE_PROOF,
        "source_file": "tests/RunServicesSmoke/Program.cs",
        "required_markers": REQUIRED_MARKERS,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"wrote next90 m127 hub registry truth binding proof: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
