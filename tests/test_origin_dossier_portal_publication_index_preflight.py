from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "materialize_origin_dossier_portal_publication_index_preflight.py"


def load_module():
    spec = importlib.util.spec_from_file_location("origin_dossier_portal_publication_index_preflight", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def inspect_payload(*, include_env: bool) -> dict[str, object]:
    env = ["ASPNETCORE_ENVIRONMENT=Production"]
    if include_env:
        env.append("CHUMMER_ORIGIN_DOSSIER_PUBLICATION_INDEX=/app/state/origin-dossier-publications.json")
    return {
        "Config": {"Env": env},
        "Mounts": [
            {
                "Type": "volume",
                "Name": "chummer6-hub_chummer-run-api-state",
                "Source": "/host/state",
                "Destination": "/app/state",
            }
        ],
    }


def write_support_files(root: Path) -> tuple[Path, Path, Path]:
    host_state = root / "state"
    host_state.mkdir()
    (host_state / "origin-dossier-publications.json").write_text('{"publications":[]}\n', encoding="utf-8")
    compose = root / "docker-compose.public-edge.yml"
    compose.write_text(
        "services:\n"
        "  chummer-portal:\n"
        "    environment:\n"
        "      CHUMMER_ORIGIN_DOSSIER_PUBLICATION_INDEX: ${CHUMMER_ORIGIN_DOSSIER_PUBLICATION_INDEX:-/app/state/origin-dossier-publications.json}\n",
        encoding="utf-8",
    )
    env_example = root / ".env.example"
    env_example.write_text(
        "CHUMMER_ORIGIN_DOSSIER_PUBLICATION_INDEX=/app/state/origin-dossier-publications.json\n",
        encoding="utf-8",
    )
    return host_state, compose, env_example


def test_preflight_blocks_when_existing_container_needs_restart(tmp_path: Path) -> None:
    module = load_module()
    host_state, compose, env_example = write_support_files(tmp_path)
    inspect_file = tmp_path / "inspect.json"
    write_json(inspect_file, [inspect_payload(include_env=False)])

    output = tmp_path / "preflight.json"
    result = module.materialize(
        output,
        host_state_root=host_state,
        inspect_file=inspect_file,
        compose_file=compose,
        env_example=env_example,
    )
    serialized = output.read_text(encoding="utf-8")

    assert result["status"] == "blocked"
    assert result["restartRequiredForExistingContainer"] is True
    assert "running_portal_publication_index_env_missing" in result["blockers"]
    assert result["runningContainer"]["stateMountPresent"] is True
    assert result["expectedHostPublicationIndex"]["present"] is True
    assert result["expectedHostPublicationIndex"]["nonempty"] is True
    assert result["configFiles"]["compose"]["publicationIndexConfigured"] is True
    assert result["configFiles"]["envExample"]["keyPresent"] is True
    assert result["runningContainer"]["envValueStoredInReceipt"] is False
    assert result["privacy"]["rawEnvValueExposed"] is False
    assert "/host/state" not in serialized
    assert "Restart/recreate chummer-portal only after explicit deploy approval" in result["next_action"]


def test_preflight_passes_when_running_container_has_expected_index(tmp_path: Path) -> None:
    module = load_module()
    host_state, compose, env_example = write_support_files(tmp_path)
    inspect_file = tmp_path / "inspect.json"
    write_json(inspect_file, [inspect_payload(include_env=True)])

    result = module.materialize(
        tmp_path / "preflight.json",
        host_state_root=host_state,
        inspect_file=inspect_file,
        compose_file=compose,
        env_example=env_example,
    )

    assert result["status"] == "pass"
    assert result["restartRequiredForExistingContainer"] is False
    assert result["blockers"] == []
    assert result["runningContainer"]["publicationIndexEnvPresent"] is True
    assert result["runningContainer"]["publicationIndexEnvMatchesExpected"] is True
    assert result["runningContainer"]["publicationIndexValueSha256"]
