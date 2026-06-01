using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using Chummer.Campaign.Contracts;
using Chummer.Run.Contracts.Boosters;
using Chummer.Run.Contracts.Community;

namespace Chummer.Run.Api.Services.Community;

public sealed class PromptFoundryService
{
    public const string Provider = "PromptArchitects";
    public const string AccountId = "prompt_architects_tier4_prompt_foundry";

    private static readonly Regex EmailRegex = new(@"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", RegexOptions.IgnoreCase | RegexOptions.Compiled);
    private static readonly string[] SourcebookBlockers =
    [
        "sourcebook prose",
        "sourcebook text",
        "copy the rulebook",
        "quote the rulebook",
        "full rules text",
        "official source page",
        "page reference text"
    ];

    private static readonly string[] PrivateDataBlockers =
    [
        "gm secret",
        "gm-only",
        "private player",
        "account id",
        "email address",
        "real name",
        "provider personal context",
        "other gm asset"
    ];

    private readonly PromptFoundryStore _store;
    private readonly CommunityStore _communityStore;
    private readonly IConfiguration _configuration;

    public PromptFoundryService(PromptFoundryStore store, CommunityStore communityStore, IConfiguration configuration)
    {
        _store = store;
        _communityStore = communityStore;
        _configuration = configuration;
        EnsureSeedTemplates();
    }

