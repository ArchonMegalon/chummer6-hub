from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "prepare_operation_playwright_authority.py"


def load_module():
    specification = importlib.util.spec_from_file_location(
        "prepare_operation_playwright_authority_under_test",
        SCRIPT,
    )
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


def test_materialize_binds_exact_operation_private_authority(tmp_path: Path) -> None:
    module = load_module()
    tmp_path.chmod(0o700)
    host_build_root = tmp_path / "host-build"
    host_build_root.mkdir(mode=0o700)
    output = tmp_path / "playwright-authority-preparation.json"

    def builder(config):
        authority = config.host_build_root / "playwright-authority.json"
        authority.write_text('{"contractName":"test"}\n', encoding="utf-8")
        authority.chmod(0o600)
        digest = hashlib.sha256(authority.read_bytes()).hexdigest()
        return {
            "hostBuildRoot": str(config.host_build_root),
            "playwrightAuthority": str(authority),
            "playwrightAuthoritySha256": digest,
            "playwrightPythonTreeSha256": "a" * 64,
            "playwrightBrowserTreeSha256": "b" * 64,
        }

    receipt = module.materialize(
        host_build_root,
        output,
        builder=builder,
    )

    assert receipt["status"] == "pass"
    assert receipt["playwrightAuthority"] == str(
        host_build_root / "playwright-authority.json"
    )
    assert json.loads(output.read_text(encoding="utf-8")) == receipt
    assert output.stat().st_mode & 0o077 == 0


def test_materialize_rejects_builder_identity_mismatch(tmp_path: Path) -> None:
    module = load_module()
    tmp_path.chmod(0o700)
    host_build_root = tmp_path / "host-build"
    host_build_root.mkdir(mode=0o700)

    def builder(config):
        authority = config.host_build_root / "playwright-authority.json"
        authority.write_text("{}\n", encoding="utf-8")
        authority.chmod(0o600)
        return {
            "hostBuildRoot": str(config.host_build_root),
            "playwrightAuthority": str(authority),
            "playwrightAuthoritySha256": "0" * 64,
            "playwrightPythonTreeSha256": "a" * 64,
            "playwrightBrowserTreeSha256": "b" * 64,
        }

    with pytest.raises(RuntimeError, match="mismatched identity"):
        module.materialize(
            host_build_root,
            tmp_path / "playwright-authority-preparation.json",
            builder=builder,
        )
