from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "materialize_portable_receipts_audit.py"


def load_module():
    spec = importlib.util.spec_from_file_location("materialize_portable_receipts_audit", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def test_scan_ignores_regex_pattern_strings_but_catches_literal_home_paths(tmp_path: Path) -> None:
    module = load_module()
    write_json(tmp_path / "PUBLIC_COPY_LEAK_GATE.generated.json", {"patterns": [r"/home/[A-Za-z0-9_.-]+/"]})
    write_json(tmp_path / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json", {"root": "/home/tibor/pCloud Drive/EA"})

    scan = module.scan_published_receipts([tmp_path])

    assert scan["scanned_artifact_count"] == 2
    assert scan["machine_specific_hits"] == [
        "scan-root-1/WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json"
    ]
    assert scan["machine_specific_path_hits"] == [
        "scan-root-1/WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json"
    ]
    assert scan["artifact_integrity_hits"] == []
    assert scan["machine_specific_hit_details"][0]["category"] == "linux_user_home"
    assert scan["machine_specific_hit_details"][0]["match"] == "<redacted:linux_user_home>"
    assert "/home/tibor" not in json.dumps(scan)


def test_scan_does_not_treat_public_home_routes_as_host_paths(tmp_path: Path) -> None:
    module = load_module()
    write_json(
        tmp_path / "routes.json",
        {
            "route": "/home/runs",
            "redirect": "/login?next=/home/runs/detail",
            "public_url": "https://chummer.run/home/runs/detail",
        },
    )

    scan = module.scan_published_receipts([tmp_path])

    assert scan["scanned_artifact_count"] == 1
    assert scan["machine_specific_hits"] == []


def test_scan_recurses_and_redacts_macos_and_windows_user_homes(tmp_path: Path) -> None:
    module = load_module()
    write_json(tmp_path / "startup-smoke" / "mac.json", {"binary": "/Users/Ålice User/build/Chummer"})
    write_json(tmp_path / "portal" / "windows.json", {"binary": r"C:\Users\Bob Builder\build\Chummer.exe"})
    write_json(tmp_path / "portal" / "linux.json", {"binary": "/home/José Runner/build/Chummer"})

    scan = module.scan_published_receipts([tmp_path])

    assert scan["scanned_artifact_count"] == 3
    assert scan["machine_specific_hits"] == [
        "scan-root-1/portal/linux.json",
        "scan-root-1/portal/windows.json",
        "scan-root-1/startup-smoke/mac.json",
    ]
    assert {detail["category"] for detail in scan["machine_specific_hit_details"]} == {
        "linux_user_home",
        "macos_user_home",
        "windows_user_home",
    }
    serialized = json.dumps(scan)
    assert "Ålice User" not in serialized
    assert "Bob Builder" not in serialized
    assert "José Runner" not in serialized
    assert str(tmp_path) not in serialized


def test_scan_rejects_absolute_process_path_even_outside_user_home(tmp_path: Path) -> None:
    module = load_module()
    write_json(
        tmp_path / "startup-smoke" / "linux.json",
        {"processPath": "/tmp/chummer-smoke.random/Chummer.Avalonia"},
    )

    scan = module.scan_published_receipts([tmp_path])

    assert scan["machine_specific_hits"] == ["scan-root-1/startup-smoke/linux.json"]
    assert scan["machine_specific_hit_details"][0]["category"] == "host_absolute_path_field"
    assert "/tmp/chummer-smoke" not in json.dumps(scan)


def test_scan_rejects_absolute_docker_opt_and_srv_roots_in_arbitrary_text(tmp_path: Path) -> None:
    module = load_module()
    for index, absolute_path in enumerate(
        (
            "/docker/chummer/build/output.json",
            "/opt/chummer/build/output.json",
            "/srv/chummer/build/output.json",
        )
    ):
        write_json(
            tmp_path / f"receipt-{index}.json",
            {"note": f"materialized from {absolute_path}"},
        )

    scan = module.scan_published_receipts([tmp_path])

    assert len(scan["machine_specific_hits"]) == 3
    assert {detail["category"] for detail in scan["machine_specific_hit_details"]} == {
        "host_absolute_root"
    }
    serialized = json.dumps(scan)
    for forbidden in ("/docker/", "/opt/", "/srv/"):
        assert forbidden not in serialized


def test_scan_rejects_absolute_candidate_path_list_fields(tmp_path: Path) -> None:
    module = load_module()
    write_json(
        tmp_path / "startup-smoke" / "candidate-paths.json",
        {
            "startup_smoke": {
                "candidate_paths": ["/tmp/private/one.json", "/var/tmp/private/two.json"],
            }
        },
    )
    write_json(
        tmp_path / "startup-smoke" / "artifact-path-candidates.json",
        {
            "startup_smoke": {
                "artifactPathCandidates": [r"C:\\Temp\\private\\three.json"],
            }
        },
    )

    scan = module.scan_published_receipts([tmp_path])

    assert scan["machine_specific_hits"] == [
        "scan-root-1/startup-smoke/artifact-path-candidates.json",
        "scan-root-1/startup-smoke/candidate-paths.json",
    ]
    assert {detail["category"] for detail in scan["machine_specific_hit_details"]} == {
        "host_absolute_path_field"
    }
    serialized = json.dumps(scan)
    assert "/tmp/private" not in serialized
    assert "C:\\\\Temp" not in serialized


def test_scan_fails_closed_on_invalid_utf8_nested_json_without_echoing_host_path(tmp_path: Path) -> None:
    module = load_module()
    invalid = tmp_path / "nested" / "invalid.json"
    invalid.parent.mkdir(parents=True)
    invalid.write_bytes(b'{"path":"/home/private/\xff"}')

    scan = module.scan_published_receipts([tmp_path])

    assert scan["machine_specific_hits"] == ["scan-root-1/nested/invalid.json"]
    assert scan["machine_specific_path_hits"] == []
    assert scan["artifact_integrity_hits"] == ["scan-root-1/nested/invalid.json"]
    assert scan["unreadable_artifacts"] == ["scan-root-1/nested/invalid.json"]
    assert scan["machine_specific_hit_details"][0]["category"] == "invalid_json"
    assert "/home/private" not in json.dumps(scan)


def test_materialize_writes_fail_closed_receipt(tmp_path: Path) -> None:
    module = load_module()
    write_json(tmp_path / "receipt.json", {"drop_root": "/home/tibor/Downloads"})

    output_path = tmp_path / "PORTABLE_RECEIPTS_AUDIT.generated.json"
    payload = module.materialize(output_path, [tmp_path])

    assert payload["status"] == "fail"
    assert payload["scanned_artifact_count"] == 1
    assert payload["machine_specific_hits"] == ["scan-root-1/receipt.json"]
    assert output_path.is_file()
    assert json.loads(output_path.read_text(encoding="utf-8")) == payload
    assert not list(tmp_path.glob(".PORTABLE_RECEIPTS_AUDIT.generated.json.*.tmp"))


def test_materialize_reports_invalid_json_as_integrity_failure_without_claiming_home_path(tmp_path: Path) -> None:
    module = load_module()
    invalid = tmp_path / "compile.manifest.abcdefgh.json"
    invalid.write_bytes(b"")

    output_path = tmp_path / "PORTABLE_RECEIPTS_AUDIT.generated.json"
    payload = module.materialize(output_path, [tmp_path])

    assert payload["status"] == "fail"
    assert payload["machine_specific_hits"] == [
        "scan-root-1/compile.manifest.abcdefgh.json"
    ]
    assert payload["machine_specific_path_hits"] == []
    assert payload["artifact_integrity_hits"] == [
        "scan-root-1/compile.manifest.abcdefgh.json"
    ]
    assert payload["failure_counts"] == {
        "machine_specific_paths": 0,
        "artifact_integrity": 1,
    }
    assert "could not be read" in payload["summary"]
    assert "embed machine-specific" not in payload["summary"]
    assert payload["policy"]["fail_on_artifact_integrity_errors"] is True


def test_materialize_excludes_its_own_output_from_followup_scans(tmp_path: Path) -> None:
    module = load_module()
    output_path = tmp_path / "PORTABLE_RECEIPTS_AUDIT.generated.json"
    write_json(tmp_path / "receipt.json", {"drop_root": "/home/tibor/Downloads"})

    payload = module.materialize(output_path, [tmp_path])
    followup_scan = module.scan_published_receipts([tmp_path], excluded_paths=[output_path])

    assert payload["machine_specific_hits"] == ["scan-root-1/receipt.json"]
    assert followup_scan["machine_specific_hits"] == ["scan-root-1/receipt.json"]
