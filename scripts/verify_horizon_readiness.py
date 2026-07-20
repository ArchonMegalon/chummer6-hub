#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import re
import sys
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import materialize_horizon_readiness as materializer


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARTIFACT = ROOT / "_completion" / "nightly" / "HORIZON_READINESS.generated.json"
DEFAULT_MAX_AGE_SECONDS = 86_400
DEFAULT_ALLOWED_FUTURE_SKEW_SECONDS = 300

TOP_LEVEL_FIELDS = {
    "contract_name",
    "schema_version",
    "generated_at_utc",
    "generator",
    "status",
    "operational_readiness_claim_allowed",
    "readiness_derivation",
    "source_catalogs",
    "source_evidence",
    "catalog_coverage",
    "summary",
    "horizons",
    "capabilities",
}
GENERATOR_FIELDS = {"path", "sha256"}
READINESS_DERIVATION_FIELDS = {
    "catalog_driven_enumeration",
    "enabled_by_default_used",
    "declared_shipment_state_used",
    "runtime_probe_performed",
    "provider_call_performed",
    "quota_consumed",
    "unknown_records_fail_closed",
}
SOURCE_CATALOG_FIELDS = {"canonical_horizons", "artifact_capabilities"}
SOURCE_CATALOG_ENTRY_FIELDS = {"path", "sha256", "record_count"}
SOURCE_EVIDENCE_FIELDS = {
    "record_count",
    "present_count",
    "missing_count",
    "records",
}
SOURCE_EVIDENCE_RECORD_FIELDS = {"path", "state", "sha256"}
CATALOG_COVERAGE_FIELDS = {
    "canonical_horizon_count",
    "capability_horizon_count",
    "joined_horizon_count",
    "capability_count",
    "canonical_horizons_without_capabilities",
    "capability_horizons_not_canonical",
    "unknown_capability_ids",
    "all_current_capabilities_assessed",
}
SUMMARY_FIELDS = {"horizons", "capabilities", "source_evidence"}
STATUS_SUMMARY_FIELDS = {
    "source_status_counts",
    "runtime_status_counts",
    "governance_status_counts",
}
SOURCE_EVIDENCE_SUMMARY_FIELDS = {"present_count", "missing_count"}
HORIZON_FIELDS = {
    "horizon_id",
    "title",
    "canonical",
    "declared_status",
    "declared_current_state",
    "public_guide_enabled",
    "canon_doc",
    "capability_ids",
    "source_status",
    "runtime_status",
    "governance_status",
    "assessment_summary",
    "evidence_refs",
    "assessment_source",
    "declared_state_used_for_readiness",
}
CAPABILITY_FIELDS = {
    "horizon_id",
    "capability_id",
    "artifact_kind",
    "public_label",
    "capability_slot",
    "enabled_by_default",
    "requires_authentication",
    "public_visible",
    "quota_tracked",
    "orchestration_lane_declared",
    "orchestration_lane_expression",
    "source_status",
    "runtime_status",
    "governance_status",
    "assessment_summary",
    "evidence_refs",
    "assessment_source",
    "enabled_used_for_readiness",
}

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_UTC_TIMESTAMP = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$"
)


def read_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"artifact not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"artifact is not valid JSON: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"artifact must be a JSON object: {path}")
    return payload


def _exact_keys(
    issues: list[str],
    value: Any,
    fields: set[str],
    location: str,
) -> bool:
    if not isinstance(value, dict):
        issues.append(f"{location}:not_object")
        return False
    actual = set(value)
    issues.extend(f"{location}:missing_field:{field}" for field in sorted(fields - actual))
    issues.extend(f"{location}:unknown_field:{field}" for field in sorted(actual - fields))
    return True


