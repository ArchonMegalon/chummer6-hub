from __future__ import annotations

import json
import subprocess
import textwrap
import unittest
from pathlib import Path


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
                  href: "/account/ledger/notifications",
                  tag: "table-pulse",
                  icon: "https://evil.invalid/track.png",
                  badge: "/favicon.svg",
                  actions: [
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

        message_types = [entry["type"] for entry in payload["clientMessages"]]
        self.assertIn("chummer:pwa-notification-push", message_types)
        self.assertIn("chummer:pwa-notification-click", message_types)
        self.assertIn("chummer:pwa-notification-close", message_types)
        self.assertTrue(payload["focused"])
        self.assertIn("https://chummer.run/passport", payload["opened"])


if __name__ == "__main__":
    unittest.main()
