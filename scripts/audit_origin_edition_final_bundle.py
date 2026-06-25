#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from origin_edition_context import OriginEditionContext


CONTRACT_NAME = "chummer.origin_edition.final_no_fallback_bundle_audit.v1"
REJECT_MARKERS = (
    "fallback",
    "placeholder",
    "sentinel",
    "stub",
    "self_generated",
    "self-generated",
    "local_fixture",
    "browser proof",
    "probe",
)
ROOT_REQUIRED_FILES = {
    "approved_canon_packet": "approved-sample-runner-canon.json",
    "provider_manuscript": "provider-manuscript-draft.md",
    "humanizer_receipt": "undetectable-humanizer.receipt.json",
    "humanizer_quality_receipt": "undetectable-humanizer-quality-gate.receipt.json",
}


def required_files(namespace: str) -> dict[str, str]:
    return {
        **ROOT_REQUIRED_FILES,
        "cover": f"{namespace}/cover.jpg",
        "ebook": f"{namespace}/dossier/ebook.epub",
        "pdf": f"{namespace}/dossier/book.pdf",
        "pdf_cover_receipt": f"{namespace}/dossier/pdf-cover.receipt.json",
        "dossier_audiobookshelf_receipt": f"{namespace}/dossier/audiobookshelf-dossier-import.receipt.json",
        "m4b_provider_gate": f"{namespace}/audiobook/m4b-provider-import-gate.receipt.json",
        "cover_consistency": f"{namespace}/cover-consistency-strict.receipt.json",
        "movie": f"{namespace}/movie/movie.mp4",
        "movie_receipt": f"{namespace}/movie/dossier-video.receipt.json",
    }


LIVE_IMPORT_PATH_FIELDS = {
    "approved_canon_packet": "sourcePacketPath",
    "provider_manuscript": "providerManuscriptPath",
    "humanizer_receipt": "humanizerReceiptPath",
    "humanizer_quality_receipt": "humanizerQualityReceiptPath",
    "ebook": "bookArtifactPath",
    "m4b_provider_gate": "m4bProviderImportReceiptPath",
    "movie": "dossierVideoPath",
    "movie_receipt": "dossierVideoReceiptPath",
}

BRANCH_REQUIRED_SURFACES = {
    "cover": ("root", (".jpg", ".jpeg", ".png", ".webp")),
    "ebook": ("dossier", (".epub",)),
    "pdf": ("dossier", (".pdf",)),
    "pdf_cover_receipt": ("dossier", (".json",)),
    "dossier_audiobookshelf_receipt": ("dossier", (".json",)),
    "m4b_provider_gate": ("audiobook", (".json",)),
    "real_m4b_artifact": ("audiobook", (".m4b",)),
    "audiobookshelf_audiobook_receipt": ("audiobook", (".json",)),
    "movie": ("movie", (".mp4",)),
    "movie_receipt": ("movie", (".json",)),
}


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    parsed = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError(f"{path}: expected object")
    return parsed


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _string(value: object) -> str:
    return str(value or "").strip()


def _live_import_request(root: Path) -> dict[str, Any]:
    path = root / "ORIGIN_DOSSIER_LIVE_IMPORT_REQUEST.generated.json"
    if not path.is_file():
        return {}
    try:
        payload = _read_json(path)
    except (OSError, json.JSONDecodeError, ValueError):
        return {}
    request = payload.get("importRequest")
    return request if isinstance(request, dict) else {}


def _resolve_path(root: Path, value: object) -> Path:
    text = _string(value)
    if not text:
        return root / "__missing__"
    path = Path(text)
    return path if path.is_absolute() else root / path


