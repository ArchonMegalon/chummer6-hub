using Chummer.Run.Contracts.Leaderboards;

namespace Chummer.Run.Api.Services.Community;

public sealed class LeaderboardService
{
    private readonly CommunityStore _store;

    public LeaderboardService(CommunityStore store)
    {
        _store = store;
    }

    public IReadOnlyList<LeaderboardRowDto> IndividualLeaderboard(int limit = 20, bool publicOnly = false)
    {
        lock (_store.Gate)
        {
            var rows = _store.RewardEntries
                .GroupBy(entry => entry.UserId, StringComparer.OrdinalIgnoreCase)
                .Select(group => BuildUserMetricsLocked(group.Key))
                .Where(row => !publicOnly || string.Equals(row.Visibility, "public", StringComparison.OrdinalIgnoreCase))
                .OrderByDescending(row => row.Points)
                .ThenBy(row => row.DisplayName, StringComparer.OrdinalIgnoreCase)
                .Take(Math.Max(1, limit))
                .ToArray();
            return rows.Select((row, index) => new LeaderboardRowDto(
                Rank: index + 1,
                UserId: row.UserId,
                DisplayName: row.DisplayName,
                Points: row.Points,
                LandedSlices: row.LandedSlices,
                VerifiedSlices: row.VerifiedSlices,
                ActiveSessions: row.ActiveSessions,
                Visibility: row.Visibility)).ToArray();
        }
    }

    public IReadOnlyList<SponsorRankLeaderboardRowDto> SponsorRankLeaderboard(int limit = 20, bool publicOnly = false)
    {
        lock (_store.Gate)
        {
            var rows = _store.UsersById.Keys
                .Distinct(StringComparer.OrdinalIgnoreCase)
                .Select(BuildUserMetricsLocked)
                .Where(row => !publicOnly || string.Equals(row.Visibility, "public", StringComparison.OrdinalIgnoreCase))
                .Where(row => row.Points > 0 || row.ActiveSessions > 0 || row.CurrentSponsorBonus > 0)
                .OrderByDescending(row => row.CurrentRankScore)
                .ThenByDescending(row => row.Points)
                .ThenBy(row => row.DisplayName, StringComparer.OrdinalIgnoreCase)
                .Take(Math.Max(1, limit))
                .ToArray();

            return rows.Select((row, index) => new SponsorRankLeaderboardRowDto(
                Rank: index + 1,
                UserId: row.UserId,
                DisplayName: row.DisplayName,
                LifetimePoints: row.Points,
                CurrentAuthorizationTier: row.CurrentAuthorizationTier,
                CurrentSponsorBonus: row.CurrentSponsorBonus,
                CurrentRankScore: row.CurrentRankScore,
                ActiveSponsorSessions: row.ActiveSessions,
                LandedSlices: row.LandedSlices,
                CurrentStatusBadges: row.CurrentStatusBadges.Select(static badge => badge.Key).ToArray(),
                PersistentBadges: row.PersistentBadges.Select(static badge => badge.Key).ToArray(),
                Visibility: row.Visibility)).ToArray();
        }
    }

    public IReadOnlyList<GroupLeaderboardRowDto> GroupLeaderboard(int limit = 20, bool publicOnly = false)
    {
        lock (_store.Gate)
        {
            var rows = _store.RewardEntries
                .Where(entry => !string.IsNullOrWhiteSpace(entry.GroupId))
                .GroupBy(entry => entry.GroupId!, StringComparer.OrdinalIgnoreCase)
                .Select(group =>
                {
                    _store.GroupsById.TryGetValue(group.Key, out var hubGroup);
                    var landedSlices = _store.Receipts.Count(receipt =>
                        string.Equals(receipt.GroupId, group.Key, StringComparison.OrdinalIgnoreCase)
                        && string.Equals(receipt.EventKind, "slice_landed", StringComparison.OrdinalIgnoreCase));
                    var activeSessions = _store.SponsorSessionsById.Values.Count(session =>
                        string.Equals(session.GroupId, group.Key, StringComparison.OrdinalIgnoreCase)
                        && string.Equals(session.Status, "active", StringComparison.OrdinalIgnoreCase));
                    return new
                    {
                        GroupId = group.Key,
                        GroupName = hubGroup?.Name ?? group.Key,
                        Visibility = hubGroup?.Visibility ?? "private",
                        Points = group.Sum(entry => entry.Points),
                        LandedSlices = landedSlices,
                        ActiveSessions = activeSessions,
                    };
                })
                .Where(row => !publicOnly || !string.Equals(row.Visibility, "private", StringComparison.OrdinalIgnoreCase))
                .OrderByDescending(row => row.Points)
                .ThenBy(row => row.GroupName, StringComparer.OrdinalIgnoreCase)
                .Take(Math.Max(1, limit))
                .ToArray();
            return rows.Select((row, index) => new GroupLeaderboardRowDto(
                Rank: index + 1,
                GroupId: row.GroupId,
                GroupName: row.GroupName,
                Points: row.Points,
                LandedSlices: row.LandedSlices,
                ActiveSessions: row.ActiveSessions)).ToArray();
        }
    }

    public IReadOnlyList<QuestDto> Quests()
    {
        lock (_store.Gate)
        {
            var landed = _store.Receipts.Count(receipt => string.Equals(receipt.EventKind, "slice_landed", StringComparison.OrdinalIgnoreCase));
            var reviewed = _store.Receipts.Count(receipt =>
                string.Equals(receipt.EventKind, "slice_reviewed", StringComparison.OrdinalIgnoreCase)
                && receipt.Verified);
            return
            [
                new QuestDto("quest-review-slices", "Review 5 sponsored slices", "Complete five verified sponsor-backed review passes.", reviewed, 5, reviewed >= 5 ? "done" : "in_progress"),
                new QuestDto("quest-land-slices", "Land 10 sponsored slices", "Help land ten verified sponsor-backed slices.", landed, 10, landed >= 10 ? "done" : "in_progress")
            ];
        }
    }

