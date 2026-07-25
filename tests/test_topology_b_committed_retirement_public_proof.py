from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from typing import Any
from urllib.parse import urlsplit

import pytest


ROOT = Path(__file__).resolve().parents[1]


def load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


controller = load_module(
    ROOT / "scripts/deploy_public_download_only_cutover.py",
    "topology_b_public_retirement_controller",
)
cloudflare = load_module(
    ROOT / "scripts/cloudflare_public_download_transaction.py",
    "topology_b_public_retirement_cloudflare",
)
sys.modules["deploy_public_download_only_cutover"] = controller
sys.modules["cloudflare_public_download_transaction"] = cloudflare
provider = load_module(
    ROOT / "scripts/verify_topology_b_committed_retirement_proof.py",
    "topology_b_public_retirement_provider",
)


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


def json_bytes(value: dict[str, Any]) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True) + "\n"
    ).encode()


def connector_gate(version: int) -> dict[str, Any]:
    connector_set = [
        {
            "id": "connector-a",
            "configVersionAvailable": True,
            "configVersion": version,
        }
    ]
    return {
        "contractName": "cloudflare.current-connector-convergence/v1",
        "targetVersion": version,
        "connectorSet": connector_set,
        "connectorSetSha256": canonical_sha256(connector_set),
        "connectorConvergence": [
            {
                "id": "connector-a",
                "configVersionAvailable": True,
                "observedConfigVersion": version,
                "converged": True,
            }
        ],
        "connectorSetTransitions": [["connector-a"]],
        "attemptsUsed": 2,
        "stableObservationsRequired": 2,
    }


def exact_bundle(
    *,
    generated_at: datetime | None = None,
) -> tuple[dict[str, Any], bytes, dict[str, Any], bytes, dict[str, Any], bytes]:
    generated = (generated_at or datetime.now(UTC)).replace(microsecond=0)
    timestamp = generated.isoformat().replace("+00:00", "Z")
    retired_sha256 = "1" * 64
    marker_gate = connector_gate(13)
    convergence = connector_gate(13)
    post_marker = {
        "contractName": (
            "chummer.public-download-retirement-connector-boundary/v1"
        ),
        "status": "pass",
        "boundary": "post-marker",
        "operationRoot": "/private/operation",
        "restoredVersion": 13,
        "retiredAuthoritySha256": retired_sha256,
        "markerConnectorGateSha256": canonical_sha256(marker_gate),
        "connectorConvergence": convergence,
        "connectorConvergenceSha256": canonical_sha256(convergence),
        "verifiedAtUtc": timestamp,
    }
    post_marker_raw = json_bytes(post_marker)
    terminal = {
        "contractName": (
            "chummer.public-download-committed-retirement/v1"
        ),
        "status": "retired",
        "operation": controller.RETIRE_OPERATION,
        "operationRoot": "/private/operation",
        "projectName": "public-retirement-test",
        "operationSourceHead": "a" * 40,
        "controllerSourceHead": "b" * 40,
        "retiredAuthorityPath": "/private/operation/retired.json",
        "retiredAuthoritySha256": retired_sha256,
        "retirementEvidencePath": "/private/operation/evidence.json",
        "retirementEvidenceSha256": "2" * 64,
        "connectorGateSha256": canonical_sha256(marker_gate),
        "postMarkerConnectorGateSha256": canonical_sha256(post_marker),
        "latestConnectorGateSha256": canonical_sha256(post_marker),
        "priorConfigSha256": "3" * 64,
        "restoredVersion": 13,
        "incumbentBaselineSha256": "4" * 64,
        "incumbentObservationSha256": "4" * 64,
        "cleanupSha256": "5" * 64,
        "completedAtUtc": timestamp,
    }
    terminal_raw = json_bytes(terminal)
    publisher_sha256 = "6" * 64
    proof = {
        "contractName": (
            controller.TOPOLOGY_B_PUBLIC_RETIREMENT_CONTRACT
        ),
        "contractVersion": 1,
        "generatedAt": timestamp,
        "status": "passed",
        "source": {
            "repository": controller.TOPOLOGY_B_SOURCE_REPOSITORY,
            "ref": controller.TOPOLOGY_B_SOURCE_REF,
            "commit": "b" * 40,
        },
        "sidecarAuthorityRetired": True,
        "activeSidecarMarkerCount": 0,
        "activeSidecarMarkers": [],
        "retiredAuthoritySha256": retired_sha256,
        "committedBoundaryReceipt": {
            "sha256": hashlib.sha256(terminal_raw).hexdigest(),
            "sizeBytes": len(terminal_raw),
        },
        "postMarkerConvergenceReceipt": {
            "sha256": hashlib.sha256(post_marker_raw).hexdigest(),
            "sizeBytes": len(post_marker_raw),
        },
        "canonicalAuthority": {
            "baseUrl": controller.CANONICAL_DOWNLOADS_BASE_URL,
            "manifestUrl": controller.CANONICAL_DOWNLOADS_MANIFEST_URL,
            "publisherPath": (
                controller.CANONICAL_DOWNLOADS_PUBLISHER_PATH
            ),
            "publisherSha256": publisher_sha256,
        },
    }
    proof_raw = json_bytes(proof)
    return (
        proof,
        proof_raw,
        terminal,
        terminal_raw,
        post_marker,
        post_marker_raw,
    )


