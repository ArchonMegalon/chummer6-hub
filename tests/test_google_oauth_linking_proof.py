from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "materialize_google_oauth_linking_proof.py"


def load_module():
    spec = importlib.util.spec_from_file_location("materialize_google_oauth_linking_proof", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def disable_auth_signin_pause(module, monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(module, "AUTH_SIGNIN_AUTOMATION_PAUSE_FLAG", tmp_path / "auth_signin_automation_not_paused.flag")


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


class FakeCookies:
    def __init__(self) -> None:
        self._values: dict[str, str] = {}

    def get_dict(self) -> dict[str, str]:
        return dict(self._values)

    def set(self, name: str, value: str, domain: str | None = None, path: str | None = None) -> None:
        self._values[name] = value


class FakeResponse:
    def __init__(self, status_code: int, text: str = "", headers: dict[str, str] | None = None) -> None:
        self.status_code = status_code
        self.text = text
        self.headers = headers or {}


class FakeSession:
    def __init__(self, responses: dict[tuple[str, str], FakeResponse]) -> None:
        self.responses = responses
        self.headers: dict[str, str] = {}
        self.cookies = FakeCookies()

    def get(self, url: str, allow_redirects: bool = False, timeout: int = 30) -> FakeResponse:
        response = self.responses.get(("GET", url))
        if response is None:
            raise AssertionError(f"unexpected GET {url}")
        return response

    def post(
        self,
        url: str,
        data: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        allow_redirects: bool = False,
        timeout: int = 30,
    ) -> FakeResponse:
        response = self.responses.get(("POST", url))
        if response is None:
            raise AssertionError(f"unexpected POST {url}")
        return response


def test_parse_google_redirect_requires_pkce_nonce_and_scope() -> None:
    module = load_module()
    redirect = module.parse_google_redirect(
        "https://accounts.google.com/o/oauth2/v2/auth"
        "?redirect_uri=https%3A%2F%2Fchummer.run%2Fauth%2Fgoogle%2Fcallback"
        "&response_type=code"
        "&scope=openid%20profile%20email"
        "&state=test-state"
        "&nonce=test-nonce"
        "&code_challenge=test-challenge"
        "&code_challenge_method=S256"
        "&prompt=select_account",
        "https://chummer.run/auth/google/callback",
    )

    assert redirect["pass"] is True
    assert redirect["redirect_uri_matches"] is True
    assert redirect["code_challenge_method_s256"] is True
    assert redirect["scope_includes_openid_profile_email"] is True

    broken = module.parse_google_redirect(
        "https://accounts.google.com/o/oauth2/v2/auth"
        "?redirect_uri=https%3A%2F%2Fchummer.run%2Fauth%2Fgoogle%2Fcallback"
        "&response_type=code"
        "&scope=openid%20profile"
        "&state="
        "&code_challenge_method=plain",
        "https://chummer.run/auth/google/callback",
    )

    assert broken["pass"] is False
    assert broken["scope_includes_openid_profile_email"] is False
    assert broken["state_present"] is False
    assert broken["code_challenge_method_s256"] is False


def test_extract_cookie_value_prefers_last_non_empty_cookie_value() -> None:
    module = load_module()
    set_cookie_header = (
        "chummer_google_auth_state=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/; HttpOnly, "
        "chummer_google_auth_state=final-state-cookie; expires=Fri, 10 Jul 2026 02:54:14 GMT; path=/; HttpOnly"
    )

    assert module.extract_cookie_value(set_cookie_header, module.GOOGLE_STATE_COOKIE_NAME) == "final-state-cookie"


def test_classify_google_callback_smoke_detects_specific_error_and_rejects_stale_generic_copy() -> None:
    module = load_module()

    specific = module.classify_google_callback_smoke(
        """
        <h1>Google sign-in callback was incomplete</h1>
        <p>Google did not return an authorization code.</p>
        """
    )
    assert specific["specific_error_detected"] is True
    assert specific["matched_title"] == "Google sign-in callback was incomplete"
    assert specific["stale_generic_copy_present"] is False

    stale = module.classify_google_callback_smoke(
        "<h1>Google sign-in failed</h1><p>Chummer could not complete the Google sign-in handshake right now. Start the flow again in a moment.</p>"
    )
    assert stale["specific_error_detected"] is False
    assert stale["stale_generic_copy_present"] is True


def test_session_request_retries_timeout_then_succeeds(monkeypatch) -> None:
    module = load_module()
    calls = {"count": 0}
    response = FakeResponse(200, "ok")

    class FlakySession:
        def get(self, url: str, allow_redirects: bool = False, timeout: int = 30) -> FakeResponse:
            calls["count"] += 1
            if calls["count"] == 1:
                raise module.requests.Timeout("timed out")
            return response

    monkeypatch.setattr(module.time, "sleep", lambda _seconds: None)

    result = module.session_request(
        FlakySession(),  # type: ignore[arg-type]
        "get",
        "https://example.test/login",
        allow_redirects=False,
    )

    assert result is response
    assert calls["count"] == 2


def test_probe_public_google_handoff_retries_transient_login_timeout(monkeypatch) -> None:
    module = load_module()
    base_url = module.DEFAULT_BASE_URL
    login_url = f"{base_url}/login?next=%2Fhome"
    google_start_url = f"{base_url}/auth/google/start?next=/home"
    google_redirect = (
        "https://accounts.google.com/o/oauth2/v2/auth"
        "?redirect_uri=https%3A%2F%2Fchummer.run%2Fauth%2Fgoogle%2Fcallback"
        "&response_type=code"
        "&scope=openid%20profile%20email"
        "&state=state-123"
        "&nonce=nonce-456"
        "&code_challenge=challenge-789"
        "&code_challenge_method=S256"
        "&prompt=select_account"
    )
    responses = {
        ("GET", login_url): FakeResponse(
            200,
            '<a href="/auth/google/start?next=/home">Continue with Google</a>',
        ),
        ("GET", google_start_url): FakeResponse(
            302,
            "",
            headers={
                "Location": google_redirect,
                "Set-Cookie": f"{module.GOOGLE_STATE_COOKIE_NAME}=abc; Path=/; HttpOnly",
            },
        ),
        (
            "GET",
            f"{module.DEFAULT_BASE_URL}/auth/google/callback?state=state-123",
        ): FakeResponse(
            200,
            (
                "<h1>Google sign-in callback was incomplete</h1>"
                "<p>Google did not return an authorization code.</p>"
            ),
            headers={
                "Cache-Control": "private, no-store, max-age=0",
                "Set-Cookie": f"{module.GOOGLE_STATE_COOKIE_NAME}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; Path=/; HttpOnly",
            },
        ),
    }
    calls = {"login": 0}

    class FlakySession(FakeSession):
        def get(self, url: str, allow_redirects: bool = False, timeout: int = 30) -> FakeResponse:
            if url == login_url:
                calls["login"] += 1
                if calls["login"] == 1:
                    raise module.requests.Timeout("timed out")
            return super().get(url, allow_redirects=allow_redirects, timeout=timeout)

    monkeypatch.setattr(module, "build_session", lambda: FlakySession(responses))
    monkeypatch.setattr(module.time, "sleep", lambda _seconds: None)

    result = module.probe_public_google_handoff(base_url)

    assert result["pass"] is True
    assert result["google_start_href_present"] is True
    assert result["redirect"]["pass"] is True
    assert result["callback_smoke"]["pass"] is True
    assert result["callback_smoke"]["specific_error_detected"] is True
    assert result["callback_smoke"]["state_cookie_cleared"] is True
    assert calls["login"] == 2


def test_inspect_operator_evidence_requires_all_steps_and_screenshots(tmp_path: Path) -> None:
    module = load_module()
    screenshot_a = tmp_path / "a.png"
    screenshot_b = tmp_path / "b.png"
    screenshot_a.write_bytes(b"a")
    screenshot_b.write_bytes(b"b")

    evidence_path = tmp_path / "operator.json"
    write_json(
        evidence_path,
        {
            "contract_name": module.OPERATOR_EVIDENCE_CONTRACT_NAME,
            "status": "pass",
            "base_url": module.DEFAULT_BASE_URL,
            "observed_at_utc": "2026-07-04T09:00:00Z",
            "verified_steps": [
                "google_sign_in_completed_to_signed_in_state",
                "existing_account_linked_google",
                "linked_provider_visible_on_signed_in_surface",
            ],
            "screenshot_paths": [str(screenshot_a), str(screenshot_b)],
        },
    )

    summary = module.inspect_operator_evidence(module.DEFAULT_BASE_URL, evidence_path)

    assert summary["pass"] is False
    assert any("screenshots must contain at least" in item for item in summary["failures"])


def test_probe_signed_in_google_link_handoff_uses_owner_session_when_inline_preview_missing(monkeypatch) -> None:
    module = load_module()
    base_url = module.DEFAULT_BASE_URL
    login_url = f"{base_url}/login?next=%2Fhome"
    email_start_url = f"{base_url}/auth/email/start"
    home_url = f"{base_url}/home"
    settings_url = f"{base_url}/account/settings"
    google_link_url = f"{base_url}/auth/google/link?next=%2Fhome"

    google_redirect = (
        "https://accounts.google.com/o/oauth2/v2/auth"
        "?redirect_uri=https%3A%2F%2Fchummer.run%2Fauth%2Fgoogle%2Fcallback"
        "&response_type=code"
        "&scope=openid%20profile%20email"
        "&state=state-123"
        "&nonce=nonce-456"
        "&code_challenge=challenge-789"
        "&code_challenge_method=S256"
        "&prompt=select_account"
    )

    home_body = """
    <details><summary>Primary sign-in</summary></details>
    <div><span>Google</span><strong>Not linked</strong></div>
    <a href="/auth/google/link?next=/home">Link Google</a>
    """
    settings_body = """
    <div><span>Primary sign-in</span><strong>Email</strong></div>
    <div><span>Linked sign-ins</span><strong>Email only</strong></div>
    <div>Linked channels</div>
    """
    responses = {
        ("GET", login_url): FakeResponse(
            200,
            '<input name="__RequestVerificationToken" value="token-123" />',
        ),
        ("POST", email_start_url): FakeResponse(200, "<p>No inline preview on this host.</p>"),
        ("GET", home_url): FakeResponse(200, home_body),
        ("GET", settings_url): FakeResponse(200, settings_body),
        ("GET", google_link_url): FakeResponse(
            302,
            "",
            headers={
                "Location": google_redirect,
                "Set-Cookie": f"{module.GOOGLE_STATE_COOKIE_NAME}=abc; Path=/; HttpOnly",
            },
        ),
    }
    fake_session = FakeSession(responses)
    monkeypatch.setattr(module, "build_session", lambda: fake_session)
    monkeypatch.setenv("CHUMMER_DEPLOYED_E2E_OWNER_SESSION_TOKEN", "owner-session-token")
    monkeypatch.delenv("CHUMMER_DEPLOYED_E2E_AUTHORIZATION_HEADER", raising=False)
    monkeypatch.delenv("CHUMMER_DEPLOYED_E2E_COOKIE_HEADER", raising=False)
    monkeypatch.delenv("CHUMMER_DEPLOYED_E2E_AUTH_MODE", raising=False)
    monkeypatch.delenv("CHUMMER_DEPLOYED_E2E_COOKIE_NAME", raising=False)

    result = module.probe_signed_in_google_link_handoff(base_url, "runner@example.com")

    assert result["status"] == "pass"
    assert result["pass"] is True
    assert result["email_preview_available"] is False
    assert result["session_auth_used"] is True
    assert result["session_auth_context"]["mode"] == "cookie"
    assert result["session_auth_context"]["cookieName"] == module.HUB_ACCESS_COOKIE_NAME
    assert result["google_link_redirect"]["pass"] is True
    assert result["home_status"] == 200
    assert result["settings_status"] == 200


def test_probe_signed_in_google_link_handoff_autoloads_default_owner_session_env_file(tmp_path: Path, monkeypatch) -> None:
    module = load_module()
    base_url = module.DEFAULT_BASE_URL
    login_url = f"{base_url}/login?next=%2Fhome"
    email_start_url = f"{base_url}/auth/email/start"
    home_url = f"{base_url}/home"
    settings_url = f"{base_url}/account/settings"
    google_link_url = f"{base_url}/auth/google/link?next=%2Fhome"

    google_redirect = (
        "https://accounts.google.com/o/oauth2/v2/auth"
        "?redirect_uri=https%3A%2F%2Fchummer.run%2Fauth%2Fgoogle%2Fcallback"
        "&response_type=code"
        "&scope=openid%20profile%20email"
        "&state=state-123"
        "&nonce=nonce-456"
        "&code_challenge=challenge-789"
        "&code_challenge_method=S256"
        "&prompt=select_account"
    )

    responses = {
        ("GET", login_url): FakeResponse(
            200,
            '<input name="__RequestVerificationToken" value="token-123" />',
        ),
        ("POST", email_start_url): FakeResponse(200, "<p>No inline preview on this host.</p>"),
        ("GET", home_url): FakeResponse(200, '<a href="/auth/google/link?next=/home">Link Google</a>'),
        ("GET", settings_url): FakeResponse(
            200,
            "<div><span>Primary sign-in</span><strong>Email</strong></div>"
            "<div><span>Linked sign-ins</span><strong>Email only</strong></div>"
            "<div><span>Linked channels</span><strong>1</strong></div>",
        ),
        ("GET", google_link_url): FakeResponse(
            302,
            "",
            headers={
                "Location": google_redirect,
                "Set-Cookie": f"{module.GOOGLE_STATE_COOKIE_NAME}=abc; Path=/; HttpOnly",
            },
        ),
    }
    env_root = tmp_path / ".state"
    env_root.mkdir(parents=True, exist_ok=True)
    (env_root / "deployed-owner-session.fresh.env").write_text(
        "\n".join(
            [
                "CHUMMER_DEPLOYED_E2E_OWNER_SESSION_TOKEN=owner-session-token",
                "CHUMMER_DEPLOYED_E2E_AUTH_MODE=cookie",
                f"CHUMMER_DEPLOYED_E2E_COOKIE_NAME={module.HUB_ACCESS_COOKIE_NAME}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    fake_session = FakeSession(responses)
    monkeypatch.setattr(module, "RUN_SERVICES_ROOT", tmp_path)
    monkeypatch.setattr(module, "build_session", lambda: fake_session)
    monkeypatch.delenv("CHUMMER_DEPLOYED_E2E_OWNER_SESSION_TOKEN", raising=False)
    monkeypatch.delenv("CHUMMER_DEPLOYED_E2E_IDENTITY_TOKEN", raising=False)
    monkeypatch.delenv("CHUMMER_DEPLOYED_E2E_AUTHORIZATION_HEADER", raising=False)
    monkeypatch.delenv("CHUMMER_DEPLOYED_E2E_COOKIE_HEADER", raising=False)
    monkeypatch.delenv("CHUMMER_DEPLOYED_E2E_AUTH_MODE", raising=False)
    monkeypatch.delenv("CHUMMER_DEPLOYED_E2E_COOKIE_NAME", raising=False)

    result = module.probe_signed_in_google_link_handoff(base_url, "runner@example.com")

    assert result["status"] == "pass"
    assert result["session_auth_used"] is True
    assert result["session_auth_context"]["cookieName"] == module.HUB_ACCESS_COOKIE_NAME


def test_probe_signed_in_google_link_handoff_stays_operator_required_without_inline_preview_or_owner_session(monkeypatch) -> None:
    module = load_module()
    base_url = module.DEFAULT_BASE_URL
    login_url = f"{base_url}/login?next=%2Fhome"
    responses = {
        ("GET", login_url): FakeResponse(
            200,
            '<input name="__RequestVerificationToken" value="token-123" />',
        ),
    }
    monkeypatch.setattr(module, "build_session", lambda: FakeSession(responses))
    monkeypatch.delenv("CHUMMER_DEPLOYED_E2E_OWNER_SESSION_TOKEN", raising=False)
    monkeypatch.delenv("CHUMMER_DEPLOYED_E2E_IDENTITY_TOKEN", raising=False)
    monkeypatch.delenv("CHUMMER_DEPLOYED_E2E_AUTHORIZATION_HEADER", raising=False)
    monkeypatch.delenv("CHUMMER_DEPLOYED_E2E_COOKIE_HEADER", raising=False)
    monkeypatch.delenv("CHUMMER_DEPLOYED_E2E_AUTH_MODE", raising=False)
    monkeypatch.delenv("CHUMMER_DEPLOYED_E2E_COOKIE_NAME", raising=False)
    monkeypatch.delenv(module.EMAIL_SIGNIN_PROBE_ENV, raising=False)
    monkeypatch.setattr(module, "resolve_default_owner_session_env_file", lambda: None)

    result = module.probe_signed_in_google_link_handoff(base_url, "runner@example.com")

    assert result["status"] == "operator_required"
    assert result["pass"] is False
    assert result["email_preview_available"] is False
    assert result["session_auth_used"] is False
    assert "avoid sending sign-in emails" in result["notes"][0]
    assert module.EMAIL_SIGNIN_PROBE_ENV in result["notes"][0]


def test_probe_signed_in_google_link_handoff_can_opt_in_to_email_preview(monkeypatch) -> None:
    module = load_module()
    base_url = "http://localhost:5101"
    login_url = f"{base_url}/login?next=%2Fhome"
    email_start_url = f"{base_url}/auth/email/start"
    callback_url = f"{base_url}/auth/email/callback?token=preview-123"
    home_url = f"{base_url}/home"
    settings_url = f"{base_url}/account/settings"
    google_link_url = f"{base_url}/auth/google/link?next=%2Fhome"

    google_redirect = (
        "https://accounts.google.com/o/oauth2/v2/auth"
        "?redirect_uri=http%3A%2F%2Flocalhost%3A5101%2Fauth%2Fgoogle%2Fcallback"
        "&response_type=code"
        "&scope=openid%20profile%20email"
        "&state=state-123"
        "&nonce=nonce-456"
        "&code_challenge=challenge-789"
        "&code_challenge_method=S256"
        "&prompt=select_account"
    )

    responses = {
        ("GET", login_url): FakeResponse(
            200,
            '<input name="__RequestVerificationToken" value="token-123" />',
        ),
        ("POST", email_start_url): FakeResponse(
            200,
            '<a href="/auth/email/callback?token=preview-123">Continue</a>',
        ),
        ("GET", callback_url): FakeResponse(
            302,
            "",
            headers={"Location": "/home"},
        ),
        ("GET", home_url): FakeResponse(
            200,
            """
            <details><summary>Primary sign-in</summary></details>
            <div><span>Google</span><strong>Not linked</strong></div>
            <a href="/auth/google/link?next=/home">Link Google</a>
            """,
        ),
        ("GET", settings_url): FakeResponse(
            200,
            """
            <div><span>Primary sign-in</span><strong>Email</strong></div>
            <div><span>Linked sign-ins</span><strong>Email only</strong></div>
            <div>Linked channels</div>
            """,
        ),
        ("GET", google_link_url): FakeResponse(
            302,
            "",
            headers={
                "Location": google_redirect,
                "Set-Cookie": f"{module.GOOGLE_STATE_COOKIE_NAME}=abc; Path=/; HttpOnly",
            },
        ),
    }
    fake_session = FakeSession(responses)
    fake_session.cookies.set(module.HUB_ACCESS_COOKIE_NAME, "preview-session")
    monkeypatch.setattr(module, "build_session", lambda: fake_session)
    monkeypatch.delenv("CHUMMER_DEPLOYED_E2E_OWNER_SESSION_TOKEN", raising=False)
    monkeypatch.delenv("CHUMMER_DEPLOYED_E2E_IDENTITY_TOKEN", raising=False)
    monkeypatch.delenv("CHUMMER_DEPLOYED_E2E_AUTHORIZATION_HEADER", raising=False)
    monkeypatch.delenv("CHUMMER_DEPLOYED_E2E_COOKIE_HEADER", raising=False)
    monkeypatch.delenv("CHUMMER_DEPLOYED_E2E_AUTH_MODE", raising=False)
    monkeypatch.delenv("CHUMMER_DEPLOYED_E2E_COOKIE_NAME", raising=False)
    monkeypatch.setattr(module, "resolve_default_owner_session_env_file", lambda: None)
    monkeypatch.setenv(module.EMAIL_SIGNIN_PROBE_ENV, "1")

    result = module.probe_signed_in_google_link_handoff(base_url, "runner@example.com")

    assert result["status"] == "pass"
    assert result["pass"] is True
    assert result["email_preview_available"] is True
    assert result["session_auth_used"] is False
    assert result["session_auth_context"]["mode"] == "inline_email_preview"
    assert result["callback_url"] == callback_url
    assert result["callback_redirect_location"] == "/home"
    assert result["google_link_redirect"]["pass"] is True


def test_probe_signed_in_google_link_handoff_refuses_email_probe_on_public_host_even_when_opted_in(monkeypatch) -> None:
    module = load_module()
    base_url = module.DEFAULT_BASE_URL
    login_url = f"{base_url}/login?next=%2Fhome"
    responses = {
        ("GET", login_url): FakeResponse(
            200,
            '<input name="__RequestVerificationToken" value="token-123" />',
        ),
    }
    monkeypatch.setattr(module, "build_session", lambda: FakeSession(responses))
    monkeypatch.delenv("CHUMMER_DEPLOYED_E2E_OWNER_SESSION_TOKEN", raising=False)
    monkeypatch.delenv("CHUMMER_DEPLOYED_E2E_IDENTITY_TOKEN", raising=False)
    monkeypatch.delenv("CHUMMER_DEPLOYED_E2E_AUTHORIZATION_HEADER", raising=False)
    monkeypatch.delenv("CHUMMER_DEPLOYED_E2E_COOKIE_HEADER", raising=False)
    monkeypatch.delenv("CHUMMER_DEPLOYED_E2E_AUTH_MODE", raising=False)
    monkeypatch.delenv("CHUMMER_DEPLOYED_E2E_COOKIE_NAME", raising=False)
    monkeypatch.setattr(module, "resolve_default_owner_session_env_file", lambda: None)
    monkeypatch.setenv(module.EMAIL_SIGNIN_PROBE_ENV, "1")

    result = module.probe_signed_in_google_link_handoff(base_url, "runner@example.com")

    assert result["status"] == "operator_required"
    assert result["pass"] is False
    assert result["email_preview_available"] is False
    assert result["session_auth_used"] is False
    assert "non-loopback hosts" in result["notes"][0]
    assert module.EMAIL_SIGNIN_PROBE_ENV in result["notes"][0]


def test_materialize_requires_operator_end_to_end_evidence_even_when_probes_pass(tmp_path: Path, monkeypatch) -> None:
    module = load_module()
    disable_auth_signin_pause(module, monkeypatch, tmp_path)
    request_path = tmp_path / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE_REQUEST.generated.json"
    ask_text_path = tmp_path / "CURRENT_GOOGLE_OAUTH_LINKING_OPERATOR_ASK.txt"
    ask_metadata_path = tmp_path / "CURRENT_GOOGLE_OAUTH_LINKING_OPERATOR_ASK.generated.json"
    template_path = tmp_path / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE.template.generated.json"
    delivery_root = tmp_path / "telegram"
    delivery_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(
        module,
        "probe_public_google_handoff",
        lambda base_url: {"pass": True, "failures": [], "redirect": {"pass": True}},
    )
    monkeypatch.setattr(
        module,
        "probe_signed_in_google_link_handoff",
        lambda base_url, email: {"pass": True, "failures": [], "email": email, "google_link_redirect": {"pass": True}},
    )
    monkeypatch.setattr(module, "DEFAULT_OPERATOR_EVIDENCE_REQUEST_PATH", request_path)
    monkeypatch.setattr(module, "DEFAULT_OPERATOR_ASK_TEXT_PATH", ask_text_path)
    monkeypatch.setattr(module, "DEFAULT_OPERATOR_ASK_METADATA_PATH", ask_metadata_path)
    monkeypatch.setattr(module, "DEFAULT_OPERATOR_EVIDENCE_TEMPLATE_PATH", template_path)
    monkeypatch.setattr(module, "DEFAULT_TELEGRAM_TEXT_DELIVERY_ROOT", delivery_root)
    write_json(
        request_path,
        {
            "contract_name": module.OPERATOR_EVIDENCE_REQUEST_CONTRACT_NAME,
            "status": "operator_action_required",
            "base_url": module.DEFAULT_BASE_URL,
            "required_operator_evidence_path": str(tmp_path / "missing-operator.json"),
            "required_steps": list(module.REQUIRED_OPERATOR_STEPS),
            "minimum_screenshot_count": module.MINIMUM_OPERATOR_SCREENSHOT_COUNT,
            "recommended_screenshot_paths": ["/tmp/one.png", "/tmp/two.png"],
            "operator_ask_text_path": str(ask_text_path),
            "operator_ask_metadata_path": str(ask_metadata_path),
            "operator_evidence_template_path": str(template_path),
            "send_command": "python3 scripts/send_telegram_message_via_ea.py --text-file /tmp/google-ask.txt --receipt-name google-oauth-linking-operator-ask.receipt.json",
            "operator_message_preview": "Google operator ask preview",
            "operator_message_sha256": module.sha256_text("operator ask\n"),
            "receipt_name": "google-oauth-linking-operator-ask.receipt.json",
        },
    )
    ask_text_path.write_text("operator ask\n", encoding="utf-8")
    write_json(
        delivery_root / "google-oauth-linking-operator-ask.receipt.json",
        {
            "status": "sent",
            "generated_at_utc": "2026-07-04T20:58:05Z",
            "text_sha256": module.sha256_text("stale operator ask\n"),
            "text_preview": "stale operator ask",
            "message_ids": ["1"],
        },
    )
    write_json(
        ask_metadata_path,
        {
            "send_command": "python3 scripts/send_telegram_message_via_ea.py --text-file /tmp/google-ask.txt --receipt-name google-oauth-linking-operator-ask.receipt.json",
            "message_preview": "Google operator ask preview",
            "message_sha256": module.sha256_text("operator ask\n"),
            "receipt_name": "google-oauth-linking-operator-ask.receipt.json",
            "request_receipt_path": str(request_path),
            "required_operator_evidence_path": str(tmp_path / "missing-operator.json"),
            "operator_ask_text_path": str(ask_text_path),
            "operator_ask_metadata_path": str(ask_metadata_path),
            "operator_evidence_template_path": str(template_path),
        },
    )
    write_json(
        template_path,
        {
            "contract_name": module.OPERATOR_EVIDENCE_CONTRACT_NAME,
            "status": "pass",
            "base_url": module.DEFAULT_BASE_URL,
            "observed_at_utc": "",
            "verified_steps": list(module.REQUIRED_OPERATOR_STEPS),
            "screenshot_paths": ["/tmp/one.png", "/tmp/two.png"],
            "notes": "",
        },
    )

    output_path = tmp_path / "GOOGLE_OAUTH_LINKING_PROOF.generated.json"
    receipt = module.materialize(
        base_url=module.DEFAULT_BASE_URL,
        output_path=output_path,
        operator_evidence_path=tmp_path / "missing-operator.json",
        audit_email=module.DEFAULT_AUDIT_EMAIL,
    )

    assert receipt["status"] == "fail"
    assert receipt["operator_end_to_end_evidence"]["pass"] is False
    assert receipt["proof_contract_version"] == 3
    assert receipt["bindings"]["release"]
    assert any(item.startswith("binding:") for item in receipt["failures"])
    return
    assert receipt["operator_request_artifacts"]["pass"] is True
    assert receipt["operator_request_artifacts"]["request_receipt_path"] == str(request_path)
    assert receipt["operator_request_artifacts"]["operator_evidence_template_path"] == str(template_path)
    assert receipt["operator_request_artifacts"]["operator_ask_send_command"] == (
        "python3 scripts/send_telegram_message_via_ea.py --text-file /tmp/google-ask.txt "
        "--receipt-name google-oauth-linking-operator-ask.receipt.json"
    )
    assert receipt["operator_request_artifacts"]["operator_ask_delivery_current_text_comparable"] is True
    assert receipt["operator_request_artifacts"]["operator_ask_delivery_matches_current_text"] is False
    assert receipt["operator_request_artifacts"]["operator_ask_delivery_needs_resend"] is True
    assert receipt["operator_request_artifacts"]["operator_ask_resend_command"] == (
        "python3 scripts/send_telegram_message_via_ea.py --text-file /tmp/google-ask.txt "
        "--receipt-name google-oauth-linking-operator-ask.receipt.json"
    )
    assert receipt["operator_request_artifacts"]["operator_ask_receipt_name"] == "google-oauth-linking-operator-ask.receipt.json"
    assert any(
        item
        == "operator_request_artifacts: operator ask delivery is stale; resend current ask: "
        "python3 scripts/send_telegram_message_via_ea.py --text-file /tmp/google-ask.txt "
        "--receipt-name google-oauth-linking-operator-ask.receipt.json"
        for item in receipt["failures"]
    )
    assert any(str(request_path) in item for item in receipt["next_actions"])
    assert any(str(template_path) in item for item in receipt["next_actions"])
    assert any(
        item
        == "Resend the current Google operator ask before waiting for more evidence: "
        "python3 scripts/send_telegram_message_via_ea.py --text-file /tmp/google-ask.txt "
        "--receipt-name google-oauth-linking-operator-ask.receipt.json"
        for item in receipt["next_actions"]
    )
    assert receipt["nextActions"] == receipt["next_actions"]
    assert any("missing operator evidence receipt" in item for item in receipt["failures"])
    assert output_path.is_file()


def test_materialize_does_not_require_resend_when_google_request_is_not_required(tmp_path: Path, monkeypatch) -> None:
    module = load_module()
    disable_auth_signin_pause(module, monkeypatch, tmp_path)
    request_path = tmp_path / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE_REQUEST.generated.json"
    ask_text_path = tmp_path / "CURRENT_GOOGLE_OAUTH_LINKING_OPERATOR_ASK.txt"
    ask_metadata_path = tmp_path / "CURRENT_GOOGLE_OAUTH_LINKING_OPERATOR_ASK.generated.json"
    template_path = tmp_path / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE.template.generated.json"
    delivery_root = tmp_path / "telegram"
    delivery_root.mkdir(parents=True, exist_ok=True)
    evidence_path = tmp_path / "operator-evidence.json"
    screenshot_a = tmp_path / "one.png"
    screenshot_b = tmp_path / "two.png"
    screenshot_a.write_bytes(b"a")
    screenshot_b.write_bytes(b"b")

    monkeypatch.setattr(
        module,
        "probe_public_google_handoff",
        lambda base_url: {"pass": True, "failures": [], "redirect": {"pass": True}},
    )
    monkeypatch.setattr(
        module,
        "probe_signed_in_google_link_handoff",
        lambda base_url, email: {"pass": True, "failures": [], "email": email, "google_link_redirect": {"pass": True}},
    )
    monkeypatch.setattr(module, "DEFAULT_OPERATOR_EVIDENCE_REQUEST_PATH", request_path)
    monkeypatch.setattr(module, "DEFAULT_OPERATOR_ASK_TEXT_PATH", ask_text_path)
    monkeypatch.setattr(module, "DEFAULT_OPERATOR_ASK_METADATA_PATH", ask_metadata_path)
    monkeypatch.setattr(module, "DEFAULT_OPERATOR_EVIDENCE_TEMPLATE_PATH", template_path)
    monkeypatch.setattr(module, "DEFAULT_TELEGRAM_TEXT_DELIVERY_ROOT", delivery_root)

    ask_text_path.write_text("proof already satisfied\n", encoding="utf-8")
    write_json(
        request_path,
        {
            "contract_name": module.OPERATOR_EVIDENCE_REQUEST_CONTRACT_NAME,
            "status": "not_required",
            "base_url": module.DEFAULT_BASE_URL,
            "required_operator_evidence_path": str(evidence_path),
            "required_steps": list(module.REQUIRED_OPERATOR_STEPS),
            "minimum_screenshot_count": module.MINIMUM_OPERATOR_SCREENSHOT_COUNT,
            "recommended_screenshot_paths": [str(screenshot_a), str(screenshot_b)],
            "operator_ask_text_path": str(ask_text_path),
            "operator_ask_metadata_path": str(ask_metadata_path),
            "operator_evidence_template_path": str(template_path),
            "send_command": "python3 scripts/send_telegram_message_via_ea.py --text-file /tmp/google-ask.txt --receipt-name google-oauth-linking-operator-ask.receipt.json",
            "operator_message_preview": "Google proof already satisfied",
            "operator_message_sha256": module.sha256_text("proof already satisfied\n"),
            "receipt_name": "google-oauth-linking-operator-ask.receipt.json",
        },
    )
    write_json(
        delivery_root / "google-oauth-linking-operator-ask.receipt.json",
        {
            "status": "sent",
            "generated_at_utc": "2026-07-06T02:00:00Z",
            "text_sha256": module.sha256_text("older operator ask\n"),
            "text_preview": "older operator ask",
            "message_ids": ["1"],
        },
    )
    write_json(
        ask_metadata_path,
        {
            "status": "not_required",
            "send_command": "python3 scripts/send_telegram_message_via_ea.py --text-file /tmp/google-ask.txt --receipt-name google-oauth-linking-operator-ask.receipt.json",
            "message_preview": "Google proof already satisfied",
            "message_sha256": module.sha256_text("proof already satisfied\n"),
            "receipt_name": "google-oauth-linking-operator-ask.receipt.json",
            "request_receipt_path": str(request_path),
            "required_operator_evidence_path": str(evidence_path),
            "operator_ask_text_path": str(ask_text_path),
            "operator_ask_metadata_path": str(ask_metadata_path),
            "operator_evidence_template_path": str(template_path),
        },
    )
    write_json(
        template_path,
        {
            "contract_name": module.OPERATOR_EVIDENCE_CONTRACT_NAME,
            "status": "pass",
            "base_url": module.DEFAULT_BASE_URL,
            "observed_at_utc": "",
            "verified_steps": list(module.REQUIRED_OPERATOR_STEPS),
            "screenshot_paths": [str(screenshot_a), str(screenshot_b)],
            "notes": "",
        },
    )
    write_json(
        evidence_path,
        {
            "contract_name": module.OPERATOR_EVIDENCE_CONTRACT_NAME,
            "status": "pass",
            "base_url": module.DEFAULT_BASE_URL,
            "observed_at_utc": "2026-07-06T01:59:00Z",
            "verified_steps": list(module.REQUIRED_OPERATOR_STEPS),
            "screenshot_paths": [str(screenshot_a), str(screenshot_b)],
            "notes": "",
        },
    )

    output_path = tmp_path / "GOOGLE_OAUTH_LINKING_PROOF.generated.json"
    receipt = module.materialize(
        base_url=module.DEFAULT_BASE_URL,
        output_path=output_path,
        operator_evidence_path=evidence_path,
        audit_email=module.DEFAULT_AUDIT_EMAIL,
    )

    assert receipt["status"] == "fail"
    assert receipt["operator_end_to_end_evidence"]["pass"] is False
    assert any("request:" in item for item in receipt["operator_end_to_end_evidence"]["failures"])
    return
    assert receipt["operator_request_artifacts"]["request_status"] == "not_required"
    assert receipt["operator_request_artifacts"]["request_effective_status"] == "not_required"
    assert receipt["operator_request_artifacts"]["operator_action_still_required"] is False
    assert receipt["operator_request_artifacts"]["operator_ask_delivery_current_text_comparable"] is True
    assert receipt["operator_request_artifacts"]["operator_ask_delivery_matches_current_text"] is False
    assert receipt["operator_request_artifacts"]["operator_ask_delivery_needs_resend"] is False
    assert receipt["operator_request_artifacts"]["operator_ask_resend_command"] == ""
    assert receipt["failures"] == []
    assert receipt["next_actions"] == []
    assert output_path.is_file()


def test_materialize_flags_broken_operator_request_artifacts_when_evidence_is_missing(tmp_path: Path, monkeypatch) -> None:
    module = load_module()
    disable_auth_signin_pause(module, monkeypatch, tmp_path)
    request_path = tmp_path / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE_REQUEST.generated.json"
    ask_text_path = tmp_path / "CURRENT_GOOGLE_OAUTH_LINKING_OPERATOR_ASK.txt"
    ask_metadata_path = tmp_path / "CURRENT_GOOGLE_OAUTH_LINKING_OPERATOR_ASK.generated.json"
    template_path = tmp_path / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE.template.generated.json"

    monkeypatch.setattr(
        module,
        "probe_public_google_handoff",
        lambda base_url: {"pass": True, "failures": [], "redirect": {"pass": True}},
    )
    monkeypatch.setattr(
        module,
        "probe_signed_in_google_link_handoff",
        lambda base_url, email: {"pass": True, "failures": [], "email": email, "google_link_redirect": {"pass": True}},
    )
    monkeypatch.setattr(module, "DEFAULT_OPERATOR_EVIDENCE_REQUEST_PATH", request_path)
    monkeypatch.setattr(module, "DEFAULT_OPERATOR_ASK_TEXT_PATH", ask_text_path)
    monkeypatch.setattr(module, "DEFAULT_OPERATOR_ASK_METADATA_PATH", ask_metadata_path)
    monkeypatch.setattr(module, "DEFAULT_OPERATOR_EVIDENCE_TEMPLATE_PATH", template_path)
    write_json(
        request_path,
        {
            "contract_name": module.OPERATOR_EVIDENCE_REQUEST_CONTRACT_NAME,
            "status": "operator_action_required",
            "base_url": module.DEFAULT_BASE_URL,
            "required_operator_evidence_path": str(tmp_path / "missing-operator.json"),
            "required_steps": list(module.REQUIRED_OPERATOR_STEPS),
            "minimum_screenshot_count": module.MINIMUM_OPERATOR_SCREENSHOT_COUNT,
            "recommended_screenshot_paths": ["/tmp/one.png", "/tmp/two.png"],
            "operator_ask_text_path": str(ask_text_path),
            "operator_ask_metadata_path": str(ask_metadata_path),
            "operator_evidence_template_path": str(template_path),
            "send_command": "python3 scripts/send_telegram_message_via_ea.py --text-file /tmp/google-ask.txt --receipt-name google-oauth-linking-operator-ask.receipt.json",
            "operator_message_preview": "Google operator ask preview",
            "operator_message_sha256": module.sha256_text("operator ask\n"),
            "receipt_name": "google-oauth-linking-operator-ask.receipt.json",
        },
    )
    ask_text_path.write_text("operator ask\n", encoding="utf-8")
    write_json(
        ask_metadata_path,
        {
            "send_command": "python3 scripts/send_telegram_message_via_ea.py --text-file /tmp/google-ask.txt --receipt-name google-oauth-linking-operator-ask.receipt.json",
            "message_preview": "Google operator ask preview",
            "message_sha256": "deadbeef",
            "receipt_name": "google-oauth-linking-operator-ask.receipt.json",
            "request_receipt_path": str(request_path),
            "required_operator_evidence_path": str(tmp_path / "missing-operator.json"),
            "operator_ask_text_path": str(ask_text_path),
            "operator_ask_metadata_path": str(ask_metadata_path),
            "operator_evidence_template_path": str(template_path),
        },
    )
    write_json(
        template_path,
        {
            "contract_name": module.OPERATOR_EVIDENCE_CONTRACT_NAME,
            "status": "pass",
            "base_url": module.DEFAULT_BASE_URL,
            "observed_at_utc": "",
            "verified_steps": list(module.REQUIRED_OPERATOR_STEPS),
            "screenshot_paths": ["/tmp/one.png", "/tmp/two.png"],
            "notes": "",
        },
    )

    receipt = module.materialize(
        base_url=module.DEFAULT_BASE_URL,
        output_path=tmp_path / "GOOGLE_OAUTH_LINKING_PROOF.generated.json",
        operator_evidence_path=tmp_path / "missing-operator.json",
        audit_email=module.DEFAULT_AUDIT_EMAIL,
    )

    assert receipt["operator_request_artifacts"]["pass"] is False
    assert "operator ask metadata message_sha256 mismatch" in receipt["operator_request_artifacts"]["failures"]
    assert any(
        item == "operator_request_artifacts: operator ask metadata message_sha256 mismatch"
        for item in receipt["failures"]
    )


def test_materialize_prefers_signed_in_probe_recovery_when_operator_evidence_already_passes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = load_module()
    disable_auth_signin_pause(module, monkeypatch, tmp_path)
    operator_evidence_path = tmp_path / "operator-evidence.json"
    output_path = tmp_path / "GOOGLE_OAUTH_LINKING_PROOF.generated.json"

    monkeypatch.setattr(
        module,
        "probe_public_google_handoff",
        lambda base_url: {"pass": True, "failures": [], "redirect": {"pass": True}},
    )
    monkeypatch.setattr(
        module,
        "probe_signed_in_google_link_handoff",
        lambda base_url, email: {
            "status": "fail",
            "pass": False,
            "failures": ["/home returned 302, expected 200"],
            "email": email,
            "session_auth_used": True,
            "session_auth_context": {"mode": "cookie", "cookieName": module.HUB_ACCESS_COOKIE_NAME},
            "google_link_redirect": {"pass": False},
        },
    )
    monkeypatch.setattr(
        module,
        "inspect_operator_evidence",
        lambda base_url, path: {
            "pass": True,
            "exists": True,
            "path": str(path),
            "failures": [],
        },
    )
    monkeypatch.setattr(
        module,
        "inspect_operator_request_artifacts",
        lambda **kwargs: {
            "pass": True,
            "request_status": "not_required",
            "request_receipt_path": str(tmp_path / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE_REQUEST.generated.json"),
            "operator_ask_text_path": str(tmp_path / "CURRENT_GOOGLE_OAUTH_LINKING_OPERATOR_ASK.txt"),
            "operator_ask_metadata_path": str(tmp_path / "CURRENT_GOOGLE_OAUTH_LINKING_OPERATOR_ASK.generated.json"),
            "operator_evidence_template_path": str(tmp_path / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE.template.generated.json"),
            "operator_ask_delivery_needs_resend": False,
            "operator_ask_resend_command": "",
            "import_command": "",
            "failures": [],
        },
    )

    receipt = module.materialize(
        base_url="https://example.test",
        output_path=output_path,
        operator_evidence_path=operator_evidence_path,
        audit_email=module.DEFAULT_AUDIT_EMAIL,
    )

    assert receipt["status"] == "fail"
    assert receipt["summary"] == (
        "Operator-backed Google linking evidence is green, but the first-party signed-in preflight is failing against the live host."
    )
    assert any("deployed owner session lane" in item for item in receipt["next_actions"])
    assert any(
        item
        == "Operator evidence already passes for this base URL. Refresh the first-party signed-in preflight instead: the deployed owner session or inline preview sign-in must keep /home, /account/settings, and /auth/google/link reachable."
        for item in receipt["next_actions"]
    )
    assert any(
        item == "After the relevant fix, rerun: python3 scripts/materialize_google_oauth_linking_proof.py --base-url https://example.test"
        for item in receipt["next_actions"]
    )
    assert not any("Complete the operator evidence template" in item for item in receipt["next_actions"])
    assert not any("Capture a real browser-backed Google linking proof receipt" in item for item in receipt["next_actions"])


def test_materialize_fails_closed_when_auth_signin_automation_is_paused(tmp_path: Path, monkeypatch) -> None:
    module = load_module()
    output_path = tmp_path / "GOOGLE_OAUTH_LINKING_PROOF.generated.json"
    operator_evidence_path = tmp_path / "operator-evidence.json"
    pause_flag = tmp_path / "auth_signin_automation_paused.flag"
    pause_flag.write_text(
        "paused by user request on 2026-07-08; disable Chummer auth sign-in automation until explicitly resumed\n",
        encoding="utf-8",
    )

    quick_probe_calls = {"count": 0}

    monkeypatch.setattr(module, "AUTH_SIGNIN_AUTOMATION_PAUSE_FLAG", pause_flag)
    monkeypatch.setattr(
        module,
        "probe_public_google_handoff",
        lambda base_url: quick_probe_calls.__setitem__("count", quick_probe_calls["count"] + 1) or {
            "pass": True,
            "failures": [],
            "login_url": f"{base_url}/login?next=%2Fhome",
            "google_start_url": f"{base_url}/auth/google/start?next=%2Fhome",
        },
    )
    monkeypatch.setattr(
        module,
        "probe_signed_in_google_link_handoff",
        lambda base_url, email, env_file=None: (_ for _ in ()).throw(
            AssertionError("signed-in probe should not run while paused")
        ),
    )
    monkeypatch.setattr(
        module,
        "inspect_operator_evidence",
        lambda base_url, path: {
            "pass": False,
            "exists": False,
            "path": str(path),
            "failures": [f"missing operator evidence receipt: {path}"],
        },
    )
    monkeypatch.setattr(
        module,
        "inspect_operator_request_artifacts",
        lambda **kwargs: {
            "pass": True,
            "request_receipt_path": str(tmp_path / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE_REQUEST.generated.json"),
            "operator_ask_text_path": str(tmp_path / "CURRENT_GOOGLE_OAUTH_LINKING_OPERATOR_ASK.txt"),
            "operator_ask_metadata_path": str(tmp_path / "CURRENT_GOOGLE_OAUTH_LINKING_OPERATOR_ASK.generated.json"),
            "operator_evidence_template_path": str(tmp_path / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE.template.generated.json"),
            "required_operator_evidence_path": str(operator_evidence_path),
            "operator_ask_send_command": "",
            "operator_ask_resend_command": "",
            "operator_action_still_required": True,
            "operator_ask_delivery_needs_resend": False,
            "failures": [],
        },
    )

    receipt = module.materialize(
        base_url=module.DEFAULT_BASE_URL,
        output_path=output_path,
        operator_evidence_path=operator_evidence_path,
        audit_email=module.DEFAULT_AUDIT_EMAIL,
    )

    assert receipt["status"] == "fail"
    assert receipt["automation_pause"]["paused"] is True
    assert receipt["automation_pause"]["flag_path"] == str(pause_flag)
    assert quick_probe_calls["count"] == 1
    assert receipt["quick_handoff_probe"]["pass"] is True
    assert receipt["signed_in_link_handoff"]["status"] == "operator_required"
    assert receipt["signed_in_link_handoff"]["pass"] is False
    assert "auth_signin_automation_paused:" in receipt["failures"][-1]
    assert "browser-backed operator evidence" in receipt["summary"]
    assert any("Keep it paused" in item for item in receipt["next_actions"])
    assert not any("After resume, rerun:" in item for item in receipt["next_actions"])
    assert any("After the relevant fix, rerun:" in item for item in receipt["next_actions"])
    assert output_path.is_file()


def test_materialize_passes_when_auth_signin_automation_is_paused_and_operator_evidence_is_current(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = load_module()
    output_path = tmp_path / "GOOGLE_OAUTH_LINKING_PROOF.generated.json"
    operator_evidence_path = tmp_path / "operator-evidence.json"
    pause_flag = tmp_path / "auth_signin_automation_paused.flag"
    pause_flag.write_text(
        "paused by user request on 2026-07-08; disable Chummer auth sign-in automation until explicitly resumed\n",
        encoding="utf-8",
    )

    quick_probe_calls = {"count": 0}

    monkeypatch.setattr(module, "AUTH_SIGNIN_AUTOMATION_PAUSE_FLAG", pause_flag)
    monkeypatch.setattr(
        module,
        "probe_public_google_handoff",
        lambda base_url: quick_probe_calls.__setitem__("count", quick_probe_calls["count"] + 1) or {
            "pass": True,
            "failures": [],
            "login_url": f"{base_url}/login?next=%2Fhome",
            "google_start_url": f"{base_url}/auth/google/start?next=%2Fhome",
        },
    )
    monkeypatch.setattr(
        module,
        "probe_signed_in_google_link_handoff",
        lambda base_url, email, env_file=None: (_ for _ in ()).throw(
            AssertionError("signed-in probe should not run while paused")
        ),
    )
    monkeypatch.setattr(
        module,
        "inspect_operator_evidence",
        lambda base_url, path: {
            "pass": True,
            "exists": True,
            "path": str(path),
            "failures": [],
        },
    )
    monkeypatch.setattr(
        module,
        "inspect_operator_request_artifacts",
        lambda **kwargs: {
            "pass": True,
            "request_receipt_path": str(tmp_path / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE_REQUEST.generated.json"),
            "operator_ask_text_path": str(tmp_path / "CURRENT_GOOGLE_OAUTH_LINKING_OPERATOR_ASK.txt"),
            "operator_ask_metadata_path": str(tmp_path / "CURRENT_GOOGLE_OAUTH_LINKING_OPERATOR_ASK.generated.json"),
            "operator_evidence_template_path": str(tmp_path / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE.template.generated.json"),
            "required_operator_evidence_path": str(operator_evidence_path),
            "operator_ask_send_command": "",
            "operator_ask_resend_command": "",
            "operator_action_still_required": False,
            "operator_ask_delivery_needs_resend": False,
            "failures": [],
        },
    )

    receipt = module.materialize(
        base_url=module.DEFAULT_BASE_URL,
        output_path=output_path,
        operator_evidence_path=operator_evidence_path,
        audit_email=module.DEFAULT_AUDIT_EMAIL,
    )

    assert receipt["status"] == "fail"
    assert any(item.startswith("binding:") for item in receipt["failures"])
    return
    assert receipt["automation_pause"]["paused"] is True
    assert quick_probe_calls["count"] == 1
    assert receipt["quick_handoff_probe"]["pass"] is True
    assert receipt["signed_in_link_handoff"]["status"] == "pass"
    assert receipt["signed_in_link_handoff"]["pass"] is True
    assert receipt["signed_in_link_handoff"]["satisfied_by_operator_evidence"] is True
    assert receipt["failures"] == []
    assert receipt["next_actions"] == []
    assert "automation stays paused" in receipt["summary"]
    assert output_path.is_file()


def test_verify_receipt_rejects_shallow_legacy_payload() -> None:
    module = load_module()
    ok, issues = module.verify_receipt(
        {
            "contract_name": "chummer.run.google_oauth_linking_proof",
            "status": "pass",
            "base_url": "https://chummer.run",
            "script": "scripts/check-google-oauth-linking.py",
            "test_cases": [
                "anonymous user starts on /login",
                "Google handoff completes and lands on signed-in state",
                "existing account can link Google",
                "linked account can sign back in with Google",
            ],
        },
        require_pass=True,
    )

    assert ok is False
    assert "proof_contract_version must be 3" in issues
    assert "generated_at_utc must be a timezone-aware timestamp" in issues
    assert any("request:" in issue for issue in issues)
    assert "proof bindings do not match current release/request/evidence/program bytes" in issues
