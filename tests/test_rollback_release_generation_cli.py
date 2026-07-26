from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import stat
import sys
from urllib import error as urlerror

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "rollback_release_generation.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "rollback_release_generation_under_test",
        SCRIPT_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def rollback():
    return _load_module()


def _base_args() -> list[str]:
    return [
        "--target-generation",
        "generation-retained",
        "--expected-current-generation",
        "generation-current",
        "--expected-current-snapshot-sha256",
        "1" * 64,
        "--expected-current-revision-id",
        f"auth-{'2' * 64}",
        "--idempotency-key",
        "rollback-20260726-nightly",
    ]


def test_dry_run_never_reads_a_token_and_writes_mode_0600_receipt(
    rollback,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "rollback-dry-run.json"

    def unexpected_token_read(_path):
        raise AssertionError("dry-run attempted to read an owner token")

    monkeypatch.setattr(rollback, "_read_owner_token", unexpected_token_read)

    assert rollback.main([*_base_args(), "--dry-run", "--output", str(output)]) == 0

    receipt = json.loads(output.read_text(encoding="utf-8"))
    assert receipt["contractName"] == rollback.RECEIPT_CONTRACT
    assert receipt["status"] == "dry_run"
    assert receipt["response"] is None
    assert receipt["endpoint"].endswith(
        "/api/internal/releases/generations/generation-retained/rollback"
    )
    assert stat.S_IMODE(output.stat().st_mode) == 0o600


def test_live_submission_uses_secure_token_and_immutable_receipt(
    rollback,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token_file = tmp_path / "fleet-owner-token"
    token_file.write_text("owner-secret-token\n", encoding="utf-8")
    token_file.chmod(0o600)
    output = tmp_path / "rollback-receipt.json"
    observed: dict[str, object] = {}

    def invoke(endpoint: str, body: bytes, token: str, timeout: int):
        observed.update(
            endpoint=endpoint,
            request=json.loads(body),
            token=token,
            timeout=timeout,
        )
        return {"status": "activated", "activationReceiptId": "activate-test"}

    monkeypatch.setattr(rollback, "_invoke", invoke)

    assert (
        rollback.main(
            [
                *_base_args(),
                "--token-file",
                str(token_file),
                "--output",
                str(output),
            ]
        )
        == 0
    )
    assert observed["token"] == "owner-secret-token"
    assert observed["timeout"] == 30
    assert observed["request"] == {
        "targetGenerationId": "generation-retained",
        "expectedCurrentGenerationId": "generation-current",
        "expectedCurrentSnapshotSha256": "1" * 64,
        "expectedCurrentRevisionId": f"auth-{'2' * 64}",
        "idempotencyKey": "rollback-20260726-nightly",
    }
    assert json.loads(output.read_text(encoding="utf-8"))["status"] == "submitted"
    with pytest.raises(rollback.RollbackClientError, match="new writable regular"):
        rollback.main(
            [
                *_base_args(),
                "--token-file",
                str(token_file),
                "--output",
                str(output),
            ]
        )


@pytest.mark.parametrize("mode", [0o400, 0o640, 0o666])
def test_owner_token_requires_exact_mode_0600(
    rollback,
    tmp_path: Path,
    mode: int,
) -> None:
    token_file = tmp_path / f"token-{mode:o}"
    token_file.write_text("owner-secret", encoding="utf-8")
    token_file.chmod(mode)

    with pytest.raises(rollback.RollbackClientError, match="mode 0600"):
        rollback._read_owner_token(token_file)


def test_owner_token_rejects_relative_symlink_and_hard_link_paths(
    rollback,
    tmp_path: Path,
) -> None:
    token_file = tmp_path / "token"
    token_file.write_text("owner-secret", encoding="utf-8")
    token_file.chmod(0o600)
    symlink = tmp_path / "token-symlink"
    symlink.symlink_to(token_file)

    with pytest.raises(rollback.RollbackClientError, match="must be absolute"):
        rollback._read_owner_token(Path("relative-token"))
    with pytest.raises(rollback.RollbackClientError, match="must not be a symlink"):
        rollback._read_owner_token(symlink)

    hard_link = tmp_path / "token-hard-link"
    os.link(token_file, hard_link)
    with pytest.raises(rollback.RollbackClientError, match="single-link"):
        rollback._read_owner_token(token_file)


@pytest.mark.parametrize(
    "candidate_origin",
    [
        "http://chummer.run",
        "https://www.chummer.run",
        "https://chummer.run:443",
        "https://user@chummer.run",
        "https://chummer.run/downloads",
        "https://chummer.run?redirect=1",
    ],
)
def test_endpoint_rejects_noncanonical_origins(
    rollback,
    candidate_origin: str,
) -> None:
    with pytest.raises(rollback.RollbackClientError, match="canonical owner endpoint"):
        rollback._endpoint(candidate_origin, "generation-retained")


def test_redirect_handler_fails_closed(rollback) -> None:
    handler = rollback._NoRedirect()
    with pytest.raises(urlerror.HTTPError) as caught:
        handler.redirect_request(
            type("Request", (), {"full_url": "https://chummer.run/source"})(),
            None,
            307,
            "Temporary Redirect",
            {},
            "https://attacker.invalid/",
        )
    assert caught.value.code == 307


def test_receipt_cannot_overwrite_current_pointer(rollback, tmp_path: Path) -> None:
    with pytest.raises(rollback.RollbackClientError, match="current.json"):
        rollback._write_receipt(
            tmp_path / "CURRENT.json",
            {"status": "must-not-write"},
        )


def test_response_parser_rejects_case_shadowed_fields(rollback) -> None:
    with pytest.raises(rollback.RollbackClientError, match="case-shadowed"):
        rollback._strict_response(b'{"status":"ok","Status":"drift"}', "response")
