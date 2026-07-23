from __future__ import annotations

import importlib.util
import hashlib
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


FRESH_WINDOWS_PATHS = (
    "files/chummer-avalonia-win-x64-installer.exe",
    "files/chummer-avalonia-win-x64-payload.zip",
    "files/chummer-avalonia-win-x64-payload.zip.json",
)


def release_candidate_authority_fixture(
    tmp_path: Path,
    *,
    fresh_digest_override: str | None = None,
    retained_digest_override: str | None = None,
) -> tuple[Any, Any, Any, dict[str, dict[str, Any]]]:
    release_root = tmp_path / "sealed-bundle"
    incumbent_root = tmp_path / "incumbent-candidate"
    projection_root = tmp_path / "projection"
    for root in (release_root, incumbent_root, projection_root):
        (root / "files").mkdir(parents=True)

    canonical = b'{"version":"fresh-windows"}\n'
    compatibility = b'{"version":"fresh-windows","downloads":[]}\n'
    (release_root / "RELEASE_CHANNEL.generated.json").write_bytes(canonical)
    (release_root / "releases.json").write_bytes(compatibility)
    retained_path = "files/retained-linux.tar.zst"
    retained_bytes = b"retained incumbent bytes\n"
    (release_root / retained_path).write_bytes(retained_bytes)
    (incumbent_root / retained_path).write_bytes(retained_bytes)

    release_bytes = {
        FRESH_WINDOWS_PATHS[0]: b"fresh installer bytes\n",
        FRESH_WINDOWS_PATHS[1]: b"fresh payload bytes\n",
        FRESH_WINDOWS_PATHS[2]: b'{"fresh":"payload-sidecar"}\n',
    }
    incumbent_bytes = {
        FRESH_WINDOWS_PATHS[0]: b"old installer bytes\n",
        FRESH_WINDOWS_PATHS[1]: b"old payload bytes\n",
        FRESH_WINDOWS_PATHS[2]: b'{"old":"payload-sidecar"}\n',
    }
    for path, payload in release_bytes.items():
        (release_root / path).write_bytes(payload)
    for path, payload in incumbent_bytes.items():
        (incumbent_root / path).write_bytes(payload)

    def row(path: str, payload: bytes) -> dict[str, Any]:
        return {
            "path": path,
            "sha256": hashlib.sha256(payload).hexdigest(),
            "sizeBytes": len(payload),
        }

    release_rows = [
        row("RELEASE_CHANNEL.generated.json", canonical),
        row("releases.json", compatibility),
        *(row(path, release_bytes[path]) for path in FRESH_WINDOWS_PATHS),
        row(retained_path, retained_bytes),
    ]
    incumbent_rows = [
        row("RELEASE_CHANNEL.generated.json", b"old canonical\n"),
        row("releases.json", b"old compatibility\n"),
        *(row(path, incumbent_bytes[path]) for path in FRESH_WINDOWS_PATHS),
        row(retained_path, retained_bytes),
    ]
    release_modes = {item["path"]: 0o644 for item in release_rows}
    incumbent_modes = {item["path"]: 0o644 for item in incumbent_rows}
    release_with_modes = [
        {**item, "mode": release_modes[item["path"]]}
        for item in release_rows
    ]
    incumbent_with_modes = [
        {**item, "mode": incumbent_modes[item["path"]]}
        for item in incumbent_rows
    ]
    release_by_path = {item["path"]: item for item in release_rows}
    fresh_delta = [
        {
            **release_by_path[path],
            "mode": release_modes[path],
        }
        for path in FRESH_WINDOWS_PATHS
    ]
    if fresh_digest_override is not None:
        fresh_delta[0]["sha256"] = fresh_digest_override
    retained = [
        {
            **release_by_path[retained_path],
            "mode": release_modes[retained_path],
        }
    ]
    if retained_digest_override is not None:
        retained[0]["sha256"] = retained_digest_override

    scope = {
        "fullShelfInventory": release_with_modes,
        "freshDelta": fresh_delta,
        "retainedFromIncumbent": retained,
    }
    registry = {
        "compositionInputDocument": {
            "incumbentSnapshot": {
                "fullShelfInventory": incumbent_with_modes,
                "directoryModes": {"files": 0o755},
            }
        }
    }
    inventory = {"contractName": "fixture"}
    custody = {
        "inventory": {"token": "inventory"},
        "unsignedPublicationEvidence": {
            "files": [{"path": "scope.json", "token": "scope"}],
            "retainedInventorySha256": "8" * 64,
            "incumbentInventorySha256": "9" * 64,
        },
        "registryPrepareCandidateReceipt": {"token": "registry"},
        "canonicalManifest": {"token": "canonical"},
        "compatibilityManifest": {"token": "compatibility"},
    }
    authority = {
        "contractName": (
            "chummer.release-upload.candidate-import-authority/v3"
        ),
        "contractVersion": 3,
        "candidate": {
            "version": "fresh-windows",
            "bundleIdentitySha256": "a" * 64,
            "inventorySha256": "b" * 64,
            "fileCount": len(release_rows),
            "totalBytes": sum(item["sizeBytes"] for item in release_rows),
            "canonicalManifestSha256": hashlib.sha256(canonical).hexdigest(),
        },
        "custody": custody,
    }
    authority_path = projection_root / (
        "RELEASE_UPLOAD_CANDIDATE_AUTHORITY.generated.json"
    )
    authority_path.write_bytes(b"fixture candidate authority\n")
    release_receipt = projection_root / "RELEASE_CHANNEL.generated.json"
    release_receipt.write_bytes(canonical)
    config = SimpleNamespace(
        source_root=ROOT,
        candidate_import_authority=authority_path,
        candidate_import_authority_sha256=hashlib.sha256(
            authority_path.read_bytes()
        ).hexdigest(),
        release_candidate_root=release_root,
        migration_candidate_root=incumbent_root,
        release_channel_receipt=release_receipt,
        release_channel_receipt_sha256=hashlib.sha256(canonical).hexdigest(),
    )

    class ProjectionVerifier:
        CANDIDATE_UNSIGNED_SCOPE_FILE = "scope.json"
        CANDIDATE_REGISTRY_RECEIPT_FILE = "registry.json"

        @staticmethod
        def _validate_candidate_import_authority(_raw: bytes) -> dict[str, Any]:
            return authority

        @staticmethod
        def _candidate_embedded_bytes(
            item: dict[str, Any] | None,
            *,
            label: str,
            expected_path: str,
        ) -> bytes:
            assert item is not None, label
            token = item.get("token")
            return {
                "inventory": b"inventory",
                "scope": b"scope",
                "registry": b"registry",
                "canonical": canonical,
                "compatibility": compatibility,
            }[token]

        @staticmethod
        def _strict_json_object(
            raw: bytes, *, label: str
        ) -> dict[str, Any]:
            return {
                b"inventory": inventory,
                b"scope": scope,
                b"registry": registry,
            }[raw]

    class CandidateMaterializer:
        observed_release_root: Path | None = None

        @classmethod
        def _validate_bundle_inventory(
            cls,
            root: Path,
            *_args: Any,
            **_kwargs: Any,
        ) -> tuple[list[dict[str, Any]], dict[str, int], dict[str, int], list[Any]]:
            cls.observed_release_root = root
            return release_rows, release_modes, {"files": 0o755}, []

        @staticmethod
        def _scan_bundle_tree(
            root: Path,
        ) -> tuple[list[dict[str, Any]], dict[str, int], dict[str, int], list[Any]]:
            assert root == incumbent_root
            return incumbent_rows, incumbent_modes, {"files": 0o755}, []

    return (
        config,
        ProjectionVerifier,
        CandidateMaterializer,
        release_by_path,
    )


