#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import requests


OUT_PATHS = (
    Path("/docker/chummercomplete/chummer-design/_completion/full_product_every_aspect/PUBLIC_DOWNLOAD_SHELF_TRUTH.generated.json"),
    Path("/docker/chummercomplete/_completion/full_product_every_aspect/PUBLIC_DOWNLOAD_SHELF_TRUTH.generated.json"),
)
DEFAULT_LOCAL_MANIFEST = Path("/docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads/releases.json")
DEFAULT_LOCAL_CANONICAL_MANIFEST = Path("/docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads/RELEASE_CHANNEL.generated.json")
RETRYABLE_STATUS_CODES = {502, 503, 504}
DEFAULT_REQUEST_ATTEMPTS = 6
DEFAULT_RETRY_DELAY_SECONDS = 2.0
DEFAULT_LIVE_CONFIRMATION_COUNT = 3
DEFAULT_LIVE_CONFIRMATION_DELAY_SECONDS = 2.0
DEFAULT_LIVE_MAX_SAMPLES = 6


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--local-manifest", default=str(DEFAULT_LOCAL_MANIFEST))
    parser.add_argument("--local-canonical-manifest", default=str(DEFAULT_LOCAL_CANONICAL_MANIFEST))
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--skip-artifact-probes", action="store_true")
    parser.add_argument("--live-confirmation-count", type=int, default=DEFAULT_LIVE_CONFIRMATION_COUNT)
    parser.add_argument("--live-confirmation-delay-seconds", type=float, default=DEFAULT_LIVE_CONFIRMATION_DELAY_SECONDS)
    parser.add_argument("--live-max-samples", type=int, default=DEFAULT_LIVE_MAX_SAMPLES)
    return parser.parse_args()


def normalize_token(value: Any) -> str:
    return str(value or "").strip().lower()


def normalize_optional_text(value: Any) -> str:
    return str(value or "").strip()


def normalize_iso(value: Any) -> str:
    raw = normalize_optional_text(value)
    if not raw:
        return ""
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return str(value or "").strip()
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def safe_int(value: Any) -> int:
    if value in (None, ""):
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return payload


def fetch_json(url: str, *, timeout: float) -> tuple[requests.Response, dict[str, Any]]:
    response = fetch_response(url, timeout=timeout)
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError(f"{url} did not contain a JSON object")
    return response, payload


def fetch_response(url: str, *, timeout: float) -> requests.Response:
    last_response: requests.Response | None = None
    last_error: Exception | None = None
    for attempt in range(1, DEFAULT_REQUEST_ATTEMPTS + 1):
        try:
            response = requests.get(url, timeout=timeout)
        except requests.RequestException as exc:
            last_error = exc
            if attempt < DEFAULT_REQUEST_ATTEMPTS:
                time.sleep(DEFAULT_RETRY_DELAY_SECONDS)
                continue
            raise

        last_response = response
        if response.status_code not in RETRYABLE_STATUS_CODES:
            response.raise_for_status()
            return response
        if attempt < DEFAULT_REQUEST_ATTEMPTS:
            time.sleep(DEFAULT_RETRY_DELAY_SECONDS)
            continue
        response.raise_for_status()

    if last_error is not None:
        raise last_error
    if last_response is not None:
        last_response.raise_for_status()
    raise RuntimeError(f"Failed to fetch {url}")


def append_cache_bust(url: str, token: str) -> str:
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}chummer_live_sample={token}"


def top_level_manifest_view(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": normalize_optional_text(payload.get("version")),
        "publicVersion": normalize_optional_text(payload.get("publicVersion")),
        "channel": normalize_optional_text(payload.get("channelId") or payload.get("channel")),
        "rolloutState": normalize_optional_text(payload.get("rolloutState")),
        "supportabilityState": normalize_optional_text(payload.get("supportabilityState")),
        "status": normalize_optional_text(payload.get("status")),
        "publishedAt": normalize_iso(payload.get("publishedAt")),
    }


