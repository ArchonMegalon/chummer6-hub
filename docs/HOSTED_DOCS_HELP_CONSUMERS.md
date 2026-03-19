# Hosted Docs And Help Consumers

Purpose: keep the hosted docs/help lane bounded as a consumer surface for canonical contracts and grounded retrieval, not a second system of record.

## Canonical contract owners

- docs query/result vocabulary: `Chummer.Play.Contracts.Docs.RuntimeDocQuery`, `Chummer.Play.Contracts.Docs.RuntimeDocResult`
- prompt/help vocabulary: `Chummer.Play.Contracts.Gateway.PromptTemplate`, `PromptRenderRequest`, `PromptRenderResult`
- hosted repo-local docs compatibility records remain compatibility-only in `Chummer.Run.AI/Compatibility/DocsCompatibilityContracts.cs`

## Hosted consumer surfaces

- prompt catalog and preview: `AiGatewayController.PromptTemplates`, `AiGatewayController.UpsertPrompt`, `AiGatewayController.PreviewPrompt`
- grounded help and research lookups: `AiGatewayController.SearchLore`, `AiGatewayController.QueryPersonaMemory`, `AiGatewayController.DraftFromSession`
- prompt/help implementation seams: `PromptRegistry`, `LoreService`, `PersonaMemoryService`, `SessionMemoryService`

## Consumer rule

- the hosted repo may scaffold help, prompt, lore, and draft-first guidance flows, but it does not own canonical docs truth
- docs/help views must consume `Chummer.Play.Contracts.Docs` and grounded runtime/lore/session surfaces instead of minting a second docs contract family
- compatibility wrappers in `Chummer.Run.AI/Compatibility/DocsCompatibilityContracts.cs` must stay obsolete and non-authoritative
- the hosted repo must not persist a parallel help-state store that outruns product canon or registry-owned read models

## Verification path

- `tests/RunServicesVerification/HubExtractionReadinessVerification.cs` asserts the docs/help consumer rule, canonical contract usage, and compatibility-only posture
- `bash scripts/ai/run_services_verification.sh` enforces that this document and the referenced code seams remain present

## Current gap

- external docs/help SaaS adapters are still absent; current proof only covers the grounded hosted consumer plane
- richer end-user help UX is still product work and must stay downstream of these consumer rules
