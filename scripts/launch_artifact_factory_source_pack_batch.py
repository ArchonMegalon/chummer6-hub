#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_BASE_URL = "https://chummer.run"
DEFAULT_BATCH_PATH = "/api/internal/artifact-factory/source-pack-batches"
DEFAULT_RECIPES_PATH = "/api/internal/artifact-factory/recipes"
EXPECTED_CONTRACT_NAME = "chummer.run.artifact_factory.recipe_job.v1"
EXPECTED_RECIPE_VERSION = "2026-04-15"
PROVIDER_SPECIFIC_REF_PREFIXES = {
    "provider",
    "vendor",
    "one_off",
    "one-off",
    "heygen",
    "elevenlabs",
    "runway",
    "replicate",
    "veo",
}
CAMPAIGN_RECIPE_SUPPLEMENTS = [
    {
        "family": "campaign_cold_open",
        "recipeId": "campaign-cold-open-bundle",
        "allowedSourceKinds": ["campaign_primer", "campaign_pack", "campaign_cold_open_pack"],
        "allowedFormats": ["preview_card", "caption", "packet", "short_video", "audio"],
        "requiredReceiptPrefixes": ["campaign", "primer", "audience", "locale"],
    },
    {
        "family": "mission_briefing",
        "recipeId": "mission-briefing-reel",
        "allowedSourceKinds": ["mission_pack", "mission_briefing", "mission_briefing_pack"],
        "allowedFormats": ["preview_card", "caption", "packet", "short_video", "audio"],
        "requiredReceiptPrefixes": ["mission", "briefing", "audience", "locale"],
    },
]


class LaunchValidationError(SystemExit):
    pass


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Launch artifact-factory source-pack batches against the internal Hub orchestration API."
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("CHUMMER_ARTIFACT_FACTORY_BASE_URL", DEFAULT_BASE_URL),
        help="Hub base URL. Defaults to CHUMMER_ARTIFACT_FACTORY_BASE_URL or https://chummer.run.",
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("FLEET_INTERNAL_API_TOKEN", ""),
        help="Internal bearer token. Defaults to FLEET_INTERNAL_API_TOKEN.",
    )
    parser.add_argument(
        "--request-file",
        default="-",
        help="JSON request file for source-pack batch launch, or '-' to read from stdin.",
    )
    parser.add_argument(
        "--public-host",
        default=os.environ.get("CHUMMER_ARTIFACT_FACTORY_PUBLIC_HOST", ""),
        help="Optional Host header override for local edge verification.",
    )
    parser.add_argument(
        "--forwarded-proto",
        default=os.environ.get("CHUMMER_ARTIFACT_FACTORY_FORWARDED_PROTO", ""),
        help="Optional X-Forwarded-Proto header override for local edge verification.",
    )
    parser.add_argument(
        "--recipes",
        action="store_true",
        help="List approved artifact-factory recipes instead of launching a source-pack batch.",
    )
    return parser.parse_args(argv)


def read_request_payload(path_value: str) -> dict[str, Any]:
    if path_value == "-":
        raw = sys.stdin.read()
    else:
        raw = Path(path_value).read_text(encoding="utf-8")

    if not raw.strip():
        raise SystemExit("artifact-factory source-pack batch request is empty.")

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"artifact-factory source-pack batch request is not valid JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise SystemExit("artifact-factory source-pack batch request must be a JSON object.")

    return payload


def build_headers(token: str, public_host: str, forwarded_proto: str, include_json_body: bool) -> dict[str, str]:
    if not token.strip():
        raise SystemExit("artifact-factory internal bearer token is required.")

    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {token.strip()}",
    }
    if include_json_body:
        headers["Content-Type"] = "application/json"
    if public_host.strip():
        headers["Host"] = public_host.strip()
    if forwarded_proto.strip():
        headers["X-Forwarded-Proto"] = forwarded_proto.strip()
    return headers


def request_json(url: str, method: str, headers: dict[str, str], payload: dict[str, Any] | None) -> Any:
    body = None if payload is None else json.dumps(payload, indent=2).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            response_body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace").strip()
        detail = error_body or exc.reason
        raise SystemExit(f"artifact-factory request failed ({exc.code}): {detail}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"artifact-factory request failed: {exc.reason}") from exc

    if not response_body.strip():
        return {}

    try:
        return json.loads(response_body)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"artifact-factory response is not valid JSON: {exc}") from exc


def load_recipe_catalog(base_url: str, token: str, public_host: str, forwarded_proto: str) -> dict[str, Any]:
    response = request_json(
        f"{base_url}{DEFAULT_RECIPES_PATH}",
        "GET",
        build_headers(token, public_host, forwarded_proto, include_json_body=False),
        payload=None,
    )
    validate_recipe_catalog_contract(response)
    if not isinstance(response, dict):
        raise LaunchValidationError("artifact-factory recipe catalog response must be a JSON object.")

    recipes = response.get("recipes")
    if not isinstance(recipes, list) or not recipes:
        raise LaunchValidationError("artifact-factory recipe catalog response must include at least one recipe.")

    response["recipes"] = merge_campaign_recipe_supplements(recipes)
    return response


def merge_campaign_recipe_supplements(recipes: list[Any]) -> list[Any]:
    merged = list(recipes)
    families = {
        str(recipe.get("family")).strip().replace("-", "_").lower()
        for recipe in recipes
        if isinstance(recipe, dict) and str(recipe.get("family")).strip()
    }
    for supplement in CAMPAIGN_RECIPE_SUPPLEMENTS:
        if supplement["family"] not in families:
            merged.append(supplement)
    return merged


