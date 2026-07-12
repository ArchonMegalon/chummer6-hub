from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VERIFIER = ROOT / "scripts" / "ai" / "run_services_verification.sh"
EXTRACTION_VERIFIER = ROOT / "tests" / "RunServicesVerification" / "HubExtractionReadinessVerification.cs"
RUN_CONTRACTS_PROJECT = ROOT / "Chummer.Run.Contracts" / "Chummer.Run.Contracts.csproj"
RUN_AI_PROJECT = ROOT / "Chummer.Run.AI" / "Chummer.Run.AI.csproj"


def test_verifier_accepts_configurable_media_factory_owner_root() -> None:
    verifier = VERIFIER.read_text(encoding="utf-8")

    assert "run_contracts_uses_media_contracts_owner" in verifier
    assert "run_ai_uses_media_contracts_owner" in verifier
    assert "run_ai_uses_media_runtime_owner" in verifier
    assert "$(ChummerMediaFactoryRoot)/src/Chummer.Media.Contracts/Chummer.Media.Contracts.csproj" in verifier
    assert "$(ChummerMediaFactoryRoot)\\src\\Chummer.Media.Contracts\\bin\\$(Configuration)" in verifier
    assert "$(ChummerMediaFactoryRoot)\\src\\Chummer.Media.Factory.Runtime\\bin\\$(Configuration)" in verifier


def test_current_projects_bind_contract_and_runtime_to_media_factory_owner() -> None:
    contracts_project = RUN_CONTRACTS_PROJECT.read_text(encoding="utf-8")
    ai_project = RUN_AI_PROJECT.read_text(encoding="utf-8")

    assert "$(ChummerMediaFactoryRoot)/src/Chummer.Media.Contracts/Chummer.Media.Contracts.csproj" in contracts_project
    assert '<ProjectReference Include="$(ChummerMediaContractsProject)"' in contracts_project
    assert "$(ChummerMediaFactoryRoot)\\src\\Chummer.Media.Contracts\\bin\\$(Configuration)" in ai_project
    assert "$(ChummerMediaFactoryRoot)\\src\\Chummer.Media.Factory.Runtime\\bin\\$(Configuration)" in ai_project
    assert '<ProjectReference Include="$(ChummerMediaFactoryRoot)\\src\\Chummer.Media.Contracts' in ai_project
    assert '<ProjectReference Include="$(ChummerMediaFactoryRoot)\\src\\Chummer.Media.Factory.Runtime' in ai_project


def test_extraction_verifier_accepts_configurable_media_factory_owner_root() -> None:
    verifier = EXTRACTION_VERIFIER.read_text(encoding="utf-8")

    assert "usesConfiguredMediaContractsRoot" in verifier
    assert "usesConfiguredMediaRuntimeRoot" in verifier
    assert "$(ChummerMediaFactoryRoot)\\src\\Chummer.Media.Contracts\\bin\\$(Configuration)" in verifier
    assert "$(ChummerMediaFactoryRoot)\\src\\Chummer.Media.Contracts\\Chummer.Media.Contracts.csproj" in verifier
    assert "$(ChummerMediaFactoryRoot)\\src\\Chummer.Media.Factory.Runtime\\bin\\$(Configuration)" in verifier
    assert "$(ChummerMediaFactoryRoot)\\src\\Chummer.Media.Factory.Runtime\\Chummer.Media.Factory.Runtime.csproj" in verifier
