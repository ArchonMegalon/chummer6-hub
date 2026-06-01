using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using Chummer.Campaign.Contracts;
using Chummer.Run.Contracts.Boosters;
using Chummer.Run.Contracts.Community;

namespace Chummer.Run.Api.Services.Community;

public sealed class GmSessionVideoFoundryService
{
    public const string ProviderAccountId = "magicfit_gm_session_video_foundry";
    public const string Origin = "gm_session_video";

    private static readonly Regex EmailRegex = new(@"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", RegexOptions.IgnoreCase | RegexOptions.Compiled);
    private static readonly string[] ForbiddenPromptFragments =
    [
        "official logo",
        "sourcebook page",
        "sourcebook prose",
        "copy the rulebook",
        "global user face",
        "publish directly"
    ];

    private readonly GmSessionVideoFoundryStore _store;
    private readonly CommunityStore _communityStore;
    private readonly IConfiguration _configuration;

    public GmSessionVideoFoundryService(
        GmSessionVideoFoundryStore store,
        CommunityStore communityStore,
        IConfiguration configuration)
    {
        _store = store;
        _communityStore = communityStore;
        _configuration = configuration;
    }

    public GmSessionVideoFoundryHomeProjection GetHome(string gmUserId, string campaignId)
    {
        CampaignAccess access = EnsureCampaignAccess(gmUserId, campaignId, requireManage: true);
        lock (_store.Gate)
        {
            return new GmSessionVideoFoundryHomeProjection(
                CampaignId: campaignId,
                ProviderAccountRole: "gm_session_video_foundry",
                ProviderAccountStatus: IsSessionAccountConfigured() ? "configured" : "pending_verification",
                QueueIsolationStatus: "isolated_from_official_product_media",
                Routes:
                [
                    $"/gm/campaigns/{campaignId}/video-foundry",
                    $"/gm/campaigns/{campaignId}/video-foundry/cast",
                    $"/gm/campaigns/{campaignId}/video-foundry/new",
                    $"/gm/campaigns/{campaignId}/video-foundry/prompts/{{promptDraftId}}",
                    $"/gm/campaigns/{campaignId}/video-foundry/jobs/{{jobId}}",
                    $"/gm/campaigns/{campaignId}/sessions/{{sessionId}}/videos",
                    $"/gm/campaigns/{campaignId}/sessions/{{sessionId}}/table-pulse/videos"
                ],
                PromptDrafts: _store.PromptDraftsById.Values
                    .Where(item => BelongsTo(gmUserId, campaignId, item))
                    .OrderByDescending(item => item.CreatedAtUtc)
                    .ToArray(),
                RenderJobs: _store.JobsById.Values
                    .Where(item => BelongsTo(gmUserId, campaignId, item))
                    .OrderByDescending(item => item.CreatedAtUtc)
                    .ToArray(),
                Usage: BuildUsageSummary(gmUserId, access.Group.GroupId, campaignId));
        }
    }

    public IReadOnlyList<FaceAssetProjection> ListFaces(string gmUserId, string campaignId, string? query = null)
    {
        EnsureCampaignAccess(gmUserId, campaignId, requireManage: true);
        lock (_store.Gate)
        {
            return _store.FacesById.Values
                .Where(face => CanAccessFace(gmUserId, campaignId, face))
                .Where(face => string.IsNullOrWhiteSpace(query)
                    || face.DisplayName.Contains(query, StringComparison.OrdinalIgnoreCase)
                    || face.RoleTags.Any(tag => tag.Contains(query, StringComparison.OrdinalIgnoreCase)))
                .OrderBy(face => face.DisplayName, StringComparer.OrdinalIgnoreCase)
                .ToArray();
        }
    }

    public FaceAssetProjection GetFace(string gmUserId, string campaignId, string faceId)
    {
        EnsureCampaignAccess(gmUserId, campaignId, requireManage: true);
        lock (_store.Gate)
        {
            if (!_store.FacesById.TryGetValue(faceId, out FaceAssetProjection? face) || !CanAccessFace(gmUserId, campaignId, face))
            {
                throw new KeyNotFoundException($"Unknown face asset: {faceId}");
            }

            return face;
        }
    }

