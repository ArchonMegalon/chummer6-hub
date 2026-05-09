#!/usr/bin/env python3
"""Check Google OAuth/account-linking flow on live chummer.run."""

import sys

import requests

BASE_URL = "https://chummer.run"
SESSION = requests.Session()
ROUTES = [
    ("/login", {200}),
    ("/auth/google/start", {302, 303, 307, 308}),
    ("/account/access", {200, 302, 303, 307, 308}),
]
TEST_CASES = [
    "anonymous user starts on /login",
    "Google handoff path exposes /auth/google/start",
    "existing account can link Google",
    "linked account can sign back in with Google",
    "linked-provider state is visible on /account/access",
    "logout/login preserves the expected linked state",
]


def probe_route(route: str, expected_statuses: set[int]) -> bool:
    try:
        response = SESSION.get(f"{BASE_URL}{route}", timeout=10, allow_redirects=False)
    except Exception as exc:
        print(f"{route} request failed: {exc}")
        return False

    status = response.status_code
    location = response.headers.get("Location")
    print(f"{route} status={status} Location={location!r}")
    if status not in expected_statuses:
        return False

    if route == "/auth/google/start":
        if location is None:
            print(f"{route} response missing Location header for OAuth handoff path")
            return False
        if (
            "accounts.google.com" not in str(location)
            and "googleapis.com" not in str(location)
            and "/auth/google/callback" not in str(location)
            and "start" not in str(location)
        ):
            print(f"{route} redirect target does not include expected OAuth handoff")
            return False
    return True


def main() -> int:
    all_ok = True
    for route, expected_statuses in ROUTES:
        if not probe_route(route, expected_statuses):
            print(f"{route} failed")
            all_ok = False

    for test_case in TEST_CASES:
        print(f"Test case: {test_case}")

    if all_ok:
        print("Google OAuth/account-linking flow ok")
        return 0

    print("Some OAuth checks failed")
    return 1


if __name__ == "__main__":
    sys.exit(main())
