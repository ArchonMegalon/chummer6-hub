using System.Security.Cryptography;
using System.Text;
using Chummer.Run.Contracts.Ledger;

namespace Chummer.Run.Api.Services.Community;

public sealed class LedgerService
{
    private readonly CommunityStore _store;
    private readonly RewardService _rewards;
    private readonly EntitlementService _entitlements;

    public LedgerService(CommunityStore store, RewardService rewards, EntitlementService entitlements)
    {
        _store = store;
        _rewards = rewards;
        _entitlements = entitlements;
    }

    public ReceiptIngestResultDto Ingest(ContributionReceiptDto receipt)
    {
        var canonicalReceipt = Canonicalize(receipt);
        lock (_store.Gate)
        {
            if (_store.Receipts.Any(existing => string.Equals(existing.ReceiptId, canonicalReceipt.ReceiptId, StringComparison.OrdinalIgnoreCase)))
            {
                return new ReceiptIngestResultDto(
                    ReceiptId: canonicalReceipt.ReceiptId,
                    Status: "duplicate",
                    MintedPoints: 0,
                    GrantedEntitlements: Array.Empty<string>(),
                    ProjectionFingerprint: ProjectionFingerprint(canonicalReceipt),
                    IngestedAtUtc: DateTimeOffset.UtcNow);
            }

            _store.Receipts.Add(canonicalReceipt);
            if (!string.IsNullOrWhiteSpace(canonicalReceipt.UserId))
            {
                _store.LedgerEntries.Add(
                    new LedgerEntryDto(
                        EntryId: AccountService.NewId("led"),
                        EntryKind: canonicalReceipt.EventKind,
                        UserId: canonicalReceipt.UserId!,
                        GroupId: AccountService.NormalizeOptional(canonicalReceipt.GroupId),
                        SourceId: canonicalReceipt.ReceiptId,
                        Units: 1,
                        Unit: "receipt",
                        Description: $"{canonicalReceipt.EventKind} receipt for {canonicalReceipt.ProjectId}.",
                        CreatedAtUtc: DateTimeOffset.UtcNow));
            }
        }

        var mintedPoints = _rewards.ApplyReceipt(canonicalReceipt);
        var granted = _entitlements.ApplyReceipt(canonicalReceipt, mintedPoints);
        lock (_store.Gate)
        {
            _store.PersistLocked();
        }
        return new ReceiptIngestResultDto(
            ReceiptId: canonicalReceipt.ReceiptId,
            Status: "ingested",
            MintedPoints: mintedPoints,
            GrantedEntitlements: granted,
            ProjectionFingerprint: ProjectionFingerprint(canonicalReceipt),
            IngestedAtUtc: DateTimeOffset.UtcNow);
    }

    public IReadOnlyList<LedgerEntryDto> ListForUser(string userId)
    {
        lock (_store.Gate)
        {
            return _store.LedgerEntries
                .Where(entry => string.Equals(entry.UserId, userId, StringComparison.OrdinalIgnoreCase))
                .OrderByDescending(entry => entry.CreatedAtUtc)
                .ToArray();
        }
    }

    private static ContributionReceiptDto Canonicalize(ContributionReceiptDto receipt)
        => receipt with
        {
            ReceiptId = AccountService.NormalizeRequired(receipt.ReceiptId, nameof(receipt.ReceiptId)),
            EventKind = AccountService.NormalizeRequired(receipt.EventKind, nameof(receipt.EventKind)),
            LaneId = AccountService.NormalizeRequired(receipt.LaneId, nameof(receipt.LaneId)),
            ProjectId = AccountService.NormalizeRequired(receipt.ProjectId, nameof(receipt.ProjectId)),
            UserId = AccountService.NormalizeOptional(receipt.UserId),
            GroupId = AccountService.NormalizeOptional(receipt.GroupId),
            SponsorSessionId = AccountService.NormalizeOptional(receipt.SponsorSessionId),
            ParticipantCodexCode = AccountService.NormalizeOptional(receipt.ParticipantCodexCode),
            AuthClass = AccountService.NormalizeOptional(receipt.AuthClass) ?? "",
            LaneType = AccountService.NormalizeOptional(receipt.LaneType) ?? "",
            SliceId = AccountService.NormalizeOptional(receipt.SliceId),
            WorkflowKind = AccountService.NormalizeOptional(receipt.WorkflowKind),
            AcceptedOnRound = AccountService.NormalizeOptional(receipt.AcceptedOnRound),
            LandedSha = AccountService.NormalizeOptional(receipt.LandedSha),
            GroundworkMs = Math.Max(0, receipt.GroundworkMs),
            ReviewMs = Math.Max(0, receipt.ReviewMs),
            JuryMs = Math.Max(0, receipt.JuryMs),
            CoreMs = Math.Max(0, receipt.CoreMs),
            FilesTouched = Math.Max(0, receipt.FilesTouched),
            DiffSize = Math.Max(0, receipt.DiffSize),
            ParticipantInputTokens = Math.Max(0, receipt.ParticipantInputTokens),
            ParticipantCachedInputTokens = Math.Max(0, receipt.ParticipantCachedInputTokens),
            ParticipantOutputTokens = Math.Max(0, receipt.ParticipantOutputTokens),
            ParticipantTotalTokens = Math.Max(0, receipt.ParticipantTotalTokens),
            IssueFingerprints = (receipt.IssueFingerprints ?? Array.Empty<string>())
                .Where(static value => !string.IsNullOrWhiteSpace(value))
                .Select(static value => value.Trim())
                .Distinct(StringComparer.OrdinalIgnoreCase)
                .ToArray(),
            SignedByFleet = AccountService.NormalizeOptional(receipt.SignedByFleet),
        };

    private static string ProjectionFingerprint(ContributionReceiptDto receipt)
    {
        var payload = $"{receipt.ReceiptId}|{receipt.EventKind}|{receipt.ProjectId}|{receipt.UserId}|{receipt.GroupId}|{receipt.SponsorSessionId}|{receipt.LandedSha}";
        var hash = SHA256.HashData(Encoding.UTF8.GetBytes(payload));
        return Convert.ToHexString(hash[..8]).ToLowerInvariant();
    }
}
