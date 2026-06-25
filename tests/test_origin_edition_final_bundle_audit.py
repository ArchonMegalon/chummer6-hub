from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "audit_origin_edition_final_bundle.py"


def load_module():
    seed_origin_context_env()
    spec = importlib.util.spec_from_file_location("origin_edition_final_bundle", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def seed_origin_context_env() -> None:
    os.environ.setdefault("CHUMMER_ORIGIN_EDITION_PROJECT_ID", "varga-mira-kestrel")
    os.environ.setdefault("CHUMMER_ORIGIN_EDITION_FAMILY_NAME", "Varga")
    os.environ.setdefault("CHUMMER_ORIGIN_EDITION_GIVEN_NAME", "Mira")
    os.environ.setdefault("CHUMMER_ORIGIN_EDITION_RUNNER_NAME", "Kestrel")
    os.environ.setdefault("CHUMMER_ORIGIN_EDITION_BASE_URL", "https://chummer.run")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def write_file(path: Path, payload: bytes | str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, bytes):
        path.write_bytes(payload)
    else:
        path.write_text(payload, encoding="utf-8")
    return path


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


def test_final_bundle_audit_without_explicit_context_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = load_module()
    clear_origin_context_env(monkeypatch)

    with pytest.raises(ValueError, match="explicit Origin Edition context required"):
        module.audit(tmp_path)


def receipt(path: Path, *, status: str = "pass", gold: bool = True, extra: dict | None = None) -> Path:
    payload = {
        "contractName": "test.receipt",
        "operation": path.stem,
        "provider": "test",
        "status": status,
        "goldEligible": gold,
        "createdAtUtc": "2026-06-25T00:00:00Z",
    }
    if extra:
        payload.update(extra)
    return write_json(path, payload)


def build_bundle(
    tmp_path: Path,
    *,
    namespace: str = "origin.chummer.run/Varga/Mira/Kestrel",
    runner: str = "Kestrel",
    m4b_name: str = "kestrel-origin.m4b",
    source_packet_name: str = "approved-sample-runner-canon.json",
    include_live_import: bool = False,
) -> Path:
    root = tmp_path / "bundle"
    edition = root / namespace
    write_json(root / source_packet_name, {"runner": runner, "status": "approved"})
    write_file(root / "provider-manuscript-draft.md", "Rain made the clinic sign stutter.\nNobody gets sold.\n")
    receipt(root / "undetectable-humanizer.receipt.json")
    receipt(root / "undetectable-humanizer-quality-gate.receipt.json")
    write_file(edition / "cover.jpg", b"cover")
    write_file(edition / "dossier" / "ebook.epub", b"epub")
    write_file(edition / "dossier" / "book.pdf", b"%PDF-1.4\n")
    receipt(edition / "dossier" / "pdf-cover.receipt.json")
    receipt(edition / "dossier" / "audiobookshelf-dossier-import.receipt.json")
    write_file(edition / "audiobook" / m4b_name, b"m4b")
    receipt(edition / "audiobook" / "m4b-provider-import-gate.receipt.json")
    receipt(edition / "audiobook" / "audiobookshelf-import.receipt.json")
    receipt(edition / "cover-consistency-strict.receipt.json")
    write_file(edition / "movie" / "movie.mp4", b"mp4")
    write_file(edition / "movie" / "poster.jpg", b"cover")
    receipt(edition / "movie" / "dossier-video.receipt.json")
    if include_live_import:
        write_json(
            root / "ORIGIN_DOSSIER_LIVE_IMPORT_REQUEST.generated.json",
            {
                "contractName": "chummer.origin_dossier_live_artifact_import_request.v1",
                "status": "pass",
                "importRequest": {
                    "projectId": f"{runner.lower()}-project",
                    "originEditionNamespace": namespace,
                    "sourcePacketPath": source_packet_name,
                    "providerManuscriptPath": "provider-manuscript-draft.md",
                    "humanizerReceiptPath": "undetectable-humanizer.receipt.json",
                    "humanizerQualityReceiptPath": "undetectable-humanizer-quality-gate.receipt.json",
                    "storySceneCoverPath": f"{namespace}/cover.jpg",
                    "bookArtifactPath": f"{namespace}/dossier/ebook.epub",
                    "ebookArtifactPath": f"{namespace}/dossier/ebook.epub",
                    "ebookAudiobookshelfImportReceiptPath": f"{namespace}/dossier/audiobookshelf-dossier-import.receipt.json",
                    "m4bProviderImportReceiptPath": f"{namespace}/audiobook/m4b-provider-import-gate.receipt.json",
                    "audiobookPath": f"{namespace}/audiobook/{m4b_name}",
                    "audiobookshelfImportReceiptPath": f"{namespace}/audiobook/audiobookshelf-import.receipt.json",
                    "dossierVideoPath": f"{namespace}/movie/movie.mp4",
                    "moviePosterPath": f"{namespace}/movie/poster.jpg",
                    "dossierVideoPosterPath": f"{namespace}/movie/poster.jpg",
                    "dossierVideoReceiptPath": f"{namespace}/movie/dossier-video.receipt.json",
                },
            },
        )
    return root


def surface(result: dict, name: str) -> dict:
    return next(item for item in result["surfaces"] if item["name"] == name)


def test_final_bundle_audit_passes_complete_clean_bundle(tmp_path: Path) -> None:
    module = load_module()
    root = build_bundle(tmp_path)

    result = module.audit(root)

    assert result["status"] == "pass"
    assert result["goldEligible"] is True
    assert result["blockedSurfaces"] == []
    assert surface(result, "real_m4b_artifact")["candidateCount"] == 1


def test_final_bundle_audit_uses_origin_edition_context_namespace(tmp_path: Path) -> None:
    module = load_module()
    namespace = "origin.chummer.run/Case/Ari/Ghost"
    root = build_bundle(tmp_path, namespace=namespace, runner="Ghost", m4b_name="ghost-origin.m4b")
    context = module.OriginEditionContext.from_env(
        project_id="case-ari-ghost",
        family_name="Case",
        given_name="Ari",
        runner_name="Ghost",
    )

    result = module.audit(root, context=context)

    assert result["status"] == "pass"
    assert result["namespace"] == namespace
    assert result["projectId"] == "case-ari-ghost"
    assert surface(result, "cover")["path"] == f"{namespace}/cover.jpg"
    assert surface(result, "real_m4b_artifact")["path"] == f"{namespace}/audiobook/*.m4b"
    assert surface(result, "movie_poster")["path"] == f"{namespace}/movie/poster.jpg"


def test_final_bundle_audit_uses_live_import_source_packet_path(tmp_path: Path) -> None:
    module = load_module()
    namespace = "origin.chummer.run/Case/Ari/Ghost"
    root = build_bundle(
        tmp_path,
        namespace=namespace,
        runner="Ghost",
        m4b_name="ghost-origin.m4b",
        source_packet_name="approved-origin-canon-packet.json",
        include_live_import=True,
    )
    (root / "approved-sample-runner-canon.json").unlink(missing_ok=True)
    context = module.OriginEditionContext.from_env(
        project_id="case-ari-ghost",
        family_name="Case",
        given_name="Ari",
        runner_name="Ghost",
    )

    result = module.audit(root, context=context)

    assert result["status"] == "pass"
    assert surface(result, "approved_canon_packet")["path"] == "approved-origin-canon-packet.json"


def test_final_bundle_audit_blocks_live_import_artifacts_outside_required_sibling_branches(tmp_path: Path) -> None:
    module = load_module()
    namespace = "origin.chummer.run/Case/Ari/Ghost"
    root = build_bundle(
        tmp_path,
        namespace=namespace,
        runner="Ghost",
        m4b_name="ghost-origin.m4b",
        include_live_import=True,
    )
    write_file(root / namespace / "wrong" / "ebook.epub", b"epub")
    live_import_path = root / "ORIGIN_DOSSIER_LIVE_IMPORT_REQUEST.generated.json"
    payload = json.loads(live_import_path.read_text(encoding="utf-8"))
    payload["importRequest"]["ebookArtifactPath"] = f"{namespace}/wrong/ebook.epub"
    write_json(live_import_path, payload)
    context = module.OriginEditionContext.from_env(
        project_id="case-ari-ghost",
        family_name="Case",
        given_name="Ari",
        runner_name="Ghost",
    )

    result = module.audit(root, context=context)

    assert result["status"] == "blocked"
    assert "ebook_branch" in result["blockedSurfaces"]
    assert surface(result, "ebook_branch")["status"] == "blocked_wrong_branch"


def test_final_bundle_audit_blocks_live_import_dossier_receipt_outside_dossier_branch(tmp_path: Path) -> None:
    module = load_module()
    namespace = "origin.chummer.run/Case/Ari/Ghost"
    root = build_bundle(
        tmp_path,
        namespace=namespace,
        runner="Ghost",
        m4b_name="ghost-origin.m4b",
        include_live_import=True,
    )
    receipt(root / namespace / "audiobook" / "audiobookshelf-dossier-import.receipt.json")
    live_import_path = root / "ORIGIN_DOSSIER_LIVE_IMPORT_REQUEST.generated.json"
    payload = json.loads(live_import_path.read_text(encoding="utf-8"))
    payload["importRequest"]["ebookAudiobookshelfImportReceiptPath"] = f"{namespace}/audiobook/audiobookshelf-dossier-import.receipt.json"
    write_json(live_import_path, payload)
    context = module.OriginEditionContext.from_env(
        project_id="case-ari-ghost",
        family_name="Case",
        given_name="Ari",
        runner_name="Ghost",
    )

    result = module.audit(root, context=context)

    assert result["status"] == "blocked"
    assert "dossier_audiobookshelf_receipt_branch" in result["blockedSurfaces"]
    assert surface(result, "dossier_audiobookshelf_receipt")["path"] == f"{namespace}/audiobook/audiobookshelf-dossier-import.receipt.json"
    assert surface(result, "dossier_audiobookshelf_receipt_branch")["status"] == "blocked_wrong_branch"


def test_final_bundle_audit_blocks_live_import_cover_outside_origin_branch(tmp_path: Path) -> None:
    module = load_module()
    namespace = "origin.chummer.run/Case/Ari/Ghost"
    root = build_bundle(
        tmp_path,
        namespace=namespace,
        runner="Ghost",
        m4b_name="ghost-origin.m4b",
        include_live_import=True,
    )
    write_file(root / namespace / "dossier" / "cover.jpg", b"wrong branch cover")
    live_import_path = root / "ORIGIN_DOSSIER_LIVE_IMPORT_REQUEST.generated.json"
    payload = json.loads(live_import_path.read_text(encoding="utf-8"))
    payload["importRequest"]["storySceneCoverPath"] = f"{namespace}/dossier/cover.jpg"
    write_json(live_import_path, payload)
    context = module.OriginEditionContext.from_env(
        project_id="case-ari-ghost",
        family_name="Case",
        given_name="Ari",
        runner_name="Ghost",
    )

    result = module.audit(root, context=context)

    assert result["status"] == "blocked"
    assert "cover_branch" in result["blockedSurfaces"]
    assert surface(result, "cover")["path"] == f"{namespace}/dossier/cover.jpg"
    assert surface(result, "cover_branch")["status"] == "blocked_wrong_branch"


def test_final_bundle_audit_blocks_and_redacts_absolute_live_import_path_outside_evidence_root(tmp_path: Path) -> None:
    module = load_module()
    namespace = "origin.chummer.run/Case/Ari/Ghost"
    root = build_bundle(
        tmp_path,
        namespace=namespace,
        runner="Ghost",
        m4b_name="ghost-origin.m4b",
        include_live_import=True,
    )
    outside = tmp_path / "outside-operator-path" / "ebook.epub"
    write_file(outside, b"external ebook bytes")
    live_import_path = root / "ORIGIN_DOSSIER_LIVE_IMPORT_REQUEST.generated.json"
    payload = json.loads(live_import_path.read_text(encoding="utf-8"))
    payload["importRequest"]["ebookArtifactPath"] = str(outside)
    write_json(live_import_path, payload)
    context = module.OriginEditionContext.from_env(
        project_id="case-ari-ghost",
        family_name="Case",
        given_name="Ari",
        runner_name="Ghost",
    )

    result = module.audit(root, context=context)
    ebook = surface(result, "ebook")
    ebook_branch = surface(result, "ebook_branch")
    serialized = json.dumps(result, sort_keys=True)

    assert result["status"] == "blocked"
    assert ebook["status"] == "pass"
    assert ebook["path"] == "__outside_evidence_root__"
    assert ebook_branch["status"] == "blocked_wrong_branch"
    assert str(outside) not in serialized
    assert result["rawRuntimePathsExposed"] is False


def test_final_bundle_audit_blocks_failed_humanizer_quality(tmp_path: Path) -> None:
    module = load_module()
    root = build_bundle(tmp_path)
    receipt(root / "undetectable-humanizer-quality-gate.receipt.json", status="failed_quality_gate", gold=False)

    result = module.audit(root)

    assert result["status"] == "blocked"
    assert "humanizer_quality_receipt" in result["blockedSurfaces"]
    assert surface(result, "humanizer_quality_receipt")["status"] == "blocked_not_pass"


def test_final_bundle_audit_blocks_missing_m4b_and_audiobook_share_receipt(tmp_path: Path) -> None:
    module = load_module()
    root = build_bundle(tmp_path)
    (root / "origin.chummer.run" / "Varga" / "Mira" / "Kestrel" / "audiobook" / "kestrel-origin.m4b").unlink()
    (root / "origin.chummer.run" / "Varga" / "Mira" / "Kestrel" / "audiobook" / "audiobookshelf-import.receipt.json").unlink()

    result = module.audit(root)

    assert result["status"] == "blocked"
    assert "real_m4b_artifact" in result["blockedSurfaces"]
    assert "audiobookshelf_audiobook_receipt" in result["blockedSurfaces"]


def test_final_bundle_audit_blocks_missing_movie_poster(tmp_path: Path) -> None:
    module = load_module()
    root = build_bundle(tmp_path)
    (root / "origin.chummer.run" / "Varga" / "Mira" / "Kestrel" / "movie" / "poster.jpg").unlink()

    result = module.audit(root)

    assert result["status"] == "blocked"
    assert "movie_poster" in result["blockedSurfaces"]
    assert surface(result, "movie_poster")["status"] == "blocked_missing_file"
    assert surface(result, "movie_poster_branch")["status"] == "pass"


def test_final_bundle_audit_blocks_fallback_marker_in_manuscript(tmp_path: Path) -> None:
    module = load_module()
    root = build_bundle(tmp_path)
    write_file(root / "provider-manuscript-draft.md", "fallback narration placeholder\n")

    result = module.audit(root)

    assert result["status"] == "blocked"
    assert "provider_manuscript" in result["blockedSurfaces"]
    assert surface(result, "provider_manuscript")["status"] == "blocked_rejected_marker"


def test_final_bundle_audit_blocks_marker_bytes_in_binary_artifacts(tmp_path: Path) -> None:
    module = load_module()
    root = build_bundle(tmp_path)
    namespace = "origin.chummer.run/Varga/Mira/Kestrel"
    write_file(root / namespace / "dossier" / "ebook.epub", b"PK placeholder ebook bytes")
    write_file(root / namespace / "audiobook" / "kestrel-origin.m4b", b"fallback audio marker")
    write_file(root / namespace / "movie" / "movie.mp4", b"sentinel movie marker")

    result = module.audit(root)

    assert result["status"] == "blocked"
    assert "ebook" in result["blockedSurfaces"]
    assert "real_m4b_artifact" in result["blockedSurfaces"]
    assert "movie" in result["blockedSurfaces"]
    assert surface(result, "ebook")["status"] == "blocked_rejected_marker"
    assert surface(result, "movie")["status"] == "blocked_rejected_marker"
    assert surface(result, "real_m4b_artifact")["status"] == "blocked_rejected_marker"
    assert surface(result, "ebook")["markerFindings"] == ["placeholder"]
    assert "fallback" in next(iter(surface(result, "real_m4b_artifact")["markerFindings"].values()))
    assert surface(result, "movie")["markerFindings"] == ["sentinel"]


def test_final_bundle_audit_writes_receipt(tmp_path: Path) -> None:
    module = load_module()
    root = build_bundle(tmp_path)
    output = tmp_path / "receipt.json"

    result = module.audit(root, output)

    assert output.is_file()
    assert json.loads(output.read_text(encoding="utf-8")) == result
    assert sha256_file(output)
