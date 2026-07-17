from __future__ import annotations

import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "ops" / "host-workload" / "rclone-mount-watchdog.sh"


def run_bash(script: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-lc", f"source '{SCRIPT}'; {script}"],
        cwd=REPO_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )


def base_env(tmp_path: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "STATE_DIR": str(tmp_path / "state"),
            "LOCKFILE": str(tmp_path / "watchdog.lock"),
            "PLEX_TOKEN_FILE": str(tmp_path / "missing-token"),
            "COOLDOWN_SECS": "300",
            "REMOTES": "pcloud internxt",
            "CONFIG_DRIFT_REMOTES": "internxt",
        }
    )
    return env


def test_handle_runtime_config_drift_defers_restart_while_blocker_unit_is_active(tmp_path: Path) -> None:
    result = run_bash(
        """
        log() { printf '%s\\n' "$*"; }
        config_drift_blocker_active() { return 0; }
        unit_rc_addr_from_service() { printf '127.0.0.1:5574\\n'; }
        unit_cache_max_size_bytes() { printf '4294967296\\n'; }
        remote_runtime_cache_max_size_bytes() { printf '8589934592\\n'; }
        restart_mount_unit() { printf 'restart:%s\\n' "$1"; return 0; }
        wait_for_mount_ready() { return 0; }
        handle_runtime_config_drift internxt /mnt/internxt /mnt/internxt/PLEX rclone-mount@internxt.service
        printf 'reprobe:%s\\n' "$plex_reprobe_required"
        """,
        base_env(tmp_path),
    )

    assert result.returncode == 0, result.stderr
    assert "blocker units are active -> deferring mount restart" in result.stdout
    assert "restart:rclone-mount@internxt.service" not in result.stdout
    assert "reprobe:0" in result.stdout


def test_handle_runtime_config_drift_restarts_mount_once_idle_and_not_throttled(tmp_path: Path) -> None:
    result = run_bash(
        """
        log() { printf '%s\\n' "$*"; }
        config_drift_blocker_active() { return 1; }
        should_defer_for_active_plex() { return 1; }
        throttled() { return 1; }
        mark_action() { printf 'marked:%s\\n' "$1"; }
        clear_failure_count() { printf 'cleared:%s\\n' "$1"; }
        unit_rc_addr_from_service() { printf '127.0.0.1:5574\\n'; }
        unit_cache_max_size_bytes() { printf '4294967296\\n'; }
        remote_runtime_cache_max_size_bytes() { printf '8589934592\\n'; }
        restart_mount_unit() { printf 'restart:%s\\n' "$1"; return 0; }
        wait_for_mount_ready() { return 0; }
        handle_runtime_config_drift internxt /mnt/internxt /mnt/internxt/PLEX rclone-mount@internxt.service
        printf 'reprobe:%s\\n' "$plex_reprobe_required"
        """,
        base_env(tmp_path),
    )

    assert result.returncode == 0, result.stderr
    assert "runtime cache max size 8589934592 != configured 4294967296 -> restarting unit to apply config drift" in result.stdout
    assert "marked:config_drift.internxt" in result.stdout
    assert "restart:rclone-mount@internxt.service" in result.stdout
    assert "cleared:internxt" in result.stdout
    assert "reprobe:1" in result.stdout


def test_restart_stale_namespace_containers_uses_container_path_overrides(tmp_path: Path) -> None:
    env = base_env(tmp_path)
    env["STALE_NAMESPACE_DOCKER_CONTAINERS"] = "mymediaalexa"
    docker_log = tmp_path / "docker.log"
    env["DOCKER_LOG"] = str(docker_log)

    result = run_bash(
        """
        log() { printf '%s\\n' "$*"; }
        container_is_running() { return 0; }
        container_has_mount_destination() { printf 'dest:%s:%s\\n' "$1" "$2"; return 0; }
        container_probe_ok() { printf 'probe:%s:%s\\n' "$1" "$2"; return 1; }
        throttled() { return 1; }
        mark_action() { printf 'marked:%s\\n' "$1"; }
        docker() { printf 'docker %s\\n' "$*" >> "$DOCKER_LOG"; return 0; }
        restart_stale_namespace_containers /mnt/pcloud /mnt/pcloud/PLEX
        """,
        env,
    )

    assert result.returncode == 0, result.stderr
    assert "dest:mymediaalexa:/medialibrary" in result.stdout
    assert "probe:mymediaalexa:/medialibrary" in result.stdout
    assert "marked:container.mymediaalexa" in result.stdout
    assert docker_log.read_text(encoding="utf-8").strip() == "docker restart mymediaalexa"
