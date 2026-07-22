#!/usr/bin/env python3
"""Attest, but never mutate, the governed initial release-shelf cutover."""

from __future__ import annotations

import argparse
import base64
from contextlib import contextmanager
import ctypes
from datetime import datetime, timezone
import errno
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
from typing import Any, Iterator


PRESTATE_CONTRACT = "chummer.initial-release-shelf-cutover-prestate/v1"
START_CONTRACT = "chummer.initial-release-shelf-cutover-start-request/v1"
POSTSTATE_CONTRACT = "chummer.initial-release-shelf-cutover-poststate/v1"
ABORTED_CONTRACT = "chummer.initial-release-shelf-cutover-aborted/v1"
COMPLETE_CONTRACT = "chummer.initial-release-shelf-cutover-complete/v1"
DEPLOY_STATE_CONTRACT = "chummer.initial-release-shelf-cutover-deploy-state/v1"
READINESS_CONTRACT = "chummer.initial-release-shelf-steady-readiness/v1"
COMPOSE_CONTRACT = "chummer.public_edge_compose_runtime_attestation.v1"
POSTDEPLOY_CONTRACT = "chummer.public_edge_postdeploy_gate.v1"
RUNTIME_AUTHORITY_CONTRACT = "chummer.public-edge.active-runtime-authority/v1"
POINTER_SCHEMA = "chummer.release-shelf.current/v1"
CANDIDATE_SCHEMA = "chummer.release-shelf.activation-candidate/v1"
INTENT_SCHEMA = "chummer.release-shelf.activation-intent/v1"
OUTCOME_SCHEMA = "chummer.release-shelf.activation-outcome/v1"
WRITER_POLICY_SCHEMA = "chummer.release-shelf.writer-policy/v1"
WRITER_POLICY_MODE = "server-journal-v1"
MARKER_NAME = ".release-shelf-layout-v1"
MARKER_BYTES = b"chummer.release-shelf-layout/v1\n"
POINTER_NAME = "current.json"
POLICY_NAME = ".release-shelf-writer-policy.json"
ACTIVE_INTENT_NAME = ".release-shelf-activation-intent.json"
JOURNAL_NAME = ".release-shelf-activation-journal"
GENERATIONS_NAME = "generations"
LOCK_NAME = ".release-shelf-promotion.lock"
CANONICAL_MANIFEST = "RELEASE_CHANNEL.generated.json"
COMPATIBILITY_MANIFEST = "releases.json"
CANDIDATE_NAME = "activation-candidate.json"
PRESTATE_NAME = "prestate.json"
START_NAME = "candidate-start-requested.json"
POSTSTATE_NAME = "poststate.json"
ABORTED_NAME = "aborted.json"
COMPLETE_NAME = "complete.json"
COMPOSE_EVIDENCE_NAME = "cutover-final-compose-attestation.json"
READINESS_EVIDENCE_NAME = "cutover-final-publication-readiness.json"
POSTDEPLOY_EVIDENCE_NAME = "cutover-final-postdeploy-attestation.json"
RUNTIME_AUTHORITY_EVIDENCE_NAME = "cutover-final-active-runtime-authority.json"
EVIDENCE_NAMES = {
    "compose": COMPOSE_EVIDENCE_NAME,
    "postdeploy": POSTDEPLOY_EVIDENCE_NAME,
    "active-runtime": RUNTIME_AUTHORITY_EVIDENCE_NAME,
}
POSTDEPLOY_ALLOWED_FIELDS = frozenset(
    """
    baseUrl blazorNewRunnerMenuAppActiveWorkflow blazorNewRunnerMenuAppCommand
    blazorNewRunnerMenuAppDialogCount blazorNewRunnerMenuAppFileMenuLockedDuringDialog
    blazorNewRunnerMenuAppFinalUrl blazorNewRunnerMenuAppHeadline
    blazorNewRunnerMenuAppNewToolLockedDuringDialog blazorNewRunnerMenuAppResolvedHref
    blazorNewRunnerMenuAppStartupCommand blazorNewRunnerMenuAppWorkflowHeading
    blazorNewRunnerMenuArtifactContract blazorNewRunnerMenuArtifactDir
    blazorNewRunnerMenuDialogCount blazorNewRunnerMenuDialogTitle
    blazorNewRunnerMenuExitCode blazorNewRunnerMenuFinalUrl
    blazorNewRunnerMenuReopenedDataCommand blazorNewRunnerMenuReopenedDataTab
    blazorNewRunnerMenuResolvedHref blazorNewRunnerMenuStatus childReceipts
    codeDeployReviewRequiredAuthoritySatisfied codeDeploymentAuthority contractName
    coreChildContracts downloadsHasMarker downloadsStatus
    downloadsStatusBrowserArtifactContract downloadsStatusBrowserArtifactDir
    downloadsStatusBrowserExitCode downloadsStatusBrowserStatus
    downloadsStatusBrowserStatusRedirectHeading downloadsStatusBrowserStatusRedirectHeadingExpected
    downloadsStatusBrowserStatusRedirectHeadingMatchesReleaseChannel
    downloadsStatusBrowserStatusRedirectHeadingRecognized
    downloadsStatusBrowserStatusRedirectHeadingUsesGenericUpdatedCopy
    downloadsVersionMarkerMatchesReleaseChannel downloadsVersionMarkerValue
    expectedFullDeploymentDigestSha256 expectedPwaAssetInventorySha256
    expectedPwaFullDeploymentDigestSha256 expectedReleaseChannel
    expectedReleaseRolloutState expectedReleaseStatus expectedReleaseSupportabilityState
    expectedReleaseVersion failures frontdoorNavigationAnalyticsRequests
    frontdoorNavigationAnchorArtifactContract frontdoorNavigationAnchorArtifactCurrentContractSatisfied
    frontdoorNavigationAnchorEntryHadQuery frontdoorNavigationAnchorFailureStage
    frontdoorNavigationAnchorFailureType frontdoorNavigationAnchorFinalHash
    frontdoorNavigationAnchorFinalPath frontdoorNavigationAnchorFinalSearch
    frontdoorNavigationArtifactDir frontdoorNavigationBlazorCircuitRequests
    frontdoorNavigationDeviceRouting frontdoorNavigationExitCode
    frontdoorNavigationHomepageLaneExpected frontdoorNavigationHomepageLaneMatchesReleaseChannel
    frontdoorNavigationHomepageLaneText frontdoorNavigationLedgerArtifactContract
    frontdoorNavigationLedgerArtifactCurrentContractSatisfied frontdoorNavigationLedgerGatedTargets
    frontdoorNavigationLedgerOpenMenuTargets frontdoorNavigationLedgerPrimary
    frontdoorNavigationLedgerPublicTargets frontdoorNavigationLedgerRoute
    frontdoorNavigationLiveSession frontdoorNavigationLiveTurnCompanionShell
    frontdoorNavigationMobileArtifactContract frontdoorNavigationMobileArtifactInstallContractSatisfied
    frontdoorNavigationPageErrors frontdoorNavigationPlayApiRequests
    frontdoorNavigationPlayAuthority frontdoorNavigationPlaySurface
    frontdoorNavigationPlaywrightCliSha256 frontdoorNavigationPlaywrightPackageJsonSha256
    frontdoorNavigationPlaywrightPackageVersion frontdoorNavigationPlaywrightRuntimeResolutionMode
    frontdoorNavigationPrivateBrowserStateKeys frontdoorNavigationPrivateQueryRequests
    frontdoorNavigationProofClosureSha256 frontdoorNavigationProofClosureStatus
    frontdoorNavigationPublicInstallTargets frontdoorNavigationPwaManifestPath
    frontdoorNavigationStatus generatedAtUtc ledgerStreamNonCacheable ledgerStreamPrecached
    mobileLedgerCacheControl mobileLedgerPayloadStatus mobileLedgerStatus mobileLedgerVary
    mobilePwaViewportArtifactContract mobilePwaViewportArtifactContractFailures
    mobilePwaViewportArtifactCurrentContractSatisfied mobilePwaViewportArtifactDir
    mobilePwaViewportExitCode mobilePwaViewportMissingRoutes mobilePwaViewportRouteCount
    mobilePwaViewportRoutes mobilePwaViewportStatus mobilePwaViewportViewportCount
    onlineLaunchContract onlineLaunchFinalUrl onlineLaunchHasBlazorMarker onlineLaunchHasRosterMarker
    onlineLaunchHttpStatus onlineLaunchLaunchUrl onlineLaunchStatus participateIframeRouteCount
    participateIframeRouteIframeCount participateIframeRouteOfflineFallbackCount
    participateIframeShellStatus preflightActiveLockCount preflightAllowForeignBuildLocks
    preflightAllowStaleForeignBuildLocks preflightBlockingLockCount preflightFindingCount
    preflightForeignLockCount preflightForeignLocksIgnored preflightIgnoredForeignLockCount
    preflightOverlayBuildInfoSourceFingerprintAggregateMatchesCurrentSource
    preflightOverlayBuildInfoSourceFingerprintExpectedAggregateSha256
    preflightOverlayBuildInfoSourceFingerprintMismatchedKeys
    preflightOverlayBuildInfoSourceFingerprintMissingKeys
    preflightOverlayBuildInfoSourceFingerprintRecordedAggregateSha256 preflightOverlayRoot
    preflightStaleForeignLockCount preflightStaleForeignLocksIgnored
    preflightStaleLookingLockCount preflightStatus projectionPurpose projectionStage
    projectionStatus publicReleaseManifestCopySafe publicReleaseManifestHasPreviewOrReviewCaveat
    publicReleaseManifestUnsafeCopyMarkers pwaAssetCount pwaAssetInventoryAnchorMatches
    pwaDeploymentIdentity pwaFullDeploymentDigestMatchesExpected pwaFullDeploymentDigestSha256
    pwaManifestCount pwaOfflineCacheArtifactContract pwaOfflineCacheArtifactDir
    pwaOfflineCacheCacheVersion pwaOfflineCacheExitCode
    pwaOfflineCacheLegacyPrivateCachePrefixesPurged pwaOfflineCacheNavigationPolicy
    pwaOfflineCacheOfflineRoleFallbacks pwaOfflineCachePersonalizedLedgerCached
    pwaOfflineCachePrivateApiCached pwaOfflineCachePrivateNavigationCached
    pwaOfflineCachePrivateStateScope pwaOfflineCacheQueryBearingRequestsCached
    pwaOfflineCacheStaticPaths pwaOfflineCacheStatus pwaOfflineCacheUnrelatedCachePreserved
    pwaRootWorkerCacheVersion pwaRootWorkerKind pwaStaticStatus
    readyMobileHandoffFrontdoorLaunchRoute readyMobileHandoffPacketRoles
    readyMobileHandoffRoleRoutes readyMobileHandoffStatus readyMobileHandoffToolIds
    releaseGateFindings releaseManifestChannel releaseManifestChannelMatchesReleaseChannel
    releaseManifestCopySafe releaseManifestHasPreviewOrReviewCaveat releaseManifestHttpStatus
    releaseManifestParseError releaseManifestRolloutMatchesReleaseChannel
    releaseManifestRolloutState releaseManifestStatus releaseManifestStatusMatchesReleaseChannel
    releaseManifestSupportabilityMatchesReleaseChannel releaseManifestSupportabilityState
    releaseManifestUnsafeCopyMarkers releaseManifestVersion releaseManifestVersionMatchesReleaseChannel
    releaseReady releaseUploadAuthority roleAliasRouteContract roleAliasRouteDrift
    roleAliasRouteResults roleAliasRouteStatus rolePwaManifestCount rolePwaManifests
    skipPreflight skipReleaseVersionMatch status statusRedirectHasMarker
    statusRedirectHeading statusRedirectHeadingExpected statusRedirectHeadingMatchesReleaseChannel
    statusRedirectHeadingRecognized statusRedirectHeadingUsesGenericUpdatedCopy
    statusRedirectVersion statusRedirectVersionMarkerMatchesReleaseChannel
    statusRedirectVersionMarkerValue statusRedirectVersionMatchesReleaseChannel
    strictInvocation strictNoAllowanceInvocation strictPreflight visibleVersion
    visibleVersionMatchesReleaseChannel
    """.split()
)
STATE_NAMES = {
    PRESTATE_NAME,
    START_NAME,
    POSTSTATE_NAME,
    ABORTED_NAME,
    COMPLETE_NAME,
}
MAX_JSON_BYTES = 8 * 1024 * 1024
SHA256 = re.compile(r"^[0-9a-f]{64}$")
COMMIT = re.compile(r"^[0-9a-f]{40}$")
SAFE_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
CONTAINER_ID = re.compile(r"^[0-9a-f]{64}$")
IMAGE_ID = re.compile(r"^sha256:[0-9a-f]{64}$")
UTC_TIMESTAMP = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]{1,7})?(?:Z|\+00:00)$"
)
CONTROL_NAMES = {
    MARKER_NAME,
    POINTER_NAME,
    POLICY_NAME,
    ACTIVE_INTENT_NAME,
    JOURNAL_NAME,
    GENERATIONS_NAME,
    LOCK_NAME,
}


class CutoverAttestationError(RuntimeError):
    pass


class _JsonNumber:
    __slots__ = ("kind", "raw")

    def __init__(self, kind: str, raw: str) -> None:
        self.kind = kind
        self.raw = raw


class AnchoredDirectory:
    def __init__(
        self,
        path: Path,
        descriptors: list[int],
        component_names: list[str],
    ) -> None:
        self.path = path
        self._descriptors = descriptors
        self._component_names = component_names
        self._initial_link_identities = [
            _directory_link_identity(os.fstat(fd)) for fd in descriptors
        ]

    @property
    def fd(self) -> int:
        return self._descriptors[-1]

    def verify_links(self) -> None:
        for index, descriptor in enumerate(self._descriptors[:-1]):
            if (
                _directory_link_identity(os.fstat(descriptor))
                != self._initial_link_identities[index]
            ):
                raise CutoverAttestationError(
                    f"anchored directory ancestor changed: {self.path}"
                )
        for index, name in enumerate(self._component_names, start=1):
            parent_fd = self._descriptors[index - 1]
            child_fd = self._descriptors[index]
            linked = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            opened = os.fstat(child_fd)
            if (
                not stat.S_ISDIR(linked.st_mode)
                or stat.S_ISLNK(linked.st_mode)
                or (linked.st_dev, linked.st_ino)
                != (opened.st_dev, opened.st_ino)
                or (
                    index < len(self._descriptors) - 1
                    and _directory_link_identity(opened)
                    != self._initial_link_identities[index]
                )
            ):
                raise CutoverAttestationError(
                    f"anchored directory component changed: {self.path}"
                )

    def close(self) -> None:
        for descriptor in reversed(self._descriptors):
            os.close(descriptor)
        self._descriptors.clear()


class AnchoredChildDirectory:
    """A child retained through, and continuously bound to, its original parent."""

    def __init__(
        self,
        path: Path,
        parent: AnchoredDirectory,
        name: str,
        descriptor: int,
    ) -> None:
        self.path = path
        self.parent = parent
        self.name = name
        self._descriptor = descriptor
        self._initial_link_identity = _directory_link_identity(os.fstat(descriptor))

    @property
    def fd(self) -> int:
        return self._descriptor

    def verify_links(self) -> None:
        self.parent.verify_links()
        linked = os.stat(self.name, dir_fd=self.parent.fd, follow_symlinks=False)
        opened = os.fstat(self.fd)
        if (
            not stat.S_ISDIR(linked.st_mode)
            or stat.S_ISLNK(linked.st_mode)
            or _directory_link_identity(linked) != self._initial_link_identity
            or _directory_link_identity(opened) != self._initial_link_identity
        ):
            raise CutoverAttestationError(
                f"anchored child directory changed: {self.path}"
            )

    def close(self) -> None:
        if self._descriptor >= 0:
            os.close(self._descriptor)
            self._descriptor = -1


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CutoverAttestationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> object:
    raise CutoverAttestationError(f"non-JSON numeric constant: {value}")


def strict_semantic_object(raw: bytes, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=reject_duplicates,
            parse_int=lambda value: _JsonNumber("integer", value),
            parse_float=lambda value: _JsonNumber("float", value),
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CutoverAttestationError(f"malformed JSON: {label}") from exc
    if not isinstance(value, dict):
        raise CutoverAttestationError(f"JSON root is not an object: {label}")
    return value


def strict_semantic_equal(left: object, right: object) -> bool:
    if isinstance(left, _JsonNumber) or isinstance(right, _JsonNumber):
        return (
            isinstance(left, _JsonNumber)
            and isinstance(right, _JsonNumber)
            and left.kind == right.kind
            and left.raw == right.raw
        )
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return set(left) == set(right) and all(
            strict_semantic_equal(left[key], right[key]) for key in left
        )
    if isinstance(left, list):
        return len(left) == len(right) and all(
            strict_semantic_equal(a, b) for a, b in zip(left, right)
        )
    return left == right


def require_utc_timestamp(value: object, label: str) -> str:
    if not isinstance(value, str) or UTC_TIMESTAMP.fullmatch(value) is None:
        raise CutoverAttestationError(f"{label} is not a canonical UTC timestamp")
    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise CutoverAttestationError(f"{label} is not a valid UTC timestamp") from exc
    if parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise CutoverAttestationError(f"{label} is not UTC")
    return value


def utc_timestamps_equal(left: object, right: object) -> bool:
    try:
        left_text = require_utc_timestamp(left, "left timestamp")
        right_text = require_utc_timestamp(right, "right timestamp")
    except CutoverAttestationError:
        return False
    normalize = lambda value: datetime.fromisoformat(
        value[:-1] + "+00:00" if value.endswith("Z") else value
    )
    return normalize(left_text) == normalize(right_text)


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _identity(value: os.stat_result) -> tuple[int, int, int, int, int, int, int]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
        value.st_nlink,
        value.st_mode,
    )


def _directory_link_identity(value: os.stat_result) -> tuple[int, int, int]:
    return value.st_dev, value.st_ino, value.st_mode


def _normalized_absolute_path(value: str | Path, label: str) -> Path:
    text = os.fspath(value)
    path = Path(text)
    if not path.is_absolute() or os.path.normpath(text) != text:
        raise CutoverAttestationError(f"{label} must be an absolute normalized path")
    return path


def open_anchored_directory(value: str | Path, label: str) -> AnchoredDirectory:
    path = _normalized_absolute_path(value, label)
    if not hasattr(os, "O_DIRECTORY") or not hasattr(os, "O_NOFOLLOW"):
        raise CutoverAttestationError(
            "descriptor-anchored no-follow directory traversal is unavailable"
        )
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    descriptors = [os.open("/", flags)]
    names: list[str] = []
    try:
        for name in path.parts[1:]:
            if name in ("", ".", ".."):
                raise CutoverAttestationError(f"{label} has an unsafe component")
            linked = os.stat(name, dir_fd=descriptors[-1], follow_symlinks=False)
            if not stat.S_ISDIR(linked.st_mode) or stat.S_ISLNK(linked.st_mode):
                raise CutoverAttestationError(f"{label} contains a symlink component")
            child_fd = os.open(name, flags, dir_fd=descriptors[-1])
            opened = os.fstat(child_fd)
            if _directory_link_identity(linked) != _directory_link_identity(opened):
                os.close(child_fd)
                raise CutoverAttestationError(f"{label} changed while being opened")
            descriptors.append(child_fd)
            names.append(name)
        anchored = AnchoredDirectory(path, descriptors, names)
        anchored.verify_links()
        return anchored
    except Exception:
        for descriptor in reversed(descriptors):
            os.close(descriptor)
        raise


@contextmanager
def anchored_directory(value: str | Path, label: str) -> Iterator[AnchoredDirectory]:
    anchored = open_anchored_directory(value, label)
    try:
        yield anchored
    finally:
        anchored.close()


@contextmanager
def anchored_parent(
    value: str | Path, label: str
) -> Iterator[tuple[AnchoredDirectory, str]]:
    path = _normalized_absolute_path(value, label)
    if path == Path("/"):
        raise CutoverAttestationError(f"{label} cannot be the filesystem root")
    with anchored_directory(path.parent, f"{label} parent") as parent:
        yield parent, path.name


@contextmanager
def anchored_child_directory(
    parent: AnchoredDirectory,
    name: str,
    path: Path,
    label: str,
) -> Iterator[AnchoredChildDirectory]:
    descriptor = _open_child_directory(parent.fd, name, label)
    child = AnchoredChildDirectory(path, parent, name, descriptor)
    try:
        child.verify_links()
        yield child
    finally:
        child.close()


