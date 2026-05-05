using Chummer.Campaign.Contracts;
using Chummer.Hub.Registry.Contracts.InstallLinking;
using Chummer.Run.Api.Contracts;
using Chummer.Run.Api.Services;
using Chummer.Run.Contracts.Community;

namespace Chummer.Run.Api.Services.Community;

public sealed class CampaignFederationOrchestrationService
{
    private readonly CampaignSpineService _campaignSpine;
    private readonly ArtifactFactoryOrchestrationService _artifactFactory;

    public CampaignFederationOrchestrationService(
        CampaignSpineService campaignSpine,
        ArtifactFactoryOrchestrationService artifactFactory)
    {
        _campaignSpine = campaignSpine;
        _artifactFactory = artifactFactory;
    }

    public CampaignFederationBatchProjection? LaunchWorkspaceFederationBatch(
        HubUserDto user,
        string workspaceId,
        CampaignFederationBatchRequest request,
        InstallLinkingSummaryDto? installLinking = null)
    {
        ArgumentNullException.ThrowIfNull(user);
        ArgumentException.ThrowIfNullOrWhiteSpace(workspaceId);
        ArgumentNullException.ThrowIfNull(request);

        AccountCampaignSummary summary = _campaignSpine.GetAccountSummary(user, installLinking);
        CampaignWorkspaceProjection? workspace = summary.Workspaces
            .FirstOrDefault(item => string.Equals(item.WorkspaceId, workspaceId, StringComparison.OrdinalIgnoreCase));
        if (workspace is null)
        {
            return null;
        }

        CreatorPublicationProjection[] creatorPublications = summary.CreatorPublications
            .Where(item => string.Equals(item.CampaignId, workspace.CampaignId, StringComparison.OrdinalIgnoreCase))
            .ToArray();
        FederationCandidate[] candidates = BuildCandidates(workspace, creatorPublications);
        if (candidates.Length == 0)
        {
            throw new InvalidOperationException("campaign federation requires at least one governed dossier, replay, or recap publication-safe source pack.");
        }

        FederationCandidate[] selected = SelectCandidates(candidates, request.SourceIds);
        if (selected.Length == 0)
        {
            throw new InvalidOperationException("campaign federation could not resolve any governed dossier, replay, or recap source packs from the selected workspace.");
        }

        CampaignFederationSourcePackProjection[] sourcePacks = selected
            .Select(candidate => BuildSourcePackProjection(candidate, request))
            .ToArray();
        ArtifactFactoryFamilyFormatOverride[]? requestedFormats = NormalizeRequestedFormats(request.RequestedFormats);
        ArtifactFactoryJobBatchLaunchResult batch = _artifactFactory.LaunchSourcePackBatch(new ArtifactFactorySourcePackBatchLaunchRequest(
            BatchId: BuildBatchId(workspace.WorkspaceId, sourcePacks),
            RequestedBy: "hub.campaign-federation",
            SourcePacks: sourcePacks.Select(candidate => candidate.ToSourcePack(request)).ToArray(),
            RequestedFormats: requestedFormats,
            Audience: NormalizeOptional(request.Audience),
            Locale: NormalizeOptional(request.Locale),
            RequiredFamilies: ["publication"]));

        string selectionSummary = $"Federated {sourcePacks.Length} governed source pack(s) from {workspace.CampaignName}: {string.Join(", ", sourcePacks.Select(static item => item.Label))}.";
        string[] watchouts = selected
            .SelectMany(BuildWatchouts)
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .Order(StringComparer.OrdinalIgnoreCase)
            .ToArray();

        return new CampaignFederationBatchProjection(
            WorkspaceId: workspace.WorkspaceId,
            CampaignId: workspace.CampaignId,
            CampaignName: workspace.CampaignName,
            SelectionSummary: selectionSummary,
            Watchouts: watchouts,
            SourcePacks: sourcePacks,
            Batch: batch);
    }

