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
ROOT_RELEASE_READY_WRAPPER_PATH = (
    SCRIPT_PATH.parents[3] / "scripts" / "release" / "verify_chummer6_release_ready.sh"
)
RELEASE_READY_CONTROLLER_PATH = (
    SCRIPT_PATH.parents[1] / "materialize_release_ready_receipt.py"
)


def load_release_ready_controller():
    spec = importlib.util.spec_from_file_location(
        "restore_drill_release_ready_controller",
        RELEASE_READY_CONTROLLER_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class RunServicesRestoreDrillFailClosedTests(unittest.TestCase):
    def test_root_release_ready_wrapper_delegates_to_isolated_controller(self) -> None:
        launcher = ROOT_RELEASE_READY_WRAPPER_PATH.read_text(encoding="utf-8")

        self.assertTrue(launcher.startswith("#!/usr/bin/python3 -I\n"))
        self.assertIn(
            'MATERIALIZER = ROOT / "chummer.run-services/scripts/'
            'materialize_release_ready_receipt.py"',
            launcher,
        )
        self.assertIn("os.execve(", launcher)
        self.assertIn('            "-I",', launcher)
        self.assertIn('            "--run-authoritative-controller",', launcher)
        self.assertNotIn(
            "verify_run_services_restore_drill:cd $root/chummer.run-services "
            "&& CHUMMER_SKIP_CLEANROOM_BUILD=1",
            launcher,
        )

    def test_controller_runs_bundle_transaction_gate_after_restore(self) -> None:
        controller = load_release_ready_controller()
        environment = {
            "CHUMMER_PUBLIC_BASE_URL": "https://chummer.run",
            "CHUMMER_BLAZOR_REQUIRE_LOCAL_E2E": "0",
            "CHUMMER_BLAZOR_REQUIRE_SELF_HOST_E2E": "0",
            "CHUMMER_RELEASE_READY_SKIP_GOOGLE_OAUTH_RUNTIME_REFRESH": "0",
            "CHUMMER_RELEASE_READY_SKIP_WINDOWS_RUNTIME_REFRESH": "0",
            "CHUMMER_RELEASE_READY_GATE_TIMEOUT_SECONDS": "900",
            "CHUMMER_RELEASE_READY_GUIDE_GATE_TIMEOUT_SECONDS": "1800",
            "CHUMMER_PUBLIC_EDGE_PLAYWRIGHT_REUSE_MAX_AGE_HOURS": "24",
            "CHUMMER_PUBLIC_EDGE_TIMEOUT_SECONDS": "60",
        }
        gates = controller.canonical_release_gate_specs(environment)
        names = [str(gate["name"]) for gate in gates]
        by_name = {str(gate["name"]): gate for gate in gates}
        services = str(controller.RUN_SERVICES_ROOT)
        bash = str(controller.TRUSTED_BASH)

        self.assertEqual(
            f"cd {services} && {bash} "
            f"{services}/scripts/ai/run_services_restore_drill.sh",
            by_name["verify_run_services_restore_drill"]["command"],
        )
        self.assertEqual(
            f"cd {services} && {bash} "
            f"{services}/scripts/verify_release_bundle_transaction_gate.sh",
            by_name["verify_release_bundle_transaction"]["command"],
        )
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
