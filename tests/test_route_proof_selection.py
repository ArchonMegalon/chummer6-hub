from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


RUN_SERVICES_ROOT = Path("/docker/chummercomplete/chummer.run-services")
SCRIPTS_DIR = RUN_SERVICES_ROOT / "scripts"
FINAL_UX_VERDICT_PATH = SCRIPTS_DIR / "final_chummer_run_ux_verdict.py"
PRE_GOLD_VERDICT_PATH = SCRIPTS_DIR / "final_pre_gold_full_product_verdict.py"


def _load_module(name: str, path: Path):
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_route_proof(path: Path, *, generated_at: str, status: str = "pass", base_url: str = "https://chummer.run") -> None:
    payload = {
        "contract_name": "chummer.public_route_proof",
        "status": status,
        "generated_at_utc": generated_at,
        "base_url": base_url,
        "summary": {
            "failed_count": 0 if status == "pass" else 1,
            "positive_proof_count": 1 if status == "pass" else 0,
        },
        "routes": [],
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


class RouteProofSelectionTests(unittest.TestCase):
    def test_final_ux_verdict_prefers_fresher_local_canonical_route_proof(self) -> None:
        module = _load_module("final_chummer_run_ux_verdict_test", FINAL_UX_VERDICT_PATH)
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            live_path = tmp_root / "CHUMMER_PUBLIC_ROUTE_PROOF.live.generated.json"
            local_path = tmp_root / "CHUMMER_PUBLIC_ROUTE_PROOF.generated.json"
            _write_route_proof(live_path, generated_at="2026-07-05T00:00:00Z")
            _write_route_proof(local_path, generated_at="2026-07-06T00:00:00Z")

            module.LIVE_ROUTE_PROOF_PATH = live_path
            module.ROUTE_PROOF_PATH = local_path

            self.assertEqual(local_path, module.select_route_proof_source())

    def test_final_ux_verdict_prefers_live_when_live_is_fresher(self) -> None:
        module = _load_module("final_chummer_run_ux_verdict_test_live", FINAL_UX_VERDICT_PATH)
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            live_path = tmp_root / "CHUMMER_PUBLIC_ROUTE_PROOF.live.generated.json"
            local_path = tmp_root / "CHUMMER_PUBLIC_ROUTE_PROOF.generated.json"
            _write_route_proof(live_path, generated_at="2026-07-06T00:00:00Z")
            _write_route_proof(local_path, generated_at="2026-07-05T00:00:00Z")

            module.LIVE_ROUTE_PROOF_PATH = live_path
            module.ROUTE_PROOF_PATH = local_path

            self.assertEqual(live_path, module.select_route_proof_source())

    def test_pre_gold_verdict_prefers_fresher_local_canonical_route_proof(self) -> None:
        module = _load_module("final_pre_gold_full_product_verdict_test", PRE_GOLD_VERDICT_PATH)
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            live_path = tmp_root / "CHUMMER_PUBLIC_ROUTE_PROOF.live.generated.json"
            local_path = tmp_root / "CHUMMER_PUBLIC_ROUTE_PROOF.generated.json"
            _write_route_proof(live_path, generated_at="2026-07-05T00:00:00Z")
            _write_route_proof(local_path, generated_at="2026-07-06T00:00:00Z")

            module.LIVE_ROUTE_PROOF_PATH = live_path
            module.LOCAL_ROUTE_PROOF_PATH = local_path

            payload, mode = module.load_live_or_local_route_proof()
            self.assertEqual("local-published", mode)
            self.assertEqual("2026-07-06T00:00:00Z", payload["generated_at_utc"])

    def test_pre_gold_verdict_prefers_live_when_live_is_fresher(self) -> None:
        module = _load_module("final_pre_gold_full_product_verdict_test_live", PRE_GOLD_VERDICT_PATH)
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            live_path = tmp_root / "CHUMMER_PUBLIC_ROUTE_PROOF.live.generated.json"
            local_path = tmp_root / "CHUMMER_PUBLIC_ROUTE_PROOF.generated.json"
            _write_route_proof(live_path, generated_at="2026-07-06T00:00:00Z")
            _write_route_proof(local_path, generated_at="2026-07-05T00:00:00Z")

            module.LIVE_ROUTE_PROOF_PATH = live_path
            module.LOCAL_ROUTE_PROOF_PATH = local_path

            payload, mode = module.load_live_or_local_route_proof()
            self.assertEqual("live", mode)
            self.assertEqual("2026-07-06T00:00:00Z", payload["generated_at_utc"])


if __name__ == "__main__":
    unittest.main()
