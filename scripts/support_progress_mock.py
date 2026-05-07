#!/usr/bin/env python3
import hashlib
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


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
