using Chummer.Run.Api.Services;

namespace Chummer.Run.Api.Contracts;

public sealed record CampaignFederationBatchRequest(
    IReadOnlyList<string>? SourceIds = null,
    IReadOnlyList<string>? RequestedFormats = null,
    string? Audience = null,
    string? Locale = null);

public sealed record CampaignFederationSourcePackProjection(
    string SourcePackId,
    string SourcePackKind,
    string EntryId,
    string PublicationId,
    string CampaignId,
    string Label,
    string Summary,
    string PublicationKind,
    string PublicationStatus,
    string PublicShelfRef,
    string? ArtifactId,
    string? DossierId,
    IReadOnlyList<string> EvidenceRefs);

public sealed record CampaignFederationBatchProjection(
    string WorkspaceId,
    string CampaignId,
    string CampaignName,
    string SelectionSummary,
    IReadOnlyList<string> Watchouts,
    IReadOnlyList<CampaignFederationSourcePackProjection> SourcePacks,
    ArtifactFactoryJobBatchLaunchResult Batch);
