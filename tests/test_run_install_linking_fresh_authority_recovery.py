from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import stat
import sys
from typing import Any, Sequence

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_install_linking_fresh_authority_recovery.py"
sys.path.insert(0, str(SCRIPT.parent))
SPEC = importlib.util.spec_from_file_location("fresh_recovery", SCRIPT)
assert SPEC and SPEC.loader
fresh = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = fresh
SPEC.loader.exec_module(fresh)

NEW_IDENTITY = "a" * 64
OLD_IDENTITY = "b" * 64
OLD_STATE = "c" * 64
TOOL_IMAGE = "sha256:" + "d" * 64
NOW = datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc)


def json_bytes(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, sort_keys=True) + "\n").encode()


def preflight(*, intent: bool = False) -> dict[str, Any]:
    return {
        "contractName": fresh.PREFLIGHT_CONTRACT,
        "dataProtectionReady": True,
        "floorGeneration": 13,
        "floorPresent": True,
        "floorSnapshotSha256": "1" * 64,
        "intentPresent": intent,
        "intentSha256": "2" * 64 if intent else None,
        "intentState": "prepared" if intent else None,
        "localStorePresent": True,
        "retainedSnapshotSha256": "3" * 64,
        "sourceEnvelopeSha256": "4" * 64,
        "sourceGeneration": 13,
        "sourceSnapshotSha256": "1" * 64,
        "status": "pass",
    }


def transport() -> dict[str, Any]:
    return {
        "authenticated": True,
        "authorityIdentitySha256": NEW_IDENTITY,
        "contractName": "chummer.postgres_transport_proof.v1",
        "gssEncryptionDisabled": True,
        "pgStatSsl": True,
        "plaintextAttempted": True,
        "plaintextRejected": True,
        "plaintextSqlState": "28000",
        "status": "pass",
    }


def prepare() -> dict[str, Any]:
    return {
        "appliedSchemaVersion": 2,
        "authorityIdentitySha256": NEW_IDENTITY,
        "contractName": "chummer.install_linking_postgres_prepare.v1",
        "leastPrivilegeValid": True,
        "runtimeRoleSha256": "5" * 64,
        "status": "pass",
    }


def empty() -> dict[str, Any]:
    return {
        "appliedSchemaVersion": 2,
        "authorityIdentitySha256": NEW_IDENTITY,
        "commitCount": 0,
        "contractName": "chummer.install_linking_postgres_empty_authority_proof.v1",
        "currentRoleMatches": True,
        "empty": True,
        "headGeneration": 0,
        "leastPrivilegeValid": True,
        "runtimeRoleSha256": "5" * 64,
        "schemaValid": True,
        "status": "pass",
    }


def validate() -> dict[str, Any]:
    return {
        "appliedSchemaVersion": 2,
        "authorityIdentitySha256": NEW_IDENTITY,
        "contractName": "chummer.install_linking_postgres_schema_validation.v1",
        "status": "pass",
    }


def role() -> dict[str, Any]:
    return {
        "authorityIdentitySha256": NEW_IDENTITY,
        "contractName": "chummer.install_linking_postgres_runtime_role_proof.v1",
        "currentRoleMatches": True,
        "leastPrivilegeValid": True,
        "runtimeRoleSha256": "5" * 64,
        "status": "pass",
    }


def ready(*, generation: int = 1) -> dict[str, Any]:
    return {
        "appliedSchemaVersion": 2,
        "authorityIdentitySha256": NEW_IDENTITY,
        "authorityStateSha256": "6" * 64,
        "commitCount": generation,
        "contractName": "chummer.install_linking_postgres_authority_readiness_proof.v1",
        "currentRoleMatches": True,
        "empty": generation == 0,
        "headGeneration": generation,
        "leastPrivilegeValid": True,
        "runtimeRoleSha256": "5" * 64,
        "schemaValid": True,
        "status": "pass",
    }


