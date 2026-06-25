from __future__ import annotations

import importlib.util
import hashlib
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "materialize_origin_dossier_route_proof.py"
LEGACY_SCRIPT = ROOT / "scripts" / "materialize_origin_dossier_kestrel_route_proof.py"


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
                "storySceneCoverUsesSelectedCharacterFace": True,
            }
        },
    )


def clear_origin_context_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "CHUMMER_ORIGIN_EDITION_PROJECT_ID",
        "CHUMMER_ORIGIN_EDITION_FAMILY_NAME",
        "CHUMMER_ORIGIN_EDITION_GIVEN_NAME",
        "CHUMMER_ORIGIN_EDITION_RUNNER_NAME",
        "CHUMMER_ORIGIN_EDITION_BASE_URL",
        "CHUMMER_ORIGIN_EDITION_NAMESPACE",
    ):
        monkeypatch.delenv(key, raising=False)


def test_route_proof_without_explicit_context_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = load_module()
    seed_import_request(tmp_path)
    clear_origin_context_env(monkeypatch)

    with pytest.raises(ValueError, match="explicit Origin Edition context required"):
        module.materialize(tmp_path, tmp_path / "route-proof.json")


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
    assert entry["requiresAuthenticatedChummerRunUser"] is True


def test_publication_index_preserves_live_import_absolute_artifact_paths(tmp_path: Path) -> None:
    module = load_module()
    seed_import_request(tmp_path)
    payload_path = tmp_path / "ORIGIN_DOSSIER_LIVE_IMPORT_REQUEST.generated.json"
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    request = payload["importRequest"]
    request["ebookArtifactPath"] = "/evidence/origin/ebook.epub"
    request["ebookAudiobookshelfImportReceiptPath"] = "/evidence/origin/dossier-import.receipt.json"
    request["coverConsistencyReceiptPath"] = "/evidence/origin/cover-consistency.receipt.json"
    request["audiobookPath"] = "/evidence/origin/audiobook.m4b"
    request["audiobookshelfImportReceiptPath"] = "/evidence/origin/audiobook-import.receipt.json"
    request["finalNoFallbackNoSentinelAuditReceiptPath"] = "/evidence/origin/final-audit.receipt.json"
    write_json(payload_path, payload)
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

    assert entry["ebookArtifactPath"] == "/evidence/origin/ebook.epub"
    assert entry["ebookAudiobookshelfImportReceiptPath"] == "/evidence/origin/dossier-import.receipt.json"
    assert entry["coverConsistencyReceiptPath"] == "/evidence/origin/cover-consistency.receipt.json"
    assert entry["audiobookPath"] == "/evidence/origin/audiobook.m4b"
    assert entry["audiobookshelfImportReceiptPath"] == "/evidence/origin/audiobook-import.receipt.json"
    assert entry["finalNoFallbackNoSentinelAuditReceiptPath"] == "/evidence/origin/final-audit.receipt.json"


def test_route_proof_identity_defaults_are_namespace_derived_for_all_runners() -> None:
    module = load_module()
    custom_context = module.OriginEditionContext.from_env(
        project_id="case-ari-ghost",
        family_name="Case",
        given_name="Ari",
        runner_name="Ghost",
    )

    assert module.subject_id_for(custom_context).startswith("subject.origin-edition.")
    assert module.token_for(custom_context).startswith("origin-route-proof-")
    assert "case-ari-ghost" not in module.subject_id_for(custom_context)
    assert "case-ari-ghost" not in module.token_for(custom_context)


def test_generic_route_proof_entrypoint_exposes_materializer_helpers() -> None:
    module = load_module()

    assert callable(module.main)
    assert callable(module.build_publication_index)
    assert callable(module.materialize)
    assert callable(module.sha256_response)


def test_generic_route_proof_script_owns_implementation_and_legacy_script_delegates() -> None:
    generic_source = SCRIPT.read_text(encoding="utf-8")
    legacy_source = LEGACY_SCRIPT.read_text(encoding="utf-8")

    assert "def materialize(" in generic_source
    assert "def build_publication_index(" in generic_source
    assert "from materialize_origin_dossier_kestrel_route_proof import" not in generic_source
    assert "from materialize_origin_dossier_route_proof import *" in legacy_source


def test_route_proof_hashes_response_bodies_for_artifact_identity() -> None:
    module = load_module()

    class Response:
        content = b"canonical artifact bytes"

    assert module.sha256_response(Response()) == hashlib.sha256(b"canonical artifact bytes").hexdigest()