    private static FederationCandidate[] BuildCandidates(
        CampaignWorkspaceProjection workspace,
        IReadOnlyList<CreatorPublicationProjection> creatorPublications)
    {
        Dictionary<string, CreatorPublicationProjection> publicationsById = creatorPublications
            .Where(static item => !string.IsNullOrWhiteSpace(item.PublicationId))
            .GroupBy(static item => item.PublicationId, StringComparer.OrdinalIgnoreCase)
            .ToDictionary(
                static group => group.Key,
                static group => group
                    .OrderByDescending(static item => item.UpdatedAtUtc)
                    .First(),
                StringComparer.OrdinalIgnoreCase);

        Dictionary<string, CreatorPublicationProjection> publicationsByArtifactId = creatorPublications
            .Where(static item => !string.IsNullOrWhiteSpace(item.ArtifactId))
            .GroupBy(static item => item.ArtifactId, StringComparer.OrdinalIgnoreCase)
            .ToDictionary(
                static group => group.Key,
                static group => group
                    .OrderByDescending(static item => item.UpdatedAtUtc)
                    .First(),
                StringComparer.OrdinalIgnoreCase);

        return (workspace.RecapShelf ?? Array.Empty<PublicationSafeProjection>())
            .Select(item =>
            {
                CreatorPublicationProjection? publication = ResolvePublication(item, publicationsById, publicationsByArtifactId);
                return publication is null ? null : BuildCandidate(item, publication);
            })
            .Where(static item => item is not null)
            .Select(static item => item!)
            .DistinctBy(static item => item.PublicationId, StringComparer.OrdinalIgnoreCase)
            .OrderByDescending(static item => CandidatePriority(item.Kind))
            .ThenByDescending(static item => item.UpdatedAtUtc)
            .ThenBy(static item => item.Label, StringComparer.OrdinalIgnoreCase)
            .ToArray();
    }

    private static FederationCandidate[] SelectCandidates(FederationCandidate[] candidates, IReadOnlyList<string>? requestedSourceIds)
    {
        if (requestedSourceIds is { Count: > 0 })
        {
            List<FederationCandidate> selected = new(requestedSourceIds.Count);
            HashSet<string> seenPublicationIds = new(StringComparer.OrdinalIgnoreCase);
            foreach (string rawSourceId in requestedSourceIds)
            {
                string sourceId = NormalizeOptional(rawSourceId)
                    ?? throw new InvalidOperationException("campaign federation source ids cannot be blank.");
                FederationCandidate candidate = candidates.FirstOrDefault(item => item.Matches(sourceId))
                    ?? throw new InvalidOperationException($"campaign federation source id '{sourceId}' does not belong to the selected workspace.");
                if (seenPublicationIds.Add(candidate.PublicationId))
                {
                    selected.Add(candidate);
                }
            }

            return selected.ToArray();
        }

        FederationCandidate? dossier = candidates.FirstOrDefault(static item => item.IsDossier);
        FederationCandidate? replay = candidates.FirstOrDefault(static item => item.IsReplay);
        FederationCandidate? recap = candidates.FirstOrDefault(static item => item.IsRecap && !item.IsReplay);
        FederationCandidate? fallback = candidates.FirstOrDefault();

        List<FederationCandidate> defaults = new(2);
        if (dossier is not null)
        {
            defaults.Add(dossier);
        }

        FederationCandidate? followThrough = replay ?? recap;
        if (followThrough is not null
            && defaults.All(item => !string.Equals(item.PublicationId, followThrough.PublicationId, StringComparison.OrdinalIgnoreCase)))
        {
            defaults.Add(followThrough);
        }

        if (defaults.Count == 0 && fallback is not null)
        {
            defaults.Add(fallback);
        }

        return defaults.ToArray();
    }

    private static CampaignFederationSourcePackProjection BuildSourcePackProjection(
        FederationCandidate candidate,
        CampaignFederationBatchRequest request)
    {
        string publicShelfRef = $"/artifacts/publications/{Uri.EscapeDataString(candidate.PublicationId)}";
        string moderationState = NormalizePublicationStatus(candidate.PublicationStatus);
        string sourcePackKind = candidate.IsReplay || candidate.IsRecap
            ? "campaign_recap"
            : "creator_publication";
        string sourcePackId = BuildSourcePackId(sourcePackKind, candidate.PublicationId, candidate.EntryId);
        string[] evidenceRefs =
        [
            $"publication:{candidate.PublicationId}:{moderationState}",
            $"moderation:{moderationState}:{candidate.PublicationId}",
            $"public-shelf:{publicShelfRef}",
            $"campaign:{candidate.CampaignId}",
            candidate.IsDossier
                ? $"dossier:{candidate.DossierId ?? candidate.PublicationId}"
                : candidate.IsReplay
                    ? $"replay:{candidate.EntryId}"
                    : $"recap:{candidate.EntryId}"
        ];

        return new CampaignFederationSourcePackProjection(
            SourcePackId: sourcePackId,
            SourcePackKind: sourcePackKind,
            EntryId: candidate.EntryId,
            PublicationId: candidate.PublicationId,
            CampaignId: candidate.CampaignId,
            Label: candidate.Label,
            Summary: candidate.Summary,
            PublicationKind: candidate.Kind,
            PublicationStatus: moderationState,
            PublicShelfRef: publicShelfRef,
            ArtifactId: candidate.ArtifactId,
            DossierId: candidate.DossierId,
            EvidenceRefs: evidenceRefs);
    }

