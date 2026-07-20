from __future__ import annotations

import importlib.util
import hashlib
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "materialize_horizon_readiness.py"
REGISTRY_PATH = REPO_ROOT / ".codex-design/product/HORIZON_REGISTRY.yaml"
CAPABILITY_SERVICE_PATH = (
    REPO_ROOT / "Chummer.Run.Api/Services/Community/HorizonCapabilityService.cs"
)
GENERATED_AT = "2026-07-20T20:00:00Z"


def load_module():
    spec = importlib.util.spec_from_file_location("materialize_horizon_readiness_test", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def by_id(records: list[dict], field: str) -> dict[str, dict]:
    return {record[field]: record for record in records}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def materialize_current(module, tmp_path: Path, *, capability_path: Path = CAPABILITY_SERVICE_PATH):
    return module.materialize(
        REPO_ROOT,
        tmp_path / "HORIZON_READINESS.generated.json",
        registry_path=REGISTRY_PATH,
        capability_service_path=capability_path,
        generated_at_utc=GENERATED_AT,
    )


def toggle_enabled_defaults(source: str) -> str:
    return (
        source.replace("EnabledByDefault: true", "EnabledByDefault: __TRUE__")
        .replace("EnabledByDefault: false", "EnabledByDefault: true")
        .replace("EnabledByDefault: __TRUE__", "EnabledByDefault: false")
    )


def inject_capability(source: str, capability_id: str, horizon_id: str) -> str:
    marker = "\n    ];\n\n    private readonly IConfiguration"
    assert marker in source
    block = f"""
,
        new(
            HorizonId: "{horizon_id}",
            CapabilityId: "{capability_id}",
            ArtifactKind: "test_artifact",
            PublicLabel: "Test Artifact",
            CapabilitySlot: "test_slot",
            InternalProviderLane: "First-party test lane",
            FreeWeeklyLimit: 0,
            SupporterWeeklyLimit: 0,
            RequiresAuthentication: false,
            PublicVisible: false,
            EnabledByDefault: true,
            CostClass: "low")
"""
    return source.replace(marker, block + marker, 1)


def test_materializer_joins_current_catalogs_and_emits_every_record_once(tmp_path: Path) -> None:
    module = load_module()

    payload = materialize_current(module, tmp_path)

    horizon_ids = [item["horizon_id"] for item in payload["horizons"]]
    capability_ids = [item["capability_id"] for item in payload["capabilities"]]
    assert len(horizon_ids) == len(set(horizon_ids)) == 15
    assert len(capability_ids) == len(set(capability_ids)) == 20
    assert payload["catalog_coverage"] == {
        "canonical_horizon_count": 9,
        "capability_horizon_count": 13,
        "joined_horizon_count": 15,
        "capability_count": 20,
        "canonical_horizons_without_capabilities": ["alice", "knowledge-fabric"],
        "capability_horizons_not_canonical": [
            "community_hub",
            "creator_os",
            "living_world",
            "propertyquarry",
            "runner_passport",
            "signal_deck",
        ],
        "unknown_capability_ids": [],
        "all_current_capabilities_assessed": True,
    }
    assert payload["readiness_derivation"] == {
        "catalog_driven_enumeration": True,
        "enabled_by_default_used": False,
        "declared_shipment_state_used": False,
        "runtime_probe_performed": False,
        "provider_call_performed": False,
        "quota_consumed": False,
        "unknown_records_fail_closed": True,
    }
    assert payload["status"] == "attention_required"
    assert payload["operational_readiness_claim_allowed"] is False
    assert payload["generated_at_utc"] == GENERATED_AT
    assert payload["generator"] == {
        "path": "scripts/materialize_horizon_readiness.py",
        "sha256": sha256_file(SCRIPT_PATH),
    }

    horizons = by_id(payload["horizons"], "horizon_id")
    capabilities = by_id(payload["capabilities"], "capability_id")
    assert horizons["alice"]["source_status"] == "working"
    assert horizons["alice"]["runtime_status"] == "unverified"
    assert horizons["knowledge-fabric"]["source_status"] == "working"
    assert horizons["knowledge-fabric"]["runtime_status"] == "unverified"
    assert horizons["origin-dossier"]["source_status"] == "working"
    assert horizons["origin-dossier"]["runtime_status"] == "unverified"
    assert horizons["origin-dossier"]["governance_status"] == "governance_blocked"
    assert capabilities["runsite-map"]["source_status"] == "working"
    assert capabilities["runbook-export"]["source_status"] == "working"
    assert capabilities["karma-forge-discovery"]["source_status"] == "working"
    assert capabilities["runsite-scene-render"]["governance_status"] == "governance_blocked"
    assert capabilities["jackpoint-briefing-video"]["runtime_status"] == "runtime_blocked"
    assert capabilities["black-ledger-newsroom"]["runtime_status"] == "unverified"
    assert not any(
        item["runtime_status"] == "ready"
        for item in payload["horizons"] + payload["capabilities"]
    )
    assert all(item["enabled_used_for_readiness"] is False for item in payload["capabilities"])
    assert all(
        item["declared_state_used_for_readiness"] is False for item in payload["horizons"]
    )


def test_source_evidence_inventory_exactly_binds_all_record_references(tmp_path: Path) -> None:
    module = load_module()
    payload = materialize_current(module, tmp_path)

    expected_refs = sorted(
        {
            ref
            for record in payload["horizons"] + payload["capabilities"]
            for ref in record["evidence_refs"]
        }
    )
    inventory = payload["source_evidence"]
    assert [record["path"] for record in inventory["records"]] == expected_refs
    assert inventory["record_count"] == len(expected_refs)
    assert inventory["present_count"] + inventory["missing_count"] == len(expected_refs)
    assert payload["summary"]["source_evidence"] == {
        "present_count": inventory["present_count"],
        "missing_count": inventory["missing_count"],
    }

    for record in inventory["records"]:
        source = REPO_ROOT / record["path"]
        if source.is_file():
            assert record == {
                "path": record["path"],
                "state": "present",
                "sha256": sha256_file(source),
            }
        else:
            assert record == {
                "path": record["path"],
                "state": "missing",
                "sha256": None,
            }


def test_fixed_generation_time_produces_identical_digest_bound_payloads(tmp_path: Path) -> None:
    module = load_module()

    first = materialize_current(module, tmp_path / "first")
    second = materialize_current(module, tmp_path / "second")

    assert first == second


@pytest.mark.parametrize(
    "unsafe_ref",
    [
        "/tmp/evidence.json",
        "Users/operator/evidence.json",
        ".env.production",
        "proofs/bearer-token.json",
    ],
)
def test_materializer_rejects_unsafe_evidence_references(
    tmp_path: Path,
    unsafe_ref: str,
) -> None:
    module = load_module()
    module.CAPABILITY_ASSESSMENTS["runsite-tour"]["evidence_refs"] = [unsafe_ref]

    with pytest.raises(ValueError, match="unsafe evidence reference"):
        materialize_current(module, tmp_path)


def test_enabled_by_default_changes_metadata_but_never_readiness(tmp_path: Path) -> None:
    module = load_module()
    original = CAPABILITY_SERVICE_PATH.read_text(encoding="utf-8")
    toggled_path = tmp_path / "HorizonCapabilityService.cs"
    toggled_path.write_text(toggle_enabled_defaults(original), encoding="utf-8")

    baseline = materialize_current(module, tmp_path / "baseline")
    toggled = materialize_current(module, tmp_path / "toggled", capability_path=toggled_path)

    baseline_records = by_id(baseline["capabilities"], "capability_id")
    toggled_records = by_id(toggled["capabilities"], "capability_id")
    assert set(baseline_records) == set(toggled_records)
    assert any(
        baseline_records[item]["enabled_by_default"]
        != toggled_records[item]["enabled_by_default"]
        for item in baseline_records
    )
    for capability_id in baseline_records:
        assert (
            baseline_records[capability_id]["source_status"],
            baseline_records[capability_id]["runtime_status"],
            baseline_records[capability_id]["governance_status"],
        ) == (
            toggled_records[capability_id]["source_status"],
            toggled_records[capability_id]["runtime_status"],
            toggled_records[capability_id]["governance_status"],
        )


def test_new_catalog_capability_is_emitted_once_and_fails_closed(tmp_path: Path) -> None:
    module = load_module()
    source = CAPABILITY_SERVICE_PATH.read_text(encoding="utf-8")
    capability_path = tmp_path / "HorizonCapabilityService.cs"
    capability_path.write_text(
        inject_capability(source, "future-lane-artifact", "future_lane"),
        encoding="utf-8",
    )

    payload = materialize_current(module, tmp_path / "out", capability_path=capability_path)

    capabilities = [
        item
        for item in payload["capabilities"]
        if item["capability_id"] == "future-lane-artifact"
    ]
    horizons = [item for item in payload["horizons"] if item["horizon_id"] == "future_lane"]
    assert len(capabilities) == 1
    assert len(horizons) == 1
    assert capabilities[0]["source_status"] == "unassessed"
    assert capabilities[0]["runtime_status"] == "unverified"
    assert capabilities[0]["governance_status"] == "unverified"
    assert capabilities[0]["assessment_source"] == "fail_closed_catalog_default"
    assert horizons[0]["capability_ids"] == ["future-lane-artifact"]
    assert payload["catalog_coverage"]["unknown_capability_ids"] == [
        "future-lane-artifact"
    ]
    assert payload["catalog_coverage"]["all_current_capabilities_assessed"] is False
    assert payload["operational_readiness_claim_allowed"] is False


def test_duplicate_capability_id_is_rejected_at_source(tmp_path: Path) -> None:
    module = load_module()
    source = CAPABILITY_SERVICE_PATH.read_text(encoding="utf-8")
    duplicate_path = tmp_path / "HorizonCapabilityService.cs"
    duplicate_path.write_text(
        inject_capability(source, "runsite-tour", "duplicate_horizon"),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="duplicate capability id: runsite-tour"):
        module.parse_capability_catalog(duplicate_path)


def test_duplicate_canonical_horizon_id_is_rejected(tmp_path: Path) -> None:
    module = load_module()
    registry = tmp_path / "HORIZON_REGISTRY.yaml"
    registry.write_text(
        """
product: chummer
horizons:
- id: alice
  title: ALICE
- id: alice
  title: Duplicate ALICE
""".lstrip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="duplicate horizon id: alice"):
        module.parse_horizon_registry(registry)
