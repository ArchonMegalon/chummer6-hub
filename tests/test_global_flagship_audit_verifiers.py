from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def test_support_submitted_route_rejects_malformed_unknown_ids() -> None:
    controller = read("Chummer.Run.Api/Controllers/PublicLandingController.cs")
    assert 'caseId.StartsWith("support_case_", StringComparison.OrdinalIgnoreCase)' in controller
    assert 'string.Equals(caseId, "sample-case-id", StringComparison.OrdinalIgnoreCase)' in controller


def test_global_audit_verifier_scripts_exist() -> None:
    assert (REPO_ROOT / "scripts" / "route_proof_semantics_gate.py").is_file()
    assert (REPO_ROOT / "scripts" / "live_public_surface_audit.py").is_file()
    assert (REPO_ROOT / "scripts" / "classify_ruleset_readiness.py").is_file()
    assert (REPO_ROOT / "scripts" / "public_copy_truth_gate.py").is_file()
    assert (REPO_ROOT / "scripts" / "public_asset_quality_gate.py").is_file()
    assert (REPO_ROOT / "scripts" / "final_chummer_run_ux_verdict.py").is_file()
    assert (REPO_ROOT / "scripts" / "ledger_stats_privacy_gate.py").is_file()
    assert (REPO_ROOT / "scripts" / "black_ledger_world_tick_e2e.py").is_file()
    assert (REPO_ROOT / "scripts" / "black_ledger_dispatch_e2e.py").is_file()
    assert (REPO_ROOT / "scripts" / "black_ledger_ai_stewardship_gate.py").is_file()
    assert (REPO_ROOT / "scripts" / "black_ledger_send_tick_news.py").is_file()
    assert (REPO_ROOT / "scripts" / "audit_black_ledger_feature_completion.py").is_file()
    assert (REPO_ROOT / "scripts" / "public_ip_privacy_scan.py").is_file()
    assert (REPO_ROOT / "scripts" / "release_dress_rehearsal.sh").is_file()
