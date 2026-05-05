using Chummer.Campaign.Contracts;
using Chummer.Hub.Registry.Contracts;
using Chummer.Run.Contracts.Community;
using Chummer.Run.Registry.Services;

namespace Chummer.Run.Api.Services.Community;

public sealed record CreatorPublicationRegistryProjection(
    HubDraftDetailProjection DraftDetail,
    HubPublicationReceipt? PublicationReceipt);

public sealed class CreatorPublicationRegistryBridge
{
    private readonly IHubPublicationDraftService _drafts;

    public CreatorPublicationRegistryBridge(IHubPublicationDraftService drafts)
    {
        _drafts = drafts;
    }

    public CreatorPublicationRegistryProjection GetOrCreatePublicationLane(
        HubUserDto user,
        CreatorPublicationProjection publication,
        CampaignWorkspaceProjection? workspace)
    {
        ArgumentNullException.ThrowIfNull(user);
        ArgumentNullException.ThrowIfNull(publication);

        HubPublishDraftRequest desiredDraft = BuildDraftRequest(publication, workspace);
        HubDraftDetailProjection? detail = _drafts.GetDraftDetail(publication.PublicationId);
        if (detail is null)
        {
            _drafts.CreateDraft(desiredDraft, user.UserId, preferredDraftId: publication.PublicationId);
            detail = _drafts.GetDraftDetail(publication.PublicationId);
        }
        else if (NeedsRefresh(detail, desiredDraft))
        {
            _drafts.UpdateDraft(
                publication.PublicationId,
                user.UserId,
                new HubUpdateDraftRequest(
                    Title: desiredDraft.Title,
                    Summary: desiredDraft.Summary,
                    Description: desiredDraft.Description,
                    PublisherId: desiredDraft.PublisherId));
            detail = _drafts.GetDraftDetail(publication.PublicationId);
        }

        return new CreatorPublicationRegistryProjection(
            DraftDetail: detail ?? throw new InvalidOperationException($"Registry draft '{publication.PublicationId}' could not be loaded."),
            PublicationReceipt: _drafts.GetPublicationReceipt(publication.PublicationId));
    }

    public CreatorPublicationRegistryProjection SubmitForReview(
        HubUserDto user,
        CreatorPublicationProjection publication,
        CampaignWorkspaceProjection? workspace,
        string? notes = null)
    {
        EnsureManifestAuthority(publication, workspace);
        GetOrCreatePublicationLane(user, publication, workspace);
        _drafts.SubmitProject(
            publication.PublicationId,
            user.UserId,
            new HubSubmitProjectRequest(Notes: NormalizeOptional(notes) ?? $"{publication.Title} entered governed shared-publication review."));
        return GetOrCreatePublicationLane(user, publication, workspace);
    }

    public CreatorPublicationRegistryProjection ApproveReview(
        HubUserDto user,
        CreatorPublicationProjection publication,
        CampaignWorkspaceProjection? workspace,
        string? notes = null)
    {
        EnsureManifestAuthority(publication, workspace);
        CreatorPublicationRegistryProjection current = GetOrCreatePublicationLane(user, publication, workspace);
        string caseId = current.DraftDetail.Moderation?.CaseId
            ?? throw new InvalidOperationException("There is no pending moderation case to approve.");
        _drafts.ApproveModerationCase(
            caseId,
            user.UserId,
            new HubModerationDecisionRequest(NormalizeOptional(notes) ?? $"{publication.Title} cleared governed shared-publication review."));
        return GetOrCreatePublicationLane(user, publication, workspace);
    }

    public CreatorPublicationRegistryProjection RejectReview(
        HubUserDto user,
        CreatorPublicationProjection publication,
        CampaignWorkspaceProjection? workspace,
        string? notes = null)
    {
        EnsureManifestAuthority(publication, workspace);
        CreatorPublicationRegistryProjection current = GetOrCreatePublicationLane(user, publication, workspace);
        string caseId = current.DraftDetail.Moderation?.CaseId
            ?? throw new InvalidOperationException("There is no pending moderation case to reject.");
        _drafts.RejectModerationCase(
            caseId,
            user.UserId,
            new HubModerationDecisionRequest(NormalizeOptional(notes) ?? $"{publication.Title} needs revision before governed shared-publication review can continue."));
        return GetOrCreatePublicationLane(user, publication, workspace);
    }

    public CreatorPublicationRegistryProjection Publish(
        HubUserDto user,
        CreatorPublicationProjection publication,
        CampaignWorkspaceProjection? workspace,
        string? notes = null)
    {
        EnsureManifestAuthority(publication, workspace);
        GetOrCreatePublicationLane(user, publication, workspace);
        _drafts.PublishProject(
            publication.PublicationId,
            user.UserId,
            new HubPublishProjectRequest(
                Notes: NormalizeOptional(notes) ?? $"{publication.Title} is live on governed shared-publication discovery.",
                PublisherId: user.UserId));
        return GetOrCreatePublicationLane(user, publication, workspace);
    }

