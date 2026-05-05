using Chummer.Run.Contracts.Boosters;
using Chummer.Run.Contracts.Community;
using Chummer.Run.Contracts.Entitlements;
using Chummer.Run.Contracts.Leaderboards;
using Chummer.Run.Contracts.Ledger;

namespace Chummer.Run.Api.Contracts;

public sealed record ReusableAccountFlowContext(
    HubUserDto User,
    IReadOnlyList<GroupDto>? Groups,
    IReadOnlyList<JoinCodeDto>? JoinCodes,
    IReadOnlyList<BoostCodeDto>? BoostCodes,
    IReadOnlyList<RewardJournalEntryDto>? Rewards,
    IReadOnlyList<BadgeDto>? Badges,
    IReadOnlyList<EntitlementDto>? Entitlements,
    string Locale = "en-US");

public sealed record ReusableAccountFlowBundle(
    DateTimeOffset BuiltAtUtc,
    IReadOnlyList<ReusableAccountFlowProjection> Projections);

public sealed record ReusableAccountFlowProjection(
    string ProjectionId,
    string SurfaceId,
    string Route,
    string ComparisonRoute,
    string ReleaseChannel,
    string ReleaseVersion,
    string ProofStatus,
    string SupportabilityState,
    string Summary,
    IReadOnlyList<string> EvidenceLines,
    IReadOnlyList<ReusableAccountFlowActionProjection> Actions,
    DateTimeOffset EmittedAtUtc,
    string Locale,
    string? SourceId = null);

public sealed record ReusableAccountFlowActionProjection(
    string ActionId,
    string Label,
    string Href,
    string Summary);
