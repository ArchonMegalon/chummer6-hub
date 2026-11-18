from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "scripts" / "ea_release_component_policy.py"
MATRIX = ROOT / "scripts" / "ea_release_component_matrix.v1.json"
VERIFY = ROOT / "scripts" / "verify_ea_release_component_matrix.py"
RELEASE = ROOT / "scripts" / "materialize_release_ready_receipt.py"


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def canonical_payload() -> dict:
    return json.loads(MATRIX.read_text(encoding="utf-8"))


def passing_report(module) -> dict:
    return {
        "contract_name": module.REPORT_CONTRACT_NAME,
        "components": [
            {"component_id": component_id, "status": "pass"}
            for component_id in module.RELEASE_CRITICAL_COMPONENT_IDS
        ],
    }


def controller_environment(module) -> dict[str, str]:
    return {
        "CHUMMER_PUBLIC_BASE_URL": "https://chummer.run",
        "CHUMMER_RELEASE_READY_GATE_TIMEOUT_SECONDS": "900",
        "CHUMMER_RELEASE_READY_GUIDE_GATE_TIMEOUT_SECONDS": "1800",
        "CHUMMER_PUBLIC_EDGE_TIMEOUT_SECONDS": "60",
        "CHUMMER_PUBLIC_EDGE_PLAYWRIGHT_REUSE_MAX_AGE_HOURS": "24",
        "CHUMMER_RELEASE_READY_SKIP_GOOGLE_OAUTH_RUNTIME_REFRESH": "0",
        "CHUMMER_RELEASE_READY_SKIP_WINDOWS_RUNTIME_REFRESH": "0",
        "CHUMMER_BLAZOR_REQUIRE_LOCAL_E2E": "0",
        "CHUMMER_BLAZOR_REQUIRE_SELF_HOST_E2E": "0",
        module.EXPECTED_RELEASE_CHANNEL_RECEIPT_SHA256_ENV: "a" * 64,
    }


def test_canonical_matrix_has_exact_code_pinned_blocker_allowlist() -> None:
    module = load(POLICY, "ea_release_component_policy_exact")
    policy = module.load_and_validate_matrix()

    assert tuple(policy.components) == module.KNOWN_COMPONENT_IDS
    assert tuple(
        component_id
        for component_id, row in policy.components.items()
        if row.may_block_chummer_release
    ) == module.RELEASE_CRITICAL_COMPONENT_IDS
    assert all(
        not policy.components[component_id].release_critical
        and not policy.components[component_id].may_block_chummer_release
        and policy.components[component_id].failure_policy == "record_only"
        for component_id in module.NON_RELEASE_CRITICAL_COMPONENT_IDS
    )


def test_unknown_component_in_matrix_fails_closed() -> None:
    module = load(POLICY, "ea_release_component_policy_unknown")
    payload = canonical_payload()
    payload["components"][-1]["component_id"] = "unreviewed_provider"

    with pytest.raises(module.PolicyValidationError) as exc_info:
        module.validate_matrix_payload(payload)

    assert "unknown component 'unreviewed_provider'" in str(exc_info.value)


def test_boolean_shaped_numbers_cannot_spoof_matrix_types() -> None:
    module = load(POLICY, "ea_release_component_policy_types")
    payload = canonical_payload()
    payload["schema_version"] = True
    payload["components"][0]["release_critical"] = 1

    with pytest.raises(module.PolicyValidationError) as exc_info:
        module.validate_matrix_payload(payload)

    assert "matrix schema_version must be 1, got True" in str(exc_info.value)
    assert "component 'release_approval_ledger' classification must be" in str(
        exc_info.value
    )


@pytest.mark.parametrize("component_id", [
    "audiobook_providers",
    "memorial_memory_bridge",
    "black_ledger_automation",
    "travel_ooda",
    "outbound_growth",
])
def test_noncritical_components_cannot_be_promoted_in_data(
    component_id: str,
) -> None:
    module = load(POLICY, f"ea_release_component_policy_{component_id}")
    payload = canonical_payload()
    row = next(
        item for item in payload["components"] if item["component_id"] == component_id
    )
    row.update(
        {
            "release_critical": True,
            "may_block_chummer_release": True,
            "failure_policy": "fail_closed",
        }
    )

    with pytest.raises(module.PolicyValidationError) as exc_info:
        module.validate_matrix_payload(payload)

    assert f"component {component_id!r} classification must be" in str(exc_info.value)


