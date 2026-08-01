import os
import shutil
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = REPO_ROOT / ".github/workflows/live-windows-installer-gold-proof.yml"


def workflow_text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_live_windows_gold_proof_workflow_is_manual_and_read_only() -> None:
    text = workflow_text()

    assert "workflow_dispatch:" in text
    assert "pull_request:" not in text
    assert "\npush:" not in text
    assert "permissions:\n  contents: read" in text
    assert "runs-on: windows-latest" in text
    assert "https://chummer.run" in text
    assert "${{ secrets." not in text
    assert "${{ runner.temp }}" not in text
    assert "$env:RUNNER_TEMP" in text
    assert "$env:GITHUB_ENV" in text
    assert "Publication/upload/deployment authority: false" in text


def test_live_windows_gold_proof_workflow_pins_authority_and_actions() -> None:
    text = workflow_text()

    for required_input in (
        "release_version:",
        "live_manifest_sha256:",
        "installer_sha256:",
        "installer_size_bytes:",
        "expected_contract_sha:",
        "capture_confirmed:",
    ):
        assert required_input in text

    assert "refs/heads/main" in text
    assert "$env:GITHUB_SHA -ne $env:EXPECTED_CONTRACT_SHA" in text
    assert "AllowAutoRedirect = $false" in text
    assert "Live release manifest SHA-256 differs" in text
    assert "Downloaded installer SHA-256 differs" in text
    assert "^/downloads/g/gen-" in text
    assert "actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683" in text
    assert text.count("actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02") == 2


def test_live_windows_gold_proof_workflow_uses_existing_native_capture_contract() -> None:
    text = workflow_text()

    assert "scripts/capture_windows_installer_gold_proof.ps1" in text
    assert "-LaunchInstaller" in text
    assert "-CaptureVisualAudit" in text
    assert "-AutoCaptureVisualAudit" in text
    assert "-ScaledDpiScale '1.5'" in text
    assert "-VisualClippingStatus pass" in text
    assert "-VisualReadabilityStatus pass" in text
    assert "Visual proof must contain exactly four screenshot rows" in text
    assert "install-progress|1.0" in text
    assert "install-progress|1.5" in text
    assert "completion|1.0" in text
    assert "completion|1.5" in text
    assert "Progress and completion surfaces must not reuse identical image bytes" in text


def test_live_windows_gold_proof_workflow_never_uploads_installer_bytes() -> None:
    text = workflow_text()

    assert "path: ${{ steps.package.outputs.bundle_path }}" in text
    assert "${{ env.CHUMMER_PROOF_ROOT }}/WINDOWS_INSTALLER_CAPTURE_FAILURE.txt" in text
    assert "${{ env.CHUMMER_PROOF_ROOT }}/*.png" in text
    assert "path: ${{ env.CHUMMER_DOWNLOADS_ROOT }}" not in text
    assert "Remove installer and proof bytes from the runner" in text


def test_windows_gold_proof_receipt_delimits_colon_adjacent_variables() -> None:
    script = (
        REPO_ROOT / "scripts/capture_windows_installer_gold_proof.ps1"
    ).read_text(encoding="utf-8")

    assert '"windows-installer-gold-proof:$HeadId:$Rid:$Version"' not in script
    assert '"windows-installer-gold-proof:${HeadId}:${Rid}:${Version}"' in script


@pytest.mark.skipif(shutil.which("pwsh") is None, reason="PowerShell is unavailable")
@pytest.mark.parametrize(
    "relative_path",
    (
        "scripts/capture_windows_installer_gold_proof.ps1",
        "scripts/capture_windows_installer_visual_audit.ps1",
    ),
)
def test_windows_gold_proof_capture_scripts_parse_in_powershell(
    relative_path: str,
) -> None:
    script_path = REPO_ROOT / relative_path
    env = os.environ.copy()
    env["CHUMMER_POWERSHELL_PARSE_TARGET"] = str(script_path)
    result = subprocess.run(
        (
            "pwsh",
            "-NoProfile",
            "-Command",
            "$tokens=$null; $errors=$null; "
            "[System.Management.Automation.Language.Parser]::ParseFile("
            "$env:CHUMMER_POWERSHELL_PARSE_TARGET, [ref]$tokens, [ref]$errors) "
            "| Out-Null; if ($errors.Count -ne 0) { "
            "$errors | ForEach-Object { Write-Error $_.Message }; exit 1 }",
        ),
        check=False,
        capture_output=True,
        env=env,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr or result.stdout
