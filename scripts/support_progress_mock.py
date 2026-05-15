#!/usr/bin/env python3
import hashlib
import html
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib import error, request


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict) -> None:
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Connection", "close")
    handler.end_headers()
    handler.wfile.write(body)
    handler.close_connection = True


class SupportProgressMockHandler(BaseHTTPRequestHandler):
    server_version = "support-progress-mock/1.0"

    def log_message(self, format: str, *args) -> None:
        return

    def do_GET(self) -> None:
        if self.path == "/healthz":
            _json_response(self, 200, {"ok": True})
            return

        _json_response(self, 404, {"error": "not_found"})

    def do_POST(self) -> None:
        raw = self._read_body()
        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            _json_response(self, 400, {"error": "invalid_json"})
            return

        if self.path == "/v1/tools/execute":
            delivery_id = self._build_delivery_id(payload)
            self._maybe_forward_email_delivery(delivery_id, payload)
            _json_response(
                self,
                200,
                {
                    "target_ref": delivery_id,
                    "output_json": {
                        "delivery_id": delivery_id,
                        "status": "queued",
                    },
                    "receipt_json": {
                        "handler_key": "connector.dispatch",
                        "invocation_contract": "tool.v1",
                    },
                },
            )
            return

        if self.path.startswith("/v1/delivery/outbox/") and self.path.endswith("/sent"):
            delivery_id = self.path.split("/")[-2]
            _json_response(self, 200, {"delivery_id": delivery_id, "state": "sent"})
            return

        if self.path.startswith("/v1/delivery/outbox/") and self.path.endswith("/failed"):
            delivery_id = self.path.split("/")[-2]
            _json_response(self, 200, {"delivery_id": delivery_id, "state": "failed"})
            return

        if self.path == "/emails":
            meta = payload.get("meta") if isinstance(payload, dict) else {}
            delivery_id = ""
            if isinstance(meta, dict):
                delivery_id = str(meta.get("delivery_id") or "").strip()
            if not delivery_id:
                delivery_id = self._build_delivery_id(payload)
            _json_response(self, 200, {"id": f"emailit_{delivery_id}"})
            return

        _json_response(self, 404, {"error": "not_found"})

    def _maybe_forward_email_delivery(self, delivery_id: str, payload: object) -> None:
        if not isinstance(payload, dict):
            return
        if payload.get("tool_name") != "connector.dispatch":
            return
        if payload.get("action_kind") != "delivery.send":
            return
        payload_json = payload.get("payload_json")
        if not isinstance(payload_json, dict):
            return
        if str(payload_json.get("channel") or "").strip().lower() != "email":
            return

        api_key = (os.environ.get("SUPPORT_PROGRESS_EMAILIT_API_KEY") or "").strip()
        if not api_key:
            return

        recipient = str(payload_json.get("recipient") or "").strip()
        subject = str(payload_json.get("subject") or "").strip()
        content = str(payload_json.get("content") or "").strip()
        if not recipient or not subject or not content:
            return

        base_url = (os.environ.get("SUPPORT_PROGRESS_EMAILIT_BASE_URL") or "https://api.emailit.com/v2").strip().rstrip("/")
        from_email = (os.environ.get("SUPPORT_PROGRESS_EMAILIT_FROM_EMAIL") or "concierge@chummer.run").strip()
        from_name = (os.environ.get("SUPPORT_PROGRESS_EMAILIT_FROM_NAME") or "Chummer Concierge").strip()
        reply_to = (os.environ.get("SUPPORT_PROGRESS_EMAILIT_REPLY_TO") or "support@chummer.run").strip()
        email_payload = {
            "from": f"{from_name} <{from_email}>",
            "to": recipient,
            "subject": subject,
            "text": content,
            "html": f"<pre>{html.escape(content)}</pre>",
            "reply_to": reply_to,
            "tracking": False,
            "meta": {"delivery_id": delivery_id},
        }
        req = request.Request(
            f"{base_url}/emails",
            data=json.dumps(email_payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=30) as response:
                if response.status >= 400:
                    raise RuntimeError(f"emailit_error_{response.status}")
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"emailit_error_{exc.code}:{detail}") from exc

    @staticmethod
    def _build_delivery_id(payload: object) -> str:
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        digest = hashlib.sha256(canonical).hexdigest()[:16]
        return f"delivery_{digest}"

    def _read_body(self) -> bytes:
        transfer_encoding = self.headers.get("Transfer-Encoding", "")
        if "chunked" in transfer_encoding.lower():
            chunks: list[bytes] = []
            while True:
                size_line = self.rfile.readline()
                if not size_line:
                    break

                size_token = size_line.split(b";", 1)[0].strip()
                if not size_token:
                    continue

                chunk_size = int(size_token, 16)
                if chunk_size == 0:
                    while True:
                        trailer_line = self.rfile.readline()
                        if trailer_line in (b"", b"\r\n", b"\n"):
                            break
                    break

                chunks.append(self.rfile.read(chunk_size))
                self.rfile.read(2)

            return b"".join(chunks)

        content_length = int(self.headers.get("Content-Length", "0") or "0")
        return self.rfile.read(content_length) if content_length > 0 else b""


def main() -> None:
    host = os.environ.get("SUPPORT_PROGRESS_MOCK_HOST", "0.0.0.0").strip() or "0.0.0.0"
    port = int(os.environ.get("SUPPORT_PROGRESS_MOCK_PORT", "8080") or "8080")
    server = ThreadingHTTPServer((host, port), SupportProgressMockHandler)
    server.serve_forever()


if __name__ == "__main__":
    main()
