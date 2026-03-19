# Assistant Plane Authority

Purpose: keep `WL-235` explicit.

This document maps the live hosted assistant plane so `Coach`, `Spider`, and `Director` are governed, grounded, and reviewable by construction instead of by reputation.

## Coach

Coach is a governed route family inside the hosted AI gateway rather than a separate service root.

### Canonical owner surface

- routing and route audit: `ProviderRouting`, `AiGatewayService`
- prompt and draft-first posture: `PromptRegistry` (`coach.system`)
- public entry surface: `AiGatewayController`
- budget and evaluation review loops: `AiBudgetService`, `EvaluationStore`

### Grounding surfaces

- `LoreService`
- `PersonaMemoryService`
- `SessionMemoryService`
- prompt lineage and runtime grounding via `PromptRegistry`

### Governance and reviewability

- route budgets and provider-routing decisions
- evaluation runs and route audits
- pipeline observability through `PipelineObservabilityController`

## Spider

Spider is the tactical observation and escalation head.

### Canonical owner surface

- ingress and action surface: `SpiderController`
- fast signal gate: `FastSignalDetector`
- deeper governed analysis: `SpiderDeepIngestionService`
- policy layer: `DirectorPolicyEngine`
- delivery rail: `DeliveryOutboxService`
- interruption rail: `InterruptionBudgetService`
- approval-aware action loop: `SpiderCardActionService`
- operator review surface: `GmOpsBoardService`

### Grounding surfaces

- `SessionLedgerService`
- `SessionRuntimeBundleService`
- `PromptRegistry` (`spider.tactical-card`)
- `AiGatewayService` with prompt lineage and evidence pointers

### Governance and reviewability

- escalation threshold before deep analysis
- runtime-bundle and ledger grounding before delivery
- interruption budgets before delivery
- approval-required action handling in `SpiderCardActionService`
- ops-board and pipeline projection visibility

## Director

Director is the policy and intake head for higher-level observation and control.

### Canonical owner surface

- intake endpoint: `AiDirectorController`
- decision layer: `DirectorPolicyEngine`
- downstream execution bridge: `SpiderController`

### Governance and reviewability

- observation intake is accepted, not silently executed
- policy decisions are derived from Spider grounding and deep analysis
- downstream effects still flow through Spider delivery, action, and ops-board surfaces

## Authority rules

- client repos must not source-own Coach, Spider, or Director orchestration logic
- client repos may consume projections, prompts, cards, and receipts, but not redefine assistant governance
- grounding for assistant outputs must flow through hosted route audits, prompt lineage, and canonical session/runtime services
- approval-aware follow-up actions must stay in hosted delivery/action services rather than client-local shortcuts

## Current gap

`WL-235` stays open until the hosted verification path proves these surfaces continuously and future assistant features stay on the same governed rails.

Current honest state:

- Coach route governance and reviewability are explicit
- Spider escalation, grounding, and approval-aware follow-up are explicit
- Director intake and policy are explicit
- richer product maturity can still deepen, but the live authority surface is now named
