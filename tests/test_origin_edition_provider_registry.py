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
    assert registry.manuscript_provider_allowed("Subscribr Tier 4") is True
    assert registry.manuscript_provider_allowed("FakeSubscribrProxy") is False
    assert registry.manuscript_provider_allowed("Inkfluence Tier 3") is False
    assert registry.manuscript_provider_allowed("FakeInkfluenceProxy") is False


def test_provider_registry_keeps_configured_multi_word_provider_tokens() -> None:
    module = load_module()
    registry = module.OriginProviderCapabilityRegistry(
        manuscript_provider_tokens=("guided memoir lane",),
        audio_provider_tokens=("premiumvoice",),
        visual_provider_tokens=("magic fit",),
        visual_preferred_provider_tokens=("magic fit",),
        render_pool_provider_tokens=("omagic",),
    )

    assert registry.manuscript_provider_allowed("Guided Memoir Lane 02") is True
    assert registry.manuscript_provider_allowed("Unguided Memoir Lane 02") is False
    assert registry.audio_provider_allowed("PremiumVoice Account 04") is True
    assert registry.audio_provider_allowed("NotPremiumVoice Account 04") is False
    assert registry.visual_provider_allowed("Magic Fit Render 02") is True
    assert registry.visual_provider_allowed("NotAMagicVisualLane Account 04") is False
    assert registry.preferred_visual_provider_allowed("Magic Fit Render 02") is True
    assert registry.render_pool_provider_allowed("oMagic Account 04") is True


def test_provider_registry_uses_preferred_visual_tokens_as_visual_fallback(monkeypatch) -> None:
    monkeypatch.delenv("CHUMMER_ORIGIN_VISUAL_PROVIDER_TOKENS", raising=False)
    monkeypatch.setenv("CHUMMER_ORIGIN_VISUAL_PREFERRED_PROVIDER_TOKENS", "scene truth")
    module = load_module()

    registry = module.OriginProviderCapabilityRegistry.from_env()

    assert registry.visual_provider_tokens == ("scene truth",)
    assert registry.visual_preferred_provider_tokens == ("scene truth",)
    assert registry.visual_provider_allowed("Scene Truth Lane 01") is True
    assert registry.preferred_visual_provider_allowed("Scene Truth Lane 01") is True
