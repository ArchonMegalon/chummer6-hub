from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "verify_flagship_product_readiness_gate.py"
REPO_ROOT = SCRIPT_PATH.parents[1]


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
        "generatedAtUtc": datetime.now(UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
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


def current_campaign_os_csc(dotnet_path: Path) -> Path:
    completed = subprocess.run(
        [str(dotnet_path), "--version"],
        cwd=REPO_ROOT,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=True,
    )
    version = completed.stdout.strip()
    csc_path = (
        dotnet_path.resolve(strict=True).parent
        / "sdk"
        / version
        / "Roslyn"
        / "bincore"
        / "csc.dll"
    )
    assert csc_path.is_file()
    return csc_path


def campaign_os_v3_payload(contract, *, observed_at: datetime) -> dict[str, object]:  # noqa: ANN001
    started = observed_at.replace(microsecond=0)
    completed = started + timedelta(seconds=1)
    run_id = "3f1f5b8e-6f8a-4f5e-8f16-65d4a917c9a2"
    checkpoints = [
        {
            "checkpoint_id": contract.CHECKPOINT_IDS[journey_id],
            "run_id": run_id,
            "status": "passed",
        }
        for journey_id in contract.JOURNEY_IDS
    ]
    runtime_entries = [{"path": path} for path in contract.MANIFEST_PATHS]
    return {
        "contract_name": contract.CONTRACT_NAME,
        "contract_version": contract.CONTRACT_VERSION,
        "status": "passed",
        "proof_kind": contract.PROOF_KIND,
        "run_id": run_id,
        "started_at": contract.format_utc(started),
        "completed_at": contract.format_utc(completed),
        "generated_at": contract.format_utc(completed),
        "expires_at": contract.format_utc(completed + contract.RECEIPT_LIFETIME),
        "invocation": {
            "id": contract.INVOCATION_ID,
            "owner": contract.INVOCATION_OWNER,
            "dependency_mode": contract.DEPENDENCY_MODE,
            "prepare_exit_code": 0,
            "runner_exit_code": 0,
        },
        "inputs": {
            "dotnet_host": {"path": str(contract.DOTNET_HOST_PATH)},
            "csc": {"path": str(current_campaign_os_csc(contract.DOTNET_HOST_PATH))},
        },
        "execution": {
            "phase": "verified",
            "failure_reason": None,
            "runtime_checkpoints": checkpoints,
            "runtime_manifest_before": {"entries": runtime_entries},
            "closure_stable": True,
        },
        "journeys": [{"journey_id": journey_id} for journey_id in contract.JOURNEY_IDS],
        "summary": {"journey_count": len(contract.JOURNEY_IDS)},
    }


def install_campaign_os_v3_validator_double(module, monkeypatch):  # noqa: ANN001
    """Exercise consumer binding without minting or copying a production proof."""

    contract = module.load_campaign_os_local_proof_contract()

    def validate_passed_receipt(_root, path, **_kwargs):  # noqa: ANN001
        try:
            raw = contract._read_regular_bytes(
                path,
                max_bytes=contract.MAX_RECEIPT_BYTES,
                reason_prefix="receipt",
            )
        except contract.ProofContractError as exc:
            reason = (
                "receipt_output_symlink"
                if exc.reason_code == "receipt_symlink"
                else exc.reason_code
            )
            return contract.ValidationResult(False, reason)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return contract.ValidationResult(False, "receipt_invalid_json")
        if not isinstance(payload, dict):
            return contract.ValidationResult(False, "receipt_invalid_shape")
        if payload.get("contract_version") != contract.CONTRACT_VERSION:
            return contract.ValidationResult(False, "contract_version_mismatch")
        try:
            expires_at = contract.parse_utc(payload.get("expires_at"))
        except contract.ProofContractError as exc:
            return contract.ValidationResult(False, exc.reason_code)
        if contract.utc_now() > expires_at:
            return contract.ValidationResult(False, "receipt_expired")
        return contract.ValidationResult(True, "valid", payload)

    monkeypatch.setattr(contract, "validate_passed_receipt", validate_passed_receipt)
    monkeypatch.setattr(module, "load_campaign_os_local_proof_contract", lambda: contract)
    return contract


def write_valid_campaign_os_local_proof(
    module,
    tmp_path: Path,
    monkeypatch,
    *,
    observed_at: datetime | None = None,
) -> tuple[dict[str, object], Path]:
    contract = install_campaign_os_v3_validator_double(module, monkeypatch)
    receipt_path = tmp_path / "campaign-os-fixture" / contract.DEFAULT_RECEIPT_PATH
    receipt_path.parent.mkdir(parents=True)
    started = (observed_at or datetime.now(UTC)).replace(microsecond=0)
    proof = campaign_os_v3_payload(contract, observed_at=started)
    receipt_path.write_text(
        json.dumps(proof, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        module,
        "CAMPAIGN_OS_LOCAL_PROOF_CONTRACT_MODULE",
        REPO_ROOT / contract.CONTRACT_MODULE_PATH,
    )
    monkeypatch.setattr(module, "DEFAULT_CAMPAIGN_OS_LOCAL_PROOF", receipt_path)
    return proof, receipt_path


def install_valid_campaign_os_local_proof_default(
    module,
    tmp_path: Path,
    monkeypatch,
) -> Path:
    _proof, proof_path = write_valid_campaign_os_local_proof(
        module,
        tmp_path,
        monkeypatch,
    )
    return proof_path


def summarize_with_valid_campaign(
    module,  # noqa: ANN001
    payload: dict[str, object],
    **kwargs,
) -> dict[str, object]:
    """Keep non-Campaign unit cases focused while satisfying the required proof seam."""

    if "campaign_os_local_proof_path" in kwargs:
        return module.summarize(payload, **kwargs)
    original = module.evaluate_campaign_os_local_proof
    module.evaluate_campaign_os_local_proof = lambda _path: {
        "path": "/test/HUB_CAMPAIGN_OS_LOCAL_PROOF.generated.json",
        "load_status": "loaded",
        "contract_name": "chummer6-hub.campaign_os_local_proof",
        "contract_version": 3,
        "status": "passed",
        "proof_kind": "materializer_owned_executed_smoke_receipt",
        "run_id": "3f1f5b8e-6f8a-4f5e-8f16-65d4a917c9a2",
        "dependency_mode": "restore_free_with_locally_closed_package_inputs",
        "generated_at": "2026-07-17T12:00:00Z",
        "expires_at": "2026-07-18T12:00:00Z",
        "journey_count": 6,
        "receipt_identity": {
            "path": "/test/HUB_CAMPAIGN_OS_LOCAL_PROOF.generated.json",
            "sha256": "a" * 64,
            "size_bytes": 1,
        },
        "validator_identity": {
            "path": "/test/campaign_os_local_proof_v3.py",
            "sha256": "b" * 64,
            "size_bytes": 1,
        },
        "reason_code": "valid",
        "blockers": [],
        "pass": True,
    }
    try:
        return module.summarize(
            payload,
            campaign_os_local_proof_path=Path(
                "/test/HUB_CAMPAIGN_OS_LOCAL_PROOF.generated.json"
            ),
            **kwargs,
        )
    finally:
        module.evaluate_campaign_os_local_proof = original


def test_summary_without_campaign_proof_fails_closed() -> None:
    module = load_module()

    summary = module.summarize(passing_payload())

    expected_blocker = (
        f"{module.CAMPAIGN_OS_LOCAL_PROOF_BLOCKER_PREFIX} (not_evaluated)."
    )
    assert summary["pass"] is False
    assert summary["contract_name"] == "fleet.flagship_product_readiness"
    assert summary["campaign_os_local_proof"]["load_status"] == "not_evaluated"
    assert summary["campaign_os_local_proof"]["pass"] is False
    assert summary["campaign_os_local_proof"]["dependency_mode"] is None
    assert summary["campaign_os_local_proof"]["receipt_identity"] is None
    assert summary["campaign_os_local_proof"]["validator_identity"] is None
    assert summary["campaign_os_local_proof"]["blockers"] == [expected_blocker]
    assert summary["launch_critical_nested_blockers"] == [expected_blocker]


def test_campaign_os_v3_executed_proof_is_structured_launch_evidence(
    tmp_path,
    monkeypatch,
) -> None:
    module = load_module()
    proof, proof_path = write_valid_campaign_os_local_proof(
        module,
        tmp_path,
        monkeypatch,
    )

    summary = summarize_with_valid_campaign(module,
        passing_payload(),
        campaign_os_local_proof_path=proof_path,
    )

    evidence = summary["campaign_os_local_proof"]
    assert summary["pass"] is True
    assert evidence["pass"] is True
    assert evidence["reason_code"] == "valid"
    assert evidence["contract_name"] == "chummer6-hub.campaign_os_local_proof"
    assert evidence["contract_version"] == 3
    assert evidence["proof_kind"] == "materializer_owned_executed_smoke_receipt"
    assert evidence["run_id"] == proof["run_id"]
    assert evidence["dependency_mode"] == (
        "restore_free_with_locally_closed_package_inputs"
    )
    assert evidence["journey_count"] == 6
    assert proof["invocation"]["owner"] == "campaign_os_local_proof_materializer"
    assert proof["invocation"]["dependency_mode"] == evidence["dependency_mode"]
    assert proof["execution"]["phase"] == "verified"
    assert proof["execution"]["closure_stable"] is True
    contract = module.load_campaign_os_local_proof_contract()
    assert contract.CONTRACT_VERSION == 3
    assert contract.CONTRACT_MODULE_PATH == "scripts/campaign_os_local_proof_v3.py"
    assert [
        checkpoint["checkpoint_id"]
        for checkpoint in proof["execution"]["runtime_checkpoints"]
    ] == [contract.CHECKPOINT_IDS[journey_id] for journey_id in contract.JOURNEY_IDS]
    assert proof["inputs"]["dotnet_host"]["path"] == "/usr/bin/dotnet"
    assert proof["inputs"]["csc"]["path"] == str(
        current_campaign_os_csc(Path("/usr/bin/dotnet"))
    )
    assert len(contract.RUNTIME_CLOSURE_PATHS) == 16
    assert "Chummer.World.Contracts.dll" in contract.RUNTIME_CLOSURE_PATHS
    assert tuple(
        entry["path"]
        for entry in proof["execution"]["runtime_manifest_before"]["entries"]
    ) == contract.MANIFEST_PATHS
    assert evidence["receipt_identity"] == {
        "path": str(proof_path.resolve()),
        "sha256": hashlib.sha256(proof_path.read_bytes()).hexdigest(),
        "size_bytes": proof_path.stat().st_size,
    }
    validator_path = module.CAMPAIGN_OS_LOCAL_PROOF_CONTRACT_MODULE.resolve()
    assert evidence["validator_identity"] == {
        "path": str(validator_path),
        "sha256": hashlib.sha256(validator_path.read_bytes()).hexdigest(),
        "size_bytes": validator_path.stat().st_size,
    }
    assert evidence["blockers"] == []


def test_campaign_os_receipt_identity_tracks_exact_validated_bytes(
    tmp_path,
    monkeypatch,
) -> None:
    module = load_module()
    _proof, proof_path = write_valid_campaign_os_local_proof(
        module,
        tmp_path,
        monkeypatch,
    )

    first = module.evaluate_campaign_os_local_proof(proof_path)
    proof_path.write_bytes(proof_path.read_bytes() + b" ")
    second = module.evaluate_campaign_os_local_proof(proof_path)

    assert first["pass"] is True
    assert second["pass"] is True
    assert first["receipt_identity"] != second["receipt_identity"]
    assert first["receipt_identity"]["sha256"] != second["receipt_identity"]["sha256"]
    assert first["receipt_identity"]["size_bytes"] + 1 == second[
        "receipt_identity"
    ]["size_bytes"]
    assert first["validator_identity"] == second["validator_identity"]


def test_campaign_os_missing_legacy_malformed_and_stale_proofs_fail_closed(
    tmp_path,
    monkeypatch,
) -> None:
    module = load_module()
    stale_time = datetime.now(UTC).replace(microsecond=0) - timedelta(hours=25)
    _proof, stale = write_valid_campaign_os_local_proof(
        module,
        tmp_path,
        monkeypatch,
        observed_at=stale_time,
    )
    stale_bytes = stale.read_bytes()
    legacy_bytes = (
        json.dumps(
            {
                "contract_name": "chummer6-hub.campaign_os_local_proof",
                "contract_version": 1,
                "status": "passed",
            }
        )
        + "\n"
    ).encode("utf-8")

    for receipt_bytes, expected_reason in (
        (None, "receipt_missing"),
        (legacy_bytes, "contract_version_mismatch"),
        (b"{not json}\n", "receipt_invalid_json"),
        (stale_bytes, "receipt_expired"),
    ):
        stale.unlink(missing_ok=True)
        if receipt_bytes is not None:
            stale.write_bytes(receipt_bytes)
        summary = summarize_with_valid_campaign(module,
            passing_payload(),
            campaign_os_local_proof_path=stale,
        )
        evidence = summary["campaign_os_local_proof"]
        expected_blocker = (
            f"{module.CAMPAIGN_OS_LOCAL_PROOF_BLOCKER_PREFIX} ({expected_reason})."
        )
        assert summary["pass"] is False
        assert evidence["pass"] is False
        assert evidence["reason_code"] == expected_reason
        assert evidence["blockers"] == [expected_blocker]
        assert summary["launch_critical_nested_blockers"] == [expected_blocker]
        assert evidence["validator_identity"] is not None
        if receipt_bytes is None:
            assert evidence["receipt_identity"] is None
        else:
            assert evidence["receipt_identity"] == {
                "path": str(stale.resolve()),
                "sha256": hashlib.sha256(stale.read_bytes()).hexdigest(),
                "size_bytes": stale.stat().st_size,
            }


def test_campaign_os_symlink_and_oversized_receipts_have_no_byte_authority(
    tmp_path,
    monkeypatch,
) -> None:
    module = load_module()
    _proof, receipt_path = write_valid_campaign_os_local_proof(
        module,
        tmp_path,
        monkeypatch,
    )
    symlink_target = tmp_path / "campaign-os-symlink-target.json"
    symlink_target.write_bytes(receipt_path.read_bytes())
    receipt_path.unlink()
    receipt_path.symlink_to(symlink_target)
    contract = module.load_campaign_os_local_proof_contract()
    symlink_evidence = module.evaluate_campaign_os_local_proof(receipt_path)
    assert symlink_evidence["pass"] is False
    assert symlink_evidence["load_status"] == "invalid"
    assert symlink_evidence["reason_code"] == "receipt_output_symlink"
    assert symlink_evidence["receipt_identity"] is None
    assert symlink_evidence["validator_identity"] is not None

    receipt_path.unlink()
    receipt_path.write_bytes(b"x" * (contract.MAX_RECEIPT_BYTES + 1))
    oversized_evidence = module.evaluate_campaign_os_local_proof(receipt_path)
    assert oversized_evidence["pass"] is False
    assert oversized_evidence["load_status"] == "invalid"
    assert oversized_evidence["reason_code"] == "receipt_too_large"
    assert oversized_evidence["receipt_identity"] is None
    assert oversized_evidence["validator_identity"] is not None


def test_privacy_review_blocks_flagship_readiness_with_explicit_reason(tmp_path) -> None:
    module = load_module()
    gate_path = tmp_path / "privacy-launch-gate.json"
    gate = privacy_launch_gate_payload(review_required=True)

    summary = summarize_with_valid_campaign(module,
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

    summary = summarize_with_valid_campaign(module,
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
        summary = summarize_with_valid_campaign(module,
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

    summary = summarize_with_valid_campaign(module,
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


def test_repository_hosted_build_decision_receipt_is_review_required(monkeypatch) -> None:
    module = load_module()
    receipt_path = module.DEFAULT_HOSTED_BUILD_OPERATOR_DECISIONS
    receipt, load_status = module.load_json(receipt_path)
    generated_at = datetime.strptime(
        str(receipt["generatedAtUtc"]),
        "%Y-%m-%dT%H:%M:%SZ",
    ).replace(tzinfo=UTC)

    class ReceiptObservationClock(datetime):
        @classmethod
        def now(cls, tz=None):  # noqa: ANN001, ANN206
            observed = generated_at + timedelta(hours=1)
            return observed if tz is not None else observed.replace(tzinfo=None)

    monkeypatch.setattr(module, "datetime", ReceiptObservationClock)

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

    summary = summarize_with_valid_campaign(module,
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

    summary = summarize_with_valid_campaign(module,
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
        summary = summarize_with_valid_campaign(module,
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

    summary = summarize_with_valid_campaign(module, payload)

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

    summary = summarize_with_valid_campaign(module, payload)

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

    summary = summarize_with_valid_campaign(module, payload)

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

    summary = summarize_with_valid_campaign(module, payload)

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

    summary = summarize_with_valid_campaign(module, payload)

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

    summary = summarize_with_valid_campaign(module, payload)

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

    summary = summarize_with_valid_campaign(module, payload)

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
    summary = summarize_with_valid_campaign(module, payload)

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

    summary = summarize_with_valid_campaign(module, payload)

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

    summary = summarize_with_valid_campaign(module, payload)

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

    summary = summarize_with_valid_campaign(module, payload)

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

    summary = summarize_with_valid_campaign(module, payload)

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

    summary = summarize_with_valid_campaign(module, payload)

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

    summary = summarize_with_valid_campaign(module, payload)

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

    summary = summarize_with_valid_campaign(module, payload)

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

    summary = summarize_with_valid_campaign(module, payload)

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

    summary = summarize_with_valid_campaign(module, payload)

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

    summary = summarize_with_valid_campaign(module, payload)

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

    summary = summarize_with_valid_campaign(module, payload)

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
    summary = summarize_with_valid_campaign(module,
        payload,
        readiness_path=tmp_path / "FLAGSHIP_PRODUCT_READINESS.generated.json",
    )

    assert stale_drift not in summary["launch_critical_nested_blockers"]
    assert not any(
        blocker.startswith(module.WORKSPACE_PORTAL_RELEASE_CHANNEL_DRIFT_PREFIX)
        for blocker in summary["launch_critical_nested_blockers"]
    )


def test_workspace_portal_release_channel_drift_uses_active_atomic_generation(
    tmp_path,
    monkeypatch,
) -> None:
    module = load_module()
    shelf_root = tmp_path / "downloads"
    generation_root = shelf_root / "generations" / "g-current"
    generation_root.mkdir(parents=True)
    portal_path = shelf_root / "RELEASE_CHANNEL.generated.json"
    authoritative = {
        "status": "published",
        "channel": "preview",
        "version": "run-current",
        "supportabilityState": "review_required",
        "rolloutState": "coverage_incomplete",
    }
    portal_path.write_text(
        json.dumps({**authoritative, "version": "run-stale-legacy"}),
        encoding="utf-8",
    )
    (generation_root / portal_path.name).write_text(
        json.dumps(authoritative),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        module,
        "resolve_shelf_root",
        lambda _root: ("generation", generation_root, {"generationId": "g-current"}),
    )

    assert module.workspace_portal_release_channel_drift_failures(
        authoritative,
        portal_path,
    ) == []


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
    summary = summarize_with_valid_campaign(module,
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

    summary = summarize_with_valid_campaign(module,
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

    summary = summarize_with_valid_campaign(module, payload)

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
    install_valid_campaign_os_local_proof_default(module, tmp_path, monkeypatch)
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
    install_valid_campaign_os_local_proof_default(module, tmp_path, monkeypatch)
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
    install_valid_campaign_os_local_proof_default(module, tmp_path, monkeypatch)
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
    install_valid_campaign_os_local_proof_default(module, tmp_path, monkeypatch)
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
    install_valid_campaign_os_local_proof_default(module, tmp_path, monkeypatch)
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
    install_valid_campaign_os_local_proof_default(module, tmp_path, monkeypatch)
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

    summary = summarize_with_valid_campaign(module, payload)

    assert summary["pass"] is False
    assert summary["launch_critical_nested_blockers"] == [
        f"google oauth linking proof receipt is malformed: {google_receipt}",
    ]
    assert summary["reason"] == (
        f"Launch blockers: google oauth linking proof receipt is malformed: {google_receipt}."
    )


def test_main_propagates_missing_campaign_os_proof_to_gate_output(
    tmp_path,
    monkeypatch,
) -> None:
    module = load_module()
    missing_proof = install_valid_campaign_os_local_proof_default(
        module,
        tmp_path,
        monkeypatch,
    )
    missing_proof.unlink()
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
    readiness.write_text(json.dumps(passing_payload()), encoding="utf-8")
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
            "--campaign-os-local-proof",
            str(missing_proof),
            "--summary-output",
            str(summary_path),
        ],
    )

    assert module.main() == 1
    written = json.loads(summary_path.read_text(encoding="utf-8"))
    expected_blocker = (
        f"{module.CAMPAIGN_OS_LOCAL_PROOF_BLOCKER_PREFIX} (receipt_missing)."
    )
    assert written["pass"] is False
    assert written["readiness_receipt_fail_closed"] is True
    assert written["launch_critical_nested_blockers"] == [expected_blocker]
    assert written["campaign_os_local_proof"]["path"] == str(missing_proof)
    assert written["campaign_os_local_proof"]["load_status"] == "missing"
    assert written["campaign_os_local_proof"]["reason_code"] == "receipt_missing"
    assert written["campaign_os_local_proof"]["pass"] is False
    assert written["campaign_os_local_proof"]["receipt_identity"] is None
    assert written["campaign_os_local_proof"]["validator_identity"] is not None
    assert written["summary"]["campaign_os_local_proof"] == written[
        "campaign_os_local_proof"
    ]


def test_main_writes_default_published_summary_output(tmp_path, monkeypatch) -> None:
    module = load_module()
    campaign_os_local_proof = install_valid_campaign_os_local_proof_default(
        module,
        tmp_path,
        monkeypatch,
    )
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
    assert written["campaign_os_local_proof"]["path"] == str(
        campaign_os_local_proof
    )
    assert written["campaign_os_local_proof"]["pass"] is True
    assert written["campaign_os_local_proof"]["reason_code"] == "valid"
    assert written["campaign_os_local_proof"]["receipt_identity"] is not None
    assert written["campaign_os_local_proof"]["validator_identity"] is not None
    assert written["summary"]["campaign_os_local_proof"] == written[
        "campaign_os_local_proof"
    ]
