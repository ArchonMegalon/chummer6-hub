# Designer Feedback Split: run-services / Hub

Source: 2026-03-08 Chummer designer market scan. Distilled direction: community demand is ops-first, not AI-first. The product must reduce Shadowrun bookkeeping, reduce duplicate entry, support cross-device play, explain rules with provenance, preserve house-rule flexibility, and avoid hosted lock-in.

## Your part
run-services should become the shared session-operations layer for Hub, not an assistant-chat shell.

Prioritize:
- the live session ledger, projections, and collaboration surface that make bookkeeping lighter at the table
- GM Ops Board / Spider Feed as tactical cards and alerts, not a babbling chat sidebar
- stable interop and exchange contracts so character/NPC/session assets can round-trip to Foundry and similar targets without fragile one-off adapters
- NPC vault, reusable prep assets, encounter packs, notes/checklists, reveal/player-screen surfaces, and other reusable GM prep tools
- sync/collaboration behavior that keeps basic play surfaces useful offline and portable when disconnected
- explain/source integration paths that can attach provenance, evidence pointers, and bring-your-own compendium/PDF mapping where licensing allows

Guardrails:
- do not recreate mechanics or rules truth here
- do not center cinematic media generation ahead of session ops value
- do not treat export/import as a courtesy feature; it is a product pillar
- design cloud/collaboration as additive, not mandatory

Product implication:
Hub should feel like the Shadowrun session OS: shared state, projections, prep assets, interop seams, and explainable operations. AI is a layer on top of that, not the center.
