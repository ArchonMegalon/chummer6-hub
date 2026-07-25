#!/usr/bin/env python3
"""Stage only release evidence that is already bound to one manifest identity.

This helper intentionally does not repair, restamp, or synthesize proof.  It is
used by the public-download bundle materializer before any persistent shelf
write so evidence from another release cannot be made to look current.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Sequence


UTC = dt.timezone.utc
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SAFE_TOKEN_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
PASS_STATUSES = {"pass", "passed", "ready"}
PROMOTION_PASS_STATUSES = PASS_STATUSES | {"promoted"}


class CandidateEvidenceError(ValueError):
    """Raised when candidate evidence is not exactly release-bound."""


@dataclass(frozen=True)
class ExpectedArtifact:
    artifact_id: str
    head: str
    platform: str
    rid: str
    file_name: str
    sha256: str
    size_bytes: int
    receipt_name: str


def _read_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise CandidateEvidenceError(f"{label} is missing or invalid JSON: {path}") from error
    if not isinstance(payload, dict):
        raise CandidateEvidenceError(f"{label} JSON root must be an object: {path}")
    return payload


def _normalize_digest(value: Any) -> str:
    digest = str(value or "").strip().lower()
    if digest.startswith("sha256:"):
        digest = digest[len("sha256:") :]
    return digest


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalize_platform(value: Any) -> str:
    platform = str(value or "").strip().lower()
    return "macos" if platform in {"mac", "osx", "darwin"} else platform


def _require_safe_token(value: Any, *, label: str) -> str:
    token = str(value or "").strip().lower()
    if not SAFE_TOKEN_RE.fullmatch(token):
        raise CandidateEvidenceError(f"{label} is missing or unsafe: {value!r}")
    return token


def _require_file_name(value: Any, *, label: str) -> str:
    raw = str(value or "").strip()
    if not raw or Path(raw).name != raw or raw in {".", ".."}:
        raise CandidateEvidenceError(f"{label} is missing or unsafe: {value!r}")
    return raw


def _parse_iso(value: Any) -> dt.datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(UTC)


def _recorded_at(payload: dict[str, Any], path: Path) -> float:
    for key in ("recordedAtUtc", "completedAtUtc", "generated_at_utc", "generatedAt", "generated_at"):
        parsed = _parse_iso(payload.get(key))
        if parsed is not None:
            return parsed.timestamp()
    return path.stat().st_mtime


def _alias_values(
    payload: dict[str, Any],
    keys: Iterable[str],
    *,
    transform=lambda value: str(value or "").strip(),
) -> list[str]:
    return [
        transform(payload.get(key))
        for key in keys
        if key in payload and transform(payload.get(key))
    ]


def _require_alias_identity(
    payload: dict[str, Any],
    keys: Sequence[str],
    expected: str,
    *,
    label: str,
    transform=lambda value: str(value or "").strip(),
) -> None:
    values = _alias_values(payload, keys, transform=transform)
    if not values:
        raise CandidateEvidenceError(f"{label} binding is missing")
    if any(value != expected for value in values):
        raise CandidateEvidenceError(
            f"{label} binding disagrees with the authoritative manifest: {values!r} != {expected!r}"
        )


def _disabled_ids(values: Iterable[str]) -> set[str]:
    disabled: set[str] = set()
    for value in values:
        for comma_part in str(value or "").replace(";", ",").replace("\n", ",").split(","):
            disabled.update(token.strip().lower() for token in comma_part.split() if token.strip())
    return disabled


def _manifest_expectations(
    manifest_path: Path,
    files_dir: Path,
    *,
    disabled_artifact_ids: set[str],
) -> tuple[dict[str, Any], str, str, dict[str, ExpectedArtifact]]:
    manifest = _read_object(manifest_path, label="release manifest")
    channel = str(manifest.get("channelId") or manifest.get("channel") or "").strip().lower()
    version = str(manifest.get("version") or manifest.get("releaseVersion") or "").strip()
    if not channel or not version:
        raise CandidateEvidenceError("release manifest must bind a non-empty channel and version")

    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list):
        raise CandidateEvidenceError("release manifest artifacts must be a list")
    artifact_by_id: dict[str, dict[str, Any]] = {}
    for raw_row in artifacts:
        if not isinstance(raw_row, dict):
            raise CandidateEvidenceError("release manifest artifact rows must be objects")
        artifact_id = str(raw_row.get("artifactId") or raw_row.get("id") or "").strip().lower()
        if not artifact_id:
            raise CandidateEvidenceError("release manifest artifact is missing artifactId")
        if artifact_id in artifact_by_id:
            raise CandidateEvidenceError(f"release manifest contains duplicate artifactId: {artifact_id}")
        artifact_by_id[artifact_id] = raw_row

    coverage = manifest.get("desktopTupleCoverage")
    if not isinstance(coverage, dict):
        raise CandidateEvidenceError("release manifest is missing desktopTupleCoverage")
    promoted = coverage.get("promotedInstallerTuples")
    if not isinstance(promoted, list):
        raise CandidateEvidenceError("release manifest is missing promotedInstallerTuples")

    expected_by_receipt: dict[str, ExpectedArtifact] = {}
    seen_artifact_ids: set[str] = set()
    for raw_tuple in promoted:
        if not isinstance(raw_tuple, dict):
            raise CandidateEvidenceError("promoted installer tuple rows must be objects")
        artifact_id = str(raw_tuple.get("artifactId") or "").strip().lower()
        if artifact_id in disabled_artifact_ids:
            continue
        if not artifact_id or artifact_id not in artifact_by_id:
            raise CandidateEvidenceError(
                f"promoted installer tuple references an unknown artifactId: {artifact_id!r}"
            )
        if artifact_id in seen_artifact_ids:
            raise CandidateEvidenceError(f"promoted installer tuple duplicates artifactId: {artifact_id}")
        seen_artifact_ids.add(artifact_id)

        tuple_head = _require_safe_token(raw_tuple.get("head"), label=f"{artifact_id} tuple head")
        tuple_platform = _require_safe_token(
            _normalize_platform(raw_tuple.get("platform")),
            label=f"{artifact_id} tuple platform",
        )
        tuple_rid = _require_safe_token(raw_tuple.get("rid"), label=f"{artifact_id} tuple rid")
        artifact = artifact_by_id[artifact_id]
        kind = str(artifact.get("kind") or "").strip().lower()
        if kind != "installer":
            raise CandidateEvidenceError(f"promoted tuple {artifact_id} is not bound to an installer artifact")

        artifact_head = _require_safe_token(artifact.get("head"), label=f"{artifact_id} artifact head")
        artifact_platform = _require_safe_token(
            _normalize_platform(artifact.get("platform")),
            label=f"{artifact_id} artifact platform",
        )
        artifact_rid = _require_safe_token(artifact.get("rid"), label=f"{artifact_id} artifact rid")
        if (artifact_head, artifact_platform, artifact_rid) != (
            tuple_head,
            tuple_platform,
            tuple_rid,
        ):
            raise CandidateEvidenceError(
                f"promoted tuple {artifact_id} disagrees with its artifact head/platform/rid binding"
            )

        file_name = _require_file_name(
            artifact.get("fileName") or Path(str(artifact.get("downloadUrl") or "")).name,
            label=f"{artifact_id} fileName",
        )
        expected_sha = _normalize_digest(artifact.get("sha256") or artifact.get("artifactSha256"))
        if not SHA256_RE.fullmatch(expected_sha):
            raise CandidateEvidenceError(f"{artifact_id} manifest SHA-256 is missing or malformed")

        artifact_channels = _alias_values(
            artifact,
            ("channelId", "channel"),
            transform=lambda value: str(value or "").strip().lower(),
        )
        if artifact_channels and any(value != channel for value in artifact_channels):
            raise CandidateEvidenceError(f"{artifact_id} artifact channel disagrees with the manifest")
        artifact_versions = _alias_values(artifact, ("releaseVersion", "version"))
        if artifact_versions and any(value != version for value in artifact_versions):
            raise CandidateEvidenceError(f"{artifact_id} artifact version disagrees with the manifest")

        artifact_path = files_dir / file_name
        if not artifact_path.is_file() or artifact_path.is_symlink():
            raise CandidateEvidenceError(f"manifest artifact bytes are missing or not a regular file: {artifact_path}")
        actual_sha = _sha256_file(artifact_path)
        if actual_sha != expected_sha:
            raise CandidateEvidenceError(
                f"manifest artifact digest mismatch for {artifact_id}: {actual_sha} != {expected_sha}"
            )

        receipt_name = f"startup-smoke-{tuple_head}-{tuple_rid}.receipt.json"
        if receipt_name in expected_by_receipt:
            raise CandidateEvidenceError(f"promoted tuples collide on startup receipt name: {receipt_name}")
        expected_by_receipt[receipt_name] = ExpectedArtifact(
            artifact_id=artifact_id,
            head=tuple_head,
            platform=tuple_platform,
            rid=tuple_rid,
            file_name=file_name,
            sha256=expected_sha,
            size_bytes=artifact_path.stat().st_size,
            receipt_name=receipt_name,
        )

    if not expected_by_receipt:
        raise CandidateEvidenceError("release candidate has no enabled promoted installer tuples")
    return manifest, channel, version, expected_by_receipt


def _validate_receipt(
    receipt_path: Path,
    expected: ExpectedArtifact,
    *,
    channel: str,
    version: str,
) -> dict[str, Any]:
    if receipt_path.is_symlink():
        raise CandidateEvidenceError(f"startup receipt must not be a symlink: {receipt_path}")
    payload = _read_object(receipt_path, label="startup receipt")
    status = str(payload.get("status") or "").strip().lower()
    if status not in PASS_STATUSES:
        raise CandidateEvidenceError(f"{expected.receipt_name} status is not passing: {status!r}")

    _require_alias_identity(
        payload,
        ("channelId", "channel"),
        channel,
        label=f"{expected.receipt_name} channel",
        transform=lambda value: str(value or "").strip().lower(),
    )
    _require_alias_identity(
        payload,
        ("releaseVersion", "version"),
        version,
        label=f"{expected.receipt_name} release version",
    )
    _require_alias_identity(
        payload,
        ("artifactId",),
        expected.artifact_id,
        label=f"{expected.receipt_name} artifactId",
        transform=lambda value: str(value or "").strip().lower(),
    )
    _require_alias_identity(
        payload,
        ("headId", "head"),
        expected.head,
        label=f"{expected.receipt_name} head",
        transform=lambda value: str(value or "").strip().lower(),
    )
    _require_alias_identity(
        payload,
        ("platform",),
        expected.platform,
        label=f"{expected.receipt_name} platform",
        transform=_normalize_platform,
    )
    _require_alias_identity(
        payload,
        ("rid",),
        expected.rid,
        label=f"{expected.receipt_name} rid",
        transform=lambda value: str(value or "").strip().lower(),
    )
    _require_alias_identity(
        payload,
        ("artifactFileName", "fileName", "artifactRelativePath", "artifactPath"),
        expected.file_name,
        label=f"{expected.receipt_name} artifact file",
        transform=lambda value: Path(str(value or "").strip()).name,
    )
    _require_alias_identity(
        payload,
        ("artifactSha256", "artifactDigest"),
        expected.sha256,
        label=f"{expected.receipt_name} artifact digest",
        transform=_normalize_digest,
    )
    return payload


def _stage_receipts(
    *,
    receipt_roots: Sequence[Path],
    target_root: Path,
    expected_by_receipt: dict[str, ExpectedArtifact],
    channel: str,
    version: str,
) -> dict[str, Path]:
    if target_root.exists() and target_root.is_symlink():
        raise CandidateEvidenceError(f"startup receipt target must not be a symlink: {target_root}")
    target_root.mkdir(parents=True, exist_ok=True)
    if any(target_root.iterdir()):
        raise CandidateEvidenceError(f"startup receipt target must be empty: {target_root}")

    staged_sources: dict[str, Path] = {}
    for receipt_name, expected in sorted(expected_by_receipt.items()):
        best: tuple[tuple[float, float], Path] | None = None
        rejections: list[str] = []
        for root in receipt_roots:
            candidate = root / receipt_name
            if not candidate.is_file():
                continue
            try:
                payload = _validate_receipt(candidate, expected, channel=channel, version=version)
            except CandidateEvidenceError as error:
                rejections.append(f"{candidate}: {error}")
                continue
            score = (_recorded_at(payload, candidate), candidate.stat().st_mtime)
            if best is None or score > best[0]:
                best = (score, candidate)
        if best is None:
            detail = "; ".join(rejections) if rejections else "no candidate receipt was found"
            raise CandidateEvidenceError(
                f"no exact release-bound receipt for {receipt_name}: {detail}"
            )
        source_path = best[1]
        staged_sources[receipt_name] = source_path
    for receipt_name, source_path in sorted(staged_sources.items()):
        shutil.copy2(source_path, target_root / receipt_name)
    return staged_sources


def _validate_public_promotion_evidence(
    evidence_path: Path,
    *,
    expected_by_receipt: dict[str, ExpectedArtifact],
    channel: str,
    version: str,
) -> None:
    evidence = _read_object(evidence_path, label="public promotion evidence")
    if str(evidence.get("contractName") or "").strip() != "chummer.run.desktop_release_publication":
        raise CandidateEvidenceError("public promotion evidence contractName is invalid")

    evidence_channels = _alias_values(
        evidence,
        ("channelId", "channel"),
        transform=lambda value: str(value or "").strip().lower(),
    )
    if evidence_channels and any(value != channel for value in evidence_channels):
        raise CandidateEvidenceError("public promotion evidence channel disagrees with the manifest")
    evidence_versions = _alias_values(evidence, ("releaseVersion", "version"))
    if evidence_versions and any(value != version for value in evidence_versions):
        raise CandidateEvidenceError("public promotion evidence version disagrees with the manifest")

    expected_by_id = {
        expected.artifact_id: expected for expected in expected_by_receipt.values()
    }
    raw_rows = evidence.get("artifacts")
    if not isinstance(raw_rows, list):
        raise CandidateEvidenceError("public promotion evidence artifacts must be a list")
    rows_by_id: dict[str, dict[str, Any]] = {}
    for raw_row in raw_rows:
        if not isinstance(raw_row, dict):
            raise CandidateEvidenceError("public promotion evidence artifact rows must be objects")
        artifact_id = str(raw_row.get("artifactId") or "").strip().lower()
        if not artifact_id:
            raise CandidateEvidenceError("public promotion evidence artifactId is missing")
        if artifact_id in rows_by_id:
            raise CandidateEvidenceError(f"public promotion evidence duplicates artifactId: {artifact_id}")
        rows_by_id[artifact_id] = raw_row

    if set(rows_by_id) != set(expected_by_id):
        missing = sorted(set(expected_by_id) - set(rows_by_id))
        extra = sorted(set(rows_by_id) - set(expected_by_id))
        raise CandidateEvidenceError(
            f"public promotion evidence artifact set disagrees with promoted tuples; missing={missing}, extra={extra}"
        )

    for artifact_id, expected in sorted(expected_by_id.items()):
        row = rows_by_id[artifact_id]
        _require_alias_identity(
            row,
            ("fileName",),
            expected.file_name,
            label=f"{artifact_id} public evidence fileName",
        )
        _require_alias_identity(
            row,
            ("artifactSha256", "sha256"),
            expected.sha256,
            label=f"{artifact_id} public evidence digest",
            transform=_normalize_digest,
        )
        _require_alias_identity(
            row,
            ("platform",),
            expected.platform,
            label=f"{artifact_id} public evidence platform",
            transform=_normalize_platform,
        )
        _require_alias_identity(
            row,
            ("kind",),
            "installer",
            label=f"{artifact_id} public evidence kind",
            transform=lambda value: str(value or "").strip().lower(),
        )
        if str(row.get("promotionStatus") or "").strip().lower() not in PROMOTION_PASS_STATUSES:
            raise CandidateEvidenceError(f"{artifact_id} public evidence promotionStatus is not passing")
        if str(row.get("startupSmokeStatus") or "").strip().lower() not in PASS_STATUSES:
            raise CandidateEvidenceError(f"{artifact_id} public evidence startupSmokeStatus is not passing")

        receipt_path = PurePosixPath(str(row.get("startupSmokeReceiptPath") or ""))
        expected_receipt_path = PurePosixPath("startup-smoke") / expected.receipt_name
        if receipt_path != expected_receipt_path:
            raise CandidateEvidenceError(
                f"{artifact_id} public evidence startup receipt path disagrees with the promoted tuple"
            )
        try:
            size_bytes = int(row.get("artifactSizeBytes"))
        except (TypeError, ValueError) as error:
            raise CandidateEvidenceError(
                f"{artifact_id} public evidence artifactSizeBytes is missing or malformed"
            ) from error
        if size_bytes != expected.size_bytes:
            raise CandidateEvidenceError(
                f"{artifact_id} public evidence artifactSizeBytes disagrees with candidate bytes"
            )


def stage_release_candidate_evidence(
    *,
    manifest_path: Path,
    files_dir: Path,
    release_evidence_path: Path,
    receipt_roots: Sequence[Path],
    target_startup_smoke_dir: Path,
    disabled_artifact_ids: Iterable[str] = (),
) -> dict[str, Any]:
    disabled = _disabled_ids(disabled_artifact_ids)
    _, channel, version, expected_by_receipt = _manifest_expectations(
        manifest_path,
        files_dir,
        disabled_artifact_ids=disabled,
    )
    staged_sources = _stage_receipts(
        receipt_roots=[path for path in receipt_roots if path.is_dir()],
        target_root=target_startup_smoke_dir,
        expected_by_receipt=expected_by_receipt,
        channel=channel,
        version=version,
    )
    try:
        _validate_public_promotion_evidence(
            release_evidence_path,
            expected_by_receipt=expected_by_receipt,
            channel=channel,
            version=version,
        )
    except Exception:
        for staged_path in target_startup_smoke_dir.iterdir():
            if staged_path.is_file() and not staged_path.is_symlink():
                staged_path.unlink()
        raise

    return {
        "contractName": "chummer.release_candidate_evidence_identity.v1",
        "status": "pass",
        "channel": channel,
        "releaseVersion": version,
        "manifestPath": str(manifest_path),
        "releaseEvidencePath": str(release_evidence_path),
        "stagedReceiptCount": len(staged_sources),
        "stagedReceipts": [
            {
                "name": name,
                "sourcePath": str(staged_sources[name]),
                "artifactId": expected_by_receipt[name].artifact_id,
                "artifactSha256": expected_by_receipt[name].sha256,
            }
            for name in sorted(staged_sources)
        ],
        "disabledArtifactIds": sorted(disabled),
    }


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Stage exact release-bound startup receipts and validate public promotion evidence.",
    )
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--files-dir", required=True)
    parser.add_argument("--release-evidence", required=True)
    parser.add_argument("--target-startup-smoke-dir", required=True)
    parser.add_argument("--receipt-root", action="append", default=[])
    parser.add_argument("--disabled-artifact-id", action="append", default=[])
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        result = stage_release_candidate_evidence(
            manifest_path=Path(args.manifest),
            files_dir=Path(args.files_dir),
            release_evidence_path=Path(args.release_evidence),
            receipt_roots=[Path(raw) for raw in args.receipt_root],
            target_startup_smoke_dir=Path(args.target_startup_smoke_dir),
            disabled_artifact_ids=args.disabled_artifact_id,
        )
    except CandidateEvidenceError as error:
        print(f"release candidate evidence identity gate failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
