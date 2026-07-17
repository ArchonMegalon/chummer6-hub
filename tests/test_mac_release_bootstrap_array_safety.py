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
    assert 'upload_file_count="$(array_count upload_files)"' in text
    assert 'if (( $(array_count bootstrap_tmp_paths) > 0 )); then' in text
    assert '(( $(array_count app_heads) > 0 )) || die "no app heads requested"' in text
    assert "array_contains_value()" in text
    assert "array_values_nul()" in text
    assert "done < <(array_values_nul install_urls)" in text
    assert "done < <(array_values_nul direct_urls)" in text
    assert "done < <(array_values_nul chunks)" in text
    assert "done < <(array_values_nul upload_files)" in text
    assert "done < <(array_values_nul bootstrap_tmp_paths)" in text
    assert "done < <(array_values_nul raw_heads)" in text
    assert 'for url in "${install_urls[@]}"; do' not in text
    assert 'for url in "${direct_urls[@]}"; do' not in text
    assert 'for line in "${validation_errors[@]}"; do' not in text
    assert 'for chunk_path in "${chunks[@]}"; do' not in text
    assert 'for file_path in "${upload_files[@]}"; do' not in text
    assert 'for file_path in "${upload_files[@]:0:8}"; do' not in text
    assert 'for path in "${bootstrap_tmp_paths[@]}"; do' not in text
    assert 'for raw_head in "${raw_heads[@]}"; do' not in text
    assert "validation_errors" not in text
    assert 'append_unique_value "avalonia" "${app_heads[@]}"' not in text
    assert 'append_unique_value "blazor-desktop" "${app_heads[@]}"' not in text

    unsafe_patterns = (
        '${#install_urls[@]}',
        '${#direct_urls[@]}',
        '${#validation_errors[@]}',
        '${#chunks[@]}',
        '${#upload_files[@]}',
        '${#app_heads[@]}',
        '${raw_heads[@]}',
        '${upload_files[@]:0:8}',
    )
    for pattern in unsafe_patterns:
        assert pattern not in text

    assert 'eval "set -- \\${${array_name}[@]+\\"\\${${array_name}[@]}\\"}"' not in text
