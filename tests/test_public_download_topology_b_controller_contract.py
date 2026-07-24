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
OVERLAY_PUBLISHER_PATH = (
    ROOT / "scripts" / "publish_public_edge_portal_overlay.py"
)


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
overlay_publisher = load_module(
    OVERLAY_PUBLISHER_PATH,
    "topology_b_overlay_publisher_contract",
)

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


def test_stage_application_uses_isolated_active_transaction_namespace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    require_topology_b_surface()
    operation_root = (
        tmp_path / "chummer-public-download-overlay-geometry-test"
    )
    release_channel_receipt = tmp_path / "RELEASE_CHANNEL.generated.json"
    release_channel_receipt.write_text("{}\n", encoding="utf-8")
    config = object.__new__(controller.SidecarConfig)
    for field, value in {
        "source_root": ROOT,
        "operation_root": operation_root,
        "release_channel_receipt": release_channel_receipt,
        "release_channel_receipt_sha256": "a" * 64,
        "delivery_phase": "windows-preview",
    }.items():
        object.__setattr__(config, field, value)

    captured: dict[str, Any] = {}

    class CapturingRunner:
        def python(
            self,
            script: Path,
            arguments: list[str],
            **kwargs: Any,
        ) -> bytes:
            captured["script"] = script
            captured["arguments"] = list(arguments)
            captured["kwargs"] = dict(kwargs)
            return b""

    actions = object.__new__(controller.TopologyBActions)
    actions.config = config
    actions.runner = CapturingRunner()
    host_build = {
        "hostBuildRoot": str(config.host_build_root),
        "home": str(config.host_build_root / "home"),
        "dotnetCliHome": str(config.host_build_root / "dotnet-cli"),
        "nugetPackages": str(config.host_build_root / "nuget-packages"),
        "nugetHttpCache": str(config.host_build_root / "nuget-http-cache"),
        "tmp": str(config.host_build_root / "tmp"),
        "sdk": str(config.host_build_root / "sdk"),
        "playwrightPythonRoot": str(
            config.host_build_root / "playwright-python"
        ),
        "playwrightPythonTreeSha256": "c" * 64,
        "playwrightBrowsersRoot": str(
            config.host_build_root / "playwright-browsers"
        ),
        "playwrightBrowserTreeSha256": "d" * 64,
        "playwrightAuthority": str(
            config.host_build_root / "playwright-authority.json"
        ),
        "playwrightAuthoritySha256": "e" * 64,
    }
    monkeypatch.setattr(
        controller,
        "prepare_operation_host_build",
        lambda _config: host_build,
    )
    monkeypatch.setattr(
        controller,
        "tree_sha256_file_stream",
        lambda root, *, label: "b" * 64,
    )

    staged = actions._stage_application()

    arguments = captured["arguments"]

    def argument_path(flag: str) -> Path:
        return Path(arguments[arguments.index(flag) + 1])

    assert captured["script"] == OVERLAY_PUBLISHER_PATH
    assert config.overlay_root == (
        operation_root / "overlay-active-unused" / "app"
    )
    assert config.overlay_root.parent != operation_root
    assert argument_path("--active-root") == config.overlay_root
    assert argument_path("--staging-root") == config.overlay_staging_root
    assert argument_path("--backup-root") == config.overlay_backup_root
    assert argument_path("--build-root") == config.overlay_build_root
    assert argument_path("--host-build-root") == config.host_build_root
    assert argument_path("--downloads-source-root") == config.shelf_source
    assert argument_path("--playwright-authority") == Path(
        host_build["playwrightAuthority"]
    )
    assert (
        arguments[arguments.index("--playwright-authority-sha256") + 1]
        == "e" * 64
    )
    assert arguments[arguments.index("--surface-profile") + 1] == "public-download"
    assert arguments[arguments.index("--delivery-phase") + 1] == "windows-preview"
    assert argument_path("--output") == operation_root / "overlay-stage.json"
    assert staged == {
        "receipt": str(operation_root / "overlay-stage.json"),
        "root": str(config.overlay_staging_root),
        "treeSha256": "b" * 64,
        "hostBuild": host_build,
    }
    environment = captured["kwargs"]["environment"]
    assert environment == {
        "HOME": str(config.host_build_root / "home"),
        "DOTNET_ROOT": str(config.host_build_root / "sdk"),
        "DOTNET_CLI_HOME": str(config.host_build_root / "dotnet-cli"),
        "NUGET_PACKAGES": str(config.host_build_root / "nuget-packages"),
        "NUGET_HTTP_CACHE_PATH": str(
            config.host_build_root / "nuget-http-cache"
        ),
        "TMPDIR": str(config.host_build_root / "tmp"),
        "PATH": f"{config.host_build_root / 'sdk'}:/usr/bin:/bin",
    }

    path_plan = overlay_publisher.validate_publisher_path_plan(
        output=argument_path("--output"),
        release_channel_receipt=argument_path(
            "--release-channel-receipt"
        ),
        release_channel_receipt_sha256=arguments[
            arguments.index("--release-channel-receipt-sha256") + 1
        ],
        source_root=argument_path("--source-root"),
        staging_root=argument_path("--staging-root"),
        active_root=argument_path("--active-root"),
        backup_root=argument_path("--backup-root"),
        build_root=argument_path("--build-root"),
        activation_mode="copy",
    )

    assert path_plan["activeRoot"] == config.overlay_root
    assert not overlay_publisher.path_is_within(
        path_plan["output"],
        path_plan["activeRoot"].parent,
    )


def test_candidate_image_is_journal_bound_before_compose_render(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    require_topology_b_surface()
    source_head = "a" * 40
    image_id = "sha256:" + "b" * 64
    tag = f"chummer-run-api:public-download-{source_head[:16]}-c0ffee12"
    config = SimpleNamespace(
        source_head=source_head,
        operation_root=tmp_path / "operation",
    )
    records: list[tuple[str, str, dict[str, Any]]] = []
    actions = object.__new__(controller.TopologyBActions)
    actions.runner = object()
    actions._stage_application = lambda: {"treeSha256": "c" * 64}
    actions._record = (
        lambda phase, name, receipt: records.append(
            (phase, name, dict(receipt))
        )
    )
    monkeypatch.setattr(
        controller,
        "prepare_immutable_build_contexts",
        lambda *_args, **_kwargs: (
            {},
            {
                name: character * 64
                for name, character in (
                    ("default", "1"),
                    ("run-services", "2"),
                    ("hub-registry", "3"),
                    ("fleet-media", "4"),
                    ("design-product", "5"),
                )
            },
            tmp_path / "contexts.json",
        ),
    )
    monkeypatch.setattr(controller.secrets, "token_hex", lambda _count: "c0ffee12")

    def fake_build(*_args: Any, **kwargs: Any) -> tuple[str, str]:
        assert kwargs["unique_tag"] == tag
        kwargs["on_built"](tag, image_id)
        return tag, image_id

    monkeypatch.setattr(controller, "build_candidate_image", fake_build)
    monkeypatch.setattr(
        controller,
        "resolve_image_tag",
        lambda *_args, **_kwargs: image_id,
    )

    def fail_compose(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise controller.CommandFailure(
            label="render topology-B Compose",
            failure_kind="failed",
            status=1,
            stderr=b"daemon unavailable",
        )

    monkeypatch.setattr(controller, "materialize_sidecar_compose", fail_compose)

    with pytest.raises(controller.CommandFailure):
        actions.materialize_sidecar_compose(config, {}, {})

    assert len(records) == 2
    plan_phase, plan_name, plan = records[0]
    assert plan_phase == "candidate-image-planned"
    assert plan_name == "candidateImagePlan"
    assert plan["candidateTag"] == tag
    phase, name, binding = records[1]
    assert phase == "candidate-image-built"
    assert name == "candidateImage"
    assert binding["candidateTag"] == tag
    assert binding["candidateImageId"] == image_id
    assert binding["sourceHead"] == source_head


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
        self.primary_failures: list[Exception] = []

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

    def record_primary_failure(
        self,
        _config: Any,
        error: Exception,
    ) -> dict[str, Any]:
        self.primary_failures.append(error)
        return {"status": "retained"}

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


def test_primary_failure_receipt_preserves_stage_without_raw_secret(
    tmp_path: Path,
) -> None:
    require_topology_b_surface()
    receipt_root = tmp_path / "receipts"
    receipt_root.mkdir(mode=0o700)
    receipt_root.chmod(0o700)
    journal = receipt_root / "operation.json"
    state = {
        "schema": controller.TOPOLOGY_B_OPERATION_SCHEMA,
        "phase": "data-protection-prepared",
        "updatedAtUtc": controller.utc_now(),
        "receipts": {"dataProtection": {"status": "pass"}},
    }
    controller.write_private_json(journal, state)
    source_head = "a" * 40
    config = SimpleNamespace(
        operation_journal=journal,
        project_name="chummer-public-download-failure-test",
        source_head=source_head,
    )
    actions = object.__new__(controller.TopologyBActions)
    actions.config = config
    actions._state = state
    secret = b"TOP_SECRET_VALUE_MUST_NOT_REACH_THE_JOURNAL"
    error = controller.CommandFailure(
        label="render topology-B Compose",
        failure_kind="failed",
        status=1,
        stdout=b"",
        stderr=b"compose failure: " + secret,
    )
    wrapped = controller.RecoveryUncertain("wrapped cleanup failure")
    wrapped.__cause__ = error

    receipt = actions.record_primary_failure(config, wrapped)

    raw = journal.read_bytes()
    payload = json.loads(raw)
    assert secret not in raw
    assert payload["phase"] == "data-protection-prepared"
    assert payload["receipts"]["primaryFailure"] == receipt
    command = receipt["command"]
    assert command["stage"] == "render topology-B Compose"
    assert command["exitStatus"] == 1
    assert command["stderrSha256"] == hashlib.sha256(
        b"compose failure: " + secret
    ).hexdigest()
    assert command["safeStderrSummary"].startswith("stderr content redacted")


def test_topology_b_runner_hashes_but_does_not_expose_failed_command_stderr(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = b"RUNNER_SECRET_VALUE_MUST_STAY_PRIVATE"
    stderr = b"\xfffailure: " + secret + (b"x" * 8192)
    config = SimpleNamespace(
        docker_config_root=tmp_path / "docker",
        project_name="chummer-public-download-runner-test",
        compose_file=tmp_path / "compose.json",
        operation_root=tmp_path,
    )
    runner = controller.TopologyBRunner(config)
    monkeypatch.setattr(
        controller.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=17,
            stdout=b"bounded output",
            stderr=stderr,
        ),
    )

    with pytest.raises(controller.CommandFailure) as raised:
        runner.run(["/usr/bin/false"], label="test governed command")

    evidence = raised.value.evidence
    assert secret.decode("ascii") not in str(raised.value)
    assert secret.decode("ascii") not in json.dumps(evidence, sort_keys=True)
    assert evidence["exitStatus"] == 17
    assert evidence["stderrSha256"] == hashlib.sha256(stderr).hexdigest()
    assert evidence["stderrSizeBytes"] == len(stderr)


def test_topology_b_runner_round_trips_real_subprocess_stdin(
    tmp_path: Path,
) -> None:
    config = SimpleNamespace(
        docker_config_root=tmp_path / "docker",
        project_name="chummer-public-download-runner-test",
        compose_file=tmp_path / "compose.json",
        operation_root=tmp_path,
    )
    runner = controller.TopologyBRunner(config)
    payload = b"governed topology-B stdin"

    output = runner.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                "value = sys.stdin.buffer.read(); "
                "sys.stdout.buffer.write(value[::-1])"
            ),
        ],
        label="test governed stdin round trip",
        input_bytes=payload,
    )

    assert output == payload[::-1]


