#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/_env.sh"

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT_DIR"

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

if [ ! -f Chummer.Play.Contracts/Chummer.Play.Contracts.csproj ]; then
  echo "Chummer.Play.Contracts project is missing." >&2
  exit 1
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

if ! grep -En '<HintPath>\.\.\\\.\.\\\.\.\\fleet\\repos\\chummer-media-factory\\src\\Chummer\.Media\.Contracts\\bin\\\$\(Configuration\)\\net10\.0\\Chummer\.Media\.Contracts\.dll</HintPath>' \
  Chummer.Run.Contracts/Chummer.Run.Contracts.csproj \
  Chummer.Run.AI/Chummer.Run.AI.csproj >/dev/null; then
  echo "Chummer.Media.Contracts consumers must point at the owner-repo canonical contract assembly." >&2
  exit 1
fi

if ! grep -En '<HintPath>\.\.\\\.\.\\\.\.\\fleet\\repos\\chummer-media-factory\\src\\Chummer\.Media\.Factory\.Runtime\\bin\\\$\(Configuration\)\\net10\.0\\Chummer\.Media\.Factory\.Runtime\.dll</HintPath>' \
  Chummer.Run.AI/Chummer.Run.AI.csproj >/dev/null; then
  echo "Chummer.Run.AI must consume media execution through the owner-repo runtime assembly." >&2
  exit 1
fi

for project_file in \
  Chummer.Campaign.Contracts/Chummer.Campaign.Contracts.csproj \
  Chummer.Run.Contracts/Chummer.Run.Contracts.csproj \
  Chummer.Run.Api/Chummer.Run.Api.csproj; do
  if ! grep -En '<ProjectReference Include="\.\.\\\.\.\\chummer-core-engine\\Chummer\.Contracts\\Chummer\.Contracts\.csproj" />' \
    "$project_file" >/dev/null; then
    echo "${project_file} must project-reference the owner-repo Chummer.Contracts project." >&2
    exit 1
  fi
done

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

bash scripts/ai/build_r1_cleanroom.sh >/dev/null

SDK_VERSION="$(dotnet --version)"
DOTNET_ROOT="$(dirname "$(readlink -f "$(command -v dotnet)")")"
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

cp Chummer.Play.Contracts/bin/Debug/net10.0/Chummer.Play.Contracts.dll "$TMP_DIR/"
cp Chummer.Campaign.Contracts/bin/Debug/net10.0/Chummer.Campaign.Contracts.dll "$TMP_DIR/"
cp Chummer.Control.Contracts/bin/Debug/net10.0/Chummer.Control.Contracts.dll "$TMP_DIR/"
cp ../chummer-core-engine/Chummer.Contracts/bin/Debug/net10.0/Chummer.Engine.Contracts.dll "$TMP_DIR/"
cp ../chummer-hub-registry/Chummer.Hub.Registry.Contracts/bin/Debug/net10.0/Chummer.Hub.Registry.Contracts.dll "$TMP_DIR/"
cp ../chummer-hub-registry/Chummer.Run.Registry/bin/Debug/net10.0/Chummer.Run.Registry.dll "$TMP_DIR/"
cp ../../fleet/repos/chummer-media-factory/src/Chummer.Media.Contracts/bin/Debug/net10.0/Chummer.Media.Contracts.dll "$TMP_DIR/"
cp ../../fleet/repos/chummer-media-factory/src/Chummer.Media.Factory.Runtime/bin/Debug/net10.0/Chummer.Media.Factory.Runtime.dll "$TMP_DIR/"
cp Chummer.Run.Api/bin/Debug/net10.0/Chummer.Run.Api.dll "$TMP_DIR/"
cp Chummer.Run.Api/bin/Debug/net10.0/YamlDotNet.dll "$TMP_DIR/"
cp Chummer.Run.Identity/bin/Debug/net10.0/Chummer.Run.Identity.dll "$TMP_DIR/"
cp Chummer.Run.AI/bin/Debug/net10.0/Chummer.Run.AI.dll "$TMP_DIR/"
cp Chummer.Run.Contracts/bin/Debug/net10.0/Chummer.Run.Contracts.dll "$TMP_DIR/"

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
