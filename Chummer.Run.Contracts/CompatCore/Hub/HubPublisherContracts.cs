namespace Chummer.Contracts.Hub;

public static class HubPublisherVerificationStates
{
    public const string Unverified = "unverified";
    public const string Verified = "verified";
    public const string Official = "official";
}

public sealed record HubUpdatePublisherRequest(
    string DisplayName,
    string Slug,
    string? Description = null,
    string? WebsiteUrl = null);

public sealed record HubPublisherProfile(
    string PublisherId,
    string OwnerId,
    string DisplayName,
    string Slug,
    string VerificationState,
    DateTimeOffset CreatedAtUtc,
    DateTimeOffset UpdatedAtUtc,
    string? Description = null,
    string? WebsiteUrl = null);

public sealed record HubPublisherCatalog(
    IReadOnlyList<HubPublisherProfile> Items);

public sealed record HubPublisherSummary(
    string PublisherId,
    string DisplayName,
    string Slug,
    string VerificationState,
    string LinkTarget);

public sealed record HubPublisherRecord(
    string PublisherId,
    string OwnerId,
    string DisplayName,
    string Slug,
    string VerificationState,
    DateTimeOffset CreatedAtUtc,
    DateTimeOffset UpdatedAtUtc,
    string? Description = null,
    string? WebsiteUrl = null);
