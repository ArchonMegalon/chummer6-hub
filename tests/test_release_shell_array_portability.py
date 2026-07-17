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
            'portal_artifact_count="$(array_count portal_artifacts)"',
            'if (( portal_artifact_count > 0 )); then',
        ),
        "forbidden": (
            '${#portal_artifacts[@]}',
        ),
    },
    Path("/docker/chummercomplete/chummer6-ui/scripts/generate-releases-manifest.sh"): {
        "required": (
            'promoted_file_count="$(array_count promoted_file_names)"',
            'portal_artifact_count="$(array_count portal_artifacts)"',
            'promoted_file_names=()',
            'if (( portal_artifact_count > 0 )); then',
        ),
        "forbidden": (
            '${#promoted_file_names[@]}',
            '${#portal_artifacts[@]}',
            'readarray -t promoted_file_names',
        ),
    },
    Path("/docker/chummercomplete/chummer-presentation/scripts/generate-releases-manifest.sh"): {
        "required": (
            'promoted_file_count="$(array_count promoted_file_names)"',
            'portal_artifact_count="$(array_count portal_artifacts)"',
            'promoted_file_names=()',
            'if (( portal_artifact_count > 0 )); then',
        ),
        "forbidden": (
            '${#promoted_file_names[@]}',
            '${#portal_artifacts[@]}',
            'readarray -t promoted_file_names',
        ),
    },
    Path("/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean/scripts/generate-releases-manifest.sh"): {
        "required": (
            'promoted_file_count="$(array_count promoted_file_names)"',
            'portal_artifact_count="$(array_count portal_artifacts)"',
            'promoted_file_names=()',
            'if (( portal_artifact_count > 0 )); then',
        ),
        "forbidden": (
            '${#promoted_file_names[@]}',
            '${#portal_artifacts[@]}',
            'readarray -t promoted_file_names',
        ),
    },
    Path("/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean/scripts/publish-download-bundle.sh"): {
        "required": (
            'installer_candidate_count="$(array_count installer_candidates)"',
            'if (( installer_candidate_count == 0 )); then',
            'artifact_count="$(array_count artifacts)"',
            'if (( artifact_count == 0 )); then',
            'live_downloads_mirror_dir_count="$(array_count live_downloads_mirror_dirs)"',
            'if (( live_downloads_mirror_dir_count > 0 )); then',
            'promoted_file_count="$(array_count promoted_file_names)"',
            'array_values_nul()',
            'eval "printf \'%s\\\\0\' \\"\\${${array_name}[@]}\\""',
            'artifacts=()',
            'manifest_meta=()',
            'manifest_integrity=()',
            'verified_startup_smoke_receipts=()',
            'done < <(array_values_nul artifacts)',
            'done < <(array_values_nul promoted_file_names)',
            'done < <(array_values_nul live_downloads_mirror_dirs)',
            '--promoted-artifact-count "$promoted_file_count"',
            'echo "synced ${promoted_file_count} promoted artifact(s) -> $target_label mirror $target_dir"',
            'echo "Published ${promoted_file_count} desktop artifact(s) through verified external downloads lane: $LIVE_VERIFY_TARGET"',
            'echo "Updated local downloads shelf with ${promoted_file_count} desktop artifact(s): $DEPLOY_DIR"',
        ),
        "forbidden": (
            '${#installer_candidates[@]}',
            '${#artifacts[@]}',
            '${#live_downloads_mirror_dirs[@]}',
            '${#promoted_file_names[@]}',
            'for artifact in "${artifacts[@]}"; do',
            'for file_name in "${promoted_file_names[@]}"; do',
            'for mirror_dir in "${live_downloads_mirror_dirs[@]}"; do',
            'mapfile -t artifacts',
            'readarray -t manifest_meta',
            'readarray -t manifest_integrity',
            'readarray -t promoted_file_names',
            'readarray -t verified_startup_smoke_receipts',
        ),
    },
    Path("/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean/scripts/build-desktop-installer.sh"): {
        "required": (
            'artifact_count="$(array_count artifacts)"',
            'if (( artifact_count == 0 )); then',
        ),
        "forbidden": (
            '${#artifacts[@]}',
        ),
    },
    Path("/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean/scripts/publish-download-bundle-s3.sh"): {
        "required": (
            'windows_payload_gate_args_count="$(array_count windows_payload_gate_args)"',
            'if (( windows_payload_gate_args_count == 6 )); then',
        ),
        "forbidden": (
            '${#windows_payload_gate_args[@]}',
        ),
    },
    Path("/docker/chummercomplete/chummer-presentation-sr6-origin-dialog-clean/scripts/verify-releases-manifest.sh"): {
        "required": (
            'verify_arg_count="$(array_count VERIFY_ARGS)"',
            'if (( verify_arg_count > 0 )); then',
        ),
        "forbidden": (
            '${#VERIFY_ARGS[@]}',
        ),
    },
    Path("/docker/chummercomplete/chummer-presentation-sr6-attribute-workbench/scripts/generate-releases-manifest.sh"): {
        "required": (
            'promoted_file_count="$(array_count promoted_file_names)"',
            'portal_artifact_count="$(array_count portal_artifacts)"',
            'promoted_file_names=()',
            'if (( portal_artifact_count > 0 )); then',
        ),
        "forbidden": (
            '${#promoted_file_names[@]}',
            '${#portal_artifacts[@]}',
            'readarray -t promoted_file_names',
        ),
    },
    Path("/docker/chummercomplete/chummer-presentation-sr6-attribute-workbench/scripts/publish-download-bundle.sh"): {
        "required": (
            'installer_candidate_count="$(array_count installer_candidates)"',
            'if (( installer_candidate_count == 0 )); then',
            'artifact_count="$(array_count artifacts)"',
            'if (( artifact_count == 0 )); then',
            'live_downloads_mirror_dir_count="$(array_count live_downloads_mirror_dirs)"',
            'if (( live_downloads_mirror_dir_count > 0 )); then',
            'promoted_file_count="$(array_count promoted_file_names)"',
            'array_values_nul()',
            'eval "printf \'%s\\\\0\' \\"\\${${array_name}[@]}\\""',
            'artifacts=()',
            'manifest_meta=()',
            'manifest_integrity=()',
            'verified_startup_smoke_receipts=()',
            'done < <(array_values_nul artifacts)',
            'done < <(array_values_nul promoted_file_names)',
            'done < <(array_values_nul live_downloads_mirror_dirs)',
            '--promoted-artifact-count "$promoted_file_count"',
            'echo "synced ${promoted_file_count} promoted artifact(s) -> $target_label mirror $target_dir"',
            'echo "Published ${promoted_file_count} desktop artifact(s) through verified external downloads lane: $LIVE_VERIFY_TARGET"',
            'echo "Updated local downloads shelf with ${promoted_file_count} desktop artifact(s): $DEPLOY_DIR"',
        ),
        "forbidden": (
            '${#installer_candidates[@]}',
            '${#artifacts[@]}',
            '${#live_downloads_mirror_dirs[@]}',
            '${#promoted_file_names[@]}',
            'for artifact in "${artifacts[@]}"; do',
            'for file_name in "${promoted_file_names[@]}"; do',
            'for mirror_dir in "${live_downloads_mirror_dirs[@]}"; do',
            'mapfile -t artifacts',
            'readarray -t manifest_meta',
            'readarray -t manifest_integrity',
            'readarray -t promoted_file_names',
            'readarray -t verified_startup_smoke_receipts',
        ),
    },
    Path("/docker/chummercomplete/chummer-presentation-sr6-attribute-workbench/scripts/build-desktop-installer.sh"): {
        "required": (
            'artifact_count="$(array_count artifacts)"',
            'if (( artifact_count == 0 )); then',
        ),
        "forbidden": (
            '${#artifacts[@]}',
        ),
    },
    Path("/docker/chummercomplete/chummer-presentation-sr6-attribute-workbench/scripts/publish-download-bundle-s3.sh"): {
        "required": (
            'windows_payload_gate_args_count="$(array_count windows_payload_gate_args)"',
            'if (( windows_payload_gate_args_count == 6 )); then',
        ),
        "forbidden": (
            '${#windows_payload_gate_args[@]}',
        ),
    },
    Path("/docker/chummercomplete/chummer-presentation-sr6-attribute-workbench/scripts/verify-releases-manifest.sh"): {
        "required": (
            'verify_arg_count="$(array_count VERIFY_ARGS)"',
            'if (( verify_arg_count > 0 )); then',
        ),
        "forbidden": (
            '${#VERIFY_ARGS[@]}',
        ),
    },
    Path("/docker/chummercomplete/chummer6-ui/scripts/publish-download-bundle.sh"): {
        "required": (
            'artifact_count="$(array_count artifacts)"',
            'if (( artifact_count == 0 )); then',
            'live_downloads_mirror_dir_count="$(array_count live_downloads_mirror_dirs)"',
            'if (( live_downloads_mirror_dir_count > 0 )); then',
            'promoted_file_count="$(array_count promoted_file_names)"',
            'array_values_nul()',
            'eval "printf \'%s\\\\0\' \\"\\${${array_name}[@]}\\""',
            'artifacts=()',
            'manifest_meta=()',
            'manifest_integrity=()',
            'verified_startup_smoke_receipts=()',
            'done < <(array_values_nul artifacts)',
            'done < <(array_values_nul promoted_file_names)',
            'done < <(array_values_nul live_downloads_mirror_dirs)',
        ),
        "forbidden": (
            '${#artifacts[@]}',
            '${#live_downloads_mirror_dirs[@]}',
            '${#promoted_file_names[@]}',
            'for artifact in "${artifacts[@]}"; do',
            'for file_name in "${promoted_file_names[@]}"; do',
            'for mirror_dir in "${live_downloads_mirror_dirs[@]}"; do',
            'mapfile -t artifacts',
            'readarray -t manifest_meta',
            'readarray -t manifest_integrity',
            'readarray -t promoted_file_names',
            'readarray -t verified_startup_smoke_receipts',
        ),
    },
    Path("/docker/chummercomplete/chummer-presentation/scripts/publish-download-bundle.sh"): {
        "required": (
            'artifact_count="$(array_count artifacts)"',
            'if (( artifact_count == 0 )); then',
            'live_downloads_mirror_dir_count="$(array_count live_downloads_mirror_dirs)"',
            'if (( live_downloads_mirror_dir_count > 0 )); then',
            'promoted_file_count="$(array_count promoted_file_names)"',
            'array_values_nul()',
            'eval "printf \'%s\\\\0\' \\"\\${${array_name}[@]}\\""',
            'artifacts=()',
            'manifest_meta=()',
            'manifest_integrity=()',
            'verified_startup_smoke_receipts=()',
            'done < <(array_values_nul artifacts)',
            'done < <(array_values_nul promoted_file_names)',
            'done < <(array_values_nul live_downloads_mirror_dirs)',
        ),
        "forbidden": (
            '${#artifacts[@]}',
            '${#live_downloads_mirror_dirs[@]}',
            '${#promoted_file_names[@]}',
            'for artifact in "${artifacts[@]}"; do',
            'for file_name in "${promoted_file_names[@]}"; do',
            'for mirror_dir in "${live_downloads_mirror_dirs[@]}"; do',
            'mapfile -t artifacts',
            'readarray -t manifest_meta',
            'readarray -t manifest_integrity',
            'readarray -t promoted_file_names',
            'readarray -t verified_startup_smoke_receipts',
        ),
    },
    REPO_ROOT / "scripts" / "publish-download-bundle.sh": {
        "required": (
            'if (( $(array_count artifacts) == 0 )); then',
            'if (( $(array_count live_downloads_mirror_dirs) > 0 )); then',
            'if (( $(array_count promoted_file_names) > 0 )); then',
            'array_values_nul()',
            'eval "printf \'%s\\\\0\' \\"\\${${array_name}[@]}\\""',
            'done < <(array_values_nul artifacts)',
            'done < <(array_values_nul promoted_file_names)',
            'done < <(array_values_nul live_downloads_mirror_dirs)',
        'echo "Published $(array_count promoted_file_names) desktop artifact(s) into $AUTHORITATIVE_DEPLOY_DIR"',
        ),
        "forbidden": (
            '${#artifacts[@]}',
            '${#live_downloads_mirror_dirs[@]}',
            '${#promoted_file_names[@]}',
            'for artifact in "${artifacts[@]}"; do',
            'for file_name in "${promoted_file_names[@]}"; do',
            'for mirror_dir in "${live_downloads_mirror_dirs[@]}"; do',
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
    REPO_ROOT / "scripts" / "materialize-public-downloads-bundle.sh": {
        "required": (
            'if (( $(array_count handoff_env) > 0 )); then',
        ),
        "forbidden": (
            '${#handoff_env[@]}',
        ),
    },
}


def test_release_shell_scripts_use_nounset_safe_array_count() -> None:
    for script_path, expectations in SCRIPT_EXPECTATIONS.items():
        text = script_path.read_text(encoding="utf-8")

        for snippet in HELPER_SNIPPETS:
            assert snippet in text, f"missing nounset-safe array_count helper snippet in {script_path}: {snippet}"
        assert 'eval "set -- \\${${array_name}[@]+\\"\\${${array_name}[@]}\\"}"' not in text

        for snippet in expectations["required"]:
            assert snippet in text, f"missing expected portability usage in {script_path}: {snippet}"

        for snippet in expectations["forbidden"]:
            assert snippet not in text, f"found bash3-unsafe raw array length expansion in {script_path}: {snippet}"
