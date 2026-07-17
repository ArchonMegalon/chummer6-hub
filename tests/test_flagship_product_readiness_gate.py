from __future__ import annotations

import hashlib
import importlib.util
import json
from datetime import UTC, datetime, timedelta
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


def privacy_launch_gate_payload(*, review_required: bool) -> dict[str, object]:
    return {
        "contractName": "chummer.privacy_launch_gate",
        "contractVersion": 1,
        "status": "review_required" if review_required else "documented",
        "reviewRequired": review_required,
        "scope": "flagship_launch_and_release_supportability",
        "blockedClaims": (
            [
                "flagship_launch",
                "public_release_supportability",
                "hosted_build_recovery_and_erasure",
            ]
            if review_required
            else []
        ),
        "reason": (
            "Hosted Build recovery and erasure policy is still under review."
            if review_required
            else "Hosted Build recovery and erasure policy is approved and verified."
        ),
    }


HOSTED_BUILD_OPERATOR_DECISION_IDS = [
    "quota_policy",
    "logical_bytes",
    "recreation_and_undo",
    "offline_compatibility",
    "tombstone_privacy_policy",
    "stable_owner_identity",
    "writer_epoch",
    "delete_replay_and_rpo",
    "provider_and_topology",
    "enforcement_boundary",
    "migration_posture",
    "capacity_and_retention",
]


def hosted_build_operator_decisions_payload(*, review_required: bool) -> dict[str, object]:
    presentation_root = SCRIPT_PATH.parents[2] / "chummer-presentation"
    source_digest = "sha256:" + hashlib.sha256(
        (presentation_root / "docs" / "HOSTED_BUILD_WORKSPACE_LIFECYCLE_AND_QUOTA_CONTRACT.md").read_bytes()
    ).hexdigest()
    packet_digest = "sha256:" + hashlib.sha256(
        (
            presentation_root
            / ".codex-design"
            / "product"
            / "HOSTED_BUILD_V002_OPERATOR_DECISIONS.json"
        ).read_bytes()
    ).hexdigest()
    approval_registry_digest = "sha256:" + hashlib.sha256(
        (
            presentation_root
            / ".codex-design"
            / "product"
            / "HOSTED_BUILD_V002_APPROVAL_KEY_REGISTRY.json"
        ).read_bytes()
    ).hexdigest()
    return {
        "contractName": "chummer.hosted_build_v002_operator_decision_gate",
        "contractVersion": 1,
        "generatedAtUtc": "2026-07-15T10:00:00Z",
        "status": "review_required" if review_required else "pass",
        "reviewRequired": review_required,
        "decisionGatePassed": not review_required,
        "canonicalProvenance": True,
        "scope": "hosted_build_workspace_lifecycle_and_quota_v002",
        "candidateReleaseIdentity": None,
        "sourceContract": {
            "path": "docs/HOSTED_BUILD_WORKSPACE_LIFECYCLE_AND_QUOTA_CONTRACT.md",
            "sha256": source_digest,
        },
        "approvalKeyRegistry": {
            "path": ".codex-design/product/HOSTED_BUILD_V002_APPROVAL_KEY_REGISTRY.json",
            "sha256": approval_registry_digest,
            "status": "unconfigured" if review_required else "active",
            "activeKeyCount": 0 if review_required else 1,
        },
        "packet": {
            "path": ".codex-design/product/HOSTED_BUILD_V002_OPERATOR_DECISIONS.json",
            "sha256": packet_digest,
        },
        "decisionCount": 12,
        "approvedDecisionIds": [] if review_required else HOSTED_BUILD_OPERATOR_DECISION_IDS,
        "unresolvedDecisionIds": HOSTED_BUILD_OPERATOR_DECISION_IDS if review_required else [],
        "invalidDecisionIds": [],
        "blockedClaims": (
            [
                "flagship_launch",
                "public_release_supportability",
                "hosted_build_v002_contract_freeze",
                "hosted_build_v002_authoring",
                "hosted_build_v002_migration",
                "hosted_build_production_launch",
            ]
            if review_required
            else []
        ),
        "doesNotAuthorize": [
            "hosted_build_v002_authoring",
            "hosted_build_v002_application",
            "quota_enforcement",
            "tombstone_deletion",
            "hosted_build_production_launch",
            "public_recovery_or_retention_claims",
        ],
        "blockers": (
            ["hosted_build_v002_operator_decisions_unresolved"]
            if review_required
            else []
        ),
        "validationErrors": [],
        "reason": (
            "Hosted Build V002 operator decisions remain unresolved: "
            + ", ".join(HOSTED_BUILD_OPERATOR_DECISION_IDS)
            + "."
            if review_required
            else "Hosted Build V002 operator decisions are explicit and evidence-bound; separate launch gates remain."
        ),
    }


def write_clear_privacy_launch_gate(path: Path) -> None:
    path.write_text(
        json.dumps(privacy_launch_gate_payload(review_required=False)),
        encoding="utf-8",
    )


def write_clear_hosted_build_operator_decisions(path: Path) -> None:
    path.write_text(
        json.dumps(hosted_build_operator_decisions_payload(review_required=False)),
        encoding="utf-8",
    )


def write_fresh_root_release_blockers(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "generated_at": datetime.now(UTC)
                .replace(microsecond=0)
                .isoformat()
                .replace("+00:00", "Z"),
                "root_blockers": [],
            }
        ),
        encoding="utf-8",
    )


def test_summary_accepts_green_whole_product_readiness() -> None:
    module = load_module()

    summary = module.summarize(passing_payload())

    assert summary["pass"] is True
    assert summary["contract_name"] == "fleet.flagship_product_readiness"


def test_privacy_review_blocks_flagship_readiness_with_explicit_reason(tmp_path) -> None:
    module = load_module()
    gate_path = tmp_path / "privacy-launch-gate.json"
    gate = privacy_launch_gate_payload(review_required=True)

    summary = module.summarize(
        passing_payload(),
        privacy_launch_gate_payload=gate,
        privacy_launch_gate_load_status="loaded",
        privacy_launch_gate_path=gate_path,
    )

    assert summary["pass"] is False
    assert summary["launch_critical_nested_blockers"] == [gate["reason"]]
    assert summary["privacy_launch_gate"]["review_required"] is True
    assert summary["privacy_launch_gate"]["scope"] == "flagship_launch_and_release_supportability"


def test_clear_privacy_contract_does_not_block_flagship_readiness(tmp_path) -> None:
    module = load_module()
    gate_path = tmp_path / "privacy-launch-gate.json"

    summary = module.summarize(
        passing_payload(),
        privacy_launch_gate_payload=privacy_launch_gate_payload(review_required=False),
        privacy_launch_gate_load_status="loaded",
        privacy_launch_gate_path=gate_path,
    )

    assert summary["pass"] is True
    assert summary["privacy_launch_gate"]["pass"] is True
    assert summary["privacy_launch_gate"]["blockers"] == []