def acknowledgement() -> dict[str, Any]:
    return {
        "authorityIdentitySha256": NEW_IDENTITY,
        "contractName": fresh.ACK_CONTRACT,
        "envelopeSha256": "7" * 64,
        "floorSnapshotSha256": "8" * 64,
        "generation": 1,
        "localAcknowledged": True,
        "localStoreSha256": "7" * 64,
        "snapshotSha256": "8" * 64,
        "status": "pass",
    }


class FakeExecutor:
    def __init__(self, *, fail_import: bool = False, intent_after_failure: bool = False):
        self.calls: list[tuple[str, ...]] = []
        self.fail_import = fail_import
        self.intent_after_failure = intent_after_failure
        self.preflight_count = 0
        self.overrides: dict[tuple[str, tuple[str, ...]], dict[str, Any]] = {}

    def __call__(
        self,
        command: Sequence[str],
        environment: dict[str, str],
        timeout: int,
    ) -> fresh.CompletedCommand:
        del environment, timeout
        call = tuple(command)
        self.calls.append(call)
        if call[1:3] == ("image", "inspect"):
            return fresh.CompletedCommand(0, (TOOL_IMAGE + "\n").encode(), b"")
        if call[1:3] in {("volume", "inspect"), ("network", "inspect")}:
            return fresh.CompletedCommand(0, b"[]\n", b"")
        if call[1:3] == ("container", "inspect"):
            return fresh.CompletedCommand(1, b"", b"not found")
        if call[1] == "ps":
            return fresh.CompletedCommand(0, b"", b"")
        assert call[1] == "compose"
        marker = call.index("-T")
        service = call[marker + 1]
        job_command = call[marker + 2 :]
        key = (service, job_command)
        if key in self.overrides:
            return fresh.CompletedCommand(0, json_bytes(self.overrides[key]), b"")
        if service.endswith("preflight"):
            self.preflight_count += 1
            proof = preflight(
                intent=self.intent_after_failure and self.preflight_count > 1
            )
            return fresh.CompletedCommand(0, json_bytes(proof), b"")
        if job_command == ("transport-proof",):
            proof = transport()
        elif job_command == ("prepare",):
            proof = prepare()
        elif job_command == ("prove-empty-authority",):
            proof = empty()
        elif job_command == ("validate",):
            proof = validate()
        elif job_command == ("prove-runtime-role",):
            proof = role()
        elif job_command == ("prove-authority-ready",):
            proof = ready()
        elif job_command == ("prove-local-import-acknowledged",):
            proof = acknowledgement()
        elif job_command == ("import-local", "--confirm-empty-authority"):
            if self.fail_import:
                return fresh.CompletedCommand(
                    1,
                    b"",
                    b"credential=must-never-enter-a-receipt",
                )
            return fresh.CompletedCommand(0, b"imported\n", b"")
        else:
            raise AssertionError(call)
        return fresh.CompletedCommand(0, json_bytes(proof), b"")


class FakeLeaseAuthority:
    def __init__(self):
        self.released = False
        self.lease = fresh.MutationLease(
            actor="install-linking-recovery",
            token="e" * 64,
            token_sha256=hashlib.sha256(("e" * 64).encode()).hexdigest(),
            lock_path=Path("/tmp/test-public-edge-mutation.lock"),
            lock_device=1,
            lock_inode=2,
            token_device=1,
            token_inode=3,
            authorization_path=Path("/tmp/test-recovery.owner-token"),
            authorization_device=1,
            authorization_inode=4,
        )

    def acquire(self, **kwargs: Any) -> fresh.MutationLease:
        assert kwargs == {"actor": "install-linking-recovery"}
        return self.lease

    def release(self, lease: fresh.MutationLease) -> None:
        assert lease == self.lease
        self.released = True

    def load(self, path: Path) -> fresh.MutationLease:
        assert path.name == fresh.LEASE_FILE
        return self.lease


def write_file(path: Path, payload: bytes, mode: int) -> None:
    path.write_bytes(payload)
    path.chmod(mode)


