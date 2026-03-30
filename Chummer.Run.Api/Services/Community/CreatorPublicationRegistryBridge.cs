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
        GetOrCreatePublicationLane(user, publication, workspace);
        _drafts.SubmitProject(
            publication.PublicationId,
            user.UserId,
            new HubSubmitProjectRequest(Notes: NormalizeOptional(notes)));
        return GetOrCreatePublicationLane(user, publication, workspace);
    }

    public CreatorPublicationRegistryProjection ApproveReview(
        HubUserDto user,
        CreatorPublicationProjection publication,
        CampaignWorkspaceProjection? workspace,
        string? notes = null)
    {
        CreatorPublicationRegistryProjection current = GetOrCreatePublicationLane(user, publication, workspace);
        string caseId = current.DraftDetail.Moderation?.CaseId
            ?? throw new InvalidOperationException("There is no pending moderation case to approve.");
        _drafts.ApproveModerationCase(caseId, user.UserId, new HubModerationDecisionRequest(NormalizeOptional(notes)));
        return GetOrCreatePublicationLane(user, publication, workspace);
    }

    public CreatorPublicationRegistryProjection RejectReview(
        HubUserDto user,
        CreatorPublicationProjection publication,
        CampaignWorkspaceProjection? workspace,
        string? notes = null)
    {
        CreatorPublicationRegistryProjection current = GetOrCreatePublicationLane(user, publication, workspace);
        string caseId = current.DraftDetail.Moderation?.CaseId
            ?? throw new InvalidOperationException("There is no pending moderation case to reject.");
        _drafts.RejectModerationCase(caseId, user.UserId, new HubModerationDecisionRequest(NormalizeOptional(notes)));
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
        PublicationSafeProjection? linkedShelfEntry = workspace?.RecapShelf
            .FirstOrDefault(item =>
                string.Equals(item.CreatorPublicationId, publication.PublicationId, StringComparison.OrdinalIgnoreCase)
                || (!string.IsNullOrWhiteSpace(publication.ArtifactId)
                    && string.Equals(item.ArtifactId, publication.ArtifactId, StringComparison.OrdinalIgnoreCase)));
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
            _ when normalized.Contains("replay", StringComparison.Ordinal) => nameof(HubArtifactKind.ReplayPackage),
            _ when normalized.Contains("recap", StringComparison.Ordinal) => nameof(HubArtifactKind.RecapPackage),
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
        List<string> lines = [publication.Summary];

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

        return string.Join(" ", lines.Where(static line => !string.IsNullOrWhiteSpace(line)));
    }

    private static string? NormalizeOptional(string? value)
        => string.IsNullOrWhiteSpace(value) ? null : value.Trim();
}
