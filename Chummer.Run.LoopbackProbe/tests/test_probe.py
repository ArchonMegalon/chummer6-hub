#!/usr/bin/env python3

from __future__ import annotations

import copy
import http.server
import json
import os
import pathlib
import subprocess
import sys
import threading
import unittest


PROJECT_DIR = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_ASSEMBLY = (
    PROJECT_DIR / "bin" / "Debug" / "net10.0" / "Chummer.Run.LoopbackProbe.dll"
)
ASSEMBLY = pathlib.Path(
    os.environ.get("CHUMMER_LOOPBACK_PROBE_ASSEMBLY", str(DEFAULT_ASSEMBLY))
).resolve()
SHA_A = "a" * 64
SHA_B = "b" * 64
TIMESTAMP = "2026-07-23T12:00:00.0000000+00:00"


AUTHORITY_PAYLOAD = {
    "authorityIdentitySha256": SHA_A,
    "checkedAtUtc": TIMESTAMP,
    "code": "runtime_role_least_privilege",
    "contractName": (
        "chummer.install_linking_postgres_runtime_authority_readiness.v1"
    ),
    "currentRoleMatches": True,
    "leastPrivilegeValid": True,
    "ready": True,
    "runtimeRoleSha256": SHA_B,
    "status": "pass",
}

PUBLICATION_CHECKS = [
    {
        "name": "release_shelf_serving",
        "ready": True,
        "status": "ready",
        "code": "verified_shelf_serving",
    },
    {
        "name": "publication_probe_contract",
        "ready": True,
        "status": "ready",
        "code": "required_probes_configured",
    },
    {
        "name": "activation_protocol",
        "ready": True,
        "status": "ready",
        "code": "activation_protocol_valid",
    },
    {
        "name": "release_storage_admission",
        "ready": True,
        "status": "ready",
        "code": "release_storage_admitted",
    },
]

PUBLICATION_PAYLOAD = {
    "ready": True,
    "checksConfigured": True,
    "status": "ready",
    "code": "publication_ready",
    "observedAt": TIMESTAMP,
    "generationId": "generation-1",
    "activationReceiptId": "receipt-1",
    "inventoryDigest": SHA_A,
    "checks": PUBLICATION_CHECKS,
}

READY_PAYLOAD = {
    "ready": True,
    "status": "ready",
    "generatedAt": TIMESTAMP,
    "hub": {
        "contractName": "chummer.run.api.deep_readiness.v2",
        "service": "chummer.run.api",
        "ready": True,
        "status": "pass",
        "servingReady": True,
        "publicationReady": True,
        "publicationChecksConfigured": True,
        "generatedAt": TIMESTAMP,
        "checks": [
            {
                "name": name,
                "passed": True,
                "status": "pass",
                "code": f"{name}_valid",
            }
            for name in (
                "data_protection_storage",
                "install_linking_store",
                "release_shelf",
                "canonical_release_manifest",
            )
        ],
        "releaseShelf": {
            "mode": "generation",
            "servingReady": True,
            "publicationReady": True,
            "publicationChecksConfigured": True,
            "status": "serving",
            "code": "generation_shelf_verified",
            "generationId": "generation-1",
            "activationReceiptId": "receipt-1",
            "inventoryDigest": SHA_A,
            "releaseVersion": "1.0.0",
            "channel": "stable",
            "publishedAt": TIMESTAMP,
            "publicationChecks": PUBLICATION_CHECKS,
        },
    },
    "playProjection": {
        "status": "disabled",
        "ready": True,
        "enabled": False,
        "detail": "Local install mirror is authoritative.",
    },
    "deploymentIdentity": {
        "ready": True,
        "code": "overlay_identity_bound",
        "sourceFingerprintSha256": SHA_A,
        "fullDeploymentDigestSha256": SHA_B,
    },
}


class ProbeHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    status = 200
    content_type = "application/json; charset=utf-8"
    body = b"{}"
    omit_content_length = False
    requests: list[tuple[str, str, str | None]] = []

    def do_GET(self) -> None:
        type(self).requests.append(
            (self.path, self.request_version, self.headers.get("Host"))
        )
        self.send_response(type(self).status)
        self.send_header("Content-Type", type(self).content_type)
        if type(self).omit_content_length:
            self.send_header("Connection", "close")
        else:
            self.send_header("Content-Length", str(len(type(self).body)))
        self.end_headers()
        self.wfile.write(type(self).body)
        if type(self).omit_content_length:
            self.close_connection = True

    def log_message(self, _format: str, *_args: object) -> None:
        return


class ReusableThreadingHttpServer(http.server.ThreadingHTTPServer):
    allow_reuse_address = True


class LoopbackProbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not ASSEMBLY.is_file():
            raise RuntimeError(f"probe assembly not found: {ASSEMBLY}")
        cls.server = ReusableThreadingHttpServer(
            ("127.0.0.1", 8080),
            ProbeHandler,
        )
        cls.thread = threading.Thread(
            target=cls.server.serve_forever,
            daemon=True,
        )
        cls.thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def setUp(self) -> None:
        ProbeHandler.status = 200
        ProbeHandler.content_type = "application/json; charset=utf-8"
        ProbeHandler.body = b"{}"
        ProbeHandler.omit_content_length = False
        ProbeHandler.requests = []

    def invoke(self, path: str) -> subprocess.CompletedProcess[str]:
        environment = dict(os.environ)
        environment.update(
            {
                "HTTP_PROXY": "http://127.0.0.1:1",
                "HTTPS_PROXY": "http://127.0.0.1:1",
                "ALL_PROXY": "http://127.0.0.1:1",
                "NO_PROXY": "",
            }
        )
        return subprocess.run(
            ["dotnet", str(ASSEMBLY), path],
            check=False,
            capture_output=True,
            cwd=PROJECT_DIR,
            env=environment,
            text=True,
            timeout=10,
        )

    def serve_json(self, payload: object) -> None:
        ProbeHandler.body = json.dumps(
            payload,
            separators=(",", ":"),
        ).encode("utf-8")

    def test_accepts_exact_install_linking_authority_contract(self) -> None:
        self.serve_json(AUTHORITY_PAYLOAD)
        expected_body = ProbeHandler.body

        result = self.invoke("/api/ready/install-linking-authority")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.encode("utf-8"), expected_body)
        self.assertEqual(
            ProbeHandler.requests,
            [
                (
                    "/api/ready/install-linking-authority",
                    "HTTP/1.1",
                    "chummer.run",
                )
            ],
        )

    def test_accepts_exact_publication_contract(self) -> None:
        self.serve_json(PUBLICATION_PAYLOAD)
        expected_body = ProbeHandler.body
        result = self.invoke("/api/ready/publication")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.encode("utf-8"), expected_body)

    def test_accepts_exact_deep_readiness_contract(self) -> None:
        self.serve_json(READY_PAYLOAD)
        expected_body = ProbeHandler.body
        result = self.invoke("/api/ready")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.encode("utf-8"), expected_body)

    def test_rejects_unknown_path_before_network_request(self) -> None:
        result = self.invoke("/api/ready/../health")
        self.assertEqual(result.returncode, 64)
        self.assertEqual(result.stdout, "")
        self.assertEqual(ProbeHandler.requests, [])

    def test_rejects_missing_or_additional_response_fields(self) -> None:
        for mutation in ("missing", "additional"):
            with self.subTest(mutation=mutation):
                payload = copy.deepcopy(AUTHORITY_PAYLOAD)
                if mutation == "missing":
                    del payload["leastPrivilegeValid"]
                else:
                    payload["unexpected"] = True
                self.serve_json(payload)
                result = self.invoke(
                    "/api/ready/install-linking-authority"
                )
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stdout, "")

    def test_rejects_non_success_semantics(self) -> None:
        payload = copy.deepcopy(AUTHORITY_PAYLOAD)
        payload["ready"] = False
        self.serve_json(payload)
        result = self.invoke("/api/ready/install-linking-authority")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")

    def test_rejects_wrong_status_content_type_and_http_version(self) -> None:
        cases = (
            ("status", 503, "application/json; charset=utf-8", "HTTP/1.1"),
            ("media_type", 200, "text/json; charset=utf-8", "HTTP/1.1"),
            ("charset", 200, "application/json", "HTTP/1.1"),
            ("http_version", 200, "application/json; charset=utf-8", "HTTP/1.0"),
        )
        for name, status, content_type, protocol_version in cases:
            with self.subTest(case=name):
                ProbeHandler.status = status
                ProbeHandler.content_type = content_type
                ProbeHandler.protocol_version = protocol_version
                self.serve_json(AUTHORITY_PAYLOAD)
                result = self.invoke(
                    "/api/ready/install-linking-authority"
                )
                self.assertEqual(result.returncode, 1)
                ProbeHandler.protocol_version = "HTTP/1.1"

    def test_rejects_redirect_without_following_it(self) -> None:
        ProbeHandler.status = 302
        ProbeHandler.body = b"{}"
        result = self.invoke("/api/ready")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(len(ProbeHandler.requests), 1)

    def test_rejects_streamed_response_over_256_kib(self) -> None:
        ProbeHandler.omit_content_length = True
        ProbeHandler.body = b" " * ((256 * 1024) + 1)
        result = self.invoke("/api/ready")
        self.assertEqual(result.returncode, 1)


if __name__ == "__main__":
    unittest.main()
