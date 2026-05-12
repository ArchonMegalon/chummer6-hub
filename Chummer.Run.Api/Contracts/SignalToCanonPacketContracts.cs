namespace Chummer.Run.Api.Contracts;

public sealed record SignalToCanonPacketBundle(
    DateTimeOffset BuiltAtUtc,
    IReadOnlyList<SignalToCanonPacketProjection> Packets);

public sealed record JourneyProofEventRef(
    string EventKey,
    string JourneyKey,
    string SourceRef,
    string Summary);

public sealed record SignalToCanonPacketProjection(
    string PacketId,
    string SurfaceId,
    string Route,
    string DestinationRoute,
    string SourceKind,
    string SourceClassification,
    string Audience,
    string ClaimSensitivity,
    string Owner,
    string DecisionAuthority,
    string UpstreamPatchRequirement,
    string NoChangeRationalePolicy,
    string CloseoutPosture,
    string Summary,
    IReadOnlyList<string> EvidenceLines,
    IReadOnlyList<JourneyProofEventRef> JourneyProofEventRefs,
    DateTimeOffset EmittedAtUtc,
    string Locale = "en-US",
    string? ReleaseChannel = null,
    string? ReleaseVersion = null,
    string? CaseId = null);
