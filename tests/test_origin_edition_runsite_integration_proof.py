from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "materialize_origin_edition_runsite_integration_proof.py"
REPO_ROOT = Path(__file__).resolve().parents[1]


def load_module():
    seed_origin_context_env()
    spec = importlib.util.spec_from_file_location("origin_edition_runsite_integration_proof", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def seed_origin_context_env() -> None:
    os.environ.setdefault("CHUMMER_ORIGIN_EDITION_PROJECT_ID", "varga-mira-kestrel")
    os.environ.setdefault("CHUMMER_ORIGIN_EDITION_FAMILY_NAME", "Varga")
    os.environ.setdefault("CHUMMER_ORIGIN_EDITION_GIVEN_NAME", "Mira")
    os.environ.setdefault("CHUMMER_ORIGIN_EDITION_RUNNER_NAME", "Kestrel")
    os.environ.setdefault("CHUMMER_ORIGIN_EDITION_BASE_URL", "https://chummer.run")


def write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def clear_origin_context_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "CHUMMER_ORIGIN_EDITION_PROJECT_ID",
        "CHUMMER_ORIGIN_EDITION_FAMILY_NAME",
        "CHUMMER_ORIGIN_EDITION_GIVEN_NAME",
        "CHUMMER_ORIGIN_EDITION_RUNNER_NAME",
        "CHUMMER_ORIGIN_EDITION_BASE_URL",
        "CHUMMER_ORIGIN_EDITION_NAMESPACE",
    ):
        monkeypatch.delenv(key, raising=False)


def test_runsite_proof_without_explicit_context_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = load_module()
    clear_origin_context_env(monkeypatch)

    with pytest.raises(ValueError, match="explicit Origin Edition context required"):
        module.materialize(REPO_ROOT, tmp_path, tmp_path, tmp_path / "runsite.json")


def seed_ea_inventory(root: Path) -> Path:
    ltds = "\n".join(
        [
            "| Crezlo Tours | owned |",
            "| Pano2VR | owned |",
            "| Unmixr AI | owned |",
            "| YouBooks | owned |",
            "| First Book ai | owned |",
            "",
        ]
    )
    env = "\n".join(
        [
            "EA_CREZLO_LOGIN_EMAIL=operator@example.test",
            "PANO2VR_LICENSE_KEY=redacted-test-key",
            "UNMIXR_API_KEY=redacted-test-key",
            "UNMIXR_VOICE_ID=voice-test",
            "YOUBOOKS_ACCOUNT_EMAILS=one@example.test,two@example.test",
            "",
        ]
    )
    write_text(root / "LTDs.md", ltds)
    write_text(root / ".env", env)
    return root


def seed_evidence(root: Path, namespace: str = "origin.chummer.run/Varga/Mira/Kestrel") -> None:
    branch = root / namespace
    write_json(root / "ORIGIN_DOSSIER_LIVE_IMPORT_REQUEST.generated.json", {"status": "pass"})
    write_json(
        branch / "authenticated-chummer-route-live.receipt.json",
        {"status": "pass", "goldEligible": True},
    )
    write_json(
        branch / "final-no-fallback-no-sentinel-audit.receipt.json",
        {"status": "pass", "goldEligible": True},
    )
    write_json(
        branch / "deployed-chummer-browser-probe.receipt.json",
        {"status": "blocked", "deployedRouteClaimAllowed": False, "blockers": ["missing_deployed_identity_token"]},
    )
    write_json(
        branch / "deployed-operator-handoff.receipt.json",
        {
            "contractName": "chummer.origin_edition.deployed_operator_handoff.v1",
            "status": "ready_for_operator_token",
            "goldEligible": False,
            "goalCompletionClaimAllowed": False,
            "blockers": ["missing_deployed_identity_token"],
        },
    )
    write_json(
        root / "ORIGIN_EDITION_GOLD_CURRENT_GAP_AUDIT.generated.json",
        {
            "contractName": "chummer.origin_dossier_gold_e2e_audit.v1",
            "status": "blocked",
            "goalCompletionClaimAllowed": False,
            "failedCodes": ["browser_deployed_probe_blocked:missing_deployed_identity_token"],
        },
    )


