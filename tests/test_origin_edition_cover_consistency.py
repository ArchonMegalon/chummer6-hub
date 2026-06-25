from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "audit_origin_edition_cover_consistency.py"


def load_module():
    spec = importlib.util.spec_from_file_location("origin_edition_cover_consistency", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def write_epub(path: Path, cover: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("mimetype", "application/epub+zip")
        archive.writestr("EPUB/images/cover.jpg", cover)
        archive.writestr("EPUB/package.opf", "<package></package>")
    return path


def build_fixture(tmp_path: Path, *, cover: bytes = b"same-cover") -> tuple[Path, str]:
    root = tmp_path / "origin.chummer.run" / "Varga" / "Mira" / "Kestrel"
    expected = sha256(cover)
    for relative in [
        "cover.jpg",
        "dossier/cover.jpg",
        "audiobook/cover.jpg",
        "movie/poster.jpg",
    ]:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(cover)
    write_epub(root / "dossier" / "ebook.epub", cover)
    (root / "dossier" / "book.pdf").write_bytes(b"%PDF-1.7\nreal pdf\n")
    (root / "audiobook" / "book.m4b").write_bytes(b"real m4b bytes")
    write_json(root / "dossier" / "pdf-cover.receipt.json", {"status": "verified", "coverSha256": expected})
    write_json(root / "audiobook" / "m4b-cover.receipt.json", {"status": "verified", "coverSha256": expected})
    write_json(
        root / "dossier" / "audiobookshelf-dossier-import.receipt.json",
        {"status": "verified", "coverSha256": expected},
    )
    write_json(
        root / "audiobook" / "audiobookshelf-import.receipt.json",
        {"status": "verified", "coverSha256": expected},
    )
    return root, expected


def build_fixture_at(root: Path, *, cover: bytes = b"same-cover") -> tuple[Path, str]:
    expected = sha256(cover)
    for relative in [
        "cover.jpg",
        "dossier/cover.jpg",
        "audiobook/cover.jpg",
        "movie/poster.jpg",
    ]:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(cover)
    write_epub(root / "dossier" / "ebook.epub", cover)
    (root / "dossier" / "book.pdf").write_bytes(b"%PDF-1.7\nreal pdf\n")
    (root / "audiobook" / "book.m4b").write_bytes(b"real m4b bytes")
    write_json(root / "dossier" / "pdf-cover.receipt.json", {"status": "verified", "coverSha256": expected})
    write_json(root / "audiobook" / "m4b-cover.receipt.json", {"status": "verified", "coverSha256": expected})
    write_json(
        root / "dossier" / "audiobookshelf-dossier-import.receipt.json",
        {"status": "verified", "coverSha256": expected},
    )
    write_json(
        root / "audiobook" / "audiobookshelf-import.receipt.json",
        {"status": "verified", "coverSha256": expected},
    )
    return root, expected


def surface(result: dict, name: str) -> dict:
    return next(item for item in result["surfaces"] if item["name"] == name)


def test_cover_consistency_passes_when_every_required_surface_matches(tmp_path: Path) -> None:
    module = load_module()
    root, expected = build_fixture(tmp_path)

    result = module.audit(root, expected, tmp_path / "receipt.json")

    assert result["status"] == "pass"
    assert result["goldEligible"] is True
    assert result["blockedSurfaces"] == []
    assert "m4b_cover_embedded" in result["tokens"]
    assert surface(result, "ebook_embedded_cover")["embeddedPath"] == "EPUB/images/cover.jpg"


def test_cover_consistency_uses_supplied_origin_edition_context_for_namespace(tmp_path: Path) -> None:
    module = load_module()
    root, expected = build_fixture_at(tmp_path / "staging" / "edition")
    context = module.OriginEditionContext.from_env(
        project_id="case-ari-ghost",
        family_name="Case",
        given_name="Ari",
        runner_name="Ghost",
    )

    result = module.audit(root, expected, context=context)

    assert result["status"] == "pass"
    assert result["namespace"] == "origin.chummer.run/Case/Ari/Ghost"
    assert result["editionRoot"] == "origin.chummer.run/Case/Ari/Ghost"
    assert surface(result, "chummer_hero_cover")["path"] == "origin.chummer.run/Case/Ari/Ghost/cover.jpg"
    assert surface(result, "pdf_cover_embedding")["artifactCandidates"][0] == "origin.chummer.run/Case/Ari/Ghost/dossier/book.pdf"


def test_cover_consistency_blocks_missing_pdf_and_m4b_artifacts(tmp_path: Path) -> None:
    module = load_module()
    root, expected = build_fixture(tmp_path)
    (root / "dossier" / "book.pdf").unlink()
    (root / "audiobook" / "book.m4b").unlink()

    result = module.audit(root, expected)

    assert result["status"] == "blocked"
    assert result["goldEligible"] is False
    assert "pdf_cover_embedding" in result["blockedSurfaces"]
    assert "m4b_cover_embedding" in result["blockedSurfaces"]
    assert surface(result, "pdf_cover_embedding")["status"] == "blocked_missing_artifact"
    assert surface(result, "m4b_cover_embedding")["status"] == "blocked_missing_artifact"
    assert "m4b_cover_embedded" not in result["tokens"]


def test_cover_consistency_blocks_mismatched_movie_poster(tmp_path: Path) -> None:
    module = load_module()
    root, expected = build_fixture(tmp_path)
    (root / "movie" / "poster.jpg").write_bytes(b"different-cover")

    result = module.audit(root, expected)

    assert result["status"] == "blocked"
    assert "movie_poster" in result["blockedSurfaces"]
    assert surface(result, "movie_poster")["status"] == "blocked_hash_mismatch"


def test_cover_consistency_blocks_mismatched_epub_cover(tmp_path: Path) -> None:
    module = load_module()
    root, expected = build_fixture(tmp_path)
    write_epub(root / "dossier" / "ebook.epub", b"different-cover")

    result = module.audit(root, expected)

    assert result["status"] == "blocked"
    assert "ebook_embedded_cover" in result["blockedSurfaces"]
    assert surface(result, "ebook_embedded_cover")["status"] == "blocked_hash_mismatch"


def test_cover_consistency_blocks_unverified_audiobookshelf_audiobook_cover(tmp_path: Path) -> None:
    module = load_module()
    root, expected = build_fixture(tmp_path)
    write_json(
        root / "audiobook" / "audiobookshelf-import.receipt.json",
        {"status": "blocked", "coverSha256": expected},
    )

    result = module.audit(root, expected)

    assert result["status"] == "blocked"
    assert "audiobookshelf_audiobook_cover" in result["blockedSurfaces"]
    assert surface(result, "audiobookshelf_audiobook_cover")["status"] == "blocked_receipt_not_verified"
