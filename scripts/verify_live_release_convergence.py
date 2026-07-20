#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import html
import json
import re
import sys
from typing import Any, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.parse import quote
from urllib.request import HTTPRedirectHandler, Request, build_opener


PROJECTION_HEADER = "x-chummer-release-truth"
AUTHORITY_SNAPSHOT_SHA256_HEADER = (
    "x-chummer-release-authority-snapshot-sha256"
)
PROJECTION_CONTRACT = "chummer.release-truth-projection/v1"
RECEIPT_CONTRACT = "chummer.live-release-convergence/v1"
REQUIRED_FIELDS = (
    "releaseVersion",
    "channel",
    "releaseStatus",
    "rolloutState",
    "supportabilityState",
    "availablePlatforms",
    "primaryHeadByPlatform",
    "artifactCount",
    "downloadAccessPosture",
    "knownIssueSummary",
    "manifestSha256",
    "registryCommit",
    "releaseDecisionStatus",
    "releaseDecisionSha256",
)
DEFAULT_ROUTES = (
    "/",
    "/now",
    "/changelog",
    "/downloads",
    "/downloads/concierge",
    "/status",
    "/artifacts",
    "/progress",
    "/help",
    "/now/concierge",
    "/now/concierge/read_notes",
    "/api/v1/public/progress-report",
    "/api/public/progress-report",
    "/api/v1/public/progress-poster.svg",
    "/api/public/progress-poster.svg",
    "/api/v1/public/weekly-pulse",
    "/api/public/weekly-pulse",
    "/api/public/release-truth",
    "/api/v1/install-linking/continuation",
    "/api/v1/install-linking/continuation/support",
    "/api/v1/install-linking/continuation/update",
    "/api/v1/install-linking/continuation/rollback",
    "/downloads/releases.json",
    "/downloads/RELEASE_CHANNEL.generated.json",
    # Exercise endpoint-routing normalization as part of the live denominator.
    "/Now/",
    "/Help/",
    "/Downloads/Concierge/",
    "/Now/Concierge/",
    "/Now/Concierge/read_notes/",
)
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
GIT_COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
GENERATION_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
ARTIFACT_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
SCRIPT_PATTERN = re.compile(
    r"<script\b[^>]*\bid=[\"']chummer-release-truth[\"'][^>]*>(.*?)</script>",
    re.IGNORECASE | re.DOTALL,
)
METADATA_PATTERN = re.compile(
    r"<metadata\b[^>]*\bid=[\"']chummer-release-truth[\"'][^>]*>(.*?)</metadata>",
    re.IGNORECASE | re.DOTALL,
)
SCRIPT_BLOCK_PATTERN = re.compile(
    r"<script\b[^>]*>.*?</script>",
    re.IGNORECASE | re.DOTALL,
)
STYLE_BLOCK_PATTERN = re.compile(
    r"<style\b[^>]*>.*?</style>",
    re.IGNORECASE | re.DOTALL,
)
TEMPLATE_BLOCK_PATTERN = re.compile(
    r"<template\b[^>]*>.*?</template>",
    re.IGNORECASE | re.DOTALL,
)
HTML_COMMENT_PATTERN = re.compile(r"<!--.*?-->", re.DOTALL)
HTML_TAG_PATTERN = re.compile(r"<[^>]+>", re.DOTALL)
RENDERED_AVAILABLE_PATTERNS = (
    re.compile(
        r"\bcurrent\s+builds?\s+(?:is|are)\s+"
        r"(?:published\s+and\s+)?(?:ready|available|live)"
        r"(?:\s+to\s+download)?\b"
    ),
    re.compile(
        r"\b(?:downloads?|installers?)\s+(?:is|are)\s+"
        r"(?:published|ready|available|live)\b"
    ),
    re.compile(
        r"\b(?:a|the)\s+(?:current\s+)?(?:public\s+)?"
        r"(?:build|installer)\s+(?:is\s+)?(?:ready|available|live)\b"
    ),
)
RENDERED_WITHHELD_PATTERNS = (
    re.compile(
        r"\bno\s+(?:(?:current|public)\s+){0,2}"
        r"(?:builds?|installers?|downloads?)\s+"
        r"(?:(?:is|are)\s+)?(?:ready|available|live)"
        r"(?:\s+right\s+now)?\b"
    ),
    re.compile(
        r"\bno\s+(?:(?:current|public)\s+){0,2}installer"
        r"(?:\s+right\s+now)?(?=[.!?,;]|$)"
    ),
    re.compile(
        r"\bdownloads?\s+(?:(?:is|are)\s+)?(?:paused|unavailable|withheld)\b"
    ),
    re.compile(r"\bno\s+current\s+build\s+has\s+passed\s+release\s+verification\b"),
)
PLATFORM_TOKEN_PATTERN = re.compile(r"\b(?:windows|linux|mac(?:os|\s+os)?)\b")
PLATFORM_CLAIM_PATTERN = re.compile(
    r"\b(?P<negated>no\s+)?"
    r"(?P<platforms>(?:windows|linux|mac(?:os|\s+os)?)"
    r"(?:\s*(?:,|and|&)\s*(?:windows|linux|mac(?:os|\s+os)?))*)\s+"
    r"(?:downloads?|installers?|builds?)\s+"
    r"(?:(?:is|are)\s+)?"
    r"(?P<state>published\s+and\s+ready|live|available|ready|paused|unavailable|withheld|blocked)\b"
)
RENDERED_SCALAR_FIELD_PATTERNS = {
    "releaseVersion": re.compile(
        r"\b(?:current\s+)?release\s+version\s*(?::|is)\s*"
        r"(?P<value>[a-z0-9][a-z0-9._-]{0,127})\b"
    ),
    "channel": re.compile(
        r"\b(?:current\s+)?release\s+channel\s*(?::|is)\s*"
        r"(?P<value>[a-z0-9][a-z0-9._-]{0,127})\b"
    ),
    "releaseStatus": re.compile(
        r"\brelease\s+status\s*(?::|is)\s*"
        r"(?P<value>[a-z0-9][a-z0-9._-]{0,127})\b"
    ),
    "rolloutState": re.compile(
        r"\brollout\s+state\s*(?::|is)\s*"
        r"(?P<value>[a-z0-9][a-z0-9._-]{0,127})\b"
    ),
    "supportabilityState": re.compile(
        r"\bsupportability\s+state\s*(?::|is)\s*"
        r"(?P<value>[a-z0-9][a-z0-9._-]{0,127})\b"
    ),
    "downloadAccessPosture": re.compile(
        r"\bdownload\s+access(?:\s+posture)?\s*(?::|is)\s*"
        r"(?P<value>[a-z0-9][a-z0-9._-]{0,127})\b"
    ),
    "releaseDecisionStatus": re.compile(
        r"\brelease\s+decision(?:\s+status)?\s*(?::|is)\s*"
        r"(?P<value>[a-z0-9][a-z0-9._-]{0,127})\b"
    ),
    "manifestSha256": re.compile(
        r"\bmanifest\s+sha(?:-?256)?\s*(?::|is)\s*"
        r"(?P<value>[0-9a-f]{64})\b"
    ),
    "releaseDecisionSha256": re.compile(
        r"\brelease\s+decision\s+sha(?:-?256)?\s*(?::|is)\s*"
        r"(?P<value>[0-9a-f]{64})\b"
    ),
}
RENDERED_ARTIFACT_COUNT_PATTERN = re.compile(
    r"\bartifact\s+count\s*(?::|is)\s*(?P<value>[0-9]{1,3})\b"
)
EXPECTED_RELEASE_FIELDS = (
    "releaseVersion",
    "manifestSha256",
    "releaseDecisionSha256",
)


