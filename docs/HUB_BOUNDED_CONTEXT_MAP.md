# Hub Bounded Context Map

`chummer6-hub` remains one hosted repo, but it no longer gets to behave like one hidden semantic owner.

The bounded contexts in this repo are:

## Accounts and Community

Owns:

- product users and linked identities
- groups, memberships, sponsor sessions, rewards, entitlements, and the community ledger
- account-facing install summaries and signed-in home/account projections

Primary services:

- `AccountService`
- `IdentityLinkService`
- `UserExperienceService`
- `GroupService`
- `RewardService`
- `EntitlementService`
- `LeaderboardService`
- `LedgerService`

## Campaign Spine

Owns:

- dossier, crew, campaign, run, scene, objective, and continuity summaries exposed from Hub
- workspace digests and calmer client follow-through read models derived from the same campaign truth
- account and workspace summaries derived from package-owned campaign truth

Primary services:

- `CampaignSpineService`
- `CampaignWorkspaceServerPlaneService`

## Control and Support

Owns:

- support intake, attachment storage, case timeline, closure truth, assistant grounding, and crash normalization
- install-aware support and fix-notice projections shown in signed-in account surfaces

Primary services:

- `SupportStore`
- `SupportAttachmentStorageService`
- `SupportCaseService`
- `SupportAssistantService`
- `CrashSupportService`

## Public Guide, Home, and Downloads

Owns:

- public landing, trust, help, downloads, and progress projections
- public read models compiled from canon plus registry/install truth rather than ad hoc copy

Primary services:

- `PublicCanonFileLoader`
- `PublicRouteCatalogService`
- `PublicActionResolver`
- `PublicLandingService`
- `PublicTrustContentService`
- `PublicNavigationService`
- `HubPageChromeService`
- `PublicProgressService`
- `PublicReleaseManifestService`
- `ReleaseSelectionService`

Runtime truth note:
- `PublicReleaseManifestService` may read the registry-owned current release-channel projection from `chummer6-hub-registry`
  over `CHUMMER_RELEASE_REGISTRY_CURRENT_URL` / `CHUMMER_HUB_REGISTRY_BASE_URL` before falling back to the file-backed
  `RELEASE_CHANNEL.generated.json` snapshot.

## Install and Orchestration Adapters

Owns:

- install-linking persistence and grant redemption
- Fleet receipt verification and authentication/browser adapters
- transactional verification seams that stay adapter-only rather than semantic owner truth

Primary services:

- `InstallLinkingStore`
- `InstallLinkingService`
- `FleetReceiptVerifier`
- `HubEmailLinkVerificationService`
- `HubIdentityClient`
- `HubBrowserAuthService`
- `HubGoogleAuthService`
- `FleetBridgeService`

## Boundary rules

- Every bounded context owns its own read models and retention posture.
- Shared contracts still come from package families, not from this repo inventing side DTOs.
- Public/help/account surfaces may compose data from multiple contexts, but they must not erase the ownership split.
- Assistant and provider integrations remain adapters around Hub-owned truth, not a second system of record.
