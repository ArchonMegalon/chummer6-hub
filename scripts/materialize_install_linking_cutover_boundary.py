#!/usr/bin/env python3
"""Record the irreversible InstallLinking PostgreSQL cutover boundary."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
from typing import Any
from urllib.parse import unquote_to_bytes

SCRIPT_DIRECTORY = Path(__file__).resolve().parent
if str(SCRIPT_DIRECTORY) not in sys.path:
    # Keep isolated-mode authority independent of PYTHONPATH while allowing audited siblings.
    sys.path.insert(0, str(SCRIPT_DIRECTORY))

try:
    from scripts.strict_json_contract import canonical_json_bytes, strict_json_object
    from scripts.public_edge_postdeploy_contract import (
        PUBLIC_EDGE_POSTDEPLOY_SCHEMA_CONTRACT_NAME,
        PUBLIC_EDGE_POSTDEPLOY_REQUIRED_FIELDS,
        load_exact_public_edge_postdeploy_schema,
        public_edge_forbidden_secret_key,
    )
except ModuleNotFoundError:  # Direct ``python3 scripts/...`` execution.
    from strict_json_contract import canonical_json_bytes, strict_json_object
    from public_edge_postdeploy_contract import (
        PUBLIC_EDGE_POSTDEPLOY_SCHEMA_CONTRACT_NAME,
        PUBLIC_EDGE_POSTDEPLOY_REQUIRED_FIELDS,
        load_exact_public_edge_postdeploy_schema,
        public_edge_forbidden_secret_key,
    )


CONTRACT_NAME = "chummer.install_linking_postgres_cutover_boundary.v3"
IMPORT_SKIPPED_PHASE = "import_skipped_no_local_store"
PHASES = (
    "prepare_starting",
    "prepare_completed",
    IMPORT_SKIPPED_PHASE,
    "validate_completed",
    "public_acceptance_completed",
)
SUPPORTED_PHASES = (
    "prepare_starting",
    "prepare_completed",
    IMPORT_SKIPPED_PHASE,
    "validate_completed",
    "public_acceptance_completed",
)
PHASE_SEQUENCE = {
    "prepare_starting": 0,
    "prepare_completed": 1,
    IMPORT_SKIPPED_PHASE: 2,
    "validate_completed": 3,
    "public_acceptance_completed": 4,
}
OPERATOR_COMPLETION_PHASES = {
    "prepare_completed",
    IMPORT_SKIPPED_PHASE,
    "validate_completed",
}
PHASE_EVIDENCE_CONTRACT = "chummer.install_linking_postgres_phase_evidence.v1"
PUBLIC_ACCEPTANCE_EVIDENCE_CONTRACT = (
    "chummer.install_linking_postgres_public_acceptance_evidence.v1"
)
POSTQUIESCE_REPROOF_CONTRACT = (
    "chummer.install_linking_postgres_postquiesce_reproof.v2"
)
POSTQUIESCE_REPROOF_PHASE = "postquiesce_reproof"
JOB_RECEIPT_CONTRACT = "chummer.install_linking_postgres_operator_job.v1"
START_INTENT_CONTRACT = "chummer.install_linking_postgres_start_intent.v1"
CUTOVER_RUN_CONTRACT = "chummer.install_linking_postgres_cutover_run.v1"
POSTQUIESCE_PROOF_KINDS = (
    "prove-local-store-absent",
    "prove-empty-authority",
    "prove-runtime-role",
)
EXPECTED_PHASE_JOBS = {
    "prepare_completed": (
        "transport-proof",
        "prepare",
        "prove-empty-authority",
        "prove-runtime-role",
    ),
    IMPORT_SKIPPED_PHASE: ("prove-local-store-absent",),
    "validate_completed": ("validate",),
}
EXPECTED_PROOF_CONTRACTS = {
    "transport-proof": "chummer.postgres_transport_proof.v1",
    "prepare": "chummer.install_linking_postgres_prepare.v1",
    "prove-empty-authority": (
        "chummer.install_linking_postgres_empty_authority_proof.v1"
    ),
    "prove-runtime-role": (
        "chummer.install_linking_postgres_runtime_role_proof.v1"
    ),
    "prove-local-store-absent": (
        "chummer.install_linking_local_store_absence_proof.v1"
    ),
    "validate": "chummer.install_linking_postgres_schema_validation.v1",
}
EXPECTED_JOB_SERVICES = {
    "transport-proof": "chummer-install-linking-postgres-admin",
    "prepare": "chummer-install-linking-postgres-admin",
    "prove-empty-authority": "chummer-install-linking-postgres-runtime-proof",
    "prove-runtime-role": "chummer-install-linking-postgres-runtime-proof",
    "prove-local-store-absent": (
        "chummer-install-linking-postgres-import-presence-proof"
    ),
    "validate": "chummer-install-linking-postgres-admin",
}
EXPECTED_SERVICE_MOUNTS = {
    "chummer-install-linking-postgres-admin": [
        {
            "destination": (
                "/run/chummer-secrets/"
                "install-linking-postgres-migrator.connection-string"
            ),
            "readWrite": False,
        },
        {
            "destination": (
                "/run/chummer-secrets/install-linking-postgres-server-ca.pem"
            ),
            "readWrite": False,
        },
    ],
    "chummer-install-linking-postgres-runtime-proof": [
        {
            "destination": (
                "/run/chummer-secrets/"
                "install-linking-postgres-runtime.connection-string"
            ),
            "readWrite": False,
        },
        {
            "destination": (
                "/run/chummer-secrets/install-linking-postgres-server-ca.pem"
            ),
            "readWrite": False,
        },
    ],
    "chummer-install-linking-postgres-import-presence-proof": [
        {"destination": "/app/state", "readWrite": False},
    ],
}
EXPECTED_TMPFS = [
    {
        "destination": "/tmp",
        "options": ["mode=1777", "nodev", "noexec", "nosuid", "rw"],
    }
]
PHASE_EVIDENCE_KEYS = {
    "authorityIdentitySha256",
    "candidateBuildInfoSha256",
    "candidateImageId",
    "candidateToolImageId",
    "contractName",
    "cutoverId",
    "jobReceiptChainSha256",
    "jobReceipts",
    "phase",
    "status",
}
PHASE_JOB_REFERENCE_KEYS = {"name", "path", "sha256"}
JOB_RECEIPT_KEYS = {
    "ambiguous",
    "candidateBuildInfoSha256",
    "candidateImageId",
    "candidateToolImageId",
    "composeProject",
    "containerId",
    "containerImageId",
    "containerName",
    "containerState",
    "contractName",
    "cutoverId",
    "exitCode",
    "finishedAtUtc",
    "imageIdAfter",
    "imageIdBefore",
    "jobName",
    "logsCaptured",
    "proofPath",
    "proofSha256",
    "retainedContainer",
    "secretCanaryLeaked",
    "secretCanarySha256",
    "service",
    "startedAtUtc",
    "startIntentPath",
    "startIntentSha256",
    "status",
    "stderrPath",
    "stderrSha256",
    "stdoutPath",
    "stdoutSha256",
    "timedOut",
    "timeoutSeconds",
    "topology",
}
TOPOLOGY_KEYS = {
    "capDrop",
    "command",
    "composeProject",
    "criticalEnvironmentSha256",
    "extraHostCount",
    "imageId",
    "labels",
    "mounts",
    "networkId",
    "networkMode",
    "noNewPrivileges",
    "readOnlyRootFilesystem",
    "service",
    "tmpfs",
    "user",
}
TOPOLOGY_MOUNT_KEYS = {
    "destination",
    "readWrite",
    "sourceIdentitySha256",
    "sourceKind",
}
TOPOLOGY_TMPFS_KEYS = {"destination", "options"}
TOPOLOGY_LABEL_KEYS = {
    "composeConfigHash",
    "composeOneoff",
    "composeProject",
    "composeService",
}
EXPECTED_JOB_COMMANDS = {
    "transport-proof": ["transport-proof"],
    "prepare": ["prepare"],
    "prove-empty-authority": ["prove-empty-authority"],
    "prove-runtime-role": ["prove-runtime-role"],
    "prove-local-store-absent": ["prove-local-store-absent"],
    "validate": ["validate"],
}
START_INTENT_KEYS = {
    "candidateToolImageId",
    "composeProject",
    "containerId",
    "containerName",
    "contractName",
    "createdAtUtc",
    "cutoverId",
    "jobName",
    "service",
    "status",
}
BOUNDARY_RECEIPT_KEYS = {
    "activeBuildInfoPath",
    "activeBuildInfoSha256",
    "automaticDatabaseRollbackAllowed",
    "candidateImageId",
    "candidateToolImageId",
    "contractName",
    "createdAtUtc",
    "cutoverId",
    "dataProtectionKeyRingPosture",
    "importCompleted",
    "importDisposition",
    "importSkippedNoLocalStore",
    "irreversibleDatabaseBoundaryMayHaveBeenEntered",
    "localStorePresentAtCutover",
    "operatorContainerImageId",
    "operatorEvidenceReceiptPath",
    "operatorEvidenceReceiptSha256",
    "phase",
    "phaseEvidence",
    "phaseReceiptPath",
    "prepareCompleted",
    "previousPhase",
    "previousReceiptSha256",
    "publicAcceptanceCompleted",
    "recoveryAuthority",
    "sequence",
    "status",
    "updatedAtUtc",
    "validateCompleted",
}
BOUNDARY_EVIDENCE_REFERENCE_KEYS = {"path", "phase", "sha256"}
RECOVERY_AUTHORITY_KEYS = {
    "localMirrorRollbackAllowed",
    "mode",
    "portalAndTunnelMustRemainStoppedUntilAccepted",
    "preserveFailedAuthorityAndLogs",
    "schemaOrGenerationRewindAllowed",
}
PUBLIC_ACCEPTANCE_EVIDENCE_KEYS = {
    "activeRuntimeAuthorityPath",
    "activeRuntimeAuthoritySha256",
    "candidateBuildInfoSha256",
    "candidateContainerImageId",
    "candidateImageId",
    "candidateToolImageId",
    "contractName",
    "cutoverId",
    "overlayAccepted",
    "postQuiesceReceiptPath",
    "postQuiesceReceiptSha256",
    "postdeployReceiptPath",
    "postdeployReceiptSha256",
    "publicReadinessAccepted",
    "status",
}
POSTQUIESCE_REPROOF_KEYS = {
    "activeBuildInfoPath",
    "activeBuildInfoSha256",
    "attemptId",
    "boundaryReceiptPath",
    "boundaryReceiptSha256",
    "candidateImageId",
    "candidatePortalTag",
    "candidateToolImageId",
    "candidateToolTag",
    "containerStartMayHaveBeenInvoked",
    "contractName",
    "cutoverId",
    "finishedAtUtc",
    "mutationLockPath",
    "mutationLockTokenSha256",
    "phaseEvidencePath",
    "phaseEvidenceSha256",
    "reason",
    "sourceHead",
    "startedAtUtc",
    "status",
    "startIntentWritten",
    "volumeInventoryReceiptPath",
    "volumeInventoryReceiptSha256",
}
POSTQUIESCE_PHASE_EVIDENCE_KEYS = PHASE_EVIDENCE_KEYS | {
    "runtimeRoleSha256",
    "volumeInventoryReceiptPath",
    "volumeInventoryReceiptSha256",
}
STATE_VOLUME_INVENTORY_CONTRACT = (
    "chummer.install_linking_state_volume_inventory.v1"
)
STATE_VOLUME_INVENTORY_KEYS = {
    "attemptId",
    "candidateToolImageId",
    "checkpoint",
    "consumerCount",
    "consumerSetSha256",
    "consumers",
    "contractName",
    "cutoverId",
    "incumbentPortalContainerId",
    "mutationLockTokenSha256",
    "status",
    "volumeName",
}
STATE_VOLUME_CONSUMER_KEYS = {
    "classification",
    "composeOneoff",
    "composeProject",
    "composeService",
    "containerId",
    "containerName",
    "imageId",
    "jobName",
    "readWrite",
    "running",
    "volumeDestination",
}
CUTOVER_RUN_KEYS = {
    "boundaryReceiptPath",
    "boundaryReceiptSha256",
    "candidateBuildInfoPath",
    "candidateBuildInfoSha256",
    "candidateImageId",
    "candidateToolImageId",
    "contractName",
    "cutoverId",
    "finishedAtUtc",
    "jobReceipts",
    "predeployStopsAtValidateCompleted",
    "publicAcceptanceCompleted",
    "reason",
    "status",
}
CUTOVER_RUN_JOB_REFERENCE_KEYS = {"name", "path", "sha256"}
ACTIVE_RUNTIME_AUTHORITY_KEYS = {
    "contractName",
    "generatedAtUtc",
    "installLinkingAuthorityReadinessPath",
    "installLinkingAuthorityReadinessSha256",
    "portal",
    "status",
}
INSTALL_LINKING_RUNTIME_AUTHORITY_READINESS_KEYS = {
    "authorityIdentitySha256",
    "checkedAtUtc",
    "code",
    "contractName",
    "currentRoleMatches",
    "leastPrivilegeValid",
    "ready",
    "runtimeRoleSha256",
    "status",
}
ACTIVE_RUNTIME_PORTAL_KEYS = {
    "containerId",
    "containerName",
    "existed",
    "imageId",
    "proofAuthorityMountSha256",
    "proofPublicMountSha256",
    "wasRunning",
}
_LEGACY_PUBLIC_EDGE_CUTOVER_POSTDEPLOY_FIELDS = {
    "baseUrl",
    "childReceipts",
    "codeDeployReviewRequiredAuthoritySatisfied",
    "codeDeploymentAuthority",
    "contractName",
    "coreChildContracts",
    "downloadsHasMarker",
    "downloadsStatus",
    "downloadsStatusBrowserArtifactContract",
    "downloadsStatusBrowserArtifactDir",
    "downloadsStatusBrowserExitCode",
    "downloadsStatusBrowserStatus",
    "downloadsStatusBrowserStatusRedirectHeading",
    "downloadsStatusBrowserStatusRedirectHeadingExpected",
    "downloadsStatusBrowserStatusRedirectHeadingMatchesReleaseChannel",
    "downloadsStatusBrowserStatusRedirectHeadingRecognized",
    "downloadsStatusBrowserStatusRedirectHeadingUsesGenericUpdatedCopy",
    "downloadsVersionMarkerMatchesReleaseChannel",
    "downloadsVersionMarkerValue",
    "expectedFullDeploymentDigestSha256",
    "expectedPwaAssetInventorySha256",
    "expectedPwaFullDeploymentDigestSha256",
    "expectedReleaseChannel",
    "expectedReleaseRolloutState",
    "expectedReleaseStatus",
    "expectedReleaseSupportabilityState",
    "expectedReleaseVersion",
    "failures",
    "frontdoorNavigationAnalyticsRequests",
    "frontdoorNavigationAnchorArtifactContract",
    "frontdoorNavigationAnchorArtifactCurrentContractSatisfied",
    "frontdoorNavigationAnchorEntryHadQuery",
    "frontdoorNavigationAnchorFailureStage",
    "frontdoorNavigationAnchorFailureType",
    "frontdoorNavigationAnchorFinalHash",
    "frontdoorNavigationAnchorFinalPath",
    "frontdoorNavigationAnchorFinalSearch",
    "frontdoorNavigationArtifactDir",
    "frontdoorNavigationBlazorCircuitRequests",
    "frontdoorNavigationDeviceRouting",
    "frontdoorNavigationExitCode",
    "frontdoorNavigationHomepageLaneExpected",
    "frontdoorNavigationHomepageLaneMatchesReleaseChannel",
    "frontdoorNavigationHomepageLaneText",
    "frontdoorNavigationLedgerArtifactContract",
    "frontdoorNavigationLedgerArtifactCurrentContractSatisfied",
    "frontdoorNavigationLedgerGatedTargets",
    "frontdoorNavigationLedgerOpenMenuTargets",
    "frontdoorNavigationLedgerPrimary",
    "frontdoorNavigationLedgerPublicTargets",
    "frontdoorNavigationLedgerRoute",
    "frontdoorNavigationLiveSession",
    "frontdoorNavigationLiveTurnCompanionShell",
    "frontdoorNavigationMobileArtifactContract",
    "frontdoorNavigationMobileArtifactInstallContractSatisfied",
    "frontdoorNavigationPageErrors",
    "frontdoorNavigationPlayApiRequests",
    "frontdoorNavigationPlayAuthority",
    "frontdoorNavigationPlaySurface",
    "frontdoorNavigationPlaywrightCliSha256",
    "frontdoorNavigationPlaywrightPackageJsonSha256",
    "frontdoorNavigationPlaywrightPackageVersion",
    "frontdoorNavigationPlaywrightRuntimeResolutionMode",
    "frontdoorNavigationPrivateBrowserStateKeys",
    "frontdoorNavigationPrivateQueryRequests",
    "frontdoorNavigationProofClosureSha256",
    "frontdoorNavigationProofClosureStatus",
    "frontdoorNavigationPublicInstallTargets",
    "frontdoorNavigationPwaManifestPath",
    "frontdoorNavigationStatus",
    "generatedAtUtc",
    "ledgerStreamNonCacheable",
    "ledgerStreamPrecached",
    "mobileLedgerCacheControl",
    "mobileLedgerPayloadStatus",
    "mobileLedgerStatus",
    "mobileLedgerVary",
    "mobilePwaViewportArtifactContract",
    "mobilePwaViewportArtifactContractFailures",
    "mobilePwaViewportArtifactCurrentContractSatisfied",
    "mobilePwaViewportArtifactDir",
    "mobilePwaViewportExitCode",
    "mobilePwaViewportMissingRoutes",
    "mobilePwaViewportRouteCount",
    "mobilePwaViewportRoutes",
    "mobilePwaViewportStatus",
    "mobilePwaViewportViewportCount",
    "onlineLaunchContract",
    "onlineLaunchFinalUrl",
    "onlineLaunchHasBlazorMarker",
    "onlineLaunchHasRosterMarker",
    "onlineLaunchHttpStatus",
    "onlineLaunchLaunchUrl",
    "onlineLaunchStatus",
    "participateIframeRouteCount",
    "participateIframeRouteIframeCount",
    "participateIframeRouteOfflineFallbackCount",
    "participateIframeShellStatus",
    "preflightActiveLockCount",
    "preflightAllowForeignBuildLocks",
    "preflightAllowStaleForeignBuildLocks",
    "preflightBlockingLockCount",
    "preflightFindingCount",
    "preflightForeignLockCount",
    "preflightForeignLocksIgnored",
    "preflightIgnoredForeignLockCount",
    "preflightOverlayBuildInfoSourceFingerprintAggregateMatchesCurrentSource",
    "preflightOverlayBuildInfoSourceFingerprintExpectedAggregateSha256",
    "preflightOverlayBuildInfoSourceFingerprintMismatchedKeys",
    "preflightOverlayBuildInfoSourceFingerprintMissingKeys",
    "preflightOverlayBuildInfoSourceFingerprintRecordedAggregateSha256",
    "preflightOverlayRoot",
    "preflightStaleForeignLockCount",
    "preflightStaleForeignLocksIgnored",
    "preflightStaleLookingLockCount",
    "preflightStatus",
    "projectionPurpose",
    "projectionStage",
    "projectionStatus",
    "publicReleaseManifestCopySafe",
    "publicReleaseManifestHasPreviewOrReviewCaveat",
    "publicReleaseManifestUnsafeCopyMarkers",
    "pwaAssetCount",
    "pwaAssetInventoryAnchorMatches",
    "pwaDeploymentIdentity",
    "pwaFullDeploymentDigestMatchesExpected",
    "pwaFullDeploymentDigestSha256",
    "pwaManifestCount",
    "pwaRootWorkerCacheVersion",
    "pwaRootWorkerKind",
    "pwaStaticStatus",
    "readyMobileHandoffFrontdoorLaunchRoute",
    "readyMobileHandoffPacketRoles",
    "readyMobileHandoffRoleRoutes",
    "readyMobileHandoffStatus",
    "readyMobileHandoffToolIds",
    "releaseGateFindings",
    "releaseManifestChannel",
    "releaseManifestChannelMatchesReleaseChannel",
    "releaseManifestCopySafe",
    "releaseManifestHasPreviewOrReviewCaveat",
    "releaseManifestHttpStatus",
    "releaseManifestParseError",
    "releaseManifestRolloutMatchesReleaseChannel",
    "releaseManifestRolloutState",
    "releaseManifestStatus",
    "releaseManifestStatusMatchesReleaseChannel",
    "releaseManifestSupportabilityMatchesReleaseChannel",
    "releaseManifestSupportabilityState",
    "releaseManifestUnsafeCopyMarkers",
    "releaseManifestVersion",
    "releaseManifestVersionMatchesReleaseChannel",
    "releaseReady",
    "releaseUploadAuthority",
    "roleAliasRouteContract",
    "roleAliasRouteDrift",
    "roleAliasRouteResults",
    "roleAliasRouteStatus",
    "rolePwaManifestCount",
    "rolePwaManifests",
    "skipPreflight",
    "skipReleaseVersionMatch",
    "status",
    "statusRedirectHasMarker",
    "statusRedirectHeading",
    "statusRedirectHeadingExpected",
    "statusRedirectHeadingMatchesReleaseChannel",
    "statusRedirectHeadingRecognized",
    "statusRedirectHeadingUsesGenericUpdatedCopy",
    "statusRedirectVersion",
    "statusRedirectVersionMarkerMatchesReleaseChannel",
    "statusRedirectVersionMarkerValue",
    "statusRedirectVersionMatchesReleaseChannel",
    "strictInvocation",
    "strictNoAllowanceInvocation",
    "strictPreflight",
    "visibleVersion",
    "visibleVersionMatchesReleaseChannel",
}
_PUBLIC_EDGE_POSTDEPLOY_SCHEMA_AUTHORITY = (
    load_exact_public_edge_postdeploy_schema()
)
PUBLIC_EDGE_CUTOVER_POSTDEPLOY_FIELDS = frozenset(
    _PUBLIC_EDGE_POSTDEPLOY_SCHEMA_AUTHORITY["fields"]
)
PUBLIC_EDGE_CUTOVER_POSTDEPLOY_SCHEMA_SHA256 = str(
    _PUBLIC_EDGE_POSTDEPLOY_SCHEMA_AUTHORITY["sha256"]
)
if (
    _LEGACY_PUBLIC_EDGE_CUTOVER_POSTDEPLOY_FIELDS
    | {"schemaContractName", "schemaSha256"}
) != PUBLIC_EDGE_CUTOVER_POSTDEPLOY_FIELDS:
    raise RuntimeError(
        "checked-in public-edge postdeploy schema drifted from the "
        "release receipt contract"
    )
CANDIDATE_BUILD_INFO_CONTRACT = (
    "chummer.install_linking_postgres_candidate_build_info.v1"
)
CANDIDATE_BUILD_INFO_KEYS = {
    "buildSourceProvenance",
    "candidateImageId",
    "candidatePortalTag",
    "candidateToolImageId",
    "candidateToolTag",
    "canonicalPortalTagIdBeforeAndAfter",
    "canonicalToolTagIdBeforeAndAfter",
    "composeSha256",
    "contractName",
    "cutoverId",
    "envSha256",
    "generatedAtUtc",
    "operatorCriticalEnvironmentSha256",
    "operatorMountSourceSha256",
    "publicNetworkId",
    "publicNetworkName",
    "runnerSha256",
    "sourceHead",
    "status",
    "uniqueTagsPreserveCanonicalRecoveryAuthority",
}
BUILD_SOURCE_PROVENANCE_KEYS = {
    "build-dependency-contract",
    "canonical-build-context",
    "design-product",
    "fleet-media-factory-contracts",
    "hub-registry",
    "run-services-source",
}
GIT_BUILD_SOURCE_PROVENANCE_KEYS = {
    "consumedPathSha256",
    "contextFileSetSha256",
    "head",
    "ignoredInputCount",
    "originMain",
    "originUrlSha256",
    "repositoryRootSha256",
    "sensitivePathCount",
    "trackedInputCount",
}
BUILD_CONTEXT_PROVENANCE_KEYS = {
    "consumedPathSha256",
    "dockerignoreSha256",
}
BUILD_DEPENDENCY_PROVENANCE_CONTRACT = (
    "chummer.install_linking_postgres_build_dependency_provenance.v1"
)
BUILD_DEPENDENCY_PROVENANCE_KEYS = {
    "baseImages",
    "contextPolicies",
    "contractName",
    "dockerfileFrontend",
    "dockerfileSha256",
    "externalMediaProjectSha256",
    "externalMediaRestoreIsSdkOnly",
    "loopbackProbeIsSdkOnly",
    "loopbackProbeProgramSha256",
    "loopbackProbeProjectSha256",
    "packageInputSetSha256",
    "packageInputs",
    "packagePlaneContract",
    "packagePlanePackageCount",
    "postdeploySchemaContractName",
    "postdeploySchemaSha256",
    "runtimePackageManagerInvocationCount",
    "status",
}
DOCKERFILE_FRONTEND_REFERENCE = (
    "docker/dockerfile:1.4@sha256:"
    "9ba7531bd80fb0a858632727cf7a112fbfd19b17e94c4e84ced81e24ef1a0dbc"
)
DOCKER_BASE_IMAGE_REFERENCES = {
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
}
BUILD_CONTEXT_POLICY_KEYS = {
    "contextBoundary",
    "dockerignoreSha256",
    "effectiveDockerignoreSha256",
    "repositoryContained",
}
BUILD_CONTEXT_POLICY_BOUNDARIES = {
    "canonical-build-context": "canonical-root-with-explicit-allowlist",
    "design-product": "exact-clean-repository",
    "fleet-media-factory-contracts": "exact-clean-repository-subtree",
    "run-services-source": "exact-clean-repository",
}
RUN_SERVICES_PACKAGE_INPUTS = {
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
PACKAGE_PLANE_CONTRACT = "chummer-hub.package-plane-lock/v4"
CANONICAL_BUILD_SOURCE_ORIGIN_URL_SHA256 = {
    name: hashlib.sha256(url.encode("utf-8")).hexdigest()
    for name, url in {
        "design-product": (
            "https://github.com/ArchonMegalon/chummer6-design.git"
        ),
        "fleet-media-factory-contracts": (
            "https://github.com/ArchonMegalon/chummer6-media-factory.git"
        ),
        "hub-registry": (
            "https://github.com/ArchonMegalon/chummer6-hub-registry.git"
        ),
        "run-services-source": (
            "https://github.com/ArchonMegalon/chummer6-hub.git"
        ),
    }.items()
}
EXPECTED_PROOF_KEYS = {
    "transport-proof": {
        "authenticated",
        "authorityIdentitySha256",
        "contractName",
        "gssEncryptionDisabled",
        "pgStatSsl",
        "plaintextAttempted",
        "plaintextRejected",
        "plaintextSqlState",
        "status",
    },
    "prepare": {
        "appliedSchemaVersion",
        "authorityIdentitySha256",
        "contractName",
        "leastPrivilegeValid",
        "runtimeRoleSha256",
        "status",
    },
    "prove-empty-authority": {
        "appliedSchemaVersion",
        "authorityIdentitySha256",
        "commitCount",
        "contractName",
        "currentRoleMatches",
        "empty",
        "headGeneration",
        "leastPrivilegeValid",
        "runtimeRoleSha256",
        "schemaValid",
        "status",
    },
    "prove-runtime-role": {
        "authorityIdentitySha256",
        "contractName",
        "currentRoleMatches",
        "leastPrivilegeValid",
        "runtimeRoleSha256",
        "status",
    },
    "prove-local-store-absent": {
        "checkedPathCount",
        "contractName",
        "localStorePresent",
        "status",
    },
    "validate": {
        "appliedSchemaVersion",
        "authorityIdentitySha256",
        "contractName",
        "status",
    },
}
MAX_RECEIPT_BYTES = 2 * 1024 * 1024
MAX_BUILD_INFO_BYTES = 16 * 1024 * 1024


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _require_utc_timestamp(value: Any, *, label: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} timestamp is invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} timestamp is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed):
        raise ValueError(f"{label} timestamp is not UTC")
    return parsed


def _job_project(cutover_id: str, job_name: str) -> str:
    cutover_hash = hashlib.sha256(cutover_id.encode("utf-8")).hexdigest()[:16]
    job_hash = hashlib.sha256(job_name.encode("utf-8")).hexdigest()[:12]
    return f"chummer6-ilpg-{cutover_hash}-{job_hash}"


def _job_container_name(cutover_id: str, job_name: str) -> str:
    cutover_hash = hashlib.sha256(cutover_id.encode("utf-8")).hexdigest()[:24]
    return (
        f"chummer-install-linking-cutover-{cutover_hash}-"
        f"{job_name.replace('_', '-')}"
    )


def _reject_secret_material(payload: Any, *, label: str) -> None:
    if isinstance(payload, dict):
        values = []
        for key, value in payload.items():
            if (
                not isinstance(key, str)
                or public_edge_forbidden_secret_key(key, value)
            ):
                raise ValueError(
                    f"{label} contains apparent secret material"
                )
            values.append(value)
    elif isinstance(payload, list):
        values = payload
    else:
        values = ()
    for value in values:
        if isinstance(value, (dict, list)):
            _reject_secret_material(value, label=label)
        elif isinstance(value, str):
            encoded = value.encode("utf-8", "strict")
            candidates = [encoded]
            try:
                decoded = unquote_to_bytes(value)
            except (UnicodeEncodeError, ValueError):
                decoded = encoded
            if decoded != encoded:
                candidates.append(decoded)
            for candidate in candidates:
                if (
                    re.search(
                        rb"(?i)(?:passwords?|passwds?|pwds?|tokens?|secrets?|"
                        rb"credentials?|accountkeys?|sharedaccesssignatures?|"
                        rb"client[_ -]?secrets?|private[_ -]?keys?|"
                        rb"authorization|api[_ -]?keys?|"
                        rb"connection[_ -]?strings?|dsns?)"
                        rb"\s*[:=]",
                        candidate,
                    )
                    or re.search(rb"://[^/\s:@]+:[^@\s/]+@", candidate)
                    or re.search(rb"(?i)\bpostgres(?:ql)?://", candidate)
                    or re.search(
                        rb"(?i)[?&](?:access_token|api[_-]?key|password|"
                        rb"sig|signature|token)=",
                        candidate,
                    )
                    or re.search(
                        rb"(?i)-----BEGIN [A-Z0-9 ]+"
                        rb"(?:PRIVATE KEY|CERTIFICATE)-----",
                        candidate,
                    )
                    or re.search(rb"(?i)\bAccountKey\s*=", candidate)
                    or re.search(
                        rb"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{8,}",
                        candidate,
                    )
                    or re.search(
                        rb"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|"
                        rb"github_pat_[A-Za-z0-9_]{20,}|"
                        rb"(?:AKIA|ASIA)[0-9A-Z]{16}|"
                        rb"(?:sk|rk)_live_[A-Za-z0-9]{16,}|"
                        rb"xox[baprs]-[A-Za-z0-9-]{10,}|"
                        rb"AIza[0-9A-Za-z_-]{20,})\b",
                        candidate,
                    )
                    or re.search(
                        rb"\beyJ[A-Za-z0-9_-]{8,}\."
                        rb"[A-Za-z0-9_-]{8,}\."
                        rb"[A-Za-z0-9_-]{8,}\b",
                        candidate,
                    )
                ):
                    raise ValueError(
                        f"{label} contains apparent secret material"
                    )


def _validate_receipt_directory(path: Path) -> Path:
    if not path.is_absolute():
        raise ValueError("cutover boundary receipt output must be absolute")
    normalized = Path(os.path.abspath(path))
    current = Path(normalized.anchor)
    for component in normalized.parent.parts[1:]:
        current /= component
        metadata = current.lstat()
        if stat.S_ISLNK(metadata.st_mode):
            raise ValueError("cutover boundary receipt directory must not contain symlinks")
    parent_metadata = normalized.parent.lstat()
    if (
        not stat.S_ISDIR(parent_metadata.st_mode)
        or parent_metadata.st_uid != os.getuid()
        or stat.S_IMODE(parent_metadata.st_mode) != 0o700
    ):
        raise ValueError("cutover boundary receipt directory must be caller-owned mode 0700")
    return normalized


def load_existing(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    if not path.exists():
        return None, None
    metadata = path.lstat()
    if (
        path.is_symlink()
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) != 0o600
    ):
        raise ValueError("cutover boundary receipt must be a caller-owned mode-0600 regular file")
    payload = path.read_bytes()
    if len(payload) > MAX_RECEIPT_BYTES:
        raise ValueError("cutover boundary receipt is oversized")
    # The runbook uses mktemp to reserve a private pathname before the first atomic write.
    if not payload:
        return None, None
    parsed = strict_json_object(
        payload,
        label="InstallLinking cutover boundary receipt",
    )
    if payload != canonical_json_bytes(
        parsed,
        label="InstallLinking cutover boundary receipt",
    ):
        raise ValueError("cutover boundary receipt is not canonical JSON")
    return parsed, hashlib.sha256(payload).hexdigest()


def _read_private_json(
    path: Path,
    *,
    label: str,
) -> tuple[dict[str, Any], str]:
    if not path.is_absolute():
        raise ValueError(f"{label} path must be absolute")
    normalized = Path(os.path.abspath(path))
    current = Path(normalized.anchor)
    for component in normalized.parts[1:-1]:
        current /= component
        metadata = current.lstat()
        if stat.S_ISLNK(metadata.st_mode):
            raise ValueError(f"{label} path must not contain symlinks")
    metadata = normalized.lstat()
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) != 0o600
        or metadata.st_size <= 0
        or metadata.st_size > MAX_RECEIPT_BYTES
    ):
        raise ValueError(
            f"{label} must be a caller-owned mode-0600 single-link regular file"
        )
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(normalized, flags)
    try:
        before = os.fstat(descriptor)
        payload = bytearray()
        while True:
            chunk = os.read(descriptor, 64 * 1024)
            if not chunk:
                break
            payload.extend(chunk)
            if len(payload) > MAX_RECEIPT_BYTES:
                raise ValueError(f"{label} is oversized")
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    if (
        (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
            before.st_nlink,
            stat.S_IMODE(before.st_mode),
        )
        != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
            after.st_nlink,
            stat.S_IMODE(after.st_mode),
        )
        or len(payload) != before.st_size
    ):
        raise ValueError(f"{label} changed while being read")
    path_after = normalized.lstat()
    if (
        path_after.st_dev,
        path_after.st_ino,
        path_after.st_size,
        path_after.st_mtime_ns,
        path_after.st_ctime_ns,
        path_after.st_nlink,
        stat.S_IMODE(path_after.st_mode),
    ) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
        after.st_nlink,
        stat.S_IMODE(after.st_mode),
    ):
        raise ValueError(f"{label} pathname changed after read")
    raw = bytes(payload)
    parsed = strict_json_object(raw, label=label)
    if raw != canonical_json_bytes(parsed, label=label):
        raise ValueError(f"{label} is not canonical JSON")
    return parsed, hashlib.sha256(raw).hexdigest()


def _read_private_blob(
    path: Path,
    *,
    label: str,
    maximum_bytes: int = MAX_RECEIPT_BYTES,
) -> tuple[bytes, str]:
    if not path.is_absolute():
        raise ValueError(f"{label} path must be absolute")
    normalized = Path(os.path.abspath(path))
    current = Path(normalized.anchor)
    for component in normalized.parts[1:-1]:
        current /= component
        metadata = current.lstat()
        if stat.S_ISLNK(metadata.st_mode):
            raise ValueError(f"{label} path must not contain symlinks")
    metadata = normalized.lstat()
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) != 0o600
        or metadata.st_size > maximum_bytes
    ):
        raise ValueError(
            f"{label} must be a caller-owned mode-0600 single-link regular file"
        )
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(normalized, flags)
    try:
        before = os.fstat(descriptor)
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, 64 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > maximum_bytes:
                raise ValueError(f"{label} is oversized")
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    path_after = normalized.lstat()
    before_identity = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
        before.st_nlink,
        stat.S_IMODE(before.st_mode),
    )
    after_identity = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
        after.st_nlink,
        stat.S_IMODE(after.st_mode),
    )
    pathname_identity = (
        path_after.st_dev,
        path_after.st_ino,
        path_after.st_size,
        path_after.st_mtime_ns,
        path_after.st_ctime_ns,
        path_after.st_nlink,
        stat.S_IMODE(path_after.st_mode),
    )
    if before_identity != after_identity or after_identity != pathname_identity:
        raise ValueError(f"{label} changed while being read")
    raw = b"".join(chunks)
    if len(raw) != before.st_size:
        raise ValueError(f"{label} changed while being read")
    return raw, hashlib.sha256(raw).hexdigest()


def _postquiesce_job_names(attempt_id: str) -> tuple[str, ...]:
    if re.fullmatch(r"[a-z0-9][a-z0-9-]{7,31}", attempt_id) is None:
        raise ValueError("post-quiesce attempt id is invalid")
    return tuple(
        f"postquiesce-{attempt_id}-{proof_kind}"
        for proof_kind in POSTQUIESCE_PROOF_KINDS
    )


def _proof_kind(job_name: str) -> str:
    if job_name in EXPECTED_PROOF_KEYS:
        return job_name
    for proof_kind in POSTQUIESCE_PROOF_KINDS:
        marker = f"-{proof_kind}"
        if job_name.startswith("postquiesce-") and job_name.endswith(marker):
            attempt_id = job_name[len("postquiesce-") : -len(marker)]
            if job_name in _postquiesce_job_names(attempt_id):
                return proof_kind
    raise ValueError("InstallLinking operator job name is invalid")


def _expected_job_service(job_name: str) -> str:
    return EXPECTED_JOB_SERVICES[_proof_kind(job_name)]


def _expected_job_command(job_name: str) -> list[str]:
    return EXPECTED_JOB_COMMANDS[_proof_kind(job_name)]


def _validate_proof_payload(job_name: str, payload: dict[str, Any]) -> None:
    proof_kind = _proof_kind(job_name)
    if (
        set(payload) != EXPECTED_PROOF_KEYS[proof_kind]
        or
        payload.get("contractName") != EXPECTED_PROOF_CONTRACTS[proof_kind]
        or payload.get("status") != "pass"
    ):
        raise ValueError(f"{job_name} proof contract is not passing")
    if (
        proof_kind != "prove-local-store-absent"
        and re.fullmatch(
            r"[0-9a-f]{64}",
            str(payload.get("authorityIdentitySha256") or ""),
        )
        is None
    ):
        raise ValueError(f"{job_name} authority identity is invalid")
    if proof_kind == "transport-proof" and not (
        payload.get("authenticated") is True
        and payload.get("pgStatSsl") is True
        and payload.get("plaintextAttempted") is True
        and payload.get("plaintextRejected") is True
        and payload.get("plaintextSqlState") == "28000"
        and payload.get("gssEncryptionDisabled") is True
    ):
        raise ValueError("transport proof is incomplete")
    if proof_kind == "prepare" and not (
        type(payload.get("appliedSchemaVersion")) is int
        and payload.get("appliedSchemaVersion") == 2
        and payload.get("leastPrivilegeValid") is True
        and re.fullmatch(
            r"[0-9a-f]{64}",
            str(payload.get("runtimeRoleSha256") or ""),
        )
    ):
        raise ValueError("prepare proof is incomplete")
    if proof_kind == "prove-empty-authority" and not (
        type(payload.get("appliedSchemaVersion")) is int
        and payload.get("appliedSchemaVersion") == 2
        and type(payload.get("commitCount")) is int
        and payload.get("commitCount") == 0
        and payload.get("currentRoleMatches") is True
        and payload.get("empty") is True
        and type(payload.get("headGeneration")) is int
        and payload.get("headGeneration") == 0
        and payload.get("leastPrivilegeValid") is True
        and payload.get("schemaValid") is True
        and re.fullmatch(
            r"[0-9a-f]{64}",
            str(payload.get("runtimeRoleSha256") or ""),
        )
    ):
        raise ValueError("empty-authority proof is incomplete")
    if proof_kind == "prove-runtime-role" and not (
        payload.get("currentRoleMatches") is True
        and payload.get("leastPrivilegeValid") is True
        and re.fullmatch(r"[0-9a-f]{64}", str(payload.get("runtimeRoleSha256") or ""))
    ):
        raise ValueError("runtime-role proof is incomplete")
    if proof_kind == "prove-local-store-absent" and not (
        type(payload.get("checkedPathCount")) is int
        and payload.get("checkedPathCount") == 3
        and payload.get("localStorePresent") is False
    ):
        raise ValueError("local-store absence proof is incomplete")
    if proof_kind == "validate" and not (
        type(payload.get("appliedSchemaVersion")) is int
        and payload.get("appliedSchemaVersion") == 2
    ):
        raise ValueError("schema validation proof is incomplete")


def bind_state_volume_inventory(
    path: Path,
    *,
    expected_sha256: str,
    attempt_id: str,
    cutover_id: str,
    candidate_tool_image_id: str,
    mutation_lock_token_sha256: str,
) -> tuple[Path, str, dict[str, Any]]:
    normalized = Path(os.path.abspath(path))
    expected_name = (
        "INSTALL_LINKING_STATE_VOLUME_INVENTORY."
        f"post-incumbent-quiesce.{attempt_id}.json"
    )
    payload, digest = _read_private_json(
        normalized,
        label="InstallLinking state-volume consumer inventory",
    )
    _reject_secret_material(
        payload,
        label="InstallLinking state-volume consumer inventory",
    )
    consumers = payload.get("consumers")
    incumbent_id = payload.get("incumbentPortalContainerId")
    if (
        normalized.name != expected_name
        or re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is None
        or digest != expected_sha256
        or set(payload) != STATE_VOLUME_INVENTORY_KEYS
        or payload.get("contractName") != STATE_VOLUME_INVENTORY_CONTRACT
        or payload.get("status") != "pass"
        or payload.get("checkpoint") != "post_incumbent_quiesce"
        or payload.get("attemptId") != attempt_id
        or payload.get("cutoverId") != cutover_id
        or payload.get("candidateToolImageId") != candidate_tool_image_id
        or payload.get("mutationLockTokenSha256")
        != mutation_lock_token_sha256
        or payload.get("volumeName")
        != "chummer6-hub_chummer-run-api-state"
        or (
            incumbent_id is not None
            and re.fullmatch(r"[0-9a-f]{64}", str(incumbent_id)) is None
        )
        or not isinstance(consumers, list)
        or type(payload.get("consumerCount")) is not int
        or payload.get("consumerCount") != len(consumers)
        or consumers
        != sorted(
            consumers,
            key=lambda item: (
                str(item.get("containerId") or "")
                if isinstance(item, dict)
                else ""
            ),
        )
    ):
        raise ValueError(
            "InstallLinking state-volume consumer inventory is invalid"
        )
    try:
        encoded_consumers = json.dumps(
            consumers,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise ValueError(
            "InstallLinking state-volume consumer inventory is invalid"
        ) from exc
    if payload.get("consumerSetSha256") != hashlib.sha256(
        encoded_consumers
    ).hexdigest():
        raise ValueError(
            "InstallLinking state-volume consumer inventory digest drifted"
        )
    suffix = hashlib.sha256(cutover_id.encode("utf-8")).hexdigest()[:24]
    observed_ids: set[str] = set()
    observed_incumbent = False
    for consumer in consumers:
        if (
            not isinstance(consumer, dict)
            or set(consumer) != STATE_VOLUME_CONSUMER_KEYS
        ):
            raise ValueError(
                "InstallLinking state-volume consumer is open-schema"
            )
        container_id = str(consumer.get("containerId") or "")
        container_name = str(consumer.get("containerName") or "")
        image_id = str(consumer.get("imageId") or "")
        if (
            re.fullmatch(r"[0-9a-f]{64}", container_id) is None
            or container_id in observed_ids
            or re.fullmatch(
                r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}",
                container_name,
            )
            is None
            or re.fullmatch(r"sha256:[0-9a-f]{64}", image_id) is None
            or consumer.get("composeOneoff") != "False"
            or consumer.get("running") is not False
            or consumer.get("volumeDestination") != "/app/state"
        ):
            raise ValueError(
                "InstallLinking state-volume consumer is invalid"
            )
        observed_ids.add(container_id)
        if container_id == incumbent_id:
            if (
                observed_incumbent
                or consumer.get("classification") != "incumbent_portal"
                or consumer.get("composeProject") != "chummer6-hub"
                or consumer.get("composeService") != "chummer-portal"
                or consumer.get("jobName") is not None
                or consumer.get("readWrite") is not True
            ):
                raise ValueError(
                    "InstallLinking incumbent volume consumer is invalid"
                )
            observed_incumbent = True
            continue
        job_name = consumer.get("jobName")
        if not isinstance(job_name, str) or (
            job_name != "prove-local-store-absent"
            and re.fullmatch(
                r"postquiesce-[a-z0-9][a-z0-9-]{7,31}-"
                r"prove-local-store-absent",
                job_name,
            )
            is None
        ):
            raise ValueError(
                "InstallLinking governed volume consumer job is invalid"
            )
        job_hash = hashlib.sha256(job_name.encode("utf-8")).hexdigest()[:12]
        if (
            consumer.get("classification") != "governed_local_store_proof"
            or consumer.get("composeProject")
            != f"chummer6-ilpg-{suffix[:16]}-{job_hash}"
            or consumer.get("composeService")
            != "chummer-install-linking-postgres-import-presence-proof"
            or consumer.get("containerName")
            != f"chummer-install-linking-cutover-{suffix}-{job_name}"
            or image_id != candidate_tool_image_id
            or consumer.get("readWrite") is not False
        ):
            raise ValueError(
                "InstallLinking governed volume consumer is invalid"
            )
    if observed_incumbent is not (incumbent_id is not None):
        raise ValueError(
            "InstallLinking incumbent volume consumer binding drifted"
        )
    return normalized, digest, payload


def bind_phase_evidence(
    path: Path,
    *,
    phase: str,
    cutover_id: str,
    candidate_image_id: str,
    candidate_tool_image_id: str,
    candidate_build_info_sha256: str,
    candidate_build_info: dict[str, Any],
    boundary_output: Path | None = None,
    postquiesce_attempt_id: str | None = None,
) -> tuple[Path, str, dict[str, Any]]:
    evidence, evidence_sha256 = _read_private_json(
        path,
        label="InstallLinking phase evidence",
    )
    _reject_secret_material(evidence, label="InstallLinking phase evidence")
    expected_jobs = (
        _postquiesce_job_names(postquiesce_attempt_id or "")
        if phase == POSTQUIESCE_REPROOF_PHASE
        else EXPECTED_PHASE_JOBS.get(phase)
    )
    if expected_jobs is None:
        if set(evidence) != PUBLIC_ACCEPTANCE_EVIDENCE_KEYS:
            raise ValueError("public acceptance evidence is open-schema")
        if (
            phase != "public_acceptance_completed"
            or evidence.get("contractName")
            != PUBLIC_ACCEPTANCE_EVIDENCE_CONTRACT
            or evidence.get("status") != "pass"
            or evidence.get("cutoverId") != cutover_id
            or evidence.get("candidateImageId") != candidate_image_id
            or evidence.get("candidateToolImageId") != candidate_tool_image_id
            or evidence.get("candidateBuildInfoSha256")
            != candidate_build_info_sha256
            or evidence.get("candidateContainerImageId") != candidate_image_id
            or evidence.get("publicReadinessAccepted") is not True
            or evidence.get("overlayAccepted") is not True
        ):
            raise ValueError("public acceptance evidence is invalid")
        evidence_root = Path(os.path.abspath(path)).parent
        postdeploy_path = Path(str(evidence.get("postdeployReceiptPath") or ""))
        active_runtime_path = Path(
            str(evidence.get("activeRuntimeAuthorityPath") or "")
        )
        postquiesce_path = Path(
            str(evidence.get("postQuiesceReceiptPath") or "")
        )
        if (
            postdeploy_path.parent != evidence_root
            or active_runtime_path.parent != evidence_root
            or postquiesce_path.parent != evidence_root
            or postdeploy_path == active_runtime_path
            or postquiesce_path in {postdeploy_path, active_runtime_path}
        ):
            raise ValueError("public acceptance inputs escaped the evidence root")
        postdeploy, postdeploy_sha256 = _read_private_json(
            postdeploy_path,
            label="public-edge postdeploy acceptance receipt",
        )
        _reject_secret_material(
            postdeploy,
            label="public-edge postdeploy acceptance receipt",
        )
        if postdeploy.get("childReceipts") != {}:
            raise ValueError(
                "public-edge postdeploy acceptance receipt violates schema"
            )
        _require_utc_timestamp(
            postdeploy.get("generatedAtUtc"),
            label="public-edge postdeploy acceptance receipt",
        )
        if (
            evidence.get("postdeployReceiptSha256") != postdeploy_sha256
            or set(postdeploy) != PUBLIC_EDGE_CUTOVER_POSTDEPLOY_FIELDS
            or postdeploy.get("contractName")
            != "chummer.public_edge_postdeploy_gate.v1"
            or postdeploy.get("schemaContractName")
            != PUBLIC_EDGE_POSTDEPLOY_SCHEMA_CONTRACT_NAME
            or postdeploy.get("schemaSha256")
            != PUBLIC_EDGE_CUTOVER_POSTDEPLOY_SCHEMA_SHA256
            or postdeploy.get("status") != "pass"
            or postdeploy.get("failures") != []
            or postdeploy.get("strictNoAllowanceInvocation") is not True
            or postdeploy.get("strictInvocation") is not True
            or postdeploy.get("strictPreflight") is not True
            or postdeploy.get("skipPreflight") is not False
            or postdeploy.get("skipReleaseVersionMatch") is not False
            or postdeploy.get("preflightStatus") != "pass"
            or postdeploy.get("preflightBlockingLockCount") != 0
            or postdeploy.get("preflightStaleForeignLockCount") != 0
            or postdeploy.get("preflightStaleForeignLocksIgnored") is not False
            or postdeploy.get("preflightForeignLocksIgnored") is not False
            or postdeploy.get(
                "preflightOverlayBuildInfoSourceFingerprint"
                "AggregateMatchesCurrentSource"
            )
            is not True
            or postdeploy.get(
                "preflightOverlayBuildInfoSourceFingerprintMissingKeys"
            )
            != []
            or postdeploy.get(
                "preflightOverlayBuildInfoSourceFingerprintMismatchedKeys"
            )
            != []
            or postdeploy.get("readyMobileHandoffStatus") != "pass"
            or postdeploy.get("downloadsStatusBrowserStatus") != "pass"
            or postdeploy.get("downloadsStatusBrowserArtifactContract")
            != "chummer.downloads_status_e2e.v1"
            or postdeploy.get("mobilePwaViewportStatus") != "pass"
            or postdeploy.get("mobilePwaViewportArtifactContract")
            != "chummer.mobile_pwa_viewport_smoke.v1"
            or postdeploy.get(
                "mobilePwaViewportArtifactCurrentContractSatisfied"
            )
            is not True
            or postdeploy.get("mobilePwaViewportMissingRoutes") != []
            or postdeploy.get("frontdoorNavigationStatus") != "pass"
            or postdeploy.get("frontdoorNavigationMobileArtifactContract")
            != "chummer.frontdoor_mobile_install_boundary.v2"
            or postdeploy.get("frontdoorNavigationAnchorArtifactContract")
            != "chummer.frontdoor_mobile_anchor_redirect.v2"
            or postdeploy.get(
                "frontdoorNavigationMobileArtifactInstallContractSatisfied"
            )
            is not True
            or postdeploy.get(
                "frontdoorNavigationAnchorArtifactCurrentContractSatisfied"
            )
            is not True
            or postdeploy.get("frontdoorNavigationProofClosureStatus")
            != "pass"
            or re.fullmatch(
                r"[0-9a-f]{64}",
                str(
                    postdeploy.get(
                        "frontdoorNavigationProofClosureSha256"
                    )
                    or ""
                ),
            )
            is None
            or postdeploy.get("pwaFullDeploymentDigestMatchesExpected") is not True
            or postdeploy.get("pwaAssetInventoryAnchorMatches") is not True
            or re.fullmatch(
                r"[0-9a-f]{64}",
                str(postdeploy.get("expectedFullDeploymentDigestSha256") or ""),
            )
            is None
            or re.fullmatch(
                r"[0-9a-f]{64}",
                str(postdeploy.get("expectedPwaAssetInventorySha256") or ""),
            )
            is None
            or postdeploy.get("releaseReady") is not False
            or postdeploy.get("projectionPurpose") != "code-deploy"
            or postdeploy.get("projectionStatus") != "review_required"
            or postdeploy.get("projectionStage")
            != "code_deploy_review_required"
            or postdeploy.get("codeDeploymentAuthority") is not True
            or postdeploy.get("releaseUploadAuthority") is not False
            or postdeploy.get("codeDeployReviewRequiredAuthoritySatisfied")
            is not True
        ):
            raise ValueError("public-edge postdeploy acceptance receipt is invalid")
        active_runtime, active_runtime_sha256 = _read_private_json(
            active_runtime_path,
            label="public-edge active runtime authority",
        )
        _reject_secret_material(
            active_runtime,
            label="public-edge active runtime authority",
        )
        _require_utc_timestamp(
            active_runtime.get("generatedAtUtc"),
            label="public-edge active runtime authority",
        )
        portal = active_runtime.get("portal")
        if (
            evidence.get("activeRuntimeAuthoritySha256")
            != active_runtime_sha256
            or set(active_runtime) != ACTIVE_RUNTIME_AUTHORITY_KEYS
            or active_runtime.get("contractName")
            != "chummer.public-edge.active-runtime-authority/v1"
            or active_runtime.get("status") != "pass"
            or not isinstance(portal, dict)
            or set(portal) != ACTIVE_RUNTIME_PORTAL_KEYS
            or portal.get("existed") is not True
            or portal.get("wasRunning") is not True
            or portal.get("imageId") != candidate_image_id
            or re.fullmatch(
                r"[0-9a-f]{64}",
                str(portal.get("containerId") or ""),
            )
            is None
            or re.fullmatch(
                r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}",
                str(portal.get("containerName") or ""),
            )
            is None
            or re.fullmatch(
                r"[0-9a-f]{64}",
                str(portal.get("proofAuthorityMountSha256") or ""),
            )
            is None
            or portal.get("proofPublicMountSha256")
            != portal.get("proofAuthorityMountSha256")
        ):
            raise ValueError("public-edge active runtime authority is invalid")
        runtime_authority_readiness_path = Path(
            str(
                active_runtime.get(
                    "installLinkingAuthorityReadinessPath"
                )
                or ""
            )
        )
        if (
            runtime_authority_readiness_path.parent != evidence_root
            or runtime_authority_readiness_path
            in {
                postdeploy_path,
                active_runtime_path,
                postquiesce_path,
            }
        ):
            raise ValueError(
                "InstallLinking active runtime readiness escaped the evidence root"
            )
        (
            runtime_authority_readiness,
            runtime_authority_readiness_sha256,
        ) = _read_private_json(
            runtime_authority_readiness_path,
            label="InstallLinking active runtime authority readiness",
        )
        _reject_secret_material(
            runtime_authority_readiness,
            label="InstallLinking active runtime authority readiness",
        )
        _require_utc_timestamp(
            runtime_authority_readiness.get("checkedAtUtc"),
            label="InstallLinking active runtime authority readiness",
        )
        if (
            active_runtime.get(
                "installLinkingAuthorityReadinessSha256"
            )
            != runtime_authority_readiness_sha256
            or set(runtime_authority_readiness)
            != INSTALL_LINKING_RUNTIME_AUTHORITY_READINESS_KEYS
            or runtime_authority_readiness.get("contractName")
            != (
                "chummer.install_linking_postgres_"
                "runtime_authority_readiness.v1"
            )
            or runtime_authority_readiness.get("status") != "pass"
            or runtime_authority_readiness.get("ready") is not True
            or runtime_authority_readiness.get("code")
            != "runtime_role_least_privilege"
            or runtime_authority_readiness.get("currentRoleMatches")
            is not True
            or runtime_authority_readiness.get("leastPrivilegeValid")
            is not True
            or re.fullmatch(
                r"[0-9a-f]{64}",
                str(
                    runtime_authority_readiness.get(
                        "runtimeRoleSha256"
                    )
                    or ""
                ),
            )
            is None
            or re.fullmatch(
                r"[0-9a-f]{64}",
                str(
                    runtime_authority_readiness.get(
                        "authorityIdentitySha256"
                    )
                    or ""
                ),
            )
            is None
        ):
            raise ValueError(
                "InstallLinking active runtime authority readiness is invalid"
            )
        if boundary_output is None:
            raise ValueError(
                "public acceptance cannot bind post-quiesce proof without its boundary"
            )
        bound_reproofs = bind_all_postquiesce_reproofs(
            boundary_output,
            cutover_id=cutover_id,
            candidate_image_id=candidate_image_id,
            candidate_tool_image_id=candidate_tool_image_id,
            candidate_build_info_sha256=candidate_build_info_sha256,
            candidate_build_info=candidate_build_info,
        )
        _, postquiesce_sha256, postquiesce_receipt = (
            bind_postquiesce_reproof(
            postquiesce_path,
            boundary_output=boundary_output,
            cutover_id=cutover_id,
            candidate_image_id=candidate_image_id,
            candidate_tool_image_id=candidate_tool_image_id,
            candidate_build_info_sha256=candidate_build_info_sha256,
            candidate_build_info=candidate_build_info,
            )
        )
        _, _, postquiesce_phase = bind_phase_evidence(
            Path(str(postquiesce_receipt["phaseEvidencePath"])),
            phase=POSTQUIESCE_REPROOF_PHASE,
            cutover_id=cutover_id,
            candidate_image_id=candidate_image_id,
            candidate_tool_image_id=candidate_tool_image_id,
            candidate_build_info_sha256=candidate_build_info_sha256,
            candidate_build_info=candidate_build_info,
            boundary_output=boundary_output,
            postquiesce_attempt_id=str(
                postquiesce_receipt["attemptId"]
            ),
        )
        if (
            evidence.get("postQuiesceReceiptSha256")
            != postquiesce_sha256
            or (postquiesce_path, postquiesce_sha256)
            not in bound_reproofs
            or runtime_authority_readiness.get(
                "authorityIdentitySha256"
            )
            != postquiesce_phase.get("authorityIdentitySha256")
            or runtime_authority_readiness.get("runtimeRoleSha256")
            != postquiesce_phase.get("runtimeRoleSha256")
        ):
            raise ValueError("post-quiesce reproof digest drifted")
        return Path(os.path.abspath(path)), evidence_sha256, evidence

    expected_evidence_keys = (
        POSTQUIESCE_PHASE_EVIDENCE_KEYS
        if phase == POSTQUIESCE_REPROOF_PHASE
        else PHASE_EVIDENCE_KEYS
    )
    if (
        set(evidence) != expected_evidence_keys
        or evidence.get("contractName") != PHASE_EVIDENCE_CONTRACT
        or evidence.get("status") != "pass"
        or evidence.get("phase") != phase
        or evidence.get("cutoverId") != cutover_id
        or evidence.get("candidateImageId") != candidate_image_id
        or evidence.get("candidateToolImageId") != candidate_tool_image_id
        or evidence.get("candidateBuildInfoSha256")
        != candidate_build_info_sha256
        or re.fullmatch(
            r"[0-9a-f]{64}",
            str(evidence.get("authorityIdentitySha256") or ""),
        )
        is None
    ):
        raise ValueError("InstallLinking phase evidence identity drifted")
    if phase == POSTQUIESCE_REPROOF_PHASE:
        inventory_path = Path(
            str(evidence.get("volumeInventoryReceiptPath") or "")
        )
        if (
            inventory_path.parent != Path(os.path.abspath(path)).parent
            or inventory_path.name
            != (
                "INSTALL_LINKING_STATE_VOLUME_INVENTORY."
                f"post-incumbent-quiesce.{postquiesce_attempt_id}.json"
            )
            or re.fullmatch(
                r"[0-9a-f]{64}",
                str(evidence.get("volumeInventoryReceiptSha256") or ""),
            )
            is None
            or re.fullmatch(
                r"[0-9a-f]{64}",
                str(evidence.get("runtimeRoleSha256") or ""),
            )
            is None
        ):
            raise ValueError(
                "post-quiesce phase volume inventory binding is invalid"
            )
    jobs = evidence.get("jobReceipts")
    if not isinstance(jobs, list) or tuple(
        item.get("name") if isinstance(item, dict) else None for item in jobs
    ) != expected_jobs:
        raise ValueError("InstallLinking phase evidence job order is invalid")
    if any(
        not isinstance(reference, dict)
        or set(reference) != PHASE_JOB_REFERENCE_KEYS
        for reference in jobs
    ):
        raise ValueError("InstallLinking phase evidence job reference is open-schema")
    evidence_root = Path(os.path.abspath(path)).parent
    aggregate = hashlib.sha256()
    proof_payloads: dict[str, dict[str, Any]] = {}
    database_network_mode: str | None = None
    for expected_name, reference in zip(expected_jobs, jobs, strict=True):
        job_path = Path(str(reference.get("path") or ""))
        if job_path.parent != evidence_root:
            raise ValueError("InstallLinking job receipt escaped the evidence root")
        job, job_sha256 = _read_private_json(
            job_path,
            label=f"InstallLinking {expected_name} job receipt",
        )
        _reject_secret_material(
            job,
            label=f"InstallLinking {expected_name} job receipt",
        )
        expected_project = _job_project(cutover_id, expected_name)
        expected_container_name = _job_container_name(cutover_id, expected_name)
        if (
            reference.get("sha256") != job_sha256
            or set(job) != JOB_RECEIPT_KEYS
            or job.get("contractName") != JOB_RECEIPT_CONTRACT
            or job.get("status") != "pass"
            or job.get("jobName") != expected_name
            or job.get("cutoverId") != cutover_id
            or job.get("candidateImageId") != candidate_image_id
            or job.get("candidateToolImageId") != candidate_tool_image_id
            or job.get("candidateBuildInfoSha256")
            != candidate_build_info_sha256
            or job.get("containerImageId") != candidate_tool_image_id
            or job.get("composeProject") != expected_project
            or job.get("containerName") != expected_container_name
            or job.get("imageIdBefore") != candidate_tool_image_id
            or job.get("imageIdAfter") != candidate_tool_image_id
            or type(job.get("timeoutSeconds")) is not int
            or job.get("timeoutSeconds") != 180
            or job.get("timedOut") is not False
            or job.get("ambiguous") is not False
            or type(job.get("exitCode")) is not int
            or job.get("exitCode") != 0
            or job.get("containerState") != "exited"
            or job.get("retainedContainer") is not True
            or job.get("logsCaptured") is not True
            or job.get("secretCanaryLeaked") is not False
            or re.fullmatch(
                r"[0-9a-f]{64}",
                str(job.get("secretCanarySha256") or ""),
            )
            is None
            or re.fullmatch(
                r"[0-9a-f]{64}",
                str(job.get("containerId") or ""),
            )
            is None
        ):
            raise ValueError(f"InstallLinking {expected_name} job receipt is invalid")
        expected_service = _expected_job_service(expected_name)
        topology = job.get("topology")
        expected_source_digests = candidate_build_info[
            "operatorMountSourceSha256"
        ][expected_service]
        expected_mounts = [
            {
                **mount,
                "sourceIdentitySha256": expected_source_digests[
                    mount["destination"]
                ],
                "sourceKind": (
                    "volume"
                    if expected_service
                    == "chummer-install-linking-postgres-import-presence-proof"
                    else "bind"
                ),
            }
            for mount in EXPECTED_SERVICE_MOUNTS[expected_service]
        ]
        labels = topology.get("labels") if isinstance(topology, dict) else None
        if (
            job.get("service") != expected_service
            or not isinstance(topology, dict)
            or set(topology) != TOPOLOGY_KEYS
            or topology.get("service") != expected_service
            or topology.get("composeProject") != expected_project
            or topology.get("criticalEnvironmentSha256")
            != candidate_build_info[
                "operatorCriticalEnvironmentSha256"
            ][expected_service]
            or topology.get("command") != _expected_job_command(expected_name)
            or topology.get("imageId") != candidate_tool_image_id
            or topology.get("mounts") != expected_mounts
            or topology.get("tmpfs") != EXPECTED_TMPFS
            or topology.get("readOnlyRootFilesystem") is not True
            or topology.get("noNewPrivileges") is not True
            or topology.get("capDrop") != ["ALL"]
            or type(topology.get("extraHostCount")) is not int
            or not isinstance(labels, dict)
            or set(labels) != TOPOLOGY_LABEL_KEYS
            or labels.get("composeProject") != expected_project
            or labels.get("composeService") != expected_service
            or labels.get("composeOneoff") != "False"
            or re.fullmatch(
                r"[0-9a-f]{64}",
                str(labels.get("composeConfigHash") or ""),
            )
            is None
            or re.fullmatch(
                r"[1-9][0-9]*:[1-9][0-9]*",
                str(topology.get("user") or ""),
            )
            is None
            or (
                expected_service
                == "chummer-install-linking-postgres-import-presence-proof"
                and (
                    topology.get("networkMode") != "none"
                    or topology.get("networkId") != ""
                    or topology.get("extraHostCount") != 0
                )
            )
            or (
                expected_service
                != "chummer-install-linking-postgres-import-presence-proof"
                and (
                    topology.get("networkMode")
                    != candidate_build_info["publicNetworkName"]
                    or topology.get("networkId")
                    != candidate_build_info["publicNetworkId"]
                    or topology.get("extraHostCount") != 1
                )
            )
        ):
            raise ValueError(
                f"InstallLinking {expected_name} container topology is invalid"
            )
        mounts = topology["mounts"]
        tmpfs = topology["tmpfs"]
        if any(
            not isinstance(mount, dict)
            or set(mount) != TOPOLOGY_MOUNT_KEYS
            for mount in mounts
        ) or any(
            not isinstance(entry, dict)
            or set(entry) != TOPOLOGY_TMPFS_KEYS
            for entry in tmpfs
        ):
            raise ValueError(
                f"InstallLinking {expected_name} nested topology is open-schema"
            )
        if expected_service != (
            "chummer-install-linking-postgres-import-presence-proof"
        ):
            network_mode = str(topology.get("networkMode") or "")
            if re.fullmatch(r"[a-z0-9][a-z0-9_.-]{0,127}", network_mode) is None:
                raise ValueError("InstallLinking database proof network is invalid")
            if (
                database_network_mode is not None
                and database_network_mode != network_mode
            ):
                raise ValueError("InstallLinking database proof network drifted")
            database_network_mode = network_mode
        start_intent_path = Path(str(job.get("startIntentPath") or ""))
        if start_intent_path.parent != evidence_root:
            raise ValueError("InstallLinking start intent escaped the evidence root")
        start_intent, start_intent_sha256 = _read_private_json(
            start_intent_path,
            label=f"InstallLinking {expected_name} start intent",
        )
        _reject_secret_material(
            start_intent,
            label=f"InstallLinking {expected_name} start intent",
        )
        if (
            set(start_intent) != START_INTENT_KEYS
            or job.get("startIntentSha256") != start_intent_sha256
            or start_intent.get("contractName") != START_INTENT_CONTRACT
            or start_intent.get("status") != "start_pending"
            or start_intent.get("cutoverId") != cutover_id
            or start_intent.get("jobName") != expected_name
            or start_intent.get("service") != expected_service
            or start_intent.get("composeProject") != expected_project
            or start_intent.get("containerName") != expected_container_name
            or start_intent.get("containerId") != job.get("containerId")
            or start_intent.get("candidateToolImageId")
            != candidate_tool_image_id
            or start_intent.get("createdAtUtc") != job.get("startedAtUtc")
        ):
            raise ValueError(
                f"InstallLinking {expected_name} start intent is invalid"
            )
        stdout_path = Path(str(job.get("stdoutPath") or ""))
        stderr_path = Path(str(job.get("stderrPath") or ""))
        if (
            stdout_path.parent != evidence_root
            or stderr_path.parent != evidence_root
            or stdout_path == stderr_path
        ):
            raise ValueError("InstallLinking job logs escaped the evidence root")
        stdout_bytes, stdout_sha256 = _read_private_blob(
            stdout_path,
            label=f"InstallLinking {expected_name} stdout",
        )
        stderr_bytes, stderr_sha256 = _read_private_blob(
            stderr_path,
            label=f"InstallLinking {expected_name} stderr",
        )
        if (
            job.get("stdoutSha256") != stdout_sha256
            or job.get("stderrSha256") != stderr_sha256
            or stderr_bytes != b""
            or re.search(
                rb"(?i)(?:password|passwd|pwd|token|secret|credential)\s*[:=]",
                stdout_bytes + stderr_bytes,
            )
        ):
            raise ValueError(f"InstallLinking {expected_name} job logs are invalid")
        proof_path = Path(str(job.get("proofPath") or ""))
        if proof_path.parent != evidence_root:
            raise ValueError("InstallLinking proof escaped the evidence root")
        proof, proof_sha256 = _read_private_json(
            proof_path,
            label=f"InstallLinking {expected_name} proof",
        )
        if (
            job.get("proofSha256") != proof_sha256
            or stdout_bytes
            != canonical_json_bytes(
                proof,
                label=f"InstallLinking {expected_name} proof",
            )
        ):
            raise ValueError(f"InstallLinking {expected_name} proof digest drifted")
        _validate_proof_payload(expected_name, proof)
        if (
            _proof_kind(expected_name)
            != "prove-local-store-absent"
            and proof.get("authorityIdentitySha256")
            != evidence.get("authorityIdentitySha256")
        ):
            raise ValueError(
                "InstallLinking proof authority identity drifted"
            )
        proof_payloads[expected_name] = proof
        aggregate.update(expected_name.encode("utf-8"))
        aggregate.update(b"\0")
        aggregate.update(job_sha256.encode("ascii"))
        aggregate.update(b"\n")
    if evidence.get("jobReceiptChainSha256") != aggregate.hexdigest():
        raise ValueError("InstallLinking phase job-receipt chain drifted")
    if phase == "prepare_completed":
        role_hashes = {
            proof_payloads[name].get("runtimeRoleSha256")
            for name in (
                "prepare",
                "prove-empty-authority",
                "prove-runtime-role",
            )
        }
        if len(role_hashes) != 1:
            raise ValueError(
                "runtime-role proof binding drifted across the prepare phase"
            )
    if phase == POSTQUIESCE_REPROOF_PHASE:
        role_hashes = {
            proof_payloads[name].get("runtimeRoleSha256")
            for name in expected_jobs[1:]
        }
        if (
            len(role_hashes) != 1
            or evidence.get("runtimeRoleSha256") not in role_hashes
        ):
            raise ValueError(
                "runtime-role proof binding drifted across post-quiesce reproof"
            )
    return Path(os.path.abspath(path)), evidence_sha256, evidence


def validate_existing_boundary_chain(
    output: Path,
    summary: dict[str, Any],
    *,
    cutover_id: str,
    candidate_image_id: str,
    candidate_tool_image_id: str,
    active_build_info: Path,
    active_build_info_sha256: str,
    active_build_info_payload: dict[str, Any],
) -> str | None:
    prior_phase = summary.get("phase")
    if prior_phase not in SUPPORTED_PHASES:
        raise ValueError("cutover boundary prior phase is invalid")
    prior_index = PHASE_SEQUENCE[prior_phase]
    previous_receipt_sha256: str | None = None
    created_at: str | None = None
    latest: dict[str, Any] | None = None
    authority_identity_sha256: str | None = None
    for index, expected_phase in enumerate(PHASES[: prior_index + 1]):
        receipt_path = output.with_name(f"{output.name}.{expected_phase}.json")
        receipt, receipt_sha256 = _read_private_json(
            receipt_path,
            label=f"InstallLinking {expected_phase} append-only phase receipt",
        )
        _reject_secret_material(
            receipt,
            label=f"InstallLinking {expected_phase} append-only phase receipt",
        )
        if created_at is None:
            created_at = receipt.get("createdAtUtc")
        evidence_phases = tuple(
            candidate
            for candidate in PHASES[: index + 1]
            if candidate in OPERATOR_COMPLETION_PHASES
            or candidate == "public_acceptance_completed"
        )
        phase_evidence = receipt.get("phaseEvidence")
        if (
            set(receipt) != BOUNDARY_RECEIPT_KEYS
            or receipt.get("contractName") != CONTRACT_NAME
            or receipt.get("cutoverId") != cutover_id
            or receipt.get("candidateImageId") != candidate_image_id
            or receipt.get("candidateToolImageId") != candidate_tool_image_id
            or receipt.get("activeBuildInfoPath") != str(active_build_info)
            or receipt.get("activeBuildInfoSha256")
            != active_build_info_sha256
            or receipt.get("phase") != expected_phase
            or type(receipt.get("sequence")) is not int
            or receipt.get("sequence") != index + 1
            or receipt.get("previousPhase")
            != (None if index == 0 else PHASES[index - 1])
            or receipt.get("previousReceiptSha256")
            != previous_receipt_sha256
            or receipt.get("phaseReceiptPath") != str(receipt_path)
            or receipt.get("createdAtUtc") != created_at
            or not isinstance(receipt.get("updatedAtUtc"), str)
            or not isinstance(phase_evidence, list)
            or tuple(
                item.get("phase") if isinstance(item, dict) else None
                for item in phase_evidence
            )
            != evidence_phases
        ):
            raise ValueError("cutover boundary append-only phase chain drifted")
        accepted = expected_phase == "public_acceptance_completed"
        import_selected = index >= PHASE_SEQUENCE[IMPORT_SKIPPED_PHASE]
        expected_operator_image = (
            candidate_tool_image_id
            if expected_phase in OPERATOR_COMPLETION_PHASES
            else None
        )
        expected_import_disposition = (
            "skipped_no_local_store" if import_selected else None
        )
        recovery = receipt.get("recoveryAuthority")
        if (
            receipt.get("status") != ("pass" if accepted else "in_progress")
            or receipt.get("operatorContainerImageId") != expected_operator_image
            or receipt.get("irreversibleDatabaseBoundaryMayHaveBeenEntered")
            is not True
            or receipt.get("prepareCompleted")
            is not (index >= PHASE_SEQUENCE["prepare_completed"])
            or receipt.get("importDisposition") != expected_import_disposition
            or receipt.get("importCompleted") is not False
            or receipt.get("importSkippedNoLocalStore") is not import_selected
            or receipt.get("localStorePresentAtCutover")
            is not (False if import_selected else None)
            or receipt.get("dataProtectionKeyRingPosture")
            != "isolated_v2_requires_no_legacy_import"
            or receipt.get("validateCompleted")
            is not (index >= PHASE_SEQUENCE["validate_completed"])
            or receipt.get("publicAcceptanceCompleted") is not accepted
            or receipt.get("automaticDatabaseRollbackAllowed") is not False
            or not isinstance(recovery, dict)
            or set(recovery) != RECOVERY_AUTHORITY_KEYS
            or recovery
            != {
                "localMirrorRollbackAllowed": False,
                "mode": "postgres_pitr_or_governed_recovery",
                "portalAndTunnelMustRemainStoppedUntilAccepted": not accepted,
                "preserveFailedAuthorityAndLogs": True,
                "schemaOrGenerationRewindAllowed": False,
            }
        ):
            raise ValueError("cutover boundary derived safety posture drifted")
        current_evidence_path: str | None = None
        current_evidence_sha256: str | None = None
        for evidence_phase, reference in zip(
            evidence_phases,
            phase_evidence,
            strict=True,
        ):
            if (
                not isinstance(reference, dict)
                or set(reference) != BOUNDARY_EVIDENCE_REFERENCE_KEYS
                or reference.get("phase") != evidence_phase
            ):
                raise ValueError("cutover boundary evidence chain is open-schema")
            evidence_path = Path(str(reference.get("path") or ""))
            if evidence_path.parent != output.parent:
                raise ValueError("cutover boundary evidence escaped its private root")
            bound_path, bound_sha256, bound_evidence = bind_phase_evidence(
                evidence_path,
                phase=evidence_phase,
                cutover_id=cutover_id,
                candidate_image_id=candidate_image_id,
                candidate_tool_image_id=candidate_tool_image_id,
                candidate_build_info_sha256=active_build_info_sha256,
                candidate_build_info=active_build_info_payload,
                boundary_output=output,
            )
            if evidence_phase in OPERATOR_COMPLETION_PHASES:
                observed_authority = str(
                    bound_evidence.get("authorityIdentitySha256") or ""
                )
                if (
                    authority_identity_sha256 is not None
                    and authority_identity_sha256 != observed_authority
                ):
                    raise ValueError(
                        "cutover boundary PostgreSQL authority identity drifted"
                    )
                authority_identity_sha256 = observed_authority
            if (
                reference.get("path") != str(bound_path)
                or reference.get("sha256") != bound_sha256
            ):
                raise ValueError("cutover boundary prior evidence digest drifted")
            if evidence_phase == expected_phase:
                current_evidence_path = str(bound_path)
                current_evidence_sha256 = bound_sha256
        if (
            receipt.get("operatorEvidenceReceiptPath") != current_evidence_path
            or receipt.get("operatorEvidenceReceiptSha256")
            != current_evidence_sha256
        ):
            raise ValueError("cutover boundary current evidence binding drifted")
        previous_receipt_sha256 = receipt_sha256
        latest = receipt
    if latest != summary:
        raise ValueError("cutover boundary mutable summary drifted from append-only chain")
    return authority_identity_sha256


def _valid_build_dependency_provenance(
    provenance: Any,
    *,
    canonical_context_dockerignore_sha256: str,
) -> bool:
    if (
        not isinstance(provenance, dict)
        or set(provenance) != BUILD_DEPENDENCY_PROVENANCE_KEYS
        or provenance.get("contractName")
        != BUILD_DEPENDENCY_PROVENANCE_CONTRACT
        or provenance.get("status") != "pass"
        or provenance.get("dockerfileFrontend")
        != DOCKERFILE_FRONTEND_REFERENCE
        or provenance.get("baseImages") != DOCKER_BASE_IMAGE_REFERENCES
        or provenance.get("externalMediaRestoreIsSdkOnly") is not True
        or provenance.get("loopbackProbeIsSdkOnly") is not True
        or provenance.get("runtimePackageManagerInvocationCount") != 0
        or isinstance(provenance.get("packagePlanePackageCount"), bool)
        or not isinstance(provenance.get("packagePlanePackageCount"), int)
        or provenance["packagePlanePackageCount"] <= 0
        or provenance["packagePlanePackageCount"] > 1024
        or provenance.get("packagePlaneContract") != PACKAGE_PLANE_CONTRACT
        or provenance.get("postdeploySchemaContractName")
        != PUBLIC_EDGE_POSTDEPLOY_SCHEMA_CONTRACT_NAME
        or provenance.get("postdeploySchemaSha256")
        != PUBLIC_EDGE_CUTOVER_POSTDEPLOY_SCHEMA_SHA256
    ):
        return False
    for field in (
        "dockerfileSha256",
        "externalMediaProjectSha256",
        "loopbackProbeProgramSha256",
        "loopbackProbeProjectSha256",
        "packageInputSetSha256",
    ):
        if re.fullmatch(r"[0-9a-f]{64}", str(provenance.get(field) or "")) is None:
            return False

    package_inputs = provenance.get("packageInputs")
    if (
        not isinstance(package_inputs, dict)
        or set(package_inputs) != RUN_SERVICES_PACKAGE_INPUTS
        or any(
            re.fullmatch(r"[0-9a-f]{64}", str(value)) is None
            for value in package_inputs.values()
        )
        or hashlib.sha256(
            canonical_json_bytes(
                package_inputs,
                label="build package input hash set",
            )
        ).hexdigest()
        != provenance.get("packageInputSetSha256")
        or package_inputs.get(
            "scripts/public_edge_postdeploy_gate.v1.schema.json"
        )
        != provenance.get("postdeploySchemaSha256")
        or package_inputs.get("Chummer.Run.LoopbackProbe/Program.cs")
        != provenance.get("loopbackProbeProgramSha256")
        or package_inputs.get(
            "Chummer.Run.LoopbackProbe/Chummer.Run.LoopbackProbe.csproj"
        )
        != provenance.get("loopbackProbeProjectSha256")
    ):
        return False

    context_policies = provenance.get("contextPolicies")
    if (
        not isinstance(context_policies, dict)
        or set(context_policies) != set(BUILD_CONTEXT_POLICY_BOUNDARIES)
    ):
        return False
    for name, expected_boundary in BUILD_CONTEXT_POLICY_BOUNDARIES.items():
        policy = context_policies.get(name)
        if (
            not isinstance(policy, dict)
            or set(policy) != BUILD_CONTEXT_POLICY_KEYS
            or policy.get("contextBoundary") != expected_boundary
            or policy.get("repositoryContained") is not True
        ):
            return False
        dockerignore = policy.get("dockerignoreSha256")
        effective_dockerignore = policy.get(
            "effectiveDockerignoreSha256"
        )
        if name == "fleet-media-factory-contracts":
            if dockerignore is not None or effective_dockerignore is not None:
                return False
        elif (
            re.fullmatch(r"[0-9a-f]{64}", str(dockerignore or "")) is None
            or re.fullmatch(
                r"[0-9a-f]{64}",
                str(effective_dockerignore or ""),
            )
            is None
        ):
            return False
    return (
        context_policies["canonical-build-context"].get(
            "dockerignoreSha256"
        )
        == canonical_context_dockerignore_sha256
    )


def bind_active_build_info(
    path: Path,
    *,
    cutover_id: str,
    candidate_image_id: str,
    candidate_tool_image_id: str,
) -> tuple[Path, str, dict[str, Any]]:
    payload, digest = _read_private_json(
        path,
        label="InstallLinking candidate build-info",
    )
    _reject_secret_material(
        payload,
        label="InstallLinking candidate build-info",
    )
    suffix = hashlib.sha256(cutover_id.encode("utf-8")).hexdigest()[:24]
    canonical_before = (
        payload.get("canonicalPortalTagIdBeforeAndAfter"),
        payload.get("canonicalToolTagIdBeforeAndAfter"),
    )
    mount_sources = payload.get("operatorMountSourceSha256")
    critical_environment = payload.get(
        "operatorCriticalEnvironmentSha256"
    )
    build_source_provenance = payload.get("buildSourceProvenance")
    build_source_provenance_valid = (
        isinstance(build_source_provenance, dict)
        and set(build_source_provenance) == BUILD_SOURCE_PROVENANCE_KEYS
    )
    if build_source_provenance_valid:
        for name in BUILD_SOURCE_PROVENANCE_KEYS - {
            "build-dependency-contract",
            "canonical-build-context",
        }:
            source = build_source_provenance.get(name)
            if (
                not isinstance(source, dict)
                or set(source) != GIT_BUILD_SOURCE_PROVENANCE_KEYS
                or source.get("head") != source.get("originMain")
                or re.fullmatch(
                    r"[0-9a-f]{40}",
                    str(source.get("head") or ""),
                )
                is None
                or source.get("originUrlSha256")
                != CANONICAL_BUILD_SOURCE_ORIGIN_URL_SHA256[name]
                or any(
                    re.fullmatch(r"[0-9a-f]{64}", str(source.get(key) or ""))
                    is None
                    for key in (
                        "consumedPathSha256",
                        "contextFileSetSha256",
                        "repositoryRootSha256",
                    )
                )
                or isinstance(source.get("ignoredInputCount"), bool)
                or not isinstance(source.get("ignoredInputCount"), int)
                or source["ignoredInputCount"] < 0
                or source.get("sensitivePathCount") != 0
                or isinstance(source.get("trackedInputCount"), bool)
                or not isinstance(source.get("trackedInputCount"), int)
                or source["trackedInputCount"] <= 0
            ):
                build_source_provenance_valid = False
                break
        canonical_context = build_source_provenance.get(
            "canonical-build-context"
        )
        if (
            not isinstance(canonical_context, dict)
            or set(canonical_context) != BUILD_CONTEXT_PROVENANCE_KEYS
            or any(
                re.fullmatch(
                    r"[0-9a-f]{64}",
                    str(canonical_context.get(key) or ""),
                )
                is None
                for key in BUILD_CONTEXT_PROVENANCE_KEYS
            )
        ):
            build_source_provenance_valid = False
        build_dependency_provenance = build_source_provenance.get(
            "build-dependency-contract"
        )
        if (
            not isinstance(canonical_context, dict)
            or not _valid_build_dependency_provenance(
                build_dependency_provenance,
                canonical_context_dockerignore_sha256=str(
                    canonical_context.get("dockerignoreSha256") or ""
                ),
            )
        ):
            build_source_provenance_valid = False
        run_services_source = build_source_provenance.get(
            "run-services-source"
        )
        if (
            not isinstance(run_services_source, dict)
            or run_services_source.get("head") != payload.get("sourceHead")
        ):
            build_source_provenance_valid = False
    critical_environment_valid = (
        isinstance(critical_environment, dict)
        and set(critical_environment) == set(EXPECTED_SERVICE_MOUNTS)
        and all(
            re.fullmatch(r"[0-9a-f]{64}", str(value)) is not None
            for value in critical_environment.values()
        )
    )
    mount_sources_valid = (
        isinstance(mount_sources, dict)
        and set(mount_sources) == set(EXPECTED_SERVICE_MOUNTS)
    )
    if mount_sources_valid:
        for service, expected_mounts in EXPECTED_SERVICE_MOUNTS.items():
            service_sources = mount_sources.get(service)
            if (
                not isinstance(service_sources, dict)
                or set(service_sources)
                != {
                    str(item["destination"])
                    for item in expected_mounts
                }
                or any(
                    re.fullmatch(r"[0-9a-f]{64}", str(value)) is None
                    for value in service_sources.values()
                )
            ):
                mount_sources_valid = False
                break
    if (
        set(payload) != CANDIDATE_BUILD_INFO_KEYS
        or payload.get("contractName") != CANDIDATE_BUILD_INFO_CONTRACT
        or payload.get("status") != "pass"
        or payload.get("cutoverId") != cutover_id
        or payload.get("candidateImageId") != candidate_image_id
        or payload.get("candidateToolImageId") != candidate_tool_image_id
        or payload.get("candidatePortalTag")
        != f"chummer-run-api:cutover-{suffix}"
        or payload.get("candidateToolTag")
        != f"chummer-install-linking-postgres-tool:cutover-{suffix}"
        or any(
            value is not None
            and re.fullmatch(r"sha256:[0-9a-f]{64}", str(value)) is None
            for value in canonical_before
        )
        or re.fullmatch(
            r"[0-9a-f]{40}",
            str(payload.get("sourceHead") or ""),
        )
        is None
        or any(
            re.fullmatch(r"[0-9a-f]{64}", str(payload.get(field) or ""))
            is None
            for field in ("composeSha256", "envSha256", "runnerSha256")
        )
        or not isinstance(payload.get("generatedAtUtc"), str)
        or payload.get("uniqueTagsPreserveCanonicalRecoveryAuthority") is not True
        or not build_source_provenance_valid
        or not mount_sources_valid
        or not critical_environment_valid
        or re.fullmatch(
            r"[a-z0-9][a-z0-9_.-]{0,127}",
            str(payload.get("publicNetworkName") or ""),
        )
        is None
        or re.fullmatch(
            r"[0-9a-f]{64}",
            str(payload.get("publicNetworkId") or ""),
        )
        is None
    ):
        raise ValueError("InstallLinking candidate build-info contract is invalid")
    return Path(os.path.abspath(path)), digest, payload


def bind_cutover_run_receipt(
    boundary_output: Path,
    *,
    cutover_id: str,
    candidate_image_id: str,
    candidate_tool_image_id: str,
    candidate_build_info_path: Path,
    candidate_build_info_sha256: str,
    required: bool,
) -> tuple[Path, str, dict[str, Any]] | None:
    boundary_output = Path(os.path.abspath(boundary_output))
    run_path = boundary_output.parent / "INSTALL_LINKING_POSTGRES_CUTOVER_RUN.json"
    if not run_path.exists():
        if required:
            raise ValueError("passing InstallLinking cutover run receipt is missing")
        return None
    run, run_sha256 = _read_private_json(
        run_path,
        label="InstallLinking cutover run receipt",
    )
    _reject_secret_material(run, label="InstallLinking cutover run receipt")
    validate_receipt_path = boundary_output.with_name(
        f"{boundary_output.name}.validate_completed.json"
    )
    _, validate_receipt_sha256 = _read_private_json(
        validate_receipt_path,
        label="InstallLinking validate-completed boundary receipt",
    )
    job_references = run.get("jobReceipts")
    expected_names = tuple(
        name
        for phase in (
            "prepare_completed",
            IMPORT_SKIPPED_PHASE,
            "validate_completed",
        )
        for name in EXPECTED_PHASE_JOBS[phase]
    )
    if (
        set(run) != CUTOVER_RUN_KEYS
        or run.get("contractName") != CUTOVER_RUN_CONTRACT
        or run.get("status") != "pass"
        or run.get("reason") is not None
        or run.get("cutoverId") != cutover_id
        or run.get("candidateImageId") != candidate_image_id
        or run.get("candidateToolImageId") != candidate_tool_image_id
        or run.get("candidateBuildInfoPath") != str(candidate_build_info_path)
        or run.get("candidateBuildInfoSha256") != candidate_build_info_sha256
        or run.get("boundaryReceiptPath") != str(boundary_output)
        or run.get("boundaryReceiptSha256") != validate_receipt_sha256
        or run.get("predeployStopsAtValidateCompleted") is not True
        or run.get("publicAcceptanceCompleted") is not False
        or not isinstance(run.get("finishedAtUtc"), str)
        or not isinstance(job_references, list)
        or tuple(
            item.get("name") if isinstance(item, dict) else None
            for item in job_references
        )
        != expected_names
    ):
        raise ValueError(
            "InstallLinking cutover has a non-passing or unbound final run receipt"
        )
    for expected_name, reference in zip(
        expected_names,
        job_references,
        strict=True,
    ):
        if (
            not isinstance(reference, dict)
            or set(reference) != CUTOVER_RUN_JOB_REFERENCE_KEYS
        ):
            raise ValueError("InstallLinking cutover final job reference is open-schema")
        job_path = Path(str(reference.get("path") or ""))
        if (
            job_path.parent != boundary_output.parent
            or job_path.name != f"{expected_name}.job-receipt.json"
        ):
            raise ValueError("InstallLinking cutover final job reference escaped its root")
        job, job_sha256 = _read_private_json(
            job_path,
            label=f"InstallLinking final {expected_name} job receipt",
        )
        if (
            reference.get("name") != expected_name
            or reference.get("sha256") != job_sha256
            or job.get("contractName") != JOB_RECEIPT_CONTRACT
            or job.get("status") != "pass"
            or job.get("jobName") != expected_name
            or job.get("cutoverId") != cutover_id
        ):
            raise ValueError("InstallLinking cutover final job receipt drifted")
    return run_path, run_sha256, run


def bind_postquiesce_reproof(
    path: Path,
    *,
    boundary_output: Path,
    cutover_id: str,
    candidate_image_id: str,
    candidate_tool_image_id: str,
    candidate_build_info_sha256: str,
    candidate_build_info: dict[str, Any],
    expected_volume_inventory_sha256: str | None = None,
) -> tuple[Path, str, dict[str, Any]]:
    receipt, receipt_sha256 = _read_private_json(
        path,
        label="InstallLinking post-quiesce reproof receipt",
    )
    _reject_secret_material(
        receipt,
        label="InstallLinking post-quiesce reproof receipt",
    )
    normalized_path = Path(os.path.abspath(path))
    normalized_boundary = Path(os.path.abspath(boundary_output))
    validate_receipt_path = normalized_boundary.with_name(
        f"{normalized_boundary.name}.validate_completed.json"
    )
    validate_boundary, validate_boundary_sha256 = _read_private_json(
        validate_receipt_path,
        label="InstallLinking validate-completed boundary receipt",
    )
    phase_evidence_path = Path(str(receipt.get("phaseEvidencePath") or ""))
    volume_inventory_path = Path(
        str(receipt.get("volumeInventoryReceiptPath") or "")
    )
    attempt_id = str(receipt.get("attemptId") or "")
    expected_receipt_name = (
        "INSTALL_LINKING_POSTGRES_POSTQUIESCE_REPROOF."
        f"{attempt_id}.json"
    )
    if (
        normalized_path.parent != normalized_boundary.parent
        or phase_evidence_path.parent != normalized_path.parent
        or volume_inventory_path.parent != normalized_path.parent
        or normalized_path.name != expected_receipt_name
        or phase_evidence_path.name
        != f"{POSTQUIESCE_REPROOF_PHASE}.{attempt_id}.phase-evidence.json"
    ):
        raise ValueError("post-quiesce reproof escaped the cutover evidence root")
    if (
        set(receipt) != POSTQUIESCE_REPROOF_KEYS
        or re.fullmatch(r"[a-z0-9][a-z0-9-]{7,31}", attempt_id) is None
        or receipt.get("contractName") != POSTQUIESCE_REPROOF_CONTRACT
        or receipt.get("status") != "pass"
        or receipt.get("reason") is not None
        or receipt.get("startIntentWritten") is not True
        or receipt.get("containerStartMayHaveBeenInvoked") is not True
        or receipt.get("cutoverId") != cutover_id
        or receipt.get("candidateImageId") != candidate_image_id
        or receipt.get("candidateToolImageId") != candidate_tool_image_id
        or receipt.get("candidatePortalTag")
        != candidate_build_info["candidatePortalTag"]
        or receipt.get("candidateToolTag")
        != candidate_build_info["candidateToolTag"]
        or receipt.get("activeBuildInfoPath")
        != validate_boundary.get("activeBuildInfoPath")
        or receipt.get("activeBuildInfoSha256")
        != candidate_build_info_sha256
        or validate_boundary.get("activeBuildInfoSha256")
        != candidate_build_info_sha256
        or receipt.get("boundaryReceiptPath") != str(normalized_boundary)
        or receipt.get("boundaryReceiptSha256") != validate_boundary_sha256
        or receipt.get("sourceHead") != candidate_build_info["sourceHead"]
        or receipt.get("mutationLockPath")
        != "/docker/chummercomplete/.state/public-edge-mutation.lock"
        or re.fullmatch(
            r"[0-9a-f]{64}",
            str(receipt.get("mutationLockTokenSha256") or ""),
        )
        is None
        or not isinstance(receipt.get("startedAtUtc"), str)
        or not isinstance(receipt.get("finishedAtUtc"), str)
    ):
        raise ValueError("InstallLinking post-quiesce reproof receipt is invalid")
    bound_inventory_path, volume_inventory_sha256, _ = (
        bind_state_volume_inventory(
            volume_inventory_path,
            expected_sha256=str(
                receipt.get("volumeInventoryReceiptSha256") or ""
            ),
            attempt_id=attempt_id,
            cutover_id=cutover_id,
            candidate_tool_image_id=candidate_tool_image_id,
            mutation_lock_token_sha256=str(
                receipt.get("mutationLockTokenSha256") or ""
            ),
        )
    )
    if (
        receipt.get("volumeInventoryReceiptPath")
        != str(bound_inventory_path)
        or (
            expected_volume_inventory_sha256 is not None
            and volume_inventory_sha256
            != expected_volume_inventory_sha256
        )
    ):
        raise ValueError(
            "post-quiesce state-volume inventory digest drifted"
        )
    build_info_path = Path(str(receipt["activeBuildInfoPath"]))
    build_info, observed_build_info_sha256 = _read_private_json(
        build_info_path,
        label="InstallLinking post-quiesce candidate build-info",
    )
    if (
        build_info != candidate_build_info
        or observed_build_info_sha256 != candidate_build_info_sha256
    ):
        raise ValueError("post-quiesce candidate build-info binding drifted")
    bound_phase_path, phase_evidence_sha256, postquiesce_phase = (
        bind_phase_evidence(
        phase_evidence_path,
        phase=POSTQUIESCE_REPROOF_PHASE,
        cutover_id=cutover_id,
        candidate_image_id=candidate_image_id,
        candidate_tool_image_id=candidate_tool_image_id,
        candidate_build_info_sha256=candidate_build_info_sha256,
        candidate_build_info=candidate_build_info,
        boundary_output=normalized_boundary,
        postquiesce_attempt_id=attempt_id,
        )
    )
    if (
        receipt.get("phaseEvidencePath") != str(bound_phase_path)
        or receipt.get("phaseEvidenceSha256") != phase_evidence_sha256
        or postquiesce_phase.get("volumeInventoryReceiptPath")
        != str(bound_inventory_path)
        or postquiesce_phase.get("volumeInventoryReceiptSha256")
        != volume_inventory_sha256
    ):
        raise ValueError("post-quiesce phase evidence digest drifted")
    validate_references = validate_boundary.get("phaseEvidence")
    if not isinstance(validate_references, list):
        raise ValueError("predeploy authority evidence is unavailable")
    validate_reference = next(
        (
            reference
            for reference in validate_references
            if isinstance(reference, dict)
            and reference.get("phase") == "validate_completed"
        ),
        None,
    )
    if not isinstance(validate_reference, dict):
        raise ValueError("predeploy validation authority evidence is unavailable")
    _, validate_evidence_sha256, validate_evidence = bind_phase_evidence(
        Path(str(validate_reference.get("path") or "")),
        phase="validate_completed",
        cutover_id=cutover_id,
        candidate_image_id=candidate_image_id,
        candidate_tool_image_id=candidate_tool_image_id,
        candidate_build_info_sha256=candidate_build_info_sha256,
        candidate_build_info=candidate_build_info,
        boundary_output=normalized_boundary,
    )
    if (
        validate_reference.get("sha256") != validate_evidence_sha256
        or validate_evidence.get("authorityIdentitySha256")
        != postquiesce_phase.get("authorityIdentitySha256")
    ):
        raise ValueError(
            "post-quiesce PostgreSQL authority identity drifted"
        )
    return normalized_path, receipt_sha256, receipt


def classify_postquiesce_reproof(
    path: Path,
    *,
    boundary_output: Path,
    cutover_id: str,
    candidate_image_id: str,
    candidate_tool_image_id: str,
    candidate_build_info_sha256: str,
    candidate_build_info: dict[str, Any],
    expected_mutation_lock_token_sha256: str,
    expected_volume_inventory_sha256: str,
) -> tuple[str, str, dict[str, Any]]:
    receipt, receipt_sha256 = _read_private_json(
        path,
        label="InstallLinking post-quiesce outcome receipt",
    )
    _reject_secret_material(
        receipt,
        label="InstallLinking post-quiesce outcome receipt",
    )
    if receipt.get("status") == "pass":
        bound_path, bound_sha256, bound_receipt = bind_postquiesce_reproof(
            path,
            boundary_output=boundary_output,
            cutover_id=cutover_id,
            candidate_image_id=candidate_image_id,
            candidate_tool_image_id=candidate_tool_image_id,
            candidate_build_info_sha256=candidate_build_info_sha256,
            candidate_build_info=candidate_build_info,
            expected_volume_inventory_sha256=(
                expected_volume_inventory_sha256
            ),
        )
        if (
            bound_receipt.get("mutationLockTokenSha256")
            != expected_mutation_lock_token_sha256
        ):
            raise ValueError(
                "post-quiesce mutation-lock identity drifted"
            )
        return "pass", bound_sha256, bound_receipt
    if receipt.get("status") != "fail":
        return "unknown", receipt_sha256, receipt

    normalized_path = Path(os.path.abspath(path))
    normalized_boundary = Path(os.path.abspath(boundary_output))
    attempt_id = str(receipt.get("attemptId") or "")
    validate_path = normalized_boundary.with_name(
        f"{normalized_boundary.name}.validate_completed.json"
    )
    validate_boundary, validate_boundary_sha256 = _read_private_json(
        validate_path,
        label="InstallLinking validate-completed boundary receipt",
    )
    build_info_path = Path(str(receipt.get("activeBuildInfoPath") or ""))
    observed_build_info, observed_build_info_sha256 = _read_private_json(
        build_info_path,
        label="InstallLinking safe-fail candidate build-info",
    )
    volume_inventory_path = Path(
        str(receipt.get("volumeInventoryReceiptPath") or "")
    )
    reason = receipt.get("reason")
    if (
        set(receipt) != POSTQUIESCE_REPROOF_KEYS
        or normalized_path.parent != normalized_boundary.parent
        or normalized_path.name
        != (
            "INSTALL_LINKING_POSTGRES_POSTQUIESCE_REPROOF."
            f"{attempt_id}.json"
        )
        or re.fullmatch(r"[a-z0-9][a-z0-9-]{7,31}", attempt_id) is None
        or receipt.get("contractName") != POSTQUIESCE_REPROOF_CONTRACT
        or volume_inventory_path.parent != normalized_path.parent
        or not isinstance(reason, str)
        or re.fullmatch(r"(?:[A-Za-z][A-Za-z0-9_]{0,127}|signal_[0-9]+)", reason)
        is None
        or receipt.get("startIntentWritten") is not False
        or receipt.get("containerStartMayHaveBeenInvoked") is not False
        or receipt.get("phaseEvidencePath") is not None
        or receipt.get("phaseEvidenceSha256") is not None
        or receipt.get("cutoverId") != cutover_id
        or receipt.get("candidateImageId") != candidate_image_id
        or receipt.get("candidateToolImageId") != candidate_tool_image_id
        or receipt.get("candidatePortalTag")
        != candidate_build_info["candidatePortalTag"]
        or receipt.get("candidateToolTag")
        != candidate_build_info["candidateToolTag"]
        or receipt.get("activeBuildInfoPath")
        != validate_boundary.get("activeBuildInfoPath")
        or receipt.get("activeBuildInfoSha256")
        != candidate_build_info_sha256
        or validate_boundary.get("activeBuildInfoSha256")
        != candidate_build_info_sha256
        or receipt.get("boundaryReceiptPath") != str(normalized_boundary)
        or receipt.get("boundaryReceiptSha256") != validate_boundary_sha256
        or receipt.get("sourceHead") != candidate_build_info["sourceHead"]
        or receipt.get("mutationLockPath")
        != "/docker/chummercomplete/.state/public-edge-mutation.lock"
        or receipt.get("mutationLockTokenSha256")
        != expected_mutation_lock_token_sha256
        or observed_build_info != candidate_build_info
        or observed_build_info_sha256 != candidate_build_info_sha256
    ):
        raise ValueError(
            "InstallLinking post-quiesce safe-fail receipt is invalid"
        )
    _require_utc_timestamp(
        receipt.get("startedAtUtc"),
        label="InstallLinking post-quiesce safe-fail start",
    )
    _require_utc_timestamp(
        receipt.get("finishedAtUtc"),
        label="InstallLinking post-quiesce safe-fail finish",
    )
    bound_inventory_path, inventory_sha256, _ = bind_state_volume_inventory(
        volume_inventory_path,
        expected_sha256=expected_volume_inventory_sha256,
        attempt_id=attempt_id,
        cutover_id=cutover_id,
        candidate_tool_image_id=candidate_tool_image_id,
        mutation_lock_token_sha256=expected_mutation_lock_token_sha256,
    )
    if (
        receipt.get("volumeInventoryReceiptPath")
        != str(bound_inventory_path)
        or receipt.get("volumeInventoryReceiptSha256")
        != inventory_sha256
    ):
        raise ValueError(
            "post-quiesce safe-fail volume inventory drifted"
        )
    for base_name in POSTQUIESCE_PROOF_KINDS:
        job_name = f"postquiesce-{attempt_id}-{base_name}"
        for suffix in ("start-intent.json", "job-receipt.json"):
            if (normalized_path.parent / f"{job_name}.{suffix}").exists():
                raise ValueError(
                    "post-quiesce safe-fail has durable start evidence"
                )
    return "safe_fail", receipt_sha256, receipt


def bind_all_postquiesce_reproofs(
    boundary_output: Path,
    *,
    cutover_id: str,
    candidate_image_id: str,
    candidate_tool_image_id: str,
    candidate_build_info_sha256: str,
    candidate_build_info: dict[str, Any],
) -> tuple[tuple[Path, str], ...]:
    boundary_output = Path(os.path.abspath(boundary_output))
    receipt_name = re.compile(
        r"INSTALL_LINKING_POSTGRES_POSTQUIESCE_REPROOF\."
        r"([a-z0-9][a-z0-9-]{7,31})\.json"
    )
    candidates: list[Path] = []
    for entry in os.scandir(boundary_output.parent):
        if entry.name.startswith(
            "INSTALL_LINKING_POSTGRES_POSTQUIESCE_REPROOF."
        ) and receipt_name.fullmatch(entry.name) is None:
            raise ValueError("post-quiesce receipt filename is ungoverned")
        if receipt_name.fullmatch(entry.name):
            candidates.append(boundary_output.parent / entry.name)
    bound: list[tuple[Path, str]] = []
    for candidate in sorted(candidates):
        path, digest, _ = bind_postquiesce_reproof(
            candidate,
            boundary_output=boundary_output,
            cutover_id=cutover_id,
            candidate_image_id=candidate_image_id,
            candidate_tool_image_id=candidate_tool_image_id,
            candidate_build_info_sha256=candidate_build_info_sha256,
            candidate_build_info=candidate_build_info,
        )
        bound.append((path, digest))
    return tuple(bound)


def atomic_write(path: Path, payload: dict[str, Any]) -> None:
    if path.is_symlink():
        raise ValueError("cutover boundary receipt output must not be a symlink")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8", closefd=True) as handle:
            json.dump(payload, handle, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0)
        directory_descriptor = os.open(path.parent, directory_flags)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def append_phase_receipt(path: Path, payload: dict[str, Any]) -> None:
    encoded = (json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    descriptor = os.open(path, flags, 0o600)
    try:
        written = 0
        while written < len(encoded):
            written += os.write(descriptor, encoded[written:])
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0)
    directory_descriptor = os.open(path.parent, directory_flags)
    try:
        os.fsync(directory_descriptor)
    finally:
        os.close(directory_descriptor)


def materialize(
    *,
    output: Path,
    phase: str,
    cutover_id: str,
    candidate_image_id: str,
    candidate_tool_image_id: str,
    operator_container_image_id: str | None = None,
    active_build_info: Path,
    evidence_receipt: Path | None = None,
) -> dict[str, Any]:
    if phase not in SUPPORTED_PHASES:
        raise ValueError("unsupported cutover boundary phase")
    if re.fullmatch(r"sha256:[0-9a-f]{64}", candidate_image_id) is None:
        raise ValueError("candidate image id must be a full lowercase SHA-256 image id")
    if re.fullmatch(r"sha256:[0-9a-f]{64}", candidate_tool_image_id) is None:
        raise ValueError("candidate tool image id must be a full lowercase SHA-256 image id")
    if phase in OPERATOR_COMPLETION_PHASES:
        if operator_container_image_id != candidate_tool_image_id:
            raise ValueError(
                "completed operator phase must bind the exact candidate tool image id"
            )
    elif operator_container_image_id is not None:
        raise ValueError("operator container image id is not valid for this phase")
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:+-]{0,127}", cutover_id) is None:
        raise ValueError("cutover id must be a safe literal of at most 128 characters")
    output = _validate_receipt_directory(output)
    (
        active_build_info,
        active_build_info_sha256,
        active_build_info_payload,
    ) = bind_active_build_info(
        active_build_info,
        cutover_id=cutover_id,
        candidate_image_id=candidate_image_id,
        candidate_tool_image_id=candidate_tool_image_id,
    )
    if active_build_info.parent != output.parent:
        raise ValueError("candidate build-info escaped the cutover receipt root")
    existing, prior_receipt_sha256 = load_existing(output)
    prior_authority_identity_sha256: str | None = None
    if existing is not None:
        if existing.get("contractName") != CONTRACT_NAME:
            raise ValueError("cutover boundary receipt contract drifted")
        if existing.get("cutoverId") != cutover_id:
            raise ValueError("cutover boundary receipt belongs to another cutover")
        if existing.get("candidateImageId") != candidate_image_id:
            raise ValueError("cutover boundary candidate image identity drifted")
        if existing.get("candidateToolImageId") != candidate_tool_image_id:
            raise ValueError("cutover boundary candidate tool image identity drifted")
        if (
            existing.get("activeBuildInfoPath") != str(active_build_info)
            or existing.get("activeBuildInfoSha256") != active_build_info_sha256
        ):
            raise ValueError("cutover boundary active build-info binding drifted")
        prior_authority_identity_sha256 = validate_existing_boundary_chain(
            output,
            existing,
            cutover_id=cutover_id,
            candidate_image_id=candidate_image_id,
            candidate_tool_image_id=candidate_tool_image_id,
            active_build_info=active_build_info,
            active_build_info_sha256=active_build_info_sha256,
            active_build_info_payload=active_build_info_payload,
        )
    bind_cutover_run_receipt(
        output,
        cutover_id=cutover_id,
        candidate_image_id=candidate_image_id,
        candidate_tool_image_id=candidate_tool_image_id,
        candidate_build_info_path=active_build_info,
        candidate_build_info_sha256=active_build_info_sha256,
        required=phase == "public_acceptance_completed",
    )
    evidence_path: Path | None = None
    evidence_sha256: str | None = None
    if phase in OPERATOR_COMPLETION_PHASES or phase == "public_acceptance_completed":
        if evidence_receipt is None:
            raise ValueError("completed cutover phase requires bound operator evidence")
        evidence_path, evidence_sha256, bound_evidence = bind_phase_evidence(
            evidence_receipt,
            phase=phase,
            cutover_id=cutover_id,
            candidate_image_id=candidate_image_id,
            candidate_tool_image_id=candidate_tool_image_id,
            candidate_build_info_sha256=active_build_info_sha256,
            candidate_build_info=active_build_info_payload,
            boundary_output=output,
        )
        if (
            phase in OPERATOR_COMPLETION_PHASES
            and prior_authority_identity_sha256 is not None
            and bound_evidence.get("authorityIdentitySha256")
            != prior_authority_identity_sha256
        ):
            raise ValueError(
                "new cutover phase selected a different PostgreSQL authority"
            )
    elif evidence_receipt is not None:
        raise ValueError("operator evidence is not valid for this cutover phase")
    phase_index = PHASE_SEQUENCE[phase]
    created_at = now_iso()
    if existing is None:
        if phase != PHASES[0]:
            raise ValueError("cutover boundary receipt must start at prepare_starting")
    else:
        prior_phase = str(existing.get("phase") or "")
        if prior_phase not in SUPPORTED_PHASES:
            raise ValueError("cutover boundary prior phase is invalid")
        prior_phase_index = PHASE_SEQUENCE[prior_phase]
        if phase_index < prior_phase_index:
            raise ValueError("cutover boundary phase cannot move backwards")
        if phase_index == prior_phase_index:
            raise ValueError("cutover boundary phase must advance exactly once")
        if phase_index > prior_phase_index + 1:
            raise ValueError("cutover boundary phase cannot skip an irreversible checkpoint")
        created_at = str(existing.get("createdAtUtc") or created_at)
    if phase == IMPORT_SKIPPED_PHASE:
        import_disposition = "skipped_no_local_store"
    elif existing is None:
        import_disposition = None
    else:
        import_disposition = existing.get("importDisposition")
    if (
        phase_index >= PHASE_SEQUENCE[IMPORT_SKIPPED_PHASE]
        and import_disposition != "skipped_no_local_store"
    ):
        raise ValueError("cutover boundary import disposition is missing or invalid")
    if (
        phase == "public_acceptance_completed"
        and import_disposition != "skipped_no_local_store"
    ):
        raise ValueError(
            "isolated v2 Data Protection acceptance requires the explicit "
            "no-local-store import checkpoint"
        )
    accepted = phase == "public_acceptance_completed"
    phase_evidence = [] if existing is None else list(existing.get("phaseEvidence") or [])
    if evidence_path is not None and evidence_sha256 is not None:
        phase_evidence.append(
            {
                "phase": phase,
                "path": str(evidence_path),
                "sha256": evidence_sha256,
            }
        )
    payload: dict[str, Any] = {
        "contractName": CONTRACT_NAME,
        "status": "pass" if accepted else "in_progress",
        "cutoverId": cutover_id,
        "phase": phase,
        "createdAtUtc": created_at,
        "updatedAtUtc": now_iso(),
        "candidateImageId": candidate_image_id,
        "candidateToolImageId": candidate_tool_image_id,
        "operatorContainerImageId": operator_container_image_id,
        "activeBuildInfoPath": str(active_build_info),
        "activeBuildInfoSha256": active_build_info_sha256,
        "operatorEvidenceReceiptPath": (
            None if evidence_path is None else str(evidence_path)
        ),
        "operatorEvidenceReceiptSha256": evidence_sha256,
        "phaseEvidence": phase_evidence,
        "sequence": phase_index + 1,
        "previousPhase": None if existing is None else existing["phase"],
        "previousReceiptSha256": prior_receipt_sha256,
        "irreversibleDatabaseBoundaryMayHaveBeenEntered": True,
        "prepareCompleted": phase_index >= PHASES.index("prepare_completed"),
        "importDisposition": import_disposition,
        "importCompleted": False,
        "importSkippedNoLocalStore": import_disposition == "skipped_no_local_store",
        "localStorePresentAtCutover": (
            None if import_disposition is None else import_disposition == "completed"
        ),
        "dataProtectionKeyRingPosture": (
            "isolated_v2_requires_no_legacy_import"
        ),
        "validateCompleted": phase_index >= PHASE_SEQUENCE["validate_completed"],
        "publicAcceptanceCompleted": accepted,
        "automaticDatabaseRollbackAllowed": False,
        "recoveryAuthority": {
            "mode": "postgres_pitr_or_governed_recovery",
            "portalAndTunnelMustRemainStoppedUntilAccepted": not accepted,
            "preserveFailedAuthorityAndLogs": True,
            "localMirrorRollbackAllowed": False,
            "schemaOrGenerationRewindAllowed": False,
        },
    }
    phase_receipt = output.with_name(f"{output.name}.{phase}.json")
    payload["phaseReceiptPath"] = str(phase_receipt)
    append_phase_receipt(phase_receipt, payload)
    atomic_write(output, payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Advance the durable InstallLinking cutover-boundary receipt."
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--phase", choices=SUPPORTED_PHASES, required=True)
    parser.add_argument("--cutover-id", required=True)
    parser.add_argument("--candidate-image-id", required=True)
    parser.add_argument("--candidate-tool-image-id", required=True)
    parser.add_argument("--operator-container-image-id")
    parser.add_argument("--active-build-info", type=Path, required=True)
    parser.add_argument("--evidence-receipt", type=Path)
    args = parser.parse_args()
    try:
        payload = materialize(
            output=args.output,
            phase=args.phase,
            cutover_id=args.cutover_id,
            candidate_image_id=args.candidate_image_id,
            candidate_tool_image_id=args.candidate_tool_image_id,
            operator_container_image_id=args.operator_container_image_id,
            active_build_info=args.active_build_info,
            evidence_receipt=args.evidence_receipt,
        )
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(payload, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
