#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import shutil
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from issue_chummer_deployed_owner_session import derive_subject_from_origin_namespace


DEFAULT_LIVE_IMPORT = Path("/docker/chummercomplete/.tmp/origin-dossier-fresh-gold/ORIGIN_DOSSIER_LIVE_IMPORT_REQUEST.generated.json")
DEFAULT_HOST_STATE_ROOT = Path("/var/lib/docker/volumes/chummer6-hub_chummer-run-api-state/_data")
DEFAULT_CONTAINER_STATE_ROOT = Path("/app/state")
PATH_FIELDS = (
    "sourcePacketPath",
    "sourcePacketReceiptPath",
    "canonAuditReceiptPath",
    "providerManuscriptPath",
    "providerManuscriptReceiptPath",
    "humanizerReceiptPath",
    "humanizerQualityReceiptPath",
    "bookArtifactPath",
    "bookArtifactReceiptPath",
    "ebookArtifactPath",
    "ebookAudiobookshelfImportReceiptPath",
    "storySceneCoverPath",
    "storySceneCoverReceiptPath",
    "coverConsistencyReceiptPath",
    "audiobookPath",
    "m4bProviderImportReceiptPath",
    "audiobookshelfImportReceiptPath",
    "dossierVideoPath",
    "dossierVideoPosterPath",
    "dossierVideoReceiptPath",
    "moviePosterPath",
    "movieSubtitlesPath",
    "movieStoryboardPath",
    "telegramShareDeliveryReceiptPath",
    "finalNoFallbackNoSentinelAuditReceiptPath",
)


class StateImportError(RuntimeError):
    pass


def now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> dict[str, Any]:
    parsed = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise StateImportError(f"{path}: expected JSON object")
    return parsed


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_relative(path: Path, evidence_root: Path, namespace: str) -> Path:
    try:
        return path.resolve().relative_to(evidence_root.resolve())
    except ValueError:
        digest = hashlib.sha256(str(path.resolve()).encode("utf-8")).hexdigest()[:12]
        return Path(namespace) / "external" / f"{digest}-{path.name}"


def copy_artifact(
    *,
    source_text: object,
    field: str,
    evidence_root: Path,
    host_archive_root: Path,
    container_archive_root: Path,
    namespace: str,
) -> tuple[str, dict[str, Any]] | None:
    source = Path(str(source_text or "").strip()).expanduser()
    if not str(source_text or "").strip():
        return None
    if not source.is_file() or source.stat().st_size <= 0:
        raise StateImportError(f"{field}: artifact is missing or empty: {source}")
    relative = safe_relative(source, evidence_root, namespace)
    destination = host_archive_root / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    source_hash = sha256_file(source)
    copied_hash = sha256_file(destination)
    if source_hash != copied_hash:
        raise StateImportError(f"{field}: copied artifact hash mismatch")
    container_path = (container_archive_root / relative).as_posix()
    return container_path, {
        "field": field,
        "sourcePathSha256": hashlib.sha256(source.as_posix().encode("utf-8")).hexdigest(),
        "containerPath": container_path,
        "sha256": copied_hash,
        "bytes": destination.stat().st_size,
    }