def _is_count(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _validate_count(issues: list[str], value: Any, location: str) -> None:
    if not _is_count(value):
        issues.append(f"{location}:invalid_count")


def _validate_sha256(
    issues: list[str],
    value: Any,
    location: str,
    *,
    allow_none: bool = False,
) -> None:
    if value is None and allow_none:
        return
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        issues.append(f"{location}:invalid_sha256")


def _validate_portable_path(issues: list[str], value: Any, location: str) -> None:
    reason = materializer.portable_evidence_ref_error(value)
    if reason is not None:
        # Do not echo the value: a rejected path may itself contain a secret.
        issues.append(f"{location}:unsafe_path:{reason}")


def _validate_generated_at(
    issues: list[str],
    value: Any,
    *,
    max_age_seconds: int,
    allowed_future_skew_seconds: int,
    now_utc: datetime | None,
) -> None:
    if not isinstance(max_age_seconds, int) or isinstance(max_age_seconds, bool) or max_age_seconds <= 0:
        issues.append("freshness_policy_invalid:max_age_seconds")
        return
    if (
        not isinstance(allowed_future_skew_seconds, int)
        or isinstance(allowed_future_skew_seconds, bool)
        or allowed_future_skew_seconds < 0
    ):
        issues.append("freshness_policy_invalid:allowed_future_skew_seconds")
        return
    if not isinstance(value, str) or _UTC_TIMESTAMP.fullmatch(value) is None:
        issues.append("generated_at_utc_malformed")
        return
    try:
        generated = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        issues.append("generated_at_utc_malformed")
        return

    now = now_utc or datetime.now(UTC)
    if now.tzinfo is None or now.utcoffset() is None:
        issues.append("freshness_policy_invalid:now_utc")
        return
    now = now.astimezone(UTC)
    future_seconds = (generated - now).total_seconds()
    if future_seconds > allowed_future_skew_seconds:
        issues.append("generated_at_utc_future")
        return
    if (now - generated).total_seconds() > max_age_seconds:
        issues.append("generated_at_utc_stale")


def _duplicate_ids(records: Any, field: str) -> list[str]:
    if not isinstance(records, list):
        return []
    seen: set[str] = set()
    duplicates: set[str] = set()
    for record in records:
        if not isinstance(record, dict):
            continue
        value = record.get(field)
        if not isinstance(value, str) or not value:
            continue
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return sorted(duplicates)


def _records_by_id(records: Any, field: str) -> dict[str, dict[str, Any]]:
    if not isinstance(records, list):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        value = record.get(field)
        if isinstance(value, str) and value and value not in result:
            result[value] = record
    return result


def _compare_record_fields(
    issues: list[str],
    kind: str,
    record_id: str,
    actual: dict[str, Any],
    expected: dict[str, Any],
    fields: set[str],
) -> None:
    for field in sorted(fields):
        if actual.get(field) != expected.get(field):
            issues.append(f"{kind}:{record_id}:field_mismatch:{field}")


def _validate_evidence_refs(
    issues: list[str],
    record: dict[str, Any],
    location: str,
) -> set[str]:
    refs = record.get("evidence_refs")
    if not isinstance(refs, list):
        issues.append(f"{location}:evidence_refs_not_list")
        return set()
    result: set[str] = set()
    for index, ref in enumerate(refs):
        _validate_portable_path(issues, ref, f"{location}:evidence_ref:{index}")
        if not isinstance(ref, str) or not ref:
            issues.append(f"{location}:evidence_ref:{index}:not_nonempty_string")
            continue
        if ref in result:
            issues.append(f"{location}:duplicate_evidence_ref")
        result.add(ref)
    return result


def _validate_status_summary(
    issues: list[str],
    value: Any,
    location: str,
) -> None:
    if not _exact_keys(issues, value, STATUS_SUMMARY_FIELDS, location):
        return
    domains = {
        "source_status_counts": materializer.SOURCE_STATUSES,
        "runtime_status_counts": materializer.RUNTIME_STATUSES,
        "governance_status_counts": materializer.GOVERNANCE_STATUSES,
    }
    for field, statuses in domains.items():
        counts = value.get(field)
        if not _exact_keys(issues, counts, set(statuses), f"{location}:{field}"):
            continue
        for status in statuses:
            _validate_count(issues, counts.get(status), f"{location}:{field}:{status}")


def _validate_nested_schema(
    payload: dict[str, Any],
    issues: list[str],
) -> tuple[list[Any], list[Any], set[str]]:
    _exact_keys(issues, payload, TOP_LEVEL_FIELDS, "top_level")

    generator = payload.get("generator")
    if _exact_keys(issues, generator, GENERATOR_FIELDS, "generator"):
        _validate_portable_path(issues, generator.get("path"), "generator:path")
        _validate_sha256(issues, generator.get("sha256"), "generator:sha256")

    derivation = payload.get("readiness_derivation")
    if _exact_keys(
        issues,
        derivation,
        READINESS_DERIVATION_FIELDS,
        "readiness_derivation",
    ):
        for field in READINESS_DERIVATION_FIELDS:
            if not isinstance(derivation.get(field), bool):
                issues.append(f"readiness_derivation:{field}:not_boolean")

    catalogs = payload.get("source_catalogs")
    if _exact_keys(issues, catalogs, SOURCE_CATALOG_FIELDS, "source_catalogs"):
        for name in sorted(SOURCE_CATALOG_FIELDS):
            entry = catalogs.get(name)
            location = f"source_catalogs:{name}"
            if not _exact_keys(issues, entry, SOURCE_CATALOG_ENTRY_FIELDS, location):
                continue
            _validate_portable_path(issues, entry.get("path"), f"{location}:path")
            _validate_sha256(issues, entry.get("sha256"), f"{location}:sha256")
            _validate_count(issues, entry.get("record_count"), f"{location}:record_count")

    coverage = payload.get("catalog_coverage")
    if _exact_keys(
        issues,
        coverage,
        CATALOG_COVERAGE_FIELDS,
        "catalog_coverage",
    ):
        for field in (
            "canonical_horizon_count",
            "capability_horizon_count",
            "joined_horizon_count",
            "capability_count",
        ):
            _validate_count(issues, coverage.get(field), f"catalog_coverage:{field}")
        for field in (
            "canonical_horizons_without_capabilities",
            "capability_horizons_not_canonical",
            "unknown_capability_ids",
        ):
            value = coverage.get(field)
            if not isinstance(value, list) or not all(
                isinstance(item, str) and item for item in value
            ):
                issues.append(f"catalog_coverage:{field}:invalid_string_list")
        if not isinstance(coverage.get("all_current_capabilities_assessed"), bool):
            issues.append("catalog_coverage:all_current_capabilities_assessed:not_boolean")

    summary = payload.get("summary")
    if _exact_keys(issues, summary, SUMMARY_FIELDS, "summary"):
        _validate_status_summary(issues, summary.get("horizons"), "summary:horizons")
        _validate_status_summary(
            issues,
            summary.get("capabilities"),
            "summary:capabilities",
        )
        evidence_summary = summary.get("source_evidence")
        if _exact_keys(
            issues,
            evidence_summary,
            SOURCE_EVIDENCE_SUMMARY_FIELDS,
            "summary:source_evidence",
        ):
            for field in SOURCE_EVIDENCE_SUMMARY_FIELDS:
                _validate_count(
                    issues,
                    evidence_summary.get(field),
                    f"summary:source_evidence:{field}",
                )

    horizons_value = payload.get("horizons")
    capabilities_value = payload.get("capabilities")
    if not isinstance(horizons_value, list):
        issues.append("horizons_not_list")
        horizons: list[Any] = []
    else:
        horizons = horizons_value
    if not isinstance(capabilities_value, list):
        issues.append("capabilities_not_list")
        capabilities: list[Any] = []
    else:
        capabilities = capabilities_value

    all_evidence_refs: set[str] = set()
    for index, record in enumerate(horizons):
        location = f"horizon_row:{index}"
        if not isinstance(record, dict):
            issues.append(f"{location}:not_object")
            continue
        _exact_keys(issues, record, HORIZON_FIELDS, location)
        horizon_id = record.get("horizon_id")
        if not isinstance(horizon_id, str) or not horizon_id:
            issues.append(f"{location}:invalid_horizon_id")
        all_evidence_refs.update(_validate_evidence_refs(issues, record, location))

    for index, record in enumerate(capabilities):
        location = f"capability_row:{index}"
        if not isinstance(record, dict):
            issues.append(f"{location}:not_object")
            continue
        _exact_keys(issues, record, CAPABILITY_FIELDS, location)
        capability_id = record.get("capability_id")
        if not isinstance(capability_id, str) or not capability_id:
            issues.append(f"{location}:invalid_capability_id")
        all_evidence_refs.update(_validate_evidence_refs(issues, record, location))

    evidence = payload.get("source_evidence")
    inventory_paths: set[str] = set()
    if _exact_keys(issues, evidence, SOURCE_EVIDENCE_FIELDS, "source_evidence"):
        for field in ("record_count", "present_count", "missing_count"):
            _validate_count(issues, evidence.get(field), f"source_evidence:{field}")
        records = evidence.get("records")
        if not isinstance(records, list):
            issues.append("source_evidence:records:not_list")
        else:
            present_count = 0
            missing_count = 0
            for index, record in enumerate(records):
                location = f"source_evidence:record:{index}"
                if not isinstance(record, dict):
                    issues.append(f"{location}:not_object")
                    continue
                _exact_keys(issues, record, SOURCE_EVIDENCE_RECORD_FIELDS, location)
                path = record.get("path")
                _validate_portable_path(issues, path, f"{location}:path")
                if isinstance(path, str) and path:
                    if path in inventory_paths:
                        issues.append("source_evidence:duplicate_path")
                    inventory_paths.add(path)
                state = record.get("state")
                if state == "present":
                    present_count += 1
                    _validate_sha256(issues, record.get("sha256"), f"{location}:sha256")
                elif state == "missing":
                    missing_count += 1
                    if record.get("sha256") is not None:
                        issues.append(f"{location}:missing_state_has_digest")
                else:
                    issues.append(f"{location}:invalid_state")
                    _validate_sha256(
                        issues,
                        record.get("sha256"),
                        f"{location}:sha256",
                        allow_none=True,
                    )
            if evidence.get("record_count") != len(records):
                issues.append("source_evidence:record_count_mismatch")
            if evidence.get("present_count") != present_count:
                issues.append("source_evidence:present_count_mismatch")
            if evidence.get("missing_count") != missing_count:
                issues.append("source_evidence:missing_count_mismatch")

    if inventory_paths != all_evidence_refs:
        issues.append("source_evidence:evidence_refs_mismatch")
    return horizons, capabilities, all_evidence_refs


def verify_payload(
    payload: dict[str, Any],
    repo_root: Path,
    registry_path: Path,
    capability_service_path: Path,
    *,
    max_age_seconds: int = DEFAULT_MAX_AGE_SECONDS,
    allowed_future_skew_seconds: int = DEFAULT_ALLOWED_FUTURE_SKEW_SECONDS,
    now_utc: datetime | None = None,
) -> tuple[bool, list[str]]:
    issues: list[str] = []
    horizons, capabilities, _ = _validate_nested_schema(payload, issues)
    _validate_generated_at(
        issues,
        payload.get("generated_at_utc"),
        max_age_seconds=max_age_seconds,
        allowed_future_skew_seconds=allowed_future_skew_seconds,
        now_utc=now_utc,
    )

    if payload.get("contract_name") != materializer.CONTRACT_NAME:
        issues.append("contract_name_mismatch")
    if payload.get("schema_version") != materializer.SCHEMA_VERSION:
        issues.append("schema_version_mismatch")

    duplicate_horizons = _duplicate_ids(horizons, "horizon_id")
    duplicate_capabilities = _duplicate_ids(capabilities, "capability_id")
    issues.extend(f"duplicate_horizon:{item}" for item in duplicate_horizons)
    issues.extend(f"duplicate_capability:{item}" for item in duplicate_capabilities)

    derivation = payload.get("readiness_derivation")
    if isinstance(derivation, dict):
        if derivation.get("enabled_by_default_used") is not False:
            issues.append("enabled_by_default_used_for_readiness")
        if derivation.get("declared_shipment_state_used") is not False:
            issues.append("declared_shipment_state_used_for_readiness")
        if derivation.get("runtime_probe_performed") is not False:
            issues.append("unexpected_runtime_probe_claim")
        if derivation.get("provider_call_performed") is not False:
            issues.append("unexpected_provider_call_claim")
        if derivation.get("quota_consumed") is not False:
            issues.append("unexpected_quota_consumption_claim")
        if derivation.get("unknown_records_fail_closed") is not True:
            issues.append("unknown_records_do_not_fail_closed")

    try:
        expected = materializer.build_readiness(
            repo_root.resolve(),
            registry_path.resolve(),
            capability_service_path.resolve(),
            generated_at_utc=(
                payload.get("generated_at_utc")
                if isinstance(payload.get("generated_at_utc"), str)
                else "verification"
            ),
        )
    except (FileNotFoundError, ValueError) as exc:
        issues.append(f"source_catalog_error:{exc}")
        return False, issues

    actual_horizons = _records_by_id(horizons, "horizon_id")
    actual_capabilities = _records_by_id(capabilities, "capability_id")
    expected_horizons = _records_by_id(expected["horizons"], "horizon_id")
    expected_capabilities = _records_by_id(expected["capabilities"], "capability_id")

    missing_horizons = sorted(set(expected_horizons) - set(actual_horizons))
    extra_horizons = sorted(set(actual_horizons) - set(expected_horizons))
    missing_capabilities = sorted(set(expected_capabilities) - set(actual_capabilities))
    extra_capabilities = sorted(set(actual_capabilities) - set(expected_capabilities))
    issues.extend(f"missing_horizon:{item}" for item in missing_horizons)
    issues.extend(f"extra_horizon:{item}" for item in extra_horizons)
    issues.extend(f"missing_capability:{item}" for item in missing_capabilities)
    issues.extend(f"extra_capability:{item}" for item in extra_capabilities)

    for horizon_id in sorted(set(expected_horizons) & set(actual_horizons)):
        actual = actual_horizons[horizon_id]
        _compare_record_fields(
            issues,
            "horizon",
            horizon_id,
            actual,
            expected_horizons[horizon_id],
            HORIZON_FIELDS,
        )
        if actual.get("source_status") not in materializer.SOURCE_STATUSES:
            issues.append(f"horizon:{horizon_id}:invalid_source_status")
        if actual.get("runtime_status") not in materializer.RUNTIME_STATUSES:
            issues.append(f"horizon:{horizon_id}:invalid_runtime_status")
        if actual.get("governance_status") not in materializer.GOVERNANCE_STATUSES:
            issues.append(f"horizon:{horizon_id}:invalid_governance_status")

    for capability_id in sorted(set(expected_capabilities) & set(actual_capabilities)):
        actual = actual_capabilities[capability_id]
        _compare_record_fields(
            issues,
            "capability",
            capability_id,
            actual,
            expected_capabilities[capability_id],
            CAPABILITY_FIELDS,
        )
        if actual.get("source_status") not in materializer.SOURCE_STATUSES:
            issues.append(f"capability:{capability_id}:invalid_source_status")
        if actual.get("runtime_status") not in materializer.RUNTIME_STATUSES:
            issues.append(f"capability:{capability_id}:invalid_runtime_status")
        if actual.get("governance_status") not in materializer.GOVERNANCE_STATUSES:
            issues.append(f"capability:{capability_id}:invalid_governance_status")
        if actual.get("enabled_used_for_readiness") is not False:
            issues.append(f"capability:{capability_id}:enabled_used_for_readiness")
        if actual.get("orchestration_lane_declared") is True and actual.get(
            "governance_status"
        ) not in {"governance_blocked", "unverified"}:
            issues.append(f"capability:{capability_id}:governed_lane_not_fail_closed")

    for field in TOP_LEVEL_FIELDS - {"generated_at_utc", "contract_name", "schema_version"}:
        if payload.get(field) != expected.get(field):
            issues.append(f"top_level_field_mismatch:{field}")

    return not issues, issues


def verify_artifact(
    artifact_path: Path,
    repo_root: Path,
    *,
    registry_path: Path | None = None,
    capability_service_path: Path | None = None,
    max_age_seconds: int = DEFAULT_MAX_AGE_SECONDS,
    allowed_future_skew_seconds: int = DEFAULT_ALLOWED_FUTURE_SKEW_SECONDS,
    now_utc: datetime | None = None,
) -> tuple[bool, list[str]]:
    payload = read_json_object(artifact_path)
    repo_root = repo_root.resolve()
    return verify_payload(
        payload,
        repo_root,
        (
            registry_path
            or repo_root / ".codex-design/product/HORIZON_REGISTRY.yaml"
        ).resolve(),
        (
            capability_service_path
            or repo_root / "Chummer.Run.Api/Services/Community/HorizonCapabilityService.cs"
        ).resolve(),
        max_age_seconds=max_age_seconds,
        allowed_future_skew_seconds=allowed_future_skew_seconds,
        now_utc=now_utc,
    )


def source_working_claim_allowed(payload: dict[str, Any]) -> bool:
    horizons = payload.get("horizons")
    capabilities = payload.get("capabilities")
    coverage = payload.get("catalog_coverage")
    if (
        not isinstance(horizons, list)
        or not horizons
        or not isinstance(capabilities, list)
        or not capabilities
        or not isinstance(coverage, dict)
    ):
        return False
    records = horizons + capabilities
    horizon_ids = [
        record.get("horizon_id")
        for record in horizons
        if isinstance(record, dict)
    ]
    capability_ids = [
        record.get("capability_id")
        for record in capabilities
        if isinstance(record, dict)
    ]
    return (
        len(horizon_ids) == len(horizons) == coverage.get("joined_horizon_count")
        and len(capability_ids) == len(capabilities) == coverage.get("capability_count")
        and all(isinstance(item, str) and item for item in horizon_ids + capability_ids)
        and len(set(horizon_ids)) == len(horizon_ids)
        and len(set(capability_ids)) == len(capability_ids)
        and all(
            isinstance(record, dict)
            and record.get("source_status") == "working"
            and not str(record.get("assessment_source") or "").startswith("fail_closed_")
            for record in records
        )
        and coverage.get("all_current_capabilities_assessed") is True
        and coverage.get("unknown_capability_ids") == []
    )


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def _nonnegative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be zero or greater")
    return parsed


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify the catalog-driven horizon readiness artifact against current source."
    )
    parser.add_argument("--artifact", type=Path, default=DEFAULT_ARTIFACT)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--registry", type=Path)
    parser.add_argument("--capability-service", type=Path)
    parser.add_argument(
        "--max-age-seconds",
        type=_positive_int,
        default=DEFAULT_MAX_AGE_SECONDS,
        help="Maximum accepted artifact age (default: 86400 seconds).",
    )
    parser.add_argument(
        "--allowed-future-skew-seconds",
        type=_nonnegative_int,
        default=DEFAULT_ALLOWED_FUTURE_SKEW_SECONDS,
        help="Maximum accepted clock skew into the future (default: 300 seconds).",
    )
    parser.add_argument(
        "--require-source-working",
        action="store_true",
        help=(
            "Fail unless all catalog horizons and capabilities have working, explicit "
            "source assessments; runtime and governance blocks remain permitted."
        ),
    )
    parser.add_argument(
        "--require-operational-ready",
        action="store_true",
        help="Also fail if the structurally valid artifact does not allow an operational readiness claim.",
    )
    args = parser.parse_args()

    try:
        payload = read_json_object(args.artifact)
        ok, issues = verify_payload(
            payload,
            args.repo_root.resolve(),
            (
                args.registry
                or args.repo_root / ".codex-design/product/HORIZON_REGISTRY.yaml"
            ).resolve(),
            (
                args.capability_service
                or args.repo_root
                / "Chummer.Run.Api/Services/Community/HorizonCapabilityService.cs"
            ).resolve(),
            max_age_seconds=args.max_age_seconds,
            allowed_future_skew_seconds=args.allowed_future_skew_seconds,
        )
    except ValueError as exc:
        payload = {}
        ok = False
        issues = [str(exc)]

    source_working = source_working_claim_allowed(payload)
    if args.require_source_working and not source_working:
        issues.append("source_working_not_allowed")
        ok = False

    if args.require_operational_ready and payload.get(
        "operational_readiness_claim_allowed"
    ) is not True:
        issues.append("operational_readiness_not_allowed")
        ok = False

    print(
        json.dumps(
            {
                "artifact": args.artifact.resolve().as_posix(),
                "status": "pass" if ok else "fail",
                "max_age_seconds": args.max_age_seconds,
                "allowed_future_skew_seconds": args.allowed_future_skew_seconds,
                "source_working_claim_allowed": source_working,
                "operational_readiness_claim_allowed": payload.get(
                    "operational_readiness_claim_allowed", False
                ),
                "issues": issues,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
