from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "verify_flagship_product_readiness_gate.py"


def load_module():
    spec = importlib.util.spec_from_file_location("verify_flagship_product_readiness_gate", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def passing_payload() -> dict[str, object]:
    return {
        "contract_name": "fleet.flagship_product_readiness",
        "generated_at": "2026-06-30T08:00:00Z",
        "status": "pass",
        "completion_audit": {"status": "pass"},
        "flagship_readiness_audit": {
            "status": "pass",
            "coverage_gap_keys": [],
            "scoped_coverage_gap_keys": [],
        },
        "summary": {
            "ready_count": 8,
            "missing_count": 0,
            "scoped_missing_count": 0,
            "warning_count": 0,
        },
    }


def test_summary_accepts_green_whole_product_readiness() -> None:
    module = load_module()

    summary = module.summarize(passing_payload())

    assert summary["pass"] is True
    assert summary["contract_name"] == "fleet.flagship_product_readiness"


def test_summary_rejects_missing_desktop_client_gap() -> None:
    module = load_module()
    payload = passing_payload()
    payload["status"] = "fail"
    payload["completion_audit"] = {"status": "fail"}
    payload["flagship_readiness_audit"] = {
        "status": "fail",
        "reason": "missing coverage: desktop_client",
        "coverage_gap_keys": ["desktop_client"],
        "scoped_coverage_gap_keys": ["desktop_client"],
    }
    payload["summary"] = {
        "ready_count": 7,
        "missing_count": 1,
        "scoped_missing_count": 1,
        "warning_count": 0,
    }

    summary = module.summarize(payload)

    assert summary["pass"] is False
    assert summary["coverage_gap_keys"] == ["desktop_client"]
    assert summary["scoped_missing_count"] == 1


def test_summary_subsumes_desktop_client_gap_when_only_windows_external_proof_is_missing(
    tmp_path,
    monkeypatch,
) -> None:
    module = load_module()
    published = tmp_path / "published"
    published.mkdir(parents=True, exist_ok=True)
    (published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json").write_text(
        json.dumps(
            {
                "contract_name": "chummer.windows_installer_visual_audit",
                "status": "fail",
                "failures": [
                    "Windows installer visual audit source digest does not match promoted installer",
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "DEFAULT_WINDOWS_INSTALLER_VISUAL_AUDIT", published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json")
    monkeypatch.setattr(module, "DEFAULT_RELEASE_CHANNEL", published / "RELEASE_CHANNEL.generated.json")
    monkeypatch.setattr(module, "DEFAULT_GOOGLE_OAUTH_LINKING_PROOF", published / "GOOGLE_OAUTH_LINKING_PROOF.generated.json")

    payload = passing_payload()
    payload["status"] = "fail"
    payload["completion_audit"] = {"status": "fail"}
    payload["flagship_readiness_audit"] = {
        "status": "fail",
        "reason": "missing coverage: desktop_client",
        "coverage_gap_keys": ["desktop_client"],
        "scoped_coverage_gap_keys": ["desktop_client"],
    }
    payload["summary"] = {
        "ready_count": 7,
        "missing_count": 0,
        "scoped_missing_count": 0,
        "warning_count": 1,
    }
    payload["coverage_details"] = {
        "fleet_and_operator_loop": {
            "status": "ready",
            "evidence": {
                "final_gold_janitor_path": "/tmp/final-gold.json",
            },
        },
        "desktop_client": {
            "status": "warning",
            "evidence": {
                "ui_executable_exit_gate_blocking_mode": "external_only",
                "ui_windows_exit_gate_blocking_mode": "external_only",
                "ui_linux_exit_gate_effective_ready": True,
                "ui_workflow_execution_gate_status": "pass",
                "ui_visual_familiarity_exit_gate_status": "pass",
                "ui_flagship_release_gate_status": "pass",
                "ui_external_host_proof_blockers_unresolved_hosts": ["windows"],
            },
        },
    }

    summary = module.summarize(payload)

    assert summary["pass"] is False
    assert summary["coverage_gap_keys"] == []
    assert summary["scoped_coverage_gap_keys"] == []
    assert summary["launch_critical_nested_blockers"] == [
        "Windows installer visual audit source digest does not match promoted installer",
    ]
    assert "Coverage gaps: desktop_client" not in summary["reason"]


def test_summary_rejects_launch_critical_nested_failures() -> None:
    module = load_module()
    payload = passing_payload()
    payload["coverage_details"] = {
        "fleet_and_operator_loop": {
            "status": "ready",
            "evidence": {
                "final_gold_janitor_state": "fail",
                "final_gold_janitor_verdict": "NOT_GOLD",
                "live_backed_gold_claim_allowed": False,
                "supervisor_completion_status": "fail",
                "supervisor_recent_enough": False,
            },
        },
    }

    summary = module.summarize(payload)

    assert summary["pass"] is False
    assert summary["launch_critical_nested_blocker_count"] == 5
    assert "final gold janitor verdict is 'NOT_GOLD'" in summary["launch_critical_nested_blockers"]
    assert "supervisor completion evidence is stale" in summary["launch_critical_nested_blockers"]


def test_summary_ignores_recovered_supervisor_staleness() -> None:
    module = load_module()
    payload = passing_payload()
    payload["readiness_planes"] = {
        "structural_ready": {
            "evidence": {
                "supervisor_recent_enough": True,
                "supervisor_current_readiness_recovery": True,
            },
        },
    }
    payload["coverage_details"] = {
        "fleet_and_operator_loop": {
            "status": "ready",
            "evidence": {
                "final_gold_janitor_state": "fail",
                "final_gold_janitor_verdict": "NOT_GOLD",
                "live_backed_gold_claim_allowed": False,
                "supervisor_completion_status": "fail",
                "supervisor_recent_enough": False,
                "supervisor_completion_status_recovered_from_current_readiness": True,
            },
        },
    }

    summary = module.summarize(payload)

    assert summary["pass"] is False
    assert summary["launch_critical_nested_blocker_count"] == 3
    assert "supervisor completion status is 'fail'" not in summary["launch_critical_nested_blockers"]
    assert "supervisor completion evidence is stale" not in summary["launch_critical_nested_blockers"]
    assert "live-backed gold claim is not allowed" in summary["launch_critical_nested_blockers"]


def test_fail_closed_readiness_payload_overrides_pass_shaped_nested_blockers() -> None:
    module = load_module()
    payload = passing_payload()
    payload["scoped_status"] = "pass"
    payload["coverage_details"] = {
        "fleet_and_operator_loop": {
            "evidence": {
                "final_gold_janitor_state": "fail",
                "final_gold_janitor_verdict": "NOT_GOLD",
                "live_backed_gold_claim_allowed": False,
            },
        },
    }
    summary = module.summarize(payload)

    updated, changed = module.fail_closed_readiness_payload(payload, summary, "2026-07-02T08:10:00Z")

    assert changed is True
    assert updated["status"] == "fail"
    assert updated["scoped_status"] == "fail"
    assert updated["gate_status_override"]["raw_status"] == "pass"
    assert updated["gate_status_override"]["raw_scoped_status"] == "pass"
    assert "live-backed gold claim is not allowed" in updated["gate_status_override"]["launch_critical_nested_blockers"]
    assert "Launch-critical nested blockers or coverage gaps remain" in updated["gate_status_override"]["effective_reason"]
    assert "final gold janitor verdict is 'NOT_GOLD'" in updated["gate_status_override"]["effective_reason"]


def test_summary_replaces_release_wrapper_blockers_with_concrete_release_ready_failures_when_available(
    tmp_path,
    monkeypatch,
) -> None:
    module = load_module()
    published = tmp_path / "published"
    published.mkdir(parents=True, exist_ok=True)
    (published / "RELEASE_READY.generated.json").write_text(
        json.dumps(
            {
                "contract_name": "chummer.release_ready",
                "status": "fail",
                "failed_gates": ["release_channel", "google_oauth_linking_proof", "windows_installer_visual_audit"],
                "failures": [
                    "FAIL release_channel: release channel channel is preview, not a flagship stable lane",
                    "FAIL release_channel: release channel supportability is not gold_supported",
                    "FAIL release_channel: release channel rollout is promoted_preview, not public_stable",
                    "FAIL google_oauth_linking_proof: operator_end_to_end_evidence: missing operator evidence receipt: /tmp/operator-evidence.json",
                    "FAIL google_oauth_linking_proof: operator_request_artifacts: operator ask delivery is stale; resend current ask: python3 resend-google",
                    "FAIL windows_installer_visual_audit: Windows installer visual audit source digest does not match promoted installer",
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "PUBLISHED_ROOT", published)
    monkeypatch.setattr(module, "DEFAULT_GOOGLE_OAUTH_LINKING_PROOF", published / "GOOGLE_OAUTH_LINKING_PROOF.generated.json")
    monkeypatch.setattr(module, "DEFAULT_WINDOWS_INSTALLER_VISUAL_AUDIT", published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json")
    monkeypatch.setattr(module, "DEFAULT_RELEASE_CHANNEL", published / "RELEASE_CHANNEL.generated.json")

    payload = passing_payload()
    payload["coverage_details"] = {
        "fleet_and_operator_loop": {
            "status": "ready",
            "evidence": {
                "final_gold_janitor_path": "/tmp/final-gold.json",
                "final_gold_janitor_state": "fail",
                "final_gold_janitor_verdict": "NOT_GOLD",
                "live_backed_gold_claim_allowed": False,
            },
        },
    }

    summary = module.summarize(payload)

    assert summary["pass"] is False
    assert summary["launch_critical_nested_blockers"] == [
        "release channel channel is preview, not a flagship stable lane",
        "release channel supportability is not gold_supported",
        "release channel rollout is promoted_preview, not public_stable",
        "operator_end_to_end_evidence: missing operator evidence receipt: /tmp/operator-evidence.json",
        "operator_request_artifacts: operator ask delivery is stale; resend current ask: python3 resend-google",
        "Windows installer visual audit source digest does not match promoted installer",
    ]
    assert "release channel channel is preview, not a flagship stable lane" in summary["reason"]
    assert "operator_end_to_end_evidence: missing operator evidence receipt: /tmp/operator-evidence.json" in summary["reason"]
    assert "operator_request_artifacts: operator ask delivery is stale; resend current ask: python3 resend-google" in summary["reason"]
    assert "Windows installer visual audit source digest does not match promoted installer" in summary["reason"]
    assert "final gold janitor verdict is 'NOT_GOLD'" not in summary["reason"]


def test_summary_prefers_current_release_truth_receipts_over_stale_release_ready_wrapper(
    tmp_path,
    monkeypatch,
) -> None:
    module = load_module()
    published = tmp_path / "published"
    published.mkdir(parents=True, exist_ok=True)
    registry_published = tmp_path / "registry-published"
    registry_published.mkdir(parents=True, exist_ok=True)

    (published / "RELEASE_READY.generated.json").write_text(
        json.dumps(
            {
                "contract_name": "chummer.release_ready",
                "status": "fail",
                "failed_gates": ["release_channel", "windows_installer_visual_audit"],
                "failures": [
                    "FAIL release_channel: release channel channel is preview, not a flagship stable lane",
                    "FAIL release_channel: release channel supportability is not gold_supported",
                    "FAIL release_channel: release channel rollout is promoted_preview, not public_stable",
                    "FAIL windows_installer_visual_audit: Windows installer visual audit source digest does not match promoted installer",
                ],
            }
        ),
        encoding="utf-8",
    )
    (published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json").write_text(
        json.dumps(
            {
                "contract_name": "chummer.windows_installer_visual_audit",
                "status": "pass",
                "summary": {
                    "reason": "Current promoted installer visual audit is complete."
                },
            }
        ),
        encoding="utf-8",
    )
    (published / "GOOGLE_OAUTH_LINKING_PROOF.generated.json").write_text(
        json.dumps(
            {
                "contract_name": "chummer.run.google_oauth_linking_proof",
                "status": "fail",
                "operator_end_to_end_evidence": {
                    "pass": False,
                    "exists": False,
                    "path": "/tmp/operator-evidence.json",
                    "failures": [
                        "missing operator evidence receipt: /tmp/operator-evidence.json",
                    ],
                },
                "operator_request_artifacts": {
                    "required_operator_evidence_path": "/tmp/operator-evidence.json",
                    "operator_ask_delivery_needs_resend": True,
                    "operator_ask_resend_command": "python3 resend-google",
                },
                "failures": [
                    "operator_end_to_end_evidence: missing operator evidence receipt: /tmp/operator-evidence.json",
                ],
            }
        ),
        encoding="utf-8",
    )
    (registry_published / "RELEASE_CHANNEL.generated.json").write_text(
        json.dumps(
            {
                "contract_name": "chummer.release_channel",
                "status": "published",
                "version": "run-20260704-032419",
                "channel": "preview",
                "supportabilityState": "preview_supported",
                "rolloutState": "promoted_preview",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "PUBLISHED_ROOT", published)
    monkeypatch.setattr(module, "DEFAULT_GOOGLE_OAUTH_LINKING_PROOF", published / "GOOGLE_OAUTH_LINKING_PROOF.generated.json")
    monkeypatch.setattr(module, "DEFAULT_WINDOWS_INSTALLER_VISUAL_AUDIT", published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json")
    monkeypatch.setattr(module, "DEFAULT_RELEASE_CHANNEL", registry_published / "RELEASE_CHANNEL.generated.json")

    payload = passing_payload()
    payload["coverage_details"] = {
        "fleet_and_operator_loop": {
            "status": "ready",
            "evidence": {
                "final_gold_janitor_path": "/tmp/final-gold.json",
                "final_gold_janitor_state": "fail",
                "final_gold_janitor_verdict": "NOT_GOLD",
                "live_backed_gold_claim_allowed": False,
            },
        },
    }

    summary = module.summarize(payload)

    assert summary["pass"] is False
    assert summary["launch_critical_nested_blockers"] == [
        "release channel channel is preview, not a flagship stable lane",
        "release channel supportability is not gold_supported",
        "release channel rollout is promoted_preview, not public_stable",
        "google oauth operator evidence is still missing: /tmp/operator-evidence.json",
        "google oauth operator ask delivery is stale; resend current ask: python3 resend-google",
    ]
    assert "Windows installer visual audit source digest does not match promoted installer" not in summary["reason"]
    assert "google oauth operator evidence is still missing: /tmp/operator-evidence.json" in summary["reason"]
    assert "google oauth operator ask delivery is stale; resend current ask: python3 resend-google" in summary["reason"]
    assert "final gold janitor verdict is 'NOT_GOLD'" not in summary["reason"]


def test_main_skip_materialize_fails_closed_and_writes_summary(tmp_path, monkeypatch) -> None:
    module = load_module()
    readiness = tmp_path / "FLAGSHIP_PRODUCT_READINESS.generated.json"
    summary_path = tmp_path / "summary.json"
    payload = passing_payload()
    payload["status"] = "fail"
    payload["flagship_readiness_audit"] = {
        "status": "fail",
        "reason": "missing coverage: desktop_client",
        "coverage_gap_keys": ["desktop_client"],
        "scoped_coverage_gap_keys": ["desktop_client"],
    }
    payload["summary"] = {"ready_count": 7, "missing_count": 1, "scoped_missing_count": 1}
    readiness.write_text(json.dumps(payload), encoding="utf-8")

    monkeypatch.setattr(
        "sys.argv",
        [
            "verify_flagship_product_readiness_gate.py",
            "--skip-materialize",
            "--readiness",
            str(readiness),
            "--summary-output",
            str(summary_path),
        ],
    )

    assert module.main() == 1
    written = json.loads(summary_path.read_text(encoding="utf-8"))
    rewritten = json.loads(readiness.read_text(encoding="utf-8"))
    assert written["status"] == "fail"
    assert written["pass"] is False
    assert written["readiness_receipt_fail_closed"] is True
    assert written["generated_at_utc"]
    assert written["coverage_gap_keys"] == ["desktop_client"]
    assert written["scoped_coverage_gap_keys"] == ["desktop_client"]
    assert written["summary"]["coverage_gap_keys"] == ["desktop_client"]
    assert rewritten["status"] == "fail"
    assert rewritten["gate_status_override"]["raw_status"] == "fail"


def test_main_skip_materialize_reports_missing_readiness_receipt_structurally(tmp_path, monkeypatch) -> None:
    module = load_module()
    readiness = tmp_path / "FLAGSHIP_PRODUCT_READINESS.generated.json"
    summary_path = tmp_path / "summary.json"
    monkeypatch.setattr(
        "sys.argv",
        [
            "verify_flagship_product_readiness_gate.py",
            "--skip-materialize",
            "--readiness",
            str(readiness),
            "--summary-output",
            str(summary_path),
        ],
    )

    assert module.main() == 1
    written = json.loads(summary_path.read_text(encoding="utf-8"))
    assert written["status"] == "fail"
    assert written["pass"] is False
    assert written["readiness_receipt_fail_closed"] is False
    assert written["readiness_load_status"] == "missing"
    assert written["reason"] == f"flagship readiness receipt is missing: {readiness}"
    assert written["summary"]["readiness_load_status"] == "missing"


def test_main_skip_materialize_reports_malformed_readiness_receipt_structurally(tmp_path, monkeypatch) -> None:
    module = load_module()
    readiness = tmp_path / "FLAGSHIP_PRODUCT_READINESS.generated.json"
    summary_path = tmp_path / "summary.json"
    readiness.write_text("{not json}\n", encoding="utf-8")
    monkeypatch.setattr(
        "sys.argv",
        [
            "verify_flagship_product_readiness_gate.py",
            "--skip-materialize",
            "--readiness",
            str(readiness),
            "--summary-output",
            str(summary_path),
        ],
    )

    assert module.main() == 1
    written = json.loads(summary_path.read_text(encoding="utf-8"))
    assert written["status"] == "fail"
    assert written["pass"] is False
    assert written["readiness_receipt_fail_closed"] is False
    assert written["readiness_load_status"] == "invalid"
    assert written["reason"] == f"flagship readiness receipt is malformed: {readiness}"
    assert written["summary"]["readiness_load_status"] == "invalid"


def test_main_rewrites_pass_shaped_readiness_when_nested_blockers_remain(tmp_path, monkeypatch) -> None:
    module = load_module()
    readiness = tmp_path / "FLAGSHIP_PRODUCT_READINESS.generated.json"
    summary_path = tmp_path / "summary.json"
    payload = passing_payload()
    payload["coverage_details"] = {
        "fleet_and_operator_loop": {
            "evidence": {
                "final_gold_janitor_state": "fail",
                "final_gold_janitor_verdict": "NOT_GOLD",
                "live_backed_gold_claim_allowed": False,
            },
        },
    }
    readiness.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(
        "sys.argv",
        [
            "verify_flagship_product_readiness_gate.py",
            "--skip-materialize",
            "--readiness",
            str(readiness),
            "--summary-output",
            str(summary_path),
        ],
    )

    assert module.main() == 1
    written = json.loads(summary_path.read_text(encoding="utf-8"))
    rewritten = json.loads(readiness.read_text(encoding="utf-8"))
    assert written["pass"] is False
    assert written["readiness_receipt_fail_closed"] is True
    assert "final gold janitor state is 'fail'" in written["launch_critical_nested_blockers"]
    assert "final gold janitor verdict is 'NOT_GOLD'" in written["reason"]
    assert rewritten["status"] == "fail"
    assert rewritten["gate_status_override"]["raw_status"] == "pass"
    assert "final gold janitor state is 'fail'" in rewritten["gate_status_override"]["launch_critical_nested_blockers"]
    assert "Launch-critical nested blockers or coverage gaps remain" in written["summary"]["reason"]
    assert "final gold janitor verdict is 'NOT_GOLD'" in written["summary"]["reason"]


def test_summary_surfaces_malformed_google_oauth_linking_proof_receipt(tmp_path, monkeypatch) -> None:
    module = load_module()
    published = tmp_path / "published"
    published.mkdir(parents=True, exist_ok=True)
    registry_published = tmp_path / "registry-published"
    registry_published.mkdir(parents=True, exist_ok=True)

    google_receipt = published / "GOOGLE_OAUTH_LINKING_PROOF.generated.json"
    google_receipt.write_text("{not json}\n", encoding="utf-8")
    (published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json").write_text(
        json.dumps(
            {
                "contract_name": "chummer.windows_installer_visual_audit",
                "status": "pass",
            }
        ),
        encoding="utf-8",
    )
    (registry_published / "RELEASE_CHANNEL.generated.json").write_text(
        json.dumps(
            {
                "contract_name": "chummer.release_channel",
                "status": "published",
                "version": "run-20260705-100000",
                "channel": "stable",
                "supportabilityState": "gold_supported",
                "rolloutState": "public_stable",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "DEFAULT_GOOGLE_OAUTH_LINKING_PROOF", google_receipt)
    monkeypatch.setattr(module, "DEFAULT_WINDOWS_INSTALLER_VISUAL_AUDIT", published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json")
    monkeypatch.setattr(module, "DEFAULT_RELEASE_CHANNEL", registry_published / "RELEASE_CHANNEL.generated.json")

    payload = passing_payload()
    payload["coverage_details"] = {
        "fleet_and_operator_loop": {
            "status": "ready",
            "evidence": {
                "final_gold_janitor_path": "/tmp/final-gold.json",
            },
        },
    }

    summary = module.summarize(payload)

    assert summary["pass"] is False
    assert summary["launch_critical_nested_blockers"] == [
        f"google oauth linking proof receipt is malformed: {google_receipt}",
    ]
    assert summary["reason"] == (
        f"Launch blockers: google oauth linking proof receipt is malformed: {google_receipt}."
    )


def test_main_writes_default_published_summary_output(tmp_path, monkeypatch) -> None:
    module = load_module()
    readiness = tmp_path / "FLAGSHIP_PRODUCT_READINESS.generated.json"
    default_summary = tmp_path / "FLAGSHIP_PRODUCT_READINESS_GATE.generated.json"
    payload = passing_payload()
    readiness.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(module, "DEFAULT_SUMMARY_OUTPUT", default_summary)
    monkeypatch.setattr(
        "sys.argv",
        [
            "verify_flagship_product_readiness_gate.py",
            "--skip-materialize",
            "--readiness",
            str(readiness),
        ],
    )

    assert module.main() == 0
    written = json.loads(default_summary.read_text(encoding="utf-8"))
    assert written["status"] == "pass"
    assert written["pass"] is True
    assert written["readiness_receipt_fail_closed"] is False
    assert written["launch_critical_nested_blockers"] == []
    assert written["launch_critical_nested_blocker_count"] == 0
    assert written["coverage_gap_keys"] == []
    assert written["scoped_coverage_gap_keys"] == []
    assert written["generated_at_utc"]
