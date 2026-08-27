from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


CONTRACT_NAME = "chummer.ea_release_component_matrix.v1"
REPORT_CONTRACT_NAME = "chummer.ea_component_status_report.v1"
CANONICAL_MATRIX = Path(__file__).with_name("ea_release_component_matrix.v1.json")

RELEASE_CRITICAL_COMPONENT_IDS = (
    "release_approval_ledger",
    "publication_authorization",
    "operator_revocation_transport",
)
NON_RELEASE_CRITICAL_COMPONENT_IDS = (
    "audiobook_providers",
    "memorial_memory_bridge",
    "black_ledger_automation",
    "travel_ooda",
    "outbound_growth",
)
KNOWN_COMPONENT_IDS = (
    *RELEASE_CRITICAL_COMPONENT_IDS,
    *NON_RELEASE_CRITICAL_COMPONENT_IDS,
)
EXPECTED_GATE_BINDINGS = {
    "verify_ea_operator_readiness": RELEASE_CRITICAL_COMPONENT_IDS,
}

MATRIX_KEYS = {
    "contract_name",
    "schema_version",
    "product",
    "decision_scope",
    "unknown_component_policy",
    "blocker_selection_policy",
    "release_critical_component_ids",
    "components",
    "gate_bindings",
}
COMPONENT_KEYS = {
    "component_id",
    "release_critical",
    "may_block_chummer_release",
    "failure_policy",
}
GATE_BINDING_KEYS = {"gate_id", "component_ids"}
REPORT_KEYS = {"contract_name", "components"}
REPORT_ROW_REQUIRED_KEYS = {"component_id", "status"}
REPORT_ROW_ALLOWED_KEYS = {*REPORT_ROW_REQUIRED_KEYS, "detail"}
REPORT_STATUSES = {"pass", "fail", "unavailable", "unknown"}


class PolicyValidationError(ValueError):
    def __init__(self, failures: Iterable[str]):
        self.failures = tuple(failures)
        super().__init__("; ".join(self.failures))


@dataclass(frozen=True)
class ComponentPolicy:
    component_id: str
    release_critical: bool
    may_block_chummer_release: bool
    failure_policy: str


@dataclass(frozen=True)
class ReleasePolicy:
    components: dict[str, ComponentPolicy]
    gate_bindings: dict[str, tuple[str, ...]]

    def component_ids_for_gate(self, gate_id: str) -> tuple[str, ...]:
        return self.gate_bindings.get(gate_id, ())

    def gate_may_block_chummer_release(self, gate_id: str) -> bool:
        component_ids = self.component_ids_for_gate(gate_id)
        if not component_ids:
            return True
        return any(
            self.components[component_id].may_block_chummer_release
            for component_id in component_ids
        )


def load_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PolicyValidationError([f"missing JSON input: {path}"]) from exc
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PolicyValidationError([f"invalid JSON input {path}: {exc}"]) from exc
    if not isinstance(payload, dict):
        raise PolicyValidationError([f"JSON root must be an object: {path}"])
    return payload


def _exact_keys(
    value: dict[str, Any],
    expected: set[str],
    location: str,
    failures: list[str],
) -> None:
    missing = sorted(expected - value.keys())
    unexpected = sorted(value.keys() - expected)
    if missing:
        failures.append(f"{location} is missing fields: {', '.join(missing)}")
    if unexpected:
        failures.append(
            f"{location} contains unauthorized fields: {', '.join(unexpected)}"
        )


def _expected_component(component_id: str) -> ComponentPolicy:
    if component_id in RELEASE_CRITICAL_COMPONENT_IDS:
        return ComponentPolicy(component_id, True, True, "fail_closed")
    return ComponentPolicy(component_id, False, False, "record_only")


