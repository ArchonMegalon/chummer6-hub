from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
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


def test_replacement_accepts_an_explicit_exact_scope_with_retirement() -> None:
    existing = manifest(
        ("avalonia", "linux", "linux-x64", "installer", "linux.deb"),
        ("avalonia", "windows", "win-x64", "installer", "windows.exe"),
        ("avalonia", "macos", "osx-arm64", "dmg", "mac.dmg"),
    )
    incoming = manifest(
        ("avalonia", "linux", "linux-x64", "installer", "linux.deb"),
        ("avalonia", "windows", "win-x64", "installer", "windows.exe"),
    )
    exact = MODULE.normalize_exact_incoming_tuples(
        ["avalonia:linux:linux-x64", "avalonia:windows:win-x64"]
    )

    assert MODULE.verify_replacement(existing, incoming, exact_incoming_tuples=exact)[1] == exact


@pytest.mark.parametrize(
    ("declared", "expected"),
    [
        (["avalonia:linux:linux-x64"], "undeclared avalonia:windows:win-x64"),
        (
            ["avalonia:linux:linux-x64", "avalonia:windows:win-x64", "avalonia:macos:osx-arm64"],
            "missing avalonia:macos:osx-arm64",
        ),
    ],
)
def test_replacement_rejects_incoming_truth_that_disagrees_with_exact_scope(
    declared: list[str], expected: str
) -> None:
    incoming = manifest(
        ("avalonia", "linux", "linux-x64", "installer", "linux.deb"),
        ("avalonia", "windows", "win-x64", "installer", "windows.exe"),
    )

    with pytest.raises(MODULE.ReplacementVerificationError, match=expected):
        MODULE.verify_replacement(
            None,
            incoming,
            exact_incoming_tuples=MODULE.normalize_exact_incoming_tuples(declared),
        )


@pytest.mark.parametrize(
    "declared",
    [
        [],
        ["avalonia:linux"],
        ["avalonia::linux-x64"],
        ["avalonia:linux:../../escape"],
        ["avalonia:linux:linux-x64", "AVALONIA:LINUX:LINUX-X64"],
    ],
)
def test_exact_scope_declaration_rejects_empty_malformed_or_duplicate_values(declared: list[str]) -> None:
    with pytest.raises(MODULE.ReplacementVerificationError):
        MODULE.normalize_exact_incoming_tuples(declared)


def test_selected_file_filter_cannot_fake_an_exact_scope() -> None:
    incoming = manifest(
        ("avalonia", "linux", "linux-x64", "installer", "linux.deb"),
        ("avalonia", "windows", "win-x64", "installer", "windows.exe"),
    )
    exact = MODULE.normalize_exact_incoming_tuples(
        ["avalonia:linux:linux-x64", "avalonia:windows:win-x64"]
    )

    with pytest.raises(MODULE.ReplacementVerificationError, match="missing avalonia:windows:win-x64"):
        MODULE.verify_replacement(
            None,
            incoming,
            selected_file_names={"linux.deb"},
            exact_incoming_tuples=exact,
        )


def test_cli_exact_scope_transport_allows_only_the_declared_windows_linux_shelf(
    tmp_path: Path,
) -> None:
    existing = tmp_path / "existing.json"
    incoming = tmp_path / "incoming.json"
    selected = tmp_path / "files"
    selected.mkdir()
    existing.write_text(
        json.dumps(
            manifest(
                ("avalonia", "linux", "linux-x64", "installer", "linux.deb"),
                ("avalonia", "windows", "win-x64", "installer", "windows.exe"),
                ("avalonia", "macos", "osx-arm64", "dmg", "mac.dmg"),
            )
        ),
        encoding="utf-8",
    )
    incoming.write_text(
        json.dumps(
            manifest(
                ("avalonia", "linux", "linux-x64", "installer", "linux.deb"),
                ("avalonia", "windows", "win-x64", "installer", "windows.exe"),
            )
        ),
        encoding="utf-8",
    )
    (selected / "linux.deb").write_bytes(b"linux")
    (selected / "windows.exe").write_bytes(b"windows")

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--existing",
            str(existing),
            "--incoming",
            str(incoming),
            "--selected-files-dir",
            str(selected),
            "--exact-incoming-scope",
            "avalonia:windows:win-x64,avalonia:linux:linux-x64",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "incoming tuples=2" in result.stdout


@pytest.mark.parametrize(
    "scope",
    [
        "",
        "avalonia:linux",
        "avalonia:linux:linux-x64,AVALONIA:LINUX:LINUX-X64",
    ],
)
def test_cli_exact_scope_transport_rejects_empty_malformed_or_duplicate_values(
    tmp_path: Path,
    scope: str,
) -> None:
    incoming = tmp_path / "incoming.json"
    incoming.write_text(
        json.dumps(manifest(("avalonia", "linux", "linux-x64", "installer", "linux.deb"))),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--existing",
            str(tmp_path / "absent.json"),
            "--allow-missing-existing",
            "--incoming",
            str(incoming),
            "--exact-incoming-scope",
            scope,
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "exact incoming" in result.stderr


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
    for publisher in (filesystem, object_storage):
        assert "CHUMMER_RELEASE_EXACT_INCOMING_TUPLES" in publisher
        assert '--exact-incoming-scope "$EXACT_INCOMING_SCOPE"' in publisher
