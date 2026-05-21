from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def test_advisory_mailshot_script_has_throttled_retry_controls() -> None:
    script = read("scripts/send_black_ledger_advisory_mailshots.py")

    assert "--attempts" in script
    assert "--retry-delay-base" in script
    assert "--retry-delay-step" in script
    assert "--per-send-delay" in script
    assert "The megacorp is not a democracy." in script
    assert "blackLedgerFactionOnboarding" in script
    assert "datetime.now(timezone.utc)" in script


def test_advisory_backfill_script_supports_dry_run_and_proof_output() -> None:
    script = read("scripts/backfill_black_ledger_faction_allegiances.py")

    assert "--dry-run" in script
    assert "--output" in script
    assert "BLACK_LEDGER_ADVISORY_ALLEGIANCE_BACKFILL.generated.json" in script
    assert '"mode": "dry_run" if args.dry_run else "applied"' in script
    assert "founder_major" in script
    assert "gm_advisory" in script
    assert "player_advisory" in script


def test_advisory_rollout_verifier_checks_live_store_and_mailshot_proof() -> None:
    script = read("scripts/verify_black_ledger_advisory_rollout.py")

    assert "BLACK_LEDGER_ADVISORY_MAILSHOTS.generated.json" in script
    assert "BLACK_LEDGER_ADVISORY_ALLEGIANCE_BACKFILL.generated.json" in script
    assert "missing_live_allegiances" in script
    assert "missing_ashline_circle_charter" in script
    assert "missing_gmail_target_in_mailshot" in script
    assert "ashline_circle_leader" in script
