#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


PACKAGE_PROOF = {
    "package_id": "next90-m125-hub-build-public-feedback-roadmap-changelog-support-and-sign",
    "work_task_id": "125.1",
    "milestone_id": 125,
    "frontier_id": 4030850391,
    "repo": "chummer6-hub",
    "status": "not_started",
    "wave": "W17",
    "task": "Build public feedback, roadmap, changelog, support, and signal-intake surfaces that emit governed SignalToCanon packets.",
    "title": "Build public feedback, roadmap, changelog, support, and signal-intake surfaces that emit governed SignalToCanon packets.",
    "allowed_paths": ["Chummer.Run.Api", "scripts", "tests"],
    "owned_surfaces": ["build_public_feedback_roadmap_changelog:hub"],
}

REQUIRED_MARKERS = [
    "var publicSignalPackets = new PublicSignalToCanonPacketService(releases);",
    "var publicSignalPacketBundle = publicSignalPackets.Build(supportCase, \"en-US\");",
    'campaign spine public signal packets should emit feedback packets for the public Participate surface.',
    'campaign spine public signal packets should emit governed roadmap packets for the public horizons projection.',
    'campaign spine public signal packets should emit governed changelog packets for shipped closeout posture.',
    'campaign spine public signal packets should emit governed support packets from the first-party contact intake lane.',
    'campaign spine public signal packets should emit governed signal-intake packets for the shared participate surface.',
]

TEST_FQN = (
    "Chummer.Tests.PublicSignalToCanonPacketServiceTests."
    "PublicSignalPacketsCoverFeedbackRoadmapChangelogSupportAndSignalIntake"
)
TEST_PROJECT = "Chummer.Tests/Chummer.Tests.csproj"
TEST_COMMAND = [
    "dotnet",
    "test",
    TEST_PROJECT,
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

DEFAULT_ROOT = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get("CHUMMER_NEXT90_M125_ROOT", DEFAULT_ROOT))
SOURCE = ROOT / "tests" / "RunServicesSmoke" / "Program.cs"
OUT = Path(
    os.environ.get(
        "CHUMMER_NEXT90_M125_OUT",
        ROOT / ".codex-studio" / "published" / "NEXT90_M125_HUB_PUBLIC_SIGNAL_PACKETS.generated.json",
    )
)
FLEET_QUEUE_STAGING_PATH = Path(
    os.environ.get(
        "CHUMMER_NEXT90_M125_QUEUE_STAGING",
        "/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml",
    )
)
DESIGN_QUEUE_STAGING_PATH = Path(
    os.environ.get(
        "CHUMMER_NEXT90_M125_DESIGN_QUEUE_STAGING",
        "/docker/chummercomplete/chummer-design-m114/products/chummer/NEXT_90_DAY_QUEUE_STAGING.generated.yaml",
    )
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


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


def _run_capability_test() -> tuple[subprocess.CompletedProcess[str], str, int]:
    env = os.environ.copy()
    env.setdefault("DOTNET_CLI_TELEMETRY_OPTOUT", "1")
    env.setdefault("DOTNET_NOLOGO", "1")
    result = subprocess.run(
        TEST_COMMAND,
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=300,
        check=False,
    )
    output = f"{result.stdout or ''}{result.stderr or ''}"
    executed_test_count = output.count(f"Passed {TEST_FQN}")
    return result, output, executed_test_count


def _write_json_atomic(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(payload, indent=2) + "\n"
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            handle.write(rendered)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
        temp_path = None
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def main() -> int:
    if not SOURCE.is_file():
        print(f"missing smoke source: {SOURCE}", file=sys.stderr)
        return 1

    text = SOURCE.read_text(encoding="utf-8")
    missing = [marker for marker in REQUIRED_MARKERS if marker not in text]
    if missing:
        for marker in missing:
            print(f"next90_m125_materializer_missing: {marker}", file=sys.stderr)
        return 1

    try:
        source_evidence = _source_evidence()
        queue_evidence = _queue_evidence()
    except OSError as exc:
        print(f"next90_m125_materializer_evidence_error: {exc}", file=sys.stderr)
        return 1

    try:
        test_result, test_output, executed_test_count = _run_capability_test()
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"next90_m125_materializer_test_error: {exc}", file=sys.stderr)
        return 1
    if test_result.returncode != 0 or executed_test_count < 1 or "Test Run Successful." not in test_output:
        print(test_output.rstrip(), file=sys.stderr)
        print(
            "next90_m125_materializer_test_failed: the focused public-signal packet test did not pass",
            file=sys.stderr,
        )
        return 1

    generated_at = _utc_now_iso()
    payload = {
        "contract_name": "chummer6-hub.next90_m125_hub_public_signal_packets",
        "schema_version": 2,
        "status": "passed",
        "status_scope": "executed_public_signal_packet_capability",
        "proof_kind": "source_digest_and_executed_test_contract",
        "generated_at": generated_at,
        "verification_command": VERIFICATION_COMMAND,
        "release_binding": {
            "scope": "release_independent_product_capability",
            "release_artifact_specific": False,
            "reason": "The SignalToCanon packet service contract is source- and test-bound, not installer-byte-bound.",
        },
        "package_proof": PACKAGE_PROOF,
        "package_workflow_status": PACKAGE_PROOF["status"],
        "package_workflow_status_affects_capability_status": False,
        "source_file": "tests/RunServicesSmoke/Program.cs",
        "required_markers": REQUIRED_MARKERS,
        "source_evidence": source_evidence,
        "source_evidence_set_sha256": _evidence_set_sha256(source_evidence),
        "queue_evidence": queue_evidence,
        "queue_evidence_set_sha256": _evidence_set_sha256(queue_evidence),
        "test_receipt": {
            "status": "passed",
            "executed_at": generated_at,
            "command": TEST_COMMAND,
            "fully_qualified_name": TEST_FQN,
            "exit_code": test_result.returncode,
            "executed_test_count": executed_test_count,
            "output_sha256": _sha256_bytes(test_output.encode("utf-8")),
        },
    }
    _write_json_atomic(OUT, payload)
    print(f"wrote next90 m125 hub public signal packets proof: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