def make_decision(tmp_path: Path, *, expires: datetime | None = None, **changes: Any) -> tuple[Path, str]:
    payload: dict[str, Any] = {
        "acknowledgements": {
            "existingAuthorityBackupUnavailable": True,
            "newAuthorityIdentityAndHistoryAccepted": True,
            "portalAndTunnelRemainStopped": True,
            "retainedLocalMirrorIsSoleSeedAccepted": True,
        },
        "approvedAtUtc": "2026-08-23T11:55:00Z",
        "contractName": fresh.DECISION_CONTRACT,
        "decision": "approve_new_authority_and_history_reset",
        "expiresAtUtc": (expires or NOW + timedelta(hours=2)).isoformat().replace(
            "+00:00", "Z"
        ),
        "newAuthorityIdentitySha256": NEW_IDENTITY,
        "oldAuthorityIdentitySha256": OLD_IDENTITY,
        "oldAuthorityStateSha256": OLD_STATE,
        "oldCommitCount": 13,
        "oldHeadGeneration": 13,
        "recoveryId": "fresh-recovery-test",
        "stateVolumeName": "chummer6-hub_chummer-run-api-state",
        "status": "approved",
        "toolImageId": TOOL_IMAGE,
    }
    payload.update(changes)
    path = tmp_path / "operator-decision.json"
    data = json_bytes(payload)
    write_file(path, data, 0o400)
    return path, hashlib.sha256(data).hexdigest()


def make_inputs(tmp_path: Path, *, mutate: bool, decision_changes: dict[str, Any] | None = None) -> fresh.RecoveryInputs:
    env_file = tmp_path / "recovery.env"
    compose_file = tmp_path / "recovery-compose.yml"
    write_file(env_file, b"SAFE_PATHS_ONLY=1\n", 0o600)
    write_file(compose_file, b"services: {}\n", 0o644)
    decision_path: Path | None = None
    decision_sha: str | None = None
    if mutate:
        decision_path, decision_sha = make_decision(
            tmp_path,
            **(decision_changes or {}),
        )
    return fresh.RecoveryInputs(
        recovery_id="fresh-recovery-test",
        receipt_root=tmp_path / "receipts",
        compose_file=compose_file,
        env_file=env_file,
        project_name="install-linking-fresh-recovery-test",
        tool_image_id=TOOL_IMAGE,
        state_volume_name="chummer6-hub_chummer-run-api-state",
        network_name="chummer6-hub_public-origin",
        expected_new_authority_identity_sha256=NEW_IDENTITY if mutate else None,
        expected_old_authority_identity_sha256=OLD_IDENTITY if mutate else None,
        expected_old_authority_state_sha256=OLD_STATE if mutate else None,
        expected_old_head_generation=13 if mutate else None,
        expected_old_commit_count=13 if mutate else None,
        decision_receipt=decision_path,
        decision_receipt_sha256=decision_sha,
        mutate=mutate,
        resume_unknown=False,
        stopped_container_names=("portal", "tunnel"),
    )


def controller(
    inputs: fresh.RecoveryInputs,
    executor: FakeExecutor,
    leases: FakeLeaseAuthority | None = None,
) -> fresh.RecoveryController:
    leases = leases or FakeLeaseAuthority()
    return fresh.RecoveryController(
        inputs,
        executor=executor,
        clock=lambda: NOW,
        acquire_lease=leases.acquire,
        release_lease=leases.release,
        load_lease=leases.load,
    )


def compose_job_commands(executor: FakeExecutor) -> list[tuple[str, ...]]:
    result = []
    for call in executor.calls:
        if len(call) > 1 and call[1] == "compose":
            marker = call.index("-T")
            result.append(call[marker + 2 :])
    return result


def test_default_lane_is_only_read_only_local_preflight(tmp_path: Path) -> None:
    executor = FakeExecutor()
    inputs = make_inputs(tmp_path, mutate=False)

    output = controller(inputs, executor).run()

    assert output.name == fresh.PREFLIGHT_FILE
    assert compose_job_commands(executor) == [("preflight-local-recovery",)]
    receipt = json.loads(output.read_text())
    assert receipt["status"] == "pass"
    assert receipt["dataProtectionReady"] is True
    assert receipt["floorGeneration"] == 13


