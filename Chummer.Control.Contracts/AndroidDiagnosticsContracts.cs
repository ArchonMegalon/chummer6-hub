using System.Text.Json.Serialization;

namespace Chummer.Control.Contracts.Support;

public enum AndroidDiagnosticArea { Other, Creation, LifeModules, Book, Account, Settings, Career }
public enum AndroidDiagnosticOperation { Appearance, Action, Refresh, StoryReadiness }
public enum AndroidDiagnosticOutcome { Failed, Slow, DispatchRejected }
public enum AndroidDiagnosticError { None, Network, Storage, InvalidState, Access, Json, Other }

// Deliberately no free text, device/account/runner identity, URLs, stack traces,
// exception messages or arbitrary metadata bag. Slow is an observation, not ANR.
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record AndroidDiagnosticReport(
    [property: JsonRequired] Guid ReportId,
    [property: JsonRequired] int VersionCode,
    [property: JsonRequired] DateTimeOffset ObservedAtUtc,
    [property: JsonRequired] AndroidDiagnosticArea Area,
    [property: JsonRequired] AndroidDiagnosticOperation Operation,
    [property: JsonRequired] AndroidDiagnosticOutcome Outcome,
    [property: JsonRequired] int ElapsedMilliseconds,
    [property: JsonRequired] AndroidDiagnosticError Error);

public sealed record AndroidDiagnosticReceipt(Guid ReportId, DateTimeOffset ReceivedAtUtc);
public sealed record AndroidDiagnosticObservation(AndroidDiagnosticReport Report, DateTimeOffset ReceivedAtUtc);
public sealed record AndroidDiagnosticReadback(IReadOnlyList<AndroidDiagnosticObservation> Items);
