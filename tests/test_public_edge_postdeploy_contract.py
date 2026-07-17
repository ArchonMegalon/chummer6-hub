from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "public_edge_postdeploy_contract.py"


def load_module():
    spec = importlib.util.spec_from_file_location("public_edge_postdeploy_contract", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_normalize_public_edge_postdeploy_payload_hydrates_current_redacted_anchor_fields() -> None:
    module = load_module()
    payload = {
        "contractName": "chummer.public_edge_postdeploy_gate.v1",
        "status": "pass",
        "childReceipts": {
            "preflight": {
                "overlayRoot": "/tmp/public-edge-overlay/app",
                "overlayBuildInfoSourceFingerprint": {
                    "aggregateMatchesCurrentSource": True,
                    "recordedAggregateSha256": "a" * 64,
                    "expectedAggregateSha256": "a" * 64,
                    "missingKeys": [],
                    "mismatchedKeys": [],
                },
            },
            "frontdoorNavigation": {
                "anchorArtifact": {
                    "contractName": "chummer.frontdoor_mobile_anchor_redirect.v2",
                    "entry_url": "https://chummer.run/#turn-runsite-card",
                    "final_url": "https://chummer.run/mobile/player#turn-runsite-card",
                    "final_pathname": "/mobile/player",
                    "final_hash": "#turn-runsite-card",
                    "pwa_manifest_path": "/manifest.player.webmanifest",
                    "pwa_role": "Player",
                    "blazor_shell": "interactive-server",
                    "private_identity_redacted": True,
                    "visible_url_private_identity_absent": True,
                    "session_context_present": True,
                    "device_context_present": True,
                    "failure": "",
                }
            }
        },
    }

    normalized = module.normalize_public_edge_postdeploy_payload(payload)

    assert normalized["preflightOverlayRoot"] == "/tmp/public-edge-overlay/app"
    assert normalized["preflightOverlayBuildInfoSourceFingerprintAggregateMatchesCurrentSource"] is True
    assert normalized["preflightOverlayBuildInfoSourceFingerprintRecordedAggregateSha256"] == "a" * 64
    assert normalized["preflightOverlayBuildInfoSourceFingerprintExpectedAggregateSha256"] == "a" * 64
    assert normalized["preflightOverlayBuildInfoSourceFingerprintMissingKeys"] == []
    assert normalized["preflightOverlayBuildInfoSourceFingerprintMismatchedKeys"] == []
    assert normalized["frontdoorNavigationAnchorArtifactContract"] == "chummer.frontdoor_mobile_anchor_redirect.v2"
    assert normalized["frontdoorNavigationAnchorEntryUrl"] == "https://chummer.run/#turn-runsite-card"
    assert normalized["frontdoorNavigationAnchorFinalUrl"] == "https://chummer.run/mobile/player#turn-runsite-card"
    assert normalized["frontdoorNavigationAnchorFinalPath"] == "/mobile/player"
    assert normalized["frontdoorNavigationAnchorFinalHash"] == "#turn-runsite-card"
    assert normalized["frontdoorNavigationAnchorPwaManifestPath"] == "/manifest.player.webmanifest"
    assert normalized["frontdoorNavigationAnchorPwaRole"] == "Player"
    assert normalized["frontdoorNavigationAnchorBlazorShell"] == "interactive-server"
    assert normalized["frontdoorNavigationAnchorPrivateIdentityRedacted"] is True
    assert normalized["frontdoorNavigationAnchorVisibleUrlPrivateIdentityAbsent"] is True
    assert normalized["frontdoorNavigationAnchorSessionContextPresent"] is True
    assert normalized["frontdoorNavigationAnchorDeviceContextPresent"] is True
    assert normalized["frontdoorNavigationAnchorFailure"] == ""


def test_normalizer_redacts_raw_v1_identity_without_hydrating_v2_proof_fields() -> None:
    module = load_module()
    payload = {
        "childReceipts": {
            "frontdoorNavigation": {
                "anchorArtifact": {
                    "contractName": "chummer.frontdoor_mobile_anchor_redirect.v1",
                    "final_url": "https://chummer.run/mobile/player?sessionId=private-session&deviceId=private-device",
                    "session_id_present": True,
                    "device_id_present": True,
                }
            }
        }
    }

    normalized = module.normalize_public_edge_postdeploy_payload(payload)
    serialized = str(normalized)

    assert "private-session" not in serialized
    assert "private-device" not in serialized
    assert normalized["privateIdentityWasRaw"] is True
    assert normalized["frontdoorNavigationAnchorArtifactContract"] == "chummer.frontdoor_mobile_anchor_redirect.v1"
    assert "frontdoorNavigationAnchorPrivateIdentityRedacted" not in normalized
    assert "frontdoorNavigationAnchorSessionContextPresent" not in normalized
