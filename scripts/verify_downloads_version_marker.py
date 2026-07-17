#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import hashlib
import json
import re
import socket
import sys
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen


SOURCE_FILES = [
    "Chummer.Run.Api/Views/PublicLanding/Downloads.cshtml",
    "Chummer.Run.Api/Views/PublicLanding/Status.cshtml",
    "Chummer.Run.Api/wwwroot/css/site.css",
    "tests/public/downloads-status.spec.ts",
]
CONTRACT_NAME = "chummer.downloads_version_marker.v1"
BOUND_CONTRACT_NAME = "chummer.downloads_version_marker.bound.v1"
RELEASE_CHANNEL_AUTHORITY_CONTRACT_NAME = "Chummer.Hub.Registry.Contracts"
RUN_SERVICES_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RELEASE_CHANNEL_RECEIPT = WORKSPACE_ROOT / "chummer-hub-registry" / ".codex-studio" / "published" / "RELEASE_CHANNEL.generated.json"
DEFAULT_PUBLIC_RELEASE_MANIFEST_RELATIVE = Path("Chummer.Portal/downloads/RELEASE_CHANNEL.generated.json")
RELEASE_CHANNEL_GOLD_SUPPORTABILITY_STATE = "gold_supported"
RELEASE_CHANNEL_PREVIEW_SUPPORTABILITY_STATE = "preview_supported"
RELEASE_CHANNEL_REVIEW_SUPPORTABILITY_STATE = "review_required"
RELEASE_CHANNEL_REVIEW_ROLLOUT_STATE = "public_release_review_required"
RELEASE_CHANNEL_CONSERVATIVE_PROOF_STATUSES = {"missing", "stale"}
RELEASE_CHANNEL_BOUND_PROOF_STATUSES = {"fresh", "missing", "stale"}
RELEASE_CHANNEL_POSITIVE_ROLLOUT_STATES = {
    "promoted_preview",
    "public_stable",
}
RELEASE_CHANNEL_BLOCKING_ROLLOUT_STATES = {
    "blocked",
    "coverage_incomplete",
    "desktop_polish_needed",
    "disabled",
    "public_release_review_required",
    "release_review_required",
    "revoked",
    "unpublished",
}
RELEASE_CHANNEL_RECOGNIZED_ROLLOUT_STATES = (
    RELEASE_CHANNEL_POSITIVE_ROLLOUT_STATES
    | RELEASE_CHANNEL_BLOCKING_ROLLOUT_STATES
)
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$", re.IGNORECASE)
RELEASE_CHANNEL_STABLE_CHANNELS = {"public_stable", "stable", "docker"}
VERSION_TEXT_PATTERN = re.compile(r"\bVersion\s+\S+", re.IGNORECASE)
STATUS_DECISION_HEADINGS = {
    "Preview downloads",
    "Stable downloads",
    "Downloads paused",
}
STALE_STATUS_DECISION_HEADINGS = {
    "Updated",
}
UNSAFE_NON_GOLD_RELEASE_COPY_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bchecks?\s+(?:are\s+)?clear\b", re.IGNORECASE), "checks are clear"),
    (re.compile(r"\bstatus\s+is\s+green\b", re.IGNORECASE), "status is green"),
    (re.compile(r"\bproof\s+is\s+green\b", re.IGNORECASE), "proof is green"),
    (re.compile(r"\bgold[-\s]?supported\b", re.IGNORECASE), "gold-supported"),
    (re.compile(r"\bno\s+blocking\s+release\s+caveat\b", re.IGNORECASE), "no blocking release caveat"),
)


def supportability_state_supported_for_channel(channel: str, supportability_state: str) -> bool:
    normalized_channel = (channel or "").lower()
    normalized_state = (supportability_state or "").lower()
    if normalized_channel in RELEASE_CHANNEL_STABLE_CHANNELS:
        return normalized_state == RELEASE_CHANNEL_GOLD_SUPPORTABILITY_STATE
    if normalized_channel == "preview":
        return normalized_state in {
            RELEASE_CHANNEL_GOLD_SUPPORTABILITY_STATE,
            RELEASE_CHANNEL_PREVIEW_SUPPORTABILITY_STATE,
        }
    return False


def require(condition: bool, failures: list[str], message: str) -> None:
    if not condition:
        failures.append(message)


def read_source(root: Path, relative_path: str) -> str:
    return (root / relative_path).read_text(encoding="utf-8")


