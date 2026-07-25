from __future__ import annotations

import subprocess
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
HELPER = REPO_ROOT / "scripts" / "ai" / "_external_artifact_blockers.sh"


class VerifyExternalArtifactBlockerTests(unittest.TestCase):
    def run_shell(self, script: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", "-c", script, "verify-external-artifact-test", str(HELPER)],
            cwd=REPO_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

    def test_expected_wait_continues_then_fails_release_at_final_boundary(self) -> None:
        result = self.run_shell(
            """
source "$1"
waiting_gate() {
  echo "native_visual_auto_import:waiting"
  return 2
}
run_expected_external_artifact_gate \
  "native Windows visual proof is required" \
  "native_visual_auto_import:waiting" \
  waiting_gate
echo "later-local-gate-ran"
fail_on_external_release_blockers
"""
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("later-local-gate-ran", result.stdout)
        self.assertIn("native_visual_auto_import:waiting", result.stderr)
        self.assertIn("release remains blocked by 1 external artifact", result.stderr)
        self.assertIn("native Windows visual proof is required", result.stderr)

    def test_unexpected_failure_is_not_reclassified_as_external_wait(self) -> None:
        result = self.run_shell(
            """
source "$1"
broken_gate() {
  echo "native_visual_auto_import:corrupt" >&2
  return 7
}
run_expected_external_artifact_gate \
  "native Windows visual proof is required" \
  "native_visual_auto_import:waiting" \
  broken_gate
"""
        )

        self.assertEqual(result.returncode, 7)
        self.assertIn("native_visual_auto_import:corrupt", result.stderr)
        self.assertNotIn("release remains blocked", result.stderr)

    def test_successful_gate_keeps_final_boundary_green(self) -> None:
        result = self.run_shell(
            """
source "$1"
passing_gate() {
  echo "native_visual_auto_import:imported"
  return 0
}
run_expected_external_artifact_gate \
  "native Windows visual proof is required" \
  "native_visual_auto_import:waiting" \
  passing_gate
fail_on_external_release_blockers
"""
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("native_visual_auto_import:imported", result.stdout)
        self.assertNotIn("release remains blocked", result.stderr)
