from __future__ import annotations

import hashlib
import importlib.util
import json
from contextlib import nullcontext
from pathlib import Path
import shutil
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "public_edge_deploy_recovery.py"
PORTAL_TAG = "chummer-run-api:local"
TOOL_TAG = "chummer-install-linking-postgres-tool:local"
PROJECT_NAME = "chummer6-hub"
PRIOR_PORTAL_NAME = "chummer6-hub-chummer-portal-1"
CANDIDATE_PORTAL_NAME = "chummer-public-edge-candidate-test"
PRIOR_PORTAL_IMAGE = "sha256:" + "1" * 64
PRIOR_TOOL_IMAGE = "sha256:" + "2" * 64
PRIOR_TUNNEL_IMAGE = "sha256:" + "3" * 64
CANDIDATE_PORTAL_IMAGE = "sha256:" + "4" * 64
CANDIDATE_TOOL_IMAGE = "sha256:" + "5" * 64
PRIOR_PORTAL = "a" * 64
PRIOR_TUNNEL = "b" * 64
CANDIDATE_PORTAL = "c" * 64
CANDIDATE_PROOF_BYTES = b"candidate-proof-authority\n"
PRIOR_PROOF_BYTES = b"prior-proof-authority\n"
CANDIDATE_PROOF_SHA256 = hashlib.sha256(CANDIDATE_PROOF_BYTES).hexdigest()
PRIOR_PROOF_SHA256 = hashlib.sha256(PRIOR_PROOF_BYTES).hexdigest()


