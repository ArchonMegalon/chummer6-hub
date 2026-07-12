from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "materialize_participate_billing_honesty.py"
VERIFY_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "ai" / "verify.sh"


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
    def test_playwright_uses_only_the_locked_local_npx_dependency(self) -> None:
        module = load_module()
        env = {"BASE_URL": "http://127.0.0.1:12345"}

        with mock.patch.object(module.subprocess, "run") as run_mock:
            module.run_playwright("npx", "tests/public/example.spec.ts", env)

        run_mock.assert_called_once_with(
            ["npx", "--no-install", "playwright", "test", "tests/public/example.spec.ts"],
            check=True,
            env=env,
        )

    def test_authoritative_verify_installs_lockfile_before_runtime_materialization(self) -> None:
        verify_script = VERIFY_SCRIPT_PATH.read_text(encoding="utf-8")
        install_command = "npm ci --ignore-scripts --no-audit --no-fund"
        materialize_command = 'python3 "$ROOT_DIR/scripts/materialize_participate_billing_honesty.py"'

        self.assertIn(install_command, verify_script)
        self.assertIn(materialize_command, verify_script)
        self.assertLess(verify_script.index(install_command), verify_script.index(materialize_command))

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
                    ]) as local_hub_mock:
                        with mock.patch.object(module, "run_playwright", side_effect=fake_run_playwright) as run_mock:
                            payload = module.materialize(completion_dir, "npx")

            self.assertEqual(payload["status"], "pass")
            self.assertEqual(run_mock.call_count, 2)
            self.assertEqual(local_hub_mock.call_count, 2)
            self.assertTrue(all(call.kwargs.get("no_build") is True for call in local_hub_mock.call_args_list))
            self.assertTrue((completion_dir / "PARTICIPATE_BILLING_HONESTY.generated.json").is_file())
            self.assertTrue((completion_dir / "PARTICIPATE_BILLING_HONESTY.md").is_file())


if __name__ == "__main__":
    unittest.main()
