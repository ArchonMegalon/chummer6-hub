from __future__ import annotations

import copy
import errno
import os
from pathlib import Path

import pytest

import scripts.public_edge_payload_modes as payload_modes
from scripts.public_edge_payload_modes import (
    PAYLOAD_MODE_CONTRACT_NAME,
    PAYLOAD_MODE_ENTRY_BINDING_ALGORITHM,
    PAYLOAD_MODE_RECEIPT_BINDING_CONTRACT_NAME,
    PayloadModePolicyError,
    canonicalize_payload_mode_receipt,
    normalize_payload_modes,
    validate_payload_modes,
    validate_payload_modes_against_receipt,
)


def _mode(path: Path) -> int:
    return path.stat(follow_symlinks=False).st_mode & 0o7777


def _add_private_state(root: Path) -> Path:
    state = root / "state"
    state.mkdir(exist_ok=True)
    state.chmod(0o700)
    return state


def test_normalizer_makes_payload_runtime_readable_and_honors_executable_allowlist(
    tmp_path: Path,
) -> None:
    root = tmp_path / "overlay"
    assets = root / "wwwroot" / "assets"
    assets.mkdir(parents=True)
    service_worker = root / "wwwroot" / "service-worker.js"
    service_worker.write_text("self.addEventListener('fetch', () => {});\n", encoding="utf-8")
    service_worker.chmod(0o600)
    build_info = root / "portal-overlay-build-info.json"
    build_info.write_text("{}\n", encoding="utf-8")
    build_info.chmod(0o600)
    launcher = assets / "launch"
    launcher.write_text("#!/bin/sh\n", encoding="utf-8")
    launcher.chmod(0o700)
    _add_private_state(root)
    root.chmod(0o700)
    (root / "wwwroot").chmod(0o700)
    assets.chmod(0o750)

    receipt = normalize_payload_modes(
        root,
        executable_relative_paths=("wwwroot/assets/launch",),
    )

    assert receipt["contractName"] == PAYLOAD_MODE_CONTRACT_NAME
    assert receipt["entryBinding"]["algorithm"] == PAYLOAD_MODE_ENTRY_BINDING_ALGORITHM
    assert len(receipt["entryBinding"]["sha256"]) == 64
    assert receipt["status"] == "pass"
    assert receipt["normalization"]["changedEntryCount"] == 6
    assert _mode(root) == 0o755
    assert _mode(root / "wwwroot") == 0o755
    assert _mode(assets) == 0o755
    assert _mode(service_worker) == 0o644
    assert _mode(build_info) == 0o644
    assert _mode(launcher) == 0o755
    assert receipt["counts"] == {
        "entryCount": 7,
        "directoryCount": 4,
        "fileCount": 3,
        "executableFileCount": 1,
        "modeFailureCount": 0,
    }
    assert [row["relativePath"] for row in receipt["entries"]] == [
        ".",
        "portal-overlay-build-info.json",
        "state",
        "wwwroot",
        "wwwroot/assets",
        "wwwroot/assets/launch",
        "wwwroot/service-worker.js",
    ]
    assert receipt["executablePolicy"]["relativePaths"] == [
        "wwwroot/assets/launch"
    ]


def test_default_executable_allowlist_strips_accidental_owner_execute_bits(
    tmp_path: Path,
) -> None:
    root = tmp_path / "overlay"
    root.mkdir()
    _add_private_state(root)
    apphost = root / "Chummer.Run.Api"
    library = root / "YamlDotNet.dll"
    manifest = root / "PUBLIC_LANDING_MANIFEST.yaml"
    for path, mode in ((apphost, 0o755), (library, 0o700), (manifest, 0o775)):
        path.write_bytes(b"payload")
        path.chmod(mode)

    receipt = normalize_payload_modes(root)

    assert receipt["status"] == "pass"
    assert receipt["executablePolicy"]["relativePaths"] == []
    assert _mode(apphost) == 0o644
    assert _mode(library) == 0o644
    assert _mode(manifest) == 0o644


