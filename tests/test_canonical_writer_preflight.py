from __future__ import annotations

import contextlib
import copy
import importlib.util
import ipaddress
import json
import socket
import stat
import subprocess
import sys
import threading
import textwrap
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "release" / "canonical_writer_preflight.py"
LANDLOCK_EXEC = ROOT / "scripts" / "release" / "landlock_exec.py"
SECCOMP_LIBRARY = Path("/usr/lib/x86_64-linux-gnu/libseccomp.so.2.5.5")
SPEC = importlib.util.spec_from_file_location("canonical_writer_preflight", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

FIXTURE_ARTIFACT_BYTES = b"a"
FIXTURE_ARTIFACT_SHA256 = MODULE.sha256_bytes(FIXTURE_ARTIFACT_BYTES)


def manifest() -> dict:
    return {
        "generationId": "generation-a",
        "version": "release-a",
        "channel": "preview",
        "publishedAt": "2026-07-16T12:00:00Z",
        "generatedAt": "2026-07-16T12:00:00Z",
        "generated_at": "2026-07-16T12:00:00Z",
        "contractName": "Chummer.Hub.Registry.Contracts",
        "contract_name": "Chummer.Hub.Registry.Contracts",
        "status": "published",
        "rolloutState": "public_release_review_required",
        "rolloutReason": (
            "Current shelf is published, but release posture stays review-required because "
            "stale or incomplete proof receipts still block launch-readiness claims."
        ),
        "supportabilityState": "review_required",
        "supportabilitySummary": (
            "Current preview artifacts remain downloadable for proof testing, but supportability "
            "is review-required until stale proof receipts are refreshed."
        ),
        "releaseProof": {
            "status": "passed",
            "generatedAt": "2026-07-16T11:59:00Z",
            "baseUrl": "https://chummer.run",
            "journeysPassed": list(MODULE.REQUIRED_RELEASE_PROOF_JOURNEYS),
            "proofRoutes": [
                *MODULE.REQUIRED_RELEASE_PROOF_ROUTES,
                "/downloads/install/a",
            ],
            "uiLocalizationReleaseGate": {
                "status": "pass",
                "generatedAt": "2026-07-16T11:59:30Z",
            },
        },
        "publicTrustMetrics": {
            "proofFreshness": {"status": "stale"},
            "releaseChannel": {
                "channelId": "preview",
                "publicationStatus": "published",
                "rolloutState": "public_release_review_required",
                "supportabilityState": "review_required",
                "posture": "blocked",
                "recommendedRouteCount": 0,
                "blockedRouteCount": 1,
                "revokedRouteCount": 0,
                "fallbackRecoveryRouteCount": 0,
                "summary": (
                    "Channel preview remains published for bounded proof testing, but public "
                    "trust posture is blocked until proof freshness is current."
                ),
            },
            "revocationFacts": {
                "status": "clear",
                "channelRevoked": False,
                "activeRevocationCount": 0,
                "activeRevocations": [],
                "summary": "No channel or route revocations are active on channel preview.",
            },
        },
        "registryBoundaryCoverage": {
            "status": "closed",
            "owner": "chummer6-hub-registry",
            "channelId": "preview",
            "releaseVersion": "release-a",
            "releaseChannel": {
                "publicationStatus": "published",
                "rolloutState": "public_release_review_required",
                "supportabilityState": "review_required",
                "publicTrustPosture": "blocked",
                "desktopTupleComplete": True,
                "promotedInstallerTupleCount": 1,
                "desktopRouteTruthCount": 1,
                "summary": (
                    "Release-channel truth for preview/release-a keeps 1 promoted installer tuples "
                    "and 1 explicit desktop route-truth rows while rollout remains "
                    "public_release_review_required and public trust is blocked."
                ),
            },
        },
        "desktopTupleCoverage": {
            "requiredDesktopPlatforms": ["desktop"],
            "requiredDesktopHeads": ["a"],
            "requiredDesktopPlatformHeadRidTuples": ["a:test-x64:desktop"],
            "promotedPlatformHeadRidTuples": ["a:test-x64:desktop"],
            "missingRequiredPlatforms": [],
            "missingRequiredHeads": [],
            "missingRequiredPlatformHeadPairs": [],
            "missingRequiredPlatformHeadRidTuples": [],
            "promotedInstallerTuples": [
                {
                    "tupleId": "a:desktop:test-x64",
                    "artifactId": "a",
                    "kind": "installer",
                    "head": "a",
                    "arch": "x64",
                    "platform": "desktop",
                    "rid": "test-x64",
                }
            ],
            "desktopRouteTruth": [
                {
                    "tupleId": "a:desktop:test-x64",
                    "artifactId": "a",
                    "routeRole": "primary",
                    "promotionState": "promoted",
                    "promotionReasonCode": "installer_smoke_and_release_proof_passed",
                    "revokeState": "not_revoked",
                    "revokeSource": "none",
                    "revokeReasonCode": "no_registry_revoke_marker",
                    "installPosture": "installer_first",
                    "rollbackState": "fallback_available",
                    "updateEligibility": "eligible",
                    "publicInstallRoute": "/downloads/install/a",
                    "head": "a",
                    "arch": "x64",
                    "platform": "desktop",
                    "rid": "test-x64",
                }
            ],
            "complete": True,
        },
        "artifacts": [
            {
                "artifactId": "a",
                "fileName": "a.bin",
                "downloadUrl": "/downloads/g/generation-a/files/a.bin",
                "sha256": FIXTURE_ARTIFACT_SHA256,
                "sizeBytes": 1,
                "installAccessClass": "open_public",
                "kind": "installer",
                "head": "a",
                "arch": "x64",
                "platform": "desktop",
                "rid": "test-x64",
                "compatibilityState": "compatible",
                "compatibilityReason": None,
            }
        ],
    }


def compatibility_manifest(canonical: dict) -> dict:
    compatibility = copy.deepcopy(canonical)
    compatibility["downloads"] = [
        {
            "id": row["artifactId"],
            "fileName": row["fileName"],
            "url": row["downloadUrl"],
            "sha256": row["sha256"],
            "sizeBytes": row["sizeBytes"],
            "installAccessClass": row["installAccessClass"],
            "kind": row["kind"],
            "head": row["head"],
            "arch": row["arch"],
            "platform": row["platform"],
            "rid": row["rid"],
            "compatibilityState": row["compatibilityState"],
            "compatibilityReason": row["compatibilityReason"],
        }
        for row in canonical["artifacts"]
    ]
    compatibility.pop("artifacts")
    return compatibility


def test_registry_compatibility_projection_satisfies_artifact_inventory_contract() -> None:
    registry_materializer = (
        ROOT.parent
        / "chummer-hub-registry"
        / "scripts"
        / "materialize_public_release_channel.py"
    )
    assert registry_materializer.is_file(), (
        "Registry compatibility producer is required for the cross-repository "
        f"release-contract test: {registry_materializer}"
    )
    registry_spec = importlib.util.spec_from_file_location(
        "registry_release_materializer_for_preflight_test",
        registry_materializer,
    )
    assert registry_spec is not None and registry_spec.loader is not None
    registry_module = importlib.util.module_from_spec(registry_spec)
    registry_spec.loader.exec_module(registry_module)

    canonical = manifest()
    compatibility = registry_module.compatibility_payload(canonical)

    assert MODULE.artifact_inventory(compatibility) == MODULE.artifact_inventory(canonical)


def first_pass_reuse_fixture(tmp_path: Path) -> tuple[dict, dict]:
    candidate = tmp_path / "candidate"
    test_project = candidate / "Chummer.Tests" / "Chummer.Tests.csproj"
    test_project.parent.mkdir(parents=True)
    test_project.write_text("<Project />", encoding="utf-8")
    first_output = tmp_path / "first-pass"
    for name in (
        "dotnet-artifacts",
        "nuget-packages",
        "dotnet-home",
        "nuget-http-cache",
        "nuget-plugins-cache",
        "tmp",
        "logs",
    ):
        (first_output / name).mkdir(parents=True)
    first_fixtures = first_output / "tests" / "fixtures"
    first_fixtures.mkdir(parents=True)
    first_compose = first_output / "docker-compose.public-edge.yml"
    first_compose.write_text("services: {}\n", encoding="utf-8")
    projection_root = first_output / "source-projection"
    (
        projection_workspace,
        projection_candidate,
        projection_media,
        _,
    ) = MODULE._source_projection_roots(projection_root)
    projection_test_project = (
        projection_candidate / "Chummer.Tests" / "Chummer.Tests.csproj"
    )
    projection_test_project.parent.mkdir(parents=True)
    projection_test_project.write_text("<Project />", encoding="utf-8")
    publish = first_output / "publish"
    postgres_tool = first_output / "postgres-tool"
    build_info = (
        publish
        / ".codex-studio"
        / "runtime"
        / "PUBLIC_EDGE_PORTAL_OVERLAY_BUILD_INFO.generated.json"
    )
    build_info.parent.mkdir(parents=True)
    build_info.write_text('{"status":"pass"}\n', encoding="utf-8")
    (publish / "Chummer.Run.Api.dll").write_bytes(b"portal")
    postgres_tool.mkdir(parents=True)
    (postgres_tool / "Chummer.InstallLinking.Postgres.Tool.dll").write_bytes(b"tool")
    build_closure = MODULE.build_output_closure(publish, postgres_tool)
    source_closure = {"closureSha256": "1" * 64}
    source_projection_manifest = {
        "schemaVersion": MODULE.SOURCE_PROJECTION_SCHEMA,
        "closureSha256": "9" * 64,
        "sourceClosureSha256": source_closure["closureSha256"],
        "fileCount": 4,
        "totalBytes": 84,
    }
    source_projection = MODULE.SourceProjection(
        root=projection_root,
        workspace_root=projection_workspace,
        candidate_root=projection_candidate,
        media_factory_root=projection_media,
        manifest=source_projection_manifest,
        omitted_symlinks=(),
    )
    tooling_closure = {"closureSha256": "2" * 64, "fileCount": 3}
    candidate_identity = {
        "path": str(candidate),
        "head": "3" * 40,
        "statusSha256": "4" * 64,
        "dirty": True,
        "expectedBase": "3" * 40,
        "baseMatches": True,
    }
    required_paths = {"writer": True, "truthTests": True}
    live_envelope = {
        "passed": True,
        "binding": "exact",
        "bindingSha256": "a" * 64,
    }
    snapshot_bytes = {
        "receipt": ("verification.receipt.json", b'{"receipt":true}\n'),
        "canonical": (MODULE.CANONICAL, b'{"canonical":true}\n'),
        "compatibility": (MODULE.COMPATIBILITY, b'{"compatibility":true}\n'),
    }

    def create_live_snapshot(root: Path) -> object:
        root.mkdir(parents=True)
        snapshots = {}
        for label, (name, raw) in snapshot_bytes.items():
            path = root / name
            path.write_bytes(raw)
            path.chmod(0o400)
            snapshots[label] = MODULE.JsonByteSnapshot(
                label=label,
                source_path=path,
                retained_path=path,
                raw=raw,
                sha256=MODULE.sha256_bytes(raw),
                payload=json.loads(raw),
            )
        return MODULE.LiveEnvelopeSnapshot(
            root=root,
            receipt=snapshots["receipt"],
            canonical=snapshots["canonical"],
            compatibility=snapshots["compatibility"],
            closure=MODULE.build_live_envelope_snapshot_closure(root),
        )

    first_live_envelope_snapshot = create_live_snapshot(
        first_output / "live-envelope-snapshot"
    )
    live_envelope_snapshot = create_live_snapshot(
        tmp_path / "second-pass" / "live-envelope-snapshot"
    )
    dotnet_root = tmp_path / "dotnet-root"
    dotnet_root.mkdir()
    dotnet_host = dotnet_root / "dotnet"
    dotnet_host.write_bytes(b"dotnet-host")
    dotnet_execution = MODULE.DotnetExecution(
        host=dotnet_host,
        host_sha256=MODULE.sha256_file(dotnet_host),
        root=dotnet_root,
        toolchain_closure={
            "closureSha256": "d" * 64,
            "fileCount": 1,
            "totalBytes": len(b"dotnet-host"),
        },
        python_host=Path(sys.executable),
        python_host_sha256=MODULE.sha256_file(Path(sys.executable)),
        landlock_launcher=(
            projection_candidate / "scripts" / "release" / "landlock_exec.py"
        ),
        seccomp_library=SECCOMP_LIBRARY,
        landlock_abi=4,
    )
    system_tools = MODULE.PinnedSystemTools(
        git=Path("/usr/bin/git"),
        git_sha256="1" * 64,
        docker=Path("/usr/bin/docker"),
        docker_sha256="2" * 64,
        docker_socket=MODULE.LOCAL_DOCKER_SOCKET,
        docker_socket_identity=MODULE.docker_socket_identity()[1],
        openssl=Path("/usr/bin/openssl"),
        openssl_sha256="3" * 64,
        seccomp_library=SECCOMP_LIBRARY,
        seccomp_library_sha256="4" * 64,
    )
    image_id = "sha256:" + "5" * 64
    test_projection = {
        "passed": True,
        "productionMutation": False,
        "closureSha256": "6" * 64,
        "fileCount": 2,
        "totalBytes": 42,
        "composePath": str(tmp_path / "second-pass" / "docker-compose.public-edge.yml"),
        "fixturesRoot": str(tmp_path / "second-pass" / "tests" / "fixtures"),
    }
    command_rows = []
    for name, argv in MODULE.first_pass_command_contract(
        projection_candidate,
        first_output,
        publish,
        postgres_tool,
        dotnet_execution,
    ):
        command_rows.append(
            {
                "name": name,
                "argv": list(argv),
                "cwd": str(projection_candidate),
                "exitCode": 0,
                "passed": True,
                "durationSeconds": 1.25,
                "stdoutSha256": "7" * 64,
                "stderrSha256": "8" * 64,
                "stdoutTail": MODULE.OUTPUT_WITHHELD,
                "stderrTail": MODULE.OUTPUT_WITHHELD,
            }
        )
    mutation_monitors = [
        {
            "command": name,
            "roots": [
                str(projection_root),
                str(first_output / "live-envelope-snapshot"),
                str(first_compose),
                str(first_fixtures),
            ],
            "watchCount": 1,
            "mutationEventCount": 0,
            "queueOverflow": False,
            "monitorErrors": [],
            "passed": True,
        }
        for name in MODULE.FIRST_PASS_COMMAND_NAMES
    ]
    rollback_primitive = "fsync temporary current.json then os.replace and parent fsync"
    receipt = {
        "schemaVersion": MODULE.SCHEMA,
        "state": "completed",
        "decision": "no-go",
        "startedAt": "2026-07-16T12:00:00Z",
        "completedAt": "2026-07-16T12:10:00Z",
        "productionMutation": False,
        "networkScope": MODULE.NETWORK_SCOPE,
        "candidate": candidate_identity,
        "requiredCandidatePaths": required_paths,
        "sourceClosure": {
            "path": str(first_output / "source-closure.json"),
            "sha256": source_closure["closureSha256"],
            "expectedSha256": source_closure["closureSha256"],
            "operatorPinned": True,
            "stableThroughRuntimeAndRollback": True,
            "afterBuildSha256": source_closure["closureSha256"],
            "finalSha256": source_closure["closureSha256"],
        },
        "sourceProjection": MODULE.source_projection_receipt_evidence(
            source_projection,
            manifest_path=first_output / "source-projection-closure.json",
            after_build_sha256=source_projection_manifest["closureSha256"],
            final_sha256=source_projection_manifest["closureSha256"],
            stable=True,
            mutation_monitors=mutation_monitors,
        ),
        "toolingClosure": {
            "path": str(first_output / "tooling-closure.json"),
            "sha256": tooling_closure["closureSha256"],
            "fileCount": tooling_closure["fileCount"],
            "finalSha256": tooling_closure["closureSha256"],
            "stableThroughRuntimeAndRollback": True,
        },
        "systemTools": MODULE.system_tools_receipt(system_tools),
        "dotnetToolchain": MODULE.dotnet_toolchain_receipt(dotnet_execution),
        "buildClosure": {
            "path": str(first_output / "build-closure.json"),
            "sha256": build_closure["closureSha256"],
            "fileCount": build_closure["fileCount"],
            "totalBytes": build_closure["totalBytes"],
            "expectedSha256": None,
            "operatorPinned": False,
            "portalRoot": str(publish),
            "postgresToolRoot": str(postgres_tool),
        },
        "liveEnvelope": live_envelope,
        "liveEnvelopeSnapshot": MODULE.live_envelope_snapshot_receipt_evidence(
            first_live_envelope_snapshot,
            live_envelope,
            stable=True,
        ),
        "postgresImage": {"reference": MODULE.POSTGRES_IMAGE, "expectedImageId": image_id},
        "commands": command_rows,
        "testSourceProjection": {
            "passed": True,
            "productionMutation": False,
            "closureSha256": test_projection["closureSha256"],
            "fileCount": test_projection["fileCount"],
            "totalBytes": test_projection["totalBytes"],
            "composePath": str(first_output / "docker-compose.public-edge.yml"),
            "fixturesRoot": str(first_output / "tests" / "fixtures"),
        },
        "reusedBuildEvidence": None,
        "runtimeBuildProjection": None,
        "runtime": {
            "passed": False,
            "skipped": True,
            "reason": "build_closure_not_operator_pinned",
        },
        "overlayIdentity": {
            "passed": True,
            "path": str(build_info),
            "sha256": MODULE.sha256_file(build_info),
        },
        "rollbackProbe": {
            "passed": True,
            "productionMutation": False,
            "atomicCommitPrimitive": rollback_primitive,
            "generationA": "preflight-generation-a",
            "generationB": "preflight-generation-b",
            "observedAfterActivation": "preflight-generation-b",
            "observedAfterRollback": "preflight-generation-a",
            "observedAfterRestore": "preflight-generation-b",
            "generationABytesUnchanged": True,
            "generationAClosureSha256Before": "d" * 64,
            "generationAClosureSha256AfterActivation": "d" * 64,
            "generationAClosureSha256AfterRollback": "d" * 64,
            "pointerASha256": "e" * 64,
            "pointerBSha256": "f" * 64,
        },
        "gates": dict(MODULE.FIRST_PASS_GATE_CONTRACT),
        "reasons": list(MODULE.FIRST_PASS_REASON_CONTRACT),
        "rollbackPlan": {
            "activationAuthorized": False,
            "candidateBuildSha256": build_closure["closureSha256"],
            "restorePrimitive": "content-addressed rollback",
            "releaseShelfPrimitive": rollback_primitive,
            "productionTargetCaptured": False,
        },
    }
    context = {
        "evidence_path": first_output / "preflight.receipt.json",
        "candidate_root": candidate,
        "candidate_identity": candidate_identity,
        "required_paths": required_paths,
        "source_closure": source_closure,
        "source_projection": source_projection,
        "tooling_closure": tooling_closure,
        "system_tools": system_tools,
        "build_closure": build_closure,
        "expected_build_sha256": build_closure["closureSha256"],
        "publish_root": publish,
        "postgres_tool_root": postgres_tool,
        "test_source_projection": test_projection,
        "live_envelope": live_envelope,
        "live_envelope_snapshot": live_envelope_snapshot,
        "dotnet_execution": dotnet_execution,
        "expected_postgres_image_id": image_id,
    }
    return receipt, context


def test_truth_floor_requires_all_top_and_nested_states() -> None:
    payload = manifest()
    assert MODULE.trust_floor_passes(payload)

    payload["registryBoundaryCoverage"]["releaseChannel"]["publicTrustPosture"] = "preview"
    assert not MODULE.trust_floor_passes(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("status", "revoked"),
        ("channelRevoked", True),
        ("activeRevocationCount", 1),
        ("activeRevocationCount", False),
        ("activeRevocations", [{"artifactId": "a"}]),
        ("summary", "No active revocations."),
    ),
)
def test_revocation_facts_cannot_contradict_published_release(
    field: str,
    value: object,
) -> None:
    payload = manifest()
    payload["publicTrustMetrics"]["revocationFacts"][field] = value

    assert not MODULE.trust_floor_passes(payload)
    with pytest.raises(MODULE.PreflightError, match="revocation facts contradict"):
        MODULE.template_manifest_binding(payload)