def test_runsite_integration_proof_passes_without_exposing_env_values(tmp_path: Path) -> None:
    module = load_module()
    seed_evidence(tmp_path)
    ea_root = seed_ea_inventory(tmp_path / "ea")
    output = tmp_path / "runsite-proof.json"

    result = module.materialize(REPO_ROOT, ea_root, tmp_path, output)

    assert result["status"] == "pass"
    assert result["integrationEligible"] is True
    assert result["goldEligible"] is False
    assert result["goalCompletionClaimAllowed"] is False
    assert result["privacy"]["envValuesExposed"] is False
    assert result["privacy"]["rawCredentialExposed"] is False
    assert result["runsiteHandoffVerified"] is True
    assert result["newestLtdsInspected"] is True
    assert result["envInspected"] is True
    assert result["rybbitEnvOnly"] is True
    assert result["deploymentPerformed"] is False
    assert result["secretValuesStored"] is False
    assert result["deployedBrowserProbe"]["status"] == "blocked"
    assert result["deployedOperatorHandoff"]["reportedStatus"] == "ready_for_operator_token"
    assert result["currentGoldGapAudit"]["reportedStatus"] == "blocked"
    assert result["inventoryInspection"]["rybbitRunKeysPresent"]["RYBBIT_CHUMMER_RUN_SITE_ID"] is True
    assert result["inventoryInspection"]["sourceFiles"]["eaEnv"]["present"] is True
    assert result["inventoryInspection"]["sourceFiles"]["eaEnv"]["sha256"]
    assert result["inventoryInspection"]["sourceFiles"]["eaEnv"]["valuesStoredInReceipt"] is False
    serialized = output.read_text(encoding="utf-8")
    assert "redacted-test-key" not in serialized
    assert "operator@example.test" not in serialized
    assert output.is_file()


def test_runsite_integration_proof_uses_origin_edition_context_namespace(tmp_path: Path) -> None:
    module = load_module()
    namespace = "origin.chummer.run/Case/Ari/Ghost"
    seed_evidence(tmp_path, namespace=namespace)
    ea_root = seed_ea_inventory(tmp_path / "ea")
    context = module.OriginEditionContext.from_env(
        project_id="custom-runner",
        family_name="Case",
        given_name="Ari",
        runner_name="Ghost",
    )
    output = tmp_path / namespace / "runsite-integration-proof.receipt.json"

    result = module.materialize(REPO_ROOT, ea_root, tmp_path, output, context)

    assert result["status"] == "pass"
    assert result["namespace"] == namespace
    assert result["projectId"] == "custom-runner"
    assert result["deployedBrowserProbe"]["path"] == f"{namespace}/deployed-chummer-browser-probe.receipt.json"
    assert result["deployedOperatorHandoff"]["path"] == f"{namespace}/deployed-operator-handoff.receipt.json"


def test_origin_gold_capabilities_allow_covered_audio_when_optional_provider_missing() -> None:
    module = load_module()

    capabilities = module.origin_gold_capability_signals(
        {
            "unmixr": False,
            "inkfluence": True,
            "firstBook": False,
            "youbooks": False,
            "crezloTours": False,
            "pano2vr": False,
        }
    )

    assert capabilities["provider_inventory_present"] is True
    assert capabilities["manuscript_or_edition_provider_available"] is True
    assert capabilities["premium_audio_provider_available"] is True
    assert capabilities["optional_overflow_accounts_do_not_block"] is True


def test_origin_gold_capabilities_block_when_audio_lane_missing() -> None:
    module = load_module()

    capabilities = module.origin_gold_capability_signals(
        {
            "unmixr": False,
            "inkfluence": False,
            "firstBook": True,
            "youbooks": True,
            "crezloTours": True,
            "pano2vr": True,
        }
    )

    assert capabilities["provider_inventory_present"] is True
    assert capabilities["manuscript_or_edition_provider_available"] is True
    assert capabilities["premium_audio_provider_available"] is False
    assert capabilities["optional_overflow_accounts_do_not_block"] is True


def test_runsite_integration_proof_reports_raw_provider_signals_separately_from_capabilities(tmp_path: Path) -> None:
    module = load_module()
    seed_evidence(tmp_path)
    ea_root = seed_ea_inventory(tmp_path / "ea")
    write_text(
        ea_root / ".env",
        "\n".join(
            [
                "EA_CREZLO_LOGIN_EMAIL=operator@example.test",
                "PANO2VR_LICENSE_KEY=redacted-test-key",
                "YOUBOOKS_ACCOUNT_EMAILS=one@example.test,two@example.test",
                "",
            ]
        ),
    )

    result = module.materialize(REPO_ROOT, ea_root, tmp_path, tmp_path / "runsite-proof.json")

    assert result["inventoryInspection"]["newestProviderInventorySignals"]["unmixr"] is False
    assert "originGoldCapabilitySignals" in result["inventoryInspection"]


