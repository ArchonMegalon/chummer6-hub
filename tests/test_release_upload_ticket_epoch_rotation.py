from __future__ import annotations

from contextlib import nullcontext
from dataclasses import replace
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "rotate_release_upload_ticket_epoch.py"
DEPLOY = ROOT / "scripts" / "deploy_public_edge_portal.sh"
IMAGE_ID = "sha256:" + "1" * 64
OLD_PORTAL_ID = "a" * 64
NEW_PORTAL_ID = "b" * 64
PORTAL_NAME = "chummer-public-edge-candidate-epochtest"
PRIMARY_TUNNEL_ID = "c" * 64
REPLICA_TUNNEL_ID = "d" * 64
TUNNEL_IMAGE_ID = "sha256:" + "2" * 64
BINARY_SHA256 = "3" * 64
PROOF_BYTES = b"pinned-runtime-proof\n"
PROOF_SHA256 = hashlib.sha256(PROOF_BYTES).hexdigest()


def load_module():
    spec = importlib.util.spec_from_file_location(
        "release_upload_ticket_epoch_rotation_test",
        SCRIPT,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FakeRuntime:
    def __init__(self, module, *, old_epoch: str, new_epoch: str) -> None:
        self.module = module
        self.old_epoch = old_epoch
        self.new_epoch = new_epoch
        self.portal_id = OLD_PORTAL_ID
        self.portal_epoch = old_epoch
        self.direct_upload = "false"
        self.fail_recreate = False
        self.replace_state_volume_on_recreate = False
        self.old_ticket_http_status = 401
        self.old_ticket_proof_contract_valid = True
        self.old_ticket_proof_epoch = new_epoch
        self.state_volume_created_at = "2026-07-25T00:00:00Z"
        self.actions: list[object] = []

    def resolve_image_id(self, image_tag: str) -> str:
        self.actions.append(("resolve-image", image_tag))
        return IMAGE_ID

    def portal_container_ids(self) -> tuple[str, ...]:
        return (self.portal_id,)

    def inspect_portal(self, container_id: str):
        assert container_id == self.portal_id
        return self.module.PortalEvidence(
            container_id=self.portal_id,
            container_name=PORTAL_NAME,
            image_id=IMAGE_ID,
            running=True,
            health="healthy",
            restart_policy="unless-stopped",
            epoch_sha256=hashlib.sha256(
                self.portal_epoch.encode("utf-8")
            ).hexdigest(),
            binary_sha256=BINARY_SHA256,
            proof_authority_sha256=PROOF_SHA256,
            proof_public_sha256=PROOF_SHA256,
            state_volume=self.module.MountEvidence(
                "/app/state",
                self.module.EXPECTED_STATE_VOLUME,
                True,
            ),
            upload_session_volume=self.module.MountEvidence(
                self.module.EXPECTED_SESSION_ROOT,
                self.module.EXPECTED_SESSION_VOLUME,
                True,
            ),
            upload_session_root=self.module.EXPECTED_SESSION_ROOT,
            data_protection_root=self.module.EXPECTED_DATA_PROTECTION_ROOT,
            direct_bundle_upload_enabled=self.direct_upload,
            runtime_contract_sha256="6" * 64,
        )

    def tunnel_evidence(self):
        return (
            self.module.TunnelEvidence(
                "chummer-run-cloudflared",
                PRIMARY_TUNNEL_ID,
                TUNNEL_IMAGE_ID,
                True,
                "healthy",
            ),
            self.module.TunnelEvidence(
                "chummer-run-cloudflared-replica",
                REPLICA_TUNNEL_ID,
                TUNNEL_IMAGE_ID,
                True,
                "healthy",
            ),
        )

    def volume_evidence(self, name: str):
        created_at = (
            self.state_volume_created_at
            if name == self.module.EXPECTED_STATE_VOLUME
            else "2026-07-25T00:00:01Z"
        )
        return self.module.VolumeEvidence(
            name=name,
            driver="local",
            scope="local",
            mountpoint=f"/var/lib/docker/volumes/{name}/_data",
            created_at=created_at,
            options_sha256=hashlib.sha256(b"{}").hexdigest(),
            labels_sha256=hashlib.sha256(b"{}").hexdigest(),
        )

    def storage_probe(
        self,
        container_id: str,
        *,
        path: str,
        require_encrypted_keyring: bool,
    ):
        assert container_id == self.portal_id
        return self.module.StorageProbeEvidence(
            path=path,
            uid=1654,
            gid=1654,
            mode="700",
            key_file_count=1 if require_encrypted_keyring else 0,
            encrypted_key_file_count=1 if require_encrypted_keyring else 0,
        )

    def verify_loopback(self, container_id: str, route: str) -> str:
        self.actions.append(("loopback", container_id, route))
        return hashlib.sha256(f"{container_id}:{route}".encode()).hexdigest()

    def recreate_all_portals(
        self,
        *,
        prior_container_ids: tuple[str, ...],
        container_names: tuple[str, ...],
    ) -> None:
        self.actions.extend(
            [
                ("all-stopped", prior_container_ids),
                ("all-removed", prior_container_ids),
            ]
        )
        if self.fail_recreate:
            raise self.module.RotationError("injected_recreate_failure")
        assert container_names == (PORTAL_NAME,)
        self.portal_id = NEW_PORTAL_ID
        self.portal_epoch = self.new_epoch
        if self.replace_state_volume_on_recreate:
            self.state_volume_created_at = "2026-07-25T00:01:00Z"
        self.actions.append(("all-recreated", container_names))

    def public_get(self, path: str) -> tuple[int, str]:
        self.actions.append(("public-get", path))
        return 200, hashlib.sha256(path.encode()).hexdigest()

    def old_ticket_revocation_proof(
        self,
        ticket: str,
        nonce: str,
    ) -> tuple[int, tuple[tuple[str, str], ...], bytes]:
        self.actions.append(("old-ticket-proof", hashlib.sha256(ticket.encode()).hexdigest()))
        headers = (
            ("Content-Type", "application/json; charset=utf-8"),
            ("Cache-Control", "no-store"),
            ("Pragma", "no-cache"),
            ("Expires", "0"),
            ("WWW-Authenticate", "Bearer"),
        )
        if not self.old_ticket_proof_contract_valid:
            return self.old_ticket_http_status, headers, b'{"status":"unauthorized"}'
        body = json.dumps(
            {
                "contractName": (
                    "chummer.release-upload-ticket-revocation-proof/v1"
                ),
                "status": "pass",
                "ticketAccepted": self.old_ticket_http_status == 200,
                "nonceSha256": hashlib.sha256(nonce.encode("ascii")).hexdigest(),
                "revocationEpochSha256": hashlib.sha256(
                    self.old_ticket_proof_epoch.encode("utf-8")
                ).hexdigest(),
            },
            separators=(",", ":"),
        ).encode("utf-8")
        return self.old_ticket_http_status, headers, body


@pytest.fixture
def rotation_fixture(tmp_path: Path):
    module = load_module()
    module.overlay.public_edge_mutation_lock = lambda **_kwargs: nullcontext()
    root = tmp_path / "private"
    root.mkdir(mode=0o700)
    root.chmod(0o700)
    old_epoch = "epoch-before"
    new_epoch = "epoch-after"
    env_file = root / ".env"
    env_file.write_text(
        f"{module.EPOCH_KEY}={old_epoch}\n"
        "UNRELATED_SECRET=must-never-enter-receipt\n",
        encoding="utf-8",
    )
    env_file.chmod(0o600)
    active_runtime = root / "active-runtime-authority.json"
    active_runtime.write_text(
        json.dumps(
            {
                "contractName": "chummer.public-edge.active-runtime-authority/v1",
                "generatedAtUtc": "2026-07-25T00:00:00Z",
                "installLinkingAuthorityReadinessPath": str(
                    root / "readiness.json"
                ),
                "installLinkingAuthorityReadinessSha256": "5" * 64,
                "portal": {
                    "containerId": OLD_PORTAL_ID,
                    "containerName": PORTAL_NAME,
                    "existed": True,
                    "imageId": IMAGE_ID,
                    "proofAuthorityMountSha256": PROOF_SHA256,
                    "proofPublicMountSha256": PROOF_SHA256,
                    "wasRunning": True,
                },
                "status": "pass",
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    active_runtime.chmod(0o600)
    ticket_file = root / "old-ticket"
    ticket_file.write_text("hidden-old-ticket\n", encoding="ascii")
    ticket_file.chmod(0o600)
    proof_file = root / "HUB_LOCAL_RELEASE_PROOF.generated.json"
    proof_file.write_bytes(PROOF_BYTES)
    proof_file.chmod(0o600)
    expected_proof_sha256 = hashlib.sha256(proof_file.read_bytes()).hexdigest()
    assert expected_proof_sha256 == PROOF_SHA256
    request = module.RotationRequest(
        env_file=env_file,
        active_runtime_authority=active_runtime,
        output=root / "rotation.json",
        expected_env_sha256_before=hashlib.sha256(env_file.read_bytes()).hexdigest(),
        expected_image_id=IMAGE_ID,
        expected_proof_sha256=expected_proof_sha256,
        image_tag="chummer-run-api:local",
        expected_source_head="6" * 40,
        new_epoch=new_epoch,
        expected_portal_replicas=1,
        shared_mutation_lock_token="7" * 64,
        old_ticket_path=ticket_file,
        old_ticket_sha256=hashlib.sha256(ticket_file.read_bytes()).hexdigest(),
        proof_bind_source=proof_file,
        expected_existing_receipt_sha256="",
        epoch_authority_output=root / "release-upload-ticket-epoch-authority.json",
    )
    runtime = FakeRuntime(module, old_epoch=old_epoch, new_epoch=new_epoch)
    return module, request, runtime


def test_rotation_is_atomic_secret_free_and_updates_runtime_authority(
    rotation_fixture,
) -> None:
    module, request, runtime = rotation_fixture

    status, receipt = module.run_rotation(request, runtime)

    assert status == 0
    assert receipt["status"] == "pass"
    assert receipt["phase"] == "post_rotation_verified"
    assert receipt["oldTicketRevocationProof"]["httpStatus"] == 401
    assert receipt["oldTicketRevocationProof"]["contractName"] == (
        "chummer.release-upload-ticket-revocation-proof/v1"
    )
    assert receipt["oldTicketRevocationProof"]["revocationEpochSha256"] == (
        hashlib.sha256(request.new_epoch.encode("utf-8")).hexdigest()
    )
    assert receipt["edgeWaf"] == {
        "mutationAuthorized": False,
        "mutationPerformed": False,
        "preservedThroughPostVerification": True,
    }
    assert module.parse_epoch_environment(request.env_file.read_bytes())[0] == (
        request.new_epoch
    )
    assert runtime.actions.index(("all-stopped", (OLD_PORTAL_ID,))) < (
        runtime.actions.index(("all-recreated", (PORTAL_NAME,)))
    )
    raw_receipt = request.output.read_text(encoding="utf-8")
    assert "must-never-enter-receipt" not in raw_receipt
    assert "hidden-old-ticket" not in raw_receipt
    assert request.output.stat().st_mode & 0o777 == 0o600
    active = json.loads(
        request.active_runtime_authority.read_text(encoding="utf-8")
    )
    assert active["portal"]["containerId"] == NEW_PORTAL_ID
    assert active["portal"]["imageId"] == IMAGE_ID
    epoch_authority = json.loads(
        request.epoch_authority_output.read_text(encoding="utf-8")
    )
    assert epoch_authority["status"] == "pass"
    assert epoch_authority["portalContainerId"] == NEW_PORTAL_ID
    assert epoch_authority["rotationReceiptSha256"] == hashlib.sha256(
        request.output.read_bytes()
    ).hexdigest()
    assert request.epoch_authority_output.stat().st_mode & 0o777 == 0o600


def test_post_commit_failure_never_restores_old_epoch_and_is_resumable(
    rotation_fixture,
) -> None:
    module, request, runtime = rotation_fixture
    runtime.fail_recreate = True

    status, failed = module.run_rotation(request, runtime)

    assert status == 76
    assert failed["status"] == "fail_forward_required"
    assert module.parse_epoch_environment(request.env_file.read_bytes())[0] == (
        request.new_epoch
    )
    assert json.loads(
        request.active_runtime_authority.read_text(encoding="utf-8")
    )["portal"]["containerId"] == OLD_PORTAL_ID

    runtime.fail_recreate = False
    resumed_request = replace(
        request,
        expected_existing_receipt_sha256=hashlib.sha256(
            request.output.read_bytes()
        ).hexdigest(),
    )
    status, recovered = module.run_rotation(resumed_request, runtime)
    assert status == 0
    assert recovered["status"] == "pass"
    assert module.parse_epoch_environment(request.env_file.read_bytes())[0] == (
        request.new_epoch
    )


def test_commit_window_exception_is_fail_forward_and_retains_new_epoch(
    rotation_fixture,
) -> None:
    module, request, runtime = rotation_fixture
    commit_epoch = module.replace_epoch_environment

    def commit_then_fail(**kwargs):
        commit_epoch(**kwargs)
        raise module.RotationError("injected_postreplace_failure")

    module.replace_epoch_environment = commit_then_fail

    status, receipt = module.run_rotation(request, runtime)

    assert status == 76
    assert receipt["status"] == "fail_forward_required"
    assert receipt["phase"] == "epoch_commit_outcome_uncertain"
    assert receipt["failureCode"] == "injected_postreplace_failure"
    committed = request.env_file.read_bytes()
    assert module.parse_epoch_environment(committed)[0] == request.new_epoch
    assert receipt["environmentSha256After"] == hashlib.sha256(
        committed
    ).hexdigest()


def test_committed_resume_rejects_static_active_authority_substitution(
    rotation_fixture,
) -> None:
    module, request, runtime = rotation_fixture
    runtime.fail_recreate = True
    status, _failed = module.run_rotation(request, runtime)
    assert status == 76

    active = json.loads(
        request.active_runtime_authority.read_text(encoding="utf-8")
    )
    active["installLinkingAuthorityReadinessPath"] = (
        "/private/substituted-readiness.json"
    )
    active["installLinkingAuthorityReadinessSha256"] = "e" * 64
    request.active_runtime_authority.write_text(
        json.dumps(active, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    request.active_runtime_authority.chmod(0o600)

    runtime.fail_recreate = False
    resumed_request = replace(
        request,
        expected_existing_receipt_sha256=hashlib.sha256(
            request.output.read_bytes()
        ).hexdigest(),
    )
    status, resumed = module.run_rotation(resumed_request, runtime)

    assert status == 76
    assert resumed["failureCode"] == (
        "active_runtime_authority_static_contract_drift"
    )
    substituted = json.loads(
        request.active_runtime_authority.read_text(encoding="utf-8")
    )
    assert substituted["installLinkingAuthorityReadinessSha256"] == "e" * 64


def test_invalid_old_ticket_proof_fails_forward_without_leaking_ticket(
    rotation_fixture,
) -> None:
    module, request, runtime = rotation_fixture
    runtime.old_ticket_http_status = 200

    status, receipt = module.run_rotation(request, runtime)

    assert status == 76
    assert receipt["failureCode"] == "old_ticket_not_revoked"
    assert receipt["status"] == "fail_forward_required"
    assert "hidden-old-ticket" not in request.output.read_text(encoding="utf-8")
    assert receipt["edgeWaf"]["preservedThroughPostVerification"] is True
    assert json.loads(
        request.active_runtime_authority.read_text(encoding="utf-8")
    )["portal"]["containerId"] == NEW_PORTAL_ID
    assert module.parse_epoch_environment(request.env_file.read_bytes())[0] == (
        request.new_epoch
    )


def test_generic_unauthorized_response_is_not_revocation_proof(
    rotation_fixture,
) -> None:
    module, request, runtime = rotation_fixture
    runtime.old_ticket_proof_contract_valid = False

    status, receipt = module.run_rotation(request, runtime)

    assert status == 76
    assert receipt["failureCode"] == "old_ticket_revocation_proof_invalid"
    assert receipt["status"] == "fail_forward_required"
    assert "hidden-old-ticket" not in request.output.read_text(encoding="utf-8")
    assert module.parse_epoch_environment(request.env_file.read_bytes())[0] == (
        request.new_epoch
    )


def test_old_ticket_proof_must_bind_the_committed_epoch(
    rotation_fixture,
) -> None:
    module, request, runtime = rotation_fixture
    runtime.old_ticket_proof_epoch = runtime.old_epoch

    status, receipt = module.run_rotation(request, runtime)

    assert status == 76
    assert receipt["failureCode"] == "old_ticket_revocation_proof_invalid"
    assert module.parse_epoch_environment(request.env_file.read_bytes())[0] == (
        request.new_epoch
    )


def test_invalid_runtime_contract_fails_before_epoch_commit(
    rotation_fixture,
) -> None:
    module, request, runtime = rotation_fixture
    runtime.direct_upload = "true"

    status, receipt = module.run_rotation(request, runtime)

    assert status == 75
    assert receipt["status"] == "failed_before_epoch_commit"
    assert receipt["failureCode"] == "portal_runtime_contract_invalid"
    assert module.parse_epoch_environment(request.env_file.read_bytes())[0] == (
        runtime.old_epoch
    )


def test_same_name_volume_replacement_fails_forward(
    rotation_fixture,
) -> None:
    module, request, runtime = rotation_fixture
    runtime.replace_state_volume_on_recreate = True

    status, receipt = module.run_rotation(request, runtime)

    assert status == 76
    assert receipt["failureCode"] == "durable_storage_authority_drift"
    assert module.parse_epoch_environment(request.env_file.read_bytes())[0] == (
        request.new_epoch
    )


def test_resume_rejects_an_unpinned_existing_receipt(
    rotation_fixture,
) -> None:
    module, request, runtime = rotation_fixture
    runtime.fail_recreate = True

    status, _failed = module.run_rotation(request, runtime)
    assert status == 76

    runtime.fail_recreate = False
    with pytest.raises(
        module.RotationError,
        match="existing_receipt_sha256_mismatch",
    ):
        module.run_rotation(
            replace(request, expected_existing_receipt_sha256="f" * 64),
            runtime,
        )
    assert runtime.portal_id == OLD_PORTAL_ID


def test_unhandled_precommit_refusal_is_safe_to_unlock_without_a_receipt(
    rotation_fixture,
) -> None:
    module, request, _runtime = rotation_fixture
    assert not request.output.exists()

    assert module.classify_unhandled_failure(request) == 75
    assert not request.output.exists()

    same_epoch_request = replace(request, new_epoch=_runtime.old_epoch)
    assert module.classify_unhandled_failure(same_epoch_request) == 75
    with pytest.raises(
        module.RotationError,
        match="new_epoch_does_not_change_authority",
    ):
        module.run_rotation(same_epoch_request, _runtime)
    assert not request.output.exists()

    request.env_file.write_text(
        f"{module.EPOCH_KEY}={request.new_epoch}\n",
        encoding="utf-8",
    )
    request.env_file.chmod(0o600)
    assert module.classify_unhandled_failure(request) == 76


def test_active_authority_proof_drift_fails_before_epoch_commit(
    rotation_fixture,
) -> None:
    module, request, runtime = rotation_fixture
    active = json.loads(
        request.active_runtime_authority.read_text(encoding="utf-8")
    )
    active["portal"]["proofPublicMountSha256"] = "e" * 64
    request.active_runtime_authority.write_text(
        json.dumps(active, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    request.active_runtime_authority.chmod(0o600)

    status, receipt = module.run_rotation(request, runtime)

    assert status == 75
    assert receipt["failureCode"] == "active_runtime_authority_portal_mismatch"
    assert module.parse_epoch_environment(request.env_file.read_bytes())[0] == (
        runtime.old_epoch
    )


def test_deploy_invokes_rotation_only_after_irreversible_acceptance_and_cleanup() -> None:
    source = DEPLOY.read_text(encoding="utf-8")
    acceptance = source.rindex("deployment_transaction_active=0")
    cleanup = source.index(
        'docker_cli container rm "$prior_portal_container_id"',
        acceptance,
    )
    rotation = source.index(
        '"$SOURCE_ROOT/scripts/rotate_release_upload_ticket_epoch.py"',
        cleanup,
    )
    release = source.index("if ! release_deploy_lock; then", rotation)

    assert acceptance < cleanup < rotation < release
    assert "epoch_rotation_fail_forward_required=1" in source[cleanup:release]
    assert "--expected-portal-replicas 1" in source[rotation:release]
    assert "--active-runtime-authority" in source[rotation:release]
    assert "--epoch-authority-output" in source[rotation:release]
    assert "--expected-proof-sha256" in source[rotation:release]
    assert "--shared-mutation-lock-fd 0" in source[rotation:release]
    assert "--shared-mutation-lock-token" not in source[rotation:release]
    assert "75)" in source[rotation:release]
    assert "epoch_rotation_fail_forward_required=0" in source[rotation:release]
    assert "epoch_rotation_precommit_refused=1" in source[rotation:release]
    assert "WAF" not in source[rotation:release]
    rotation_source = SCRIPT.read_text(encoding="utf-8")
    assert '"--pull",\n                "never"' in rotation_source
    assert '"--build"' not in rotation_source


def test_resume_is_a_dedicated_pinned_fail_forward_path_without_build() -> None:
    source = DEPLOY.read_text(encoding="utf-8")
    resume = source.index(
        'if ((RELEASE_UPLOAD_TICKET_EPOCH_ROTATION_RESUME == 1)); then\n'
        '  if ! trusted_source_python "$COMPOSE_SOURCE_ATTESTOR" verify'
    )
    ordinary_capture = source.index(
        'if ! trusted_source_python "$COMPOSE_SOURCE_ATTESTOR" capture',
        resume,
    )
    resume_source = source[resume:ordinary_capture]

    assert "--expected-existing-receipt-sha256" in resume_source
    assert "--expected-env-sha256-before" in resume_source
    assert "--expected-image-id" in resume_source
    assert "--expected-proof-sha256" in resume_source
    assert "--epoch-authority-output" in resume_source
    assert "--shared-mutation-lock-fd 0" in resume_source
    assert "epoch_rotation_fail_forward_required=0" in resume_source
    assert "release_deploy_lock" in resume_source
    assert "buildx build" not in resume_source
    assert "--source-replay-preflight" not in resume_source
    assert "exit 0" in resume_source
