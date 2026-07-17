from __future__ import annotations

import argparse
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


def test_discover_candidates_accepts_top_level_temp_auto_import_root_files(tmp_path: Path) -> None:
    module = load_module()
    temp_root = tmp_path / "tmp"
    temp_root.mkdir(parents=True)
    receipt = temp_root / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE.generated.json"
    receipt.write_text("{}", encoding="utf-8")
    intake = {
        "artifact_intake": {
            "auto_import_roots": [str(temp_root)],
        },
        "expected_artifact_patterns": [
            "*google-oauth-linking-operator-evidence*.zip",
            "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE.generated.json",
        ],
        "drop_roots_checked": [],
    }

    candidates = module.discover_candidates(intake, [temp_root])

    assert [Path(row["path"]) for row in candidates] == [receipt]
    assert candidates[0]["discovery_kind"] == "expected_exact_name"


def test_build_waiting_payload_uses_current_waiting_contract_and_refreshable_watch_command(tmp_path: Path) -> None:
    module = load_module()
    intake_request = tmp_path / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE_REQUEST.generated.json"
    intake = {
        "base_url": "https://chummer.run",
        "required_operator_evidence_path": str(tmp_path / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE.generated.json"),
        "release_channel_receipt_path": str(tmp_path / "RELEASE_CHANNEL.generated.json"),
        "release_version": "run-20260704-170602",
        "release_channel": "preview",
        "release_supportability_state": "preview_supported",
        "release_rollout_state": "promoted_preview",
        "release_published_at": "2026-07-04T17:48:20Z",
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
    assert payload["release_channel_receipt_path"] == str(tmp_path / "RELEASE_CHANNEL.generated.json")
    assert payload["release_version"] == "run-20260704-170602"
    assert payload["release_channel"] == "preview"
    assert payload["release_supportability_state"] == "preview_supported"
    assert payload["release_rollout_state"] == "promoted_preview"
    assert payload["release_published_at"] == "2026-07-04T17:48:20Z"
    assert payload["base_url"] == "https://chummer.run"


def test_build_result_payload_carries_release_tuple_from_current_intake_request(tmp_path: Path) -> None:
    module = load_module()
    intake_request = tmp_path / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE_REQUEST.generated.json"
    intake_request.write_text(
        """{
  "base_url": "https://chummer.run",
  "release_channel_receipt_path": "/tmp/RELEASE_CHANNEL.generated.json",
  "release_version": "run-20260704-170602",
  "release_channel": "preview",
  "release_supportability_state": "preview_supported",
  "release_rollout_state": "promoted_preview",
  "release_published_at": "2026-07-04T17:48:20Z"
}
""",
        encoding="utf-8",
    )
    artifact = tmp_path / "google-proof.zip"
    artifact.write_bytes(b"zip")

    payload = module.build_result_payload(
        artifact=artifact,
        intake_request=intake_request,
        roots=[tmp_path / "incoming"],
        candidates=[],
        import_summary={"status": "pass"},
        command_results=[],
    )

    assert payload["release_channel_receipt_path"] == "/tmp/RELEASE_CHANNEL.generated.json"
    assert payload["release_version"] == "run-20260704-170602"
    assert payload["release_channel"] == "preview"
    assert payload["release_supportability_state"] == "preview_supported"
    assert payload["release_rollout_state"] == "promoted_preview"
    assert payload["release_published_at"] == "2026-07-04T17:48:20Z"
    assert payload["base_url"] == "https://chummer.run"


def test_build_not_required_payload_marks_request_satisfied_without_artifact(tmp_path: Path) -> None:
    module = load_module()
    intake_request = tmp_path / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE_REQUEST.generated.json"
    intake = {
        "status": "not_required",
        "base_url": "https://chummer.run",
        "required_operator_evidence_path": str(tmp_path / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE.generated.json"),
        "release_channel_receipt_path": str(tmp_path / "RELEASE_CHANNEL.generated.json"),
        "release_version": "run-20260704-170602",
        "release_channel": "preview",
        "release_supportability_state": "preview_supported",
        "release_rollout_state": "promoted_preview",
        "release_published_at": "2026-07-04T17:48:20Z",
        "artifact_intake": {
            "preferred_drop_path": str(tmp_path / "incoming" / "google-evidence.zip"),
        },
    }

    payload = module.build_not_required_payload(
        intake=intake,
        intake_request=intake_request,
        roots=[tmp_path / "incoming"],
        candidates=[],
    )

    assert payload["status"] == "pass"
    assert payload["request_status"] == "not_required"
    assert payload["operator_action_still_required"] is False
    assert payload["summary"] == "Google OAuth operator evidence already satisfies the current request."
    assert payload["required_operator_evidence_path"] == str(
        tmp_path / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE.generated.json"
    )
    assert payload["base_url"] == "https://chummer.run"


def test_main_rejects_legacy_not_required_request_as_replay(tmp_path: Path) -> None:
    module = load_module()
    intake_request = tmp_path / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE_REQUEST.generated.json"
    output = tmp_path / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE_AUTO_IMPORT.generated.json"
    preferred_root = tmp_path / "incoming"
    preferred_root.mkdir()
    intake_request.write_text(
        """{
  "status": "not_required",
  "required_operator_evidence_path": "%s",
  "release_channel_receipt_path": "%s",
  "release_version": "run-20260704-170602",
  "release_channel": "preview",
  "release_supportability_state": "preview_supported",
  "release_rollout_state": "promoted_preview",
  "release_published_at": "2026-07-04T17:48:20Z",
  "artifact_intake": {
    "preferred_drop_path": "%s",
    "auto_import_roots": ["%s"]
  }
}
"""
        % (
            tmp_path / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE.generated.json",
            tmp_path / "RELEASE_CHANNEL.generated.json",
            preferred_root / "google-oauth-linking-operator-evidence-run-20260704-170602.zip",
            preferred_root,
        ),
        encoding="utf-8",
    )

    with (
        mock.patch.object(
            module,
            "parse_args",
            return_value=argparse.Namespace(
                artifact=None,
                base_url="https://chummer.run",
                intake_request=intake_request,
                output=output,
                discovery_root=None,
                wait_seconds=0.0,
                poll_seconds=5.0,
                refresh_intake_request=False,
            ),
        ),
        mock.patch.object(module, "wait_for_candidate", side_effect=AssertionError("not_required should not wait")),
    ):
        exit_code = module.main()

    payload = module.load_json(output)
    assert exit_code == 1
    assert payload["status"] == "fail"
    assert "not_required" in payload["failures"][0]


def test_main_passes_base_url_into_ensure_intake_request(tmp_path: Path) -> None:
    module = load_module()
    intake_request = tmp_path / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE_REQUEST.generated.json"
    output = tmp_path / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE_AUTO_IMPORT.generated.json"
    preferred_root = tmp_path / "incoming"
    preferred_root.mkdir()
    captured: dict[str, object] = {}

    def fake_ensure(path: Path, refresh: bool, base_url: str) -> dict[str, object]:
        captured["path"] = path
        captured["refresh"] = refresh
        captured["base_url"] = base_url
        return {
            "status": "not_required",
            "required_operator_evidence_path": str(tmp_path / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE.generated.json"),
            "artifact_intake": {
                "preferred_drop_path": str(preferred_root / "google-oauth-linking-operator-evidence.zip"),
                "auto_import_roots": [str(preferred_root)],
            },
        }

    with (
        mock.patch.object(
            module,
            "parse_args",
            return_value=argparse.Namespace(
                artifact=None,
                base_url="https://ops.example.test",
                intake_request=intake_request,
                output=output,
                discovery_root=None,
                wait_seconds=0.0,
                poll_seconds=5.0,
                refresh_intake_request=True,
            ),
        ),
        mock.patch.object(module, "ensure_intake_request", side_effect=fake_ensure),
        mock.patch.object(module, "wait_for_candidate", side_effect=AssertionError("not_required should not wait")),
    ):
        exit_code = module.main()

    assert exit_code == 1
    assert captured == {
        "path": intake_request,
        "refresh": True,
        "base_url": "https://ops.example.test",
    }


def test_main_passes_intake_request_into_importer(tmp_path: Path) -> None:
    module = load_module()
    intake_request = tmp_path / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE_REQUEST.generated.json"
    output = tmp_path / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE_AUTO_IMPORT.generated.json"
    artifact = tmp_path / "google-proof.zip"
    artifact.write_bytes(b"zip")
    evidence_path = tmp_path / "published" / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE.generated.json"
    intake = {
        "status": "operator_action_required",
        "required_operator_evidence_path": str(evidence_path),
        "required_receipt_path": str(evidence_path),
        "artifact_intake": {
            "preferred_drop_path": str(tmp_path / "incoming" / artifact.name),
            "post_import_commands": [
                "python3 scripts/materialize_google_oauth_linking_proof.py --base-url https://chummer.run",
            ],
        },
    }

    with (
        mock.patch.object(
            module,
            "parse_args",
            return_value=argparse.Namespace(
                artifact=artifact,
                base_url="https://chummer.run",
                intake_request=intake_request,
                output=output,
                discovery_root=None,
                wait_seconds=0.0,
                poll_seconds=5.0,
                refresh_intake_request=False,
            ),
        ),
        mock.patch.object(module, "ensure_intake_request", return_value=intake),
        mock.patch.object(
            module.evidence_v2,
            "verify_request_file",
            return_value=(intake, {}, b"{}", []),
        ),
        mock.patch.object(module, "discovery_roots_from_intake", return_value=[tmp_path / "incoming"]),
        mock.patch.object(module, "discover_candidates", return_value=[]),
        mock.patch.object(
            module.evidence_importer,
            "import_artifact",
            return_value={"status": "imported", "base_url": "https://chummer.run"},
        ) as import_mock,
        mock.patch.object(
            module,
            "run_command",
            return_value={
                "argv": ["python3", "scripts/materialize_google_oauth_linking_proof.py"],
                "returncode": 0,
                "stdout_tail": [],
                "stderr_tail": [],
            },
        ),
    ):
        exit_code = module.main()

    assert exit_code == 0
    import_mock.assert_called_once_with(
        artifact,
        evidence_path=evidence_path,
        intake_request=intake_request,
    )
