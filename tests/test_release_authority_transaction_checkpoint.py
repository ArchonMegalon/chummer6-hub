from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SOURCE_TOOL = ROOT / "scripts" / "release_authority_transaction_checkpoint.py"


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def write_bytes(path: Path, raw: bytes, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    path.chmod(mode)


def invoke(tool: Path, *args: str, secret: str = "ticket-must-never-persist") -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["CHUMMER_RELEASE_UPLOAD_TICKET"] = secret
    return subprocess.run(
        [sys.executable, str(tool), *args],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )


def prepare_workspace(tmp_path: Path) -> dict[str, object]:
    workspace = tmp_path / "private-workspace"
    workspace.mkdir(mode=0o700)
    workspace.chmod(0o700)
    tool = workspace / ".c" / "hub" / "scripts" / SOURCE_TOOL.name
    tool.parent.mkdir(parents=True)
    shutil.copy2(SOURCE_TOOL, tool)
    executed_bootstrap = workspace / "bootstrap.sh"
    write_bytes(executed_bootstrap, b"#!/usr/bin/env bash\nexit 0\n", mode=0o700)

    release_version = "run-20260721-test"
    generation_id = "generation-test"
    manifest_sha256 = "c" * 64
    predecessor_current = b'{"status":"review_required"}\n'
    predecessor_snapshot = b'{"releaseDecisionStatus":"review_required"}\n'
    predecessor_decision = b'{"status":"review_required"}\n'
    successor_decision = json.dumps(
        {
            "releaseVersion": release_version,
            "status": "preview_ready",
            "releaseDecisionStatus": "preview_ready",
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode() + b"\n"
    successor_snapshot = json.dumps(
        {
            "releaseVersion": release_version,
            "releaseDecisionStatus": "preview_ready",
            "releaseDecisionSha256": digest(successor_decision),
            "manifestSha256": manifest_sha256,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode() + b"\n"
    successor_current = json.dumps(
        {
            "releaseVersion": release_version,
            "status": "preview_ready",
            "snapshotSha256": digest(successor_snapshot),
            "decisionSha256": digest(successor_decision),
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode() + b"\n"
    scorecard = b'{"preview_status":"pass"}\n'
    convergence = b'{"status":"pass"}\n'
    raw_files = {
        "predecessor-current": predecessor_current,
        "predecessor-snapshot": predecessor_snapshot,
        "predecessor-decision": predecessor_decision,
        "successor-current": successor_current,
        "successor-snapshot": successor_snapshot,
        "successor-decision": successor_decision,
        "scorecard": scorecard,
        "convergence": convergence,
    }
    paths: dict[str, Path] = {}
    for name, raw in raw_files.items():
        path = workspace / "evidence" / f"{name}.json"
        write_bytes(path, raw)
        paths[name] = path
    for name in ("response-verifier", "registry-inspector", "live-convergence-verifier"):
        path = workspace / "scripts" / f"{name}.py"
        write_bytes(path, b"# pinned helper\n", mode=0o700)
        paths[name] = path

    request_payload = {
        "generationId": generation_id,
        "expectedShelfPointerSha256": "a" * 64,
        "expectedShelfInventoryDigest": "sha256:" + "b" * 64,
    }
    for request_field, source_name in {
        "predecessorCurrentBytes": "predecessor-current",
        "predecessorSnapshotBytes": "predecessor-snapshot",
        "predecessorDecisionBytes": "predecessor-decision",
        "successorCurrentBytes": "successor-current",
        "successorSnapshotBytes": "successor-snapshot",
        "successorDecisionBytes": "successor-decision",
        "scorecardBytes": "scorecard",
        "convergenceBytes": "convergence",
    }.items():
        request_payload[request_field] = base64.b64encode(raw_files[source_name]).decode()
    request = workspace / "evidence" / ".hub-authority-request.json"
    write_bytes(
        request,
        (json.dumps(request_payload, sort_keys=True, separators=(",", ":")) + "\n").encode(),
    )
    paths["request"] = request
    return {
        "workspace": workspace,
        "tool": tool,
        "executed_bootstrap": executed_bootstrap,
        "paths": paths,
        "generation_id": generation_id,
        "release_version": release_version,
        "manifest_sha256": manifest_sha256,
    }


def create_checkpoint(setup: dict[str, object]) -> tuple[Path, str]:
    workspace = setup["workspace"]
    tool = setup["tool"]
    paths = setup["paths"]
    assert isinstance(workspace, Path)
    assert isinstance(tool, Path)
    assert isinstance(paths, dict)
    checkpoint = workspace / "evidence" / ".authority-checkpoint.json"
    result = invoke(
        tool,
        "create",
        "--workspace", str(workspace),
        "--executed-bootstrap", str(setup["executed_bootstrap"]),
        "--generation-id", str(setup["generation_id"]),
        "--release-version", str(setup["release_version"]),
        "--registry-current-url", "https://registry.example/api/v1/registry/release-authority/current",
        "--hub-authority-advance-url",
        f"https://chummer.example/api/internal/releases/generations/{setup['generation_id']}/authority-advances",
        "--live-convergence-base-url", "https://chummer.example",
        "--expected-manifest-sha256", str(setup["manifest_sha256"]),
        "--request", str(paths["request"]),
        "--predecessor-current", str(paths["predecessor-current"]),
        "--predecessor-snapshot", str(paths["predecessor-snapshot"]),
        "--predecessor-decision", str(paths["predecessor-decision"]),
        "--successor-current", str(paths["successor-current"]),
        "--successor-snapshot", str(paths["successor-snapshot"]),
        "--successor-decision", str(paths["successor-decision"]),
        "--scorecard", str(paths["scorecard"]),
        "--convergence", str(paths["convergence"]),
        "--response-verifier", str(paths["response-verifier"]),
        "--registry-inspector", str(paths["registry-inspector"]),
        "--live-convergence-verifier", str(paths["live-convergence-verifier"]),
        "--evidence-directory", str(workspace / "evidence"),
        "--convergence-timeout-seconds", "30",
        "--convergence-attempts", "3",
        "--convergence-retry-seconds", "1",
        "--output", str(checkpoint),
    )
    assert result.returncode == 0, result.stderr
    receipt = json.loads(result.stdout)
    return checkpoint, receipt["checkpointSha256"]


def test_checkpoint_round_trip_is_private_digest_pinned_and_secret_free(tmp_path: Path) -> None:
    setup = prepare_workspace(tmp_path)
    checkpoint, checkpoint_sha256 = create_checkpoint(setup)
    assert stat.S_IMODE(checkpoint.stat().st_mode) == 0o600
    assert digest(checkpoint.read_bytes()) == checkpoint_sha256
    assert b"ticket-must-never-persist" not in checkpoint.read_bytes()

    resolution = setup["workspace"] / ".resolution.json"
    result = invoke(
        setup["tool"],
        "resolve",
        "--workspace", str(setup["workspace"]),
        "--executed-bootstrap", str(setup["executed_bootstrap"]),
        "--checkpoint", str(checkpoint),
        "--expected-checkpoint-sha256", checkpoint_sha256,
        "--output", str(resolution),
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "release_authority_transaction_resolution:pass"
    assert stat.S_IMODE(resolution.stat().st_mode) == 0o600
    assert b"ticket-must-never-persist" not in resolution.read_bytes()


def test_resolve_fails_closed_after_exact_request_tamper(tmp_path: Path) -> None:
    setup = prepare_workspace(tmp_path)
    checkpoint, checkpoint_sha256 = create_checkpoint(setup)
    request = setup["paths"]["request"]
    request.write_bytes(request.read_bytes() + b" ")
    resolution = setup["workspace"] / ".resolution.json"

    result = invoke(
        setup["tool"],
        "resolve",
        "--workspace", str(setup["workspace"]),
        "--executed-bootstrap", str(setup["executed_bootstrap"]),
        "--checkpoint", str(checkpoint),
        "--expected-checkpoint-sha256", checkpoint_sha256,
        "--output", str(resolution),
    )

    assert result.returncode == 1
    assert "request SHA-256 changed" in result.stderr
    assert not resolution.exists()


@pytest.mark.parametrize("failure", ["wrong-digest", "public-mode", "tool-tamper"])
def test_resolve_rejects_checkpoint_or_tool_integrity_failure(tmp_path: Path, failure: str) -> None:
    setup = prepare_workspace(tmp_path)
    checkpoint, checkpoint_sha256 = create_checkpoint(setup)
    if failure == "wrong-digest":
        checkpoint_sha256 = "0" * 64
    elif failure == "public-mode":
        checkpoint.chmod(0o644)
    else:
        setup["tool"].write_text(setup["tool"].read_text() + "\n# tampered\n")
    resolution = setup["workspace"] / ".resolution.json"

    result = invoke(
        setup["tool"],
        "resolve",
        "--workspace", str(setup["workspace"]),
        "--executed-bootstrap", str(setup["executed_bootstrap"]),
        "--checkpoint", str(checkpoint),
        "--expected-checkpoint-sha256", checkpoint_sha256,
        "--output", str(resolution),
    )

    assert result.returncode == 1
    assert not resolution.exists()


def test_resolve_rejects_group_writable_workspace(tmp_path: Path) -> None:
    setup = prepare_workspace(tmp_path)
    checkpoint, checkpoint_sha256 = create_checkpoint(setup)
    setup["workspace"].chmod(0o770)
    resolution = setup["workspace"] / ".resolution.json"
    result = invoke(
        setup["tool"],
        "resolve",
        "--workspace", str(setup["workspace"]),
        "--executed-bootstrap", str(setup["executed_bootstrap"]),
        "--checkpoint", str(checkpoint),
        "--expected-checkpoint-sha256", checkpoint_sha256,
        "--output", str(resolution),
    )
    assert result.returncode == 1
    assert "must not be group- or world-writable" in result.stderr
    assert not resolution.exists()


def test_resolve_rejects_different_or_tampered_executed_bootstrap(tmp_path: Path) -> None:
    setup = prepare_workspace(tmp_path)
    checkpoint, checkpoint_sha256 = create_checkpoint(setup)
    setup["executed_bootstrap"].write_bytes(b"#!/usr/bin/env bash\nexit 1\n")
    resolution = setup["workspace"] / ".resolution.json"
    result = invoke(
        setup["tool"],
        "resolve",
        "--workspace", str(setup["workspace"]),
        "--executed-bootstrap", str(setup["executed_bootstrap"]),
        "--checkpoint", str(checkpoint),
        "--expected-checkpoint-sha256", checkpoint_sha256,
        "--output", str(resolution),
    )
    assert result.returncode == 1
    assert "executedBootstrap SHA-256 changed" in result.stderr
    assert not resolution.exists()
