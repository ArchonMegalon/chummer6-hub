from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "verify_account_handoff_runtime_config.py"


def load_module():
    spec = importlib.util.spec_from_file_location("verify_account_handoff_runtime_config", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AccountHandoffRuntimeConfigTests(unittest.TestCase):
    def test_unavailable_billing_and_default_release_upload_passes(self) -> None:
        module = load_module()
        env = {}
        with mock.patch.dict("os.environ", env, clear=True):
            payload = module.build_payload()

        self.assertEqual(payload["status"], "pass")
        self.assertEqual(payload["billing"]["mode"], "unavailable")
        self.assertEqual(payload["release_upload"]["mode"], "default_single_operator")
        self.assertEqual(
            payload["release_upload"]["effective_allowed_emails"],
            ["tibor.girschele@gmail.com"],
        )

    def test_configured_billing_and_release_upload_allowlist_passes(self) -> None:
        module = load_module()
        env = {
            "BRILLIANT_DIRECTORIES_SUPPORTER_PLAN_URL": "https://billing.example.test/supporter",
            "BRILLIANT_DIRECTORIES_MEMBER_PORTAL_URL": "https://billing.example.test/manage",
            "BRILLIANT_DIRECTORIES_CHECKOUT_USER_ID_PARAMETER": "external_user",
            "BRILLIANT_DIRECTORIES_CHECKOUT_EMAIL_PARAMETER": "contact",
            "BRILLIANT_DIRECTORIES_CHECKOUT_PLAN_PARAMETER": "membership_plan",
            "CHUMMER_RELEASE_UPLOAD_ALLOWED_EMAILS": "archon.megalon@gmail.com, tibor.girschele@gmail.com",
        }
        with mock.patch.dict("os.environ", env, clear=True):
            payload = module.build_payload()

        self.assertEqual(payload["status"], "pass")
        self.assertEqual(payload["billing"]["mode"], "external_handoff_configured")
        self.assertEqual(payload["release_upload"]["mode"], "configured_allowlist")
        self.assertEqual(payload["release_upload"]["configured_allowed_email_count"], 2)

    def test_required_live_billing_fails_when_handoff_is_unavailable(self) -> None:
        module = load_module()
        env = {
            "CHUMMER_REQUIRE_BRILLIANT_DIRECTORIES_CHECKOUT": "1",
        }
        with mock.patch.dict("os.environ", env, clear=True):
            payload = module.build_payload()

        self.assertEqual(payload["status"], "fail")
        self.assertTrue(payload["billing"]["checkout_live_required"])
        self.assertIn("billing checkout is required for this release", " ".join(payload["failures"]))

    def test_required_live_billing_passes_when_handoff_is_configured(self) -> None:
        module = load_module()
        env = {
            "CHUMMER_REQUIRE_BRILLIANT_DIRECTORIES_CHECKOUT": "1",
            "BRILLIANT_DIRECTORIES_SUPPORTER_PLAN_URL": "https://billing.example.test/supporter",
            "BRILLIANT_DIRECTORIES_MEMBER_PORTAL_URL": "https://billing.example.test/manage",
            "BRILLIANT_DIRECTORIES_CHECKOUT_USER_ID_PARAMETER": "external_user",
            "BRILLIANT_DIRECTORIES_CHECKOUT_EMAIL_PARAMETER": "contact",
            "BRILLIANT_DIRECTORIES_CHECKOUT_PLAN_PARAMETER": "membership_plan",
        }
        with mock.patch.dict("os.environ", env, clear=True):
            payload = module.build_payload()

        self.assertEqual(payload["status"], "pass")
        self.assertEqual(payload["billing"]["mode"], "external_handoff_configured")
        self.assertTrue(payload["billing"]["checkout_live_required"])

    def test_partial_billing_config_fails(self) -> None:
        module = load_module()
        env = {
            "BRILLIANT_DIRECTORIES_SUPPORTER_PLAN_URL": "https://billing.example.test/supporter",
            "BRILLIANT_DIRECTORIES_CHECKOUT_USER_ID_PARAMETER": "external_user",
            "BRILLIANT_DIRECTORIES_CHECKOUT_EMAIL_PARAMETER": "contact",
            "BRILLIANT_DIRECTORIES_CHECKOUT_PLAN_PARAMETER": "membership_plan",
        }
        with mock.patch.dict("os.environ", env, clear=True):
            payload = module.build_payload()

        self.assertEqual(payload["status"], "fail")
        self.assertIn("billing handoff config is partial", " ".join(payload["failures"]))

    def test_release_upload_allowlist_must_include_tibor(self) -> None:
        module = load_module()
        env = {
            "CHUMMER_RELEASE_UPLOAD_ALLOWED_EMAILS": "archon.megalon@gmail.com",
        }
        with mock.patch.dict("os.environ", env, clear=True):
            payload = module.build_payload()

        self.assertEqual(payload["status"], "fail")
        self.assertIn("must include tibor.girschele@gmail.com", " ".join(payload["failures"]))

    def test_main_writes_outputs(self) -> None:
        module = load_module()
        payload = {
            "generated_at_utc": "2026-06-28T12:00:00Z",
            "status": "pass",
            "verdict": "READY",
            "failures": [],
            "billing": {"mode": "unavailable"},
            "release_upload": {"mode": "default_single_operator"},
        }
        with tempfile.TemporaryDirectory(prefix="account-handoff-config-") as temp_dir:
            output_root = Path(temp_dir)
            with mock.patch.object(module, "OUTPUT_JSON", output_root / "ACCOUNT_HANDOFF_RUNTIME_CONFIG.generated.json"), \
                mock.patch.object(module, "OUTPUT_MD", output_root / "ACCOUNT_HANDOFF_RUNTIME_CONFIG.md"), \
                mock.patch.object(module, "build_payload", return_value=payload):
                result = module.main()

            self.assertEqual(result, 0)
            receipt = json.loads((output_root / "ACCOUNT_HANDOFF_RUNTIME_CONFIG.generated.json").read_text(encoding="utf-8"))
            self.assertEqual(receipt["status"], "pass")
            self.assertTrue((output_root / "ACCOUNT_HANDOFF_RUNTIME_CONFIG.md").is_file())


if __name__ == "__main__":
    unittest.main()
