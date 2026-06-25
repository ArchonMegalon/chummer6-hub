from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "origin_edition_provider_registry.py"


def load_module():
    spec = importlib.util.spec_from_file_location("origin_edition_provider_registry", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_provider_registry_uses_token_boundaries_not_substrings() -> None:
    module = load_module()
    registry = module.OriginProviderCapabilityRegistry()

    assert registry.audio_provider_allowed("Unmixr Account 02") is True
    assert registry.audio_provider_allowed("NotUnmixr Account 02") is False
    assert registry.manuscript_provider_allowed("Inkfluence Tier 3") is True
    assert registry.manuscript_provider_allowed("FakeInkfluenceProxy") is False


def test_provider_registry_keeps_configured_multi_word_provider_tokens() -> None:
    module = load_module()
    registry = module.OriginProviderCapabilityRegistry(
        manuscript_provider_tokens=("guided memoir lane",),
        audio_provider_tokens=("premiumvoice",),
    )

    assert registry.manuscript_provider_allowed("Guided Memoir Lane 02") is True
    assert registry.manuscript_provider_allowed("Unguided Memoir Lane 02") is False
    assert registry.audio_provider_allowed("PremiumVoice Account 04") is True
    assert registry.audio_provider_allowed("NotPremiumVoice Account 04") is False
