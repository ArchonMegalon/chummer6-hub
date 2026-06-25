from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "issue_chummer_deployed_owner_session.py"


def load_module():
    spec = importlib.util.spec_from_file_location("issue_chummer_deployed_owner_session", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeResponse:
    def __init__(self, status_code: int = 201, payload: dict | None = None, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self) -> dict:
        return self._payload


def issued_session() -> dict:
    return {
        "sessionId": "sid_test",
        "subjectId": "subject.owner",
        "displayName": "Owner Runner",
        "email": "owner@example.test",
        "roles": ["player"],
        "accessToken": "secret-owner-access-token",
        "refreshToken": "secret-refresh",
        "issuedAtUtc": "2026-06-25T12:00:00Z",
        "expiresAtUtc": "2026-06-25T20:00:00Z",
    }


def test_issue_session_calls_identity_admin_route_without_query_secret(monkeypatch) -> None:
    module = load_module()
    seen = {}

    def fake_post(url, headers, json, timeout):  # noqa: A002 - matches requests API
        seen["url"] = url
        seen["headers"] = headers
        seen["json"] = json
        seen["timeout"] = timeout
        return FakeResponse(payload=issued_session())

    monkeypatch.setattr(module.requests, "post", fake_post)

    payload = module.issue_session(
        identity_base_url="https://identity.chummer.run/",
        admin_key="admin-secret",
        subject_id="subject.owner",
        display_name="Owner Runner",
        email="owner@example.test",
        roles=["player"],
    )

    assert payload["accessToken"] == "secret-owner-access-token"
    assert seen["url"] == "https://identity.chummer.run/api/v1/identity/sessions"
    assert seen["headers"] == {"X-Identity-Admin-Key": "admin-secret"}
    assert seen["json"]["subjectId"] == "subject.owner"
    assert "admin-secret" not in seen["url"]


def test_render_env_output_is_directly_exportable_for_probe() -> None:
    module = load_module()

    rendered = module.render_output(issued_session(), "env", "chummer_hub_access_token")

    assert "CHUMMER_DEPLOYED_E2E_OWNER_SESSION_TOKEN" in rendered
    assert "secret-owner-access-token" in rendered
    assert "CHUMMER_DEPLOYED_E2E_AUTH_MODE=cookie" in rendered
    assert "CHUMMER_DEPLOYED_E2E_COOKIE_NAME=chummer_hub_access_token" in rendered


def test_render_dotenv_output_is_directly_loadable_by_probe_env_file() -> None:
    module = load_module()

    rendered = module.render_output(issued_session(), "dotenv", "chummer_hub_access_token")

    assert 'CHUMMER_DEPLOYED_E2E_OWNER_SESSION_TOKEN="secret-owner-access-token"' in rendered
    assert 'CHUMMER_DEPLOYED_E2E_AUTH_MODE="cookie"' in rendered
    assert 'CHUMMER_DEPLOYED_E2E_COOKIE_NAME="chummer_hub_access_token"' in rendered
    assert "export " not in rendered


def test_render_header_outputs_match_probe_inputs() -> None:
    module = load_module()

    cookie = module.render_output(issued_session(), "cookie-header", "chummer_hub_access_token")
    authorization = module.render_output(issued_session(), "authorization-header", "chummer_hub_access_token")

    assert "CHUMMER_DEPLOYED_E2E_COOKIE_HEADER" in cookie
    assert "chummer_hub_access_token=secret-owner-access-token" in cookie
    assert "CHUMMER_DEPLOYED_E2E_AUTHORIZATION_HEADER" in authorization
    assert "Bearer secret-owner-access-token" in authorization


def test_summary_output_does_not_expose_raw_token() -> None:
    module = load_module()

    rendered = module.render_output(issued_session(), "summary", "chummer_hub_access_token")
    payload = json.loads(rendered)

    assert payload["status"] == "issued"
    assert payload["rawTokenPrinted"] is False
    assert payload["accessTokenSha256"]
    assert "secret-owner-access-token" not in rendered


def test_derives_identity_subject_from_owner_email_like_chummer_identity() -> None:
    module = load_module()

    assert module.derive_subject_from_email("OWNER@Example.Test ") == "subject.email.b2096dbc5111b630"


def test_derives_route_proof_subject_from_origin_namespace() -> None:
    module = load_module()

    assert module.derive_subject_from_origin_namespace("origin.chummer.run/Varga/Mira/Kestrel") == "subject.origin-edition.c96868f7b6a6a550"
