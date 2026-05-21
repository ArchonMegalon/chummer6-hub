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
            var rows = _store.UsersById.Keys
                .Distinct(StringComparer.OrdinalIgnoreCase)
                .Select(BuildUserMetricsLocked)
                .Where(row => !publicOnly || (string.Equals(row.Visibility, "public", StringComparison.OrdinalIgnoreCase) && row.PublicContributionProfileOptIn))
                .OrderByDescending(row => row.Points)
                .ThenByDescending(row => row.ParticipantTotalTokens)
                .ThenBy(row => row.DisplayName, StringComparer.OrdinalIgnoreCase)
                .Take(Math.Max(1, limit))
                .ToArray();
            return rows.Select((row, index) => new LeaderboardRowDto(
                Rank: index + 1,
                UserId: row.UserId,
                DisplayName: row.DisplayName,
                Points: row.Points,
                ContributionCount: row.ContributionCount,
                LandedSlices: row.LandedSlices,
                VerifiedSlices: row.VerifiedSlices,
                ParticipantTotalTokens: row.ParticipantTotalTokens,
                ParticipantCodexCode: row.ParticipantCodexCode,
                BadgeCount: row.BadgeCount,
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
                .Where(row => !publicOnly || (string.Equals(row.Visibility, "public", StringComparison.OrdinalIgnoreCase) && row.PublicContributionProfileOptIn))
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
                ContributionCount: row.ContributionCount,
                CurrentAuthorizationTier: row.CurrentAuthorizationTier,
                CurrentSponsorBonus: row.CurrentSponsorBonus,
                CurrentRankScore: row.CurrentRankScore,
                ActiveSponsorSessions: row.ActiveSessions,
                LandedSlices: row.LandedSlices,
                VerifiedSlices: row.VerifiedSlices,
                ParticipantTotalTokens: row.ParticipantTotalTokens,
                ParticipantCodexCode: row.ParticipantCodexCode,
                CurrentStatusBadges: row.CurrentStatusBadges.Select(static badge => badge.Key).ToArray(),
                PersistentBadges: row.PersistentBadges.Select(static badge => badge.Key).ToArray(),
                Visibility: row.Visibility)).ToArray();
        }
    }

    public IReadOnlyList<CodexUsageLeaderboardRowDto> CodexUsageLeaderboard(int limit = 20, bool publicOnly = false)
    {
        lock (_store.Gate)
        {
            var rows = _store.UsersById.Keys
                .Distinct(StringComparer.OrdinalIgnoreCase)
                .Select(BuildUserMetricsLocked)
                .Where(row => row.ContributionCount > 0 && row.ParticipantTotalTokens > 0 && !string.IsNullOrWhiteSpace(row.ParticipantCodexCode))
                .Where(row => !publicOnly || (string.Equals(row.Visibility, "public", StringComparison.OrdinalIgnoreCase) && row.PublicContributionProfileOptIn))
                .OrderByDescending(row => row.ParticipantTotalTokens)
                .ThenByDescending(row => row.LandedSlices)
                .ThenBy(row => row.DisplayName, StringComparer.OrdinalIgnoreCase)
                .Take(Math.Max(1, limit))
                .ToArray();

            return rows.Select((row, index) => new CodexUsageLeaderboardRowDto(
                Rank: index + 1,
                UserId: row.UserId,
                DisplayName: row.DisplayName,
                ParticipantCodexCode: row.ParticipantCodexCode,
                ParticipantTotalTokens: row.ParticipantTotalTokens,
                ReceiptCount: row.ContributionCount,
                LandedSlices: row.LandedSlices,
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
                ContributionCount: metrics.ContributionCount,
                CurrentSponsorRankScore: metrics.CurrentRankScore,
                CurrentAuthorizationTier: metrics.CurrentAuthorizationTier,
                CurrentTierSource: metrics.CurrentTierSource,
                CurrentSponsorBonus: metrics.CurrentSponsorBonus,
                LandedSlices: metrics.LandedSlices,
                VerifiedSlices: metrics.VerifiedSlices,
                ParticipantTotalTokens: metrics.ParticipantTotalTokens,
                ParticipantCodexCode: metrics.ParticipantCodexCode,
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
        var receipts = _store.Receipts
            .Where(receipt => string.Equals(receipt.UserId, userId, StringComparison.OrdinalIgnoreCase))
            .ToArray();
        var points = _store.RewardEntries
            .Where(entry => string.Equals(entry.UserId, userId, StringComparison.OrdinalIgnoreCase))
            .Sum(entry => entry.Points);
        var landedSlices = receipts.Count(receipt => string.Equals(receipt.EventKind, "slice_landed", StringComparison.OrdinalIgnoreCase));
        var verifiedSlices = receipts.Count(receipt => receipt.Verified);
        var contributionCount = receipts.Length;
        var participantTotalTokens = receipts.Sum(receipt => Math.Max(0, receipt.ParticipantTotalTokens));
        var participantCodexCode = receipts
            .Where(receipt => !string.IsNullOrWhiteSpace(receipt.ParticipantCodexCode))
            .OrderByDescending(receipt => receipt.EndedAtUtc ?? receipt.LandedAtUtc ?? receipt.StartedAtUtc ?? DateTimeOffset.MinValue)
            .Select(receipt => receipt.ParticipantCodexCode)
            .FirstOrDefault();
        var activeSessions = currentSessions.Length;
        var currentTier = SponsorStatusPolicy.NormalizeAuthorizationTier(bestCurrentSession?.AuthorizationTier);
        var currentTierSource = SponsorStatusPolicy.NormalizeTierSource(bestCurrentSession?.TierSource);
        var currentSponsorBonus = SponsorStatusPolicy.TierBonus(currentTier) + (activeSessions > 0 ? SponsorStatusPolicy.ActiveSessionBonus : 0);
        bool publicContributionProfileOptIn = _store.UserExperienceByUserId.TryGetValue(userId, out var experience)
            && experience.PublicContributionProfileOptIn;
        var badgeCount = activeStatusBadges.Length + persistentBadges.Length;

        return new UserMetrics(
            UserId: userId,
            DisplayName: user?.DisplayName ?? userId,
            Visibility: user?.Visibility ?? "private",
            Points: points,
            ContributionCount: contributionCount,
            LandedSlices: landedSlices,
            VerifiedSlices: verifiedSlices,
            ParticipantTotalTokens: participantTotalTokens,
            ParticipantCodexCode: participantCodexCode,
            BadgeCount: badgeCount,
            ActiveSessions: activeSessions,
            CurrentAuthorizationTier: currentTier,
            CurrentTierSource: currentTierSource,
            CurrentSponsorBonus: currentSponsorBonus,
            CurrentRankScore: points + currentSponsorBonus,
            PublicContributionProfileOptIn: publicContributionProfileOptIn,
            CurrentStatusBadges: activeStatusBadges,
            PersistentBadges: persistentBadges,
            RevokedBadges: revokedBadges);
    }

    private sealed record UserMetrics(
        string UserId,
        string DisplayName,
        string Visibility,
        int Points,
        int ContributionCount,
        int LandedSlices,
        int VerifiedSlices,
        int ParticipantTotalTokens,
        string? ParticipantCodexCode,
        int BadgeCount,
        int ActiveSessions,
        string CurrentAuthorizationTier,
        string CurrentTierSource,
        int CurrentSponsorBonus,
        int CurrentRankScore,
        bool PublicContributionProfileOptIn,
        IReadOnlyList<BadgeDto> CurrentStatusBadges,
        IReadOnlyList<BadgeDto> PersistentBadges,
        IReadOnlyList<BadgeDto> RevokedBadges);
}
