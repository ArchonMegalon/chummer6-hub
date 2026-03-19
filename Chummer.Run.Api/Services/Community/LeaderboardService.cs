using Chummer.Run.Contracts.Leaderboards;

namespace Chummer.Run.Api.Services.Community;

public sealed class LeaderboardService
{
    private readonly CommunityStore _store;

    public LeaderboardService(CommunityStore store)
    {
        _store = store;
    }

    public IReadOnlyList<LeaderboardRowDto> IndividualLeaderboard(int limit = 20)
    {
        lock (_store.Gate)
        {
            var rows = _store.RewardEntries
                .GroupBy(entry => entry.UserId, StringComparer.OrdinalIgnoreCase)
                .Select(group =>
                {
                    _store.UsersById.TryGetValue(group.Key, out var user);
                    var sourceReceipts = group
                        .Select(entry => entry.SourceReceiptId)
                        .Distinct(StringComparer.OrdinalIgnoreCase)
                        .ToArray();
                    var landedSlices = _store.Receipts.Count(receipt =>
                        string.Equals(receipt.UserId, group.Key, StringComparison.OrdinalIgnoreCase)
                        && string.Equals(receipt.EventKind, "slice_landed", StringComparison.OrdinalIgnoreCase));
                    var verifiedSlices = _store.Receipts.Count(receipt =>
                        string.Equals(receipt.UserId, group.Key, StringComparison.OrdinalIgnoreCase)
                        && receipt.Verified);
                    var activeSessions = _store.SponsorSessionsById.Values.Count(session =>
                        string.Equals(session.UserId, group.Key, StringComparison.OrdinalIgnoreCase)
                        && string.Equals(session.Status, "active", StringComparison.OrdinalIgnoreCase));
                    return new
                    {
                        UserId = group.Key,
                        DisplayName = user?.DisplayName ?? group.Key,
                        Visibility = user?.Visibility ?? "private",
                        Points = group.Sum(entry => entry.Points),
                        LandedSlices = landedSlices,
                        VerifiedSlices = verifiedSlices,
                        ActiveSessions = activeSessions,
                    };
                })
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

    public IReadOnlyList<GroupLeaderboardRowDto> GroupLeaderboard(int limit = 20)
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
                        Points = group.Sum(entry => entry.Points),
                        LandedSlices = landedSlices,
                        ActiveSessions = activeSessions,
                    };
                })
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
            var activated = _store.Receipts.Count(receipt => string.Equals(receipt.EventKind, "lane_activated", StringComparison.OrdinalIgnoreCase));
            return
            [
                new QuestDto("quest-launch-lanes", "Launch 5 sponsor lanes", "Open and activate five community-sponsored premium burst lanes.", activated, 5, activated >= 5 ? "done" : "in_progress"),
                new QuestDto("quest-land-slices", "Land 10 sponsored slices", "Help land ten verified sponsor-backed slices.", landed, 10, landed >= 10 ? "done" : "in_progress")
            ];
        }
    }
}
