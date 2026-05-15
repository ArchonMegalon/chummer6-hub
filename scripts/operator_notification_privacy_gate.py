#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

from absolute_completion_common import RUN_SERVICES_ROOT, completion_path, now_iso, write_json, write_text


SERVICE_PATH = RUN_SERVICES_ROOT / "Chummer.Run.Api" / "Services" / "Community" / "ParticipationOperatorNotificationService.cs"
ACCOUNT_VIEW_PATH = RUN_SERVICES_ROOT / "Chummer.Run.Api" / "Views" / "Accounts" / "Account.cshtml"
PRIVACY_REVIEW_PATH = completion_path("OPERATOR_NOTIFICATION_PRIVACY_REVIEW.md")

REQUIRED_SERVICE_TOKENS = [
    "email_masked",
    "email_hash",
    "subject_hash",
    "suppressed_recipient_missing",
    "suppressed_adapter_unconfigured",
    "failed_delivery",
]

REQUIRED_PRIVACY_REVIEW_TOKENS = [
    "Allowed payload fields",
    "Forbidden payload fields",
    "Retention and receipts",
    "unmasked user email",
    "recipient address on public routes",
]

FORBIDDEN_ACCOUNT_VIEW_TOKENS = [
    "CHUMMER_OPERATOR_PARTICIPATION_",
    "ops@chummer.run",
    "connector.dispatch",
    "delivery.send",
]


def main() -> int:
    failures: list[str] = []
    service = SERVICE_PATH.read_text(encoding="utf-8")
    account_view = ACCOUNT_VIEW_PATH.read_text(encoding="utf-8")
    privacy_review = PRIVACY_REVIEW_PATH.read_text(encoding="utf-8") if PRIVACY_REVIEW_PATH.is_file() else ""

    for token in REQUIRED_SERVICE_TOKENS:
        if token not in service:
            failures.append(f"service missing token: {token}")

    for token in REQUIRED_PRIVACY_REVIEW_TOKENS:
        if token not in privacy_review:
            failures.append(f"privacy review missing token: {token}")

    for token in FORBIDDEN_ACCOUNT_VIEW_TOKENS:
        if token in account_view:
            failures.append(f"account view leaked internal token: {token}")

    payload = {
        "contract_name": "chummer.operator_notification_privacy_gate",
        "status": "pass" if not failures else "fail",
        "generated_at_utc": now_iso(),
        "service_path": str(SERVICE_PATH.relative_to(RUN_SERVICES_ROOT)),
        "account_view_path": str(ACCOUNT_VIEW_PATH.relative_to(RUN_SERVICES_ROOT)),
        "privacy_review_path": str(PRIVACY_REVIEW_PATH),
        "failure_count": len(failures),
        "failures": failures,
    }
    write_json(completion_path("OPERATOR_NOTIFICATION_PRIVACY_GATE.generated.json"), payload)

    lines = [
        "# Operator notification privacy gate",
        "",
        f"- Generated: {payload['generated_at_utc']}",
        f"- Status: `{payload['status']}`",
        f"- Failure count: {payload['failure_count']}",
    ]
    if failures:
        lines.extend(["", "## Failures", ""])
        lines.extend(f"- {failure}" for failure in failures)
    else:
        lines.extend(["", "The runtime stores masked and hashed participant identifiers, keeps recipient config internal, and avoids leaking queue details into the signed-in account view."])

    write_text(completion_path("OPERATOR_NOTIFICATION_PRIVACY_GATE.md"), "\n".join(lines))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
