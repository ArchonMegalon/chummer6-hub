from __future__ import annotations

from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "ai" / "run_flagship_public_edge_verification.sh"


def test_flagship_public_edge_helper_runs_the_live_proof_pack() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert "scripts/verify_all_horizons_preview_routes.py" in text
    assert 'children.get("pwaStatic")' in text
    assert "PUBLIC_PWA_STATIC_ASSETS.generated.json" in text
    assert "scripts/verify_mobile_pwa_ledger_boundary.py" in text
    assert "scripts/verify_ready_mobile_handoff_contract.py" in text
    assert "scripts/verify_participate_iframe_shell.py" in text
    assert "scripts/verify_live_surface_parity.py" in text
    assert "scripts/verify_public_edge_postdeploy_gate.py" in text
    assert "--require-downloads-status-playwright" in text
    assert "--require-mobile-pwa-viewport-playwright" in text
    assert "--require-pwa-offline-cache-playwright" in text
    assert "--require-frontdoor-navigation-playwright" in text
    assert "public-edge-browser-proofs" in text
    assert "flagship public-edge verification receipts:" in text