def validate_recipe_catalog_contract(response: Any) -> None:
    if not isinstance(response, dict):
        raise LaunchValidationError("artifact-factory recipe catalog response must be a JSON object.")

    contract_name = response.get("contractName")
    if contract_name != EXPECTED_CONTRACT_NAME:
        raise LaunchValidationError(
            "artifact-factory recipe catalog response contractName must stay "
            f"'{EXPECTED_CONTRACT_NAME}'."
        )

    recipe_version = response.get("recipeVersion")
    if recipe_version != EXPECTED_RECIPE_VERSION:
        raise LaunchValidationError(
            "artifact-factory recipe catalog response recipeVersion must stay "
            f"'{EXPECTED_RECIPE_VERSION}'."
        )


def validate_batch_launch_response(
    response: Any,
    recipe_catalog: dict[str, Any],
    normalized_payload: dict[str, Any],
) -> None:
    if not isinstance(response, dict):
        raise LaunchValidationError("artifact-factory source-pack batch response must be a JSON object.")

    expected_contract_name = recipe_catalog.get("contractName")
    expected_recipe_version = recipe_catalog.get("recipeVersion")
    if response.get("contractName") != expected_contract_name:
        raise LaunchValidationError(
            "artifact-factory source-pack batch response contractName must match the recipe catalog contractName."
        )

    if response.get("recipeVersion") != expected_recipe_version:
        raise LaunchValidationError(
            "artifact-factory source-pack batch response recipeVersion must match the recipe catalog recipeVersion."
        )

    state = response.get("state")
    if not isinstance(state, str) or not state.strip():
        raise LaunchValidationError("artifact-factory source-pack batch response must include a non-empty state.")

    required_families = normalize_string_list(response.get("requiredFamilies"), "requiredFamilies")
    expected_required_families = normalize_string_list(
        normalized_payload.get("requiredFamilies"),
        "launch request requiredFamilies",
    )
    if required_families != expected_required_families:
        raise LaunchValidationError(
            "artifact-factory source-pack batch response requiredFamilies must match the launch request requiredFamilies."
        )

    families = normalize_string_list(response.get("families"), "families")
    if families != expected_required_families:
        raise LaunchValidationError(
            "artifact-factory source-pack batch response families must match the launch request requiredFamilies."
        )

    source_pack_ids = normalize_string_list(response.get("sourcePackIds"), "sourcePackIds")
    expected_source_pack_ids = expected_source_pack_ids_for_families(
        expected_required_families,
        normalized_payload,
    )
    if source_pack_ids != expected_source_pack_ids:
        raise LaunchValidationError(
            "artifact-factory source-pack batch response sourcePackIds must match the launch request source packs for the requested recipe families."
        )

    recipe_ids = normalize_string_list(response.get("recipeIds"), "recipeIds")
    if not recipe_ids:
        raise LaunchValidationError(
            "artifact-factory source-pack batch response recipeIds must include at least one non-empty recipe id."
        )
    expected_recipe_ids = sorted(
        {
            str(recipe.get("recipeId")).strip()
            for recipe in recipe_catalog.get("recipes", [])
            if isinstance(recipe, dict)
            and isinstance(recipe.get("family"), str)
            and recipe.get("family", "").strip().replace("-", "_").lower() in expected_required_families
            and isinstance(recipe.get("recipeId"), str)
            and str(recipe.get("recipeId")).strip()
        }
    )
    if recipe_ids != expected_recipe_ids:
        raise LaunchValidationError(
            "artifact-factory source-pack batch response recipeIds must match the launch request requiredFamilies."
        )

    job_count = response.get("jobCount")
    if not isinstance(job_count, int) or job_count <= 0:
        raise LaunchValidationError("artifact-factory source-pack batch response jobCount must be a positive integer.")

    job_ids = normalize_string_list(response.get("jobIds"), "jobIds")
    jobs = response.get("jobs")
    if not isinstance(jobs, list) or len(jobs) != job_count:
        raise LaunchValidationError("artifact-factory source-pack batch response jobs length must match jobCount.")

    media_factory_requests = response.get("mediaFactoryRequests")
    if not isinstance(media_factory_requests, list) or len(media_factory_requests) != job_count:
        raise LaunchValidationError(
            "artifact-factory source-pack batch response mediaFactoryRequests length must match jobCount."
        )

    if len(job_ids) != job_count:
        raise LaunchValidationError("artifact-factory source-pack batch response jobIds length must match jobCount.")

    if job_count != len(expected_required_families):
        raise LaunchValidationError(
            "artifact-factory source-pack batch response jobCount must match the launch request requiredFamilies."
        )

    validate_job_response_shape(response, expected_required_families, job_ids)
    validate_media_factory_request_response(response, recipe_catalog, normalized_payload)
    validate_campaign_media_factory_response(response, recipe_catalog, normalized_payload)


def validate_job_response_shape(
    response: dict[str, Any],
    expected_required_families: list[str],
    expected_job_ids: list[str],
) -> None:
    jobs = response.get("jobs")
    if not isinstance(jobs, list):
        raise LaunchValidationError("artifact-factory source-pack batch response jobs must be an array.")

    response_job_ids = normalize_job_field_list(jobs, "jobId", "jobs jobId")
    if response_job_ids != expected_job_ids:
        raise LaunchValidationError(
            "artifact-factory source-pack batch response jobs jobId values must match response jobIds."
        )

    response_job_families = normalize_job_field_list(jobs, "family", "jobs family")
    if response_job_families != expected_required_families:
        raise LaunchValidationError(
            "artifact-factory source-pack batch response jobs family values must match the launch request requiredFamilies."
        )


