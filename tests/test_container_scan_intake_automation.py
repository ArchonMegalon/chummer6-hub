from __future__ import annotations

import importlib.util
import json
import os
import shlex
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest


ROOT = Path("/docker/chummercomplete")
REQUEST_SCRIPT = (
    ROOT
    / "scripts"
    / "release"
    / "materialize_container_vulnerability_scan_intake_request.py"
)
WATCH_SCRIPT = (
    ROOT / "scripts" / "release" / "watch_container_vulnerability_scan_intake.py"
)


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


REQUEST = load_module(REQUEST_SCRIPT, "container_scan_intake_request_test")
WATCH = load_module(WATCH_SCRIPT, "container_scan_intake_watch_test")
NOW = datetime(2026, 7, 13, 15, 0, tzinfo=UTC)
IMAGE_DIGESTS = {
    "chummer-run-api:local": "a" * 64,
    "chummer-run-identity:local": "b" * 64,
}


def write_executable(path: Path, source: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    path.chmod(0o755)


def write_fake_docker(path: Path, state: Path, command_log: Path) -> None:
    write_executable(
        path,
        f"""#!/usr/bin/env python3
import json
import sys
from pathlib import Path

state_path = Path({str(state)!r})
log_path = Path({str(command_log)!r})
with log_path.open("a", encoding="utf-8") as handle:
    handle.write(json.dumps(sys.argv[1:]) + "\\n")
if sys.argv[1:3] != ["image", "inspect"] or len(sys.argv) != 6:
    raise SystemExit(31)
digests = json.loads(state_path.read_text(encoding="utf-8"))
image = sys.argv[3]
if image not in digests:
    raise SystemExit(32)
print("sha256:" + digests[image])
""",
    )


def write_external_drop(
    intake_root: Path,
    *,
    scanner_log: Path,
    fail_scan: bool = False,
) -> None:
    scanner = intake_root / "bin" / "trivy"
    write_executable(
        scanner,
        f"""#!/usr/bin/env python3
import json
import sys
from pathlib import Path

log = Path({str(scanner_log)!r})
with log.open("a", encoding="utf-8") as handle:
    handle.write(json.dumps(sys.argv[1:]) + "\\n")
if sys.argv[1:] == ["--version"]:
    print("Version: 9.9.9")
    raise SystemExit(0)
raise SystemExit({7 if fail_scan else 9})
""",
    )
    cache = intake_root / "cache" / "db"
    cache.mkdir(parents=True, exist_ok=True)
    (cache / "trivy.db").write_bytes(b"operator supplied native offline database")
    (cache / "metadata.json").write_text(
        json.dumps({"UpdatedAt": (NOW - timedelta(hours=1)).isoformat().replace("+00:00", "Z")}),
        encoding="utf-8",
    )


def fixture(tmp_path: Path, *, with_drop: bool = True, fail_scan: bool = False):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    docker_state = tmp_path / "docker-state.json"
    docker_state.write_text(json.dumps(IMAGE_DIGESTS), encoding="utf-8")
    docker_log = tmp_path / "docker-log.jsonl"
    docker = tmp_path / "tools" / "docker"
    write_fake_docker(docker, docker_state, docker_log)
    intake = workspace / ".state" / "incoming_container_vulnerability_scanner" / "trivy"
    scanner_log = tmp_path / "scanner-log.jsonl"
    if with_drop:
        write_external_drop(intake, scanner_log=scanner_log, fail_scan=fail_scan)
    request_path = workspace / ".codex-studio" / "published" / "request.json"
    state_path = workspace / ".state" / "watch.json"
    evidence = workspace / ".codex-studio" / "published" / "evidence.json"

    def request() -> dict[str, object]:
        return REQUEST.build_request(
            workspace_root=workspace,
            scanner="trivy",
            intake_root=intake,
            docker_binary=docker,
            output_path=request_path,
            state_path=state_path,
            evidence_output=evidence,
            now=NOW,
        )

    return {
        "workspace": workspace,
        "docker_state": docker_state,
        "docker_log": docker_log,
        "docker": docker,
        "intake": intake,
        "scanner_log": scanner_log,
        "request_path": request_path,
        "state_path": state_path,
        "evidence": evidence,
        "request": request,
    }


def test_request_records_exact_current_images_scripts_layouts_and_commands(tmp_path: Path) -> None:
    values = fixture(tmp_path)
    payload = values["request"]()

    assert payload["status"] == "ready", payload["failures"]
    assert payload["external_artifacts_required"] is True
    assert payload["repository_generates_external_artifacts"] is False
    assert payload["network_access_allowed"] is False
    assert payload["scanner_or_database_install_allowed"] is False
    assert payload["automatic_import_allowed"] is False
    assert payload["arbitrary_root_discovery_allowed"] is False
    binding = payload["current_bindings"]
    assert len(binding["binding_sha256"]) == 64
    basis = binding["binding_basis"]
    assert basis["release_images"] == [
        {"image_name": name, "image_digest": f"sha256:{digest}"}
        for name, digest in sorted(IMAGE_DIGESTS.items())
    ]
    assert all(len(row["sha256"]) == 64 for row in basis["scripts"].values())
    assert basis["freshness"] == {
        "maximum_scan_age_hours": 24,
        "maximum_database_age_hours": 72,
        "ceilings_may_only_be_tightened": True,
    }
    assert basis["request_output"] == str(values["request_path"])
    assert basis["watch_state"] == str(values["state_path"])

    layout = payload["selected_intake_layout"]
    assert layout["root"] == str(values["intake"])
    assert layout["roles"]["scanner_binary"]["path"] == str(values["intake"] / "bin" / "trivy")
    assert layout["roles"]["database_artifact"]["path"] == str(
        values["intake"] / "cache" / "db" / "trivy.db"
    )
    assert layout["roles"]["database_metadata"]["path"] == str(
        values["intake"] / "cache" / "db" / "metadata.json"
    )
    assert payload["preferred_drop_roots"]["grype"].endswith(
        "/.state/incoming_container_vulnerability_scanner/grype"
    )

    validate = shlex.split(payload["commands"]["validate_now"])
    generate = shlex.split(payload["commands"]["generate_after_validation_approval"])
    verify = shlex.split(payload["commands"]["verify_after_generation"])
    assert "--generate-evidence" not in validate
    assert "--generate-evidence" in generate
    assert "--approved-validation-state" in generate
    assert generate[generate.index("--expected-request-binding-sha256") + 1] == binding["binding_sha256"]
    assert verify[verify.index("--container-scan-evidence") + 1] == str(values["evidence"])
    assert "telegram" not in json.dumps(payload).lower()


def test_validate_only_hashes_fixed_drop_without_executing_or_generating(tmp_path: Path) -> None:
    values = fixture(tmp_path)
    request = values["request"]()
    binding = request["current_bindings"]["binding_sha256"]

    payload = WATCH.watch_for_artifacts(
        request_path=values["request_path"],
        state_path=values["state_path"],
        expected_request_binding_sha256=binding,
        wait_seconds=0,
        poll_seconds=1,
        generate_evidence=False,
        approved_validation_state=None,
        refresh_request=values["request"],
        monotonic=lambda: 0.0,
        sleep=lambda _: pytest.fail("validate-now must not sleep"),
        now_utc=lambda: NOW,
    )

    assert payload["status"] == "artifacts_validated"
    assert payload["verdict"] == "EXTERNAL_ARTIFACTS_VALIDATED_NOT_EXECUTED"
    assert payload["mode"] == "validate_only"
    assert payload["evidence_generated_by_watcher"] is False
    assert payload["independent_supply_chain_verification_performed"] is False
    assert payload["supply_chain_release_gate_ready"] is False
    assert payload["artifact_import_performed"] is False
    assert payload["executable_permissions_changed"] is False
    assert payload["arbitrary_root_discovery_performed"] is False
    assert len(payload["artifact_binding_sha256"]) == 64
    assert not values["scanner_log"].exists()
    assert not values["evidence"].exists()
    assert json.loads(values["state_path"].read_text(encoding="utf-8")) == payload


def test_grype_native_layout_validates_without_executing_scanner(tmp_path: Path) -> None:
    values = fixture(tmp_path, with_drop=False)
    intake = (
        values["workspace"]
        / ".state"
        / "incoming_container_vulnerability_scanner"
        / "grype"
    )
    scanner_log = tmp_path / "grype-invoked"
    write_executable(
        intake / "bin" / "grype",
        f"#!/bin/sh\nprintf invoked > {str(scanner_log)!r}\n",
    )
    database_root = intake / "cache" / "db"
    database_root.mkdir(parents=True)
    (database_root / "vulnerability.db").write_bytes(b"native grype database")
    (database_root / "metadata.json").write_text(
        json.dumps({"built": (NOW - timedelta(hours=1)).isoformat()}),
        encoding="utf-8",
    )
    request = REQUEST.build_request(
        workspace_root=values["workspace"],
        scanner="grype",
        intake_root=intake,
        docker_binary=values["docker"],
        output_path=values["request_path"],
        state_path=values["state_path"],
        evidence_output=values["evidence"],
        now=NOW,
    )

    validation = WATCH.validate_deterministic_artifacts(request, now=NOW)

    assert request["status"] == "ready"
    assert validation["status"] == "ready"
    assert len(validation["artifact_binding_sha256"]) == 64
    assert not scanner_log.exists()


def test_missing_selected_drop_does_not_discover_or_execute_decoy(tmp_path: Path) -> None:
    values = fixture(tmp_path, with_drop=False)
    decoy_log = tmp_path / "decoy-log"
    write_executable(
        tmp_path / "Downloads" / "trivy",
        f"#!/bin/sh\nprintf invoked > {str(decoy_log)!r}\n",
    )
    request = values["request"]()

    payload = WATCH.watch_for_artifacts(
        request_path=values["request_path"],
        state_path=values["state_path"],
        expected_request_binding_sha256=request["current_bindings"]["binding_sha256"],
        wait_seconds=0,
        poll_seconds=1,
        generate_evidence=False,
        approved_validation_state=None,
        refresh_request=values["request"],
        monotonic=lambda: 0.0,
        sleep=lambda _: pytest.fail("validate-now must not sleep"),
        now_utc=lambda: NOW,
    )

    assert payload["status"] == "waiting_for_external_artifacts"
    assert payload["validation"]["missing_roles"] == [
        "cache_dir",
        "database_artifact",
        "database_metadata",
        "scanner_binary",
    ]
    assert not decoy_log.exists()


def test_current_image_binding_drift_is_rejected_before_scanner_execution(tmp_path: Path) -> None:
    values = fixture(tmp_path)
    original = values["request"]()
    drifted = dict(IMAGE_DIGESTS)
    drifted["chummer-run-api:local"] = "c" * 64
    values["docker_state"].write_text(json.dumps(drifted), encoding="utf-8")

    payload = WATCH.watch_for_artifacts(
        request_path=values["request_path"],
        state_path=values["state_path"],
        expected_request_binding_sha256=original["current_bindings"]["binding_sha256"],
        wait_seconds=0,
        poll_seconds=1,
        generate_evidence=False,
        approved_validation_state=None,
        refresh_request=values["request"],
        monotonic=lambda: 0.0,
        sleep=lambda _: pytest.fail("drift rejection must not sleep"),
        now_utc=lambda: NOW,
    )

    assert payload["status"] == "request_binding_drift"
    assert payload["verdict"] == "INTAKE_BINDING_DRIFT"
    assert not values["scanner_log"].exists()
    assert not values["evidence"].exists()


def test_symbolic_link_component_cannot_escape_selected_drop_root(tmp_path: Path) -> None:
    values = fixture(tmp_path, with_drop=False)
    outside = tmp_path / "outside"
    write_external_drop(outside, scanner_log=values["scanner_log"])
    values["intake"].mkdir(parents=True)
    (values["intake"] / "bin").symlink_to(outside / "bin", target_is_directory=True)
    cache = values["intake"] / "cache" / "db"
    cache.mkdir(parents=True)
    (cache / "trivy.db").write_bytes((outside / "cache" / "db" / "trivy.db").read_bytes())
    (cache / "metadata.json").write_bytes((outside / "cache" / "db" / "metadata.json").read_bytes())
    request = values["request"]()

    payload = WATCH.watch_for_artifacts(
        request_path=values["request_path"],
        state_path=values["state_path"],
        expected_request_binding_sha256=request["current_bindings"]["binding_sha256"],
        wait_seconds=0,
        poll_seconds=1,
        generate_evidence=False,
        approved_validation_state=None,
        refresh_request=values["request"],
        monotonic=lambda: 0.0,
        sleep=lambda _: pytest.fail("symlink rejection must not sleep"),
        now_utc=lambda: NOW,
    )

    assert payload["status"] == "artifacts_rejected"
    assert "symbolic-link component" in payload["failures"][0]
    assert not values["scanner_log"].exists()


def test_request_rejects_symlink_in_intake_root_ancestor_without_canonicalizing_it(
    tmp_path: Path,
) -> None:
    values = fixture(tmp_path, with_drop=False)
    outside = tmp_path / "outside"
    outside.mkdir()
    linked_parent = tmp_path / "linked-parent"
    linked_parent.symlink_to(outside, target_is_directory=True)
    intake = linked_parent / "trivy"

    payload = REQUEST.build_request(
        workspace_root=values["workspace"],
        scanner="trivy",
        intake_root=intake,
        docker_binary=values["docker"],
        output_path=values["request_path"],
        state_path=values["state_path"],
        evidence_output=values["evidence"],
        now=NOW,
    )

    assert payload["status"] == "fail"
    assert payload["selected_intake_layout"]["root"] == str(intake)
    assert any("symbolic-link components" in failure for failure in payload["failures"])


def test_explicit_generation_requires_approved_validation_and_never_synthesizes_pass(tmp_path: Path) -> None:
    values = fixture(tmp_path, fail_scan=True)
    request = values["request"]()
    binding = request["current_bindings"]["binding_sha256"]
    validated = WATCH.watch_for_artifacts(
        request_path=values["request_path"],
        state_path=values["state_path"],
        expected_request_binding_sha256=binding,
        wait_seconds=0,
        poll_seconds=1,
        generate_evidence=False,
        approved_validation_state=None,
        refresh_request=values["request"],
        monotonic=lambda: 0.0,
        sleep=lambda _: None,
        now_utc=lambda: NOW,
    )
    assert validated["status"] == "artifacts_validated"

    generated = WATCH.watch_for_artifacts(
        request_path=values["request_path"],
        state_path=values["state_path"],
        expected_request_binding_sha256=binding,
        wait_seconds=0,
        poll_seconds=1,
        generate_evidence=True,
        approved_validation_state=values["state_path"],
        refresh_request=values["request"],
        monotonic=lambda: 0.0,
        sleep=lambda _: None,
        now_utc=lambda: NOW,
    )

    assert generated["status"] == "evidence_generation_failed"
    assert generated["exit_code"] == 1
    assert generated["evidence_generated_by_watcher"] is False
    assert generated["generation"]["return_code"] == 1
    evidence = json.loads(values["evidence"].read_text(encoding="utf-8"))
    assert evidence["status"] == "fail"
    assert evidence["scans"] == []
    assert any("producer did not complete" in failure for failure in generated["failures"])
    assert values["scanner_log"].exists()


def test_artifact_drift_after_validation_rejects_generation_approval(tmp_path: Path) -> None:
    values = fixture(tmp_path, fail_scan=True)
    request = values["request"]()
    binding = request["current_bindings"]["binding_sha256"]
    validated = WATCH.watch_for_artifacts(
        request_path=values["request_path"],
        state_path=values["state_path"],
        expected_request_binding_sha256=binding,
        wait_seconds=0,
        poll_seconds=1,
        generate_evidence=False,
        approved_validation_state=None,
        refresh_request=values["request"],
        monotonic=lambda: 0.0,
        sleep=lambda _: None,
        now_utc=lambda: NOW,
    )
    assert validated["status"] == "artifacts_validated"
    database = values["intake"] / "cache" / "db" / "trivy.db"
    database.write_bytes(database.read_bytes() + b" drift")

    generated = WATCH.watch_for_artifacts(
        request_path=values["request_path"],
        state_path=values["state_path"],
        expected_request_binding_sha256=binding,
        wait_seconds=0,
        poll_seconds=1,
        generate_evidence=True,
        approved_validation_state=values["state_path"],
        refresh_request=values["request"],
        monotonic=lambda: 0.0,
        sleep=lambda _: None,
        now_utc=lambda: NOW,
    )

    assert generated["status"] == "validation_approval_rejected"
    assert "artifact_binding_sha256" in generated["failures"][0]
    assert not values["scanner_log"].exists()
    assert not values["evidence"].exists()


def test_artifact_drift_during_producer_run_cannot_return_generation_success(
    tmp_path: Path,
) -> None:
    values = fixture(tmp_path)
    request = values["request"]()
    binding = request["current_bindings"]["binding_sha256"]
    validated = WATCH.watch_for_artifacts(
        request_path=values["request_path"],
        state_path=values["state_path"],
        expected_request_binding_sha256=binding,
        wait_seconds=0,
        poll_seconds=1,
        generate_evidence=False,
        approved_validation_state=None,
        refresh_request=values["request"],
        monotonic=lambda: 0.0,
        sleep=lambda _: None,
        now_utc=lambda: NOW,
    )
    approved = {
        row["role"]: row["sha256"]
        for row in validated["validation"]["files"]
    }

    def drift_and_claim_success(current_request: dict[str, object]) -> dict[str, object]:
        database = values["intake"] / "cache" / "db" / "trivy.db"
        database.write_bytes(database.read_bytes() + b" changed during producer execution")
        values["evidence"].parent.mkdir(parents=True, exist_ok=True)
        values["evidence"].write_text(
            json.dumps(
                {
                    "contract_name": WATCH.verifier.CONTAINER_SCAN_CONTRACT_NAME,
                    "producer_contract_name": WATCH.producer.PRODUCER_CONTRACT_NAME,
                    "status": "pass",
                    "release_images": current_request["current_bindings"]["binding_basis"]["release_images"],
                    "scanner": {"binary_sha256": approved["scanner binary"]},
                    "database": {
                        "artifact_sha256": approved["vulnerability database artifact"],
                        "metadata_sha256": approved["vulnerability database metadata"],
                    },
                }
            ),
            encoding="utf-8",
        )
        return {"status": "completed", "return_code": 0, "failure": ""}

    generated = WATCH.watch_for_artifacts(
        request_path=values["request_path"],
        state_path=values["state_path"],
        expected_request_binding_sha256=binding,
        wait_seconds=0,
        poll_seconds=1,
        generate_evidence=True,
        approved_validation_state=values["state_path"],
        refresh_request=values["request"],
        run_producer=drift_and_claim_success,
        monotonic=lambda: 0.0,
        sleep=lambda _: None,
        now_utc=lambda: NOW,
    )

    assert generated["status"] == "evidence_generation_failed"
    assert generated["generation"]["approved_artifact_binding_preserved"] is False
    assert any("changed during evidence generation" in failure for failure in generated["failures"])


def test_generation_flag_without_prior_validation_receipt_is_rejected(tmp_path: Path) -> None:
    values = fixture(tmp_path)
    request = values["request"]()

    with pytest.raises(ValueError, match="approved-validation-state"):
        WATCH.watch_for_artifacts(
            request_path=values["request_path"],
            state_path=values["state_path"],
            expected_request_binding_sha256=request["current_bindings"]["binding_sha256"],
            wait_seconds=0,
            poll_seconds=1,
            generate_evidence=True,
            approved_validation_state=None,
            refresh_request=values["request"],
        )
    assert not values["scanner_log"].exists()
    assert not values["evidence"].exists()


@pytest.mark.parametrize(
    ("wait_seconds", "poll_seconds", "message"),
    [
        (WATCH.MAX_WAIT_SECONDS + 1, 1, "wait_seconds"),
        (0, WATCH.MAX_POLL_SECONDS + 1, "poll_seconds"),
        (0, 0, "poll_seconds"),
    ],
)
def test_watcher_rejects_unbounded_wait_or_poll_values(
    tmp_path: Path,
    wait_seconds: float,
    poll_seconds: float,
    message: str,
) -> None:
    values = fixture(tmp_path)
    request = values["request"]()
    with pytest.raises(ValueError, match=message):
        WATCH.watch_for_artifacts(
            request_path=values["request_path"],
            state_path=values["state_path"],
            expected_request_binding_sha256=request["current_bindings"]["binding_sha256"],
            wait_seconds=wait_seconds,
            poll_seconds=poll_seconds,
            generate_evidence=False,
            approved_validation_state=None,
            refresh_request=values["request"],
        )


def test_intake_lane_contains_no_download_install_copy_or_chmod_implementation() -> None:
    combined = REQUEST_SCRIPT.read_text(encoding="utf-8") + WATCH_SCRIPT.read_text(encoding="utf-8")
    forbidden_implementation_tokens = (
        "urllib.request",
        "requests.get(",
        "curl ",
        "wget ",
        "apt-get",
        "pip install",
        ".chmod(",
        "shutil.copy",
        "copy2(",
    )
    for token in forbidden_implementation_tokens:
        assert token not in combined
    assert "subprocess.run(\n            arguments," in combined
    assert "producer_exact_argv" in combined
