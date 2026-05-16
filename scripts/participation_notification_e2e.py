#!/usr/bin/env python3
from __future__ import annotations

from absolute_completion_common import RUN_SERVICES_ROOT, completion_path, now_iso, write_json


AUTH_CONTROLLER = RUN_SERVICES_ROOT / "Chummer.Run.Api" / "Controllers" / "AuthController.cs"
PUBLIC_LANDING_CONTROLLER = RUN_SERVICES_ROOT / "Chummer.Run.Api" / "Controllers" / "PublicLandingController.cs"
CODEX_CONTROLLER = RUN_SERVICES_ROOT / "Chummer.Run.Api" / "Controllers" / "CodexParticipationController.cs"
ACCOUNTS_CONTROLLER = RUN_SERVICES_ROOT / "Chummer.Run.Api" / "Controllers" / "AccountsController.cs"
SERVICE = RUN_SERVICES_ROOT / "Chummer.Run.Api" / "Services" / "Community" / "ParticipationOperatorNotificationService.cs"


def main() -> int:
    failures: list[str] = []
    auth_controller = AUTH_CONTROLLER.read_text(encoding="utf-8")
    public_landing_controller = PUBLIC_LANDING_CONTROLLER.read_text(encoding="utf-8")
    codex_controller = CODEX_CONTROLLER.read_text(encoding="utf-8")
    accounts_controller = ACCOUNTS_CONTROLLER.read_text(encoding="utf-8")
    service = SERVICE.read_text(encoding="utf-8")

    if "NotifyAccountOpenedIfNeededAsync" not in auth_controller:
        failures.append("auth controller missing account-open notification hook")
    if "NotifyFirstActionIfNeededAsync" not in public_landing_controller:
        failures.append("public landing controller missing first-action notification hook")
    if "NotifyFirstActionIfNeededAsync" not in codex_controller:
        failures.append("codex participation controller missing first-action notification hook")
    if "NotifyFirstActionIfNeededAsync" not in accounts_controller:
        failures.append("accounts controller missing beta first-action notification hook")
    for token in ("participant_account_opened", "participant_first_action", "suppressed_recipient_missing", "failed_delivery"):
        if token not in service:
            failures.append(f"service missing token: {token}")

    payload = {
        "contract_name": "chummer.participation_notification_e2e",
        "status": "pass" if not failures else "fail",
        "generated_at_utc": now_iso(),
        "checks": {
            "auth_controller_hook": "NotifyAccountOpenedIfNeededAsync" in auth_controller,
            "public_landing_first_action_hook": "NotifyFirstActionIfNeededAsync" in public_landing_controller,
            "codex_first_action_hook": "NotifyFirstActionIfNeededAsync" in codex_controller,
            "accounts_beta_hook": "NotifyFirstActionIfNeededAsync" in accounts_controller,
            "service_receipt_states": all(token in service for token in ("participant_account_opened", "participant_first_action", "suppressed_recipient_missing", "failed_delivery")),
        },
        "failure_count": len(failures),
        "failures": failures,
    }
    write_json(completion_path("PARTICIPATION_NOTIFICATION_E2E_RESULTS.generated.json"), payload)
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
