from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
CONTROLLER_PATH = ROOT / "scripts" / "deploy_public_download_only_cutover.py"
GENERATION_PATH = ROOT / "scripts" / "release_shelf_generation.py"


def load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


controller = load_module(CONTROLLER_PATH, "topology_b_controller_contract")
generation = load_module(GENERATION_PATH, "topology_b_generation_contract")

HOSTS = ("chummer.run", "www.chummer.run")
VOLUME_ROLES = (
    "app",
    "fleet",
    "state",
    "upload_sessions",
    "windows_proof",
    "windows_proof_upload",
    "runtime_secrets",
    "projection",
    "proofs",
    "shelf",
)


def require_topology_b_surface() -> None:
    missing = [
        name
        for name in (
            "SidecarConfig",
            "TopologyBRunner",
            "TopologyBActions",
            "tree_sha256_file_stream",
            "generate_sidecar_data_protection",
            "prepare_sidecar_release_shelf",
            "materialize_sidecar_compose",
            "probe_sidecar_hosts",
            "probe_public_incumbent",
            "execute_topology_b",
            "recover_topology_b",
        )
        if not hasattr(controller, name)
    ]
    assert not missing, f"topology-B controller surface is incomplete: {missing}"


def function_node(name: str) -> ast.FunctionDef:
    tree = ast.parse(CONTROLLER_PATH.read_text(encoding="utf-8"))
    matches = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == name
    ]
    assert len(matches) == 1, f"expected one controller function named {name}"
    return matches[0]


def call_leaf_names(node: ast.AST) -> set[str]:
    names: set[str] = set()
    for candidate in ast.walk(node):
        if not isinstance(candidate, ast.Call):
            continue
        function = candidate.func
        if isinstance(function, ast.Name):
            names.add(function.id)
        elif isinstance(function, ast.Attribute):
            names.add(function.attr)
    return names


def topology_b_config(tmp_path: Path) -> SimpleNamespace:
    operation_root = tmp_path / "chummer-public-download-op-a1b2c3d4"
    operation_root.mkdir(mode=0o700)
    canonical_shelf = tmp_path / "canonical-release-shelf"
    canonical_shelf.mkdir()
    canonical_payload = canonical_shelf / "sentinel"
    canonical_payload.write_bytes(b"incumbent shelf must remain unchanged\n")
    dp_root = operation_root / "inputs" / "data-protection"
    dp_root.mkdir(parents=True, mode=0o700)
    certificate = dp_root / "sidecar.pfx"
    password = dp_root / "sidecar.password"
    certificate.write_bytes(b"operation-only certificate")
    password.write_bytes(b"operation-only password")
    certificate.chmod(0o600)
    password.chmod(0o600)
    project_name = operation_root.name
    return SimpleNamespace(
        operation="initial-release-shelf-public-download-cutover",
        operation_root=operation_root,
        project_name=project_name,
        bind_address="172.17.0.1",
        bind_port=18091,
        volume_names={
            role: f"{project_name}-{role.replace('_', '-')}"
            for role in VOLUME_ROLES
        },
        canonical_project="chummer6-hub",
        canonical_shelf_root=canonical_shelf,
        canonical_shelf_sentinel=canonical_payload,
        sidecar_dp_certificate=certificate,
        sidecar_dp_password=password,
        cloudflare_journal=operation_root / "cloudflare-live.json",
        cloudflare_committed_evidence=(
            operation_root / "cloudflare-committed.json"
        ),
        cloudflare_rollback_evidence=(
            operation_root / "cloudflare-rolled-back.json"
        ),
        base_url="https://chummer.run",
    )


