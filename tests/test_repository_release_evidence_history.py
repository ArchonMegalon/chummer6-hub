from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PUBLISHED_ROOT = REPO_ROOT / ".codex-studio" / "published"
HISTORY_ROOT = REPO_ROOT / "release-evidence" / "history" / "run-20260701-124648"
GENERIC_NAMES = (
    "RELEASE_READY.generated.json",
    "OPERATOR_RELEASE_DASHBOARD.generated.json",
)


class RepositoryReleaseEvidenceHistoryTests(unittest.TestCase):
    def test_generic_receipts_are_non_authoritative_pointers(self) -> None:
        for name in GENERIC_NAMES:
            with self.subTest(name=name):
                pointer = json.loads((PUBLISHED_ROOT / name).read_text(encoding="utf-8"))
                self.assertEqual(
                    "chummer.hub.repository-release-evidence-pointer/v1",
                    pointer["contractName"],
                )
                self.assertEqual("not_runtime_authority", pointer["status"])
                self.assertEqual("run-20260701-124648", pointer["historicalReleaseVersion"])
                self.assertEqual(
                    f"release-evidence/history/run-20260701-124648/{name}",
                    pointer["historicalEvidencePath"],
                )
                self.assertNotIn("/tmp/", json.dumps(pointer))

    def test_historical_receipts_retain_the_original_release_identity(self) -> None:
        release_ready_bytes = (HISTORY_ROOT / "RELEASE_READY.generated.json").read_bytes()
        dashboard_bytes = (
            HISTORY_ROOT / "OPERATOR_RELEASE_DASHBOARD.generated.json"
        ).read_bytes()
        release_ready = json.loads(release_ready_bytes)
        dashboard = json.loads(dashboard_bytes)

        self.assertEqual("chummer.release_ready", release_ready["contract_name"])
        self.assertEqual("fail", release_ready["status"])
        self.assertEqual("chummer.operator_release_dashboard", dashboard["contract_name"])
        self.assertEqual("run-20260701-124648", dashboard["release"]["version"])
        self.assertEqual(
            "965d4089f8c536d5a80740e82d4f8eb9334c40eca1a6cdd421ea72c68337a62a",
            hashlib.sha256(release_ready_bytes).hexdigest(),
        )
        self.assertEqual(
            "853c042fb650289e09936f60445f72002a9d077bc68f6a225ff0b87fe88590f2",
            hashlib.sha256(dashboard_bytes).hexdigest(),
        )

    def test_generic_markdown_dashboard_is_also_an_explicit_pointer(self) -> None:
        pointer = (PUBLISHED_ROOT / "OPERATOR_RELEASE_DASHBOARD.md").read_text(
            encoding="utf-8"
        )
        historical = (HISTORY_ROOT / "OPERATOR_RELEASE_DASHBOARD.md").read_text(
            encoding="utf-8"
        )

        self.assertIn("# Not runtime authority", pointer)
        self.assertIn("release-evidence/history/run-20260701-124648", pointer)
        self.assertNotIn("NIGHTLY_HANDOFF_READY", pointer)
        self.assertIn("NIGHTLY_HANDOFF_READY", historical)
        self.assertEqual(
            "c28da4a30d862a99a88c2588f21df3649c43624fcad6d01e3add7f458833f505",
            hashlib.sha256(historical.encode("utf-8")).hexdigest(),
        )


if __name__ == "__main__":
    unittest.main()