def test_state_root_is_private_and_state_contents_are_never_inspected_or_changed(
    tmp_path: Path,
) -> None:
    root = tmp_path / "overlay"
    state = root / "state"
    state.mkdir(parents=True)
    private_file = state / "operator-secret"
    private_file.write_text("secret\n", encoding="utf-8")
    private_file.chmod(0o600)
    private_link = state / "opaque-link"
    private_link.symlink_to(private_file)
    state.chmod(0o755)

    receipt = normalize_payload_modes(root)

    assert receipt["status"] == "pass"
    assert _mode(root) == 0o755
    assert _mode(state) == 0o700
    assert _mode(private_file) == 0o600
    assert private_link.is_symlink()
    assert receipt["stateBoundary"] == {
        "relativePath": "state",
        "stateRootPresent": True,
        "stateRootModeActual": "0700",
        "stateRootModeExpected": "0700",
        "stateRootModeMatches": True,
        "stateContentsInspected": False,
    }
    rendered = repr(receipt)
    assert "operator-secret" not in rendered
    assert "opaque-link" not in rendered


def test_validator_reports_mode_drift_without_mutating_it(tmp_path: Path) -> None:
    root = tmp_path / "overlay"
    root.mkdir()
    _add_private_state(root)
    payload = root / "Chummer.Run.Api.dll"
    payload.write_bytes(b"assembly")
    root.chmod(0o755)
    payload.chmod(0o600)

    receipt = validate_payload_modes(root)

    assert receipt["status"] == "fail"
    assert receipt["counts"]["modeFailureCount"] == 1
    assert receipt["failures"] == [
        {
            "relativePath": "Chummer.Run.Api.dll",
            "kind": "file",
            "modeActual": "0600",
            "modeExpected": "0644",
        }
    ]
    assert _mode(payload) == 0o600

    normalize_payload_modes(root)
    payload.chmod(0o640)
    drift = validate_payload_modes(root)
    assert drift["status"] == "fail"
    assert drift["failures"][0]["modeActual"] == "0640"


def test_missing_state_root_fails_validation_and_normalization_before_mutation(
    tmp_path: Path,
) -> None:
    root = tmp_path / "overlay"
    root.mkdir()
    payload = root / "payload.json"
    payload.write_text("{}\n", encoding="utf-8")
    payload.chmod(0o600)

    receipt = validate_payload_modes(root)

    assert receipt["status"] == "fail"
    assert receipt["stateBoundary"] == {
        "relativePath": "state",
        "stateRootPresent": False,
        "stateRootModeActual": None,
        "stateRootModeExpected": "0700",
        "stateRootModeMatches": False,
        "stateContentsInspected": False,
    }
    assert receipt["failures"][-1] == {
        "relativePath": "state",
        "kind": "state_directory",
        "modeActual": None,
        "modeExpected": "0700",
    }
    with pytest.raises(
        PayloadModePolicyError,
        match="exactly one private state directory",
    ):
        normalize_payload_modes(root)
    assert _mode(payload) == 0o600


def test_receipt_binding_rejects_execute_loss_special_bits_and_path_set_drift(
    tmp_path: Path,
) -> None:
    root = tmp_path / "overlay"
    root.mkdir()
    _add_private_state(root)
    library = root / "Chummer.Run.Api.dll"
    launcher = root / "launcher"
    library.write_bytes(b"assembly")
    launcher.write_bytes(b"apphost")
    normalization_result = normalize_payload_modes(
        root,
        executable_relative_paths=("launcher",),
    )
    with pytest.raises(PayloadModePolicyError, match="unknown=normalization"):
        validate_payload_modes_against_receipt(root, normalization_result)
    expected = canonicalize_payload_mode_receipt(normalization_result)

    initial = validate_payload_modes_against_receipt(root, expected)
    assert initial["contractName"] == PAYLOAD_MODE_RECEIPT_BINDING_CONTRACT_NAME
    assert initial["algorithm"] == PAYLOAD_MODE_ENTRY_BINDING_ALGORITHM
    assert initial["status"] == "pass"

    launcher.chmod(0o644)
    execute_loss = validate_payload_modes_against_receipt(root, expected)
    assert execute_loss["status"] == "fail"
    assert execute_loss["checks"]["exactSortedRelativePathKindModeRowsMatch"] is False
    assert execute_loss["checks"]["entryBindingSha256Matches"] is False

    launcher.chmod(0o755)
    library.chmod(0o4755)
    special_bits = validate_payload_modes_against_receipt(root, expected)
    assert special_bits["status"] == "fail"
    assert special_bits["checks"]["currentPayloadModePolicyPasses"] is False

    library.chmod(0o644)
    added = root / "added.json"
    added.write_text("{}\n", encoding="utf-8")
    added.chmod(0o644)
    addition = validate_payload_modes_against_receipt(root, expected)
    assert addition["status"] == "fail"
    assert addition["actual"]["entryCount"] == addition["expected"]["entryCount"] + 1

    added.unlink()
    library.unlink()
    removal = validate_payload_modes_against_receipt(root, expected)
    assert removal["status"] == "fail"
    assert removal["actual"]["entryCount"] == removal["expected"]["entryCount"] - 1