def test_public_bundle_validator_accepts_exact_terminal_bound_proof() -> None:
    proof, proof_raw, _terminal, terminal_raw, _post, post_raw = (
        exact_bundle()
    )

    validated = controller.validate_topology_b_public_retirement_bundle(
        proof_bytes=proof_raw,
        committed_boundary_bytes=terminal_raw,
        post_marker_bytes=post_raw,
        expected_source_head="b" * 40,
        expected_publisher_sha256="6" * 64,
        cloudflare=cloudflare,
    )

    assert validated == proof


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("contractVersion", True),
        ("activeSidecarMarkerCount", False),
    ),
)
def test_public_bundle_validator_rejects_boolean_integer_confusion(
    field: str,
    value: bool,
) -> None:
    proof, _proof_raw, _terminal, terminal_raw, _post, post_raw = (
        exact_bundle()
    )
    proof[field] = value

    with pytest.raises(controller.RecoveryUncertain, match="authority drifted"):
        controller.validate_topology_b_public_retirement_bundle(
            proof_bytes=json_bytes(proof),
            committed_boundary_bytes=terminal_raw,
            post_marker_bytes=post_raw,
            expected_source_head="b" * 40,
            expected_publisher_sha256="6" * 64,
            cloudflare=cloudflare,
        )


@pytest.mark.parametrize(
    "mutation,match",
    (
        ("source", "authority drifted"),
        ("marker", "authority drifted"),
        ("publisher", "publisher authority drifted"),
        ("terminal", "retirement boundary drifted"),
        ("post-marker", "post-marker connector convergence boundary drifted"),
        ("binding", "committed boundary binding drifted"),
    ),
)
def test_public_bundle_validator_rejects_tamper(
    mutation: str,
    match: str,
) -> None:
    proof, _proof_raw, terminal, _terminal_raw, post, _post_raw = (
        exact_bundle()
    )
    if mutation == "source":
        proof["source"]["commit"] = "c" * 40
    elif mutation == "marker":
        proof["activeSidecarMarkerCount"] = 1
        proof["activeSidecarMarkers"] = ["forged"]
    elif mutation == "publisher":
        proof["canonicalAuthority"]["publisherSha256"] = "7" * 64
    elif mutation == "terminal":
        terminal["controllerSourceHead"] = "c" * 40
    elif mutation == "post-marker":
        post["retiredAuthoritySha256"] = "8" * 64
    else:
        proof["committedBoundaryReceipt"]["sha256"] = "9" * 64
    terminal_raw = json_bytes(terminal)
    post_raw = json_bytes(post)
    if mutation != "binding":
        proof["committedBoundaryReceipt"] = {
            "sha256": hashlib.sha256(terminal_raw).hexdigest(),
            "sizeBytes": len(terminal_raw),
        }
        proof["postMarkerConvergenceReceipt"] = {
            "sha256": hashlib.sha256(post_raw).hexdigest(),
            "sizeBytes": len(post_raw),
        }

    with pytest.raises(controller.RecoveryUncertain, match=match):
        controller.validate_topology_b_public_retirement_bundle(
            proof_bytes=json_bytes(proof),
            committed_boundary_bytes=terminal_raw,
            post_marker_bytes=post_raw,
            expected_source_head="b" * 40,
            expected_publisher_sha256="6" * 64,
            cloudflare=cloudflare,
        )


