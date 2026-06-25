#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import sys
from typing import Any
from zipfile import BadZipFile, ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from origin_edition_context import OriginEditionContext


CONTRACT_NAME = "chummer.origin_edition.cover_consistency_audit.v1"
DEFAULT_OUTPUT_NAME = "cover-consistency-strict.receipt.json"
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    parsed = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError(f"{path}: expected JSON object")
    return parsed


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _string(value: object) -> str:
    return str(value or "").strip()


def _status_ok(value: object) -> bool:
    return _string(value).lower() in {"pass", "verified", "ready"}


def _surface_file(name: str, path: Path, expected_sha256: str) -> dict[str, Any]:
    surface: dict[str, Any] = {"name": name, "path": path.as_posix(), "required": True}
    if not path.is_file():
        surface["status"] = "blocked_missing_file"
        return surface
    actual = _sha256_file(path)
    surface["sha256"] = actual
    surface["status"] = "pass" if actual == expected_sha256 else "blocked_hash_mismatch"
    return surface


def _epub_cover_surface(path: Path, expected_sha256: str) -> dict[str, Any]:
    surface: dict[str, Any] = {"name": "ebook_embedded_cover", "path": path.as_posix(), "required": True}
    if not path.is_file():
        surface["status"] = "blocked_missing_file"
        return surface

    try:
        with ZipFile(path) as archive:
            candidates = [
                name
                for name in archive.namelist()
                if Path(name).suffix.lower() in IMAGE_SUFFIXES and "cover" in Path(name).name.lower()
            ]
            surface["candidateCount"] = len(candidates)
            for name in candidates:
                digest = _sha256_bytes(archive.read(name))
                if digest == expected_sha256:
                    surface["status"] = "pass"
                    surface["embeddedPath"] = name
                    surface["sha256"] = digest
                    return surface
            if candidates:
                surface["status"] = "blocked_hash_mismatch"
                surface["candidateSha256"] = [_sha256_bytes(archive.read(name)) for name in candidates]
            else:
                surface["status"] = "blocked_cover_image_missing"
    except (BadZipFile, OSError, KeyError) as exc:
        surface["status"] = "blocked_unreadable_epub"
        surface["error"] = exc.__class__.__name__
    return surface


def _receipt_surface(
    name: str,
    paths: list[Path],
    expected_sha256: str,
    *,
    required_status: bool = True,
) -> dict[str, Any]:
    surface: dict[str, Any] = {
        "name": name,
        "candidatePaths": [path.as_posix() for path in paths],
        "required": True,
    }
    receipt = next((path for path in paths if path.is_file()), None)
    if receipt is None:
        surface["status"] = "blocked_missing_receipt"
        return surface

    surface["path"] = receipt.as_posix()
    surface["receiptSha256"] = _sha256_file(receipt)
    try:
        payload = _read_json(receipt)
    except (json.JSONDecodeError, OSError, ValueError) as exc:
        surface["status"] = "blocked_unreadable_receipt"
        surface["error"] = exc.__class__.__name__
        return surface

    cover_sha = _string(payload.get("coverSha256") or payload.get("cover_sha256"))
    status = payload.get("status")
    surface["reportedStatus"] = status
    surface["reportedCoverSha256"] = cover_sha
    if required_status and not _status_ok(status):
        surface["status"] = "blocked_receipt_not_verified"
    elif cover_sha != expected_sha256:
        surface["status"] = "blocked_cover_hash_mismatch"
    else:
        surface["status"] = "pass"
    return surface


def _display_path(path_value: str, edition_root: Path, namespace: str) -> str:
    path = Path(path_value)
    try:
        relative = path.resolve().relative_to(edition_root.resolve())
    except (OSError, ValueError):
        return path_value
    return (Path(namespace) / relative).as_posix()


def _redact_surface_paths(surface: dict[str, Any], edition_root: Path, namespace: str) -> dict[str, Any]:
    redacted = dict(surface)
    for key in ("path", "candidatePaths", "artifactCandidates"):
        value = redacted.get(key)
        if isinstance(value, str):
            redacted[key] = _display_path(value, edition_root, namespace)
        elif isinstance(value, list):
            redacted[key] = [
                _display_path(item, edition_root, namespace) if isinstance(item, str) else item
                for item in value
            ]
    return redacted


