#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


DEFAULT_REQUESTED_BY = "fleet.release"
DEFAULT_REQUIRED_FAMILIES = ("release",)
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
FAMILY_TO_SOURCE_KINDS = {
    "release": {"release", "release_evidence", "desktop_release", "install_receipt"},
    "fix": {"fix_receipt", "support_case", "install_receipt", "release"},
    "support": {"support_case", "crash_report", "install_receipt", "release"},
    "publication": {"publication", "creator_publication", "campaign_recap", "runtime_bundle"},
    "campaign_cold_open": {"campaign_primer", "campaign_pack", "campaign_cold_open_pack"},
    "mission_briefing": {"mission_pack", "mission_briefing", "mission_briefing_pack"},
}
SUPPORTED_FAMILIES = frozenset(FAMILY_TO_SOURCE_KINDS)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Materialize a recipe-backed artifact-factory source-pack batch request from promoted release bundles and approved sidecar packs."
    )
    parser.add_argument(
        "--release-manifest",
        help="Optional path to the promoted releases.json manifest. Required only when release source packs should be synthesized from a promoted bundle.",
    )
    parser.add_argument("--promotion-result", help="Optional path to the release upload response JSON.")
    parser.add_argument("--release-proof", help="Optional path to HUB_LOCAL_RELEASE_PROOF.generated.json.")
    parser.add_argument(
        "--source-pack-file",
        action="append",
        default=[],
        help="Optional JSON file containing additional approved source packs or a source-pack batch fragment.",
    )
    parser.add_argument("--requested-by", default=DEFAULT_REQUESTED_BY, help="RequestedBy token for the launch request.")
    parser.add_argument("--batch-id", help="Explicit batch id. Defaults to a stable value derived from the manifest.")
    parser.add_argument(
        "--required-family",
        action="append",
        default=[],
        help="Recipe family to require. Repeat for multiple families. Defaults to release.",
    )
    parser.add_argument(
        "--requested-format",
        action="append",
        default=[],
        help="Optional family=format1,format2 override. Repeat for multiple families.",
    )
    parser.add_argument("--audience", help="Optional audience token.")
    parser.add_argument("--locale", help="Optional locale token.")
    parser.add_argument("--output", default="-", help="Where to write the JSON request. Defaults to stdout.")
    return parser.parse_args(argv)


