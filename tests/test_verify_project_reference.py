from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "verify_project_reference.py"


def _fixture(tmp_path: Path, include: str, *, namespace: bool = False) -> tuple[Path, Path]:
    expected = tmp_path / "chummer-core-engine" / "Chummer.Contracts" / "Chummer.Contracts.csproj"
    expected.parent.mkdir(parents=True)
    expected.write_text('<Project Sdk="Microsoft.NET.Sdk" />\n', encoding="utf-8")

    project = tmp_path / "hub" / "Chummer.Run.Contracts" / "Chummer.Run.Contracts.csproj"
    project.parent.mkdir(parents=True)
    namespace_attribute = ' xmlns="urn:msbuild"' if namespace else ""
    project.write_text(
        f'<Project Sdk="Microsoft.NET.Sdk"{namespace_attribute}>\n'
        "  <ItemGroup>\n"
        f'    <ProjectReference Include="{include}" />\n'
        "  </ItemGroup>\n"
        "</Project>\n",
        encoding="utf-8",
    )
    return project, expected


def _run(project: Path, expected: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--expected", str(expected), str(project)],
        check=False,
        capture_output=True,
        text=True,
    )


def test_accepts_literal_owner_project_reference(tmp_path: Path) -> None:
    project, expected = _fixture(
        tmp_path,
        r"..\..\chummer-core-engine\Chummer.Contracts\Chummer.Contracts.csproj",
    )

    result = _run(project, expected)

    assert result.returncode == 0, result.stderr


def test_accepts_msbuild_project_directory_reference_and_xml_namespace(tmp_path: Path) -> None:
    project, expected = _fixture(
        tmp_path,
        "$(MSBuildProjectDirectory)/../../chummer-core-engine/Chummer.Contracts/Chummer.Contracts.csproj",
        namespace=True,
    )

    result = _run(project, expected)

    assert result.returncode == 0, result.stderr


def test_accepts_msbuild_this_file_directory_reference(tmp_path: Path) -> None:
    project, expected = _fixture(
        tmp_path,
        "$(MSBuildThisFileDirectory)../../chummer-core-engine/Chummer.Contracts/Chummer.Contracts.csproj",
    )

    result = _run(project, expected)

    assert result.returncode == 0, result.stderr


def test_rejects_package_reference_instead_of_owner_project(tmp_path: Path) -> None:
    project, expected = _fixture(tmp_path, "../Different.Contracts/Different.Contracts.csproj")
    project.write_text(
        '<Project Sdk="Microsoft.NET.Sdk"><ItemGroup>'
        '<PackageReference Include="Chummer.Contracts" Version="1.0.0" />'
        "</ItemGroup></Project>\n",
        encoding="utf-8",
    )

    result = _run(project, expected)

    assert result.returncode == 1
    assert "does not reference owner project" in result.stderr


def test_rejects_unresolved_property(tmp_path: Path) -> None:
    project, expected = _fixture(
        tmp_path,
        "$(UntrustedRoot)/Chummer.Contracts/Chummer.Contracts.csproj",
    )

    result = _run(project, expected)

    assert result.returncode == 1


def test_rejects_existing_neighboring_project(tmp_path: Path) -> None:
    project, expected = _fixture(
        tmp_path,
        "Chummer.Contracts/Chummer.Contracts.csproj",
    )
    impostor = project.parent / "Chummer.Contracts" / "Chummer.Contracts.csproj"
    impostor.parent.mkdir(parents=True)
    impostor.write_text('<Project Sdk="Microsoft.NET.Sdk" />\n', encoding="utf-8")

    result = _run(project, expected)

    assert result.returncode == 1


@pytest.mark.parametrize(
    "reference_markup",
    [
        '<ProjectReference Include="{include}" Condition="\'$(UseOwner)\' == \'true\'" />',
        '<ProjectReference Include="{include}" ReferenceOutputAssembly="false" />',
        (
            '<ProjectReference Include="{include}">'
            "<BuildReference>false</BuildReference>"
            "</ProjectReference>"
        ),
    ],
)
def test_rejects_conditioned_or_non_consumed_owner_reference(
    tmp_path: Path,
    reference_markup: str,
) -> None:
    include = "$(MSBuildProjectDirectory)/../../chummer-core-engine/Chummer.Contracts/Chummer.Contracts.csproj"
    project, expected = _fixture(tmp_path, include)
    project.write_text(
        '<Project Sdk="Microsoft.NET.Sdk"><ItemGroup>'
        f"{reference_markup.format(include=include)}"
        "</ItemGroup></Project>\n",
        encoding="utf-8",
    )

    result = _run(project, expected)

    assert result.returncode == 1


@pytest.mark.parametrize(
    "project_markup",
    [
        pytest.param(
            '<Project Sdk="Microsoft.NET.Sdk">'
            '<ItemGroup Condition="\'$(UseOwner)\' == \'true\'">'
            "{reference}</ItemGroup></Project>",
            id="conditioned-item-group",
        ),
        pytest.param(
            '<Project Sdk="Microsoft.NET.Sdk" Condition="\'$(UseOwner)\' == \'true\'">'
            "<ItemGroup>{reference}</ItemGroup></Project>",
            id="conditioned-project",
        ),
        pytest.param(
            '<Project Sdk="Microsoft.NET.Sdk"><Choose>'
            '<When Condition="\'$(UseOwner)\' == \'true\'">'
            "<ItemGroup>{reference}</ItemGroup>"
            "</When></Choose></Project>",
            id="choose-when",
        ),
        pytest.param(
            '<Project Sdk="Microsoft.NET.Sdk"><Choose><Otherwise>'
            "<ItemGroup>{reference}</ItemGroup>"
            "</Otherwise></Choose></Project>",
            id="choose-otherwise",
        ),
        pytest.param(
            '<Project Sdk="Microsoft.NET.Sdk"><Target Name="AddOwnerReference">'
            "<ItemGroup>{reference}</ItemGroup>"
            "</Target></Project>",
            id="target-scoped",
        ),
    ],
)
def test_rejects_reference_outside_static_unconditional_item_group(
    tmp_path: Path,
    project_markup: str,
) -> None:
    include = "$(MSBuildProjectDirectory)/../../chummer-core-engine/Chummer.Contracts/Chummer.Contracts.csproj"
    project, expected = _fixture(tmp_path, include)
    reference = f'<ProjectReference Include="{include}" />'
    project.write_text(
        project_markup.format(reference=reference) + "\n",
        encoding="utf-8",
    )

    result = _run(project, expected)

    assert result.returncode == 1


def test_rejects_missing_expected_owner_project(tmp_path: Path) -> None:
    project, expected = _fixture(
        tmp_path,
        "$(MSBuildProjectDirectory)/../../chummer-core-engine/Chummer.Contracts/Chummer.Contracts.csproj",
    )
    expected.unlink()

    result = _run(project, expected)

    assert result.returncode == 2
    assert "expected owner project is unavailable" in result.stderr
