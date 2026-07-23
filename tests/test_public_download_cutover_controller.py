from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
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
                return json.dumps(
                    [
                        {
                            "Id": image_id,
                            "Config": {
                                "Labels": {
                                    "org.opencontainers.image.revision": head,
                                    "run.chummer.runtime-profile": "public-download-only",
                                }
                            },
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