def test_v3_authority_binds_exact_candidate_tree_retained_and_fresh_delta(
    tmp_path: Path,
) -> None:
    (
        config,
        projection_verifier,
        candidate_materializer,
        release_by_path,
    ) = release_candidate_authority_fixture(tmp_path)

    receipt = controller.validate_release_candidate_authority(
        config,
        projection_verifier=projection_verifier,
        candidate_materializer=candidate_materializer,
    )

    assert (
        candidate_materializer.observed_release_root
        == config.release_candidate_root
    )
    assert receipt["servingAuthority"] is True
    assert receipt["retainedInventorySha256"] == "8" * 64
    assert receipt["incumbentInventorySha256"] == "9" * 64
    assert {
        item["path"]: (item["sha256"], item["sizeBytes"])
        for item in receipt["freshDelta"]
    } == {
        path: (
            release_by_path[path]["sha256"],
            release_by_path[path]["sizeBytes"],
        )
        for path in FRESH_WINDOWS_PATHS
    }


def test_v3_authority_rejects_fresh_windows_hash_not_in_exact_bundle(
    tmp_path: Path,
) -> None:
    config, projection_verifier, candidate_materializer, _release = (
        release_candidate_authority_fixture(
            tmp_path,
            fresh_digest_override="f" * 64,
        )
    )

    with pytest.raises(controller.CutoverError, match="freshDelta|fresh"):
        controller.validate_release_candidate_authority(
            config,
            projection_verifier=projection_verifier,
            candidate_materializer=candidate_materializer,
        )


def test_v3_authority_rejects_retained_hash_not_in_incumbent(
    tmp_path: Path,
) -> None:
    config, projection_verifier, candidate_materializer, _release = (
        release_candidate_authority_fixture(
            tmp_path,
            retained_digest_override="e" * 64,
        )
    )

    with pytest.raises(controller.CutoverError, match="retained"):
        controller.validate_release_candidate_authority(
            config,
            projection_verifier=projection_verifier,
            candidate_materializer=candidate_materializer,
        )