    private static bool NeedsRefresh(HubDraftDetailProjection detail, HubPublishDraftRequest desired)
    {
        HubPublishDraftReceipt draft = detail.Draft;
        if (!string.Equals(draft.State, HubPublicationStates.Draft, StringComparison.OrdinalIgnoreCase))
        {
            return false;
        }

        return !string.Equals(draft.ProjectKind, desired.ProjectKind, StringComparison.OrdinalIgnoreCase)
            || !string.Equals(draft.ProjectId, desired.ProjectId, StringComparison.OrdinalIgnoreCase)
            || !string.Equals(draft.RulesetId, desired.RulesetId, StringComparison.OrdinalIgnoreCase)
            || !string.Equals(draft.Title, desired.Title, StringComparison.Ordinal)
            || !string.Equals(draft.Summary, desired.Summary, StringComparison.Ordinal)
            || !string.Equals(detail.Description, desired.Description, StringComparison.Ordinal)
            || !string.Equals(draft.PublisherId, desired.PublisherId, StringComparison.OrdinalIgnoreCase);
    }

    private static HubPublishDraftRequest BuildDraftRequest(
        CreatorPublicationProjection publication,
        CampaignWorkspaceProjection? workspace)
    {
        PublicationSafeProjection? linkedShelfEntry = ResolveLinkedShelfEntry(publication, workspace);
        return new HubPublishDraftRequest(
            ProjectKind: ResolveProjectKind(publication, linkedShelfEntry),
            ProjectId: string.IsNullOrWhiteSpace(publication.ArtifactId) ? publication.PublicationId : publication.ArtifactId,
            RulesetId: ResolveRulesetId(workspace),
            Title: publication.Title,
            Summary: publication.Summary,
            Description: BuildDescription(publication, workspace, linkedShelfEntry),
            PublisherId: null);
    }

    private static string ResolveProjectKind(CreatorPublicationProjection publication, PublicationSafeProjection? linkedShelfEntry)
    {
        string candidate = linkedShelfEntry?.Kind
            ?? publication.Kind
            ?? string.Empty;
        string normalized = candidate.Trim().ToLowerInvariant();
        return normalized switch
        {
            "replay_timeline" => nameof(HubArtifactKind.ReplayPackage),
            "session_recap" => nameof(HubArtifactKind.RecapPackage),
            "after_action_report" => nameof(HubArtifactKind.RecapPackage),
            "downtime_brief" => nameof(HubArtifactKind.RecapPackage),
            "campaign_recap" => "Campaign",
            "campaign_packet" => "Campaign",
            "dossier_card" => "Dossier",
            "runboard_packet" => "RunModule",
            _ when normalized.Contains("replay", StringComparison.Ordinal) => nameof(HubArtifactKind.ReplayPackage),
            _ when normalized.Contains("recap", StringComparison.Ordinal) => nameof(HubArtifactKind.RecapPackage),
            _ when normalized.Contains("dossier", StringComparison.Ordinal) => "Dossier",
            _ when normalized.Contains("module", StringComparison.Ordinal) => "RunModule",
            _ when normalized.Contains("runboard", StringComparison.Ordinal) => "RunModule",
            _ when normalized.Contains("primer", StringComparison.Ordinal) => "Primer",
            _ when normalized.Contains("handbook", StringComparison.Ordinal) => "Primer",
            _ when normalized.Contains("guide", StringComparison.Ordinal) => "Primer",
            _ when normalized.Contains("campaign", StringComparison.Ordinal) => "Campaign",
            _ when normalized.Contains("npc", StringComparison.Ordinal) => nameof(HubArtifactKind.NpcVault),
            _ => nameof(HubArtifactKind.BuildIdea)
        };
    }

    private static string ResolveRulesetId(CampaignWorkspaceProjection? workspace)
    {
        string candidate = workspace?.RuleEnvironment.CompatibilityFingerprint ?? workspace?.RuleEnvironment.EnvironmentId ?? string.Empty;
        if (!string.IsNullOrWhiteSpace(candidate))
        {
            foreach (string separator in new[] { ".", ":", "/", "-", "_" })
            {
                int index = candidate.IndexOf(separator, StringComparison.Ordinal);
                if (index > 0)
                {
                    return candidate[..index].Trim();
                }
            }

            return candidate.Trim();
        }

        return "sr6";
    }

