#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


RUN_SERVICES_ROOT = Path(__file__).resolve().parents[1]
FLEET_COMPLETION_ROOT = Path("/docker/chummercomplete/.integrated/fleet/_completion")
PUBLISHED_ROOT = RUN_SERVICES_ROOT / ".codex-studio" / "published"
OUTPUT_PATH = PUBLISHED_ROOT / "PROVIDER_PROOF_DISCOVERABILITY.generated.json"
MIRROR_ROOT = PUBLISHED_ROOT / "provider-proof-discoverability"


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")

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
        "magicfit_session": [
            FLEET_COMPLETION_ROOT / "magicfit_session" / "FINAL_GM_SESSION_VIDEO_FOUNDRY_VERDICT.md",
            FLEET_COMPLETION_ROOT / "magicfit_session" / "MAGICFIT_SESSION_PROVIDER_VERIFICATION.generated.json",
            FLEET_COMPLETION_ROOT / "magicfit_session" / "PROMPT_PREVIEW_APPROVAL_PROOF.generated.json",
            FLEET_COMPLETION_ROOT / "magicfit_session" / "GM_VIDEO_USAGE_METERING.generated.json",
        ],
    }


TRACKED_PROVIDER_RECEIPTS: dict[str, dict[str, Any]] = {
    "dadan": {
        "status": "tracked",
        "provider": "Dadan",
        "lane": "candidate video report workflow",
        "runtime_ready": False,
        "boundary": "Inventory only until provider verification and first workflow proof are captured.",
    },
    "rybbit": {
        "status": "tracked",
        "provider": "Rybbit",
        "lane": "bounded public analytics",
        "runtime_ready": True,
        "boundary": "Public-shell analytics only; event taxonomy and privacy posture must remain discoverable before expansion.",
    },
    "neuronwriter": {
        "status": "tracked",
        "provider": "NeuronWriter",
        "lane": "candidate SEO workflow",
        "runtime_ready": False,
        "boundary": "Inventory only until SEO workflow proof exists; not product, release, support, or truth authority.",
    },
    "joggai": {
        "status": "tracked",
        "provider": "JoggAI",
        "lane": "governed memorial video rendering",
        "runtime_ready": False,
        "boundary": "Off by default; likeness clips require avatar_consent before use.",
    },
    "poppy_ai": {
        "status": "tracked",
        "provider": "Poppy AI",
        "lane": "operator draft lane",
        "runtime_ready": False,
        "boundary": "Not a runtime adapter and not product, release, support, entitlement, prompt, sourcebook, private-user, or memorial-private truth.",
    },
    "fliplink": {
        "status": "tracked",
        "provider": "FlipLink.me",
        "lane": "candidate document portal",
        "runtime_ready": False,
        "boundary": "First-publication progress only; dashboard capacity, CNAME/API/embed/analytics/password, and expanded access-control proof remain gated.",
    },
    "unmixr": {
        "status": "tracked",
        "provider": "Unmixr AI",
        "lane": "bounded voice adapter",
        "runtime_ready": True,
        "boundary": "Private API key, voice id, Piper fallback, and voice roundtrip validation are proven locally; secrets remain outside git.",
    },
}


def write_tracked_provider_receipts() -> dict[str, Any]:
    rows: dict[str, Any] = {}
    for provider, receipt in TRACKED_PROVIDER_RECEIPTS.items():
        provider_root = MIRROR_ROOT / provider
        provider_root.mkdir(parents=True, exist_ok=True)
        receipt_path = provider_root / f"{provider.upper()}_TRACKED_PROVIDER_RECEIPT.generated.json"
        payload = {
            "contract_name": "chummer.provider.tracked_inventory_receipt",
            "generated_at_utc": now_iso(),
            **receipt,
            "claim_boundary": receipt["boundary"],
        }
        receipt_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        rows[provider] = {
            "status": "pass",
            "tracked_inventory_only": receipt["runtime_ready"] is False,
            "runtime_ready": receipt["runtime_ready"],
            "mirrored_paths": [str(receipt_path)],
            "missing_paths": [],
        }
    return rows


def main() -> int:
    argparse.ArgumentParser(description="Mirror discoverable provider proof artifacts into the repo-published proof shelf.").parse_known_args()

    subprocess.run(
        ["python3", "scripts/materialize_fleet_proof_discoverability_mirrors.py"],
        cwd=RUN_SERVICES_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

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
        if required_paths:
            for source in sorted(required_paths[0].parent.glob("*")):
                if source.is_file() and str(source) not in [str(path) for path in required_paths]:
                    target = provider_root / source.name
                    shutil.copyfile(source, target)
                    mirrored_paths.append(str(target))
        status = "pass" if not missing else "fail"
        if missing:
            failures.append(f"{provider} missing discoverable proof artifacts")
        providers[provider] = {
            "status": status,
            "required_paths": [str(path) for path in required_paths],
            "mirrored_paths": sorted(set(mirrored_paths)),
            "missing_paths": missing,
        }

    providers.update(write_tracked_provider_receipts())

    payload = {
        "contract_name": "chummer.provider_proof_discoverability",
        "generated_at_utc": now_iso(),
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
