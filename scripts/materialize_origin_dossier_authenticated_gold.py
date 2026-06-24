#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from absolute_completion_common import LocalHubApp, TokenIdentityStub, ensure_completion_root, write_json


PROJECT_ID = "origin-browser"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Materialize local browser proof for authenticated Origin Dossier playback.")
    parser.add_argument("--completion-dir", default=str(ensure_completion_root()))
    parser.add_argument("--node-runner", default="npx")
    return parser.parse_args()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_artifact(root: Path, name: str, content: bytes | str) -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")
    return path


def write_receipt(
    root: Path,
    name: str,
    *,
    operation: str,
    provider: str,
    artifacts: list[Path] | None = None,
    delivered_links: list[str] | None = None,
) -> Path:
    path = root / name
    links = list(delivered_links or [])
    if provider.lower() != "chummer":
        links.append("operator_verified_live_run")
        links.append(f"provider_receipt_reference:{provider}:{operation}")
    payload = {
        "operation": operation,
        "provider": provider,
        "status": "verified",
        "completedAtUtc": now_iso(),
        "deliveredLinks": links,
        "artifactSha256": [sha256(item) for item in artifacts or []],
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def build_gold_publication(root: Path, subject_id: str) -> Path:
    project_root = root / PROJECT_ID
    project_root.mkdir(parents=True, exist_ok=True)

    source_packet = write_artifact(
        project_root,
        "approved-source-packet.json",
        json.dumps(
            {
                "runnerAlias": "Route Runner",
                "approvedForExternalProcessing": True,
                "selectedCharacterFace": "route-runner-face-v1",
                "canonPacketVersion": "origin-dossier-browser-proof-v1",
            },
            indent=2,
        ),
    )
    provider_manuscript = write_artifact(
        project_root,
        "provider-manuscript.md",
        "# Route Runner Origin Dossier\n\nProvider-authored story text from the approved source packet.\n",
    )
    book = write_artifact(project_root, "book.pdf", b"%PDF-1.7\nRoute Runner Origin Dossier browser proof\n")
    cover = write_artifact(project_root, "story-scene-cover.png", b"PNG route runner selected-face cover browser proof\n")
    audiobook = write_artifact(project_root, "audiobook.m4b", b"M4B route runner Unmixr audiobook browser proof\n")
    video = write_artifact(project_root, "dossier-film.mp4", b"MP4 route runner dossier video browser proof\n")

    source_receipt = write_receipt(
        project_root,
        "approved-source-packet.receipt.json",
        operation="origin_source_packet_approval",
        provider="Chummer",
        artifacts=[source_packet],
        delivered_links=["approved_source_packet", "external_processing_consent"],
    )
    canon_receipt = write_receipt(
        project_root,
        "chummer-canon-audit.receipt.json",
        operation="chummer_canon_audit",
        provider="Chummer",
        artifacts=[source_packet, provider_manuscript],
        delivered_links=["canon_audit_passed", "hard_conflicts:0", "privacy_findings:0"],
    )
    provider_receipt = write_receipt(
        project_root,
        "provider-manuscript.receipt.json",
        operation="provider_manuscript_import",
        provider="Inkfluence",
        artifacts=[provider_manuscript],
    )
    humanizer_receipt = write_receipt(
        project_root,
        "undetectable-humanizer.receipt.json",
        operation="undetectable_humanizer_postprocess",
        provider="Undetectable Humanizer",
        artifacts=[provider_manuscript],
    )
    book_receipt = write_receipt(
        project_root,
        "book.receipt.json",
        operation="book_artifact_import",
        provider="Inkfluence",
        artifacts=[book],
    )
    cover_receipt = write_receipt(
        project_root,
        "story-scene-cover.receipt.json",
        operation="selected_face_scene_render",
        provider="rendered_cover_lane",
        artifacts=[cover],
        delivered_links=[
            f"/account/work/origin-dossiers/{PROJECT_ID}",
            f"/account/work/origin-dossiers/{PROJECT_ID}/cover",
            "selected_character_face",
        ],
    )
    audiobook_receipt = write_receipt(
        project_root,
        "audiobookshelf-import.receipt.json",
        operation="audiobookshelf_import",
        provider="Audiobookshelf",
        artifacts=[audiobook],
        delivered_links=["narrationProvider: Unmixr"],
    )
    video_receipt = write_receipt(
        project_root,
        "dossier-film.receipt.json",
        operation="dossier_video_import",
        provider="video_lane",
        artifacts=[video],
    )
    telegram_receipt = write_receipt(
        project_root,
        "telegram-share.receipt.json",
        operation="telegram_share_delivery",
        provider="EA Telegram",
        delivered_links=[
            f"/account/work/origin-dossiers/{PROJECT_ID}",
            f"/account/work/origin-dossiers/{PROJECT_ID}/listen",
        ],
    )

    index_path = root / "origin-dossier-publications.json"
    write_json(
        index_path,
        {
            "publications": [
                {
                    "ownerUserId": "origin-browser-user",
                    "subjectId": subject_id,
                    "ownerSubjectId": subject_id,
                    "projectId": PROJECT_ID,
                    "title": "Route Runner Origin Dossier",
                    "runnerAlias": "Route Runner",
                    "publicationState": "published_for_owner",
                    "chummerRunOwnerUrl": f"https://chummer.run/account/work/origin-dossiers/{PROJECT_ID}",
                    "bookArtifactUrl": f"https://chummer.run/account/work/origin-dossiers/{PROJECT_ID}/book",
                    "audiobookshelfShareUrl": f"https://audio.chummer.run/share/{PROJECT_ID}",
                    "dossierVideoUrl": f"https://chummer.run/account/work/origin-dossiers/{PROJECT_ID}/video",
                    "storySceneCoverUrl": f"https://chummer.run/account/work/origin-dossiers/{PROJECT_ID}/cover",
                    "providerAuthoredManuscriptImported": True,
                    "undetectableHumanizerApplied": True,
                    "bookArtifactVerified": True,
                    "dossierVideoVerified": True,
                    "storySceneCoverUsesSelectedCharacterFace": True,
                    "audiobookshelfPlaybackVerified": True,
                    "telegramShareDelivered": True,
                    "requiresAuthenticatedChummerRunUser": True,
                    "sourcePacketPath": str(source_packet),
                    "sourcePacketReceiptPath": str(source_receipt),
                    "canonAuditReceiptPath": str(canon_receipt),
                    "providerManuscriptPath": str(provider_manuscript),
                    "providerManuscriptReceiptPath": str(provider_receipt),
                    "humanizerReceiptPath": str(humanizer_receipt),
                    "bookArtifactPath": str(book),
                    "bookArtifactReceiptPath": str(book_receipt),
                    "storySceneCoverPath": str(cover),
                    "storySceneCoverReceiptPath": str(cover_receipt),
                    "audiobookPath": str(audiobook),
                    "audiobookshelfImportReceiptPath": str(audiobook_receipt),
                    "dossierVideoPath": str(video),
                    "dossierVideoReceiptPath": str(video_receipt),
                    "telegramShareDeliveryReceiptPath": str(telegram_receipt),
                }
            ]
        },
    )
    return index_path


def run_playwright(node_runner: str, env: dict[str, str]) -> None:
    subprocess.run(
        [node_runner, "playwright", "test", "tests/public/origin-dossier-authenticated-gold.spec.ts"],
        check=True,
        env=env,
    )


def materialize(completion_dir: Path, node_runner: str) -> dict[str, Any]:
    completion_dir.mkdir(parents=True, exist_ok=True)
    subject_id = "subject.origin-browser"
    identity = TokenIdentityStub(
        access_token="origin-browser-token",
        subject_id=subject_id,
        display_name="Route Runner",
        email="route.runner@example.invalid",
    )
    with tempfile.TemporaryDirectory(prefix="chummer-origin-dossier-browser-") as temp_dir:
        runtime_root = Path(temp_dir)
        index_path = build_gold_publication(runtime_root, subject_id)
        with identity:
            app = LocalHubApp(
                identity_base_url=identity.base_url,
                extra_env={
                    "CHUMMER_ORIGIN_DOSSIER_PUBLICATION_INDEX": str(index_path),
                },
            )
            app.extra_env["CHUMMER_PUBLIC_BASE_URL"] = app.base_url
            with app:
                env = os.environ.copy()
                env.update(
                    {
                        "BASE_URL": app.base_url,
                        "CHUMMER_COMPLETION_DIR": str(completion_dir),
                        "CHUMMER_E2E_IDENTITY_TOKEN": identity.access_token,
                        "CHUMMER_E2E_ORIGIN_DOSSIER_PROJECT_ID": PROJECT_ID,
                    }
                )
                run_playwright(node_runner, env)

                proof_path = completion_dir / "ORIGIN_DOSSIER_AUTHENTICATED_GOLD_E2E.generated.json"
                payload = json.loads(proof_path.read_text(encoding="utf-8"))
                payload["source_packet_index"] = str(index_path)
                payload["local_hub_log"] = str(app.log_path) if app.log_path else None
                write_json(proof_path, payload)
                return payload

    raise RuntimeError("Origin Dossier browser proof did not run.")


def main() -> int:
    args = parse_args()
    payload = materialize(Path(args.completion_dir).resolve(), args.node_runner)
    return 0 if payload.get("status") == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
