from __future__ import annotations

import hashlib
import json

import pytest

from scripts import final_gold_janitor
from scripts import materialize_operator_release_dashboard
from scripts import materialize_release_ready_receipt
from scripts.public_edge_postdeploy_contract import (
    PUBLIC_EDGE_DOWNLOADS_AUTHORITY_BINDING_FIELDS,
    PUBLIC_EDGE_DOWNLOADS_BOUND_CONTRACT_NAME,
    PUBLIC_EDGE_POSTDEPLOY_BOUND_CONTRACT_NAME,
    PUBLIC_EDGE_POSTDEPLOY_LEGACY_CONTRACT_NAME,
    PUBLIC_EDGE_POSTDEPLOY_REQUIRED_FIELDS,
    build_public_edge_downloads_authority_binding,
    load_exact_public_edge_postdeploy_schema,
    public_edge_authorizing_binding_failures,
)


AUTHORIZING_SCHEMA_ADDITIONS = {
    "downloadsAuthorityBinding",
    "frontdoorNavigationPlaySignInRoute",
    "releaseChannelAuthorizationCapable",
    "releaseChannelReceiptBindingRequired",
    "releaseManifestGeneration",
    "releaseManifestSchema",
}


def bound_public_edge_payload(
    release_channel_receipt_sha256: str = "a" * 64,
) -> dict[str, object]:
    schema = load_exact_public_edge_postdeploy_schema(
        receipt_contract_name=PUBLIC_EDGE_POSTDEPLOY_BOUND_CONTRACT_NAME
    )
    payload: dict[str, object] = {
        field: None
        for field in schema["fields"]
    }
    payload.update(
        {
            "childReceipts": {},
            "contractName": PUBLIC_EDGE_POSTDEPLOY_BOUND_CONTRACT_NAME,
            "coreChildContracts": {
                "downloads": PUBLIC_EDGE_DOWNLOADS_BOUND_CONTRACT_NAME,
            },
            "expectedReleaseChannel": "public_stable",
            "expectedReleaseVersion": "run-20260726-120000",
            "failures": [],
            "generatedAtUtc": "2026-07-26T12:00:00Z",
            "releaseChannelAuthorizationCapable": True,
            "releaseChannelReceiptBindingRequired": True,
            "releaseManifestChannel": "public_stable",
            "releaseManifestGeneration": "generation-20260726",
            "releaseManifestSchema": "chummer.release-channel.v1",
            "releaseManifestVersion": "run-20260726-120000",
            "schemaContractName": schema["contractName"],
            "schemaSha256": schema["sha256"],
            "status": "pass",
        }
    )
    downloads_receipt = {
        "contractName": PUBLIC_EDGE_DOWNLOADS_BOUND_CONTRACT_NAME,
        "downloads_generation_matches_served_manifest": True,
        "expected_release_channel": payload["expectedReleaseChannel"],
        "release_channel_receipt_binding_status": "pass",
        "release_channel_receipt_sha256_actual": (
            release_channel_receipt_sha256
        ),
        "release_channel_receipt_sha256_expected": (
            release_channel_receipt_sha256
        ),
        "release_channel_receipt_sha256_matches": True,
        "release_channel_version": payload["expectedReleaseVersion"],
        "release_manifest_channel": payload["releaseManifestChannel"],
        "release_manifest_channel_matches_release_channel": True,
        "release_manifest_generation": payload[
            "releaseManifestGeneration"
        ],
        "release_manifest_schema": payload["releaseManifestSchema"],
        "release_manifest_version": payload["releaseManifestVersion"],
        "release_manifest_version_matches_release_channel": True,
        "status": "pass",
        "status_redirect_generation_matches_served_manifest": True,
    }
    payload["downloadsAuthorityBinding"] = (
        build_public_edge_downloads_authority_binding(
            downloads_receipt,
            downloads_receipt_sha256="b" * 64,
            release_channel_receipt_sha256=(
                release_channel_receipt_sha256
            ),
        )
    )
    return payload


def test_v2_schema_is_exact_full_shared_consumer_union() -> None:
    legacy = load_exact_public_edge_postdeploy_schema(
        receipt_contract_name=PUBLIC_EDGE_POSTDEPLOY_LEGACY_CONTRACT_NAME
    )
    bound = load_exact_public_edge_postdeploy_schema(
        receipt_contract_name=PUBLIC_EDGE_POSTDEPLOY_BOUND_CONTRACT_NAME
    )

    expected = (
        set(legacy["fields"])
        | set(PUBLIC_EDGE_POSTDEPLOY_REQUIRED_FIELDS)
        | AUTHORIZING_SCHEMA_ADDITIONS
    )

    assert len(legacy["fields"]) == 180
    assert len(bound["fields"]) == 279
    assert set(bound["fields"]) == expected
    assert not set(legacy["fields"]) - set(bound["fields"])


