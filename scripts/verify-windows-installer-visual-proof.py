#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


PASSING_STATUSES = {"pass", "passed", "ready"}
REQUIRED_ROLES = {"progress", "completion"}
REQUIRED_AUDIT_SURFACES = {"install-progress", "completion"}
REQUIRED_AUDIT_DPI_SCALES = {"1.0", "1.5"}
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VISUAL_PROOF_HINT = Path(
    os.environ.get(
        "CHUMMER_WINDOWS_INSTALLER_VISUAL_PROOF_PATH",
        "/docker/chummercomplete/chummer6-ui/.codex-studio/published/WINDOWS_INSTALLER_VISUAL_PROOF.generated.json",
    )
)
DEFAULT_VISUAL_AUDIT_HINT = Path(
    os.environ.get(
        "CHUMMER_WINDOWS_VISUAL_AUDIT_PUBLISHED_PATH",
        str(REPO_ROOT / ".codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json"),
    )
)


@dataclass(frozen=True)
class ManifestRow:
    artifact_id: str
    file_name: str
    version: str
    channel: str
    head: str
    rid: str
    sha256: str


def normalize_token(value: Any) -> str:
    return str(value or "").strip().lower()


def is_windows_installer_name(name: str) -> bool:
    lowered = name.lower()
    return lowered.startswith("chummer-") and lowered.endswith("-win-x64-installer.exe") or (
        lowered.startswith("chummer-") and "-win-" in lowered and lowered.endswith("-installer.exe")
    )


def resolve_file_name(item: dict[str, Any]) -> str:
    file_name = str(item.get("fileName") or "").strip()
    if file_name:
        return file_name
    raw_url = str(item.get("downloadUrl") or item.get("url") or "").strip()
    return Path(urlparse(raw_url).path).name if raw_url else ""


def infer_head_id(installer_name: str) -> str:
    lowered = installer_name.lower()
    if lowered.startswith("chummer-blazor-desktop-"):
        return "blazor-desktop"
    if lowered.startswith("chummer-avalonia-"):
        return "avalonia"
    return ""


def infer_rid(installer_name: str) -> str:
    lowered = installer_name.lower()
    suffix = "-installer.exe"
    if not lowered.endswith(suffix):
        return ""
    stem = lowered[: -len(suffix)]
    marker = stem.rfind("-win-")
    if marker < 0:
        return ""
    return stem[marker + 1 :]


def read_manifest_rows(manifest_paths: list[Path]) -> dict[str, ManifestRow]:
    rows: dict[str, ManifestRow] = {}
    for manifest_path in manifest_paths:
        if not manifest_path.is_file():
            continue
        payload = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        if not isinstance(payload, dict):
            continue
        version = str(payload.get("version") or payload.get("releaseVersion") or "").strip()
        channel = str(payload.get("channel") or "").strip()
        for collection_name in ("artifacts", "downloads"):
            collection = payload.get(collection_name)
            if not isinstance(collection, list):
                continue
            for item in collection:
                if not isinstance(item, dict):
                    continue
                file_name = resolve_file_name(item)
                if not file_name or not is_windows_installer_name(file_name):
                    continue
                rows[file_name] = ManifestRow(
                    artifact_id=str(item.get("artifactId") or item.get("id") or "").strip(),
                    file_name=file_name,
                    version=str(item.get("version") or version or "").strip(),
                    channel=str(item.get("channel") or channel or "").strip(),
                    head=str(item.get("head") or "").strip(),
                    rid=str(item.get("rid") or "").strip(),
                    sha256=str(item.get("sha256") or item.get("artifactSha256") or "").strip(),
                )
    return rows


def find_installers(files_dir: Path | None, explicit_installers: list[Path]) -> list[Path]:
    installers: list[Path] = [path.resolve() for path in explicit_installers]
    if files_dir is not None and files_dir.is_dir():
        installers.extend(sorted(path.resolve() for path in files_dir.glob("chummer-*-win-*-installer.exe")))
    seen: set[Path] = set()
    unique: list[Path] = []
    for installer in installers:
        if installer in seen:
            continue
        seen.add(installer)
        unique.append(installer)
    return unique


