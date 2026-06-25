from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "materialize_origin_dossier_route_proof.py"


def load_module():
    spec = importlib.util.spec_from_file_location("origin_dossier_route_proof", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def seed_import_request(root: Path) -> None:
    write_json(
        root / "ORIGIN_DOSSIER_LIVE_IMPORT_REQUEST.generated.json",
        {
            "importRequest": {
                "projectId": "case-ari-ghost",
                "bookArtifactPath": "origin.chummer.run/Case/Ari/Ghost/dossier/ebook.epub",
                "audiobookshelfDossierShareUrl": "https://audio.chummer.run/share/ghost-dossier",
                "audiobookshelfAudiobookShareUrl": "https://audio.chummer.run/share/ghost-audio",
            }
        },
    )


def test_publication_index_uses_origin_edition_context_for_routes_and_artifacts(tmp_path: Path) -> None:
    module = load_module()
    seed_import_request(tmp_path)
    context = module.OriginEditionContext.from_env(
        project_id="case-ari-ghost",
        family_name="Case",
        given_name="Ari",
        runner_name="Ghost",
        base_url="https://staging.chummer.run",
    )

    entry = module.build_publication_index(
        tmp_path,
        tmp_path / "publication-index.json",
        context,
        "subject.case.ari.ghost",
    )

    assert entry["ownerUserId"] == "case-ari-ghost-origin-route-proof-user"
    assert entry["subjectId"] == "subject.case.ari.ghost"
    assert entry["ownerSubjectId"] == "subject.case.ari.ghost"
    assert entry["chummerRunOwnerUrl"] == "https://staging.chummer.run/account/work/origin-dossiers/case-ari-ghost"
    assert entry["bookArtifactUrl"] == "https://staging.chummer.run/account/work/origin-dossiers/case-ari-ghost/book"
    assert entry["dossierVideoUrl"] == "https://staging.chummer.run/account/work/origin-dossiers/case-ari-ghost/video"
    assert entry["storySceneCoverUrl"] == "https://staging.chummer.run/account/work/origin-dossiers/case-ari-ghost/cover"
    assert entry["ebookAudiobookshelfImportReceiptPath"].endswith(
        "origin.chummer.run/Case/Ari/Ghost/dossier/audiobookshelf-dossier-import.receipt.json"
    )
    assert entry["coverConsistencyReceiptPath"].endswith(
        "origin.chummer.run/Case/Ari/Ghost/cover-consistency-strict.receipt.json"
    )
    assert entry["audiobookPath"].endswith("origin.chummer.run/Case/Ari/Ghost/audiobook/ghost-origin.m4b")
    assert entry["audiobookshelfImportReceiptPath"].endswith(
        "origin.chummer.run/Case/Ari/Ghost/audiobook/audiobookshelf-import.receipt.json"
    )
    assert entry["finalNoFallbackNoSentinelAuditReceiptPath"].endswith(
        "origin.chummer.run/Case/Ari/Ghost/final-no-fallback-no-sentinel-audit.receipt.json"
    )


def test_route_proof_identity_defaults_remain_stable_for_kestrel_and_generic_for_custom_runner() -> None:
    module = load_module()
    default_context = module.OriginEditionContext.default()
    custom_context = module.OriginEditionContext.from_env(
        project_id="case-ari-ghost",
        family_name="Case",
        given_name="Ari",
        runner_name="Ghost",
    )

    assert module.subject_id_for(default_context) == "subject.varga-mira.kestrel"
    assert module.token_for(default_context) == "kestrel-origin-route-proof-token"
    assert module.subject_id_for(custom_context).startswith("subject.origin-edition.")
    assert module.token_for(custom_context).startswith("origin-route-proof-")
    assert module.subject_id_for(custom_context) != module.subject_id_for(default_context)
    assert module.token_for(custom_context) != module.token_for(default_context)


def test_generic_route_proof_entrypoint_exposes_materializer_helpers() -> None:
    module = load_module()

    assert callable(module.main)
    assert callable(module.build_publication_index)
    assert callable(module.materialize)
