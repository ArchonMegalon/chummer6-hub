from __future__ import annotations

import base64
from datetime import UTC, datetime
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import zipfile

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = (
    REPO_ROOT
    / "scripts"
    / "release"
    / "public_download_successor_authority.py"
)
WORKFLOW_PATH = (
    REPO_ROOT
    / ".github"
    / "workflows"
    / "public-download-successor-decision.yml"
)
V4_FIXTURE = (
    REPO_ROOT
    / "Chummer.Tests"
    / "Fixtures"
    / "unsigned_candidate_import_authority_v4_distinct_source.json.gz.b64"
)
SOURCE_HEAD = "a" * 40
PREDECESSOR_HEAD = "d" * 40
ACCOUNT_ID = "b" * 32
TUNNEL_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc"
GITHUB_ARTIFACT_ID = 987654321
DECISION_NOW = datetime(2026, 7, 27, 0, 0, tzinfo=UTC)
MATERIALIZE_NOW = datetime(2026, 7, 27, 0, 5, tzinfo=UTC)
VALIDATE_NOW = datetime(2026, 7, 27, 0, 10, tzinfo=UTC)


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


SUCCESSOR = _load(MODULE_PATH, "_successor_authority_under_test")
CLOUDFLARE = SUCCESSOR.load_cloudflare_helper()


class FakeLiveGitHub:
    def __init__(
        self,
        *,
        workflow_run: dict[str, object],
        artifact: dict[str, object],
    ) -> None:
        self.workflow_run = workflow_run
        self.artifact = artifact

    def get_workflow_run(self, run_id: int) -> dict[str, object]:
        return json.loads(json.dumps(self.workflow_run))

    def get_artifact(self, artifact_id: int) -> dict[str, object]:
        return json.loads(json.dumps(self.artifact))


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _label_digest(label: str) -> str:
    return _digest(label.encode())


def _write_json(
    path: Path,
    value: object,
    *,
    canonical: bool = False,
    mode: int = 0o600,
) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    if canonical:
        raw = (
            json.dumps(value, sort_keys=True, separators=(",", ":"))
            + "\n"
        ).encode()
    else:
        raw = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()
    path.write_bytes(raw)
    path.chmod(mode)
    return raw


def _decision_environment() -> dict[str, str]:
    return {
        "GITHUB_EVENT_NAME": "workflow_dispatch",
        "GITHUB_REPOSITORY": SUCCESSOR.SOURCE_REPOSITORY,
        "GITHUB_REF": SUCCESSOR.SOURCE_REF,
        "GITHUB_REF_PROTECTED": "true",
        "GITHUB_SHA": SOURCE_HEAD,
        "GITHUB_RUN_ATTEMPT": "1",
        "GITHUB_RUN_ID": "123456",
        "GITHUB_ACTOR": "ArchonMegalon",
        "GITHUB_TRIGGERING_ACTOR": "ArchonMegalon",
        "GITHUB_ACTOR_ID": "11421547",
        "GITHUB_WORKFLOW_REF": (
            f"{SUCCESSOR.SOURCE_REPOSITORY}/"
            f"{SUCCESSOR.WORKFLOW_PATH}@{SUCCESSOR.SOURCE_REF}"
        ),
    }


def _zip_decision(decision_path: Path, artifact_path: Path) -> bytes:
    info = zipfile.ZipInfo(
        SUCCESSOR.DECISION_ARTIFACT_FILENAME,
        date_time=(2026, 7, 27, 0, 0, 0),
    )
    info.compress_type = zipfile.ZIP_STORED
    info.external_attr = (0o100444 << 16)
    with zipfile.ZipFile(artifact_path, "x") as archive:
        archive.writestr(info, decision_path.read_bytes())
    artifact_path.chmod(0o600)
    return artifact_path.read_bytes()


def _v4_candidate(path: Path) -> tuple[dict[str, object], bytes]:
    raw = gzip.decompress(base64.b64decode(V4_FIXTURE.read_bytes()))
    candidate = json.loads(raw)
    path.write_bytes(raw)
    path.chmod(0o600)
    return candidate, raw