    public FaceAssetProjection CreateFace(string gmUserId, string campaignId, CreateFaceAssetRequest request)
    {
        CampaignAccess access = EnsureCampaignAccess(gmUserId, campaignId, requireManage: true);
        ArgumentNullException.ThrowIfNull(request);
        string displayName = NormalizeRequired(request.DisplayName, "display_name");
        string sourceType = NormalizeSourceType(request.SourceType);
        string visibility = NormalizeVisibilityScope(request.VisibilityScope);
        string consentState = NormalizeConsent(sourceType, request.ConsentState);
        if (request.PublicShareAllowed && consentState != "attested")
        {
            throw new ArgumentException("public face sharing requires attested consent.");
        }

        if (visibility == "public")
        {
            throw new ArgumentException("user faces cannot be globally public.");
        }

        DateTimeOffset now = DateTimeOffset.UtcNow;
        FaceAssetProjection face = new(
            Id: StableId("face", gmUserId, campaignId, displayName, now.ToUnixTimeMilliseconds().ToString(System.Globalization.CultureInfo.InvariantCulture)),
            OwnerGmUserId: gmUserId,
            OwnerWorkspaceId: access.Group.GroupId,
            CampaignId: campaignId,
            DisplayName: displayName,
            Metatype: NormalizeMetatype(request.Metatype),
            RoleTags: NormalizeTags(request.RoleTags),
            SourceType: sourceType,
            VisibilityScope: visibility,
            AllowedUserIds: (request.AllowedUserIds ?? Array.Empty<string>())
                .Select(item => item.Trim())
                .Where(item => item.Length > 0)
                .Distinct(StringComparer.OrdinalIgnoreCase)
                .ToArray(),
            ConsentState: consentState,
            PublicShareAllowed: request.PublicShareAllowed,
            StorageObjectId: $"gm-face-vault/{gmUserId}/{Slug(displayName)}/reference.webp",
            ThumbnailObjectId: $"gm-face-vault/{gmUserId}/{Slug(displayName)}/thumbnail.webp",
            ProviderReferenceIdEncrypted: null,
            CreatedAtUtc: now,
            UpdatedAtUtc: now);

        lock (_store.Gate)
        {
            _store.FacesById[face.Id] = face;
            _store.PersistLocked();
            return face;
        }
    }

