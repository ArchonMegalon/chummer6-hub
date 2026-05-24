from __future__ import annotations

import importlib.util
import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "verify_mobile_pwa_public_projection.py"


class _FakeResponse:
    def __init__(
        self,
        url: str,
        *,
        status_code: int = 200,
        text: str = "",
        json_data: object | None = None,
    ) -> None:
        self.url = url
        self.status_code = status_code
        self.text = text
        self._json_data = json_data

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"unexpected status {self.status_code}")

    def json(self) -> object:
        return self._json_data


class _FakeSession:
    def get(self, url: str, timeout: int = 30, allow_redirects: bool = True) -> _FakeResponse:
        del timeout, allow_redirects
        if url.endswith("/mobile"):
            return _FakeResponse(
                url,
                text=(
                    '<link rel="manifest" href="/manifest.json">'
                    '<script>serviceWorker.register("/service-worker.js")</script>'
                    "Install this app /play/continuity"
                ),
            )
        if url.endswith("/pwa"):
            return _FakeResponse(f"{url[:-4]}/mobile")
        if url.endswith("/play"):
            return _FakeResponse(url)
        if url.endswith("/player"):
            return _FakeResponse(f"{url[:-7]}/play?role=player")
        if url.endswith("/gm"):
            return _FakeResponse(f"{url[:-3]}/play?role=gm")
        if url.endswith("/observer"):
            return _FakeResponse(f"{url[:-9]}/play?role=observer")
        if url.endswith("/session"):
            return _FakeResponse(f"{url[:-8]}/play")
        if url.endswith("/play/continuity"):
            return _FakeResponse(url, text="continuity")
        if url.endswith("/mobile/pwa.json"):
            return _FakeResponse(
                url,
                json_data={
                    "install_route": "/downloads",
                    "continuity_route": "/play/continuity",
                    "receipt_index_route": "/play/continuity/receipts",
                },
            )
        if url.endswith("/play/continuity/receipts"):
            return _FakeResponse(
                url,
                json_data={
                    "boundary": "first-party only",
                    "receipts": [{"id": "one"}, {"id": "two"}, {"id": "three"}],
                },
            )
        if url.endswith("/manifest.json"):
            return _FakeResponse(
                url,
                json_data={
                    "id": "/mobile",
                    "start_url": "/mobile",
                    "display": "standalone",
                    "display_override": ["window-controls-overlay"],
                    "shortcuts": [
                        {"url": "/mobile"},
                        {"url": "/play"},
                        {"url": "/play/continuity"},
                    ],
                    "screenshots": [{"src": "/one.png"}, {"src": "/two.png"}],
                    "icons": [{"src": "/icon.png"}],
                },
            )
        if url.endswith("/service-worker.js"):
            return _FakeResponse(
                url,
                text=(
                    'self.addEventListener("fetch", () => {});\n'
                    'self.addEventListener("push", () => {});\n'
                    'self.addEventListener("notificationclick", () => {});\n'
                    'self.addEventListener("notificationclose", () => {});\n'
                    "navigationPreload\n"
                    "RUNTIME_CACHE\n"
                    "/mobile\n/play\n/play/continuity\n/mobile/pwa.json\n/ready/handoff/mobile.json\n"
                ),
            )
        raise AssertionError(f"unexpected url {url}")


def _load_module():
    scripts_dir = str(SCRIPT_PATH.parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    spec = importlib.util.spec_from_file_location("verify_mobile_pwa_public_projection", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load verifier module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MobilePwaPublicProjectionTests(unittest.TestCase):
    def test_verifier_prints_explicit_ok_line_on_pass(self) -> None:
        module = _load_module()
        stdout = io.StringIO()

        with (
            patch.object(module.requests, "Session", return_value=_FakeSession()),
            patch.object(module, "completion_path", side_effect=lambda name: Path("/tmp") / name),
            patch.object(module, "write_json"),
            patch.object(module, "write_text"),
            patch.object(module, "now_iso", return_value="2026-05-24T00:00:00Z"),
            redirect_stdout(stdout),
        ):
            result = module.run("http://example.test")

        self.assertEqual(result, 0)
        self.assertIn("mobile_pwa_public_projection:ok", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
