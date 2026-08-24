from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
LOCK_PATH = ROOT / "eng" / "package-plane.lock.json"
SCRIPT_PATH = ROOT / "scripts" / "ai" / "bootstrap-hub-package-feed.py"
CORE_VERSION = "0.0.0-packageplane.candidate.shabc08228d3ce0"
OWNER_VERSION = "0.0.0-packageplane.20260721.1"
CORE_IDS = (
    "Chummer.Engine.Contracts",
    "Chummer.Application",
    "Chummer.Rulesets.Hosting",
    "Chummer.Rulesets.Sr5",
    "Chummer.Rulesets.Sr6",
    "Chummer.Infrastructure",
    "Chummer.Rulesets.Sr4",
    "Chummer.Engine.GmCharacterEdits",
)
REGISTRY_IDS = (
    "Chummer.Hub.Registry.Contracts",
    "Chummer.Run.Registry",
)
HUB_IDS = (
    "Chummer.Play.Contracts",
    "Chummer.Run.Contracts",
    "Chummer.Campaign.Contracts",
    "Chummer.Control.Contracts",
    "Chummer.World.Contracts",
)


def load_module():
    spec = importlib.util.spec_from_file_location("hub_package_plane_v5", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_v5_authority_is_exact_about_graph_versions_and_pending_bytes() -> None:
    module = load_module()
    lock = module.load_lock(LOCK_PATH)
    assert lock.state == module.PENDING_LOCK_STATE
    assert tuple(spec.package_id for spec in lock.packages) == (
        *CORE_IDS,
        *REGISTRY_IDS,
        *HUB_IDS,
    )
    assert all(spec.version == CORE_VERSION for spec in lock.packages[:8])
    assert all(spec.version == OWNER_VERSION for spec in lock.packages[8:])
    assert all(spec.source_kind == module.CORE_SOURCE_KIND for spec in lock.packages[:8])
    assert all(spec.source_kind == module.BUILD_SOURCE_KIND for spec in lock.packages[8:])
    assert all(spec.byte_authority_status == "locked" for spec in lock.packages[:9])
    pending = lock.packages[9:]
    assert tuple(spec.package_id for spec in pending) == (
        "Chummer.Run.Registry",
        *HUB_IDS,
    )
    assert all(spec.byte_authority_status == "pending_pinned_ci" for spec in pending)
    assert all(spec.nupkg_sha256 is None and spec.nupkg_size_bytes is None for spec in pending)
    assert set(module.EXPECTED_INTERNAL_DEPENDENCIES) == {
        *CORE_IDS,
        *REGISTRY_IDS,
        *HUB_IDS,
    }


def test_pending_v5_authority_fails_closed_for_normal_materialization(tmp_path: Path) -> None:
    module = load_module()
    with pytest.raises(module.PackagePlaneError, match="not sealed"):
        module.load_lock(LOCK_PATH, allow_pending=False)
    lock = module.load_lock(LOCK_PATH)
    with pytest.raises(module.PackagePlaneError, match="not sealed"):
        module.build_feed(
            lock,
            lock_sha256=hashlib.sha256(LOCK_PATH.read_bytes()).hexdigest(),
            feed=tmp_path / "feed",
            dotnet="must-not-run",
            core_public_bundle=tmp_path / "must-not-open.zip",
        )


def test_v5_rejects_preview_substitution_and_placeholder_digests() -> None:
    module = load_module()
    payload = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    payload["packages"][8]["version"] = "0.1.0-preview"
    with pytest.raises(module.PackagePlaneError, match="owner package version mismatch"):
        module.validate_lock_payload(payload)

    payload = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    payload["packages"][9]["nupkg_sha256"] = "0" * 64
    with pytest.raises(module.PackagePlaneError, match="must not carry placeholder bytes"):
        module.validate_lock_payload(payload)


def test_core_public_bundle_provenance_is_fully_digest_bound() -> None:
    module = load_module()
    lock = module.load_lock(LOCK_PATH)
    authority = lock.core_public_bundle
    assert authority.release_commit == "c6138ff7ca27d66e85b223d0b29381cff4811277"
    assert authority.source_commit == "bc08228d3ce06410ca97ada63a5af41a2eaa91bf"
    assert authority.sha256 == "76943cee5aa7761adf6f13cf8e641d03cf9892ea2ab795d2c9a4e0de6ccd9ce9"
    assert authority.size_bytes == 1546766
    assert authority.receipt_size_bytes == 4539
    assert authority.member_count == 11
    assert authority.uncompressed_size_bytes == 1544384
    assert authority.runtime_lock_sha256 == "e0bf7a1cdd588d542096abb47e3713ac98646bd8cb10786bb4770e8fb7359140"
    assert authority.runtime_inventory_sha256 == "a9e6d7056cdd710080e44eca91e75c06d1a4bf4c44df3df1e05450b15c55946d"


def test_pinned_ci_lane_emits_receipt_and_all_seven_source_package_bytes() -> None:
    workflow = (
        ROOT / ".github/workflows/package-plane-v5-byte-authority.yml"
    ).read_text(encoding="utf-8")
    assert "workflow_dispatch:" in workflow
    assert "--observe-package-authority" in workflow
    assert "--core-public-bundle" in workflow
    assert "--core-public-receipt" in workflow
    assert "76943cee5aa7761adf6f13cf8e641d03cf9892ea2ab795d2c9a4e0de6ccd9ce9" in workflow
    assert "chummer-hub-packages.observed-authority.json" in workflow
    for package_id in (*REGISTRY_IDS, *HUB_IDS):
        assert f"{package_id}.{OWNER_VERSION}.nupkg" in workflow


@pytest.mark.skipif(
    not os.environ.get("HUB_CORE_PUBLIC_BUNDLE")
    or not os.environ.get("HUB_CORE_PUBLIC_RECEIPT"),
    reason="exact public Core bundle is supplied by the package-plane workflow",
)
def test_real_public_core_bundle_imports_exactly_eight_locked_packages(
    tmp_path: Path,
) -> None:
    module = load_module()
    lock = module.load_lock(LOCK_PATH)
    feed = tmp_path / "feed"
    feed.mkdir()
    receipt = module.validate_core_public_receipt(
        Path(os.environ["HUB_CORE_PUBLIC_RECEIPT"]), lock
    )
    assert receipt["receipt_sha256"] == lock.core_public_bundle.receipt_sha256
    provenance = module.import_core_public_bundle(
        Path(os.environ["HUB_CORE_PUBLIC_BUNDLE"]),
        lock,
        feed,
        enforce_locked_bytes=True,
    )
    assert provenance["sha256"] == lock.core_public_bundle.sha256
    assert {path.name for path in feed.iterdir()} == {
        f"{spec.package_id}.{spec.version}.nupkg" for spec in lock.packages[:8]
    }
