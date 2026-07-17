#!/usr/bin/env python3
"""Bounded watcher for externally produced observability operator proof.

The default mode validates only.  Canonical import and post-import gate
regeneration occur only when the caller explicitly supplies ``--import-proof``.
The watcher never creates proof, configures monitoring, or sends alerts.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import time
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
GATE_SCRIPT = ROOT / "scripts" / "verify_public_edge_observability_release.py"
REQUEST_SCRIPT = (
    ROOT
    / "scripts"
    / "materialize_public_edge_observability_operator_proof_intake_request.py"
)
IMPORT_SCRIPT = ROOT / "scripts" / "import_public_edge_observability_operator_proof.py"
DEFAULT_REQUEST = (
    ROOT
    / ".codex-studio"
    / "published"
    / "PUBLIC_EDGE_OBSERVABILITY_OPERATOR_PROOF_INTAKE_REQUEST.generated.json"
)
DEFAULT_STATE = (
    ROOT
    / ".state"
    / "public_edge_observability_operator_proof_watcher.generated.json"
)
WATCH_CONTRACT = "chummer.public_edge_observability_operator_proof_watch.v1"
MAX_WAIT_SECONDS = 86_400.0
MAX_POLL_SECONDS = 3_600.0


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {path.name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_gate_module():
    return _load_module(GATE_SCRIPT, "public_edge_observability_release_for_watch")


def _load_request_module():
    return _load_module(
        REQUEST_SCRIPT,
        "public_edge_observability_operator_proof_intake_request_for_watch",
    )


def _load_import_module():
    return _load_module(
        IMPORT_SCRIPT,
        "public_edge_observability_operator_proof_intake_for_watch",
    )


def _source_row(path: Path, *, gate_module: Any | None = None) -> dict[str, Any]:
    gate = gate_module or _load_gate_module()
    raw, load_error = gate.read_regular_file_bytes(path)
    return {
        "name": path.name,
        "path": str(path),
        "exists": load_error != "missing",
        "load_status": load_error or "loaded",
        "sha256": hashlib.sha256(raw).hexdigest() if raw is not None else None,
    }


def _source_row_after_intake(
    path: Path,
    intake_receipt: dict[str, Any],
    *,
    gate_module: Any,
) -> dict[str, Any]:
    row = _source_row(path, gate_module=gate_module)
    processed_source = intake_receipt.get("source")
    processed_source = (
        processed_source if isinstance(processed_source, dict) else {}
    )
    processed_digest = processed_source.get("sha256")
    if not isinstance(processed_digest, str) or not processed_digest:
        processed_digest = None
    row["processed_sha256"] = processed_digest
    row["matches_processed_bytes"] = (
        row["sha256"] == processed_digest if processed_digest is not None else None
    )

    attestation_path = gate_module.detached_operator_attestation_path(path)
    attestation_row = _source_row(attestation_path, gate_module=gate_module)
    processed_attestation = processed_source.get("attestation")
    processed_attestation = (
        processed_attestation if isinstance(processed_attestation, dict) else {}
    )
    processed_attestation_digest = processed_attestation.get("sha256")
    if (
        not isinstance(processed_attestation_digest, str)
        or not processed_attestation_digest
    ):
        processed_attestation_digest = None
    attestation_row["processed_sha256"] = processed_attestation_digest
    attestation_row["matches_processed_bytes"] = (
        attestation_row["sha256"] == processed_attestation_digest
        if processed_attestation_digest is not None
        else None
    )
    row["attestation"] = attestation_row
    return row


def materialize_current_request(
    request_path: Path,
    source_path: Path,
    *,
    policy_path: Path | None = None,
    release_channel_path: Path | None = None,
    canonical_proof_path: Path | None = None,
) -> dict[str, Any]:
    gate = _load_gate_module()
    request_module = _load_request_module()
    payload = request_module.build_request(
        policy_path=policy_path or gate.DEFAULT_POLICY,
        release_channel_path=(
            release_channel_path or gate.DEFAULT_RELEASE_CHANNEL
        ),
        source_path=source_path,
        canonical_proof_path=canonical_proof_path or gate.DEFAULT_OPERATOR_PROOF,
        request_output=request_path,
    )
    gate.atomic_write_json(request_path, payload)
    return payload


def process_external_source(
    source_path: Path,
    import_proof: bool,
    *,
    policy_path: Path | None = None,
    release_channel_path: Path | None = None,
    canonical_proof_path: Path | None = None,
    intake_request_path: Path = DEFAULT_REQUEST,
) -> dict[str, Any]:
    gate = _load_gate_module()
    importer = _load_import_module()
    receipt = importer.process_intake(
        source_path=source_path,
        import_proof=import_proof,
        destination_path=canonical_proof_path or gate.DEFAULT_OPERATOR_PROOF,
        policy_path=policy_path or gate.DEFAULT_POLICY,
        release_channel_path=(
            release_channel_path or gate.DEFAULT_RELEASE_CHANNEL
        ),
        intake_request_path=intake_request_path,
    )
    gate.atomic_write_json(importer.DEFAULT_INTAKE_RECEIPT, receipt)
    return receipt


def verify_after_import(
    *,
    policy_path: Path | None = None,
    release_channel_path: Path | None = None,
    canonical_proof_path: Path | None = None,
    intake_request_path: Path = DEFAULT_REQUEST,
) -> dict[str, Any]:
    gate = _load_gate_module()
    receipt = gate.build_receipt(
        policy_path=policy_path or gate.DEFAULT_POLICY,
        operator_proof_path=canonical_proof_path or gate.DEFAULT_OPERATOR_PROOF,
        release_channel_path=(
            release_channel_path or gate.DEFAULT_RELEASE_CHANNEL
        ),
        intake_request_path=intake_request_path,
    )
    gate.atomic_write_json(gate.DEFAULT_OUTPUT, receipt)
    return receipt


def _state(
    *,
    status: str,
    verdict: str,
    request: dict[str, Any],
    request_path: Path,
    source_path: Path,
    import_proof: bool,
    poll_count: int,
    wait_seconds: float,
    poll_seconds: float,
    started_at: datetime,
    now: datetime,
    exit_code: int,
    intake_receipt: dict[str, Any] | None = None,
    gate_receipt: dict[str, Any] | None = None,
    source_observation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    current_bindings = request.get("current_bindings")
    current_bindings = current_bindings if isinstance(current_bindings, dict) else {}
    return {
        "contract_name": WATCH_CONTRACT,
        "status": status,
        "verdict": verdict,
        "generated_at_utc": now.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "started_at_utc": started_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "mode": "import" if import_proof else "validate_only",
        "import_requested_explicitly": import_proof,
        "proof_generated_by_watcher": False,
        "sends_alerts": False,
        "configures_monitoring": False,
        "request_path": str(request_path),
        "request_status": str(request.get("status") or ""),
        "request_binding_sha256": str(current_bindings.get("binding_sha256") or ""),
        "source": source_observation or _source_row(source_path),
        "poll_count": poll_count,
        "wait_seconds": wait_seconds,
        "poll_seconds": poll_seconds,
        "intake_receipt": intake_receipt or {},
        "post_import_gate": gate_receipt or {},
        "exit_code": exit_code,
    }


def watch_for_proof(
    *,
    source_path: Path,
    request_path: Path,
    state_path: Path,
    wait_seconds: float,
    poll_seconds: float,
    import_proof: bool,
    refresh_request: Callable[[Path, Path], dict[str, Any]] = materialize_current_request,
    process_source: Callable[[Path, bool], dict[str, Any]] = process_external_source,
    post_import_verify: Callable[[], dict[str, Any]] = verify_after_import,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    utc_now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> dict[str, Any]:
    if not 0 <= wait_seconds <= MAX_WAIT_SECONDS:
        raise ValueError(f"wait_seconds must be between 0 and {MAX_WAIT_SECONDS:g}")
    if not 0.1 <= poll_seconds <= MAX_POLL_SECONDS:
        raise ValueError(f"poll_seconds must be between 0.1 and {MAX_POLL_SECONDS:g}")

    gate = _load_gate_module()
    started_at = utc_now().astimezone(UTC)
    deadline = monotonic() + wait_seconds
    poll_count = 0

    while True:
        poll_count += 1
        request = refresh_request(request_path, source_path)
        now = utc_now().astimezone(UTC)
        if request.get("status") != "ready":
            payload = _state(
                status="request_blocked",
                verdict="INTAKE_REQUEST_BLOCKED",
                request=request,
                request_path=request_path,
                source_path=source_path,
                import_proof=import_proof,
                poll_count=poll_count,
                wait_seconds=wait_seconds,
                poll_seconds=poll_seconds,
                started_at=started_at,
                now=now,
                exit_code=1,
            )
            gate.atomic_write_json(state_path, payload)
            return payload

        if source_path.exists():
            intake = process_source(source_path, import_proof)
            intake_status = str(intake.get("status") or "")
            if intake_status not in {"ready", "pass"}:
                payload = _state(
                    status="proof_rejected",
                    verdict=str(intake.get("verdict") or "OPERATOR_PROOF_REJECTED"),
                    request=request,
                    request_path=request_path,
                    source_path=source_path,
                    import_proof=import_proof,
                    poll_count=poll_count,
                    wait_seconds=wait_seconds,
                    poll_seconds=poll_seconds,
                    started_at=started_at,
                    now=now,
                    exit_code=1,
                    intake_receipt=intake,
                )
                gate.atomic_write_json(state_path, payload)
                return payload

            source_observation = _source_row_after_intake(
                source_path,
                intake,
                gate_module=gate,
            )
            source_changed_after_processing = (
                source_observation["processed_sha256"] is not None
                and source_observation["matches_processed_bytes"] is not True
            )
            source_binding_missing = source_observation["processed_sha256"] is None
            attestation_observation = source_observation.get("attestation")
            attestation_observation = (
                attestation_observation
                if isinstance(attestation_observation, dict)
                else {}
            )
            attestation_changed_after_processing = (
                attestation_observation.get("processed_sha256") is not None
                and attestation_observation.get("matches_processed_bytes") is not True
            )
            attestation_binding_missing = (
                attestation_observation.get("processed_sha256") is None
            )
            source_pair_binding_missing = (
                source_binding_missing or attestation_binding_missing
            )
            source_pair_changed_after_processing = (
                source_changed_after_processing
                or attestation_changed_after_processing
            )
            if (
                source_pair_binding_missing or source_pair_changed_after_processing
            ) and not import_proof:
                payload = _state(
                    status=(
                        "proof_source_binding_missing"
                        if source_pair_binding_missing
                        else "proof_source_changed_after_validation"
                    ),
                    verdict=(
                        "OPERATOR_PROOF_SOURCE_BINDING_MISSING"
                        if source_pair_binding_missing
                        else "OPERATOR_PROOF_SOURCE_CHANGED"
                    ),
                    request=request,
                    request_path=request_path,
                    source_path=source_path,
                    import_proof=False,
                    poll_count=poll_count,
                    wait_seconds=wait_seconds,
                    poll_seconds=poll_seconds,
                    started_at=started_at,
                    now=now,
                    exit_code=1,
                    intake_receipt=intake,
                    source_observation=source_observation,
                )
                gate.atomic_write_json(state_path, payload)
                return payload

            if not import_proof:
                payload = _state(
                    status="proof_validated",
                    verdict="OPERATOR_PROOF_VALIDATED_NOT_IMPORTED",
                    request=request,
                    request_path=request_path,
                    source_path=source_path,
                    import_proof=False,
                    poll_count=poll_count,
                    wait_seconds=wait_seconds,
                    poll_seconds=poll_seconds,
                    started_at=started_at,
                    now=now,
                    exit_code=0,
                    intake_receipt=intake,
                    source_observation=source_observation,
                )
                gate.atomic_write_json(state_path, payload)
                return payload

            gate_receipt = post_import_verify()
            gate_passed = (
                gate_receipt.get("status") == "pass"
                and gate_receipt.get("verdict") == "OBSERVABILITY_RELEASE_READY"
                and not gate_receipt.get("failures")
            )
            payload = _state(
                status=(
                    "proof_imported_and_verified"
                    if gate_passed
                    else "post_import_verification_failed"
                ),
                verdict=(
                    "OBSERVABILITY_RELEASE_READY"
                    if gate_passed
                    else "OBSERVABILITY_RELEASE_BLOCKED"
                ),
                request=request,
                request_path=request_path,
                source_path=source_path,
                import_proof=True,
                poll_count=poll_count,
                wait_seconds=wait_seconds,
                poll_seconds=poll_seconds,
                started_at=started_at,
                now=now,
                exit_code=0 if gate_passed else 1,
                intake_receipt=intake,
                gate_receipt=gate_receipt,
                source_observation=source_observation,
            )
            gate.atomic_write_json(state_path, payload)
            return payload

        now_monotonic = monotonic()
        if now_monotonic >= deadline:
            payload = _state(
                status="waiting_for_external_proof",
                verdict="WATCH_TIMEOUT",
                request=request,
                request_path=request_path,
                source_path=source_path,
                import_proof=import_proof,
                poll_count=poll_count,
                wait_seconds=wait_seconds,
                poll_seconds=poll_seconds,
                started_at=started_at,
                now=now,
                exit_code=2,
            )
            gate.atomic_write_json(state_path, payload)
            return payload

        waiting = _state(
            status="waiting_for_external_proof",
            verdict="WATCHING",
            request=request,
            request_path=request_path,
            source_path=source_path,
            import_proof=import_proof,
            poll_count=poll_count,
            wait_seconds=wait_seconds,
            poll_seconds=poll_seconds,
            started_at=started_at,
            now=now,
            exit_code=2,
        )
        gate.atomic_write_json(state_path, waiting)
        sleep(min(poll_seconds, max(deadline - now_monotonic, 0.0)))


def parse_args() -> argparse.Namespace:
    gate = _load_gate_module()
    parser = argparse.ArgumentParser(
        description=(
            "Watch a deterministic drop path for external observability proof. "
            "Defaults to validate-only and never sends alerts."
        )
    )
    parser.add_argument(
        "--source", type=Path, default=gate.DEFAULT_OPERATOR_PROOF_INTAKE_SOURCE
    )
    parser.add_argument("--policy", type=Path, default=gate.DEFAULT_POLICY)
    parser.add_argument(
        "--release-channel", type=Path, default=gate.DEFAULT_RELEASE_CHANNEL
    )
    parser.add_argument(
        "--canonical-proof", type=Path, default=gate.DEFAULT_OPERATOR_PROOF
    )
    parser.add_argument("--request", type=Path, default=DEFAULT_REQUEST)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--wait-seconds", type=float, default=900.0)
    parser.add_argument("--poll-seconds", type=float, default=10.0)
    parser.add_argument(
        "--import-proof",
        action="store_true",
        help=(
            "After successful validation, atomically import the exact source bytes and "
            "regenerate the release gate. Without this flag the watcher validates only."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        payload = watch_for_proof(
            source_path=args.source,
            request_path=args.request,
            state_path=args.state,
            wait_seconds=args.wait_seconds,
            poll_seconds=args.poll_seconds,
            import_proof=args.import_proof,
            refresh_request=partial(
                materialize_current_request,
                policy_path=args.policy,
                release_channel_path=args.release_channel,
                canonical_proof_path=args.canonical_proof,
            ),
            process_source=partial(
                process_external_source,
                policy_path=args.policy,
                release_channel_path=args.release_channel,
                canonical_proof_path=args.canonical_proof,
                intake_request_path=args.request,
            ),
            post_import_verify=partial(
                verify_after_import,
                policy_path=args.policy,
                release_channel_path=args.release_channel,
                canonical_proof_path=args.canonical_proof,
                intake_request_path=args.request,
            ),
        )
    except ValueError as exc:
        print(f"public_edge_observability_operator_proof_watch:invalid_arguments:{exc}")
        return 2
    print(f"public_edge_observability_operator_proof_watch:{payload['status']}")
    return int(payload["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
