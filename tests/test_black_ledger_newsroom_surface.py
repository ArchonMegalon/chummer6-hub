from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "verify_black_ledger_newsroom_surface.py"
SOURCE_FILES = [
    "Chummer.Run.Api/Controllers/PublicLandingController.cs",
    "Chummer.Run.Api/Views/PublicLanding/Ledger.cshtml",
    "Chummer.Run.Api/Services/Community/BlackLedgerWorldTickBriefingService.cs",
    "Chummer.Run.Api/ViewModels/SiteViewModels.cs",
    "scripts/verify_black_ledger_newsroom_surface.py",
    "tests/test_black_ledger_newsroom_surface.py",
]


class BlackLedgerNewsroomSurfaceTests(unittest.TestCase):
    def test_verifier_accepts_repo_surface(self) -> None:
        result = subprocess.run(
            ["python3", str(SCRIPT)],
            cwd=REPO_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)
        self.assertIn("black_ledger_newsroom_surface:ok", result.stdout)

    def test_verifier_fails_when_view_drops_receipts_link(self) -> None:
        with tempfile.TemporaryDirectory(prefix="black-ledger-newsroom-view-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            view_path = temp_root / "Chummer.Run.Api/Views/PublicLanding/Ledger.cshtml"
            view_path.write_text(
                view_path.read_text(encoding="utf-8").replace("Source receipts", "Source archive", 1),
                encoding="utf-8",
            )

            result = self.run_verifier(temp_root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "Chummer.Run.Api/Views/PublicLanding/Ledger.cshtml missing marker: Source receipts",
            result.stderr,
        )

    def test_verifier_fails_when_live_watch_route_drops_newsroom_heading(self) -> None:
        class FakeResponse:
            def __init__(self, text: str = "", status_code: int = 200, headers: dict[str, str] | None = None) -> None:
                self.text = text
                self.status_code = status_code
                self.headers = {"Cache-Control": "private, no-store, max-age=0", **(headers or {})}

            def raise_for_status(self) -> None:
                return None

        class FakeJsonResponse(FakeResponse):
            def __init__(self, payload: dict[str, object], status_code: int = 200) -> None:
                super().__init__(text="", status_code=status_code, headers={})
                self._payload = payload

            def json(self) -> dict[str, object]:
                return self._payload

        route_bodies = {
            "http://example.test/ledger/newsroom/turn-2-newsreel": "<section><h2>Ledger Bulletin</h2><video poster=\"/media/ledger/newsreels/turn-2-newsreel-poster.png?v=1\"><source src=\"/media/ledger/newsreels/turn-2-newsreel.mp4?v=1\" type=\"video/mp4\" /><source src=\"/media/ledger/newsreels/turn-2-newsreel.webm?v=1\" type=\"video/webm\" /><track kind=\"captions\" src=\"/media/ledger/newsreels/turn-2-newsreel.vtt?v=1\" /></video><a>Transcript</a><a>Source receipts</a><a>Feedback</a><span>Published:</span></section>",
        }
        receipts_payload = {
            "summary": "Turn 0 -> Turn 1 validation packet for the inbox/newsreel lane.",
            "checks": [
                "Public-safe effects carried: 6",
                "Notification route: /account/ledger/notifications",
            ],
        }
        redirect_bodies = {
            "http://example.test/ledger/newsroom": FakeResponse(status_code=302, headers={"Location": "/ledger/newsroom/turn-2-newsreel"}),
            "http://example.test/ledger/newsroom/turn-2-newsreel/transcript": FakeResponse(status_code=302, headers={"Location": "/media/ledger/newsreels/turn-2-newsreel.vtt"}),
            "http://example.test/ledger/newsroom/turn-999-newsreel": FakeResponse(status_code=404, headers={}),
            "http://example.test/ledger/newsroom/turn-999-newsreel/transcript": FakeResponse(status_code=404, headers={}),
            "http://example.test/ledger/newsroom/turn-999-newsreel/receipts": FakeResponse(status_code=404, headers={}),
        }

        def fake_get(url: str, timeout: int, allow_redirects: bool = True) -> FakeResponse:
            self.assertEqual(timeout, 30)
            if not allow_redirects:
                return redirect_bodies[url]
            if url.endswith("/turn-2-newsreel/receipts"):
                return FakeJsonResponse(receipts_payload)
            if url.endswith("turn-2-newsreel-poster.png?v=1"):
                return FakeResponse(status_code=200, headers={"Content-Type": "image/png"})
            if url.endswith("turn-2-newsreel.mp4?v=1"):
                return FakeResponse(status_code=200, headers={"Content-Type": "video/mp4"})
            if url.endswith("turn-2-newsreel.webm?v=1"):
                return FakeResponse(status_code=200, headers={"Content-Type": "video/webm"})
            if url.endswith("turn-2-newsreel.vtt?v=1"):
                return FakeResponse(status_code=200, headers={"Content-Type": "text/vtt"})
            return FakeResponse(route_bodies[url])

        script_dir = str(SCRIPT.parent)
        with patch.object(sys, "path", [script_dir, *sys.path]):
            import verify_black_ledger_newsroom_surface as verifier

        with patch.object(verifier.requests, "get", side_effect=fake_get), patch.object(
            sys,
            "argv",
            ["verify_black_ledger_newsroom_surface.py", "--base-url", "http://example.test"],
        ):
            self.assertEqual(verifier.main(), 1)

    def test_verifier_fails_when_live_transcript_redirect_drifts(self) -> None:
        class FakeResponse:
            def __init__(self, text: str = "", status_code: int = 200, headers: dict[str, str] | None = None) -> None:
                self.text = text
                self.status_code = status_code
                self.headers = {"Cache-Control": "private, no-store, max-age=0", **(headers or {})}

            def raise_for_status(self) -> None:
                return None

        class FakeJsonResponse(FakeResponse):
            def __init__(self, payload: dict[str, object], status_code: int = 200) -> None:
                super().__init__(text="", status_code=status_code, headers={})
                self._payload = payload

            def json(self) -> dict[str, object]:
                return self._payload

        route_bodies = {
            "http://example.test/ledger/newsroom/turn-2-newsreel": "<section><h2>Black Ledger Newsroom</h2><video poster=\"/media/ledger/newsreels/turn-2-newsreel-poster.png?v=1\"><source src=\"/media/ledger/newsreels/turn-2-newsreel.mp4?v=1\" type=\"video/mp4\" /><source src=\"/media/ledger/newsreels/turn-2-newsreel.webm?v=1\" type=\"video/webm\" /><track kind=\"captions\" src=\"/media/ledger/newsreels/turn-2-newsreel.vtt?v=1\" /></video><a>Transcript</a><a>Source receipts</a><a>Feedback</a><span>Published:</span></section>",
        }
        receipts_payload = {
            "summary": "Turn 0 -> Turn 1 validation packet for the inbox/newsreel lane.",
            "checks": [
                "Public-safe effects carried: 6",
                "Notification route: /account/ledger/notifications",
            ],
        }
        redirect_bodies = {
            "http://example.test/ledger/newsroom": FakeResponse(status_code=302, headers={"Location": "/ledger/newsroom/turn-2-newsreel"}),
            "http://example.test/ledger/newsroom/turn-2-newsreel/transcript": FakeResponse(status_code=302, headers={"Location": "/media/ledger/newsreels/turn-2-newsreel.txt"}),
            "http://example.test/ledger/newsroom/turn-999-newsreel": FakeResponse(status_code=404, headers={}),
            "http://example.test/ledger/newsroom/turn-999-newsreel/transcript": FakeResponse(status_code=404, headers={}),
            "http://example.test/ledger/newsroom/turn-999-newsreel/receipts": FakeResponse(status_code=404, headers={}),
        }

        def fake_get(url: str, timeout: int, allow_redirects: bool = True) -> FakeResponse:
            self.assertEqual(timeout, 30)
            if not allow_redirects:
                return redirect_bodies[url]
            if url.endswith("/turn-2-newsreel/receipts"):
                return FakeJsonResponse(receipts_payload)
            if url.endswith("turn-2-newsreel-poster.png?v=1"):
                return FakeResponse(status_code=200, headers={"Content-Type": "image/png"})
            if url.endswith("turn-2-newsreel.mp4?v=1"):
                return FakeResponse(status_code=200, headers={"Content-Type": "video/mp4"})
            if url.endswith("turn-2-newsreel.webm?v=1"):
                return FakeResponse(status_code=200, headers={"Content-Type": "video/webm"})
            if url.endswith("turn-2-newsreel.vtt?v=1"):
                return FakeResponse(status_code=200, headers={"Content-Type": "text/vtt"})
            return FakeResponse(route_bodies[url])

        script_dir = str(SCRIPT.parent)
        with patch.object(sys, "path", [script_dir, *sys.path]):
            import verify_black_ledger_newsroom_surface as verifier

        with patch.object(verifier.requests, "get", side_effect=fake_get), patch.object(
            sys,
            "argv",
            ["verify_black_ledger_newsroom_surface.py", "--base-url", "http://example.test"],
        ):
            self.assertEqual(verifier.main(), 1)

    def test_verifier_fails_when_invalid_episode_does_not_404(self) -> None:
        class FakeResponse:
            def __init__(self, text: str = "", status_code: int = 200, headers: dict[str, str] | None = None) -> None:
                self.text = text
                self.status_code = status_code
                self.headers = {"Cache-Control": "private, no-store, max-age=0", **(headers or {})}

            def raise_for_status(self) -> None:
                return None

        class FakeJsonResponse(FakeResponse):
            def __init__(self, payload: dict[str, object], status_code: int = 200) -> None:
                super().__init__(text="", status_code=status_code, headers={})
                self._payload = payload

            def json(self) -> dict[str, object]:
                return self._payload

        route_bodies = {
            "http://example.test/ledger/newsroom/turn-2-newsreel": "<section><h2>Black Ledger Newsroom</h2><video poster=\"/media/ledger/newsreels/turn-2-newsreel-poster.png?v=1\"><source src=\"/media/ledger/newsreels/turn-2-newsreel.mp4?v=1\" type=\"video/mp4\" /><source src=\"/media/ledger/newsreels/turn-2-newsreel.webm?v=1\" type=\"video/webm\" /><track kind=\"captions\" src=\"/media/ledger/newsreels/turn-2-newsreel.vtt?v=1\" /></video><a>Transcript</a><a>Source receipts</a><a>Feedback</a><span>Published:</span></section>",
        }
        receipts_payload = {
            "summary": "Turn 0 -> Turn 1 validation packet for the inbox/newsreel lane.",
            "checks": [
                "Public-safe effects carried: 6",
                "Notification route: /account/ledger/notifications",
            ],
        }
        redirect_bodies = {
            "http://example.test/ledger/newsroom": FakeResponse(status_code=302, headers={"Location": "/ledger/newsroom/turn-2-newsreel"}),
            "http://example.test/ledger/newsroom/turn-2-newsreel/transcript": FakeResponse(status_code=302, headers={"Location": "/media/ledger/newsreels/turn-2-newsreel.vtt"}),
            "http://example.test/ledger/newsroom/turn-999-newsreel": FakeResponse(status_code=200, headers={}),
            "http://example.test/ledger/newsroom/turn-999-newsreel/transcript": FakeResponse(status_code=404, headers={}),
            "http://example.test/ledger/newsroom/turn-999-newsreel/receipts": FakeResponse(status_code=404, headers={}),
        }

        def fake_get(url: str, timeout: int, allow_redirects: bool = True) -> FakeResponse:
            self.assertEqual(timeout, 30)
            if not allow_redirects:
                return redirect_bodies[url]
            if url.endswith("/turn-2-newsreel/receipts"):
                return FakeJsonResponse(receipts_payload)
            if url.endswith("turn-2-newsreel-poster.png?v=1"):
                return FakeResponse(status_code=200, headers={"Content-Type": "image/png"})
            if url.endswith("turn-2-newsreel.mp4?v=1"):
                return FakeResponse(status_code=200, headers={"Content-Type": "video/mp4"})
            if url.endswith("turn-2-newsreel.webm?v=1"):
                return FakeResponse(status_code=200, headers={"Content-Type": "video/webm"})
            if url.endswith("turn-2-newsreel.vtt?v=1"):
                return FakeResponse(status_code=200, headers={"Content-Type": "text/vtt"})
            return FakeResponse(route_bodies[url])

        script_dir = str(SCRIPT.parent)
        with patch.object(sys, "path", [script_dir, *sys.path]):
            import verify_black_ledger_newsroom_surface as verifier

        with patch.object(verifier.requests, "get", side_effect=fake_get), patch.object(
            sys,
            "argv",
            ["verify_black_ledger_newsroom_surface.py", "--base-url", "http://example.test"],
        ):
            self.assertEqual(verifier.main(), 1)

    def test_verifier_fails_when_watch_page_drops_mp4_asset_reference(self) -> None:
        class FakeResponse:
            def __init__(self, text: str = "", status_code: int = 200, headers: dict[str, str] | None = None) -> None:
                self.text = text
                self.status_code = status_code
                self.headers = {"Cache-Control": "private, no-store, max-age=0", **(headers or {})}

            def raise_for_status(self) -> None:
                return None

        class FakeJsonResponse(FakeResponse):
            def __init__(self, payload: dict[str, object], status_code: int = 200) -> None:
                super().__init__(text="", status_code=status_code, headers={})
                self._payload = payload

            def json(self) -> dict[str, object]:
                return self._payload

        watch_html = """
<section>
  <h2>Black Ledger Newsroom</h2>
  <video poster="/media/ledger/newsreels/turn-2-newsreel-poster.png?v=1">
    <source src="/media/ledger/newsreels/turn-2-newsreel.webm?v=1" type="video/webm" />
    <track kind="captions" src="/media/ledger/newsreels/turn-2-newsreel.vtt?v=1" />
  </video>
  <a>Transcript</a><a>Source receipts</a><a>Feedback</a><span>Published:</span>
</section>
"""
        receipts_payload = {
            "summary": "Turn 0 -> Turn 1 validation packet for the inbox/newsreel lane.",
            "checks": [
                "Public-safe effects carried: 6",
                "Notification route: /account/ledger/notifications",
            ],
        }
        redirect_bodies = {
            "http://example.test/ledger/newsroom": FakeResponse(status_code=302, headers={"Location": "/ledger/newsroom/turn-2-newsreel"}),
            "http://example.test/ledger/newsroom/turn-2-newsreel/transcript": FakeResponse(status_code=302, headers={"Location": "/media/ledger/newsreels/turn-2-newsreel.vtt"}),
            "http://example.test/ledger/newsroom/turn-999-newsreel": FakeResponse(status_code=404, headers={}),
            "http://example.test/ledger/newsroom/turn-999-newsreel/transcript": FakeResponse(status_code=404, headers={}),
            "http://example.test/ledger/newsroom/turn-999-newsreel/receipts": FakeResponse(status_code=404, headers={}),
        }

        def fake_get(url: str, timeout: int, allow_redirects: bool = True) -> FakeResponse:
            self.assertEqual(timeout, 30)
            if not allow_redirects:
                return redirect_bodies[url]
            if url.endswith("/ledger/newsroom/turn-2-newsreel"):
                return FakeResponse(text=watch_html)
            if url.endswith("/ledger/newsroom/turn-2-newsreel/receipts"):
                return FakeJsonResponse(receipts_payload)
            if url.endswith("turn-2-newsreel-poster.png?v=1"):
                return FakeResponse(status_code=200, headers={"Content-Type": "image/png"})
            if url.endswith("turn-2-newsreel.webm?v=1"):
                return FakeResponse(status_code=200, headers={"Content-Type": "video/webm"})
            if url.endswith("turn-2-newsreel.vtt?v=1"):
                return FakeResponse(status_code=200, headers={"Content-Type": "text/vtt"})
            raise AssertionError(f"unexpected url {url}")

        script_dir = str(SCRIPT.parent)
        with patch.object(sys, "path", [script_dir, *sys.path]):
            import verify_black_ledger_newsroom_surface as verifier

        with patch.object(verifier.requests, "get", side_effect=fake_get), patch.object(
            sys,
            "argv",
            ["verify_black_ledger_newsroom_surface.py", "--base-url", "http://example.test"],
        ):
            self.assertEqual(verifier.main(), 1)

    def test_verifier_fails_when_newsroom_route_lacks_no_store_headers(self) -> None:
        class FakeResponse:
            def __init__(self, text: str = "", status_code: int = 200, headers: dict[str, str] | None = None) -> None:
                self.text = text
                self.status_code = status_code
                self.headers = headers or {}

            def raise_for_status(self) -> None:
                return None

        class FakeJsonResponse(FakeResponse):
            def __init__(self, payload: dict[str, object], status_code: int = 200, headers: dict[str, str] | None = None) -> None:
                super().__init__(text="", status_code=status_code, headers=headers)
                self._payload = payload

            def json(self) -> dict[str, object]:
                return self._payload

        watch_html = """
<section>
  <h2>Black Ledger Newsroom</h2>
  <video poster="/media/ledger/newsreels/turn-2-newsreel-poster.png?v=1">
    <source src="/media/ledger/newsreels/turn-2-newsreel.mp4?v=1" type="video/mp4" />
    <source src="/media/ledger/newsreels/turn-2-newsreel.webm?v=1" type="video/webm" />
    <track kind="captions" src="/media/ledger/newsreels/turn-2-newsreel.vtt?v=1" />
  </video>
  <a>Transcript</a><a>Source receipts</a><a>Feedback</a><span>Published:</span>
</section>
"""
        receipts_payload = {
            "summary": "Turn 1 -> Turn 2 validation packet for the inbox/newsreel lane.",
            "checks": [
                "Public-safe effects carried: 3",
                "Notification route: /account/ledger/notifications",
            ],
        }
        redirect_bodies = {
            "http://example.test/ledger/newsroom": FakeResponse(status_code=302, headers={"Location": "/ledger/newsroom/turn-2-newsreel"}),
            "http://example.test/ledger/newsroom/turn-2-newsreel/transcript": FakeResponse(status_code=302, headers={"Location": "/media/ledger/newsreels/turn-2-newsreel.vtt", "Cache-Control": "private"}),
            "http://example.test/ledger/newsroom/turn-999-newsreel": FakeResponse(status_code=404, headers={"Cache-Control": "private, no-store, max-age=0"}),
            "http://example.test/ledger/newsroom/turn-999-newsreel/transcript": FakeResponse(status_code=404, headers={"Cache-Control": "private, no-store, max-age=0"}),
            "http://example.test/ledger/newsroom/turn-999-newsreel/receipts": FakeResponse(status_code=404, headers={"Cache-Control": "private, no-store, max-age=0"}),
        }

        def fake_get(url: str, timeout: int, allow_redirects: bool = True) -> FakeResponse:
            self.assertEqual(timeout, 30)
            if not allow_redirects:
                return redirect_bodies[url]
            if url.endswith("/ledger/newsroom/turn-2-newsreel"):
                return FakeResponse(text=watch_html, headers={"Cache-Control": "private"})
            if url.endswith("/ledger/newsroom/turn-2-newsreel/receipts"):
                return FakeJsonResponse(receipts_payload, headers={"Cache-Control": "private, no-store, max-age=0"})
            if url.endswith("turn-2-newsreel-poster.png?v=1"):
                return FakeResponse(status_code=200, headers={"Content-Type": "image/png"})
            if url.endswith("turn-2-newsreel.mp4?v=1"):
                return FakeResponse(status_code=200, headers={"Content-Type": "video/mp4"})
            if url.endswith("turn-2-newsreel.webm?v=1"):
                return FakeResponse(status_code=200, headers={"Content-Type": "video/webm"})
            if url.endswith("turn-2-newsreel.vtt?v=1"):
                return FakeResponse(status_code=200, headers={"Content-Type": "text/vtt"})
            raise AssertionError(f"unexpected url {url}")

        script_dir = str(SCRIPT.parent)
        with patch.object(sys, "path", [script_dir, *sys.path]):
            import verify_black_ledger_newsroom_surface as verifier

        with patch.object(verifier.requests, "get", side_effect=fake_get), patch.object(
            sys,
            "argv",
            ["verify_black_ledger_newsroom_surface.py", "--base-url", "http://example.test"],
        ):
            self.assertEqual(verifier.main(), 1)

    @staticmethod
    def copy_sources(temp_root: Path) -> None:
        for relative_path in SOURCE_FILES:
            source = REPO_ROOT / relative_path
            target = temp_root / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)

    @staticmethod
    def run_verifier(temp_root: Path) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["CHUMMER_BLACK_LEDGER_NEWSROOM_ROOT"] = str(temp_root)
        return subprocess.run(
            ["python3", str(temp_root / "scripts/verify_black_ledger_newsroom_surface.py")],
            cwd=temp_root,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )


if __name__ == "__main__":
    unittest.main()
