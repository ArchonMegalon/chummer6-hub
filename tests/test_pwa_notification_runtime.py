from __future__ import annotations

import json
import subprocess
import textwrap
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


REPO_ROOT = Path(__file__).resolve().parents[1]
VERIFY_SCRIPT = REPO_ROOT / "scripts" / "verify_pwa_notification_runtime.py"
SERVICE_WORKER = REPO_ROOT / "Chummer.Run.Api" / "wwwroot" / "service-worker.js"


class PwaNotificationRuntimeTests(unittest.TestCase):
    def test_verifier_accepts_repo_service_worker(self) -> None:
        result = subprocess.run(
            ["python3", str(VERIFY_SCRIPT)],
            cwd=REPO_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)
        self.assertIn("pwa_notification_runtime:ok", result.stdout)

    def test_verifier_prefers_registered_service_worker_url_for_live_base(self) -> None:
        module_globals: dict[str, object] = {
            "__file__": str(VERIFY_SCRIPT),
            "__name__": "verify_pwa_notification_runtime_test",
        }
        exec(VERIFY_SCRIPT.read_text(encoding="utf-8"), module_globals)
        load_service_worker_text = module_globals["load_service_worker_text"]
        service_worker_text = SERVICE_WORKER.read_text(encoding="utf-8")
        requested_urls: list[str] = []

        def fake_get(url: str, timeout: int = 30) -> Mock:
            del timeout
            requested_urls.append(url)
            if url.endswith("/mobile"):
                return Mock(ok=True, text='navigator.serviceWorker.register("/service-worker.js?v=proof", { scope: "/" });')

            return Mock(ok=True, text=service_worker_text, raise_for_status=lambda: None)

        with patch.object(module_globals["requests"], "get", side_effect=fake_get):
            text = load_service_worker_text("https://chummer.run")

        self.assertEqual(text, service_worker_text)
        self.assertIn("https://chummer.run/service-worker.js?v=proof", requested_urls)

    def test_service_worker_push_and_notification_routes_are_bounded(self) -> None:
        node_script = textwrap.dedent(
            f"""
            (async () => {{
            const fs = require("node:fs");
            const vm = require("node:vm");

            const source = fs.readFileSync({json.dumps(str(SERVICE_WORKER))}, "utf8");
            const eventHandlers = {{}};
            const notifications = [];
            const clientMessages = [];
            const opened = [];
            const focused = [];

            const existingClient = {{
              url: "https://chummer.run/mobile",
              focus: async () => {{ focused.push("focus"); return existingClient; }},
              navigate: async (url) => {{ opened.push(url); return existingClient; }},
              postMessage: (message) => clientMessages.push(message)
            }};

            const context = {{
              URL,
              Response,
              caches: {{
                open: async () => ({{ addAll: async () => {{}}, put: async () => {{}} }}),
                keys: async () => [],
                delete: async () => true,
                match: async () => null
              }},
              fetch: async (request) => new Response("ok", {{ status: 200 }}),
              self: {{
                location: {{ origin: "https://chummer.run" }},
                registration: {{
                  showNotification: async (title, options) => notifications.push({{ title, options }}),
                  navigationPreload: {{ enable: async () => {{}} }}
                }},
                skipWaiting: async () => {{}},
                addEventListener: (name, handler) => {{ eventHandlers[name] = handler; }},
                clients: {{
                  matchAll: async () => [existingClient],
                  openWindow: async (url) => opened.push(`open:${{url}}`)
                }}
              }}
            }};

            vm.createContext(context);
            vm.runInContext(source, context);

            let pushPromise = null;
            const pushEvent = {{
              data: {{
                json: () => ({{
                  title: "Table Pulse",
                  body: "Heat moved in Tacoma.",
                  href: "/admin/hidden-ops",
                  tag: "table-pulse",
                  icon: "/admin/track.png",
                  badge: "/favicon.svg",
                  actions: [
                    {{
                      action: "open-admin",
                      title: "Open admin",
                      href: "/admin/hidden-ops"
                    }},
                    {{
                      action: "open-passport",
                      title: "Open passport",
                      href: "/passport"
                    }}
                  ]
                }})
              }},
              waitUntil: (promise) => {{ pushPromise = promise; return promise; }}
            }};

            eventHandlers.push(pushEvent);
            await pushPromise;

            let clickPromise = null;
            const clickEvent = {{
              action: "open-passport",
              notification: {{
                data: notifications[0].options.data,
                close: () => {{}}
              }},
              waitUntil: (promise) => {{ clickPromise = promise; return promise; }}
            }};

            eventHandlers.notificationclick(clickEvent);
            await clickPromise;

            let closePromise = null;
            const closeEvent = {{
              notification: {{
                data: {{ href: "/account/ledger/notifications", tag: "table-pulse" }}
              }},
              waitUntil: (promise) => {{ closePromise = promise; return promise; }}
            }};

            eventHandlers.notificationclose(closeEvent);
            await closePromise;

            process.stdout.write(JSON.stringify({{
              notifications,
              clientMessages,
              opened,
              focused
            }}));
            }})().catch((error) => {{
              console.error(error);
              process.exit(1);
            }});
            """
        )

        result = subprocess.run(
            ["node", "-e", node_script],
            cwd=REPO_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)
        payload = json.loads(result.stdout)

        self.assertEqual(len(payload["notifications"]), 1)
        self.assertEqual(payload["notifications"][0]["title"], "Table Pulse")
        self.assertEqual(payload["notifications"][0]["options"]["data"]["href"], "/account/ledger/notifications")
        self.assertEqual(payload["notifications"][0]["options"]["icon"], "/apple-touch-icon.png")
        self.assertEqual(payload["notifications"][0]["options"]["badge"], "/favicon.svg")
        self.assertEqual(payload["notifications"][0]["options"]["actions"], [{"action": "open-passport", "title": "Open passport"}])
        self.assertEqual(payload["notifications"][0]["options"]["data"]["actionRoutes"], {"open-passport": "/passport"})

        message_types = [entry["type"] for entry in payload["clientMessages"]]
        self.assertIn("chummer:pwa-notification-push", message_types)
        self.assertIn("chummer:pwa-notification-click", message_types)
        self.assertIn("chummer:pwa-notification-close", message_types)
        self.assertTrue(payload["focused"])
        self.assertIn("https://chummer.run/passport", payload["opened"])

    def test_service_worker_runtime_cache_is_public_only(self) -> None:
        node_script = textwrap.dedent(
            f"""
            const fs = require("node:fs");
            const vm = require("node:vm");

            const source = fs.readFileSync({json.dumps(str(SERVICE_WORKER))}, "utf8");
            const context = {{
              URL,
              Response,
              caches: {{
                open: async () => ({{ addAll: async () => {{}}, put: async () => {{}} }}),
                keys: async () => [],
                delete: async () => true,
                match: async () => null
              }},
              fetch: async () => new Response("ok", {{ status: 200 }}),
              self: {{
                location: {{ origin: "https://chummer.run" }},
                registration: {{
                  showNotification: async () => {{}},
                  navigationPreload: {{ enable: async () => {{}} }}
                }},
                skipWaiting: async () => {{}},
                addEventListener: () => {{}},
                clients: {{
                  matchAll: async () => [],
                  openWindow: async () => null
                }}
              }}
            }};

            vm.createContext(context);
            vm.runInContext(source, context);

            const publicNavigate = {{ url: "https://chummer.run/mobile", mode: "navigate" }};
            const accountNavigate = {{ url: "https://chummer.run/account/ledger/notifications", mode: "navigate" }};
            const apiGet = {{ url: "https://chummer.run/api/v1/ledger/worlds", mode: "same-origin" }};
            const publicAsset = {{ url: "https://chummer.run/css/site.css", mode: "same-origin" }};
            const payload = {{
              publicNavigate: context.isPublicRuntimeCacheableRequest(publicNavigate),
              accountNavigate: context.isPublicRuntimeCacheableRequest(accountNavigate),
              apiGet: context.isPublicRuntimeCacheableRequest(apiGet),
              publicAsset: context.isPublicRuntimeCacheableRequest(publicAsset),
              publicResponse: context.shouldCacheResponse(publicNavigate, new Response("ok", {{ status: 200 }})),
              accountResponse: context.shouldCacheResponse(accountNavigate, new Response("ok", {{ status: 200 }})),
              validNotificationHref: context.normalizeNotificationHref("/ledger/turns/42?source=pwa"),
              invalidNotificationHref: context.normalizeNotificationHref("/admin/hidden-ops"),
              externalNotificationHref: context.normalizeNotificationHref("https://evil.invalid/passport"),
              validNotificationAsset: context.normalizeNotificationAssetPath("/media/ledger/globe/black-ledger-video-globe-idle-poster.png", "/fallback.png"),
              invalidNotificationAsset: context.normalizeNotificationAssetPath("/api/v1/account/ledger/track.png", "/fallback.png")
            }};
            process.stdout.write(JSON.stringify(payload));
            """
        )

        result = subprocess.run(
            ["node", "-e", node_script],
            cwd=REPO_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)
        payload = json.loads(result.stdout)

        self.assertTrue(payload["publicNavigate"])
        self.assertTrue(payload["publicAsset"])
        self.assertTrue(payload["publicResponse"])
        self.assertFalse(payload["accountNavigate"])
        self.assertFalse(payload["apiGet"])
        self.assertFalse(payload["accountResponse"])
        self.assertEqual(payload["validNotificationHref"], "/ledger/turns/42?source=pwa")
        self.assertEqual(payload["invalidNotificationHref"], "/account/ledger/notifications")
        self.assertEqual(payload["externalNotificationHref"], "/account/ledger/notifications")
        self.assertEqual(payload["validNotificationAsset"], "/media/ledger/globe/black-ledger-video-globe-idle-poster.png")
        self.assertEqual(payload["invalidNotificationAsset"], "/fallback.png")

    def test_verifier_accepts_served_service_worker_asset(self) -> None:
        class FakeResponse:
            def __init__(self, text: str) -> None:
                self.text = text

            def raise_for_status(self) -> None:
                return None

        script_dir = str(VERIFY_SCRIPT.parent)
        import sys

        if script_dir not in sys.path:
            sys.path.insert(0, script_dir)

        import verify_pwa_notification_runtime as verifier

        with patch.object(verifier.requests, "get", return_value=FakeResponse(SERVICE_WORKER.read_text(encoding="utf-8"))):
            with patch.object(sys, "argv", ["verify_pwa_notification_runtime.py", "--base-url", "http://example.test"]):
                self.assertEqual(verifier.main(), 0)

    def test_verifier_fails_when_served_service_worker_asset_drops_required_marker(self) -> None:
        class FakeResponse:
            def __init__(self, text: str) -> None:
                self.text = text

            def raise_for_status(self) -> None:
                return None

        script_dir = str(VERIFY_SCRIPT.parent)
        import sys

        if script_dir not in sys.path:
            sys.path.insert(0, script_dir)

        import verify_pwa_notification_runtime as verifier

        drifted = SERVICE_WORKER.read_text(encoding="utf-8").replace(
            'self.addEventListener("notificationclick"',
            'self.addEventListener("notifyclick"',
            1,
        )

        with patch.object(verifier.requests, "get", return_value=FakeResponse(drifted)):
            with patch.object(sys, "argv", ["verify_pwa_notification_runtime.py", "--base-url", "http://example.test"]):
                self.assertEqual(verifier.main(), 1)

if __name__ == "__main__":
    unittest.main()
