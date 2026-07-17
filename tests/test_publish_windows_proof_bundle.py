from __future__ import annotations

import importlib.util
import io
import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from urllib.error import HTTPError
from urllib.request import Request


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "publish-windows-proof-bundle.py"
SPEC = importlib.util.spec_from_file_location("publish_windows_proof_bundle", SCRIPT_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"could not import {SCRIPT_PATH}")
UPLOADER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = UPLOADER
SPEC.loader.exec_module(UPLOADER)

FIXTURE_SCRIPT = SCRIPT_PATH.parents[1] / "tests" / "test_materialize_windows_proof_bundle.py"
FIXTURE_SPEC = importlib.util.spec_from_file_location(
    "windows_proof_uploader_fixture",
    FIXTURE_SCRIPT,
)
assert FIXTURE_SPEC is not None and FIXTURE_SPEC.loader is not None
FIXTURE = importlib.util.module_from_spec(FIXTURE_SPEC)
sys.modules[FIXTURE_SPEC.name] = FIXTURE
FIXTURE_SPEC.loader.exec_module(FIXTURE)


class FakeResponse:
    def __init__(self, payload: bytes = b"{}") -> None:
        self.payload = payload

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self, limit: int = -1) -> bytes:
        return self.payload if limit < 0 else self.payload[:limit]


class WindowsProofBundleContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        stage, _, _ = FIXTURE.make_stage(self.root)
        self.bundle = self.root / "bundle"
        result = FIXTURE.run_materializer(stage, self.bundle)
        if result.returncode != 0:
            raise AssertionError(result.stderr)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_accepts_only_the_eight_role_v2_governed_bundle(self) -> None:
        bundle = UPLOADER.validate_bundle(self.bundle)

        self.assertEqual("chummer.windows-proof.manifest/v2", bundle.manifest["schemaVersion"])
        self.assertEqual(8, len(bundle.files))
        self.assertEqual(
            UPLOADER.REQUIRED_KINDS,
            {artifact.kind for artifact in bundle.files},
        )

    def test_rejects_expired_manifest_before_opening_a_session(self) -> None:
        manifest_path = self.bundle / UPLOADER.MANIFEST_NAME
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["generatedAt"] = "2000-01-01T00:00:00Z"
        manifest["expiresAt"] = "2000-01-02T00:00:00Z"
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(ValueError, "expired"):
            UPLOADER.validate_bundle(self.bundle)

    def test_rejects_semantically_invalid_provenance_even_when_manifest_hash_is_updated(self) -> None:
        manifest_path = self.bundle / UPLOADER.MANIFEST_NAME
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        row = next(
            item
            for item in manifest["artifacts"]
            if item["kind"] == "build_provenance_receipt"
        )
        receipt_path = self.bundle / row["relativePath"]
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        state = receipt["invocation"]["state"]
        state["build_inputs"].pop()
        receipt["invocation"]["state_sha256"] = hashlib.sha256(
            json.dumps(state, separators=(",", ":"), sort_keys=True).encode()
        ).hexdigest()
        receipt_path.write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        row["size"] = receipt_path.stat().st_size
        row["sha256"] = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(ValueError, "exact Windows recipe set"):
            UPLOADER.validate_bundle(self.bundle)


class RecordingOpener:
    def __init__(self, payload: bytes = b"{}") -> None:
        self.payload = payload
        self.requests: list[Request] = []

    def open(self, request: Request, timeout: int) -> FakeResponse:
        self.requests.append(request)
        if timeout != 90:
            raise AssertionError("unexpected timeout")
        return FakeResponse(self.payload)


class ErrorOpener:
    def __init__(self, error: HTTPError) -> None:
        self.error = error

    def open(self, _request: Request, timeout: int) -> FakeResponse:
        if timeout != 90:
            raise AssertionError("unexpected timeout")
        raise self.error


class CloudflareAccessCredentialTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write_env(self, content: bytes, mode: int = 0o600, name: str = "access.env") -> Path:
        path = self.root / name
        path.write_bytes(content)
        path.chmod(mode)
        return path

    def test_accepts_exact_or_one_shared_prefixed_pair_without_repr_leak(self) -> None:
        exact = self.write_env(
            b"CF_ACCESS_CLIENT_ID=client-id\nCF_ACCESS_CLIENT_SECRET=client-secret\n",
            name="exact.env",
        )
        prefixed = self.write_env(
            b"CODEXLIZ_CF_ACCESS_CLIENT_ID=prefixed-id\n"
            b"CODEXLIZ_CF_ACCESS_CLIENT_SECRET=prefixed-secret\n",
            name="prefixed.env",
        )

        exact_credentials = UPLOADER.read_cf_access_env_file(exact)
        prefixed_credentials = UPLOADER.read_cf_access_env_file(prefixed)

        self.assertEqual("client-id", exact_credentials.client_id)
        self.assertEqual("client-secret", exact_credentials.client_secret)
        self.assertEqual("prefixed-id", prefixed_credentials.client_id)
        self.assertEqual("prefixed-secret", prefixed_credentials.client_secret)
        self.assertNotIn("client-secret", repr(exact_credentials))
        self.assertNotIn("prefixed-secret", repr(prefixed_credentials))

    def test_rejects_non_0600_mode(self) -> None:
        path = self.write_env(
            b"CF_ACCESS_CLIENT_ID=id\nCF_ACCESS_CLIENT_SECRET=secret\n",
            mode=0o640,
        )
        with self.assertRaisesRegex(ValueError, "exact mode 0600"):
            UPLOADER.read_cf_access_env_file(path)

    def test_rejects_wrong_owner(self) -> None:
        path = self.write_env(
            b"CF_ACCESS_CLIENT_ID=id\nCF_ACCESS_CLIENT_SECRET=secret\n"
        )
        with mock.patch.object(UPLOADER.os, "geteuid", return_value=os.geteuid() + 1):
            with self.assertRaisesRegex(ValueError, "owned by the current user"):
                UPLOADER.read_cf_access_env_file(path)

    def test_rejects_symlink(self) -> None:
        target = self.write_env(
            b"CF_ACCESS_CLIENT_ID=id\nCF_ACCESS_CLIENT_SECRET=secret\n",
            name="target.env",
        )
        link = self.root / "linked.env"
        link.symlink_to(target)
        with self.assertRaisesRegex(ValueError, "non-symlink regular file"):
            UPLOADER.read_cf_access_env_file(link)

    def test_rejects_duplicate_mixed_or_multiple_prefixes(self) -> None:
        cases = {
            "duplicate.env": (
                b"CF_ACCESS_CLIENT_ID=id\nCF_ACCESS_CLIENT_ID=other\n"
            ),
            "mixed.env": (
                b"CF_ACCESS_CLIENT_ID=id\n"
                b"CODEXLIZ_CF_ACCESS_CLIENT_SECRET=secret\n"
            ),
            "prefixes.env": (
                b"FIRST_CF_ACCESS_CLIENT_ID=id\n"
                b"SECOND_CF_ACCESS_CLIENT_SECRET=secret\n"
            ),
        }
        for name, content in cases.items():
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    UPLOADER.read_cf_access_env_file(self.write_env(content, name=name))

    def test_rejects_extra_malformed_empty_or_oversized_content(self) -> None:
        cases = {
            "extra.env": b"CF_ACCESS_CLIENT_ID=id\nNOT_ALLOWED=secret\n",
            "malformed.env": b"CF_ACCESS_CLIENT_ID=id\nCF_ACCESS_CLIENT_SECRET\n",
            "empty.env": b"CF_ACCESS_CLIENT_ID=id\nCF_ACCESS_CLIENT_SECRET=\n",
            "blank.env": b"CF_ACCESS_CLIENT_ID=id\n\nCF_ACCESS_CLIENT_SECRET=secret\n",
            "invalid-utf8.env": b"CF_ACCESS_CLIENT_ID=id\nCF_ACCESS_CLIENT_SECRET=\xff\n",
            "oversized.env": b"X" * (UPLOADER.MAX_CF_ACCESS_ENV_BYTES + 1),
        }
        for name, content in cases.items():
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    UPLOADER.read_cf_access_env_file(self.write_env(content, name=name))


