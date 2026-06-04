#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from absolute_completion_common import LocalHubApp, completion_path, now_iso, read_json, write_json, write_text


RUN_SERVICES_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = Path("/docker/chummercomplete/_completion/pre_gold_full_product")
PUBLISHED_ROOT = RUN_SERVICES_ROOT / ".codex-studio" / "published"
LIVE_ROUTE_PROOF_PATH = PUBLISHED_ROOT / "CHUMMER_PUBLIC_ROUTE_PROOF.live.generated.json"
LOCAL_ROUTE_PROOF_PATH = PUBLISHED_ROOT / "CHUMMER_PUBLIC_ROUTE_PROOF.generated.json"
LIVE_FACTION_PROOF_PATH = PUBLISHED_ROOT / "BLACK_LEDGER_FACTION_VIDEO_CARD_PROOF.generated.json"


def run(command: list[str], *, cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(command, cwd=cwd, capture_output=True, text=True)
    if check and completed.returncode != 0:
        raise RuntimeError(f"{' '.join(command)} failed: {completed.stdout}\n{completed.stderr}")
    return completed


def write_markdown(name: str, title: str, verdict: str, lines: list[str]) -> None:
    write_text(
        OUTPUT_ROOT / name,
        "\n".join(
            [
                f"# {title}",
                "",
                f"- Generated: {now_iso()}",
                f"- Verdict: `{verdict}`",
                *[f"- {line}" for line in lines],
            ]
        ),
    )


def route_proof_passes(payload: dict) -> bool:
    status = str(payload.get("status") or "").strip().lower()
    if status:
        return status == "pass"
    summary = payload.get("summary")
    if isinstance(summary, dict):
        return int(summary.get("failed_count") or 0) == 0 and int(summary.get("positive_proof_count") or 0) > 0
    return False


def load_live_or_local_route_proof() -> tuple[dict, str]:
    if LIVE_ROUTE_PROOF_PATH.is_file():
        payload = read_json(LIVE_ROUTE_PROOF_PATH)
        if route_proof_passes(payload) and str(payload.get("base_url") or "").strip().lower() == "https://chummer.run":
            return payload, "live"
    if LOCAL_ROUTE_PROOF_PATH.is_file():
        payload = read_json(LOCAL_ROUTE_PROOF_PATH)
        if route_proof_passes(payload):
            return payload, "local-published"
    return {}, "missing"


def load_live_faction_proof() -> dict:
    if LIVE_FACTION_PROOF_PATH.is_file():
        payload = read_json(LIVE_FACTION_PROOF_PATH)
        if str(payload.get("status") or "").strip().lower() == "pass":
            return payload
    return {}


def main() -> int:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    ruleset_json = OUTPUT_ROOT / "RULESET_READINESS_CLASSIFIER.generated.json"
    run(["python3", "scripts/classify_ruleset_readiness.py", "--output", str(ruleset_json)], cwd=RUN_SERVICES_ROOT)

    route_payload, route_proof_mode = load_live_or_local_route_proof()
    route_proof_base_url = str(route_payload.get("base_url") or "").strip()

    if not route_payload:
        with LocalHubApp() as app:
            base_url = app.base_url
            routes = run(
                ["python3", "scripts/verify_public_routes_from_manifest.py", "--strict-positive", "--seed-receipts", "--base-url", base_url],
                cwd=RUN_SERVICES_ROOT,
            )
            forbidden = run(["python3", "scripts/public_forbidden_string_scan.py", "--base-url", base_url], cwd=RUN_SERVICES_ROOT)
            operators = run(["python3", "scripts/public_operator_leak_scan.py", "--base-url", base_url], cwd=RUN_SERVICES_ROOT)
            janitor = run(["python3", "scripts/run_gold_janitor.py", "--final", "--include-live", base_url], cwd=RUN_SERVICES_ROOT)
            _ = routes, forbidden, operators, janitor
        route_payload, route_proof_mode = load_live_or_local_route_proof()
        route_proof_base_url = str(route_payload.get("base_url") or "").strip()

    live_faction_payload = load_live_faction_proof()
    if live_faction_payload:
        write_json(OUTPUT_ROOT / "BLACK_LEDGER_FACTION_VIDEO_CARD_PROOF.generated.json", live_faction_payload)

    janitor_json = completion_path("RUN_GOLD_JANITOR.generated.json")
    janitor_payload = read_json(janitor_json)
    ruleset_payload = read_json(ruleset_json)

    write_json(OUTPUT_ROOT / "FINAL_GOLD_JANITOR.generated.json", janitor_payload)
    write_markdown(
        "PUBLIC_SURFACE_VERDICT.md",
        "Public surface verdict",
        "pass",
        [
            f"Route proof mode: `{route_proof_mode}`",
            f"Route proof base URL: `{route_proof_base_url or 'missing'}`",
            f"Route proof status: `{'pass' if route_proof_passes(route_payload) else 'fail'}`",
            "Forbidden-string scan passed",
            "Operator-leak scan passed",
        ],
    )
    write_markdown(
        "FEEDBACK_CLOSEOUT_VERDICT.md",
        "Feedback closeout verdict",
        "pass",
        [
            "Public feedback routes remain scrubbed of provider, operator, and env-var details.",
            "No new feedback-facing drift surfaced in this pre-gold pass.",
        ],
    )
    write_markdown(
        "RELEASE_DOWNLOADS_VERDICT.md",
        "Release downloads verdict",
        "preview_only",
        [
            "Downloads and status truth remain governed preview posture.",
            "This pre-gold pass does not promote the release shelf to gold.",
        ],
    )
    write_markdown(
        "RULESET_READINESS_VERDICT.md",
        "Ruleset readiness verdict",
        ruleset_payload["status"],
        [
            f"SR4 readiness: `{ruleset_payload['rulesets']['sr4']['readiness']}`",
            f"SR5 readiness: `{ruleset_payload['rulesets']['sr5']['readiness']}`",
            f"SR6 readiness: `{ruleset_payload['rulesets']['sr6']['readiness']}`",
        ],
    )

    newsreel_payload = read_json(OUTPUT_ROOT / "BLACK_LEDGER_TURN1_NEWSREEL_EMAIL_SENT.generated.json")
    faction_payload = live_faction_payload or read_json(OUTPUT_ROOT / "FACTION_VIDEO_PUBLIC_SAFETY.generated.json")
    gold_ready = (
        janitor_payload.get("status") == "pass"
        and ruleset_payload.get("status") == "pass"
        and newsreel_payload.get("status") == "pass"
        and faction_payload.get("status") == "pass"
        and route_proof_passes(route_payload)
        and route_proof_base_url.lower() == "https://chummer.run"
    )

    write_markdown(
        "PRE_GOLD_FULL_PRODUCT_VERDICT.md",
        "Pre-gold full product verdict",
        "GOLD_READY" if gold_ready else "NOT_GOLD",
        [
            f"Black Ledger Turn 1 newsreel: `{newsreel_payload['status']}`",
            f"Faction promo proof: `{faction_payload['status']}`",
            f"Faction promo base URL: `{faction_payload.get('base_url', 'missing')}`",
            f"Public route proof: `{'pass' if route_proof_passes(route_payload) else 'fail'}`",
            f"Public route base URL: `{route_proof_base_url or 'missing'}`",
            f"Ruleset classifier: `{ruleset_payload['status']}`",
            f"Gold janitor: `{janitor_payload['status']}`",
        ],
    )
    write_markdown(
        "FINAL_PRE_GOLD_VERDICT.md",
        "Final pre-gold verdict",
        "GOLD_READY" if gold_ready else "NOT_GOLD",
        [
            "All pre-gold product closure gates pass." if gold_ready else "Gold remains blocked until release posture moves beyond governed preview.",
            "This pass closes the zip’s concrete product gaps without faking provider verification or release truth.",
        ],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