    private static ArtifactFactoryFamilyFormatOverride[]? NormalizeRequestedFormats(IReadOnlyList<string>? requestedFormats)
    {
        if (requestedFormats is null || requestedFormats.Count == 0)
        {
            return null;
        }

        string[] formats = requestedFormats
            .Where(static item => !string.IsNullOrWhiteSpace(item))
            .Select(static item => item.Trim())
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .Order(StringComparer.OrdinalIgnoreCase)
            .ToArray();
        return formats.Length == 0
            ? null
            : [new ArtifactFactoryFamilyFormatOverride("publication", formats)];
    }

    private static CreatorPublicationProjection? ResolvePublication(
        PublicationSafeProjection item,
        IReadOnlyDictionary<string, CreatorPublicationProjection> publicationsById,
        IReadOnlyDictionary<string, CreatorPublicationProjection> publicationsByArtifactId)
    {
        string? publicationId = NormalizeOptional(item.CreatorPublicationId);
        if (publicationId is not null
            && publicationsById.TryGetValue(publicationId, out CreatorPublicationProjection? publicationById))
        {
            return publicationById;
        }

        string? artifactId = NormalizeOptional(item.ArtifactId);
        if (artifactId is not null
            && publicationsByArtifactId.TryGetValue(artifactId, out CreatorPublicationProjection? publicationByArtifact))
        {
            return publicationByArtifact;
        }

        return null;
    }

    private static FederationCandidate BuildCandidate(PublicationSafeProjection item, CreatorPublicationProjection publication)
    {
        string kind = NormalizeOptional(publication.Kind)
            ?? NormalizeOptional(item.Kind)
            ?? "publication";
        string label = NormalizeOptional(publication.Title)
            ?? NormalizeOptional(item.Label)
            ?? publication.PublicationId;
        string summary = NormalizeOptional(publication.Summary)
            ?? NormalizeOptional(item.Summary)
            ?? label;
        string entryId = NormalizeOptional(item.ProjectionId)
            ?? publication.PublicationId;
        string? artifactId = NormalizeOptional(item.ArtifactId)
            ?? NormalizeOptional(publication.ArtifactId);
        string[] aliases = new[]
        {
            entryId,
            publication.PublicationId,
            item.CreatorPublicationId,
            item.ArtifactId,
            publication.ArtifactId
        }
        .Where(static item => !string.IsNullOrWhiteSpace(item))
        .Select(static item => item!.Trim())
        .Distinct(StringComparer.OrdinalIgnoreCase)
        .ToArray();
        bool isDossier = KindContains(kind, "dossier");
        bool isReplay = KindContains(kind, "replay");
        bool isRecap = isReplay
            || KindContains(kind, "recap")
            || KindContains(kind, "after")
            || KindContains(kind, "downtime")
            || KindContains(kind, "campaign");
        return new FederationCandidate(
            EntryId: entryId,
            PublicationId: publication.PublicationId,
            CampaignId: publication.CampaignId,
            Label: label,
            Summary: summary,
            Kind: kind,
            PublicationStatus: publication.PublicationStatus,
            ArtifactId: artifactId,
            DossierId: NormalizeOptional(publication.DossierId),
            UpdatedAtUtc: publication.UpdatedAtUtc,
            IsDossier: isDossier,
            IsReplay: isReplay,
            IsRecap: isRecap,
            Aliases: aliases,
            Watchouts: publication.Watchouts ?? Array.Empty<string>());
    }

    private static int CandidatePriority(string kind)
    {
        if (KindContains(kind, "dossier"))
        {
            return 3;
        }

        if (KindContains(kind, "replay"))
        {
            return 2;
        }

        return KindContains(kind, "recap") || KindContains(kind, "after") || KindContains(kind, "downtime") || KindContains(kind, "campaign")
            ? 1
            : 0;
    }

