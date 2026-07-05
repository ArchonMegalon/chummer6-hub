from __future__ import annotations

from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "publish-download-bundle-http.sh"


def test_publish_download_bundle_http_avoids_empty_array_length_expansions() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert "array_count()" in text
    assert 'local restore_nounset=0' in text
    assert 'case "$-" in' in text
    assert 'set +u' in text
    assert 'local count="0"' in text
    assert 'eval "count=\\${#${array_name}[@]}"' in text
    assert 'set -u' in text
    assert 'upload_file_count="$(array_count upload_files)"' in text
    assert '${#upload_files[@]}' not in text
    assert "Publishing ${upload_file_count} bundle files from $BUNDLE_DIR" in text
