using Chummer.Run.Contracts.Boosters;
using Chummer.Run.Contracts.Ledger;
using Chummer.Run.Contracts.Leaderboards;

namespace Chummer.Run.Api.Services.Community;

public sealed class RewardService
{
    private readonly CommunityStore _store;

    public RewardService(CommunityStore store)
    {
        _store = store;
    }

    public int ApplyReceipt(ContributionReceiptDto receipt)
    {
        var points = ScoreReceipt(receipt);
        if (points <= 0 || string.IsNullOrWhiteSpace(receipt.UserId))
        {
            return 0;
        }

        lock (_store.Gate)
        {
            if (_store.RewardEntries.Any(entry => string.Equals(entry.SourceReceiptId, receipt.ReceiptId, StringComparison.OrdinalIgnoreCase)))
            {
                return _store.RewardEntries
                    .Where(entry => string.Equals(entry.SourceReceiptId, receipt.ReceiptId, StringComparison.OrdinalIgnoreCase))
                    .Sum(entry => entry.Points);
            }

            _store.RewardEntries.Add(
                new RewardJournalEntryDto(
                    RewardEntryId: AccountService.NewId("rwd"),
                    UserId: receipt.UserId!,
                    GroupId: AccountService.NormalizeOptional(receipt.GroupId),
                    RewardKind: RewardKind(receipt),
                    Points: points,
                    SourceReceiptId: receipt.ReceiptId,
                    Description: RewardDescription(receipt, points),
                    GrantedAtUtc: DateTimeOffset.UtcNow));

            MaybeAddBadgeLocked(receipt);
            return points;
        }
    }

    public IReadOnlyList<RewardJournalEntryDto> ListRewardsForUser(string userId)
    {
        lock (_store.Gate)
        {
            return _store.RewardEntries
                .Where(entry => string.Equals(entry.UserId, userId, StringComparison.OrdinalIgnoreCase))
                .OrderByDescending(entry => entry.GrantedAtUtc)
                .ToArray();
        }
    }

    public IReadOnlyList<BadgeDto> ListBadgesForUser(string userId)
    {
        lock (_store.Gate)
        {
            return _store.Badges
                .Where(badge => string.Equals(badge.UserId, userId, StringComparison.OrdinalIgnoreCase))
                .OrderBy(badge => badge.AwardedAtUtc)
                .ToArray();
        }
    }

    private static int ScoreReceipt(ContributionReceiptDto receipt)
    {
        var eventKind = (receipt.EventKind ?? string.Empty).Trim().ToLowerInvariant();
        var points = eventKind switch
        {
            "lane_activated" => 1,
            "slice_reviewed" when receipt.Verified => 5,
            "slice_landed" when receipt.Verified => 15,
            _ => 0,
        };
        if (string.Equals(eventKind, "slice_landed", StringComparison.OrdinalIgnoreCase))
        {
            if (string.Equals(receipt.AcceptedOnRound, "1", StringComparison.OrdinalIgnoreCase))
            {
                points += 5;
            }
            else if (string.Equals(receipt.AcceptedOnRound, "2", StringComparison.OrdinalIgnoreCase))
            {
                points += 2;
            }

            if (!receipt.PaidLaneUsed || receipt.CoreMs <= 0)
            {
                points += 3;
            }
        }

        return points;
    }

    private static string RewardKind(ContributionReceiptDto receipt)
        => string.Equals(receipt.EventKind, "slice_landed", StringComparison.OrdinalIgnoreCase) ? "impact_points" : "participation_points";

    private static string RewardDescription(ContributionReceiptDto receipt, int points)
        => $"{receipt.EventKind} on {receipt.ProjectId} minted {points} points.";

    private void MaybeAddBadgeLocked(ContributionReceiptDto receipt)
    {
        if (string.IsNullOrWhiteSpace(receipt.UserId))
        {
            return;
        }

        var userId = receipt.UserId!;
        if (string.Equals(receipt.EventKind, "lane_activated", StringComparison.OrdinalIgnoreCase)
            && _store.Badges.All(badge => !(badge.UserId == userId && badge.Key == "booster-starter")))
        {
            _store.Badges.Add(new BadgeDto("badge-booster-starter", userId, "booster-starter", "Booster Starter", DateTimeOffset.UtcNow));
        }

        if (string.Equals(receipt.EventKind, "slice_landed", StringComparison.OrdinalIgnoreCase)
            && receipt.Verified
            && _store.Badges.All(badge => !(badge.UserId == userId && badge.Key == "jury-finisher")))
        {
            _store.Badges.Add(new BadgeDto("badge-jury-finisher", userId, "jury-finisher", "Jury Finisher", DateTimeOffset.UtcNow));
        }
    }
}
