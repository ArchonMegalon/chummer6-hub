from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import sys
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]


def load_module(relative: str, name: str):
    path = ROOT / relative
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


controller = load_module(
    "scripts/deploy_public_download_only_cutover.py",
    "deploy_public_download_only_cutover_test",
)
generation = load_module(
    "scripts/release_shelf_generation.py",
    "release_shelf_generation_public_download_test",
)
attestor = load_module(
    "scripts/attest_initial_release_shelf_cutover.py",
    "attest_initial_release_shelf_cutover_public_download_test",
)


def test_final_postdeploy_declares_bootstrap_delivery_phase(
    tmp_path: Path,
) -> None:
    output = tmp_path / "postdeploy.json"
    output.write_text('{"status":"pass"}\n', encoding="utf-8")
    calls: list[list[str]] = []

    class FakeRunner:
        def python(self, _script, arguments, **_kwargs):
            calls.append(list(arguments))
            return b""

    receipt = controller.final_postdeploy(
        SimpleNamespace(
            source_root=tmp_path,
            base_url="https://chummer.run",
        ),
        FakeRunner(),
        manifest=tmp_path / "releases.json",
        canonical_manifest=tmp_path / "RELEASE_CHANNEL.generated.json",
        output=output,
    )

    assert receipt == {"status": "pass"}
    assert calls[0][
        calls[0].index("--delivery-phase") : calls[0].index(
            "--delivery-phase"
        )
        + 2
    ] == ["--delivery-phase", "bootstrap"]


