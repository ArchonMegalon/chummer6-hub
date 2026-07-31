#!/usr/bin/env python3
"""Sign exact live-operator observability proof with the pinned local authority."""

from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import json
import os
import stat
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GATE_SCRIPT = ROOT / "scripts" / "verify_public_edge_observability_release.py"
DEFAULT_PROOF = (
    ROOT
    / ".state"
    / "incoming_public_edge_observability_operator_proof"
    / "PUBLIC_EDGE_OBSERVABILITY_OPERATOR_PROOF.generated.json"
)
DEFAULT_REQUEST = (
    ROOT
    / ".codex-studio"
    / "published"
    / "PUBLIC_EDGE_OBSERVABILITY_OPERATOR_PROOF_INTAKE_REQUEST.generated.json"
)
DEFAULT_PRIVATE_KEY = (
    ROOT
    / ".state"
    / "observability-attesters"
    / "local-observability-operator-2026.private.pem"
)
DEFAULT_KEY_ID = "local-observability-operator-2026"


def load_gate():
    spec = importlib.util.spec_from_file_location(
        "public_edge_observability_release_for_signing",
        GATE_SCRIPT,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("observability gate module could not be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_private_key(path: Path) -> None:
    if not path.is_absolute() or path.is_symlink():
        raise RuntimeError("private key must be an absolute, non-symlink path")
    metadata = path.stat()
    if not stat.S_ISREG(metadata.st_mode):
        raise RuntimeError("private key must be a regular file")
    if stat.S_IMODE(metadata.st_mode) & 0o077:
        raise RuntimeError("private key permissions must not grant group or other access")


def load_object(gate, path: Path, label: str) -> tuple[dict[str, object], bytes, str]:
    raw, error = gate.read_regular_file_bytes(path)
    if error is not None or raw is None:
        raise RuntimeError(f"{label} is {error}")
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"{label} is invalid JSON") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"{label} must be an object")
    return value, raw, hashlib.sha256(raw).hexdigest()


def sign(*, proof_path: Path, request_path: Path, private_key: Path, key_id: str, output: Path) -> None:
    gate = load_gate()
    proof, proof_bytes, proof_sha256 = load_object(gate, proof_path, "operator proof")
    request, _, request_sha256 = load_object(gate, request_path, "intake request")
    policy, policy_error, policy_sha256 = gate.load_json_with_sha256(gate.DEFAULT_POLICY)
    if policy_error is not None or policy is None or policy_sha256 is None:
        raise RuntimeError(f"policy is {policy_error}")
    release, _, _, release_failures = gate.release_candidate_binding(
        gate.DEFAULT_RELEASE_CHANNEL
    )
    _, runtime_failures, runtime_binding = gate.inspect_runtime_sources()
    if release_failures or runtime_failures:
        raise RuntimeError("current release or runtime bindings are invalid")
    bindings = gate.operator_attestation_bindings(
        policy_sha256=policy_sha256,
        release_candidate=release,
        runtime_binding=runtime_binding,
    )
    request_failures = gate.validate_intake_request(
        request,
        expected_bindings=bindings,
    )
    proof_failures = gate.validate_operator_proof(
        proof,
        policy=policy,
        policy_digest=policy_sha256,
        release_candidate=release,
        runtime_binding=runtime_binding,
        now=datetime.now(UTC),
    )
    if request_failures or proof_failures:
        raise RuntimeError(
            "proof or request does not bind current runtime: "
            + "; ".join([*request_failures, *proof_failures])
        )

    validate_private_key(private_key)
    unsigned = {
        "contract_name": gate.OPERATOR_ATTESTATION_CONTRACT,
        "algorithm": "ed25519",
        "key_id": key_id,
        "role": "observability_operator",
        "generated_at_utc": gate.iso(datetime.now(UTC)),
        "subject_sha256": proof_sha256,
        "challenge_nonce": str(request.get("challenge_nonce") or ""),
        "request_sha256": request_sha256,
        "bindings": bindings,
    }
    with tempfile.NamedTemporaryFile(prefix="chummer-observability-attestation-") as handle:
        handle.write(gate.canonical_json_bytes(unsigned))
        handle.flush()
        completed = subprocess.run(
            [
                str(gate.ATTESTATION_SUPPORT.OPENSSL_BINARY),
                "pkeyutl",
                "-sign",
                "-inkey",
                str(private_key),
                "-rawin",
                "-in",
                handle.name,
            ],
            capture_output=True,
            check=False,
            env=dict(gate.ATTESTATION_SUPPORT.OPENSSL_SUBPROCESS_ENVIRONMENT),
            timeout=30,
        )
    if completed.returncode != 0 or len(completed.stdout) != 64:
        raise RuntimeError("Ed25519 signing failed")
    attestation = {
        **unsigned,
        "signature": base64.b64encode(completed.stdout).decode("ascii"),
    }
    _, failures = gate.validate_operator_attestation(
        attestation,
        proof_bytes=proof_bytes,
        request=request,
        request_sha256=request_sha256,
        expected_bindings=bindings,
        now=datetime.now(UTC),
    )
    if failures:
        raise RuntimeError("self-verification failed: " + "; ".join(failures))
    gate.atomic_write_json(output, attestation)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--proof", type=Path, default=DEFAULT_PROOF)
    parser.add_argument("--request", type=Path, default=DEFAULT_REQUEST)
    parser.add_argument("--private-key", type=Path, default=DEFAULT_PRIVATE_KEY)
    parser.add_argument("--key-id", default=DEFAULT_KEY_ID)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    proof = args.proof.expanduser().resolve()
    output = (
        args.output.expanduser().resolve()
        if args.output
        else proof.with_name(proof.name + ".attestation.json")
    )
    sign(
        proof_path=proof,
        request_path=args.request.expanduser().resolve(),
        private_key=args.private_key.expanduser().resolve(),
        key_id=str(args.key_id),
        output=output,
    )
    print("public_edge_observability_operator_proof_attestation:pass")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
        print(
            f"public_edge_observability_operator_proof_attestation:fail reason={exc}",
            file=os.sys.stderr,
        )
        raise SystemExit(1)
