from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
MATERIALIZER = ROOT / "scripts" / "materialize_public_download_only_compose.py"
VALIDATOR = ROOT / "scripts" / "validate_public_download_only_compose_runtime.py"
BASE_COMPOSE = ROOT / "docker-compose.public-edge.yml"
PROFILE_COMPOSE = ROOT / "docker-compose.public-downloads.yml"
CANDIDATE_IMAGE_ID = "sha256:" + ("1" * 64)
OPERATION = "initial-release-shelf-public-download-cutover"
SOURCE_HEAD = subprocess.run(
    ["git", "rev-parse", "HEAD"],
    cwd=ROOT,
    check=True,
    capture_output=True,
    text=True,
).stdout.strip()
CERTIFICATE_SOURCE = "/tmp/cert.pfx"
CERTIFICATE_PASSWORD_SOURCE = "/tmp/cert.pass"
RUNTIME_PROOF_SOURCE = "/tmp/proof.json"
PROJECTION_SOURCE = (
    "/docker/chummercomplete/chummer.run-services/.codex-studio/published"
)


def materialize(
    tmp_path: Path,
    *,
    source_root: Path = ROOT,
    source: Path = BASE_COMPOSE,
    profile: Path = PROFILE_COMPOSE,
    source_head: str = SOURCE_HEAD,
) -> tuple[Path, Path]:
    output = tmp_path / "runtime.json"
    receipt = tmp_path / "materialization.json"
    subprocess.run(
        [
            sys.executable,
            str(MATERIALIZER),
            "--source-root",
            str(source_root),
            "--source-head",
            source_head,
            "--source",
            str(source),
            "--profile-source",
            str(profile),
            "--output",
            str(output),
            "--receipt-output",
            str(receipt),
            "--candidate-image-id",
            CANDIDATE_IMAGE_ID,
            "--operation",
            OPERATION,
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return output, receipt


def render(output: Path) -> str:
    environment = {
        **os.environ,
        "CHUMMER_DATA_PROTECTION_CERTIFICATE_FILE": CERTIFICATE_SOURCE,
        "CHUMMER_DATA_PROTECTION_CERTIFICATE_PASSWORD_FILE": (
            CERTIFICATE_PASSWORD_SOURCE
        ),
        "CHUMMER_PUBLIC_EDGE_PROJECTION_SNAPSHOT_ROOT": PROJECTION_SOURCE,
        "CHUMMER_PUBLIC_EDGE_RUNTIME_PROOF_BIND_SOURCE": RUNTIME_PROOF_SOURCE,
    }
    return subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            str(output),
            "--project-name",
            "chummer6-hub",
            "--profile",
            "public-downloads",
            "config",
            "--format",
            "json",
        ],
        cwd=ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def validate(
    tmp_path: Path,
    *,
    output: Path,
    receipt: Path,
    rendered: str,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(VALIDATOR),
            "--operation",
            OPERATION,
            "--source-root",
            str(ROOT),
            "--source-head",
            SOURCE_HEAD,
            "--materialized-compose",
            str(output),
            "--materialization-receipt",
            str(receipt),
            "--candidate-image-id",
            CANDIDATE_IMAGE_ID,
            "--certificate-source",
            CERTIFICATE_SOURCE,
            "--certificate-password-source",
            CERTIFICATE_PASSWORD_SOURCE,
            "--runtime-proof-source",
            RUNTIME_PROOF_SOURCE,
            "--output",
            str(tmp_path / "runtime-attestation.json"),
        ],
        cwd=ROOT,
        input=rendered,
        check=check,
        capture_output=True,
        text=True,
    )


def test_materialized_runtime_is_exact_portal_only_build_free_closure(
    tmp_path: Path,
) -> None:
    output, receipt = materialize(tmp_path)
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert stat.S_IMODE(receipt.stat().st_mode) == 0o600
    assert set(payload["services"]) == {"chummer-portal"}
    portal = payload["services"]["chummer-portal"]
    assert portal["image"] == CANDIDATE_IMAGE_ID
    assert "build" not in portal
    assert "depends_on" not in portal
    assert "extra_hosts" not in portal
    assert portal["profiles"] == ["public-downloads"]
    assert portal["healthcheck"]["test"] == [
        "CMD",
        "dotnet",
        "/app/loopback-probe/Chummer.Run.LoopbackProbe.dll",
        "/api/ready/public-downloads",
    ]
    assert all(
        isinstance(token, str) for token in portal["healthcheck"]["test"]
    )
    serialized = json.dumps(payload, sort_keys=True).lower()
    assert "install-linking-postgres" not in serialized
    assert "chummer_install_linking_postgres" not in serialized
    assert (
        portal["environment"]["CHUMMER_RELEASE_SHELF_LAYOUT_V1_REQUIRED"]
        == "true"
    )
    assert (
        portal["environment"]["CHUMMER_RELEASE_SHELF_INITIAL_MIGRATION_ALLOWED"]
        == "false"
    )
    authority = json.loads(receipt.read_text(encoding="utf-8"))
    assert authority["sourceRoot"] == str(ROOT)
    assert authority["sourceHead"] == SOURCE_HEAD
    assert authority["baseComposeSourceSha256"]
    assert authority["profileSourceSha256"]
    assert authority["candidateImageId"] == CANDIDATE_IMAGE_ID


