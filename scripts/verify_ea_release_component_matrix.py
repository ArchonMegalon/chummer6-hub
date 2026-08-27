#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import ea_release_component_policy as policy_contract


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify the closed-world Chummer Executive Assistant release matrix."
    )
    parser.add_argument("--matrix", type=Path, default=policy_contract.CANONICAL_MATRIX)
    parser.add_argument("--component-report", type=Path)
    args = parser.parse_args()
    try:
        policy = policy_contract.load_and_validate_matrix(args.matrix)
        if args.component_report is None:
            payload = {
                "contract_name": "chummer.ea_release_component_decision.v1",
                "status": "pass",
                "release_ready": True,
                "release_blockers": [],
                "validated_component_ids": list(policy.components),
                "validated_gate_ids": list(policy.gate_bindings),
            }
        else:
            payload = policy_contract.evaluate_component_report(
                policy,
                policy_contract.load_json_object(args.component_report),
            )
    except policy_contract.PolicyValidationError as exc:
        payload = {
            "contract_name": "chummer.ea_release_component_decision.v1",
            "status": "fail_closed",
            "release_ready": False,
            "release_blockers": [],
            "policy_failures": list(exc.failures),
        }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["release_ready"] is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
