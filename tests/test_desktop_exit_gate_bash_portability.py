from __future__ import annotations

from pathlib import Path


EXIT_GATE_SCRIPTS = (
    Path("/docker/chummercomplete/chummer6-ui/scripts/materialize-macos-desktop-exit-gate.sh"),
    Path("/docker/chummercomplete/chummer6-ui/scripts/materialize-linux-desktop-exit-gate.sh"),
    Path("/docker/chummercomplete/chummer6-ui/scripts/materialize-windows-desktop-exit-gate.sh"),
    Path("/docker/chummercomplete/chummer-presentation/scripts/materialize-macos-desktop-exit-gate.sh"),
    Path("/docker/chummercomplete/chummer-presentation/scripts/materialize-linux-desktop-exit-gate.sh"),
    Path("/docker/chummercomplete/chummer-presentation/scripts/materialize-windows-desktop-exit-gate.sh"),
    Path("/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean/scripts/materialize-macos-desktop-exit-gate.sh"),
    Path("/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean/scripts/materialize-linux-desktop-exit-gate.sh"),
    Path("/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean/scripts/materialize-windows-desktop-exit-gate.sh"),
    Path("/docker/chummercomplete/chummer-presentation-sr6-attribute-workbench/scripts/materialize-macos-desktop-exit-gate.sh"),
    Path("/docker/chummercomplete/chummer-presentation-sr6-attribute-workbench/scripts/materialize-linux-desktop-exit-gate.sh"),
    Path("/docker/chummercomplete/chummer-presentation-sr6-attribute-workbench/scripts/materialize-windows-desktop-exit-gate.sh"),
)


def test_desktop_exit_gate_scripts_avoid_bash4_mapfile() -> None:
    for script_path in EXIT_GATE_SCRIPTS:
        text = script_path.read_text(encoding="utf-8")

        assert 'RELEASE_PROMOTED_TUPLE=()' in text, f"missing tuple initializer in {script_path}"
        assert 'while IFS= read -r tuple_value; do' in text, f"missing bash3-safe tuple collector loop in {script_path}"
        assert 'RELEASE_PROMOTED_TUPLE+=("$tuple_value")' in text, f"missing tuple append in {script_path}"
        assert 'mapfile -t RELEASE_PROMOTED_TUPLE' not in text, f"exit gate must not rely on bash4 mapfile in {script_path}"
