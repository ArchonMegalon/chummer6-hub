from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = REPO_ROOT.parent
BUILDER = WORKSPACE_ROOT / "chummer6-ui" / "scripts" / "build-desktop-installer.sh"
GENERATOR = WORKSPACE_ROOT / "scripts" / "release" / "materialize_build_provenance.py"
SUPPLY_CHAIN_VERIFIER = WORKSPACE_ROOT / "scripts" / "release" / "verify_supply_chain_evidence.py"


def load_generator():
    name = "windows_proof_provenance_generator"
    spec = importlib.util.spec_from_file_location(name, GENERATOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def init_repo(path: Path) -> None:
    path.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    subprocess.run(
        ["git", "-C", str(path), "config", "user.email", "test@example.invalid"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(path), "config", "user.name", "Provenance Test"],
        check=True,
    )


def commit_all(path: Path, message: str = "fixture") -> None:
    subprocess.run(["git", "-C", str(path), "add", "."], check=True)
    subprocess.run(["git", "-C", str(path), "commit", "-qm", message], check=True)


def make_provenance_fixture(tmp_path: Path) -> tuple[object, argparse.Namespace, list[Path]]:
    module = load_generator()
    primary = tmp_path / "sources" / "chummer6-ui"
    init_repo(primary)
    project = primary / "App" / "App.csproj"
    project.parent.mkdir(parents=True)
    project.write_text('<Project Sdk="Microsoft.NET.Sdk" />\n', encoding="utf-8")
    commit_all(primary)

    assets = project.parent / "obj" / "project.assets.json"
    assets.parent.mkdir(parents=True)
    assets.write_text(
        json.dumps(
            {
                "version": 3,
                "targets": {"net10.0": {}},
                "libraries": {},
                "project": {
                    "version": "1.0.0",
                    "restore": {"projectPath": str(project)},
                    "frameworks": {"net10.0": {}},
                },
            }
        ),
        encoding="utf-8",
    )

    material_names = (
        "chummer-core-engine",
        "chummer.run-services",
        "chummer-ui-kit",
        "chummer-hub-registry",
        "chummer-media-factory",
        "chummer5a",
    )
    materials: list[Path] = []
    source_material_args: list[str] = []
    for name in material_names:
        root = tmp_path / "sources" / name
        init_repo(root)
        (root / "README.md").write_text(f"# {name}\n", encoding="utf-8")
        commit_all(root)
        materials.append(root)
        source_material_args.append(f"{name}={root}")

    output_root = tmp_path / "proof"
    args = argparse.Namespace(
        state=output_root / "state.json",
        output=output_root / "receipt.json",
        builder_id="chummer-windows-release-bootstrap",
        build_type="windows-desktop-release",
        invocation_id="run-test.avalonia.win-x64.installer",
        release_version="run-test",
        supply_chain_script=SUPPLY_CHAIN_VERIFIER,
        source_repository="chummer-presentation",
        source_repo_root=primary,
        source_material=source_material_args,
        build_root=primary,
        target_id="desktop-avalonia",
        project_path=Path("App/App.csproj"),
        artifact_id="avalonia-win-x64-installer",
        artifact_kind="desktop_download",
        artifact_name="chummer-nightly.exe",
        artifact_path=output_root / "chummer-nightly.exe",
        artifact_image=None,
        docker_binary=None,
        sbom_path=output_root / "desktop-avalonia.cdx.json",
        build_input=[f"desktop-project={project}"],
    )
    return module, args, materials


def test_windows_installer_declares_provenance_before_build_and_finalizes_signed_bytes() -> None:
    script = BUILDER.read_text(encoding="utf-8")
    case_start = script.rindex("case \"$RID\" in")
    windows_case = script[case_start : script.index("linux-*)", case_start)]

    assert windows_case.index("begin_windows_build_provenance") < windows_case.index(
        "build_windows_installer"
    )
    assert windows_case.index("build_windows_installer") < windows_case.index(
        "finalize_windows_signing_receipt"
    )
    assert windows_case.index("finalize_windows_signing_receipt") < windows_case.index(
        "finalize_windows_build_provenance"
    )
    assert windows_case.index("finalize_windows_build_provenance") < windows_case.index(
        "stage_installer_for_downloads_manifest"
    )


def test_windows_build_provenance_uses_the_canonical_authority_and_input_sets() -> None:
    script = BUILDER.read_text(encoding="utf-8")

    assert '--builder-id "chummer-windows-release-bootstrap"' in script
    assert '--build-type "windows-desktop-release"' in script
    assert '--release-version "$VERSION"' in script
    assert '--artifact-kind "desktop_download"' in script
    assert '--artifact-id "avalonia-win-x64-installer"' in script
    assert '--target-id "desktop-avalonia"' in script
    assert '[[ ! -e "$artifact_path" && ! -L "$artifact_path" ]]' in script
    for repository in (
        "chummer-core-engine",
        "chummer.run-services",
        "chummer-ui-kit",
        "chummer-hub-registry",
        "chummer-media-factory",
        "chummer5a",
    ):
        assert f'--source-material "{repository}=' in script
    for label in (
        "windows-bootstrap-recipe",
        "desktop-project",
        "desktop-installer-recipe",
        "dotnet-sdk-selection",
    ):
        assert f'--build-input "{label}=' in script


def test_governed_generator_binds_release_version_into_receipt_and_sbom() -> None:
    module = load_generator()
    receipt = module.base_receipt(
        argparse.Namespace(
            builder_id="chummer-windows-release-bootstrap",
            build_type="windows-desktop-release",
            invocation_id="run-1.avalonia.win-x64.installer",
            release_version="run-1",
        ),
        status="pass",
        failures=[],
    )

    assert receipt["release_version"] == "run-1"
    source = GENERATOR.read_text(encoding="utf-8")
    assert 'component["version"] = release_version' in source
    assert 'receipt["release_version"] = release_version' in source
    assert '"release_version": release_version' in source


def test_governed_generator_executes_the_exact_hashed_support_snapshot(
    tmp_path: Path,
) -> None:
    module = load_generator()
    support_path = tmp_path / "support.py"
    support_path.write_text("VALUE = 'captured'\n", encoding="utf-8")
    captured, digest = module.capture_regular_file_bytes(support_path)
    support_path.write_text("VALUE = 'mutated'\nraise RuntimeError('must not run')\n", encoding="utf-8")

    loaded = module.load_supply_chain_module(support_path, captured)

    assert loaded.VALUE == "captured"
    assert digest == __import__("hashlib").sha256(captured).hexdigest()


def test_governed_generator_scans_all_sources_at_begin_and_finalize(
    tmp_path: Path,
) -> None:
    module, begin_args, _ = make_provenance_fixture(tmp_path)

    assert module.begin(begin_args) == 0
    state = json.loads(begin_args.state.read_text(encoding="utf-8"))
    scan = state["source_secret_scan"]
    assert scan["contract_name"] == "chummer6.source_secret_scan.v1"
    assert scan["engine"].endswith(".v2")
    assert scan["scope"] == "git_committed_object_tree"
    assert scan["status"] == "pass"
    assert scan["repository_count"] == 7
    assert len(scan["repositories"]) == 7
    assert len({repository["repository"] for repository in scan["repositories"]}) == 7
    assert tuple(repository["repository"] for repository in scan["repositories"]) == (
        "chummer-presentation",
        "chummer-core-engine",
        "chummer.run-services",
        "chummer-ui-kit",
        "chummer-hub-registry",
        "chummer-media-factory",
        "chummer5a",
    )
    assert len(
        {
            repository["repository_history_fingerprint"]
            for repository in scan["repositories"]
        }
    ) == 7
    private_roots = [
        state["source"]["repo_root"],
        *(material["repo_root"] for material in state["source_materials"]),
    ]
    assert len(private_roots) == 7
    assert len({str(Path(root).resolve()) for root in private_roots}) == 7
    assert all("repo_root" not in repository for repository in scan["repositories"])

    begin_args.artifact_path.write_bytes(b"signed-windows-nightly")
    finalize_args = argparse.Namespace(
        state=begin_args.state,
        output=begin_args.output,
        builder_id=begin_args.builder_id,
        build_type=begin_args.build_type,
        invocation_id=begin_args.invocation_id,
        release_version=begin_args.release_version,
    )

    assert module.finalize(finalize_args) == 0
    receipt = json.loads(begin_args.output.read_text(encoding="utf-8"))
    serialized = json.dumps(receipt)
    assert receipt["status"] == "pass"
    assert receipt["invocation"]["state"]["source_secret_scan"] == scan
    assert str(tmp_path) not in serialized


def test_governed_generator_rejects_secret_added_to_material_before_finalize(
    tmp_path: Path,
) -> None:
    module, begin_args, materials = make_provenance_fixture(tmp_path)

    assert module.begin(begin_args) == 0
    sensitive_name = ".env." + "production"
    (materials[0] / sensitive_name).write_text("PUBLIC_SETTING=enabled\n", encoding="utf-8")
    commit_all(materials[0], "unexpected release credential file")
    begin_args.artifact_path.write_bytes(b"signed-windows-nightly")
    finalize_args = argparse.Namespace(
        state=begin_args.state,
        output=begin_args.output,
        builder_id=begin_args.builder_id,
        build_type=begin_args.build_type,
        invocation_id=begin_args.invocation_id,
        release_version=begin_args.release_version,
    )

    assert module.finalize(finalize_args) == 1
    receipt = json.loads(begin_args.output.read_text(encoding="utf-8"))
    serialized = json.dumps(receipt)
    assert receipt["status"] == "fail"
    assert any(
        "source secret scan did not pass during finalization" in failure
        for failure in receipt["failures"]
    )
    assert "source secret scan result changed during the build invocation" in receipt["failures"]
    assert sensitive_name not in serialized


def test_governed_generator_rejects_duplicate_resolved_source_root(
    tmp_path: Path,
) -> None:
    module, begin_args, _ = make_provenance_fixture(tmp_path)
    begin_args.source_material[-1] = f"chummer5a={begin_args.source_repo_root}"

    assert module.begin(begin_args) == 1
    receipt = json.loads(begin_args.output.read_text(encoding="utf-8"))

    assert receipt["status"] == "fail"
    assert any(
        "seven canonical, distinct repository authorities" in failure
        for failure in receipt["failures"]
    )
    assert not begin_args.state.exists()


def test_governed_generator_rejects_noncanonical_authority_label(
    tmp_path: Path,
) -> None:
    module, begin_args, _ = make_provenance_fixture(tmp_path)
    _, root = begin_args.source_material[0].split("=", 1)
    begin_args.source_material[0] = f"renamed-core={root}"

    assert module.begin(begin_args) == 1
    receipt = json.loads(begin_args.output.read_text(encoding="utf-8"))

    assert receipt["status"] == "fail"
    assert any(
        "seven canonical, distinct repository authorities" in failure
        for failure in receipt["failures"]
    )


def test_governed_generator_rejects_seven_clones_of_one_authority(
    tmp_path: Path,
) -> None:
    module, begin_args, _ = make_provenance_fixture(tmp_path)
    clone_root = tmp_path / "cloned-authorities"
    replacements: list[str] = []
    for declaration in begin_args.source_material:
        repository, _ = declaration.split("=", 1)
        clone = clone_root / repository
        subprocess.run(
            ["git", "clone", "-q", str(begin_args.source_repo_root), str(clone)],
            check=True,
        )
        replacements.append(f"{repository}={clone}")
    begin_args.source_material = replacements

    assert module.begin(begin_args) == 1
    receipt = json.loads(begin_args.output.read_text(encoding="utf-8"))

    assert receipt["status"] == "fail"
    assert any(
        "seven canonical, distinct repository authorities" in failure
        for failure in receipt["failures"]
    )
