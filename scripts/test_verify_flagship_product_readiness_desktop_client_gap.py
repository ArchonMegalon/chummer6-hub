from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("verify_flagship_product_readiness_gate.py")


def load_module():
    spec = importlib.util.spec_from_file_location("flagship_product_readiness_gate", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def external_windows_only_payload(
    *,
    journey_required: object = True,
    journey_status: object = "pass",
    journey_ready: object = True,
) -> dict:
    return {
        "coverage_details": {
            "desktop_client": {
                "evidence": {
                    "ui_linux_exit_gate_effective_ready": True,
                    "ui_workflow_execution_gate_status": "pass",
                    "ui_visual_familiarity_exit_gate_status": "pass",
                    "ui_flagship_release_gate_status": "pass",
                    "ui_user_journey_tester_audit_required": journey_required,
                    "ui_user_journey_tester_audit_status": journey_status,
                    "ui_user_journey_tester_audit_ready": journey_ready,
                    "ui_executable_exit_gate_blocking_mode": "external_only",
                    "ui_windows_exit_gate_blocking_mode": "external_only",
                    "ui_external_host_proof_blockers_unresolved_hosts": ["windows"],
                }
            }
        }
    }


def test_external_windows_gap_is_subsumed_only_when_user_journey_audit_passes() -> None:
    module = load_module()
    blockers = ["Windows installer visual audit source digest does not match promoted installer"]

    assert module.desktop_client_gap_subsumed_by_launch_blockers(
        external_windows_only_payload(),
        blockers,
    )
    assert not module.desktop_client_gap_subsumed_by_launch_blockers(
        external_windows_only_payload(journey_status="fail"),
        blockers,
    )
    assert not module.desktop_client_gap_subsumed_by_launch_blockers(
        external_windows_only_payload(journey_ready=False),
        blockers,
    )
    assert not module.desktop_client_gap_subsumed_by_launch_blockers(
        external_windows_only_payload(journey_status=None),
        blockers,
    )
    assert not module.desktop_client_gap_subsumed_by_launch_blockers(
        external_windows_only_payload(journey_ready="true"),
        blockers,
    )
    assert not module.desktop_client_gap_subsumed_by_launch_blockers(
        external_windows_only_payload(journey_required="true"),
        blockers,
    )


def test_external_windows_gap_can_be_subsumed_when_user_journey_audit_is_not_required() -> None:
    module = load_module()
    blockers = ["Windows installer visual audit source digest does not match promoted installer"]

    assert module.desktop_client_gap_subsumed_by_launch_blockers(
        external_windows_only_payload(
            journey_required=False,
            journey_status="fail",
            journey_ready=False,
        ),
        blockers,
    )
