# Codex Instructions — run-services

## Read first
1. instructions.md
2. .agent-memory.md
3. AGENT_MEMORY.md
4. chummer-run-services.design.v2.md
5. AGENTS.md if present
6. audit.md if present

## Scope
Own:
- API route groups
- auth/identity/roles
- Hub registry and publication services
- session relay / runtime bundle delivery
- AI gateway / provider routing
- retrieval / lore / GM Spider orchestration
- moderation / publication workflow
- generated media job orchestration

Do not own:
- GPL-derived mechanics code
- Shadowrun math
- legacy XML parsing
- engine internals
- UI rendering concerns

## Hard boundaries
- Treat game/rules payloads as opaque contract-shaped data
- Do not recreate mechanics or parsing here
- Keep this repository clean-room

## Quality rules
- Session state must be event/log based, not overwrite based
- Generated media must be asynchronous, cached, and TTL-aware
- Installed/used Hub artifacts must be immutable or delisted, not hard-deleted
- Persona retrieval must be selective/RAG-based

## Queue
1. Clean-room scaffold and compile recovery
2. Contracts-first API hardening
3. Identity / registry / publication foundation
4. Session relay / runtime bundle foundation
5. AI gateway / Spider foundation
6. Generated asset orchestration

## Execution style
Inspect current repo state first.
Do not repeat completed work.
Continue silently until the queue is exhausted or you are truly blocked.
