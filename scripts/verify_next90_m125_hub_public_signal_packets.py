#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml


PACKAGE_ID = "next90-m125-hub-build-public-feedback-roadmap-changelog-support-and-sign"
WORK_TASK_ID = "125.1"
FRONTIER_ID = 4030850391
MILESTONE_ID = 125
PACKAGE_TITLE = "Build public feedback, roadmap, changelog, support, and signal-intake surfaces that emit governed SignalToCanon packets."
PACKAGE_TASK = PACKAGE_TITLE
PACKAGE_REPO = "chummer6-hub"
PACKAGE_WAVE = "W17"
PACKAGE_STATUS = "not_started"
ALLOWED_PATHS = ["Chummer.Run.Api", "scripts", "tests"]
OWNED_SURFACES = ["build_public_feedback_roadmap_changelog:hub"]
PROOF_KIND = "source_digest_and_executed_test_contract"
STATUS_SCOPE = "executed_public_signal_packet_capability"
TEST_FQN = (
    "Chummer.Tests.PublicSignalToCanonPacketServiceTests."
    "PublicSignalPacketsCoverFeedbackRoadmapChangelogSupportAndSignalIntake"
)
TEST_COMMAND = [
    "dotnet",
    "test",
    "Chummer.Tests/Chummer.Tests.csproj",
    "--filter",
    f"FullyQualifiedName={TEST_FQN}",
    "--no-restore",
    "--nologo",
    "--logger",
    "console;verbosity=normal",
]
VERIFICATION_COMMAND = (
    "python3 /docker/chummercomplete/chummer.run-services/scripts/"
    "verify_next90_m125_hub_public_signal_packets.py"
)
EVIDENCE_SOURCE_FILES = [
    "Chummer.Run.Api/Contracts/SignalToCanonPacketContracts.cs",
    "Chummer.Run.Api/Services/Support/PublicSignalToCanonPacketService.cs",
    "Chummer.Run.Api/ServiceCollectionBoundedContextExtensions.cs",
    "Chummer.Tests/PublicSignalToCanonPacketServiceTests.cs",
    "tests/RunServicesSmoke/Program.cs",
    "scripts/materialize_next90_m125_hub_public_signal_packets_proof.py",
    "scripts/verify_next90_m125_hub_public_signal_packets.py",
]
MAX_FUTURE_SKEW_SECONDS = 300
FORBIDDEN_PROOF_MARKERS = [
    "TASK_LOCAL_TELEMETRY",
    "ACTIVE_RUN_HANDOFF",
    "/var/lib/codex-fleet",
    "supervisor status",
    "task-local telemetry",
]

SOURCE_MARKERS = {
    "Chummer.Run.Api/Contracts/SignalToCanonPacketContracts.cs": [
        "public sealed record SignalToCanonPacketBundle(",
        "public sealed record SignalToCanonPacketProjection(",
    ],
    "Chummer.Run.Api/Services/Support/PublicSignalToCanonPacketService.cs": [
        "public sealed class PublicSignalToCanonPacketService",
        'Route: "/participate"',
        'DestinationRoute: "/participate"',
        'Route: "/roadmap"',
        'DestinationRoute: "/horizons?source=roadmap#public-roadmap-projection"',
        'Route: "/changelog"',
        'DestinationRoute: "/now?source=changelog#public-shipped-closeout"',
        'Route: "/contact"',
        'Route: "/participate"',
    ],
    "Chummer.Run.Api/ServiceCollectionBoundedContextExtensions.cs": [
        "services.AddSingleton<PublicSignalToCanonPacketService>();",
    ],
    "Chummer.Tests/PublicSignalToCanonPacketServiceTests.cs": [
        "public void PublicSignalPacketsCoverFeedbackRoadmapChangelogSupportAndSignalIntake()",
        'Assert.Contains(bundle.Packets, item => string.Equals(item.SurfaceId, "feedback", StringComparison.Ordinal)',
        'Assert.Contains(bundle.Packets, item => string.Equals(item.SurfaceId, "signal_intake", StringComparison.Ordinal)',
    ],
    "tests/RunServicesSmoke/Program.cs": [
        "var publicSignalPackets = new PublicSignalToCanonPacketService(releases);",
        'var publicSignalPacketBundle = publicSignalPackets.Build(supportCase, "en-US");',
        'campaign spine public signal packets should emit feedback packets for the public Participate surface.',
        'campaign spine public signal packets should emit governed signal-intake packets for the shared participate surface.',
    ],
    "scripts/materialize_next90_m125_hub_public_signal_packets_proof.py": [
        '"package_id": "next90-m125-hub-build-public-feedback-roadmap-changelog-support-and-sign"',
        '"frontier_id": 4030850391',
        '"owned_surfaces": ["build_public_feedback_roadmap_changelog:hub"]',
    ],
    "scripts/verify_next90_m125_hub_public_signal_packets.py": [
        f'PACKAGE_ID = "{PACKAGE_ID}"',
        f'WORK_TASK_ID = "{WORK_TASK_ID}"',
        f"FRONTIER_ID = {FRONTIER_ID}",
        'print("next90 m125 hub public signal packets proof passed")',
    ],
    "scripts/ai/verify.sh": [
        "python3 scripts/materialize_next90_m125_hub_public_signal_packets_proof.py",
        "python3 scripts/verify_next90_m125_hub_public_signal_packets.py",
        "python3 -m unittest tests/test_next90_m125_hub_public_signal_packets.py",
    ],
}

