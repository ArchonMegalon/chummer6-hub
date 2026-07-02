#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PUBLISHED_ROOT = ROOT / ".codex-studio" / "published"
DEFAULT_INPUT = PUBLISHED_ROOT / "FLAGSHIP_PRODUCT_READINESS.generated.json"
FALLBACK_INPUT = Path("/docker/fleet/.codex-studio/published/FLAGSHIP_PRODUCT_READINESS.generated.json")
DEFAULT_OUTPUT = PUBLISHED_ROOT / "FLAGSHIP_PRODUCT_READINESS_GATE.generated.json"
REQUIRED_READY_KEYS = {
    "desktop_client",
    "rules_engine_and_import",
    "hub_and_registry",
    "mobile_play_shell",
    "ui_kit_and_flagship_polish",
    "media_artifacts",
    "horizons_and_public_surface",
    "fleet_and_operator_loop",
}


def now_utc() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def now_iso() -> str:
    return now_utc().isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def parse_timestamp(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def generated_at(payload: dict[str, Any]) -> datetime | None:
    return parse_timestamp(payload.get("generated_at") or payload.get("generatedAt") or payload.get("generated_at_utc"))


def candidate_row(path: Path) -> dict[str, Any]:
    payload = load_json(path)
    generated = generated_at(payload)
    return {
        "path": str(path),
        "exists": path.is_file(),
        "status": payload.get("status"),
        "scoped_status": payload.get("scoped_status"),
        "generated_at_utc": generated.isoformat().replace("+00:00", "Z") if generated else "",
    }


def resolve_input(explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit
    candidates = [path for path in (DEFAULT_INPUT, FALLBACK_INPUT) if path.is_file()]
    if not candidates:
        return DEFAULT_INPUT
    return max(candidates, key=lambda path: generated_at(load_json(path)) or datetime.fromtimestamp(path.stat().st_mtime, UTC))


def build_payload(input_path: Path, max_age_hours: int) -> dict[str, Any]:
    payload = load_json(input_path)
    failures: list[str] = []
    generated = generated_at(payload)
    freshness_cutoff = now_utc() - timedelta(hours=max_age_hours)

    if not payload:
        failures.append(f"flagship readiness proof is missing or invalid: {input_path}")
    if str(payload.get("contract_name") or payload.get("contractName") or "").strip() != "fleet.flagship_product_readiness":
        failures.append("flagship readiness proof has the wrong contract")
    if str(payload.get("status") or "").strip().lower() != "pass":
        failures.append("flagship readiness proof status is not pass")
    if str(payload.get("scoped_status") or "").strip().lower() != "pass":
        failures.append("flagship readiness scoped_status is not pass")
    if generated is None:
        failures.append("flagship readiness proof does not publish a generated timestamp")
    elif generated < freshness_cutoff:
        failures.append(f"flagship readiness proof is stale: {generated.isoformat().replace('+00:00', 'Z')}")

    ready_keys = set(payload.get("ready_keys") if isinstance(payload.get("ready_keys"), list) else [])
    missing_ready_keys = sorted(REQUIRED_READY_KEYS - ready_keys)
    if missing_ready_keys:
        failures.append(f"flagship readiness proof is missing ready keys: {', '.join(missing_ready_keys)}")

    for key in ("completion_audit", "flagship_readiness_audit", "external_host_proof"):
        section = payload.get(key) if isinstance(payload.get(key), dict) else {}
        if str(section.get("status") or "").strip().lower() != "pass":
            failures.append(f"flagship readiness {key} is not pass")

    return {
        "contract_name": "chummer.flagship_product_readiness_gate.v1",
        "generated_at_utc": now_iso(),
        "status": "pass" if not failures else "fail",
        "input_path": str(input_path),
        "max_age_hours": max_age_hours,
        "source_candidates": [candidate_row(path) for path in (DEFAULT_INPUT, FALLBACK_INPUT)],
        "readiness": {
            "contract_name": payload.get("contract_name") or payload.get("contractName"),
            "status": payload.get("status"),
            "scoped_status": payload.get("scoped_status"),
            "generated_at_utc": generated.isoformat().replace("+00:00", "Z") if generated else "",
            "ready_keys": sorted(ready_keys),
            "completion_audit_status": (payload.get("completion_audit") or {}).get("status")
            if isinstance(payload.get("completion_audit"), dict)
            else None,
            "flagship_readiness_audit_status": (payload.get("flagship_readiness_audit") or {}).get("status")
            if isinstance(payload.get("flagship_readiness_audit"), dict)
            else None,
            "external_host_proof_status": (payload.get("external_host_proof") or {}).get("status")
            if isinstance(payload.get("external_host_proof"), dict)
            else None,
        },
        "failures": failures,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify the fleet flagship product readiness proof used by release gates.")
    parser.add_argument("--input", type=Path, default=None, help="Explicit FLAGSHIP_PRODUCT_READINESS.generated.json path.")
    parser.add_argument("--summary-output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--max-age-hours", type=int, default=int(os.environ.get("CHUMMER_FLAGSHIP_READINESS_MAX_AGE_HOURS", "168")))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = resolve_input(args.input)
    payload = build_payload(input_path, args.max_age_hours)
    args.summary_output.parent.mkdir(parents=True, exist_ok=True)
    args.summary_output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"flagship_product_readiness_gate:{payload['status']}")
    return 0 if payload["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
