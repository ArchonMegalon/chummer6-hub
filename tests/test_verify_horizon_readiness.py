from __future__ import annotations

import copy
from datetime import UTC, datetime, timedelta
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
MATERIALIZER_PATH = REPO_ROOT / "scripts/materialize_horizon_readiness.py"
VERIFIER_PATH = REPO_ROOT / "scripts/verify_horizon_readiness.py"
REGISTRY_PATH = REPO_ROOT / ".codex-design/product/HORIZON_REGISTRY.yaml"
CAPABILITY_SERVICE_PATH = (
    REPO_ROOT / "Chummer.Run.Api/Services/Community/HorizonCapabilityService.cs"
)
GENERATED_AT = "2026-07-20T20:00:00Z"
VERIFY_NOW = datetime(2026, 7, 20, 20, 5, tzinfo=UTC)


def load_module(path: Path, name: str):
    scripts_dir = str(path.parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def materialize_artifact(tmp_path: Path, *, generated_at_utc: str = GENERATED_AT):
    materializer = load_module(MATERIALIZER_PATH, "materialize_horizon_readiness_fixture")
    artifact = tmp_path / "HORIZON_READINESS.generated.json"
    payload = materializer.materialize(
        REPO_ROOT,
        artifact,
        registry_path=REGISTRY_PATH,
        capability_service_path=CAPABILITY_SERVICE_PATH,
        generated_at_utc=generated_at_utc,
    )
    return artifact, payload


def verify_payload(verifier, payload: dict):
    return verifier.verify_payload(
        payload,
        REPO_ROOT,
        REGISTRY_PATH,
        CAPABILITY_SERVICE_PATH,
        now_utc=VERIFY_NOW,
    )


def test_verifier_accepts_current_structurally_honest_artifact(tmp_path: Path) -> None:
    verifier = load_module(VERIFIER_PATH, "verify_horizon_readiness_pass")
    artifact, payload = materialize_artifact(tmp_path)

    ok, issues = verifier.verify_artifact(artifact, REPO_ROOT, now_utc=VERIFY_NOW)

    assert ok is True
    assert issues == []
    assert payload["status"] == "attention_required"
    assert payload["operational_readiness_claim_allowed"] is False


def test_verifier_rejects_duplicate_and_missing_catalog_records(tmp_path: Path) -> None:
    verifier = load_module(VERIFIER_PATH, "verify_horizon_readiness_duplicates")
    _, original = materialize_artifact(tmp_path)
    payload = copy.deepcopy(original)
    duplicated = copy.deepcopy(payload["capabilities"][0])
    payload["capabilities"].append(duplicated)
    removed_id = payload["capabilities"][1]["capability_id"]
    del payload["capabilities"][1]

    ok, issues = verify_payload(verifier, payload)

    assert ok is False
    assert f"duplicate_capability:{duplicated['capability_id']}" in issues
    assert f"missing_capability:{removed_id}" in issues


def test_verifier_rejects_enabled_or_declared_state_as_readiness_inputs(tmp_path: Path) -> None:
    verifier = load_module(VERIFIER_PATH, "verify_horizon_readiness_derivation")
    _, original = materialize_artifact(tmp_path)
    payload = copy.deepcopy(original)
    payload["readiness_derivation"]["enabled_by_default_used"] = True
    payload["readiness_derivation"]["declared_shipment_state_used"] = True
    payload["capabilities"][0]["enabled_used_for_readiness"] = True
    payload["horizons"][0]["declared_state_used_for_readiness"] = True

    ok, issues = verify_payload(verifier, payload)

    assert ok is False
    assert "enabled_by_default_used_for_readiness" in issues
    assert "declared_shipment_state_used_for_readiness" in issues
    assert any(issue.endswith(":enabled_used_for_readiness") for issue in issues)
    assert any("declared_state_used_for_readiness" in issue for issue in issues)


def test_verifier_rejects_cleared_governance_on_governed_lane(tmp_path: Path) -> None:
    verifier = load_module(VERIFIER_PATH, "verify_horizon_readiness_governance")
    _, original = materialize_artifact(tmp_path)
    payload = copy.deepcopy(original)
    governed = next(
        item
        for item in payload["capabilities"]
        if item["orchestration_lane_declared"] is True
    )
    governed["governance_status"] = "cleared"

    ok, issues = verify_payload(verifier, payload)

    assert ok is False
    assert f"capability:{governed['capability_id']}:governed_lane_not_fail_closed" in issues


def test_verifier_rejects_unknown_missing_fields_and_non_object_rows(tmp_path: Path) -> None:
    verifier = load_module(VERIFIER_PATH, "verify_horizon_readiness_exact_schema")
    _, original = materialize_artifact(tmp_path)
    payload = copy.deepcopy(original)
    payload["unexpected"] = True
    del payload["status"]
    payload["horizons"][0]["unexpected"] = "ignored-before-hardening"
    del payload["horizons"][0]["title"]
    payload["capabilities"].append("not-an-object")
    payload["source_evidence"]["records"].append(["not-an-object"])

    ok, issues = verify_payload(verifier, payload)

    assert ok is False
    assert "top_level:unknown_field:unexpected" in issues
    assert "top_level:missing_field:status" in issues
    assert "horizon_row:0:unknown_field:unexpected" in issues
    assert "horizon_row:0:missing_field:title" in issues
    assert any(issue.endswith(":not_object") for issue in issues)


@pytest.mark.parametrize(
    ("generated_at_utc", "max_age_seconds", "expected_issue"),
    [
        ("2026-07-20T20:00:00+00:00", 86_400, "generated_at_utc_malformed"),
        ("2026-07-20T20:11:00Z", 86_400, "generated_at_utc_future"),
        ("2026-07-20T20:03:00Z", 60, "generated_at_utc_stale"),
    ],
)
def test_verifier_rejects_malformed_future_and_stale_generation_times(
    tmp_path: Path,
    generated_at_utc: str,
    max_age_seconds: int,
    expected_issue: str,
) -> None:
    verifier = load_module(VERIFIER_PATH, f"verify_horizon_readiness_time_{expected_issue}")
    _, payload = materialize_artifact(tmp_path, generated_at_utc=generated_at_utc)

    ok, issues = verifier.verify_payload(
        payload,
        REPO_ROOT,
        REGISTRY_PATH,
        CAPABILITY_SERVICE_PATH,
        max_age_seconds=max_age_seconds,
        now_utc=VERIFY_NOW,
    )

    assert ok is False
    assert expected_issue in issues


@pytest.mark.parametrize(
    ("unsafe_ref", "reason"),
    [
        ("/tmp/operator-proof.json", "absolute_path"),
        ("Users/operator/proof.json", "machine_local_prefix"),
        ("proofs/bearer-token.json", "secret_like_component"),
    ],
)
def test_verifier_rejects_unsafe_evidence_paths_without_echoing_them(
    tmp_path: Path,
    unsafe_ref: str,
    reason: str,
) -> None:
    verifier = load_module(VERIFIER_PATH, f"verify_horizon_readiness_path_{reason}")
    _, original = materialize_artifact(tmp_path)
    payload = copy.deepcopy(original)
    payload["horizons"][0]["evidence_refs"] = [unsafe_ref]

    ok, issues = verify_payload(verifier, payload)

    assert ok is False
    assert any(f":unsafe_path:{reason}" in issue for issue in issues)
    assert unsafe_ref not in "\n".join(issues)
    assert "source_evidence:evidence_refs_mismatch" in issues


def test_verifier_rejects_mismatched_summaries_evidence_refs_and_digests(
    tmp_path: Path,
) -> None:
    verifier = load_module(VERIFIER_PATH, "verify_horizon_readiness_bindings")
    _, original = materialize_artifact(tmp_path)
    payload = copy.deepcopy(original)
    payload["summary"]["source_evidence"]["present_count"] += 1
    payload["horizons"][0]["assessment_summary"] = "unsupported summary"
    payload["horizons"][0]["evidence_refs"].append("proofs/unbound.json")
    payload["generator"]["sha256"] = "0" * 64
    present = next(
        record
        for record in payload["source_evidence"]["records"]
        if record["state"] == "present"
    )
    present["sha256"] = "f" * 64

    ok, issues = verify_payload(verifier, payload)

    assert ok is False
    assert "top_level_field_mismatch:summary" in issues
    assert "top_level_field_mismatch:generator" in issues
    assert "top_level_field_mismatch:source_evidence" in issues
    assert any(issue.endswith(":field_mismatch:assessment_summary") for issue in issues)
    assert any(issue.endswith(":field_mismatch:evidence_refs") for issue in issues)
    assert "source_evidence:evidence_refs_mismatch" in issues


def test_source_working_gate_requires_complete_explicit_working_catalog(
    tmp_path: Path,
) -> None:
    verifier = load_module(VERIFIER_PATH, "verify_horizon_readiness_source_gate")
    _, original = materialize_artifact(tmp_path)
    assert verifier.source_working_claim_allowed(original) is True

    incomplete = copy.deepcopy(original)
    incomplete["capabilities"][0]["source_status"] = "source_incomplete"
    assert verifier.source_working_claim_allowed(incomplete) is False

    uncovered = copy.deepcopy(original)
    uncovered["catalog_coverage"]["all_current_capabilities_assessed"] = False
    assert verifier.source_working_claim_allowed(uncovered) is False

    missing_record = copy.deepcopy(original)
    missing_record["horizons"].pop()
    assert verifier.source_working_claim_allowed(missing_record) is False

    missing_evidence = copy.deepcopy(original)
    missing_evidence["source_evidence"]["records"][0]["state"] = "missing"
    missing_evidence["source_evidence"]["records"][0]["sha256"] = None
    missing_evidence["source_evidence"]["present_count"] -= 1
    missing_evidence["source_evidence"]["missing_count"] += 1
    assert verifier.source_working_claim_allowed(missing_evidence) is False


def test_verifier_cli_separates_structural_truth_from_operational_readiness(
    tmp_path: Path,
) -> None:
    generated_at_utc = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    artifact, _ = materialize_artifact(tmp_path, generated_at_utc=generated_at_utc)
    base_command = [
        sys.executable,
        str(VERIFIER_PATH),
        "--artifact",
        str(artifact),
        "--repo-root",
        str(REPO_ROOT),
    ]

    structural = subprocess.run(
        base_command,
        check=False,
        capture_output=True,
        text=True,
    )
    source_working = subprocess.run(
        [*base_command, "--require-source-working"],
        check=False,
        capture_output=True,
        text=True,
    )
    strict = subprocess.run(
        [*base_command, "--require-operational-ready"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert structural.returncode == 0, structural.stdout + structural.stderr
    assert json.loads(structural.stdout)["status"] == "pass"
    assert source_working.returncode == 0, source_working.stdout + source_working.stderr
    assert json.loads(source_working.stdout)["source_working_claim_allowed"] is True
    assert strict.returncode == 1
    strict_payload = json.loads(strict.stdout)
    assert strict_payload["status"] == "fail"
    assert "operational_readiness_not_allowed" in strict_payload["issues"]


def test_verifier_cli_enforces_explicit_max_age_policy(tmp_path: Path) -> None:
    generated_at = datetime.now(UTC) - timedelta(seconds=5)
    artifact, _ = materialize_artifact(
        tmp_path,
        generated_at_utc=generated_at.isoformat().replace("+00:00", "Z"),
    )

    result = subprocess.run(
        [
            sys.executable,
            str(VERIFIER_PATH),
            "--artifact",
            str(artifact),
            "--repo-root",
            str(REPO_ROOT),
            "--max-age-seconds",
            "1",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "generated_at_utc_stale" in json.loads(result.stdout)["issues"]