def test_parity_binds_revocation_facts() -> None:
    canonical = manifest()
    compatibility = compatibility_manifest(canonical)
    compatibility["publicTrustMetrics"]["revocationFacts"]["channelRevoked"] = True

    with pytest.raises(MODULE.PreflightError, match="revocation facts contradict"):
        MODULE.parity_result(canonical, compatibility)


@pytest.mark.parametrize(
    ("path", "value"),
    (
        (("publicTrustMetrics", "releaseChannel", "channelId"), "stable"),
        (("publicTrustMetrics", "releaseChannel", "publicationStatus"), "revoked"),
        (("publicTrustMetrics", "releaseChannel", "recommendedRouteCount"), 1),
        (("publicTrustMetrics", "releaseChannel", "blockedRouteCount"), 0),
        (("publicTrustMetrics", "releaseChannel", "revokedRouteCount"), 1),
        (("publicTrustMetrics", "releaseChannel", "fallbackRecoveryRouteCount"), 1),
        (("registryBoundaryCoverage", "status"), "open"),
        (("registryBoundaryCoverage", "owner"), "untrusted-writer"),
        (("registryBoundaryCoverage", "channelId"), "stable"),
        (("registryBoundaryCoverage", "releaseVersion"), "release-b"),
    ),
)
def test_release_channel_authority_must_match_identity_and_route_truth(
    path: tuple[str, ...],
    value: object,
) -> None:
    payload = manifest()
    target = payload
    for segment in path[:-1]:
        target = target[segment]
    target[path[-1]] = value

    assert not MODULE.trust_floor_passes(payload)
    with pytest.raises(MODULE.PreflightError, match="release-channel authority conflicts"):
        MODULE.template_manifest_binding(payload)


@pytest.mark.parametrize(
    ("path", "value"),
    (
        (("rolloutReason",), "Current release shelf passed the local release run."),
        (("supportabilitySummary",), "Current preview release is supported."),
        (
            ("publicTrustMetrics", "releaseChannel", "summary"),
            "The current preview is supported.",
        ),
        (
            ("registryBoundaryCoverage", "releaseChannel", "summary"),
            "Registry truth reports a supported preview.",
        ),
    ),
)
def test_truth_floor_rejects_optimistic_narratives(
    path: tuple[str, ...],
    value: str,
) -> None:
    payload = manifest()
    target = payload
    for segment in path[:-1]:
        target = target[segment]
    target[path[-1]] = value

    assert not MODULE.trust_floor_passes(payload)


@pytest.mark.parametrize(
    "value",
    (
        "This release is not review-required and launch ready.",
        "Stale or incomplete proof receipts are irrelevant; this release is not "
        "review-required and launch ready.",
    ),
)
def test_truth_floor_rejects_negated_or_launch_ready_narratives(value: str) -> None:
    payload = manifest()
    payload["rolloutReason"] = value

    assert not MODULE.trust_floor_passes(payload)


def test_parity_requires_identity_trust_and_artifact_inventory() -> None:
    canonical = manifest()
    compatibility = json.loads(json.dumps(canonical))
    compatibility["downloads"] = [
        {
            "id": "a",
            "fileName": "a.bin",
            "url": "/downloads/g/generation-a/files/a.bin",
            "sha256": FIXTURE_ARTIFACT_SHA256,
            "sizeBytes": 1,
            "installAccessClass": "open_public",
            "kind": "installer",
            "head": "a",
            "arch": "x64",
            "platform": "desktop",
            "rid": "test-x64",
            "compatibilityState": "compatible",
            "compatibilityReason": None,
        }
    ]
    compatibility.pop("artifacts")

    assert MODULE.parity_result(canonical, compatibility)["passed"]
    compatibility["supportabilityState"] = "preview_supported"
    assert not MODULE.parity_result(canonical, compatibility)["passed"]


def test_served_manifest_binding_requires_exact_generation_and_prepared_inventory() -> None:
    payload = manifest()
    expected = MODULE.prepared_manifest_binding(payload)
    headers = {"x-chummer-release-generation": ("generation-a",)}

    evidence = MODULE.served_manifest_binding_evidence(
        payload,
        headers,
        "generation-a",
        expected,
    )

    assert evidence["passed"]
    wrong_generation = MODULE.served_manifest_binding_evidence(
        payload,
        {"x-chummer-release-generation": ("generation-b",)},
        "generation-a",
        expected,
    )
    assert not wrong_generation["passed"]
    duplicate_generation = MODULE.served_manifest_binding_evidence(
        payload,
        {"x-chummer-release-generation": ("generation-a", "generation-a")},
        "generation-a",
        expected,
    )
    assert not duplicate_generation["passed"]
    assert not MODULE.served_manifest_binding_evidence(
        payload,
        {},
        "generation-a",
        expected,
    )["passed"]
    assert not MODULE.served_manifest_binding_evidence(
        payload,
        {"x-chummer-release-generation": ("generation-a,generation-a",)},
        "generation-a",
        expected,
    )["passed"]
    identity_drift = copy.deepcopy(payload)
    identity_drift["version"] = "release-b"
    identity_evidence = MODULE.served_manifest_binding_evidence(
        identity_drift,
        headers,
        "generation-a",
        expected,
    )
    assert not identity_evidence["identityAliasesConsistent"]
    assert not identity_evidence["artifactInventoryExact"]
    assert not identity_evidence["immutableProjectionExact"]
    assert not identity_evidence["passed"]
    substituted = copy.deepcopy(payload)
    substituted["artifacts"][0]["sha256"] = "b" * 64
    wrong_inventory = MODULE.served_manifest_binding_evidence(
        substituted,
        headers,
        "generation-a",
        expected,
    )
    assert not wrong_inventory["passed"]
    missing_body_generation = copy.deepcopy(payload)
    missing_body_generation.pop("generationId")
    assert not MODULE.served_manifest_binding_evidence(
        missing_body_generation,
        headers,
        "generation-a",
        expected,
    )["passed"]
    wrong_body_generation = copy.deepcopy(payload)
    wrong_body_generation["generationId"] = "generation-b"
    assert not MODULE.served_manifest_binding_evidence(
        wrong_body_generation,
        headers,
        "generation-a",
        expected,
    )["passed"]


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("artifactId", "substituted"),
        ("fileName", "substituted.bin"),
        ("sha256", "b" * 64),
        ("sizeBytes", 2),
        ("downloadUrl", "/downloads/g/generation-a/files/substituted.bin"),
        ("installAccessClass", "account_required"),
        ("kind", "archive"),
        ("head", "other"),
        ("arch", "arm64"),
        ("platform", "mobile"),
        ("rid", "other-rid"),
    ),
)
def test_served_manifest_binding_rejects_every_inventory_field_drift(
    field: str,
    value: object,
) -> None:
    expected_payload = manifest()
    expected = MODULE.prepared_manifest_binding(expected_payload)
    observed = copy.deepcopy(expected_payload)
    observed["artifacts"][0][field] = value

    evidence = MODULE.served_manifest_binding_evidence(
        observed,
        {"x-chummer-release-generation": ("generation-a",)},
        "generation-a",
        expected,
    )

    assert not evidence["artifactInventoryExact"]
    assert not evidence["passed"]


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("releaseVersion", "release-b"),
        ("channelId", "stable"),
        ("generatedAt", "2026-07-16T13:00:00Z"),
        ("generated_at", "2026-07-16T13:00:00Z"),
    ),
)
def test_prepared_manifest_binding_rejects_conflicting_identity_aliases(
    field: str,
    value: str,
) -> None:
    payload = manifest()
    payload[field] = value

    with pytest.raises(MODULE.PreflightError, match="identity aliases conflict"):
        MODULE.prepared_manifest_binding(payload)


@pytest.mark.parametrize("field", ("contractName", "contract_name"))
def test_prepared_manifest_binding_rejects_contract_alias_drift(field: str) -> None:
    payload = manifest()
    payload[field] = "Untrusted.Registry.Contracts"

    with pytest.raises(MODULE.PreflightError, match="contract-name aliases"):
        MODULE.prepared_manifest_binding(payload)


@pytest.mark.parametrize(
    "mutation",
    (
        "status",
        "base-url",
        "journey-order",
        "route-order",
        "forbidden-route",
        "missing-artifact-route",
        "duplicate-route",
        "generated-at",
        "localization-status",
        "localization-generated-at",
    ),
)
def test_release_proof_must_match_registry_and_artifact_contract(
    mutation: str,
) -> None:
    payload = manifest()
    proof = payload["releaseProof"]
    if mutation == "status":
        proof["status"] = "unknown"
    elif mutation == "base-url":
        proof["baseUrl"] = "https://example.invalid"
    elif mutation == "journey-order":
        proof["journeysPassed"][0], proof["journeysPassed"][1] = (
            proof["journeysPassed"][1],
            proof["journeysPassed"][0],
        )
    elif mutation == "route-order":
        proof["proofRoutes"][0], proof["proofRoutes"][1] = (
            proof["proofRoutes"][1],
            proof["proofRoutes"][0],
        )
    elif mutation == "forbidden-route":
        proof["proofRoutes"].append("/account/roster")
    elif mutation == "missing-artifact-route":
        proof["proofRoutes"].remove("/downloads/install/a")
    elif mutation == "duplicate-route":
        proof["proofRoutes"].append("/downloads/install/a")
    elif mutation == "generated-at":
        proof["generatedAt"] = "2026-07-16T11:59:00"
    elif mutation == "localization-status":
        proof["uiLocalizationReleaseGate"]["status"] = "fail"
    else:
        proof["uiLocalizationReleaseGate"]["generatedAt"] = (
            "2026-07-16T11:59:30"
        )

    assert not MODULE.trust_floor_passes(payload)
    with pytest.raises(MODULE.PreflightError, match="release proof"):
        MODULE.template_manifest_binding(payload)


def test_release_proof_parity_normalizes_equivalent_utc_timestamp_forms() -> None:
    canonical = manifest()
    compatibility = compatibility_manifest(canonical)
    compatibility["releaseProof"]["generatedAt"] = "2026-07-16T11:59:00+00:00"
    compatibility["releaseProof"]["uiLocalizationReleaseGate"]["generatedAt"] = (
        "2026-07-16T11:59:30+00:00"
    )

    assert MODULE.parity_result(canonical, compatibility)["passed"]


@pytest.mark.parametrize(
    "published_at",
    (
        "definitely-not-a-timestamp",
        "2026-07-16T12:00:00",
        " 2026-07-16T12:00:00Z",
    ),
)
def test_prepared_manifest_binding_requires_timezone_aware_publication_timestamp(
    published_at: str,
) -> None:
    payload = manifest()
    payload["publishedAt"] = published_at

    with pytest.raises(MODULE.PreflightError, match="publication timestamp"):
        MODULE.prepared_manifest_binding(payload)


@pytest.mark.parametrize("status", (None, "revoked", "unpublished"))
def test_prepared_manifest_binding_requires_published_status(status: object) -> None:
    payload = manifest()
    if status is None:
        payload.pop("status")
    else:
        payload["status"] = status

    with pytest.raises(MODULE.PreflightError, match="publication status"):
        MODULE.prepared_manifest_binding(payload)


def test_prepared_manifest_binding_rejects_unbound_desktop_tuple_counts() -> None:
    payload = manifest()
    channel = payload["registryBoundaryCoverage"]["releaseChannel"]
    channel["promotedInstallerTupleCount"] = 999
    channel["desktopRouteTruthCount"] = 888
    channel["summary"] = (
        "Release-channel truth for preview/release-a keeps 999 promoted installer tuples and "
        "888 explicit desktop route-truth rows while rollout remains "
        "public_release_review_required and public trust is blocked."
    )

    with pytest.raises(MODULE.PreflightError, match="conflict"):
        MODULE.prepared_manifest_binding(payload)


