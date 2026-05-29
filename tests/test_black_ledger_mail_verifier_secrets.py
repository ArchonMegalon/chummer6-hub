from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATHS = [
    REPO_ROOT / "scripts" / "verify_black_ledger_tibor_mailbox_delivery.py",
    REPO_ROOT / "scripts" / "verify_black_ledger_inbox_and_mail_rollout.py",
]


class BlackLedgerMailVerifierSecretTests(unittest.TestCase):
    def test_mail_verifiers_require_env_backed_emailit_key(self) -> None:
        for script_path in SCRIPT_PATHS:
            script_text = script_path.read_text(encoding="utf-8")
            self.assertIn("IDENTITY_EMAILIT_API_KEY", script_text, msg=str(script_path))
            self.assertIn(
                'raise RuntimeError("IDENTITY_EMAILIT_API_KEY is missing")',
                script_text,
                msg=str(script_path),
            )

    def test_mail_verifiers_do_not_hardcode_provider_secret(self) -> None:
        for script_path in SCRIPT_PATHS:
            script_text = script_path.read_text(encoding="utf-8")
            self.assertNotIn('EMAILIT_API_KEY = "secret_', script_text, msg=str(script_path))
            self.assertNotIn("api.emailit.com/v1/emails", script_text.split("headers =")[0], msg=str(script_path))


if __name__ == "__main__":
    unittest.main()
