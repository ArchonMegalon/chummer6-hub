from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

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

PROJECTION_SCRIPT = REPO_ROOT / "scripts" / "release" / "verify_public_projection.py"


def load_projection():
    name = "preview_ready_projection_consumer_test"
    spec = importlib.util.spec_from_file_location(name, PROJECTION_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode()


def embedded(path: str, raw: bytes) -> dict[str, object]:
    return {
        "path": path,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "sizeBytes": len(raw),
        "base64": base64.b64encode(raw).decode(),
    }


def v6_consumer_fixture(projection):
    now = datetime(2026, 8, 6, 8, 0, tzinfo=timezone.utc)
    version = "run-20260806-050000"
    generation_id = "gen-20260806T075500Z-test"
    common = {
        "projectionProfile": projection.CANDIDATE_PREVIEW_READY_PROFILE,
        "version": version,
        "releaseVersion": version,
        "channel": "preview",
        "channelId": "preview",
        "status": "published",
        "rolloutState": "promoted_preview",
        "supportabilityState": "preview_supported",
        "publicationEligible": True,
        "routeAuthority": True,
        "releaseUploadAuthority": False,
        "deployAuthority": False,
        "generationId": generation_id,
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
    compatibility = dict(common)
    canonical_raw = canonical_bytes(canonical)
    compatibility_raw = canonical_bytes(compatibility)
    preprojection_canonical_raw = canonical_raw
    preprojection_compatibility_raw = compatibility_raw
    seed_rows = {
        name: {
            "path": f"release-evidence/{name}",
            "sha256": hashlib.sha256(name.encode()).hexdigest(),
            "sizeBytes": len(name),
        }
        for name in ("CURRENT.json", "RELEASE_DECISION.json", "SNAPSHOT.json")
    }
    rows = sorted(
        [
            {
                "path": "RELEASE_CHANNEL.generated.json",
                "sha256": hashlib.sha256(canonical_raw).hexdigest(),
                "sizeBytes": len(canonical_raw),
            },
            {
                "path": "releases.json",
                "sha256": hashlib.sha256(compatibility_raw).hexdigest(),
                "sizeBytes": len(compatibility_raw),
            },
            *seed_rows.values(),
        ],
        key=lambda row: row["path"],
    )
    inventory_raw = canonical_bytes(
        {
            "contractName": "chummer.release-upload.candidate-inventory/v1",
            "contractVersion": 1,
            "files": rows,
        }
    )
    candidate_identity = {
        "version": version,
        "canonicalManifestSha256": hashlib.sha256(canonical_raw).hexdigest(),
        "inventorySha256": projection._candidate_inventory_digest(rows),
        "fileCount": len(rows),
        "totalBytes": sum(row["sizeBytes"] for row in rows),
    }
    candidate = {
        **candidate_identity,
        "bundleIdentitySha256": hashlib.sha256(
            json.dumps(
                candidate_identity,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest(),
    }
    native = {"status": "passed"}
    native_raw = canonical_bytes(native)
    source_canonical_raw = canonical_bytes({"version": version, "source": True})
    source_compatibility_raw = canonical_bytes({"version": version, "source": True})
    source_authority = {
        "contractName": projection.CANDIDATE_AUTHORITY_CONTRACT_V4,
        "candidate": {"version": version},
        "expiresAtUtc": (now + timedelta(hours=5)).isoformat().replace("+00:00", "Z"),
        "custody": {
            "canonicalManifest": embedded(
                "RELEASE_CHANNEL.generated.json", source_canonical_raw
            ),
            "compatibilityManifest": embedded("releases.json", source_compatibility_raw),
            "nativeWindowsFinalizedEvidence": native,
        },
    }
    source_authority_raw = canonical_bytes(source_authority)
    readiness = {
        "canonicalManifest": {
            "path": "RELEASE_CHANNEL.generated.json",
            "sha256": hashlib.sha256(preprojection_canonical_raw).hexdigest(),
            "sizeBytes": len(preprojection_canonical_raw),
        },
        "compatibilityManifest": {
            "path": "releases.json",
            "sha256": hashlib.sha256(preprojection_compatibility_raw).hexdigest(),
            "sizeBytes": len(preprojection_compatibility_raw),
        },
        "contractName": projection.CANDIDATE_PREVIEW_READINESS_CONTRACT,
        "contractVersion": 1,
        "deployAuthority": False,
        "generatedAtUtc": now.isoformat().replace("+00:00", "Z"),
        "localizationGateSha256": "1" * 64,
        "nativeWindowsEvidenceSha256": hashlib.sha256(native_raw).hexdigest(),
        "platforms": ["linux", "windows"],
        "publicationEligible": True,
        "registryCommit": "2" * 40,
        "releaseProofSha256": "3" * 64,
        "releaseUploadAuthority": False,
        "releaseVersion": version,
        "routeAuthority": True,
        "sourceCandidateAuthoritySha256": hashlib.sha256(
            source_authority_raw
        ).hexdigest(),
        "sourceCanonicalManifestSha256": hashlib.sha256(
            source_canonical_raw
        ).hexdigest(),
        "sourceCompatibilityManifestSha256": hashlib.sha256(
            source_compatibility_raw
        ).hexdigest(),
        "status": "preview_ready",
    }
    projection_receipt = {
        "contractName": projection.CANDIDATE_GENERATION_PROJECTION_CONTRACT,
        "contractVersion": 1,
        "status": "passed",
        "generationId": generation_id,
        "evaluatedAtUtc": now.isoformat().replace("+00:00", "Z"),
        "sourceCanonicalManifestSha256": hashlib.sha256(
            preprojection_canonical_raw
        ).hexdigest(),
        "sourceCompatibilityManifestSha256": hashlib.sha256(
            preprojection_compatibility_raw
        ).hexdigest(),
        "projectedCanonicalManifestSha256": hashlib.sha256(canonical_raw).hexdigest(),
        "projectedCompatibilityManifestSha256": hashlib.sha256(
            compatibility_raw
        ).hexdigest(),
        "authoritySeed": seed_rows,
    }
    authority = {
        "contractName": projection.CANDIDATE_AUTHORITY_CONTRACT_V6,
        "contractVersion": 6,
        "status": "candidate_import_ready",
        "candidateImportAuthority": True,
        "candidateReviewAuthority": True,
        "ownerNativeFinalizationBridgeAuthority": True,
        "ownerNativeStageAuthoritySeedBridgeAuthority": True,
        "previewPublicationReadinessBridgeAuthority": True,
        "publicationAuthorized": False,
        "publicationEligible": False,
        "releaseUploadAuthority": False,
        "deployAuthority": False,
        "routeAuthority": False,
        "codeDeploymentAuthority": False,
        "platformScope": "windows_only",
        "exactIncomingDesktopScope": projection.CANDIDATE_EXACT_SCOPE,
        "crossRunBitReproducible": False,
        "signaturePolicy": {
            "signatureStatus": "unsigned",
            "signingRequired": False,
            "unsignedReason": "preview_policy",
        },
        "generatedAtUtc": now.isoformat().replace("+00:00", "Z"),
        "expiresAtUtc": (now + timedelta(hours=4)).isoformat().replace("+00:00", "Z"),
        "candidate": candidate,
        "custody": {
            "canonicalManifest": embedded(
                "RELEASE_CHANNEL.generated.json", canonical_raw
            ),
            "compatibilityManifest": embedded("releases.json", compatibility_raw),
            "inventory": embedded(
                "CANDIDATE_UPLOAD_INVENTORY.generated.json", inventory_raw
            ),
            "sourceCandidateAuthority": embedded(
                projection.CANDIDATE_SOURCE_AUTHORITY_PATH, source_authority_raw
            ),
            "publicationReadinessReceipt": embedded(
                projection.CANDIDATE_PREVIEW_READINESS_PATH,
                canonical_bytes(readiness),
            ),
            "nativeWindowsFinalizedEvidence": embedded(
                "proof/windows-native/"
                "UNSIGNED_WINDOWS_PREVIEW_NATIVE_FINALIZED_EVIDENCE.generated.json",
                native_raw,
            ),
            "preprojectionCanonicalManifest": embedded(
                projection.CANDIDATE_PREPROJECTION_CANONICAL_PATH,
                preprojection_canonical_raw,
            ),
            "preprojectionCompatibilityManifest": embedded(
                projection.CANDIDATE_PREPROJECTION_COMPATIBILITY_PATH,
                preprojection_compatibility_raw,
            ),
            "generationProjection": projection_receipt,
        },
    }

    class Projector:
        @staticmethod
        def project_manifest_pair(canonical_path, compatibility_path, *_args, **_kwargs):
            canonical_path.write_bytes(canonical_raw)
            compatibility_path.write_bytes(compatibility_raw)

    materializer = SimpleNamespace(_generation_projector=lambda: Projector())
    return authority, now, materializer


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


def test_projection_accepts_exact_preview_ready_v6_authority(monkeypatch) -> None:
    projection = load_projection()
    authority, now, materializer = v6_consumer_fixture(projection)
    monkeypatch.setattr(
        projection,
        "_validate_candidate_import_authority_v4",
        lambda value, **_kwargs: value,
    )
    monkeypatch.setattr(
        projection,
        "_load_candidate_authority_materializer",
        lambda: materializer,
    )

    assert projection._validate_candidate_import_authority_v6(
        authority,
        now=now,
    ) is authority


@pytest.mark.parametrize(
    "tamper",
    [
        "route_authority",
        "readiness_bridge",
        "lifetime",
        "readiness_platforms",
        "generation_digest",
    ],
)
def test_projection_rejects_broadened_or_drifted_v6_authority(
    monkeypatch,
    tamper: str,
) -> None:
    projection = load_projection()
    authority, now, materializer = v6_consumer_fixture(projection)
    monkeypatch.setattr(
        projection,
        "_validate_candidate_import_authority_v4",
        lambda value, **_kwargs: value,
    )
    monkeypatch.setattr(
        projection,
        "_load_candidate_authority_materializer",
        lambda: materializer,
    )
    if tamper == "route_authority":
        authority["routeAuthority"] = True
    elif tamper == "readiness_bridge":
        authority["previewPublicationReadinessBridgeAuthority"] = False
    elif tamper == "lifetime":
        authority["expiresAtUtc"] = (now + timedelta(hours=7)).isoformat().replace(
            "+00:00", "Z"
        )
    elif tamper == "readiness_platforms":
        binding = authority["custody"]["publicationReadinessReceipt"]
        readiness = json.loads(base64.b64decode(binding["base64"]))
        readiness["platforms"] = ["windows"]
        authority["custody"]["publicationReadinessReceipt"] = embedded(
            projection.CANDIDATE_PREVIEW_READINESS_PATH,
            canonical_bytes(readiness),
        )
    else:
        authority["custody"]["generationProjection"][
            "projectedCanonicalManifestSha256"
        ] = "0" * 64

    with pytest.raises(projection.ProjectionBlocked):
        projection._validate_candidate_import_authority_v6(authority, now=now)


def test_projection_dispatches_v6_authority_to_closed_validator(monkeypatch) -> None:
    projection = load_projection()
    expected = {"validated": True}
    monkeypatch.setattr(
        projection,
        "_validate_candidate_import_authority_v6",
        lambda _authority: expected,
    )

    assert projection._validate_candidate_import_authority(
        canonical_bytes({"contractName": projection.CANDIDATE_AUTHORITY_CONTRACT_V6})
    ) is expected
