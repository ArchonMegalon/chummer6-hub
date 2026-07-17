from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import pytest


ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / "scripts" / "deploy_public_edge_portal.sh"
MIGRATION_LOOP = ROOT / "scripts" / "migration-loop.sh"
RESTORE = ROOT / "scripts" / "restore_public_edge_portal_image.py"
PUBLISHER = ROOT / "scripts" / "publish_public_edge_portal_overlay.py"
RUNBOOK = ROOT / "docs" / "SELF_HOSTED_DOWNLOADS_RUNBOOK.md"


@pytest.fixture(autouse=True)
def fake_rendered_compose_contract(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for forbidden_name in (
        "BASH_ENV",
        "ENV",
        "CDPATH",
        "GLOBIGNORE",
        "LD_PRELOAD",
        "LD_LIBRARY_PATH",
        "PYTHONHOME",
        "PYTHONPATH",
        "PYTHONSTARTUP",
        "PYTHONINSPECT",
        "PYTHONBREAKPOINT",
        "PYTHONWARNINGS",
        "PYTHONSAFEPATH",
        "DOCKER_HOST",
        "DOCKER_CONTEXT",
        "DOCKER_CONFIG",
        "BUILDKIT_HOST",
        "BUILDX_BUILDER",
        "COMPOSE_FILE",
    ):
        monkeypatch.delenv(forbidden_name, raising=False)
    trusted_tools = tmp_path / "trusted-tools"
    trusted_tools.mkdir()
    trusted_python = trusted_tools / "python3"
    trusted_python.write_text(
        "#!/bin/sh\n"
        "set -eu\n"
        "if [ -n \"${FAKE_TRUSTED_PYTHON_LOG:-}\" ]; then printf '%s\\n' \"$*\" >> \"$FAKE_TRUSTED_PYTHON_LOG\"; fi\n"
        "case \"$*\" in\n"
        "  *verify_public_edge_deploy_authority.py*) exit \"${FAKE_AUTHORITY_EXIT:-0}\";;\n"
        "  *verify_public_edge_deploy_source.py*) exit \"${FAKE_SOURCE_GATE_EXIT:-0}\";;\n"
        "  *verify_public_edge_postdeploy_gate.py*) exec /usr/bin/python3 \"$@\";;\n"
        "  *validate_public_edge_compose_runtime.py*) /usr/bin/cat >/dev/null; exit 0;;\n"
        "  *secrets.token_hex*|*hmac.compare_digest*) exec /usr/bin/python3 \"$@\";;\n"
        "  *matches\\ =\\ \\[\\]*) exec /usr/bin/python3 \"$@\";;\n"
        "esac\n"
        "if [ \"${1:-}\" = -I ] && [ \"${2:-}\" = -c ]; then\n"
        "  /usr/bin/cat >/dev/null\n"
        "  printf '%s\\n' 'default|docker|default|running'\n"
        "  exit 0\n"
        "fi\n"
        "exec /usr/bin/env python3 \"$@\"\n",
        encoding="utf-8",
    )
    trusted_python.chmod(0o755)
    trusted_docker = trusted_tools / "docker"
    trusted_docker.write_text(
        "#!/bin/sh\n"
        "set -eu\n"
        "if [ \"${1:-}\" = --context ] && [ \"${2:-}\" = default ]; then shift 2; fi\n"
        "case \"$*\" in\n"
        "  \"context inspect default --format {{.Name}}|{{.Endpoints.docker.Host}}|{{.Endpoints.docker.SkipTLSVerify}}\")\n"
        "    if [ -n \"${FAKE_DOCKER_CONTEXT_PAUSE_READY:-}\" ]; then /usr/bin/touch \"$FAKE_DOCKER_CONTEXT_PAUSE_READY\"; /usr/bin/sleep 30; fi\n"
        "    printf '%s\\n' \"${FAKE_DOCKER_CONTEXT_IDENTITY:-default|unix:///var/run/docker.sock|false}\"; exit 0;;\n"
        "  \"buildx ls --format json\")\n"
        "    if [ -n \"${FAKE_BUILDER_JSON:-}\" ]; then printf '%s\\n' \"$FAKE_BUILDER_JSON\"; else printf '%s\\n' '{\"Current\":true,\"Driver\":\"docker\",\"Name\":\"default\",\"Nodes\":[{\"Endpoint\":\"default\",\"Name\":\"default\",\"Status\":\"running\"}]}'; fi; exit 0;;\n"
        "esac\n"
        "exec /usr/bin/env docker \"$@\"\n",
        encoding="utf-8",
    )
    trusted_docker.chmod(0o755)
    deploy_under_test = tmp_path / "deploy_public_edge_portal.sh"
    deploy_script = DEPLOY.read_text(encoding="utf-8")
    deploy_script = deploy_script.replace(
        'readonly TRUSTED_PYTHON="/usr/bin/python3"',
        f'readonly TRUSTED_PYTHON="{trusted_python}"',
    ).replace(
        'readonly TRUSTED_DOCKER="/usr/bin/docker"',
        f'readonly TRUSTED_DOCKER="{trusted_docker}"',
    ).replace(
        'ROOT_DIR="$("$TRUSTED_REALPATH" -e -- "$SCRIPT_DIR/..")"',
        f'ROOT_DIR="{ROOT}"',
    ).replace(
        'CANONICAL_DOCKER_CONFIG_ROOT="/docker/chummercomplete/.state/public-edge-docker-cli"',
        f'CANONICAL_DOCKER_CONFIG_ROOT="{tmp_path / "docker-config"}"',
    ).replace(
        'DEPLOY_LOCK_ROOT="/docker/chummercomplete/.state"',
        f'DEPLOY_LOCK_ROOT="{tmp_path / "lock-state"}"',
    ).replace("PATH=/usr/bin:/bin", 'PATH="$PATH"').replace(
        '"$TRUSTED_ENV" -i', '"$TRUSTED_ENV"'
    )
    deploy_under_test.write_text(deploy_script, encoding="utf-8")
    deploy_under_test.chmod(0o755)
    monkeypatch.setattr(sys.modules[__name__], "DEPLOY", deploy_under_test)
    monkeypatch.setenv("CHUMMER_PUBLIC_EDGE_EXPECTED_HEAD", "0" * 40)
    monkeypatch.setenv(
        "CHUMMER_PUBLIC_EDGE_EXPECTED_UPSTREAM_REF", "refs/remotes/origin/main"
    )
    monkeypatch.setenv("CHUMMER_PUBLIC_EDGE_REQUIRE_UPSTREAM", "1")
    monkeypatch.setenv("CHUMMER_PUBLIC_EDGE_CLEAN_LAUNCH", "1")
    monkeypatch.setenv(
        "CHUMMER_PUBLIC_EDGE_AUTHORITY_VERIFIER_SHA256",
        hashlib.sha256(
            (ROOT / "scripts" / "verify_public_edge_deploy_authority.py").read_bytes()
        ).hexdigest(),
    )
    release_channel_receipt = Path(
        "/docker/chummercomplete/chummer-hub-registry/.codex-studio/published/RELEASE_CHANNEL.generated.json"
    )
    runtime_proof = Path(
        "/docker/chummercomplete/chummer.run-services/.codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json"
    )
    monkeypatch.setenv(
        "CHUMMER_PUBLIC_EDGE_RELEASE_CHANNEL_RECEIPT",
        str(release_channel_receipt),
    )
    monkeypatch.setenv(
        "CHUMMER_PUBLIC_EDGE_RELEASE_CHANNEL_RECEIPT_SHA256",
        hashlib.sha256(release_channel_receipt.read_bytes()).hexdigest(),
    )
    monkeypatch.setenv(
        "CHUMMER_PUBLIC_EDGE_RUNTIME_PROOF_BIND_SOURCE_SHA256",
        hashlib.sha256(runtime_proof.read_bytes()).hexdigest(),
    )

    build = {
        "context": "/docker/chummercomplete",
        "dockerfile": str(ROOT / "Chummer.Run.Api" / "Dockerfile"),
        "additional_contexts": {
            "run-services-source": str(ROOT),
            "fleet-media-factory-contracts": "/docker/fleet/repos/chummer-media-factory/src/Chummer.Media.Contracts",
            "design-product": "/docker/chummercomplete/chummer-design",
        },
    }
    tool_build = {**build, "target": "install-linking-postgres-tool-final"}
    rendered = {
        "name": "chummer6-hub",
        "services": {
            "chummer-portal-volume-init": {"image": "chummer-run-api:local"},
            "chummer-portal": {
                "image": "chummer-run-api:local",
                "build": build,
                "environment": {
                    "CHUMMER_PUBLIC_PLAY_PROXY_ENABLED": "false",
                    "CHUMMER_PUBLIC_PLAY_LIVE_SESSION_PROXY_ENABLED": "false",
                },
                "volumes": [
                    {
                        "type": "bind",
                        "source": "/docker/chummercomplete/chummer.run-services/.state/public-edge-portal-overlay/app",
                        "target": "/app",
                        "read_only": True,
                    }
                ],
                "ports": [{"target": 8080, "published": "8091", "protocol": "tcp"}],
            },
            "chummer-install-linking-postgres-admin": {
                "image": "chummer-install-linking-postgres-tool:local",
                "build": tool_build,
            },
            "chummer-install-linking-postgres-import": {
                "image": "chummer-install-linking-postgres-tool:local",
                "build": tool_build,
            },
        },
    }
    path = tmp_path / "rendered-compose.json"
    path.write_text(json.dumps(rendered), encoding="utf-8")
    monkeypatch.setenv("FAKE_COMPOSE_CONFIG_JSON", str(path))
    monkeypatch.setenv(
        "CHUMMER_PUBLIC_EDGE_COMPOSE_ATTESTATION_OUTPUT",
        str(tmp_path / "compose-runtime-attestation.json"),
    )


def make_fake_authority_source(tmp_path: Path) -> Path:
    source = tmp_path / "source"
    (source / "scripts").mkdir(parents=True)
    (source / "Chummer.Run.Api").mkdir()
    (source / "docker-compose.public-edge.yml").write_text(
        "services: {}\n", encoding="utf-8"
    )
    (source / "Chummer.Run.Api" / "Dockerfile").write_text(
        "FROM scratch\n", encoding="utf-8"
    )
    (source / "scripts" / "validate_public_edge_compose_runtime.py").write_text(
        "import sys\nsys.stdin.read()\n",
        encoding="utf-8",
    )
    (source / "scripts" / "verify_public_edge_postdeploy_gate.py").write_text(
        "import json, os, pathlib, sys\n"
        "pathlib.Path(os.environ['FAKE_POSTDEPLOY_LOG']).write_text("
        "json.dumps(sys.argv[1:]), encoding='utf-8')\n"
        "raise SystemExit(int(os.environ.get('FAKE_POSTDEPLOY_EXIT', '0')))\n",
        encoding="utf-8",
    )
    return source


@pytest.mark.parametrize(
    ("missing_name", "message"),
    (
        (
            "CHUMMER_PUBLIC_EDGE_CLEAN_LAUNCH",
            "requires /usr/bin/env -i",
        ),
        (
            "CHUMMER_PUBLIC_EDGE_EXPECTED_HEAD",
            "externally supplied as a full 40-hex commit",
        ),
        (
            "CHUMMER_PUBLIC_EDGE_EXPECTED_UPSTREAM_REF",
            "full refs/remotes/... authority",
        ),
        (
            "CHUMMER_PUBLIC_EDGE_AUTHORITY_VERIFIER_SHA256",
            "independently supplied full SHA-256",
        ),
        (
            "CHUMMER_PUBLIC_EDGE_RELEASE_CHANNEL_RECEIPT_SHA256",
            "independently supplied as a lowercase SHA-256",
        ),
        (
            "CHUMMER_PUBLIC_EDGE_RUNTIME_PROOF_BIND_SOURCE_SHA256",
            "independently supplied as a lowercase SHA-256",
        ),
    ),
)
def test_guarded_deploy_requires_external_clean_launch_and_source_authorities(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    missing_name: str,
    message: str,
) -> None:
    docker_log = tmp_path / "docker.log"
    monkeypatch.delenv(missing_name, raising=False)
    monkeypatch.setenv("FAKE_DOCKER_LOG", str(docker_log))

    result = subprocess.run(
        ["/usr/bin/bash", "--noprofile", "--norc", str(DEPLOY)],
        cwd=ROOT,
        env=os.environ.copy(),
        text=True,
        capture_output=True,
    )

    assert result.returncode == 2
    assert message in result.stderr
    assert not docker_log.exists()


@pytest.mark.parametrize(
    ("name", "value", "message"),
    (
        (
            "CHUMMER_PUBLIC_EDGE_AUTHORITY_VERIFIER_SHA256",
            "0" * 64,
            "does not match its independent SHA-256 pin",
        ),
        (
            "CHUMMER_PUBLIC_EDGE_REQUIRE_UPSTREAM",
            "0",
            "upstream authority is mandatory",
        ),
    ),
)
def test_guarded_deploy_rejects_authority_pin_mismatch_or_upstream_bypass(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    value: str,
    message: str,
) -> None:
    docker_log = tmp_path / "docker.log"
    python_log = tmp_path / "python.log"
    monkeypatch.setenv(name, value)
    monkeypatch.setenv("FAKE_DOCKER_LOG", str(docker_log))
    monkeypatch.setenv("FAKE_TRUSTED_PYTHON_LOG", str(python_log))

    result = subprocess.run(
        ["/usr/bin/bash", "--noprofile", "--norc", str(DEPLOY)],
        cwd=ROOT,
        env=os.environ.copy(),
        text=True,
        capture_output=True,
    )

    assert result.returncode == 2
    assert message in result.stderr
    assert not docker_log.exists()
    assert not python_log.exists()


@pytest.mark.parametrize(
    "name",
    (
        "BASH_ENV",
        "ENV",
        "PYTHONPATH",
        "LD_PRELOAD",
        "LD_LIBRARY_PATH",
        "DOCKER_HOST",
        "DOCKER_CONTEXT",
        "DOCKER_CONFIG",
        "BUILDKIT_HOST",
        "BUILDX_BUILDER",
        "COMPOSE_FILE",
    ),
)
def test_guarded_deploy_rejects_ambient_execution_routing_before_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    name: str,
) -> None:
    docker_log = tmp_path / "docker.log"
    python_log = tmp_path / "python.log"
    monkeypatch.setenv(name, "/dev/null")
    monkeypatch.setenv("FAKE_DOCKER_LOG", str(docker_log))
    monkeypatch.setenv("FAKE_TRUSTED_PYTHON_LOG", str(python_log))

    result = subprocess.run(
        ["/usr/bin/bash", "--noprofile", "--norc", str(DEPLOY)],
        cwd=ROOT,
        env=os.environ.copy(),
        text=True,
        capture_output=True,
    )

    assert result.returncode == 2
    assert "rejects ambient execution routing" in result.stderr
    assert not docker_log.exists()
    assert not python_log.exists()