def validate_matrix_payload(payload: dict[str, Any]) -> ReleasePolicy:
    failures: list[str] = []
    _exact_keys(payload, MATRIX_KEYS, "matrix", failures)
    expected_scalars = {
        "contract_name": CONTRACT_NAME,
        "schema_version": 1,
        "product": "chummer6",
        "decision_scope": "chummer_release",
        "unknown_component_policy": "fail_closed",
        "blocker_selection_policy": "explicit_allowlist",
    }
    for field, expected in expected_scalars.items():
        actual = payload.get(field)
        if type(actual) is not type(expected) or actual != expected:
            failures.append(f"matrix {field} must be {expected!r}, got {actual!r}")

    critical_ids = payload.get("release_critical_component_ids")
    if not isinstance(critical_ids, list) or any(
        not isinstance(item, str) for item in critical_ids
    ):
        failures.append("matrix release_critical_component_ids must be a string list")
    elif tuple(critical_ids) != RELEASE_CRITICAL_COMPONENT_IDS:
        failures.append(
            "matrix release_critical_component_ids must exactly match the "
            "code-pinned Chummer blocker allowlist"
        )

    raw_components = payload.get("components")
    if not isinstance(raw_components, list):
        failures.append("matrix components must be a list")
        raw_components = []
    components: dict[str, ComponentPolicy] = {}
    for index, row in enumerate(raw_components):
        location = f"matrix components[{index}]"
        if not isinstance(row, dict):
            failures.append(f"{location} must be an object")
            continue
        _exact_keys(row, COMPONENT_KEYS, location, failures)
        component_id = row.get("component_id")
        if not isinstance(component_id, str) or not component_id:
            failures.append(f"{location} component_id must be a non-empty string")
            continue
        if component_id not in KNOWN_COMPONENT_IDS:
            failures.append(
                f"{location} contains unknown component {component_id!r}; "
                "unknown components fail closed"
            )
            continue
        if component_id in components:
            failures.append(f"matrix contains duplicate component {component_id!r}")
            continue
        expected = _expected_component(component_id)
        actual_values = (
            row.get("release_critical"),
            row.get("may_block_chummer_release"),
            row.get("failure_policy"),
        )
        expected_values = (
            expected.release_critical,
            expected.may_block_chummer_release,
            expected.failure_policy,
        )
        if any(
            type(actual) is not type(expected_value) or actual != expected_value
            for actual, expected_value in zip(actual_values, expected_values)
        ):
            failures.append(
                f"matrix component {component_id!r} classification must be "
                f"release_critical={expected.release_critical!r}, "
                f"may_block_chummer_release={expected.may_block_chummer_release!r}, "
                f"failure_policy={expected.failure_policy!r}"
            )
        components[component_id] = expected

    missing_components = sorted(set(KNOWN_COMPONENT_IDS) - components.keys())
    if missing_components:
        failures.append(
            "matrix is missing code-pinned components: " + ", ".join(missing_components)
        )
    if len(raw_components) != len(KNOWN_COMPONENT_IDS):
        failures.append(
            f"matrix must contain exactly {len(KNOWN_COMPONENT_IDS)} component rows"
        )

    raw_bindings = payload.get("gate_bindings")
    if not isinstance(raw_bindings, list):
        failures.append("matrix gate_bindings must be a list")
        raw_bindings = []
    gate_bindings: dict[str, tuple[str, ...]] = {}
    for index, row in enumerate(raw_bindings):
        location = f"matrix gate_bindings[{index}]"
        if not isinstance(row, dict):
            failures.append(f"{location} must be an object")
            continue
        _exact_keys(row, GATE_BINDING_KEYS, location, failures)
        gate_id = row.get("gate_id")
        component_ids = row.get("component_ids")
        if not isinstance(gate_id, str) or not gate_id:
            failures.append(f"{location} gate_id must be a non-empty string")
            continue
        if gate_id in gate_bindings:
            failures.append(f"matrix contains duplicate gate binding {gate_id!r}")
            continue
        if not isinstance(component_ids, list) or not component_ids or any(
            not isinstance(item, str) for item in component_ids
        ):
            failures.append(f"{location} component_ids must be a non-empty string list")
            continue
        unknown = sorted(set(component_ids) - set(KNOWN_COMPONENT_IDS))
        if unknown:
            failures.append(
                f"{location} references unknown components: {', '.join(unknown)}; "
                "unknown components fail closed"
            )
        if len(set(component_ids)) != len(component_ids):
            failures.append(f"{location} contains duplicate component_ids")
        gate_bindings[gate_id] = tuple(component_ids)

    if gate_bindings != EXPECTED_GATE_BINDINGS:
        failures.append(
            "matrix gate_bindings must exactly match the code-pinned EA release gate bindings"
        )
    if failures:
        raise PolicyValidationError(failures)
    return ReleasePolicy(components=components, gate_bindings=gate_bindings)