@pytest.mark.parametrize(
    "proof_change",
    [
        {"localStorePresent": False},
        {"dataProtectionReady": False},
        {"floorPresent": False, "floorGeneration": None, "floorSnapshotSha256": None},
        {"sourceGeneration": 12, "floorGeneration": 13},
        {"sourceSnapshotSha256": "not-a-digest"},
    ],
)
def test_preflight_refuses_missing_undecryptable_unsafe_or_behind_floor_state(
    tmp_path: Path,
    proof_change: dict[str, Any],
) -> None:
    executor = FakeExecutor()
    bad = preflight()
    bad.update(proof_change)
    executor.overrides[
        ("install-linking-fresh-recovery-preflight", ("preflight-local-recovery",))
    ] = bad

    with pytest.raises(fresh.RecoveryError):
        controller(make_inputs(tmp_path, mutate=False), executor).run()

    assert compose_job_commands(executor) == [("preflight-local-recovery",)]


@pytest.mark.parametrize(
    "decision_change",
    [
        {"status": "draft"},
        {"decision": "approve_something_else"},
        {"oldHeadGeneration": 12},
        {"newAuthorityIdentitySha256": "9" * 64},
        {
            "acknowledgements": {
                "existingAuthorityBackupUnavailable": True,
                "newAuthorityIdentityAndHistoryAccepted": False,
                "portalAndTunnelRemainStopped": True,
                "retainedLocalMirrorIsSoleSeedAccepted": True,
            }
        },
        {"expiresAtUtc": "2026-08-23T11:59:00Z"},
    ],
)
def test_mutation_refuses_incomplete_mismatched_or_expired_decision_before_db_jobs(
    tmp_path: Path,
    decision_change: dict[str, Any],
) -> None:
    executor = FakeExecutor()

    with pytest.raises(fresh.RecoveryError):
        controller(
            make_inputs(tmp_path, mutate=True, decision_changes=decision_change),
            executor,
        ).run()

    assert compose_job_commands(executor) == [("preflight-local-recovery",)]


def test_mutation_requires_owner_read_only_decision_and_external_digest(tmp_path: Path) -> None:
    inputs = make_inputs(tmp_path, mutate=True)
    assert inputs.decision_receipt is not None
    inputs.decision_receipt.chmod(0o600)
    with pytest.raises(fresh.RecoveryError, match="unsafe metadata"):
        controller(inputs, FakeExecutor()).run()

    inputs.decision_receipt.chmod(0o400)
    inputs = fresh.RecoveryInputs(
        **{
            **inputs.__dict__,
            "decision_receipt_sha256": "0" * 64,
            "receipt_root": tmp_path / "other-receipts",
        }
    )
    with pytest.raises(fresh.RecoveryError, match="external pin"):
        controller(inputs, FakeExecutor()).run()


def test_positive_mutation_proves_empty_imports_once_and_proves_exact_seed(tmp_path: Path) -> None:
    executor = FakeExecutor()
    leases = FakeLeaseAuthority()

    output = controller(make_inputs(tmp_path, mutate=True), executor, leases).run()

    assert output.name == fresh.RECOVERY_FILE
    assert compose_job_commands(executor) == [
        ("preflight-local-recovery",),
        ("transport-proof",),
        ("prepare",),
        ("prove-empty-authority",),
        ("import-local", "--confirm-empty-authority"),
        ("transport-proof",),
        ("validate",),
        ("prove-runtime-role",),
        ("prove-authority-ready",),
        ("prove-local-import-acknowledged",),
    ]
    receipt = json.loads(output.read_text())
    assert receipt["status"] == "pass"
    assert receipt["normalCutoverRemainsSeededOnly"] is True
    assert receipt["postImportProof"]["authority"]["headGeneration"] == 1
    assert receipt["postImportProof"]["authority"]["commitCount"] == 1
    assert receipt["postImportProof"]["acknowledgement"]["localAcknowledged"] is True
    assert leases.released is True
    lease = json.loads((inputs_root := output.parent / fresh.LEASE_FILE).read_text())
    assert lease["status"] == "released"
    assert stat.S_IMODE(inputs_root.stat().st_mode) == 0o600


