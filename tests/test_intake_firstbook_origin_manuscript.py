from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "intake_firstbook_origin_manuscript.py"


def load_module():
    scripts_dir = str(SCRIPT.parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    spec = importlib.util.spec_from_file_location("intake_firstbook_origin_manuscript", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_packet(path: Path, chapter_count: int = 8) -> Path:
    path.write_text(
        json.dumps(
            {
                "contract_name": "chummer.firstbook_premium_packet.v1",
                "packet_id": "origin-firstbook-intake",
                "source_packet_refs": ["approved-origin-source-sha256"],
                "book_title": "Rain Ledger",
                "chapter_count": chapter_count,
                "approved_claims_only": True,
                "publication_allowed": False,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def build_manuscript(path: Path, chapter_count: int = 8, words_per_chapter: int = 1_300) -> Path:
    parts = []
    for chapter in range(1, chapter_count + 1):
        prose = " ".join(
            f"runner memory consequence choice rain contact promise scene{chapter}"
            for _ in range(words_per_chapter // 8)
        )
        parts.append(f"# Chapter {chapter} - Scene {chapter}\n{prose}\n")
    path.write_text("\n".join(parts), encoding="utf-8")
    return path


def test_split_chapters_collapses_adjacent_identical_provider_title_wrappers() -> None:
    module = load_module()
    manuscript = (
        "## Chapter 1: Arrival\n\n"
        "# Chapter 1: Arrival\n\n"
        "The runner enters the rain.\n\n"
        "## Chapter 2: Reckoning\n\n"
        "The runner chooses the truth.\n"
    )

    chapters = module._split_chapters(manuscript)

    assert [chapter["number"] for chapter in chapters] == [1, 2]
    assert [chapter["title"] for chapter in chapters] == ["Arrival", "Reckoning"]
    assert "# Chapter 1: Arrival" in chapters[0]["text"]


def test_split_chapters_preserves_real_or_mismatched_duplicate_boundaries() -> None:
    module = load_module()
    manuscript = (
        "## Chapter 1: Arrival\n\n"
        "Substantive prose separates the headings.\n\n"
        "# Chapter 1: Arrival\n\n"
        "More prose.\n\n"
        "## Chapter 2: Reckoning\n\n"
        "# Chapter 2: Different title\n\n"
        "Closing prose.\n"
    )

    chapters = module._split_chapters(manuscript)

    assert [chapter["number"] for chapter in chapters] == [1, 1, 2, 2]
    assert [chapter["title"] for chapter in chapters] == [
        "Arrival",
        "Arrival",
        "Reckoning",
        "Different title",
    ]


def test_intake_preserves_provider_export_and_emits_hub_compatible_receipt(tmp_path: Path) -> None:
    module = load_module()
    packet = build_packet(tmp_path / "packet.json")
    outline = tmp_path / "outline.md"
    outline.write_text("# Outline\nEight source-bound chapters.\n", encoding="utf-8")
    manuscript = build_manuscript(tmp_path / "provider-export.md")
    original_hash = module.sha256_file(manuscript)

    result = module.intake(
        packet_path=packet,
        outline_path=outline,
        manuscript_path=manuscript,
        output_dir=tmp_path / "archive",
        provider_run_ref="firstbook-authenticated-run-20260730",
        account_alias="firstbook-premium",
    )

    assert result["status"] == "pass"
    assert result["fullManuscriptReady"] is True
    assert result["manuscriptSha256"] == original_hash
    assert result["manuscriptWordCount"] >= 10_000
    assert result["chapterCount"] == 8
    receipt = json.loads(Path(result["receiptPath"]).read_text(encoding="utf-8"))
    assert receipt["status"] == "verified"
    assert receipt["full_manuscript_ready"] is True
    assert receipt["artifactSha256"] == [original_hash]
    assert receipt["providerAuthentication"]["status"] == "authenticated"
    assert receipt["providerAuthentication"]["rawProviderRunRefIncluded"] is False
    serialized = json.dumps(receipt)
    assert "firstbook-authenticated-run-20260730" not in serialized
    assert "provider_receipt_reference:First Book AI:provider_manuscript_import" in serialized


def test_intake_rejects_outline_length_content(tmp_path: Path) -> None:
    module = load_module()
    packet = build_packet(tmp_path / "packet.json")
    outline = tmp_path / "outline.md"
    outline.write_text("# Outline\n", encoding="utf-8")
    manuscript = tmp_path / "provider-export.md"
    manuscript.write_text("# Chapter 1 - Only an outline\nA short paragraph.\n", encoding="utf-8")

    with pytest.raises(module.IntakeError, match="at least 10000"):
        module.intake(
            packet_path=packet,
            outline_path=outline,
            manuscript_path=manuscript,
            output_dir=tmp_path / "archive",
            provider_run_ref="firstbook-authenticated-run-20260730",
            account_alias="firstbook-premium",
        )