def normalize_job_field_list(jobs: list[Any], field_name: str, label: str) -> list[str]:
    values: list[str] = []
    for job in jobs:
        if not isinstance(job, dict):
            raise LaunchValidationError(
                "artifact-factory source-pack batch response jobs must only contain objects."
            )

        value = job.get(field_name)
        if not isinstance(value, str) or not value.strip():
            raise LaunchValidationError(
                f"artifact-factory source-pack batch response {label} values must be non-empty strings."
            )

        values.append(value.strip().replace("-", "_").lower() if field_name == "family" else value.strip())

    return sorted(dict.fromkeys(values))


def validate_media_factory_request_response(
    response: dict[str, Any],
    recipe_catalog: dict[str, Any],
    normalized_payload: dict[str, Any],
) -> None:
    recipes_by_family = {
        str(recipe.get("family")).strip().replace("-", "_").lower(): recipe
        for recipe in recipe_catalog.get("recipes", [])
        if isinstance(recipe, dict) and str(recipe.get("family")).strip()
    }
    expected_families = normalize_string_list(
        normalized_payload.get("requiredFamilies"),
        "launch request requiredFamilies",
    )
    media_factory_requests = response.get("mediaFactoryRequests")
    if not isinstance(media_factory_requests, list):
        raise LaunchValidationError(
            "artifact-factory source-pack batch response mediaFactoryRequests must be an array."
        )

    for family in expected_families:
        recipe = recipes_by_family.get(family)
        recipe_id = string_field(recipe or {}, "recipeId")
        if not recipe_id:
            raise LaunchValidationError(
                f"artifact-factory recipe catalog is missing recipeId for family '{family}'."
            )

        matching_requests = [
            item
            for item in media_factory_requests
            if isinstance(item, dict) and string_field(item, "recipeId") == recipe_id
        ]
        if len(matching_requests) != 1:
            raise LaunchValidationError(
                f"artifact-factory source-pack batch response mediaFactoryRequests must include exactly one recipeId '{recipe_id}'."
            )

        validate_media_factory_request_family_shape(family, recipe_id, matching_requests[0], normalized_payload)


def validate_media_factory_request_family_shape(
    family: str,
    recipe_id: str,
    media_request: dict[str, Any],
    normalized_payload: dict[str, Any],
) -> None:
    required_receipt_refs = normalize_string_list(
        media_request.get("requiredReceiptRefs"),
        f"mediaFactoryRequest '{recipe_id}' requiredReceiptRefs",
    )
    if family not in {"campaign_cold_open", "mission_briefing"}:
        expected_receipt_prefixes = expected_receipt_prefixes_for_family(family)
        missing_receipt_prefixes = [
            prefix for prefix in expected_receipt_prefixes if not receipt_ref_matches_prefix(set(required_receipt_refs), prefix)
        ]
        if missing_receipt_prefixes:
            raise LaunchValidationError(
                f"artifact-factory source-pack batch response mediaFactoryRequest '{recipe_id}' missing receipt prefix(es): "
                + ", ".join(missing_receipt_prefixes)
                + "."
            )

    public_proof_shelf_refs = normalize_string_list(
        media_request.get("publicProofShelfRefs"),
        f"mediaFactoryRequest '{recipe_id}' publicProofShelfRefs",
    )
    approved_source_packs = media_request.get("approvedSourcePacks")
    if not isinstance(approved_source_packs, list) or not approved_source_packs:
        raise LaunchValidationError(
            f"artifact-factory source-pack batch response mediaFactoryRequest '{recipe_id}' must include approvedSourcePacks."
        )

    expected_source_pack_ids = expected_source_pack_ids_for_family(family, normalized_payload)
    response_source_pack_ids = sorted(
        {
            string_field(source_pack, "sourcePackId")
            for source_pack in approved_source_packs
            if isinstance(source_pack, dict) and string_field(source_pack, "sourcePackId")
        }
    )
    if response_source_pack_ids != expected_source_pack_ids:
        raise LaunchValidationError(
            f"artifact-factory source-pack batch response mediaFactoryRequest '{recipe_id}' approvedSourcePacks must match the launch request source packs for family '{family}'."
        )

    output_bindings = media_request.get("outputBindings")
    if not isinstance(output_bindings, list) or not output_bindings:
        raise LaunchValidationError(
            f"artifact-factory source-pack batch response mediaFactoryRequest '{recipe_id}' must include outputBindings."
        )

    validate_family_response_output_bindings(family, recipe_id, output_bindings, set(public_proof_shelf_refs))


def expected_receipt_prefixes_for_family(family: str) -> list[str]:
    return {
        "release": ["release", "promotion", "public-shelf"],
        "fix": ["fix", "install", "support"],
        "support": ["support", "privacy", "install"],
        "publication": ["publication", "moderation", "public-shelf"],
        "campaign_cold_open": ["campaign", "primer", "audience", "locale"],
        "mission_briefing": ["mission", "briefing", "audience", "locale"],
    }.get(family, [])


def expected_source_pack_ids_for_family(family: str, normalized_payload: dict[str, Any]) -> list[str]:
    family_to_source_kinds = {
        "release": {"release", "release_evidence", "desktop_release", "install_receipt"},
        "fix": {"fix_receipt", "support_case", "install_receipt", "release"},
        "support": {"support_case", "crash_report", "install_receipt", "release"},
        "publication": {"publication", "creator_publication", "campaign_recap", "runtime_bundle"},
        "campaign_cold_open": {"campaign_primer", "campaign_pack", "campaign_cold_open_pack"},
        "mission_briefing": {"mission_pack", "mission_briefing", "mission_briefing_pack"},
    }
    allowed_source_kinds = family_to_source_kinds.get(family, set())
    return sorted(
        {
            string_field(source_pack, "sourcePackId")
            for source_pack in normalized_payload.get("sourcePacks", [])
            if isinstance(source_pack, dict)
            and string_field(source_pack, "sourcePackId")
            and string_field(source_pack, "sourcePackKind").replace("-", "_").lower() in allowed_source_kinds
        }
    )


