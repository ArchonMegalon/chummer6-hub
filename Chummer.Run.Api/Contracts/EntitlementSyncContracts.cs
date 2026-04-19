using Chummer.Campaign.Contracts;
using Chummer.Run.Contracts.Community;
using Chummer.Run.Contracts.Entitlements;
using Chummer.Run.Contracts.Leaderboards;

namespace Chummer.Run.Api.Contracts;

public sealed record EntitlementSyncReceiptProjection(
    WorkspaceRestoreReceiptStatusProjection ReceiptStatus,
    IReadOnlyList<WorkspaceRestoreReceiptSurfaceProjection> ReceiptSurfaces,
    IReadOnlyList<WorkspaceRestoreProvenanceReceipt> ProvenanceReceipts,
    IReadOnlyList<WorkspaceRestoreProvenanceRecoveryProjection> ProvenanceRecoveryReceipts,
    IReadOnlyList<WorkspaceRestoreConflictReceiptProjection> ConflictReceipts,
    DateTimeOffset GeneratedAtUtc);

public sealed record EntitlementAccountProjection(
    HubUserDto User,
    IReadOnlyList<EntitlementDto> Entitlements,
    IReadOnlyList<BadgeDto> Badges,
    EntitlementSyncReceiptProjection SyncReceipts);
