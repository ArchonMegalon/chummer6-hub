# Lead-dev feedback: run-services contract dedupe

Public audit status: `red/yellow`

Main issues:

* play and run packages still duplicate semantic relay/runtime DTO families
* `MediaContracts.cs` still mixes play-surface and media ownership concerns
* README still narrates the old multi-head runtime
* the repo root is still too wide

Required next steps:

1. Pick one semantic owner for session event and runtime bundle meaning.
2. Leave transport/projection wrappers in play/run contracts only after engine semantic ownership is frozen.
3. Untangle media execution contracts from hosted orchestration contracts.
4. Rewrite the README to the current split architecture.
