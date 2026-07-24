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
ATTESTOR_PATH = ROOT / "scripts" / "attest_initial_release_shelf_cutover.py"


def load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


controller = load_module(CONTROLLER_PATH, "topology_b_controller_contract")
generation = load_module(GENERATION_PATH, "topology_b_generation_contract")
attestor = load_module(ATTESTOR_PATH, "topology_b_attestor_contract")

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


def class_method_node(class_name: str, method_name: str) -> ast.FunctionDef:
    tree = ast.parse(CONTROLLER_PATH.read_text(encoding="utf-8"))
    classes = [
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == class_name
    ]
    assert len(classes) == 1, f"expected one controller class named {class_name}"
    matches = [
        node
        for node in classes[0].body
        if isinstance(node, ast.FunctionDef) and node.name == method_name
    ]
    assert len(matches) == 1, (
        f"expected one {class_name} method named {method_name}"
    )
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


def call_leaf_names_in_source_order(node: ast.AST) -> list[str]:
    calls = [
        candidate
        for candidate in ast.walk(node)
        if isinstance(candidate, ast.Call)
    ]
    names: list[str] = []
    for candidate in sorted(
        calls,
        key=lambda call: (call.lineno, call.col_offset),
    ):
        function = candidate.func
        if isinstance(function, ast.Name):
            names.append(function.id)
        elif isinstance(function, ast.Attribute):
            names.append(function.attr)
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
        cloudflare_lock=operation_root / "cloudflare-live.lock",
        cloudflare_committed_evidence=(
            operation_root / "cloudflare-committed.json"
        ),
        cloudflare_rollback_evidence=(
            operation_root / "cloudflare-rolled-back.json"
        ),
        external_probe_receipt=(
            operation_root / "cloudflare-external-probe.json"
        ),
        base_url="https://chummer.run",
        ready_timeout_seconds=30,
    )


