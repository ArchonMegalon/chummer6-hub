namespace Chummer.Run.Api.Contracts;

public sealed record SignalToCanonPacketBundle(
    DateTimeOffset BuiltAtUtc,
    IReadOnlyList<SignalToCanonPacketProjection> Packets);

public sealed record SignalToCanonPacketProjection(
    string PacketId,
    string SurfaceId,
    string Route,
    string DestinationRoute,
    string SourceKind,
    string Audience,
    string ClaimSensitivity,
    string Owner,
    string DecisionAuthority,
    string CloseoutPosture,
    string Summary,
    IReadOnlyList<string> EvidenceLines,
    DateTimeOffset EmittedAtUtc,
    string Locale = "en-US",
    string? ReleaseChannel = null,
    string? ReleaseVersion = null,
    string? CaseId = null);