def manifest_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = payload.get("downloads")
    if isinstance(rows, list):
        return [row for row in rows if isinstance(row, dict)]
    rows = payload.get("artifacts")
    if isinstance(rows, list):
        return [row for row in rows if isinstance(row, dict)]
    return []


def normalize_url(base_url: str, value: Any) -> str:
    raw = normalize_optional_text(value)
    if not raw:
        return ""
    return urljoin(base_url.rstrip("/") + "/", raw)


def file_name_from_row(row: dict[str, Any], *, base_url: str) -> str:
    file_name = normalize_optional_text(row.get("fileName"))
    if file_name:
        return file_name
    for key in ("downloadUrl", "url"):
        raw_url = normalize_optional_text(row.get(key))
        if raw_url:
            path = urlparse(normalize_url(base_url, raw_url)).path
            return Path(path).name
    return ""


def rid_from_row(row: dict[str, Any]) -> str:
    rid = normalize_token(row.get("rid"))
    if rid:
        return rid
    platform_id = normalize_token(row.get("platformId"))
    if platform_id.startswith(("win-", "linux-", "osx-")):
        return platform_id
    arch = normalize_token(row.get("arch"))
    if platform_id and arch:
        if platform_id in {"windows", "win"}:
            return f"win-{arch}"
        if platform_id == "linux":
            return f"linux-{arch}"
        if platform_id in {"mac", "macos", "osx"}:
            return f"osx-{arch}"
    return ""


def normalized_artifact_row(row: dict[str, Any], *, base_url: str) -> dict[str, Any]:
    artifact_id = normalize_optional_text(row.get("artifactId") or row.get("id"))
    file_name = file_name_from_row(row, base_url=base_url)
    return {
        "artifactId": artifact_id,
        "fileName": file_name,
        "url": normalize_url(base_url, row.get("downloadUrl") or row.get("url")),
        "sha256": normalize_token(row.get("sha256")),
        "sizeBytes": safe_int(row.get("sizeBytes")),
        "head": normalize_token(row.get("head")),
        "rid": rid_from_row(row),
        "channel": normalize_token(row.get("channelId") or row.get("channel")),
        "installAccessClass": normalize_token(row.get("installAccessClass")),
        "installerMode": normalize_token(row.get("installerMode")),
        "kind": normalize_token(row.get("kind")),
        "payloadFileName": normalize_optional_text(row.get("payloadFileName")),
        "payloadDownloadUrl": normalize_url(base_url, row.get("payloadDownloadUrl")),
        "payloadSha256": normalize_token(row.get("payloadSha256")),
        "payloadSizeBytes": safe_int(row.get("payloadSizeBytes")),
    }


def artifact_index(payload: dict[str, Any], *, base_url: str) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for row in manifest_rows(payload):
        normalized = normalized_artifact_row(row, base_url=base_url)
        artifact_id = normalized["artifactId"] or normalized["fileName"]
        if not artifact_id:
            continue
        indexed[artifact_id] = normalized
    return indexed


def extract_page_artifact_ids(page_html: str) -> list[str]:
    matches = re.findall(r'data-download-artifact="([^"]+)"', page_html, flags=re.IGNORECASE)
    ordered: list[str] = []
    seen: set[str] = set()
    for match in matches:
        token = normalize_optional_text(match)
        if token and token not in seen:
            ordered.append(token)
            seen.add(token)
    return ordered


def compare_views(
    left_name: str,
    left_value: dict[str, Any],
    right_name: str,
    right_value: dict[str, Any],
    *,
    failures: list[str],
) -> None:
    for key in sorted(set(left_value) | set(right_value)):
        if left_value.get(key) != right_value.get(key):
            failures.append(
                f"{left_name} and {right_name} differ for {key}: {left_value.get(key)!r} != {right_value.get(key)!r}"
            )