class RecordingActions:
    """Mocked action boundary approved for the topology-B controller."""

    def __init__(
        self,
        *,
        fail_at: str | None = None,
        recovery_disposition: str = "rollback",
    ) -> None:
        self.events: list[str] = []
        self.fail_at = fail_at
        self.recovery_disposition = recovery_disposition

    def record(self, event: str, result: Any = None) -> Any:
        self.events.append(event)
        if self.fail_at == event:
            raise RuntimeError(f"forced failure at {event}")
        return result if result is not None else {"event": event}

    def prepare_sidecar_release_shelf(self, config: Any) -> dict[str, Any]:
        before = config.canonical_shelf_sentinel.read_bytes()
        result = self.record(
            "prepare_shelf",
            {
                "pointerSha256": "1" * 64,
                "activationCandidateSha256": "2" * 64,
                "canonicalMirrorSha256": "3" * 64,
                "compatibilityMirrorSha256": "4" * 64,
                "writerPolicy": "sidecar-readonly-v1",
            },
        )
        assert config.canonical_shelf_sentinel.read_bytes() == before
        return result

    def generate_sidecar_data_protection(self, config: Any) -> dict[str, Any]:
        assert config.sidecar_dp_certificate.is_relative_to(
            config.operation_root
        )
        assert config.sidecar_dp_password.is_relative_to(config.operation_root)
        return self.record(
            "generate_dp",
            {
                "certificate": str(config.sidecar_dp_certificate),
                "certificateSha256": hashlib.sha256(
                    config.sidecar_dp_certificate.read_bytes()
                ).hexdigest(),
                "password": str(config.sidecar_dp_password),
                "passwordSha256": hashlib.sha256(
                    config.sidecar_dp_password.read_bytes()
                ).hexdigest(),
            },
        )

    def materialize_sidecar_compose(self, config: Any, *_args: Any) -> dict[str, Any]:
        return self.record(
            "materialize_compose",
            {
                "projectName": config.project_name,
                "publishedAddress": config.bind_address,
                "publishedPort": config.bind_port,
                "volumes": dict(config.volume_names),
            },
        )

    def create_sidecar_resources(self, config: Any, *_args: Any) -> dict[str, Any]:
        assert config.project_name != config.canonical_project
        assert config.bind_address == "172.17.0.1"
        assert config.bind_port == 18091
        assert tuple(config.volume_names) == VOLUME_ROLES
        assert len(set(config.volume_names.values())) == 10
        assert all(
            name.startswith(f"{config.project_name}-")
            for name in config.volume_names.values()
        )
        return self.record("create_resources")

    def start_sidecar_runtime(self, _config: Any, *_args: Any) -> dict[str, Any]:
        return self.record("start_sidecar", {"containerId": "a" * 64})

    def wait_sidecar_healthy(self, _config: Any, *_args: Any) -> dict[str, Any]:
        return self.record("sidecar_healthy", {"status": "healthy"})

    def probe_sidecar_hosts(
        self,
        _config: Any,
        *_args: Any,
        hosts: tuple[str, ...],
        scope: str,
        **_kwargs: Any,
    ) -> dict[str, Any]:
        assert hosts == HOSTS
        assert scope in {"local", "public"}
        return self.record(f"probe_{scope}_{','.join(hosts)}")

    def probe_public_incumbent(
        self,
        _config: Any,
        *,
        phase: str,
        hosts: tuple[str, ...],
        **_kwargs: Any,
    ) -> dict[str, Any]:
        assert phase in {"before-cloudflare", "after-rollback"}
        assert hosts == HOSTS
        return self.record(
            f"probe_incumbent_{phase}_{','.join(hosts)}"
        )

    def capture_cloudflare(self, _config: Any, *_args: Any) -> dict[str, Any]:
        return self.record("cloudflare_capture")

    def apply_cloudflare(self, _config: Any, *_args: Any) -> dict[str, Any]:
        return self.record("cloudflare_apply")

    def commit_cloudflare(self, _config: Any, *_args: Any) -> dict[str, Any]:
        return self.record("cloudflare_commit")

    def write_active_receipt(self, _config: Any, *_args: Any) -> dict[str, Any]:
        return self.record("write_active_receipt")

    def rollback_cloudflare(self, _config: Any, *_args: Any) -> dict[str, Any]:
        return self.record("cloudflare_rollback")

    def cleanup_sidecar_resources(
        self, _config: Any, *_args: Any
    ) -> dict[str, Any]:
        return self.record("cleanup_sidecar")

    def classify_recovery(self, _config: Any) -> str:
        self.record(f"classify_recovery_{self.recovery_disposition}")
        return self.recovery_disposition

    def reconcile_committed(self, _config: Any, *_args: Any) -> dict[str, Any]:
        return self.record("reconcile_committed")


SUCCESS_EVENTS = [
    "prepare_shelf",
    "generate_dp",
    "materialize_compose",
    "create_resources",
    "start_sidecar",
    "sidecar_healthy",
    "probe_local_chummer.run,www.chummer.run",
    "probe_incumbent_before-cloudflare_chummer.run,www.chummer.run",
    "cloudflare_capture",
    "cloudflare_apply",
    "probe_public_chummer.run,www.chummer.run",
    "cloudflare_commit",
    "write_active_receipt",
]


