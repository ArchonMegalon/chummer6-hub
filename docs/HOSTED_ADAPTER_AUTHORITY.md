# Hosted Adapter Authority

Purpose: keep `WL-233` explicit.

This document inventories the live orchestration-side external adapters that are still owned by `chummer6-hub` and makes the ownership rule verifier-checkable.

## Current owner surface

- runtime registration root: `Chummer.Run.AI/Program.cs`
- provider adapter implementations: `Chummer.Run.AI/Services/Gateway/HttpProviderAdapters.cs`
- governed skill adapter implementations: `Chummer.Run.AI/Services/Gateway/GovernedSkillRuntimeService.cs`
- route audit / receipt-bearing surface: `Chummer.Run.AI/Services/Gateway/AiGatewayService.cs`
- public adapter discovery surface: `Chummer.Run.AI/Controllers/AiGatewayController.cs`

## Live adapter families

| Family | Hub-owned implementation | Switchability / kill switch | Receipt-bearing surface | Notes |
|---|---|---|---|---|
| structured/text provider routing | `AiMagicx`, `OneMinAi`, `ChatPlayground`, `PromptingSystems` through `IProviderAdapter` registration in `Program.cs` | `AiGateway:Providers:*:Enabled` | `AiGatewayService` route audits and pipeline projection | These remain orchestration-side adapters, not client-owned provider calls. |
| browser extraction | `BrowserActGatewayAdapter` | `AiGateway:Providers:BrowserAct:Enabled` | `AiGatewayService` route audits | External extraction stays hub-owned. |
| screenshot capture | `PeekShotGatewayAdapter` | `AiGateway:Providers:PeekShot:Enabled` | `AiGatewayService` route audits | Preview/screenshot adapter stays hub-owned unless a future owner transfer says otherwise. |
| document/pdf conversion | `MarkupGoGatewayAdapter` | `AiGateway:Providers:MarkupGo:Enabled` | `AiGatewayService` route audits | Orchestration-side document conversion remains hub-owned until a future owner transfer says otherwise. |
| governed skill execution | `SessionProjectionSkillToolAdapter`, `LoreSearchSkillToolAdapter` | adapter registration + approval gating in `GovernedSkillRuntimeService` | governed skill execution result + governance flags | Tool adapter ownership stays in the hosted orchestrator. |

## Adjacent hosted families that still belong to this repo

These are not all third-party provider adapters, but they are part of the same orchestration-side authority plane that `C1b` is trying to make explicit.

| Family | Canonical hosted owner surface | Why it belongs here |
|---|---|---|
| prompt/help scaffolding | `PromptRegistry`, `AiGatewayController` | Prompt templates and grounded help-style route scaffolding are hosted consumers of canonical contracts, not client-owned truth. |
| research grounding | `LoreSearchSkillToolAdapter`, `ILoreService`, `AiGatewayController` | Retrieval and lore search remain governed hosted execution paths. |
| approval-gated asset automation | `CreativeAssetsController`, `IPortraitForgeService`, `IPacketFactoryService`, `INewsNetworkService`, `IRouteCinemaService`, `IShadowfeedService`, `INpcMessageVideoService` | Approval-aware creative automation and delivery orchestration stay in the hosted repo. |
| operator prep and reveal control | `GmOpsBoardService`, `GmOpsBoardController` | Prep assets, reveal surfaces, and operator projections are hosted orchestration consumers of canonical contracts. |
| tactical automation | `SpiderController`, `IFastSignalDetector`, `IDirectorPolicyEngine`, `ISpiderCardActionService` | Observation, escalation, and interruption-budgeted tactical delivery remain hosted automation lanes. |
| interop/export bridge | `InteropController`, `IInteropExportService` | Export/import and round-trip packaging stay hosted consumer bridges instead of client-owned persistence logic. |
| director intake | `AiDirectorController` | Director observations are accepted and queued through the hosted orchestration surface. |

## Currently absent live families

- survey adapters are not live yet
- dedicated feedback SaaS adapters are not live yet
- external docs/help SaaS adapters are not live yet beyond hosted prompt/lore/interop consumer surfaces

## Authority rules

- Client repos must not define hub-owned provider adapter classes such as `BrowserActGatewayAdapter`, `MarkupGoGatewayAdapter`, or `PeekShotGatewayAdapter`.
- Client repos must not define hosted governed-skill adapter classes such as `SessionProjectionSkillToolAdapter` or `LoreSearchSkillToolAdapter`.
- Provider enable/disable controls stay in hub runtime configuration rather than client-side provider routing code.
- The public discovery and audit path for these adapters stays under the hosted AI gateway surface.
- Approval-gated automation surfaces such as `CreativeAssetsController`, `GmOpsBoardService`, `SpiderController`, `DirectorPolicyEngine`, and `InteropController` remain hosted orchestration consumers rather than second system-of-record owners in client repos.

## Current gap

`WL-233` is only closed when this ownership remains true and the remaining open work no longer needs new client-side adapter authority exceptions.

The previously traced leakage behind `WL-D020` was core-side remote provider transport and credential routing in:

- `Chummer.Infrastructure/DependencyInjection/ServiceCollectionExtensions.cs`
- `Chummer.Infrastructure/AI/HttpAiProviderTransportClient.cs`
- `Chummer.Infrastructure/AI/EnvironmentAiProviderCredentialCatalog.cs`
- `Chummer.Infrastructure/AI/EnvironmentAiProviderTransportOptionsCatalog.cs`
- `Chummer.Application/AI/RemoteHttpAiProvider.cs`

Those files do not duplicate hub-owned adapter classes. As of 2026-03-19, the core repo now fences that path behind an explicit compatibility-only hook instead of wiring it into the active headless-core boundary by default.

That closes the client/provider leakage part of this lane.

The remaining `WL-233` work is narrower:

- keep the hosted inventory current as additional approval/docs/help/survey/research/automation bridges become real
- continue proving that future survey/feedback/docs-help integrations land here as bounded hosted consumers instead of leaking into client repos
