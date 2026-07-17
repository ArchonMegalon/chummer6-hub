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


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def write_artifact(root: Path, name: str, content: bytes | str) -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")
    return path


def build_full_story_manuscript(runner_alias: str) -> str:
    chapter_titles = [
        "Rain Before the Name",
        "The Debt With Teeth",
        "Clinic Glass",
        "The Market That Lied",
        "A Favor Owed Twice",
        "The Safehouse Ledger",
        "The Name She Chose",
        "After the Sirens",
    ]
    scene_anchors = [
        "the clinic door",
        "the night market",
        "the rented booth",
        "the safehouse stairwell",
        "the transit platform",
        "the neon service alley",
        "the backroom call",
        "the rain-cut roofline",
    ]
    lines: list[str] = []
    for chapter_index, title in enumerate(chapter_titles, start=1):
        lines.append(f"# Chapter {chapter_index} - {title}")
        lines.append("")
        for beat in range(18):
            anchor = scene_anchors[(chapter_index + beat) % len(scene_anchors)]
            lines.append(
                f"{runner_alias} moves through {anchor} with a choice that belongs to the approved source packet, not to a new rules exception. "
                "The scene holds on concrete action, dialogue, memory, consequence, and the private reason the runner keeps returning to the same dangerous promise. "
                "Contacts notice the cost, rivals misread the silence, and the future GM receives useful relationship pressure without invented ware, qualities, gear, or sourcebook changes. "
                "Each beat leaves enough visual detail for the fitted cover, portrait shortlist, voice direction, and cinematic scene summary while preserving the character sheet as the authority."
            )
            lines.append("")
    return "\n".join(lines)


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