def expected_source_pack_ids_for_families(families: list[str], normalized_payload: dict[str, Any]) -> list[str]:
    expected_source_pack_ids: set[str] = set()
    for family in families:
        expected_source_pack_ids.update(expected_source_pack_ids_for_family(family, normalized_payload))
    return sorted(expected_source_pack_ids)


def validate_family_response_output_bindings(
    family: str,
    recipe_id: str,
    output_bindings: list[Any],
    public_proof_shelf_refs: set[str],
) -> None:
    for binding in output_bindings:
        if not isinstance(binding, dict):
            raise LaunchValidationError(
                f"artifact-factory source-pack batch response mediaFactoryRequest '{recipe_id}' outputBindings must only contain objects."
            )

        public_ref = string_field(binding, "publicRef")
        if not public_ref:
            raise LaunchValidationError(
                f"artifact-factory source-pack batch response mediaFactoryRequest '{recipe_id}' outputBindings must include publicRef."
            )

        if not family_public_ref_is_allowed(family, public_ref):
            raise LaunchValidationError(
                f"artifact-factory source-pack batch response mediaFactoryRequest '{recipe_id}' output publicRef '{public_ref}' "
                "must stay on the approved release, support, fix, publication, campaign, or mission proof shelf."
            )

        shelf_ref = public_ref.rsplit("/", 1)[0]
        if shelf_ref not in public_proof_shelf_refs:
            raise LaunchValidationError(
                f"artifact-factory source-pack batch response mediaFactoryRequest '{recipe_id}' publicProofShelfRefs must include '{shelf_ref}'."
            )


def family_public_ref_is_allowed(family: str, public_ref: str) -> bool:
    prefixes_by_family = {
        "release": ["/artifacts/release-bundles/"],
        "fix": ["/account/fix-followthrough/", "/account/support/", "/artifacts/release-bundles/"],
        "support": ["/account/support-packets/", "/account/support/"],
        "publication": ["/artifacts/publications/"],
        "campaign_cold_open": ["/artifacts/campaigns/"],
        "mission_briefing": ["/artifacts/missions/"],
    }
    return any(public_ref.startswith(prefix) for prefix in prefixes_by_family.get(family, []))


def validate_campaign_media_factory_response(
    response: dict[str, Any],
    recipe_catalog: dict[str, Any],
    normalized_payload: dict[str, Any],
) -> None:
    campaign_families = [
        family
        for family in normalize_string_list(normalized_payload.get("requiredFamilies"), "launch request requiredFamilies")
        if family in {"campaign_cold_open", "mission_briefing"}
    ]
    if not campaign_families:
        return

    audience = string_field(normalized_payload, "audience")
    locale = string_field(normalized_payload, "locale") or "en-US"
    expected_anchors = {f"audience:{audience}".lower(), f"locale:{locale}".lower()}
    media_factory_requests = response.get("mediaFactoryRequests")
    recipes_by_family = {
        str(recipe.get("family")).strip().replace("-", "_").lower(): recipe
        for recipe in recipe_catalog.get("recipes", [])
        if isinstance(recipe, dict) and str(recipe.get("family")).strip()
    }

    for family in campaign_families:
        recipe = recipes_by_family.get(family)
        recipe_id = string_field(recipe or {}, "recipeId")
        if not recipe_id:
            raise LaunchValidationError(
                f"artifact-factory recipe catalog is missing recipeId for campaign family '{family}'."
            )

        media_request = next(
            (
                item
                for item in media_factory_requests
                if isinstance(item, dict) and string_field(item, "recipeId") == recipe_id
            ),
            None,
        )
        if media_request is None:
            raise LaunchValidationError(
                f"artifact-factory source-pack batch response mediaFactoryRequests must include recipeId '{recipe_id}' for audience-safe campaign artifacts."
            )

        required_receipt_refs = {
            str(receipt_ref).strip().lower()
            for receipt_ref in media_request.get("requiredReceiptRefs", []) or []
            if isinstance(receipt_ref, str) and receipt_ref.strip()
        }
        missing_receipt_anchors = sorted(anchor for anchor in expected_anchors if anchor not in required_receipt_refs)
        if missing_receipt_anchors:
            raise LaunchValidationError(
                f"artifact-factory source-pack batch response mediaFactoryRequest '{recipe_id}' must include campaign proof anchor(s): "
                + ", ".join(missing_receipt_anchors)
                + "."
            )

        approved_source_packs = media_request.get("approvedSourcePacks")
        if not isinstance(approved_source_packs, list) or not approved_source_packs:
            raise LaunchValidationError(
                f"artifact-factory source-pack batch response mediaFactoryRequest '{recipe_id}' must include approvedSourcePacks for audience-safe campaign artifacts."
            )

        validate_campaign_response_source_packs(family, recipe_id, approved_source_packs, audience, locale, expected_anchors)

        public_proof_shelf_refs = {
            str(proof_ref).strip()
            for proof_ref in media_request.get("publicProofShelfRefs", []) or []
            if isinstance(proof_ref, str) and proof_ref.strip()
        }
        output_bindings = media_request.get("outputBindings")
        if not isinstance(output_bindings, list) or not output_bindings:
            raise LaunchValidationError(
                f"artifact-factory source-pack batch response mediaFactoryRequest '{recipe_id}' must include outputBindings for campaign artifacts."
            )

        validate_campaign_response_output_bindings(family, recipe_id, output_bindings, public_proof_shelf_refs)