def test_provider_inventory_detects_aliased_unmixr_account_pair(tmp_path: Path) -> None:
    module = load_module()
    ea_root = tmp_path / "ea"
    local_env = tmp_path / "local.env"
    write_text(ea_root / "LTDs.md", "| Unmixr AI | owned |\n")
    write_text(
        ea_root / ".env",
        "\n".join(
            [
                "UNMIXR_ACCOUNT_TIBOR_API_KEY=redacted-test-key",
                "UNMIXR_ACCOUNT_TIBOR_VOICE_ID=voice-test",
                "",
            ]
        ),
    )
    write_text(local_env, "")

    signals = module.provider_inventory_signals(
        (ea_root / "LTDs.md").read_text(encoding="utf-8"),
        ea_root / ".env",
        (ea_root / ".env").read_text(encoding="utf-8"),
        local_env,
    )

    assert signals["unmixr"] is True
    assert module.origin_gold_capability_signals(signals)["premium_audio_provider_available"] is True


def test_provider_inventory_rejects_incomplete_aliased_unmixr_account(tmp_path: Path) -> None:
    module = load_module()
    ea_root = tmp_path / "ea"
    local_env = tmp_path / "local.env"
    write_text(ea_root / "LTDs.md", "| Unmixr AI | owned |\n")
    write_text(ea_root / ".env", "UNMIXR_ACCOUNT_TIBOR_API_KEY=redacted-test-key\n")
    write_text(local_env, "")

    signals = module.provider_inventory_signals(
        (ea_root / "LTDs.md").read_text(encoding="utf-8"),
        ea_root / ".env",
        (ea_root / ".env").read_text(encoding="utf-8"),
        local_env,
    )

    assert signals["unmixr"] is False
    assert signals["unmixrApiConfigured"] is True
    assert signals["configuredAudioProvider"] is False
    assert module.origin_gold_capability_signals(signals)["premium_audio_provider_available"] is False


def test_runsite_integration_proof_reports_unmixr_accounts_missing_voice_ids_without_leaking_values(tmp_path: Path) -> None:
    module = load_module()
    seed_evidence(tmp_path)
    ea_root = tmp_path / "ea"
    write_text(ea_root / "LTDs.md", "| Unmixr AI | owned |\n| Inkfluence | owned |\n")
    write_text(
        ea_root / ".env",
        "\n".join(
            [
                "UNMIXR_ACCOUNT_NEW_ONE_API_KEY=secret-api-one",
                "UNMIXR_ACCOUNT_NEW_ONE_VOICE_ID=",
                "UNMIXR_ACCOUNT_READY_API_KEY=secret-api-ready",
                "UNMIXR_ACCOUNT_READY_VOICE_ID=secret-voice-ready",
                "CHUMMER_EA_INKFLUENCE_BASE_URL=https://inkfluence.example.invalid",
                "",
            ]
        ),
    )

    result = module.materialize(REPO_ROOT, ea_root, tmp_path, tmp_path / "runsite-proof.json")

    inventory = result["inventoryInspection"]
    assert inventory["newestProviderInventorySignals"]["unmixr"] is True
    assert inventory["newestProviderInventorySignals"]["unmixrApiConfigured"] is True
    assert "ready" in inventory["unmixrVoiceReadyAccounts"]
    assert "new_one" in inventory["unmixrAccountsMissingVoiceId"]
    serialized = (tmp_path / "runsite-proof.json").read_text(encoding="utf-8")
    assert "secret-api-one" not in serialized
    assert "secret-api-ready" not in serialized
    assert "secret-voice-ready" not in serialized


def test_runsite_integration_proof_uses_configured_provider_tokens_for_capabilities(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CHUMMER_ORIGIN_MANUSCRIPT_PROVIDER_TOKENS", "memoirforge")
    monkeypatch.setenv("CHUMMER_ORIGIN_AUDIO_PROVIDER_TOKENS", "voiceforge")
    module = load_module()
    seed_evidence(tmp_path)
    ea_root = tmp_path / "ea"
    write_text(ea_root / "LTDs.md", "| MemoirForge | owned |\n| VoiceForge | owned |\n")
    write_text(ea_root / ".env", "MEMOIRFORGE_ACCOUNT_EMAILS=one@example.test\nVOICEFORGE_API_KEY=redacted-test-key\n")

    result = module.materialize(REPO_ROOT, ea_root, tmp_path, tmp_path / "runsite-proof.json")

    signals = result["inventoryInspection"]["newestProviderInventorySignals"]
    capabilities = result["inventoryInspection"]["originGoldCapabilitySignals"]
    assert signals["configuredManuscriptProvider"] is True
    assert signals["configuredAudioProvider"] is True
    assert capabilities["manuscript_or_edition_provider_available"] is True
    assert capabilities["premium_audio_provider_available"] is True