def test_topology_b_runner_uses_devnull_without_input(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = SimpleNamespace(
        docker_config_root=tmp_path / "docker",
        project_name="chummer-public-download-runner-test",
        compose_file=tmp_path / "compose.json",
        operation_root=tmp_path,
    )
    runner = controller.TopologyBRunner(config)
    observed: dict[str, Any] = {}

    def completed(*_args: Any, **kwargs: Any) -> SimpleNamespace:
        observed.update(kwargs)
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setattr(controller.subprocess, "run", completed)

    assert runner.run(["/usr/bin/true"], label="test no-input command") == b""
    assert observed["input"] is None
    assert observed["stdin"] is controller.subprocess.DEVNULL


def test_topology_b_runner_normalizes_signal_exit_for_replayable_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = SimpleNamespace(
        docker_config_root=tmp_path / "docker",
        project_name="chummer-public-download-runner-test",
        compose_file=tmp_path / "compose.json",
        operation_root=tmp_path,
    )
    runner = controller.TopologyBRunner(config)
    monkeypatch.setattr(
        controller.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=-9,
            stdout=b"",
            stderr=b"",
        ),
    )

    with pytest.raises(controller.CommandFailure) as raised:
        runner.run(["/usr/bin/false"], label="test signaled command")

    assert raised.value.evidence["exitStatus"] == 137


class FakeVolumeRunner:
    def __init__(
        self,
        *,
        existing_labels: dict[str, dict[str, str]] | None = None,
        inspection_overrides: dict[str, dict[str, Any]] | None = None,
        fail_create_names: set[str] | None = None,
    ) -> None:
        self.labels = dict(existing_labels or {})
        self.inspected: list[str] = []
        self.created: list[str] = []
        self.removed: list[str] = []
        self.inspection_overrides = dict(inspection_overrides or {})
        self.fail_create_names = set(fail_create_names or set())

    def docker(self, arguments: list[str], **_kwargs: Any) -> bytes:
        if arguments[:2] == ["volume", "ls"]:
            filter_value = arguments[-1]
            assert filter_value.startswith("name=^")
            assert filter_value.endswith("$")
            name = filter_value.removeprefix("name=^").removesuffix("$")
            return f"{name}\n".encode("utf-8") if name in self.labels else b""
        if arguments[:2] == ["volume", "create"]:
            name = arguments[-1]
            self.created.append(name)
            if name in self.fail_create_names:
                raise controller.CutoverError("injected volume create failure")
            if name not in self.labels:
                labels: dict[str, str] = {}
                for index, value in enumerate(arguments[:-1]):
                    if value == "--label":
                        key, label_value = arguments[index + 1].split("=", 1)
                        labels[key] = label_value
                self.labels[name] = labels
            return f"{name}\n".encode("utf-8")
        if arguments[:2] == ["volume", "inspect"]:
            name = arguments[2]
            self.inspected.append(name)
            inspection = {
                "Name": name,
                "Labels": self.labels[name],
                "Driver": "local",
                "Scope": "local",
                "Options": None,
                "Mountpoint": f"/var/lib/docker/volumes/{name}/_data",
            }
            inspection.update(self.inspection_overrides.get(name, {}))
            return json.dumps(
                [inspection]
            ).encode("utf-8")
        if arguments[:2] == ["volume", "rm"]:
            name = arguments[2]
            self.removed.append(name)
            self.labels.pop(name)
            return f"{name}\n".encode("utf-8")
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


def test_preexisting_later_volume_is_rejected_before_any_create() -> None:
    require_topology_b_surface()
    config = volume_test_config()
    logical = controller.SIDECAR_LOGICAL_VOLUMES[3]
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

    with pytest.raises(
        controller.RecoveryUncertain,
        match="preexisting topology-B volume is prohibited",
    ):
        actions.create_sidecar_resources(config, {})

    assert runner.created == []
    assert runner.inspected == []


@pytest.mark.parametrize("options", (None, {}))
def test_exact_new_local_volume_authority_is_accepted(
    options: dict[str, str] | None,
) -> None:
    require_topology_b_surface()
    config = volume_test_config()
    runner = FakeVolumeRunner(
        inspection_overrides={
            name: {"Options": options}
            for name in config.volume_names.values()
        }
    )
    actions = concrete_actions_with_volume_runner(runner)

    receipt = actions.create_sidecar_resources(config, {})

    expected = [
        config.volume_names[logical]
        for logical in controller.SIDECAR_LOGICAL_VOLUMES
    ]
    assert receipt["reusedEmptyVolumes"] == []
    assert receipt["volumes"] == expected
    assert runner.created == expected
    assert runner.inspected == expected