def test_guarded_deploy_authority_gate_precedes_selected_source_and_docker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    docker_log = tmp_path / "docker.log"
    python_log = tmp_path / "python.log"
    monkeypatch.setenv("FAKE_DOCKER_LOG", str(docker_log))
    monkeypatch.setenv("FAKE_TRUSTED_PYTHON_LOG", str(python_log))
    monkeypatch.setenv("FAKE_AUTHORITY_EXIT", "19")

    result = subprocess.run(
        ["/usr/bin/bash", "--noprofile", "--norc", str(DEPLOY)],
        cwd=ROOT,
        env=os.environ.copy(),
        text=True,
        capture_output=True,
    )

    assert result.returncode == 19
    python_calls = python_log.read_text(encoding="utf-8").splitlines()
    assert len(python_calls) == 1
    assert "verify_public_edge_deploy_authority.py" in python_calls[0]
    assert "check_public_edge_deploy_preflight.py" not in python_calls[0]
    assert not docker_log.exists()


@pytest.mark.parametrize(
    ("name", "value", "message"),
    (
        (
            "FAKE_DOCKER_CONTEXT_IDENTITY",
            "remote|tcp://attacker.invalid:2375|false",
            "non-canonical Docker daemon context",
        ),
        (
            "FAKE_BUILDER_JSON",
            '{"Current":true,"Driver":"docker-container","Name":"default","Nodes":[]}',
            "non-canonical Buildx builder",
        ),
    ),
)
def test_guarded_deploy_attests_local_daemon_and_builder_before_compose(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    value: str,
    message: str,
) -> None:
    docker_log = tmp_path / "docker.log"
    monkeypatch.setenv(name, value)
    monkeypatch.setenv("FAKE_DOCKER_LOG", str(docker_log))

    result = subprocess.run(
        ["/usr/bin/bash", "--noprofile", "--norc", str(DEPLOY)],
        cwd=ROOT,
        env=os.environ.copy(),
        text=True,
        capture_output=True,
    )

    assert result.returncode == 2
    assert message in result.stderr
    assert not docker_log.exists()
    assert not (tmp_path / "lock-state" / "public-edge-mutation.lock").exists()
    assert not list(
        (
            tmp_path
            / "lock-state"
            / "public-edge-lock-recovery-receipts"
        ).glob("deploy-*.owner-token")
    )


