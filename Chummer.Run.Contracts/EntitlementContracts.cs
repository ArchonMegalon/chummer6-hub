namespace Chummer.Run.Contracts.Entitlements;

public sealed record EntitlementDto(
    string EntitlementId,
    string Scope,
    string ScopeId,
    string Key,
    string Status,
    string Source,
    string? SponsorSessionId,
    DateTimeOffset GrantedAtUtc,
    DateTimeOffset? ExpiresAtUtc = null);

public sealed record EntitlementGrantDto(
    string GrantId,
    string Scope,
    string ScopeId,
    string Key,
    string SourceReceiptId,
    string Reason,
    DateTimeOffset GrantedAtUtc,
    DateTimeOffset? ExpiresAtUtc = null);