def test_public_bundle_validator_rejects_stale_proof() -> None:
    proof, _proof_raw, terminal, _terminal_raw, post, post_raw = (
        exact_bundle(generated_at=datetime.now(UTC) - timedelta(hours=25))
    )
    terminal_raw = json_bytes(terminal)
    proof["committedBoundaryReceipt"] = {
        "sha256": hashlib.sha256(terminal_raw).hexdigest(),
        "sizeBytes": len(terminal_raw),
    }
    proof["postMarkerConvergenceReceipt"] = {
        "sha256": hashlib.sha256(post_raw).hexdigest(),
        "sizeBytes": len(post_raw),
    }

    with pytest.raises(controller.RecoveryUncertain, match="stale"):
        controller.validate_topology_b_public_retirement_bundle(
            proof_bytes=json_bytes(proof),
            committed_boundary_bytes=terminal_raw,
            post_marker_bytes=post_raw,
            expected_source_head="b" * 40,
            expected_publisher_sha256="6" * 64,
            cloudflare=cloudflare,
        )


def materialization_fixture(
    tmp_path: Path,
) -> tuple[SimpleNamespace, dict[str, Any]]:
    (
        _proof,
        _proof_raw,
        terminal,
        terminal_raw,
        post_marker,
        _post_raw,
    ) = exact_bundle()
    operation_root = tmp_path / "operation"
    receipt_root = tmp_path / "receipts"
    shelf_root = tmp_path / "downloads"
    authority_root = tmp_path / "authority"
    for path, mode in (
        (operation_root, 0o700),
        (receipt_root, 0o700),
        (shelf_root, 0o755),
        (authority_root, 0o700),
    ):
        path.mkdir(mode=mode)
    retired = operation_root / "retired.json"
    retired.write_bytes(b"retired authority\n")
    retired.chmod(0o600)
    controller_head = subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout.strip()
    terminal["operationRoot"] = str(operation_root)
    terminal["controllerSourceHead"] = controller_head
    terminal["retiredAuthorityPath"] = str(retired)
    terminal["retiredAuthoritySha256"] = hashlib.sha256(
        retired.read_bytes()
    ).hexdigest()
    post_marker["operationRoot"] = str(operation_root)
    post_marker["retiredAuthoritySha256"] = terminal[
        "retiredAuthoritySha256"
    ]
    post_marker["markerConnectorGateSha256"] = terminal[
        "connectorGateSha256"
    ]
    terminal["postMarkerConnectorGateSha256"] = canonical_sha256(
        post_marker
    )
    terminal["latestConnectorGateSha256"] = canonical_sha256(post_marker)
    terminal_path = operation_root / "topology-b-retirement.json"
    terminal_path.write_bytes(json_bytes(terminal))
    terminal_path.chmod(0o600)
    operation_journal = receipt_root / "operation.json"
    operation_journal.write_bytes(
        json_bytes(
            {
                "schema": controller.TOPOLOGY_B_OPERATION_SCHEMA,
                "phase": "retired",
                "operation": controller.CUTOVER_OPERATION,
                "receipts": {
                    "retirement": terminal,
                    "retirementPostMarkerConnectorGate": post_marker,
                },
            }
        )
    )
    operation_journal.chmod(0o600)
    active = authority_root / "active.json"
    config = SimpleNamespace(
        operation=controller.RETIRE_OPERATION,
        source_root=ROOT,
        source_head="a" * 40,
        controller_source_head=controller_head,
        canonical_publisher_sha256="6" * 64,
        base_url="https://chummer.run",
        operation_root=operation_root,
        operation_journal=operation_journal,
        active_runtime_authority=active,
        retired_active_authority=retired,
        retirement_receipt=terminal_path,
        public_retirement_proof=(
            operation_root / "public-retirement-proof.json"
        ),
        public_retirement_materialization_receipt=(
            operation_root / "public-retirement-materialization.json"
        ),
        shelf_root=shelf_root,
    )
    result = {
        "contractName": controller.TOPOLOGY_B_CONTRACT,
        "status": "pass",
        "operation": controller.RETIRE_OPERATION,
        "disposition": "committed-sidecar-retired-to-incumbent",
        "operationSourceHead": "a" * 40,
        "controllerSourceHead": controller_head,
        "terminalReceipt": terminal,
    }
    assert terminal_raw != terminal_path.read_bytes()
    return config, result


def shelf_reader(config: SimpleNamespace):
    def read(url: str) -> bytes:
        parsed = urlsplit(url)
        assert parsed.scheme == "https"
        assert parsed.netloc == "chummer.run"
        relative = parsed.path.removeprefix("/downloads/")
        return (config.shelf_root / relative).read_bytes()

    return read


