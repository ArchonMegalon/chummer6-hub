from __future__ import annotations

import hashlib
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
INITIALIZER = ROOT / "scripts" / "initialize-public-edge-volumes.sh"
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
RUNTIME_PROOF_SOURCE = "/tmp/proof.json"
APP_OVERLAY_SOURCE = "/tmp/public-download-app"
FLEET_SOURCE = "/tmp/public-download-fleet"
SHELF_SOURCE = "/tmp/public-download-shelf"
PROJECTION_SOURCE = "/tmp/public-download-projection"
FINAL_GOLD_SOURCE = "/tmp/final-gold.json"
PROJECT_NAME = "public-download-op-1234"
DIGESTS = {
    "app_overlay": "4" * 64,
    "fleet": "5" * 64,
    "shelf": "6" * 64,
    "projection": "7" * 64,
    "runtime_proof": "8" * 64,
    "final_gold": "9" * 64,
}
VOLUMES = {
    "app": "public-download-op-app",
    "fleet": "public-download-op-fleet",
    "state": "public-download-op-state",
    "upload_sessions": "public-download-op-upload-sessions",
    "windows_proof": "public-download-op-windows-proof",
    "windows_proof_upload": "public-download-op-windows-proof-upload",
    "runtime_secrets": "public-download-op-runtime-secrets",
    "projection": "public-download-op-projection",
    "proofs": "public-download-op-proofs",
    "shelf": "public-download-op-shelf",
}


