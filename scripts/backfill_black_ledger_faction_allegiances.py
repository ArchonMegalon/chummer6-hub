#!/usr/bin/env python3
import argparse
import json
import subprocess
from datetime import datetime, timedelta, timezone


GAME_MASTER_ROLES = {"owner", "organizer", "manager", "admin", "gm"}
DEFAULT_FACTION_ID = "ashline-circle"
PREFERRED_LEADER_EMAIL = "tibor.girschele@gmail.com"
EXCLUDED_DOMAINS = {"example.invalid", "example.test", "example.com"}
EXCLUDED_TEXT_MARKERS = (
    "probe",
    "stress",
    "audit",
    "preview crew",
    "cache",
    "latency",
    "slice",
    "connclose",
    "stalecache",
)
PREFERRED_HUMAN_EMAILS = {
    "tibor.girschele@gmail.com",
    "the.girscheles@gmail.com",
}


def sh(*args: str) -> str:
    return subprocess.check_output(args, text=True).strip()


def read_store(container: str) -> dict:
    raw = sh("docker", "exec", container, "/bin/sh", "-lc", "cat /app/state/community-store.json")
    return json.loads(raw)


def write_store(container: str, payload: dict) -> None:
    blob = json.dumps(payload, indent=2).encode("utf-8")
    proc = subprocess.run(
        ["docker", "exec", "-i", container, "/bin/sh", "-lc", "cat > /app/state/community-store.json"],
        input=blob,
        check=True,
    )
    _ = proc


def normalize_role(value: str | None) -> str:
    return (value or "").strip().replace("_", "-").lower()


def deliverable(email: str) -> bool:
    if "@" not in email:
        return False
    domain = email.rsplit("@", 1)[-1].strip().lower()
    return domain not in EXCLUDED_DOMAINS


def intended_human_recipient(user: dict, groups: dict[str, dict]) -> bool:
    email = (user.get("email") or "").strip()
    if not deliverable(email):
        return False
    if email.lower() in PREFERRED_HUMAN_EMAILS:
        return True
    parts = [email, (user.get("displayName") or "").strip()]
    for group_id in user.get("groupIds") or []:
        group = groups.get(group_id)
        if not group:
            continue
        parts.append((group.get("slug") or group.get("name") or "").strip())
    haystack = " ".join(parts).lower()
    return not any(marker in haystack for marker in EXCLUDED_TEXT_MARKERS)


