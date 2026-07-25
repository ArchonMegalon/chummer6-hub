from __future__ import annotations

import importlib.util
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "materialize_horizon_e2e_gold_matrix.py"
SPEC = importlib.util.spec_from_file_location("materialize_horizon_e2e_gold_matrix", SCRIPT_PATH)
if SPEC is None or SPEC.loader is None:
    raise ImportError(f"Unable to import {SCRIPT_PATH}")
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


ROUTES = {
    "alice": ("/alice", "/alice/receipts/build-ghost.json"),
    "origin-dossier": ("/origin-dossier", "/origin-dossier/receipts/story-network.json"),
    "karma-forge": (
        "/participate/karma-forge",
        "/participate/karma-forge/receipts/discovery-network.json",
    ),
    "knowledge-fabric": ("/rules", "/rules/explanations"),
    "jackpoint": ("/jackpoint", "/jackpoint/receipts/briefing-network.json"),
    "black-ledger": ("/ledger", "/ledger/receipts/viewer-network.json"),
    "runsite": ("/runsites", "/runsites/receipts/prep-network.json"),
    "runbook-press": ("/runbook", "/runbook/receipts/primer-network.json"),
    "table-pulse": (
        "/table-pulse",
        "/table-pulse/receipts/live-and-aftermath.json",
    ),
}


def registry_rows() -> list[dict]:
    return [
        {
            "id": horizon_id,
            "title": horizon_id,
            "status": "shipped_mvp",
            "route": ROUTES[horizon_id][0],
            "receipt_route": ROUTES[horizon_id][1],
            "claim_scope": module.CLAIM_SCOPE,
            "owning_repos": ["owner"],
        }
        for horizon_id in module.EXPECTED_HORIZON_IDS
    ]


def write_artifacts(path: Path, generated_at: datetime) -> None:
    path.mkdir(parents=True)
    for row in registry_rows():
        payload = {
            "contract_name": module.RECEIPT_CONTRACT_NAME,
            "generated_at_utc": module.iso_utc(generated_at),
            "status": "pass",
            "verdict": "GOLD",
            "claim_scope": module.CLAIM_SCOPE,
            "base_url": "https://chummer.run",
            "horizon_id": row["id"],
            "route": row["route"],
            "receipt_route": row["receipt_route"],
            "assertion_count": 12,
            "journey_steps": ["one", "two", "three", "four"],
            "boundaries_verified": ["one", "two", "three", "four"],
            "evidence": {"receipt_route": row["receipt_route"]},
        }
        (path / f"HORIZON_E2E_GOLD.{row['id']}.generated.json").write_text(
            json.dumps(payload),
            encoding="utf-8",
        )


def passing_runner() -> dict:
    return {
        "returncode": 0,
        "timed_out": False,
        "stats": {
            "expected": 9,
            "unexpected": 0,
            "flaky": 0,
            "skipped": 0,
            "duration_ms": 100,
        },
        "parse_failure": "",
    }


def test_build_matrix_passes_only_with_all_nine_fresh_executed_receipts(tmp_path: Path) -> None:
    started = datetime(2026, 7, 29, 12, 0, tzinfo=UTC)
    finished = started + timedelta(minutes=1)
    artifacts = tmp_path / "artifacts"
    write_artifacts(artifacts, started + timedelta(seconds=30))

    payload = module.build_matrix(
        registry_rows=registry_rows(),
        registry_failures=[],
        artifacts_dir=artifacts,
        evidence_dir=tmp_path / "published",
        base_url="https://chummer.run",
        run_started_at=started,
        run_finished_at=finished,
        runner=passing_runner(),
        source_inputs={},
    )

    assert payload["status"] == "pass"
    assert payload["verdict"] == module.PASS_VERDICT
    assert payload["all_horizons_gold"] is True
    assert payload["summary"] == {
        "horizon_count": 9,
        "gold_count": 9,
        "failed_count": 0,
        "expected_count": 9,
        "assertion_count": 108,
    }
    assert [row["id"] for row in payload["horizons"]] == list(module.EXPECTED_HORIZON_IDS)
    assert all(row["status"] == "pass" for row in payload["horizons"])


def test_build_matrix_fails_closed_for_missing_horizon_receipt(tmp_path: Path) -> None:
    started = datetime(2026, 7, 29, 12, 0, tzinfo=UTC)
    finished = started + timedelta(minutes=1)
    artifacts = tmp_path / "artifacts"
    write_artifacts(artifacts, started + timedelta(seconds=30))
    (artifacts / "HORIZON_E2E_GOLD.knowledge-fabric.generated.json").unlink()

    payload = module.build_matrix(
        registry_rows=registry_rows(),
        registry_failures=[],
        artifacts_dir=artifacts,
        evidence_dir=tmp_path / "published",
        base_url="https://chummer.run",
        run_started_at=started,
        run_finished_at=finished,
        runner=passing_runner(),
        source_inputs={},
    )

    assert payload["status"] == "fail"
    assert payload["all_horizons_gold"] is False
    assert payload["summary"]["gold_count"] == 8
    assert any("knowledge-fabric browser receipt is missing" in item for item in payload["failures"])


def test_build_matrix_rejects_skipped_or_scope_drift(tmp_path: Path) -> None:
    started = datetime(2026, 7, 29, 12, 0, tzinfo=UTC)
    finished = started + timedelta(minutes=1)
    artifacts = tmp_path / "artifacts"
    write_artifacts(artifacts, started + timedelta(seconds=30))
    drifted_path = artifacts / "HORIZON_E2E_GOLD.alice.generated.json"
    drifted = json.loads(drifted_path.read_text(encoding="utf-8"))
    drifted["claim_scope"] = "screenshots_only"
    drifted_path.write_text(json.dumps(drifted), encoding="utf-8")
    runner = passing_runner()
    runner["stats"]["skipped"] = 1

    payload = module.build_matrix(
        registry_rows=registry_rows(),
        registry_failures=[],
        artifacts_dir=artifacts,
        evidence_dir=tmp_path / "published",
        base_url="https://chummer.run",
        run_started_at=started,
        run_finished_at=finished,
        runner=runner,
        source_inputs={},
    )

    assert payload["status"] == "fail"
    assert any("skipped 1 horizon" in item for item in payload["failures"])
    assert any("alice browser receipt claim_scope drifted" in item for item in payload["failures"])