def split_tokens(value: str | None) -> set[str]:
    tokens: set[str] = set()
    for raw in str(value or "").replace(";", ",").replace("\n", ",").split(","):
        for token in raw.split():
            token = token.strip().lower()
            if token:
                tokens.add(token)
    return tokens


def is_disabled_installer(installer_path: Path, manifest_row: ManifestRow | None, disabled_tokens: set[str]) -> bool:
    if not disabled_tokens:
        return False

    candidates = {installer_path.name.lower()}
    if manifest_row is not None:
        for value in (manifest_row.artifact_id, manifest_row.file_name):
            value = str(value or "").strip().lower()
            if value:
                candidates.add(value)
    return any(token in candidates for token in disabled_tokens)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().lower()


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} is not a JSON object")
    return payload


def screenshot_map(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    screenshots = payload.get("screenshots")
    mapped: dict[str, dict[str, Any]] = {}
    if not isinstance(screenshots, list):
        return mapped
    for item in screenshots:
        if not isinstance(item, dict):
            continue
        role = normalize_token(item.get("role"))
        if role:
            mapped[role] = item
    return mapped


def status_is_passing(value: Any) -> bool:
    return normalize_token(value) in PASSING_STATUSES


def nested_status(payload: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, dict):
            status = str(value.get("status") or "").strip()
            if status:
                return status
    return ""


def parse_iso_utc(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def normalize_digest(value: Any) -> str:
    digest = normalize_token(value)
    if digest and not digest.startswith("sha256:") and len(digest) == 64 and all(char in "0123456789abcdef" for char in digest):
        return f"sha256:{digest}"
    return digest


def visual_proof_candidate_timestamp(payload: dict[str, Any], path: Path) -> float:
    for key in ("generated_at", "generatedAt", "recordedAtUtc", "completedAtUtc"):
        parsed = parse_iso_utc(payload.get(key))
        if parsed is not None:
            return parsed.timestamp()
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def visual_proof_matches_expected_release(
    payload: dict[str, Any],
    *,
    expected_head: str,
    expected_rid: str,
    expected_version: str,
    expected_digest: str,
) -> bool:
    contract = str(payload.get("contractName") or payload.get("contract_name") or "").strip()
    if contract != "chummer6-ui.windows_installer_visual_proof":
        return False
    if not status_is_passing(payload.get("status")):
        return False

    visual_head = normalize_token(payload.get("headId") or payload.get("head"))
    if expected_head and visual_head and visual_head != expected_head:
        return False

    visual_rid = normalize_token(payload.get("rid"))
    if expected_rid and visual_rid and visual_rid != expected_rid:
        return False

    visual_version = str(payload.get("releaseVersion") or payload.get("version") or "").strip()
    if expected_version and visual_version and visual_version != expected_version:
        return False

    visual_digest = normalize_digest(
        payload.get("artifactDigest") or payload.get("installerDigest") or payload.get("installerSha256")
    )
    if expected_digest and visual_digest != expected_digest:
        return False

    return True


def select_visual_proof_path(
    candidates: list[Path],
    *,
    installer_path: Path,
    manifest_row: ManifestRow | None,
) -> Path | None:
    expected_head = (manifest_row.head if manifest_row is not None and manifest_row.head else infer_head_id(installer_path.name)).strip().lower()
    expected_rid = (manifest_row.rid if manifest_row is not None and manifest_row.rid else infer_rid(installer_path.name)).strip().lower()
    expected_version = manifest_row.version.strip() if manifest_row is not None else ""
    expected_digest = f"sha256:{sha256_file(installer_path)}" if installer_path.is_file() else ""
    best_path: Path | None = None
    best_score: tuple[int, int, int, int, int, float] | None = None

    for candidate in candidates:
        if not candidate.is_file():
            continue
        try:
            payload = load_json(candidate)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if not visual_proof_matches_expected_release(
            payload,
            expected_head=expected_head,
            expected_rid=expected_rid,
            expected_version=expected_version,
            expected_digest=expected_digest,
        ):
            continue
        score = (
            int(normalize_token(payload.get("headId") or payload.get("head")) == expected_head) if expected_head else 1,
            int(normalize_token(payload.get("rid")) == expected_rid) if expected_rid else 1,
            int(str(payload.get("releaseVersion") or payload.get("version") or "").strip() == expected_version)
            if expected_version
            else 1,
            int(bool(str(payload.get("headId") or payload.get("head") or "").strip())),
            int(bool(str(payload.get("releaseVersion") or payload.get("version") or "").strip())),
            visual_proof_candidate_timestamp(payload, candidate),
        )
        if best_score is None or score > best_score:
            best_score = score
            best_path = candidate

    return best_path


def verify_installer(installer_path: Path, manifest_row: ManifestRow | None, visual_proof_path: Path) -> list[str]:
    failures: list[str] = []
    if not installer_path.is_file():
        return [f"installer does not exist: {installer_path}"]

    if manifest_row is None:
        failures.append("Windows installer is missing from the supplied release manifest")

    if not visual_proof_path.is_file():
        return ["Windows installer visual proof is missing; capture progress and completion screenshots on a Windows host."]

    payload = load_json(visual_proof_path)
    contract = str(payload.get("contractName") or payload.get("contract_name") or "").strip()
    if contract != "chummer6-ui.windows_installer_visual_proof":
        failures.append("Windows installer visual proof contract is not chummer6-ui.windows_installer_visual_proof.")

    status = str(payload.get("status") or "").strip()
    if not status_is_passing(status):
        failures.append("Windows installer visual proof status is not passing.")

    expected_head = (manifest_row.head if manifest_row is not None and manifest_row.head else infer_head_id(installer_path.name)).strip()
    expected_rid = (manifest_row.rid if manifest_row is not None and manifest_row.rid else infer_rid(installer_path.name)).strip()
    expected_version = manifest_row.version.strip() if manifest_row is not None else ""
    expected_digest = f"sha256:{sha256_file(installer_path)}"

    visual_head = str(payload.get("headId") or payload.get("head") or "").strip()
    visual_rid = str(payload.get("rid") or "").strip()
    visual_version = str(payload.get("releaseVersion") or payload.get("version") or "").strip()
    visual_digest = str(payload.get("artifactDigest") or payload.get("installerDigest") or "").strip().lower()

    if expected_head and visual_head and visual_head != expected_head:
        failures.append(f"Windows installer visual proof head does not match promoted head {expected_head}.")
    if expected_rid and visual_rid and visual_rid != expected_rid:
        failures.append(f"Windows installer visual proof rid does not match promoted RID {expected_rid}.")
    if expected_version and visual_version and visual_version != expected_version:
        failures.append("Windows installer visual proof version does not match release channel.")
    if visual_digest != expected_digest:
        failures.append("Windows installer visual proof artifactDigest does not match promoted installer bytes.")

    screenshots = screenshot_map(payload)
    missing_roles = sorted(REQUIRED_ROLES - set(screenshots))
    if missing_roles:
        failures.append(
            "Windows installer visual proof is missing required screenshot roles: "
            + ", ".join(missing_roles)
            + "."
        )

    missing_files: list[str] = []
    missing_digests: list[str] = []
    distinct_digests: set[str] = set()
    for role in sorted(REQUIRED_ROLES & set(screenshots)):
        shot = screenshots[role]
        shot_path = Path(str(shot.get("path") or "").strip())
        if not shot_path.is_file():
            missing_files.append(role)
            continue
        digest = str(shot.get("imageDigest") or "").strip().lower()
        if not digest:
            raw_sha = str(shot.get("sha256") or shot.get("imageSha256") or "").strip().lower()
            digest = f"sha256:{raw_sha}" if raw_sha else ""
        if not digest:
            missing_digests.append(role)
        else:
            distinct_digests.add(digest)
            actual_digest = f"sha256:{sha256_file(shot_path)}"
            if actual_digest != digest:
                failures.append(
                    "Windows installer visual proof screenshot digests do not match the referenced files for: "
                    + role
                    + "."
                )
    if missing_files:
        failures.append(
            "Windows installer visual proof screenshot files are missing for: "
            + ", ".join(missing_files)
            + "."
        )
    if missing_digests:
        failures.append(
            "Windows installer visual proof screenshots are missing image digests for: "
            + ", ".join(missing_digests)
            + "."
        )
    if not missing_roles and not missing_files and len(distinct_digests) < len(REQUIRED_ROLES):
        failures.append("Windows installer visual proof screenshots are not distinct across progress and completion.")

    for review_name, review_status in (
        ("readability", nested_status(payload, "readabilityReview", "textReadabilityReview", "readability")),
        ("contrast", nested_status(payload, "contrastReview", "contrast")),
        ("clipping", nested_status(payload, "clippingReview", "clipping")),
    ):
        if not status_is_passing(review_status):
            failures.append(f"Windows installer visual proof {review_name} review is not passing.")

    return failures


def exact_nonnegative_integer(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def referenced_path(value: Any, receipt_path: Path) -> Path:
    path = Path(str(value or "").strip())
    if not path.is_absolute():
        path = receipt_path.parent / path
    return path


def verify_visual_audit(
    installer_path: Path,
    manifest_row: ManifestRow | None,
    visual_audit_path: Path,
) -> list[str]:
    failures: list[str] = []
    if not visual_audit_path.is_file():
        return ["Windows installer visual audit is missing."]
    try:
        payload = load_json(visual_audit_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [f"Windows installer visual audit could not be loaded: {exc}"]

    if not installer_path.is_file():
        return [f"installer does not exist: {installer_path}"]
    expected_digest = f"sha256:{sha256_file(installer_path)}"
    expected_version = manifest_row.version if manifest_row is not None else ""
    expected_channel = manifest_row.channel if manifest_row is not None else ""
    expected_artifact_id = manifest_row.artifact_id if manifest_row is not None else ""
    expected_manifest_digest = normalize_digest(manifest_row.sha256 if manifest_row is not None else "")

    if manifest_row is None:
        failures.append("Windows installer visual audit cannot be accepted without a manifest row.")
    if not expected_manifest_digest:
        failures.append("Windows installer visual audit requires the promoted manifest digest.")
    elif expected_manifest_digest != expected_digest:
        failures.append("Windows installer bytes do not match the promoted manifest digest.")

    contract = str(payload.get("contract_name") or payload.get("contractName") or "").strip()
    if contract != "chummer.windows_installer_visual_audit":
        failures.append("Windows installer visual audit contract is not chummer.windows_installer_visual_audit.")
    if not status_is_passing(payload.get("status")):
        failures.append("Windows installer visual audit status is not passing.")
    receipt_failures = payload.get("failures")
    if not isinstance(receipt_failures, list) or receipt_failures:
        failures.append("Windows installer visual audit has unresolved failures.")

    for field in (
        "required_promoted_digest",
        "actual_artifact_sha256",
        "manifest_promoted_digest",
        "source_digest",
    ):
        if normalize_digest(payload.get(field)) != expected_digest:
            failures.append(f"Windows installer visual audit {field} does not match promoted installer bytes.")
    if payload.get("source_digest_matches_promoted") is not True:
        failures.append("Windows installer visual audit source digest is not explicitly matched to promotion.")

    release = payload.get("release")
    if not isinstance(release, dict):
        failures.append("Windows installer visual audit release lineage is missing.")
    else:
        if normalize_token(release.get("loadStatus")) != "loaded":
            failures.append("Windows installer visual audit release lineage was not loaded.")
        if not expected_version or str(release.get("version") or "").strip() != expected_version:
            failures.append("Windows installer visual audit version does not match release channel.")
        if not expected_channel or str(release.get("channel") or "").strip() != expected_channel:
            failures.append("Windows installer visual audit channel does not match release channel.")

    artifact = payload.get("artifact")
    if not isinstance(artifact, dict):
        failures.append("Windows installer visual audit artifact lineage is missing.")
    else:
        if expected_artifact_id and str(artifact.get("artifactId") or "").strip() != expected_artifact_id:
            failures.append("Windows installer visual audit artifact id does not match the manifest.")
        if str(artifact.get("fileName") or "").strip() != installer_path.name:
            failures.append("Windows installer visual audit file name does not match the promoted installer.")
        for field in ("sha256", "actualSha256", "effectiveSha256"):
            if normalize_digest(artifact.get(field)) != expected_digest:
                failures.append(f"Windows installer visual audit artifact {field} does not match promotion.")
        artifact_path = referenced_path(artifact.get("path"), visual_audit_path)
        if not artifact_path.is_file() or normalize_digest(sha256_file(artifact_path) if artifact_path.is_file() else "") != expected_digest:
            failures.append("Windows installer visual audit referenced artifact bytes are missing or mismatched.")

    startup_receipt = payload.get("startupReceipt")
    if not isinstance(startup_receipt, dict):
        failures.append("Windows installer visual audit startup receipt lineage is missing.")
    else:
        if startup_receipt.get("exists") is not True or normalize_token(startup_receipt.get("loadStatus")) != "loaded":
            failures.append("Windows installer visual audit startup receipt is not loaded.")
        if not status_is_passing(startup_receipt.get("status")):
            failures.append("Windows installer visual audit startup receipt is not passing.")
        if startup_receipt.get("artifactDigestMatchesPromoted") is not True:
            failures.append("Windows installer visual audit startup receipt is not bound to promotion.")
        if normalize_digest(startup_receipt.get("artifactDigest")) != expected_digest:
            failures.append("Windows installer visual audit startup receipt digest does not match promotion.")
        startup_path = referenced_path(startup_receipt.get("path"), visual_audit_path)
        if not startup_path.is_file():
            failures.append("Windows installer visual audit startup receipt file is missing.")
        else:
            try:
                startup_payload = load_json(startup_path)
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                failures.append(f"Windows installer visual audit startup receipt file could not be loaded: {exc}")
            else:
                if not status_is_passing(startup_payload.get("status")):
                    failures.append("Windows installer visual audit referenced startup receipt is not passing.")
                if normalize_digest(startup_payload.get("artifactDigest")) != expected_digest:
                    failures.append("Windows installer visual audit referenced startup receipt digest is stale.")
                if str(startup_payload.get("releaseVersion") or startup_payload.get("version") or "").strip() != expected_version:
                    failures.append("Windows installer visual audit referenced startup receipt version is stale.")
                if str(startup_payload.get("channel") or startup_payload.get("channelId") or "").strip() != expected_channel:
                    failures.append("Windows installer visual audit referenced startup receipt channel is stale.")

    source = payload.get("visualAuditSource")
    source_screenshot_count: int | None = None
    source_screenshot_names: set[str] = set()
    if not isinstance(source, dict):
        failures.append("Windows installer visual audit source lineage is missing.")
    else:
        if source.get("exists") is not True or normalize_token(source.get("loadStatus")) != "loaded":
            failures.append("Windows installer visual audit source was not loaded.")
        if not status_is_passing(source.get("status")):
            failures.append("Windows installer visual audit source status is not passing.")
        if normalize_token(source.get("platform")) != "windows":
            failures.append("Windows installer visual audit source platform is not Windows.")
        if not normalize_token(source.get("hostClass")).startswith("native-windows"):
            failures.append("Windows installer visual audit source host is not native Windows.")
        if source.get("artifactDigestMatchesPromoted") is not True:
            failures.append("Windows installer visual audit source is not explicitly bound to promotion.")
        if normalize_digest(source.get("artifactSha256")) != expected_digest:
            failures.append("Windows installer visual audit source digest does not match promotion.")
        if source.get("requiresRecapture") is not False:
            failures.append("Windows installer visual audit still requires recapture.")
        required_surfaces = {
            normalize_token(value) for value in source.get("requiredSurfaces", [])
        } if isinstance(source.get("requiredSurfaces"), list) else set()
        if not REQUIRED_AUDIT_SURFACES.issubset(required_surfaces):
            failures.append("Windows installer visual audit source omits a required surface.")
        source_screenshot_count = exact_nonnegative_integer(source.get("screenshotCount"))
        if source_screenshot_count is None or source_screenshot_count < 4:
            failures.append("Windows installer visual audit source does not attest at least four screenshots.")
        source_path = referenced_path(source.get("path"), visual_audit_path)
        if not source_path.is_file():
            failures.append("Windows installer visual audit source receipt file is missing.")
        else:
            try:
                source_payload = load_json(source_path)
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                failures.append(f"Windows installer visual audit source receipt could not be loaded: {exc}")
            else:
                if str(source_payload.get("contract_name") or source_payload.get("contractName") or "").strip() != "chummer.windows_installer_visual_audit.source":
                    failures.append("Windows installer visual audit source receipt contract is invalid.")
                if not status_is_passing(source_payload.get("status")):
                    failures.append("Windows installer visual audit source receipt is not passing.")
                if normalize_token(source_payload.get("platform")) != "windows":
                    failures.append("Windows installer visual audit source receipt platform is not Windows.")
                if not normalize_token(source_payload.get("hostClass")).startswith("native-windows"):
                    failures.append("Windows installer visual audit source receipt host is not native Windows.")
                if normalize_digest(source_payload.get("artifactSha256")) != expected_digest:
                    failures.append("Windows installer visual audit source receipt digest is stale.")
                source_surfaces = {
                    normalize_token(value) for value in source_payload.get("requiredSurfaces", [])
                } if isinstance(source_payload.get("requiredSurfaces"), list) else set()
                if not REQUIRED_AUDIT_SURFACES.issubset(source_surfaces):
                    failures.append("Windows installer visual audit source receipt omits a required surface.")
                source_screenshots = source_payload.get("screenshots")
                if not isinstance(source_screenshots, list) or len(source_screenshots) < 4:
                    failures.append("Windows installer visual audit source receipt lacks four screenshots.")
                else:
                    source_combinations: set[tuple[str, str]] = set()
                    for index, source_screenshot in enumerate(source_screenshots):
                        if not isinstance(source_screenshot, dict):
                            failures.append(f"Windows installer visual audit source screenshot[{index}] is invalid.")
                            continue
                        source_surface = normalize_token(source_screenshot.get("surface"))
                        source_dpi = str(source_screenshot.get("dpiScale") or "").strip()
                        source_combinations.add((source_surface, source_dpi))
                        if not normalize_token(source_screenshot.get("hostClass")).startswith("native-windows"):
                            failures.append(f"Windows installer visual audit source screenshot[{index}] is not native Windows.")
                        if not status_is_passing(source_screenshot.get("clippingStatus")):
                            failures.append(f"Windows installer visual audit source screenshot[{index}] clipping review is not passing.")
                        if not status_is_passing(source_screenshot.get("readabilityStatus")):
                            failures.append(f"Windows installer visual audit source screenshot[{index}] readability review is not passing.")
                        source_image_path = referenced_path(source_screenshot.get("path"), source_path)
                        if not source_image_path.is_file():
                            failures.append(f"Windows installer visual audit source screenshot[{index}] file is missing.")
                        else:
                            source_screenshot_names.add(source_image_path.name)
                    required_combinations = {
                        (surface, dpi)
                        for surface in REQUIRED_AUDIT_SURFACES
                        for dpi in REQUIRED_AUDIT_DPI_SCALES
                    }
                    if not required_combinations.issubset(source_combinations):
                        failures.append("Windows installer visual audit source receipt lacks required surface/DPI coverage.")

    screenshots = payload.get("screenshots")
    if not isinstance(screenshots, list) or len(screenshots) < 4:
        failures.append("Windows installer visual audit does not contain at least four screenshots.")
        screenshots = []
    if source_screenshot_count is not None and source_screenshot_count != len(screenshots):
        failures.append("Windows installer visual audit screenshot count does not match its source receipt.")

    combinations: set[tuple[str, str]] = set()
    default_dpi_count = 0
    scaled_dpi_count = 0
    audit_screenshot_names: set[str] = set()
    for index, screenshot in enumerate(screenshots):
        label = f"screenshot[{index}]"
        if not isinstance(screenshot, dict):
            failures.append(f"Windows installer visual audit {label} is not an object.")
            continue
        surface = normalize_token(screenshot.get("canonicalSurface") or screenshot.get("surface"))
        dpi_scale = str(screenshot.get("dpiScale") or "").strip()
        combinations.add((surface, dpi_scale))
        if dpi_scale == "1.0":
            default_dpi_count += 1
        elif dpi_scale == "1.5":
            scaled_dpi_count += 1
        if not normalize_token(screenshot.get("hostClass")).startswith("native-windows"):
            failures.append(f"Windows installer visual audit {label} was not captured on native Windows.")
        if screenshot.get("exists") is not True:
            failures.append(f"Windows installer visual audit {label} is not explicitly present.")
        screenshot_path = referenced_path(screenshot.get("path"), visual_audit_path)
        if not screenshot_path.is_file():
            failures.append(f"Windows installer visual audit {label} file is missing.")
        else:
            audit_screenshot_names.add(screenshot_path.name)
            expected_screenshot_digest = normalize_digest(screenshot.get("sha256"))
            actual_screenshot_digest = f"sha256:{sha256_file(screenshot_path)}"
            if not expected_screenshot_digest or expected_screenshot_digest != actual_screenshot_digest:
                failures.append(f"Windows installer visual audit {label} digest does not match its file.")
        if not status_is_passing(screenshot.get("clippingStatus")):
            failures.append(f"Windows installer visual audit {label} clipping review is not passing.")
        if not status_is_passing(screenshot.get("readabilityStatus")):
            failures.append(f"Windows installer visual audit {label} readability review is not passing.")

    missing_combinations = sorted(
        (surface, dpi)
        for surface in REQUIRED_AUDIT_SURFACES
        for dpi in REQUIRED_AUDIT_DPI_SCALES
        if (surface, dpi) not in combinations
    )
    if missing_combinations:
        rendered = ", ".join(f"{surface}@{dpi}" for surface, dpi in missing_combinations)
        failures.append(f"Windows installer visual audit is missing required surface/DPI evidence: {rendered}.")
    if isinstance(source, dict):
        if exact_nonnegative_integer(source.get("defaultDpiScreenshotCount")) != default_dpi_count:
            failures.append("Windows installer visual audit default-DPI count is inconsistent.")
        if exact_nonnegative_integer(source.get("scaledDpiScreenshotCount")) != scaled_dpi_count:
            failures.append("Windows installer visual audit scaled-DPI count is inconsistent.")
    if source_screenshot_names and audit_screenshot_names != source_screenshot_names:
        failures.append("Windows installer visual audit screenshots do not match the source receipt files.")

    return failures


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fail if a promoted Windows Chummer installer lacks a matching passing visual-proof receipt."
    )
    parser.add_argument("--files-dir", type=Path, help="Bundle files directory containing installers.")
    parser.add_argument("--manifest", type=Path, action="append", default=[], help="Release manifest to cross-check version/head/rid.")
    parser.add_argument("--installer", type=Path, action="append", default=[], help="Specific installer .exe to check.")
    parser.add_argument("--visual-proof", type=Path, help="Path to WINDOWS_INSTALLER_VISUAL_PROOF.generated.json.")
    parser.add_argument("--visual-audit", type=Path, help="Path to the stronger WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json receipt.")
    parser.add_argument("--disabled-artifact-id", action="append", default=[], help="Skip a quarantined Windows installer artifact id or file name.")
    parser.add_argument("--allow-empty", action="store_true", help="Pass when no Windows installers are present.")
    args = parser.parse_args()

    files_dir = args.files_dir.resolve() if args.files_dir else None
    manifest_paths = [path.resolve() for path in args.manifest]
    manifest_rows = read_manifest_rows(manifest_paths)
    disabled_tokens: set[str] = set()
    for value in args.disabled_artifact_id:
        disabled_tokens.update(split_tokens(value))
    disabled_tokens.update(split_tokens(os.environ.get("CHUMMER_PUBLIC_DISABLED_ARTIFACT_IDS")))
    disabled_tokens.update(split_tokens(os.environ.get("CHUMMER_RELEASE_DISABLED_ARTIFACT_IDS")))
    installers = [
        installer
        for installer in find_installers(files_dir, args.installer)
        if not is_disabled_installer(installer, manifest_rows.get(installer.name), disabled_tokens)
    ]
    if not installers:
        if args.allow_empty:
            print("windows_installer_visual_proof_gate:ok no_windows_installers")
            return 0
        print("windows_installer_visual_proof_gate:fail no Windows installers found", file=sys.stderr)
        return 1

    if args.visual_proof is not None:
        visual_proof_path = args.visual_proof.resolve()
    else:
        visual_proof_candidates: list[Path] = []
        if files_dir is not None:
            visual_proof_candidates.extend(
                [
                    files_dir.parent / "WINDOWS_INSTALLER_VISUAL_PROOF.generated.json",
                    files_dir.parent.parent / "WINDOWS_INSTALLER_VISUAL_PROOF.generated.json",
                ]
            )
        for manifest_path in manifest_paths:
            visual_proof_candidates.extend(
                [
                    manifest_path.parent / "WINDOWS_INSTALLER_VISUAL_PROOF.generated.json",
                    manifest_path.parent.parent / "WINDOWS_INSTALLER_VISUAL_PROOF.generated.json",
                ]
            )
        visual_proof_candidates.append(DEFAULT_VISUAL_PROOF_HINT.resolve())
        deduped_candidates = list(dict.fromkeys(visual_proof_candidates))
        visual_proof_path = select_visual_proof_path(
            deduped_candidates,
            installer_path=installers[0],
            manifest_row=manifest_rows.get(installers[0].name),
        ) or deduped_candidates[0]
    visual_audit_path = (
        args.visual_audit.resolve()
        if args.visual_audit is not None
        else DEFAULT_VISUAL_AUDIT_HINT.resolve()
    )
    failures: list[str] = []
    legacy_evidence_count = 0
    audit_evidence_count = 0
    for installer_path in installers:
        manifest_row = manifest_rows.get(installer_path.name)
        try:
            legacy_failures = verify_installer(installer_path, manifest_row, visual_proof_path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            legacy_failures = [f"Windows installer visual proof could not be loaded: {exc}"]
        if not legacy_failures:
            legacy_evidence_count += 1
            continue

        audit_failures = verify_visual_audit(installer_path, manifest_row, visual_audit_path)
        if not audit_failures:
            audit_evidence_count += 1
            continue

        failures.extend(f"{installer_path.name}: {failure}" for failure in legacy_failures)
        failures.extend(
            f"{installer_path.name}: stronger audit: {failure}" for failure in audit_failures
        )

    if failures:
        print("windows_installer_visual_proof_gate:fail", file=sys.stderr)
        for failure in failures:
            print(f" - {failure}", file=sys.stderr)
        return 1

    print(
        "windows_installer_visual_proof_gate:ok "
        f"checked={len(installers)} legacy={legacy_evidence_count} visual_audit={audit_evidence_count}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
