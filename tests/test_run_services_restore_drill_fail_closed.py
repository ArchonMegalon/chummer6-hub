from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "ai"
    / "run_services_restore_drill.sh"
)
VERIFY_SCRIPT_PATH = SCRIPT_PATH.with_name("verify.sh")
RELEASE_READY_MATERIALIZER_PATH = (
    SCRIPT_PATH.parents[2] / "scripts" / "materialize_release_ready_receipt.py"
)


def canonical_release_gate_specs():  # noqa: ANN201
    name = "release_ready_materializer_for_restore_drill_test"
    spec = importlib.util.spec_from_file_location(name, RELEASE_READY_MATERIALIZER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    environment = {key: "" for key in module.RELEASE_EXECUTION_ENV_KEYS}
    environment.update(
        {
            "CHUMMER_PUBLIC_BASE_URL": "https://chummer.run",
            "CHUMMER_PUBLIC_EDGE_EXPECTED_HEAD": "a" * 40,
            "CHUMMER_RUN_SERVICES_ROOT": str(module.RUN_SERVICES_ROOT),
            "CHUMMER_BLAZOR_REQUIRE_LOCAL_E2E": "0",
            "CHUMMER_BLAZOR_REQUIRE_SELF_HOST_E2E": "0",
            "CHUMMER_RELEASE_READY_SKIP_GOOGLE_OAUTH_RUNTIME_REFRESH": "0",
            "CHUMMER_RELEASE_READY_SKIP_WINDOWS_RUNTIME_REFRESH": "0",
            "CHUMMER_RELEASE_READY_GATE_TIMEOUT_SECONDS": "900",
            "CHUMMER_RELEASE_READY_GUIDE_GATE_TIMEOUT_SECONDS": "1800",
            "CHUMMER_RELEASE_READY_GATE_KILL_AFTER_SECONDS": "30",
            "CHUMMER_PUBLIC_EDGE_PLAYWRIGHT_REUSE_MAX_AGE_HOURS": "24",
            "CHUMMER_PUBLIC_EDGE_TIMEOUT_SECONDS": "60",
            "PATH": module.TRUSTED_PATH,
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1",
        }
    )
    validated = module.validate_release_execution_environment(environment)
    return module, module.canonical_release_gate_specs(validated)


class RunServicesRestoreDrillFailClosedTests(unittest.TestCase):
    def test_release_controller_runs_restore_drill_directly(self) -> None:
        module, specs = canonical_release_gate_specs()
        restore = next(
            value for value in specs if value["name"] == "verify_run_services_restore_drill"
        )
        entrypoint = module.RUN_SERVICES_ROOT / "scripts" / "ai" / "run_services_restore_drill.sh"

        self.assertEqual((str(entrypoint),), restore["entrypoints"])
        self.assertEqual(
            f"cd {module.RUN_SERVICES_ROOT} && {module.TRUSTED_BASH} {entrypoint}",
            restore["command"],
        )
        self.assertNotIn("CHUMMER_SKIP_CLEANROOM_BUILD", str(restore["command"]))

    def test_release_controller_runs_bundle_transaction_gate_after_restore(self) -> None:
        module, specs = canonical_release_gate_specs()
        names = [str(value["name"]) for value in specs]
        transaction = next(
            value for value in specs if value["name"] == "verify_release_bundle_transaction"
        )
        shell_gate = module.RUN_SERVICES_ROOT / "scripts" / "verify_release_bundle_transaction_gate.sh"
        trx_verifier = module.RUN_SERVICES_ROOT / "scripts" / "verify_release_bundle_transaction_trx.py"

        self.assertEqual((str(shell_gate), str(trx_verifier)), transaction["entrypoints"])
        self.assertIn(str(shell_gate), str(transaction["command"]))
        self.assertIn(str(trx_verifier), str(transaction["command"]))
        self.assertLess(
            names.index("verify_run_services_restore_drill"),
            names.index("verify_release_bundle_transaction"),
        )
        self.assertLess(
            names.index("verify_release_bundle_transaction"),
            names.index("verify_release_channel"),
        )

    def test_shared_verifier_runs_restore_drill_and_regression_contract(self) -> None:
        verifier = VERIFY_SCRIPT_PATH.read_text(encoding="utf-8")

        regression_test = (
            "python3 -m unittest discover -s \"$ROOT_DIR/tests\" "
            "-p 'test_run_services_restore_drill_fail_closed.py' >/dev/null"
        )
        restore_drill = "bash scripts/ai/run_services_restore_drill.sh"
        self.assertIn(regression_test, verifier)
        self.assertIn(restore_drill, verifier)
        self.assertLess(verifier.index(regression_test), verifier.index(restore_drill))

    def test_missing_required_artifacts_fail_the_restore_drill(self) -> None:
        with tempfile.TemporaryDirectory(prefix="run-services-restore-drill-") as temp_dir:
            root = Path(temp_dir)
            copied_script = root / "scripts" / "ai" / SCRIPT_PATH.name
            copied_script.parent.mkdir(parents=True)
            shutil.copy2(SCRIPT_PATH, copied_script)

            env = os.environ.copy()
            env["CHUMMER_SKIP_CLEANROOM_BUILD"] = "1"
            completed = subprocess.run(
                ["bash", str(copied_script)],
                cwd=root,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertNotEqual(0, completed.returncode)
        self.assertEqual("", completed.stdout)
        self.assertIn("restore drill blocked", completed.stderr)
        self.assertIn(
            "Chummer.Play.Contracts/bin/Debug/net10.0/Chummer.Play.Contracts.dll",
            completed.stderr,
        )
        self.assertNotIn("skip restore drill", completed.stderr)


if __name__ == "__main__":
    unittest.main()
