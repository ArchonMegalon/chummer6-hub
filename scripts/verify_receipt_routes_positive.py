#!/usr/bin/env python3
from __future__ import annotations

import argparse
from urllib.parse import urljoin, urlparse

import requests

from absolute_completion_common import (
    LocalHubApp,
    completion_path,
    extract_antiforgery_token,
    extract_first_select_option,
    now_iso,
    write_json,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create real support and Karma Forge receipts, then prove the receipt URLs return 200.")
    parser.add_argument("--base-url", default="", help="Optional running Hub base URL. When omitted the script launches a temporary local Hub.")
    return parser.parse_args()


def create_contact_receipt(session: requests.Session, base_url: str) -> dict:
    get_response = session.get(f"{base_url}/contact", timeout=30)
    get_response.raise_for_status()
    token = extract_antiforgery_token(get_response.text)
    post_response = session.post(
        f"{base_url}/contact",
        data={
            "__RequestVerificationToken": token,
            "kind": "install_help",
            "title": "Proof contact case",
            "summary": "The public support rail should create a first-party receipt.",
            "detail": "This audit submission proves the support receipt route resolves from a created case instead of a seeded placeholder.",
            "replyEmail": "proof-contact@chummer.run",
            "platform": "Linux",
            "applicationVersion": "preview-proof",
            "releaseChannel": "preview",
            "headId": "avalonia",
            "arch": "x64",
        },
        timeout=30,
        allow_redirects=True,
    )
    post_response.raise_for_status()
    final_path = urlparse(post_response.url).path
    if not final_path.startswith("/contact/submitted/"):
        raise RuntimeError(f"contact flow landed on unexpected path {final_path}")
    return {
        "created_url": post_response.url,
        "status_code": post_response.status_code,
        "case_id": final_path.rsplit("/", 1)[-1],
    }


def create_karma_receipt(session: requests.Session, base_url: str) -> dict:
    get_response = session.get(f"{base_url}/participate/karma-forge", timeout=30)
    get_response.raise_for_status()
    token = extract_antiforgery_token(get_response.text)
    post_response = session.post(
        f"{base_url}/participate/karma-forge",
        data={
            "__RequestVerificationToken": token,
            "TrackKey": extract_first_select_option(get_response.text, "TrackKey"),
            "RespondentRole": extract_first_select_option(get_response.text, "RespondentRole"),
            "Edition": "SR6",
            "TableType": extract_first_select_option(get_response.text, "TableType"),
            "RuleCategory": extract_first_select_option(get_response.text, "RuleCategory"),
            "Severity": extract_first_select_option(get_response.text, "Severity"),
            "FeedbackPrompt": "Proof packet for the governed amendment rail.",
            "UserWordsSummary": "Our table needs a first-party proof that the public Karma Forge receipt page is real.",
            "CurrentWorkaround": "We keep the request in a private note and lose the chain of custody.",
            "InterpretedNeedSummary": "Keep the amendment intake on a Chummer-owned route with a visible receipt.",
            "ImpactNotes": "This protects auditability, rollback posture, and public truth boundaries.",
            "ShareabilityNotes": "Reusable public proof route for the governed amendment lane.",
            "ReplyEmail": "proof-karma-forge@chummer.run",
            "FollowUpAllowed": "true",
            "QuoteAllowed": "true",
            "ConsentAccepted": "true",
        },
        timeout=30,
        allow_redirects=True,
    )
    post_response.raise_for_status()
    final_path = urlparse(post_response.url).path
    if not final_path.startswith("/participate/karma-forge/submitted/"):
        raise RuntimeError(f"karma forge flow landed on unexpected path {final_path}")
    return {
        "created_url": post_response.url,
        "status_code": post_response.status_code,
        "submission_id": final_path.rsplit("/", 1)[-1],
    }


def run(base_url: str) -> dict:
    session = requests.Session()
    contact = create_contact_receipt(session, base_url)
    karma = create_karma_receipt(session, base_url)
    payload = {
        "contract_name": "chummer.receipt_route_positive_proof",
        "status": "pass",
        "generated_at_utc": now_iso(),
        "base_url": base_url,
        "contact_receipt": contact,
        "karma_forge_receipt": karma,
    }
    write_json(completion_path("RECEIPT_ROUTE_POSITIVE_PROOF.generated.json"), payload)
    return payload


def main() -> int:
    args = parse_args()
    if args.base_url:
        run(args.base_url)
        return 0

    with LocalHubApp() as app:
        run(app.base_url)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
