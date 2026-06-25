from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "materialize_origin_dossier_portal_publication_index_preflight.py"


def load_module():
    spec = importlib.util.spec_from_file_location("portal_preflight", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_preflight_blocks_when_running_container_needs_restart(tmp_path: Path) -> None:
    module = load_module()
    state = tmp_path / "state"
    state.mkdir()
    write(state / "origin-dossier-publications.json", "{}")
    compose = tmp_path / "docker-compose.public-edge.yml"
    write(compose, "CHUMMER_ORIGIN_DOSSIER_PUBLICATION_INDEX=/app/state/origin-dossier-publications.json")
    env_example = tmp_path / ".env.example"
    write(env_example, "CHUMMER_ORIGIN_DOSSIER_PUBLICATION_INDEX=/app/state/origin-dossier-publications.json")
    inspect = tmp_path / "inspect.json"
    write(inspect, json.dumps([{"Config": {"Env": []}, "Mounts": [{"Destination": "/app/state", "Source": "/secret/source"}]}]))

    result = module.materialize(
        tmp_path / "receipt.json",
        host_state_root=state,
        inspect_file=inspect,
        compose_file=compose,
        env_example=env_example,
    )
    serialized = (tmp_path / "receipt.json").read_text(encoding="utf-8")

    assert result["status"] == "blocked"
    assert result["restartRequiredForExistingContainer"] is True
    assert "running_portal_publication_index_env_missing" in result["blockers"]
    assert result["runningContainer"]["stateMountPresent"] is True
    assert "/secret/source" not in serialized


def test_preflight_passes_when_running_container_has_index(tmp_path: Path) -> None:
    module = load_module()
    state = tmp_path / "state"
    state.mkdir()
    write(state / "origin-dossier-publications.json", "{}")
    compose = tmp_path / "docker-compose.public-edge.yml"
    write(compose, "CHUMMER_ORIGIN_DOSSIER_PUBLICATION_INDEX=/app/state/origin-dossier-publications.json")
    env_example = tmp_path / ".env.example"
    write(env_example, "CHUMMER_ORIGIN_DOSSIER_PUBLICATION_INDEX=/app/state/origin-dossier-publications.json")
    inspect = tmp_path / "inspect.json"
    write(inspect, json.dumps([{"Config": {"Env": ["CHUMMER_ORIGIN_DOSSIER_PUBLICATION_INDEX=/app/state/origin-dossier-publications.json"]}, "Mounts": [{"Destination": "/app/state"}]}]))

    result = module.materialize(
        tmp_path / "receipt.json",
        host_state_root=state,
        inspect_file=inspect,
        compose_file=compose,
        env_example=env_example,
    )

    assert result["status"] == "pass"
    assert result["restartRequiredForExistingContainer"] is False
