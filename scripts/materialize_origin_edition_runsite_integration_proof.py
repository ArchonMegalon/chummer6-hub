#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from magicai_pool_registry import magicai_api_missing_aliases as shared_magicai_api_missing_aliases
from magicai_pool_registry import magicai_api_ready_aliases as shared_magicai_api_ready_aliases
from magicai_pool_registry import magicai_declared_aliases as shared_magicai_declared_aliases
from magicai_pool_registry import magicai_login_ready_aliases as shared_magicai_login_ready_aliases
from magicai_pool_registry import magicai_platform_audit_summary as shared_magicai_platform_audit_summary
from origin_edition_context import OriginEditionContext
from origin_edition_provider_registry import OriginProviderCapabilityRegistry


CONTRACT_NAME = "chummer.origin_edition.runsite_integration_proof.v1"
DEFAULT_EVIDENCE_ROOT = Path("/docker/chummercomplete/.tmp/origin-dossier-fresh-gold")
DEFAULT_MAGICAI_PLATFORM_AUDIT = Path(".codex-studio/published/MAGICAI_PLATFORM_ACCESS.generated.json")


def now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def read_json(path: Path) -> dict[str, Any]:
    parsed = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError(f"{path}: expected JSON object")
    return parsed


def read_json_object(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def env_assignments(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    assignments: dict[str, str] = {}
    for line in read_text(path).splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        if key:
            assignments[key] = value.strip()
    return assignments


def env_key_present(path: Path, key: str) -> bool:
    return bool(env_assignments(path).get(key, "").strip())


def _compact(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _key_matches_token(key: str, token: str) -> bool:
    compact_key = _compact(key)
    compact_token = _compact(token)
    return bool(compact_token and compact_token in compact_key)


def _has_nonempty_matching_env_key(assignments: dict[str, str], token: str) -> bool:
    credential_markers = ("API_KEY", "TOKEN", "EMAIL", "USERNAME", "BASE_URL", "ACCOUNT_EMAILS")
    return any(
        value.strip()
        and _key_matches_token(key, token)
        and any(marker in key.upper() for marker in credential_markers)
        for key, value in assignments.items()
    )


def _unmixr_account_available(*assignment_sets: dict[str, str]) -> bool:
    return bool(_unmixr_voice_ready_aliases(*assignment_sets))


def _unmixr_account_api_available(*assignment_sets: dict[str, str]) -> bool:
    assignments = _merged_assignments(*assignment_sets)
    if assignments.get("UNMIXR_API_KEY", "").strip():
        return True
    return any(
        value.strip() and re.fullmatch(r"UNMIXR_ACCOUNT_.+_API_KEY", key)
        for key, value in assignments.items()
    )


def _unmixr_voice_ready_aliases(*assignment_sets: dict[str, str]) -> list[str]:
    assignments = _merged_assignments(*assignment_sets)
    ready: list[str] = []
    if assignments.get("UNMIXR_API_KEY", "").strip() and assignments.get("UNMIXR_VOICE_ID", "").strip():
        ready.append("default")
    for alias in _unmixr_account_aliases(assignments):
        if (
            assignments.get(f"UNMIXR_ACCOUNT_{alias}_API_KEY", "").strip()
            and assignments.get(f"UNMIXR_ACCOUNT_{alias}_VOICE_ID", "").strip()
        ):
            ready.append(alias.lower())
    return ready


def _unmixr_voice_missing_aliases(*assignment_sets: dict[str, str]) -> list[str]:
    assignments = _merged_assignments(*assignment_sets)
    missing: list[str] = []
    if assignments.get("UNMIXR_API_KEY", "").strip() and not assignments.get("UNMIXR_VOICE_ID", "").strip():
        missing.append("default")
    for alias in _unmixr_account_aliases(assignments):
        if (
            assignments.get(f"UNMIXR_ACCOUNT_{alias}_API_KEY", "").strip()
            and not assignments.get(f"UNMIXR_ACCOUNT_{alias}_VOICE_ID", "").strip()
        ):
            missing.append(alias.lower())
    return missing


def _magicai_declared_aliases(*assignment_sets: dict[str, str]) -> list[str]:
    return shared_magicai_declared_aliases(*assignment_sets)


def _magicai_login_ready_aliases(*assignment_sets: dict[str, str]) -> list[str]:
    return shared_magicai_login_ready_aliases(*assignment_sets)


def _magicai_api_ready_aliases(*assignment_sets: dict[str, str]) -> list[str]:
    return shared_magicai_api_ready_aliases(*assignment_sets)


def _magicai_api_missing_aliases(*assignment_sets: dict[str, str]) -> list[str]:
    return shared_magicai_api_missing_aliases(*assignment_sets)


def _magicai_platform_audit_summary(repo_root: Path) -> dict[str, Any]:
    return shared_magicai_platform_audit_summary(repo_root, assignment_sets=(env_assignments(repo_root / ".env"),))


def _merged_assignments(*assignment_sets: dict[str, str]) -> dict[str, str]:
    assignments: dict[str, str] = {}
    for source in assignment_sets:
        assignments.update(source)
    return assignments


def _unmixr_account_aliases(assignments: dict[str, str]) -> set[str]:
    aliases: set[str] = set()
    for key, value in assignments.items():
        if not value.strip():
            continue
        match = re.fullmatch(r"UNMIXR_ACCOUNT_(.+)_API_KEY", key)
        if match:
            aliases.add(match.group(1))
    return aliases


def configured_provider_available(
    inventory_text: str,
    assignments: dict[str, str],
    tokens: tuple[str, ...],
    *,
    strict_provider_tokens: tuple[str, ...] = (),
) -> bool:
    strict = {_compact(token) for token in strict_provider_tokens}
    for token in tokens:
        compact_token = _compact(token)
        if not compact_token or compact_token in strict:
            continue
        if token.lower() in inventory_text and _has_nonempty_matching_env_key(assignments, token):
            return True
    return False


def source_metadata(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {
            "present": False,
            "sha256": "",
            "sizeBytes": 0,
            "valuesStoredInReceipt": False,
        }
    return {
        "present": True,
        "sha256": sha256_file(path),
        "sizeBytes": path.stat().st_size,
        "valuesStoredInReceipt": False,
    }


def contains_all(text: str, needles: list[str]) -> bool:
    return all(needle in text for needle in needles)


def check_file_contains(name: str, path: Path, needles: list[str], root: Path) -> dict[str, Any]:
    item: dict[str, Any] = {
        "name": name,
        "path": path.relative_to(root).as_posix() if path.is_relative_to(root) else path.as_posix(),
        "required": True,
    }
    if not path.is_file():
        item["status"] = "missing_file"
        item["missing"] = needles
        return item
    text = read_text(path)
    missing = [needle for needle in needles if needle not in text]
    item["sha256"] = sha256_file(path)
    item["status"] = "pass" if not missing else "missing_expected_content"
    item["missing"] = missing
    return item


def provider_inventory_signals(ltd_text: str, ea_env: Path, ea_env_text: str, local_env: Path) -> dict[str, Any]:
    registry = OriginProviderCapabilityRegistry.from_env()
    repo_root = local_env.parent.resolve()
    local_env_text = read_text(local_env) if local_env.is_file() else ""
    provider_inventory_text = f"{ltd_text}\n{ea_env_text}\n{local_env_text}".lower()
    ea_assignments = env_assignments(ea_env)
    local_assignments = env_assignments(local_env)
    merged_assignments = _merged_assignments(local_assignments, ea_assignments)
    magicai_declared_aliases = _magicai_declared_aliases(local_assignments, ea_assignments)
    magicai_login_ready_aliases = _magicai_login_ready_aliases(local_assignments, ea_assignments)
    magicai_api_ready_aliases = _magicai_api_ready_aliases(local_assignments, ea_assignments)
    magicai_api_missing_aliases = _magicai_api_missing_aliases(local_assignments, ea_assignments)
    magicai_platform_audit = _magicai_platform_audit_summary(repo_root)
    pending_login_ready = set(magicai_login_ready_aliases) - set(magicai_api_ready_aliases)
    accessible_accounts = set(magicai_platform_audit["accessibleAccounts"])
    forbidden_accounts = set(magicai_platform_audit["forbiddenAccounts"])
    login_failed_accounts = set(magicai_platform_audit["loginFailedAccounts"])
    unverified_accounts = set(magicai_platform_audit["unverifiedAccounts"])
    return {
        "crezloTours": "Crezlo Tours" in ltd_text and "EA_CREZLO_LOGIN_EMAIL" in ea_env_text,
        "pano2vr": "Pano2VR" in ltd_text and "PANO2VR_LICENSE_KEY" in ea_env_text,
        "unmixr": "Unmixr AI" in ltd_text and _unmixr_account_available(ea_assignments),
        "unmixrApiConfigured": "Unmixr AI" in ltd_text and _unmixr_account_api_available(ea_assignments),
        "youbooks": "YouBooks" in ltd_text and "YOUBOOKS_ACCOUNT_EMAILS" in ea_env_text,
        "firstBook": "First Book ai" in ltd_text,
        "inkfluence": env_key_present(local_env, "CHUMMER_EA_INKFLUENCE_BASE_URL"),
        "magicfit": configured_provider_available(
            provider_inventory_text,
            merged_assignments,
            registry.visual_preferred_provider_tokens,
        ),
        "configuredPreferredVisualProvider": configured_provider_available(
            provider_inventory_text,
            merged_assignments,
            registry.visual_preferred_provider_tokens,
        ),
        "configuredApprovedVisualProvider": configured_provider_available(
            provider_inventory_text,
            merged_assignments,
            registry.visual_provider_tokens,
        ),
        "configuredRenderPoolProvider": configured_provider_available(
            provider_inventory_text,
            merged_assignments,
            registry.render_pool_provider_tokens,
        ),
        "magicaiLoginConfigured": bool(magicai_login_ready_aliases),
        "magicaiApiConfigured": bool(magicai_api_ready_aliases),
        "magicaiDeclaredAccountCount": len(magicai_declared_aliases),
        "magicaiLoginReadyAccountCount": len(magicai_login_ready_aliases),
        "magicaiApiReadyAccountCount": len(magicai_api_ready_aliases),
        "magicaiAccountsMissingApiKey": magicai_api_missing_aliases,
        "magicaiPlatformAuditPresent": magicai_platform_audit["present"],
        "magicaiPlatformAccessibleAccounts": magicai_platform_audit["accessibleAccounts"],
        "magicaiPlatformForbiddenAccounts": magicai_platform_audit["forbiddenAccounts"],
        "magicaiPlatformLoginFailedAccounts": magicai_platform_audit["loginFailedAccounts"],
        "magicaiPlatformUnverifiedAccounts": magicai_platform_audit["unverifiedAccounts"],
        "magicaiPlatformPendingMintableAccounts": sorted(pending_login_ready & accessible_accounts),
        "magicaiPlatformPendingForbiddenAccounts": sorted(pending_login_ready & forbidden_accounts),
        "magicaiPlatformPendingLoginFailedAccounts": sorted(pending_login_ready & login_failed_accounts),
        "magicaiPlatformPendingUnverifiedAccounts": sorted(pending_login_ready & unverified_accounts),
        "configuredManuscriptProvider": configured_provider_available(
            provider_inventory_text,
            merged_assignments,
            registry.manuscript_provider_tokens,
        ),
        "configuredAudioProvider": configured_provider_available(
            provider_inventory_text,
            merged_assignments,
            registry.audio_provider_tokens,
            strict_provider_tokens=("unmixr",),
        ),
    }


def origin_gold_capability_signals(provider_signals: dict[str, Any]) -> dict[str, bool]:
    manuscript_providers = ("inkfluence", "youbooks", "firstBook", "configuredManuscriptProvider")
    audio_providers = ("unmixr", "inkfluence", "configuredAudioProvider")
    return {
        "provider_inventory_present": any(provider_signals.values()),
        "manuscript_or_edition_provider_available": any(provider_signals.get(provider) is True for provider in manuscript_providers),
        "premium_audio_provider_available": any(provider_signals.get(provider) is True for provider in audio_providers),
        "preferred_visual_provider_available": any(
            provider_signals.get(provider) is True
            for provider in ("magicfit", "configuredPreferredVisualProvider")
        ),
        "approved_visual_provider_available": any(
            provider_signals.get(provider) is True
            for provider in ("magicfit", "configuredApprovedVisualProvider")
        ),
        "shared_render_pool_available": provider_signals.get("magicaiApiConfigured") is True,
        "optional_overflow_accounts_do_not_block": True,
    }


def receipt_status(name: str, path: Path, root: Path, expected_status: str = "pass") -> dict[str, Any]:
    item: dict[str, Any] = {
        "name": name,
        "path": path.relative_to(root).as_posix() if path.is_relative_to(root) else path.as_posix(),
        "required": True,
    }
    if not path.is_file():
        item["status"] = "missing_file"
        return item
    payload = read_json(path)
    item["sha256"] = sha256_file(path)
    item["reportedStatus"] = payload.get("status")
    item["goldEligible"] = payload.get("goldEligible")
    item["status"] = "pass" if str(payload.get("status") or "").lower() == expected_status else "unexpected_status"
    return item


def receipt_summary(name: str, path: Path, root: Path) -> dict[str, Any]:
    item: dict[str, Any] = {
        "name": name,
        "path": path.relative_to(root).as_posix() if path.is_relative_to(root) else path.as_posix(),
        "required": True,
    }
    if not path.is_file():
        item["status"] = "missing_file"
        return item
    payload = read_json(path)
    item["status"] = "present"
    item["sha256"] = sha256_file(path)
    item["contractName"] = payload.get("contractName")
    item["reportedStatus"] = payload.get("status")
    item["goldEligible"] = payload.get("goldEligible")
    item["goalCompletionClaimAllowed"] = payload.get("goalCompletionClaimAllowed")
    item["blockers"] = payload.get("blockers", [])
    item["failedCodes"] = payload.get("failedCodes", [])
    return item


def materialize(
    repo_root: Path,
    ea_root: Path,
    evidence_root: Path,
    output: Path,
    context: OriginEditionContext | None = None,
    *,
    runsite_env: Path | None = None,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    ea_root = ea_root.resolve()
    evidence_root = evidence_root.resolve()
    context = context or OriginEditionContext.from_env(require_explicit=True)
    branch = context.branch(evidence_root)
    checks: list[dict[str, Any]] = []

    checks.append(
        check_file_contains(
            "shared_governed_render_contract",
            repo_root / "Chummer.Run.Api/Services/Community/HorizonGovernedRenderRequestComposerService.cs",
            [
                'public const string OrchestrationLane = "ea_governed_render";',
                'public const string ContractName = "chummer6-hub.horizon_governed_render_request.v1";',
                'blocked.Add("governed render evidence refs");',
            ],
            repo_root,
        )
    )
    checks.append(
        check_file_contains(
            "runsite_scene_render_bridge",
            repo_root / "Chummer.Run.Api/Services/RunsiteOrientationArtifactRequestBridgeService.cs",
            [
                'private const string DefaultPreferredProvider = "magicai";',
                'ArtifactKindOrCapabilityId: "runsite-scene-render"',
                "GovernedRenderRequest: new HorizonGovernedRenderRequestCreateRequest(",
            ],
            repo_root,
        )
    )
    checks.append(
        check_file_contains(
            "propertyquarry_apartment_video_bridge",
            repo_root / "Chummer.Run.Api/Services/PropertyquarryApartmentVideoArtifactRequestBridgeService.cs",
            [
                'private const string DefaultPreferredProvider = "magicai";',
                'ArtifactKindOrCapabilityId: "propertyquarry-apartment-video"',
                "GovernedRenderRequest: new HorizonGovernedRenderRequestCreateRequest(",
                "propertyquarry:property-packet",
                "propertyquarry:property-continuity",
            ],
            repo_root,
        )
    )
    checks.append(
        check_file_contains(
            "propertyquarry_apartment_video_internal_route",
            repo_root / "Chummer.Run.Api/Controllers/InternalPropertyquarryApartmentVideoController.cs",
            [
                '[HttpPost("/api/internal/propertyquarry/apartment-videos/requests")]',
                '[HttpPost("/api/internal/propertyquarry/apartment-videos/artifact-requests")]',
                "PropertyquarryApartmentVideoArtifactRequestBridgeResult",
            ],
            repo_root,
        )
    )
    checks.append(
        check_file_contains(
            "propertyquarry_apartment_video_signed_in_route",
            repo_root / "Chummer.Run.Api/Controllers/CampaignSpineController.cs",
            [
                '[HttpPost("me/property-workspaces/{propertyId}/apartment-video")]',
                "PropertyquarryApartmentVideoRequest",
                "BuildPropertyquarryApartmentVideoLane(property)",
                "apartmentVideoRequestApiHrefTemplate",
            ],
            repo_root,
        )
    )
    checks.append(
        check_file_contains(
            "runsite_handoff_constraints",
            repo_root / "RUNSITE_HANDOFF.md",
            [
                "Before implementing, inspect the newest entries in `LTDs.md` and `.env`.",
                "Do not hardcode secrets from `.env` into committed files.",
                "Wire from env only.",
                "Rybbit",
                "Do not deploy unless explicitly asked.",
            ],
            repo_root,
        )
    )
    checks.append(
        check_file_contains(
            "origin_dossier_authenticated_page",
            repo_root / "Chummer.Run.Api/Views/Accounts/OriginDossier.cshtml",
            [
                "data-origin-edition-tabs",
                "href=\"#origin-edition-read\"",
                "href=\"#origin-edition-listen\"",
                "href=\"#origin-edition-watch\"",
                "href=\"#origin-edition-canon-audit\"",
                "Read the ebook",
                "Listen in Audiobookshelf",
                "Watch selected cinematic scene",
                "data-chummer-owns-canon=\"true\"",
                "data-provider-created-facts-auto-canon=\"false\"",
            ],
            repo_root,
        )
    )
    checks.append(
        check_file_contains(
            "origin_dossier_private_route_controller",
            repo_root / "Chummer.Run.Api/Controllers/AccountsController.cs",
            [
                "[HttpGet(\"/account/work/origin-dossiers/{originDossierProjectId}\")]",
                "_identity.RequireSubjectAsync",
                "Redirect($\"/login?next={Uri.EscapeDataString(currentPath)}\")",
                "[HttpGet(\"/account/work/origin-dossiers/{originDossierProjectId}/{artifactKind}\")]",
                "PhysicalFile(artifact.Path, artifact.ContentType, enableRangeProcessing: true)",
            ],
            repo_root,
        )
    )
    checks.append(
        check_file_contains(
            "origin_publication_gold_gate_service",
            repo_root / "Chummer.Run.Api/Services/Community/OriginDossierPublicationService.cs",
            [
                'DefaultApprovedManuscriptProviderTokens = ["Subscribr"]',
                "FullStoryManuscriptToken",
                "StoryEditionEbookToken",
                "CharacterVisibleCinematicToken",
                "HasFinalNoFallbackNoSentinelReceipt",
                "HasCoverConsistencyReceipt",
                "CHUMMER_ORIGIN_AUDIOBOOKSHELF_TRUSTED_HOSTS",
                "OriginDossier:AudiobookshelfTrustedHosts",
                "FinalNoFallbackNoSentinelAuditReceiptPath",
            ],
            repo_root,
        )
    )
    checks.append(
        check_file_contains(
            "origin_provider_account_registry",
            repo_root / "Chummer.Run.Api/Services/Community/OriginDossierProviderAccountRegistry.cs",
            [
                "ResolveAliases(",
                "ResolveHosts(",
                '"manuscript"',
                '"audio"',
                '"visual"',
                '"packaging"',
                '"audiobookshelf"',
                "DisabledStatuses",
                "rawRegistry",
            ],
            repo_root,
        )
    )
    checks.append(
        check_file_contains(
            "origin_provider_account_registry_tests",
            repo_root / "Chummer.Tests/OriginDossierProviderAccountRegistryTests.cs",
            [
                "ManuscriptAndAudioRegistriesResolveOnlyEnabledRoleMatchedAccounts",
                "AudiobookshelfRegistryNormalizesTrustedHostsFromProviderAccounts",
                "VisualRegistryDoesNotTreatRunsiteMagicAiSceneAccountsAsOriginVisualAccounts",
                "PackagingRegistryAcceptsExplicitBookArtifactAccounts",
            ],
            repo_root,
        )
    )
    checks.append(
        check_file_contains(
            "rybbit_env_only_layout",
            repo_root / "Chummer.Run.Api/Views/Shared/_Layout.cshtml",
            [
                "RYBBIT_CHUMMER_RUN_SITE_ID",
                "RYBBIT_CHUMMER_RUN_SCRIPT_URL",
                "RYBBIT_CHUMMER_RUN_SCRIPT_ORIGIN",
                "RYBBIT_CHUMMER_RUN_ALLOW_SAME_HOST_PROXY",
                "GetEnvironmentVariable",
            ],
            repo_root,
        )
    )
    checks.append(
        check_file_contains(
            "runsite_env_example_rybbit",
            repo_root / ".env.example",
            [
                "RYBBIT_CHUMMER_RUN_SITE_ID=",
                "RYBBIT_CHUMMER_RUN_SCRIPT_URL=",
                "RYBBIT_CHUMMER_RUN_SCRIPT_ORIGIN=https://app.rybbit.io",
                "RYBBIT_CHUMMER_RUN_ALLOW_SAME_HOST_PROXY=false",
            ],
            repo_root,
        )
    )
    checks.append(
        check_file_contains(
            "runsite_compose_rybbit",
            repo_root / "docker-compose.public-edge.yml",
            [
                "RYBBIT_CHUMMER_RUN_SITE_ID: ${RYBBIT_CHUMMER_RUN_SITE_ID:-}",
                "RYBBIT_CHUMMER_RUN_SCRIPT_URL: ${RYBBIT_CHUMMER_RUN_SCRIPT_URL:-}",
                "RYBBIT_CHUMMER_RUN_SCRIPT_ORIGIN: ${RYBBIT_CHUMMER_RUN_SCRIPT_ORIGIN:-https://app.rybbit.io}",
                "RYBBIT_CHUMMER_RUN_ALLOW_SAME_HOST_PROXY: ${RYBBIT_CHUMMER_RUN_ALLOW_SAME_HOST_PROXY:-false}",
            ],
            repo_root,
        )
    )

    local_env = runsite_env.resolve() if runsite_env is not None else repo_root / ".env"
    ea_env = ea_root / ".env"
    ltds = ea_root / "LTDs.md"
    ltd_text = read_text(ltds) if ltds.is_file() else ""
    ea_env_text = read_text(ea_env) if ea_env.is_file() else ""
    ea_assignments = env_assignments(ea_env)
    provider_signals = provider_inventory_signals(ltd_text, ea_env, ea_env_text, local_env)
    capability_signals = origin_gold_capability_signals(provider_signals)
    inventory = {
        "runsiteEnvInspected": local_env.is_file(),
        "eaEnvInspected": ea_env.is_file(),
        "ltdInventoryInspected": ltds.is_file(),
        "sharedRenderLaneSignals": {
            "governedRenderContractPresent": check_file_contains(
                "shared_governed_render_contract",
                repo_root / "Chummer.Run.Api/Services/Community/HorizonGovernedRenderRequestComposerService.cs",
                ['public const string OrchestrationLane = "ea_governed_render";'],
                repo_root,
            )["status"]
            == "pass",
            "runsiteBridgePresent": check_file_contains(
                "runsite_scene_render_bridge",
                repo_root / "Chummer.Run.Api/Services/RunsiteOrientationArtifactRequestBridgeService.cs",
                ['ArtifactKindOrCapabilityId: "runsite-scene-render"'],
                repo_root,
            )["status"]
            == "pass",
            "propertyquarryBridgePresent": check_file_contains(
                "propertyquarry_apartment_video_bridge",
                repo_root / "Chummer.Run.Api/Services/PropertyquarryApartmentVideoArtifactRequestBridgeService.cs",
                ['ArtifactKindOrCapabilityId: "propertyquarry-apartment-video"'],
                repo_root,
            )["status"]
            == "pass",
            "propertyquarryInternalRoutePresent": check_file_contains(
                "propertyquarry_apartment_video_internal_route",
                repo_root / "Chummer.Run.Api/Controllers/InternalPropertyquarryApartmentVideoController.cs",
                ['[HttpPost("/api/internal/propertyquarry/apartment-videos/artifact-requests")]'],
                repo_root,
            )["status"]
            == "pass",
            "propertyquarrySignedInRoutePresent": check_file_contains(
                "propertyquarry_apartment_video_signed_in_route",
                repo_root / "Chummer.Run.Api/Controllers/CampaignSpineController.cs",
                ['[HttpPost("me/property-workspaces/{propertyId}/apartment-video")]'],
                repo_root,
            )["status"]
            == "pass",
        },
        "sourceFiles": {
            "runsiteEnv": source_metadata(local_env),
            "eaEnv": source_metadata(ea_env),
            "ltdInventory": source_metadata(ltds),
        },
        "rybbitRunKeysPresent": {
            key: env_key_present(local_env, key)
            for key in [
                "RYBBIT_CHUMMER_RUN_SITE_ID",
                "RYBBIT_CHUMMER_RUN_SCRIPT_URL",
                "RYBBIT_CHUMMER_RUN_SCRIPT_ORIGIN",
                "RYBBIT_CHUMMER_RUN_ALLOW_SAME_HOST_PROXY",
            ]
        },
        "newestProviderInventorySignals": provider_signals,
        "unmixrVoiceReadyAccounts": _unmixr_voice_ready_aliases(ea_assignments),
        "unmixrAccountsMissingVoiceId": _unmixr_voice_missing_aliases(ea_assignments),
        "magicaiDeclaredAccounts": _magicai_declared_aliases(env_assignments(local_env), ea_assignments),
        "magicaiLoginReadyAccounts": _magicai_login_ready_aliases(env_assignments(local_env), ea_assignments),
        "magicaiApiReadyAccounts": _magicai_api_ready_aliases(env_assignments(local_env), ea_assignments),
        "magicaiAccountsMissingApiKey": _magicai_api_missing_aliases(env_assignments(local_env), ea_assignments),
        "magicaiPlatformAccessAudit": _magicai_platform_audit_summary(repo_root),
        "originGoldCapabilitySignals": capability_signals,
    }
    checks.append(
        {
            "name": "newest_ltd_and_env_inputs_inspected",
            "required": True,
            "status": "pass"
            if inventory["runsiteEnvInspected"]
            and inventory["eaEnvInspected"]
            and inventory["ltdInventoryInspected"]
            and all(inventory["rybbitRunKeysPresent"].values())
            and all(inventory["originGoldCapabilitySignals"].values())
            else "missing_expected_inventory_signal",
        }
    )

    checks.append(
        receipt_status(
            "live_import_request",
            evidence_root / "ORIGIN_DOSSIER_LIVE_IMPORT_REQUEST.generated.json",
            evidence_root,
        )
    )
    checks.append(
        receipt_status(
            "local_authenticated_route_proof",
            branch / "authenticated-chummer-route-live.receipt.json",
            evidence_root,
        )
    )
    checks.append(
        receipt_status(
            "final_no_sentinel_media_audit",
            branch / "final-no-fallback-no-sentinel-audit.receipt.json",
            evidence_root,
        )
    )
    deployed_probe = branch / "deployed-chummer-browser-probe.receipt.json"
    deployed_payload = read_json(deployed_probe) if deployed_probe.is_file() else {}
    deployed_handoff = branch / "deployed-operator-handoff.receipt.json"
    gold_audit = evidence_root / "ORIGIN_EDITION_GOLD_CURRENT_GAP_AUDIT.generated.json"
    deployed_status = str(deployed_payload.get("status") or "").lower()
    handoff_summary = receipt_summary("deployed_operator_handoff", deployed_handoff, evidence_root)
    gold_summary = receipt_summary("current_gold_gap_audit", gold_audit, evidence_root)
    gold_evidence_passed = (
        deployed_status == "pass"
        and str(gold_summary.get("reportedStatus") or "").lower() == "pass"
        and gold_summary.get("goalCompletionClaimAllowed") is True
    )
    check_statuses = {str(item.get("name") or ""): item.get("status") for item in checks if isinstance(item, dict)}
    rybbit_env_only = (
        check_statuses.get("rybbit_env_only_layout") == "pass"
        and check_statuses.get("runsite_env_example_rybbit") == "pass"
        and check_statuses.get("runsite_compose_rybbit") == "pass"
    )
    newest_ltds_inspected = (
        inventory["runsiteEnvInspected"]
        and inventory["eaEnvInspected"]
        and inventory["ltdInventoryInspected"]
        and all(inventory["originGoldCapabilitySignals"].values())
    )
    env_inspected = inventory["runsiteEnvInspected"] and inventory["eaEnvInspected"]
    runsite_handoff_verified = check_statuses.get("runsite_handoff_constraints") == "pass"
    secret_values_stored = False
    deployment_performed = False

    blocked = [item["name"] for item in checks if item.get("status") != "pass"]
    payload: dict[str, Any] = {
        "contractName": CONTRACT_NAME,
        "generatedAtUtc": now_iso(),
        "status": "pass" if not blocked else "blocked",
        "integrationEligible": not blocked,
        "goldEligible": not blocked and gold_evidence_passed,
        "goalCompletionClaimAllowed": False,
        "namespace": context.resolved_namespace,
        "projectId": context.project_id,
        "runsiteHandoffVerified": runsite_handoff_verified,
        "newestLtdsInspected": newest_ltds_inspected,
        "envInspected": env_inspected,
        "rybbitEnvOnly": rybbit_env_only,
        "deploymentPerformed": deployment_performed,
        "secretValuesStored": secret_values_stored,
        "checks": checks,
        "blockedChecks": blocked,
        "inventoryInspection": inventory,
        "deployedBrowserProbe": {
            "path": deployed_probe.relative_to(evidence_root).as_posix(),
            "status": deployed_payload.get("status"),
            "deployedRouteClaimAllowed": deployed_payload.get("deployedRouteClaimAllowed"),
            "blockers": deployed_payload.get("blockers", []),
            "sha256": sha256_file(deployed_probe) if deployed_probe.is_file() else "",
        },
        "deployedOperatorHandoff": handoff_summary,
        "currentGoldGapAudit": gold_summary,
        "privacy": {
            "envValuesExposed": False,
            "rawCredentialExposed": False,
            "rawSessionTokenExposed": False,
            "deploymentPerformed": deployment_performed,
        },
        "claim": "RunSite integration is wired and locally proven; final Gold still requires a deployed owner-session browser proof.",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Materialize Origin Edition RunSite integration proof without exposing secrets.")
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--ea-root", type=Path, default=Path("/docker/EA"))
    parser.add_argument("--evidence-root", type=Path, default=DEFAULT_EVIDENCE_ROOT)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--project-id")
    parser.add_argument("--family-name")
    parser.add_argument("--given-name")
    parser.add_argument("--runner-name")
    parser.add_argument("--namespace")
    parser.add_argument("--base-url")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    context = OriginEditionContext.from_env(
        project_id=args.project_id,
        family_name=args.family_name,
        given_name=args.given_name,
        runner_name=args.runner_name,
        namespace=args.namespace,
        base_url=args.base_url,
        require_explicit=True,
    )
    output = args.output or context.branch(args.evidence_root) / "runsite-integration-proof.receipt.json"
    payload = materialize(args.repo_root, args.ea_root, args.evidence_root, output, context)
    print(json.dumps(payload, sort_keys=True))
    return 0 if payload.get("status") == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
