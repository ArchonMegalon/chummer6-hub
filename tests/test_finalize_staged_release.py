from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import stat
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "finalize_staged_release.py"
SPEC = importlib.util.spec_from_file_location("finalize_staged_release", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def pointer(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def registry_current(snapshot: bytes) -> bytes:
    encoded_empty = base64.b64encode(b"{}\n").decode("ascii")
    return (
        json.dumps(
            {
                "current": {},
                "snapshot": {},
                "snapshotBytes": base64.b64encode(snapshot).decode("ascii"),
                "manifestBytes": encoded_empty,
                "releaseDecisionBytes": encoded_empty,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode()


def test_activation_ambiguity_target_retries_idempotently_without_compensation() -> None:
    target = b'{"generationId":"target"}\n'
    calls: list[str] = []

    result = MODULE.reconcile_activation_failure(
        observed_pointer_bytes=target,
        target_pointer_sha256=pointer(target),
        predecessor_pointer_sha256="sha256:" + "a" * 64,
        retry_activation=lambda: calls.append("retry") is None,
    )

    assert result == "activated"
    assert calls == ["retry"]


def test_delayed_activation_after_predecessor_read_never_triggers_registry_compensation() -> None:
    predecessor = b'{"generationId":"previous"}\n'
    target = b'{"generationId":"target"}\n'
    calls: list[str] = []
    public_current = predecessor

    with pytest.raises(MODULE.MutationOutcomeUnknown, match="still be in flight"):
        MODULE.reconcile_activation_failure(
            observed_pointer_bytes=public_current,
            target_pointer_sha256=pointer(target),
            predecessor_pointer_sha256="sha256:" + pointer(predecessor),
            retry_activation=lambda: calls.append("retry") is None,
        )

    # Model the original timed-out server request committing after the first
    # CURRENT read. The finalizer must have left Registry untouched.
    public_current = target
    assert public_current == target
    assert calls == []


def test_execute_transaction_persists_unknown_when_delayed_activation_commits_after_get(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    predecessor = b'{"generationId":"previous"}\n'
    target = b'{"generationId":"target"}\n'
    preview_snapshot = b'{"releaseVersion":"run-test","status":"preview_ready"}\n'
    state = {
        "current": predecessor,
        "activationPosts": 0,
        "registryPosts": 0,
        "registryGets": 0,
    }

    class DelayedActivationTransport:
        def __init__(self, timeout: int):
            assert timeout == 1

        def request(
            self,
            method: str,
            url: str,
            *,
            body: bytes | None = None,
            credential_header: tuple[str, str] | None = None,
            maximum: int = 16 * 1024 * 1024,
        ) -> tuple[int, bytes]:
            del body, credential_header, maximum
            if method == "POST" and url.endswith("/activate-staged"):
                state["activationPosts"] += 1
                if state["activationPosts"] == 1:
                    raise MODULE.MutationOutcomeUnknown(
                        "timed out while server kept running"
                    )
                assert state["current"] == target
                return 200, b'{"generationId":"gen-target","version":"run-test"}\n'
            if method == "POST":
                state["registryPosts"] += 1
                raise AssertionError("Registry must not be compensated")
            assert method == "GET"
            if url.endswith("/api/v1/registry/release-authority/current"):
                state["registryGets"] += 1
                return 200, registry_current(preview_snapshot)
            assert url.endswith("/downloads/current.json")
            observed = state["current"]
            # The timed-out activation commits immediately after the finalizer's
            # first predecessor observation.
            state["current"] = target
            return 200, observed

    monkeypatch.setattr(MODULE, "HttpsTransport", DelayedActivationTransport)
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    checkpoint_path = tmp_path / "checkpoint.json"
    checkpoint = {
        "state": "registry_preview_published",
        "convergencePolicy": {"timeoutSeconds": 1},
        "expected": {
            "authorityRevisionId": "auth-" + "a" * 64,
            "previewSnapshotSha256": pointer(preview_snapshot),
            "previewDecisionSha256": "c" * 64,
        },
        "activationUrl": "https://chummer.run/api/internal/releases/upload-sessions/"
        "00000000000000000000000000000000/activate-staged",
        "registryPublishUrl": "https://registry.invalid/api/v1/registry/release-authority/publish",
        "registryCurrentUrl": "https://registry.invalid/api/v1/registry/release-authority/current",
        "liveBaseUrl": "https://chummer.run",
        "generationId": "gen-target",
        "releaseVersion": "run-test",
        "stageReceiptId": "stage-test",
        "targetPointerSha256": pointer(target),
        "predecessorPointerSha256": "sha256:" + pointer(predecessor),
        "evidenceDirectory": "evidence",
        "files": {},
    }

    with pytest.raises(MODULE.MutationOutcomeUnknown, match="Registry was not compensated"):
        MODULE._execute_transaction(
            checkpoint,
            {},
            checkpoint_path,
            tmp_path,
            "hub-token",
            "registry-key",
        )

    assert state["activationPosts"] == 1
    assert state["registryPosts"] == 0
    assert state["registryGets"] == 1
    assert state["current"] == target
    persisted = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    assert persisted["state"] == "activation_outcome_unknown"
    assert checkpoint_path.read_bytes() == (
        json.dumps(persisted, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()
    assert stat.S_IMODE(checkpoint_path.stat().st_mode) == 0o600

    def stop_before_convergence(*_args: object, **_kwargs: object) -> None:
        raise MODULE.FinalizerError("stop after idempotent activation acknowledgement")

    monkeypatch.setattr(MODULE, "_run_convergence", stop_before_convergence)
    with pytest.raises(MODULE.FinalizerError, match="stop after idempotent"):
        MODULE._execute_transaction(
            persisted,
            {},
            checkpoint_path,
            tmp_path,
            "hub-token",
            "registry-key",
        )

    assert state["activationPosts"] == 2
    assert state["registryPosts"] == 0
    assert state["registryGets"] == 4
    assert state["current"] == target
    resumed = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    assert resumed["state"] == "hub_activation_confirmed"
    assert resumed["files"]["hubActivationResponse"]["sha256"] == hashlib.sha256(
        b'{"generationId":"gen-target","version":"run-test"}\n'
    ).hexdigest()


@pytest.mark.parametrize(
    "checkpoint_state", ["registry_preview_published", "activation_outcome_unknown"]
)
def test_registry_drift_blocks_resume_before_any_hub_activation_post(
    checkpoint_state: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected_snapshot = b'{"releaseVersion":"run-test","revision":1}\n'
    advanced_snapshot = b'{"releaseVersion":"run-next","revision":2}\n'
    calls = {"activationPosts": 0, "registryGets": 0}

    class DriftedRegistryTransport:
        def __init__(self, timeout: int):
            assert timeout == 1

        def request(
            self,
            method: str,
            url: str,
            *,
            body: bytes | None = None,
            credential_header: tuple[str, str] | None = None,
            maximum: int = 16 * 1024 * 1024,
        ) -> tuple[int, bytes]:
            del body, credential_header, maximum
            if method == "POST" and url.endswith("/activate-staged"):
                calls["activationPosts"] += 1
                raise AssertionError("stale checkpoint must not activate Hub")
            assert method == "GET"
            assert url.endswith("/api/v1/registry/release-authority/current")
            calls["registryGets"] += 1
            return 200, registry_current(advanced_snapshot)

    monkeypatch.setattr(MODULE, "HttpsTransport", DriftedRegistryTransport)
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    checkpoint = {
        "state": checkpoint_state,
        "convergencePolicy": {"timeoutSeconds": 1},
        "expected": {
            "authorityRevisionId": "auth-" + "a" * 64,
            "previewSnapshotSha256": pointer(expected_snapshot),
            "previewDecisionSha256": "c" * 64,
        },
        "activationUrl": "https://chummer.run/api/internal/releases/upload-sessions/"
        "00000000000000000000000000000000/activate-staged",
        "registryCurrentUrl": "https://registry.invalid/api/v1/registry/release-authority/current",
        "liveBaseUrl": "https://chummer.run",
        "generationId": "gen-target",
        "releaseVersion": "run-test",
        "stageReceiptId": "stage-test",
        "targetPointerSha256": "d" * 64,
        "evidenceDirectory": "evidence",
        "files": {},
    }

    with pytest.raises(MODULE.FinalizerError, match="expected exact snapshot"):
        MODULE._execute_transaction(
            checkpoint,
            {},
            tmp_path / "checkpoint.json",
            tmp_path,
            "hub-token",
            "registry-key",
        )

    assert calls == {"activationPosts": 0, "registryGets": 1}


def test_registry_advance_after_exact_hub_ack_persists_outcome_unknown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    preview_snapshot = b'{"releaseVersion":"run-test","revision":1}\n'
    advanced_snapshot = b'{"releaseVersion":"run-next","revision":2}\n'
    target = b'{"generationId":"gen-target"}\n'
    state = {
        "registrySnapshot": preview_snapshot,
        "activationPosts": 0,
        "registryPosts": 0,
        "registryGets": 0,
        "publicGets": 0,
    }

    class RegistryAdvanceDuringActivationTransport:
        def __init__(self, timeout: int):
            assert timeout == 1

        def request(
            self,
            method: str,
            url: str,
            *,
            body: bytes | None = None,
            credential_header: tuple[str, str] | None = None,
            maximum: int = 16 * 1024 * 1024,
        ) -> tuple[int, bytes]:
            del body, credential_header, maximum
            if method == "POST" and url.endswith("/activate-staged"):
                state["activationPosts"] += 1
                state["registrySnapshot"] = advanced_snapshot
                return 200, b'{"generationId":"gen-target","version":"run-test"}\n'
            if method == "POST":
                state["registryPosts"] += 1
                raise AssertionError("Registry must not be compensated")
            assert method == "GET"
            if url.endswith("/api/v1/registry/release-authority/current"):
                state["registryGets"] += 1
                return 200, registry_current(state["registrySnapshot"])
            assert url.endswith("/downloads/current.json")
            state["publicGets"] += 1
            return 200, target

    monkeypatch.setattr(
        MODULE, "HttpsTransport", RegistryAdvanceDuringActivationTransport
    )
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    checkpoint_path = tmp_path / "checkpoint.json"
    checkpoint = {
        "state": "registry_preview_published",
        "convergencePolicy": {"timeoutSeconds": 1},
        "expected": {
            "authorityRevisionId": "auth-" + "a" * 64,
            "previewSnapshotSha256": pointer(preview_snapshot),
            "previewDecisionSha256": "c" * 64,
        },
        "activationUrl": "https://chummer.run/api/internal/releases/upload-sessions/"
        "00000000000000000000000000000000/activate-staged",
        "registryCurrentUrl": "https://registry.invalid/api/v1/registry/release-authority/current",
        "liveBaseUrl": "https://chummer.run",
        "generationId": "gen-target",
        "releaseVersion": "run-test",
        "stageReceiptId": "stage-test",
        "targetPointerSha256": pointer(target),
        "predecessorPointerSha256": "sha256:" + "d" * 64,
        "evidenceDirectory": "evidence",
        "files": {},
    }

    with pytest.raises(MODULE.MutationOutcomeUnknown, match="Registry was not compensated"):
        MODULE._execute_transaction(
            checkpoint,
            {},
            checkpoint_path,
            tmp_path,
            "hub-token",
            "registry-key",
        )

    assert state == {
        "registrySnapshot": advanced_snapshot,
        "activationPosts": 1,
        "registryPosts": 0,
        "registryGets": 3,
        "publicGets": 1,
    }
    persisted = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    assert persisted["state"] == "activation_outcome_unknown"
    assert persisted["files"]["hubActivationResponse"]["sha256"] == pointer(
        b'{"generationId":"gen-target","version":"run-test"}\n'
    )
    assert "finalReceipt" not in persisted["files"]


def test_confirmed_resume_with_registry_drift_never_runs_convergence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    preview_snapshot = b'{"releaseVersion":"run-test","revision":1}\n'
    advanced_snapshot = b'{"releaseVersion":"run-next","revision":2}\n'
    calls = {"registryGets": 0, "convergence": 0}

    class DriftedRegistryTransport:
        def __init__(self, timeout: int):
            assert timeout == 1

        def request(self, method: str, url: str, **_kwargs: object) -> tuple[int, bytes]:
            assert method == "GET"
            assert url.endswith("/api/v1/registry/release-authority/current")
            calls["registryGets"] += 1
            return 200, registry_current(advanced_snapshot)

    def convergence(*_args: object, **_kwargs: object) -> None:
        calls["convergence"] += 1

    monkeypatch.setattr(MODULE, "HttpsTransport", DriftedRegistryTransport)
    monkeypatch.setattr(MODULE, "_run_convergence", convergence)
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    checkpoint = {
        "state": "hub_activation_confirmed",
        "convergencePolicy": {"timeoutSeconds": 1},
        "expected": {"previewSnapshotSha256": pointer(preview_snapshot)},
        "registryCurrentUrl": "https://registry.invalid/api/v1/registry/release-authority/current",
        "evidenceDirectory": "evidence",
        "files": {},
    }

    with pytest.raises(MODULE.FinalizerError, match="expected exact snapshot"):
        MODULE._execute_transaction(
            checkpoint,
            {},
            tmp_path / "checkpoint.json",
            tmp_path,
            "hub-token",
            "registry-key",
        )

    assert calls == {"registryGets": 1, "convergence": 0}
    assert not (evidence / "STAGED_RELEASE_OWNER_FINALIZATION.generated.json").exists()


def test_registry_drift_during_convergence_prevents_completion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    preview_snapshot = b'{"releaseVersion":"run-test","revision":1}\n'
    advanced_snapshot = b'{"releaseVersion":"run-next","revision":2}\n'
    state = {"registrySnapshot": preview_snapshot, "registryGets": 0, "convergence": 0}

    class AdvancingRegistryTransport:
        def __init__(self, timeout: int):
            assert timeout == 1

        def request(self, method: str, url: str, **_kwargs: object) -> tuple[int, bytes]:
            assert method == "GET"
            assert url.endswith("/api/v1/registry/release-authority/current")
            state["registryGets"] += 1
            return 200, registry_current(state["registrySnapshot"])

    def convergence(*_args: object, **_kwargs: object) -> None:
        state["convergence"] += 1
        state["registrySnapshot"] = advanced_snapshot

    monkeypatch.setattr(MODULE, "HttpsTransport", AdvancingRegistryTransport)
    monkeypatch.setattr(MODULE, "_run_convergence", convergence)
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    checkpoint_path = tmp_path / "checkpoint.json"
    checkpoint = {
        "state": "hub_activation_confirmed",
        "convergencePolicy": {"timeoutSeconds": 1},
        "expected": {"previewSnapshotSha256": pointer(preview_snapshot)},
        "registryCurrentUrl": "https://registry.invalid/api/v1/registry/release-authority/current",
        "evidenceDirectory": "evidence",
        "files": {},
    }

    with pytest.raises(MODULE.FinalizerError, match="expected exact snapshot"):
        MODULE._execute_transaction(
            checkpoint,
            {},
            checkpoint_path,
            tmp_path,
            "hub-token",
            "registry-key",
        )

    assert state == {
        "registrySnapshot": advanced_snapshot,
        "registryGets": 2,
        "convergence": 1,
    }
    assert checkpoint["state"] == "hub_activation_confirmed"
    assert not checkpoint_path.exists()
    assert not (evidence / "STAGED_RELEASE_OWNER_FINALIZATION.generated.json").exists()


def test_unhandled_transaction_state_cannot_fall_through_to_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class NoNetworkTransport:
        def __init__(self, timeout: int):
            assert timeout == 1

        def request(self, *_args: object, **_kwargs: object) -> tuple[int, bytes]:
            raise AssertionError("unhandled state must not touch the network")

    monkeypatch.setattr(MODULE, "HttpsTransport", NoNetworkTransport)
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    checkpoint = {
        "state": "compensated_review_required",
        "convergencePolicy": {"timeoutSeconds": 1},
        "expected": {},
        "evidenceDirectory": "evidence",
    }

    with pytest.raises(MODULE.FinalizerError, match="did not reach complete state"):
        MODULE._execute_transaction(
            checkpoint,
            {},
            tmp_path / "checkpoint.json",
            tmp_path,
            "hub-token",
            "registry-key",
        )


def test_activation_ambiguity_unknown_never_retries_or_compensates() -> None:
    calls: list[str] = []

    with pytest.raises(MODULE.MutationOutcomeUnknown, match="neither"):
        MODULE.reconcile_activation_failure(
            observed_pointer_bytes=b"unexpected-current\n",
            target_pointer_sha256="b" * 64,
            predecessor_pointer_sha256="sha256:" + "a" * 64,
            retry_activation=lambda: calls.append("retry") is None,
        )

    assert calls == []


def test_predecessor_without_durable_abort_proof_is_always_outcome_unknown() -> None:
    predecessor = b'{"generationId":"previous"}\n'

    with pytest.raises(MODULE.MutationOutcomeUnknown, match="durable server-side"):
        MODULE.reconcile_activation_failure(
            observed_pointer_bytes=predecessor,
            target_pointer_sha256="b" * 64,
            predecessor_pointer_sha256=pointer(predecessor),
            retry_activation=lambda: True,
        )


def test_main_emits_distinct_outcome_unknown_exit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workspace = tmp_path / "run"
    workspace.mkdir(mode=0o700)
    args = SimpleNamespace(
        timeout=1,
        convergence_attempts=1,
        convergence_retry_seconds=1,
        workspace=workspace,
        resume_checkpoint=None,
        hub_owner_token_file=tmp_path / "hub-token",
        registry_control_key_file=tmp_path / "registry-key",
    )
    for name in MODULE.OWNER_ENVIRONMENT_NAMES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(MODULE, "_args", lambda _argv=None: args)
    monkeypatch.setattr(
        MODULE,
        "_prepare_transaction",
        lambda _args, _root: ({}, {}, workspace / "checkpoint.json"),
    )
    monkeypatch.setattr(MODULE, "_read_secret", lambda *_args, **_kwargs: "secret")

    def outcome_unknown(*_args: object, **_kwargs: object) -> None:
        raise MODULE.MutationOutcomeUnknown("durable reconciliation required")

    monkeypatch.setattr(MODULE, "_execute_transaction", outcome_unknown)

    assert MODULE.main([]) == 3
    assert "activation outcome_unknown" in capsys.readouterr().err


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