def _build_lane(
    tmp_path: Path,
    *,
    decision_now: datetime = DECISION_NOW,
    decision_environment: dict[str, str] | None = None,
) -> dict[str, object]:
    candidate_path = tmp_path / "candidate-v4.json"
    candidate, candidate_raw = _v4_candidate(candidate_path)
    candidate_sha = _digest(candidate_raw)
    predecessor_project = (
        "chummer-public-download-predecessor-a1b2c3d4"
    )
    predecessor_root = tmp_path / predecessor_project
    predecessor_root.mkdir(mode=0o700)
    retained_generation_id = "run-20260723-193143"
    shelf_root = predecessor_root / "release-shelf"
    generation_root = (
        shelf_root / "generations" / retained_generation_id
    )
    generation_root.mkdir(parents=True, mode=0o700)
    retained_file = generation_root / "retained-incumbent.bin"
    retained_file.write_bytes(b"retained active sidecar generation")
    retained_file.chmod(0o400)
    shelf_tree_sha = SUCCESSOR._tree_sha256_file_stream(
        shelf_root,
        label="test retained predecessor shelf",
    )

    shelf_receipt = {
        "contractName": "chummer.public-download-sidecar-shelf/v1",
        "status": "pass",
        "sourceHead": PREDECESSOR_HEAD,
        "incumbentMigrationAuthority": {"servingAuthority": False},
        "releaseCandidateAuthority": {"status": "pass"},
        "generationId": retained_generation_id,
        "activationReceiptId": "activation-20260723-a1b2c3d4",
        "inventoryDigest": _label_digest("inventory"),
        "pointerSha256": _label_digest("pointer"),
        "activationCandidateSha256": _label_digest("activation"),
        "canonicalMirrorSha256": _label_digest("canonical-mirror"),
        "compatibilityMirrorSha256": _label_digest(
            "compatibility-mirror"
        ),
        "generationCanonicalSha256": _label_digest(
            "generation-canonical"
        ),
        "generationCompatibilitySha256": _label_digest(
            "generation-compatibility"
        ),
        "writerPolicy": {"mode": "immutable"},
        "shelfTreeSha256": shelf_tree_sha,
        "generationRoot": str(generation_root),
    }
    shelf_receipt_path = (
        predecessor_root / "sidecar-shelf-receipt.json"
    )
    shelf_receipt_raw = _write_json(
        shelf_receipt_path,
        shelf_receipt,
    )

    retired_authority_path = (
        predecessor_root / "retired-active-runtime-authority.json"
    )
    retired_authority_raw = _write_json(
        retired_authority_path,
        {
            "contractName": "chummer.public-download-runtime-authority/v1",
            "generationId": retained_generation_id,
            "status": "retired",
        },
    )
    retired_authority_sha = _digest(retired_authority_raw)
    prior_config = {
        "ingress": [
            {
                "hostname": "legacy.invalid",
                "service": "http://127.0.0.1:18080",
            },
            {"service": "http_status:404"},
        ]
    }
    prior_config_sha = CLOUDFLARE.canonical_sha256(prior_config)
    retirement_evidence_sha = _label_digest("retirement-evidence")
    connector_gate_sha = _label_digest("connector-gate")
    terminal = {
        "contractName": "chummer.public-download-committed-retirement/v1",
        "status": "retired",
        "operation": SUCCESSOR.RETIRE_OPERATION,
        "operationRoot": str(predecessor_root),
        "projectName": predecessor_project,
        "operationSourceHead": PREDECESSOR_HEAD,
        "controllerSourceHead": PREDECESSOR_HEAD,
        "retiredAuthorityPath": str(retired_authority_path),
        "retiredAuthoritySha256": retired_authority_sha,
        "retirementEvidencePath": str(
            predecessor_root / "cloudflare-retirement-committed.json"
        ),
        "retirementEvidenceSha256": retirement_evidence_sha,
        "connectorGateSha256": connector_gate_sha,
        "postMarkerConnectorGateSha256": _label_digest(
            "post-marker-connector-gate"
        ),
        "latestConnectorGateSha256": _label_digest(
            "latest-connector-gate"
        ),
        "priorConfigSha256": prior_config_sha,
        "restoredVersion": 12,
        "incumbentBaselineSha256": _label_digest("incumbent"),
        "incumbentObservationSha256": _label_digest("incumbent"),
        "cleanupSha256": _label_digest("cleanup"),
        "completedAtUtc": "2026-07-26T23:50:00Z",
    }
    terminal_path = predecessor_root / "topology-b-retirement.json"
    terminal_raw = _write_json(terminal_path, terminal)
    terminal_sha = _digest(terminal_raw)
    retired_receipt = {
        "contractName": "chummer.public-download-retired-authority/v1",
        "status": "retired",
        "activeAuthorityPath": (
            "/run/chummer-public-download-only/"
            "active-runtime-authority.json"
        ),
        "retiredAuthorityPath": str(retired_authority_path),
        "activeAuthoritySha256": retired_authority_sha,
        "retirementEvidenceSha256": retirement_evidence_sha,
        "connectorGateSha256": connector_gate_sha,
        "disposition": "atomically-retired",
        "retiredAtUtc": "2026-07-26T23:49:00Z",
    }
    journal = {
        "schema": "chummer.public-download-only-operation/v1",
        "phase": "retired",
        "operation": SUCCESSOR.CUTOVER_OPERATION,
        "projectName": predecessor_project,
        "operationRoot": str(predecessor_root),
        "sourceHead": PREDECESSOR_HEAD,
        "bindAddress": "127.0.0.1",
        "bindPort": 18091,
        "canonicalProject": "chummer-public-edge",
        "canonicalShelfRoot": "/srv/chummer/release-shelf",
        "volumes": {"public-download-shelf": "retained-shelf"},
        "createdAtUtc": "2026-07-23T19:30:00Z",
        "updatedAtUtc": "2026-07-26T23:51:00Z",
        "receipts": {
            "shelf": shelf_receipt,
            "retiredAuthority": retired_receipt,
            "retirement": terminal,
        },
        "incumbentBaseline": {"status": "pass"},
    }
    journal_path = (
        predecessor_root.parent / f"{predecessor_project}.operation.json"
    )
    journal_raw = _write_json(journal_path, journal)

    successor_project = "chummer-public-download-successor-e5f6a7b8"
    successor_root = tmp_path / successor_project
    decision_path = (
        tmp_path / SUCCESSOR.DECISION_ARTIFACT_FILENAME
    )
    SUCCESSOR.emit_decision_artifact(
        output=decision_path,
        environment=(
            decision_environment
            if decision_environment is not None
            else _decision_environment()
        ),
        transition_id="successor-20260727-a1b2c3d4",
        operation_root=successor_root,
        project_name=successor_project,
        candidate_authority_sha256=candidate_sha,
        release_version=candidate["candidate"]["version"],
        generation_id=candidate["candidate"]["version"],
        predecessor_operation_root=predecessor_root,
        predecessor_project_name=predecessor_project,
        predecessor_retirement_sha256=terminal_sha,
        predecessor_operation_journal_sha256=_digest(journal_raw),
        predecessor_shelf_receipt_sha256=_digest(shelf_receipt_raw),
        predecessor_retired_authority_sha256=retired_authority_sha,
        retained_generation_id=retained_generation_id,
        retained_shelf_tree_sha256=shelf_tree_sha,
        now=decision_now,
    )
    artifact_path = tmp_path / "provider-decision-artifact.zip"
    artifact_raw = _zip_decision(decision_path, artifact_path)
    run_id = 123456
    run_api_url = (
        f"{SUCCESSOR.GITHUB_API_ROOT}/actions/runs/{run_id}"
    )
    artifact_api_url = (
        f"{SUCCESSOR.GITHUB_API_ROOT}/actions/artifacts/"
        f"{GITHUB_ARTIFACT_ID}"
    )
    github = FakeLiveGitHub(
        workflow_run={
            "id": run_id,
            "url": run_api_url,
            "html_url": (
                f"{SUCCESSOR.GITHUB_WEB_ROOT}/actions/runs/{run_id}"
            ),
            "artifacts_url": f"{run_api_url}/artifacts",
            "path": SUCCESSOR.WORKFLOW_PATH,
            "head_branch": "main",
            "head_sha": SOURCE_HEAD,
            "event": "workflow_dispatch",
            "status": "completed",
            "conclusion": "success",
            "run_attempt": 1,
            "actor": {
                "login": "ArchonMegalon",
                "id": 11421547,
            },
            "triggering_actor": {
                "login": "ArchonMegalon",
                "id": 11421547,
            },
            "repository": {
                "full_name": SUCCESSOR.SOURCE_REPOSITORY,
            },
            "head_repository": {
                "full_name": SUCCESSOR.SOURCE_REPOSITORY,
            },
        },
        artifact={
            "id": GITHUB_ARTIFACT_ID,
            "node_id": "MDg6QXJ0aWZhY3Q5ODc2NTQzMjE=",
            "name": (
                f"public-download-successor-decision-{run_id}-1"
            ),
            "url": artifact_api_url,
            "archive_download_url": f"{artifact_api_url}/zip",
            "expired": False,
            "digest": f"sha256:{_digest(artifact_raw)}",
            "size_in_bytes": len(artifact_raw),
            "workflow_run": {
                "id": run_id,
                "head_branch": "main",
                "head_sha": SOURCE_HEAD,
            },
        },
    )
    response = {
        "success": True,
        "result": {
            "config": prior_config,
            "version": 12,
            "source": "cloudflare",
        },
    }
    response_raw = SUCCESSOR._canonical_bytes(response)
    authority_path = tmp_path / "successor-authority.json"
    return {
        "candidate": candidate,
        "candidatePath": candidate_path,
        "candidateSha256": candidate_sha,
        "predecessorRoot": predecessor_root,
        "terminalPath": terminal_path,
        "terminalSha256": terminal_sha,
        "journalPath": journal_path,
        "shelfReceiptPath": shelf_receipt_path,
        "retiredAuthorityPath": retired_authority_path,
        "generationRoot": generation_root,
        "retainedFile": retained_file,
        "retainedGenerationId": retained_generation_id,
        "shelfTreeSha256": shelf_tree_sha,
        "successorRoot": successor_root,
        "successorProject": successor_project,
        "decisionPath": decision_path,
        "artifactPath": artifact_path,
        "artifactSha256": _digest(artifact_raw),
        "github": github,
        "githubArtifactId": GITHUB_ARTIFACT_ID,
        "response": response,
        "responseRaw": response_raw,
        "authorityPath": authority_path,
    }


