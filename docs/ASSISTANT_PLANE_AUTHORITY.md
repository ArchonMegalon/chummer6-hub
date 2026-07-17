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

## HTTP authorization boundary

`Chummer.Run.AI` uses an exact public-route allowlist. Every controller route, including reads, must carry `Authorization: Bearer <token>` before controller routing or model binding runs. `OPTIONS` remains anonymous as a transport preflight and does not return controller data.

- `CHUMMER_AI_INTERNAL_API_TOKEN` is the dedicated credential.
- `FLEET_INTERNAL_API_TOKEN` is accepted only as a compatibility fallback when the dedicated credential is blank or absent.
- When neither credential is configured, protected routes fail closed with `503`; they never become anonymous.
- Missing, malformed, or incorrect bearer credentials return `401` without echoing credential material.

### Route classification

| Access | Routes | Returned data |
| --- | --- | --- |
| Anonymous | `GET`/`HEAD /api/health` | Static service name and health state |
| Anonymous | `GET`/`HEAD /api/v1/ai/capabilities` | Static API version, availability, and protected-route auth posture |
| Anonymous transport | `OPTIONS *` | No controller data |
| Internal | `/api/v1/ai/status`, `/prompts`, `/budget/*`, `/skills/adapters`, `/conversations/*`, `/evaluations*` | Provider, prompt, budget, conversation, and evaluation detail |
| Internal | `/api/v1/ai/support/*`, `/creative/*`, `/session/*`, `/spider/*`, `/gm-ops/*` | Crash, asset, campaign, session, message, and GM data |
| Internal | `/api/v1/ai/pipeline/*`, `/booster/*`, and every other or unknown route | Operational projections and tenant/group data |

The two anonymous responses are deliberately static and contain no provider configuration, prompt content, identifiers, queues, audit records, or tenant/session state. Exact matching (apart from a trailing slash and path casing) prevents a public path prefix from opening deeper routes.

### Compatibility impact

- Existing anonymous callers of `GET /api/v1/ai/status` and all other AI controller reads must now send the same bearer token already required for mutations.
- Readiness probes should move to `GET /api/health`; public feature discovery should use `GET /api/v1/ai/capabilities`.
- Unknown GET routes now return `401` when a token is configured or `503` when no token is configured before routing can return `404`.
- Booster projection reads still retain their controller-level legacy guard when invoked outside the normal host pipeline. In the hosted pipeline, successful common AI authorization satisfies that secondary guard, so callers do not need two unrelated bearer credentials.
- This is an internal service boundary, not end-user identity or tenant authorization. If direct end-user access is introduced later, subject and tenant checks must be added rather than treating the shared internal token as user authorization.

## Current gap

`WL-235` stays open until the hosted verification path proves these surfaces continuously and future assistant features stay on the same governed rails.

Current honest state:

- Coach route governance and reviewability are explicit
- Spider escalation, grounding, and approval-aware follow-up are explicit
- Director intake and policy are explicit
- richer product maturity can still deepen, but the live authority surface is now named
