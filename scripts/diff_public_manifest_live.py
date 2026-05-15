#!/usr/bin/env python3
from __future__ import annotations

import argparse

import requests

from absolute_completion_common import LocalHubApp, RUN_SERVICES_ROOT, WORKSPACE_ROOT, completion_path, now_iso, read_yaml, write_text


MIRROR_MANIFEST_PATH = RUN_SERVICES_ROOT / ".codex-design" / "product" / "PUBLIC_LANDING_MANIFEST.yaml"
CENTRAL_MANIFEST_PATH = WORKSPACE_ROOT / "chummer-design" / "products" / "chummer" / "PUBLIC_LANDING_MANIFEST.yaml"
LEGACY_PRIMARY_CTA = "Create account to install"
GUIDED_INSTALL_CTA = "Create account for guided install"
ACCOUNT_AWARE_CONTEXT_SNIPPETS = (
    GUIDED_INSTALL_CTA,
    "Account-aware install value",
    "attach this installed copy to your account",
    "Already have an account? Sign in",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare manifest CTA canon against rendered homepage and downloads HTML.")
    parser.add_argument("--base-url", default="", help="Optional running Hub base URL. When omitted the script launches a temporary local Hub.")
    return parser.parse_args()


def primary_cta(manifest: dict) -> tuple[str, str]:
    hero_ctas = manifest.get("hero_ctas") or []
    primary = next(
        (
            action
            for action in hero_ctas
            if isinstance(action, dict) and str(action.get("emphasis", "")).strip().lower() == "primary"
        ),
        None,
    )
    if not isinstance(primary, dict):
        primary = next((action for action in hero_ctas if isinstance(action, dict)), {})

    label = str(primary.get("label") or "").strip()
    href = str(primary.get("href") or "").strip()
    return label, href


def fetch_html(session: requests.Session, base_url: str, route: str) -> str:
    response = session.get(f"{base_url}{route}", timeout=30)
    response.raise_for_status()
    return response.text


def run(base_url: str) -> int:
    mirror_manifest = read_yaml(MIRROR_MANIFEST_PATH) or {}
    central_manifest = read_yaml(CENTRAL_MANIFEST_PATH) or {}
    mirror_label, mirror_href = primary_cta(mirror_manifest)
    central_label, central_href = primary_cta(central_manifest)

    session = requests.Session()
    landing_html = fetch_html(session, base_url, "/")
    now_html = fetch_html(session, base_url, "/now")
    downloads_html = fetch_html(session, base_url, "/downloads")

    checks = [
        ("central_mirror_primary_match", mirror_label == central_label and mirror_href == central_href, f"mirror={mirror_label} {mirror_href} central={central_label} {central_href}"),
        ("landing_contains_public_primary", mirror_label in landing_html and mirror_href in landing_html, f"expected `{mirror_label}` / `{mirror_href}` on `/`"),
        ("landing_excludes_legacy_primary", LEGACY_PRIMARY_CTA not in landing_html, f"legacy CTA `{LEGACY_PRIMARY_CTA}` should not appear on `/`"),
        ("now_contains_public_primary", mirror_label in now_html, f"expected `{mirror_label}` on `/now`"),
        ("downloads_contains_public_primary", mirror_label in downloads_html, f"expected `{mirror_label}` on `/downloads`"),
        (
            "downloads_contains_account_aware_context",
            any(snippet in downloads_html for snippet in ACCOUNT_AWARE_CONTEXT_SNIPPETS),
            "expected guided-install or calmer account-aware context on `/downloads`",
        ),
        ("downloads_excludes_legacy_primary", LEGACY_PRIMARY_CTA not in downloads_html, f"legacy CTA `{LEGACY_PRIMARY_CTA}` should not appear on `/downloads`"),
    ]
    passed = all(result for _, result, _ in checks)

    lines = [
        "# Live deployment delta audit",
        "",
        f"- Generated: {now_iso()}",
        f"- Base URL: {base_url}",
        f"- Mirror primary CTA: `{mirror_label}` -> `{mirror_href}`",
        f"- Central primary CTA: `{central_label}` -> `{central_href}`",
        f"- Status: `{'pass' if passed else 'fail'}`",
        "",
        "## Checks",
        "",
    ]
    for check_id, result, detail in checks:
        lines.append(f"- `{check_id}`: `{'pass' if result else 'fail'}` - {detail}")

    write_text(completion_path("LIVE_DEPLOYMENT_DELTA_AUDIT.md"), "\n".join(lines))
    return 0 if passed else 1


def main() -> int:
    args = parse_args()
    if args.base_url:
        return run(args.base_url.rstrip("/"))

    with LocalHubApp() as app:
        return run(app.base_url)


if __name__ == "__main__":
    raise SystemExit(main())
