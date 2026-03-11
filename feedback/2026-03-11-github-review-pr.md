# GitHub Codex Review

PR: https://github.com/ArchonMegalon/chummer.run-services/pull/1

Findings:
- [high] Chummer.Run.Contracts/MediaContracts.cs : line 55 Public DTOs previously exposed from Chummer.Run.Contracts.Media (e.g., PacketFactory*/RouteCinema* types present on main) were removed without public forwarding aliases. This is a compile-time breaking change for existing consumers of Chummer.Run.Contracts and should be handled via compatibility wrappers in the public package or an explicit major-version break/migration gate.
- [medium] Chummer.Media.Contracts/MediaFactoryContracts.cs : line 74 MediaRenderJobType member names were renamed (e.g., legacy names like RouteCinemaVideo/PacketPreview are no longer present). Any string-based enum serialization/deserialization or code compiled against previous names will break. Add backward-compatible aliases or a migration/translation layer to avoid contract drift.
- [high] Chummer.Run.AI/Services/Session/OfflineSyncService.cs : line 69 Offline reconcile concatenates snapshot and local pending events and passes them directly to MergeEventsAsync without enforcing snapshot session/scene identity. MergeEventsAsync then anchors to events[0] (SessionLedgerService.cs:51-55), so mixed-scene payloads can be silently ignored or merged under an unintended scene, creating relay convergence and state-safety hazards. Validate/partition LocalPendingEvents by snapshot session+scene before merge and reject mismatches explicitly.
