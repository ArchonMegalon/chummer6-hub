from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
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
            "retire_topology_b",
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


def test_playwright_browser_authority_accepts_stable_private_cache_link(
    tmp_path: Path,
) -> None:
    cache_parent = tmp_path / "cache"
    cache_parent.mkdir()
    target = tmp_path / "private-browser-cache"
    target.mkdir(mode=0o700)
    source = cache_parent / "ms-playwright"
    source.symlink_to(target)

    assert controller.resolve_playwright_browser_authority_root(source) == target


def test_playwright_browser_authority_rejects_nonprivate_link_target(
    tmp_path: Path,
) -> None:
    cache_parent = tmp_path / "cache"
    cache_parent.mkdir()
    target = tmp_path / "public-browser-cache"
    target.mkdir(mode=0o755)
    target.chmod(0o755)
    source = cache_parent / "ms-playwright"
    source.symlink_to(target)

    with pytest.raises(controller.CutoverError, match="private directory is unsafe"):
        controller.resolve_playwright_browser_authority_root(source)


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


def local_generation_probe(
    generation_id: str,
    *,
    chummer_sha256: str = "b" * 64,
    www_sha256: str = "b" * 64,
) -> dict[str, Any]:
    observations: list[dict[str, Any]] = []
    for hostname, body_sha256 in (
        ("chummer.run", chummer_sha256),
        ("www.chummer.run", www_sha256),
    ):
        observations.append(
            {
                "endpoint": (
                    f"http://{hostname}/downloads/g/{generation_id}/"
                    "releases.json"
                ),
                "httpStatus": 200,
                "bodySha256": body_sha256,
                "sizeBytes": 1234,
                "generationId": generation_id,
                "anonymous": True,
            }
        )
    return {
        "status": "pass",
        "origin": controller.SIDECAR_ORIGIN,
        "hosts": list(controller.SIDECAR_HOSTS),
        "generationId": generation_id,
        "observations": observations,
        "artifactVerification": {"status": "pass"},
    }


def test_local_served_manifest_digest_requires_exact_two_host_closure() -> None:
    generation_id = "generation-a"
    local_probe = local_generation_probe(generation_id)

    assert controller._local_served_generation_manifest_sha256(
        local_probe,
        generation_id=generation_id,
    ) == "b" * 64

    divergent = local_generation_probe(
        generation_id,
        www_sha256="c" * 64,
    )
    with pytest.raises(
        controller.CutoverError,
        match="body digest diverged by host",
    ):
        controller._local_served_generation_manifest_sha256(
            divergent,
            generation_id=generation_id,
        )

    incomplete = local_generation_probe(generation_id)
    incomplete["observations"].pop()
    with pytest.raises(
        controller.CutoverError,
        match="host closure is incomplete",
    ):
        controller._local_served_generation_manifest_sha256(
            incomplete,
            generation_id=generation_id,
        )


def test_capture_cloudflare_binds_recorded_local_served_manifest_digest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generation_id = "generation-a"
    local_probe = local_generation_probe(generation_id)
    release_authority = {
        "contractName": "candidate-authority",
        "validatedAtUtc": "2026-07-24T20:00:00Z",
    }
    shelf = {
        "generationId": generation_id,
        "releaseCandidateAuthority": release_authority,
    }
    config = SimpleNamespace(
        cloudflare_account_id="account-a",
        cloudflare_tunnel_id="tunnel-a",
        cloudflare_journal=Path("/tmp/cloudflare-journal"),
        cloudflare_lock=Path("/tmp/cloudflare-lock"),
    )
    captured: dict[str, Any] = {}

    class FakeCloudflare:
        def capture_transaction(self, _api: Any, **kwargs: Any) -> dict[str, Any]:
            captured.update(kwargs)
            return {
                "phase": "captured",
                "priorConfigSha256": "1" * 64,
                "priorVersion": 5,
                "targetConfigSha256": "2" * 64,
            }

    actions = object.__new__(controller.TopologyBActions)
    actions.config = config
    actions.cloudflare = FakeCloudflare()
    actions.projection_verifier = object()
    actions.candidate_materializer = object()
    actions._state = {"receipts": {"localProbe": local_probe}}
    actions._record = lambda *_args, **_kwargs: None
    actions._cloudflare_api = lambda: object()
    monkeypatch.setattr(
        controller,
        "validate_release_candidate_authority",
        lambda *_args, **_kwargs: release_authority,
    )

    actions.capture_cloudflare(
        config,
        shelf,
        {},
        {},
        local_probe,
        {},
    )

    assert captured["probe_body_sha256"] == "b" * 64
    assert captured["probe_body_sha256"] != hashlib.sha256(
        b"prepared unwrapped manifest"
    ).hexdigest()

    drifted = local_generation_probe(generation_id)
    drifted["observations"][0]["bodySha256"] = "c" * 64
    with pytest.raises(
        controller.CutoverError,
        match="local generation probe changed",
    ):
        actions.capture_cloudflare(
            config,
            shelf,
            {},
            {},
            drifted,
            {},
        )


def test_successor_capture_requires_exact_authorized_cloudflare_transition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generation_id = "g-successor-capture"
    local_probe = local_generation_probe(generation_id)
    prior_config = {"ingress": [{"service": "http_status:404"}]}
    target_config = {
        "ingress": [
            {
                "hostname": "chummer.run",
                "service": controller.SIDECAR_ORIGIN,
            },
            {"service": "http_status:404"},
        ]
    }
    successor = {
        "generationId": generation_id,
        "priorConfig": prior_config,
        "priorConfigSha256": "1" * 64,
        "priorVersion": 5,
        "targetConfig": target_config,
        "targetConfigSha256": "2" * 64,
    }
    release_authority = {
        "contractName": "candidate-authority",
        "validatedAtUtc": "2026-07-24T20:00:00Z",
        "successorCutoverAuthority": successor,
    }
    shelf = {
        "generationId": generation_id,
        "releaseCandidateAuthority": release_authority,
    }
    config = SimpleNamespace(
        cloudflare_account_id="account-a",
        cloudflare_tunnel_id="tunnel-a",
        cloudflare_journal=Path("/tmp/cloudflare-journal"),
        cloudflare_lock=Path("/tmp/cloudflare-lock"),
    )

    class FakeCloudflare:
        mismatch = False

        def capture_transaction(
            self,
            _api: Any,
            **_kwargs: Any,
        ) -> dict[str, Any]:
            return {
                "phase": "captured",
                "priorConfig": prior_config,
                "priorConfigSha256": "1" * 64,
                "priorVersion": 5,
                "targetConfig": target_config,
                "targetConfigSha256": (
                    "3" * 64 if self.mismatch else "2" * 64
                ),
                "generationId": generation_id,
                "origin": controller.SIDECAR_ORIGIN,
                "accountId": "account-a",
                "tunnelId": "tunnel-a",
            }

    actions = object.__new__(controller.TopologyBActions)
    actions.config = config
    actions.cloudflare = FakeCloudflare()
    actions.projection_verifier = object()
    actions.candidate_materializer = object()
    actions._state = {"receipts": {"localProbe": local_probe}}
    actions._record = lambda *_args, **_kwargs: None
    actions._cloudflare_api = lambda: object()
    monkeypatch.setattr(
        controller,
        "validate_release_candidate_authority",
        lambda *_args, **_kwargs: release_authority,
    )

    actions.capture_cloudflare(
        config,
        shelf,
        {},
        {},
        local_probe,
        {},
    )

    actions.cloudflare.mismatch = True
    with pytest.raises(
        controller.CutoverError,
        match="one-use successor authority",
    ):
        actions.capture_cloudflare(
            config,
            shelf,
            {},
            {},
            local_probe,
            {},
        )


def test_public_generation_convergence_retries_only_positive_manifest_probe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generation_id = "generation-a"
    expected_body_sha256 = "b" * 64
    generation_root = tmp_path / generation_id
    generation_root.mkdir()
    (generation_root / "releases.json").write_text(
        '{"generationId":"generation-a"}\n',
        encoding="utf-8",
    )
    config = SimpleNamespace(
        cloudflare_journal=tmp_path / "cloudflare-journal.json",
        ready_timeout_seconds=5,
    )

    class FakeCloudflare:
        @staticmethod
        def load_journal(_path: Path) -> dict[str, Any]:
            return {
                "generationId": generation_id,
                "probeBodySha256": expected_body_sha256,
            }

    actions = object.__new__(controller.TopologyBActions)
    actions.config = config
    actions.cloudflare = FakeCloudflare()
    calls: list[str] = []

    def probe(**kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs["request_host"])
        if len(calls) == 1:
            raise controller.CutoverError("incumbent still served")
        return {
            "endpoint": (
                f"https://{kwargs['request_host']}{kwargs['path']}"
            ),
            "httpStatus": 200,
            "bodySha256": expected_body_sha256,
            "sizeBytes": 1234,
            "generationId": generation_id,
            "anonymous": True,
        }

    monkeypatch.setattr(controller, "_probe_exact_manifest", probe)
    now = [0.0]
    sleeps: list[float] = []

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        now[0] += seconds

    observations = actions._wait_for_public_generation_convergence(
        {
            "generationId": generation_id,
            "generationRoot": str(generation_root),
        },
        sleep_fn=sleep,
        monotonic_fn=lambda: now[0],
        interval_seconds=2,
    )

    assert calls == ["chummer.run", "chummer.run", "www.chummer.run"]
    assert sleeps == [2]
    assert [row["bodySha256"] for row in observations] == [
        expected_body_sha256,
        expected_body_sha256,
    ]


def test_public_generation_convergence_timeout_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generation_id = "generation-a"
    generation_root = tmp_path / generation_id
    generation_root.mkdir()
    (generation_root / "releases.json").write_text(
        '{"generationId":"generation-a"}\n',
        encoding="utf-8",
    )
    config = SimpleNamespace(
        cloudflare_journal=tmp_path / "cloudflare-journal.json",
        ready_timeout_seconds=3,
    )

    class FakeCloudflare:
        @staticmethod
        def load_journal(_path: Path) -> dict[str, Any]:
            return {
                "generationId": generation_id,
                "probeBodySha256": "b" * 64,
            }

    actions = object.__new__(controller.TopologyBActions)
    actions.config = config
    actions.cloudflare = FakeCloudflare()
    attempts = [0]

    def never_converges(**_kwargs: Any) -> dict[str, Any]:
        attempts[0] += 1
        raise controller.CutoverError("incumbent still served")

    monkeypatch.setattr(
        controller,
        "_probe_exact_manifest",
        never_converges,
    )
    now = [0.0]
    sleeps: list[float] = []

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        now[0] += seconds

    with pytest.raises(
        controller.CutoverError,
        match="did not converge before timeout",
    ):
        actions._wait_for_public_generation_convergence(
            {
                "generationId": generation_id,
                "generationRoot": str(generation_root),
            },
            sleep_fn=sleep,
            monotonic_fn=lambda: now[0],
            interval_seconds=2,
        )

    assert attempts[0] == 2
    assert sleeps == [2, 1]


