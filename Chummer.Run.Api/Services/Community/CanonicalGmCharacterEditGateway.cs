namespace Chummer.Run.Api.Services.Community;

/// <summary>
/// Package-plane command passed to the adapter for Core's
/// chummer.delegated-gm-character-edit/v1 service. Hub owns the current
/// campaign grant; the adapter must make Core re-authorize that grant and must
/// not implement character patching itself.
/// </summary>
public sealed record CanonicalGmCharacterEditCommand(
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
    DateTimeOffset AuthorityGrantedAtUtc,
    long ExpectedRevision,
    string IdempotencyKey,
    string Reason,
    string RunnerHandle,
    string DisplayName);

public enum CanonicalGmCharacterEditPatchOperationKind
{
    Replace = 0
}

/// <summary>
/// Exact package-plane projection of Core's privacy-safe delegated-edit audit
/// operation. Hub verifies these digests before changing its read projection;
/// the adapter must not synthesize them from the request.
/// </summary>
public sealed record CanonicalGmCharacterEditAuditOperation(
    CanonicalGmCharacterEditPatchOperationKind Operation,
    string Path,
    string ValueSha256,
    int ValueLength);

public enum CanonicalGmCharacterEditOutcome
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

/// <summary>
/// The minimal Core receipt projection Hub needs to reconcile its campaign
/// sheet. Values are returned by the typed Core package adapter after Core has
/// atomically committed or replayed the canonical character edit.
/// </summary>
public sealed record CanonicalGmCharacterEditReceipt(
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
    IReadOnlyList<CanonicalGmCharacterEditAuditOperation> Operations);

public sealed record CanonicalGmCharacterEditResult(
    CanonicalGmCharacterEditOutcome Outcome,
    CanonicalGmCharacterEditReceipt? Receipt = null,
    // Mandatory for Applied/Replayed. The package adapter must read the
    // canonical workspace after execution so Hub never projects an old replay
    // receipt over a character that has since advanced again.
    long? CurrentRevision = null,
    string? ErrorCode = null);

/// <summary>
/// Typed seam for Core's delegated canonical character-edit service. A release
/// implementation must come from the pinned Core package plane and re-check
/// Hub's current authority through its Core authorizer. Test implementations
/// may emulate Core's atomic idempotency ledger, but production Hub code must
/// never duplicate the canonical patch logic.
/// </summary>
public interface ICanonicalGmCharacterEditGateway
{
    CanonicalGmCharacterEditResult Execute(CanonicalGmCharacterEditCommand command);
}

/// <summary>
/// Safe release default until the Core package containing the delegated-edit
/// adapter is pinned. It deliberately cannot mutate either Core or Hub state.
/// </summary>
public sealed class UnavailableCoreDelegatedGmCharacterEditGateway : ICanonicalGmCharacterEditGateway
{
    public CanonicalGmCharacterEditResult Execute(CanonicalGmCharacterEditCommand command)
    {
        ArgumentNullException.ThrowIfNull(command);
        return new CanonicalGmCharacterEditResult(
            CanonicalGmCharacterEditOutcome.Unavailable,
            ErrorCode: "core_delegated_edit_package_unavailable");
    }
}
