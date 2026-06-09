#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any


RUN_SERVICES_ROOT = Path(__file__).resolve().parents[1]
FLEET_COMPLETION_ROOT = Path("/docker/chummercomplete/.integrated/fleet/_completion")
PUBLISHED_ROOT = RUN_SERVICES_ROOT / ".codex-studio" / "published"
OUTPUT_PATH = PUBLISHED_ROOT / "PROVIDER_PROOF_DISCOVERABILITY.generated.json"
MIRROR_ROOT = PUBLISHED_ROOT / "provider-proof-discoverability"

def required_artifacts() -> dict[str, list[Path]]:
    return {
        "payfunnels": [
            FLEET_COMPLETION_ROOT / "payfunnels" / "FINAL_PAYFUNNELS_TEST_BILLING_ADAPTER_VERDICT.md",
            FLEET_COMPLETION_ROOT / "payfunnels" / "PAYFUNNELS_PROVIDER_VERIFICATION.generated.json",
        ],
        "prompt_architects": [
            FLEET_COMPLETION_ROOT / "prompt_architects" / "FINAL_PROMPT_ARCHITECTS_INTEGRATION_VERDICT.md",
            FLEET_COMPLETION_ROOT / "prompt_architects" / "PROMPT_ARCHITECTS_PROVIDER_VERIFICATION.generated.json",
        ],
        "magicfit": [
            FLEET_COMPLETION_ROOT / "magicfit" / "FINAL_MAGICFIT_PROVIDER_ADAPTER_VERDICT.md",
            FLEET_COMPLETION_ROOT / "magicfit" / "MAGICFIT_PROVIDER_VERIFICATION.generated.json",
        ],
        "table_pulse": [
            FLEET_COMPLETION_ROOT / "table_pulse" / "TABLE_PULSE_SCENARIO_REPLAY.generated.json",
        ],
        "black_ledger_media": [
            FLEET_COMPLETION_ROOT / "black_ledger" / "BLACK_LEDGER_LIVE_MEDIA_PROOF.generated.json",
        ],
    }


def main() -> int:
    argparse.ArgumentParser(description="Mirror discoverable provider proof artifacts into the repo-published proof shelf.").parse_known_args()

    MIRROR_ROOT.mkdir(parents=True, exist_ok=True)
    providers: dict[str, Any] = {}
    failures: list[str] = []

    for provider, required_paths in required_artifacts().items():
        mirrored_paths: list[str] = []
        missing: list[str] = []
        provider_root = MIRROR_ROOT / provider
        provider_root.mkdir(parents=True, exist_ok=True)
        for source in required_paths:
            if not source.is_file():
                missing.append(str(source))
                continue
            target = provider_root / source.name
            shutil.copyfile(source, target)
            mirrored_paths.append(str(target))
        status = "pass" if not missing else "fail"
        if missing:
            failures.append(f"{provider} missing discoverable proof artifacts")
        providers[provider] = {
            "status": status,
            "required_paths": [str(path) for path in required_paths],
            "mirrored_paths": mirrored_paths,
            "missing_paths": missing,
        }

    payload = {
        "contract_name": "chummer.provider_proof_discoverability",
        "status": "pass" if not failures else "fail",
        "providers": providers,
        "failures": failures,
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    if failures:
        raise SystemExit("provider proof discoverability failed")
    print("provider_proof_discoverability:ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
