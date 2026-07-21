#!/usr/bin/env python3
"""Materialize fail-closed evidence for the governed live campaign journey.

This v1 producer validates the release binding, isolated browser states, and an
expiring mutation permit.  Exact production browser flows are not governed in
source yet, so it can only emit ``attention_required`` evidence.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, Mapping, Sequence
from urllib.parse import urlsplit


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import verify_post_activation_acceptance as acceptance


PRODUCTION_ORIGIN = "https://chummer.run"
EVIDENCE_CONTRACT = "chummer.post-activation-evidence/v1"
EVIDENCE_KIND = "multi_account_live_journey"
PERMIT_CONTRACT = "chummer.live-campaign-mutation-permit/v1"
ROLES = frozenset({"gm_campaign", "alice_runner", "bob_runner", "depleted_runner"})
ALLOWED_ACTIONS = (
    "alice_runner_reaction",
    "bob_runner_reaction",
    "campaign_create_or_join",
    "consent_visibility",
    "depleted_runner_quota_denial",
    "runsite_cross_user_privacy",
)
PERMIT_FIELDS = {
    "contractName",
    "contractVersion",
    "status",
    "secretRedacted",
    "permitId",
    "issuedAtUtc",
    "expiresAtUtc",
    "allowedOrigin",
    "allowedActions",
    "releaseBinding",
}
STATE_FIELDS = {"cookies", "origins"}
SAFE_EVIDENCE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
FORBIDDEN_TEST_MARKERS = (
    "x-test-identity",
    "fakecampaignhub",
    "requestinterception",
    "admin-issued",
    "admin_issued",
)


class JourneyError(RuntimeError):
    pass


def _parse_map(values: Sequence[str], label: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for value in values:
        if value.count("=") != 1:
            raise JourneyError(f"{label}:invalid_mapping")
        role, item = value.split("=", 1)
        if role not in ROLES or not item or role in result:
            raise JourneyError(f"{label}:invalid_role_set")
        result[role] = item
    if set(result) != ROLES:
        raise JourneyError(f"{label}:role_denominator_mismatch")
    return result


def _contains_forbidden_test_marker(value: Any) -> bool:
    if isinstance(value, dict):
        return any(
            any(marker in str(key).casefold() for marker in FORBIDDEN_TEST_MARKERS)
            or _contains_forbidden_test_marker(nested)
            for key, nested in value.items()
        )
    if isinstance(value, list):
        return any(_contains_forbidden_test_marker(item) for item in value)
    if isinstance(value, str):
        folded = value.casefold()
        return any(marker in folded for marker in FORBIDDEN_TEST_MARKERS)
    return False


def _is_production_host(host: str | None) -> bool:
    if host is None:
        return False
    normalized = host.rstrip(".").casefold()
    return normalized == "chummer.run" or normalized.endswith(".chummer.run")


def _validate_storage_state(payload: dict[str, Any], role: str) -> dict[str, Any]:
    if set(payload) != STATE_FIELDS or _contains_forbidden_test_marker(payload):
        raise JourneyError(f"storage_state:{role}:unsafe_schema")
    cookies = payload.get("cookies")
    origins = payload.get("origins")
    if not isinstance(cookies, list) or not isinstance(origins, list) or not (cookies or origins):
        raise JourneyError(f"storage_state:{role}:empty")

    production_bound = False
    observed_origins: set[str] = set()
    for row in origins:
        if not isinstance(row, dict) or set(row) != {"origin", "localStorage"}:
            raise JourneyError(f"storage_state:{role}:origin_schema")
        origin = row.get("origin")
        local_storage = row.get("localStorage")
        if not isinstance(origin, str) or not isinstance(local_storage, list):
            raise JourneyError(f"storage_state:{role}:origin_schema")
        parsed = urlsplit(origin)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.port not in {None, 443}
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise JourneyError(f"storage_state:{role}:unsafe_origin")
        observed_origins.add(f"https://{parsed.netloc.casefold()}")
        production_bound = production_bound or _is_production_host(parsed.hostname)
        for item in local_storage:
            if not isinstance(item, dict) or set(item) != {"name", "value"}:
                raise JourneyError(f"storage_state:{role}:local_storage_schema")
            if not all(isinstance(item.get(field), str) for field in ("name", "value")):
                raise JourneyError(f"storage_state:{role}:local_storage_schema")

    for cookie in cookies:
        if not isinstance(cookie, dict):
            raise JourneyError(f"storage_state:{role}:cookie_schema")
        domain = cookie.get("domain")
        name = cookie.get("name")
        value = cookie.get("value")
        if not all(isinstance(item, str) and item for item in (domain, name, value)):
            raise JourneyError(f"storage_state:{role}:cookie_schema")
        production_bound = production_bound or _is_production_host(domain.lstrip("."))
    if not production_bound:
        raise JourneyError(f"storage_state:{role}:not_production_bound")
    return {"originCount": len(observed_origins), "productionBound": True}


def _validate_permit(
    payload: dict[str, Any],
    target: Mapping[str, str],
    *,
    now: dt.datetime,
) -> str:
    if set(payload) != PERMIT_FIELDS:
        raise JourneyError("mutation_permit:field_set")
    if (
        payload.get("contractName") != PERMIT_CONTRACT
        or type(payload.get("contractVersion")) is not int
        or payload.get("contractVersion") != 1
        or payload.get("status") != "approved"
        or payload.get("secretRedacted") is not True
        or payload.get("allowedOrigin") != PRODUCTION_ORIGIN
        or payload.get("allowedActions") != list(ALLOWED_ACTIONS)
        or payload.get("releaseBinding") != dict(target)
    ):
        raise JourneyError("mutation_permit:invalid")
    permit_id = acceptance._safe_id(payload.get("permitId"), "mutation permit ID")
    issued = acceptance._timestamp(payload.get("issuedAtUtc"), "mutation permit issuedAtUtc")
    expires = acceptance._timestamp(payload.get("expiresAtUtc"), "mutation permit expiresAtUtc")
    if (
        issued > now + dt.timedelta(seconds=acceptance.MAX_FUTURE_SKEW_SECONDS)
        or expires <= now
        or expires <= issued
        or expires - issued > dt.timedelta(hours=1)
    ):
        raise JourneyError("mutation_permit:expired_or_unbounded")
    return permit_id


def build_evidence(
    *,
    workspace: Path,
    finalization_receipt: Path,
    finalization_sha256: str,
    storage_states: Mapping[str, tuple[Path, str]],
    mutation_permit: Path,
    mutation_permit_sha256: str,
    evidence_id: str,
    output: Path,
    observed_at: dt.datetime | None = None,
) -> dict[str, Any]:
    root = acceptance._workspace(workspace)
    if set(storage_states) != ROLES:
        raise JourneyError("storage_state:role_denominator_mismatch")
    if SAFE_EVIDENCE_ID.fullmatch(evidence_id or "") is None or ".." in evidence_id:
        raise JourneyError("evidence_id:invalid")
    now = observed_at or dt.datetime.now(dt.timezone.utc)
    if now.tzinfo is None or now.utcoffset() != dt.timedelta(0):
        raise JourneyError("observed_at:invalid")

    _, finalization = acceptance._pinned_json(
        finalization_receipt,
        finalization_sha256,
        root,
        "owner finalization receipt",
        require_canonical=True,
    )
    target = acceptance._target_from_finalization(finalization)
    completed = acceptance._timestamp(finalization.get("completedAtUtc"), "completedAtUtc")
    if now < completed:
        raise JourneyError("owner_finalization:future")

    state_digests: dict[str, str] = {}
    state_summaries: dict[str, dict[str, Any]] = {}
    for role in sorted(ROLES):
        path, expected_sha256 = storage_states[role]
        raw, payload = acceptance._pinned_json(
            path,
            expected_sha256,
            root,
            f"{role} storage state",
        )
        state_digests[role] = acceptance._sha(raw)
        state_summaries[role] = _validate_storage_state(payload, role)
    if len(set(state_digests.values())) != len(ROLES):
        raise JourneyError("storage_state:shared_or_duplicate")

    permit_raw, permit = acceptance._pinned_json(
        mutation_permit,
        mutation_permit_sha256,
        root,
        "mutation permit",
        require_canonical=True,
    )
    _validate_permit(permit, target, now=now)
    state_claim_sha = acceptance._sha(
        acceptance._canonical_bytes(
            {"digests": state_digests, "summaries": state_summaries}
        )
    )
    deferred_claim_sha = acceptance._sha(
        acceptance._canonical_bytes(
            {
                "contractName": "chummer.live-campaign-journey-adapter/v1",
                "status": "not_implemented",
                "reason": "governed_production_flow_not_available",
            }
        )
    )
    evidence = {
        "contractName": EVIDENCE_CONTRACT,
        "contractVersion": 1,
        "status": "attention_required",
        "secretRedacted": True,
        "evidenceId": evidence_id,
        "evidenceKind": EVIDENCE_KIND,
        "generatedAtUtc": now.astimezone(dt.timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
        "releaseBinding": target,
        "claims": [
            {
                "claimId": "isolated_production_storage_states",
                "status": "pass",
                "evidenceSha256": state_claim_sha,
            },
            {
                "claimId": "mutation_permit_preflight",
                "status": "pass",
                "evidenceSha256": acceptance._sha(permit_raw),
            },
            {
                "claimId": "production_multi_account_journey",
                "status": "attention_required",
                "evidenceSha256": deferred_claim_sha,
            },
        ],
        "operationalReadinessClaimAllowed": False,
    }
    acceptance._write_new(output, root, acceptance._canonical_bytes(evidence))
    return evidence


def _args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate governed live-campaign inputs and emit attention-only evidence; "
            "v1 never performs or accepts the production journey."
        )
    )
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--finalization-receipt", type=Path, required=True)
    parser.add_argument("--expected-finalization-sha256", required=True)
    parser.add_argument("--storage-state", action="append", default=[], metavar="ROLE=PATH")
    parser.add_argument(
        "--storage-state-sha256", action="append", default=[], metavar="ROLE=SHA256"
    )
    parser.add_argument("--mutation-permit", type=Path, required=True)
    parser.add_argument("--expected-mutation-permit-sha256", required=True)
    parser.add_argument("--evidence-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--allow-attention-required",
        action="store_true",
        help="Observation-only mode; never authorizes flagship acceptance.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _args(argv)
    try:
        paths = _parse_map(args.storage_state, "storage_state")
        digests = _parse_map(args.storage_state_sha256, "storage_state_sha256")
        states = {
            role: (Path(paths[role]), acceptance._require_sha(digests[role], f"{role} digest"))
            for role in sorted(ROLES)
        }
        evidence = build_evidence(
            workspace=args.workspace,
            finalization_receipt=args.finalization_receipt,
            finalization_sha256=args.expected_finalization_sha256,
            storage_states=states,
            mutation_permit=args.mutation_permit,
            mutation_permit_sha256=args.expected_mutation_permit_sha256,
            evidence_id=args.evidence_id,
            output=args.output,
        )
    except (JourneyError, acceptance.AcceptanceError):
        print("multi_account_live_journey:fail", file=sys.stderr)
        return 1
    except (OSError, KeyError, TypeError, ValueError):
        print("multi_account_live_journey:fail", file=sys.stderr)
        return 1
    print(f"multi_account_live_journey:{evidence['status']}")
    return 0 if args.allow_attention_required else 2


if __name__ == "__main__":
    raise SystemExit(main())
