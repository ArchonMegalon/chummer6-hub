using Chummer.Hub.Registry.Contracts.InstallLinking;

namespace Chummer.Run.Api.Contracts;

public sealed record HostedProofContractContext(
    OpenRunOrchestrationProjection? OpenRun,
    SignalToCanonPacketBundle? PublicSignals,
    InstallLinkingSummaryDto? InstallLinking,
    string? CommunityHubRoute,
    string? CommunityWorkspaceRoute,
    string Locale = "en-US");

public sealed record HostedProofContractBundle(
    DateTimeOffset BuiltAtUtc,
    IReadOnlyList<HostedProofContractProjection> Contracts);

public sealed record HostedProofContractProjection(
    string ContractId,
    string ContractName,
    string SurfaceId,
    string Route,
    string ComparisonRoute,
    string Audience,
    string ClaimSensitivity,
    string Owner,
    string DecisionAuthority,
    string CloseoutPosture,
    string Summary,
    IReadOnlyList<string> EvidenceLines,
    IReadOnlyList<HostedProofContractActionProjection> Actions,
    DateTimeOffset EmittedAtUtc,
    string Locale,
    string ReleaseChannel,
    string ReleaseVersion,
    string? SourceId = null);

public sealed record HostedProofContractActionProjection(
    string ActionId,
    string Label,
    string Href,
    string Summary);
