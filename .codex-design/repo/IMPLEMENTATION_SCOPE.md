# Run-services implementation scope

## Mission

`chummer.run-services` owns hosted orchestration: identity, session relay, Spider, Coach, approvals, play API aggregation, delivery, memory, and service-to-service policy.

## Owns

* identity and campaign/session access control
* play API aggregation
* relay and hosted session coordination
* approvals and reviewable actions
* Coach / Spider / Director orchestration
* memory, recap, and delivery workflows
* service policy and external-service coordination
* run-service contract canon

## Must not own long-term

* registry persistence internals after `chummer-hub-registry`
* media render internals after `chummer-media-factory`
* duplicate engine event semantics
* canonical rules math

## Current split focus

* publish and stabilize `Chummer.Play.Contracts`
* keep `Chummer.Run.Contracts` focused on orchestration concerns
* dedupe any semantic session DTO overlap with engine canon
* route registry work through `chummer-hub-registry`
* route render/media execution through `chummer-media-factory`
* shrink root-level legacy clutter and stale README architecture claims

## Milestone spine

* R0 shrink-to-boundary reset
* R1 package canon
* R2 identity/campaign core
* R3 play APIs and relay
* R4 skill runtime
* R5 Spider/Director/memory
* R6 orchestration-only registry/media mode
* R7 notifications/docs/delivery
* R8 resilience/compliance
* R9 finished hosted orchestration

## Worker rule

If it is about hosted orchestration and policy, it belongs here.
If it is about canonical mechanics, registry persistence, or render execution, it does not.


## External integrations scope

`chummer.run-services` is the orchestration owner for all non-render external-tool integrations.

### Owns

* `IReasoningProviderRoute`
* `IApprovalBridge`
* `IDocumentationBridge`
* `ISurveyBridge`
* `IAutomationBridge`
* `IEvalLabAdapter`
* `IResearchAssistAdapter`
* prompt/style/persona toolchain orchestration
* provider-route receipts for non-media operations

### Initial vendor mapping

* 1min.AI - fallback reasoning and multimodal route
* AI Magicx - structured AI route
* Prompting Systems - prompt/style authoring support
* ChatPlayground AI - eval lab only
* BrowserAct - no-API automation fallback, off critical path
* ApproveThis - approval bridge
* Documentation.AI - docs/help bridge
* MetaSurvey - survey bridge
* Teable - curated ops projection bridge
* ApiX-Drive - low-risk automation bridge
* Paperguide - cited research assist
* Vizologi - design/program strategy support only

### Must not own

* document/image/video rendering internals
* media binary lifecycle
* direct provider use from clients
* canonical rules math
* registry truth

### Required design rules

* every provider route emits a Chummer receipt
* every provider route is kill-switchable
* every provider route degrades gracefully
* every provider route preserves Chummer as system of record

