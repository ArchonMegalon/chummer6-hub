from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "materialize_public_release_snapshot_readonly_audit.py"
SPEC = importlib.util.spec_from_file_location("public_release_snapshot_audit", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
MODULE.DEFAULT_AUXILIARY_RELEASE_RECEIPTS = {}


def write_json(path: Path, payload: dict[str, object]) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def release_channel(*, channel: str, version: str, generated_at: str) -> dict[str, object]:
    stable = channel == "public_stable"
    return {
        "generatedAt": generated_at,
        "status": "published",
        "channel": channel,
        "version": version,
        "supportabilityState": "gold_supported" if stable else "preview_supported",
        "rolloutState": "public_stable" if stable else "promoted_preview",
    }


def readiness_gate(
    *,
    ready: bool,
    generated_at: str,
    coverage_gap_keys: list[str] | None = None,
) -> dict[str, object]:
    blockers = [] if ready else [
        "release channel channel is preview, not a flagship stable lane",
        "release channel supportability is not gold_supported",
        "release channel rollout is promoted_preview, not public_stable",
    ]
    return {
        "generated_at_utc": generated_at,
        "status": "pass" if ready else "fail",
        "verdict": "FLAGSHIP_PRODUCT_READY" if ready else "NOT_FLAGSHIP_PRODUCT_READY",
        "pass": ready,
        "launch_critical_nested_blockers": blockers,
        "coverage_gap_keys": list(coverage_gap_keys or []),
    }


def snapshot(*, channel: str, version: str, generated_at: str, ready: bool = True) -> dict[str, object]:
    return {
        "channel": channel,
        "build_id": version,
        "generated_at": generated_at,
        "launch_ready_from_current_truth": ready,
        "release_channel_state": {"flagship_release_posture": ready},
    }


def test_preview_truth_overrides_stale_gold_snapshot(tmp_path: Path) -> None:
    snapshot_path = write_json(tmp_path / "snapshot.json", snapshot(channel="public_stable", version="old", generated_at="2026-01-01T00:00:00Z"))
    channel_path = write_json(tmp_path / "channel.json", release_channel(channel="preview", version="new", generated_at="2026-01-03T00:00:00Z"))
    gate_path = write_json(tmp_path / "gate.json", readiness_gate(ready=False, generated_at="2026-01-03T00:01:00Z"))

    audit = MODULE.build_audit(snapshot_path, channel_path, gate_path, generated_at_utc="2026-01-03T00:02:00Z")

    assert audit["status"] == "fail"
    assert audit["launch_ready_from_current_truth"] is False
    assert audit["final_gold_verdict"] == "NOT_GOLD"
    assert audit["flagship_product_readiness_verdict"] == "NOT_FLAGSHIP_PRODUCT_READY"
    assert "release_posture:non_flagship_channel" in audit["launch_truth_blockers"]
    assert "snapshot:channel_mismatch" in audit["launch_truth_blockers"]
    assert audit["release_label"] == "preview"


def test_flagship_wrapper_does_not_duplicate_channel_owned_release_posture(tmp_path: Path) -> None:
    snapshot_path = write_json(
        tmp_path / "snapshot.json",
        snapshot(
            channel="preview",
            version="build-2",
            generated_at="2026-01-03T00:02:00Z",
            ready=False,
        ),
    )
    channel_path = write_json(
        tmp_path / "channel.json",
        release_channel(
            channel="preview",
            version="build-2",
            generated_at="2026-01-03T00:00:00Z",
        ),
    )
    gate_path = write_json(
        tmp_path / "gate.json",
        readiness_gate(ready=False, generated_at="2026-01-03T00:01:00Z"),
    )

    audit = MODULE.build_audit(snapshot_path, channel_path, gate_path)

    assert audit["launch_truth_blockers"] == [
        "release_posture:non_flagship_channel",
        "release_posture:not_gold_supported",
        "release_posture:not_public_stable",
    ]
    assert audit["launch_truth_blocker_details"] == [
        "release channel channel is preview, not a flagship stable lane",
        "release channel supportability is not gold_supported",
        "release channel rollout is promoted_preview, not public_stable",
    ]
    gate = audit["flagship_product_readiness_gate"]
    assert gate["suppressed_duplicate_projection_count"] == 3
    assert [item["represented_by"] for item in gate["suppressed_duplicate_projections"]] == [
        "release_posture:non_flagship_channel",
        "release_posture:not_gold_supported",
        "release_posture:not_public_stable",
    ]


def test_flagship_release_posture_detail_remains_when_channel_does_not_own_cause(
    tmp_path: Path,
) -> None:
    snapshot_path = write_json(
        tmp_path / "snapshot.json",
        snapshot(
            channel="public_stable",
            version="build-2",
            generated_at="2026-01-03T00:02:00Z",
            ready=False,
        ),
    )
    channel_path = write_json(
        tmp_path / "channel.json",
        release_channel(
            channel="public_stable",
            version="build-2",
            generated_at="2026-01-03T00:00:00Z",
        ),
    )
    gate_payload = readiness_gate(ready=False, generated_at="2026-01-03T00:01:00Z")
    gate_payload["launch_critical_nested_blockers"] = [
        "release channel supportability is not gold_supported",
        "windows installer gold proof artifact is still missing: /proof.zip",
    ]
    gate_path = write_json(tmp_path / "gate.json", gate_payload)

    audit = MODULE.build_audit(snapshot_path, channel_path, gate_path)

    assert audit["launch_truth_blockers"] == [
        "flagship_readiness:blocker_1",
        "flagship_readiness:blocker_2",
    ]
    assert audit["launch_truth_blocker_details"] == [
        "release channel supportability is not gold_supported",
        "windows installer gold proof artifact is still missing: /proof.zip",
    ]
    assert audit["flagship_product_readiness_gate"]["suppressed_duplicate_projection_count"] == 0


def test_release_posture_projection_mapping_is_narrow_but_handles_wrapper_variants() -> None:
    assert (
        MODULE.release_posture_projection_cause("release channel channel is missing")
        == "release_posture:non_flagship_channel"
    )
    assert (
        MODULE.release_posture_projection_cause(
            "release channel rollout is blocking: public_release_review_required"
        )
        == "release_posture:not_public_stable"
    )
    assert MODULE.release_posture_projection_cause("release channel version is missing") is None
    assert (
        MODULE.release_posture_projection_cause(
            "windows installer gold proof artifact is still missing: /proof.zip"
        )
        is None
    )


def test_stale_pass_gate_fails_when_it_predates_current_channel(tmp_path: Path) -> None:
    snapshot_path = write_json(tmp_path / "snapshot.json", snapshot(channel="preview", version="new", generated_at="2026-01-03T00:01:00Z", ready=False))
    channel_path = write_json(tmp_path / "channel.json", release_channel(channel="preview", version="new", generated_at="2026-01-03T00:00:00Z"))
    gate_path = write_json(tmp_path / "gate.json", readiness_gate(ready=True, generated_at="2026-01-02T00:00:00Z"))

    audit = MODULE.build_audit(snapshot_path, channel_path, gate_path)

    assert audit["launch_ready_from_current_truth"] is False
    assert "freshness:flagship_gate_predates_channel" in audit["launch_truth_blockers"]


def test_flagship_coverage_gap_is_an_explicit_launch_truth_blocker(tmp_path: Path) -> None:
    snapshot_path = write_json(
        tmp_path / "snapshot.json",
        snapshot(
            channel="public_stable",
            version="build-2",
            generated_at="2026-01-03T00:02:00Z",
        ),
    )
    channel_path = write_json(
        tmp_path / "channel.json",
        release_channel(
            channel="public_stable",
            version="build-2",
            generated_at="2026-01-03T00:00:00Z",
        ),
    )
    gate_path = write_json(
        tmp_path / "gate.json",
        readiness_gate(
            ready=True,
            generated_at="2026-01-03T00:01:00Z",
            coverage_gap_keys=["desktop_client"],
        ),
    )

    audit = MODULE.build_audit(snapshot_path, channel_path, gate_path)

    assert audit["status"] == "fail"
    assert "flagship_readiness:coverage_gap_1" in audit["launch_truth_blockers"]
    assert "flagship readiness coverage gap remains: desktop_client" in audit["launch_truth_blocker_details"]
    assert audit["flagship_product_readiness_gate"]["coverage_gap_keys"] == ["desktop_client"]


def test_mandatory_supply_chain_and_observability_receipts_are_launch_truth(tmp_path: Path) -> None:
    snapshot_path = write_json(
        tmp_path / "snapshot.json",
        snapshot(
            channel="public_stable",
            version="build-2",
            generated_at="2026-01-03T00:04:00Z",
        ),
    )
    channel_path = write_json(
        tmp_path / "channel.json",
        release_channel(
            channel="public_stable",
            version="build-2",
            generated_at="2026-01-03T00:00:00Z",
        ),
    )
    gate_path = write_json(
        tmp_path / "gate.json",
        readiness_gate(ready=True, generated_at="2026-01-03T00:01:00Z"),
    )
    supply_chain_path = write_json(
        tmp_path / "supply-chain.json",
        {
            "contract_name": "chummer6.supply_chain_release_gate.v1",
            "generated_at_utc": "2026-01-03T00:02:00Z",
            "status": "fail",
            "verdict": "SUPPLY_CHAIN_BLOCKED",
            "blockers": ["provenance:not_available"],
        },
    )
    observability_path = write_json(
        tmp_path / "observability.json",
        {
            "contract_name": "chummer.public_edge_observability_release_gate.v1",
            "generated_at_utc": "2026-01-03T00:03:00Z",
            "status": "pass",
            "verdict": "OBSERVABILITY_RELEASE_READY",
            "failures": [],
        },
    )

    audit = MODULE.build_audit(
        snapshot_path,
        channel_path,
        gate_path,
        auxiliary_release_receipts={
            "supply_chain_evidence": supply_chain_path,
            "public_edge_observability_release": observability_path,
        },
    )
    document = MODULE.below_gold_markdown(audit)

    assert audit["status"] == "fail"
    assert audit["launch_ready_from_current_truth"] is False
    assert "supply_chain_evidence:blocker_1" in audit["launch_truth_blockers"]
    assert "provenance:not_available" in audit["launch_truth_blocker_details"]
    assert audit["auxiliary_release_gates"]["supply_chain_evidence"]["pass"] is False
    assert audit["auxiliary_release_gates"]["public_edge_observability_release"]["pass"] is True
    assert "provenance:not_available" in document
    assert str(supply_chain_path) in document
    assert str(observability_path) in document


def test_root_release_blockers_project_actionable_truth_without_meta_duplicates(tmp_path: Path) -> None:
    channel_path = write_json(
        tmp_path / "channel.json",
        release_channel(
            channel="public_stable",
            version="build-2",
            generated_at="2026-01-03T00:00:00Z",
        ),
    )
    gate_path = write_json(
        tmp_path / "gate.json",
        readiness_gate(ready=True, generated_at="2026-01-03T00:01:00Z"),
    )
    snapshot_path = write_json(
        tmp_path / "snapshot.json",
        snapshot(
            channel="public_stable",
            version="build-2",
            generated_at="2026-01-03T00:02:00Z",
        ),
    )
    release_blockers_path = write_json(
        tmp_path / "release-blockers.json",
        {
            "generated_at": "2026-01-03T00:03:00Z",
            "root_blockers": [
                {
                    "id": "release_posture:non_flagship_channel",
                    "failing_gate": "channel posture is already represented by the audit",
                },
                {
                    "id": "proof:user_journey_tester_audit",
                    "failing_gate": "user journey tester audit is not passing and fresh",
                },
                {
                    "id": "release_truth:public_edge_postdeploy_gate",
                    "failing_gate": "public edge runtime overlay does not match current source",
                },
                {
                    "id": "release_truth:release_ready",
                    "failing_gate": "release-ready is the aggregate receipt itself",
                },
                {
                    "id": "release_truth:windows_installer_visual_audit",
                    "failing_gate": "Windows evidence is represented by its owning gate",
                },
            ],
        },
    )

    audit = MODULE.build_audit(
        snapshot_path,
        channel_path,
        gate_path,
        release_blockers_path=release_blockers_path,
    )
    document = MODULE.below_gold_markdown(audit)

    assert audit["status"] == "fail"
    assert audit["release_blockers_projection"]["root_blockers"] == [
        {
            "id": "proof:user_journey_tester_audit",
            "detail": "user journey tester audit is not passing and fresh",
        },
        {
            "id": "release_truth:public_edge_postdeploy_gate",
            "detail": "public edge runtime overlay does not match current source",
        },
    ]
    assert "release_blockers_projection:proof:user_journey_tester_audit" in audit["launch_truth_blockers"]
    assert "release_blockers_projection:release_truth:public_edge_postdeploy_gate" in audit["launch_truth_blockers"]
    assert not any(
        blocker.endswith("release_posture:non_flagship_channel")
        or blocker.endswith("release_truth:release_ready")
        or blocker.endswith("release_truth:windows_installer_visual_audit")
        for blocker in audit["launch_truth_blockers"]
        if blocker.startswith("release_blockers_projection:")
    )
    assert "proof:user_journey_tester_audit: user journey tester audit is not passing and fresh" in document
    assert "release_truth:public_edge_postdeploy_gate: public edge runtime overlay does not match current source" in document
    assert str(release_blockers_path) in document


def test_matching_stable_sources_can_prove_launch_ready(tmp_path: Path) -> None:
    channel_path = write_json(tmp_path / "channel.json", release_channel(channel="public_stable", version="build-2", generated_at="2026-01-03T00:00:00Z"))
    gate_path = write_json(tmp_path / "gate.json", readiness_gate(ready=True, generated_at="2026-01-03T00:01:00Z"))
    snapshot_path = write_json(tmp_path / "snapshot.json", snapshot(channel="public_stable", version="build-2", generated_at="2026-01-03T00:02:00Z"))

    audit = MODULE.build_audit(snapshot_path, channel_path, gate_path)

    assert audit["status"] == "pass"
    assert audit["launch_ready_from_current_truth"] is True
    assert audit["final_gold_verdict"] == "GOLD_READY"
    assert audit["launch_truth_blockers"] == []


def test_missing_source_fails_closed_and_generated_doc_stays_truthful(tmp_path: Path) -> None:
    missing_snapshot = tmp_path / "missing.json"
    channel_path = write_json(tmp_path / "channel.json", release_channel(channel="preview", version="new", generated_at="2026-01-03T00:00:00Z"))
    gate_path = write_json(tmp_path / "gate.json", readiness_gate(ready=False, generated_at="2026-01-03T00:01:00Z"))

    audit = MODULE.build_audit(missing_snapshot, channel_path, gate_path)
    document = MODULE.below_gold_markdown(audit)

    assert audit["launch_ready_from_current_truth"] is False
    assert "source:public_release_snapshot_missing" in audit["launch_truth_blockers"]
    assert "not flagship-product-ready" in document
    assert "`preview`" in document
    assert "`public_stable`" in document


def test_materialized_published_audit_and_root_mirror_are_identical(tmp_path: Path) -> None:
    snapshot_path = write_json(tmp_path / "snapshot.json", snapshot(channel="public_stable", version="old", generated_at="2026-01-01T00:00:00Z"))
    channel_path = write_json(tmp_path / "channel.json", release_channel(channel="preview", version="new", generated_at="2026-01-03T00:00:00Z"))
    gate_path = write_json(tmp_path / "gate.json", readiness_gate(ready=False, generated_at="2026-01-03T00:01:00Z"))
    audit = MODULE.build_audit(snapshot_path, channel_path, gate_path)
    published_output = tmp_path / ".codex-studio" / "published" / "audit.json"
    root_mirror_output = tmp_path / "audit.json"
    below_gold_output = tmp_path / "WHAT_IS_STILL_BELOW_GOLD.md"

    MODULE.materialize_outputs(
        audit,
        output=published_output,
        root_mirror_output=root_mirror_output,
        below_gold_output=below_gold_output,
    )

    assert published_output.read_bytes() == root_mirror_output.read_bytes()
    assert json.loads(published_output.read_text(encoding="utf-8"))["launch_ready_from_current_truth"] is False
    assert "not flagship-product-ready" in below_gold_output.read_text(encoding="utf-8")


def test_default_published_audit_path_matches_release_ready_consumer() -> None:
    expected = MODULE.ROOT / ".codex-studio" / "published" / "PUBLIC_RELEASE_SNAPSHOT_READONLY_AUDIT.generated.json"

    assert MODULE.DEFAULT_OUTPUT == expected
    assert MODULE.DEFAULT_ROOT_MIRROR_OUTPUT == MODULE.ROOT / "PUBLIC_RELEASE_SNAPSHOT_READONLY_AUDIT.generated.json"
