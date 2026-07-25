from __future__ import annotations

from contextlib import nullcontext
from dataclasses import replace
import hashlib
import importlib.util
import json
import os
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


def materialize_ticket_authority(
    module,
    *,
    authority_path: Path,
    ticket_path: Path,
    ticket_payload: bytes,
):
    payload = {
        "contractName": (
            "chummer.release-upload-incident-ticket-"
            "materialization-authority/v1"
        ),
        "generatedAtUtc": "2026-07-26T00:00:00Z",
        "status": "materialized_pending_revocation",
        "ticketPathSha256": hashlib.sha256(
            str(ticket_path).encode("utf-8")
        ).hexdigest(),
        "ticketSha256": hashlib.sha256(ticket_payload).hexdigest(),
        "ticketSizeBytes": len(ticket_payload),
        "envelopeSha256": "8" * 64,
        "inventoryCommitmentSha256": "9" * 64,
        "recipientCertificateSha256": "a" * 64,
        "signerCertificateSha256": "b" * 64,
        "opensslExecutableSha256": "c" * 64,
        "materializationOpensslExecutableSha256": "e" * 64,
        "materializationTransactionId": "d" * 32,
        "quarantineStatus": "pending",
        "revocationStatus": "pending",
    }
    authority_path.write_bytes(
        (
            json.dumps(
                payload,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
    )
    authority_path.chmod(0o600)
    descriptor = os.open(authority_path, os.O_RDONLY)
    return module.read_old_ticket_authority(descriptor)


class FakeRuntime:
    def __init__(self, module, *, old_epoch: str, new_epoch: str) -> None:
        self.module = module
        self.old_epoch = old_epoch
        self.new_epoch = new_epoch
        self.portal_id = OLD_PORTAL_ID
        self.portal_epoch = old_epoch
        self.portal_running = True
        self.direct_upload = "false"
        self.fail_recreate = False
        self.fail_quiesce_after_stop = False
        self.fail_restart = False
        self.fail_restart_health = False
        self.portal_health_override = ""
        self.block_requiesce_after_restart = False
        self.hide_project_enumeration = False
        self.hide_independent_enumeration = False
        self.rogue_portal_id = "e" * 64
        self.rogue_portal_exists = False
        self.rogue_portal_running = False
        self.fail_connector_quiesce = False
        self.connectors_running = True
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
        if self.hide_project_enumeration and any(
            action[0] == "restart" for action in self.actions
        ):
            return ()
        return (self.portal_id,)

    def independently_enumerated_portal_container_ids(
        self,
    ) -> tuple[str, ...]:
        if self.hide_independent_enumeration and any(
            action[0] == "restart" for action in self.actions
        ):
            return ()
        identities = [self.portal_id]
        if self.rogue_portal_exists:
            identities.append(self.rogue_portal_id)
        return tuple(identities)

    def inspect_portal(self, container_id: str):
        assert container_id == self.portal_id
        return self.module.PortalEvidence(
            container_id=self.portal_id,
            container_name=PORTAL_NAME,
            image_id=IMAGE_ID,
            running=self.portal_running,
            health=(
                self.portal_health_override
                or ("healthy" if self.portal_running else "none")
            ),
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
        assert self.portal_running
        self.actions.append(("loopback", container_id, route))
        return hashlib.sha256(f"{container_id}:{route}".encode()).hexdigest()

    def assert_portals_stopped(
        self,
        container_ids: tuple[str, ...],
    ) -> None:
        assert container_ids == (self.portal_id,)
        self.actions.append(("assert-stopped", container_ids))
        if self.portal_running:
            raise self.module.RotationError("portal_quiescence_not_proven")

    def assert_known_portals_stopped(
        self,
        container_ids: tuple[str, ...],
    ) -> None:
        self.actions.append(("assert-known-stopped", container_ids))
        if self.portal_id in container_ids and self.portal_running:
            raise self.module.RotationError(
                "known_portal_quiescence_not_proven"
            )
        if (
            self.rogue_portal_id in container_ids
            and self.rogue_portal_running
        ):
            raise self.module.RotationError(
                "known_portal_quiescence_not_proven"
            )

    def quiesce_known_portals(
        self,
        container_ids: tuple[str, ...],
    ) -> None:
        self.actions.append(("quiesce-known", container_ids))
        if self.block_requiesce_after_restart:
            raise self.module.RotationError("injected_requiesce_blocked")
        if self.portal_id in container_ids:
            self.portal_running = False
        if self.rogue_portal_id in container_ids:
            self.rogue_portal_running = False
        self.assert_known_portals_stopped(container_ids)

    def quiesce_portals(self, container_ids: tuple[str, ...]) -> None:
        assert container_ids == (self.portal_id,)
        self.actions.append(("quiesce", container_ids))
        if (
            self.block_requiesce_after_restart
            and any(action[0] == "restart" for action in self.actions)
        ):
            raise self.module.RotationError("injected_requiesce_blocked")
        self.portal_running = False
        if self.fail_quiesce_after_stop:
            raise self.module.RotationError("injected_quiesce_failure")
        self.assert_portals_stopped(container_ids)

    def restart_portals(self, container_ids: tuple[str, ...]) -> None:
        assert container_ids == (self.portal_id,)
        self.actions.append(("restart", container_ids))
        if self.fail_restart:
            raise self.module.RotationError("injected_restart_failure")
        self.portal_running = True
        if self.fail_restart_health:
            self.portal_health_override = "unhealthy"

    def quiesce_public_connectors(self) -> None:
        self.actions.append(("connectors-quiesce",))
        if self.fail_connector_quiesce:
            raise self.module.RotationError(
                "injected_connector_quiesce_failure"
            )
        self.connectors_running = False

    def assert_public_connectors_stopped(self) -> None:
        self.actions.append(("connectors-assert-stopped",))
        if self.connectors_running:
            raise self.module.RotationError(
                "public_connector_quiescence_not_proven"
            )

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
        self.portal_running = True
        self.portal_health_override = ""
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
    ticket_authority = materialize_ticket_authority(
        module,
        authority_path=root / "old-ticket-authority.json",
        ticket_path=ticket_file,
        ticket_payload=ticket_file.read_bytes(),
    )
    proof_file = root / "HUB_LOCAL_RELEASE_PROOF.generated.json"
    proof_file.write_bytes(PROOF_BYTES)
    proof_file.chmod(0o600)
    expected_proof_sha256 = hashlib.sha256(proof_file.read_bytes()).hexdigest()
    assert expected_proof_sha256 == PROOF_SHA256
    bootstrap_authority = root / "epoch-history-bootstrap-authority.json"
    bootstrap_authority.write_text(
        json.dumps(
            {
                "contractName": (
                    "chummer.release-upload-ticket-epoch-history-"
                    "bootstrap-authority/v1"
                ),
                "status": "approved",
                "generatedAtUtc": "2026-07-25T00:00:00Z",
                "knownLegacyEpochSha256": [
                    hashlib.sha256(old_epoch.encode("utf-8")).hexdigest()
                ],
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    bootstrap_authority.chmod(0o600)
    waf_local_evidence = root / "edge-waf-local-evidence.json"
    waf_local_evidence.write_text(
        '{"ruleset":"pinned-release-upload-containment"}\n',
        encoding="utf-8",
    )
    waf_local_evidence.chmod(0o600)
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
        old_ticket_authority=ticket_authority,
        proof_bind_source=proof_file,
        expected_existing_receipt_sha256="",
        epoch_authority_output=root / "release-upload-ticket-epoch-authority.json",
        epoch_history_path=root / "release-upload-ticket-epoch-history.json",
        expected_epoch_history_sha256="absent",
        epoch_history_bootstrap_authority=bootstrap_authority,
        expected_epoch_history_bootstrap_authority_sha256=hashlib.sha256(
            bootstrap_authority.read_bytes()
        ).hexdigest(),
        epoch_history_bootstrap_marker=(
            root / "release-upload-ticket-epoch-bootstrap-marker.json"
        ),
        expected_epoch_history_bootstrap_marker_sha256="absent",
        edge_waf_local_evidence_source=waf_local_evidence,
        expected_edge_waf_local_evidence_sha256=hashlib.sha256(
            waf_local_evidence.read_bytes()
        ).hexdigest(),
    )
    runtime = FakeRuntime(module, old_epoch=old_epoch, new_epoch=new_epoch)
    return module, request, runtime


def pinned_resume_request(request):
    history_sha256 = (
        hashlib.sha256(request.epoch_history_path.read_bytes()).hexdigest()
        if request.epoch_history_path.exists()
        else "absent"
    )
    return replace(
        request,
        expected_existing_receipt_sha256=hashlib.sha256(
            request.output.read_bytes()
        ).hexdigest(),
        expected_epoch_history_sha256=history_sha256,
        expected_epoch_history_bootstrap_marker_sha256=(
            hashlib.sha256(
                request.epoch_history_bootstrap_marker.read_bytes()
            ).hexdigest()
            if request.epoch_history_bootstrap_marker.exists()
            else "absent"
        ),
    )


def test_rotation_is_atomic_secret_free_and_updates_runtime_authority(
    rotation_fixture,
) -> None:
    module, request, runtime = rotation_fixture
    commit_epoch = module.replace_epoch_environment

    def observed_commit(**kwargs):
        runtime.actions.append(("environment-commit", runtime.portal_running))
        assert runtime.portal_running is False
        return commit_epoch(**kwargs)

    module.replace_epoch_environment = observed_commit

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
    assert receipt["edgeWafLocalEvidence"] == {
        "evidenceScope": "pinned_local_evidence_only",
        "mutationAuthorized": False,
        "mutationPerformed": False,
        "stableThroughPostVerification": True,
        "sha256Before": (
            request.expected_edge_waf_local_evidence_sha256
        ),
        "sha256After": (
            request.expected_edge_waf_local_evidence_sha256
        ),
        "liveControlPlaneVerified": False,
    }
    assert module.parse_epoch_environment(request.env_file.read_bytes())[0] == (
        request.new_epoch
    )
    assert runtime.actions.index(("all-stopped", (OLD_PORTAL_ID,))) < (
        runtime.actions.index(("all-recreated", (PORTAL_NAME,)))
    )
    quiesce_index = runtime.actions.index(("quiesce", (OLD_PORTAL_ID,)))
    commit_index = runtime.actions.index(("environment-commit", False))
    recreate_index = runtime.actions.index(("all-recreated", (PORTAL_NAME,)))
    assert quiesce_index < commit_index < recreate_index
    raw_receipt = request.output.read_text(encoding="utf-8")
    assert "must-never-enter-receipt" not in raw_receipt
    assert "hidden-old-ticket" not in raw_receipt
    assert request.old_ticket_authority.ticket_sha256 not in raw_receipt
    assert str(request.old_ticket_path) not in raw_receipt
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
    assert epoch_authority["edgeWafLocalEvidenceSha256"] == (
        request.expected_edge_waf_local_evidence_sha256
    )
    assert (
        epoch_authority[
            "edgeWafLocalEvidenceStableThroughPostVerification"
        ]
        is True
    )
    assert epoch_authority["edgeWafLiveControlPlaneVerified"] is False
    assert request.epoch_authority_output.stat().st_mode & 0o777 == 0o600
    history = json.loads(
        request.epoch_history_path.read_text(encoding="utf-8")
    )
    assert [
        event["eventType"] for event in history["events"]
    ] == [
        "legacy_observed",
        "rotation_reserved",
        "rotation_committed",
    ]
    assert history["events"][0]["epochSha256"] == hashlib.sha256(
        runtime.old_epoch.encode("utf-8")
    ).hexdigest()
    assert history["events"][1]["epochSha256"] == hashlib.sha256(
        request.new_epoch.encode("utf-8")
    ).hexdigest()
    assert request.epoch_history_path.stat().st_mode & 0o777 == 0o600
    assert epoch_authority["epochHistorySha256"] == hashlib.sha256(
        request.epoch_history_path.read_bytes()
    ).hexdigest()


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
    resumed_request = pinned_resume_request(request)
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
    assert runtime.portal_running is False
    assert runtime.actions.index(("quiesce", (OLD_PORTAL_ID,))) < (
        runtime.actions.index(("all-recreated", (PORTAL_NAME,)))
        if ("all-recreated", (PORTAL_NAME,)) in runtime.actions
        else len(runtime.actions)
    )


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
    resumed_request = pinned_resume_request(request)
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
    assert (
        receipt["edgeWafLocalEvidence"][
            "stableThroughPostVerification"
        ]
        is True
    )
    assert (
        receipt["edgeWafLocalEvidence"]["liveControlPlaneVerified"]
        is False
    )
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


def test_epoch_history_permanently_rejects_a_b_a_reuse(
    rotation_fixture,
) -> None:
    module, request, runtime = rotation_fixture
    status, _receipt = module.run_rotation(request, runtime)
    assert status == 0

    actions_before = list(runtime.actions)
    second_output = request.output.with_name("rotation-back-to-a.json")
    back_to_a = replace(
        request,
        output=second_output,
        expected_env_sha256_before=hashlib.sha256(
            request.env_file.read_bytes()
        ).hexdigest(),
        new_epoch=runtime.old_epoch,
        expected_epoch_history_sha256=hashlib.sha256(
            request.epoch_history_path.read_bytes()
        ).hexdigest(),
        expected_existing_receipt_sha256="",
        expected_epoch_history_bootstrap_marker_sha256=hashlib.sha256(
            request.epoch_history_bootstrap_marker.read_bytes()
        ).hexdigest(),
    )

    status, refused = module.run_rotation(back_to_a, runtime)

    assert status == 75
    assert refused["failureCode"] == "epoch_history_epoch_reused"
    assert runtime.actions == actions_before + [
        ("resolve-image", "chummer-run-api:local")
    ]
    assert runtime.portal_running is True
    assert module.parse_epoch_environment(request.env_file.read_bytes())[0] == (
        request.new_epoch
    )


def test_deleted_history_cannot_reset_bootstrap_or_reuse_a(
    rotation_fixture,
) -> None:
    module, request, runtime = rotation_fixture
    status, _receipt = module.run_rotation(request, runtime)
    assert status == 0
    request.epoch_history_path.unlink()
    actions_before = list(runtime.actions)
    reset = replace(
        request,
        output=request.output.with_name("rotation-reset-to-a.json"),
        expected_env_sha256_before=hashlib.sha256(
            request.env_file.read_bytes()
        ).hexdigest(),
        new_epoch=runtime.old_epoch,
        expected_existing_receipt_sha256="",
        expected_epoch_history_sha256="absent",
        expected_epoch_history_bootstrap_marker_sha256=hashlib.sha256(
            request.epoch_history_bootstrap_marker.read_bytes()
        ).hexdigest(),
    )

    status, refused = module.run_rotation(reset, runtime)

    assert status == 75
    assert refused["failureCode"] == "epoch_history_missing_after_bootstrap"
    assert runtime.actions == actions_before + [
        ("resolve-image", "chummer-run-api:local")
    ]
    assert runtime.portal_running is True
    assert module.parse_epoch_environment(request.env_file.read_bytes())[0] == (
        request.new_epoch
    )


def test_bootstrap_imports_every_pinned_known_legacy_epoch(
    rotation_fixture,
) -> None:
    module, request, runtime = rotation_fixture
    prior_legacy_sha256 = hashlib.sha256(
        b"legacy-before-observed-a"
    ).hexdigest()
    authority = json.loads(
        request.epoch_history_bootstrap_authority.read_text(
            encoding="utf-8"
        )
    )
    authority["knownLegacyEpochSha256"].insert(0, prior_legacy_sha256)
    request.epoch_history_bootstrap_authority.write_text(
        json.dumps(authority, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    request.epoch_history_bootstrap_authority.chmod(0o600)
    imported = replace(
        request,
        expected_epoch_history_bootstrap_authority_sha256=hashlib.sha256(
            request.epoch_history_bootstrap_authority.read_bytes()
        ).hexdigest(),
    )

    status, _receipt = module.run_rotation(imported, runtime)

    assert status == 0
    history = json.loads(
        request.epoch_history_path.read_text(encoding="utf-8")
    )
    assert [
        event["epochSha256"] for event in history["events"][:2]
    ] == [
        prior_legacy_sha256,
        hashlib.sha256(runtime.old_epoch.encode("utf-8")).hexdigest(),
    ]
    assert all(
        event["eventType"] == "legacy_observed"
        for event in history["events"][:2]
    )


def test_epoch_history_external_pin_and_chain_tamper_fail_before_quiesce(
    rotation_fixture,
) -> None:
    module, request, runtime = rotation_fixture
    status, _receipt = module.run_rotation(request, runtime)
    assert status == 0

    history_sha256 = hashlib.sha256(
        request.epoch_history_path.read_bytes()
    ).hexdigest()
    history = json.loads(
        request.epoch_history_path.read_text(encoding="utf-8")
    )
    history["events"][0]["epochSha256"] = "f" * 64
    request.epoch_history_path.write_text(
        json.dumps(history, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    request.epoch_history_path.chmod(0o600)
    actions_before = list(runtime.actions)
    next_request = replace(
        request,
        output=request.output.with_name("rotation-after-tamper.json"),
        expected_env_sha256_before=hashlib.sha256(
            request.env_file.read_bytes()
        ).hexdigest(),
        new_epoch="epoch-third",
        expected_existing_receipt_sha256="",
        expected_epoch_history_sha256=history_sha256,
        expected_epoch_history_bootstrap_marker_sha256=hashlib.sha256(
            request.epoch_history_bootstrap_marker.read_bytes()
        ).hexdigest(),
    )

    status, refused = module.run_rotation(next_request, runtime)
    assert status == 75
    assert refused["failureCode"] == "epoch_history_sha256_mismatch"
    assert runtime.actions == actions_before + [
        ("resolve-image", "chummer-run-api:local")
    ]

    repinned = replace(
        next_request,
        output=request.output.with_name("rotation-after-repin.json"),
        expected_epoch_history_sha256=hashlib.sha256(
            request.epoch_history_path.read_bytes()
        ).hexdigest(),
        expected_epoch_history_bootstrap_marker_sha256=hashlib.sha256(
            request.epoch_history_bootstrap_marker.read_bytes()
        ).hexdigest(),
    )
    status, refused = module.run_rotation(repinned, runtime)
    assert status == 75
    assert refused["failureCode"] == "epoch_history_event_invalid"
    assert runtime.portal_running is True


@pytest.mark.parametrize(
    ("field_path", "invalid_value", "failure_code"),
    [
        (("generation",), True, "epoch_history_contract_invalid"),
        (("updatedAtUtc",), 20260725, "epoch_history_contract_invalid"),
        (
            ("headEventSha256",),
            int("1" * 64),
            "epoch_history_contract_invalid",
        ),
        (("events", 0, "sequence"), False, "epoch_history_event_invalid"),
        (
            ("events", 0, "epochSha256"),
            int("1" * 64),
            "epoch_history_event_invalid",
        ),
        (
            ("events", 0, "recordedAtUtc"),
            20260725,
            "epoch_history_event_invalid",
        ),
        (
            ("events", 0, "sourceHead"),
            int("1" * 40),
            "epoch_history_event_invalid",
        ),
    ],
)
def test_epoch_history_rejects_json_type_confusion(
    rotation_fixture,
    field_path,
    invalid_value,
    failure_code: str,
) -> None:
    module, request, runtime = rotation_fixture
    status, _receipt = module.run_rotation(request, runtime)
    assert status == 0

    history = json.loads(
        request.epoch_history_path.read_text(encoding="utf-8")
    )
    target = history
    for component in field_path[:-1]:
        target = target[component]
    target[field_path[-1]] = invalid_value

    with pytest.raises(module.RotationError, match=failure_code):
        module.validate_epoch_history(history)


def test_epoch_history_mid_transaction_drift_fails_forward_with_old_stopped(
    rotation_fixture,
) -> None:
    module, request, runtime = rotation_fixture
    commit_epoch = module.replace_epoch_environment

    def drift_then_commit(**kwargs):
        payload = request.epoch_history_path.read_bytes()
        request.epoch_history_path.write_bytes(payload + b" ")
        request.epoch_history_path.chmod(0o600)
        return commit_epoch(**kwargs)

    module.replace_epoch_environment = drift_then_commit
    status, receipt = module.run_rotation(request, runtime)

    assert status == 76
    assert receipt["failureCode"] == "epoch_history_sha256_mismatch"
    assert runtime.portal_running is False
    assert module.parse_epoch_environment(request.env_file.read_bytes())[0] == (
        request.new_epoch
    )


def test_old_ticket_authority_is_mandatory_before_mutation(
    rotation_fixture,
) -> None:
    module, request, runtime = rotation_fixture
    refused = replace(
        request,
        old_ticket_path=None,
    )

    with pytest.raises(
        module.RotationError,
        match="old_ticket_proof_required",
    ):
        module.run_rotation(refused, runtime)
    assert runtime.actions == []
    assert not request.output.exists()


def test_old_ticket_materialization_authority_is_required(
    rotation_fixture,
) -> None:
    module, request, runtime = rotation_fixture
    with pytest.raises(
        module.RotationError,
        match="old_ticket_authority_invalid",
    ):
        module.run_rotation(
            replace(request, old_ticket_authority=None),
            runtime,
        )
    assert runtime.actions == []


def test_ticket_materialization_authority_is_read_from_owner_only_fd(
    rotation_fixture,
) -> None:
    module, request, _runtime = rotation_fixture
    observed = module.read_old_ticket_authority(
        request.old_ticket_authority.fd
    )
    assert observed == request.old_ticket_authority


def test_ticket_materialization_authority_requires_canonical_json(
    rotation_fixture,
) -> None:
    module, request, _runtime = rotation_fixture
    noncanonical_path = (
        request.output.parent / "noncanonical-ticket-authority.json"
    )
    authority = json.loads(
        request.old_ticket_authority.canonical_bytes.decode("utf-8")
    )
    noncanonical_path.write_text(
        json.dumps(authority, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    noncanonical_path.chmod(0o600)
    descriptor = os.open(noncanonical_path, os.O_RDONLY)
    try:
        with pytest.raises(
            module.RotationError,
            match="old_ticket_authority_not_canonical",
        ):
            module.read_old_ticket_authority(descriptor)
    finally:
        os.close(descriptor)


def test_ticket_materialization_authority_rejects_bool_size(
    rotation_fixture,
) -> None:
    module, request, _runtime = rotation_fixture
    invalid_path = request.output.parent / "invalid-ticket-authority.json"
    authority = json.loads(
        request.old_ticket_authority.canonical_bytes.decode("utf-8")
    )
    authority["ticketSizeBytes"] = True
    invalid_path.write_bytes(
        (
            json.dumps(
                authority,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
    )
    invalid_path.chmod(0o600)
    descriptor = os.open(invalid_path, os.O_RDONLY)
    try:
        with pytest.raises(
            module.RotationError,
            match="old_ticket_authority_contract_invalid",
        ):
            module.read_old_ticket_authority(descriptor)
    finally:
        os.close(descriptor)


@pytest.mark.parametrize(
    "field",
    [
        "opensslExecutableSha256",
        "materializationOpensslExecutableSha256",
    ],
)
def test_ticket_materialization_authority_rejects_non_string_openssl_pins(
    rotation_fixture,
    field: str,
) -> None:
    module, request, _runtime = rotation_fixture
    invalid_path = (
        request.output.parent / f"invalid-{field}.json"
    )
    authority = json.loads(
        request.old_ticket_authority.canonical_bytes.decode("utf-8")
    )
    authority[field] = int("1" * 64)
    invalid_path.write_bytes(
        (
            json.dumps(
                authority,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
    )
    invalid_path.chmod(0o600)
    descriptor = os.open(invalid_path, os.O_RDONLY)
    try:
        with pytest.raises(
            module.RotationError,
            match="old_ticket_authority_contract_invalid",
        ):
            module.read_old_ticket_authority(descriptor)
    finally:
        os.close(descriptor)


def test_ticket_materialization_authority_requires_linux_openssl_pin(
    rotation_fixture,
) -> None:
    module, request, _runtime = rotation_fixture
    invalid_path = request.output.parent / "missing-materializer-pin.json"
    authority = json.loads(
        request.old_ticket_authority.canonical_bytes.decode("utf-8")
    )
    del authority["materializationOpensslExecutableSha256"]
    invalid_path.write_bytes(
        (
            json.dumps(
                authority,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
    )
    invalid_path.chmod(0o600)
    descriptor = os.open(invalid_path, os.O_RDONLY)
    try:
        with pytest.raises(
            module.RotationError,
            match="old_ticket_authority_contract_invalid",
        ):
            module.read_old_ticket_authority(descriptor)
    finally:
        os.close(descriptor)


@pytest.mark.parametrize(
    "authority_field",
    [
        "openssl_executable_sha256",
        "materialization_openssl_executable_sha256",
    ],
)
def test_incident_commitment_binds_both_openssl_authorities(
    rotation_fixture,
    authority_field: str,
) -> None:
    module, request, _runtime = rotation_fixture
    assert request.old_ticket_path is not None
    ticket = request.old_ticket_path.read_text(
        encoding="ascii"
    ).rstrip("\n")
    baseline = module.incident_ticket_commitment_sha256(
        request,
        ticket,
    )
    substituted_authority = replace(
        request.old_ticket_authority,
        **{authority_field: "f" * 64},
    )
    substituted_request = replace(
        request,
        old_ticket_authority=substituted_authority,
    )

    assert module.incident_ticket_commitment_sha256(
        substituted_request,
        ticket,
    ) != baseline


def test_ticket_authority_binds_normalized_absolute_ticket_path(
    rotation_fixture,
) -> None:
    module, request, runtime = rotation_fixture
    substituted_path = request.output.parent / "substituted-ticket"
    substituted_path.write_bytes(request.old_ticket_path.read_bytes())
    substituted_path.chmod(0o600)

    with pytest.raises(
        module.RotationError,
        match="old_ticket_path_authority_mismatch",
    ):
        module.run_rotation(
            replace(request, old_ticket_path=substituted_path),
            runtime,
        )
    assert runtime.actions == []


def test_old_ticket_file_tamper_refuses_before_portal_stop(
    rotation_fixture,
) -> None:
    module, request, runtime = rotation_fixture
    assert request.old_ticket_path is not None
    request.old_ticket_path.write_text("tampered-ticket\n", encoding="ascii")
    request.old_ticket_path.chmod(0o600)

    with pytest.raises(
        module.RotationError,
        match="old_ticket_sha256_mismatch",
    ):
        module.run_rotation(request, runtime)
    assert not any(action[0] == "quiesce" for action in runtime.actions)
    assert runtime.portal_running is True


@pytest.mark.parametrize(
    "invalid_payload",
    [
        b"Authorization: Bearer token\n",
        b"token\n\n",
        b"token\r\n",
        b" token\n",
        b"token with-space\n",
        b"token\x00suffix\n",
        b"token\x7fsuffix\n",
    ],
)
def test_old_ticket_file_accepts_only_raw_bearer_bytes(
    rotation_fixture,
    invalid_payload: bytes,
) -> None:
    module, request, runtime = rotation_fixture
    assert request.old_ticket_path is not None
    request.old_ticket_path.write_bytes(invalid_payload)
    request.old_ticket_path.chmod(0o600)
    invalid_authority = materialize_ticket_authority(
        module,
        authority_path=(
            request.output.parent
            / f"invalid-ticket-authority-{hashlib.sha256(invalid_payload).hexdigest()[:12]}.json"
        ),
        ticket_path=request.old_ticket_path,
        ticket_payload=invalid_payload,
    )
    invalid = replace(
        request,
        old_ticket_authority=invalid_authority,
    )

    with pytest.raises(module.RotationError, match="old_ticket_invalid"):
        module.run_rotation(invalid, runtime)
    assert not any(action[0] == "quiesce" for action in runtime.actions)


def test_precommit_failure_restarts_old_portal_and_returns_75(
    rotation_fixture,
) -> None:
    module, request, runtime = rotation_fixture
    commit_epoch = module.replace_epoch_environment

    def fail_before_commit(**_kwargs):
        raise module.RotationError("injected_precommit_failure")

    module.replace_epoch_environment = fail_before_commit
    status, receipt = module.run_rotation(request, runtime)
    module.replace_epoch_environment = commit_epoch

    assert status == 75
    assert receipt["status"] == "failed_before_epoch_commit"
    assert runtime.portal_running is True
    assert ("quiesce", (OLD_PORTAL_ID,)) in runtime.actions
    assert ("restart", (OLD_PORTAL_ID,)) in runtime.actions
    assert module.parse_epoch_environment(request.env_file.read_bytes())[0] == (
        runtime.old_epoch
    )
    history = json.loads(
        request.epoch_history_path.read_text(encoding="utf-8")
    )
    assert [
        event["eventType"] for event in history["events"]
    ] == ["legacy_observed", "rotation_reserved"]
    actions_before_retry = list(runtime.actions)
    retry = replace(
        request,
        output=request.output.with_name("rotation-reuse-burned.json"),
        expected_existing_receipt_sha256="",
        expected_epoch_history_sha256=hashlib.sha256(
            request.epoch_history_path.read_bytes()
        ).hexdigest(),
        expected_epoch_history_bootstrap_marker_sha256=hashlib.sha256(
            request.epoch_history_bootstrap_marker.read_bytes()
        ).hexdigest(),
    )
    status, retry_receipt = module.run_rotation(retry, runtime)
    assert status == 75
    assert retry_receipt["failureCode"] == "epoch_history_epoch_reused"
    assert runtime.actions == actions_before_retry + [
        ("resolve-image", "chummer-run-api:local")
    ]


def test_precommit_restart_failure_retains_lock_posture_with_76(
    rotation_fixture,
) -> None:
    module, request, runtime = rotation_fixture
    runtime.fail_quiesce_after_stop = True
    runtime.fail_restart = True

    status, receipt = module.run_rotation(request, runtime)

    assert status == 76
    assert receipt["failureCode"] == "precommit_portal_restart_failed"
    assert runtime.portal_running is False
    assert module.parse_epoch_environment(request.env_file.read_bytes())[0] == (
        runtime.old_epoch
    )


def test_precommit_restart_health_failure_is_requiesced_before_76(
    rotation_fixture,
) -> None:
    module, request, runtime = rotation_fixture
    runtime.fail_quiesce_after_stop = True
    runtime.fail_restart_health = True

    status, receipt = module.run_rotation(request, runtime)

    assert status == 76
    assert receipt["failureCode"] == "precommit_portal_restart_failed"
    restart_index = runtime.actions.index(("restart", (OLD_PORTAL_ID,)))
    requiesce_index = runtime.actions.index(
        ("quiesce-known", (OLD_PORTAL_ID,)),
        restart_index,
    )
    assert restart_index < requiesce_index
    assert runtime.portal_running is False
    assert module.parse_epoch_environment(request.env_file.read_bytes())[0] == (
        runtime.old_epoch
    )


def test_empty_enumerations_do_not_replace_durable_prior_identity_proof(
    rotation_fixture,
) -> None:
    module, request, runtime = rotation_fixture
    runtime.fail_quiesce_after_stop = True
    runtime.fail_restart_health = True
    runtime.hide_project_enumeration = True
    runtime.hide_independent_enumeration = True

    status, receipt = module.run_rotation(request, runtime)

    assert status == 76
    assert receipt["failureContainment"] == {
        "portalQuiescenceProven": True,
        "publicConnectorsStopped": False,
    }
    assert ("quiesce-known", (OLD_PORTAL_ID,)) in runtime.actions
    assert runtime.portal_running is False


def test_empty_enumerations_and_unproven_prior_stop_require_connector_cut_70(
    rotation_fixture,
) -> None:
    module, request, runtime = rotation_fixture
    runtime.fail_quiesce_after_stop = True
    runtime.fail_restart_health = True
    runtime.hide_project_enumeration = True
    runtime.hide_independent_enumeration = True
    runtime.block_requiesce_after_restart = True

    status, receipt = module.run_rotation(request, runtime)

    assert status == 70
    assert receipt["failureContainment"] == {
        "portalQuiescenceProven": False,
        "publicConnectorsStopped": True,
    }
    assert runtime.portal_running is True
    assert runtime.connectors_running is False


def test_invalid_durable_prior_identity_always_cuts_connectors(
    rotation_fixture,
) -> None:
    module, _request, runtime = rotation_fixture

    containment = module.fail_closed_contain_precommit_portals(
        runtime,
        durable_prior_ids=(),
    )

    assert containment == {
        "portalQuiescenceProven": False,
        "publicConnectorsStopped": True,
    }
    assert runtime.connectors_running is False


def test_independent_enumeration_adds_and_stops_unrecorded_portal(
    rotation_fixture,
) -> None:
    module, request, runtime = rotation_fixture
    runtime.fail_quiesce_after_stop = True
    runtime.fail_restart_health = True
    runtime.rogue_portal_exists = True
    runtime.rogue_portal_running = True

    status, receipt = module.run_rotation(request, runtime)

    assert status == 76
    assert receipt["failureContainment"]["portalQuiescenceProven"] is True
    assert (
        "quiesce-known",
        (OLD_PORTAL_ID, runtime.rogue_portal_id),
    ) in runtime.actions
    assert runtime.portal_running is False
    assert runtime.rogue_portal_running is False


def test_precommit_requiesce_failure_cuts_connectors_and_returns_70(
    rotation_fixture,
) -> None:
    module, request, runtime = rotation_fixture
    runtime.fail_quiesce_after_stop = True
    runtime.fail_restart_health = True
    runtime.block_requiesce_after_restart = True

    status, receipt = module.run_rotation(request, runtime)

    assert status == 70
    assert receipt["status"] == "emergency_public_connectors_stopped"
    assert receipt["failureCode"] == (
        "precommit_portal_quiescence_unproven_connectors_stopped"
    )
    assert receipt["failureContainment"] == {
        "portalQuiescenceProven": False,
        "publicConnectorsStopped": True,
    }
    assert runtime.portal_running is True
    assert runtime.connectors_running is False
    assert ("connectors-quiesce",) in runtime.actions


def test_unproven_precommit_containment_never_returns_fail_forward_76(
    rotation_fixture,
) -> None:
    module, request, runtime = rotation_fixture
    runtime.fail_quiesce_after_stop = True
    runtime.fail_restart_health = True
    runtime.block_requiesce_after_restart = True
    runtime.fail_connector_quiesce = True

    status, receipt = module.run_rotation(request, runtime)

    assert status == 70
    assert receipt["status"] == "emergency_containment_unproven"
    assert receipt["failureCode"] == (
        "precommit_emergency_containment_not_proven"
    )


def test_crash_before_commit_resumes_by_restart_then_quiesce(
    rotation_fixture,
) -> None:
    module, request, runtime = rotation_fixture
    commit_epoch = module.replace_epoch_environment

    def crash_before_commit(**_kwargs):
        raise KeyboardInterrupt()

    module.replace_epoch_environment = crash_before_commit
    with pytest.raises(KeyboardInterrupt):
        module.run_rotation(request, runtime)
    assert runtime.portal_running is False
    assert module.parse_epoch_environment(request.env_file.read_bytes())[0] == (
        runtime.old_epoch
    )

    module.replace_epoch_environment = commit_epoch
    status, receipt = module.run_rotation(
        pinned_resume_request(request),
        runtime,
    )

    assert status == 0
    assert receipt["status"] == "pass"
    restart_index = runtime.actions.index(("restart", (OLD_PORTAL_ID,)))
    later_quiesce = runtime.actions.index(
        ("quiesce", (OLD_PORTAL_ID,)),
        restart_index,
    )
    assert restart_index < later_quiesce


def test_crash_after_stop_before_history_reservation_is_resumable(
    rotation_fixture,
) -> None:
    module, request, runtime = rotation_fixture
    publish_history = module.publish_epoch_history

    def crash_before_reservation(*_args, **_kwargs):
        raise KeyboardInterrupt()

    module.publish_epoch_history = crash_before_reservation
    with pytest.raises(KeyboardInterrupt):
        module.run_rotation(request, runtime)
    assert runtime.portal_running is False
    assert not request.epoch_history_path.exists()
    assert module.parse_epoch_environment(request.env_file.read_bytes())[0] == (
        runtime.old_epoch
    )

    module.publish_epoch_history = publish_history
    status, receipt = module.run_rotation(
        pinned_resume_request(request),
        runtime,
    )

    assert status == 0
    assert receipt["status"] == "pass"
    assert request.epoch_history_path.exists()
    assert ("restart", (OLD_PORTAL_ID,)) in runtime.actions


def test_crash_after_durable_bootstrap_marker_is_receipt_bound_and_resumable(
    rotation_fixture,
) -> None:
    module, request, runtime = rotation_fixture
    publish_marker = module.publish_epoch_history_bootstrap_marker

    def publish_marker_then_crash(*args, **kwargs):
        publish_marker(*args, **kwargs)
        raise KeyboardInterrupt()

    module.publish_epoch_history_bootstrap_marker = publish_marker_then_crash
    with pytest.raises(KeyboardInterrupt):
        module.run_rotation(request, runtime)
    assert request.epoch_history_bootstrap_marker.exists()
    assert not request.epoch_history_path.exists()
    assert runtime.portal_running is True

    module.publish_epoch_history_bootstrap_marker = publish_marker
    status, receipt = module.run_rotation(
        pinned_resume_request(request),
        runtime,
    )

    assert status == 0
    assert receipt["status"] == "pass"
    assert request.epoch_history_path.exists()


def test_crash_after_commit_never_restarts_old_portal_and_resumes(
    rotation_fixture,
) -> None:
    module, request, runtime = rotation_fixture
    commit_epoch = module.replace_epoch_environment

    def crash_after_commit(**kwargs):
        result = commit_epoch(**kwargs)
        assert runtime.portal_running is False
        raise KeyboardInterrupt()

    module.replace_epoch_environment = crash_after_commit
    with pytest.raises(KeyboardInterrupt):
        module.run_rotation(request, runtime)
    assert runtime.portal_running is False
    assert module.parse_epoch_environment(request.env_file.read_bytes())[0] == (
        request.new_epoch
    )
    restart_count = runtime.actions.count(("restart", (OLD_PORTAL_ID,)))

    module.replace_epoch_environment = commit_epoch
    status, receipt = module.run_rotation(
        pinned_resume_request(request),
        runtime,
    )

    assert status == 0
    assert receipt["status"] == "pass"
    assert runtime.actions.count(("restart", (OLD_PORTAL_ID,))) == (
        restart_count
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
        match="existing_receipt_sha256_required",
    ):
        module.run_rotation(request, runtime)
    with pytest.raises(
        module.RotationError,
        match="existing_receipt_sha256_mismatch",
    ):
        module.run_rotation(
            replace(request, expected_existing_receipt_sha256="f" * 64),
            runtime,
        )
    assert runtime.portal_id == OLD_PORTAL_ID


def test_resume_is_bound_to_exact_held_incident_ticket(
    rotation_fixture,
) -> None:
    module, request, runtime = rotation_fixture
    runtime.fail_recreate = True
    status, _failed = module.run_rotation(request, runtime)
    assert status == 76

    replacement_ticket = b"different-held-incident-ticket\n"
    assert request.old_ticket_path is not None
    request.old_ticket_path.write_bytes(replacement_ticket)
    request.old_ticket_path.chmod(0o600)
    replacement_authority = materialize_ticket_authority(
        module,
        authority_path=(
            request.output.parent / "replacement-ticket-authority.json"
        ),
        ticket_path=request.old_ticket_path,
        ticket_payload=replacement_ticket,
    )
    substituted = replace(
        pinned_resume_request(request),
        old_ticket_authority=replacement_authority,
    )

    with pytest.raises(
        module.RotationError,
        match="resume_receipt_authority_mismatch",
    ):
        module.run_rotation(substituted, runtime)
    receipt_text = request.output.read_text(encoding="utf-8")
    assert "different-held-incident-ticket" not in receipt_text
    assert substituted.old_ticket_authority.ticket_sha256 not in receipt_text
    assert str(substituted.old_ticket_path) not in receipt_text


@pytest.mark.parametrize(
    ("field_path", "invalid_value"),
    [
        (("portalReplicaCount",), True),
        (("canonicalTunnelsBefore", 0, "running"), 1),
        (("edgeWafLocalEvidence", "mutationPerformed"), 0),
        (("oldTicketRevocationProof", "supplied"), 1),
    ],
)
def test_resume_receipt_rejects_bool_integer_and_coercion_confusion(
    rotation_fixture,
    field_path,
    invalid_value,
) -> None:
    module, request, runtime = rotation_fixture
    runtime.fail_recreate = True
    status, _failed = module.run_rotation(request, runtime)
    assert status == 76

    receipt = json.loads(request.output.read_text(encoding="utf-8"))
    target = receipt
    for component in field_path[:-1]:
        target = target[component]
    target[field_path[-1]] = invalid_value
    request.output.write_text(
        json.dumps(receipt, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    request.output.chmod(0o600)
    invalid_resume = replace(
        pinned_resume_request(request),
        expected_existing_receipt_sha256=hashlib.sha256(
            request.output.read_bytes()
        ).hexdigest(),
    )

    with pytest.raises(module.RotationError, match="receipt_types_invalid"):
        module.run_rotation(invalid_resume, runtime)
    assert runtime.portal_id == OLD_PORTAL_ID


def test_waf_local_evidence_drift_fails_forward(
    rotation_fixture,
) -> None:
    module, request, runtime = rotation_fixture
    verify_waf = module.verify_edge_waf_local_evidence_source
    calls = 0

    def drift_on_postverification(current_request):
        nonlocal calls
        calls += 1
        if calls == 3:
            current_request.edge_waf_local_evidence_source.write_text(
                '{"ruleset":"substituted"}\n',
                encoding="utf-8",
            )
            current_request.edge_waf_local_evidence_source.chmod(0o600)
        return verify_waf(current_request)

    module.verify_edge_waf_local_evidence_source = (
        drift_on_postverification
    )
    status, receipt = module.run_rotation(request, runtime)

    assert status == 76
    assert receipt["failureCode"] == (
        "edge_waf_local_evidence_sha256_mismatch"
    )
    assert (
        receipt["edgeWafLocalEvidence"][
            "stableThroughPostVerification"
        ]
        is False
    )
    assert (
        receipt["edgeWafLocalEvidence"]["liveControlPlaneVerified"]
        is False
    )
    assert module.parse_epoch_environment(request.env_file.read_bytes())[0] == (
        request.new_epoch
    )


def test_ticket_authority_is_refstat_and_reread_before_revocation_proof(
    rotation_fixture,
) -> None:
    module, request, runtime = rotation_fixture
    verify_waf = module.verify_edge_waf_local_evidence_source
    authority_path = request.output.parent / "old-ticket-authority.json"
    calls = 0

    def mutate_authority_before_proof(current_request):
        nonlocal calls
        calls += 1
        if calls == 3:
            authority = json.loads(
                request.old_ticket_authority.canonical_bytes.decode("utf-8")
            )
            authority["envelopeSha256"] = "e" * 64
            authority_path.write_bytes(
                (
                    json.dumps(
                        authority,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    + "\n"
                ).encode("utf-8")
            )
            authority_path.chmod(0o600)
        return verify_waf(current_request)

    module.verify_edge_waf_local_evidence_source = (
        mutate_authority_before_proof
    )
    status, receipt = module.run_rotation(request, runtime)

    assert status == 76
    assert receipt["failureCode"] == "old_ticket_authority_changed"
    assert not any(
        action[0] == "old-ticket-proof" for action in runtime.actions
    )
    assert module.parse_epoch_environment(request.env_file.read_bytes())[0] == (
        request.new_epoch
    )


def test_direct_request_rejects_noncanonical_path_alias(
    rotation_fixture,
) -> None:
    module, request, _runtime = rotation_fixture
    alias = Path(f"{request.output.parent}/nested/../rotation.json")
    with pytest.raises(module.RotationError, match="receipt_path_invalid"):
        module._validate_request(replace(request, output=alias))


def test_direct_runtime_rejects_noncanonical_compose_project_alias(
    rotation_fixture,
) -> None:
    module, request, _runtime = rotation_fixture
    root = request.output.parent
    with pytest.raises(
        module.RotationError,
        match="compose_project_not_canonical",
    ):
        module.DockerRuntime(
            docker_config_root=root,
            docker_context="default",
            compose_file=request.proof_bind_source,
            env_file=request.env_file,
            project_name="chummer6-hub-alias",
            source_root=root,
            build_context=root,
            overlay_root=root,
            projection_root=root,
            proof_bind_source=request.proof_bind_source,
            published_port=8091,
            base_url="https://chummer.run",
        )


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

    request.env_file.write_text(
        f"{module.EPOCH_KEY}=unexpected-third-epoch\n",
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


@pytest.mark.parametrize(
    ("field_path", "invalid_value"),
    [
        (("portal", "containerId"), int("1" * 64)),
        (("portal", "containerName"), int("1" * 64)),
        (("portal", "imageId"), 1),
        (
            ("portal", "proofAuthorityMountSha256"),
            int("1" * 64),
        ),
        (
            ("portal", "proofPublicMountSha256"),
            int("1" * 64),
        ),
        (
            ("installLinkingAuthorityReadinessSha256",),
            int("1" * 64),
        ),
    ],
)
def test_active_runtime_authority_rejects_json_type_confusion(
    rotation_fixture,
    field_path,
    invalid_value,
) -> None:
    module, request, _runtime = rotation_fixture
    active = json.loads(
        request.active_runtime_authority.read_text(encoding="utf-8")
    )
    target = active
    for component in field_path[:-1]:
        target = target[component]
    target[field_path[-1]] = invalid_value
    request.active_runtime_authority.write_text(
        json.dumps(active, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    request.active_runtime_authority.chmod(0o600)

    with pytest.raises(
        module.RotationError,
        match="active_runtime_authority_contract_invalid",
    ):
        module.read_active_runtime_authority(
            request.active_runtime_authority
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
    assert "--epoch-history-path" in source[rotation:release]
    assert "--expected-epoch-history-sha256" in source[rotation:release]
    assert "--expected-proof-sha256" in source[rotation:release]
    assert "--old-ticket-path" in source[rotation:release]
    assert "--old-ticket-authority-fd 3" in source[rotation:release]
    assert "--old-ticket-sha256" not in source[rotation:release]
    assert "CHUMMER_RELEASE_UPLOAD_OLD_TICKET_SHA256" not in source
    assert "CHUMMER_RELEASE_UPLOAD_OLD_TICKET_AUTHORITY" in source
    assert "--shared-mutation-lock-fd 0" in source[rotation:release]
    assert "--shared-mutation-lock-token" not in source[rotation:release]
    assert "75)" in source[rotation:release]
    assert "epoch_rotation_fail_forward_required=0" in source[rotation:release]
    assert "epoch_rotation_precommit_refused=1" in source[rotation:release]
    assert "--edge-waf-local-evidence-source" in source[rotation:release]
    assert (
        "--expected-edge-waf-local-evidence-sha256"
        in source[rotation:release]
    )
    assert "cloudflare" not in source[rotation:release].lower()
    rotation_source = SCRIPT.read_text(encoding="utf-8")
    assert '"--pull",\n                "never"' in rotation_source
    assert '"--build"' not in rotation_source
    usage = source.splitlines()[17]
    assert usage.index("initial-release-shelf") < usage.index(
        "release-upload-ticket-epoch-rotate"
    )


def test_waf_contract_names_only_pinned_local_evidence() -> None:
    rotation_source = SCRIPT.read_text(encoding="utf-8")
    deploy_source = DEPLOY.read_text(encoding="utf-8")
    combined = rotation_source + deploy_source

    for misleading_contract_fragment in (
        "edge_waf_control_plane",
        "EDGE_WAF_CONTROL_PLANE",
        "--edge-waf-control-plane",
        '"edgeWaf":',
        "ControlPlaneFingerprint",
        "PreservedThroughPostVerification",
    ):
        assert misleading_contract_fragment not in combined
    assert '"evidenceScope": "pinned_local_evidence_only"' in rotation_source
    assert '"edgeWafLiveControlPlaneVerified": False' in rotation_source
    assert (
        "this is not live control-plane verification"
        in deploy_source
    )


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
    assert "--epoch-history-path" in resume_source
    assert "--expected-epoch-history-sha256" in resume_source
    assert "--old-ticket-path" in resume_source
    assert "--old-ticket-authority-fd 3" in resume_source
    assert "--old-ticket-sha256" not in resume_source
    assert "--shared-mutation-lock-fd 0" in resume_source
    assert "epoch_rotation_fail_forward_required=0" in resume_source
    assert "release_deploy_lock" in resume_source
    assert "buildx build" not in resume_source
    assert "--source-replay-preflight" not in resume_source
    assert "exit 0" in resume_source
