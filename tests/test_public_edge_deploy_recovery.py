from __future__ import annotations

import importlib.util
import json
from contextlib import nullcontext
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "public_edge_deploy_recovery.py"
PORTAL_TAG = "chummer-run-api:local"
TOOL_TAG = "chummer-install-linking-postgres-tool:local"
PRIOR_PORTAL_IMAGE = "sha256:" + "1" * 64
PRIOR_TOOL_IMAGE = "sha256:" + "2" * 64
PRIOR_TUNNEL_IMAGE = "sha256:" + "3" * 64
CANDIDATE_PORTAL_IMAGE = "sha256:" + "4" * 64
CANDIDATE_TOOL_IMAGE = "sha256:" + "5" * 64
PRIOR_PORTAL = "a" * 64
PRIOR_TUNNEL = "b" * 64
CANDIDATE_PORTAL = "c" * 64
CANDIDATE_TUNNEL = "d" * 64
EXPECTED_PROOF_SHA256 = "6" * 64


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
        self.containers = {
            PRIOR_PORTAL: {"image": PRIOR_PORTAL_IMAGE, "running": True},
            PRIOR_TUNNEL: {"image": PRIOR_TUNNEL_IMAGE, "running": True},
        }
        self.proof_digests = {
            (PRIOR_PORTAL, "/proofs/HUB_LOCAL_RELEASE_PROOF.generated.json"): (
                EXPECTED_PROOF_SHA256
            ),
            (
                PRIOR_PORTAL,
                "/app/wwwroot/proofs/mac-codex-release/"
                "HUB_LOCAL_RELEASE_PROOF.generated.json",
            ): EXPECTED_PROOF_SHA256,
        }
        self.actions: list[tuple[object, ...]] = []

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
) -> dict[str, object]:
    return {
        "expectedRuntimeProofBindSourceSha256": EXPECTED_PROOF_SHA256,
        "priorImageTagId": PRIOR_PORTAL_IMAGE,
        "priorToolImageTagId": PRIOR_TOOL_IMAGE,
        "priorPortalContainerId": PRIOR_PORTAL if portal_existed else "",
        "priorPortalImageId": PRIOR_PORTAL_IMAGE if portal_existed else "",
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

    return module.reconcile(
        runtime=runtime,
        runtime_prior_state=state,
        overlay_matches=lambda: overlay[0],
        restore_overlay=restore_overlay,
        portal_image_tag=PORTAL_TAG,
        tool_image_tag=TOOL_TAG,
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
        "chummer6-hub",
        "--build-context",
        str(tmp_path),
        "--published-port",
        "8091",
        "--portal-image-tag",
        PORTAL_TAG,
        "--tool-image-tag",
        TOOL_TAG,
        "--expected-runtime-proof-bind-source-sha256",
        EXPECTED_PROOF_SHA256,
    ]


def write_deploy_journal(module, tmp_path: Path) -> tuple[Path, Path, Path]:
    source_root = tmp_path / "source"
    active_root = tmp_path / "active" / "app"
    staging_root = tmp_path / "staging" / "app"
    backup_root = tmp_path / "backups"
    source_root.mkdir()
    active_root.mkdir(parents=True)
    staging_root.mkdir(parents=True)
    backup_root.mkdir()
    (active_root / "payload.txt").write_text("prior\n", encoding="utf-8")
    (staging_root / "payload.txt").write_text("candidate\n", encoding="utf-8")
    journal = tmp_path / "journal.json"
    module.transaction.snapshot(
        source_root=source_root,
        active_root=active_root,
        output=journal,
        shared_mutation_lock_token="f" * 64,
        runtime_prior_state=prior_state(),
        staging_root=staging_root,
        backup_root=backup_root,
        activation_receipt=tmp_path / "activation.json",
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


def test_hard_crash_after_overlay_exchange_restores_exact_overlay_and_runtime() -> None:
    module = load_module()
    runtime = FakeRuntime()
    runtime.tags[PORTAL_TAG] = CANDIDATE_PORTAL_IMAGE
    runtime.tags[TOOL_TAG] = CANDIDATE_TOOL_IMAGE
    runtime.containers[PRIOR_PORTAL]["running"] = False
    runtime.containers[PRIOR_TUNNEL]["running"] = False
    overlay = [False]

    receipt = run_reconcile(module, runtime, prior_state(), overlay)

    assert receipt["status"] == "pass"
    assert overlay == [True]
    assert ("restore-overlay",) in runtime.actions
    assert ("running", PRIOR_PORTAL, True) in runtime.actions
    assert ("running", PRIOR_TUNNEL, True) in runtime.actions
    public_proof_check = runtime.actions.index(
        ("proof-sha256", PRIOR_PORTAL, module.PROOF_PUBLIC_PATH)
    )
    tunnel_restart = runtime.actions.index(("running", PRIOR_TUNNEL, True))
    assert public_proof_check < tunnel_restart


def test_compose_failure_before_replacement_leaves_exact_prior_container_alone() -> None:
    module = load_module()
    runtime = FakeRuntime()
    # Compose returned failure before replacing the stopped prior container.
    runtime.containers[PRIOR_PORTAL]["running"] = False

    receipt = run_reconcile(module, runtime, prior_state(), [True])

    assert receipt["status"] == "pass"
    assert runtime.services["chummer-portal"] == PRIOR_PORTAL
    assert ("running", PRIOR_PORTAL, True) in runtime.actions
    assert not any(action[0] == "remove-container" for action in runtime.actions)


def test_replaced_prior_portal_is_honestly_fail_closed_and_tunnel_stays_drained() -> None:
    module = load_module()
    runtime = FakeRuntime()
    runtime.services["chummer-portal"] = CANDIDATE_PORTAL
    runtime.containers.pop(PRIOR_PORTAL)
    runtime.containers[CANDIDATE_PORTAL] = {
        "image": CANDIDATE_PORTAL_IMAGE,
        "running": True,
    }
    runtime.containers[PRIOR_TUNNEL]["running"] = False

    receipt = run_reconcile(module, runtime, prior_state(), [True])

    assert receipt["status"] == "fail"
    assert receipt["exactPriorStateRestored"] is False
    assert receipt["componentChecks"]["portal"]["status"] == "fail"
    assert receipt["componentChecks"]["runtimeProofMounts"]["status"] == "fail"
    assert receipt["componentChecks"]["tunnel"]["status"] == "fail"
    assert ("running", CANDIDATE_PORTAL, False) in runtime.actions
    assert ("running", PRIOR_TUNNEL, True) not in runtime.actions


def test_recovery_restores_prior_container_absence_but_retains_proof_gate() -> None:
    module = load_module()
    runtime = FakeRuntime()
    runtime.services["chummer-portal"] = CANDIDATE_PORTAL
    runtime.containers.pop(PRIOR_PORTAL)
    runtime.containers[CANDIDATE_PORTAL] = {
        "image": CANDIDATE_PORTAL_IMAGE,
        "running": True,
    }

    receipt = run_reconcile(
        module,
        runtime,
        prior_state(portal_existed=False),
        [True],
    )

    assert receipt["status"] == "fail"
    assert runtime.service_container("chummer-portal") == ""
    assert ("remove-container", CANDIDATE_PORTAL) in runtime.actions
    assert receipt["componentChecks"]["runtimeProofMounts"]["status"] == "fail"


def test_recovery_fails_closed_on_mismatched_authority_proof_mount() -> None:
    module = load_module()
    runtime = FakeRuntime()
    runtime.proof_digests[(PRIOR_PORTAL, module.PROOF_AUTHORITY_PATH)] = "7" * 64

    receipt = run_reconcile(module, runtime, prior_state(), [True])

    assert receipt["status"] == "fail"
    assert receipt["componentChecks"]["runtimeProofMounts"]["status"] == "fail"
    assert ("running", PRIOR_PORTAL, False) in runtime.actions
    assert ("running", PRIOR_TUNNEL, False) in runtime.actions


def test_recovery_fails_closed_when_public_proof_mount_is_missing() -> None:
    module = load_module()
    runtime = FakeRuntime()
    runtime.proof_digests.pop((PRIOR_PORTAL, module.PROOF_PUBLIC_PATH))

    receipt = run_reconcile(module, runtime, prior_state(), [True])

    assert receipt["status"] == "fail"
    assert receipt["componentChecks"]["runtimeProofMounts"]["status"] == "fail"
    assert ("running", PRIOR_PORTAL, False) in runtime.actions
    assert ("running", PRIOR_TUNNEL, False) in runtime.actions


def test_recovery_fails_closed_when_prior_portal_is_not_running() -> None:
    module = load_module()
    runtime = FakeRuntime()
    runtime.containers[PRIOR_PORTAL]["running"] = False

    receipt = run_reconcile(
        module,
        runtime,
        prior_state(portal_running=False),
        [True],
    )

    assert receipt["status"] == "fail"
    assert receipt["componentChecks"]["portal"]["status"] == "pass"
    assert receipt["componentChecks"]["runtimeProofMounts"]["status"] == "fail"
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


def test_recovery_command_consumes_journal_and_is_idempotent(
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
    first_receipt = json.loads(
        (tmp_path / "recovery.json").read_text(encoding="utf-8")
    )
    second_status = module.main(argv)
    second_receipt = json.loads(
        (tmp_path / "recovery.json").read_text(encoding="utf-8")
    )

    assert first_status == 0
    assert first_receipt["exactPriorStateRestored"] is True
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
    runtime.services["chummer-portal"] = CANDIDATE_PORTAL
    runtime.containers.pop(PRIOR_PORTAL)
    runtime.containers[CANDIDATE_PORTAL] = {
        "image": CANDIDATE_PORTAL_IMAGE,
        "running": True,
    }
    monkeypatch.setattr(module, "DockerRuntime", lambda **_kwargs: runtime)

    status = module.main(recovery_argv(tmp_path, source_root, active_root))
    receipt = json.loads(
        (tmp_path / "recovery.json").read_text(encoding="utf-8")
    )

    assert status == 70
    assert receipt["status"] == "fail"
    assert receipt["exactPriorStateRestored"] is False
    assert journal.exists()


def test_recovery_command_rejects_external_proof_authority_mismatch(
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
    argv[-1] = "9" * 64

    status = module.main(argv)
    receipt = json.loads(
        (tmp_path / "recovery.json").read_text(encoding="utf-8")
    )

    assert status == 70
    assert receipt["status"] == "fail"
    assert "durable journal" in receipt["warning"]
    assert journal.exists()


def test_recovery_command_retains_journal_on_runtime_proof_mismatch(
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
    receipt = json.loads(
        (tmp_path / "recovery.json").read_text(encoding="utf-8")
    )

    assert status == 70
    assert receipt["componentChecks"]["runtimeProofMounts"]["status"] == "fail"
    assert journal.exists()
    assert ("running", PRIOR_PORTAL, False) in runtime.actions
    assert ("running", PRIOR_TUNNEL, False) in runtime.actions
