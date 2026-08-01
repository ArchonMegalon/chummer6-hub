from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
GENERATOR = REPO_ROOT / "scripts" / "release" / "materialize_build_provenance.py"
SUPPORT = REPO_ROOT / "scripts" / "release" / "build_provenance_support.py"
VALIDATOR = REPO_ROOT / "scripts" / "release" / "verify_release_build_provenance_bundle.py"
BOOTSTRAP = (
    REPO_ROOT
    / "Chummer.Run.Api"
    / "wwwroot"
    / "artifacts"
    / "mac-codex-release-pipeline"
    / "bootstrap.sh"
)
SERVER_VALIDATOR = REPO_ROOT / "Chummer.Run.Api" / "Services" / "ReleaseBuildProvenanceValidator.cs"
UPLOAD_CONTROLLER = REPO_ROOT / "Chummer.Run.Api" / "Controllers" / "InternalReleaseBundlesController.cs"


def test_portal_public_promotion_receipt_references_are_portable() -> None:
    evidence_path = REPO_ROOT / "Chummer.Portal" / "downloads" / "release-evidence" / "public-promotion.json"
    payload = json.loads(evidence_path.read_text(encoding="utf-8"))

    for artifact in payload.get("artifacts") or []:
        for field, expected_root in (
            ("startupSmokeReceiptPath", "startup-smoke/"),
            ("signingReceiptPath", "signing/"),
        ):
            reference = str(artifact.get(field) or "")
            if not reference:
                continue
            assert reference.startswith(expected_root)
            assert not Path(reference).is_absolute()
            assert "\\" not in reference
            assert ".." not in reference.split("/")


def init_repo(path: Path, files: dict[str, str] | None = None) -> None:
    path.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.email", "test@example.invalid"], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "Provenance Test"], check=True)
    for relative, content in (files or {"README.md": "fixture\n"}).items():
        target = path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    subprocess.run(["git", "-C", str(path), "add", "."], check=True)
    subprocess.run(["git", "-C", str(path), "commit", "-qm", "fixture"], check=True)


def make_primary_repo(path: Path) -> Path:
    project = path / "App" / "App.csproj"
    assets = project.parent / "obj" / "project.assets.json"
    init_repo(
        path,
        {
            ".gitignore": "**/obj/\ndist/\n",
            "App/App.csproj": '<Project Sdk="Microsoft.NET.Sdk" />\n',
            "scripts/build-desktop-installer.sh": "#!/usr/bin/env bash\nexit 0\n",
            "bootstrap.sh": "#!/usr/bin/env bash\nexit 0\n",
            "global.json": '{"sdk":{"version":"10.0.100"}}\n',
        },
    )
    assets.parent.mkdir(parents=True, exist_ok=True)
    assets.write_text(
        json.dumps(
            {
                "version": 3,
                "targets": {"net10.0": {"Example.Package/1.0.0": {"type": "package", "dependencies": {}}}},
                "libraries": {
                    "Example.Package/1.0.0": {
                        "type": "package",
                        "sha512": "",
                        "path": "example.package/1.0.0",
                    }
                },
                "project": {"version": "1.0.0", "restore": {"projectPath": str(project)}},
            }
        ),
        encoding="utf-8",
    )
    return project


def common_begin_args(
    *,
    primary: Path,
    project: Path,
    artifact: Path,
    state: Path,
    receipt: Path,
    sbom: Path,
    source_materials: dict[str, Path] | None = None,
) -> list[str]:
    command = [
        sys.executable,
        str(GENERATOR),
        "begin",
        "--state",
        str(state),
        "--output",
        str(receipt),
        "--builder-id",
        "chummer-mac-hosted-bootstrap",
        "--build-type",
        "macos-desktop-release",
        "--invocation-id",
        "run-test.avalonia.osx-arm64.installer",
        "--support-script",
        str(SUPPORT),
        "--source-repository",
        "chummer-presentation",
        "--source-repo-root",
        str(primary),
        "--build-root",
        str(primary),
        "--target-id",
        "desktop-avalonia",
        "--project-path",
        str(project.relative_to(primary)),
        "--artifact-id",
        "avalonia-osx-arm64-installer",
        "--artifact-kind",
        "desktop_download",
        "--artifact-name",
        artifact.name,
        "--artifact-path",
        str(artifact),
        "--sbom-path",
        str(sbom),
        "--build-input",
        f"hosted-bootstrap={primary / 'bootstrap.sh'}",
        "--build-input",
        f"desktop-project={project}",
        "--build-input",
        f"desktop-installer-recipe={primary / 'scripts/build-desktop-installer.sh'}",
        "--build-input",
        f"dotnet-sdk-selection={primary / 'global.json'}",
    ]
    for name, material_path in (source_materials or {}).items():
        command.extend(["--source-material", f"{name}={material_path}"])
    return command


