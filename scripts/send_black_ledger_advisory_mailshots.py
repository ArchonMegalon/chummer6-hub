#!/usr/bin/env python3
import argparse
import http.client
import json
import os
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


GAME_MASTER_ROLES = {"owner", "organizer", "manager", "admin", "gm"}
EXCLUDED_DOMAINS = {"example.invalid", "example.test", "example.com", "chummer.local"}
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


@dataclass
class Recipient:
    user_id: str
    email: str
    display_name: str
    faction_id: str
    is_player: bool
    is_gm: bool
    is_leader: bool


def sh(*args: str) -> str:
    return subprocess.check_output(args, text=True).strip()


def load_env(env_path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not env_path.exists():
        return values
    for line in env_path.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def normalize(value: str | None) -> str:
    return (value or "").strip().replace("_", "-").lower()


def mask(email: str) -> str:
    if "@" not in email:
        return "***"
    left, right = email.split("@", 1)
    if len(left) <= 1:
        return f"*@@{right}"
    return f"{left[0]}***@{right}"


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


def read_store_from_container(container: str) -> dict:
    raw = sh("docker", "exec", container, "/bin/sh", "-lc", "cat /app/state/community-store.json")
    return json.loads(raw)


def container_ip(container: str) -> str:
    return sh("docker", "inspect", "-f", "{{range.NetworkSettings.Networks}}{{.IPAddress}}{{end}}", container)


def build_recipients(store: dict) -> list[Recipient]:
    users = {item["userId"]: item for item in store.get("users", [])}
    groups = {item["groupId"]: item for item in store.get("groups", [])}
    onboarding = store.get("blackLedgerFactionOnboarding") or {}
    allegiances = onboarding.get("Allegiances") or onboarding.get("allegiances") or {}
    charters = onboarding.get("Charters") or onboarding.get("charters") or {}
    recipients: list[Recipient] = []
    for user_id, allegiance in allegiances.items():
        user = users.get(user_id)
        if not user or not intended_human_recipient(user, groups):
            continue
        faction_id = normalize(allegiance.get("ActiveFactionId") or allegiance.get("activeFactionId"))
        is_player = True
        membership_type = str(allegiance.get("MembershipType") or allegiance.get("membershipType") or "")
        is_gm = membership_type.startswith("founder_")
        for group_id in user.get("groupIds") or []:
            group = groups.get(group_id)
            if not group:
                continue
            for membership in group.get("memberships") or []:
                if membership.get("userId") == user_id and normalize(membership.get("role")) in GAME_MASTER_ROLES:
                    is_gm = True
        charter = charters.get(faction_id.replace("-", "_")) or charters.get(faction_id)
        founder_account_id = (charter or {}).get("FounderAccountId") or (charter or {}).get("founderAccountId")
        is_leader = bool(charter and founder_account_id == user_id)
        recipients.append(
            Recipient(
                user_id=user_id,
                email=user["email"].strip(),
                display_name=(user.get("displayName") or "Runner").strip(),
                faction_id=faction_id,
                is_player=is_player,
                is_gm=is_gm,
                is_leader=is_leader,
            )
        )
    if not recipients:
        for user in users.values():
            email = (user.get("email") or "").strip()
            if not email or not intended_human_recipient(user, groups):
                continue
            is_gm = False
            for group_id in user.get("groupIds") or []:
                group = groups.get(group_id)
                if not group:
                    continue
                for membership in group.get("memberships") or []:
                    if membership.get("userId") == user.get("userId") and normalize(membership.get("role")) in GAME_MASTER_ROLES:
                        is_gm = True
            recipients.append(
                Recipient(
                    user_id=user["userId"],
                    email=email,
                    display_name=(user.get("displayName") or "Runner").strip(),
                    faction_id="ashline-circle",
                    is_player=True,
                    is_gm=is_gm,
                    is_leader=False,
                )
            )
    by_email: dict[str, Recipient] = {}
    for item in recipients:
        existing = by_email.get(item.email.lower())
        if existing is None:
            by_email[item.email.lower()] = item
            continue
        by_email[item.email.lower()] = Recipient(
            user_id=existing.user_id,
            email=existing.email,
            display_name=existing.display_name,
            faction_id=existing.faction_id or item.faction_id,
            is_player=existing.is_player or item.is_player,
            is_gm=existing.is_gm or item.is_gm,
            is_leader=existing.is_leader or item.is_leader,
        )
    recipients = list(by_email.values())
    return recipients


def build_messages(base_url: str, recipient: Recipient) -> list[tuple[str, str, str]]:
    advisory_href = f"{base_url}/account/ledger/advisory"
    faction_href = f"{base_url}/account/ledger/factions/{recipient.faction_id}"
    leader_href = f"{base_url}/account/ledger/factions/{recipient.faction_id}/leader-briefing"
    messages: list[tuple[str, str, str]] = []
    if recipient.is_player:
        messages.append(
            (
                "player_vote",
                "[Chummer] Black Ledger player advisory voting is open",
                "\n".join(
                    [
                        "Black Ledger advisory voting is open.",
                        "",
                        "You can now tell the Game Masters which runs, research, or hardware feel worth pushing next.",
                        "That signal goes to the GM desk. It does not bind the world. The megacorp is not a democracy.",
                        "",
                        f"Open the advisory lane: {advisory_href}",
                        f"Faction command: {faction_href}",
                    ]
                ),
            )
        )
    if recipient.is_gm:
        messages.append(
            (
                "gm_vote",
                "[Chummer] Black Ledger GM strategy recommendation lane is open",
                "\n".join(
                    [
                        "Black Ledger GM strategy voting is open.",
                        "",
                        "Player demand is ready for review, and the GM desk can now send a strategic recommendation upward.",
                        "The faction leader receives that recommendation and may ratify, reshape, or override it. The megacorp is not a democracy.",
                        "",
                        f"Open the advisory lane: {advisory_href}",
                        f"Leader intake: {leader_href}",
                    ]
                ),
            )
        )
    if recipient.is_leader:
        messages.append(
            (
                "leader_summary",
                "[Chummer] Black Ledger GM strategy signal reached executive intake",
                "\n".join(
                    [
                        "Black Ledger executive intake has fresh GM strategy signal.",
                        "",
                        "This is advisory command pressure from the GM desk, not a binding vote.",
                        "Review it, use it, or overrule it. The megacorp is not a democracy.",
                        "",
                        f"Open the advisory lane: {advisory_href}",
                        f"Leader intake: {leader_href}",
                    ]
                ),
            )
        )
    return messages


def post_dispatch(base_url: str, token: str, principal_id: str, binding_id: str, recipient: Recipient, mail_kind: str, subject: str, content: str) -> dict:
    payload = {
        "tool_name": "connector.dispatch",
        "action_kind": "delivery.send",
        "payload_json": {
            "principal_id": principal_id,
            "binding_id": binding_id,
            "channel": "email",
            "recipient": recipient.email,
            "subject": subject,
            "content": content,
            "metadata": {
                "mail_kind": mail_kind,
                "faction_id": recipient.faction_id,
                "recipient_user_id": recipient.user_id,
            },
            "idempotency_key": f"{mail_kind}|{recipient.faction_id}|{recipient.user_id}",
        },
    }
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/v1/tools/execute",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "x-ea-principal-id": principal_id,
            "Idempotency-Key": f"{mail_kind}|{recipient.faction_id}|{recipient.user_id}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--portal-container", default="chummer6-hub-chummer-portal-1")
    parser.add_argument("--dispatch-container", default="chummer6-hub-support-progress-mock-1")
    parser.add_argument("--env-file", default="/docker/chummercomplete/chummer.run-services/.env")
    parser.add_argument("--base-url", default="https://chummer.run")
    parser.add_argument("--output", default="/docker/chummercomplete/chummer-design/_completion/full_product_every_aspect/BLACK_LEDGER_ADVISORY_MAILSHOTS.generated.json")
    parser.add_argument("--attempts", type=int, default=8)
    parser.add_argument("--retry-delay-base", type=float, default=1.5)
    parser.add_argument("--retry-delay-step", type=float, default=0.75)
    parser.add_argument("--per-send-delay", type=float, default=1.35)
    args = parser.parse_args()

    env = load_env(Path(args.env_file))
    token = env.get("CHUMMER_BLACK_LEDGER_NEWS_EA_API_TOKEN", "").strip()
    principal_id = env.get("CHUMMER_BLACK_LEDGER_NEWS_EA_PRINCIPAL_ID", "").strip()
    binding_id = env.get("CHUMMER_BLACK_LEDGER_NEWS_EA_BINDING_ID", "").strip()
    if not token or not principal_id or not binding_id:
        raise SystemExit("EA dispatch config missing in .env")

    store = read_store_from_container(args.portal_container)
    dispatch_base = f"http://{container_ip(args.dispatch_container)}:8080"
    recipients = build_recipients(store)
    deliveries: list[dict] = []
    for recipient in recipients:
        for mail_kind, subject, content in build_messages(args.base_url.rstrip("/"), recipient):
            response = None
            last_error = None
            for attempt in range(max(1, args.attempts)):
                try:
                    response = post_dispatch(dispatch_base, token, principal_id, binding_id, recipient, mail_kind, subject, content)
                    break
                except Exception as exc:  # noqa: BLE001
                    last_error = exc
                    time.sleep(args.retry_delay_base + attempt * args.retry_delay_step)
            if response is None:
                raise last_error or RuntimeError("dispatch_failed")
            deliveries.append(
                {
                    "mail_kind": mail_kind,
                    "recipient_user_id": recipient.user_id,
                    "recipient_email_masked": mask(recipient.email),
                    "faction_id": recipient.faction_id,
                    "delivery_ref": response.get("target_ref") or ((response.get("output_json") or {}).get("delivery_id")),
                    "status": ((response.get("output_json") or {}).get("status")) or "queued",
                }
            )
            time.sleep(args.per_send_delay)

    output = {
        "status": "pass",
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "recipient_count": len(recipients),
        "delivery_count": len(deliveries),
        "deliveries": deliveries,
    }
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