def choose_leader(users: list[dict], groups: dict[str, dict]) -> str | None:
    preferred = next(
        (
            user["userId"]
            for user in users
            if (user.get("email") or "").strip().lower() == PREFERRED_LEADER_EMAIL and intended_human_recipient(user, groups)
        ),
        None,
    )
    if preferred:
        return preferred

    for user in users:
        email = (user.get("email") or "").strip().lower()
        if not intended_human_recipient(user, groups):
            continue
        if not email.endswith("@chummer.run"):
            return user["userId"]

    for user in users:
        email = (user.get("email") or "").strip().lower()
        if not intended_human_recipient(user, groups):
            continue
        for group_id in user.get("groupIds") or []:
            group = groups.get(group_id)
            if not group:
                continue
            for membership in group.get("memberships") or []:
                if membership.get("userId") == user.get("userId") and normalize_role(membership.get("role")) in GAME_MASTER_ROLES:
                    return user["userId"]
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--portal-container", default="chummer6-hub-chummer-portal-1")
    parser.add_argument("--faction-id", default=DEFAULT_FACTION_ID)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output", default="/docker/chummercomplete/chummer-design/_completion/full_product_every_aspect/BLACK_LEDGER_ADVISORY_ALLEGIANCE_BACKFILL.generated.json")
    args = parser.parse_args()

    store = read_store(args.portal_container)
    users = store.get("users", [])
    groups = {item.get("groupId"): item for item in store.get("groups", [])}
    onboarding = store.get("blackLedgerFactionOnboarding") or {}
    allegiances = dict(onboarding.get("Allegiances") or onboarding.get("allegiances") or {})
    charters = dict(onboarding.get("Charters") or onboarding.get("charters") or {})
    receipts = list(onboarding.get("MembershipReceipts") or onboarding.get("membershipReceipts") or [])
    created = dict(onboarding.get("CreatedFactions") or onboarding.get("createdFactions") or {})
    actions = dict(onboarding.get("ActionReceiptsByFactionId") or onboarding.get("actionReceiptsByFactionId") or {})
    ops = dict(onboarding.get("FactionOperationalStates") or onboarding.get("factionOperationalStates") or {})
    overlays = dict(onboarding.get("PrivateLoreOverlays") or onboarding.get("privateLoreOverlays") or {})
    moderation = list(onboarding.get("ModerationReceipts") or onboarding.get("moderationReceipts") or [])

    now = datetime.now(timezone.utc)
    lock_until = now + timedelta(days=30)
    leader_user_id = choose_leader(users, groups)
    if not leader_user_id:
        raise SystemExit("No suitable leader account found.")

    added = 0
    gm_count = 0
    player_count = 0
    for user in users:
        user_id = user.get("userId")
        email = (user.get("email") or "").strip()
        if not user_id or not intended_human_recipient(user, groups):
            continue

        is_gm = False
        for group_id in user.get("groupIds") or []:
            group = groups.get(group_id)
            if not group:
                continue
            for membership in group.get("memberships") or []:
                if membership.get("userId") == user_id and normalize_role(membership.get("role")) in GAME_MASTER_ROLES:
                    is_gm = True
                    break
            if is_gm:
                break

        if user_id in allegiances:
            continue

        membership_type = "founder_major" if user_id == leader_user_id else ("gm_advisory" if is_gm else "player_advisory")
        receipt_id = f"fmem_backfill_{user_id}"
        allegiances[user_id] = {
            "AccountId": user_id,
            "ActiveFactionId": args.faction_id,
            "MembershipType": membership_type,
            "AppliesToAllCurrentRunners": True,
            "AppliesToAllFutureRunners": True,
            "JoinedAtUtc": now.isoformat().replace("+00:00", "Z"),
            "LockUntilUtc": lock_until.isoformat().replace("+00:00", "Z"),
            "SwitchCount": 1,
            "CurrentRunnerIdsSnapshot": [],
            "ReceiptId": receipt_id,
            "PublicProjectionAllowed": False,
            "NotificationPreferences": {
                "FactionDispatches": True,
                "WorldTickDigest": True,
                "PackagePressureUpdates": True,
            },
        }
        receipts.append(
            {
                "ReceiptId": receipt_id,
                "AccountIdHash": f"backfill:{user_id}",
                "FactionId": args.faction_id,
                "MembershipType": membership_type,
                "AppliesToAllRunners": True,
                "RunnerCount": 0,
                "FutureRunnersInherit": True,
                "CreatedAtUtc": now.isoformat().replace("+00:00", "Z"),
                "PrivacyResult": "backfill_passed",
                "PublicProjectionAllowed": False,
            }
        )
        added += 1
        player_count += 1
        if is_gm:
            gm_count += 1

    if args.faction_id not in charters:
        charters[args.faction_id] = {
            "FactionId": args.faction_id,
            "FounderAccountId": leader_user_id,
            "CharterType": "major",
            "CharterPointsTotal": 12,
            "CharterPointsSpent": 12,
            "Archetype": "command_hegemony",
            "Attributes": {"influence": 4, "security": 3, "research": 3, "operations": 4},
            "Perks": ["executive-mandate", "rapid-procurement"],
            "Flaws": ["public-audit-trail"],
            "StartingDistrictId": "downtown-core",
            "RivalFactionId": None,
            "CreatedAtUtc": now.isoformat().replace("+00:00", "Z"),
            "Status": "seeded_backfill",
            "PublicName": "Ashline Circle",
            "Summary": "Executive command spine used to backfill advisory governance receipts.",
        }

    store["blackLedgerFactionOnboarding"] = {
        "Allegiances": allegiances,
        "CreatedFactions": created,
        "Charters": charters,
        "ActionReceiptsByFactionId": actions,
        "FactionOperationalStates": ops,
        "PrivateLoreOverlays": overlays,
        "MembershipReceipts": receipts,
        "ModerationReceipts": moderation,
    }
    output = {
        "status": "pass",
        "mode": "dry_run" if args.dry_run else "applied",
        "faction_id": args.faction_id,
        "leader_user_id": leader_user_id,
        "added_allegiances": added,
        "player_count": player_count,
        "gm_count": gm_count,
        "charter_present": args.faction_id in charters,
    }
    if not args.dry_run:
        write_store(args.portal_container, store)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            json.dump(output, handle, indent=2)
    print(
        json.dumps(
            output,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
