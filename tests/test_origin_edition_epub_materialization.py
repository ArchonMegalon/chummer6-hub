from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from zipfile import ZipFile

from PIL import Image
import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "materialize_origin_edition_epub.py"


def load_module():
    spec = importlib.util.spec_from_file_location("origin_edition_epub_materialization", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_cover(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (300, 420), (24, 38, 47)).save(path, format="JPEG")
    return path


def read_zip_text(path: Path, member: str) -> str:
    with ZipFile(path) as archive:
        return archive.read(member).decode("utf-8")


def test_materializes_epub_with_contextual_runner_metadata(tmp_path: Path) -> None:
    module = load_module()
    manuscript = tmp_path / "accepted.md"
    manuscript.write_text(
        "Rain made the clinic sign stutter.\n\nNobody gets sold.\n",
        encoding="utf-8",
    )
    cover = write_cover(tmp_path / "cover.jpg")
    output = tmp_path / "dossier" / "ebook.epub"
    receipt = tmp_path / "dossier" / "ebook.receipt.json"
    namespace = "origin.chummer.run/Case/Ari/Ghost"

    result = module.materialize(
        manuscript=manuscript,
        cover=cover,
        dossier_dir=tmp_path / "dossier",
        output_epub=output,
        receipt=receipt,
        namespace=namespace,
    )

    package = read_zip_text(output, "EPUB/package.opf")
    title = read_zip_text(output, "EPUB/title.xhtml")
    story = read_zip_text(output, "EPUB/story.xhtml")
    assert result["status"] == "verified"
    assert result["runnerName"] == "Ghost"
    assert result["bookTitle"] == "Ghost: Origin Dossier"
    assert result["epubSha256"] == sha256_file(output)
    assert result["coverSha256"] == sha256_file(cover)
    assert result["manuscriptSha256"] == sha256_file(manuscript)
    assert result["epubPath"] == f"{namespace}/dossier/ebook.epub"
    assert "<dc:title>Ghost: Origin Dossier</dc:title>" in package
    assert "<meta property=\"chummer:namespace\">origin.chummer.run/Case/Ari/Ghost</meta>" in package
    assert "<meta property=\"chummer:runner-name\">Ghost</meta>" in package
    assert "Kestrel" not in package
    assert "Ghost origin scene cover" in title
    assert "<h1>Rain made the clinic sign stutter.</h1>" in story
    assert json.loads(receipt.read_text(encoding="utf-8")) == result


def test_materializes_epub_with_explicit_title_and_runner(tmp_path: Path) -> None:
    module = load_module()
    manuscript = tmp_path / "accepted.md"
    manuscript.write_text("The clinic sign died in blue rain.\n", encoding="utf-8")
    cover = write_cover(tmp_path / "cover.jpg")
    output = tmp_path / "dossier" / "ebook.epub"

    result = module.materialize(
        manuscript=manuscript,
        cover=cover,
        dossier_dir=tmp_path / "dossier",
        output_epub=output,
        receipt=tmp_path / "dossier" / "ebook.receipt.json",
        namespace="origin.chummer.run/Case/Ari/Ghost",
        book_title="Ghost: Deluxe Origin",
        runner_name="Cipher Ghost",
    )

    package = read_zip_text(output, "EPUB/package.opf")
    assert result["bookTitle"] == "Ghost: Deluxe Origin"
    assert result["runnerName"] == "Cipher Ghost"
    assert "<dc:title>Ghost: Deluxe Origin</dc:title>" in package
    assert "<meta property=\"chummer:runner-name\">Cipher Ghost</meta>" in package


def test_materialize_epub_marks_known_preamble_start_as_not_story_start(tmp_path: Path) -> None:
    module = load_module()
    manuscript = tmp_path / "preamble.md"
    manuscript.write_text(
        "Introduction: this dossier explains the runner.\n\nThe clinic sign died in blue rain.\n",
        encoding="utf-8",
    )
    cover = write_cover(tmp_path / "cover.jpg")

    result = module.materialize(
        manuscript=manuscript,
        cover=cover,
        dossier_dir=tmp_path / "dossier",
        output_epub=tmp_path / "dossier" / "ebook.epub",
        receipt=tmp_path / "dossier" / "ebook.receipt.json",
        namespace="origin.chummer.run/Case/Ari/Ghost",
    )

    assert result["storyStartsWithoutPreamble"] is False
    assert "story_starts_without_preamble" not in result["tokens"]


def test_materialize_epub_rejects_empty_manuscript(tmp_path: Path) -> None:
    module = load_module()
    manuscript = tmp_path / "empty.md"
    manuscript.write_text(" \n", encoding="utf-8")
    cover = write_cover(tmp_path / "cover.jpg")

    with pytest.raises(ValueError, match="manuscript is empty"):
        module.materialize(
            manuscript=manuscript,
            cover=cover,
            dossier_dir=tmp_path / "dossier",
            output_epub=tmp_path / "dossier" / "ebook.epub",
            receipt=tmp_path / "dossier" / "ebook.receipt.json",
            namespace="origin.chummer.run/Case/Ari/Ghost",
        )