def load_optional_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def load_sha256_bound_json(
    path: Path,
    expected_sha256: str,
) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    normalized_expected = str(expected_sha256 or "").strip().lower()
    binding = {
        "path": str(path),
        "expected_sha256": normalized_expected,
        "actual_sha256": "",
        "sha256_matches": False,
        "status": "fail",
    }
    failures: list[str] = []
    if SHA256_PATTERN.fullmatch(normalized_expected) is None:
        failures.append("release channel receipt expected SHA-256 must be exactly 64 hexadecimal characters")

    try:
        raw_payload = path.read_bytes()
    except OSError as exc:
        failures.append(f"release channel receipt could not be read: {path}: {exc}")
        return {}, binding, failures

    actual_sha256 = hashlib.sha256(raw_payload).hexdigest()
    sha256_matches = bool(
        SHA256_PATTERN.fullmatch(normalized_expected)
        and actual_sha256 == normalized_expected
    )
    binding.update(
        {
            "actual_sha256": actual_sha256,
            "sha256_matches": sha256_matches,
        }
    )
    if not sha256_matches and SHA256_PATTERN.fullmatch(normalized_expected):
        failures.append("release channel receipt SHA-256 does not match the explicitly selected digest")

    try:
        parsed = json.loads(raw_payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        failures.append(f"release channel receipt is not valid UTF-8 JSON: {exc}")
        return {}, binding, failures
    if not isinstance(parsed, dict):
        failures.append("release channel receipt is not a JSON object")
        return {}, binding, failures

    binding["status"] = "pass" if not failures else "fail"
    return parsed, binding, failures


def verify_source(root: Path) -> tuple[dict[str, Any], list[str]]:
    failures: list[str] = []
    downloads_view = read_source(root, SOURCE_FILES[0])
    status_view = read_source(root, SOURCE_FILES[1])
    css = read_source(root, SOURCE_FILES[2])
    spec = read_source(root, SOURCE_FILES[3])

    require("static string ManifestVersionText(PublicReleaseManifestDto manifest)" in downloads_view, failures, "Downloads view must define ManifestVersionText")
    require("!string.IsNullOrWhiteSpace(manifest.Version)" in downloads_view, failures, "Downloads page-level version marker must prefer manifest.Version")
    valued_marker = 'data-downloads-release-version="@ManifestVersionText(Model.Manifest)"'
    require(valued_marker in downloads_view, failures, "Downloads view must expose a valued data-downloads-release-version attribute")
    require("@ManifestVersionText(Model.Manifest)" in downloads_view, failures, "Downloads view must render ManifestVersionText(Model.Manifest)")
    require(valued_marker in status_view, failures, "Status view must expose a valued data-downloads-release-version attribute")
    require("@ManifestVersionText(Model.Manifest)" in status_view, failures, "Status view must render ManifestVersionText(Model.Manifest)")
    require("downloads-version" in downloads_view, failures, "Downloads view must style the version marker with downloads-version")
    require(".surface-downloads .downloads-version" in css, failures, "site.css must style the downloads version marker")
    require("overflow-wrap: anywhere" in css, failures, "downloads version marker must wrap long versions")
    require("downloads_version_text: downloadsVersionText" in spec, failures, "Playwright artifact must record downloads version text")
    require("status_redirect_version_text: statusVersionText" in spec, failures, "Playwright artifact must record redirected status version text")
    require("status_redirect_heading: statusHeadingText" in spec, failures, "Playwright artifact must record the /status heading text")
    require("status_redirect_heading_recognized: statusHeadingRecognized" in spec, failures, "Playwright artifact must record whether the /status heading is recognized")
    require("status_redirect_heading_expected: expectedStatusHeading" in spec, failures, "Playwright artifact must record the expected /status heading for the release posture")
    require("status_redirect_heading_matches_release_channel: statusHeadingMatchesReleaseChannel" in spec, failures, "Playwright artifact must record whether the /status heading matches release posture")
    require("status_redirect_heading_uses_generic_updated_copy: statusHeadingUsesGenericUpdatedCopy" in spec, failures, "Playwright artifact must record whether the /status heading still uses generic Updated copy")

    return {
        "mode": "source",
        "files": SOURCE_FILES,
        "marker_in_view": valued_marker in downloads_view,
        "status_marker_in_view": valued_marker in status_view,
        "manifest_version_marker_prefers_release_version": "!string.IsNullOrWhiteSpace(manifest.Version)" in downloads_view,
        "status_manifest_version_marker_prefers_release_version": "!string.IsNullOrWhiteSpace(manifest.Version)" in status_view,
        "status_uses_marker_contract": valued_marker in status_view and "@ManifestVersionText(Model.Manifest)" in status_view,
        "styled_marker": ".surface-downloads .downloads-version" in css,
        "playwright_records_version_text": "downloads_version_text: downloadsVersionText" in spec,
        "playwright_records_status_heading": "status_redirect_heading: statusHeadingText" in spec,
    }, failures


def fetch(base_url: str, path: str, timeout: float) -> tuple[int, dict[str, str], str]:
    url = urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
    request = Request(url, headers={"User-Agent": "ChummerDownloadsVersionProof/1.0"})
    try:
        with urlopen(request, timeout=timeout) as response:
            headers = {key.lower(): value for key, value in response.headers.items()}
            body = response.read().decode("utf-8", errors="replace")
            return response.status, headers, body
    except HTTPError as exc:
        headers = {key.lower(): value for key, value in exc.headers.items()}
        body = exc.read().decode("utf-8", errors="replace")
        return exc.code, headers, body
    except (TimeoutError, socket.timeout, URLError, OSError) as exc:
        raise RuntimeError(f"{base_url}{path}: {exc}") from exc


def release_text(payload: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = str(payload.get(key) or "").strip()
        if value:
            return value
    return ""


def release_alias_values(
    payload: dict[str, Any],
    *keys: str,
    lowercase: bool = False,
) -> set[str]:
    values = {
        str(payload.get(key) or "").strip()
        for key in keys
        if str(payload.get(key) or "").strip()
    }
    return {value.lower() for value in values} if lowercase else values


def is_timezone_aware_iso8601(value: str) -> bool:
    normalized = str(value or "").strip()
    if not normalized:
        return False
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def release_manifest_posture(payload: dict[str, Any]) -> dict[str, str]:
    public_trust_metrics = payload.get("publicTrustMetrics")
    public_trust_metrics = public_trust_metrics if isinstance(public_trust_metrics, dict) else {}
    proof_freshness = public_trust_metrics.get("proofFreshness")
    proof_freshness = proof_freshness if isinstance(proof_freshness, dict) else {}
    public_release_channel = public_trust_metrics.get("releaseChannel")
    public_release_channel = public_release_channel if isinstance(public_release_channel, dict) else {}

    registry_boundary_coverage = payload.get("registryBoundaryCoverage")
    registry_boundary_coverage = registry_boundary_coverage if isinstance(registry_boundary_coverage, dict) else {}
    registry_release_channel = registry_boundary_coverage.get("releaseChannel")
    registry_release_channel = registry_release_channel if isinstance(registry_release_channel, dict) else {}

    return {
        "published_at": release_text(payload, "publishedAt", "published_at"),
        "proof_freshness_status": release_text(proof_freshness, "status").lower(),
        "public_trust_supportability_state": release_text(
            public_release_channel,
            "supportabilityState",
            "supportability_state",
        ).lower(),
        "public_trust_rollout_state": release_text(
            public_release_channel,
            "rolloutState",
            "rollout_state",
        ).lower(),
        "registry_supportability_state": release_text(
            registry_release_channel,
            "supportabilityState",
            "supportability_state",
        ).lower(),
        "registry_rollout_state": release_text(
            registry_release_channel,
            "rolloutState",
            "rollout_state",
        ).lower(),
    }


def bound_release_manifest_authority_contract(
    payload: dict[str, Any],
    prefix: str,
    *,
    expected_contract_name: str = RELEASE_CHANNEL_AUTHORITY_CONTRACT_NAME,
) -> tuple[dict[str, Any], list[str]]:
    public_trust_metrics = payload.get("publicTrustMetrics")
    public_trust_metrics = public_trust_metrics if isinstance(public_trust_metrics, dict) else {}
    public_release_channel = public_trust_metrics.get("releaseChannel")
    public_release_channel = public_release_channel if isinstance(public_release_channel, dict) else {}
    registry_boundary_coverage = payload.get("registryBoundaryCoverage")
    registry_boundary_coverage = (
        registry_boundary_coverage if isinstance(registry_boundary_coverage, dict) else {}
    )
    registry_release_channel = registry_boundary_coverage.get("releaseChannel")
    registry_release_channel = registry_release_channel if isinstance(registry_release_channel, dict) else {}

    contract_names = release_alias_values(payload, "contractName", "contract_name")
    failures: list[str] = []
    contract_name = release_text(payload, "contractName", "contract_name")
    contract_name_matches_expected = bool(
        len(contract_names) == 1
        and next(iter(contract_names)) == expected_contract_name
    )
    if not contract_names:
        failures.append(
            f"{prefix} contractName is missing for SHA-256-bound verification"
        )
    elif len(contract_names) != 1:
        failures.append(
            f"{prefix} contractName aliases conflict for SHA-256-bound verification"
        )
    elif not contract_name_matches_expected:
        failures.append(
            f"{prefix} contractName is unsupported for SHA-256-bound verification"
        )

    alias_groups = (
        (payload, ("version", "releaseVersion", "release_version"), "version", False),
        (payload, ("channel", "channelId", "channel_id"), "channel", True),
        (payload, ("publishedAt", "published_at"), "publishedAt", False),
        (
            payload,
            ("supportabilityState", "supportability_state"),
            "supportabilityState",
            True,
        ),
        (payload, ("rolloutState", "rollout_state"), "rolloutState", True),
        (
            public_release_channel,
            ("supportabilityState", "supportability_state"),
            "publicTrustMetrics release-channel supportabilityState",
            True,
        ),
        (
            public_release_channel,
            ("rolloutState", "rollout_state"),
            "publicTrustMetrics release-channel rolloutState",
            True,
        ),
        (
            registry_release_channel,
            ("supportabilityState", "supportability_state"),
            "registryBoundaryCoverage release-channel supportabilityState",
            True,
        ),
        (
            registry_release_channel,
            ("rolloutState", "rollout_state"),
            "registryBoundaryCoverage release-channel rolloutState",
            True,
        ),
    )
    conflicting_aliases: list[str] = (
        ["contractName"] if len(contract_names) > 1 else []
    )
    for alias_payload, alias_keys, alias_label, lowercase in alias_groups:
        if len(release_alias_values(alias_payload, *alias_keys, lowercase=lowercase)) > 1:
            conflicting_aliases.append(alias_label)
            failures.append(
                f"{prefix} {alias_label} aliases conflict for SHA-256-bound verification"
            )

    return {
        "contract_name": contract_name,
        "contract_name_matches_expected": contract_name_matches_expected,
        "aliases_consistent": not conflicting_aliases,
        "conflicting_aliases": conflicting_aliases,
    }, failures


def release_manifest_rollout_vocabulary_failures(
    payload: dict[str, Any],
    prefix: str,
) -> list[str]:
    public_trust_metrics = payload.get("publicTrustMetrics")
    public_trust_metrics = public_trust_metrics if isinstance(public_trust_metrics, dict) else {}
    public_release_channel = public_trust_metrics.get("releaseChannel")
    public_release_channel = public_release_channel if isinstance(public_release_channel, dict) else {}
    registry_boundary_coverage = payload.get("registryBoundaryCoverage")
    registry_boundary_coverage = (
        registry_boundary_coverage if isinstance(registry_boundary_coverage, dict) else {}
    )
    registry_release_channel = registry_boundary_coverage.get("releaseChannel")
    registry_release_channel = registry_release_channel if isinstance(registry_release_channel, dict) else {}
    rollout_groups = (
        (payload, "rolloutState"),
        (public_release_channel, "publicTrustMetrics release-channel rolloutState"),
        (registry_release_channel, "registryBoundaryCoverage release-channel rolloutState"),
    )
    failures: list[str] = []
    for rollout_payload, rollout_label in rollout_groups:
        values = release_alias_values(
            rollout_payload,
            "rolloutState",
            "rollout_state",
            lowercase=True,
        )
        for value in sorted(values - RELEASE_CHANNEL_RECOGNIZED_ROLLOUT_STATES):
            failures.append(f"{prefix} {rollout_label} is unsupported: {value}")
    return failures


def conservative_rollout_floor(expected_rollout_state: str, effective_rollout_state: str) -> str:
    normalized = str(expected_rollout_state or "").strip().lower()
    if normalized in RELEASE_CHANNEL_BLOCKING_ROLLOUT_STATES:
        return normalized
    if normalized in RELEASE_CHANNEL_POSITIVE_ROLLOUT_STATES:
        effective = str(effective_rollout_state or "").strip().lower()
        return effective if effective in RELEASE_CHANNEL_RECOGNIZED_ROLLOUT_STATES else ""
    return ""


def served_posture_compatibility(
    manifest: dict[str, Any],
    expected: dict[str, Any],
    *,
    release_channel_receipt_sha256_bound: bool = False,
) -> dict[str, Any]:
    posture = release_manifest_posture(manifest)
    served_supportability_state = release_text(
        manifest,
        "supportabilityState",
        "supportability_state",
    ).lower()
    served_rollout_state = release_text(manifest, "rolloutState", "rollout_state").lower()
    expected_supportability_state = str(expected.get("supportability_state") or "").strip().lower()
    expected_rollout_state = str(expected.get("rollout_state") or "").strip().lower()
    expected_proof_freshness_status = str(
        expected.get("proof_freshness_status") or ""
    ).strip().lower()
    expected_public_trust_supportability_state = str(
        expected.get("public_trust_supportability_state") or ""
    ).strip().lower()
    expected_registry_supportability_state = str(
        expected.get("registry_supportability_state") or ""
    ).strip().lower()
    expected_public_trust_rollout_state = str(
        expected.get("public_trust_rollout_state") or ""
    ).strip().lower()
    expected_registry_rollout_state = str(
        expected.get("registry_rollout_state") or ""
    ).strip().lower()
    expected_internal_supportability_consistent = bool(
        expected_supportability_state
        and expected_supportability_state
        == expected_public_trust_supportability_state
        == expected_registry_supportability_state
    )
    expected_internal_rollout_consistent = bool(
        expected_rollout_state
        and expected_rollout_state
        == expected_public_trust_rollout_state
        == expected_registry_rollout_state
    )

    supportability_exact = (
        served_supportability_state == expected_supportability_state
        if expected_supportability_state
        else None
    )
    rollout_exact = (
        served_rollout_state == expected_rollout_state
        if expected_rollout_state
        else None
    )
    effective_review_rollout = conservative_rollout_floor(
        expected_rollout_state,
        RELEASE_CHANNEL_REVIEW_ROLLOUT_STATE,
    )
    expected_public_trust_rollout = conservative_rollout_floor(
        expected_public_trust_rollout_state,
        effective_review_rollout,
    )
    expected_registry_rollout = conservative_rollout_floor(
        expected_registry_rollout_state,
        effective_review_rollout,
    )
    conservative_floor_valid = bool(
        release_channel_receipt_sha256_bound
        and expected_supportability_state
        in {
            RELEASE_CHANNEL_GOLD_SUPPORTABILITY_STATE,
            RELEASE_CHANNEL_PREVIEW_SUPPORTABILITY_STATE,
            RELEASE_CHANNEL_REVIEW_SUPPORTABILITY_STATE,
        }
        and expected_proof_freshness_status in RELEASE_CHANNEL_CONSERVATIVE_PROOF_STATUSES
        and expected_internal_supportability_consistent
        and expected_internal_rollout_consistent
        and expected_rollout_state in RELEASE_CHANNEL_RECOGNIZED_ROLLOUT_STATES
        and expected_public_trust_rollout_state
        in RELEASE_CHANNEL_RECOGNIZED_ROLLOUT_STATES
        and expected_registry_rollout_state
        in RELEASE_CHANNEL_RECOGNIZED_ROLLOUT_STATES
        and posture["proof_freshness_status"] == expected_proof_freshness_status
        and served_supportability_state == RELEASE_CHANNEL_REVIEW_SUPPORTABILITY_STATE
        and posture["public_trust_supportability_state"]
        == RELEASE_CHANNEL_REVIEW_SUPPORTABILITY_STATE
        and posture["registry_supportability_state"]
        == RELEASE_CHANNEL_REVIEW_SUPPORTABILITY_STATE
        and served_rollout_state in RELEASE_CHANNEL_RECOGNIZED_ROLLOUT_STATES
        and posture["public_trust_rollout_state"]
        in RELEASE_CHANNEL_RECOGNIZED_ROLLOUT_STATES
        and posture["registry_rollout_state"]
        in RELEASE_CHANNEL_RECOGNIZED_ROLLOUT_STATES
        and served_rollout_state == effective_review_rollout
        and posture["public_trust_rollout_state"] == expected_public_trust_rollout
        and posture["registry_rollout_state"] == expected_registry_rollout
    )
    conservative_floor_applied = bool(
        conservative_floor_valid
        and (supportability_exact is False or rollout_exact is False)
    )
    return {
        **posture,
        "supportability_exact": supportability_exact,
        "rollout_exact": rollout_exact,
        "supportability_compatible": supportability_exact is not False or conservative_floor_valid,
        "rollout_compatible": rollout_exact is not False or conservative_floor_valid,
        "conservative_review_floor_valid": conservative_floor_valid,
        "conservative_review_floor_applied": conservative_floor_applied,
        "internal_supportability_consistent": (
            served_supportability_state
            == posture["public_trust_supportability_state"]
            == posture["registry_supportability_state"]
        ),
        "expected_internal_supportability_consistent": expected_internal_supportability_consistent,
        "expected_internal_rollout_consistent": expected_internal_rollout_consistent,
        "effective_review_rollout_state": effective_review_rollout,
    }


def release_manifest_copy_safety(manifest: dict[str, Any], prefix: str) -> tuple[dict[str, Any], list[str]]:
    supportability_state = release_text(manifest, "supportabilityState", "supportability_state").lower()
    channel = release_text(manifest, "channel", "channelId", "channel_id").lower()
    rollout_state = release_text(manifest, "rolloutState", "rollout_state").lower()
    supportability_summary = release_text(manifest, "supportabilitySummary", "supportability_summary")
    known_issue_summary = release_text(manifest, "knownIssueSummary", "known_issue_summary")
    fix_availability_summary = release_text(manifest, "fixAvailabilitySummary", "fix_availability_summary")
    combined_copy = " ".join(
        item
        for item in (supportability_summary, known_issue_summary, fix_availability_summary)
        if item
    )
    non_gold = supportability_state != RELEASE_CHANNEL_GOLD_SUPPORTABILITY_STATE
    matched_patterns = [
        label
        for pattern, label in UNSAFE_NON_GOLD_RELEASE_COPY_PATTERNS
        if pattern.search(combined_copy)
    ]
    has_preview_or_review_caveat = bool(
        re.search(r"\bpreview\b|\breview[-\s]?required\b|\bnot\s+yet\s+gold[-\s]?ready\b|\bcaveats?\b", combined_copy, re.IGNORECASE)
    )
    failures: list[str] = []
    if non_gold and matched_patterns:
        failures.append(f"{prefix} release manifest uses green/gold copy while supportabilityState is {supportability_state or 'missing'}")
    if channel == "preview" and non_gold and not has_preview_or_review_caveat:
        failures.append(f"{prefix} preview release manifest copy does not carry preview/review caveat")
    if rollout_state in RELEASE_CHANNEL_BLOCKING_ROLLOUT_STATES and not has_preview_or_review_caveat:
        failures.append(f"{prefix} release manifest copy does not explain blocking rollout state {rollout_state}")

    return {
        "supportability_summary": supportability_summary,
        "known_issue_summary": known_issue_summary,
        "fix_availability_summary": fix_availability_summary,
        "copy_safe": not failures,
        "unsafe_copy_markers": matched_patterns,
        "has_preview_or_review_caveat": has_preview_or_review_caveat,
    }, failures


def public_installer_available(payload: dict[str, Any]) -> bool:
    trust_metrics = payload.get("publicTrustMetrics")
    trust_metrics = trust_metrics if isinstance(trust_metrics, dict) else {}
    adoption_health = trust_metrics.get("adoptionHealth")
    adoption_health = adoption_health if isinstance(adoption_health, dict) else {}
    if "publicInstallCount" in adoption_health:
        try:
            return int(adoption_health.get("publicInstallCount") or 0) > 0
        except (TypeError, ValueError):
            return False

    coverage = payload.get("registryBoundaryCoverage")
    coverage = coverage if isinstance(coverage, dict) else {}
    entitlement = coverage.get("entitlement")
    entitlement = entitlement if isinstance(entitlement, dict) else {}
    if "openPublicSurfaceCount" in entitlement:
        try:
            return int(entitlement.get("openPublicSurfaceCount") or 0) > 0
        except (TypeError, ValueError):
            return False

    downloads = payload.get("downloads")
    if isinstance(downloads, list):
        return bool(downloads)

    artifacts = payload.get("artifacts")
    if isinstance(artifacts, list):
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                continue
            kind = release_text(artifact, "kind", "artifactKind").lower()
            if "installer" not in kind:
                continue
            access = release_text(
                artifact,
                "installAccessClass",
                "accessClass",
                "access",
            ).lower()
            if access and access not in {"open_public", "public", "guest"}:
                continue
            if release_text(artifact, "downloadUrl", "url", "installUrl"):
                return True
        return False

    # Older manifest contracts did not expose availability counters. Preserve their
    # established heading expectations until an explicit availability signal exists.
    return True


def expected_status_heading(
    expected_release_status: str,
    expected_release_version: str,
    expected_release_channel: str,
    expected_supportability_state: str,
    expected_rollout_state: str,
    expected_public_installer_available: bool | None = None,
) -> str | None:
    normalized_status = (expected_release_status or "").strip().lower()
    normalized_version = (expected_release_version or "").strip()
    normalized_channel = (expected_release_channel or "").strip().lower()
    normalized_supportability_state = (expected_supportability_state or "").strip().lower()
    normalized_rollout_state = (expected_rollout_state or "").strip().lower()

    if expected_public_installer_available is False:
        return "Downloads paused"

    if not any(
        (
            normalized_status,
            normalized_version,
            normalized_channel,
            normalized_supportability_state,
            normalized_rollout_state,
        )
    ):
        return None

    if normalized_status and normalized_status != "published":
        return "Downloads paused"

    if is_published_stable_release(
        normalized_status,
        normalized_channel,
        normalized_supportability_state,
        normalized_rollout_state,
    ):
        return "Stable downloads"

    if (
        normalized_channel == "preview"
        or normalized_rollout_state == "promoted_preview"
        or normalized_supportability_state == RELEASE_CHANNEL_PREVIEW_SUPPORTABILITY_STATE
        or normalized_channel in RELEASE_CHANNEL_STABLE_CHANNELS
        or normalized_rollout_state == "public_stable"
        or normalized_supportability_state == RELEASE_CHANNEL_GOLD_SUPPORTABILITY_STATE
        or normalized_version
    ):
        return "Preview downloads"

    return None


class VersionMarkerParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.has_marker = False
        self.marker_value: str | None = None
        self._capture_depth = 0
        self._text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._capture_depth > 0:
            self._capture_depth += 1
            return
        attr_map = {name.lower(): value for name, value in attrs}
        if "data-downloads-release-version" not in attr_map:
            return
        self.has_marker = True
        self.marker_value = attr_map.get("data-downloads-release-version")
        self._capture_depth = 1

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {name.lower(): value for name, value in attrs}
        if "data-downloads-release-version" in attr_map and not self.has_marker:
            self.has_marker = True
            self.marker_value = attr_map.get("data-downloads-release-version")

    def handle_endtag(self, tag: str) -> None:
        if self._capture_depth > 0:
            self._capture_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._capture_depth > 0:
            self._text_parts.append(data)

    @property
    def marker_text(self) -> str:
        return " ".join(part.strip() for part in self._text_parts if part.strip()).strip()


class VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.version_texts: list[str] = []
        self._hidden_stack: list[bool] = []
        self._version_capture_depth = 0
        self._current_version_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {name.lower(): value or "" for name, value in attrs}
        class_tokens = {
            token.strip().lower()
            for token in attr_map.get("class", "").split()
            if token.strip()
        }
        parent_hidden = self._hidden_stack[-1] if self._hidden_stack else False
        current_hidden = (
            tag.lower() in {"script", "style", "svg", "template"}
            or "hidden" in attr_map
            or attr_map.get("aria-hidden", "").lower() == "true"
            or "sr-only" in class_tokens
        )
        effective_hidden = parent_hidden or current_hidden
        self._hidden_stack.append(effective_hidden)

        if self._version_capture_depth > 0:
            self._version_capture_depth += 1
            return

        if not effective_hidden and "downloads-version" in class_tokens:
            self._version_capture_depth = 1
            self._current_version_parts = []

    def handle_endtag(self, tag: str) -> None:
        if self._version_capture_depth > 0:
            self._version_capture_depth -= 1
            if self._version_capture_depth == 0:
                text = " ".join(part.strip() for part in self._current_version_parts if part.strip()).strip()
                if text:
                    self.version_texts.append(text)
                self._current_version_parts = []

        if self._hidden_stack:
            self._hidden_stack.pop()

    def handle_data(self, data: str) -> None:
        hidden = self._hidden_stack[-1] if self._hidden_stack else False
        normalized = " ".join(html.unescape(data).split()).strip()
        if hidden or not normalized:
            return
        self.parts.append(normalized)
        if self._version_capture_depth > 0:
            self._current_version_parts.append(normalized)

    @property
    def text(self) -> str:
        return " ".join(self.parts)


def expected_visible_version_candidates(expected_release_version: str) -> list[str]:
    return expected_visible_version_candidates_for_posture(expected_release_version)


def is_published_stable_release(
    expected_release_status: str,
    expected_release_channel: str,
    expected_supportability_state: str,
    expected_rollout_state: str,
) -> bool:
    normalized_status = str(expected_release_status or "").strip().lower()
    normalized_channel = str(expected_release_channel or "").strip().lower()
    normalized_supportability_state = str(expected_supportability_state or "").strip().lower()
    normalized_rollout_state = str(expected_rollout_state or "").strip().lower()
    stable_lane_published = (
        normalized_channel in RELEASE_CHANNEL_STABLE_CHANNELS
        or normalized_rollout_state == "public_stable"
    )
    status_allows_stable_release = not normalized_status or normalized_status == "published"
    return (
        stable_lane_published
        and normalized_supportability_state == RELEASE_CHANNEL_GOLD_SUPPORTABILITY_STATE
        and status_allows_stable_release
    )


def expected_visible_version_candidates_for_posture(
    expected_release_version: str,
    expected_release_status: str = "",
    expected_release_channel: str = "",
    expected_supportability_state: str = "",
    expected_rollout_state: str = "",
) -> list[str]:
    normalized = str(expected_release_version or "").strip()
    if not normalized:
        return []

    posture_known = any(
        (
            str(expected_release_status or "").strip(),
            str(expected_release_channel or "").strip(),
            str(expected_supportability_state or "").strip(),
            str(expected_rollout_state or "").strip(),
        )
    )
    stable_release = is_published_stable_release(
        expected_release_status,
        expected_release_channel,
        expected_supportability_state,
        expected_rollout_state,
    )
    candidates: list[str] = [f"Version {normalized}"]
    if normalized.lower().startswith("run-") and len(normalized) >= 12:
        stamp = normalized[4:12]
        if stamp.isdigit():
            stable_label = f"Version {stamp[0:4]}.{stamp[4:6]}.{stamp[6:8]}"
            preview_label = f"{stable_label} (Preview)"
            candidates.insert(0, stable_label if stable_release else preview_label)
            if not posture_known:
                candidates.insert(1, preview_label)
                candidates.insert(2, stable_label)
        else:
            candidates.insert(0, "Version" if stable_release else "Version Preview")
            if not posture_known:
                candidates.insert(1, "Version")
                candidates.insert(2, "Version Preview")

    return list(dict.fromkeys(candidate for candidate in candidates if candidate))


def extract_visible_version_text(html_text: str) -> str | None:
    parser = VisibleTextParser()
    parser.feed(html_text)
    parser.close()

    for candidate in parser.version_texts:
        if candidate.startswith("Version "):
            return candidate

    for candidate in parser.parts:
        if candidate.startswith("Version "):
            return candidate

    match = re.search(r"\bVersion\s+[^\r\n<]+?(?:\s+\([^)]*\))?(?=$)", parser.text)
    if match is not None:
        return match.group(0).strip()

    return None


def extract_version_marker(html_text: str) -> dict[str, Any]:
    parser = VersionMarkerParser()
    parser.feed(html_text)
    parser.close()
    marker_value = html.unescape(parser.marker_value or "").strip()
    marker_text = html.unescape(parser.marker_text).strip()
    marker_version_match = VERSION_TEXT_PATTERN.search(marker_value)
    visible_version_text = extract_visible_version_text(html_text)
    marker_version_text = html.unescape(marker_version_match.group(0)).strip() if marker_version_match else None
    return {
        "has_marker": parser.has_marker,
        "marker_value": marker_value,
        "marker_version_text": marker_version_text,
        "visible_version_text": visible_version_text,
        "marker_text": marker_text,
    }


def extract_first_heading_text(html_text: str, tag_name: str = "h1") -> str:
    heading_match = re.search(
        rf"<{tag_name}\b[^>]*>(.*?)</{tag_name}>",
        html_text,
        re.IGNORECASE | re.DOTALL,
    )
    if heading_match is None:
        return ""

    heading_html = heading_match.group(1)
    heading_text = re.sub(r"<[^>]+>", " ", heading_html)
    return " ".join(html.unescape(heading_text).split())


def release_channel_expectations(
    release_channel: dict[str, Any],
    *,
    require_launch_supported: bool = True,
    require_published_at: bool = False,
    require_bound_contract: bool = False,
) -> tuple[dict[str, Any], list[str]]:
    contract_name = release_text(release_channel, "contractName", "contract_name")
    status = release_text(release_channel, "status").lower()
    version = release_text(release_channel, "version", "releaseVersion", "release_version")
    channel = release_text(release_channel, "channel", "channelId", "channel_id").lower()
    supportability_state = release_text(release_channel, "supportabilityState", "supportability_state").lower()
    rollout_state = release_text(release_channel, "rolloutState", "rollout_state").lower()
    posture = release_manifest_posture(release_channel)
    installer_available = public_installer_available(release_channel) if release_channel else None
    failures: list[str] = []

    if status != "published":
        failures.append("release channel status is not published")
    if not version:
        failures.append("release channel version is missing")
    if (require_published_at or require_bound_contract) and not posture["published_at"]:
        failures.append("release channel publishedAt is missing for SHA-256-bound verification")
    if require_bound_contract:
        _authority_contract, authority_failures = bound_release_manifest_authority_contract(
            release_channel,
            "release channel",
        )
        failures.extend(authority_failures)
        if posture["published_at"] and not is_timezone_aware_iso8601(posture["published_at"]):
            failures.append(
                "release channel publishedAt must be a timezone-aware ISO-8601 timestamp for SHA-256-bound verification"
            )
        if posture["proof_freshness_status"] not in RELEASE_CHANNEL_BOUND_PROOF_STATUSES:
            failures.append(
                "release channel proofFreshness.status must be fresh, stale, or explicit missing for SHA-256-bound verification"
            )
        if not supportability_state:
            failures.append(
                "release channel supportabilityState is missing for SHA-256-bound verification"
            )
        if not posture["public_trust_supportability_state"]:
            failures.append(
                "release channel publicTrustMetrics release-channel supportabilityState is missing for SHA-256-bound verification"
            )
        if not posture["registry_supportability_state"]:
            failures.append(
                "release channel registryBoundaryCoverage release-channel supportabilityState is missing for SHA-256-bound verification"
            )
        if not posture["public_trust_rollout_state"]:
            failures.append(
                "release channel publicTrustMetrics release-channel rolloutState is missing for SHA-256-bound verification"
            )
        if not posture["registry_rollout_state"]:
            failures.append(
                "release channel registryBoundaryCoverage release-channel rolloutState is missing for SHA-256-bound verification"
            )
        if (
            supportability_state
            and posture["public_trust_supportability_state"]
            and posture["public_trust_supportability_state"] != supportability_state
        ):
            failures.append(
                "release channel publicTrustMetrics release-channel supportabilityState contradicts the top-level SHA-256-bound posture"
            )
        if (
            supportability_state
            and posture["registry_supportability_state"]
            and posture["registry_supportability_state"] != supportability_state
        ):
            failures.append(
                "release channel registryBoundaryCoverage release-channel supportabilityState contradicts the top-level SHA-256-bound posture"
            )
        if (
            rollout_state
            and posture["public_trust_rollout_state"]
            and posture["public_trust_rollout_state"] != rollout_state
        ):
            failures.append(
                "release channel publicTrustMetrics release-channel rolloutState contradicts the top-level SHA-256-bound posture"
            )
        if (
            rollout_state
            and posture["registry_rollout_state"]
            and posture["registry_rollout_state"] != rollout_state
        ):
            failures.append(
                "release channel registryBoundaryCoverage release-channel rolloutState contradicts the top-level SHA-256-bound posture"
            )
    if not channel:
        failures.append("release channel channel is missing")
    elif channel not in RELEASE_CHANNEL_STABLE_CHANNELS | {"preview"}:
        failures.append(f"release channel channel is unsupported: {channel}")
    if (
        require_launch_supported
        and supportability_state != RELEASE_CHANNEL_GOLD_SUPPORTABILITY_STATE
    ):
        if not supportability_state_supported_for_channel(channel, supportability_state):
            failures.append("release channel supportabilityState is not launch-supported")
    if not rollout_state:
        failures.append("release channel rolloutState is missing")
    elif require_launch_supported and rollout_state in RELEASE_CHANNEL_BLOCKING_ROLLOUT_STATES:
        failures.append(f"release channel rolloutState is blocking: {rollout_state}")
    failures.extend(
        release_manifest_rollout_vocabulary_failures(release_channel, "release channel")
    )

    status_heading_expected = expected_status_heading(
        status,
        version,
        channel,
        supportability_state,
        rollout_state,
        installer_available,
    )
    return {
        "contract_name": contract_name,
        "status": status,
        "version": version,
        "channel": channel,
        "supportability_state": supportability_state,
        "rollout_state": rollout_state,
        **posture,
        "public_installer_available": installer_available,
        "status_heading_expected": status_heading_expected,
    }, failures


def verify_public_release_manifest(
    path: Path,
    expected: dict[str, Any],
    *,
    release_channel_receipt_sha256_bound: bool = False,
) -> tuple[dict[str, Any], list[str]]:
    failures: list[str] = []
    manifest = load_optional_json(path)
    exists = path.is_file()
    if not exists:
        failures.append(f"public release manifest is missing: {path}")

    expected_contract_name = str(expected.get("contract_name") or "").strip()
    public_authority_contract = {
        "contract_name": release_text(manifest, "contractName", "contract_name"),
        "contract_name_matches_expected": None,
        "aliases_consistent": None,
        "conflicting_aliases": [],
    }
    if release_channel_receipt_sha256_bound:
        public_authority_contract, authority_failures = (
            bound_release_manifest_authority_contract(
                manifest,
                "public release manifest",
                expected_contract_name=(
                    expected_contract_name or RELEASE_CHANNEL_AUTHORITY_CONTRACT_NAME
                ),
            )
        )
        failures.extend(authority_failures)
    failures.extend(
        release_manifest_rollout_vocabulary_failures(
            manifest,
            "public release manifest",
        )
    )

    public_status = release_text(manifest, "status").lower()
    public_version = release_text(manifest, "version", "releaseVersion", "release_version")
    public_channel = release_text(manifest, "channel", "channelId", "channel_id").lower()
    public_supportability_state = release_text(manifest, "supportabilityState", "supportability_state").lower()
    public_rollout_state = release_text(manifest, "rolloutState", "rollout_state").lower()
    public_posture = release_manifest_posture(manifest)

    expected_status = str(expected.get("status") or "").strip().lower()
    expected_version = str(expected.get("version") or "").strip()
    expected_channel = str(expected.get("channel") or "").strip().lower()
    expected_supportability_state = str(expected.get("supportability_state") or "").strip().lower()
    expected_rollout_state = str(expected.get("rollout_state") or "").strip().lower()
    expected_published_at = str(expected.get("published_at") or "").strip()
    expected_proof_freshness_status = str(
        expected.get("proof_freshness_status") or ""
    ).strip().lower()
    expected_public_trust_supportability_state = str(
        expected.get("public_trust_supportability_state") or ""
    ).strip().lower()
    expected_public_trust_rollout_state = str(
        expected.get("public_trust_rollout_state") or ""
    ).strip().lower()
    expected_registry_supportability_state = str(
        expected.get("registry_supportability_state") or ""
    ).strip().lower()
    expected_registry_rollout_state = str(
        expected.get("registry_rollout_state") or ""
    ).strip().lower()

    status_matches = public_status == expected_status if expected_status else None
    version_matches = public_version == expected_version if expected_version else None
    channel_matches = public_channel == expected_channel if expected_channel else None
    supportability_matches = (
        public_supportability_state == expected_supportability_state
        if expected_supportability_state
        else None
    )
    rollout_matches = public_rollout_state == expected_rollout_state if expected_rollout_state else None
    published_at_matches = (
        public_posture["published_at"] == expected_published_at
        if expected_published_at
        else None
    )
    proof_freshness_matches = (
        public_posture["proof_freshness_status"] == expected_proof_freshness_status
        if expected_proof_freshness_status
        else None
    )
    public_trust_supportability_matches = (
        public_posture["public_trust_supportability_state"]
        == expected_public_trust_supportability_state
        if expected_public_trust_supportability_state
        else None
    )
    public_trust_rollout_matches = (
        public_posture["public_trust_rollout_state"] == expected_public_trust_rollout_state
        if expected_public_trust_rollout_state
        else None
    )
    registry_supportability_matches = (
        public_posture["registry_supportability_state"]
        == expected_registry_supportability_state
        if expected_registry_supportability_state
        else None
    )
    registry_rollout_matches = (
        public_posture["registry_rollout_state"] == expected_registry_rollout_state
        if expected_registry_rollout_state
        else None
    )

    if status_matches is False:
        failures.append("public release manifest status does not match release channel")
    if version_matches is False:
        failures.append("public release manifest version does not match release channel")
    if channel_matches is False:
        failures.append("public release manifest channel does not match release channel")
    if supportability_matches is False:
        failures.append("public release manifest supportabilityState does not match release channel")
    if rollout_matches is False:
        failures.append("public release manifest rolloutState does not match release channel")
    if published_at_matches is False:
        failures.append("public release manifest publishedAt does not match release channel")
    if proof_freshness_matches is False:
        failures.append("public release manifest proofFreshness.status does not match release channel")
    if public_trust_supportability_matches is False:
        failures.append("public release manifest publicTrustMetrics release-channel supportabilityState does not match release channel")
    if public_trust_rollout_matches is False:
        failures.append("public release manifest publicTrustMetrics release-channel rolloutState does not match release channel")
    if registry_supportability_matches is False:
        failures.append("public release manifest registryBoundaryCoverage release-channel supportabilityState does not match release channel")
    if registry_rollout_matches is False:
        failures.append("public release manifest registryBoundaryCoverage release-channel rolloutState does not match release channel")
    copy_safety, copy_failures = release_manifest_copy_safety(manifest, "public")
    failures.extend(copy_failures)

    return {
        "mode": "public_release_manifest",
        "path": str(path),
        "exists": exists,
        "release_channel_receipt_sha256_bound": release_channel_receipt_sha256_bound,
        "expected_release_contract_name": expected_contract_name,
        "public_release_contract_name": public_authority_contract["contract_name"],
        "public_release_contract_name_matches_release_channel": public_authority_contract[
            "contract_name_matches_expected"
        ],
        "public_release_aliases_consistent": public_authority_contract[
            "aliases_consistent"
        ],
        "public_release_conflicting_aliases": public_authority_contract[
            "conflicting_aliases"
        ],
        "expected_release_status": expected_status,
        "expected_release_version": expected_version,
        "expected_release_channel": expected_channel,
        "expected_release_supportability_state": expected_supportability_state,
        "expected_release_rollout_state": expected_rollout_state,
        "expected_release_published_at": expected_published_at,
        "expected_release_proof_freshness_status": expected_proof_freshness_status,
        "public_release_status": public_status,
        "public_release_status_matches_release_channel": status_matches,
        "public_release_version": public_version,
        "public_release_version_matches_release_channel": version_matches,
        "public_release_channel": public_channel,
        "public_release_channel_matches_release_channel": channel_matches,
        "public_release_supportability_state": public_supportability_state,
        "public_release_supportability_matches_release_channel": supportability_matches,
        "public_release_rollout_state": public_rollout_state,
        "public_release_rollout_matches_release_channel": rollout_matches,
        "public_release_published_at": public_posture["published_at"],
        "public_release_published_at_matches_release_channel": published_at_matches,
        "public_release_proof_freshness_status": public_posture["proof_freshness_status"],
        "public_release_proof_freshness_matches_release_channel": proof_freshness_matches,
        "public_release_public_trust_supportability_state": public_posture["public_trust_supportability_state"],
        "public_release_public_trust_supportability_matches_release_channel": public_trust_supportability_matches,
        "public_release_public_trust_rollout_state": public_posture["public_trust_rollout_state"],
        "public_release_public_trust_rollout_matches_release_channel": public_trust_rollout_matches,
        "public_release_registry_supportability_state": public_posture["registry_supportability_state"],
        "public_release_registry_supportability_matches_release_channel": registry_supportability_matches,
        "public_release_registry_rollout_state": public_posture["registry_rollout_state"],
        "public_release_registry_rollout_matches_release_channel": registry_rollout_matches,
        "public_release_supportability_summary": copy_safety["supportability_summary"],
        "public_release_known_issue_summary": copy_safety["known_issue_summary"],
        "public_release_fix_availability_summary": copy_safety["fix_availability_summary"],
        "public_release_copy_safe": copy_safety["copy_safe"],
        "public_release_unsafe_copy_markers": copy_safety["unsafe_copy_markers"],
        "public_release_has_preview_or_review_caveat": copy_safety["has_preview_or_review_caveat"],
    }, failures


def verify_live(
    base_url: str,
    timeout: float,
    expected_release_status: str | None = None,
    expected_release_version: str | None = None,
    expected_release_channel: str | None = None,
    expected_supportability_state: str | None = None,
    expected_rollout_state: str | None = None,
    expected_public_installer_available: bool | None = None,
    expected_published_at: str | None = None,
    expected_proof_freshness_status: str | None = None,
    expected_public_trust_supportability_state: str | None = None,
    expected_public_trust_rollout_state: str | None = None,
    expected_registry_supportability_state: str | None = None,
    expected_registry_rollout_state: str | None = None,
    expected_contract_name: str | None = None,
    release_channel_receipt_sha256_bound: bool = False,
) -> tuple[dict[str, Any], list[str]]:
    failures: list[str] = []
    downloads_status, downloads_headers, downloads_html = fetch(base_url, "/downloads", timeout)
    status_status, status_headers, status_html = fetch(base_url, "/status", timeout)
    downloads_marker = extract_version_marker(downloads_html)
    status_marker = extract_version_marker(status_html)
    downloads_has_marker = downloads_marker["has_marker"]
    status_has_marker = status_marker["has_marker"]
    downloads_marker_value = str(downloads_marker["marker_value"] or "").strip()
    status_marker_value = str(status_marker["marker_value"] or "").strip()
    downloads_marker_version_text = downloads_marker["marker_version_text"]
    status_marker_version_text = status_marker["marker_version_text"]
    downloads_version_text = downloads_marker["visible_version_text"]
    status_visible_version_text = status_marker["visible_version_text"]
    status_version_text = status_visible_version_text or status_marker_version_text
    status_heading = extract_first_heading_text(status_html)
    status_heading_recognized = status_heading in STATUS_DECISION_HEADINGS
    status_heading_uses_generic_updated_copy = status_heading in STALE_STATUS_DECISION_HEADINGS

    require(downloads_status == 200, failures, f"/downloads expected 200, got {downloads_status}")
    require(status_status == 200, failures, f"/status expected 200, got {status_status}")
    require(downloads_has_marker, failures, "/downloads missing data-downloads-release-version")
    require(status_has_marker, failures, "/status missing data-downloads-release-version")
    if downloads_has_marker:
        require(bool(downloads_marker_value), failures, "/downloads data-downloads-release-version is empty")
        require(downloads_marker_version_text is not None, failures, "/downloads data-downloads-release-version is not a Version value")
    if status_has_marker:
        require(bool(status_marker_value), failures, "/status data-downloads-release-version is empty")
        require(status_marker_version_text is not None, failures, "/status data-downloads-release-version is not a Version value")
    require(downloads_version_text is not None, failures, "/downloads missing visible Version text")
    expected_release_version = str(expected_release_version or "").strip()
    expected_marker_version = f"Version {expected_release_version}" if expected_release_version else ""
    expected_visible_versions = expected_visible_version_candidates_for_posture(
        expected_release_version,
        expected_release_status or "",
        expected_release_channel or "",
        expected_supportability_state or "",
        expected_rollout_state or "",
    )
    normalized_expected_proof_freshness_status = str(
        expected_proof_freshness_status or ""
    ).strip().lower()
    if (
        release_channel_receipt_sha256_bound
        and normalized_expected_proof_freshness_status
        in RELEASE_CHANNEL_CONSERVATIVE_PROOF_STATUSES
    ):
        expected_visible_versions.extend(
            candidate
            for candidate in expected_visible_version_candidates_for_posture(
                expected_release_version,
                expected_release_status or "",
                expected_release_channel or "",
                RELEASE_CHANNEL_REVIEW_SUPPORTABILITY_STATE,
                conservative_rollout_floor(
                    expected_rollout_state or "",
                    RELEASE_CHANNEL_REVIEW_ROLLOUT_STATE,
                ),
            )
            if candidate not in expected_visible_versions
        )
    downloads_marker_matches_release_channel = (
        downloads_marker_version_text == expected_marker_version if expected_release_version else None
    )
    status_marker_matches_release_channel = (
        status_marker_version_text == expected_marker_version if expected_release_version else None
    )
    downloads_visible_matches_release_channel = (
        downloads_version_text in expected_visible_versions if expected_release_version else None
    )
    status_visible_matches_release_channel = (
        status_version_text in expected_visible_versions if expected_release_version else None
    )
    downloads_version_matches_release_channel = (
        downloads_visible_matches_release_channel is True
        and downloads_marker_matches_release_channel is True
        if expected_release_version
        else None
    )
    status_version_matches_release_channel = (
        (
            (status_visible_matches_release_channel is True if status_visible_version_text else True)
            and status_marker_matches_release_channel is True
        )
        if expected_release_version
        else None
    )
    if expected_release_version and not downloads_marker_matches_release_channel:
        failures.append("/downloads data-downloads-release-version does not match release channel")
    if expected_release_version and not status_marker_matches_release_channel:
        failures.append("/status data-downloads-release-version does not match release channel")
    if expected_release_version and not downloads_visible_matches_release_channel:
        failures.append("/downloads visible Version text does not match release channel")
    if expected_release_version and status_visible_version_text and not status_visible_matches_release_channel:
        failures.append("/status visible Version text does not match release channel")
    require(bool(status_heading), failures, "/status missing visible status heading")
    if status_heading_uses_generic_updated_copy:
        failures.append("/status still uses stale generic Updated heading")
    if not status_heading_recognized:
        failures.append("/status heading is not a recognized release-status decision heading")

    live_release_manifest: dict[str, Any] = {}
    release_manifest_http_status: int | None = None
    release_manifest_parse_error: str | None = None
    release_manifest_status_matches = None
    release_manifest_version_matches = None
    release_manifest_channel_matches = None
    release_manifest_supportability_matches = None
    release_manifest_rollout_matches = None
    release_manifest_published_at_matches = None
    release_manifest_proof_freshness_matches = None
    release_manifest_public_trust_supportability_matches = None
    release_manifest_public_trust_rollout_matches = None
    release_manifest_registry_supportability_matches = None
    release_manifest_registry_rollout_matches = None
    release_manifest_supportability_compatible = None
    release_manifest_rollout_compatible = None
    release_manifest_conservative_review_floor_applied = False
    release_manifest_internal_supportability_consistent = None
    release_manifest_public_installer_available: bool | None = None
    live_authority_contract = {
        "contract_name": "",
        "contract_name_matches_expected": None,
        "aliases_consistent": None,
        "conflicting_aliases": [],
    }
    expected_contract_name = str(expected_contract_name or "").strip()
    expected_release_status = str(expected_release_status or "").strip().lower()
    expected_release_channel = str(expected_release_channel or "").strip().lower()
    expected_supportability_state = str(expected_supportability_state or "").strip().lower()
    expected_rollout_state = str(expected_rollout_state or "").strip().lower()
    expected_published_at = str(expected_published_at or "").strip()
    expected_proof_freshness_status = normalized_expected_proof_freshness_status
    expected_public_trust_supportability_state = str(
        expected_public_trust_supportability_state or ""
    ).strip().lower()
    expected_public_trust_rollout_state = str(
        expected_public_trust_rollout_state or ""
    ).strip().lower()
    expected_registry_supportability_state = str(
        expected_registry_supportability_state or ""
    ).strip().lower()
    expected_registry_rollout_state = str(
        expected_registry_rollout_state or ""
    ).strip().lower()
    should_check_release_manifest = bool(
        expected_release_status
        or expected_release_version
        or expected_release_channel
        or expected_supportability_state
        or expected_rollout_state
        or expected_published_at
        or expected_proof_freshness_status
        or expected_public_trust_supportability_state
        or expected_public_trust_rollout_state
        or expected_registry_supportability_state
        or expected_registry_rollout_state
        or expected_contract_name
        or expected_public_installer_available is not None
    )
    if should_check_release_manifest:
        release_manifest_http_status, _release_headers, release_body = fetch(base_url, "/downloads/RELEASE_CHANNEL.generated.json", timeout)
        require(
            release_manifest_http_status == 200,
            failures,
            f"/downloads/RELEASE_CHANNEL.generated.json expected 200, got {release_manifest_http_status}",
        )
        try:
            parsed_manifest = json.loads(release_body)
            if isinstance(parsed_manifest, dict):
                live_release_manifest = parsed_manifest
            else:
                release_manifest_parse_error = "release manifest is not a JSON object"
        except json.JSONDecodeError as exc:
            release_manifest_parse_error = str(exc)
        if release_manifest_parse_error:
            failures.append(f"/downloads/RELEASE_CHANNEL.generated.json parse failed: {release_manifest_parse_error}")

        live_release_status = release_text(live_release_manifest, "status").lower()
        live_release_version = release_text(live_release_manifest, "version")
        live_release_channel = release_text(live_release_manifest, "channel", "channelId", "channel_id").lower()
        live_supportability_state = release_text(live_release_manifest, "supportabilityState", "supportability_state").lower()
        live_rollout_state = release_text(live_release_manifest, "rolloutState", "rollout_state").lower()
        live_posture = release_manifest_posture(live_release_manifest)
        if release_channel_receipt_sha256_bound:
            live_authority_contract, authority_failures = (
                bound_release_manifest_authority_contract(
                    live_release_manifest,
                    "/downloads RELEASE_CHANNEL",
                    expected_contract_name=(
                        expected_contract_name
                        or RELEASE_CHANNEL_AUTHORITY_CONTRACT_NAME
                    ),
                )
            )
            failures.extend(authority_failures)
        failures.extend(
            release_manifest_rollout_vocabulary_failures(
                live_release_manifest,
                "/downloads RELEASE_CHANNEL",
            )
        )
        compatibility = served_posture_compatibility(
            live_release_manifest,
            {
                "supportability_state": expected_supportability_state,
                "rollout_state": expected_rollout_state,
                "proof_freshness_status": expected_proof_freshness_status,
                "public_trust_supportability_state": expected_public_trust_supportability_state,
                "public_trust_rollout_state": expected_public_trust_rollout_state,
                "registry_supportability_state": expected_registry_supportability_state,
                "registry_rollout_state": expected_registry_rollout_state,
            },
            release_channel_receipt_sha256_bound=release_channel_receipt_sha256_bound,
        )
        release_manifest_supportability_compatible = compatibility["supportability_compatible"]
        release_manifest_rollout_compatible = compatibility["rollout_compatible"]
        release_manifest_conservative_review_floor_applied = compatibility[
            "conservative_review_floor_applied"
        ]
        release_manifest_internal_supportability_consistent = compatibility[
            "internal_supportability_consistent"
        ]
        if live_release_manifest:
            release_manifest_public_installer_available = public_installer_available(live_release_manifest)
        if expected_release_status:
            release_manifest_status_matches = live_release_status == expected_release_status
            if not release_manifest_status_matches:
                failures.append("/downloads RELEASE_CHANNEL status does not match release channel")
        if expected_release_version:
            release_manifest_version_matches = live_release_version == expected_release_version
            if not release_manifest_version_matches:
                failures.append("/downloads RELEASE_CHANNEL version does not match release channel")
        if expected_release_channel:
            release_manifest_channel_matches = live_release_channel == expected_release_channel
            if not release_manifest_channel_matches:
                failures.append("/downloads RELEASE_CHANNEL channel does not match release channel")
        if expected_supportability_state:
            release_manifest_supportability_matches = live_supportability_state == expected_supportability_state
            if not release_manifest_supportability_compatible:
                failures.append("/downloads RELEASE_CHANNEL supportabilityState does not match release channel")
        if expected_rollout_state:
            release_manifest_rollout_matches = live_rollout_state == expected_rollout_state
            if not release_manifest_rollout_compatible:
                failures.append("/downloads RELEASE_CHANNEL rolloutState does not match release channel")
        if expected_published_at:
            release_manifest_published_at_matches = live_posture["published_at"] == expected_published_at
            if not release_manifest_published_at_matches:
                failures.append("/downloads RELEASE_CHANNEL publishedAt does not match release channel")
        if expected_proof_freshness_status:
            release_manifest_proof_freshness_matches = (
                live_posture["proof_freshness_status"] == expected_proof_freshness_status
            )
            if not release_manifest_proof_freshness_matches:
                failures.append("/downloads RELEASE_CHANNEL proofFreshness.status does not match release channel")
        if expected_public_trust_supportability_state:
            release_manifest_public_trust_supportability_matches = (
                live_posture["public_trust_supportability_state"]
                == expected_public_trust_supportability_state
            )
            if (
                not release_manifest_public_trust_supportability_matches
                and not compatibility["conservative_review_floor_valid"]
            ):
                failures.append("/downloads RELEASE_CHANNEL publicTrustMetrics release-channel supportabilityState does not match release channel")
        if expected_public_trust_rollout_state:
            release_manifest_public_trust_rollout_matches = (
                live_posture["public_trust_rollout_state"]
                == expected_public_trust_rollout_state
            )
            if (
                not release_manifest_public_trust_rollout_matches
                and not compatibility["conservative_review_floor_valid"]
            ):
                failures.append("/downloads RELEASE_CHANNEL publicTrustMetrics release-channel rolloutState does not match release channel")
        if expected_registry_supportability_state:
            release_manifest_registry_supportability_matches = (
                live_posture["registry_supportability_state"]
                == expected_registry_supportability_state
            )
            if (
                not release_manifest_registry_supportability_matches
                and not compatibility["conservative_review_floor_valid"]
            ):
                failures.append("/downloads RELEASE_CHANNEL registryBoundaryCoverage release-channel supportabilityState does not match release channel")
        if expected_registry_rollout_state:
            release_manifest_registry_rollout_matches = (
                live_posture["registry_rollout_state"] == expected_registry_rollout_state
            )
            if (
                not release_manifest_registry_rollout_matches
                and not compatibility["conservative_review_floor_valid"]
            ):
                failures.append("/downloads RELEASE_CHANNEL registryBoundaryCoverage release-channel rolloutState does not match release channel")
        live_copy_safety, live_copy_failures = release_manifest_copy_safety(live_release_manifest, "live")
        failures.extend(f"/downloads RELEASE_CHANNEL {failure}" for failure in live_copy_failures)
    else:
        live_release_status = ""
        live_release_version = ""
        live_release_channel = ""
        live_supportability_state = ""
        live_rollout_state = ""
        live_posture = release_manifest_posture({})
        live_copy_safety = {
            "supportability_summary": "",
            "known_issue_summary": "",
            "fix_availability_summary": "",
            "copy_safe": None,
            "unsafe_copy_markers": [],
            "has_preview_or_review_caveat": None,
        }

    if live_release_manifest and release_manifest_parse_error is None:
        status_heading_expectation_source = "live_release_manifest"
        expected_status_decision_heading = expected_status_heading(
            live_release_status,
            live_release_version,
            live_release_channel,
            live_supportability_state,
            live_rollout_state,
            release_manifest_public_installer_available,
        )
    else:
        status_heading_expectation_source = (
            "release_channel_receipt"
            if any(
                (
                    expected_release_status,
                    expected_release_version,
                    expected_release_channel,
                    expected_supportability_state,
                    expected_rollout_state,
                    expected_public_installer_available is not None,
                )
            )
            else None
        )
        expected_status_decision_heading = expected_status_heading(
            expected_release_status or "",
            expected_release_version or "",
            expected_release_channel or "",
            expected_supportability_state or "",
            expected_rollout_state or "",
            expected_public_installer_available,
        )
    status_heading_matches_release_channel = (
        status_heading == expected_status_decision_heading if expected_status_decision_heading else None
    )
    if expected_status_decision_heading and not status_heading_matches_release_channel:
        failures.append(
            f"/status heading does not match served release posture (expected {expected_status_decision_heading})"
        )

    return {
        "mode": "live",
        "base_url": base_url.rstrip("/"),
        "expected_release_status": expected_release_status,
        "expected_release_version": expected_release_version,
        "expected_release_channel": expected_release_channel,
        "expected_release_contract_name": expected_contract_name,
        "expected_public_installer_available": expected_public_installer_available,
        "visible_version_matches_release_channel": downloads_version_matches_release_channel,
        "status_redirect_version_matches_release_channel": status_version_matches_release_channel,
        "expected_release_supportability_state": expected_supportability_state,
        "expected_release_rollout_state": expected_rollout_state,
        "expected_release_published_at": expected_published_at,
        "expected_release_proof_freshness_status": expected_proof_freshness_status,
        "release_manifest_http_status": release_manifest_http_status,
        "release_channel_receipt_sha256_bound": release_channel_receipt_sha256_bound,
        "release_manifest_contract_name": live_authority_contract["contract_name"],
        "release_manifest_contract_name_matches_release_channel": live_authority_contract[
            "contract_name_matches_expected"
        ],
        "release_manifest_aliases_consistent": live_authority_contract[
            "aliases_consistent"
        ],
        "release_manifest_conflicting_aliases": live_authority_contract[
            "conflicting_aliases"
        ],
        "release_manifest_status": live_release_status,
        "release_manifest_status_matches_release_channel": release_manifest_status_matches,
        "release_manifest_version": live_release_version,
        "release_manifest_version_matches_release_channel": release_manifest_version_matches,
        "release_manifest_channel": live_release_channel,
        "release_manifest_channel_matches_release_channel": release_manifest_channel_matches,
        "release_manifest_supportability_state": live_supportability_state,
        "release_manifest_supportability_matches_release_channel": release_manifest_supportability_matches,
        "release_manifest_supportability_compatible_with_release_channel": release_manifest_supportability_compatible,
        "release_manifest_rollout_state": live_rollout_state,
        "release_manifest_rollout_matches_release_channel": release_manifest_rollout_matches,
        "release_manifest_rollout_compatible_with_release_channel": release_manifest_rollout_compatible,
        "release_manifest_published_at": live_posture["published_at"],
        "release_manifest_published_at_matches_release_channel": release_manifest_published_at_matches,
        "release_manifest_proof_freshness_status": live_posture["proof_freshness_status"],
        "release_manifest_proof_freshness_matches_release_channel": release_manifest_proof_freshness_matches,
        "release_manifest_public_trust_supportability_state": live_posture["public_trust_supportability_state"],
        "release_manifest_public_trust_supportability_matches_release_channel": release_manifest_public_trust_supportability_matches,
        "release_manifest_public_trust_rollout_state": live_posture["public_trust_rollout_state"],
        "release_manifest_public_trust_rollout_matches_release_channel": release_manifest_public_trust_rollout_matches,
        "release_manifest_registry_supportability_state": live_posture["registry_supportability_state"],
        "release_manifest_registry_supportability_matches_release_channel": release_manifest_registry_supportability_matches,
        "release_manifest_registry_rollout_state": live_posture["registry_rollout_state"],
        "release_manifest_registry_rollout_matches_release_channel": release_manifest_registry_rollout_matches,
        "release_manifest_conservative_review_floor_applied": release_manifest_conservative_review_floor_applied,
        "release_manifest_internal_supportability_consistent": release_manifest_internal_supportability_consistent,
        "release_manifest_public_installer_available": release_manifest_public_installer_available,
        "release_manifest_parse_error": release_manifest_parse_error,
        "release_manifest_supportability_summary": live_copy_safety["supportability_summary"],
        "release_manifest_known_issue_summary": live_copy_safety["known_issue_summary"],
        "release_manifest_fix_availability_summary": live_copy_safety["fix_availability_summary"],
        "release_manifest_copy_safe": live_copy_safety["copy_safe"],
        "release_manifest_unsafe_copy_markers": live_copy_safety["unsafe_copy_markers"],
        "release_manifest_has_preview_or_review_caveat": live_copy_safety["has_preview_or_review_caveat"],
        "downloads_status": downloads_status,
        "status_status": status_status,
        "downloads_content_type": downloads_headers.get("content-type"),
        "status_content_type": status_headers.get("content-type"),
        "downloads_marker": downloads_has_marker,
        "status_redirect_marker": status_has_marker,
        "downloads_version_marker_value": downloads_marker_value,
        "status_redirect_version_marker_value": status_marker_value,
        "downloads_version_marker_matches_release_channel": downloads_marker_matches_release_channel,
        "status_redirect_version_marker_matches_release_channel": status_marker_matches_release_channel,
        "status_redirect_heading": status_heading,
        "status_redirect_heading_recognized": status_heading_recognized,
        "status_redirect_heading_expected": expected_status_decision_heading,
        "status_redirect_heading_expectation_source": status_heading_expectation_source,
        "status_redirect_heading_matches_release_channel": status_heading_matches_release_channel,
        "status_redirect_heading_uses_generic_updated_copy": status_heading_uses_generic_updated_copy,
        "downloads_version_text": downloads_version_text,
        "status_redirect_version_text": status_version_text,
        "downloads_sha256": hashlib.sha256(downloads_html.encode("utf-8")).hexdigest(),
        "status_sha256": hashlib.sha256(status_html.encode("utf-8")).hexdigest(),
    }, failures


def summarize_checks(checks: list[dict[str, Any]]) -> dict[str, Any]:
    source_check = next((check for check in checks if check.get("mode") == "source"), {})
    public_release_check = next((check for check in checks if check.get("mode") == "public_release_manifest"), {})
    live_check = next((check for check in checks if check.get("mode") == "live"), {})

    summary: dict[str, Any] = {
        "source_marker_in_view": source_check.get("marker_in_view"),
        "source_manifest_version_marker_prefers_release_version": source_check.get("manifest_version_marker_prefers_release_version"),
        "source_styled_marker": source_check.get("styled_marker"),
        "source_playwright_records_version_text": source_check.get("playwright_records_version_text"),
    }

    if public_release_check:
        summary.update(
            {
                "public_release_manifest_path": public_release_check.get("path"),
                "public_release_manifest_exists": public_release_check.get("exists"),
                "public_release_contract_name": public_release_check.get("public_release_contract_name"),
                "public_release_contract_name_matches_release_channel": public_release_check.get("public_release_contract_name_matches_release_channel"),
                "public_release_aliases_consistent": public_release_check.get("public_release_aliases_consistent"),
                "public_release_conflicting_aliases": public_release_check.get("public_release_conflicting_aliases"),
                "public_release_status": public_release_check.get("public_release_status"),
                "public_release_status_matches_release_channel": public_release_check.get("public_release_status_matches_release_channel"),
                "public_release_version": public_release_check.get("public_release_version"),
                "public_release_version_matches_release_channel": public_release_check.get("public_release_version_matches_release_channel"),
                "public_release_channel": public_release_check.get("public_release_channel"),
                "public_release_channel_matches_release_channel": public_release_check.get("public_release_channel_matches_release_channel"),
                "public_release_supportability_state": public_release_check.get("public_release_supportability_state"),
                "public_release_supportability_matches_release_channel": public_release_check.get("public_release_supportability_matches_release_channel"),
                "public_release_rollout_state": public_release_check.get("public_release_rollout_state"),
                "public_release_rollout_matches_release_channel": public_release_check.get("public_release_rollout_matches_release_channel"),
                "public_release_published_at": public_release_check.get("public_release_published_at"),
                "public_release_published_at_matches_release_channel": public_release_check.get("public_release_published_at_matches_release_channel"),
                "public_release_proof_freshness_status": public_release_check.get("public_release_proof_freshness_status"),
                "public_release_proof_freshness_matches_release_channel": public_release_check.get("public_release_proof_freshness_matches_release_channel"),
                "public_release_public_trust_supportability_state": public_release_check.get("public_release_public_trust_supportability_state"),
                "public_release_public_trust_supportability_matches_release_channel": public_release_check.get("public_release_public_trust_supportability_matches_release_channel"),
                "public_release_public_trust_rollout_state": public_release_check.get("public_release_public_trust_rollout_state"),
                "public_release_public_trust_rollout_matches_release_channel": public_release_check.get("public_release_public_trust_rollout_matches_release_channel"),
                "public_release_registry_supportability_state": public_release_check.get("public_release_registry_supportability_state"),
                "public_release_registry_supportability_matches_release_channel": public_release_check.get("public_release_registry_supportability_matches_release_channel"),
                "public_release_registry_rollout_state": public_release_check.get("public_release_registry_rollout_state"),
                "public_release_registry_rollout_matches_release_channel": public_release_check.get("public_release_registry_rollout_matches_release_channel"),
                "public_release_copy_safe": public_release_check.get("public_release_copy_safe"),
                "public_release_unsafe_copy_markers": public_release_check.get("public_release_unsafe_copy_markers"),
                "public_release_has_preview_or_review_caveat": public_release_check.get("public_release_has_preview_or_review_caveat"),
            }
        )

    if live_check:
        summary.update(
            {
                "base_url": live_check.get("base_url"),
                "expected_release_version": live_check.get("expected_release_version"),
                "visible_version_matches_release_channel": live_check.get("visible_version_matches_release_channel"),
                "status_redirect_version_matches_release_channel": live_check.get("status_redirect_version_matches_release_channel"),
                "downloads_status": live_check.get("downloads_status"),
                "status_status": live_check.get("status_status"),
                "downloads_has_marker": live_check.get("downloads_marker"),
                "status_redirect_has_marker": live_check.get("status_redirect_marker"),
                "downloads_version_marker_value": live_check.get("downloads_version_marker_value"),
                "status_redirect_version_marker_value": live_check.get("status_redirect_version_marker_value"),
                "downloads_version_marker_matches_release_channel": live_check.get("downloads_version_marker_matches_release_channel"),
                "status_redirect_version_marker_matches_release_channel": live_check.get("status_redirect_version_marker_matches_release_channel"),
                "status_redirect_heading": live_check.get("status_redirect_heading"),
                "status_redirect_heading_recognized": live_check.get("status_redirect_heading_recognized"),
                "status_redirect_heading_expected": live_check.get("status_redirect_heading_expected"),
                "status_redirect_heading_expectation_source": live_check.get("status_redirect_heading_expectation_source"),
                "status_redirect_heading_matches_release_channel": live_check.get("status_redirect_heading_matches_release_channel"),
                "status_redirect_heading_uses_generic_updated_copy": live_check.get("status_redirect_heading_uses_generic_updated_copy"),
                "visible_version": live_check.get("downloads_version_text"),
                "status_redirect_version": live_check.get("status_redirect_version_text"),
                "expected_release_status": live_check.get("expected_release_status"),
                "expected_release_supportability_state": live_check.get("expected_release_supportability_state"),
                "expected_release_channel": live_check.get("expected_release_channel"),
                "expected_release_rollout_state": live_check.get("expected_release_rollout_state"),
                "expected_release_published_at": live_check.get("expected_release_published_at"),
                "expected_release_proof_freshness_status": live_check.get("expected_release_proof_freshness_status"),
                "expected_public_installer_available": live_check.get("expected_public_installer_available"),
                "release_manifest_http_status": live_check.get("release_manifest_http_status"),
                "release_manifest_contract_name": live_check.get("release_manifest_contract_name"),
                "release_manifest_contract_name_matches_release_channel": live_check.get("release_manifest_contract_name_matches_release_channel"),
                "release_manifest_aliases_consistent": live_check.get("release_manifest_aliases_consistent"),
                "release_manifest_conflicting_aliases": live_check.get("release_manifest_conflicting_aliases"),
                "release_manifest_status": live_check.get("release_manifest_status"),
                "release_manifest_status_matches_release_channel": live_check.get("release_manifest_status_matches_release_channel"),
                "release_manifest_version": live_check.get("release_manifest_version"),
                "release_manifest_version_matches_release_channel": live_check.get("release_manifest_version_matches_release_channel"),
                "release_manifest_channel": live_check.get("release_manifest_channel"),
                "release_manifest_channel_matches_release_channel": live_check.get("release_manifest_channel_matches_release_channel"),
                "release_manifest_supportability_state": live_check.get("release_manifest_supportability_state"),
                "release_manifest_supportability_matches_release_channel": live_check.get("release_manifest_supportability_matches_release_channel"),
                "release_manifest_supportability_compatible_with_release_channel": live_check.get("release_manifest_supportability_compatible_with_release_channel"),
                "release_manifest_rollout_state": live_check.get("release_manifest_rollout_state"),
                "release_manifest_rollout_matches_release_channel": live_check.get("release_manifest_rollout_matches_release_channel"),
                "release_manifest_rollout_compatible_with_release_channel": live_check.get("release_manifest_rollout_compatible_with_release_channel"),
                "release_manifest_published_at": live_check.get("release_manifest_published_at"),
                "release_manifest_published_at_matches_release_channel": live_check.get("release_manifest_published_at_matches_release_channel"),
                "release_manifest_proof_freshness_status": live_check.get("release_manifest_proof_freshness_status"),
                "release_manifest_proof_freshness_matches_release_channel": live_check.get("release_manifest_proof_freshness_matches_release_channel"),
                "release_manifest_public_trust_supportability_state": live_check.get("release_manifest_public_trust_supportability_state"),
                "release_manifest_public_trust_supportability_matches_release_channel": live_check.get("release_manifest_public_trust_supportability_matches_release_channel"),
                "release_manifest_public_trust_rollout_state": live_check.get("release_manifest_public_trust_rollout_state"),
                "release_manifest_public_trust_rollout_matches_release_channel": live_check.get("release_manifest_public_trust_rollout_matches_release_channel"),
                "release_manifest_registry_supportability_state": live_check.get("release_manifest_registry_supportability_state"),
                "release_manifest_registry_supportability_matches_release_channel": live_check.get("release_manifest_registry_supportability_matches_release_channel"),
                "release_manifest_registry_rollout_state": live_check.get("release_manifest_registry_rollout_state"),
                "release_manifest_registry_rollout_matches_release_channel": live_check.get("release_manifest_registry_rollout_matches_release_channel"),
                "release_manifest_conservative_review_floor_applied": live_check.get("release_manifest_conservative_review_floor_applied"),
                "release_manifest_internal_supportability_consistent": live_check.get("release_manifest_internal_supportability_consistent"),
                "release_manifest_public_installer_available": live_check.get("release_manifest_public_installer_available"),
                "release_manifest_copy_safe": live_check.get("release_manifest_copy_safe"),
                "release_manifest_unsafe_copy_markers": live_check.get("release_manifest_unsafe_copy_markers"),
                "release_manifest_has_preview_or_review_caveat": live_check.get("release_manifest_has_preview_or_review_caveat"),
                "release_manifest_parse_error": live_check.get("release_manifest_parse_error"),
                "downloads_sha256": live_check.get("downloads_sha256"),
                "status_sha256": live_check.get("status_sha256"),
            }
        )

    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify the downloads page-level release version marker.")
    parser.add_argument("--source-root", default=str(RUN_SERVICES_ROOT))
    parser.add_argument("--base-url")
    parser.add_argument("--output")
    parser.add_argument(
        "--invocation-id",
        help="Opaque caller nonce echoed into the receipt to prevent stale receipt reuse.",
    )
    parser.add_argument("--timeout-seconds", type=float, default=20.0)
    parser.add_argument("--release-channel-receipt", default=str(DEFAULT_RELEASE_CHANNEL_RECEIPT))
    parser.add_argument(
        "--release-channel-receipt-sha256",
        help="Expected SHA-256 of the exact release-channel receipt bytes selected for verification.",
    )
    parser.add_argument(
        "--public-release-manifest",
        help="Static public release manifest expected to be served from /downloads/RELEASE_CHANNEL.generated.json.",
    )
    parser.add_argument(
        "--allow-non-launch-supported-release-channel",
        action="store_true",
        help=(
            "Allow non-launch-supported release posture while still verifying that "
            "/downloads, /status, and the served manifest align with the current release channel."
        ),
    )
    parser.add_argument(
        "--allow-unbound-release-channel",
        action="store_true",
        help=(
            "Explicit legacy opt-in for live verification without an exact receipt SHA-256. "
            "Digest binding is required by default when --base-url is used."
        ),
    )
    parser.add_argument("--skip-release-version-match", action="store_true")
    args = parser.parse_args(argv)
    source_root = Path(args.source_root).resolve()
    release_channel_receipt_path = Path(args.release_channel_receipt)
    binding_requested = bool(str(args.release_channel_receipt_sha256 or "").strip())
    release_channel_binding: dict[str, Any] = {
        "path": "" if args.skip_release_version_match else str(release_channel_receipt_path),
        "expected_sha256": "",
        "actual_sha256": "",
        "sha256_matches": None,
        "status": "not_requested",
    }
    release_channel_binding_failures: list[str] = []
    if args.skip_release_version_match:
        release_channel = {}
        if binding_requested:
            release_channel_binding_failures.append(
                "release channel receipt SHA-256 cannot be combined with --skip-release-version-match"
            )
    elif binding_requested:
        (
            release_channel,
            release_channel_binding,
            release_channel_binding_failures,
        ) = load_sha256_bound_json(
            release_channel_receipt_path,
            args.release_channel_receipt_sha256,
        )
    else:
        release_channel = load_optional_json(release_channel_receipt_path)
    release_channel_receipt_sha256_bound = bool(
        release_channel_binding.get("status") == "pass"
        and release_channel_binding.get("sha256_matches") is True
    )
    release_expectations, release_channel_failures = (
        ({}, [])
        if args.skip_release_version_match
        else release_channel_expectations(
            release_channel,
            require_launch_supported=not args.allow_non_launch_supported_release_channel,
            require_published_at=binding_requested,
            require_bound_contract=binding_requested,
        )
    )
    expected_release_status = release_expectations.get("status", "")
    expected_release_version = release_expectations.get("version", "")
    expected_release_channel = release_expectations.get("channel", "")
    expected_supportability_state = release_expectations.get("supportability_state", "")
    expected_rollout_state = release_expectations.get("rollout_state", "")
    expected_public_installer_available = release_expectations.get("public_installer_available")

    checks: list[dict[str, Any]] = []
    failures: list[str] = list(release_channel_binding_failures)
    if (
        args.base_url
        and not binding_requested
        and not args.allow_unbound_release_channel
    ):
        failures.append(
            "live verification requires --release-channel-receipt-sha256 unless --allow-unbound-release-channel is explicit"
        )
    source_result, source_failures = verify_source(source_root)
    checks.append(source_result)
    failures.extend(source_failures)

    if not args.skip_release_version_match:
        failures.extend(release_channel_failures)
        public_release_manifest_path = (
            Path(args.public_release_manifest)
            if args.public_release_manifest
            else source_root / DEFAULT_PUBLIC_RELEASE_MANIFEST_RELATIVE
        )
        public_release_result, public_release_failures = verify_public_release_manifest(
            public_release_manifest_path,
            release_expectations,
            release_channel_receipt_sha256_bound=(
                release_channel_receipt_sha256_bound
            ),
        )
        checks.append(public_release_result)
        failures.extend(public_release_failures)

    if args.base_url:
        try:
            live_result, live_failures = verify_live(
                args.base_url,
                args.timeout_seconds,
                expected_release_status,
                expected_release_version,
                expected_release_channel,
                expected_supportability_state,
                expected_rollout_state,
                expected_public_installer_available,
                expected_published_at=release_expectations.get("published_at", ""),
                expected_proof_freshness_status=release_expectations.get("proof_freshness_status", ""),
                expected_public_trust_supportability_state=release_expectations.get("public_trust_supportability_state", ""),
                expected_public_trust_rollout_state=release_expectations.get("public_trust_rollout_state", ""),
                expected_registry_supportability_state=release_expectations.get("registry_supportability_state", ""),
                expected_registry_rollout_state=release_expectations.get("registry_rollout_state", ""),
                expected_contract_name=release_expectations.get("contract_name", ""),
                release_channel_receipt_sha256_bound=release_channel_receipt_sha256_bound,
            )
        except RuntimeError as exc:
            live_result = {
                "mode": "live",
                "base_url": args.base_url.rstrip("/"),
                "expected_release_status": expected_release_status,
                "expected_release_version": expected_release_version,
                "expected_release_channel": expected_release_channel,
                "expected_release_supportability_state": expected_supportability_state,
                "expected_release_rollout_state": expected_rollout_state,
                "expected_release_published_at": release_expectations.get("published_at", ""),
                "expected_release_proof_freshness_status": release_expectations.get("proof_freshness_status", ""),
                "expected_public_installer_available": expected_public_installer_available,
                "status_redirect_heading_expected": release_expectations.get("status_heading_expected"),
                "status_redirect_heading_expectation_source": "release_channel_receipt",
                "probe_error": str(exc),
            }
            live_failures = [f"live probe failed: {exc}"]
        checks.append(live_result)
        failures.extend(live_failures)

    result = {
        "contractName": (
            BOUND_CONTRACT_NAME
            if release_channel_receipt_sha256_bound
            else CONTRACT_NAME
        ),
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "invocation_id": str(args.invocation_id or "").strip(),
        "status": "pass" if not failures else "fail",
        "checks": checks,
        "failures": failures,
        "release_channel_receipt": "" if args.skip_release_version_match else str(Path(args.release_channel_receipt)),
        "release_channel_receipt_sha256_expected": release_channel_binding.get("expected_sha256", ""),
        "release_channel_receipt_sha256_actual": release_channel_binding.get("actual_sha256", ""),
        "release_channel_receipt_sha256_matches": release_channel_binding.get("sha256_matches"),
        "release_channel_receipt_binding_status": release_channel_binding.get("status", "not_requested"),
        "release_channel_status": release_expectations.get("status", ""),
        "release_channel_version": release_expectations.get("version", ""),
        "release_channel_published_at": release_expectations.get("published_at", ""),
        "release_channel_proof_freshness_status": release_expectations.get(
            "proof_freshness_status",
            "",
        ),
        "release_channel_public_installer_available": release_expectations.get("public_installer_available"),
        "release_channel_status_heading_expected": release_expectations.get("status_heading_expected"),
    }
    result.update(summarize_checks(checks))
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        Path(args.output).write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