def test_unknown_report_component_fails_closed() -> None:
    module = load(POLICY, "ea_release_component_policy_report_unknown")
    policy = module.load_and_validate_matrix()
    report = passing_report(module)
    report["components"].append(
        {"component_id": "surprise_component", "status": "fail"}
    )

    with pytest.raises(module.PolicyValidationError) as exc_info:
        module.evaluate_component_report(policy, report)

    assert "unknown component 'surprise_component'" in str(exc_info.value)


def test_report_cannot_self_declare_noncritical_blocker_authority() -> None:
    module = load(POLICY, "ea_release_component_policy_report_authority")
    policy = module.load_and_validate_matrix()
    report = passing_report(module)
    report["components"].append(
        {
            "component_id": "black_ledger_automation",
            "status": "fail",
            "blocks_release": True,
        }
    )

    with pytest.raises(module.PolicyValidationError) as exc_info:
        module.evaluate_component_report(policy, report)

    assert "reports cannot self-declare blocker authority" in str(exc_info.value)


def test_all_noncritical_failures_are_recorded_without_blocking() -> None:
    module = load(POLICY, "ea_release_component_policy_noncritical")
    policy = module.load_and_validate_matrix()
    report = passing_report(module)
    report["components"].extend(
        {
            "component_id": component_id,
            "status": "unavailable",
        }
        for component_id in module.NON_RELEASE_CRITICAL_COMPONENT_IDS
    )

    decision = module.evaluate_component_report(policy, report)

    assert decision["status"] == "pass"
    assert decision["release_ready"] is True
    assert decision["release_blockers"] == []
    assert {
        item["component_id"] for item in decision["non_release_critical_findings"]
    } == set(module.NON_RELEASE_CRITICAL_COMPONENT_IDS)


def test_only_allowlisted_critical_component_can_be_report_blocker() -> None:
    module = load(POLICY, "ea_release_component_policy_critical")
    policy = module.load_and_validate_matrix()
    report = passing_report(module)
    report["components"][1]["status"] = "fail"
    report["components"].append(
        {"component_id": "outbound_growth", "status": "fail"}
    )

    decision = module.evaluate_component_report(policy, report)

    assert [item["component_id"] for item in decision["release_blockers"]] == [
        "publication_authorization"
    ]
    assert decision["non_release_critical_findings"] == [
        {"component_id": "outbound_growth", "status": "fail"}
    ]


def test_noncritical_component_cannot_acquire_a_release_gate_in_data() -> None:
    module = load(POLICY, "ea_release_component_policy_gate_promotion")
    payload = canonical_payload()
    payload["gate_bindings"].append(
        {
            "gate_id": "verify_mymedia_public_surface",
            "component_ids": ["audiobook_providers"],
        }
    )

    with pytest.raises(module.PolicyValidationError) as exc_info:
        module.validate_matrix_payload(payload)

    assert "gate_bindings must exactly match the code-pinned" in str(exc_info.value)


def test_canonical_controller_applies_matrix_to_real_ea_gates() -> None:
    module = load(RELEASE, "materialize_release_ready_receipt_ea_matrix")
    specs = module.canonical_release_gate_specs(controller_environment(module))
    by_name = {str(item["name"]): item for item in specs}

    readiness = by_name["verify_ea_operator_readiness"]
    assert readiness["ea_component_ids"] == module.ea_release_component_policy.RELEASE_CRITICAL_COMPONENT_IDS
    assert readiness["release_blocking"] is True
    assert "verify_ea_release_component_matrix.py" in str(readiness["command"])
    assert any(
        str(path).endswith("verify_ea_release_component_matrix.py")
        for path in readiness["entrypoints"]
    )

    assert "verify_mymedia_public_surface" not in by_name
    bound_components = {
        component_id
        for item in specs
        for component_id in item["ea_component_ids"]
    }
    assert bound_components == set(
        module.ea_release_component_policy.RELEASE_CRITICAL_COMPONENT_IDS
    )
    assert not (
        bound_components
        & set(module.ea_release_component_policy.NON_RELEASE_CRITICAL_COMPONENT_IDS)
    )


def test_cli_unknown_component_is_nonzero_and_does_not_widen_blockers(
    tmp_path: Path,
) -> None:
    module = load(POLICY, "ea_release_component_policy_cli")
    report = passing_report(module)
    report["components"].append({"component_id": "surprise", "status": "pass"})
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")

    completed = subprocess.run(
        [sys.executable, str(VERIFY), "--component-report", str(report_path)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 1
    payload = json.loads(completed.stdout)
    assert payload["status"] == "fail_closed"
    assert payload["release_blockers"] == []
    assert any("unknown component 'surprise'" in item for item in payload["policy_failures"])
