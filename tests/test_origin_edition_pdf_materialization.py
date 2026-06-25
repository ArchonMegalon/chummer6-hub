from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

from PIL import Image
import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "materialize_origin_edition_pdf.py"


def load_module():
    spec = importlib.util.spec_from_file_location("origin_edition_pdf_materialization", SCRIPT)
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
    Image.new("RGB", (300, 420), (17, 31, 41)).save(path, format="JPEG")
    return path


def test_materializes_real_pdf_and_receipt_bound_to_cover_and_manuscript(tmp_path: Path) -> None:
    module = load_module()
    manuscript = tmp_path / "provider-manuscript.md"
    manuscript.write_text(
        "Rain made the clinic sign stutter.\n\nNobody gets sold.\n\nNobody gets left in the rain.\n",
        encoding="utf-8",
    )
    cover = write_cover(tmp_path / "cover.jpg")
    pdf = tmp_path / "dossier" / "book.pdf"
    receipt = tmp_path / "dossier" / "pdf-cover.receipt.json"

    result = module.materialize(
        manuscript=manuscript,
        cover=cover,
        output_pdf=pdf,
        receipt=receipt,
        namespace="origin.chummer.run/Varga/Mira/Kestrel",
    )

    assert pdf.read_bytes().startswith(b"%PDF-1.4")
    assert b"/Subtype /Image" in pdf.read_bytes()
    assert b"Rain made the clinic sign stutter." in pdf.read_bytes()
    assert result["status"] == "verified"
    assert result["pdfSha256"] == sha256_file(pdf)
    assert result["coverSha256"] == sha256_file(cover)
    assert result["manuscriptSha256"] == sha256_file(manuscript)
    assert result["storyStartsWithoutPreamble"] is True
    assert result["coverEmbeddedOnFirstPage"] is True
    assert result["rawRuntimePathsExposed"] is False
    assert result["pdfPath"] == "origin.chummer.run/Varga/Mira/Kestrel/dossier/book.pdf"
    assert json.loads(receipt.read_text(encoding="utf-8")) == result


def test_materializes_pdf_for_custom_runner_story_without_kestrel_sentence(tmp_path: Path) -> None:
    module = load_module()
    manuscript = tmp_path / "ghost-manuscript.md"
    manuscript.write_text(
        "The clinic sign died in blue rain.\n\nGhost counted exits before names.\n",
        encoding="utf-8",
    )
    cover = write_cover(tmp_path / "ghost-cover.jpg")
    pdf = tmp_path / "dossier" / "book.pdf"

    result = module.materialize(
        manuscript=manuscript,
        cover=cover,
        output_pdf=pdf,
        receipt=tmp_path / "dossier" / "pdf-cover.receipt.json",
        namespace="origin.chummer.run/Case/Ari/Ghost",
    )

    assert b"The clinic sign died in blue rain." in pdf.read_bytes()
    assert result["storyStartsWithoutPreamble"] is True
    assert result["pdfPath"] == "origin.chummer.run/Case/Ari/Ghost/dossier/book.pdf"


def test_materialize_pdf_marks_known_preamble_start_as_not_story_start(tmp_path: Path) -> None:
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
        output_pdf=tmp_path / "dossier" / "book.pdf",
        receipt=tmp_path / "dossier" / "pdf-cover.receipt.json",
        namespace="origin.chummer.run/Case/Ari/Ghost",
    )

    assert result["storyStartsWithoutPreamble"] is False
    assert "story_starts_without_preamble" not in result["tokens"]


def test_materialize_rejects_empty_manuscript(tmp_path: Path) -> None:
    module = load_module()
    manuscript = tmp_path / "empty.md"
    manuscript.write_text(" \n", encoding="utf-8")
    cover = write_cover(tmp_path / "cover.jpg")

    with pytest.raises(ValueError, match="manuscript is empty"):
        module.materialize(
            manuscript=manuscript,
            cover=cover,
            output_pdf=tmp_path / "book.pdf",
            receipt=tmp_path / "pdf-cover.receipt.json",
            namespace="origin.chummer.run/Varga/Mira/Kestrel",
        )