def test_nonempty_preimport_authority_is_refused_before_import(tmp_path: Path) -> None:
    executor = FakeExecutor()
    not_empty = empty()
    not_empty.update(empty=False, headGeneration=1, commitCount=1)
    executor.overrides[
        ("install-linking-fresh-recovery-runtime-proof", ("prove-empty-authority",))
    ] = not_empty

    with pytest.raises(fresh.AmbiguousRecoveryError):
        controller(make_inputs(tmp_path, mutate=True), executor).run()

    assert ("import-local", "--confirm-empty-authority") not in compose_job_commands(executor)
    receipt = json.loads((tmp_path / "receipts" / fresh.RECOVERY_FILE).read_text())
    assert receipt["status"] == "unknown"


@pytest.mark.parametrize(
    "bad_ready",
    [ready(generation=0), ready(generation=2), {**ready(), "empty": True}],
)
def test_post_import_requires_nonempty_generation_one_commit_one(
    tmp_path: Path,
    bad_ready: dict[str, Any],
) -> None:
    executor = FakeExecutor()
    executor.overrides[
        ("install-linking-fresh-recovery-runtime-proof", ("prove-authority-ready",))
    ] = bad_ready

    with pytest.raises(fresh.AmbiguousRecoveryError):
        controller(make_inputs(tmp_path, mutate=True), executor).run()

    receipt = json.loads((tmp_path / "receipts" / fresh.RECOVERY_FILE).read_text())
    assert receipt["status"] == "unknown"


def test_import_ambiguity_retains_only_exact_intent_digest_and_never_stderr(
    tmp_path: Path,
) -> None:
    executor = FakeExecutor(fail_import=True, intent_after_failure=True)
    leases = FakeLeaseAuthority()

    with pytest.raises(fresh.AmbiguousRecoveryError):
        controller(make_inputs(tmp_path, mutate=True), executor, leases).run()

    receipt_path = tmp_path / "receipts" / fresh.RECOVERY_FILE
    text = receipt_path.read_text()
    receipt = json.loads(text)
    assert receipt["status"] == "unknown"
    assert receipt["retainedImportIntentSha256"] == "2" * 64
    assert "must-never-enter-a-receipt" not in text
    assert leases.released is False
    assert json.loads((receipt_path.parent / fresh.LEASE_FILE).read_text())["status"] == "active"


def test_local_acknowledgement_mismatch_is_unknown_and_fail_closed(tmp_path: Path) -> None:
    executor = FakeExecutor()
    bad = acknowledgement()
    bad["floorSnapshotSha256"] = "9" * 64
    executor.overrides[
        (
            "install-linking-fresh-recovery-acknowledgement",
            ("prove-local-import-acknowledged",),
        )
    ] = bad

    with pytest.raises(fresh.AmbiguousRecoveryError):
        controller(make_inputs(tmp_path, mutate=True), executor).run()


def test_normal_cutover_remains_seeded_only() -> None:
    runner = (ROOT / "scripts" / "run_install_linking_postgres_cutover.py").read_text()
    verifier = (ROOT / "scripts" / "verify_install_linking_cutover_boundary.py").read_text()
    assert '"import_not_required_seeded_authority"' in runner
    assert '"import-local"' not in runner
    assert '!= "not_required_seeded_authority"' in verifier


def test_cli_rejects_decision_inputs_without_unmistakable_confirmation(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        fresh.parse_args(
            [
                "--recovery-id",
                "test",
                "--receipt-root",
                str(tmp_path / "receipts"),
                "--env-file",
                str(tmp_path / "env"),
                "--project-name",
                "test",
                "--tool-image-id",
                TOOL_IMAGE,
                "--state-volume-name",
                "state",
                "--network-name",
                "network",
                "--operator-decision-receipt",
                str(tmp_path / "decision"),
            ]
        )