def test_receipt_binding_rejects_tampered_or_noncanonical_expected_receipt(
    tmp_path: Path,
) -> None:
    root = tmp_path / "overlay"
    root.mkdir()
    _add_private_state(root)
    payload = root / "payload.json"
    payload.write_text("{}\n", encoding="utf-8")
    expected = canonicalize_payload_mode_receipt(normalize_payload_modes(root))

    tampered_digest = copy.deepcopy(expected)
    tampered_digest["entryBinding"]["sha256"] = "0" * 64
    with pytest.raises(PayloadModePolicyError, match="entry binding is invalid"):
        validate_payload_modes_against_receipt(root, tampered_digest)

    tampered_mode = copy.deepcopy(expected)
    tampered_mode["entries"][1]["modeActual"] = "4755"
    tampered_mode["entries"][1]["modeExpected"] = "4755"
    with pytest.raises(PayloadModePolicyError, match="invalid kind/mode"):
        validate_payload_modes_against_receipt(root, tampered_mode)


def test_canonicalizer_strips_only_valid_normalization_metadata(tmp_path: Path) -> None:
    root = tmp_path / "overlay"
    root.mkdir()
    _add_private_state(root)
    payload = root / "payload.json"
    payload.write_text("{}\n", encoding="utf-8")
    normalization_result = normalize_payload_modes(root)

    canonical = canonicalize_payload_mode_receipt(normalization_result)

    assert "normalization" not in canonical
    assert canonicalize_payload_mode_receipt(canonical) == canonical
    assert canonical is not normalization_result
    assert validate_payload_modes_against_receipt(root, canonical)["status"] == "pass"

    invalid_normalization = copy.deepcopy(normalization_result)
    invalid_normalization["normalization"]["unknown"] = True
    with pytest.raises(PayloadModePolicyError, match="normalization metadata fields"):
        canonicalize_payload_mode_receipt(invalid_normalization)


def test_authoritative_receipt_rejects_state_counts_and_failures_tampering(
    tmp_path: Path,
) -> None:
    root = tmp_path / "overlay"
    state = root / "state"
    state.mkdir(parents=True)
    payload = root / "payload.json"
    payload.write_text("{}\n", encoding="utf-8")
    expected = canonicalize_payload_mode_receipt(normalize_payload_modes(root))

    for field, value in (
        ("relativePath", "private-state"),
        ("stateRootPresent", False),
        ("stateRootModeActual", "0755"),
        ("stateRootModeExpected", "0755"),
        ("stateRootModeMatches", False),
        ("stateContentsInspected", True),
    ):
        tampered = copy.deepcopy(expected)
        tampered["stateBoundary"][field] = value
        with pytest.raises(PayloadModePolicyError, match="state boundary is invalid"):
            validate_payload_modes_against_receipt(root, tampered)

    for field in (
        "entryCount",
        "directoryCount",
        "fileCount",
        "executableFileCount",
        "modeFailureCount",
    ):
        tampered = copy.deepcopy(expected)
        tampered["counts"][field] += 1
        with pytest.raises(PayloadModePolicyError, match="counts are invalid"):
            validate_payload_modes_against_receipt(root, tampered)

    tampered_failures = copy.deepcopy(expected)
    tampered_failures["failures"].append({"reason": "forged"})
    with pytest.raises(PayloadModePolicyError, match="failures must be empty"):
        validate_payload_modes_against_receipt(root, tampered_failures)


def test_authoritative_receipt_requires_exactly_one_private_state_root(
    tmp_path: Path,
) -> None:
    root = tmp_path / "overlay"
    root.mkdir()
    _add_private_state(root)
    expected = canonicalize_payload_mode_receipt(normalize_payload_modes(root))
    missing_state = copy.deepcopy(expected)
    missing_state["entries"] = [
        entry
        for entry in missing_state["entries"]
        if entry["kind"] != "state_directory"
    ]
    binding_rows = [
        {
            "relativePath": entry["relativePath"],
            "kind": entry["kind"],
            "mode": entry["modeActual"],
        }
        for entry in missing_state["entries"]
    ]
    missing_state["entryBinding"] = {
        "algorithm": PAYLOAD_MODE_ENTRY_BINDING_ALGORITHM,
        "rowCount": len(binding_rows),
        "sha256": payload_modes._binding_sha256(binding_rows),
    }
    missing_state["counts"]["entryCount"] -= 1
    missing_state["counts"]["directoryCount"] -= 1
    missing_state["stateBoundary"] = {
        "relativePath": "state",
        "stateRootPresent": False,
        "stateRootModeActual": None,
        "stateRootModeExpected": "0700",
        "stateRootModeMatches": True,
        "stateContentsInspected": False,
    }

    with pytest.raises(
        PayloadModePolicyError,
        match="exactly one private state root",
    ):
        canonicalize_payload_mode_receipt(missing_state)