DEFAULT_ROOT = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get("CHUMMER_NEXT90_M125_ROOT", DEFAULT_ROOT))
FLEET_QUEUE_STAGING_PATH = Path(os.environ.get("CHUMMER_NEXT90_M125_QUEUE_STAGING", "/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml"))
DESIGN_QUEUE_STAGING_PATH = Path(os.environ.get("CHUMMER_NEXT90_M125_DESIGN_QUEUE_STAGING", "/docker/chummercomplete/chummer-design-m114/products/chummer/NEXT_90_DAY_QUEUE_STAGING.generated.yaml"))
PROOF_PATH = Path(
    os.environ.get(
        "CHUMMER_NEXT90_M125_OUT",
        ROOT / ".codex-studio" / "published" / "NEXT90_M125_HUB_PUBLIC_SIGNAL_PACKETS.generated.json",
    )
)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _file_evidence(path: Path, *, display_path: str) -> dict[str, object]:
    content = path.read_bytes()
    return {
        "path": display_path,
        "sha256": _sha256_bytes(content),
        "size_bytes": len(content),
    }


def _source_evidence() -> list[dict[str, object]]:
    return [
        _file_evidence(ROOT / relative_path, display_path=relative_path)
        for relative_path in EVIDENCE_SOURCE_FILES
    ]


def _queue_evidence() -> list[dict[str, object]]:
    return [
        _file_evidence(path, display_path=str(path))
        for path in (FLEET_QUEUE_STAGING_PATH, DESIGN_QUEUE_STAGING_PATH)
    ]


def _evidence_set_sha256(rows: list[dict[str, object]]) -> str:
    canonical = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return _sha256_bytes(canonical)


def _parse_timestamp(value: object) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _expected_package_proof() -> dict[str, object]:
    return {
        "package_id": PACKAGE_ID,
        "work_task_id": WORK_TASK_ID,
        "milestone_id": MILESTONE_ID,
        "frontier_id": FRONTIER_ID,
        "repo": PACKAGE_REPO,
        "status": PACKAGE_STATUS,
        "wave": PACKAGE_WAVE,
        "task": PACKAGE_TASK,
        "title": PACKAGE_TITLE,
        "allowed_paths": ALLOWED_PATHS,
        "owned_surfaces": OWNED_SURFACES,
    }