def validate_campaign_response_source_packs(
    family: str,
    recipe_id: str,
    approved_source_packs: list[Any],
    audience: str,
    locale: str,
    expected_anchors: set[str],
) -> None:
    for source_pack in approved_source_packs:
        if not isinstance(source_pack, dict):
            raise LaunchValidationError(
                f"artifact-factory source-pack batch response mediaFactoryRequest '{recipe_id}' approvedSourcePacks must only contain objects."
            )

        pack_audience = string_field(source_pack, "audience")
        allowed_audiences = [item.strip() for item in pack_audience.split(",") if item.strip()]
        if audience not in allowed_audiences:
            raise LaunchValidationError(
                f"artifact-factory source-pack batch response mediaFactoryRequest '{recipe_id}' source pack "
                f"'{source_pack.get('sourcePackId')}' audience does not allow requested audience '{audience}'."
            )

        pack_locale = string_field(source_pack, "locale")
        if pack_locale.lower() != locale.lower():
            raise LaunchValidationError(
                f"artifact-factory source-pack batch response mediaFactoryRequest '{recipe_id}' source pack "
                f"'{source_pack.get('sourcePackId')}' locale '{pack_locale}' does not match requested locale '{locale}'."
            )

        evidence_refs = {
            str(evidence_ref).strip().lower()
            for evidence_ref in source_pack.get("evidenceRefs", []) or []
            if isinstance(evidence_ref, str) and evidence_ref.strip()
        }
        missing_evidence_anchors = sorted(anchor for anchor in expected_anchors if anchor not in evidence_refs)
        if missing_evidence_anchors:
            raise LaunchValidationError(
                f"artifact-factory source-pack batch response mediaFactoryRequest '{recipe_id}' source pack "
                f"'{source_pack.get('sourcePackId')}' must preserve evidence anchor(s): "
                + ", ".join(missing_evidence_anchors)
                + "."
            )

        if family == "campaign_cold_open" and not (string_field(source_pack, "campaignId") or string_field(source_pack, "publicShelfRef")):
            raise LaunchValidationError(
                f"artifact-factory source-pack batch response mediaFactoryRequest '{recipe_id}' source pack "
                f"'{source_pack.get('sourcePackId')}' must preserve a campaignId or publicShelfRef."
            )
        if family == "mission_briefing" and not (string_field(source_pack, "missionId") or string_field(source_pack, "publicShelfRef")):
            raise LaunchValidationError(
                f"artifact-factory source-pack batch response mediaFactoryRequest '{recipe_id}' source pack "
                f"'{source_pack.get('sourcePackId')}' must preserve a missionId or publicShelfRef."
            )


def validate_campaign_response_output_bindings(
    family: str,
    recipe_id: str,
    output_bindings: list[Any],
    public_proof_shelf_refs: set[str],
) -> None:
    for binding in output_bindings:
        if not isinstance(binding, dict):
            raise LaunchValidationError(
                f"artifact-factory source-pack batch response mediaFactoryRequest '{recipe_id}' outputBindings must only contain objects."
            )

        public_ref = string_field(binding, "publicRef")
        if not public_ref:
            raise LaunchValidationError(
                f"artifact-factory source-pack batch response mediaFactoryRequest '{recipe_id}' outputBindings must include publicRef."
            )

        expected_prefix = "/artifacts/campaigns/" if family == "campaign_cold_open" else "/artifacts/missions/"
        expected_leaf = "/cold-open/" if family == "campaign_cold_open" else "/briefing/"
        if expected_prefix not in public_ref or expected_leaf not in public_ref:
            raise LaunchValidationError(
                f"artifact-factory source-pack batch response mediaFactoryRequest '{recipe_id}' output publicRef '{public_ref}' "
                "must stay on the campaign cold-open or mission briefing proof shelf."
            )

        shelf_ref = public_ref.rsplit("/", 1)[0]
        if shelf_ref not in public_proof_shelf_refs:
            raise LaunchValidationError(
                f"artifact-factory source-pack batch response mediaFactoryRequest '{recipe_id}' publicProofShelfRefs must include '{shelf_ref}'."
            )