def test_missing_malformed_or_wrong_version_privacy_contract_fails_closed(tmp_path) -> None:
    module = load_module()
    gate_path = tmp_path / "privacy-launch-gate.json"
    wrong_version = privacy_launch_gate_payload(review_required=False)
    wrong_version["contractVersion"] = 2
    scenarios = [
        ({}, "missing", "receipt is missing"),
        ({}, "invalid", "receipt is malformed"),
        (wrong_version, "loaded", "contractVersion must be 1"),
    ]

    for gate, load_status, expected in scenarios:
        summary = module.summarize(
            passing_payload(),
            privacy_launch_gate_payload=gate,
            privacy_launch_gate_load_status=load_status,
            privacy_launch_gate_path=gate_path,
        )
        assert summary["pass"] is False
        assert any(expected in blocker for blocker in summary["launch_critical_nested_blockers"])


def test_unresolved_hosted_build_decisions_block_with_structured_ids(tmp_path) -> None:
    module = load_module()
    gate_path = tmp_path / "hosted-build-decisions.json"
    gate = hosted_build_operator_decisions_payload(review_required=True)

    summary = module.summarize(
        passing_payload(),
        privacy_launch_gate_payload=privacy_launch_gate_payload(review_required=False),
        privacy_launch_gate_load_status="loaded",
        privacy_launch_gate_path=tmp_path / "privacy.json",
        hosted_build_operator_decisions_payload=gate,
        hosted_build_operator_decisions_load_status="loaded",
        hosted_build_operator_decisions_path=gate_path,
    )

    assert summary["pass"] is False
    assert summary["launch_critical_nested_blockers"] == [gate["reason"]]
    structured = summary["hosted_build_operator_decisions"]
    assert structured["review_required"] is True
    assert structured["unresolved_decision_ids"] == HOSTED_BUILD_OPERATOR_DECISION_IDS
    assert structured["validation_failures"] == []


def test_repository_hosted_build_decision_receipt_is_review_required() -> None:
    module = load_module()
    receipt_path = module.DEFAULT_HOSTED_BUILD_OPERATOR_DECISIONS
    receipt, load_status = module.load_json(receipt_path)

    evaluated = module.evaluate_hosted_build_operator_decisions(
        receipt,
        load_status,
        receipt_path,
    )

    assert load_status == "loaded"
    assert evaluated["status"] == "review_required"
    assert evaluated["unresolved_decision_ids"] == HOSTED_BUILD_OPERATOR_DECISION_IDS
    assert evaluated["validation_failures"] == []
    assert evaluated["pass"] is False
    assert evaluated["canonical_provenance"] is True


def test_hand_edited_derived_decision_receipt_cannot_self_clear_or_change_reason() -> None:
    module = load_module()
    receipt_path = module.DEFAULT_HOSTED_BUILD_OPERATOR_DECISIONS
    receipt, load_status = module.load_json(receipt_path)
    receipt["reason"] = "Hand-edited optimistic decision claim."

    evaluated = module.evaluate_hosted_build_operator_decisions(
        receipt,
        load_status,
        receipt_path,
    )

    assert evaluated["pass"] is False
    assert "derived_receipt_material_mismatch" in evaluated["validation_failures"]
    assert evaluated["blockers"] == [
        "Hosted Build V002 operator decision gate receipt is missing, malformed, or internally inconsistent."
    ]


def test_noncanonical_decision_receipt_is_rejected_even_when_material_checks_are_disabled(
    tmp_path,
) -> None:
    module = load_module()
    receipt = hosted_build_operator_decisions_payload(review_required=True)
    receipt["canonicalProvenance"] = False

    evaluated = module.evaluate_hosted_build_operator_decisions(
        receipt,
        "loaded",
        tmp_path / "decision.json",
        verify_material_bindings=False,
    )

    assert evaluated["pass"] is False
    assert "canonical_provenance_required" in evaluated["validation_failures"]


def test_future_decision_receipt_trust_clock_is_rejected(tmp_path) -> None:
    module = load_module()
    receipt = hosted_build_operator_decisions_payload(review_required=True)
    receipt["generatedAtUtc"] = "2099-01-01T00:00:00Z"

    evaluated = module.evaluate_hosted_build_operator_decisions(
        receipt,
        "loaded",
        tmp_path / "decision.json",
        verify_material_bindings=False,
    )

    assert evaluated["pass"] is False
    assert "generated_at_utc_future" in evaluated["validation_failures"]


def test_stale_decision_receipt_trust_clock_is_rejected(tmp_path) -> None:
    module = load_module()
    receipt = hosted_build_operator_decisions_payload(review_required=True)
    receipt["generatedAtUtc"] = "2000-01-01T00:00:00Z"

    evaluated = module.evaluate_hosted_build_operator_decisions(
        receipt,
        "loaded",
        tmp_path / "decision.json",
        verify_material_bindings=False,
    )

    assert evaluated["pass"] is False
    assert "generated_at_utc_stale" in evaluated["validation_failures"]


def test_clear_decision_gate_does_not_clear_review_required_privacy_gate(tmp_path) -> None:
    module = load_module()
    privacy = privacy_launch_gate_payload(review_required=True)

    summary = module.summarize(
        passing_payload(),
        privacy_launch_gate_payload=privacy,
        privacy_launch_gate_load_status="loaded",
        privacy_launch_gate_path=tmp_path / "privacy.json",
        hosted_build_operator_decisions_payload=hosted_build_operator_decisions_payload(
            review_required=False
        ),
        hosted_build_operator_decisions_load_status="loaded",
        hosted_build_operator_decisions_path=tmp_path / "hosted-build-decisions.json",
        hosted_build_operator_decisions_verify_material_bindings=False,
    )

    assert summary["pass"] is False
    assert summary["launch_critical_nested_blockers"] == [
        privacy["reason"],
        module.HOSTED_BUILD_IMPLEMENTATION_GATE_REQUIRED_REASON,
    ]
    assert summary["hosted_build_operator_decisions"]["decision_gate_passed"] is True
    assert summary["hosted_build_operator_decisions"]["pass"] is False
    assert summary["privacy_launch_gate"]["pass"] is False