def test_public_generation_convergence_rejects_success_after_deadline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generation_id = "generation-a"
    generation_root = tmp_path / generation_id
    generation_root.mkdir()
    (generation_root / "releases.json").write_text(
        '{"generationId":"generation-a"}\n',
        encoding="utf-8",
    )
    config = SimpleNamespace(
        cloudflare_journal=tmp_path / "cloudflare-journal.json",
        ready_timeout_seconds=5,
    )

    class FakeCloudflare:
        @staticmethod
        def load_journal(_path: Path) -> dict[str, Any]:
            return {
                "generationId": generation_id,
                "probeBodySha256": "b" * 64,
            }

    actions = object.__new__(controller.TopologyBActions)
    actions.config = config
    actions.cloudflare = FakeCloudflare()
    now = [0.0]

    def late_success(**kwargs: Any) -> dict[str, Any]:
        now[0] = 6.0
        return {
            "endpoint": (
                f"https://{kwargs['request_host']}{kwargs['path']}"
            ),
            "httpStatus": 200,
            "bodySha256": "b" * 64,
            "sizeBytes": 1234,
            "generationId": generation_id,
            "anonymous": True,
        }

    monkeypatch.setattr(controller, "_probe_exact_manifest", late_success)

    with pytest.raises(
        controller.CutoverError,
        match="did not converge before timeout",
    ):
        actions._wait_for_public_generation_convergence(
            {
                "generationId": generation_id,
                "generationRoot": str(generation_root),
            },
            sleep_fn=lambda _seconds: None,
            monotonic_fn=lambda: now[0],
            interval_seconds=2,
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
    successor_authority = document(
        tmp_path / "successor-authority.json"
    )
    decision_artifact = document(
        tmp_path / "successor-decision.zip"
    )
    predecessor_retirement = document(
        tmp_path / "predecessor-retirement.json"
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
            "--successor-cutover-authority",
            str(successor_authority),
            "--successor-cutover-authority-sha256",
            "d" * 64,
            "--operator-decision-artifact",
            str(decision_artifact),
            "--operator-decision-artifact-sha256",
            "e" * 64,
            "--operator-decision-artifact-id",
            "123456",
            "--predecessor-retirement-receipt",
            str(predecessor_retirement),
            "--predecessor-retirement-receipt-sha256",
            "f" * 64,
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
            "--projection-authority-root",
            str(projection_root.parent),
            "--projection-current-sha256",
            "c" * 64,
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
    assert config.successor_cutover_authority == successor_authority
    assert config.successor_cutover_authority_sha256 == "d" * 64
    assert config.operator_decision_artifact == decision_artifact
    assert config.operator_decision_artifact_sha256 == "e" * 64
    assert config.operator_decision_artifact_id == 123456
    assert (
        config.predecessor_retirement_receipt
        == predecessor_retirement
    )
    assert config.predecessor_retirement_receipt_sha256 == "f" * 64
    assert config.direct_import_receipt == direct_import
    assert config.direct_import_receipt_sha256 == direct_import_sha256
    assert config.projection_snapshot_sha256 == semantic_sha256
    assert config.projection_source_tree_sha256 == tree_sha256
    assert config.projection_authority_root == projection_root.parent
    assert config.projection_current_sha256 == "c" * 64
    assert semantic_sha256 != tree_sha256

    wrapper = (
        ROOT / "scripts" / "deploy_public_edge_portal.sh"
    ).read_text(encoding="utf-8")
    for flag in (
        "--release-candidate-root",
        "--candidate-import-authority",
        "--candidate-import-authority-sha256",
        "--successor-cutover-authority",
        "--successor-cutover-authority-sha256",
        "--operator-decision-artifact",
        "--operator-decision-artifact-sha256",
        "--operator-decision-artifact-id",
        "--predecessor-retirement-receipt",
        "--predecessor-retirement-receipt-sha256",
        "--direct-import-receipt",
        "--direct-import-receipt-sha256",
        "--projection-snapshot-sha256",
        "--projection-snapshot-tree-sha256",
        "--projection-authority-root",
        "--projection-current-sha256",
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
        assert phase in {
            "before-cloudflare",
            "after-rollback",
            "after-retirement",
        }
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

    def authorize_committed_retirement(
        self, _config: Any, *_args: Any
    ) -> dict[str, Any]:
        return self.record("authorize_committed_retirement")

    def verify_canonical_incumbent_before_retirement(
        self, _config: Any, *_args: Any
    ) -> dict[str, Any]:
        return self.record(
            "verify_canonical_incumbent_before_retirement"
        )

    def restore_committed_prior(
        self, _config: Any, *_args: Any
    ) -> dict[str, Any]:
        return self.record("restore_committed_prior")

    def commit_retirement_evidence(
        self, _config: Any, *_args: Any
    ) -> dict[str, Any]:
        return self.record("commit_retirement_evidence")

    def retire_active_authority(
        self, _config: Any, *_args: Any
    ) -> dict[str, Any]:
        return self.record("retire_active_authority")

    def verify_retired_authority_connectors(
        self, _config: Any, *_args: Any
    ) -> dict[str, Any]:
        return self.record("verify_retired_authority_connectors")

    def finalize_committed_retirement(
        self, _config: Any, *_args: Any
    ) -> dict[str, Any]:
        return self.record("finalize_committed_retirement")


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
    assert "recover_topology_b" in main_calls
    assert "retire_topology_b" in main_calls
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
    for name in (
        "execute_topology_b",
        "recover_topology_b",
        "retire_topology_b",
    ):
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
        projection_authority_root=operation_root / "projection-authority",
        projection_current_sha256="9" * 64,
        projection_snapshot_root=(
            operation_root
            / "projection-authority"
            / ("public-projection-" + ("a" * 64))
        ),
        projection_snapshot_id="public-projection-" + ("a" * 64),
        projection_snapshot_sha256="a" * 64,
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
                        "source": str(config.projection_authority_root),
                        "currentSha256": (
                            config.projection_current_sha256
                        ),
                        "snapshotId": config.projection_snapshot_id,
                        "snapshotTreeSha256": (
                            config.projection_source_tree_sha256
                        ),
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


def r7_retirement_loader_inputs(
    tmp_path: Path,
) -> tuple[Any, SimpleNamespace, dict[str, Any], bytes]:
    fixture = (
        ROOT
        / "tests"
        / "fixtures"
        / "cloudflare-committed-r7.json"
    )
    fixture_raw = fixture.read_bytes()
    r7_project = (
        "chummer-public-download-windows-preview-pr74-"
        "c46cfcf9-20260725t041830z-r7"
    )
    r7_source_head = "c46cfcf92ccc7fd051157e88dc76fde580f8d71e"
    actions = object.__new__(controller.TopologyBActions)
    actions.cloudflare = load_module(
        ROOT / "scripts" / "cloudflare_public_download_transaction.py",
        f"r7_retirement_cloudflare_{time.time_ns()}",
    )
    operation_root = tmp_path / r7_project
    operation_root.mkdir(mode=0o700)
    evidence_path = operation_root / "cloudflare-committed.json"
    evidence_path.write_bytes(fixture_raw)
    evidence_path.chmod(0o600)
    config = SimpleNamespace(
        operation=controller.RETIRE_OPERATION,
        operation_root=operation_root,
        project_name=r7_project,
        source_head=r7_source_head,
        cloudflare_committed_evidence=evidence_path,
        cloudflare_account_id=actions.cloudflare.R7_RETIREMENT_ACCOUNT_ID,
        cloudflare_tunnel_id=actions.cloudflare.R7_RETIREMENT_TUNNEL_ID,
    )
    active = {
        "operation": controller.CUTOVER_OPERATION,
        "operationRoot": str(operation_root),
        "origin": controller.SIDECAR_ORIGIN,
        "projectName": r7_project,
        "sourceHead": r7_source_head,
        "generationId": actions.cloudflare.R7_RETIREMENT_GENERATION_ID,
        "cloudflare": {
            "evidencePath": str(evidence_path),
            "evidenceSha256": actions.cloudflare.R7_RETIREMENT_EVIDENCE_SHA256,
            "targetConfigSha256": (
                actions.cloudflare.R7_RETIREMENT_TARGET_CONFIG_SHA256
            ),
            "targetVersion": actions.cloudflare.R7_RETIREMENT_TARGET_VERSION,
        },
    }
    return actions, config, active, fixture_raw


def test_retirement_accepts_only_the_byte_pinned_r7_terminal_evidence(
    tmp_path: Path,
) -> None:
    actions, config, active, fixture_raw = r7_retirement_loader_inputs(
        tmp_path
    )

    raw, payload = actions._load_committed_retirement_evidence(
        config,
        active,
    )

    assert raw == fixture_raw
    assert hashlib.sha256(raw).hexdigest() == (
        actions.cloudflare.R7_RETIREMENT_EVIDENCE_SHA256
    )
    assert payload["phase"] == "committed"
    assert payload["priorVersion"] == (
        actions.cloudflare.R7_RETIREMENT_PRIOR_VERSION
    )
    assert (
        payload["targetVersion"]
        == actions.cloudflare.R7_RETIREMENT_TARGET_VERSION
    )


@pytest.mark.parametrize(
    "drift",
    [
        "generation",
        "active-evidence-sha",
        "target-config-sha",
        "target-version",
        "account",
        "tunnel",
        "raw-byte",
    ],
)
def test_r7_retirement_compatibility_rejects_identity_or_byte_drift(
    tmp_path: Path,
    drift: str,
) -> None:
    actions, config, active, fixture_raw = r7_retirement_loader_inputs(
        tmp_path
    )
    if drift == "generation":
        active["generationId"] = "g-drifted"
    elif drift == "active-evidence-sha":
        active["cloudflare"]["evidenceSha256"] = "0" * 64
    elif drift == "target-config-sha":
        active["cloudflare"]["targetConfigSha256"] = "0" * 64
    elif drift == "target-version":
        active["cloudflare"]["targetVersion"] = 13
    elif drift == "account":
        config.cloudflare_account_id = "account-drifted"
    elif drift == "tunnel":
        config.cloudflare_tunnel_id = "tunnel-drifted"
    elif drift == "raw-byte":
        mutated = fixture_raw.replace(
            b'"updatedAt":"2026-07-25T04:25:43.650029Z"',
            b'"updatedAt":"2026-07-25T04:25:43.650028Z"',
        )
        assert mutated != fixture_raw
        config.cloudflare_committed_evidence.write_bytes(mutated)
        config.cloudflare_committed_evidence.chmod(0o600)

    with pytest.raises(controller.RecoveryUncertain):
        actions._load_committed_retirement_evidence(config, active)


def test_explicit_retirement_restores_proves_retires_then_cleans(
    tmp_path: Path,
) -> None:
    require_topology_b_surface()
    config = topology_b_config(tmp_path)
    config.operation = controller.RETIRE_OPERATION
    config.source_head = "a" * 40
    config.controller_source_head = "b" * 40
    canonical_before = config.canonical_shelf_sentinel.read_bytes()
    actions = RecordingActions(baseline_captured=True)
    original_handlers = {
        signal_number: signal.getsignal(signal_number)
        for signal_number in (signal.SIGINT, signal.SIGTERM)
    }

    result = controller.retire_topology_b(config, actions=actions)

    assert result["disposition"] == "committed-sidecar-retired-to-incumbent"
    assert actions.events == [
        "verify_canonical_incumbent_before_retirement",
        "authorize_committed_retirement",
        "restore_committed_prior",
        "probe_incumbent_after-retirement_chummer.run,www.chummer.run",
        "commit_retirement_evidence",
        "retire_active_authority",
        "verify_retired_authority_connectors",
        "cleanup_sidecar",
        "finalize_committed_retirement",
    ]
    assert "classify_recovery_committed" not in actions.events
    assert "reconcile_committed" not in actions.events
    assert "cloudflare_rollback" not in actions.events
    assert config.canonical_shelf_sentinel.read_bytes() == canonical_before
    assert {
        signal_number: signal.getsignal(signal_number)
        for signal_number in (signal.SIGINT, signal.SIGTERM)
    } == original_handlers


def test_retirement_preflight_freezes_flat_primary_without_mutating_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shelf = tmp_path / "downloads"
    shelf.mkdir()
    canonical = b'{"version":"incumbent"}\n'
    compatibility = b'{"downloads":[],"version":"incumbent"}\n'
    (shelf / "RELEASE_CHANNEL.generated.json").write_bytes(canonical)
    (shelf / "releases.json").write_bytes(compatibility)
    journal = tmp_path / "operation.json"
    journal.write_text('{"phase":"active"}\n', encoding="utf-8")
    journal.chmod(0o600)
    operation_root = tmp_path / "chummer-public-download-incumbent"
    config = SimpleNamespace(
        operation=controller.RETIRE_OPERATION,
        operation_root=operation_root,
        operation_journal=journal,
        shelf_root=shelf,
    )
    by_path = {
        "/downloads/RELEASE_CHANNEL.generated.json": canonical,
        "/downloads/releases.json": compatibility,
    }
    baseline = {
        hostname: {
            path: {
                "httpStatus": 200,
                "bodySha256": hashlib.sha256(payload).hexdigest(),
                "sizeBytes": len(payload),
            }
            for path, payload in by_path.items()
        }
        for hostname in HOSTS
    }

    class Cloudflare:
        @staticmethod
        def parse_configuration_response(_value: Any) -> Any:
            return SimpleNamespace(sha256="a" * 64, version=12)

        @staticmethod
        def canonical_sha256(value: Any) -> str:
            return hashlib.sha256(
                json.dumps(value, sort_keys=True).encode()
            ).hexdigest()

    actions = object.__new__(controller.TopologyBActions)
    actions.config = config
    actions.runner = object()
    actions.cloudflare = Cloudflare()
    actions._state = {"phase": "active", "receipts": {}}
    actions._load_retirement_authority = lambda _config: (
        b"active\n",
        {"cloudflare": {}},
        tmp_path / "active.json",
    )
    actions._load_committed_retirement_evidence = (
        lambda _config, _active: (
            b"committed\n",
            {
                "targetConfigSha256": "a" * 64,
                "targetVersion": 12,
            },
        )
    )
    actions._validated_retirement_baseline = lambda: baseline
    actions._cloudflare_api = lambda: SimpleNamespace(
        get_configuration=lambda: {}
    )
    monkeypatch.setattr(
        controller,
        "service_container",
        lambda *_args, **_kwargs: "b" * 64,
    )
    monkeypatch.setattr(
        controller,
        "container_runtime",
        lambda *_args, **_kwargs: {
            "existed": True,
            "wasRunning": True,
            "containerId": "b" * 64,
            "imageId": "sha256:" + "c" * 64,
        },
    )
    monkeypatch.setattr(
        controller,
        "docker_inspect_json",
        lambda *_args, **_kwargs: {
            "Mounts": [
                {
                    "Type": "bind",
                    "Source": str(shelf),
                    "Destination": "/downloads-source",
                    "RW": True,
                }
            ]
        },
    )
    monkeypatch.setattr(
        controller,
        "_http_bytes",
        lambda **kwargs: (200, {}, by_path[kwargs["path"]]),
    )
    before = controller.tree_sha256_file_stream(
        shelf,
        label="primary before retirement preflight",
    )

    receipt = actions.verify_canonical_incumbent_before_retirement(
        config
    )

    assert receipt["status"] == "pass"
    assert receipt["canonicalShelfMutated"] is False
    assert receipt["observations"] == baseline
    assert actions._state["phase"] == "active"
    assert controller.tree_sha256_file_stream(
        shelf,
        label="primary after retirement preflight",
    ) == before


class FatalRetirementBoundary(BaseException):
    pass


@pytest.mark.parametrize(
    "failure_event",
    (
        "verify_canonical_incumbent_before_retirement",
        "authorize_committed_retirement",
        "restore_committed_prior",
        "probe_incumbent_after-retirement_chummer.run,www.chummer.run",
        "commit_retirement_evidence",
        "retire_active_authority",
        "verify_retired_authority_connectors",
        "cleanup_sidecar",
        "finalize_committed_retirement",
    ),
)
@pytest.mark.parametrize(
    "fatal_type",
    (KeyboardInterrupt, SystemExit, FatalRetirementBoundary),
)
def test_retirement_base_exceptions_are_lock_retaining_uncertainty(
    tmp_path: Path,
    failure_event: str,
    fatal_type: type[BaseException],
) -> None:
    config = topology_b_config(tmp_path)
    config.operation = controller.RETIRE_OPERATION
    config.source_head = "a" * 40
    config.controller_source_head = "b" * 40
    actions = RecordingActions(baseline_captured=True)
    original_record = actions.record

    def fatal_record(event: str, result: Any = None) -> Any:
        if event == failure_event:
            actions.events.append(event)
            raise fatal_type()
        return original_record(event, result)

    actions.record = fatal_record  # type: ignore[method-assign]
    original_handlers = {
        signal_number: signal.getsignal(signal_number)
        for signal_number in (signal.SIGINT, signal.SIGTERM)
    }

    with pytest.raises(controller.RecoveryUncertain) as raised:
        controller.retire_topology_b(config, actions=actions)

    assert isinstance(raised.value.__cause__, fatal_type)
    assert actions.events[-1] == failure_event
    assert {
        signal_number: signal.getsignal(signal_number)
        for signal_number in (signal.SIGINT, signal.SIGTERM)
    } == original_handlers


def test_keyboard_interrupt_outside_retirement_keeps_normal_semantics(
    tmp_path: Path,
) -> None:
    config = topology_b_config(tmp_path)

    def interrupted(*_args: Any, **_kwargs: Any) -> Any:
        raise KeyboardInterrupt()

    with pytest.raises(KeyboardInterrupt):
        controller.execute_topology_b(
            config,
            actions=SimpleNamespace(
                prepare_sidecar_release_shelf=interrupted
            ),
        )
    with pytest.raises(KeyboardInterrupt):
        controller.recover_topology_b(
            config,
            actions=SimpleNamespace(classify_recovery=interrupted),
        )


@pytest.mark.parametrize("signal_number", (signal.SIGINT, signal.SIGTERM))
@pytest.mark.parametrize(
    "boundary",
    (
        "restore_committed_prior",
        "retire_active_authority",
        "verify_retired_authority_connectors",
    ),
)
def test_retirement_subprocess_signal_is_status_76_at_destructive_boundaries(
    tmp_path: Path,
    signal_number: signal.Signals,
    boundary: str,
) -> None:
    child = tmp_path / "retirement-signal-child.py"
    ready = tmp_path / "ready"
    receipt = tmp_path / "receipt.json"
    child.write_text(
        """
import importlib.util
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace

controller_path = Path(sys.argv[1])
boundary = sys.argv[2]
ready = Path(sys.argv[3])
receipt = Path(sys.argv[4])
spec = importlib.util.spec_from_file_location("retirement_signal_controller", controller_path)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)

def maybe_block(name):
    if boundary == name:
        ready.write_text(name, encoding="utf-8")
        while True:
            time.sleep(10)
    return {"stage": name}

class Actions:
    def verify_canonical_incumbent_before_retirement(self, *_args):
        return maybe_block("verify_canonical_incumbent_before_retirement")
    def authorize_committed_retirement(self, *_args):
        return maybe_block("authorize_committed_retirement")
    def restore_committed_prior(self, *_args):
        return maybe_block("restore_committed_prior")
    def probe_public_incumbent(self, *_args, **_kwargs):
        return maybe_block("probe_public_incumbent")
    def commit_retirement_evidence(self, *_args):
        return maybe_block("commit_retirement_evidence")
    def retire_active_authority(self, *_args):
        return maybe_block("retire_active_authority")
    def verify_retired_authority_connectors(self, *_args):
        return maybe_block("verify_retired_authority_connectors")
    def cleanup_sidecar_resources(self, *_args):
        return maybe_block("cleanup_sidecar_resources")
    def finalize_committed_retirement(self, *_args):
        return maybe_block("finalize_committed_retirement")

config = SimpleNamespace(
    operation=module.RETIRE_OPERATION,
    source_head="a" * 40,
    controller_source_head="b" * 40,
)
try:
    module.retire_topology_b(config, actions=Actions())
except module.RecoveryUncertain as error:
    receipt.write_text(
        json.dumps(
            {
                "status": 76,
                "cause": type(error.__cause__).__name__,
                "boundary": boundary,
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    raise SystemExit(76)
raise SystemExit(0)
""".lstrip(),
        encoding="utf-8",
    )
    process = subprocess.Popen(
        [
            sys.executable,
            str(child),
            str(CONTROLLER_PATH),
            boundary,
            str(ready),
            str(receipt),
        ],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    deadline = time.monotonic() + 5
    while (
        not ready.exists()
        and process.poll() is None
        and time.monotonic() < deadline
    ):
        time.sleep(0.01)
    assert ready.read_text(encoding="utf-8") == boundary

    os.kill(process.pid, signal_number)
    stdout, stderr = process.communicate(timeout=5)

    assert process.returncode == 76, (stdout, stderr)
    assert json.loads(receipt.read_text(encoding="utf-8")) == {
        "boundary": boundary,
        "cause": "_RetirementInterrupted",
        "status": 76,
    }


@pytest.mark.parametrize(
    "failure_event",
    (
        "verify_canonical_incumbent_before_retirement",
        "authorize_committed_retirement",
        "restore_committed_prior",
        "probe_incumbent_after-retirement_chummer.run,www.chummer.run",
        "commit_retirement_evidence",
        "retire_active_authority",
        "verify_retired_authority_connectors",
        "cleanup_sidecar",
        "finalize_committed_retirement",
    ),
)
def test_retirement_partial_failure_is_uncertain_and_never_reapplies_target(
    tmp_path: Path,
    failure_event: str,
) -> None:
    config = topology_b_config(tmp_path)
    config.operation = controller.RETIRE_OPERATION
    config.source_head = "a" * 40
    config.controller_source_head = "b" * 40
    actions = RecordingActions(
        fail_at=failure_event,
        baseline_captured=True,
    )

    with pytest.raises(controller.RecoveryUncertain):
        controller.retire_topology_b(config, actions=actions)

    assert "cloudflare_apply" not in actions.events
    assert "cloudflare_rollback" not in actions.events
    failure_index = actions.events.index(failure_event)
    assert actions.events == actions.events[: failure_index + 1]
    if failure_event in {
        "authorize_committed_retirement",
        "restore_committed_prior",
        "probe_incumbent_after-retirement_chummer.run,www.chummer.run",
        "commit_retirement_evidence",
    }:
        assert "retire_active_authority" not in actions.events
        assert "cleanup_sidecar" not in actions.events
    if failure_event == "verify_retired_authority_connectors":
        assert "retire_active_authority" in actions.events
        assert "cleanup_sidecar" not in actions.events


class RetirementTestLock:
    def __init__(self, _path: Path) -> None:
        pass

    def __enter__(self) -> "RetirementTestLock":
        return self

    def __exit__(self, *_args: Any) -> None:
        return None


class RetirementTestApi:
    def __init__(self, snapshot: SimpleNamespace) -> None:
        self.snapshot = snapshot
        self.put_calls = 0

    def get_configuration(self) -> SimpleNamespace:
        return self.snapshot


def retirement_connector_gate(
    version: int,
    *connector_ids: str,
) -> dict[str, Any]:
    ids = list(connector_ids or ("connector-a",))
    connector_set = [
        {
            "id": connector_id,
            "configVersionAvailable": True,
            "configVersion": version,
        }
        for connector_id in ids
    ]
    return {
        "contractName": (
            "cloudflare.current-connector-convergence/v1"
        ),
        "targetVersion": version,
        "connectorSet": connector_set,
        "connectorSetSha256": hashlib.sha256(
            json.dumps(
                connector_set,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest(),
        "connectorConvergence": [
            {
                "id": connector_id,
                "configVersionAvailable": True,
                "observedConfigVersion": version,
                "converged": True,
            }
            for connector_id in ids
        ],
        "connectorSetTransitions": [ids],
        "attemptsUsed": 2,
        "stableObservationsRequired": 2,
    }


def retirement_connector_boundary(
    *,
    operation_root: Path,
    boundary: str,
    version: int,
    retired_authority_sha256: str,
    marker_gate: Mapping[str, Any],
    convergence: Mapping[str, Any],
    verified_at: str = "2026-07-25T00:00:00Z",
) -> dict[str, Any]:
    def canonical_sha256(value: Any) -> str:
        return hashlib.sha256(
            json.dumps(
                value,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()

    return {
        "contractName": (
            "chummer.public-download-retirement-"
            "connector-boundary/v1"
        ),
        "status": "pass",
        "boundary": boundary,
        "operationRoot": str(operation_root),
        "restoredVersion": version,
        "retiredAuthoritySha256": retired_authority_sha256,
        "markerConnectorGateSha256": canonical_sha256(marker_gate),
        "connectorConvergence": dict(convergence),
        "connectorConvergenceSha256": canonical_sha256(convergence),
        "verifiedAtUtc": verified_at,
    }


def retirement_restore_actions(
    tmp_path: Path,
    *,
    current: SimpleNamespace,
) -> tuple[Any, SimpleNamespace, RetirementTestApi, dict[str, Any]]:
    operation_root = tmp_path / "chummer-public-download-retirement-test"
    operation_root.mkdir(mode=0o700)
    config = SimpleNamespace(
        operation_root=operation_root,
        cloudflare_lock=operation_root / "cloudflare.lock",
    )
    authorization = {"authorization": "durable"}
    evidence = {
        "targetConfigSha256": "1" * 64,
        "targetVersion": 12,
        "priorConfig": {"ingress": [{"service": "http_status:404"}]},
        "priorConfigSha256": "2" * 64,
        "preexistingConnectors": [
            {
                "id": "connector-a",
                "configVersionAvailable": True,
                "configVersion": 12,
            }
        ],
    }
    api = RetirementTestApi(current)
    actions = object.__new__(controller.TopologyBActions)
    actions._state = {
        "phase": "retirement-authorized",
        "receipts": {"retirementAuthorization": authorization},
    }
    actions._load_retirement_authority = (
        lambda _config: (b"active", {}, tmp_path / "active.json")
    )
    actions._load_committed_retirement_evidence = (
        lambda _config, _active: (b"committed", evidence)
    )
    actions._cloudflare_api = lambda: api
    actions.cloudflare = SimpleNamespace(
        ExclusiveFileLock=RetirementTestLock,
        parse_configuration_response=lambda response: response,
        validate_current_connector_convergence_receipt=lambda value: value,
    )
    return actions, config, api, authorization


def test_retirement_toctou_drift_stops_before_cloudflare_put(
    tmp_path: Path,
) -> None:
    current = SimpleNamespace(sha256="3" * 64, version=13)
    actions, config, api, authorization = retirement_restore_actions(
        tmp_path,
        current=current,
    )

    def forbidden_put(*_args: Any, **_kwargs: Any) -> Any:
        api.put_calls += 1
        raise AssertionError("drifted target must not be mutated")

    actions.cloudflare._configuration_after_put_or_reget = forbidden_put

    with pytest.raises(
        controller.RecoveryUncertain,
        match="drifted before retirement PUT",
    ):
        actions.restore_committed_prior(config, authorization)

    assert api.put_calls == 0
    assert "cloudflareRetirement" not in actions._state["receipts"]


def test_retirement_reconciles_lost_receipt_without_second_put(
    tmp_path: Path,
) -> None:
    target = SimpleNamespace(
        sha256="1" * 64,
        version=12,
        response={"target": True},
    )
    prior = SimpleNamespace(
        sha256="2" * 64,
        version=13,
        response={"prior": True},
    )
    actions, config, api, authorization = retirement_restore_actions(
        tmp_path,
        current=target,
    )

    def restore(*_args: Any, **_kwargs: Any) -> SimpleNamespace:
        api.put_calls += 1
        api.snapshot = prior
        return prior

    actions.cloudflare._configuration_after_put_or_reget = restore
    actions.cloudflare.poll_configuration = (
        lambda *_args, **_kwargs: api.snapshot
    )
    actions.cloudflare.poll_current_connector_convergence = (
        lambda *_args, **_kwargs: retirement_connector_gate(13)
    )
    actions.cloudflare.canonical_sha256 = (
        lambda _value: "4" * 64
    )
    attempts = 0

    def durable_record(
        phase: str,
        name: str,
        receipt: dict[str, Any],
    ) -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise OSError("simulated crash after remote restore")
        actions._state["phase"] = phase
        actions._state["receipts"][name] = receipt

    actions._record = durable_record

    with pytest.raises(
        controller.RecoveryUncertain,
        match="restoration is uncertain",
    ):
        actions.restore_committed_prior(config, authorization)

    assert api.put_calls == 1
    recovered = actions.restore_committed_prior(config, authorization)
    repeated = actions.restore_committed_prior(config, authorization)

    assert recovered == repeated
    assert recovered["restoredVersion"] == 13
    assert api.put_calls == 1
    assert attempts == 3


def test_retirement_resume_rebinds_to_the_current_connector_set(
    tmp_path: Path,
) -> None:
    prior = SimpleNamespace(
        sha256="2" * 64,
        version=13,
        response={"prior": True},
    )
    actions, config, api, authorization = retirement_restore_actions(
        tmp_path,
        current=prior,
    )
    original_gate = retirement_connector_gate(
        13,
        "connector-removed",
    )
    current_gate = retirement_connector_gate(
        13,
        "connector-added",
    )
    existing = {
        "contractName": (
            "chummer.public-download-cloudflare-retirement/v1"
        ),
        "phase": "restored",
        "operationRoot": str(config.operation_root),
        "targetConfigSha256": "1" * 64,
        "targetVersion": 12,
        "priorConfigSha256": "2" * 64,
        "restoredVersion": 13,
        "restoredResponseSha256": "4" * 64,
        "connectorConvergence": original_gate,
        "restoredAtUtc": "2026-07-25T00:00:00Z",
        "connectorsVerifiedAtUtc": "2026-07-25T00:00:00Z",
    }
    actions._state["receipts"]["cloudflareRetirement"] = existing
    actions.cloudflare.poll_current_connector_convergence = (
        lambda *_args, **_kwargs: current_gate
    )
    actions.cloudflare.canonical_sha256 = lambda _value: "4" * 64

    def record(
        phase: str,
        name: str,
        receipt: dict[str, Any],
    ) -> None:
        actions._state["phase"] = phase
        actions._state["receipts"][name] = receipt

    actions._record = record

    resumed = actions.restore_committed_prior(config, authorization)

    assert api.put_calls == 0
    assert resumed == existing
    assert (
        actions._state["receipts"]["cloudflareRetirement"]
        ["connectorConvergence"]
        == original_gate
    )
    assert (
        actions._state["receipts"]
        ["retirementRestorationConnectorResumeGate"]
        == current_gate
    )
    assert resumed["restoredAtUtc"] == existing["restoredAtUtc"]


def test_retirement_atomically_moves_authority_and_is_idempotent(
    tmp_path: Path,
) -> None:
    authority_root = tmp_path / "authority"
    operation_root = tmp_path / "operation"
    authority_root.mkdir(mode=0o700)
    operation_root.mkdir(mode=0o700)
    active = authority_root / "active.json"
    retired = operation_root / "retired.json"
    evidence_path = operation_root / "retirement-evidence.json"
    authority_raw = b'{"authority":"exact"}\n'
    evidence_raw = b'{"retirement":"proved"}\n'
    active.write_bytes(authority_raw)
    evidence_path.write_bytes(evidence_raw)
    active.chmod(0o600)
    evidence_path.chmod(0o600)
    config = SimpleNamespace(
        active_runtime_authority=active,
        retired_active_authority=retired,
        cloudflare_retirement_evidence=evidence_path,
        cloudflare_lock=operation_root / "cloudflare.lock",
        operation_root=operation_root,
    )
    authorization = {
        "activeAuthoritySha256": hashlib.sha256(
            authority_raw
        ).hexdigest()
    }
    restoration = {"restored": True, "restoredVersion": 13}
    retirement_evidence = {
        "priorConfigSha256": "1" * 64,
        "restoredVersion": 13,
        "evidenceSha256": hashlib.sha256(evidence_raw).hexdigest(),
    }
    actions = object.__new__(controller.TopologyBActions)
    actions._state = {
        "receipts": {
            "retirementAuthorization": authorization,
            "cloudflareRetirement": restoration,
            "retirementEvidence": retirement_evidence,
        }
    }
    api = RetirementTestApi(
        SimpleNamespace(sha256="1" * 64, version=13)
    )
    actions._cloudflare_api = lambda: api
    connector_checks: list[tuple[bool, bool]] = []

    def current_connector_gate(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        connector_checks.append((active.exists(), retired.exists()))
        if active.exists():
            return retirement_connector_gate(
                13,
                "connector-at-marker",
            )
        return retirement_connector_gate(
            13,
            "connector-added-before-resume",
        )

    actions.cloudflare = SimpleNamespace(
        ExclusiveFileLock=RetirementTestLock,
        parse_configuration_response=lambda response: response,
        poll_current_connector_convergence=current_connector_gate,
        validate_current_connector_convergence_receipt=(
            lambda value: value
        ),
        canonical_sha256=lambda value: hashlib.sha256(
            json.dumps(
                value,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest(),
    )

    def load_authority(
        _config: SimpleNamespace,
    ) -> tuple[bytes, dict[str, Any], Path]:
        path = active if active.exists() else retired
        return path.read_bytes(), {}, path

    actions._load_retirement_authority = load_authority

    def record(
        phase: str,
        name: str,
        receipt: dict[str, Any],
    ) -> None:
        actions._state["phase"] = phase
        actions._state["receipts"][name] = receipt

    actions._record = record

    first = actions.retire_active_authority(
        config,
        authorization,
        restoration,
        retirement_evidence,
    )
    second = actions.retire_active_authority(
        config,
        authorization,
        restoration,
        retirement_evidence,
    )

    assert first == second
    assert first["disposition"] == "atomically-retired"
    assert not active.exists()
    assert retired.read_bytes() == authority_raw
    assert retired.stat().st_mode & 0o777 == 0o600
    assert "retirementConnectorGate" in actions._state["receipts"]
    assert "retirementConnectorResumeGate" not in actions._state["receipts"]
    assert connector_checks == [(True, False)]


def post_marker_connector_actions(
    tmp_path: Path,
) -> tuple[
    Any,
    SimpleNamespace,
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
]:
    operation_root = tmp_path / "operation"
    authority_root = tmp_path / "authority"
    operation_root.mkdir(mode=0o700)
    authority_root.mkdir(mode=0o700)
    active = authority_root / "active.json"
    retired = operation_root / "retired.json"
    retired_raw = b'{"authority":"retired"}\n'
    retired.write_bytes(retired_raw)
    retired.chmod(0o600)
    config = SimpleNamespace(
        active_runtime_authority=active,
        retired_active_authority=retired,
        cloudflare_lock=operation_root / "cloudflare.lock",
        operation_root=operation_root,
    )

    def canonical_sha256(value: Any) -> str:
        return hashlib.sha256(
            json.dumps(
                value,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()

    retired_sha256 = hashlib.sha256(retired_raw).hexdigest()
    marker_gate = retirement_connector_gate(
        13,
        "connector-at-marker",
    )
    authorization = {"activeAuthoritySha256": retired_sha256}
    restoration = {
        "priorConfigSha256": "1" * 64,
        "restoredVersion": 13,
    }
    retirement_evidence = {
        "priorConfigSha256": "1" * 64,
        "restoredVersion": 13,
    }
    retired_authority = {
        "activeAuthoritySha256": retired_sha256,
        "connectorGateSha256": canonical_sha256(marker_gate),
    }
    actions = object.__new__(controller.TopologyBActions)
    actions._state = {
        "receipts": {
            "retirementAuthorization": authorization,
            "cloudflareRetirement": restoration,
            "retirementEvidence": retirement_evidence,
            "retiredAuthority": retired_authority,
            "retirementConnectorGate": marker_gate,
        }
    }
    actions._load_retirement_authority = (
        lambda _config: (retired_raw, {}, retired)
    )
    actions._cloudflare_api = lambda: RetirementTestApi(
        SimpleNamespace(sha256="1" * 64, version=13)
    )
    actions.cloudflare = SimpleNamespace(
        ExclusiveFileLock=RetirementTestLock,
        parse_configuration_response=lambda response: response,
        validate_current_connector_convergence_receipt=(
            lambda value: value
        ),
        canonical_sha256=canonical_sha256,
    )

    def record(
        phase: str,
        name: str,
        receipt: dict[str, Any],
    ) -> None:
        actions._state["phase"] = phase
        actions._state["receipts"][name] = receipt

    actions._record = record
    return (
        actions,
        config,
        authorization,
        restoration,
        retirement_evidence,
        retired_authority,
    )


def terminal_adoption_fixture(
    tmp_path: Path,
) -> tuple[SimpleNamespace, dict[str, Any], dict[str, Any]]:
    operation_root = tmp_path / "operation"
    authority_root = tmp_path / "authority"
    receipt_root = tmp_path / "receipts"
    operation_root.mkdir(mode=0o700)
    authority_root.mkdir(mode=0o700)
    receipt_root.mkdir(mode=0o700)
    active_path = authority_root / "active.json"
    retired_path = operation_root / "retired.json"
    committed_path = operation_root / "cloudflare-committed.json"
    evidence_path = operation_root / "retirement-evidence.json"
    terminal_path = operation_root / "retirement.json"
    operation_journal = receipt_root / "operation.json"
    source_head = "a" * 40
    controller_source_head = "b" * 40
    project_name = "retirement-adoption-test"
    volumes = {"public-download-app": "retirement-adoption-app"}
    config = SimpleNamespace(
        operation=controller.RETIRE_OPERATION,
        source_root=ROOT,
        source_head=source_head,
        controller_source_head=controller_source_head,
        operation_root=operation_root,
        operation_journal=operation_journal,
        project_name=project_name,
        volume_names=volumes,
        active_runtime_authority=active_path,
        retired_active_authority=retired_path,
        cloudflare_committed_evidence=committed_path,
        cloudflare_retirement_evidence=evidence_path,
        retirement_receipt=terminal_path,
    )

    def canonical_sha256(value: Any) -> str:
        return hashlib.sha256(
            json.dumps(
                value,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()

    active_authority = {
        "schema": "test-only-retired-authority",
        "status": "active",
        "operationRoot": str(operation_root),
        "projectName": project_name,
        "sourceHead": source_head,
    }
    controller.write_private_json(retired_path, active_authority)
    retired_raw = retired_path.read_bytes()
    retired_sha256 = hashlib.sha256(retired_raw).hexdigest()
    committed = {"phase": "committed", "authority": "test-only"}
    controller.write_private_json(committed_path, committed)
    committed_raw = committed_path.read_bytes()
    baseline = {
        hostname: {
            path: {
                "httpStatus": 200,
                "bodySha256": hashlib.sha256(
                    f"{hostname}:{path}".encode()
                ).hexdigest(),
                "sizeBytes": 1,
            }
            for path in (
                "/downloads/RELEASE_CHANNEL.generated.json",
                "/downloads/releases.json",
            )
        }
        for hostname in HOSTS
    }
    marker_gate = retirement_connector_gate(
        13,
        "connector-at-marker",
    )
    authorization = {
        "contractName": (
            "chummer.public-download-committed-retirement-"
            "authorization/v1"
        ),
        "operation": controller.RETIRE_OPERATION,
        "operationRoot": str(operation_root),
        "projectName": project_name,
        "operationSourceHead": source_head,
        "controllerSourceHead": controller_source_head,
        "activeAuthorityPath": str(active_path),
        "activeAuthoritySha256": retired_sha256,
        "committedEvidencePath": str(committed_path),
        "committedEvidenceSha256": hashlib.sha256(
            committed_raw
        ).hexdigest(),
        "targetConfigSha256": "1" * 64,
        "targetVersion": 12,
        "priorConfigSha256": "2" * 64,
        "priorVersion": 11,
        "incumbentBaselineSha256": canonical_sha256(baseline),
        "authorizedAtUtc": "2026-07-25T00:00:00Z",
    }
    restoration = {
        "contractName": (
            "chummer.public-download-cloudflare-retirement/v1"
        ),
        "phase": "restored",
        "operationRoot": str(operation_root),
        "targetConfigSha256": authorization["targetConfigSha256"],
        "targetVersion": authorization["targetVersion"],
        "priorConfigSha256": authorization["priorConfigSha256"],
        "restoredVersion": 13,
        "restoredResponseSha256": "3" * 64,
        "connectorConvergence": retirement_connector_gate(
            13,
            "connector-restored",
        ),
        "restoredAtUtc": "2026-07-25T00:01:00Z",
        "connectorsVerifiedAtUtc": "2026-07-25T00:01:01Z",
    }
    evidence = {
        "contractName": (
            "chummer.public-download-committed-retirement-evidence/v1"
        ),
        "status": "committed",
        "operation": controller.RETIRE_OPERATION,
        "operationRoot": str(operation_root),
        "projectName": project_name,
        "operationSourceHead": source_head,
        "controllerSourceHead": controller_source_head,
        "authorizationSha256": canonical_sha256(authorization),
        "restorationSha256": canonical_sha256(restoration),
        "connectorConvergenceSha256": canonical_sha256(
            restoration["connectorConvergence"]
        ),
        "targetConfigSha256": authorization["targetConfigSha256"],
        "targetVersion": authorization["targetVersion"],
        "priorConfigSha256": restoration["priorConfigSha256"],
        "restoredVersion": restoration["restoredVersion"],
        "incumbentBaselineSha256": canonical_sha256(baseline),
        "incumbentObservationSha256": canonical_sha256(baseline),
        "incumbent": baseline,
        "committedAtUtc": "2026-07-25T00:02:00Z",
    }
    controller.write_private_json(evidence_path, evidence)
    evidence_raw = evidence_path.read_bytes()
    retirement_evidence = {
        "contractName": (
            "chummer.public-download-retirement-evidence-summary/v1"
        ),
        "status": "committed",
        "evidencePath": str(evidence_path),
        "evidenceSha256": hashlib.sha256(evidence_raw).hexdigest(),
        "priorConfigSha256": restoration["priorConfigSha256"],
        "restoredVersion": restoration["restoredVersion"],
        "connectorConvergenceSha256": canonical_sha256(
            restoration["connectorConvergence"]
        ),
        "incumbentBaselineSha256": canonical_sha256(baseline),
    }
    retired_authority = {
        "contractName": (
            "chummer.public-download-retired-authority/v1"
        ),
        "status": "retired",
        "activeAuthorityPath": str(active_path),
        "retiredAuthorityPath": str(retired_path),
        "activeAuthoritySha256": retired_sha256,
        "retirementEvidenceSha256": hashlib.sha256(
            evidence_raw
        ).hexdigest(),
        "connectorGateSha256": canonical_sha256(marker_gate),
        "disposition": "atomically-retired",
        "retiredAtUtc": "2026-07-25T00:03:00Z",
    }
    post_marker_gate = retirement_connector_boundary(
        operation_root=operation_root,
        boundary="post-marker",
        version=13,
        retired_authority_sha256=retired_sha256,
        marker_gate=marker_gate,
        convergence=retirement_connector_gate(
            13,
            "connector-post-marker",
        ),
    )
    cleanup = {
        "contractName": "test-only-cleanup/v1",
        "status": "pass",
    }
    receipts = {
        "activeAuthority": active_authority,
        "retirementAuthorization": authorization,
        "cloudflareRetirement": restoration,
        "incumbentAfterRetirement": baseline,
        "retirementEvidence": retirement_evidence,
        "retiredAuthority": retired_authority,
        "retirementConnectorGate": marker_gate,
        "retirementPostMarkerConnectorGate": post_marker_gate,
        "cleanup": cleanup,
    }
    state = {
        "schema": controller.TOPOLOGY_B_OPERATION_SCHEMA,
        "phase": "cleaned",
        "operation": controller.CUTOVER_OPERATION,
        "projectName": project_name,
        "operationRoot": str(operation_root),
        "sourceHead": source_head,
        "volumes": volumes,
        "createdAtUtc": "2026-07-25T00:00:00Z",
        "updatedAtUtc": "2026-07-25T00:04:00Z",
        "receipts": receipts,
        "incumbentBaseline": baseline,
    }
    controller.write_private_json(operation_journal, state)
    terminal = {
        "contractName": (
            "chummer.public-download-committed-retirement/v1"
        ),
        "status": "retired",
        "operation": controller.RETIRE_OPERATION,
        "operationRoot": str(operation_root),
        "projectName": project_name,
        "operationSourceHead": source_head,
        "controllerSourceHead": controller_source_head,
        "retiredAuthorityPath": str(retired_path),
        "retiredAuthoritySha256": retired_sha256,
        "retirementEvidencePath": str(evidence_path),
        "retirementEvidenceSha256": hashlib.sha256(
            evidence_raw
        ).hexdigest(),
        "connectorGateSha256": canonical_sha256(marker_gate),
        "postMarkerConnectorGateSha256": canonical_sha256(
            post_marker_gate
        ),
        "latestConnectorGateSha256": canonical_sha256(
            post_marker_gate
        ),
        "priorConfigSha256": restoration["priorConfigSha256"],
        "restoredVersion": restoration["restoredVersion"],
        "incumbentBaselineSha256": canonical_sha256(baseline),
        "incumbentObservationSha256": canonical_sha256(baseline),
        "cleanupSha256": canonical_sha256(cleanup),
        "completedAtUtc": "2026-07-25T00:05:00Z",
    }
    controller.write_private_json(terminal_path, terminal)
    return config, terminal, state


def test_post_marker_connector_gate_precedes_cleanup_and_is_immutable(
    tmp_path: Path,
) -> None:
    (
        actions,
        config,
        authorization,
        restoration,
        retirement_evidence,
        retired_authority,
    ) = post_marker_connector_actions(tmp_path)
    observed: list[tuple[bool, bool]] = []
    gates = [
        retirement_connector_gate(13, "connector-post-marker"),
        retirement_connector_gate(13, "connector-added-on-resume"),
    ]

    def converge(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        observed.append(
            (
                config.active_runtime_authority.exists(),
                config.retired_active_authority.exists(),
            )
        )
        return gates[len(observed) - 1]

    actions.cloudflare.poll_current_connector_convergence = converge

    first = actions.verify_retired_authority_connectors(
        config,
        authorization,
        restoration,
        retirement_evidence,
        retired_authority,
    )
    immutable_first = json.loads(json.dumps(first))
    second = actions.verify_retired_authority_connectors(
        config,
        authorization,
        restoration,
        retirement_evidence,
        retired_authority,
    )

    receipts = actions._state["receipts"]
    assert observed == [(False, True), (False, True)]
    assert first["boundary"] == "post-marker"
    assert second["boundary"] == "resume-post-marker"
    assert (
        receipts["retirementPostMarkerConnectorGate"]
        == immutable_first
    )
    assert receipts["retirementConnectorResumeGate"] == second
    assert first["connectorConvergence"] != second[
        "connectorConvergence"
    ]


def test_post_marker_connector_receipt_crash_is_safely_resumable(
    tmp_path: Path,
) -> None:
    (
        actions,
        config,
        authorization,
        restoration,
        retirement_evidence,
        retired_authority,
    ) = post_marker_connector_actions(tmp_path)
    convergence = retirement_connector_gate(
        13,
        "connector-post-marker",
    )
    attempts = 0
    actions.cloudflare.poll_current_connector_convergence = (
        lambda *_args, **_kwargs: convergence
    )
    durable_record = actions._record

    def fail_once(
        phase: str,
        name: str,
        receipt: dict[str, Any],
    ) -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise OSError("simulated crash before post-marker receipt")
        durable_record(phase, name, receipt)

    actions._record = fail_once

    with pytest.raises(
        controller.RecoveryUncertain,
        match="could not become durable",
    ):
        actions.verify_retired_authority_connectors(
            config,
            authorization,
            restoration,
            retirement_evidence,
            retired_authority,
        )

    assert config.retired_active_authority.exists()
    assert not config.active_runtime_authority.exists()
    assert (
        "retirementPostMarkerConnectorGate"
        not in actions._state["receipts"]
    )

    resumed = actions.verify_retired_authority_connectors(
        config,
        authorization,
        restoration,
        retirement_evidence,
        retired_authority,
    )

    assert resumed["boundary"] == "post-marker"
    assert (
        actions._state["receipts"]
        ["retirementPostMarkerConnectorGate"]
        == resumed
    )
    assert attempts == 2


def test_retirement_cleanup_requires_durable_post_marker_gate(
    tmp_path: Path,
) -> None:
    (
        actions,
        config,
        authorization,
        restoration,
        retirement_evidence,
        retired_authority,
    ) = post_marker_connector_actions(tmp_path)
    config.operation = controller.RETIRE_OPERATION
    convergence = retirement_connector_gate(
        13,
        "connector-post-marker",
    )
    actions.cloudflare.poll_current_connector_convergence = (
        lambda *_args, **_kwargs: convergence
    )

    with pytest.raises(
        controller.RecoveryUncertain,
        match="connector boundary receipt drifted",
    ):
        actions._require_retirement_cleanup_connector_gate(
            config,
            actions._state["receipts"],
        )

    actions.verify_retired_authority_connectors(
        config,
        authorization,
        restoration,
        retirement_evidence,
        retired_authority,
    )

    actions._require_retirement_cleanup_connector_gate(
        config,
        actions._state["receipts"],
    )


def test_retirement_does_not_move_authority_before_connector_convergence(
    tmp_path: Path,
) -> None:
    authority_root = tmp_path / "authority"
    operation_root = tmp_path / "operation"
    authority_root.mkdir(mode=0o700)
    operation_root.mkdir(mode=0o700)
    active = authority_root / "active.json"
    retired = operation_root / "retired.json"
    evidence_path = operation_root / "retirement-evidence.json"
    authority_raw = b'{"authority":"exact"}\n'
    evidence_raw = b'{"retirement":"proved"}\n'
    active.write_bytes(authority_raw)
    evidence_path.write_bytes(evidence_raw)
    active.chmod(0o600)
    evidence_path.chmod(0o600)
    config = SimpleNamespace(
        active_runtime_authority=active,
        retired_active_authority=retired,
        cloudflare_retirement_evidence=evidence_path,
        cloudflare_lock=operation_root / "cloudflare.lock",
        operation_root=operation_root,
    )
    authorization = {
        "activeAuthoritySha256": hashlib.sha256(
            authority_raw
        ).hexdigest()
    }
    restoration = {"restoredVersion": 13}
    retirement_evidence = {
        "priorConfigSha256": "1" * 64,
        "restoredVersion": 13,
        "evidenceSha256": hashlib.sha256(evidence_raw).hexdigest(),
    }
    actions = object.__new__(controller.TopologyBActions)
    actions._state = {
        "receipts": {
            "retirementAuthorization": authorization,
            "cloudflareRetirement": restoration,
            "retirementEvidence": retirement_evidence,
        }
    }
    actions._load_retirement_authority = (
        lambda _config: (authority_raw, {}, active)
    )
    actions._cloudflare_api = lambda: RetirementTestApi(
        SimpleNamespace(sha256="1" * 64, version=13)
    )

    def unstable_connectors(
        *_args: Any,
        **_kwargs: Any,
    ) -> dict[str, Any]:
        assert active.exists()
        assert not retired.exists()
        raise RuntimeError("connector set never stabilized")

    actions.cloudflare = SimpleNamespace(
        ExclusiveFileLock=RetirementTestLock,
        parse_configuration_response=lambda response: response,
        poll_current_connector_convergence=unstable_connectors,
    )

    with pytest.raises(
        controller.RecoveryUncertain,
        match="authority retirement is uncertain",
    ):
        actions.retire_active_authority(
            config,
            authorization,
            restoration,
            retirement_evidence,
        )

    assert active.read_bytes() == authority_raw
    assert not retired.exists()
    assert "retirementConnectorGate" not in actions._state["receipts"]
    assert "retiredAuthority" not in actions._state["receipts"]


def test_terminal_retirement_binds_marker_post_marker_and_latest_gates(
    tmp_path: Path,
) -> None:
    operation_root = tmp_path / "operation"
    authority_root = tmp_path / "authority"
    operation_root.mkdir(mode=0o700)
    authority_root.mkdir(mode=0o700)
    active = authority_root / "active.json"
    retired = operation_root / "retired.json"
    evidence_path = operation_root / "retirement-evidence.json"
    terminal_path = operation_root / "retirement.json"
    retired_raw = b'{"authority":"retired"}\n'
    evidence_raw = b'{"evidence":"committed"}\n'
    retired.write_bytes(retired_raw)
    evidence_path.write_bytes(evidence_raw)
    retired.chmod(0o600)
    evidence_path.chmod(0o600)
    config = SimpleNamespace(
        active_runtime_authority=active,
        retired_active_authority=retired,
        cloudflare_retirement_evidence=evidence_path,
        cloudflare_lock=operation_root / "cloudflare.lock",
        retirement_receipt=terminal_path,
        operation_root=operation_root,
        project_name="retirement-contract-test",
        source_head="a" * 40,
        controller_source_head="b" * 40,
    )
    marker_gate = retirement_connector_gate(
        13,
        "connector-at-marker",
    )
    post_marker_convergence = retirement_connector_gate(
        13,
        "connector-after-marker",
    )
    latest_convergence = retirement_connector_gate(
        13,
        "connector-before-cleanup",
    )

    def canonical_sha256(value: Any) -> str:
        return hashlib.sha256(
            json.dumps(
                value,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()

    authorization = {"authorization": "durable"}
    restoration = {
        "priorConfigSha256": "1" * 64,
        "restoredVersion": 13,
    }
    retirement_evidence = {"evidence": "durable"}
    retired_authority = {
        "connectorGateSha256": canonical_sha256(marker_gate)
    }
    retired_authority_sha256 = hashlib.sha256(retired_raw).hexdigest()
    post_marker_gate = retirement_connector_boundary(
        operation_root=operation_root,
        boundary="post-marker",
        version=13,
        retired_authority_sha256=retired_authority_sha256,
        marker_gate=marker_gate,
        convergence=post_marker_convergence,
    )
    latest_gate = retirement_connector_boundary(
        operation_root=operation_root,
        boundary="resume-post-marker",
        version=13,
        retired_authority_sha256=retired_authority_sha256,
        marker_gate=marker_gate,
        convergence=latest_convergence,
        verified_at="2026-07-25T00:05:00Z",
    )
    incumbent = {"incumbent": "exact"}
    cleanup = {"cleanup": "exact"}
    actions = object.__new__(controller.TopologyBActions)
    actions._state = {
        "receipts": {
            "retirementAuthorization": authorization,
            "cloudflareRetirement": restoration,
            "retirementEvidence": retirement_evidence,
            "retiredAuthority": retired_authority,
            "cleanup": cleanup,
            "retirementConnectorGate": marker_gate,
            "retirementPostMarkerConnectorGate": post_marker_gate,
            "retirementConnectorResumeGate": latest_gate,
        }
    }
    actions._load_retirement_authority = (
        lambda _config: (retired_raw, {}, retired)
    )
    actions._validated_retirement_baseline = lambda: incumbent
    actions._cloudflare_api = lambda: RetirementTestApi(
        SimpleNamespace(sha256="1" * 64, version=13)
    )
    actions.cloudflare = SimpleNamespace(
        ExclusiveFileLock=RetirementTestLock,
        parse_configuration_response=lambda response: response,
        validate_current_connector_convergence_receipt=(
            lambda value: value
        ),
        canonical_sha256=canonical_sha256,
    )

    def record(
        phase: str,
        name: str,
        receipt: dict[str, Any],
    ) -> None:
        actions._state["phase"] = phase
        actions._state["receipts"][name] = receipt

    actions._record = record

    terminal = actions.finalize_committed_retirement(
        config,
        authorization,
        restoration,
        retirement_evidence,
        retired_authority,
        incumbent,
        cleanup,
    )

    assert terminal["connectorGateSha256"] == canonical_sha256(
        marker_gate
    )
    assert terminal[
        "postMarkerConnectorGateSha256"
    ] == canonical_sha256(post_marker_gate)
    assert terminal["latestConnectorGateSha256"] == canonical_sha256(
        latest_gate
    )
    assert (
        terminal["connectorGateSha256"]
        != terminal["latestConnectorGateSha256"]
    )
    assert json.loads(terminal_path.read_text(encoding="utf-8")) == terminal


def test_terminal_receipt_write_interruption_is_adopted_before_reverify(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config, terminal, _state = terminal_adoption_fixture(tmp_path)
    config.controller_source_head = "c" * 40
    terminal_raw = config.retirement_receipt.read_bytes()

    def unexpected_action_construction(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError(
            "terminal adoption must precede provider action construction"
        )

    monkeypatch.setattr(
        controller,
        "TopologyBActions",
        unexpected_action_construction,
    )

    resumed = controller.retire_topology_b(config)
    adopted_journal_raw = config.operation_journal.read_bytes()
    repeated = controller.retire_topology_b(config)

    assert resumed["terminalReceipt"] == terminal
    assert resumed["controllerSourceHead"] == "b" * 40
    assert repeated == resumed
    assert config.retirement_receipt.read_bytes() == terminal_raw
    assert config.operation_journal.read_bytes() == adopted_journal_raw
    adopted = json.loads(adopted_journal_raw)
    assert adopted["phase"] == "retired"
    assert adopted["receipts"]["retirement"] == terminal
    assert (
        "retirementRestorationConnectorResumeGate"
        not in adopted["receipts"]
    )
    assert (
        "retirementConnectorResumeGate" not in adopted["receipts"]
    )


@pytest.mark.parametrize(
    "mutation,match",
    (
        ("terminal", "terminal topology-B retirement receipt drifted"),
        (
            "missing-cleanup",
            "terminal topology-B retirement lacks durable boundary receipts",
        ),
        (
            "retired-authority",
            "terminal topology-B retired authority journal drifted",
        ),
    ),
)
def test_terminal_receipt_adoption_rejects_tampering_or_incomplete_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
    match: str,
) -> None:
    config, _terminal, _state = terminal_adoption_fixture(tmp_path)
    if mutation == "terminal":
        tampered = json.loads(
            config.retirement_receipt.read_text(encoding="utf-8")
        )
        tampered["latestConnectorGateSha256"] = "0" * 64
        controller.write_private_json(
            config.retirement_receipt,
            tampered,
            replace=True,
        )
    elif mutation == "missing-cleanup":
        incomplete = json.loads(
            config.operation_journal.read_text(encoding="utf-8")
        )
        del incomplete["receipts"]["cleanup"]
        controller.write_private_json(
            config.operation_journal,
            incomplete,
            replace=True,
        )
    else:
        config.retired_active_authority.write_text(
            '{"tampered":true}\n',
            encoding="utf-8",
        )
        config.retired_active_authority.chmod(0o600)
    journal_raw = config.operation_journal.read_bytes()

    def unexpected_action_construction(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError(
            "invalid terminal authority must fail before live actions"
        )

    monkeypatch.setattr(
        controller,
        "TopologyBActions",
        unexpected_action_construction,
    )

    with pytest.raises(
        controller.RecoveryUncertain,
        match=match,
    ):
        controller.retire_topology_b(config)

    assert config.operation_journal.read_bytes() == journal_raw


def test_retirement_cleanup_reconstructs_original_runtime_inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded = {
        "CHUMMER_PUBLIC_DOWNLOAD_FLEET_SOURCE": "/recorded/fleet",
        "CHUMMER_PUBLIC_DOWNLOAD_FLEET_SHA256": "1" * 64,
            "CHUMMER_PUBLIC_EDGE_PROJECTION_SNAPSHOT_ROOT": (
                "/recorded/projection"
            ),
            "CHUMMER_PUBLIC_EDGE_PROJECTION_CURRENT_SHA256": "5" * 64,
            "CHUMMER_PUBLIC_EDGE_PROJECTION_SNAPSHOT_ID": (
                "public-projection-" + ("6" * 64)
            ),
            "CHUMMER_PUBLIC_EDGE_PROJECTION_SNAPSHOT_SHA256": "2" * 64,
        "CHUMMER_PUBLIC_EDGE_RUNTIME_PROOF_BIND_SOURCE": (
            "/recorded/projection/proof.json"
        ),
        "CHUMMER_PUBLIC_EDGE_RUNTIME_PROOF_BIND_SOURCE_SHA256": "3" * 64,
        "CHUMMER_PUBLIC_DOWNLOAD_FINAL_GOLD_SOURCE": (
            "/recorded/final-gold.json"
        ),
        "CHUMMER_PUBLIC_DOWNLOAD_FINAL_GOLD_SHA256": "4" * 64,
    }
    config = SimpleNamespace(
        operation=controller.RETIRE_OPERATION,
        project_name="chummer-public-download-retirement-cleanup",
        volume_names={},
        fleet_source=Path("/placeholder/fleet"),
        fleet_sha256="0" * 64,
            projection_snapshot_root=Path("/placeholder/projection"),
            projection_authority_root=Path("/placeholder"),
            projection_current_sha256="0" * 64,
            projection_snapshot_id="public-projection-" + ("0" * 64),
            projection_snapshot_sha256="0" * 64,
            projection_source_tree_sha256="0" * 64,
        runtime_proof_source=Path("/placeholder/proof.json"),
        runtime_proof_sha256="0" * 64,
        final_gold_source=Path("/placeholder/final-gold.json"),
        final_gold_sha256="0" * 64,
    )
    runtime = {"environment": recorded}
    actions = object.__new__(controller.TopologyBActions)
    actions._state = {"receipts": {"runtime": runtime}}
    actions.runner = SimpleNamespace(
        compose=lambda *_args, **_kwargs: b"",
    )
    observed: dict[str, Any] = {}
    connector_gate_checks: list[dict[str, Any]] = []
    actions._require_retirement_cleanup_connector_gate = (
        lambda _config, receipts: connector_gate_checks.append(
            dict(receipts)
        )
    )

    def fake_replace(
        original: SimpleNamespace,
        **changes: Any,
    ) -> SimpleNamespace:
        values = vars(original).copy()
        values.update(changes)
        return SimpleNamespace(**values)

    monkeypatch.setattr(controller, "dataclass_replace", fake_replace)

    def validate(
        cleanup_config: SimpleNamespace,
        _runtime: dict[str, Any],
        _receipts: dict[str, Any],
        *,
        historical_source: bool,
    ) -> tuple[dict[str, str], str]:
        assert historical_source is True
        observed.update(vars(cleanup_config))
        return recorded, "5" * 64

    actions._validated_runtime_environment = validate
    actions._preflight_candidate_image = lambda _config: {
        "disposition": "not-bound"
    }
    actions._sidecar_container_references = (
        lambda *_args, **_kwargs: []
    )
    actions._prove_zero_sidecar_project_networks = (
        lambda *_args, **_kwargs: None
    )
    actions._prove_rendered_compose_unchanged = (
        lambda *_args, **_kwargs: None
    )
    actions._prove_sidecar_resources_unreferenced = (
        lambda *_args, **_kwargs: None
    )
    actions._remove_candidate_image = lambda value: dict(value)
    actions._record = lambda *_args, **_kwargs: None

    actions.cleanup_sidecar_resources(config)

    assert observed["operation"] == controller.CUTOVER_OPERATION
    assert observed["fleet_source"] == Path("/recorded/fleet")
    assert observed["fleet_sha256"] == "1" * 64
    assert observed["projection_authority_root"] == Path(
        "/recorded/projection"
    )
    assert observed["projection_snapshot_root"] == Path(
        "/recorded/projection/public-projection-" + ("6" * 64)
    )
    assert observed["projection_current_sha256"] == "5" * 64
    assert observed["projection_snapshot_id"] == (
        "public-projection-" + ("6" * 64)
    )
    assert observed["projection_snapshot_sha256"] == "6" * 64
    assert observed["projection_source_tree_sha256"] == "2" * 64
    assert observed["runtime_proof_source"] == Path(
        "/recorded/projection/proof.json"
    )
    assert observed["runtime_proof_sha256"] == "3" * 64
    assert observed["final_gold_source"] == Path(
        "/recorded/final-gold.json"
    )
    assert observed["final_gold_sha256"] == "4" * 64
    assert connector_gate_checks == [{"runtime": runtime}]


def test_retirement_cleanup_validates_deleted_source_from_operation_commit(
    tmp_path: Path,
) -> None:
    config = cleanup_test_config(tmp_path)
    config.source_head = controller.subprocess.run(
        [
            "/usr/bin/git",
            "-C",
            str(ROOT),
            "rev-parse",
            "--verify",
            "HEAD^{commit}",
        ],
        check=True,
        stdout=controller.subprocess.PIPE,
        text=True,
    ).stdout.strip()
    receipts = complete_runtime_receipts(config)
    removed_source = tmp_path / "removed-sealed-source"
    assert not removed_source.exists()
    materialization = json.loads(
        config.materialization_receipt.read_text(encoding="utf-8")
    )
    materialization["sourceRoot"] = str(removed_source)
    materialization["baseComposeSource"] = str(
        removed_source / "docker-compose.public-edge.yml"
    )
    materialization["profileSource"] = str(
        removed_source / "docker-compose.public-downloads.yml"
    )
    config.materialization_receipt.write_text(
        json.dumps(materialization, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    config.materialization_receipt.chmod(0o600)
    attestation = json.loads(
        config.runtime_attestation.read_text(encoding="utf-8")
    )
    attestation["sourceRoot"] = str(removed_source)
    config.runtime_attestation.write_text(
        json.dumps(attestation, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    config.runtime_attestation.chmod(0o600)
    actions = object.__new__(controller.TopologyBActions)
    actions._state = {
        "operation": controller.CUTOVER_OPERATION,
        "receipts": receipts,
    }

    environment, rendered = actions._validated_runtime_environment(
        config,
        receipts["runtime"],
        receipts,
        historical_source=True,
    )

    assert environment == receipts["runtime"]["environment"]
    assert rendered == hashlib.sha256(b"").hexdigest()
    assert not removed_source.exists()


def test_retirement_is_the_only_marker_retirement_route() -> None:
    retirement = class_method_node(
        "TopologyBActions",
        "retire_active_authority",
    )
    recovery = function_node("recover_topology_b")
    assert "replace" in call_leaf_names(retirement)
    assert "unlink" not in call_leaf_names(retirement)
    assert "retire_active_authority" not in call_leaf_names(recovery)


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


def windows_only_artifact_binding_fixture(
    tmp_path: Path,
) -> dict[str, Any]:
    generation_id = "generation-windows-fixture"
    generation_root = tmp_path / generation_id
    generation_files = generation_root / "files"
    generation_files.mkdir(parents=True)
    file_bytes = {
        "chummer-avalonia-win-x64-installer.exe": b"MZwindows-fixture",
        "chummer-avalonia-win-x64-payload.zip": b"PK\x03\x04windows-fixture",
        "chummer-avalonia-win-x64-payload.zip.json": (
            b'{"contractName":"windows-fixture"}\n'
        ),
    }
    for name, raw in file_bytes.items():
        (generation_files / name).write_bytes(raw)
    installer_name, payload_name, _sidecar_name = file_bytes
    artifact = {
        "artifactId": "avalonia-win-x64-installer",
        "id": "avalonia-win-x64-installer",
        "platform": "windows",
        "rid": "win-x64",
        "fileName": installer_name,
        "downloadUrl": (
            f"/downloads/g/{generation_id}/files/{installer_name}"
        ),
        "sha256": hashlib.sha256(file_bytes[installer_name]).hexdigest(),
        "sizeBytes": len(file_bytes[installer_name]),
        "installAccessClass": "open_public",
        "payloadFileName": payload_name,
        "payloadDownloadUrl": (
            f"/downloads/g/{generation_id}/install/"
            "avalonia-win-x64-installer/payload"
        ),
        "payloadSha256": hashlib.sha256(
            file_bytes[payload_name]
        ).hexdigest(),
        "payloadSizeBytes": len(file_bytes[payload_name]),
    }
    canonical = {
        "generationId": generation_id,
        "artifacts": [dict(artifact)],
    }
    compatibility = {
        "generationId": generation_id,
        "downloads": [
            {
                **artifact,
                "url": artifact["downloadUrl"],
            }
        ],
    }
    fresh_rows = [
        {
            "kind": (
                "installer"
                if name.endswith("-installer.exe")
                else "sidecar"
                if name.endswith(".json")
                else "payload"
            ),
            "path": f"/downloads/files/{name}",
            "sha256": hashlib.sha256(raw).hexdigest(),
            "sizeBytes": len(raw),
        }
        for name, raw in file_bytes.items()
    ]
    result = {
        "generationId": generation_id,
        "generationRoot": generation_root,
        "fileBytes": file_bytes,
        "canonical": canonical,
        "compatibility": compatibility,
        "freshRows": fresh_rows,
    }
    write_artifact_binding_manifests(result)
    return result


def write_artifact_binding_manifests(fixture: dict[str, Any]) -> None:
    generation_root = fixture["generationRoot"]
    (generation_root / "RELEASE_CHANNEL.generated.json").write_text(
        json.dumps(fixture["canonical"]),
        encoding="utf-8",
    )
    (generation_root / "releases.json").write_text(
        json.dumps(fixture["compatibility"]),
        encoding="utf-8",
    )


def test_artifact_host_gate_accepts_exact_windows_only_open_public_zero_denials(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    require_topology_b_surface()
    generation_id = "generation-windows-only"
    generation_root = tmp_path / generation_id
    generation_files = generation_root / "files"
    generation_files.mkdir(parents=True)
    file_bytes = {
        "chummer-avalonia-win-x64-installer.exe": b"MZwindows-installer",
        "chummer-avalonia-win-x64-payload.zip": b"PK\x03\x04windows-payload",
        "chummer-avalonia-win-x64-payload.zip.json": (
            b'{"contractName":"windows-payload"}\n'
        ),
    }
    for name, raw in file_bytes.items():
        (generation_files / name).write_bytes(raw)
    installer_name, payload_name, _sidecar_name = file_bytes
    artifact = {
        "artifactId": "avalonia-win-x64-installer",
        "id": "avalonia-win-x64-installer",
        "platform": "windows",
        "rid": "win-x64",
        "fileName": installer_name,
        "downloadUrl": (
            f"/downloads/g/{generation_id}/files/{installer_name}"
        ),
        "sha256": hashlib.sha256(file_bytes[installer_name]).hexdigest(),
        "sizeBytes": len(file_bytes[installer_name]),
        "installAccessClass": "open_public",
        "payloadFileName": payload_name,
        "payloadDownloadUrl": (
            f"/downloads/g/{generation_id}/install/"
            "avalonia-win-x64-installer/payload"
        ),
        "payloadSha256": hashlib.sha256(
            file_bytes[payload_name]
        ).hexdigest(),
        "payloadSizeBytes": len(file_bytes[payload_name]),
    }
    (generation_root / "RELEASE_CHANNEL.generated.json").write_text(
        json.dumps(
            {
                "generationId": generation_id,
                "artifacts": [artifact],
            }
        ),
        encoding="utf-8",
    )
    (generation_root / "releases.json").write_text(
        json.dumps(
            {
                "generationId": generation_id,
                "downloads": [
                    {
                        **artifact,
                        "url": artifact["downloadUrl"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    fresh_paths = tuple(f"files/{name}" for name in file_bytes)
    shelf = {
        "generationId": generation_id,
        "generationRoot": str(generation_root),
        "releaseCandidateAuthority": {
            "freshDelta": [
                {
                    "path": path,
                    "sha256": hashlib.sha256(
                        file_bytes[Path(path).name]
                    ).hexdigest(),
                    "sizeBytes": len(file_bytes[Path(path).name]),
                }
                for path in fresh_paths
            ]
        },
    }
    streamed: list[dict[str, Any]] = []

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

    monkeypatch.setattr(controller, "_stream_exact_download", fake_stream)
    monkeypatch.setattr(
        controller,
        "_probe_denied_download",
        lambda **_kwargs: pytest.fail(
            "Windows-only open-public shelf must not invent a denial probe"
        ),
    )

    receipt = controller.probe_download_artifact_hosts(
        SimpleNamespace(base_url="https://chummer.run"),
        shelf=shelf,
        scope="local",
    )

    assert receipt["status"] == "pass"
    assert len(streamed) == len(HOSTS) * len(file_bytes) * 2
    assert receipt["accountRequiredDenials"] == []
    assert receipt["accountRequiredDenialClosure"] == {
        "status": "pass",
        "accountRequiredArtifactCount": 0,
        "bindingCount": 0,
        "expectedObservationCount": 0,
        "observedObservationCount": 0,
        "sealedGenerationFileCount": 3,
        "freshFileCount": 3,
        "zeroCountProved": True,
    }


@pytest.mark.parametrize(
    "case",
    (
        "missing_access",
        "padded_access",
        "unknown_access",
        "conflicting_access_alias",
        "non_object_row",
        "duplicate_id",
        "duplicate_path",
        "alias_conflict",
        "unexpected_canonical_collection",
        "unexpected_compatibility_collection",
        "generation_drift",
        "compatibility_access_drift",
        "compatibility_identity_drift",
        "compatibility_sha_drift",
        "compatibility_size_drift",
        "compatibility_payload_omission",
        "absolute_url",
        "bad_port_url",
        "encoded_url",
        "query_url",
        "control_url",
        "raw_files_metadata_url",
        "duplicate_json_key",
        "extra_file",
        "missing_file",
        "symlink_file",
        "fresh_sha_drift",
        "fresh_size_drift",
    ),
)
def test_retained_binding_closure_rejects_manifest_and_file_bypasses(
    tmp_path: Path,
    case: str,
) -> None:
    fixture = windows_only_artifact_binding_fixture(tmp_path)
    canonical_row = fixture["canonical"]["artifacts"][0]
    compatibility_row = fixture["compatibility"]["downloads"][0]
    if case == "missing_access":
        canonical_row.pop("installAccessClass")
        compatibility_row.pop("installAccessClass")
    elif case == "padded_access":
        canonical_row["installAccessClass"] = " open_public"
        compatibility_row["installAccessClass"] = " open_public"
    elif case == "unknown_access":
        canonical_row["installAccessClass"] = "public"
        compatibility_row["installAccessClass"] = "public"
    elif case == "conflicting_access_alias":
        canonical_row["install_access_class"] = "account_required"
        compatibility_row["install_access_class"] = "account_required"
    elif case == "non_object_row":
        fixture["canonical"]["artifacts"] = ["not-an-object"]
    elif case == "duplicate_id":
        fixture["canonical"]["artifacts"].append(dict(canonical_row))
    elif case == "duplicate_path":
        duplicate = {
            **canonical_row,
            "artifactId": "duplicate-win-x64-installer",
            "id": "duplicate-win-x64-installer",
            "payloadDownloadUrl": (
                f"/downloads/g/{fixture['generationId']}/install/"
                "duplicate-win-x64-installer/payload"
            ),
        }
        fixture["canonical"]["artifacts"].append(duplicate)
    elif case == "alias_conflict":
        canonical_row["id"] = "conflicting-artifact-id"
    elif case == "unexpected_canonical_collection":
        fixture["canonical"]["downloads"] = [
            {
                **canonical_row,
                "installAccessClass": "account_required",
            }
        ]
    elif case == "unexpected_compatibility_collection":
        fixture["compatibility"]["artifacts"] = [
            {
                **compatibility_row,
                "installAccessClass": "account_required",
            }
        ]
    elif case == "generation_drift":
        fixture["canonical"]["generationId"] = "other-generation"
        fixture["compatibility"]["generationId"] = "other-generation"
    elif case == "compatibility_access_drift":
        compatibility_row["installAccessClass"] = "account_required"
    elif case == "compatibility_identity_drift":
        compatibility_row["artifactId"] = "other-win-installer"
        compatibility_row["id"] = "other-win-installer"
    elif case == "compatibility_sha_drift":
        compatibility_row["sha256"] = "f" * 64
    elif case == "compatibility_size_drift":
        compatibility_row["sizeBytes"] += 1
    elif case == "compatibility_payload_omission":
        for key in (
            "payloadFileName",
            "payloadDownloadUrl",
            "payloadSha256",
            "payloadSizeBytes",
        ):
            compatibility_row.pop(key)
    elif case in {
        "absolute_url",
        "bad_port_url",
        "encoded_url",
        "query_url",
        "control_url",
    }:
        original = str(canonical_row["downloadUrl"])
        mutated = {
            "absolute_url": f"https://chummer.run{original}",
            "bad_port_url": f"https://chummer.run:bad{original}",
            "encoded_url": original.replace(
                "/downloads/",
                "/downloads%2f",
            ),
            "query_url": f"{original}?ticket=secret",
            "control_url": f"{original}\n",
        }[case]
        canonical_row["downloadUrl"] = mutated
        compatibility_row["downloadUrl"] = mutated
        compatibility_row["url"] = mutated
    elif case == "raw_files_metadata_url":
        sidecar_name = (
            "chummer-avalonia-win-x64-payload.zip.json"
        )
        for row in (canonical_row, compatibility_row):
            row["payloadMetadataFileName"] = sidecar_name
            row["payloadMetadataUrl"] = (
                f"/downloads/g/{fixture['generationId']}/files/"
                f"{sidecar_name}"
            )
    elif case == "extra_file":
        (
            fixture["generationRoot"]
            / "files"
            / "unbound-secret.bin"
        ).write_bytes(b"unbound")
    elif case == "missing_file":
        (
            fixture["generationRoot"]
            / "files"
            / "chummer-avalonia-win-x64-payload.zip.json"
        ).unlink()
    elif case == "symlink_file":
        sidecar = (
            fixture["generationRoot"]
            / "files"
            / "chummer-avalonia-win-x64-payload.zip.json"
        )
        sidecar.unlink()
        sidecar.symlink_to(
            fixture["generationRoot"]
            / "files"
            / "chummer-avalonia-win-x64-payload.zip"
        )
    elif case == "fresh_sha_drift":
        fixture["freshRows"][0]["sha256"] = "f" * 64
    elif case == "fresh_size_drift":
        fixture["freshRows"][0]["sizeBytes"] += 1

    write_artifact_binding_manifests(fixture)
    if case == "duplicate_json_key":
        (
            fixture["generationRoot"]
            / "RELEASE_CHANNEL.generated.json"
        ).write_text(
            (
                '{"generationId":"'
                f'{fixture["generationId"]}",'
                '"generationId":"duplicate","artifacts":[]}'
            ),
            encoding="utf-8",
        )

    with pytest.raises(controller.CutoverError):
        controller._retained_account_required_bindings(
            config=SimpleNamespace(base_url="https://chummer.run"),
            generation_root=fixture["generationRoot"],
            fresh_rows=fixture["freshRows"],
        )


def test_retained_binding_closure_accepts_unambiguous_snake_case_access_alias(
    tmp_path: Path,
) -> None:
    fixture = windows_only_artifact_binding_fixture(tmp_path)
    for row in (
        fixture["canonical"]["artifacts"][0],
        fixture["compatibility"]["downloads"][0],
    ):
        row["install_access_class"] = row.pop("installAccessClass")
    write_artifact_binding_manifests(fixture)

    bindings, closure = controller._retained_account_required_bindings(
        config=SimpleNamespace(base_url="https://chummer.run"),
        generation_root=fixture["generationRoot"],
        fresh_rows=fixture["freshRows"],
    )

    assert bindings == []
    assert closure["accountRequiredArtifactCount"] == 0
    assert closure["zeroCountProved"] is True


def test_artifact_host_gate_rejects_shelf_and_generation_root_identity_drift(
    tmp_path: Path,
) -> None:
    fixture = windows_only_artifact_binding_fixture(tmp_path)
    shelf = {
        "generationId": "different-generation",
        "generationRoot": str(fixture["generationRoot"]),
        "releaseCandidateAuthority": {
            "freshDelta": [
                {
                    **row,
                    "path": str(row["path"]).removeprefix(
                        "/downloads/"
                    ),
                }
                for row in fixture["freshRows"]
            ]
        },
    }

    with pytest.raises(
        controller.CutoverError,
        match="generation authority",
    ):
        controller.probe_download_artifact_hosts(
            SimpleNamespace(base_url="https://chummer.run"),
            shelf=shelf,
            scope="local",
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
    generation_root = tmp_path / generation_id
    generation_root.mkdir()
    generation_files = generation_root / "files"
    generation_files.mkdir()
    fresh_file_bytes = {
        "chummer-avalonia-win-x64-installer.exe": b"MZfresh-windows",
        "chummer-avalonia-win-x64-payload.zip": b"PK\x03\x04fresh-windows",
        "chummer-avalonia-win-x64-payload.zip.json": (
            b'{"contractName":"fresh-windows"}\n'
        ),
    }
    for file_name, raw in fresh_file_bytes.items():
        (generation_files / file_name).write_bytes(raw)
    fresh_installer_name, fresh_payload_name, _fresh_sidecar = (
        fresh_file_bytes
    )
    open_artifact = {
        "artifactId": "avalonia-win-x64-installer",
        "id": "avalonia-win-x64-installer",
        "platform": "windows",
        "rid": "win-x64",
        "fileName": fresh_installer_name,
        "downloadUrl": (
            f"/downloads/g/{generation_id}/files/{fresh_installer_name}"
        ),
        "sha256": hashlib.sha256(
            fresh_file_bytes[fresh_installer_name]
        ).hexdigest(),
        "sizeBytes": len(fresh_file_bytes[fresh_installer_name]),
        "installAccessClass": "open_public",
        "payloadFileName": fresh_payload_name,
        "payloadDownloadUrl": (
            f"/downloads/g/{generation_id}/install/"
            "avalonia-win-x64-installer/payload"
        ),
        "payloadSha256": hashlib.sha256(
            fresh_file_bytes[fresh_payload_name]
        ).hexdigest(),
        "payloadSizeBytes": len(
            fresh_file_bytes[fresh_payload_name]
        ),
    }
    private_payload_name = "chummer-avalonia-osx-x64-payload.zip"
    private_payload = b"PK\x03\x04private-mac-payload"
    private_sidecar = b'{"contractName":"private-mac-payload"}\n'
    (generation_files / private_payload_name).write_bytes(private_payload)
    (generation_files / f"{private_payload_name}.json").write_bytes(private_sidecar)
    mac_files = {
        "avalonia-osx-x64-installer": (
            "chummer-avalonia-osx-x64-installer.dmg",
            b"protected-avalonia-mac-installer",
        ),
        "blazor-desktop-osx-arm64-installer": (
            "chummer-blazor-desktop-osx-arm64-installer.dmg",
            b"protected-blazor-mac-installer",
        ),
    }
    for mac_file, raw in mac_files.values():
        (generation_files / mac_file).write_bytes(raw)
    protected_artifacts = [
        {
            "artifactId": artifact_id,
            "platform": "macos",
            "rid": (
                "osx-arm64"
                if "arm64" in artifact_id
                else "osx-x64"
            ),
            "fileName": mac_file,
            "downloadUrl": (
                f"/downloads/g/{generation_id}/install/{artifact_id}"
            ),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "sizeBytes": len(raw),
            "installAccessClass": "account_required",
            **(
                {
                    "payloadFileName": private_payload_name,
                    "payloadDownloadUrl": (
                        f"/downloads/g/{generation_id}/install/"
                        f"{artifact_id}/payload"
                    ),
                    "payloadSha256": hashlib.sha256(
                        private_payload
                    ).hexdigest(),
                    "payloadSizeBytes": len(private_payload),
                    "payloadMetadataFileName": (
                        f"{private_payload_name}.json"
                    ),
                    "payloadMetadataUrl": (
                        f"/downloads/g/{generation_id}/install/"
                        f"{artifact_id}/metadata"
                    ),
                }
                if artifact_id == "avalonia-osx-x64-installer"
                else {}
            ),
        }
        for artifact_id, (mac_file, raw) in mac_files.items()
    ]
    all_artifacts = [open_artifact, *protected_artifacts]
    (generation_root / "RELEASE_CHANNEL.generated.json").write_text(
        json.dumps(
            {
                "generationId": generation_id,
                "artifacts": all_artifacts,
            }
        ),
        encoding="utf-8",
    )
    (generation_root / "releases.json").write_text(
        json.dumps(
            {
                "generationId": generation_id,
                "downloads": [
                    {
                        **artifact,
                        "url": artifact["downloadUrl"],
                    }
                    for artifact in all_artifacts
                ],
            }
        ),
        encoding="utf-8",
    )
    fresh_paths = tuple(
        f"files/{file_name}" for file_name in fresh_file_bytes
    )
    shelf = {
        "generationId": generation_id,
        "generationRoot": str(generation_root),
        "releaseCandidateAuthority": {
            "freshDelta": [
                {
                    "path": path,
                    "sha256": hashlib.sha256(
                        fresh_file_bytes[Path(path).name]
                    ).hexdigest(),
                    "sizeBytes": len(
                        fresh_file_bytes[Path(path).name]
                    ),
                }
                for path in fresh_paths
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
    assert receipt["accountRequiredDenialClosure"] == {
        "status": "pass",
        "accountRequiredArtifactCount": 2,
        "bindingCount": 4,
        "expectedObservationCount": 16,
        "observedObservationCount": 16,
        "sealedGenerationFileCount": 7,
        "freshFileCount": 3,
        "zeroCountProved": False,
    }
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
    public_probe = class_method_node(
        "TopologyBActions",
        "_verify_public_downloads",
    )
    public_calls = call_leaf_names_in_source_order(public_probe)
    assert "probe_download_artifact_hosts" in public_calls
    assert public_calls.index(
        "_wait_for_public_generation_convergence"
    ) < public_calls.index("python")
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
