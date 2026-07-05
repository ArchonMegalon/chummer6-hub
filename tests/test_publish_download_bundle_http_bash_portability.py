from __future__ import annotations

from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "publish-download-bundle-http.sh"


def test_publish_download_bundle_http_avoids_empty_array_length_expansions() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert "array_count()" in text
    assert 'local restore_nounset=0' in text
    assert 'case "$-" in' in text
    assert 'set +u' in text
    assert 'eval "set -- \\"\\${${array_name}[@]}\\""' in text
    assert 'local count="$#"' in text
    assert 'set -u' in text
    assert 'upload_file_count="$(array_count upload_files)"' in text
    assert '${#upload_files[@]}' not in text
    assert 'eval "count=\\${#${array_name}[@]}"' not in text
    assert "Publishing ${upload_file_count} bundle files from $BUNDLE_DIR" in text
    assert 'VERIFY_SHELF_TRUTH_LIVE_CONFIRMATION_COUNT="${CHUMMER_RELEASE_UPLOAD_VERIFY_SHELF_TRUTH_LIVE_CONFIRMATION_COUNT:-3}"' in text
    assert 'VERIFY_SHELF_TRUTH_LIVE_CONFIRMATION_DELAY_SECONDS="${CHUMMER_RELEASE_UPLOAD_VERIFY_SHELF_TRUTH_LIVE_CONFIRMATION_DELAY_SECONDS:-2}"' in text
    assert 'VERIFY_SHELF_TRUTH_LIVE_MAX_SAMPLES="${CHUMMER_RELEASE_UPLOAD_VERIFY_SHELF_TRUTH_LIVE_MAX_SAMPLES:-6}"' in text
    assert '--live-confirmation-count "$VERIFY_SHELF_TRUTH_LIVE_CONFIRMATION_COUNT"' in text
    assert '--live-confirmation-delay-seconds "$VERIFY_SHELF_TRUTH_LIVE_CONFIRMATION_DELAY_SECONDS"' in text
    assert '--live-max-samples "$VERIFY_SHELF_TRUTH_LIVE_MAX_SAMPLES"' in text
    assert text.count("canonicalize_release_channel_registries() {") == 1
    assert text.count("canonicalize_bundle_release_channel_registries() {") == 1
    assert text.count("canonicalize_bundle_release_channel_registries\n") == 1