def _materialize(lane: dict[str, object]):
    return SUCCESSOR.materialize_successor_authority(
        output=lane["authorityPath"],
        decision_artifact_path=lane["artifactPath"],
        decision_artifact_sha256=lane["artifactSha256"],
        github_artifact_id=lane["githubArtifactId"],
        candidate_authority=lane["candidate"],
        candidate_authority_path=lane["candidatePath"],
        candidate_authority_sha256=lane["candidateSha256"],
        predecessor_retirement_path=lane["terminalPath"],
        predecessor_retirement_sha256=lane["terminalSha256"],
        post_retirement_response=lane["response"],
        post_retirement_response_sha256=_digest(lane["responseRaw"]),
        post_retirement_response_raw=lane["responseRaw"],
        operation_root=lane["successorRoot"],
        project_name=lane["successorProject"],
        source_head=SOURCE_HEAD,
        account_id=ACCOUNT_ID,
        tunnel_id=TUNNEL_ID,
        cloudflare=CLOUDFLARE,
        github=lane["github"],
        now=MATERIALIZE_NOW,
    )


def _validate(lane: dict[str, object]):
    authority_raw = lane["authorityPath"].read_bytes()
    return SUCCESSOR.validate_successor_authority(
        authority_raw,
        authority_path=lane["authorityPath"],
        authority_sha256=_digest(authority_raw),
        decision_artifact_path=lane["artifactPath"],
        decision_artifact_sha256=lane["artifactSha256"],
        github_artifact_id=lane["githubArtifactId"],
        candidate_authority=lane["candidate"],
        candidate_authority_path=lane["candidatePath"],
        candidate_authority_sha256=lane["candidateSha256"],
        predecessor_retirement_path=lane["terminalPath"],
        predecessor_retirement_sha256=lane["terminalSha256"],
        operation_root=lane["successorRoot"],
        project_name=lane["successorProject"],
        source_head=SOURCE_HEAD,
        account_id=ACCOUNT_ID,
        tunnel_id=TUNNEL_ID,
        origin=SUCCESSOR.SUCCESSOR_ORIGIN,
        public_hosts=SUCCESSOR.PUBLIC_HOSTS,
        cloudflare=CLOUDFLARE,
        github=lane["github"],
        now=VALIDATE_NOW,
    )