def test_bound_summary_is_exact_empty_child_and_non_secret_allowlist() -> None:
    payload = bound_public_edge_payload()
    binding = payload["downloadsAuthorityBinding"]

    assert payload["childReceipts"] == {}
    assert isinstance(binding, dict)
    assert set(binding) == PUBLIC_EDGE_DOWNLOADS_AUTHORITY_BINDING_FIELDS
    forbidden_key_fragments = {
        "body",
        "credential",
        "path",
        "raw",
        "secret",
        "ticket",
        "token",
        "url",
    }
    for field in binding:
        lowered = field.lower()
        assert not any(
            fragment in lowered
            for fragment in forbidden_key_fragments
        )
    serialized = json.dumps(binding, sort_keys=True)
    assert "://" not in serialized
    assert "/" not in serialized
    assert "\n" not in serialized
    assert public_edge_authorizing_binding_failures(
        payload,
        current_release_channel_sha256="a" * 64,
    ) == []


def test_binding_rejects_path_or_url_shaped_release_identity() -> None:
    payload = bound_public_edge_payload()
    binding = dict(payload["downloadsAuthorityBinding"])
    binding["releaseManifestGeneration"] = (
        "https://internal.invalid/ticket/secret"
    )
    binding_body = {
        key: value
        for key, value in binding.items()
        if key != "bindingSha256"
    }
    binding["bindingSha256"] = hashlib.sha256(
        json.dumps(
            binding_body,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    payload["downloadsAuthorityBinding"] = binding
    payload["releaseManifestGeneration"] = binding[
        "releaseManifestGeneration"
    ]

    failures = public_edge_authorizing_binding_failures(
        payload,
        current_release_channel_sha256="a" * 64,
    )

    assert (
        "public-edge postdeploy downloads authority binding release identity is unsafe"
        in failures
    )

    non_canonical = bound_public_edge_payload()
    non_canonical_binding = dict(
        non_canonical["downloadsAuthorityBinding"]
    )
    non_canonical_binding["releaseVersion"] = float("nan")
    non_canonical["downloadsAuthorityBinding"] = non_canonical_binding
    non_canonical_failures = public_edge_authorizing_binding_failures(
        non_canonical,
        current_release_channel_sha256="a" * 64,
    )
    assert (
        "public-edge postdeploy downloads authority binding encoding is invalid"
        in non_canonical_failures
    )


def test_v1_and_nested_child_receipts_are_non_authorizing() -> None:
    legacy_schema = load_exact_public_edge_postdeploy_schema(
        receipt_contract_name=PUBLIC_EDGE_POSTDEPLOY_LEGACY_CONTRACT_NAME
    )
    legacy = {
        field: None
        for field in legacy_schema["fields"]
    }
    legacy.update(
        {
            "childReceipts": {},
            "contractName": PUBLIC_EDGE_POSTDEPLOY_LEGACY_CONTRACT_NAME,
            "failures": [],
            "generatedAtUtc": "2026-07-26T12:00:00Z",
            "schemaContractName": legacy_schema["contractName"],
            "schemaSha256": legacy_schema["sha256"],
            "status": "pass",
        }
    )
    legacy_failures = public_edge_authorizing_binding_failures(
        legacy,
        current_release_channel_sha256="a" * 64,
    )

    nested = bound_public_edge_payload()
    nested["childReceipts"] = {
        "downloads": {
            "rawBody": "never public",
            "token": "never public",
        }
    }
    nested_failures = public_edge_authorizing_binding_failures(
        nested,
        current_release_channel_sha256="a" * 64,
    )

    assert legacy_failures
    assert (
        "public-edge postdeploy receipt contract does not match schema authority"
        in legacy_failures
    )
    assert (
        "public-edge postdeploy public childReceipts must be empty"
        in nested_failures
    )


@pytest.mark.parametrize(
    "consumer",
    (
        final_gold_janitor.public_edge_postdeploy_semantic_failures,
        materialize_operator_release_dashboard.public_edge_postdeploy_semantic_failures,
    ),
)
def test_final_consumers_share_exact_stale_binding_rejection(
    consumer,
) -> None:
    payload = bound_public_edge_payload()

    failures = consumer(
        payload,
        current_release_channel_sha256="c" * 64,
    )

    assert (
        "public-edge postdeploy release-channel binding is stale"
        in failures
    )


def test_release_ready_consumer_shares_exact_stale_binding_rejection(
    tmp_path,
) -> None:
    release_channel_path = tmp_path / "RELEASE_CHANNEL.generated.json"
    release_channel_path.write_text(
        '{"channel":"public_stable","version":"run-20260726-120000"}',
        encoding="utf-8",
    )
    current_digest = hashlib.sha256(
        release_channel_path.read_bytes()
    ).hexdigest()
    payload = bound_public_edge_payload("a" * 64)

    failures = (
        materialize_release_ready_receipt
        .public_edge_postdeploy_release_blocking_reasons(
            payload,
            release_channel_path=release_channel_path,
            expected_current_release_channel_sha256=current_digest,
        )
    )

    assert (
        "public-edge postdeploy release-channel binding is stale"
        in failures
    )

    nested = bound_public_edge_payload(current_digest)
    nested["childReceipts"] = {
        "downloads": {
            "rawBody": "never public",
            "token": "never public",
        }
    }
    nested_failures = (
        materialize_release_ready_receipt
        .public_edge_postdeploy_release_blocking_reasons(
            nested,
            release_channel_path=release_channel_path,
            expected_current_release_channel_sha256=current_digest,
        )
    )
    assert (
        "public-edge postdeploy public childReceipts must be empty"
        in nested_failures
    )