def materialize(
    *,
    live_import: Path,
    host_state_root: Path,
    container_state_root: Path,
    subject_id: str | None,
    owner_user_id: str | None,
    output_receipt: Path | None,
) -> dict[str, Any]:
    payload = read_json(live_import)
    request = payload.get("importRequest")
    if not isinstance(request, dict):
        raise StateImportError("live import request is missing importRequest")
    namespace = str(request.get("originEditionNamespace") or "").strip()
    if not namespace.startswith("origin.chummer.run/"):
        raise StateImportError("originEditionNamespace must start with origin.chummer.run/")
    project_id = str(request.get("projectId") or "").strip()
    if not project_id:
        raise StateImportError("projectId is required")
    resolved_subject_id = (subject_id or "").strip() or derive_subject_from_origin_namespace(namespace)
    resolved_owner_user_id = (owner_user_id or "").strip() or f"origin-edition-{hashlib.sha256(resolved_subject_id.encode('utf-8')).hexdigest()[:12]}"
    evidence_root = live_import.resolve().parent
    host_archive_root = host_state_root / "origin-dossier-editions"
    container_archive_root = container_state_root / "origin-dossier-editions"
    entry = dict(request)
    copied: list[dict[str, Any]] = []
    for field in PATH_FIELDS:
        if field not in entry:
            continue
        copied_result = copy_artifact(
            source_text=entry.get(field),
            field=field,
            evidence_root=evidence_root,
            host_archive_root=host_archive_root,
            container_archive_root=container_archive_root,
            namespace=namespace,
        )
        if copied_result is None:
            continue
        container_path, row = copied_result
        entry[field] = container_path
        copied.append(row)

    entry["ownerUserId"] = resolved_owner_user_id
    entry["subjectId"] = resolved_subject_id
    entry["ownerSubjectId"] = resolved_subject_id
    entry["requiresAuthenticatedChummerRunUser"] = True
    entry["ebookArtifactPath"] = entry.get("ebookArtifactPath") or entry.get("bookArtifactPath")
    entry["moviePosterPath"] = entry.get("moviePosterPath") or entry.get("dossierVideoPosterPath")

    index_path = host_state_root / "origin-dossier-publications.json"
    existing: list[dict[str, Any]] = []
    if index_path.is_file():
        current = read_json(index_path)
        current_entries = current.get("publications") or current.get("originDossierPublications") or []
        if isinstance(current_entries, list):
            existing = [item for item in current_entries if isinstance(item, dict)]
    merged = [
        item
        for item in existing
        if str(item.get("projectId") or "").strip().lower() != project_id.lower()
        or str(item.get("ownerSubjectId") or item.get("subjectId") or "").strip().lower() != resolved_subject_id.lower()
    ]
    merged.append(entry)
    write_json(index_path, {"publications": merged})

    receipt = {
        "contractName": "chummer.origin_edition.deployed_state_import.v1",
        "operation": "origin_edition_deployed_state_import",
        "provider": "Chummer",
        "status": "verified",
        "completedAtUtc": now_iso(),
        "projectId": project_id,
        "namespace": namespace,
        "subjectId": resolved_subject_id,
        "ownerUserId": resolved_owner_user_id,
        "hostStateRootSha256": hashlib.sha256(host_state_root.as_posix().encode("utf-8")).hexdigest(),
        "containerStateRoot": container_state_root.as_posix(),
        "publicationIndexPath": index_path.as_posix(),
        "publicationIndexSha256": sha256_file(index_path),
        "copiedArtifacts": copied,
        "rawCredentialExposed": False,
        "rawSessionTokenExposed": False,
        "deploymentPerformed": False,
        "restartRequiredForExistingContainer": True,
        "nextAction": "Restart/recreate chummer-portal only after explicit deploy approval so CHUMMER_ORIGIN_DOSSIER_PUBLICATION_INDEX is active, then rerun the deployed browser probe.",
    }
    if output_receipt is not None:
        write_json(output_receipt, receipt)
    return receipt


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Copy an approved Origin Edition bundle into Chummer deployed state and write the publication index.")
    parser.add_argument("--live-import", type=Path, default=DEFAULT_LIVE_IMPORT)
    parser.add_argument("--host-state-root", type=Path, default=DEFAULT_HOST_STATE_ROOT)
    parser.add_argument("--container-state-root", type=Path, default=DEFAULT_CONTAINER_STATE_ROOT)
    parser.add_argument("--subject-id")
    parser.add_argument("--owner-user-id")
    parser.add_argument("--output-receipt", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    receipt = materialize(
        live_import=args.live_import,
        host_state_root=args.host_state_root,
        container_state_root=args.container_state_root,
        subject_id=args.subject_id,
        owner_user_id=args.owner_user_id,
        output_receipt=args.output_receipt,
    )
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