def _proof_validation_issues(
    payload: object,
    *,
    materialization_started_at: datetime,
    expected_source_evidence: list[dict[str, object]],
    expected_queue_evidence: list[dict[str, object]],
) -> list[str]:
    issues: list[str] = []
    if not isinstance(payload, dict):
        return ["proof payload must be a JSON object"]
    if payload.get("contract_name") != "chummer6-hub.next90_m125_hub_public_signal_packets":
        issues.append("proof file contract_name drifted")
    if payload.get("schema_version") != 2:
        issues.append("proof file schema_version must be 2")
    if payload.get("status") != "passed":
        issues.append("proof file status must be passed")
    if payload.get("status_scope") != STATUS_SCOPE:
        issues.append(f"proof file status_scope must be {STATUS_SCOPE}")
    if payload.get("proof_kind") != PROOF_KIND:
        issues.append(f"proof file proof_kind must be {PROOF_KIND}")
    if payload.get("verification_command") != VERIFICATION_COMMAND:
        issues.append("proof file verification_command drifted")
    if payload.get("package_proof") != _expected_package_proof():
        issues.append("proof file package identity drifted")
    if payload.get("package_workflow_status") != PACKAGE_STATUS:
        issues.append(f"proof file package_workflow_status must be {PACKAGE_STATUS}")
    if payload.get("package_workflow_status_affects_capability_status") is not False:
        issues.append("proof file must state that workflow status does not redefine capability test status")

    generated_at = _parse_timestamp(payload.get("generated_at"))
    now = datetime.now(timezone.utc)
    if generated_at is None:
        issues.append("proof file generated_at must be an offset-aware ISO timestamp")
    else:
        if generated_at < materialization_started_at - timedelta(seconds=2):
            issues.append("proof file generated_at predates the current materializer run")
        if generated_at > now + timedelta(seconds=MAX_FUTURE_SKEW_SECONDS):
            issues.append("proof file generated_at is unacceptably future-dated")

    if payload.get("source_evidence") != expected_source_evidence:
        issues.append("proof file source evidence does not bind the current exact source bytes")
    if payload.get("source_evidence_set_sha256") != _evidence_set_sha256(expected_source_evidence):
        issues.append("proof file source evidence set digest drifted")
    if payload.get("queue_evidence") != expected_queue_evidence:
        issues.append("proof file queue evidence does not bind both current queue snapshots")
    if payload.get("queue_evidence_set_sha256") != _evidence_set_sha256(expected_queue_evidence):
        issues.append("proof file queue evidence set digest drifted")

    release_binding = payload.get("release_binding")
    if not isinstance(release_binding, dict):
        issues.append("proof file release_binding must be an object")
    elif (
        release_binding.get("scope") != "release_independent_product_capability"
        or release_binding.get("release_artifact_specific") is not False
    ):
        issues.append("proof file must honestly declare release-independent capability scope")

    receipt = payload.get("test_receipt")
    if not isinstance(receipt, dict):
        issues.append("proof file test_receipt must be an object")
    else:
        if receipt.get("status") != "passed" or receipt.get("exit_code") != 0:
            issues.append("proof file test receipt must record a passing zero-exit test")
        if receipt.get("command") != TEST_COMMAND:
            issues.append("proof file test receipt command drifted")
        if receipt.get("fully_qualified_name") != TEST_FQN:
            issues.append("proof file test receipt fully-qualified name drifted")
        if not isinstance(receipt.get("executed_test_count"), int) or receipt.get("executed_test_count", 0) < 1:
            issues.append("proof file test receipt must record at least one executed focused test")
        output_sha256 = str(receipt.get("output_sha256") or "")
        if len(output_sha256) != 64 or any(char not in "0123456789abcdef" for char in output_sha256):
            issues.append("proof file test receipt output_sha256 must be lowercase SHA-256")
        if receipt.get("executed_at") != payload.get("generated_at"):
            issues.append("proof file test receipt executed_at must equal generated_at")
    return issues


def read_text(relative_path: str) -> str:
    path = ROOT / relative_path
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise SystemExit(f"missing required source file: {path}") from exc


def load_yaml(path: Path) -> object:
    text = path.read_text(encoding="utf-8")
    return yaml.safe_load(text)


def load_queue_staging_yaml(path: Path) -> object:
    text = path.read_text(encoding="utf-8")
    try:
        payload = yaml.safe_load(text)
    except yaml.YAMLError:
        payload = None
    else:
        if isinstance(payload, dict) and isinstance(payload.get("items"), list):
            return payload

    package_marker = f"package_id: {PACKAGE_ID}"
    package_index = text.find(package_marker)
    if package_index < 0:
        raise ValueError(f"queue staging is missing package_id {PACKAGE_ID}")

    start = text.rfind("\n- title:", 0, package_index)
    if start < 0:
        if not text.startswith("- title:"):
            raise ValueError(f"queue staging is missing the item block for {PACKAGE_ID}")
        start = 0
    else:
        start += 1

    end = text.find("\n- title:", package_index)
    if end < 0:
        end = len(text)

    block = text[start:end].rstrip() + "\n"
    payload = yaml.safe_load(block)
    if not isinstance(payload, list) or len(payload) != 1 or not isinstance(payload[0], dict):
        raise ValueError(f"queue staging package block for {PACKAGE_ID} must parse to exactly one item")
    return {"items": payload}


