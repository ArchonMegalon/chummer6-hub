from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "verify_rook_private_deployment.py"


def _module():
    spec = importlib.util.spec_from_file_location("rook_preflight", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_preflight_requires_immutable_image_and_private_env(tmp_path: Path) -> None:
    env_file = tmp_path / "rook.env"
    env_file.write_text("CHUMMER_BUILD_GHOST_PRIVATE_TOOL_SERVICE_TOKEN=x\n")
    env_file.chmod(0o600)
    module = _module()
    assert module.validate("ghcr.io/example/rook:latest", env_file) == [
        "image-must-be-sha256-digest-pinned"
    ]
    assert module.validate(
        "ghcr.io/example/rook@sha256:" + "a" * 64, env_file
    ) == []


def test_preflight_rejects_insecure_env_permissions(tmp_path: Path) -> None:
    env_file = tmp_path / "rook.env"
    env_file.write_text("TOKEN=redacted\n")
    env_file.chmod(0o644)
    module = _module()
    assert module.validate(
        "ghcr.io/example/rook@sha256:" + "b" * 64, env_file
    ) == ["env-file-must-not-be-group-or-world-accessible"]
