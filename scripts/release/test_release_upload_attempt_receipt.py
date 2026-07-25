from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace


MODULE_PATH = Path(__file__).with_name("release_upload_attempt_receipt.py")
SPEC = importlib.util.spec_from_file_location("release_upload_attempt_receipt", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
receipt_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(receipt_module)


def candidate() -> dict[str, object]:
    payload: dict[str, object] = {
        "version": "run-20260728-173651",
        "canonicalManifestSha256": "a" * 64,
        "inventorySha256": "b" * 64,
        "fileCount": 13,
        "totalBytes": 93_280_706,
    }
    material = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    payload["bundleIdentitySha256"] = hashlib.sha256(material).hexdigest()
    return payload


class ResumeCreatedReceiptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.summary = self.root / "summary.json"
        self.receipt = self.root / "receipt.json"
        self.summary.write_text(json.dumps(candidate()), encoding="utf-8")
        os.chmod(self.summary, 0o600)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write_receipt(
        self,
        *,
        state: str = "created",
        candidate_payload: dict[str, object] | None = None,
        expires_delta: timedelta = timedelta(hours=1),
    ) -> None:
        now = datetime.now(timezone.utc)
        payload = {
            "schemaVersion": receipt_module.SCHEMA_VERSION,
            "apiOrigin": "http://chummer.run:8091",
            "sessionId": "f" * 32,
            "expiresAtUtc": (now + expires_delta).isoformat().replace("+00:00", "Z"),
            "candidate": candidate_payload or candidate(),
            "completion": {
                "state": state,
                "requestStartedAtUtc": None,
                "lastUpdatedAtUtc": now.isoformat().replace("+00:00", "Z"),
                "lastHttpStatus": None,
                "lastProblemType": None,
                "traceId": None,
            },
            "stateHistory": [
                {"state": state, "atUtc": now.isoformat().replace("+00:00", "Z")}
            ],
        }
        self.receipt.write_text(json.dumps(payload), encoding="utf-8")
        os.chmod(self.receipt, 0o600)

    def validate(self) -> dict[str, str]:
        output = io.StringIO()
        with redirect_stdout(output):
            result = receipt_module.validate_resume_created(
                SimpleNamespace(
                    receipt=str(self.receipt),
                    summary=str(self.summary),
                    sessions_url="http://chummer.run:8091/api/internal/releases/upload-sessions",
                )
            )
        self.assertEqual(0, result)
        return json.loads(output.getvalue())

    def test_accepts_exact_pristine_created_receipt(self) -> None:
        self.write_receipt()

        result = self.validate()

        self.assertEqual("f" * 32, result["sessionId"])

    def test_rejects_non_created_or_expired_receipt(self) -> None:
        self.write_receipt(state="uploaded")
        with self.assertRaisesRegex(ValueError, "pristine created"):
            self.validate()

        self.write_receipt(expires_delta=timedelta(seconds=-1))
        with self.assertRaisesRegex(ValueError, "expired"):
            self.validate()

    def test_rejects_candidate_or_origin_mismatch(self) -> None:
        mismatched = candidate()
        mismatched["version"] = "different"
        identity_fields = {
            key: mismatched[key]
            for key in (
                "version",
                "canonicalManifestSha256",
                "inventorySha256",
                "fileCount",
                "totalBytes",
            )
        }
        mismatched["bundleIdentitySha256"] = hashlib.sha256(
            json.dumps(identity_fields, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        self.write_receipt(candidate_payload=mismatched)
        with self.assertRaisesRegex(ValueError, "candidate binding"):
            self.validate()

        self.write_receipt()
        with self.assertRaisesRegex(ValueError, "API origin"):
            receipt_module.validate_resume_created(
                SimpleNamespace(
                    receipt=str(self.receipt),
                    summary=str(self.summary),
                    sessions_url="https://chummer.run/api/internal/releases/upload-sessions",
                )
            )


if __name__ == "__main__":
    unittest.main()