def test_guarded_deploy_rejects_identical_duplicate_default_builders(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    builder = {
        "Current": True,
        "Driver": "docker",
        "Name": "default",
        "Nodes": [
            {
                "Endpoint": "default",
                "Name": "default",
                "Status": "running",
            }
        ],
    }
    monkeypatch.setenv(
        "FAKE_BUILDER_JSON",
        "\n".join((json.dumps(builder), json.dumps(builder, sort_keys=True))),
    )
    result = subprocess.run(
        ["/usr/bin/bash", "--noprofile", "--norc", str(DEPLOY)],
        cwd=ROOT,
        env=os.environ.copy(),
        text=True,
        capture_output=True,
    )

    assert result.returncode == 2
    assert "non-canonical Buildx builder" in result.stderr


def test_guarded_deploy_rejects_conflicting_duplicate_default_builders(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    canonical = {
        "Current": True,
        "Driver": "docker",
        "Name": "default",
        "Nodes": [
            {
                "Endpoint": "default",
                "Name": "default",
                "Status": "running",
            }
        ],
    }
    conflicting = {
        **canonical,
        "Nodes": [{**canonical["Nodes"][0], "Status": "stopped"}],
    }
    monkeypatch.setenv(
        "FAKE_BUILDER_JSON",
        "\n".join((json.dumps(canonical), json.dumps(conflicting))),
    )

    result = subprocess.run(
        ["/usr/bin/bash", "--noprofile", "--norc", str(DEPLOY)],
        cwd=ROOT,
        env=os.environ.copy(),
        text=True,
        capture_output=True,
    )

    assert result.returncode == 2
    assert "non-canonical Buildx builder" in result.stderr
    assert not (tmp_path / "lock-state" / "public-edge-mutation.lock").exists()


def test_guarded_deploy_sigkill_leaves_external_authenticated_recovery_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ready = tmp_path / "docker-context-paused"
    monkeypatch.setenv("FAKE_DOCKER_CONTEXT_PAUSE_READY", str(ready))
    process = subprocess.Popen(
        ["/usr/bin/bash", "--noprofile", "--norc", str(DEPLOY)],
        cwd=ROOT,
        env=os.environ.copy(),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    deadline = time.monotonic() + 5
    while not ready.exists() and process.poll() is None and time.monotonic() < deadline:
        time.sleep(0.01)
    assert ready.exists(), "deploy did not reach the paused canonical Docker attestation"

    lock_token = tmp_path / "lock-state" / "public-edge-mutation.lock" / "owner-token"
    external_tokens = list(
        (
            tmp_path
            / "lock-state"
            / "public-edge-lock-recovery-receipts"
        ).glob("deploy-*.owner-token")
    )
    assert len(external_tokens) == 1
    external_token = external_tokens[0]
    assert lock_token.stat().st_mode & 0o777 == 0o600
    assert external_token.stat().st_mode & 0o777 == 0o600
    assert lock_token.read_text(encoding="ascii") == external_token.read_text(
        encoding="ascii"
    )

    os.killpg(process.pid, signal.SIGKILL)
    process.wait(timeout=5)

    assert (tmp_path / "lock-state" / "public-edge-mutation.lock").is_dir()
    assert external_token.is_file()


def test_guarded_deploy_unique_auth_orphan_does_not_block_new_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lock_root = tmp_path / "lock-state"
    auth_root = lock_root / "public-edge-lock-recovery-receipts"
    auth_root.mkdir(parents=True, mode=0o700)
    auth_root.chmod(0o700)
    orphan_token = "a" * 64
    orphan_digest = hashlib.sha256(orphan_token.encode("ascii")).hexdigest()
    orphan = auth_root / f"deploy-{orphan_digest}.owner-token"
    orphan.write_text(orphan_token + "\n", encoding="ascii")
    orphan.chmod(0o600)
    monkeypatch.setenv(
        "FAKE_DOCKER_CONTEXT_IDENTITY",
        "remote|tcp://attacker.invalid:2375|false",
    )

    result = subprocess.run(
        ["/usr/bin/bash", "--noprofile", "--norc", str(DEPLOY)],
        cwd=ROOT,
        env=os.environ.copy(),
        text=True,
        capture_output=True,
    )

    assert result.returncode == 2
    assert "non-canonical Docker daemon context" in result.stderr
    assert orphan.read_text(encoding="ascii") == orphan_token + "\n"
    assert not (lock_root / "public-edge-mutation.lock").exists()
    assert list(auth_root.glob("deploy-*.owner-token")) == [orphan]


def test_guarded_deploy_never_removes_tokenless_existing_fixed_lock(
    tmp_path: Path,
) -> None:
    lock_root = tmp_path / "lock-state"
    lock_root.mkdir(mode=0o700)
    fixed_lock = lock_root / "public-edge-mutation.lock"
    fixed_lock.mkdir(mode=0o700)

    result = subprocess.run(
        ["/usr/bin/bash", "--noprofile", "--norc", str(DEPLOY)],
        cwd=ROOT,
        env=os.environ.copy(),
        text=True,
        capture_output=True,
    )

    assert result.returncode == 75
    assert "another public-edge mutation owns" in result.stderr
    assert fixed_lock.is_dir()
    assert list(fixed_lock.iterdir()) == []
    assert not list(lock_root.glob(".public-edge-mutation.lock.staging.*"))
    assert not list(
        (lock_root / "public-edge-lock-recovery-receipts").glob(
            "deploy-*.owner-token"
        )
    )


@pytest.mark.parametrize(
    "failure_phase",
    [
        "stop",
        "initializer",
        "recreate",
        "recreate_removed",
        "publication_readiness",
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
case "$*" in *" config --format json") cat "$FAKE_COMPOSE_CONFIG_JSON"; exit 0;; esac
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
  *" exec -T chummer-portal /usr/bin/curl "*)
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
            "CHUMMER_PUBLIC_EDGE_BUILD_CONTEXT": "/docker/chummercomplete",
            "CHUMMER_PUBLIC_EDGE_COMPOSE_FILE": str(ROOT / "docker-compose.public-edge.yml"),
            "CHUMMER_PUBLIC_EDGE_ENV_FILE": "/docker/chummercomplete/chummer.run-services/.env",
            "CHUMMER_PUBLIC_EDGE_EXPECTED_HEAD": "0" * 40,
            "CHUMMER_PUBLIC_EDGE_REQUIRE_UPSTREAM": "1",
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
            if " exec -T chummer-portal /usr/bin/curl " in command
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


def test_guarded_deploy_uses_orchestrated_postdeploy_closure_and_no_legacy_flags(
    tmp_path: Path,
) -> None:
    source = make_fake_authority_source(tmp_path)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    (fake_bin / "python3").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    (fake_bin / "python3").chmod(0o755)
    docker_log = tmp_path / "docker.log"
    postdeploy_log = tmp_path / "postdeploy.json"
    fake_docker = fake_bin / "docker"
    fake_docker.write_text(
        """#!/bin/sh
set -eu
printf '%s\n' "$*" >> "$FAKE_DOCKER_LOG"
case "$*" in
  *" config --format json") printf '%s\n' '{}';;
  "image ls --quiet --no-trunc --filter reference=chummer-run-api:local")
    count="$(grep -c '^image ls --quiet --no-trunc --filter reference=chummer-run-api:local$' "$FAKE_DOCKER_LOG")"
    if [ "$count" -eq 1 ]; then printf '%s\n' sha256:prior; else printf '%s\n' sha256:candidate; fi
    ;;
  "image inspect chummer-run-api:local --format {{.Id}}") printf '%s\n' sha256:candidate ;;
  *" ps --all -q chummer-portal")
    count="$(grep -c ' ps --all -q chummer-portal$' "$FAKE_DOCKER_LOG")"
    if [ "$count" -eq 1 ]; then printf '%s\n' prior-container; else printf '%s\n' candidate-container; fi
    ;;
  "container inspect --format {{.Image}} prior-container") printf '%s\n' sha256:prior ;;
  "container inspect --format {{.Image}} candidate-container")
    if [ "${FAKE_CANDIDATE_MISMATCH:-0}" = 1 ]; then printf '%s\n' sha256:mismatch; else printf '%s\n' sha256:candidate; fi
    ;;
  "container inspect --format {{.State.Running}} prior-container") printf '%s\n' true ;;
  "container inspect --format {{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}} prior-container") printf '%s\n' healthy ;;
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
            "FAKE_POSTDEPLOY_LOG": str(postdeploy_log),
            "FAKE_POSTDEPLOY_EXIT": "47",
            "CHUMMER_RUN_SERVICES_SOURCE": str(source),
            "CHUMMER_PUBLIC_EDGE_COMPOSE_FILE": str(
                source / "docker-compose.public-edge.yml"
            ),
            "CHUMMER_PUBLIC_EDGE_EXPECTED_HEAD": "0" * 40,
            "CHUMMER_PUBLIC_EDGE_REQUIRE_UPSTREAM": "1",
            "CHUMMER_PUBLIC_EDGE_POSTDEPLOY_ATTEMPTS": "1",
        }
    )

    result = subprocess.run(
        ["bash", str(DEPLOY)], cwd=ROOT, env=env, text=True, capture_output=True
    )

    assert result.returncode == 1
    args = json.loads(postdeploy_log.read_text(encoding="utf-8"))
    assert args == [
        "--base-url",
        "https://chummer.run",
        "--strict-preflight",
        "--release-channel-receipt",
        "/docker/chummercomplete/chummer-hub-registry/.codex-studio/published/RELEASE_CHANNEL.generated.json",
        "--overlay-root",
        "/docker/chummercomplete/chummer.run-services/.state/public-edge-portal-overlay/app",
        "--expected-build-info",
        "/docker/chummercomplete/chummer.run-services/.state/public-edge-portal-overlay/app/.codex-studio/runtime/PUBLIC_EDGE_PORTAL_OVERLAY_BUILD_INFO.generated.json",
        "--require-downloads-status-playwright",
        "--require-mobile-pwa-viewport-playwright",
        "--require-frontdoor-navigation-playwright",
        "--playwright-artifact-dir",
        str(source / ".codex-studio/published/public-edge-browser-proofs/downloads-status"),
        "--mobile-pwa-viewport-artifact-dir",
        str(source / ".codex-studio/published/public-edge-browser-proofs/mobile-pwa-viewport"),
        "--frontdoor-navigation-artifact-dir",
        str(source / ".codex-studio/published/public-edge-browser-proofs/frontdoor-navigation"),
        "--output",
        str(source / ".codex-studio/published/PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json"),
    ]
    assert "--self-contained-direct" not in args
    assert "--expected-release-channel" not in args
    assert "--expected-portal-image-id" not in args


def test_guarded_deploy_rejects_candidate_image_mismatch_before_postdeploy(
    tmp_path: Path,
) -> None:
    source = make_fake_authority_source(tmp_path)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    (fake_bin / "python3").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    (fake_bin / "python3").chmod(0o755)
    postdeploy_log = tmp_path / "postdeploy.json"
    docker_log = tmp_path / "docker.log"
    fake_docker = fake_bin / "docker"
    fake_docker.write_text(
        """#!/bin/sh
set -eu
printf '%s\n' "$*" >> "$FAKE_DOCKER_LOG"
case "$*" in
  *" config --format json") printf '%s\n' '{}';;
  "image ls --quiet --no-trunc --filter reference=chummer-run-api:local")
    count="$(grep -c '^image ls --quiet --no-trunc --filter reference=chummer-run-api:local$' "$FAKE_DOCKER_LOG")"
    if [ "$count" -eq 1 ]; then printf '%s\n' sha256:prior; else printf '%s\n' sha256:candidate; fi ;;
  "image inspect chummer-run-api:local --format {{.Id}}") printf '%s\n' sha256:candidate ;;
  *" ps --all -q chummer-portal")
    count="$(grep -c ' ps --all -q chummer-portal$' "$FAKE_DOCKER_LOG")"
    if [ "$count" -eq 1 ]; then printf '%s\n' prior-container; else printf '%s\n' candidate-container; fi ;;
  "container inspect --format {{.Image}} prior-container") printf '%s\n' sha256:prior ;;
  "container inspect --format {{.Image}} candidate-container") printf '%s\n' sha256:mismatch ;;
  "container inspect --format {{.State.Running}} prior-container") printf '%s\n' true ;;
  "container inspect --format {{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}} prior-container") printf '%s\n' healthy ;;
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
            "FAKE_POSTDEPLOY_LOG": str(postdeploy_log),
            "CHUMMER_RUN_SERVICES_SOURCE": str(source),
            "CHUMMER_PUBLIC_EDGE_COMPOSE_FILE": str(
                source / "docker-compose.public-edge.yml"
            ),
            "CHUMMER_PUBLIC_EDGE_EXPECTED_HEAD": "0" * 40,
            "CHUMMER_PUBLIC_EDGE_REQUIRE_UPSTREAM": "1",
            "CHUMMER_PUBLIC_EDGE_POSTDEPLOY_ATTEMPTS": "1",
        }
    )

    result = subprocess.run(
        ["bash", str(DEPLOY)], cwd=ROOT, env=env, text=True, capture_output=True
    )

    assert result.returncode == 1
    assert "candidate image identity failed" in result.stderr
    assert not postdeploy_log.exists()


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
            "CHUMMER_PUBLIC_EDGE_BUILD_CONTEXT": "/docker/chummercomplete",
            "CHUMMER_PUBLIC_EDGE_COMPOSE_FILE": str(ROOT / "docker-compose.public-edge.yml"),
            "CHUMMER_PUBLIC_EDGE_ENV_FILE": "/docker/chummercomplete/chummer.run-services/.env",
            "CHUMMER_PUBLIC_EDGE_EXPECTED_HEAD": "0" * 40,
            "CHUMMER_PUBLIC_EDGE_REQUIRE_UPSTREAM": "1",
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
        "case \"$*\" in *\" config --format json\") exit 31;; esac\n"
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
            "CHUMMER_PUBLIC_EDGE_BUILD_CONTEXT": "/docker/chummercomplete",
            "CHUMMER_PUBLIC_EDGE_COMPOSE_FILE": str(ROOT / "docker-compose.public-edge.yml"),
            "CHUMMER_PUBLIC_EDGE_ENV_FILE": "/docker/chummercomplete/chummer.run-services/.env",
            "CHUMMER_PUBLIC_EDGE_EXPECTED_HEAD": "0" * 40,
            "CHUMMER_PUBLIC_EDGE_REQUIRE_UPSTREAM": "1",
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

    assert result.returncode != 0
    commands = docker_log.read_text(encoding="utf-8").splitlines()
    assert len(commands) == 1
    assert commands[0].endswith(" config --format json")
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
case "$*" in *" config --format json") cat "$FAKE_COMPOSE_CONFIG_JSON"; exit 0;; esac
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
            "CHUMMER_PUBLIC_EDGE_BUILD_CONTEXT": "/docker/chummercomplete",
            "CHUMMER_PUBLIC_EDGE_COMPOSE_FILE": str(ROOT / "docker-compose.public-edge.yml"),
            "CHUMMER_PUBLIC_EDGE_ENV_FILE": "/docker/chummercomplete/chummer.run-services/.env",
            "CHUMMER_PUBLIC_EDGE_EXPECTED_HEAD": "0" * 40,
            "CHUMMER_PUBLIC_EDGE_REQUIRE_UPSTREAM": "1",
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
            "CHUMMER_PUBLIC_EDGE_BUILD_CONTEXT": "/docker/chummercomplete",
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
            "CHUMMER_PUBLIC_EDGE_BUILD_CONTEXT": "/docker/chummercomplete",
            "CHUMMER_PUBLIC_EDGE_COMPOSE_FILE": str(unreviewed_compose),
        }
    )

    result = subprocess.run(
        ["bash", str(DEPLOY)], cwd=ROOT, env=env, text=True, capture_output=True
    )

    assert result.returncode == 2
    assert "outside the audited source root" in result.stderr
    assert not docker_log.exists()


