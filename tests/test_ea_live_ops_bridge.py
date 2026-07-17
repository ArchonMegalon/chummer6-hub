from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "ea_live_ops.py"
HYGIENE = Path(__file__).resolve().parents[1] / "scripts" / "ea_live_ops_receipt_hygiene.py"


def _module():
    spec = importlib.util.spec_from_file_location("ea_live_ops_bridge", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _hygiene_module():
    spec = importlib.util.spec_from_file_location("ea_live_ops_receipt_hygiene", HYGIENE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_main_forwards_arguments_to_external_module(monkeypatch) -> None:
    module = _module()
    captured: dict[str, object] = {}

    def _fake_load(path: Path | None = None):
        def _main() -> int:
            captured["argv"] = sys.argv[:]
            return 7

        return SimpleNamespace(main=_main)

    monkeypatch.setattr(module, "load_ea_live_ops_module", _fake_load)

    exit_code = module.main(["probe-operator-readiness", "--timeout-seconds", "5"])

    assert exit_code == 7
    assert captured["argv"] == [
        str(module.DEFAULT_EA_LIVE_OPS_PATH),
        "probe-operator-readiness",
        "--timeout-seconds",
        "5",
    ]


def test_load_module_raises_when_external_script_missing(tmp_path: Path) -> None:
    module = _module()
    missing = tmp_path / "missing.py"
    try:
        module.load_ea_live_ops_module(missing)
    except FileNotFoundError as exc:
        assert "missing_ea_live_ops_script" in str(exc)
    else:
        raise AssertionError("expected FileNotFoundError")


def test_resolve_path_honors_environment_override(tmp_path: Path, monkeypatch) -> None:
    module = _module()
    override = tmp_path / "ea_live_ops.py"
    monkeypatch.setenv(module.EA_LIVE_OPS_SCRIPT_PATH_ENV, str(override))

    resolved = module.resolve_ea_live_ops_path()

    assert resolved == override


def test_main_uses_environment_override_for_forwarded_argv(tmp_path: Path, monkeypatch) -> None:
    module = _module()
    override = tmp_path / "ea_live_ops.py"
    captured: dict[str, object] = {}

    def _fake_load(path: Path | None = None):
        captured["loaded_path"] = path

        def _main() -> int:
            captured["argv"] = sys.argv[:]
            return 11

        return SimpleNamespace(main=_main)

    monkeypatch.setenv(module.EA_LIVE_OPS_SCRIPT_PATH_ENV, str(override))
    monkeypatch.setattr(module, "load_ea_live_ops_module", _fake_load)

    exit_code = module.main(["probe-mymedia-alexa", "--format", "json"])

    assert exit_code == 11
    assert captured["loaded_path"] == override
    assert captured["argv"] == [str(override), "probe-mymedia-alexa", "--format", "json"]


def test_public_source_ref_normalizes_module_style_script_names() -> None:
    module = _hygiene_module()

    assert module.public_source_ref("scripts.materialize_google_workspace_oauth_readiness.py") == (
        "script:materialize_google_workspace_oauth_readiness.py"
    )
    assert module.public_source_ref("telegram_delivery.py") == "script:telegram_delivery.py"
    assert module.public_source_ref("script:telegram_delivery.py") == "script:telegram_delivery.py"


def test_public_href_removes_url_credentials_and_sensitive_query_or_fragment_values() -> None:
    module = _hygiene_module()

    sanitized = module.public_href(
        "https://operator:private@example.com/proof?access_token=top-secret&page=2#session_id=private"
    )

    assert sanitized == "https://example.com/proof?page=2"
    assert "operator" not in sanitized
    assert "private" not in sanitized
    assert "top-secret" not in sanitized


def test_public_href_preserves_safe_public_route_queries() -> None:
    module = _hygiene_module()

    assert module.public_href("https://chummer.run/login?next=%2Fhome%2Fruns#continue") == (
        "https://chummer.run/login?next=%2Fhome%2Fruns#continue"
    )
    assert module.public_href("/login?next=/home/runs") == "/login?next=/home/runs"


def test_contains_secretish_key_covers_authorization_cookies_and_sessions() -> None:
    module = _hygiene_module()

    assert module.contains_secretish_key(
        {
            "headers": {"Authorization": "Bearer private"},
            "session_id": "private-session",
            "cookie": "auth=private",
        }
    )
    assert not module.contains_secretish_key(
        {
            "authorization_present": True,
            "session_id_sha256": "abc123",
            "credential_count": 2,
        }
    )
