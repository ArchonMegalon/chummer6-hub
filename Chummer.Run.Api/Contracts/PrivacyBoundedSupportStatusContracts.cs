using Chummer.Control.Contracts.Support;
using Chummer.Hub.Registry.Contracts.InstallLinking;

namespace Chummer.Run.Api.Contracts;

public sealed record PrivacyBoundedSupportStatusContext(
    IReadOnlyList<SupportCaseProjection>? SupportCases,
    IReadOnlyList<CrashWorkItemProjection>? CrashWorkItems,
    SignalToCanonPacketBundle? PublicSignals,
    InstallLinkingSummaryDto? InstallLinking,
    string Locale = "en-US");

public sealed record PrivacyBoundedSupportStatusBundle(
    DateTimeOffset BuiltAtUtc,
    IReadOnlyList<PrivacyBoundedSupportStatusProjection> Projections);

public sealed record PrivacyBoundedSupportStatusProjection(
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
    IReadOnlyList<PrivacyBoundedSupportStatusActionProjection> Actions,
    DateTimeOffset EmittedAtUtc,
    string Locale,
    string? SourceId = null);

public sealed record PrivacyBoundedSupportStatusActionProjection(
    string ActionId,
    string Label,
    string Href,
    string Summary);
