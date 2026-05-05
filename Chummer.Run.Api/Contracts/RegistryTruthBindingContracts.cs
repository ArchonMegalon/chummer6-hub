using Chummer.Control.Contracts.Support;
using Chummer.Hub.Registry.Contracts.InstallLinking;

namespace Chummer.Run.Api.Contracts;

public sealed record RegistryTruthBindingContext(
    InstallLinkingSummaryDto? InstallLinking,
    IReadOnlyList<SupportCaseProjection>? SupportCases,
    string Locale = "en-US");

public sealed record RegistryTruthBindingBundle(
    DateTimeOffset BuiltAtUtc,
    IReadOnlyList<RegistryTruthBindingProjection> Bindings);

public sealed record RegistryTruthBindingProjection(
    string BindingId,
    string SurfaceId,
    string Route,
    string ComparisonRoute,
    string RegistrySource,
    string ReleaseChannel,
    string ReleaseVersion,
    string ProofStatus,
    string SupportabilityState,
    string FixAvailabilitySummary,
    string Summary,
    IReadOnlyList<string> EvidenceLines,
    IReadOnlyList<RegistryTruthBindingActionProjection> Actions,
    DateTimeOffset EmittedAtUtc,
    string Locale,
    string? SourceId = null);

public sealed record RegistryTruthBindingActionProjection(
    string ActionId,
    string Label,
    string Href,
    string Summary);
