#!/usr/bin/env python3
"""Materialize the current external observability-proof intake request.

This script records the exact local bindings an externally produced operator
proof must satisfy.  It never configures monitoring, sends an alert, or creates
operator proof.
"""

from __future__ import annotations

import argparse
import importlib.util
import re
import secrets
import shlex
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
GATE_SCRIPT = ROOT / "scripts" / "verify_public_edge_observability_release.py"
DEFAULT_OUTPUT = (
    ROOT
    / ".codex-studio"
    / "published"
    / "PUBLIC_EDGE_OBSERVABILITY_OPERATOR_PROOF_INTAKE_REQUEST.generated.json"
)
REQUEST_CONTRACT = "chummer.public_edge_observability_operator_proof_intake_request.v2"
NONCE_RE = re.compile(r"^[0-9a-f]{64}$")


def _load_gate_module():
    spec = importlib.util.spec_from_file_location(
        "public_edge_observability_release_for_intake_request",
        GATE_SCRIPT,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("observability gate module could not be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _command(*parts: object) -> str:
    return " ".join(shlex.quote(str(part)) for part in parts)


def build_request(
    *,
    policy_path: Path,
    release_channel_path: Path,
    source_path: Path,
    canonical_proof_path: Path,
    request_output: Path,
    runtime_sources: dict[str, Path] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    gate = _load_gate_module()
    observed_at = (now or datetime.now(UTC)).astimezone(UTC)
    failures: list[str] = []

    policy, policy_error, policy_digest = gate.load_json_with_sha256(policy_path)
    if policy_error is not None or policy is None or policy_digest is None:
        failures.append(f"policy: current policy is {policy_error}")
    else:
        failures.extend(
            f"policy: {failure}" for failure in gate.validate_policy(policy)
        )

    release_candidate, _, _, release_failures = gate.release_candidate_binding(
        release_channel_path
    )
    failures.extend(
        f"release_candidate: {failure}" for failure in release_failures
    )

    runtime_checks, runtime_failures, runtime_binding = gate.inspect_runtime_sources(
        runtime_sources
    )
    failures.extend(runtime_failures)

    binding_material = {
        "policy_sha256": policy_digest,
        "release_candidate": {
            "sha256": release_candidate.get("sha256"),
            "version": release_candidate.get("version"),
            "channel": release_candidate.get("channel"),
        },
        "runtime_source_fingerprint_sha256": runtime_binding.get(
            "aggregate_sha256"
        ),
    }
    binding_sha256 = gate.canonical_sha256(binding_material)
    source_attestation_path = gate.detached_operator_attestation_path(source_path)
    canonical_attestation_path = gate.detached_operator_attestation_path(
        canonical_proof_path
    )

    existing, existing_error, _ = gate.load_json_with_sha256(request_output)
    if (
        existing_error is None
        and isinstance(existing, dict)
        and existing.get("contract_name") == REQUEST_CONTRACT
        and existing.get("status") == "ready"
        and NONCE_RE.fullmatch(str(existing.get("challenge_nonce") or ""))
        and isinstance(existing.get("current_bindings"), dict)
        and existing["current_bindings"].get("binding_sha256") == binding_sha256
        and isinstance(existing.get("intake"), dict)
        and existing["intake"].get("source_path") == str(source_path)
        and existing["intake"].get("canonical_proof_path")
        == str(canonical_proof_path)
        and existing["intake"].get("source_attestation_path")
        == str(source_attestation_path)
        and existing["intake"].get("canonical_attestation_path")
        == str(canonical_attestation_path)
    ):
        return existing

    challenge_nonce = secrets.token_hex(32)

    materialize_command = _command(
        "python3",
        "scripts/materialize_public_edge_observability_operator_proof_intake_request.py",
        "--policy",
        policy_path,
        "--release-channel",
        release_channel_path,
        "--source",
        source_path,
        "--canonical-proof",
        canonical_proof_path,
        "--output",
        request_output,
    )
    validate_command = _command(
        "python3",
        "scripts/import_public_edge_observability_operator_proof.py",
        "--source",
        source_path,
        "--policy",
        policy_path,
        "--release-channel",
        release_channel_path,
        "--canonical-proof",
        canonical_proof_path,
        "--attestation",
        source_attestation_path,
        "--canonical-attestation",
        canonical_attestation_path,
        "--intake-request",
        request_output,
    )
    import_command = f"{validate_command} --import-proof"
    verify_command = _command(
        "python3",
        "scripts/verify_public_edge_observability_release.py",
        "--policy",
        policy_path,
        "--operator-proof",
        canonical_proof_path,
        "--operator-attestation",
        canonical_attestation_path,
        "--intake-request",
        request_output,
        "--release-channel",
        release_channel_path,
        "--output",
        gate.DEFAULT_OUTPUT,
    )
    watch_command = _command(
        "python3",
        "scripts/watch_public_edge_observability_operator_proof.py",
        "--source",
        source_path,
        "--request",
        request_output,
        "--policy",
        policy_path,
        "--release-channel",
        release_channel_path,
        "--canonical-proof",
        canonical_proof_path,
        "--wait-seconds",
        900,
        "--poll-seconds",
        10,
    )

    ready = not failures
    return {
        "contract_name": REQUEST_CONTRACT,
        "status": "ready" if ready else "fail",
        "verdict": "INTAKE_REQUEST_READY" if ready else "INTAKE_REQUEST_BLOCKED",
        "generated_at_utc": gate.iso(observed_at),
        "challenge_nonce": challenge_nonce,
        "proof_origin": "external_operator_evidence",
        "required_proof_contract": gate.OPERATOR_PROOF_CONTRACT,
        "external_evidence_required": True,
        "proof_generated_by_repository": False,
        "sends_alerts": False,
        "configures_monitoring": False,
        "current_bindings": {
            "binding_algorithm": "sha256-canonical-json-v1",
            "binding_sha256": binding_sha256,
            "policy": {
                "path": str(policy_path),
                "sha256": policy_digest,
            },
            "release_candidate": release_candidate,
            "runtime_source_binding": runtime_binding,
        },
        "runtime_checks": runtime_checks,
        "intake": {
            "source_path": str(source_path),
            "canonical_proof_path": str(canonical_proof_path),
            "source_attestation_path": str(source_attestation_path),
            "canonical_attestation_path": str(canonical_attestation_path),
            "request_receipt_path": str(request_output),
            "validate_only_by_default": True,
            "import_requires_explicit_flag": True,
            "deterministic_source_only": True,
        },
        "required_proof_fields": {
            "top_level": sorted(gate.OPERATOR_PROOF_FIELDS),
            "nested": {
                key: sorted(value)
                for key, value in sorted(gate.OPERATOR_PROOF_NESTED_FIELDS.items())
            },
        },
        "required_attestation": {
            "contract_name": gate.OPERATOR_ATTESTATION_CONTRACT,
            "algorithm": "ed25519",
            "role": "observability_operator",
            "challenge_nonce": challenge_nonce,
            "subject_sha256_source": "exact intake.source_path bytes",
            "request_sha256_source": "exact intake.request_receipt_path bytes",
            "trusted_identity_count": len(gate.TRUSTED_OPERATOR_ATTESTERS),
        },
        "proof_requirements": [
            "Use the exact current_bindings values from this request.",
            "Obtain a real monitoring-backend binding for availability, latency, and readiness.",
            "Deliver a real test alert to the primary_on_call receiver class.",
            "Do not include credentials, receiver addresses, tokens, or message contents.",
            "Do not edit or restamp stale proof; produce new external evidence after any binding change.",
            "Sign a detached attestation over the exact proof bytes, this challenge_nonce, the exact request digest, and current_bindings with a code-pinned observability_operator identity.",
        ],
        "commands": {
            "refresh_request": materialize_command,
            "validate_only": validate_command,
            "import_after_review": import_command,
            "verify_after_import": verify_command,
            "watch_validate_only": watch_command,
            "watch_and_import_explicit": f"{watch_command} --import-proof",
        },
        "failure_count": len(failures),
        "failures": failures,
        "next_action": (
            "Have a governed live-ops process produce fresh external proof for these exact bindings, "
            "place it at intake.source_path, and run commands.validate_only."
            if ready
            else "Correct the local policy, release-candidate, or runtime binding failures before requesting external proof."
        ),
    }


def parse_args() -> argparse.Namespace:
    gate = _load_gate_module()
    parser = argparse.ArgumentParser(
        description=(
            "Materialize exact current bindings for external public-edge observability "
            "operator proof without creating proof or sending alerts."
        )
    )
    parser.add_argument("--policy", type=Path, default=gate.DEFAULT_POLICY)
    parser.add_argument(
        "--release-channel", type=Path, default=gate.DEFAULT_RELEASE_CHANNEL
    )
    parser.add_argument(
        "--source", type=Path, default=gate.DEFAULT_OPERATOR_PROOF_INTAKE_SOURCE
    )
    parser.add_argument(
        "--canonical-proof", type=Path, default=gate.DEFAULT_OPERATOR_PROOF
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = build_request(
        policy_path=args.policy,
        release_channel_path=args.release_channel,
        source_path=args.source,
        canonical_proof_path=args.canonical_proof,
        request_output=args.output,
    )
    gate = _load_gate_module()
    gate.atomic_write_json(args.output, payload)
    print(f"public_edge_observability_operator_proof_intake_request:{payload['status']}")
    return 0 if payload["status"] == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
