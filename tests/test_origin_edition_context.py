from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "origin_edition_context.py"


def load_module():
    spec = importlib.util.spec_from_file_location("origin_edition_context", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_origin_edition_context_defaults_to_kestrel_gold_fixture(tmp_path: Path) -> None:
    module = load_module()
    context = module.OriginEditionContext.default()

    assert context.project_id == "varga-mira-kestrel"
    assert context.resolved_namespace == "origin.chummer.run/Varga/Mira/Kestrel"
    assert context.branch(tmp_path) == tmp_path / "origin.chummer.run/Varga/Mira/Kestrel"
    assert context.owner_url == "https://chummer.run/account/work/origin-dossiers/varga-mira-kestrel"


def test_origin_edition_context_supports_env_and_cli_overrides(tmp_path: Path, monkeypatch) -> None:
    module = load_module()
    monkeypatch.setenv("CHUMMER_ORIGIN_EDITION_PROJECT_ID", "project-from-env")
    monkeypatch.setenv("CHUMMER_ORIGIN_EDITION_FAMILY_NAME", "Family")
    monkeypatch.setenv("CHUMMER_ORIGIN_EDITION_GIVEN_NAME", "Given")
    monkeypatch.setenv("CHUMMER_ORIGIN_EDITION_RUNNER_NAME", "Runner")
    monkeypatch.setenv("CHUMMER_ORIGIN_EDITION_BASE_URL", "https://example.test/")

    context = module.OriginEditionContext.from_env(project_id="project-from-cli")

    assert context.project_id == "project-from-cli"
    assert context.resolved_namespace == "origin.chummer.run/Family/Given/Runner"
    assert context.branch(tmp_path) == tmp_path / "origin.chummer.run/Family/Given/Runner"
    assert context.owner_url == "https://example.test/account/work/origin-dossiers/project-from-cli"
