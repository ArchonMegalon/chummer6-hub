from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
import os
from pathlib import Path

import pytest

from scripts import verify_governed_campaign_e2e_receipt as verifier


TEST_NOW = dt.datetime(2026, 7, 21, 12, 0, tzinfo=dt.timezone.utc)
TARGET = {
    "releaseVersion": "run-20260728-050000",
    "generationId": "generation-20260721",
    "manifestSha256": "a" * 64,
    "decisionSha256": "b" * 64,
    "snapshotSha256": "c" * 64,
    "targetPointerSha256": "d" * 64,
}


def hmac_ref(label: str) -> str:
    return hashlib.sha256(("operator-hmac:" + label).encode()).hexdigest()


def digest(label: str) -> str:
    return hashlib.sha256(("evidence:" + label).encode()).hexdigest()


def utc(value: dt.datetime) -> str:
    return (
        value.astimezone(dt.timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def build_permit(
    *,
    now: dt.datetime = TEST_NOW,
    release_binding: dict[str, str] | None = None,
) -> dict[str, object]:
    binding = copy.deepcopy(release_binding or TARGET)
    actions = []
    forward_total = 0
    cleanup_total = 0
    for action_id in verifier.ACTION_IDS:
        catalog = verifier.ACTION_CATALOG[action_id]
        forward_total += catalog["forwardWriteLimit"]
        cleanup_total += catalog["cleanupWriteLimit"]
        actions.append(
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
        "contractName": verifier.PERMIT_CONTRACT,
        "contractVersion": 2,
        "status": "approved",
        "secretRedacted": True,
        "permitId": "permit-governed-campaign-20260721",
        "issuedAtUtc": utc(now - dt.timedelta(minutes=5)),
        "forwardExpiresAtUtc": utc(now + dt.timedelta(minutes=30)),
        "cleanupExpiresAtUtc": utc(now + dt.timedelta(hours=2)),
        "allowedOrigin": verifier.PRODUCTION_ORIGIN,
        "releaseBinding": binding,
        "ownerAuthorization": {
            "authorizationRefHmac": hmac_ref("owner-authorization"),
            "authorizedByRefHmac": hmac_ref("owner-authorizer"),
            "authorizedAtUtc": utc(now - dt.timedelta(minutes=10)),
            "producerIndependent": True,
        },
        "canaryCampaignRefHmac": hmac_ref("canary-campaign"),
        "roleAccountRefHmacs": {
            role: hmac_ref("account:" + role) for role in verifier.ROLES
        },
        "actions": actions,
        "totalForwardWriteLimit": forward_total,
        "totalCleanupWriteLimit": cleanup_total,
        "nonceRefHmac": hmac_ref("permit-nonce"),
        "replayLedgerRefHmac": hmac_ref("replay-ledger"),
        "irreversibleActionsAllowed": False,
        "notificationsAllowed": False,
    }


def build_receipt(
    permit: dict[str, object],
    *,
    status: str = "not_run",
    now: dt.datetime = TEST_NOW,
    release_binding: dict[str, str] | None = None,
    input_bindings: dict[str, str] | None = None,
    permit_sha256: str | None = None,
    owner_finalization_sha256: str | None = None,
    generation_convergence_sha256: str | None = None,
    generation_manifest_sha256: str | None = None,
    current_snapshot: dict[str, str] | None = None,
    generated_at: dt.datetime | None = None,
) -> dict[str, object]:
    binding = copy.deepcopy(release_binding or permit["releaseBinding"])
    pinned_permit = permit_sha256 or hashlib.sha256(
        verifier.canonical_bytes(permit)
    ).hexdigest()
    bindings = copy.deepcopy(input_bindings) if input_bindings is not None else {
        "mutationPermitSha256": pinned_permit,
        "ownerFinalizationReceiptSha256": owner_finalization_sha256
        or digest("owner-finalization"),
        "generationConvergenceSha256": generation_convergence_sha256
        or digest("generation-convergence"),
        "generationManifestFileSha256": generation_manifest_sha256
        or digest("generation-manifest"),
    }
    snapshot = copy.deepcopy(current_snapshot) if current_snapshot is not None else {
        **binding,
        "responseSha256": digest("current-response"),
    }
    steps = []
    for action_id in verifier.ACTION_IDS:
        catalog = verifier.ACTION_CATALOG[action_id]
        steps.append(
            {
                "actionId": action_id,
                "role": catalog["role"],
                "status": "not_run",
                "mutating": catalog["mutating"],
                "attempts": 0,
                "forwardWrites": 0,
                "cleanupWrites": 0,
                "assertionPassed": False,
                "compensator": catalog["compensator"],
                "compensatorAvailableBeforeWrite": False,
                "serverIdempotencyKeyHmac": None,
                "revisionPreconditionHmac": None,
                "journalIntentSha256": None,
                "evidenceSha256": None,
            }
        )
    receipt: dict[str, object] = {
        "contractName": verifier.RECEIPT_CONTRACT,
        "contractVersion": 2,
        "receiptId": "campaign-e2e-receipt-20260721",
        "generatedAtUtc": utc(generated_at or now),
        "status": "not_run",
        "secretRedacted": True,
        "operationalReadinessClaimAllowed": False,
        "releaseBinding": binding,
        "inputBindings": bindings,
        "browserPolicy": {
            "allowedOrigin": verifier.PRODUCTION_ORIGIN,
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
                "accountRefHmac": permit["roleAccountRefHmacs"][role],
                "browserContextRefHmac": hmac_ref("browser-context:" + role),
                "browserSessionRefHmac": hmac_ref("browser-session:" + role),
                "visibleIdentityMatched": False,
            }
            for role in verifier.ROLES
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
                "pathRefHmac": hmac_ref("cleanup-journal-path"),
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
            "site": verifier.PRODUCTION_ORIGIN,
            "requestedActions": list(verifier.ACTION_IDS),
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
    if status == "blocked":
        receipt["status"] = "blocked"
        receipt["journey"]["credentialedAttemptPerformed"] = True
        receipt["permit"]["nonceClaimed"] = True
        receipt["browserOoda"].update(
            qualityGate="blocked",
            stopCondition="blocker",
        )
        receipt["blockers"] = ["credentialed_preflight_blocked"]
    elif status == "pass":
        receipt["status"] = "pass"
        receipt["operationalReadinessClaimAllowed"] = True
        receipt["journey"]["credentialedAttemptPerformed"] = True
        receipt["permit"]["nonceClaimed"] = True
        for step in receipt["journey"]["steps"]:
            step.update(
                status="pass",
                attempts=1,
                assertionPassed=True,
                evidenceSha256=digest("synthetic-pass:" + step["actionId"]),
            )
        receipt["browserOoda"].update(
            completedActions=list(verifier.ACTION_IDS),
            qualityGate="pass",
            finalUrl="https://chummer.run/campaigns/governed-canary",
            stopCondition="none",
            evidenceSha256s=[step["evidenceSha256"] for step in receipt["journey"]["steps"]],
        )
        receipt["blockers"] = []
    elif status == "cleanup_required":
        receipt["status"] = "cleanup_required"
        receipt["journey"]["credentialedAttemptPerformed"] = True
        receipt["permit"]["nonceClaimed"] = True
        first = receipt["journey"]["steps"][0]
        first.update(
            status="blocked",
            attempts=1,
            forwardWrites=1,
            assertionPassed=False,
            compensatorAvailableBeforeWrite=False,
            evidenceSha256=digest("synthetic-write"),
        )
        receipt["blockers"] = ["synthetic_unauthorized_write"]
    elif status != "not_run":
        raise ValueError(status)
    return receipt


def validate(
    receipt: dict[str, object],
    permit: dict[str, object],
    *,
    observed_at: dt.datetime = TEST_NOW,
) -> dict[str, object]:
    return verifier.validate_payloads(
        receipt,
        permit,
        permit_sha256=hashlib.sha256(verifier.canonical_bytes(permit)).hexdigest(),
        observed_at=observed_at,
    )


@pytest.mark.parametrize("status", ("not_run", "blocked"))
def test_only_non_ready_terminal_states_are_currently_valid(status: str) -> None:
    permit = build_permit()
    result = validate(build_receipt(permit, status=status), permit)
    assert result["status"] == status
    assert result["operationalReadinessClaimAllowed"] is False


def test_catalog_keeps_every_mutation_unavailable_and_quota_denial_mutating() -> None:
    assert verifier.LIVE_PASS_AUTHORIZED is False
    for action_id, catalog in verifier.ACTION_CATALOG.items():
        assert "method" not in catalog
        assert "route" not in catalog
        if catalog["mutating"]:
            assert catalog["attemptLimit"] == 0
            assert catalog["forwardWriteLimit"] == 0
            assert catalog["cleanupWriteLimit"] == 0
            assert catalog["compensator"] is None
    quota = verifier.ACTION_CATALOG["depleted_runner_quota_denial"]
    assert quota["mutating"] is True
    assert verifier.ACTION_CATALOG["runsite_cross_user_privacy"] == {
        "role": "alice_runner",
        "mutating": False,
        "attemptLimit": 1,
        "forwardWriteLimit": 0,
        "cleanupWriteLimit": 0,
        "compensator": None,
    }


@pytest.mark.parametrize("status", ("pass", "cleanup_required"))
def test_synthetic_ready_or_write_receipts_are_rejected(status: str) -> None:
    permit = build_permit()
    with pytest.raises(verifier.ReceiptError):
        validate(build_receipt(permit, status=status), permit)


def test_outer_evidence_is_deterministic_and_binds_canonical_receipt() -> None:
    permit = build_permit()
    receipt = build_receipt(permit)
    validation = validate(receipt, permit)
    first = verifier.build_outer_evidence(receipt, validation)
    second = verifier.build_outer_evidence(receipt, validation)
    assert first == second
    assert first["claims"] == [
        {
            "claimId": verifier.OUTER_CLAIM_ID,
            "status": "attention_required",
            "evidenceSha256": hashlib.sha256(
                verifier.canonical_bytes(receipt)
            ).hexdigest(),
        }
    ]
    assert first["status"] == "attention_required"
    assert first["operationalReadinessClaimAllowed"] is False


def test_rejects_claimed_status_and_readiness_bypasses() -> None:
    permit = build_permit()
    receipt = build_receipt(permit)
    receipt["status"] = "pass"
    receipt["operationalReadinessClaimAllowed"] = True
    with pytest.raises(verifier.ReceiptError, match="claimed status"):
        validate(receipt, permit)
    receipt = build_receipt(permit)
    receipt["operationalReadinessClaimAllowed"] = True
    with pytest.raises(verifier.ReceiptError, match="readiness claim"):
        validate(receipt, permit)


@pytest.mark.parametrize("field", ["role", "mutating", "compensator"])
def test_rejects_relabelled_action_authority(field: str) -> None:
    permit = build_permit()
    receipt = build_receipt(permit)
    receipt["journey"]["steps"][0][field] = "drift" if field != "mutating" else False
    with pytest.raises(verifier.ReceiptError, match="relabeled"):
        validate(receipt, permit)


def test_rejects_action_reordering_and_unknown_fields() -> None:
    permit = build_permit()
    receipt = build_receipt(permit)
    receipt["journey"]["steps"][0], receipt["journey"]["steps"][1] = (
        receipt["journey"]["steps"][1],
        receipt["journey"]["steps"][0],
    )
    with pytest.raises(verifier.ReceiptError, match="reordered"):
        validate(receipt, permit)
    receipt = build_receipt(permit)
    receipt["unexpected"] = True
    with pytest.raises(verifier.ReceiptError, match="field set"):
        validate(receipt, permit)


@pytest.mark.parametrize("container", ("permit", "step"))
def test_method_and_route_are_not_authority_fields(container: str) -> None:
    permit = build_permit()
    if container == "permit":
        target = permit["actions"][0]
        receipt = None
    else:
        receipt = build_receipt(permit)
        target = receipt["journey"]["steps"][0]
    target["method"] = "POST"
    target["route"] = "/invented"
    if receipt is None:
        receipt = build_receipt(permit)
    with pytest.raises(verifier.ReceiptError, match="field set"):
        validate(receipt, permit)


@pytest.mark.parametrize("field", ["attemptLimit", "forwardWriteLimit", "cleanupWriteLimit"])
def test_permit_numeric_budgets_reject_booleans(field: str) -> None:
    permit = build_permit()
    permit["actions"][0][field] = True
    receipt = build_receipt(permit)
    with pytest.raises(verifier.ReceiptError, match="budget"):
        validate(receipt, permit)


@pytest.mark.parametrize(
    "field", ["totalForwardWriteLimit", "totalCleanupWriteLimit"]
)
def test_permit_aggregate_budgets_reject_booleans(field: str) -> None:
    permit = build_permit()
    permit[field] = False
    receipt = build_receipt(permit)
    with pytest.raises(verifier.ReceiptError, match="aggregate budgets"):
        validate(receipt, permit)


def test_browser_ooda_irreversible_attempt_count_rejects_boolean() -> None:
    permit = build_permit()
    receipt = build_receipt(permit)
    receipt["browserOoda"]["irreversibleAttemptCount"] = False
    with pytest.raises(verifier.ReceiptError, match="prohibited action boundary"):
        validate(receipt, permit)


def test_rejects_raw_secret_fields_but_allows_required_credentialed_flag() -> None:
    permit = build_permit()
    receipt = build_receipt(permit)
    assert validate(receipt, permit)["status"] == "not_run"
    receipt["journey"]["rawCredential"] = "secret-value"
    with pytest.raises(verifier.ReceiptError, match="sensitive field"):
        validate(receipt, permit)


def test_rejects_raw_email_even_inside_an_allowed_string_field() -> None:
    permit = build_permit()
    receipt = build_receipt(permit)
    receipt["receiptId"] = "operator@example.com"
    with pytest.raises(verifier.ReceiptError, match="sensitive material"):
        validate(receipt, permit)


def test_rejects_shared_context_or_session_hmac() -> None:
    permit = build_permit()
    receipt = build_receipt(permit)
    receipt["accounts"][1]["browserContextRefHmac"] = receipt["accounts"][0][
        "browserContextRefHmac"
    ]
    with pytest.raises(verifier.ReceiptError, match="distinct browser"):
        validate(receipt, permit)


def test_rejects_fabricated_write_controls_on_read_only_action() -> None:
    permit = build_permit()
    for field in (
        "serverIdempotencyKeyHmac",
        "revisionPreconditionHmac",
        "journalIntentSha256",
    ):
        receipt = build_receipt(permit, status="blocked")
        step = receipt["journey"]["steps"][-1]
        step.update(
            status="blocked",
            attempts=1,
            evidenceSha256=digest("runsite-blocked"),
        )
        step[field] = digest("fabricated:" + field)
        with pytest.raises(verifier.ReceiptError, match="fabricated write-control"):
            validate(receipt, permit)


def test_rejects_cleanup_journal_and_browser_context_collision() -> None:
    permit = build_permit()
    receipt = build_receipt(permit)
    receipt["cleanup"]["journal"]["pathRefHmac"] = receipt["accounts"][0][
        "browserContextRefHmac"
    ]
    with pytest.raises(verifier.ReceiptError, match="domains collide"):
        validate(receipt, permit)


def test_rejects_cleanup_entry_without_an_authorized_forward_write() -> None:
    permit = build_permit()
    receipt = build_receipt(permit)
    receipt["cleanup"]["entries"] = [
        {
            "sequence": 1,
            "actionId": "campaign_create_or_join",
            "resourceRefHmac": permit["canaryCampaignRefHmac"],
            "idempotencyKeyHmac": hmac_ref("unauthorized-cleanup-idempotency"),
            "revisionPreconditionHmac": hmac_ref("unauthorized-cleanup-revision"),
            "intentEvidenceSha256": digest("unauthorized-forward-intent"),
            "responseEvidenceSha256": digest("unauthorized-cleanup-response"),
            "result": "cleaned",
            "acknowledged": True,
        }
    ]
    with pytest.raises(verifier.ReceiptError, match="entry denominator"):
        validate(receipt, permit)


def test_cleanup_rejects_broad_delete() -> None:
    permit = build_permit()
    receipt = build_receipt(permit)
    receipt["cleanup"]["strategy"]["broadDeletesUsed"] = True
    with pytest.raises(verifier.ReceiptError, match="unsafe"):
        validate(receipt, permit)


def test_not_run_uses_an_explicitly_unobserved_current_fence() -> None:
    permit = build_permit()
    receipt = build_receipt(permit)
    assert receipt["currentFence"] == {
        "preCurrent": None,
        "postCurrent": None,
        "stable": False,
    }
    assert validate(receipt, permit)["status"] == "not_run"
    receipt["currentFence"]["stable"] = True
    with pytest.raises(verifier.ReceiptError, match="unobserved CURRENT"):
        validate(receipt, permit)


def test_ooda_must_bind_step_evidence_and_reject_query_url() -> None:
    permit = build_permit()
    receipt = build_receipt(permit, status="blocked")
    first = receipt["journey"]["steps"][0]
    first.update(status="blocked", evidenceSha256=digest("blocked-first-action"))
    receipt["browserOoda"]["completedActions"] = [verifier.ACTION_IDS[0]]
    receipt["browserOoda"]["evidenceSha256s"] = [digest("wrong-ooda-evidence")]
    with pytest.raises(verifier.ReceiptError, match="exactly bind"):
        validate(receipt, permit)
    receipt = build_receipt(permit, status="blocked")
    receipt["browserOoda"]["finalUrl"] = "https://chummer.run/account?invite=secret"
    with pytest.raises(verifier.ReceiptError, match="same-origin"):
        validate(receipt, permit)


def test_not_run_cannot_claim_browser_completion() -> None:
    permit = build_permit()
    receipt = build_receipt(permit, status="not_run")
    receipt["browserOoda"]["completedActions"] = [verifier.ACTION_IDS[0]]
    with pytest.raises(verifier.ReceiptError):
        validate(receipt, permit)


def test_generated_at_must_follow_start_and_cleanup() -> None:
    permit = build_permit()
    receipt = build_receipt(
        permit,
        status="blocked",
        generated_at=TEST_NOW - dt.timedelta(minutes=2),
    )
    receipt["permit"]["forwardStartedAtUtc"] = utc(
        TEST_NOW - dt.timedelta(minutes=1)
    )
    with pytest.raises(verifier.ReceiptError, match="predates"):
        validate(receipt, permit)


def write_input(path: Path, payload: object) -> str:
    raw = verifier.canonical_bytes(payload)
    path.write_bytes(raw)
    path.chmod(0o600)
    return hashlib.sha256(raw).hexdigest()


def test_safe_file_verification_materializes_no_clobber_evidence(tmp_path: Path) -> None:
    tmp_path.chmod(0o700)
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    permit = build_permit(now=now)
    receipt = build_receipt(permit, now=now)
    permit_path = tmp_path / "permit.json"
    receipt_path = tmp_path / "receipt.json"
    permit_sha = write_input(permit_path, permit)
    receipt_sha = write_input(receipt_path, receipt)
    output = tmp_path / "evidence.json"
    validation, evidence = verifier.verify_files(
        workspace=tmp_path,
        receipt_path=receipt_path,
        receipt_sha256=receipt_sha,
        permit_path=permit_path,
        permit_sha256=permit_sha,
        output=output,
        observed_at=now,
    )
    assert validation["status"] == "not_run"
    assert evidence["status"] == "attention_required"
    assert output.stat().st_mode & 0o777 == 0o600
    assert json.loads(output.read_text()) == evidence
    with pytest.raises(verifier.ReceiptError, match="exists"):
        verifier.verify_files(
            workspace=tmp_path,
            receipt_path=receipt_path,
            receipt_sha256=receipt_sha,
            permit_path=permit_path,
            permit_sha256=permit_sha,
            output=output,
            observed_at=now,
        )


def test_safe_reader_rejects_symlink_hardlink_and_fifo(tmp_path: Path) -> None:
    tmp_path.chmod(0o700)
    permit = build_permit()
    original = tmp_path / "permit.json"
    write_input(original, permit)
    symlink = tmp_path / "permit-link.json"
    symlink.symlink_to(original)
    with pytest.raises(verifier.ReceiptError):
        verifier._stable_file(symlink, tmp_path.resolve(), "permit")
    hardlink = tmp_path / "permit-hard.json"
    os.link(original, hardlink)
    with pytest.raises(verifier.ReceiptError, match="single-link"):
        verifier._stable_file(original, tmp_path.resolve(), "permit")
    fifo = tmp_path / "permit.fifo"
    os.mkfifo(fifo, 0o600)
    with pytest.raises(verifier.ReceiptError, match="regular file"):
        verifier._stable_file(fifo, tmp_path.resolve(), "permit")


def test_strict_json_rejects_case_shadow_nonfinite_and_noncanonical() -> None:
    with pytest.raises(verifier.ReceiptError, match="case-shadowed"):
        verifier._strict_json(b'{"x":1,"X":2}\n', "test")
    with pytest.raises(verifier.ReceiptError, match="non-finite"):
        verifier._strict_json(b'{"x":NaN}\n', "test")
    with pytest.raises(verifier.ReceiptError, match="canonical"):
        verifier._strict_json(b'{"x": 1}\n', "test")


def build_finalization(now: dt.datetime, binding: dict[str, str]) -> dict[str, object]:
    return {
        "contractName": "chummer.staged-release-owner-finalization/v1",
        "contractVersion": 1,
        "status": "preview_ready",
        "releaseVersion": binding["releaseVersion"],
        "generationId": binding["generationId"],
        "stageReceiptId": "stage-receipt-governed-campaign",
        "manifestSha256": binding["manifestSha256"],
        "releaseScopeDecisionSha256": digest("release-scope-decision"),
        "releaseScopeVerificationSha256": digest("release-scope-verification"),
        "exactIncomingDesktopScope": "avalonia:macos:osx-arm64",
        "snapshotSha256": binding["snapshotSha256"],
        "decisionSha256": binding["decisionSha256"],
        "authorityRevisionId": "auth-" + "e" * 64,
        "targetPointerSha256": binding["targetPointerSha256"],
        "completedAtUtc": utc(now - dt.timedelta(minutes=15)),
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("authorityRevisionId", "operator-approved"),
        ("exactIncomingDesktopScope", "macos arm64"),
    ],
)
def test_not_run_finalization_requires_producer_exact_authority_fields(
    field: str, value: str
) -> None:
    payload = build_finalization(TEST_NOW, TARGET)
    payload[field] = value
    with pytest.raises(verifier.ReceiptError):
        verifier._release_binding_from_finalization(payload, observed_at=TEST_NOW)


def build_release_truth(binding: dict[str, str]) -> dict[str, object]:
    return {
        "contractName": "chummer.release-truth-projection/v1",
        "releaseVersion": binding["releaseVersion"],
        "channel": "preview",
        "releaseStatus": "published",
        "rolloutState": "complete",
        "supportabilityState": "supported",
        "availablePlatforms": ["windows"],
        "primaryHeadByPlatform": {"windows": "artifact-test"},
        "artifactCount": 1,
        "downloadAccessPosture": "open_public",
        "knownIssueSummary": "No blocking known issues.",
        "manifestSha256": binding["manifestSha256"],
        "registryCommit": "4" * 40,
        "releaseDecisionStatus": "preview_ready",
        "releaseDecisionSha256": binding["decisionSha256"],
    }


def build_convergence(
    now: dt.datetime,
    binding: dict[str, str],
    release_truth: dict[str, object],
) -> dict[str, object]:
    checked_routes = set(
        verifier.CONVERGENCE_HELPERS.generation_routes(binding["generationId"])
    )
    checked_routes.add(
        f"/downloads/g/{binding['generationId']}/install/artifact-test"
    )
    routes = sorted(checked_routes)
    return {
        "contractName": "chummer.live-release-convergence/v1",
        "contractVersion": 1,
        "generatedAtUtc": utc(now - dt.timedelta(minutes=5)),
        "verificationMode": "committed_public",
        "status": "pass",
        "mismatchCount": 0,
        "failureCount": 0,
        "mismatches": [],
        "failures": [],
        "releaseVersion": binding["releaseVersion"],
        "manifestSha256": binding["manifestSha256"],
        "releaseDecisionStatus": "preview_ready",
        "authoritySnapshotSha256": binding["snapshotSha256"],
        "releaseDecisionSha256": binding["decisionSha256"],
        "authorityRoute": (
            f"/api/v1/public/release-truth/g/{binding['generationId']}"
        ),
        "checkedRouteCount": len(routes),
        "checkedRoutes": routes,
        "comparedFields": list(verifier.CONVERGENCE_HELPERS.REQUIRED_FIELDS),
        "releaseTruth": copy.deepcopy(release_truth),
    }


def build_manifest(
    binding: dict[str, str], release_truth: dict[str, object]
) -> dict[str, object]:
    return {
        "version": binding["releaseVersion"],
        "channel": "preview",
        "status": "published",
        "rolloutState": "complete",
        "supportabilityState": "supported",
        "downloadAccessPosture": "open_public",
        "knownIssueSummary": "No blocking known issues.",
        "manifestSha256": binding["manifestSha256"],
        "registryCommit": "4" * 40,
        "releaseDecisionStatus": "preview_ready",
        "releaseDecisionSha256": binding["decisionSha256"],
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
        "releaseTruth": copy.deepcopy(release_truth),
    }


def build_materialization_bundle(
    tmp_path: Path,
    now: dt.datetime,
    *,
    permit: dict[str, object] | None = None,
) -> dict[str, object]:
    tmp_path.chmod(0o700)
    permit = permit or build_permit(now=now)
    permit_path = tmp_path / "permit.json"
    permit_sha = write_input(permit_path, permit)
    finalization_path = tmp_path / "finalization.json"
    convergence_path = tmp_path / "convergence.json"
    manifest_path = tmp_path / "manifest.json"
    finalization_sha = write_input(finalization_path, build_finalization(now, TARGET))
    truth = build_release_truth(TARGET)
    convergence_sha = write_input(
        convergence_path, build_convergence(now, TARGET, truth)
    )
    manifest_sha = write_input(manifest_path, build_manifest(TARGET, truth))
    return {
        "workspace": tmp_path,
        "now": now,
        "permit": permit,
        "permit_path": permit_path,
        "permit_sha": permit_sha,
        "finalization_path": finalization_path,
        "finalization_sha": finalization_sha,
        "convergence_path": convergence_path,
        "convergence_sha": convergence_sha,
        "manifest_path": manifest_path,
        "manifest_sha": manifest_sha,
        "output": tmp_path / "materialized-not-run.json",
    }


def materialization_refs() -> tuple[dict[str, str], dict[str, str]]:
    contexts = {
        role: hmac_ref("not-run-context:" + role) for role in verifier.ROLES
    }
    sessions = {
        role: hmac_ref("not-run-session:" + role) for role in verifier.ROLES
    }
    return contexts, sessions


def materialization_arguments(bundle: dict[str, object]) -> list[str]:
    arguments = [
        "--workspace",
        str(bundle["workspace"]),
        "--materialize-not-run",
        "--permit",
        str(bundle["permit_path"]),
        "--expected-permit-sha256",
        str(bundle["permit_sha"]),
        "--finalization-receipt",
        str(bundle["finalization_path"]),
        "--expected-finalization-sha256",
        str(bundle["finalization_sha"]),
        "--generation-convergence",
        str(bundle["convergence_path"]),
        "--expected-generation-convergence-sha256",
        str(bundle["convergence_sha"]),
        "--generation-manifest",
        str(bundle["manifest_path"]),
        "--expected-generation-manifest-sha256",
        str(bundle["manifest_sha"]),
        "--receipt-id",
        "campaign-e2e-not-run-cli",
        "--cleanup-journal-ref-hmac",
        hmac_ref("not-run-cleanup-journal"),
        "--output",
        str(bundle["output"]),
    ]
    contexts, sessions = materialization_refs()
    for role in verifier.ROLES:
        arguments.extend(
            ["--browser-context-ref", f"{role}={contexts[role]}"]
        )
        arguments.extend(
            ["--browser-session-ref", f"{role}={sessions[role]}"]
        )
    return arguments


def materialize_direct(
    bundle: dict[str, object],
    *,
    cleanup_journal_ref_hmac: str | None = None,
    browser_context_refs: dict[str, str] | None = None,
) -> tuple[dict[str, object], dict[str, object]]:
    contexts, sessions = materialization_refs()
    return verifier.materialize_not_run(
        workspace=bundle["workspace"],
        finalization_path=bundle["finalization_path"],
        finalization_sha256=bundle["finalization_sha"],
        convergence_path=bundle["convergence_path"],
        convergence_sha256=bundle["convergence_sha"],
        manifest_path=bundle["manifest_path"],
        manifest_sha256=bundle["manifest_sha"],
        permit_path=bundle["permit_path"],
        permit_sha256=bundle["permit_sha"],
        receipt_id="campaign-e2e-not-run-direct",
        browser_context_refs=browser_context_refs or contexts,
        browser_session_refs=sessions,
        cleanup_journal_ref_hmac=(
            cleanup_journal_ref_hmac or hmac_ref("not-run-cleanup-journal")
        ),
        output=bundle["output"],
        observed_at=bundle["now"],
    )


def test_cli_exit_codes_and_governed_not_run_materialization(tmp_path: Path) -> None:
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    bundle = build_materialization_bundle(tmp_path, now)
    permit = bundle["permit"]
    for status, expected_exit in {
        "blocked": 2,
        "not_run": 2,
        "pass": 1,
        "cleanup_required": 1,
    }.items():
        receipt = build_receipt(permit, status=status, now=now)
        receipt_path = tmp_path / f"receipt-{status}.json"
        receipt_sha = write_input(receipt_path, receipt)
        assert verifier.main(
            [
                "--workspace",
                str(tmp_path),
                "--receipt",
                str(receipt_path),
                "--expected-receipt-sha256",
                receipt_sha,
                "--permit",
                str(bundle["permit_path"]),
                "--expected-permit-sha256",
                str(bundle["permit_sha"]),
            ]
        ) == expected_exit

    assert verifier.main(materialization_arguments(bundle)) == 2
    output = bundle["output"]
    materialized = json.loads(output.read_text())
    assert materialized["status"] == "not_run"
    assert materialized["operationalReadinessClaimAllowed"] is False
    assert materialized["journey"]["credentialedAttemptPerformed"] is False
    assert all(step["attempts"] == 0 for step in materialized["journey"]["steps"])
    assert materialized["currentFence"] == {
        "preCurrent": None,
        "postCurrent": None,
        "stable": False,
    }
    assert all("method" not in step and "route" not in step for step in materialized["journey"]["steps"])
    assert output.stat().st_mode & 0o777 == 0o600


def test_materializer_requires_a_current_unexpired_permit(tmp_path: Path) -> None:
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    expired = build_permit(now=now - dt.timedelta(hours=2))
    bundle = build_materialization_bundle(tmp_path, now, permit=expired)
    with pytest.raises(verifier.ReceiptError, match="currently valid permit"):
        materialize_direct(bundle)
    assert not bundle["output"].exists()


def test_materializer_rejects_skeletal_release_artifacts(tmp_path: Path) -> None:
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    bundle = build_materialization_bundle(tmp_path, now)
    skeletal = {
        "contractName": "chummer.live-release-convergence/v1",
        "contractVersion": 1,
        "status": "pass",
        "releaseVersion": TARGET["releaseVersion"],
        "manifestSha256": TARGET["manifestSha256"],
        "releaseDecisionSha256": TARGET["decisionSha256"],
        "authoritySnapshotSha256": TARGET["snapshotSha256"],
    }
    bundle["convergence_sha"] = write_input(bundle["convergence_path"], skeletal)
    with pytest.raises(verifier.ReceiptError, match="unexpected field set"):
        materialize_direct(bundle)
    assert not bundle["output"].exists()


def test_materializer_preserves_pretty_producer_artifact_bytes(tmp_path: Path) -> None:
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    bundle = build_materialization_bundle(tmp_path, now)
    for path_key, digest_key in (
        ("convergence_path", "convergence_sha"),
        ("manifest_path", "manifest_sha"),
    ):
        path = bundle[path_key]
        payload = json.loads(path.read_text(encoding="utf-8"))
        raw = (json.dumps(payload, indent=2, ensure_ascii=True) + "\n").encode()
        path.write_bytes(raw)
        path.chmod(0o600)
        bundle[digest_key] = hashlib.sha256(raw).hexdigest()

    receipt, validation = materialize_direct(bundle)
    assert validation["status"] == "not_run"
    assert receipt["inputBindings"]["generationConvergenceSha256"] == bundle[
        "convergence_sha"
    ]
    assert receipt["inputBindings"]["generationManifestFileSha256"] == bundle[
        "manifest_sha"
    ]


def test_cli_rejects_mixed_verification_and_materialization_modes(
    tmp_path: Path,
) -> None:
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    bundle = build_materialization_bundle(tmp_path, now)
    receipt_path = tmp_path / "receipt-not-run.json"
    receipt_sha = write_input(
        receipt_path, build_receipt(bundle["permit"], now=now)
    )
    mixed_materialize = materialization_arguments(bundle) + [
        "--receipt",
        str(receipt_path),
        "--expected-receipt-sha256",
        receipt_sha,
    ]
    assert verifier.main(mixed_materialize) == 1
    assert verifier.main(
        [
            "--workspace",
            str(tmp_path),
            "--receipt",
            str(receipt_path),
            "--expected-receipt-sha256",
            receipt_sha,
            "--permit",
            str(bundle["permit_path"]),
            "--expected-permit-sha256",
            str(bundle["permit_sha"]),
            "--receipt-id",
            "mixed-mode",
        ]
    ) == 1


def test_materializer_rejects_journal_context_collision(tmp_path: Path) -> None:
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    bundle = build_materialization_bundle(tmp_path, now)
    contexts, _ = materialization_refs()
    with pytest.raises(verifier.ReceiptError, match="HMAC domains overlap"):
        materialize_direct(
            bundle,
            cleanup_journal_ref_hmac=contexts[verifier.ROLES[0]],
            browser_context_refs=contexts,
        )
    assert not bundle["output"].exists()