def compare_artifact_indexes(
    left_name: str,
    left_rows: dict[str, dict[str, Any]],
    right_name: str,
    right_rows: dict[str, dict[str, Any]],
    *,
    failures: list[str],
) -> None:
    left_keys = set(left_rows)
    right_keys = set(right_rows)
    missing_from_right = sorted(left_keys - right_keys)
    missing_from_left = sorted(right_keys - left_keys)
    if missing_from_right:
        failures.append(f"{right_name} is missing artifact(s): {', '.join(missing_from_right)}")
    if missing_from_left:
        failures.append(f"{left_name} is missing artifact(s): {', '.join(missing_from_left)}")
    for artifact_id in sorted(left_keys & right_keys):
        if left_rows[artifact_id] != right_rows[artifact_id]:
            failures.append(
                f"{left_name} and {right_name} differ for artifact {artifact_id}: "
                f"{json.dumps(left_rows[artifact_id], sort_keys=True)} != {json.dumps(right_rows[artifact_id], sort_keys=True)}"
            )


def manifest_summary(payload: dict[str, Any], *, base_url: str) -> dict[str, Any]:
    rows = artifact_index(payload, base_url=base_url)
    return {
        "topLevel": top_level_manifest_view(payload),
        "artifactCount": len(rows),
        "artifactIds": sorted(rows),
        "artifacts": rows,
    }


def parse_total_size_from_content_range(value: str) -> int:
    match = re.match(r"^bytes\s+\d+-\d+/(\d+)$", value.strip(), flags=re.IGNORECASE)
    if not match:
        return 0
    return safe_int(match.group(1))


def probe_artifact_url(url: str, *, expected_size: int, timeout: float) -> dict[str, Any]:
    head_response = None
    try:
        head_response = requests.head(url, allow_redirects=True, timeout=timeout)
        head_status = head_response.status_code
        head_length = safe_int(head_response.headers.get("Content-Length"))
        if head_response.ok:
            return {
                "url": url,
                "method": "HEAD",
                "statusCode": head_status,
                "resolvedUrl": head_response.url,
                "reportedSizeBytes": head_length,
                "sizeMatches": expected_size == 0 or head_length == 0 or head_length == expected_size,
            }
    except requests.RequestException as exc:
        head_error = str(exc)
    else:
        head_error = f"HTTP {head_response.status_code}" if head_response is not None else "HEAD failed"

    try:
        get_response = requests.get(
            url,
            headers={"Range": "bytes=0-0"},
            allow_redirects=True,
            timeout=timeout,
            stream=True,
        )
        get_status = get_response.status_code
        reported_size = parse_total_size_from_content_range(get_response.headers.get("Content-Range", ""))
        if reported_size == 0:
            reported_size = safe_int(get_response.headers.get("Content-Length"))
        result = {
            "url": url,
            "method": "GET",
            "statusCode": get_status,
            "resolvedUrl": get_response.url,
            "reportedSizeBytes": reported_size,
            "sizeMatches": expected_size == 0 or reported_size == 0 or reported_size == expected_size,
        }
        get_response.close()
        return result
    except requests.RequestException as exc:
        return {
            "url": url,
            "method": "GET",
            "statusCode": 0,
            "resolvedUrl": "",
            "reportedSizeBytes": 0,
            "sizeMatches": False,
            "error": f"HEAD failed: {head_error}; GET failed: {exc}",
        }


