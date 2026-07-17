from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest


ROOT = Path("/docker/chummercomplete")
PRODUCER = ROOT / "scripts" / "release" / "materialize_container_vulnerability_scan_evidence.py"
VERIFIER = ROOT / "scripts" / "release" / "verify_supply_chain_evidence.py"
SPEC = importlib.util.spec_from_file_location("container_scan_contract_verifier", VERIFIER)
assert SPEC is not None and SPEC.loader is not None
VERIFY_MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = VERIFY_MODULE
SPEC.loader.exec_module(VERIFY_MODULE)


IMAGE_DIGESTS = {
    "chummer-run-api:local": "a" * 64,
    "chummer-run-identity:local": "b" * 64,
}


def iso_utc(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def write_executable(path: Path, source: str) -> None:
    path.write_text(source, encoding="utf-8")
    path.chmod(0o755)


def fake_docker(path: Path, state_path: Path, drift_after: dict[str, int] | None = None) -> None:
    state_path.write_text(
        json.dumps(
            {
                "digests": IMAGE_DIGESTS,
                "calls": {},
                "drift_after": drift_after or {},
            }
        ),
        encoding="utf-8",
    )
    write_executable(
        path,
        f"""#!/usr/bin/env python3
import json
import sys
from pathlib import Path

state_path = Path({str(state_path)!r})
state = json.loads(state_path.read_text(encoding="utf-8"))
if sys.argv[1:3] != ["image", "inspect"] or len(sys.argv) != 6:
    raise SystemExit(21)
image = sys.argv[3]
if image not in state["digests"]:
    raise SystemExit(22)
state["calls"][image] = state["calls"].get(image, 0) + 1
state_path.write_text(json.dumps(state), encoding="utf-8")
digest = state["digests"][image]
if state["calls"][image] > state["drift_after"].get(image, 1000000):
    digest = "f" * 64
print("sha256:" + digest)
""",
    )


def fake_scanner(
    path: Path,
    scanner: str,
    log_path: Path,
    *,
    wrong_digest: bool = False,
    scan_exit_code: int = 0,
    mutate_path: Path | None = None,
    severity: str | None = None,
) -> None:
    write_executable(
        path,
        f"""#!/usr/bin/env python3
import datetime
import json
import os
import sys
from pathlib import Path

scanner = {scanner!r}
log_path = Path({str(log_path)!r})
arguments = sys.argv[1:]
with log_path.open("a", encoding="utf-8") as log:
    log.write(json.dumps({{
        "arguments": arguments,
        "environment": {{
            "GRYPE_DB_AUTO_UPDATE": os.environ.get("GRYPE_DB_AUTO_UPDATE"),
            "GRYPE_CHECK_FOR_APP_UPDATE": os.environ.get("GRYPE_CHECK_FOR_APP_UPDATE"),
            "GRYPE_DB_CACHE_DIR": os.environ.get("GRYPE_DB_CACHE_DIR"),
            "GRYPE_DEFAULT_IMAGE_PULL_SOURCE": os.environ.get("GRYPE_DEFAULT_IMAGE_PULL_SOURCE"),
            "TRIVY_OFFLINE_SCAN": os.environ.get("TRIVY_OFFLINE_SCAN"),
            "TRIVY_SKIP_DB_UPDATE": os.environ.get("TRIVY_SKIP_DB_UPDATE"),
            "TRIVY_SKIP_JAVA_DB_UPDATE": os.environ.get("TRIVY_SKIP_JAVA_DB_UPDATE"),
            "TRIVY_SKIP_CHECK_UPDATE": os.environ.get("TRIVY_SKIP_CHECK_UPDATE"),
            "TRIVY_IMAGE_SRC": os.environ.get("TRIVY_IMAGE_SRC"),
            "TRIVY_SCANNERS": os.environ.get("TRIVY_SCANNERS"),
        }},
    }}) + "\\n")
if arguments in (["--version"], ["version"]):
    print("Version: 9.9.9")
    raise SystemExit(0)
if {scan_exit_code}:
    raise SystemExit({scan_exit_code})
image = arguments[-1] if scanner == "trivy" else arguments[0]
digests = {IMAGE_DIGESTS!r}
digest = "c" * 64 if {wrong_digest!r} else digests[image]
now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
if scanner == "trivy":
    findings = [] if {severity!r} is None else [{{
        "VulnerabilityID": "CVE-FIXTURE",
        "PkgName": "fixture-package",
        "Severity": {severity!r},
    }}]
    payload = {{
        "SchemaVersion": 2,
        "ArtifactName": image,
        "ArtifactType": "container_image",
        "CreatedAt": now,
        "Metadata": {{"ImageID": "sha256:" + digest, "RepoTags": [image], "RepoDigests": []}},
        "Results": [{{"Target": image, "Vulnerabilities": findings}}],
    }}
else:
    matches = [] if {severity!r} is None else [{{
        "vulnerability": {{"id": "CVE-FIXTURE", "severity": {severity!r}}},
        "artifact": {{"name": "fixture-package"}},
    }}]
    payload = {{
        "descriptor": {{"name": "grype", "version": "9.9.9", "timestamp": now}},
        "source": {{
            "type": "image",
            "target": {{"userInput": image, "imageID": "sha256:" + digest, "repoDigests": []}},
        }},
        "matches": matches,
        "ignoredMatches": [],
    }}
mutate_path = {str(mutate_path) if mutate_path is not None else ''!r}
if mutate_path:
    Path(mutate_path).write_bytes(b"database changed during scan")
print(json.dumps(payload))
""",
    )


def fixture_command(
    tmp_path: Path,
    scanner: str = "trivy",
    *,
    database_timestamp: datetime | None = None,
    wrong_digest: bool = False,
    scan_exit_code: int = 0,
    drift_after: dict[str, int] | None = None,
    mutate_database: bool = False,
    severity: str | None = None,
) -> tuple[list[str], Path, Path, Path, Path]:
    workspace = tmp_path / "workspace"
    output = workspace / "evidence.json"
    tools = tmp_path / "tools"
    tools.mkdir()
    docker = tools / "docker"
    scanner_binary = tools / scanner
    docker_state = tmp_path / "docker-state.json"
    scanner_log = tmp_path / "scanner-log.jsonl"
    fake_docker(docker, docker_state, drift_after)
    cache = tmp_path / f"{scanner}-cache"
    database = cache / "db" / ("trivy.db" if scanner == "trivy" else "vulnerability.db")
    metadata = cache / "db" / "metadata.json"
    database.parent.mkdir(parents=True)
    database.write_bytes(b"existing offline vulnerability database")
    updated_at = database_timestamp or datetime.now(UTC) - timedelta(hours=1)
    metadata_key = "UpdatedAt" if scanner == "trivy" else "built"
    metadata.write_text(json.dumps({metadata_key: iso_utc(updated_at)}), encoding="utf-8")
    fake_scanner(
        scanner_binary,
        scanner,
        scanner_log,
        wrong_digest=wrong_digest,
        scan_exit_code=scan_exit_code,
        mutate_path=database if mutate_database else None,
        severity=severity,
    )
    command = [
        sys.executable,
        str(PRODUCER),
        "--workspace-root",
        str(workspace),
        "--output",
        str(output),
        "--scanner",
        scanner,
        "--scanner-binary",
        str(scanner_binary.resolve()),
        "--docker-binary",
        str(docker.resolve()),
        "--cache-dir",
        str(cache.resolve()),
        "--database-artifact",
        str(database.resolve()),
        "--database-metadata",
        str(metadata.resolve()),
        "--timeout-seconds",
        "10",
    ]
    return command, output, scanner_log, database, metadata


def load_log(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def assert_verifier_accepts_evidence(monkeypatch, workspace: Path, output: Path) -> None:
    monkeypatch.setattr(
        VERIFY_MODULE,
        "inspect_image_digest",
        lambda image_name: (IMAGE_DIGESTS[image_name], None),
    )
    monkeypatch.setattr(
        VERIFY_MODULE,
        "verify_evidence_attestation",
        lambda *_args, **_kwargs: ({"status": "pass", "key_id": "fixture"}, []),
    )
    result = VERIFY_MODULE.container_vulnerability_audit(
        VERIFY_MODULE.default_targets(workspace),
        output,
    )
    assert result["status"] == "pass", result["failures"]
    assert result["failures"] == []
    assert result["evidence_sha256"] == hashlib.sha256(output.read_bytes()).hexdigest()


def test_trivy_producer_writes_contract_consumable_offline_evidence(monkeypatch, tmp_path: Path) -> None:
    command, output, scanner_log, database, metadata = fixture_command(tmp_path)

    completed = subprocess.run(command, capture_output=True, text=True, check=False)

    assert completed.returncode == 0, completed.stderr
    receipt = json.loads(output.read_text(encoding="utf-8"))
    assert receipt["contract_name"] == VERIFY_MODULE.CONTAINER_SCAN_CONTRACT_NAME
    assert receipt["status"] == "pass"
    assert len(receipt["scans"]) == 2
    assert receipt["database"]["artifact_sha256"] == hashlib.sha256(database.read_bytes()).hexdigest()
    assert receipt["database"]["metadata_sha256"] == hashlib.sha256(metadata.read_bytes()).hexdigest()
    for scan in receipt["scans"]:
        native_result = output.parent / scan["result_path"]
        assert scan["result_sha256"] == hashlib.sha256(native_result.read_bytes()).hexdigest()
    log = load_log(scanner_log)
    scan_calls = [row for row in log if row["arguments"] != ["--version"]]
    assert len(scan_calls) == 2
    assert all("--offline-scan" in row["arguments"] for row in scan_calls)
    assert all("--skip-db-update" in row["arguments"] for row in scan_calls)
    assert all("--skip-java-db-update" in row["arguments"] for row in scan_calls)
    assert all("--skip-check-update" in row["arguments"] for row in scan_calls)
    assert all("--image-src" in row["arguments"] for row in scan_calls)
    assert all("--scanners" in row["arguments"] for row in scan_calls)
    assert all(row["environment"]["TRIVY_OFFLINE_SCAN"] == "true" for row in scan_calls)
    assert all(row["environment"]["TRIVY_SKIP_DB_UPDATE"] == "true" for row in scan_calls)
    assert all(row["environment"]["TRIVY_SKIP_CHECK_UPDATE"] == "true" for row in scan_calls)
    assert all(row["environment"]["TRIVY_IMAGE_SRC"] == "docker" for row in scan_calls)
    assert_verifier_accepts_evidence(monkeypatch, tmp_path / "workspace", output)


def test_unsigned_native_scan_evidence_is_not_release_authoritative(
    monkeypatch,
    tmp_path: Path,
) -> None:
    command, output, _, _, _ = fixture_command(tmp_path)
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    assert completed.returncode == 0, completed.stderr
    monkeypatch.setattr(
        VERIFY_MODULE,
        "inspect_image_digest",
        lambda image_name: (IMAGE_DIGESTS[image_name], None),
    )

    result = VERIFY_MODULE.container_vulnerability_audit(
        VERIFY_MODULE.default_targets(tmp_path / "workspace"),
        output,
    )

    assert result["status"] == "fail"
    assert any("detached" in failure for failure in result["failures"])


def test_grype_producer_disables_database_and_application_updates(monkeypatch, tmp_path: Path) -> None:
    command, output, scanner_log, _, _ = fixture_command(tmp_path, "grype")

    completed = subprocess.run(command, capture_output=True, text=True, check=False)

    assert completed.returncode == 0, completed.stderr
    receipt = json.loads(output.read_text(encoding="utf-8"))
    assert receipt["scanner"]["name"] == "grype"
    scan_calls = [row for row in load_log(scanner_log) if row["arguments"] != ["version"]]
    assert len(scan_calls) == 2
    assert all(row["environment"]["GRYPE_DB_AUTO_UPDATE"] == "false" for row in scan_calls)
    assert all(row["environment"]["GRYPE_CHECK_FOR_APP_UPDATE"] == "false" for row in scan_calls)
    assert all(row["environment"]["GRYPE_DB_CACHE_DIR"] for row in scan_calls)
    assert all(row["environment"]["GRYPE_DEFAULT_IMAGE_PULL_SOURCE"] == "docker" for row in scan_calls)
    assert all(row["arguments"][1:3] == ["--from", "docker"] for row in scan_calls)
    assert_verifier_accepts_evidence(monkeypatch, tmp_path / "workspace", output)


def test_stale_database_fails_before_scanner_is_invoked(tmp_path: Path) -> None:
    command, output, scanner_log, _, _ = fixture_command(
        tmp_path,
        database_timestamp=datetime(2000, 1, 1, tzinfo=UTC),
    )

    completed = subprocess.run(command, capture_output=True, text=True, check=False)

    assert completed.returncode == 1
    receipt = json.loads(output.read_text(encoding="utf-8"))
    assert receipt["status"] == "fail"
    assert "stale" in receipt["failures"][0]
    assert load_log(scanner_log) == []


def test_nonzero_scan_invalidates_prior_pass_receipt(tmp_path: Path) -> None:
    command, output, _, _, _ = fixture_command(tmp_path, scan_exit_code=7)
    output.parent.mkdir(parents=True)
    output.write_text(json.dumps({"contract_name": VERIFY_MODULE.CONTAINER_SCAN_CONTRACT_NAME, "status": "pass"}))

    completed = subprocess.run(command, capture_output=True, text=True, check=False)

    assert completed.returncode == 1
    receipt = json.loads(output.read_text(encoding="utf-8"))
    assert receipt["status"] == "fail"
    assert "exited with code 7" in receipt["failures"][0]
    assert receipt["scans"] == []


def test_native_image_mismatch_is_rejected(tmp_path: Path) -> None:
    command, output, _, _, _ = fixture_command(tmp_path, wrong_digest=True)

    completed = subprocess.run(command, capture_output=True, text=True, check=False)

    assert completed.returncode == 1
    receipt = json.loads(output.read_text(encoding="utf-8"))
    assert receipt["status"] == "fail"
    assert "does not bind the current image digest" in receipt["failures"][0]


def test_image_drift_during_scan_is_rejected(tmp_path: Path) -> None:
    command, output, _, _, _ = fixture_command(
        tmp_path,
        drift_after={"chummer-run-api:local": 2},
    )

    completed = subprocess.run(command, capture_output=True, text=True, check=False)

    assert completed.returncode == 1
    receipt = json.loads(output.read_text(encoding="utf-8"))
    assert receipt["status"] == "fail"
    assert "changed during scan" in receipt["failures"][0]


def test_database_drift_during_scan_is_rejected(tmp_path: Path) -> None:
    command, output, _, _, _ = fixture_command(tmp_path, mutate_database=True)

    completed = subprocess.run(command, capture_output=True, text=True, check=False)

    assert completed.returncode == 1
    receipt = json.loads(output.read_text(encoding="utf-8"))
    assert receipt["status"] == "fail"
    assert "database artifact changed" in receipt["failures"][0]


@pytest.mark.parametrize("scanner", ["trivy", "grype"])
def test_producer_rejects_non_native_database_metadata_path(
    tmp_path: Path,
    scanner: str,
) -> None:
    command, output, scanner_log, _, metadata = fixture_command(tmp_path, scanner)
    alternative_metadata = metadata.with_name("operator-supplied-freshness.json")
    alternative_metadata.write_bytes(metadata.read_bytes())
    metadata_index = command.index("--database-metadata") + 1
    command[metadata_index] = str(alternative_metadata.resolve())

    completed = subprocess.run(command, capture_output=True, text=True, check=False)

    assert completed.returncode == 1
    receipt = json.loads(output.read_text(encoding="utf-8"))
    assert receipt["status"] == "fail"
    assert "native" in receipt["failures"][0]
    assert load_log(scanner_log) == []


def test_release_blocking_native_findings_publish_red_evidence_and_exit_nonzero(tmp_path: Path) -> None:
    command, output, _, _, _ = fixture_command(tmp_path, severity="HIGH")

    completed = subprocess.run(command, capture_output=True, text=True, check=False)

    assert completed.returncode == 1
    receipt = json.loads(output.read_text(encoding="utf-8"))
    assert receipt["status"] == "fail"
    assert receipt["release_blocking_vulnerability_count"] == 2
    assert len(receipt["release_blocking_vulnerabilities"]) == 2
    assert "release-blocking vulnerability" in receipt["failures"][0]


def test_disallowed_extra_scanner_arguments_invalidate_prior_receipt(tmp_path: Path) -> None:
    command, output, scanner_log, _, _ = fixture_command(tmp_path)
    output.parent.mkdir(parents=True)
    output.write_text(json.dumps({"contract_name": VERIFY_MODULE.CONTAINER_SCAN_CONTRACT_NAME, "status": "pass"}))

    completed = subprocess.run(
        [*command, "--severity", "LOW"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 2
    receipt = json.loads(output.read_text(encoding="utf-8"))
    assert receipt["status"] == "fail"
    assert "invalid or disallowed arguments" in receipt["failures"][0]
    assert load_log(scanner_log) == []


@pytest.mark.parametrize(
    ("option", "value"),
    [
        ("--scan-max-age-hours", str(VERIFY_MODULE.CONTAINER_SCAN_MAX_AGE_HOURS + 1)),
        (
            "--database-max-age-hours",
            str(VERIFY_MODULE.CONTAINER_DATABASE_MAX_AGE_HOURS + 1),
        ),
    ],
)
def test_producer_freshness_overrides_can_only_tighten_policy(
    tmp_path: Path,
    option: str,
    value: str,
) -> None:
    command, output, scanner_log, _, _ = fixture_command(tmp_path)
    output.parent.mkdir(parents=True)
    output.write_text(
        json.dumps({"contract_name": VERIFY_MODULE.CONTAINER_SCAN_CONTRACT_NAME, "status": "pass"}),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [*command, option, value],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 2
    receipt = json.loads(output.read_text(encoding="utf-8"))
    assert receipt["status"] == "fail"
    assert "may only be tightened" in receipt["failures"][0]
    assert load_log(scanner_log) == []