def test_materializer_commits_content_before_fixed_proof_and_is_idempotent(
    tmp_path: Path,
) -> None:
    config, result = materialization_fixture(tmp_path)

    first = controller.materialize_topology_b_public_retirement_proof(
        config,
        result,
        public_reader=shelf_reader(config),
        attempts=1,
        sleep_fn=lambda _seconds: None,
        interval_seconds=0,
    )
    proof_path = (
        config.shelf_root
        / controller.TOPOLOGY_B_PUBLIC_RETIREMENT_FILENAME
    )
    first_proof = proof_path.read_bytes()
    first_receipt = (
        config.public_retirement_materialization_receipt.read_bytes()
    )
    second = controller.materialize_topology_b_public_retirement_proof(
        config,
        result,
        public_reader=shelf_reader(config),
        attempts=1,
        sleep_fn=lambda _seconds: None,
        interval_seconds=0,
    )

    assert second == first
    assert proof_path.read_bytes() == first_proof
    assert (
        config.public_retirement_materialization_receipt.read_bytes()
        == first_receipt
    )
    public_files = [
        proof_path,
        *(
            config.shelf_root
            / controller.TOPOLOGY_B_PUBLIC_RECEIPT_DIRECTORY
        ).iterdir(),
    ]
    assert len(public_files) == 3
    assert {path.stat().st_mode & 0o777 for path in public_files} == {
        0o444
    }


def test_materializer_prefers_latest_resume_post_marker_gate(
    tmp_path: Path,
) -> None:
    config, result = materialization_fixture(tmp_path)
    journal = json.loads(config.operation_journal.read_text())
    resume_gate = deepcopy(
        journal["receipts"]["retirementPostMarkerConnectorGate"]
    )
    resume_gate["boundary"] = "resume-post-marker"
    terminal = journal["receipts"]["retirement"]
    terminal["latestConnectorGateSha256"] = canonical_sha256(resume_gate)
    journal["receipts"]["retirementConnectorResumeGate"] = resume_gate
    config.operation_journal.write_bytes(json_bytes(journal))
    config.retirement_receipt.write_bytes(json_bytes(terminal))
    result["terminalReceipt"] = terminal

    materialization = (
        controller.materialize_topology_b_public_retirement_proof(
            config,
            result,
            public_reader=shelf_reader(config),
            attempts=1,
            sleep_fn=lambda _seconds: None,
            interval_seconds=0,
        )
    )

    published = Path(
        materialization["postMarkerConvergence"]["path"]
    ).read_bytes()
    assert published == json_bytes(resume_gate)
    assert (
        materialization["postMarkerConvergence"]["sha256"]
        == hashlib.sha256(json_bytes(resume_gate)).hexdigest()
    )


def test_materializer_recovers_after_interruption_before_commit_marker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config, result = materialization_fixture(tmp_path)
    real_write = controller._atomic_public_retirement_write
    events: list[str] = []

    def interrupt(path: Path, value: bytes, *, replace: bool) -> None:
        events.append(path.name)
        if path.name == controller.TOPOLOGY_B_PUBLIC_RETIREMENT_FILENAME:
            raise OSError("simulated interruption")
        real_write(path, value, replace=replace)

    monkeypatch.setattr(
        controller,
        "_atomic_public_retirement_write",
        interrupt,
    )
    with pytest.raises(OSError, match="simulated interruption"):
        controller.materialize_topology_b_public_retirement_proof(
            config,
            result,
            public_reader=shelf_reader(config),
            attempts=1,
            sleep_fn=lambda _seconds: None,
            interval_seconds=0,
        )
    assert events[-1] == controller.TOPOLOGY_B_PUBLIC_RETIREMENT_FILENAME
    assert not (
        config.shelf_root
        / controller.TOPOLOGY_B_PUBLIC_RETIREMENT_FILENAME
    ).exists()
    assert len(
        list(
            (
                config.shelf_root
                / controller.TOPOLOGY_B_PUBLIC_RECEIPT_DIRECTORY
            ).iterdir()
        )
    ) == 2

    monkeypatch.setattr(
        controller,
        "_atomic_public_retirement_write",
        real_write,
    )
    controller.materialize_topology_b_public_retirement_proof(
        config,
        result,
        public_reader=shelf_reader(config),
        attempts=1,
        sleep_fn=lambda _seconds: None,
        interval_seconds=0,
    )
    assert (
        config.shelf_root
        / controller.TOPOLOGY_B_PUBLIC_RETIREMENT_FILENAME
    ).is_file()


