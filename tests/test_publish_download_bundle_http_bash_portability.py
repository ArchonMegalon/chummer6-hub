from __future__ import annotations

from pathlib import Path


SCRIPT_EXPECTATIONS = {
    Path(__file__).resolve().parents[1] / "scripts" / "publish-download-bundle-http.sh": {
        "required": (
            'upload_file_count="$(array_count upload_files)"',
            'Publishing ${upload_file_count} bundle files from $BUNDLE_DIR',
        ),
        "forbidden": (
            '${#upload_files[@]}',
        ),
    },
    Path("/docker/chummercomplete/chummer-presentation/scripts/publish-download-bundle-http.sh"): {
        "required": (
            'windows_payload_gate_args_count="$(array_count windows_payload_gate_args)"',
            'upload_file_count="$(array_count upload_files)"',
            'Publishing ${upload_file_count} bundle files from $BUNDLE_DIR',
        ),
        "forbidden": (
            '${#windows_payload_gate_args[@]}',
            '${#upload_files[@]}',
        ),
    },
    Path("/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean/scripts/publish-download-bundle-http.sh"): {
        "required": (
            'windows_payload_gate_args_count="$(array_count windows_payload_gate_args)"',
            'upload_file_count="$(array_count upload_files)"',
            'Publishing ${upload_file_count} bundle files from $BUNDLE_DIR',
        ),
        "forbidden": (
            '${#windows_payload_gate_args[@]}',
            '${#upload_files[@]}',
        ),
    },
    Path("/docker/chummercomplete/chummer-presentation-sr6-attribute-workbench/scripts/publish-download-bundle-http.sh"): {
        "required": (
            'windows_payload_gate_args_count="$(array_count windows_payload_gate_args)"',
            'upload_file_count="$(array_count upload_files)"',
            'Publishing ${upload_file_count} bundle files from $BUNDLE_DIR',
        ),
        "forbidden": (
            '${#windows_payload_gate_args[@]}',
            '${#upload_files[@]}',
        ),
    },
}


def test_publish_download_bundle_http_avoids_empty_array_length_expansions() -> None:
    for script, expectations in SCRIPT_EXPECTATIONS.items():
        text = script.read_text(encoding="utf-8")

        assert "array_count()" in text
        assert 'local restore_nounset=0' in text
        assert 'case "$-" in' in text
        assert 'set +u' in text
        assert 'eval "set -- \\"\\${${array_name}[@]}\\""' in text
        assert 'local count="$#"' in text
        assert 'set -u' in text
        assert "array_values_nul()" in text
        assert 'eval "printf \'%s\\\\0\' \\"\\${${array_name}[@]}\\""' in text
        assert "done < <(array_values_nul upload_files)" in text
        assert 'eval "set -- \\${${array_name}[@]+\\"\\${${array_name}[@]}\\"}"' not in text

        for snippet in expectations["required"]:
            assert snippet in text, f"missing expected portability usage in {script}: {snippet}"

        for snippet in expectations["forbidden"]:
            assert snippet not in text, f"found bash3-unsafe raw array length expansion in {script}: {snippet}"

        assert 'for file_path in "${upload_files[@]}"; do' not in text, f"found bash3-unsafe raw upload_files iteration in {script}"