def test_volume_mountpoint_is_never_traversed_on_the_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    require_topology_b_surface()
    config = volume_test_config()
    runner = FakeVolumeRunner()
    actions = concrete_actions_with_volume_runner(runner)

    def forbidden_host_traversal(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("Docker Mountpoint must not be traversed on host")

    monkeypatch.setattr(controller.Path, "lstat", forbidden_host_traversal)
    monkeypatch.setattr(controller.os, "scandir", forbidden_host_traversal)

    assert actions.create_sidecar_resources(config, {})["volumes"]


@pytest.mark.parametrize(
    "ambiguity",
    (
        "driver",
        "scope",
        "options",
        "labels",
        "name",
        "mountpoint-tab",
        "mountpoint-del",
        "mountpoint-parent",
    ),
)
def test_new_volume_authority_rejects_ambiguous_metadata(
    ambiguity: str,
) -> None:
    require_topology_b_surface()
    config = volume_test_config()
    logical = controller.SIDECAR_LOGICAL_VOLUMES[0]
    name = config.volume_names[logical]
    override: dict[str, Any]
    if ambiguity == "driver":
        override = {"Driver": "foreign"}
    elif ambiguity == "scope":
        override = {"Scope": "global"}
    elif ambiguity == "options":
        override = {"Options": {"type": "nfs"}}
    elif ambiguity == "labels":
        override = {"Labels": {"foreign": "label"}}
    elif ambiguity == "name":
        override = {"Name": f"{name}-foreign"}
    elif ambiguity == "mountpoint-tab":
        override = {
            "Mountpoint": f"/var/lib/docker/volumes/\t/{name}/_data"
        }
    elif ambiguity == "mountpoint-del":
        override = {
            "Mountpoint": f"/var/lib/docker/volumes/\x7f/{name}/_data"
        }
    else:
        override = {
            "Mountpoint": (
                f"/var/lib/docker/volumes/foreign/../{name}/_data"
            )
        }
    runner = FakeVolumeRunner(
        inspection_overrides={name: override},
    )
    actions = concrete_actions_with_volume_runner(runner)

    with pytest.raises(
        controller.RecoveryUncertain,
        match="created topology-B volume authority is ambiguous",
    ):
        actions.create_sidecar_resources(config, {})

    assert runner.created == [name]
    assert runner.inspected == [name]


def test_inspect_rejected_volume_is_not_deleted_by_cleanup() -> None:
    require_topology_b_surface()
    config = volume_test_config()
    logical = controller.SIDECAR_LOGICAL_VOLUMES[0]
    name = config.volume_names[logical]
    runner = FakeVolumeRunner(
        inspection_overrides={name: {"Driver": "foreign"}},
    )
    actions = concrete_actions_with_volume_runner(runner)

    with pytest.raises(
        controller.RecoveryUncertain,
        match="created topology-B volume authority is ambiguous",
    ):
        actions.create_sidecar_resources(config, {})

    actions._state = {"receipts": {}}
    actions._prove_pre_runtime_absence = lambda _config: {"status": "pass"}
    actions._preflight_candidate_image = lambda _config: {
        "disposition": "not-bound"
    }
    actions._sidecar_container_references = (
        lambda *_args, **_kwargs: []
    )
    actions._prove_zero_sidecar_project_networks = (
        lambda *_args, **_kwargs: None
    )
    actions._prove_sidecar_resources_unreferenced = (
        lambda *_args, **_kwargs: None
    )
    actions._remove_candidate_image = lambda preflight: dict(preflight)

    with pytest.raises(
        controller.RecoveryUncertain,
        match="topology-B volume identity is ambiguous",
    ):
        actions.cleanup_sidecar_resources(config)

    assert runner.removed == []
    assert set(runner.labels) == {name}


def test_partial_new_volume_failure_remains_exactly_cleanupable() -> None:
    require_topology_b_surface()
    config = volume_test_config()
    first = config.volume_names[controller.SIDECAR_LOGICAL_VOLUMES[0]]
    second = config.volume_names[controller.SIDECAR_LOGICAL_VOLUMES[1]]
    runner = FakeVolumeRunner(fail_create_names={second})
    actions = concrete_actions_with_volume_runner(runner)

    with pytest.raises(
        controller.CutoverError,
        match="injected volume create failure",
    ):
        actions.create_sidecar_resources(config, {})

    assert set(runner.labels) == {first}
    actions._state = {"receipts": {}}
    actions._prove_pre_runtime_absence = lambda _config: {"status": "pass"}
    actions._preflight_candidate_image = lambda _config: {
        "disposition": "not-bound"
    }
    actions._sidecar_container_references = (
        lambda *_args, **_kwargs: []
    )
    actions._prove_zero_sidecar_project_networks = (
        lambda *_args, **_kwargs: None
    )
    actions._prove_sidecar_resources_unreferenced = (
        lambda *_args, **_kwargs: None
    )
    actions._remove_candidate_image = lambda preflight: dict(preflight)

    receipt = actions.cleanup_sidecar_resources(config)

    assert receipt["removedVolumes"] == [first]
    assert runner.removed == [first]
    assert runner.labels == {}


class FakeCleanupRunner:
    def __init__(
        self,
        *,
        blocker: str | None = None,
        image_id: str | None = None,
        tag: str | None = None,
        tag_image_id: str | None = None,
        referencing_container: bool = False,
        project_candidate_containers: bool = False,
        retain_project_containers_after_down: bool = False,
        project_compose_file: str = "",
        project_working_dir: str = "",
        project_volume_names: list[str] | None = None,
        project_oneoff: str = "False",
        project_container_number: str = "1",
        foreign_image_id: str | None = None,
        foreign_volume_name: str | None = None,
        foreign_same_project: bool = False,
        post_down_foreign_volume_name: str | None = None,
        post_down_project_network: bool = False,
        repo_tags: list[str] | None = None,
        repo_digests: list[str] | None = None,
        volume_labels: dict[str, dict[str, str]] | None = None,
        volume_inspection_overrides: (
            dict[str, dict[str, Any]] | None
        ) = None,
    ) -> None:
        self.blocker = blocker
        self.image_id = image_id
        self.tag = tag
        self.tag_image_id = tag_image_id or image_id
        self.referencing_container = referencing_container
        self.project_candidate_containers = project_candidate_containers
        self.retain_project_containers_after_down = (
            retain_project_containers_after_down
        )
        self.project_compose_file = project_compose_file
        self.project_working_dir = project_working_dir
        self.project_volume_names = list(project_volume_names or [])
        self.project_oneoff = project_oneoff
        self.project_container_number = project_container_number
        self.foreign_image_id = foreign_image_id
        self.foreign_volume_name = foreign_volume_name
        self.foreign_same_project = foreign_same_project
        self.post_down_foreign_volume_name = (
            post_down_foreign_volume_name
        )
        self.post_down_project_network = post_down_project_network
        self.repo_tags = repo_tags
        self.repo_digests = repo_digests
        self.volume_labels = dict(volume_labels or {})
        self.volume_inspection_overrides = dict(
            volume_inspection_overrides or {}
        )
        self.image_present = image_id is not None
        self.tag_present = tag is not None
        self.docker_calls: list[list[str]] = []
        self.compose_calls: list[list[str]] = []
        self.run_calls: list[list[str]] = []
        self.events: list[tuple[str, list[str]]] = []

    def run(self, arguments: list[str], **_kwargs: Any) -> bytes:
        self.run_calls.append(list(arguments))
        self.events.append(("run", list(arguments)))
        assert arguments[:4] == ["/usr/bin/ss", "-H", "-ltn", "sport = :18091"]
        return (
            b"LISTEN 0 128 172.17.0.1:18091 0.0.0.0:*\n"
            if self.blocker == "listener"
            else b""
        )

    def compose(self, arguments: list[str], **_kwargs: Any) -> bytes:
        self.compose_calls.append(list(arguments))
        self.events.append(("compose", list(arguments)))
        if (
            arguments == ["down", "--remove-orphans"]
            and not self.retain_project_containers_after_down
        ):
            self.project_candidate_containers = False
        if (
            arguments == ["down", "--remove-orphans"]
            and self.post_down_foreign_volume_name is not None
        ):
            self.referencing_container = True
            self.foreign_volume_name = self.post_down_foreign_volume_name
            if self.foreign_image_id is None:
                self.foreign_image_id = "sha256:" + "c" * 64
        if (
            arguments == ["down", "--remove-orphans"]
            and self.post_down_project_network
        ):
            self.blocker = "networks"
        return b""

    def docker(self, arguments: list[str], **_kwargs: Any) -> bytes:
        self.docker_calls.append(list(arguments))
        self.events.append(("docker", list(arguments)))
        if self.blocker == "probeFailure":
            raise controller.CommandFailure(
                label="test cleanup probe",
                failure_kind="failed",
                status=1,
                stderr=b"daemon unavailable",
            )
        if arguments[:2] == ["container", "ls"]:
            if self.blocker == "malformed":
                return b"\xff"
            filter_value = arguments[-1]
            if filter_value.startswith("label=com.docker.compose.project="):
                return b"c" * 64 + b"\n" if self.blocker == "containers" else b""
            if arguments == [
                "container",
                "ls",
                "--all",
                "--quiet",
                "--no-trunc",
            ]:
                container_ids: list[str] = []
                if self.referencing_container:
                    container_ids.append("d" * 64)
                if self.project_candidate_containers:
                    container_ids.extend(("1" * 64, "2" * 64))
                if not container_ids:
                    return b""
                return ("\n".join(container_ids) + "\n").encode("utf-8")
        if arguments[:2] == ["container", "inspect"]:
            container_id = arguments[2]
            service = {
                "1" * 64: "chummer-public-download-init",
                "2" * 64: controller.PORTAL_SERVICE,
            }.get(container_id)
            labels = (
                {
                    "com.docker.compose.project": (
                        "chummer-public-download-cleanup-test"
                    ),
                    "com.docker.compose.project.config_files": (
                        self.project_compose_file
                    ),
                    "com.docker.compose.project.working_dir": (
                        self.project_working_dir
                    ),
                    "com.docker.compose.service": service,
                    "com.docker.compose.oneoff": self.project_oneoff,
                    "com.docker.compose.container-number": (
                        self.project_container_number
                    ),
                }
                if service is not None
                else (
                    {
                        "com.docker.compose.project": (
                            "chummer-public-download-cleanup-test"
                        ),
                        "com.docker.compose.service": "foreign-service",
                    }
                    if self.foreign_same_project
                    else {}
                )
            )
            if service is not None:
                mounts = [
                    {"Type": "volume", "Name": name}
                    for name in self.project_volume_names
                ]
                inspected_image_id = self.image_id
            else:
                mounts = (
                    [
                        {
                            "Type": "volume",
                            "Name": self.foreign_volume_name,
                        }
                    ]
                    if self.foreign_volume_name is not None
                    else []
                )
                inspected_image_id = (
                    self.foreign_image_id or self.image_id
                )
            return json.dumps(
                [
                    {
                        "Id": container_id,
                        "Image": inspected_image_id,
                        "Config": {"Labels": labels},
                        "Mounts": mounts,
                    }
                ]
            ).encode("utf-8")
        if arguments[:2] == ["network", "ls"]:
            return b"e" * 64 + b"\n" if self.blocker == "networks" else b""
        if arguments[:2] == ["volume", "ls"]:
            filter_value = arguments[-1]
            if filter_value.startswith(
                "label=run.chummer.public-download-operation="
            ):
                return (
                    b"operation-volume\n"
                    if self.blocker == "labeledVolumes"
                    else b""
                )
            if filter_value.startswith("name=^"):
                name = filter_value.removeprefix("name=^").removesuffix("$")
                if self.blocker == "exactVolume":
                    return name.encode("utf-8") + b"\n"
                if name in self.volume_labels:
                    return name.encode("utf-8") + b"\n"
                return b""
        if arguments[:2] == ["volume", "inspect"]:
            name = arguments[2]
            inspection = {
                "Name": name,
                "Labels": self.volume_labels.get(name, {}),
                "Driver": "local",
                "Scope": "local",
                "Options": None,
                "Mountpoint": f"/var/lib/docker/volumes/{name}/_data",
            }
            inspection.update(
                self.volume_inspection_overrides.get(name, {})
            )
            return json.dumps(
                [inspection]
            ).encode("utf-8")
        if arguments[:2] == ["volume", "rm"]:
            self.volume_labels.pop(arguments[2], None)
            return f"{arguments[2]}\n".encode("utf-8")
        if arguments == ["image", "ls", "--all", "--quiet", "--no-trunc"]:
            if not self.image_present:
                return b""
            identifiers = {self.image_id}
            if self.tag_present:
                identifiers.add(self.tag_image_id)
            return (
                "\n".join(
                    sorted(item for item in identifiers if item is not None)
                )
                + "\n"
            ).encode("utf-8")
        if arguments[:4] == ["image", "ls", "--quiet", "--no-trunc"]:
            requested_tag = arguments[4]
            if self.tag is not None:
                assert requested_tag == self.tag
            if not self.tag_present or self.tag_image_id is None:
                return b""
            return f"{self.tag_image_id}\n".encode("utf-8")
        if arguments[:2] == ["image", "inspect"]:
            assert arguments[2] in {self.tag, self.image_id}
            return json.dumps(
                [
                    {
                        "Id": self.image_id,
                        "RepoTags": (
                            self.repo_tags
                            if self.repo_tags is not None
                            else ([self.tag] if self.tag_present else [])
                        ),
                        "RepoDigests": self.repo_digests,
                        "Config": {
                            "Labels": {
                                "org.opencontainers.image.revision": "a" * 40,
                                "run.chummer.runtime-profile": (
                                    controller.RUNTIME_PROFILE
                                ),
                                **{
                                    "run.chummer.build-context."
                                    f"{name}.sha256": character * 64
                                    for name, character in (
                                        ("default", "1"),
                                        ("run-services", "2"),
                                        ("hub-registry", "3"),
                                        ("fleet-media", "4"),
                                        ("design-product", "5"),
                                    )
                                },
                            }
                        },
                    }
                ]
            ).encode("utf-8")
        if arguments[:2] == ["image", "rm"]:
            assert arguments[2] == self.image_id
            self.image_present = False
            self.tag_present = False
            return f"Deleted: {self.image_id}\n".encode("utf-8")
        raise AssertionError(arguments)


def cleanup_test_config(tmp_path: Path) -> SimpleNamespace:
    operation_root = tmp_path / "chummer-public-download-cleanup-test"
    operation_root.mkdir()
    compose_file = operation_root / "public-download-runtime.json"
    materialization_receipt = operation_root / "compose-materialization.json"
    runtime_attestation = operation_root / "compose-runtime-attestation.json"
    compose_file.write_text(
        '{"mustNotBeInterpolated":"${SECRET_REQUIRED_VARIABLE:?missing}"}\n',
        encoding="utf-8",
    )
    materialization_receipt.write_text("{}\n", encoding="utf-8")
    runtime_attestation.write_text("{}\n", encoding="utf-8")
    for path in (compose_file, materialization_receipt, runtime_attestation):
        path.chmod(0o600)
    volume_names = {
        logical: (
            f"{operation_root.name}-"
            f"{logical.removeprefix('public-download-')}"
        )
        for logical in controller.SIDECAR_LOGICAL_VOLUMES
    }
    return SimpleNamespace(
        operation=controller.CUTOVER_OPERATION,
        operation_root=operation_root,
        project_name=operation_root.name,
        source_root=ROOT,
        source_head="a" * 40,
        compose_file=compose_file,
        materialization_receipt=materialization_receipt,
        runtime_attestation=runtime_attestation,
        volume_names=volume_names,
        sidecar_certificate=operation_root / "sidecar.pfx",
        sidecar_certificate_password=operation_root / "sidecar.password",
        overlay_staging_root=operation_root / "app-overlay",
        fleet_source=operation_root / "fleet-source",
        fleet_sha256="1" * 64,
        shelf_source=operation_root / "release-shelf",
        projection_snapshot_root=operation_root / "projection",
        projection_source_tree_sha256="2" * 64,
        runtime_proof_source=operation_root / "runtime-proof.json",
        runtime_proof_sha256="3" * 64,
        final_gold_source=operation_root / "final-gold.json",
        final_gold_sha256="4" * 64,
    )


def concrete_cleanup_actions(
    config: SimpleNamespace,
    runner: FakeCleanupRunner,
    receipts: dict[str, Any],
) -> tuple[Any, list[tuple[str, str, dict[str, Any]]]]:
    actions = object.__new__(controller.TopologyBActions)
    actions.config = config
    actions.runner = runner
    actions._state = {
        "phase": "data-protection-prepared",
        "receipts": receipts,
    }
    recorded: list[tuple[str, str, dict[str, Any]]] = []
    actions._record = (
        lambda phase, name, receipt: recorded.append(
            (phase, name, dict(receipt))
        )
    )
    return actions, recorded


def candidate_binding(config: SimpleNamespace) -> tuple[str, str, dict[str, Any]]:
    image_id = "sha256:" + "b" * 64
    tag = (
        "chummer-run-api:public-download-"
        f"{config.source_head[:16]}-c0ffee12"
    )
    return (
        image_id,
        tag,
        {
            "contractName": (
                "chummer.public-download-candidate-image-binding/v1"
            ),
            "candidateTag": tag,
            "candidateImageId": image_id,
            "sourceHead": config.source_head,
            "boundAtUtc": "2026-07-24T00:00:00Z",
        },
    )


def candidate_plan(config: SimpleNamespace, tag: str) -> dict[str, Any]:
    return {
        "contractName": "chummer.public-download-candidate-image-plan/v1",
        "candidateTag": tag,
        "sourceHead": config.source_head,
        "immutableBuildContextDigests": {
            name: character * 64
            for name, character in (
                ("default", "1"),
                ("run-services", "2"),
                ("hub-registry", "3"),
                ("fleet-media", "4"),
                ("design-product", "5"),
            )
        },
        "plannedAtUtc": "2026-07-24T00:00:00Z",
    }


def complete_runtime_receipts(
    config: SimpleNamespace,
    *,
    environment_update: dict[str, str] | None = None,
) -> dict[str, Any]:
    _image_id, _tag, binding = candidate_binding(config)
    shelf = {"shelfTreeSha256": "5" * 64}
    data_protection = {
        "certificateSha256": "6" * 64,
        "passwordSha256": "7" * 64,
    }
    application = {"treeSha256": "8" * 64}
    environment = controller._sidecar_compose_environment(
        config,
        dp=data_protection,
        app_overlay_sha256=application["treeSha256"],
        shelf=shelf,
    )
    if environment_update:
        environment.update(environment_update)
    canonical_source_root = config.source_root.resolve(strict=True)
    base_source = canonical_source_root / "docker-compose.public-edge.yml"
    profile_source = (
        canonical_source_root / "docker-compose.public-downloads.yml"
    )
    base_sha256 = hashlib.sha256(base_source.read_bytes()).hexdigest()
    profile_sha256 = hashlib.sha256(profile_source.read_bytes()).hexdigest()
    compose_sha256 = hashlib.sha256(config.compose_file.read_bytes()).hexdigest()
    config.materialization_receipt.write_text(
        json.dumps(
            {
                "contractName": (
                    "chummer.public-download-only-compose-materialization/v1"
                ),
                "status": "pass",
                "operation": config.operation,
                "sourceRoot": str(canonical_source_root),
                "sourceHead": config.source_head,
                "baseComposeSource": str(base_source),
                "baseComposeSourceSha256": base_sha256,
                "profileSource": str(profile_source),
                "profileSourceSha256": profile_sha256,
                "candidateImageId": binding["candidateImageId"],
                "composeSha256": compose_sha256,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    config.runtime_attestation.write_text(
        json.dumps(
            {
                "contractName": (
                    "chummer.public-download-only-compose-runtime-attestation/v1"
                ),
                "status": "pass",
                "operation": config.operation,
                "runtimeProfile": controller.RUNTIME_PROFILE,
                "projectName": config.project_name,
                "operationRoot": str(config.operation_root),
                "portalImageId": binding["candidateImageId"],
                "initializerImageId": binding["candidateImageId"],
                "initializerConstrained": True,
                "portalAppCopiedReadOnly": True,
                "portalFleetCopiedReadOnly": True,
                "longRunningSourceBindsAbsent": True,
                "releaseShelfPreinitialized": True,
                "releaseShelfPortalReadOnly": True,
                "isolatedVolumes": dict(config.volume_names),
                "runtimeInputs": {
                    "appOverlay": {
                        "source": str(config.overlay_staging_root),
                        "sha256": application["treeSha256"],
                    },
                    "fleet": {
                        "source": str(config.fleet_source),
                        "sha256": config.fleet_sha256,
                    },
                    "shelf": {
                        "source": str(config.shelf_source),
                        "sha256": shelf["shelfTreeSha256"],
                    },
                    "projection": {
                        "source": str(config.projection_snapshot_root),
                        "sha256": config.projection_source_tree_sha256,
                    },
                    "runtimeProof": {
                        "source": str(config.runtime_proof_source),
                        "sha256": config.runtime_proof_sha256,
                    },
                    "finalGold": {
                        "source": str(config.final_gold_source),
                        "sha256": config.final_gold_sha256,
                    },
                    "certificateSha256": (
                        data_protection["certificateSha256"]
                    ),
                    "certificatePasswordSha256": (
                        data_protection["passwordSha256"]
                    ),
                    "certificateAuthority": (
                        "operation-bound-sidecar-only"
                    ),
                },
                "postgresServicesAbsent": True,
                "postgresEnvironmentAbsent": True,
                "postgresMountsAbsent": True,
                "postgresHostMappingAbsent": True,
                "portalBuildAbsent": True,
                "publicDownloadsHealthcheck": True,
                "releaseShelfPosture": {
                    "CHUMMER_RELEASE_SHELF_LAYOUT_V1_REQUIRED": "true",
                    "CHUMMER_RELEASE_SHELF_INITIAL_MIGRATION_ALLOWED": (
                        "false"
                    ),
                },
                "portalMountCount": 10,
                "initializerMountCount": 18,
                "publishedAddress": controller.SIDECAR_ADDRESS,
                "publishedPort": controller.SIDECAR_PORT,
                "sourceRoot": str(canonical_source_root),
                "sourceHead": config.source_head,
                "baseComposeSourceSha256": base_sha256,
                "profileSourceSha256": profile_sha256,
                "materializedComposeSha256": compose_sha256,
                "renderedComposeSha256": hashlib.sha256(b"").hexdigest(),
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    config.materialization_receipt.chmod(0o600)
    config.runtime_attestation.chmod(0o600)
    return {
        "shelf": shelf,
        "dataProtection": data_protection,
        "candidateImagePlan": candidate_plan(
            config,
            binding["candidateTag"],
        ),
        "candidateImage": binding,
        "runtime": {
            "projectName": config.project_name,
            "publishedAddress": controller.SIDECAR_ADDRESS,
            "publishedPort": controller.SIDECAR_PORT,
            "candidateImageId": binding["candidateImageId"],
            "candidateTag": binding["candidateTag"],
            "composePath": str(config.compose_file),
            "materializationReceipt": str(config.materialization_receipt),
            "runtimeAttestation": str(config.runtime_attestation),
            "environment": environment,
            "volumes": dict(config.volume_names),
            "application": application,
        },
    }


def test_no_runtime_receipt_skips_compose_only_after_exact_absence_proof(
    tmp_path: Path,
) -> None:
    config = cleanup_test_config(tmp_path)
    runner = FakeCleanupRunner()
    actions, recorded = concrete_cleanup_actions(
        config,
        runner,
        {
            "shelf": {"status": "pass"},
            "dataProtection": {"status": "pass"},
        },
    )

    receipt = actions.cleanup_sidecar_resources(config)

    assert runner.compose_calls == []
    assert receipt["composeDisposition"] == "not-created"
    assert receipt["preRuntimeAbsence"]["status"] == "pass"
    assert receipt["preRuntimeAbsence"]["containers"] == 0
    assert receipt["preRuntimeAbsence"]["networks"] == 0
    assert receipt["preRuntimeAbsence"]["labeledVolumes"] == 0
    assert receipt["preRuntimeAbsence"]["listeners"] == 0
    assert receipt["candidateImage"] == {"disposition": "not-bound"}
    assert recorded == [("cleaned", "cleanup", receipt)]
    assert not any(
        call[:2] in (["volume", "rm"], ["image", "rm"])
        for call in runner.docker_calls
    )


@pytest.mark.parametrize(
    "case",
    (
        "empty-receipt",
        "missing-environment",
        "empty-environment",
        "bad-value",
        "wrong-project",
        "missing-compose",
        "symlink-compose",
    ),
)
def test_present_but_corrupt_runtime_receipt_is_not_treated_as_absent(
    tmp_path: Path,
    case: str,
) -> None:
    config = cleanup_test_config(tmp_path)
    runtime: Any
    if case == "empty-receipt":
        runtime = {}
    elif case == "missing-environment":
        runtime = {"projectName": config.project_name}
    elif case == "empty-environment":
        runtime = {
            "projectName": config.project_name,
            "environment": {},
        }
    elif case == "bad-value":
        runtime = {
            "projectName": config.project_name,
            "environment": {"REQUIRED": 7},
        }
    elif case == "wrong-project":
        runtime = {
            "projectName": "chummer-public-download-wrong-project",
            "environment": {"REQUIRED": "present"},
        }
    else:
        runtime = {
            "projectName": config.project_name,
            "environment": {"REQUIRED": "present"},
        }
        config.compose_file.unlink()
        if case == "symlink-compose":
            target = tmp_path / "other-compose.json"
            target.write_text("{}\n", encoding="utf-8")
            config.compose_file.symlink_to(target)
    runner = FakeCleanupRunner()
    actions, recorded = concrete_cleanup_actions(
        config,
        runner,
        {"runtime": runtime},
    )

    with pytest.raises(controller.RecoveryUncertain):
        actions.cleanup_sidecar_resources(config)

    assert runner.compose_calls == []
    assert runner.docker_calls == []
    assert runner.run_calls == []
    assert recorded == []


def test_runtime_environment_injection_is_rejected_before_compose_or_delete(
    tmp_path: Path,
) -> None:
    config = cleanup_test_config(tmp_path)
    receipts = complete_runtime_receipts(
        config,
        environment_update={"DOCKER_HOST": "tcp://attacker.invalid:2375"},
    )
    runner = FakeCleanupRunner()
    actions, recorded = concrete_cleanup_actions(config, runner, receipts)

    with pytest.raises(
        controller.RecoveryUncertain,
        match="environment drifted",
    ):
        actions.cleanup_sidecar_resources(config)

    assert runner.compose_calls == []
    assert runner.docker_calls == []
    assert runner.run_calls == []
    assert recorded == []


def test_runtime_compose_byte_tamper_is_rejected_before_mutation(
    tmp_path: Path,
) -> None:
    config = cleanup_test_config(tmp_path)
    receipts = complete_runtime_receipts(config)
    config.compose_file.write_text('{"tampered":true}\n', encoding="utf-8")
    config.compose_file.chmod(0o600)
    runner = FakeCleanupRunner()
    actions, recorded = concrete_cleanup_actions(config, runner, receipts)

    with pytest.raises(
        controller.RecoveryUncertain,
        match="authority drifted",
    ):
        actions.cleanup_sidecar_resources(config)

    assert runner.compose_calls == []
    assert runner.docker_calls == []
    assert runner.run_calls == []
    assert recorded == []


def test_exact_runtime_authority_is_preflighted_before_compose_cleanup(
    tmp_path: Path,
) -> None:
    config = cleanup_test_config(tmp_path)
    image_id, tag, _binding = candidate_binding(config)
    runner = FakeCleanupRunner(
        image_id=image_id,
        tag=tag,
        project_candidate_containers=True,
        project_compose_file=str(config.compose_file),
        project_working_dir=str(config.operation_root),
        project_volume_names=list(config.volume_names.values()),
    )
    actions, recorded = concrete_cleanup_actions(
        config,
        runner,
        complete_runtime_receipts(config),
    )

    receipt = actions.cleanup_sidecar_resources(config)

    assert runner.compose_calls == [
        ["config", "--format", "json"],
        ["down", "--remove-orphans"],
    ]
    assert ["image", "rm", image_id] in runner.docker_calls
    assert receipt["composeDisposition"] == "removed"
    assert receipt["candidateImage"]["disposition"] == "removed"
    assert recorded[-1][0:2] == ("cleaned", "cleanup")
    down_index = runner.events.index(
        ("compose", ["down", "--remove-orphans"])
    )
    container_inventory_indices = [
        index
        for index, event in enumerate(runner.events)
        if event
        == (
            "docker",
            ["container", "ls", "--all", "--quiet", "--no-trunc"],
        )
    ]
    image_removal_index = runner.events.index(
        ("docker", ["image", "rm", image_id])
    )
    assert len(container_inventory_indices) == 2
    assert (
        container_inventory_indices[0]
        < down_index
        < container_inventory_indices[1]
        < image_removal_index
    )


def test_foreign_candidate_reference_blocks_runtime_cleanup_before_down(
    tmp_path: Path,
) -> None:
    config = cleanup_test_config(tmp_path)
    image_id, tag, _binding = candidate_binding(config)
    runner = FakeCleanupRunner(
        image_id=image_id,
        tag=tag,
        referencing_container=True,
        project_candidate_containers=True,
        project_compose_file=str(config.compose_file),
        project_working_dir=str(config.operation_root),
        project_volume_names=list(config.volume_names.values()),
    )
    actions, recorded = concrete_cleanup_actions(
        config,
        runner,
        complete_runtime_receipts(config),
    )

    with pytest.raises(
        controller.RecoveryUncertain,
        match="foreign or ambiguous container reference",
    ):
        actions.cleanup_sidecar_resources(config)

    assert runner.compose_calls == []
    assert ["image", "rm", image_id] not in runner.docker_calls
    assert recorded == []


@pytest.mark.parametrize(
    ("project_oneoff", "project_container_number"),
    (("True", "1"), ("False", "2")),
)
def test_noncanonical_project_container_blocks_cleanup_before_down(
    tmp_path: Path,
    project_oneoff: str,
    project_container_number: str,
) -> None:
    config = cleanup_test_config(tmp_path)
    image_id, tag, _binding = candidate_binding(config)
    runner = FakeCleanupRunner(
        image_id=image_id,
        tag=tag,
        project_candidate_containers=True,
        project_compose_file=str(config.compose_file),
        project_working_dir=str(config.operation_root),
        project_volume_names=list(config.volume_names.values()),
        project_oneoff=project_oneoff,
        project_container_number=project_container_number,
    )
    actions, recorded = concrete_cleanup_actions(
        config,
        runner,
        complete_runtime_receipts(config),
    )

    with pytest.raises(
        controller.RecoveryUncertain,
        match="foreign or ambiguous container reference",
    ):
        actions.cleanup_sidecar_resources(config)

    assert runner.compose_calls == []
    assert ["image", "rm", image_id] not in runner.docker_calls
    assert not any(
        call[:2] == ["volume", "rm"] for call in runner.docker_calls
    )
    assert recorded == []


def test_foreign_volume_reference_blocks_cleanup_before_down(
    tmp_path: Path,
) -> None:
    config = cleanup_test_config(tmp_path)
    image_id, tag, _binding = candidate_binding(config)
    runner = FakeCleanupRunner(
        image_id=image_id,
        tag=tag,
        referencing_container=True,
        project_candidate_containers=True,
        project_compose_file=str(config.compose_file),
        project_working_dir=str(config.operation_root),
        project_volume_names=list(config.volume_names.values()),
        foreign_image_id="sha256:" + "c" * 64,
        foreign_volume_name=config.volume_names["public-download-app"],
    )
    actions, recorded = concrete_cleanup_actions(
        config,
        runner,
        complete_runtime_receipts(config),
    )

    with pytest.raises(
        controller.RecoveryUncertain,
        match="foreign or ambiguous container reference",
    ):
        actions.cleanup_sidecar_resources(config)

    assert runner.compose_calls == []
    assert ["image", "rm", image_id] not in runner.docker_calls
    assert not any(
        call[:2] == ["volume", "rm"] for call in runner.docker_calls
    )
    assert recorded == []


def test_foreign_same_project_container_blocks_cleanup_before_down(
    tmp_path: Path,
) -> None:
    config = cleanup_test_config(tmp_path)
    image_id, tag, _binding = candidate_binding(config)
    runner = FakeCleanupRunner(
        image_id=image_id,
        tag=tag,
        referencing_container=True,
        project_candidate_containers=True,
        project_compose_file=str(config.compose_file),
        project_working_dir=str(config.operation_root),
        project_volume_names=list(config.volume_names.values()),
        foreign_image_id="sha256:" + "c" * 64,
        foreign_same_project=True,
    )
    actions, recorded = concrete_cleanup_actions(
        config,
        runner,
        complete_runtime_receipts(config),
    )

    with pytest.raises(
        controller.RecoveryUncertain,
        match="foreign or ambiguous container reference",
    ):
        actions.cleanup_sidecar_resources(config)

    assert runner.compose_calls == []
    assert ["image", "rm", image_id] not in runner.docker_calls
    assert not any(
        call[:2] == ["volume", "rm"] for call in runner.docker_calls
    )
    assert recorded == []


def test_foreign_project_network_blocks_cleanup_before_compose(
    tmp_path: Path,
) -> None:
    config = cleanup_test_config(tmp_path)
    image_id, tag, _binding = candidate_binding(config)
    runner = FakeCleanupRunner(
        blocker="networks",
        image_id=image_id,
        tag=tag,
    )
    actions, recorded = concrete_cleanup_actions(
        config,
        runner,
        complete_runtime_receipts(config),
    )

    with pytest.raises(
        controller.RecoveryUncertain,
        match="network deletion scope is not empty",
    ):
        actions.cleanup_sidecar_resources(config)

    assert runner.compose_calls == []
    assert ["image", "rm", image_id] not in runner.docker_calls
    assert not any(
        call[:2] == ["volume", "rm"] for call in runner.docker_calls
    )
    assert recorded == []


def test_candidate_reference_is_rechecked_after_compose_down(
    tmp_path: Path,
) -> None:
    config = cleanup_test_config(tmp_path)
    image_id, tag, _binding = candidate_binding(config)
    runner = FakeCleanupRunner(
        image_id=image_id,
        tag=tag,
        project_candidate_containers=True,
        retain_project_containers_after_down=True,
        project_compose_file=str(config.compose_file),
        project_working_dir=str(config.operation_root),
        project_volume_names=list(config.volume_names.values()),
    )
    actions, recorded = concrete_cleanup_actions(
        config,
        runner,
        complete_runtime_receipts(config),
    )

    with pytest.raises(
        controller.RecoveryUncertain,
        match="foreign or ambiguous container reference",
    ):
        actions.cleanup_sidecar_resources(config)

    assert runner.compose_calls == [
        ["config", "--format", "json"],
        ["down", "--remove-orphans"],
    ]
    assert ["image", "rm", image_id] not in runner.docker_calls
    assert not any(
        call[:2] == ["volume", "rm"] for call in runner.docker_calls
    )
    assert recorded == []


def test_volume_reference_is_rechecked_after_compose_down(
    tmp_path: Path,
) -> None:
    config = cleanup_test_config(tmp_path)
    image_id, tag, _binding = candidate_binding(config)
    runner = FakeCleanupRunner(
        image_id=image_id,
        tag=tag,
        project_candidate_containers=True,
        project_compose_file=str(config.compose_file),
        project_working_dir=str(config.operation_root),
        project_volume_names=list(config.volume_names.values()),
        post_down_foreign_volume_name=(
            config.volume_names["public-download-state"]
        ),
    )
    actions, recorded = concrete_cleanup_actions(
        config,
        runner,
        complete_runtime_receipts(config),
    )

    with pytest.raises(
        controller.RecoveryUncertain,
        match="foreign or ambiguous container reference",
    ):
        actions.cleanup_sidecar_resources(config)

    assert runner.compose_calls == [
        ["config", "--format", "json"],
        ["down", "--remove-orphans"],
    ]
    assert ["image", "rm", image_id] not in runner.docker_calls
    assert not any(
        call[:2] == ["volume", "rm"] for call in runner.docker_calls
    )
    assert recorded == []


def test_project_network_is_rechecked_after_compose_down(
    tmp_path: Path,
) -> None:
    config = cleanup_test_config(tmp_path)
    image_id, tag, _binding = candidate_binding(config)
    runner = FakeCleanupRunner(
        image_id=image_id,
        tag=tag,
        project_candidate_containers=True,
        project_compose_file=str(config.compose_file),
        project_working_dir=str(config.operation_root),
        project_volume_names=list(config.volume_names.values()),
        post_down_project_network=True,
    )
    actions, recorded = concrete_cleanup_actions(
        config,
        runner,
        complete_runtime_receipts(config),
    )

    with pytest.raises(
        controller.RecoveryUncertain,
        match="network deletion scope is not empty",
    ):
        actions.cleanup_sidecar_resources(config)

    assert runner.compose_calls == [
        ["config", "--format", "json"],
        ["down", "--remove-orphans"],
    ]
    assert ["image", "rm", image_id] not in runner.docker_calls
    assert not any(
        call[:2] == ["volume", "rm"] for call in runner.docker_calls
    )
    assert recorded == []


def test_volume_preflight_detects_late_ambiguity_before_any_volume_delete(
    tmp_path: Path,
) -> None:
    config = cleanup_test_config(tmp_path)
    first = config.volume_names["public-download-app"]
    second = config.volume_names["public-download-state"]
    runner = FakeCleanupRunner(
        volume_labels={
            first: {
                "run.chummer.public-download-operation": config.project_name,
                "run.chummer.public-download-logical-volume": (
                    "public-download-app"
                ),
            },
            second: {
                "run.chummer.public-download-operation": config.project_name,
                "run.chummer.public-download-logical-volume": "wrong-logical",
            },
        }
    )
    actions, recorded = concrete_cleanup_actions(
        config,
        runner,
        complete_runtime_receipts(config),
    )

    with pytest.raises(controller.RecoveryUncertain):
        actions.cleanup_sidecar_resources(config)

    assert runner.compose_calls == []
    assert not any(call[:2] == ["volume", "rm"] for call in runner.docker_calls)
    assert recorded == []


@pytest.mark.parametrize(
    "blocker",
    (
        "containers",
        "networks",
        "labeledVolumes",
        "exactVolume",
        "listener",
        "malformed",
        "probeFailure",
    ),
)
def test_no_runtime_cleanup_fails_closed_on_ambiguous_resources(
    tmp_path: Path,
    blocker: str,
) -> None:
    config = cleanup_test_config(tmp_path)
    runner = FakeCleanupRunner(blocker=blocker)
    actions, recorded = concrete_cleanup_actions(config, runner, {})

    with pytest.raises(controller.RecoveryUncertain):
        actions.cleanup_sidecar_resources(config)

    assert runner.compose_calls == []
    assert recorded == []
    assert not any(
        call[:2] in (["volume", "rm"], ["image", "rm"])
        for call in runner.docker_calls
    )


def test_cleanup_removes_only_exact_bound_unused_candidate_image(
    tmp_path: Path,
) -> None:
    config = cleanup_test_config(tmp_path)
    image_id, tag, binding = candidate_binding(config)
    runner = FakeCleanupRunner(image_id=image_id, tag=tag)
    actions, _recorded = concrete_cleanup_actions(
        config,
        runner,
        {
            "candidateImagePlan": candidate_plan(config, tag),
            "candidateImage": binding,
        },
    )

    receipt = actions.cleanup_sidecar_resources(config)

    assert receipt["candidateImage"] == {
        "disposition": "removed",
        "candidateTag": tag,
        "candidateImageId": image_id,
    }
    assert ["image", "rm", image_id] in runner.docker_calls
    assert runner.compose_calls == []


def test_bound_untagged_image_cleanup_retries_by_exact_id(
    tmp_path: Path,
) -> None:
    config = cleanup_test_config(tmp_path)
    image_id, tag, binding = candidate_binding(config)
    runner = FakeCleanupRunner(image_id=image_id, tag=tag)
    runner.tag_present = False
    actions, _recorded = concrete_cleanup_actions(
        config,
        runner,
        {
            "candidateImagePlan": candidate_plan(config, tag),
            "candidateImage": binding,
        },
    )

    receipt = actions.cleanup_sidecar_resources(config)

    assert receipt["candidateImage"]["disposition"] == "removed"
    assert ["image", "rm", image_id] in runner.docker_calls


@pytest.mark.parametrize(
    "tamper",
    ("missing-plan", "source-head", "context-digest"),
)
def test_bound_candidate_plan_tamper_blocks_cleanup_before_mutation(
    tmp_path: Path,
    tamper: str,
) -> None:
    config = cleanup_test_config(tmp_path)
    image_id, tag, _binding = candidate_binding(config)
    receipts = complete_runtime_receipts(config)
    plan = receipts.get("candidateImagePlan")
    assert isinstance(plan, dict)
    if tamper == "missing-plan":
        del receipts["candidateImagePlan"]
    elif tamper == "source-head":
        plan["sourceHead"] = "f" * 40
    else:
        plan["immutableBuildContextDigests"]["default"] = "9" * 64
    runner = FakeCleanupRunner(image_id=image_id, tag=tag)
    actions, recorded = concrete_cleanup_actions(config, runner, receipts)

    with pytest.raises(controller.RecoveryUncertain):
        actions.cleanup_sidecar_resources(config)

    assert runner.compose_calls == []
    assert ["image", "rm", image_id] not in runner.docker_calls
    assert not any(
        call[:2] == ["volume", "rm"] for call in runner.docker_calls
    )
    assert recorded == []


def test_planned_image_is_validated_bound_and_removed_after_build_crash(
    tmp_path: Path,
) -> None:
    config = cleanup_test_config(tmp_path)
    image_id, tag, _binding = candidate_binding(config)
    runner = FakeCleanupRunner(image_id=image_id, tag=tag)
    actions, recorded = concrete_cleanup_actions(
        config,
        runner,
        {"candidateImagePlan": candidate_plan(config, tag)},
    )

    receipt = actions.cleanup_sidecar_resources(config)

    assert receipt["candidateImage"]["disposition"] == "removed"
    assert ["image", "rm", image_id] in runner.docker_calls
    assert recorded[0][0:2] == (
        "candidate-image-recovered",
        "candidateImage",
    )
    assert recorded[-1][0:2] == ("cleaned", "cleanup")


@pytest.mark.parametrize(
    "ambiguity",
    ("tag-drift", "container", "extra-tag", "repo-digest"),
)
def test_candidate_image_cleanup_fails_closed_on_identity_ambiguity(
    tmp_path: Path,
    ambiguity: str,
) -> None:
    config = cleanup_test_config(tmp_path)
    image_id, tag, binding = candidate_binding(config)
    runner = FakeCleanupRunner(
        image_id=image_id,
        tag=tag,
        tag_image_id=(
            "sha256:" + "c" * 64 if ambiguity == "tag-drift" else image_id
        ),
        referencing_container=ambiguity == "container",
        repo_tags=(
            [tag, "chummer-run-api:unexpected-alias"]
            if ambiguity == "extra-tag"
            else None
        ),
        repo_digests=(
            ["registry.invalid/chummer@sha256:" + "d" * 64]
            if ambiguity == "repo-digest"
            else None
        ),
    )
    actions, recorded = concrete_cleanup_actions(
        config,
        runner,
        {
            "candidateImagePlan": candidate_plan(config, tag),
            "candidateImage": binding,
        },
    )

    with pytest.raises(controller.RecoveryUncertain):
        actions.cleanup_sidecar_resources(config)

    assert ["image", "rm", image_id] not in runner.docker_calls
    assert recorded == []


def test_candidate_preflight_precedes_compose_and_volume_deletion(
    tmp_path: Path,
) -> None:
    config = cleanup_test_config(tmp_path)
    image_id, tag, _binding = candidate_binding(config)
    logical = "public-download-app"
    volume = config.volume_names[logical]
    runner = FakeCleanupRunner(
        image_id=image_id,
        tag=tag,
        tag_image_id="sha256:" + "c" * 64,
        volume_labels={
            volume: {
                "run.chummer.public-download-operation": config.project_name,
                "run.chummer.public-download-logical-volume": logical,
            }
        },
    )
    actions, recorded = concrete_cleanup_actions(
        config,
        runner,
        complete_runtime_receipts(config),
    )

    with pytest.raises(controller.RecoveryUncertain):
        actions.cleanup_sidecar_resources(config)

    assert runner.compose_calls == []
    assert not any(call[:2] == ["volume", "rm"] for call in runner.docker_calls)
    assert recorded == []


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

    assert len(actions.primary_failures) == 1
    assert actions.events[-1] == "cleanup_sidecar"
    assert "cloudflare_rollback" not in actions.events
    assert (
        "probe_incumbent_after-rollback_chummer.run,www.chummer.run"
        not in actions.events
    )
    assert config.canonical_shelf_sentinel.read_bytes() == canonical_before


def test_cleanup_failure_does_not_discard_primary_failure(
    tmp_path: Path,
) -> None:
    require_topology_b_surface()
    config = topology_b_config(tmp_path)
    actions = RecordingActions(fail_at="materialize_compose")

    def fail_cleanup(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("forced cleanup failure")

    actions.cleanup_sidecar_resources = fail_cleanup  # type: ignore[method-assign]

    with pytest.raises(
        controller.RecoveryUncertain,
        match="primary failure evidence was retained",
    ):
        controller.execute_topology_b(config, actions=actions)

    assert len(actions.primary_failures) == 1
    assert "materialize_compose" in str(actions.primary_failures[0])


def test_primary_failure_write_failure_stops_before_cleanup(
    tmp_path: Path,
) -> None:
    require_topology_b_surface()
    config = topology_b_config(tmp_path)
    actions = RecordingActions(fail_at="materialize_compose")

    def fail_failure_receipt(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise OSError("simulated journal write failure")

    actions.record_primary_failure = fail_failure_receipt  # type: ignore[method-assign]

    with pytest.raises(
        controller.RecoveryUncertain,
        match="primary failure evidence could not be retained",
    ):
        controller.execute_topology_b(config, actions=actions)

    assert "cleanup_sidecar" not in actions.events


def test_post_apply_evidence_failure_does_not_preempt_exact_recovery(
    tmp_path: Path,
) -> None:
    require_topology_b_surface()
    config = topology_b_config(tmp_path)
    actions = RecordingActions(
        fail_at="probe_public_chummer.run,www.chummer.run"
    )

    def fail_failure_receipt(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        actions.events.append("primary_failure_write")
        raise OSError("simulated journal write failure")

    actions.record_primary_failure = fail_failure_receipt  # type: ignore[method-assign]

    with pytest.raises(
        controller.RecoveryUncertain,
        match="after exact rollback and cleanup",
    ):
        controller.execute_topology_b(config, actions=actions)

    assert actions.events[-4:] == [
        "cloudflare_rollback",
        "probe_incumbent_after-rollback_chummer.run,www.chummer.run",
        "primary_failure_write",
        "cleanup_sidecar",
    ]


def test_rollback_uncertainty_is_not_masked_by_evidence_failure(
    tmp_path: Path,
) -> None:
    require_topology_b_surface()
    config = topology_b_config(tmp_path)
    actions = RecordingActions(
        fail_at="probe_public_chummer.run,www.chummer.run"
    )
    original_record = actions.record

    def fail_rollback(event: str, result: Any = None) -> Any:
        if event == "cloudflare_rollback":
            actions.events.append(event)
            raise RuntimeError("rollback uncertain")
        return original_record(event, result)

    def fail_failure_receipt(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        actions.events.append("primary_failure_write")
        raise OSError("simulated journal write failure")

    actions.record = fail_rollback  # type: ignore[method-assign]
    actions.record_primary_failure = fail_failure_receipt  # type: ignore[method-assign]

    with pytest.raises(
        controller.RecoveryUncertain,
        match="rollback or incumbent verification is uncertain",
    ):
        controller.execute_topology_b(config, actions=actions)

    assert actions.events[-2:] == [
        "cloudflare_rollback",
        "primary_failure_write",
    ]
    assert "cleanup_sidecar" not in actions.events


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
        artifact_id="mac",
        route_kind="stable",
        expected_sha256=hashlib.sha256(
            b"protected-mac-installer"
        ).hexdigest(),
        expected_size_bytes=len(b"protected-mac-installer"),
    )

    assert receipt["httpStatus"] == 302
    assert receipt["artifactBytesServed"] is False
    assert receipt["bodyDiffersFromProtectedBytes"] is True
    assert receipt["routeKind"] == "stable"
    assert receipt["redirectsFollowed"] == 0
    assert len(connection.requests) == 1
    assert {
        "authorization",
        "cookie",
        "proxy-authorization",
    }.isdisjoint(
        key.lower() for key in connection.requests[0][2]
    )


def test_account_required_generation_denial_requires_exact_409_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    require_topology_b_surface()
    response = FakeProbeResponse(
        json.dumps(
            {
                "error": "generation_bound_credential_required",
                "message": (
                    "This retained release generation requires its "
                    "generation-bound install ticket or claim code. "
                    "Use the install command issued for this exact release."
                ),
            }
        ).encode(),
        status=409,
        headers=[("Content-Type", "application/json; charset=utf-8")],
    )
    connection = FakeProbeConnection(response)
    monkeypatch.setattr(
        controller,
        "_open_probe_connection",
        lambda **_kwargs: connection,
    )

    receipt = controller._probe_denied_download(
        scheme="http",
        connect_host=controller.SIDECAR_ADDRESS,
        connect_port=controller.SIDECAR_PORT,
        request_host="www.chummer.run",
        path=(
            "/downloads/g/generation-a/files/"
            "chummer-avalonia-osx-x64-installer.dmg"
        ),
        generation_id="generation-a",
        artifact_id="mac",
        route_kind="generation",
        expected_sha256=hashlib.sha256(
            b"protected-mac-installer"
        ).hexdigest(),
        expected_size_bytes=len(b"protected-mac-installer"),
    )

    assert receipt["httpStatus"] == 409
    assert receipt["routeKind"] == "generation"
    assert receipt["artifactBytesServed"] is False
    assert receipt["bodyDiffersFromProtectedBytes"] is True


@pytest.mark.parametrize(
    "route_kind,status,body,headers",
    [
        ("stable", 404, b"", []),
        (
            "stable",
            302,
            b"",
            [
                ("Location", "/login?next=%2Fdownloads%2Finstall%2Fmac"),
                ("Set-Cookie", "session=secret"),
            ],
        ),
        (
            "stable",
            302,
            b"",
            [
                (
                    "Location",
                    "https://www.chummer.run/login"
                    "?next=%2Fdownloads%2Finstall%2Fmac",
                )
            ],
        ),
        (
            "stable",
            302,
            b"protected-mac-installer",
            [("Location", "/login?next=%2Fdownloads%2Finstall%2Fmac")],
        ),
        (
            "stable",
            302,
            b"protected-prefix",
            [("Location", "/login?next=%2Fdownloads%2Finstall%2Fmac")],
        ),
        (
            "generation",
            302,
            b"",
            [("Location", "/login?next=%2Fdownloads%2Finstall%2Fmac")],
        ),
        (
            "generation",
            409,
            b'{"error":"wrong"}',
            [("Content-Type", "application/json")],
        ),
        (
            "generation",
            409,
            json.dumps(
                {
                    "error": "generation_bound_credential_required",
                    "message": (
                        "This retained release generation requires its "
                        "generation-bound install ticket or claim code. "
                        "Use the install command issued for this exact release."
                    ),
                    "leakedPrefix": "protected-prefix",
                }
            ).encode(),
            [("Content-Type", "application/json")],
        ),
    ],
)
def test_account_required_denial_probe_rejects_contract_drift_or_exact_bytes(
    monkeypatch: pytest.MonkeyPatch,
    route_kind: str,
    status: int,
    body: bytes,
    headers: list[tuple[str, str]],
) -> None:
    require_topology_b_surface()
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
        controller._probe_denied_download(
            scheme="https",
            connect_host="chummer.run",
            connect_port=443,
            request_host="chummer.run",
            path=(
                "/downloads/files/"
                "chummer-avalonia-osx-x64-installer.dmg"
                if route_kind == "stable"
                else (
                    "/downloads/g/generation-a/files/"
                    "chummer-avalonia-osx-x64-installer.dmg"
                )
            ),
            generation_id="generation-a",
            artifact_id="mac",
            route_kind=route_kind,
            expected_sha256=hashlib.sha256(
                b"protected-mac-installer"
            ).hexdigest(),
            expected_size_bytes=len(b"protected-mac-installer"),
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
    generation_files = generation_root / "files"
    generation_files.mkdir()
    private_payload_name = "chummer-avalonia-osx-x64-payload.zip"
    private_sidecar = b'{"contractName":"private-mac-payload"}\n'
    (generation_files / f"{private_payload_name}.json").write_bytes(
        private_sidecar
    )
    mac_files = {
        "avalonia-osx-x64-installer": (
            "chummer-avalonia-osx-x64-installer.dmg",
            "d",
        ),
        "blazor-desktop-osx-arm64-installer": (
            "chummer-blazor-desktop-osx-arm64-installer.dmg",
            "e",
        ),
    }
    (generation_root / "RELEASE_CHANNEL.generated.json").write_text(
        json.dumps(
            {
                "artifacts": [
                    {
                        "artifactId": artifact_id,
                        "platform": "macos",
                        "rid": (
                            "osx-arm64"
                            if "arm64" in artifact_id
                            else "osx-x64"
                        ),
                        "fileName": mac_file,
                        "downloadUrl": f"/downloads/files/{mac_file}",
                        "sha256": character * 64,
                        "sizeBytes": index + 101,
                        "installAccessClass": "account_required",
                        **(
                            {
                                "payloadFileName": private_payload_name,
                                "payloadDownloadUrl": (
                                    "/downloads/files/"
                                    f"{private_payload_name}"
                                ),
                                "payloadSha256": "f" * 64,
                                "payloadSizeBytes": 303,
                            }
                            if artifact_id
                            == "avalonia-osx-x64-installer"
                            else {}
                        ),
                    }
                    for index, (
                        artifact_id,
                        (mac_file, character),
                    ) in enumerate(mac_files.items())
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
            "httpStatus": (
                302 if kwargs["route_kind"] == "stable" else 409
            ),
            "anonymous": True,
            "artifactBytesServed": False,
            "bodyDiffersFromProtectedBytes": True,
            "routeKind": kwargs["route_kind"],
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
    assert len(receipt["freshArtifacts"]) == 12
    assert len(receipt["accountRequiredDenials"]) == 16
    assert {call["request_host"] for call in streamed} == set(HOSTS)
    assert {call["connect_host"] for call in streamed} == connect_hosts
    assert {call["scheme"] for call in streamed} == {scheme}
    assert {call["path"] for call in streamed} == {
        candidate
        for path in fresh_paths
        for candidate in (
            f"/downloads/{path}",
            (
                f"/downloads/g/{generation_id}/files/"
                f"{Path(path).name}"
            ),
        )
    }
    private_file_names = {
        *(mac_file for mac_file, _character in mac_files.values()),
        private_payload_name,
        f"{private_payload_name}.json",
    }
    assert {call["path"] for call in denied} == {
        candidate
        for file_name in private_file_names
        for candidate in (
            f"/downloads/files/{file_name}",
            f"/downloads/g/{generation_id}/files/{file_name}",
        )
    }
    assert {
        call["artifact_id"] for call in denied
    } == set(mac_files)
    assert {
        call["route_kind"] for call in denied
    } == {"stable", "generation"}
    assert {
        (
            call["expected_sha256"],
            call["expected_size_bytes"],
        )
        for call in denied
        if call["path"].endswith(
            f"{private_payload_name}.json"
        )
    } == {
        (
            hashlib.sha256(private_sidecar).hexdigest(),
            len(private_sidecar),
        )
    }
    assert {
        observation["role"]
        for observation in receipt["accountRequiredDenials"]
    } == {"primary", "payload", "sidecar"}
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
    def __init__(
        self,
        *,
        fail_first_request: bool = False,
        fail_lifetime_check: bool = False,
    ) -> None:
        self.fail_first_request = fail_first_request
        self.fail_lifetime_check = fail_lifetime_check
        self.calls: list[str] = []
        self.commands: list[list[str]] = []

    def run(self, command: list[str], **kwargs: Any) -> bytes:
        operation = command[1]
        self.calls.append(operation)
        self.commands.append(list(command))
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
            if "-clcerts" in command and "-nokeys" in command:
                certificate = Path(command[command.index("-in") + 1])
                password_argument = command[command.index("-passin") + 1]
                password = Path(
                    password_argument.removeprefix("file:")
                ).read_bytes()
                if certificate.read_bytes() != b"fake-pkcs12:" + password:
                    raise controller.CutoverError("invalid fake PKCS#12")
                return b"fake-public-certificate"
            password_argument = command[command.index("-passout") + 1]
            assert password_argument.startswith("file:")
            password = Path(password_argument.removeprefix("file:")).read_bytes()
            Path(command[command.index("-out") + 1]).write_bytes(
                b"fake-pkcs12:" + password
            )
            return b""
        if operation == "x509":
            assert kwargs["input_bytes"] == b"fake-public-certificate"
            if self.fail_lifetime_check:
                raise controller.CutoverError(
                    "simulated certificate lifetime failure"
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
    certificate_request = next(
        command for command in runner.commands if command[1] == "req"
    )
    assert certificate_request[
        certificate_request.index("-days") + 1
    ] == str(controller.SIDECAR_CERTIFICATE_VALIDITY_DAYS)
    assert controller.SIDECAR_CERTIFICATE_VALIDITY_DAYS == 30
    certificate_lifetime_check = next(
        command for command in runner.commands if command[1] == "x509"
    )
    assert certificate_lifetime_check[
        certificate_lifetime_check.index("-checkend") + 1
    ] == str(controller.SIDECAR_CERTIFICATE_MINIMUM_REMAINING_SECONDS)
    assert (
        controller.SIDECAR_CERTIFICATE_MINIMUM_REMAINING_SECONDS
        == 7 * 24 * 60 * 60
    )
    assert "fake-public-certificate" not in " ".join(
        certificate_lifetime_check
    )
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


def test_data_protection_replay_rejects_near_expiry_certificate(
    tmp_path: Path,
) -> None:
    operation_root = tmp_path / "chummer-public-download-dp-near-expiry"
    operation_root.mkdir(mode=0o700)
    certificate = operation_root / "sidecar-data-protection.pfx"
    password = operation_root / "sidecar-data-protection.password"
    password_bytes = b"known-password\n"
    certificate.write_bytes(b"fake-pkcs12:" + password_bytes)
    password.write_bytes(password_bytes)
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
            FakeDataProtectionRunner(fail_lifetime_check=True),
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
