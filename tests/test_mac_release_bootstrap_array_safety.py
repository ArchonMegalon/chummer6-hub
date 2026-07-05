from __future__ import annotations

from pathlib import Path


BOOTSTRAP = (
    Path(__file__).resolve().parents[1]
    / "Chummer.Run.Api"
    / "wwwroot"
    / "artifacts"
    / "mac-codex-release-pipeline"
    / "bootstrap.sh"
)


def test_mac_release_bootstrap_avoids_bash3_empty_array_expansions_under_nounset() -> None:
    text = BOOTSTRAP.read_text(encoding="utf-8")

    assert "array_count()" in text
    assert 'local restore_nounset=0' in text
    assert 'case "$-" in' in text
    assert 'set +u' in text
    assert 'eval "set -- \\"\\${${array_name}[@]}\\""' in text
    assert 'local count="$#"' in text
    assert 'set -u' in text
    assert 'if (( $(array_count install_urls) > 0 )); then' in text
    assert 'if (( $(array_count direct_urls) > 0 )); then' in text
    assert 'if (( $(array_count validation_errors) > 0 )); then' in text
    assert 'upload_file_count="$(array_count upload_files)"' in text
    assert 'if (( $(array_count bootstrap_tmp_paths) > 0 )); then' in text
    assert 'if (( $(array_count app_heads) == 0 ))' in text
    assert '(( $(array_count app_heads) > 0 )) || die "no app heads requested"' in text

    unsafe_patterns = (
        '${#install_urls[@]}',
        '${#direct_urls[@]}',
        '${#validation_errors[@]}',
        '${#chunks[@]}',
        '${#upload_files[@]}',
        '${#app_heads[@]}',
    )
    for pattern in unsafe_patterns:
        assert pattern not in text

    assert 'eval "set -- \\${${array_name}[@]+\\"\\${${array_name}[@]}\\"}"' not in text
