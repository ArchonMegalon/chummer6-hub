from __future__ import annotations

from dataclasses import asdict
from email.message import Message
import importlib.util
import io
import json
from pathlib import Path
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "probe_android_app_links_postdeploy.py"
ASSET_LINKS_PATH = (
    REPO_ROOT / "Chummer.Run.Api" / "wwwroot" / ".well-known" / "assetlinks.json"
)


def load_module():
    spec = importlib.util.spec_from_file_location(
        "probe_android_app_links_postdeploy",
        SCRIPT_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FakeResponse:
    def __init__(
        self,
        body: bytes,
        *,
        status: int = 200,
        content_type: str = "application/json",
        final_url: str,
    ) -> None:
        self._body = io.BytesIO(body)
        self._status = status
        self._final_url = final_url
        self.headers = Message()
        self.headers["Content-Type"] = content_type

    def __enter__(self):
        return self

    def __exit__(self, exception_type, exception, traceback) -> None:
        return None

    def getcode(self) -> int:
        return self._status

    def geturl(self) -> str:
        return self._final_url

    def read(self, size: int = -1) -> bytes:
        return self._body.read(size)


def success_response(module, body: bytes | None = None) -> FakeResponse:
    return FakeResponse(
        ASSET_LINKS_PATH.read_bytes() if body is None else body,
        final_url=module.ASSET_LINKS_URL,
    )


def test_probe_uses_only_the_exact_https_url_and_reports_bounded_authority() -> None:
    module = load_module()
    requests: list[tuple[Request, int]] = []

    def open_url(request: Request, timeout: int) -> FakeResponse:
        requests.append((request, timeout))
        return success_response(module)

    result = module.probe_android_app_links(open_url=open_url)

    assert len(requests) == 1
    request, timeout = requests[0]
    assert request.full_url == "https://chummer.run/.well-known/assetlinks.json"
    assert request.get_method() == "GET"
    assert timeout == 20
    assert request.get_header("Accept") == "application/json"
    assert request.get_header("Accept-encoding") == "identity"
    assert asdict(result) == {
        "contract_name": "chummer.android.digital_asset_links_postdeploy/v1",
        "status": "pass",
        "url": "https://chummer.run/.well-known/assetlinks.json",
        "final_url": "https://chummer.run/.well-known/assetlinks.json",
        "http_status": 200,
        "content_type": "application/json",
        "payload_sha256": module.hashlib.sha256(ASSET_LINKS_PATH.read_bytes()).hexdigest(),
        "association_file_matches": True,
        "device_verification_evaluated": False,
    }


def test_redirect_handler_and_changed_final_url_fail_closed() -> None:
    module = load_module()
    handler = module.NoRedirectHandler()
    assert handler.redirect_request(None, None, 302, "Found", {}, "https://evil.test") is None

    def redirected(_request: Request, _timeout: int) -> FakeResponse:
        return FakeResponse(
            ASSET_LINKS_PATH.read_bytes(),
            final_url="https://www.chummer.run/.well-known/assetlinks.json",
        )

    with pytest.raises(module.AppLinksProbeFailure, match="redirect_forbidden"):
        module.probe_android_app_links(open_url=redirected)


def test_http_redirect_is_rejected_without_following() -> None:
    module = load_module()

    def redirect(request: Request, _timeout: int):
        raise HTTPError(
            request.full_url,
            302,
            "Found",
            {"Location": "https://evil.test/assetlinks.json"},
            io.BytesIO(b""),
        )

    with pytest.raises(module.AppLinksProbeFailure, match="redirect_forbidden"):
        module.probe_android_app_links(open_url=redirect)

    with pytest.raises(module.AppLinksProbeFailure, match="redirect_forbidden"):
        module.probe_android_app_links(
            open_url=lambda _request, _timeout: FakeResponse(
                b"",
                status=302,
                final_url=module.ASSET_LINKS_URL,
            )
        )


def test_cloudflare_1033_is_explicitly_unreachable() -> None:
    module = load_module()

    def unavailable(request: Request, _timeout: int):
        raise HTTPError(
            request.full_url,
            530,
            "Origin DNS Error",
            {"Content-Type": "text/plain", "Server": "cloudflare"},
            io.BytesIO(b"error code: 1033\n"),
        )

    with pytest.raises(
        module.AppLinksProbeFailure,
        match="cloudflare_1033_origin_unreachable",
    ):
        module.probe_android_app_links(open_url=unavailable)


def test_network_failure_is_explicitly_unreachable() -> None:
    module = load_module()

    def unreachable(_request: Request, _timeout: int):
        raise URLError("network down")

    with pytest.raises(module.AppLinksProbeFailure, match="public_origin_unreachable"):
        module.probe_android_app_links(open_url=unreachable)


def test_non_200_and_non_json_responses_fail_closed() -> None:
    module = load_module()

    with pytest.raises(module.AppLinksProbeFailure, match="unexpected_http_status_503"):
        module.probe_android_app_links(
            open_url=lambda _request, _timeout: FakeResponse(
                ASSET_LINKS_PATH.read_bytes(),
                status=503,
                final_url=module.ASSET_LINKS_URL,
            )
        )

    with pytest.raises(
        module.AppLinksProbeFailure,
        match="content_type_not_application_json",
    ):
        module.probe_android_app_links(
            open_url=lambda _request, _timeout: FakeResponse(
                ASSET_LINKS_PATH.read_bytes(),
                content_type="text/plain; charset=utf-8",
                final_url=module.ASSET_LINKS_URL,
            )
        )


def test_semantic_and_byte_drift_fail_independently() -> None:
    module = load_module()
    tracked = json.loads(ASSET_LINKS_PATH.read_bytes())
    tracked[0]["target"]["package_name"] = "com.example.wrong"
    semantic_drift = (json.dumps(tracked, indent=2) + "\n").encode("utf-8")

    with pytest.raises(module.AppLinksProbeFailure, match="assetlinks_semantic_mismatch"):
        module.probe_android_app_links(
            open_url=lambda _request, _timeout: success_response(module, semantic_drift)
        )

    same_semantics_different_bytes = json.dumps(
        json.loads(ASSET_LINKS_PATH.read_bytes()),
        separators=(",", ":"),
    ).encode("utf-8")
    with pytest.raises(module.AppLinksProbeFailure, match="assetlinks_byte_mismatch"):
        module.probe_android_app_links(
            open_url=lambda _request, _timeout: success_response(
                module,
                same_semantics_different_bytes,
            )
        )


def test_duplicate_keys_and_oversized_payloads_fail_closed() -> None:
    module = load_module()
    duplicate_key = b'[{"relation":[],"relation":[],"target":{}}]'
    with pytest.raises(module.AppLinksProbeFailure, match="live_assetlinks_invalid_json"):
        module.probe_android_app_links(
            open_url=lambda _request, _timeout: success_response(module, duplicate_key)
        )

    oversized = b" " * (module.MAXIMUM_RESPONSE_BYTES + 1)
    with pytest.raises(module.AppLinksProbeFailure, match="live_assetlinks_too_large"):
        module.probe_android_app_links(
            open_url=lambda _request, _timeout: success_response(module, oversized)
        )


def test_cli_rejects_url_overrides_without_network_access(capsys) -> None:
    module = load_module()
    called = False

    def forbidden_probe():
        nonlocal called
        called = True

    module.probe_android_app_links = forbidden_probe
    assert module.main(["--url", "https://evil.test/assetlinks.json"]) == 2
    assert called is False
    assert "usage: probe_android_app_links_postdeploy.py" in capsys.readouterr().err
