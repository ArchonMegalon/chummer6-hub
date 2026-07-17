from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "verify_release_shelf_replacement.py"
SPEC = importlib.util.spec_from_file_location("verify_release_shelf_replacement", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def manifest(*rows: tuple[str, str, str, str, str]) -> dict:
    return {
        "artifacts": [
            {
                "artifactId": f"{head}-{rid}-{kind}",
                "head": head,
                "platform": platform,
                "rid": rid,
                "kind": kind,
                "fileName": file_name,
            }
            for head, platform, rid, kind, file_name in rows
        ]
    }


def test_replacement_accepts_first_shelf_and_complete_superset() -> None:
    incoming = manifest(
        ("avalonia", "linux", "linux-x64", "installer", "linux.deb"),
        ("avalonia", "windows", "win-x64", "installer", "windows.exe"),
        ("avalonia", "macos", "osx-arm64", "dmg", "mac.dmg"),
    )

    assert MODULE.verify_replacement(None, incoming)[0] == set()
    existing = manifest(("avalonia", "linux", "linux-x64", "installer", "linux.deb"))
    assert MODULE.verify_replacement(existing, incoming)[1] == {
        "avalonia:linux:linux-x64",
        "avalonia:windows:win-x64",
        "avalonia:macos:osx-arm64",
    }


def test_replacement_rejects_implicit_tuple_loss() -> None:
    existing = manifest(
        ("avalonia", "linux", "linux-x64", "installer", "linux.deb"),
        ("avalonia", "windows", "win-x64", "installer", "windows.exe"),
    )
    incoming = manifest(("avalonia", "macos", "osx-arm64", "dmg", "mac.dmg"))

    with pytest.raises(MODULE.ReplacementVerificationError, match="would drop existing desktop install tuple"):
        MODULE.verify_replacement(existing, incoming)


def test_selected_file_filter_cannot_claim_an_unselected_tuple() -> None:
    existing = manifest(
        ("avalonia", "linux", "linux-x64", "installer", "linux.deb"),
        ("avalonia", "macos", "osx-arm64", "dmg", "mac.dmg"),
    )
    incoming = manifest(
        ("avalonia", "linux", "linux-x64", "installer", "linux.deb"),
        ("avalonia", "macos", "osx-arm64", "dmg", "mac.dmg"),
    )

    with pytest.raises(MODULE.ReplacementVerificationError, match="avalonia:macos:osx-arm64"):
        MODULE.verify_replacement(existing, incoming, selected_file_names={"linux.deb"})


def test_non_install_media_does_not_define_a_preserved_tuple() -> None:
    existing = manifest(("avalonia", "windows", "win-x64", "portable", "portable.zip"))
    incoming = manifest(("avalonia", "mac", "osx-arm64", "dmg", "mac.dmg"))

    existing_tuples, incoming_tuples = MODULE.verify_replacement(existing, incoming)

    assert existing_tuples == set()
    assert incoming_tuples == {"avalonia:macos:osx-arm64"}


def test_load_manifest_fails_closed_on_malformed_existing_truth(tmp_path: Path) -> None:
    existing = tmp_path / "existing.json"
    existing.write_text(json.dumps({"artifacts": {"not": "a list"}}), encoding="utf-8")

    with pytest.raises(MODULE.ReplacementVerificationError, match="artifacts must be a list"):
        MODULE.load_manifest(str(existing), allow_missing=False)


def test_publishers_run_preflight_before_mutation() -> None:
    filesystem = (ROOT / "scripts" / "publish-download-bundle.sh").read_text(encoding="utf-8")
    object_storage = (ROOT / "scripts" / "publish-download-bundle-s3.sh").read_text(encoding="utf-8")

    assert filesystem.index("verify_release_shelf_replacement.py") < filesystem.index(
        'bash "$SCRIPT_DIR/generate-releases-manifest.sh"'
    )
    assert "copy_legacy_target" not in object_storage
    assert "CHUMMER_RELEASE_SHELF_LAYOUT_V1_ENABLED" not in object_storage
    assert object_storage.index("verify_release_shelf_replacement.py") < object_storage.index(
        'activate_release_shelf_generation "$S3_TARGET_URI"'
    )
