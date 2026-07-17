from __future__ import annotations

import os
import shutil
import subprocess
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


class RunServicesRestoreDrillFailClosedTests(unittest.TestCase):
    def test_root_release_ready_wrapper_runs_restore_drill_directly(self) -> None:
        wrapper = ROOT_RELEASE_READY_WRAPPER_PATH.read_text(encoding="utf-8")
        direct_gate = (
            '"verify_run_services_restore_drill:cd $root/chummer.run-services '
            '&& bash scripts/ai/run_services_restore_drill.sh"'
        )

        self.assertIn(direct_gate, wrapper)
        self.assertNotIn(
            "verify_run_services_restore_drill:cd $root/chummer.run-services "
            "&& CHUMMER_SKIP_CLEANROOM_BUILD=1",
            wrapper,
        )

    def test_root_release_ready_wrapper_runs_bundle_transaction_gate_after_restore(self) -> None:
        wrapper = ROOT_RELEASE_READY_WRAPPER_PATH.read_text(encoding="utf-8")
        restore_gate = (
            '"verify_run_services_restore_drill:cd $root/chummer.run-services '
            '&& bash scripts/ai/run_services_restore_drill.sh"'
        )
        transaction_gate = (
            '"verify_release_bundle_transaction:cd $root/chummer.run-services '
            '&& bash scripts/verify_release_bundle_transaction_gate.sh"'
        )
        release_channel_gate = (
            '"verify_release_channel:bash '
            '$root/chummer-hub-registry/scripts/release/verify_release_channel.sh"'
        )

        self.assertIn(transaction_gate, wrapper)
        self.assertLess(wrapper.index(restore_gate), wrapper.index(transaction_gate))
        self.assertLess(wrapper.index(transaction_gate), wrapper.index(release_channel_gate))

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