def test_clear_privacy_and_decision_freeze_still_require_implementation_gate(tmp_path) -> None:
    module = load_module()

    summary = module.summarize(
        passing_payload(),
        privacy_launch_gate_payload=privacy_launch_gate_payload(review_required=False),
        privacy_launch_gate_load_status="loaded",
        privacy_launch_gate_path=tmp_path / "privacy.json",
        hosted_build_operator_decisions_payload=hosted_build_operator_decisions_payload(
            review_required=False
        ),
        hosted_build_operator_decisions_load_status="loaded",
        hosted_build_operator_decisions_path=tmp_path / "hosted-build-decisions.json",
        hosted_build_operator_decisions_verify_material_bindings=False,
    )

    assert summary["pass"] is False
    assert summary["hosted_build_operator_decisions"]["decision_gate_passed"] is True
    assert summary["launch_critical_nested_blockers"] == [
        module.HOSTED_BUILD_IMPLEMENTATION_GATE_REQUIRED_REASON
    ]


def test_missing_malformed_or_wrong_decision_receipt_fails_closed(tmp_path) -> None:
    module = load_module()
    gate_path = tmp_path / "hosted-build-decisions.json"
    wrong_contract = hosted_build_operator_decisions_payload(review_required=False)
    wrong_contract["contractName"] = "wrong.contract"
    scenarios = [
        ({}, "missing", "receipt_missing"),
        ({}, "invalid", "receipt_malformed"),
        (wrong_contract, "loaded", "contract_name_invalid"),
    ]

    for gate, load_status, expected_failure in scenarios:
        summary = module.summarize(
            passing_payload(),
            privacy_launch_gate_payload=privacy_launch_gate_payload(review_required=False),
            privacy_launch_gate_load_status="loaded",
            privacy_launch_gate_path=tmp_path / "privacy.json",
            hosted_build_operator_decisions_payload=gate,
            hosted_build_operator_decisions_load_status=load_status,
            hosted_build_operator_decisions_path=gate_path,
        )
        assert summary["pass"] is False
        structured = summary["hosted_build_operator_decisions"]
        assert expected_failure in structured["validation_failures"]
        assert summary["launch_critical_nested_blockers"] == [
            "Hosted Build V002 operator decision gate receipt is missing, malformed, or internally inconsistent."
        ]


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
    assert summary["missing_count"] == 0
    assert summary["scoped_missing_count"] == 0
    assert "Windows installer visual audit source digest does not match promoted installer" in summary[
        "launch_critical_nested_blockers"
    ]
    assert "Coverage gaps: desktop_client" not in summary["reason"]


def test_summary_subsumes_desktop_client_gap_when_only_release_posture_blockers_remain(
    monkeypatch,
) -> None:
    module = load_module()
    monkeypatch.setattr(
        module,
        "current_release_truth_launch_blockers",
        lambda: [
            "release channel supportability is not gold_supported",
            "release channel rollout is public_release_review_required, not public_stable",
        ],
    )

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
    payload["coverage_details"] = {
        "fleet_and_operator_loop": {
            "status": "ready",
            "evidence": {
                "final_gold_janitor_path": "/tmp/final-gold.json",
            },
        },
        "desktop_client": {
            "status": "missing",
            "evidence": {
                "ui_executable_exit_gate_blocking_mode": "mixed_or_local",
                "ui_windows_exit_gate_blocking_mode": "none",
                "ui_linux_exit_gate_effective_ready": True,
                "ui_windows_exit_gate_effective_ready": True,
                "ui_workflow_execution_gate_status": "pass",
                "ui_visual_familiarity_exit_gate_status": "pass",
                "ui_flagship_release_gate_status": "pass",
                "ui_external_host_proof_blockers_unresolved_hosts": [],
                "ui_executable_exit_gate_effective_local_blocking_findings_count": 4,
                "ui_executable_exit_gate_effective_local_blocking_findings": [
                    "Release channel rolloutState is not a recognized registry rollout posture for desktop install media: public_release_review_required.",
                    "Release channel rolloutState must be local_docker_preview/promoted_preview/release_candidate/public_stable/stable when status is publishable and required desktop tuple coverage is complete.",
                    "Release channel supportabilityState must be local_docker_proven/preview_supported/gold_supported when status is publishable and required desktop tuple coverage is complete.",
                    "Release channel supportabilityState cannot remain review_required when required desktop tuple coverage is complete.",
                ],
            },
        },
    }

    summary = module.summarize(payload)

    assert summary["pass"] is False
    assert summary["coverage_gap_keys"] == []
    assert summary["scoped_coverage_gap_keys"] == []
    assert summary["missing_count"] == 0
    assert summary["scoped_missing_count"] == 0
    assert summary["launch_critical_nested_blockers"] == [
        "release channel supportability is not gold_supported",
        "release channel rollout is public_release_review_required, not public_stable",
    ]
    assert "Coverage gaps: desktop_client" not in summary["reason"]


def test_failed_independent_audits_are_not_recoverable_as_wrapper_only(
    monkeypatch,
) -> None:
    module = load_module()
    monkeypatch.setattr(module, "current_release_truth_launch_blockers", lambda: [])

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
    payload["coverage_details"] = {
        "fleet_and_operator_loop": {
            "status": "ready",
            "evidence": {
                "final_gold_janitor_path": "/tmp/final-gold.json",
                "final_gold_janitor_state": "fail",
                "final_gold_janitor_verdict": "NOT_GOLD",
            },
        },
        "desktop_client": {
            "status": "missing",
            "evidence": {
                "ui_executable_exit_gate_effective_ready": True,
                "ui_executable_exit_gate_effective_local_blocking_findings": [],
                "ui_executable_exit_gate_blocking_mode": "none",
                "ui_windows_exit_gate_effective_ready": True,
                "ui_windows_exit_gate_blocking_mode": "none",
                "ui_linux_exit_gate_effective_ready": True,
                "ui_workflow_execution_gate_status": "pass",
                "ui_visual_familiarity_exit_gate_status": "pass",
                "ui_flagship_release_gate_status": "pass",
                "ui_external_host_proof_blockers_unresolved_hosts": [],
                "release_channel_freshness_ok": False,
                "release_channel_status": "published",
                "release_channel_rollout_state": "public_stable",
                "release_channel_supportability_state": "gold_supported",
                "release_channel_release_proof_status": "passed",
                "release_channel_tuple_coverage_incomplete": False,
                "release_channel_has_windows_public_installer": True,
                "release_channel_has_linux_public_installer": True,
                "release_channel_missing_required_platform_head_pairs": [],
                "release_channel_missing_required_platform_head_pairs_derived": [],
                "release_channel_missing_required_platforms_derived": [],
                "release_channel_missing_required_heads_derived": [],
            },
        },
    }

    summary = module.summarize(payload)

    assert summary["pass"] is False
    assert summary["coverage_gap_keys"] == []
    assert summary["scoped_coverage_gap_keys"] == []
    assert summary["missing_count"] == 0
    assert summary["scoped_missing_count"] == 0
    assert summary["launch_critical_nested_blockers"] == [
        "final gold janitor state is 'fail'",
        "final gold janitor verdict is 'NOT_GOLD'",
    ]
    assert module.recoverable_wrapper_blockers_only(summary) is False
    assert "Coverage gaps: desktop_client" not in summary["reason"]


