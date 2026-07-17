#!/usr/bin/env python3
"""Validate and atomically import externally produced observability proof.

This command never configures monitoring, sends an alert, or creates operator
evidence.  It only accepts proof bytes that already satisfy the current release
gate and copies those exact bytes to the canonical proof path.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
GATE_SCRIPT = ROOT / "scripts" / "verify_public_edge_observability_release.py"
DEFAULT_INTAKE_RECEIPT = (
    ROOT
    / ".codex-studio"
    / "published"
    / "PUBLIC_EDGE_OBSERVABILITY_OPERATOR_PROOF_INTAKE.generated.json"
)
INTAKE_CONTRACT = "chummer.public_edge_observability_operator_proof_intake.v2"
DEFAULT_SOURCE = (
    ROOT
    / ".state"
    / "incoming_public_edge_observability_operator_proof"
    / "PUBLIC_EDGE_OBSERVABILITY_OPERATOR_PROOF.generated.json"
)


def _load_gate_module():
    spec = importlib.util.spec_from_file_location(
        "public_edge_observability_release_for_intake",
        GATE_SCRIPT,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("observability gate module could not be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _same_path(left: Path, right: Path) -> bool:
    try:
        return left.resolve(strict=False) == right.resolve(strict=False)
    except OSError:
        return os.path.abspath(left) == os.path.abspath(right)


def _atomic_write_exact_bytes(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise OSError("canonical destination is a symlink")

    expected_digest = hashlib.sha256(raw).hexdigest()
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        if hashlib.sha256(Path(temporary_name).read_bytes()).hexdigest() != expected_digest:
            raise OSError("temporary proof digest mismatch")
        os.replace(temporary_name, path)
        directory_fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def process_intake(
    *,
    source_path: Path,
    import_proof: bool,
    destination_path: Path | None = None,
    attestation_path: Path | None = None,
    destination_attestation_path: Path | None = None,
    intake_request_path: Path | None = None,
    policy_path: Path | None = None,
    release_channel_path: Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    gate = _load_gate_module()
    observed_at = (now or datetime.now(UTC)).astimezone(UTC)
    destination = destination_path or gate.DEFAULT_OPERATOR_PROOF
    source_attestation = attestation_path or gate.detached_operator_attestation_path(
        source_path
    )
    destination_attestation = (
        destination_attestation_path
        or gate.detached_operator_attestation_path(destination)
    )
    request_source = intake_request_path or gate.DEFAULT_INTAKE_REQUEST
    policy_source = policy_path or gate.DEFAULT_POLICY
    release_channel_source = release_channel_path or gate.DEFAULT_RELEASE_CHANNEL
    failures: list[str] = []

    raw: bytes | None = None
    source_error: str | None = None
    source_digest: str | None = None
    proof: dict[str, Any] | None = None
    attestation_raw: bytes | None = None
    attestation_error: str | None = None
    attestation_digest: str | None = None
    attestation: dict[str, Any] | None = None

    if _same_path(source_path, destination):
        source_error = "canonical_path_is_not_an_intake_source"
        failures.append(
            "source: canonical proof cannot be used as its own intake source"
        )
    else:
        raw, source_error = gate.read_regular_file_bytes(source_path)
        if source_error is not None or raw is None:
            failures.append(f"source: operator proof is {source_error}")
        else:
            source_digest = hashlib.sha256(raw).hexdigest()
            try:
                decoded = json.loads(raw)
            except (UnicodeDecodeError, json.JSONDecodeError):
                source_error = "invalid_json"
                failures.append("source: operator proof is invalid_json")
            else:
                if not isinstance(decoded, dict):
                    source_error = "not_an_object"
                    failures.append("source: operator proof is not_an_object")
                else:
                    proof = decoded

    if _same_path(source_attestation, destination_attestation):
        attestation_error = "canonical_path_is_not_an_intake_source"
        failures.append(
            "attestation: canonical attestation cannot be used as its own intake source"
        )
    else:
        attestation_raw, attestation_error = gate.read_regular_file_bytes(
            source_attestation
        )
        if attestation_error is not None or attestation_raw is None:
            failures.append(
                f"attestation: detached attestation is {attestation_error}"
            )
        else:
            attestation_digest = hashlib.sha256(attestation_raw).hexdigest()
            try:
                decoded_attestation = json.loads(attestation_raw)
            except (UnicodeDecodeError, json.JSONDecodeError):
                attestation_error = "invalid_json"
                failures.append("attestation: detached attestation is invalid_json")
            else:
                if not isinstance(decoded_attestation, dict):
                    attestation_error = "not_an_object"
                    failures.append("attestation: detached attestation is not_an_object")
                else:
                    attestation = decoded_attestation

    policy, policy_error, policy_digest = gate.load_json_with_sha256(policy_source)
    if policy_error is not None or policy is None or policy_digest is None:
        failures.append(f"policy: current policy is {policy_error}")
    else:
        failures.extend(f"policy: {failure}" for failure in gate.validate_policy(policy))

    release_candidate, _, _, release_failures = gate.release_candidate_binding(
        release_channel_source
    )
    failures.extend(f"release_candidate: {failure}" for failure in release_failures)

    runtime_checks, runtime_failures, runtime_binding = gate.inspect_runtime_sources()
    failures.extend(runtime_failures)

    expected_bindings = gate.operator_attestation_bindings(
        policy_sha256=policy_digest or "",
        release_candidate=release_candidate,
        runtime_binding=runtime_binding,
    )
    request, request_error, request_digest, _ = gate.load_json_snapshot(
        request_source
    )
    request_failures: list[str] = []
    if request_error is not None or request is None or request_digest is None:
        request_failures.append(f"intake request is {request_error}")
    else:
        request_failures.extend(
            gate.validate_intake_request(
                request,
                expected_bindings=expected_bindings,
            )
        )
    failures.extend(f"intake_request: {failure}" for failure in request_failures)

    if (
        proof is not None
        and policy is not None
        and policy_digest is not None
        and not release_failures
        and not runtime_failures
    ):
        failures.extend(
            f"operator_proof: {failure}"
            for failure in gate.validate_operator_proof(
                proof,
                policy=policy,
                policy_digest=policy_digest,
                release_candidate=release_candidate,
                runtime_binding=runtime_binding,
                now=observed_at,
            )
        )

    attestation_summary: dict[str, Any] = {
        "contract_name": None,
        "status": "fail",
        "key_id": None,
    }
    if (
        attestation is not None
        and raw is not None
        and request is not None
        and request_digest is not None
        and not request_failures
    ):
        attestation_summary, authority_failures = gate.validate_operator_attestation(
            attestation,
            proof_bytes=raw,
            request=request,
            request_sha256=request_digest,
            expected_bindings=expected_bindings,
            now=observed_at,
        )
        failures.extend(
            f"attestation: {failure}" for failure in authority_failures
        )

    imported = False
    destination_digest: str | None = None
    destination_attestation_digest: str | None = None
    if not failures and import_proof:
        assert raw is not None
        assert attestation_raw is not None
        try:
            # Install authority first and proof last.  The proof replace is the commit
            # marker; any interruption leaves a mismatched pair that fails closed.
            _atomic_write_exact_bytes(destination_attestation, attestation_raw)
            _atomic_write_exact_bytes(destination, raw)
            imported_raw, destination_error = gate.read_regular_file_bytes(destination)
            imported_attestation_raw, destination_attestation_error = (
                gate.read_regular_file_bytes(destination_attestation)
            )
            if destination_error is not None or imported_raw is None:
                failures.append(
                    f"destination: imported proof could not be verified ({destination_error})"
                )
            elif (
                destination_attestation_error is not None
                or imported_attestation_raw is None
            ):
                failures.append(
                    "destination: imported attestation could not be verified "
                    f"({destination_attestation_error})"
                )
            else:
                destination_digest = hashlib.sha256(imported_raw).hexdigest()
                destination_attestation_digest = hashlib.sha256(
                    imported_attestation_raw
                ).hexdigest()
                if destination_digest != source_digest:
                    failures.append("destination: imported proof digest mismatch")
                elif destination_attestation_digest != attestation_digest:
                    failures.append("destination: imported attestation digest mismatch")
                else:
                    imported = True
        except OSError as exc:
            failures.append(f"destination: atomic import failed ({type(exc).__name__})")

    if failures:
        status = "fail"
        verdict = "OPERATOR_PROOF_REJECTED"
        next_action = (
            "Obtain new external proof for the current bindings or correct the intake path; "
            "do not edit or restamp evidence to clear these failures."
        )
    elif import_proof:
        status = "pass"
        verdict = "OPERATOR_PROOF_IMPORTED"
        next_action = "Regenerate the public-edge observability release gate."
    else:
        status = "ready"
        verdict = "OPERATOR_PROOF_VALIDATED_NOT_IMPORTED"
        next_action = "Rerun with --import-proof to atomically install these exact proof bytes."

    return {
        "contract_name": INTAKE_CONTRACT,
        "status": status,
        "verdict": verdict,
        "generated_at_utc": gate.iso(observed_at),
        "mode": "import" if import_proof else "validate_only",
        "source": {
            "name": source_path.name,
            "load_status": source_error or "loaded",
            "sha256": source_digest,
            "attestation": {
                "name": source_attestation.name,
                "load_status": attestation_error or "loaded",
                "sha256": attestation_digest,
                **attestation_summary,
            },
        },
        "destination": {
            "path": str(destination),
            "imported": imported,
            "sha256": destination_digest,
            "attestation_path": str(destination_attestation),
            "attestation_sha256": destination_attestation_digest,
        },
        "intake_request": {
            "path": str(request_source),
            "load_status": request_error or "loaded",
            "sha256": request_digest,
            "challenge_nonce": (
                request.get("challenge_nonce") if request is not None else None
            ),
        },
        "current_bindings": {
            "policy_sha256": policy_digest,
            "release_candidate": {
                "sha256": release_candidate.get("sha256"),
                "version": release_candidate.get("version"),
                "channel": release_candidate.get("channel"),
            },
            "runtime_source_fingerprint_sha256": runtime_binding.get(
                "aggregate_sha256"
            ),
        },
        "runtime_checks": runtime_checks,
        "proof_origin": "external_operator_evidence",
        "external_evidence_pending": not imported,
        "sends_alerts": False,
        "configures_monitoring": False,
        "failure_count": len(failures),
        "failures": failures,
        "next_action": next_action,
    }


def parse_args() -> argparse.Namespace:
    gate = _load_gate_module()
    parser = argparse.ArgumentParser(
        description=(
            "Validate and optionally import externally produced public-edge observability "
            "operator proof. This command never sends an alert or creates proof."
        )
    )
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--policy", type=Path, default=gate.DEFAULT_POLICY)
    parser.add_argument(
        "--release-channel", type=Path, default=gate.DEFAULT_RELEASE_CHANNEL
    )
    parser.add_argument(
        "--canonical-proof", type=Path, default=gate.DEFAULT_OPERATOR_PROOF
    )
    parser.add_argument("--attestation", type=Path)
    parser.add_argument("--canonical-attestation", type=Path)
    parser.add_argument("--intake-request", type=Path, default=gate.DEFAULT_INTAKE_REQUEST)
    parser.add_argument(
        "--import-proof",
        action="store_true",
        help="Atomically install the exact validated bytes at the canonical proof path.",
    )
    parser.add_argument("--receipt", type=Path, default=DEFAULT_INTAKE_RECEIPT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    receipt = process_intake(
        source_path=args.source,
        import_proof=args.import_proof,
        destination_path=args.canonical_proof,
        attestation_path=args.attestation,
        destination_attestation_path=args.canonical_attestation,
        intake_request_path=args.intake_request,
        policy_path=args.policy,
        release_channel_path=args.release_channel,
    )
    gate = _load_gate_module()
    gate.atomic_write_json(args.receipt, receipt)
    print(f"public_edge_observability_operator_proof_intake:{receipt['status']}")
    return 0 if receipt["status"] in {"pass", "ready"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
