from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "materialize_workllm_manuscript_import_receipt.py"


def load_module():
    scripts_dir = str(SCRIPT_PATH.parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    spec = importlib.util.spec_from_file_location("workllm_manuscript_receipt", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def full_story() -> str:
    paragraphs: list[str] = []
    for chapter in range(1, 9):
        paragraphs.append(f"Chapter {chapter}: A Real Choice")
        paragraphs.extend(
            "A stubborn runner studies the harbor route, speaks with the community, accepts a concrete consequence, "
            "and makes a difficult choice that preserves both agency and continuity."
            for _ in range(100)
        )
    return "\n\n".join(paragraphs)


def test_materializes_redacted_live_workllm_receipt(tmp_path: Path) -> None:
    module = load_module()
    manuscript = tmp_path / "aster.md"
    manuscript.write_text(full_story(), encoding="utf-8")
    output = tmp_path / "receipt.json"
    thread_url = "https://example-workspace.workllm.io/team-ai?threadId=public-canary"

    receipt = module.materialize(
        manuscript,
        output,
        thread_url=thread_url,
        tier=4,
        model_sections=[
            "chapters_1_6=Anthropic Claude Sonnet 5",
            "chapters_7_8=Google Gemma 3 27B",
        ],
        completed_at_utc="2026-07-28T09:00:00Z",
    )

    assert receipt["status"] == "verified"
    assert receipt["provider"] == "WorkLLM Tier 4"
    assert receipt["evidence"]["wordCount"] >= 10_000
    assert receipt["evidence"]["chapterCount"] == 8
    assert receipt["privacy"]["rawThreadUrlExposed"] is False
    assert thread_url not in output.read_text(encoding="utf-8")
    assert json.loads(output.read_text(encoding="utf-8")) == receipt


def test_rejects_non_workllm_thread_url(tmp_path: Path) -> None:
    module = load_module()
    manuscript = tmp_path / "aster.md"
    manuscript.write_text(full_story(), encoding="utf-8")

    with pytest.raises(module.ValidationError, match="WorkLLM"):
        module.materialize(
            manuscript,
            tmp_path / "receipt.json",
            thread_url="https://example.invalid/team-ai?threadId=public-canary",
            tier=4,
            model_sections=["chapters_1_8=Model"],
        )


def test_rejects_short_or_fake_manuscript(tmp_path: Path) -> None:
    module = load_module()
    manuscript = tmp_path / "aster.md"
    manuscript.write_text("Chapter 1\nA placeholder story.", encoding="utf-8")

    with pytest.raises(module.ValidationError, match="fake/fallback"):
        module.materialize(
            manuscript,
            tmp_path / "receipt.json",
            thread_url="https://example-workspace.workllm.io/team-ai?threadId=public-canary",
            tier=4,
            model_sections=["chapters_1_8=Model"],
        )