def write_cover_consistency_receipt(root: Path, name: str, *, origin_namespace: str, cover_sha: str) -> Path:
    required_surfaces = [
        "chummer_hero_cover",
        "dossier_cover_asset",
        "ebook_embedded_cover",
        "pdf_cover_embedding",
        "audiobook_cover_asset",
        "m4b_cover_embedding",
        "audiobookshelf_dossier_cover",
        "audiobookshelf_audiobook_cover",
        "movie_poster",
    ]
    path = root / name
    payload = {
        "contractName": "chummer.origin_edition.cover_consistency_audit.v1",
        "operation": "origin_edition_cover_consistency",
        "provider": "Chummer",
        "status": "pass",
        "goldEligible": True,
        "completedAtUtc": now_iso(),
        "namespace": origin_namespace,
        "expectedCoverSha256": cover_sha,
        "blockedSurfaces": [],
        "surfaces": [{"name": surface, "status": "pass", "sha256": cover_sha} for surface in required_surfaces],
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def write_final_no_fallback_receipt(root: Path, name: str, *, origin_namespace: str) -> Path:
    required_surfaces = [
        "approved_canon_packet",
        "provider_manuscript",
        "humanizer_receipt",
        "humanizer_quality_receipt",
        "cover",
        "ebook",
        "pdf",
        "pdf_cover_receipt",
        "dossier_audiobookshelf_receipt",
        "m4b_provider_gate",
        "cover_consistency",
        "movie",
        "movie_receipt",
        "gap_audit",
        "real_m4b_artifact",
        "audiobookshelf_audiobook_receipt",
    ]
    path = root / name
    payload = {
        "contractName": "chummer.origin_edition.final_no_fallback_bundle_audit.v1",
        "operation": "origin_edition_final_no_fallback_bundle_audit",
        "provider": "Chummer",
        "status": "pass",
        "goldEligible": True,
        "completedAtUtc": now_iso(),
        "namespace": origin_namespace,
        "blockedSurfaces": [],
        "surfaces": [{"name": surface, "status": "pass"} for surface in required_surfaces],
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def write_telegram_share_receipt(root: Path, name: str, *, project_id: str, origin_namespace: str) -> Path:
    owner_path = f"/account/work/origin-dossiers/{project_id}"
    read_path = f"{owner_path}/read"
    listen_path = f"{owner_path}/listen"
    watch_path = f"{owner_path}/watch"
    path = root / name
    payload = {
        "contractName": "ea.telegram_audiobook_live_delivery_receipt.v1",
        "operation": "telegram_share_delivery",
        "provider": "Telegram",
        "adapter": "ExecutiveAssistantChannelMessagingService",
        "status": "verified",
        "completedAtUtc": now_iso(),
        "telegramMessageIdHashedByEa": True,
        "rawTelegramChatIdIncluded": False,
        "deliveredLinks": [
            owner_path,
            read_path,
            listen_path,
            watch_path,
            sha256_text(owner_path),
            sha256_text(read_path),
            sha256_text(listen_path),
            sha256_text(watch_path),
            origin_namespace,
            sha256_text(origin_namespace),
            "operator_verified_live_run",
            "provider_receipt_reference:Telegram:telegram_share_delivery",
        ],
        "origin_edition_link_bundle": {
            "project_id": project_id,
            "origin_namespace_sha256": sha256_text(origin_namespace),
            "open_in_chummer_url_sha256": sha256_text(owner_path),
            "read_url_sha256": sha256_text(read_path),
            "listen_url_sha256": sha256_text(listen_path),
            "watch_url_sha256": sha256_text(watch_path),
            "all_required_links_present": True,
            "raw_urls_exposed": False,
            "telegram_delivery_status": "sent",
            "telegram_message_id_present": True,
        },
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def build_gold_publication(root: Path, subject_id: str) -> Path:
    project_root = root / PROJECT_ID
    project_root.mkdir(parents=True, exist_ok=True)
    origin_namespace = "origin.chummer.run/Varga/Mira/Route-Runner"

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
        build_full_story_manuscript("Route Runner"),
    )
    book = write_artifact(project_root, "book.pdf", b"%PDF-1.7\nRoute Runner Origin Dossier browser proof\n")
    ebook = write_artifact(project_root, "ebook.epub", b"EPUB route runner origin dossier browser proof\n")
    cover = write_artifact(project_root, "story-scene-cover.png", b"PNG route runner selected-face cover browser proof\n")
    audiobook = write_artifact(project_root, "audiobook.m4b", b"M4B route runner Unmixr audiobook browser proof\n")
    video = write_artifact(project_root, "dossier-film.mp4", b"MP4 route runner dossier video browser proof\n")
    movie_poster = write_artifact(project_root, "movie-poster.png", cover.read_bytes())
    movie_subtitles = write_artifact(project_root, "subtitles.vtt", "WEBVTT\n\n00:00.000 --> 00:02.000\nRain made the clinic sign stutter.\n")
    movie_storyboard = write_artifact(project_root, "storyboard.json", '{"sceneId":"night-market-run","shots":["threshold","market","escape"]}\n')

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
        provider="Subscribr",
        artifacts=[provider_manuscript],
        delivered_links=["full_story_manuscript", "chaptered_story"],
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
        delivered_links=["story_edition_ebook", "fitted_cover_art"],
    )
    ebook_dossier_receipt = write_receipt(
        project_root,
        "ebook-audiobookshelf-dossier.receipt.json",
        operation="audiobookshelf_dossier_import",
        provider="Audiobookshelf",
        artifacts=[ebook],
        delivered_links=[
            "dossierShare: https://audio.chummer.run/share/origin-browser-dossier",
            origin_namespace,
            f"{origin_namespace}/dossier",
        ],
    )
    cover_receipt = write_receipt(
        project_root,
        "story-scene-cover.receipt.json",
        operation="selected_face_scene_render",
        provider="Magicfit",
        artifacts=[cover],
        delivered_links=[
            f"/account/work/origin-dossiers/{PROJECT_ID}",
            f"/account/work/origin-dossiers/{PROJECT_ID}/cover",
            origin_namespace,
            "selected_character_face",
        ],
    )
    cover_consistency_receipt = write_cover_consistency_receipt(
        project_root,
        "cover-consistency.receipt.json",
        origin_namespace=origin_namespace,
        cover_sha=sha256(cover),
    )
    audiobook_receipt = write_receipt(
        project_root,
        "audiobookshelf-import.receipt.json",
        operation="audiobookshelf_import",
        provider="Audiobookshelf",
        artifacts=[audiobook],
        delivered_links=[
            "narrationProvider: Unmixr",
            origin_namespace,
            f"{origin_namespace}/audiobook",
        ],
    )
    video_receipt = write_receipt(
        project_root,
        "dossier-film.receipt.json",
        operation="dossier_video_import",
        provider="Magicfit",
        artifacts=[video],
        delivered_links=[
            "selected_character_face",
            "selected_cinematic_scene",
            "character_visible_cinematic",
        ],
    )
    telegram_receipt = write_telegram_share_receipt(
        project_root,
        "telegram-share.receipt.json",
        project_id=PROJECT_ID,
        origin_namespace=origin_namespace,
    )
    final_no_fallback_receipt = write_final_no_fallback_receipt(
        project_root,
        "final-no-fallback-no-sentinel.receipt.json",
        origin_namespace=origin_namespace,
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
                    "familyName": "Varga",
                    "givenName": "Mira",
                    "runnerName": "Route Runner",
                    "originEditionNamespace": origin_namespace,
                    "chummerRunOwnerUrl": f"https://chummer.run/account/work/origin-dossiers/{PROJECT_ID}",
                    "bookArtifactUrl": f"https://chummer.run/account/work/origin-dossiers/{PROJECT_ID}/book",
                    "audiobookshelfShareUrl": f"https://audio.chummer.run/share/{PROJECT_ID}",
                    "audiobookshelfDossierShareUrl": f"https://audio.chummer.run/share/{PROJECT_ID}-dossier",
                    "audiobookshelfAudiobookShareUrl": f"https://audio.chummer.run/share/{PROJECT_ID}",
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
                    "ebookArtifactPath": str(ebook),
                    "ebookAudiobookshelfImportReceiptPath": str(ebook_dossier_receipt),
                    "coverConsistencyReceiptPath": str(cover_consistency_receipt),
                    "audiobookPath": str(audiobook),
                    "audiobookshelfImportReceiptPath": str(audiobook_receipt),
                    "dossierVideoPath": str(video),
                    "dossierVideoReceiptPath": str(video_receipt),
                    "moviePosterPath": str(movie_poster),
                    "movieSubtitlesPath": str(movie_subtitles),
                    "movieStoryboardPath": str(movie_storyboard),
                    "telegramShareDeliveryReceiptPath": str(telegram_receipt),
                    "finalNoFallbackNoSentinelAuditReceiptPath": str(final_no_fallback_receipt),
                    "portraitChoices": [
                        {
                            "portraitId": "route-runner-night-market",
                            "title": "Night Market Exit",
                            "summary": "Street-smart, alert, and dressed for the first chapter's escape through neon market alleys.",
                            "previewUrl": f"https://chummer.run/account/work/origin-dossiers/{PROJECT_ID}/cover",
                            "selected": True,
                        },
                        {
                            "portraitId": "route-runner-clinic-shadow",
                            "title": "Clinic Shadow",
                            "summary": "A colder clinic-side portrait that matches the debt and recovery scenes in the story.",
                            "previewUrl": f"https://chummer.run/account/work/origin-dossiers/{PROJECT_ID}/cover",
                            "selected": False,
                        },
                        {
                            "portraitId": "route-runner-rain-platform",
                            "title": "Rain Platform",
                            "summary": "A transit-platform portrait that fits the runner's departure chapter and public-mask persona.",
                            "previewUrl": f"https://chummer.run/account/work/origin-dossiers/{PROJECT_ID}/cover",
                            "selected": False,
                        },
                    ],
                    "audiobookVoiceOptions": [
                        {
                            "voiceId": "voice-noir-01",
                            "label": "Noir mezzo",
                            "summary": "Low, controlled narration that fits the private-clinic and debt-collector chapters.",
                            "recommended": True,
                            "selected": True,
                        },
                        {
                            "voiceId": "voice-street-02",
                            "label": "Street alto",
                            "summary": "More edge and pace for the market, transit, and getaway scenes.",
                            "recommended": False,
                        },
                        {
                            "voiceId": "voice-warm-03",
                            "label": "Warm contralto",
                            "summary": "More reflective delivery for family, memory, and aftermath chapters.",
                            "recommended": False,
                        },
                    ],
                    "sceneHighlights": [
                        {
                            "sceneId": "chapter-01-clinic-glass",
                            "chapterLabel": "Chapter 01",
                            "title": "Clinic Glass",
                            "summary": "The runner understands the real cost of the clinic debt while rain hits reinforced windows.",
                            "selected": False,
                        },
                        {
                            "sceneId": "chapter-03-market-run",
                            "chapterLabel": "Chapter 03",
                            "title": "Night Market Run",
                            "summary": "A handoff goes bad in a crowded night market and the runner chooses who gets left behind.",
                            "selected": True,
                        },
                        {
                            "sceneId": "chapter-05-platform-farewell",
                            "chapterLabel": "Chapter 05",
                            "title": "Platform Farewell",
                            "summary": "The departure scene that breaks the old identity and forces the new alias into the open.",
                            "selected": False,
                        },
                        {
                            "sceneId": "chapter-07-aftermath-call",
                            "chapterLabel": "Chapter 07",
                            "title": "Aftermath Call",
                            "summary": "A final comm call shows what the runner lost and what the first job will demand next.",
                            "selected": False,
                        },
                    ],
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
