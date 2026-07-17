from __future__ import annotations

import os
from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / "scripts" / "deploy_public_edge_portal.sh"
MIGRATION_LOOP = ROOT / "scripts" / "migration-loop.sh"
RESTORE = ROOT / "scripts" / "restore_public_edge_portal_image.py"
RUNBOOK = ROOT / "docs" / "SELF_HOSTED_DOWNLOADS_RUNBOOK.md"


@pytest.mark.parametrize(
    "failure_phase",
    [
        "stop",
        "initializer",
        "recreate",
        "recreate_removed",
        "publication_readiness",
        "postdeploy",
    ],
)
def test_guarded_deploy_quiesces_before_init_and_restarts_prior_portal_on_failure(
    tmp_path: Path,
    failure_phase: str,
) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    docker_log = tmp_path / "docker.log"
    fake_python = fake_bin / "python3"
    fake_python.write_text(
        "#!/bin/sh\n"
        "set -eu\n"
        "case \"$*\" in\n"
        "  *verify_public_edge_postdeploy_gate.py*)\n"
        "    if [ \"$FAKE_DOCKER_FAILURE_PHASE\" = postdeploy ]; then exit 47; fi\n"
        "    ;;\n"
        "esac\n"
        "exit 0\n",
        encoding="utf-8",
    )
    fake_python.chmod(0o755)
    fake_docker = fake_bin / "docker"
    fake_docker.write_text(
        """#!/bin/sh
set -eu
printf '%s\n' "$*" >> "$FAKE_DOCKER_LOG"
case "$*" in
  "image ls --quiet --no-trunc --filter reference=chummer-run-api:local")
    image_list_count="$(grep -c '^image ls --quiet --no-trunc --filter reference=chummer-run-api:local$' "$FAKE_DOCKER_LOG")"
    if [ "$image_list_count" -eq 1 ]; then
      printf '%s\n' 'sha256:prior-portal-image'
    else
      printf '%s\n' 'sha256:new-portal-image'
    fi
    ;;
  "image inspect chummer-run-api:local --format {{.Id}}")
    printf '%s\n' 'sha256:new-portal-image'
    ;;
  *" ps --all -q chummer-portal")
    printf '%s\n' 'prior-portal-container'
    ;;
  "container inspect --format {{.Image}} prior-portal-container")
    printf '%s\n' 'sha256:prior-portal-image'
    ;;
  "container inspect --format {{.State.Running}} prior-portal-container")
    printf '%s\n' 'true'
    ;;
  "container inspect --format {{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}} prior-portal-container")
    printf '%s\n' 'healthy'
    ;;
  "container inspect prior-portal-container")
    if [ "$FAKE_DOCKER_FAILURE_PHASE" = recreate_removed ] \
      || [ "$FAKE_DOCKER_FAILURE_PHASE" = publication_readiness ] \
      || [ "$FAKE_DOCKER_FAILURE_PHASE" = postdeploy ]; then exit 1; fi
    ;;
  *" stop chummer-portal")
    if [ "$FAKE_DOCKER_FAILURE_PHASE" = stop ]; then exit 43; fi
    ;;
  *" run --rm --no-deps chummer-portal-volume-init")
    if [ "$FAKE_DOCKER_FAILURE_PHASE" = initializer ]; then exit 37; fi
    ;;
  *" up -d --no-build --no-deps --force-recreate --wait --wait-timeout 180 chummer-portal")
    if [ "$FAKE_DOCKER_FAILURE_PHASE" = recreate ]; then exit 41; fi
    if [ "$FAKE_DOCKER_FAILURE_PHASE" = recreate_removed ]; then
      count="$(grep -c ' up -d --no-build --no-deps --force-recreate --wait --wait-timeout 180 chummer-portal$' "$FAKE_DOCKER_LOG")"
      if [ "$count" -eq 1 ]; then exit 41; fi
    fi
    ;;
  *" exec -T chummer-portal curl "*)
    if [ "$FAKE_DOCKER_FAILURE_PHASE" = publication_readiness ]; then exit 45; fi
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
            "CHUMMER_PUBLIC_EDGE_POSTDEPLOY_ATTEMPTS": "1",
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
        assert not any(" up -d --no-build --no-deps --force-recreate " in command for command in commands)
        return

    init_index = next(
        index for index, command in enumerate(commands) if command.endswith(" run --rm --no-deps chummer-portal-volume-init")
    )
    recreate_indexes = [
        index
        for index, command in enumerate(commands)
        if command.endswith(" up -d --no-build --no-deps --force-recreate --wait --wait-timeout 180 chummer-portal")
    ]
    if failure_phase == "initializer":
        restart_index = commands.index("start prior-portal-container")
        assert stop_index < init_index < restart_index
        assert recreate_indexes == []
    elif failure_phase == "recreate":
        restart_index = commands.index("start prior-portal-container")
        assert len(recreate_indexes) == 1
        assert init_index < recreate_indexes[0] < restart_index
    elif failure_phase == "recreate_removed":
        prior_missing_index = commands.index("container inspect prior-portal-container")
        rollback_tag_index = commands.index("tag sha256:prior-portal-image chummer-run-api:local")
        rollback_recreate_index = recreate_indexes[-1]
        assert len(recreate_indexes) == 2
        assert init_index < recreate_indexes[0] < prior_missing_index < rollback_tag_index < rollback_recreate_index
        assert "start prior-portal-container" not in commands
    else:
        publication_index = next(
            index
            for index, command in enumerate(commands)
            if " exec -T chummer-portal curl " in command
        )
        rollback_stop_index = next(
            index
            for index, command in enumerate(
                commands[recreate_indexes[0] + 1 :], recreate_indexes[0] + 1
            )
            if command.endswith(" stop chummer-portal")
        )
        rollback_tag_index = commands.index(
            "tag sha256:prior-portal-image chummer-run-api:local"
        )
        rollback_recreate_index = recreate_indexes[-1]
        assert len(recreate_indexes) == 2
        assert init_index < recreate_indexes[0] < publication_index < rollback_stop_index
        assert rollback_stop_index < rollback_tag_index < rollback_recreate_index
        assert "start prior-portal-container" not in commands


def test_guarded_deploy_preflight_failure_prevents_every_docker_command(
    tmp_path: Path,
) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    python_log = tmp_path / "python.log"
    docker_log = tmp_path / "docker.log"
    fake_python = fake_bin / "python3"
    fake_python.write_text(
        "#!/bin/sh\n"
        "set -eu\n"
        "printf '%s\\n' \"$*\" >> \"$FAKE_PYTHON_LOG\"\n"
        "case \"$*\" in *check_public_edge_deploy_preflight.py*) exit 23;; esac\n"
        "exit 0\n",
        encoding="utf-8",
    )
    fake_python.chmod(0o755)
    fake_docker = fake_bin / "docker"
    fake_docker.write_text(
        "#!/bin/sh\n"
        "printf '%s\\n' \"$*\" >> \"$FAKE_DOCKER_LOG\"\n"
        "exit 0\n",
        encoding="utf-8",
    )
    fake_docker.chmod(0o755)
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:{env['PATH']}",
            "FAKE_PYTHON_LOG": str(python_log),
            "FAKE_DOCKER_LOG": str(docker_log),
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

    assert result.returncode == 23
    assert "check_public_edge_deploy_preflight.py" in python_log.read_text(encoding="utf-8")
    assert not docker_log.exists()


def test_guarded_deploy_compose_config_failure_prevents_image_build(
    tmp_path: Path,
) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    docker_log = tmp_path / "docker.log"
    fake_python = fake_bin / "python3"
    fake_python.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    fake_python.chmod(0o755)
    fake_docker = fake_bin / "docker"
    fake_docker.write_text(
        "#!/bin/sh\n"
        "set -eu\n"
        "printf '%s\\n' \"$*\" >> \"$FAKE_DOCKER_LOG\"\n"
        "case \"$*\" in *\" config --quiet\") exit 31;; esac\n"
        "exit 0\n",
        encoding="utf-8",
    )
    fake_docker.chmod(0o755)
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:{env['PATH']}",
            "FAKE_DOCKER_LOG": str(docker_log),
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

    assert result.returncode == 31
    commands = docker_log.read_text(encoding="utf-8").splitlines()
    assert len(commands) == 1
    assert commands[0].endswith(" config --quiet")
    assert all("buildx build" not in command for command in commands)


def test_guarded_deploy_build_failure_restores_exact_prior_image_tag(
    tmp_path: Path,
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
  "image ls --quiet --no-trunc --filter reference=chummer-run-api:local")
    count="$(grep -c '^image ls --quiet --no-trunc --filter reference=chummer-run-api:local$' "$FAKE_DOCKER_LOG")"
    if [ "$count" -eq 1 ]; then
      printf '%s\n' 'sha256:prior-tag-image'
    else
      printf '%s\n' 'sha256:partial-build-image'
    fi
    ;;
  "buildx build "*) exit 44 ;;
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

    assert result.returncode == 44
    commands = docker_log.read_text(encoding="utf-8").splitlines()
    build_index = next(
        index for index, command in enumerate(commands) if command.startswith("buildx build ")
    )
    restore_index = commands.index("tag sha256:prior-tag-image chummer-run-api:local")
    assert build_index < restore_index
    assert all(not command.endswith(" stop chummer-portal") for command in commands)


def test_migration_loop_runs_default_preflight_before_build_mutation(
    tmp_path: Path,
) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    python_log = tmp_path / "python.log"
    docker_log = tmp_path / "docker.log"
    fake_python = fake_bin / "python3"
    fake_python.write_text(
        "#!/bin/sh\n"
        "set -eu\n"
        "printf '%s\\n' \"$*\" >> \"$FAKE_PYTHON_LOG\"\n"
        "case \"$*\" in *check_public_edge_deploy_preflight.py*) exit 29;; esac\n"
        "exit 0\n",
        encoding="utf-8",
    )
    fake_python.chmod(0o755)
    fake_docker = fake_bin / "docker"
    fake_docker.write_text(
        "#!/bin/sh\n"
        "printf '%s\\n' \"$*\" >> \"$FAKE_DOCKER_LOG\"\n"
        "exit 0\n",
        encoding="utf-8",
    )
    fake_docker.chmod(0o755)
    env = os.environ.copy()
    env.pop("CHUMMER_PUBLIC_EDGE_DEPLOY_PREFLIGHT_GATE", None)
    env.update(
        {
            "PATH": f"{fake_bin}:{env['PATH']}",
            "FAKE_PYTHON_LOG": str(python_log),
            "FAKE_DOCKER_LOG": str(docker_log),
            "CHUMMER_PUBLIC_EDGE_DEPLOY_REPO_ROOT": str(ROOT),
            "CHUMMER_PUBLIC_EDGE_DEPLOY_SOURCE_GATE": "1",
            "CHUMMER_PORTAL_E2E": "0",
            "CHUMMER_HUB_E2E": "0",
        }
    )

    result = subprocess.run(
        ["bash", str(MIGRATION_LOOP), "1"],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode == 1
    python_commands = python_log.read_text(encoding="utf-8").splitlines()
    assert python_commands
    assert "check_public_edge_deploy_preflight.py" in python_commands[0]
    docker_commands = docker_log.read_text(encoding="utf-8").splitlines()
    assert all(" up -d --build " not in command for command in docker_commands)


@pytest.mark.parametrize(
    ("name", "value"),
    (
        ("CHUMMER_PUBLIC_EDGE_POSTDEPLOY_ATTEMPTS", "0"),
        ("CHUMMER_PUBLIC_EDGE_POSTDEPLOY_ATTEMPTS", "not-a-number"),
        ("CHUMMER_PUBLIC_EDGE_POSTDEPLOY_RETRY_DELAY_SECONDS", "-1"),
    ),
)
def test_guarded_deploy_rejects_postdeploy_bypass_before_docker(
    tmp_path: Path,
    name: str,
    value: str,
) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    docker_log = tmp_path / "docker.log"
    fake_docker = fake_bin / "docker"
    fake_docker.write_text(
        "#!/bin/sh\nprintf '%s\\n' \"$*\" >> \"$FAKE_DOCKER_LOG\"\n",
        encoding="utf-8",
    )
    fake_docker.chmod(0o755)
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:{env['PATH']}",
            "FAKE_DOCKER_LOG": str(docker_log),
            "CHUMMER_RUN_SERVICES_SOURCE": str(ROOT),
            "CHUMMER_PUBLIC_EDGE_BUILD_CONTEXT": str(ROOT),
            "CHUMMER_PUBLIC_EDGE_COMPOSE_FILE": str(ROOT / "docker-compose.public-edge.yml"),
            name: value,
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

    assert result.returncode == 2
    assert not docker_log.exists()


def test_guarded_deploy_rejects_unreviewed_compose_override_before_docker(
    tmp_path: Path,
) -> None:
    unreviewed_compose = tmp_path / "docker-compose.public-edge.yml"
    unreviewed_compose.write_text("services: {}\n", encoding="utf-8")
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    docker_log = tmp_path / "docker.log"
    fake_docker = fake_bin / "docker"
    fake_docker.write_text(
        "#!/bin/sh\nprintf '%s\\n' \"$*\" >> \"$FAKE_DOCKER_LOG\"\n",
        encoding="utf-8",
    )
    fake_docker.chmod(0o755)
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:{env['PATH']}",
            "FAKE_DOCKER_LOG": str(docker_log),
            "CHUMMER_RUN_SERVICES_SOURCE": str(ROOT),
            "CHUMMER_PUBLIC_EDGE_BUILD_CONTEXT": str(ROOT),
            "CHUMMER_PUBLIC_EDGE_COMPOSE_FILE": str(unreviewed_compose),
        }
    )

    result = subprocess.run(
        ["bash", str(DEPLOY)], cwd=ROOT, env=env, text=True, capture_output=True
    )

    assert result.returncode == 2
    assert "outside the audited source root" in result.stderr
    assert not docker_log.exists()


@pytest.mark.parametrize("failure", ("compose_ps", "container_image", "container_state"))
def test_guarded_deploy_fails_closed_when_prior_runtime_capture_fails(
    tmp_path: Path,
    failure: str,
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
  "image ls --quiet --no-trunc --filter reference=chummer-run-api:local") printf '%s\n' sha256:prior-image ;;
  "image inspect chummer-run-api:local --format {{.Id}}") printf '%s\n' sha256:new-image ;;
  *" ps --all -q chummer-portal")
    if [ "$FAKE_CAPTURE_FAILURE" = compose_ps ]; then exit 58; fi
    printf '%s\n' prior-portal
    ;;
  "container inspect --format {{.Image}} prior-portal")
    if [ "$FAKE_CAPTURE_FAILURE" = container_image ]; then exit 59; fi
    printf '%s\n' sha256:prior-image
    ;;
  "container inspect --format {{.State.Running}} prior-portal")
    if [ "$FAKE_CAPTURE_FAILURE" = container_state ]; then exit 60; fi
    printf '%s\n' true
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
            "FAKE_CAPTURE_FAILURE": failure,
            "CHUMMER_RUN_SERVICES_SOURCE": str(ROOT),
            "CHUMMER_PUBLIC_EDGE_BUILD_CONTEXT": str(ROOT),
            "CHUMMER_PUBLIC_EDGE_COMPOSE_FILE": str(ROOT / "docker-compose.public-edge.yml"),
            "CHUMMER_PUBLIC_EDGE_ENV_FILE": str(tmp_path / "missing.env"),
            "CHUMMER_PUBLIC_EDGE_EXPECTED_HEAD": "0" * 40,
            "CHUMMER_PUBLIC_EDGE_REQUIRE_UPSTREAM": "0",
        }
    )

    result = subprocess.run(
        ["bash", str(DEPLOY)], cwd=ROOT, env=env, text=True, capture_output=True
    )

    assert result.returncode == 3
    commands = docker_log.read_text(encoding="utf-8").splitlines()
    assert not any(command.endswith(" stop chummer-portal") for command in commands)
    assert not any("chummer-portal-volume-init" in command for command in commands)


def test_all_public_edge_mutators_share_one_nonoverrideable_host_lock() -> None:
    lock_path = "/docker/chummercomplete/.state/public-edge-mutation.lock"
    deploy_text = DEPLOY.read_text(encoding="utf-8")
    restore_text = RESTORE.read_text(encoding="utf-8")
    runbook_text = RUNBOOK.read_text(encoding="utf-8")

    assert f'DEPLOY_LOCK_DIR="$DEPLOY_LOCK_ROOT/public-edge-mutation.lock"' in deploy_text
    assert f'Path("{lock_path}")' in restore_text
    assert f"cutover_lock_dir={lock_path}" in runbook_text
    assert "CHUMMER_PUBLIC_EDGE_DEPLOY_LOCK_ROOT" not in deploy_text


def test_migration_loop_routes_portal_through_guarded_transaction_wrapper() -> None:
    script = MIGRATION_LOOP.read_text(encoding="utf-8")

    assert 'bash "$PUBLIC_EDGE_DEPLOY_REPO_ROOT/scripts/deploy_public_edge_portal.sh"' in script
    assert "up -d --build chummer-run-identity" in script
    assert "up -d --build --remove-orphans chummer-run-identity chummer-portal" not in script
    assert 'export CHUMMER_RUN_SERVICES_CONTEXT_DIR="$PUBLIC_EDGE_DEPLOY_REPO_ROOT"' in script


def test_guarded_deploy_restores_a_previously_stopped_portal_as_stopped(
    tmp_path: Path,
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
  "image ls --quiet --no-trunc --filter reference=chummer-run-api:local")
    count="$(grep -c '^image ls --quiet --no-trunc --filter reference=chummer-run-api:local$' "$FAKE_DOCKER_LOG")"
    if [ "$count" -eq 1 ]; then printf '%s\n' sha256:prior-image; else printf '%s\n' sha256:new-image; fi
    ;;
  "image inspect chummer-run-api:local --format {{.Id}}") printf '%s\n' sha256:new-image ;;
  *" ps --all -q chummer-portal")
    count="$(grep -c ' ps --all -q chummer-portal$' "$FAKE_DOCKER_LOG")"
    if [ "$count" -eq 1 ]; then printf '%s\n' prior-stopped; else printf '%s\n' restored-stopped; fi
    ;;
  "container inspect --format {{.Image}} prior-stopped"|"container inspect --format {{.Image}} restored-stopped") printf '%s\n' sha256:prior-image ;;
  "container inspect --format {{.State.Running}} prior-stopped"|"container inspect --format {{.State.Running}} restored-stopped") printf '%s\n' false ;;
  "container inspect prior-stopped") exit 1 ;;
  *" exec -T chummer-portal curl "*) exit 45 ;;
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
            "CHUMMER_RUN_SERVICES_SOURCE": str(ROOT),
            "CHUMMER_PUBLIC_EDGE_BUILD_CONTEXT": str(ROOT),
            "CHUMMER_PUBLIC_EDGE_COMPOSE_FILE": str(ROOT / "docker-compose.public-edge.yml"),
            "CHUMMER_PUBLIC_EDGE_ENV_FILE": str(tmp_path / "missing.env"),
            "CHUMMER_PUBLIC_EDGE_EXPECTED_HEAD": "0" * 40,
            "CHUMMER_PUBLIC_EDGE_REQUIRE_UPSTREAM": "0",
            "CHUMMER_PUBLIC_EDGE_POSTDEPLOY_ATTEMPTS": "1",
        }
    )

    result = subprocess.run(
        ["bash", str(DEPLOY)], cwd=ROOT, env=env, text=True, capture_output=True
    )

    assert result.returncode == 1
    commands = docker_log.read_text(encoding="utf-8").splitlines()
    assert any(command.endswith(" rm -f -s chummer-portal") for command in commands)
    assert any(command.endswith(" create --no-build --force-recreate chummer-portal") for command in commands)
    assert "start prior-stopped" not in commands
    assert "container inspect --format {{.State.Running}} restored-stopped" in commands