    private static string BuildDescription(
        CreatorPublicationProjection publication,
        CampaignWorkspaceProjection? workspace,
        PublicationSafeProjection? linkedShelfEntry)
    {
        List<string> lines =
        [
            publication.Summary,
            $"Publication kind: {ResolvePublicationKindLabel(publication, linkedShelfEntry)}",
            $"Status: {HumanizeValue(publication.PublicationStatus, "Preview ready")}",
            $"Visibility: {HumanizeValue(publication.Visibility, "Shared")}"
        ];

        if (!string.IsNullOrWhiteSpace(publication.DiscoverySummary))
        {
            lines.Add($"Discovery: {publication.DiscoverySummary}");
        }

        if (!string.IsNullOrWhiteSpace(publication.ProvenanceSummary))
        {
            lines.Add($"Provenance: {publication.ProvenanceSummary}");
        }

        if (!string.IsNullOrWhiteSpace(publication.LineageSummary))
        {
            lines.Add($"Lineage: {publication.LineageSummary}");
        }

        if (!string.IsNullOrWhiteSpace(publication.CampaignReturnSummary))
        {
            lines.Add($"Return: {publication.CampaignReturnSummary}");
        }

        if (!string.IsNullOrWhiteSpace(workspace?.CampaignName))
        {
            lines.Add($"Campaign: {workspace.CampaignName}");
        }

        if (!string.IsNullOrWhiteSpace(linkedShelfEntry?.AuditSummary))
        {
            lines.Add($"Audit: {linkedShelfEntry.AuditSummary}");
        }

        lines.Add($"Manifest authority: {BuildManifestAuthority(publication, workspace, linkedShelfEntry)}");

        return string.Join(" ", lines.Where(static line => !string.IsNullOrWhiteSpace(line)));
    }

    private static void EnsureManifestAuthority(
        CreatorPublicationProjection publication,
        CampaignWorkspaceProjection? workspace)
    {
        PublicationSafeProjection? linkedShelfEntry = ResolveLinkedShelfEntry(publication, workspace);
        if (ResolveApprovedManifestAuditSummary(linkedShelfEntry) is null)
        {
            throw new InvalidOperationException("Creator publication moderation requires an approved manifest-backed audit receipt before submission, correction, approval, or publication.");
        }
    }

    private static PublicationSafeProjection? ResolveLinkedShelfEntry(
        CreatorPublicationProjection publication,
        CampaignWorkspaceProjection? workspace)
        => workspace?.RecapShelf.FirstOrDefault(item =>
            string.Equals(item.CreatorPublicationId, publication.PublicationId, StringComparison.OrdinalIgnoreCase)
            || (!string.IsNullOrWhiteSpace(publication.ArtifactId)
                && string.Equals(item.ArtifactId, publication.ArtifactId, StringComparison.OrdinalIgnoreCase)));

    private static string BuildManifestAuthority(
        CreatorPublicationProjection publication,
        CampaignWorkspaceProjection? workspace,
        PublicationSafeProjection? linkedShelfEntry)
    {
        string? approvedAuditSummary = ResolveApprovedManifestAuditSummary(linkedShelfEntry);
        if (approvedAuditSummary is not null)
        {
            string workspaceId = workspace?.WorkspaceId ?? "unknown-workspace";
            string artifactId = string.IsNullOrWhiteSpace(publication.ArtifactId) ? publication.PublicationId : publication.ArtifactId;
            return $"approved-shared-publication-manifest; workspace:{workspaceId}; artifact:{artifactId}; audit:{approvedAuditSummary}";
        }

        return "missing-audit-receipt";
    }

    private static string? ResolveApprovedManifestAuditSummary(PublicationSafeProjection? linkedShelfEntry)
    {
        string? auditSummary = NormalizeOptional(linkedShelfEntry?.AuditSummary);
        return auditSummary is not null
            && auditSummary.Contains("manifest-authority-backed", StringComparison.OrdinalIgnoreCase)
            ? auditSummary
            : null;
    }

    private static string ResolvePublicationKindLabel(
        CreatorPublicationProjection publication,
        PublicationSafeProjection? linkedShelfEntry)
    {
        string normalizedPublicationKind = (publication.Kind ?? string.Empty).Trim().ToLowerInvariant();
        return normalizedPublicationKind switch
        {
            "campaign" => "Campaign packet",
            "dossier" => "Dossier",
            "primer" => "Primer",
            "run_module" => "Run Module",
            _ when normalizedPublicationKind.Contains("replay", StringComparison.Ordinal) => "Replay timeline",
            _ when normalizedPublicationKind.Contains("recap", StringComparison.Ordinal)
                || normalizedPublicationKind.Contains("after", StringComparison.Ordinal)
                || normalizedPublicationKind.Contains("downtime", StringComparison.Ordinal) => "Recap package",
            _ => HumanizeValue(linkedShelfEntry?.Kind ?? publication.Kind, "Publication")
        };
    }

    private static string HumanizeValue(string? value, string fallback)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return fallback;
        }

        return System.Globalization.CultureInfo.InvariantCulture.TextInfo.ToTitleCase(
            value.Trim().Replace('_', ' ').Replace('-', ' '));
    }

    private static string? NormalizeOptional(string? value)
        => string.IsNullOrWhiteSpace(value) ? null : value.Trim();
}