def test_recoverable_wrapper_blockers_require_failed_source_status_and_passed_independent_audits() -> None:
    module = load_module()
    summary = {
        "contract_name": "fleet.flagship_product_readiness",
        "status": "fail",
        "readiness_load_status": "loaded",
        "completion_audit_status": "pass",
        "flagship_readiness_audit_status": "pass",
        "pass": False,
        "missing_count": 0,
        "scoped_missing_count": 0,
        "coverage_gap_keys": [],
        "scoped_coverage_gap_keys": [],
        "launch_critical_nested_blockers": [
            "final gold janitor state is 'fail'",
            "final gold janitor verdict is 'NOT_GOLD'",
        ],
        "launch_critical_nested_blocker_count": 2,
    }

    assert module.recoverable_wrapper_blockers_only(summary) is True

    for field, unsafe_value in (
        ("status", "pass"),
        ("status", "unknown"),
        ("readiness_load_status", "invalid"),
        ("readiness_load_status", None),
        ("completion_audit_status", "fail"),
        ("completion_audit_status", None),
        ("flagship_readiness_audit_status", "fail"),
        ("flagship_readiness_audit_status", None),
        ("pass", True),
        ("pass", None),
        ("launch_critical_nested_blocker_count", 1),
        ("launch_critical_nested_blocker_count", None),
    ):
        adversarial = dict(summary)
        adversarial[field] = unsafe_value
        assert module.recoverable_wrapper_blockers_only(adversarial) is False


def test_summary_keeps_desktop_client_gap_when_release_channel_freshness_lacks_wrapper_cycle(
    monkeypatch,
) -> None:
    module = load_module()
    monkeypatch.setattr(module, "current_release_truth_launch_blockers", lambda: [])

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
    payload["coverage_details"] = {
        "fleet_and_operator_loop": {
            "status": "ready",
            "evidence": {
                "final_gold_janitor_path": "/tmp/final-gold.json",
            },
        },
        "desktop_client": {
            "status": "missing",
            "evidence": {
                "ui_executable_exit_gate_effective_ready": True,
                "ui_executable_exit_gate_effective_local_blocking_findings": [],
                "ui_executable_exit_gate_blocking_mode": "none",
                "ui_windows_exit_gate_effective_ready": True,
                "ui_windows_exit_gate_blocking_mode": "none",
                "ui_linux_exit_gate_effective_ready": True,
                "ui_workflow_execution_gate_status": "pass",
                "ui_visual_familiarity_exit_gate_status": "pass",
                "ui_flagship_release_gate_status": "pass",
                "ui_external_host_proof_blockers_unresolved_hosts": [],
                "release_channel_freshness_ok": False,
                "release_channel_status": "published",
                "release_channel_rollout_state": "public_stable",
                "release_channel_supportability_state": "gold_supported",
                "release_channel_release_proof_status": "passed",
                "release_channel_tuple_coverage_incomplete": False,
                "release_channel_has_windows_public_installer": True,
                "release_channel_has_linux_public_installer": True,
                "release_channel_missing_required_platform_head_pairs": [],
                "release_channel_missing_required_platform_head_pairs_derived": [],
                "release_channel_missing_required_platforms_derived": [],
                "release_channel_missing_required_heads_derived": [],
            },
        },
    }

    summary = module.summarize(payload)

    assert summary["coverage_gap_keys"] == ["desktop_client"]
    assert summary["scoped_coverage_gap_keys"] == ["desktop_client"]
    assert module.recoverable_wrapper_blockers_only(summary) is False


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


def test_summary_rejects_pass_shaped_release_ready_wrapper_with_unexpected_verdict(
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
                "status": "pass",
                "verdict": "READY_BUT_NOT_RELEASE_READY",
                "returncode": 0,
                "timed_out": False,
                "saw_release_ready_marker": True,
                "not_release_ready_markers": [],
                "failures": [],
                "failed_gates": [],
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
            },
        },
    }

    summary = module.summarize(payload)

    assert summary["pass"] is False
    assert summary["launch_critical_nested_blockers"] == [
        "release_ready receipt has unexpected verdict",
    ]
    assert summary["reason"] == "Launch blockers: release_ready receipt has unexpected verdict."


def test_summary_recovers_google_signed_in_only_failures_when_operator_evidence_is_green(
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
                "failed_gates": ["google_oauth_linking_proof"],
                "failures": [
                    "FAIL google_oauth_linking_proof: signed_in_link_handoff: /home returned 302, expected 200",
                    "FAIL google_oauth_linking_proof: signed_in_link_handoff: /auth/google/link did not produce a complete Google OAuth redirect contract",
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
                "quick_handoff_probe": {"pass": True},
                "signed_in_link_handoff": {"status": "fail", "pass": False},
                "operator_end_to_end_evidence": {
                    "pass": True,
                    "exists": True,
                    "path": "/tmp/operator-evidence.json",
                },
                "operator_request_artifacts": {
                    "pass": True,
                    "request_status": "not_required",
                    "operator_ask_delivery_needs_resend": False,
                },
                "failures": [
                    "signed_in_link_handoff: /home returned 302, expected 200",
                    "signed_in_link_handoff: /auth/google/link did not produce a complete Google OAuth redirect contract",
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
                "version": "run-20260706-041011",
                "channel": "public_stable",
                "supportabilityState": "gold_supported",
                "rolloutState": "public_stable",
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
            },
        },
    }

    summary = module.summarize(payload)

    assert summary["pass"] is True
    assert summary["launch_critical_nested_blockers"] == []
    assert "signed_in_link_handoff:" not in str(summary["reason"] or "")


def test_summary_recovers_google_signed_in_only_failures_when_effective_request_status_is_not_required(
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
                "failed_gates": ["google_oauth_linking_proof"],
                "failures": [
                    "FAIL google_oauth_linking_proof: signed_in_link_handoff: /home returned 302, expected 200",
                    "FAIL google_oauth_linking_proof: signed_in_link_handoff: /auth/google/link did not produce a complete Google OAuth redirect contract",
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
                "quick_handoff_probe": {"pass": True},
                "signed_in_link_handoff": {"status": "fail", "pass": False},
                "operator_end_to_end_evidence": {
                    "pass": True,
                    "exists": True,
                    "path": "/tmp/operator-evidence.json",
                },
                "operator_request_artifacts": {
                    "pass": True,
                    "request_status": "operator_action_required",
                    "request_effective_status": "not_required",
                    "operator_ask_delivery_needs_resend": False,
                },
                "failures": [
                    "signed_in_link_handoff: /home returned 302, expected 200",
                    "signed_in_link_handoff: /auth/google/link did not produce a complete Google OAuth redirect contract",
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
                "version": "run-20260706-041011",
                "channel": "public_stable",
                "supportabilityState": "gold_supported",
                "rolloutState": "public_stable",
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
            },
        },
    }

    summary = module.summarize(payload)

    assert summary["pass"] is True
    assert summary["launch_critical_nested_blockers"] == []
    assert "signed_in_link_handoff:" not in str(summary["reason"] or "")