def load_and_validate_matrix(path: Path = CANONICAL_MATRIX) -> ReleasePolicy:
    return validate_matrix_payload(load_json_object(path))


def validate_gate_coverage(
    policy: ReleasePolicy,
    canonical_gate_ids: Iterable[str],
) -> None:
    available = set(canonical_gate_ids)
    missing = sorted(set(policy.gate_bindings) - available)
    if missing:
        raise PolicyValidationError(
            ["EA matrix references non-canonical release gates: " + ", ".join(missing)]
        )


def evaluate_component_report(
    policy: ReleasePolicy,
    payload: dict[str, Any],
) -> dict[str, Any]:
    failures: list[str] = []
    _exact_keys(payload, REPORT_KEYS, "component report", failures)
    if payload.get("contract_name") != REPORT_CONTRACT_NAME:
        failures.append(
            f"component report contract_name must be {REPORT_CONTRACT_NAME!r}"
        )
    rows = payload.get("components")
    if not isinstance(rows, list):
        failures.append("component report components must be a list")
        rows = []
    statuses: dict[str, tuple[str, str | None]] = {}
    for index, row in enumerate(rows):
        location = f"component report components[{index}]"
        if not isinstance(row, dict):
            failures.append(f"{location} must be an object")
            continue
        missing = sorted(REPORT_ROW_REQUIRED_KEYS - row.keys())
        unexpected = sorted(row.keys() - REPORT_ROW_ALLOWED_KEYS)
        if missing:
            failures.append(f"{location} is missing fields: {', '.join(missing)}")
        if unexpected:
            failures.append(
                f"{location} contains unauthorized fields: {', '.join(unexpected)}; "
                "reports cannot self-declare blocker authority"
            )
        component_id = row.get("component_id")
        if not isinstance(component_id, str) or not component_id:
            failures.append(f"{location} component_id must be a non-empty string")
            continue
        if component_id not in policy.components:
            failures.append(
                f"{location} contains unknown component {component_id!r}; "
                "unknown components fail closed"
            )
            continue
        if component_id in statuses:
            failures.append(f"component report contains duplicate component {component_id!r}")
            continue
        status = row.get("status")
        if status not in REPORT_STATUSES:
            failures.append(f"{location} has invalid status {status!r}")
            continue
        detail = row.get("detail")
        if detail is not None and (not isinstance(detail, str) or not detail.strip()):
            failures.append(f"{location} detail must be a non-empty string when present")
            detail = None
        statuses[component_id] = (status, detail)
    if failures:
        raise PolicyValidationError(failures)

    blockers: list[dict[str, str]] = []
    for component_id in RELEASE_CRITICAL_COMPONENT_IDS:
        status, detail = statuses.get(component_id, ("unknown", None))
        if status == "pass":
            continue
        blocker = {"component_id": component_id, "status": status}
        if detail:
            blocker["detail"] = detail
        elif component_id not in statuses:
            blocker["detail"] = "release-critical component status is missing"
        blockers.append(blocker)
    findings: list[dict[str, str]] = []
    for component_id in NON_RELEASE_CRITICAL_COMPONENT_IDS:
        if component_id not in statuses:
            continue
        status, detail = statuses[component_id]
        if status == "pass":
            continue
        finding = {"component_id": component_id, "status": status}
        if detail:
            finding["detail"] = detail
        findings.append(finding)
    return {
        "contract_name": "chummer.ea_release_component_decision.v1",
        "status": "blocked" if blockers else "pass",
        "release_ready": not blockers,
        "release_blockers": blockers,
        "non_release_critical_findings": findings,
    }
