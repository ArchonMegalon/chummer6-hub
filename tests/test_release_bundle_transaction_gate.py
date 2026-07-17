from __future__ import annotations

import os
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "verify_release_bundle_transaction_gate.sh"
TEST_PROJECT = ROOT / "Chummer.Tests" / "Chummer.Tests.csproj"
EXPECTED_FILTER = "|".join(
    (
        "FullyQualifiedName~Chummer.Tests.ReleaseBundlePromotionServiceTests",
        "FullyQualifiedName~Chummer.Tests.ReleaseBundleUploadSessionServiceTests",
        "FullyQualifiedName~Chummer.Tests.InternalReleaseBundlesControllerTests",
        "FullyQualifiedName~Chummer.Tests.ReleaseUploadRequestGateMiddlewareTests",
    )
)
EXPECTED_CLASSES = tuple(
    clause.removeprefix("FullyQualifiedName~")
    for clause in EXPECTED_FILTER.split("|")
)


def write_trx(path: Path, classes: tuple[str, ...]) -> None:
    root = ET.Element("TestRun")
    definitions = ET.SubElement(root, "TestDefinitions")
    results = ET.SubElement(root, "Results")
    for index, class_name in enumerate(classes, start=1):
        test_id = f"test-{index}"
        unit_test = ET.SubElement(
            definitions,
            "UnitTest",
            {"id": test_id, "name": f"{class_name}.TransactionBoundary"},
        )
        ET.SubElement(
            unit_test,
            "TestMethod",
            {
                "className": class_name,
                "name": "TransactionBoundary",
            },
        )
        ET.SubElement(
            results,
            "UnitTestResult",
            {
                "testId": test_id,
                "testName": f"{class_name}.TransactionBoundary",
                "outcome": "Passed",
            },
        )
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


def fake_dotnet_source(exit_status: int = 0) -> str:
    if exit_status:
        return f"#!/usr/bin/env bash\nexit {exit_status}\n"
    return """#!/usr/bin/env bash
set -euo pipefail
printf '%s\\n' "$@" > "${CAPTURE_ARGUMENTS:-/dev/null}"
results_dir=''
while (($#)); do
  if [[ "$1" == '--results-directory' ]]; then
    results_dir="$2"
    break
  fi
  shift
done
[[ -n "$results_dir" ]]
mkdir -p -- "$results_dir"
cp -- "$FAKE_TRX" "$results_dir/release-bundle-transaction.trx"
"""


def test_transaction_gate_has_a_closed_four_boundary_filter() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    project = TEST_PROJECT.read_text(encoding="utf-8")

    assert f"transaction_filter='{EXPECTED_FILTER}'" in source
    assert source.count("FullyQualifiedName~Chummer.Tests.") == 4
    assert "ReleaseUploadTicketServiceTests" not in source
    assert "ReleaseUploadAccessPolicyTests" not in source
    assert "--no-restore" in source
    assert "-p:UseSharedCompilation=false" in source
    assert "${CHUMMER_RELEASE_BUNDLE_TRANSACTION_GATE_FRAMEWORK:-net10.0}" in source
    assert "CHUMMER_RELEASE_BUNDLE_TRANSACTION_TRX_VERIFIER" in source
    assert '"$trx_verifier"' in source
    assert "<IsTestProject>true</IsTestProject>" in project


def test_transaction_gate_passes_the_exact_filter_to_dotnet() -> None:
    with tempfile.TemporaryDirectory(prefix="release-bundle-transaction-gate-") as temp_dir:
        root = Path(temp_dir)
        bin_dir = root / "bin"
        bin_dir.mkdir()
        arguments_path = root / "arguments.txt"
        trx_path = root / "fixture.trx"
        write_trx(trx_path, EXPECTED_CLASSES)
        dotnet = bin_dir / "dotnet"
        dotnet.write_text(fake_dotnet_source(), encoding="utf-8")
        dotnet.chmod(0o700)
        environment = {
            **os.environ,
            "PATH": f"{bin_dir}:/usr/bin:/bin",
            "CAPTURE_ARGUMENTS": str(arguments_path),
            "FAKE_TRX": str(trx_path),
        }

        result = subprocess.run(
            ["/usr/bin/bash", "--noprofile", "--norc", str(SCRIPT)],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )

        arguments = arguments_path.read_text(encoding="utf-8").splitlines()

    assert result.returncode == 0, result.stderr
    output_lines = result.stdout.splitlines()
    assert len(output_lines) == 2
    assert output_lines[0].startswith("release_bundle_transaction_trx:pass:")
    assert output_lines[1] == "release_bundle_transaction_gate:pass"
    filter_index = arguments.index("--filter")
    assert arguments[filter_index + 1] == EXPECTED_FILTER
    assert arguments.count("--filter") == 1
    assert arguments[:2] == ["test", str(TEST_PROJECT)]


