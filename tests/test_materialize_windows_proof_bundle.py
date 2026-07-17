from __future__ import annotations

import hashlib
import io
import json
import stat
import subprocess
import sys
import warnings
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "materialize-windows-proof-bundle.py"
SCRIPTS_ROOT = REPO_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

import windows_proof_evidence as windows_evidence  # noqa: E402
VERSION = "run-20260716-115521"
INSTALLER = "chummer-avalonia-win-x64-installer.exe"
PAYLOAD = "chummer-avalonia-win-x64-payload.zip"
URL = (
    "https://chummer.run/downloads/proof/windows/candidates/"
    f"{VERSION}/files/{PAYLOAD}"
)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def make_payload_zip(
    entries: list[tuple[str, bytes]] | None = None,
    *,
    compression: int = zipfile.ZIP_DEFLATED,
) -> bytes:
    target = io.BytesIO()
    options: dict[str, object] = {"compression": compression}
    if compression == zipfile.ZIP_DEFLATED:
        options["compresslevel"] = 6
    with zipfile.ZipFile(target, "w", **options) as archive:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            for name, content in entries or [
                ("app/Chummer.Avalonia.exe", b"MZ-proof-payload\n"),
                ("app/runtimeconfig.json", b'{"runtime":"proof"}\n'),
            ]:
                archive.writestr(name, content)
    return target.getvalue()


def corrupt_first_stored_entry(payload: bytes) -> bytes:
    result = bytearray(payload)
    local = result.find(b"PK\x03\x04")
    assert local >= 0
    method = int.from_bytes(result[local + 8 : local + 10], "little")
    assert method == zipfile.ZIP_STORED
    name_length = int.from_bytes(result[local + 26 : local + 28], "little")
    extra_length = int.from_bytes(result[local + 28 : local + 30], "little")
    data_offset = local + 30 + name_length + extra_length
    assert data_offset < len(result)
    result[data_offset] ^= 0x01
    return bytes(result)


def make_symlink_payload_zip() -> bytes:
    target = io.BytesIO()
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("app/Chummer.Avalonia.exe", b"MZ-proof-payload\n")
        link = zipfile.ZipInfo("app/runtime-link")
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(link, b"runtimeconfig.json")
    return target.getvalue()


def mark_first_zip_entry_encrypted(payload: bytes) -> bytes:
    result = bytearray(payload)
    local = result.find(b"PK\x03\x04")
    central = result.find(b"PK\x01\x02")
    assert local >= 0 and central >= 0
    local_flags = int.from_bytes(result[local + 6 : local + 8], "little") | 0x1
    central_flags = int.from_bytes(result[central + 8 : central + 10], "little") | 0x1
    result[local + 6 : local + 8] = local_flags.to_bytes(2, "little")
    result[central + 8 : central + 10] = central_flags.to_bytes(2, "little")
    return bytes(result)


def mark_first_zip_entry_local_only_encrypted(payload: bytes) -> bytes:
    result = bytearray(payload)
    local = result.find(b"PK\x03\x04")
    assert local >= 0
    flags = int.from_bytes(result[local + 6 : local + 8], "little") | 0x1
    result[local + 6 : local + 8] = flags.to_bytes(2, "little")
    return bytes(result)


def mark_first_zip_entry_central_only_encrypted(payload: bytes) -> bytes:
    result = bytearray(payload)
    central = result.find(b"PK\x01\x02")
    assert central >= 0
    flags = int.from_bytes(result[central + 8 : central + 10], "little") | 0x1
    result[central + 8 : central + 10] = flags.to_bytes(2, "little")
    return bytes(result)


def mismatch_first_zip_entry_local_flags(payload: bytes) -> bytes:
    result = bytearray(payload)
    local = result.find(b"PK\x03\x04")
    assert local >= 0
    flags = int.from_bytes(result[local + 6 : local + 8], "little") ^ 0x8
    result[local + 6 : local + 8] = flags.to_bytes(2, "little")
    return bytes(result)


def mismatch_first_zip_entry_local_method(payload: bytes) -> bytes:
    result = bytearray(payload)
    local = result.find(b"PK\x03\x04")
    central = result.find(b"PK\x01\x02")
    assert local >= 0 and central >= 0
    central_method = int.from_bytes(result[central + 10 : central + 12], "little")
    local_method = zipfile.ZIP_STORED if central_method != zipfile.ZIP_STORED else zipfile.ZIP_DEFLATED
    result[local + 8 : local + 10] = local_method.to_bytes(2, "little")
    return bytes(result)


