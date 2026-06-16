using System.ComponentModel.DataAnnotations;
using Chummer.Campaign.Contracts;
using Chummer.Contracts.Receipts;

namespace Chummer.Run.Api.Contracts;

public sealed record DossierMovementRequest(
    [property: Required(AllowEmptyStrings = false), StringLength(128)]
    string DossierId,
    [property: Required(AllowEmptyStrings = false), StringLength(128)]
    string TargetGroupId,
    [property: StringLength(128)]
    string? TargetCampaignId = null,
    [property: StringLength(160)]
    string? TargetCampaignTitle = null,
    [property: StringLength(128)]
    string? TargetRunId = null,
    [property: StringLength(160)]
    string? TargetRunTitle = null,
    [property: StringLength(128)]
    string? TargetSceneId = null,
    [property: StringLength(160)]
    string? TargetSceneTitle = null,
    [property: StringLength(128)]
    string? TargetOwnerUserId = null,
    [property: StringLength(256)]
    string? Note = null);

public sealed record DossierMovementPlannerProjection(
    string WorkspaceId,
    string SourceGroupId,
    string SourceGroupName,
    string SourceCampaignId,
    string SourceCampaignName,
    string Summary,
    IReadOnlyList<RosterTransferCandidateProjection> DossierOptions,
    IReadOnlyList<DossierMovementTargetGroupProjection> TargetGroups);

public sealed record DossierMovementTargetGroupProjection(
    string GroupId,
    string GroupName,
    string GroupType,
    string OperatorRole,
    string SuggestedCampaignTitle,
    IReadOnlyList<RosterTransferOwnerOptionProjection> OwnerOptions,
    IReadOnlyList<DossierMovementTargetCampaignProjection> CampaignOptions);

public sealed record DossierMovementTargetCampaignProjection(
    string CampaignId,
    string CampaignName,
    string Status,
    bool Suggested,
    IReadOnlyList<DossierMovementEventProjection> EventOptions);

public sealed record DossierMovementEventProjection(
    string RunId,
    string RunTitle,
    string RunStatus,
    string SceneId,
    string SceneTitle,
    string SceneStatus,
    string SceneRevision,
    bool Active);

public sealed record DossierMovementReceiptProjection(
    string MovementId,
    string DossierId,
    string RunnerHandle,
    string PreviousOwnerUserId,
    string CurrentOwnerUserId,
    string SourceGroupId,
    string SourceGroupName,
    string SourceCampaignId,
    string SourceCampaignName,
    string? SourceRunId,
    string? SourceRunTitle,
    string? SourceSceneId,
    string? SourceSceneTitle,
    string TargetGroupId,
    string TargetGroupName,
    string TargetCampaignId,
    string TargetCampaignName,
    string TargetRunId,
    string TargetRunTitle,
    string TargetSceneId,
    string TargetSceneTitle,
    bool OwnershipChanged,
    bool CampaignChanged,
    bool GroupChanged,
    bool EventChanged,
    string InitiatedByUserId,
    string Summary,
    IReadOnlyList<string> AuditLines,
    IReadOnlyList<CampaignConsequenceReceipt> Receipts,
    DateTimeOffset MovedAtUtc,
    RosterTransferProjection TransferReceipt,
    ReceiptEnvelope? Envelope = null);