def test_active_cli_parses_exact_release_authorities_from_wrapper_argv(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    require_topology_b_surface()

    def directory(name: str) -> Path:
        path = tmp_path / name
        path.mkdir(parents=True)
        return path

    def document(path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}\n", encoding="utf-8")
        return path

    source_root = directory("source")
    shelf_root = directory("canonical-shelf")
    migration_candidate = directory("migration-candidate")
    sealed_root = directory("sealed")
    release_candidate = directory("sealed/bundle")
    projection_root = directory("projection/public-projection-" + "1" * 64)
    fleet_source = directory("fleet")
    operation_parent = directory("operations")
    operation_root = operation_parent / "chummer-public-download-op-a1b2c3d4"
    active_root = directory("active-authority")
    docker_root = directory("docker")
    receipt_root = directory("receipts")
    build_context = directory("build-context")
    fleet_contracts = directory("fleet-contracts")
    design_product = directory("design-product")

    migration_authority = document(tmp_path / "migration-authority.json")
    candidate_authority = document(
        projection_root
        / "RELEASE_UPLOAD_CANDIDATE_AUTHORITY.generated.json"
    )
    direct_import = document(
        sealed_root
        / "UNSIGNED_WINDOWS_PREVIEW_DIRECT_IMPORT.generated.json"
    )
    restoration_spec = document(tmp_path / "restoration-spec.json")
    release_receipt = document(
        projection_root / "RELEASE_CHANNEL.generated.json"
    )
    runtime_proof = document(
        projection_root / "HUB_LOCAL_RELEASE_PROOF.generated.json"
    )
    final_gold = document(tmp_path / "final-gold.json")
    cloudflare_credentials = document(tmp_path / "cloudflare.env")
    active_authority = active_root / "topology-b-active.json"

    semantic_sha256 = "1" * 64
    tree_sha256 = "2" * 64
    candidate_sha256 = "3" * 64
    direct_import_sha256 = "4" * 64
    monkeypatch.setattr(
        controller,
        "CANONICAL_RELEASE_SHELF_ROOT",
        shelf_root,
    )

    config = controller.parse_args(
        [
            "--operation",
            controller.CUTOVER_OPERATION,
            "--source-root",
            str(source_root),
            "--source-head",
            "a" * 40,
            "--shared-mutation-lock-token",
            "b" * 64,
            "--shelf-root",
            str(shelf_root),
            "--migration-candidate-root",
            str(migration_candidate),
            "--migration-authority",
            str(migration_authority),
            "--migration-authority-sha256",
            "5" * 64,
            "--release-candidate-root",
            str(release_candidate),
            "--candidate-import-authority",
            str(candidate_authority),
            "--candidate-import-authority-sha256",
            candidate_sha256,
            "--direct-import-receipt",
            str(direct_import),
            "--direct-import-receipt-sha256",
            direct_import_sha256,
            "--manifest-closure-restoration-spec",
            str(restoration_spec),
            "--manifest-closure-restoration-spec-sha256",
            "6" * 64,
            "--release-channel-receipt",
            str(release_receipt),
            "--release-channel-receipt-sha256",
            "7" * 64,
            "--projection-snapshot-root",
            str(projection_root),
            "--projection-snapshot-id",
            projection_root.name,
            "--projection-snapshot-sha256",
            semantic_sha256,
            "--projection-snapshot-tree-sha256",
            tree_sha256,
            "--projection-manifest-sha256",
            "8" * 64,
            "--runtime-proof-source",
            str(runtime_proof),
            "--runtime-proof-sha256",
            "9" * 64,
            "--final-gold-source",
            str(final_gold),
            "--final-gold-sha256",
            "a" * 64,
            "--fleet-source",
            str(fleet_source),
            "--fleet-sha256",
            "b" * 64,
            "--operation-root",
            str(operation_root),
            "--active-runtime-authority",
            str(active_authority),
            "--docker-config-root",
            str(docker_root),
            "--cloudflare-credentials-file",
            str(cloudflare_credentials),
            "--cloudflare-account-id",
            "account-id",
            "--cloudflare-tunnel-id",
            "tunnel-id",
            "--receipt-root",
            str(receipt_root),
            "--base-url",
            "https://chummer.run",
            "--build-context",
            str(build_context),
            "--fleet-media-contracts",
            str(fleet_contracts),
            "--design-product-root",
            str(design_product),
            "--delivery-phase",
            "windows-preview",
        ]
    )

    assert config.release_candidate_root == release_candidate
    assert config.candidate_import_authority == candidate_authority
    assert config.candidate_import_authority_sha256 == candidate_sha256
    assert config.direct_import_receipt == direct_import
    assert config.direct_import_receipt_sha256 == direct_import_sha256
    assert config.projection_snapshot_sha256 == semantic_sha256
    assert config.projection_source_tree_sha256 == tree_sha256
    assert semantic_sha256 != tree_sha256

    wrapper = (
        ROOT / "scripts" / "deploy_public_edge_portal.sh"
    ).read_text(encoding="utf-8")
    for flag in (
        "--release-candidate-root",
        "--candidate-import-authority",
        "--candidate-import-authority-sha256",
        "--direct-import-receipt",
        "--direct-import-receipt-sha256",
        "--projection-snapshot-sha256",
        "--projection-snapshot-tree-sha256",
    ):
        assert flag in wrapper


class RecordingActions:
    """Mocked action boundary approved for the topology-B controller."""

    def __init__(
        self,
        *,
        fail_at: str | None = None,
        recovery_disposition: str = "rollback",
        baseline_captured: bool = False,
    ) -> None:
        self.events: list[str] = []
        self.fail_at = fail_at
        self.recovery_disposition = recovery_disposition
        self.incumbent_baseline_captured = baseline_captured

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
        event = f"probe_incumbent_{phase}_{','.join(hosts)}"
        if phase == "after-rollback" and not self.incumbent_baseline_captured:
            self.events.append(event)
            raise RuntimeError("incumbent baseline is unavailable")
        result = self.record(event)
        if phase == "before-cloudflare":
            self.incumbent_baseline_captured = True
        return result

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


def test_planned_journal_is_not_published_before_operation_root_exists(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    require_topology_b_surface()
    receipt_root = tmp_path / "receipts"
    operation_parent = tmp_path / "operations"
    shelf = tmp_path / "canonical-shelf"
    docker_config_root = tmp_path / "docker"
    for directory in (
        receipt_root,
        operation_parent,
        shelf,
        docker_config_root,
        docker_config_root / "config",
    ):
        directory.mkdir(mode=0o700)
        directory.chmod(0o700)
    operation_root = operation_parent / "chummer-public-download-crash-test"
    journal = receipt_root / f"{operation_root.name}.operation.json"
    volume_names = {
        logical: (
            f"{operation_root.name}-"
            f"{logical.removeprefix('public-download-')}"
        )
        for logical in controller.SIDECAR_LOGICAL_VOLUMES
    }
    config = SimpleNamespace(
        operation=controller.CUTOVER_OPERATION,
        source_root=ROOT,
        source_head="a" * 40,
        operation_root=operation_root,
        operation_journal=journal,
        project_name=operation_root.name,
        shelf_root=shelf,
        volume_names=volume_names,
        docker_config_root=docker_config_root,
    )
    monkeypatch.setattr(controller, "_validate_sidecar_config", lambda _config: None)
    monkeypatch.setattr(
        controller,
        "load_module",
        lambda *_args, **_kwargs: SimpleNamespace(),
    )
    original_mkdir = Path.mkdir

    def crash_before_operation_root(
        path: Path, *args: Any, **kwargs: Any
    ) -> None:
        if path == operation_root:
            raise OSError("simulated crash before operation-root creation")
        original_mkdir(path, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", crash_before_operation_root)

    with pytest.raises(OSError):
        controller.TopologyBActions(config)

    assert not journal.exists()
    assert not operation_root.exists()


class FakeVolumeRunner:
    def __init__(
        self,
        *,
        existing_labels: dict[str, dict[str, str]] | None = None,
        mount_root: Path | None = None,
    ) -> None:
        self.labels = dict(existing_labels or {})
        self.inspected: list[str] = []
        self.mount_root = mount_root
        if self.mount_root is not None:
            self.mount_root.mkdir(parents=True, exist_ok=True)
            for name in self.labels:
                (self.mount_root / name).mkdir()

    def docker(self, arguments: list[str], **_kwargs: Any) -> bytes:
        if arguments[:2] == ["volume", "ls"]:
            filter_value = arguments[-1]
            assert filter_value.startswith("name=^")
            assert filter_value.endswith("$")
            name = filter_value.removeprefix("name=^").removesuffix("$")
            return f"{name}\n".encode("utf-8") if name in self.labels else b""
        if arguments[:2] == ["volume", "create"]:
            name = arguments[-1]
            if name not in self.labels:
                labels: dict[str, str] = {}
                for index, value in enumerate(arguments[:-1]):
                    if value == "--label":
                        key, label_value = arguments[index + 1].split("=", 1)
                        labels[key] = label_value
                self.labels[name] = labels
                if self.mount_root is not None:
                    (self.mount_root / name).mkdir()
            return f"{name}\n".encode("utf-8")
        if arguments[:2] == ["volume", "inspect"]:
            name = arguments[2]
            self.inspected.append(name)
            return json.dumps(
                [
                    {
                        "Name": name,
                        "Labels": self.labels[name],
                        "Mountpoint": (
                            str(self.mount_root / name)
                            if self.mount_root is not None
                            else ""
                        ),
                    }
                ]
            ).encode("utf-8")
        raise AssertionError(arguments)


def concrete_actions_with_volume_runner(
    runner: FakeVolumeRunner,
) -> Any:
    actions = object.__new__(controller.TopologyBActions)
    actions.runner = runner
    actions._record = lambda *_args, **_kwargs: None
    return actions


def volume_test_config() -> SimpleNamespace:
    project_name = "chummer-public-download-volume-test"
    return SimpleNamespace(
        project_name=project_name,
        volume_names={
            logical: (
                f"{project_name}-"
                f"{logical.removeprefix('public-download-')}"
            )
            for logical in controller.SIDECAR_LOGICAL_VOLUMES
        },
    )


def test_partial_volume_replay_rejects_wrong_adoption_labels() -> None:
    require_topology_b_surface()
    config = volume_test_config()
    logical = controller.SIDECAR_LOGICAL_VOLUMES[0]
    name = config.volume_names[logical]
    runner = FakeVolumeRunner(
        existing_labels={
            name: {
                "run.chummer.public-download-operation": config.project_name,
                "run.chummer.public-download-logical-volume": "wrong-logical",
            }
        }
    )
    actions = concrete_actions_with_volume_runner(runner)

    with pytest.raises((controller.CutoverError, controller.RecoveryUncertain)):
        actions.create_sidecar_resources(config, {})


def test_partial_volume_replay_adopts_only_exact_labeled_volumes(
    tmp_path: Path,
) -> None:
    require_topology_b_surface()
    config = volume_test_config()
    existing_labels: dict[str, dict[str, str]] = {}
    for logical in controller.SIDECAR_LOGICAL_VOLUMES[:3]:
        existing_labels[config.volume_names[logical]] = {
            "run.chummer.public-download-operation": config.project_name,
            "run.chummer.public-download-logical-volume": logical,
        }
    runner = FakeVolumeRunner(
        existing_labels=existing_labels,
        mount_root=tmp_path / "volume-mounts",
    )
    actions = concrete_actions_with_volume_runner(runner)

    receipt = actions.create_sidecar_resources(config, {})

    expected = [
        config.volume_names[logical]
        for logical in controller.SIDECAR_LOGICAL_VOLUMES
    ]
    assert receipt["reusedEmptyVolumes"] == expected[:3]
    assert receipt["volumes"] == expected[3:]
    assert runner.inspected == expected


def test_sidecar_start_removes_only_exact_project_orphans() -> None:
    require_topology_b_surface()
    start = class_method_node("TopologyBActions", "start_sidecar_runtime")
    string_literals = {
        candidate.value
        for candidate in ast.walk(start)
        if isinstance(candidate, ast.Constant)
        and isinstance(candidate.value, str)
    }
    assert "--remove-orphans" in string_literals


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


@pytest.mark.parametrize(
    "failure_event",
    (
        "prepare_shelf",
        "generate_dp",
        "materialize_compose",
        "create_resources",
        "start_sidecar",
        "sidecar_healthy",
        "probe_local_chummer.run,www.chummer.run",
        "probe_incumbent_before-cloudflare_chummer.run,www.chummer.run",
    ),
)
def test_pre_cloudflare_failure_cleans_without_rollback_reprobe_dead_end(
    tmp_path: Path,
    failure_event: str,
) -> None:
    require_topology_b_surface()
    config = topology_b_config(tmp_path)
    canonical_before = config.canonical_shelf_sentinel.read_bytes()
    actions = RecordingActions(fail_at=failure_event)

    with pytest.raises(controller.CutoverError):
        controller.execute_topology_b(config, actions=actions)

    assert actions.events[-1] == "cleanup_sidecar"
    assert "cloudflare_rollback" not in actions.events
    assert (
        "probe_incumbent_after-rollback_chummer.run,www.chummer.run"
        not in actions.events
    )
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
    actions = RecordingActions(
        recovery_disposition="rollback",
        baseline_captured=True,
    )

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


def test_recovery_classification_rejects_unvalidated_committed_evidence(
    tmp_path: Path,
) -> None:
    require_topology_b_surface()
    config = topology_b_config(tmp_path)
    config.cloudflare_committed_evidence.write_text(
        '{"phase":"committed"}\n',
        encoding="utf-8",
    )
    config.cloudflare_committed_evidence.chmod(0o600)
    actions = object.__new__(controller.TopologyBActions)
    actions.cloudflare = load_module(
        ROOT / "scripts" / "cloudflare_public_download_transaction.py",
        "topology_b_malformed_committed_evidence_contract",
    )

    with pytest.raises(controller.RecoveryUncertain):
        actions.classify_recovery(config)


def test_recovery_classification_does_not_rollback_a_lost_committed_archive(
    tmp_path: Path,
) -> None:
    require_topology_b_surface()
    config = topology_b_config(tmp_path)
    actions = object.__new__(controller.TopologyBActions)
    actions._state = {
        "phase": "cloudflare-committed",
        "receipts": {},
    }
    actions.cloudflare = SimpleNamespace(
        journal_path_present=lambda _path: False
    )

    with pytest.raises(controller.RecoveryUncertain):
        actions.classify_recovery(config)


def test_committed_reconciliation_reverifies_sidecar_before_active_authority() -> None:
    require_topology_b_surface()
    reconcile = class_method_node("TopologyBActions", "reconcile_committed")
    calls = call_leaf_names_in_source_order(reconcile)
    for required in (
        "container_runtime",
        "wait_healthy",
        "probe_sidecar_hosts",
        "_probe_exact_manifest",
        "write_active_receipt",
    ):
        assert required in calls
    assert calls.index("container_runtime") < calls.index(
        "write_active_receipt"
    )
    assert calls.index("wait_healthy") < calls.index("write_active_receipt")
    assert calls.index("probe_sidecar_hosts") < calls.index(
        "write_active_receipt"
    )
    assert calls.index("_probe_exact_manifest") < calls.index(
        "write_active_receipt"
    )


def test_commit_archive_crash_reconstructs_active_authority_without_state_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    require_topology_b_surface()
    config = topology_b_config(tmp_path)
    shelf = {"generationId": "g-test", "generationRoot": str(tmp_path)}
    runtime = {"candidateImageId": "sha256:" + "1" * 64}
    sidecar = {"containerId": "2" * 64}
    terminal = {
        "phase": "committed",
        "targetConfigSha256": "3" * 64,
        "targetVersion": 7,
    }
    (tmp_path / "releases.json").write_text("{}\n", encoding="utf-8")
    config.cloudflare_committed_evidence.write_text(
        '{"phase":"committed"}\n',
        encoding="utf-8",
    )
    config.cloudflare_committed_evidence.chmod(0o600)

    class FakeCloudflare:
        @staticmethod
        def commit_transaction(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
            return dict(terminal)

    actions = object.__new__(controller.TopologyBActions)
    actions.cloudflare = FakeCloudflare()
    actions._state = {
        "receipts": {
            "shelf": shelf,
            "runtime": runtime,
            "sidecar": sidecar,
        }
    }
    actions.config = config
    actions.runner = SimpleNamespace()
    actions._cloudflare_api = lambda: object()
    monkeypatch.setattr(
        controller,
        "container_runtime",
        lambda *_args, **_kwargs: {
            "wasRunning": True,
            "imageId": runtime["candidateImageId"],
        },
    )
    monkeypatch.setattr(
        controller,
        "wait_healthy",
        lambda *_args, **_kwargs: {"status": "healthy"},
    )
    monkeypatch.setattr(
        controller,
        "probe_sidecar_hosts",
        lambda *_args, **_kwargs: {"status": "pass"},
    )
    monkeypatch.setattr(
        controller,
        "_probe_exact_manifest",
        lambda *_args, **_kwargs: {"status": "pass"},
    )
    monkeypatch.setattr(
        controller,
        "probe_download_artifact_hosts",
        lambda *_args, **_kwargs: {"status": "pass"},
    )
    captured_commit: list[dict[str, Any]] = []

    def write_active(
        _config: Any,
        _shelf: Any,
        _runtime: Any,
        _sidecar: Any,
        commit: Mapping[str, Any],
        *_args: Any,
    ) -> dict[str, Any]:
        captured_commit.append(dict(commit))
        return {"status": "active"}

    actions.write_active_receipt = write_active

    result = actions.reconcile_committed(config)

    assert result["active"] == {"status": "active"}
    assert len(captured_commit) == 1
    assert {
        key: captured_commit[0][key]
        for key in ("phase", "targetConfigSha256", "targetVersion")
    } == terminal
    assert captured_commit[0]["evidencePath"] == str(
        config.cloudflare_committed_evidence
    )
    assert captured_commit[0]["evidenceSha256"] == hashlib.sha256(
        config.cloudflare_committed_evidence.read_bytes()
    ).hexdigest()


def test_committed_reconciliation_reprobes_with_existing_active_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    require_topology_b_surface()
    config = topology_b_config(tmp_path)
    shelf = {"generationId": "g-test", "generationRoot": str(tmp_path)}
    runtime = {"candidateImageId": "sha256:" + "1" * 64}
    sidecar = {"containerId": "2" * 64}
    commit = {
        "phase": "committed",
        "targetConfigSha256": "3" * 64,
        "targetVersion": 7,
    }
    active = {"status": "active"}
    (tmp_path / "releases.json").write_text("{}\n", encoding="utf-8")

    class FakeCloudflare:
        @staticmethod
        def commit_transaction(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
            return dict(commit)

    actions = object.__new__(controller.TopologyBActions)
    actions.cloudflare = FakeCloudflare()
    actions._state = {
        "receipts": {
            "shelf": shelf,
            "runtime": runtime,
            "sidecar": sidecar,
            "cloudflareCommit": commit,
            "activeAuthority": active,
        }
    }
    actions.config = config
    actions.runner = SimpleNamespace()
    actions._cloudflare_api = lambda: object()

    events: list[str] = []

    def current_runtime(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        events.append("container")
        return {
            "wasRunning": True,
            "imageId": runtime["candidateImageId"],
        }

    monkeypatch.setattr(controller, "container_runtime", current_runtime)
    monkeypatch.setattr(
        controller,
        "wait_healthy",
        lambda *_args, **_kwargs: events.append("healthy"),
    )
    monkeypatch.setattr(
        controller,
        "probe_sidecar_hosts",
        lambda *_args, **_kwargs: events.append("local"),
    )

    def probe_artifacts(*_args: Any, **kwargs: Any) -> None:
        assert kwargs["scope"] == "public"
        events.append("public-artifacts")

    monkeypatch.setattr(
        controller,
        "probe_download_artifact_hosts",
        probe_artifacts,
    )
    monkeypatch.setattr(
        controller,
        "_probe_exact_manifest",
        lambda *_args, **_kwargs: events.append("public-manifest"),
    )
    actions.write_active_receipt = lambda *_args, **_kwargs: pytest.fail(
        "existing active authority must not be rewritten"
    )

    result = actions.reconcile_committed(config)

    assert result["active"] is active
    assert events == [
        "container",
        "healthy",
        "local",
        "public-artifacts",
        "public-manifest",
        "public-manifest",
    ]


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


class FakeProbeResponse:
    def __init__(
        self,
        body: bytes,
        *,
        status: int = 200,
        generation: str = "generation-a",
        headers: list[tuple[str, str]] | None = None,
    ) -> None:
        self.status = status
        self._body = body
        self._offset = 0
        self._headers = [
            ("Content-Length", str(len(body))),
            ("X-Chummer-Release-Generation", generation),
            *(headers or []),
        ]

    def getheaders(self) -> list[tuple[str, str]]:
        return list(self._headers)

    def read(self, amount: int) -> bytes:
        chunk = self._body[self._offset : self._offset + amount]
        self._offset += len(chunk)
        return chunk


class FakeProbeConnection:
    def __init__(self, response: FakeProbeResponse) -> None:
        self.response = response
        self.requests: list[tuple[str, str, dict[str, str]]] = []
        self.closed = False

    def request(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str],
    ) -> None:
        self.requests.append((method, path, dict(headers)))

    def getresponse(self) -> FakeProbeResponse:
        return self.response

    def close(self) -> None:
        self.closed = True


def test_exact_download_probe_streams_hashes_and_sends_no_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    require_topology_b_surface()
    body = b"fresh-windows-payload"
    response = FakeProbeResponse(body)
    connection = FakeProbeConnection(response)
    monkeypatch.setattr(
        controller,
        "_open_probe_connection",
        lambda **_kwargs: connection,
    )

    receipt = controller._stream_exact_download(
        scheme="https",
        connect_host="www.chummer.run",
        connect_port=443,
        request_host="www.chummer.run",
        path="/downloads/files/chummer-avalonia-win-x64-payload.zip",
        expected_sha256=hashlib.sha256(body).hexdigest(),
        expected_size_bytes=len(body),
        generation_id="generation-a",
    )

    assert receipt["sha256"] == hashlib.sha256(body).hexdigest()
    assert receipt["sizeBytes"] == len(body)
    assert receipt["anonymous"] is True
    assert receipt["redirectsFollowed"] == 0
    method, path, headers = connection.requests[0]
    assert (method, path) == (
        "GET",
        "/downloads/files/chummer-avalonia-win-x64-payload.zip",
    )
    assert headers["Host"] == "www.chummer.run"
    assert headers["Accept-Encoding"] == "identity"
    assert {
        "authorization",
        "cookie",
        "proxy-authorization",
    }.isdisjoint(key.lower() for key in headers)
    assert connection.closed is True


@pytest.mark.parametrize(
    "failure",
    ("corrupt", "redirect", "cookie", "auth-challenge"),
)
def test_exact_download_probe_rejects_corruption_redirect_cookie_and_auth(
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    require_topology_b_surface()
    expected = b"fresh-installer"
    body = expected
    status = 200
    headers: list[tuple[str, str]] = []
    if failure == "corrupt":
        body = b"Fresh-installer"
    elif failure == "redirect":
        status = 302
        headers.append(("Location", "/login"))
    elif failure == "cookie":
        headers.append(("Set-Cookie", "session=secret"))
    else:
        headers.append(("WWW-Authenticate", 'Bearer realm="private"'))
    response = FakeProbeResponse(
        body,
        status=status,
        headers=headers,
    )
    connection = FakeProbeConnection(response)
    monkeypatch.setattr(
        controller,
        "_open_probe_connection",
        lambda **_kwargs: connection,
    )

    with pytest.raises(controller.CutoverError):
        controller._stream_exact_download(
            scheme="http",
            connect_host=controller.SIDECAR_ADDRESS,
            connect_port=controller.SIDECAR_PORT,
            request_host="chummer.run",
            path="/downloads/files/chummer-avalonia-win-x64-installer.exe",
            expected_sha256=hashlib.sha256(expected).hexdigest(),
            expected_size_bytes=len(expected),
            generation_id="generation-a",
        )


def test_account_required_denial_probe_does_not_follow_login_redirect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    require_topology_b_surface()
    response = FakeProbeResponse(
        b"",
        status=302,
        headers=[("Location", "/login?next=%2Fdownloads%2Finstall%2Fmac")],
    )
    connection = FakeProbeConnection(response)
    monkeypatch.setattr(
        controller,
        "_open_probe_connection",
        lambda **_kwargs: connection,
    )

    receipt = controller._probe_denied_download(
        scheme="https",
        connect_host="chummer.run",
        connect_port=443,
        request_host="chummer.run",
        path="/downloads/files/chummer-avalonia-osx-x64-installer.dmg",
        generation_id="generation-a",
    )

    assert receipt["httpStatus"] == 302
    assert receipt["artifactBytesServed"] is False
    assert receipt["redirectsFollowed"] == 0
    assert len(connection.requests) == 1
    assert {
        "authorization",
        "cookie",
        "proxy-authorization",
    }.isdisjoint(
        key.lower() for key in connection.requests[0][2]
    )


@pytest.mark.parametrize(
    "status,headers",
    [
        (200, []),
        (302, [("Location", "/login"), ("Set-Cookie", "session=secret")]),
        (401, [("WWW-Authenticate", 'Bearer realm="private"')]),
    ],
)
def test_account_required_denial_probe_rejects_exposure_or_auth_state(
    monkeypatch: pytest.MonkeyPatch,
    status: int,
    headers: list[tuple[str, str]],
) -> None:
    require_topology_b_surface()
    response = FakeProbeResponse(
        b"mac-installer-bytes" if status == 200 else b"",
        status=status,
        headers=headers,
    )
    connection = FakeProbeConnection(response)
    monkeypatch.setattr(
        controller,
        "_open_probe_connection",
        lambda **_kwargs: connection,
    )

    with pytest.raises(controller.CutoverError):
        controller._probe_denied_download(
            scheme="https",
            connect_host="chummer.run",
            connect_port=443,
            request_host="chummer.run",
            path="/downloads/files/chummer-avalonia-osx-x64-installer.dmg",
            generation_id="generation-a",
        )


@pytest.mark.parametrize(
    "scope,scheme,connect_hosts",
    [
        (
            "local",
            "http",
            {controller.SIDECAR_ADDRESS},
        ),
        (
            "public",
            "https",
            set(HOSTS),
        ),
    ],
)
def test_artifact_host_gate_covers_three_fresh_bytes_and_retained_mac_denials(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    scope: str,
    scheme: str,
    connect_hosts: set[str],
) -> None:
    require_topology_b_surface()
    generation_id = "generation-a"
    generation_root = tmp_path / "generation"
    generation_root.mkdir()
    mac_file = "chummer-avalonia-osx-x64-installer.dmg"
    (generation_root / "RELEASE_CHANNEL.generated.json").write_text(
        json.dumps(
            {
                "artifacts": [
                    {
                        "artifactId": "avalonia-osx-x64-installer",
                        "platform": "macos",
                        "rid": "osx-x64",
                        "fileName": mac_file,
                        "downloadUrl": f"/downloads/files/{mac_file}",
                        "sha256": "d" * 64,
                        "sizeBytes": 101,
                        "installAccessClass": "account_required",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    fresh_paths = (
        "files/chummer-avalonia-win-x64-installer.exe",
        "files/chummer-avalonia-win-x64-payload.zip",
        "files/chummer-avalonia-win-x64-payload.zip.json",
    )
    shelf = {
        "generationId": generation_id,
        "generationRoot": str(generation_root),
        "releaseCandidateAuthority": {
            "freshDelta": [
                {
                    "path": path,
                    "sha256": character * 64,
                    "sizeBytes": index + 10,
                }
                for index, (path, character) in enumerate(
                    zip(fresh_paths, ("a", "b", "c"), strict=True)
                )
            ]
        },
    }
    config = SimpleNamespace(base_url="https://chummer.run")
    streamed: list[dict[str, Any]] = []
    denied: list[dict[str, Any]] = []

    def fake_stream(**kwargs: Any) -> dict[str, Any]:
        streamed.append(kwargs)
        return {
            "endpoint": (
                f"{kwargs['scheme']}://{kwargs['request_host']}"
                f"{kwargs['path']}"
            ),
            "httpStatus": 200,
            "sha256": kwargs["expected_sha256"],
            "sizeBytes": kwargs["expected_size_bytes"],
            "anonymous": True,
            "redirectsFollowed": 0,
        }

    def fake_denial(**kwargs: Any) -> dict[str, Any]:
        denied.append(kwargs)
        return {
            "endpoint": (
                f"{kwargs['scheme']}://{kwargs['request_host']}"
                f"{kwargs['path']}"
            ),
            "httpStatus": 302,
            "anonymous": True,
            "artifactBytesServed": False,
            "redirectsFollowed": 0,
        }

    monkeypatch.setattr(controller, "_stream_exact_download", fake_stream)
    monkeypatch.setattr(controller, "_probe_denied_download", fake_denial)

    receipt = controller.probe_download_artifact_hosts(
        config,
        shelf=shelf,
        scope=scope,
    )

    assert receipt["status"] == "pass"
    assert receipt["hosts"] == list(HOSTS)
    assert len(receipt["freshArtifacts"]) == 6
    assert len(receipt["accountRequiredDenials"]) == 4
    assert {call["request_host"] for call in streamed} == set(HOSTS)
    assert {call["connect_host"] for call in streamed} == connect_hosts
    assert {call["scheme"] for call in streamed} == {scheme}
    assert {call["path"] for call in streamed} == {
        f"/downloads/{path}" for path in fresh_paths
    }
    assert {call["path"] for call in denied} == {
        f"/downloads/files/{mac_file}",
        f"/downloads/g/{generation_id}/files/{mac_file}",
    }
    assert all(
        observation["installAccessClass"] == "account_required"
        and observation["artifactBytesServed"] is False
        for observation in receipt["accountRequiredDenials"]
    )


def test_local_and_public_controller_phases_both_require_artifact_host_gate() -> None:
    require_topology_b_surface()
    assert "probe_download_artifact_hosts" in call_leaf_names(
        function_node("probe_sidecar_hosts")
    )
    assert "probe_download_artifact_hosts" in call_leaf_names(
        class_method_node("TopologyBActions", "_verify_public_downloads")
    )
    assert "probe_download_artifact_hosts" in call_leaf_names(
        class_method_node("TopologyBActions", "reconcile_committed")
    )


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
            if "-noout" in command:
                certificate = Path(command[command.index("-in") + 1])
                password_argument = command[command.index("-passin") + 1]
                password = Path(
                    password_argument.removeprefix("file:")
                ).read_bytes()
                if certificate.read_bytes() != b"fake-pkcs12:" + password:
                    raise controller.CutoverError("invalid fake PKCS#12")
                return b""
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


def test_data_protection_replay_rejects_partial_final_pkcs12(
    tmp_path: Path,
) -> None:
    operation_root = tmp_path / "chummer-public-download-dp-partial"
    operation_root.mkdir(mode=0o700)
    certificate = operation_root / "sidecar-data-protection.pfx"
    password = operation_root / "sidecar-data-protection.password"
    certificate.write_bytes(b"partial")
    password.write_bytes(b"known-password\n")
    certificate.chmod(0o600)
    password.chmod(0o600)
    config = SimpleNamespace(
        operation_root=operation_root,
        sidecar_certificate=certificate,
        sidecar_certificate_password=password,
    )

    with pytest.raises(controller.RecoveryUncertain):
        controller.generate_sidecar_data_protection(
            config,
            FakeDataProtectionRunner(),
        )


def write_legacy_migration_shelf(root: Path) -> None:
    artifact = b"incumbent portable release\n"
    artifact_name = "Chummer6-portable.zip"
    files = root / "files"
    files.mkdir(parents=True)
    (files / artifact_name).write_bytes(artifact)
    digest = hashlib.sha256(artifact).hexdigest()
    identity = {
        "version": "authority-test",
        "channel": "preview",
        "publishedAt": "2026-07-24T01:00:00Z",
    }
    download = {
        "fileName": artifact_name,
        "sha256": digest,
        "sizeBytes": len(artifact),
    }
    (root / "releases.json").write_text(
        json.dumps({**identity, "downloads": [download]}) + "\n",
        encoding="utf-8",
    )
    (root / "RELEASE_CHANNEL.generated.json").write_text(
        json.dumps(
            {
                "version": identity["version"],
                "channelId": identity["channel"],
                "publishedAt": identity["publishedAt"],
                "artifacts": [download],
            }
        )
        + "\n",
        encoding="utf-8",
    )


def test_sidecar_shelf_rejects_authority_for_a_different_exact_candidate(
    tmp_path: Path,
) -> None:
    require_topology_b_surface()
    shelf = tmp_path / "canonical-shelf"
    shelf.mkdir()
    write_legacy_migration_shelf(shelf)
    private_root = tmp_path / "private"
    private_root.mkdir(mode=0o700)
    private_root.chmod(0o700)
    restoration_spec = private_root / "restorations.json"
    restoration_spec.write_text("[]\n", encoding="utf-8")
    restoration_sha = hashlib.sha256(
        restoration_spec.read_bytes()
    ).hexdigest()
    source_head = "a" * 40

    candidates: list[tuple[Path, Path]] = []
    for suffix in ("authority-source", "controller-input"):
        candidate = private_root / suffix
        materialization = private_root / f"{suffix}-materialization.json"
        attestor.materialize_public_download_migration_candidate(
            shelf,
            candidate,
            source_head,
            restoration_spec,
            restoration_sha,
            materialization,
        )
        candidates.append((candidate, materialization))

    authority = private_root / "migration-authority.json"
    authority_candidate, authority_materialization = candidates[0]
    attestor.materialize_public_download_migration_authority(
        shelf,
        authority_candidate,
        source_head,
        restoration_spec,
        restoration_sha,
        authority_materialization,
        hashlib.sha256(authority_materialization.read_bytes()).hexdigest(),
        authority,
    )
    operation_root = private_root / "chummer-public-download-authority-test"
    operation_root.mkdir(mode=0o700)
    canonical_before = controller.tree_sha256_file_stream(
        shelf,
        label="canonical shelf before authority mismatch",
    )
    config = SimpleNamespace(
        source_root=ROOT,
        source_head=source_head,
        shelf_root=shelf,
        migration_candidate_root=candidates[1][0],
        migration_authority=authority,
        migration_authority_sha256=hashlib.sha256(
            authority.read_bytes()
        ).hexdigest(),
        manifest_closure_restoration_spec=restoration_spec,
        manifest_closure_restoration_spec_sha256=restoration_sha,
        operation_root=operation_root,
        shelf_source=operation_root / "release-shelf",
    )

    with pytest.raises(
        (controller.CutoverError, attestor.CutoverAttestationError),
        match="authority|candidate",
    ):
        controller.prepare_sidecar_release_shelf(
            config,
            generation=generation,
            attestor=attestor,
        )

    assert controller.tree_sha256_file_stream(
        shelf,
        label="canonical shelf after authority mismatch",
    ) == canonical_before


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