def test_materialized_runtime_survives_real_compose_render_and_attestation(
    tmp_path: Path,
) -> None:
    output, receipt = materialize(tmp_path)
    rendered = render(output)
    payload = json.loads(rendered)
    assert set(payload["services"]) == {"chummer-portal"}
    validate(tmp_path, output=output, receipt=receipt, rendered=rendered)
    attestation = tmp_path / "runtime-attestation.json"
    receipt = json.loads(attestation.read_text(encoding="utf-8"))
    assert receipt["status"] == "pass"
    assert receipt["portalBuildAbsent"] is True
    assert receipt["toolImage"] is None
    assert receipt["portalImageId"] == CANDIDATE_IMAGE_ID
    assert receipt["sourceHead"] == SOURCE_HEAD


def initialize_source_repo(
    root: Path,
    *,
    profile_text: str | None = None,
) -> tuple[Path, Path, str]:
    root.mkdir()
    source = root / BASE_COMPOSE.name
    profile = root / PROFILE_COMPOSE.name
    shutil.copyfile(BASE_COMPOSE, source)
    profile.write_text(
        profile_text
        if profile_text is not None
        else PROFILE_COMPOSE.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "add", source.name, profile.name], cwd=root, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Compose Test",
            "-c",
            "user.email=compose-test@example.invalid",
            "commit",
            "-qm",
            "fixture",
        ],
        cwd=root,
        check=True,
    )
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return source, profile, head


def test_materializer_rejects_profile_tag_drift(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    profile_text = (
        PROFILE_COMPOSE.read_text(encoding="utf-8").replace(
            "volumes: !override",
            "volumes:",
        )
    )
    source, profile, head = initialize_source_repo(
        source_root,
        profile_text=profile_text,
    )
    completed = subprocess.run(
        [
            sys.executable,
            str(MATERIALIZER),
            "--source-root",
            str(source_root),
            "--source-head",
            head,
            "--source",
            str(source),
            "--profile-source",
            str(profile),
            "--output",
            str(tmp_path / "runtime.json"),
            "--receipt-output",
            str(tmp_path / "receipt.json"),
            "--candidate-image-id",
            CANDIDATE_IMAGE_ID,
            "--operation",
            OPERATION,
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode != 0
    assert "profile tag closure drifted" in completed.stderr


def test_materializer_rejects_working_source_drift(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    source, profile, head = initialize_source_repo(source_root)
    profile.write_text(
        profile.read_text(encoding="utf-8") + "\n# uncommitted drift\n",
        encoding="utf-8",
    )
    completed = subprocess.run(
        [
            sys.executable,
            str(MATERIALIZER),
            "--source-root",
            str(source_root),
            "--source-head",
            head,
            "--source",
            str(source),
            "--profile-source",
            str(profile),
            "--output",
            str(tmp_path / "runtime.json"),
            "--receipt-output",
            str(tmp_path / "receipt.json"),
            "--candidate-image-id",
            CANDIDATE_IMAGE_ID,
            "--operation",
            OPERATION,
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode != 0
    assert "not byte-identical to source HEAD" in completed.stderr


@pytest.mark.parametrize(
    ("mutation", "expected_error"),
    [
        (
            lambda payload: payload["services"]["chummer-portal"]["volumes"][1].__setitem__(
                "source",
                "rogue-state",
            ),
            "mount authority drifted",
        ),
        (
            lambda payload: payload["services"]["chummer-portal"]["volumes"][2].__setitem__(
                "read_only",
                False,
            ),
            "mount authority drifted",
        ),
        (
            lambda payload: payload["networks"]["public-origin"].__setitem__(
                "name",
                "rogue-public",
            ),
            "external network authority drifted",
        ),
        (
            lambda payload: payload["services"]["chummer-portal"].__setitem__(
                "cap_add",
                ["SYS_ADMIN"],
            ),
            "portal field closure drifted",
        ),
        (
            lambda payload: payload["volumes"]["chummer-run-api-state"].__setitem__(
                "name",
                "rogue-state",
            ),
            "named-volume authority drifted",
        ),
        (
            lambda payload: payload["services"]["chummer-portal"][
                "environment"
            ].__setitem__("ASPNETCORE_ENVIRONMENT", "Development"),
            "ASPNETCORE_ENVIRONMENT authority drifted",
        ),
    ],
)
def test_runtime_validator_rejects_authority_drift(
    tmp_path: Path,
    mutation: object,
    expected_error: str,
) -> None:
    output, receipt = materialize(tmp_path)
    payload = json.loads(render(output))
    mutation(payload)  # type: ignore[operator]
    completed = validate(
        tmp_path,
        output=output,
        receipt=receipt,
        rendered=json.dumps(payload),
        check=False,
    )
    assert completed.returncode != 0
    assert expected_error in completed.stderr
