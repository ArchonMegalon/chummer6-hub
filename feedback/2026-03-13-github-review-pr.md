# GitHub Codex Review

PR: local://hub

Findings:
- [high] Chummer.Run.Contracts/HubRegistryContracts.cs : line 137 Public registry contracts drifted in-place: `HubArtifactCreateRequest` now requires new fields (`RulesetId`, `Visibility`, `TrustTier`) and renames `Owner` to `OwnerId`; related DTOs (`HubArtifactMetadata`, `RuntimeBundleIssueRequest`, install/state projections) were also reshaped. This is a compatibility regression against `main` for compiled consumers and for existing JSON clients posting the prior payload shape (now 400/model-validation failures). Keep v1 fields/constructors as backward-compatible shims or introduce explicit v2 contract types/routes with migration handling.
- [medium] tests/RunServicesVerification/CompatibilityVerification.cs : line 172 Compatibility coverage for registry contracts only asserts install/review DTOs and does not verify create/metadata/runtime-bundle request/response shapes. Because of that gap, the current breaking registry DTO drift passed without a dedicated guardrail. Add shape-compat assertions (or explicit breakage gates) for the changed registry DTO family.
