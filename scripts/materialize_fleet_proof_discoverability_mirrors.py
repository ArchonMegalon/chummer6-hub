#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shutil
from json import JSONDecodeError
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
RUN_SERVICES_PUBLISHED_ROOT = Path(
    os.environ.get(
        "CHUMMER_RUN_SERVICES_PUBLISHED_ROOT",
        str(REPO_ROOT / ".codex-studio" / "published"),
    )
)
FLEET_COMPLETION_ROOT = Path(
    os.environ.get(
        "CHUMMER_FLEET_COMPLETION_ROOT",
        "/docker/chummercomplete/.integrated/fleet/_completion",
    )
)
MAGICFIT_PROVIDER_ROOT = Path(
    os.environ.get(
        "CHUMMER_MAGICFIT_PROVIDER_ROOT",
        "/docker/chummercomplete/_completion/magicfit_provider",
    )
)
LEGACY_REAUDIT_ROOT = Path(
    os.environ.get(
        "CHUMMER_LEGACY_REAUDIT_ROOT",
        "/docker/chummercomplete/_completion/full_product_reaudit_v19",
    )
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except JSONDecodeError as exc:
        raise ValueError(f"invalid json at {path}: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"expected object json at {path}")
    return payload


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def copy_if_present(source: Path, target: Path) -> bool:
    if not source.is_file():
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    return True


def is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def materialize_magicfit() -> dict[str, Any]:
    target_root = FLEET_COMPLETION_ROOT / "magicfit"
    target_root.mkdir(parents=True, exist_ok=True)
    sources = [
        MAGICFIT_PROVIDER_ROOT / "FINAL_MAGICFIT_PROVIDER_ADAPTER_VERDICT.md",
        MAGICFIT_PROVIDER_ROOT / "MAGICFIT_PROVIDER_VERIFICATION.generated.json",
    ]
    copied: list[str] = []
    missing: list[str] = []
    for source in sources:
        target = target_root / source.name
        if copy_if_present(source, target):
            copied.append(str(target))
        else:
            missing.append(str(source))
    return {
        "status": "pass" if not missing else "fail",
        "copied_paths": copied,
        "missing_paths": missing,
    }


def materialize_black_ledger() -> dict[str, Any]:
    source_receipt = RUN_SERVICES_PUBLISHED_ROOT / "BLACK_LEDGER_LIVE_MEDIA_PROOF.generated.json"
    target_root = FLEET_COMPLETION_ROOT / "black_ledger"
    target_root.mkdir(parents=True, exist_ok=True)
    if not source_receipt.is_file():
        return {
            "status": "fail",
            "copied_paths": [],
            "missing_paths": [str(source_receipt)],
        }

    source_payload = load_json(source_receipt)
    copied: list[str] = []
    missing: list[str] = []
    target_receipt = target_root / source_receipt.name
    shutil.copyfile(source_receipt, target_receipt)
    copied.append(str(target_receipt))

    screenshots: list[dict[str, str]] = []
    for index, shot in enumerate(source_payload.get("screenshots", [])):
        source_path_raw = str(shot.get("screenshotPath", "")).strip()
        if not source_path_raw:
            missing.append(f"screenshots[{index}].screenshotPath")
            continue
        source_path = Path(source_path_raw)
        if not source_path.is_file():
            missing.append(str(source_path))
            continue
        if not is_relative_to(source_path, RUN_SERVICES_PUBLISHED_ROOT):
            missing.append(f"outside_published_root:{source_path}")
            continue
        relative_dir = Path(shot.get("viewport", "unknown"))
        target_path = target_root / "live_media" / relative_dir / source_path.name
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_path, target_path)
        copied.append(str(target_path))
        screenshots.append(
            {
                "route": str(shot.get("route", "")),
                "viewport": str(shot.get("viewport", "")),
                "screenshotPath": str(target_path),
            }
        )

    mirrored_payload = dict(source_payload)
    mirrored_payload["mirrored_from"] = str(source_receipt)
    if screenshots:
        mirrored_payload["screenshots"] = screenshots
    write_json(target_receipt, mirrored_payload)
    return {
        "status": "pass"
        if source_payload.get("status") == "pass" and not missing
        else "fail",
        "copied_paths": copied,
        "missing_paths": missing,
    }


def materialize_table_pulse() -> dict[str, Any]:
    target_root = FLEET_COMPLETION_ROOT / "table_pulse"
    target_root.mkdir(parents=True, exist_ok=True)
    live_source = RUN_SERVICES_PUBLISHED_ROOT / "PWA_TABLE_PULSE_SCENARIO_RECEIPTS.generated.json"
    legacy_source = LEGACY_REAUDIT_ROOT / "TABLE_PULSE_SCENARIO_REPLAY.generated.json"
    target_receipt = target_root / "TABLE_PULSE_SCENARIO_REPLAY.generated.json"

    missing = [str(path) for path in (live_source, legacy_source) if not path.is_file()]
    if not live_source.is_file():
        return {
            "status": "fail",
            "copied_paths": [],
            "missing_paths": missing,
        }

    live_payload = load_json(live_source)
    legacy_payload = load_json(legacy_source) if legacy_source.is_file() else {}

    covered_steps = dict(legacy_payload.get("covered_steps") or {})
    required_steps = list(legacy_payload.get("required_steps") or [])
    scenario_ids = {scenario.get("id"): scenario.get("result") for scenario in live_payload.get("scenarios", [])}
    if not legacy_source.is_file():
        covered_steps = {
            "opt-in-policy": scenario_ids.get("table_pulse_remote_reaction_gm_adjudication") == "pass",
            "remote-notification": scenario_ids.get("pwa_subscription_delivery_click") == "pass",
            "remote-choice": scenario_ids.get("table_pulse_remote_reaction_gm_adjudication") == "pass",
            "gm-adjudication": scenario_ids.get("table_pulse_remote_reaction_gm_adjudication") == "pass",
            "state-update": scenario_ids.get("table_pulse_remote_reaction_gm_adjudication") == "pass",
            "receipt": scenario_ids.get("table_pulse_remote_reaction_gm_adjudication") == "pass",
        }
        required_steps = list(covered_steps.keys())

    status = "pass"
    failures: list[str] = []
    if live_payload.get("status") != "pass":
        status = "fail"
        failures.append("live scenario receipt is not pass")
    if legacy_source.is_file():
        if not required_steps:
            status = "fail"
            failures.append("legacy replay receipt is missing required_steps")
        if not covered_steps:
            status = "fail"
            failures.append("legacy replay receipt is missing covered_steps")
    for step in required_steps:
        if not covered_steps.get(step):
            status = "fail"
            failures.append(f"required step {step} is not covered")

    payload = {
        "contract_name": "fleet.table_pulse_scenario_replay",
        "generated_at_utc": utc_now(),
        "status": status,
        "required_steps": required_steps,
        "covered_steps": covered_steps,
        "source_receipts": {
            "live_scenario_receipts": str(live_source),
            "legacy_reaudit_receipt": str(legacy_source) if legacy_source.is_file() else "",
        },
        "scenarios": live_payload.get("scenarios", []),
        "private_campaign_data_captured": live_payload.get("private_campaign_data_captured"),
        "failures": failures,
    }
    write_json(target_receipt, payload)
    return {
        "status": status,
        "copied_paths": [str(target_receipt)],
        "missing_paths": missing,
    }


def main() -> int:
    magicfit = materialize_magicfit()
    black_ledger = materialize_black_ledger()
    table_pulse = materialize_table_pulse()
    summary = {
        "generated_at_utc": utc_now(),
        "status": "pass"
        if all(item["status"] == "pass" for item in (magicfit, black_ledger, table_pulse))
        else "fail",
        "mirrors": {
            "magicfit": magicfit,
            "black_ledger": black_ledger,
            "table_pulse": table_pulse,
        },
    }
    write_json(FLEET_COMPLETION_ROOT / "DISCOVERABILITY_MIRROR_SUMMARY.generated.json", summary)
    if summary["status"] != "pass":
        raise SystemExit("fleet proof discoverability mirror materialization failed")
    print("fleet_proof_discoverability_mirrors:ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