def test_authoritative_receipt_rejects_unknown_and_missing_fields_at_every_level(
    tmp_path: Path,
) -> None:
    root = tmp_path / "overlay"
    root.mkdir()
    _add_private_state(root)
    payload = root / "payload.json"
    payload.write_text("{}\n", encoding="utf-8")
    expected = canonicalize_payload_mode_receipt(normalize_payload_modes(root))

    def top(receipt):
        return receipt

    def checks(receipt):
        return receipt["checks"]

    def entry_binding(receipt):
        return receipt["entryBinding"]

    def executable_policy(receipt):
        return receipt["executablePolicy"]

    def state_boundary(receipt):
        return receipt["stateBoundary"]

    def counts(receipt):
        return receipt["counts"]

    def entry(receipt):
        return receipt["entries"][0]

    for accessor in (
        top,
        checks,
        entry_binding,
        executable_policy,
        state_boundary,
        counts,
        entry,
    ):
        unknown = copy.deepcopy(expected)
        accessor(unknown)["unknownField"] = "forged"
        with pytest.raises(PayloadModePolicyError, match="fields are invalid"):
            validate_payload_modes_against_receipt(root, unknown)

        missing = copy.deepcopy(expected)
        container = accessor(missing)
        del container[next(iter(container))]
        with pytest.raises(PayloadModePolicyError, match="fields are invalid"):
            validate_payload_modes_against_receipt(root, missing)


@pytest.mark.parametrize("unsafe_kind", ["symlink", "fifo", "hardlink"])
def test_payload_unsafe_entries_are_rejected_before_any_mode_changes(
    tmp_path: Path,
    unsafe_kind: str,
) -> None:
    root = tmp_path / "overlay"
    root.mkdir()
    safe_file = root / "safe.txt"
    safe_file.write_text("safe\n", encoding="utf-8")
    safe_file.chmod(0o600)
    unsafe = root / "unsafe"
    if unsafe_kind == "symlink":
        unsafe.symlink_to(safe_file)
    elif unsafe_kind == "fifo":
        os.mkfifo(unsafe)
    else:
        os.link(safe_file, unsafe)

    expected_error = {
        "symlink": "symlink",
        "fifo": "non-regular",
        "hardlink": "hardlinked",
    }[unsafe_kind]
    with pytest.raises(PayloadModePolicyError, match=expected_error):
        normalize_payload_modes(root)

    assert _mode(safe_file) == 0o600


def test_state_boundary_name_must_be_one_safe_component(tmp_path: Path) -> None:
    root = tmp_path / "overlay"
    root.mkdir()

    for value in ("", ".", "..", "nested/state", "nested\\state"):
        with pytest.raises(ValueError):
            validate_payload_modes(root, state_directory_name=value)


def test_executable_allowlist_is_safe_exact_and_must_resolve_to_files(
    tmp_path: Path,
) -> None:
    root = tmp_path / "overlay"
    root.mkdir()

    for values in (
        ("../launcher",),
        ("/launcher",),
        ("nested\\launcher",),
        ("state/launcher",),
        ("launcher", "launcher"),
    ):
        with pytest.raises(ValueError):
            validate_payload_modes(root, executable_relative_paths=values)
    with pytest.raises(PayloadModePolicyError, match="missing or not regular"):
        validate_payload_modes(root, executable_relative_paths=("launcher",))


def test_directory_enumeration_errors_fail_closed_before_normalization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "overlay"
    root.mkdir()
    payload = root / "payload.json"
    payload.write_text("{}\n", encoding="utf-8")
    payload.chmod(0o600)

    def failing_walk(path, *, followlinks, onerror):
        assert Path(path) == root
        assert followlinks is False
        onerror(PermissionError(errno.EACCES, "permission denied", root / "private"))
        yield  # pragma: no cover

    monkeypatch.setattr(payload_modes.os, "walk", failing_walk)
    with pytest.raises(PayloadModePolicyError, match="unable to enumerate"):
        normalize_payload_modes(root)
    assert _mode(payload) == 0o600
