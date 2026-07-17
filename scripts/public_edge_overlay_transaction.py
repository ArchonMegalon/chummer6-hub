#!/usr/bin/env python3
"""Snapshot and restore the exact active public-edge overlay under the shared lock."""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import shutil
import stat
import sys
from pathlib import Path
from typing import Any


def _load_overlay_publisher():
    publisher_path = Path(__file__).resolve().with_name(
        "publish_public_edge_portal_overlay.py"
    )
    spec = importlib.util.spec_from_file_location(
        "chummer_public_edge_overlay_publisher",
        publisher_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load the public-edge overlay publisher")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    publisher_directory = str(publisher_path.parent)
    sys.path.insert(0, publisher_directory)
    try:
        spec.loader.exec_module(module)
    finally:
        try:
            sys.path.remove(publisher_directory)
        except ValueError:
            pass
    return module


overlay = _load_overlay_publisher()


CONTRACT_NAME = "chummer.public-edge.overlay-transaction/v1"
TRANSACTION_PHASES = (
    "prepared",
    "image_build_started",
    "image_built",
    "tunnel_drained",
    "portal_stopped",
    "overlay_activated",
    "portal_recreated",
    "tunnel_started",
)
IMAGE_ID_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
CONTAINER_ID_PATTERN = re.compile(r"^[0-9a-f]{64}$")
RUNTIME_PRIOR_STATE_FIELDS = {
    "expectedRuntimeProofBindSourceSha256",
    "priorImageTagId",
    "priorToolImageTagId",
    "priorPortalContainerId",
    "priorPortalImageId",
    "priorPortalExisted",
    "priorPortalWasRunning",
    "priorTunnelContainerId",
    "priorTunnelImageId",
    "priorTunnelExisted",
    "priorTunnelWasRunning",
}
DEPLOY_OVERLAY_AUTHORITY_FIELDS = {
    "stagingRoot",
    "backupRoot",
    "activationReceipt",
}


def validate_runtime_prior_state(value: object) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != RUNTIME_PRIOR_STATE_FIELDS:
        raise RuntimeError("overlay transaction runtime prior-state fields are invalid")
    state = dict(value)
    expected_proof_sha256 = state["expectedRuntimeProofBindSourceSha256"]
    if (
        not isinstance(expected_proof_sha256, str)
        or re.fullmatch(r"[0-9a-f]{64}", expected_proof_sha256) is None
    ):
        raise RuntimeError(
            "overlay transaction expected runtime proof bind-source SHA-256 is invalid"
        )
    for field in ("priorImageTagId", "priorToolImageTagId"):
        image_id = state[field]
        if not isinstance(image_id, str) or (
            image_id and IMAGE_ID_PATTERN.fullmatch(image_id) is None
        ):
            raise RuntimeError(f"overlay transaction {field} is invalid")
    for prefix in ("Portal", "Tunnel"):
        existed = state[f"prior{prefix}Existed"]
        was_running = state[f"prior{prefix}WasRunning"]
        container_id = state[f"prior{prefix}ContainerId"]
        image_id = state[f"prior{prefix}ImageId"]
        if not isinstance(existed, bool) or not isinstance(was_running, bool):
            raise RuntimeError(
                f"overlay transaction prior {prefix.lower()} state flags are invalid"
            )
        if not isinstance(container_id, str) or not isinstance(image_id, str):
            raise RuntimeError(
                f"overlay transaction prior {prefix.lower()} identities are invalid"
            )
        if existed:
            if (
                CONTAINER_ID_PATTERN.fullmatch(container_id) is None
                or IMAGE_ID_PATTERN.fullmatch(image_id) is None
            ):
                raise RuntimeError(
                    f"overlay transaction prior {prefix.lower()} identities are invalid"
                )
        elif container_id or image_id or was_running:
            raise RuntimeError(
                f"absent prior {prefix.lower()} cannot claim identity or running state"
            )
    return state


def _load_object(path: Path, *, label: str) -> dict[str, Any]:
    payload, _metadata = overlay.read_stable_regular_bytes(path, label=label)
    return overlay.strict_json_object_bytes(payload, label=label)


def _same_path(left: object, right: Path) -> bool:
    try:
        return overlay.normalized_absolute_path(Path(str(left))) == right
    except (OSError, RuntimeError, ValueError):
        return False


def _fingerprint_matches(expected: object, actual: dict[str, Any]) -> bool:
    return isinstance(expected, dict) and overlay.fingerprint_envelope_matches(
        expected,
        actual,
    )


def _identity_matches(expected: object, actual: dict[str, int]) -> bool:
    if not isinstance(expected, dict):
        return False
    return expected == actual


def _current_state(active_root: Path) -> tuple[bool, dict[str, Any], dict[str, int]]:
    try:
        active_root.lstat()
    except FileNotFoundError:
        return False, {}, {}
    overlay.assert_regular_overlay_tree(active_root, label="active root")
    return (
        True,
        overlay.overlay_tree_fingerprint(active_root, label="active root"),
        overlay.directory_identity(active_root, label="active root"),
    )


def _state_matches(
    *,
    expected_existed: bool,
    expected_fingerprint: object,
    expected_identity: object,
    active_root: Path,
) -> bool:
    actual_existed, actual_fingerprint, actual_identity = _current_state(active_root)
    if actual_existed != expected_existed:
        return False
    if not expected_existed:
        return True
    return _fingerprint_matches(
        expected_fingerprint,
        actual_fingerprint,
    ) and _identity_matches(expected_identity, actual_identity)


def snapshot(
    *,
    source_root: Path,
    active_root: Path,
    output: Path,
    shared_mutation_lock_token: str,
    runtime_prior_state: dict[str, Any] | None = None,
    staging_root: Path | None = None,
    backup_root: Path | None = None,
    activation_receipt: Path | None = None,
) -> dict[str, Any]:
    source_root = source_root.resolve()
    active_root = overlay.normalized_absolute_path(active_root)
    output = overlay.normalized_absolute_path(output)
    with overlay.public_edge_mutation_lock(
        activate=True,
        inherited_token=shared_mutation_lock_token,
    ):
        with overlay.overlay_publish_lock(source_root, active_root):
            overlay.assert_no_incomplete_activation_transaction(active_root)
            existed, fingerprint, identity = _current_state(active_root)
            prior_runtime = dict(runtime_prior_state or {})
            deploy_authority: dict[str, str] = {}
            if prior_runtime:
                prior_runtime = validate_runtime_prior_state(prior_runtime)
                if (
                    staging_root is None
                    or backup_root is None
                    or activation_receipt is None
                ):
                    raise RuntimeError(
                        "deploy overlay authority paths are required with runtime prior state"
                    )
                normalized_staging_root = overlay.normalized_absolute_path(staging_root)
                normalized_backup_root = overlay.normalized_absolute_path(backup_root)
                normalized_activation_receipt = overlay.normalized_absolute_path(
                    activation_receipt
                )
                if normalized_staging_root == active_root:
                    raise RuntimeError("deploy staging and active roots must be distinct")
                overlay.assert_no_symlink_components(
                    normalized_staging_root,
                    label="deploy staging root",
                )
                overlay.assert_no_symlink_components(
                    normalized_backup_root,
                    label="deploy backup root",
                )
                overlay.assert_no_symlink_components(
                    normalized_activation_receipt.parent,
                    label="deploy activation receipt parent",
                )
                deploy_authority = {
                    "stagingRoot": str(normalized_staging_root),
                    "backupRoot": str(normalized_backup_root),
                    "activationReceipt": str(normalized_activation_receipt),
                }
            elif any(
                value is not None
                for value in (staging_root, backup_root, activation_receipt)
            ):
                raise RuntimeError(
                    "deploy overlay authority paths require runtime prior state"
                )
            payload = {
                "contractName": CONTRACT_NAME,
                "operation": "snapshot",
                "status": "pass",
                "phase": "prepared",
                "sourceRoot": str(source_root),
                "activeRoot": str(active_root),
                "activeExisted": existed,
                "priorActiveFingerprint": fingerprint,
                "priorActiveIdentity": identity,
                "runtimePriorState": prior_runtime,
                "deployOverlayAuthority": deploy_authority,
            }
            overlay.atomic_write_json(output, payload)
            return payload


def _validated_snapshot(
    path: Path,
    *,
    source_root: Path,
    active_root: Path,
) -> dict[str, Any]:
    payload = _load_object(path, label="overlay transaction snapshot")
    if (
        payload.get("contractName") != CONTRACT_NAME
        or payload.get("operation") != "snapshot"
        or payload.get("status") != "pass"
        or not _same_path(payload.get("sourceRoot"), source_root)
        or not _same_path(payload.get("activeRoot"), active_root)
        or not isinstance(payload.get("activeExisted"), bool)
        or not isinstance(payload.get("priorActiveFingerprint"), dict)
        or not isinstance(payload.get("priorActiveIdentity"), dict)
        or payload.get("phase") not in TRANSACTION_PHASES
        or not isinstance(payload.get("runtimePriorState"), dict)
        or not isinstance(payload.get("deployOverlayAuthority", {}), dict)
    ):
        raise RuntimeError("overlay transaction snapshot contract is invalid")
    if payload["activeExisted"]:
        fingerprint = payload["priorActiveFingerprint"]
        identity = payload["priorActiveIdentity"]
        if (
            fingerprint.get("algorithm") != overlay.SOURCE_FINGERPRINT_ALGORITHM
            or not isinstance(fingerprint.get("aggregateSha256"), str)
            or len(fingerprint["aggregateSha256"]) != 64
            or not isinstance(fingerprint.get("fileCount"), int)
            or not identity
        ):
            raise RuntimeError("overlay transaction snapshot identity is invalid")
    elif payload["priorActiveFingerprint"] or payload["priorActiveIdentity"]:
        raise RuntimeError("absent prior overlay must not claim an identity")
    return payload


def validated_deploy_snapshot(
    path: Path,
    *,
    source_root: Path,
    active_root: Path,
) -> dict[str, Any]:
    payload = _validated_snapshot(
        path,
        source_root=source_root.resolve(),
        active_root=overlay.normalized_absolute_path(active_root),
    )
    payload["runtimePriorState"] = validate_runtime_prior_state(
        payload["runtimePriorState"]
    )
    authority = payload.get("deployOverlayAuthority")
    if not isinstance(authority, dict) or set(authority) != DEPLOY_OVERLAY_AUTHORITY_FIELDS:
        raise RuntimeError("deploy overlay authority contract is invalid")
    normalized_authority: dict[str, str] = {}
    for field in DEPLOY_OVERLAY_AUTHORITY_FIELDS:
        value = authority[field]
        if not isinstance(value, str) or not value or not Path(value).is_absolute():
            raise RuntimeError(f"deploy overlay authority {field} is invalid")
        try:
            normalized = overlay.normalized_absolute_path(Path(value))
        except (OSError, RuntimeError, ValueError) as exc:
            raise RuntimeError(f"deploy overlay authority {field} is invalid") from exc
        if str(normalized) != value:
            raise RuntimeError(f"deploy overlay authority {field} is not canonical")
        normalized_authority[field] = value
    if normalized_authority["stagingRoot"] == str(
        overlay.normalized_absolute_path(active_root)
    ):
        raise RuntimeError("deploy staging and active roots must be distinct")
    payload["deployOverlayAuthority"] = normalized_authority
    return payload


def prior_overlay_matches_snapshot(
    payload: dict[str, Any],
    *,
    active_root: Path,
) -> bool:
    activation_journal = overlay.activation_transaction_journal_path(
        overlay.normalized_absolute_path(active_root)
    )
    if activation_journal.exists() or activation_journal.is_symlink():
        return False
    return _state_matches(
        expected_existed=bool(payload["activeExisted"]),
        expected_fingerprint=payload["priorActiveFingerprint"],
        expected_identity=payload["priorActiveIdentity"],
        active_root=overlay.normalized_absolute_path(active_root),
    )


def mark_phase(
    *,
    source_root: Path,
    active_root: Path,
    journal_path: Path,
    phase: str,
    shared_mutation_lock_token: str,
) -> dict[str, Any]:
    source_root = source_root.resolve()
    active_root = overlay.normalized_absolute_path(active_root)
    journal_path = overlay.normalized_absolute_path(journal_path)
    if phase not in TRANSACTION_PHASES:
        raise RuntimeError("public-edge overlay transaction phase is invalid")
    with overlay.public_edge_mutation_lock(
        activate=True,
        inherited_token=shared_mutation_lock_token,
    ):
        with overlay.overlay_publish_lock(source_root, active_root):
            payload = _validated_snapshot(
                journal_path,
                source_root=source_root,
                active_root=active_root,
            )
            current_phase = str(payload.get("phase") or "")
            current_index = TRANSACTION_PHASES.index(current_phase)
            requested_index = TRANSACTION_PHASES.index(phase)
            if requested_index < current_index:
                raise RuntimeError("public-edge overlay transaction phase cannot move backward")
            if requested_index > current_index + 1:
                raise RuntimeError("public-edge overlay transaction phase cannot skip forward")
            payload["phase"] = phase
            overlay.atomic_write_json(journal_path, payload)
            return payload


def complete_transaction(
    *,
    source_root: Path,
    active_root: Path,
    journal_path: Path,
    shared_mutation_lock_token: str,
) -> dict[str, Any]:
    source_root = source_root.resolve()
    active_root = overlay.normalized_absolute_path(active_root)
    journal_path = overlay.normalized_absolute_path(journal_path)
    with overlay.public_edge_mutation_lock(
        activate=True,
        inherited_token=shared_mutation_lock_token,
    ):
        with overlay.overlay_publish_lock(source_root, active_root):
            payload = validated_deploy_snapshot(
                journal_path,
                source_root=source_root,
                active_root=active_root,
            )
            if payload.get("phase") != "tunnel_started":
                raise RuntimeError(
                    "public-edge overlay transaction cannot complete before tunnel start"
                )
            overlay.assert_no_incomplete_activation_transaction(active_root)
            journal_path.unlink()
            overlay.fsync_directory(journal_path.parent)
    return {
        "contractName": CONTRACT_NAME,
        "operation": "complete",
        "status": "pass",
        "journalRetired": True,
    }


def _activation_receipt_backup_hint(
    activation_receipt: Path,
    *,
    active_root: Path,
    backup_root: Path,
) -> Path | None:
    try:
        payload = _load_object(activation_receipt, label="overlay activation receipt")
    except (FileNotFoundError, OSError, RuntimeError):
        return None
    if (
        payload.get("contractName") != overlay.CONTRACT_NAME
        or payload.get("activateRequested") is not True
        or payload.get("activationAtomicCutover") is not True
        or not _same_path(payload.get("activeRoot"), active_root)
        or not _same_path(payload.get("backupRoot"), backup_root)
        or (payload.get("sharedMutationLock") or {}).get("status") != "held"
        or (payload.get("sharedMutationLock") or {}).get("inherited") is not True
    ):
        return None
    backup_value = str(payload.get("backupPath") or "").strip()
    if not backup_value:
        return None
    backup_path = overlay.normalized_absolute_path(Path(backup_value))
    try:
        relative = backup_path.relative_to(backup_root)
    except ValueError:
        return None
    if len(relative.parts) != 2 or relative.parts[-1] != "app":
        return None
    return backup_path


def _validated_backup_path(
    activation_receipt: Path,
    *,
    active_root: Path,
    backup_root: Path,
    expected_fingerprint: object,
    expected_identity: object,
) -> Path:
    # The durable prior-state journal, not a later success receipt, is rollback
    # authority. A crash after the atomic exchange can precede every publisher
    # receipt write, so locate the unique preserved inode under the fixed backup
    # root and treat a receipt path only as a non-authoritative hint.
    overlay.assert_no_symlink_components(backup_root, label="backup root")
    try:
        backup_root_stat = backup_root.lstat()
    except FileNotFoundError as exc:
        raise RuntimeError("preserved overlay backup root is missing") from exc
    if not stat.S_ISDIR(backup_root_stat.st_mode) or stat.S_ISLNK(
        backup_root_stat.st_mode
    ):
        raise RuntimeError("preserved overlay backup root is unsafe")

    hint = _activation_receipt_backup_hint(
        activation_receipt,
        active_root=active_root,
        backup_root=backup_root,
    )
    candidates: list[Path] = []
    for transaction_root in backup_root.iterdir():
        transaction_stat = transaction_root.lstat()
        if not stat.S_ISDIR(transaction_stat.st_mode) or stat.S_ISLNK(
            transaction_stat.st_mode
        ):
            raise RuntimeError("preserved overlay backup root contains an unsafe entry")
        candidate = transaction_root / "app"
        try:
            candidate.lstat()
        except FileNotFoundError:
            continue
        overlay.assert_regular_overlay_tree(
            candidate,
            label="preserved prior active root",
        )
        candidate_fingerprint = overlay.overlay_tree_fingerprint(
            candidate,
            label="preserved prior active root",
        )
        candidate_identity = overlay.directory_identity(
            candidate,
            label="preserved prior active root",
        )
        if _fingerprint_matches(
            expected_fingerprint,
            candidate_fingerprint,
        ) and _identity_matches(expected_identity, candidate_identity):
            candidates.append(candidate)

    if len(candidates) != 1:
        raise RuntimeError(
            "could not resolve one exact preserved prior overlay from the durable snapshot"
        )
    selected = candidates[0]
    if hint is not None and hint != selected:
        raise RuntimeError("overlay activation receipt backup hint conflicts with durable state")
    return selected


def _path_disposition(
    path: Path,
    *,
    prior_fingerprint: object,
    prior_identity: object,
    candidate_fingerprint: object,
    candidate_identity: object,
) -> str:
    try:
        path.lstat()
    except FileNotFoundError:
        return "missing"
    overlay.assert_regular_overlay_tree(path, label="activation recovery tree")
    fingerprint = overlay.overlay_tree_fingerprint(
        path,
        label="activation recovery tree",
    )
    identity = overlay.directory_identity(path, label="activation recovery tree")
    if _fingerprint_matches(prior_fingerprint, fingerprint) and _identity_matches(
        prior_identity,
        identity,
    ):
        return "prior"
    if _fingerprint_matches(candidate_fingerprint, fingerprint) and _identity_matches(
        candidate_identity,
        identity,
    ):
        return "candidate"
    return "unknown"


def _remove_recovery_candidate(path: Path) -> None:
    shutil.rmtree(path)
    overlay.fsync_directory(path.parent)
    try:
        path.parent.rmdir()
    except OSError:
        return
    overlay.fsync_directory(path.parent.parent)


def _recover_interrupted_activation_to_prior(
    *,
    snapshot: dict[str, Any],
    active_root: Path,
    staging_root: Path,
    backup_root: Path,
) -> str:
    overlay.assert_no_symlink_components(staging_root, label="deploy staging root")
    overlay.assert_no_symlink_components(backup_root, label="deploy backup root")
    journal_path = overlay.activation_transaction_journal_path(active_root)
    if not journal_path.exists() and not journal_path.is_symlink():
        return "not_required"
    activation = _load_object(
        journal_path,
        label="overlay activation transaction journal",
    )
    expected_existed = bool(snapshot["activeExisted"])
    prior_fingerprint = snapshot["priorActiveFingerprint"]
    prior_identity = snapshot["priorActiveIdentity"]
    candidate_fingerprint = activation.get("candidateFingerprint")
    candidate_identity = activation.get("candidateIdentity")
    if (
        activation.get("contractName")
        != overlay.ACTIVATION_TRANSACTION_CONTRACT_NAME
        or activation.get("status") != "prepared"
        or activation.get("mode") != "copy"
        or activation.get("preserveOldTree") is not True
        or activation.get("activeExisted") is not expected_existed
        or not _same_path(activation.get("activeRoot"), active_root)
        or not _same_path(activation.get("stagingRoot"), staging_root)
        or not _same_path(activation.get("candidateRoot"), staging_root)
        or not isinstance(candidate_fingerprint, dict)
        or not isinstance(candidate_identity, dict)
        or activation.get("priorActiveFingerprint") != prior_fingerprint
        or activation.get("priorActiveIdentity") != prior_identity
    ):
        raise RuntimeError(
            "overlay activation journal conflicts with durable prior-state authority"
        )

    old_destination_value = str(activation.get("oldTreeDestination") or "")
    old_destination: Path | None = None
    if expected_existed:
        if not old_destination_value:
            raise RuntimeError("overlay activation journal omitted its prior-tree destination")
        old_destination = overlay.normalized_absolute_path(
            Path(old_destination_value)
        )
        try:
            relative = old_destination.relative_to(backup_root)
        except ValueError as exc:
            raise RuntimeError(
                "overlay activation prior-tree destination escaped its backup root"
            ) from exc
        if len(relative.parts) != 2 or relative.parts[-1] != "app":
            raise RuntimeError(
                "overlay activation prior-tree destination is not canonical"
            )
        overlay.assert_no_symlink_components(
            old_destination,
            label="overlay activation prior-tree destination",
        )
    elif old_destination_value:
        raise RuntimeError(
            "overlay activation journal claims a prior-tree destination for prior absence"
        )

    locations = [active_root, staging_root]
    if old_destination is not None:
        locations.append(old_destination)

    def disposition(path: Path) -> str:
        return _path_disposition(
            path,
            prior_fingerprint=prior_fingerprint,
            prior_identity=prior_identity,
            candidate_fingerprint=candidate_fingerprint,
            candidate_identity=candidate_identity,
        )

    states = {path: disposition(path) for path in locations}
    if "unknown" in states.values():
        raise RuntimeError(
            "overlay activation recovery found a tree outside journal authority"
        )

    if expected_existed:
        prior_locations = [path for path, state in states.items() if state == "prior"]
        if len(prior_locations) != 1:
            raise RuntimeError(
                "overlay activation recovery could not resolve one exact prior tree"
            )
        prior_location = prior_locations[0]
        if prior_location != active_root:
            if states[active_root] != "candidate":
                raise RuntimeError(
                    "overlay activation recovery cannot exchange an unauthorised active tree"
                )
            overlay.atomic_exchange_overlay_roots(prior_location, active_root)
        if not _state_matches(
            expected_existed=True,
            expected_fingerprint=prior_fingerprint,
            expected_identity=prior_identity,
            active_root=active_root,
        ):
            raise RuntimeError(
                "overlay activation recovery did not restore the exact prior tree"
            )
    else:
        active_state = states[active_root]
        if active_state == "candidate":
            if states[staging_root] != "missing":
                raise RuntimeError(
                    "overlay activation recovery staging root is unexpectedly occupied"
                )
            overlay.atomic_move_overlay_root(active_root, staging_root)
        elif active_state != "missing":
            raise RuntimeError(
                "overlay activation recovery cannot restore prior active-root absence"
            )
        if active_root.exists() or active_root.is_symlink():
            raise RuntimeError(
                "overlay activation recovery did not restore prior active-root absence"
            )

    for path in locations:
        if path == active_root:
            continue
        current = disposition(path)
        if current == "candidate":
            _remove_recovery_candidate(path)
        elif current not in {"missing"}:
            raise RuntimeError(
                "overlay activation recovery retained an unexpected non-active tree"
            )

    journal_path.unlink()
    overlay.fsync_directory(journal_path.parent)
    overlay.assert_no_incomplete_activation_transaction(active_root)
    return "exact_prior_activation_state_restored"


def restore(
    *,
    source_root: Path,
    active_root: Path,
    backup_root: Path,
    snapshot_path: Path,
    activation_receipt: Path,
    output: Path,
    shared_mutation_lock_token: str,
) -> dict[str, Any]:
    source_root = source_root.resolve()
    active_root = overlay.normalized_absolute_path(active_root)
    backup_root = overlay.normalized_absolute_path(backup_root)
    output = overlay.normalized_absolute_path(output)
    prior = _validated_snapshot(
        snapshot_path,
        source_root=source_root,
        active_root=active_root,
    )
    deploy_authority: dict[str, str] | None = None
    if prior["runtimePriorState"]:
        prior = validated_deploy_snapshot(
            snapshot_path,
            source_root=source_root,
            active_root=active_root,
        )
        deploy_authority = prior["deployOverlayAuthority"]
        authoritative_backup_root = overlay.normalized_absolute_path(
            Path(deploy_authority["backupRoot"])
        )
        if backup_root != authoritative_backup_root:
            raise RuntimeError("overlay recovery backup root conflicts with its journal")
        backup_root = authoritative_backup_root
        activation_receipt = overlay.normalized_absolute_path(
            Path(deploy_authority["activationReceipt"])
        )
    expected_existed = bool(prior["activeExisted"])
    expected_fingerprint = prior["priorActiveFingerprint"]
    expected_identity = prior["priorActiveIdentity"]
    action = "already_restored"
    retired_cleanup_status = "not_applicable"

    with overlay.public_edge_mutation_lock(
        activate=True,
        inherited_token=shared_mutation_lock_token,
    ):
        with overlay.overlay_publish_lock(source_root, active_root):
            activation_recovery = "not_applicable"
            if deploy_authority is not None:
                activation_recovery = _recover_interrupted_activation_to_prior(
                    snapshot=prior,
                    active_root=active_root,
                    staging_root=overlay.normalized_absolute_path(
                        Path(deploy_authority["stagingRoot"])
                    ),
                    backup_root=backup_root,
                )
            if not _state_matches(
                expected_existed=expected_existed,
                expected_fingerprint=expected_fingerprint,
                expected_identity=expected_identity,
                active_root=active_root,
            ):
                if expected_existed:
                    backup_path = _validated_backup_path(
                        activation_receipt,
                        active_root=active_root,
                        backup_root=backup_root,
                        expected_fingerprint=expected_fingerprint,
                        expected_identity=expected_identity,
                    )
                    activation = overlay.activate_overlay_tree(
                        backup_path,
                        active_root,
                        mode="copy",
                        backup_root=None,
                    )
                    if activation.get("transactionCleanupStatus") != "complete":
                        raise RuntimeError(
                            "overlay rollback committed with an incomplete transaction journal"
                        )
                    action = "exact_prior_tree_restored"
                else:
                    existed, _fingerprint, _identity = _current_state(active_root)
                    if existed:
                        retired_path = overlay.retired_overlay_path(active_root)
                        overlay.require_same_filesystem(active_root, retired_path.parent)
                        overlay.atomic_move_overlay_root(active_root, retired_path)
                        overlay.fsync_directory(active_root.parent)
                        action = "prior_absence_restored"
                        try:
                            shutil.rmtree(retired_path)
                            retired_path.parent.rmdir()
                            overlay.fsync_directory(active_root.parent)
                            retired_cleanup_status = "removed"
                        except OSError:
                            retired_cleanup_status = "retained_for_manual_cleanup"

            overlay.assert_no_incomplete_activation_transaction(active_root)
            if not _state_matches(
                expected_existed=expected_existed,
                expected_fingerprint=expected_fingerprint,
                expected_identity=expected_identity,
                active_root=active_root,
            ):
                raise RuntimeError("overlay rollback did not restore the exact prior state")

            payload = {
                "contractName": CONTRACT_NAME,
                "operation": "restore",
                "status": "pass",
                "sourceRoot": str(source_root),
                "activeRoot": str(active_root),
                "priorActiveExisted": expected_existed,
                "action": action,
                "retiredCleanupStatus": retired_cleanup_status,
                "activationRecovery": activation_recovery,
                "exactPriorStateRestored": True,
            }
            overlay.atomic_write_json(output, payload)
            return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Snapshot or restore the exact public-edge overlay transaction boundary."
    )
    subparsers = parser.add_subparsers(dest="operation", required=True)
    snapshot_parser = subparsers.add_parser("snapshot")
    phase_parser = subparsers.add_parser("mark-phase")
    restore_parser = subparsers.add_parser("restore")
    complete_parser = subparsers.add_parser("complete")
    for command in (snapshot_parser, phase_parser, restore_parser, complete_parser):
        command.add_argument("--source-root", type=Path, required=True)
        command.add_argument("--active-root", type=Path, required=True)
        command.add_argument("--output", type=Path, required=True)
        command.add_argument("--shared-mutation-lock-token", required=True)
    restore_parser.add_argument("--backup-root", type=Path, required=True)
    restore_parser.add_argument("--snapshot", type=Path, required=True)
    restore_parser.add_argument("--activation-receipt", type=Path, required=True)
    snapshot_parser.add_argument("--prior-image-tag-id", default="")
    snapshot_parser.add_argument(
        "--expected-runtime-proof-bind-source-sha256",
        required=True,
    )
    snapshot_parser.add_argument("--prior-tool-image-tag-id", default="")
    snapshot_parser.add_argument("--prior-portal-container-id", default="")
    snapshot_parser.add_argument("--prior-portal-image-id", default="")
    snapshot_parser.add_argument("--prior-portal-existed", choices=("0", "1"), required=True)
    snapshot_parser.add_argument("--prior-portal-was-running", choices=("0", "1"), required=True)
    snapshot_parser.add_argument("--prior-tunnel-container-id", default="")
    snapshot_parser.add_argument("--prior-tunnel-image-id", default="")
    snapshot_parser.add_argument("--prior-tunnel-existed", choices=("0", "1"), required=True)
    snapshot_parser.add_argument("--prior-tunnel-was-running", choices=("0", "1"), required=True)
    snapshot_parser.add_argument("--staging-root", type=Path, required=True)
    snapshot_parser.add_argument("--backup-root", type=Path, required=True)
    snapshot_parser.add_argument("--activation-receipt", type=Path, required=True)
    phase_parser.add_argument("--phase", choices=TRANSACTION_PHASES, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.operation == "snapshot":
            payload = snapshot(
                source_root=args.source_root,
                active_root=args.active_root,
                output=args.output,
                shared_mutation_lock_token=args.shared_mutation_lock_token,
                runtime_prior_state={
                    "expectedRuntimeProofBindSourceSha256": (
                        args.expected_runtime_proof_bind_source_sha256
                    ),
                    "priorImageTagId": args.prior_image_tag_id,
                    "priorToolImageTagId": args.prior_tool_image_tag_id,
                    "priorPortalContainerId": args.prior_portal_container_id,
                    "priorPortalImageId": args.prior_portal_image_id,
                    "priorPortalExisted": args.prior_portal_existed == "1",
                    "priorPortalWasRunning": args.prior_portal_was_running == "1",
                    "priorTunnelContainerId": args.prior_tunnel_container_id,
                    "priorTunnelImageId": args.prior_tunnel_image_id,
                    "priorTunnelExisted": args.prior_tunnel_existed == "1",
                    "priorTunnelWasRunning": args.prior_tunnel_was_running == "1",
                },
                staging_root=args.staging_root,
                backup_root=args.backup_root,
                activation_receipt=args.activation_receipt,
            )
        elif args.operation == "mark-phase":
            payload = mark_phase(
                source_root=args.source_root,
                active_root=args.active_root,
                journal_path=args.output,
                phase=args.phase,
                shared_mutation_lock_token=args.shared_mutation_lock_token,
            )
        elif args.operation == "complete":
            payload = complete_transaction(
                source_root=args.source_root,
                active_root=args.active_root,
                journal_path=args.output,
                shared_mutation_lock_token=args.shared_mutation_lock_token,
            )
        else:
            payload = restore(
                source_root=args.source_root,
                active_root=args.active_root,
                backup_root=args.backup_root,
                snapshot_path=args.snapshot,
                activation_receipt=args.activation_receipt,
                output=args.output,
                shared_mutation_lock_token=args.shared_mutation_lock_token,
            )
    except Exception as exc:
        payload = {
            "contractName": CONTRACT_NAME,
            "operation": args.operation,
            "status": "fail",
            "exactPriorStateRestored": False,
            "warning": str(exc),
        }
        if args.operation not in {"mark-phase", "complete"}:
            try:
                overlay.atomic_write_json(
                    overlay.normalized_absolute_path(args.output),
                    payload,
                )
            except Exception:
                pass
    print(json.dumps(payload, sort_keys=True, allow_nan=False))
    return 0 if payload.get("status") == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
