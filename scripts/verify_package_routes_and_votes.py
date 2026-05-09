#!/usr/bin/env python3
from __future__ import annotations

from urllib.parse import urlparse

import requests

from absolute_completion_common import (
    LocalHubApp,
    TokenIdentityStub,
    completion_path,
    extract_antiforgery_token,
    now_iso,
    write_json,
    write_text,
)


PACKAGE_ID = "desktop-preview"
ACCESS_TOKEN = "package-proof-token"


def fetch_token(session: requests.Session, base_url: str) -> str:
    response = session.get(f"{base_url}/packages/{PACKAGE_ID}", timeout=30)
    response.raise_for_status()
    return extract_antiforgery_token(response.text)


def record_action(session: requests.Session, base_url: str, action: str) -> dict:
    token = fetch_token(session, base_url)
    response = session.post(
        f"{base_url}/packages/{PACKAGE_ID}/{action}",
        data={"__RequestVerificationToken": token},
        timeout=30,
        allow_redirects=True,
    )
    response.raise_for_status()
    final_path = urlparse(response.url).path
    expected_prefix = f"/packages/{PACKAGE_ID}/{action}/"
    if not final_path.startswith(expected_prefix):
        raise RuntimeError(f"{action} route landed on unexpected path {final_path}")
    return {
        "final_url": response.url,
        "status_code": response.status_code,
        "receipt_id": final_path.rsplit("/", 1)[-1],
    }


def run() -> int:
    with TokenIdentityStub(access_token=ACCESS_TOKEN) as identity:
        with LocalHubApp(identity_base_url=identity.base_url) as app:
            session = requests.Session()
            session.headers["Authorization"] = f"Bearer {ACCESS_TOKEN}"

            package_list = session.get(f"{app.base_url}/packages", timeout=30)
            package_list.raise_for_status()
            package_detail = session.get(f"{app.base_url}/packages/{PACKAGE_ID}", timeout=30)
            package_detail.raise_for_status()
            vote = record_action(session, app.base_url, "vote")
            follow = record_action(session, app.base_url, "follow")

            account_packages = session.get(f"{app.base_url}/account/packages", timeout=30, allow_redirects=True)
            account_packages.raise_for_status()
            account_detail = session.get(f"{app.base_url}/account/packages/{PACKAGE_ID}", timeout=30, allow_redirects=True)
            account_detail.raise_for_status()

            payload = {
                "contract_name": "chummer.package_route_and_votes",
                "status": "pass",
                "generated_at_utc": now_iso(),
                "base_url": app.base_url,
                "identity_stub_base_url": identity.base_url,
                "package_id": PACKAGE_ID,
                "public_routes": {
                    "packages": package_list.status_code,
                    "package_detail": package_detail.status_code,
                },
                "authenticated_receipts": {
                    "vote": vote,
                    "follow": follow,
                },
                "account_routes": {
                    "account_packages": account_packages.status_code,
                    "account_package_detail": account_detail.status_code,
                },
            }
            write_json(completion_path("PACKAGE_ROUTE_AND_API_AUDIT.generated.json"), payload)
            write_text(
                completion_path("PACKAGE_ROUTE_AND_API_AUDIT.md"),
                "\n".join(
                    [
                        "# Package route and API audit",
                        "",
                        f"- Generated: {payload['generated_at_utc']}",
                        f"- Package id: `{PACKAGE_ID}`",
                        f"- Public browser route: `{package_list.status_code}`",
                        f"- Public detail route: `{package_detail.status_code}`",
                        f"- Vote receipt: `{vote['final_url']}`",
                        f"- Follow receipt: `{follow['final_url']}`",
                        f"- Account package rail: `{account_packages.status_code}`",
                        f"- Account package detail: `{account_detail.status_code}`",
                    ]
                ),
            )
            return 0


if __name__ == "__main__":
    raise SystemExit(run())