    public PromptDraftProjection CreatePromptDraft(string gmUserId, string campaignId, string? sessionId, CreatePromptDraftRequest request)
    {
        CampaignAccess access = EnsureCampaignAccess(gmUserId, campaignId, requireManage: true);
        ArgumentNullException.ThrowIfNull(request);
        IReadOnlyList<string> faceIds = NormalizeIds(request.SelectedFaceAssetIds);
        lock (_store.Gate)
        {
            EnsureFacesAccessibleLocked(gmUserId, campaignId, faceIds);
            DateTimeOffset now = DateTimeOffset.UtcNow;
            int units = EstimateUnits(request.DurationSeconds);
            string prompt = BuildPrompt(campaignId, sessionId, request, faceIds);
            string negativePrompt = "No official Shadowrun logos, no sourcebook page designs, no real corporate logos, no private player data, no direct publishing.";
            string privacyScan = ScanPrompt(prompt, negativePrompt, request.Audience, faceIds, gmUserId, campaignId).Status;
            GmVideoUsageEstimateProjection estimate = BuildUsageEstimate(gmUserId, access.Group.GroupId, campaignId, units, request.DurationSeconds);
            PromptDraftProjection draft = new(
                Id: StableId("prompt", gmUserId, campaignId, now.ToUnixTimeMilliseconds().ToString(System.Globalization.CultureInfo.InvariantCulture)),
                CampaignId: campaignId,
                SessionId: NormalizeOptional(sessionId),
                GmUserId: gmUserId,
                VideoType: NormalizeVideoType(request.VideoType),
                Audience: NormalizeAudience(request.Audience),
                SpoilerLevel: NormalizeSpoilerLevel(request.SpoilerLevel),
                Tone: NormalizeOptional(request.Tone) ?? "noir",
                SelectedFaceAssetIds: faceIds,
                AllowedFacts: NormalizeFacts(request.AllowedFacts),
                ForbiddenFacts: NormalizeFacts(request.ForbiddenFacts),
                GeneratedPrompt: prompt,
                NegativePrompt: negativePrompt,
                ProviderSettings: new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase)
                {
                    ["provider"] = "MagicFit",
                    ["provider_account_id"] = ProviderAccountId,
                    ["duration_seconds"] = Math.Clamp(request.DurationSeconds, 8, 75).ToString(System.Globalization.CultureInfo.InvariantCulture),
                    ["aspect_ratio"] = string.IsNullOrWhiteSpace(request.AspectRatio) ? "16:9" : request.AspectRatio.Trim()
                },
                EstimatedUsage: estimate,
                PrivacyWarnings: BuildPrivacyWarnings(request.Audience, faceIds),
                PrivacyScanStatus: privacyScan,
                Status: "gm_prompt_review",
                CreatedAtUtc: now,
                ApprovedAtUtc: null);
            _store.PromptDraftsById[draft.Id] = draft;
            AddPromptVersionLocked(draft, gmUserId);
            _store.PersistLocked();
            return draft;
        }
    }

    public PromptDraftProjection EditPromptDraft(string gmUserId, string campaignId, string promptDraftId, EditPromptDraftRequest request)
    {
        EnsureCampaignAccess(gmUserId, campaignId, requireManage: true);
        ArgumentNullException.ThrowIfNull(request);
        lock (_store.Gate)
        {
            PromptDraftProjection draft = RequireDraftLocked(gmUserId, campaignId, promptDraftId);
            if (draft.Status == "approved_for_render")
            {
                throw new InvalidOperationException("approved prompts cannot be edited; create a new draft or regenerate prompt only.");
            }

            ScanResult scan = ScanPrompt(request.GeneratedPrompt, request.NegativePrompt, draft.Audience, draft.SelectedFaceAssetIds, gmUserId, campaignId);
            PromptDraftProjection updated = draft with
            {
                GeneratedPrompt = NormalizeRequired(request.GeneratedPrompt, "generated_prompt"),
                NegativePrompt = NormalizeRequired(request.NegativePrompt, "negative_prompt"),
                Tone = NormalizeOptional(request.Tone) ?? draft.Tone,
                PrivacyWarnings = scan.Warnings,
                PrivacyScanStatus = scan.Status,
                Status = "gm_prompt_review"
            };
            _store.PromptDraftsById[updated.Id] = updated;
            AddPromptVersionLocked(updated, gmUserId);
            _store.PersistLocked();
            return updated;
        }
    }

    public PromptDraftProjection RegeneratePromptOnly(string gmUserId, string campaignId, string promptDraftId)
    {
        EnsureCampaignAccess(gmUserId, campaignId, requireManage: true);
        lock (_store.Gate)
        {
            PromptDraftProjection draft = RequireDraftLocked(gmUserId, campaignId, promptDraftId);
            var request = new CreatePromptDraftRequest(
                draft.VideoType,
                draft.Audience,
                draft.SpoilerLevel,
                draft.Tone,
                draft.SelectedFaceAssetIds,
                draft.AllowedFacts,
                draft.ForbiddenFacts,
                int.Parse(draft.ProviderSettings.GetValueOrDefault("duration_seconds", "30"), System.Globalization.CultureInfo.InvariantCulture),
                draft.ProviderSettings.GetValueOrDefault("aspect_ratio", "16:9"));
            string prompt = BuildPrompt(campaignId, draft.SessionId, request, draft.SelectedFaceAssetIds);
            ScanResult scan = ScanPrompt(prompt, draft.NegativePrompt, draft.Audience, draft.SelectedFaceAssetIds, gmUserId, campaignId);
            PromptDraftProjection updated = draft with
            {
                GeneratedPrompt = prompt,
                PrivacyWarnings = scan.Warnings,
                PrivacyScanStatus = scan.Status,
                Status = "gm_prompt_review",
                ApprovedAtUtc = null
            };
            _store.PromptDraftsById[updated.Id] = updated;
            AddPromptVersionLocked(updated, gmUserId);
            _store.PersistLocked();
            return updated;
        }
    }

    public SessionVideoRenderJobProjection ApprovePrompt(string gmUserId, string campaignId, string promptDraftId, ApprovePromptDraftRequest request)
    {
        CampaignAccess access = EnsureCampaignAccess(gmUserId, campaignId, requireManage: true);
        ArgumentNullException.ThrowIfNull(request);
        if (!request.Approved)
        {
            throw new ArgumentException("explicit approval is required before render.");
        }

        lock (_store.Gate)
        {
            PromptDraftProjection draft = RequireDraftLocked(gmUserId, campaignId, promptDraftId);
            EnsureFacesAccessibleLocked(gmUserId, campaignId, draft.SelectedFaceAssetIds);
            ScanResult scan = ScanPrompt(draft.GeneratedPrompt, draft.NegativePrompt, draft.Audience, draft.SelectedFaceAssetIds, gmUserId, campaignId);
            if (scan.Status != "pass")
            {
                throw new InvalidOperationException("prompt privacy scan must pass before render approval.");
            }

            int units = draft.EstimatedUsage.RenderUnits;
            EnsureQuotaAvailable(gmUserId, access.Group.GroupId, campaignId, units);
            DateTimeOffset now = DateTimeOffset.UtcNow;
            PromptDraftProjection approved = draft with
            {
                PrivacyScanStatus = "pass",
                PrivacyWarnings = scan.Warnings,
                Status = "approved_for_render",
                ApprovedAtUtc = now
            };
            _store.PromptDraftsById[approved.Id] = approved;

            SessionVideoRenderJobProjection job = new(
                Id: StableId("gm-video-job", promptDraftId, now.ToUnixTimeMilliseconds().ToString(System.Globalization.CultureInfo.InvariantCulture)),
                PromptDraftId: promptDraftId,
                CampaignId: campaignId,
                SessionId: approved.SessionId,
                GmUserId: gmUserId,
                GroupId: access.Group.GroupId,
                ProviderAccountId: ProviderAccountId,
                Origin: Origin,
                VideoType: approved.VideoType,
                Audience: approved.Audience,
                Status: "usage_reserved",
                RenderUnitsEstimated: units,
                RenderUnitsReserved: units,
                RenderUnitsConsumed: 0,
                ProviderJobId: null,
                AssetIds: Array.Empty<string>(),
                CreatedAtUtc: now,
                UpdatedAtUtc: now);
            _store.JobsById[job.Id] = job;
            AddLedgerLocked(gmUserId, access.Group.GroupId, campaignId, job.Id, "reserve", units, "GM approved prompt for render.", gmUserId, now);
            _store.PersistLocked();
            return job;
        }
    }

    public SessionVideoRenderJobProjection StartApprovedRender(string gmUserId, string campaignId, string jobId)
    {
        EnsureCampaignAccess(gmUserId, campaignId, requireManage: true);
        lock (_store.Gate)
        {
            if (!_store.JobsById.TryGetValue(jobId, out SessionVideoRenderJobProjection? job) || !BelongsTo(gmUserId, campaignId, job))
            {
                throw new KeyNotFoundException($"Unknown video render job: {jobId}");
            }

            PromptDraftProjection draft = RequireDraftLocked(gmUserId, campaignId, job.PromptDraftId);
            if (draft.Status != "approved_for_render")
            {
                throw new InvalidOperationException("render cannot start before explicit GM prompt approval.");
            }

            DateTimeOffset now = DateTimeOffset.UtcNow;
            SessionVideoRenderJobProjection updated = job with
            {
                Status = "queued",
                ProviderJobId = StableId("magicfit-session", job.Id),
                UpdatedAtUtc = now
            };
            _store.JobsById[updated.Id] = updated;
            _store.PersistLocked();
            return updated;
        }
    }

    public TablePulseMediaPacketProjection BuildTablePulseMediaPacket(
        string gmUserId,
        string campaignId,
        string sessionId,
        CreatePromptDraftRequest request,
        string heatSummary,
        string factionSummary,
        string locationAlias)
    {
        EnsureCampaignAccess(gmUserId, campaignId, requireManage: true);
        IReadOnlyList<string> faces = NormalizeIds(request.SelectedFaceAssetIds);
        lock (_store.Gate)
        {
            EnsureFacesAccessibleLocked(gmUserId, campaignId, faces);
            var packet = new TablePulseMediaPacketProjection(
                CampaignId: campaignId,
                GmUserId: gmUserId,
                SessionId: NormalizeOptional(sessionId),
                Audience: NormalizeAudience(request.Audience),
                VideoType: NormalizeVideoType(request.VideoType),
                AllowedFacts: NormalizeFacts(request.AllowedFacts),
                ForbiddenFacts: NormalizeFacts(request.ForbiddenFacts),
                HeatSummary: PublicSafe(heatSummary),
                FactionSummary: PublicSafe(factionSummary),
                LocationAlias: PublicSafe(locationAlias),
                CastAssetIds: faces,
                Tone: NormalizeOptional(request.Tone) ?? "tactical security report",
                SpoilerLevel: NormalizeSpoilerLevel(request.SpoilerLevel),
                PrivacyScanStatus: "pass");
            _store.TablePulsePackets.Add(packet);
            _store.PersistLocked();
            return packet;
        }
    }

    public IReadOnlyList<SessionVideoRenderJobProjection> ListSessionVideos(string gmUserId, string campaignId, string sessionId)
    {
        EnsureCampaignAccess(gmUserId, campaignId, requireManage: true);
        lock (_store.Gate)
        {
            return _store.JobsById.Values
                .Where(job => BelongsTo(gmUserId, campaignId, job) && string.Equals(job.SessionId, sessionId, StringComparison.OrdinalIgnoreCase))
                .OrderByDescending(job => job.CreatedAtUtc)
                .ToArray();
        }
    }

    public GmVideoUsageSummaryProjection GetUsage(string gmUserId, string campaignId)
    {
        CampaignAccess access = EnsureCampaignAccess(gmUserId, campaignId, requireManage: true);
        lock (_store.Gate)
        {
            return BuildUsageSummary(gmUserId, access.Group.GroupId, campaignId);
        }
    }

    internal bool CanAccessFaceForGate(string gmUserId, string campaignId, string faceId)
    {
        lock (_store.Gate)
        {
            return _store.FacesById.TryGetValue(faceId, out FaceAssetProjection? face) && CanAccessFace(gmUserId, campaignId, face);
        }
    }

    internal IReadOnlyList<RenderUsageLedgerEntryProjection> LedgerForGate()
    {
        lock (_store.Gate)
        {
            return _store.UsageLedger.ToArray();
        }
    }

    private PromptDraftProjection RequireDraftLocked(string gmUserId, string campaignId, string promptDraftId)
    {
        if (!_store.PromptDraftsById.TryGetValue(promptDraftId, out PromptDraftProjection? draft) || !BelongsTo(gmUserId, campaignId, draft))
        {
            throw new KeyNotFoundException($"Unknown prompt draft: {promptDraftId}");
        }

        return draft;
    }

    private void AddPromptVersionLocked(PromptDraftProjection draft, string editorUserId)
    {
        int nextVersion = _store.PromptVersions.Count(item => string.Equals(item.PromptDraftId, draft.Id, StringComparison.OrdinalIgnoreCase)) + 1;
        _store.PromptVersions.Add(new PromptVersionProjection(
            PromptDraftId: draft.Id,
            VersionNumber: nextVersion,
            EditorUserId: editorUserId,
            PromptTextHash: Hash(draft.GeneratedPrompt),
            NegativePromptHash: Hash(draft.NegativePrompt),
            PrivacyScanStatus: draft.PrivacyScanStatus,
            UsageEstimate: draft.EstimatedUsage,
            CreatedAtUtc: DateTimeOffset.UtcNow));
    }

    private void EnsureFacesAccessibleLocked(string gmUserId, string campaignId, IReadOnlyList<string> faceIds)
    {
        foreach (string faceId in faceIds)
        {
            if (!_store.FacesById.TryGetValue(faceId, out FaceAssetProjection? face) || !CanAccessFace(gmUserId, campaignId, face))
            {
                throw new CommunityAccessDeniedException("Selected cast face is not available to this GM/campaign.");
            }
        }
    }

    private bool CanAccessFace(string gmUserId, string campaignId, FaceAssetProjection face)
        => string.Equals(face.VisibilityScope, "official_template", StringComparison.OrdinalIgnoreCase)
            || string.Equals(face.OwnerGmUserId, gmUserId, StringComparison.OrdinalIgnoreCase)
            || (string.Equals(face.CampaignId, campaignId, StringComparison.OrdinalIgnoreCase)
                && face.AllowedUserIds.Any(id => string.Equals(id, gmUserId, StringComparison.OrdinalIgnoreCase)));

    private CampaignAccess EnsureCampaignAccess(string gmUserId, string campaignId, bool requireManage)
    {
        string normalizedCampaignId = NormalizeRequired(campaignId, nameof(campaignId));
        string normalizedUserId = NormalizeRequired(gmUserId, nameof(gmUserId));
        lock (_communityStore.Gate)
        {
            if (!_communityStore.CampaignsById.TryGetValue(normalizedCampaignId, out BoostCampaignDto? campaign))
            {
                throw new KeyNotFoundException($"Unknown campaign: {normalizedCampaignId}");
            }

            if (!_communityStore.GroupsById.TryGetValue(campaign.GroupId, out GroupDto? group))
            {
                throw new KeyNotFoundException($"Unknown group for campaign: {normalizedCampaignId}");
            }

            GroupMembershipDto? membership = group.Memberships.FirstOrDefault(member => string.Equals(member.UserId, normalizedUserId, StringComparison.OrdinalIgnoreCase));
            if (membership is null)
            {
                throw new CommunityAccessDeniedException("Current account is not a member of this campaign group.");
            }

            if (requireManage && !CanManageFoundry(membership.Role))
            {
                throw new CommunityAccessDeniedException("Current account must be an owner, organizer, admin, manager, or gm to use the Session Video Foundry.");
            }

            return new CampaignAccess(campaign, group, membership);
        }
    }

    private GmVideoUsageSummaryProjection BuildUsageSummary(string gmUserId, string groupId, string campaignId)
    {
        int gmConsumed = SumLedger("consume", entry => string.Equals(entry.GmUserId, gmUserId, StringComparison.OrdinalIgnoreCase));
        int groupConsumed = SumLedger("consume", entry => string.Equals(entry.GroupId, groupId, StringComparison.OrdinalIgnoreCase));
        int campaignConsumed = SumLedger("consume", entry => string.Equals(entry.CampaignId, campaignId, StringComparison.OrdinalIgnoreCase));
        int gmReserved = SumLedger("reserve", entry => string.Equals(entry.GmUserId, gmUserId, StringComparison.OrdinalIgnoreCase));
        int groupReserved = SumLedger("reserve", entry => string.Equals(entry.GroupId, groupId, StringComparison.OrdinalIgnoreCase));
        int campaignReserved = SumLedger("reserve", entry => string.Equals(entry.CampaignId, campaignId, StringComparison.OrdinalIgnoreCase));
        return new GmVideoUsageSummaryProjection(
            GmUserId: gmUserId,
            GroupId: groupId,
            CampaignId: campaignId,
            GmMonthlyLimit: GetInt("CHUMMER_GM_VIDEO_QUOTA_PER_GM", 20),
            GroupMonthlyLimit: GetInt("CHUMMER_GM_VIDEO_QUOTA_PER_GROUP", 60),
            CampaignMonthlyLimit: GetInt("CHUMMER_GM_VIDEO_QUOTA_PER_CAMPAIGN", 30),
            GmMonthlyConsumed: gmConsumed,
            GroupMonthlyConsumed: groupConsumed,
            CampaignMonthlyConsumed: campaignConsumed,
            GmMonthlyReserved: gmReserved,
            GroupMonthlyReserved: groupReserved,
            CampaignMonthlyReserved: campaignReserved);
    }

    private int SumLedger(string eventType, Func<RenderUsageLedgerEntryProjection, bool> predicate)
        => _store.UsageLedger
            .Where(entry => string.Equals(entry.ProviderAccountId, ProviderAccountId, StringComparison.OrdinalIgnoreCase)
                && string.Equals(entry.EventType, eventType, StringComparison.OrdinalIgnoreCase)
                && predicate(entry))
            .Sum(entry => entry.Units);

    private GmVideoUsageEstimateProjection BuildUsageEstimate(string gmUserId, string groupId, string campaignId, int units, int durationSeconds)
    {
        GmVideoUsageSummaryProjection usage = BuildUsageSummary(gmUserId, groupId, campaignId);
        return new GmVideoUsageEstimateProjection(
            RenderUnits: units,
            DurationPreset: DurationPreset(durationSeconds),
            QueueSlot: "standard",
            GmMonthlyRemaining: Math.Max(0, usage.GmMonthlyLimit - usage.GmMonthlyConsumed - usage.GmMonthlyReserved),
            CampaignMonthlyRemaining: Math.Max(0, usage.CampaignMonthlyLimit - usage.CampaignMonthlyConsumed - usage.CampaignMonthlyReserved),
            GroupMonthlyRemaining: Math.Max(0, usage.GroupMonthlyLimit - usage.GroupMonthlyConsumed - usage.GroupMonthlyReserved));
    }

    private void EnsureQuotaAvailable(string gmUserId, string groupId, string campaignId, int units)
    {
        GmVideoUsageSummaryProjection usage = BuildUsageSummary(gmUserId, groupId, campaignId);
        if (usage.GmMonthlyLimit - usage.GmMonthlyConsumed - usage.GmMonthlyReserved < units
            || usage.GroupMonthlyLimit - usage.GroupMonthlyConsumed - usage.GroupMonthlyReserved < units
            || usage.CampaignMonthlyLimit - usage.CampaignMonthlyConsumed - usage.CampaignMonthlyReserved < units)
        {
            throw new InvalidOperationException("GM session video render quota is exhausted.");
        }
    }

    private void AddLedgerLocked(string gmUserId, string groupId, string campaignId, string? renderJobId, string eventType, int units, string reason, string createdBy, DateTimeOffset now)
    {
        _store.UsageLedger.Add(new RenderUsageLedgerEntryProjection(
            Id: StableId("gm-video-ledger", eventType, gmUserId, now.ToUnixTimeMilliseconds().ToString(System.Globalization.CultureInfo.InvariantCulture)),
            GmUserId: gmUserId,
            GroupId: groupId,
            CampaignId: campaignId,
            RenderJobId: renderJobId,
            ProviderAccountId: ProviderAccountId,
            EventType: eventType,
            Units: units,
            Reason: reason,
            CreatedAtUtc: now,
            CreatedBy: createdBy));
    }

    private string BuildPrompt(string campaignId, string? sessionId, CreatePromptDraftRequest request, IReadOnlyList<string> faceIds)
    {
        string audience = NormalizeAudience(request.Audience);
        string safeFacts = string.Join("; ", NormalizeFacts(request.AllowedFacts).Select(PublicSafe));
        string forbidden = string.Join("; ", NormalizeFacts(request.ForbiddenFacts).Select(PublicSafe));
        string cast = faceIds.Count == 0 ? "no recurring face reference" : $"{faceIds.Count} private GM cast reference(s)";
        return $"Create a {Math.Clamp(request.DurationSeconds, 8, 75)} second {NormalizeVideoType(request.VideoType)} for a Chummer6 campaign session. Audience: {audience}. Spoiler level: {NormalizeSpoilerLevel(request.SpoilerLevel)}. Tone: {NormalizeOptional(request.Tone) ?? "noir"}. Campaign: {PublicSafe(campaignId)}. Session: {PublicSafe(sessionId ?? "campaign-wide")}. Use {cast}. Allowed facts: {safeFacts}. Do not reveal: {forbidden}. Style: cinematic cyberpunk tabletop, metahuman cast where appropriate, visible AR overlays and cyberware, generic original setting details only.";
    }

    private ScanResult ScanPrompt(string prompt, string negativePrompt, string audience, IReadOnlyList<string> faceIds, string gmUserId, string campaignId)
    {
        List<string> warnings = new();
        if (EmailRegex.IsMatch(prompt))
        {
            warnings.Add("prompt_contains_email_or_private_contact");
        }

        foreach (string fragment in ForbiddenPromptFragments)
        {
            if (prompt.Contains(fragment, StringComparison.OrdinalIgnoreCase))
            {
                warnings.Add($"prompt_contains_forbidden_fragment:{fragment}");
            }
        }

        foreach (string faceId in faceIds)
        {
            if (!_store.FacesById.TryGetValue(faceId, out FaceAssetProjection? face) || !CanAccessFace(gmUserId, campaignId, face))
            {
                warnings.Add("prompt_references_inaccessible_face");
            }
            else if (NormalizeAudience(audience) == "public_share" && !face.PublicShareAllowed)
            {
                warnings.Add("public_share_uses_private_face");
            }
        }

        if (NormalizeAudience(audience) == "public_share" && prompt.Contains("gm-only", StringComparison.OrdinalIgnoreCase))
        {
            warnings.Add("public_share_contains_gm_only_marker");
        }

        return new ScanResult(warnings.Count == 0 ? "pass" : "fail", warnings);
    }

    private static IReadOnlyList<string> BuildPrivacyWarnings(string audience, IReadOnlyList<string> faceIds)
    {
        List<string> warnings = ["MagicFit receives only the GM-approved prompt after approval."];
        if (faceIds.Count > 0)
        {
            warnings.Add($"{faceIds.Count} private cast face reference(s) selected.");
        }

        if (NormalizeAudience(audience) == "public_share")
        {
            warnings.Add("Public share requires the strictest privacy scan and explicit GM opt-in.");
        }

        return warnings;
    }

    private bool IsSessionAccountConfigured()
        => !string.IsNullOrWhiteSpace(_configuration["CHUMMER_EA_MAGICFIT_EMAIL"])
            || File.Exists("/docker/EA/.env");

    private int GetInt(string key, int fallback)
        => int.TryParse(_configuration[key], out int value) && value > 0 ? value : fallback;

    private static int EstimateUnits(int durationSeconds)
        => Math.Clamp(durationSeconds, 8, 75) switch
        {
            <= 12 => 1,
            <= 35 => 2,
            _ => 4
        };

    private static string DurationPreset(int durationSeconds)
        => Math.Clamp(durationSeconds, 8, 75) switch
        {
            <= 12 => "short_alert",
            <= 35 => "standard_scene",
            _ => "extended_recap"
        };

    private static bool BelongsTo(string gmUserId, string campaignId, PromptDraftProjection draft)
        => string.Equals(draft.GmUserId, gmUserId, StringComparison.OrdinalIgnoreCase)
            && string.Equals(draft.CampaignId, campaignId, StringComparison.OrdinalIgnoreCase);

    private static bool BelongsTo(string gmUserId, string campaignId, SessionVideoRenderJobProjection job)
        => string.Equals(job.GmUserId, gmUserId, StringComparison.OrdinalIgnoreCase)
            && string.Equals(job.CampaignId, campaignId, StringComparison.OrdinalIgnoreCase)
            && string.Equals(job.Origin, Origin, StringComparison.OrdinalIgnoreCase)
            && string.Equals(job.ProviderAccountId, ProviderAccountId, StringComparison.OrdinalIgnoreCase);

    private static bool CanManageFoundry(string role)
        => role.Equals("owner", StringComparison.OrdinalIgnoreCase)
            || role.Equals("organizer", StringComparison.OrdinalIgnoreCase)
            || role.Equals("admin", StringComparison.OrdinalIgnoreCase)
            || role.Equals("manager", StringComparison.OrdinalIgnoreCase)
            || role.Equals("gm", StringComparison.OrdinalIgnoreCase);

    private static string NormalizeRequired(string? value, string name)
        => string.IsNullOrWhiteSpace(value) ? throw new ArgumentException($"{name} is required.") : value.Trim();

    private static string? NormalizeOptional(string? value)
        => string.IsNullOrWhiteSpace(value) ? null : value.Trim();

    private static IReadOnlyList<string> NormalizeIds(IReadOnlyList<string>? values)
        => (values ?? Array.Empty<string>()).Select(NormalizeOptional).Where(static item => item is not null).Select(static item => item!).Distinct(StringComparer.OrdinalIgnoreCase).ToArray();

    private static IReadOnlyList<string> NormalizeFacts(IReadOnlyList<string>? facts)
        => (facts ?? Array.Empty<string>()).Select(PublicSafe).Where(static item => item.Length > 0).Distinct(StringComparer.OrdinalIgnoreCase).ToArray();

    private static IReadOnlyList<string> NormalizeTags(IReadOnlyList<string>? tags)
        => (tags ?? Array.Empty<string>()).Select(static item => item.Trim().ToLowerInvariant()).Where(static item => item.Length > 0).Distinct(StringComparer.OrdinalIgnoreCase).ToArray();

    private static string NormalizeMetatype(string? metatype)
        => (NormalizeOptional(metatype)?.ToLowerInvariant()) switch
        {
            "human" or "elf" or "ork" or "dwarf" or "troll" or "other" => NormalizeOptional(metatype)!.ToLowerInvariant(),
            _ => "unknown"
        };

    private static string NormalizeSourceType(string? sourceType)
        => (NormalizeOptional(sourceType)?.ToLowerInvariant()) switch
        {
            "ai_generated" or "user_uploaded_reference" or "player_character_likeness" or "stock_or_official_template" or "provider_generated_from_prompt" => NormalizeOptional(sourceType)!.ToLowerInvariant(),
            _ => throw new ArgumentException("unsupported face source type.")
        };

    private static string NormalizeVisibilityScope(string? visibility)
        => (NormalizeOptional(visibility)?.ToLowerInvariant()) switch
        {
            "private_gm" or "campaign_shared" or "co_gm_shared" or "official_template" => NormalizeOptional(visibility)!.ToLowerInvariant(),
            _ => "private_gm"
        };

    private static string NormalizeConsent(string sourceType, string? consent)
    {
        string normalized = NormalizeOptional(consent)?.ToLowerInvariant() ?? "not_required";
        if ((sourceType == "user_uploaded_reference" || sourceType == "player_character_likeness") && normalized != "attested")
        {
            throw new ArgumentException("uploaded or player likeness faces require attested consent.");
        }

        return normalized is "not_required" or "attested" or "revoked" or "missing" ? normalized : "missing";
    }

    private static string NormalizeVideoType(string? value)
        => (NormalizeOptional(value)?.ToLowerInvariant().Replace('-', '_')) switch
        {
            "player_teaser" or "pre_session_teaser" => "player_teaser",
            "mr_johnson_briefing" => "mr_johnson_briefing",
            "location_mood_clip" => "location_mood_clip",
            "faction_warning" or "faction_dispatch" => "faction_dispatch",
            "newsreel" or "aftermath_newsreel" => "newsreel",
            "security_breach_report" => "security_breach_report",
            "matrix_alert" => "matrix_alert",
            "astral_disturbance" or "astral_disturbance_report" => "astral_disturbance_report",
            "post_session_recap" or "previously_on_recap" => "post_session_recap",
            _ => "player_teaser"
        };

    private static string NormalizeAudience(string? value)
        => (NormalizeOptional(value)?.ToLowerInvariant()) switch
        {
            "gm_only" or "campaign_players" or "selected_players" or "faction_members" or "public_share" => NormalizeOptional(value)!.ToLowerInvariant(),
            _ => "gm_only"
        };

    private static string NormalizeSpoilerLevel(string? value)
        => (NormalizeOptional(value)?.ToLowerInvariant()) switch
        {
            "none" or "mild" or "known_table_facts" or "gm_secret" => NormalizeOptional(value)!.ToLowerInvariant(),
            _ => "none"
        };

    private static string PublicSafe(string? value)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return string.Empty;
        }

        string result = EmailRegex.Replace(value.Trim(), "[redacted email]");
        result = result.Replace("Renraku", "a corporation", StringComparison.OrdinalIgnoreCase)
            .Replace("Ares", "a corporation", StringComparison.OrdinalIgnoreCase)
            .Replace("Aztechnology", "a corporation", StringComparison.OrdinalIgnoreCase)
            .Replace("Saeder-Krupp", "a corporation", StringComparison.OrdinalIgnoreCase)
            .Replace("Shadowrun", "cyberpunk tabletop", StringComparison.OrdinalIgnoreCase);
        return result.Length <= 400 ? result : result[..400];
    }

    private static string StableId(string prefix, params string[] parts)
        => $"{prefix}-{Hash(string.Join("::", parts))[..16]}";

    private static string Slug(string value)
        => Regex.Replace(value.Trim().ToLowerInvariant(), @"[^a-z0-9]+", "-").Trim('-');

    private static string Hash(string value)
        => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(value))).ToLowerInvariant();

    private sealed record CampaignAccess(BoostCampaignDto Campaign, GroupDto Group, GroupMembershipDto Membership);

    private sealed record ScanResult(string Status, IReadOnlyList<string> Warnings);
}
