from __future__ import annotations

import datetime as dt
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys

import pytest


SCRIPT = Path(__file__).parents[1] / "scripts" / "verify_post_activation_acceptance.py"
SCRIPTS = SCRIPT.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location("verify_post_activation_acceptance", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

CAMPAIGN_PRODUCER = importlib.import_module("accept_live_campaign_release")
CAMPAIGN_V2_PRODUCER = importlib.import_module(
    "verify_governed_campaign_e2e_receipt"
)
HORIZON_PRODUCER = importlib.import_module("verify_horizon_live_readiness")

OBSERVED_AT = dt.datetime(2026, 7, 21, 12, 2, tzinfo=dt.timezone.utc)
TARGET = {
    "releaseVersion": "run-test",
    "generationId": "gen-test",
    "manifestSha256": "a" * 64,
    "decisionSha256": "c" * 64,
    "snapshotSha256": "b" * 64,
    "targetPointerSha256": "d" * 64,
}
COMPARED_FIELDS = [
    "releaseVersion",
    "channel",
    "releaseStatus",
    "rolloutState",
    "supportabilityState",
    "availablePlatforms",
    "primaryHeadByPlatform",
    "artifactCount",
    "downloadAccessPosture",
    "knownIssueSummary",
    "manifestSha256",
    "registryCommit",
    "releaseDecisionStatus",
    "releaseDecisionSha256",
]


def _canonical(payload: object) -> bytes:
    return (
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        + "\n"
    ).encode()


def _write(path: Path, payload: object, *, canonical: bool = True) -> str:
    raw = _canonical(payload) if canonical else (json.dumps(payload, indent=2) + "\n").encode()
    path.write_bytes(raw)
    path.chmod(0o600)
    return hashlib.sha256(raw).hexdigest()


def _utc(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _finalization(completed_at: dt.datetime) -> dict[str, object]:
    return {
        "contractName": "chummer.staged-release-owner-finalization/v1",
        "contractVersion": 1,
        "status": "preview_ready",
        "releaseVersion": TARGET["releaseVersion"],
        "generationId": TARGET["generationId"],
        "stageReceiptId": "stage-receipt-test",
        "manifestSha256": TARGET["manifestSha256"],
        "releaseScopeDecisionSha256": "1" * 64,
        "releaseScopeVerificationSha256": "2" * 64,
        "exactIncomingDesktopScope": (
            "avalonia:macos:osx-arm64,blazor-desktop:macos:osx-arm64"
        ),
        "snapshotSha256": TARGET["snapshotSha256"],
        "decisionSha256": TARGET["decisionSha256"],
        "authorityRevisionId": "auth-" + "e" * 64,
        "targetPointerSha256": TARGET["targetPointerSha256"],
        "completedAtUtc": _utc(completed_at),
    }


def _convergence(role: str, generated_at: dt.datetime) -> dict[str, object]:
    route = (
        f"/api/v1/public/release-truth/g/{TARGET['generationId']}"
        if role == "generation"
        else "/api/v1/public/release-truth"
    )
    release_truth = {
        "contractName": "chummer.release-truth-projection/v1",
        "releaseVersion": TARGET["releaseVersion"],
        "channel": "preview",
        "releaseStatus": "published",
        "rolloutState": "complete",
        "supportabilityState": "supported",
        "availablePlatforms": ["windows"],
        "primaryHeadByPlatform": {"windows": "artifact-test"},
        "artifactCount": 1,
        "downloadAccessPosture": "open_public",
        "knownIssueSummary": "No blocking known issues.",
        "manifestSha256": TARGET["manifestSha256"],
        "registryCommit": "4" * 40,
        "releaseDecisionStatus": "preview_ready",
        "releaseDecisionSha256": TARGET["decisionSha256"],
    }
    if role == "generation":
        checked_routes = set(
            MODULE.CONVERGENCE_HELPERS.generation_routes(TARGET["generationId"])
        )
        checked_routes.add(
            f"/downloads/g/{TARGET['generationId']}/install/artifact-test"
        )
    else:
        checked_routes = set(MODULE.CONVERGENCE_HELPERS.DEFAULT_ROUTES)
        checked_routes.add("/downloads/install/artifact-test")
    checked_routes = sorted(checked_routes)
    return {
        "contractName": "chummer.live-release-convergence/v1",
        "contractVersion": 1,
        "generatedAtUtc": _utc(generated_at),
        "verificationMode": "committed_public",
        "status": "pass",
        "mismatchCount": 0,
        "failureCount": 0,
        "mismatches": [],
        "failures": [],
        "releaseVersion": TARGET["releaseVersion"],
        "manifestSha256": TARGET["manifestSha256"],
        "releaseDecisionStatus": "preview_ready",
        "authoritySnapshotSha256": TARGET["snapshotSha256"],
        "releaseDecisionSha256": TARGET["decisionSha256"],
        "authorityRoute": route,
        "checkedRouteCount": len(checked_routes),
        "checkedRoutes": checked_routes,
        "comparedFields": COMPARED_FIELDS,
        "releaseTruth": release_truth,
    }


def _evidence(
    kind: str,
    evidence_id: str,
    generated_at: dt.datetime,
    *,
    status: str = "ready",
    readiness: bool | None = True,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "contractName": "chummer.post-activation-evidence/v1",
        "contractVersion": 1,
        "status": status,
        "secretRedacted": True,
        "evidenceId": evidence_id,
        "evidenceKind": kind,
        "generatedAtUtc": _utc(generated_at),
        "releaseBinding": dict(TARGET),
        "claims": [
            {
                "claimId": f"{kind}-claim",
                "status": "pass",
                "evidenceSha256": "3" * 64,
            }
        ],
    }
    if readiness is not None:
        payload["operationalReadinessClaimAllowed"] = readiness
    return payload


def _horizon_receipt(
    generated_at: dt.datetime,
    *,
    convergence_sha256: str,
    manifest_file_sha256: str,
) -> dict[str, object]:
    horizon_rows = [
        {
            "horizonId": horizon_id,
            "route": route,
            "sourceStatus": "source_working",
            "deploymentStatus": "raw_http_reachable",
            "configurationStatus": "not_applicable",
            "operationalStatus": "unverified",
            "governanceStatus": "cleared",
            "httpStatus": 200,
            "contentType": "text/html",
            "responseSha256": hashlib.sha256(route.encode()).hexdigest(),
            "identityBindingStatus": "not_exposed",
        }
        for horizon_id, route in sorted(MODULE.HORIZON_ROUTES.items())
    ]
    horizon_ids = sorted(MODULE.HORIZON_ROUTES)
    capability_rows = [
        {
            "horizonId": horizon_ids[index % len(horizon_ids)],
            "capabilityId": f"capability-{index:02d}",
            "sourceStatus": "source_working",
            "deploymentStatus": "raw_http_observed",
            "configurationStatus": "configured",
            "operationalStatus": "unverified",
            "governanceStatus": "cleared",
            "httpStatus": 200,
            "responseSha256": hashlib.sha256(f"capability-{index}".encode()).hexdigest(),
            "identityBindingStatus": "not_exposed",
            "publicCatalogObserved": index < 8,
        }
        for index in range(20)
    ]
    fence = {
        "route": "/api/v1/public/release-truth",
        "releaseVersion": TARGET["releaseVersion"],
        "manifestSha256": TARGET["manifestSha256"],
        "releaseDecisionSha256": TARGET["decisionSha256"],
        "releaseDecisionStatus": "preview_ready",
        "authoritySnapshotSha256": TARGET["snapshotSha256"],
        "releaseTruthSha256": "5" * 64,
        "responseSha256": "6" * 64,
    }
    return {
        "contractName": HORIZON_PRODUCER.CONTRACT_NAME,
        "contractVersion": HORIZON_PRODUCER.CONTRACT_VERSION,
        "generatedAtUtc": _utc(generated_at),
        "status": "attention_required",
        "operationalReadinessClaimAllowed": False,
        "releaseBinding": {
            "releaseVersion": TARGET["releaseVersion"],
            "generationId": TARGET["generationId"],
            "manifestSha256": TARGET["manifestSha256"],
            "releaseDecisionStatus": "preview_ready",
            "releaseDecisionSha256": TARGET["decisionSha256"],
            "authoritySnapshotSha256": TARGET["snapshotSha256"],
        },
        "inputBindings": {
            "sourceReadinessSha256": "7" * 64,
            "committedPublicConvergenceSha256": convergence_sha256,
            "generationManifestFileSha256": manifest_file_sha256,
        },
        "probePolicy": {
            "baseOrigin": "https://chummer.run",
            "methods": ["GET"],
            "sameOriginOnly": True,
            "redirectsFollowed": False,
            "runtimeRequestsPerformed": True,
            "providerCallsPerformed": False,
            "quotaConsumed": False,
            "mutationsPerformed": False,
            "secretRedacted": True,
        },
        "currentFence": {
            "preCurrent": dict(fence),
            "postCurrent": dict(fence),
            "stable": True,
        },
        "catalogObservations": {
            "internalPublicSafe": {
                "route": "/api/internal/horizons/capabilities?publicSafe=true",
                "httpStatus": 200,
                "contentType": "application/json",
                "responseSha256": "a" * 64,
                "identityBindingStatus": "not_exposed",
                "rowCount": 20,
            },
            "public": {
                "route": "/api/v1/public/horizons/capabilities",
                "httpStatus": 200,
                "contentType": "application/json",
                "responseSha256": "b" * 64,
                "identityBindingStatus": "not_exposed",
                "rowCount": 8,
            },
        },
        "summary": {
            "horizonCount": 15,
            "capabilityCount": 20,
            "deploymentReachableCount": 15,
            "configurationConfiguredCount": 20,
            "configurationDisabledCount": 0,
            "operationalReadyCount": 0,
            "governanceClearedCount": 20,
            "publicCapabilityCount": 8,
        },
        "horizons": horizon_rows,
        "capabilities": capability_rows,
    }


def _campaign_state(role: str) -> dict[str, object]:
    return {
        "cookies": [
            {
                "name": "session",
                "value": f"opaque-{role}",
                "domain": ".chummer.run",
                "path": "/",
            }
        ],
        "origins": [
            {
                "origin": "https://chummer.run",
                "localStorage": [{"name": "state", "value": role}],
            }
        ],
    }


def _campaign_permit(now: dt.datetime) -> dict[str, object]:
    return {
        "contractName": CAMPAIGN_PRODUCER.PERMIT_CONTRACT,
        "contractVersion": 1,
        "status": "approved",
        "secretRedacted": True,
        "permitId": "permit-acceptance-golden",
        "issuedAtUtc": _utc(now - dt.timedelta(minutes=1)),
        "expiresAtUtc": _utc(now + dt.timedelta(minutes=20)),
        "allowedOrigin": CAMPAIGN_PRODUCER.PRODUCTION_ORIGIN,
        "allowedActions": list(CAMPAIGN_PRODUCER.ALLOWED_ACTIONS),
        "releaseBinding": dict(TARGET),
    }


def _opaque(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


def _campaign_v2_permit(
    now: dt.datetime,
    *,
    release_binding: dict[str, str],
) -> dict[str, object]:
    action_rows = []
    forward_total = 0
    cleanup_total = 0
    for action_id in CAMPAIGN_V2_PRODUCER.ACTION_IDS:
        catalog = CAMPAIGN_V2_PRODUCER.ACTION_CATALOG[action_id]
        forward_total += catalog["forwardWriteLimit"]
        cleanup_total += catalog["cleanupWriteLimit"]
        action_rows.append(
            {
                "actionId": action_id,
                "role": catalog["role"],
                "attemptLimit": catalog["attemptLimit"],
                "forwardWriteLimit": catalog["forwardWriteLimit"],
                "cleanupWriteLimit": catalog["cleanupWriteLimit"],
                "compensator": catalog["compensator"],
            }
        )
    return {
        "contractName": CAMPAIGN_V2_PRODUCER.PERMIT_CONTRACT,
        "contractVersion": 2,
        "status": "approved",
        "secretRedacted": True,
        "permitId": "campaign-v2-permit",
        "issuedAtUtc": _utc(now - dt.timedelta(minutes=2)),
        "forwardExpiresAtUtc": _utc(now + dt.timedelta(minutes=10)),
        "cleanupExpiresAtUtc": _utc(now + dt.timedelta(minutes=30)),
        "allowedOrigin": CAMPAIGN_V2_PRODUCER.PRODUCTION_ORIGIN,
        "releaseBinding": dict(release_binding),
        "ownerAuthorization": {
            "authorizationRefHmac": _opaque("owner-authorization"),
            "authorizedByRefHmac": _opaque("release-owner"),
            "authorizedAtUtc": _utc(now - dt.timedelta(minutes=3)),
            "producerIndependent": True,
        },
        "canaryCampaignRefHmac": _opaque("canary-campaign"),
        "roleAccountRefHmacs": {
            role: _opaque(f"account:{role}")
            for role in CAMPAIGN_V2_PRODUCER.ROLES
        },
        "actions": action_rows,
        "totalForwardWriteLimit": forward_total,
        "totalCleanupWriteLimit": cleanup_total,
        "nonceRefHmac": _opaque("permit-nonce"),
        "replayLedgerRefHmac": _opaque("permit-replay-ledger"),
        "irreversibleActionsAllowed": False,
        "notificationsAllowed": False,
    }


def _campaign_v2_receipt(
    permit: dict[str, object],
    *,
    permit_sha256: str,
    status: str,
    generated_at: dt.datetime,
    input_bindings: dict[str, str],
) -> dict[str, object]:
    pass_run = status == "pass"
    cleanup_required = status == "cleanup_required"
    credentialed = status != "not_run"
    release_binding = dict(permit["releaseBinding"])
    steps: list[dict[str, object]] = []
    for index, action_id in enumerate(CAMPAIGN_V2_PRODUCER.ACTION_IDS):
        catalog = CAMPAIGN_V2_PRODUCER.ACTION_CATALOG[action_id]
        mutating = catalog["mutating"]
        compensator = catalog["compensator"]
        attempted = pass_run or (cleanup_required and index == 0)
        forward_writes = catalog["forwardWriteLimit"] if attempted else 0
        cleanup_writes = (
            catalog["cleanupWriteLimit"] if pass_run and forward_writes else 0
        )
        steps.append(
            {
                "actionId": action_id,
                "role": catalog["role"],
                "status": (
                    "pass" if pass_run else ("blocked" if attempted else "not_run")
                ),
                "mutating": mutating,
                "attempts": 1 if attempted else 0,
                "forwardWrites": forward_writes,
                "cleanupWrites": cleanup_writes,
                "assertionPassed": pass_run,
                "compensator": compensator,
                "compensatorAvailableBeforeWrite": bool(
                    forward_writes and compensator
                ),
                "serverIdempotencyKeyHmac": (
                    _opaque(f"forward-idempotency:{action_id}")
                    if forward_writes
                    else None
                ),
                "revisionPreconditionHmac": (
                    _opaque(f"forward-revision:{action_id}")
                    if forward_writes
                    else None
                ),
                "journalIntentSha256": (
                    _opaque(f"forward-journal:{action_id}")
                    if forward_writes
                    else None
                ),
                "evidenceSha256": (
                    _opaque(f"action-evidence:{action_id}") if attempted else None
                ),
            }
        )

    cleanup_entries = []
    if pass_run:
        written_steps = [step for step in steps if step["forwardWrites"] == 1]
        for sequence, step in enumerate(reversed(written_steps), start=1):
            action_id = str(step["actionId"])
            cleanup_entries.append(
                {
                    "sequence": sequence,
                    "actionId": action_id,
                    "resourceRefHmac": (
                        permit["canaryCampaignRefHmac"]
                        if action_id == "campaign_create_or_join"
                        else _opaque(f"resource:{action_id}")
                    ),
                    "idempotencyKeyHmac": _opaque(f"cleanup-idempotency:{action_id}"),
                    "revisionPreconditionHmac": _opaque(f"cleanup-revision:{action_id}"),
                    "intentEvidenceSha256": step["journalIntentSha256"],
                    "responseEvidenceSha256": _opaque(f"cleanup-response:{action_id}"),
                    "result": "cleaned",
                    "acknowledged": True,
                }
            )

    clean = status != "cleanup_required"
    snapshot = {**release_binding, "responseSha256": _opaque("current-response")}
    browser_policy = {
        field: False for field in CAMPAIGN_V2_PRODUCER.BROWSER_POLICY_FIELDS
    }
    browser_policy.update(
        {
            "allowedOrigin": CAMPAIGN_V2_PRODUCER.PRODUCTION_ORIGIN,
            "sameOriginOnly": True,
            "stopOnApprovalBoundary": True,
            "stopOnIdentityMismatch": True,
            "stopOnMfa": True,
            "stopOnCaptcha": True,
            "stopOnCloudflare": True,
        }
    )
    return {
        "contractName": CAMPAIGN_V2_PRODUCER.RECEIPT_CONTRACT,
        "contractVersion": 2,
        "receiptId": f"campaign-v2-{status}",
        "generatedAtUtc": _utc(generated_at),
        "status": status,
        "secretRedacted": True,
        "operationalReadinessClaimAllowed": pass_run,
        "releaseBinding": release_binding,
        "inputBindings": {**input_bindings, "mutationPermitSha256": permit_sha256},
        "browserPolicy": browser_policy,
        "currentFence": (
            {
                "preCurrent": None,
                "postCurrent": None,
                "stable": False,
            }
            if status == "not_run"
            else {
                "preCurrent": dict(snapshot),
                "postCurrent": dict(snapshot),
                "stable": True,
            }
        ),
        "accounts": [
            {
                "role": role,
                "accountRefHmac": permit["roleAccountRefHmacs"][role],
                "browserContextRefHmac": _opaque(f"browser-context:{role}"),
                "browserSessionRefHmac": _opaque(f"browser-session:{role}"),
                "visibleIdentityMatched": True,
            }
            for role in CAMPAIGN_V2_PRODUCER.ROLES
        ],
        "journey": {
            "credentialedAttemptPerformed": credentialed,
            "steps": steps,
        },
        "permit": {
            "permitSha256": permit_sha256,
            "permitId": permit["permitId"],
            "nonceRefHmac": permit["nonceRefHmac"],
            "replayLedgerRefHmac": permit["replayLedgerRefHmac"],
            "nonceClaimed": credentialed,
            "replayDetected": False,
            "forwardStartedAtUtc": (
                _utc(generated_at - dt.timedelta(seconds=30))
                if credentialed
                else None
            ),
            "cleanupCompletedAtUtc": (
                _utc(generated_at - dt.timedelta(seconds=5)) if pass_run else None
            ),
        },
        "cleanup": {
            "journal": {
                "pathRefHmac": _opaque("cleanup-journal"),
                "mode": 0o600,
                "appendOnly": True,
                "intentBeforeWrite": True,
                "resultAfterResponse": True,
            },
            "strategy": {
                "reverseOrder": True,
                "resumable": True,
                "finallyGuaranteed": True,
                "runOwnedIdsOnly": True,
                "broadDeletesUsed": False,
                "preExistingContentChanged": False,
            },
            "entries": cleanup_entries,
            "postconditions": {
                "compensatorsAcknowledged": clean,
                "canonicalPostMatchesPre": clean,
                "residualCampaignRows": 0 if clean else 1,
                "residualAuditRows": 0,
                "residualRequestReceiptRows": 0,
                "quotaUnchanged": clean,
                "providerCallCount": 0,
                "notificationCount": 0,
            },
        },
        "browserOoda": {
            "site": CAMPAIGN_V2_PRODUCER.PRODUCTION_ORIGIN,
            "requestedActions": list(CAMPAIGN_V2_PRODUCER.ACTION_IDS),
            "completedActions": (
                list(CAMPAIGN_V2_PRODUCER.ACTION_IDS) if pass_run else []
            ),
            "safeContext": "production_isolated_contexts",
            "qualityGate": (
                "pass" if pass_run else ("not_run" if status == "not_run" else "blocked")
            ),
            "finalUrl": "https://chummer.run/account" if pass_run else None,
            "stopCondition": (
                "none" if pass_run else ("not_started" if status == "not_run" else "blocker")
            ),
            "evidenceSha256s": (
                [step["evidenceSha256"] for step in steps] if pass_run else []
            ),
            "notificationOutcome": "none",
            "irreversibleAttemptCount": 0,
        },
        "blockers": ["governed_test_blocker"] if status == "blocked" else [],
        "failures": [],
    }


def _manifest(release_truth: dict[str, object]) -> dict[str, object]:
    truth = json.loads(json.dumps(release_truth))
    return {
        "version": TARGET["releaseVersion"],
        "channel": "preview",
        "status": "published",
        "rolloutState": "complete",
        "supportabilityState": "supported",
        "downloadAccessPosture": "open_public",
        "knownIssueSummary": "No blocking known issues.",
        "manifestSha256": TARGET["manifestSha256"],
        "registryCommit": "4" * 40,
        "releaseDecisionStatus": "preview_ready",
        "releaseDecisionSha256": TARGET["decisionSha256"],
        "artifactCount": 1,
        "availablePlatforms": ["windows"],
        "primaryHeadByPlatform": {"windows": "artifact-test"},
        "downloads": [
            {
                "id": "artifact-test",
                "platformId": "windows",
                "head": "artifact-test",
                "installAccessClass": "open_public",
            }
        ],
        "releaseTruth": truth,
    }


def _bundle(
    tmp_path: Path,
    *,
    kinds: tuple[str, ...] = (
        "horizon_live_readiness",
        "multi_account_live_journey",
    ),
    observed_at: dt.datetime = OBSERVED_AT,
    campaign_v2_status: str | None = None,
) -> dict[str, object]:
    workspace = tmp_path / "workspace"
    workspace.mkdir(mode=0o700, parents=True)
    workspace.chmod(0o700)
    completed_at = observed_at - dt.timedelta(minutes=3)
    generation_at = observed_at - dt.timedelta(minutes=2)
    evidence_at = observed_at - dt.timedelta(minutes=1)
    finalization = workspace / "finalization.json"
    generation = workspace / "generation.json"
    current = workspace / "current.json"
    manifest = workspace / "release-manifest.json"
    generation_payload = _convergence("generation", generation_at)
    current_payload = _convergence("current", observed_at)
    finalization_payload = _finalization(completed_at)
    manifest_payload = _manifest(generation_payload["releaseTruth"])
    bundle: dict[str, object] = {
        "workspace": workspace,
        "finalization": finalization,
        "finalization_sha": _write(finalization, finalization_payload),
        "finalization_payload": finalization_payload,
        "generation": generation,
        "generation_sha": _write(generation, generation_payload),
        "generation_payload": generation_payload,
        "current": current,
        "current_sha": _write(current, current_payload),
        "current_payload": current_payload,
        "manifest": manifest,
        "manifest_sha": _write(manifest, manifest_payload),
        "manifest_payload": manifest_payload,
        "evidence": {},
        "evidence_payloads": {},
        "producer_receipts": {},
        "producer_receipt_payloads": {},
        "producer_permits": {},
        "producer_permit_payloads": {},
        "observed_at": observed_at,
    }
    for index, kind in enumerate(kinds):
        path = workspace / f"evidence-{kind}.json"
        if kind == "horizon_live_readiness":
            producer_path = workspace / "horizon-live-readiness-receipt.json"
            producer_payload = _horizon_receipt(
                evidence_at,
                convergence_sha256=bundle["generation_sha"],
                manifest_file_sha256=bundle["manifest_sha"],
            )
            producer_digest = _write(producer_path, producer_payload)
            producer_raw = producer_path.read_bytes()
            payload = HORIZON_PRODUCER.build_post_activation_evidence(
                producer_payload,
                producer_raw,
                evidence_id=f"evidence-{index}",
                target_pointer_sha256=TARGET["targetPointerSha256"],
            )
            digest = _write(path, payload)
            bundle["producer_receipts"][kind] = (  # type: ignore[index]
                producer_path,
                producer_digest,
            )
            bundle["producer_receipt_payloads"][kind] = producer_payload  # type: ignore[index]
        elif kind == "multi_account_live_journey":
            if campaign_v2_status is not None:
                permit_path = workspace / "campaign-mutation-permit-v2.json"
                permit_payload = _campaign_v2_permit(
                    evidence_at,
                    release_binding=dict(TARGET),
                )
                permit_digest = _write(permit_path, permit_payload)
                producer_path = workspace / "campaign-e2e-receipt-v2.json"
                producer_payload = _campaign_v2_receipt(
                    permit_payload,
                    permit_sha256=permit_digest,
                    status=campaign_v2_status,
                    generated_at=evidence_at,
                    input_bindings={
                        "ownerFinalizationReceiptSha256": bundle["finalization_sha"],
                        "generationConvergenceSha256": bundle["generation_sha"],
                        "generationManifestFileSha256": bundle["manifest_sha"],
                    },
                )
                producer_digest = _write(producer_path, producer_payload)
                if campaign_v2_status in {"pass", "cleanup_required"}:
                    passed = campaign_v2_status == "pass"
                    payload = {
                        "contractName": CAMPAIGN_V2_PRODUCER.EVIDENCE_CONTRACT,
                        "contractVersion": 1,
                        "status": "pass" if passed else "attention_required",
                        "secretRedacted": True,
                        "evidenceId": producer_payload["receiptId"],
                        "evidenceKind": CAMPAIGN_V2_PRODUCER.EVIDENCE_KIND,
                        "generatedAtUtc": producer_payload["generatedAtUtc"],
                        "releaseBinding": producer_payload["releaseBinding"],
                        "claims": [
                            {
                                "claimId": CAMPAIGN_V2_PRODUCER.OUTER_CLAIM_ID,
                                "status": "pass" if passed else "attention_required",
                                "evidenceSha256": producer_digest,
                            }
                        ],
                        "operationalReadinessClaimAllowed": passed,
                    }
                else:
                    validation = CAMPAIGN_V2_PRODUCER.validate_payloads(
                        producer_payload,
                        permit_payload,
                        permit_sha256=permit_digest,
                        observed_at=observed_at,
                    )
                    payload = CAMPAIGN_V2_PRODUCER.build_outer_evidence(
                        producer_payload,
                        validation,
                    )
                digest = _write(path, payload)
                bundle["producer_receipts"][kind] = (  # type: ignore[index]
                    producer_path,
                    producer_digest,
                )
                bundle["producer_receipt_payloads"][kind] = producer_payload  # type: ignore[index]
                bundle["producer_permits"][kind] = (  # type: ignore[index]
                    permit_path,
                    permit_digest,
                )
                bundle["producer_permit_payloads"][kind] = permit_payload  # type: ignore[index]
                bundle["evidence"][kind] = (path, digest)  # type: ignore[index]
                bundle["evidence_payloads"][kind] = payload  # type: ignore[index]
                continue
            storage_states: dict[str, tuple[Path, str]] = {}
            for role in sorted(CAMPAIGN_PRODUCER.ROLES):
                state_path = workspace / f"storage-{role}.json"
                storage_states[role] = (
                    state_path,
                    _write(state_path, _campaign_state(role)),
                )
            permit_path = workspace / "campaign-mutation-permit.json"
            permit_digest = _write(permit_path, _campaign_permit(evidence_at))
            payload = CAMPAIGN_PRODUCER.build_evidence(
                workspace=workspace,
                finalization_receipt=finalization,
                finalization_sha256=bundle["finalization_sha"],
                storage_states=storage_states,
                mutation_permit=permit_path,
                mutation_permit_sha256=permit_digest,
                evidence_id=f"evidence-{index}",
                output=path,
                observed_at=evidence_at,
            )
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
        else:
            payload = _evidence(kind, f"evidence-{index}", evidence_at)
            digest = _write(path, payload)
        bundle["evidence"][kind] = (path, digest)  # type: ignore[index]
        bundle["evidence_payloads"][kind] = payload  # type: ignore[index]
    return bundle


def _rebind_horizon_producer_inputs(bundle: dict[str, object]) -> None:
    kind = "horizon_live_readiness"
    producer_path, _ = bundle["producer_receipts"][kind]
    producer_payload = bundle["producer_receipt_payloads"][kind]
    producer_payload["inputBindings"]["committedPublicConvergenceSha256"] = bundle[
        "generation_sha"
    ]
    producer_payload["inputBindings"]["generationManifestFileSha256"] = bundle[
        "manifest_sha"
    ]
    producer_digest = _write(producer_path, producer_payload)
    bundle["producer_receipts"][kind] = (producer_path, producer_digest)

    evidence_path, _ = bundle["evidence"][kind]
    evidence_id = bundle["evidence_payloads"][kind]["evidenceId"]
    evidence = HORIZON_PRODUCER.build_post_activation_evidence(
        producer_payload,
        producer_path.read_bytes(),
        evidence_id=evidence_id,
        target_pointer_sha256=TARGET["targetPointerSha256"],
    )
    bundle["evidence_payloads"][kind] = evidence
    bundle["evidence"][kind] = (evidence_path, _write(evidence_path, evidence))


def _rebind_campaign_v2_producer_receipt(bundle: dict[str, object]) -> None:
    kind = "multi_account_live_journey"
    producer_path, _ = bundle["producer_receipts"][kind]
    producer_payload = bundle["producer_receipt_payloads"][kind]
    producer_digest = _write(producer_path, producer_payload)
    bundle["producer_receipts"][kind] = (producer_path, producer_digest)

    evidence_path, _ = bundle["evidence"][kind]
    evidence = bundle["evidence_payloads"][kind]
    evidence["claims"][0]["evidenceSha256"] = producer_digest
    bundle["evidence"][kind] = (evidence_path, _write(evidence_path, evidence))


def _verify(bundle: dict[str, object], *, output: Path | None = None):
    workspace = bundle["workspace"]
    assert isinstance(workspace, Path)
    return MODULE.verify(
        workspace=workspace,
        finalization_receipt=bundle["finalization"],
        finalization_sha256=bundle["finalization_sha"],
        generation_convergence=bundle["generation"],
        generation_convergence_sha256=bundle["generation_sha"],
        current_convergence=bundle["current"],
        current_convergence_sha256=bundle["current_sha"],
        release_manifest=bundle["manifest"],
        release_manifest_file_sha256=bundle["manifest_sha"],
        required_evidence=bundle["evidence"],
        producer_receipts=bundle["producer_receipts"],
        producer_permits=bundle["producer_permits"],
        output=output or workspace / "acceptance.json",
        observed_at=bundle["observed_at"],
    )


def _cli_args(bundle: dict[str, object], output: Path) -> list[str]:
    evidence = bundle["evidence"]
    producer_receipts = bundle["producer_receipts"]
    producer_permits = bundle["producer_permits"]
    assert isinstance(evidence, dict)
    assert isinstance(producer_receipts, dict)
    assert isinstance(producer_permits, dict)
    args = [
        "--workspace",
        str(bundle["workspace"]),
        "--finalization-receipt",
        str(bundle["finalization"]),
        "--expected-finalization-sha256",
        str(bundle["finalization_sha"]),
        "--generation-convergence",
        str(bundle["generation"]),
        "--expected-generation-convergence-sha256",
        str(bundle["generation_sha"]),
        "--current-convergence",
        str(bundle["current"]),
        "--expected-current-convergence-sha256",
        str(bundle["current_sha"]),
        "--release-manifest",
        str(bundle["manifest"]),
        "--expected-release-manifest-file-sha256",
        str(bundle["manifest_sha"]),
    ]
    for kind, (path, digest) in evidence.items():
        args.extend(["--require-evidence", f"{kind}={path}"])
        args.extend(["--evidence-sha256", f"{kind}={digest}"])
    for kind, (path, digest) in producer_receipts.items():
        args.extend(["--producer-receipt", f"{kind}={path}"])
        args.extend(["--producer-receipt-sha256", f"{kind}={digest}"])
    for kind, (path, digest) in producer_permits.items():
        args.extend(["--producer-permit", f"{kind}={path}"])
        args.extend(["--producer-permit-sha256", f"{kind}={digest}"])
    return [*args, "--output", str(output)]


def test_actual_producers_validate_but_keep_aggregate_attention_required(tmp_path: Path):
    kinds = ("horizon_live_readiness", "multi_account_live_journey")
    bundle = _bundle(tmp_path, kinds=kinds)
    output = bundle["workspace"] / "acceptance.json"

    receipt = _verify(bundle, output=output)

    assert receipt["status"] == "attention_required"
    assert receipt["requiredEvidenceKinds"] == sorted(kinds)
    assert receipt["evidenceCount"] == 2
    assert output.read_bytes() == _canonical(receipt)
    assert os.stat(output).st_mode & 0o777 == 0o600
    assert set(receipt["inputDigests"]) == {
        "ownerFinalization",
        "generationConvergence",
        "currentConvergence",
        "releaseManifest",
    }
    rows = {row["evidenceKind"]: row for row in receipt["evidence"]}
    assert rows["horizon_live_readiness"]["provenanceStatus"] == (
        "structural_attention_receipt_bound_unverified"
    )
    assert len(rows["horizon_live_readiness"]["producerReceiptSha256"]) == 64
    assert rows["multi_account_live_journey"]["provenanceStatus"] == (
        "unverified_preflight_attention_only"
    )
    assert all(row["accepted"] is False for row in rows.values())


def test_aggregate_horizon_schema_matches_canonical_verifier() -> None:
    assert MODULE.HORIZON_RECEIPT_CONTRACT == HORIZON_PRODUCER.CONTRACT_NAME
    assert MODULE.HORIZON_EXPECTED_HORIZON_COUNT == (
        HORIZON_PRODUCER.EXPECTED_HORIZON_COUNT
    )
    assert MODULE.HORIZON_EXPECTED_CAPABILITY_COUNT == (
        HORIZON_PRODUCER.EXPECTED_CAPABILITY_COUNT
    )
    assert MODULE.HORIZON_ROUTES == HORIZON_PRODUCER.HORIZON_ROUTES
    assert MODULE.HORIZON_RECEIPT_FIELDS == HORIZON_PRODUCER.TOP_LEVEL_FIELDS
    assert MODULE.HORIZON_RELEASE_FIELDS == HORIZON_PRODUCER.RELEASE_FIELDS
    assert MODULE.HORIZON_INPUT_FIELDS == HORIZON_PRODUCER.INPUT_FIELDS
    assert MODULE.HORIZON_POLICY_FIELDS == HORIZON_PRODUCER.POLICY_FIELDS
    assert MODULE.HORIZON_FENCE_FIELDS == HORIZON_PRODUCER.FENCE_FIELDS
    assert MODULE.HORIZON_FENCE_SNAPSHOT_FIELDS == (
        HORIZON_PRODUCER.FENCE_SNAPSHOT_FIELDS
    )
    assert MODULE.HORIZON_SUMMARY_FIELDS == HORIZON_PRODUCER.SUMMARY_FIELDS
    assert MODULE.HORIZON_ROW_FIELDS == HORIZON_PRODUCER.HORIZON_FIELDS
    assert MODULE.HORIZON_CAPABILITY_FIELDS == HORIZON_PRODUCER.CAPABILITY_FIELDS
    assert MODULE.HORIZON_CATALOG_FIELDS == (
        HORIZON_PRODUCER.CATALOG_OBSERVATIONS_FIELDS
    )
    assert MODULE.HORIZON_CATALOG_OBSERVATION_FIELDS == (
        HORIZON_PRODUCER.CATALOG_OBSERVATION_FIELDS
    )


def test_governed_campaign_v2_pass_is_rejected_while_producer_authority_is_disabled(
    tmp_path: Path,
):
    assert CAMPAIGN_V2_PRODUCER.LIVE_PASS_AUTHORIZED is False
    assert MODULE.CAMPAIGN_V2_LIVE_PASS_AUTHORIZED is False
    bundle = _bundle(tmp_path, campaign_v2_status="pass")

    with pytest.raises(
        MODULE.AcceptanceError,
        match="native pass is disabled by producer authority",
    ):
        _verify(bundle)


@pytest.mark.parametrize("native_status", ["not_run", "blocked"])
def test_governed_campaign_v2_non_pass_native_status_requires_attention(
    tmp_path: Path,
    native_status: str,
):
    bundle = _bundle(tmp_path, campaign_v2_status=native_status)

    receipt = _verify(bundle)

    campaign = next(
        row
        for row in receipt["evidence"]
        if row["evidenceKind"] == "multi_account_live_journey"
    )
    assert receipt["status"] == "attention_required"
    assert campaign["status"] == "attention_required"
    assert campaign["accepted"] is False
    assert campaign["provenanceStatus"] == (
        f"governed_v2_{native_status}_receipt_and_permit_bound"
    )


def test_governed_campaign_v2_not_run_accepts_truthful_unobserved_fence(
    tmp_path: Path,
):
    bundle = _bundle(tmp_path, campaign_v2_status="not_run")
    producer = bundle["producer_receipt_payloads"]["multi_account_live_journey"]
    assert producer["currentFence"] == {
        "preCurrent": None,
        "postCurrent": None,
        "stable": False,
    }

    receipt = _verify(bundle)

    campaign = next(
        row
        for row in receipt["evidence"]
        if row["evidenceKind"] == "multi_account_live_journey"
    )
    assert campaign["status"] == "attention_required"
    assert campaign["accepted"] is False
    assert campaign["provenanceStatus"] == (
        "governed_v2_not_run_receipt_and_permit_bound"
    )


def test_governed_campaign_v2_outer_id_must_bind_native_receipt_id(tmp_path: Path):
    bundle = _bundle(tmp_path, campaign_v2_status="not_run")
    kind = "multi_account_live_journey"
    path, _ = bundle["evidence"][kind]
    envelope = bundle["evidence_payloads"][kind]
    envelope["evidenceId"] = "unbound-receipt-alias"
    bundle["evidence"][kind] = (path, _write(path, envelope))

    with pytest.raises(MODULE.AcceptanceError, match="producer receipt identity"):
        _verify(bundle)


def test_governed_campaign_v2_synthetic_cleanup_required_is_rejected(
    tmp_path: Path,
):
    bundle = _bundle(tmp_path, campaign_v2_status="cleanup_required")

    with pytest.raises(
        MODULE.AcceptanceError,
        match="failed authoritative validation",
    ):
        _verify(bundle)


@pytest.mark.parametrize(
    ("mapping_name", "label"),
    [
        ("producer_receipts", "producer receipt"),
        ("producer_permits", "producer permit"),
    ],
)
def test_governed_campaign_v2_receipt_and_permit_digest_tamper_is_rejected(
    tmp_path: Path,
    mapping_name: str,
    label: str,
):
    bundle = _bundle(tmp_path, campaign_v2_status="not_run")
    path, _ = bundle[mapping_name]["multi_account_live_journey"]
    path.write_bytes(path.read_bytes() + b" ")

    with pytest.raises(MODULE.AcceptanceError, match=rf"{label} SHA-256 mismatch"):
        _verify(bundle)


@pytest.mark.parametrize(
    "field",
    [
        "ownerFinalizationReceiptSha256",
        "generationConvergenceSha256",
        "generationManifestFileSha256",
    ],
)
def test_governed_campaign_v2_input_bindings_must_match_aggregate_bytes(
    tmp_path: Path,
    field: str,
):
    bundle = _bundle(tmp_path, campaign_v2_status="not_run")
    producer = bundle["producer_receipt_payloads"]["multi_account_live_journey"]
    producer["inputBindings"][field] = "f" * 64
    _rebind_campaign_v2_producer_receipt(bundle)

    with pytest.raises(
        MODULE.AcceptanceError,
        match="inputBindings do not bind aggregate bytes",
    ):
        _verify(bundle)


def test_governed_campaign_v2_current_fence_drift_is_rejected(tmp_path: Path):
    bundle = _bundle(tmp_path, campaign_v2_status="pass")
    producer = bundle["producer_receipt_payloads"]["multi_account_live_journey"]
    producer["currentFence"]["postCurrent"]["responseSha256"] = "f" * 64
    _rebind_campaign_v2_producer_receipt(bundle)

    with pytest.raises(MODULE.AcceptanceError, match="CURRENT fence is not stable"):
        _verify(bundle)


def test_governed_campaign_v2_schema_drift_is_rejected(tmp_path: Path):
    bundle = _bundle(tmp_path, campaign_v2_status="not_run")
    producer = bundle["producer_receipt_payloads"]["multi_account_live_journey"]
    producer["unexpected"] = True
    _rebind_campaign_v2_producer_receipt(bundle)

    with pytest.raises(MODULE.AcceptanceError, match="unexpected field set"):
        _verify(bundle)


@pytest.mark.parametrize(
    "kind",
    ["horizon_live_readiness", "multi_account_live_journey"],
)
def test_arbitrary_ready_envelopes_are_rejected(tmp_path: Path, kind: str):
    bundle = _bundle(tmp_path)
    path, _ = bundle["evidence"][kind]
    payload = bundle["evidence_payloads"][kind]
    payload["status"] = "ready"
    payload["operationalReadinessClaimAllowed"] = True
    for claim in payload["claims"]:
        claim["status"] = "pass"
    bundle["evidence"][kind] = (path, _write(path, payload))

    with pytest.raises(
        MODULE.AcceptanceError,
        match="producer-exact|producer authority",
    ):
        _verify(bundle)


def test_horizon_claim_must_bind_pinned_producer_receipt_bytes(tmp_path: Path):
    bundle = _bundle(tmp_path)
    kind = "horizon_live_readiness"
    path, _ = bundle["evidence"][kind]
    payload = bundle["evidence_payloads"][kind]
    payload["claims"][0]["evidenceSha256"] = "f" * 64
    bundle["evidence"][kind] = (path, _write(path, payload))

    with pytest.raises(MODULE.AcceptanceError, match="does not bind"):
        _verify(bundle)


@pytest.mark.parametrize(
    "field",
    [
        "committedPublicConvergenceSha256",
        "generationManifestFileSha256",
    ],
)
def test_horizon_receipt_input_bindings_must_match_aggregate_bytes(
    tmp_path: Path,
    field: str,
):
    bundle = _bundle(tmp_path)
    kind = "horizon_live_readiness"
    producer_path, _ = bundle["producer_receipts"][kind]
    producer_payload = bundle["producer_receipt_payloads"][kind]
    producer_payload["inputBindings"][field] = "f" * 64
    producer_digest = _write(producer_path, producer_payload)
    bundle["producer_receipts"][kind] = (producer_path, producer_digest)

    evidence_path, _ = bundle["evidence"][kind]
    evidence = bundle["evidence_payloads"][kind]
    evidence["claims"][0]["evidenceSha256"] = producer_digest
    bundle["evidence"][kind] = (evidence_path, _write(evidence_path, evidence))

    with pytest.raises(MODULE.AcceptanceError, match="inputBindings do not bind"):
        _verify(bundle)


def test_horizon_receipt_cannot_self_authorize_mutation(tmp_path: Path):
    bundle = _bundle(tmp_path)
    kind = "horizon_live_readiness"
    producer_path, _ = bundle["producer_receipts"][kind]
    producer_payload = bundle["producer_receipt_payloads"][kind]
    producer_payload["probePolicy"]["mutationsPerformed"] = True
    producer_digest = _write(producer_path, producer_payload)
    bundle["producer_receipts"][kind] = (producer_path, producer_digest)

    evidence_path, _ = bundle["evidence"][kind]
    evidence = bundle["evidence_payloads"][kind]
    evidence["claims"][0]["evidenceSha256"] = producer_digest
    bundle["evidence"][kind] = (evidence_path, _write(evidence_path, evidence))

    with pytest.raises(MODULE.AcceptanceError, match="not read-only"):
        _verify(bundle)


def test_campaign_preflight_claim_ids_are_fixed(tmp_path: Path):
    bundle = _bundle(tmp_path)
    kind = "multi_account_live_journey"
    path, _ = bundle["evidence"][kind]
    payload = bundle["evidence_payloads"][kind]
    payload["claims"][0]["claimId"] = "caller_authored_ready_claim"
    bundle["evidence"][kind] = (path, _write(path, payload))

    with pytest.raises(MODULE.AcceptanceError, match="producer-exact"):
        _verify(bundle)


def test_missing_horizon_producer_receipt_is_rejected(tmp_path: Path):
    bundle = _bundle(tmp_path)
    bundle["producer_receipts"] = {}

    with pytest.raises(MODULE.AcceptanceError, match="provenance policy"):
        _verify(bundle)


@pytest.mark.parametrize(
    "kinds",
    [
        ("horizon_live_readiness",),
        ("multi_account_live_journey",),
        (
            "horizon_live_readiness",
            "multi_account_live_journey",
            "operator_requested_probe",
        ),
    ],
)
def test_flagship_v1_requires_exact_evidence_kind_policy(
    tmp_path: Path, kinds: tuple[str, ...]
):
    bundle = _bundle(tmp_path, kinds=kinds)

    with pytest.raises(MODULE.AcceptanceError, match="flagship v1 denominator"):
        _verify(bundle)


@pytest.mark.parametrize(
    ("status", "readiness"),
    [("attention_required", True), ("ready", False)],
)
def test_evidence_cannot_widen_current_producer_authority(
    tmp_path: Path, status: str, readiness: bool | None
):
    bundle = _bundle(tmp_path)
    kind = "horizon_live_readiness"
    path, _ = bundle["evidence"][kind]
    payload = bundle["evidence_payloads"][kind]
    payload["status"] = status
    payload["operationalReadinessClaimAllowed"] = readiness
    bundle["evidence"][kind] = (path, _write(path, payload))

    with pytest.raises(MODULE.AcceptanceError, match="producer authority"):
        _verify(bundle)


def test_operational_readiness_flag_is_required(tmp_path: Path):
    bundle = _bundle(tmp_path)
    kind = "horizon_live_readiness"
    path, _ = bundle["evidence"][kind]
    payload = bundle["evidence_payloads"][kind]
    payload.pop("operationalReadinessClaimAllowed")
    bundle["evidence"][kind] = (path, _write(path, payload))

    with pytest.raises(MODULE.AcceptanceError, match="unexpected field set"):
        _verify(bundle)


@pytest.mark.parametrize("field", tuple(TARGET))
def test_rejects_evidence_target_drift(tmp_path: Path, field: str):
    bundle = _bundle(tmp_path)
    kind = "horizon_live_readiness"
    path, _ = bundle["evidence"][kind]
    payload = bundle["evidence_payloads"][kind]
    payload["releaseBinding"][field] = (
        "f" * 64 if field.endswith("Sha256") else "drift"
    )
    bundle["evidence"][kind] = (path, _write(path, payload))

    with pytest.raises(MODULE.AcceptanceError, match="target drifted"):
        _verify(bundle)


def test_rejects_missing_extra_and_duplicate_kind_denominators(tmp_path: Path):
    bundle = _bundle(tmp_path)
    bundle["evidence"] = {}
    with pytest.raises(MODULE.AcceptanceError, match="flagship v1 denominator"):
        _verify(bundle)

    with pytest.raises(MODULE.AcceptanceError, match="duplicate kind"):
        MODULE._parse_kind_map(["probe=/one", "probe=/two"], "--require-evidence")

    bundle = _bundle(tmp_path / "second")
    output = bundle["workspace"] / "acceptance.json"
    args = _cli_args(bundle, output)
    digest_index = args.index("--evidence-sha256")
    args[digest_index + 1] = args[digest_index + 1].replace(
        "horizon_live_readiness=", "extra_kind="
    )
    assert MODULE.main(args) == 1
    assert not output.exists()


def test_rejects_duplicate_evidence_ids(tmp_path: Path):
    bundle = _bundle(
        tmp_path, kinds=("horizon_live_readiness", "multi_account_live_journey")
    )
    kind = "multi_account_live_journey"
    path, _ = bundle["evidence"][kind]
    payload = bundle["evidence_payloads"][kind]
    payload["evidenceId"] = "evidence-0"
    bundle["evidence"][kind] = (path, _write(path, payload))

    with pytest.raises(MODULE.AcceptanceError, match="duplicate evidenceId"):
        _verify(bundle)


def test_rejects_digest_tamper_and_noncanonical_evidence(tmp_path: Path):
    bundle = _bundle(tmp_path)
    kind = "horizon_live_readiness"
    path, _ = bundle["evidence"][kind]
    bundle["evidence"][kind] = (path, "0" * 64)
    with pytest.raises(MODULE.AcceptanceError, match="SHA-256 mismatch"):
        _verify(bundle)

    bundle = _bundle(tmp_path / "noncanonical")
    path, _ = bundle["evidence"][kind]
    payload = bundle["evidence_payloads"][kind]
    bundle["evidence"][kind] = (path, _write(path, payload, canonical=False))
    with pytest.raises(MODULE.AcceptanceError, match="not canonical JSON"):
        _verify(bundle)


@pytest.mark.parametrize("unsafe", ["symlink", "mode"])
def test_rejects_symlink_and_unsafe_input_modes(tmp_path: Path, unsafe: str):
    bundle = _bundle(tmp_path)
    kind = "horizon_live_readiness"
    path, digest = bundle["evidence"][kind]
    if unsafe == "symlink":
        alias = bundle["workspace"] / "evidence-link.json"
        alias.symlink_to(path)
        bundle["evidence"][kind] = (alias, digest)
    else:
        path.chmod(0o644)

    with pytest.raises(MODULE.AcceptanceError, match="symlink|mode-0600"):
        _verify(bundle)


def test_fifo_input_is_rejected_without_blocking(tmp_path: Path):
    bundle = _bundle(tmp_path)
    fifo = bundle["workspace"] / "evidence.fifo"
    os.mkfifo(fifo, 0o600)
    fifo.chmod(0o600)

    with pytest.raises(MODULE.AcceptanceError, match="mode-0600 regular file"):
        MODULE._stable_file(fifo, bundle["workspace"], "FIFO evidence")


@pytest.mark.parametrize("case", ["unknown", "missing", "stable_ready"])
def test_finalization_schema_is_exact_and_v1_is_preview_only(tmp_path: Path, case: str):
    bundle = _bundle(tmp_path)
    payload = bundle["finalization_payload"]
    if case == "unknown":
        payload["extra"] = True
    elif case == "missing":
        payload.pop("stageReceiptId")
    else:
        payload["status"] = "stable_ready"
    bundle["finalization_sha"] = _write(bundle["finalization"], payload)

    with pytest.raises(MODULE.AcceptanceError, match="field set|preview_ready"):
        _verify(bundle)


@pytest.mark.parametrize(
    "scope",
    [
        {"paths": ["Chummer.exe"]},
        "blazor-desktop:macos:osx-arm64,avalonia:macos:osx-arm64",
        "avalonia:macos:osx-arm64,avalonia:macos:osx-arm64",
        "avalonia:macos",
        "Avalonia:macos:osx-arm64",
    ],
)
def test_finalization_desktop_scope_is_canonical_tuple_string(
    tmp_path: Path, scope: object
):
    bundle = _bundle(tmp_path)
    payload = bundle["finalization_payload"]
    payload["exactIncomingDesktopScope"] = scope
    bundle["finalization_sha"] = _write(bundle["finalization"], payload)

    with pytest.raises(MODULE.AcceptanceError, match="exactIncomingDesktopScope"):
        _verify(bundle)


def test_finalization_requires_canonical_compact_json(tmp_path: Path):
    bundle = _bundle(tmp_path)
    bundle["finalization_sha"] = _write(
        bundle["finalization"], bundle["finalization_payload"], canonical=False
    )

    with pytest.raises(MODULE.AcceptanceError, match="not canonical JSON"):
        _verify(bundle)


@pytest.mark.parametrize(
    "case",
    ["unknown", "denominator", "nested_drift", "unpublished", "failure", "bool_count"],
)
def test_convergence_requires_exact_full_success_semantics(tmp_path: Path, case: str):
    bundle = _bundle(tmp_path)
    payload = bundle["generation_payload"]
    if case == "unknown":
        payload["extra"] = True
    elif case == "denominator":
        payload["checkedRouteCount"] = 3
    elif case == "nested_drift":
        payload["releaseTruth"]["manifestSha256"] = "f" * 64
    elif case == "unpublished":
        payload["releaseTruth"]["releaseStatus"] = "draft"
    elif case == "failure":
        payload["failures"] = ["forged success"]
    else:
        payload["mismatchCount"] = False
    bundle["generation_sha"] = _write(bundle["generation"], payload)

    with pytest.raises(MODULE.AcceptanceError):
        _verify(bundle)


@pytest.mark.parametrize("role", ["generation", "current"])
@pytest.mark.parametrize("case", ["wrong", "missing_install", "multiple_install"])
def test_convergence_route_denominator_is_producer_exact(
    tmp_path: Path, role: str, case: str
):
    bundle = _bundle(tmp_path)
    payload_key = "generation_payload" if role == "generation" else "current_payload"
    path_key = "generation" if role == "generation" else "current"
    sha_key = "generation_sha" if role == "generation" else "current_sha"
    payload = bundle[payload_key]
    routes = list(payload["checkedRoutes"])
    install_prefix = (
        f"/downloads/g/{TARGET['generationId']}/install/"
        if role == "generation"
        else "/downloads/install/"
    )
    install_routes = [route for route in routes if route.startswith(install_prefix)]
    assert len(install_routes) == 1
    if case == "wrong":
        routes[0] = "/bogus"
    elif case == "missing_install":
        routes.remove(install_routes[0])
    else:
        routes.append(f"{install_prefix}artifact-second")
    payload["checkedRoutes"] = sorted(routes)
    payload["checkedRouteCount"] = len(routes)
    bundle[sha_key] = _write(bundle[path_key], payload)

    with pytest.raises(MODULE.AcceptanceError, match="checked-route denominator"):
        _verify(bundle)


def test_manifest_selects_the_only_allowed_install_routes(tmp_path: Path):
    bundle = _bundle(tmp_path)
    manifest = bundle["manifest_payload"]
    manifest["downloads"][0]["id"] = "artifact-other"
    bundle["manifest_sha"] = _write(bundle["manifest"], manifest)

    with pytest.raises(MODULE.AcceptanceError, match="checked-route denominator"):
        _verify(bundle)


@pytest.mark.parametrize("case", ["digest", "native_drift", "truth_drift"])
def test_manifest_is_digest_pinned_and_bound_to_release_truth(
    tmp_path: Path, case: str
):
    bundle = _bundle(tmp_path)
    if case == "digest":
        bundle["manifest_sha"] = "0" * 64
    else:
        manifest = bundle["manifest_payload"]
        if case == "native_drift":
            manifest["status"] = "withdrawn"
        else:
            manifest["releaseTruth"]["knownIssueSummary"] = "Drifted."
        bundle["manifest_sha"] = _write(bundle["manifest"], manifest)

    with pytest.raises(MODULE.AcceptanceError, match="SHA-256|manifest"):
        _verify(bundle)


def test_manifest_accepts_strict_producer_native_pretty_json(tmp_path: Path):
    bundle = _bundle(tmp_path)
    bundle["manifest_sha"] = _write(
        bundle["manifest"], bundle["manifest_payload"], canonical=False
    )
    _rebind_horizon_producer_inputs(bundle)

    assert _verify(bundle)["status"] == "attention_required"


def test_convergence_accepts_strict_producer_native_pretty_json(tmp_path: Path):
    bundle = _bundle(tmp_path)
    bundle["generation_sha"] = _write(
        bundle["generation"], bundle["generation_payload"], canonical=False
    )
    bundle["current_sha"] = _write(
        bundle["current"], bundle["current_payload"], canonical=False
    )
    _rebind_horizon_producer_inputs(bundle)

    assert _verify(bundle)["status"] == "attention_required"


def test_generation_and_current_release_truth_must_match_fully(tmp_path: Path):
    bundle = _bundle(tmp_path)
    current = bundle["current_payload"]
    current["releaseTruth"]["knownIssueSummary"] = "A different summary."
    bundle["current_sha"] = _write(bundle["current"], current)

    with pytest.raises(MODULE.AcceptanceError, match="do not converge exactly"):
        _verify(bundle)


@pytest.mark.parametrize("case", ["old_kind", "empty", "duplicate", "bad_digest", "extra"])
def test_evidence_kind_and_nonempty_claim_schema_are_strict(tmp_path: Path, case: str):
    bundle = _bundle(tmp_path)
    kind = "horizon_live_readiness"
    path, _ = bundle["evidence"][kind]
    payload = bundle["evidence_payloads"][kind]
    if case == "old_kind":
        payload["kind"] = payload.pop("evidenceKind")
    elif case == "empty":
        payload["claims"] = []
    elif case == "duplicate":
        payload["claims"].append(dict(payload["claims"][0]))
    elif case == "bad_digest":
        payload["claims"][0]["evidenceSha256"] = "not-a-digest"
    else:
        payload["claims"][0]["path"] = "/secret/path"
    bundle["evidence"][kind] = (path, _write(path, payload))

    with pytest.raises(MODULE.AcceptanceError):
        _verify(bundle)


def test_attention_claim_prevents_acceptance_without_copying_raw_claims(tmp_path: Path):
    bundle = _bundle(tmp_path)
    kind = "horizon_live_readiness"
    path, _ = bundle["evidence"][kind]
    payload = bundle["evidence_payloads"][kind]
    payload["claims"][0]["status"] = "attention_required"
    bundle["evidence"][kind] = (path, _write(path, payload))

    receipt = _verify(bundle)

    assert receipt["status"] == "attention_required"
    row = receipt["evidence"][0]
    assert row["accepted"] is False
    assert row["claimCount"] == 1
    assert len(row["claimSetSha256"]) == 64
    assert "claims" not in row


def test_evidence_timestamp_requires_canonical_z_form(tmp_path: Path):
    bundle = _bundle(tmp_path)
    kind = "horizon_live_readiness"
    path, _ = bundle["evidence"][kind]
    payload = bundle["evidence_payloads"][kind]
    payload["generatedAtUtc"] = payload["generatedAtUtc"].replace("Z", "+00:00")
    bundle["evidence"][kind] = (path, _write(path, payload))

    with pytest.raises(MODULE.AcceptanceError, match="canonical UTC timestamp"):
        _verify(bundle)


def test_current_convergence_must_be_a_post_evidence_fence(tmp_path: Path):
    bundle = _bundle(tmp_path)
    payload = bundle["current_payload"]
    payload["generatedAtUtc"] = _utc(OBSERVED_AT - dt.timedelta(seconds=90))
    bundle["current_sha"] = _write(bundle["current"], payload)

    with pytest.raises(MODULE.AcceptanceError, match="predates .* post-activation evidence"):
        _verify(bundle)


def test_generation_convergence_must_precede_every_evidence(tmp_path: Path):
    bundle = _bundle(tmp_path)
    generation = bundle["generation_payload"]
    generation["generatedAtUtc"] = _utc(OBSERVED_AT - dt.timedelta(seconds=30))
    bundle["generation_sha"] = _write(bundle["generation"], generation)
    _rebind_horizon_producer_inputs(bundle)

    with pytest.raises(MODULE.AcceptanceError, match="postdates .* post-activation evidence"):
        _verify(bundle)


def test_generation_convergence_must_follow_finalization(tmp_path: Path):
    bundle = _bundle(tmp_path)
    generation = bundle["generation_payload"]
    generation["generatedAtUtc"] = _utc(OBSERVED_AT - dt.timedelta(minutes=4))
    bundle["generation_sha"] = _write(bundle["generation"], generation)

    with pytest.raises(MODULE.AcceptanceError, match="predates owner finalization"):
        _verify(bundle)


def test_generation_convergence_must_be_fresh(tmp_path: Path):
    bundle = _bundle(tmp_path)
    finalization = bundle["finalization_payload"]
    finalization["completedAtUtc"] = _utc(OBSERVED_AT - dt.timedelta(hours=26))
    bundle["finalization_sha"] = _write(bundle["finalization"], finalization)
    generation = bundle["generation_payload"]
    generation["generatedAtUtc"] = _utc(OBSERVED_AT - dt.timedelta(hours=25))
    bundle["generation_sha"] = _write(bundle["generation"], generation)

    with pytest.raises(MODULE.AcceptanceError, match="generation convergence is stale"):
        _verify(bundle)


def test_current_convergence_must_be_fresh(tmp_path: Path):
    bundle = _bundle(tmp_path)
    finalization = bundle["finalization_payload"]
    finalization["completedAtUtc"] = _utc(OBSERVED_AT - dt.timedelta(hours=26))
    bundle["finalization_sha"] = _write(bundle["finalization"], finalization)
    current = bundle["current_payload"]
    current["generatedAtUtc"] = _utc(OBSERVED_AT - dt.timedelta(hours=25))
    bundle["current_sha"] = _write(bundle["current"], current)
    kind = "horizon_live_readiness"
    path, _ = bundle["evidence"][kind]
    evidence = bundle["evidence_payloads"][kind]
    evidence["generatedAtUtc"] = _utc(OBSERVED_AT - dt.timedelta(hours=23))
    bundle["evidence"][kind] = (path, _write(path, evidence))

    with pytest.raises(MODULE.AcceptanceError, match="CURRENT convergence is stale"):
        _verify(bundle)


def test_output_is_create_exclusive_and_does_not_overwrite(tmp_path: Path):
    bundle = _bundle(tmp_path)
    output = bundle["workspace"] / "acceptance.json"
    output.write_text("keep-me", encoding="utf-8")
    output.chmod(0o600)

    with pytest.raises(MODULE.AcceptanceError, match="already exists"):
        _verify(bundle, output=output)
    assert output.read_text(encoding="utf-8") == "keep-me"
    assert not list(bundle["workspace"].glob(".post-activation-acceptance.tmp-*"))


def test_publish_race_never_unlinks_replacement_target(
    tmp_path: Path, monkeypatch
):
    bundle = _bundle(tmp_path)
    output = bundle["workspace"] / "acceptance.json"

    def racing_link(source, target, *, follow_symlinks):
        assert follow_symlinks is False
        replacement = Path(target)
        replacement.write_text("replacement-wins", encoding="utf-8")
        replacement.chmod(0o600)
        raise FileExistsError("raced")

    monkeypatch.setattr(MODULE.os, "link", racing_link)

    with pytest.raises(MODULE.AcceptanceError, match="already exists"):
        _verify(bundle, output=output)
    assert output.read_text(encoding="utf-8") == "replacement-wins"
    assert not list(bundle["workspace"].glob(".post-activation-acceptance.tmp-*"))


def test_duplicate_json_error_does_not_echo_attacker_key():
    raw = b'{"credential-material":1,"credential-material":2}'

    with pytest.raises(MODULE.AcceptanceError) as raised:
        MODULE._strict_json(raw, "evidence")

    assert "credential-material" not in str(raised.value)


def test_cli_redacts_raw_oserror_details(tmp_path: Path, monkeypatch, capsys):
    bundle = _bundle(tmp_path)
    output = bundle["workspace"] / "acceptance.json"

    def fail_with_oserror(**_kwargs):
        raise OSError("/private/attacker-controlled-path")

    monkeypatch.setattr(MODULE, "verify", fail_with_oserror)

    assert MODULE.main(_cli_args(bundle, output)) == 1
    error = capsys.readouterr().err
    assert error == (
        "post_activation_acceptance:fail: bounded local validation failed\n"
    )
    assert "attacker-controlled" not in error


def test_cli_returns_attention_and_fail_without_partial_output(tmp_path: Path, capsys):
    now = dt.datetime.now(dt.timezone.utc)
    bundle = _bundle(tmp_path, observed_at=now)
    kind = "horizon_live_readiness"
    path, _ = bundle["evidence"][kind]
    payload = bundle["evidence_payloads"][kind]
    payload["status"] = "attention_required"
    bundle["evidence"][kind] = (path, _write(path, payload))
    attention_output = bundle["workspace"] / "attention.json"

    assert MODULE.main(_cli_args(bundle, attention_output)) == 2
    assert json.loads(attention_output.read_text())["status"] == "attention_required"
    assert "post_activation_acceptance:attention_required" in capsys.readouterr().out

    fail_output = bundle["workspace"] / "fail.json"
    args = _cli_args(bundle, fail_output)
    index = args.index("--evidence-sha256")
    args[index + 1] = f"{kind}={'0' * 64}"
    assert MODULE.main(args) == 1
    assert not fail_output.exists()
    assert "post_activation_acceptance:fail:" in capsys.readouterr().err


def test_cli_maps_accepted_status_to_success(
    tmp_path: Path,
    monkeypatch,
    capsys,
):
    bundle = _bundle(
        tmp_path,
        observed_at=dt.datetime.now(dt.timezone.utc),
    )
    output = bundle["workspace"] / "accepted.json"
    monkeypatch.setattr(MODULE, "verify", lambda **_kwargs: {"status": "accepted"})

    assert MODULE.main(_cli_args(bundle, output)) == 0
    streams = capsys.readouterr()
    assert streams.out == "post_activation_acceptance:accepted\n"
    assert streams.err == ""


def test_governed_campaign_v2_cli_keeps_non_pass_attention_and_rejects_pass(
    tmp_path: Path,
    capsys,
):
    bundle = _bundle(
        tmp_path / "non-pass",
        observed_at=dt.datetime.now(dt.timezone.utc),
        campaign_v2_status="blocked",
    )
    attention_output = bundle["workspace"] / "v2-attention.json"

    assert MODULE.main(_cli_args(bundle, attention_output)) == 2
    assert json.loads(attention_output.read_text())["status"] == "attention_required"
    assert "post_activation_acceptance:attention_required" in capsys.readouterr().out

    pass_bundle = _bundle(
        tmp_path / "pass",
        observed_at=dt.datetime.now(dt.timezone.utc),
        campaign_v2_status="pass",
    )
    fail_output = pass_bundle["workspace"] / "v2-pass.json"
    assert MODULE.main(_cli_args(pass_bundle, fail_output)) == 1
    assert not fail_output.exists()
    assert (
        "native pass is disabled by producer authority" in capsys.readouterr().err
    )