def _relative_for_receipt(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _path_under_branch(path: Path, root: Path, namespace: str, branch: str, suffixes: tuple[str, ...]) -> bool:
    try:
        relative = path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        relative = path.as_posix().lstrip("/")
        marker = "origin.chummer.run/"
        if marker in relative:
            relative = relative[relative.index(marker) :]
    expected = namespace if branch == "root" else f"{namespace}/{branch}"
    prefix = expected.rstrip("/") + "/"
    return relative.startswith(prefix) and relative.lower().endswith(tuple(item.lower() for item in suffixes))


def _contains_reject_marker(value: object) -> bool:
    if isinstance(value, str):
        lowered = value.lower()
        return any(marker in lowered for marker in REJECT_MARKERS)
    if isinstance(value, dict):
        return any(_contains_reject_marker(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_reject_marker(item) for item in value)
    return False


def _status_pass(payload: dict[str, Any]) -> bool:
    return _string(payload.get("status")).lower() in {"approved", "pass", "verified", "delivered", "published"}


def _json_surface(name: str, path: Path, root: Path, *, reject_markers: bool = True) -> dict[str, Any]:
    surface: dict[str, Any] = {
        "name": name,
        "path": path.relative_to(root).as_posix(),
        "required": True,
    }
    if not path.is_file():
        surface["status"] = "blocked_missing_file"
        return surface
    if path.stat().st_size <= 0:
        surface["status"] = "blocked_empty_file"
        return surface
    surface["sha256"] = _sha256_file(path)
    try:
        payload = _read_json(path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        surface["status"] = "blocked_unreadable_json"
        surface["error"] = exc.__class__.__name__
        return surface
    surface["reportedStatus"] = payload.get("status")
    surface["goldEligible"] = payload.get("goldEligible")
    if reject_markers and _contains_reject_marker(payload):
        surface["status"] = "blocked_rejected_marker"
    elif not _status_pass(payload):
        surface["status"] = "blocked_not_pass"
    elif payload.get("goldEligible") is False:
        surface["status"] = "blocked_not_gold_eligible"
    else:
        surface["status"] = "pass"
    return surface


def _file_surface(name: str, path: Path, root: Path, *, reject_content_markers: bool = False) -> dict[str, Any]:
    surface: dict[str, Any] = {
        "name": name,
        "path": path.relative_to(root).as_posix(),
        "required": True,
    }
    if not path.is_file():
        surface["status"] = "blocked_missing_file"
        return surface
    if path.stat().st_size <= 0:
        surface["status"] = "blocked_empty_file"
        return surface
    surface["sha256"] = _sha256_file(path)
    if reject_content_markers:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = ""
        if text and _contains_reject_marker(text):
            surface["status"] = "blocked_rejected_marker"
            return surface
    surface["status"] = "pass"
    return surface


def _branch_surface(name: str, path: Path, root: Path, namespace: str, branch: str, suffixes: tuple[str, ...]) -> dict[str, Any]:
    expected = namespace if branch == "root" else f"{namespace}/{branch}"
    return {
        "name": f"{name}_branch",
        "path": _relative_for_receipt(path, root),
        "required": True,
        "expectedBranch": expected,
        "status": "pass" if _path_under_branch(path, root, namespace, branch, suffixes) else "blocked_wrong_branch",
    }


def audit(root: Path, output: Path | None = None, context: OriginEditionContext | None = None) -> dict[str, Any]:
    root = root.resolve()
    context = context or OriginEditionContext.from_env()
    namespace = context.resolved_namespace
    live_request = _live_import_request(root)
    surfaces: list[dict[str, Any]] = []
    resolved_required_files = required_files(namespace)
    for name, field in LIVE_IMPORT_PATH_FIELDS.items():
        if _string(live_request.get(field)):
            resolved_required_files[name] = _string(live_request.get(field))
    for name, relative in resolved_required_files.items():
        path = _resolve_path(root, relative)
        if name == "approved_canon_packet":
            surfaces.append(_file_surface(name, path, root))
        elif path.suffix.lower() == ".json":
            surfaces.append(_json_surface(name, path, root, reject_markers=name != "gap_audit"))
        else:
            surfaces.append(_file_surface(name, path, root, reject_content_markers=name in {"provider_manuscript"}))
        if name in BRANCH_REQUIRED_SURFACES:
            branch, suffixes = BRANCH_REQUIRED_SURFACES[name]
            surfaces.append(_branch_surface(name, path, root, namespace, branch, suffixes))

    # The actual M4B and Audiobookshelf audiobook receipt are intentionally distinct from the gate receipt.
    audiobook_dir = root / namespace / "audiobook"
    m4b_candidates = sorted(audiobook_dir.glob("*.m4b"))
    live_m4b_path = _resolve_path(root, live_request.get("audiobookPath")) if _string(live_request.get("audiobookPath")) else None
    if live_m4b_path is not None:
        m4b_candidates = [live_m4b_path] if live_m4b_path.is_file() else []
    surfaces.append(
        {
            "name": "real_m4b_artifact",
            "path": _relative_for_receipt(live_m4b_path, root) if live_m4b_path is not None else f"{namespace}/audiobook/*.m4b",
            "required": True,
            "status": "pass" if m4b_candidates else "blocked_missing_file",
            "candidateCount": len(m4b_candidates),
            "candidateSha256": [_sha256_file(path) for path in m4b_candidates],
        }
    )
    if live_m4b_path is not None:
        branch, suffixes = BRANCH_REQUIRED_SURFACES["real_m4b_artifact"]
        surfaces.append(_branch_surface("real_m4b_artifact", live_m4b_path, root, namespace, branch, suffixes))
    audiobook_receipt_path = (
        _resolve_path(root, live_request.get("audiobookshelfImportReceiptPath"))
        if _string(live_request.get("audiobookshelfImportReceiptPath"))
        else audiobook_dir / "audiobookshelf-import.receipt.json"
    )
    surfaces.append(
        _json_surface(
            "audiobookshelf_audiobook_receipt",
            audiobook_receipt_path,
            root,
            reject_markers=True,
        )
    )
    branch, suffixes = BRANCH_REQUIRED_SURFACES["audiobookshelf_audiobook_receipt"]
    surfaces.append(_branch_surface("audiobookshelf_audiobook_receipt", audiobook_receipt_path, root, namespace, branch, suffixes))

    blocked = [surface["name"] for surface in surfaces if surface.get("status") != "pass"]
    completed_at = _now_iso()
    payload: dict[str, Any] = {
        "contractName": CONTRACT_NAME,
        "operation": "origin_edition_final_no_fallback_bundle_audit",
        "provider": "Chummer",
        "status": "pass" if not blocked else "blocked",
        "goldEligible": not blocked,
        "generatedAtUtc": completed_at,
        "completedAtUtc": completed_at,
        "namespace": namespace,
        "projectId": context.project_id,
        "blockedSurfaces": blocked,
        "surfaceCount": len(surfaces),
        "surfaces": surfaces,
        "rawRuntimePathsExposed": False,
        "tokens": [
            namespace,
            "final_no_fallback_no_sentinel_audit",
            *([] if blocked else ["all_required_origin_edition_surfaces_passed"]),
        ],
    }
    if output is not None:
        _write_json(output, payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit Origin Edition final bundle for fallback/sentinel gaps.")
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--project-id")
    parser.add_argument("--family-name")
    parser.add_argument("--given-name")
    parser.add_argument("--runner-name")
    parser.add_argument("--namespace")
    parser.add_argument("--base-url")
    args = parser.parse_args()
    context = OriginEditionContext.from_env(
        project_id=args.project_id,
        family_name=args.family_name,
        given_name=args.given_name,
        runner_name=args.runner_name,
        namespace=args.namespace,
        base_url=args.base_url,
    )
    result = audit(args.root, args.output, context)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