def test_workflow_is_first_attempt_exact_sole_operator_and_one_file() -> None:
    workflow = WORKFLOW_PATH.read_text()
    assert SUCCESSOR.SOLE_OPERATOR_GITHUB_LOGIN == "ArchonMegalon"
    assert SUCCESSOR.SOLE_OPERATOR_GITHUB_ACTOR_ID == 11421547
    assert "github.run_attempt == 1" in workflow
    assert "github.actor == 'ArchonMegalon'" in workflow
    assert "github.triggering_actor == 'ArchonMegalon'" in workflow
    assert "github.event.sender.login == 'ArchonMegalon'" in workflow
    assert "github.event.sender.id == 11421547" in workflow
    assert 'test "${GITHUB_ACTOR}" = "ArchonMegalon"' in workflow
    assert 'test "${GITHUB_TRIGGERING_ACTOR}" = "ArchonMegalon"' in workflow
    assert 'test "${GITHUB_ACTOR_ID}" = "11421547"' in workflow
    assert "github.ref == 'refs/heads/main'" in workflow
    assert "github.ref_protected == true" in workflow
    assert "environment:" not in workflow
    assert "overwrite: false" in workflow
    assert "PUBLIC_DOWNLOAD_SUCCESSOR_DECISION.generated.json" in workflow
    assert "predecessor_binding_json:" in workflow
    assert workflow.count("        type: string") == 7