def _stable_directory_identity(descriptor: int) -> tuple[int, int, int, int, int, int, int]:
    metadata = os.fstat(descriptor)
    if not stat.S_ISDIR(metadata.st_mode):
        raise CutoverAttestationError("retained descriptor is not a directory")
    return _identity(metadata)


def _verify_directory_stable(
    anchored: AnchoredDirectory,
    before: tuple[int, int, int, int, int, int, int],
    label: str,
) -> None:
    anchored.verify_links()
    if _stable_directory_identity(anchored.fd) != before:
        raise CutoverAttestationError(f"{label} changed during attestation")


def _open_child_directory(parent_fd: int, name: str, label: str) -> int:
    if not hasattr(os, "O_DIRECTORY") or not hasattr(os, "O_NOFOLLOW"):
        raise CutoverAttestationError(
            "descriptor-anchored no-follow directory traversal is unavailable"
        )
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    linked = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    if not stat.S_ISDIR(linked.st_mode) or stat.S_ISLNK(linked.st_mode):
        raise CutoverAttestationError(f"{label} is not a real directory")
    descriptor = os.open(name, flags, dir_fd=parent_fd)
    opened = os.fstat(descriptor)
    if _directory_link_identity(linked) != _directory_link_identity(opened):
        os.close(descriptor)
        raise CutoverAttestationError(f"{label} changed while opened")
    return descriptor


def _verify_child_directory_link(
    parent_fd: int,
    name: str,
    child_fd: int,
    before: tuple[int, int, int, int, int, int, int],
    label: str,
) -> None:
    linked = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    opened = os.fstat(child_fd)
    if (
        _directory_link_identity(linked) != _directory_link_identity(opened)
        or _identity(opened) != before
    ):
        raise CutoverAttestationError(f"{label} changed during attestation")


def read_regular_file_at(
    parent_fd: int,
    name: str,
    *,
    label: str,
    maximum_bytes: int | None = None,
    owner_only: bool = False,
    require_owner: bool = False,
    forbid_group_world_write: bool = False,
    expected_owner_uid: int | None = None,
) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    linked = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    if (
        not stat.S_ISREG(linked.st_mode)
        or stat.S_ISLNK(linked.st_mode)
        or linked.st_nlink != 1
    ):
        raise CutoverAttestationError(f"not a safe single-link regular file: {label}")
    descriptor = os.open(name, flags, dir_fd=parent_fd)
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or _identity(before) != _identity(linked)
            or (owner_only and before.st_uid != os.getuid())
            or (owner_only and stat.S_IMODE(before.st_mode) != 0o600)
            or (require_owner and before.st_uid != os.getuid())
            or (
                expected_owner_uid is not None
                and before.st_uid != expected_owner_uid
            )
            or (forbid_group_world_write and stat.S_IMODE(before.st_mode) & 0o022)
        ):
            raise CutoverAttestationError(f"not a safe single-link regular file: {label}")
        if maximum_bytes is not None and before.st_size > maximum_bytes:
            raise CutoverAttestationError(f"bounded file is too large: {label}")
        chunks: list[bytes] = []
        remaining = maximum_bytes + 1 if maximum_bytes is not None else None
        while True:
            amount = 1024 * 1024 if remaining is None else min(1024 * 1024, remaining)
            if amount <= 0:
                raise CutoverAttestationError(f"bounded file is too large: {label}")
            chunk = os.read(descriptor, amount)
            if not chunk:
                break
            chunks.append(chunk)
            if remaining is not None:
                remaining -= len(chunk)
        after = os.fstat(descriptor)
        path_stat = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if (
            _identity(before) != _identity(after)
            or _identity(after) != _identity(path_stat)
        ):
            raise CutoverAttestationError(f"file changed while being read: {label}")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def read_regular_file(path: Path, *, maximum_bytes: int | None = None) -> bytes:
    with anchored_parent(path, "regular file") as (parent, name):
        before = _stable_directory_identity(parent.fd)
        raw = read_regular_file_at(
            parent.fd,
            name,
            label=str(path),
            maximum_bytes=maximum_bytes,
        )
        _verify_directory_stable(parent, before, "regular file parent")
        return raw


