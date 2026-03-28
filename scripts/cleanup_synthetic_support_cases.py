#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Iterable, List


DEFAULT_NOTE = "Synthetic browser verification case auto-closed after successful hub E2E proof."
DEFAULT_ACTOR = "fleet_automation"
TERMINAL_STATUSES = {"deferred", "rejected", "user_notified"}
SYNTHETIC_TITLES = {
    "Guest support intake smoke",
    "Playwright support case",
}
SYNTHETIC_SUMMARIES = {
    "Guest support submission should land on the first-party confirmation page.",
    "Tracked support submission with attachment",
}
SYNTHETIC_DETAIL_PREFIXES = (
    "Browser harness is validating the public support intake route",
    "Browser harness is validating tracked support submission",
)


def parse_args(argv: List[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Close synthetic Hub support cases created by local browser/E2E verification flows.",
    )
    parser.add_argument("--base-url", required=True, help="Hub base URL, for example http://127.0.0.1:8091")
    parser.add_argument("--token", required=True, help="Internal support automation bearer token")
    parser.add_argument("--actor", default=DEFAULT_ACTOR, help="Actor name recorded in the case timeline")
    parser.add_argument("--note", default=DEFAULT_NOTE, help="Closure note recorded in the case timeline")
    return parser.parse_args(argv or sys.argv[1:])


def _request_json(method: str, url: str, token: str, payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
    body = None
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=20) as response:
        raw = response.read().decode("utf-8")
    if not raw.strip():
        return {}
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise SystemExit(f"expected JSON object from {url}, got {type(data).__name__}")
    return data


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _is_synthetic_case(item: Dict[str, Any]) -> bool:
    title = _normalize_text(item.get("title"))
    summary = _normalize_text(item.get("summary"))
    detail = _normalize_text(item.get("detail"))
    reporter_email = _normalize_text(item.get("reporterEmail")).lower()

    if title in SYNTHETIC_TITLES:
        return True
    if summary in SYNTHETIC_SUMMARIES:
        return True
    if any(detail.startswith(prefix) for prefix in SYNTHETIC_DETAIL_PREFIXES):
        return True
    if reporter_email.endswith("@example.com") and "Browser harness is validating" in detail:
        return True
    return False


def _iter_cases(payload: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    items = payload.get("items") or []
    if not isinstance(items, list):
        return []
    return (dict(item) for item in items if isinstance(item, dict))


def main(argv: List[str] | None = None) -> int:
    args = parse_args(argv)
    base_url = args.base_url.rstrip("/")
    triage_url = f"{base_url}/api/v1/support/cases/triage"
    triage_payload = _request_json("GET", triage_url, args.token)
    cases = list(_iter_cases(triage_payload))
    matched = [item for item in cases if _is_synthetic_case(item)]

    closed: List[str] = []
    already_terminal: List[str] = []
    skipped: List[str] = []
    for item in matched:
        case_id = _normalize_text(item.get("caseId"))
        if not case_id:
            continue
        status = _normalize_text(item.get("status")).lower()
        if status in TERMINAL_STATUSES:
            already_terminal.append(case_id)
            continue
        if status == "released_to_reporter_channel":
            skipped.append(case_id)
            continue
        transition_url = f"{base_url}/api/v1/support/cases/{urllib.parse.quote(case_id, safe='')}/transition"
        _request_json(
            "POST",
            transition_url,
            args.token,
            {
                "targetStatus": "rejected",
                "note": args.note,
                "actor": args.actor,
            },
        )
        closed.append(case_id)

    result = {
        "matched_count": len(matched),
        "closed_count": len(closed),
        "already_terminal_count": len(already_terminal),
        "skipped_count": len(skipped),
        "closed_case_ids": closed,
        "already_terminal_case_ids": already_terminal,
        "skipped_case_ids": skipped,
    }
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
