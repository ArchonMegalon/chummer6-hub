namespace Chummer.Contracts.AI;

public static class AiMediaAssetApiOperations
{
    public const string ListMediaAssets = "list-media-assets";
    public const string GetMediaAsset = "get-media-asset";
}

public static class AiMediaAssetKinds
{
    public const string Portrait = "portrait";
    public const string Dossier = "dossier";
    public const string RouteVideo = "route-video";
    public const string Handout = "handout";
}

public static class AiMediaAssetStates
{
    public const string Draft = "draft";
    public const string PendingReview = "pending-review";
    public const string ApprovedPrivate = "approved-private";
    public const string ApprovedCanonical = "approved-canonical";
    public const string Rejected = "rejected";
    public const string Published = "published";
}

public sealed record AiMediaAssetQuery(
    string? AssetKind = null,
    string? CharacterId = null,
    string? State = null,
    int MaxCount = 20);

public sealed record AiMediaAssetProjection(
    string AssetId,
    string AssetKind,
    string Title,
    string State,
    DateTimeOffset CreatedAtUtc,
    string? CharacterId = null,
    string? SourceJobId = null);

public sealed record AiMediaAssetCatalog(
    IReadOnlyList<AiMediaAssetProjection> Items,
    int TotalCount);
