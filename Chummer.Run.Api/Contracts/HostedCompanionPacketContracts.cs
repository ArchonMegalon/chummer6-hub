using Chummer.Campaign.Contracts;
using Chummer.Control.Contracts.Support;
using Chummer.Hub.Registry.Contracts.InstallLinking;

namespace Chummer.Run.Api.Contracts;

public sealed record HostedCompanionPacketContext(
    WorkspaceRestoreProjection Restore,
    IReadOnlyList<CampaignWorkspaceProjection> Workspaces,
    IReadOnlyList<CreatorPublicationProjection> Publications,
    IReadOnlyList<SupportCaseProjection> SupportCases,
    InstallLinkingSummaryDto? InstallLinking = null,
    string Locale = "en-US");

public sealed record HostedCompanionPacketBundle(
    DateTimeOffset BuiltAtUtc,
    IReadOnlyList<HostedCompanionPacketProjection> AccountPackets,
    IReadOnlyList<HostedCompanionPacketProjection> PublicHubPackets);

public sealed record HostedCompanionPacketProjection(
    string PacketId,
    string TriggerClass,
    string EventType,
    string TriggerVersion,
    DateTimeOffset EmittedAtUtc,
    string OwningDomain,
    string Severity,
    string Urgency,
    string Locale,
    IReadOnlyList<string> SurfaceAllowlist,
    string DeviceRole,
    string InstallRole,
    string MaskId,
    string PersonaModeDefault,
    string AllowedJokeBudget,
    bool EvidenceDrawerRequired,
    IReadOnlyList<HostedCompanionFactRefProjection> FactRefs,
    string FactSummary,
    IReadOnlyList<HostedCompanionActionProjection> AllowedActions,
    HostedCompanionSuppressionProjection Suppression,
    HostedCompanionEaCompileProjection EaCompile,
    HostedCompanionMediaEligibilityProjection MediaEligibility,
    string PrivacyClass,
    bool RequiresUserGestureForVoice,
    DateTimeOffset? SuppressUntilUtc,
    DateTimeOffset ExpiryUtc,
    IReadOnlyList<string> ForbiddenClaims,
    string Summary,
    string? FallbackPackId = null,
    string? MediaRef = null,
    string? SourceId = null);

public sealed record HostedCompanionFactRefProjection(
    string FactId,
    string Kind,
    string Label,
    string Summary,
    string? Route = null,
    string? ReceiptId = null);

public sealed record HostedCompanionActionProjection(
    string ActionId,
    string Label,
    string Href,
    string Summary);

public sealed record HostedCompanionSuppressionProjection(
    string CooldownScope,
    int CooldownSeconds,
    int MaxImpressionsPerDay,
    bool RequiresMaterialChange,
    IReadOnlyList<string> ResetOnAction);

public sealed record HostedCompanionEaCompileProjection(
    bool Eligible,
    string Mode,
    IReadOnlyList<string> AllowedOutputs,
    bool RuntimeBlocking);

public sealed record HostedCompanionMediaEligibilityProjection(
    bool Eligible,
    IReadOnlyList<string> Modes);
