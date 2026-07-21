using System.Security.Cryptography;
using System.Text;
using Chummer.Contracts.Receipts;
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
            if (canonicalReceipt.GroupId is { } groupId
                && !_store.GroupsById.ContainsKey(groupId))
            {
                throw new KeyNotFoundException($"Unknown group: {groupId}");
            }

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

            int receiptCount = _store.Receipts.Count;
            int ledgerCount = _store.LedgerEntries.Count;
            int rewardCount = _store.RewardEntries.Count;
            int entitlementCount = _store.EntitlementEntries.Count;
            int badgeCount = _store.Badges.Count;
            try
            {
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

                var mintedPoints = _rewards.ApplyReceipt(canonicalReceipt);
                var granted = _entitlements.ApplyReceipt(canonicalReceipt, mintedPoints);
                _store.LedgerPersistenceFaultInjector?.Invoke();
                _store.PersistLocked();
                return new ReceiptIngestResultDto(
                    ReceiptId: canonicalReceipt.ReceiptId,
                    Status: "ingested",
                    MintedPoints: mintedPoints,
                    GrantedEntitlements: granted,
                    ProjectionFingerprint: ProjectionFingerprint(canonicalReceipt),
                    IngestedAtUtc: DateTimeOffset.UtcNow);
            }
            catch
            {
                RemoveAppended(_store.Receipts, receiptCount);
                RemoveAppended(_store.LedgerEntries, ledgerCount);
                RemoveAppended(_store.RewardEntries, rewardCount);
                RemoveAppended(_store.EntitlementEntries, entitlementCount);
                RemoveAppended(_store.Badges, badgeCount);
                throw;
            }
        }
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
    {
        string receiptId = AccountService.NormalizeRequired(receipt.ReceiptId, nameof(receipt.ReceiptId));
        string eventKind = AccountService.NormalizeRequired(receipt.EventKind, nameof(receipt.EventKind));
        string laneId = AccountService.NormalizeRequired(receipt.LaneId, nameof(receipt.LaneId));
        string projectId = AccountService.NormalizeRequired(receipt.ProjectId, nameof(receipt.ProjectId));
        string? userId = AccountService.NormalizeOptional(receipt.UserId);
        string? groupId = AccountService.NormalizeOptional(receipt.GroupId);

        return receipt with
        {
            ReceiptId = receiptId,
            EventKind = eventKind,
            LaneId = laneId,
            ProjectId = projectId,
            UserId = userId,
            GroupId = groupId,
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
            Envelope = receipt.Envelope ?? ReceiptEnvelopeFactory.Runtime(
                receiptKind: "community_contribution",
                ownerScope: string.IsNullOrWhiteSpace(groupId) ? "community.user" : "community.group",
                exposureClass: ReceiptExposureClasses.SignedIn,
                evidenceRef: receiptId,
                reviewState: receipt.Verified ? "verified" : "pending")
        };
    }

    private static string ProjectionFingerprint(ContributionReceiptDto receipt)
    {
        var payload = $"{receipt.ReceiptId}|{receipt.EventKind}|{receipt.ProjectId}|{receipt.UserId}|{receipt.GroupId}|{receipt.SponsorSessionId}|{receipt.LandedSha}";
        var hash = SHA256.HashData(Encoding.UTF8.GetBytes(payload));
        return Convert.ToHexString(hash[..8]).ToLowerInvariant();
    }

    private static void RemoveAppended<T>(List<T> items, int originalCount)
    {
        if (items.Count > originalCount)
        {
            items.RemoveRange(originalCount, items.Count - originalCount);
        }
    }
}
