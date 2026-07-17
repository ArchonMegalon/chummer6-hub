from __future__ import annotations

from pathlib import Path


STARTUP_SMOKE_SCRIPTS = (
    Path("/docker/chummercomplete/chummer-presentation/scripts/run-desktop-startup-smoke.sh"),
    Path("/docker/chummercomplete/chummer6-ui/scripts/run-desktop-startup-smoke.sh"),
    Path("/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean/scripts/run-desktop-startup-smoke.sh"),
    Path("/docker/chummercomplete/chummer-presentation-sr6-attribute-workbench/scripts/run-desktop-startup-smoke.sh"),
)


def test_release_startup_smoke_scripts_keep_bash3_safe_array_count() -> None:
    for script_path in STARTUP_SMOKE_SCRIPTS:
        text = script_path.read_text(encoding="utf-8")

        assert "array_count()" in text, f"missing array_count helper in {script_path}"
        assert 'local restore_nounset=0' in text, f"array_count should preserve nounset in {script_path}"
        assert 'case "$-" in' in text, f"array_count should inspect shell flags in {script_path}"
        assert 'set +u' in text, f"array_count should relax nounset while counting in {script_path}"
        assert 'eval "set -- \\"\\${${array_name}[@]}\\""' in text, f"array_count should count the array without bash4-only expansion tricks in {script_path}"
        assert 'local count="$#"' in text, f"array_count should capture the counted element total in {script_path}"
        assert 'set -u' in text, f"array_count should restore nounset in {script_path}"
        assert 'eval "set -- \\${${array_name}[@]+\\"\\${${array_name}[@]}\\"}"' not in text, f"array_count should not rely on older empty-array expansion tricks in {script_path}"


def test_release_startup_smoke_scripts_avoid_bash4_case_modifiers() -> None:
    for script_path in STARTUP_SMOKE_SCRIPTS:
        text = script_path.read_text(encoding="utf-8")

        assert "${1,,}" not in text, f"startup smoke must not use bash4-only lowercasing in {script_path}"
        assert "${1^^}" not in text, f"startup smoke must not use bash4-only uppercasing in {script_path}"
        assert ",,}" not in text, f"startup smoke must keep bash3-compatible case handling in {script_path}"
        assert "^^}" not in text, f"startup smoke must keep bash3-compatible case handling in {script_path}"
