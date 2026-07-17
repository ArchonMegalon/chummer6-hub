from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "ai" / "run_flagship_public_edge_verification.sh"
RUNBOOK = ROOT / "docs" / "SELF_HOSTED_DOWNLOADS_RUNBOOK.md"


def test_flagship_verification_derives_and_threads_trusted_deployment_digest() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert "CHUMMER_FLAGSHIP_PUBLIC_EDGE_EXPECTED_BUILD_INFO" in source
    assert "load_expected_full_deployment_digest" in source
    assert 'os.environ.get("CHUMMER_RUN_SERVICES_SOURCE")' in source
    assert "overlay_root=build_info_path.parents[2]" in source
    assert "EXPECTED_FULL_DEPLOYMENT_DIGEST_SHA256" in source
    assert source.count("--expected-full-deployment-digest-sha256") >= 1
    assert "--expected-pwa-asset-inventory-sha256" in source
    assert 'children.get("pwaStatic")' in source
    assert 'EXPECTED_OVERLAY_ROOT="$(dirname --' in source
    assert '--overlay-root "$EXPECTED_OVERLAY_ROOT"' in source
    assert '--expected-build-info "$EXPECTED_BUILD_INFO"' in source
    assert "/api/ready" not in source


def test_runbook_live_pwa_commands_require_independent_deployment_digest() -> None:
    source = RUNBOOK.read_text(encoding="utf-8")

    assert "load_expected_full_deployment_digest" in source
    assert "CHUMMER_RUN_SERVICES_SOURCE" in source
    assert "overlay_root=build_info.parents[2]" in source
    assert source.count("--expected-full-deployment-digest-sha256") >= 8
    assert (
        'verify_public_pwa_static_assets.py --base-url https://chummer.run '
        '--expected-full-deployment-digest-sha256'
    ) in source