    public UserRecognitionSummaryDto UserRecognitionSummary(string userId)
    {
        lock (_store.Gate)
        {
            var metrics = BuildUserMetricsLocked(userId);
            return new UserRecognitionSummaryDto(
                UserId: metrics.UserId,
                LifetimePoints: metrics.Points,
                CurrentSponsorRankScore: metrics.CurrentRankScore,
                CurrentAuthorizationTier: metrics.CurrentAuthorizationTier,
                CurrentTierSource: metrics.CurrentTierSource,
                CurrentSponsorBonus: metrics.CurrentSponsorBonus,
                LandedSlices: metrics.LandedSlices,
                ActiveSessionCount: metrics.ActiveSessions,
                CurrentStatusBadges: metrics.CurrentStatusBadges.ToArray(),
                PersistentBadges: metrics.PersistentBadges.ToArray(),
                RevokedBadges: metrics.RevokedBadges.ToArray());
        }
    }

    private UserMetrics BuildUserMetricsLocked(string userId)
    {
        _store.UsersById.TryGetValue(userId, out var user);
        var sessions = _store.SponsorSessionsById.Values
            .Where(session => string.Equals(session.UserId, userId, StringComparison.OrdinalIgnoreCase))
            .ToArray();
        var currentSessions = sessions
            .Where(session => SponsorStatusPolicy.IsCurrentSponsorSession(session.Status, session.AuthorizedAtUtc))
            .ToArray();
        var bestCurrentSession = currentSessions
            .OrderByDescending(session => SponsorStatusPolicy.TierPriority(session.AuthorizationTier))
            .ThenByDescending(session => session.AuthorizedAtUtc ?? session.ActivatedAtUtc ?? session.UpdatedAtUtc)
            .FirstOrDefault();
        var activeStatusBadges = _store.Badges
            .Where(badge =>
                string.Equals(badge.UserId, userId, StringComparison.OrdinalIgnoreCase)
                && string.Equals(badge.Status, "active", StringComparison.OrdinalIgnoreCase)
                && string.Equals(badge.BadgeKind, "transient", StringComparison.OrdinalIgnoreCase))
            .OrderByDescending(badge => badge.AwardedAtUtc)
            .ToArray();
        var persistentBadges = _store.Badges
            .Where(badge =>
                string.Equals(badge.UserId, userId, StringComparison.OrdinalIgnoreCase)
                && string.Equals(badge.Status, "active", StringComparison.OrdinalIgnoreCase)
                && string.Equals(badge.BadgeKind, "persistent", StringComparison.OrdinalIgnoreCase))
            .OrderByDescending(badge => badge.AwardedAtUtc)
            .ToArray();
        var revokedBadges = _store.Badges
            .Where(badge =>
                string.Equals(badge.UserId, userId, StringComparison.OrdinalIgnoreCase)
                && string.Equals(badge.Status, "revoked", StringComparison.OrdinalIgnoreCase))
            .OrderByDescending(badge => badge.RevokedAtUtc ?? badge.AwardedAtUtc)
            .ToArray();
        var points = _store.RewardEntries
            .Where(entry => string.Equals(entry.UserId, userId, StringComparison.OrdinalIgnoreCase))
            .Sum(entry => entry.Points);
        var landedSlices = _store.Receipts.Count(receipt =>
            string.Equals(receipt.UserId, userId, StringComparison.OrdinalIgnoreCase)
            && string.Equals(receipt.EventKind, "slice_landed", StringComparison.OrdinalIgnoreCase));
        var verifiedSlices = _store.Receipts.Count(receipt =>
            string.Equals(receipt.UserId, userId, StringComparison.OrdinalIgnoreCase)
            && receipt.Verified);
        var activeSessions = currentSessions.Length;
        var currentTier = SponsorStatusPolicy.NormalizeAuthorizationTier(bestCurrentSession?.AuthorizationTier);
        var currentTierSource = SponsorStatusPolicy.NormalizeTierSource(bestCurrentSession?.TierSource);
        var currentSponsorBonus = SponsorStatusPolicy.TierBonus(currentTier) + (activeSessions > 0 ? SponsorStatusPolicy.ActiveSessionBonus : 0);

        return new UserMetrics(
            UserId: userId,
            DisplayName: user?.DisplayName ?? userId,
            Visibility: user?.Visibility ?? "private",
            Points: points,
            LandedSlices: landedSlices,
            VerifiedSlices: verifiedSlices,
            ActiveSessions: activeSessions,
            CurrentAuthorizationTier: currentTier,
            CurrentTierSource: currentTierSource,
            CurrentSponsorBonus: currentSponsorBonus,
            CurrentRankScore: points + currentSponsorBonus,
            CurrentStatusBadges: activeStatusBadges,
            PersistentBadges: persistentBadges,
            RevokedBadges: revokedBadges);
    }

    private sealed record UserMetrics(
        string UserId,
        string DisplayName,
        string Visibility,
        int Points,
        int LandedSlices,
        int VerifiedSlices,
        int ActiveSessions,
        string CurrentAuthorizationTier,
        string CurrentTierSource,
        int CurrentSponsorBonus,
        int CurrentRankScore,
        IReadOnlyList<BadgeDto> CurrentStatusBadges,
        IReadOnlyList<BadgeDto> PersistentBadges,
        IReadOnlyList<BadgeDto> RevokedBadges);
}
