namespace Chummer.Campaign.Contracts;

public sealed record AntiforgeryTokenProjection(
    string RequestToken,
    string HeaderName);

public sealed record CreateCampaignCollaborationRequest(
    string Name,
    string? Summary = null,
    string? Visibility = null,
    string? InitialRunTitle = null);

public sealed record CampaignCollaborationProjection(
    string CampaignId,
    string GroupId,
    string Name,
    string Summary,
    string Visibility,
    string Role,
    bool CanManage,
    string CrewId,
    IReadOnlyList<string> RunIds,
    IReadOnlyList<CampaignRosterEntryProjection> Roster,
    DateTimeOffset CreatedAtUtc,
    DateTimeOffset UpdatedAtUtc);

public sealed record CampaignRosterEntryProjection(
    string DossierId,
    string AuthorityKind,
    string AuthoritativeCharacterId,
    string RunnerHandle,
    string DisplayName,
    string Status,
    string Role,
    long Revision,
    bool GmEditAuthorityGranted,
    long GmAuthorityBindingRevision,
    DateTimeOffset JoinedAtUtc,
    DateTimeOffset UpdatedAtUtc);

public sealed record CampaignPlayerSafeSheetProjection(
    string CampaignId,
    string DossierId,
    string RunnerHandle,
    string DisplayName,
    string Status,
    string Role,
    bool CanManage,
    bool GmEditAuthorityGranted,
    long GmAuthorityBindingRevision,
    long Revision,
    string RuleEnvironmentFingerprint,
    IReadOnlyList<PublicationSafeProjection> Sections,
    DateTimeOffset UpdatedAtUtc);

public sealed record CampaignEligibleCharacterProjection(
    string DossierId,
    string AuthorityKind,
    string AuthoritativeCharacterId,
    string RunnerHandle,
    string DisplayName,
    string Status,
    long CurrentRevision,
    DateTimeOffset UpdatedAtUtc);

public sealed record CampaignSharedSheetUpdateRequest(
    long ExpectedRevision,
    string IdempotencyKey,
    string RunnerHandle,
    string DisplayName,
    string Status,
    string Reason,
    IReadOnlyList<PublicationSafeProjection>? Sections = null);

public sealed record CampaignSharedSheetEditReceipt(
    string ReceiptId,
    string CampaignId,
    string DossierId,
    long PreviousRevision,
    long Revision,
    string IdempotencyKey,
    string Reason,
    string EditedByUserId,
    string BeforeSha256,
    string AfterSha256,
    DateTimeOffset EditedAtUtc);

public sealed record CampaignGmAuthorityUpdateRequest(
    long ExpectedBindingRevision,
    bool GrantGmEditAuthority,
    string IdempotencyKey,
    string Reason);

public sealed record CampaignGmAuthorityUpdateReceipt(
    string ReceiptId,
    string CampaignId,
    string DossierId,
    long PreviousBindingRevision,
    long BindingRevision,
    long CurrentCharacterRevision,
    bool GmEditAuthorityGranted,
    bool Changed,
    string IdempotencyKey,
    string Reason,
    DateTimeOffset ChangedAtUtc);

public sealed record CreateCampaignInviteRequest(
    int ExpiresInMinutes = 1440,
    int MaxUses = 1);

public sealed record CampaignInviteSecretProjection(
    string InviteId,
    string CampaignId,
    string JoinPath,
    string LinkSecret,
    string ShortCode,
    DateTimeOffset ExpiresAtUtc,
    int MaxUses,
    DateTimeOffset CreatedAtUtc);

public sealed record RedeemCampaignInviteRequest(
    string Secret,
    string DossierId,
    string AuthoritativeCharacterId,
    long ExpectedCharacterRevision,
    bool GrantGmEditAuthority,
    string IdempotencyKey);

public sealed record RedeemCampaignJoinCodeRequest(
    string Code,
    string DossierId,
    string AuthoritativeCharacterId,
    long ExpectedCharacterRevision,
    bool GrantGmEditAuthority,
    string IdempotencyKey);

public sealed record CampaignCharacterBindingProjection(
    string BindingId,
    string CampaignId,
    string DossierId,
    string AuthorityKind,
    string AuthoritativeCharacterId,
    long BindingRevision,
    long CurrentRevision,
    string GmAuthorityRole,
    DateTimeOffset GrantedAtUtc);

public sealed record CampaignInviteRedemptionProjection(
    string CampaignId,
    string DossierId,
    string CrewId,
    string Role,
    CampaignCharacterBindingProjection Binding,
    bool AlreadyJoined,
    DateTimeOffset JoinedAtUtc);

public sealed record RunsitePlayerSectionInput(
    string Heading,
    string Body);

public sealed record CampaignRunsiteDraftUpdateRequest(
    long ExpectedRevision,
    string Title,
    string Summary,
    IReadOnlyList<RunsitePlayerSectionInput> PlayerSections,
    string? GmNotes = null);

public sealed record CampaignRunsiteDraftProjection(
    string CampaignId,
    string RunId,
    long Revision,
    string Title,
    string Summary,
    IReadOnlyList<RunsitePlayerSectionInput> PlayerSections,
    string? GmNotes,
    long? PublishedRevision,
    DateTimeOffset UpdatedAtUtc,
    DateTimeOffset? PublishedAtUtc);

public sealed record PublishCampaignRunsiteRequest(
    long ExpectedRevision);

public sealed record CampaignRunsitePlayerProjection(
    string CampaignId,
    string RunId,
    long Revision,
    string Title,
    string Summary,
    IReadOnlyList<RunsitePlayerSectionInput> Sections,
    DateTimeOffset PublishedAtUtc);