def read_json(path: Path, *, maximum_bytes: int = MAX_JSON_BYTES) -> tuple[dict[str, Any], bytes]:
    raw = read_regular_file(path, maximum_bytes=maximum_bytes)
    try:
        value = json.loads(raw, object_pairs_hook=reject_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CutoverAttestationError(f"malformed JSON: {path}") from exc
    if not isinstance(value, dict):
        raise CutoverAttestationError(f"JSON root is not an object: {path}")
    return value, raw


def read_json_at(
    parent_fd: int,
    name: str,
    *,
    label: str,
    maximum_bytes: int = MAX_JSON_BYTES,
    owner_only: bool = False,
    require_owner: bool = False,
    forbid_group_world_write: bool = False,
    expected_owner_uid: int | None = None,
) -> tuple[dict[str, Any], bytes]:
    raw = read_regular_file_at(
        parent_fd,
        name,
        label=label,
        maximum_bytes=maximum_bytes,
        owner_only=owner_only,
        require_owner=require_owner,
        forbid_group_world_write=forbid_group_world_write,
        expected_owner_uid=expected_owner_uid,
    )
    try:
        value = json.loads(raw, object_pairs_hook=reject_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CutoverAttestationError(f"malformed JSON: {label}") from exc
    if not isinstance(value, dict):
        raise CutoverAttestationError(f"JSON root is not an object: {label}")
    return value, raw


def require_exact_keys(value: dict[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise CutoverAttestationError(f"{label} has unexpected or missing fields")


def require_sha256(value: object, label: str, *, prefix: bool = False) -> str:
    candidate = value if isinstance(value, str) else ""
    if prefix:
        if not candidate.startswith("sha256:"):
            raise CutoverAttestationError(f"{label} is not a sha256: binding")
        candidate = candidate[7:]
    if SHA256.fullmatch(candidate) is None:
        raise CutoverAttestationError(f"{label} is not a lowercase SHA-256")
    return candidate


def require_string(value: object, label: str, *, nonempty: bool = True) -> str:
    if not isinstance(value, str) or (nonempty and not value):
        raise CutoverAttestationError(f"{label} is not a valid string")
    return value


def require_exact_bool(value: object, label: str, expected: bool | None = None) -> bool:
    if type(value) is not bool or (expected is not None and value is not expected):
        raise CutoverAttestationError(f"{label} is not the exact boolean value")
    return value


def require_exact_int(value: object, label: str, expected: int | None = None) -> int:
    if type(value) is not int or (expected is not None and value != expected):
        raise CutoverAttestationError(f"{label} is not the exact integer value")
    return value


def strict_python_equal(left: object, right: object) -> bool:
    left_raw = json.dumps({"value": left}, separators=(",", ":")).encode("utf-8")
    right_raw = json.dumps({"value": right}, separators=(",", ":")).encode("utf-8")
    return strict_semantic_equal(
        strict_semantic_object(left_raw, label="left semantic value"),
        strict_semantic_object(right_raw, label="right semantic value"),
    )


def safe_relative_path(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise CutoverAttestationError(f"{label} is not a portable relative path")
    try:
        value.encode("ascii")
    except UnicodeEncodeError as exc:
        raise CutoverAttestationError(f"{label} is not portable ASCII") from exc
    pure = PurePosixPath(value)
    if pure.is_absolute() or any(part in ("", ".", "..") for part in pure.parts):
        raise CutoverAttestationError(f"{label} is not traversal-safe")
    return value


def _hash_openat(parent_fd: int, name: str, expected: os.stat_result) -> tuple[str, int]:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(name, flags, dir_fd=parent_fd)
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or _identity(before) != _identity(expected)
        ):
            raise CutoverAttestationError(f"unsafe legacy shelf file: {name}")
        digest = hashlib.sha256()
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
        after = os.fstat(descriptor)
        if _identity(before) != _identity(after):
            raise CutoverAttestationError(f"legacy shelf file changed while read: {name}")
        return digest.hexdigest(), after.st_size
    finally:
        os.close(descriptor)


def _fresh_scandir(directory_fd: int) -> list[str]:
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    scan_fd = os.open(".", flags, dir_fd=directory_fd)
    try:
        with os.scandir(scan_fd) as iterator:
            return [entry.name for entry in iterator]
    finally:
        os.close(scan_fd)


def inventory_tree_fd(root_fd: int, *, skip_top_level_controls: bool) -> list[dict[str, Any]]:
    root_flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    retained_root_fd = os.dup(root_fd)
    rows: list[dict[str, Any]] = []
    folded_paths: set[str] = set()

    def walk(directory_fd: int, prefix: str) -> None:
        before = os.fstat(directory_fd)
        if not stat.S_ISDIR(before.st_mode):
            raise CutoverAttestationError("release shelf inventory root is not a directory")
        entries = sorted(_fresh_scandir(directory_fd))
        folded_names: set[str] = set()
        for name in entries:
            if not name or name in (".", "..") or "/" in name or "\\" in name:
                raise CutoverAttestationError("release shelf contains an unsafe entry name")
            try:
                name.encode("ascii")
            except UnicodeEncodeError as exc:
                raise CutoverAttestationError("release shelf contains a nonportable entry") from exc
            folded = name.casefold()
            if folded in folded_names:
                raise CutoverAttestationError("release shelf contains case-colliding entries")
            folded_names.add(folded)
            if not prefix and skip_top_level_controls and name in CONTROL_NAMES:
                continue
            relative = f"{prefix}/{name}" if prefix else name
            relative = safe_relative_path(relative, "release shelf inventory path")
            relative_folded = relative.casefold()
            if relative_folded in folded_paths:
                raise CutoverAttestationError("release shelf inventory contains case-colliding paths")
            folded_paths.add(relative_folded)
            metadata = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            if stat.S_ISLNK(metadata.st_mode):
                raise CutoverAttestationError(f"release shelf contains a symbolic link: {relative}")
            if stat.S_ISDIR(metadata.st_mode):
                child_fd = os.open(
                    name,
                    root_flags,
                    dir_fd=directory_fd,
                )
                try:
                    opened = os.fstat(child_fd)
                    if (opened.st_dev, opened.st_ino) != (metadata.st_dev, metadata.st_ino):
                        raise CutoverAttestationError(
                            f"release shelf directory changed while opened: {relative}"
                        )
                    walk(child_fd, relative)
                finally:
                    os.close(child_fd)
            elif stat.S_ISREG(metadata.st_mode):
                sha256, size_bytes = _hash_openat(directory_fd, name, metadata)
                rows.append(
                    {
                        "path": relative,
                        "sha256": sha256,
                        "sizeBytes": size_bytes,
                        "device": metadata.st_dev,
                        "inode": metadata.st_ino,
                        "mtimeNs": metadata.st_mtime_ns,
                        "ctimeNs": metadata.st_ctime_ns,
                        "mode": stat.S_IMODE(metadata.st_mode),
                        "linkCount": metadata.st_nlink,
                        "role": (
                            "source-manifest"
                            if relative in (CANONICAL_MANIFEST, COMPATIBILITY_MANIFEST)
                            else "payload"
                        ),
                    }
                )
            else:
                raise CutoverAttestationError(
                    f"release shelf contains a non-file entry: {relative}"
                )
        after = os.fstat(directory_fd)
        if _identity(before) != _identity(after):
            raise CutoverAttestationError("release shelf directory changed during inventory")

    try:
        walk(retained_root_fd, "")
    finally:
        os.close(retained_root_fd)
    return sorted(rows, key=lambda row: str(row["path"]))


def inventory_tree(root: Path, *, skip_top_level_controls: bool) -> list[dict[str, Any]]:
    with anchored_directory(root, "release shelf inventory root") as anchored:
        before = _stable_directory_identity(anchored.fd)
        rows = inventory_tree_fd(
            anchored.fd,
            skip_top_level_controls=skip_top_level_controls,
        )
        _verify_directory_stable(anchored, before, "release shelf inventory root")
        return rows


def shelf_closure_fd(root_fd: int) -> tuple[list[dict[str, Any]], str]:
    rows = inventory_tree_fd(root_fd, skip_top_level_controls=False)
    return rows, f"sha256:{digest_bytes(canonical_json_bytes(rows))}"


def directory_entry_names(directory_fd: int, label: str) -> list[str]:
    before = _stable_directory_identity(directory_fd)
    names: list[str] = []
    folded: dict[str, str] = {}
    for name in _fresh_scandir(directory_fd):
        try:
            name.encode("ascii")
        except UnicodeEncodeError as exc:
            raise CutoverAttestationError(f"{label} contains a nonportable entry") from exc
        prior = folded.get(name.casefold())
        if prior is not None:
            raise CutoverAttestationError(
                f"{label} has case-colliding entries: {prior}, {name}"
            )
        folded[name.casefold()] = name
        names.append(name)
    if _stable_directory_identity(directory_fd) != before:
        raise CutoverAttestationError(f"{label} changed while listed")
    return sorted(names)


def root_entries_fd(root_fd: int) -> set[str]:
    return set(directory_entry_names(root_fd, "release shelf root"))


def root_entries(root: Path) -> dict[str, Path]:
    with anchored_directory(root, "release shelf root") as anchored:
        before = _stable_directory_identity(anchored.fd)
        entries = {
            name: root / name for name in directory_entry_names(anchored.fd, "release shelf root")
        }
        _verify_directory_stable(anchored, before, "release shelf root")
        return entries


def ensure_control_name_absent(entries: dict[str, Path] | set[str], name: str) -> None:
    if any(candidate.casefold() == name.casefold() for candidate in entries):
        raise CutoverAttestationError(f"initial cutover requires exact absence of {name}")


def manifest_identity(path: Path, *, canonical: bool) -> dict[str, str]:
    payload, _ = read_json(path, maximum_bytes=4 * 1024 * 1024)
    version = payload.get("releaseVersion") or payload.get("version")
    channel = payload.get("channelId") or payload.get("channel")
    published_at = payload.get("publishedAt") or payload.get("generatedAt")
    if not all(isinstance(value, str) and value for value in (version, channel)):
        raise CutoverAttestationError(f"release manifest identity is incomplete: {path}")
    if canonical and not isinstance(published_at, str):
        raise CutoverAttestationError("canonical legacy manifest lacks publishedAt")
    return {
        "releaseVersion": str(version),
        "channel": str(channel),
        "publishedAt": str(published_at or ""),
    }


def manifest_identity_at(
    parent_fd: int,
    name: str,
    *,
    canonical: bool,
) -> dict[str, str]:
    payload, _ = read_json_at(
        parent_fd,
        name,
        label=f"release manifest {name}",
        maximum_bytes=4 * 1024 * 1024,
    )
    version = payload.get("releaseVersion") or payload.get("version")
    channel = payload.get("channelId") or payload.get("channel")
    published_at = payload.get("publishedAt") or payload.get("generatedAt")
    if not all(isinstance(value, str) and value for value in (version, channel)):
        raise CutoverAttestationError(f"release manifest identity is incomplete: {name}")
    if canonical and not isinstance(published_at, str):
        raise CutoverAttestationError("canonical legacy manifest lacks publishedAt")
    if published_at:
        require_utc_timestamp(published_at, f"{name} publishedAt")
    return {
        "releaseVersion": str(version),
        "channel": str(channel),
        "publishedAt": str(published_at or ""),
    }


def legacy_manifest_utc_instants_equal(left: object, right: object) -> bool:
    """Compare validated UTC spellings at the contract's full 100ns precision."""

    try:
        left_text = require_utc_timestamp(left, "canonical legacy manifest publishedAt")
        right_text = require_utc_timestamp(
            right, "compatibility legacy manifest publishedAt"
        )
    except CutoverAttestationError:
        return False

    def instant_key(value: str) -> tuple[str, str]:
        without_zone = value[:-1] if value.endswith("Z") else value[:-6]
        whole_seconds, separator, fraction = without_zone.partition(".")
        return whole_seconds, fraction.ljust(7, "0") if separator else "0" * 7

    return instant_key(left_text) == instant_key(right_text)


def generation_rewritten_metadata_paths(path: Path) -> list[str]:
    """Identify payload sidecars that layout-v1 intentionally route-projects."""
    payload, _ = read_json(path, maximum_bytes=4 * 1024 * 1024)
    artifacts = payload.get("downloads")
    if not isinstance(artifacts, list):
        raise CutoverAttestationError("legacy compatibility manifest downloads are malformed")
    paths: set[str] = set()
    for index, artifact in enumerate(artifacts):
        if not isinstance(artifact, dict):
            raise CutoverAttestationError(
                f"legacy compatibility manifest download {index} is malformed"
            )
        payload_name = artifact.get("payloadFileName")
        if payload_name is None:
            continue
        safe_name = safe_relative_path(
            payload_name,
            f"legacy compatibility manifest download {index} payloadFileName",
        )
        if PurePosixPath(safe_name).name != safe_name:
            raise CutoverAttestationError(
                "legacy compatibility payloadFileName must be a portable basename"
            )
        paths.add(f"files/{safe_name}.json")
    return sorted(paths)


def generation_rewritten_metadata_paths_at(parent_fd: int, name: str) -> list[str]:
    payload, _ = read_json_at(
        parent_fd,
        name,
        label="legacy compatibility manifest",
        maximum_bytes=4 * 1024 * 1024,
    )
    artifacts = payload.get("downloads")
    if not isinstance(artifacts, list):
        raise CutoverAttestationError("legacy compatibility manifest downloads are malformed")
    paths: set[str] = set()
    for index, artifact in enumerate(artifacts):
        if not isinstance(artifact, dict):
            raise CutoverAttestationError(
                f"legacy compatibility manifest download {index} is malformed"
            )
        payload_name = artifact.get("payloadFileName")
        if payload_name is None:
            continue
        safe_name = safe_relative_path(
            payload_name,
            f"legacy compatibility manifest download {index} payloadFileName",
        )
        if PurePosixPath(safe_name).name != safe_name:
            raise CutoverAttestationError(
                "legacy compatibility payloadFileName must be a portable basename"
            )
        paths.add(f"files/{safe_name}.json")
    return sorted(paths)


def validate_writer_policy(path: Path) -> dict[str, str]:
    payload, _ = read_json(path, maximum_bytes=64 * 1024)
    require_exact_keys(payload, {"schemaVersion", "mode"}, "release shelf writer policy")
    if payload != {"schemaVersion": WRITER_POLICY_SCHEMA, "mode": WRITER_POLICY_MODE}:
        raise CutoverAttestationError("release shelf writer policy is noncanonical")
    return {"schemaVersion": WRITER_POLICY_SCHEMA, "mode": WRITER_POLICY_MODE}


def validate_writer_policy_at(
    parent_fd: int,
    name: str = POLICY_NAME,
    *,
    expected_owner_uid: int | None = None,
) -> dict[str, str]:
    payload, _ = read_json_at(
        parent_fd,
        name,
        label="release shelf writer policy",
        maximum_bytes=64 * 1024,
        forbid_group_world_write=True,
        expected_owner_uid=expected_owner_uid,
    )
    require_exact_keys(payload, {"schemaVersion", "mode"}, "release shelf writer policy")
    if payload != {"schemaVersion": WRITER_POLICY_SCHEMA, "mode": WRITER_POLICY_MODE}:
        raise CutoverAttestationError("release shelf writer policy is noncanonical")
    return {"schemaVersion": WRITER_POLICY_SCHEMA, "mode": WRITER_POLICY_MODE}


def validate_persistent_promotion_lock_at(
    root_fd: int,
    entries: set[str],
    *,
    required: bool,
) -> int | None:
    candidates = sorted(
        name for name in entries if name.casefold() == LOCK_NAME.casefold()
    )
    if not candidates:
        if required:
            raise CutoverAttestationError(
                "release shelf persistent promotion lock is missing"
            )
        return None
    if candidates != [LOCK_NAME]:
        raise CutoverAttestationError(
            "release shelf persistent promotion lock has noncanonical casing"
        )
    metadata = os.stat(LOCK_NAME, dir_fd=root_fd, follow_symlinks=False)
    if (
        not stat.S_ISREG(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or metadata.st_nlink != 1
        or stat.S_IMODE(metadata.st_mode) != 0o600
    ):
        raise CutoverAttestationError(
            "release shelf persistent promotion lock is not an owner-only single-link file"
        )
    read_regular_file_at(
        root_fd,
        LOCK_NAME,
        label="release shelf persistent promotion lock",
        maximum_bytes=64 * 1024,
        expected_owner_uid=metadata.st_uid,
    )
    return metadata.st_uid


def validate_activation_intent(
    intent: dict[str, Any],
    *,
    receipt_name: str,
    require_initial: bool = False,
) -> dict[str, Any]:
    require_exact_keys(
        intent,
        {
            "schemaVersion",
            "state",
            "intent",
            "previousPointerBase64",
            "targetPointerBase64",
        },
        "release activation intent",
    )
    identity = intent.get("intent")
    if not isinstance(identity, dict):
        raise CutoverAttestationError("release activation intent identity is malformed")
    require_exact_keys(
        identity,
        {
            "operation",
            "previousGenerationId",
            "previousPointerSha256",
            "generationId",
            "activationReceiptId",
            "releaseVersion",
            "channel",
            "publishedAt",
            "inventoryDigest",
            "pointerSha256",
            "preparedAtUtc",
            "previousPointerBase64",
            "targetPointerBase64",
            "exactIncomingDesktopScope",
        },
        "release activation intent identity",
    )
    generation_id = require_string(
        identity.get("generationId"), "release activation generationId"
    )
    activation_receipt_id = require_string(
        identity.get("activationReceiptId"),
        "release activation activationReceiptId",
    )
    operation = identity.get("operation")
    allowed_operations = {"promotion"} if require_initial else {"promotion", "rollback"}
    if (
        intent.get("schemaVersion") != INTENT_SCHEMA
        or intent.get("state") != "prepared"
        or operation not in allowed_operations
        or SAFE_TOKEN.fullmatch(generation_id) is None
        or SAFE_TOKEN.fullmatch(activation_receipt_id) is None
        or activation_receipt_id != receipt_name
    ):
        raise CutoverAttestationError("release activation intent is invalid")
    require_string(identity.get("releaseVersion"), "release activation releaseVersion")
    require_string(identity.get("channel"), "release activation channel")
    require_utc_timestamp(identity.get("publishedAt"), "release activation publishedAt")
    require_utc_timestamp(
        identity.get("preparedAtUtc"), "release activation preparedAtUtc"
    )
    require_sha256(
        identity.get("inventoryDigest"),
        "release activation inventoryDigest",
        prefix=True,
    )
    require_sha256(
        identity.get("pointerSha256"),
        "release activation pointerSha256",
        prefix=True,
    )
    previous_generation = identity.get("previousGenerationId")
    previous_sha = identity.get("previousPointerSha256")
    previous_base64 = identity.get("previousPointerBase64")
    if operation == "rollback" and previous_generation is None:
        raise CutoverAttestationError(
            "release activation rollback lacks its previous generation binding"
        )
    if previous_generation is None:
        if previous_sha is not None or previous_base64 is not None:
            raise CutoverAttestationError(
                "release activation previous pointer binding is inconsistent"
            )
    else:
        if (
            not isinstance(previous_generation, str)
            or SAFE_TOKEN.fullmatch(previous_generation) is None
            or previous_sha is None
            or not isinstance(previous_base64, str)
        ):
            raise CutoverAttestationError(
                "release activation previous pointer binding is invalid"
            )
        require_sha256(
            previous_sha,
            "release activation previousPointerSha256",
            prefix=True,
        )
    target_base64 = require_string(
        identity.get("targetPointerBase64"),
        "release activation targetPointerBase64",
    )
    if (
        intent.get("previousPointerBase64") != previous_base64
        or intent.get("targetPointerBase64") != target_base64
    ):
        raise CutoverAttestationError(
            "release activation top-level pointer bytes are inconsistent"
        )
    decoded_bindings: dict[str, bytes] = {}
    for binding_name, value, label in (
        (
            "previous",
            previous_base64,
            "release activation previousPointerBase64",
        ),
        (
            "target",
            target_base64,
            "release activation targetPointerBase64",
        ),
    ):
        if value is None:
            continue
        try:
            decoded_bindings[binding_name] = base64.b64decode(value, validate=True)
        except (ValueError, TypeError) as exc:
            raise CutoverAttestationError(f"{label} is not canonical base64") from exc
    target_bytes = decoded_bindings["target"]
    if identity.get("pointerSha256") != f"sha256:{digest_bytes(target_bytes)}":
        raise CutoverAttestationError(
            "release activation target pointer bytes disagree with pointerSha256"
        )
    if previous_sha is not None and previous_sha != (
        f"sha256:{digest_bytes(decoded_bindings['previous'])}"
    ):
        raise CutoverAttestationError(
            "release activation previous pointer bytes disagree with previousPointerSha256"
        )
    try:
        target_pointer = json.loads(
            target_bytes,
            object_pairs_hook=reject_duplicates,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CutoverAttestationError(
            "release activation target pointer bytes are malformed"
        ) from exc
    if not isinstance(target_pointer, dict):
        raise CutoverAttestationError(
            "release activation target pointer is not an object"
        )
    require_exact_keys(
        target_pointer,
        {
            "schemaVersion",
            "generationId",
            "releaseVersion",
            "channel",
            "publishedAt",
            "manifests",
            "inventoryDigest",
            "activatedAt",
            "activationReceiptId",
        },
        "release activation target pointer",
    )
    if (
        target_pointer.get("schemaVersion") != POINTER_SCHEMA
        or target_pointer.get("generationId") != generation_id
        or target_pointer.get("activationReceiptId") != activation_receipt_id
        or target_pointer.get("releaseVersion") != identity.get("releaseVersion")
        or target_pointer.get("channel") != identity.get("channel")
        or not utc_timestamps_equal(
            target_pointer.get("publishedAt"), identity.get("publishedAt")
        )
        or target_pointer.get("inventoryDigest") != identity.get("inventoryDigest")
    ):
        raise CutoverAttestationError(
            "release activation target pointer disagrees with intent identity"
        )
    require_utc_timestamp(
        target_pointer.get("activatedAt"),
        "release activation target pointer activatedAt",
    )
    _validate_manifest_binding(
        target_pointer, generation_id, "canonical", CANONICAL_MANIFEST
    )
    _validate_manifest_binding(
        target_pointer, generation_id, "compatibility", COMPATIBILITY_MANIFEST
    )
    if previous_generation is not None:
        try:
            previous_pointer = json.loads(
                decoded_bindings["previous"],
                object_pairs_hook=reject_duplicates,
                parse_constant=_reject_json_constant,
            )
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CutoverAttestationError(
                "release activation previous pointer bytes are malformed"
            ) from exc
        if (
            not isinstance(previous_pointer, dict)
            or previous_pointer.get("schemaVersion") != POINTER_SCHEMA
            or previous_pointer.get("generationId") != previous_generation
        ):
            raise CutoverAttestationError(
                "release activation previous pointer identity is invalid"
            )
    exact_scope = identity.get("exactIncomingDesktopScope")
    if exact_scope is not None:
        require_string(exact_scope, "release activation exactIncomingDesktopScope")
    if require_initial and (
        previous_generation is not None
        or previous_sha is not None
        or previous_base64 is not None
        or exact_scope is not None
    ):
        raise CutoverAttestationError(
            "initial release activation intent has predecessor or scoped state"
        )
    return identity


def journal_outcomes(root: Path, entries: dict[str, Path]) -> list[dict[str, str]]:
    journal_candidates = [name for name in entries if name.casefold() == JOURNAL_NAME.casefold()]
    if not journal_candidates:
        return []
    if journal_candidates != [JOURNAL_NAME]:
        raise CutoverAttestationError("release activation journal has noncanonical casing")
    journal_root = entries[JOURNAL_NAME]
    if journal_root.is_symlink() or not journal_root.is_dir():
        raise CutoverAttestationError("release activation journal is not a regular directory")
    results: list[dict[str, str]] = []
    for receipt in sorted(journal_root.iterdir(), key=lambda value: value.name):
        if not SAFE_TOKEN.fullmatch(receipt.name) or receipt.is_symlink() or not receipt.is_dir():
            raise CutoverAttestationError("release activation receipt path is unsafe")
        receipt_entries = {entry.name for entry in receipt.iterdir()}
        if not receipt_entries.issubset({"intent.json", "outcome.json"}) or "intent.json" not in receipt_entries:
            raise CutoverAttestationError("release activation receipt contents are invalid")
        if "outcome.json" not in receipt_entries:
            raise CutoverAttestationError("release activation history contains an unresolved intent")
        outcome, _ = read_json(receipt / "outcome.json", maximum_bytes=1024 * 1024)
        state = outcome.get("state")
        if state not in ("committed", "aborted"):
            raise CutoverAttestationError("release activation outcome is invalid")
        results.append({"activationReceiptId": receipt.name, "state": state})
    return results


def journal_outcomes_fd(
    root_fd: int,
    entries: set[str],
    *,
    require_initial: bool = False,
    expected_owner_uid: int | None = None,
) -> list[dict[str, str]]:
    journal_candidates = [name for name in entries if name.casefold() == JOURNAL_NAME.casefold()]
    if not journal_candidates:
        return []
    if journal_candidates != [JOURNAL_NAME]:
        raise CutoverAttestationError("release activation journal has noncanonical casing")
    journal_fd = _open_child_directory(
        root_fd, JOURNAL_NAME, "release activation journal"
    )
    try:
        _validate_owner_control_directory(
            journal_fd,
            "release activation journal",
            expected_owner_uid=expected_owner_uid,
        )
        journal_before = _stable_directory_identity(journal_fd)
        results: list[dict[str, str]] = []
        for receipt_name in directory_entry_names(
            journal_fd, "release activation journal"
        ):
            if SAFE_TOKEN.fullmatch(receipt_name) is None:
                raise CutoverAttestationError("release activation receipt path is unsafe")
            receipt_fd = _open_child_directory(
                journal_fd,
                receipt_name,
                "release activation receipt directory",
            )
            try:
                _validate_owner_control_directory(
                    receipt_fd,
                    "release activation receipt directory",
                    expected_owner_uid=expected_owner_uid,
                )
                receipt_before = _stable_directory_identity(receipt_fd)
                receipt_entries = set(
                    directory_entry_names(
                        receipt_fd, "release activation receipt directory"
                    )
                )
                if (
                    not receipt_entries.issubset({"intent.json", "outcome.json"})
                    or "intent.json" not in receipt_entries
                ):
                    raise CutoverAttestationError(
                        "release activation receipt contents are invalid"
                    )
                if "outcome.json" not in receipt_entries:
                    raise CutoverAttestationError(
                        "release activation history contains an unresolved intent"
                    )
                intent, intent_bytes = read_json_at(
                    receipt_fd,
                    "intent.json",
                    label="release activation intent",
                    maximum_bytes=1024 * 1024,
                    forbid_group_world_write=True,
                    expected_owner_uid=expected_owner_uid,
                )
                validate_activation_intent(
                    intent,
                    receipt_name=receipt_name,
                    require_initial=require_initial,
                )
                outcome, _ = read_json_at(
                    receipt_fd,
                    "outcome.json",
                    label="release activation outcome",
                    maximum_bytes=1024 * 1024,
                    forbid_group_world_write=True,
                    expected_owner_uid=expected_owner_uid,
                )
                require_exact_keys(
                    outcome,
                    {
                        "schemaVersion",
                        "state",
                        "activationReceiptId",
                        "intentSha256",
                        "resolvedAtUtc",
                    },
                    "release activation outcome",
                )
                state_value = outcome.get("state")
                if (
                    outcome.get("schemaVersion") != OUTCOME_SCHEMA
                    or state_value not in ("committed", "aborted")
                    or outcome.get("activationReceiptId") != receipt_name
                ):
                    raise CutoverAttestationError("release activation outcome is invalid")
                require_sha256(
                    outcome.get("intentSha256"),
                    "release activation outcome intentSha256",
                    prefix=True,
                )
                require_utc_timestamp(
                    outcome.get("resolvedAtUtc"),
                    "release activation outcome resolvedAtUtc",
                )
                serialized_intent = (
                    intent_bytes[:-1] if intent_bytes.endswith(b"\n") else intent_bytes
                )
                if outcome.get("intentSha256") != (
                    f"sha256:{digest_bytes(serialized_intent)}"
                ):
                    raise CutoverAttestationError(
                        "release activation outcome is not bound to intent bytes"
                    )
                _verify_child_directory_link(
                    journal_fd,
                    receipt_name,
                    receipt_fd,
                    receipt_before,
                    "release activation receipt directory",
                )
                results.append(
                    {"activationReceiptId": receipt_name, "state": str(state_value)}
                )
            finally:
                os.close(receipt_fd)
        if _stable_directory_identity(journal_fd) != journal_before:
            raise CutoverAttestationError(
                "release activation journal changed during attestation"
            )
        linked = os.stat(JOURNAL_NAME, dir_fd=root_fd, follow_symlinks=False)
        opened = os.fstat(journal_fd)
        if _directory_link_identity(linked) != _directory_link_identity(opened):
            raise CutoverAttestationError("release activation journal was exchanged")
        return results
    finally:
        os.close(journal_fd)


def capture_legacy_snapshot(root: Path, *, allow_aborted_history: bool) -> dict[str, Any]:
    with anchored_directory(root, "release shelf root") as anchored:
        return capture_legacy_snapshot_fd(
            anchored,
            allow_aborted_history=allow_aborted_history,
        )


def capture_legacy_snapshot_fd(
    root: AnchoredDirectory,
    *,
    allow_aborted_history: bool,
) -> dict[str, Any]:
    root_before = _stable_directory_identity(root.fd)
    entries = root_entries_fd(root.fd)
    lock_owner_uid = validate_persistent_promotion_lock_at(
        root.fd, entries, required=False
    )
    ensure_control_name_absent(entries, MARKER_NAME)
    ensure_control_name_absent(entries, POINTER_NAME)
    ensure_control_name_absent(entries, ACTIVE_INTENT_NAME)
    generation_candidates = [name for name in entries if name.casefold() == GENERATIONS_NAME.casefold()]
    if generation_candidates:
        if generation_candidates != [GENERATIONS_NAME]:
            raise CutoverAttestationError("release generations root has noncanonical casing")
        generation_fd = _open_child_directory(
            root.fd, GENERATIONS_NAME, "release generations root"
        )
        try:
            _validate_owner_control_directory(
                generation_fd,
                "release generations root",
                expected_owner_uid=lock_owner_uid,
            )
            generation_before = _stable_directory_identity(generation_fd)
            if directory_entry_names(generation_fd, "release generations root"):
                raise CutoverAttestationError("initial cutover requires no generation footprint")
            _verify_child_directory_link(
                root.fd,
                GENERATIONS_NAME,
                generation_fd,
                generation_before,
                "release generations root",
            )
        finally:
            os.close(generation_fd)
    outcomes = journal_outcomes_fd(
        root.fd,
        entries,
        require_initial=True,
        expected_owner_uid=lock_owner_uid,
    )
    if outcomes and lock_owner_uid is None:
        raise CutoverAttestationError(
            "recovered release activation history lacks its persistent promotion lock"
        )
    if any(item["state"] == "committed" for item in outcomes):
        raise CutoverAttestationError("initial cutover refuses committed activation history")
    if outcomes and not allow_aborted_history:
        raise CutoverAttestationError("initial cutover requires an explicit recovered-abort handoff")
    policy_candidates = [name for name in entries if name.casefold() == POLICY_NAME.casefold()]
    if policy_candidates and policy_candidates != [POLICY_NAME]:
        raise CutoverAttestationError("release writer policy has noncanonical casing")
    writer_policy: dict[str, str] | None = None
    if policy_candidates:
        writer_policy = validate_writer_policy_at(
            root.fd, expected_owner_uid=lock_owner_uid
        )
    inventory = inventory_tree_fd(root.fd, skip_top_level_controls=True)
    inventory_by_path = {str(row["path"]): row for row in inventory}
    if CANONICAL_MANIFEST not in inventory_by_path or COMPATIBILITY_MANIFEST not in inventory_by_path:
        raise CutoverAttestationError("legacy shelf is missing its two release manifests")
    canonical_identity = manifest_identity_at(
        root.fd, CANONICAL_MANIFEST, canonical=True
    )
    compatibility_identity = manifest_identity_at(
        root.fd, COMPATIBILITY_MANIFEST, canonical=False
    )
    if (
        canonical_identity["releaseVersion"]
        != compatibility_identity["releaseVersion"]
        or canonical_identity["channel"] != compatibility_identity["channel"]
        or not legacy_manifest_utc_instants_equal(
            canonical_identity["publishedAt"],
            compatibility_identity["publishedAt"],
        )
    ):
        raise CutoverAttestationError("legacy release manifests expose different identities")
    result = {
        "markerAbsent": True,
        "currentPointerAbsent": True,
        "activeIntentAbsent": True,
        "generationFootprintAbsent": True,
        "priorActivationOutcomes": outcomes,
        "writerPolicy": writer_policy,
        "manifestIdentity": canonical_identity,
        "generationRewrittenMetadataPaths": generation_rewritten_metadata_paths_at(
            root.fd, COMPATIBILITY_MANIFEST
        ),
        "legacyInventory": {
            "algorithm": "sha256-canonical-json-v1",
            "digest": f"sha256:{digest_bytes(canonical_json_bytes(inventory))}",
            "files": inventory,
        },
    }
    _verify_directory_stable(root, root_before, "release shelf root")
    return result


def state_file(state_root: Path, name: str) -> Path:
    return state_root / name


def ensure_state_root_fd(descriptor: int) -> None:
    metadata = os.fstat(descriptor)
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) != 0o700
    ):
        raise CutoverAttestationError("cutover state root is unsafe")


def ensure_state_root(path: Path) -> None:
    with anchored_directory(path, "cutover state root") as anchored:
        ensure_state_root_fd(anchored.fd)


def state_entries_fd(state_root_fd: int) -> set[str]:
    ensure_state_root_fd(state_root_fd)
    names = directory_entry_names(state_root_fd, "cutover state root")
    canonical_by_folded = {name.casefold(): name for name in STATE_NAMES}
    for name in names:
        canonical = canonical_by_folded.get(name.casefold())
        if canonical is None or canonical != name:
            raise CutoverAttestationError(
                f"cutover state contains a noncanonical component: {name}"
            )
        metadata = os.stat(name, dir_fd=state_root_fd, follow_symlinks=False)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_ISLNK(metadata.st_mode)
            or metadata.st_nlink != 1
            or metadata.st_uid != os.getuid()
            or stat.S_IMODE(metadata.st_mode) != 0o600
        ):
            raise CutoverAttestationError(
                f"cutover state component is not an owner-only single-link file: {name}"
            )
    return set(names)


def _render_receipt(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, indent=2, sort_keys=True).encode("utf-8") + b"\n"


def _idempotent_receipts_equal(existing_raw: bytes, candidate_raw: bytes) -> bool:
    existing = strict_semantic_object(existing_raw, label="existing cutover receipt")
    candidate = strict_semantic_object(candidate_raw, label="candidate cutover receipt")
    require_utc_timestamp(
        existing.get("generatedAtUtc"),
        "existing cutover receipt generatedAtUtc",
    )
    require_utc_timestamp(
        candidate.get("generatedAtUtc"),
        "candidate cutover receipt generatedAtUtc",
    )
    existing.pop("generatedAtUtc", None)
    candidate.pop("generatedAtUtc", None)
    return strict_semantic_equal(existing, candidate)


def _link_unnamed_file_noreplace_at(
    source_fd: int,
    target_directory_fd: int,
    target_name: str,
) -> None:
    try:
        linkat = ctypes.CDLL(None, use_errno=True).linkat
    except AttributeError as exc:
        raise CutoverAttestationError(
            "O_TMPFILE no-replace publication is unavailable: linkat is missing"
        ) from exc
    linkat.argtypes = (
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
    )
    linkat.restype = ctypes.c_int
    at_empty_path = 0x1000
    if linkat(
        source_fd,
        b"",
        target_directory_fd,
        os.fsencode(target_name),
        at_empty_path,
    ) == 0:
        return
    first_error = ctypes.get_errno()
    if first_error == errno.EEXIST:
        raise FileExistsError(first_error, os.strerror(first_error), target_name)

    # Unprivileged callers can lack CAP_DAC_READ_SEARCH for AT_EMPTY_PATH.
    # The procfd form keeps the source anonymous and links it only at commit.
    procfd_path = f"/proc/self/fd/{source_fd}".encode("ascii")
    at_fdcwd = -100
    at_symlink_follow = 0x400
    if linkat(
        at_fdcwd,
        procfd_path,
        target_directory_fd,
        os.fsencode(target_name),
        at_symlink_follow,
    ) == 0:
        return
    error_number = ctypes.get_errno()
    if error_number == errno.EEXIST:
        raise FileExistsError(error_number, os.strerror(error_number), target_name)
    raise CutoverAttestationError(
        "O_TMPFILE no-replace publication is unavailable "
        f"(AT_EMPTY_PATH errno={first_error}, procfd errno={error_number})"
    )


def _open_unnamed_file_at(directory_fd: int, label: str) -> int:
    if not hasattr(os, "O_TMPFILE"):
        raise CutoverAttestationError(
            f"O_TMPFILE publication is unavailable for {label}"
        )
    flags = os.O_WRONLY | os.O_TMPFILE | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(".", flags, 0o600, dir_fd=directory_fd)
    except OSError as exc:
        raise CutoverAttestationError(
            f"O_TMPFILE publication is unavailable for {label}: errno={exc.errno}"
        ) from exc
    os.fchmod(descriptor, 0o600)
    return descriptor


def _write_and_publish_unnamed_at(
    directory_fd: int,
    name: str,
    raw: bytes,
    label: str,
) -> None:
    descriptor = _open_unnamed_file_at(directory_fd, label)
    try:
        offset = 0
        while offset < len(raw):
            written = os.write(descriptor, raw[offset:])
            if written <= 0:
                raise CutoverAttestationError(
                    f"short write while publishing {label}"
                )
            offset += written
        os.fsync(descriptor)
        _link_unnamed_file_noreplace_at(descriptor, directory_fd, name)
        os.fsync(directory_fd)
    finally:
        os.close(descriptor)


def atomic_write_new_at(
    state_root: AnchoredDirectory | AnchoredChildDirectory,
    name: str,
    payload: dict[str, Any],
) -> None:
    if name not in STATE_NAMES:
        raise CutoverAttestationError("cutover receipt name is not canonical")
    ensure_state_root_fd(state_root.fd)
    entries = state_entries_fd(state_root.fd)
    raw = _render_receipt(payload)
    if name in entries:
        existing_raw = read_regular_file_at(
            state_root.fd,
            name,
            label=f"cutover state {name}",
            maximum_bytes=MAX_JSON_BYTES,
            owner_only=True,
        )
        if _idempotent_receipts_equal(existing_raw, raw):
            state_entries_fd(state_root.fd)
            state_root.verify_links()
            return
        raise CutoverAttestationError(f"cutover state receipt already exists: {name}")
    try:
        _write_and_publish_unnamed_at(
            state_root.fd,
            name,
            raw,
            f"cutover state {name}",
        )
        state_entries_fd(state_root.fd)
        state_root.verify_links()
    except FileExistsError:
        existing_raw = read_regular_file_at(
            state_root.fd,
            name,
            label=f"cutover state {name}",
            maximum_bytes=MAX_JSON_BYTES,
            owner_only=True,
        )
        if _idempotent_receipts_equal(existing_raw, raw):
            state_entries_fd(state_root.fd)
            state_root.verify_links()
            return
        raise CutoverAttestationError(f"cutover state receipt already exists: {name}")


def atomic_write_new(path: Path, payload: dict[str, Any]) -> None:
    with anchored_directory(path.parent, "cutover state root") as state_root:
        atomic_write_new_at(state_root, path.name, payload)


def load_state(path: Path, contract: str) -> tuple[dict[str, Any], bytes]:
    payload, raw = read_json(path)
    if payload.get("contractName") != contract or payload.get("status") != "pass":
        raise CutoverAttestationError(f"invalid cutover state receipt: {path.name}")
    return payload, raw


def load_state_at(
    state_root: AnchoredDirectory,
    name: str,
    contract: str,
) -> tuple[dict[str, Any], bytes]:
    payload, raw = read_json_at(
        state_root.fd,
        name,
        label=f"cutover state {name}",
        owner_only=True,
    )
    if payload.get("contractName") != contract or payload.get("status") != "pass":
        raise CutoverAttestationError(f"invalid cutover state receipt: {name}")
    return payload, raw


def directory_object_identity(descriptor: int) -> dict[str, int]:
    metadata = os.fstat(descriptor)
    if not stat.S_ISDIR(metadata.st_mode):
        raise CutoverAttestationError("identity target is not a directory")
    return {"device": metadata.st_dev, "inode": metadata.st_ino}


def validate_directory_object_identity(
    value: object,
    descriptor: int,
    label: str,
) -> None:
    if not isinstance(value, dict) or set(value) != {"device", "inode"}:
        raise CutoverAttestationError(f"{label} identity is malformed")
    expected = directory_object_identity(descriptor)
    if (
        type(value.get("device")) is not int
        or type(value.get("inode")) is not int
        or value != expected
    ):
        raise CutoverAttestationError(f"{label} directory identity changed")


def validate_prestate_receipt(
    payload: dict[str, Any],
    *,
    state_root: AnchoredDirectory,
    shelf_root: AnchoredDirectory,
    source_head: str | None = None,
) -> None:
    require_exact_keys(
        payload,
        {
            "contractName",
            "status",
            "generatedAtUtc",
            "sourceHead",
            "shelfRoot",
            "shelfRootIdentity",
            "stateRootIdentity",
            "shelfSnapshot",
        },
        "cutover prestate receipt",
    )
    if payload.get("contractName") != PRESTATE_CONTRACT or payload.get("status") != "pass":
        raise CutoverAttestationError("cutover prestate contract is invalid")
    require_utc_timestamp(payload.get("generatedAtUtc"), "cutover prestate generatedAtUtc")
    receipt_head = require_string(payload.get("sourceHead"), "cutover prestate sourceHead")
    if COMMIT.fullmatch(receipt_head) is None or (
        source_head is not None and receipt_head != source_head
    ):
        raise CutoverAttestationError("cutover prestate source HEAD changed")
    if payload.get("shelfRoot") != str(shelf_root.path):
        raise CutoverAttestationError("cutover prestate shelf root changed")
    validate_directory_object_identity(
        payload.get("shelfRootIdentity"), shelf_root.fd, "release shelf root"
    )
    validate_directory_object_identity(
        payload.get("stateRootIdentity"), state_root.fd, "cutover state root"
    )
    if not isinstance(payload.get("shelfSnapshot"), dict):
        raise CutoverAttestationError("cutover prestate shelf snapshot is malformed")


def validate_start_receipt(
    payload: dict[str, Any],
    *,
    prestate_raw: bytes,
) -> None:
    require_exact_keys(
        payload,
        {
            "contractName",
            "status",
            "generatedAtUtc",
            "phase",
            "prestateSha256",
        },
        "cutover start receipt",
    )
    if (
        payload.get("contractName") != START_CONTRACT
        or payload.get("status") != "pass"
        or payload.get("phase") != "candidate_start_requested"
        or payload.get("prestateSha256")
        != f"sha256:{digest_bytes(prestate_raw)}"
    ):
        raise CutoverAttestationError("candidate start receipt is not bound to prestate")
    require_utc_timestamp(payload.get("generatedAtUtc"), "cutover start generatedAtUtc")


def validate_poststate_receipt(
    payload: dict[str, Any],
    *,
    prestate_raw: bytes,
    start_raw: bytes,
) -> None:
    require_exact_keys(
        payload,
        {
            "contractName",
            "status",
            "generatedAtUtc",
            "prestateSha256",
            "startRequestSha256",
            "classification",
            "markerSha256",
            "writerPolicy",
            "currentPointer",
            "activationCandidateSha256",
            "shelfClosureDigest",
            "legacyInventoryDigest",
            "legacyPayloadPreserved",
            "activeIntentAbsent",
        },
        "cutover poststate receipt",
    )
    if (
        payload.get("contractName") != POSTSTATE_CONTRACT
        or payload.get("status") != "pass"
        or payload.get("classification") != "committed"
        or payload.get("prestateSha256") != f"sha256:{digest_bytes(prestate_raw)}"
        or payload.get("startRequestSha256") != f"sha256:{digest_bytes(start_raw)}"
    ):
        raise CutoverAttestationError("cutover poststate receipt bindings are invalid")
    require_utc_timestamp(payload.get("generatedAtUtc"), "cutover poststate generatedAtUtc")
    require_sha256(payload.get("markerSha256"), "cutover markerSha256", prefix=True)
    require_sha256(
        payload.get("activationCandidateSha256"),
        "cutover activationCandidateSha256",
        prefix=True,
    )
    require_sha256(
        payload.get("shelfClosureDigest"),
        "cutover shelfClosureDigest",
        prefix=True,
    )
    require_sha256(
        payload.get("legacyInventoryDigest"),
        "cutover legacyInventoryDigest",
        prefix=True,
    )
    require_exact_bool(
        payload.get("legacyPayloadPreserved"),
        "cutover legacyPayloadPreserved",
        True,
    )
    require_exact_bool(
        payload.get("activeIntentAbsent"), "cutover activeIntentAbsent", True
    )
    if payload.get("writerPolicy") != {
        "schemaVersion": WRITER_POLICY_SCHEMA,
        "mode": WRITER_POLICY_MODE,
    }:
        raise CutoverAttestationError("cutover poststate writer policy is invalid")
    current = payload.get("currentPointer")
    if not isinstance(current, dict):
        raise CutoverAttestationError("cutover poststate current pointer is malformed")
    require_exact_keys(
        current,
        {
            "sha256",
            "generationId",
            "activationReceiptId",
            "inventoryDigest",
            "canonicalManifestPath",
            "canonicalManifestSha256",
            "compatibilityManifestPath",
            "compatibilityManifestSha256",
        },
        "cutover poststate current pointer",
    )
    for field in (
        "sha256",
        "inventoryDigest",
        "canonicalManifestSha256",
        "compatibilityManifestSha256",
    ):
        require_sha256(current.get(field), f"cutover current pointer {field}", prefix=True)
    for field in ("generationId", "activationReceiptId"):
        value = require_string(current.get(field), f"cutover current pointer {field}")
        if SAFE_TOKEN.fullmatch(value) is None:
            raise CutoverAttestationError(f"cutover current pointer {field} is unsafe")
    for field in ("canonicalManifestPath", "compatibilityManifestPath"):
        require_string(current.get(field), f"cutover current pointer {field}")


def validate_aborted_receipt(
    payload: dict[str, Any],
    *,
    prestate: dict[str, Any],
    prestate_raw: bytes,
    start_raw: bytes,
) -> None:
    require_exact_keys(
        payload,
        {
            "contractName",
            "status",
            "generatedAtUtc",
            "classification",
            "prestateSha256",
            "startRequestSha256",
            "legacyInventoryDigest",
            "abortedShelfClosureDigest",
            "legacyShelfUnchanged",
            "activeIntentAbsent",
        },
        "cutover aborted receipt",
    )
    if (
        payload.get("contractName") != ABORTED_CONTRACT
        or payload.get("status") != "pass"
        or payload.get("classification") != "aborted"
        or payload.get("prestateSha256") != f"sha256:{digest_bytes(prestate_raw)}"
        or payload.get("startRequestSha256") != f"sha256:{digest_bytes(start_raw)}"
    ):
        raise CutoverAttestationError("cutover aborted receipt bindings are invalid")
    require_utc_timestamp(payload.get("generatedAtUtc"), "cutover aborted generatedAtUtc")
    require_sha256(
        payload.get("legacyInventoryDigest"),
        "cutover aborted legacyInventoryDigest",
        prefix=True,
    )
    require_sha256(
        payload.get("abortedShelfClosureDigest"),
        "cutover aborted shelf closure digest",
        prefix=True,
    )
    expected_digest = prestate.get("shelfSnapshot", {}).get(
        "legacyInventory", {}
    ).get("digest")
    if payload.get("legacyInventoryDigest") != expected_digest:
        raise CutoverAttestationError(
            "cutover aborted receipt is not bound to prestate inventory"
        )
    require_exact_bool(
        payload.get("legacyShelfUnchanged"), "cutover legacyShelfUnchanged", True
    )
    require_exact_bool(
        payload.get("activeIntentAbsent"), "cutover activeIntentAbsent", True
    )


def validate_aborted_shelf_snapshot(
    current: dict[str, Any],
    expected: dict[str, Any],
) -> None:
    for field in (
        "markerAbsent",
        "currentPointerAbsent",
        "activeIntentAbsent",
        "generationFootprintAbsent",
        "manifestIdentity",
        "generationRewrittenMetadataPaths",
        "legacyInventory",
    ):
        if not strict_python_equal(current.get(field), expected.get(field)):
            raise CutoverAttestationError(
                "aborted cutover changed the exact legacy shelf closure"
            )
    expected_policy = expected.get("writerPolicy")
    current_policy = current.get("writerPolicy")
    canonical_policy = {
        "schemaVersion": WRITER_POLICY_SCHEMA,
        "mode": WRITER_POLICY_MODE,
    }
    if current_policy not in (expected_policy, canonical_policy):
        raise CutoverAttestationError(
            "aborted cutover left a noncanonical writer policy"
        )
    outcomes = current.get("priorActivationOutcomes")
    if not isinstance(outcomes, list) or len(outcomes) > 1 or any(
        not isinstance(item, dict)
        or set(item) != {"activationReceiptId", "state"}
        or item.get("state") != "aborted"
        for item in outcomes
    ):
        raise CutoverAttestationError(
            "aborted cutover has noncanonical activation history"
        )


def validate_complete_receipt(
    payload: dict[str, Any],
    *,
    poststate: dict[str, Any],
    poststate_raw: bytes,
) -> None:
    require_exact_keys(
        payload,
        {
            "contractName",
            "status",
            "generatedAtUtc",
            "poststateSha256",
            "composeAttestationSha256",
            "readinessAttestationSha256",
            "postdeployAttestationSha256",
            "activeRuntimeAuthoritySha256",
            "evidenceDirectory",
            "releaseShelfPosture",
            "candidate",
            "generationId",
            "activationReceiptId",
        },
        "cutover complete receipt",
    )
    if (
        payload.get("contractName") != COMPLETE_CONTRACT
        or payload.get("status") != "pass"
        or payload.get("poststateSha256")
        != f"sha256:{digest_bytes(poststate_raw)}"
    ):
        raise CutoverAttestationError("cutover complete receipt binding is invalid")
    require_utc_timestamp(payload.get("generatedAtUtc"), "cutover complete generatedAtUtc")
    for field in (
        "composeAttestationSha256",
        "readinessAttestationSha256",
        "postdeployAttestationSha256",
        "activeRuntimeAuthoritySha256",
    ):
        require_sha256(payload.get(field), f"cutover complete {field}", prefix=True)
    evidence_directory = payload.get("evidenceDirectory")
    if not isinstance(evidence_directory, dict):
        raise CutoverAttestationError(
            "cutover complete evidence directory binding is malformed"
        )
    require_exact_keys(
        evidence_directory,
        {"path", "device", "inode"},
        "cutover complete evidence directory",
    )
    evidence_path = require_string(
        evidence_directory.get("path"),
        "cutover complete evidence directory path",
    )
    _normalized_absolute_path(evidence_path, "cutover complete evidence directory path")
    require_exact_int(
        evidence_directory.get("device"),
        "cutover complete evidence directory device",
    )
    require_exact_int(
        evidence_directory.get("inode"),
        "cutover complete evidence directory inode",
    )
    expected_posture = {
        "CHUMMER_RELEASE_SHELF_LAYOUT_V1_REQUIRED": "true",
        "CHUMMER_RELEASE_SHELF_INITIAL_MIGRATION_ALLOWED": "false",
    }
    if payload.get("releaseShelfPosture") != expected_posture:
        raise CutoverAttestationError("cutover complete steady posture is invalid")
    current = poststate.get("currentPointer")
    if not isinstance(current, dict):
        raise CutoverAttestationError("cutover poststate current pointer is malformed")
    if (
        payload.get("generationId") != current.get("generationId")
        or payload.get("activationReceiptId") != current.get("activationReceiptId")
    ):
        raise CutoverAttestationError("cutover complete generation binding is invalid")
    candidate = payload.get("candidate")
    if not isinstance(candidate, dict) or set(candidate) != {
        "containerId",
        "containerName",
        "imageId",
    }:
        raise CutoverAttestationError("cutover complete candidate identity is malformed")
    if (
        not isinstance(candidate.get("containerId"), str)
        or CONTAINER_ID.fullmatch(candidate["containerId"]) is None
        or not isinstance(candidate.get("containerName"), str)
        or SAFE_TOKEN.fullmatch(candidate["containerName"]) is None
        or not isinstance(candidate.get("imageId"), str)
        or IMAGE_ID.fullmatch(candidate["imageId"]) is None
    ):
        raise CutoverAttestationError("cutover complete candidate identity is invalid")


def _require_unprefixed_sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or SHA256.fullmatch(value) is None:
        raise CutoverAttestationError(f"{label} is not a lowercase SHA-256")
    return value


def validate_compose_attestation(payload: dict[str, Any]) -> None:
    require_exact_keys(
        payload,
        {
            "contractName",
            "status",
            "operation",
            "projectName",
            "portalImage",
            "toolImage",
            "sourceRoot",
            "buildContext",
            "overlayRoot",
            "overlayReadOnly",
            "publishedPort",
            "proxyGates",
            "retiredProxyKeysAbsent",
            "releaseShelfPosture",
            "runtimePolicyChecks",
            "mountCounts",
            "builds",
        },
        "steady Compose attestation",
    )
    expected_posture = {
        "CHUMMER_RELEASE_SHELF_LAYOUT_V1_REQUIRED": "true",
        "CHUMMER_RELEASE_SHELF_INITIAL_MIGRATION_ALLOWED": "false",
    }
    if (
        payload.get("contractName") != COMPOSE_CONTRACT
        or payload.get("status") != "pass"
        or payload.get("operation") != "deploy"
        or payload.get("projectName") != "chummer6-hub"
        or payload.get("portalImage") != "chummer-run-api:local"
        or payload.get("toolImage") != "chummer-install-linking-postgres-tool:local"
        or payload.get("releaseShelfPosture") != expected_posture
        or payload.get("proxyGates")
        != {
            "CHUMMER_PUBLIC_PLAY_PROXY_ENABLED": "false",
            "CHUMMER_PUBLIC_PLAY_LIVE_SESSION_PROXY_ENABLED": "false",
        }
    ):
        raise CutoverAttestationError("steady Compose attestation is not canonical")
    require_exact_bool(payload.get("overlayReadOnly"), "Compose overlayReadOnly", True)
    require_exact_bool(
        payload.get("retiredProxyKeysAbsent"),
        "Compose retiredProxyKeysAbsent",
        True,
    )
    require_exact_int(payload.get("publishedPort"), "Compose publishedPort", 8091)
    for field in ("sourceRoot", "buildContext", "overlayRoot"):
        value = require_string(payload.get(field), f"Compose {field}")
        _normalized_absolute_path(value, f"Compose {field}")
    expected_checks = [
        "closed-service-fields",
        "identity",
        "security",
        "resource-limits",
        "command-entrypoint",
        "mounts",
        "ports-health",
        "dependency-network",
        "profiles-tmpfs-restart",
        "critical-environment",
        "release-shelf-operation-posture",
    ]
    if payload.get("runtimePolicyChecks") != expected_checks:
        raise CutoverAttestationError("steady Compose policy checks are not exact")
    expected_mounts = {
        "chummer-portal-volume-init": 5,
        "chummer-portal": 13,
        "chummer-install-linking-postgres-admin": 1,
        "chummer-install-linking-postgres-import": 4,
    }
    mounts = payload.get("mountCounts")
    if not isinstance(mounts, dict) or set(mounts) != set(expected_mounts):
        raise CutoverAttestationError("steady Compose mount counts are malformed")
    for service, count in expected_mounts.items():
        require_exact_int(mounts.get(service), f"Compose {service} mount count", count)
    builds = payload.get("builds")
    expected_services = {
        "chummer-portal": "",
        "chummer-install-linking-postgres-admin": "install-linking-postgres-tool-final",
        "chummer-install-linking-postgres-import": "install-linking-postgres-tool-final",
    }
    if not isinstance(builds, dict) or set(builds) != set(expected_services):
        raise CutoverAttestationError("steady Compose build receipts are malformed")
    source_root = payload["sourceRoot"]
    build_context = payload["buildContext"]
    reference_contexts: object = None
    for service, expected_target in expected_services.items():
        build = builds.get(service)
        if not isinstance(build, dict):
            raise CutoverAttestationError(f"Compose {service} build receipt is malformed")
        require_exact_keys(
            build,
            {
                "context",
                "dockerfile",
                "additionalContexts",
                "target",
                "runtimeIdentityConsistent",
            },
            f"Compose {service} build receipt",
        )
        contexts = build.get("additionalContexts")
        if not isinstance(contexts, dict) or set(contexts) != {
            "run-services-source",
            "fleet-media-factory-contracts",
            "design-product",
        }:
            raise CutoverAttestationError(
                f"Compose {service} additional contexts are malformed"
            )
        if (
            build.get("context") != build_context
            or build.get("dockerfile") != f"{source_root}/Chummer.Run.Api/Dockerfile"
            or contexts.get("run-services-source") != source_root
            or build.get("target") != expected_target
        ):
            raise CutoverAttestationError(f"Compose {service} build binding changed")
        for context_path in contexts.values():
            _normalized_absolute_path(
                require_string(context_path, f"Compose {service} build context"),
                f"Compose {service} build context",
            )
        require_exact_bool(
            build.get("runtimeIdentityConsistent"),
            f"Compose {service} runtime identity",
            True,
        )
        if reference_contexts is None:
            reference_contexts = contexts
        elif not strict_python_equal(reference_contexts, contexts):
            raise CutoverAttestationError("Compose build additional contexts disagree")


def validate_readiness_attestation(payload: dict[str, Any]) -> dict[str, str]:
    require_exact_keys(
        payload,
        {
            "contractName",
            "status",
            "generatedAtUtc",
            "candidateContainerId",
            "candidateContainerName",
            "candidateImageId",
            "endpoint",
            "hostHeader",
            "httpStatus",
            "responseSha256",
            "running",
            "health",
        },
        "publication readiness attestation",
    )
    if (
        payload.get("contractName") != READINESS_CONTRACT
        or payload.get("status") != "pass"
        or payload.get("endpoint")
        != "http://127.0.0.1:8080/api/ready/publication"
        or payload.get("hostHeader") != "chummer.run"
        or payload.get("health") != "healthy"
    ):
        raise CutoverAttestationError("publication readiness attestation is not canonical")
    require_utc_timestamp(
        payload.get("generatedAtUtc"), "publication readiness generatedAtUtc"
    )
    require_exact_int(payload.get("httpStatus"), "publication readiness HTTP status", 200)
    require_exact_bool(payload.get("running"), "publication readiness running", True)
    require_sha256(
        payload.get("responseSha256"),
        "publication readiness responseSha256",
        prefix=True,
    )
    container_id = require_string(
        payload.get("candidateContainerId"), "publication readiness container ID"
    )
    container_name = require_string(
        payload.get("candidateContainerName"), "publication readiness container name"
    )
    image_id = require_string(
        payload.get("candidateImageId"), "publication readiness image ID"
    )
    if (
        CONTAINER_ID.fullmatch(container_id) is None
        or SAFE_TOKEN.fullmatch(container_name) is None
        or IMAGE_ID.fullmatch(image_id) is None
    ):
        raise CutoverAttestationError("publication readiness candidate identity is invalid")
    return {
        "containerId": container_id,
        "containerName": container_name,
        "imageId": image_id,
    }


def _require_child_pass(
    children: object,
    name: str,
    contract: str | None = None,
) -> dict[str, Any]:
    if not isinstance(children, dict) or not isinstance(children.get(name), dict):
        raise CutoverAttestationError(f"postdeploy child receipt is missing: {name}")
    child = children[name]
    if child.get("status") != "pass":
        raise CutoverAttestationError(f"postdeploy child receipt is not pass: {name}")
    if contract is not None and child.get("contractName") != contract:
        raise CutoverAttestationError(
            f"postdeploy child receipt contract is invalid: {name}"
        )
    failures = child.get("failures")
    if failures is not None and failures != []:
        raise CutoverAttestationError(f"postdeploy child receipt has failures: {name}")
    return child


def validate_postdeploy_attestation(payload: dict[str, Any]) -> None:
    required_fields = {
        "contractName",
        "status",
        "generatedAtUtc",
        "failures",
        "skipPreflight",
        "skipReleaseVersionMatch",
        "strictPreflight",
        "strictInvocation",
        "strictNoAllowanceInvocation",
        "projectionPurpose",
        "projectionStatus",
        "projectionStage",
        "codeDeploymentAuthority",
        "releaseUploadAuthority",
        "releaseReady",
        "codeDeployReviewRequiredAuthoritySatisfied",
        "expectedFullDeploymentDigestSha256",
        "expectedPwaAssetInventorySha256",
        "pwaAssetInventoryAnchorMatches",
        "expectedPwaFullDeploymentDigestSha256",
        "pwaFullDeploymentDigestSha256",
        "pwaFullDeploymentDigestMatchesExpected",
        "downloadsStatusBrowserStatus",
        "downloadsStatusBrowserExitCode",
        "downloadsStatusBrowserArtifactContract",
        "mobilePwaViewportStatus",
        "mobilePwaViewportExitCode",
        "mobilePwaViewportArtifactContract",
        "mobilePwaViewportArtifactCurrentContractSatisfied",
        "mobilePwaViewportArtifactContractFailures",
        "frontdoorNavigationStatus",
        "frontdoorNavigationExitCode",
        "frontdoorNavigationMobileArtifactContract",
        "frontdoorNavigationLedgerArtifactContract",
        "frontdoorNavigationAnchorArtifactContract",
        "frontdoorNavigationMobileArtifactInstallContractSatisfied",
        "frontdoorNavigationLedgerArtifactCurrentContractSatisfied",
        "frontdoorNavigationAnchorArtifactCurrentContractSatisfied",
        "frontdoorNavigationProofClosureStatus",
        "frontdoorNavigationProofClosureSha256",
        "onlineLaunchStatus",
        "onlineLaunchContract",
        "onlineLaunchHttpStatus",
        "onlineLaunchHasBlazorMarker",
        "roleAliasRouteStatus",
        "roleAliasRouteContract",
        "childReceipts",
    }
    missing = required_fields - set(payload)
    unexpected = set(payload) - POSTDEPLOY_ALLOWED_FIELDS
    if missing or unexpected:
        raise CutoverAttestationError(
            "postdeploy attestation has missing or unexpected final-gate fields"
        )
    if (
        payload.get("contractName") != POSTDEPLOY_CONTRACT
        or payload.get("status") != "pass"
        or payload.get("failures") != []
        or payload.get("projectionPurpose") != "code-deploy"
        or payload.get("projectionStatus") != "review_required"
        or payload.get("projectionStage") != "code_deploy_review_required"
    ):
        raise CutoverAttestationError("postdeploy attestation is not a passing code deploy")
    require_utc_timestamp(payload.get("generatedAtUtc"), "postdeploy generatedAtUtc")
    for field, expected in (
        ("skipPreflight", False),
        ("skipReleaseVersionMatch", False),
        ("strictPreflight", True),
        ("strictInvocation", True),
        ("strictNoAllowanceInvocation", True),
        ("codeDeploymentAuthority", True),
        ("releaseUploadAuthority", False),
        ("releaseReady", False),
        ("codeDeployReviewRequiredAuthoritySatisfied", True),
        ("pwaAssetInventoryAnchorMatches", True),
        ("pwaFullDeploymentDigestMatchesExpected", True),
        ("mobilePwaViewportArtifactCurrentContractSatisfied", True),
        ("frontdoorNavigationMobileArtifactInstallContractSatisfied", True),
        ("frontdoorNavigationLedgerArtifactCurrentContractSatisfied", True),
        ("frontdoorNavigationAnchorArtifactCurrentContractSatisfied", True),
    ):
        require_exact_bool(payload.get(field), f"postdeploy {field}", expected)
    full_digest = _require_unprefixed_sha256(
        payload.get("expectedFullDeploymentDigestSha256"),
        "postdeploy full deployment digest",
    )
    if (
        payload.get("expectedPwaFullDeploymentDigestSha256") != full_digest
        or payload.get("pwaFullDeploymentDigestSha256") != full_digest
    ):
        raise CutoverAttestationError("postdeploy PWA deployment digest binding changed")
    _require_unprefixed_sha256(
        payload.get("expectedPwaAssetInventorySha256"),
        "postdeploy PWA inventory digest",
    )
    if payload.get("mobilePwaViewportArtifactContractFailures") != []:
        raise CutoverAttestationError("postdeploy mobile PWA contract has failures")
    expected_browser_values = {
        "downloadsStatusBrowserStatus": "pass",
        "downloadsStatusBrowserArtifactContract": "chummer.downloads_status_e2e.v1",
        "mobilePwaViewportStatus": "pass",
        "mobilePwaViewportArtifactContract": "chummer.mobile_pwa_viewport_smoke.v1",
        "frontdoorNavigationStatus": "pass",
        "frontdoorNavigationMobileArtifactContract": "chummer.frontdoor_mobile_install_boundary.v2",
        "frontdoorNavigationLedgerArtifactContract": "chummer.black_ledger_globe_frontdoor.v1",
        "frontdoorNavigationAnchorArtifactContract": "chummer.frontdoor_mobile_anchor_redirect.v2",
        "frontdoorNavigationProofClosureStatus": "pass",
    }
    for field, expected in expected_browser_values.items():
        if payload.get(field) != expected:
            raise CutoverAttestationError(f"postdeploy {field} is not canonical")
    for field in (
        "downloadsStatusBrowserExitCode",
        "mobilePwaViewportExitCode",
        "frontdoorNavigationExitCode",
    ):
        require_exact_int(payload.get(field), f"postdeploy {field}", 0)
    _require_unprefixed_sha256(
        payload.get("frontdoorNavigationProofClosureSha256"),
        "postdeploy frontdoor proof closure digest",
    )
    children = payload.get("childReceipts")
    expected_child_names = {
        "preflight",
        "downloads",
        "pwaStatic",
        "mobileLedger",
        "readyMobileHandoff",
        "participateIframeShell",
        "onlineLaunch",
        "downloadsStatusBrowser",
        "mobilePwaViewport",
        "frontdoorNavigation",
    }
    if not isinstance(children, dict) or set(children) != expected_child_names:
        raise CutoverAttestationError("postdeploy child receipt closure is not exact")
    expected_core_contracts = {
        "preflight": "chummer.public_edge_deploy_preflight.v1",
        "downloads": "chummer.downloads_version_marker.v1",
        "pwaStatic": "chummer.public_pwa_static_assets.v1",
        "mobileLedger": "chummer.mobile_pwa_ledger_boundary.v1",
        "readyMobileHandoff": "chummer.ready_mobile_handoff_contract.v1",
        "participateIframeShell": "chummer.participate_iframe_shell.v1",
    }
    for name, contract in expected_core_contracts.items():
        _require_child_pass(children, name, contract)
    _require_child_pass(
        children, "onlineLaunch", "chummer.online_character_roster_launch.v1"
    )
    if (
        payload.get("onlineLaunchStatus") != "pass"
        or payload.get("onlineLaunchContract")
        != "chummer.online_character_roster_launch.v1"
        or type(payload.get("onlineLaunchHttpStatus")) is not int
        or payload.get("onlineLaunchHttpStatus") != 200
        or payload.get("onlineLaunchHasBlazorMarker") is not True
        or payload.get("roleAliasRouteStatus") != "pass"
        or payload.get("roleAliasRouteContract")
        != "chummer.public_role_alias_routes.v1"
    ):
        raise CutoverAttestationError(
            "postdeploy online launch or role-alias proof is not canonical"
        )
    browser_contracts = {
        "downloadsStatusBrowser": "chummer.downloads_status_e2e.v1",
        "mobilePwaViewport": "chummer.mobile_pwa_viewport_smoke.v1",
    }
    for name, artifact_contract in browser_contracts.items():
        child = _require_child_pass(children, name)
        require_exact_int(child.get("exitCode"), f"postdeploy {name} exitCode", 0)
        artifact = child.get("artifact")
        if (
            not isinstance(artifact, dict)
            or artifact.get("contractName") != artifact_contract
            or artifact.get("status") != "pass"
        ):
            raise CutoverAttestationError(
                f"postdeploy {name} artifact is not canonical"
            )
    frontdoor = _require_child_pass(children, "frontdoorNavigation")
    require_exact_int(
        frontdoor.get("exitCode"), "postdeploy frontdoorNavigation exitCode", 0
    )
    for artifact_name, contract in {
        "mobileArtifact": "chummer.frontdoor_mobile_install_boundary.v2",
        "ledgerArtifact": "chummer.black_ledger_globe_frontdoor.v1",
        "anchorArtifact": "chummer.frontdoor_mobile_anchor_redirect.v2",
    }.items():
        artifact = frontdoor.get(artifact_name)
        if (
            not isinstance(artifact, dict)
            or artifact.get("contractName") != contract
            or artifact.get("status") != "pass"
        ):
            raise CutoverAttestationError(
                f"postdeploy frontdoor {artifact_name} is not canonical"
            )
    for field in (
        "mobileArtifactPrivacyContractSatisfied",
        "ledgerArtifactCurrentContractSatisfied",
        "anchorArtifactCurrentContractSatisfied",
    ):
        require_exact_bool(
            frontdoor.get(field), f"postdeploy frontdoor {field}", True
        )
    if (
        frontdoor.get("proofClosureStatus") != "pass"
        or frontdoor.get("proofClosureSha256")
        != payload.get("frontdoorNavigationProofClosureSha256")
    ):
        raise CutoverAttestationError(
            "postdeploy frontdoor proof closure is not generation-bound"
        )


def validate_active_runtime_authority(
    payload: dict[str, Any],
) -> dict[str, str]:
    require_exact_keys(
        payload,
        {"contractName", "status", "generatedAtUtc", "portal"},
        "active runtime authority",
    )
    if (
        payload.get("contractName") != RUNTIME_AUTHORITY_CONTRACT
        or payload.get("status") != "pass"
    ):
        raise CutoverAttestationError("active runtime authority is not pass")
    require_utc_timestamp(
        payload.get("generatedAtUtc"), "active runtime authority generatedAtUtc"
    )
    portal = payload.get("portal")
    if not isinstance(portal, dict):
        raise CutoverAttestationError("active runtime authority portal is malformed")
    require_exact_keys(
        portal,
        {
            "existed",
            "containerId",
            "containerName",
            "imageId",
            "wasRunning",
            "proofAuthorityMountSha256",
            "proofPublicMountSha256",
        },
        "active runtime authority portal",
    )
    require_exact_bool(portal.get("existed"), "active runtime portal existed", True)
    require_exact_bool(
        portal.get("wasRunning"), "active runtime portal wasRunning", True
    )
    container_id = require_string(portal.get("containerId"), "active runtime container ID")
    container_name = require_string(
        portal.get("containerName"), "active runtime container name"
    )
    image_id = require_string(portal.get("imageId"), "active runtime image ID")
    if (
        CONTAINER_ID.fullmatch(container_id) is None
        or SAFE_TOKEN.fullmatch(container_name) is None
        or IMAGE_ID.fullmatch(image_id) is None
    ):
        raise CutoverAttestationError("active runtime portal identity is invalid")
    proof_authority = _require_unprefixed_sha256(
        portal.get("proofAuthorityMountSha256"),
        "active runtime authority proof digest",
    )
    proof_public = _require_unprefixed_sha256(
        portal.get("proofPublicMountSha256"),
        "active runtime public proof digest",
    )
    if proof_authority != proof_public:
        raise CutoverAttestationError("active runtime proof mount digests disagree")
    return {
        "containerId": container_id,
        "containerName": container_name,
        "imageId": image_id,
    }


def _validate_owner_control_directory(
    descriptor: int,
    label: str,
    *,
    expected_owner_uid: int | None = None,
) -> None:
    metadata = os.fstat(descriptor)
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or (
            expected_owner_uid is not None
            and metadata.st_uid != expected_owner_uid
        )
        or stat.S_IMODE(metadata.st_mode) & 0o022
    ):
        raise CutoverAttestationError(f"{label} is not an owner-controlled directory")


def validate_installed_bootstrap_fd(shelf: AnchoredDirectory) -> None:
    """Validate durable layout controls without replaying the initial generation."""

    root_before = _stable_directory_identity(shelf.fd)
    entries = root_entries_fd(shelf.fd)
    for name in (
        MARKER_NAME,
        POINTER_NAME,
        POLICY_NAME,
        JOURNAL_NAME,
        GENERATIONS_NAME,
        LOCK_NAME,
    ):
        matches = sorted(
            candidate for candidate in entries if candidate.casefold() == name.casefold()
        )
        if matches != [name]:
            raise CutoverAttestationError(
                f"installed release shelf lacks canonical {name}"
            )
    ensure_control_name_absent(entries, ACTIVE_INTENT_NAME)
    control_owner_uid = validate_persistent_promotion_lock_at(
        shelf.fd, entries, required=True
    )
    if control_owner_uid is None:
        raise CutoverAttestationError(
            "installed release shelf control owner is unavailable"
        )
    marker = read_regular_file_at(
        shelf.fd,
        MARKER_NAME,
        label="release shelf layout marker",
        maximum_bytes=128,
        forbid_group_world_write=True,
        expected_owner_uid=control_owner_uid,
    )
    if marker != MARKER_BYTES:
        raise CutoverAttestationError(
            "release shelf layout marker bytes are not canonical"
        )
    validate_writer_policy_at(
        shelf.fd, expected_owner_uid=control_owner_uid
    )
    pointer, _ = read_json_at(
        shelf.fd,
        POINTER_NAME,
        label="release shelf current pointer",
        maximum_bytes=64 * 1024,
        forbid_group_world_write=True,
        expected_owner_uid=control_owner_uid,
    )
    require_exact_keys(
        pointer,
        {
            "schemaVersion",
            "generationId",
            "releaseVersion",
            "channel",
            "publishedAt",
            "manifests",
            "inventoryDigest",
            "activatedAt",
            "activationReceiptId",
        },
        "release shelf current pointer",
    )
    generation_id = require_string(
        pointer.get("generationId"), "current generation id"
    )
    receipt_id = require_string(
        pointer.get("activationReceiptId"), "current activation receipt id"
    )
    if (
        pointer.get("schemaVersion") != POINTER_SCHEMA
        or SAFE_TOKEN.fullmatch(generation_id) is None
        or SAFE_TOKEN.fullmatch(receipt_id) is None
    ):
        raise CutoverAttestationError("release shelf current pointer is invalid")
    require_string(pointer.get("releaseVersion"), "current releaseVersion")
    require_string(pointer.get("channel"), "current channel")
    require_utc_timestamp(pointer.get("publishedAt"), "current publishedAt")
    require_utc_timestamp(pointer.get("activatedAt"), "current activatedAt")
    require_sha256(pointer.get("inventoryDigest"), "current inventoryDigest", prefix=True)
    _validate_manifest_binding(
        pointer, generation_id, "canonical", CANONICAL_MANIFEST
    )
    _validate_manifest_binding(
        pointer, generation_id, "compatibility", COMPATIBILITY_MANIFEST
    )

    generations_fd = _open_child_directory(
        shelf.fd, GENERATIONS_NAME, "release generations root"
    )
    try:
        _validate_owner_control_directory(
            generations_fd,
            "release generations root",
            expected_owner_uid=control_owner_uid,
        )
        generation_names = directory_entry_names(
            generations_fd, "release generations root"
        )
        if generation_id not in generation_names:
            raise CutoverAttestationError(
                "current generation directory is unavailable"
            )
        for name in generation_names:
            if SAFE_TOKEN.fullmatch(name) is None:
                raise CutoverAttestationError(
                    "release generations root contains an unsafe generation name"
                )
            generation_fd = _open_child_directory(
                generations_fd, name, "release generation directory"
            )
            try:
                _validate_owner_control_directory(
                    generation_fd,
                    "release generation directory",
                    expected_owner_uid=control_owner_uid,
                )
            finally:
                os.close(generation_fd)
    finally:
        os.close(generations_fd)

    journal_fd = _open_child_directory(
        shelf.fd, JOURNAL_NAME, "release activation journal"
    )
    try:
        _validate_owner_control_directory(
            journal_fd,
            "release activation journal",
            expected_owner_uid=control_owner_uid,
        )
    finally:
        os.close(journal_fd)
    journal_outcomes_fd(
        shelf.fd, entries, expected_owner_uid=control_owner_uid
    )
    _verify_directory_stable(shelf, root_before, "release shelf root")


def _state_root_exists(path: Path) -> bool:
    with anchored_parent(path, "cutover state root") as (parent, leaf):
        ensure_state_root_fd(parent.fd)
        matches = [
            name
            for name in directory_entry_names(parent.fd, "cutover state parent")
            if name.casefold() == leaf.casefold()
        ]
        if not matches:
            parent.verify_links()
            return False
        if matches != [leaf]:
            raise CutoverAttestationError("cutover state root has noncanonical casing")
        metadata = os.stat(leaf, dir_fd=parent.fd, follow_symlinks=False)
        if not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
            raise CutoverAttestationError("cutover state root is not a real directory")
        parent.verify_links()
        return True


def inspect_deploy_state(
    shelf_root: Path,
    state_root: Path,
    source_head: str,
) -> dict[str, Any]:
    if COMMIT.fullmatch(source_head) is None:
        raise CutoverAttestationError("source HEAD must be a full lowercase commit")
    state_path = _normalized_absolute_path(state_root, "cutover state root")
    if not _state_root_exists(state_path):
        return {
            "contractName": DEPLOY_STATE_CONTRACT,
            "status": "pass",
            "classification": "absent",
        }
    with anchored_directory(shelf_root, "release shelf root") as shelf, anchored_directory(
        state_path, "cutover state root"
    ) as state:
        shelf_before = _stable_directory_identity(shelf.fd)
        state_before = _stable_directory_identity(state.fd)
        entries = state_entries_fd(state.fd)
        phase_sets = {
            frozenset(): "empty",
            frozenset({PRESTATE_NAME}): "prestate",
            frozenset({PRESTATE_NAME, START_NAME}): "start",
            frozenset({PRESTATE_NAME, START_NAME, ABORTED_NAME}): "aborted",
            frozenset({PRESTATE_NAME, START_NAME, POSTSTATE_NAME}): "poststate",
            frozenset(
                {PRESTATE_NAME, START_NAME, POSTSTATE_NAME, COMPLETE_NAME}
            ): "complete",
        }
        phase = phase_sets.get(frozenset(entries))
        if phase is None:
            raise CutoverAttestationError("cutover state phase set is not canonical")
        if phase == "empty":
            _verify_directory_stable(state, state_before, "cutover state root")
            _verify_directory_stable(shelf, shelf_before, "release shelf root")
            return {
                "contractName": DEPLOY_STATE_CONTRACT,
                "status": "pass",
                "classification": "absent",
            }
        prestate, prestate_raw = load_state_at(state, PRESTATE_NAME, PRESTATE_CONTRACT)
        validate_prestate_receipt(
            prestate,
            state_root=state,
            shelf_root=shelf,
            source_head=None if phase == "complete" else source_head,
        )
        expected_snapshot = prestate.get("shelfSnapshot")
        if not isinstance(expected_snapshot, dict):
            raise CutoverAttestationError("cutover prestate snapshot is malformed")
        if phase == "prestate":
            current = capture_legacy_snapshot_fd(shelf, allow_aborted_history=False)
            if not strict_python_equal(current, expected_snapshot):
                raise CutoverAttestationError(
                    "legacy shelf changed after resumable cutover prestate"
                )
            classification = "prestate-resumable"
        else:
            start, start_raw = load_state_at(state, START_NAME, START_CONTRACT)
            validate_start_receipt(start, prestate_raw=prestate_raw)
            if phase == "start":
                shelf_entries = root_entries_fd(shelf.fd)
                has_activation_controls = any(
                    name.casefold()
                    in {POINTER_NAME.casefold(), ACTIVE_INTENT_NAME.casefold()}
                    for name in shelf_entries
                )
                if not has_activation_controls:
                    current = capture_legacy_snapshot_fd(
                        shelf, allow_aborted_history=True
                    )
                    if not strict_python_equal(current, expected_snapshot):
                        raise CutoverAttestationError(
                            "legacy shelf changed after candidate start receipt"
                        )
                classification = "unknown-outcome"
            elif phase == "aborted":
                aborted, _ = load_state_at(state, ABORTED_NAME, ABORTED_CONTRACT)
                validate_aborted_receipt(
                    aborted,
                    prestate=prestate,
                    prestate_raw=prestate_raw,
                    start_raw=start_raw,
                )
                current = capture_legacy_snapshot_fd(
                    shelf, allow_aborted_history=True
                )
                validate_aborted_shelf_snapshot(current, expected_snapshot)
                _, live_closure_digest = shelf_closure_fd(shelf.fd)
                if aborted.get("abortedShelfClosureDigest") != live_closure_digest:
                    raise CutoverAttestationError(
                        "aborted release shelf closure changed after attestation"
                    )
                classification = "aborted"
            else:
                poststate, poststate_raw = load_state_at(
                    state, POSTSTATE_NAME, POSTSTATE_CONTRACT
                )
                validate_poststate_receipt(
                    poststate,
                    prestate_raw=prestate_raw,
                    start_raw=start_raw,
                )
                if phase == "complete":
                    complete, _ = load_state_at(
                        state, COMPLETE_NAME, COMPLETE_CONTRACT
                    )
                    validate_complete_receipt(
                        complete,
                        poststate=poststate,
                        poststate_raw=poststate_raw,
                    )
                    validate_complete_evidence(complete)
                    validate_installed_bootstrap_fd(shelf)
                    classification = "complete"
                else:
                    live_poststate = verify_committed_fd(shelf, prestate)
                    _, live_closure_digest = shelf_closure_fd(shelf.fd)
                    if not strict_python_equal(
                        live_poststate,
                        {key: poststate.get(key) for key in live_poststate},
                    ) or poststate.get("shelfClosureDigest") != live_closure_digest:
                        raise CutoverAttestationError(
                            "committed release shelf changed after cutover poststate"
                        )
                    classification = "steady-handoff"
        _verify_directory_stable(state, state_before, "cutover state root")
        _verify_directory_stable(shelf, shelf_before, "release shelf root")
        return {
            "contractName": DEPLOY_STATE_CONTRACT,
            "status": "pass",
            "classification": classification,
        }


def prepare(shelf_root: Path, state_root: Path, source_head: str) -> dict[str, Any]:
    if COMMIT.fullmatch(source_head) is None:
        raise CutoverAttestationError("source HEAD must be a full lowercase commit")
    state_path = _normalized_absolute_path(state_root, "cutover state root")
    with anchored_directory(shelf_root, "release shelf root") as shelf:
        with anchored_parent(state_path, "cutover state root") as (parent, leaf):
            ensure_state_root_fd(parent.fd)
            matches = [
                name
                for name in directory_entry_names(parent.fd, "cutover state parent")
                if name.casefold() == leaf.casefold()
            ]
            if matches and matches != [leaf]:
                raise CutoverAttestationError("cutover state root has noncanonical casing")
            if not matches:
                snapshot = capture_legacy_snapshot_fd(
                    shelf, allow_aborted_history=False
                )
                os.mkdir(leaf, 0o700, dir_fd=parent.fd)
                os.fsync(parent.fd)
                parent.verify_links()
                linked = os.stat(leaf, dir_fd=parent.fd, follow_symlinks=False)
                if not stat.S_ISDIR(linked.st_mode) or stat.S_ISLNK(linked.st_mode):
                    raise CutoverAttestationError("cutover state root creation was redirected")
            else:
                snapshot = None
            with anchored_child_directory(
                parent, leaf, state_path, "cutover state root"
            ) as state:
                ensure_state_root_fd(state.fd)
                entries = state_entries_fd(state.fd)
                if snapshot is None and entries == set():
                    # An exact empty canonical directory is the sole recoverable
                    # residue of a crash between mkdir and anonymous publication.
                    snapshot = capture_legacy_snapshot_fd(
                        shelf, allow_aborted_history=False
                    )
                elif snapshot is None:
                    if entries != {PRESTATE_NAME}:
                        raise CutoverAttestationError(
                            "initial cutover state is not an exact resumable prestate"
                        )
                    existing, _ = load_state_at(
                        state, PRESTATE_NAME, PRESTATE_CONTRACT
                    )
                    validate_prestate_receipt(
                        existing,
                        state_root=state,
                        shelf_root=shelf,
                        source_head=source_head,
                    )
                    current_snapshot = capture_legacy_snapshot_fd(
                        shelf, allow_aborted_history=False
                    )
                    if not strict_python_equal(
                        existing.get("shelfSnapshot"), current_snapshot
                    ):
                        raise CutoverAttestationError(
                            "legacy shelf changed after resumable cutover prestate"
                        )
                    state.verify_links()
                    shelf.verify_links()
                    return existing
                if snapshot is None:
                    raise CutoverAttestationError(
                        "cutover prestate snapshot is unavailable"
                    )
                receipt = {
                    "contractName": PRESTATE_CONTRACT,
                    "status": "pass",
                    "generatedAtUtc": utc_now(),
                    "sourceHead": source_head,
                    "shelfRoot": str(shelf.path),
                    "shelfRootIdentity": directory_object_identity(shelf.fd),
                    "stateRootIdentity": directory_object_identity(state.fd),
                    "shelfSnapshot": snapshot,
                }
                shelf_rows, _ = shelf_closure_fd(shelf.fd)
                atomic_write_new_at(state, PRESTATE_NAME, receipt)
                current_snapshot = capture_legacy_snapshot_fd(
                    shelf, allow_aborted_history=False
                )
                recaptured_rows, _ = shelf_closure_fd(shelf.fd)
                if (
                    not strict_python_equal(snapshot, current_snapshot)
                    or not strict_python_equal(shelf_rows, recaptured_rows)
                ):
                    raise CutoverAttestationError(
                        "legacy shelf changed while prestate was persisted"
                    )
                state.verify_links()
                shelf.verify_links()
                return receipt


def request_start(shelf_root: Path, state_root: Path) -> dict[str, Any]:
    with anchored_directory(shelf_root, "release shelf root") as shelf, anchored_directory(
        state_root, "cutover state root"
    ) as state:
        state_before = _stable_directory_identity(state.fd)
        entries = state_entries_fd(state.fd)
        if entries not in ({PRESTATE_NAME}, {PRESTATE_NAME, START_NAME}):
            raise CutoverAttestationError("cutover state cannot request candidate start")
        prestate, prestate_raw = load_state_at(state, PRESTATE_NAME, PRESTATE_CONTRACT)
        validate_prestate_receipt(
            prestate,
            state_root=state,
            shelf_root=shelf,
        )
        current = capture_legacy_snapshot_fd(shelf, allow_aborted_history=True)
        if not strict_python_equal(current, prestate.get("shelfSnapshot")):
            raise CutoverAttestationError("legacy shelf changed after cutover prestate capture")
        receipt = {
            "contractName": START_CONTRACT,
            "status": "pass",
            "generatedAtUtc": utc_now(),
            "phase": "candidate_start_requested",
            "prestateSha256": f"sha256:{digest_bytes(prestate_raw)}",
        }
        shelf_rows, _ = shelf_closure_fd(shelf.fd)
        atomic_write_new_at(state, START_NAME, receipt)
        recaptured = capture_legacy_snapshot_fd(shelf, allow_aborted_history=True)
        recaptured_rows, _ = shelf_closure_fd(shelf.fd)
        if (
            not strict_python_equal(current, recaptured)
            or not strict_python_equal(shelf_rows, recaptured_rows)
        ):
            raise CutoverAttestationError(
                "legacy shelf changed while start receipt was persisted"
            )
        if START_NAME in entries:
            _verify_directory_stable(state, state_before, "cutover state root")
        else:
            state.verify_links()
        shelf.verify_links()
        return receipt


def _validate_manifest_binding(
    pointer: dict[str, Any], generation_id: str, role: str, name: str
) -> tuple[str, str]:
    manifests = pointer.get("manifests")
    if not isinstance(manifests, dict) or set(manifests) != {"canonical", "compatibility"}:
        raise CutoverAttestationError("current pointer manifest bindings are malformed")
    binding = manifests.get(role)
    if not isinstance(binding, dict) or set(binding) != {"path", "sha256"}:
        raise CutoverAttestationError(f"current pointer {role} binding is malformed")
    expected_path = f"/downloads/g/{generation_id}/{name}"
    if binding.get("path") != expected_path:
        raise CutoverAttestationError(f"current pointer {role} path is not generation-bound")
    return expected_path, require_sha256(binding.get("sha256"), f"{role} manifest sha256")


def verify_committed(shelf_root: Path, prestate: dict[str, Any]) -> dict[str, Any]:
    entries = root_entries(shelf_root)
    for name in (MARKER_NAME, POINTER_NAME, POLICY_NAME, JOURNAL_NAME, GENERATIONS_NAME):
        matches = [candidate for candidate in entries if candidate.casefold() == name.casefold()]
        if matches != [name]:
            raise CutoverAttestationError(f"committed cutover lacks canonical {name}")
    ensure_control_name_absent(entries, ACTIVE_INTENT_NAME)
    marker_bytes = read_regular_file(entries[MARKER_NAME], maximum_bytes=128)
    if marker_bytes != MARKER_BYTES:
        raise CutoverAttestationError("release shelf layout marker bytes are not canonical")
    writer_policy = validate_writer_policy(entries[POLICY_NAME])
    pointer, pointer_bytes = read_json(entries[POINTER_NAME], maximum_bytes=64 * 1024)
    require_exact_keys(
        pointer,
        {
            "schemaVersion", "generationId", "releaseVersion", "channel",
            "publishedAt", "manifests", "inventoryDigest", "activatedAt",
            "activationReceiptId",
        },
        "release shelf current pointer",
    )
    if pointer.get("schemaVersion") != POINTER_SCHEMA:
        raise CutoverAttestationError("release shelf current pointer schema is unsupported")
    generation_id = pointer.get("generationId")
    receipt_id = pointer.get("activationReceiptId")
    if not isinstance(generation_id, str) or SAFE_TOKEN.fullmatch(generation_id) is None:
        raise CutoverAttestationError("current generation id is unsafe")
    if not isinstance(receipt_id, str) or SAFE_TOKEN.fullmatch(receipt_id) is None:
        raise CutoverAttestationError("activation receipt id is unsafe")
    pre_identity = prestate["shelfSnapshot"]["manifestIdentity"]
    for field in ("releaseVersion", "channel", "publishedAt"):
        if pointer.get(field) != pre_identity.get(field):
            raise CutoverAttestationError(f"current pointer changed legacy {field}")
    pointer_inventory_digest = require_sha256(
        pointer.get("inventoryDigest"), "current inventoryDigest", prefix=True
    )
    canonical_route, canonical_sha = _validate_manifest_binding(
        pointer, generation_id, "canonical", CANONICAL_MANIFEST
    )
    compatibility_route, compatibility_sha = _validate_manifest_binding(
        pointer, generation_id, "compatibility", COMPATIBILITY_MANIFEST
    )
    generation_root = entries[GENERATIONS_NAME] / generation_id
    if generation_root.is_symlink() or not generation_root.is_dir():
        raise CutoverAttestationError("current generation directory is unavailable")
    candidate, candidate_bytes = read_json(generation_root / CANDIDATE_NAME)
    require_exact_keys(
        candidate,
        {
            "schemaVersion", "generationId", "releaseVersion", "channel",
            "publishedAt", "manifests", "inventoryDigest", "inventory",
        },
        "release shelf activation candidate",
    )
    if (
        candidate.get("schemaVersion") != CANDIDATE_SCHEMA
        or candidate.get("generationId") != generation_id
        or candidate.get("releaseVersion") != pointer.get("releaseVersion")
        or candidate.get("channel") != pointer.get("channel")
        or candidate.get("publishedAt") != pointer.get("publishedAt")
        or candidate.get("manifests") != pointer.get("manifests")
        or candidate.get("inventoryDigest") != pointer.get("inventoryDigest")
    ):
        raise CutoverAttestationError("activation candidate disagrees with current pointer")
    raw_inventory = candidate.get("inventory")
    if not isinstance(raw_inventory, list):
        raise CutoverAttestationError("activation candidate inventory is not a list")
    inventory: list[dict[str, str]] = []
    for index, raw_row in enumerate(raw_inventory):
        if not isinstance(raw_row, dict) or set(raw_row) != {"path", "sha256"}:
            raise CutoverAttestationError("activation candidate inventory row is malformed")
        path = safe_relative_path(raw_row.get("path"), f"inventory row {index} path")
        digest = require_sha256(raw_row.get("sha256"), f"inventory row {index} sha256")
        inventory.append({"path": path, "sha256": digest})
    if inventory != sorted(inventory, key=lambda row: row["path"]):
        raise CutoverAttestationError("activation candidate inventory is not sorted")
    if len({row["path"].casefold() for row in inventory}) != len(inventory):
        raise CutoverAttestationError("activation candidate inventory case-collides")
    if digest_bytes(canonical_json_bytes(inventory)) != pointer_inventory_digest:
        raise CutoverAttestationError("activation candidate inventory digest is invalid")
    actual_rows = inventory_tree(generation_root, skip_top_level_controls=False)
    actual_inventory = [
        {"path": row["path"], "sha256": row["sha256"]}
        for row in actual_rows
        if row["path"] not in (CANDIDATE_NAME, CANONICAL_MANIFEST, COMPATIBILITY_MANIFEST)
    ]
    if actual_inventory != inventory:
        raise CutoverAttestationError("generation bytes disagree with activation inventory")
    canonical_path = generation_root / CANONICAL_MANIFEST
    compatibility_path = generation_root / COMPATIBILITY_MANIFEST
    canonical_bytes = read_regular_file(canonical_path, maximum_bytes=4 * 1024 * 1024)
    compatibility_bytes = read_regular_file(
        compatibility_path, maximum_bytes=4 * 1024 * 1024
    )
    if digest_bytes(canonical_bytes) != canonical_sha or digest_bytes(compatibility_bytes) != compatibility_sha:
        raise CutoverAttestationError("generation manifest bytes disagree with current pointer")
    canonical_identity = manifest_identity(canonical_path, canonical=True)
    compatibility_identity = manifest_identity(compatibility_path, canonical=False)
    if canonical_identity != pre_identity or compatibility_identity != pre_identity:
        raise CutoverAttestationError("generation manifest identity changed during cutover")
    actual_by_path = {row["path"]: row for row in actual_rows}
    rewritten_metadata = prestate["shelfSnapshot"].get(
        "generationRewrittenMetadataPaths"
    )
    if not isinstance(rewritten_metadata, list) or any(
        not isinstance(path, str) for path in rewritten_metadata
    ):
        raise CutoverAttestationError("cutover prestate rewritten metadata paths are malformed")
    rewritten_metadata_paths = set(rewritten_metadata)
    for legacy_row in prestate["shelfSnapshot"]["legacyInventory"]["files"]:
        if (
            legacy_row["role"] != "payload"
            or legacy_row["path"] in rewritten_metadata_paths
        ):
            continue
        retained = actual_by_path.get(legacy_row["path"])
        if retained is None or (
            retained["sha256"], retained["sizeBytes"]
        ) != (legacy_row["sha256"], legacy_row["sizeBytes"]):
            raise CutoverAttestationError(
                f"legacy payload was not preserved: {legacy_row['path']}"
            )
    receipt_root = entries[JOURNAL_NAME] / receipt_id
    if receipt_root.is_symlink() or not receipt_root.is_dir():
        raise CutoverAttestationError("matching activation receipt directory is missing")
    if {item.name for item in receipt_root.iterdir()} != {"intent.json", "outcome.json"}:
        raise CutoverAttestationError("activation receipt contents are not exact")
    intent, intent_bytes = read_json(receipt_root / "intent.json", maximum_bytes=1024 * 1024)
    require_exact_keys(
        intent,
        {"schemaVersion", "state", "intent", "previousPointerBase64", "targetPointerBase64"},
        "activation journal intent",
    )
    identity = intent.get("intent")
    if not isinstance(identity, dict):
        raise CutoverAttestationError("activation journal identity is malformed")
    expected_identity_keys = {
        "operation", "previousGenerationId", "previousPointerSha256", "generationId",
        "activationReceiptId", "releaseVersion", "channel", "publishedAt",
        "inventoryDigest", "pointerSha256", "preparedAtUtc",
        "previousPointerBase64", "targetPointerBase64",
    }
    if "exactIncomingDesktopScope" in identity:
        expected_identity_keys.add("exactIncomingDesktopScope")
    require_exact_keys(identity, expected_identity_keys, "activation journal identity")
    if (
        intent.get("schemaVersion") != INTENT_SCHEMA
        or intent.get("state") != "prepared"
        or identity.get("operation") != "promotion"
        or identity.get("previousGenerationId") is not None
        or identity.get("previousPointerSha256") is not None
        or identity.get("previousPointerBase64") is not None
        or identity.get("exactIncomingDesktopScope") is not None
        or identity.get("generationId") != generation_id
        or identity.get("activationReceiptId") != receipt_id
        or identity.get("releaseVersion") != pointer.get("releaseVersion")
        or identity.get("channel") != pointer.get("channel")
        or identity.get("publishedAt") != pointer.get("publishedAt")
        or identity.get("inventoryDigest") != pointer.get("inventoryDigest")
        or identity.get("pointerSha256") != f"sha256:{digest_bytes(pointer_bytes)}"
        or intent.get("previousPointerBase64") is not None
    ):
        raise CutoverAttestationError("activation journal does not describe an initial promotion")
    target_base64 = base64.b64encode(pointer_bytes).decode("ascii")
    if identity.get("targetPointerBase64") != target_base64 or intent.get("targetPointerBase64") != target_base64:
        raise CutoverAttestationError("activation journal target bytes differ from current.json")
    outcome, _ = read_json(receipt_root / "outcome.json", maximum_bytes=1024 * 1024)
    require_exact_keys(
        outcome,
        {"schemaVersion", "state", "activationReceiptId", "intentSha256", "resolvedAtUtc"},
        "activation journal outcome",
    )
    serialized_intent = intent_bytes[:-1] if intent_bytes.endswith(b"\n") else intent_bytes
    if (
        outcome.get("schemaVersion") != OUTCOME_SCHEMA
        or outcome.get("state") != "committed"
        or outcome.get("activationReceiptId") != receipt_id
        or outcome.get("intentSha256") != f"sha256:{digest_bytes(serialized_intent)}"
    ):
        raise CutoverAttestationError("activation journal outcome is not a committed binding")
    return {
        "classification": "committed",
        "markerSha256": f"sha256:{digest_bytes(marker_bytes)}",
        "writerPolicy": writer_policy,
        "currentPointer": {
            "sha256": f"sha256:{digest_bytes(pointer_bytes)}",
            "generationId": generation_id,
            "activationReceiptId": receipt_id,
            "inventoryDigest": pointer.get("inventoryDigest"),
            "canonicalManifestPath": canonical_route,
            "canonicalManifestSha256": f"sha256:{canonical_sha}",
            "compatibilityManifestPath": compatibility_route,
            "compatibilityManifestSha256": f"sha256:{compatibility_sha}",
        },
        "activationCandidateSha256": f"sha256:{digest_bytes(candidate_bytes)}",
        "legacyInventoryDigest": prestate["shelfSnapshot"]["legacyInventory"]["digest"],
        "legacyPayloadPreserved": True,
        "activeIntentAbsent": True,
    }


def verify_committed_fd(
    shelf_root: AnchoredDirectory,
    prestate: dict[str, Any],
) -> dict[str, Any]:
    root_before = _stable_directory_identity(shelf_root.fd)
    entries = root_entries_fd(shelf_root.fd)
    control_owner_uid = validate_persistent_promotion_lock_at(
        shelf_root.fd, entries, required=True
    )
    if control_owner_uid is None:
        raise CutoverAttestationError(
            "committed cutover control owner is unavailable"
        )
    for name in (MARKER_NAME, POINTER_NAME, POLICY_NAME, JOURNAL_NAME, GENERATIONS_NAME):
        matches = {candidate for candidate in entries if candidate.casefold() == name.casefold()}
        if matches != {name}:
            raise CutoverAttestationError(f"committed cutover lacks canonical {name}")
    ensure_control_name_absent(entries, ACTIVE_INTENT_NAME)
    legacy_root_rows = inventory_tree_fd(
        shelf_root.fd,
        skip_top_level_controls=True,
    )
    expected_legacy_rows = prestate.get("shelfSnapshot", {}).get(
        "legacyInventory", {}
    ).get("files")
    if not strict_python_equal(legacy_root_rows, expected_legacy_rows):
        raise CutoverAttestationError(
            "committed cutover changed the exact legacy shelf inventory"
        )
    marker_bytes = read_regular_file_at(
        shelf_root.fd,
        MARKER_NAME,
        label="release shelf layout marker",
        maximum_bytes=128,
        forbid_group_world_write=True,
        expected_owner_uid=control_owner_uid,
    )
    if marker_bytes != MARKER_BYTES:
        raise CutoverAttestationError("release shelf layout marker bytes are not canonical")
    writer_policy = validate_writer_policy_at(
        shelf_root.fd, expected_owner_uid=control_owner_uid
    )
    pointer, pointer_bytes = read_json_at(
        shelf_root.fd,
        POINTER_NAME,
        label="release shelf current pointer",
        maximum_bytes=64 * 1024,
        forbid_group_world_write=True,
        expected_owner_uid=control_owner_uid,
    )
    require_exact_keys(
        pointer,
        {
            "schemaVersion", "generationId", "releaseVersion", "channel",
            "publishedAt", "manifests", "inventoryDigest", "activatedAt",
            "activationReceiptId",
        },
        "release shelf current pointer",
    )
    if pointer.get("schemaVersion") != POINTER_SCHEMA:
        raise CutoverAttestationError("release shelf current pointer schema is unsupported")
    generation_id = require_string(pointer.get("generationId"), "current generation id")
    receipt_id = require_string(pointer.get("activationReceiptId"), "activation receipt id")
    if SAFE_TOKEN.fullmatch(generation_id) is None or SAFE_TOKEN.fullmatch(receipt_id) is None:
        raise CutoverAttestationError("current pointer contains an unsafe identity")
    require_utc_timestamp(pointer.get("publishedAt"), "current pointer publishedAt")
    require_utc_timestamp(pointer.get("activatedAt"), "current pointer activatedAt")
    pre_identity = prestate["shelfSnapshot"]["manifestIdentity"]
    for field in ("releaseVersion", "channel", "publishedAt"):
        if pointer.get(field) != pre_identity.get(field):
            raise CutoverAttestationError(f"current pointer changed legacy {field}")
    pointer_inventory_digest = require_sha256(
        pointer.get("inventoryDigest"), "current inventoryDigest", prefix=True
    )
    canonical_route, canonical_sha = _validate_manifest_binding(
        pointer, generation_id, "canonical", CANONICAL_MANIFEST
    )
    compatibility_route, compatibility_sha = _validate_manifest_binding(
        pointer, generation_id, "compatibility", COMPATIBILITY_MANIFEST
    )

    generations_fd = _open_child_directory(
        shelf_root.fd, GENERATIONS_NAME, "release generations root"
    )
    try:
        _validate_owner_control_directory(
            generations_fd,
            "release generations root",
            expected_owner_uid=control_owner_uid,
        )
        generations_before = _stable_directory_identity(generations_fd)
        if directory_entry_names(generations_fd, "release generations root") != [generation_id]:
            raise CutoverAttestationError(
                "committed cutover requires exactly the current generation"
            )
        generation_fd = _open_child_directory(
            generations_fd, generation_id, "current release generation"
        )
        try:
            _validate_owner_control_directory(
                generation_fd,
                "current release generation",
                expected_owner_uid=control_owner_uid,
            )
            generation_before = _stable_directory_identity(generation_fd)
            candidate, candidate_bytes = read_json_at(
                generation_fd,
                CANDIDATE_NAME,
                label="release shelf activation candidate",
            )
            require_exact_keys(
                candidate,
                {
                    "schemaVersion", "generationId", "releaseVersion", "channel",
                    "publishedAt", "manifests", "inventoryDigest", "inventory",
                },
                "release shelf activation candidate",
            )
            if (
                candidate.get("schemaVersion") != CANDIDATE_SCHEMA
                or candidate.get("generationId") != generation_id
                or candidate.get("releaseVersion") != pointer.get("releaseVersion")
                or candidate.get("channel") != pointer.get("channel")
                or candidate.get("publishedAt") != pointer.get("publishedAt")
                or candidate.get("manifests") != pointer.get("manifests")
                or candidate.get("inventoryDigest") != pointer.get("inventoryDigest")
            ):
                raise CutoverAttestationError("activation candidate disagrees with current pointer")
            require_utc_timestamp(candidate.get("publishedAt"), "activation candidate publishedAt")
            raw_inventory = candidate.get("inventory")
            if not isinstance(raw_inventory, list):
                raise CutoverAttestationError("activation candidate inventory is not a list")
            inventory: list[dict[str, str]] = []
            for index, raw_row in enumerate(raw_inventory):
                if not isinstance(raw_row, dict) or set(raw_row) != {"path", "sha256"}:
                    raise CutoverAttestationError("activation candidate inventory row is malformed")
                path = safe_relative_path(raw_row.get("path"), f"inventory row {index} path")
                digest = require_sha256(raw_row.get("sha256"), f"inventory row {index} sha256")
                inventory.append({"path": path, "sha256": digest})
            if inventory != sorted(inventory, key=lambda row: row["path"]):
                raise CutoverAttestationError("activation candidate inventory is not sorted")
            if len({row["path"].casefold() for row in inventory}) != len(inventory):
                raise CutoverAttestationError("activation candidate inventory case-collides")
            if digest_bytes(canonical_json_bytes(inventory)) != pointer_inventory_digest:
                raise CutoverAttestationError("activation candidate inventory digest is invalid")
            actual_rows = inventory_tree_fd(
                generation_fd, skip_top_level_controls=False
            )
            actual_inventory = [
                {"path": row["path"], "sha256": row["sha256"]}
                for row in actual_rows
                if row["path"] not in (
                    CANDIDATE_NAME, CANONICAL_MANIFEST, COMPATIBILITY_MANIFEST
                )
            ]
            if actual_inventory != inventory:
                raise CutoverAttestationError(
                    "generation bytes disagree with activation inventory"
                )
            canonical_bytes = read_regular_file_at(
                generation_fd,
                CANONICAL_MANIFEST,
                label="generation canonical manifest",
                maximum_bytes=4 * 1024 * 1024,
            )
            compatibility_bytes = read_regular_file_at(
                generation_fd,
                COMPATIBILITY_MANIFEST,
                label="generation compatibility manifest",
                maximum_bytes=4 * 1024 * 1024,
            )
            if (
                digest_bytes(canonical_bytes) != canonical_sha
                or digest_bytes(compatibility_bytes) != compatibility_sha
            ):
                raise CutoverAttestationError(
                    "generation manifest bytes disagree with current pointer"
                )
            canonical_identity = manifest_identity_at(
                generation_fd, CANONICAL_MANIFEST, canonical=True
            )
            compatibility_identity = manifest_identity_at(
                generation_fd, COMPATIBILITY_MANIFEST, canonical=False
            )
            if canonical_identity != pre_identity or compatibility_identity != pre_identity:
                raise CutoverAttestationError(
                    "generation manifest identity changed during cutover"
                )
            actual_by_path = {row["path"]: row for row in actual_rows}
            rewritten_metadata = prestate["shelfSnapshot"].get(
                "generationRewrittenMetadataPaths"
            )
            if not isinstance(rewritten_metadata, list) or any(
                not isinstance(path, str) for path in rewritten_metadata
            ):
                raise CutoverAttestationError(
                    "cutover prestate rewritten metadata paths are malformed"
                )
            rewritten_metadata_paths = set(rewritten_metadata)
            for legacy_row in prestate["shelfSnapshot"]["legacyInventory"]["files"]:
                if (
                    legacy_row["role"] != "payload"
                    or legacy_row["path"] in rewritten_metadata_paths
                ):
                    continue
                retained = actual_by_path.get(legacy_row["path"])
                if retained is None or (
                    retained["sha256"], retained["sizeBytes"]
                ) != (legacy_row["sha256"], legacy_row["sizeBytes"]):
                    raise CutoverAttestationError(
                        f"legacy payload was not preserved: {legacy_row['path']}"
                    )
            _verify_child_directory_link(
                generations_fd,
                generation_id,
                generation_fd,
                generation_before,
                "current release generation",
            )
        finally:
            os.close(generation_fd)
        _verify_child_directory_link(
            shelf_root.fd,
            GENERATIONS_NAME,
            generations_fd,
            generations_before,
            "release generations root",
        )
    finally:
        os.close(generations_fd)

    journal_fd = _open_child_directory(
        shelf_root.fd, JOURNAL_NAME, "release activation journal"
    )
    try:
        _validate_owner_control_directory(
            journal_fd,
            "release activation journal",
            expected_owner_uid=control_owner_uid,
        )
        journal_before = _stable_directory_identity(journal_fd)
        if directory_entry_names(journal_fd, "release activation journal") != [receipt_id]:
            raise CutoverAttestationError(
                "committed cutover requires exactly one matching activation receipt"
            )
        receipt_fd = _open_child_directory(
            journal_fd, receipt_id, "matching activation receipt"
        )
        try:
            _validate_owner_control_directory(
                receipt_fd,
                "matching activation receipt",
                expected_owner_uid=control_owner_uid,
            )
            receipt_before = _stable_directory_identity(receipt_fd)
            if set(directory_entry_names(receipt_fd, "matching activation receipt")) != {
                "intent.json", "outcome.json"
            }:
                raise CutoverAttestationError("activation receipt contents are not exact")
            intent, intent_bytes = read_json_at(
                receipt_fd,
                "intent.json",
                label="activation journal intent",
                maximum_bytes=1024 * 1024,
                forbid_group_world_write=True,
                expected_owner_uid=control_owner_uid,
            )
            require_exact_keys(
                intent,
                {
                    "schemaVersion", "state", "intent", "previousPointerBase64",
                    "targetPointerBase64",
                },
                "activation journal intent",
            )
            identity = intent.get("intent")
            expected_identity_keys = {
                "operation", "previousGenerationId", "previousPointerSha256",
                "generationId", "activationReceiptId", "releaseVersion", "channel",
                "publishedAt", "inventoryDigest", "pointerSha256", "preparedAtUtc",
                "previousPointerBase64", "targetPointerBase64",
                "exactIncomingDesktopScope",
            }
            if not isinstance(identity, dict):
                raise CutoverAttestationError("activation journal identity is malformed")
            require_exact_keys(identity, expected_identity_keys, "activation journal identity")
            require_utc_timestamp(identity.get("publishedAt"), "activation intent publishedAt")
            require_utc_timestamp(identity.get("preparedAtUtc"), "activation intent preparedAtUtc")
            if (
                intent.get("schemaVersion") != INTENT_SCHEMA
                or intent.get("state") != "prepared"
                or identity.get("operation") != "promotion"
                or identity.get("previousGenerationId") is not None
                or identity.get("previousPointerSha256") is not None
                or identity.get("previousPointerBase64") is not None
                or identity.get("exactIncomingDesktopScope") is not None
                or identity.get("generationId") != generation_id
                or identity.get("activationReceiptId") != receipt_id
                or identity.get("releaseVersion") != pointer.get("releaseVersion")
                or identity.get("channel") != pointer.get("channel")
                or not utc_timestamps_equal(
                    identity.get("publishedAt"), pointer.get("publishedAt")
                )
                or identity.get("inventoryDigest") != pointer.get("inventoryDigest")
                or identity.get("pointerSha256")
                != f"sha256:{digest_bytes(pointer_bytes)}"
                or intent.get("previousPointerBase64") is not None
            ):
                raise CutoverAttestationError(
                    "activation journal does not describe an initial promotion"
                )
            target_base64 = base64.b64encode(pointer_bytes).decode("ascii")
            if (
                identity.get("targetPointerBase64") != target_base64
                or intent.get("targetPointerBase64") != target_base64
            ):
                raise CutoverAttestationError(
                    "activation journal target bytes differ from current.json"
                )
            outcome, _ = read_json_at(
                receipt_fd,
                "outcome.json",
                label="activation journal outcome",
                maximum_bytes=1024 * 1024,
                forbid_group_world_write=True,
                expected_owner_uid=control_owner_uid,
            )
            require_exact_keys(
                outcome,
                {
                    "schemaVersion", "state", "activationReceiptId",
                    "intentSha256", "resolvedAtUtc",
                },
                "activation journal outcome",
            )
            require_utc_timestamp(outcome.get("resolvedAtUtc"), "activation outcome resolvedAtUtc")
            serialized_intent = (
                intent_bytes[:-1] if intent_bytes.endswith(b"\n") else intent_bytes
            )
            if (
                outcome.get("schemaVersion") != OUTCOME_SCHEMA
                or outcome.get("state") != "committed"
                or outcome.get("activationReceiptId") != receipt_id
                or outcome.get("intentSha256")
                != f"sha256:{digest_bytes(serialized_intent)}"
            ):
                raise CutoverAttestationError(
                    "activation journal outcome is not a committed binding"
                )
            _verify_child_directory_link(
                journal_fd,
                receipt_id,
                receipt_fd,
                receipt_before,
                "matching activation receipt",
            )
        finally:
            os.close(receipt_fd)
        _verify_child_directory_link(
            shelf_root.fd,
            JOURNAL_NAME,
            journal_fd,
            journal_before,
            "release activation journal",
        )
    finally:
        os.close(journal_fd)
    _verify_directory_stable(shelf_root, root_before, "release shelf root")
    return {
        "classification": "committed",
        "markerSha256": f"sha256:{digest_bytes(marker_bytes)}",
        "writerPolicy": writer_policy,
        "currentPointer": {
            "sha256": f"sha256:{digest_bytes(pointer_bytes)}",
            "generationId": generation_id,
            "activationReceiptId": receipt_id,
            "inventoryDigest": pointer.get("inventoryDigest"),
            "canonicalManifestPath": canonical_route,
            "canonicalManifestSha256": f"sha256:{canonical_sha}",
            "compatibilityManifestPath": compatibility_route,
            "compatibilityManifestSha256": f"sha256:{compatibility_sha}",
        },
        "activationCandidateSha256": f"sha256:{digest_bytes(candidate_bytes)}",
        "legacyInventoryDigest": prestate["shelfSnapshot"]["legacyInventory"]["digest"],
        "legacyPayloadPreserved": True,
        "activeIntentAbsent": True,
    }


def verify_outcome(shelf_root: Path, state_root: Path) -> dict[str, Any]:
    with anchored_directory(shelf_root, "release shelf root") as shelf, anchored_directory(
        state_root, "cutover state root"
    ) as state:
        shelf_before = _stable_directory_identity(shelf.fd)
        state_entries = state_entries_fd(state.fd)
        if state_entries != {PRESTATE_NAME, START_NAME}:
            raise CutoverAttestationError(
                "cutover outcome requires the exact prestate/start phase"
            )
        prestate, prestate_raw = load_state_at(state, PRESTATE_NAME, PRESTATE_CONTRACT)
        validate_prestate_receipt(
            prestate,
            state_root=state,
            shelf_root=shelf,
        )
        start, start_raw = load_state_at(state, START_NAME, START_CONTRACT)
        validate_start_receipt(start, prestate_raw=prestate_raw)
        entries = root_entries_fd(shelf.fd)
        active_matches = {
            name for name in entries if name.casefold() == ACTIVE_INTENT_NAME.casefold()
        }
        if active_matches:
            raise CutoverAttestationError(
                "release shelf activation outcome remains unknown; recovery-only startup is required"
            )
        current_matches = {
            name for name in entries if name.casefold() == POINTER_NAME.casefold()
        }
        if not current_matches:
            snapshot = capture_legacy_snapshot_fd(shelf, allow_aborted_history=True)
            shelf_inventory, shelf_closure_digest = shelf_closure_fd(shelf.fd)
            expected = prestate.get("shelfSnapshot")
            if not isinstance(expected, dict):
                raise CutoverAttestationError("cutover prestate snapshot is malformed")
            validate_aborted_shelf_snapshot(snapshot, expected)
            receipt = {
                "contractName": ABORTED_CONTRACT,
                "status": "pass",
                "generatedAtUtc": utc_now(),
                "classification": "aborted",
                "prestateSha256": f"sha256:{digest_bytes(prestate_raw)}",
                "startRequestSha256": f"sha256:{digest_bytes(start_raw)}",
                "legacyInventoryDigest": expected["legacyInventory"]["digest"],
                "abortedShelfClosureDigest": shelf_closure_digest,
                "legacyShelfUnchanged": True,
                "activeIntentAbsent": True,
            }
            atomic_write_new_at(state, ABORTED_NAME, receipt)
            recaptured = capture_legacy_snapshot_fd(
                shelf, allow_aborted_history=True
            )
            recaptured_inventory, _ = shelf_closure_fd(shelf.fd)
            if (
                not strict_python_equal(snapshot, recaptured)
                or not strict_python_equal(shelf_inventory, recaptured_inventory)
            ):
                raise CutoverAttestationError(
                    "legacy shelf changed while aborted receipt was persisted"
                )
            shelf.verify_links()
            return receipt
        if current_matches != {POINTER_NAME}:
            raise CutoverAttestationError("current pointer has noncanonical casing")
        post = verify_committed_fd(shelf, prestate)
        shelf_inventory, shelf_closure_digest = shelf_closure_fd(shelf.fd)
        receipt = {
            "contractName": POSTSTATE_CONTRACT,
            "status": "pass",
            "generatedAtUtc": utc_now(),
            "prestateSha256": f"sha256:{digest_bytes(prestate_raw)}",
            "startRequestSha256": f"sha256:{digest_bytes(start_raw)}",
            "shelfClosureDigest": shelf_closure_digest,
            **post,
        }
        atomic_write_new_at(state, POSTSTATE_NAME, receipt)
        live_post = verify_committed_fd(shelf, prestate)
        recaptured_inventory, _ = shelf_closure_fd(shelf.fd)
        if (
            not strict_python_equal(post, live_post)
            or not strict_python_equal(shelf_inventory, recaptured_inventory)
        ):
            raise CutoverAttestationError(
                "committed shelf changed while poststate receipt was persisted"
            )
        shelf.verify_links()
        return receipt


def verify_handoff(shelf_root: Path, state_root: Path) -> dict[str, Any]:
    """Read-only revalidation of the exact poststate handoff phase."""

    with anchored_directory(shelf_root, "release shelf root") as shelf, anchored_directory(
        state_root, "cutover state root"
    ) as state:
        shelf_before = _stable_directory_identity(shelf.fd)
        state_before = _stable_directory_identity(state.fd)
        entries = state_entries_fd(state.fd)
        if entries != {PRESTATE_NAME, START_NAME, POSTSTATE_NAME}:
            raise CutoverAttestationError(
                "cutover handoff requires the exact prestate/start/poststate phase"
            )
        prestate, prestate_raw = load_state_at(
            state, PRESTATE_NAME, PRESTATE_CONTRACT
        )
        validate_prestate_receipt(
            prestate,
            state_root=state,
            shelf_root=shelf,
        )
        start, start_raw = load_state_at(state, START_NAME, START_CONTRACT)
        validate_start_receipt(start, prestate_raw=prestate_raw)
        poststate, _ = load_state_at(state, POSTSTATE_NAME, POSTSTATE_CONTRACT)
        validate_poststate_receipt(
            poststate,
            prestate_raw=prestate_raw,
            start_raw=start_raw,
        )
        live = verify_committed_fd(shelf, prestate)
        _, live_closure_digest = shelf_closure_fd(shelf.fd)
        if not strict_python_equal(
            live, {key: poststate.get(key) for key in live}
        ) or poststate.get("shelfClosureDigest") != live_closure_digest:
            raise CutoverAttestationError(
                "committed release shelf changed after cutover poststate"
            )
        _verify_directory_stable(state, state_before, "cutover state root")
        _verify_directory_stable(shelf, shelf_before, "release shelf root")
        return poststate


def _decode_json_object(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=reject_duplicates,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CutoverAttestationError(f"malformed JSON: {label}") from exc
    if not isinstance(value, dict):
        raise CutoverAttestationError(f"JSON root is not an object: {label}")
    return value


def _atomic_write_evidence_raw(output: Path, expected_name: str, raw: bytes) -> None:
    output_path = _normalized_absolute_path(output, "cutover evidence output")
    if output_path.name != expected_name:
        raise CutoverAttestationError("cutover evidence output name is not canonical")
    with anchored_parent(output_path, "cutover evidence output") as (parent, name):
        ensure_state_root_fd(parent.fd)
        matches = [
            candidate
            for candidate in directory_entry_names(parent.fd, "deploy receipt directory")
            if candidate.casefold() == name.casefold()
        ]
        if matches and matches != [name]:
            raise CutoverAttestationError("cutover evidence has a casing alias")
        if matches:
            existing = read_regular_file_at(
                parent.fd,
                name,
                label=f"cutover evidence {name}",
                maximum_bytes=MAX_JSON_BYTES,
                owner_only=True,
            )
            if existing != raw:
                raise CutoverAttestationError(
                    f"cutover evidence already exists with different bytes: {name}"
                )
            final_matches = sorted(
                candidate
                for candidate in directory_entry_names(
                    parent.fd, "deploy receipt directory"
                )
                if candidate.casefold() == name.casefold()
            )
            if final_matches != [name]:
                raise CutoverAttestationError("cutover evidence has a casing alias")
            parent.verify_links()
            return
        try:
            _write_and_publish_unnamed_at(
                parent.fd,
                name,
                raw,
                f"cutover evidence {name}",
            )
        except FileExistsError:
            existing = read_regular_file_at(
                parent.fd,
                name,
                label=f"cutover evidence {name}",
                maximum_bytes=MAX_JSON_BYTES,
                owner_only=True,
            )
            if existing != raw:
                raise CutoverAttestationError(
                    f"cutover evidence already exists with different bytes: {name}"
                )
        final_matches = sorted(
            candidate
            for candidate in directory_entry_names(
                parent.fd, "deploy receipt directory"
            )
            if candidate.casefold() == name.casefold()
        )
        if final_matches != [name]:
            raise CutoverAttestationError("cutover evidence has a casing alias")
        published = read_regular_file_at(
            parent.fd,
            name,
            label=f"cutover evidence {name}",
            maximum_bytes=MAX_JSON_BYTES,
            owner_only=True,
        )
        if published != raw:
            raise CutoverAttestationError(
                f"cutover evidence publication bytes changed: {name}"
            )
        parent.verify_links()


def _read_evidence_source(
    source: Path,
    label: str,
) -> tuple[dict[str, Any], bytes, tuple[int, int, int, int, int, int, int]]:
    source_path = _normalized_absolute_path(source, label)
    with anchored_parent(source_path, label) as (parent, name):
        before = _stable_directory_identity(parent.fd)
        matches = sorted(
            candidate
            for candidate in directory_entry_names(parent.fd, f"{label} parent")
            if candidate.casefold() == name.casefold()
        )
        if matches != [name]:
            raise CutoverAttestationError(f"{label} has a casing alias")
        raw = read_regular_file_at(
            parent.fd,
            name,
            label=label,
            maximum_bytes=MAX_JSON_BYTES,
            require_owner=True,
            forbid_group_world_write=True,
        )
        payload = _decode_json_object(raw, label)
        source_identity = _identity(
            os.stat(name, dir_fd=parent.fd, follow_symlinks=False)
        )
        _verify_directory_stable(parent, before, f"{label} parent")
        return payload, raw, source_identity


def _verify_evidence_source_unchanged(
    source: Path,
    label: str,
    expected_raw: bytes,
    expected_identity: tuple[int, int, int, int, int, int, int],
) -> None:
    source_path = _normalized_absolute_path(source, label)
    with anchored_parent(source_path, label) as (parent, name):
        before = _stable_directory_identity(parent.fd)
        matches = sorted(
            candidate
            for candidate in directory_entry_names(parent.fd, f"{label} parent")
            if candidate.casefold() == name.casefold()
        )
        if matches != [name]:
            raise CutoverAttestationError(f"{label} has a casing alias")
        raw = read_regular_file_at(
            parent.fd,
            name,
            label=label,
            maximum_bytes=MAX_JSON_BYTES,
            require_owner=True,
            forbid_group_world_write=True,
        )
        actual_identity = _identity(
            os.stat(name, dir_fd=parent.fd, follow_symlinks=False)
        )
        if raw != expected_raw or actual_identity != expected_identity:
            raise CutoverAttestationError(
                f"{label} changed before immutable snapshot publication"
            )
        _verify_directory_stable(parent, before, f"{label} parent")


def snapshot_evidence(kind: str, source: Path, output: Path) -> dict[str, Any]:
    expected_name = EVIDENCE_NAMES.get(kind)
    if expected_name is None:
        raise CutoverAttestationError("cutover evidence kind is unsupported")
    source_label = f"{kind} evidence source"
    payload, raw, source_identity = _read_evidence_source(source, source_label)
    if kind == "compose":
        validate_compose_attestation(payload)
    elif kind == "postdeploy":
        validate_postdeploy_attestation(payload)
    else:
        validate_active_runtime_authority(payload)
    _atomic_write_evidence_raw(output, expected_name, raw)
    _verify_evidence_source_unchanged(
        source,
        source_label,
        raw,
        source_identity,
    )
    return {
        "contractName": "chummer.initial-release-shelf-cutover-evidence-snapshot/v1",
        "status": "pass",
        "kind": kind,
        "sha256": f"sha256:{digest_bytes(raw)}",
    }


def record_readiness(
    output: Path,
    *,
    candidate_container_id: str,
    candidate_container_name: str,
    candidate_image_id: str,
    http_status: int,
    response_sha256: str,
    running: str,
    health: str,
) -> dict[str, Any]:
    receipt = {
        "contractName": READINESS_CONTRACT,
        "status": "pass",
        "generatedAtUtc": utc_now(),
        "candidateContainerId": candidate_container_id,
        "candidateContainerName": candidate_container_name,
        "candidateImageId": candidate_image_id,
        "endpoint": "http://127.0.0.1:8080/api/ready/publication",
        "hostHeader": "chummer.run",
        "httpStatus": http_status,
        "responseSha256": f"sha256:{response_sha256}",
        "running": running == "true",
        "health": health,
    }
    if running != "true":
        raise CutoverAttestationError("publication readiness running state is not true")
    validate_readiness_attestation(receipt)
    raw = _render_receipt(receipt)
    _atomic_write_evidence_raw(output, READINESS_EVIDENCE_NAME, raw)
    return receipt


def _read_evidence_bundle(
    compose_attestation: Path,
    readiness_attestation: Path,
    postdeploy_attestation: Path,
    active_runtime_authority: Path,
) -> tuple[
    dict[str, tuple[dict[str, Any], bytes]],
    dict[str, str | int],
]:
    requested = {
        "compose": (compose_attestation, COMPOSE_EVIDENCE_NAME),
        "readiness": (readiness_attestation, READINESS_EVIDENCE_NAME),
        "postdeploy": (postdeploy_attestation, POSTDEPLOY_EVIDENCE_NAME),
        "active-runtime": (
            active_runtime_authority,
            RUNTIME_AUTHORITY_EVIDENCE_NAME,
        ),
    }
    normalized: dict[str, Path] = {}
    for kind, (path, expected_name) in requested.items():
        normalized_path = _normalized_absolute_path(path, f"{kind} evidence")
        if normalized_path.name != expected_name:
            raise CutoverAttestationError(f"{kind} evidence name is not canonical")
        normalized[kind] = normalized_path
    parents = {str(path.parent) for path in normalized.values()}
    if len(parents) != 1:
        raise CutoverAttestationError("cutover final evidence is not one deploy receipt set")
    parent_path = next(iter(normalized.values())).parent
    with anchored_directory(parent_path, "deploy receipt directory") as parent:
        ensure_state_root_fd(parent.fd)
        before = _stable_directory_identity(parent.fd)
        result: dict[str, tuple[dict[str, Any], bytes]] = {}
        for kind, path in normalized.items():
            matches = sorted(
                candidate
                for candidate in directory_entry_names(
                    parent.fd, "deploy receipt directory"
                )
                if candidate.casefold() == path.name.casefold()
            )
            if matches != [path.name]:
                raise CutoverAttestationError(
                    f"cutover {kind} evidence has a casing alias"
                )
            raw = read_regular_file_at(
                parent.fd,
                path.name,
                label=f"cutover {kind} evidence",
                maximum_bytes=MAX_JSON_BYTES,
                owner_only=True,
            )
            result[kind] = (_decode_json_object(raw, f"cutover {kind} evidence"), raw)
        metadata = os.fstat(parent.fd)
        binding: dict[str, str | int] = {
            "path": str(parent.path),
            "device": metadata.st_dev,
            "inode": metadata.st_ino,
        }
        _verify_directory_stable(parent, before, "deploy receipt directory")
        return result, binding


def validate_complete_evidence(payload: dict[str, Any]) -> None:
    binding = payload.get("evidenceDirectory")
    if not isinstance(binding, dict):
        raise CutoverAttestationError(
            "cutover complete evidence directory binding is malformed"
        )
    evidence_root = _normalized_absolute_path(
        require_string(binding.get("path"), "cutover complete evidence path"),
        "cutover complete evidence path",
    )
    evidence, actual_binding = _read_evidence_bundle(
        evidence_root / COMPOSE_EVIDENCE_NAME,
        evidence_root / READINESS_EVIDENCE_NAME,
        evidence_root / POSTDEPLOY_EVIDENCE_NAME,
        evidence_root / RUNTIME_AUTHORITY_EVIDENCE_NAME,
    )
    if not strict_python_equal(actual_binding, binding):
        raise CutoverAttestationError(
            "cutover complete evidence directory object changed"
        )
    compose, compose_raw = evidence["compose"]
    readiness, readiness_raw = evidence["readiness"]
    postdeploy, postdeploy_raw = evidence["postdeploy"]
    active, active_raw = evidence["active-runtime"]
    validate_compose_attestation(compose)
    readiness_candidate = validate_readiness_attestation(readiness)
    validate_postdeploy_attestation(postdeploy)
    active_candidate = validate_active_runtime_authority(active)
    if (
        not strict_python_equal(readiness_candidate, active_candidate)
        or not strict_python_equal(readiness_candidate, payload.get("candidate"))
    ):
        raise CutoverAttestationError(
            "cutover complete evidence candidate identities disagree"
        )
    expected_hashes = {
        "composeAttestationSha256": compose_raw,
        "readinessAttestationSha256": readiness_raw,
        "postdeployAttestationSha256": postdeploy_raw,
        "activeRuntimeAuthoritySha256": active_raw,
    }
    for field, raw in expected_hashes.items():
        if payload.get(field) != f"sha256:{digest_bytes(raw)}":
            raise CutoverAttestationError(
                f"cutover complete evidence hash changed: {field}"
            )


def finalize(
    state_root: Path,
    compose_attestation: Path,
    readiness_attestation: Path,
    postdeploy_attestation: Path,
    active_runtime_authority: Path,
    candidate_image_id: str,
) -> dict[str, Any]:
    if IMAGE_ID.fullmatch(candidate_image_id) is None:
        raise CutoverAttestationError("steady runtime candidate image id is invalid")
    evidence, evidence_directory = _read_evidence_bundle(
        compose_attestation,
        readiness_attestation,
        postdeploy_attestation,
        active_runtime_authority,
    )
    compose, compose_raw = evidence["compose"]
    readiness, readiness_raw = evidence["readiness"]
    postdeploy, postdeploy_raw = evidence["postdeploy"]
    active, active_raw = evidence["active-runtime"]
    validate_compose_attestation(compose)
    candidate = validate_readiness_attestation(readiness)
    validate_postdeploy_attestation(postdeploy)
    active_candidate = validate_active_runtime_authority(active)
    if not strict_python_equal(candidate, active_candidate):
        raise CutoverAttestationError(
            "readiness and active runtime candidate identities disagree"
        )
    if candidate["imageId"] != candidate_image_id:
        raise CutoverAttestationError("candidate image differs from final runtime evidence")
    expected_posture = {
        "CHUMMER_RELEASE_SHELF_LAYOUT_V1_REQUIRED": "true",
        "CHUMMER_RELEASE_SHELF_INITIAL_MIGRATION_ALLOWED": "false",
    }
    with anchored_directory(state_root, "cutover state root") as state:
        state_before = _stable_directory_identity(state.fd)
        entries = state_entries_fd(state.fd)
        if entries not in (
            {PRESTATE_NAME, START_NAME, POSTSTATE_NAME},
            {PRESTATE_NAME, START_NAME, POSTSTATE_NAME, COMPLETE_NAME},
        ):
            raise CutoverAttestationError("cutover state cannot be finalized")
        prestate, prestate_raw = load_state_at(state, PRESTATE_NAME, PRESTATE_CONTRACT)
        start, start_raw = load_state_at(state, START_NAME, START_CONTRACT)
        poststate, poststate_raw = load_state_at(
            state, POSTSTATE_NAME, POSTSTATE_CONTRACT
        )
        validate_start_receipt(start, prestate_raw=prestate_raw)
        validate_poststate_receipt(
            poststate,
            prestate_raw=prestate_raw,
            start_raw=start_raw,
        )
        current = poststate.get("currentPointer")
        if not isinstance(current, dict):
            raise CutoverAttestationError("cutover poststate current pointer is malformed")
        receipt = {
            "contractName": COMPLETE_CONTRACT,
            "status": "pass",
            "generatedAtUtc": utc_now(),
            "poststateSha256": f"sha256:{digest_bytes(poststate_raw)}",
            "composeAttestationSha256": f"sha256:{digest_bytes(compose_raw)}",
            "readinessAttestationSha256": f"sha256:{digest_bytes(readiness_raw)}",
            "postdeployAttestationSha256": f"sha256:{digest_bytes(postdeploy_raw)}",
            "activeRuntimeAuthoritySha256": f"sha256:{digest_bytes(active_raw)}",
            "evidenceDirectory": evidence_directory,
            "releaseShelfPosture": expected_posture,
            "candidate": candidate,
            "generationId": current.get("generationId"),
            "activationReceiptId": current.get("activationReceiptId"),
        }
        validate_complete_receipt(
            receipt,
            poststate=poststate,
            poststate_raw=poststate_raw,
        )
        atomic_write_new_at(state, COMPLETE_NAME, receipt)
        validate_complete_evidence(receipt)
        if COMPLETE_NAME in entries:
            _verify_directory_stable(state, state_before, "cutover state root")
        else:
            state.verify_links()
        return receipt


def absolute_directory(value: str, label: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        raise CutoverAttestationError(f"{label} must be absolute")
    if path.is_symlink():
        raise CutoverAttestationError(f"{label} must not be a symlink")
    resolved = path.resolve(strict=True)
    if not resolved.is_dir():
        raise CutoverAttestationError(f"{label} must be a real directory")
    return resolved


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare_parser = commands.add_parser("prepare")
    prepare_parser.add_argument("--shelf-root", required=True)
    prepare_parser.add_argument("--state-root", required=True)
    prepare_parser.add_argument("--source-head", required=True)
    inspect_parser = commands.add_parser("inspect-deploy-state")
    inspect_parser.add_argument("--shelf-root", required=True)
    inspect_parser.add_argument("--state-root", required=True)
    inspect_parser.add_argument("--source-head", required=True)
    request_parser = commands.add_parser("request-start")
    request_parser.add_argument("--shelf-root", required=True)
    request_parser.add_argument("--state-root", required=True)
    verify_parser = commands.add_parser("verify-outcome")
    verify_parser.add_argument("--shelf-root", required=True)
    verify_parser.add_argument("--state-root", required=True)
    handoff_parser = commands.add_parser("verify-handoff")
    handoff_parser.add_argument("--shelf-root", required=True)
    handoff_parser.add_argument("--state-root", required=True)
    snapshot_parser = commands.add_parser("snapshot-evidence")
    snapshot_parser.add_argument(
        "--kind", choices=tuple(sorted(EVIDENCE_NAMES)), required=True
    )
    snapshot_parser.add_argument("--source", required=True)
    snapshot_parser.add_argument("--output", required=True)
    readiness_parser = commands.add_parser("record-readiness")
    readiness_parser.add_argument("--output", required=True)
    readiness_parser.add_argument("--candidate-container-id", required=True)
    readiness_parser.add_argument("--candidate-container-name", required=True)
    readiness_parser.add_argument("--candidate-image-id", required=True)
    readiness_parser.add_argument("--http-status", type=int, required=True)
    readiness_parser.add_argument("--response-sha256", required=True)
    readiness_parser.add_argument("--running", choices=("true", "false"), required=True)
    readiness_parser.add_argument("--health", required=True)
    finalize_parser = commands.add_parser("finalize")
    finalize_parser.add_argument("--state-root", required=True)
    finalize_parser.add_argument("--compose-attestation", required=True)
    finalize_parser.add_argument("--publication-readiness-attestation", required=True)
    finalize_parser.add_argument("--postdeploy-attestation", required=True)
    finalize_parser.add_argument("--active-runtime-authority", required=True)
    finalize_parser.add_argument("--candidate-image-id", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "prepare":
            result = prepare(Path(args.shelf_root), Path(args.state_root), args.source_head)
        elif args.command == "inspect-deploy-state":
            result = inspect_deploy_state(
                Path(args.shelf_root),
                Path(args.state_root),
                args.source_head,
            )
        elif args.command == "request-start":
            result = request_start(
                Path(args.shelf_root),
                Path(args.state_root),
            )
        elif args.command == "verify-outcome":
            result = verify_outcome(
                Path(args.shelf_root),
                Path(args.state_root),
            )
        elif args.command == "verify-handoff":
            result = verify_handoff(
                Path(args.shelf_root),
                Path(args.state_root),
            )
        elif args.command == "snapshot-evidence":
            result = snapshot_evidence(
                args.kind,
                Path(args.source),
                Path(args.output),
            )
        elif args.command == "record-readiness":
            result = record_readiness(
                Path(args.output),
                candidate_container_id=args.candidate_container_id,
                candidate_container_name=args.candidate_container_name,
                candidate_image_id=args.candidate_image_id,
                http_status=args.http_status,
                response_sha256=args.response_sha256,
                running=args.running,
                health=args.health,
            )
        else:
            result = finalize(
                Path(args.state_root),
                Path(args.compose_attestation),
                Path(args.publication_readiness_attestation),
                Path(args.postdeploy_attestation),
                Path(args.active_runtime_authority),
                args.candidate_image_id,
            )
    except (CutoverAttestationError, OSError, KeyError, TypeError, ValueError) as exc:
        print(f"initial_release_shelf_cutover_attestation: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
