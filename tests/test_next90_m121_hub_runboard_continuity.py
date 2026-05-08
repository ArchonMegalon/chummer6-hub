from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / 'scripts' / 'verify_next90_m121_hub_runboard_continuity.py'
SOURCE_FILES = [
    'Chummer.Campaign.Contracts/RunboardContinuityContracts.cs',
    'Chummer.Run.Api/Contracts/CampaignRunboardContinuityContracts.cs',
    'Chummer.Run.Api/Controllers/CampaignSpineController.cs',
    'Chummer.Run.Api/Services/Community/CampaignSpineService.cs',
    'Chummer.Run.Api/Services/Community/CampaignWorkspaceServerPlaneService.cs',
    'tests/RunServicesSmoke/Program.cs',
    'scripts/materialize_next90_m121_hub_runboard_continuity_proof.py',
    'scripts/verify_next90_m121_hub_runboard_continuity.py',
    'scripts/ai/verify.sh',
]


class Next90M121HubRunboardContinuityTests(unittest.TestCase):
    def test_verifier_accepts_repo_local_runboard_continuity_lane(self) -> None:
        result = subprocess.run(["python3", str(SCRIPT)], cwd=REPO_ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)
        self.assertIn("next90 m121 hub runboard continuity proof passed", result.stdout)

    def test_verify_script_runs_m121_guard(self) -> None:
        verify_script = (REPO_ROOT / 'scripts' / 'ai' / 'verify.sh').read_text(encoding='utf-8')
        self.assertIn('python3 scripts/materialize_next90_m121_hub_runboard_continuity_proof.py', verify_script)
        self.assertIn('python3 scripts/verify_next90_m121_hub_runboard_continuity.py', verify_script)
        self.assertIn('python3 -m unittest tests/test_next90_m121_hub_runboard_continuity.py', verify_script)

    def test_verifier_fails_when_queue_row_drifts(self) -> None:
        with tempfile.TemporaryDirectory(prefix='next90-m121-queue-') as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            queue_path = temp_root / 'fleet-queue.yaml'
            design_queue_path = temp_root / 'design-queue.yaml'
            shutil.copyfile('/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml', queue_path)
            shutil.copyfile('/docker/chummercomplete/chummer-design-m114/products/chummer/NEXT_90_DAY_QUEUE_STAGING.generated.yaml', design_queue_path)
            queue_payload = self.load_queue_payload(queue_path)
            for item in queue_payload['items']:
                if item.get('package_id') == 'next90-m121-hub-persist-session-turn-ledger-handoff-runboard-state-and-r':
                    item['frontier_id'] = 0
                    break
            queue_path.write_text(yaml.safe_dump(queue_payload, sort_keys=False), encoding='utf-8')
            result = self.run_verifier(temp_root, queue_path=queue_path, design_queue_path=design_queue_path)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn('frontier_id must be 7165194744', result.stderr)

    def test_verifier_fails_when_smoke_loses_runboard_endpoint(self) -> None:
        with tempfile.TemporaryDirectory(prefix='next90-m121-smoke-') as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            smoke_path = temp_root / 'tests/RunServicesSmoke/Program.cs'
            smoke_text = smoke_path.read_text(encoding='utf-8')
            smoke_path.write_text(smoke_text.replace('UpsertMyCampaignWorkspaceRunboardContinuity', 'UpsertMyCampaignWorkspaceRunboardDrift'), encoding='utf-8')
            result = self.run_verifier(temp_root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn('UpsertMyCampaignWorkspaceRunboardContinuity', result.stderr)

    @staticmethod
    def copy_sources(temp_root: Path) -> None:
        for relative_path in SOURCE_FILES:
            source = REPO_ROOT / relative_path
            target = temp_root / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)

    def run_verifier(self, temp_root: Path, *, queue_path: Path | None = None, design_queue_path: Path | None = None) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env['CHUMMER_NEXT90_M121_ROOT'] = str(temp_root)
        if queue_path is not None:
            env['CHUMMER_NEXT90_M121_QUEUE_STAGING'] = str(queue_path)
        if design_queue_path is not None:
            env['CHUMMER_NEXT90_M121_DESIGN_QUEUE_STAGING'] = str(design_queue_path)
        return subprocess.run(["python3", str(temp_root / 'scripts/verify_next90_m121_hub_runboard_continuity.py')], cwd=temp_root, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    @staticmethod
    def load_queue_payload(path: Path) -> dict:
        text = path.read_text(encoding='utf-8')
        try:
            payload = yaml.safe_load(text)
        except yaml.YAMLError:
            payload = None
        if isinstance(payload, dict) and isinstance(payload.get('items'), list):
            return payload

        package_marker = 'package_id: next90-m121-hub-persist-session-turn-ledger-handoff-runboard-state-and-r'
        package_index = text.find(package_marker)
        if package_index < 0:
            raise AssertionError(f'queue staging is missing {package_marker}')

        start = text.rfind('\n- title:', 0, package_index)
        if start < 0:
            if not text.startswith('- title:'):
                raise AssertionError('queue staging is missing the target item block')
            start = 0
        else:
            start += 1

        end = text.find('\n- title:', package_index)
        if end < 0:
            end = len(text)

        block = text[start:end].rstrip() + '\n'
        payload = yaml.safe_load(block)
        if not isinstance(payload, list) or len(payload) != 1 or not isinstance(payload[0], dict):
            raise AssertionError('queue staging target block did not parse correctly')
        return {'items': payload}


if __name__ == '__main__':
    unittest.main()
