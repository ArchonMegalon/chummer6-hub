#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "$0")" && pwd)"
if [[ -f "$script_dir/_env.sh" ]]; then
  source "$script_dir/_env.sh"
fi

ROOT_DIR="$(cd "$script_dir/../.." && pwd)"
cd "$ROOT_DIR"

export CHUMMER_VERIFY_RELEASE_PROOF_MAX_AGE_SECONDS="${CHUMMER_VERIFY_RELEASE_PROOF_MAX_AGE_SECONDS:-315360000}"

if ! command -v rg >/dev/null 2>&1; then
  rg() {
    local invert=0
    local with_line_numbers=0
    local pattern=""
    local files=()
    while [[ $# -gt 0 ]]; do
      case "$1" in
        -v)
          invert=1
          ;;
        -n)
          with_line_numbers=1
          ;;
        --)
          ;;
        -*)
          echo "unsupported rg compatibility option: $1" >&2
          return 2
          ;;
        *)
          if [[ -z "$pattern" ]]; then
            pattern="$1"
          else
            files+=("$1")
          fi
          ;;
      esac
      shift
    done

    if [[ -z "$pattern" ]]; then
      echo "rg compatibility shim requires a pattern" >&2
      return 2
    fi

    local args=()
    if [[ $with_line_numbers -eq 1 ]]; then
      args+=(-n)
    fi
    if [[ $invert -eq 1 ]]; then
      args+=(-v)
    fi

    grep -E "${args[@]}" -- "$pattern" "${files[@]}"
  }
fi

PYTHON_BIN="${PYTHON_BIN:-}"
if [[ -z "$PYTHON_BIN" ]]; then
  if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
  elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
  else
    PYTHON_BIN=""
  fi
fi

TMP_ROOT="${ROOT_DIR}/.tmp"
if ! mkdir -p "$TMP_ROOT" 2>/dev/null || [[ ! -w "$TMP_ROOT" ]]; then
  TMP_ROOT="${TMPDIR:-/tmp}"
fi
TMP_DIR="$(mktemp -d "${TMP_ROOT}/run-services-verification.XXXXXX")"
trap 'rm -rf "$TMP_DIR"' EXIT
TEST_BIN="Chummer.Tests/bin/Debug/net10.0"