def read_json(path_value: str) -> Any:
    path = Path(path_value)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(f"artifact-factory source-pack materializer input missing: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"artifact-factory source-pack materializer input is not valid JSON: {path}: {exc}") from exc


def normalize_token(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise SystemExit(f"artifact-factory source-pack materializer {field_name} is required.")
    if not re.fullmatch(r"[A-Za-z0-9._-]+", normalized):
        raise SystemExit(
            f"artifact-factory source-pack materializer {field_name} '{value}' is unsafe; use stable token characters only."
        )
    return normalized


def normalize_metadata_token(value: str, field_name: str, *, allow_comma: bool) -> str:
    normalized = value.strip()
    if not normalized:
        raise SystemExit(f"artifact-factory source-pack materializer {field_name} is required.")

    pattern = r"[A-Za-z0-9._,-]+" if allow_comma else r"[A-Za-z0-9._-]+"
    if not re.fullmatch(pattern, normalized):
        raise SystemExit(
            f"artifact-factory source-pack materializer {field_name} '{value}' is unsafe; use stable token characters only."
        )

    return normalized


def normalize_family(value: str, field_name: str) -> str:
    family = normalize_token(value.replace("-", "_").lower(), field_name)
    if family not in SUPPORTED_FAMILIES:
        raise SystemExit(f"artifact-factory source-pack materializer {field_name} '{value}' is not supported.")
    return family


def stable_batch_id(seed: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", seed.strip()).strip("-").lower() or "release"
    return normalize_token(f"artifact-factory-{slug}", "batch-id")


def load_release_manifest(path_value: str) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    payload = read_json(path_value)
    if not isinstance(payload, dict):
        raise SystemExit("artifact-factory source-pack materializer release manifest must be a JSON object.")

    downloads = payload.get("downloads")
    if not isinstance(downloads, list) or not downloads:
        raise SystemExit("artifact-factory source-pack materializer release manifest must include downloads[].")

    downloads_by_id: dict[str, dict[str, Any]] = {}
    for item in downloads:
        if not isinstance(item, dict):
            continue
        artifact_id = str(item.get("id") or "").strip()
        if artifact_id:
            downloads_by_id[artifact_id] = item

    if not downloads_by_id:
        raise SystemExit("artifact-factory source-pack materializer release manifest has no downloadable artifact ids.")

    return payload, downloads_by_id


def promoted_artifact_ids(downloads_by_id: dict[str, dict[str, Any]], promotion_result_path: str | None) -> list[str]:
    if not promotion_result_path:
        return sorted(downloads_by_id)

    payload = read_json(promotion_result_path)
    if not isinstance(payload, dict):
        raise SystemExit("artifact-factory source-pack materializer promotion result must be a JSON object.")

    promoted_ids = [str(item).strip() for item in payload.get("promotedArtifactIds", []) or [] if str(item).strip()]
    if not promoted_ids:
        return sorted(downloads_by_id)

    missing_ids = [artifact_id for artifact_id in promoted_ids if artifact_id not in downloads_by_id]
    if missing_ids:
        raise SystemExit(
            "artifact-factory source-pack materializer promotion result refers to artifact ids not present in the release manifest: "
            + ", ".join(sorted(missing_ids))
        )

    return sorted(dict.fromkeys(promoted_ids))


def load_release_proof_routes(path_value: str | None) -> list[str]:
    if not path_value:
        return []

    payload = read_json(path_value)
    if not isinstance(payload, dict):
        return []

    routes = payload.get("proofRoutes") or payload.get("proof_routes") or []
    if not isinstance(routes, list):
        return []

    return sorted(
        dict.fromkeys(
            f"public-shelf:{route_text}"
            for route in routes
            if (route_text := str(route).strip()).startswith("/downloads/install/")
        )
    )


def build_release_source_pack(
    artifact_id: str,
    manifest: dict[str, Any],
    artifact: dict[str, Any],
    release_proof_routes: list[str],
) -> dict[str, Any]:
    version = str(manifest.get("version") or "unpublished").strip() or "unpublished"
    channel = str(manifest.get("channel") or "preview").strip() or "preview"
    public_install_ref = f"/downloads/install/{artifact_id}"

    source_pack_kind = str(artifact.get("kind") or "").strip().replace("-", "_").lower() or "desktop_release"
    if source_pack_kind not in {"release", "release_evidence", "desktop_release", "install_receipt"}:
        source_pack_kind = "desktop_release"

    evidence_refs = sorted(
        dict.fromkeys(
            [
                f"release:{version}",
                f"promotion:{channel}:{artifact_id}",
                f"public-shelf:{public_install_ref}",
            ]
            + [route for route in release_proof_routes if route.endswith(f"/{artifact_id}")]
        )
    )

    return {
        "sourcePackId": f"release-pack-{artifact_id}",
        "sourcePackKind": source_pack_kind,
        "approvalState": "approved",
        "provenanceRef": f"release-channel:{channel}:{version}:{artifact_id}",
        "evidenceRefs": evidence_refs,
        "releaseArtifactId": artifact_id,
        "publicShelfRef": public_install_ref,
    }


def load_sidecar_source_packs(path_value: str) -> tuple[list[dict[str, Any]], list[str], list[dict[str, Any]], str | None, str | None]:
    payload = read_json(path_value)
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)], [], [], None, None

    if not isinstance(payload, dict):
        raise SystemExit(
            f"artifact-factory source-pack materializer sidecar file must be a JSON object or array: {path_value}"
        )

    source_packs = [item for item in payload.get("sourcePacks", []) or [] if isinstance(item, dict)]
    required_families = [
        normalize_family(str(item), "required-family")
        for item in payload.get("requiredFamilies", []) or []
        if str(item).strip()
    ]

    requested_formats: list[dict[str, Any]] = []
    for item in payload.get("requestedFormats", []) or []:
        if not isinstance(item, dict):
            continue
        family = normalize_family(str(item.get("family") or ""), "requested-format-family")
        formats = [
            normalize_token(str(format_value).replace("-", "_").lower(), "requested-format")
            for format_value in item.get("formats", []) or []
            if str(format_value).strip()
        ]
        if formats:
            requested_formats.append({"family": family, "formats": formats})

    audience = str(payload.get("audience") or "").strip() or None
    locale = str(payload.get("locale") or "").strip() or None
    return source_packs, required_families, requested_formats, audience, locale


def parse_requested_formats(values: list[str]) -> list[dict[str, Any]]:
    requested_formats: list[dict[str, Any]] = []
    for value in values:
        raw = str(value).strip()
        if not raw:
            continue
        family, separator, formats = raw.partition("=")
        if not separator:
            raise SystemExit(
                f"artifact-factory source-pack materializer requested format '{value}' must use family=format1,format2."
            )
        format_tokens = [
            normalize_token(item.replace("-", "_").lower(), "requested-format")
            for item in formats.split(",")
            if item.strip()
        ]
        if not format_tokens:
            raise SystemExit(
                f"artifact-factory source-pack materializer requested format '{value}' must include at least one format."
            )
        requested_formats.append(
            {
                "family": normalize_family(family, "requested-format-family"),
                "formats": format_tokens,
            }
        )
    return requested_formats


def infer_required_families(source_packs: list[dict[str, Any]]) -> list[str]:
    source_pack_kinds = {
        str(source_pack.get("sourcePackKind") or "").strip().replace("-", "_").lower()
        for source_pack in source_packs
        if isinstance(source_pack, dict) and str(source_pack.get("sourcePackKind") or "").strip()
    }

    return sorted(
        family
        for family, allowed_source_kinds in FAMILY_TO_SOURCE_KINDS.items()
        if source_pack_kinds & allowed_source_kinds
    )


def validate_source_packs(source_packs: list[dict[str, Any]]) -> None:
    seen_source_pack_ids: set[str] = set()
    for source_pack in source_packs:
        raw_source_pack_id = str(source_pack.get("sourcePackId") or "").strip()
        reject_provider_specific_ref(raw_source_pack_id or "source-pack", raw_source_pack_id, "sourcePackId")
        source_pack_id = normalize_token(raw_source_pack_id, "sourcePackId")
        if source_pack_id in seen_source_pack_ids:
            raise SystemExit(
                f"artifact-factory source-pack materializer contains duplicate sourcePackId '{source_pack_id}'."
            )
        seen_source_pack_ids.add(source_pack_id)

        source_pack_kind = normalize_token(str(source_pack.get("sourcePackKind") or ""), "sourcePackKind")
        if source_pack_kind not in {kind for kinds in FAMILY_TO_SOURCE_KINDS.values() for kind in kinds}:
            raise SystemExit(
                f"artifact-factory source-pack materializer sourcePackKind '{source_pack_kind}' is not supported."
            )

        approval_state = str(source_pack.get("approvalState") or "").strip().lower()
        if approval_state != "approved":
            raise SystemExit(
                f"artifact-factory source-pack materializer source pack '{source_pack_id}' must already be approved."
            )

        provenance_ref = str(source_pack.get("provenanceRef") or "").strip()
        if not provenance_ref:
            raise SystemExit(
                f"artifact-factory source-pack materializer source pack '{source_pack_id}' must include provenanceRef."
            )
        reject_provider_specific_ref(source_pack_id, provenance_ref, "provenanceRef")

        public_shelf_ref = str(source_pack.get("publicShelfRef") or "").strip()
        if public_shelf_ref:
            reject_provider_specific_ref(source_pack_id, public_shelf_ref, "publicShelfRef")
            reject_non_local_public_shelf_ref(source_pack_id, public_shelf_ref, "publicShelfRef")
            reject_unsafe_public_shelf_ref(source_pack_id, public_shelf_ref, "publicShelfRef")

        evidence_refs = source_pack.get("evidenceRefs", []) or []
        if not isinstance(evidence_refs, list):
            raise SystemExit(
                f"artifact-factory source-pack materializer source pack '{source_pack_id}' evidenceRefs must be an array."
            )

        for evidence_ref in evidence_refs:
            if not isinstance(evidence_ref, str) or not evidence_ref.strip():
                continue

            normalized_evidence_ref = evidence_ref.strip()
            reject_provider_specific_ref(source_pack_id, normalized_evidence_ref, "evidenceRef")
            if normalized_evidence_ref.lower().startswith("public-shelf:"):
                public_shelf_evidence = normalized_evidence_ref.split(":", 1)[1].strip()
                reject_non_local_public_shelf_ref(source_pack_id, public_shelf_evidence, "evidenceRef")
                reject_unsafe_public_shelf_ref(source_pack_id, public_shelf_evidence, "evidenceRef")

        for field_name in ("releaseArtifactId", "supportCaseId", "publicationId", "campaignId", "missionId"):
            reject_unsafe_public_path_id(source_pack_id, str(source_pack.get(field_name) or "").strip(), field_name)
        if audience := str(source_pack.get("audience") or "").strip():
            normalize_metadata_token(audience, "audience", allow_comma=True)
        if locale := str(source_pack.get("locale") or "").strip():
            normalize_metadata_token(locale, "locale", allow_comma=False)


def validate_requested_formats(requested_formats: list[dict[str, Any]], required_families: list[str]) -> None:
    seen_families: set[str] = set()
    required_family_set = set(required_families)
    for requested_format in requested_formats:
        family = normalize_family(str(requested_format.get("family") or ""), "requested-format-family")
        if family in seen_families:
            raise SystemExit(
                f"artifact-factory source-pack materializer contains duplicate requested formats for family '{family}'."
            )
        seen_families.add(family)
        if family not in required_family_set:
            raise SystemExit(
                f"artifact-factory source-pack materializer requested formats for family '{family}' without requiring that family."
            )


def infer_campaign_metadata(
    source_packs: list[dict[str, Any]],
    required_families: list[str],
    audience: str | None,
    locale: str | None,
) -> tuple[str | None, str | None]:
    campaign_families = {"campaign_cold_open", "mission_briefing"} & set(required_families)
    if not campaign_families:
        return audience, locale

    relevant_packs = [
        source_pack
        for source_pack in source_packs
        if any(
            str(source_pack.get("sourcePackKind") or "").strip().replace("-", "_").lower() in FAMILY_TO_SOURCE_KINDS[family]
            for family in campaign_families
        )
    ]
    if not relevant_packs:
        return audience, locale

    inferred_audience = audience
    if not inferred_audience:
        audience_values = {
            normalize_metadata_token(str(source_pack.get("audience") or "").strip(), "audience", allow_comma=True)
            for source_pack in relevant_packs
            if str(source_pack.get("audience") or "").strip()
        }
        if len(audience_values) > 1:
            raise SystemExit(
                "artifact-factory source-pack materializer campaign and mission bundle requests require --audience or sidecar audience when approved packs disagree."
            )
        inferred_audience = next(iter(audience_values), None)

    inferred_locale = locale
    if not inferred_locale:
        locale_values = {
            normalize_metadata_token(str(source_pack.get("locale") or "").strip(), "locale", allow_comma=False)
            for source_pack in relevant_packs
            if str(source_pack.get("locale") or "").strip()
        }
        if len(locale_values) > 1:
            raise SystemExit(
                "artifact-factory source-pack materializer campaign and mission bundle requests require --locale or sidecar locale when approved packs disagree."
            )
        inferred_locale = next(iter(locale_values), None)

    return inferred_audience, inferred_locale


def source_pack_supports_family(
    source_pack: dict[str, Any],
    family: str,
    audience: str | None,
    locale: str | None,
) -> bool:
    source_pack_kind = str(source_pack.get("sourcePackKind") or "").strip().replace("-", "_").lower()
    if source_pack_kind not in FAMILY_TO_SOURCE_KINDS[family]:
        return False

    if family not in {"campaign_cold_open", "mission_briefing"}:
        return True

    pack_audience = str(source_pack.get("audience") or "").strip()
    pack_locale = str(source_pack.get("locale") or "").strip()
    if not audience or not locale or not pack_audience or not pack_locale:
        return False

    allowed_audiences = {item.strip().lower() for item in pack_audience.split(",") if item.strip()}
    requested_audiences = {item.strip().lower() for item in audience.split(",") if item.strip()}
    return requested_audiences.issubset(allowed_audiences) and pack_locale == locale


def validate_required_family_coverage(
    source_packs: list[dict[str, Any]],
    required_families: list[str],
    audience: str | None,
    locale: str | None,
) -> None:
    for family in required_families:
        if not any(source_pack_supports_family(source_pack, family, audience, locale) for source_pack in source_packs):
            if family in {"campaign_cold_open", "mission_briefing"}:
                raise SystemExit(
                    "artifact-factory source-pack materializer has no approved source packs for required family "
                    f"'{family}' matching audience '{audience or ''}' and locale '{locale or ''}'."
                )
            raise SystemExit(
                f"artifact-factory source-pack materializer has no approved source packs for required family '{family}'."
            )


def require_campaign_metadata(required_families: list[str], audience: str | None, locale: str | None) -> None:
    if not {"campaign_cold_open", "mission_briefing"} & set(required_families):
        return

    if not audience:
        raise SystemExit(
            "artifact-factory source-pack materializer campaign and mission bundle requests require --audience or sidecar audience."
        )

    if not locale:
        raise SystemExit(
            "artifact-factory source-pack materializer campaign and mission bundle requests require --locale or sidecar locale."
        )


def reject_provider_specific_ref(source_pack_id: str, value: str, field_name: str) -> None:
    normalized = value.strip()
    if not normalized:
        return

    if normalized.lower().startswith(("http://", "https://")) or (
        "://" in normalized and not is_external_public_shelf_evidence_ref(normalized, field_name)
    ):
        raise SystemExit(
            f"artifact-factory source-pack materializer source pack '{source_pack_id}' has external absolute URI {field_name}; "
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
        raise SystemExit(
            f"artifact-factory source-pack materializer source pack '{source_pack_id}' has provider-specific {field_name}; "
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
    start = 0
    while True:
        index = value.find(token, start)
        if index < 0:
            return False

        before_ok = index == 0 or not value[index - 1].isalnum()
        after_index = index + len(token)
        after_ok = after_index == len(value) or not value[after_index].isalnum()
        if before_ok and after_ok:
            return True

        start = index + 1


def reject_non_local_public_shelf_ref(source_pack_id: str, public_shelf_ref: str, field_name: str) -> None:
    if public_shelf_ref.startswith("/"):
        return

    raise SystemExit(
        f"artifact-factory source-pack materializer source pack '{source_pack_id}' has non-local public proof shelf {field_name}; "
        "public proof shelf refs must stay on stable first-party routes."
    )


def reject_unsafe_public_shelf_ref(source_pack_id: str, public_shelf_ref: str, field_name: str) -> None:
    if "?" in public_shelf_ref or "#" in public_shelf_ref:
        raise SystemExit(
            f"artifact-factory source-pack materializer source pack '{source_pack_id}' has unsafe public proof shelf {field_name}; "
            "public proof shelf refs must not contain query strings or fragments."
        )

    decoded_ref = Path(public_shelf_ref).as_posix()
    if "/../" in f"{decoded_ref}/" or "/./" in f"{decoded_ref}/":
        raise SystemExit(
            f"artifact-factory source-pack materializer source pack '{source_pack_id}' has unsafe public proof shelf {field_name}; "
            "public proof shelf refs must not contain traversal segments."
        )


def reject_unsafe_public_path_id(source_pack_id: str, value: str, field_name: str) -> None:
    if not value:
        return

    reject_provider_specific_ref(source_pack_id, value, field_name)
    normalize_token(value, field_name)


def write_output(path_value: str, payload: dict[str, Any]) -> None:
    serialized = json.dumps(payload, indent=2) + "\n"
    if path_value == "-":
        sys.stdout.write(serialized)
        return

    path = Path(path_value)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(serialized, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    manifest: dict[str, Any] = {}
    source_packs: list[dict[str, Any]] = []
    promoted_ids: list[str] = []
    if args.release_manifest:
        manifest, downloads_by_id = load_release_manifest(args.release_manifest)
        promoted_ids = promoted_artifact_ids(downloads_by_id, args.promotion_result)
        release_proof_routes = load_release_proof_routes(args.release_proof)
        source_packs.extend(
            build_release_source_pack(artifact_id, manifest, downloads_by_id[artifact_id], release_proof_routes)
            for artifact_id in promoted_ids
        )

    explicit_required_families = [
        normalize_family(value, "required-family")
        for value in args.required_family
        if str(value).strip()
    ]
    requested_formats = parse_requested_formats(args.requested_format)
    audience = (
        normalize_metadata_token(str(args.audience), "audience", allow_comma=True)
        if str(args.audience or "").strip()
        else None
    )
    locale = (
        normalize_metadata_token(str(args.locale), "locale", allow_comma=False)
        if str(args.locale or "").strip()
        else None
    )

    for source_pack_file in args.source_pack_file:
        packs, sidecar_families, sidecar_formats, sidecar_audience, sidecar_locale = load_sidecar_source_packs(source_pack_file)
        source_packs.extend(packs)
        explicit_required_families.extend(sidecar_families)
        requested_formats.extend(sidecar_formats)
        audience = audience or (
            normalize_metadata_token(sidecar_audience, "audience", allow_comma=True) if sidecar_audience else None
        )
        locale = locale or (
            normalize_metadata_token(sidecar_locale, "locale", allow_comma=False) if sidecar_locale else None
        )

    if not source_packs:
        raise SystemExit(
            "artifact-factory source-pack materializer requires --release-manifest or at least one --source-pack-file with approved source packs."
        )

    inferred_required_families = infer_required_families(source_packs)
    required_families = sorted(dict.fromkeys(explicit_required_families or inferred_required_families or DEFAULT_REQUIRED_FAMILIES))
    validate_source_packs(source_packs)
    audience, locale = infer_campaign_metadata(source_packs, required_families, audience, locale)
    require_campaign_metadata(required_families, audience, locale)
    validate_requested_formats(requested_formats, required_families)
    validate_required_family_coverage(source_packs, required_families, audience, locale)

    batch_seed = args.batch_id or str(manifest.get("version") or ",".join(promoted_ids))
    if not batch_seed.strip():
        source_pack_ids = sorted(
            normalize_token(str(source_pack.get("sourcePackId") or ""), "sourcePackId")
            for source_pack in source_packs
        )
        batch_seed = ",".join(source_pack_ids) or ",".join(required_families)

    payload: dict[str, Any] = {
        "batchId": stable_batch_id(batch_seed),
        "requestedBy": normalize_token(args.requested_by, "requested-by"),
        "requiredFamilies": sorted(dict.fromkeys(required_families or DEFAULT_REQUIRED_FAMILIES)),
        "sourcePacks": source_packs,
    }
    if requested_formats:
        payload["requestedFormats"] = requested_formats
    if audience:
        payload["audience"] = audience
    if locale:
        payload["locale"] = locale

    write_output(args.output, payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
