from __future__ import annotations

import json
import os
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from contextlib import contextmanager
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
EDGE_PROJECT = ROOT / "Chummer.Run.Api" / "Chummer.Run.Api.csproj"
EDGE_DLL = EDGE_PROJECT.parent / "bin" / "Debug" / "net10.0" / "Chummer.Run.Api.dll"
CANONICAL_HOST = "chummer.run"
CANONICAL_ORIGIN = "https://chummer.run"
LOCAL_IDENTITY_TOKEN = "canonical-host-policy-local-identity"
POSTGRES_CONNECTION_STRING_FILE_NAME = "install-linking-postgres.connection-string"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


NO_REDIRECT_OPENER = urllib.request.build_opener(_NoRedirect())


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as handle:
        handle.bind(("127.0.0.1", 0))
        return int(handle.getsockname()[1])


def _ensure_built() -> None:
    inputs = (
        EDGE_PROJECT,
        EDGE_PROJECT.parent / "Program.cs",
        EDGE_PROJECT.parent / "Services" / "PublicCanonicalOriginPolicy.cs",
        EDGE_PROJECT.parent / "Views" / "Shared" / "_Layout.cshtml",
    )
    if EDGE_DLL.is_file() and all(path.stat().st_mtime <= EDGE_DLL.stat().st_mtime for path in inputs):
        return

    result = subprocess.run(
        [
            "dotnet",
            "build",
            str(EDGE_PROJECT),
            "-f",
            "net10.0",
            "--no-restore",
            "-m:1",
            "-p:UseSharedCompilation=false",
            "-v:minimal",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        timeout=900,
    )
    assert result.returncode == 0, result.stdout + "\n" + result.stderr


def _headers_to_dict(headers) -> dict[str, str]:  # type: ignore[no-untyped-def]
    grouped: dict[str, list[str]] = {}
    for key, value in headers.items():
        grouped.setdefault(key.lower(), []).append(value)
    return {key: "\n".join(values) for key, values in grouped.items()}


def _request(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    follow_redirects: bool = True,
) -> tuple[int, dict[str, str], bytes]:
    request = urllib.request.Request(url, headers=headers or {}, method="GET")
    opener = urllib.request.urlopen if follow_redirects else NO_REDIRECT_OPENER.open
    try:
        with opener(request, timeout=15) as response:
            return int(response.status), _headers_to_dict(response.headers), response.read()
    except urllib.error.HTTPError as error:
        return int(error.code), _headers_to_dict(error.headers), error.read()


def _base_environment(port: int, state_root: Path) -> dict[str, str]:
    postgres_connection_string_path = state_root / POSTGRES_CONNECTION_STRING_FILE_NAME
    descriptor = os.open(
        postgres_connection_string_path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        os.write(
            descriptor,
            (
                "Host=127.0.0.1;Port=9;Database=chummer_host_policy_probe;"
                "Username=chummer_host_policy_probe;SSL Mode=VerifyFull\n"
            ).encode("utf-8"),
        )
        os.fsync(descriptor)
    finally:
        os.close(descriptor)

    environment = os.environ.copy()
    environment.update(
        {
            "ASPNETCORE_ENVIRONMENT": "Production",
            "DOTNET_ENVIRONMENT": "Production",
            "ASPNETCORE_URLS": f"http://127.0.0.1:{port}",
            "CHUMMER_ENABLE_HTTPS_REDIRECTION": "false",
            "AllowedHosts": CANONICAL_HOST,
            "CHUMMER_PUBLIC_ALLOWED_HOSTS": CANONICAL_HOST,
            "CHUMMER_PUBLIC_CANONICAL_ORIGIN": CANONICAL_ORIGIN,
            "CHUMMER_PUBLIC_PLAY_PROXY_ENABLED": "false",
            "CHUMMER_PUBLIC_PLAY_LIVE_SESSION_PROXY_ENABLED": "false",
            "CHUMMER_GOOGLE_OIDC_REQUIRED": "false",
            "GOOGLE_OIDC_CLIENT_ID": "canonical-host-test-client",
            "GOOGLE_OIDC_CLIENT_SECRET": "canonical-host-test-secret",
            "CHUMMER_LOCAL_E2E_ACCESS_TOKEN": LOCAL_IDENTITY_TOKEN,
            "CHUMMER_LOCAL_E2E_SUBJECT_ID": "subject.canonical-host-test",
            "CHUMMER_LOCAL_E2E_DISPLAY_NAME": "Canonical Host Test",
            "CHUMMER_LOCAL_E2E_EMAIL": "canonical-host@example.invalid",
            "CHUMMER_LOCAL_E2E_ROLES": "player,gm",
            "CHUMMER_PUBLIC_CONCIERGE_ENABLED": "true",
            "CHUMMER_PUBLIC_CONCIERGE_DOWNLOADS_ENABLED": "true",
            "CHUMMER_PUBLIC_CONCIERGE_DOWNLOADS_WIDGET_URL": "https://widgets.example.test/downloads",
            "CHUMMER_DATA_PROTECTION_KEYS_PATH": str(state_root / "keys"),
            "CHUMMER_INSTALL_LINKING_POSTGRES_CONNECTION_STRING_FILE": str(
                postgres_connection_string_path
            ),
            "CHUMMER_INSTALL_LINKING_STORE_PATH": str(
                state_root / "install-linking.json"
            ),
            "CHUMMER_COMMUNITY_STORE_PATH": str(state_root / "community.json"),
            "CHUMMER_PUBLIC_CONCIERGE_STORE_PATH": str(state_root / "concierge.json"),
            "TMPDIR": str(state_root),
        }
    )
    return environment


@contextmanager
def _edge_server(port: int, temporary_root: Path):
    environment = _base_environment(port, temporary_root)
    log_path = temporary_root / "edge.log"
    with log_path.open("wb") as log:
        process = subprocess.Popen(
            ["dotnet", str(EDGE_DLL)],
            cwd=EDGE_PROJECT.parent,
            env=environment,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
    try:
        yield process, log_path
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)


def _wait_ready(base_url: str, process: subprocess.Popen[bytes], log_path: Path) -> None:
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        if process.poll() is not None:
            break
        try:
            status, _, _ = _request(
                f"{base_url}/api/health",
                headers={"Host": CANONICAL_HOST},
            )
            if status == 200:
                return
        except OSError:
            pass
        time.sleep(0.2)

    log = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
    raise AssertionError(f"Edge did not become ready at {base_url}.\n{log}")


@pytest.mark.parametrize(
    ("allowed_hosts", "canonical_origin", "expected_log"),
    (
        ("", CANONICAL_ORIGIN, "allowlist must not be missing or empty"),
        ("*", CANONICAL_ORIGIN, "Wildcard public hosts are not allowed in Production"),
        ("bad/host", CANONICAL_ORIGIN, "contains invalid host"),
        (CANONICAL_HOST, "", "must configure one absolute public origin"),
        (CANONICAL_HOST, "http://chummer.run", "must use HTTPS in Production"),
        (CANONICAL_HOST, "https://alias.chummer.run", "must be present in the public host allowlist"),
    ),
)
def test_production_startup_rejects_unsafe_public_host_configuration(
    allowed_hosts: str,
    canonical_origin: str,
    expected_log: str,
) -> None:
    _ensure_built()
    port = _free_port()
    with tempfile.TemporaryDirectory(prefix="chummer-canonical-startup-") as temporary:
        temporary_root = Path(temporary)
        environment = _base_environment(port, temporary_root)
        environment["AllowedHosts"] = allowed_hosts
        environment["CHUMMER_PUBLIC_ALLOWED_HOSTS"] = allowed_hosts
        environment["CHUMMER_PUBLIC_CANONICAL_ORIGIN"] = canonical_origin
        result = subprocess.run(
            ["dotnet", str(EDGE_DLL)],
            cwd=EDGE_PROJECT.parent,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
            timeout=30,
        )

    combined = result.stdout + "\n" + result.stderr
    assert result.returncode != 0, combined
    assert expected_log in combined


def test_real_host_boundary_keeps_links_qr_redirects_cookies_and_csp_canonical() -> None:
    _ensure_built()
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"

    with tempfile.TemporaryDirectory(prefix="chummer-canonical-host-") as temporary:
        temporary_root = Path(temporary)
        with _edge_server(port, temporary_root) as (edge, log_path):
            _wait_ready(base_url, edge, log_path)

            canonical_headers = {"Host": CANONICAL_HOST}
            status, _, body = _request(f"{base_url}/", headers=canonical_headers)
            page = body.decode("utf-8", errors="replace")
            assert status == 200
            assert 'rel="canonical" href="https://chummer.run/"' in page
            assert 'property="og:url" content="https://chummer.run/"' in page
            assert "127.0.0.1" not in page

            authenticated_headers = {
                **canonical_headers,
                "Cookie": f"chummer_hub_access_token={LOCAL_IDENTITY_TOKEN}",
            }
            status, _, body = _request(f"{base_url}/", headers=authenticated_headers)
            authenticated_page = body.decode("utf-8", errors="replace")
            assert status == 200
            assert 'data-mobile-app-path="https://chummer.run/build"' in authenticated_page
            assert 'data-mobile-app-path="https://chummer.run/mobile/player"' in authenticated_page
            assert authenticated_page.count('data-mobile-app-origin="https://chummer.run"') == 2
            assert "127.0.0.1" not in authenticated_page

            status, redirect_headers, _ = _request(
                f"{base_url}/hub",
                headers=canonical_headers,
                follow_redirects=False,
            )
            assert status == 302
            assert redirect_headers.get("location") == "/account"

            status, cookie_headers, _ = _request(
                f"{base_url}/auth/google/start?next=%2Fbuild",
                headers={**canonical_headers, "X-Forwarded-Proto": "http"},
                follow_redirects=False,
            )
            assert status == 302
            google_location = cookie_headers.get("location", "")
            assert google_location.startswith("https://accounts.google.com/")
            google_query = urllib.parse.parse_qs(urllib.parse.urlparse(google_location).query)
            assert google_query["redirect_uri"] == ["https://chummer.run/auth/google/callback"]
            set_cookie = cookie_headers.get("set-cookie", "")
            assert "secure" in set_cookie.lower()
            assert "domain=" not in set_cookie.lower()
            assert "127.0.0.1" not in set_cookie

            status, csp_headers, _ = _request(
                f"{base_url}/downloads/concierge",
                headers=canonical_headers,
            )
            assert status == 200
            csp = csp_headers.get("content-security-policy", "")
            assert "frame-ancestors 'self'" in csp
            assert "widgets.example.test" in csp
            assert "127.0.0.1" not in csp

            for hostile_headers in (
                {"Host": "alias.chummer.run"},
                {"Host": CANONICAL_HOST, "X-Forwarded-Host": "attacker.invalid"},
                {"Host": CANONICAL_HOST, "Forwarded": "for=127.0.0.1;host=attacker.invalid;proto=https"},
            ):
                status, response_headers, hostile_body = _request(
                    f"{base_url}/hub",
                    headers=hostile_headers,
                    follow_redirects=False,
                )
                assert status == 400, (hostile_headers, status, hostile_body)
                assert "location" not in response_headers
                assert "set-cookie" not in response_headers
                assert "content-security-policy" not in response_headers
                assert "attacker.invalid" not in hostile_body.decode("utf-8", errors="replace")

            status, _, body = _request(
                f"{base_url}/",
                headers={"Host": CANONICAL_HOST, "X-Forwarded-Host": CANONICAL_HOST},
            )
            assert status == 200
            assert CANONICAL_ORIGIN.encode() in body
