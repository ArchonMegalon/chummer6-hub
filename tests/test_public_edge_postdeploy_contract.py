from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "public_edge_postdeploy_contract.py"


def load_module():
    spec = importlib.util.spec_from_file_location("public_edge_postdeploy_contract", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_checked_in_postdeploy_schema_is_canonical_closed_and_versioned() -> None:
    module = load_module()

    authority = module.load_exact_public_edge_postdeploy_schema()

    assert authority["contractName"] == (
        "chummer.public_edge_postdeploy_gate.schema.v1"
    )
    assert authority["receiptContractName"] == (
        "chummer.public_edge_postdeploy_gate.v1"
    )
    assert authority["path"] == module.PUBLIC_EDGE_POSTDEPLOY_SCHEMA_PATH
    assert len(authority["fields"]) == 180
    assert {
        "contractName",
        "failures",
        "generatedAtUtc",
        "schemaContractName",
        "schemaSha256",
        "status",
    }.issubset(authority["fields"])
    assert authority["sha256"] == hashlib.sha256(
        module.PUBLIC_EDGE_POSTDEPLOY_SCHEMA_PATH.read_bytes()
    ).hexdigest()
    schema = json.loads(
        module.PUBLIC_EDGE_POSTDEPLOY_SCHEMA_PATH.read_text(
            encoding="utf-8"
        )
    )
    assert schema["properties"]["childReceipts"] == {
        "additionalProperties": False,
        "maxProperties": 0,
        "type": "object",
    }


def test_checked_in_postdeploy_schema_rejects_noncanonical_or_duplicate_fields(
    tmp_path: Path,
) -> None:
    module = load_module()
    schema = json.loads(
        module.PUBLIC_EDGE_POSTDEPLOY_SCHEMA_PATH.read_text(
            encoding="utf-8"
        )
    )
    noncanonical = tmp_path / "noncanonical.schema.json"
    noncanonical.write_text(
        json.dumps(schema, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="strict canonical JSON"):
        module.load_exact_public_edge_postdeploy_schema(noncanonical)

    duplicated = tmp_path / "duplicate.schema.json"
    fields = schema["propertyNames"]["enum"]
    fields[-1] = fields[0]
    duplicated.write_text(
        json.dumps(schema, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="schema contract is invalid"):
        module.load_exact_public_edge_postdeploy_schema(duplicated)


@pytest.mark.parametrize(
    "secret_key",
    (
        "credentials",
        "databaseCredentials",
        "database_credentials",
        "DATABASE-CREDENTIALS",
        "passwords",
        "tokens",
        "secrets",
        "connectionString",
        "connection_strings",
        "dsn",
        "DSNs",
        "databasedsn",
        "dbPwd",
        "connStr",
        "accessKeys",
    ),
)
def test_secret_key_policy_rejects_plural_compound_and_dsn_aliases(
    secret_key: str,
) -> None:
    module = load_module()

    assert module.public_edge_secret_like_key(secret_key) is True
    assert (
        module.public_edge_forbidden_secret_key(secret_key, "hunter2")
        is True
    )


@pytest.mark.parametrize(
    ("key", "value"),
    (
        ("secretCanarySha256", "a" * 64),
        ("secretCanaryLeaked", False),
        ("mutationLockTokenSha256", "b" * 64),
        ("databaseCredentialsPresent", False),
        ("connectionStringCount", 0),
    ),
)
def test_secret_key_policy_allows_only_typed_bounded_metadata(
    key: str,
    value: object,
) -> None:
    module = load_module()

    assert module.public_edge_secret_like_key(key) is True
    assert module.public_edge_forbidden_secret_key(key, value) is False


@pytest.mark.parametrize(
    ("key", "value"),
    (
        ("passwordSha256", "hunter2"),
        ("tokensPresent", "hunter2"),
        ("credentialsCount", -1),
        ("connectionStringStatus", "pass"),
    ),
)
def test_secret_key_policy_rejects_untyped_or_unbounded_metadata(
    key: str,
    value: object,
) -> None:
    module = load_module()

    assert module.public_edge_forbidden_secret_key(key, value) is True


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

    assert normalized["childReceipts"] == {}
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
    assert normalized["childReceipts"] == {}
    assert normalized["frontdoorNavigationAnchorArtifactContract"] == "chummer.frontdoor_mobile_anchor_redirect.v1"
    assert "frontdoorNavigationAnchorPrivateIdentityRedacted" not in normalized
    assert "frontdoorNavigationAnchorSessionContextPresent" not in normalized


@pytest.mark.parametrize(
    "schema_identity",
    (
        "chummer.release-channel/v1",
        "vendor.schema/v2-preview",
    ),
)
def test_downloads_authority_schema_identity_accepts_one_bounded_contract_separator(
    schema_identity: str,
) -> None:
    module = load_module()

    assert module.PUBLIC_EDGE_DOWNLOADS_AUTHORITY_SCHEMA_PATTERN.fullmatch(
        schema_identity
    )


@pytest.mark.parametrize(
    "schema_identity",
    (
        "chummer.release-channel",
        "chummer.release-channel/v1/extra",
        "../release/v1",
        "chummer.release-channel/v1?token=private",
        "chummer.release-channel/v1#fragment",
    ),
)
def test_downloads_authority_schema_identity_rejects_path_and_url_syntax(
    schema_identity: str,
) -> None:
    module = load_module()

    assert (
        module.PUBLIC_EDGE_DOWNLOADS_AUTHORITY_SCHEMA_PATTERN.fullmatch(
            schema_identity
        )
        is None
    )