def test_topology_b_surface_and_dispatch_replace_topology_a() -> None:
    require_topology_b_surface()
    execute = function_node("execute")
    calls = call_leaf_names(execute)
    assert calls == {"execute_topology_b"}

    parse_args = function_node("parse_args")
    parse_calls = call_leaf_names(parse_args)
    assert "SidecarConfig" in parse_calls
    assert "Config" not in parse_calls
    assert "_retired_topology_a_parse_args" not in parse_calls

    main = function_node("main")
    main_calls = call_leaf_names(main)
    assert "parse_args" in main_calls
    assert "execute" in main_calls
    assert "_retired_topology_a_parse_args" not in main_calls
    assert "_retired_topology_a_execute" not in main_calls


def test_topology_b_functions_contain_no_incumbent_or_canonical_mutation_calls() -> None:
    require_topology_b_surface()
    forbidden_calls = {
        "migrate_shelf",
        "activate_filesystem",
        "stage_overlay",
        "activate_overlay",
        "stop_container",
        "start_container",
        "resolve_image_tag",
        "restore_active_authority",
        "complete_transaction",
    }
    forbidden_names = {
        "CANONICAL_PROJECT",
        "CANONICAL_PORTAL_TAG",
        "CANONICAL_TOOL_TAG",
    }
    for name in ("execute_topology_b", "recover_topology_b"):
        node = function_node(name)
        assert call_leaf_names(node).isdisjoint(forbidden_calls)
        loaded_names = {
            candidate.id
            for candidate in ast.walk(node)
            if isinstance(candidate, ast.Name)
        }
        assert loaded_names.isdisjoint(forbidden_names)


def test_execute_topology_b_prestarts_and_probes_sidecar_before_cf_commit(
    tmp_path: Path,
) -> None:
    require_topology_b_surface()
    config = topology_b_config(tmp_path)
    canonical_before = config.canonical_shelf_sentinel.read_bytes()
    actions = RecordingActions()

    controller.execute_topology_b(config, actions=actions)

    assert actions.events == SUCCESS_EVENTS
    assert actions.events.index("sidecar_healthy") < actions.events.index(
        "cloudflare_capture"
    )
    assert actions.events.index(
        "probe_public_chummer.run,www.chummer.run"
    ) < actions.events.index("cloudflare_commit")
    assert config.canonical_shelf_sentinel.read_bytes() == canonical_before


def test_execute_failure_after_cf_apply_rolls_back_before_exact_cleanup(
    tmp_path: Path,
) -> None:
    require_topology_b_surface()
    config = topology_b_config(tmp_path)
    canonical_before = config.canonical_shelf_sentinel.read_bytes()
    actions = RecordingActions(
        fail_at="probe_public_chummer.run,www.chummer.run"
    )

    with pytest.raises(controller.CutoverError):
        controller.execute_topology_b(config, actions=actions)

    assert actions.events[-3:] == [
        "cloudflare_rollback",
        "probe_incumbent_after-rollback_chummer.run,www.chummer.run",
        "cleanup_sidecar",
    ]
    assert config.canonical_shelf_sentinel.read_bytes() == canonical_before


def test_execute_retains_sidecar_when_cf_rollback_is_uncertain(
    tmp_path: Path,
) -> None:
    require_topology_b_surface()
    config = topology_b_config(tmp_path)
    canonical_before = config.canonical_shelf_sentinel.read_bytes()
    actions = RecordingActions(
        fail_at="probe_public_chummer.run,www.chummer.run"
    )
    original_record = actions.record

    def fail_rollback(event: str, result: Any = None) -> Any:
        if event == "cloudflare_rollback":
            actions.events.append(event)
            raise RuntimeError("rollback uncertain")
        return original_record(event, result)

    actions.record = fail_rollback  # type: ignore[method-assign]

    with pytest.raises(controller.RecoveryUncertain):
        controller.execute_topology_b(config, actions=actions)

    assert "cloudflare_rollback" in actions.events
    assert (
        "probe_incumbent_after-rollback_chummer.run,www.chummer.run"
        not in actions.events
    )
    assert "cleanup_sidecar" not in actions.events
    assert config.canonical_shelf_sentinel.read_bytes() == canonical_before


def test_execute_retains_sidecar_when_incumbent_reprobe_is_uncertain(
    tmp_path: Path,
) -> None:
    require_topology_b_surface()
    config = topology_b_config(tmp_path)
    canonical_before = config.canonical_shelf_sentinel.read_bytes()
    actions = RecordingActions()
    original_record = actions.record
    failed_events = {
        "probe_public_chummer.run,www.chummer.run",
        "probe_incumbent_after-rollback_chummer.run,www.chummer.run",
    }

    def fail_public_and_incumbent(
        event: str, result: Any = None
    ) -> Any:
        if event in failed_events:
            actions.events.append(event)
            raise RuntimeError(f"forced failure at {event}")
        return original_record(event, result)

    actions.record = fail_public_and_incumbent  # type: ignore[method-assign]

    with pytest.raises(controller.RecoveryUncertain):
        controller.execute_topology_b(config, actions=actions)

    assert actions.events[-2:] == [
        "cloudflare_rollback",
        "probe_incumbent_after-rollback_chummer.run,www.chummer.run",
    ]
    assert "cleanup_sidecar" not in actions.events
    assert config.canonical_shelf_sentinel.read_bytes() == canonical_before


