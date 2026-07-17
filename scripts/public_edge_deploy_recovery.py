#!/usr/bin/env python3
"""Idempotently reconcile an interrupted standalone public-edge deployment."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
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
    portal_image_tag: str,
    tool_image_tag: str,
) -> dict[str, Any]:
    prior = transaction.validate_runtime_prior_state(runtime_prior_state)
    checks: dict[str, dict[str, Any]] = {}

    def reconcile_overlay() -> str:
        if overlay_matches():
            return "already_exact"
        for service in ("chummer-run-cloudflared", "chummer-portal"):
            container_id = runtime.service_container(service)
            if container_id and runtime.container_running(container_id):
                runtime.set_container_running(container_id, False)
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
    portal_passed = _component(
        checks,
        "portal",
        lambda: _restore_service(
            runtime,
            service="chummer-portal",
            prior_existed=prior["priorPortalExisted"],
            prior_container_id=prior["priorPortalContainerId"],
            prior_image_id=prior["priorPortalImageId"],
            prior_was_running=prior["priorPortalWasRunning"],
            may_start=overlay_passed and portal_tag_passed and tool_tag_passed,
        ),
    )
    expected_proof_sha256 = prior["expectedRuntimeProofBindSourceSha256"]

    def verify_runtime_proof_mounts() -> str:
        if (
            not portal_passed
            or not prior["priorPortalExisted"]
            or not prior["priorPortalWasRunning"]
        ):
            raise RuntimeError(
                "exact prior running portal is unavailable for proof verification"
            )
        portal_id = prior["priorPortalContainerId"]
        if (
            runtime.service_container("chummer-portal") != portal_id
            or not runtime.container_running(portal_id)
        ):
            raise RuntimeError(
                "exact prior running portal changed before proof verification"
            )
        try:
            authority_digest = runtime.container_file_sha256(
                portal_id,
                PROOF_AUTHORITY_PATH,
            )
            public_digest = runtime.container_file_sha256(
                portal_id,
                PROOF_PUBLIC_PATH,
            )
            if (
                authority_digest != expected_proof_sha256
                or public_digest != expected_proof_sha256
            ):
                raise RuntimeError(
                    "recovered runtime proof mounts do not match sealed authority"
                )
        except Exception:
            if runtime.container_running(portal_id):
                runtime.set_container_running(portal_id, False)
            raise
        return "both_runtime_proof_mounts_match_sealed_sha256"

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
                portal_image_tag=args.portal_image_tag,
                tool_image_tag=args.tool_image_tag,
            )
        payload["journalPhase"] = snapshot["phase"]
        if payload["status"] == "pass":
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
