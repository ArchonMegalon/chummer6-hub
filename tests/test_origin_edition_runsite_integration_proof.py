from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "materialize_origin_edition_runsite_integration_proof.py"
REPO_ROOT = Path(__file__).resolve().parents[1]
GOVERNED_RENDER_SERVICE_FILE = REPO_ROOT / "Chummer.Run.Api/Services/Community/HorizonGovernedRenderRequestComposerService.cs"


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


def build_governed_render_harness_project(project_path: Path) -> None:
    project_path.write_text(
        "\n".join(
            [
                "<Project Sdk=\"Microsoft.NET.Sdk\">",
                "  <PropertyGroup>",
                "    <OutputType>Exe</OutputType>",
                "    <TargetFramework>net10.0</TargetFramework>",
                "    <ImplicitUsings>enable</ImplicitUsings>",
                "    <Nullable>enable</Nullable>",
                "  </PropertyGroup>",
                "  <ItemGroup>",
                f"    <Compile Include=\"{GOVERNED_RENDER_SERVICE_FILE.as_posix()}\" Link=\"HorizonGovernedRenderRequestComposerService.cs\" />",
                "  </ItemGroup>",
                "</Project>",
                "",
            ]
        ),
        encoding="utf-8",
    )


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
    check_statuses = {check["name"]: check["status"] for check in result["checks"]}
    assert check_statuses["shared_governed_render_contract"] == "pass"
    assert check_statuses["runsite_scene_render_bridge"] == "pass"
    assert check_statuses["propertyquarry_apartment_video_bridge"] == "pass"
    assert check_statuses["propertyquarry_apartment_video_internal_route"] == "pass"
    assert check_statuses["propertyquarry_apartment_video_signed_in_route"] == "pass"
    assert check_statuses["origin_provider_account_registry"] == "pass"
    assert check_statuses["origin_provider_account_registry_tests"] == "pass"
    assert result["inventoryInspection"]["rybbitRunKeysPresent"]["RYBBIT_CHUMMER_RUN_SITE_ID"] is True
    assert result["inventoryInspection"]["sharedRenderLaneSignals"] == {
        "governedRenderContractPresent": True,
        "runsiteBridgePresent": True,
        "propertyquarryBridgePresent": True,
        "propertyquarryInternalRoutePresent": True,
        "propertyquarrySignedInRoutePresent": True,
    }
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


