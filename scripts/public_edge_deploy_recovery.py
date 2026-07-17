#!/usr/bin/env python3
"""Idempotently reconcile an interrupted standalone public-edge deployment."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import stat
import sys
from typing import Any, Callable, Protocol


def _load_transaction_module():
    module_path = Path(__file__).resolve().with_name(
        "public_edge_overlay_transaction.py"
    )
    spec = importlib.util.spec_from_file_location(
        "chummer_public_edge_overlay_transaction_recovery",
        module_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load public-edge overlay transaction authority")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


transaction = _load_transaction_module()

CONTRACT_NAME = "chummer.public-edge.deploy-recovery/v1"
PROOF_AUTHORITY_PATH = "/proofs/HUB_LOCAL_RELEASE_PROOF.generated.json"
PROOF_PUBLIC_PATH = (
    "/app/wwwroot/proofs/mac-codex-release/HUB_LOCAL_RELEASE_PROOF.generated.json"
)


class RuntimeAuthority(Protocol):
    def resolve_image_tag(self, tag: str) -> str: ...

    def image_exists(self, image_id: str) -> bool: ...

    def tag_image(self, image_id: str, tag: str) -> None: ...

    def remove_image_tag(self, tag: str) -> None: ...

    def service_container(self, service: str) -> str: ...

    def container_by_name(self, name: str) -> str: ...

    def container_exists(self, container_id: str) -> bool: ...

    def container_labels(self, container_id: str) -> dict[str, str]: ...

    def container_image(self, container_id: str) -> str: ...

    def container_running(self, container_id: str) -> bool: ...

    def set_container_running(self, container_id: str, running: bool) -> None: ...

    def remove_container(self, container_id: str) -> None: ...

    def container_file_sha256(self, container_id: str, path: str) -> str: ...


class DockerRuntime:
    def __init__(
        self,
        *,
        docker_config: Path,
        docker_context: str,
        compose_file: Path,
        env_file: Path,
        project_name: str,
        source_root: Path,
        build_context: Path,
        overlay_root: Path,
        published_port: int,
    ) -> None:
        self.environment = {
            "PATH": "/usr/bin:/bin",
            "HOME": str(docker_config / "home"),
            "DOCKER_CONFIG": str(docker_config / "config"),
            "LANG": "C",
            "LC_ALL": "C",
            "CHUMMER_PUBLIC_EDGE_BUILD_CONTEXT": str(build_context),
            "CHUMMER_RUN_SERVICES_CONTEXT_DIR": str(source_root),
            "CHUMMER_RUN_SERVICES_SOURCE": str(source_root),
            "CHUMMER_PUBLIC_PORTAL_APP_OVERLAY_DIR": str(overlay_root),
            "CHUMMER_PUBLIC_EDGE_PORT": str(published_port),
        }
        self.docker_base = [
            "/usr/bin/timeout",
            "--kill-after=5s",
            "60s",
            "/usr/bin/docker",
            "--context",
            docker_context,
        ]
        self.compose_base = [
            *self.docker_base,
            "compose",
            "--env-file",
            str(env_file),
            "-p",
            project_name,
            "-f",
            str(compose_file),
        ]
        self.project_name = project_name

    def _run(self, command: list[str], *, label: str) -> str:
        completed = subprocess.run(
            command,
            env=self.environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            timeout=75,
        )
        if completed.returncode != 0:
            raise RuntimeError(f"Docker recovery command failed: {label}")
        return completed.stdout.strip()

    def resolve_image_tag(self, tag: str) -> str:
        output = self._run(
            [
                *self.docker_base,
                "image",
                "ls",
                "--quiet",
                "--no-trunc",
                "--filter",
                f"reference={tag}",
            ],
            label="resolve image tag",
        )
        identities = tuple(dict.fromkeys(line for line in output.splitlines() if line))
        if len(identities) > 1:
            raise RuntimeError("Docker recovery image tag resolved ambiguously")
        return identities[0] if identities else ""

    def image_exists(self, image_id: str) -> bool:
        try:
            actual = self._run(
                [
                    *self.docker_base,
                    "image",
                    "inspect",
                    "--format",
                    "{{.Id}}",
                    image_id,
                ],
                label="inspect preserved image",
            )
        except RuntimeError:
            return False
        return actual == image_id

    def tag_image(self, image_id: str, tag: str) -> None:
        self._run(
            [*self.docker_base, "image", "tag", image_id, tag],
            label="restore image tag",
        )

    def remove_image_tag(self, tag: str) -> None:
        self._run(
            [*self.docker_base, "image", "rm", tag],
            label="restore image-tag absence",
        )

    def service_container(self, service: str) -> str:
        output = self._run(
            [*self.compose_base, "ps", "--all", "-q", service],
            label=f"resolve {service} container",
        )
        identities = tuple(line for line in output.splitlines() if line)
        if len(identities) > 1:
            raise RuntimeError(f"Docker recovery {service} container is ambiguous")
        if not identities:
            return ""
        return self._run(
            [
                *self.docker_base,
                "container",
                "inspect",
                "--format",
                "{{.Id}}",
                identities[0],
            ],
            label=f"canonicalize {service} container identity",
        )

    def container_by_name(self, name: str) -> str:
        output = self._run(
            [
                *self.docker_base,
                "container",
                "ls",
                "--all",
                "--quiet",
                "--no-trunc",
                "--filter",
                f"name=^/{name}$",
            ],
            label="resolve deployment candidate container",
        )
        identities = tuple(line for line in output.splitlines() if line)
        if len(identities) > 1:
            raise RuntimeError("deployment candidate container name is ambiguous")
        return identities[0] if identities else ""

    def container_exists(self, container_id: str) -> bool:
        output = self._run(
            [
                *self.docker_base,
                "container",
                "ls",
                "--all",
                "--quiet",
                "--no-trunc",
                "--filter",
                f"id={container_id}",
            ],
            label="resolve exact prior container",
        )
        identities = tuple(line for line in output.splitlines() if line)
        return identities == (container_id,)

    def container_labels(self, container_id: str) -> dict[str, str]:
        rendered = self._run(
            [
                *self.docker_base,
                "container",
                "inspect",
                "--format",
                "{{json .Config.Labels}}",
                container_id,
            ],
            label="inspect deployment candidate labels",
        )
        try:
            labels = json.loads(rendered)
        except (json.JSONDecodeError, TypeError) as exc:
            raise RuntimeError("deployment candidate labels are invalid") from exc
        if not isinstance(labels, dict) or not all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in labels.items()
        ):
            raise RuntimeError("deployment candidate labels are invalid")
        return labels

    def container_image(self, container_id: str) -> str:
        return self._run(
            [
                *self.docker_base,
                "container",
                "inspect",
                "--format",
                "{{.Image}}",
                container_id,
            ],
            label="inspect container image",
        )

    def container_running(self, container_id: str) -> bool:
        value = self._run(
            [
                *self.docker_base,
                "container",
                "inspect",
                "--format",
                "{{.State.Running}}",
                container_id,
            ],
            label="inspect container running state",
        )
        if value not in {"true", "false"}:
            raise RuntimeError("Docker recovery container running state is invalid")
        return value == "true"

    def set_container_running(self, container_id: str, running: bool) -> None:
        verb = "start" if running else "stop"
        self._run(
            [*self.docker_base, "container", verb, container_id],
            label=f"{verb} exact prior container",
        )

    def remove_container(self, container_id: str) -> None:
        self._run(
            [*self.docker_base, "container", "rm", "--force", container_id],
            label="restore prior container absence",
        )

    def container_file_sha256(self, container_id: str, path: str) -> str:
        rendered = self._run(
            [
                *self.docker_base,
                "container",
                "exec",
                container_id,
                "/usr/bin/sha256sum",
                "--",
                path,
            ],
            label="verify recovered runtime proof mount",
        )
        digest = rendered.split(" ", 1)[0]
        if (
            re.fullmatch(r"[0-9a-f]{64}", digest) is None
            or rendered != f"{digest}  {path}"
        ):
            raise RuntimeError("recovered runtime proof digest output is invalid")
        return digest


def _component(
    checks: dict[str, dict[str, Any]],
    name: str,
    action: Callable[[], str],
) -> bool:
    try:
        disposition = action()
    except Exception as exc:
        checks[name] = {
            "status": "fail",
            "disposition": "uncertain",
            "warning": str(exc),
        }
        return False
    checks[name] = {"status": "pass", "disposition": disposition}
    return True


def _restore_image_tag(
    runtime: RuntimeAuthority,
    *,
    tag: str,
    prior_image_id: str,
) -> str:
    current = runtime.resolve_image_tag(tag)
    if prior_image_id:
        if not runtime.image_exists(prior_image_id):
            raise RuntimeError("exact prior image is unavailable")
        if current != prior_image_id:
            runtime.tag_image(prior_image_id, tag)
        if runtime.resolve_image_tag(tag) != prior_image_id:
            raise RuntimeError("exact prior image tag was not restored")
        return "exact_prior_image_tag_restored"
    if current:
        runtime.remove_image_tag(tag)
    if runtime.resolve_image_tag(tag):
        raise RuntimeError("prior image-tag absence was not restored")
    return "prior_image_tag_absence_restored"


def _restore_service(
    runtime: RuntimeAuthority,
    *,
    service: str,
    prior_existed: bool,
    prior_container_id: str,
    prior_image_id: str,
    prior_was_running: bool,
    may_start: bool,
) -> str:
    current = runtime.service_container(service)
    if not prior_existed:
        if current:
            if runtime.container_running(current):
                runtime.set_container_running(current, False)
            runtime.remove_container(current)
        if runtime.service_container(service):
            raise RuntimeError(f"prior {service} absence was not restored")
        return "prior_container_absence_restored"

    if current != prior_container_id:
        if current and runtime.container_running(current):
            runtime.set_container_running(current, False)
        raise RuntimeError(f"exact prior {service} container identity is unavailable")
    if runtime.container_image(current) != prior_image_id:
        raise RuntimeError(f"exact prior {service} image identity drifted")
    running = runtime.container_running(current)
    if prior_was_running and not may_start:
        if running:
            runtime.set_container_running(current, False)
        raise RuntimeError(f"exact prior {service} cannot start before overlay recovery")
    if running != prior_was_running:
        runtime.set_container_running(current, prior_was_running)
    if (
        runtime.service_container(service) != prior_container_id
        or runtime.container_image(prior_container_id) != prior_image_id
        or runtime.container_running(prior_container_id) != prior_was_running
    ):
        raise RuntimeError(f"exact prior {service} runtime was not restored")
    return "exact_prior_container_state_restored"


def reconcile(
    *,
    runtime: RuntimeAuthority,
    runtime_prior_state: dict[str, Any],
    overlay_matches: Callable[[], bool],
    restore_overlay: Callable[[], None],
    proof_bind_source_matches_candidate: Callable[[], bool],
    prepare_prior_proof_bind: Callable[[], None],
    restore_candidate_proof_bind: Callable[[], None],
    portal_image_tag: str,
    tool_image_tag: str,
    project_name: str,
) -> dict[str, Any]:
    prior = transaction.validate_runtime_prior_state(runtime_prior_state)
    checks: dict[str, dict[str, Any]] = {}

    def remove_candidate_portal() -> str:
        candidate_name = prior["candidatePortalContainerName"]
        candidate_id = runtime.container_by_name(candidate_name)
        if not candidate_id:
            return "candidate_not_created"
        if candidate_id == prior["priorPortalContainerId"]:
            raise RuntimeError("candidate name resolves to the exact prior portal")
        labels = runtime.container_labels(candidate_id)
        if (
            labels.get("com.docker.compose.project") != project_name
            or labels.get("com.docker.compose.service") != "chummer-portal"
            or labels.get("com.docker.compose.oneoff", "").lower() != "true"
        ):
            raise RuntimeError("candidate container is outside deployment authority")
        if runtime.container_running(candidate_id):
            runtime.set_container_running(candidate_id, False)
        runtime.remove_container(candidate_id)
        if runtime.container_by_name(candidate_name):
            raise RuntimeError("candidate portal container was not removed")
        return "candidate_removed_without_touching_prior"

    candidate_removed = _component(
        checks,
        "candidatePortal",
        remove_candidate_portal,
    )

    def reconcile_overlay() -> str:
        if not candidate_removed:
            raise RuntimeError("candidate cleanup is uncertain before overlay recovery")
        if overlay_matches():
            return "already_exact"
        tunnel_id = runtime.service_container("chummer-run-cloudflared")
        if tunnel_id and runtime.container_running(tunnel_id):
            runtime.set_container_running(tunnel_id, False)
        prior_portal_id = prior["priorPortalContainerId"]
        if (
            prior_portal_id
            and runtime.container_exists(prior_portal_id)
            and runtime.container_running(prior_portal_id)
        ):
            runtime.set_container_running(prior_portal_id, False)
        restore_overlay()
        if not overlay_matches():
            raise RuntimeError("exact prior overlay was not restored")
        return "exact_prior_overlay_restored"

    overlay_passed = _component(checks, "overlay", reconcile_overlay)
    portal_tag_passed = _component(
        checks,
        "portalImageTag",
        lambda: _restore_image_tag(
            runtime,
            tag=portal_image_tag,
            prior_image_id=prior["priorImageTagId"],
        ),
    )
    tool_tag_passed = _component(
        checks,
        "toolImageTag",
        lambda: _restore_image_tag(
            runtime,
            tag=tool_image_tag,
            prior_image_id=prior["priorToolImageTagId"],
        ),
    )

    def restore_portal_identity() -> str:
        if not candidate_removed:
            raise RuntimeError("candidate portal cleanup is uncertain")
        if not prior["priorPortalExisted"]:
            if runtime.service_container("chummer-portal"):
                raise RuntimeError("prior portal absence was not restored")
            return "prior_portal_absence_restored"
        portal_id = prior["priorPortalContainerId"]
        if not runtime.container_exists(portal_id):
            raise RuntimeError("exact prior portal container identity is unavailable")
        if runtime.container_by_name(prior["priorPortalContainerName"]) != portal_id:
            raise RuntimeError("exact prior portal name identity is unavailable")
        if runtime.container_image(portal_id) != prior["priorPortalImageId"]:
            raise RuntimeError("exact prior portal image identity drifted")
        if not prior["priorPortalWasRunning"] and runtime.container_running(portal_id):
            runtime.set_container_running(portal_id, False)
        if (
            runtime.container_image(portal_id) != prior["priorPortalImageId"]
            or (
                not prior["priorPortalWasRunning"]
                and runtime.container_running(portal_id)
            )
        ):
            raise RuntimeError("exact prior portal state was not restored")
        return (
            "exact_prior_portal_preserved_running_or_startable"
            if prior["priorPortalWasRunning"]
            else "exact_prior_stopped_portal_restored"
        )

    portal_passed = _component(
        checks,
        "portal",
        restore_portal_identity,
    )

    def ensure_candidate_proof_source() -> None:
        if not proof_bind_source_matches_candidate():
            restore_candidate_proof_bind()
        if not proof_bind_source_matches_candidate():
            raise RuntimeError("candidate proof bind source was not restored")

    def verify_runtime_proof_mounts() -> str:
        if not (
            portal_passed
            and overlay_passed
            and portal_tag_passed
            and tool_tag_passed
        ):
            raise RuntimeError("prior portal recovery prerequisites are incomplete")
        if not prior["priorPortalExisted"]:
            ensure_candidate_proof_source()
            return "not_applicable_prior_portal_absent"
        portal_id = prior["priorPortalContainerId"]
        if not prior["priorPortalWasRunning"]:
            if runtime.container_running(portal_id):
                runtime.set_container_running(portal_id, False)
            ensure_candidate_proof_source()
            return "not_applicable_prior_portal_stopped"
        try:
            if not runtime.container_running(portal_id):
                prepare_prior_proof_bind()
                try:
                    runtime.set_container_running(portal_id, True)
                finally:
                    restore_candidate_proof_bind()
            ensure_candidate_proof_source()
            if not runtime.container_running(portal_id):
                raise RuntimeError("exact prior portal did not restart")
            authority_digest = runtime.container_file_sha256(
                portal_id,
                PROOF_AUTHORITY_PATH,
            )
            public_digest = runtime.container_file_sha256(
                portal_id,
                PROOF_PUBLIC_PATH,
            )
            if (
                authority_digest
                != prior["priorPortalProofAuthorityMountSha256"]
                or public_digest != prior["priorPortalProofPublicMountSha256"]
            ):
                raise RuntimeError(
                    "recovered prior runtime proof mounts changed identity"
                )
        except Exception:
            if runtime.container_running(portal_id):
                runtime.set_container_running(portal_id, False)
            raise
        return "both_prior_runtime_proof_mounts_match_journaled_digests"

    proof_mounts_passed = _component(
        checks,
        "runtimeProofMounts",
        verify_runtime_proof_mounts,
    )

    def restore_tunnel() -> str:
        if not proof_mounts_passed:
            current_tunnel = runtime.service_container("chummer-run-cloudflared")
            if current_tunnel and runtime.container_running(current_tunnel):
                runtime.set_container_running(current_tunnel, False)
            raise RuntimeError(
                "tunnel restoration is blocked by runtime proof verification"
            )
        return _restore_service(
            runtime,
            service="chummer-run-cloudflared",
            prior_existed=prior["priorTunnelExisted"],
            prior_container_id=prior["priorTunnelContainerId"],
            prior_image_id=prior["priorTunnelImageId"],
            prior_was_running=prior["priorTunnelWasRunning"],
            may_start=True,
        )

    _component(checks, "tunnel", restore_tunnel)
    passed = all(check["status"] == "pass" for check in checks.values())
    return {
        "contractName": CONTRACT_NAME,
        "operation": "reconcile",
        "status": "pass" if passed else "fail",
        "exactPriorStateRestored": passed,
        "componentChecks": checks,
    }


def atomic_write(path: Path, payload: dict[str, Any]) -> None:
    transaction.overlay.atomic_write_json(
        transaction.overlay.normalized_absolute_path(path),
        payload,
    )


def fsync_directory(path: Path) -> None:
    descriptor = os.open(
        path,
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_CLOEXEC", 0),
    )
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def stable_file_sha256(path: Path, *, label: str) -> str:
    payload, _metadata = transaction.overlay.read_stable_regular_bytes(
        path,
        label=label,
    )
    return hashlib.sha256(payload).hexdigest()


def atomic_replace_from_snapshot(
    *,
    snapshot: Path,
    destination: Path,
    expected_sha256: str,
) -> None:
    snapshot = transaction.overlay.normalized_absolute_path(snapshot)
    destination = transaction.overlay.normalized_absolute_path(destination)
    payload, _snapshot_metadata = transaction.overlay.read_stable_regular_bytes(
        snapshot,
        label="runtime proof recovery snapshot",
    )
    if hashlib.sha256(payload).hexdigest() != expected_sha256:
        raise RuntimeError("runtime proof recovery snapshot digest changed")
    transaction.overlay.assert_no_symlink_components(
        destination,
        label="runtime proof bind source",
    )
    destination_metadata = destination.lstat()
    if (
        not stat.S_ISREG(destination_metadata.st_mode)
        or stat.S_ISLNK(destination_metadata.st_mode)
        or destination_metadata.st_nlink != 1
        or destination_metadata.st_uid != os.getuid()
    ):
        raise RuntimeError("runtime proof bind source identity is unsafe")
    temporary = destination.parent / (
        f".{destination.name}.recovery-{os.getpid()}-{secrets.token_hex(8)}"
    )
    descriptor = os.open(
        temporary,
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        os.fchmod(descriptor, stat.S_IMODE(destination_metadata.st_mode))
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise RuntimeError("runtime proof snapshot write made no progress")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    try:
        os.replace(temporary, destination)
        fsync_directory(destination.parent)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
    if stable_file_sha256(
        destination,
        label="restored runtime proof bind source",
    ) != expected_sha256:
        raise RuntimeError("runtime proof bind source replacement did not commit")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Reconcile an interrupted standalone public-edge deployment."
    )
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--active-root", type=Path, required=True)
    parser.add_argument("--backup-root", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--activation-receipt", type=Path, required=True)
    parser.add_argument("--overlay-rollback-output", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--runtime-authority-output", type=Path, required=True)
    parser.add_argument("--shared-mutation-lock-token", required=True)
    parser.add_argument("--docker-config-root", type=Path, required=True)
    parser.add_argument("--docker-context", required=True)
    parser.add_argument("--compose-file", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--project-name", required=True)
    parser.add_argument("--build-context", type=Path, required=True)
    parser.add_argument("--published-port", type=int, required=True)
    parser.add_argument("--portal-image-tag", required=True)
    parser.add_argument("--tool-image-tag", required=True)
    parser.add_argument(
        "--expected-runtime-proof-bind-source-sha256",
        required=True,
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    snapshot_path = transaction.overlay.normalized_absolute_path(args.snapshot)
    output_path = transaction.overlay.normalized_absolute_path(args.output)
    expected_proof_sha256 = str(
        args.expected_runtime_proof_bind_source_sha256
    )
    if re.fullmatch(r"[0-9a-f]{64}", expected_proof_sha256) is None:
        payload = {
            "contractName": CONTRACT_NAME,
            "operation": "reconcile",
            "status": "fail",
            "exactPriorStateRestored": False,
            "warning": "recovery proof authority SHA-256 is invalid",
        }
        atomic_write(output_path, payload)
        print(json.dumps(payload, sort_keys=True))
        return 70
    if not snapshot_path.exists() and not snapshot_path.is_symlink():
        payload = {
            "contractName": CONTRACT_NAME,
            "operation": "reconcile",
            "status": "pass",
            "exactPriorStateRestored": True,
            "disposition": "already_reconciled",
            "componentChecks": {},
        }
        atomic_write(output_path, payload)
        print(json.dumps(payload, sort_keys=True))
        return 0
    try:
        snapshot = transaction.validated_deploy_snapshot(
            snapshot_path,
            source_root=args.source_root,
            active_root=args.active_root,
        )
        if (
            snapshot["runtimePriorState"][
                "expectedRuntimeProofBindSourceSha256"
            ]
            != expected_proof_sha256
        ):
            raise RuntimeError(
                "recovery proof authority does not match its durable journal"
            )
        runtime = DockerRuntime(
            docker_config=args.docker_config_root,
            docker_context=args.docker_context,
            compose_file=args.compose_file,
            env_file=args.env_file,
            project_name=args.project_name,
            source_root=args.source_root,
            build_context=args.build_context,
            overlay_root=args.active_root,
            published_port=args.published_port,
        )
        deploy_authority = snapshot["deployOverlayAuthority"]
        prior = snapshot["runtimePriorState"]
        proof_bind_source = Path(deploy_authority["proofBindSourcePath"])
        candidate_proof_snapshot = Path(
            deploy_authority["candidateProofBindSourceSnapshot"]
        )

        def proof_bind_source_matches_candidate() -> bool:
            try:
                return stable_file_sha256(
                    proof_bind_source,
                    label="runtime proof bind source",
                ) == prior["expectedRuntimeProofBindSourceSha256"]
            except (OSError, RuntimeError):
                return False

        def restore_candidate_proof_bind() -> None:
            atomic_replace_from_snapshot(
                snapshot=candidate_proof_snapshot,
                destination=proof_bind_source,
                expected_sha256=prior[
                    "expectedRuntimeProofBindSourceSha256"
                ],
            )

        def prepare_prior_proof_bind() -> None:
            snapshot_value = deploy_authority[
                "priorPortalProofAuthoritySnapshot"
            ]
            if not snapshot_value:
                raise RuntimeError("prior portal proof snapshot is unavailable")
            atomic_replace_from_snapshot(
                snapshot=Path(snapshot_value),
                destination=proof_bind_source,
                expected_sha256=prior[
                    "priorPortalProofAuthorityMountSha256"
                ],
            )

        def overlay_matches() -> bool:
            return transaction.prior_overlay_matches_snapshot(
                snapshot,
                active_root=args.active_root,
            )

        def restore_overlay() -> None:
            result = transaction.restore(
                source_root=args.source_root,
                active_root=args.active_root,
                backup_root=args.backup_root,
                snapshot_path=snapshot_path,
                activation_receipt=args.activation_receipt,
                output=args.overlay_rollback_output,
                shared_mutation_lock_token=args.shared_mutation_lock_token,
            )
            if result.get("status") != "pass":
                raise RuntimeError("exact prior overlay restoration failed")

        with transaction.overlay.public_edge_mutation_lock(
            activate=True,
            inherited_token=args.shared_mutation_lock_token,
        ):
            payload = reconcile(
                runtime=runtime,
                runtime_prior_state=snapshot["runtimePriorState"],
                overlay_matches=overlay_matches,
                restore_overlay=restore_overlay,
                proof_bind_source_matches_candidate=(
                    proof_bind_source_matches_candidate
                ),
                prepare_prior_proof_bind=prepare_prior_proof_bind,
                restore_candidate_proof_bind=restore_candidate_proof_bind,
                portal_image_tag=args.portal_image_tag,
                tool_image_tag=args.tool_image_tag,
                project_name=args.project_name,
            )
            payload["journalPhase"] = snapshot["phase"]
            if payload["status"] == "pass":
                runtime_authority = transaction.active_runtime_authority_payload(
                    portal_existed=prior["priorPortalExisted"],
                    portal_container_id=prior["priorPortalContainerId"],
                    portal_container_name=prior["priorPortalContainerName"],
                    portal_image_id=prior["priorPortalImageId"],
                    portal_was_running=prior["priorPortalWasRunning"],
                    proof_authority_mount_sha256=prior[
                        "priorPortalProofAuthorityMountSha256"
                    ],
                    proof_public_mount_sha256=prior[
                        "priorPortalProofPublicMountSha256"
                    ],
                )
                atomic_write(args.runtime_authority_output, runtime_authority)
                snapshot_path.unlink()
                fsync_directory(snapshot_path.parent)
    except Exception as exc:
        payload = {
            "contractName": CONTRACT_NAME,
            "operation": "reconcile",
            "status": "fail",
            "exactPriorStateRestored": False,
            "warning": str(exc),
        }
    atomic_write(output_path, payload)
    print(json.dumps(payload, sort_keys=True))
    return 0 if payload.get("status") == "pass" else 70


if __name__ == "__main__":
    raise SystemExit(main())
