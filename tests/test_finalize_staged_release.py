from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import stat

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "finalize_staged_release.py"
SPEC = importlib.util.spec_from_file_location("finalize_staged_release", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def pointer(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def test_activation_ambiguity_target_retries_idempotently_without_compensation() -> None:
    target = b'{"generationId":"target"}\n'
    calls: list[str] = []

    result = MODULE.reconcile_activation_failure(
        observed_pointer_bytes=target,
        target_pointer_sha256=pointer(target),
        predecessor_pointer_sha256="sha256:" + "a" * 64,
        retry_activation=lambda: calls.append("retry") is None,
        compensate_registry=lambda: calls.append("compensate") is None,
    )

    assert result == "activated"
    assert calls == ["retry"]


def test_activation_ambiguity_predecessor_compensates_registry_and_stays_review_required() -> None:
    predecessor = b'{"generationId":"previous"}\n'
    calls: list[str] = []

    result = MODULE.reconcile_activation_failure(
        observed_pointer_bytes=predecessor,
        target_pointer_sha256="b" * 64,
        predecessor_pointer_sha256="sha256:" + pointer(predecessor),
        retry_activation=lambda: calls.append("retry") is None,
        compensate_registry=lambda: calls.append("compensate") is None,
    )

    assert result == "compensated_review_required"
    assert calls == ["compensate"]


def test_activation_ambiguity_unknown_never_retries_or_compensates() -> None:
    calls: list[str] = []

    with pytest.raises(MODULE.MutationOutcomeUnknown, match="neither"):
        MODULE.reconcile_activation_failure(
            observed_pointer_bytes=b"unexpected-current\n",
            target_pointer_sha256="b" * 64,
            predecessor_pointer_sha256="sha256:" + "a" * 64,
            retry_activation=lambda: calls.append("retry") is None,
            compensate_registry=lambda: calls.append("compensate") is None,
        )

    assert calls == []


def test_failed_bounded_compensation_is_never_reported_as_success() -> None:
    predecessor = b'{"generationId":"previous"}\n'

    with pytest.raises(MODULE.MutationOutcomeUnknown, match="not confirmed"):
        MODULE.reconcile_activation_failure(
            observed_pointer_bytes=predecessor,
            target_pointer_sha256="b" * 64,
            predecessor_pointer_sha256=pointer(predecessor),
            retry_activation=lambda: True,
            compensate_registry=lambda: False,
        )


def test_compensation_request_is_exact_cas_and_contains_no_credential() -> None:
    manifest = b'{"version":"run-test"}\n'
    decision = b'{"status":"review_required"}\n'
    snapshot_payload = {
        "releaseVersion": "run-test",
        "channel": "preview",
        "status": "review_required",
        "rolloutState": "review_required",
        "supportabilityState": "review_required",
        "availablePlatforms": ["macos"],
        "primaryHeadByPlatform": {"macos": "avalonia"},
        "artifactCount": 1,
        "downloadAccessPosture": "signed_in",
        "knownIssueSummary": "Review required.",
        "registryRepository": "ArchonMegalon/chummer6-hub-registry",
        "registryCommit": "c" * 40,
        "supportOwner": "release ops",
        "nextActions": ["Review"],
        "artifacts": [{"id": "mac"}],
    }
    snapshot = (json.dumps(snapshot_payload, sort_keys=True) + "\n").encode()

    raw = MODULE._registry_publish_payload_from_envelope(
        manifest,
        snapshot,
        decision,
        "d" * 64,
    )
    payload = json.loads(raw)

    assert payload["expectedCurrentSnapshotSha256"] == "d" * 64
    assert base64.b64decode(payload["manifestBytes"], validate=True) == manifest
    assert base64.b64decode(payload["releaseDecisionBytes"], validate=True) == decision
    assert "token" not in raw.decode().lower()
    assert "authorization" not in raw.decode().lower()


def test_owner_credentials_must_be_mode_0600_and_outside_persisted_workspace(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "run"
    workspace.mkdir(mode=0o700)
    inside = workspace / "leaked-token"
    inside.write_text("secret\n", encoding="utf-8")
    inside.chmod(0o600)
    with pytest.raises(MODULE.FinalizerError, match="outside"):
        MODULE._read_secret(inside, workspace, "Hub owner token")

    outside = tmp_path / "owner-token"
    outside.write_text("secret\n", encoding="utf-8")
    outside.chmod(0o600)
    assert MODULE._read_secret(outside, workspace, "Hub owner token") == "secret"
    outside.chmod(0o640)
    with pytest.raises(MODULE.FinalizerError, match="0600"):
        MODULE._read_secret(outside, workspace, "Hub owner token")
    assert stat.S_IMODE(inside.stat().st_mode) == 0o600
