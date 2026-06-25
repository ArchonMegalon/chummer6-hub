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


def test_env_example_documents_origin_publication_index_path() -> None:
    source = ENV_EXAMPLE.read_text(encoding="utf-8")

    assert "CHUMMER_ORIGIN_DOSSIER_PUBLICATION_INDEX=.state/origin-dossier-publications.json" in source
