#!/usr/bin/env python3
"""Materialize a fail-closed audit of the public release snapshot.

The snapshot is intentionally read-only.  Current launch truth comes from the
registry release channel and the whole-product flagship readiness gate.  This
materializer binds those sources by channel, version, and generation time so a
stale gold snapshot cannot remain launch-ready after the release posture moves
back to preview.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path("/docker/chummercomplete")
RUN_SERVICES_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SNAPSHOT = ROOT / ".codex-studio" / "published" / "PUBLIC_RELEASE_SNAPSHOT.generated.json"
DEFAULT_RELEASE_CHANNEL = ROOT / "chummer-hub-registry" / ".codex-studio" / "published" / "RELEASE_CHANNEL.generated.json"
DEFAULT_FLAGSHIP_GATE = RUN_SERVICES_ROOT / ".codex-studio" / "published" / "FLAGSHIP_PRODUCT_READINESS_GATE.generated.json"
DEFAULT_SUPPLY_CHAIN_GATE = ROOT / ".codex-studio" / "published" / "SUPPLY_CHAIN_RELEASE_GATE.generated.json"
DEFAULT_OBSERVABILITY_GATE = RUN_SERVICES_ROOT / ".codex-studio" / "published" / "PUBLIC_EDGE_OBSERVABILITY_RELEASE_GATE.generated.json"
DEFAULT_RELEASE_BLOCKERS = ROOT / "RELEASE_BLOCKERS.generated.json"
DEFAULT_AUXILIARY_RELEASE_RECEIPTS = {
    "supply_chain_evidence": DEFAULT_SUPPLY_CHAIN_GATE,
    "public_edge_observability_release": DEFAULT_OBSERVABILITY_GATE,
}
AUXILIARY_RELEASE_CONTRACTS = {
    "supply_chain_evidence": "chummer6.supply_chain_release_gate.v1",
    "public_edge_observability_release": "chummer.public_edge_observability_release_gate.v1",
}
DEFAULT_OUTPUT = ROOT / ".codex-studio" / "published" / "PUBLIC_RELEASE_SNAPSHOT_READONLY_AUDIT.generated.json"
DEFAULT_ROOT_MIRROR_OUTPUT = ROOT / "PUBLIC_RELEASE_SNAPSHOT_READONLY_AUDIT.generated.json"
DEFAULT_BELOW_GOLD_OUTPUT = ROOT / "chummer-hub-registry" / ".codex-design" / "product" / "WHAT_IS_STILL_BELOW_GOLD.md"

PASS_STATES = {"pass", "passed", "ready"}
STABLE_CHANNELS = {"public_stable", "stable", "docker"}
READY_VERDICT = "FLAGSHIP_PRODUCT_READY"
NOT_READY_VERDICT = "NOT_FLAGSHIP_PRODUCT_READY"


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalized(value: object) -> str:
    return str(value or "").strip().lower()


def normalized_strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        candidate = str(item or "").strip()
        if not candidate or candidate.casefold() in seen:
            continue
        seen.add(candidate.casefold())
        result.append(candidate)
    return result


def release_posture_projection_cause(detail: object) -> str | None:
    """Map wrapper prose to the authoritative release-channel cause it repeats.

    The flagship gate deliberately carries nested human-readable blockers.  A
    release-posture blocker can therefore arrive twice: once from the channel
    fields inspected by this audit and once through the flagship wrapper.  Keep
    this mapping deliberately narrow so adjacent launch blockers are never
    collapsed merely because their prose happens to look similar.
    """

    value = " ".join(str(detail or "").strip().casefold().split())
    if value == "release channel status is not published":
        return "release_posture:not_published"
    if (
        value.startswith("release channel channel is ")
        and value.endswith(", not a flagship stable lane")
    ) or value == "release channel channel is missing":
        return "release_posture:non_flagship_channel"
    if value == "release channel supportability is not gold_supported":
        return "release_posture:not_gold_supported"
    if (
        value.startswith("release channel rollout is ")
        and value.endswith(", not public_stable")
    ) or value.startswith("release channel rollout is blocking:"):
        return "release_posture:not_public_stable"
    return None


def load_json(path: Path) -> tuple[dict[str, Any], str]:
    if not path.is_file():
        return {}, "missing"
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}, "invalid"
    return (payload, "loaded") if isinstance(payload, dict) else ({}, "invalid")


def digest(path: Path) -> str | None:
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_timestamp(value: object) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def release_channel_identity(payload: dict[str, Any]) -> tuple[str, str, str, str, str]:
    return (
        str(payload.get("channel") or payload.get("channelId") or "").strip(),
        str(payload.get("version") or payload.get("releaseVersion") or "").strip(),
        normalized(payload.get("status")),
        normalized(payload.get("supportabilityState")),
        normalized(payload.get("rolloutState")),
    )


def snapshot_identity(payload: dict[str, Any]) -> tuple[str, str]:
    state = payload.get("release_channel_state")
    state = state if isinstance(state, dict) else {}
    channel = str(
        payload.get("channel")
        or payload.get("release_label")
        or state.get("channel_id")
        or ""
    ).strip()
    version = str(payload.get("build_id") or state.get("version") or "").strip()
    return channel, version


def add_finding(
    findings: list[dict[str, str]],
    blocker_ids: list[str],
    blocker_details: list[str],
    code: str,
    detail: str,
) -> None:
    if code in blocker_ids:
        return
    blocker_ids.append(code)
    blocker_details.append(detail)
    findings.append({"code": code, "severity": "blocker", "detail": detail})


def build_audit(
    snapshot_path: Path,
    release_channel_path: Path,
    flagship_gate_path: Path,
    *,
    generated_at_utc: str | None = None,
    auxiliary_release_receipts: dict[str, Path] | None = None,
    release_blockers_path: Path | None = None,
) -> dict[str, Any]:
    generated_at_utc = generated_at_utc or now_iso()
    snapshot, snapshot_load_status = load_json(snapshot_path)
    release_channel, release_channel_load_status = load_json(release_channel_path)
    flagship_gate, flagship_gate_load_status = load_json(flagship_gate_path)
    auxiliary_release_receipts = dict(
        DEFAULT_AUXILIARY_RELEASE_RECEIPTS
        if auxiliary_release_receipts is None
        else auxiliary_release_receipts
    )
    auxiliary_payloads = {
        gate: (*load_json(path), path)
        for gate, path in auxiliary_release_receipts.items()
    }
    release_blockers, release_blockers_load_status = (
        load_json(release_blockers_path)
        if release_blockers_path is not None
        else ({}, "not_configured")
    )

    findings: list[dict[str, str]] = []
    blocker_ids: list[str] = []
    blocker_details: list[str] = []

    for label, path, status in (
        ("public release snapshot", snapshot_path, snapshot_load_status),
        ("release channel", release_channel_path, release_channel_load_status),
        ("flagship readiness gate", flagship_gate_path, flagship_gate_load_status),
        *(
            (gate.replace("_", " "), path, load_status)
            for gate, (_payload, load_status, path) in auxiliary_payloads.items()
        ),
    ):
        if status != "loaded":
            add_finding(
                findings,
                blocker_ids,
                blocker_details,
                f"source:{label.replace(' ', '_')}_{status}",
                f"{label} is {status}: {path}",
            )
    if release_blockers_path is not None and release_blockers_load_status != "loaded":
        add_finding(
            findings,
            blocker_ids,
            blocker_details,
            f"source:release_blockers_{release_blockers_load_status}",
            f"release blockers projection is {release_blockers_load_status}: {release_blockers_path}",
        )

    channel, version, channel_status, supportability, rollout = release_channel_identity(release_channel)
    snapshot_channel, snapshot_version = snapshot_identity(snapshot)

    if release_channel_load_status == "loaded":
        if channel_status != "published":
            add_finding(findings, blocker_ids, blocker_details, "release_posture:not_published", "release channel status is not published")
        if normalized(channel) not in STABLE_CHANNELS:
            add_finding(
                findings,
                blocker_ids,
                blocker_details,
                "release_posture:non_flagship_channel",
                f"release channel channel is {channel or 'missing'}, not a flagship stable lane",
            )
        if supportability != "gold_supported":
            add_finding(findings, blocker_ids, blocker_details, "release_posture:not_gold_supported", "release channel supportability is not gold_supported")
        if rollout != "public_stable":
            add_finding(
                findings,
                blocker_ids,
                blocker_details,
                "release_posture:not_public_stable",
                f"release channel rollout is {rollout or 'missing'}, not public_stable",
            )

    gate_blockers = normalized_strings(flagship_gate.get("launch_critical_nested_blockers"))
    gate_coverage_gaps = normalized_strings(flagship_gate.get("coverage_gap_keys"))
    for coverage_gap in normalized_strings(flagship_gate.get("scoped_coverage_gap_keys")):
        if coverage_gap.casefold() not in {item.casefold() for item in gate_coverage_gaps}:
            gate_coverage_gaps.append(coverage_gap)
    gate_ready = (
        flagship_gate_load_status == "loaded"
        and normalized(flagship_gate.get("status")) in PASS_STATES
        and flagship_gate.get("pass") is True
        and str(flagship_gate.get("verdict") or "").strip() == READY_VERDICT
        and not gate_blockers
        and not gate_coverage_gaps
    )
    suppressed_duplicate_projections: list[dict[str, str]] = []
    if flagship_gate_load_status == "loaded" and not gate_ready:
        gate_findings_added = False
        if gate_blockers:
            unique_gate_blockers: list[str] = []
            for detail in gate_blockers:
                represented_by = release_posture_projection_cause(detail)
                if represented_by is not None and represented_by in blocker_ids:
                    suppressed_duplicate_projections.append(
                        {
                            "detail": detail,
                            "represented_by": represented_by,
                            "source": "launch_critical_nested_blockers",
                        }
                    )
                    gate_findings_added = True
                    continue
                unique_gate_blockers.append(detail)
            for index, detail in enumerate(unique_gate_blockers, start=1):
                add_finding(findings, blocker_ids, blocker_details, f"flagship_readiness:blocker_{index}", detail)
                gate_findings_added = True
        for index, coverage_gap in enumerate(gate_coverage_gaps, start=1):
            add_finding(
                findings,
                blocker_ids,
                blocker_details,
                f"flagship_readiness:coverage_gap_{index}",
                f"flagship readiness coverage gap remains: {coverage_gap}",
            )
            gate_findings_added = True
        if not gate_findings_added:
            reason = str(flagship_gate.get("reason") or "flagship readiness gate is not ready").strip()
            add_finding(findings, blocker_ids, blocker_details, "flagship_readiness:not_ready", reason)

    auxiliary_gate_states: dict[str, dict[str, Any]] = {}
    for gate, (payload, load_status, path) in auxiliary_payloads.items():
        expected_contract = AUXILIARY_RELEASE_CONTRACTS.get(gate, "")
        contract_name = str(payload.get("contract_name") or payload.get("contractName") or "").strip()
        reasons = normalized_strings(payload.get("failures"))
        for blocker in normalized_strings(payload.get("blockers")):
            if blocker.casefold() not in {item.casefold() for item in reasons}:
                reasons.append(blocker)
        contract_matches = bool(expected_contract and contract_name == expected_contract)
        gate_pass = (
            load_status == "loaded"
            and contract_matches
            and normalized(payload.get("status")) in PASS_STATES
            and not reasons
        )
        if load_status == "loaded" and not contract_matches:
            add_finding(
                findings,
                blocker_ids,
                blocker_details,
                f"{gate}:contract_mismatch",
                f"{gate.replace('_', ' ')} contract is not {expected_contract}",
            )
        if load_status == "loaded" and not gate_pass:
            if reasons:
                for index, detail in enumerate(reasons, start=1):
                    add_finding(
                        findings,
                        blocker_ids,
                        blocker_details,
                        f"{gate}:blocker_{index}",
                        detail,
                    )
            elif contract_matches:
                verdict = str(payload.get("verdict") or "").strip()
                detail = f"{gate.replace('_', ' ')} is not pass"
                if verdict:
                    detail = f"{detail}: {verdict}"
                add_finding(
                    findings,
                    blocker_ids,
                    blocker_details,
                    f"{gate}:not_ready",
                    detail,
                )
        auxiliary_gate_states[gate] = {
            "path": str(path),
            "load_status": load_status,
            "sha256": digest(path),
            "contract_name": contract_name or None,
            "status": payload.get("status"),
            "verdict": payload.get("verdict"),
            "pass": gate_pass,
            "generated_at_utc": payload.get("generated_at_utc") or payload.get("generatedAt"),
            "reasons": reasons,
        }

    release_blocker_entries = release_blockers.get("root_blockers")
    if not isinstance(release_blocker_entries, list):
        release_blocker_entries = release_blockers.get("blockers")
    release_blocker_entries = release_blocker_entries if isinstance(release_blocker_entries, list) else []
    ignored_projection_blockers = {
        "release_posture:non_flagship_channel",
        "release_truth:release_ready",
        "release_truth:windows_installer_visual_audit",
    }
    projected_root_blockers: list[dict[str, str]] = []
    for entry in release_blocker_entries:
        if not isinstance(entry, dict):
            continue
        blocker_id = str(entry.get("id") or entry.get("blocker_id") or "").strip()
        if not blocker_id or blocker_id in ignored_projection_blockers:
            continue
        detail = str(
            entry.get("failing_gate")
            or entry.get("external_prerequisite")
            or "root release blocker remains"
        ).strip()
        projected_root_blockers.append({"id": blocker_id, "detail": detail})
        add_finding(
            findings,
            blocker_ids,
            blocker_details,
            f"release_blockers_projection:{blocker_id}",
            f"{blocker_id}: {detail}",
        )

    channel_generated_at = parse_timestamp(
        release_channel.get("generated_at")
        or release_channel.get("generatedAt")
        or release_channel.get("publishedAt")
    )
    gate_generated_at = parse_timestamp(
        flagship_gate.get("generated_at_utc")
        or flagship_gate.get("generated_at")
        or flagship_gate.get("generatedAt")
    )
    snapshot_generated_at = parse_timestamp(
        snapshot.get("generated_at")
        or snapshot.get("snapshot_generated_at")
        or snapshot.get("published_at")
    )
    if channel_generated_at is not None:
        if gate_generated_at is None or gate_generated_at < channel_generated_at:
            add_finding(
                findings,
                blocker_ids,
                blocker_details,
                "freshness:flagship_gate_predates_channel",
                "flagship readiness gate is missing a current observation of the release channel",
            )
        if snapshot_generated_at is None or snapshot_generated_at < channel_generated_at:
            add_finding(
                findings,
                blocker_ids,
                blocker_details,
                "freshness:snapshot_predates_channel",
                "public release snapshot predates the current release channel",
            )
        for gate, state in auxiliary_gate_states.items():
            if state.get("load_status") != "loaded":
                continue
            observed_at = parse_timestamp(state.get("generated_at_utc"))
            if observed_at is None or observed_at < channel_generated_at:
                add_finding(
                    findings,
                    blocker_ids,
                    blocker_details,
                    f"freshness:{gate}_predates_channel",
                    f"{gate.replace('_', ' ')} is missing a current observation of the release channel",
                )
        if release_blockers_path is not None and release_blockers_load_status == "loaded":
            release_blockers_generated_at = parse_timestamp(
                release_blockers.get("generated_at")
                or release_blockers.get("generated_at_utc")
            )
            if release_blockers_generated_at is None or release_blockers_generated_at < channel_generated_at:
                add_finding(
                    findings,
                    blocker_ids,
                    blocker_details,
                    "freshness:release_blockers_predates_channel",
                    "release blockers projection is missing a current observation of the release channel",
                )

    if snapshot_load_status == "loaded" and release_channel_load_status == "loaded":
        if normalized(snapshot_channel) != normalized(channel):
            add_finding(
                findings,
                blocker_ids,
                blocker_details,
                "snapshot:channel_mismatch",
                f"snapshot channel {snapshot_channel or 'missing'} does not match current channel {channel or 'missing'}",
            )
        if snapshot_version != version:
            add_finding(
                findings,
                blocker_ids,
                blocker_details,
                "snapshot:version_mismatch",
                f"snapshot version {snapshot_version or 'missing'} does not match current version {version or 'missing'}",
            )

    launch_ready = not blocker_ids and gate_ready
    snapshot_claims_launch_ready = bool(
        snapshot.get("launch_ready_from_current_truth")
        or snapshot.get("release_channel_state", {}).get("flagship_release_posture")
        if isinstance(snapshot.get("release_channel_state"), dict)
        else snapshot.get("launch_ready_from_current_truth")
    )
    if snapshot_claims_launch_ready and not launch_ready:
        findings.append(
            {
                "code": "snapshot:stale_launch_ready_claim",
                "severity": "blocker",
                "detail": "snapshot launch-ready claim is overridden by current authoritative truth",
            }
        )
        if "snapshot:stale_launch_ready_claim" not in blocker_ids:
            blocker_ids.append("snapshot:stale_launch_ready_claim")
            blocker_details.append("snapshot launch-ready claim is overridden by current authoritative truth")
        launch_ready = False

    status = "pass" if launch_ready else "fail"
    gate_verdict = str(flagship_gate.get("verdict") or NOT_READY_VERDICT).strip()
    if not gate_ready:
        gate_verdict = NOT_READY_VERDICT
    release_id = f"{channel}:{version}" if channel and version else None
    return {
        "contract_name": "chummer.public_release_snapshot_readonly_audit",
        "generated_at_utc": generated_at_utc,
        "status": status,
        "verdict": "SNAPSHOT_CONSISTENT_LAUNCH_READY" if launch_ready else "SNAPSHOT_NOT_LAUNCH_READY_FROM_CURRENT_TRUTH",
        "consistency_status": status,
        "summary": (
            "Snapshot is bound to the current flagship-ready release truth."
            if launch_ready
            else "Snapshot is not launch-ready from current truth; stale or contradictory gold claims are fail-closed."
        ),
        "launch_ready_from_current_truth": launch_ready,
        "release_ready_status": status,
        "release_ready_verdict": "RELEASE_READY" if launch_ready else "NOT_RELEASE_READY",
        "final_gold_status": "pass" if gate_ready else "fail",
        "final_gold_verdict": "GOLD_READY" if gate_ready else "NOT_GOLD",
        "flagship_product_readiness_status": "pass" if gate_ready else "fail",
        "flagship_product_readiness_verdict": gate_verdict,
        "blocker_count": len(blocker_ids),
        "launch_truth_blocker_count": len(blocker_ids),
        "launch_truth_blockers": blocker_ids,
        "launch_truth_blocker_details": blocker_details,
        "findings": findings,
        "release_id": release_id,
        "release_label": channel or None,
        "build_id": version or None,
        "snapshot_path": str(snapshot_path),
        "snapshot_generated_at": snapshot.get("generated_at") or snapshot.get("snapshot_generated_at"),
        "current_release_channel": {
            "path": str(release_channel_path),
            "load_status": release_channel_load_status,
            "sha256": digest(release_channel_path),
            "channel": channel or None,
            "version": version or None,
            "status": channel_status or None,
            "supportability_state": supportability or None,
            "rollout_state": rollout or None,
            "generated_at": release_channel.get("generated_at") or release_channel.get("generatedAt"),
        },
        "flagship_product_readiness_gate": {
            "path": str(flagship_gate_path),
            "load_status": flagship_gate_load_status,
            "sha256": digest(flagship_gate_path),
            "status": flagship_gate.get("status"),
            "verdict": gate_verdict,
            "pass": gate_ready,
            "generated_at_utc": flagship_gate.get("generated_at_utc"),
            "coverage_gap_keys": gate_coverage_gaps,
            "suppressed_duplicate_projection_count": len(suppressed_duplicate_projections),
            "suppressed_duplicate_projections": suppressed_duplicate_projections,
        },
        "auxiliary_release_gates": auxiliary_gate_states,
        "release_blockers_projection": {
            "path": str(release_blockers_path) if release_blockers_path is not None else None,
            "load_status": release_blockers_load_status,
            "sha256": digest(release_blockers_path) if release_blockers_path is not None else None,
            "generated_at": release_blockers.get("generated_at") or release_blockers.get("generated_at_utc"),
            "root_blockers": projected_root_blockers,
        },
        "source_load_status": {
            "snapshot": snapshot_load_status,
            "release_channel": release_channel_load_status,
            "flagship_product_readiness_gate": flagship_gate_load_status,
            **{
                gate: load_status
                for gate, (_payload, load_status, _path) in auxiliary_payloads.items()
            },
            **(
                {"release_blockers": release_blockers_load_status}
                if release_blockers_path is not None
                else {}
            ),
        },
    }


def below_gold_markdown(audit: dict[str, Any]) -> str:
    channel = audit.get("current_release_channel")
    channel = channel if isinstance(channel, dict) else {}
    blockers = normalized_strings(audit.get("launch_truth_blocker_details"))
    generated_at = str(audit.get("generated_at_utc") or "unknown")
    lines = [
        "# What Is Still Below Gold",
        "",
        f"Launch truth observed: {generated_at}",
        "",
        "This document is generated from the current release channel, the authoritative whole-product flagship readiness gate, and mandatory release evidence gates. Do not edit it independently of those sources.",
        "",
        "## Current whole-product posture",
        "",
    ]
    if audit.get("launch_ready_from_current_truth") is True:
        lines.append("The current release is flagship-ready and its snapshot is bound to the same channel and version.")
    else:
        lines.extend(
            [
                "The current release is **not flagship-product-ready**. Preview support is real, but it is not a public-stable or gold-supported launch claim.",
                "",
                f"- Channel: `{channel.get('channel') or 'missing'}`",
                f"- Version: `{channel.get('version') or 'missing'}`",
                f"- Rollout: `{channel.get('rollout_state') or 'missing'}`",
                f"- Supportability: `{channel.get('supportability_state') or 'missing'}`",
                f"- Authoritative verdict: `{audit.get('flagship_product_readiness_verdict') or NOT_READY_VERDICT}`",
                "",
                "### Launch blockers",
                "",
            ]
        )
        lines.extend(f"- {blocker}" for blocker in blockers)
    lines.extend(
        [
            "",
            "## Gold-claim boundary",
            "",
            "Do not describe the current lane as `public_stable`, `gold_supported`, `GOLD_READY`, or launch-ready unless the registry channel, the flagship readiness gate, and the public release snapshot all agree on the same current channel and version.",
            "",
            "Flagship parity-family evidence remains useful, but it cannot override a whole-product launch blocker or promote a preview channel.",
            "",
            "## Authoritative sources",
            "",
            f"- Release channel: `{channel.get('path') or DEFAULT_RELEASE_CHANNEL}`",
            f"- Flagship readiness gate: `{audit.get('flagship_product_readiness_gate', {}).get('path') or DEFAULT_FLAGSHIP_GATE}`",
            f"- Supply-chain release gate: `{audit.get('auxiliary_release_gates', {}).get('supply_chain_evidence', {}).get('path') or DEFAULT_SUPPLY_CHAIN_GATE}`",
            f"- Public-edge observability gate: `{audit.get('auxiliary_release_gates', {}).get('public_edge_observability_release', {}).get('path') or DEFAULT_OBSERVABILITY_GATE}`",
            f"- Release blockers projection: `{audit.get('release_blockers_projection', {}).get('path') or DEFAULT_RELEASE_BLOCKERS}`",
            f"- Read-only snapshot audit: `{DEFAULT_OUTPUT}`",
            "",
        ]
    )
    return "\n".join(lines)


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def materialize_outputs(
    audit: dict[str, Any],
    *,
    output: Path,
    root_mirror_output: Path | None,
    below_gold_output: Path | None,
) -> None:
    rendered = json.dumps(audit, indent=2) + "\n"
    atomic_write(output, rendered)
    if root_mirror_output is not None and root_mirror_output.resolve() != output.resolve():
        atomic_write(root_mirror_output, rendered)
    if below_gold_output is not None:
        atomic_write(below_gold_output, below_gold_markdown(audit))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
    parser.add_argument("--release-channel", type=Path, default=DEFAULT_RELEASE_CHANNEL)
    parser.add_argument("--flagship-readiness-gate", type=Path, default=DEFAULT_FLAGSHIP_GATE)
    parser.add_argument("--supply-chain-gate", type=Path, default=DEFAULT_SUPPLY_CHAIN_GATE)
    parser.add_argument("--observability-gate", type=Path, default=DEFAULT_OBSERVABILITY_GATE)
    parser.add_argument("--release-blockers", type=Path, default=DEFAULT_RELEASE_BLOCKERS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--root-mirror-output", type=Path)
    parser.add_argument("--skip-root-mirror", action="store_true")
    parser.add_argument("--below-gold-output", type=Path, default=DEFAULT_BELOW_GOLD_OUTPUT)
    parser.add_argument("--skip-below-gold", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    audit = build_audit(
        args.snapshot,
        args.release_channel,
        args.flagship_readiness_gate,
        auxiliary_release_receipts={
            "supply_chain_evidence": args.supply_chain_gate,
            "public_edge_observability_release": args.observability_gate,
        },
        release_blockers_path=args.release_blockers,
    )
    root_mirror_output = args.root_mirror_output
    if root_mirror_output is None and args.output == DEFAULT_OUTPUT and not args.skip_root_mirror:
        root_mirror_output = DEFAULT_ROOT_MIRROR_OUTPUT
    materialize_outputs(
        audit,
        output=args.output,
        root_mirror_output=root_mirror_output,
        below_gold_output=None if args.skip_below_gold else args.below_gold_output,
    )
    print(f"public_release_snapshot_readonly_audit:{audit['status']}")
    return 0 if audit["launch_ready_from_current_truth"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
