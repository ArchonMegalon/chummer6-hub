from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "materialize_operator_release_dashboard.py"


def load_module():
    spec = importlib.util.spec_from_file_location("materialize_operator_release_dashboard", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class OperatorReleaseDashboardParticipateBillingTests(unittest.TestCase):
    def test_dashboard_materializes_into_current_repo_published_root(self) -> None:
        module = load_module()

        self.assertEqual(SCRIPT_PATH.parents[1], module.RUN_SERVICES_ROOT)
        self.assertEqual(SCRIPT_PATH.parents[1] / ".codex-studio" / "published", module.PUBLISHED_ROOT)

    def test_dashboard_surfaces_participate_billing_honesty_gate(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="operator-dashboard-") as temp_dir:
            published = Path(temp_dir) / "published"
            published.mkdir(parents=True, exist_ok=True)
            completion = Path(temp_dir) / "completion"
            completion.mkdir(parents=True, exist_ok=True)
            registry = Path(temp_dir) / "registry"
            registry.mkdir(parents=True, exist_ok=True)

            receipts = {
                published / "EXTERNAL_DISTRIBUTION_MIRROR_PROOF.generated.json": {"status": "pass"},
                published / "RULESET_READINESS.generated.json": {"status": "pass", "rulesets": {}},
                published / "CHUMMER_PUBLIC_ROUTE_PROOF.generated.json": {"status": "pass", "base_url": "https://chummer.run"},
                completion / "UI_FRAME_INTEGRITY.generated.json": {"status": "pass", "base_url": "https://chummer.run", "summary": {"checked_pages": 1, "failure_count": 0}},
                published / "DESIGN_QUALITY_GATE.generated.json": {"status": "pass", "verdict": "READY"},
                published / "PUBLIC_COPY_LEAK_GATE.generated.json": {"status": "pass", "verdict": "READY"},
                published / "PARTICIPATE_BILLING_HONESTY.generated.json": {"status": "pass", "verdict": "READY"},
                published / "ACCOUNT_HANDOFF_RUNTIME_CONFIG.generated.json": {
                    "status": "pass",
                    "verdict": "READY",
                    "billing": {"mode": "external_handoff_configured"},
                    "release_upload": {"mode": "default_single_operator"},
                },
                published / "RELEASE_READY.generated.json": {"status": "pass", "verdict": "RELEASE_READY"},
                published / "FINAL_GOLD_JANITOR.generated.json": {"status": "pass", "verdict": "GOLD_READY"},
                published / "GOOGLE_OAUTH_LINKING_PROOF.generated.json": {"status": "pass"},
                registry / "RELEASE_CHANNEL.generated.json": {
                    "status": "published",
                    "version": "run-20260624-080000",
                    "publishedAt": "2026-06-24T08:00:00Z",
                    "channel": "stable",
                    "supportabilityState": "supported",
                },
            }
            for path, payload in receipts.items():
                path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

            with mock.patch.object(module, "PUBLISHED_ROOT", published), \
                mock.patch.object(module, "COMPLETION_ROOT", completion), \
                mock.patch.object(module, "REGISTRY_ROOT", registry):
                payload = module.build_payload()

        self.assertIn("participate_billing_honesty", payload["checks"])
        self.assertTrue(payload["checks"]["participate_billing_honesty"]["pass"])
        self.assertIn("account_handoff_runtime_config", payload["checks"])
        self.assertTrue(payload["checks"]["account_handoff_runtime_config"]["pass"])
        self.assertEqual(payload["account_handoffs"]["billing_mode"], "external_handoff_configured")


if __name__ == "__main__":
    unittest.main()
