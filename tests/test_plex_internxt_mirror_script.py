from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "ops" / "host-workload" / "plex-internxt-mirror.sh"


def run_bash(function_call: str, env: dict[str, str]) -> str:
    completed = subprocess.run(
        ["bash", "-lc", f"source '{SCRIPT}'; {function_call}"],
        cwd=REPO_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return completed.stdout.strip()


def base_env(tmp_path: Path) -> dict[str, str]:
    requested_root = tmp_path / "Requested"
    env = os.environ.copy()
    env.update(
        {
            "STATE_DIR": str(tmp_path / "state"),
            "PCLOUD_ROOT": str(tmp_path),
            "INTERNXT_ROOT": str(tmp_path / "internxt"),
            "MOVIES_DEST": str(tmp_path / "internxt" / "PLEX" / "Movies"),
            "TV_DEST": str(tmp_path / "internxt" / "PLEX" / "TV"),
            "REQUESTED_ROOT": str(requested_root),
            "REQUESTED_MOVIES_SOURCE": str(requested_root / "Movies"),
            "REQUESTED_TV_SOURCE": str(requested_root / "TV"),
            "REQUESTED_UNSORTED_SOURCE": str(requested_root / "Unsorted"),
            "REQUESTED_INBOX_SOURCE": str(requested_root / "_inbox"),
        }
    )
    return env


def test_requested_entry_type_uses_requested_subtrees(tmp_path: Path) -> None:
    env = base_env(tmp_path)
    movie_dir = Path(env["REQUESTED_MOVIES_SOURCE"]) / "Anastasia (1997)"
    tv_dir = Path(env["REQUESTED_TV_SOURCE"]) / "Bluey (2018)"
    movie_dir.mkdir(parents=True)
    tv_dir.mkdir(parents=True)

    assert run_bash(f"requested_entry_type '{movie_dir}'", env) == "movie"
    assert run_bash(f"requested_entry_type '{tv_dir}'", env) == "tv"


def test_requested_dest_entry_routes_inbox_episode_file_into_tv_show_folder(tmp_path: Path) -> None:
    env = base_env(tmp_path)
    inbox = Path(env["REQUESTED_INBOX_SOURCE"])
    inbox.mkdir(parents=True)
    episode = inbox / "Greys.Anatomy.S22E01.1080p.WEB.h264-ETHEL[EZTVx.to].mkv"
    episode.write_text("x", encoding="utf-8")

    result = run_bash(f"requested_dest_entry '{episode}'", env)

    assert result == str(Path(env["TV_DEST"]) / "G" / "Greys Anatomy" / episode.name)


def test_requested_dest_entry_routes_inbox_movie_file_into_movie_folder(tmp_path: Path) -> None:
    env = base_env(tmp_path)
    inbox = Path(env["REQUESTED_INBOX_SOURCE"])
    inbox.mkdir(parents=True)
    movie = inbox / "Minions.The.Rise.of.Gru.2022.D.MVO.BDRip.1080p.seleZen.mkv"
    movie.write_text("x", encoding="utf-8")

    result = run_bash(f"requested_dest_entry '{movie}'", env)

    assert result == str(
        Path(env["MOVIES_DEST"]) / "M" / "Minions The Rise of Gru (2022)" / movie.name
    )


def test_requested_dest_entry_routes_season_pack_directory_under_tv_show_folder(tmp_path: Path) -> None:
    env = base_env(tmp_path)
    inbox = Path(env["REQUESTED_INBOX_SOURCE"])
    season_pack = inbox / "Stranger Things - Season 3 (2019) [1080p]"
    season_pack.mkdir(parents=True)
    (season_pack / "Stranger.Things.S03E01.mkv").write_text("x", encoding="utf-8")

    result = run_bash(f"requested_dest_entry '{season_pack}'", env)

    assert result == str(
        Path(env["TV_DEST"]) / "S" / "Stranger Things" / "Stranger Things - Season 3 (2019) [1080p]"
    )


def test_update_status_writes_machine_readable_progress_state(tmp_path: Path) -> None:
    env = base_env(tmp_path)

    result = run_bash(
        "RUN_STARTED_AT='2026-07-06T03:10:28Z'; update_status 'running' 'movies' 'Movies' 25 1555 25 1840 'A.I. Rising (2019)' 'A' 'syncing'; cat \"$STATUS_FILE\"",
        env,
    )
    payload = json.loads(result)

    assert payload["status"] == "running"
    assert payload["phase"] == "movies"
    assert payload["phase_label"] == "Movies"
    assert payload["phase_current"] == 25
    assert payload["phase_total"] == 1555
    assert payload["overall_current"] == 25
    assert payload["overall_total"] == 1840
    assert payload["current_name"] == "A.I. Rising (2019)"
    assert payload["current_detail"] == "A"
    assert payload["note"] == "syncing"
    assert payload["run_started_at"] == "2026-07-06T03:10:28Z"


def test_handle_exit_writes_failed_status_with_exit_code(tmp_path: Path) -> None:
    env = base_env(tmp_path)

    result = run_bash(
        "RUN_STARTED_AT='2026-07-06T03:10:28Z'; OVERALL_TOTAL=1840; CURRENT_PHASE='movies'; CURRENT_PHASE_LABEL='Movies'; CURRENT_PHASE_CURRENT=100; CURRENT_PHASE_TOTAL=1555; CURRENT_OVERALL_CURRENT=100; CURRENT_NAME='Ant-Man and the Wasp - Quantumania (2023)'; CURRENT_DETAIL='A'; CURRENT_NOTE='syncing'; CURRENT_LAST_ERROR='internxt_write_failed'; handle_exit 23; cat \"$STATUS_FILE\"",
        env,
    )
    payload = json.loads(result)

    assert payload["status"] == "failed"
    assert payload["phase"] == "movies"
    assert payload["phase_current"] == 100
    assert payload["overall_current"] == 100
    assert payload["overall_total"] == 1840
    assert payload["last_error"] == "internxt_write_failed"
    assert payload["exit_code"] == 23