def test_provider_context_requires_first_attempt_same_actor_main() -> None:
    context = {
        "GITHUB_EVENT_NAME": "workflow_dispatch",
        "GITHUB_REPOSITORY": "ArchonMegalon/chummer6-hub",
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_SHA": "b" * 40,
        "GITHUB_RUN_ATTEMPT": "1",
        "GITHUB_ACTOR": "release-reviewer",
        "GITHUB_TRIGGERING_ACTOR": "release-reviewer",
    }
    assert provider.validate_github_context(context) == "b" * 40
    for key, replacement in (
        ("GITHUB_RUN_ATTEMPT", "2"),
        ("GITHUB_REF", "refs/heads/feature"),
        ("GITHUB_TRIGGERING_ACTOR", "different-reviewer"),
    ):
        tampered = dict(context)
        tampered[key] = replacement
        with pytest.raises(provider.ProofError):
            provider.validate_github_context(tampered)


def test_provider_capture_emits_exact_three_read_only_entries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proof, proof_raw, _terminal, terminal_raw, _post, post_raw = (
        exact_bundle()
    )
    by_url = {
        (
            f"{controller.CANONICAL_DOWNLOADS_BASE_URL}/"
            f"{controller.TOPOLOGY_B_PUBLIC_RETIREMENT_FILENAME}"
        ): proof_raw,
        (
            f"{controller.CANONICAL_DOWNLOADS_BASE_URL}/"
            f"{controller.TOPOLOGY_B_PUBLIC_RECEIPT_DIRECTORY}/"
            "committed-boundary-"
            f"{proof['committedBoundaryReceipt']['sha256']}.json"
        ): terminal_raw,
        (
            f"{controller.CANONICAL_DOWNLOADS_BASE_URL}/"
            f"{controller.TOPOLOGY_B_PUBLIC_RECEIPT_DIRECTORY}/"
            "post-marker-convergence-"
            f"{proof['postMarkerConvergenceReceipt']['sha256']}.json"
        ): post_raw,
    }
    monkeypatch.setattr(
        controller,
        "strict_public_retirement_get",
        by_url.__getitem__,
    )
    output = tmp_path / "provider-proof"

    result = provider.capture_public_bundle(
        source_sha="b" * 40,
        output_dir=output,
    )

    assert result["status"] == "passed"
    assert result["entryCount"] == 3
    assert sorted(path.name for path in output.iterdir()) == [
        "TOPOLOGY_B_RETIREMENT.generated.json",
        "committed-boundary-receipt.json",
        "post-marker-convergence-receipt.json",
    ]
    assert {path.stat().st_mode & 0o777 for path in output.iterdir()} == {
        0o444
    }


def test_workflow_is_exact_protected_three_file_authority() -> None:
    workflow = (
        ROOT
        / ".github/workflows/topology-b-committed-retirement-proof.yml"
    ).read_text(encoding="utf-8")

    assert "workflow_dispatch:" in workflow
    assert "environment: topology-b-committed-retirement-proof" in workflow
    assert "runs-on: ubuntu-24.04" in workflow
    assert "permissions:\n  contents: read" in workflow
    assert "persist-credentials: false" in workflow
    assert "topology-b-committed-retirement-proof-${{ github.run_id }}-1" in workflow
    assert "overwrite: false" in workflow
    assert "include-hidden-files: false" in workflow
    assert "TOPOLOGY_B_RETIREMENT.generated.json" in workflow
    assert "committed-boundary-receipt.json" in workflow
    assert "post-marker-convergence-receipt.json" in workflow


def test_retirement_wrapper_requires_main_and_exact_publisher_pin() -> None:
    wrapper = (
        ROOT / "scripts/deploy_public_edge_portal.sh"
    ).read_text(encoding="utf-8")

    assert (
        'PUBLIC_DOWNLOAD_CANONICAL_PUBLISHER_SHA256="${'
        'CHUMMER_PUBLIC_DOWNLOAD_CANONICAL_PUBLISHER_SHA256-}"'
    ) in wrapper
    assert (
        'EXPECTED_UPSTREAM_REF" != refs/remotes/origin/main'
    ) in wrapper
    assert (
        "--canonical-publisher-sha256 "
        '"$PUBLIC_DOWNLOAD_CANONICAL_PUBLISHER_SHA256"'
    ) in wrapper
