#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_COMPLETION_DIR = Path(
    os.environ.get("CHUMMER_COMPLETION_DIR", "/docker/chummercomplete/_completion/chummer_run_redesign_closure")
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def build_payload(completion_dir: Path) -> dict:
    available_path = completion_dir / "PARTICIPATE_BILLING_AUTH_E2E.generated.json"
    unavailable_path = completion_dir / "PARTICIPATE_BILLING_UNAVAILABLE_E2E.generated.json"

    failures: list[str] = []
    results: dict[str, dict] = {}

    if not available_path.is_file():
        failures.append("missing available-state runtime receipt")
    else:
        available = read_json(available_path)
        results["billing_available"] = available
        if available.get("status") != "pass":
            failures.append("available-state runtime receipt did not pass")
        signed_in_first_party_verified = bool(
            available.get("signed_in_participate_first_party_verified", False)
            or available.get("signed_in_participate_proxy_verified", False)
        )
        if not signed_in_first_party_verified:
            failures.append("available-state runtime receipt did not verify signed-in participate proxy behavior")
        location = str(available.get("signed_in_supporter_checkout_location", ""))
        if "membership_plan=supporter" not in location:
            failures.append("available-state runtime receipt did not prove supporter checkout routing")

    if not unavailable_path.is_file():
        failures.append("missing unavailable-state runtime receipt")
    else:
        unavailable = read_json(unavailable_path)
        results["billing_unavailable"] = unavailable
        if unavailable.get("status") != "pass":
            failures.append("unavailable-state runtime receipt did not pass")
        if unavailable.get("supporter_link_count") != 0:
            failures.append("unavailable-state runtime receipt still exposed supporter links")
        if bool(unavailable.get("supporter_copy_visible")):
            failures.append("unavailable-state runtime receipt still exposed supporter copy")

    status = "pass" if not failures else "fail"
    verdict = "READY" if status == "pass" else "NOT_READY"
    return {
        "generated_at_utc": now_iso(),
        "status": status,
        "verdict": verdict,
        "completion_dir": str(completion_dir),
        "required_receipts": [
            "PARTICIPATE_BILLING_AUTH_E2E.generated.json",
            "PARTICIPATE_BILLING_UNAVAILABLE_E2E.generated.json",
        ],
        "failures": failures,
        "results": results,
    }


def write_outputs(completion_dir: Path, payload: dict) -> None:
    completion_dir.mkdir(parents=True, exist_ok=True)
    json_path = completion_dir / "PARTICIPATE_BILLING_HONESTY.generated.json"
    md_path = completion_dir / "PARTICIPATE_BILLING_HONESTY.md"
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# Participate Billing Honesty",
        "",
        f"- status: `{payload['status']}`",
        f"- verdict: `{payload['verdict']}`",
        "",
    ]
    if payload["failures"]:
        lines.append("## Failures")
        lines.append("")
        lines.extend(f"- {failure}" for failure in payload["failures"])
        lines.append("")
    else:
        lines.append("Both participate billing runtime states passed:")
        lines.append("")
        lines.append("- billing available: supporter path exposed and checkout proved")
        lines.append("- billing unavailable: supporter path suppressed")
        lines.append("")

    md_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--completion-dir", default=str(DEFAULT_COMPLETION_DIR))
    args = parser.parse_args()
    completion_dir = Path(args.completion_dir).resolve()
    payload = build_payload(completion_dir)
    write_outputs(completion_dir, payload)
    return 0 if payload["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
