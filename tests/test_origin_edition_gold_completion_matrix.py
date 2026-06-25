from __future__ import annotations

import importlib.util
import json
import hashlib
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "materialize_origin_edition_gold_completion_matrix.py"


def load_module():
    spec = importlib.util.spec_from_file_location("origin_edition_gold_completion_matrix", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def write_file(path: Path, content: bytes | str = "x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")
    return path


def receipt(path: Path, *, status: str = "pass", gold: bool = True, extra: dict | None = None) -> Path:
    payload = {
        "contractName": "test.receipt",
        "status": status,
        "goldEligible": gold,
    }
    if extra:
        payload.update(extra)
    return write_json(path, payload)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def telegram_origin_link_receipt(
    path: Path,
    *,
    project_id: str = "varga-mira-kestrel",
    namespace: str = "origin.chummer.run/Varga/Mira/Kestrel",
    watch_hash: str | None = None,
    status: str = "pass",
) -> Path:
    return write_json(
        path,
        {
            "contract_name": "ea.telegram_audiobook_live_delivery_receipt.v1",
            "status": status,
            "selected_delivery": {
                "status": "audiobookshelf_imported",
                "telegram_delivery_status": "sent",
                "telegram_delivery_message_id_present": True,
                "telegram_chat_bound": True,
                "telegram_message_bound": True,
                "origin_edition_link_bundle": {
                    "status": "sent",
                    "project_id": project_id,
                    "origin_namespace_sha256": sha256_text(namespace),
                    "telegram_delivery_status": "sent",
                    "telegram_message_id_present": True,
                    "all_required_links_present": True,
                    "raw_urls_exposed": False,
                    "read_url_sha256": sha256_text(f"https://chummer.run/account/work/origin-dossiers/{project_id}/read"),
                    "listen_url_sha256": sha256_text(f"https://chummer.run/account/work/origin-dossiers/{project_id}/listen"),
                    "watch_url_sha256": watch_hash
                    or sha256_text(f"https://chummer.run/account/work/origin-dossiers/{project_id}/video"),
                    "open_in_chummer_url_sha256": sha256_text(f"https://chummer.run/account/work/origin-dossiers/{project_id}"),
                }
            },
        },
    )


def authenticated_route_receipt(
    path: Path,
    *,
    project_id: str = "varga-mira-kestrel",
    listen_tab_visible: bool = True,
    local_base_url: str = "http://127.0.0.1:41319",
) -> Path:
    owner = f"{local_base_url}/account/work/origin-dossiers/{project_id}"
    return write_json(
        path,
        {
            "contractName": "chummer.origin_edition.authenticated_route_live_proof.v1",
            "status": "pass",
            "goldEligible": True,
            "localAuthenticatedRunSiteInstance": True,
            "local_fixture_artifacts": False,
            "deployedRouteClaimAllowed": False,
            "rawCredentialExposed": False,
            "rawSessionTokenExposed": False,
            "owner_detail_page": owner,
            "read_url": f"{owner}/read",
            "listen_url": f"{owner}/listen",
            "watch_url": f"{owner}/video",
            "selected_face_cover_url": f"{owner}/cover",
            "book_url": f"{owner}/book",
            "ownerDetailStatus": 200,
            "ownerLibraryStatus": 200,
            "anonymousDetailRedirectVerified": True,
            "anonymousReadRedirectVerified": True,
            "anonymousListenRedirectVerified": True,
            "anonymousBookRedirectVerified": True,
            "anonymousCoverRedirectVerified": True,
            "anonymousVideoRedirectVerified": True,
            "anonymousArtifactRedirectVerified": True,
            "all_private_routes_login_protected": True,
            "logged_in_browser_verified": True,
            "selected_face_cover_marker_visible": True,
            "selected_face_cover_alt_visible": True,
            "selected_face_cover_route_visible": True,
            "selected_face_cover_visible": True,
            "read_tab_visible": True,
            "read_section_visible": True,
            "listen_tab_visible": listen_tab_visible,
            "listen_section_visible": listen_tab_visible,
            "watch_tab_visible": True,
            "watch_section_visible": True,
            "canon_audit_tab_visible": True,
            "canon_audit_content_verified": True,
            "read_gate_verified": True,
            "chummer_run_listen_gate_verified": True,
            "watch_gate_verified": True,
            "coverRouteVerified": True,
            "bookRouteVerified": True,
            "cover_sha_matches_import": True,
            "book_sha_matches_import": True,
            "video_sha_matches_import": True,
            "live_provider_artifacts_verified": True,
            "live_provider_delivery_verified": True,
            "urlHashes": {
                "owner": sha256_text(owner),
                "read": sha256_text(f"{owner}/read"),
                "listen": sha256_text(f"{owner}/listen"),
                "video": sha256_text(f"{owner}/video"),
                "cover": sha256_text(f"{owner}/cover"),
                "book": sha256_text(f"{owner}/book"),
            },
            "tokens": [
                "authenticated_chummer_run_route_proof",
                "read_tab_visible",
                "listen_tab_visible",
                "watch_tab_visible",
                "canon_audit_tab_visible",
                "anonymous_private_access_redirects_to_login",
                "owner_read_listen_watch_routes_verified",
            ],
        },
    )


REQUIRED_COVER_SURFACES = [
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
REQUIRED_FINAL_BUNDLE_SURFACES = [
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
    "real_m4b_artifact",
    "audiobookshelf_audiobook_receipt",
]


def cover_consistency_receipt(path: Path, *, missing_surface: str | None = None) -> Path:
    surfaces = [
        {
            "name": surface,
            "status": "blocked_hash_mismatch" if surface == missing_surface else "pass",
            "sha256": "a" * 64,
        }
        for surface in REQUIRED_COVER_SURFACES
    ]
    return write_json(
        path,
        {
            "contractName": "chummer.origin_edition.cover_consistency_audit.v1",
            "operation": "origin_edition_cover_consistency",
            "provider": "Chummer",
            "status": "blocked" if missing_surface else "pass",
            "goldEligible": missing_surface is None,
            "expectedCoverSha256": "a" * 64,
            "blockedSurfaces": [] if missing_surface is None else [missing_surface],
            "surfaces": surfaces,
        },
    )


def final_bundle_receipt(path: Path, *, blocked_surface: str | None = None) -> Path:
    surfaces = [
        {
            "name": surface,
            "status": "blocked" if surface == blocked_surface else "pass",
            "required": True,
        }
        for surface in REQUIRED_FINAL_BUNDLE_SURFACES
    ]
    return write_json(
        path,
        {
            "contractName": "chummer.origin_edition.final_no_fallback_bundle_audit.v1",
            "operation": "origin_edition_final_no_fallback_bundle_audit",
            "provider": "Chummer",
            "status": "blocked" if blocked_surface else "pass",
            "goldEligible": blocked_surface is None,
            "rawRuntimePathsExposed": False,
            "blockedSurfaces": [] if blocked_surface is None else [blocked_surface],
            "surfaces": surfaces,
            "tokens": [
                "origin.chummer.run/Varga/Mira/Kestrel",
                "final_no_fallback_no_sentinel_audit",
                *([] if blocked_surface else ["all_required_origin_edition_surfaces_passed"]),
            ],
        },
    )


def seed_bundle(root: Path, *, deployed_pass: bool, gold_pass: bool) -> None:
    branch = root / "origin.chummer.run/Varga/Mira/Kestrel"
    ebook_bytes = b"epub"
    pdf_bytes = b"pdf"
    ebook_sha = sha256_bytes(ebook_bytes)
    pdf_sha = sha256_bytes(pdf_bytes)
    source_packet = {
        "contractName": "chummer.origin_dossier.approved_sample_runner_canon.v1",
        "runnerAlias": "Kestrel",
        "privacyClassification": "operator_owned_fictional_sample",
        "externalProcessingConsent": True,
        "canonOwnsFacts": "Chummer",
        "prohibitedInventions": [
            "Do not add new game qualities, skills, equipment, contacts, enemies, or debts.",
            "Do not alter metatype, age, chronology, relationship states, or unresolved threads.",
            "Do not quote sourcebook prose.",
            "Do not include other players' private information.",
            "Do not make provider-created facts canonical.",
        ],
        "selectedCharacterFace": {"faceRef": "sample-face-kestrel-v1"},
        "storySceneForCover": {"sceneId": "clinic-door-rain"},
    }
    write_json(root / "approved-sample-runner-canon.json", source_packet)
    source_packet_sha = sha256_bytes((root / "approved-sample-runner-canon.json").read_bytes())
    write_file(root / "provider-manuscript-draft.md")
    write_file(branch / "dossier/ebook.epub", ebook_bytes)
    write_file(branch / "dossier/book.pdf", pdf_bytes)
    m4b_bytes = b"m4b"
    m4b_sha = sha256_bytes(m4b_bytes)
    write_file(branch / "audiobook/kestrel-origin.m4b", m4b_bytes)
    write_file(branch / "movie/movie.mp4", b"mp4")
    write_file(branch / "cover.jpg", b"cover")

    receipt(
        root / "source-packet-approval.receipt.json",
        extra={
            "artifactSha256": [source_packet_sha],
            "tokens": [
                "approved_source_packet",
                "external_processing_consent",
                "approved_sample_runner_canon_only",
                "privacy_review_passed",
            ]
        },
    )
    receipt(root / "provider-manuscript-import.receipt.json")
    receipt(root / "undetectable-humanizer.receipt.json")
    receipt(root / "undetectable-humanizer-quality-gate.browseract.normalized.receipt.json")
    receipt(
        root / "canon-privacy-audit.receipt.json",
        extra={
            "artifactSha256": [source_packet_sha, "g" * 64, "e" * 64],
            "hardConflicts": 0,
            "privacyFindings": 0,
            "tokens": [
                "canon_audit_passed",
                "hard_conflicts:0",
                "privacy_findings:0",
                "approved_sample_runner_canon_only",
                "no_provider_created_facts_entered_canon",
            ],
        },
    )
    receipt(root / "story-scene-cover.receipt.json", status="generated")
    cover_consistency_receipt(branch / "cover-consistency-strict.receipt.json")
    receipt(
        root / "book-artifact-import.receipt.json",
        extra={
            "artifactSha256": [ebook_sha, pdf_sha],
            "tokens": [
                ebook_sha,
                pdf_sha,
                "e" * 64,
                "accepted_humanized_manuscript_embedded",
                "ebook_cover_embedded",
                "pdf_cover_embedded",
            ],
        },
    )
    receipt(
        branch / "dossier/pdf-cover.receipt.json",
        extra={
            "pdfSha256": pdf_sha,
            "coverSha256": "a" * 64,
            "manuscriptSha256": "e" * 64,
            "rawRuntimePathsExposed": False,
            "storyStartsWithoutPreamble": True,
            "tokens": [
                "pdf_cover_embedded",
                "story_starts_without_preamble",
            ],
        },
    )
    receipt(
        branch / "audiobook/m4b-provider-import-gate.receipt.json",
        extra={
            "directProviderPublishingAllowed": False,
            "m4bSha256": m4b_sha,
            "coverSha256": "a" * 64,
            "sourceSha256": "e" * 64,
            "providerReceiptPath": "origin.chummer.run/Varga/Mira/Kestrel/audiobook/unmixr-provider-m4b.receipt.json",
            "providerReceiptSha256": "",
            "rawCredentialExposed": False,
            "rawProviderTokenExposed": False,
            "rawRuntimePathsExposed": False,
            "tokens": [
                "provider:Unmixr",
                m4b_sha,
                "a" * 64,
                "e" * 64,
                "accepted_humanized_manuscript",
                "provider_m4b_verified",
                "m4b_cover_embedded",
            ],
        },
    )
    provider_receipt = receipt(
        branch / "audiobook/unmixr-provider-m4b.receipt.json",
        extra={
            "provider": "Unmixr",
            "voiceProvider": "Unmixr",
            "m4bSha256": m4b_sha,
            "audiobookSha256": m4b_sha,
            "coverSha256": "a" * 64,
            "manuscriptSha256": "e" * 64,
            "sourceSha256": "e" * 64,
            "directProviderPublishingAllowed": False,
            "rawCredentialExposed": False,
            "rawProviderTokenExposed": False,
            "tokens": [
                "provider:Unmixr",
                f"m4b_sha256:{m4b_sha}",
                f"cover_sha256:{'a' * 64}",
                f"accepted_humanized_manuscript_sha256:{'e' * 64}",
            ],
        },
    )
    gate = json.loads((branch / "audiobook/m4b-provider-import-gate.receipt.json").read_text(encoding="utf-8"))
    gate["providerReceiptSha256"] = hashlib.sha256(provider_receipt.read_bytes()).hexdigest()
    write_json(branch / "audiobook/m4b-provider-import-gate.receipt.json", gate)
    receipt(
        branch / "audiobook/audiobookshelf-import.receipt.json",
        extra={
            "shareCreated": True,
            "shareStatus": "public_share_ready",
            "shareUrl": "https://audiobookshelf.girschele.com/audiobookshelf/share/audiobook-test",
        },
    )
    receipt(
        branch / "dossier/audiobookshelf-dossier-import.receipt.json",
        extra={
            "audiobookshelfDossierShareUrl": "https://audiobookshelf.girschele.com/audiobookshelf/share/dossier-test",
        },
    )
    receipt(
        branch / "movie/dossier-video.receipt.json",
        extra={
            "artifactSha256": ["d" * 64],
            "posterSha256": "a" * 64,
            "visualSourceCoverSha256": "a" * 64,
            "audioSourceM4bSha256": m4b_sha,
            "acceptedHumanizedManuscriptSha256": "e" * 64,
            "sourcePacketSha256": source_packet_sha,
            "rawRuntimePathExposed": False,
            "rawProviderSecretExposed": False,
            "storySceneProof": {
                "usesAcceptedHumanizedStoryScene": True,
                "usesSelectedCharacterFaceCover": True,
                "usesUnmixrNarrationAudio": True,
                "markerMediaUsed": False,
                "syntheticBackupAudioUsed": False,
            },
        },
    )
    authenticated_route_receipt(branch / "authenticated-chummer-route-live.receipt.json")
    write_json(
        branch / "runsite-integration-proof.receipt.json",
        {
            "contractName": "chummer.origin_edition.runsite_integration_proof.v1",
            "status": "pass",
            "integrationEligible": True,
            "goalCompletionClaimAllowed": False,
            "runsiteHandoffVerified": True,
            "newestLtdsInspected": True,
            "envInspected": True,
            "rybbitEnvOnly": True,
            "deploymentPerformed": False,
            "secretValuesStored": False,
            "checks": [
                {"name": name, "status": "pass"}
                for name in [
                    "runsite_handoff_constraints",
                    "origin_dossier_authenticated_page",
                    "origin_dossier_private_route_controller",
                    "origin_publication_gold_gate_service",
                    "rybbit_env_only_layout",
                    "runsite_env_example_rybbit",
                    "runsite_compose_rybbit",
                    "newest_ltd_and_env_inputs_inspected",
                    "live_import_request",
                    "local_authenticated_route_proof",
                    "final_no_sentinel_media_audit",
                ]
            ],
            "inventoryInspection": {
                "ltdInventoryInspected": True,
                "runsiteEnvInspected": True,
                "eaEnvInspected": True,
                "newestProviderInventorySignals": {
                    "unmixr": True,
                    "inkfluence": True,
                    "firstBook": True,
                    "youbooks": True,
                },
                "originGoldCapabilitySignals": {
                    "provider_inventory_present": True,
                    "manuscript_or_edition_provider_available": True,
                    "premium_audio_provider_available": True,
                    "optional_overflow_accounts_do_not_block": True,
                },
                "rybbitRunKeysPresent": {
                    "RYBBIT_CHUMMER_RUN_SITE_ID": True,
                    "RYBBIT_CHUMMER_RUN_SCRIPT_URL": True,
                    "RYBBIT_CHUMMER_RUN_SCRIPT_ORIGIN": True,
                    "RYBBIT_CHUMMER_RUN_ALLOW_SAME_HOST_PROXY": True,
                },
            },
        },
    )
    telegram_origin_link_receipt(branch / "telegram-origin-link-bundle-live.receipt.json")
    final_bundle_receipt(branch / "final-no-fallback-no-sentinel-audit.receipt.json")
    receipt(branch / "deployed-operator-handoff.receipt.json", status="pass" if deployed_pass else "ready_for_operator_token", gold=deployed_pass)

    write_json(
        branch / "deployed-chummer-browser-probe.receipt.json",
        {
            "contractName": "chummer.origin_edition.deployed_browser_probe.v1",
            "status": "pass" if deployed_pass else "blocked",
            "logged_in_browser_verified": deployed_pass,
            "selected_face_cover_marker_visible": deployed_pass,
            "selected_face_cover_alt_visible": deployed_pass,
            "selected_face_cover_route_visible": deployed_pass,
            "selected_face_cover_visible": deployed_pass,
            "read_tab_visible": deployed_pass,
            "read_section_visible": deployed_pass,
            "listen_tab_visible": deployed_pass,
            "listen_section_visible": deployed_pass,
            "watch_tab_visible": deployed_pass,
            "watch_section_visible": deployed_pass,
            "canon_audit_tab_visible": deployed_pass,
            "canon_audit_content_verified": deployed_pass,
            "chummer_canon_owner_visible": deployed_pass,
            "provider_created_facts_blocked_visible": deployed_pass,
            "canon_privacy_receipts_present": deployed_pass,
            "no_fallback_media_verified": deployed_pass,
            "read_gate_verified": deployed_pass,
            "chummer_run_listen_gate_verified": deployed_pass,
            "watch_gate_verified": deployed_pass,
            "watch_artifact_nonempty": deployed_pass,
            "audiobook_share_url_trusted": deployed_pass,
            "dossier_share_url_trusted": deployed_pass,
            "audiobook_share_reachable": deployed_pass,
            "dossier_share_reachable": deployed_pass,
            "cover_artifact_nonempty": deployed_pass,
            "book_artifact_nonempty": deployed_pass,
            "cover_sha_matches_import": deployed_pass,
            "book_sha_matches_import": deployed_pass,
            "video_sha_matches_import": deployed_pass,
            "owner_playback_e2e_verified": deployed_pass,
            "unauthenticated_detail_redirect_verified": True,
            "unauthenticated_read_redirect_verified": True,
            "unauthenticated_listen_redirect_verified": True,
            "unauthenticated_book_redirect_verified": True,
            "unauthenticated_cover_redirect_verified": True,
            "unauthenticated_video_redirect_verified": True,
            "all_private_routes_login_protected": True,
            "blockers": [] if deployed_pass else ["missing_deployed_identity_token"],
        },
    )
    write_json(
        root / "ORIGIN_EDITION_GOLD_CURRENT_GAP_AUDIT.generated.json",
        {
            "contractName": "chummer.origin_dossier_gold_e2e_audit.v1",
            "status": "pass" if gold_pass else "blocked",
            "goalCompletionClaimAllowed": gold_pass,
            "failedCodes": [] if gold_pass else ["browser_deployed_probe_blocked:missing_deployed_identity_token"],
        },
    )
    write_json(
        root / "ORIGIN_DOSSIER_LIVE_IMPORT_REQUEST.generated.json",
        {
            "contractName": "chummer.origin_dossier_live_artifact_import_request.v1",
            "status": "pass",
            "chummerRunOwnerUrl": "https://chummer.run/account/work/origin-dossiers/varga-mira-kestrel",
            "evidence": {
                "storySceneCoverSha256": "a" * 64,
                "audiobookSha256": m4b_sha,
                "bookArtifactSha256": ebook_sha,
                "dossierVideoSha256": "d" * 64,
                "acceptedHumanizedManuscriptSha256": "e" * 64,
                "sourcePacketSha256": source_packet_sha,
            },
            "importRequest": {
                "projectId": "varga-mira-kestrel",
                "baseUrl": "https://chummer.run",
                "originEditionNamespace": "origin.chummer.run/Varga/Mira/Kestrel",
                "publicationState": "published_for_owner",
                "missingGoldRequirements": [],
                "sourcePacketPath": "approved-sample-runner-canon.json",
                "sourcePacketReceiptPath": "source-packet-approval.receipt.json",
                "canonAuditReceiptPath": "canon-privacy-audit.receipt.json",
                "providerManuscriptPath": "provider-manuscript-draft.md",
                "bookArtifactPath": "origin.chummer.run/Varga/Mira/Kestrel/dossier/ebook.epub",
                "ebookArtifactPath": "origin.chummer.run/Varga/Mira/Kestrel/dossier/ebook.epub",
                "ebookAudiobookshelfImportReceiptPath": "origin.chummer.run/Varga/Mira/Kestrel/dossier/audiobookshelf-dossier-import.receipt.json",
                "bookArtifactReceiptPath": "book-artifact-import.receipt.json",
                "bookArtifactUrl": "https://chummer.run/account/work/origin-dossiers/varga-mira-kestrel/book",
                "bookArtifactVerified": True,
                "audiobookPath": "origin.chummer.run/Varga/Mira/Kestrel/audiobook/kestrel-origin.m4b",
                "audiobookshelfAudiobookShareUrl": "https://audiobookshelf.girschele.com/audiobookshelf/share/audiobook-test",
                "audiobookshelfDossierShareUrl": "https://audiobookshelf.girschele.com/audiobookshelf/share/dossier-test",
                "audiobookshelfPlaybackVerified": True,
                "dossierVideoPath": "origin.chummer.run/Varga/Mira/Kestrel/movie/movie.mp4",
                "dossierVideoUrl": "https://chummer.run/account/work/origin-dossiers/varga-mira-kestrel/video",
                "dossierVideoVerified": True,
                "m4bProviderImportReceiptPath": "origin.chummer.run/Varga/Mira/Kestrel/audiobook/m4b-provider-import-gate.receipt.json",
                "audiobookshelfImportReceiptPath": "origin.chummer.run/Varga/Mira/Kestrel/audiobook/audiobookshelf-import.receipt.json",
                "dossierVideoReceiptPath": "origin.chummer.run/Varga/Mira/Kestrel/movie/dossier-video.receipt.json",
                "telegramShareDeliveryReceiptPath": "origin.chummer.run/Varga/Mira/Kestrel/telegram-origin-link-bundle-live.receipt.json",
                "finalNoFallbackNoSentinelAuditReceiptPath": "origin.chummer.run/Varga/Mira/Kestrel/final-no-fallback-no-sentinel-audit.receipt.json",
            },
        },
    )


def rewrite_seeded_bundle_namespace(root: Path, *, namespace: str, project_id: str) -> None:
    old_namespace = "origin.chummer.run/Varga/Mira/Kestrel"
    old_project = "varga-mira-kestrel"
    old_branch = root / old_namespace
    new_branch = root / namespace
    new_branch.parent.mkdir(parents=True, exist_ok=True)
    old_branch.rename(new_branch)
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        updated = text.replace(old_namespace, namespace).replace(old_project, project_id)
        if updated != text:
            path.write_text(updated, encoding="utf-8")
    import_path = root / "ORIGIN_DOSSIER_LIVE_IMPORT_REQUEST.generated.json"
    live_import = json.loads(import_path.read_text(encoding="utf-8"))
    live_import["importRequest"]["originEditionNamespace"] = namespace
    live_import["importRequest"]["projectId"] = project_id
    live_import["chummerRunOwnerUrl"] = f"https://chummer.run/account/work/origin-dossiers/{project_id}"
    write_json(import_path, live_import)


def test_completion_matrix_requires_live_import_origin_namespace(tmp_path: Path) -> None:
    module = load_module()
    seed_bundle(tmp_path, deployed_pass=True, gold_pass=True)
    import_path = tmp_path / "ORIGIN_DOSSIER_LIVE_IMPORT_REQUEST.generated.json"
    live_import = json.loads(import_path.read_text(encoding="utf-8"))
    live_import["importRequest"].pop("originEditionNamespace", None)
    write_json(import_path, live_import)

    try:
        module.materialize(tmp_path, tmp_path / "matrix.json")
    except ValueError as exc:
        assert "live import request missing explicit Origin Edition context" in str(exc)
        assert "originEditionNamespace" in str(exc)
    else:
        raise AssertionError("completion matrix accepted missing originEditionNamespace")


def test_completion_matrix_requires_live_import_base_url(tmp_path: Path) -> None:
    module = load_module()
    seed_bundle(tmp_path, deployed_pass=True, gold_pass=True)
    import_path = tmp_path / "ORIGIN_DOSSIER_LIVE_IMPORT_REQUEST.generated.json"
    live_import = json.loads(import_path.read_text(encoding="utf-8"))
    live_import["importRequest"].pop("baseUrl", None)
    live_import["importRequest"].pop("chummerBaseUrl", None)
    live_import["importRequest"].pop("originEditionBaseUrl", None)
    write_json(import_path, live_import)

    try:
        module.materialize(tmp_path, tmp_path / "matrix.json")
    except ValueError as exc:
        assert "live import request missing explicit Origin Edition context" in str(exc)
        assert "baseUrl" in str(exc)
    else:
        raise AssertionError("completion matrix accepted missing baseUrl")


def test_completion_matrix_blocks_until_deployed_login_probe_and_gold_audit_pass(tmp_path: Path) -> None:
    module = load_module()
    seed_bundle(tmp_path, deployed_pass=False, gold_pass=False)

    result = module.materialize(tmp_path, tmp_path / "matrix.json")

    assert result["status"] == "blocked"
    assert result["goalCompletionClaimAllowed"] is False
    assert "deployed_user_login_read_listen_watch" in result["blockedRows"]
    assert "gold_audit_completion_claim_allowed" in result["blockedHardGates"]


def test_completion_matrix_uses_origin_edition_namespace_from_import_request(tmp_path: Path) -> None:
    module = load_module()
    namespace = "origin.chummer.run/Case/Ari/Ghost"
    project_id = "custom-runner"
    seed_bundle(tmp_path, deployed_pass=True, gold_pass=True)
    rewrite_seeded_bundle_namespace(tmp_path, namespace=namespace, project_id=project_id)

    result = module.materialize(tmp_path, tmp_path / "matrix.json")
    ebook = next(row for row in result["rows"] if row["id"] == "ebook_artifact_namespace")
    movie = next(row for row in result["rows"] if row["id"] == "movie_artifact_namespace")

    assert result["namespace"] == namespace
    assert result["projectId"] == project_id
    assert ebook["status"] == "proved"
    assert movie["status"] == "proved"


def test_completion_matrix_passes_when_all_rows_and_hard_gates_pass(tmp_path: Path) -> None:
    module = load_module()
    seed_bundle(tmp_path, deployed_pass=True, gold_pass=True)

    result = module.materialize(tmp_path, tmp_path / "matrix.json")

    assert result["status"] == "pass"
    assert result["finalVerdict"] == "ORIGIN_EDITION_GOLD_READY"
    assert result["goalCompletionClaimAllowed"] is True
    assert result["blockedRows"] == []
    assert result["blockedHardGates"] == []


def test_completion_matrix_blocks_when_deployed_private_route_protection_is_incomplete(tmp_path: Path) -> None:
    module = load_module()
    seed_bundle(tmp_path, deployed_pass=True, gold_pass=True)
    probe_path = tmp_path / "origin.chummer.run/Varga/Mira/Kestrel/deployed-chummer-browser-probe.receipt.json"
    probe = json.loads(probe_path.read_text(encoding="utf-8"))
    probe["unauthenticated_video_redirect_verified"] = False
    probe["all_private_routes_login_protected"] = False
    probe["blockers"] = ["unauthenticated_video_redirect_verified", "all_private_routes_login_protected"]
    write_json(probe_path, probe)

    result = module.materialize(tmp_path, tmp_path / "matrix.json")
    deployed_row = next(row for row in result["rows"] if row["id"] == "deployed_user_login_read_listen_watch")

    assert result["status"] == "blocked"
    assert result["goalCompletionClaimAllowed"] is False
    assert "deployed_user_login_read_listen_watch" in result["blockedRows"]
    assert deployed_row["flags"]["unauthenticated_video_redirect_verified"] is False
    assert deployed_row["flags"]["all_private_routes_login_protected"] is False


def test_completion_matrix_blocks_when_deployed_audiobook_share_is_untrusted(tmp_path: Path) -> None:
    module = load_module()
    seed_bundle(tmp_path, deployed_pass=True, gold_pass=True)
    probe_path = tmp_path / "origin.chummer.run/Varga/Mira/Kestrel/deployed-chummer-browser-probe.receipt.json"
    probe = json.loads(probe_path.read_text(encoding="utf-8"))
    probe["audiobook_share_url_trusted"] = False
    probe["blockers"] = ["audiobook_share_url_trusted"]
    write_json(probe_path, probe)

    result = module.materialize(tmp_path, tmp_path / "matrix.json")
    deployed_row = next(row for row in result["rows"] if row["id"] == "deployed_user_login_read_listen_watch")

    assert result["status"] == "blocked"
    assert result["goalCompletionClaimAllowed"] is False
    assert "deployed_user_login_read_listen_watch" in result["blockedRows"]
    assert deployed_row["flags"]["audiobook_share_url_trusted"] is False


def test_completion_matrix_blocks_when_deployed_audiobook_share_is_unreachable(tmp_path: Path) -> None:
    module = load_module()
    seed_bundle(tmp_path, deployed_pass=True, gold_pass=True)
    probe_path = tmp_path / "origin.chummer.run/Varga/Mira/Kestrel/deployed-chummer-browser-probe.receipt.json"
    probe = json.loads(probe_path.read_text(encoding="utf-8"))
    probe["audiobook_share_reachable"] = False
    probe["blockers"] = ["audiobook_share_reachable"]
    write_json(probe_path, probe)

    result = module.materialize(tmp_path, tmp_path / "matrix.json")
    deployed_row = next(row for row in result["rows"] if row["id"] == "deployed_user_login_read_listen_watch")

    assert result["status"] == "blocked"
    assert result["goalCompletionClaimAllowed"] is False
    assert "deployed_user_login_read_listen_watch" in result["blockedRows"]
    assert deployed_row["flags"]["audiobook_share_reachable"] is False


def test_completion_matrix_blocks_when_deployed_movie_body_is_empty(tmp_path: Path) -> None:
    module = load_module()
    seed_bundle(tmp_path, deployed_pass=True, gold_pass=True)
    probe_path = tmp_path / "origin.chummer.run/Varga/Mira/Kestrel/deployed-chummer-browser-probe.receipt.json"
    probe = json.loads(probe_path.read_text(encoding="utf-8"))
    probe["watch_artifact_nonempty"] = False
    probe["blockers"] = ["watch_artifact_nonempty"]
    write_json(probe_path, probe)

    result = module.materialize(tmp_path, tmp_path / "matrix.json")
    deployed_row = next(row for row in result["rows"] if row["id"] == "deployed_user_login_read_listen_watch")

    assert result["status"] == "blocked"
    assert result["goalCompletionClaimAllowed"] is False
    assert "deployed_user_login_read_listen_watch" in result["blockedRows"]
    assert deployed_row["flags"]["watch_artifact_nonempty"] is False


def test_completion_matrix_blocks_when_deployed_movie_hash_mismatches_import(tmp_path: Path) -> None:
    module = load_module()
    seed_bundle(tmp_path, deployed_pass=True, gold_pass=True)
    probe_path = tmp_path / "origin.chummer.run/Varga/Mira/Kestrel/deployed-chummer-browser-probe.receipt.json"
    probe = json.loads(probe_path.read_text(encoding="utf-8"))
    probe["video_sha_matches_import"] = False
    probe["blockers"] = ["video_sha_matches_import"]
    write_json(probe_path, probe)

    result = module.materialize(tmp_path, tmp_path / "matrix.json")
    deployed_row = next(row for row in result["rows"] if row["id"] == "deployed_user_login_read_listen_watch")

    assert result["status"] == "blocked"
    assert result["goalCompletionClaimAllowed"] is False
    assert "deployed_user_login_read_listen_watch" in result["blockedRows"]
    assert deployed_row["flags"]["video_sha_matches_import"] is False


def test_completion_matrix_blocks_when_deployed_canon_audit_content_is_missing(tmp_path: Path) -> None:
    module = load_module()
    seed_bundle(tmp_path, deployed_pass=True, gold_pass=True)
    probe_path = tmp_path / "origin.chummer.run/Varga/Mira/Kestrel/deployed-chummer-browser-probe.receipt.json"
    probe = json.loads(probe_path.read_text(encoding="utf-8"))
    probe["canon_audit_content_verified"] = False
    probe["chummer_canon_owner_visible"] = False
    probe["blockers"] = ["canon_audit_content_verified", "chummer_canon_owner_visible"]
    write_json(probe_path, probe)

    result = module.materialize(tmp_path, tmp_path / "matrix.json")
    deployed_row = next(row for row in result["rows"] if row["id"] == "deployed_user_login_read_listen_watch")

    assert result["status"] == "blocked"
    assert result["goalCompletionClaimAllowed"] is False
    assert "deployed_user_login_read_listen_watch" in result["blockedRows"]
    assert deployed_row["flags"]["canon_audit_content_verified"] is False
    assert deployed_row["flags"]["chummer_canon_owner_visible"] is False


def test_completion_matrix_blocks_artifacts_outside_required_origin_branches(tmp_path: Path) -> None:
    module = load_module()
    seed_bundle(tmp_path, deployed_pass=True, gold_pass=True)
    misplaced = tmp_path / "elsewhere"
    write_file(misplaced / "ebook.epub", b"epub")
    write_file(misplaced / "kestrel-origin.m4b", b"m4b")
    write_file(misplaced / "movie.mp4", b"mp4")
    write_file(misplaced / "m4b-provider-import-gate.receipt.json", "{}")
    write_file(misplaced / "audiobookshelf-import.receipt.json", "{}")
    write_file(misplaced / "dossier-video.receipt.json", "{}")
    import_path = tmp_path / "ORIGIN_DOSSIER_LIVE_IMPORT_REQUEST.generated.json"
    live_import = json.loads(import_path.read_text(encoding="utf-8"))
    request = live_import["importRequest"]
    request["bookArtifactPath"] = "elsewhere/ebook.epub"
    request["ebookArtifactPath"] = "elsewhere/ebook.epub"
    request["audiobookPath"] = "elsewhere/kestrel-origin.m4b"
    request["dossierVideoPath"] = "elsewhere/movie.mp4"
    request["m4bProviderImportReceiptPath"] = "elsewhere/m4b-provider-import-gate.receipt.json"
    request["audiobookshelfImportReceiptPath"] = "elsewhere/audiobookshelf-import.receipt.json"
    request["dossierVideoReceiptPath"] = "elsewhere/dossier-video.receipt.json"
    write_json(import_path, live_import)

    result = module.materialize(tmp_path, tmp_path / "matrix.json")
    blocked = {row["id"] for row in result["rows"] if row["status"] != "proved"}

    assert result["status"] == "blocked"
    assert "ebook_artifact_namespace" in blocked
    assert "m4b_provider_receipt_namespace" in blocked
    assert "m4b_artifact_namespace" in blocked
    assert "audiobookshelf_import_receipt_namespace" in blocked
    assert "movie_generation_receipt_namespace" in blocked
    assert "movie_artifact_namespace" in blocked


def test_completion_matrix_blocks_missing_explicit_ebook_import_fields(tmp_path: Path) -> None:
    module = load_module()
    seed_bundle(tmp_path, deployed_pass=True, gold_pass=True)
    import_path = tmp_path / "ORIGIN_DOSSIER_LIVE_IMPORT_REQUEST.generated.json"
    live_import = json.loads(import_path.read_text(encoding="utf-8"))
    request = live_import["importRequest"]
    request.pop("ebookArtifactPath", None)
    request.pop("ebookAudiobookshelfImportReceiptPath", None)
    write_json(import_path, live_import)

    result = module.materialize(tmp_path, tmp_path / "matrix.json")
    blocked = {row["id"] for row in result["rows"] if row["status"] != "proved"}

    assert result["status"] == "blocked"
    assert "ebook_artifact_file" in blocked
    assert "ebook_artifact_namespace" in blocked
    assert "ebook_audiobookshelf_import_receipt" in blocked
    assert "ebook_audiobookshelf_import_receipt_namespace" in blocked


def test_completion_matrix_blocks_missing_required_cover_surface(tmp_path: Path) -> None:
    module = load_module()
    seed_bundle(tmp_path, deployed_pass=True, gold_pass=True)
    cover_consistency_receipt(
        tmp_path / "origin.chummer.run/Varga/Mira/Kestrel/cover-consistency-strict.receipt.json",
        missing_surface="movie_poster",
    )

    result = module.materialize(tmp_path, tmp_path / "matrix.json")
    row = next(item for item in result["rows"] if item["id"] == "cover_consistency_required_surfaces")

    assert result["status"] == "blocked"
    assert "cover_consistency_required_surfaces" in result["blockedRows"]
    assert row["status"] == "blocked"
    assert row["flags"]["movie_poster"] is False
    assert row["blockedSurfaces"] == ["movie_poster"]


def test_completion_matrix_blocks_cover_surface_that_passes_with_wrong_hash(tmp_path: Path) -> None:
    module = load_module()
    seed_bundle(tmp_path, deployed_pass=True, gold_pass=True)
    receipt_path = tmp_path / "origin.chummer.run/Varga/Mira/Kestrel/cover-consistency-strict.receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    for surface in receipt["surfaces"]:
        if surface["name"] == "audiobookshelf_audiobook_cover":
            surface["sha256"] = "b" * 64
    write_json(receipt_path, receipt)

    result = module.materialize(tmp_path, tmp_path / "matrix.json")
    row = next(item for item in result["rows"] if item["id"] == "cover_consistency_required_surfaces")

    assert result["status"] == "blocked"
    assert "cover_consistency_required_surfaces" in result["blockedRows"]
    assert row["flags"]["audiobookshelf_audiobook_cover"] is True
    assert row["flags"]["all_required_surface_hashes_match_expected"] is False
    assert row["coverHashMismatchedSurfaces"] == ["audiobookshelf_audiobook_cover"]


def test_completion_matrix_blocks_cover_consistency_without_valid_expected_hash(tmp_path: Path) -> None:
    module = load_module()
    seed_bundle(tmp_path, deployed_pass=True, gold_pass=True)
    receipt_path = tmp_path / "origin.chummer.run/Varga/Mira/Kestrel/cover-consistency-strict.receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["expectedCoverSha256"] = ""
    write_json(receipt_path, receipt)

    result = module.materialize(tmp_path, tmp_path / "matrix.json")
    row = next(item for item in result["rows"] if item["id"] == "cover_consistency_required_surfaces")

    assert result["status"] == "blocked"
    assert row["flags"]["expected_cover_sha_valid"] is False
    assert "expected_cover_sha_valid" in row["blockedSurfaces"]


def test_completion_matrix_blocks_mismatched_telegram_origin_link_hash(tmp_path: Path) -> None:
    module = load_module()
    seed_bundle(tmp_path, deployed_pass=True, gold_pass=True)
    telegram_origin_link_receipt(
        tmp_path / "origin.chummer.run/Varga/Mira/Kestrel/telegram-origin-link-bundle-live.receipt.json",
        watch_hash="0" * 64,
    )

    result = module.materialize(tmp_path, tmp_path / "matrix.json")
    row = next(item for item in result["rows"] if item["id"] == "telegram_origin_links_verified")

    assert result["status"] == "blocked"
    assert "telegram_origin_links_verified" in result["blockedRows"]
    assert row["status"] == "blocked"
    assert row["flags"]["watch_link_hash_matches"] is False
    assert "watch_link_hash_matches" in row["failedFlags"]


def test_completion_matrix_blocks_failed_telegram_origin_link_receipt(tmp_path: Path) -> None:
    module = load_module()
    seed_bundle(tmp_path, deployed_pass=True, gold_pass=True)
    telegram_origin_link_receipt(
        tmp_path / "origin.chummer.run/Varga/Mira/Kestrel/telegram-origin-link-bundle-live.receipt.json",
        status="blocked",
    )

    result = module.materialize(tmp_path, tmp_path / "matrix.json")
    row = next(item for item in result["rows"] if item["id"] == "telegram_origin_links_verified")

    assert result["status"] == "blocked"
    assert "telegram_origin_links_verified" in result["blockedRows"]
    assert row["flags"]["telegram_receipt_status_pass"] is False
    assert "telegram_receipt_status_pass" in row["failedFlags"]


def test_completion_matrix_blocks_telegram_origin_link_raw_url_exposure(tmp_path: Path) -> None:
    module = load_module()
    seed_bundle(tmp_path, deployed_pass=True, gold_pass=True)
    receipt_path = tmp_path / "origin.chummer.run/Varga/Mira/Kestrel/telegram-origin-link-bundle-live.receipt.json"
    telegram_origin_link_receipt(receipt_path)
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["selected_delivery"]["origin_edition_link_bundle"]["raw_urls_exposed"] = True
    write_json(receipt_path, receipt)

    result = module.materialize(tmp_path, tmp_path / "matrix.json")
    row = next(item for item in result["rows"] if item["id"] == "telegram_origin_links_verified")

    assert result["status"] == "blocked"
    assert row["flags"]["raw_urls_not_exposed"] is False
    assert "raw_urls_not_exposed" in row["failedFlags"]


def test_completion_matrix_blocks_telegram_origin_links_without_message_binding(tmp_path: Path) -> None:
    module = load_module()
    seed_bundle(tmp_path, deployed_pass=True, gold_pass=True)
    receipt_path = tmp_path / "origin.chummer.run/Varga/Mira/Kestrel/telegram-origin-link-bundle-live.receipt.json"
    telegram_origin_link_receipt(receipt_path)
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["selected_delivery"]["telegram_message_bound"] = False
    receipt["selected_delivery"]["telegram_delivery_message_id_present"] = False
    write_json(receipt_path, receipt)

    result = module.materialize(tmp_path, tmp_path / "matrix.json")
    row = next(item for item in result["rows"] if item["id"] == "telegram_origin_links_verified")

    assert result["status"] == "blocked"
    assert "telegram_origin_links_verified" in result["blockedRows"]
    assert row["flags"]["telegram_message_bound"] is False
    assert row["flags"]["telegram_selected_delivery_message_id_present"] is False
    assert "telegram_message_bound" in row["failedFlags"]
    assert "telegram_selected_delivery_message_id_present" in row["failedFlags"]


def test_completion_matrix_blocks_telegram_origin_link_namespace_hash_mismatch(tmp_path: Path) -> None:
    module = load_module()
    seed_bundle(tmp_path, deployed_pass=True, gold_pass=True)
    receipt_path = tmp_path / "origin.chummer.run/Varga/Mira/Kestrel/telegram-origin-link-bundle-live.receipt.json"
    telegram_origin_link_receipt(receipt_path, namespace="origin.chummer.run/Other/Runner/Name")

    result = module.materialize(tmp_path, tmp_path / "matrix.json")
    row = next(item for item in result["rows"] if item["id"] == "telegram_origin_links_verified")

    assert result["status"] == "blocked"
    assert row["flags"]["origin_namespace_hash_matches"] is False
    assert "origin_namespace_hash_matches" in row["failedFlags"]


def test_completion_matrix_blocks_when_provider_created_facts_guard_missing(tmp_path: Path) -> None:
    module = load_module()
    seed_bundle(tmp_path, deployed_pass=True, gold_pass=True)
    canon_path = tmp_path / "canon-privacy-audit.receipt.json"
    canon = json.loads(canon_path.read_text(encoding="utf-8"))
    canon["tokens"] = [
        token
        for token in canon["tokens"]
        if token != "no_provider_created_facts_entered_canon"
    ]
    write_json(canon_path, canon)

    result = module.materialize(tmp_path, tmp_path / "matrix.json")
    row = next(item for item in result["rows"] if item["id"] == "chummer_canon_authority_verified")

    assert result["status"] == "blocked"
    assert "chummer_canon_authority_verified" in result["blockedRows"]
    assert row["status"] == "blocked"
    assert row["flags"]["no_provider_created_facts_entered_canon"] is False
    assert "no_provider_created_facts_entered_canon" in row["failedFlags"]


def test_completion_matrix_blocks_when_canon_authority_packet_does_not_assign_chummer_fact_ownership(tmp_path: Path) -> None:
    module = load_module()
    seed_bundle(tmp_path, deployed_pass=True, gold_pass=True)
    source_path = tmp_path / "approved-sample-runner-canon.json"
    source_packet = json.loads(source_path.read_text(encoding="utf-8"))
    source_packet["canonOwnsFacts"] = "Provider"
    write_json(source_path, source_packet)

    result = module.materialize(tmp_path, tmp_path / "matrix.json")
    row = next(item for item in result["rows"] if item["id"] == "chummer_canon_authority_verified")

    assert result["status"] == "blocked"
    assert "chummer_canon_authority_verified" in result["blockedRows"]
    assert row["flags"]["chummer_owns_facts"] is False
    assert "chummer_owns_facts" in row["failedFlags"]


def test_completion_matrix_blocks_when_canon_authority_packet_allows_provider_created_canon(tmp_path: Path) -> None:
    module = load_module()
    seed_bundle(tmp_path, deployed_pass=True, gold_pass=True)
    source_path = tmp_path / "approved-sample-runner-canon.json"
    source_packet = json.loads(source_path.read_text(encoding="utf-8"))
    source_packet["prohibitedInventions"] = [
        item for item in source_packet["prohibitedInventions"] if item != "Do not make provider-created facts canonical."
    ]
    write_json(source_path, source_packet)

    result = module.materialize(tmp_path, tmp_path / "matrix.json")
    row = next(item for item in result["rows"] if item["id"] == "chummer_canon_authority_verified")

    assert result["status"] == "blocked"
    assert "chummer_canon_authority_verified" in result["blockedRows"]
    assert row["flags"]["prohibits_provider_created_canon"] is False
    assert "prohibits_provider_created_canon" in row["failedFlags"]


def test_completion_matrix_blocks_when_final_bundle_surface_is_blocked(tmp_path: Path) -> None:
    module = load_module()
    seed_bundle(tmp_path, deployed_pass=True, gold_pass=True)
    final_bundle_receipt(
        tmp_path / "origin.chummer.run/Varga/Mira/Kestrel/final-no-fallback-no-sentinel-audit.receipt.json",
        blocked_surface="real_m4b_artifact",
    )

    result = module.materialize(tmp_path, tmp_path / "matrix.json")
    row = next(item for item in result["rows"] if item["id"] == "final_bundle_no_fallback_no_sentinel_verified")

    assert result["status"] == "blocked"
    assert "final_bundle_no_fallback_no_sentinel_verified" in result["blockedRows"]
    assert row["status"] == "blocked"
    assert row["surfaceFlags"]["real_m4b_artifact"] is False
    assert "all_required_surfaces_present_and_passed" in row["failedFlags"]


def test_completion_matrix_blocks_when_generated_receipt_exposes_secret_marker(tmp_path: Path) -> None:
    module = load_module()
    seed_bundle(tmp_path, deployed_pass=True, gold_pass=True)
    write_json(tmp_path / "leaky-provider-receipt.generated.json", {"debug": "Bearer secret-session"})

    result = module.materialize(tmp_path, tmp_path / "matrix.json")
    row = next(item for item in result["rows"] if item["id"] == "secret_hygiene_verified")

    assert result["status"] == "blocked"
    assert "secret_hygiene_verified" in result["blockedRows"]
    assert "no_committed_or_receipt_secrets_claimed" in result["blockedHardGates"]
    assert row["status"] == "blocked"
    assert row["flags"]["receipt_secret_marker_scan_clean"] is False
    assert row["receiptFindings"] != []


def test_completion_matrix_blocks_when_generated_receipt_exposes_provider_or_transport_secret_marker(tmp_path: Path) -> None:
    module = load_module()
    seed_bundle(tmp_path, deployed_pass=True, gold_pass=True)
    write_json(
        tmp_path / "leaky-transport-receipt.generated.json",
        {
            "debug": "Cookie: synthetic-session",
            "provider": "https://api.telegram.org/botREDACTED/sendMessage",
            "operator_note": "api: synthetic-token",
        },
    )

    result = module.materialize(tmp_path, tmp_path / "matrix.json")
    row = next(item for item in result["rows"] if item["id"] == "secret_hygiene_verified")

    assert result["status"] == "blocked"
    assert "secret_hygiene_verified" in result["blockedRows"]
    assert row["status"] == "blocked"
    assert row["flags"]["receipt_secret_marker_scan_clean"] is False
    markers = {finding["marker"] for finding in row["receiptFindings"]}
    assert "Cookie:" in markers
    assert "api.telegram.org/bot" in markers
    assert "api:" in markers


def test_completion_matrix_allows_safe_env_key_names_but_blocks_value_assignments(tmp_path: Path) -> None:
    module = load_module()
    seed_bundle(tmp_path, deployed_pass=True, gold_pass=True)
    write_json(
        tmp_path / "safe-env-key-reference.generated.json",
        {"requiredEnv": ["UNMIXR_API_KEY", "EA_TELEGRAM_BOT_TOKEN"]},
    )

    safe_result = module.materialize(tmp_path, tmp_path / "safe-matrix.json")
    safe_row = next(item for item in safe_result["rows"] if item["id"] == "secret_hygiene_verified")

    assert safe_row["status"] == "proved"

    write_json(
        tmp_path / "leaky-env-assignment.generated.json",
        {"debug": "UNMIXR_API_KEY=synthetic-token"},
    )
    blocked_result = module.materialize(tmp_path, tmp_path / "blocked-matrix.json")
    blocked_row = next(item for item in blocked_result["rows"] if item["id"] == "secret_hygiene_verified")

    assert blocked_result["status"] == "blocked"
    assert blocked_row["status"] == "blocked"
    markers = {finding["marker"] for finding in blocked_row["receiptFindings"]}
    assert "UNMIXR_API_KEY=" in markers


def test_completion_matrix_blocks_when_provider_direct_publish_signal_is_present(tmp_path: Path) -> None:
    module = load_module()
    seed_bundle(tmp_path, deployed_pass=True, gold_pass=True)
    provider_path = tmp_path / "origin.chummer.run/Varga/Mira/Kestrel/audiobook/m4b-provider-import-gate.receipt.json"
    provider = json.loads(provider_path.read_text(encoding="utf-8"))
    provider["providerPublished"] = True
    write_json(provider_path, provider)

    result = module.materialize(tmp_path, tmp_path / "matrix.json")
    row = next(item for item in result["rows"] if item["id"] == "provider_publish_boundary_verified")

    assert result["status"] == "blocked"
    assert "provider_publish_boundary_verified" in result["blockedRows"]
    assert "no_provider_direct_publish" in result["blockedHardGates"]
    assert row["status"] == "blocked"
    assert row["flags"]["no_direct_provider_publish_signals"] is False
    assert row["directPublishFindings"] != []


def test_completion_matrix_blocks_when_audiobookshelf_dossier_share_mismatches_receipt(tmp_path: Path) -> None:
    module = load_module()
    seed_bundle(tmp_path, deployed_pass=True, gold_pass=True)
    import_path = tmp_path / "ORIGIN_DOSSIER_LIVE_IMPORT_REQUEST.generated.json"
    live_import = json.loads(import_path.read_text(encoding="utf-8"))
    live_import["importRequest"]["audiobookshelfDossierShareUrl"] = "https://example.invalid/not-audiobookshelf-share"
    write_json(import_path, live_import)

    result = module.materialize(tmp_path, tmp_path / "matrix.json")
    row = next(item for item in result["rows"] if item["id"] == "audiobookshelf_dossier_and_audiobook_share_verified")

    assert result["status"] == "blocked"
    assert "audiobookshelf_dossier_and_audiobook_share_verified" in result["blockedRows"]
    assert "audiobookshelf_dossier_and_audiobook_shared" in result["blockedHardGates"]
    assert row["status"] == "blocked"
    assert row["flags"]["dossier_share_url_matches_receipt"] is False
    assert row["flags"]["dossier_share_url_is_audiobookshelf"] is False


def test_completion_matrix_blocks_when_movie_uses_marker_media(tmp_path: Path) -> None:
    module = load_module()
    seed_bundle(tmp_path, deployed_pass=True, gold_pass=True)
    movie_receipt_path = tmp_path / "origin.chummer.run/Varga/Mira/Kestrel/movie/dossier-video.receipt.json"
    movie = json.loads(movie_receipt_path.read_text(encoding="utf-8"))
    movie["storySceneProof"]["markerMediaUsed"] = True
    write_json(movie_receipt_path, movie)

    result = module.materialize(tmp_path, tmp_path / "matrix.json")
    row = next(item for item in result["rows"] if item["id"] == "chummer_movie_story_scene_playback_verified")

    assert result["status"] == "blocked"
    assert "chummer_movie_story_scene_playback_verified" in result["blockedRows"]
    assert "chummer_movie_story_scene_playback_verified" in result["blockedHardGates"]
    assert row["status"] == "blocked"
    assert row["flags"]["marker_media_not_used"] is False
    assert "marker_media_not_used" in row["failedFlags"]


def test_completion_matrix_accepts_movie_with_generic_approved_premium_narration_flag(tmp_path: Path) -> None:
    module = load_module()
    seed_bundle(tmp_path, deployed_pass=True, gold_pass=True)
    movie_receipt_path = tmp_path / "origin.chummer.run/Varga/Mira/Kestrel/movie/dossier-video.receipt.json"
    movie = json.loads(movie_receipt_path.read_text(encoding="utf-8"))
    movie["storySceneProof"].pop("usesUnmixrNarrationAudio", None)
    movie["storySceneProof"].pop("usesInkfluenceNarrationAudio", None)
    movie["storySceneProof"]["usesApprovedPremiumNarrationAudio"] = True
    write_json(movie_receipt_path, movie)

    result = module.materialize(tmp_path, tmp_path / "matrix.json")
    row = next(item for item in result["rows"] if item["id"] == "chummer_movie_story_scene_playback_verified")

    assert row["status"] == "proved"
    assert row["flags"]["uses_approved_premium_narration_audio"] is True


def test_completion_matrix_blocks_when_pdf_manuscript_hash_mismatches_accepted_text(tmp_path: Path) -> None:
    module = load_module()
    seed_bundle(tmp_path, deployed_pass=True, gold_pass=True)
    pdf_receipt_path = tmp_path / "origin.chummer.run/Varga/Mira/Kestrel/dossier/pdf-cover.receipt.json"
    pdf_receipt = json.loads(pdf_receipt_path.read_text(encoding="utf-8"))
    pdf_receipt["manuscriptSha256"] = "0" * 64
    write_json(pdf_receipt_path, pdf_receipt)

    result = module.materialize(tmp_path, tmp_path / "matrix.json")
    row = next(item for item in result["rows"] if item["id"] == "dossier_ebook_pdf_packaging_verified")

    assert result["status"] == "blocked"
    assert "dossier_ebook_pdf_packaging_verified" in result["blockedRows"]
    assert "dossier_ebook_pdf_packaging_verified" in result["blockedHardGates"]
    assert row["status"] == "blocked"
    assert row["flags"]["pdf_manuscript_sha_matches_accepted"] is False
    assert "pdf_manuscript_sha_matches_accepted" in row["failedFlags"]


def test_completion_matrix_allows_inkfluence_as_approved_premium_audio_provider(tmp_path: Path) -> None:
    module = load_module()
    seed_bundle(tmp_path, deployed_pass=True, gold_pass=True)
    provider_path = tmp_path / "origin.chummer.run/Varga/Mira/Kestrel/audiobook/unmixr-provider-m4b.receipt.json"
    provider = json.loads(provider_path.read_text(encoding="utf-8"))
    provider["provider"] = "Inkfluence"
    provider["voiceProvider"] = "Inkfluence"
    provider["tokens"] = [
        token.replace("provider:Unmixr", "provider:Inkfluence")
        for token in provider["tokens"]
    ]
    write_json(provider_path, provider)
    gate_path = tmp_path / "origin.chummer.run/Varga/Mira/Kestrel/audiobook/m4b-provider-import-gate.receipt.json"
    gate = json.loads(gate_path.read_text(encoding="utf-8"))
    gate["tokens"] = [
        token.replace("provider:Unmixr", "provider:Inkfluence")
        for token in gate["tokens"]
    ]
    gate["providerReceiptSha256"] = hashlib.sha256(provider_path.read_bytes()).hexdigest()
    write_json(gate_path, gate)

    result = module.materialize(tmp_path, tmp_path / "matrix.json")
    row = next(item for item in result["rows"] if item["id"] == "m4b_premium_narration_import_verified")

    assert row["status"] == "proved"
    assert row["approvedAudioProvider"] == "Inkfluence"
    assert row["flags"]["provider_is_approved_premium_narration_provider"] is True


def test_completion_matrix_allows_configured_premium_audio_provider(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CHUMMER_ORIGIN_AUDIO_PROVIDER_TOKENS", "premiumvoice")
    module = load_module()
    seed_bundle(tmp_path, deployed_pass=True, gold_pass=True)
    provider_label = "PremiumVoice Account 04"
    provider_path = tmp_path / "origin.chummer.run/Varga/Mira/Kestrel/audiobook/unmixr-provider-m4b.receipt.json"
    provider = json.loads(provider_path.read_text(encoding="utf-8"))
    provider["provider"] = provider_label
    provider["voiceProvider"] = provider_label
    provider["tokens"] = [
        token.replace("provider:Unmixr", f"provider:{provider_label}")
        for token in provider["tokens"]
    ]
    write_json(provider_path, provider)
    gate_path = tmp_path / "origin.chummer.run/Varga/Mira/Kestrel/audiobook/m4b-provider-import-gate.receipt.json"
    gate = json.loads(gate_path.read_text(encoding="utf-8"))
    gate["tokens"] = [
        token.replace("provider:Unmixr", f"provider:{provider_label}")
        for token in gate["tokens"]
    ]
    gate["providerReceiptSha256"] = hashlib.sha256(provider_path.read_bytes()).hexdigest()
    write_json(gate_path, gate)

    result = module.materialize(tmp_path, tmp_path / "matrix.json")
    row = next(item for item in result["rows"] if item["id"] == "m4b_premium_narration_import_verified")

    assert row["status"] == "proved"
    assert row["approvedAudioProvider"] == provider_label
    assert row["flags"]["provider_is_approved_premium_narration_provider"] is True
    assert row["flags"]["tokens_bind_approved_provider_and_cover_and_m4b"] is True


def test_completion_matrix_blocks_when_m4b_provider_is_not_approved_premium_provider(tmp_path: Path) -> None:
    module = load_module()
    seed_bundle(tmp_path, deployed_pass=True, gold_pass=True)
    provider_path = tmp_path / "origin.chummer.run/Varga/Mira/Kestrel/audiobook/unmixr-provider-m4b.receipt.json"
    provider = json.loads(provider_path.read_text(encoding="utf-8"))
    provider["provider"] = "FallbackTTS"
    provider["voiceProvider"] = "FallbackTTS"
    write_json(provider_path, provider)
    gate_path = tmp_path / "origin.chummer.run/Varga/Mira/Kestrel/audiobook/m4b-provider-import-gate.receipt.json"
    gate = json.loads(gate_path.read_text(encoding="utf-8"))
    gate["providerReceiptSha256"] = hashlib.sha256(provider_path.read_bytes()).hexdigest()
    write_json(gate_path, gate)

    result = module.materialize(tmp_path, tmp_path / "matrix.json")
    row = next(item for item in result["rows"] if item["id"] == "m4b_premium_narration_import_verified")

    assert result["status"] == "blocked"
    assert "m4b_premium_narration_import_verified" in result["blockedRows"]
    assert "m4b_premium_narration_import_verified" in result["blockedHardGates"]
    assert row["status"] == "blocked"
    assert row["flags"]["provider_is_approved_premium_narration_provider"] is False
    assert "provider_is_approved_premium_narration_provider" in row["failedFlags"]


def test_completion_matrix_blocks_disguised_m4b_provider_substring(tmp_path: Path) -> None:
    module = load_module()
    seed_bundle(tmp_path, deployed_pass=True, gold_pass=True)
    provider_path = tmp_path / "origin.chummer.run/Varga/Mira/Kestrel/audiobook/unmixr-provider-m4b.receipt.json"
    provider = json.loads(provider_path.read_text(encoding="utf-8"))
    provider["provider"] = "NotUnmixr Account 02"
    provider["voiceProvider"] = "NotUnmixr Account 02"
    write_json(provider_path, provider)
    gate_path = tmp_path / "origin.chummer.run/Varga/Mira/Kestrel/audiobook/m4b-provider-import-gate.receipt.json"
    gate = json.loads(gate_path.read_text(encoding="utf-8"))
    gate["providerReceiptSha256"] = hashlib.sha256(provider_path.read_bytes()).hexdigest()
    write_json(gate_path, gate)

    result = module.materialize(tmp_path, tmp_path / "matrix.json")
    row = next(item for item in result["rows"] if item["id"] == "m4b_premium_narration_import_verified")

    assert result["status"] == "blocked"
    assert row["flags"]["provider_is_approved_premium_narration_provider"] is False
    assert "provider_is_approved_premium_narration_provider" in row["failedFlags"]


def test_completion_matrix_blocks_when_local_authenticated_listen_tab_missing(tmp_path: Path) -> None:
    module = load_module()
    seed_bundle(tmp_path, deployed_pass=True, gold_pass=True)
    authenticated_route_receipt(
        tmp_path / "origin.chummer.run/Varga/Mira/Kestrel/authenticated-chummer-route-live.receipt.json",
        listen_tab_visible=False,
    )

    result = module.materialize(tmp_path, tmp_path / "matrix.json")
    row = next(item for item in result["rows"] if item["id"] == "local_authenticated_route_tabs_verified")

    assert result["status"] == "blocked"
    assert "local_authenticated_route_tabs_verified" in result["blockedRows"]
    assert "local_authenticated_route_tabs_verified" in result["blockedHardGates"]
    assert row["status"] == "blocked"
    assert row["flags"]["listen_tab_visible"] is False
    assert "listen_tab_visible" in row["failedFlags"]


def test_completion_matrix_blocks_when_local_authenticated_cover_marker_missing(tmp_path: Path) -> None:
    module = load_module()
    seed_bundle(tmp_path, deployed_pass=True, gold_pass=True)
    route_path = tmp_path / "origin.chummer.run/Varga/Mira/Kestrel/authenticated-chummer-route-live.receipt.json"
    route = json.loads(route_path.read_text(encoding="utf-8"))
    route["selected_face_cover_marker_visible"] = False
    write_json(route_path, route)

    result = module.materialize(tmp_path, tmp_path / "matrix.json")
    row = next(item for item in result["rows"] if item["id"] == "local_authenticated_route_tabs_verified")

    assert result["status"] == "blocked"
    assert "local_authenticated_route_tabs_verified" in result["blockedRows"]
    assert "local_authenticated_route_tabs_verified" in result["blockedHardGates"]
    assert row["status"] == "blocked"
    assert row["flags"]["selected_face_cover_marker_visible"] is False
    assert "selected_face_cover_marker_visible" in row["failedFlags"]


def test_completion_matrix_blocks_when_local_private_artifact_route_is_public(tmp_path: Path) -> None:
    module = load_module()
    seed_bundle(tmp_path, deployed_pass=True, gold_pass=True)
    route_path = tmp_path / "origin.chummer.run/Varga/Mira/Kestrel/authenticated-chummer-route-live.receipt.json"
    route = json.loads(route_path.read_text(encoding="utf-8"))
    route["anonymousVideoRedirectVerified"] = False
    route["anonymousArtifactRedirectVerified"] = False
    route["all_private_routes_login_protected"] = False
    write_json(route_path, route)

    result = module.materialize(tmp_path, tmp_path / "matrix.json")
    row = next(item for item in result["rows"] if item["id"] == "local_authenticated_route_tabs_verified")

    assert result["status"] == "blocked"
    assert "local_authenticated_route_tabs_verified" in result["blockedRows"]
    assert row["flags"]["anonymous_video_redirect_verified"] is False
    assert row["flags"]["all_private_routes_login_protected"] is False
    assert "anonymous_video_redirect_verified" in row["failedFlags"]
    assert "all_private_routes_login_protected" in row["failedFlags"]


def test_completion_matrix_blocks_when_local_authenticated_route_media_hash_mismatches_import(tmp_path: Path) -> None:
    module = load_module()
    seed_bundle(tmp_path, deployed_pass=True, gold_pass=True)
    route_path = tmp_path / "origin.chummer.run/Varga/Mira/Kestrel/authenticated-chummer-route-live.receipt.json"
    route = json.loads(route_path.read_text(encoding="utf-8"))
    route["video_sha_matches_import"] = False
    write_json(route_path, route)

    result = module.materialize(tmp_path, tmp_path / "matrix.json")
    row = next(item for item in result["rows"] if item["id"] == "local_authenticated_route_tabs_verified")

    assert result["status"] == "blocked"
    assert "local_authenticated_route_tabs_verified" in result["blockedRows"]
    assert "local_authenticated_route_tabs_verified" in result["blockedHardGates"]
    assert row["status"] == "blocked"
    assert row["flags"]["video_sha_matches_import"] is False
    assert "video_sha_matches_import" in row["failedFlags"]


def test_completion_matrix_accepts_local_authenticated_route_on_ephemeral_port(tmp_path: Path) -> None:
    module = load_module()
    seed_bundle(tmp_path, deployed_pass=True, gold_pass=True)
    authenticated_route_receipt(
        tmp_path / "origin.chummer.run/Varga/Mira/Kestrel/authenticated-chummer-route-live.receipt.json",
        local_base_url="http://127.0.0.1:47019",
    )

    result = module.materialize(tmp_path, tmp_path / "matrix.json")
    row = next(item for item in result["rows"] if item["id"] == "local_authenticated_route_tabs_verified")

    assert row["status"] == "proved"
    assert row["flags"]["local_route_urls_are_private_origin_routes"] is True
    assert row["flags"]["url_hashes_match_expected_local_routes"] is True
    assert "local_authenticated_route_tabs_verified" not in result["blockedRows"]


def test_completion_matrix_blocks_when_source_packet_external_consent_missing(tmp_path: Path) -> None:
    module = load_module()
    seed_bundle(tmp_path, deployed_pass=True, gold_pass=True)
    source_path = tmp_path / "approved-sample-runner-canon.json"
    source_packet = json.loads(source_path.read_text(encoding="utf-8"))
    source_packet["externalProcessingConsent"] = False
    write_json(source_path, source_packet)
    source_sha = hashlib.sha256(source_path.read_bytes()).hexdigest()
    import_path = tmp_path / "ORIGIN_DOSSIER_LIVE_IMPORT_REQUEST.generated.json"
    live_import = json.loads(import_path.read_text(encoding="utf-8"))
    live_import["evidence"]["sourcePacketSha256"] = source_sha
    write_json(import_path, live_import)
    source_receipt_path = tmp_path / "source-packet-approval.receipt.json"
    source_receipt = json.loads(source_receipt_path.read_text(encoding="utf-8"))
    source_receipt["artifactSha256"] = [source_sha]
    write_json(source_receipt_path, source_receipt)
    canon_path = tmp_path / "canon-privacy-audit.receipt.json"
    canon = json.loads(canon_path.read_text(encoding="utf-8"))
    canon["artifactSha256"][0] = source_sha
    write_json(canon_path, canon)

    result = module.materialize(tmp_path, tmp_path / "matrix.json")
    row = next(item for item in result["rows"] if item["id"] == "source_packet_integrity_and_consent_verified")

    assert result["status"] == "blocked"
    assert "source_packet_integrity_and_consent_verified" in result["blockedRows"]
    assert "source_packet_integrity_and_consent_verified" in result["blockedHardGates"]
    assert row["status"] == "blocked"
    assert row["flags"]["external_processing_consented_in_packet"] is False
    assert "external_processing_consented_in_packet" in row["failedFlags"]


def test_completion_matrix_blocks_when_runsite_rybbit_env_inspection_missing(tmp_path: Path) -> None:
    module = load_module()
    seed_bundle(tmp_path, deployed_pass=True, gold_pass=True)
    runsite_path = tmp_path / "origin.chummer.run/Varga/Mira/Kestrel/runsite-integration-proof.receipt.json"
    runsite = json.loads(runsite_path.read_text(encoding="utf-8"))
    runsite["inventoryInspection"]["rybbitRunKeysPresent"]["RYBBIT_CHUMMER_RUN_SCRIPT_URL"] = False
    write_json(runsite_path, runsite)

    result = module.materialize(tmp_path, tmp_path / "matrix.json")
    row = next(item for item in result["rows"] if item["id"] == "runsite_handoff_constraints_verified")

    assert result["status"] == "blocked"
    assert "runsite_handoff_constraints_verified" in result["blockedRows"]
    assert "runsite_handoff_constraints_verified" in result["blockedHardGates"]
    assert row["status"] == "blocked"
    assert row["flags"]["rybbit_run_keys_present"] is False
    assert "rybbit_run_keys_present" in row["failedFlags"]


def test_completion_matrix_blocks_when_runsite_top_level_handoff_facts_missing(tmp_path: Path) -> None:
    module = load_module()
    seed_bundle(tmp_path, deployed_pass=True, gold_pass=True)
    runsite_path = tmp_path / "origin.chummer.run/Varga/Mira/Kestrel/runsite-integration-proof.receipt.json"
    runsite = json.loads(runsite_path.read_text(encoding="utf-8"))
    for key in [
        "runsiteHandoffVerified",
        "newestLtdsInspected",
        "envInspected",
        "rybbitEnvOnly",
        "secretValuesStored",
    ]:
        runsite.pop(key, None)
    write_json(runsite_path, runsite)

    result = module.materialize(tmp_path, tmp_path / "matrix.json")
    row = next(item for item in result["rows"] if item["id"] == "runsite_handoff_constraints_verified")

    assert result["status"] == "blocked"
    assert "runsite_handoff_constraints_verified" in result["blockedRows"]
    assert row["status"] == "blocked"
    assert "runsite_handoff_verified" in row["failedFlags"]
    assert "newest_ltds_inspected_top_level" in row["failedFlags"]
    assert "env_inspected_top_level" in row["failedFlags"]
    assert "rybbit_env_only_top_level" in row["failedFlags"]
    assert "secret_values_not_stored" in row["failedFlags"]


def test_completion_matrix_blocks_when_origin_gold_provider_capability_missing(tmp_path: Path) -> None:
    module = load_module()
    seed_bundle(tmp_path, deployed_pass=True, gold_pass=True)
    runsite_path = tmp_path / "origin.chummer.run/Varga/Mira/Kestrel/runsite-integration-proof.receipt.json"
    runsite = json.loads(runsite_path.read_text(encoding="utf-8"))
    runsite["inventoryInspection"]["originGoldCapabilitySignals"]["premium_audio_provider_available"] = False
    write_json(runsite_path, runsite)

    result = module.materialize(tmp_path, tmp_path / "matrix.json")
    row = next(item for item in result["rows"] if item["id"] == "runsite_handoff_constraints_verified")

    assert result["status"] == "blocked"
    assert row["flags"]["required_origin_gold_provider_capabilities_present"] is False
    assert "required_origin_gold_provider_capabilities_present" in row["failedFlags"]
    assert row["requiredOriginGoldCapabilities"] == [
        "manuscript_or_edition_provider_available",
        "optional_overflow_accounts_do_not_block",
        "premium_audio_provider_available",
        "provider_inventory_present",
    ]


def test_completion_matrix_blocks_when_runsite_secret_values_stored(tmp_path: Path) -> None:
    module = load_module()
    seed_bundle(tmp_path, deployed_pass=True, gold_pass=True)
    runsite_path = tmp_path / "origin.chummer.run/Varga/Mira/Kestrel/runsite-integration-proof.receipt.json"
    runsite = json.loads(runsite_path.read_text(encoding="utf-8"))
    runsite["secretValuesStored"] = True
    write_json(runsite_path, runsite)

    result = module.materialize(tmp_path, tmp_path / "matrix.json")
    row = next(item for item in result["rows"] if item["id"] == "runsite_handoff_constraints_verified")

    assert result["status"] == "blocked"
    assert row["flags"]["secret_values_not_stored"] is False
    assert "secret_values_not_stored" in row["failedFlags"]


def test_completion_matrix_accepts_absolute_paths_inside_origin_namespace(tmp_path: Path) -> None:
    module = load_module()
    seed_bundle(tmp_path, deployed_pass=True, gold_pass=True)
    import_path = tmp_path / "ORIGIN_DOSSIER_LIVE_IMPORT_REQUEST.generated.json"
    live_import = json.loads(import_path.read_text(encoding="utf-8"))
    request = live_import["importRequest"]
    for key in [
        "bookArtifactPath",
        "audiobookPath",
        "dossierVideoPath",
        "m4bProviderImportReceiptPath",
        "audiobookshelfImportReceiptPath",
        "dossierVideoReceiptPath",
    ]:
        request[key] = str(tmp_path / request[key])
    write_json(import_path, live_import)

    result = module.materialize(tmp_path, tmp_path / "matrix.json")
    rows = {row["id"]: row for row in result["rows"]}

    assert rows["ebook_artifact_namespace"]["status"] == "proved"
    assert rows["m4b_provider_receipt_namespace"]["status"] == "proved"
    assert rows["m4b_artifact_namespace"]["status"] == "proved"
    assert rows["audiobookshelf_import_receipt_namespace"]["status"] == "proved"
    assert rows["movie_generation_receipt_namespace"]["status"] == "proved"
    assert rows["movie_artifact_namespace"]["status"] == "proved"
