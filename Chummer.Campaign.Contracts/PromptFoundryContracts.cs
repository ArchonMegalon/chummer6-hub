namespace Chummer.Campaign.Contracts;

public static class PromptFoundryProviderModes
{
    public const string LocalTemplate = "local_template";
    public const string PromptArchitectsTemplateSeed = "prompt_architects_template_seed";
    public const string PromptArchitectsOperatorAssist = "prompt_architects_operator_assist";
    public const string PromptArchitectsRuntime = "prompt_architects_runtime";
}

public sealed record PromptArchitectsProviderVerificationProjection(
    string Service,
    string Plan,
    bool AccountVerified,
    string LicenseStatus,
    int TeamMembersLimit,
    int TotalPromptsPerMonth,
    string PromptHistoryLimit,
    string PersonalContextLimit,
    bool JsonPromptSupport,
    bool ImagePromptGeneration,
    bool ImagePromptLibrary,
    bool VideoPromptLibrary,
    bool ChromeExtension,
    bool HotkeyCommands,
    bool UniversalSidebarUi,
    bool TemplateLibraryTags,
    bool RefineMode,
    bool ShortenMode,
    bool McpConnectionClaimed,
    bool ApiAvailable,
    bool ExportAvailable,
    bool ImportAvailable,
    bool BulkTemplateExport,
    bool WebhookAvailable,
    bool AuditLogAvailable,
    string TeamWorkspacePermissions,
    string DataRetentionReviewed,
    string ProviderSupportContact,
    IReadOnlyDictionary<string, bool> IntegrationModeAllowed,
    string Status);

public sealed record PromptTemplateProjection(
    string Id,
    string Name,
    string Type,
    string Version,
    string Source,
    string? SourceReceiptId,
    IReadOnlyList<string> AllowedDataClasses,
    IReadOnlyList<string> ForbiddenDataClasses,
    IReadOnlyDictionary<string, string> InputSchema,
    IReadOnlyDictionary<string, string> OutputSchema,
    string PromptBody,
    string NegativePrompt,
    string Status,
    IReadOnlyList<string> Tags,
    DateTimeOffset UpdatedAtUtc);

public sealed record PromptFoundryCreateDraftRequest(
    string TemplateId,
    string? CampaignId,
    string? GroupId,
    string? VideoType,
    string Audience,
    string Tone,
    string PublicSafeSummary,
    string LocationAlias,
    IReadOnlyList<string>? StyleTags = null,
    IReadOnlyList<string>? GenericCharacterDescriptors = null,
    IReadOnlyList<string>? FaceReferencePlaceholders = null,
    int DurationSeconds = 30,
    string OutputFormat = "magicfit_video_prompt",
    string ProviderMode = PromptFoundryProviderModes.LocalTemplate);

public sealed record PromptFoundryDraftProjection(
    string Id,
    string TemplateId,
    string? CampaignId,
    string? GroupId,
    string? GmUserId,
    string? OperatorUserId,
    string ProviderMode,
    string BasePrompt,
    string? EnhancedPrompt,
    string NegativePrompt,
    IReadOnlyList<string> DiffSummary,
    IReadOnlyList<string> PrivacyWarnings,
    string PrivacyScanStatus,
    decimal? QualityScore,
    int PromptUnitsEstimated,
    string Status,
    DateTimeOffset CreatedAtUtc,
    DateTimeOffset UpdatedAtUtc,
    DateTimeOffset? ApprovedAtUtc);

public sealed record PromptFoundryEditDraftRequest(
    string EnhancedPrompt,
    string NegativePrompt);

public sealed record PromptFoundryApproveDraftRequest(
    bool Approved,
    string ApprovalNote = "");

public sealed record PromptFoundryVersionProjection(
    string PromptDraftId,
    int VersionNumber,
    string EditorUserId,
    string BasePromptHash,
    string EnhancedPromptHash,
    string NegativePromptHash,
    string PrivacyScanStatus,
    DateTimeOffset CreatedAtUtc);

public sealed record PromptUsageLedgerEntryProjection(
    string Id,
    string Provider,
    string AccountId,
    string UserId,
    string? GroupId,
    string? CampaignId,
    string PromptDraftId,
    string TemplateId,
    string EventType,
    int Units,
    string Reason,
    DateTimeOffset CreatedAtUtc);

public sealed record PromptFoundryHomeProjection(
    PromptArchitectsProviderVerificationProjection Provider,
    IReadOnlyList<PromptTemplateProjection> Templates,
    IReadOnlyList<PromptFoundryDraftProjection> Drafts,
    IReadOnlyList<PromptUsageLedgerEntryProjection> UsageLedger,
    IReadOnlyDictionary<string, string> RequiredModes);
