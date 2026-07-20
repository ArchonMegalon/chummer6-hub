from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]

HELPER_SNIPPETS = (
    "array_count()",
    'local restore_nounset=0',
    'case "$-" in',
    'set +u',
    'eval "set -- \\"\\${${array_name}[@]}\\""',
    'local count="$#"',
    'set -u',
)

SCRIPT_EXPECTATIONS = {
    REPO_ROOT / "scripts" / "generate-releases-manifest.sh": {
        "required": (
            "lower_ascii()",
            'if [[ "$(lower_ascii "$RELEASE_CHANNEL")" == "preview" ]]; then',
            'portal_artifact_count="$(array_count portal_artifacts)"',
            'if (( portal_artifact_count > 0 )); then',
            'echo "synced ${portal_artifact_count} local portal artifact(s) -> $portal_files_dir"',
        ),
        "forbidden": (
            '${RELEASE_CHANNEL,,}',
            '${#portal_artifacts[@]}',
        ),
    },
    REPO_ROOT / "scripts" / "publish-download-bundle.sh": {
        "required": (
            'if (( $(array_count artifacts) == 0 )); then',
            'if (( $(array_count live_downloads_mirror_dirs) > 0 )); then',
            'if (( $(array_count promoted_file_names) > 0 )); then',
            'echo "Published $(array_count promoted_file_names) desktop artifact(s) into $AUTHORITATIVE_DEPLOY_DIR"',
        ),
        "forbidden": (
            '${#artifacts[@]}',
            '${#live_downloads_mirror_dirs[@]}',
            '${#promoted_file_names[@]}',
        ),
    },
    REPO_ROOT / "scripts" / "verify-releases-manifest.sh": {
        "required": (
            'if (( $(array_count VERIFY_ARGS) > 0 )); then',
        ),
        "forbidden": (
            '${#VERIFY_ARGS[@]}',
        ),
    },
    REPO_ROOT / "scripts" / "verify_chummer6_release_ready.sh": {
        "required": (
            "array_count()",
            'if (( $(array_count failures) > 0 )) && [[ "${CHUMMER_RELEASE_READY_STOP_ON_PRECHECK_FAILURE:-1}" =~ ^(1|true|yes|on)$ ]]; then',
            'if (( $(array_count failures) > 0 )); then',
        ),
        "forbidden": (
            '${#failures[@]}',
        ),
    },
}


def test_release_shell_scripts_use_nounset_safe_array_count() -> None:
    for script_path, expectations in SCRIPT_EXPECTATIONS.items():
        text = script_path.read_text(encoding="utf-8")

        for snippet in HELPER_SNIPPETS:
            assert snippet in text, f"missing nounset-safe array_count helper snippet in {script_path}: {snippet}"

        for snippet in expectations["required"]:
            assert snippet in text, f"missing expected portability usage in {script_path}: {snippet}"

        for snippet in expectations["forbidden"]:
            assert snippet not in text, f"found bash3-unsafe raw array length expansion in {script_path}: {snippet}"

        assert 'eval "count=\\${#${array_name}[@]}"' not in text, (
            f"found bash3-unsafe array-length eval helper in {script_path}"
        )
