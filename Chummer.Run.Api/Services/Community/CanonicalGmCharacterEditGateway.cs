namespace Chummer.Run.Api.Services.Community;

/// <summary>
/// Hub-private routing context for a future adapter over Core's
/// chummer.delegated-gm-character-edit/v1 package contract. These transport
/// envelopes are deliberately not copies of Chummer.Contracts.Workspaces.
/// The production adapter must consume the pinned Core package types, ask a
/// store-backed Core authorizer to re-check the current Hub grant, and map the
/// exact Core result into this bounded Hub transport seam.
/// </summary>
public sealed record CoreDelegatedGmEditTransportContext(
    string CampaignId,
    string ActorUserId,
    string CampaignOwnerUserId,
    string CharacterOwnerUserId,
    string DossierId,
    string AuthorityKind,
    string AuthoritativeCharacterId,
    string DelegationId,
    string AuthorityReceiptId,
    long AuthorityRevision,
    DateTimeOffset AuthorityGrantedAtUtc);

public sealed record CoreDelegatedGmEditTransportReadCommand(
    CoreDelegatedGmEditTransportContext Context);

public sealed record CoreDelegatedGmEditTransportCommand(
    CoreDelegatedGmEditTransportContext Context,
    long ExpectedRevision,
    string IdempotencyKey,
    string Reason,
    string RunnerHandle,
    string DisplayName);

/// <summary>
/// Privacy-bounded canonical readback. A real adapter obtains these values from
/// Core after authorization; it must never echo Hub request values as proof.
/// </summary>
public sealed record CoreDelegatedGmEditTransportProfile(
    long Revision,
    string RunnerHandle,
    string DisplayName);

public enum CoreDelegatedGmEditTransportReadOutcome
{
    Available = 0,
    Denied = 1,
    Forbidden = 2,
    Invalid = 3,
    Missing = 4,
    Corrupt = 5,
    Unavailable = 6
}

public sealed record CoreDelegatedGmEditTransportReadResult(
    CoreDelegatedGmEditTransportReadOutcome Outcome,
    CoreDelegatedGmEditTransportProfile? Profile = null,
    string? ErrorCode = null);

public enum CoreDelegatedGmEditTransportPatchOperationKind
{
    Replace = 0
}

/// <summary>
/// Privacy-safe transport projection of one Core receipt operation. The real
/// adapter maps the package-owned receipt; Hub never synthesizes this receipt
/// from the mutation request.
/// </summary>
public sealed record CoreDelegatedGmEditTransportAuditOperation(
    CoreDelegatedGmEditTransportPatchOperationKind Operation,
    string Path,
    string ValueSha256,
    int ValueLength);

public enum CoreDelegatedGmEditTransportOutcome
{
    Applied = 0,
    Replayed = 1,
    Denied = 2,
    Forbidden = 3,
    Invalid = 4,
    Missing = 5,
    Conflict = 6,
    Corrupt = 7,
    Unavailable = 8
}

public sealed record CoreDelegatedGmEditTransportReceipt(
    string Contract,
    string ReceiptId,
    string CampaignId,
    string DelegationId,
    string GrantedByCampaignOwnerId,
    string GrantedByCharacterOwnerId,
    string AuthorityReceiptId,
    long AuthorityRevision,
    string ActorId,
    string ActorRole,
    string CharacterOwnerId,
    string AuthoritativeCharacterId,
    string Reason,
    string IdempotencyKeySha256,
    string CommandSha256,
    long PreviousRevision,
    long NewRevision,
    DateTimeOffset AppliedAtUtc,
    IReadOnlyList<CoreDelegatedGmEditTransportAuditOperation> Operations);

public sealed record CoreDelegatedGmEditTransportResult(
    CoreDelegatedGmEditTransportOutcome Outcome,
    CoreDelegatedGmEditTransportReceipt? Receipt = null,
    // Mandatory for Applied, Replayed, and Conflict. This is an
    // authoritative read after execution/replay, so Hub can reconcile without
    // overwriting a later character-owner edit.
    CoreDelegatedGmEditTransportProfile? CurrentProfile = null,
    string? ErrorCode = null);

/// <summary>
/// Hub-private seam for the future pinned Core adapter. Readback is mandatory:
/// Hub-derived revisions are only a projection and may never veto a Core
/// idempotent replay or overwrite a newer owner edit.
/// </summary>
public interface ICanonicalGmCharacterEditGateway
{
    CoreDelegatedGmEditTransportReadResult ReadCurrentProfile(
        CoreDelegatedGmEditTransportReadCommand command);

    CoreDelegatedGmEditTransportResult Execute(
        CoreDelegatedGmEditTransportCommand command);
}

/// <summary>
/// Safe release default until the exact Core package plus authoritative
/// readback adapter is pinned. It deliberately cannot mutate Core or Hub.
/// </summary>
public sealed class UnavailableCoreDelegatedGmCharacterEditGateway : ICanonicalGmCharacterEditGateway
{
    public CoreDelegatedGmEditTransportReadResult ReadCurrentProfile(
        CoreDelegatedGmEditTransportReadCommand command)
    {
        ArgumentNullException.ThrowIfNull(command);
        return new CoreDelegatedGmEditTransportReadResult(
            CoreDelegatedGmEditTransportReadOutcome.Unavailable,
            ErrorCode: "core_delegated_edit_package_unavailable");
    }

    public CoreDelegatedGmEditTransportResult Execute(
        CoreDelegatedGmEditTransportCommand command)
    {
        ArgumentNullException.ThrowIfNull(command);
        return new CoreDelegatedGmEditTransportResult(
            CoreDelegatedGmEditTransportOutcome.Unavailable,
            ErrorCode: "core_delegated_edit_package_unavailable");
    }
}