    public PromptFoundryHomeProjection GetHome(string userId, string? campaignId = null)
    {
        lock (_store.Gate)
        {
            IReadOnlyList<PromptFoundryDraftProjection> drafts = _store.DraftsById.Values
                .Where(draft => CanSeeDraft(userId, campaignId, draft))
                .OrderByDescending(draft => draft.CreatedAtUtc)
                .ToArray();
            return new PromptFoundryHomeProjection(
                Provider: BuildProviderVerification(),
                Templates: _store.TemplatesById.Values.OrderBy(static item => item.Name, StringComparer.OrdinalIgnoreCase).ToArray(),
                Drafts: drafts,
                UsageLedger: _store.UsageLedger.Where(entry => string.Equals(entry.UserId, userId, StringComparison.OrdinalIgnoreCase)).ToArray(),
                RequiredModes: new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase)
                {
                    ["template_seed_mode"] = "enabled_safe_default",
                    ["operator_assist_mode"] = BuildProviderVerification().IntegrationModeAllowed["operator_assist"] ? "enabled" : "disabled_provider_unverified",
                    ["runtime_gm_assist_mode"] = BuildProviderVerification().IntegrationModeAllowed["runtime_gm_assist"] ? "enabled" : "disabled_pending_api_mcp_privacy_export_proof"
                });
        }
    }

    public PromptArchitectsProviderVerificationProjection BuildProviderVerification()
    {
        bool accountVerified = ReadBoolean("PROMPT_ARCHITECTS_TIER4_VERIFIED", true);
        bool apiAvailable = ReadBoolean("PROMPT_ARCHITECTS_API_AVAILABLE", false);
        bool mcpVerified = ReadBoolean("PROMPT_ARCHITECTS_MCP_VERIFIED", false);
        bool exportAvailable = ReadBoolean("PROMPT_ARCHITECTS_EXPORT_AVAILABLE", true);
        bool importAvailable = ReadBoolean("PROMPT_ARCHITECTS_IMPORT_AVAILABLE", false);
        bool retentionReviewed = ReadBoolean("PROMPT_ARCHITECTS_DATA_RETENTION_REVIEWED", false);
        bool teamPermissionsReviewed = ReadBoolean("PROMPT_ARCHITECTS_TEAM_PERMISSIONS_REVIEWED", true);
        bool runtimeAllowed = accountVerified && (apiAvailable || mcpVerified) && exportAvailable && retentionReviewed && teamPermissionsReviewed;

        return new PromptArchitectsProviderVerificationProjection(
            Service: "Prompt Architects",
            Plan: "License Tier 4",
            AccountVerified: accountVerified,
            LicenseStatus: accountVerified ? "verified_from_ltd_inventory" : "pending",
            TeamMembersLimit: 20,
            TotalPromptsPerMonth: 20000,
            PromptHistoryLimit: "unlimited",
            PersonalContextLimit: "unlimited",
            JsonPromptSupport: true,
            ImagePromptGeneration: true,
            ImagePromptLibrary: true,
            VideoPromptLibrary: true,
            ChromeExtension: true,
            HotkeyCommands: true,
            UniversalSidebarUi: true,
            TemplateLibraryTags: true,
            RefineMode: true,
            ShortenMode: true,
            McpConnectionClaimed: true,
            ApiAvailable: apiAvailable,
            ExportAvailable: exportAvailable,
            ImportAvailable: importAvailable,
            BulkTemplateExport: exportAvailable,
            WebhookAvailable: false,
            AuditLogAvailable: false,
            TeamWorkspacePermissions: teamPermissionsReviewed ? "reviewed_collection_scoping_required" : "pending_review",
            DataRetentionReviewed: retentionReviewed ? "reviewed" : "pending_runtime_review",
            ProviderSupportContact: "tracked_in_executive_assistant_ltd_inventory",
            IntegrationModeAllowed: new Dictionary<string, bool>(StringComparer.OrdinalIgnoreCase)
            {
                ["template_seed"] = true,
                ["operator_assist"] = accountVerified,
                ["runtime_gm_assist"] = runtimeAllowed
            },
            Status: accountVerified ? "verified" : "pilot");
    }

    public IReadOnlyList<PromptTemplateProjection> SyncSeedTemplates(string operatorUserId)
    {
        lock (_store.Gate)
        {
            EnsureSeedTemplatesLocked(DateTimeOffset.UtcNow);
            _store.PersistLocked();
            return _store.TemplatesById.Values.OrderBy(static item => item.Name, StringComparer.OrdinalIgnoreCase).ToArray();
        }
    }

    public PromptFoundryDraftProjection CreateDraft(string userId, PromptFoundryCreateDraftRequest request)
    {
        ArgumentNullException.ThrowIfNull(request);
        if (!string.IsNullOrWhiteSpace(request.CampaignId))
        {
            EnsureCampaignAccess(userId, request.CampaignId, requireManage: true);
        }

        lock (_store.Gate)
        {
            PromptTemplateProjection template = RequireTemplateLocked(request.TemplateId);
            string mode = NormalizeProviderMode(request.ProviderMode);
            if (mode == PromptFoundryProviderModes.PromptArchitectsRuntime && !BuildProviderVerification().IntegrationModeAllowed["runtime_gm_assist"])
            {
                mode = PromptFoundryProviderModes.LocalTemplate;
            }

            DateTimeOffset now = DateTimeOffset.UtcNow;
            string basePrompt = BuildBasePrompt(template, request);
            string enhanced = mode is PromptFoundryProviderModes.PromptArchitectsTemplateSeed or PromptFoundryProviderModes.PromptArchitectsOperatorAssist
                ? EnhanceFromSeedTemplate(template, request, basePrompt)
                : basePrompt;
            ScanResult scan = ScanPrompt(enhanced, template.NegativePrompt, request, mode);
            PromptFoundryDraftProjection draft = new(
                Id: StableId("prompt-foundry-draft", userId, request.CampaignId ?? "operator", now.ToUnixTimeMilliseconds().ToString(System.Globalization.CultureInfo.InvariantCulture)),
                TemplateId: template.Id,
                CampaignId: NormalizeOptional(request.CampaignId),
                GroupId: NormalizeOptional(request.GroupId),
                GmUserId: NormalizeOptional(request.CampaignId) is null ? null : userId,
                OperatorUserId: NormalizeOptional(request.CampaignId) is null ? userId : null,
                ProviderMode: mode,
                BasePrompt: basePrompt,
                EnhancedPrompt: enhanced,
                NegativePrompt: template.NegativePrompt,
                DiffSummary: BuildDiffSummary(basePrompt, enhanced),
                PrivacyWarnings: scan.Warnings,
                PrivacyScanStatus: scan.Status,
                QualityScore: mode == PromptFoundryProviderModes.LocalTemplate ? 0.72m : 0.88m,
                PromptUnitsEstimated: EstimatePromptUnits(basePrompt, enhanced),
                Status: "draft",
                CreatedAtUtc: now,
                UpdatedAtUtc: now,
                ApprovedAtUtc: null);
            _store.DraftsById[draft.Id] = draft;
            AddVersionLocked(draft, userId, now);
            AddUsageLocked(draft, userId, "estimate", draft.PromptUnitsEstimated, "Prompt Architects prompt-unit estimate only; no render units consumed.", now);
            _store.PersistLocked();
            return draft;
        }
    }

    public PromptFoundryDraftProjection EditDraft(string userId, string promptDraftId, PromptFoundryEditDraftRequest request)
    {
        ArgumentNullException.ThrowIfNull(request);
        lock (_store.Gate)
        {
            PromptFoundryDraftProjection draft = RequireDraftLocked(userId, null, promptDraftId);
            var scanRequest = new PromptFoundryCreateDraftRequest(
                TemplateId: draft.TemplateId,
                CampaignId: draft.CampaignId,
                GroupId: draft.GroupId,
                VideoType: null,
                Audience: "campaign_players",
                Tone: "edited",
                PublicSafeSummary: request.EnhancedPrompt,
                LocationAlias: "edited-draft");
            ScanResult scan = ScanPrompt(request.EnhancedPrompt, request.NegativePrompt, scanRequest, draft.ProviderMode);
            DateTimeOffset now = DateTimeOffset.UtcNow;
            PromptFoundryDraftProjection updated = draft with
            {
                EnhancedPrompt = NormalizeRequired(request.EnhancedPrompt, "enhanced_prompt"),
                NegativePrompt = NormalizeRequired(request.NegativePrompt, "negative_prompt"),
                DiffSummary = BuildDiffSummary(draft.BasePrompt, request.EnhancedPrompt),
                PrivacyWarnings = scan.Warnings,
                PrivacyScanStatus = scan.Status,
                Status = "reviewed",
                UpdatedAtUtc = now,
                ApprovedAtUtc = null
            };
            _store.DraftsById[updated.Id] = updated;
            AddVersionLocked(updated, userId, now);
            _store.PersistLocked();
            return updated;
        }
    }

    public PromptFoundryDraftProjection ApproveDraft(string userId, string promptDraftId, PromptFoundryApproveDraftRequest request)
    {
        ArgumentNullException.ThrowIfNull(request);
        if (!request.Approved)
        {
            throw new ArgumentException("explicit prompt approval is required.");
        }

        lock (_store.Gate)
        {
            PromptFoundryDraftProjection draft = RequireDraftLocked(userId, null, promptDraftId);
            if (draft.PrivacyScanStatus != "pass")
            {
                throw new InvalidOperationException("prompt privacy scan must pass before approval.");
            }

            DateTimeOffset now = DateTimeOffset.UtcNow;
            PromptFoundryDraftProjection approved = draft with
            {
                Status = "approved",
                ApprovedAtUtc = now,
                UpdatedAtUtc = now
            };
            _store.DraftsById[approved.Id] = approved;
            AddUsageLocked(approved, userId, "consume", approved.PromptUnitsEstimated, "Approved prompt draft for downstream Chummer-owned render or support flow.", now);
            _store.PersistLocked();
            return approved;
        }
    }

    public string HumanizeRulesSafeSupport(string safeSummary, IReadOnlyList<string> ruleFactIds, IReadOnlyList<string> explainReceiptIds)
    {
        string normalized = NormalizeRequired(safeSummary, nameof(safeSummary));
        foreach (string blocker in SourcebookBlockers)
        {
            if (normalized.Contains(blocker, StringComparison.OrdinalIgnoreCase))
            {
                throw new InvalidOperationException("sourcebook prose cannot be sent to Prompt Architects or stored in a rules-safe prompt.");
            }
        }

        string facts = string.Join(", ", ruleFactIds.Select(NormalizeRequiredToken).Distinct(StringComparer.OrdinalIgnoreCase));
        string receipts = string.Join(", ", explainReceiptIds.Select(NormalizeRequiredToken).Distinct(StringComparer.OrdinalIgnoreCase));
        return $"Plain-language support wording: {normalized}. Preserve rule fact ids [{facts}] and explain receipt ids [{receipts}]. Do not add mechanics, quotes, page text, or rules truth.";
    }

    internal IReadOnlyList<PromptFoundryVersionProjection> VersionsForGate()
    {
        lock (_store.Gate)
        {
            return _store.Versions.ToArray();
        }
    }

    private void EnsureSeedTemplates()
    {
        lock (_store.Gate)
        {
            EnsureSeedTemplatesLocked(DateTimeOffset.UtcNow);
            _store.PersistLocked();
        }
    }

    private void EnsureSeedTemplatesLocked(DateTimeOffset now)
    {
        foreach (PromptTemplateProjection template in BuildSeedTemplates(now))
        {
            _store.TemplatesById[template.Id] = template;
        }
    }

    private static IReadOnlyList<PromptTemplateProjection> BuildSeedTemplates(DateTimeOffset now)
    {
        string[] allowed = ["public_template", "product_internal_template"];
        string[] forbidden = ["gm_secret", "player_private_data", "sourcebook_text", "face_asset"];
        Dictionary<string, string> input = new(StringComparer.OrdinalIgnoreCase)
        {
            ["public_safe_summary"] = "string",
            ["tone"] = "string",
            ["duration_seconds"] = "integer",
            ["style_tags"] = "string[]"
        };
        Dictionary<string, string> output = new(StringComparer.OrdinalIgnoreCase)
        {
            ["enhanced_prompt"] = "string",
            ["negative_prompt"] = "string",
            ["diff_summary"] = "string[]"
        };
        return
        [
            Template("gm_session_video_aftermath_v1", "GM Session Video Aftermath", "gm_session_video", allowed, forbidden, input, output, "Structure a GM-approved aftermath/newsreel prompt with public-safe facts, timing beats, camera direction, AR overlay space, generic metahumans, visible cyberware, and no private campaign truth.", "No sourcebook prose, no private player data, no official logos, no direct publish, no cross-GM assets.", ["gm-video", "magicfit", "table-pulse"], now),
            Template("magicfit_video_bridge_v1", "MagicFit Video Bridge", "magicfit_video", allowed, forbidden, input, output, "Convert a Chummer media packet into a MagicFit-ready prompt with title, duration, aspect ratio, scene description, camera, character descriptors, lighting, motion, overlay room, negative prompt, and output requirements.", "No copyrighted page designs, no real corporate logos, no raw private session transcript, no sourcebook text.", ["magicfit", "video", "operator"], now),
            Template("black_ledger_newsroom_v1", "Black Ledger Newsroom", "black_ledger_newsreel", allowed, forbidden, input, output, "Create a public-safe Black Ledger newsroom/newsreel prompt from aggregate city-state consequences, faction pressure, and job seeds without leaking private tables.", "No canonical corporate marks, no private campaign labels, no sourcebook wording, no player identities.", ["black-ledger", "newsroom"], now),
            Template("faction_video_series_v1", "Faction Video Series", "faction_video_series", allowed, forbidden, input, output, "Structure a faction dispatch prompt around motive, pressure, public signal, metahuman spokesperson, AR overlays, and original faction styling.", "No official faction marks, no real-world targeting, no private GM assets, no sourcebook prose.", ["faction", "video"], now),
            Template("rules_safe_humanizer_v1", "Rules-Safe Humanizer", "rules_safe_humanizer", allowed, forbidden, input, output, "Humanize only Chummer-owned RuleFact and explain-receipt summaries. Preserve values and ids. Never invent mechanics or quote protected source text.", "No page quotes, no copied tables, no unverified mechanics, no provider rules truth.", ["support", "rules-safe"], now),
            Template("codex_audit_prompt_v1", "Codex Audit Prompt", "codex_dev_package", allowed, forbidden, input, output, "Turn a product audit objective into a strict implementation prompt with required artifacts, gates, fail conditions, and final verdict wording.", "No credentials, no private user secrets, no sourcebook prose, no provider ownership claims.", ["codex", "audit"], now),
        ];

        static PromptTemplateProjection Template(
            string id,
            string name,
            string type,
            IReadOnlyList<string> allowed,
            IReadOnlyList<string> forbidden,
            IReadOnlyDictionary<string, string> input,
            IReadOnlyDictionary<string, string> output,
            string body,
            string negative,
            IReadOnlyList<string> tags,
            DateTimeOffset now)
            => new(
                Id: id,
                Name: name,
                Type: type,
                Version: "1.0.0",
                Source: "prompt_architects_template_seed",
                SourceReceiptId: "chummer6_prompt_architects_tier4_integration_design_20260531",
                AllowedDataClasses: allowed,
                ForbiddenDataClasses: forbidden,
                InputSchema: input,
                OutputSchema: output,
                PromptBody: body,
                NegativePrompt: negative,
                Status: "approved",
                Tags: tags,
                UpdatedAtUtc: now);
    }

    private PromptTemplateProjection RequireTemplateLocked(string templateId)
    {
        string normalized = NormalizeRequired(templateId, nameof(templateId));
        if (!_store.TemplatesById.TryGetValue(normalized, out PromptTemplateProjection? template) || template.Status != "approved")
        {
            throw new KeyNotFoundException($"Unknown prompt template: {templateId}");
        }

        return template;
    }

    private PromptFoundryDraftProjection RequireDraftLocked(string userId, string? campaignId, string promptDraftId)
    {
        if (!_store.DraftsById.TryGetValue(promptDraftId, out PromptFoundryDraftProjection? draft) || !CanSeeDraft(userId, campaignId, draft))
        {
            throw new KeyNotFoundException($"Unknown prompt draft: {promptDraftId}");
        }

        return draft;
    }

    private bool CanSeeDraft(string userId, string? campaignId, PromptFoundryDraftProjection draft)
    {
        if (!string.IsNullOrWhiteSpace(draft.GmUserId))
        {
            return string.Equals(draft.GmUserId, userId, StringComparison.OrdinalIgnoreCase)
                && (string.IsNullOrWhiteSpace(campaignId) || string.Equals(draft.CampaignId, campaignId, StringComparison.OrdinalIgnoreCase));
        }

        return string.Equals(draft.OperatorUserId, userId, StringComparison.OrdinalIgnoreCase);
    }

    private CampaignAccess EnsureCampaignAccess(string userId, string campaignId, bool requireManage)
    {
        string normalizedCampaignId = NormalizeRequired(campaignId, nameof(campaignId));
        string normalizedUserId = NormalizeRequired(userId, nameof(userId));
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

            if (requireManage && membership.Role is not ("owner" or "organizer" or "admin" or "manager" or "gm"))
            {
                throw new CommunityAccessDeniedException("Current account must be able to manage prompt foundry drafts for this campaign.");
            }

            return new CampaignAccess(campaign, group, membership);
        }
    }

    private string BuildBasePrompt(PromptTemplateProjection template, PromptFoundryCreateDraftRequest request)
    {
        string summary = PublicSafe(request.PublicSafeSummary);
        string tags = string.Join(", ", (request.StyleTags ?? Array.Empty<string>()).Select(PublicSafe).Where(static item => item.Length > 0));
        string characters = string.Join(", ", (request.GenericCharacterDescriptors ?? Array.Empty<string>()).Select(PublicSafe).Where(static item => item.Length > 0));
        string faces = string.Join(", ", (request.FaceReferencePlaceholders ?? Array.Empty<string>()).Select(PublicSafe).Where(static item => item.Length > 0));
        return $"{template.PromptBody} Video type: {PublicSafe(request.VideoType ?? template.Type)}. Audience: {PublicSafe(request.Audience)}. Tone: {PublicSafe(request.Tone)}. Duration: {Math.Clamp(request.DurationSeconds, 8, 90)} seconds. Location alias: {PublicSafe(request.LocationAlias)}. Public-safe summary: {summary}. Style tags: {tags}. Generic characters: {characters}. Face placeholders: {faces}. Output format: {PublicSafe(request.OutputFormat)}.";
    }

    private static string EnhanceFromSeedTemplate(PromptTemplateProjection template, PromptFoundryCreateDraftRequest request, string basePrompt)
    {
        return string.Join(" ", [
            "Role: governed Chummer prompt foundry accelerator.",
            "Task: improve structure only; do not add facts.",
            $"Template: {template.Name} {template.Version}.",
            $"Timing: {Math.Clamp(request.DurationSeconds, 8, 90)} seconds with clear beats.",
            "Camera: establish, detail, reaction, overlay-safe close.",
            "Characters: generic cyberpunk/metahuman descriptions only; visible cyberware allowed when requested.",
            "AR overlay: reserve clean negative space for Chummer captions and receipts.",
            "Constraints: Chummer owns truth, privacy, approval, rendering, and publishing.",
            basePrompt
        ]);
    }

    private ScanResult ScanPrompt(string prompt, string negativePrompt, PromptFoundryCreateDraftRequest request, string providerMode)
    {
        List<string> warnings = new();
        string combined = $"{prompt}\n{request.PublicSafeSummary}";
        if (EmailRegex.IsMatch(combined))
        {
            warnings.Add("prompt_contains_email_or_private_contact");
        }

        foreach (string blocker in SourcebookBlockers)
        {
            if (combined.Contains(blocker, StringComparison.OrdinalIgnoreCase))
            {
                warnings.Add($"sourcebook_prose_blocker:{blocker}");
            }
        }

        foreach (string blocker in PrivateDataBlockers)
        {
            if (combined.Contains(blocker, StringComparison.OrdinalIgnoreCase))
            {
                warnings.Add($"private_data_blocker:{blocker}");
            }
        }

        if (request.FaceReferencePlaceholders?.Any(item => item.StartsWith("face_asset:", StringComparison.OrdinalIgnoreCase) || item.Contains("/", StringComparison.Ordinal)) == true)
        {
            warnings.Add("face_asset_reference_must_remain_placeholder");
        }

        if (NormalizeProviderMode(providerMode) == PromptFoundryProviderModes.PromptArchitectsRuntime && !BuildProviderVerification().IntegrationModeAllowed["runtime_gm_assist"])
        {
            warnings.Add("runtime_provider_assist_disabled_pending_api_mcp_privacy_export_proof");
        }

        return new ScanResult(warnings.Count == 0 ? "pass" : "fail", warnings);
    }

    private static IReadOnlyList<string> BuildDiffSummary(string basePrompt, string enhancedPrompt)
    {
        List<string> diff = new();
        if (!string.Equals(basePrompt, enhancedPrompt, StringComparison.Ordinal))
        {
            diff.Add("added_role_task_structure");
            diff.Add("added_timing_camera_overlay_constraints");
            diff.Add("preserved_chummer_truth_and_approval_boundary");
        }

        return diff;
    }

    private void AddVersionLocked(PromptFoundryDraftProjection draft, string editorUserId, DateTimeOffset now)
    {
        int nextVersion = _store.Versions.Count(item => string.Equals(item.PromptDraftId, draft.Id, StringComparison.OrdinalIgnoreCase)) + 1;
        _store.Versions.Add(new PromptFoundryVersionProjection(
            PromptDraftId: draft.Id,
            VersionNumber: nextVersion,
            EditorUserId: editorUserId,
            BasePromptHash: Hash(draft.BasePrompt),
            EnhancedPromptHash: Hash(draft.EnhancedPrompt ?? string.Empty),
            NegativePromptHash: Hash(draft.NegativePrompt),
            PrivacyScanStatus: draft.PrivacyScanStatus,
            CreatedAtUtc: now));
    }

    private void AddUsageLocked(PromptFoundryDraftProjection draft, string userId, string eventType, int units, string reason, DateTimeOffset now)
    {
        _store.UsageLedger.Add(new PromptUsageLedgerEntryProjection(
            Id: StableId("prompt-ledger", userId, draft.Id, eventType, now.ToUnixTimeMilliseconds().ToString(System.Globalization.CultureInfo.InvariantCulture)),
            Provider: Provider,
            AccountId: AccountId,
            UserId: userId,
            GroupId: draft.GroupId,
            CampaignId: draft.CampaignId,
            PromptDraftId: draft.Id,
            TemplateId: draft.TemplateId,
            EventType: eventType,
            Units: Math.Max(0, units),
            Reason: reason,
            CreatedAtUtc: now));
    }

    private static int EstimatePromptUnits(string basePrompt, string? enhancedPrompt)
        => Math.Max(1, (basePrompt.Length + (enhancedPrompt?.Length ?? 0) + 999) / 1000);

    private string NormalizeProviderMode(string? mode)
    {
        string normalized = string.IsNullOrWhiteSpace(mode) ? PromptFoundryProviderModes.LocalTemplate : mode.Trim();
        return normalized switch
        {
            PromptFoundryProviderModes.LocalTemplate => PromptFoundryProviderModes.LocalTemplate,
            PromptFoundryProviderModes.PromptArchitectsTemplateSeed => PromptFoundryProviderModes.PromptArchitectsTemplateSeed,
            PromptFoundryProviderModes.PromptArchitectsOperatorAssist => PromptFoundryProviderModes.PromptArchitectsOperatorAssist,
            PromptFoundryProviderModes.PromptArchitectsRuntime => PromptFoundryProviderModes.PromptArchitectsRuntime,
            _ => PromptFoundryProviderModes.LocalTemplate
        };
    }

    private static string PublicSafe(string? value)
    {
        string text = NormalizeOptional(value) ?? string.Empty;
        text = EmailRegex.Replace(text, "[private-contact]");
        text = text.Replace("Renraku", "a major corporation", StringComparison.OrdinalIgnoreCase)
            .Replace("Ares", "a security contractor", StringComparison.OrdinalIgnoreCase)
            .Replace("Aztechnology", "a megacorp", StringComparison.OrdinalIgnoreCase)
            .Replace("Mitsuhama", "an industrial group", StringComparison.OrdinalIgnoreCase);
        return text;
    }

    private static string NormalizeRequired(string? value, string name)
    {
        string? normalized = NormalizeOptional(value);
        return normalized ?? throw new ArgumentException($"{name} is required.");
    }

    private static string NormalizeRequiredToken(string value)
        => NormalizeRequired(value, "token").Replace(" ", "_", StringComparison.Ordinal);

    private static string? NormalizeOptional(string? value)
    {
        string? normalized = value?.Trim();
        return string.IsNullOrWhiteSpace(normalized) ? null : normalized;
    }

    private bool ReadBoolean(string key, bool fallback)
    {
        string? value = _configuration[key];
        if (string.IsNullOrWhiteSpace(value))
        {
            return fallback;
        }

        return value.Equals("1", StringComparison.OrdinalIgnoreCase)
            || value.Equals("true", StringComparison.OrdinalIgnoreCase)
            || value.Equals("yes", StringComparison.OrdinalIgnoreCase)
            || value.Equals("verified", StringComparison.OrdinalIgnoreCase);
    }

    private static string Hash(string value)
        => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(value))).ToLowerInvariant()[..16];

    private static string StableId(string prefix, params string[] parts)
    {
        string input = string.Join("|", parts.Select(static item => item.Trim().ToLowerInvariant()));
        return $"{prefix}_{Hash(input)}";
    }

    private sealed record ScanResult(string Status, IReadOnlyList<string> Warnings);

    private sealed record CampaignAccess(BoostCampaignDto Campaign, GroupDto Group, GroupMembershipDto Membership);
}