class HttpCredentialPropagationTests(unittest.TestCase):
    def credentials(self) -> object:
        return UPLOADER.CfAccessCredentials("cf-client-id", "cf-client-secret")

    def test_access_headers_are_present_on_json_and_multipart_requests(self) -> None:
        client = UPLOADER.ProofHttpClient(
            UPLOADER.DEFAULT_SESSIONS_URL,
            "upload-ticket",
            cf_access_credentials=self.credentials(),
        )
        opener = RecordingOpener()
        client.opener = opener

        client.request_json("POST", client.sessions_url)
        client.multipart_file(
            f"{client.sessions_url}/{'a' * 32}/files",
            {"path": "proof/file.json"},
            "file",
            "file.json",
            b"{}",
        )

        self.assertEqual(2, len(opener.requests))
        for request in opener.requests:
            headers = {key.lower(): value for key, value in request.header_items()}
            self.assertEqual("Bearer upload-ticket", headers["authorization"])
            self.assertEqual("cf-client-id", headers["cf-access-client-id"])
            self.assertEqual("cf-client-secret", headers["cf-access-client-secret"])

    def test_redirect_handler_still_rejects_redirects(self) -> None:
        handler = UPLOADER.RejectRedirects()
        request = Request(UPLOADER.DEFAULT_SESSIONS_URL)
        with self.assertRaisesRegex(HTTPError, "redirects are forbidden"):
            handler.http_error_302(request, io.BytesIO(), 302, "Found", {})

    def test_server_problem_detail_redacts_every_credential(self) -> None:
        ticket = "upload-ticket-secret"
        credentials = UPLOADER.CfAccessCredentials("cf-client-id-secret", "cf-client-secret")
        payload = json.dumps(
            {
                "detail": (
                    f"reflected {ticket} {credentials.client_id} "
                    f"{credentials.client_secret}"
                )
            }
        ).encode()
        error = HTTPError(
            UPLOADER.DEFAULT_SESSIONS_URL,
            403,
            "Forbidden",
            {},
            io.BytesIO(payload),
        )
        client = UPLOADER.ProofHttpClient(
            UPLOADER.DEFAULT_SESSIONS_URL,
            ticket,
            cf_access_credentials=credentials,
        )
        client.opener = ErrorOpener(error)

        with self.assertRaises(ValueError) as caught:
            client.request_json("POST", client.sessions_url)

        message = str(caught.exception)
        self.assertNotIn(ticket, message)
        self.assertNotIn(credentials.client_id, message)
        self.assertNotIn(credentials.client_secret, message)
        self.assertIn("[redacted]", message)


class RecoveryReceiptRedactionTests(unittest.TestCase):
    def test_transition_never_persists_credential_material(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "receipt.json"
            receipt = {"schemaVersion": UPLOADER.RECEIPT_SCHEMA}
            forbidden = ("ticket-secret", "client-id-secret", "client-secret")
            UPLOADER.transition(
                path,
                receipt,
                "preflight",
                forbidden_values=forbidden,
            )
            before = path.read_bytes()
            self.assertTrue(all(value.encode() not in before for value in forbidden))

            with self.assertRaisesRegex(ValueError, "credential material"):
                UPLOADER.transition(
                    path,
                    receipt,
                    "completed",
                    forbidden_values=forbidden,
                    completion={"reflected": f"prefix-{forbidden[2]}-suffix"},
                )

            self.assertEqual(before, path.read_bytes())
            self.assertNotIn("completion", receipt)


if __name__ == "__main__":
    unittest.main()