    private static IEnumerable<string> BuildWatchouts(FederationCandidate candidate)
    {
        foreach (string watchout in candidate.Watchouts.Where(static item => !string.IsNullOrWhiteSpace(item)))
        {
            yield return watchout;
        }

        string normalizedStatus = NormalizePublicationStatus(candidate.PublicationStatus);
        if (!string.Equals(normalizedStatus, "published", StringComparison.OrdinalIgnoreCase)
            && !string.Equals(normalizedStatus, "approved", StringComparison.OrdinalIgnoreCase))
        {
            yield return $"{candidate.Label} stays {normalizedStatus.Replace('_', ' ')} on governed publication shelves until wider review clears.";
        }
    }

    private static string BuildBatchId(string workspaceId, IReadOnlyList<CampaignFederationSourcePackProjection> sourcePacks)
    {
        string workspaceToken = StableToken(workspaceId);
        string sourceToken = string.Join(
            "-",
            sourcePacks
                .Select(static item => StableToken(item.PublicationId))
                .Take(3));
        return $"campaign-federation-{workspaceToken}-{sourceToken}-{DateTimeOffset.UtcNow.ToUnixTimeMilliseconds()}";
    }

    private static string BuildSourcePackId(string sourcePackKind, string publicationId, string entryId)
        => $"{StableToken(sourcePackKind)}-{StableToken(publicationId)}-{StableToken(entryId)}";

    private static bool KindContains(string? value, string token)
        => value?.Contains(token, StringComparison.OrdinalIgnoreCase) == true;

    private static string NormalizePublicationStatus(string? publicationStatus)
        => string.IsNullOrWhiteSpace(publicationStatus)
            ? "preview_ready"
            : publicationStatus.Trim().Replace('-', '_').ToLowerInvariant();

    private static string? NormalizeOptional(string? value)
        => string.IsNullOrWhiteSpace(value) ? null : value.Trim();

    private static string StableToken(string value)
    {
        char[] buffer = value
            .Trim()
            .ToLowerInvariant()
            .Select(ch => char.IsLetterOrDigit(ch) ? ch : '-')
            .ToArray();
        string normalized = new(buffer);
        while (normalized.Contains("--", StringComparison.Ordinal))
        {
            normalized = normalized.Replace("--", "-", StringComparison.Ordinal);
        }

        return normalized.Trim('-');
    }

    private sealed record FederationCandidate(
        string EntryId,
        string PublicationId,
        string CampaignId,
        string Label,
        string Summary,
        string Kind,
        string PublicationStatus,
        string? ArtifactId,
        string? DossierId,
        DateTimeOffset UpdatedAtUtc,
        bool IsDossier,
        bool IsReplay,
        bool IsRecap,
        IReadOnlyList<string> Aliases,
        IReadOnlyList<string> Watchouts)
    {
        public bool Matches(string sourceId)
            => Aliases.Any(alias => string.Equals(alias, sourceId, StringComparison.OrdinalIgnoreCase));
    }
}

internal static class CampaignFederationSourcePackProjectionExtensions
{
    public static ApprovedArtifactSourcePack ToSourcePack(
        this CampaignFederationSourcePackProjection projection,
        CampaignFederationBatchRequest request)
    {
        string normalizedStatus = projection.PublicationStatus;
        string sourceKind = projection.SourcePackKind;
        string provenanceRef = sourceKind.Equals("creator_publication", StringComparison.OrdinalIgnoreCase)
            ? $"creator-publication:{projection.PublicationId}:{normalizedStatus}"
            : $"{sourceKind}:{projection.EntryId}:{normalizedStatus}";
        return new ApprovedArtifactSourcePack(
            SourcePackId: projection.SourcePackId,
            SourcePackKind: projection.SourcePackKind,
            ApprovalState: "approved",
            ProvenanceRef: provenanceRef,
            EvidenceRefs: projection.EvidenceRefs,
            PublicationId: projection.PublicationId,
            PublicShelfRef: projection.PublicShelfRef,
            CampaignId: projection.CampaignId,
            Audience: string.IsNullOrWhiteSpace(request.Audience) ? null : request.Audience.Trim(),
            Locale: string.IsNullOrWhiteSpace(request.Locale) ? null : request.Locale.Trim());
    }
}