def test_candidate_build_uses_only_unique_tag_and_immutable_source_labels(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source"
    (source / "Chummer.Run.Api").mkdir(parents=True)
    build_context = tmp_path / "build"
    (build_context / "chummer-hub-registry").mkdir(parents=True)
    fleet = tmp_path / "fleet-contracts"
    design = tmp_path / "design"
    fleet.mkdir()
    design.mkdir()
    head = "a" * 40
    image_id = "sha256:" + "b" * 64
    calls: list[list[str]] = []

    class FakeRunner:
        def docker(self, arguments, **_kwargs):
            calls.append(list(arguments))
            if arguments[:2] == ["image", "inspect"]:
                build_arguments = calls[0]
                labels = {
                    build_arguments[index + 1].split("=", 1)[0]: (
                        build_arguments[index + 1].split("=", 1)[1]
                    )
                    for index, value in enumerate(build_arguments[:-1])
                    if value == "--label"
                }
                return json.dumps(
                    [
                        {
                            "Id": image_id,
                            "Config": {"Labels": labels},
                        }
                    ]
                ).encode()
            return b""

    monkeypatch.setattr(controller.secrets, "token_hex", lambda _count: "c0ffee12")
    unique_tag, observed_image = controller.build_candidate_image(
        SimpleNamespace(
            source_root=source,
            source_head=head,
            build_context=build_context,
            fleet_media_contracts=fleet,
            design_product_root=design,
        ),
        FakeRunner(),
    )

    assert observed_image == image_id
    assert unique_tag == f"chummer-run-api:public-download-{head[:16]}-c0ffee12"
    build = calls[0]
    assert build[:2] == ["buildx", "build"]
    assert controller.CANONICAL_PORTAL_TAG not in build
    assert controller.CANONICAL_TOOL_TAG not in build
    assert "run.chummer.runtime-profile=public-download-only" in build
    assert f"org.opencontainers.image.revision={head}" in build
    assert sum(
        value.startswith("run.chummer.build-context.")
        and value.endswith(".sha256")
        for value in (
            item.split("=", 1)[0]
            for item in build
            if "=" in item
        )
    ) == 5


def test_candidate_build_rejects_immutable_context_drift_during_build(
    tmp_path: Path,
) -> None:
    contexts = {
        name: tmp_path / name
        for name in (
            "default",
            "run-services",
            "hub-registry",
            "fleet-media",
            "design-product",
        )
    }
    for name, root in contexts.items():
        root.mkdir()
        (root / "input.txt").write_text(f"{name}\n", encoding="utf-8")
    dockerfile = contexts["default"] / "Chummer.Run.Api" / "Dockerfile"
    dockerfile.parent.mkdir()
    dockerfile.write_text("FROM scratch\n", encoding="utf-8")
    context_digests = {
        name: controller._snapshot_inventory(
            path,
            label=f"{name} test context",
        )
        for name, path in contexts.items()
    }
    head = "a" * 40
    image_id = "sha256:" + "b" * 64
    calls: list[list[str]] = []

    class DriftingRunner:
        def docker(self, arguments, **_kwargs):
            calls.append(list(arguments))
            if arguments[:2] == ["buildx", "build"]:
                (contexts["run-services"] / "input.txt").write_text(
                    "changed during build\n",
                    encoding="utf-8",
                )
                return b""
            labels = {
                calls[0][index + 1].split("=", 1)[0]: (
                    calls[0][index + 1].split("=", 1)[1]
                )
                for index, value in enumerate(calls[0][:-1])
                if value == "--label"
            }
            return json.dumps(
                [{"Id": image_id, "Config": {"Labels": labels}}]
            ).encode()

    with pytest.raises(
        controller.CutoverError,
        match="identity or source labels",
    ):
        controller.build_candidate_image(
            SimpleNamespace(
                source_head=head,
                build_context=tmp_path,
                source_root=tmp_path,
                fleet_media_contracts=tmp_path,
                design_product_root=tmp_path,
            ),
            DriftingRunner(),
            contexts=contexts,
            context_digests=context_digests,
        )


def test_context_inventory_binds_modes_empty_directories_and_rejects_symlink_dirs(
    tmp_path: Path,
) -> None:
    root = tmp_path / "context"
    empty = root / "empty"
    empty.mkdir(parents=True)
    empty.chmod(0o700)
    payload = root / "payload"
    payload.write_text("payload\n", encoding="utf-8")
    first = controller._snapshot_inventory(root, label="test context")

    empty.chmod(0o755)
    second = controller._snapshot_inventory(root, label="test context")
    assert first != second

    symlink = root / "linked-directory"
    symlink.symlink_to(empty, target_is_directory=True)
    with pytest.raises(controller.CutoverError, match="symbolic link"):
        controller._snapshot_inventory(root, label="test context")


def test_warm_start_validation_failure_reconciles_exact_created_name(
    tmp_path: Path,
) -> None:
    container_id = "c" * 64
    image_id = "sha256:" + "b" * 64
    name = "chummer-public-download-warm-test"
    docker_calls: list[list[str]] = []

    class FakeRunner:
        def compose(self, *_args, **_kwargs):
            return b"malformed-container-output\n"

        def docker(self, arguments, **_kwargs):
            docker_calls.append(list(arguments))
            if arguments[:3] == ["container", "ls", "--all"]:
                return (container_id + "\n").encode()
            if arguments[:2] == ["container", "inspect"]:
                return json.dumps(
                    [
                        {
                            "Id": container_id,
                            "Image": image_id,
                            "Name": f"/{name}",
                            "Config": {
                                "Labels": {
                                    "com.docker.compose.project": (
                                        controller.CANONICAL_PROJECT
                                    ),
                                    "com.docker.compose.service": (
                                        controller.PORTAL_SERVICE
                                    ),
                                    "com.docker.compose.oneoff": "True",
                                }
                            },
                            "State": {"Running": True},
                        }
                    ]
                ).encode()
            if arguments[:3] == ["container", "rm", "--force"]:
                return b""
            raise AssertionError(arguments)

    with pytest.raises(
        controller.CutoverError,
        match="container identity is invalid",
    ):
        controller.warm_oneoff_portal(
            SimpleNamespace(ready_timeout_seconds=1),
            FakeRunner(),
            tmp_path / "compose.json",
            name=name,
            overlay_root=tmp_path / "overlay",
            image_id=image_id,
        )

    assert ["container", "rm", "--force", container_id] in docker_calls


def test_journal_recovery_parse_does_not_require_mutable_build_inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source"
    shelf = tmp_path / "shelf"
    projection = tmp_path / "projection"
    docker_config = tmp_path / "docker"
    receipt_root = tmp_path / "receipts"
    for path in (
        source,
        shelf,
        projection,
        docker_config,
        docker_config / "home",
        docker_config / "config",
        receipt_root,
    ):
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
    journal = receipt_root / "journal.json"
    journal.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(
        controller,
        "CANONICAL_RELEASE_SHELF_ROOT",
        shelf,
    )
    missing = tmp_path / "deliberately-missing"
    sha = "a" * 64
    config = controller.parse_args(
        [
            "--operation",
            controller.RECOVERY_OPERATION,
            "--source-root",
            str(source),
            "--source-head",
            "b" * 40,
            "--shared-mutation-lock-token",
            "c" * 64,
            "--shelf-root",
            str(shelf),
            "--migration-state-root",
            str(missing / "state"),
            "--migration-candidate-root",
            str(missing / "candidate"),
            "--migration-authority",
            str(missing / "authority.json"),
            "--migration-authority-sha256",
            sha,
            "--release-channel-receipt",
            str(missing / "release.json"),
            "--release-channel-receipt-sha256",
            sha,
            "--projection-snapshot-root",
            str(projection),
            "--projection-snapshot-id",
            f"public-projection-{sha}",
            "--projection-snapshot-sha256",
            sha,
            "--projection-manifest-sha256",
            sha,
            "--runtime-proof-source",
            str(missing / "proof.json"),
            "--runtime-proof-sha256",
            sha,
            "--certificate-file",
            str(missing / "certificate.pfx"),
            "--certificate-password-file",
            str(missing / "certificate-password"),
            "--overlay-root",
            str(tmp_path / "overlay"),
            "--overlay-staging-root",
            str(tmp_path / "overlay-next"),
            "--overlay-backup-root",
            str(tmp_path / "overlay-backups"),
            "--overlay-build-root",
            str(tmp_path / "overlay-build"),
            "--transaction-journal",
            str(journal),
            "--active-runtime-authority",
            str(receipt_root / "active.json"),
            "--docker-config-root",
            str(docker_config),
            "--env-file",
            str(missing / ".env"),
            "--receipt-root",
            str(receipt_root),
            "--base-url",
            "https://chummer.run",
            "--build-context",
            str(missing / "build"),
            "--fleet-media-contracts",
            str(missing / "fleet"),
            "--design-product-root",
            str(missing / "design"),
        ]
    )

    assert config.env_file == missing / ".env"
    assert config.build_context == missing / "build"
    assert config.fleet_media_contracts == missing / "fleet"
    assert config.design_product_root == missing / "design"


def _write_migration_shelf(root: Path) -> None:
    artifact = b"incumbent artifact\n"
    artifact_name = "chummer-test.zip"
    (root / "files").mkdir(parents=True)
    (root / "files" / artifact_name).write_bytes(artifact)
    download = {
        "fileName": artifact_name,
        "sha256": controller.sha256_bytes(artifact),
        "sizeBytes": len(artifact),
    }
    identity = {
        "version": "run-test",
        "channel": "preview",
        "publishedAt": "2026-07-23T12:00:00Z",
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


def test_cutover_consumes_exact_preflight_candidate_unchanged_and_quarantines_drift(
    tmp_path: Path,
) -> None:
    shelf = tmp_path / "shelf"
    _write_migration_shelf(shelf)
    private_parent = tmp_path / "private"
    private_parent.mkdir(mode=0o700)
    private_parent.chmod(0o700)
    candidate = private_parent / "candidate"
    restoration_spec = private_parent / "restorations.json"
    restoration_spec.write_text("[]\n", encoding="utf-8")
    attestor.materialize_public_download_migration_candidate(
        shelf,
        candidate,
        "a" * 40,
        restoration_spec,
        controller.sha256_bytes(restoration_spec.read_bytes()),
        private_parent / "candidate-materialization.json",
    )
    candidate_identity = candidate.stat().st_dev, candidate.stat().st_ino
    candidate_inventory = attestor.inventory_tree(
        candidate,
        skip_top_level_controls=False,
    )

    receipt = controller.materialize_incumbent_candidate(
        attestor=attestor,
        shelf_root=shelf,
        candidate_root=candidate,
        manifest_closure_restorations=[],
    )
    assert receipt["resumedExactCandidate"] is True
    assert (
        candidate.stat().st_dev,
        candidate.stat().st_ino,
    ) == candidate_identity
    assert attestor.inventory_tree(
        candidate,
        skip_top_level_controls=False,
    ) == candidate_inventory

    (candidate / "files" / "chummer-test.zip").write_bytes(b"drift\n")
    with pytest.raises(controller.CutoverError, match="quarantined"):
        controller.materialize_incumbent_candidate(
            attestor=attestor,
            shelf_root=shelf,
            candidate_root=candidate,
            manifest_closure_restorations=[],
        )
    assert not candidate.exists()
    assert any(
        path.name.startswith(".quarantine-candidate-")
        for path in private_parent.iterdir()
    )


def test_promotion_lease_avoids_nested_lock_and_is_shelf_bound(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shelf = tmp_path / "shelf"
    shelf.mkdir()
    prepared = tmp_path / "prepared"
    prepared_generation = prepared / generation.GENERATIONS_DIRECTORY / "g-test"
    prepared_generation.mkdir(parents=True)
    (prepared / generation.CURRENT_POINTER).write_text("{}\n", encoding="utf-8")

    monkeypatch.setattr(
        generation,
        "load_pointer",
        lambda _path: {
            "schemaVersion": generation.POINTER_SCHEMA,
            "generationId": "g-test",
        },
    )
    monkeypatch.setattr(generation, "verify_generation", lambda *_args: None)
    monkeypatch.setattr(generation, "refuse_server_managed_filesystem_shelf", lambda *_args: None)
    monkeypatch.setattr(
        generation,
        "resolve_shelf_root",
        lambda _path: ("legacy", shelf, None),
    )

    with generation.promotion_lock(shelf) as lease:
        assert stat.S_IMODE(
            (shelf / generation.PROMOTION_LOCK).stat().st_mode
        ) == 0o600
        assert (shelf / generation.PROMOTION_LOCK).stat().st_uid == os.getuid()
        pointer = generation.activate_prepared_filesystem(
            prepared,
            shelf,
            initialize_layout=True,
            promotion_lease=lease,
        )
        lease.validate_for(shelf)

    assert pointer["generationId"] == "g-test"
    assert (shelf / "generations" / "g-test").is_dir()
    assert (shelf / generation.CURRENT_POINTER).is_file()

    other = tmp_path / "other"
    other.mkdir()
    with generation.promotion_lock(shelf) as lease:
        with pytest.raises(
            generation.ReleaseShelfError,
            match="different release shelf",
        ):
            lease.validate_for(other)


def test_wrapper_routes_public_profile_before_postgres_boundary() -> None:
    script = (ROOT / "scripts/deploy_public_edge_portal.sh").read_text(
        encoding="utf-8"
    )
    controller_branch = script.index("if ((PUBLIC_DOWNLOAD_ONLY_OPERATION == 1)); then")
    postgres_boundary = script.index(
        'INSTALL_LINKING_CUTOVER_BOUNDARY=""',
        controller_branch,
    )

    assert controller_branch < postgres_boundary
    assert "initial-release-shelf-public-download-cutover-recover" in script
    assert "--migration-authority-sha256" in script
    assert "--runtime-proof-sha256" in script
    assert 'if ((public_download_controller_status == 76)); then' in script
    assert "authenticated mutation lock retained" in script
    assert "if ((RECOVERY_ROUTE_REQUESTED == 0)); then" in script
    assert (
        "RECOVERY_ROUTE_REQUESTED == 0 || PUBLIC_DOWNLOAD_ONLY_OPERATION == 1"
        not in script
    )
    recovery_defaults = (
        'PUBLIC_DOWNLOAD_MIGRATION_AUTHORITY="$PUBLIC_DOWNLOAD_MIGRATION_AUTHORITY_INPUT"'
    )
    assert recovery_defaults in script
