namespace Chummer.Contracts.Presentation;

public sealed record GeneratedAssetProjection(
    string AssetId,
    string Title,
    string AssetKind,
    string Source,
    string Summary,
    string PreviewKind,
    string ReviewState,
    DateTimeOffset CreatedAtUtc,
    bool IsCanonical = false,
    string? PreviewUri = null,
    string? PreviewBody = null,
    IReadOnlyList<GeneratedAssetBadge>? Badges = null,
    IReadOnlyList<GeneratedAssetMetadataField>? Metadata = null,
    IReadOnlyList<GeneratedAssetComparisonSlot>? ComparisonSlots = null,
    IReadOnlyList<GeneratedAssetPreviewSection>? PreviewSections = null,
    IReadOnlyList<GeneratedAssetAttachmentTarget>? AttachmentTargets = null,
    IReadOnlyList<GeneratedAssetActionDescriptor>? Actions = null);

public sealed record GeneratedAssetBadge(
    string BadgeId,
    string Label,
    string Kind,
    bool Emphasized = false);

public sealed record GeneratedAssetMetadataField(
    string FieldId,
    string Label,
    string Value,
    bool Emphasized = false);

public sealed record GeneratedAssetComparisonSlot(
    string SlotId,
    string Label,
    string Role,
    string Summary,
    string PreviewUri,
    IReadOnlyList<GeneratedAssetBadge>? Badges = null,
    IReadOnlyList<GeneratedAssetMetadataField>? Metadata = null);

public sealed record GeneratedAssetPreviewSection(
    string SectionId,
    string Label,
    string Summary,
    string? Body = null,
    IReadOnlyList<GeneratedAssetBadge>? Badges = null,
    IReadOnlyList<GeneratedAssetMetadataField>? Metadata = null);

public sealed record GeneratedAssetAttachmentTarget(
    string TargetId,
    string Label,
    string Kind,
    bool Enabled = true);

public sealed record GeneratedAssetActionDescriptor(
    string ActionId,
    string Label,
    string Kind,
    bool Enabled,
    string? TargetId = null)
{
    public string ActionKind => Kind;
}

public sealed record GeneratedAssetActionRequest(
    string AssetId,
    string ActionId,
    string ActionKind,
    string? TargetId = null);

public static class GeneratedAssetPreviewKinds
{
    public const string Image = "image";
    public const string Video = "video";
    public const string Document = "document";
    public const string Summary = "summary";
}

public static class GeneratedAssetBadgeKinds
{
    public const string Source = "source";
    public const string Audience = "audience";
    public const string Provenance = "provenance";
    public const string State = "state";
}

public static class GeneratedAssetComparisonRoles
{
    public const string Baseline = "baseline";
    public const string Candidate = "candidate";
}

public static class GeneratedAssetActionKinds
{
    public const string Attach = "attach";
    public const string Approve = "approve";
    public const string Archive = "archive";
}
