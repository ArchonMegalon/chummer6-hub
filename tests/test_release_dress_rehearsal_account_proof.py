from __future__ import annotations

import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REHEARSAL = (ROOT / "scripts" / "release_dress_rehearsal.sh").read_text(encoding="utf-8")
ACCOUNT_PROOF = (ROOT / "tests" / "public" / "account-access.spec.ts").read_text(encoding="utf-8")
FRONTDOOR_PROOF = (ROOT / "tests" / "public" / "frontdoor-mobile-launch.spec.ts").read_text(
    encoding="utf-8"
)


def test_release_rehearsal_propagates_target_and_requires_signed_in_account_proof() -> None:
    assert 'BASE_URL="$BASE_URL" \\\n' in REHEARSAL
    assert "CHUMMER_REQUIRE_SIGNED_IN_ACCOUNT_PROOF=1 \\\n" in REHEARSAL
    assert 'ACCOUNT_PROOF_IDENTITY_TOKEN="${CHUMMER_E2E_IDENTITY_TOKEN:-}"' in REHEARSAL
    assert 'ACCOUNT_PROOF_LOCAL_IDENTITY_TOKEN="${CHUMMER_E2E_LOCAL_IDENTITY_TOKEN:-}"' in REHEARSAL
    assert "unset CHUMMER_E2E_IDENTITY_TOKEN CHUMMER_E2E_LOCAL_IDENTITY_TOKEN" in REHEARSAL
    assert 'CHUMMER_E2E_IDENTITY_TOKEN="$ACCOUNT_PROOF_IDENTITY_TOKEN" \\\n' in REHEARSAL
    assert 'CHUMMER_E2E_LOCAL_IDENTITY_TOKEN="$ACCOUNT_PROOF_LOCAL_IDENTITY_TOKEN" \\\n' in REHEARSAL
    assert "tests/public/account-access.spec.ts" in REHEARSAL


def test_release_rehearsal_fails_before_work_when_signed_in_proof_token_is_missing() -> None:
    environment = os.environ.copy()
    environment.pop("CHUMMER_E2E_IDENTITY_TOKEN", None)
    environment.pop("CHUMMER_E2E_LOCAL_IDENTITY_TOKEN", None)

    completed = subprocess.run(
        ["bash", str(ROOT / "scripts" / "release_dress_rehearsal.sh"), "https://no-network.invalid"],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 2
    assert completed.stdout == ""
    assert "signed-in account proof requires" in completed.stderr


def test_release_rehearsal_runs_real_rendered_frontdoor_focus_and_target_size_proof() -> None:
    assert "tests/public/frontdoor-mobile-launch.spec.ts" in REHEARSAL
    assert "desktop Build and Play handoffs keep keyboard focus contained and expose 44px controls" in FRONTDOOR_PROOF
    assert "toBeGreaterThanOrEqual(44)" in FRONTDOOR_PROOF
    assert "await expect(closeButton).toBeFocused()" in FRONTDOOR_PROOF
    assert "await expect(opener).toBeFocused()" in FRONTDOOR_PROOF


def test_signed_in_account_proof_is_fail_closed_and_non_mutating_in_release_mode() -> None:
    assert "CHUMMER_REQUIRE_SIGNED_IN_ACCOUNT_PROOF" in ACCOUNT_PROOF
    assert "Release account proof requires CHUMMER_E2E_IDENTITY_TOKEN" in ACCOUNT_PROOF
    assert "optional developer proof needs" in ACCOUNT_PROOF
    assert "safeIdentityTokenTarget(baseUrl)" in ACCOUNT_PROOF
    assert "https://chummer.run" in ACCOUNT_PROOF
    assert "Local account proof tokens may only target an HTTP(S) loopback origin." in ACCOUNT_PROOF
    assert "Refusing to place a hosted account proof token on unapproved origin" in ACCOUNT_PROOF
    assert ACCOUNT_PROOF.index("safeIdentityTokenTarget(baseUrl)") < ACCOUNT_PROOF.index("browser.newContext")
    assert "httpOnly: true" in ACCOUNT_PROOF
    assert "httpOnly: false" not in ACCOUNT_PROOF
    assert "url: `${parsedBaseUrl.origin}/`" in ACCOUNT_PROOF
    assert "serviceWorkers: 'block'" in ACCOUNT_PROOF
    assert "context.route('**/*'" in ACCOUNT_PROOF
    assert ACCOUNT_PROOF.index("context.route('**/*'") < ACCOUNT_PROOF.index("context.addCookies")
    assert "!safeHttpMethods.has(method)" in ACCOUNT_PROOF
    assert "await route.abort('blockedbyclient')" in ACCOUNT_PROOF
    assert "expect(unsafeMethodAttempts" in ACCOUNT_PROOF
    assert "toEqual([])" in ACCOUNT_PROOF
    assert "document.cookie" in ACCOUNT_PROOF