def mismatch_first_zip_entry_local_name(payload: bytes) -> bytes:
    result = bytearray(payload)
    local = result.find(b"PK\x03\x04")
    assert local >= 0
    name_length = int.from_bytes(result[local + 26 : local + 28], "little")
    assert name_length > 0
    result[local + 30] ^= 0x01
    return bytes(result)


def break_first_zip_entry_local_signature(payload: bytes) -> bytes:
    result = bytearray(payload)
    local = result.find(b"PK\x03\x04")
    assert local >= 0
    result[local] ^= 0x01
    return bytes(result)


def overflow_first_zip_entry_local_name_length(payload: bytes) -> bytes:
    result = bytearray(payload)
    local = result.find(b"PK\x03\x04")
    assert local >= 0
    result[local + 26 : local + 28] = (0xFFFF).to_bytes(2, "little")
    return bytes(result)


def make_stage(
    root: Path,
    *,
    payload_mode: str = "embedded",
    payload_bytes: bytes | None = None,
) -> tuple[Path, str, str]:
    stage = root / "stage"
    payload_bytes = payload_bytes if payload_bytes is not None else make_payload_zip()
    payload_sha = digest(payload_bytes)
    installer_bytes = (
        b"MZ-proof-bootstrap\nCHUMMER6_BOOTSTRAP_METADATA\n"
        + f"payloadFileName={PAYLOAD}\n".encode()
        + f"payloadDownloadUrl={URL}\n".encode()
        + f"payloadSha256={payload_sha}\n".encode()
        + f"payloadSizeBytes={len(payload_bytes)}\n".encode()
        + (b"payloadAcquisitionMode=embedded\n" if payload_mode == "embedded" else b"")
    )
    installer_sha = digest(installer_bytes)
    (stage / "files").mkdir(parents=True)
    (stage / "files" / INSTALLER).write_bytes(installer_bytes)
    (stage / "files" / PAYLOAD).write_bytes(payload_bytes)
    write_json(
        stage / "files" / f"{PAYLOAD}.json",
        {
            "contractName": "chummer6-ui.windows_bootstrap_payload",
            "fileName": PAYLOAD,
            "downloadUrl": URL,
            "sha256": payload_sha,
            "sizeBytes": len(payload_bytes),
            "payloadAcquisitionMode": payload_mode,
            "installerFileName": INSTALLER,
            "releaseVersion": VERSION,
        },
    )
    write_json(
        stage / "signing" / "signing-avalonia-win-x64.receipt.json",
        {
            "contractName": "chummer6-ui.desktop_artifact_signing",
            "platform": "windows",
            "app": "avalonia",
            "rid": "win-x64",
            "releaseChannel": "preview",
            "releaseVersion": VERSION,
            "signingStatus": "skipped_preview",
            "artifacts": [
                {
                    "fileName": INSTALLER,
                    "sha256": installer_sha,
                    "kind": "installer",
                    "signingStatus": "skipped_preview",
                }
            ],
        },
    )
    write_json(
        stage / "startup-smoke" / "startup-smoke-avalonia-win-x64.receipt.json",
        {
            "status": "pass",
            "headId": "avalonia",
            "version": VERSION,
            "releaseVersion": VERSION,
            "channelId": "preview",
            "platform": "windows",
            "rid": "win-x64",
            "artifactId": "avalonia-win-x64-installer",
            "artifactFileName": INSTALLER,
            "artifactRelativePath": f"files/{INSTALLER}",
            "artifactDigest": f"sha256:{installer_sha}",
            "artifactSha256": installer_sha,
            "bootstrapPayloadAcquisitionMode": payload_mode,
            "bootstrapPayloadFileName": PAYLOAD,
            "bootstrapPayloadSha256": payload_sha,
            "bootstrapPayloadSizeBytes": len(payload_bytes),
            "executionEnvironment": "wine_compatibility",
            "verificationScope": "windows_compatibility_startup",
            "nativeHostEvidence": {
                "contractName": "chummer6-ui.native_windows_host_evidence",
                "status": "not_native",
                "isNativeWindows": False,
                "runner": "wine",
            },
        },
    )
    invocation_id = f"{VERSION}.avalonia.win-x64.installer"
    authority_nonce = "9" * 64
    sbom = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "serialNumber": "urn:uuid:00000000-0000-5000-8000-000000000001",
        "version": 1,
        "metadata": {
            "component": {
                "type": "application",
                "bom-ref": "urn:chummer:project:desktop-avalonia",
                "name": "desktop-avalonia",
                "version": VERSION,
            }
        },
        "components": [],
        "dependencies": [
            {"ref": "urn:chummer:project:desktop-avalonia", "dependsOn": []}
        ],
    }
    sbom_path = (
        stage
        / "proof"
        / "build-provenance"
        / "v1"
        / "sbom"
        / "desktop-avalonia.cdx.json"
    )
    write_json(sbom_path, sbom)
    sbom_sha = digest(sbom_path.read_bytes())
    source_commit = "a" * 40
    source_tree = "b" * 40
    generated_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    started_epoch_ns = 1_000_000_000
    state = {
        "state_contract_name": "chummer6.build_provenance_invocation_state.v1",
        "builder_id": "chummer-windows-release-bootstrap",
        "build_type": "windows-desktop-release",
        "invocation_id": invocation_id,
        "release_version": VERSION,
        "authority_nonce": authority_nonce,
        "started_at_utc": generated_at,
        "started_epoch_ns": started_epoch_ns,
        "source": {
            "repository": "chummer-presentation",
            "commit": source_commit,
            "tree": source_tree,
            "tracked_worktree_dirty": False,
            "worktree_dirty": False,
            "untracked_build_inputs_included": True,
        },
        "source_materials": [
            {
                "repository": repository,
                "commit": source_commit,
                "tree": source_tree,
                "tracked_worktree_dirty": False,
                "worktree_dirty": False,
            }
            for repository in (
                "chummer-core-engine",
                "chummer.run-services",
                "chummer-ui-kit",
                "chummer-hub-registry",
                "chummer-media-factory",
                "chummer5a",
            )
        ],
        "subject_declaration": {
            "artifact_id": "avalonia-win-x64-installer",
            "artifact_kind": "desktop_download",
            "artifact_name": INSTALLER,
            "artifact_binding_type": "file",
            "artifact_path": f"files/{INSTALLER}",
            "target_id": "desktop-avalonia",
            "prebuild": {"exists": False},
        },
        "sbom": {
            "path": "proof/build-provenance/v1/sbom/desktop-avalonia.cdx.json",
            "sha256": sbom_sha,
            "generator": "deterministic_project.assets.json_inventory.v1",
        },
        "build_tools": {
            "provenance_generator_sha256": "c" * 64,
            "supply_chain_verifier_sha256": "d" * 64,
        },
        "build_inputs": [
            {"label": label, "sha256": "e" * 64}
            for label in (
                "windows-bootstrap-recipe",
                "desktop-project",
                "desktop-installer-recipe",
                "dotnet-sdk-selection",
            )
        ],
    }
    state_sha = digest(
        json.dumps(state, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    write_json(
        stage
        / "proof"
        / "build-provenance"
        / "v1"
        / "invocations"
        / f"{invocation_id}.json",
        {
            "contract_name": "chummer6.build_provenance.v1",
            "receipt_kind": "invocation",
            "status": "pass",
            "builder_id": "chummer-windows-release-bootstrap",
            "build_type": "windows-desktop-release",
            "invocation_id": invocation_id,
            "release_version": VERSION,
            "generated_at_utc": generated_at,
            "build_started_at_utc": generated_at,
            "authority_nonce": authority_nonce,
            "failures": [],
            "invocation": {
                "state_contract_name": "chummer6.build_provenance_invocation_state.v1",
                "state_sha256": state_sha,
                "state": state,
                "public_projection": "portable_path_references.v1",
                "subject_declared_before_build": True,
                "source_identity_stable": True,
            },
            "subjects": [
                {
                    "artifact_id": "avalonia-win-x64-installer",
                    "artifact_kind": "desktop_download",
                    "artifact_name": INSTALLER,
                    "artifact_sha256": installer_sha,
                    "artifact_size_bytes": len(installer_bytes),
                    "artifact_built_mtime_ns": started_epoch_ns + 1,
                    "release_version": VERSION,
                    "target_id": "desktop-avalonia",
                    "source_repository": "chummer-presentation",
                    "source_commit": source_commit,
                    "source_tree": source_tree,
                    "source_tracked_worktree_dirty": False,
                    "source_worktree_dirty": False,
                    "source_untracked_build_inputs_included": True,
                    "sbom_sha256": sbom_sha,
                    "sbom_generator": "deterministic_project.assets.json_inventory.v1",
                    "invocation_id": invocation_id,
                    "authority_nonce": authority_nonce,
                    "produced_during_invocation": True,
                }
            ],
        },
    )
    write_json(stage / "RELEASE_CHANNEL.generated.json", {"sentinel": "do-not-read-or-mutate"})
    return stage, installer_sha, payload_sha


def run_materializer(stage: Path, output: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--stage-root",
            str(stage),
            "--output-root",
            str(output),
            "--candidate-version",
            VERSION,
        ],
        text=True,
        capture_output=True,
        check=False,
    )


def provenance_path(stage: Path) -> Path:
    return (
        stage
        / "proof"
        / "build-provenance"
        / "v1"
        / "invocations"
        / f"{VERSION}.avalonia.win-x64.installer.json"
    )


def rewrite_provenance_state(stage: Path, mutate: object) -> None:
    path = provenance_path(stage)
    receipt = json.loads(path.read_text(encoding="utf-8"))
    state = receipt["invocation"]["state"]
    mutate(state, receipt)
    receipt["invocation"]["state_sha256"] = digest(
        json.dumps(state, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    write_json(path, receipt)


def test_materializes_eight_role_proof_only_bundle_without_touching_canonical_sentinel(
    tmp_path: Path,
) -> None:
    stage, installer_sha, payload_sha = make_stage(tmp_path)
    sentinel_before = (stage / "RELEASE_CHANNEL.generated.json").read_bytes()
    output = tmp_path / "proof-bundle"

    result = run_materializer(stage, output)

    assert result.returncode == 0, result.stderr
    assert "windows_proof_bundle:ok" in result.stdout
    assert (
        windows_evidence.BOOTSTRAP_ZIP_POLICY_VERSION
        == "chummer6.windows-bootstrap-zip-admission.v1"
    )
    assert (stage / "RELEASE_CHANNEL.generated.json").read_bytes() == sentinel_before
    assert not (output / "RELEASE_CHANNEL.generated.json").exists()
    manifest = json.loads(
        (output / "WINDOWS_PROOF_MANIFEST.generated.json").read_text(encoding="utf-8")
    )
    assert manifest["schemaVersion"] == "chummer.windows-proof.manifest/v2"
    assert manifest["candidateVersion"] == VERSION
    assert manifest["channel"] == "preview"
    assert manifest["releaseScope"] == "proof_only"
    assert manifest["supportabilityState"] == "review_required"
    assert manifest["publicTrustPosture"] == "blocked"
    assert manifest["cfAccessGated"] is True
    assert manifest["proofOnlyPolicy"]["nativeWindowsValidationRequired"] is True
    assert manifest["compatibilitySmoke"]["nativeWindows"] is False
    assert manifest["compatibilitySmoke"]["payloadAcquisitionMode"] == "embedded"
    assert len(manifest["artifacts"]) == 8
    assert manifest["generatedAt"].endswith("Z")
    assert manifest["expiresAt"].endswith("Z")
    by_kind = {row["kind"]: row for row in manifest["artifacts"]}
    assert by_kind["installer"]["sha256"] == installer_sha
    assert by_kind["bootstrap_payload"]["sha256"] == payload_sha
    assert by_kind["build_provenance_receipt"]["relativePath"].endswith(
        f"/{VERSION}.avalonia.win-x64.installer.json"
    )
    assert by_kind["sbom"]["relativePath"].endswith("/desktop-avalonia.cdx.json")
    assert {row["artifactId"] for row in manifest["artifacts"]} == {
        "avalonia-win-x64-installer"
    }
    handoff = json.loads(
        (output / "proof" / "WINDOWS_INSTALLER_VISUAL_PROOF_HANDOFF.generated.json").read_text(
            encoding="utf-8"
        )
    )
    assert handoff["status"] == "ready_for_windows_host"
    assert handoff["only_blocker"] == "visual_proof"
    assert handoff["only_blocker_is_visual_proof"] is True
    assert handoff["blockers"] == []
    assert handoff["release"]["cf_access_gated"] is True
    assert handoff["startup_smoke"]["artifact_id"] == "avalonia-win-x64-installer"
    assert handoff["startup_smoke"]["bootstrap_payload_acquisition_mode"] == "embedded"
    assert handoff["windows_installer"]["sha256"] == f"sha256:{installer_sha}"


def test_rejects_provenance_that_does_not_bind_installer_bytes(tmp_path: Path) -> None:
    stage, _, _ = make_stage(tmp_path)
    receipt_path = (
        stage
        / "proof"
        / "build-provenance"
        / "v1"
        / "invocations"
        / f"{VERSION}.avalonia.win-x64.installer.json"
    )
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["subjects"][0]["artifact_sha256"] = "0" * 64
    write_json(receipt_path, receipt)

    result = run_materializer(stage, tmp_path / "proof-bundle")

    assert result.returncode == 1
    assert "artifact_sha256" in result.stderr


def test_rejects_sbom_changed_after_provenance_finalization(tmp_path: Path) -> None:
    stage, _, _ = make_stage(tmp_path)
    sbom_path = (
        stage
        / "proof"
        / "build-provenance"
        / "v1"
        / "sbom"
        / "desktop-avalonia.cdx.json"
    )
    sbom = json.loads(sbom_path.read_text(encoding="utf-8"))
    sbom["components"].append({"type": "library", "name": "tampered"})
    write_json(sbom_path, sbom)

    result = run_materializer(stage, tmp_path / "proof-bundle")

    assert result.returncode == 1
    assert "SBOM.sha256" in result.stderr


def test_rejects_incomplete_source_material_set_even_with_rehashed_state(tmp_path: Path) -> None:
    stage, _, _ = make_stage(tmp_path)
    rewrite_provenance_state(
        stage,
        lambda state, _receipt: state["source_materials"].pop(),
    )

    result = run_materializer(stage, tmp_path / "proof-bundle")

    assert result.returncode == 1
    assert "exact release repository set" in result.stderr


def test_rejects_incomplete_windows_build_input_set_even_with_rehashed_state(tmp_path: Path) -> None:
    stage, _, _ = make_stage(tmp_path)
    rewrite_provenance_state(
        stage,
        lambda state, _receipt: state["build_inputs"].pop(),
    )

    result = run_materializer(stage, tmp_path / "proof-bundle")

    assert result.returncode == 1
    assert "exact Windows recipe set" in result.stderr


def test_rejects_preexisting_artifact_or_invalid_build_tool_identity(tmp_path: Path) -> None:
    for name, mutate, diagnostic in (
        (
            "preexisting",
            lambda state, _receipt: state["subject_declaration"]["prebuild"].update(
                {"exists": True}
            ),
            "prebuild.exists",
        ),
        (
            "tool",
            lambda state, _receipt: state["build_tools"].update(
                {"provenance_generator_sha256": "invalid"}
            ),
            "build_tools.provenance_generator_sha256",
        ),
    ):
        case_root = tmp_path / name
        stage, _, _ = make_stage(case_root)
        rewrite_provenance_state(stage, mutate)

        result = run_materializer(stage, case_root / "proof-bundle")

        assert result.returncode == 1
        assert diagnostic in result.stderr


def test_rejects_manifest_materialized_before_build_started_at(tmp_path: Path) -> None:
    stage, _, _ = make_stage(tmp_path)
    future = (datetime.now(UTC) + timedelta(minutes=1)).replace(microsecond=0)
    future_text = future.isoformat().replace("+00:00", "Z")

    def move_build_start(state: dict[str, object], receipt: dict[str, object]) -> None:
        state["started_at_utc"] = future_text
        receipt["build_started_at_utc"] = future_text
        receipt["generated_at_utc"] = future_text

    rewrite_provenance_state(stage, move_build_start)

    result = run_materializer(stage, tmp_path / "proof-bundle")

    assert result.returncode == 1
    assert "manifest.generatedAt precedes" in result.stderr


def test_rejects_tampered_smoke_binding_and_leaves_no_partial_output(tmp_path: Path) -> None:
    stage, _, _ = make_stage(tmp_path)
    smoke_path = stage / "startup-smoke" / "startup-smoke-avalonia-win-x64.receipt.json"
    smoke = json.loads(smoke_path.read_text(encoding="utf-8"))
    smoke["artifactSha256"] = "0" * 64
    write_json(smoke_path, smoke)
    output = tmp_path / "proof-bundle"

    result = run_materializer(stage, output)

    assert result.returncode == 1
    assert "artifactSha256 does not match" in result.stderr
    assert not output.exists()


def test_rejects_existing_output_instead_of_merging_stale_files(tmp_path: Path) -> None:
    stage, _, _ = make_stage(tmp_path)
    output = tmp_path / "proof-bundle"
    output.mkdir()
    (output / "stale.txt").write_text("stale", encoding="utf-8")

    result = run_materializer(stage, output)

    assert result.returncode == 1
    assert "output root must not already exist" in result.stderr
    assert (output / "stale.txt").read_text(encoding="utf-8") == "stale"


def test_rejects_symlinked_admitted_artifact(tmp_path: Path) -> None:
    stage, _, _ = make_stage(tmp_path)
    installer = stage / "files" / INSTALLER
    real_installer = tmp_path / "real-installer.exe"
    installer.replace(real_installer)
    installer.symlink_to(real_installer)

    result = run_materializer(stage, tmp_path / "proof-bundle")

    assert result.returncode == 1
    assert "non-symlink regular file" in result.stderr


def test_materializes_self_contained_embedded_payload_evidence(tmp_path: Path) -> None:
    stage, _, _ = make_stage(tmp_path, payload_mode="embedded")
    output = tmp_path / "proof-bundle"

    result = run_materializer(stage, output)

    assert result.returncode == 0, result.stderr
    manifest = json.loads(
        (output / "WINDOWS_PROOF_MANIFEST.generated.json").read_text(encoding="utf-8")
    )
    assert manifest["compatibilitySmoke"]["payloadAcquisitionMode"] == "embedded"
    handoff = json.loads(
        (output / "proof" / "WINDOWS_INSTALLER_VISUAL_PROOF_HANDOFF.generated.json").read_text(
            encoding="utf-8"
        )
    )
    assert handoff["startup_smoke"]["bootstrap_payload_acquisition_mode"] == "embedded"


def test_rejects_download_mode_even_when_legacy_evidence_is_internally_consistent(
    tmp_path: Path,
) -> None:
    stage, _, _ = make_stage(tmp_path, payload_mode="download")

    result = run_materializer(stage, tmp_path / "proof-bundle")

    assert result.returncode == 1
    assert "payloadAcquisitionMode" in result.stderr
    assert "embedded" in result.stderr


def test_rejects_embedded_mode_without_installer_marker(tmp_path: Path) -> None:
    stage, _, _ = make_stage(tmp_path, payload_mode="embedded")
    installer = stage / "files" / INSTALLER
    installer.write_bytes(installer.read_bytes().replace(b"payloadAcquisitionMode=embedded\n", b""))
    installer_digest = digest(installer.read_bytes())
    signing_path = stage / "signing" / "signing-avalonia-win-x64.receipt.json"
    signing = json.loads(signing_path.read_text(encoding="utf-8"))
    signing["artifacts"][0]["sha256"] = installer_digest
    write_json(signing_path, signing)
    smoke_path = stage / "startup-smoke" / "startup-smoke-avalonia-win-x64.receipt.json"
    smoke = json.loads(smoke_path.read_text(encoding="utf-8"))
    smoke["artifactDigest"] = f"sha256:{installer_digest}"
    smoke["artifactSha256"] = installer_digest
    write_json(smoke_path, smoke)

    result = run_materializer(stage, tmp_path / "proof-bundle")

    assert result.returncode == 1
    assert "exact embedded bootstrap metadata trailer" in result.stderr


def test_accepts_clean_public_key_pem_in_bootstrap_payload(tmp_path: Path) -> None:
    payload = make_payload_zip(
        [
            ("app/Chummer.Avalonia.exe", b"MZ-proof-payload\n"),
            (
                "app/public-key.pem",
                b"-----BEGIN PUBLIC KEY-----\nPUBLIC-MATERIAL\n-----END PUBLIC KEY-----\n",
            ),
            (
                "app/empty-sensitive-values.json",
                json.dumps(
                    {
                        "client_secret": "",
                        "authorization": None,
                        "ConnectionStrings": {},
                    }
                ).encode(),
            ),
        ]
    )
    stage, _, _ = make_stage(tmp_path, payload_bytes=payload)

    result = run_materializer(stage, tmp_path / "proof-bundle")

    assert result.returncode == 0, result.stderr


def test_rejects_non_zip_and_unsafe_archive_entries_without_leaking_values(
    tmp_path: Path,
) -> None:
    secret_canary = "secret-canary-that-must-not-be-diagnosed"
    service_account = json.dumps(
        {
            "type": "service_account",
            "project_id": "proof-project",
            "private_key_id": "",
            "private_key": "",
            "client_email": "proof@example.invalid",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    ).encode()
    cases = [
        ("not-zip", b"not a zip archive", "rule=archive.format"),
        ("traversal", make_payload_zip([("../escape.dll", b"x")]), "rule=path.relative"),
        ("absolute", make_payload_zip([("/absolute.dll", b"x")]), "rule=path.relative"),
        ("drive-absolute", make_payload_zip([("C:/escape.dll", b"x")]), "rule=path.relative"),
        ("ads", make_payload_zip([("app/file.txt:stream", b"x")]), "rule=path.windows_invalid_segment"),
        ("control", make_payload_zip([("app/bad\x01name.txt", b"x")]), "rule=path.ascii_printable"),
        ("wildcard", make_payload_zip([("app/bad?.txt", b"x")]), "rule=path.windows_invalid_segment"),
        ("trailing-dot", make_payload_zip([("app/name.", b"x")]), "rule=path.windows_invalid_segment"),
        ("trailing-space", make_payload_zip([("app/name ", b"x")]), "rule=path.windows_invalid_segment"),
        ("reserved-con", make_payload_zip([("app/CON.txt", b"x")]), "rule=path.windows_reserved_device"),
        ("reserved-lpt", make_payload_zip([("app/lpt9.log", b"x")]), "rule=path.windows_reserved_device"),
        (
            "duplicate",
            make_payload_zip([("app/a.dll", b"a"), ("app/a.dll", b"b")]),
            "rule=path.duplicate",
        ),
        (
            "case-collision",
            make_payload_zip([("app/A.dll", b"a"), ("app/a.dll", b"b")]),
            "rule=path.portable_collision",
        ),
        (
            "non-ascii-name",
            make_payload_zip([("app/café.txt", b"a")]),
            "rule=path.ascii_printable",
        ),
        ("symlink", make_symlink_payload_zip(), "rule=entry.symlink"),
        (
            "encrypted",
            mark_first_zip_entry_encrypted(make_payload_zip()),
            "rule=entry.encrypted",
        ),
        (
            "local-only-encrypted",
            mark_first_zip_entry_local_only_encrypted(make_payload_zip()),
            "rule=entry.encrypted",
        ),
        (
            "central-only-encrypted",
            mark_first_zip_entry_central_only_encrypted(make_payload_zip()),
            "rule=entry.encrypted",
        ),
        (
            "local-flags-mismatch",
            mismatch_first_zip_entry_local_flags(make_payload_zip()),
            "rule=entry.flags_binding",
        ),
        (
            "local-method-mismatch",
            mismatch_first_zip_entry_local_method(make_payload_zip()),
            "rule=entry.compression_binding",
        ),
        (
            "local-name-mismatch-redacted",
            mismatch_first_zip_entry_local_name(
                make_payload_zip([(f"app/{secret_canary}.bin", b"safe")])
            ),
            "rule=entry.name_binding",
        ),
        (
            "local-signature",
            break_first_zip_entry_local_signature(make_payload_zip()),
            "rule=entry.local_header",
        ),
        (
            "local-header-bounds",
            overflow_first_zip_entry_local_name_length(make_payload_zip()),
            "rule=entry.local_header_bounds",
        ),
        (
            "corrupt-stored",
            corrupt_first_stored_entry(
                make_payload_zip(
                    [("app/corrupt.bin", b"stored-content")],
                    compression=zipfile.ZIP_STORED,
                )
            ),
            "rule=entry.integrity",
        ),
        ("environment", make_payload_zip([("app/.env.production", b"safe")]), "rule=name.sensitive"),
        (
            "private-container-redacted-name",
            make_payload_zip([(f"app/{secret_canary}.p12", b"safe")]),
            "rule=name.sensitive",
        ),
        (
            "service-account-name",
            make_payload_zip([("app/google-service-account.json", b"{}")]),
            "rule=name.sensitive",
        ),
        (
            "classic-private-key",
            make_payload_zip([("app/notes.txt", b"-----BEGIN RSA PRIVATE KEY-----")]),
            "rule=content.private_key_marker",
        ),
        (
            "encrypted-private-key",
            make_payload_zip([("app/notes.txt", b"-----BEGIN ENCRYPTED PRIVATE KEY-----")]),
            "rule=content.private_key_marker",
        ),
        (
            "pgp-private-key",
            make_payload_zip([("app/notes.txt", b"-----BEGIN PGP PRIVATE KEY BLOCK-----")]),
            "rule=content.private_key_marker",
        ),
        (
            "bearer",
            make_payload_zip(
                [("app/settings.txt", f"Authorization: Bearer {secret_canary}".encode())]
            ),
            "rule=content.bearer_assignment",
        ),
        (
            "refresh-token",
            make_payload_zip(
                [("app/settings.json", json.dumps({"refresh_token": secret_canary}).encode())]
            ),
            "rule=content.credential_assignment",
        ),
        (
            "access-token",
            make_payload_zip(
                [("app/settings.json", json.dumps({"access-token": secret_canary}).encode())]
            ),
            "rule=content.credential_assignment",
        ),
        (
            "short-client-secret",
            make_payload_zip([("app/settings.txt", b"client_secret=x")]),
            "rule=content.credential_assignment",
        ),
        (
            "symbolic-client-secret",
            make_payload_zip(
                [("app/settings.txt", b"client_secret=${CLIENT_SECRET}")]
            ),
            "rule=content.credential_assignment",
        ),
        (
            "binary-client-secret",
            make_payload_zip(
                [
                    (
                        "app/native.dll",
                        b"MZ\x00\x01client_secret="
                        + secret_canary.encode()
                        + b"\x00\xff\x10",
                    )
                ]
            ),
            "rule=content.credential_assignment",
        ),
        (
            "connection-string",
            make_payload_zip(
                [("app/settings.txt", f"connection_string={secret_canary}".encode())]
            ),
            "rule=content.connection_string_assignment",
        ),
        (
            "structural-service-account",
            make_payload_zip([("app/innocent.dat", service_account)]),
            "rule=content.google_service_account_json",
        ),
        (
            "nested-sensitive-json-key",
            make_payload_zip(
                [
                    (
                        "app/innocent.json",
                        json.dumps(
                            {"outer": [{"client.secret": {"source": "provider"}}]}
                        ).encode(),
                    )
                ]
            ),
            "rule=content.sensitive_json_value",
        ),
    ]

    for name, payload_bytes, expected_rule in cases:
        case_root = tmp_path / name
        stage, _, _ = make_stage(case_root, payload_bytes=payload_bytes)
        output = case_root / "proof-bundle"

        result = run_materializer(stage, output)

        assert result.returncode == 1, name
        assert expected_rule in result.stderr, (name, result.stderr)
        assert (
            f"policy={windows_evidence.BOOTSTRAP_ZIP_POLICY_VERSION}"
            in result.stderr
        )
        if name != "not-zip":
            assert "entry_ordinal=" in result.stderr
            assert "entry_name_sha256=" in result.stderr
        assert secret_canary not in result.stderr
        assert not output.exists()


def test_shared_zip_policy_enforces_each_resource_bound(tmp_path: Path) -> None:
    payload_path = tmp_path / PAYLOAD
    cases = [
        (
            "rule=archive.size",
            make_payload_zip(),
            "BOOTSTRAP_ZIP_MAX_ARCHIVE_BYTES",
            1,
        ),
        (
            "rule=archive.entry_count",
            make_payload_zip([("app/a", b"a"), ("app/b", b"b")]),
            "BOOTSTRAP_ZIP_MAX_ENTRIES",
            1,
        ),
        (
            "rule=entry.decompressed_size",
            make_payload_zip([("app/a", b"abcd")]),
            "BOOTSTRAP_ZIP_MAX_ENTRY_BYTES",
            3,
        ),
        (
            "rule=archive.decompressed_size",
            make_payload_zip([("app/a", b"abc"), ("app/b", b"def")]),
            "BOOTSTRAP_ZIP_MAX_TOTAL_BYTES",
            5,
        ),
        (
            "rule=entry.compression_ratio",
            make_payload_zip([("app/a", b"0" * 10_000)]),
            "BOOTSTRAP_ZIP_MAX_COMPRESSION_RATIO",
            1,
        ),
        (
            "rule=archive.central_directory_size",
            make_payload_zip([("app/a", b"x")]),
            "BOOTSTRAP_ZIP_MAX_CENTRAL_DIRECTORY_BYTES",
            1,
        ),
        (
            "rule=content.text_inspection_size",
            make_payload_zip([("app/a.txt", b"abcdef")]),
            "BOOTSTRAP_ZIP_MAX_INSPECTABLE_TEXT_BYTES",
            4,
        ),
        (
            "rule=content.json_inspection_size",
            make_payload_zip([("app/a.json", b'{"a":"b"}')]),
            "BOOTSTRAP_ZIP_MAX_INSPECTABLE_TEXT_BYTES",
            4,
        ),
    ]

    for expected_rule, payload_bytes, setting, value in cases:
        payload_path.write_bytes(payload_bytes)
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(windows_evidence, setting, value)
            with pytest.raises(ValueError) as error:
                windows_evidence.validate_bootstrap_payload_zip(payload_path)
        assert expected_rule in str(error.value)
        assert windows_evidence.BOOTSTRAP_ZIP_POLICY_VERSION in str(error.value)


def test_shared_zip_policy_streams_known_binary_past_inspection_limit(
    tmp_path: Path,
) -> None:
    payload_path = tmp_path / PAYLOAD
    payload_path.write_bytes(
        make_payload_zip([("app/native.dll", b"MZ\x00\x01\xff\x10")])
    )

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(
            windows_evidence,
            "BOOTSTRAP_ZIP_MAX_INSPECTABLE_TEXT_BYTES",
            4,
        )
        windows_evidence.validate_bootstrap_payload_zip(payload_path)
