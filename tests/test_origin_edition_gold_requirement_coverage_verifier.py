from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "verify_origin_edition_gold_requirement_coverage.py"


def load_module():
    spec = importlib.util.spec_from_file_location("origin_edition_gold_requirement_coverage_verifier", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def coverage_payload(*, ready: bool = False) -> dict:
    module = load_module()
    blocked = [] if ready else ["deployed_owner_read_listen_watch_canon"]
    requirements = []
    for requirement_id in module.EXPECTED_REQUIREMENTS:
        is_blocked = requirement_id in blocked
        requirements.append(
            {
                "id": requirement_id,
                "label": requirement_id.replace("_", " "),
                "status": "blocked" if is_blocked else "proved",
                "rowIds": ["deployed_user_login_read_listen_watch"] if is_blocked else ["dummy_row"],
                "hardGateIds": ["gold_audit_completion_claim_allowed"] if is_blocked else [],
                "missingRows": [],
                "blockedRows": ["deployed_user_login_read_listen_watch"] if is_blocked else [],
                "missingHardGates": [],
                "blockedHardGates": ["gold_audit_completion_claim_allowed"] if is_blocked else [],
            }
        )
    return {
        "contractName": "chummer.origin_edition.gold_requirement_coverage.v1",
        "status": "pass" if ready else "blocked",
        "goalCompletionClaimAllowed": ready,
        "matrixSha256": "a" * 64,
        "proofChainSha256": "b" * 64,
        "blockedRequirements": blocked,
        "requirements": requirements,
        "privacy": {
            "envValuesExposed": False,
            "rawCredentialExposed": False,
            "rawSessionTokenExposed": False,
        },
    }


def test_verifier_accepts_current_single_blocked_requirement(tmp_path: Path) -> None:
    module = load_module()
    path = tmp_path / "coverage.json"
    write_json(path, coverage_payload())

    ok, issues = module.verify(path)

    assert ok is True
    assert issues == []


def test_verifier_accepts_gold_coverage_when_require_gold(tmp_path: Path) -> None:
    module = load_module()
    path = tmp_path / "coverage.json"
    write_json(path, coverage_payload(ready=True))

    ok, issues = module.verify(path, require_gold=True)

    assert ok is True
    assert issues == []


def test_verifier_rejects_unexpected_blocked_requirement(tmp_path: Path) -> None:
    module = load_module()
    path = tmp_path / "coverage.json"
    payload = coverage_payload()
    payload["requirements"][0]["status"] = "blocked"
    payload["requirements"][0]["blockedRows"] = ["some_row"]
    payload["blockedRequirements"] = [payload["requirements"][0]["id"], "deployed_owner_read_listen_watch_canon"]
    write_json(path, payload)

    ok, issues = module.verify(path)

    assert ok is False
    assert any(issue.startswith("unexpected_blocked_requirements:") for issue in issues)


def test_verifier_rejects_requirement_order_drift(tmp_path: Path) -> None:
    module = load_module()
    path = tmp_path / "coverage.json"
    payload = coverage_payload()
    payload["requirements"] = list(reversed(payload["requirements"]))
    write_json(path, payload)

    ok, issues = module.verify(path)

    assert ok is False
    assert any(issue.startswith("requirement_order_mismatch:") for issue in issues)


def test_verifier_rejects_secret_marker_even_when_json_invalid(tmp_path: Path) -> None:
    module = load_module()
    path = tmp_path / "coverage.json"
    write_json(path, coverage_payload())
    path.write_text(path.read_text(encoding="utf-8") + "\nBearer leaked\n", encoding="utf-8")

    ok, issues = module.verify(path)

    assert ok is False
    assert "forbidden_secret_marker:Bearer " in issues
    assert any(issue.startswith("invalid_json:") for issue in issues)
