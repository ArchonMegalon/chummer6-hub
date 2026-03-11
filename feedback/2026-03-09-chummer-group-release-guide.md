# Group Feedback: Chummer Release Path

Date: 2026-03-09
Applies to: `core`, `ui`, `hub`

This is shared program guidance for the whole Chummer group, not only this repo.

## Executive audit

The design docs are ahead of the code layout.

Publicly, the three Chummer repos still look more like parallelized slices of one large codebase than sharply enforced product boundaries:

- repo roots still overlap heavily
- `WORKLIST.md` and `AGENTS.md` are still effectively mirrored across repos
- shared contract source still exists in more than one repo
- test ownership is still smeared across repo boundaries

The intended architecture is still the right one:

- `core-engine` owns deterministic mechanics, RuntimeLock, Explain traces, Build Lab primitives, and reducer-style session application
- `presentation` owns desktop/web/mobile rendering, local-first UI, Explain visualization, and GM Board rendering
- `run-services` owns Hub, auth, relay, memory, AI orchestration, and creative or media workflows

The current trees and public test ownership are not enforcing that separation yet.

## Major blockers

### 1. Contract drift is already real

`Chummer.Contracts` exists in both `core-engine` and `presentation`, with different folder sets.

There is also a concrete divergence in `AiExplainContracts`:

- the core copy is localization-safe and provenance or evidence rich
- the presentation copy is simplified into rendered strings and drops part of the structured grounding model

### 2. Authority leakage remains inside core

`core-engine` still carries AI, media, Hub, and publication-related contract families that belong in hosted services according to the repo boundary docs.

### 3. Session and event truth is not canonical yet

Core already defines reducer-oriented session and event shapes with sequence, actor or device metadata, and overlay projections, while `run-services` defines a different session overlay or event shape in `AIPlatformContracts.cs`.

Until that becomes one canonical envelope, reducer truth, relay truth, and client cache truth can drift.

### 4. Test ownership is still backwards

`core-engine` and `presentation` still carry broad AI, Hub, and publication-style tests, while `run-services` has a much thinner smoke-style public test surface. That is the opposite of the intended end-state.

## Immediate required actions

1. One source of truth for shared contracts.
   `presentation` should stop carrying source copies of shared DTOs. `core-engine` should publish the authoritative engine or shared package, and `run-services` should publish the authoritative hosted-services package.

2. Move hosted-only DTO families out of `core-engine`.
   Hub, publication, media, approval, transcription, provider-routing, and similar hosted concerns belong in `Chummer.Run.Contracts`, not in engine-shared source.

3. Canonicalize Explain on the richer core shape.
   The correct direction is the key or params or provenance or evidence or trace model from core, with presentation doing localization and rendering.

4. Canonicalize session envelopes.
   There should be one event envelope and one projection family used by reducer, relay, sync, Spider, and client cache.

5. Break up `AIPlatformContracts.cs`.
   Split it into hosted domain families such as gateway, coach, media jobs, session memory, lore, docs, and overlay or relay.

6. Use `executive-assistant` as the pattern for governed skills, approvals, and memory candidates.
   Use it as a runtime architecture reference, not as a freeform chat template.

## Contract canon expectations

- `core-engine` publishes the authoritative engine or shared contract package
- `run-services` publishes the authoritative hosted-service contract package
- `presentation` consumes packages and does not keep duplicated shared contract source
- session envelopes carry sequence, causation or idempotency, actor or device identity, scene revision, runtime or pack provenance, and explicit schema versioning
- Explain remains localization-safe and evidence-bearing across repo boundaries

## Milestone spine

- M0: contract canon and repo purification
- M1: deterministic runtime kernel
- M2: Explain Everywhere plus browse or build surfaces
- M3: Session OS with local-first play and relay convergence
- M4: Hub registry, publication, immutable artifacts
- M5: Spider, GM Board, DeliveryOutbox
- M6: governed GM Companion skill runtime
- M7: memory, lore, canonization, NPC persona
- M8: creative asset factory
- M9: player shell, exchange package, interop
- M10: hardening, security, ops, observability
- M11: release candidate and v1.0 launch

## Program instruction

Treat Milestone 0 as a product milestone, not deferred cleanup.

The current repo state is still close enough to the intended architecture that clean convergence is possible, but only if contract canon and authority boundaries become the first product milestone rather than later cleanup.
