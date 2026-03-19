using System.ComponentModel.DataAnnotations;

namespace Chummer.Run.Contracts.Identity;

public sealed record IdentitySessionIssueRequest(
    [Required(AllowEmptyStrings = false), StringLength(128)] string SubjectId,
    string? DisplayName,
    string? Email,
    IReadOnlyList<string>? RequestedRoles = null,
    TimeSpan? RequestedTtl = null);

public sealed record IdentitySessionIssueResponse(
    string SessionId,
    string SubjectId,
    string DisplayName,
    string? Email,
    IReadOnlyList<string> Roles,
    string AccessToken,
    string RefreshToken,
    DateTimeOffset IssuedAtUtc,
    DateTimeOffset ExpiresAtUtc);

public sealed record EmailAuthStartRequest(
    [Required(AllowEmptyStrings = false), StringLength(320)] string Email,
    string? DisplayName,
    string? NextPath = null);

public sealed record EmailAuthStartResponse(
    string TicketId,
    string SubjectId,
    string Email,
    string DisplayName,
    string? NextPath,
    DateTimeOffset CreatedAtUtc,
    DateTimeOffset ExpiresAtUtc,
    string DeliveryMode,
    string PreviewNote);

public sealed record EmailAuthCompleteRequest(
    [Required(AllowEmptyStrings = false), StringLength(128)] string TicketId);

public sealed record IdentityRoleSetRequest(
    [Required, MinLength(1)] IReadOnlyList<string> Roles,
    string? AssignedBy = null);

public sealed record IdentitySubjectResponse(
    string SubjectId,
    string DisplayName,
    string? Email,
    IReadOnlyList<string> Roles,
    DateTimeOffset UpdatedAtUtc);

public sealed record IdentityIntrospectionRequest(
    [Required(AllowEmptyStrings = false), StringLength(512)] string AccessToken);

public sealed record IdentityIntrospectionResponse(
    bool Active,
    string? SessionId,
    string? SubjectId,
    IReadOnlyList<string>? Roles,
    DateTimeOffset? ExpiresAtUtc);

public sealed record IdentitySessionRevokeRequest(
    [Required(AllowEmptyStrings = false), StringLength(512)] string AccessToken);

public sealed record IdentitySessionRevokeResponse(
    bool Revoked,
    string? SessionId,
    string? SubjectId,
    DateTimeOffset RevokedAtUtc);