def finalize_args(state: Path, receipt: Path) -> list[str]:
    return [
        sys.executable,
        str(GENERATOR),
        "finalize",
        "--state",
        str(state),
        "--output",
        str(receipt),
        "--builder-id",
        "chummer-mac-hosted-bootstrap",
        "--build-type",
        "macos-desktop-release",
        "--invocation-id",
        "run-test.avalonia.osx-arm64.installer",
    ]


def test_portable_generator_and_bundle_validator_bind_final_artifact_bytes(tmp_path: Path) -> None:
    primary = tmp_path / "primary"
    project = make_primary_repo(primary)
    material_names = (
        "chummer-core-engine",
        "chummer.run-services",
        "chummer-ui-kit",
        "chummer-hub-registry",
        "chummer-media-factory",
        "chummer5a",
    )
    materials: dict[str, Path] = {}
    for name in material_names:
        material = tmp_path / "materials" / name
        init_repo(material)
        materials[name] = material

    bundle = primary / "dist" / "promotion-bundle"
    artifact = bundle / "files" / "chummer-avalonia-osx-arm64-installer.dmg"
    invocation_id = "run-test.avalonia.osx-arm64.installer"
    receipt = bundle / "proof" / "build-provenance" / "v1" / "invocations" / f"{invocation_id}.json"
    sbom = bundle / "proof" / "build-provenance" / "v1" / "sbom" / "desktop-avalonia.cdx.json"
    state = tmp_path / "state.json"

    begun = subprocess.run(
        common_begin_args(
            primary=primary,
            project=project,
            artifact=artifact,
            state=state,
            receipt=receipt,
            sbom=sbom,
            source_materials=materials,
        ),
        capture_output=True,
        text=True,
        check=False,
    )
    assert begun.returncode == 0, begun.stderr
    assert json.loads(receipt.read_text(encoding="utf-8"))["status"] == "in_progress"

    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_bytes(b"final-dmg-bytes")
    os.utime(artifact, None)
    finalized = subprocess.run(finalize_args(state, receipt), capture_output=True, text=True, check=False)
    assert finalized.returncode == 0, finalized.stderr

    artifact_sha = hashlib.sha256(artifact.read_bytes()).hexdigest()
    manifest_path = bundle / "RELEASE_CHANNEL.generated.json"
    manifest_payload = {
        "artifacts": [
            {
                "artifactId": "avalonia-osx-arm64-installer",
                "head": "avalonia",
                "platform": "macos",
                "rid": "osx-arm64",
                "kind": "installer",
                "fileName": artifact.name,
                "sha256": artifact_sha,
                "sizeBytes": artifact.stat().st_size,
            }
        ]
    }
    manifest_path.write_text(json.dumps(manifest_payload), encoding="utf-8")
    validated = subprocess.run(
        [sys.executable, str(VALIDATOR), str(bundle)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert validated.returncode == 0, validated.stderr
    assert "build_provenance_bundle=pass" in validated.stdout

    receipt_payload = json.loads(receipt.read_text(encoding="utf-8"))
    serialized_receipt = json.dumps(receipt_payload, sort_keys=True)
    assert str(tmp_path) not in serialized_receipt
    assert "\\\\" not in serialized_receipt
    assert receipt_payload["invocation"]["public_projection"] == "portable_path_references.v1"
    public_state = receipt_payload["invocation"]["state"]
    assert public_state["source"]["repo_root"] == "sources/chummer-presentation"
    assert public_state["subject_declaration"]["artifact_path"] == f"files/{artifact.name}"
    assert public_state["sbom"]["path"] == "proof/build-provenance/v1/sbom/desktop-avalonia.cdx.json"
    assert all(
        str(item["repo_root"]).startswith("sources/")
        for item in public_state["source_materials"]
    )
    assert all(
        str(item["path"]).startswith("build-inputs/")
        for item in public_state["build_inputs"]
    )
    subject = receipt_payload["subjects"][0]
    assert subject["artifact_sha256"] == artifact_sha
    assert subject["artifact_size_bytes"] == artifact.stat().st_size
    assert subject["produced_during_invocation"] is True
    assert {item["repository"] for item in subject["source_materials"]} == set(material_names)

    workspace_supply_chain = Path("/docker/chummercomplete/scripts/release/verify_supply_chain_evidence.py")
    if workspace_supply_chain.is_file():
        spec = importlib.util.spec_from_file_location("workspace_supply_chain_for_mac_provenance_test", workspace_supply_chain)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        subjects, failures = module.validate_invocation_provenance_payload(receipt_payload)
        assert failures == []
        assert set(subjects) == {"avalonia-osx-arm64-installer"}
        assets_payload = json.loads((project.parent / "obj" / "project.assets.json").read_text(encoding="utf-8"))
        target = module.ProjectTarget(
            "desktop-avalonia",
            "desktop",
            "chummer-presentation",
            primary,
            project,
        )
        expected_sbom = module.build_cyclonedx(
            target,
            assets_payload,
            module.dependency_inventory_sha256(assets_payload),
        )
        assert json.loads(sbom.read_text(encoding="utf-8")) == expected_sbom

    def validator_failure() -> str:
        result = subprocess.run(
            [sys.executable, str(VALIDATOR), str(bundle)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 1
        return result.stderr

    def clone_receipt() -> dict[str, object]:
        return json.loads(json.dumps(receipt_payload))

    def refresh_state_digest(payload: dict[str, object]) -> None:
        invocation = payload["invocation"]
        state_payload = invocation["state"]
        invocation["state_sha256"] = hashlib.sha256(
            json.dumps(state_payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        ).hexdigest()

    for field, invalid_value in (
        ("builder_id", "unexpected-builder"),
        ("build_type", "unexpected-build-type"),
    ):
        invalid_identity = clone_receipt()
        invalid_identity[field] = invalid_value
        invalid_identity["invocation"]["state"][field] = invalid_value
        refresh_state_digest(invalid_identity)
        receipt.write_text(json.dumps(invalid_identity), encoding="utf-8")
        assert "invocation contract is invalid" in validator_failure()

    invalid_source = clone_receipt()
    invalid_source["subjects"][0]["source_commit"] = "0" * 40
    receipt.write_text(json.dumps(invalid_source), encoding="utf-8")
    assert "subject identity mismatch" in validator_failure()

    invalid_epoch = clone_receipt()
    invalid_epoch["invocation"]["state"]["started_epoch_ns"] = 0
    refresh_state_digest(invalid_epoch)
    receipt.write_text(json.dumps(invalid_epoch), encoding="utf-8")
    assert "artifact production time is invalid" in validator_failure()

    artifact.write_bytes(b"")
    empty_sha = hashlib.sha256(b"").hexdigest()
    empty_manifest = json.loads(json.dumps(manifest_payload))
    empty_manifest["artifacts"][0]["sha256"] = empty_sha
    empty_manifest["artifacts"][0]["sizeBytes"] = 0
    manifest_path.write_text(json.dumps(empty_manifest), encoding="utf-8")
    empty_receipt = clone_receipt()
    empty_receipt["subjects"][0]["artifact_sha256"] = empty_sha
    empty_receipt["subjects"][0]["artifact_size_bytes"] = 0
    receipt.write_text(json.dumps(empty_receipt), encoding="utf-8")
    assert "artifact row is incomplete" in validator_failure()

    artifact.write_bytes(b"final-dmg-bytes")
    manifest_path.write_text(json.dumps(manifest_payload), encoding="utf-8")
    receipt.write_text(json.dumps(receipt_payload), encoding="utf-8")

    artifact.write_bytes(b"tampered")
    rejected = subprocess.run(
        [sys.executable, str(VALIDATOR), str(bundle)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert rejected.returncode == 1
    assert "artifact identity does not match" in rejected.stderr


def test_bundle_validator_requires_linux_windows_and_payload_provenance(tmp_path: Path) -> None:
    primary = tmp_path / "primary"
    project = make_primary_repo(primary)
    material_names = (
        "chummer-core-engine",
        "chummer.run-services",
        "chummer-ui-kit",
        "chummer-hub-registry",
        "chummer-media-factory",
        "chummer5a",
    )
    materials: dict[str, Path] = {}
    for name in material_names:
        material = tmp_path / "materials" / name
        init_repo(material)
        materials[name] = material

    bundle = primary / "dist" / "promotion-bundle"
    proof_root = bundle / "proof" / "build-provenance" / "v1"
    artifacts = (
        {
            "artifact_id": "avalonia-linux-x64-installer",
            "artifact_kind": "desktop_download",
            "artifact_name": "chummer-avalonia-linux-x64-installer.deb",
            "builder_id": "chummer-linux-desktop-exit-gate",
            "build_type": "chummer6.desktop.linux-self-contained-installer",
            "invocation_id": "run-test.avalonia.linux-x64.installer",
            "inputs": {"source_snapshot_manifest": primary / "bootstrap.sh"},
            "bytes": b"linux-installer-bytes",
        },
        {
            "artifact_id": "avalonia-win-x64-installer",
            "artifact_kind": "desktop_download",
            "artifact_name": "chummer-avalonia-win-x64-installer.exe",
            "builder_id": "chummer-windows-release-bootstrap",
            "build_type": "windows-desktop-release",
            "invocation_id": "run-test.avalonia.win-x64.installer",
            "inputs": {
                "desktop-project": project,
                "desktop-installer-recipe": primary / "scripts" / "build-desktop-installer.sh",
                "windows-bootstrap-recipe": primary / "bootstrap.sh",
                "dotnet-sdk-selection": primary / "global.json",
            },
            "bytes": b"windows-installer-bytes",
        },
        {
            "artifact_id": "avalonia-win-x64-installer-payload",
            "artifact_kind": "desktop_payload",
            "artifact_name": "chummer-avalonia-win-x64-payload.zip",
            "builder_id": "chummer-windows-release-bootstrap",
            "build_type": "windows-desktop-release",
            "invocation_id": "run-test.avalonia.win-x64.payload",
            "inputs": {
                "desktop-project": project,
                "desktop-installer-recipe": primary / "scripts" / "build-desktop-installer.sh",
                "windows-bootstrap-recipe": primary / "bootstrap.sh",
                "dotnet-sdk-selection": primary / "global.json",
            },
            "bytes": b"windows-payload-bytes",
        },
    )

    for artifact_spec in artifacts:
        artifact = bundle / "files" / str(artifact_spec["artifact_name"])
        sbom = proof_root / "sbom" / f"{artifact_spec['artifact_id']}.cdx.json"
        invocation_id = str(artifact_spec["invocation_id"])
        receipt = proof_root / "invocations" / f"{invocation_id}.json"
        state = tmp_path / f"{invocation_id}.state.json"
        command = [
            sys.executable,
            str(GENERATOR),
            "begin",
            "--state",
            str(state),
            "--output",
            str(receipt),
            "--builder-id",
            str(artifact_spec["builder_id"]),
            "--build-type",
            str(artifact_spec["build_type"]),
            "--invocation-id",
            invocation_id,
            "--support-script",
            str(SUPPORT),
            "--source-repository",
            "chummer-presentation",
            "--source-repo-root",
            str(primary),
            "--build-root",
            str(primary),
            "--target-id",
            "desktop-avalonia",
            "--project-path",
            str(project.relative_to(primary)),
            "--artifact-id",
            str(artifact_spec["artifact_id"]),
            "--artifact-kind",
            str(artifact_spec["artifact_kind"]),
            "--artifact-name",
            str(artifact_spec["artifact_name"]),
            "--artifact-path",
            str(artifact),
            "--sbom-path",
            str(sbom),
        ]
        for name, path in materials.items():
            command.extend(["--source-material", f"{name}={path}"])
        for name, path in dict(artifact_spec["inputs"]).items():
            command.extend(["--build-input", f"{name}={path}"])
        begun = subprocess.run(command, capture_output=True, text=True, check=False)
        assert begun.returncode == 0, begun.stderr
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_bytes(bytes(artifact_spec["bytes"]))
        os.utime(artifact, None)
        finalized = subprocess.run(
            [
                sys.executable,
                str(GENERATOR),
                "finalize",
                "--state",
                str(state),
                "--output",
                str(receipt),
                "--builder-id",
                str(artifact_spec["builder_id"]),
                "--build-type",
                str(artifact_spec["build_type"]),
                "--invocation-id",
                invocation_id,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert finalized.returncode == 0, finalized.stderr

    linux = bundle / "files" / "chummer-avalonia-linux-x64-installer.deb"
    windows = bundle / "files" / "chummer-avalonia-win-x64-installer.exe"
    payload = bundle / "files" / "chummer-avalonia-win-x64-payload.zip"
    manifest = {
        "artifacts": [
            {
                "artifactId": "avalonia-linux-x64-installer",
                "head": "avalonia",
                "platform": "linux",
                "rid": "linux-x64",
                "kind": "installer",
                "fileName": linux.name,
                "sha256": hashlib.sha256(linux.read_bytes()).hexdigest(),
                "sizeBytes": linux.stat().st_size,
            },
            {
                "artifactId": "avalonia-win-x64-installer",
                "head": "avalonia",
                "platform": "windows",
                "rid": "win-x64",
                "kind": "installer",
                "fileName": windows.name,
                "sha256": hashlib.sha256(windows.read_bytes()).hexdigest(),
                "sizeBytes": windows.stat().st_size,
                "payloadFileName": payload.name,
                "payloadSha256": hashlib.sha256(payload.read_bytes()).hexdigest(),
                "payloadSizeBytes": payload.stat().st_size,
            },
        ]
    }
    (bundle / "RELEASE_CHANNEL.generated.json").write_text(json.dumps(manifest), encoding="utf-8")

    validated = subprocess.run(
        [sys.executable, str(VALIDATOR), str(bundle)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert validated.returncode == 0, validated.stderr

    payload.write_bytes(b"tampered-payload")
    rejected = subprocess.run(
        [sys.executable, str(VALIDATOR), str(bundle)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert rejected.returncode == 1
    assert "payload identity does not match" in rejected.stderr


def test_generator_fails_closed_when_source_changes_after_begin(tmp_path: Path) -> None:
    primary = tmp_path / "primary"
    project = make_primary_repo(primary)
    artifact = primary / "dist" / "files" / "artifact.dmg"
    receipt = tmp_path / "receipt.json"
    state = tmp_path / "state.json"
    sbom = tmp_path / "sbom.json"
    begun = subprocess.run(
        common_begin_args(
            primary=primary,
            project=project,
            artifact=artifact,
            state=state,
            receipt=receipt,
            sbom=sbom,
        ),
        capture_output=True,
        text=True,
        check=False,
    )
    assert begun.returncode == 0, begun.stderr
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"artifact")
    project.write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup /></Project>\n', encoding="utf-8")

    finalized = subprocess.run(finalize_args(state, receipt), capture_output=True, text=True, check=False)
    assert finalized.returncode == 1
    payload = json.loads(receipt.read_text(encoding="utf-8"))
    assert payload["status"] == "fail"
    assert payload["subjects"] == []
    assert any("source revision changed or became dirty" in failure for failure in payload["failures"])


def test_generator_rejects_nonignored_untracked_source_at_begin(tmp_path: Path) -> None:
    primary = tmp_path / "primary"
    project = make_primary_repo(primary)
    (primary / "App" / "InjectedCompile.cs").write_text("internal class InjectedCompile {}\n", encoding="utf-8")

    receipt = tmp_path / "receipt.json"
    begun = subprocess.run(
        common_begin_args(
            primary=primary,
            project=project,
            artifact=primary / "dist" / "files" / "artifact.dmg",
            state=tmp_path / "state.json",
            receipt=receipt,
            sbom=tmp_path / "sbom.json",
        ),
        capture_output=True,
        text=True,
        check=False,
    )

    assert begun.returncode == 1
    payload = json.loads(receipt.read_text(encoding="utf-8"))
    assert payload["status"] == "fail"
    assert any("source repository has worktree changes" in failure for failure in payload["failures"])


def test_generator_rejects_nonignored_untracked_material_at_finalize(tmp_path: Path) -> None:
    primary = tmp_path / "primary"
    project = make_primary_repo(primary)
    material = tmp_path / "material"
    init_repo(material)
    artifact = primary / "dist" / "files" / "artifact.dmg"
    receipt = tmp_path / "receipt.json"
    state = tmp_path / "state.json"
    begun = subprocess.run(
        common_begin_args(
            primary=primary,
            project=project,
            artifact=artifact,
            state=state,
            receipt=receipt,
            sbom=tmp_path / "sbom.json",
            source_materials={"chummer-core-engine": material},
        ),
        capture_output=True,
        text=True,
        check=False,
    )
    assert begun.returncode == 0, begun.stderr

    (material / "Directory.Build.props").write_text("<Project />\n", encoding="utf-8")
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_bytes(b"artifact")
    finalized = subprocess.run(finalize_args(state, receipt), capture_output=True, text=True, check=False)

    assert finalized.returncode == 1
    payload = json.loads(receipt.read_text(encoding="utf-8"))
    assert payload["status"] == "fail"
    assert payload["subjects"] == []
    assert any("source material changed or became dirty" in failure for failure in payload["failures"])


def test_localization_gate_regeneration_restores_clean_checkout_on_success_and_failure(tmp_path: Path) -> None:
    ui_repo = tmp_path / "ui"
    original_gate = '{"status":"stale","generatedAt":"2020-01-01T00:00:00Z"}\n'
    init_repo(
        ui_repo,
        {
            ".codex-studio/published/UI_LOCALIZATION_RELEASE_GATE.generated.json": original_gate,
            "scripts/ai/milestones/b15-localization-release-gate.sh": """#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd -P)"
printf '%s\\n' '{"status":"pass","generatedAt":"2099-01-01T00:00:00Z"}' >"$repo_root/.codex-studio/published/UI_LOCALIZATION_RELEASE_GATE.generated.json"
if [[ "${FAIL_LOCALIZATION_GATE:-0}" == "1" ]]; then
  exit 19
fi
""",
        },
    )
    temporary_root = tmp_path / "tmp"
    temporary_root.mkdir()
    command = 'source "$1"; generated="$(generate_ui_localization_release_gate "$2")"; printf "%s\\n" "$generated"'
    environment = {**os.environ, "TMPDIR": str(temporary_root)}

    generated = subprocess.run(
        ["bash", "-c", command, "gate-test", str(BOOTSTRAP), str(ui_repo)],
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )
    assert generated.returncode == 0, generated.stderr
    captured_path = Path(generated.stdout.strip().splitlines()[-1])
    assert json.loads(captured_path.read_text(encoding="utf-8"))["status"] == "pass"
    assert (ui_repo / ".codex-studio/published/UI_LOCALIZATION_RELEASE_GATE.generated.json").read_text(
        encoding="utf-8"
    ) == original_gate
    assert subprocess.run(
        ["git", "-C", str(ui_repo), "status", "--porcelain", "--untracked-files=all"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout == ""
    captured_path.unlink()
    assert list(temporary_root.iterdir()) == []

    failed = subprocess.run(
        ["bash", "-c", command, "gate-test", str(BOOTSTRAP), str(ui_repo)],
        capture_output=True,
        text=True,
        check=False,
        env={**environment, "FAIL_LOCALIZATION_GATE": "1"},
    )
    assert failed.returncode != 0
    assert (ui_repo / ".codex-studio/published/UI_LOCALIZATION_RELEASE_GATE.generated.json").read_text(
        encoding="utf-8"
    ) == original_gate
    assert subprocess.run(
        ["git", "-C", str(ui_repo), "status", "--porcelain", "--untracked-files=all"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout == ""
    assert list(temporary_root.iterdir()) == []


def test_provenance_records_the_executed_bootstrap_not_the_cloned_copy(tmp_path: Path) -> None:
    generator = tmp_path / "capture_generator.py"
    generator.write_text(
        "import json, os, pathlib, sys\n"
        "pathlib.Path(os.environ['CAPTURE_ARGS']).write_text(json.dumps(sys.argv[1:]), encoding='utf-8')\n",
        encoding="utf-8",
    )
    support = tmp_path / "support.py"
    support.write_text("# support fixture\n", encoding="utf-8")
    executed_bootstrap = tmp_path / "verified-hosted-bootstrap.sh"
    executed_bootstrap.write_text("#!/usr/bin/env bash\n# verified hosted bytes\n", encoding="utf-8")
    hub_repo = tmp_path / "hub-clone"
    cloned_bootstrap = hub_repo / "Chummer.Run.Api/wwwroot/artifacts/mac-codex-release-pipeline/bootstrap.sh"
    cloned_bootstrap.parent.mkdir(parents=True)
    cloned_bootstrap.write_text("#!/usr/bin/env bash\n# different clone bytes\n", encoding="utf-8")
    captured_arguments = tmp_path / "arguments.json"
    function_arguments = [
        str(generator),
        str(support),
        str(tmp_path / "ui"),
        str(tmp_path / "core"),
        str(hub_repo),
        str(tmp_path / "ui-kit"),
        str(tmp_path / "registry"),
        str(tmp_path / "media"),
        str(tmp_path / "legacy"),
        "App/App.csproj",
        "desktop-avalonia",
        "avalonia-osx-arm64-installer",
        "artifact.dmg",
        str(tmp_path / "artifact.dmg"),
        "run-test.avalonia.osx-arm64.installer",
        str(tmp_path / "state.json"),
        str(tmp_path / "receipt.json"),
        str(tmp_path / "sbom.json"),
        str(executed_bootstrap),
    ]
    invoked = subprocess.run(
        [
            "bash",
            "-c",
            'source "$1"; shift; begin_mac_file_build_provenance "$@"',
            "provenance-test",
            str(BOOTSTRAP),
            *function_arguments,
        ],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "CAPTURE_ARGS": str(captured_arguments)},
    )
    assert invoked.returncode == 0, invoked.stderr
    arguments = json.loads(captured_arguments.read_text(encoding="utf-8"))
    build_inputs = [arguments[index + 1] for index, value in enumerate(arguments) if value == "--build-input"]
    assert f"hosted-bootstrap={executed_bootstrap}" in build_inputs
    assert f"hosted-bootstrap={cloned_bootstrap}" not in build_inputs


def test_hosted_bootstrap_and_server_use_the_governed_provenance_boundary() -> None:
    bootstrap = BOOTSTRAP.read_text(encoding="utf-8")
    server = SERVER_VALIDATOR.read_text(encoding="utf-8")
    controller = UPLOAD_CONTROLLER.read_text(encoding="utf-8")
    restore_index = bootstrap.index('log "restoring $project for $rid"')
    begin_index = bootstrap.index('log "declaring build provenance subjects before publish for $head"')
    publish_index = bootstrap.index('log "publishing $project"')
    finalize_index = bootstrap.index('log "finalizing build provenance against final dist/files bytes for $head"')
    promoted_index = bootstrap.index('mv "$dmg_path" "$promoted_dmg_path"')

    assert restore_index < begin_index < publish_index
    assert promoted_index < finalize_index
    assert bootstrap.count("begin_mac_file_build_provenance \\") == 2
    assert bootstrap.count("finalize_mac_file_build_provenance \\") == 2
    assert '"$dist_dir/proof/build-provenance/v1/invocations"' in bootstrap
    assert 'find "$bundle_root/proof/build-provenance/v1" -type f | sort' in bootstrap
    assert 'cp -a "$governed_provenance_root/." "$bundle_root/proof/build-provenance/v1/"' in bootstrap
    assert bootstrap.count('bootstrap_tmp_paths+=("$ui_localization_release_gate_path")') == 2
    assert '--build-input "hosted-bootstrap=$executed_bootstrap_path"' in bootstrap
    assert '--build-input "hosted-bootstrap=$hub_repo/' not in bootstrap
    assert 'ReleaseBuildProvenanceValidator.Validate(incomingCanonicalManifest, filesRoot, proofRoot);' in (
        REPO_ROOT / "Chummer.Run.Api" / "Services" / "ReleaseBundlePromotionService.cs"
    ).read_text(encoding="utf-8")
    assert "ValidateGovernedPaths(governedRoot, invocationRoot, sbomRoot);" in server
    assert "build provenance subject does not match uploaded artifact identity" in server
    assert "governed build provenance cannot contain symlinks or reparse points" in server
    assert "TryGetGovernedUploadLimit(uploadPath, out long maximumProofBytes)" in controller
    assert "governed build provenance files must use the bounded file upload endpoint" in controller
    assert "is not an allowlisted governed build provenance path" in controller
