from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "verify_table_pulse_connected_lane_surface.py"
SOURCE_FILES = [
    "Chummer.Run.Api/Controllers/PublicLandingController.cs",
    "Chummer.Run.Api/Views/Accounts/Account.cshtml",
    "Chummer.Run.Api/Views/PublicLanding/Home.cshtml",
    "Chummer.Run.Api/Views/PublicLanding/Shelf.cshtml",
    "Chummer.Run.Api/Views/PublicLanding/LedgerFactionWorkspace.cshtml",
    "Chummer.Run.Api/Views/PublicLanding/MediaArtifactHorizon.cshtml",
    "scripts/verify_table_pulse_connected_lane_surface.py",
    "tests/test_table_pulse_connected_lane_surface.py",
]


class TablePulseConnectedLaneSurfaceTests(unittest.TestCase):
    def test_verifier_accepts_repo_surface(self) -> None:
        result = subprocess.run(
            ["python3", str(SCRIPT)],
            cwd=REPO_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)
        self.assertIn("table_pulse_connected_lane_surface:ok", result.stdout)

    def test_verifier_fails_when_account_workspace_lane_drifts(self) -> None:
        with tempfile.TemporaryDirectory(prefix="table-pulse-account-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            account_path = temp_root / "Chummer.Run.Api/Views/Accounts/Account.cshtml"
            account_path.write_text(
                account_path.read_text(encoding="utf-8").replace(
                    "<strong>Table Pulse Live command-to-fallout lane</strong>",
                    "<strong>Workspace recap</strong>",
                    1,
                ),
                encoding="utf-8",
            )

            result = self.run_verifier(temp_root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "Chummer.Run.Api/Views/Accounts/Account.cshtml missing marker: <strong>Table Pulse Live command-to-fallout lane</strong>",
            result.stderr,
        )

    def test_verifier_fails_when_shelf_drops_return_rail_language(self) -> None:
        with tempfile.TemporaryDirectory(prefix="table-pulse-home-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            shelf_path = temp_root / "Chummer.Run.Api/Views/PublicLanding/Shelf.cshtml"
            shelf_path.write_text(
                shelf_path.read_text(encoding="utf-8").replace(
                    "Table Pulse Aftermath return artifacts that stay on this signed-in shelf",
                    "return artifacts that stay on this signed-in shelf",
                    1,
                ),
                encoding="utf-8",
            )

            result = self.run_verifier(temp_root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "Chummer.Run.Api/Views/PublicLanding/Shelf.cshtml missing marker: Table Pulse Aftermath return artifacts that stay on this signed-in shelf",
            result.stderr,
        )

    def test_verifier_fails_when_shelf_drops_connected_return_cues(self) -> None:
        with tempfile.TemporaryDirectory(prefix="table-pulse-shelf-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            shelf_path = temp_root / "Chummer.Run.Api/Views/PublicLanding/Shelf.cshtml"
            shelf_path.write_text(
                shelf_path.read_text(encoding="utf-8").replace(
                    "the artifact shelf keeps your live Table Pulse Aftermath return cues, aftermath, replay, and linked creator-publication record together",
                    "the artifact shelf keeps your live aftermath, replay, and linked creator-publication record together",
                    1,
                ),
                encoding="utf-8",
            )

            result = self.run_verifier(temp_root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "Chummer.Run.Api/Views/PublicLanding/Shelf.cshtml missing marker: the artifact shelf keeps your live Table Pulse Aftermath return cues, aftermath, replay, and linked creator-publication record together",
            result.stderr,
        )

    def test_verifier_fails_when_controller_drops_runner_passport_lane(self) -> None:
        with tempfile.TemporaryDirectory(prefix="table-pulse-controller-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            controller_path = temp_root / "Chummer.Run.Api/Controllers/PublicLandingController.cs"
            controller_path.write_text(
                controller_path.read_text(encoding="utf-8").replace(
                    'Heading: "Runner Passport connected lane"',
                    'Heading: "Runner Passport"',
                    1,
                ),
                encoding="utf-8",
            )

            result = self.run_verifier(temp_root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "Chummer.Run.Api/Controllers/PublicLandingController.cs missing marker: Runner Passport connected lane",
            result.stderr,
        )

    def test_verifier_fails_when_media_horizon_drops_connected_lane(self) -> None:
        with tempfile.TemporaryDirectory(prefix="table-pulse-media-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            media_path = temp_root / "Chummer.Run.Api/Views/PublicLanding/MediaArtifactHorizon.cshtml"
            media_path.write_text(
                media_path.read_text(encoding="utf-8").replace(
                    "<p class=\"eyebrow\">Connected lane</p>",
                    "<p class=\"eyebrow\">Artifact lane</p>",
                    1,
                ),
                encoding="utf-8",
            )

            result = self.run_verifier(temp_root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "Chummer.Run.Api/Views/PublicLanding/MediaArtifactHorizon.cshtml missing marker: <p class=\"eyebrow\">Connected lane</p>",
            result.stderr,
        )

    def test_verifier_fails_when_workspace_drops_connected_lane(self) -> None:
        with tempfile.TemporaryDirectory(prefix="table-pulse-workspace-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            workspace_path = temp_root / "Chummer.Run.Api/Views/PublicLanding/LedgerFactionWorkspace.cshtml"
            workspace_path.write_text(
                workspace_path.read_text(encoding="utf-8").replace(
                    "Connected command lane",
                    "Workspace tabs",
                    1,
                ),
                encoding="utf-8",
            )

            result = self.run_verifier(temp_root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "Chummer.Run.Api/Views/PublicLanding/LedgerFactionWorkspace.cshtml missing marker: Connected command lane",
            result.stderr,
        )

    @staticmethod
    def copy_sources(temp_root: Path) -> None:
        for relative_path in SOURCE_FILES:
            source = REPO_ROOT / relative_path
            target = temp_root / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)

    @staticmethod
    def run_verifier(temp_root: Path) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["CHUMMER_TABLE_PULSE_CONNECTED_LANE_ROOT"] = str(temp_root)
        return subprocess.run(
            ["python3", str(temp_root / "scripts/verify_table_pulse_connected_lane_surface.py")],
            cwd=temp_root,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )


if __name__ == "__main__":
    unittest.main()