def test_prepared_manifest_binding_binds_coverage_into_immutable_projection() -> None:
    expected_payload = manifest()
    expected = MODULE.prepared_manifest_binding(expected_payload)
    observed = copy.deepcopy(expected_payload)
    observed["desktopTupleCoverage"]["promotedInstallerTuples"][0][
        "tupleId"
    ] = "rewritten:desktop:test-x64"
    observed["desktopTupleCoverage"]["desktopRouteTruth"][0][
        "tupleId"
    ] = "rewritten:desktop:test-x64"

    evidence = MODULE.served_manifest_binding_evidence(
        observed,
        {"x-chummer-release-generation": ("generation-a",)},
        "generation-a",
        expected,
    )

    assert not evidence["immutableProjectionExact"]
    assert not evidence["passed"]


def test_prepared_manifest_binding_requires_canonical_tuple_ids() -> None:
    payload = manifest()
    payload["desktopTupleCoverage"]["promotedInstallerTuples"][0][
        "tupleId"
    ] = "totally-wrong"
    payload["desktopTupleCoverage"]["desktopRouteTruth"][0][
        "tupleId"
    ] = "totally-wrong"

    with pytest.raises(MODULE.PreflightError, match="identity conflicts"):
        MODULE.prepared_manifest_binding(payload)


def test_desktop_tuple_coverage_rejects_cross_artifact_substitution() -> None:
    payload = manifest()
    second = copy.deepcopy(payload["artifacts"][0])
    second.update(
        {
            "artifactId": "b",
            "fileName": "b.bin",
            "downloadUrl": "/downloads/g/generation-a/files/b.bin",
            "head": "b",
        }
    )
    payload["artifacts"].append(second)
    route = payload["desktopTupleCoverage"]["desktopRouteTruth"][0]
    route["artifactId"] = "b"
    route["head"] = "b"

    with pytest.raises(MODULE.PreflightError, match="conflicts"):
        MODULE.prepared_manifest_binding(payload)


def test_desktop_tuple_coverage_requires_installer_artifact_kind() -> None:
    payload = manifest()
    payload["artifacts"][0]["kind"] = "archive"

    with pytest.raises(MODULE.PreflightError, match="coverage counts or rows conflict"):
        MODULE.prepared_manifest_binding(payload)


@pytest.mark.parametrize("collision", ("artifactId", "fileName", "downloadUrl"))
def test_artifact_inventory_rejects_ambiguous_identity_collisions(
    collision: str,
) -> None:
    payload = manifest()
    first = payload["artifacts"][0]
    second = copy.deepcopy(first)
    second.update(
        {
            "artifactId": "b",
            "fileName": "b.bin",
            "downloadUrl": "/downloads/g/generation-a/files/b.bin",
            "head": "b",
        }
    )
    second[collision] = first[collision]
    payload["artifacts"].append(second)

    with pytest.raises(
        MODULE.PreflightError,
        match="malformed|ambiguous id, file name, or URL",
    ):
        MODULE.artifact_inventory(payload)


def test_prepared_manifest_binding_accepts_equivalent_timestamp_aliases() -> None:
    payload = manifest()
    payload["generatedAt"] = "2026-07-16T12:00:00+00:00"

    assert MODULE.prepared_manifest_binding(payload)["identityAliasesConsistent"]


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("releaseVersion", None),
        ("releaseVersion", " release-a"),
        ("channelId", None),
        ("channelId", "preview "),
        ("generatedAt", None),
        ("generatedAt", " 2026-07-16T12:00:00Z"),
        ("generationId", " generation-a "),
    ),
)
def test_prepared_manifest_binding_rejects_null_or_padded_aliases(
    field: str,
    value: object,
) -> None:
    payload = manifest()
    payload[field] = value

    with pytest.raises(MODULE.PreflightError):
        MODULE.prepared_manifest_binding(payload)


def test_artifact_inventory_rejects_conflicting_aliases_and_collections() -> None:
    conflicting_id = manifest()
    conflicting_id["artifacts"][0]["id"] = "different"
    with pytest.raises(MODULE.PreflightError, match="artifact inventory row is malformed"):
        MODULE.artifact_inventory(conflicting_id)

    conflicting_url = manifest()
    conflicting_url["artifacts"][0]["url"] = "/downloads/g/generation-a/files/other.bin"
    with pytest.raises(MODULE.PreflightError, match="artifact inventory row is malformed"):
        MODULE.artifact_inventory(conflicting_url)

    dual_collection = manifest()
    dual_collection["downloads"] = []
    with pytest.raises(MODULE.PreflightError, match="simultaneous"):
        MODULE.artifact_inventory(dual_collection)


@pytest.mark.parametrize(
    "mutate",
    (
        lambda payload: payload.update(downloads={"malformed": True}),
        lambda payload: payload.update(artifacts={"malformed": True}),
        lambda payload: payload["artifacts"][0].update(id=None),
        lambda payload: payload["artifacts"][0].update(url=None),
        lambda payload: payload["artifacts"][0].update(
            url=" /downloads/g/generation-a/files/a.bin "
        ),
        lambda payload: payload["artifacts"][0].update(artifactId=" a "),
        lambda payload: payload["artifacts"][0].update(fileName=" a.bin "),
        lambda payload: payload["artifacts"][0].update(sha256="A" * 64),
    ),
)
def test_artifact_inventory_rejects_malformed_shape_null_aliases_and_padding(
    mutate,
) -> None:
    payload = manifest()
    mutate(payload)

    with pytest.raises(MODULE.PreflightError):
        MODULE.artifact_inventory(payload)


@pytest.mark.parametrize(
    "url",
    (
        "/downloads/g/generation-a/files/a.bin?ticket=secret",
        "/downloads/g/generation-a/files/a.bin#fragment",
        " /downloads/g/generation-a/files/a.bin",
    ),
)
def test_artifact_inventory_rejects_noncanonical_urls(url: str) -> None:
    payload = manifest()
    payload["artifacts"][0]["downloadUrl"] = url

    with pytest.raises(MODULE.PreflightError, match="artifact inventory row is malformed"):
        MODULE.artifact_inventory(payload)