resolve_artifact() {
  local label="$1"
  shift
  local candidate
  for candidate in "$@"; do
    if [[ -f "$candidate" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done

  echo "missing artifact for ${label}" >&2
  return 1
}

copy_artifact() {
  local label="$1"
  local output_name="$2"
  shift 2
  local source_path
  source_path="$(resolve_artifact "$label" "$@")" || return 1
  cp "$source_path" "${TMP_DIR}/${output_name}"
}

if [ ! -f Chummer.Play.Contracts/Chummer.Play.Contracts.csproj ]; then
  echo "skip run-services verification: repository slice does not include the full local run-services project tree"
  exit 0
fi

test -f docs/HOSTED_ADAPTER_AUTHORITY.md
test -f docs/ASSISTANT_PLANE_AUTHORITY.md
test -f docs/HOSTED_DOCS_HELP_CONSUMERS.md
test -f docs/HOSTED_FEEDBACK_AND_OPERATOR_CONSUMERS.md
test -f docs/HUB_COMMUNITY_LEDGER_PLANE.md
test -f docs/HUB_IDENTITY_AND_CHANNEL_MODEL.md
test -f docs/PUBLIC_LANDING_SURFACE.md
rg -n 'BrowserActGatewayAdapter|MarkupGoGatewayAdapter|PeekShotGatewayAdapter|SessionProjectionSkillToolAdapter|LoreSearchSkillToolAdapter|PromptRegistry|GmOpsBoardService|CreativeAssetsController|SpiderController|DirectorPolicyEngine|InteropController|AiDirectorController|survey adapters are not live yet' \
  docs/HOSTED_ADAPTER_AUTHORITY.md >/dev/null
rg -n 'coach.system|PromptRegistry|LoreService|PersonaMemoryService|SessionMemoryService|AiGatewayService|EvaluationStore|FastSignalDetector|SpiderDeepIngestionService|DirectorPolicyEngine|InterruptionBudgetService|SpiderCardActionService|GmOpsBoardService|AiDirectorController|PipelineObservabilityController' \
  docs/ASSISTANT_PLANE_AUTHORITY.md >/dev/null
rg -n 'Chummer\.Play\.Contracts\.Docs\.RuntimeDocQuery|RuntimeDocResult|PromptTemplates|PreviewPrompt|SearchLore|QueryPersonaMemory|DraftFromSession|compatibility-only|second system of record' \
  docs/HOSTED_DOCS_HELP_CONSUMERS.md >/dev/null
rg -n 'HubRegistryController\.AddReview|PublicationsController\.Review|PublicationsController\.Moderate|GmOpsBoardController\.CreatePrepAssetFromProject|GmOpsBoardController\.GetProjection|GmOpsBoardController\.UpdateChecklist|GmOpsBoardController\.Reveal|SpiderController\.QueueManual|SpiderController\.ExecuteAction|DeliveryOutboxService\.RecordAction|PipelineObservabilityController\.GetProjection|advisory input with receipts|hidden write-owning side systems' \
  docs/HOSTED_FEEDBACK_AND_OPERATOR_CONSUMERS.md >/dev/null
rg -n 'AccountsController|GroupsController|BoostCodesController|BoostSessionsController|LedgerController|LeaderboardsController|EntitlementsController|BoosterReceiptsController|fact ledger|reward journal|entitlement journal|Fleet executes sponsored participant lanes' \
  docs/HUB_COMMUNITY_LEDGER_PLANE.md >/dev/null
rg -n 'linked identities|channel links|Google|Facebook|Telegram|EA remains the orchestrator brain|/api/v1/accounts/me/links' \
  docs/HUB_IDENTITY_AND_CHANNEL_MODEL.md >/dev/null
rg -n 'PUBLIC_LANDING_MANIFEST\.yaml|PUBLIC_FEATURE_REGISTRY\.yaml|PUBLIC_LANDING_ASSET_REGISTRY\.yaml|/what-is-chummer|/downloads|/participate|/status|/artifacts|/login|/signup|/logout|product front door|Create account|self-link|external fallback' \
  docs/PUBLIC_LANDING_SURFACE.md >/dev/null
rg -n 'durable local snapshot|CHUMMER_COMMUNITY_STORE_PATH|parallel intent-only state model' \
  docs/HUB_COMMUNITY_LEDGER_PLANE.md >/dev/null
rg -n 'Chummer\.Campaign\.Contracts|Chummer\.Control\.Contracts|campaign spine truth|product-control truth' \
  README.md docs/HOSTED_BOUNDARY.md docs/HUB_EXTRACTION_ACCEPTANCE.md >/dev/null
rg -n 'user accounts, groups, access/support state, and the canonical community ledger|Chummer\.Run\.Api owns the customer account backbone first: product-level users, groups, support/access flows, device/install linking, and the canonical community ledger|Optional join/boost codes, sponsor sessions, leaderboards, rewards, and entitlements sit on top of that shared account and access plane' \
  README.md >/dev/null
rg -n 'linked identity and channel-link state|EA remains the orchestrator brain behind companion and assistant channels|Telegram, Google, Facebook, and transactional email are adapters around that hub-owned account plane' \
  README.md >/dev/null
rg -n 'public sealed class AccountsController|public sealed class GroupsController|public sealed class BoostCodesController|public sealed class BoostSessionsController|public sealed class LedgerController|public sealed class LeaderboardsController|public sealed class EntitlementsController' \
  Chummer.Run.Api/Controllers/*.cs >/dev/null
rg -n 'public sealed class AccountLinksController' Chummer.Run.Api/Controllers/AccountLinksController.cs >/dev/null
rg -n 'public sealed class PublicLandingController|PublicReleaseManifestService|/what-is-chummer|/downloads|/participate|/status|/artifacts|GetLanding|GuestShellActions|ResolveCardHref' \
  Chummer.Run.Api/Controllers/PublicLandingController.cs >/dev/null
rg -n 'public sealed class CampaignSpineController|api/v1/campaign-spine|GetMyCampaignSummary' \
  Chummer.Run.Api/Controllers/CampaignSpineController.cs >/dev/null
rg -n 'public sealed class AuthController|/login|/signup|/logout|/auth/email/start|/auth/email/callback|/auth/google/start|/auth/google/callback|Create Account|Sign in instead|shell-action' \
  Chummer.Run.Api/Controllers/AuthController.cs >/dev/null
rg -n 'public sealed class AccountService|public sealed class GroupService|public sealed class BoostSessionService|public sealed class LedgerService|public sealed class RewardService|public sealed class EntitlementService|public sealed class LeaderboardService|public sealed class CommunityStore' \
  Chummer.Run.Api/Services/Community/*.cs >/dev/null
rg -n 'public sealed class CampaignSpineService|RunnerDossierProjection|CampaignProjection|RunProjection|CampaignWorkspaceProjection|CampaignReadinessCue|WorkspaceRestoreProjection|AccountCampaignSummary' \
  Chummer.Run.Api/Services/Community/CampaignSpineService.cs >/dev/null
rg -n 'OperatorRole|CampaignVisibilitySummary|ApprovalState|Workspaces|Shared campaign view|GM-ready|Permissions' \
  Chummer.Campaign.Contracts/CampaignContracts.cs \
  Chummer.Run.Api/Views/Accounts/Account.cshtml >/dev/null
rg -n 'public sealed class IdentityLinkService|Google|Facebook|Telegram|EA' \
  Chummer.Run.Api/Services/Community/IdentityLinkService.cs >/dev/null
rg -n 'public sealed class PublicLandingService|PUBLIC_LANDING_MANIFEST\.yaml|PUBLIC_FEATURE_REGISTRY\.yaml|PUBLIC_LANDING_ASSET_REGISTRY\.yaml|guest_shell_actions|asset_slot|auth_routes|registered_overlays|feature registry' \
  Chummer.Run.Api/Services/PublicLandingService.cs >/dev/null
rg -n 'AddHubPublicGuideContext\(\)|AddHubInstallAndOrchestrationAdapters\(\)|AddSingleton<PublicLandingService>\(\)|AddHttpClient<HubBrowserAuthService>\(\)' Chummer.Run.Api/Program.cs Chummer.Run.Api/ServiceCollectionBoundedContextExtensions.cs >/dev/null
rg -n 'EmailAuthStartRequest|EmailAuthStartResponse|EmailAuthCompleteRequest|IdentitySessionRevokeRequest|IdentitySessionRevokeResponse' \
  Chummer.Run.Contracts/IdentityContracts.cs >/dev/null
rg -n 'StartEmailEntry|CompleteEmailEntry|RevokeSession|CHUMMER_IDENTITY_STORE_PATH|preview_inline_link' \
  Chummer.Run.Identity/Services/IdentityAccessService.cs \
  Chummer.Run.Identity/Controllers/IdentityController.cs >/dev/null
rg -n '^GET .*//$' Chummer.Run.Api/Chummer.Run.Api.http -v >/dev/null
rg -n '/login\?next=/home|/participate|/status' Chummer.Run.Api/Chummer.Run.Api.http >/dev/null
rg -n 'CHUMMER_COMMUNITY_STORE_PATH|PersistLocked|File.Move' Chummer.Run.Api/Services/Community/CommunityStore.cs >/dev/null
rg -n 'BoostSessionService|/api/v1/participation/intents|sponsor-session/community-ledger path' Chummer.Run.Api/Controllers/CodexParticipationController.cs >/dev/null
rg -n 'public sealed class BoosterReceiptsController|public sealed class BoosterReceiptProjectionService' \
  Chummer.Run.AI/Controllers/*.cs Chummer.Run.AI/Services/Booster/*.cs >/dev/null
rg -n 'AddSingleton<IProviderAdapter, BrowserActGatewayAdapter>\(\)|AddSingleton<IProviderAdapter, MarkupGoGatewayAdapter>\(\)|AddSingleton<IProviderAdapter, PeekShotGatewayAdapter>\(\)|AddSingleton<ISkillToolAdapter, SessionProjectionSkillToolAdapter>\(\)|AddSingleton<ISkillToolAdapter, LoreSearchSkillToolAdapter>\(\)|AddSingleton<IGmOpsBoardService, GmOpsBoardService>\(\)|AddSingleton<IFastSignalDetector, FastSignalDetector>\(\)|AddSingleton<IDirectorPolicyEngine, DirectorPolicyEngine>\(\)|AddSingleton<ISpiderCardActionService, SpiderCardActionService>\(\)' \
  Chummer.Run.AI/Program.cs >/dev/null
rg -n 'global using Chummer\.Play\.Contracts\.Docs;' Chummer.Run.AI/GlobalUsings.cs >/dev/null
rg -n 'Use Chummer\.Play\.Contracts\.Docs\.RuntimeDocQuery|Use Chummer\.Play\.Contracts\.Docs\.RuntimeDocResult' Chummer.Run.AI/Compatibility/DocsCompatibilityContracts.cs >/dev/null
rg -n 'public sealed class BrowserActGatewayAdapter|public sealed class MarkupGoGatewayAdapter|public sealed class PeekShotGatewayAdapter' \
  Chummer.Run.AI/Services/Gateway/HttpProviderAdapters.cs >/dev/null
rg -n 'public sealed class PromptRegistry' Chummer.Run.AI/Services/Gateway/PromptRegistry.cs >/dev/null
rg -n 'public sealed class GmOpsBoardService' Chummer.Run.AI/Services/Ops/GmOpsBoardService.cs >/dev/null
rg -n 'public sealed class DirectorPolicyEngine' Chummer.Run.AI/Services/Spider/DirectorPolicyEngine.cs >/dev/null
rg -n 'CreatePrepAssetFromProject|GetProjection|UpdateChecklist|Reveal' Chummer.Run.AI/Controllers/GmOpsBoardController.cs Chummer.Run.AI/Services/Ops/GmOpsBoardService.cs >/dev/null
rg -n 'QueueManual|ExecuteAction|GetOutbox' Chummer.Run.AI/Controllers/SpiderController.cs >/dev/null
rg -n 'RecordAction|ApprovalState|ProjectionFingerprint' Chummer.Run.AI/Services/Spider/DeliveryOutboxService.cs >/dev/null
rg -n 'public sealed class SpiderController' Chummer.Run.AI/Controllers/SpiderController.cs >/dev/null
rg -n 'public sealed class CreativeAssetsController' Chummer.Run.AI/Controllers/CreativeAssetsController.cs >/dev/null
rg -n 'public sealed class InteropController' Chummer.Run.AI/Controllers/InteropController.cs >/dev/null
rg -n 'public sealed class AiDirectorController' Chummer.Run.AI/Controllers/AiDirectorController.cs >/dev/null
rg -n 'PromptTemplates|PreviewPrompt|coach.system|RunEvaluations|SearchLore|QueryPersonaMemory|DraftFromSession' Chummer.Run.AI/Controllers/AiGatewayController.cs Chummer.Run.AI/Services/Gateway/PromptRegistry.cs >/dev/null
rg -n 'public sealed class SpiderDeepIngestionService|PromptLineage|ISessionLedgerService|SessionRuntimeBundleDto' Chummer.Run.AI/Services/Spider/SpiderDeepIngestionService.cs >/dev/null
rg -n 'approval-required|DeliveryOutboxCreateRequest|SpiderActionExecutionState' Chummer.Run.AI/Services/Spider/SpiderCardActionService.cs >/dev/null
rg -n 'GetGatewayPipelineProjection|GetApprovalPipelineProjection|GetMediaPipelineProjection' Chummer.Run.AI/Controllers/PipelineObservabilityController.cs >/dev/null

if [ -d Chummer.Media.Contracts ]; then
  echo "repo-local Chummer.Media.Contracts source must stay deleted after media-factory owner transfer." >&2
  exit 1
fi

if [ -f Chummer.Run.Api/Services/CodexParticipationService.cs ]; then
  echo "legacy CodexParticipationService must stay removed after sponsor-session convergence." >&2
  exit 1
fi

if rg -n 'AddSingleton<CodexParticipationService>' Chummer.Run.Api/Program.cs >/dev/null; then
  echo "Chummer.Run.Api must not register the retired CodexParticipationService." >&2
  exit 1
fi

for retired_contract in \
  Chummer.Run.Contracts/HubRegistryContracts.cs \
  Chummer.Run.Contracts/RegistryContracts.cs \
  Chummer.Run.Contracts/PublicationContracts.cs; do
  if [ -e "$retired_contract" ]; then
    echo "retired local registry/publication contract shadow should not exist: $retired_contract" >&2
    exit 1
  fi
done

if ! grep -En '<HintPath>\.\.\\Chummer\.Play\.Contracts\\bin\\\$\(Configuration\)\\net10\.0\\Chummer\.Play\.Contracts\.dll</HintPath>' \
  Chummer.Run.Contracts/Chummer.Run.Contracts.csproj \
  Chummer.Run.AI/Chummer.Run.AI.csproj >/dev/null; then
  echo "Chummer.Play.Contracts consumers must point at the built canonical contract assembly." >&2
  exit 1
fi

run_contracts_uses_media_contracts_owner() {
  grep -Fq '<ProjectReference Include="$(ChummerMediaContractsProject)"' \
    Chummer.Run.Contracts/Chummer.Run.Contracts.csproj \
    && {
      grep -Fq '$(ChummerMediaFactoryRoot)/src/Chummer.Media.Contracts/Chummer.Media.Contracts.csproj' \
        Chummer.Run.Contracts/Chummer.Run.Contracts.csproj \
      || grep -Fq '$(MSBuildThisFileDirectory)../../../fleet/repos/chummer-media-factory/src/Chummer.Media.Contracts/Chummer.Media.Contracts.csproj' \
        Chummer.Run.Contracts/Chummer.Run.Contracts.csproj
    }
}

run_ai_uses_media_contracts_owner() {
  if grep -Fq '<HintPath>..\..\..\fleet\repos\chummer-media-factory\src\Chummer.Media.Contracts\bin\$(Configuration)\net10.0\Chummer.Media.Contracts.dll</HintPath>' \
    Chummer.Run.AI/Chummer.Run.AI.csproj; then
    return 0
  fi
  grep -Fq '<HintPath>$(ChummerMediaFactoryRoot)\src\Chummer.Media.Contracts\bin\$(Configuration)\net10.0\Chummer.Media.Contracts.dll</HintPath>' \
    Chummer.Run.AI/Chummer.Run.AI.csproj \
    && grep -Fq '<ProjectReference Include="$(ChummerMediaFactoryRoot)\src\Chummer.Media.Contracts\Chummer.Media.Contracts.csproj"' \
      Chummer.Run.AI/Chummer.Run.AI.csproj
}

run_ai_uses_media_runtime_owner() {
  if grep -Fq '<HintPath>..\..\..\fleet\repos\chummer-media-factory\src\Chummer.Media.Factory.Runtime\bin\$(Configuration)\net10.0\Chummer.Media.Factory.Runtime.dll</HintPath>' \
    Chummer.Run.AI/Chummer.Run.AI.csproj; then
    return 0
  fi
  grep -Fq '<HintPath>$(ChummerMediaFactoryRoot)\src\Chummer.Media.Factory.Runtime\bin\$(Configuration)\net10.0\Chummer.Media.Factory.Runtime.dll</HintPath>' \
    Chummer.Run.AI/Chummer.Run.AI.csproj \
    && grep -Fq '<ProjectReference Include="$(ChummerMediaFactoryRoot)\src\Chummer.Media.Factory.Runtime\Chummer.Media.Factory.Runtime.csproj"' \
      Chummer.Run.AI/Chummer.Run.AI.csproj
}

if ! run_contracts_uses_media_contracts_owner || ! run_ai_uses_media_contracts_owner; then
  echo "Chummer.Media.Contracts consumers must point at the owner-repo canonical contract assembly." >&2
  exit 1
fi

if ! run_ai_uses_media_runtime_owner; then
  echo "Chummer.Run.AI must consume media execution through the owner-repo runtime assembly." >&2
  exit 1
fi

if [[ -z "$PYTHON_BIN" ]] || ! "$PYTHON_BIN" scripts/verify_project_reference.py \
  --expected ../chummer-core-engine/Chummer.Contracts/Chummer.Contracts.csproj \
  Chummer.Campaign.Contracts/Chummer.Campaign.Contracts.csproj \
  Chummer.Run.Contracts/Chummer.Run.Contracts.csproj \
  Chummer.Run.Api/Chummer.Run.Api.csproj; then
  echo "run-services bridge projects must project-reference the owner-repo Chummer.Contracts project." >&2
  exit 1
fi

if grep -En '<HintPath>\.\.\\\.\.\\chummer-core-engine\\Chummer\.Contracts\\bin\\\$\(Configuration\)\\net10\.0\\Chummer\.Engine\.Contracts\.dll</HintPath>' \
  Chummer.Campaign.Contracts/Chummer.Campaign.Contracts.csproj \
  Chummer.Run.Contracts/Chummer.Run.Contracts.csproj \
  Chummer.Run.Api/Chummer.Run.Api.csproj >/dev/null; then
  echo "run-services bridge projects must not consume Chummer.Engine.Contracts through a binary HintPath seam." >&2
  exit 1
fi

if [ -d Chummer.Run.Registry ]; then
  echo "Chummer.Run.Registry must not stay source-owned inside chummer6-hub." >&2
  exit 1
fi

if [ -f Chummer.Run.Api/Controllers/PublicationsController.cs ] || [ -f Chummer.Run.Api/Services/PublicationWorkflowService.cs ]; then
  echo "Publication ownership must stay in Chummer.Run.Registry, not Chummer.Run.Api." >&2
  exit 1
fi

if [ ! -f ../chummer-hub-registry/Chummer.Run.Registry/Controllers/PublicationsController.cs ] || [ ! -f ../chummer-hub-registry/Chummer.Run.Registry/Services/PublicationWorkflowService.cs ]; then
  echo "Hub-registry must host publication controller/workflow for boundary readiness." >&2
  exit 1
fi

if ! grep -En '<ProjectReference Include="\.\.\\Chummer\.Hub\.Registry\.Contracts\\Chummer\.Hub\.Registry\.Contracts\.csproj" />' \
  ../chummer-hub-registry/Chummer.Run.Registry/Chummer.Run.Registry.csproj >/dev/null; then
  echo "Hub-registry runtime must consume the owner-repo contract project." >&2
  exit 1
fi

if grep -En '<HintPath>\.\.\\Chummer\.Hub\.Registry\.Contracts\\bin\\\$\(Configuration\)\\net10\.0\\Chummer\.Hub\.Registry\.Contracts\.dll</HintPath>' \
  ../chummer-hub-registry/Chummer.Run.Registry/Chummer.Run.Registry.csproj >/dev/null; then
  echo "Hub-registry runtime must not consume owner contracts through a binary HintPath seam." >&2
  exit 1
fi

if grep -En '<ProjectReference Include="\.\.\\Chummer\.Run\.Contracts\\Chummer\.Run\.Contracts\.csproj" />' \
  ../chummer-hub-registry/Chummer.Run.Registry/Chummer.Run.Registry.csproj >/dev/null; then
  echo "Hub-registry runtime must not source-own registry/publication contracts through local Chummer.Run.Contracts." >&2
  exit 1
fi

for retired_media_service in \
  Chummer.Run.AI/Services/Assets/AssetLifecycleService.cs \
  Chummer.Run.AI/Services/Assets/MediaRenderJobService.cs; do
  if [ -e "$retired_media_service" ]; then
    echo "retired local media execution service should not exist: $retired_media_service" >&2
    exit 1
  fi
done

ORIGIN_EDITION_EVIDENCE_ROOT="${CHUMMER_ORIGIN_EDITION_EVIDENCE_ROOT:-$ROOT_DIR/../.tmp/origin-dossier-fresh-gold}"
ORIGIN_EDITION_ENV_FILE="${CHUMMER_ORIGIN_EDITION_ENV_FILE:-$ROOT_DIR/.env}"
ORIGIN_EDITION_REQUIRE_GOLD="${CHUMMER_ORIGIN_EDITION_REQUIRE_GOLD:-0}"
ORIGIN_EDITION_SKIP_VERIFICATION="${CHUMMER_ORIGIN_EDITION_SKIP_VERIFICATION:-0}"
ORIGIN_EDITION_PROJECT_ID="${CHUMMER_ORIGIN_EDITION_PROJECT_ID:-varga-mira-kestrel}"
ORIGIN_EDITION_NAMESPACE="${CHUMMER_ORIGIN_EDITION_NAMESPACE:-origin.chummer.run/Varga/Mira/Kestrel}"
ORIGIN_PROVIDER_ACCOUNT_REGISTRY_PATH="${CHUMMER_ORIGIN_PROVIDER_ACCOUNT_REGISTRY_PATH:-$ROOT_DIR/.state/origin-provider-accounts.json}"
ORIGIN_EDITION_BASE_URL="${CHUMMER_ORIGIN_EDITION_BASE_URL:-}"
ORIGIN_EDITION_BRANCH="$ORIGIN_EDITION_EVIDENCE_ROOT/$ORIGIN_EDITION_NAMESPACE"
if [ "$ORIGIN_EDITION_SKIP_VERIFICATION" = "1" ] || [ "$ORIGIN_EDITION_SKIP_VERIFICATION" = "true" ]; then
  echo "skip Origin Edition proof-chain verification: explicitly disabled for this verification run"
elif [ -f "$ORIGIN_EDITION_EVIDENCE_ROOT/ORIGIN_DOSSIER_LIVE_IMPORT_REQUEST.generated.json" ]; then
  if [ -z "$ORIGIN_EDITION_BASE_URL" ]; then
    echo "skip Origin Edition proof-chain verification: CHUMMER_ORIGIN_EDITION_BASE_URL is not configured for this host"
  else
  if [ -f "$ORIGIN_PROVIDER_ACCOUNT_REGISTRY_PATH" ]; then
    python3 scripts/verify_origin_provider_account_registry.py \
      --registry "$ORIGIN_PROVIDER_ACCOUNT_REGISTRY_PATH" \
      --output "$ORIGIN_EDITION_EVIDENCE_ROOT/ORIGIN_PROVIDER_ACCOUNT_REGISTRY_VERIFICATION.generated.json" \
      --require-all-roles >/dev/null
  else
    echo "skip Origin provider account registry verification: registry file not present at $ORIGIN_PROVIDER_ACCOUNT_REGISTRY_PATH"
  fi
  python3 scripts/audit_origin_edition_final_bundle.py \
    --root "$ORIGIN_EDITION_EVIDENCE_ROOT" \
    --output "$ORIGIN_EDITION_BRANCH/final-no-fallback-no-sentinel-audit.receipt.json" \
    --project-id "$ORIGIN_EDITION_PROJECT_ID" \
    --namespace "$ORIGIN_EDITION_NAMESPACE" >/dev/null
  python3 scripts/materialize_origin_edition_gold_proof_chain.py \
    --env-file "$ORIGIN_EDITION_ENV_FILE" \
    --evidence-root "$ORIGIN_EDITION_EVIDENCE_ROOT" \
    --allow-blocked >/dev/null
  python3 scripts/materialize_origin_edition_gold_final_verdict.py \
    --evidence-root "$ORIGIN_EDITION_EVIDENCE_ROOT" \
    --allow-blocked >/dev/null
  python3 scripts/verify_origin_dossier_deployed_browser_probe.py \
    --probe "$ORIGIN_EDITION_BRANCH/deployed-chummer-browser-probe.receipt.json" >/dev/null
  python3 scripts/verify_origin_dossier_deployed_operator_handoff.py \
    --handoff "$ORIGIN_EDITION_BRANCH/deployed-operator-handoff.receipt.json" >/dev/null
  python3 scripts/verify_origin_edition_gold_requirement_coverage.py \
    --coverage "$ORIGIN_EDITION_EVIDENCE_ROOT/ORIGIN_EDITION_GOLD_REQUIREMENT_COVERAGE.generated.json" >/dev/null
  ORIGIN_EDITION_VERIFY_ARGS=(
    --proof-chain "$ORIGIN_EDITION_EVIDENCE_ROOT/ORIGIN_EDITION_GOLD_PROOF_CHAIN.generated.json"
    --project-id "$ORIGIN_EDITION_PROJECT_ID"
    --namespace "$ORIGIN_EDITION_NAMESPACE"
  )
  if [ "$ORIGIN_EDITION_REQUIRE_GOLD" = "1" ] || [ "$ORIGIN_EDITION_REQUIRE_GOLD" = "true" ]; then
    ORIGIN_EDITION_VERIFY_ARGS+=(--require-gold)
  fi
  python3 scripts/verify_origin_edition_gold_proof_chain.py \
    "${ORIGIN_EDITION_VERIFY_ARGS[@]}" >/dev/null
  python3 scripts/verify_origin_edition_gold_final_verdict.py \
    --verdict "$ORIGIN_EDITION_EVIDENCE_ROOT/FINAL_ORIGIN_EDITION_GOLD_VERDICT.md" \
    --proof-chain "$ORIGIN_EDITION_EVIDENCE_ROOT/ORIGIN_EDITION_GOLD_PROOF_CHAIN.generated.json" \
    --requirement-coverage "$ORIGIN_EDITION_EVIDENCE_ROOT/ORIGIN_EDITION_GOLD_REQUIREMENT_COVERAGE.generated.json" >/dev/null
  fi
else
  echo "skip Origin Edition proof-chain verification: evidence bundle not present at $ORIGIN_EDITION_EVIDENCE_ROOT"
fi

if [[ "${CHUMMER_SKIP_CLEANROOM_BUILD:-0}" != "1" ]]; then
  bash scripts/ai/build_r1_cleanroom.sh >/dev/null
fi

SDK_VERSION="$(dotnet --version)"
DOTNET_ROOT="$(dirname "$(readlink -f "$(command -v dotnet)")")"
if [[ ! -d "${DOTNET_ROOT}/packs" || ! -d "${DOTNET_ROOT}/sdk/${SDK_VERSION}" ]]; then
  DOTNET_BASE_PATH="$(dotnet --info | awk -F': *' '/Base Path:/{print $2; exit}')"
  if [[ -n "$DOTNET_BASE_PATH" ]]; then
    DOTNET_ROOT="$(dirname "$(dirname "${DOTNET_BASE_PATH%/}")")"
  fi
fi
CSC_DLL="${DOTNET_ROOT}/sdk/${SDK_VERSION}/Roslyn/bincore/csc.dll"
NETCORE_REF_DIR="$(find "${DOTNET_ROOT}/packs/Microsoft.NETCore.App.Ref" -path '*/ref/net10.0' -type d | sort | tail -n 1)"
ASPNET_REF_DIR="$(find "${DOTNET_ROOT}/packs/Microsoft.AspNetCore.App.Ref" -path '*/ref/net10.0' -type d | sort | tail -n 1)"
NETCORE_RUNTIME_VERSION="$(dotnet --list-runtimes | awk '/Microsoft.NETCore.App 10\./ { print $2; exit }')"
ASPNET_RUNTIME_VERSION="$(dotnet --list-runtimes | awk '/Microsoft.AspNetCore.App 10\./ { print $2; exit }')"
OUT_DLL="${TMP_DIR}/RunServicesVerification.dll"
RSP_FILE="${TMP_DIR}/RunServicesVerification.rsp"

if [[ ! -f "$CSC_DLL" || -z "$NETCORE_REF_DIR" || -z "$ASPNET_REF_DIR" || -z "$NETCORE_RUNTIME_VERSION" || -z "$ASPNET_RUNTIME_VERSION" ]]; then
  echo "unable to resolve installed .NET 10 SDK/reference/runtime locations" >&2
  exit 1
fi

copy_artifact "Chummer.Play.Contracts" "Chummer.Play.Contracts.dll" \
  "Chummer.Play.Contracts/bin/Debug/net10.0/Chummer.Play.Contracts.dll" \
  "${TEST_BIN}/Chummer.Play.Contracts.dll"
copy_artifact "Chummer.Campaign.Contracts" "Chummer.Campaign.Contracts.dll" \
  "Chummer.Campaign.Contracts/bin/Debug/net10.0/Chummer.Campaign.Contracts.dll" \
  "${TEST_BIN}/Chummer.Campaign.Contracts.dll"
copy_artifact "Chummer.Control.Contracts" "Chummer.Control.Contracts.dll" \
  "Chummer.Control.Contracts/bin/Debug/net10.0/Chummer.Control.Contracts.dll" \
  "${TEST_BIN}/Chummer.Control.Contracts.dll"
copy_artifact "Chummer.Engine.Contracts" "Chummer.Engine.Contracts.dll" \
  "../chummer-core-engine/Chummer.Contracts/bin/Debug/net10.0/Chummer.Engine.Contracts.dll" \
  "${TEST_BIN}/Chummer.Engine.Contracts.dll"
copy_artifact "Chummer.Hub.Registry.Contracts" "Chummer.Hub.Registry.Contracts.dll" \
  "../chummer-hub-registry/Chummer.Hub.Registry.Contracts/bin/Debug/net10.0/Chummer.Hub.Registry.Contracts.dll" \
  "${TEST_BIN}/Chummer.Hub.Registry.Contracts.dll"
copy_artifact "Chummer.Run.Registry" "Chummer.Run.Registry.dll" \
  "../chummer-hub-registry/Chummer.Run.Registry/bin/Debug/net10.0/Chummer.Run.Registry.dll" \
  "${TEST_BIN}/Chummer.Run.Registry.dll"
copy_artifact "Chummer.Media.Contracts" "Chummer.Media.Contracts.dll" \
  "../../fleet/repos/chummer-media-factory/src/Chummer.Media.Contracts/bin/Debug/net10.0/Chummer.Media.Contracts.dll" \
  "${TEST_BIN}/Chummer.Media.Contracts.dll"
copy_artifact "Chummer.Media.Factory.Runtime" "Chummer.Media.Factory.Runtime.dll" \
  "../../fleet/repos/chummer-media-factory/src/Chummer.Media.Factory.Runtime/bin/Debug/net10.0/Chummer.Media.Factory.Runtime.dll" \
  "${TEST_BIN}/Chummer.Media.Factory.Runtime.dll"
copy_artifact "Chummer.Run.Api" "Chummer.Run.Api.dll" \
  "Chummer.Run.Api/bin/Debug/net10.0/Chummer.Run.Api.dll" \
  "${TEST_BIN}/Chummer.Run.Api.dll"
copy_artifact "YamlDotNet" "YamlDotNet.dll" \
  "Chummer.Run.Api/bin/Debug/net10.0/YamlDotNet.dll" \
  "${TEST_BIN}/YamlDotNet.dll"
copy_artifact "Chummer.Run.Identity" "Chummer.Run.Identity.dll" \
  "Chummer.Run.Identity/bin/Debug/net10.0/Chummer.Run.Identity.dll" \
  "${TEST_BIN}/Chummer.Run.Identity.dll"
copy_artifact "Chummer.Run.AI" "Chummer.Run.AI.dll" \
  "Chummer.Run.AI/bin/Debug/net10.0/Chummer.Run.AI.dll" \
  "${TEST_BIN}/Chummer.Run.AI.dll"
copy_artifact "Chummer.Run.Contracts" "Chummer.Run.Contracts.dll" \
  "Chummer.Run.Contracts/bin/Debug/net10.0/Chummer.Run.Contracts.dll" \
  "${TEST_BIN}/Chummer.Run.Contracts.dll"

{
  echo "-nologo"
  echo "-langversion:preview"
  echo "-nullable:enable"
  echo "-target:exe"
  echo "-out:${OUT_DLL}"
  echo "-nowarn:612,618"
  for dll in "$NETCORE_REF_DIR"/*.dll; do
    echo "-r:${dll}"
  done
  for dll in "$ASPNET_REF_DIR"/*.dll; do
    echo "-r:${dll}"
  done
  for dll in "$TMP_DIR"/Chummer*.dll; do
    echo "-r:${dll}"
  done
  echo "-r:${TMP_DIR}/YamlDotNet.dll"
  echo "${ROOT_DIR}/../chummer-hub-registry/Chummer.Run.Registry/GlobalUsings.RegistryContracts.cs"
  find "${ROOT_DIR}/tests/RunServicesVerification" -maxdepth 1 -name '*.cs' | sort
} > "$RSP_FILE"

cat > "${TMP_DIR}/RunServicesVerification.runtimeconfig.json" <<EOF
{
  "runtimeOptions": {
    "tfm": "net10.0",
    "frameworks": [
      {
        "name": "Microsoft.NETCore.App",
        "version": "${NETCORE_RUNTIME_VERSION}"
      },
      {
        "name": "Microsoft.AspNetCore.App",
        "version": "${ASPNET_RUNTIME_VERSION}"
      }
    ]
  }
}
EOF

dotnet "$CSC_DLL" @"$RSP_FILE"
dotnet "$OUT_DLL"

if [[ "${CHUMMER_HUB_PLAYWRIGHT:-0}" == "1" ]]; then
  bash scripts/e2e-hub.sh
fi

if [[ -n "$PYTHON_BIN" ]]; then
  "$PYTHON_BIN" scripts/materialize_campaign_os_local_proof.py >/dev/null
else
  echo "python runtime is required to materialize campaign OS local proof." >&2
  exit 1
fi
