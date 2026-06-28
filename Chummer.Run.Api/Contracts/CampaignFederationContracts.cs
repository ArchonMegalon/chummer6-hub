using System.ComponentModel.DataAnnotations;
using Chummer.Contracts.Receipts;
using Chummer.Run.Api.Services;

namespace Chummer.Run.Api.Contracts;

public sealed record CampaignFederationRouteReceiptProjection(
    string ReceiptId,
    string PackageId,
    string MatchedRoute,
    string MatchMode,
    string Summary,
    ReceiptEnvelope? Envelope = null);

public sealed record CampaignFederationBatchRequest(
    [property: MaxLength(8)] IReadOnlyList<string>? SourceIds = null,
    [property: MaxLength(8)] IReadOnlyList<string>? RequestedFormats = null,
    [property: StringLength(64)] string? Audience = null,
    [property: StringLength(32)] string? Locale = null);

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
    string RouteState,
    CampaignFederationRouteReceiptProjection? RouteReceipt,
    string? BoundedFailureReason,
    string NextSafeAction,
    string PublicShelfRef,
    string? ArtifactId,
    string? DossierId,
    IReadOnlyList<string> EvidenceRefs);

public sealed record CampaignFederationBatchProjection(
    string WorkspaceId,
    string CampaignId,
    string CampaignName,
    string SelectionSummary,
    string RouteState,
    CampaignFederationRouteReceiptProjection? RouteReceipt,
    string? BoundedFailureReason,
    string NextSafeAction,
    IReadOnlyList<string> RequiredReceiptRefs,
    IReadOnlyList<string> Watchouts,
    IReadOnlyList<CampaignFederationSourcePackProjection> SourcePacks,
    ArtifactFactoryJobBatchLaunchResult Batch);
