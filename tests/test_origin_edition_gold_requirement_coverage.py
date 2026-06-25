from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "materialize_origin_edition_gold_requirement_coverage.py"


def load_module():
    spec = importlib.util.spec_from_file_location("origin_edition_gold_requirement_coverage", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def seed_matrix(root: Path, *, deployed_pass: bool = False) -> None:
    module = load_module()
    rows = []
    for _, _, row_ids, _ in module.REQUIREMENTS:
        for row_id in row_ids:
            if row_id not in {row["id"] for row in rows}:
                rows.append(
                    {
                        "id": row_id,
                        "status": "proved" if deployed_pass or row_id != "deployed_user_login_read_listen_watch" else "blocked",
                    }
                )
    hard_gates = {}
    for _, _, _, gate_ids in module.REQUIREMENTS:
        for gate_id in gate_ids:
            hard_gates[gate_id] = deployed_pass or gate_id != "gold_audit_completion_claim_allowed"
    write_json(
        root / "ORIGIN_EDITION_GOLD_COMPLETION_MATRIX.generated.json",
        {
            "contractName": "chummer.origin_edition.gold_completion_matrix.v1",
            "status": "pass" if deployed_pass else "blocked",
            "hardGates": hard_gates,
            "rows": rows,
        },
    )
    write_json(
        root / "ORIGIN_EDITION_GOLD_PROOF_CHAIN.generated.json",
        {
            "contractName": "chummer.origin_edition.gold_proof_chain.v1",
            "status": "pass" if deployed_pass else "blocked",
            "goalCompletionClaimAllowed": deployed_pass,
        },
    )


def test_requirement_coverage_blocks_only_deployed_owner_requirement_for_current_gap(tmp_path: Path) -> None:
    module = load_module()
    seed_matrix(tmp_path, deployed_pass=False)

    result = module.materialize(tmp_path, tmp_path / "coverage.json")

    assert result["status"] == "blocked"
    assert result["goalCompletionClaimAllowed"] is False
    assert result["blockedRequirements"] == ["deployed_owner_read_listen_watch_canon"]
    deployed = next(item for item in result["requirements"] if item["id"] == "deployed_owner_read_listen_watch_canon")
    assert deployed["blockedRows"] == ["deployed_user_login_read_listen_watch"]
    assert deployed["blockedHardGates"] == ["gold_audit_completion_claim_allowed"]


def test_requirement_coverage_passes_when_all_matrix_rows_and_hard_gates_pass(tmp_path: Path) -> None:
    module = load_module()
    seed_matrix(tmp_path, deployed_pass=True)

    result = module.materialize(tmp_path, tmp_path / "coverage.json")

    assert result["status"] == "pass"
    assert result["goalCompletionClaimAllowed"] is True
    assert result["blockedRequirements"] == []


def test_requirement_coverage_blocks_missing_required_receipt_row(tmp_path: Path) -> None:
    module = load_module()
    seed_matrix(tmp_path, deployed_pass=True)
    matrix_path = tmp_path / "ORIGIN_EDITION_GOLD_COMPLETION_MATRIX.generated.json"
    matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    matrix["rows"] = [row for row in matrix["rows"] if row["id"] != "m4b_unmixr_narration_import_verified"]
    write_json(matrix_path, matrix)

    result = module.materialize(tmp_path, tmp_path / "coverage.json")
    audiobook = next(item for item in result["requirements"] if item["id"] == "m4b_unmixr_audiobook_packaging")

    assert result["status"] == "blocked"
    assert "m4b_unmixr_audiobook_packaging" in result["blockedRequirements"]
    assert audiobook["missingRows"] == ["m4b_unmixr_narration_import_verified"]
