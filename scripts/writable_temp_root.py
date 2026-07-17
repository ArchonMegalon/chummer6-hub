from __future__ import annotations

import os
import tempfile
from pathlib import Path


def resolve_writable_tmp_root(*, workspace_root: Path | None = None) -> Path | None:
    candidates = [
        os.environ.get("TMPDIR", "").strip(),
        str((workspace_root or Path.cwd()) / ".tmp") if workspace_root is not None else "",
        "/dev/shm",
        "/tmp",
    ]
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate).expanduser()
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        if path.is_dir() and os.access(path, os.W_OK | os.X_OK):
            return path
    return None


def configure_process_tmpdir(*, workspace_root: Path | None = None) -> Path | None:
    resolved = resolve_writable_tmp_root(workspace_root=workspace_root)
    if resolved is None:
        return None
    os.environ["TMPDIR"] = str(resolved)
    tempfile.tempdir = None
    return resolved


def subprocess_env(
    *,
    workspace_root: Path | None = None,
    extra_env: dict[str, str] | None = None,
) -> dict[str, str]:
    env = os.environ.copy()
    resolved = resolve_writable_tmp_root(workspace_root=workspace_root)
    if resolved is not None:
        env["TMPDIR"] = str(resolved)
    if extra_env:
        env.update(extra_env)
    return env
