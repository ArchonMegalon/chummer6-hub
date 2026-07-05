from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from unittest import mock


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "auto_import_google_oauth_linking_operator_evidence.py"


def load_module():
    spec = importlib.util.spec_from_file_location("auto_import_google_oauth_linking_operator_evidence", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_discover_candidates_prefers_newest_exact_name_match(tmp_path: Path) -> None:
    module = load_module()
    root = tmp_path / "incoming"
    root.mkdir()
    older = root / "google-oauth-linking-operator-evidence-run-20260704-170602.zip"
    newer = root / "copy" / "google-oauth-linking-operator-evidence-run-20260704-170602.zip"
    newer.parent.mkdir()
    older.write_bytes(b"older")
    newer.write_bytes(b"newer")
    os.utime(older, (1_720_000_000, 1_720_000_000))
    os.utime(newer, (1_720_000_100, 1_720_000_100))

    intake = {
        "preferred_drop_path": str(root / "preferred-missing.zip"),
        "expected_artifact_patterns": [
            "*google-oauth-linking-operator-evidence*.zip",
            "google-oauth-linking-operator-evidence-run-20260704-170602.zip",
            "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE.generated.json",
        ],
        "artifact_intake": {
            "preferred_drop_path": str(root / "preferred-missing.zip"),
        },
    }

    candidates = module.discover_candidates(intake, [root])

    assert [Path(row["path"]) for row in candidates[:2]] == [newer, older]
    assert candidates[0]["discovery_kind"] == "expected_exact_name"
    assert module.select_candidate(candidates) == newer


def test_discover_candidates_keeps_preferred_drop_path_ahead_of_newer_glob_matches(tmp_path: Path) -> None:
    module = load_module()
    root = tmp_path / "incoming"
    root.mkdir()
    preferred = root / "google-oauth-linking-operator-evidence-run-20260704-170602.zip"
    newer_other = root / "other" / "google-oauth-linking-operator-evidence-run-20260704-170603.zip"
    newer_other.parent.mkdir()
    preferred.write_bytes(b"preferred")
    newer_other.write_bytes(b"newer")
    os.utime(preferred, (1_720_000_000, 1_720_000_000))
    os.utime(newer_other, (1_720_000_200, 1_720_000_200))

    intake = {
        "preferred_drop_path": str(preferred),
        "expected_artifact_patterns": [
            "*google-oauth-linking-operator-evidence*.zip",
            preferred.name,
            "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE.generated.json",
        ],
        "artifact_intake": {
            "preferred_drop_path": str(preferred),
        },
    }

    candidates = module.discover_candidates(intake, [root])

    assert Path(candidates[0]["path"]) == preferred
    assert candidates[0]["discovery_kind"] == "preferred_drop_path"
    assert module.select_candidate(candidates) == preferred


def test_discovery_roots_from_intake_accepts_artifact_intake_auto_import_roots(tmp_path: Path) -> None:
    module = load_module()
    dedicated = tmp_path / "incoming"
    downloads = tmp_path / "Downloads"
    intake = {
        "artifact_intake": {
            "dedicated_drop_root": str(dedicated),
            "auto_import_roots": [str(dedicated), str(downloads)],
        }
    }

    roots = module.discovery_roots_from_intake(intake)

    assert roots == [dedicated, downloads]


def test_discovery_roots_from_intake_expands_home_relative_roots(tmp_path: Path) -> None:
    module = load_module()
    home = tmp_path / "home"
    downloads = home / "Downloads"
    intake = {
        "artifact_intake": {
            "auto_import_roots": ["~/Downloads"],
        }
    }

    with mock.patch("pathlib.Path.home", return_value=home):
        roots = module.discovery_roots_from_intake(intake)

    assert roots == [downloads]


def test_discover_candidates_does_not_recurse_broad_auto_import_roots(tmp_path: Path) -> None:
    module = load_module()
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    preferred = downloads / "google-oauth-linking-operator-evidence-run-20260704-170602.zip"
    preferred.write_bytes(b"preferred")

    intake = {
        "preferred_drop_path": str(preferred),
        "expected_artifact_patterns": [
            "*google-oauth-linking-operator-evidence*.zip",
            preferred.name,
            "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE.generated.json",
        ],
        "drop_roots_checked": [],
        "artifact_intake": {
            "preferred_drop_path": str(preferred),
            "auto_import_roots": [str(downloads)],
        },
    }

    with mock.patch.object(module, "walk_candidate_files", side_effect=AssertionError("broad roots should not recurse")):
        candidates = module.discover_candidates(intake, [downloads])

    assert Path(candidates[0]["path"]) == preferred
    assert candidates[0]["discovery_kind"] == "preferred_drop_path"


def test_build_waiting_payload_uses_current_waiting_contract_and_refreshable_watch_command(tmp_path: Path) -> None:
    module = load_module()
    intake_request = tmp_path / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE_REQUEST.generated.json"
    intake = {
        "required_operator_evidence_path": str(tmp_path / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE.generated.json"),
        "artifact_intake": {
            "preferred_drop_path": str(tmp_path / "incoming" / "google-evidence.zip"),
        },
    }

    payload = module.build_waiting_payload(
        intake=intake,
        intake_request=intake_request,
        roots=[tmp_path / "incoming"],
        candidates=[],
    )

    assert payload["contract_name"] == module.CONTRACT_NAME
    assert payload["status"] == module.WAITING_STATUS
    assert payload["required_operator_evidence_path"] == str(
        tmp_path / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE.generated.json"
    )
    assert payload["required_receipt_path"] == str(
        tmp_path / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE.generated.json"
    )
    assert "auto_import_google_oauth_linking_operator_evidence.py" in payload["auto_import_command"]
    assert "auto_import_google_oauth_linking_operator_evidence.py" in payload["auto_import_watch_command"]
    assert "--wait-seconds 900" in payload["auto_import_watch_command"]
    assert "--poll-seconds 10" in payload["auto_import_watch_command"]
    assert "--refresh-intake-request" in payload["auto_import_watch_command"]