def test_execute_does_not_rollback_a_committed_route_on_receipt_crash(
    tmp_path: Path,
) -> None:
    require_topology_b_surface()
    config = topology_b_config(tmp_path)
    canonical_before = config.canonical_shelf_sentinel.read_bytes()
    actions = RecordingActions(fail_at="write_active_receipt")

    with pytest.raises(controller.RecoveryUncertain):
        controller.execute_topology_b(config, actions=actions)

    assert "cloudflare_commit" in actions.events
    assert "cloudflare_rollback" not in actions.events
    assert "cleanup_sidecar" not in actions.events
    assert config.canonical_shelf_sentinel.read_bytes() == canonical_before


def test_recovery_rolls_back_cf_then_probes_incumbent_then_cleans_sidecar(
    tmp_path: Path,
) -> None:
    require_topology_b_surface()
    config = topology_b_config(tmp_path)
    canonical_before = config.canonical_shelf_sentinel.read_bytes()
    actions = RecordingActions(recovery_disposition="rollback")

    controller.recover_topology_b(config, actions=actions)

    assert actions.events == [
        "classify_recovery_rollback",
        "cloudflare_rollback",
        "probe_incumbent_after-rollback_chummer.run,www.chummer.run",
        "cleanup_sidecar",
    ]
    assert config.canonical_shelf_sentinel.read_bytes() == canonical_before


def test_recovery_reconciles_committed_route_without_cleanup(
    tmp_path: Path,
) -> None:
    require_topology_b_surface()
    config = topology_b_config(tmp_path)
    canonical_before = config.canonical_shelf_sentinel.read_bytes()
    actions = RecordingActions(recovery_disposition="committed")

    controller.recover_topology_b(config, actions=actions)

    assert actions.events == [
        "classify_recovery_committed",
        "reconcile_committed",
    ]
    assert config.canonical_shelf_sentinel.read_bytes() == canonical_before


def test_incumbent_baseline_and_rollback_cover_both_public_hosts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    require_topology_b_surface()
    config = topology_b_config(tmp_path)
    observed_requests: list[tuple[str, str]] = []
    drift_www = False

    def fake_http_bytes(**kwargs: Any) -> tuple[int, dict[str, str], bytes]:
        nonlocal drift_www
        host = kwargs["request_host"]
        path = kwargs["path"]
        assert kwargs["scheme"] == "https"
        assert kwargs["connect_host"] == host
        assert host in HOSTS
        observed_requests.append((host, path))
        body = f"{host}:{path}".encode("utf-8")
        if drift_www and host == "www.chummer.run":
            body += b":drift"
        return 200, {}, body

    monkeypatch.setattr(controller, "_http_bytes", fake_http_bytes)

    baseline = controller.probe_public_incumbent(config)

    assert tuple(baseline) == HOSTS
    assert all(
        tuple(baseline[host])
        == (
            "/downloads/RELEASE_CHANNEL.generated.json",
            "/downloads/releases.json",
        )
        for host in HOSTS
    )
    controller.probe_public_incumbent(config, expected=baseline)
    assert {host for host, _path in observed_requests} == set(HOSTS)

    drift_www = True
    with pytest.raises(controller.CutoverError):
        controller.probe_public_incumbent(config, expected=baseline)


class FakeDataProtectionRunner:
    def __init__(self, *, fail_first_request: bool = False) -> None:
        self.fail_first_request = fail_first_request
        self.calls: list[str] = []

    def run(self, command: list[str], **_kwargs: Any) -> bytes:
        operation = command[1]
        self.calls.append(operation)
        if operation == "req":
            if self.fail_first_request:
                self.fail_first_request = False
                raise controller.CutoverError("simulated crash before certificate")
            Path(command[command.index("-keyout") + 1]).write_bytes(
                b"fake-private-key"
            )
            Path(command[command.index("-out") + 1]).write_bytes(
                b"fake-certificate"
            )
            return b""
        if operation == "pkcs12":
            password_argument = command[command.index("-passout") + 1]
            assert password_argument.startswith("file:")
            password = Path(password_argument.removeprefix("file:")).read_bytes()
            Path(command[command.index("-out") + 1]).write_bytes(
                b"fake-pkcs12:" + password
            )
            return b""
        raise AssertionError(f"unexpected fake OpenSSL operation: {operation}")


