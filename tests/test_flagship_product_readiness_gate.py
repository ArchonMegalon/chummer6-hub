from __future__ import annotations

import importlib.util
import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "verify_flagship_product_readiness_gate.py"
SPEC = importlib.util.spec_from_file_location("verify_flagship_product_readiness_gate", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def ready_payload(status: str = "pass") -> dict:
    return {
        "contract_name": "fleet.flagship_product_readiness",
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "status": status,
        "scoped_status": "pass",
        "ready_keys": sorted(MODULE.REQUIRED_READY_KEYS),
        "completion_audit": {"status": "pass"},
        "flagship_readiness_audit": {"status": "pass"},
        "external_host_proof": {"status": "pass"},
    }


def test_flagship_product_readiness_gate_passes_green_fresh_payload() -> None:
    with tempfile.TemporaryDirectory(prefix="flagship-readiness-gate-") as temp_dir:
        path = Path(temp_dir) / "FLAGSHIP_PRODUCT_READINESS.generated.json"
        path.write_text(json.dumps(ready_payload()), encoding="utf-8")

        payload = MODULE.build_payload(path, max_age_hours=168)

    assert payload["status"] == "pass"
    assert payload["failures"] == []
    assert payload["readiness"]["ready_keys"] == sorted(MODULE.REQUIRED_READY_KEYS)


def test_flagship_product_readiness_gate_fails_closed_on_missing_ready_key() -> None:
    with tempfile.TemporaryDirectory(prefix="flagship-readiness-gate-") as temp_dir:
        path = Path(temp_dir) / "FLAGSHIP_PRODUCT_READINESS.generated.json"
        body = ready_payload()
        body["ready_keys"] = [key for key in body["ready_keys"] if key != "mobile_play_shell"]
        path.write_text(json.dumps(body), encoding="utf-8")

        payload = MODULE.build_payload(path, max_age_hours=168)

    assert payload["status"] == "fail"
    assert any("mobile_play_shell" in failure for failure in payload["failures"])


def test_flagship_product_readiness_gate_materializes_summary_output() -> None:
    with tempfile.TemporaryDirectory(prefix="flagship-readiness-gate-") as temp_dir:
        root = Path(temp_dir)
        input_path = root / "FLAGSHIP_PRODUCT_READINESS.generated.json"
        output_path = root / "FLAGSHIP_PRODUCT_READINESS_GATE.generated.json"
        input_path.write_text(json.dumps(ready_payload()), encoding="utf-8")

        result = MODULE.build_payload(input_path, max_age_hours=168)
        output_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        saved = json.loads(output_path.read_text(encoding="utf-8"))

    assert saved["contract_name"] == "chummer.flagship_product_readiness_gate.v1"
    assert saved["status"] == "pass"
