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

    return response


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
    expected_source_pack_ids = sorted(
        {
            source_pack["sourcePackId"].strip()
            for source_pack in normalized_payload["sourcePacks"]
            if isinstance(source_pack, dict) and isinstance(source_pack.get("sourcePackId"), str) and source_pack["sourcePackId"].strip()
        }
    )
    if source_pack_ids != expected_source_pack_ids:
        raise LaunchValidationError(
            "artifact-factory source-pack batch response sourcePackIds must match the launch request sourcePackIds."
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
    return False


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