def audit(
    edition_root: Path,
    expected_cover_sha256: str,
    output: Path | None = None,
    context: OriginEditionContext | None = None,
) -> dict[str, Any]:
    expected_cover_sha256 = expected_cover_sha256.lower()
    namespace = (context.resolved_namespace if context is not None else "") or "origin.chummer.run/" + "/".join(edition_root.parts[-3:])
    pdf_candidates = [
        edition_root / "dossier" / "book.pdf",
        edition_root / "dossier" / "dossier.pdf",
        edition_root / "dossier" / "ebook.pdf",
    ]
    m4b_candidates = sorted((edition_root / "audiobook").glob("*.m4b"))

    surfaces = [
        _surface_file("chummer_hero_cover", edition_root / "cover.jpg", expected_cover_sha256),
        _surface_file("dossier_cover_asset", edition_root / "dossier" / "cover.jpg", expected_cover_sha256),
        _epub_cover_surface(edition_root / "dossier" / "ebook.epub", expected_cover_sha256),
        _receipt_surface(
            "pdf_cover_embedding",
            [
                edition_root / "dossier" / "pdf-cover.receipt.json",
                edition_root / "dossier" / "book.pdf.cover.receipt.json",
                edition_root / "dossier" / "dossier.pdf.cover.receipt.json",
            ],
            expected_cover_sha256,
        )
        | {
            "artifactPresent": any(path.is_file() for path in pdf_candidates),
            "artifactCandidates": [path.as_posix() for path in pdf_candidates],
        },
        _surface_file("audiobook_cover_asset", edition_root / "audiobook" / "cover.jpg", expected_cover_sha256),
        _receipt_surface(
            "m4b_cover_embedding",
            [
                edition_root / "audiobook" / "m4b-cover.receipt.json",
                *[Path(f"{candidate}.cover.receipt.json") for candidate in m4b_candidates],
            ],
            expected_cover_sha256,
        )
        | {
            "artifactPresent": bool(m4b_candidates),
            "artifactCandidates": [path.as_posix() for path in m4b_candidates],
        },
        _receipt_surface(
            "audiobookshelf_dossier_cover",
            [
                edition_root / "dossier" / "audiobookshelf-dossier-import.receipt.json",
                edition_root / "dossier" / "audiobookshelf-dossier-import-attempt.receipt.json",
            ],
            expected_cover_sha256,
        ),
        _receipt_surface(
            "audiobookshelf_audiobook_cover",
            [
                edition_root / "audiobook" / "audiobookshelf-import.receipt.json",
                edition_root / "audiobook" / "audiobookshelf-audiobook-import.receipt.json",
                edition_root / "audiobook" / "audiobook-audiobookshelf-import.receipt.json",
            ],
            expected_cover_sha256,
        ),
        _surface_file("movie_poster", edition_root / "movie" / "poster.jpg", expected_cover_sha256),
    ]

    for surface in surfaces:
        if surface["name"] in {"pdf_cover_embedding", "m4b_cover_embedding"} and not surface.get("artifactPresent"):
            surface["status"] = "blocked_missing_artifact"

    surfaces = [_redact_surface_paths(surface, edition_root, namespace) for surface in surfaces]
    blocked = [surface["name"] for surface in surfaces if surface.get("status") != "pass"]
    payload: dict[str, Any] = {
        "contractName": CONTRACT_NAME,
        "operation": "origin_edition_cover_consistency",
        "provider": "Chummer",
        "status": "pass" if not blocked else "blocked",
        "goldEligible": not blocked,
        "completedAtUtc": _now_iso(),
        "namespace": namespace,
        "editionRoot": namespace,
        "rawRuntimePathsExposed": False,
        "expectedCoverSha256": expected_cover_sha256,
        "surfaceCount": len(surfaces),
        "blockedSurfaces": blocked,
        "surfaces": surfaces,
        "tokens": [
            namespace,
            expected_cover_sha256,
            "strict_cover_consistency_audit",
            *([] if blocked else [
                "ebook_cover_embedded",
                "pdf_cover_embedded",
                "m4b_cover_embedded",
                "audiobookshelf_covers_verified",
                "movie_poster_matches_cover",
            ]),
        ],
    }

    if output is not None:
        _write_json(output, payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit Origin Edition cover consistency across all Gold surfaces.")
    parser.add_argument("--edition-root", required=True, type=Path)
    parser.add_argument("--expected-cover-sha256", required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--project-id")
    parser.add_argument("--family-name")
    parser.add_argument("--given-name")
    parser.add_argument("--runner-name")
    parser.add_argument("--namespace")
    parser.add_argument("--base-url")
    args = parser.parse_args()

    output = args.output or args.edition_root / DEFAULT_OUTPUT_NAME
    context = OriginEditionContext.from_env(
        project_id=args.project_id,
        family_name=args.family_name,
        given_name=args.given_name,
        runner_name=args.runner_name,
        namespace=args.namespace,
        base_url=args.base_url,
    )
    result = audit(args.edition_root, args.expected_cover_sha256, output, context)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