def normalize_string_list(value: Any, field_name: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise LaunchValidationError(
            f"artifact-factory source-pack batch response {field_name} must be a non-empty array of strings."
        )

    normalized_values: list[str] = []
    for entry in value:
        if not isinstance(entry, str) or not entry.strip():
            raise LaunchValidationError(
                f"artifact-factory source-pack batch response {field_name} must only contain non-empty strings."
            )

        normalized_values.append(entry.strip())

    return sorted(dict.fromkeys(normalized_values))


def normalize_launch_payload(payload: dict[str, Any], recipe_catalog: dict[str, Any]) -> dict[str, Any]:
    batch_id = payload.get("batchId")
    if not isinstance(batch_id, str) or not batch_id.strip():
        raise LaunchValidationError("artifact-factory source-pack batch request must include a non-empty batchId.")

    requested_by = payload.get("requestedBy")
    if not isinstance(requested_by, str) or not requested_by.strip():
        raise LaunchValidationError("artifact-factory source-pack batch request must include a non-empty requestedBy.")

    source_packs = payload.get("sourcePacks")
    if not isinstance(source_packs, list) or not source_packs:
        raise LaunchValidationError("artifact-factory source-pack batch request must include at least one approved source pack.")

    recipes = recipe_catalog["recipes"]
    recipe_map: dict[str, dict[str, Any]] = {}
    for recipe in recipes:
        if not isinstance(recipe, dict):
            raise LaunchValidationError("artifact-factory recipe catalog contains a non-object recipe.")

        family = recipe.get("family")
        if not isinstance(family, str) or not family.strip():
            raise LaunchValidationError("artifact-factory recipe catalog contains a recipe without a family.")

        recipe_map[family.strip().replace("-", "_").lower()] = recipe

    if not recipe_map:
        raise LaunchValidationError("artifact-factory recipe catalog did not publish any usable recipe families.")

    for source_pack in source_packs:
        if not isinstance(source_pack, dict):
            raise LaunchValidationError("artifact-factory source-pack batch request sourcePacks must only contain objects.")

        approval_state = source_pack.get("approvalState")
        if not isinstance(approval_state, str) or approval_state.strip().lower() != "approved":
            raise LaunchValidationError("artifact-factory source-pack batch request sourcePacks must already be approved.")

        source_pack_kind = source_pack.get("sourcePackKind")
        if not isinstance(source_pack_kind, str) or not source_pack_kind.strip():
            raise LaunchValidationError("artifact-factory source-pack batch request sourcePacks must include sourcePackKind.")

        validate_source_pack_refs(source_pack)

    source_pack_kinds = {
        source_pack["sourcePackKind"].strip().replace("-", "_").lower()
        for source_pack in source_packs
        if isinstance(source_pack, dict) and isinstance(source_pack.get("sourcePackKind"), str)
    }
    inferred_families = sorted(
        family
        for family, recipe in recipe_map.items()
        if recipe_can_launch_from_source_packs(family, recipe, source_packs)
    )

    required_families_input = payload.get("requiredFamilies")
    if required_families_input is None:
        required_families = inferred_families
        if not required_families:
            raise LaunchValidationError(
                "artifact-factory source-pack batch request has no approved source packs matching any supported recipe family."
            )
    else:
        if not isinstance(required_families_input, list) or not required_families_input:
            raise LaunchValidationError("artifact-factory source-pack batch request requiredFamilies must be a non-empty array when provided.")

        required_families = []
        for family_value in required_families_input:
            if not isinstance(family_value, str) or not family_value.strip():
                raise LaunchValidationError("artifact-factory source-pack batch request requiredFamilies must only contain non-empty strings.")

            family = family_value.strip().replace("-", "_").lower()
            if family not in recipe_map:
                raise LaunchValidationError(f"artifact-factory source-pack batch request requires unsupported recipe family '{family_value}'.")

            if family not in required_families:
                required_families.append(family)

        required_families.sort()

    missing_families = [
        family
        for family in required_families
        if not recipe_can_launch_from_source_packs(family, recipe_map[family], source_packs)
    ]
    if missing_families:
        raise LaunchValidationError(
            "artifact-factory source-pack batch request has no approved source packs for required recipe family/families: "
            + ", ".join(missing_families)
            + "."
        )

    validate_campaign_audience_and_locale(payload, required_families, recipe_map)

    requested_formats = payload.get("requestedFormats")
    if requested_formats is not None:
        if not isinstance(requested_formats, list):
            raise LaunchValidationError("artifact-factory source-pack batch request requestedFormats must be an array when provided.")

        for format_override in requested_formats:
            if not isinstance(format_override, dict):
                raise LaunchValidationError("artifact-factory source-pack batch request requestedFormats must only contain objects.")

            family_value = format_override.get("family")
            if not isinstance(family_value, str) or not family_value.strip():
                raise LaunchValidationError("artifact-factory source-pack batch request requestedFormats entries must include family.")

            family = family_value.strip().replace("-", "_").lower()
            if family not in required_families:
                raise LaunchValidationError(
                    f"artifact-factory source-pack batch request requestedFormats contains family '{family_value}' outside requiredFamilies."
                )

            formats = format_override.get("formats")
            if not isinstance(formats, list) or not formats:
                raise LaunchValidationError(
                    f"artifact-factory source-pack batch request requestedFormats for family '{family_value}' must include at least one format."
                )

            allowed_formats = {
                str(format_name).strip().replace("-", "_").lower()
                for format_name in recipe_map[family].get("allowedFormats", [])
                if str(format_name).strip()
            }
            unsupported_formats = sorted(
                {
                    str(format_name).strip().replace("-", "_").lower()
                    for format_name in formats
                    if not isinstance(format_name, str)
                    or not format_name.strip()
                    or str(format_name).strip().replace("-", "_").lower() not in allowed_formats
                }
            )
            if unsupported_formats:
                raise LaunchValidationError(
                    f"artifact-factory source-pack batch request requestedFormats for family '{family_value}' "
                    f"contains unsupported format(s): {', '.join(unsupported_formats)}."
                )

    normalized_payload = dict(payload)
    normalized_payload["batchId"] = batch_id.strip()
    normalized_payload["requestedBy"] = requested_by.strip()
    normalized_payload["requiredFamilies"] = required_families
    return normalized_payload


def recipe_can_launch_from_source_packs(
    family: str,
    recipe: dict[str, Any],
    source_packs: list[dict[str, Any]],
) -> bool:
    allowed_source_kinds = {
        str(kind).strip().replace("-", "_").lower()
        for kind in recipe.get("allowedSourceKinds", [])
        if str(kind).strip()
    }
    matching_source_packs = [
        source_pack
        for source_pack in source_packs
        if isinstance(source_pack, dict)
        and isinstance(source_pack.get("sourcePackKind"), str)
        and source_pack["sourcePackKind"].strip().replace("-", "_").lower() in allowed_source_kinds
    ]
    if not matching_source_packs:
        return False

    if not family_has_required_anchor(family, matching_source_packs):
        return False

    required_receipt_prefixes = [
        str(prefix).strip().lower()
        for prefix in recipe.get("requiredReceiptPrefixes", [])
        if str(prefix).strip()
    ]
    evidence_refs = {
        str(evidence_ref).strip().lower()
        for source_pack in matching_source_packs
        for evidence_ref in source_pack.get("evidenceRefs", []) or []
        if isinstance(evidence_ref, str) and evidence_ref.strip()
    }
    return all(receipt_ref_matches_prefix(evidence_refs, prefix) for prefix in required_receipt_prefixes)


def family_has_required_anchor(family: str, source_packs: list[dict[str, Any]]) -> bool:
    if family == "release":
        return any(string_field(source_pack, "releaseArtifactId") or string_field(source_pack, "publicShelfRef") for source_pack in source_packs)
    if family == "fix":
        return any(string_field(source_pack, "supportCaseId") or string_field(source_pack, "releaseArtifactId") for source_pack in source_packs)
    if family == "support":
        return any(string_field(source_pack, "supportCaseId") for source_pack in source_packs)
    if family == "publication":
        return any(string_field(source_pack, "publicationId") or string_field(source_pack, "publicShelfRef") for source_pack in source_packs)
    if family == "campaign_cold_open":
        return campaign_pack_metadata_matches_request(family, source_packs)
    if family == "mission_briefing":
        return campaign_pack_metadata_matches_request(family, source_packs)
    return False


def campaign_pack_metadata_matches_request(family: str, source_packs: list[dict[str, Any]]) -> bool:
    return any(
        (string_field(source_pack, "campaignId") if family == "campaign_cold_open" else string_field(source_pack, "missionId"))
        or string_field(source_pack, "publicShelfRef")
        for source_pack in source_packs
    )


def validate_campaign_audience_and_locale(payload: dict[str, Any], required_families: list[str], recipe_map: dict[str, dict[str, Any]]) -> None:
    campaign_families = [family for family in required_families if family in {"campaign_cold_open", "mission_briefing"}]
    if not campaign_families:
        return

    audience = string_field(payload, "audience")
    if not audience or audience == "public-proof-shelf":
        raise LaunchValidationError(
            "artifact-factory source-pack batch request campaign recipes require an explicit audience token."
        )

    locale = string_field(payload, "locale") or "en-US"
    for family in campaign_families:
        recipe = recipe_map[family]
        allowed_source_kinds = {
            str(kind).strip().replace("-", "_").lower()
            for kind in recipe.get("allowedSourceKinds", [])
            if str(kind).strip()
        }
        for source_pack in payload["sourcePacks"]:
            source_pack_kind = string_field(source_pack, "sourcePackKind").replace("-", "_").lower()
            if source_pack_kind not in allowed_source_kinds:
                continue

            pack_audience = string_field(source_pack, "audience")
            if not pack_audience:
                raise LaunchValidationError(
                    f"artifact-factory source-pack batch request source pack '{source_pack.get('sourcePackId')}' must include audience for {family}."
                )

            allowed_audiences = [item.strip() for item in pack_audience.split(",") if item.strip()]
            if audience not in allowed_audiences:
                raise LaunchValidationError(
                    f"artifact-factory source-pack batch request source pack '{source_pack.get('sourcePackId')}' audience does not allow requested audience '{audience}'."
                )

            pack_locale = string_field(source_pack, "locale")
            if not pack_locale:
                raise LaunchValidationError(
                    f"artifact-factory source-pack batch request source pack '{source_pack.get('sourcePackId')}' must include locale for {family}."
                )

            if pack_locale.lower() != locale.lower():
                raise LaunchValidationError(
                    f"artifact-factory source-pack batch request source pack '{source_pack.get('sourcePackId')}' locale '{pack_locale}' does not match requested locale '{locale}'."
                )

            require_campaign_proof_anchor(source_pack, "audience", audience)
            require_campaign_proof_anchor(source_pack, "locale", locale)
            validate_campaign_public_shelf_ref(source_pack, family)


def require_campaign_proof_anchor(source_pack: dict[str, Any], anchor_prefix: str, expected_value: str) -> None:
    expected_ref = f"{anchor_prefix}:{expected_value}".lower()
    evidence_refs = {
        str(evidence_ref).strip().lower()
        for evidence_ref in source_pack.get("evidenceRefs", []) or []
        if isinstance(evidence_ref, str) and evidence_ref.strip()
    }
    if expected_ref in evidence_refs:
        return

    raise LaunchValidationError(
        "artifact-factory source-pack batch request source pack "
        f"'{source_pack.get('sourcePackId')}' must include evidenceRef '{anchor_prefix}:{expected_value}' "
        "for audience-safe campaign artifact requests."
    )


def validate_campaign_public_shelf_ref(source_pack: dict[str, Any], family: str) -> None:
    public_shelf_ref = string_field(source_pack, "publicShelfRef")
    if not public_shelf_ref:
        return

    source_pack_id = string_field(source_pack, "sourcePackId")
    expected_prefix = "/artifacts/campaigns/" if family == "campaign_cold_open" else "/artifacts/missions/"
    expected_surface = "cold-open" if family == "campaign_cold_open" else "briefing"
    if campaign_surface_shelf_ref_is_allowed(public_shelf_ref, expected_prefix, expected_surface):
        return

    raise LaunchValidationError(
        f"artifact-factory source-pack batch request source pack '{source_pack_id}' publicShelfRef "
        f"must resolve to {expected_prefix}{{id}}/{expected_surface} for audience-safe campaign artifact requests."
    )


def campaign_surface_shelf_ref_is_allowed(public_shelf_ref: str, expected_prefix: str, expected_surface: str) -> bool:
    if not public_shelf_ref.startswith(expected_prefix):
        return False

    remainder = public_shelf_ref[len(expected_prefix):].strip("/")
    segments = [segment for segment in remainder.split("/") if segment]
    return (
        len(segments) == 2
        and segments[1].lower() == expected_surface
    ) or (
        len(segments) == 3
        and segments[1].lower() == expected_surface
        and segments[2].lower() == "bundles"
    )


def validate_source_pack_refs(source_pack: dict[str, Any]) -> None:
    source_pack_id = string_field(source_pack, "sourcePackId")
    if not source_pack_id:
        raise LaunchValidationError("artifact-factory source-pack batch request sourcePacks must include sourcePackId.")

    reject_provider_specific_ref(source_pack_id, source_pack_id, "sourcePackId")
    reject_provider_specific_ref(source_pack_id, string_field(source_pack, "provenanceRef"), "provenanceRef")

    public_shelf_ref = string_field(source_pack, "publicShelfRef")
    if public_shelf_ref:
        reject_provider_specific_ref(source_pack_id, public_shelf_ref, "publicShelfRef")
        reject_non_local_public_shelf_ref(source_pack_id, public_shelf_ref, "publicShelfRef")

    evidence_refs = source_pack.get("evidenceRefs", []) or []
    if not isinstance(evidence_refs, list):
        raise LaunchValidationError(
            f"artifact-factory source-pack batch request source pack '{source_pack_id}' evidenceRefs must be an array when provided."
        )

    for evidence_ref in evidence_refs:
        if not isinstance(evidence_ref, str) or not evidence_ref.strip():
            continue

        reject_provider_specific_ref(source_pack_id, evidence_ref.strip(), "evidenceRef")
        if evidence_ref.strip().lower().startswith("public-shelf:"):
            reject_non_local_public_shelf_ref(source_pack_id, evidence_ref.split(":", 1)[1], "evidenceRef")


def reject_provider_specific_ref(source_pack_id: str, value: str, field_name: str) -> None:
    normalized = value.strip()
    if not normalized:
        if field_name == "provenanceRef":
            raise LaunchValidationError(
                f"artifact-factory source-pack batch request source pack '{source_pack_id}' must include provenanceRef."
            )
        return

    if normalized.lower().startswith(("http://", "https://")) or (
        "://" in normalized and not is_external_public_shelf_evidence_ref(normalized, field_name)
    ):
        raise LaunchValidationError(
            f"artifact-factory source-pack batch request source pack '{source_pack_id}' has external absolute URI {field_name}; "
            "jobs must launch from approved source-pack receipts instead of one-off provider flows."
        )

    prefix = first_ref_prefix(normalized)
    if (
        normalized.lower() in PROVIDER_SPECIFIC_REF_PREFIXES
        or prefix.lower() in PROVIDER_SPECIFIC_REF_PREFIXES
        or (
            not is_external_public_shelf_evidence_ref(normalized, field_name)
            and contains_provider_specific_token(normalized)
        )
    ):
        raise LaunchValidationError(
            f"artifact-factory source-pack batch request source pack '{source_pack_id}' has provider-specific {field_name}; "
            "jobs must launch from approved source-pack receipts instead of one-off provider flows."
        )


def first_ref_prefix(normalized: str) -> str:
    if normalized.startswith("/"):
        return ""

    colon_index = normalized.find(":")
    slash_index = normalized.find("/")
    indexes = [index for index in (colon_index, slash_index) if index >= 0]
    return normalized[: min(indexes)].strip() if indexes else ""


def is_external_public_shelf_evidence_ref(normalized: str, field_name: str) -> bool:
    return field_name == "evidenceRef" and normalized.lower().startswith("public-shelf:") and not normalized.split(":", 1)[1].lstrip().startswith("/")


def contains_provider_specific_token(value: str) -> bool:
    lower = value.lower()
    return any(contains_delimited_token(lower, token.lower()) for token in PROVIDER_SPECIFIC_REF_PREFIXES)


def contains_delimited_token(value: str, token: str) -> bool:
    start_index = 0
    while True:
        index = value.find(token, start_index)
        if index < 0:
            return False

        end_index = index + len(token)
        if is_provider_token_boundary(value, index - 1) and is_provider_token_boundary(value, end_index):
            return True

        start_index = index + 1


def is_provider_token_boundary(value: str, index: int) -> bool:
    return index < 0 or index >= len(value) or value[index] in {":", "/", "\\", "-", "_", "."}


def reject_non_local_public_shelf_ref(source_pack_id: str, value: str, field_name: str) -> None:
    public_shelf_ref = value.strip()
    if not public_shelf_ref.startswith("/") or public_shelf_ref.startswith("//"):
        raise LaunchValidationError(
            f"artifact-factory source-pack batch request source pack '{source_pack_id}' has non-local public proof shelf {field_name}; "
            "artifact factory output refs must stay on the Chummer public proof shelf."
        )


def string_field(source_pack: dict[str, Any], field_name: str) -> str:
    value = source_pack.get(field_name)
    return value.strip() if isinstance(value, str) else ""


def receipt_ref_matches_prefix(evidence_refs: set[str], prefix: str) -> bool:
    return any(evidence_ref == prefix or evidence_ref.startswith(f"{prefix}:") for evidence_ref in evidence_refs)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    base_url = args.base_url.rstrip("/")
    if not base_url:
        raise SystemExit("artifact-factory base URL is required.")

    if args.recipes:
        response = load_recipe_catalog(base_url, args.token, args.public_host, args.forwarded_proto)
    else:
        recipe_catalog = load_recipe_catalog(base_url, args.token, args.public_host, args.forwarded_proto)
        payload = normalize_launch_payload(read_request_payload(args.request_file), recipe_catalog)
        url = f"{base_url}{DEFAULT_BATCH_PATH}"
        response = request_json(
            url,
            "POST",
            build_headers(args.token, args.public_host, args.forwarded_proto, include_json_body=True),
            payload=payload,
        )
        validate_batch_launch_response(response, recipe_catalog, payload)

    json.dump(response, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
