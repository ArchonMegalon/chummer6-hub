from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_run_services_verification_wires_origin_edition_proof_chain() -> None:
    script = (ROOT / "scripts/ai/run_services_verification.sh").read_text(encoding="utf-8")

    assert "ORIGIN_EDITION_EVIDENCE_ROOT" in script
    assert "ORIGIN_EDITION_ENV_FILE" in script
    assert "ORIGIN_EDITION_REQUIRE_GOLD" in script
    assert "ORIGIN_EDITION_NAMESPACE" in script
    assert 'ORIGIN_EDITION_BRANCH="$ORIGIN_EDITION_EVIDENCE_ROOT/$ORIGIN_EDITION_NAMESPACE"' in script
    assert "CHUMMER_ORIGIN_EDITION_REQUIRE_GOLD" in script
    assert "scripts/materialize_origin_edition_gold_proof_chain.py" in script
    assert "scripts/materialize_origin_edition_gold_final_verdict.py" in script
    assert "scripts/verify_origin_dossier_deployed_browser_probe.py" in script
    assert "scripts/verify_origin_dossier_deployed_operator_handoff.py" in script
    assert "scripts/verify_origin_edition_gold_requirement_coverage.py" in script
    assert "scripts/verify_origin_edition_gold_proof_chain.py" in script
    assert "scripts/verify_origin_edition_gold_final_verdict.py" in script
    assert "--allow-blocked >/dev/null" in script
    assert "FINAL_ORIGIN_EDITION_GOLD_VERDICT.md" in script or "materialize_origin_edition_gold_final_verdict.py" in script
    assert '--probe "$ORIGIN_EDITION_BRANCH/deployed-chummer-browser-probe.receipt.json"' in script
    assert '--handoff "$ORIGIN_EDITION_BRANCH/deployed-operator-handoff.receipt.json"' in script
    assert "--proof-chain \"$ORIGIN_EDITION_EVIDENCE_ROOT/ORIGIN_EDITION_GOLD_PROOF_CHAIN.generated.json\"" in script
    assert "--requirement-coverage \"$ORIGIN_EDITION_EVIDENCE_ROOT/ORIGIN_EDITION_GOLD_REQUIREMENT_COVERAGE.generated.json\"" in script
    assert "ORIGIN_EDITION_VERIFY_ARGS+=(--require-gold)" in script
    origin_hook = script.split("ORIGIN_EDITION_EVIDENCE_ROOT=", 1)[1].split("bash scripts/ai/build_r1_cleanroom.sh", 1)[0]
    assert "|| true" not in origin_hook


def test_env_example_documents_origin_edition_gold_without_committing_session_secrets() -> None:
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")

    assert "CHUMMER_ORIGIN_EDITION_EVIDENCE_ROOT=../.tmp/origin-dossier-fresh-gold" in env_example
    assert "CHUMMER_ORIGIN_EDITION_ENV_FILE=.env" in env_example
    assert "CHUMMER_ORIGIN_EDITION_REQUIRE_GOLD=0" in env_example
    assert "CHUMMER_ORIGIN_EDITION_PROJECT_ID=varga-mira-kestrel" in env_example
    assert "CHUMMER_ORIGIN_EDITION_FAMILY_NAME=Varga" in env_example
    assert "CHUMMER_ORIGIN_EDITION_GIVEN_NAME=Mira" in env_example
    assert "CHUMMER_ORIGIN_EDITION_RUNNER_NAME=Kestrel" in env_example
    assert "CHUMMER_ORIGIN_EDITION_NAMESPACE=origin.chummer.run/Varga/Mira/Kestrel" in env_example
    assert "CHUMMER_ORIGIN_EDITION_BASE_URL=https://chummer.run" in env_example
    assert "CHUMMER_DEPLOYED_E2E_IDENTITY_TOKEN=\n" in env_example
    assert "CHUMMER_DEPLOYED_E2E_OWNER_SESSION_TOKEN=\n" in env_example
    assert "CHUMMER_DEPLOYED_E2E_COOKIE_HEADER=\n" in env_example
    assert "CHUMMER_DEPLOYED_E2E_AUTHORIZATION_HEADER=\n" in env_example
    assert "CHUMMER_DEPLOYED_E2E_AUTH_MODE=cookie" in env_example
    assert "CHUMMER_DEPLOYED_E2E_COOKIE_NAME=chummer_hub_access_token" in env_example
    assert "Keep owner-session values operator-local; never commit populated values." in env_example
    assert "secret-token" not in env_example
    assert "owner-session-token" not in env_example
