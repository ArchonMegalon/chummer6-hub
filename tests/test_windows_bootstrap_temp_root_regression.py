from __future__ import annotations

from pathlib import Path


INSTALLER_SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "chummer-presentation"
    / "scripts"
    / "windows-bootstrap"
    / "installer.nsi"
)


def test_windows_bootstrap_uses_resolved_temp_root_instead_of_raw_temp() -> None:
    text = INSTALLER_SCRIPT.read_text(encoding="utf-8")

    assert "Var BootstrapTempRoot" in text
    assert "Function EnsureBootstrapTempRoot" in text
    assert 'StrCpy $EffectivePayloadPath "$BootstrapTempRoot\\${CHUMMER_PAYLOAD_FILE_NAME}"' in text
    assert '"$BootstrapTempRoot\\curl.exe"' in text
    assert '"$BootstrapTempRoot\\chummer-verify-size.cmd"' in text
    assert '"$BootstrapTempRoot\\chummer-verify-payload.cmd"' in text
    assert '"$BootstrapTempRoot\\chummer-extract-payload.cmd"' in text
    assert 'SetOutPath "$BootstrapTempRoot"' in text
    assert 'StrCpy $EffectivePayloadPath "$TEMP\\${CHUMMER_PAYLOAD_FILE_NAME}"' not in text
    assert 'SetOutPath "$TEMP"' not in text
