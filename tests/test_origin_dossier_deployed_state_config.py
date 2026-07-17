from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "docker-compose.public-edge.yml"
ENV_EXAMPLE = ROOT / ".env.example"


def test_public_edge_configures_origin_publication_index_on_persistent_state_volume() -> None:
    source = COMPOSE.read_text(encoding="utf-8")

    assert "CHUMMER_ORIGIN_DOSSIER_PUBLICATION_INDEX" in source
    assert "${CHUMMER_ORIGIN_DOSSIER_PUBLICATION_INDEX:-/app/state/origin-dossier-publications.json}" in source
    assert "CHUMMER_ORIGIN_DOSSIER_PUBLICATION_INDEX: /tmp/" not in source


def test_public_edge_forwards_origin_provider_registry_and_visual_runtime_env() -> None:
    source = COMPOSE.read_text(encoding="utf-8")

    for snippet in (
        "CHUMMER_ORIGIN_AUDIOBOOKSHELF_TRUSTED_HOSTS: ${CHUMMER_ORIGIN_AUDIOBOOKSHELF_TRUSTED_HOSTS:-audio.chummer.run,audiobookshelf.chummer.run,audiobookshelf.girschele.com}",
        "CHUMMER_ORIGIN_PROVIDER_ACCOUNT_REGISTRY_PATH: ${CHUMMER_ORIGIN_PROVIDER_ACCOUNT_REGISTRY_PATH:-}",
        "CHUMMER_ORIGIN_PROVIDER_ACCOUNT_REGISTRY: ${CHUMMER_ORIGIN_PROVIDER_ACCOUNT_REGISTRY:-}",
        "CHUMMER_ORIGIN_PROVIDER_ACCOUNT_ALIASES: ${CHUMMER_ORIGIN_PROVIDER_ACCOUNT_ALIASES:-}",
        "CHUMMER_ORIGIN_MANUSCRIPT_ACCOUNT_ALIASES: ${CHUMMER_ORIGIN_MANUSCRIPT_ACCOUNT_ALIASES:-}",
        "CHUMMER_ORIGIN_AUDIO_ACCOUNT_ALIASES: ${CHUMMER_ORIGIN_AUDIO_ACCOUNT_ALIASES:-}",
        "CHUMMER_ORIGIN_VISUAL_ACCOUNT_ALIASES: ${CHUMMER_ORIGIN_VISUAL_ACCOUNT_ALIASES:-}",
        "CHUMMER_ORIGIN_PACKAGING_ACCOUNT_ALIASES: ${CHUMMER_ORIGIN_PACKAGING_ACCOUNT_ALIASES:-}",
        "CHUMMER_ORIGIN_TELEGRAM_ACCOUNT_ALIASES: ${CHUMMER_ORIGIN_TELEGRAM_ACCOUNT_ALIASES:-}",
        "CHUMMER_ORIGIN_MANUSCRIPT_PROVIDER_TOKENS: ${CHUMMER_ORIGIN_MANUSCRIPT_PROVIDER_TOKENS:-}",
        "CHUMMER_ORIGIN_AUDIO_PROVIDER_TOKENS: ${CHUMMER_ORIGIN_AUDIO_PROVIDER_TOKENS:-}",
        "CHUMMER_ORIGIN_VISUAL_PREFERRED_PROVIDER_TOKENS: ${CHUMMER_ORIGIN_VISUAL_PREFERRED_PROVIDER_TOKENS:-}",
        "CHUMMER_ORIGIN_VISUAL_PROVIDER_TOKENS: ${CHUMMER_ORIGIN_VISUAL_PROVIDER_TOKENS:-}",
        "CHUMMER_ORIGIN_PACKAGING_PROVIDER_TOKENS: ${CHUMMER_ORIGIN_PACKAGING_PROVIDER_TOKENS:-}",
        "CHUMMER_RENDER_POOL_PROVIDER_TOKENS: ${CHUMMER_RENDER_POOL_PROVIDER_TOKENS:-}",
    ):
        assert snippet in source


def test_env_example_documents_origin_publication_index_path() -> None:
    source = ENV_EXAMPLE.read_text(encoding="utf-8")

    assert "CHUMMER_ORIGIN_DOSSIER_PUBLICATION_INDEX=.state/origin-dossier-publications.json" in source


def test_env_example_documents_origin_provider_runtime_keys() -> None:
    source = ENV_EXAMPLE.read_text(encoding="utf-8")

    for snippet in (
        "CHUMMER_ORIGIN_AUDIOBOOKSHELF_TRUSTED_HOSTS=audio.chummer.run,audiobookshelf.chummer.run,audiobookshelf.girschele.com",
        "CHUMMER_ORIGIN_PROVIDER_ACCOUNT_REGISTRY_PATH=.state/origin-provider-accounts.json",
        "CHUMMER_ORIGIN_PROVIDER_ACCOUNT_REGISTRY=",
        "CHUMMER_ORIGIN_PROVIDER_ACCOUNT_ALIASES=",
        "CHUMMER_ORIGIN_MANUSCRIPT_ACCOUNT_ALIASES=",
        "CHUMMER_ORIGIN_AUDIO_ACCOUNT_ALIASES=",
        "CHUMMER_ORIGIN_VISUAL_ACCOUNT_ALIASES=",
        "CHUMMER_ORIGIN_PACKAGING_ACCOUNT_ALIASES=",
        "CHUMMER_ORIGIN_TELEGRAM_ACCOUNT_ALIASES=",
        "CHUMMER_ORIGIN_MANUSCRIPT_PROVIDER_TOKENS=",
        "CHUMMER_ORIGIN_AUDIO_PROVIDER_TOKENS=",
        "CHUMMER_ORIGIN_VISUAL_PREFERRED_PROVIDER_TOKENS=",
        "CHUMMER_ORIGIN_VISUAL_PROVIDER_TOKENS=",
        "CHUMMER_ORIGIN_PACKAGING_PROVIDER_TOKENS=",
        "CHUMMER_RENDER_POOL_PROVIDER_TOKENS=",
    ):
        assert snippet in source
