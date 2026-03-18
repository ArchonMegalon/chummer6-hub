using Chummer.Contracts.Content;

namespace Chummer.Contracts.Presentation;

public static class BuildKitWorkbenchSurfaceIds
{
    public const string Library = "buildkit-library";
    public const string Inspector = "buildkit-inspector";
    public const string PromptPanel = "buildkit-prompt-panel";
    public const string ApplyPreview = "buildkit-apply-preview";
}

public static class BuildKitAvailabilityStates
{
    public const string Available = "available";
    public const string Installed = "installed";
    public const string RequiresRuntimeChange = "requires-runtime-change";
    public const string MissingDependencies = "missing-dependencies";
    public const string Blocked = "blocked";
}

public static class BuildKitPreviewChangeKinds
{
    public const string BundleAdded = "bundle-added";
    public const string MetadataUpdated = "metadata-updated";
    public const string CareerUpdateQueued = "career-update-queued";
    public const string PromptSelectionApplied = "prompt-selection-applied";
}

public sealed record BuildKitLibraryItem(
    ArtifactVersionReference BuildKit,
    string Title,
    string AvailabilityState,
    string Visibility,
    string TrustTier,
    IReadOnlyList<string> Targets,
    int IssueCount = 0);

public sealed record BuildKitPromptPreview(
    BuildKitPromptDescriptor Prompt,
    IReadOnlyList<BuildKitPromptResolution> CurrentSelections,
    IReadOnlyList<BuildKitValidationIssue> Issues);

public sealed record BuildKitPreviewChange(
    string Kind,
    string Summary,
    string? ActionId = null,
    string? TargetId = null,
    string? PromptId = null);

public sealed record BuildKitLibraryProjection(
    IReadOnlyList<BuildKitLibraryItem> Items,
    string? SelectedBuildKitId = null,
    string? ContinuationToken = null);

public sealed record BuildKitInspectorProjection(
    BuildKitManifest Manifest,
    string AvailabilityState,
    IReadOnlyList<BuildKitValidationIssue> Issues,
    bool CanApply,
    string? RuntimeFingerprint = null);

public sealed record BuildKitApplyPreviewProjection(
    string BuildKitId,
    string WorkspaceId,
    IReadOnlyList<BuildKitPromptPreview> Prompts,
    IReadOnlyList<BuildKitPreviewChange> Changes,
    BuildKitValidationReceipt Validation,
    bool RequiresConfirmation = true);
