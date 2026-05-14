#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import sys

import yaml


ROOT = Path("/docker/chummercomplete")
DESIGN = ROOT / "chummer-design" / "products" / "chummer"
REGISTRY_SEED = ROOT / "chummer-hub-registry" / "black-ledger" / "worlds" / "emerald-sprawl-prelude.yaml"
HUB = ROOT / "chummer.run-services"
OUT = HUB / ".codex-studio" / "published" / "BLACK_LEDGER_FEATURE_COMPLETION_AUDIT.generated.json"


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def main() -> int:
    failures: list[str] = []

    for name in (
        "BLACK_LEDGER_PRESEEDED_WORLD_SPEC.md",
        "BLACK_LEDGER_AI_STEWARDSHIP_SPEC.md",
        "BLACK_LEDGER_WORLD_TICK_SPEC.md",
        "BLACK_LEDGER_MAP_AND_FACTION_INTEL_SPEC.md",
        "BLACK_LEDGER_TICK_EMAIL_FAILURE_AUDIT.md",
        "BLACK_LEDGER_TICK_EMAIL_DEV_CHANGE_GUIDE.md",
        "BLACK_LEDGER_TICK_EMAIL_BLOCKERS.yaml",
        "BLACK_LEDGER_TICK_EMAIL_VERIFICATION_MATRIX.yaml",
    ):
        require((DESIGN / name).exists(), f"missing design canon doc: {name}", failures)

    seed = yaml.safe_load(REGISTRY_SEED.read_text(encoding="utf-8"))
    require(bool(seed.get("global_posts")), "seed missing global_posts", failures)
    require(bool(seed.get("stewardship_transfer_preview")), "seed missing stewardship_transfer_preview", failures)
    require(any(item.get("turn") == 2 for item in (seed.get("deterministic_test_ticks") or [])), "seed missing deterministic turn 2 fixture", failures)

    ledger_controller = (HUB / "Chummer.Run.Api" / "Controllers" / "LedgerController.cs").read_text(encoding="utf-8")
    public_controller = (HUB / "Chummer.Run.Api" / "Controllers" / "PublicLandingController.cs").read_text(encoding="utf-8")
    ledger_view = (HUB / "Chummer.Run.Api" / "Views" / "PublicLanding" / "Ledger.cshtml").read_text(encoding="utf-8")
    ledger_service = (HUB / "Chummer.Run.Api" / "Services" / "Community" / "BlackLedgerPublicStatsService.cs").read_text(encoding="utf-8")
    tick_news_service = (HUB / "Chummer.Run.Api" / "Services" / "Community" / "BlackLedgerTickNewsNotificationService.cs").read_text(encoding="utf-8")

    for marker in (
        '[HttpGet("worlds/{worldId}")]',
        '[HttpPost("worlds/{worldId}/ticks")]',
        '[HttpPost("worlds/{worldId}/tick-news/send")]',
        '[HttpGet("/ledger")]',
    ):
        require(marker in (ledger_controller + public_controller), f"missing controller contract: {marker}", failures)

    require("/ledger?turn=2" in ledger_service, "missing runtime turn-two preview route", failures)
    require("public sealed class BlackLedgerTickNewsNotificationService" in tick_news_service, "missing tick-news notification service", failures)
    require("public sealed class BlackLedgerNewsRecipientResolver" in tick_news_service, "missing tick-news recipient resolver", failures)
    require('CHUMMER_BLACK_LEDGER_NEWS_EMAIL_POLICY' in tick_news_service, "missing tick-news policy config contract", failures)
    for marker in (
        "Stewardship transfer preview",
        "Interim bots run bounded posts until verified humans take over.",
    ):
        require(marker in ledger_view, f"missing live ledger view marker: {marker}", failures)

    payload = {
        "contract_name": "chummer.black_ledger_feature_completion_audit",
        "status": "pass" if not failures else "fail",
        "failure_count": len(failures),
        "failures": failures,
    }
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    print("pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
