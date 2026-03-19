using Chummer.Run.Contracts.Boosters;
using Chummer.Run.Contracts.Ledger;
using Chummer.Run.Contracts.Leaderboards;

namespace Chummer.Run.Api.Services.Community;

public sealed class RewardService
{
    private readonly CommunityStore _store;
    private static readonly StringComparer Comparer = StringComparer.OrdinalIgnoreCase;

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

    public IReadOnlyList<BadgeDto> ListBadgesForUser(string userId, string? status = null, string? badgeKind = null)
    {
        lock (_store.Gate)
        {
            return _store.Badges
                .Where(badge => string.Equals(badge.UserId, userId, StringComparison.OrdinalIgnoreCase))
                .Where(badge => string.IsNullOrWhiteSpace(status) || string.Equals(badge.Status, status, StringComparison.OrdinalIgnoreCase))
                .Where(badge => string.IsNullOrWhiteSpace(badgeKind) || string.Equals(badge.BadgeKind, badgeKind, StringComparison.OrdinalIgnoreCase))
                .OrderBy(badge => badge.AwardedAtUtc)
                .ToArray();
        }
    }

    public bool AwardBadgeIfMissing(
        string userId,
        string key,
        string label,
        string badgeScope = "user",
        string badgeKind = "persistent",
        string? sourceSponsorSessionId = null)
    {
        var normalizedUserId = AccountService.NormalizeOptional(userId);
        var normalizedKey = NormalizeBadgeKey(AccountService.NormalizeOptional(key));
        var normalizedLabel = AccountService.NormalizeOptional(label);
        var normalizedScope = AccountService.NormalizeOptional(badgeScope) ?? "user";
        var normalizedKind = AccountService.NormalizeOptional(badgeKind) ?? "persistent";
        var normalizedSourceSessionId = AccountService.NormalizeOptional(sourceSponsorSessionId);
        if (normalizedUserId is null || normalizedKey is null || normalizedLabel is null)
        {
            return false;
        }

        lock (_store.Gate)
        {
            if (TryFindActiveBadgeLocked(normalizedUserId, normalizedKey, normalizedSourceSessionId) is not null)
            {
                return false;
            }

            _store.Badges.Add(new BadgeDto(
                BadgeId: $"badge-{normalizedKey}-{Guid.NewGuid():N}",
                UserId: normalizedUserId,
                Key: normalizedKey,
                Label: normalizedLabel,
                AwardedAtUtc: DateTimeOffset.UtcNow,
                BadgeScope: normalizedScope,
                BadgeKind: normalizedKind,
                Status: "active",
                RevokedAtUtc: null,
                RevocationReason: null,
                SourceSponsorSessionId: normalizedSourceSessionId));
            _store.PersistLocked();
            return true;
        }
    }

    public bool RevokeBadgeIfActive(string userId, string key, string reason, string? sourceSponsorSessionId = null)
    {
        var normalizedUserId = AccountService.NormalizeOptional(userId);
        var normalizedKey = NormalizeBadgeKey(AccountService.NormalizeOptional(key));
        var normalizedReason = AccountService.NormalizeOptional(reason) ?? "superseded";
        var normalizedSourceSessionId = AccountService.NormalizeOptional(sourceSponsorSessionId);
        if (normalizedUserId is null || normalizedKey is null)
        {
            return false;
        }

        lock (_store.Gate)
        {
            var badgeIndex = FindActiveBadgeIndexLocked(normalizedUserId, normalizedKey, normalizedSourceSessionId);
            if (badgeIndex < 0)
            {
                return false;
            }

            _store.Badges[badgeIndex] = _store.Badges[badgeIndex] with
            {
                Status = "revoked",
                RevokedAtUtc = DateTimeOffset.UtcNow,
                RevocationReason = normalizedReason,
            };
            _store.PersistLocked();
            return true;
        }
    }

