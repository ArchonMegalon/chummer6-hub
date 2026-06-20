#!/usr/bin/env python3
from __future__ import annotations

import argparse

import requests

from absolute_completion_common import LocalHubApp, RUN_SERVICES_ROOT, completion_path, now_iso, write_json, write_text


FEEDBACK_VIEW = RUN_SERVICES_ROOT / "Chummer.Run.Api" / "Views" / "PublicLanding" / "Feedback.cshtml"
OPERATIONS_VIEW = RUN_SERVICES_ROOT / "Chummer.Run.Api" / "Views" / "Shared" / "_PublicSignalOperationsPacket.cshtml"
PROJECTION_VIEW = RUN_SERVICES_ROOT / "Chummer.Run.Api" / "Views" / "Shared" / "_PublicSignalProjectionPacket.cshtml"

REQUIRED_HTML_PHRASES = (
    "Votes show demand. Chummer decides what ships.",
    "The loop closes only after people can use it",
    "First-party follow-up is not posted here yet.",
    "Public feedback can still show demand, but account-backed follow-up waits until the shipped path is available on this host.",
)
FORBIDDEN_HTML_PHRASES = (
    "webhook verification",
    "recipient projection",
    "consent basis",
    "governor approval",
    "delivery candidates",
    "outbox candidates",
    "sent receipts",
    "release-backed closeout",
    "proof-bound",
)
REQUIRED_SOURCE_PHRASES = (
    "Votes show demand. Chummer decides what ships.",
    "The loop closes only after people can use it",
    "First-party follow-up is not posted here yet.",
    "account-backed follow-up waits until the shipped path is available on this host",
)
FORBIDDEN_SOURCE_PHRASES = (
    "pending/zero closeout",
    "webhook verification",
    "recipient projection",
    "consent basis",
    "governor approval",
    "release-backed closeout",
    "proof-bound",
    "release proof, delivery candidates, outbox candidates, sent receipts, and journey receipts are pending or zero",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify /feedback public copy stays preview-honest and does not overclaim closeout operations.")
    parser.add_argument("--base-url", default="", help="Optional running Hub base URL. When omitted the script launches a temporary local Hub.")
    parser.add_argument("--route", default="/feedback", help="Public route to verify. Defaults to /feedback.")
    return parser.parse_args()


def scan_required(text: str, phrases: tuple[str, ...], label: str, failures: list[str]) -> None:
    for phrase in phrases:
        if phrase not in text:
            failures.append(f"{label} missing required phrase: {phrase}")


def scan_forbidden(text: str, phrases: tuple[str, ...], label: str, failures: list[str]) -> None:
    for phrase in phrases:
        if phrase in text:
            failures.append(f"{label} contains forbidden phrase: {phrase}")


def run(base_url: str, route: str) -> int:
    failures: list[str] = []
    normalized_route = route if route.startswith("/") else f"/{route}"
    response = requests.get(f"{base_url}{normalized_route}", timeout=30)
    response.raise_for_status()
    body = response.text

    scan_required(body, REQUIRED_HTML_PHRASES, normalized_route, failures)
    scan_forbidden(body, FORBIDDEN_HTML_PHRASES, normalized_route, failures)

    feedback_source = FEEDBACK_VIEW.read_text(encoding="utf-8")
    operations_source = OPERATIONS_VIEW.read_text(encoding="utf-8")
    projection_source = PROJECTION_VIEW.read_text(encoding="utf-8")
    source_text = "\n".join((feedback_source, operations_source, projection_source))

    scan_required(source_text, REQUIRED_SOURCE_PHRASES, "feedback source", failures)
    scan_forbidden(source_text, FORBIDDEN_SOURCE_PHRASES, "feedback source", failures)

    payload = {
        "contract_name": "chummer.public_copy_truth_gate",
        "status": "pass" if not failures else "fail",
        "generated_at_utc": now_iso(),
        "base_url": base_url,
        "route": normalized_route,
        "html_status_code": response.status_code,
        "failure_count": len(failures),
        "failures": failures,
        "source_files": [
            str(FEEDBACK_VIEW),
            str(OPERATIONS_VIEW),
            str(PROJECTION_VIEW),
        ],
    }
    write_json(completion_path("PUBLIC_COPY_TRUTH_GATE.generated.json"), payload)

    lines = [
        "# Public copy truth gate",
        "",
        f"- Generated: {payload['generated_at_utc']}",
        f"- Base URL: {payload['base_url']}",
        f"- Route: `{payload['route']}`",
        f"- Status: `{payload['status']}`",
        f"- HTML status: `{payload['html_status_code']}`",
        f"- Failure count: `{payload['failure_count']}`",
    ]
    if failures:
        lines.extend(["", "## Failures", ""])
        lines.extend(f"- {failure}" for failure in failures)
    else:
        lines.extend(["", "The /feedback public copy stays clear, public-safe, and honest about what has shipped."])
    write_text(completion_path("PUBLIC_COPY_TRUTH_GATE.md"), "\n".join(lines))
    return 0 if not failures else 1


def main() -> int:
    args = parse_args()
    if args.base_url:
        return run(args.base_url.rstrip("/"), args.route)

    with LocalHubApp() as app:
        return run(app.base_url, args.route)


if __name__ == "__main__":
    raise SystemExit(main())
