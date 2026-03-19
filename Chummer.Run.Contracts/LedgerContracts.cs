using System.ComponentModel.DataAnnotations;

namespace Chummer.Run.Contracts.Ledger;

public sealed record ContributionReceiptDto(
    [Required(AllowEmptyStrings = false), StringLength(128)] string ReceiptId,
    [Required(AllowEmptyStrings = false), StringLength(64)] string EventKind,
    [Required(AllowEmptyStrings = false), StringLength(128)] string LaneId,
    [Required(AllowEmptyStrings = false), StringLength(128)] string ProjectId,
    string? UserId,
    string? GroupId,
    string? SponsorSessionId,
    string AuthClass,
    string LaneType,
    DateTimeOffset? StartedAtUtc = null,
    DateTimeOffset? EndedAtUtc = null,
    string? SliceId = null,
    string? WorkflowKind = null,
    int ReviewRoundsUsed = 0,
    string? AcceptedOnRound = null,
    string? LandedSha = null,
    DateTimeOffset? LandedAtUtc = null,
    bool Verified = false,
    bool CheapLoopOnly = false,
    bool PaidLaneUsed = false,
    int GroundworkMs = 0,
    int ReviewMs = 0,
    int JuryMs = 0,
    int CoreMs = 0,
    int FilesTouched = 0,
    int DiffSize = 0,
    IReadOnlyList<string>? IssueFingerprints = null,
    decimal CreditBurnEstimate = 0,
    string? SignedByFleet = null);

public sealed record LedgerEntryDto(
    string EntryId,
    string EntryKind,
    string UserId,
    string? GroupId,
    string SourceId,
    int Units,
    string Unit,
    string Description,
    DateTimeOffset CreatedAtUtc);

public sealed record RewardJournalEntryDto(
    string RewardEntryId,
    string UserId,
    string? GroupId,
    string RewardKind,
    int Points,
    string SourceReceiptId,
    string Description,
    DateTimeOffset GrantedAtUtc);

public sealed record ReceiptIngestResultDto(
    string ReceiptId,
    string Status,
    int MintedPoints,
    IReadOnlyList<string> GrantedEntitlements,
    string ProjectionFingerprint,
    DateTimeOffset IngestedAtUtc);
