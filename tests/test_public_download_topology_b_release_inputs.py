from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace
from typing import Any
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
CONTROLLER_PATH = ROOT / "scripts" / "deploy_public_download_only_cutover.py"
WRAPPER_PATH = ROOT / "scripts" / "deploy_public_edge_portal.sh"


def load_controller() -> Any:
    spec = importlib.util.spec_from_file_location(
        "topology_b_release_input_contract",
        CONTROLLER_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


controller = load_controller()


def projection_fixture(tmp_path: Path) -> tuple[Path, str, str]:
    root = tmp_path / "projection"
    root.mkdir()
    (root / "PUBLIC_PROJECTION_MANIFEST.generated.json").write_text(
        '{"schema":"fixture","snapshotId":"public-projection-semantic"}\n',
        encoding="utf-8",
    )
    (root / "projection.bin").write_bytes(b"projection source bytes\n")
    semantic_sha256 = "fa691b" + "0" * 58
    source_tree_sha256 = controller.tree_sha256_file_stream(
        root,
        label="authentic projection source fixture",
    )
    assert semantic_sha256 != source_tree_sha256
    return root, semantic_sha256, source_tree_sha256


def test_projection_semantic_identity_is_distinct_from_source_tree_digest(
    tmp_path: Path,
) -> None:
    projection_root, semantic_sha256, source_tree_sha256 = projection_fixture(
        tmp_path
    )
    annotations = controller.SidecarConfig.__annotations__
    assert "projection_snapshot_sha256" in annotations
    assert "projection_source_tree_sha256" in annotations

    operation_root = tmp_path / "operation"
    operation_root.mkdir()
    volume_names = {
        logical: f"fixture-{logical}"
        for logical in controller.SIDECAR_LOGICAL_VOLUMES
    }
    config = SimpleNamespace(
        sidecar_certificate=operation_root / "sidecar.pfx",
        sidecar_certificate_password=operation_root / "sidecar.password",
        overlay_staging_root=operation_root / "app",
        fleet_source=operation_root / "fleet",
        fleet_sha256="1" * 64,
        shelf_source=operation_root / "shelf",
        projection_snapshot_root=projection_root,
        projection_snapshot_id=f"public-projection-{semantic_sha256}",
        projection_snapshot_sha256=semantic_sha256,
        projection_source_tree_sha256=source_tree_sha256,
        runtime_proof_source=operation_root / "runtime-proof.json",
        runtime_proof_sha256="2" * 64,
        final_gold_source=operation_root / "final-gold.json",
        final_gold_sha256="3" * 64,
        volume_names=volume_names,
    )

    environment = controller._sidecar_compose_environment(
        config,
        dp={
            "certificateSha256": "4" * 64,
            "passwordSha256": "5" * 64,
        },
        app_overlay_sha256="6" * 64,
        shelf={"shelfTreeSha256": "7" * 64},
    )

    assert config.projection_snapshot_id == (
        f"public-projection-{semantic_sha256}"
    )
    assert environment[
        "CHUMMER_PUBLIC_EDGE_PROJECTION_SNAPSHOT_SHA256"
    ] == source_tree_sha256
    assert source_tree_sha256 != semantic_sha256


def test_wrapper_uses_a_sidecar_only_active_runtime_authority() -> None:
    lines = WRAPPER_PATH.read_text(encoding="utf-8").splitlines()
    authority_argument = next(
        line
        for line in lines
        if "--active-runtime-authority" in line
    )

    assert "CANONICAL_ACTIVE_RUNTIME_AUTHORITY" not in authority_argument
    assert "PUBLIC_DOWNLOAD" in authority_argument
    assert any(
        "PUBLIC_DOWNLOAD" in line
        and "ACTIVE_RUNTIME_AUTHORITY" in line
        and "CANONICAL_ACTIVE_RUNTIME_AUTHORITY" not in line
        for line in lines
    )


def test_wrapper_operation_identity_is_not_source_head_only() -> None:
    script = WRAPPER_PATH.read_text(encoding="utf-8")
    operation_root_lines = [
        line.strip()
        for line in script.splitlines()
        if line.startswith("PUBLIC_DOWNLOAD_OPERATION_ROOT=")
    ]

    assert len(operation_root_lines) == 1
    assert "PUBLIC_DOWNLOAD_OPERATION_ID" in script
    assert "PUBLIC_DOWNLOAD_OPERATION_ID" in operation_root_lines[0]
    assert "${EXPECTED_HEAD,,}" not in operation_root_lines[0]


@pytest.mark.parametrize(
    "api_base",
    (
        "https://attacker.example/client/v4",
        "http://api.cloudflare.com/client/v4",
        "https://api.cloudflare.com/client/v4/",
        "https://api.cloudflare.com/client/v4/extra",
        "https://api.cloudflare.com/client/v4?redirect=attacker.example",
    ),
)
def test_cloudflare_api_base_is_exact_before_any_credential_read(
    api_base: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    credential_touched = False

    def reject_credential_read(*_args: Any, **_kwargs: Any) -> bytes:
        nonlocal credential_touched
        credential_touched = True
        raise AssertionError("credential material was touched")

    monkeypatch.setattr(
        controller,
        "stable_regular_bytes",
        reject_credential_read,
    )
    config = SimpleNamespace(
        operation=controller.CUTOVER_OPERATION,
        source_head="a" * 40,
        shared_lock_token="b" * 64,
        project_name="chummer-public-download-api-test",
        base_url="https://chummer.run",
        cloudflare_account_id="c" * 32,
        cloudflare_tunnel_id="d" * 8 + "-dddd-dddd-dddd-" + "d" * 12,
        cloudflare_api_base=api_base,
        ready_timeout_seconds=0,
    )

    with pytest.raises(controller.CutoverError, match="Cloudflare API base"):
        controller._validate_sidecar_config(config)

    assert credential_touched is False


def test_exact_official_cloudflare_api_base_passes_the_api_boundary() -> None:
    config = SimpleNamespace(
        operation=controller.CUTOVER_OPERATION,
        source_head="a" * 40,
        shared_lock_token="b" * 64,
        project_name="chummer-public-download-api-test",
        base_url="https://chummer.run",
        cloudflare_account_id="c" * 32,
        cloudflare_tunnel_id="d" * 8 + "-dddd-dddd-dddd-" + "d" * 12,
        cloudflare_api_base="https://api.cloudflare.com/client/v4",
        ready_timeout_seconds=0,
    )

    with pytest.raises(controller.CutoverError, match="readiness timeout"):
        controller._validate_sidecar_config(config)