def test_summary_recovers_user_paused_google_sign_in_automation_when_request_is_not_required(
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
                "failed_gates": ["google_oauth_linking_proof"],
                "failures": [
                    "FAIL google_oauth_linking_proof: auth_signin_automation_paused: paused by user request on 2026-07-08",
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
                "operator_request_artifacts": {
                    "pass": True,
                    "request_status": "not_required",
                    "request_effective_status": "not_required",
                    "operator_action_still_required": False,
                    "operator_ask_delivery_needs_resend": False,
                },
                "failures": [
                    "auth_signin_automation_paused: paused by user request on 2026-07-08",
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
                "version": "run-20260706-041011",
                "channel": "public_stable",
                "supportabilityState": "gold_supported",
                "rolloutState": "public_stable",
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
            },
        },
    }

    summary = module.summarize(payload)

    assert summary["pass"] is True
    assert summary["launch_critical_nested_blockers"] == []
    assert "auth_signin_automation_paused:" not in str(summary["reason"] or "")


def test_summary_rejects_pass_shaped_google_oauth_receipt_with_failures(
    tmp_path,
    monkeypatch,
) -> None:
    module = load_module()
    published = tmp_path / "published"
    published.mkdir(parents=True, exist_ok=True)
    registry_published = tmp_path / "registry-published"
    registry_published.mkdir(parents=True, exist_ok=True)

    (published / "GOOGLE_OAUTH_LINKING_PROOF.generated.json").write_text(
        json.dumps(
            {
                "contract_name": "chummer.run.google_oauth_linking_proof",
                "status": "pass",
                "operator_end_to_end_evidence": {
                    "pass": False,
                    "exists": False,
                    "path": "/tmp/operator-evidence.json",
                    "failures": [
                        "missing operator evidence receipt: /tmp/operator-evidence.json",
                    ],
                },
                "operator_request_artifacts": {
                    "request_status": "not_required",
                    "operator_ask_delivery_needs_resend": False,
                    "required_operator_evidence_path": "/tmp/operator-evidence.json",
                },
                "failures": [
                    "operator_end_to_end_evidence: missing operator evidence receipt: /tmp/operator-evidence.json",
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
            }
        ),
        encoding="utf-8",
    )
    (registry_published / "RELEASE_CHANNEL.generated.json").write_text(
        json.dumps(
            {
                "contract_name": "chummer.release_channel",
                "status": "published",
                "version": "run-20260706-041011",
                "channel": "public_stable",
                "supportabilityState": "gold_supported",
                "rolloutState": "public_stable",
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
            },
        },
    }

    summary = module.summarize(payload)

    assert summary["pass"] is False
    assert summary["launch_critical_nested_blockers"] == [
        "google oauth operator evidence is still missing: /tmp/operator-evidence.json",
    ]
    assert summary["reason"] == (
        "Launch blockers: google oauth operator evidence is still missing: /tmp/operator-evidence.json."
    )


def test_summary_rejects_pass_shaped_windows_visual_audit_receipt_with_failures(
    tmp_path,
    monkeypatch,
) -> None:
    module = load_module()
    published = tmp_path / "published"
    published.mkdir(parents=True, exist_ok=True)
    registry_published = tmp_path / "registry-published"
    registry_published.mkdir(parents=True, exist_ok=True)

    (published / "GOOGLE_OAUTH_LINKING_PROOF.generated.json").write_text(
        json.dumps(
            {
                "contract_name": "chummer.run.google_oauth_linking_proof",
                "status": "pass",
            }
        ),
        encoding="utf-8",
    )
    (published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json").write_text(
        json.dumps(
            {
                "contract_name": "chummer.windows_installer_visual_audit",
                "status": "pass",
                "failures": [
                    "Windows installer visual audit source digest does not match promoted installer",
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
                "version": "run-20260706-041011",
                "channel": "public_stable",
                "supportabilityState": "gold_supported",
                "rolloutState": "public_stable",
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
            },
        },
    }

    summary = module.summarize(payload)

    assert summary["pass"] is False
    assert summary["launch_critical_nested_blockers"] == [
        "Windows installer visual audit source digest does not match promoted installer",
    ]
    assert summary["reason"] == (
        "Launch blockers: Windows installer visual audit source digest does not match promoted installer."
    )


def test_summary_rejects_pass_shaped_windows_visual_audit_receipt_with_nested_digest_mismatch_only(
    tmp_path,
    monkeypatch,
) -> None:
    module = load_module()
    published = tmp_path / "published"
    published.mkdir(parents=True, exist_ok=True)
    registry_published = tmp_path / "registry-published"
    registry_published.mkdir(parents=True, exist_ok=True)

    (published / "GOOGLE_OAUTH_LINKING_PROOF.generated.json").write_text(
        json.dumps(
            {
                "contract_name": "chummer.run.google_oauth_linking_proof",
                "status": "pass",
            }
        ),
        encoding="utf-8",
    )
    (published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json").write_text(
        json.dumps(
            {
                "contract_name": "chummer.windows_installer_visual_audit",
                "status": "pass",
                "source_digest_matches_promoted": False,
                "visualAuditSource": {
                    "status": "pass",
                    "artifactDigestMatchesPromoted": False,
                },
                "summary": {
                    "reason": "Current promoted installer visual audit is complete."
                },
            }
        ),
        encoding="utf-8",
    )
    (registry_published / "RELEASE_CHANNEL.generated.json").write_text(
        json.dumps(
            {
                "contract_name": "chummer.release_channel",
                "status": "published",
                "version": "run-20260706-041011",
                "channel": "public_stable",
                "supportabilityState": "gold_supported",
                "rolloutState": "public_stable",
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
            },
        },
    }

    summary = module.summarize(payload)

    assert summary["pass"] is False
    assert summary["launch_critical_nested_blockers"] == [
        "Windows installer visual audit source digest does not match promoted installer",
    ]
    assert summary["reason"] == (
        "Launch blockers: Windows installer visual audit source digest does not match promoted installer."
    )


def test_summary_merges_current_windows_audit_with_release_ready_bundle_gap_details(
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
                "failed_gates": ["windows_installer_visual_audit"],
                "failures": [
                    "FAIL windows_installer_visual_audit: Windows installer visual audit source digest does not match promoted installer",
                    "FAIL windows_installer_visual_audit: windows installer gold proof artifact is still missing: /tmp/windows-installer-gold-proof.zip",
                ],
            }
        ),
        encoding="utf-8",
    )
    (published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json").write_text(
        json.dumps(
            {
                "contract_name": "chummer.windows_installer_visual_audit",
                "status": "fail",
                "failures": [
                    "Windows installer visual audit source digest does not match promoted installer",
                ],
                "operator_request_artifacts": {
                    "preferred_drop_path": "/tmp/windows-installer-gold-proof.zip",
                },
            }
        ),
        encoding="utf-8",
    )
    (registry_published / "RELEASE_CHANNEL.generated.json").write_text(
        json.dumps(
            {
                "contract_name": "chummer.release_channel",
                "status": "published",
                "version": "run-20260706-041011",
                "channel": "public_stable",
                "supportabilityState": "gold_supported",
                "rolloutState": "public_stable",
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
        "Windows installer visual audit source digest does not match promoted installer",
        "windows installer gold proof artifact is still missing: /tmp/windows-installer-gold-proof.zip",
    ]
    assert "windows installer gold proof artifact is still missing: /tmp/windows-installer-gold-proof.zip" in summary["reason"]


def test_summary_merges_current_windows_audit_with_pass_shaped_release_ready_bundle_gap_details(
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
                "status": "pass",
                "verdict": "READY_BUT_NOT_RELEASE_READY",
                "returncode": 0,
                "timed_out": False,
                "saw_release_ready_marker": True,
                "not_release_ready_markers": [],
                "failed_gates": ["windows_installer_visual_audit"],
                "failures": [
                    "FAIL windows_installer_visual_audit: Windows installer visual audit source digest does not match promoted installer",
                    "FAIL windows_installer_visual_audit: windows installer gold proof artifact is still missing: /tmp/windows-installer-gold-proof.zip",
                ],
            }
        ),
        encoding="utf-8",
    )
    (published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json").write_text(
        json.dumps(
            {
                "contract_name": "chummer.windows_installer_visual_audit",
                "status": "fail",
                "failures": [
                    "Windows installer visual audit source digest does not match promoted installer",
                ],
                "operator_request_artifacts": {
                    "preferred_drop_path": "/tmp/windows-installer-gold-proof.zip",
                },
            }
        ),
        encoding="utf-8",
    )
    (registry_published / "RELEASE_CHANNEL.generated.json").write_text(
        json.dumps(
            {
                "contract_name": "chummer.release_channel",
                "status": "published",
                "version": "run-20260706-041011",
                "channel": "public_stable",
                "supportabilityState": "gold_supported",
                "rolloutState": "public_stable",
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
        "Windows installer visual audit source digest does not match promoted installer",
        "windows installer gold proof artifact is still missing: /tmp/windows-installer-gold-proof.zip",
    ]
    assert "windows installer gold proof artifact is still missing: /tmp/windows-installer-gold-proof.zip" in summary["reason"]


def test_summary_recomputes_current_portal_registry_identity_instead_of_echoing_stale_release_ready(
    tmp_path,
    monkeypatch,
) -> None:
    module = load_module()
    published = tmp_path / "published"
    published.mkdir()
    registry = tmp_path / "registry-release-channel.json"
    portal = tmp_path / "portal-release-channel.json"
    root_blockers = tmp_path / "RELEASE_BLOCKERS.generated.json"
    write_fresh_root_release_blockers(root_blockers)

    authoritative = {
        "status": "published",
        "channel": "preview",
        "version": "run-current-registry",
        "supportabilityState": "preview_supported",
        "rolloutState": "promoted_preview",
    }
    registry.write_text(json.dumps(authoritative), encoding="utf-8")
    portal.write_text(json.dumps(authoritative), encoding="utf-8")
    stale_drift = (
        "workspace portal release channel artifact stale/RELEASE_CHANNEL.generated.json "
        "disagrees with authoritative registry receipt "
        "(local channel=preview, version=run-stale-portal, "
        "supportability=preview_supported, rollout=promoted_preview; "
        "authoritative channel=preview, version=run-stale-registry, "
        "supportability=preview_supported, rollout=promoted_preview)"
    )
    (published / "RELEASE_READY.generated.json").write_text(
        json.dumps(
            {
                "contract_name": "chummer.release_ready",
                "status": "fail",
                "failed_gates": ["release_channel"],
                "failures": [f"FAIL release_channel: {stale_drift}"],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(module, "PUBLISHED_ROOT", published)
    monkeypatch.setattr(module, "DEFAULT_RELEASE_CHANNEL", registry)
    monkeypatch.setattr(module, "DEFAULT_WORKSPACE_PORTAL_RELEASE_CHANNEL", portal)
    monkeypatch.setattr(module, "DEFAULT_RELEASE_BLOCKERS", root_blockers)
    monkeypatch.setattr(
        module,
        "DEFAULT_GOOGLE_OAUTH_LINKING_PROOF",
        published / "GOOGLE_OAUTH_LINKING_PROOF.generated.json",
    )
    monkeypatch.setattr(
        module,
        "DEFAULT_WINDOWS_INSTALLER_VISUAL_AUDIT",
        published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json",
    )

    payload = passing_payload()
    payload["coverage_details"] = {
        "fleet_and_operator_loop": {
            "evidence": {"final_gold_janitor_path": "/tmp/final-gold.json"}
        }
    }
    summary = module.summarize(
        payload,
        readiness_path=tmp_path / "FLAGSHIP_PRODUCT_READINESS.generated.json",
    )

    assert stale_drift not in summary["launch_critical_nested_blockers"]
    assert not any(
        blocker.startswith(module.WORKSPACE_PORTAL_RELEASE_CHANNEL_DRIFT_PREFIX)
        for blocker in summary["launch_critical_nested_blockers"]
    )


def test_summary_reports_current_portal_registry_identity_mismatch(
    tmp_path,
    monkeypatch,
) -> None:
    module = load_module()
    published = tmp_path / "published"
    published.mkdir()
    registry = tmp_path / "registry-release-channel.json"
    portal = tmp_path / "portal-release-channel.json"
    root_blockers = tmp_path / "RELEASE_BLOCKERS.generated.json"
    write_fresh_root_release_blockers(root_blockers)

    base = {
        "status": "published",
        "channel": "preview",
        "supportabilityState": "preview_supported",
        "rolloutState": "promoted_preview",
    }
    registry.write_text(
        json.dumps({**base, "version": "run-current-registry"}),
        encoding="utf-8",
    )
    portal.write_text(
        json.dumps({**base, "version": "run-current-portal"}),
        encoding="utf-8",
    )
    (published / "RELEASE_READY.generated.json").write_text(
        json.dumps(
            {
                "contract_name": "chummer.release_ready",
                "status": "fail",
                "failed_gates": ["release_channel"],
                "failures": [
                    "FAIL release_channel: workspace portal release channel artifact "
                    "stale.json disagrees with authoritative registry receipt "
                    "(local version=run-stale-portal; authoritative version=run-stale-registry)"
                ],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(module, "PUBLISHED_ROOT", published)
    monkeypatch.setattr(module, "DEFAULT_RELEASE_CHANNEL", registry)
    monkeypatch.setattr(module, "DEFAULT_WORKSPACE_PORTAL_RELEASE_CHANNEL", portal)
    monkeypatch.setattr(module, "DEFAULT_RELEASE_BLOCKERS", root_blockers)
    monkeypatch.setattr(
        module,
        "DEFAULT_GOOGLE_OAUTH_LINKING_PROOF",
        published / "GOOGLE_OAUTH_LINKING_PROOF.generated.json",
    )
    monkeypatch.setattr(
        module,
        "DEFAULT_WINDOWS_INSTALLER_VISUAL_AUDIT",
        published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json",
    )

    payload = passing_payload()
    payload["coverage_details"] = {
        "fleet_and_operator_loop": {
            "evidence": {"final_gold_janitor_path": "/tmp/final-gold.json"}
        }
    }
    summary = module.summarize(
        payload,
        readiness_path=tmp_path / "FLAGSHIP_PRODUCT_READINESS.generated.json",
    )
    drift = [
        blocker
        for blocker in summary["launch_critical_nested_blockers"]
        if blocker.startswith(module.WORKSPACE_PORTAL_RELEASE_CHANNEL_DRIFT_PREFIX)
    ]

    assert len(drift) == 1
    assert "run-current-portal" in drift[0]
    assert "run-current-registry" in drift[0]
    assert "run-stale-portal" not in drift[0]
    assert "run-stale-registry" not in drift[0]


def test_root_release_truth_fails_closed_on_missing_malformed_stale_and_future_receipts(
    tmp_path,
) -> None:
    module = load_module()
    path = tmp_path / "RELEASE_BLOCKERS.generated.json"
    observed_at = datetime(2026, 7, 15, 12, 0, tzinfo=UTC)
    fresh_payload = {
        "generated_at": "2026-07-15T11:00:00Z",
        "root_blockers": [],
    }

    assert module.root_release_truth_failures(
        fresh_payload,
        "loaded",
        path,
        observed_at=observed_at,
    ) == []
    scenarios = [
        ({}, "missing", "receipt is missing"),
        ({}, "invalid", "receipt is malformed"),
        ({"generated_at": "not-a-time", "root_blockers": []}, "loaded", "missing or malformed"),
        (
            {"generated_at": "2026-07-14T11:59:59Z", "root_blockers": []},
            "loaded",
            "receipt is stale",
        ),
        (
            {"generated_at": "2026-07-15T12:05:01Z", "root_blockers": []},
            "loaded",
            "is in the future",
        ),
        (
            {"generated_at": "2026-07-15T11:00:00Z", "root_blockers": {}},
            "loaded",
            "must contain root_blockers or blockers as a list",
        ),
    ]
    for payload, load_status, expected in scenarios:
        failures = module.root_release_truth_failures(
            payload,
            load_status,
            path,
            observed_at=observed_at,
        )
        assert any(expected in failure for failure in failures)


def test_concrete_summary_adds_stale_root_release_truth_as_launch_blocker(
    tmp_path,
    monkeypatch,
) -> None:
    module = load_module()
    blockers = tmp_path / "RELEASE_BLOCKERS.generated.json"
    blockers.write_text(
        json.dumps(
            {
                "generated_at": (
                    datetime.now(UTC) - timedelta(hours=25)
                ).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                "root_blockers": [],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "DEFAULT_RELEASE_BLOCKERS", blockers)

    summary = module.summarize(
        passing_payload(),
        readiness_path=tmp_path / "FLAGSHIP_PRODUCT_READINESS.generated.json",
    )

    assert summary["pass"] is False
    assert summary["root_release_truth_failures"] == [
        summary["launch_critical_nested_blockers"][0]
    ]
    assert "root RELEASE_BLOCKERS receipt is stale" in summary[
        "launch_critical_nested_blockers"
    ][0]


def test_summary_surfaces_root_blocker_context_and_stable_promotion_commands(
    tmp_path,
    monkeypatch,
) -> None:
    module = load_module()
    published = tmp_path / "published"
    published.mkdir(parents=True, exist_ok=True)
    registry_published = tmp_path / "registry-published"
    registry_published.mkdir(parents=True, exist_ok=True)
    blockers = tmp_path / "RELEASE_BLOCKERS.generated.json"

    blockers.write_text(
        json.dumps(
            {
                "generated_at": "2026-07-06T05:18:22Z",
                "blockers": [
                    {
                        "blocker_id": "release_posture:non_flagship_channel",
                        "stable_promotion_command": "RELEASE_CHANNEL=public_stable bash publish-download-bundle.sh",
                        "post_promotion_verify_command": (
                            "python3 scripts/materialize_release_ready_receipt.py --force-global-verifier && "
                            "python3 scripts/materialize_operator_release_dashboard.py && "
                            "python3 scripts/final_gold_janitor.py && "
                            "python3 ../scripts/release/_release_gate_common.py && "
                            "python3 ../scripts/materialize_codex_flagship_handoff.py --timestamp "
                            "\"$(date --iso-8601=seconds)\""
                        ),
                    },
                    {
                        "blocker_id": "release_truth:windows_installer_visual_audit",
                    },
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
            }
        ),
        encoding="utf-8",
    )
    (registry_published / "RELEASE_CHANNEL.generated.json").write_text(
        json.dumps(
            {
                "contract_name": "chummer.release_channel",
                "status": "published",
                "version": "run-20260706-041011",
                "channel": "preview",
                "supportabilityState": "preview_supported",
                "rolloutState": "promoted_preview",
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(module, "DEFAULT_RELEASE_BLOCKERS", blockers)
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

    assert summary["root_blocker_ids"] == [
        "release_posture:non_flagship_channel",
        "release_truth:windows_installer_visual_audit",
    ]
    assert summary["root_blockers_generated_at"] == "2026-07-06T05:18:22Z"
    assert summary["stable_promotion_command"] == "RELEASE_CHANNEL=public_stable bash publish-download-bundle.sh"
    assert (
        summary["post_promotion_verify_command"]
        == "python3 scripts/materialize_release_ready_receipt.py --force-global-verifier && "
        "python3 scripts/materialize_operator_release_dashboard.py && "
        "python3 scripts/final_gold_janitor.py && "
        "python3 ../scripts/release/_release_gate_common.py && "
        "python3 ../scripts/materialize_codex_flagship_handoff.py --timestamp "
        "\"$(date --iso-8601=seconds)\""
    )
    assert summary["root_release_truth_source"] == str(blockers)


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
    assert written["verdict"] == module.NOT_READY_VERDICT
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
    assert written["verdict"] == module.NOT_READY_VERDICT
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
    assert written["verdict"] == module.NOT_READY_VERDICT
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
    assert written["verdict"] == module.NOT_READY_VERDICT
    assert written["pass"] is False
    assert written["readiness_receipt_fail_closed"] is True
    assert "final gold janitor state is 'fail'" in written["launch_critical_nested_blockers"]
    assert "final gold janitor verdict is 'NOT_GOLD'" in written["reason"]
    assert rewritten["status"] == "fail"
    assert rewritten["gate_status_override"]["raw_status"] == "pass"
    assert "final gold janitor state is 'fail'" in rewritten["gate_status_override"]["launch_critical_nested_blockers"]
    assert "Launch-critical nested blockers or coverage gaps remain" in written["summary"]["reason"]
    assert "final gold janitor verdict is 'NOT_GOLD'" in written["summary"]["reason"]


def test_main_allows_recoverable_wrapper_blockers_when_requested(tmp_path, monkeypatch) -> None:
    module = load_module()
    root_blockers = tmp_path / "RELEASE_BLOCKERS.generated.json"
    write_fresh_root_release_blockers(root_blockers)
    monkeypatch.setattr(module, "DEFAULT_RELEASE_BLOCKERS", root_blockers)
    readiness = tmp_path / "FLAGSHIP_PRODUCT_READINESS.generated.json"
    summary_path = tmp_path / "summary.json"
    privacy_gate_path = tmp_path / "privacy-launch-gate.json"
    hosted_build_decisions_path = tmp_path / "hosted-build-decisions.json"
    write_clear_privacy_launch_gate(privacy_gate_path)
    write_clear_hosted_build_operator_decisions(hosted_build_decisions_path)
    monkeypatch.setattr(
        module,
        "evaluate_hosted_build_operator_decisions",
        lambda *args, **kwargs: {
            "decision_gate_passed": True,
            "blockers": [],
            "pass": True,
        },
    )
    payload = passing_payload()
    payload["status"] = "fail"
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
            "--allow-recoverable-wrapper-blockers",
            "--readiness",
            str(readiness),
            "--privacy-launch-gate",
            str(privacy_gate_path),
            "--hosted-build-v002-decisions",
            str(hosted_build_decisions_path),
            "--summary-output",
            str(summary_path),
        ],
    )

    assert module.main() == 0
    written = json.loads(summary_path.read_text(encoding="utf-8"))
    assert written["status"] == "fail"
    assert written["verdict"] == module.NOT_READY_VERDICT
    assert written["pass"] is False
    assert written["recoverable_wrapper_blockers_only"] is True


def test_main_never_waives_failed_independent_audits_even_when_wrapper_waiver_is_requested(
    tmp_path,
    monkeypatch,
) -> None:
    module = load_module()
    root_blockers = tmp_path / "RELEASE_BLOCKERS.generated.json"
    write_fresh_root_release_blockers(root_blockers)
    monkeypatch.setattr(module, "DEFAULT_RELEASE_BLOCKERS", root_blockers)
    readiness = tmp_path / "FLAGSHIP_PRODUCT_READINESS.generated.json"
    summary_path = tmp_path / "summary.json"
    privacy_gate_path = tmp_path / "privacy-launch-gate.json"
    hosted_build_decisions_path = tmp_path / "hosted-build-decisions.json"
    write_clear_privacy_launch_gate(privacy_gate_path)
    write_clear_hosted_build_operator_decisions(hosted_build_decisions_path)
    monkeypatch.setattr(
        module,
        "evaluate_hosted_build_operator_decisions",
        lambda *args, **kwargs: {
            "decision_gate_passed": True,
            "blockers": [],
            "pass": True,
        },
    )
    payload = passing_payload()
    payload["status"] = "fail"
    payload["completion_audit"] = {"status": "fail"}
    payload["flagship_readiness_audit"] = {
        "status": "fail",
        "coverage_gap_keys": [],
        "scoped_coverage_gap_keys": [],
    }
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
            "--allow-recoverable-wrapper-blockers",
            "--readiness",
            str(readiness),
            "--privacy-launch-gate",
            str(privacy_gate_path),
            "--hosted-build-v002-decisions",
            str(hosted_build_decisions_path),
            "--summary-output",
            str(summary_path),
        ],
    )

    assert module.main() == 1
    written = json.loads(summary_path.read_text(encoding="utf-8"))
    assert written["recoverable_wrapper_blockers_only"] is False
    assert written["summary"]["completion_audit_status"] == "fail"
    assert written["summary"]["flagship_readiness_audit_status"] == "fail"


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
    root_blockers = tmp_path / "RELEASE_BLOCKERS.generated.json"
    write_fresh_root_release_blockers(root_blockers)
    monkeypatch.setattr(module, "DEFAULT_RELEASE_BLOCKERS", root_blockers)
    readiness = tmp_path / "FLAGSHIP_PRODUCT_READINESS.generated.json"
    default_summary = tmp_path / "FLAGSHIP_PRODUCT_READINESS_GATE.generated.json"
    privacy_gate_path = tmp_path / "privacy-launch-gate.json"
    hosted_build_decisions_path = tmp_path / "hosted-build-decisions.json"
    write_clear_privacy_launch_gate(privacy_gate_path)
    write_clear_hosted_build_operator_decisions(hosted_build_decisions_path)
    monkeypatch.setattr(
        module,
        "evaluate_hosted_build_operator_decisions",
        lambda *args, **kwargs: {
            "decision_gate_passed": True,
            "blockers": [],
            "pass": True,
        },
    )
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
            "--privacy-launch-gate",
            str(privacy_gate_path),
            "--hosted-build-v002-decisions",
            str(hosted_build_decisions_path),
        ],
    )

    assert module.main() == 0
    written = json.loads(default_summary.read_text(encoding="utf-8"))
    assert written["status"] == "pass"
    assert written["verdict"] == module.READY_VERDICT
    assert written["pass"] is True
    assert written["readiness_receipt_fail_closed"] is False
    assert written["launch_critical_nested_blockers"] == []
    assert written["launch_critical_nested_blocker_count"] == 0
    assert written["coverage_gap_keys"] == []
    assert written["scoped_coverage_gap_keys"] == []
    assert written["generated_at_utc"]