@pytest.mark.parametrize(
    ("name", "value_kind", "message"),
    (
        ("CHUMMER_PUBLIC_EDGE_PROJECT_NAME", "literal", "non-canonical Compose project"),
        ("CHUMMER_PUBLIC_EDGE_PORTAL_IMAGE_TAG", "literal", "non-canonical portal image tag"),
        ("CHUMMER_PUBLIC_PORTAL_APP_OVERLAY_DIR", "literal", "non-canonical portal overlay root"),
        ("CHUMMER_PUBLIC_EDGE_BASE_URL", "literal", "non-canonical verification origin"),
        ("CHUMMER_PUBLIC_EDGE_PORT", "literal", "non-canonical public portal port"),
        ("CHUMMER_PUBLIC_EDGE_BUILD_CONTEXT", "directory", "non-canonical build context"),
        ("CHUMMER_PUBLIC_EDGE_ENV_FILE", "file", "non-canonical Compose environment file"),
        (
            "CHUMMER_PUBLIC_EDGE_RELEASE_CHANNEL_RECEIPT",
            "file",
            "non-canonical release-channel receipt",
        ),
    ),
)
def test_guarded_deploy_rejects_runtime_authority_override_before_docker(
    tmp_path: Path,
    name: str,
    value_kind: str,
    message: str,
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
    override = "noncanonical"
    if value_kind == "directory":
        override_path = tmp_path / "override"
        override_path.mkdir()
        override = str(override_path)
    elif value_kind == "file":
        override_path = tmp_path / "override"
        override_path.write_text("{}\n", encoding="utf-8")
        override = str(override_path)
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:{env['PATH']}",
            "FAKE_DOCKER_LOG": str(docker_log),
            "CHUMMER_RUN_SERVICES_SOURCE": str(ROOT),
            "CHUMMER_PUBLIC_EDGE_COMPOSE_FILE": str(ROOT / "docker-compose.public-edge.yml"),
            "CHUMMER_PUBLIC_EDGE_ENV_FILE": "/docker/chummercomplete/chummer.run-services/.env",
            "CHUMMER_PUBLIC_EDGE_BUILD_CONTEXT": "/docker/chummercomplete",
            name: override,
        }
    )

    result = subprocess.run(
        ["bash", str(DEPLOY)], cwd=ROOT, env=env, text=True, capture_output=True
    )

    assert result.returncode == 2
    assert message in result.stderr
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
case "$*" in *" config --format json") cat "$FAKE_COMPOSE_CONFIG_JSON"; exit 0;; esac
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
            "CHUMMER_PUBLIC_EDGE_BUILD_CONTEXT": "/docker/chummercomplete",
            "CHUMMER_PUBLIC_EDGE_COMPOSE_FILE": str(ROOT / "docker-compose.public-edge.yml"),
            "CHUMMER_PUBLIC_EDGE_ENV_FILE": "/docker/chummercomplete/chummer.run-services/.env",
            "CHUMMER_PUBLIC_EDGE_EXPECTED_HEAD": "0" * 40,
            "CHUMMER_PUBLIC_EDGE_REQUIRE_UPSTREAM": "1",
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
    shared_lock_text = (ROOT / "scripts" / "public_edge_mutation_lock.py").read_text(
        encoding="utf-8"
    )
    publisher_text = PUBLISHER.read_text(encoding="utf-8")
    runbook_text = RUNBOOK.read_text(encoding="utf-8")

    assert f'DEPLOY_LOCK_DIR="$DEPLOY_LOCK_ROOT/public-edge-mutation.lock"' in deploy_text
    assert "LOCK_PATH as PUBLIC_EDGE_MUTATION_LOCK" in restore_text
    assert 'LOCK_ROOT = Path("/docker/chummercomplete/.state")' in shared_lock_text
    assert 'LOCK_PATH = LOCK_ROOT / "public-edge-mutation.lock"' in shared_lock_text
    assert f'Path("{lock_path}")' in publisher_text
    assert f"cutover_lock_dir={lock_path}" in runbook_text
    assert "CHUMMER_PUBLIC_EDGE_DEPLOY_LOCK_ROOT" not in deploy_text
    assert '--shared-mutation-lock-token "$cutover_lock_token"' in runbook_text
    assert publisher_text.index("with public_edge_mutation_lock(") < publisher_text.index(
        "with overlay_publish_lock(",
        publisher_text.index("with public_edge_mutation_lock("),
    )


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
case "$*" in *" config --format json") cat "$FAKE_COMPOSE_CONFIG_JSON"; exit 0;; esac
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
  *" exec -T chummer-portal /usr/bin/curl "*) exit 45 ;;
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
            "CHUMMER_PUBLIC_EDGE_BUILD_CONTEXT": "/docker/chummercomplete",
            "CHUMMER_PUBLIC_EDGE_COMPOSE_FILE": str(ROOT / "docker-compose.public-edge.yml"),
            "CHUMMER_PUBLIC_EDGE_ENV_FILE": "/docker/chummercomplete/chummer.run-services/.env",
            "CHUMMER_PUBLIC_EDGE_EXPECTED_HEAD": "0" * 40,
            "CHUMMER_PUBLIC_EDGE_REQUIRE_UPSTREAM": "1",
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