def test_fresh_data_protection_generation_recovers_and_replays_exactly(
    tmp_path: Path,
) -> None:
    require_topology_b_surface()
    operation_root = tmp_path / "chummer-public-download-dp-retry"
    operation_root.mkdir(mode=0o700)
    config = SimpleNamespace(
        operation_root=operation_root,
        sidecar_certificate=operation_root / "sidecar-data-protection.pfx",
        sidecar_certificate_password=(
            operation_root / "sidecar-data-protection.password"
        ),
    )
    runner = FakeDataProtectionRunner(fail_first_request=True)

    with pytest.raises(controller.CutoverError):
        controller.generate_sidecar_data_protection(config, runner)

    assert config.sidecar_certificate_password.exists()
    assert not config.sidecar_certificate.exists()

    first = controller.generate_sidecar_data_protection(config, runner)
    certificate = config.sidecar_certificate.read_bytes()
    password = config.sidecar_certificate_password.read_bytes()
    replay = controller.generate_sidecar_data_protection(config, runner)

    assert replay == first
    assert config.sidecar_certificate.read_bytes() == certificate
    assert config.sidecar_certificate_password.read_bytes() == password
    assert first["certificateSha256"] == hashlib.sha256(certificate).hexdigest()
    assert first["passwordSha256"] == hashlib.sha256(password).hexdigest()


def write_candidate(root: Path) -> Path:
    files = root / "files"
    files.mkdir(parents=True)
    artifact = files / "Chummer6-portable.zip"
    artifact.write_bytes(b"portable release artifact\n")
    digest = generation.sha256_file(artifact)
    identity = {
        "version": "release-sidecar",
        "channel": "preview",
        "publishedAt": "2026-07-24T01:00:00Z",
    }
    canonical = {
        **identity,
        "releaseVersion": identity["version"],
        "artifacts": [
            {
                "artifactId": "portable",
                "fileName": artifact.name,
                "downloadUrl": f"/downloads/files/{artifact.name}",
                "sha256": digest,
                "sizeBytes": artifact.stat().st_size,
                "installAccessClass": "open_public",
            }
        ],
    }
    compatibility = {
        **identity,
        "downloads": [
            {
                "id": "portable",
                "fileName": artifact.name,
                "url": f"/downloads/files/{artifact.name}",
                "sha256": digest,
                "sizeBytes": artifact.stat().st_size,
                "installAccessClass": "open_public",
            }
        ],
    }
    (root / generation.CANONICAL_MANIFEST).write_text(
        json.dumps(canonical) + "\n", encoding="utf-8"
    )
    (root / generation.COMPATIBILITY_MANIFEST).write_text(
        json.dumps(compatibility) + "\n", encoding="utf-8"
    )
    return root


def test_sidecar_current_receipt_binds_pointer_generation_and_manifest_mirrors(
    tmp_path: Path,
) -> None:
    candidate = write_candidate(tmp_path / "candidate")
    output = tmp_path / "readonly-sidecar-shelf"

    receipt = generation.prepare_sidecar_active_layout(
        candidate,
        output,
        generation_id="generation-sidecar",
        activation_receipt_id="activation-sidecar",
        activated_at="2026-07-24T01:00:00Z",
    )

    pointer = json.loads((output / generation.CURRENT_POINTER).read_bytes())
    generation_root = (
        output / generation.GENERATIONS_DIRECTORY / pointer["generationId"]
    )
    assert (output / generation.LAYOUT_MARKER).read_bytes() == b"v1\n"
    assert json.loads((output / generation.WRITER_POLICY).read_bytes()) == {
        "schemaVersion": generation.SERVER_WRITER_POLICY_SCHEMA,
        "mode": generation.SIDECAR_WRITER_POLICY_MODE,
    }
    assert not (output / ".release-shelf-activation-journal").exists()
    assert not (output / generation.PROMOTION_LOCK).exists()
    assert receipt["pointerSha256"] == generation.sha256_file(
        output / generation.CURRENT_POINTER
    )
    assert receipt["activationCandidateSha256"] == generation.sha256_file(
        generation_root / generation.ACTIVATION_CANDIDATE
    )
    assert receipt["canonicalMirrorSha256"] == generation.sha256_file(
        output / generation.CANONICAL_MANIFEST
    )
    assert receipt["compatibilityMirrorSha256"] == generation.sha256_file(
        output / generation.COMPATIBILITY_MANIFEST
    )
