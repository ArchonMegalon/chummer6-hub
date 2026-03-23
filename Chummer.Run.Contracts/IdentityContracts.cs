using System.ComponentModel.DataAnnotations;
using System.Security.Cryptography;
using System.Text;

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

public sealed record IdentityEmailDeliveryEventResponse(
    string DeliveryId,
    string EmailKind,
    string TransportKey,
    string DeliveryMode,
    string Status,
    bool Delivered,
    string RecipientEmail,
    string? ProviderMessageId,
    string? FailureReason,
    DateTimeOffset OccurredAtUtc);

public sealed record IdentityEmailRecipientStateResponse(
    string Email,
    string State,
    string? LastEvent,
    DateTimeOffset? LastEventAtUtc,
    string? Provider,
    string? ProviderDetail);

public sealed record IdentityEmailDeliveryStatusResponse(
    IReadOnlyList<IdentityEmailDeliveryEventResponse> RecentDeliveries,
    IReadOnlyList<IdentityEmailRecipientStateResponse> Recipients,
    DateTimeOffset GeneratedAtUtc);

public sealed record IdentityEmailWebhookAckResponse(
    string Provider,
    string Status,
    int RecordedEvents,
    DateTimeOffset ReceivedAtUtc);

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

public static class IdentitySubjectDerivation
{
    public static string FromEmail(string email)
    {
        if (string.IsNullOrWhiteSpace(email))
        {
            throw new ArgumentException("email is required.", nameof(email));
        }

        return BuildHashedSubject("subject.email", email.Trim().ToLowerInvariant());
    }

    public static string FromGoogleSubject(string providerSubject)
    {
        if (string.IsNullOrWhiteSpace(providerSubject))
        {
            throw new ArgumentException("providerSubject is required.", nameof(providerSubject));
        }

        return BuildHashedSubject("subject.google", providerSubject.Trim());
    }

    private static string BuildHashedSubject(string prefix, string value)
    {
        var hash = SHA256.HashData(Encoding.UTF8.GetBytes(value));
        return $"{prefix}.{Convert.ToHexString(hash[..8]).ToLowerInvariant()}";
    }
}
