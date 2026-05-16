#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import requests
import yaml

from absolute_completion_common import LocalHubApp, WORKSPACE_ROOT, completion_path, now_iso, write_json, write_text


def resolve_existing_path(*candidates: Path) -> Path:
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


DESIGN_DOC = resolve_existing_path(
    WORKSPACE_ROOT / "chummer-design" / "products" / "chummer" / "BLACK_LEDGER_AI_STEWARDSHIP_SPEC.md",
    Path("/docker/chummercomplete/chummer-design/products/chummer/BLACK_LEDGER_AI_STEWARDSHIP_SPEC.md"),
)
SEED_PATH = resolve_existing_path(
    WORKSPACE_ROOT / "chummer-hub-registry" / "black-ledger" / "worlds" / "emerald-sprawl-prelude.yaml",
    Path("/docker/chummercomplete/chummer-hub-registry/black-ledger/worlds/emerald-sprawl-prelude.yaml"),
)

DOC_REQUIRED_PHRASES = (
    "Human takeover",
    "takeover emits a stewardship transfer receipt",
    "`holder_type` becomes `human`",
    "propose a world tick",
    "AI never outranks human authority and never becomes release truth by itself.",
)

LEDGER_REQUIRED_PHRASES = (
    "AI interim stewards can summarize pressure, but every public lane stays privacy-bounded and receipt-backed.",
    "Turn 1 already ran",
    "Interim bots run bounded posts until verified humans take over.",
    "Stewardship transfer preview",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify Black Ledger AI stewardship remains bounded and human-overridable.")
    parser.add_argument("--base-url", default="", help="Optional running Hub base URL. When omitted the script launches a temporary local Hub.")
    return parser.parse_args()


def run(base_url: str) -> int:
    failures: list[str] = []
    seed = yaml.safe_load(SEED_PATH.read_text(encoding="utf-8"))
    design_doc = DESIGN_DOC.read_text(encoding="utf-8")
    ai_personalities = {item.get("id"): item for item in seed.get("ai_personalities", []) if item.get("id")}

    for phrase in DOC_REQUIRED_PHRASES:
        if phrase not in design_doc:
            failures.append(f"design doc missing required phrase: {phrase}")

    for faction in seed.get("factions", []):
        posts = faction.get("management_posts") or {}
        for post_key in ("faction_leader", "field_gm", "intel_provider"):
            holder = posts.get(post_key)
            if not holder:
                failures.append(f"{faction.get('id', 'unknown faction')} missing {post_key}")
                continue
            if holder not in ai_personalities:
                failures.append(f"{faction.get('id', 'unknown faction')} references unknown AI steward {holder}")
                continue
            personality = ai_personalities[holder]
            if not personality.get("tone") or not personality.get("goals"):
                failures.append(f"{holder} is missing public-safe summary fields")

    response = requests.get(f"{base_url}/ledger", timeout=30)
    response.raise_for_status()
    body = response.text
    for phrase in LEDGER_REQUIRED_PHRASES:
        if phrase not in body:
            failures.append(f"/ledger missing required phrase: {phrase}")

    payload = {
        "contract_name": "chummer.black_ledger_ai_stewardship_gate",
        "status": "pass" if not failures else "fail",
        "generated_at_utc": now_iso(),
        "base_url": base_url,
        "seed_path": str(SEED_PATH),
        "design_doc": str(DESIGN_DOC),
        "failure_count": len(failures),
        "failures": failures,
    }
    write_json(completion_path("BLACK_LEDGER_AI_STEWARDSHIP_GATE.generated.json"), payload)
    lines = [
        "# Black Ledger AI stewardship gate",
        "",
        f"- Generated: {payload['generated_at_utc']}",
        f"- Base URL: {base_url}",
        f"- Status: `{payload['status']}`",
        f"- Failure count: `{payload['failure_count']}`",
    ]
    if failures:
        lines.extend(["", "## Failures", ""])
        lines.extend(f"- {failure}" for failure in failures)
    else:
        lines.extend(["", "AI stewardship stays bounded, documented, and subordinate to human takeover receipts."])
    write_text(completion_path("BLACK_LEDGER_AI_STEWARDSHIP_GATE.md"), "\n".join(lines))
    return 0 if not failures else 1


def main() -> int:
    args = parse_args()
    if args.base_url:
        return run(args.base_url.rstrip("/"))
    with LocalHubApp() as app:
        return run(app.base_url)


if __name__ == "__main__":
    raise SystemExit(main())
