#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import requests

from absolute_completion_common import LocalHubApp, TokenIdentityStub, completion_path, pick_free_port, write_json, write_text


WORLD_ID = "emerald-sprawl-prelude"
DEFAULT_OUTPUT_ROOT = Path("/docker/chummercomplete/_completion/pre_gold_full_product")
INTERNAL_TOKEN = "black-ledger-internal-proof-token"
ACCESS_TOKEN = "black-ledger-signed-in-proof-token"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prove Black Ledger Turn 1 newsreel delivery, suppression, and idempotency.")
    parser.add_argument("--world", default=WORLD_ID)
    parser.add_argument("--from-turn", type=int, default=0)
    parser.add_argument("--to-turn", type=int, default=1)
    return parser.parse_args()


@contextmanager
def patched_env(overrides: dict[str, str | None]):
    previous = {key: os.environ.get(key) for key in overrides}
    try:
        for key, value in overrides.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


class EaDispatchStub:
    def __init__(self, *, delivery_id: str = "ea-delivery-turn1-newsreel") -> None:
        self.port = pick_free_port()
        self.base_url = f"http://127.0.0.1:{self.port}"
        self.delivery_id = delivery_id
        self.requests: list[dict[str, Any]] = []
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def __enter__(self) -> "EaDispatchStub":
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: object) -> None:
                return

            def do_POST(self) -> None:  # noqa: N802
                length = int(self.headers.get("Content-Length", "0") or "0")
                raw = self.rfile.read(length).decode("utf-8") if length else "{}"
                payload = json.loads(raw or "{}")
                stub.requests.append(
                    {
                        "path": self.path,
                        "authorization": self.headers.get("Authorization", ""),
                        "idempotency_key": self.headers.get("Idempotency-Key", ""),
                        "payload": payload,
                    }
                )
                body = json.dumps({"target_ref": stub.delivery_id}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self._server = ThreadingHTTPServer(("127.0.0.1", self.port), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)


def prepare_session(base_url: str, access_token: str) -> requests.Session:
    session = requests.Session()
    session.headers["Authorization"] = f"Bearer {access_token}"
    response = session.get(f"{base_url}/account/ledger/onboarding", timeout=30, allow_redirects=False)
    if response.status_code not in {200, 302}:
        raise RuntimeError(f"failed to establish signed-in ledger session: {response.status_code}")
    return session


def send_tick_news(base_url: str, *, dry_run: bool) -> dict[str, Any]:
    response = requests.post(
        f"{base_url}/api/v1/ledger/worlds/{WORLD_ID}/tick-news/send",
        params={"turn": 1, "dryRun": str(dry_run).lower()},
        headers={"Authorization": f"Bearer {INTERNAL_TOKEN}"},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def fetch_route(session: requests.Session | None, url: str) -> dict[str, Any]:
    client = session or requests
    response = client.get(url, timeout=30, allow_redirects=False)
    return {
        "status_code": response.status_code,
        "location": response.headers.get("Location"),
        "contains_sent": "Sent" in response.text,
        "contains_suppressed": "Suppressed" in response.text,
        "contains_dry_run": "Dry run" in response.text,
        "contains_not_current_recipient": "not a recipient" in response.text.lower(),
    }


def run_sent_and_duplicate_scenario() -> dict[str, Any]:
    with EaDispatchStub() as ea_stub:
        env = {
            "FLEET_INTERNAL_API_TOKEN": INTERNAL_TOKEN,
            "CHUMMER_BLACK_LEDGER_NEWS_EMAIL_ENABLED": "true",
            "CHUMMER_BLACK_LEDGER_NEWS_EMAIL_POLICY": "operator_only",
            "CHUMMER_BLACK_LEDGER_NEWS_OPERATOR_TO": "operator@chummer.run",
            "CHUMMER_BLACK_LEDGER_NEWS_EA_API_TOKEN": "ea-api-token",
            "CHUMMER_BLACK_LEDGER_NEWS_EA_PRINCIPAL_ID": "principal-turn1",
            "CHUMMER_BLACK_LEDGER_NEWS_EA_BINDING_ID": "binding-turn1",
            "CHUMMER_BLACK_LEDGER_NEWS_EA_BASE_URL": ea_stub.base_url,
            "CHUMMER_BLACK_LEDGER_NEWS_HASH_SALT": "turn1-proof-salt",
        }
        with patched_env(env):
            with TokenIdentityStub(
                access_token=ACCESS_TOKEN,
                subject_id="subject.turn1.news",
                display_name="Turn One Proof Runner",
                email="turn1-proof@chummer.run",
            ) as identity:
                with LocalHubApp(identity_base_url=identity.base_url) as app:
                    session = prepare_session(app.base_url, ACCESS_TOKEN)
                    joined = session.post(
                        f"{app.base_url}/api/v1/account/ledger/allegiance/join",
                        json={"factionId": "ashline-circle"},
                        timeout=30,
                    )
                    joined.raise_for_status()
                    first = send_tick_news(app.base_url, dry_run=False)
                    duplicate = send_tick_news(app.base_url, dry_run=False)
                    account = fetch_route(session, f"{app.base_url}/account/ledger")
                    notifications = fetch_route(session, f"{app.base_url}/account/ledger/notifications")
                    turn_page = fetch_route(None, f"{app.base_url}/ledger/turns/1")
                    return {
                        "event": {
                            "worldId": WORLD_ID,
                            "turn": 1,
                            "batchId": first.get("BatchId") or first.get("batchId"),
                            "tickReceiptId": first.get("TickReceiptId") or first.get("tickReceiptId"),
                            "newsId": first.get("NewsId") or first.get("newsId"),
                        },
                        "first_batch": first,
                        "duplicate_batch": duplicate,
                        "ea_requests": ea_stub.requests,
                        "account_route": account,
                        "notifications_route": notifications,
                        "turn_route": turn_page,
                        "base_url": app.base_url,
                        "join_receipt": joined.json(),
                    }


def run_disabled_scenario() -> dict[str, Any]:
    env = {
        "FLEET_INTERNAL_API_TOKEN": INTERNAL_TOKEN,
        "CHUMMER_BLACK_LEDGER_NEWS_EMAIL_ENABLED": "false",
        "CHUMMER_BLACK_LEDGER_NEWS_EMAIL_POLICY": "operator_only",
        "CHUMMER_BLACK_LEDGER_NEWS_OPERATOR_TO": "operator@chummer.run",
    }
    with patched_env(env):
        with TokenIdentityStub(access_token=ACCESS_TOKEN, subject_id="subject.turn1.disabled", display_name="Disabled Proof", email="disabled@chummer.run") as identity:
            with LocalHubApp(identity_base_url=identity.base_url) as app:
                session = prepare_session(app.base_url, ACCESS_TOKEN)
                payload = send_tick_news(app.base_url, dry_run=False)
                notifications = fetch_route(session, f"{app.base_url}/account/ledger/notifications")
                return {"batch": payload, "notifications_route": notifications}


def run_unconfigured_scenario() -> dict[str, Any]:
    env = {
        "FLEET_INTERNAL_API_TOKEN": INTERNAL_TOKEN,
        "CHUMMER_BLACK_LEDGER_NEWS_EMAIL_ENABLED": "true",
        "CHUMMER_BLACK_LEDGER_NEWS_EMAIL_POLICY": "operator_only",
        "CHUMMER_BLACK_LEDGER_NEWS_OPERATOR_TO": "operator@chummer.run",
        "CHUMMER_BLACK_LEDGER_NEWS_EA_API_TOKEN": None,
        "CHUMMER_BLACK_LEDGER_NEWS_EA_PRINCIPAL_ID": None,
        "CHUMMER_BLACK_LEDGER_NEWS_EA_BINDING_ID": None,
        "CHUMMER_BLACK_LEDGER_NEWS_EA_BASE_URL": None,
    }
    with patched_env(env):
        with TokenIdentityStub(access_token=ACCESS_TOKEN, subject_id="subject.turn1.unconfigured", display_name="Unconfigured Proof", email="unconfigured@chummer.run") as identity:
            with LocalHubApp(identity_base_url=identity.base_url) as app:
                payload = send_tick_news(app.base_url, dry_run=False)
                return {"batch": payload}


def run_dry_run_scenario() -> dict[str, Any]:
    env = {
        "FLEET_INTERNAL_API_TOKEN": INTERNAL_TOKEN,
        "CHUMMER_BLACK_LEDGER_NEWS_EMAIL_ENABLED": "true",
        "CHUMMER_BLACK_LEDGER_NEWS_EMAIL_POLICY": "operator_only",
        "CHUMMER_BLACK_LEDGER_NEWS_OPERATOR_TO": "operator@chummer.run",
        "CHUMMER_BLACK_LEDGER_NEWS_EA_API_TOKEN": "ea-api-token",
        "CHUMMER_BLACK_LEDGER_NEWS_EA_PRINCIPAL_ID": "principal-turn1",
        "CHUMMER_BLACK_LEDGER_NEWS_EA_BINDING_ID": "binding-turn1",
        "CHUMMER_BLACK_LEDGER_NEWS_EA_BASE_URL": "http://127.0.0.1:65535",
    }
    with patched_env(env):
        with TokenIdentityStub(access_token=ACCESS_TOKEN, subject_id="subject.turn1.dryrun", display_name="Dry Run Proof", email="dryrun@chummer.run") as identity:
            with LocalHubApp(identity_base_url=identity.base_url) as app:
                payload = send_tick_news(app.base_url, dry_run=True)
                return {"batch": payload}


def main() -> int:
    _ = parse_args()
    DEFAULT_OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    sent = run_sent_and_duplicate_scenario()
    disabled = run_disabled_scenario()
    unconfigured = run_unconfigured_scenario()
    dry_run = run_dry_run_scenario()

    event_payload = {
        "contract_name": "black_ledger_turn1_newsreel_event",
        "generated_at_utc": now_iso(),
        "status": "pass" if sent["event"].get("turn") == 1 and sent["first_batch"].get("TickReceiptId", sent["first_batch"].get("tickReceiptId")) else "fail",
        "world_id": WORLD_ID,
        "turn_event": sent["event"],
        "news_batch_id": sent["first_batch"].get("batchId") or sent["first_batch"].get("BatchId"),
    }
    recipient_payload = {
        "contract_name": "black_ledger_turn1_newsreel_recipients",
        "generated_at_utc": now_iso(),
        "status": "pass" if int(sent["first_batch"].get("recipientCount", sent["first_batch"].get("RecipientCount", 0))) >= 1 else "fail",
        "policy": sent["first_batch"].get("policy") or sent["first_batch"].get("Policy"),
        "recipient_count": sent["first_batch"].get("recipientCount", sent["first_batch"].get("RecipientCount")),
        "ea_requests": sent["ea_requests"],
    }
    sent_payload = {
        "contract_name": "black_ledger_turn1_newsreel_email_sent",
        "generated_at_utc": now_iso(),
        "status": "pass"
        if (sent["first_batch"].get("status") or sent["first_batch"].get("Status")) == "sent"
        and sent["turn_route"]["contains_sent"]
        and sent["account_route"]["contains_suppressed"]
        and sent["notifications_route"]["contains_suppressed"]
        else "fail",
        "batch": sent["first_batch"],
        "account_route": sent["account_route"],
        "notifications_route": sent["notifications_route"],
        "turn_route": sent["turn_route"],
    }
    suppressed_payload = {
        "contract_name": "black_ledger_turn1_newsreel_email_suppressed",
        "generated_at_utc": now_iso(),
        "status": "pass"
        if (disabled["batch"].get("status") or disabled["batch"].get("Status")) == "suppressed_disabled"
        and (unconfigured["batch"].get("status") or unconfigured["batch"].get("Status")) == "suppressed_delivery_unconfigured"
        else "fail",
        "disabled": disabled,
        "delivery_unconfigured": unconfigured,
        "dry_run": dry_run,
    }
    idempotency_payload = {
        "contract_name": "black_ledger_turn1_newsreel_idempotency",
        "generated_at_utc": now_iso(),
        "status": "pass"
        if (sent["duplicate_batch"].get("status") or sent["duplicate_batch"].get("Status")) == "duplicate"
        else "fail",
        "first_status": sent["first_batch"].get("status") or sent["first_batch"].get("Status"),
        "duplicate_status": sent["duplicate_batch"].get("status") or sent["duplicate_batch"].get("Status"),
        "duplicate_batch": sent["duplicate_batch"],
    }

    write_json(DEFAULT_OUTPUT_ROOT / "BLACK_LEDGER_TURN1_NEWSREEL_EVENT.generated.json", event_payload)
    write_json(DEFAULT_OUTPUT_ROOT / "BLACK_LEDGER_TURN1_NEWSREEL_RECIPIENTS.generated.json", recipient_payload)
    write_json(DEFAULT_OUTPUT_ROOT / "BLACK_LEDGER_TURN1_NEWSREEL_EMAIL_SENT.generated.json", sent_payload)
    write_json(DEFAULT_OUTPUT_ROOT / "BLACK_LEDGER_TURN1_NEWSREEL_EMAIL_SUPPRESSED.generated.json", suppressed_payload)
    write_json(DEFAULT_OUTPUT_ROOT / "BLACK_LEDGER_TURN1_NEWSREEL_IDEMPOTENCY.generated.json", idempotency_payload)

    verdict = "pass" if all(payload["status"] == "pass" for payload in [event_payload, recipient_payload, sent_payload, suppressed_payload, idempotency_payload]) else "fail"
    write_text(
        DEFAULT_OUTPUT_ROOT / "BLACK_LEDGER_TURN1_NEWSREEL_VERDICT.md",
        "\n".join(
            [
                "# Black Ledger Turn 1 newsreel verdict",
                "",
                f"- Generated: {now_iso()}",
                f"- Verdict: `{verdict}`",
                f"- Sent status: `{sent_payload['status']}`",
                f"- Suppressed status: `{suppressed_payload['status']}`",
                f"- Idempotency status: `{idempotency_payload['status']}`",
            ]
        ),
    )
    return 0 if verdict == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
