from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_mac_bootstrap_verifies_release_upload_response_against_local_manifests() -> None:
    bootstrap = (
        REPO_ROOT
        / "Chummer.Run.Api"
        / "wwwroot"
        / "artifacts"
        / "mac-codex-release-pipeline"
        / "bootstrap.sh"
    ).read_text(encoding="utf-8")

    assert 'python3 "$hub_alias/scripts/verify_release_upload_response_truth.py"' in bootstrap
    assert '--local-manifest "$dist_dir/releases.json"' in bootstrap
    assert '--local-canonical-manifest "$dist_dir/RELEASE_CHANNEL.generated.json"' in bootstrap
    assert '--upload-response "$response_path"' in bootstrap