class ConvergenceError(RuntimeError):
    pass


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class SameOriginRedirectHandler(HTTPRedirectHandler):
    def __init__(self, authority: tuple[str, str]):
        super().__init__()
        self._authority = authority

    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        parsed = urlparse(new_url)
        if (parsed.scheme.lower(), parsed.netloc.lower()) != self._authority:
            raise ConvergenceError(f"cross-origin redirect refused: {new_url}")
        return super().redirect_request(
            request, file_pointer, code, message, headers, new_url
        )


class NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        return None


def canonicalize_projection(payload: Any, *, source: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ConvergenceError(f"{source}: release truth must be a JSON object")

    projection = dict(payload)
    if projection.get("contractName") != PROJECTION_CONTRACT:
        raise ConvergenceError(
            f"{source}: contractName must be {PROJECTION_CONTRACT}"
        )
    allowed_fields = {"contractName", *REQUIRED_FIELDS}
    unknown = sorted(set(projection) - allowed_fields)
    if unknown:
        raise ConvergenceError(
            f"{source}: unknown release-truth fields: {', '.join(unknown)}"
        )

    missing = [field for field in REQUIRED_FIELDS if field not in projection]
    if missing:
        raise ConvergenceError(f"{source}: missing required fields: {', '.join(missing)}")

    scalar_fields = (
        "releaseVersion",
        "channel",
        "releaseStatus",
        "rolloutState",
        "supportabilityState",
        "downloadAccessPosture",
        "knownIssueSummary",
        "manifestSha256",
        "registryCommit",
        "releaseDecisionStatus",
        "releaseDecisionSha256",
    )
    for field in scalar_fields:
        value = projection[field]
        if (
            not isinstance(value, str)
            or not value.strip()
            or value != value.strip()
        ):
            raise ConvergenceError(
                f"{source}: {field} must be a canonical non-empty string"
            )
    for field in scalar_fields:
        maximum = 512 if field == "knownIssueSummary" else 128
        if len(projection[field]) > maximum:
            raise ConvergenceError(f"{source}: {field} exceeds its bounded length")

    platforms = projection["availablePlatforms"]
    if not isinstance(platforms, list) or len(platforms) > 16 or any(
        not isinstance(platform, str) or not platform or len(platform) > 128
        for platform in platforms
    ):
        raise ConvergenceError(f"{source}: availablePlatforms must be a string array")
    if platforms != sorted(set(platforms)) or any(
        platform != platform.lower() for platform in platforms
    ):
        raise ConvergenceError(
            f"{source}: availablePlatforms must contain unique lower-case IDs in ordinal order"
        )

    heads = projection["primaryHeadByPlatform"]
    if not isinstance(heads, dict) or set(heads) != set(platforms):
        raise ConvergenceError(
            f"{source}: primaryHeadByPlatform keys must exactly match availablePlatforms"
        )
    if any(
        not isinstance(value, str) or not value or len(value) > 128
        for value in heads.values()
    ):
        raise ConvergenceError(
            f"{source}: primaryHeadByPlatform values must be non-empty strings"
        )

    artifact_count = projection["artifactCount"]
    if (
        isinstance(artifact_count, bool)
        or not isinstance(artifact_count, int)
        or artifact_count < 0
        or artifact_count > 256
    ):
        raise ConvergenceError(f"{source}: artifactCount must be a non-negative integer")
    if projection["downloadAccessPosture"] not in {
        "unavailable",
        "open_public",
        "account_recommended",
        "account_required",
        "mixed",
    }:
        raise ConvergenceError(f"{source}: invalid downloadAccessPosture")
    if projection["releaseDecisionStatus"] not in {
        "review_required",
        "preview_ready",
        "stable_ready",
    }:
        raise ConvergenceError(f"{source}: invalid releaseDecisionStatus")
    if artifact_count == 0:
        if (
            platforms
            or heads
            or projection["downloadAccessPosture"] != "unavailable"
            or projection["releaseDecisionStatus"] != "review_required"
        ):
            raise ConvergenceError(
                f"{source}: an empty shelf is valid only as review_required with unavailable access"
            )
    elif not platforms or projection["downloadAccessPosture"] == "unavailable":
        raise ConvergenceError(
            f"{source}: a non-empty shelf requires platforms and a usable downloadAccessPosture"
        )
    if not SHA256_PATTERN.fullmatch(projection["manifestSha256"]):
        raise ConvergenceError(f"{source}: manifestSha256 is not immutable authority SHA-256")
    if not SHA256_PATTERN.fullmatch(projection["releaseDecisionSha256"]):
        raise ConvergenceError(f"{source}: releaseDecisionSha256 is not a SHA-256")
    if not GIT_COMMIT_PATTERN.fullmatch(projection["registryCommit"]):
        raise ConvergenceError(f"{source}: registryCommit is not a Git commit ID")

    return {
        "contractName": PROJECTION_CONTRACT,
        **{field: projection[field] for field in REQUIRED_FIELDS},
    }


def decode_projection_header(value: str, *, source: str) -> dict[str, Any]:
    if len(value) > 16 * 1024:
        raise ConvergenceError(f"{source}: {PROJECTION_HEADER} header exceeds 16 KiB")
    try:
        padding = "=" * (-len(value) % 4)
        raw = base64.urlsafe_b64decode((value + padding).encode("ascii"))
        payload = _strict_json_loads(raw.decode("utf-8"), source=source)
    except (ValueError, UnicodeError, json.JSONDecodeError) as error:
        raise ConvergenceError(f"{source}: invalid {PROJECTION_HEADER} header") from error
    return canonicalize_projection(payload, source=f"{source} header")


def _strict_json_loads(value: str, *, source: str) -> Any:
    def reject_duplicates(pairs):
        result = {}
        for key, item in pairs:
            if key in result:
                raise ConvergenceError(f"{source}: duplicate JSON property: {key}")
            result[key] = item
        return result

    return json.loads(value, object_pairs_hook=reject_duplicates)


def _body_projection(
    body: bytes,
    content_type: str,
    *,
    source: str,
    require_textual_projection: bool = True,
) -> dict[str, Any] | None:
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError as error:
        if "application/octet-stream" in content_type:
            return None
        raise ConvergenceError(f"{source}: response body is not UTF-8") from error

    candidate: Any | None = None
    native_payload: dict[str, Any] | None = None
    if "json" in content_type:
        try:
            payload = _strict_json_loads(text, source=source)
        except json.JSONDecodeError as error:
            raise ConvergenceError(f"{source}: response JSON is malformed") from error
        if isinstance(payload, dict):
            native_payload = payload
            candidate = payload.get("releaseTruth")
            if candidate is None and payload.get("contractName") == PROJECTION_CONTRACT:
                candidate = payload
    elif "html" in content_type:
        match = SCRIPT_PATTERN.search(text)
        if match:
            try:
                candidate = _strict_json_loads(match.group(1), source=source)
            except json.JSONDecodeError as error:
                raise ConvergenceError(f"{source}: embedded release truth is malformed") from error
    elif "svg" in content_type:
        match = METADATA_PATTERN.search(text)
        if match:
            try:
                candidate = _strict_json_loads(html.unescape(match.group(1)), source=source)
            except json.JSONDecodeError as error:
                raise ConvergenceError(f"{source}: SVG release truth is malformed") from error

    if require_textual_projection and candidate is None and any(
        media_type in content_type for media_type in ("json", "html", "svg")
    ):
        raise ConvergenceError(
            f"{source}: textual release-facing response is missing embedded releaseTruth"
        )

    if candidate is None:
        return None

    projection = canonicalize_projection(candidate, source=f"{source} body")
    if "html" in content_type:
        _validate_rendered_release_fields(text, projection, source=source)
    if (
        native_payload is not None
        and native_payload is not candidate
        and _is_release_manifest_route(source)
    ):
        _validate_native_manifest_claims(native_payload, projection, source=source)
    return projection


def _visible_document_text(document: str) -> str:
    visible = SCRIPT_BLOCK_PATTERN.sub(" ", document)
    visible = STYLE_BLOCK_PATTERN.sub(" ", visible)
    visible = TEMPLATE_BLOCK_PATTERN.sub(" ", visible)
    visible = HTML_COMMENT_PATTERN.sub(" ", visible)
    visible = HTML_TAG_PATTERN.sub(" ", visible)
    return " ".join(html.unescape(visible).casefold().split())


def _matching_spans(
    patterns: Sequence[re.Pattern[str]],
    text: str,
) -> list[tuple[int, int]]:
    return [match.span() for pattern in patterns for match in pattern.finditer(text)]


def _mask_spans(text: str, spans: Sequence[tuple[int, int]]) -> str:
    masked = list(text)
    for start, end in spans:
        masked[start:end] = " " * (end - start)
    return "".join(masked)


def _spans_overlap(left: tuple[int, int], right: tuple[int, int]) -> bool:
    return left[0] < right[1] and right[0] < left[1]


def _platform_family(value: str) -> str | None:
    normalized = value.casefold().replace(" ", "").replace("_", "").replace("-", "")
    if "windows" in normalized or normalized.startswith("win"):
        return "windows"
    if "linux" in normalized:
        return "linux"
    if normalized == "mac" or any(
        marker in normalized for marker in ("macos", "osx", "darwin")
    ):
        return "macos"
    return None


def _canonical_rendered_scalar(field: str, value: Any) -> Any:
    if field == "artifactCount":
        return int(value)
    rendered = str(value).casefold()
    if field in {
        "channel",
        "releaseStatus",
        "rolloutState",
        "supportabilityState",
        "downloadAccessPosture",
        "releaseDecisionStatus",
    }:
        return re.sub(r"[^a-z0-9]+", "_", rendered).strip("_")
    return rendered


def _platform_claim_is_negative(match: re.Match[str]) -> bool:
    return bool(match.group("negated")) or match.group("state") in {
        "paused",
        "unavailable",
        "withheld",
        "blocked",
    }


def _validate_rendered_release_fields(
    document: str,
    projection: Mapping[str, Any],
    *,
    source: str,
) -> None:
    visible = _visible_document_text(document)
    contradictions: list[str] = []

    platform_matches = list(PLATFORM_CLAIM_PATTERN.finditer(visible))
    platform_spans = [match.span() for match in platform_matches]
    withheld_spans = [
        span
        for span in _matching_spans(RENDERED_WITHHELD_PATTERNS, visible)
        if not any(_spans_overlap(span, platform_span) for platform_span in platform_spans)
    ]
    availability_claims = [False] * len(withheld_spans)
    negated_platform_spans = [
        match.span() for match in platform_matches if _platform_claim_is_negative(match)
    ]
    visible_without_withheld_claims = _mask_spans(
        visible,
        [*withheld_spans, *negated_platform_spans],
    )
    availability_claims.extend(
        True
        for pattern in RENDERED_AVAILABLE_PATTERNS
        for _ in pattern.finditer(visible_without_withheld_claims)
    )
    expected_availability = _availability_claims_allowed(projection)
    if any(claim != expected_availability for claim in availability_claims):
        rendered_states = sorted(
            {"available" if claim else "withheld" for claim in availability_claims}
        )
        contradictions.append(
            "availability=" + "/".join(rendered_states)
            + f" (expected {'available' if expected_availability else 'withheld'})"
        )

    available_families = {
        family
        for platform in projection["availablePlatforms"]
        if (family := _platform_family(platform)) is not None
    }
    for match in platform_matches:
        negative_state = _platform_claim_is_negative(match)
        claimed_families = {
            family
            for token in PLATFORM_TOKEN_PATTERN.findall(match.group("platforms"))
            if (family := _platform_family(token)) is not None
        }
        for family in sorted(claimed_families):
            observed_available = not negative_state
            if observed_available != (family in available_families):
                contradictions.append(
                    f"availablePlatforms:{family}="
                    f"{'available' if observed_available else 'withheld'}"
                )

    for field, pattern in RENDERED_SCALAR_FIELD_PATTERNS.items():
        expected_value = _canonical_rendered_scalar(field, projection[field])
        for match in pattern.finditer(visible):
            rendered_value = _canonical_rendered_scalar(field, match.group("value"))
            if rendered_value != expected_value:
                contradictions.append(
                    f"{field}={match.group('value')} (expected {projection[field]})"
                )

    for match in RENDERED_ARTIFACT_COUNT_PATTERN.finditer(visible):
        rendered_count = int(match.group("value"))
        if rendered_count != projection["artifactCount"]:
            contradictions.append(
                f"artifactCount={rendered_count} (expected {projection['artifactCount']})"
            )

    if contradictions:
        raise ConvergenceError(
            f"{source}: rendered release fields contradict embedded release truth: "
            + ", ".join(sorted(set(contradictions)))
        )


def _is_release_manifest_route(route: str) -> bool:
    normalized = route.rstrip("/").lower()
    return normalized.endswith("/releases.json") or normalized.endswith(
        "/release_channel.generated.json"
    )


def _validate_native_manifest_claims(
    payload: Mapping[str, Any],
    projection: Mapping[str, Any],
    *,
    source: str,
) -> None:
    claim_aliases = {
        "releaseVersion": ("releaseVersion", "version"),
        "channel": ("channel", "channelId"),
        "releaseStatus": ("releaseStatus", "status"),
        "rolloutState": ("rolloutState",),
        "supportabilityState": ("supportabilityState",),
        "downloadAccessPosture": ("downloadAccessPosture",),
        "knownIssueSummary": ("knownIssueSummary",),
        "manifestSha256": ("manifestSha256",),
        "registryCommit": ("registryCommit",),
        "releaseDecisionStatus": ("releaseDecisionStatus",),
        "releaseDecisionSha256": ("releaseDecisionSha256",),
    }
    drift: list[str] = []
    for projection_field, aliases in claim_aliases.items():
        present = [alias for alias in aliases if alias in payload]
        if not present:
            continue
        values = [payload[alias] for alias in present]
        if any(not isinstance(value, str) or value != value.strip() for value in values):
            raise ConvergenceError(
                f"{source}: native {present[0]} must be a canonical string"
            )
        if any(value != projection[projection_field] for value in values):
            drift.append(projection_field)

    artifact_fields = [field for field in ("downloads", "artifacts") if field in payload]
    for field in artifact_fields:
        artifacts = payload[field]
        if not isinstance(artifacts, list):
            raise ConvergenceError(f"{source}: native {field} must be an array")
        if len(artifacts) != projection["artifactCount"]:
            drift.append("artifactCount")
        rows: list[Mapping[str, Any]] = []
        for index, artifact in enumerate(artifacts):
            if not isinstance(artifact, dict):
                raise ConvergenceError(
                    f"{source}: native {field}[{index}] must be an object"
                )
            rows.append(artifact)

        if rows:
            platforms: list[str] = []
            access_classes: list[str] = []
            platform_heads: set[tuple[str, str]] = set()
            for index, artifact in enumerate(rows):
                platform = _native_artifact_string(
                    artifact,
                    ("platformId",) if "platformId" in artifact else ("platform",),
                    source=f"{source}: native {field}[{index}]",
                )
                head = _native_artifact_string(
                    artifact,
                    ("head", "headId"),
                    source=f"{source}: native {field}[{index}]",
                )
                access_class = _native_artifact_string(
                    artifact,
                    ("installAccessClass",),
                    source=f"{source}: native {field}[{index}]",
                )
                if access_class not in {
                    "open_public",
                    "account_recommended",
                    "account_required",
                }:
                    raise ConvergenceError(
                        f"{source}: native {field}[{index}] installAccessClass is unsupported"
                    )
                platforms.append(platform)
                access_classes.append(access_class)
                platform_heads.add((platform, head))

            derived_platforms = sorted(set(platforms))
            if derived_platforms != projection["availablePlatforms"]:
                drift.append("availablePlatforms")

            distinct_access = set(access_classes)
            derived_access_posture = (
                next(iter(distinct_access))
                if len(distinct_access) == 1
                else "mixed"
            )
            if derived_access_posture != projection["downloadAccessPosture"]:
                drift.append("downloadAccessPosture")

            if any(
                (platform, head) not in platform_heads
                for platform, head in projection["primaryHeadByPlatform"].items()
            ):
                drift.append("primaryHeadByPlatform")
        elif projection["availablePlatforms"]:
            drift.extend(("availablePlatforms", "primaryHeadByPlatform"))

    if "artifactCount" in payload:
        value = payload["artifactCount"]
        if isinstance(value, bool) or not isinstance(value, int):
            raise ConvergenceError(f"{source}: native artifactCount must be an integer")
        if value != projection["artifactCount"]:
            drift.append("artifactCount")

    if "availablePlatforms" in payload:
        platforms = payload["availablePlatforms"]
        if not isinstance(platforms, list) or any(not isinstance(item, str) for item in platforms):
            raise ConvergenceError(f"{source}: native availablePlatforms must be a string array")
        if platforms != projection["availablePlatforms"]:
            drift.append("availablePlatforms")

    if "primaryHeadByPlatform" in payload:
        heads = payload["primaryHeadByPlatform"]
        if not isinstance(heads, dict) or any(
            not isinstance(key, str) or not isinstance(value, str)
            for key, value in heads.items()
        ):
            raise ConvergenceError(f"{source}: native primaryHeadByPlatform must be a string map")
        if heads != projection["primaryHeadByPlatform"]:
            drift.append("primaryHeadByPlatform")

    if drift:
        raise ConvergenceError(
            f"{source}: native body/releaseTruth drift: {', '.join(sorted(set(drift)))}"
        )


def _native_artifact_string(
    artifact: Mapping[str, Any],
    aliases: Sequence[str],
    *,
    source: str,
) -> str:
    present = [alias for alias in aliases if alias in artifact]
    if not present:
        raise ConvergenceError(f"{source}: missing {aliases[0]}")
    values = [artifact[alias] for alias in present]
    if any(
        not isinstance(value, str)
        or not value
        or value != value.strip()
        for value in values
    ):
        raise ConvergenceError(f"{source}: {present[0]} must be a canonical string")
    if any(value != values[0] for value in values[1:]):
        raise ConvergenceError(f"{source}: contradictory {present[0]} aliases")
    return values[0]


def extract_route_projection(
    *,
    route: str,
    headers: Mapping[str, str],
    body: bytes,
    content_type: str,
    require_body_projection: bool = True,
) -> dict[str, Any]:
    normalized_headers = {str(key).lower(): str(value) for key, value in headers.items()}
    encoded = normalized_headers.get(PROJECTION_HEADER)
    if not encoded:
        raise ConvergenceError(f"{route}: missing {PROJECTION_HEADER} header")

    header_projection = decode_projection_header(encoded, source=route)
    body_projection = None
    if body or require_body_projection:
        body_projection = _body_projection(
            body,
            content_type.lower(),
            source=route,
            require_textual_projection=require_body_projection,
        )
    if body_projection is not None and body_projection != header_projection:
        differing = [
            field
            for field in REQUIRED_FIELDS
            if body_projection[field] != header_projection[field]
        ]
        raise ConvergenceError(
            f"{route}: body/header release truth contradiction: {', '.join(differing)}"
        )
    return header_projection


def extract_authority_snapshot_sha256(
    *, route: str, headers: Mapping[str, str]
) -> str:
    normalized_headers = {str(key).lower(): str(value) for key, value in headers.items()}
    value = normalized_headers.get(AUTHORITY_SNAPSHOT_SHA256_HEADER, "").strip()
    if not SHA256_PATTERN.fullmatch(value):
        raise ConvergenceError(
            f"{route}: missing or invalid {AUTHORITY_SNAPSHOT_SHA256_HEADER} header"
        )
    return value


def verify_route_projections(
    authority: Mapping[str, Any],
    route_projections: Mapping[str, Mapping[str, Any]],
    *,
    authority_snapshot_sha256: str,
    route_authority_snapshot_sha256: Mapping[str, str],
    authority_route: str = "/api/v1/public/release-truth",
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    expected = canonicalize_projection(dict(authority), source="authority")
    if not SHA256_PATTERN.fullmatch(authority_snapshot_sha256):
        raise ConvergenceError("authority: authoritySnapshotSha256 is not a SHA-256")
    if not route_projections:
        raise ConvergenceError("no release-facing routes were checked")
    if set(route_authority_snapshot_sha256) != set(route_projections):
        raise ConvergenceError(
            "authority snapshot SHA coverage does not exactly match checked routes"
        )

    contradictions: dict[str, list[str]] = {}
    for route, payload in route_projections.items():
        observed = canonicalize_projection(dict(payload), source=route)
        differing = [field for field in REQUIRED_FIELDS if observed[field] != expected[field]]
        if differing:
            contradictions[route] = differing
        route_snapshot_sha256 = route_authority_snapshot_sha256[route]
        if not SHA256_PATTERN.fullmatch(route_snapshot_sha256):
            raise ConvergenceError(
                f"{route}: authoritySnapshotSha256 is not a SHA-256"
            )
        if route_snapshot_sha256 != authority_snapshot_sha256:
            contradictions.setdefault(route, []).append("authoritySnapshotSha256")

    if contradictions:
        detail = "; ".join(
            f"{route}: {', '.join(fields)}"
            for route, fields in sorted(contradictions.items())
        )
        raise ConvergenceError(f"contradictory release-facing routes: {detail}")

    return {
        "contractName": RECEIPT_CONTRACT,
        "contractVersion": 1,
        "generatedAtUtc": generated_at_utc or now_utc_iso(),
        "status": "pass",
        "mismatchCount": 0,
        "failureCount": 0,
        "mismatches": [],
        "failures": [],
        "authorityRoute": authority_route,
        "checkedRouteCount": len(route_projections),
        "checkedRoutes": sorted(route_projections),
        "comparedFields": list(REQUIRED_FIELDS),
        "releaseTruth": expected,
        "manifestSha256": expected["manifestSha256"],
        "releaseDecisionStatus": expected["releaseDecisionStatus"],
        "releaseDecisionSha256": expected["releaseDecisionSha256"],
        "authoritySnapshotSha256": authority_snapshot_sha256,
    }


def _validate_base_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ConvergenceError("base URL must be an absolute HTTP(S) URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ConvergenceError("base URL must not contain credentials, query, or fragment")
    return value.rstrip("/") + "/"


def fetch_route(
    opener,
    base_url: str,
    route: str,
    timeout: float,
    *,
    method: str = "GET",
    accept_redirect_response: bool = False,
    accepted_error_statuses: Sequence[int] = (),
) -> tuple[dict[str, str], bytes, str]:
    if not route.startswith("/") or route.startswith("//"):
        raise ConvergenceError(f"unsafe route: {route}")
    url = urljoin(base_url, route.lstrip("/"))
    request = Request(
        url,
        headers={"Accept": "*/*", "User-Agent": "chummer-release-convergence/1"},
        method=method,
    )
    try:
        with opener.open(request, timeout=timeout) as response:
            return _read_bounded_response(response, route)
    except HTTPError as error:
        if (
            (accept_redirect_response and 300 <= error.code < 400)
            or error.code in accepted_error_statuses
        ):
            try:
                return _read_bounded_response(error, route)
            finally:
                error.close()
        raise ConvergenceError(f"{route}: HTTP {error.code}") from error
    except URLError as error:
        raise ConvergenceError(f"{route}: request failed: {error.reason}") from error


def _read_bounded_response(response, route: str) -> tuple[dict[str, str], bytes, str]:
    body = response.read(8 * 1024 * 1024 + 1)
    if len(body) > 8 * 1024 * 1024:
        raise ConvergenceError(f"{route}: response exceeds 8 MiB")
    headers = {key: value for key, value in response.headers.items()}
    content_type = response.headers.get_content_type()
    return headers, body, content_type


def _requires_source_hop_validation(route: str) -> bool:
    path = urlparse(route).path.rstrip("/").lower()
    return (
        path.startswith("/now/concierge/")
        or path.startswith("/downloads/concierge/")
        or path.startswith("/downloads/install/")
        or bool(re.match(r"^/downloads/g/[^/]+/install/", path))
    )


def _requires_header_only_head(route: str) -> bool:
    path = urlparse(route).path.rstrip("/").lower()
    return path.startswith("/downloads/install/") or bool(
        re.match(r"^/downloads/g/[^/]+/install/", path)
    )


def _state_tokens(value: Any) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", str(value).casefold()))


def _availability_claims_allowed(projection: Mapping[str, Any]) -> bool:
    rollout_tokens = _state_tokens(projection["rolloutState"])
    supportability_tokens = _state_tokens(projection["supportabilityState"])
    blocking_rollout = bool(
        rollout_tokens
        & {
            "missing",
            "unknown",
            "invalid",
            "review",
            "revoked",
            "blocked",
            "withdrawn",
            "unpublished",
        }
    ) or {"coverage", "incomplete"}.issubset(rollout_tokens)
    blocking_supportability = bool(
        supportability_tokens
        & {
            "missing",
            "unknown",
            "invalid",
            "review",
            "unsupported",
            "unavailable",
            "blocked",
        }
    )
    return (
        projection["releaseDecisionStatus"] in {"preview_ready", "stable_ready"}
        and projection["releaseStatus"] == "published"
        and projection["artifactCount"] > 0
        and bool(projection["availablePlatforms"])
        and projection["downloadAccessPosture"]
        in {"open_public", "account_recommended", "account_required", "mixed"}
        and not blocking_rollout
        and not blocking_supportability
    )


def _accepted_handoff_error_statuses(
    projection: Mapping[str, Any],
) -> tuple[int, ...]:
    return () if _availability_claims_allowed(projection) else (409,)


def _validate_generation_id(value: str | None) -> str | None:
    if value is None:
        return None
    if not GENERATION_ID_PATTERN.fullmatch(value):
        raise ConvergenceError("generation ID is not a traversal-safe opaque token")
    return value


def validate_expected_release_truth(
    projection: Mapping[str, Any],
    expected_release_truth: Mapping[str, str] | None,
) -> None:
    if expected_release_truth is None:
        return
    if set(expected_release_truth) != set(EXPECTED_RELEASE_FIELDS):
        raise ConvergenceError(
            "expected release binding must provide releaseVersion, manifestSha256, "
            "and releaseDecisionSha256 together"
        )

    expected_version = expected_release_truth["releaseVersion"]
    if (
        not isinstance(expected_version, str)
        or not expected_version
        or expected_version != expected_version.strip()
        or len(expected_version) > 128
    ):
        raise ConvergenceError(
            "expected release binding releaseVersion must be a canonical non-empty string"
        )
    for field in ("manifestSha256", "releaseDecisionSha256"):
        value = expected_release_truth[field]
        if not isinstance(value, str) or not SHA256_PATTERN.fullmatch(value):
            raise ConvergenceError(
                f"expected release binding {field} must be a lower-case SHA-256"
            )

    mismatches = [
        field
        for field in EXPECTED_RELEASE_FIELDS
        if projection.get(field) != expected_release_truth[field]
    ]
    if mismatches:
        detail = ", ".join(
            f"{field}: expected={expected_release_truth[field]!r} "
            f"actual={projection.get(field)!r}"
            for field in mismatches
        )
        raise ConvergenceError(f"candidate release truth mismatch: {detail}")


def _expected_release_truth_from_args(
    args: argparse.Namespace,
) -> dict[str, str] | None:
    values = {
        "releaseVersion": args.expected_release_version,
        "manifestSha256": args.expected_manifest_sha256,
        "releaseDecisionSha256": args.expected_release_decision_sha256,
    }
    provided = {field for field, value in values.items() if value is not None}
    if not provided:
        return None
    if provided != set(EXPECTED_RELEASE_FIELDS):
        missing = sorted(set(EXPECTED_RELEASE_FIELDS) - provided)
        raise ConvergenceError(
            "expected release binding is incomplete; missing: " + ", ".join(missing)
        )
    expected = {field: str(value) for field, value in values.items()}
    validate_expected_release_truth(expected, expected)
    return expected


def generation_routes(generation_id: str) -> tuple[str, ...]:
    generation_id = _validate_generation_id(generation_id) or ""
    return (
        f"/api/public/release-truth/g/{generation_id}",
        f"/downloads/g/{generation_id}/releases.json",
        f"/downloads/g/{generation_id}/RELEASE_CHANNEL.generated.json",
        f"/downloads/g/{generation_id}/releases.json/",
    )


def discover_install_route(
    manifest_body: bytes,
    *,
    generation_id: str | None = None,
) -> str | None:
    try:
        payload = _strict_json_loads(manifest_body.decode("utf-8"), source="install-route discovery")
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ConvergenceError("install-route discovery: manifest JSON is malformed") from error
    if not isinstance(payload, dict):
        raise ConvergenceError("install-route discovery: manifest must be an object")

    candidates = payload.get("downloads") or payload.get("artifacts") or []
    if not isinstance(candidates, list):
        raise ConvergenceError("install-route discovery: artifact collection must be an array")
    rows = [row for row in candidates if isinstance(row, dict)]
    preferred = [
        row for row in rows
        if row.get("installAccessClass") == "open_public"
    ] or rows
    for row in preferred:
        artifact_id = row.get("id") or row.get("artifactId")
        if isinstance(artifact_id, str) and ARTIFACT_ID_PATTERN.fullmatch(artifact_id):
            encoded = quote(artifact_id, safe="._-")
            return (
                f"/downloads/g/{generation_id}/install/{encoded}"
                if generation_id
                else f"/downloads/install/{encoded}"
            )
    return None


def build_failure_receipt(
    detail: str,
    *,
    authority_route: str = "/api/v1/public/release-truth",
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    mismatch = any(marker in detail for marker in ("contradict", "drift", "mismatch"))
    return {
        "contractName": RECEIPT_CONTRACT,
        "contractVersion": 1,
        "generatedAtUtc": generated_at_utc or now_utc_iso(),
        "status": "fail",
        "mismatchCount": 1 if mismatch else 0,
        "failureCount": 1,
        "mismatches": [detail] if mismatch else [],
        "failures": [detail],
        "authorityRoute": authority_route,
        "checkedRouteCount": 0,
        "checkedRoutes": [],
        "comparedFields": list(REQUIRED_FIELDS),
        "releaseTruth": {},
        "manifestSha256": "missing",
        "releaseDecisionStatus": "missing",
        "releaseDecisionSha256": "missing",
        "authoritySnapshotSha256": "missing",
    }


def verify_live(
    base_url: str,
    routes: Sequence[str],
    timeout: float,
    generation_id: str | None = None,
    expected_release_truth: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    normalized_base = _validate_base_url(base_url)
    generation_id = _validate_generation_id(generation_id)
    parsed = urlparse(normalized_base)
    authority = (parsed.scheme.lower(), parsed.netloc.lower())
    opener = build_opener(SameOriginRedirectHandler(authority))
    no_redirect_opener = build_opener(NoRedirectHandler())

    authority_route = (
        f"/api/v1/public/release-truth/g/{generation_id}"
        if generation_id
        else "/api/v1/public/release-truth"
    )
    authority_headers, authority_body, authority_content_type = fetch_route(
        opener, normalized_base, authority_route, timeout
    )
    expected = extract_route_projection(
        route=authority_route,
        headers=authority_headers,
        body=authority_body,
        content_type=authority_content_type,
    )
    validate_expected_release_truth(expected, expected_release_truth)
    authority_snapshot_sha256 = extract_authority_snapshot_sha256(
        route=authority_route,
        headers=authority_headers,
    )

    route_list = list(dict.fromkeys(routes))
    fetched: dict[str, tuple[dict[str, str], bytes, str]] = {}
    manifest_route = (
        f"/downloads/g/{generation_id}/releases.json"
        if generation_id
        else "/downloads/releases.json"
    )
    if manifest_route in route_list:
        fetched[manifest_route] = fetch_route(opener, normalized_base, manifest_route, timeout)
        install_route = discover_install_route(
            fetched[manifest_route][1],
            generation_id=generation_id,
        )
        if install_route:
            route_list.append(install_route)

    route_list = list(dict.fromkeys(route_list))
    observed: dict[str, dict[str, Any]] = {}
    observed_snapshot_sha256: dict[str, str] = {}
    for route in route_list:
        header_only_head = _requires_header_only_head(route)
        prefetched = fetched.get(route)
        if prefetched is not None:
            headers, body, content_type = prefetched
        else:
            validate_source_hop = _requires_source_hop_validation(route)
            headers, body, content_type = fetch_route(
                no_redirect_opener if validate_source_hop else opener,
                normalized_base,
                route,
                timeout,
                method="HEAD" if header_only_head else "GET",
                accept_redirect_response=validate_source_hop,
                accepted_error_statuses=(
                    _accepted_handoff_error_statuses(expected)
                    if header_only_head
                    else ()
                ),
            )
        observed[route] = extract_route_projection(
            route=route,
            headers=headers,
            body=body,
            content_type=content_type,
            require_body_projection=not header_only_head,
        )
        observed_snapshot_sha256[route] = extract_authority_snapshot_sha256(
            route=route,
            headers=headers,
        )
    return verify_route_projections(
        expected,
        observed,
        authority_snapshot_sha256=authority_snapshot_sha256,
        route_authority_snapshot_sha256=observed_snapshot_sha256,
        authority_route=authority_route,
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify that every live Hub release-facing route exposes one immutable release truth."
    )
    parser.add_argument("--base-url", default="https://chummer.run")
    parser.add_argument(
        "--route",
        action="append",
        dest="routes",
        help="Release-facing route to check; repeat to override the default route set.",
    )
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument(
        "--generation-id",
        help="Verify one committed explicit/retained generation independently of CURRENT.",
    )
    parser.add_argument(
        "--expected-release-version",
        help="Require the live authority to match this local candidate releaseVersion.",
    )
    parser.add_argument(
        "--expected-manifest-sha256",
        help="Require the live authority to match this local candidate manifestSha256.",
    )
    parser.add_argument(
        "--expected-release-decision-sha256",
        help="Require the live authority to match this local candidate releaseDecisionSha256.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    authority_route = "/api/v1/public/release-truth"
    try:
        generation_id = _validate_generation_id(args.generation_id)
        if generation_id:
            authority_route = f"/api/v1/public/release-truth/g/{generation_id}"
        expected_release_truth = _expected_release_truth_from_args(args)
        routes = tuple(
            args.routes
            or (generation_routes(generation_id) if generation_id else DEFAULT_ROUTES)
        )
        result = verify_live(
            args.base_url,
            routes,
            args.timeout,
            generation_id=generation_id,
            expected_release_truth=expected_release_truth,
        )
    except ConvergenceError as error:
        detail = str(error)
        json.dump(
            build_failure_receipt(detail, authority_route=authority_route),
            sys.stdout,
            indent=2,
        )
        sys.stdout.write("\n")
        return 1
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