def test_transaction_gate_propagates_dotnet_failure_without_a_pass_marker() -> None:
    with tempfile.TemporaryDirectory(prefix="release-bundle-transaction-failure-") as temp_dir:
        bin_dir = Path(temp_dir) / "bin"
        bin_dir.mkdir()
        dotnet = bin_dir / "dotnet"
        dotnet.write_text(fake_dotnet_source(exit_status=42), encoding="utf-8")
        dotnet.chmod(0o700)
        environment = {
            **os.environ,
            "PATH": f"{bin_dir}:/usr/bin:/bin",
        }

        result = subprocess.run(
            ["/usr/bin/bash", "--noprofile", "--norc", str(SCRIPT)],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )

    assert result.returncode == 42
    assert "release_bundle_transaction_gate:pass" not in result.stdout


def test_transaction_gate_rejects_dotnet_success_without_a_declared_trx() -> None:
    with tempfile.TemporaryDirectory(prefix="release-bundle-transaction-no-trx-") as temp_dir:
        bin_dir = Path(temp_dir) / "bin"
        bin_dir.mkdir()
        dotnet = bin_dir / "dotnet"
        dotnet.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
        dotnet.chmod(0o700)
        environment = {
            **os.environ,
            "PATH": f"{bin_dir}:/usr/bin:/bin",
        }

        result = subprocess.run(
            ["/usr/bin/bash", "--noprofile", "--norc", str(SCRIPT)],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )

    assert result.returncode != 0
    assert "release bundle transaction TRX is invalid" in result.stderr
    assert "No such file" in result.stderr
    assert "release_bundle_transaction_gate:pass" not in result.stdout


def test_transaction_gate_rejects_a_successful_zero_match_dotnet_run() -> None:
    with tempfile.TemporaryDirectory(prefix="release-bundle-transaction-empty-") as temp_dir:
        root = Path(temp_dir)
        bin_dir = root / "bin"
        bin_dir.mkdir()
        trx_path = root / "empty.trx"
        write_trx(trx_path, ())
        dotnet = bin_dir / "dotnet"
        dotnet.write_text(fake_dotnet_source(), encoding="utf-8")
        dotnet.chmod(0o700)
        environment = {
            **os.environ,
            "PATH": f"{bin_dir}:/usr/bin:/bin",
            "FAKE_TRX": str(trx_path),
        }

        result = subprocess.run(
            ["/usr/bin/bash", "--noprofile", "--norc", str(SCRIPT)],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )

    assert result.returncode != 0
    assert "contains no test results" in result.stderr
    assert "release_bundle_transaction_gate:pass" not in result.stdout


def test_transaction_gate_rejects_a_missing_required_test_class() -> None:
    with tempfile.TemporaryDirectory(prefix="release-bundle-transaction-missing-") as temp_dir:
        root = Path(temp_dir)
        bin_dir = root / "bin"
        bin_dir.mkdir()
        trx_path = root / "missing.trx"
        write_trx(trx_path, EXPECTED_CLASSES[:-1])
        dotnet = bin_dir / "dotnet"
        dotnet.write_text(fake_dotnet_source(), encoding="utf-8")
        dotnet.chmod(0o700)
        environment = {
            **os.environ,
            "PATH": f"{bin_dir}:/usr/bin:/bin",
            "FAKE_TRX": str(trx_path),
        }

        result = subprocess.run(
            ["/usr/bin/bash", "--noprofile", "--norc", str(SCRIPT)],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )

    assert result.returncode != 0
    assert EXPECTED_CLASSES[-1] in result.stderr
    assert "release_bundle_transaction_gate:pass" not in result.stdout


def test_transaction_gate_rejects_a_renamed_test_class() -> None:
    with tempfile.TemporaryDirectory(prefix="release-bundle-transaction-renamed-") as temp_dir:
        root = Path(temp_dir)
        bin_dir = root / "bin"
        bin_dir.mkdir()
        renamed_class = "Chummer.Tests.ReleaseUploadRequestGateMiddlewareRenamedTests"
        trx_path = root / "renamed.trx"
        write_trx(trx_path, (*EXPECTED_CLASSES[:-1], renamed_class))
        dotnet = bin_dir / "dotnet"
        dotnet.write_text(fake_dotnet_source(), encoding="utf-8")
        dotnet.chmod(0o700)
        environment = {
            **os.environ,
            "PATH": f"{bin_dir}:/usr/bin:/bin",
            "FAKE_TRX": str(trx_path),
        }

        result = subprocess.run(
            ["/usr/bin/bash", "--noprofile", "--norc", str(SCRIPT)],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )

    assert result.returncode != 0
    assert f"unexpected class {renamed_class}" in result.stderr
    assert "release_bundle_transaction_gate:pass" not in result.stdout