    public int RevokeBadgesIfActive(string userId, IEnumerable<string> keys, string reason)
    {
        var normalizedUserId = AccountService.NormalizeOptional(userId);
        var normalizedKeys = keys
            .Select(key => NormalizeBadgeKey(AccountService.NormalizeOptional(key)))
            .Where(static key => key is not null)
            .Cast<string>()
            .Distinct(Comparer)
            .ToArray();
        var normalizedReason = AccountService.NormalizeOptional(reason) ?? "superseded";
        if (normalizedUserId is null || normalizedKeys.Length == 0)
        {
            return 0;
        }

        lock (_store.Gate)
        {
            var revoked = 0;
            for (var index = 0; index < _store.Badges.Count; index++)
            {
                var badge = _store.Badges[index];
                if (!string.Equals(badge.UserId, normalizedUserId, StringComparison.OrdinalIgnoreCase)
                    || !string.Equals(badge.Status, "active", StringComparison.OrdinalIgnoreCase)
                    || !normalizedKeys.Contains(NormalizeBadgeKey(badge.Key) ?? string.Empty, Comparer))
                {
                    continue;
                }

                _store.Badges[index] = badge with
                {
                    Status = "revoked",
                    RevokedAtUtc = DateTimeOffset.UtcNow,
                    RevocationReason = normalizedReason,
                };
                revoked++;
            }

            if (revoked > 0)
            {
                _store.PersistLocked();
            }

            return revoked;
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
            && TryFindActiveBadgeLocked(userId, "booster-starter", null) is null)
        {
            _store.Badges.Add(new BadgeDto(
                BadgeId: $"badge-booster-starter-{Guid.NewGuid():N}",
                UserId: userId,
                Key: "booster-starter",
                Label: "Booster Starter",
                AwardedAtUtc: DateTimeOffset.UtcNow,
                BadgeScope: "user",
                BadgeKind: "persistent",
                Status: "active"));
        }

        if (string.Equals(receipt.EventKind, "slice_landed", StringComparison.OrdinalIgnoreCase)
            && receipt.Verified
            && TryFindActiveBadgeLocked(userId, "jury-finisher", null) is null)
        {
            _store.Badges.Add(new BadgeDto(
                BadgeId: $"badge-jury-finisher-{Guid.NewGuid():N}",
                UserId: userId,
                Key: "jury-finisher",
                Label: "Jury Finisher",
                AwardedAtUtc: DateTimeOffset.UtcNow,
                BadgeScope: "user",
                BadgeKind: "persistent",
                Status: "active"));
        }
    }

    private BadgeDto? TryFindActiveBadgeLocked(string userId, string key, string? sourceSponsorSessionId)
        => FindActiveBadgeIndexLocked(userId, key, sourceSponsorSessionId) is var index && index >= 0 ? _store.Badges[index] : null;

    private int FindActiveBadgeIndexLocked(string userId, string key, string? sourceSponsorSessionId)
    {
        var normalizedKey = NormalizeBadgeKey(key);
        var normalizedSourceSessionId = AccountService.NormalizeOptional(sourceSponsorSessionId);
        for (var index = 0; index < _store.Badges.Count; index++)
        {
            var badge = _store.Badges[index];
            if (string.Equals(badge.UserId, userId, StringComparison.OrdinalIgnoreCase)
                && string.Equals(badge.Status, "active", StringComparison.OrdinalIgnoreCase)
                && string.Equals(NormalizeBadgeKey(badge.Key), normalizedKey, StringComparison.OrdinalIgnoreCase)
                && (normalizedSourceSessionId is null
                    || string.Equals(AccountService.NormalizeOptional(badge.SourceSponsorSessionId) ?? string.Empty, normalizedSourceSessionId, StringComparison.OrdinalIgnoreCase)))
            {
                return index;
            }
        }

        return -1;
    }

    private static string? NormalizeBadgeKey(string? key)
        => (key ?? string.Empty).Trim().ToLowerInvariant() switch
        {
            "" => null,
            "chickend-out" => "chickened-out",
            _ => (key ?? string.Empty).Trim().ToLowerInvariant(),
        };

}
