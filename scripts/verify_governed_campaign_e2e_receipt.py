#!/usr/bin/env python3
"""Validate governed real-account campaign evidence without touching the network.

This module is deliberately a verifier, not a browser runner.  It accepts only
one exact v2 receipt/permit vocabulary, recomputes the terminal state from the
recorded facts, and can materialize the small post-activation evidence envelope
consumed by ``verify_post_activation_acceptance.py``.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import hmac
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
from typing import Any, Mapping, Sequence
from urllib.parse import urlsplit


RECEIPT_CONTRACT = "chummer.multi-account-live-journey/v2"
PERMIT_CONTRACT = "chummer.live-campaign-mutation-permit/v2"
EVIDENCE_CONTRACT = "chummer.post-activation-evidence/v1"
EVIDENCE_KIND = "multi_account_live_journey"
OUTER_CLAIM_ID = "production_multi_account_journey_v2"
PRODUCTION_ORIGIN = "https://chummer.run"

STATUSES = ("not_run", "blocked", "cleanup_required", "pass")
EXIT_CODES = {"not_run": 2, "blocked": 2, "cleanup_required": 3, "pass": 0}
# A caller-supplied digest proves byte consistency, not independent production
# provenance.  Until every denominator action has an audited, canary-scoped
# compensator and authenticated evidence source, neither this verifier nor an
# aggregate consumer may authorize a live pass.
LIVE_PASS_AUTHORIZED = False
ROLES = ("alice_runner", "bob_runner", "depleted_runner", "gm_campaign")
ACTION_IDS = (
    "campaign_create_or_join",
    "consent_visibility",
    "alice_runner_reaction",
    "bob_runner_reaction",
    "depleted_runner_quota_denial",
    "runsite_cross_user_privacy",
)
ACTION_CATALOG: dict[str, dict[str, Any]] = {
    "campaign_create_or_join": {
        "role": "gm_campaign",
        "mutating": True,
        "attemptLimit": 0,
        "forwardWriteLimit": 0,
        "cleanupWriteLimit": 0,
        "compensator": None,
    },
    "consent_visibility": {
        "role": "alice_runner",
        "mutating": True,
        "attemptLimit": 0,
        "forwardWriteLimit": 0,
        "cleanupWriteLimit": 0,
        "compensator": None,
    },
    "alice_runner_reaction": {
        "role": "alice_runner",
        "mutating": True,
        "attemptLimit": 0,
        "forwardWriteLimit": 0,
        "cleanupWriteLimit": 0,
        "compensator": None,
    },
    "bob_runner_reaction": {
        "role": "bob_runner",
        "mutating": True,
        "attemptLimit": 0,
        "forwardWriteLimit": 0,
        "cleanupWriteLimit": 0,
        "compensator": None,
    },
    "depleted_runner_quota_denial": {
        "role": "depleted_runner",
        "mutating": True,
        "attemptLimit": 0,
        "forwardWriteLimit": 0,
        "cleanupWriteLimit": 0,
        "compensator": None,
    },
    "runsite_cross_user_privacy": {
        "role": "alice_runner",
        "mutating": False,
        "attemptLimit": 1,
        "forwardWriteLimit": 0,
        "cleanupWriteLimit": 0,
        "compensator": None,
    },
}

RECEIPT_FIELDS = {
    "contractName",
    "contractVersion",
    "receiptId",
    "generatedAtUtc",
    "status",
    "secretRedacted",
    "operationalReadinessClaimAllowed",
    "releaseBinding",
    "inputBindings",
    "browserPolicy",
    "currentFence",
    "accounts",
    "journey",
    "permit",
    "cleanup",
    "browserOoda",
    "blockers",
    "failures",
}
RELEASE_BINDING_FIELDS = {
    "releaseVersion",
    "generationId",
    "manifestSha256",
    "decisionSha256",
    "snapshotSha256",
    "targetPointerSha256",
}
INPUT_BINDING_FIELDS = {
    "mutationPermitSha256",
    "ownerFinalizationReceiptSha256",
    "generationConvergenceSha256",
    "generationManifestFileSha256",
}
CURRENT_FENCE_FIELDS = {"preCurrent", "postCurrent", "stable"}
CURRENT_SNAPSHOT_FIELDS = RELEASE_BINDING_FIELDS | {"responseSha256"}
BROWSER_POLICY_FIELDS = {
    "allowedOrigin",
    "sameOriginOnly",
    "redirectsFollowed",
    "requestInterceptionUsed",
    "testIdentityHeadersUsed",
    "adminSessionUsed",
    "sharedBrowserContextUsed",
    "crossOriginRequestsPerformed",
    "providerCallsPerformed",
    "notificationsSent",
    "publicationsPerformed",
    "accountChangesPerformed",
    "securityChangesPerformed",
    "paymentsPerformed",
    "purchasesPerformed",
    "irreversibleActionsPerformed",
    "stopOnApprovalBoundary",
    "stopOnIdentityMismatch",
    "stopOnMfa",
    "stopOnCaptcha",
    "stopOnCloudflare",
}
ACCOUNT_FIELDS = {
    "role",
    "accountRefHmac",
    "browserContextRefHmac",
    "browserSessionRefHmac",
    "visibleIdentityMatched",
}
JOURNEY_FIELDS = {"credentialedAttemptPerformed", "steps"}
STEP_FIELDS = {
    "actionId",
    "role",
    "status",
    "mutating",
    "attempts",
    "forwardWrites",
    "cleanupWrites",
    "assertionPassed",
    "compensator",
    "compensatorAvailableBeforeWrite",
    "serverIdempotencyKeyHmac",
    "revisionPreconditionHmac",
    "journalIntentSha256",
    "evidenceSha256",
}
PERMIT_FIELDS = {
    "contractName",
    "contractVersion",
    "status",
    "secretRedacted",
    "permitId",
    "issuedAtUtc",
    "forwardExpiresAtUtc",
    "cleanupExpiresAtUtc",
    "allowedOrigin",
    "releaseBinding",
    "ownerAuthorization",
    "canaryCampaignRefHmac",
    "roleAccountRefHmacs",
    "actions",
    "totalForwardWriteLimit",
    "totalCleanupWriteLimit",
    "nonceRefHmac",
    "replayLedgerRefHmac",
    "irreversibleActionsAllowed",
    "notificationsAllowed",
}
OWNER_AUTHORIZATION_FIELDS = {
    "authorizationRefHmac",
    "authorizedByRefHmac",
    "authorizedAtUtc",
    "producerIndependent",
}
PERMIT_ACTION_FIELDS = {
    "actionId",
    "role",
    "attemptLimit",
    "forwardWriteLimit",
    "cleanupWriteLimit",
    "compensator",
}
RECEIPT_PERMIT_FIELDS = {
    "permitSha256",
    "permitId",
    "nonceRefHmac",
    "replayLedgerRefHmac",
    "nonceClaimed",
    "replayDetected",
    "forwardStartedAtUtc",
    "cleanupCompletedAtUtc",
}
CLEANUP_FIELDS = {"journal", "strategy", "entries", "postconditions"}
CLEANUP_JOURNAL_FIELDS = {
    "pathRefHmac",
    "mode",
    "appendOnly",
    "intentBeforeWrite",
    "resultAfterResponse",
}
CLEANUP_STRATEGY_FIELDS = {
    "reverseOrder",
    "resumable",
    "finallyGuaranteed",
    "runOwnedIdsOnly",
    "broadDeletesUsed",
    "preExistingContentChanged",
}
CLEANUP_ENTRY_FIELDS = {
    "sequence",
    "actionId",
    "resourceRefHmac",
    "idempotencyKeyHmac",
    "revisionPreconditionHmac",
    "intentEvidenceSha256",
    "responseEvidenceSha256",
    "result",
    "acknowledged",
}
CLEANUP_POSTCONDITION_FIELDS = {
    "compensatorsAcknowledged",
    "canonicalPostMatchesPre",
    "residualCampaignRows",
    "residualAuditRows",
    "residualRequestReceiptRows",
    "quotaUnchanged",
    "providerCallCount",
    "notificationCount",
}
BROWSER_OODA_FIELDS = {
    "site",
    "requestedActions",
    "completedActions",
    "safeContext",
    "qualityGate",
    "finalUrl",
    "stopCondition",
    "evidenceSha256s",
    "notificationOutcome",
    "irreversibleAttemptCount",
}
FINALIZATION_FIELDS = {
    "contractName",
    "contractVersion",
    "status",
    "releaseVersion",
    "generationId",
    "stageReceiptId",
    "manifestSha256",
    "releaseScopeDecisionSha256",
    "releaseScopeVerificationSha256",
    "exactIncomingDesktopScope",
    "snapshotSha256",
    "decisionSha256",
    "authorityRevisionId",
    "targetPointerSha256",
    "completedAtUtc",
}
CONVERGENCE_FIELDS = {
    "contractName",
    "contractVersion",
    "generatedAtUtc",
    "status",
    "mismatchCount",
    "failureCount",
    "mismatches",
    "failures",
    "authorityRoute",
    "checkedRouteCount",
    "checkedRoutes",
    "comparedFields",
    "releaseTruth",
    "releaseVersion",
    "manifestSha256",
    "releaseDecisionStatus",
    "releaseDecisionSha256",
    "authoritySnapshotSha256",
    "verificationMode",
}

SHA256 = re.compile(r"^[0-9a-f]{64}$")
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
SAFE_REASON = re.compile(r"^[a-z][a-z0-9._:-]{0,127}$")
AUTHORITY_REVISION = re.compile(r"^auth-[0-9a-f]{64}$")
SAFE_SCOPE_COMPONENT = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
UTC_TIMESTAMP = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?Z$"
)
MAX_INPUT_BYTES = 8 * 1024 * 1024
MAX_FUTURE_SKEW_SECONDS = 5 * 60
MAX_EVIDENCE_AGE_SECONDS = 24 * 60 * 60
MAX_PERMIT_FORWARD_LIFETIME = dt.timedelta(hours=1)
MAX_PERMIT_CLEANUP_LIFETIME = dt.timedelta(hours=24)
FORBIDDEN_KEY_MARKERS = (
    "password",
    "credential",
    "accesstoken",
    "access_token",
    "refreshtoken",
    "refresh_token",
    "authorizationheader",
    "privatekey",
    "email",
    "subjectid",
    "accountid",
    "storage_state",
    "storagestate",
    "cookie",
)
FORBIDDEN_VALUE_PATTERNS = (
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
)


class ReceiptError(RuntimeError):
    """The supplied evidence is malformed or contradicts the exact contract."""


def _convergence_helpers():
    path = Path(__file__).with_name("verify_live_release_convergence.py")
    spec = importlib.util.spec_from_file_location("_campaign_live_convergence", path)
    if spec is None or spec.loader is None:
        raise ReceiptError("live convergence verifier helpers are unavailable")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except (ImportError, OSError) as error:
        raise ReceiptError("live convergence verifier helpers are unavailable") from error
    return module


CONVERGENCE_HELPERS = _convergence_helpers()


def canonical_bytes(payload: Any) -> bytes:
    try:
        text = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        raise ReceiptError("payload is not canonicalizable JSON") from error
    return (text + "\n").encode("utf-8")


def _exact_object(value: Any, fields: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        raise ReceiptError(f"{label} has an unexpected field set")
    return value


def _sha(value: Any, label: str) -> str:
    if not isinstance(value, str) or SHA256.fullmatch(value) is None:
        raise ReceiptError(f"{label} must be canonical SHA-256")
    return value


def _hmac_ref(value: Any, label: str) -> str:
    if not isinstance(value, str) or SHA256.fullmatch(value) is None:
        raise ReceiptError(f"{label} must be an operator-keyed HMAC reference")
    return value


def _safe_id(value: Any, label: str) -> str:
    if not isinstance(value, str) or SAFE_ID.fullmatch(value) is None or ".." in value:
        raise ReceiptError(f"{label} must be a safe opaque identifier")
    return value


def _desktop_scope(value: Any) -> str:
    if not isinstance(value, str) or not value or len(value) > 4096:
        raise ReceiptError("owner finalization desktop scope is invalid")
    entries = value.split(",")
    if len(entries) > 64 or entries != sorted(set(entries)):
        raise ReceiptError("owner finalization desktop scope is not canonical")
    for entry in entries:
        components = entry.split(":")
        if len(components) != 3 or any(
            SAFE_SCOPE_COMPONENT.fullmatch(component) is None
            for component in components
        ):
            raise ReceiptError("owner finalization desktop scope is invalid")
    return value


def _timestamp(value: Any, label: str) -> dt.datetime:
    if not isinstance(value, str) or UTC_TIMESTAMP.fullmatch(value) is None:
        raise ReceiptError(f"{label} must be a canonical UTC timestamp")
    try:
        parsed = dt.datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise ReceiptError(f"{label} must be a canonical UTC timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() != dt.timedelta(0):
        raise ReceiptError(f"{label} must be a canonical UTC timestamp")
    return parsed.astimezone(dt.timezone.utc)


def _optional_timestamp(value: Any, label: str) -> dt.datetime | None:
    return None if value is None else _timestamp(value, label)


def _bounded_int(value: Any, label: str, maximum: int = 64) -> int:
    if type(value) is not int or not 0 <= value <= maximum:
        raise ReceiptError(f"{label} must be a bounded non-negative integer")
    return value


def _reject_sensitive(value: Any, path: str = "receipt") -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            if not isinstance(key, str):
                raise ReceiptError(f"{path} contains a non-string field name")
            folded = key.casefold()
            if folded != "credentialedattemptperformed" and any(
                marker in folded for marker in FORBIDDEN_KEY_MARKERS
            ):
                raise ReceiptError(f"{path} contains a forbidden sensitive field")
            _reject_sensitive(nested, f"{path}.{key}")
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            _reject_sensitive(nested, f"{path}[{index}]")
    elif isinstance(value, str):
        if len(value) > 4096 or any(pattern.search(value) for pattern in FORBIDDEN_VALUE_PATTERNS):
            raise ReceiptError(f"{path} contains raw sensitive material")


def _validate_release_binding(value: Any, label: str) -> dict[str, str]:
    binding = _exact_object(value, RELEASE_BINDING_FIELDS, label)
    result = {
        "releaseVersion": _safe_id(binding["releaseVersion"], f"{label}.releaseVersion"),
        "generationId": _safe_id(binding["generationId"], f"{label}.generationId"),
        "manifestSha256": _sha(binding["manifestSha256"], f"{label}.manifestSha256"),
        "decisionSha256": _sha(binding["decisionSha256"], f"{label}.decisionSha256"),
        "snapshotSha256": _sha(binding["snapshotSha256"], f"{label}.snapshotSha256"),
        "targetPointerSha256": _sha(
            binding["targetPointerSha256"], f"{label}.targetPointerSha256"
        ),
    }
    return result


def _validate_permit(
    payload: Any,
    *,
    release_binding: Mapping[str, str],
    observed_at: dt.datetime,
) -> dict[str, Any]:
    permit = _exact_object(payload, PERMIT_FIELDS, "mutation permit")
    _reject_sensitive(permit, "mutation permit")
    if (
        permit["contractName"] != PERMIT_CONTRACT
        or type(permit["contractVersion"]) is not int
        or permit["contractVersion"] != 2
        or permit["status"] != "approved"
        or permit["secretRedacted"] is not True
        or permit["allowedOrigin"] != PRODUCTION_ORIGIN
        or permit["irreversibleActionsAllowed"] is not False
        or permit["notificationsAllowed"] is not False
    ):
        raise ReceiptError("mutation permit identity or safety posture is invalid")
    permit_id = _safe_id(permit["permitId"], "mutation permit permitId")
    permit_binding = _validate_release_binding(
        permit["releaseBinding"], "mutation permit releaseBinding"
    )
    if permit_binding != dict(release_binding):
        raise ReceiptError("mutation permit release binding drifted")

    owner = _exact_object(
        permit["ownerAuthorization"],
        OWNER_AUTHORIZATION_FIELDS,
        "mutation permit ownerAuthorization",
    )
    _hmac_ref(owner["authorizationRefHmac"], "owner authorization reference")
    _hmac_ref(owner["authorizedByRefHmac"], "owner authorizer reference")
    authorized_at = _timestamp(owner["authorizedAtUtc"], "owner authorizedAtUtc")
    if owner["producerIndependent"] is not True:
        raise ReceiptError("mutation permit must be independently owner-authorized")

    issued = _timestamp(permit["issuedAtUtc"], "mutation permit issuedAtUtc")
    forward_expires = _timestamp(
        permit["forwardExpiresAtUtc"], "mutation permit forwardExpiresAtUtc"
    )
    cleanup_expires = _timestamp(
        permit["cleanupExpiresAtUtc"], "mutation permit cleanupExpiresAtUtc"
    )
    if (
        authorized_at > issued
        or issued > observed_at + dt.timedelta(seconds=MAX_FUTURE_SKEW_SECONDS)
        or forward_expires <= issued
        or forward_expires - issued > MAX_PERMIT_FORWARD_LIFETIME
        or cleanup_expires <= forward_expires
        or cleanup_expires - issued > MAX_PERMIT_CLEANUP_LIFETIME
    ):
        raise ReceiptError("mutation permit lifetime is invalid")

    campaign_ref = _hmac_ref(
        permit["canaryCampaignRefHmac"], "mutation permit canary campaign"
    )
    role_refs = _exact_object(
        permit["roleAccountRefHmacs"], set(ROLES), "mutation permit role accounts"
    )
    normalized_role_refs = {
        role: _hmac_ref(role_refs[role], f"mutation permit {role} account")
        for role in ROLES
    }
    if len(set(normalized_role_refs.values())) != len(ROLES):
        raise ReceiptError("mutation permit role account references must be distinct")

    actions = permit["actions"]
    if not isinstance(actions, list) or len(actions) != len(ACTION_IDS):
        raise ReceiptError("mutation permit action denominator is invalid")
    normalized_actions: dict[str, dict[str, Any]] = {}
    forward_total = 0
    cleanup_total = 0
    for index, expected_action in enumerate(ACTION_IDS):
        row = _exact_object(
            actions[index], PERMIT_ACTION_FIELDS, f"mutation permit action {index}"
        )
        if row["actionId"] != expected_action:
            raise ReceiptError("mutation permit action denominator is reordered or unknown")
        catalog = ACTION_CATALOG[expected_action]
        expected_attempts = catalog["attemptLimit"]
        expected_forward = catalog["forwardWriteLimit"]
        expected_cleanup = catalog["cleanupWriteLimit"]
        if (
            row["role"] != catalog["role"]
            or type(row["attemptLimit"]) is not int
            or type(row["forwardWriteLimit"]) is not int
            or type(row["cleanupWriteLimit"]) is not int
            or row["attemptLimit"] != expected_attempts
            or row["forwardWriteLimit"] != expected_forward
            or row["cleanupWriteLimit"] != expected_cleanup
            or row["compensator"] != catalog["compensator"]
        ):
            raise ReceiptError("mutation permit action budget or compensator drifted")
        forward_total += expected_forward
        cleanup_total += expected_cleanup
        normalized_actions[expected_action] = row
    if (
        type(permit["totalForwardWriteLimit"]) is not int
        or type(permit["totalCleanupWriteLimit"]) is not int
        or permit["totalForwardWriteLimit"] != forward_total
        or permit["totalCleanupWriteLimit"] != cleanup_total
    ):
        raise ReceiptError("mutation permit aggregate budgets are inconsistent")
    nonce = _hmac_ref(permit["nonceRefHmac"], "mutation permit nonce")
    ledger = _hmac_ref(permit["replayLedgerRefHmac"], "mutation permit replay ledger")
    owner_refs = {owner["authorizationRefHmac"], owner["authorizedByRefHmac"]}
    all_hmac_refs = {
        campaign_ref,
        nonce,
        ledger,
        *normalized_role_refs.values(),
        *owner_refs,
    }
    if len(owner_refs) != 2 or len(all_hmac_refs) != 3 + len(ROLES) + 2:
        raise ReceiptError("mutation permit HMAC references are not domain-separated")
    return {
        "permitId": permit_id,
        "issuedAt": issued,
        "forwardExpiresAt": forward_expires,
        "cleanupExpiresAt": cleanup_expires,
        "roleAccountRefs": normalized_role_refs,
        "actions": normalized_actions,
        "nonceRefHmac": nonce,
        "replayLedgerRefHmac": ledger,
        "canaryCampaignRefHmac": campaign_ref,
        "allHmacRefs": all_hmac_refs,
    }


def _validate_browser_policy(value: Any) -> list[str]:
    policy = _exact_object(value, BROWSER_POLICY_FIELDS, "browserPolicy")
    if policy["allowedOrigin"] != PRODUCTION_ORIGIN:
        raise ReceiptError("browser policy does not name the exact production origin")
    true_fields = {
        "sameOriginOnly",
        "stopOnApprovalBoundary",
        "stopOnIdentityMismatch",
        "stopOnMfa",
        "stopOnCaptcha",
        "stopOnCloudflare",
    }
    false_fields = BROWSER_POLICY_FIELDS - true_fields - {"allowedOrigin"}
    for field in true_fields | false_fields:
        if not isinstance(policy[field], bool):
            raise ReceiptError(f"browserPolicy.{field} must be boolean")
    issues = [field for field in true_fields if policy[field] is not True]
    issues.extend(field for field in false_fields if policy[field] is not False)
    return [f"browser_policy:{field}" for field in sorted(issues)]


def _validate_current_fence(
    value: Any, release_binding: Mapping[str, str]
) -> list[str]:
    fence = _exact_object(value, CURRENT_FENCE_FIELDS, "currentFence")
    if not isinstance(fence["stable"], bool):
        raise ReceiptError("currentFence.stable must be boolean")
    if fence["preCurrent"] is None and fence["postCurrent"] is None:
        if fence["stable"] is not False:
            raise ReceiptError("an unobserved CURRENT fence cannot claim stability")
        return ["current_fence:unobserved"]
    if fence["preCurrent"] is None or fence["postCurrent"] is None:
        raise ReceiptError("CURRENT fence observations must be both present or both absent")
    snapshots: dict[str, dict[str, Any]] = {}
    for name in ("preCurrent", "postCurrent"):
        snapshot = _exact_object(
            fence[name], CURRENT_SNAPSHOT_FIELDS, f"currentFence.{name}"
        )
        for field in RELEASE_BINDING_FIELDS:
            if field in {"releaseVersion", "generationId"}:
                _safe_id(snapshot[field], f"currentFence.{name}.{field}")
            else:
                _sha(snapshot[field], f"currentFence.{name}.{field}")
        _sha(snapshot["responseSha256"], f"currentFence.{name}.responseSha256")
        snapshots[name] = snapshot
    issues: list[str] = []
    if fence["stable"] is not True:
        issues.append("current_fence:not_stable")
    if snapshots["preCurrent"] != snapshots["postCurrent"]:
        issues.append("current_fence:changed")
    if any(
        snapshots[name][field] != release_binding[field]
        for name in snapshots
        for field in RELEASE_BINDING_FIELDS
    ):
        issues.append("current_fence:release_binding_drift")
    return issues


def _validate_accounts(
    value: Any, permit: Mapping[str, Any]
) -> tuple[list[str], set[str]]:
    if not isinstance(value, list) or len(value) != len(ROLES):
        raise ReceiptError("account role denominator is invalid")
    account_refs: list[str] = []
    contexts: list[str] = []
    sessions: list[str] = []
    issues: list[str] = []
    for index, role in enumerate(ROLES):
        row = _exact_object(value[index], ACCOUNT_FIELDS, f"account {index}")
        if row["role"] != role:
            raise ReceiptError("account rows are not in the exact sorted role order")
        account_ref = _hmac_ref(row["accountRefHmac"], f"{role} account reference")
        context_ref = _hmac_ref(
            row["browserContextRefHmac"], f"{role} browser context"
        )
        session_ref = _hmac_ref(
            row["browserSessionRefHmac"], f"{role} browser session"
        )
        if account_ref != permit["roleAccountRefs"][role]:
            raise ReceiptError(f"{role} account does not bind the authorized permit role")
        if not isinstance(row["visibleIdentityMatched"], bool):
            raise ReceiptError(f"{role} visible identity result must be boolean")
        if row["visibleIdentityMatched"] is not True:
            issues.append(f"account:{role}:visible_identity_mismatch")
        account_refs.append(account_ref)
        contexts.append(context_ref)
        sessions.append(session_ref)
    if len(set(account_refs)) != len(ROLES):
        raise ReceiptError("account references are not distinct")
    if len(set(contexts)) != len(ROLES) or len(set(sessions)) != len(ROLES):
        raise ReceiptError("each role must use a distinct browser context and session")
    if set(contexts) & set(sessions) or (set(contexts) | set(sessions)) & set(
        permit["allHmacRefs"]
    ):
        raise ReceiptError("browser context and session HMAC domains overlap")
    return issues, set(contexts) | set(sessions)


def _validate_journey(
    value: Any, permit: Mapping[str, Any]
) -> tuple[bool, list[dict[str, Any]], int, list[str]]:
    journey = _exact_object(value, JOURNEY_FIELDS, "journey")
    credentialed = journey["credentialedAttemptPerformed"]
    if not isinstance(credentialed, bool):
        raise ReceiptError("journey credentialedAttemptPerformed must be boolean")
    steps = journey["steps"]
    if not isinstance(steps, list) or len(steps) != len(ACTION_IDS):
        raise ReceiptError("journey action denominator is invalid")
    normalized: list[dict[str, Any]] = []
    writes = 0
    issues: list[str] = []
    for index, action_id in enumerate(ACTION_IDS):
        step = _exact_object(steps[index], STEP_FIELDS, f"journey step {index}")
        if step["actionId"] != action_id:
            raise ReceiptError("journey actions are missing, duplicated, unknown, or reordered")
        catalog = ACTION_CATALOG[action_id]
        mutating = catalog["mutating"]
        compensator = catalog["compensator"]
        if (
            step["role"] != catalog["role"]
            or step["mutating"] is not mutating
            or step["compensator"] != compensator
        ):
            raise ReceiptError("journey action authority, mutability, or compensator was relabeled")
        if step["status"] not in {"not_run", "blocked", "pass"}:
            raise ReceiptError("journey step status is invalid")
        attempts = _bounded_int(step["attempts"], f"{action_id}.attempts", 1)
        forward_writes = _bounded_int(
            step["forwardWrites"], f"{action_id}.forwardWrites", 1
        )
        cleanup_writes = _bounded_int(
            step["cleanupWrites"], f"{action_id}.cleanupWrites", 1
        )
        budget = permit["actions"][action_id]
        if (
            attempts > budget["attemptLimit"]
            or forward_writes > budget["forwardWriteLimit"]
            or cleanup_writes > budget["cleanupWriteLimit"]
            or cleanup_writes > forward_writes
            or forward_writes > attempts
        ):
            raise ReceiptError("journey action exceeded its permit budget")
        if not isinstance(step["assertionPassed"], bool) or not isinstance(
            step["compensatorAvailableBeforeWrite"], bool
        ):
            raise ReceiptError("journey step boolean evidence is malformed")
        evidence = step["evidenceSha256"]
        if step["status"] == "not_run":
            if (
                attempts != 0
                or forward_writes != 0
                or cleanup_writes != 0
                or step["assertionPassed"] is not False
                or step["compensatorAvailableBeforeWrite"] is not False
                or evidence is not None
            ):
                raise ReceiptError("not-run journey step contains contradictory execution facts")
        else:
            _sha(evidence, f"{action_id}.evidenceSha256")
        if forward_writes:
            if not mutating or step["compensatorAvailableBeforeWrite"] is not True:
                raise ReceiptError("forward write lacked an available compensator")
            _hmac_ref(
                step["serverIdempotencyKeyHmac"],
                f"{action_id}.serverIdempotencyKeyHmac",
            )
            _hmac_ref(
                step["revisionPreconditionHmac"],
                f"{action_id}.revisionPreconditionHmac",
            )
            _sha(step["journalIntentSha256"], f"{action_id}.journalIntentSha256")
        elif any(
            step[field] is not None
            for field in (
                "serverIdempotencyKeyHmac",
                "revisionPreconditionHmac",
                "journalIntentSha256",
            )
        ):
            raise ReceiptError("non-writing action fabricated write-control evidence")
        if step["status"] == "pass" and (
            budget["attemptLimit"] != 1
            or attempts != 1
            or step["assertionPassed"] is not True
            or forward_writes != budget["forwardWriteLimit"]
            or cleanup_writes != budget["cleanupWriteLimit"]
            or (
                mutating
                and (
                    compensator is None
                    or step["compensatorAvailableBeforeWrite"] is not True
                )
            )
        ):
            raise ReceiptError("pass step does not contain its exact authorized execution proof")
        if step["status"] != "pass" or step["assertionPassed"] is not True or attempts != 1:
            issues.append(f"journey:{action_id}:incomplete_or_failed")
        writes += forward_writes
        normalized.append(step)
    if not credentialed and any(
        step["attempts"] or step["forwardWrites"] for step in normalized
    ):
        raise ReceiptError("uncredentialed journey claims attempted actions")
    forward_controls = [
        step[field]
        for step in normalized
        if step["forwardWrites"]
        for field in ("serverIdempotencyKeyHmac", "revisionPreconditionHmac")
    ]
    if len(set(forward_controls)) != len(forward_controls) or set(
        forward_controls
    ) & set(permit["allHmacRefs"]):
        raise ReceiptError("forward write-control HMAC domains collide")
    return credentialed, normalized, writes, issues


def _validate_receipt_permit(
    value: Any,
    permit: Mapping[str, Any],
    *,
    permit_sha256: str,
    credentialed: bool,
    writes: int,
) -> tuple[dt.datetime | None, dt.datetime | None, list[str]]:
    row = _exact_object(value, RECEIPT_PERMIT_FIELDS, "receipt permit evidence")
    if (
        row["permitSha256"] != permit_sha256
        or row["permitId"] != permit["permitId"]
        or row["nonceRefHmac"] != permit["nonceRefHmac"]
        or row["replayLedgerRefHmac"] != permit["replayLedgerRefHmac"]
    ):
        raise ReceiptError("receipt permit evidence does not bind the permit")
    if not isinstance(row["nonceClaimed"], bool) or not isinstance(
        row["replayDetected"], bool
    ):
        raise ReceiptError("receipt permit replay evidence is malformed")
    started = _optional_timestamp(row["forwardStartedAtUtc"], "forwardStartedAtUtc")
    completed = _optional_timestamp(
        row["cleanupCompletedAtUtc"], "cleanupCompletedAtUtc"
    )
    if credentialed and row["nonceClaimed"] is not True:
        raise ReceiptError("credentialed attempt did not durably claim its one-time nonce")
    if not credentialed and (row["nonceClaimed"] or started is not None):
        raise ReceiptError("not-run receipt claims a consumed mutation nonce")
    if writes and started is None:
        raise ReceiptError("forward writes have no bound start time")
    if started is not None and not (
        permit["issuedAt"] <= started < permit["forwardExpiresAt"]
    ):
        raise ReceiptError("forward journey began outside the short permit window")
    if completed is not None and (
        started is None
        or completed < started
        or completed >= permit["cleanupExpiresAt"]
    ):
        raise ReceiptError("cleanup completion is outside its permit window")
    issues = ["permit:replay_detected"] if row["replayDetected"] else []
    return started, completed, issues


def _validate_cleanup(
    value: Any,
    steps: Sequence[Mapping[str, Any]],
    *,
    writes: int,
    cleanup_completed_at: dt.datetime | None,
    permit: Mapping[str, Any],
    account_session_refs: set[str],
) -> tuple[bool, int]:
    cleanup = _exact_object(value, CLEANUP_FIELDS, "cleanup")
    journal = _exact_object(
        cleanup["journal"], CLEANUP_JOURNAL_FIELDS, "cleanup journal"
    )
    _hmac_ref(journal["pathRefHmac"], "cleanup journal path reference")
    if (
        journal["mode"] != 0o600
        or journal["appendOnly"] is not True
        or journal["intentBeforeWrite"] is not True
        or journal["resultAfterResponse"] is not True
    ):
        raise ReceiptError("cleanup journal is not append-only mode-0600 write-ahead evidence")
    strategy = _exact_object(
        cleanup["strategy"], CLEANUP_STRATEGY_FIELDS, "cleanup strategy"
    )
    for field in CLEANUP_STRATEGY_FIELDS:
        if not isinstance(strategy[field], bool):
            raise ReceiptError(f"cleanup strategy {field} must be boolean")
    if (
        strategy["reverseOrder"] is not True
        or strategy["resumable"] is not True
        or strategy["finallyGuaranteed"] is not True
        or strategy["runOwnedIdsOnly"] is not True
        or strategy["broadDeletesUsed"] is not False
        or strategy["preExistingContentChanged"] is not False
    ):
        raise ReceiptError("cleanup strategy permits unsafe or broad mutation")

    expected_reverse = [
        step["actionId"] for step in reversed(steps) if step["forwardWrites"] == 1
    ]
    entries = cleanup["entries"]
    if not isinstance(entries, list) or len(entries) > writes:
        raise ReceiptError("cleanup journal entry denominator is invalid")
    for index, entry_value in enumerate(entries):
        entry = _exact_object(
            entry_value, CLEANUP_ENTRY_FIELDS, f"cleanup entry {index}"
        )
        if (
            type(entry["sequence"]) is not int
            or entry["sequence"] != index + 1
            or entry["actionId"] != expected_reverse[index]
        ):
            raise ReceiptError("cleanup entries are not the exact reverse write order")
        for field in (
            "resourceRefHmac",
            "idempotencyKeyHmac",
            "revisionPreconditionHmac",
        ):
            _hmac_ref(entry[field], f"cleanup entry {index}.{field}")
        _sha(entry["intentEvidenceSha256"], f"cleanup entry {index}.intentEvidenceSha256")
        _sha(
            entry["responseEvidenceSha256"],
            f"cleanup entry {index}.responseEvidenceSha256",
        )
        if entry["result"] not in {"pending", "failed", "cleaned"} or not isinstance(
            entry["acknowledged"], bool
        ):
            raise ReceiptError("cleanup entry result is malformed")
        forward_step = next(
            step for step in steps if step["actionId"] == entry["actionId"]
        )
        if entry["intentEvidenceSha256"] != forward_step["journalIntentSha256"]:
            raise ReceiptError("cleanup entry does not bind its forward write-ahead intent")
        if (
            entry["actionId"] == "campaign_create_or_join"
            and entry["resourceRefHmac"] != permit["canaryCampaignRefHmac"]
        ):
            raise ReceiptError("campaign cleanup does not bind the permitted canary resource")

    forward_controls = {
        step[field]
        for step in steps
        if step["forwardWrites"]
        for field in ("serverIdempotencyKeyHmac", "revisionPreconditionHmac")
    }
    cleanup_controls = [
        entry[field]
        for entry in entries
        for field in ("idempotencyKeyHmac", "revisionPreconditionHmac")
    ]
    resource_refs = [entry["resourceRefHmac"] for entry in entries]
    journal_ref = journal["pathRefHmac"]
    reserved = set(permit["allHmacRefs"]) | account_session_refs
    non_campaign_resources = {
        entry["resourceRefHmac"]
        for entry in entries
        if entry["actionId"] != "campaign_create_or_join"
    }
    if (
        len(cleanup_controls) != len(set(cleanup_controls))
        or set(cleanup_controls) & (forward_controls | reserved | {journal_ref})
        or len(resource_refs) != len(set(resource_refs))
        or non_campaign_resources
        & (forward_controls | set(cleanup_controls) | reserved | {journal_ref})
        or journal_ref in forward_controls
        or journal_ref in reserved
    ):
        raise ReceiptError("cleanup HMAC reference domains collide")

    observed_cleanup_counts = {
        action_id: sum(entry["actionId"] == action_id for entry in entries)
        for action_id in ACTION_IDS
    }
    if any(
        step["cleanupWrites"] != observed_cleanup_counts[step["actionId"]]
        for step in steps
    ):
        raise ReceiptError("cleanup write counts do not bind the journal")

    post = _exact_object(
        cleanup["postconditions"],
        CLEANUP_POSTCONDITION_FIELDS,
        "cleanup postconditions",
    )
    for field in (
        "compensatorsAcknowledged",
        "canonicalPostMatchesPre",
        "quotaUnchanged",
    ):
        if not isinstance(post[field], bool):
            raise ReceiptError(f"cleanup postcondition {field} must be boolean")
    for field in (
        "residualCampaignRows",
        "residualAuditRows",
        "residualRequestReceiptRows",
        "providerCallCount",
        "notificationCount",
    ):
        _bounded_int(post[field], f"cleanup postcondition {field}", 1_000_000)
    proved = (
        len(entries) == writes
        and all(
            entry["result"] == "cleaned" and entry["acknowledged"] is True
            for entry in entries
        )
        and post["compensatorsAcknowledged"] is True
        and post["canonicalPostMatchesPre"] is True
        and post["residualCampaignRows"] == 0
        and post["residualAuditRows"] == 0
        and post["residualRequestReceiptRows"] == 0
        and post["quotaUnchanged"] is True
        and post["providerCallCount"] == 0
        and post["notificationCount"] == 0
        and (writes == 0 or cleanup_completed_at is not None)
    )
    return proved, len(entries)


def _same_origin_url(value: Any) -> bool:
    if not isinstance(value, str) or len(value) > 2048:
        return False
    parsed = urlsplit(value)
    return (
        parsed.scheme == "https"
        and parsed.hostname is not None
        and parsed.hostname.rstrip(".").casefold() == "chummer.run"
        and parsed.username is None
        and parsed.password is None
        and parsed.port in {None, 443}
        and not parsed.query
        and not parsed.fragment
    )


def _validate_browser_ooda(
    value: Any,
    *,
    credentialed: bool,
    steps: Sequence[Mapping[str, Any]],
) -> list[str]:
    row = _exact_object(value, BROWSER_OODA_FIELDS, "browserOoda")
    if row["site"] != PRODUCTION_ORIGIN or row["requestedActions"] != list(ACTION_IDS):
        raise ReceiptError("browser OODA requested-action denominator is invalid")
    completed = row["completedActions"]
    if (
        not isinstance(completed, list)
        or completed != list(ACTION_IDS[: len(completed)])
    ):
        raise ReceiptError("browser OODA completed actions are not an exact prefix")
    if row["safeContext"] != "production_isolated_contexts":
        raise ReceiptError("browser OODA safe context is invalid")
    if row["qualityGate"] not in {"not_run", "blocked", "pass"}:
        raise ReceiptError("browser OODA quality gate is invalid")
    final_url = row["finalUrl"]
    if final_url is not None and not _same_origin_url(final_url):
        raise ReceiptError("browser OODA final URL is not same-origin production")
    if row["stopCondition"] not in {
        "not_started",
        "none",
        "approval_boundary",
        "identity_mismatch",
        "mfa",
        "captcha",
        "cloudflare",
        "blocker",
        "failure",
    }:
        raise ReceiptError("browser OODA stop condition is invalid")
    evidence = row["evidenceSha256s"]
    if not isinstance(evidence, list) or len(evidence) > 64:
        raise ReceiptError("browser OODA evidence denominator is invalid")
    for index, digest in enumerate(evidence):
        _sha(digest, f"browserOoda.evidenceSha256s[{index}]")
    if (
        row["notificationOutcome"] != "none"
        or type(row["irreversibleAttemptCount"]) is not int
        or row["irreversibleAttemptCount"] != 0
    ):
        raise ReceiptError("browser OODA crossed a prohibited action boundary")
    expected_evidence = [
        step["evidenceSha256"]
        for step in steps[: len(completed)]
        if step["evidenceSha256"] is not None
    ]
    if evidence != expected_evidence:
        raise ReceiptError("browser OODA evidence does not exactly bind completed journey steps")
    if not credentialed and (
        completed
        or evidence
        or final_url is not None
        or row["qualityGate"] != "not_run"
        or row["stopCondition"] != "not_started"
    ):
        raise ReceiptError("uncredentialed journey contradicts browser OODA execution facts")
    issues: list[str] = []
    if (
        row["qualityGate"] != "pass"
        or completed != list(ACTION_IDS)
        or final_url is None
        or row["stopCondition"] != "none"
    ):
        issues.append("browser_ooda:incomplete_or_blocked")
    return issues


def _reason_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or len(value) > 128:
        raise ReceiptError(f"{label} must be a bounded array")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or SAFE_REASON.fullmatch(item) is None:
            raise ReceiptError(f"{label} contains an unsafe reason")
        result.append(item)
    if result != sorted(set(result)):
        raise ReceiptError(f"{label} must be sorted and unique")
    return result


def validate_payloads(
    payload: dict[str, Any],
    permit_payload: dict[str, Any],
    *,
    permit_sha256: str,
    observed_at: dt.datetime,
) -> dict[str, Any]:
    """Validate receipt+permit and return the independently derived state."""

    receipt = _exact_object(payload, RECEIPT_FIELDS, "campaign receipt")
    _reject_sensitive(receipt)
    expected_permit_sha = _sha(permit_sha256, "permit_sha256")
    if observed_at.tzinfo is None or observed_at.utcoffset() != dt.timedelta(0):
        raise ReceiptError("observed_at must be timezone-aware UTC")
    now = observed_at.astimezone(dt.timezone.utc)
    if (
        receipt["contractName"] != RECEIPT_CONTRACT
        or type(receipt["contractVersion"]) is not int
        or receipt["contractVersion"] != 2
        or receipt["status"] not in STATUSES
        or receipt["secretRedacted"] is not True
    ):
        raise ReceiptError("campaign receipt identity is invalid")
    _safe_id(receipt["receiptId"], "receiptId")
    generated_at = _timestamp(receipt["generatedAtUtc"], "generatedAtUtc")
    if generated_at > now + dt.timedelta(seconds=MAX_FUTURE_SKEW_SECONDS):
        raise ReceiptError("campaign receipt is unreasonably in the future")

    release_binding = _validate_release_binding(
        receipt["releaseBinding"], "campaign receipt releaseBinding"
    )
    inputs = _exact_object(
        receipt["inputBindings"], INPUT_BINDING_FIELDS, "inputBindings"
    )
    for field in INPUT_BINDING_FIELDS:
        _sha(inputs[field], f"inputBindings.{field}")
    if not hmac.compare_digest(inputs["mutationPermitSha256"], expected_permit_sha):
        raise ReceiptError("campaign receipt does not bind the permit bytes")

    permit = _validate_permit(
        permit_payload, release_binding=release_binding, observed_at=now
    )
    issues = _validate_browser_policy(receipt["browserPolicy"])
    issues.extend(_validate_current_fence(receipt["currentFence"], release_binding))
    account_issues, account_session_refs = _validate_accounts(
        receipt["accounts"], permit
    )
    issues.extend(account_issues)
    credentialed, steps, writes, journey_issues = _validate_journey(
        receipt["journey"], permit
    )
    issues.extend(journey_issues)
    forward_started_at, cleanup_completed_at, permit_issues = _validate_receipt_permit(
        receipt["permit"],
        permit,
        permit_sha256=expected_permit_sha,
        credentialed=credentialed,
        writes=writes,
    )
    if (
        (forward_started_at is not None and generated_at < forward_started_at)
        or (cleanup_completed_at is not None and generated_at < cleanup_completed_at)
    ):
        raise ReceiptError("receipt generatedAtUtc predates bound execution evidence")
    issues.extend(permit_issues)
    cleanup_proved, cleanup_entries = _validate_cleanup(
        receipt["cleanup"],
        steps,
        writes=writes,
        cleanup_completed_at=cleanup_completed_at,
        permit=permit,
        account_session_refs=account_session_refs,
    )
    issues.extend(
        _validate_browser_ooda(
            receipt["browserOoda"], credentialed=credentialed, steps=steps
        )
    )
    blockers = _reason_list(receipt["blockers"], "blockers")
    failures = _reason_list(receipt["failures"], "failures")
    issues.extend(f"blocker:{item}" for item in blockers)
    issues.extend(f"failure:{item}" for item in failures)
    if not LIVE_PASS_AUTHORIZED:
        issues.append("authority:live_pass_not_authorized")

    if not credentialed and writes == 0:
        derived = "not_run"
    elif writes > 0 and not cleanup_proved:
        derived = "cleanup_required"
    elif issues:
        derived = "blocked"
    else:
        derived = "pass"
    if receipt["status"] != derived:
        raise ReceiptError("claimed status contradicts the independently derived state")
    readiness = derived == "pass"
    if receipt["operationalReadinessClaimAllowed"] is not readiness:
        raise ReceiptError("operational readiness claim contradicts the derived state")
    return {
        "status": derived,
        "operationalReadinessClaimAllowed": readiness,
        "receiptSha256": hashlib.sha256(canonical_bytes(receipt)).hexdigest(),
        "permitSha256": expected_permit_sha,
        "forwardWriteCount": writes,
        "cleanupEntryCount": cleanup_entries,
        "cleanupVerified": cleanup_proved,
        "blockerCount": len(blockers),
        "failureCount": len(failures),
    }


def build_outer_evidence(
    payload: dict[str, Any], validation: Mapping[str, Any]
) -> dict[str, Any]:
    """Build the deterministic, one-claim post-activation evidence envelope."""

    native_status = validation.get("status")
    receipt_sha = hashlib.sha256(canonical_bytes(payload)).hexdigest()
    if native_status == "pass" and not LIVE_PASS_AUTHORIZED:
        raise ReceiptError("production live-pass authority is unavailable")
    if (
        native_status not in STATUSES
        or native_status != payload.get("status")
        or validation.get("receiptSha256") != receipt_sha
        or validation.get("operationalReadinessClaimAllowed")
        is not (native_status == "pass")
    ):
        raise ReceiptError("cannot materialize evidence for an invalid native state")
    passed = native_status == "pass"
    return {
        "contractName": EVIDENCE_CONTRACT,
        "contractVersion": 1,
        "status": "pass" if passed else "attention_required",
        "secretRedacted": True,
        "evidenceId": _safe_id(payload.get("receiptId"), "receiptId"),
        "evidenceKind": EVIDENCE_KIND,
        "generatedAtUtc": payload.get("generatedAtUtc"),
        "releaseBinding": payload.get("releaseBinding"),
        "claims": [
            {
                "claimId": OUTER_CLAIM_ID,
                "status": "pass" if passed else "attention_required",
                "evidenceSha256": receipt_sha,
            }
        ],
        "operationalReadinessClaimAllowed": passed,
    }


def _strict_json(raw: bytes, label: str, *, require_canonical: bool = True) -> dict[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        folded: set[str] = set()
        for key, value in pairs:
            normalized = key.casefold()
            if normalized in folded:
                raise ReceiptError(f"{label} contains a duplicate or case-shadowed field")
            folded.add(normalized)
            result[key] = value
        return result

    try:
        payload = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=reject_duplicates,
            parse_constant=lambda value: (_ for _ in ()).throw(
                ReceiptError(f"{label} contains a non-finite number")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ReceiptError(f"{label} is not strict UTF-8 JSON") from error
    if not isinstance(payload, dict):
        raise ReceiptError(f"{label} must be a JSON object")
    if require_canonical and raw != canonical_bytes(payload):
        raise ReceiptError(f"{label} is not canonical JSON")
    return payload


def _workspace(path: Path) -> Path:
    if not path.is_absolute():
        raise ReceiptError("workspace must be absolute")
    try:
        lexical = os.lstat(path)
        root = path.resolve(strict=True)
        metadata = root.stat()
    except OSError as error:
        raise ReceiptError("workspace is unavailable") from error
    if (
        stat.S_ISLNK(lexical.st_mode)
        or not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or stat.S_IMODE(metadata.st_mode) != 0o700
    ):
        raise ReceiptError("workspace must be caller-owned non-symlink mode-0700")
    return root


def _confined(path: Path, root: Path, label: str) -> Path:
    if not path.is_absolute():
        raise ReceiptError(f"{label} must be absolute")
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as error:
        raise ReceiptError(f"{label} must remain beneath the workspace") from error
    if path.absolute() != resolved:
        raise ReceiptError(f"{label} must not use symlinks or non-canonical components")
    return resolved


def _stable_file(path: Path, root: Path, label: str) -> bytes:
    resolved = _confined(path, root, label)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    flags |= getattr(os, "O_NONBLOCK", 0)
    try:
        descriptor = os.open(resolved, flags)
    except OSError as error:
        raise ReceiptError(f"{label} could not be opened safely") from error
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.geteuid()
            or before.st_nlink != 1
            or stat.S_IMODE(before.st_mode) != 0o600
            or not 1 <= before.st_size <= MAX_INPUT_BYTES
        ):
            raise ReceiptError(
                f"{label} must be caller-owned single-link mode-0600 regular file"
            )
        chunks: list[bytes] = []
        remaining = before.st_size + 1
        while remaining:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    raw = b"".join(chunks)
    try:
        final = os.lstat(resolved)
    except OSError as error:
        raise ReceiptError(f"{label} changed during stable read") from error
    identity = lambda item: (
        item.st_dev,
        item.st_ino,
        item.st_size,
        item.st_mtime_ns,
        item.st_ctime_ns,
        item.st_mode,
        item.st_nlink,
    )
    if (
        identity(before) != identity(after)
        or identity(after) != identity(final)
        or len(raw) != before.st_size
        or stat.S_ISLNK(final.st_mode)
    ):
        raise ReceiptError(f"{label} changed during stable read")
    return raw


def _pinned_json(
    path: Path,
    expected_sha256: str,
    root: Path,
    label: str,
    *,
    require_canonical: bool = True,
) -> tuple[bytes, dict[str, Any]]:
    expected = _sha(expected_sha256, f"{label} expected SHA-256")
    raw = _stable_file(path, root, label)
    if not hmac.compare_digest(hashlib.sha256(raw).hexdigest(), expected):
        raise ReceiptError(f"{label} SHA-256 mismatch")
    return raw, _strict_json(raw, label, require_canonical=require_canonical)


def _write_new(path: Path, root: Path, raw: bytes) -> None:
    if not path.is_absolute():
        raise ReceiptError("output must be absolute")
    try:
        parent = path.parent.resolve(strict=True)
        parent.relative_to(root)
        metadata = parent.stat()
    except (OSError, ValueError) as error:
        raise ReceiptError("output parent must remain beneath the workspace") from error
    if path.parent.absolute() != parent or metadata.st_uid != os.geteuid():
        raise ReceiptError("output parent is unsafe")
    if path.exists() or path.is_symlink():
        raise ReceiptError("output already exists")
    temporary_name: str | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(prefix=".campaign-e2e-", dir=parent)
        os.fchmod(descriptor, 0o600)
        try:
            with os.fdopen(descriptor, "wb", closefd=True) as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
            os.link(temporary_name, path)
            directory = os.open(parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        except FileExistsError as error:
            raise ReceiptError("output already exists") from error
    finally:
        if temporary_name is not None:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass


def _release_binding_from_finalization(
    payload: dict[str, Any], *, observed_at: dt.datetime
) -> dict[str, str]:
    receipt = _exact_object(payload, FINALIZATION_FIELDS, "owner finalization receipt")
    if (
        receipt["contractName"] != "chummer.staged-release-owner-finalization/v1"
        or type(receipt["contractVersion"]) is not int
        or receipt["contractVersion"] != 1
        or receipt["status"] != "preview_ready"
    ):
        raise ReceiptError("owner finalization receipt is not preview_ready")
    binding = _validate_release_binding(
        {
            "releaseVersion": receipt["releaseVersion"],
            "generationId": receipt["generationId"],
            "manifestSha256": receipt["manifestSha256"],
            "decisionSha256": receipt["decisionSha256"],
            "snapshotSha256": receipt["snapshotSha256"],
            "targetPointerSha256": receipt["targetPointerSha256"],
        },
        "owner finalization releaseBinding",
    )
    _safe_id(receipt["stageReceiptId"], "owner finalization stageReceiptId")
    revision = receipt["authorityRevisionId"]
    if not isinstance(revision, str) or AUTHORITY_REVISION.fullmatch(revision) is None:
        raise ReceiptError("owner finalization authorityRevisionId is invalid")
    _sha(
        receipt["releaseScopeDecisionSha256"],
        "owner finalization releaseScopeDecisionSha256",
    )
    _sha(
        receipt["releaseScopeVerificationSha256"],
        "owner finalization releaseScopeVerificationSha256",
    )
    _desktop_scope(receipt["exactIncomingDesktopScope"])
    if _timestamp(receipt["completedAtUtc"], "owner finalization completedAtUtc") > observed_at:
        raise ReceiptError("owner finalization receipt is in the future")
    return binding


def _validate_not_run_release_inputs(
    convergence: dict[str, Any],
    manifest: dict[str, Any],
    manifest_raw: bytes,
    binding: Mapping[str, str],
    finalization: Mapping[str, Any],
    *,
    observed_at: dt.datetime,
) -> None:
    if set(convergence) != CONVERGENCE_FIELDS:
        raise ReceiptError("generation convergence has an unexpected field set")
    try:
        truth = CONVERGENCE_HELPERS.canonicalize_projection(
            convergence.get("releaseTruth"), source="generation convergence releaseTruth"
        )
        manifest_truth = CONVERGENCE_HELPERS.canonicalize_projection(
            manifest.get("releaseTruth"), source="generation manifest releaseTruth"
        )
        CONVERGENCE_HELPERS._validate_native_manifest_claims(
            manifest, truth, source="generation manifest"
        )
        install_route = CONVERGENCE_HELPERS.discover_install_route(
            manifest_raw, generation_id=binding["generationId"]
        )
    except CONVERGENCE_HELPERS.ConvergenceError as error:
        raise ReceiptError("generation release inputs are not producer-valid") from error

    checked_routes = convergence.get("checkedRoutes")
    expected_routes = set(
        CONVERGENCE_HELPERS.generation_routes(binding["generationId"])
    )
    if truth["artifactCount"] > 0:
        if install_route is None:
            raise ReceiptError("generation manifest has no canonical install route")
        expected_routes.add(install_route)
    generated_at = _timestamp(
        convergence.get("generatedAtUtc"), "generation convergence generatedAtUtc"
    )
    completed_at = _timestamp(
        finalization.get("completedAtUtc"), "owner finalization completedAtUtc"
    )
    if (
        convergence.get("contractName") != "chummer.live-release-convergence/v1"
        or type(convergence.get("contractVersion")) is not int
        or convergence.get("contractVersion") != 1
        or convergence.get("verificationMode") != "committed_public"
        or convergence.get("status") != "pass"
        or type(convergence.get("mismatchCount")) is not int
        or convergence.get("mismatchCount") != 0
        or type(convergence.get("failureCount")) is not int
        or convergence.get("failureCount") != 0
        or convergence.get("mismatches") != []
        or convergence.get("failures") != []
        or convergence.get("releaseVersion") != binding["releaseVersion"]
        or convergence.get("manifestSha256") != binding["manifestSha256"]
        or convergence.get("releaseDecisionStatus") != finalization.get("status")
        or convergence.get("releaseDecisionSha256") != binding["decisionSha256"]
        or convergence.get("authoritySnapshotSha256") != binding["snapshotSha256"]
        or convergence.get("authorityRoute")
        != f"/api/v1/public/release-truth/g/{binding['generationId']}"
        or not isinstance(checked_routes, list)
        or checked_routes != sorted(expected_routes)
        or convergence.get("checkedRouteCount") != len(expected_routes)
        or convergence.get("comparedFields")
        != list(CONVERGENCE_HELPERS.REQUIRED_FIELDS)
        or truth != convergence.get("releaseTruth")
        or manifest_truth != manifest.get("releaseTruth")
        or manifest_truth != truth
        or truth["releaseVersion"] != binding["releaseVersion"]
        or truth["manifestSha256"] != binding["manifestSha256"]
        or truth["releaseDecisionStatus"] != finalization.get("status")
        or truth["releaseDecisionSha256"] != binding["decisionSha256"]
        or not CONVERGENCE_HELPERS._availability_claims_allowed(truth)
        or generated_at < completed_at
        or generated_at > observed_at + dt.timedelta(seconds=MAX_FUTURE_SKEW_SECONDS)
        or observed_at - generated_at
        > dt.timedelta(seconds=MAX_EVIDENCE_AGE_SECONDS)
    ):
        raise ReceiptError("generation convergence does not bind the finalized release")


def _parse_role_hmac_map(values: Sequence[str], label: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for value in values:
        if value.count("=") != 1:
            raise ReceiptError(f"{label} must use ROLE=HMAC")
        role, reference = value.split("=", 1)
        if role not in ROLES or role in result:
            raise ReceiptError(f"{label} has an invalid or duplicate role")
        result[role] = _hmac_ref(reference, f"{label}.{role}")
    if set(result) != set(ROLES):
        raise ReceiptError(f"{label} must cover the exact role denominator")
    return result


def materialize_not_run(
    *,
    workspace: Path,
    finalization_path: Path,
    finalization_sha256: str,
    convergence_path: Path,
    convergence_sha256: str,
    manifest_path: Path,
    manifest_sha256: str,
    permit_path: Path,
    permit_sha256: str,
    receipt_id: str,
    browser_context_refs: Mapping[str, str],
    browser_session_refs: Mapping[str, str],
    cleanup_journal_ref_hmac: str,
    output: Path,
    observed_at: dt.datetime | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Materialize only an honest, non-attempted receipt from pinned authority.

    This path performs no network call and has no code path capable of emitting
    ``pass``.  Caller-supplied digests and opaque HMAC references are integrity
    and domain-separation inputs only; this offline path does not establish
    independent authorization, identity, or browser provenance.
    """

    root = _workspace(workspace)
    now = observed_at or dt.datetime.now(dt.timezone.utc)
    if now.tzinfo is None or now.utcoffset() != dt.timedelta(0):
        raise ReceiptError("observed_at must be timezone-aware UTC")
    now = now.astimezone(dt.timezone.utc)
    final_raw, finalization = _pinned_json(
        finalization_path, finalization_sha256, root, "owner finalization receipt"
    )
    convergence_raw, convergence = _pinned_json(
        convergence_path,
        convergence_sha256,
        root,
        "generation convergence",
        require_canonical=False,
    )
    manifest_raw, manifest = _pinned_json(
        manifest_path,
        manifest_sha256,
        root,
        "generation manifest",
        require_canonical=False,
    )
    permit_raw, permit_payload = _pinned_json(
        permit_path, permit_sha256, root, "mutation permit"
    )
    binding = _release_binding_from_finalization(finalization, observed_at=now)
    _validate_not_run_release_inputs(
        convergence,
        manifest,
        manifest_raw,
        binding,
        finalization,
        observed_at=now,
    )
    pinned_permit = hashlib.sha256(permit_raw).hexdigest()
    permit = _validate_permit(
        permit_payload, release_binding=binding, observed_at=now
    )
    if not (permit["issuedAt"] <= now < permit["forwardExpiresAt"]):
        raise ReceiptError("not-run materialization requires a currently valid permit")
    contexts = {
        role: _hmac_ref(browser_context_refs.get(role), f"{role} browser context")
        for role in ROLES
    }
    sessions = {
        role: _hmac_ref(browser_session_refs.get(role), f"{role} browser session")
        for role in ROLES
    }
    journal_ref = _hmac_ref(cleanup_journal_ref_hmac, "cleanup journal reference")
    if journal_ref in set(contexts.values()) | set(sessions.values()):
        raise ReceiptError("cleanup journal and browser HMAC domains overlap")
    generated = now.isoformat(timespec="microseconds").replace("+00:00", "Z")
    steps = [
        {
            "actionId": action_id,
            "role": ACTION_CATALOG[action_id]["role"],
            "status": "not_run",
            "mutating": ACTION_CATALOG[action_id]["mutating"],
            "attempts": 0,
            "forwardWrites": 0,
            "cleanupWrites": 0,
            "assertionPassed": False,
            "compensator": ACTION_CATALOG[action_id]["compensator"],
            "compensatorAvailableBeforeWrite": False,
            "serverIdempotencyKeyHmac": None,
            "revisionPreconditionHmac": None,
            "journalIntentSha256": None,
            "evidenceSha256": None,
        }
        for action_id in ACTION_IDS
    ]
    receipt: dict[str, Any] = {
        "contractName": RECEIPT_CONTRACT,
        "contractVersion": 2,
        "receiptId": _safe_id(receipt_id, "receiptId"),
        "generatedAtUtc": generated,
        "status": "not_run",
        "secretRedacted": True,
        "operationalReadinessClaimAllowed": False,
        "releaseBinding": binding,
        "inputBindings": {
            "mutationPermitSha256": pinned_permit,
            "ownerFinalizationReceiptSha256": hashlib.sha256(final_raw).hexdigest(),
            "generationConvergenceSha256": hashlib.sha256(convergence_raw).hexdigest(),
            "generationManifestFileSha256": hashlib.sha256(manifest_raw).hexdigest(),
        },
        "browserPolicy": {
            "allowedOrigin": PRODUCTION_ORIGIN,
            "sameOriginOnly": True,
            "redirectsFollowed": False,
            "requestInterceptionUsed": False,
            "testIdentityHeadersUsed": False,
            "adminSessionUsed": False,
            "sharedBrowserContextUsed": False,
            "crossOriginRequestsPerformed": False,
            "providerCallsPerformed": False,
            "notificationsSent": False,
            "publicationsPerformed": False,
            "accountChangesPerformed": False,
            "securityChangesPerformed": False,
            "paymentsPerformed": False,
            "purchasesPerformed": False,
            "irreversibleActionsPerformed": False,
            "stopOnApprovalBoundary": True,
            "stopOnIdentityMismatch": True,
            "stopOnMfa": True,
            "stopOnCaptcha": True,
            "stopOnCloudflare": True,
        },
        "currentFence": {
            "preCurrent": None,
            "postCurrent": None,
            "stable": False,
        },
        "accounts": [
            {
                "role": role,
                "accountRefHmac": permit["roleAccountRefs"][role],
                "browserContextRefHmac": contexts[role],
                "browserSessionRefHmac": sessions[role],
                "visibleIdentityMatched": False,
            }
            for role in ROLES
        ],
        "journey": {"credentialedAttemptPerformed": False, "steps": steps},
        "permit": {
            "permitSha256": pinned_permit,
            "permitId": permit["permitId"],
            "nonceRefHmac": permit["nonceRefHmac"],
            "replayLedgerRefHmac": permit["replayLedgerRefHmac"],
            "nonceClaimed": False,
            "replayDetected": False,
            "forwardStartedAtUtc": None,
            "cleanupCompletedAtUtc": None,
        },
        "cleanup": {
            "journal": {
                "pathRefHmac": journal_ref,
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
            "entries": [],
            "postconditions": {
                "compensatorsAcknowledged": True,
                "canonicalPostMatchesPre": True,
                "residualCampaignRows": 0,
                "residualAuditRows": 0,
                "residualRequestReceiptRows": 0,
                "quotaUnchanged": True,
                "providerCallCount": 0,
                "notificationCount": 0,
            },
        },
        "browserOoda": {
            "site": PRODUCTION_ORIGIN,
            "requestedActions": list(ACTION_IDS),
            "completedActions": [],
            "safeContext": "production_isolated_contexts",
            "qualityGate": "not_run",
            "finalUrl": None,
            "stopCondition": "not_started",
            "evidenceSha256s": [],
            "notificationOutcome": "none",
            "irreversibleAttemptCount": 0,
        },
        "blockers": ["credentialed_journey_not_started"],
        "failures": [],
    }
    validation = validate_payloads(
        receipt,
        permit_payload,
        permit_sha256=pinned_permit,
        observed_at=now,
    )
    if validation["status"] != "not_run":
        raise ReceiptError("not-run materializer derived an impossible state")
    _write_new(output, root, canonical_bytes(receipt))
    return receipt, validation


def verify_files(
    *,
    workspace: Path,
    receipt_path: Path,
    receipt_sha256: str,
    permit_path: Path,
    permit_sha256: str,
    output: Path | None = None,
    observed_at: dt.datetime | None = None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    root = _workspace(workspace)
    _, receipt = _pinned_json(receipt_path, receipt_sha256, root, "campaign receipt")
    permit_raw, permit = _pinned_json(permit_path, permit_sha256, root, "mutation permit")
    now = observed_at or dt.datetime.now(dt.timezone.utc)
    validation = validate_payloads(
        receipt,
        permit,
        permit_sha256=hashlib.sha256(permit_raw).hexdigest(),
        observed_at=now,
    )
    evidence = None
    if output is not None:
        evidence = build_outer_evidence(receipt, validation)
        _write_new(output, root, canonical_bytes(evidence))
    return validation, evidence


def _args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Offline validation of a governed campaign v2 receipt and permit."
    )
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--expected-receipt-sha256")
    parser.add_argument("--permit", type=Path, required=True)
    parser.add_argument("--expected-permit-sha256", required=True)
    parser.add_argument(
        "--materialize-not-run",
        action="store_true",
        help="Create only a pinned, non-attempted native receipt; never runs a browser.",
    )
    parser.add_argument("--finalization-receipt", type=Path)
    parser.add_argument("--expected-finalization-sha256")
    parser.add_argument("--generation-convergence", type=Path)
    parser.add_argument("--expected-generation-convergence-sha256")
    parser.add_argument("--generation-manifest", type=Path)
    parser.add_argument("--expected-generation-manifest-sha256")
    parser.add_argument("--receipt-id")
    parser.add_argument(
        "--browser-context-ref", action="append", default=[], metavar="ROLE=HMAC"
    )
    parser.add_argument(
        "--browser-session-ref", action="append", default=[], metavar="ROLE=HMAC"
    )
    parser.add_argument("--cleanup-journal-ref-hmac")
    parser.add_argument(
        "--output",
        type=Path,
        help=(
            "Create an outer evidence envelope in verification mode, or the native "
            "not-run receipt in materialization mode."
        ),
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = _args(argv)
        if args.materialize_not_run:
            if args.receipt is not None or args.expected_receipt_sha256 is not None:
                raise ReceiptError("verification inputs cannot be mixed with materialization")
            required = {
                "finalization receipt": args.finalization_receipt,
                "finalization digest": args.expected_finalization_sha256,
                "generation convergence": args.generation_convergence,
                "generation convergence digest": args.expected_generation_convergence_sha256,
                "generation manifest": args.generation_manifest,
                "generation manifest digest": args.expected_generation_manifest_sha256,
                "receipt ID": args.receipt_id,
                "cleanup journal reference": args.cleanup_journal_ref_hmac,
                "output": args.output,
            }
            if any(value is None or value == "" for value in required.values()):
                raise ReceiptError("not-run materialization inputs are incomplete")
            contexts = _parse_role_hmac_map(
                args.browser_context_ref, "--browser-context-ref"
            )
            sessions = _parse_role_hmac_map(
                args.browser_session_ref, "--browser-session-ref"
            )
            _, validation = materialize_not_run(
                workspace=args.workspace,
                finalization_path=args.finalization_receipt,
                finalization_sha256=args.expected_finalization_sha256,
                convergence_path=args.generation_convergence,
                convergence_sha256=args.expected_generation_convergence_sha256,
                manifest_path=args.generation_manifest,
                manifest_sha256=args.expected_generation_manifest_sha256,
                permit_path=args.permit,
                permit_sha256=args.expected_permit_sha256,
                receipt_id=args.receipt_id,
                browser_context_refs=contexts,
                browser_session_refs=sessions,
                cleanup_journal_ref_hmac=args.cleanup_journal_ref_hmac,
                output=args.output,
            )
        else:
            materialization_only = (
                args.finalization_receipt,
                args.expected_finalization_sha256,
                args.generation_convergence,
                args.expected_generation_convergence_sha256,
                args.generation_manifest,
                args.expected_generation_manifest_sha256,
                args.receipt_id,
                args.cleanup_journal_ref_hmac,
                *args.browser_context_ref,
                *args.browser_session_ref,
            )
            if any(value is not None and value != "" for value in materialization_only):
                raise ReceiptError("materialization inputs cannot be mixed with verification")
            if args.receipt is None or args.expected_receipt_sha256 is None:
                raise ReceiptError("receipt and expected receipt digest are required")
            validation, _ = verify_files(
                workspace=args.workspace,
                receipt_path=args.receipt,
                receipt_sha256=args.expected_receipt_sha256,
                permit_path=args.permit,
                permit_sha256=args.expected_permit_sha256,
                output=args.output,
            )
    except (ReceiptError, OSError, KeyError, TypeError, ValueError):
        print("governed_campaign_e2e:malformed", file=sys.stderr)
        return 1
    status = validation["status"]
    print(f"governed_campaign_e2e:{status}")
    return EXIT_CODES[status]


if __name__ == "__main__":
    raise SystemExit(main())