def build_probe_plan(rows: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    probes: list[dict[str, Any]] = []
    seen: set[str] = set()
    for artifact_id, row in sorted(rows.items()):
        if row["installAccessClass"] not in {"", "open_public"}:
            continue
        if row["url"] and row["url"] not in seen:
            probes.append(
                {
                    "label": f"{artifact_id}:installer",
                    "url": row["url"],
                    "expectedSizeBytes": row["sizeBytes"],
                }
            )
            seen.add(row["url"])
        if row["payloadDownloadUrl"] and row["payloadDownloadUrl"] not in seen:
            probes.append(
                {
                    "label": f"{artifact_id}:payload",
                    "url": row["payloadDownloadUrl"],
                    "expectedSizeBytes": row["payloadSizeBytes"],
                }
            )
            seen.add(row["payloadDownloadUrl"])
    return probes


def fetch_live_snapshot(
    *,
    base_url: str,
    timeout: float,
    sample_index: int,
    cache_bust: bool,
) -> dict[str, Any]:
    downloads_url = f"{base_url}/downloads"
    releases_url = f"{base_url}/downloads/releases.json"
    canonical_url = f"{base_url}/downloads/RELEASE_CHANNEL.generated.json"
    if cache_bust:
        downloads_url = append_cache_bust(downloads_url, f"downloads-{sample_index}")
        releases_url = append_cache_bust(releases_url, f"releases-{sample_index}")
        canonical_url = append_cache_bust(canonical_url, f"canonical-{sample_index}")

    downloads_response = fetch_response(downloads_url, timeout=timeout)
    live_releases_response, live_releases_payload = fetch_json(releases_url, timeout=timeout)
    live_canonical_response, live_canonical_payload = fetch_json(canonical_url, timeout=timeout)
    return {
        "downloadsResponse": downloads_response,
        "releasesResponse": live_releases_response,
        "releasesPayload": live_releases_payload,
        "canonicalResponse": live_canonical_response,
        "canonicalPayload": live_canonical_payload,
    }


def analyze_live_snapshot(
    *,
    base_url: str,
    local_manifest_summary: dict[str, Any],
    local_canonical_summary: dict[str, Any],
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    downloads_response = snapshot["downloadsResponse"]
    live_releases_response = snapshot["releasesResponse"]
    live_releases_payload = snapshot["releasesPayload"]
    live_canonical_response = snapshot["canonicalResponse"]
    live_canonical_payload = snapshot["canonicalPayload"]

    live_manifest_summary = manifest_summary(live_releases_payload, base_url=base_url)
    live_canonical_summary = manifest_summary(live_canonical_payload, base_url=base_url)
    failures: list[str] = []

    compare_views(
        "live releases.json",
        live_manifest_summary["topLevel"],
        "live RELEASE_CHANNEL.generated.json",
        live_canonical_summary["topLevel"],
        failures=failures,
    )
    compare_views(
        "local releases.json",
        local_manifest_summary["topLevel"],
        "live releases.json",
        live_manifest_summary["topLevel"],
        failures=failures,
    )
    compare_views(
        "local RELEASE_CHANNEL.generated.json",
        local_canonical_summary["topLevel"],
        "live RELEASE_CHANNEL.generated.json",
        live_canonical_summary["topLevel"],
        failures=failures,
    )

    compare_artifact_indexes(
        "live releases.json",
        live_manifest_summary["artifacts"],
        "live RELEASE_CHANNEL.generated.json",
        live_canonical_summary["artifacts"],
        failures=failures,
    )
    compare_artifact_indexes(
        "local releases.json",
        local_manifest_summary["artifacts"],
        "live releases.json",
        live_manifest_summary["artifacts"],
        failures=failures,
    )
    compare_artifact_indexes(
        "local RELEASE_CHANNEL.generated.json",
        local_canonical_summary["artifacts"],
        "live RELEASE_CHANNEL.generated.json",
        live_canonical_summary["artifacts"],
        failures=failures,
    )

    page_artifact_ids = extract_page_artifact_ids(downloads_response.text)
    live_public_artifact_ids = sorted(
        artifact_id
        for artifact_id, row in live_manifest_summary["artifacts"].items()
        if row["installAccessClass"] in {"", "open_public"}
    )
    unknown_page_artifact_ids = sorted(set(page_artifact_ids) - set(live_manifest_summary["artifactIds"]))
    if unknown_page_artifact_ids:
        failures.append(
            "downloads page exposes artifact ids missing from live releases.json: "
            + ", ".join(unknown_page_artifact_ids)
        )
    missing_page_artifact_ids = sorted(set(live_public_artifact_ids) - set(page_artifact_ids))
    if live_public_artifact_ids and missing_page_artifact_ids:
        failures.append(
            "downloads page is missing public artifact call-to-action ids: "
            + ", ".join(missing_page_artifact_ids)
        )

    return {
        "downloadsResponse": downloads_response,
        "releasesResponse": live_releases_response,
        "canonicalResponse": live_canonical_response,
        "manifest": live_manifest_summary,
        "canonicalManifest": live_canonical_summary,
        "pageArtifactIds": page_artifact_ids,
        "publicArtifactIds": live_public_artifact_ids,
        "unknownPageArtifactIds": unknown_page_artifact_ids,
        "missingPageArtifactIds": missing_page_artifact_ids,
        "failures": failures,
    }


def evaluate(
    *,
    base_url: str,
    local_manifest_path: Path,
    local_canonical_manifest_path: Path,
    timeout: float,
    artifact_probes_enabled: bool,
    live_confirmation_count: int = 1,
    live_confirmation_delay_seconds: float = 0.0,
    live_max_samples: int = 1,
) -> dict[str, Any]:
    base = base_url.rstrip("/")
    local_manifest_payload = load_json(local_manifest_path)
    local_canonical_payload = load_json(local_canonical_manifest_path)

    local_manifest_summary = manifest_summary(local_manifest_payload, base_url=base)
    local_canonical_summary = manifest_summary(local_canonical_payload, base_url=base)

    failures: list[str] = []
    compare_views(
        "local releases.json",
        local_manifest_summary["topLevel"],
        "local RELEASE_CHANNEL.generated.json",
        local_canonical_summary["topLevel"],
        failures=failures,
    )
    compare_artifact_indexes(
        "local releases.json",
        local_manifest_summary["artifacts"],
        "local RELEASE_CHANNEL.generated.json",
        local_canonical_summary["artifacts"],
        failures=failures,
    )

    required_consecutive_matches = max(1, live_confirmation_count)
    sample_limit = max(required_consecutive_matches, live_max_samples)
    cache_bust_live_reads = sample_limit > 1
    live_analysis: dict[str, Any] | None = None
    live_confirmation_samples: list[dict[str, Any]] = []
    consecutive_matches = 0
    stabilized = False

    for sample_index in range(1, sample_limit + 1):
        snapshot = fetch_live_snapshot(
            base_url=base,
            timeout=timeout,
            sample_index=sample_index,
            cache_bust=cache_bust_live_reads,
        )
        live_analysis = analyze_live_snapshot(
            base_url=base,
            local_manifest_summary=local_manifest_summary,
            local_canonical_summary=local_canonical_summary,
            snapshot=snapshot,
        )
        sample_failures = list(live_analysis["failures"])
        matched_local_truth = len(sample_failures) == 0
        if matched_local_truth:
            consecutive_matches += 1
        else:
            consecutive_matches = 0
        live_confirmation_samples.append(
            {
                "sampleIndex": sample_index,
                "matchedLocalTruth": matched_local_truth,
                "consecutiveMatches": consecutive_matches,
                "releasesVersion": live_analysis["manifest"]["topLevel"]["version"],
                "canonicalVersion": live_analysis["canonicalManifest"]["topLevel"]["version"],
                "releasesPublishedAt": live_analysis["manifest"]["topLevel"]["publishedAt"],
                "canonicalPublishedAt": live_analysis["canonicalManifest"]["topLevel"]["publishedAt"],
                "failureCount": len(sample_failures),
                "summary": "pass" if matched_local_truth else (sample_failures[0] if sample_failures else "live sample mismatch"),
            }
        )
        if consecutive_matches >= required_consecutive_matches:
            stabilized = True
            break
        if sample_index < sample_limit and live_confirmation_delay_seconds > 0:
            time.sleep(live_confirmation_delay_seconds)

    if live_analysis is None:
        raise RuntimeError("no live download shelf snapshot was captured")

    failures.extend(live_analysis["failures"])
    if not stabilized:
        failures.append(
            "live shelf never matched local manifests for "
            f"{required_consecutive_matches} consecutive sample(s) within {sample_limit} sample(s)"
        )

    downloads_response = live_analysis["downloadsResponse"]
    live_releases_response = live_analysis["releasesResponse"]
    live_canonical_response = live_analysis["canonicalResponse"]
    live_manifest_summary = live_analysis["manifest"]
    live_canonical_summary = live_analysis["canonicalManifest"]
    page_artifact_ids = live_analysis["pageArtifactIds"]
    live_public_artifact_ids = live_analysis["publicArtifactIds"]
    unknown_page_artifact_ids = live_analysis["unknownPageArtifactIds"]
    missing_page_artifact_ids = live_analysis["missingPageArtifactIds"]

    artifact_probes: list[dict[str, Any]] = []
    if artifact_probes_enabled:
        for probe in build_probe_plan(live_manifest_summary["artifacts"]):
            result = probe_artifact_url(
                probe["url"],
                expected_size=safe_int(probe["expectedSizeBytes"]),
                timeout=timeout,
            )
            result["label"] = probe["label"]
            artifact_probes.append(result)
            if result["statusCode"] < 200 or result["statusCode"] >= 300:
                failures.append(f"artifact probe failed for {probe['label']}: HTTP {result['statusCode']}")
            elif not result["sizeMatches"]:
                failures.append(
                    f"artifact probe size mismatch for {probe['label']}: "
                    f"reported {result['reportedSizeBytes']} vs expected {probe['expectedSizeBytes']}"
                )

    payload = {
        "generated_at_utc": now_iso(),
        "contract_name": "chummer.public_download_shelf_truth",
        "base_url": base,
        "status": "fail" if failures else "pass",
        "local": {
            "manifestPath": str(local_manifest_path),
            "canonicalManifestPath": str(local_canonical_manifest_path),
            "manifest": local_manifest_summary,
            "canonicalManifest": local_canonical_summary,
        },
        "live": {
            "downloadsStatusCode": downloads_response.status_code,
            "releasesStatusCode": live_releases_response.status_code,
            "canonicalStatusCode": live_canonical_response.status_code,
            "manifest": live_manifest_summary,
            "canonicalManifest": live_canonical_summary,
            "pageArtifactIds": page_artifact_ids,
            "publicArtifactIds": live_public_artifact_ids,
            "confirmation": {
                "requiredConsecutiveMatches": required_consecutive_matches,
                "delaySeconds": live_confirmation_delay_seconds,
                "maxSamples": sample_limit,
                "samplesObserved": len(live_confirmation_samples),
                "stabilized": stabilized,
                "samples": live_confirmation_samples,
            },
            "artifactProbes": artifact_probes,
        },
        "alignment": {
            "localManifestsAligned": (
                local_manifest_summary["topLevel"] == local_canonical_summary["topLevel"]
                and local_manifest_summary["artifacts"] == local_canonical_summary["artifacts"]
            ),
            "liveManifestsAligned": (
                live_manifest_summary["topLevel"] == live_canonical_summary["topLevel"]
                and live_manifest_summary["artifacts"] == live_canonical_summary["artifacts"]
            ),
            "localMatchesLive": (
                local_manifest_summary == live_manifest_summary
                and local_canonical_summary == live_canonical_summary
            ),
            "pageArtifactIdsAligned": not unknown_page_artifact_ids and not missing_page_artifact_ids,
            "artifactProbesPassed": all(
                probe["statusCode"] in range(200, 300) and probe["sizeMatches"]
                for probe in artifact_probes
            ),
        },
        "failures": failures,
        "summary": "pass: public download shelf truth is aligned" if not failures else "fail: " + "; ".join(failures),
    }
    return payload


def main() -> int:
    args = parse_args()
    payload = evaluate(
        base_url=args.base_url,
        local_manifest_path=Path(args.local_manifest),
        local_canonical_manifest_path=Path(args.local_canonical_manifest),
        timeout=args.timeout,
        artifact_probes_enabled=not args.skip_artifact_probes,
        live_confirmation_count=args.live_confirmation_count,
        live_confirmation_delay_seconds=args.live_confirmation_delay_seconds,
        live_max_samples=args.live_max_samples,
    )
    for out_path in OUT_PATHS:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload))
    return 0 if payload["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