def test_source_closure_is_order_stable_and_content_addressed(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    (first / "z.txt").write_text("z", encoding="utf-8")
    (first / "a.txt").write_text("a", encoding="utf-8")
    (second / "x.txt").write_text("x", encoding="utf-8")

    one = MODULE.build_closure_manifest(
        MODULE.SOURCE_CLOSURE_SCHEMA,
        (("first", first), ("second", second)),
    )
    two = MODULE.build_closure_manifest(
        MODULE.SOURCE_CLOSURE_SCHEMA,
        (("second", second), ("first", first)),
    )
    assert one["closureSha256"] == two["closureSha256"]

    (first / "a.txt").write_text("changed", encoding="utf-8")
    changed = MODULE.build_closure_manifest(
        MODULE.SOURCE_CLOSURE_SCHEMA,
        (("first", first), ("second", second)),
    )
    assert one["closureSha256"] != changed["closureSha256"]


def test_source_closure_rejects_symlinks(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    target = tmp_path / "target"
    target.write_text("target", encoding="utf-8")
    (root / "link").symlink_to(target)

    with pytest.raises(MODULE.PreflightError, match="symbolic link"):
        MODULE.build_closure_manifest(MODULE.SOURCE_CLOSURE_SCHEMA, (("root", root),))


def test_optimistic_fixture_never_mutates_source(tmp_path: Path) -> None:
    source = tmp_path / "source.json"
    destination = tmp_path / "copy.json"
    payload = manifest()
    source.write_text(json.dumps(payload), encoding="utf-8")
    before = source.read_bytes()

    projected = MODULE.make_optimistic_copy(source, destination)

    assert source.read_bytes() == before
    assert projected["supportabilityState"] == "preview_supported"
    assert projected["publicTrustMetrics"]["proofFreshness"]["status"] == "stale"
    assert destination.is_file()


def test_atomic_json_writer_replaces_complete_document(tmp_path: Path) -> None:
    path = tmp_path / "receipt.json"
    MODULE.atomic_write_json(path, {"state": "first"})
    MODULE.atomic_write_json(path, {"state": "second", "complete": True})

    assert json.loads(path.read_text(encoding="utf-8")) == {
        "state": "second",
        "complete": True,
    }


def test_production_loopback_origin_is_https_and_explicitly_allows_probe_host() -> None:
    settings = MODULE.production_loopback_origin_settings()

    assert settings["CHUMMER_PUBLIC_CANONICAL_ORIGIN"] == "https://chummer.run"
    assert set(settings["CHUMMER_PUBLIC_ALLOWED_HOSTS"].split(";")) == {
        "chummer.run",
        "127.0.0.1",
    }


def test_truth_test_command_uses_integrated_writer_matrix(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    project = candidate / "Chummer.Tests" / "Chummer.Tests.csproj"
    project.parent.mkdir(parents=True)
    project.write_text("<Project />", encoding="utf-8")

    dotnet = Path("/trusted/dotnet")
    selected, argv = MODULE.truth_test_command(candidate, dotnet)

    assert selected == project
    assert "--framework" in argv
    assert "net10.0" in argv
    assert "--filter" in argv
    assert MODULE.MAIN_TRUTH_TEST_FILTER in argv
    assert argv[0] == str(dotnet)
    assert "ReleaseBundlePromotionServiceTests" in MODULE.MAIN_TRUTH_TEST_FILTER
    assert "ReleaseShelfGenerationStoreTests" in MODULE.MAIN_TRUTH_TEST_FILTER


def test_truth_test_command_prefers_sealed_focused_project(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    integrated = candidate / "Chummer.Tests" / "Chummer.Tests.csproj"
    focused = candidate / "tests" / "CanonicalManifestTruth.Tests" / "CanonicalManifestTruth.Tests.csproj"
    integrated.parent.mkdir(parents=True)
    focused.parent.mkdir(parents=True)
    integrated.write_text("<Project />", encoding="utf-8")
    focused.write_text("<Project />", encoding="utf-8")

    selected, argv = MODULE.truth_test_command(candidate, Path("/trusted/dotnet"))

    assert selected == focused
    assert "--filter" not in argv


def test_git_source_closure_tracks_untracked_source_and_deletions_without_operational_links(
    tmp_path: Path,
) -> None:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    subprocess.run(("git", "init", "-q", str(candidate)), check=True)
    tracked = candidate / "tracked.cs"
    tracked.write_text("tracked", encoding="utf-8")
    design_contract = candidate / ".codex-design" / "product" / "contract.json"
    design_contract.parent.mkdir(parents=True)
    design_contract.write_text('{"status":"review_required"}', encoding="utf-8")
    subprocess.run(
        ("git", "-C", str(candidate), "add", "tracked.cs", ".codex-design/product/contract.json"),
        check=True,
    )
    tracked.unlink()
    (candidate / "new-source.cs").write_text("new", encoding="utf-8")
    operational = candidate / ".codex-studio" / "out"
    operational.mkdir(parents=True)
    (operational / "current").symlink_to(candidate / "new-source.cs")

    closure = MODULE.build_source_closure_manifest(candidate, ())
    rows = {row["path"]: row for row in closure["files"]}

    assert rows["chummer-run-services/tracked.cs"]["state"] == "deleted"
    assert rows["chummer-run-services/new-source.cs"]["state"] == "present"
    assert rows["chummer-run-services/.codex-design/product/contract.json"]["state"] == "present"
    assert not any(".codex-studio" in path for path in rows)


def _source_projection_test_roots(tmp_path: Path) -> tuple[Path, Path, Path]:
    workspace = tmp_path / "chummercomplete"
    candidate = workspace / "chummer.run-services"
    media = tmp_path / "fleet" / "repos" / "chummer-media-factory"
    roots = (
        candidate,
        workspace / "chummer-core-engine",
        workspace / "chummer-hub-registry",
        media,
    )
    for root in roots:
        root.mkdir(parents=True)
        subprocess.run(("git", "init", "-q", str(root)), check=True)
        marker = root / "tracked.txt"
        marker.write_text(root.name, encoding="utf-8")
        subprocess.run(("git", "-C", str(root), "add", marker.name), check=True)
    return candidate, workspace, media


def test_source_projection_excludes_ignored_inputs_and_binds_copied_bytes(
    tmp_path: Path,
) -> None:
    candidate, workspace, media = _source_projection_test_roots(tmp_path)
    (candidate / ".gitignore").write_text("ignored.cs\n", encoding="utf-8")
    (candidate / "ignored.cs").write_text("ambient", encoding="utf-8")
    subprocess.run(("git", "-C", str(candidate), "add", ".gitignore"), check=True)
    closure = MODULE.build_source_closure_manifest(
        candidate,
        (),
        (
            ("chummer-core-engine", workspace / "chummer-core-engine"),
            ("chummer-hub-registry", workspace / "chummer-hub-registry"),
            ("media-factory", media),
        ),
    )

    projection = MODULE.materialize_source_projection(
        closure,
        candidate_root=candidate,
        workspace_root=workspace,
        media_factory_root=media,
        projection_root=tmp_path / "projection",
    )

    assert (projection.candidate_root / "tracked.txt").is_file()
    assert not (projection.candidate_root / "ignored.cs").exists()
    assert projection.manifest["sourceClosureSha256"] == closure["closureSha256"]
    assert MODULE.owner_read_only_tree_passes(projection.root)
    with pytest.raises(PermissionError):
        (projection.candidate_root / "obj").mkdir()
    (candidate / "ignored.cs").write_text("changed ambient", encoding="utf-8")
    assert MODULE._projection_manifest(
        MODULE._source_projection_roots(projection.root)[3]
    )["closureSha256"] == projection.manifest["closureSha256"]


def test_source_projection_rejects_pinned_file_drift_and_omits_symlinks(
    tmp_path: Path,
) -> None:
    candidate, workspace, media = _source_projection_test_roots(tmp_path)
    link = media / "self"
    link.symlink_to(media, target_is_directory=True)
    subprocess.run(("git", "-C", str(media), "add", "self"), check=True)
    closure = MODULE.build_source_closure_manifest(
        candidate,
        (),
        (
            ("chummer-core-engine", workspace / "chummer-core-engine"),
            ("chummer-hub-registry", workspace / "chummer-hub-registry"),
            ("media-factory", media),
        ),
    )
    (candidate / "tracked.txt").write_text("drifted", encoding="utf-8")
    with pytest.raises(MODULE.PreflightError, match="drifted"):
        MODULE.materialize_source_projection(
            closure,
            candidate_root=candidate,
            workspace_root=workspace,
            media_factory_root=media,
            projection_root=tmp_path / "drifted-projection",
        )

    (candidate / "tracked.txt").write_text(candidate.name, encoding="utf-8")
    projection = MODULE.materialize_source_projection(
        closure,
        candidate_root=candidate,
        workspace_root=workspace,
        media_factory_root=media,
        projection_root=tmp_path / "clean-projection",
    )
    assert not (projection.media_factory_root / "self").exists()
    assert [row["path"] for row in projection.omitted_symlinks] == [
        "media-factory/self"
    ]


def test_runtime_build_projection_is_independent_content_exact_and_read_only(
    tmp_path: Path,
) -> None:
    publish = tmp_path / "first" / "publish"
    postgres_tool = tmp_path / "first" / "postgres-tool"
    (publish / "empty-runtime-directory").mkdir(parents=True)
    postgres_tool.mkdir(parents=True)
    portal_dll = publish / "Chummer.Run.Api.dll"
    tool_dll = postgres_tool / "Chummer.InstallLinking.Postgres.Tool.dll"
    portal_dll.write_bytes(b"portal")
    tool_dll.write_bytes(b"tool")
    source_closure = MODULE.build_output_closure(publish, postgres_tool)

    projection = MODULE.materialize_runtime_build_projection(
        publish,
        postgres_tool,
        source_closure,
        tmp_path / "second" / "runtime-build-projection",
    )

    projected_portal = projection.publish_root / portal_dll.name
    assert projection.independent_inodes
    assert projection.source_closure_sha256 == source_closure["closureSha256"]
    assert projection.content_sha256 == MODULE.closure_content_sha256(source_closure)
    assert MODULE.owner_read_only_tree_passes(projection.root)
    assert projected_portal.read_bytes() == b"portal"
    assert (
        projection.publish_root / "empty-runtime-directory"
    ).is_dir()
    assert portal_dll.stat().st_ino != projected_portal.stat().st_ino
    portal_dll.write_bytes(b"mutated-original")
    assert projected_portal.read_bytes() == b"portal"
    with pytest.raises(PermissionError):
        projected_portal.write_bytes(b"forged-runtime")
    assert MODULE.build_output_closure(
        projection.publish_root,
        projection.postgres_tool_root,
    )["closureSha256"] == projection.sealed_closure["closureSha256"]


def test_isolated_dotnet_argv_cannot_resolve_an_ambient_path_wrapper(
    tmp_path: Path,
) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    execution = MODULE.DotnetExecution(
        host=Path("/usr/lib/dotnet/dotnet"),
        host_sha256="a" * 64,
        root=Path("/usr/lib/dotnet"),
        toolchain_closure={"closureSha256": "b" * 64, "fileCount": 1, "totalBytes": 1},
        python_host=Path(sys.executable),
        python_host_sha256="c" * 64,
        landlock_launcher=LANDLOCK_EXEC,
        seccomp_library=SECCOMP_LIBRARY,
        landlock_abi=4,
    )

    argv = MODULE.isolated_dotnet_argv(
        execution,
        (str(execution.host), "--info"),
        (allowed,),
    )

    assert argv[0] == str(Path(sys.executable))
    assert argv[1] == str(LANDLOCK_EXEC)
    assert str(execution.host) in argv
    assert "dotnet" not in argv
    loopback_argv = MODULE.isolated_dotnet_argv(
        execution,
        (str(execution.host), "--info"),
        (allowed,),
        (15432,),
        (18443,),
    )
    assert ("--allow-connect-port", "15432") == tuple(
        loopback_argv[
            loopback_argv.index("--allow-connect-port") :
            loopback_argv.index("--allow-connect-port") + 2
        ]
    )
    assert ("--allow-bind-port", "18443") == tuple(
        loopback_argv[
            loopback_argv.index("--allow-bind-port") :
            loopback_argv.index("--allow-bind-port") + 2
        ]
    )


def test_dotnet_toolchain_closure_rejects_symlink_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    toolchain = tmp_path / "toolchain"
    toolchain.mkdir()
    target = toolchain / "target"
    target.write_bytes(b"pinned")
    link = toolchain / "link"
    link.symlink_to(target.name)
    original_lstat = Path.lstat
    link_samples = 0

    def root_owned_lstat(path: Path) -> SimpleNamespace:
        nonlocal link_samples
        metadata = original_lstat(path)
        ctime_ns = metadata.st_ctime_ns
        if path == link:
            link_samples += 1
            if link_samples > 1:
                ctime_ns += 1
        return SimpleNamespace(
            st_dev=metadata.st_dev,
            st_ino=metadata.st_ino,
            st_mode=metadata.st_mode,
            st_nlink=metadata.st_nlink,
            st_size=metadata.st_size,
            st_mtime_ns=metadata.st_mtime_ns,
            st_ctime_ns=ctime_ns,
            st_uid=0,
        )

    monkeypatch.setattr(Path, "lstat", root_owned_lstat)

    with pytest.raises(MODULE.PreflightError, match="changed while it was hashed"):
        MODULE.build_dotnet_toolchain_closure(toolchain)


def test_system_tools_are_absolute_root_owned_and_operator_pinned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PATH", "/home/tibor/.local/bin:/usr/bin:/bin")
    tools = MODULE.bind_system_tools(
        git=Path("/usr/bin/git"),
        expected_git_sha256=MODULE.sha256_file(Path("/usr/bin/git")),
        docker=Path("/usr/bin/docker"),
        expected_docker_sha256=MODULE.sha256_file(Path("/usr/bin/docker")),
        openssl=Path("/usr/bin/openssl"),
        expected_openssl_sha256=MODULE.sha256_file(Path("/usr/bin/openssl")),
        seccomp_library=SECCOMP_LIBRARY,
        expected_seccomp_library_sha256=MODULE.sha256_file(SECCOMP_LIBRARY),
    )

    assert tools.docker == Path("/usr/bin/docker")
    assert tools.docker_socket == MODULE.LOCAL_DOCKER_SOCKET
    assert stat.S_ISSOCK(tools.docker_socket.lstat().st_mode)
    docker_receipt = MODULE.system_tools_receipt(tools)["docker"]
    assert docker_receipt["endpoint"] == "unix:///run/docker.sock"
    assert docker_receipt["configRoot"] == "/nonexistent"
    assert MODULE.sanitized_environment()["PATH"] == "/usr/bin:/bin"
    with pytest.raises(MODULE.PreflightError, match="Docker host does not match"):
        MODULE.bind_system_tools(
            git=tools.git,
            expected_git_sha256=tools.git_sha256,
            docker=tools.docker,
            expected_docker_sha256="0" * 64,
            openssl=tools.openssl,
            expected_openssl_sha256=tools.openssl_sha256,
            seccomp_library=tools.seccomp_library,
            expected_seccomp_library_sha256=tools.seccomp_library_sha256,
        )


def test_docker_commands_ignore_ambient_context_and_bind_local_socket(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = tmp_path / "ambient-home"
    docker_config = home / ".docker"
    docker_config.mkdir(parents=True)
    (docker_config / "config.json").write_text(
        json.dumps({"currentContext": "remote-production"}),
        encoding="utf-8",
    )
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("DOCKER_HOST", "tcp://production.invalid:2376")
    captured: dict[str, object] = {}

    def fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess:
        captured["argv"] = tuple(argv)
        captured["environment"] = kwargs.get("env")
        return subprocess.CompletedProcess(argv, 0, stdout=b"owned\n", stderr=b"")

    monkeypatch.setattr(MODULE.subprocess, "run", fake_run)
    evidence: list[dict] = []

    assert MODULE._docker_resource_present(
        "container",
        "owned",
        docker_host=Path("/usr/bin/docker"),
        cwd=tmp_path,
        evidence=evidence,
        phase="ambient-context-test",
    )
    assert captured["argv"][:5] == (
        "/usr/bin/docker",
        "--config",
        "/nonexistent",
        "--host",
        "unix:///run/docker.sock",
    )
    environment = captured["environment"]
    assert isinstance(environment, dict)
    assert "DOCKER_HOST" not in environment


def test_git_source_operations_disable_repository_fsmonitor_hook(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    subprocess.run(
        ("/usr/bin/git", "init", "--quiet", str(repository)),
        check=True,
    )
    tracked = repository / "tracked.txt"
    tracked.write_text("tracked\n", encoding="utf-8")
    subprocess.run(
        ("/usr/bin/git", "-C", str(repository), "add", "tracked.txt"),
        check=True,
    )
    subprocess.run(
        (
            "/usr/bin/git",
            "-C",
            str(repository),
            "-c",
            "user.name=Preflight Test",
            "-c",
            "user.email=preflight@example.invalid",
            "commit",
            "--quiet",
            "-m",
            "fixture",
        ),
        check=True,
    )
    marker = tmp_path / "fsmonitor-was-executed"
    hook = tmp_path / "hostile-fsmonitor"
    # Bind the marker directly in the configured executable instead of trusting
    # fsmonitor's protocol arguments.
    hook.write_text(
        "#!/usr/bin/python3\n"
        "from pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('executed', encoding='utf-8')\n"
        "raise SystemExit(1)\n",
        encoding="utf-8",
    )
    hook.chmod(0o755)
    subprocess.run(
        (
            "/usr/bin/git",
            "-C",
            str(repository),
            "config",
            "core.fsmonitor",
            str(hook),
        ),
        check=True,
    )

    rows = MODULE._git_source_rows("candidate", repository, Path("/usr/bin/git"))
    identity = MODULE.git_identity(repository, Path("/usr/bin/git"))

    assert any(row["path"] == "candidate/tracked.txt" for row in rows)
    assert identity["head"] or identity["dirty"]
    assert not marker.exists()


def test_owner_only_secret_file_and_secure_cleanup(tmp_path: Path) -> None:
    secret_root = tmp_path / "secrets"
    secret = secret_root / "runtime.connection"

    MODULE.write_owner_only_file(secret, b"opaque-secret\n")

    assert MODULE.owner_only_file_passes(secret)
    assert stat.S_IMODE(secret_root.stat().st_mode) == 0o700
    assert stat.S_IMODE(secret.stat().st_mode) == 0o600
    assert MODULE._secure_remove_tree(secret_root)
    assert not secret_root.exists()


def test_stdin_bearing_provisioning_output_is_never_copied_into_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = b"CREATE ROLE runtime PASSWORD 'must-not-leak';\n"
    emitted = b"diagnostic repeated must-not-leak"
    monkeypatch.setattr(
        MODULE.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=args[0],
            returncode=0,
            stdout=emitted,
            stderr=emitted,
        ),
    )
    evidence: list[dict] = []

    MODULE._run_provisioning_command(
        "secret-stdin",
        ("/usr/bin/true",),
        cwd=tmp_path,
        evidence=evidence,
        stdin_payload=secret,
    )

    serialized = json.dumps(evidence)
    assert "must-not-leak" not in serialized
    assert evidence[0]["stdoutTail"] == "[output suppressed for stdin-bearing command]"
    assert evidence[0]["stderrTail"] == "[output suppressed for stdin-bearing command]"


def test_credential_bearing_provisioning_output_is_withheld_without_stdin(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    emitted = b"unexpected credential-adjacent diagnostic"
    monkeypatch.setattr(
        MODULE.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=args[0],
            returncode=0,
            stdout=emitted,
            stderr=emitted,
        ),
    )
    evidence: list[dict] = []

    observed = MODULE._run_provisioning_command(
        "credential-bearing",
        ("/usr/bin/true",),
        cwd=tmp_path,
        evidence=evidence,
        suppress_receipt_output=True,
    )

    assert observed == emitted
    assert emitted.decode() not in json.dumps(evidence)
    assert evidence[0]["receiptOutputWithheld"] is True
    assert evidence[0]["stdoutTail"] == "[output suppressed for credential-bearing command]"
    assert evidence[0]["stderrTail"] == "[output suppressed for credential-bearing command]"


def test_production_runtime_certificate_exceeds_application_readiness_floor() -> None:
    assert MODULE.DATA_PROTECTION_CERTIFICATE_DAYS > 7


def test_postgres_runtime_contract_is_exact_loopback_tls17(tmp_path: Path) -> None:
    ca = tmp_path / "ca.crt"
    ca.write_text("not-used-by-string-builder", encoding="ascii")
    password = "a" * 64

    value = MODULE._postgres_connection_string(
        port=15432,
        username="cwpf_runtime_a",
        password=password,
        ca_certificate=ca,
    )

    assert MODULE.POSTGRES_IMAGE == "postgres:17-alpine"
    assert "Host=127.0.0.1" in value
    assert "Port=15432" in value
    assert "SSL Mode=VerifyFull" in value
    assert "Trust Server Certificate=false" in value
    assert f"Root Certificate={ca}" in value
    assert value.split(";") == [
        "Host=127.0.0.1",
        "Port=15432",
        "Database=chummer_preflight",
        "Username=cwpf_runtime_a",
        f"Password={password}",
        "SSL Mode=VerifyFull",
        f"Root Certificate={ca}",
        "Trust Server Certificate=false",
        "Pooling=false",
    ]
    with pytest.raises(MODULE.PreflightError, match="role is invalid"):
        MODULE._postgres_connection_string(
            port=15432,
            username="unsafe-role;",
            password=password,
            ca_certificate=ca,
        )
    with pytest.raises(MODULE.PreflightError, match="credential shape is invalid"):
        MODULE._postgres_connection_string(
            port=15432,
            username="cwpf_runtime_a",
            password="a" * 63 + ";",
            ca_certificate=ca,
        )


@pytest.mark.parametrize(
    "injected_name",
    (
        "ca.crt;Trust Server Certificate=true",
        'ca.crt";SSL Mode=Disable',
        "ca.crt\nPooling=true",
        "ca.crt=override",
        "ca cert.crt",
    ),
)
def test_postgres_connection_string_rejects_ca_path_property_injection(
    tmp_path: Path,
    injected_name: str,
) -> None:
    ca = tmp_path / injected_name
    ca.write_text("certificate", encoding="ascii")

    with pytest.raises(MODULE.PreflightError, match="metacharacters"):
        MODULE._postgres_connection_string(
            port=15432,
            username="cwpf_runtime_a",
            password="a" * 64,
            ca_certificate=ca,
        )


def test_postgres_connection_string_rejects_symlinked_ca_path(tmp_path: Path) -> None:
    ca = tmp_path / "real-ca.crt"
    ca.write_text("certificate", encoding="ascii")
    linked = tmp_path / "linked-ca.crt"
    linked.symlink_to(ca)

    with pytest.raises(MODULE.PreflightError, match="symbolic-link component"):
        MODULE._postgres_connection_string(
            port=15432,
            username="cwpf_runtime_a",
            password="a" * 64,
            ca_certificate=linked,
        )


def test_postgres_internal_endpoint_requires_one_rfc1918_network() -> None:
    networks = {"owned-internal": {"IPAddress": "172.31.0.2"}}

    assert (
        MODULE._validated_internal_container_ipv4(networks, "owned-internal")
        == "172.31.0.2"
    )
    assert MODULE._docker_ports_are_unpublished(None, {"5432/tcp": None})
    assert MODULE._docker_ports_are_unpublished({}, {})
    assert not MODULE._docker_ports_are_unpublished(
        {"5432/tcp": [{"HostIp": "127.0.0.1", "HostPort": "15432"}]},
        {"5432/tcp": [{"HostIp": "127.0.0.1", "HostPort": "15432"}]},
    )

    with pytest.raises(MODULE.PreflightError, match="only to its owned internal network"):
        MODULE._validated_internal_container_ipv4(
            {
                **networks,
                "unexpected-egress": {"IPAddress": "172.30.0.2"},
            },
            "owned-internal",
        )
    with pytest.raises(MODULE.PreflightError, match="RFC1918 IPv4"):
        MODULE._validated_internal_container_ipv4(
            {"owned-internal": {"IPAddress": "203.0.113.4"}},
            "owned-internal",
        )


def test_postgres_hba_contract_requires_exact_tls_only_rules() -> None:
    rules = [
        {
            "ruleNumber": 1,
            "type": "local",
            "database": ["all"],
            "user": ["all"],
            "address": None,
            "netmask": None,
            "authMethod": "trust",
            "options": None,
            "error": None,
        },
        *[
            {
                "ruleNumber": number,
                "type": kind,
                "database": ["all"],
                "user": ["all"],
                "address": address,
                "netmask": netmask,
                "authMethod": method,
                "options": None,
                "error": None,
            }
            for number, kind, address, netmask, method in (
                (2, "hostssl", "0.0.0.0", "0.0.0.0", "scram-sha-256"),
                (3, "hostssl", "::", "::", "scram-sha-256"),
                (4, "hostnossl", "0.0.0.0", "0.0.0.0", "reject"),
                (5, "hostnossl", "::", "::", "reject"),
            )
        ],
    ]
    document = {"ssl": "on", "hbaFile": MODULE.POSTGRES_HBA_PATH, "rules": rules}

    assert MODULE._postgres_hba_contract_evidence(document)["passed"]
    generic = copy.deepcopy(document)
    generic["rules"][1]["type"] = "host"
    assert not MODULE._postgres_hba_contract_evidence(generic)["passed"]
    parse_error = copy.deepcopy(document)
    parse_error["rules"][2]["error"] = "invalid rule"
    assert not MODULE._postgres_hba_contract_evidence(parse_error)["passed"]
    extra = copy.deepcopy(document)
    extra["rules"].append(copy.deepcopy(extra["rules"][-1]))
    assert not MODULE._postgres_hba_contract_evidence(extra)["passed"]


def test_postgres_transport_proof_requires_exact_tls_and_plaintext_rejection() -> None:
    proof = {
        "contractName": "chummer.postgres_transport_proof.v1",
        "authenticated": True,
        "pgStatSsl": True,
        "plaintextAttempted": True,
        "plaintextRejected": True,
        "plaintextSqlState": "28000",
        "gssEncryptionDisabled": True,
    }

    evidence = MODULE._postgres_transport_proof_evidence(
        proof,
        accepted_before=4,
        accepted_after=6,
    )
    assert evidence["passed"]
    wrong_state = {**proof, "plaintextSqlState": "28P01"}
    assert not MODULE._postgres_transport_proof_evidence(
        wrong_state,
        accepted_before=4,
        accepted_after=6,
    )["passed"]
    assert not MODULE._postgres_transport_proof_evidence(
        proof,
        accepted_before=4,
        accepted_after=5,
    )["passed"]
def test_loopback_tcp_forwarder_round_trips_and_cleans_up(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    target.settimeout(5)
    target.bind(("127.0.0.1", 0))
    target.listen(1)
    target_port = int(target.getsockname()[1])
    server_errors: list[Exception] = []

    def echo_once() -> None:
        try:
            connection, _ = target.accept()
            with connection:
                payload = connection.recv(4096)
                connection.sendall(b"echo:" + payload)
        except Exception as exc:  # pragma: no cover - asserted below
            server_errors.append(exc)
        finally:
            target.close()

    server_thread = threading.Thread(target=echo_once, daemon=True)
    server_thread.start()
    monkeypatch.setattr(
        MODULE,
        "RFC1918_NETWORKS",
        (ipaddress.ip_network("127.0.0.0/8"),),
    )
    evidence: dict = {}

    with MODULE.loopback_tcp_forwarder(
        target_host="127.0.0.1",
        target_port=target_port,
        evidence=evidence,
    ) as forwarder_port:
        with socket.create_connection(("127.0.0.1", forwarder_port), timeout=5) as client:
            client.sendall(b"opaque-tls-bytes")
            assert client.recv(4096) == b"echo:opaque-tls-bytes"

    server_thread.join(timeout=5)
    assert not server_thread.is_alive()
    assert not server_errors
    assert evidence["started"]
    assert evidence["listenerLoopbackOnly"]
    assert evidence["tlsTerminated"] is False
    assert evidence["acceptedConnections"] == 1
    assert evidence["upstreamConnectionFailures"] == 0
    assert evidence["cleanupPassed"]
    assert evidence["passed"]
    assert evidence["connectionLimit"] == MODULE.POSTGRES_FORWARDER_MAX_CONNECTIONS
    assert evidence["idleTimeoutSeconds"] == MODULE.POSTGRES_FORWARDER_IDLE_TIMEOUT_SECONDS
    assert evidence["rejectedConnections"] == 0
    assert evidence["idleTimeouts"] == 0


def test_sigterm_handler_raises_through_cleanup_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    installed: list[tuple[object, object]] = []
    monkeypatch.setattr(
        MODULE.signal,
        "signal",
        lambda signum, handler: installed.append((signum, handler)),
    )

    assert not issubclass(MODULE.PreflightCancelled, Exception)
    with pytest.raises(MODULE.PreflightCancelled, match="SIGTERM"):
        MODULE._terminate_for_signal(MODULE.signal.SIGTERM, None)

    assert installed == [(MODULE.signal.SIGTERM, MODULE.signal.SIG_IGN)]


def test_data_protection_keyring_evidence_requires_encrypted_xml(tmp_path: Path) -> None:
    keyring = tmp_path / "keyring"
    keyring.mkdir()
    plain = keyring / "key-plain.xml"
    plain.write_text("<key><secret>plain</secret></key>", encoding="utf-8")
    assert not MODULE._data_protection_keyring_evidence(keyring)["encryptedAtRest"]

    plain.unlink()
    encrypted = keyring / "key-encrypted.xml"
    encrypted.write_text(
        """<key><encryptedSecret decryptorType="CertificateXmlEncryptor">
        <EncryptedData xmlns="http://www.w3.org/2001/04/xmlenc#">
        <CipherData><CipherValue>Y2lwaGVydGV4dA==</CipherValue></CipherData>
        </EncryptedData></encryptedSecret></key>""",
        encoding="utf-8",
    )
    evidence = MODULE._data_protection_keyring_evidence(keyring)
    assert evidence["encryptedAtRest"]
    assert evidence["keyCount"] == 1

    encrypted.write_text(
        "<key><!-- encryptedSecret CipherValue --><descriptor>plain</descriptor></key>",
        encoding="utf-8",
    )
    assert not MODULE._data_protection_keyring_evidence(keyring)["encryptedAtRest"]


def test_loopback_probe_contract_rejects_external_urls_and_redirects() -> None:
    parsed = MODULE._validate_loopback_probe_url("https://127.0.0.1:8443/api/ready")
    assert parsed.hostname == "127.0.0.1"
    assert parsed.port == 8443
    with pytest.raises(MODULE.PreflightError, match="exact HTTPS loopback"):
        MODULE._validate_loopback_probe_url("https://chummer.run/api/ready")
    with pytest.raises(MODULE.PreflightError, match="exact HTTPS loopback"):
        MODULE._validate_loopback_probe_url("http://127.0.0.1:8443/api/ready")
    assert MODULE._NoRedirectHandler().redirect_request(
        None,
        None,
        302,
        "Found",
        {},
        "https://chummer.run/api/ready",
    ) is None


def test_landlock_launcher_denies_source_write_and_allows_declared_output(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    output = tmp_path / "output"
    source.mkdir()
    output.mkdir()
    protected = source / "protected.txt"
    protected.write_text("original", encoding="utf-8")
    allowed = output / "allowed.txt"
    code = (
        "from pathlib import Path; import socket, sys; "
        "source=Path(sys.argv[1]); output=Path(sys.argv[2]); "
        "denied=False; socket_denied=False; "
        "\ntry:\n source.write_text('forged')\n"
        "except PermissionError:\n denied=True\n"
        "try:\n socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)\n"
        "except PermissionError:\n socket_denied=True\n"
        "output.write_text('allowed'); "
        "sys.exit(0 if denied and socket_denied else 9)"
    )

    completed = subprocess.run(
        (
            sys.executable,
            str(LANDLOCK_EXEC),
            "--seccomp-library",
            str(SECCOMP_LIBRARY),
            "--allow-write",
            str(output),
            "--",
            sys.executable,
            "-c",
            code,
            str(protected),
            str(allowed),
        ),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr.decode(errors="replace")
    assert protected.read_text(encoding="utf-8") == "original"
    assert allowed.read_text(encoding="utf-8") == "allowed"


def test_landlock_launcher_denies_host_docker_socket(
    tmp_path: Path,
) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    code = (
        "import ctypes, errno, socket, sys; "
        "denied=False; ring_denied=False; "
        "\ntry:\n"
        " handle=socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); "
        "handle.connect('/var/run/docker.sock')\n"
        "except PermissionError:\n denied=True\n"
        "libc=ctypes.CDLL(None, use_errno=True); "
        "result=libc.syscall(425, 1, 0); "
        "ring_denied=(result == -1 and ctypes.get_errno() == errno.EPERM); "
        "sys.exit(0 if denied and ring_denied else 9)"
    )

    completed = subprocess.run(
        (
            sys.executable,
            str(LANDLOCK_EXEC),
            "--seccomp-library",
            str(SECCOMP_LIBRARY),
            "--allow-write",
            str(allowed),
            "--",
            sys.executable,
            "-c",
            code,
        ),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr.decode(errors="replace")


def test_landlock_launcher_brokers_tcp_to_loopback_and_denies_non_loopback(
    tmp_path: Path,
) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    code = textwrap.dedent(
        """
        import concurrent.futures
        import errno
        import os
        import socket
        import sys

        port = int(sys.argv[1])
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.bind(("127.0.0.1", port))
        listener.listen()
        client = socket.create_connection(
            ("127.0.0.1", port), timeout=2
        )
        accepted, _ = listener.accept()
        accepted.close()
        client.close()
        listener.close()

        def denied(address):
            try:
                socket.create_connection(address, timeout=.2)
            except PermissionError as exc:
                return exc.errno == errno.EPERM
            return False

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            denied4, denied6 = tuple(
                pool.map(denied, (("192.0.2.1", port), ("2001:db8::1", port)))
            )
        loopback_other_port_denied = denied(("127.0.0.1", (port % 65535) + 1))
        forked = os.fork()
        if forked == 0:
            os._exit(0 if denied(("192.0.2.1", port)) else 1)
        _, forked_status = os.waitpid(forked, 0)
        forked_denied = os.WIFEXITED(forked_status) and os.WEXITSTATUS(forked_status) == 0
        nonloopback_listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            nonloopback_listener.bind(("0.0.0.0", port))
        except PermissionError as exc:
            bind_denied = exc.errno == errno.EPERM
        else:
            bind_denied = False
        nonloopback_listener.close()
        automatic_listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            automatic_listener.listen()
        except PermissionError as exc:
            automatic_listen_denied = exc.errno == errno.EPERM
        else:
            automatic_listen_denied = False
        automatic_listener.close()
        fast_open = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            fast_open.sendto(
                b"x", socket.MSG_FASTOPEN, ("192.0.2.1", port)
            )
        except PermissionError as exc:
            fast_open_denied = exc.errno == errno.EPERM
        else:
            fast_open_denied = False
        fast_open.close()
        try:
            socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        except PermissionError as exc:
            udp_denied = exc.errno == errno.EPERM
        else:
            udp_denied = False
        sys.exit(
            0
            if denied4
            and denied6
            and loopback_other_port_denied
            and forked_denied
            and bind_denied
            and automatic_listen_denied
            and fast_open_denied
            and udp_denied
            else 9
        )
        """
    )

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    completed = subprocess.run(
        (
            sys.executable,
            str(LANDLOCK_EXEC),
            "--seccomp-library",
            str(SECCOMP_LIBRARY),
            "--allow-write",
            str(allowed),
            "--allow-connect-port",
            str(port),
            "--allow-bind-port",
            str(port),
            "--",
            sys.executable,
            "-c",
            code,
            str(port),
        ),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=10,
    )

    assert completed.returncode == 0, completed.stderr.decode(errors="replace")


def test_transient_tree_mutation_monitor_detects_restored_metadata(
    tmp_path: Path,
) -> None:
    root = tmp_path / "sealed"
    root.mkdir()
    target = root / "source.txt"
    target.write_text("unchanged", encoding="utf-8")
    initial_mode = stat.S_IMODE(target.stat().st_mode)
    initial_times = (target.stat().st_atime_ns, target.stat().st_mtime_ns)
    evidence: dict[str, object] = {}

    with MODULE.transient_tree_mutation_monitor((root,), evidence):
        target.chmod(0o600)
        target.chmod(initial_mode)
        MODULE.os.setxattr(target, b"user.cwpf-test", b"transient")
        MODULE.os.removexattr(target, b"user.cwpf-test")
        target.touch()
        target_stat = target.stat()
        assert target_stat.st_size == len("unchanged")
        MODULE.os.utime(target, ns=initial_times)

    assert not evidence["passed"]
    assert int(evidence["mutationEventCount"]) > 0
    assert target.read_text(encoding="utf-8") == "unchanged"
    assert stat.S_IMODE(target.stat().st_mode) == initial_mode


def test_transient_tree_mutation_monitor_allows_read_only_consumption(
    tmp_path: Path,
) -> None:
    root = tmp_path / "sealed"
    root.mkdir()
    target = root / "source.txt"
    target.write_text("unchanged", encoding="utf-8")
    evidence: dict[str, object] = {}

    with MODULE.transient_tree_mutation_monitor((root,), evidence):
        assert target.read_text(encoding="utf-8") == "unchanged"

    assert evidence["passed"]
    assert evidence["mutationEventCount"] == 0


def test_loopback_probe_preserves_duplicate_generation_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Headers:
        def get_all(self, name: str, default: object = None):
            assert name == "X-Chummer-Release-Generation"
            return ["generation-a", "generation-b"]

    class Response:
        status = 200
        headers = Headers()

        def __enter__(self):
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self, _maximum: int) -> bytes:
            return b'{"status":"ok"}'

        def geturl(self) -> str:
            return "https://127.0.0.1:8443/api/ready"

    class Opener:
        def open(self, *_args: object, **_kwargs: object) -> Response:
            return Response()

    monkeypatch.setattr(MODULE.urllib.request, "build_opener", lambda *_args: Opener())

    status, payload, _body, headers = MODULE.http_get_json(
        "https://127.0.0.1:8443/api/ready"
    )

    assert status == 200
    assert payload == {"status": "ok"}
    assert headers["x-chummer-release-generation"] == (
        "generation-a",
        "generation-b",
    )


@pytest.mark.parametrize(
    "body",
    (
        b'{"ready":false,"ready":true}',
        b'{"ready":true,"metric":NaN}',
        b'{"ready":true,"metric":Infinity}',
        b'{"ready":true,"metric":1e999}',
    ),
)
def test_loopback_probe_rejects_ambiguous_or_non_finite_json(
    body: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Headers:
        def get_all(self, _name: str, default: object = None):
            return default or []

    class Response:
        status = 200
        headers = Headers()

        def __enter__(self):
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self, _maximum: int) -> bytes:
            return body

        def geturl(self) -> str:
            return "https://127.0.0.1:8443/api/ready"

    class Opener:
        def open(self, *_args: object, **_kwargs: object) -> Response:
            return Response()

    monkeypatch.setattr(MODULE.urllib.request, "build_opener", lambda *_args: Opener())

    status, payload, returned_body, _headers = MODULE.http_get_json(
        "https://127.0.0.1:8443/api/ready"
    )

    assert status == 200
    assert payload is None
    assert returned_body == body


def test_generation_artifact_delivery_binds_route_header_size_and_hash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, int]] = []

    def fetch(url: str, *, max_bytes: int, **_kwargs: object):
        calls.append((url, max_bytes))
        return (
            200,
            FIXTURE_ARTIFACT_BYTES,
            {"x-chummer-release-generation": ("generation-a",)},
        )

    monkeypatch.setattr(MODULE, "http_get_bytes", fetch)
    inventory = MODULE.prepared_manifest_binding(manifest())["artifactInventory"]

    evidence = MODULE.generation_artifact_delivery_evidence(
        "https://127.0.0.1:8443",
        SimpleNamespace(),
        "generation-a",
        inventory,
    )

    assert evidence["passed"]
    assert calls == [
        (
            "https://127.0.0.1:8443/downloads/g/generation-a/files/a.bin",
            1,
        )
    ]


@pytest.mark.parametrize(
    ("status", "body", "headers"),
    (
        (404, FIXTURE_ARTIFACT_BYTES, {"x-chummer-release-generation": ("generation-a",)}),
        (200, b"b", {"x-chummer-release-generation": ("generation-a",)}),
        (200, FIXTURE_ARTIFACT_BYTES, {}),
        (
            200,
            FIXTURE_ARTIFACT_BYTES,
            {"x-chummer-release-generation": ("generation-a", "generation-a")},
        ),
    ),
)
def test_generation_artifact_delivery_fails_closed_on_response_drift(
    monkeypatch: pytest.MonkeyPatch,
    status: int,
    body: bytes,
    headers: dict[str, tuple[str, ...]],
) -> None:
    monkeypatch.setattr(
        MODULE,
        "http_get_bytes",
        lambda *_args, **_kwargs: (status, body, headers),
    )
    inventory = MODULE.prepared_manifest_binding(manifest())["artifactInventory"]

    evidence = MODULE.generation_artifact_delivery_evidence(
        "https://127.0.0.1:8443",
        SimpleNamespace(),
        "generation-a",
        inventory,
    )

    assert not evidence["passed"]


def test_generation_artifact_delivery_rejects_current_shelf_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inventory = copy.deepcopy(
        MODULE.prepared_manifest_binding(manifest())["artifactInventory"]
    )
    inventory[0]["url"] = "/downloads/files/a.bin"
    monkeypatch.setattr(
        MODULE,
        "http_get_bytes",
        lambda *_args, **_kwargs: pytest.fail("non-generation route must not be fetched"),
    )

    with pytest.raises(MODULE.PreflightError, match="generation-bound"):
        MODULE.generation_artifact_delivery_evidence(
            "https://127.0.0.1:8443",
            SimpleNamespace(),
            "generation-a",
            inventory,
        )


def test_postgres_image_id_requires_exact_operator_pin() -> None:
    expected = "sha256:" + "a" * 64
    assert MODULE.require_postgres_image_id(expected) == expected
    with pytest.raises(MODULE.PreflightError, match="expected-postgres-image-id"):
        MODULE.require_postgres_image_id("postgres:17-alpine")


def test_generation_tool_must_be_candidate_owned(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    expected = candidate / "scripts" / "release_shelf_generation.py"
    expected.parent.mkdir(parents=True)
    expected.write_text("# candidate", encoding="utf-8")
    outside = tmp_path / "outside.py"
    outside.write_text("# outside", encoding="utf-8")

    assert MODULE.bind_generation_tool(candidate, expected) == expected.resolve()
    with pytest.raises(MODULE.PreflightError, match="must resolve to the candidate"):
        MODULE.bind_generation_tool(candidate, outside)


def test_generation_rollback_probe_binds_every_retained_generation_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generation_tool = ROOT / "scripts" / "release_shelf_generation.py"
    generation_module = MODULE._load_generation_module(generation_tool)
    activate = generation_module.activate_filesystem
    activation_count = 0

    def activate_and_tamper(*args: object, **kwargs: object):
        nonlocal activation_count
        result = activate(*args, **kwargs)
        activation_count += 1
        if activation_count == 2:
            shelf = Path(args[1])
            candidate_path = (
                shelf
                / generation_module.GENERATIONS_DIRECTORY
                / "preflight-generation-a"
                / generation_module.ACTIVATION_CANDIDATE
            )
            payload = json.loads(candidate_path.read_text(encoding="utf-8"))
            payload["unexpectedAuditField"] = "tampered"
            candidate_path.write_text(json.dumps(payload), encoding="utf-8")
        return result

    generation_module.activate_filesystem = activate_and_tamper
    monkeypatch.setattr(
        MODULE,
        "_load_generation_module",
        lambda _path: generation_module,
    )

    evidence = MODULE.generation_rollback_probe(
        generation_tool,
        tmp_path / "rollback",
    )

    assert not evidence["passed"]
    assert not evidence["generationABytesUnchanged"]
    assert (
        evidence["generationAClosureSha256Before"]
        != evidence["generationAClosureSha256AfterActivation"]
    )


@pytest.mark.parametrize("mutation", ("empty-directory", "directory-mode"))
def test_generation_rollback_probe_binds_directory_topology_and_modes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    generation_tool = ROOT / "scripts" / "release_shelf_generation.py"
    generation_module = MODULE._load_generation_module(generation_tool)
    activate = generation_module.activate_filesystem
    activation_count = 0

    def activate_and_tamper(*args: object, **kwargs: object):
        nonlocal activation_count
        result = activate(*args, **kwargs)
        activation_count += 1
        if activation_count == 2:
            generation_a = (
                Path(args[1])
                / generation_module.GENERATIONS_DIRECTORY
                / "preflight-generation-a"
            )
            if mutation == "empty-directory":
                (generation_a / "unexpected-empty").mkdir()
            else:
                files = generation_a / "files"
                files.chmod(stat.S_IMODE(files.stat().st_mode) ^ 0o020)
        return result

    generation_module.activate_filesystem = activate_and_tamper
    monkeypatch.setattr(MODULE, "_load_generation_module", lambda _path: generation_module)

    evidence = MODULE.generation_rollback_probe(generation_tool, tmp_path / "rollback")

    assert not evidence["passed"]
    assert not evidence["generationABytesUnchanged"]
    assert (
        evidence["generationAClosureSha256Before"]
        != evidence["generationAClosureSha256AfterActivation"]
    )


def test_runtime_shelf_binds_post_activation_generation_and_artifact_route(
    tmp_path: Path,
) -> None:
    canonical_template = tmp_path / "source" / MODULE.CANONICAL
    compatibility_template = tmp_path / "source" / MODULE.COMPATIBILITY
    canonical_template.parent.mkdir()
    canonical_template.write_text(json.dumps(manifest()), encoding="utf-8")
    compatibility_template.write_text(json.dumps(manifest()), encoding="utf-8")

    shelf, evidence = MODULE.prepare_runtime_release_shelf(
        ROOT / "scripts" / "release_shelf_generation.py",
        tmp_path / "runtime-shelf",
        json.loads(canonical_template.read_text(encoding="utf-8")),
        json.loads(compatibility_template.read_text(encoding="utf-8")),
    )

    assert shelf.is_dir()
    assert evidence["passed"]
    assert evidence["generationId"] == "canonical-writer-production-envelope"
    canonical = evidence["preparedManifestBindings"]["canonical"]
    compatibility = evidence["preparedManifestBindings"]["compatibility"]
    assert canonical["generationId"] == evidence["generationId"]
    assert compatibility["generationId"] == evidence["generationId"]
    assert canonical["artifactInventory"] == compatibility["artifactInventory"]
    assert canonical["artifactInventory"][0]["url"] == (
        "/downloads/g/canonical-writer-production-envelope/files/preflight-installer.exe"
    )


def test_build_closure_includes_overlay_identity_and_postgres_tool(tmp_path: Path) -> None:
    portal = tmp_path / "portal"
    identity = (
        portal
        / ".codex-studio"
        / "runtime"
        / "PUBLIC_EDGE_PORTAL_OVERLAY_BUILD_INFO.generated.json"
    )
    identity.parent.mkdir(parents=True)
    identity.write_text('{"status":"pass"}', encoding="utf-8")
    postgres_tool = tmp_path / "postgres-tool"
    postgres_tool.mkdir()
    (postgres_tool / "Chummer.InstallLinking.Postgres.Tool.dll").write_bytes(b"tool")

    closure = MODULE.build_output_closure(portal, postgres_tool)
    paths = {row["path"] for row in closure["files"]}

    assert (
        "portal/.codex-studio/runtime/"
        "PUBLIC_EDGE_PORTAL_OVERLAY_BUILD_INFO.generated.json"
    ) in paths
    assert "postgres-tool/Chummer.InstallLinking.Postgres.Tool.dll" in paths


def test_overlay_identity_uses_runtime_reported_source_and_deployment_digests(
    tmp_path: Path,
) -> None:
    build_info = tmp_path / "PUBLIC_EDGE_PORTAL_OVERLAY_BUILD_INFO.generated.json"
    source = "a" * 64
    staged = "b" * 64
    deployment = "c" * 64
    build_info.write_text(
        json.dumps(
            {
                "contractName": "chummer.public_edge_portal_overlay_publish.v1",
                "status": "pass",
                "activationStatus": "activated",
                "sourceFingerprint": {"aggregateSha256": source},
                "stagedPayloadFingerprint": {"aggregateSha256": staged},
                "fullDeploymentDigest": {"sha256": deployment},
                "payloadModeReceipt": {"status": "pass"},
            }
        ),
        encoding="utf-8",
    )

    identity = MODULE.read_preflight_overlay_identity(build_info)

    assert identity["passed"]
    assert identity["sourceFingerprintSha256"] == source
    assert identity["stagedPayloadSha256"] == staged
    assert identity["fullDeploymentDigestSha256"] == deployment


def test_materialized_test_source_projection_matches_pinned_inputs(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    fixtures = candidate / "tests" / "fixtures" / "atomic_release_shelf_v1"
    fixtures.mkdir(parents=True)
    (candidate / "docker-compose.public-edge.yml").write_text(
        'services:\n  portal:\n    image: "pinned"\n',
        encoding="utf-8",
    )
    (fixtures / "current.json").write_text(
        '{"generationId":"fixture"}\n',
        encoding="utf-8",
    )
    output = tmp_path / "output"
    output.mkdir()

    evidence = MODULE.materialize_test_source_projection(candidate, output)

    assert evidence["passed"]
    assert evidence["fileCount"] == 2
    assert (output / "docker-compose.public-edge.yml").read_bytes() == (
        candidate / "docker-compose.public-edge.yml"
    ).read_bytes()
    assert (
        output / "tests" / "fixtures" / "atomic_release_shelf_v1" / "current.json"
    ).read_bytes() == (fixtures / "current.json").read_bytes()


def test_private_payload_state_root_is_single_owner_only_directory(tmp_path: Path) -> None:
    publish = tmp_path / "publish"
    publish.mkdir()

    state = MODULE.ensure_private_payload_state_root(publish)

    assert state == publish / "state"
    assert state.is_dir()
    assert stat.S_IMODE(state.stat().st_mode) == 0o700

    state.rmdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    state.symlink_to(outside, target_is_directory=True)
    with pytest.raises(MODULE.PreflightError, match="state root is unsafe"):
        MODULE.ensure_private_payload_state_root(publish)


def test_closure_rejects_symlinked_root(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    (real / "payload").write_text("payload", encoding="utf-8")
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)

    with pytest.raises(MODULE.PreflightError, match="symbolic-link component"):
        MODULE.build_closure_manifest(MODULE.BUILD_CLOSURE_SCHEMA, (("build", link),))


def test_external_git_source_closure_includes_root_metadata_and_deletions(
    tmp_path: Path,
) -> None:
    candidate = tmp_path / "candidate"
    external = tmp_path / "external"
    for root in (candidate, external):
        root.mkdir()
        subprocess.run(("git", "init", "-q", str(root)), check=True)
    (candidate / "candidate.cs").write_text("candidate", encoding="utf-8")
    subprocess.run(("git", "-C", str(candidate), "add", "candidate.cs"), check=True)
    metadata = external / "Directory.Build.props"
    metadata.write_text("<Project />", encoding="utf-8")
    deleted = external / "deleted.cs"
    deleted.write_text("deleted", encoding="utf-8")
    subprocess.run(
        ("git", "-C", str(external), "add", "Directory.Build.props", "deleted.cs"),
        check=True,
    )
    deleted.unlink()

    closure = MODULE.build_source_closure_manifest(
        candidate,
        (),
        (("external", external),),
    )
    rows = {row["path"]: row for row in closure["files"]}

    assert rows["external/Directory.Build.props"]["state"] == "present"
    assert rows["external/deleted.cs"]["state"] == "deleted"


def test_git_source_closure_hashes_tracked_symlink_text_without_following(
    tmp_path: Path,
) -> None:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    subprocess.run(("git", "init", "-q", str(candidate)), check=True)
    outside = tmp_path / "outside-secret"
    outside.write_text("must-not-be-hashed", encoding="utf-8")
    link = candidate / "source-link"
    link.symlink_to(outside)
    subprocess.run(("git", "-C", str(candidate), "add", "source-link"), check=True)

    closure = MODULE.build_source_closure_manifest(candidate, ())
    row = next(row for row in closure["files"] if row["path"].endswith("source-link"))

    assert row["state"] == "symlink"
    assert row["sha256"] == MODULE.sha256_bytes(str(outside).encode())
    assert row["sha256"] != MODULE.sha256_file(outside)


def test_owned_docker_cleanup_refuses_foreign_resource(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    removed: list[tuple[str, ...]] = []
    monkeypatch.setattr(MODULE, "_docker_resource_present", lambda *args, **kwargs: True)
    monkeypatch.setattr(MODULE, "_docker_resource_owner", lambda *args, **kwargs: "foreign")
    monkeypatch.setattr(
        MODULE,
        "_cleanup_provisioning_command",
        lambda _name, argv, **_kwargs: removed.append(tuple(argv)) or True,
    )

    assert not MODULE._cleanup_owned_docker_resource(
            "container",
            "candidate",
            "a" * 64,
            docker_host=Path("/usr/bin/docker"),
            cwd=tmp_path,
        evidence=[],
    )
    assert removed == []


def _deep_readiness_payload(
    generation_id: str = "generation-a",
    *,
    digest: str = "a" * 64,
) -> dict:
    checks = [
        {"name": name, "passed": True, "status": "pass", "code": "ready"}
        for name in (
            "data_protection_storage",
            "install_linking_store",
            "release_shelf",
            "canonical_release_manifest",
        )
    ]
    return {
        "ready": True,
        "status": "ready",
        "hub": {
            "contractName": "chummer.run.api.deep_readiness.v2",
            "ready": True,
            "status": "pass",
            "servingReady": True,
            "publicationChecksConfigured": True,
            "checks": checks,
            "releaseShelf": {
                "mode": "generation",
                "servingReady": True,
                "publicationChecksConfigured": True,
                "generationId": generation_id,
                "activationReceiptId": (
                    f"activation-{generation_id.removeprefix('generation-')}"
                ),
                "inventoryDigest": digest,
            },
        },
        "playProjection": {"ready": True},
        "deploymentIdentity": {
            "ready": True,
            "code": "overlay_identity_bound",
            "sourceFingerprintSha256": digest,
            "fullDeploymentDigestSha256": digest,
        },
    }


def _publication_readiness_payload(
    generation_id: str = "generation-a",
    *,
    digest: str = "a" * 64,
) -> dict:
    return {
        "ready": True,
        "checksConfigured": True,
        "status": "ready",
        "code": "publication_ready",
        "generationId": generation_id,
        "activationReceiptId": f"activation-{generation_id.removeprefix('generation-')}",
        "inventoryDigest": digest,
        "checks": [
            {"name": name, "ready": True, "status": "ready", "code": "ready"}
            for name in (
                "release_shelf_serving",
                "publication_probe_contract",
                "activation_protocol",
                "release_storage_admission",
            )
        ],
    }


def _install_probe_runtime_fakes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    http_fetch: object,
    *,
    process: object,
    runtime_exit_error: Exception | None = None,
    artifact_fetch: object | None = None,
) -> tuple[dict, list[str]]:
    candidate_root = tmp_path / "candidate"
    publish_root = tmp_path / "publish"
    postgres_tool_root = tmp_path / "postgres-tool"
    work_root = tmp_path / "runtime-work"
    downloads = tmp_path / "downloads"
    generation_root = downloads / "generations" / "generation-a"
    for directory in (
        candidate_root,
        publish_root,
        postgres_tool_root,
        generation_root,
    ):
        directory.mkdir(parents=True, exist_ok=True)

    canonical = manifest()
    compatibility = compatibility_manifest(canonical)
    artifact_path = generation_root / "files" / "a.bin"
    artifact_path.parent.mkdir()
    artifact_path.write_bytes(FIXTURE_ARTIFACT_BYTES)
    for name, payload in (
        (MODULE.CANONICAL, canonical),
        (MODULE.COMPATIBILITY, compatibility),
    ):
        (generation_root / name).write_text(json.dumps(payload), encoding="utf-8")
    canonical_raw = json.dumps(canonical).encode()
    compatibility_raw = json.dumps(compatibility).encode()
    receipt_raw = b"{}"
    live_snapshot = MODULE.LiveEnvelopeSnapshot(
        root=generation_root,
        receipt=MODULE.JsonByteSnapshot(
            "receipt",
            generation_root / "receipt.json",
            generation_root / "receipt.json",
            receipt_raw,
            MODULE.sha256_bytes(receipt_raw),
            {},
        ),
        canonical=MODULE.JsonByteSnapshot(
            "canonical",
            generation_root / MODULE.CANONICAL,
            generation_root / MODULE.CANONICAL,
            canonical_raw,
            MODULE.sha256_bytes(canonical_raw),
            canonical,
        ),
        compatibility=MODULE.JsonByteSnapshot(
            "compatibility",
            generation_root / MODULE.COMPATIBILITY,
            generation_root / MODULE.COMPATIBILITY,
            compatibility_raw,
            MODULE.sha256_bytes(compatibility_raw),
            compatibility,
        ),
        closure={},
    )
    live_binding = {
        "passed": True,
        "canonicalSha256": live_snapshot.canonical.sha256,
        "compatibilitySha256": live_snapshot.compatibility.sha256,
        "bindingSha256": "c" * 64,
    }

    digest = "a" * 64
    shelf_evidence = {
        "passed": True,
        "layout": "v1",
        "generationId": "generation-a",
        "activationReceiptId": "activation-a",
        "inventoryDigest": digest,
        "releaseIdentity": MODULE.manifest_identity(canonical),
        "preparedManifestBindings": {
            "canonical": MODULE.prepared_manifest_binding(canonical),
            "compatibility": MODULE.prepared_manifest_binding(compatibility),
        },
    }
    tls_root = tmp_path / "tls"
    tls_root.mkdir()
    tls_paths = [tls_root / name for name in ("ca", "server", "key", "dpfx", "password")]
    for path in tls_paths:
        path.write_bytes(b"fixture")
        path.chmod(0o600)
    tls = MODULE.RuntimeTlsMaterial(*tls_paths)
    runtime_connection = tls_root / "runtime.connection"
    runtime_connection.write_text("withheld", encoding="utf-8")
    runtime_connection.chmod(0o600)
    postgres = MODULE.PostgresRuntimeAuthority(
        runtime_connection_file=runtime_connection,
        image_id="sha256:" + "b" * 64,
        container_name="fixture",
        host_port=15432,
        evidence={},
    )
    runtime = MODULE.LoopbackRuntimeHandle(
        process=process,
        port=8443,
        ssl_context=SimpleNamespace(),
        evidence={"fixtureEnvelope": True},
    )
    dotnet_execution = MODULE.DotnetExecution(
        host=Path("/usr/lib/dotnet/dotnet"),
        host_sha256="d" * 64,
        root=Path("/usr/lib/dotnet"),
        toolchain_closure={"closureSha256": "e" * 64, "fileCount": 1, "totalBytes": 1},
        python_host=Path(sys.executable),
        python_host_sha256="f" * 64,
        landlock_launcher=LANDLOCK_EXEC,
        seccomp_library=SECCOMP_LIBRARY,
        landlock_abi=4,
    )
    runtime_system_tools = MODULE.PinnedSystemTools(
        git=Path("/usr/bin/git"),
        git_sha256="1" * 64,
        docker=Path("/usr/bin/docker"),
        docker_sha256="2" * 64,
        docker_socket=MODULE.LOCAL_DOCKER_SOCKET,
        docker_socket_identity=MODULE.docker_socket_identity()[1],
        openssl=Path("/usr/bin/openssl"),
        openssl_sha256="3" * 64,
        seccomp_library=SECCOMP_LIBRARY,
        seccomp_library_sha256="4" * 64,
    )
    events: list[str] = []

    @contextlib.contextmanager
    def fake_postgres_authority(*, evidence: dict, **_kwargs: object):
        evidence.update({"passed": True, "cleanupPassed": True})
        try:
            yield postgres
        finally:
            events.append("postgres-exit")

    @contextlib.contextmanager
    def fake_loopback_runtime(*_args: object, **_kwargs: object):
        try:
            yield runtime
        finally:
            events.append("runtime-exit")
            if runtime_exit_error is not None:
                raise runtime_exit_error

    def fake_remove(path: Path) -> bool:
        events.append(f"remove-{path.name}")
        return True

    monkeypatch.setattr(
        MODULE,
        "prepare_runtime_release_shelf",
        lambda *_args, **_kwargs: (downloads, shelf_evidence),
    )
    monkeypatch.setattr(
        MODULE,
        "generate_runtime_tls_material",
        lambda *_args, **_kwargs: tls,
    )
    monkeypatch.setattr(MODULE, "isolated_postgres_authority", fake_postgres_authority)
    monkeypatch.setattr(MODULE, "loopback_runtime", fake_loopback_runtime)
    monkeypatch.setattr(MODULE, "http_get_json", http_fetch)
    if artifact_fetch is None:
        artifact_fetch = lambda _url, **_kwargs: (
            200,
            FIXTURE_ARTIFACT_BYTES,
            {"x-chummer-release-generation": ("generation-a",)},
        )
    monkeypatch.setattr(MODULE, "http_get_bytes", artifact_fetch)
    monkeypatch.setattr(MODULE.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        MODULE,
        "_data_protection_keyring_evidence",
        lambda _path: {"encryptedAtRest": True, "keyCount": 1},
    )
    monkeypatch.setattr(MODULE, "_secure_remove_tree", fake_remove)

    return (
        {
            "candidate_root": candidate_root,
            "publish_root": publish_root,
            "postgres_tool_root": postgres_tool_root,
            "generation_tool": candidate_root / "scripts" / "release_shelf_generation.py",
            "live_envelope_snapshot": live_snapshot,
            "live_envelope_binding": live_binding,
            "overlay_identity": {
                "sourceFingerprintSha256": digest,
                "fullDeploymentDigestSha256": digest,
            },
            "work_root": work_root,
            "expected_postgres_image_id": "sha256:" + "b" * 64,
            "dotnet_execution": dotnet_execution,
            "system_tools": runtime_system_tools,
        },
        events,
    )


def test_readiness_contracts_are_strict() -> None:
    deep = _deep_readiness_payload()
    assert MODULE.deep_readiness_passes(200, deep)
    deep["hub"]["checks"][0]["passed"] = False
    assert not MODULE.deep_readiness_passes(200, deep)
    assert not MODULE.deep_readiness_passes(200, {"status": "ready"})

    digest = "b" * 64
    publication = {
        "ready": True,
        "checksConfigured": True,
        "status": "ready",
        "code": "publication_ready",
        "generationId": "generation-a",
        "activationReceiptId": "activation-a",
        "inventoryDigest": digest,
        "checks": [
            {"name": name, "ready": True, "status": "ready", "code": "ready"}
            for name in (
                "release_shelf_serving",
                "publication_probe_contract",
                "activation_protocol",
                "release_storage_admission",
            )
        ],
    }
    assert MODULE.publication_readiness_passes(200, publication)
    publication["checks"].append(
        {"name": "unexpected", "ready": False, "status": "blocked", "code": "failed"}
    )
    assert not MODULE.publication_readiness_passes(200, publication)


def test_readiness_identity_binds_shelf_publication_and_overlay() -> None:
    digest = "a" * 64
    deep = _deep_readiness_payload()
    publication = {
        "generationId": "generation-a",
        "activationReceiptId": "activation-a",
        "inventoryDigest": digest,
    }
    shelf = {
        "generationId": "generation-a",
        "activationReceiptId": "activation-a",
        "inventoryDigest": digest,
    }
    overlay = {
        "sourceFingerprintSha256": digest,
        "fullDeploymentDigestSha256": digest,
    }

    evidence = MODULE.coherent_readiness_identity_evidence(
        deep,
        publication,
        shelf,
        overlay,
    )
    assert evidence["passed"]
    drifted = copy.deepcopy(publication)
    drifted["generationId"] = "generation-b"
    assert not MODULE.coherent_readiness_identity_evidence(
        deep,
        drifted,
        shelf,
        overlay,
    )["passed"]
    wrong_overlay = {**overlay, "fullDeploymentDigestSha256": "b" * 64}
    assert not MODULE.coherent_readiness_identity_evidence(
        deep,
        publication,
        shelf,
        wrong_overlay,
    )["passed"]


@pytest.mark.parametrize("binding_matches", (True, False))
def test_probe_runtime_requires_exact_live_envelope_snapshot_binding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    binding_matches: bool,
) -> None:
    class RunningProcess:
        def poll(self) -> None:
            return None

    canonical = manifest()
    compatibility = compatibility_manifest(canonical)
    responses = [
        (200, {"status": "ok"}, {}),
        (200, _deep_readiness_payload("generation-a"), {}),
        (200, _publication_readiness_payload("generation-a"), {}),
        (200, canonical, {"x-chummer-release-generation": ("generation-a",)}),
        (200, compatibility, {"x-chummer-release-generation": ("generation-a",)}),
        (200, _deep_readiness_payload("generation-a"), {}),
        (200, _publication_readiness_payload("generation-a"), {}),
    ]

    def fetch(_url: str, **_kwargs: object):
        status, payload, headers = responses.pop(0)
        return status, payload, json.dumps(payload).encode(), headers

    kwargs, _events = _install_probe_runtime_fakes(
        tmp_path,
        monkeypatch,
        fetch,
        process=RunningProcess(),
    )
    if not binding_matches:
        kwargs["live_envelope_binding"] = {
            **kwargs["live_envelope_binding"],
            "canonicalSha256": "f" * 64,
        }

    result = MODULE.probe_runtime(**kwargs)

    assert not responses
    assert result["sourceTemplateBinding"]["passed"] is binding_matches
    assert result["passed"] is binding_matches


def test_probe_runtime_never_mixes_readiness_attempts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class TwoAttemptProcess:
        def __init__(self) -> None:
            self.polls = 0

        def poll(self) -> int | None:
            self.polls += 1
            return None if self.polls <= 2 else 1

    calls: list[str] = []
    responses = [
        (200, {"status": "ok"}),
        (200, _deep_readiness_payload("generation-a")),
        (200, _publication_readiness_payload("generation-b")),
        (200, {"status": "ok"}),
        (200, _deep_readiness_payload("generation-b")),
        (200, _publication_readiness_payload("generation-a")),
    ]

    def fetch(url: str, **_kwargs: object):
        calls.append(url)
        status, payload = responses.pop(0)
        return status, payload, json.dumps(payload).encode(), {}

    kwargs, _events = _install_probe_runtime_fakes(
        tmp_path,
        monkeypatch,
        fetch,
        process=TwoAttemptProcess(),
    )

    result = MODULE.probe_runtime(**kwargs)

    assert not result["passed"]
    assert result["readinessProbe"]["attempts"] == 2
    assert result["coherentReadinessSampleObserved"] is False
    assert not any("/downloads/" in url for url in calls)
    assert not responses


def test_probe_runtime_rechecks_identity_after_bound_manifest_reads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class RunningProcess:
        def poll(self) -> None:
            return None

    canonical = manifest()
    compatibility = compatibility_manifest(canonical)
    expected_paths = [
        "/api/health",
        "/api/ready",
        "/api/ready/publication",
        f"/downloads/{MODULE.CANONICAL}",
        f"/downloads/{MODULE.COMPATIBILITY}",
        "/api/ready",
        "/api/ready/publication",
    ]
    responses = [
        (200, {"status": "ok"}, {}),
        (200, _deep_readiness_payload("generation-a"), {}),
        (200, _publication_readiness_payload("generation-a"), {}),
        (
            200,
            canonical,
            {"x-chummer-release-generation": ("generation-a",)},
        ),
        (
            200,
            compatibility,
            {"x-chummer-release-generation": ("generation-a",)},
        ),
        (200, _deep_readiness_payload("generation-b"), {}),
        (200, _publication_readiness_payload("generation-b"), {}),
    ]
    observed_paths: list[str] = []

    def fetch(url: str, **_kwargs: object):
        prefix = "https://127.0.0.1:8443"
        assert url.startswith(prefix)
        observed_paths.append(url.removeprefix(prefix))
        status, payload, headers = responses.pop(0)
        return status, payload, json.dumps(payload).encode(), headers

    kwargs, _events = _install_probe_runtime_fakes(
        tmp_path,
        monkeypatch,
        fetch,
        process=RunningProcess(),
    )

    result = MODULE.probe_runtime(**kwargs)

    assert observed_paths == expected_paths
    assert not responses
    assert result["canonical"]["preparedGenerationBinding"]["passed"]
    assert result["compatibility"]["preparedGenerationBinding"]["passed"]
    assert not result["postManifestReadiness"]["passed"]
    assert not result["passed"]


def test_probe_runtime_binds_the_full_generation_not_only_manifests(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class RunningProcess:
        def poll(self) -> None:
            return None

    canonical = manifest()
    compatibility = compatibility_manifest(canonical)
    responses = [
        (200, {"status": "ok"}, {}),
        (200, _deep_readiness_payload("generation-a"), {}),
        (200, _publication_readiness_payload("generation-a"), {}),
        (200, canonical, {"x-chummer-release-generation": ("generation-a",)}),
        (200, compatibility, {"x-chummer-release-generation": ("generation-a",)}),
        (200, _deep_readiness_payload("generation-a"), {}),
        (200, _publication_readiness_payload("generation-a"), {}),
    ]

    def fetch_json(_url: str, **_kwargs: object):
        status, payload, headers = responses.pop(0)
        return status, payload, json.dumps(payload).encode(), headers

    def fetch_artifact(_url: str, **_kwargs: object):
        artifact = (
            tmp_path
            / "downloads"
            / "generations"
            / "generation-a"
            / "files"
            / "a.bin"
        )
        artifact.write_bytes(b"mutated-after-runtime-read")
        return (
            200,
            FIXTURE_ARTIFACT_BYTES,
            {"x-chummer-release-generation": ("generation-a",)},
        )

    kwargs, _events = _install_probe_runtime_fakes(
        tmp_path,
        monkeypatch,
        fetch_json,
        process=RunningProcess(),
        artifact_fetch=fetch_artifact,
    )

    result = MODULE.probe_runtime(**kwargs)

    assert not responses
    assert result["artifactDelivery"]["passed"]
    assert result["preparedManifestBytesUnchanged"]
    assert not result["preparedGenerationWasUnchanged"]
    assert not result["passed"]


def test_probe_runtime_requires_process_alive_after_final_bound_sample(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ExitAfterResponsesProcess:
        def __init__(self) -> None:
            self.polls = 0

        def poll(self) -> int | None:
            self.polls += 1
            return None if self.polls <= 2 else 17

    canonical = manifest()
    compatibility = compatibility_manifest(canonical)
    responses = [
        (200, {"status": "ok"}, {}),
        (200, _deep_readiness_payload("generation-a"), {}),
        (200, _publication_readiness_payload("generation-a"), {}),
        (
            200,
            canonical,
            {"x-chummer-release-generation": ("generation-a",)},
        ),
        (
            200,
            compatibility,
            {"x-chummer-release-generation": ("generation-a",)},
        ),
        (200, _deep_readiness_payload("generation-a"), {}),
        (200, _publication_readiness_payload("generation-a"), {}),
    ]

    def fetch(_url: str, **_kwargs: object):
        status, payload, headers = responses.pop(0)
        return status, payload, json.dumps(payload).encode(), headers

    kwargs, _events = _install_probe_runtime_fakes(
        tmp_path,
        monkeypatch,
        fetch,
        process=ExitAfterResponsesProcess(),
    )

    result = MODULE.probe_runtime(**kwargs)

    assert not responses
    assert result["postManifestReadiness"]["passed"]
    assert result["processExitCodeAfterFinalProbe"] == 17
    assert result["aliveThroughFinalBoundSample"] is False
    assert not result["passed"]


def test_probe_runtime_never_passes_with_context_teardown_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class RunningProcess:
        def poll(self) -> None:
            return None

    canonical = manifest()
    compatibility = compatibility_manifest(canonical)
    responses = [
        (200, {"status": "ok"}, {}),
        (200, _deep_readiness_payload("generation-a"), {}),
        (200, _publication_readiness_payload("generation-a"), {}),
        (
            200,
            canonical,
            {"x-chummer-release-generation": ("generation-a",)},
        ),
        (
            200,
            compatibility,
            {"x-chummer-release-generation": ("generation-a",)},
        ),
        (200, _deep_readiness_payload("generation-a"), {}),
        (200, _publication_readiness_payload("generation-a"), {}),
    ]

    def fetch(_url: str, **_kwargs: object):
        status, payload, headers = responses.pop(0)
        return status, payload, json.dumps(payload).encode(), headers

    kwargs, _events = _install_probe_runtime_fakes(
        tmp_path,
        monkeypatch,
        fetch,
        process=RunningProcess(),
        runtime_exit_error=RuntimeError("runtime teardown failed"),
    )

    result = MODULE.probe_runtime(**kwargs)

    assert not responses
    assert result["postManifestReadiness"]["passed"]
    assert result["aliveThroughFinalBoundSample"]
    assert "runtime teardown failed" in result["error"]
    assert not result["passed"]


def test_sigterm_escapes_probe_and_unwinds_nested_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class RunningProcess:
        def poll(self) -> None:
            return None

    monkeypatch.setattr(MODULE.signal, "signal", lambda *_args: None)

    def cancel(_url: str, **_kwargs: object):
        (
            tmp_path
            / "downloads"
            / "generations"
            / "generation-a"
            / MODULE.CANONICAL
        ).unlink()
        MODULE._terminate_for_signal(MODULE.signal.SIGTERM, None)

    kwargs, events = _install_probe_runtime_fakes(
        tmp_path,
        monkeypatch,
        cancel,
        process=RunningProcess(),
    )

    with pytest.raises(MODULE.PreflightCancelled, match="SIGTERM"):
        MODULE.probe_runtime(**kwargs)

    assert events == [
        "runtime-exit",
        "postgres-exit",
        "remove-secrets",
        "remove-state",
    ]


def test_manifest_identity_must_match_prepared_release() -> None:
    payload = manifest()
    expected = {
        "version": "release-a",
        "channel": "preview",
        "publishedAt": "2026-07-16T12:00:00+00:00",
    }

    assert MODULE.manifest_matches_release_identity(payload, expected)
    payload["version"] = "release-b"
    assert not MODULE.manifest_matches_release_identity(payload, expected)


def _write_live_envelope_fixture(
    tmp_path: Path,
) -> tuple[Path, Path, Path, dict]:
    canonical = tmp_path / MODULE.CANONICAL
    compatibility = tmp_path / MODULE.COMPATIBILITY
    canonical_payload = manifest()
    compatibility_payload = copy.deepcopy(canonical_payload)
    canonical.write_text(json.dumps(canonical_payload), encoding="utf-8")
    compatibility.write_text(json.dumps(compatibility_payload), encoding="utf-8")
    receipt = tmp_path / "verification.receipt.json"
    payload = {
        "schemaVersion": MODULE.LIVE_ENVELOPE_RECEIPT_SCHEMA,
        "state": "completed",
        "operation": MODULE.LIVE_ENVELOPE_RECEIPT_OPERATION,
        "publicationMutation": False,
        "artifactBytesChanged": False,
        "containerRestarted": False,
        "version": "release-a",
        "publishedAt": "2026-07-16T12:00:00Z",
        "source": {
            "afterSha256": MODULE.sha256_file(canonical),
            "releasesSourceSha256": MODULE.sha256_file(compatibility),
        },
        "servedCanonical": {
            "beforeSha256": "1" * 64,
            "afterSha256": "2" * 64,
            "originSha256": "2" * 64,
            "publicSha256": "2" * 64,
            "originPublicByteIdentical": True,
            "artifactInventoryDigest": MODULE.sha256_bytes(
                MODULE.canonical_json_bytes(canonical_payload["artifacts"])
            ),
            "artifactInventoryUnchanged": True,
            "proofFreshnessStatus": "stale",
            "rolloutState": "public_release_review_required",
            "supportabilityState": "review_required",
            "publicTrustPosture": "blocked",
            "publicTrustSupportabilityState": "review_required",
            "registryPublicTrustPosture": "blocked",
            "registrySupportabilityState": "review_required",
            "optimisticNarrativeRemoved": True,
        },
        "servedReleases": {
            "originSha256": "3" * 64,
            "publicSha256": "3" * 64,
            "originPublicByteIdentical": True,
            "rolloutState": "public_release_review_required",
            "supportabilityState": "review_required",
        },
        "runtime": {
            "statusOriginHttpStatus": 200,
            "statusPublicHttpStatus": 200,
            "statusCacheControl": "private, no-store, max-age=0",
            "containerIdentityAndConfigDigestBefore": "4" * 64,
            "containerIdentityAndConfigDigestAfter": "4" * 64,
            "containerIdentityAndConfigUnchanged": True,
        },
    }
    receipt.write_text(json.dumps(payload), encoding="utf-8")
    return canonical, compatibility, receipt, payload


def test_live_envelope_receipt_requires_digest_and_completed_truth_contract(
    tmp_path: Path,
) -> None:
    canonical, compatibility, receipt, payload = _write_live_envelope_fixture(tmp_path)
    receipt_digest = MODULE.sha256_file(receipt)

    snapshot = MODULE.materialize_live_envelope_snapshot(
        canonical,
        compatibility,
        receipt,
        receipt_digest,
        tmp_path / "snapshot-good",
    )
    assert MODULE._envelope_binding(snapshot)["passed"]
    with pytest.raises(MODULE.PreflightError, match="operator-supplied SHA-256"):
        MODULE.materialize_live_envelope_snapshot(
            canonical,
            compatibility,
            receipt,
            "0" * 64,
            tmp_path / "snapshot-wrong-pin",
        )
    payload["servedCanonical"]["supportabilityState"] = "preview_supported"
    receipt.write_text(json.dumps(payload), encoding="utf-8")
    invalid_snapshot = MODULE.materialize_live_envelope_snapshot(
        canonical,
        compatibility,
        receipt,
        MODULE.sha256_file(receipt),
        tmp_path / "snapshot-invalid-contract",
    )
    assert not MODULE._envelope_binding(invalid_snapshot)["passed"]


@pytest.mark.parametrize(
    ("target", "mutation"),
    (
        ("canonical", "optimistic"),
        ("compatibility", "optimistic"),
        ("canonical", "malformed-inventory"),
        ("compatibility", "malformed-inventory"),
        ("canonical", "revoked"),
        ("compatibility", "revoked"),
    ),
)
def test_live_envelope_binding_validates_authenticated_template_semantics(
    tmp_path: Path,
    target: str,
    mutation: str,
) -> None:
    canonical, compatibility, receipt, receipt_payload = _write_live_envelope_fixture(
        tmp_path
    )
    target_path = canonical if target == "canonical" else compatibility
    payload = json.loads(target_path.read_text(encoding="utf-8"))
    if mutation == "optimistic":
        payload["supportabilityState"] = "preview_supported"
    elif mutation == "revoked":
        payload["status"] = "revoked"
    else:
        payload["artifacts"] = "not-a-list"
    target_path.write_text(json.dumps(payload), encoding="utf-8")
    receipt_payload["source"][
        "afterSha256" if target == "canonical" else "releasesSourceSha256"
    ] = MODULE.sha256_file(target_path)
    receipt.write_text(json.dumps(receipt_payload), encoding="utf-8")

    snapshot = MODULE.materialize_live_envelope_snapshot(
        canonical,
        compatibility,
        receipt,
        MODULE.sha256_file(receipt),
        tmp_path / f"snapshot-{target}-{mutation}",
    )
    binding = MODULE._envelope_binding(snapshot)

    assert not binding["semanticContractValid"]
    assert not binding["passed"]


@pytest.mark.parametrize(
    ("path", "value"),
    (
        (("servedCanonical", "publicSha256"), "5" * 64),
        (("servedCanonical", "artifactInventoryDigest"), "5" * 64),
        (("servedReleases", "publicSha256"), "5" * 64),
        (("runtime", "containerIdentityAndConfigDigestAfter"), "5" * 64),
    ),
)
def test_live_envelope_receipt_binds_supporting_hash_evidence(
    tmp_path: Path,
    path: tuple[str, ...],
    value: str,
) -> None:
    canonical, compatibility, receipt, payload = _write_live_envelope_fixture(tmp_path)
    target = payload
    for segment in path[:-1]:
        target = target[segment]
    target[path[-1]] = value
    receipt.write_text(json.dumps(payload), encoding="utf-8")

    snapshot = MODULE.materialize_live_envelope_snapshot(
        canonical,
        compatibility,
        receipt,
        MODULE.sha256_file(receipt),
        tmp_path / "snapshot-invalid-supporting-hash",
    )
    binding = MODULE._envelope_binding(snapshot)

    assert not binding["receiptContractValid"]
    assert not binding["passed"]


def test_live_envelope_binding_uses_only_retained_snapshot_after_materialization(
    tmp_path: Path,
) -> None:
    canonical, compatibility, receipt, _payload = _write_live_envelope_fixture(tmp_path)
    snapshot = MODULE.materialize_live_envelope_snapshot(
        canonical,
        compatibility,
        receipt,
        MODULE.sha256_file(receipt),
        tmp_path / "snapshot",
    )
    expected_binding = MODULE._envelope_binding(snapshot)

    canonical.unlink()
    compatibility.write_text('{"forged":true}\n', encoding="utf-8")
    receipt.unlink()

    assert MODULE._envelope_binding(snapshot) == expected_binding
    assert MODULE.build_live_envelope_snapshot_closure(snapshot.root) == snapshot.closure


@pytest.mark.parametrize(
    ("target", "raw"),
    (
        ("canonical", b'{"version":"a","version":"b"}\n'),
        ("compatibility", b'{"channel":NaN}\n'),
        ("compatibility", b'{"channel":"preview","metric":1e999}\n'),
        ("receipt", b'{"source":{},"source":{}}\n'),
    ),
)
def test_live_envelope_snapshot_rejects_non_strict_json(
    tmp_path: Path,
    target: str,
    raw: bytes,
) -> None:
    canonical, compatibility, receipt, payload = _write_live_envelope_fixture(tmp_path)
    paths = {
        "canonical": canonical,
        "compatibility": compatibility,
        "receipt": receipt,
    }
    paths[target].write_bytes(raw)
    if target != "receipt":
        source = payload["source"]
        digest = MODULE.sha256_bytes(raw)
        source[
            "afterSha256" if target == "canonical" else "releasesSourceSha256"
        ] = digest
        receipt.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(MODULE.PreflightError, match="strict UTF-8 JSON"):
        MODULE.materialize_live_envelope_snapshot(
            canonical,
            compatibility,
            receipt,
            MODULE.sha256_file(receipt),
            tmp_path / "snapshot",
        )


def test_live_envelope_snapshot_closure_rejects_mutation_and_extra_entries(
    tmp_path: Path,
) -> None:
    canonical, compatibility, receipt, _payload = _write_live_envelope_fixture(tmp_path)
    snapshot = MODULE.materialize_live_envelope_snapshot(
        canonical,
        compatibility,
        receipt,
        MODULE.sha256_file(receipt),
        tmp_path / "snapshot",
    )
    snapshot.canonical.retained_path.chmod(0o600)
    with pytest.raises(MODULE.PreflightError, match="owner-read-only"):
        MODULE.build_live_envelope_snapshot_closure(snapshot.root)

    snapshot.canonical.retained_path.chmod(0o400)
    extra = snapshot.root / "extra.json"
    extra.write_text("{}\n", encoding="utf-8")
    extra.chmod(0o400)
    with pytest.raises(MODULE.PreflightError, match="unexpected entry set"):
        MODULE.build_live_envelope_snapshot_closure(snapshot.root)


def test_output_root_rejects_symlink_components_and_candidate_writes(
    tmp_path: Path,
) -> None:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    real = tmp_path / "real"
    real.mkdir()
    redirected = tmp_path / "redirected"
    redirected.symlink_to(real, target_is_directory=True)

    with pytest.raises(MODULE.PreflightError, match="symbolic-link component"):
        MODULE.prepare_output_root(redirected / "output", candidate)
    with pytest.raises(MODULE.PreflightError, match="outside the candidate"):
        MODULE.prepare_output_root(candidate / "output", candidate)


def test_run_command_never_persists_or_receipts_raw_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = b"Authorization: " + b"Bear" + b"er must-not-survive"
    monkeypatch.setattr(
        MODULE.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=args[0],
            returncode=1,
            stdout=secret,
            stderr=secret,
        ),
    )

    result = MODULE.run_command(
        "opaque",
        ("/usr/bin/true",),
        cwd=tmp_path,
        environment={},
        log_root=tmp_path / "logs",
        timeout_seconds=1,
    )

    assert "must-not-survive" not in json.dumps(result.to_json())
    assert result.stdout_tail == MODULE.OUTPUT_WITHHELD
    assert result.stderr_tail == MODULE.OUTPUT_WITHHELD
    assert not (tmp_path / "logs").exists()


def test_reuse_evidence_hashes_and_parses_one_exact_byte_snapshot(tmp_path: Path) -> None:
    receipt, context = first_pass_reuse_fixture(tmp_path)
    receipt_path = context["evidence_path"]
    MODULE.atomic_write_json(receipt_path, receipt)
    pinned = MODULE.sha256_file(receipt_path)

    loaded, actual = MODULE.read_operator_pinned_json_object(
        receipt_path,
        pinned,
        "reused preflight evidence",
    )

    assert loaded == receipt
    assert actual == pinned
    MODULE.validate_first_pass_reuse_evidence(loaded, **context)

    receipt_path.write_bytes(receipt_path.read_bytes() + b" ")
    with pytest.raises(MODULE.PreflightError, match="operator-supplied SHA-256"):
        MODULE.read_operator_pinned_json_object(
            receipt_path,
            pinned,
            "reused preflight evidence",
        )


def test_reuse_evidence_rejects_mutated_first_pass_live_envelope_snapshot(
    tmp_path: Path,
) -> None:
    receipt, context = first_pass_reuse_fixture(tmp_path)
    retained = (
        context["evidence_path"].parent
        / "live-envelope-snapshot"
        / MODULE.CANONICAL
    )
    retained.chmod(0o600)
    retained.write_bytes(b'{"canonical":"mutated"}\n')
    retained.chmod(0o400)

    with pytest.raises(MODULE.PreflightError, match="snapshot bytes drifted"):
        MODULE.validate_first_pass_reuse_evidence(receipt, **context)


def test_reuse_evidence_rejects_duplicate_json_properties_even_when_pinned(
    tmp_path: Path,
) -> None:
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text('{"state":"completed","state":"forged"}\n', encoding="utf-8")

    with pytest.raises(MODULE.PreflightError, match="duplicate JSON property"):
        MODULE.read_operator_pinned_json_object(
            receipt_path,
            MODULE.sha256_file(receipt_path),
            "reused preflight evidence",
        )


def test_reuse_evidence_rejects_numeric_overflow_even_when_pinned(tmp_path: Path) -> None:
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text('{"state":"completed","startedAt":1e999}\n', encoding="utf-8")

    with pytest.raises(MODULE.PreflightError, match="non-finite JSON number"):
        MODULE.read_operator_pinned_json_object(
            receipt_path,
            MODULE.sha256_file(receipt_path),
            "reused preflight evidence",
        )


@pytest.mark.parametrize(
    ("started_at", "completed_at"),
    (
        ({"not": "a timestamp"}, "2026-07-16T12:10:00Z"),
        ("2026-07-16T12:00:00Z", []),
        ("2026-07-16T12:00:00", "2026-07-16T12:10:00Z"),
        ("2026-07-16T12:10:01Z", "2026-07-16T12:10:00Z"),
    ),
)
def test_reuse_evidence_requires_ordered_timezone_aware_timestamps(
    tmp_path: Path,
    started_at: object,
    completed_at: object,
) -> None:
    receipt, context = first_pass_reuse_fixture(tmp_path)
    receipt["startedAt"] = started_at
    receipt["completedAt"] = completed_at

    with pytest.raises(MODULE.PreflightError, match="timestamps are malformed"):
        MODULE.validate_first_pass_reuse_evidence(receipt, **context)


def test_reuse_evidence_rejects_pinned_passed_row_gate_and_closure_forgeries(
    tmp_path: Path,
) -> None:
    receipt, context = first_pass_reuse_fixture(tmp_path)
    receipt_path = context["evidence_path"]

    for mutate, expected_error in (
        (
            lambda value: value["commands"].append(copy.deepcopy(value["commands"][-1])),
            "command count is not exact",
        ),
        (
            lambda value: value["commands"][0].update({"name": "arbitrary-passed-row"}),
            "name/order drifted",
        ),
        (
            lambda value: value["gates"].update({"buildClosureOperatorPinned": True}),
            "gate contract is not exact",
        ),
        (
            lambda value: value["sourceClosure"].update({"sha256": "f" * 64}),
            "source closure is not exact",
        ),
        (
            lambda value: value["buildClosure"].update({"operatorPinned": True}),
            "build closure is not exact",
        ),
        (
            lambda value: value["rollbackProbe"].update(
                {"generationABytesUnchanged": False}
            ),
            "rollback probe contract is invalid",
        ),
    ):
        forged = copy.deepcopy(receipt)
        mutate(forged)
        MODULE.atomic_write_json(receipt_path, forged)
        forged_pin = MODULE.sha256_file(receipt_path)
        loaded, _ = MODULE.read_operator_pinned_json_object(
            receipt_path,
            forged_pin,
            "reused preflight evidence",
        )

        with pytest.raises(MODULE.PreflightError, match=expected_error):
            MODULE.validate_first_pass_reuse_evidence(loaded, **context)
