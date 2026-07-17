from __future__ import annotations

import os
from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / "scripts" / "deploy_public_edge_portal.sh"


@pytest.mark.parametrize("failure_phase", ["stop", "initializer", "recreate", "recreate_removed"])
def test_guarded_deploy_quiesces_before_init_and_restarts_prior_portal_on_failure(
    tmp_path: Path,
    failure_phase: str,
) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    docker_log = tmp_path / "docker.log"
    fake_python = fake_bin / "python3"
    fake_python.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    fake_python.chmod(0o755)
    fake_docker = fake_bin / "docker"
    fake_docker.write_text(
        """#!/bin/sh
set -eu
printf '%s\n' "$*" >> "$FAKE_DOCKER_LOG"
case "$*" in
  "image inspect chummer-run-api:local --format {{.Id}}")
    printf '%s\n' 'sha256:new-portal-image'
    ;;
  *" ps -q chummer-portal")
    printf '%s\n' 'prior-portal-container'
    ;;
  "container inspect --format {{.Image}} prior-portal-container")
    printf '%s\n' 'sha256:prior-portal-image'
    ;;
  "container inspect --format {{.State.Running}} prior-portal-container")
    printf '%s\n' 'true'
    ;;
  "container inspect prior-portal-container")
    if [ "$FAKE_DOCKER_FAILURE_PHASE" = recreate_removed ]; then exit 1; fi
    ;;
  *" stop chummer-portal")
    if [ "$FAKE_DOCKER_FAILURE_PHASE" = stop ]; then exit 43; fi
    ;;
  *" run --rm --no-deps chummer-portal-volume-init")
    if [ "$FAKE_DOCKER_FAILURE_PHASE" = initializer ]; then exit 37; fi
    ;;
  *" up -d --no-build --no-deps --force-recreate chummer-portal")
    if [ "$FAKE_DOCKER_FAILURE_PHASE" = recreate ]; then exit 41; fi
    if [ "$FAKE_DOCKER_FAILURE_PHASE" = recreate_removed ]; then
      count="$(grep -c ' up -d --no-build --no-deps --force-recreate chummer-portal$' "$FAKE_DOCKER_LOG")"
      if [ "$count" -eq 1 ]; then exit 41; fi
    fi
    ;;
esac
exit 0
""",
        encoding="utf-8",
    )
    fake_docker.chmod(0o755)

    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:{env['PATH']}",
            "FAKE_DOCKER_LOG": str(docker_log),
            "FAKE_DOCKER_FAILURE_PHASE": failure_phase,
            "CHUMMER_RUN_SERVICES_SOURCE": str(ROOT),
            "CHUMMER_PUBLIC_EDGE_BUILD_CONTEXT": str(ROOT),
            "CHUMMER_PUBLIC_EDGE_COMPOSE_FILE": str(ROOT / "docker-compose.public-edge.yml"),
            "CHUMMER_PUBLIC_EDGE_ENV_FILE": str(tmp_path / "missing.env"),
            "CHUMMER_PUBLIC_EDGE_EXPECTED_HEAD": "0" * 40,
            "CHUMMER_PUBLIC_EDGE_REQUIRE_UPSTREAM": "0",
        }
    )
    result = subprocess.run(
        ["bash", str(DEPLOY)],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode == 1
    commands = docker_log.read_text(encoding="utf-8").splitlines()
    stop_index = next(index for index, command in enumerate(commands) if command.endswith(" stop chummer-portal"))
    if failure_phase == "stop":
        restart_index = commands.index("start prior-portal-container")
        assert stop_index < restart_index
        assert not any(command.endswith(" run --rm --no-deps chummer-portal-volume-init") for command in commands)
        assert not any(command.endswith(" up -d --no-build --no-deps --force-recreate chummer-portal") for command in commands)
        return

    init_index = next(
        index for index, command in enumerate(commands) if command.endswith(" run --rm --no-deps chummer-portal-volume-init")
    )
    recreate_indexes = [
        index
        for index, command in enumerate(commands)
        if command.endswith(" up -d --no-build --no-deps --force-recreate chummer-portal")
    ]
    if failure_phase == "initializer":
        restart_index = commands.index("start prior-portal-container")
        assert stop_index < init_index < restart_index
        assert recreate_indexes == []
    elif failure_phase == "recreate":
        restart_index = commands.index("start prior-portal-container")
        assert len(recreate_indexes) == 1
        assert init_index < recreate_indexes[0] < restart_index
    else:
        prior_missing_index = commands.index("container inspect prior-portal-container")
        rollback_tag_index = commands.index("tag sha256:prior-portal-image chummer-run-api:local")
        assert len(recreate_indexes) == 2
        assert init_index < recreate_indexes[0] < prior_missing_index < rollback_tag_index < recreate_indexes[1]
        assert "start prior-portal-container" not in commands
