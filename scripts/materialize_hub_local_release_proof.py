#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import json
import os
import sys
from pathlib import Path


def iso_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _stable_payload(payload: dict) -> dict:
    stable = dict(payload)
    stable.pop("generated_at", None)
    stable.pop("generatedAt", None)
    return stable


def _load_existing_payload(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return loaded if isinstance(loaded, dict) else None


def _parse_int_env(*names: str, default: int) -> int:
    for name in names:
        raw = str(os.environ.get(name) or "").strip()
        if not raw:
            continue
        try:
            value = int(raw)
        except ValueError:
            continue
        if value >= 0:
            return value
    return default


def _parse_iso_timestamp(raw_value: str | None) -> dt.datetime | None:
    if not raw_value:
        return None
    normalized = raw_value.strip()
    if not normalized:
        return None
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _payload_is_fresh(payload: dict, *, max_age_seconds: int, max_future_skew_seconds: int) -> bool:
    raw_generated_at = str(payload.get("generatedAt") or payload.get("generated_at") or "").strip() or None
    generated_at = _parse_iso_timestamp(raw_generated_at)
    if generated_at is None:
        return False

    age_seconds = int((dt.datetime.now(dt.timezone.utc) - generated_at).total_seconds())
    if age_seconds < 0:
        return abs(age_seconds) <= max_future_skew_seconds
    return age_seconds <= max_age_seconds


def main() -> int:
    if len(sys.argv) != 6:
        print(
            "usage: materialize_hub_local_release_proof.py <out_path> <base_url> <compose_file> <timeout_seconds> <skip_rebuild>",
            file=sys.stderr,
        )
        return 1

    out_path_text, base_url, compose_file, timeout_seconds, skip_rebuild = sys.argv[1:]
    out_path = Path(out_path_text)
    proof_max_age_seconds = _parse_int_env(
        "CHUMMER_VERIFY_RELEASE_PROOF_MAX_AGE_SECONDS",
        "CHUMMER_RELEASE_PROOF_MAX_AGE_SECONDS",
        default=604800,
    )
    proof_max_future_skew_seconds = _parse_int_env(
        "CHUMMER_VERIFY_RELEASE_PROOF_MAX_FUTURE_SKEW_SECONDS",
        "CHUMMER_RELEASE_PROOF_MAX_FUTURE_SKEW_SECONDS",
        default=300,
    )

    successor_queue_packages = [
        {
            "package_id": "next90-m102-hub-desktop-native-trust",
            "milestone_id": 102,
            "frontier_id": 2897065929,
            "repo": "chummer6-hub",
            "status": "complete",
            "completion_action": "verify_closed_package_only",
            "do_not_reopen_reason": "M102 chummer6-hub desktop-native trust is complete; future shards must verify this receipt, registry row, queue row, and design-queue row instead of reopening the claim/install/update/rollback/support continuation package.",
            "landed_commit": "160af58f",
            "title": "Unify claim, install, update, and support recovery into one desktop-native flow",
            "allowed_paths": [
                "Chummer.Run.Api",
                "scripts",
                "tests",
            ],
            "owned_surfaces": [
                "desktop_native_claim_and_recovery",
                "support_followthrough:install_truth",
            ],
            "exit_criterion": "Claim, update, rollback, recovery, and support followthrough happen from the installer or app, not as browser ritual.",
        },
        {
            "package_id": "next90-m107-hub-artifact-factory",
            "milestone_id": 107,
            "frontier_id": 1421219975,
            "repo": "chummer6-hub",
            "status": "complete",
            "completion_action": "verify_closed_package_only",
            "do_not_reopen_reason": "M107 chummer6-hub artifact factory orchestration is complete; future shards must verify this receipt, registry row, Fleet queue row, and design queue row instead of reopening the artifact-factory orchestration and public proof shelf release-bundles package.",
            "landed_commit": "b9e6b52e",
            "title": "Stand up artifact-factory orchestration for release, support, and publication bundles",
            "allowed_paths": [
                "Chummer.Run.Api",
                "scripts",
                "tests",
            ],
            "owned_surfaces": [
                "artifact_factory:orchestration",
                "public_proof_shelf:release_bundles",
            ],
            "exit_criterion": "Release, fix, support, and publication explainers can ship as approved video, audio, preview, and packet bundles from the same underlying release and support truth.",
        },
        {
            "package_id": "next90-m105-hub-workspace-continuity",
            "milestone_id": 105,
            "frontier_id": 4623636482,
            "repo": "chummer6-hub",
            "status": "complete",
            "completion_action": "verify_closed_package_only",
            "do_not_reopen_reason": "M105 chummer6-hub workspace continuity is complete; future shards must verify the workspace restore receipt, registry row, queue row, and design-queue row instead of reopening the workspace restore and entitlement conflict receipt package.",
            "landed_commit": "4d4b3856",
            "title": "Emit provenance and conflict receipts for workspace restore and continuity",
            "allowed_paths": [
                "Chummer.Run.Api",
                "scripts",
                "tests",
            ],
            "owned_surfaces": [
                "workspace_restore:provenance",
                "entitlement_sync:conflict_receipts",
            ],
            "exit_criterion": "Claimed users can restore workspace, entitlement, last context, and safe continuation with explicit stale and conflict posture.",
        },
    ]

    payload = {
        "contract_name": "chummer6-hub.local_release_proof",
        "package_repo": "chummer6-hub",
        "status": "passed",
        "successor_queue_package": {
            "package_id": "next90-m105-hub-workspace-continuity",
            "milestone_id": 105,
            "frontier_id": 4623636482,
            "repo": "chummer6-hub",
            "status": "complete",
            "completion_action": "verify_closed_package_only",
            "do_not_reopen_reason": "M105 chummer6-hub workspace continuity is complete; future shards must verify the workspace restore receipt, registry row, queue row, and design-queue row instead of reopening the workspace restore and entitlement conflict receipt package.",
            "landed_commit": "4d4b3856",
            "title": "Emit provenance and conflict receipts for workspace restore and continuity",
            "allowed_paths": [
                "Chummer.Run.Api",
                "scripts",
                "tests",
            ],
            "owned_surfaces": [
                "workspace_restore:provenance",
                "entitlement_sync:conflict_receipts",
            ],
            "exit_criterion": "Claimed users can restore workspace, entitlement, last context, and safe continuation with explicit stale and conflict posture.",
        },
        "successor_queue_packages": successor_queue_packages,
        "successor_queue_packages_by_id": {
            package["package_id"]: dict(package)
            for package in successor_queue_packages
        },
        "base_url": base_url,
        "compose_file": compose_file,
        "playwright_timeout_seconds": int(timeout_seconds),
        "edge_rebuild_skipped": skip_rebuild.lower() in {"1", "true"},
        "journeys_passed": [
            "install_claim_restore_continue",
            "build_explain_publish",
            "campaign_session_recover_recap",
            "report_cluster_release_notify",
            "organize_community_and_close_loop",
        ],
        "proof_routes": [
            "/downloads/install/avalonia-linux-x64-installer",
            "/home/access",
            "/home/work",
            "/account/access",
            "/account/work",
            "/account/support",
            "/contact",
            "/downloads",
            "/downloads/install/avalonia-osx-arm64-installer",
            "/downloads/install/avalonia-win-x64-installer",
        ],
        "proof_receipts": [
            {
                "receipt_id": "desktop_native_claim_and_recovery",
                "package_id": "next90-m102-hub-desktop-native-trust",
                "milestone_id": 102,
                "frontier_id": 2897065929,
                "summary": "Claim and recovery continuation now have installer/app-native receipts: guided setup is the default, claim codes are recovery fallback only, and the claimed desktop app can call the grant-bound continuation endpoint without a browser redemption ritual.",
                "routes": [
                    "/downloads/install/avalonia-linux-x64-installer/continue.json",
                    "/api/v1/install-linking/continuation",
                    "/account/access",
                ],
                "surfaces": [
                    "desktop_native_claim_and_recovery",
                    "install_claim_restore_continue",
                    "claimed_install_continuation",
                ],
            },
            {
                "receipt_id": "support_followthrough:install_truth",
                "package_id": "next90-m102-hub-desktop-native-trust",
                "milestone_id": 102,
                "frontier_id": 2897065929,
                "summary": "Support follow-through carries installed build, current release, channel, head, platform, fallback, update, and rollback truth on the same install rail used by the desktop client.",
                "routes": [
                    "/api/v1/install-linking/continuation",
                    "/api/v1/install-linking/continuation/support",
                    "/account/support",
                    "/contact",
                ],
                "surfaces": [
                    "support_followthrough:install_truth",
                    "support_case_install_readiness",
                    "desktop_update_rollback_recovery",
                ],
            },
            {
                "receipt_id": "public_proof_shelf:release_bundles",
                "package_id": "next90-m107-hub-artifact-factory",
                "milestone_id": 107,
                "frontier_id": 1421219975,
                "summary": "Approved release source packs now launch recipe-backed artifact jobs whose preview, caption, packet, audio, and video outputs bind onto stable public release-bundle shelf refs instead of one-off provider flows.",
                "routes": [
                    "/downloads/install/avalonia-linux-x64-installer",
                    "/artifacts/release-bundles/avalonia-linux-x64-installer",
                    "/artifacts/release-bundles/avalonia-linux-x64-installer/preview_card",
                ],
                "surfaces": [
                    "artifact_factory:orchestration",
                    "public_proof_shelf:release_bundles",
                    "build_explain_publish",
                ],
            },
            {
                "receipt_id": "workspace_restore:provenance",
                "package_id": "next90-m105-hub-workspace-continuity",
                "milestone_id": 105,
                "frontier_id": 4623636482,
                "summary": "Workspace restore continuity emits provenance receipts and typed recovery actions for claimed installs, recent artifacts, rule environments, and restore inventory on the shared account workspace surfaces.",
                "routes": [
                    "/home/work",
                    "/account/work",
                    "/account/access",
                ],
                "surfaces": [
                    "workspace_restore:provenance",
                    "workspace_restore:recoverable_actions",
                    "workspace_restore",
                    "account_workspace_detail",
                ],
            },
            {
                "receipt_id": "entitlement_sync:conflict_receipts",
                "package_id": "next90-m105-hub-workspace-continuity",
                "milestone_id": 105,
                "frontier_id": 4623636482,
                "summary": "Entitlement drift, stale claims, missing grants, and continue-blocking conflicts emit recoverable receipts and typed account-access actions on the same restore lane instead of falling back to support folklore.",
                "routes": [
                    "/home/work",
                    "/account/work",
                    "/account/access",
                    "/downloads",
                ],
                "surfaces": [
                    "entitlement_sync:conflict_receipts",
                    "entitlement_sync:recoverable_actions",
                    "entitlement_sync",
                    "workspace_restore",
                ],
            },
        ],
    }

    existing_payload = _load_existing_payload(out_path)
    if (
        existing_payload is not None
        and _stable_payload(existing_payload) == _stable_payload(payload)
        and _payload_is_fresh(
            existing_payload,
            max_age_seconds=proof_max_age_seconds,
            max_future_skew_seconds=proof_max_future_skew_seconds,
        )
    ):
        print(f"hub local proof unchanged and still fresh: {out_path}")
        return 0

    generated_at = iso_now()
    payload["generated_at"] = generated_at
    payload["generatedAt"] = generated_at

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"wrote hub local proof: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
