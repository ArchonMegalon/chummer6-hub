#!/usr/bin/env python3
"""Quick structural Google OAuth handoff probe for live chummer.run."""

from __future__ import annotations

import sys

from materialize_google_oauth_linking_proof import DEFAULT_BASE_URL, probe_public_google_handoff


def main() -> int:
    probe = probe_public_google_handoff(DEFAULT_BASE_URL)
    print(f"base_url={DEFAULT_BASE_URL}")
    print(f"login_url={probe.get('login_url')}")
    print(f"google_start_url={probe.get('google_start_url')}")
    print(f"login_status={probe.get('login_status')}")
    print(f"google_start_status={probe.get('google_start_status')}")
    print(f"google_start_href_present={probe.get('google_start_href_present')}")
    print(f"state_cookie_present={probe.get('state_cookie_present')}")

    redirect = probe.get("redirect") or {}
    for key in (
        "is_google_host",
        "is_supported_google_path",
        "redirect_uri_matches",
        "response_type_code",
        "scope_includes_openid_profile_email",
        "state_present",
        "nonce_present",
        "code_challenge_present",
        "code_challenge_method_s256",
        "prompt_select_account",
    ):
        print(f"{key}={redirect.get(key)}")

    if probe.get("failures"):
        for failure in probe["failures"]:
            print(f"failure={failure}")
        print("google_oauth_structural_handoff:fail")
        return 1

    print("google_oauth_structural_handoff:pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
