from __future__ import annotations

import importlib.util
import os
import re
import subprocess
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "verify_workspace_restore_receipts.py"


class WorkspaceRestoreCommitResolutionTests(unittest.TestCase):
    def test_default_required_commits_include_closed_package_hardening_commit(self) -> None:
        script_text = SCRIPT.read_text(encoding="utf-8")

        self.assertIn('"80454b41"', script_text)
        self.assertIn('"e1f65c8b"', script_text)
        self.assertIn('"b72eaf89"', script_text)
        self.assertIn('"290ec61e"', script_text)
        self.assertIn('"1d11729a"', script_text)
        self.assertIn('"35db07af"', script_text)
        self.assertIn('"784fbcef"', script_text)
        self.assertIn('"5c8e5527"', script_text)
        self.assertIn('"bd398493"', script_text)
        self.assertIn('"a45d9e9e"', script_text)
        self.assertIn('"a002019a"', script_text)
        self.assertIn('"717af57e"', script_text)
        self.assertIn('"346c3ede"', script_text)
        self.assertIn('"8d59d95f"', script_text)
        self.assertIn('"1b8d9363"', script_text)
        self.assertIn('"e0521ca5"', script_text)
        self.assertIn('"06e2ec99"', script_text)
        self.assertIn('"cb560573"', script_text)
        self.assertIn('"7c92635e"', script_text)
        self.assertIn('"fcdd1fa5"', script_text)
        self.assertIn('"c90d02e0"', script_text)
        self.assertIn('"211ce4a1"', script_text)
        self.assertIn('"93182934"', script_text)
        self.assertIn('"021de48a"', script_text)
        self.assertIn('"5bf1a11e"', script_text)
        self.assertIn('"db002589"', script_text)
        self.assertIn('"f6db9d91"', script_text)
        self.assertIn('"b1270fd0"', script_text)
        self.assertIn('"691c625f"', script_text)
        self.assertIn('"f8226de9"', script_text)
        self.assertIn('"f8f3ce8e"', script_text)
        self.assertIn('"70b6f382"', script_text)
        self.assertIn('"0014a763"', script_text)
        self.assertIn('"d26e961c"', script_text)
        self.assertIn('"9f723c15"', script_text)
        self.assertIn('"7e908447"', script_text)
        self.assertIn('"2df21683"', script_text)
        self.assertIn('"442c76c2"', script_text)
        self.assertIn('"1f4f0e2e"', script_text)
        self.assertIn('"29f7ec9b"', script_text)
        self.assertIn('"46551461"', script_text)
        self.assertIn('"b4da7025"', script_text)
        self.assertIn('"af336c17"', script_text)
        self.assertIn('"aa61c498"', script_text)
        self.assertIn('"1b1c5427"', script_text)
        self.assertIn('"1d5a811f"', script_text)
        self.assertIn('"f02e985f"', script_text)
        self.assertIn('"0f06bcef"', script_text)
        self.assertIn('"1ca535e2"', script_text)
        self.assertIn('"25fb4391"', script_text)
        self.assertIn('"41c106c8"', script_text)
        self.assertIn('"b4bdc153"', script_text)
        self.assertIn('"1c98d6ba"', script_text)
        self.assertIn('"83bbc0d4"', script_text)
        self.assertIn('"1a0ba130"', script_text)
        self.assertIn('"63313972"', script_text)
        self.assertIn('"0b038324"', script_text)
        self.assertIn('"447f2a90"', script_text)
        self.assertIn('"a8f94a63"', script_text)
        self.assertIn('"06b0e574"', script_text)
        self.assertIn('"79764447"', script_text)
        self.assertIn('"2960fc91"', script_text)
        self.assertIn('"0f4a31d3"', script_text)
        self.assertIn('"d7788857"', script_text)
        self.assertIn('"8dcd8b46"', script_text)
        self.assertIn('"f5f414b0"', script_text)
        self.assertIn('"5e77a853"', script_text)
        self.assertIn('"23308c16"', script_text)
        self.assertIn('"2da59c68"', script_text)
        self.assertIn('"71e514b2"', script_text)
        self.assertIn('"e0d2bff6"', script_text)
        self.assertIn('"c6f628ef"', script_text)
        self.assertIn('"fa17ff4d"', script_text)
        self.assertIn('"72f96452"', script_text)
        self.assertIn('"664737cb"', script_text)
        self.assertIn('"138d84ef"', script_text)
        self.assertIn('"109face0"', script_text)
        self.assertIn('"28b9e40a"', script_text)
        self.assertIn('"f6cd760e"', script_text)
        self.assertIn('"03517936"', script_text)
        self.assertIn('"57da8fb3"', script_text)
        self.assertIn('"aa7d6b9a"', script_text)
        self.assertIn('"6add6cc6"', script_text)
        self.assertIn('"4487d01a"', script_text)
        self.assertIn('"9171e3f4"', script_text)
        self.assertIn('"a7e826d3"', script_text)
        self.assertIn('"d882db69"', script_text)
        self.assertIn('"db4fe453"', script_text)
        self.assertIn("commit fcdd1fa5 pins the current M105 workspace proof floor", script_text)
        self.assertIn("commit 021de48a requires the current M105 queue proof guard", script_text)
        self.assertIn("commit 5bf1a11e pins the current M105 workspace queue guard", script_text)
        self.assertIn("commit db002589 pins the M105 workspace queue guard proof", script_text)
        self.assertIn("commit f6db9d91 pins the M105 workspace proof floor", script_text)
        self.assertIn("commit b1270fd0 pins the M105 workspace verifier", script_text)
        self.assertIn("commit 691c625f requires the current M105 workspace proof floor", script_text)
        self.assertIn("commit f8226de9 pins the M105 workspace proof floor", script_text)
        self.assertIn("commit f8f3ce8e requires the latest M105 workspace proof floor", script_text)
        self.assertIn("commit 70b6f382 tightens the M105 served workspace proof guard", script_text)
        self.assertIn("commit 0014a763 tightens the M105 active-run proof marker guard", script_text)
        self.assertIn("commit d26e961c tightens the M105 workspace release proof guard", script_text)
        self.assertIn("commit 9f723c15 tightens the M105 queue mirror guard", script_text)
        self.assertIn("commit 7e908447 tightens the M105 workspace receipt proof", script_text)
        self.assertIn("commit 2df21683 pins the M105 workspace receipt proof floor", script_text)
        self.assertIn("commit 442c76c2 pins the M105 workspace receipt guard floor", script_text)
        self.assertIn("commit 1f4f0e2e requires the current M105 workspace receipt guard floor", script_text)
        self.assertIn("commit 29f7ec9b pins the M105 workspace receipt proof floor", script_text)
        self.assertIn("commit b4da7025 pins the M105 workspace proof floor guard", script_text)
        self.assertIn("commit 46551461 tightens the M105 standard verify entrypoint guard", script_text)
        self.assertIn("commit 1b1c5427 pins the M105 workspace proof floor guard", script_text)
        self.assertIn("commit 1d5a811f pins the M105 workspace proof floor guard", script_text)
        self.assertIn("commit f02e985f tightens the M105 blocked-helper command guard", script_text)
        self.assertIn("commit 0f06bcef pins the M105 helper guard proof floor", script_text)
        self.assertIn("commit 1ca535e2 pins the M105 workspace helper proof floor", script_text)
        self.assertIn("commit 25fb4391 pins the M105 workspace proof floor", script_text)
        self.assertIn("commit 41c106c8 pins the M105 workspace proof floor guard", script_text)
        self.assertIn("commit b4bdc153 pins the M105 workspace proof floor guard", script_text)
        self.assertIn("commit 1c98d6ba pins the M105 workspace proof floor", script_text)
        self.assertIn("commit 83bbc0d4 tightens the M105 workspace duplicate proof guard", script_text)
        self.assertIn("commit 1a0ba130 pins the M105 workspace duplicate proof floor", script_text)
        self.assertIn("commit 63313972 pins the M105 workspace proof floor", script_text)
        self.assertIn("commit 0b038324 tightens M105 local and served release proof uniqueness", script_text)
        self.assertIn("commit 447f2a90 pins the M105 workspace uniqueness proof floor", script_text)
        self.assertIn("commit a8f94a63 pins the M105 workspace uniqueness proof floor", script_text)
        self.assertIn("commit 06b0e574 pins the current M105 workspace proof floor guard", script_text)
        self.assertIn("commit 79764447 pins the M105 workspace current proof floor", script_text)
        self.assertIn("commit 0f4a31d3 pins the M105 workspace proof floor", script_text)
        self.assertIn("commit d7788857 tightens the M105 workspace canonical proof floor", script_text)
        self.assertIn("commit f5f414b0 pins the M105 workspace current proof floor", script_text)
        self.assertIn("commit 5e77a853 pins the M105 workspace current proof floor", script_text)
        self.assertIn("commit 23308c16 requires the current M105 workspace proof floor guard", script_text)
        self.assertIn("commit 2da59c68 pins the M105 workspace proof floor guard", script_text)
        self.assertIn("commit 71e514b2 pins the M105 workspace proof floor guard", script_text)
        self.assertIn("commit e0d2bff6 pins the M105 workspace queue-frontier guard proof", script_text)
        self.assertIn("commit c6f628ef pins the M105 verifier to the canonical queue-frontier proof floor", script_text)
        self.assertIn("commit fa17ff4d tightens the M105 workspace queue task guard", script_text)
        self.assertIn("commit 72f96452 pins the M105 workspace task guard proof", script_text)
        self.assertIn("commit 664737cb pins the current M105 workspace task guard floor", script_text)
        self.assertIn("commit 138d84ef pins the latest M105 workspace task guard floor", script_text)
        self.assertIn("commit 109face0 pins the M105 workspace proof floor", script_text)
        self.assertIn("commit 28b9e40a pins the M105 workspace proof floor guard", script_text)
        self.assertIn("commit f6cd760e tightens the M105 verifier to require the current queue-cited workspace proof floor", script_text)
        self.assertIn("commit 03517936 tightens the M105 restore API proof guard", script_text)
        self.assertIn("commit 57da8fb3 preserves workspace restore receipt observation timestamps", script_text)
        self.assertIn("commit aa7d6b9a pins the M105 current workspace proof floor", script_text)
        self.assertIn("commit 6add6cc6 pins the M105 workspace proof floor", script_text)
        self.assertIn("commit 4487d01a pins the M105 workspace proof floor guard", script_text)
        self.assertIn("commit 9171e3f4 tightens M105 release proof receipt uniqueness", script_text)
        self.assertIn("commit a7e826d3 pins the M105 workspace receipt uniqueness proof floor", script_text)
        self.assertIn("commit d882db69 pins the M105 workspace proof floor guard", script_text)
        self.assertIn("commit db4fe453 tightens M105 served proof route mirroring", script_text)
        self.assertIn("/docker/chummercomplete/chummer.run-services/tests/test_workspace_restore_queue_frontier_guard.py", script_text)

    def test_all_registry_and_queue_commit_citations_are_required_to_resolve(self) -> None:
        spec = importlib.util.spec_from_file_location("workspace_restore_verifier", SCRIPT)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        verifier = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(verifier)

        cited_commits = {
            match
            for markers in [verifier.REGISTRY_MARKERS, verifier.QUEUE_STAGING_MARKERS]
            for marker in markers
            for match in re.findall(r"commit ([0-9a-f]{8})", marker)
        }
        cited_commits.add(verifier.LANDED_COMMIT)

        required_commits = set(verifier.DEFAULT_REQUIRED_LOCAL_COMMITS)
        self.assertFalse(
            cited_commits - required_commits,
            f"commit citations must be present in DEFAULT_REQUIRED_LOCAL_COMMITS: {sorted(cited_commits - required_commits)}",
        )

    def test_verifier_fails_closed_when_required_local_commit_does_not_resolve(self) -> None:
        env = os.environ.copy()
        env["CHUMMER_WORKSPACE_RESTORE_RECEIPTS_REQUIRED_COMMITS"] = "4d4b3856,00000000"

        result = subprocess.run(
            ["python3", str(SCRIPT)],
            cwd=REPO_ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("required local commit does not resolve: 00000000", result.stderr)


if __name__ == "__main__":
    unittest.main()
