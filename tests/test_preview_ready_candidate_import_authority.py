from __future__ import annotations

import base64
import hashlib
import importlib.util
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    REPO_ROOT
    / "scripts"
    / "release"
    / "materialize_preview_ready_candidate_import_authority.py"
)
SPEC = importlib.util.spec_from_file_location("preview_ready_candidate_authority", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def ready_pair() -> tuple[dict[str, object], dict[str, object]]:
    common: dict[str, object] = {
        "projectionProfile": MODULE.READY_PROFILE,
        "version": "run-20260806-050000",
        "releaseVersion": "run-20260806-050000",
        "channel": "preview",
        "channelId": "preview",
        "status": "published",
        "rolloutState": "promoted_preview",
        "supportabilityState": "preview_supported",
        "publicationEligible": True,
        "routeAuthority": True,
        "releaseUploadAuthority": False,
        "deployAuthority": False,
    }
    canonical = {
        **common,
        "desktopTupleCoverage": {
            "complete": True,
            "routeAuthority": True,
            "missingRequiredPlatforms": [],
            "missingRequiredHeads": [],
            "missingRequiredPlatformHeadRidTuples": [],
        },
    }
    return canonical, dict(common)


def test_ready_pair_accepts_only_closed_linux_windows_posture() -> None:
    canonical, compatibility = ready_pair()
    MODULE._validate_ready_pair(
        canonical,
        compatibility,
        release_version="run-20260806-050000",
    )


def test_ready_pair_rejects_review_required_supportability() -> None:
    canonical, compatibility = ready_pair()
    canonical["supportabilityState"] = "review_required"
    with pytest.raises(
        MODULE.PreviewReadyAuthorityBlocked,
        match="exact ready preview profile",
    ):
        MODULE._validate_ready_pair(
            canonical,
            compatibility,
            release_version="run-20260806-050000",
        )


def test_false_authority_rejects_route_authority_broadening() -> None:
    authority = {
        "publicationAuthorized": False,
        "publicationEligible": False,
        "releaseUploadAuthority": False,
        "deployAuthority": False,
        "routeAuthority": True,
        "codeDeploymentAuthority": False,
    }
    with pytest.raises(MODULE.PreviewReadyAuthorityBlocked, match="routeAuthority"):
        MODULE._false_authority(authority, label="v6")


def test_decode_embedded_rejects_digest_substitution() -> None:
    raw = b"ready"
    binding = {
        "path": "ready.json",
        "sha256": "0" * 64,
        "sizeBytes": len(raw),
        "base64": base64.b64encode(raw).decode(),
    }
    with pytest.raises(MODULE.PreviewReadyAuthorityBlocked, match="binding drifted"):
        MODULE._decode_embedded(binding, path="ready.json", label="ready")


def test_decode_embedded_accepts_exact_bytes() -> None:
    raw = b"ready"
    binding = {
        "path": "ready.json",
        "sha256": hashlib.sha256(raw).hexdigest(),
        "sizeBytes": len(raw),
        "base64": base64.b64encode(raw).decode(),
    }
    assert MODULE._decode_embedded(binding, path="ready.json", label="ready") == raw
