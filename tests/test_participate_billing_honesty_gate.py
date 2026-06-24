from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "verify_participate_billing_honesty.py"


def load_module():
    spec = importlib.util.spec_from_file_location("verify_participate_billing_honesty", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ParticipateBillingHonestyGateTests(unittest.TestCase):
    def test_payload_passes_when_both_runtime_receipts_are_present(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="participate-billing-honesty-") as temp_dir:
            root = Path(temp_dir)
            (root / "PARTICIPATE_BILLING_AUTH_E2E.generated.json").write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "signed_in_participate_proxy_verified": True,
                        "signed_in_supporter_checkout_location": "https://billing.example.test/supporter?membership_plan=supporter",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (root / "PARTICIPATE_BILLING_UNAVAILABLE_E2E.generated.json").write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "supporter_link_count": 0,
                        "supporter_copy_visible": False,
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            payload = module.build_payload(root)
            self.assertEqual(payload["status"], "pass")
            self.assertEqual(payload["verdict"], "READY")

    def test_payload_fails_when_unavailable_state_still_shows_supporter_ui(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="participate-billing-honesty-") as temp_dir:
            root = Path(temp_dir)
            (root / "PARTICIPATE_BILLING_AUTH_E2E.generated.json").write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "signed_in_participate_proxy_verified": True,
                        "signed_in_supporter_checkout_location": "https://billing.example.test/supporter?membership_plan=supporter",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (root / "PARTICIPATE_BILLING_UNAVAILABLE_E2E.generated.json").write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "supporter_link_count": 1,
                        "supporter_copy_visible": True,
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            payload = module.build_payload(root)
            self.assertEqual(payload["status"], "fail")
            self.assertIn("still exposed supporter links", " ".join(payload["failures"]))

    def test_main_writes_receipt_and_report(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="participate-billing-honesty-") as temp_dir:
            root = Path(temp_dir)
            (root / "PARTICIPATE_BILLING_AUTH_E2E.generated.json").write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "signed_in_participate_proxy_verified": True,
                        "signed_in_supporter_checkout_location": "https://billing.example.test/supporter?membership_plan=supporter",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (root / "PARTICIPATE_BILLING_UNAVAILABLE_E2E.generated.json").write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "supporter_link_count": 0,
                        "supporter_copy_visible": False,
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            with mock.patch("sys.argv", ["verify_participate_billing_honesty.py", "--completion-dir", temp_dir]):
                result = module.main()
            self.assertEqual(result, 0)
            self.assertTrue((root / "PARTICIPATE_BILLING_HONESTY.generated.json").is_file())
            self.assertTrue((root / "PARTICIPATE_BILLING_HONESTY.md").is_file())


if __name__ == "__main__":
    unittest.main()
