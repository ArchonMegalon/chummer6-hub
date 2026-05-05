using Chummer.Control.Contracts.Support;
using Chummer.Hub.Registry.Contracts.InstallLinking;
using Chummer.Run.Contracts.Community;

namespace Chummer.Run.Api.Contracts;

public sealed record HostedBoundedContextCoverageContext(
    HubUserDto? User,
    IReadOnlyList<GroupDto>? Groups,
    OpenRunOrchestrationProjection? OpenRun,
    SupportCaseProjection? SupportCase,
    SignalToCanonPacketBundle? PublicSignals,
    InstallLinkingSummaryDto? InstallLinking,
    string Locale = "en-US",
    string? CommunityHubRoute = null);

public sealed record HostedBoundedContextCoverageBundle(
    DateTimeOffset BuiltAtUtc,
    IReadOnlyList<HostedBoundedContextCoverageProjection> Projections);

public sealed record HostedBoundedContextCoverageProjection(
    string ProjectionId,
    string SurfaceId,
    string Route,
    string ComparisonRoute,
    string BoundaryOwner,
    string DecisionAuthority,
    string ReleaseChannel,
    string ReleaseVersion,
    string ProofStatus,
    string SupportabilityState,
    string Summary,
    IReadOnlyList<string> EvidenceLines,
    IReadOnlyList<HostedBoundedContextCoverageActionProjection> Actions,
    DateTimeOffset EmittedAtUtc,
    string Locale,
    string? SourceId = null);

public sealed record HostedBoundedContextCoverageActionProjection(
    string ActionId,
    string Label,
    string Href,
    string Summary);
