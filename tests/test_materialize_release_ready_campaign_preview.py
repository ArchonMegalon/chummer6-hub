from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "materialize_release_ready_receipt.py"


def load_module():
    spec = importlib.util.spec_from_file_location(
        "materialize_release_ready_campaign_preview",
        SCRIPT,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_exact_seven_field_v2_declaration_preserves_outer_failure_truth() -> None:
    module = load_module()
    release_version = "run-20260728-050000"
    environment = {
        module.CAMPAIGN_PREVIEW_RELEASE_VERSION_ENV: release_version,
        module.CAMPAIGN_PREVIEW_SCOPE_SHA256_ENV: "a" * 64,
        module.CAMPAIGN_PREVIEW_OWNER_ENV: "chummer-release-operations",
        module.CAMPAIGN_PREVIEW_ACTIONS_ENV: json.dumps(
            ["Close the bounded release-ready flagship gap."]
        ),
    }

    declaration = module.campaign_operability_preview_declaration(
        environment,
        {"version": release_version},
    )

    assert declaration == {
        "contract_name": "chummer.campaign_operability_preview_evidence",
        "contract_version": 2,
        "status": "pass",
        "release_version": release_version,
        "release_scope_decision_sha256": "a" * 64,
        "bounded_owner": "chummer-release-operations",
        "next_actions": ["Close the bounded release-ready flagship gap."],
    }
    payload = {
        "status": "fail",
        "verdict": "NOT_RELEASE_READY",
        "failures": ["raw gate remains blocked"],
    }
    module.apply_campaign_operability_preview_declaration(payload, declaration)
    assert payload["status"] == "fail"
    assert payload["verdict"] == "NOT_RELEASE_READY"
    assert payload["failures"] == ["raw gate remains blocked"]
    assert payload["campaign_operability_preview"] == declaration


def test_preview_inputs_are_explicit_all_or_none_and_candidate_bound() -> None:
    module = load_module()
    release_version = "run-20260728-050000"
    valid = {
        module.CAMPAIGN_PREVIEW_RELEASE_VERSION_ENV: release_version,
        module.CAMPAIGN_PREVIEW_SCOPE_SHA256_ENV: "a" * 64,
        module.CAMPAIGN_PREVIEW_OWNER_ENV: "chummer-release-operations",
        module.CAMPAIGN_PREVIEW_ACTIONS_ENV: '["Close the bounded flagship gap."]',
    }
    assert module.campaign_operability_preview_declaration({}, {"version": release_version}) is None
    with pytest.raises(ValueError, match="all-or-none"):
        module.campaign_operability_preview_declaration(
            {module.CAMPAIGN_PREVIEW_RELEASE_VERSION_ENV: release_version},
            {"version": release_version},
        )

    for name, value in (
        (module.CAMPAIGN_PREVIEW_RELEASE_VERSION_ENV, "run-stale"),
        (module.CAMPAIGN_PREVIEW_SCOPE_SHA256_ENV, "A" * 64),
        (module.CAMPAIGN_PREVIEW_OWNER_ENV, "Release Operations"),
        (module.CAMPAIGN_PREVIEW_ACTIONS_ENV, '["todo"]'),
    ):
        mutated = dict(valid)
        mutated[name] = value
        with pytest.raises(ValueError):
            module.campaign_operability_preview_declaration(
                mutated,
                {"version": release_version},
            )
