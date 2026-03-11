# Vision

## North star

Chummer becomes a complete digital Shadowrun operating environment built on hard architectural boundaries.

The finished product is:

* a deterministic character and rules engine
* a workbench for building, inspecting, comparing, publishing, and moderating
* a session OS for players and GMs across desktop, web, and mobile
* a hosted campaign and assistant orchestration plane
* a reusable registry/publication ecosystem
* a bounded media studio for artifacts, portraits, and video
* a fully explainable system where derived values can always be grounded

## Product promises

### 1. Engine truth is deterministic

No repo other than `chummer-core-engine` computes canonical rules math.

### 2. Explain Everywhere is real

Every important derived value, legality outcome, or state transition can be explained with structured provenance.

### 3. Workbench and play are different products

`chummer-presentation` is the builder/workbench/admin surface.
`chummer-play` is the live session shell.

### 4. Hosted orchestration is not rules truth

`chummer.run-services` coordinates identity, relay, memory, approvals, and assistants, but it does not own duplicate mechanics.

### 5. Shared UI is a package, not a rumor

`chummer-ui-kit` becomes the only reusable cross-head UI boundary.

### 6. Registry and media are real services

Publication/catalog concerns and render/media concerns do not remain hidden inside run-services forever.

### 7. Legacy is an oracle, not a shadow product

`chummer5a` exists to support migration and regression confidence, not to compete with vNext architecture.

## Finished-state experience

### Player

A player can build, sync, inspect, and play from a modern shell that works across devices and survives intermittent connectivity.

### GM

A GM can run live sessions, inspect grounded state, receive Spider/Coach support, review generated assets, and manage play flow without juggling unrelated tools.

### Creator / publisher

A creator can prepare artifacts, publish content, manage installs, review compatibility, and work through governed publication flows.

### Operator / maintainer

A maintainer can tell:

* which repo owns what
* which package owns which DTO
* which milestone is blocking release
* which mirror is stale
* which design change became canonical and why

## Anti-vision

Chummer is not:

* one repo pretending to be many
* a rules engine hidden in UI code
* an AI-first product with fuzzy authority
* a design system copied into each frontend
* a media generator welded directly to play or workbench
* a registry buried inside orchestration services
* a design repo that only contains slogans
