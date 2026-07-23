from __future__ import annotations

import importlib.util
import hashlib
import json
import os
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "materialize_install_linking_cutover_boundary.py"
VERIFIER_SCRIPT = (
    ROOT / "scripts" / "verify_install_linking_cutover_boundary.py"
)
CANDIDATE_IMAGE = "sha256:" + "a" * 64
CANDIDATE_TOOL_IMAGE = "sha256:" + "c" * 64


def load_module():
    spec = importlib.util.spec_from_file_location(
        "materialize_install_linking_cutover_boundary", SCRIPT
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_verifier():
    name = "verify_install_linking_cutover_boundary"
    spec = importlib.util.spec_from_file_location(name, VERIFIER_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def build_info(tmp_path: Path) -> Path:
    path = tmp_path / "INSTALL_LINKING_POSTGRES_CANDIDATE_BUILD_INFO.generated.json"
    suffix = hashlib.sha256(
        b"2026-07-17T12:00:00Z"
    ).hexdigest()[:24]
    package_input_paths = {
        "Directory.Build.props",
        "global.json",
        "eng/NuGet.Container.Config",
        "eng/package-plane.lock.json",
        "scripts/ai/bootstrap-hub-package-feed.py",
        "scripts/public_edge_postdeploy_contract.py",
        "scripts/public_edge_postdeploy_gate.v1.schema.json",
        "Chummer.InstallLinking.Postgres.Tool/Chummer.InstallLinking.Postgres.Tool.csproj",
        "Chummer.Run.LoopbackProbe/Chummer.Run.LoopbackProbe.csproj",
        "Chummer.Run.LoopbackProbe/packages.lock.json",
        "Chummer.Run.LoopbackProbe/Program.cs",
        "Chummer.Run.Api/Chummer.Run.Api.csproj",
        "Chummer.Run.Api/packages.lock.json",
        "Chummer.Campaign.Contracts/Chummer.Campaign.Contracts.csproj",
        "Chummer.Campaign.Contracts/packages.lock.json",
        "Chummer.Control.Contracts/Chummer.Control.Contracts.csproj",
        "Chummer.Control.Contracts/packages.lock.json",
        "Chummer.Play.Contracts/Chummer.Play.Contracts.csproj",
        "Chummer.Play.Contracts/packages.lock.json",
        "Chummer.Run.Contracts/Chummer.Run.Contracts.csproj",
        "Chummer.Run.Contracts/packages.lock.json",
        "Chummer.World.Contracts/Chummer.World.Contracts.csproj",
        "Chummer.World.Contracts/packages.lock.json",
    }
    package_inputs = {
        input_path: hashlib.sha256(input_path.encode("utf-8")).hexdigest()
        for input_path in package_input_paths
    }
    postdeploy_schema_sha256 = hashlib.sha256(
        (
            ROOT
            / "scripts"
            / "public_edge_postdeploy_gate.v1.schema.json"
        ).read_bytes()
    ).hexdigest()
    package_inputs[
        "scripts/public_edge_postdeploy_gate.v1.schema.json"
    ] = postdeploy_schema_sha256
    package_input_set_sha256 = hashlib.sha256(
        (
            json.dumps(package_inputs, indent=2, sort_keys=True)
            + "\n"
        ).encode("utf-8")
    ).hexdigest()
    payload = {
        "buildSourceProvenance": {
            **{
                name: {
                    "consumedPathSha256": marker * 64,
                    "contextFileSetSha256": marker * 64,
                    "head": (
                        "4" * 40
                        if name == "run-services-source"
                        else marker * 40
                    ),
                    "ignoredInputCount": 0,
                    "originMain": (
                        "4" * 40
                        if name == "run-services-source"
                        else marker * 40
                    ),
                    "originUrlSha256": hashlib.sha256(
                        url.encode("utf-8")
                    ).hexdigest(),
                    "repositoryRootSha256": marker * 64,
                    "sensitivePathCount": 0,
                    "trackedInputCount": 10,
                }
                for name, marker, url in (
                    (
                        "run-services-source",
                        "5",
                        "https://github.com/ArchonMegalon/chummer6-hub.git",
                    ),
                    (
                        "hub-registry",
                        "6",
                        "https://github.com/ArchonMegalon/chummer6-hub-registry.git",
                    ),
                    (
                        "design-product",
                        "7",
                        "https://github.com/ArchonMegalon/chummer6-design.git",
                    ),
                    (
                        "fleet-media-factory-contracts",
                        "8",
                        "https://github.com/ArchonMegalon/chummer6-media-factory.git",
                    ),
                )
            },
            "canonical-build-context": {
                "consumedPathSha256": "9" * 64,
                "dockerignoreSha256": "a" * 64,
            },
            "build-dependency-contract": {
                "baseImages": {
                    "build": (
                        "mcr.microsoft.com/dotnet/sdk:10.0.103@sha256:"
                        "e362a8dbcd691522456da26a5198b8f3ca1d7641c95624fadc5e3e82678bd08a"
                    ),
                    "final": (
                        "mcr.microsoft.com/dotnet/aspnet:10.0@sha256:"
                        "1fa23fc4872d95fd71c2833ebe65d7e84a43b2d51a31d119516852f13d9505a7"
                    ),
                    "hub-package-feed": (
                        "mcr.microsoft.com/dotnet/sdk:10.0.103@sha256:"
                        "e362a8dbcd691522456da26a5198b8f3ca1d7641c95624fadc5e3e82678bd08a"
                    ),
                    "install-linking-postgres-tool-final": (
                        "mcr.microsoft.com/dotnet/aspnet:10.0@sha256:"
                        "1fa23fc4872d95fd71c2833ebe65d7e84a43b2d51a31d119516852f13d9505a7"
                    ),
                    "public-pwa-proof": (
                        "python:3.12-slim@sha256:"
                        "c3d81d25b3154142b0b42eb1e61300024426268edeb5b5a26dd7ddf64d9daf28"
                    ),
                },
                "contextPolicies": {
                    "canonical-build-context": {
                        "contextBoundary": (
                            "canonical-root-with-explicit-allowlist"
                        ),
                        "dockerignoreSha256": "a" * 64,
                        "effectiveDockerignoreSha256": "b" * 64,
                        "repositoryContained": True,
                    },
                    "design-product": {
                        "contextBoundary": "exact-clean-repository",
                        "dockerignoreSha256": "c" * 64,
                        "effectiveDockerignoreSha256": "c" * 64,
                        "repositoryContained": True,
                    },
                    "fleet-media-factory-contracts": {
                        "contextBoundary": (
                            "exact-clean-repository-subtree"
                        ),
                        "dockerignoreSha256": None,
                        "effectiveDockerignoreSha256": None,
                        "repositoryContained": True,
                    },
                    "run-services-source": {
                        "contextBoundary": "exact-clean-repository",
                        "dockerignoreSha256": "d" * 64,
                        "effectiveDockerignoreSha256": "d" * 64,
                        "repositoryContained": True,
                    },
                },
                "contractName": (
                    "chummer.install_linking_postgres_build_dependency_provenance.v1"
                ),
                "dockerfileFrontend": (
                    "docker/dockerfile:1.4@sha256:"
                    "9ba7531bd80fb0a858632727cf7a112fbfd19b17e94c4e84ced81e24ef1a0dbc"
                ),
                "dockerfileSha256": "e" * 64,
                "externalMediaProjectSha256": "f" * 64,
                "externalMediaRestoreIsSdkOnly": True,
                "loopbackProbeIsSdkOnly": True,
                "loopbackProbeProgramSha256": package_inputs[
                    "Chummer.Run.LoopbackProbe/Program.cs"
                ],
                "loopbackProbeProjectSha256": package_inputs[
                    "Chummer.Run.LoopbackProbe/Chummer.Run.LoopbackProbe.csproj"
                ],
                "packageInputSetSha256": package_input_set_sha256,
                "packageInputs": package_inputs,
                "packagePlaneContract": (
                    "chummer-hub.package-plane-lock/v4"
                ),
                "packagePlanePackageCount": 6,
                "postdeploySchemaContractName": (
                    "chummer.public_edge_postdeploy_gate.schema.v1"
                ),
                "postdeploySchemaSha256": postdeploy_schema_sha256,
                "runtimePackageManagerInvocationCount": 0,
                "status": "pass",
            },
        },
        "candidateImageId": CANDIDATE_IMAGE,
        "candidatePortalTag": f"chummer-run-api:cutover-{suffix}",
        "candidateToolImageId": CANDIDATE_TOOL_IMAGE,
        "candidateToolTag": (
            f"chummer-install-linking-postgres-tool:cutover-{suffix}"
        ),
        "canonicalPortalTagIdBeforeAndAfter": "sha256:" + "d" * 64,
        "canonicalToolTagIdBeforeAndAfter": None,
        "composeSha256": "1" * 64,
        "contractName": (
            "chummer.install_linking_postgres_candidate_build_info.v1"
        ),
        "cutoverId": "2026-07-17T12:00:00Z",
        "envSha256": "2" * 64,
        "generatedAtUtc": "2026-07-17T11:59:00+00:00",
        "operatorCriticalEnvironmentSha256": {
            "chummer-install-linking-postgres-admin": "b" * 64,
            "chummer-install-linking-postgres-import-presence-proof": "c"
            * 64,
            "chummer-install-linking-postgres-runtime-proof": "d" * 64,
        },
        "operatorMountSourceSha256": {
            "chummer-install-linking-postgres-admin": {
                "/run/chummer-secrets/install-linking-postgres-migrator.connection-string": "5"
                * 64,
                "/run/chummer-secrets/install-linking-postgres-server-ca.pem": "6"
                * 64,
            },
            "chummer-install-linking-postgres-import-presence-proof": {
                "/app/state": "7" * 64,
            },
            "chummer-install-linking-postgres-runtime-proof": {
                "/run/chummer-secrets/install-linking-postgres-runtime.connection-string": "8"
                * 64,
                "/run/chummer-secrets/install-linking-postgres-server-ca.pem": "6"
                * 64,
            },
        },
        "publicNetworkId": "a" * 64,
        "publicNetworkName": "chummer5a_default",
        "runnerSha256": "3" * 64,
        "sourceHead": "4" * 40,
        "status": "pass",
        "uniqueTagsPreserveCanonicalRecoveryAuthority": True,
    }
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    path.chmod(0o600)
    return path


def write_canonical(module, path: Path, payload: dict) -> str:
    rendered = module.canonical_json_bytes(payload, label=path.name)
    path.write_bytes(rendered)
    path.chmod(0o600)
    return hashlib.sha256(rendered).hexdigest()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def rewrite_job_chain(module, evidence_path: Path, index: int, job: dict) -> None:
    evidence = read_json(evidence_path)
    reference = evidence["jobReceipts"][index]
    job_path = Path(reference["path"])
    reference["sha256"] = write_canonical(module, job_path, job)
    aggregate = hashlib.sha256()
    for item in evidence["jobReceipts"]:
        aggregate.update(item["name"].encode())
        aggregate.update(b"\0")
        aggregate.update(item["sha256"].encode())
        aggregate.update(b"\n")
    evidence["jobReceiptChainSha256"] = aggregate.hexdigest()
    write_canonical(module, evidence_path, evidence)


def proof_payload(job_name: str) -> dict:
    payloads = {
        "transport-proof": {
            "authenticated": True,
            "authorityIdentitySha256": "e" * 64,
            "contractName": "chummer.postgres_transport_proof.v1",
            "gssEncryptionDisabled": True,
            "pgStatSsl": True,
            "plaintextAttempted": True,
            "plaintextRejected": True,
            "plaintextSqlState": "28000",
            "status": "pass",
        },
        "prepare": {
            "appliedSchemaVersion": 2,
            "authorityIdentitySha256": "e" * 64,
            "contractName": "chummer.install_linking_postgres_prepare.v1",
            "leastPrivilegeValid": True,
            "runtimeRoleSha256": "9" * 64,
            "status": "pass",
        },
        "prove-empty-authority": {
            "appliedSchemaVersion": 2,
            "authorityIdentitySha256": "e" * 64,
            "commitCount": 0,
            "contractName": (
                "chummer.install_linking_postgres_empty_authority_proof.v1"
            ),
            "currentRoleMatches": True,
            "empty": True,
            "headGeneration": 0,
            "leastPrivilegeValid": True,
            "runtimeRoleSha256": "9" * 64,
            "schemaValid": True,
            "status": "pass",
        },
        "prove-runtime-role": {
            "authorityIdentitySha256": "e" * 64,
            "contractName": (
                "chummer.install_linking_postgres_runtime_role_proof.v1"
            ),
            "currentRoleMatches": True,
            "leastPrivilegeValid": True,
            "runtimeRoleSha256": "9" * 64,
            "status": "pass",
        },
        "prove-local-store-absent": {
            "checkedPathCount": 3,
            "contractName": (
                "chummer.install_linking_local_store_absence_proof.v1"
            ),
            "localStorePresent": False,
            "status": "pass",
        },
        "validate": {
            "appliedSchemaVersion": 2,
            "authorityIdentitySha256": "e" * 64,
            "contractName": (
                "chummer.install_linking_postgres_schema_validation.v1"
            ),
            "status": "pass",
        },
    }
    if job_name not in payloads and job_name.startswith("postquiesce-"):
        for proof_kind in (
            "prove-local-store-absent",
            "prove-empty-authority",
            "prove-runtime-role",
        ):
            if job_name.endswith(f"-{proof_kind}"):
                job_name = proof_kind
                break
    return payloads[job_name]


def state_volume_inventory(
    module,
    root: Path,
    *,
    attempt_id: str = "attempt01",
    mutation_lock_token_sha256: str = "f" * 64,
) -> tuple[Path, str]:
    path = root / (
        "INSTALL_LINKING_STATE_VOLUME_INVENTORY."
        f"post-incumbent-quiesce.{attempt_id}.json"
    )
    consumers: list[dict] = []
    digest = write_canonical(
        module,
        path,
        {
            "attemptId": attempt_id,
            "candidateToolImageId": CANDIDATE_TOOL_IMAGE,
            "checkpoint": "post_incumbent_quiesce",
            "consumerCount": 0,
            "consumerSetSha256": hashlib.sha256(
                json.dumps(
                    consumers,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                ).encode("utf-8")
            ).hexdigest(),
            "consumers": consumers,
            "contractName": module.STATE_VOLUME_INVENTORY_CONTRACT,
            "cutoverId": "2026-07-17T12:00:00Z",
            "incumbentPortalContainerId": None,
            "mutationLockTokenSha256": mutation_lock_token_sha256,
            "status": "pass",
            "volumeName": "chummer6-hub_chummer-run-api-state",
        },
    )
    return path, digest


def phase_evidence(
    module,
    root: Path,
    active_build_info: Path,
    phase: str,
    *,
    boundary_output: Path | None = None,
    postquiesce_attempt_id: str = "attempt01",
) -> Path:
    build_sha = hashlib.sha256(active_build_info.read_bytes()).hexdigest()
    build_payload = read_json(active_build_info)
    if phase == "public_acceptance_completed":
        assert boundary_output is not None
        postquiesce_phase_path = phase_evidence(
            module,
            root,
            active_build_info,
            module.POSTQUIESCE_REPROOF_PHASE,
            boundary_output=boundary_output,
            postquiesce_attempt_id=postquiesce_attempt_id,
        )
        postquiesce_phase_sha = hashlib.sha256(
            postquiesce_phase_path.read_bytes()
        ).hexdigest()
        volume_inventory_path, volume_inventory_sha = (
            state_volume_inventory(
                module,
                root,
                attempt_id=postquiesce_attempt_id,
            )
        )
        postquiesce_path = root / (
            "INSTALL_LINKING_POSTGRES_POSTQUIESCE_REPROOF."
            f"{postquiesce_attempt_id}.json"
        )
        postquiesce_sha = write_canonical(
            module,
            postquiesce_path,
            {
                "activeBuildInfoPath": str(active_build_info),
                "activeBuildInfoSha256": build_sha,
                "attemptId": postquiesce_attempt_id,
                "boundaryReceiptPath": str(boundary_output),
                "boundaryReceiptSha256": hashlib.sha256(
                    boundary_output.with_name(
                        f"{boundary_output.name}.validate_completed.json"
                    ).read_bytes()
                ).hexdigest(),
                "candidateImageId": CANDIDATE_IMAGE,
                "candidatePortalTag": build_payload["candidatePortalTag"],
                "candidateToolImageId": CANDIDATE_TOOL_IMAGE,
                "candidateToolTag": build_payload["candidateToolTag"],
                "containerStartMayHaveBeenInvoked": True,
                "contractName": module.POSTQUIESCE_REPROOF_CONTRACT,
                "cutoverId": "2026-07-17T12:00:00Z",
                "finishedAtUtc": "2026-07-17T12:00:04+00:00",
                "mutationLockPath": (
                    "/docker/chummercomplete/.state/"
                    "public-edge-mutation.lock"
                ),
                "mutationLockTokenSha256": "f" * 64,
                "phaseEvidencePath": str(postquiesce_phase_path),
                "phaseEvidenceSha256": postquiesce_phase_sha,
                "reason": None,
                "sourceHead": build_payload["sourceHead"],
                "startIntentWritten": True,
                "startedAtUtc": "2026-07-17T12:00:03+00:00",
                "status": "pass",
                "volumeInventoryReceiptPath": str(
                    volume_inventory_path
                ),
                "volumeInventoryReceiptSha256": volume_inventory_sha,
            },
        )
        postdeploy_path = root / "public-edge-postdeploy.json"
        postdeploy = {
            field: None
            for field in module.PUBLIC_EDGE_CUTOVER_POSTDEPLOY_FIELDS
        }
        postdeploy.update(
            {
                "childReceipts": {},
                "codeDeploymentAuthority": True,
                "codeDeployReviewRequiredAuthoritySatisfied": True,
                "contractName": "chummer.public_edge_postdeploy_gate.v1",
                "downloadsStatusBrowserArtifactContract": (
                    "chummer.downloads_status_e2e.v1"
                ),
                "downloadsStatusBrowserStatus": "pass",
                "failures": [],
                "frontdoorNavigationAnchorArtifactContract": (
                    "chummer.frontdoor_mobile_anchor_redirect.v2"
                ),
                "frontdoorNavigationAnchorArtifactCurrentContractSatisfied": True,
                "frontdoorNavigationMobileArtifactContract": (
                    "chummer.frontdoor_mobile_install_boundary.v2"
                ),
                "frontdoorNavigationMobileArtifactInstallContractSatisfied": True,
                "frontdoorNavigationProofClosureSha256": "9" * 64,
                "frontdoorNavigationProofClosureStatus": "pass",
                "frontdoorNavigationStatus": "pass",
                "generatedAtUtc": "2026-07-17T12:00:02+00:00",
                "mobilePwaViewportArtifactContract": (
                    "chummer.mobile_pwa_viewport_smoke.v1"
                ),
                "mobilePwaViewportArtifactCurrentContractSatisfied": True,
                "mobilePwaViewportMissingRoutes": [],
                "mobilePwaViewportStatus": "pass",
                "expectedFullDeploymentDigestSha256": "a" * 64,
                "expectedPwaAssetInventorySha256": "b" * 64,
                "preflightBlockingLockCount": 0,
                "preflightForeignLocksIgnored": False,
                "preflightOverlayBuildInfoSourceFingerprintAggregateMatchesCurrentSource": True,
                "preflightOverlayBuildInfoSourceFingerprintMismatchedKeys": [],
                "preflightOverlayBuildInfoSourceFingerprintMissingKeys": [],
                "preflightStaleForeignLockCount": 0,
                "preflightStaleForeignLocksIgnored": False,
                "preflightStatus": "pass",
                "projectionPurpose": "code-deploy",
                "projectionStage": "code_deploy_review_required",
                "projectionStatus": "review_required",
                "pwaAssetInventoryAnchorMatches": True,
                "pwaFullDeploymentDigestMatchesExpected": True,
                "readyMobileHandoffStatus": "pass",
                "releaseReady": False,
                "releaseUploadAuthority": False,
                "schemaContractName": (
                    module.PUBLIC_EDGE_POSTDEPLOY_SCHEMA_CONTRACT_NAME
                ),
                "schemaSha256": (
                    module.PUBLIC_EDGE_CUTOVER_POSTDEPLOY_SCHEMA_SHA256
                ),
                "skipPreflight": False,
                "skipReleaseVersionMatch": False,
                "status": "pass",
                "strictInvocation": True,
                "strictNoAllowanceInvocation": True,
                "strictPreflight": True,
            }
        )
        postdeploy_sha = write_canonical(
            module,
            postdeploy_path,
            postdeploy,
        )
        runtime_readiness_path = (
            root / "install-linking-authority-readiness.json"
        )
        runtime_readiness_sha = write_canonical(
            module,
            runtime_readiness_path,
            {
                "authorityIdentitySha256": "e" * 64,
                "checkedAtUtc": "2026-07-17T12:00:02+00:00",
                "code": "runtime_role_least_privilege",
                "contractName": (
                    "chummer.install_linking_postgres_"
                    "runtime_authority_readiness.v1"
                ),
                "currentRoleMatches": True,
                "leastPrivilegeValid": True,
                "ready": True,
                "runtimeRoleSha256": "9" * 64,
                "status": "pass",
            },
        )
        active_runtime_path = root / "active-runtime-authority.json"
        active_runtime_sha = write_canonical(
            module,
            active_runtime_path,
            {
                "contractName": (
                    "chummer.public-edge.active-runtime-authority/v1"
                ),
                "generatedAtUtc": "2026-07-17T12:00:02+00:00",
                "installLinkingAuthorityReadinessPath": str(
                    runtime_readiness_path
                ),
                "installLinkingAuthorityReadinessSha256": (
                    runtime_readiness_sha
                ),
                "portal": {
                    "containerId": "6" * 64,
                    "containerName": "chummer-public-edge-candidate-test",
                    "existed": True,
                    "imageId": CANDIDATE_IMAGE,
                    "proofAuthorityMountSha256": "5" * 64,
                    "proofPublicMountSha256": "5" * 64,
                    "wasRunning": True,
                },
                "status": "pass",
            },
        )
        path = root / f"{phase}.evidence.json"
        write_canonical(
            module,
            path,
            {
                "activeRuntimeAuthorityPath": str(active_runtime_path),
                "activeRuntimeAuthoritySha256": active_runtime_sha,
                "candidateBuildInfoSha256": build_sha,
                "candidateContainerImageId": CANDIDATE_IMAGE,
                "candidateImageId": CANDIDATE_IMAGE,
                "candidateToolImageId": CANDIDATE_TOOL_IMAGE,
                "contractName": (
                    "chummer.install_linking_postgres_"
                    "public_acceptance_evidence.v1"
                ),
                "cutoverId": "2026-07-17T12:00:00Z",
                "overlayAccepted": True,
                "postQuiesceReceiptPath": str(postquiesce_path),
                "postQuiesceReceiptSha256": postquiesce_sha,
                "postdeployReceiptPath": str(postdeploy_path),
                "postdeployReceiptSha256": postdeploy_sha,
                "publicReadinessAccepted": True,
                "status": "pass",
            },
        )
        return path

    aggregate = hashlib.sha256()
    references = []
    job_names = (
        module._postquiesce_job_names(postquiesce_attempt_id)
        if phase == module.POSTQUIESCE_REPROOF_PHASE
        else module.EXPECTED_PHASE_JOBS[phase]
    )
    for index, job_name in enumerate(job_names):
        proof_path = root / f"{job_name}.proof.json"
        proof_sha = write_canonical(
            module,
            proof_path,
            proof_payload(job_name),
        )
        service = module._expected_job_service(job_name)
        project = module._job_project("2026-07-17T12:00:00Z", job_name)
        container_name = module._job_container_name(
            "2026-07-17T12:00:00Z",
            job_name,
        )
        container_id = f"{index + 1:x}".rjust(64, "0")
        started_at = "2026-07-17T12:00:00+00:00"
        topology = {
            "capDrop": ["ALL"],
            "command": module._expected_job_command(job_name),
            "composeProject": project,
            "criticalEnvironmentSha256": build_payload[
                "operatorCriticalEnvironmentSha256"
            ][service],
            "extraHostCount": (
                0
                if service
                == "chummer-install-linking-postgres-import-presence-proof"
                else 1
            ),
            "imageId": CANDIDATE_TOOL_IMAGE,
            "labels": {
                "composeConfigHash": "b" * 64,
                "composeOneoff": "False",
                "composeProject": project,
                "composeService": service,
            },
            "mounts": [
                {
                    **mount,
                    "sourceIdentitySha256": build_payload[
                        "operatorMountSourceSha256"
                    ][service][mount["destination"]],
                    "sourceKind": (
                        "volume"
                        if service
                        == "chummer-install-linking-postgres-import-presence-proof"
                        else "bind"
                    ),
                }
                for mount in module.EXPECTED_SERVICE_MOUNTS[service]
            ],
            "networkId": (
                ""
                if service
                == "chummer-install-linking-postgres-import-presence-proof"
                else build_payload["publicNetworkId"]
            ),
            "networkMode": (
                "none"
                if service
                == "chummer-install-linking-postgres-import-presence-proof"
                else build_payload["publicNetworkName"]
            ),
            "noNewPrivileges": True,
            "readOnlyRootFilesystem": True,
            "service": service,
            "tmpfs": module.EXPECTED_TMPFS,
            "user": "1000:1000",
        }
        start_intent_path = root / f"{job_name}.start-intent.json"
        start_intent_sha = write_canonical(
            module,
            start_intent_path,
            {
                "candidateToolImageId": CANDIDATE_TOOL_IMAGE,
                "composeProject": project,
                "containerId": container_id,
                "containerName": container_name,
                "contractName": module.START_INTENT_CONTRACT,
                "createdAtUtc": started_at,
                "cutoverId": "2026-07-17T12:00:00Z",
                "jobName": job_name,
                "service": service,
                "status": "start_pending",
            },
        )
        stdout_path = root / f"{job_name}.stdout.log"
        stdout_sha = write_canonical(
            module,
            stdout_path,
            proof_payload(job_name),
        )
        stderr_path = root / f"{job_name}.stderr.log"
        stderr_path.write_bytes(b"")
        stderr_path.chmod(0o600)
        stderr_sha = hashlib.sha256(b"").hexdigest()
        job_path = root / f"{job_name}.job-receipt.json"
        job_sha = write_canonical(
            module,
            job_path,
            {
                "ambiguous": False,
                "candidateBuildInfoSha256": build_sha,
                "candidateImageId": CANDIDATE_IMAGE,
                "candidateToolImageId": CANDIDATE_TOOL_IMAGE,
                "composeProject": project,
                "containerId": container_id,
                "containerImageId": CANDIDATE_TOOL_IMAGE,
                "containerName": container_name,
                "containerState": "exited",
                "contractName": module.JOB_RECEIPT_CONTRACT,
                "cutoverId": "2026-07-17T12:00:00Z",
                "exitCode": 0,
                "finishedAtUtc": "2026-07-17T12:00:01+00:00",
                "imageIdAfter": CANDIDATE_TOOL_IMAGE,
                "imageIdBefore": CANDIDATE_TOOL_IMAGE,
                "jobName": job_name,
                "logsCaptured": True,
                "proofPath": str(proof_path),
                "proofSha256": proof_sha,
                "retainedContainer": True,
                "secretCanaryLeaked": False,
                "secretCanarySha256": "7" * 64,
                "service": service,
                "startedAtUtc": started_at,
                "startIntentPath": str(start_intent_path),
                "startIntentSha256": start_intent_sha,
                "status": "pass",
                "stderrPath": str(stderr_path),
                "stderrSha256": stderr_sha,
                "stdoutPath": str(stdout_path),
                "stdoutSha256": stdout_sha,
                "timedOut": False,
                "timeoutSeconds": 180,
                "topology": topology,
            },
        )
        references.append(
            {"name": job_name, "path": str(job_path), "sha256": job_sha}
        )
        aggregate.update(job_name.encode())
        aggregate.update(b"\0")
        aggregate.update(job_sha.encode())
        aggregate.update(b"\n")
    evidence_path = root / (
        f"{phase}.{postquiesce_attempt_id}.phase-evidence.json"
        if phase == module.POSTQUIESCE_REPROOF_PHASE
        else f"{phase}.evidence.json"
    )
    evidence_payload = {
        "authorityIdentitySha256": "e" * 64,
        "candidateBuildInfoSha256": build_sha,
        "candidateImageId": CANDIDATE_IMAGE,
        "candidateToolImageId": CANDIDATE_TOOL_IMAGE,
        "contractName": module.PHASE_EVIDENCE_CONTRACT,
        "cutoverId": "2026-07-17T12:00:00Z",
        "jobReceiptChainSha256": aggregate.hexdigest(),
        "jobReceipts": references,
        "phase": phase,
        "status": "pass",
    }
    if phase == module.POSTQUIESCE_REPROOF_PHASE:
        inventory_path, inventory_sha = state_volume_inventory(
            module,
            root,
            attempt_id=postquiesce_attempt_id,
        )
        evidence_payload.update(
            {
                "runtimeRoleSha256": "9" * 64,
                "volumeInventoryReceiptPath": str(inventory_path),
                "volumeInventoryReceiptSha256": inventory_sha,
            }
        )
    write_canonical(
        module,
        evidence_path,
        evidence_payload,
    )
    return evidence_path


def write_passing_final_run(
    module,
    boundary_output: Path,
    active_build_info: Path,
) -> Path:
    job_names = tuple(
        name
        for phase in (
            "prepare_completed",
            module.IMPORT_SKIPPED_PHASE,
            "validate_completed",
        )
        for name in module.EXPECTED_PHASE_JOBS[phase]
    )
    job_references = []
    for name in job_names:
        job_path = boundary_output.parent / f"{name}.job-receipt.json"
        job_references.append(
            {
                "name": name,
                "path": str(job_path),
                "sha256": hashlib.sha256(job_path.read_bytes()).hexdigest(),
            }
        )
    path = (
        boundary_output.parent / "INSTALL_LINKING_POSTGRES_CUTOVER_RUN.json"
    )
    write_canonical(
        module,
        path,
        {
            "boundaryReceiptPath": str(boundary_output),
            "boundaryReceiptSha256": hashlib.sha256(
                boundary_output.read_bytes()
            ).hexdigest(),
            "candidateBuildInfoPath": str(active_build_info),
            "candidateBuildInfoSha256": hashlib.sha256(
                active_build_info.read_bytes()
            ).hexdigest(),
            "candidateImageId": CANDIDATE_IMAGE,
            "candidateToolImageId": CANDIDATE_TOOL_IMAGE,
            "contractName": module.CUTOVER_RUN_CONTRACT,
            "cutoverId": "2026-07-17T12:00:00Z",
            "finishedAtUtc": "2026-07-17T12:00:02+00:00",
            "jobReceipts": job_references,
            "predeployStopsAtValidateCompleted": True,
            "publicAcceptanceCompleted": False,
            "reason": None,
            "status": "pass",
        },
    )
    return path


def advance(module, output: Path, active_build_info: Path, phase: str):
    evidence = (
        phase_evidence(
            module,
            output.parent,
            active_build_info,
            phase,
            boundary_output=output,
        )
        if phase in module.OPERATOR_COMPLETION_PHASES
        or phase == "public_acceptance_completed"
        else None
    )
    receipt = module.materialize(
        output=output,
        phase=phase,
        cutover_id="2026-07-17T12:00:00Z",
        candidate_image_id=CANDIDATE_IMAGE,
        candidate_tool_image_id=CANDIDATE_TOOL_IMAGE,
        operator_container_image_id=(
            CANDIDATE_TOOL_IMAGE
            if phase in module.OPERATOR_COMPLETION_PHASES
            else None
        ),
        active_build_info=active_build_info,
        evidence_receipt=evidence,
    )
    if phase == "validate_completed":
        write_passing_final_run(module, output, active_build_info)
    return receipt


def test_boundary_rejects_legacy_import_phase_for_isolated_v2(
    tmp_path: Path,
) -> None:
    module = load_module()
    active_build_info = build_info(tmp_path)
    with pytest.raises(ValueError, match="unsupported"):
        module.materialize(
            output=tmp_path / "boundary.json",
            phase="import_completed",
            cutover_id="2026-07-17T12:00:00Z",
            candidate_image_id=CANDIDATE_IMAGE,
            candidate_tool_image_id=CANDIDATE_TOOL_IMAGE,
            operator_container_image_id=CANDIDATE_TOOL_IMAGE,
            active_build_info=active_build_info,
        )


def test_boundary_receipt_records_no_local_store_branch_before_validation(
    tmp_path: Path,
) -> None:
    module = load_module()
    output = tmp_path / "boundary.json"
    active_build_info = build_info(tmp_path)

    for phase in (
        "prepare_starting",
        "prepare_completed",
        module.IMPORT_SKIPPED_PHASE,
        "validate_completed",
        "public_acceptance_completed",
    ):
        receipt = advance(module, output, active_build_info, phase)

    assert receipt["status"] == "pass"
    assert receipt["sequence"] == 5
    assert receipt["importDisposition"] == "skipped_no_local_store"
    assert receipt["importCompleted"] is False
    assert receipt["importSkippedNoLocalStore"] is True
    assert receipt["localStorePresentAtCutover"] is False
    assert receipt["dataProtectionKeyRingPosture"] == (
        "isolated_v2_requires_no_legacy_import"
    )
    assert receipt["validateCompleted"] is True
    skipped_receipt = output.with_name(
        f"{output.name}.{module.IMPORT_SKIPPED_PHASE}.json"
    )
    assert skipped_receipt.is_file()


def test_boundary_receipt_requires_import_or_explicit_no_store_checkpoint(
    tmp_path: Path,
) -> None:
    module = load_module()
    output = tmp_path / "boundary.json"
    active_build_info = build_info(tmp_path)
    advance(module, output, active_build_info, "prepare_starting")
    advance(module, output, active_build_info, "prepare_completed")

    with pytest.raises(ValueError, match="cannot skip"):
        advance(module, output, active_build_info, "validate_completed")


def test_boundary_receipt_rejects_skipped_or_reversed_phase(tmp_path: Path) -> None:
    module = load_module()
    active_build_info = build_info(tmp_path)
    output = tmp_path / "boundary.json"

    with pytest.raises(ValueError, match="must start"):
        advance(module, output, active_build_info, "prepare_completed")
    advance(module, output, active_build_info, "prepare_starting")
    with pytest.raises(ValueError, match="cannot skip"):
        advance(module, output, active_build_info, "validate_completed")
    advance(module, output, active_build_info, "prepare_completed")
    with pytest.raises(ValueError, match="cannot move backwards"):
        advance(module, output, active_build_info, "prepare_starting")


def test_boundary_receipt_rejects_build_info_or_identity_drift(tmp_path: Path) -> None:
    module = load_module()
    active_build_info = build_info(tmp_path)
    output = tmp_path / "boundary.json"
    advance(module, output, active_build_info, "prepare_starting")

    original_build_info = active_build_info.read_bytes()
    active_build_info.write_text('{"status":"changed"}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="build-info|canonical"):
        module.materialize(
            output=output,
            phase="prepare_completed",
            cutover_id="2026-07-17T12:00:00Z",
            candidate_image_id=CANDIDATE_IMAGE,
            candidate_tool_image_id=CANDIDATE_TOOL_IMAGE,
            operator_container_image_id=CANDIDATE_TOOL_IMAGE,
            active_build_info=active_build_info,
        )
    active_build_info.write_bytes(original_build_info)
    with pytest.raises(ValueError, match="build-info contract|candidate image"):
        module.materialize(
            output=output,
            phase="prepare_completed",
            cutover_id="2026-07-17T12:00:00Z",
            candidate_image_id="sha256:" + "b" * 64,
            candidate_tool_image_id=CANDIDATE_TOOL_IMAGE,
            operator_container_image_id=CANDIDATE_TOOL_IMAGE,
            active_build_info=active_build_info,
        )

    with pytest.raises(ValueError, match="build-info contract|candidate tool image"):
        module.materialize(
            output=output,
            phase="prepare_completed",
            cutover_id="2026-07-17T12:00:00Z",
            candidate_image_id=CANDIDATE_IMAGE,
            candidate_tool_image_id="sha256:" + "d" * 64,
            operator_container_image_id="sha256:" + "d" * 64,
            active_build_info=active_build_info,
        )


@pytest.mark.parametrize("cutover_id", ["", "bad value", "x/escape", "x" * 129])
def test_boundary_receipt_rejects_unsafe_cutover_id(
    tmp_path: Path, cutover_id: str
) -> None:
    module = load_module()
    with pytest.raises(ValueError, match="safe literal"):
        module.materialize(
            output=tmp_path / "boundary.json",
            phase="prepare_starting",
            cutover_id=cutover_id,
            candidate_image_id=CANDIDATE_IMAGE,
            candidate_tool_image_id=CANDIDATE_TOOL_IMAGE,
            active_build_info=build_info(tmp_path),
        )


def test_boundary_receipt_rejects_repeated_phase_and_symlinked_receipt_root(
    tmp_path: Path,
) -> None:
    module = load_module()
    active_build_info = build_info(tmp_path)
    output = tmp_path / "boundary.json"
    advance(module, output, active_build_info, "prepare_starting")
    with pytest.raises(ValueError, match="advance exactly once"):
        advance(module, output, active_build_info, "prepare_starting")

    real_root = tmp_path / "real-receipts"
    real_root.mkdir(mode=0o700)
    linked_root = tmp_path / "linked-receipts"
    linked_root.symlink_to(real_root, target_is_directory=True)
    with pytest.raises(ValueError, match="must not contain symlinks"):
        module.materialize(
            output=linked_root / "boundary.json",
            phase="prepare_starting",
            cutover_id="2026-07-17T12:00:01Z",
            candidate_image_id=CANDIDATE_IMAGE,
            candidate_tool_image_id=CANDIDATE_TOOL_IMAGE,
            active_build_info=active_build_info,
        )


def test_boundary_receipt_requires_verified_tool_image_for_operator_completion(
    tmp_path: Path,
) -> None:
    module = load_module()
    active_build_info = build_info(tmp_path)
    output = tmp_path / "boundary.json"
    advance(module, output, active_build_info, "prepare_starting")
    with pytest.raises(ValueError, match="exact candidate tool image"):
        module.materialize(
            output=output,
            phase="prepare_completed",
            cutover_id="2026-07-17T12:00:00Z",
            candidate_image_id=CANDIDATE_IMAGE,
            candidate_tool_image_id=CANDIDATE_TOOL_IMAGE,
            operator_container_image_id="sha256:" + "e" * 64,
            active_build_info=active_build_info,
        )


@pytest.mark.parametrize(
    "layer",
    [
        "evidence",
        "reference",
        "job",
        "topology",
        "start_intent",
        "proof",
        "stderr",
    ],
)
def test_phase_evidence_closes_every_nested_schema(
    tmp_path: Path,
    layer: str,
) -> None:
    module = load_module()
    active_build_info = build_info(tmp_path)
    evidence_path = phase_evidence(
        module,
        tmp_path,
        active_build_info,
        "prepare_completed",
    )
    evidence = read_json(evidence_path)
    if layer == "evidence":
        evidence["password"] = "raw"
        write_canonical(module, evidence_path, evidence)
    elif layer == "reference":
        evidence["jobReceipts"][0]["password"] = "raw"
        write_canonical(module, evidence_path, evidence)
    else:
        reference = evidence["jobReceipts"][0]
        job = read_json(Path(reference["path"]))
        if layer == "job":
            job["password"] = "raw"
        elif layer == "topology":
            job["topology"]["password"] = "raw"
        elif layer == "start_intent":
            start_path = Path(job["startIntentPath"])
            start_intent = read_json(start_path)
            start_intent["password"] = "raw"
            job["startIntentSha256"] = write_canonical(
                module,
                start_path,
                start_intent,
            )
        elif layer == "proof":
            proof_path = Path(job["proofPath"])
            proof = read_json(proof_path)
            proof["password"] = "raw"
            proof_sha = write_canonical(module, proof_path, proof)
            stdout_path = Path(job["stdoutPath"])
            stdout_sha = write_canonical(module, stdout_path, proof)
            job["proofSha256"] = proof_sha
            job["stdoutSha256"] = stdout_sha
        else:
            stderr_path = Path(job["stderrPath"])
            stderr_path.write_bytes(
                b"postgresql://runtime:do-not-record@example.test/chummer"
            )
            job["stderrSha256"] = hashlib.sha256(
                stderr_path.read_bytes()
            ).hexdigest()
        rewrite_job_chain(module, evidence_path, 0, job)

    with pytest.raises(ValueError):
        module.bind_phase_evidence(
            evidence_path,
            phase="prepare_completed",
            cutover_id="2026-07-17T12:00:00Z",
            candidate_image_id=CANDIDATE_IMAGE,
            candidate_tool_image_id=CANDIDATE_TOOL_IMAGE,
            candidate_build_info_sha256=hashlib.sha256(
                active_build_info.read_bytes()
            ).hexdigest(),
            candidate_build_info=read_json(active_build_info),
        )


@pytest.mark.parametrize(
    ("job_name", "field"),
    [
        ("prove-empty-authority", "commitCount"),
        ("prove-empty-authority", "headGeneration"),
        ("validate", "appliedSchemaVersion"),
    ],
)
def test_proof_numeric_fields_reject_boolean_type_confusion(
    tmp_path: Path,
    job_name: str,
    field: str,
) -> None:
    module = load_module()
    payload = proof_payload(job_name)
    payload[field] = False
    with pytest.raises(ValueError):
        module._validate_proof_payload(job_name, payload)


def test_job_and_topology_numeric_fields_reject_boolean_type_confusion(
    tmp_path: Path,
) -> None:
    module = load_module()
    active_build_info = build_info(tmp_path)
    for field_path in ("exitCode", "extraHostCount"):
        evidence_path = phase_evidence(
            module,
            tmp_path,
            active_build_info,
            "import_skipped_no_local_store",
        )
        evidence = read_json(evidence_path)
        job_path = Path(evidence["jobReceipts"][0]["path"])
        job = read_json(job_path)
        if field_path == "exitCode":
            job["exitCode"] = False
        else:
            job["topology"]["extraHostCount"] = False
        rewrite_job_chain(module, evidence_path, 0, job)
        with pytest.raises(ValueError):
            module.bind_phase_evidence(
                evidence_path,
                phase="import_skipped_no_local_store",
                cutover_id="2026-07-17T12:00:00Z",
                candidate_image_id=CANDIDATE_IMAGE,
                candidate_tool_image_id=CANDIDATE_TOOL_IMAGE,
                candidate_build_info_sha256=hashlib.sha256(
                    active_build_info.read_bytes()
                ).hexdigest(),
                candidate_build_info=read_json(active_build_info),
            )
        for path in tmp_path.iterdir():
            if path != active_build_info:
                path.unlink()


def test_boundary_reopens_summary_and_append_only_phase_chain(
    tmp_path: Path,
) -> None:
    module = load_module()
    active_build_info = build_info(tmp_path)
    output = tmp_path / "boundary.json"
    advance(module, output, active_build_info, "prepare_starting")

    summary = read_json(output)
    summary["password"] = "raw"
    write_canonical(module, output, summary)
    with pytest.raises(ValueError, match="append-only|drifted"):
        advance(module, output, active_build_info, "prepare_completed")

    write_canonical(
        module,
        output,
        read_json(output.with_name(f"{output.name}.prepare_starting.json")),
    )
    phase_receipt = output.with_name(f"{output.name}.prepare_starting.json")
    tampered = read_json(phase_receipt)
    tampered["status"] = "pass"
    write_canonical(module, phase_receipt, tampered)
    with pytest.raises(ValueError, match="append-only|posture"):
        advance(module, output, active_build_info, "prepare_completed")


@pytest.mark.parametrize(
    "mutation",
    [
        "digest",
        "image",
        "readiness",
        "overlay",
        "extra-postdeploy-field",
        "postdeploy-schema-contract",
        "postdeploy-schema-digest",
        "postdeploy-secret",
        "runtime-secret",
    ],
)
def test_public_acceptance_binds_real_postdeploy_and_runtime_evidence(
    tmp_path: Path,
    mutation: str,
) -> None:
    module = load_module()
    active_build_info = build_info(tmp_path)
    output = tmp_path / "boundary.json"
    for phase in (
        "prepare_starting",
        "prepare_completed",
        module.IMPORT_SKIPPED_PHASE,
        "validate_completed",
    ):
        advance(module, output, active_build_info, phase)
    evidence_path = phase_evidence(
        module,
        tmp_path,
        active_build_info,
        "public_acceptance_completed",
        boundary_output=output,
    )
    evidence = read_json(evidence_path)
    if mutation == "digest":
        evidence["postdeployReceiptSha256"] = "0" * 64
    elif mutation in {"image", "runtime-secret"}:
        runtime_path = Path(evidence["activeRuntimeAuthorityPath"])
        runtime = read_json(runtime_path)
        if mutation == "image":
            runtime["portal"]["imageId"] = "sha256:" + "b" * 64
        else:
            runtime["portal"]["containerName"] = (
                "postgresql://runtime:do-not-record@example.test/chummer"
            )
        evidence["activeRuntimeAuthoritySha256"] = write_canonical(
            module,
            runtime_path,
            runtime,
        )
    else:
        postdeploy_path = Path(evidence["postdeployReceiptPath"])
        postdeploy = read_json(postdeploy_path)
        if mutation == "readiness":
            postdeploy["readyMobileHandoffStatus"] = "fail"
        elif mutation == "overlay":
            postdeploy[
                "preflightOverlayBuildInfoSourceFingerprintAggregateMatchesCurrentSource"
            ] = False
        elif mutation == "extra-postdeploy-field":
            postdeploy["unreviewed"] = True
        elif mutation == "postdeploy-schema-contract":
            postdeploy["schemaContractName"] = (
                "chummer.public_edge_postdeploy_gate.schema.v0"
            )
        elif mutation == "postdeploy-schema-digest":
            postdeploy["schemaSha256"] = "0" * 64
        else:
            postdeploy["baseUrl"] = (
                "https://public:do-not-record@example.test/"
            )
        evidence["postdeployReceiptSha256"] = write_canonical(
            module,
            postdeploy_path,
            postdeploy,
        )
    write_canonical(module, evidence_path, evidence)

    with pytest.raises(ValueError):
        module.materialize(
            output=output,
            phase="public_acceptance_completed",
            cutover_id="2026-07-17T12:00:00Z",
            candidate_image_id=CANDIDATE_IMAGE,
            candidate_tool_image_id=CANDIDATE_TOOL_IMAGE,
            active_build_info=active_build_info,
            evidence_receipt=evidence_path,
        )


@pytest.mark.parametrize(
    "secret_value",
    (
        "api_key = do-not-record",
        "credentials: do-not-record",
        "connectionStrings=do-not-record",
        "tokens = do-not-record",
        "github_pat_" + "a" * 24,
        "AKIA" + "A" * 16,
        "sk_live_" + "a" * 24,
        "xoxb-" + "a" * 20,
        "AIza" + "a" * 30,
        "eyJ" + "a" * 10 + "." + "b" * 10 + "." + "c" * 10,
        "https%3A%2F%2Fuser%3Apassword%40example.test%2F",
    ),
)
def test_public_acceptance_rejects_secret_values_anywhere_in_full_postdeploy(
    tmp_path: Path,
    secret_value: str,
) -> None:
    module = load_module()
    active_build_info = build_info(tmp_path)
    output = tmp_path / "boundary.json"
    for phase in (
        "prepare_starting",
        "prepare_completed",
        module.IMPORT_SKIPPED_PHASE,
        "validate_completed",
    ):
        advance(module, output, active_build_info, phase)
    evidence_path = phase_evidence(
        module,
        tmp_path,
        active_build_info,
        "public_acceptance_completed",
        boundary_output=output,
    )
    evidence = read_json(evidence_path)
    postdeploy_path = Path(evidence["postdeployReceiptPath"])
    postdeploy = read_json(postdeploy_path)
    postdeploy["childReceipts"] = {
        "nested": [{"otherwiseBenignField": secret_value}]
    }
    evidence["postdeployReceiptSha256"] = write_canonical(
        module,
        postdeploy_path,
        postdeploy,
    )
    write_canonical(module, evidence_path, evidence)

    with pytest.raises(ValueError, match="apparent secret material"):
        module.materialize(
            output=output,
            phase="public_acceptance_completed",
            cutover_id="2026-07-17T12:00:00Z",
            candidate_image_id=CANDIDATE_IMAGE,
            candidate_tool_image_id=CANDIDATE_TOOL_IMAGE,
            active_build_info=active_build_info,
            evidence_receipt=evidence_path,
        )


@pytest.mark.parametrize(
    "secret_key",
    (
        "databasePassword",
        "api_key",
        "clientSecret",
        "authorization",
        "privateKey",
    ),
)
def test_public_acceptance_rejects_secret_bearing_keys_anywhere_in_postdeploy(
    tmp_path: Path,
    secret_key: str,
) -> None:
    module = load_module()
    active_build_info = build_info(tmp_path)
    output = tmp_path / "boundary.json"
    for phase in (
        "prepare_starting",
        "prepare_completed",
        module.IMPORT_SKIPPED_PHASE,
        "validate_completed",
    ):
        advance(module, output, active_build_info, phase)
    evidence_path = phase_evidence(
        module,
        tmp_path,
        active_build_info,
        "public_acceptance_completed",
        boundary_output=output,
    )
    evidence = read_json(evidence_path)
    postdeploy_path = Path(evidence["postdeployReceiptPath"])
    postdeploy = read_json(postdeploy_path)
    postdeploy["childReceipts"] = {
        "preflight": {secret_key: "hunter2"}
    }
    evidence["postdeployReceiptSha256"] = write_canonical(
        module,
        postdeploy_path,
        postdeploy,
    )
    write_canonical(module, evidence_path, evidence)

    with pytest.raises(ValueError, match="apparent secret material"):
        module.materialize(
            output=output,
            phase="public_acceptance_completed",
            cutover_id="2026-07-17T12:00:00Z",
            candidate_image_id=CANDIDATE_IMAGE,
            candidate_tool_image_id=CANDIDATE_TOOL_IMAGE,
            active_build_info=active_build_info,
            evidence_receipt=evidence_path,
        )


@pytest.mark.parametrize(
    "secret_key",
    (
        "credentials",
        "databaseCredentials",
        "passwords",
        "tokens",
        "secrets",
        "connectionString",
        "connection_strings",
        "dsn",
    ),
)
def test_public_acceptance_rejects_secret_aliases_in_allowed_nested_field(
    tmp_path: Path,
    secret_key: str,
) -> None:
    module = load_module()
    active_build_info = build_info(tmp_path)
    output = tmp_path / "boundary.json"
    for phase in (
        "prepare_starting",
        "prepare_completed",
        module.IMPORT_SKIPPED_PHASE,
        "validate_completed",
    ):
        advance(module, output, active_build_info, phase)
    evidence_path = phase_evidence(
        module,
        tmp_path,
        active_build_info,
        "public_acceptance_completed",
        boundary_output=output,
    )
    evidence = read_json(evidence_path)
    postdeploy_path = Path(evidence["postdeployReceiptPath"])
    postdeploy = read_json(postdeploy_path)
    postdeploy["roleAliasRouteResults"] = [
        {secret_key: "hunter2"}
    ]
    evidence["postdeployReceiptSha256"] = write_canonical(
        module,
        postdeploy_path,
        postdeploy,
    )
    write_canonical(module, evidence_path, evidence)

    with pytest.raises(ValueError, match="apparent secret material"):
        module.materialize(
            output=output,
            phase="public_acceptance_completed",
            cutover_id="2026-07-17T12:00:00Z",
            candidate_image_id=CANDIDATE_IMAGE,
            candidate_tool_image_id=CANDIDATE_TOOL_IMAGE,
            active_build_info=active_build_info,
            evidence_receipt=evidence_path,
        )


def test_public_acceptance_rejects_even_benign_raw_child_receipts(
    tmp_path: Path,
) -> None:
    module = load_module()
    active_build_info = build_info(tmp_path)
    output = tmp_path / "boundary.json"
    for phase in (
        "prepare_starting",
        "prepare_completed",
        module.IMPORT_SKIPPED_PHASE,
        "validate_completed",
    ):
        advance(module, output, active_build_info, phase)
    evidence_path = phase_evidence(
        module,
        tmp_path,
        active_build_info,
        "public_acceptance_completed",
        boundary_output=output,
    )
    evidence = read_json(evidence_path)
    postdeploy_path = Path(evidence["postdeployReceiptPath"])
    postdeploy = read_json(postdeploy_path)
    postdeploy["childReceipts"] = {
        "preflight": {"status": "pass"}
    }
    evidence["postdeployReceiptSha256"] = write_canonical(
        module,
        postdeploy_path,
        postdeploy,
    )
    write_canonical(module, evidence_path, evidence)

    with pytest.raises(ValueError, match="schema"):
        module.materialize(
            output=output,
            phase="public_acceptance_completed",
            cutover_id="2026-07-17T12:00:00Z",
            candidate_image_id=CANDIDATE_IMAGE,
            candidate_tool_image_id=CANDIDATE_TOOL_IMAGE,
            active_build_info=active_build_info,
            evidence_receipt=evidence_path,
        )


def make_safe_fail_postquiesce_receipt(
    module,
    tmp_path: Path,
    output: Path,
    active_build_info: Path,
    *,
    attempt_id: str = "attempt01",
) -> tuple[Path, str]:
    inventory_path, inventory_sha = state_volume_inventory(
        module,
        tmp_path,
        attempt_id=attempt_id,
    )
    build_payload = read_json(active_build_info)
    validate_snapshot = output.with_name(
        f"{output.name}.validate_completed.json"
    )
    receipt_path = tmp_path / (
        "INSTALL_LINKING_POSTGRES_POSTQUIESCE_REPROOF."
        f"{attempt_id}.json"
    )
    write_canonical(
        module,
        receipt_path,
        {
            "activeBuildInfoPath": str(active_build_info),
            "activeBuildInfoSha256": hashlib.sha256(
                active_build_info.read_bytes()
            ).hexdigest(),
            "attemptId": attempt_id,
            "boundaryReceiptPath": str(output),
            "boundaryReceiptSha256": hashlib.sha256(
                validate_snapshot.read_bytes()
            ).hexdigest(),
            "candidateImageId": CANDIDATE_IMAGE,
            "candidatePortalTag": build_payload["candidatePortalTag"],
            "candidateToolImageId": CANDIDATE_TOOL_IMAGE,
            "candidateToolTag": build_payload["candidateToolTag"],
            "containerStartMayHaveBeenInvoked": False,
            "contractName": module.POSTQUIESCE_REPROOF_CONTRACT,
            "cutoverId": "2026-07-17T12:00:00Z",
            "finishedAtUtc": "2026-07-17T12:00:04+00:00",
            "mutationLockPath": (
                "/docker/chummercomplete/.state/"
                "public-edge-mutation.lock"
            ),
            "mutationLockTokenSha256": "f" * 64,
            "phaseEvidencePath": None,
            "phaseEvidenceSha256": None,
            "reason": "CutoverError",
            "sourceHead": build_payload["sourceHead"],
            "startedAtUtc": "2026-07-17T12:00:03+00:00",
            "startIntentWritten": False,
            "status": "fail",
            "volumeInventoryReceiptPath": str(inventory_path),
            "volumeInventoryReceiptSha256": inventory_sha,
        },
    )
    return receipt_path, inventory_sha


def prepare_validated_boundary(
    module,
    tmp_path: Path,
) -> tuple[Path, Path]:
    active_build_info = build_info(tmp_path)
    output = tmp_path / "boundary.json"
    for phase in (
        "prepare_starting",
        "prepare_completed",
        module.IMPORT_SKIPPED_PHASE,
        "validate_completed",
    ):
        advance(module, output, active_build_info, phase)
    return output, active_build_info


def test_postquiesce_safe_fail_requires_proof_no_start_was_possible(
    tmp_path: Path,
) -> None:
    module = load_module()
    output, active_build_info = prepare_validated_boundary(
        module,
        tmp_path,
    )
    receipt_path, inventory_sha = make_safe_fail_postquiesce_receipt(
        module,
        tmp_path,
        output,
        active_build_info,
    )
    build_payload = read_json(active_build_info)
    build_sha = hashlib.sha256(active_build_info.read_bytes()).hexdigest()

    classification, _, _ = module.classify_postquiesce_reproof(
        receipt_path,
        boundary_output=output,
        cutover_id="2026-07-17T12:00:00Z",
        candidate_image_id=CANDIDATE_IMAGE,
        candidate_tool_image_id=CANDIDATE_TOOL_IMAGE,
        candidate_build_info_sha256=build_sha,
        candidate_build_info=build_payload,
        expected_mutation_lock_token_sha256="f" * 64,
        expected_volume_inventory_sha256=inventory_sha,
    )

    assert classification == "safe_fail"


@pytest.mark.parametrize(
    "mutation",
    ["start-intent-flag", "container-start-flag", "durable-start-intent"],
)
def test_postquiesce_safe_fail_rejects_any_start_evidence(
    tmp_path: Path,
    mutation: str,
) -> None:
    module = load_module()
    output, active_build_info = prepare_validated_boundary(
        module,
        tmp_path,
    )
    receipt_path, inventory_sha = make_safe_fail_postquiesce_receipt(
        module,
        tmp_path,
        output,
        active_build_info,
    )
    if mutation == "durable-start-intent":
        durable = tmp_path / (
            "postquiesce-attempt01-prove-local-store-absent."
            "start-intent.json"
        )
        durable.write_bytes(b"{}\n")
        durable.chmod(0o600)
    else:
        receipt = read_json(receipt_path)
        receipt[
            (
                "startIntentWritten"
                if mutation == "start-intent-flag"
                else "containerStartMayHaveBeenInvoked"
            )
        ] = True
        write_canonical(module, receipt_path, receipt)

    with pytest.raises(ValueError):
        module.classify_postquiesce_reproof(
            receipt_path,
            boundary_output=output,
            cutover_id="2026-07-17T12:00:00Z",
            candidate_image_id=CANDIDATE_IMAGE,
            candidate_tool_image_id=CANDIDATE_TOOL_IMAGE,
            candidate_build_info_sha256=hashlib.sha256(
                active_build_info.read_bytes()
            ).hexdigest(),
            candidate_build_info=read_json(active_build_info),
            expected_mutation_lock_token_sha256="f" * 64,
            expected_volume_inventory_sha256=inventory_sha,
        )


def test_postquiesce_unknown_outcome_remains_blocking(
    tmp_path: Path,
) -> None:
    module = load_module()
    output, active_build_info = prepare_validated_boundary(
        module,
        tmp_path,
    )
    receipt_path, inventory_sha = make_safe_fail_postquiesce_receipt(
        module,
        tmp_path,
        output,
        active_build_info,
    )
    receipt = read_json(receipt_path)
    receipt["status"] = "unknown"
    write_canonical(module, receipt_path, receipt)

    classification, _, _ = module.classify_postquiesce_reproof(
        receipt_path,
        boundary_output=output,
        cutover_id="2026-07-17T12:00:00Z",
        candidate_image_id=CANDIDATE_IMAGE,
        candidate_tool_image_id=CANDIDATE_TOOL_IMAGE,
        candidate_build_info_sha256=hashlib.sha256(
            active_build_info.read_bytes()
        ).hexdigest(),
        candidate_build_info=read_json(active_build_info),
        expected_mutation_lock_token_sha256="f" * 64,
        expected_volume_inventory_sha256=inventory_sha,
    )

    assert classification == "unknown"


def test_candidate_build_info_is_closed_and_identity_bound(
    tmp_path: Path,
) -> None:
    module = load_module()
    path = build_info(tmp_path)
    opaque = {"status": "pass"}
    write_canonical(module, path, opaque)
    with pytest.raises(ValueError, match="build-info contract"):
        module.bind_active_build_info(
            path,
            cutover_id="2026-07-17T12:00:00Z",
            candidate_image_id=CANDIDATE_IMAGE,
            candidate_tool_image_id=CANDIDATE_TOOL_IMAGE,
        )

    path = build_info(tmp_path)
    payload = read_json(path)
    payload["buildSourceProvenance"]["design-product"]["originMain"] = "f" * 40
    write_canonical(module, path, payload)
    with pytest.raises(ValueError, match="build-info contract"):
        module.bind_active_build_info(
            path,
            cutover_id="2026-07-17T12:00:00Z",
            candidate_image_id=CANDIDATE_IMAGE,
            candidate_tool_image_id=CANDIDATE_TOOL_IMAGE,
        )

    path = build_info(tmp_path)
    payload = read_json(path)
    payload["candidateImageId"] = "sha256:" + "f" * 64
    write_canonical(module, path, payload)
    with pytest.raises(ValueError, match="build-info contract"):
        module.bind_active_build_info(
            path,
            cutover_id="2026-07-17T12:00:00Z",
            candidate_image_id=CANDIDATE_IMAGE,
            candidate_tool_image_id=CANDIDATE_TOOL_IMAGE,
        )


@pytest.mark.parametrize(
    "mutation",
    (
        "mutable-base",
        "mutable-frontend",
        "runtime-package-install",
        "package-input-drift",
        "package-input-removed",
        "postdeploy-schema-drift",
        "sensitive-context-path",
        "context-policy-opened",
        "root-ignore-disagrees",
        "external-restore-not-sdk-only",
        "loopback-probe-not-sdk-only",
        "loopback-probe-program-drift",
    ),
)
def test_candidate_build_info_rejects_dependency_provenance_drift(
    tmp_path: Path,
    mutation: str,
) -> None:
    module = load_module()
    path = build_info(tmp_path)
    payload = read_json(path)
    provenance = payload["buildSourceProvenance"]
    dependency = provenance["build-dependency-contract"]
    if mutation == "mutable-base":
        dependency["baseImages"]["final"] = (
            "mcr.microsoft.com/dotnet/aspnet:10.0"
        )
    elif mutation == "mutable-frontend":
        dependency["dockerfileFrontend"] = "docker/dockerfile:1.4"
    elif mutation == "runtime-package-install":
        dependency["runtimePackageManagerInvocationCount"] = 1
    elif mutation == "package-input-drift":
        dependency["packageInputs"]["global.json"] = "0" * 64
    elif mutation == "package-input-removed":
        dependency["packageInputs"].pop("global.json")
    elif mutation == "postdeploy-schema-drift":
        dependency["postdeploySchemaSha256"] = "0" * 64
    elif mutation == "sensitive-context-path":
        provenance["design-product"]["sensitivePathCount"] = 1
    elif mutation == "context-policy-opened":
        dependency["contextPolicies"]["design-product"][
            "contextBoundary"
        ] = "unrestricted-directory"
    elif mutation == "root-ignore-disagrees":
        dependency["contextPolicies"]["canonical-build-context"][
            "dockerignoreSha256"
        ] = "0" * 64
    elif mutation == "external-restore-not-sdk-only":
        dependency["externalMediaRestoreIsSdkOnly"] = False
    elif mutation == "loopback-probe-not-sdk-only":
        dependency["loopbackProbeIsSdkOnly"] = False
    elif mutation == "loopback-probe-program-drift":
        dependency["loopbackProbeProgramSha256"] = "0" * 64
    else:  # pragma: no cover - parameter list is closed.
        raise AssertionError(mutation)
    write_canonical(module, path, payload)

    with pytest.raises(ValueError, match="build-info contract"):
        module.bind_active_build_info(
            path,
            cutover_id="2026-07-17T12:00:00Z",
            candidate_image_id=CANDIDATE_IMAGE,
            candidate_tool_image_id=CANDIDATE_TOOL_IMAGE,
        )


def test_materializer_rejects_wrong_mount_source_identity(
    tmp_path: Path,
) -> None:
    module = load_module()
    active_build_info = build_info(tmp_path)
    evidence_path = phase_evidence(
        module,
        tmp_path,
        active_build_info,
        module.IMPORT_SKIPPED_PHASE,
    )
    evidence = read_json(evidence_path)
    job_path = Path(evidence["jobReceipts"][0]["path"])
    job = read_json(job_path)
    job["topology"]["mounts"][0]["sourceIdentitySha256"] = "0" * 64
    rewrite_job_chain(module, evidence_path, 0, job)

    with pytest.raises(ValueError, match="topology"):
        module.bind_phase_evidence(
            evidence_path,
            phase=module.IMPORT_SKIPPED_PHASE,
            cutover_id="2026-07-17T12:00:00Z",
            candidate_image_id=CANDIDATE_IMAGE,
            candidate_tool_image_id=CANDIDATE_TOOL_IMAGE,
            candidate_build_info_sha256=hashlib.sha256(
                active_build_info.read_bytes()
            ).hexdigest(),
            candidate_build_info=read_json(active_build_info),
        )


def test_prepare_phase_cross_binds_admin_and_runtime_role_hashes(
    tmp_path: Path,
) -> None:
    module = load_module()
    active_build_info = build_info(tmp_path)
    evidence_path = phase_evidence(
        module,
        tmp_path,
        active_build_info,
        "prepare_completed",
    )
    evidence = read_json(evidence_path)
    prepare_index = 1
    job_path = Path(evidence["jobReceipts"][prepare_index]["path"])
    job = read_json(job_path)
    proof_path = Path(job["proofPath"])
    proof = read_json(proof_path)
    proof["runtimeRoleSha256"] = "8" * 64
    job["proofSha256"] = write_canonical(module, proof_path, proof)
    job["stdoutSha256"] = write_canonical(
        module,
        Path(job["stdoutPath"]),
        proof,
    )
    rewrite_job_chain(module, evidence_path, prepare_index, job)

    with pytest.raises(ValueError, match="runtime-role proof binding"):
        module.bind_phase_evidence(
            evidence_path,
            phase="prepare_completed",
            cutover_id="2026-07-17T12:00:00Z",
            candidate_image_id=CANDIDATE_IMAGE,
            candidate_tool_image_id=CANDIDATE_TOOL_IMAGE,
            candidate_build_info_sha256=hashlib.sha256(
                active_build_info.read_bytes()
            ).hexdigest(),
            candidate_build_info=read_json(active_build_info),
        )


def test_predeploy_verifier_binds_boundary_source_and_unique_images(
    tmp_path: Path,
) -> None:
    module = load_module()
    verifier = load_verifier()
    source_root = tmp_path / "source"
    (source_root / "scripts").mkdir(parents=True)
    compose = source_root / "docker-compose.public-edge.yml"
    runner_script = source_root / "scripts" / "run_install_linking_postgres_cutover.py"
    env_file = tmp_path / ".env"
    compose.write_text("services: {}\n", encoding="utf-8")
    runner_script.write_text("# runner\n", encoding="utf-8")
    env_file.write_text("SAFE=value\n", encoding="utf-8")
    env_file.chmod(0o600)
    active_build_info = build_info(tmp_path)
    build_payload = read_json(active_build_info)
    build_payload["composeSha256"] = hashlib.sha256(
        compose.read_bytes()
    ).hexdigest()
    build_payload["runnerSha256"] = hashlib.sha256(
        runner_script.read_bytes()
    ).hexdigest()
    build_payload["envSha256"] = hashlib.sha256(
        env_file.read_bytes()
    ).hexdigest()
    write_canonical(module, active_build_info, build_payload)
    output = tmp_path / "boundary.json"
    for phase in (
        "prepare_starting",
        "prepare_completed",
        module.IMPORT_SKIPPED_PHASE,
        "validate_completed",
    ):
        advance(module, output, active_build_info, phase)
    boundary_sha = hashlib.sha256(output.read_bytes()).hexdigest()

    receipt = verifier.verify_boundary(
        boundary=output,
        expected_boundary_sha256=boundary_sha,
        expected_cutover_id="2026-07-17T12:00:00Z",
        expected_source_head="4" * 40,
        expected_candidate_image_id=CANDIDATE_IMAGE,
        expected_candidate_tool_image_id=CANDIDATE_TOOL_IMAGE,
        observed_candidate_image_id=CANDIDATE_IMAGE,
        observed_candidate_tool_image_id=CANDIDATE_TOOL_IMAGE,
        source_root=source_root,
        env_file=env_file,
    )
    assert receipt["status"] == "pass"

    with pytest.raises(ValueError, match="digest"):
        verifier.verify_boundary(
            boundary=output,
            expected_boundary_sha256="0" * 64,
            expected_cutover_id="2026-07-17T12:00:00Z",
            expected_source_head="4" * 40,
            expected_candidate_image_id=CANDIDATE_IMAGE,
            expected_candidate_tool_image_id=CANDIDATE_TOOL_IMAGE,
            observed_candidate_image_id=CANDIDATE_IMAGE,
            observed_candidate_tool_image_id=CANDIDATE_TOOL_IMAGE,
            source_root=source_root,
            env_file=env_file,
        )
