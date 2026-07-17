#!/usr/bin/env python3
"""Snapshot and restore the exact active public-edge overlay under the shared lock."""

from __future__ import annotations

import argparse
import importlib.util
import json
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
    "tunnel_drained",
    "portal_stopped",
    "overlay_activated",
    "portal_recreated",
    "tunnel_started",
)


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
                "runtimePriorState": dict(runtime_prior_state or {}),
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
            if TRANSACTION_PHASES.index(phase) < TRANSACTION_PHASES.index(current_phase):
                raise RuntimeError("public-edge overlay transaction phase cannot move backward")
            payload["phase"] = phase
            overlay.atomic_write_json(journal_path, payload)
            return payload


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
    for command in (snapshot_parser, phase_parser, restore_parser):
        command.add_argument("--source-root", type=Path, required=True)
        command.add_argument("--active-root", type=Path, required=True)
        command.add_argument("--output", type=Path, required=True)
        command.add_argument("--shared-mutation-lock-token", required=True)
    restore_parser.add_argument("--backup-root", type=Path, required=True)
    restore_parser.add_argument("--snapshot", type=Path, required=True)
    restore_parser.add_argument("--activation-receipt", type=Path, required=True)
    snapshot_parser.add_argument("--prior-image-tag-id", default="")
    snapshot_parser.add_argument("--prior-portal-container-id", default="")
    snapshot_parser.add_argument("--prior-portal-image-id", default="")
    snapshot_parser.add_argument("--prior-portal-existed", choices=("0", "1"), required=True)
    snapshot_parser.add_argument("--prior-portal-was-running", choices=("0", "1"), required=True)
    snapshot_parser.add_argument("--prior-tunnel-container-id", default="")
    snapshot_parser.add_argument("--prior-tunnel-existed", choices=("0", "1"), required=True)
    snapshot_parser.add_argument("--prior-tunnel-was-running", choices=("0", "1"), required=True)
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
                    "priorImageTagId": args.prior_image_tag_id,
                    "priorPortalContainerId": args.prior_portal_container_id,
                    "priorPortalImageId": args.prior_portal_image_id,
                    "priorPortalExisted": args.prior_portal_existed == "1",
                    "priorPortalWasRunning": args.prior_portal_was_running == "1",
                    "priorTunnelContainerId": args.prior_tunnel_container_id,
                    "priorTunnelExisted": args.prior_tunnel_existed == "1",
                    "priorTunnelWasRunning": args.prior_tunnel_was_running == "1",
                },
            )
        elif args.operation == "mark-phase":
            payload = mark_phase(
                source_root=args.source_root,
                active_root=args.active_root,
                journal_path=args.output,
                phase=args.phase,
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
        if args.operation != "mark-phase":
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