def operation_secrets(tmp_path: Path) -> tuple[Path, Path, Path, str, str]:
    operation_root = tmp_path / PROJECT_NAME
    operation_root.mkdir(mode=0o700, exist_ok=True)
    operation_root.chmod(0o700)
    certificate = operation_root / "sidecar-data-protection.pfx"
    password = operation_root / "sidecar-data-protection.password"
    certificate.write_bytes(b"sidecar-only-certificate-fixture\n")
    password.write_bytes(b"sidecar-only-password-fixture\n")
    certificate.chmod(0o600)
    password.chmod(0o600)
    return (
        operation_root,
        certificate,
        password,
        hashlib.sha256(certificate.read_bytes()).hexdigest(),
        hashlib.sha256(password.read_bytes()).hexdigest(),
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


def render(output: Path, tmp_path: Path) -> str:
    (
        _,
        certificate_source,
        certificate_password_source,
        certificate_sha256,
        certificate_password_sha256,
    ) = operation_secrets(tmp_path)
    environment = {
        **os.environ,
        "CHUMMER_PUBLIC_DOWNLOAD_SIDECAR_DP_CERTIFICATE_FILE": str(
            certificate_source
        ),
        "CHUMMER_PUBLIC_DOWNLOAD_SIDECAR_DP_PASSWORD_FILE": str(
            certificate_password_source
        ),
        "CHUMMER_PUBLIC_DOWNLOAD_SIDECAR_DP_CERTIFICATE_SHA256": (
            certificate_sha256
        ),
        "CHUMMER_PUBLIC_DOWNLOAD_SIDECAR_DP_PASSWORD_SHA256": (
            certificate_password_sha256
        ),
        "CHUMMER_PUBLIC_PORTAL_APP_OVERLAY_DIR": APP_OVERLAY_SOURCE,
        "CHUMMER_PUBLIC_DOWNLOAD_APP_OVERLAY_SHA256": DIGESTS["app_overlay"],
        "CHUMMER_PUBLIC_DOWNLOAD_FLEET_SOURCE": FLEET_SOURCE,
        "CHUMMER_PUBLIC_DOWNLOAD_FLEET_SHA256": DIGESTS["fleet"],
        "CHUMMER_PUBLIC_DOWNLOAD_SHELF_SOURCE": SHELF_SOURCE,
        "CHUMMER_PUBLIC_DOWNLOAD_SHELF_SHA256": DIGESTS["shelf"],
        "CHUMMER_PUBLIC_EDGE_PROJECTION_SNAPSHOT_ROOT": PROJECTION_SOURCE,
        "CHUMMER_PUBLIC_EDGE_PROJECTION_SNAPSHOT_SHA256": (
            DIGESTS["projection"]
        ),
        "CHUMMER_PUBLIC_EDGE_RUNTIME_PROOF_BIND_SOURCE": RUNTIME_PROOF_SOURCE,
        "CHUMMER_PUBLIC_EDGE_RUNTIME_PROOF_BIND_SOURCE_SHA256": (
            DIGESTS["runtime_proof"]
        ),
        "CHUMMER_PUBLIC_DOWNLOAD_FINAL_GOLD_SOURCE": FINAL_GOLD_SOURCE,
        "CHUMMER_PUBLIC_DOWNLOAD_FINAL_GOLD_SHA256": DIGESTS["final_gold"],
        "CHUMMER_PUBLIC_DOWNLOAD_APP_VOLUME": VOLUMES["app"],
        "CHUMMER_PUBLIC_DOWNLOAD_FLEET_VOLUME": VOLUMES["fleet"],
        "CHUMMER_PUBLIC_DOWNLOAD_STATE_VOLUME": VOLUMES["state"],
        "CHUMMER_PUBLIC_DOWNLOAD_UPLOAD_SESSIONS_VOLUME": (
            VOLUMES["upload_sessions"]
        ),
        "CHUMMER_PUBLIC_DOWNLOAD_WINDOWS_PROOF_VOLUME": (
            VOLUMES["windows_proof"]
        ),
        "CHUMMER_PUBLIC_DOWNLOAD_WINDOWS_PROOF_UPLOAD_VOLUME": (
            VOLUMES["windows_proof_upload"]
        ),
        "CHUMMER_PUBLIC_DOWNLOAD_RUNTIME_SECRETS_VOLUME": (
            VOLUMES["runtime_secrets"]
        ),
        "CHUMMER_PUBLIC_DOWNLOAD_PROJECTION_VOLUME": VOLUMES["projection"],
        "CHUMMER_PUBLIC_DOWNLOAD_PROOFS_VOLUME": VOLUMES["proofs"],
        "CHUMMER_PUBLIC_DOWNLOAD_SHELF_VOLUME": VOLUMES["shelf"],
    }
    return subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            str(output),
            "--project-name",
            PROJECT_NAME,
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
    (
        operation_root,
        certificate_source,
        certificate_password_source,
        certificate_sha256,
        certificate_password_sha256,
    ) = operation_secrets(tmp_path)
    return subprocess.run(
        [
            sys.executable,
            str(VALIDATOR),
            "--project-name",
            PROJECT_NAME,
            "--operation-root",
            str(operation_root),
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
            "--shelf-source",
            SHELF_SOURCE,
            "--shelf-sha256",
            DIGESTS["shelf"],
            "--certificate-source",
            str(certificate_source),
            "--certificate-password-source",
            str(certificate_password_source),
            "--certificate-sha256",
            certificate_sha256,
            "--certificate-password-sha256",
            certificate_password_sha256,
            "--app-overlay-source",
            APP_OVERLAY_SOURCE,
            "--app-overlay-sha256",
            DIGESTS["app_overlay"],
            "--fleet-source",
            FLEET_SOURCE,
            "--fleet-sha256",
            DIGESTS["fleet"],
            "--projection-source",
            PROJECTION_SOURCE,
            "--projection-sha256",
            DIGESTS["projection"],
            "--runtime-proof-source",
            RUNTIME_PROOF_SOURCE,
            "--runtime-proof-sha256",
            DIGESTS["runtime_proof"],
            "--final-gold-source",
            FINAL_GOLD_SOURCE,
            "--final-gold-sha256",
            DIGESTS["final_gold"],
            "--app-volume",
            VOLUMES["app"],
            "--fleet-volume",
            VOLUMES["fleet"],
            "--state-volume",
            VOLUMES["state"],
            "--upload-sessions-volume",
            VOLUMES["upload_sessions"],
            "--windows-proof-volume",
            VOLUMES["windows_proof"],
            "--windows-proof-upload-volume",
            VOLUMES["windows_proof_upload"],
            "--runtime-secrets-volume",
            VOLUMES["runtime_secrets"],
            "--projection-volume",
            VOLUMES["projection"],
            "--proofs-volume",
            VOLUMES["proofs"],
            "--shelf-volume",
            VOLUMES["shelf"],
            "--output",
            str(tmp_path / "runtime-attestation.json"),
        ],
        cwd=ROOT,
        input=rendered,
        check=check,
        capture_output=True,
        text=True,
    )


def test_materialized_runtime_is_exact_isolated_portal_and_initializer_closure(
    tmp_path: Path,
) -> None:
    output, receipt = materialize(tmp_path)
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert stat.S_IMODE(receipt.stat().st_mode) == 0o600
    assert set(payload["services"]) == {
        "chummer-portal",
        "chummer-public-download-init",
    }
    portal = payload["services"]["chummer-portal"]
    initializer = payload["services"]["chummer-public-download-init"]
    assert portal["image"] == CANDIDATE_IMAGE_ID
    assert initializer["image"] == CANDIDATE_IMAGE_ID
    assert "build" not in portal
    assert "build" not in initializer
    assert "env_file" not in portal
    assert "extra_hosts" not in portal
    assert "group_add" not in portal
    assert portal["network_mode"] == "bridge"
    assert portal["ports"] == ["172.17.0.1:18091:8080"]
    assert "public-download-app:/app:ro" in portal["volumes"]
    assert "public-download-fleet:/fleet-artifacts:ro" in portal["volumes"]
    assert "public-download-shelf:/downloads-source:ro" in portal["volumes"]
    assert portal["environment"]["CHUMMER_RELEASE_DIRECT_BUNDLE_UPLOAD_ENABLED"] == (
        "false"
    )
    assert not any("TOKEN" in key for key in portal["environment"])
    assert portal["environment"]["AllowedHosts"] == (
        "chummer.run;www.chummer.run"
    )
    assert portal["environment"]["CHUMMER_PUBLIC_ALLOWED_HOSTS"] == (
        "chummer.run;www.chummer.run"
    )
    assert "CHUMMER_DATA_PROTECTION_CERTIFICATE_SHA256" not in (
        initializer["environment"]
    )
    assert portal["depends_on"] == {
        "chummer-public-download-init": {
            "condition": "service_completed_successfully"
        }
    }
    assert portal["profiles"] == ["public-downloads"]
    assert initializer["profiles"] == ["public-downloads"]
    assert initializer["network_mode"] == "none"
    assert initializer["read_only"] is True
    assert initializer["cap_add"] == [
        "CHOWN",
        "SETUID",
        "SETGID",
        "DAC_READ_SEARCH",
    ]
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
    assert set(payload["volumes"]) == {
        "public-download-app",
        "public-download-fleet",
        "public-download-state",
        "public-download-upload-sessions",
        "public-download-windows-proof",
        "public-download-windows-proof-upload",
        "public-download-runtime-secrets",
        "public-download-projection",
        "public-download-proofs",
        "public-download-shelf",
    }
    assert all(
        volume["external"] is True
        for volume in payload["volumes"].values()
    )
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


def test_initializer_requires_and_seals_a_read_only_current_shelf() -> None:
    script = INITIALIZER.read_text(encoding="utf-8")

    assert "require_active_release_shelf \"$source\"" in script
    assert "require_active_release_shelf \"$destination\"" in script
    assert ".release-shelf-layout-v1" in script
    assert ".release-shelf-writer-policy.json" in script
    assert "activation-candidate.json" in script
    assert "sidecar-readonly-v1" in script
    assert "printf 'v1\\n'" in script
    assert ".release-shelf-activation-journal" not in script
    assert "targetPointerBase64" not in script
    assert "server-journal-v1" not in script
    assert "chown -R 0:0 -- \"$destination\"" in script
    assert "chmod 0444" in script
    assert "chmod 0555" in script


def test_materialized_runtime_survives_real_compose_render_and_attestation(
    tmp_path: Path,
) -> None:
    output, receipt = materialize(tmp_path)
    rendered = render(output, tmp_path)
    payload = json.loads(rendered)
    assert set(payload["services"]) == {
        "chummer-portal",
        "chummer-public-download-init",
    }
    validate(tmp_path, output=output, receipt=receipt, rendered=rendered)
    attestation = tmp_path / "runtime-attestation.json"
    receipt = json.loads(attestation.read_text(encoding="utf-8"))
    assert receipt["status"] == "pass"
    assert receipt["portalBuildAbsent"] is True
    assert receipt["initializerImageId"] == CANDIDATE_IMAGE_ID
    assert receipt["projectName"] == PROJECT_NAME
    assert receipt["operationRoot"] == str(tmp_path / PROJECT_NAME)
    assert receipt["runtimeInputs"]["certificateAuthority"] == (
        "operation-bound-sidecar-only"
    )
    assert receipt["publishedAddress"] == "172.17.0.1"
    assert receipt["publishedPort"] == 18091
    assert receipt["portalImageId"] == CANDIDATE_IMAGE_ID
    assert receipt["portalAppCopiedReadOnly"] is True
    assert receipt["portalFleetCopiedReadOnly"] is True
    assert receipt["longRunningSourceBindsAbsent"] is True
    assert receipt["releaseShelfPreinitialized"] is True
    assert receipt["releaseShelfPortalReadOnly"] is True
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
            lambda payload: payload["services"]["chummer-portal"].__setitem__(
                "network_mode",
                "host",
            ),
            "isolated network contract drifted",
        ),
        (
            lambda payload: payload["services"]["chummer-portal"].__setitem__(
                "cap_add",
                ["SYS_ADMIN"],
            ),
            "portal field closure drifted",
        ),
        (
            lambda payload: payload["volumes"]["public-download-state"].__setitem__(
                "name",
                "rogue-state",
            ),
            "named-volume authority drifted",
        ),
        (
            lambda payload: payload["services"]["chummer-portal"][
                "environment"
            ].__setitem__("ASPNETCORE_ENVIRONMENT", "Development"),
            "environment allowlist drifted",
        ),
        (
            lambda payload: payload["services"]["chummer-portal"][
                "environment"
            ].__setitem__("AllowedHosts", "chummer.run"),
            "environment allowlist drifted",
        ),
        (
            lambda payload: payload["services"]["chummer-portal"][
                "volumes"
            ][0].update(
                {
                    "type": "bind",
                    "source": APP_OVERLAY_SOURCE,
                }
            ),
            "mount authority drifted",
        ),
        (
            lambda payload: payload["services"][
                "chummer-public-download-init"
            ].__setitem__("cap_add", ["CHOWN", "SYS_ADMIN"]),
            "initializer capability closure drifted",
        ),
    ],
)
def test_runtime_validator_rejects_authority_drift(
    tmp_path: Path,
    mutation: object,
    expected_error: str,
) -> None:
    output, receipt = materialize(tmp_path)
    payload = json.loads(render(output, tmp_path))
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


def test_runtime_validator_rejects_sidecar_certificate_escape(
    tmp_path: Path,
) -> None:
    output, receipt = materialize(tmp_path)
    rendered = render(output, tmp_path)
    _, certificate, _, _, _ = operation_secrets(tmp_path)
    outside = tmp_path / "incumbent-data-protection.pfx"
    outside.write_bytes(b"incumbent-authority\n")
    outside.chmod(0o600)
    certificate.unlink()
    certificate.symlink_to(outside)

    completed = validate(
        tmp_path,
        output=output,
        receipt=receipt,
        rendered=rendered,
        check=False,
    )

    assert completed.returncode != 0
    assert "not contained by the operation root" in completed.stderr