def test_shared_governed_render_harness_accepts_origin_media_request() -> None:
    with tempfile.TemporaryDirectory(prefix="governed-render-origin-") as temp_dir:
        temp_root = Path(temp_dir)
        project_path = temp_root / "GovernedRenderHarness.csproj"
        program_path = temp_root / "Program.cs"
        output_path = temp_root / "result.json"

        build_governed_render_harness_project(project_path)
        program_path.write_text(
            "\n".join(
                [
                    "using System.IO;",
                    "using System.Text.Json;",
                    "using Chummer.Run.Api.Services.Community;",
                    "",
                    "HorizonGovernedRenderRequestComposerService service = new();",
                    "HorizonCapabilityDefinition capability = new(",
                    "    HorizonId: \"origin-dossier\",",
                    "    CapabilityId: \"origin-dossier-media\",",
                    "    ArtifactKind: \"dossier_media\",",
                    "    PublicLabel: \"Dossier media\",",
                    "    CapabilitySlot: \"origin_media\",",
                    "    InternalProviderLane: \"Magicfit\",",
                    "    FreeWeeklyLimit: 0,",
                    "    SupporterWeeklyLimit: 2,",
                    "    RequiresAuthentication: true,",
                    "    PublicVisible: false,",
                    "    EnabledByDefault: false,",
                    "    CostClass: \"high\",",
                    "    OrchestrationLane: HorizonGovernedRenderRequestComposerService.OrchestrationLane);",
                    "",
                    "HorizonGovernedRenderRequestCompositionResult result = service.Compose(",
                    "    capability,",
                    "    \"origin-dossier:project-varga:cover\",",
                    "    new HorizonGovernedRenderRequestCreateRequest(",
                    "        WorkItemId: \"origin-varga-cover\",",
                    "        RequestedBy: \"ea.ops\",",
                    "        Subject: \"Mira Varga dossier cover\",",
                    "        Audience: \"account-owner\",",
                    "        Locale: \"en-US\",",
                    "        PreferredProvider: \"MagicFit\",",
                    "        TruthRefs: new[]",
                    "        {",
                    "            \"/artifacts/origin-dossier/project-varga/canon-summary\",",
                    "            \"origin:project-varga:cover-brief\"",
                    "        },",
                    "        EvidenceRefs: new[]",
                    "        {",
                    "            \"review:approved\",",
                    "            \"provider-pool:magicfit\"",
                    "        },",
                    "        Artifacts: new[]",
                    "        {",
                    "            new HorizonGovernedRenderArtifactSpec(",
                    "                ArtifactId: \"cover-main\",",
                    "                Role: \"cover\",",
                    "                Category: \"origin-dossier/cover\",",
                    "                Payload: \"{\\\"prompt_ref\\\":\\\"origin:project-varga:cover-brief\\\"}\",",
                    "                OutputFormat: \"png\",",
                    "                DeduplicationKey: \"origin-varga-cover-main\",",
                    "                AspectRatio: \"2:3\",",
                    "                MaxBytes: 4194304,",
                    "                RequiresApproval: true,",
                    "                PersistOnApproval: true)",
                    "        }));",
                    "",
                    f"File.WriteAllText(\"{output_path.as_posix()}\", JsonSerializer.Serialize(result));",
                    "",
                    "namespace Chummer.Run.Api.Services.Community",
                    "{",
                    "    public sealed record HorizonCapabilityDefinition(",
                    "        string HorizonId,",
                    "        string CapabilityId,",
                    "        string ArtifactKind,",
                    "        string PublicLabel,",
                    "        string CapabilitySlot,",
                    "        string InternalProviderLane,",
                    "        int FreeWeeklyLimit,",
                    "        int SupporterWeeklyLimit,",
                    "        bool RequiresAuthentication,",
                    "        bool PublicVisible,",
                    "        bool EnabledByDefault,",
                    "        string CostClass,",
                    "        string? OrchestrationLane = null);",
                    "}",
                ]
            ),
            encoding="utf-8",
        )

        result = subprocess.run(
            ["dotnet", "run", "--project", str(project_path)],
            cwd=REPO_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        assert result.returncode == 0, result.stderr or result.stdout
        payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert payload["Accepted"] is True
    assert payload["BlockedReasons"] == []
    assert payload["Contract"]["OrchestrationLane"] == "ea_governed_render"
    assert payload["Contract"]["PreferredProvider"] == "MagicFit"
    assert payload["Contract"]["SourceRef"] == "origin-dossier:project-varga:cover"
    assert payload["Contract"]["TruthRefs"] == [
        "/artifacts/origin-dossier/project-varga/canon-summary",
        "origin-dossier:project-varga:cover",
        "origin:project-varga:cover-brief",
    ]


def test_shared_governed_render_harness_rejects_external_evidence_refs() -> None:
    with tempfile.TemporaryDirectory(prefix="governed-render-external-proof-") as temp_dir:
        temp_root = Path(temp_dir)
        project_path = temp_root / "GovernedRenderHarness.csproj"
        program_path = temp_root / "Program.cs"
        output_path = temp_root / "result.json"

        build_governed_render_harness_project(project_path)
        program_path.write_text(
            "\n".join(
                [
                    "using System.IO;",
                    "using System.Text.Json;",
                    "using Chummer.Run.Api.Services.Community;",
                    "",
                    "HorizonGovernedRenderRequestComposerService service = new();",
                    "HorizonCapabilityDefinition capability = new(",
                    "    HorizonId: \"runsite\",",
                    "    CapabilityId: \"runsite-scene-render\",",
                    "    ArtifactKind: \"scene_render\",",
                    "    PublicLabel: \"Scene Render\",",
                    "    CapabilitySlot: \"ea_scene_render\",",
                    "    InternalProviderLane: \"MagicAI\",",
                    "    FreeWeeklyLimit: 0,",
                    "    SupporterWeeklyLimit: 2,",
                    "    RequiresAuthentication: true,",
                    "    PublicVisible: false,",
                    "    EnabledByDefault: false,",
                    "    CostClass: \"high\",",
                    "    OrchestrationLane: HorizonGovernedRenderRequestComposerService.OrchestrationLane);",
                    "",
                    "HorizonGovernedRenderRequestCompositionResult result = service.Compose(",
                    "    capability,",
                    "    \"runsite:redmond-dockyard-pack:segment-a\",",
                    "    new HorizonGovernedRenderRequestCreateRequest(",
                    "        WorkItemId: \"runsite-redmond-scene-a\",",
                    "        RequestedBy: \"ea.ops\",",
                    "        Subject: \"Redmond dockyard orientation segment A\",",
                    "        Audience: \"players\",",
                    "        Locale: \"en-US\",",
                    "        PreferredProvider: \"MagicAI\",",
                    "        TruthRefs: new[] { \"route:segment-a\" },",
                    "        EvidenceRefs: new[] { \"https://example.com/provider-owned-proof\" },",
                    "        Artifacts: new[]",
                    "        {",
                    "            new HorizonGovernedRenderArtifactSpec(",
                    "                ArtifactId: \"segment-a-preview\",",
                    "                Role: \"route_preview\",",
                    "                Category: \"runsite/orientation/route-preview\",",
                    "                Payload: \"{\\\"prompt_ref\\\":\\\"route:segment-a\\\"}\",",
                    "                OutputFormat: \"png\",",
                    "                DeduplicationKey: \"runsite-redmond-segment-a-preview\",",
                    "                AspectRatio: \"16:9\",",
                    "                MaxBytes: 4194304)",
                    "        }));",
                    "",
                    f"File.WriteAllText(\"{output_path.as_posix()}\", JsonSerializer.Serialize(result));",
                    "",
                    "namespace Chummer.Run.Api.Services.Community",
                    "{",
                    "    public sealed record HorizonCapabilityDefinition(",
                    "        string HorizonId,",
                    "        string CapabilityId,",
                    "        string ArtifactKind,",
                    "        string PublicLabel,",
                    "        string CapabilitySlot,",
                    "        string InternalProviderLane,",
                    "        int FreeWeeklyLimit,",
                    "        int SupporterWeeklyLimit,",
                    "        bool RequiresAuthentication,",
                    "        bool PublicVisible,",
                    "        bool EnabledByDefault,",
                    "        string CostClass,",
                    "        string? OrchestrationLane = null);",
                    "}",
                ]
            ),
            encoding="utf-8",
        )

        result = subprocess.run(
            ["dotnet", "run", "--project", str(project_path)],
            cwd=REPO_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        assert result.returncode == 0, result.stderr or result.stdout
        payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert payload["Accepted"] is False
    assert payload["Contract"] is None
    assert "governed render evidence refs" in payload["BlockedReasons"]


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


def test_provider_inventory_tracks_preferred_origin_visuals_and_shared_render_pool(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CHUMMER_ORIGIN_VISUAL_PREFERRED_PROVIDER_TOKENS", "magicfit")
    monkeypatch.setenv("CHUMMER_ORIGIN_VISUAL_PROVIDER_TOKENS", "magicfit, chummer scene renderer")
    monkeypatch.setenv("CHUMMER_RENDER_POOL_PROVIDER_TOKENS", "magicai, omagic")
    module = load_module()
    ea_root = tmp_path / "ea"
    local_env = tmp_path / "local.env"
    write_text(ea_root / "LTDs.md", "| Magicfit | owned |\n")
    write_text(ea_root / ".env", "")
    write_text(
        local_env,
        "\n".join(
            [
                "CHUMMER_EA_MAGICFIT_EMAIL=operator@example.test",
                "CHUMMER_EA_MAGICFIT_PASSWORD=redacted-test-password",
                "CHUMMER_EA_MAGICAI_BASE_URL=https://app.omagic.ai",
                "MAGICAI_ACCOUNT_01_API_KEY=redacted-test-key",
                "",
            ]
        ),
    )

    signals = module.provider_inventory_signals(
        (ea_root / "LTDs.md").read_text(encoding="utf-8"),
        ea_root / ".env",
        (ea_root / ".env").read_text(encoding="utf-8"),
        local_env,
    )
    capabilities = module.origin_gold_capability_signals(signals)

    assert signals["magicfit"] is True
    assert signals["configuredPreferredVisualProvider"] is True
    assert signals["configuredApprovedVisualProvider"] is True
    assert signals["configuredRenderPoolProvider"] is True
    assert signals["magicaiLoginConfigured"] is False
    assert signals["magicaiApiConfigured"] is True
    assert signals["magicaiDeclaredAccountCount"] == 1
    assert signals["magicaiLoginReadyAccountCount"] == 0
    assert signals["magicaiApiReadyAccountCount"] == 1
    assert signals["magicaiAccountsMissingApiKey"] == []
    assert capabilities["preferred_visual_provider_available"] is True
    assert capabilities["approved_visual_provider_available"] is True
    assert capabilities["shared_render_pool_available"] is True


def test_shared_render_pool_requires_minted_magicai_api_key(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CHUMMER_ORIGIN_VISUAL_PREFERRED_PROVIDER_TOKENS", "magicfit")
    monkeypatch.setenv("CHUMMER_RENDER_POOL_PROVIDER_TOKENS", "magicai, omagic")
    module = load_module()
    ea_root = tmp_path / "ea"
    local_env = tmp_path / "local.env"
    write_text(ea_root / "LTDs.md", "| Magicfit | owned |\n")
    write_text(ea_root / ".env", "")
    write_text(
        local_env,
        "\n".join(
            [
                "CHUMMER_EA_MAGICFIT_EMAIL=operator@example.test",
                "CHUMMER_EA_MAGICFIT_PASSWORD=redacted-test-password",
                "MAGICAI_ACCOUNT_01_EMAIL=render@example.test",
                "MAGICAI_ACCOUNT_01_PASSWORD=redacted-shared-password",
                "",
            ]
        ),
    )

    signals = module.provider_inventory_signals(
        (ea_root / "LTDs.md").read_text(encoding="utf-8"),
        ea_root / ".env",
        (ea_root / ".env").read_text(encoding="utf-8"),
        local_env,
    )
    capabilities = module.origin_gold_capability_signals(signals)

    assert signals["configuredRenderPoolProvider"] is True
    assert signals["magicaiLoginConfigured"] is True
    assert signals["magicaiApiConfigured"] is False
    assert signals["magicaiDeclaredAccountCount"] == 1
    assert signals["magicaiLoginReadyAccountCount"] == 1
    assert signals["magicaiApiReadyAccountCount"] == 0
    assert signals["magicaiAccountsMissingApiKey"] == ["01"]
    assert capabilities["shared_render_pool_available"] is False


def test_runsite_integration_proof_reports_live_magicai_platform_audit(tmp_path: Path) -> None:
    module = load_module()
    ea_root = tmp_path / "ea"
    write_text(ea_root / "LTDs.md", "| Magicfit | owned |\n")
    write_text(ea_root / ".env", "")
    write_text(
        tmp_path / ".env",
        "\n".join(
            [
                "CHUMMER_EA_MAGICFIT_EMAIL=operator@example.test",
                "CHUMMER_EA_MAGICFIT_PASSWORD=redacted-test-password",
                "MAGICAI_ACCOUNT_02_EMAIL=two@example.test",
                "MAGICAI_ACCOUNT_02_PASSWORD=shared-password",
                "MAGICAI_ACCOUNT_03_EMAIL=three@example.test",
                "MAGICAI_ACCOUNT_03_PASSWORD=shared-password",
                "MAGICAI_ACCOUNT_03_API_KEY=api-key-three",
                "MAGICAI_ACCOUNT_09_EMAIL=nine@example.test",
                "MAGICAI_ACCOUNT_09_PASSWORD=shared-password",
                "",
            ]
        ),
    )
    write_json(
        tmp_path / ".codex-studio/published/MAGICAI_PLATFORM_ACCESS.generated.json",
        {
            "checked_at_utc": "2026-06-30T00:45:28Z",
            "slots": [
                {"slot": "02", "keys_status": "forbidden", "logged_in": True},
                {"slot": "03", "keys_status": "ok", "logged_in": True},
                {"slot": "09", "keys_status": "login_failed", "logged_in": False},
            ],
        },
    )

    signals = module.provider_inventory_signals(
        (ea_root / "LTDs.md").read_text(encoding="utf-8"),
        ea_root / ".env",
        (ea_root / ".env").read_text(encoding="utf-8"),
        tmp_path / ".env",
    )
    audit = module._magicai_platform_audit_summary(tmp_path)
    assert signals["magicaiPlatformAuditPresent"] is True
    assert signals["magicaiPlatformAccessibleAccounts"] == ["03"]
    assert signals["magicaiPlatformForbiddenAccounts"] == ["02"]
    assert signals["magicaiPlatformLoginFailedAccounts"] == ["09"]
    assert signals["magicaiPlatformPendingMintableAccounts"] == []
    assert signals["magicaiPlatformPendingForbiddenAccounts"] == ["02"]
    assert signals["magicaiPlatformPendingLoginFailedAccounts"] == ["09"]
    assert audit["present"] is True
    assert audit["accessibleAccounts"] == ["03"]
    assert audit["forbiddenAccounts"] == ["02"]
    assert audit["loginFailedAccounts"] == ["09"]
    serialized = json.dumps({"signals": signals, "audit": audit})
    assert "api-key-three" not in serialized
    assert "two@example.test" not in serialized
    assert "nine@example.test" not in serialized


def test_env_example_documents_all_magicai_pool_slots() -> None:
    env_example = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")

    for slot in range(1, 11):
        alias = f"{slot:02d}"
        assert f"# MAGICAI_ACCOUNT_{alias}_EMAIL=" in env_example
        assert f"# MAGICAI_ACCOUNT_{alias}_PASSWORD=" in env_example
        assert f"# MAGICAI_ACCOUNT_{alias}_API_KEY=" in env_example
