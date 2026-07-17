from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest import mock


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "materialize_participate_billing_honesty.py"


def load_module():
    spec = importlib.util.spec_from_file_location("materialize_participate_billing_honesty", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _DummyContext:
    def __init__(self, **attrs):
        self.__dict__.update(attrs)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return None


class MaterializeParticipateBillingHonestyTests(unittest.TestCase):
    def test_materialize_runs_both_runtime_states_and_writes_aggregate_receipt(self) -> None:
        module = load_module()

        with tempfile.TemporaryDirectory(prefix="materialize-participate-billing-") as temp_dir:
            completion_dir = Path(temp_dir)

            def fake_run_playwright(node_runner: str, spec_path: str, env: dict[str, str]) -> None:
                if spec_path.endswith("participate-billing-auth.spec.ts"):
                    (completion_dir / "PARTICIPATE_BILLING_AUTH_E2E.generated.json").write_text(
                        json.dumps(
                            {
                                "status": "pass",
                                "signed_in_participate_first_party_verified": True,
                                "signed_in_supporter_checkout_location": "https://billing.example.test/supporter?membership_plan=supporter",
                            }
                        )
                        + "\n",
                        encoding="utf-8",
                    )
                elif spec_path.endswith("participate-billing-unavailable.spec.ts"):
                    (completion_dir / "PARTICIPATE_BILLING_UNAVAILABLE_E2E.generated.json").write_text(
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
                else:  # pragma: no cover - defensive
                    raise AssertionError(spec_path)

            with mock.patch.object(module, "TokenIdentityStub", return_value=_DummyContext(access_token="token", base_url="http://identity")):
                with mock.patch.object(module, "StaticHtmlStub", return_value=_DummyContext(base_url="http://board")):
                    with mock.patch.object(module, "LocalHubApp", side_effect=[
                        _DummyContext(base_url="http://configured-app"),
                        _DummyContext(base_url="http://unavailable-app"),
                    ]):
                        with mock.patch.object(module, "run_playwright", side_effect=fake_run_playwright) as run_mock:
                            payload = module.materialize(completion_dir, "npx")

            self.assertEqual(payload["status"], "pass")
            self.assertEqual(run_mock.call_count, 2)
            self.assertEqual(payload["materializer_source_digest"], module.compute_materializer_source_digest())
            self.assertTrue((completion_dir / "PARTICIPATE_BILLING_HONESTY.generated.json").is_file())
            self.assertTrue((completion_dir / "PARTICIPATE_BILLING_HONESTY.md").is_file())

    def test_materialize_can_reuse_fresh_existing_receipts_when_source_digest_matches(self) -> None:
        module = load_module()

        with tempfile.TemporaryDirectory(prefix="materialize-participate-billing-reuse-") as temp_dir:
            completion_dir = Path(temp_dir)
            digest = module.compute_materializer_source_digest()
            now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
            (completion_dir / "PARTICIPATE_BILLING_AUTH_E2E.generated.json").write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "generated_at_utc": now,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (completion_dir / "PARTICIPATE_BILLING_UNAVAILABLE_E2E.generated.json").write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "generated_at_utc": now,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (completion_dir / "PARTICIPATE_BILLING_HONESTY.generated.json").write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "verdict": "READY",
                        "generated_at_utc": now,
                        "materializer_source_digest": digest,
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            with mock.patch.object(module, "run_playwright", side_effect=AssertionError("Playwright should not run")):
                payload = module.materialize(
                    completion_dir,
                    "npx",
                    reuse_existing_receipts=True,
                )

            self.assertEqual(payload["status"], "pass")
            self.assertEqual(payload["materializer_source_digest"], digest)

    def test_materialize_reruns_when_existing_receipts_are_stale(self) -> None:
        module = load_module()

        with tempfile.TemporaryDirectory(prefix="materialize-participate-billing-stale-") as temp_dir:
            completion_dir = Path(temp_dir)
            digest = module.compute_materializer_source_digest()
            stale = (datetime.now(UTC) - timedelta(hours=48)).isoformat().replace("+00:00", "Z")
            now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
            (completion_dir / "PARTICIPATE_BILLING_AUTH_E2E.generated.json").write_text(
                json.dumps({"status": "pass", "generated_at_utc": stale}) + "\n",
                encoding="utf-8",
            )
            (completion_dir / "PARTICIPATE_BILLING_UNAVAILABLE_E2E.generated.json").write_text(
                json.dumps({"status": "pass", "generated_at_utc": stale}) + "\n",
                encoding="utf-8",
            )
            (completion_dir / "PARTICIPATE_BILLING_HONESTY.generated.json").write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "verdict": "READY",
                        "generated_at_utc": stale,
                        "materializer_source_digest": digest,
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            def fake_run_playwright(node_runner: str, spec_path: str, env: dict[str, str]) -> None:
                if spec_path.endswith("participate-billing-auth.spec.ts"):
                    (completion_dir / "PARTICIPATE_BILLING_AUTH_E2E.generated.json").write_text(
                        json.dumps(
                            {
                                "status": "pass",
                                "generated_at_utc": now,
                                "signed_in_participate_first_party_verified": True,
                                "signed_in_supporter_checkout_location": "https://billing.example.test/supporter?membership_plan=supporter",
                            }
                        )
                        + "\n",
                        encoding="utf-8",
                    )
                elif spec_path.endswith("participate-billing-unavailable.spec.ts"):
                    (completion_dir / "PARTICIPATE_BILLING_UNAVAILABLE_E2E.generated.json").write_text(
                        json.dumps(
                            {
                                "status": "pass",
                                "generated_at_utc": now,
                                "supporter_link_count": 0,
                                "supporter_copy_visible": False,
                            }
                        )
                        + "\n",
                        encoding="utf-8",
                    )
                else:  # pragma: no cover - defensive
                    raise AssertionError(spec_path)

            with mock.patch.object(module, "TokenIdentityStub", return_value=_DummyContext(access_token="token", base_url="http://identity")):
                with mock.patch.object(module, "StaticHtmlStub", return_value=_DummyContext(base_url="http://board")):
                    with mock.patch.object(module, "LocalHubApp", side_effect=[
                        _DummyContext(base_url="http://configured-app"),
                        _DummyContext(base_url="http://unavailable-app"),
                    ]):
                        with mock.patch.object(module, "run_playwright", side_effect=fake_run_playwright) as run_mock:
                            payload = module.materialize(
                                completion_dir,
                                "npx",
                                reuse_existing_receipts=True,
                            )

            self.assertEqual(payload["status"], "pass")
            self.assertEqual(run_mock.call_count, 2)
            self.assertEqual(payload["materializer_source_digest"], digest)


if __name__ == "__main__":
    unittest.main()