@pytest.mark.parametrize(
    ("variable", "replacement"),
    [
        ("GITHUB_ACTOR", "OtherCollaborator"),
        ("GITHUB_TRIGGERING_ACTOR", "OtherCollaborator"),
        ("GITHUB_ACTOR_ID", "11421548"),
        ("GITHUB_ACTOR_ID", "011421547"),
    ],
)
def test_emission_rejects_any_nonsole_operator_identity(
    tmp_path: Path,
    variable: str,
    replacement: str,
) -> None:
    environment = _decision_environment()
    environment[variable] = replacement

    with pytest.raises(
        SUCCESSOR.SuccessorAuthorityError,
        match="exact sole GitHub operator",
    ):
        _build_lane(
            tmp_path,
            decision_environment=environment,
        )


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("actor", "OtherCollaborator"),
        ("triggeringActor", "OtherCollaborator"),
        ("actorId", 11421548),
    ],
)
def test_decision_validation_rejects_nonsole_operator_identity(
    tmp_path: Path,
    field: str,
    replacement: object,
) -> None:
    lane = _build_lane(tmp_path)
    decision = json.loads(lane["decisionPath"].read_text())
    decision["provider"][field] = replacement

    with pytest.raises(
        SUCCESSOR.SuccessorAuthorityError,
        match="provider authentication drifted",
    ):
        SUCCESSOR._validate_decision(decision, now=MATERIALIZE_NOW)


def test_materializes_and_normalizes_exact_retained_successor(
    tmp_path: Path,
) -> None:
    lane = _build_lane(tmp_path)
    authority = _materialize(lane)
    normalized = _validate(lane)

    assert authority["candidate"]["authorityCeiling"] == (
        SUCCESSOR.CANDIDATE_AUTHORITY_CEILING
    )
    assert authority["candidate"]["authorityCeiling"][
        "deployAuthority"
    ] is False
    assert normalized["generationId"] == lane["candidate"]["candidate"][
        "version"
    ]
    assert normalized["retainedIncumbentRoot"] == str(
        lane["generationRoot"]
    )
    assert normalized["retainedIncumbentGenerationId"] == (
        lane["retainedGenerationId"]
    )
    assert normalized["retainedIncumbentShelfTreeSha256"] == (
        lane["shelfTreeSha256"]
    )
    assert normalized["priorVersion"] == 12
    assert normalized["targetConfigSha256"] == authority["cloudflare"][
        "targetConfigSha256"
    ]
    assert normalized["servingAuthority"]["singleUse"] is True
    assert authority["githubProviderEvidence"]["workflowRun"][
        "workflowPath"
    ] == SUCCESSOR.WORKFLOW_PATH
    assert (
        normalized["servingAuthority"]["retainedIncumbentRoot"]
        == str(lane["generationRoot"])
    )
    for field in SUCCESSOR.CANDIDATE_AUTHORITY_CEILING:
        assert lane["candidate"][field] is (
            SUCCESSOR.CANDIDATE_AUTHORITY_CEILING[field]
        )


