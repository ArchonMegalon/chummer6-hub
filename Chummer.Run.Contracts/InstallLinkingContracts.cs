namespace Chummer.Run.Contracts.InstallLinking;

public static class InstallAccessClasses
{
    public const string OpenPublic = "open_public";
    public const string AccountRecommended = "account_recommended";
    public const string AccountRequired = "account_required";
}

public static class InstallClaimTicketStates
{
    public const string Pending = "pending";
    public const string Redeemed = "redeemed";
    public const string Expired = "expired";
    public const string Revoked = "revoked";
}

public static class InstallationGrantStates
{
    public const string Active = "active";
    public const string Revoked = "revoked";
    public const string Expired = "expired";
}

public static class ClaimedInstallationStates
{
    public const string Active = "active";
    public const string Revoked = "revoked";
}

public sealed record DownloadReceiptDto(
    string ReceiptId,
    string ArtifactId,
    string ArtifactLabel,
    string FileName,
    string DownloadUrl,
    string Channel,
    string Version,
    string Head,
    string Platform,
    string Arch,
    string Kind,
    string InstallAccessClass,
    DateTimeOffset IssuedAtUtc,
    string? UserId = null,
    string? SubjectId = null,
    string? ClaimTicketId = null,
    string? ClaimCode = null,
    DateTimeOffset? ClaimTicketExpiresAtUtc = null);

public sealed record InstallClaimTicketDto(
    string TicketId,
    string ClaimCode,
    string ArtifactId,
    string ArtifactLabel,
    string Channel,
    string Version,
    string InstallAccessClass,
    string Status,
    DateTimeOffset CreatedAtUtc,
    DateTimeOffset ExpiresAtUtc,
    string? UserId = null,
    string? SubjectId = null,
    string? ReceiptId = null,
    string? InstallationId = null);

public sealed record ClaimedInstallationDto(
    string InstallationId,
    string ArtifactId,
    string Channel,
    string Version,
    string InstallAccessClass,
    string Status,
    DateTimeOffset CreatedAtUtc,
    DateTimeOffset UpdatedAtUtc,
    string? UserId = null,
    string? SubjectId = null,
    string? PublicKey = null,
    string? ClaimTicketId = null,
    string? HeadId = null,
    string? Platform = null,
    string? Arch = null,
    string? HostLabel = null,
    string? GrantId = null);

public sealed record InstallationGrantDto(
    string GrantId,
    string InstallationId,
    string Status,
    string AccessToken,
    DateTimeOffset IssuedAtUtc,
    DateTimeOffset ExpiresAtUtc,
    string? UserId = null,
    string? SubjectId = null);

public sealed record InstallLinkingSummaryDto(
    IReadOnlyList<DownloadReceiptDto> RecentReceipts,
    IReadOnlyList<InstallClaimTicketDto> PendingClaimTickets,
    IReadOnlyList<ClaimedInstallationDto>? ClaimedInstallations = null,
    IReadOnlyList<InstallationGrantDto>? ActiveGrants = null);

public sealed record RedeemInstallClaimRequestDto(
    string ClaimCode,
    string InstallationId,
    string HeadId,
    string ApplicationVersion,
    string ChannelId,
    string Platform,
    string Arch,
    string? PublicKey = null,
    string? HostLabel = null);

public sealed record RedeemInstallClaimResponseDto(
    InstallClaimTicketDto Ticket,
    ClaimedInstallationDto Installation,
    InstallationGrantDto Grant,
    bool AlreadyClaimed);

public sealed record RefreshInstallationGrantRequestDto(
    string InstallationId,
    string AccessToken,
    string? HeadId = null,
    string? ApplicationVersion = null,
    string? ChannelId = null,
    string? Platform = null,
    string? Arch = null,
    string? PublicKey = null,
    string? HostLabel = null);

public sealed record RefreshInstallationGrantResponseDto(
    ClaimedInstallationDto Installation,
    InstallationGrantDto Grant,
    bool Rotated);
