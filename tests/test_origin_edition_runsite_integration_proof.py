from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "materialize_origin_edition_runsite_integration_proof.py"
REPO_ROOT = Path(__file__).resolve().parents[1]


def load_module():
    spec = importlib.util.spec_from_file_location("origin_edition_runsite_integration_proof", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


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


def test_runsite_integration_proof_blocks_missing_ea_inventory_signal(tmp_path: Path) -> None:
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

    assert result["status"] == "blocked"
    assert "newest_ltd_and_env_inputs_inspected" in result["blockedChecks"]
    assert result["inventoryInspection"]["newestProviderInventorySignals"]["unmixr"] is False