def test_materialize_cli_does_not_inject_operator_time_into_candidate_freshness(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    candidate_path = tmp_path / "candidate-v4.json"
    candidate_raw = _write_json(
        candidate_path,
        {"contractName": "candidate-v4-sentinel"},
    )
    no_injected_clock = object()

    class RecordingVerifier:
        def __init__(self) -> None:
            self.received_now: list[object] = []

        def _validate_candidate_import_authority_v4(
            self,
            candidate: dict[str, object],
            *,
            now: object = no_injected_clock,
        ) -> dict[str, object]:
            self.received_now.append(now)
            raise RuntimeError("stop after candidate freshness validation")

    verifier = RecordingVerifier()
    monkeypatch.setattr(
        SUCCESSOR,
        "load_projection_verifier",
        lambda: verifier,
    )
    unused_path = tmp_path / "unused"
    result = SUCCESSOR.main(
        [
            "materialize",
            "--decision-artifact",
            str(unused_path),
            "--decision-artifact-sha256",
            "0" * 64,
            "--github-artifact-id",
            "1",
            "--candidate-authority",
            str(candidate_path),
            "--candidate-authority-sha256",
            _digest(candidate_raw),
            "--predecessor-retirement",
            str(unused_path),
            "--predecessor-retirement-sha256",
            "0" * 64,
            "--cloudflare-current-response",
            str(unused_path),
            "--cloudflare-current-response-sha256",
            "0" * 64,
            "--operation-root",
            str(tmp_path / "operation"),
            "--project-name",
            "successor-test",
            "--source-head",
            SOURCE_HEAD,
            "--account-id",
            ACCOUNT_ID,
            "--tunnel-id",
            TUNNEL_ID,
            "--output",
            str(tmp_path / "successor-authority.json"),
            "--now",
            MATERIALIZE_NOW.strftime("%Y-%m-%dT%H:%M:%SZ"),
        ]
    )

    assert result == 1
    assert verifier.received_now == [no_injected_clock]
    assert "failed the strict v4 verifier" in capsys.readouterr().err


def test_rejects_any_v4_serving_authority_widening(
    tmp_path: Path,
) -> None:
    lane = _build_lane(tmp_path)
    widened = json.loads(json.dumps(lane["candidate"]))
    widened["deployAuthority"] = True
    with pytest.raises(
        SUCCESSOR.SuccessorAuthorityError,
        match="exact non-serving v4 identity",
    ):
        SUCCESSOR._validate_v4_identity(
            widened,
            now=MATERIALIZE_NOW,
        )


def test_rejects_retained_generation_tree_or_journal_tamper(
    tmp_path: Path,
) -> None:
    lane = _build_lane(tmp_path)
    _materialize(lane)
    lane["retainedFile"].chmod(0o600)
    lane["retainedFile"].write_bytes(b"stale primary substitution")
    lane["retainedFile"].chmod(0o400)

    with pytest.raises(
        SUCCESSOR.SuccessorAuthorityError,
        match="generation custody drifted",
    ):
        _validate(lane)


def test_rejects_nonterminal_or_extra_file_provider_decision(
    tmp_path: Path,
) -> None:
    lane = _build_lane(tmp_path)
    bad_artifact = tmp_path / "bad-provider-decision.zip"
    with zipfile.ZipFile(bad_artifact, "x") as archive:
        archive.write(
            lane["decisionPath"],
            SUCCESSOR.DECISION_ARTIFACT_FILENAME,
        )
        archive.writestr("reviewer.txt", b"not part of the contract")
    bad_artifact.chmod(0o600)

    with pytest.raises(
        SUCCESSOR.SuccessorAuthorityError,
        match="exactly one file",
    ):
        SUCCESSOR.read_decision_artifact(
            bad_artifact,
            _digest(bad_artifact.read_bytes()),
            now=MATERIALIZE_NOW,
        )


def test_live_github_rejects_forged_valid_one_file_zip(
    tmp_path: Path,
) -> None:
    lane = _build_lane(tmp_path)
    forged_decision = json.loads(lane["decisionPath"].read_text())
    forged_decision["transitionId"] = "forged-20260727-a1b2c3d4"
    forged_decision_path = tmp_path / "forged-decision.json"
    _write_json(
        forged_decision_path,
        forged_decision,
        canonical=True,
        mode=0o444,
    )
    forged_artifact_path = tmp_path / "forged-provider-artifact.zip"
    forged_artifact_raw = _zip_decision(
        forged_decision_path,
        forged_artifact_path,
    )
    lane["artifactPath"] = forged_artifact_path
    lane["artifactSha256"] = _digest(forged_artifact_raw)

    with pytest.raises(
        SUCCESSOR.SuccessorAuthorityError,
        match="live GitHub artifact does not bind",
    ):
        _materialize(lane)


@pytest.mark.parametrize(
    ("resource", "path", "replacement"),
    [
        (
            "workflow_run",
            ("path",),
            f"{SUCCESSOR.WORKFLOW_PATH}@main",
        ),
        (
            "workflow_run",
            ("path",),
            ".github/workflows/other.yml",
        ),
        ("workflow_run", ("head_sha",), "e" * 40),
        ("workflow_run", ("event",), "push"),
        (
            "workflow_run",
            ("triggering_actor", "login"),
            "DifferentActor",
        ),
        (
            "workflow_run",
            ("actor", "login"),
            "DifferentActor",
        ),
        ("workflow_run", ("actor", "id"), 11421548),
        ("workflow_run", ("triggering_actor", "id"), 11421548),
        ("workflow_run", ("run_attempt",), 2),
        ("workflow_run", ("status",), "in_progress"),
        ("workflow_run", ("conclusion",), "failure"),
        ("artifact", ("id",), GITHUB_ARTIFACT_ID + 1),
        ("artifact", ("name",), "forged-artifact-name"),
        ("artifact", ("digest",), f"sha256:{'f' * 64}"),
        ("artifact", ("workflow_run", "id"), 654321),
        ("artifact", ("workflow_run", "head_sha"), "e" * 40),
        ("artifact", ("expired",), True),
    ],
)
def test_live_github_rejects_provider_field_tamper(
    tmp_path: Path,
    resource: str,
    path: tuple[str, ...],
    replacement: object,
) -> None:
    lane = _build_lane(tmp_path)
    github = lane["github"]
    target = getattr(github, resource)
    for component in path[:-1]:
        target = target[component]
    target[path[-1]] = replacement

    with pytest.raises(
        SUCCESSOR.SuccessorAuthorityError,
        match="live GitHub (workflow run|artifact) does not",
    ):
        _materialize(lane)


def test_rejects_post_retirement_cloudflare_snapshot_drift(
    tmp_path: Path,
) -> None:
    lane = _build_lane(tmp_path)
    lane["response"]["result"]["version"] = 13
    lane["responseRaw"] = SUCCESSOR._canonical_bytes(lane["response"])
    with pytest.raises(
        SUCCESSOR.SuccessorAuthorityError,
        match="actual post-retirement Cloudflare snapshot differs",
    ):
        _materialize(lane)


def test_rejects_decision_that_predates_ordinary_retirement(
    tmp_path: Path,
) -> None:
    lane = _build_lane(
        tmp_path,
        decision_now=datetime(2026, 7, 26, 23, 49, tzinfo=UTC),
    )
    with pytest.raises(
        SUCCESSOR.SuccessorAuthorityError,
        match="retire-then-fresh",
    ):
        _materialize(lane)