def write_public_projection_snapshot(root: Path, *, variant: bytes = b"") -> Path:
    output_names = (
        "HUB_LOCAL_RELEASE_PROOF.generated.json",
        "HUB_SERVED_RELEASE_PROOF.generated.json",
        "NEXT90_M125_HUB_PUBLIC_SIGNAL_PACKETS.generated.json",
        "NEXT90_M126_HUB_HOSTED_PROOF_CONTRACTS.generated.json",
        "LIVE_PUBLIC_WINDOWS_INSTALLER.generated.json",
        "RELEASE_CHANNEL.generated.json",
        "FLAGSHIP_PRODUCT_READINESS.generated.json",
    )
    payloads = {
        output_names[0]: CANDIDATE_PROOF_BYTES,
        output_names[1]: CANDIDATE_PROOF_BYTES,
        output_names[2]: b"m125\n" + variant,
        output_names[3]: b"m126\n",
        output_names[4]: b"windows\n",
        output_names[5]: b"release-channel\n",
        output_names[6]: b"flagship-readiness\n",
    }
    digests = {
        name: hashlib.sha256(payloads[name]).hexdigest() for name in output_names
    }
    aggregate = hashlib.sha256()
    for name in output_names:
        aggregate.update(name.encode("utf-8"))
        aggregate.update(b"\0")
        aggregate.update(digests[name].encode("ascii"))
        aggregate.update(b"\n")
    snapshot_sha256 = aggregate.hexdigest()
    snapshot_id = f"public-projection-{snapshot_sha256}"
    snapshot = root / snapshot_id
    snapshot.mkdir(parents=True)
    for name, payload in payloads.items():
        (snapshot / name).write_bytes(payload)
    manifest_name = "PUBLIC_PROJECTION_SNAPSHOT.generated.json"
    manifest = {
        "contractName": "chummer.public_projection_snapshot/v1",
        "status": "pass",
        "projectionStage": "release_upload_ready",
        "codeDeploymentAuthority": True,
        "releaseUploadAuthority": True,
        "candidateImportAuthority": False,
        "snapshotId": snapshot_id,
        "snapshotSha256": snapshot_sha256,
        "authorityInputs": {},
        "outputs": {
            name: {
                "relativePath": name,
                "sha256": digests[name],
                "sizeBytes": len(payloads[name]),
            }
            for name in output_names
        },
    }
    manifest_bytes = (
        json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    (snapshot / manifest_name).write_bytes(manifest_bytes)
    current = {
        "contractName": "chummer.public_projection_current/v1",
        "status": "pass",
        "projectionStage": "release_upload_ready",
        "codeDeploymentAuthority": True,
        "releaseUploadAuthority": True,
        "candidateImportAuthority": False,
        "snapshotId": snapshot_id,
        "snapshotSha256": snapshot_sha256,
        "manifestRelativePath": f"{snapshot_id}/{manifest_name}",
        "manifestSha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "outputs": {name: f"{snapshot_id}/{name}" for name in output_names},
    }
    (root / "CURRENT.json").write_text(
        json.dumps(current, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    return snapshot / output_names[0]


def public_projection_identity(root: Path) -> dict[str, str]:
    current = json.loads((root / "CURRENT.json").read_text(encoding="utf-8"))
    return {
        "publicProjectionManifestSha256": current["manifestSha256"],
        "publicProjectionSnapshotId": current["snapshotId"],
        "publicProjectionSnapshotSha256": current["snapshotSha256"],
    }


def load_module():
    spec = importlib.util.spec_from_file_location("public_edge_deploy_recovery_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FakeRuntime:
    def __init__(self) -> None:
        self.tags = {
            PORTAL_TAG: PRIOR_PORTAL_IMAGE,
            TOOL_TAG: PRIOR_TOOL_IMAGE,
        }
        self.images = {
            PRIOR_PORTAL_IMAGE,
            PRIOR_TOOL_IMAGE,
            PRIOR_TUNNEL_IMAGE,
            CANDIDATE_PORTAL_IMAGE,
            CANDIDATE_TOOL_IMAGE,
        }
        self.services = {
            "chummer-portal": PRIOR_PORTAL,
            "chummer-run-cloudflared": PRIOR_TUNNEL,
        }
        self.names = {PRIOR_PORTAL_NAME: PRIOR_PORTAL}
        self.containers = {
            PRIOR_PORTAL: {
                "image": PRIOR_PORTAL_IMAGE,
                "running": True,
                "labels": {
                    "com.docker.compose.project": PROJECT_NAME,
                    "com.docker.compose.service": "chummer-portal",
                    "com.docker.compose.oneoff": "False",
                },
            },
            PRIOR_TUNNEL: {
                "image": PRIOR_TUNNEL_IMAGE,
                "running": True,
                "labels": {
                    "com.docker.compose.project": PROJECT_NAME,
                    "com.docker.compose.service": "chummer-run-cloudflared",
                    "com.docker.compose.oneoff": "False",
                },
            },
        }
        self.proof_digests = {
            (PRIOR_PORTAL, "/proofs/HUB_LOCAL_RELEASE_PROOF.generated.json"): (
                PRIOR_PROOF_SHA256
            ),
            (
                PRIOR_PORTAL,
                "/app/wwwroot/proofs/mac-codex-release/"
                "HUB_LOCAL_RELEASE_PROOF.generated.json",
            ): PRIOR_PROOF_SHA256,
        }
        self.bound_proof_sha256 = CANDIDATE_PROOF_SHA256
        self.actions: list[tuple[object, ...]] = []

    def add_candidate(self, *, running: bool = True) -> None:
        self.names[CANDIDATE_PORTAL_NAME] = CANDIDATE_PORTAL
        self.containers[CANDIDATE_PORTAL] = {
            "image": CANDIDATE_PORTAL_IMAGE,
            "running": running,
            "labels": {
                "com.docker.compose.project": PROJECT_NAME,
                "com.docker.compose.service": "chummer-portal",
                "com.docker.compose.oneoff": "True",
            },
        }

    def resolve_image_tag(self, tag: str) -> str:
        return self.tags.get(tag, "")

    def image_exists(self, image_id: str) -> bool:
        return image_id in self.images

    def tag_image(self, image_id: str, tag: str) -> None:
        self.actions.append(("tag", image_id, tag))
        self.tags[tag] = image_id

    def remove_image_tag(self, tag: str) -> None:
        self.actions.append(("remove-tag", tag))
        self.tags.pop(tag, None)

    def service_container(self, service: str) -> str:
        return self.services.get(service, "")

    def container_by_name(self, name: str) -> str:
        return self.names.get(name, "")

    def container_exists(self, container_id: str) -> bool:
        return container_id in self.containers

    def container_labels(self, container_id: str) -> dict[str, str]:
        return dict(self.containers[container_id]["labels"])

    def container_image(self, container_id: str) -> str:
        return str(self.containers[container_id]["image"])

    def container_running(self, container_id: str) -> bool:
        return bool(self.containers[container_id]["running"])

    def set_container_running(self, container_id: str, running: bool) -> None:
        self.actions.append(("running", container_id, running))
        self.containers[container_id]["running"] = running

    def remove_container(self, container_id: str) -> None:
        self.actions.append(("remove-container", container_id))
        self.containers.pop(container_id, None)
        for service, current in tuple(self.services.items()):
            if current == container_id:
                self.services.pop(service)
        for name, current in tuple(self.names.items()):
            if current == container_id:
                self.names.pop(name)

    def container_file_sha256(self, container_id: str, path: str) -> str:
        self.actions.append(("proof-sha256", container_id, path))
        try:
            return self.proof_digests[(container_id, path)]
        except KeyError as exc:
            raise RuntimeError("runtime proof mount is unavailable") from exc


def prior_state(
    *,
    portal_existed: bool = True,
    portal_running: bool = True,
    tunnel_existed: bool = True,
    tunnel_running: bool = True,
    projection_identity: dict[str, str] | None = None,
) -> dict[str, object]:
    mounted_digest = PRIOR_PROOF_SHA256 if portal_existed and portal_running else ""
    generation = projection_identity or {
        "publicProjectionManifestSha256": "0" * 64,
        "publicProjectionSnapshotId": "public-projection-" + "0" * 64,
        "publicProjectionSnapshotSha256": "0" * 64,
    }
    return {
        "candidatePortalContainerName": CANDIDATE_PORTAL_NAME,
        "expectedRuntimeProofBindSourceSha256": CANDIDATE_PROOF_SHA256,
        **generation,
        "priorImageTagId": PRIOR_PORTAL_IMAGE,
        "priorToolImageTagId": PRIOR_TOOL_IMAGE,
        "priorPortalContainerId": PRIOR_PORTAL if portal_existed else "",
        "priorPortalContainerName": PRIOR_PORTAL_NAME if portal_existed else "",
        "priorPortalImageId": PRIOR_PORTAL_IMAGE if portal_existed else "",
        "priorPortalProofAuthorityMountSha256": mounted_digest,
        "priorPortalProofPublicMountSha256": mounted_digest,
        "priorPortalExisted": portal_existed,
        "priorPortalWasRunning": portal_running if portal_existed else False,
        "priorTunnelContainerId": PRIOR_TUNNEL if tunnel_existed else "",
        "priorTunnelImageId": PRIOR_TUNNEL_IMAGE if tunnel_existed else "",
        "priorTunnelExisted": tunnel_existed,
        "priorTunnelWasRunning": tunnel_running if tunnel_existed else False,
    }


def run_reconcile(module, runtime: FakeRuntime, state: dict[str, object], overlay: list[bool]):
    def restore_overlay() -> None:
        runtime.actions.append(("restore-overlay",))
        overlay[0] = True

    def prepare_prior_proof_bind() -> None:
        return None

    def restore_candidate_proof_bind() -> None:
        return None

    return module.reconcile(
        runtime=runtime,
        runtime_prior_state=state,
        overlay_matches=lambda: overlay[0],
        restore_overlay=restore_overlay,
        proof_bind_source_matches_candidate=(
            lambda: runtime.bound_proof_sha256 == CANDIDATE_PROOF_SHA256
        ),
        prepare_prior_proof_bind=prepare_prior_proof_bind,
        restore_candidate_proof_bind=restore_candidate_proof_bind,
        portal_image_tag=PORTAL_TAG,
        tool_image_tag=TOOL_TAG,
        project_name=PROJECT_NAME,
    )


def recovery_argv(tmp_path: Path, source_root: Path, active_root: Path) -> list[str]:
    return [
        "--source-root",
        str(source_root),
        "--active-root",
        str(active_root),
        "--backup-root",
        str(tmp_path / "backups"),
        "--snapshot",
        str(tmp_path / "journal.json"),
        "--activation-receipt",
        str(tmp_path / "activation.json"),
        "--overlay-rollback-output",
        str(tmp_path / "overlay-rollback.json"),
        "--output",
        str(tmp_path / "recovery.json"),
        "--runtime-authority-output",
        str(tmp_path / "active-runtime-authority.json"),
        "--shared-mutation-lock-token",
        "f" * 64,
        "--docker-config-root",
        str(tmp_path / "docker"),
        "--docker-context",
        "default",
        "--compose-file",
        str(tmp_path / "compose.yml"),
        "--env-file",
        str(tmp_path / ".env"),
        "--project-name",
        PROJECT_NAME,
        "--build-context",
        str(tmp_path),
        "--public-projection-snapshot-root",
        str(tmp_path / "public-projection"),
        "--published-port",
        "8091",
        "--portal-image-tag",
        PORTAL_TAG,
        "--tool-image-tag",
        TOOL_TAG,
    ]


def write_deploy_journal(module, tmp_path: Path) -> tuple[Path, Path, Path]:
    source_root = tmp_path / "source"
    active_root = tmp_path / "active" / "app"
    staging_root = tmp_path / "staging" / "app"
    backup_root = tmp_path / "backups"
    projection_root = tmp_path / "public-projection"
    proof_bind_source = write_public_projection_snapshot(projection_root)
    projection_generation = public_projection_identity(projection_root)
    candidate_snapshot = tmp_path / "candidate-proof.json"
    prior_authority_snapshot = tmp_path / "prior-authority-proof.json"
    prior_public_snapshot = tmp_path / "prior-public-proof.json"
    source_root.mkdir()
    projection_verifier = source_root / "scripts/release/verify_public_projection.py"
    projection_verifier.parent.mkdir(parents=True)
    shutil.copyfile(
        ROOT / "scripts/release/verify_public_projection.py",
        projection_verifier,
    )
    active_root.mkdir(parents=True)
    staging_root.mkdir(parents=True)
    backup_root.mkdir()
    (active_root / "payload.txt").write_text("prior\n", encoding="utf-8")
    (staging_root / "payload.txt").write_text("candidate\n", encoding="utf-8")
    candidate_snapshot.write_bytes(CANDIDATE_PROOF_BYTES)
    prior_authority_snapshot.write_bytes(PRIOR_PROOF_BYTES)
    prior_public_snapshot.write_bytes(PRIOR_PROOF_BYTES)
    journal = tmp_path / "journal.json"
    module.transaction.snapshot(
        source_root=source_root,
        active_root=active_root,
        output=journal,
        shared_mutation_lock_token="f" * 64,
        runtime_prior_state=prior_state(
            projection_identity=projection_generation,
        ),
        staging_root=staging_root,
        backup_root=backup_root,
        activation_receipt=tmp_path / "activation.json",
        proof_bind_source=proof_bind_source,
        candidate_proof_bind_source_snapshot=candidate_snapshot,
        prior_portal_proof_authority_snapshot=prior_authority_snapshot,
        prior_portal_proof_public_snapshot=prior_public_snapshot,
    )
    return source_root, active_root, journal


def test_hard_crash_during_build_restores_both_tags_without_touching_runtime() -> None:
    module = load_module()
    runtime = FakeRuntime()
    runtime.tags[PORTAL_TAG] = CANDIDATE_PORTAL_IMAGE
    runtime.tags[TOOL_TAG] = CANDIDATE_TOOL_IMAGE

    receipt = run_reconcile(module, runtime, prior_state(), [True])

    assert receipt["status"] == "pass"
    assert runtime.tags[PORTAL_TAG] == PRIOR_PORTAL_IMAGE
    assert runtime.tags[TOOL_TAG] == PRIOR_TOOL_IMAGE
    assert runtime.services["chummer-portal"] == PRIOR_PORTAL
    assert not any(action[0] in {"running", "remove-container"} for action in runtime.actions)


def test_hard_crash_after_candidate_start_removes_only_candidate_and_restores_old_proof() -> None:
    module = load_module()
    runtime = FakeRuntime()
    runtime.add_candidate()
    runtime.containers[PRIOR_PORTAL]["running"] = False
    runtime.containers[PRIOR_TUNNEL]["running"] = False
    overlay = [False]

    receipt = run_reconcile(module, runtime, prior_state(), overlay)

    assert receipt["status"] == "pass"
    assert overlay == [True]
    assert CANDIDATE_PORTAL not in runtime.containers
    assert PRIOR_PORTAL in runtime.containers
    assert runtime.container_running(PRIOR_PORTAL) is True
    assert runtime.bound_proof_sha256 == CANDIDATE_PROOF_SHA256
    assert runtime.proof_digests[(PRIOR_PORTAL, module.PROOF_AUTHORITY_PATH)] == PRIOR_PROOF_SHA256
    assert not any(action[0] == "proof-source" for action in runtime.actions)
    assert runtime.actions.index(("remove-container", CANDIDATE_PORTAL)) < runtime.actions.index(
        ("running", PRIOR_TUNNEL, True)
    )


def test_candidate_outside_compose_authority_fails_closed() -> None:
    module = load_module()
    runtime = FakeRuntime()
    runtime.add_candidate()
    runtime.containers[CANDIDATE_PORTAL]["labels"]["com.docker.compose.project"] = "other"
    runtime.containers[PRIOR_TUNNEL]["running"] = False

    receipt = run_reconcile(module, runtime, prior_state(), [True])

    assert receipt["status"] == "fail"
    assert CANDIDATE_PORTAL in runtime.containers
    assert receipt["componentChecks"]["candidatePortal"]["status"] == "fail"
    assert receipt["componentChecks"]["overlay"]["status"] == "fail"
    assert receipt["componentChecks"]["portal"]["status"] == "fail"
    assert runtime.container_running(PRIOR_TUNNEL) is False


def test_recovery_restores_prior_container_absence_without_impossible_proof_check() -> None:
    module = load_module()
    runtime = FakeRuntime()
    runtime.add_candidate()
    runtime.containers.pop(PRIOR_PORTAL)
    runtime.names.pop(PRIOR_PORTAL_NAME)
    runtime.services.pop("chummer-portal")
    runtime.containers[PRIOR_TUNNEL]["running"] = False

    receipt = run_reconcile(module, runtime, prior_state(portal_existed=False), [True])

    assert receipt["status"] == "pass"
    assert runtime.container_by_name(CANDIDATE_PORTAL_NAME) == ""
    assert receipt["componentChecks"]["runtimeProofMounts"] == {
        "status": "pass",
        "disposition": "not_applicable_prior_portal_absent",
    }
    assert runtime.container_running(PRIOR_TUNNEL) is True


def test_recovery_restores_prior_stopped_state_without_impossible_proof_check() -> None:
    module = load_module()
    runtime = FakeRuntime()
    runtime.containers[PRIOR_PORTAL]["running"] = False
    runtime.containers[PRIOR_TUNNEL]["running"] = False

    receipt = run_reconcile(module, runtime, prior_state(portal_running=False), [True])

    assert receipt["status"] == "pass"
    assert runtime.container_running(PRIOR_PORTAL) is False
    assert runtime.bound_proof_sha256 == CANDIDATE_PROOF_SHA256
    assert not any(action[0] == "proof-source" for action in runtime.actions)
    assert receipt["componentChecks"]["runtimeProofMounts"] == {
        "status": "pass",
        "disposition": "not_applicable_prior_portal_stopped",
    }
    assert runtime.container_running(PRIOR_TUNNEL) is True


def test_recovery_fails_closed_on_mismatched_old_authority_proof_mount() -> None:
    module = load_module()
    runtime = FakeRuntime()
    runtime.proof_digests[(PRIOR_PORTAL, module.PROOF_AUTHORITY_PATH)] = "7" * 64

    receipt = run_reconcile(module, runtime, prior_state(), [True])

    assert receipt["status"] == "fail"
    assert receipt["componentChecks"]["runtimeProofMounts"]["status"] == "fail"
    assert ("running", PRIOR_PORTAL, False) in runtime.actions
    assert ("running", PRIOR_TUNNEL, False) in runtime.actions


def test_recovery_fails_closed_when_old_public_proof_mount_is_missing() -> None:
    module = load_module()
    runtime = FakeRuntime()
    runtime.proof_digests.pop((PRIOR_PORTAL, module.PROOF_PUBLIC_PATH))

    receipt = run_reconcile(module, runtime, prior_state(), [True])

    assert receipt["status"] == "fail"
    assert receipt["componentChecks"]["runtimeProofMounts"]["status"] == "fail"
    assert ("running", PRIOR_PORTAL, False) in runtime.actions
    assert ("running", PRIOR_TUNNEL, False) in runtime.actions


def test_recovery_is_idempotent_after_exact_state_is_restored() -> None:
    module = load_module()
    runtime = FakeRuntime()
    first = run_reconcile(module, runtime, prior_state(), [True])
    runtime.actions.clear()

    second = run_reconcile(module, runtime, prior_state(), [True])

    assert first["status"] == "pass"
    assert second["status"] == "pass"
    assert runtime.actions == [
        ("proof-sha256", PRIOR_PORTAL, module.PROOF_AUTHORITY_PATH),
        ("proof-sha256", PRIOR_PORTAL, module.PROOF_PUBLIC_PATH),
    ]


def test_recovery_command_consumes_journal_and_writes_prior_runtime_authority(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = load_module()
    monkeypatch.setattr(
        module.transaction.overlay,
        "public_edge_mutation_lock",
        lambda **_kwargs: nullcontext(None),
    )
    monkeypatch.setattr(
        module.transaction.overlay,
        "overlay_publish_lock",
        lambda *_args, **_kwargs: nullcontext(None),
    )
    source_root, active_root, journal = write_deploy_journal(module, tmp_path)
    runtime = FakeRuntime()
    monkeypatch.setattr(module, "DockerRuntime", lambda **_kwargs: runtime)
    argv = recovery_argv(tmp_path, source_root, active_root)

    first_status = module.main(argv)
    first_receipt = json.loads((tmp_path / "recovery.json").read_text(encoding="utf-8"))
    authority = json.loads(
        (tmp_path / "active-runtime-authority.json").read_text(encoding="utf-8")
    )
    second_status = module.main(argv)
    second_receipt = json.loads((tmp_path / "recovery.json").read_text(encoding="utf-8"))

    assert first_status == 0
    assert first_receipt["exactPriorStateRestored"] is True
    assert authority["portal"]["containerId"] == PRIOR_PORTAL
    assert authority["portal"]["proofAuthorityMountSha256"] == PRIOR_PROOF_SHA256
    assert authority["portal"]["proofAuthorityMountSha256"] != CANDIDATE_PROOF_SHA256
    assert not journal.exists()
    assert second_status == 0
    assert second_receipt["disposition"] == "already_reconciled"


def test_recovery_command_retains_journal_when_prior_portal_identity_is_lost(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = load_module()
    monkeypatch.setattr(
        module.transaction.overlay,
        "public_edge_mutation_lock",
        lambda **_kwargs: nullcontext(None),
    )
    monkeypatch.setattr(
        module.transaction.overlay,
        "overlay_publish_lock",
        lambda *_args, **_kwargs: nullcontext(None),
    )
    source_root, active_root, journal = write_deploy_journal(module, tmp_path)
    runtime = FakeRuntime()
    runtime.add_candidate()
    runtime.containers.pop(PRIOR_PORTAL)
    runtime.names.pop(PRIOR_PORTAL_NAME)
    runtime.services.pop("chummer-portal")
    monkeypatch.setattr(module, "DockerRuntime", lambda **_kwargs: runtime)

    status = module.main(recovery_argv(tmp_path, source_root, active_root))
    receipt = json.loads((tmp_path / "recovery.json").read_text(encoding="utf-8"))

    assert status == 70
    assert receipt["status"] == "fail"
    assert receipt["exactPriorStateRestored"] is False
    assert CANDIDATE_PORTAL not in runtime.containers
    assert journal.exists()


def test_recovery_rejects_tampered_journal_generation_before_docker_or_journal_mutation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = load_module()
    monkeypatch.setattr(
        module.transaction.overlay,
        "public_edge_mutation_lock",
        lambda **_kwargs: nullcontext(None),
    )
    monkeypatch.setattr(
        module.transaction.overlay,
        "overlay_publish_lock",
        lambda *_args, **_kwargs: nullcontext(None),
    )
    source_root, active_root, journal = write_deploy_journal(module, tmp_path)
    argv = recovery_argv(tmp_path, source_root, active_root)
    journal_payload = json.loads(journal.read_text(encoding="utf-8"))
    snapshot_id = journal_payload["runtimePriorState"][
        "publicProjectionSnapshotId"
    ]
    manifest = (
        tmp_path
        / "public-projection"
        / snapshot_id
        / "PUBLIC_PROJECTION_SNAPSHOT.generated.json"
    )
    manifest.write_text("{}\n", encoding="utf-8")
    journal_before = journal.read_bytes()

    def unexpected_docker(**_kwargs):
        raise AssertionError("Docker recovery must not start after generation tamper")

    monkeypatch.setattr(module, "DockerRuntime", unexpected_docker)

    status = module.main(argv)
    receipt = json.loads((tmp_path / "recovery.json").read_text(encoding="utf-8"))

    assert status == 70
    assert receipt["status"] == "fail"
    assert "journal-bound public projection generation" in receipt["warning"]
    assert journal.read_bytes() == journal_before


def test_recovery_command_retains_journal_on_old_runtime_proof_mismatch(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = load_module()
    monkeypatch.setattr(
        module.transaction.overlay,
        "public_edge_mutation_lock",
        lambda **_kwargs: nullcontext(None),
    )
    monkeypatch.setattr(
        module.transaction.overlay,
        "overlay_publish_lock",
        lambda *_args, **_kwargs: nullcontext(None),
    )
    source_root, active_root, journal = write_deploy_journal(module, tmp_path)
    runtime = FakeRuntime()
    runtime.proof_digests[(PRIOR_PORTAL, module.PROOF_AUTHORITY_PATH)] = "0" * 64
    monkeypatch.setattr(module, "DockerRuntime", lambda **_kwargs: runtime)

    status = module.main(recovery_argv(tmp_path, source_root, active_root))
    receipt = json.loads((tmp_path / "recovery.json").read_text(encoding="utf-8"))

    assert status == 70
    assert receipt["componentChecks"]["runtimeProofMounts"]["status"] == "fail"
    assert journal.exists()
    assert ("running", PRIOR_PORTAL, False) in runtime.actions
    assert ("running", PRIOR_TUNNEL, False) in runtime.actions


def test_recovery_restores_s1_while_preserving_advanced_s2_current(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = load_module()
    monkeypatch.setattr(
        module.transaction.overlay,
        "public_edge_mutation_lock",
        lambda **_kwargs: nullcontext(None),
    )
    monkeypatch.setattr(
        module.transaction.overlay,
        "overlay_publish_lock",
        lambda *_args, **_kwargs: nullcontext(None),
    )
    source_root, active_root, journal = write_deploy_journal(module, tmp_path)
    argv = recovery_argv(tmp_path, source_root, active_root)
    projection_root = tmp_path / "public-projection"
    journal_payload = json.loads(journal.read_text(encoding="utf-8"))
    s1_snapshot_id = journal_payload["runtimePriorState"][
        "publicProjectionSnapshotId"
    ]
    write_public_projection_snapshot(
        projection_root,
        variant=b"advanced-s2\n",
    )
    advanced_current = (projection_root / "CURRENT.json").read_bytes()
    s2_identity = public_projection_identity(projection_root)
    assert s2_identity["publicProjectionSnapshotId"] != s1_snapshot_id
    runtime = FakeRuntime()
    monkeypatch.setattr(module, "DockerRuntime", lambda **_kwargs: runtime)

    status = module.main(argv)
    receipt = json.loads((tmp_path / "recovery.json").read_text(encoding="utf-8"))

    assert status == 0
    assert receipt["status"] == "pass"
    assert receipt["exactPriorStateRestored"] is True
    assert not journal.exists()
    assert (projection_root / "CURRENT.json").read_bytes() == advanced_current
    assert public_projection_identity(projection_root) == s2_identity