def verify_queue(path: Path, missing: list[str]) -> None:
    if not path.is_file():
        missing.append(f"missing queue staging file: {path}")
        return
    try:
        payload = load_queue_staging_yaml(path) or {}
    except (ValueError, yaml.YAMLError) as exc:
        missing.append(f"{path}: unable to load queue staging for {PACKAGE_ID}: {exc}")
        return
    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        missing.append(f"{path}: items is missing")
        return
    matches = [item for item in items if isinstance(item, dict) and item.get("package_id") == PACKAGE_ID]
    if len(matches) != 1:
        missing.append(f"{path}: expected exactly one {PACKAGE_ID} row, found {len(matches)}")
        return
    item = matches[0]
    expected = {
        "title": PACKAGE_TITLE,
        "task": PACKAGE_TASK,
        "repo": PACKAGE_REPO,
        "milestone_id": MILESTONE_ID,
        "work_task_id": WORK_TASK_ID,
        "frontier_id": FRONTIER_ID,
        "wave": PACKAGE_WAVE,
        "status": PACKAGE_STATUS,
        "allowed_paths": ALLOWED_PATHS,
        "owned_surfaces": OWNED_SURFACES,
    }
    for key, value in expected.items():
        if item.get(key) != value:
            missing.append(f"{path}: {PACKAGE_ID} {key} must be {value!r}")


def main() -> int:
    missing: list[str] = []
    verify_queue(FLEET_QUEUE_STAGING_PATH, missing)
    verify_queue(DESIGN_QUEUE_STAGING_PATH, missing)

    for relative_path, markers in SOURCE_MARKERS.items():
        text = read_text(relative_path)
        for marker in markers:
            if marker not in text:
                missing.append(f"{relative_path}: missing marker {marker}")
        if relative_path != "scripts/verify_next90_m125_hub_public_signal_packets.py":
            for forbidden in FORBIDDEN_PROOF_MARKERS:
                if forbidden in text:
                    missing.append(f"{relative_path}: forbidden marker {forbidden}")

    if missing:
        for item in missing:
            print(item, file=sys.stderr)
        return 1

    try:
        source_evidence_before = _source_evidence()
        queue_evidence_before = _queue_evidence()
    except OSError as exc:
        print(f"unable to snapshot M125 proof inputs: {exc}", file=sys.stderr)
        return 1

    prior_fingerprint: tuple[int, int, str] | None = None
    if PROOF_PATH.is_file() and not PROOF_PATH.is_symlink():
        prior_stat = PROOF_PATH.stat()
        prior_fingerprint = (prior_stat.st_mtime_ns, prior_stat.st_size, _sha256_file(PROOF_PATH))

    materializer = ROOT / "scripts" / "materialize_next90_m125_hub_public_signal_packets_proof.py"
    materialization_started_at = datetime.now(timezone.utc)
    try:
        result = subprocess.run(
            [sys.executable, str(materializer)],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=360,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        print(f"M125 proof materializer timed out: {exc}", file=sys.stderr)
        return 1
    if result.returncode != 0:
        missing.append(result.stderr.strip() or result.stdout.strip() or "materializer failed")
    elif not PROOF_PATH.is_file() or PROOF_PATH.is_symlink():
        missing.append(f"proof file was not written: {PROOF_PATH}")
    else:
        current_stat = PROOF_PATH.stat()
        current_fingerprint = (current_stat.st_mtime_ns, current_stat.st_size, _sha256_file(PROOF_PATH))
        if prior_fingerprint is not None and current_fingerprint == prior_fingerprint:
            missing.append("materializer did not replace the pre-existing proof bytes or file timestamp")
        try:
            source_evidence_after = _source_evidence()
            queue_evidence_after = _queue_evidence()
        except OSError as exc:
            missing.append(f"unable to re-snapshot M125 proof inputs: {exc}")
        else:
            if source_evidence_after != source_evidence_before:
                missing.append("M125 source bytes changed during proof materialization")
            if queue_evidence_after != queue_evidence_before:
                missing.append("M125 queue bytes changed during proof materialization")
            try:
                payload = json.loads(PROOF_PATH.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                missing.append(f"proof file is not readable valid JSON: {exc}")
            else:
                missing.extend(
                    _proof_validation_issues(
                        payload,
                        materialization_started_at=materialization_started_at,
                        expected_source_evidence=source_evidence_after,
                        expected_queue_evidence=queue_evidence_after,
                    )
                )

    if missing:
        for item in missing:
            print(item, file=sys.stderr)
        return 1

    print("next90 m125 hub public signal packets proof passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
