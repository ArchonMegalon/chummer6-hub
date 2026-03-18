namespace Chummer.Contracts.Hub;

public static class HubRecommendationStates
{
    public const string Recommended = "recommended";
    public const string Neutral = "neutral";
    public const string NotRecommended = "not-recommended";
}

public sealed record HubUpsertReviewRequest(
    string RulesetId,
    string RecommendationState,
    int? Stars = null,
    string? ReviewText = null,
    bool UsedAtTable = false);

public sealed record HubReviewReceipt(
    string ReviewId,
    string ProjectKind,
    string ProjectId,
    string RulesetId,
    string OwnerId,
    string RecommendationState,
    DateTimeOffset CreatedAtUtc,
    DateTimeOffset UpdatedAtUtc,
    int? Stars = null,
    string? ReviewText = null,
    bool UsedAtTable = false);

public sealed record HubReviewCatalog(
    IReadOnlyList<HubReviewReceipt> Items);

public sealed record HubReviewSummary(
    string RecommendationState,
    int? Stars = null,
    bool UsedAtTable = false,
    string? ReviewText = null,
    DateTimeOffset? UpdatedAtUtc = null);

public sealed record HubReviewAggregateSummary(
    int TotalReviews,
    int RecommendedCount,
    int NeutralCount,
    int NotRecommendedCount,
    int UsedAtTableCount = 0,
    int RatedReviewCount = 0,
    double? AverageStars = null,
    DateTimeOffset? LatestReviewAtUtc = null);

public sealed record HubReviewRecord(
    string ReviewId,
    string ProjectKind,
    string ProjectId,
    string RulesetId,
    string OwnerId,
    string RecommendationState,
    DateTimeOffset CreatedAtUtc,
    DateTimeOffset UpdatedAtUtc,
    int? Stars = null,
    string? ReviewText = null,
    bool UsedAtTable = false);
