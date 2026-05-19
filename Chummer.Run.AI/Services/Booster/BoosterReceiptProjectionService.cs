using System.Security.Cryptography;
using System.Text;
using Chummer.Run.Contracts.Boosters;
using Chummer.Run.Contracts.Ledger;
using Chummer.Run.Contracts.Leaderboards;

namespace Chummer.Run.AI.Services.Booster;

public sealed class BoosterReceiptProjectionService
{
    private readonly object _gate = new();
    private readonly List<ContributionReceiptDto> _receipts = new();

    public ReceiptIngestResultDto Ingest(ContributionReceiptDto receipt)
    {
        lock (_gate)
        {
            if (_receipts.Any(existing => string.Equals(existing.ReceiptId, receipt.ReceiptId, StringComparison.OrdinalIgnoreCase)))
            {
                return new ReceiptIngestResultDto(
                    ReceiptId: receipt.ReceiptId,
                    Status: "duplicate",
                    MintedPoints: Score(receipt),
                    GrantedEntitlements: Array.Empty<string>(),
                    ProjectionFingerprint: Fingerprint(receipt),
                    IngestedAtUtc: DateTimeOffset.UtcNow);
            }

            _receipts.Add(receipt);
        }

        return new ReceiptIngestResultDto(
            ReceiptId: receipt.ReceiptId,
            Status: "projected",
            MintedPoints: Score(receipt),
            GrantedEntitlements: Array.Empty<string>(),
            ProjectionFingerprint: Fingerprint(receipt),
            IngestedAtUtc: DateTimeOffset.UtcNow);
    }

    public SponsorSessionProjectionDto SessionProjection(string sponsorSessionId)
    {
        lock (_gate)
        {
            var rows = _receipts
                .Where(receipt => string.Equals(receipt.SponsorSessionId, sponsorSessionId, StringComparison.OrdinalIgnoreCase))
                .ToArray();
            return new SponsorSessionProjectionDto(
                SponsorSessionId: sponsorSessionId,
                Status: rows.Any(receipt => string.Equals(receipt.EventKind, "lane_stopped", StringComparison.OrdinalIgnoreCase)) ? "stopped" : rows.Length > 0 ? "active" : "unknown",
                ReceiptCount: rows.Length,
                LandedSlices: rows.Count(receipt => string.Equals(receipt.EventKind, "slice_landed", StringComparison.OrdinalIgnoreCase)),
                EstimatedPoints: rows.Sum(Score),
                LastReceiptAtUtc: rows.OrderByDescending(receipt => receipt.EndedAtUtc ?? receipt.LandedAtUtc ?? receipt.StartedAtUtc).FirstOrDefault()?.EndedAtUtc
                    ?? rows.OrderByDescending(receipt => receipt.LandedAtUtc ?? receipt.StartedAtUtc).FirstOrDefault()?.LandedAtUtc
                    ?? rows.OrderByDescending(receipt => receipt.StartedAtUtc).FirstOrDefault()?.StartedAtUtc,
                ActiveLaneIds: rows.Select(receipt => receipt.LaneId).Where(static value => !string.IsNullOrWhiteSpace(value)).Distinct(StringComparer.OrdinalIgnoreCase).ToArray());
        }
    }

    public GroupContributionProjectionDto GroupProjection(string groupId)
    {
        lock (_gate)
        {
            var rows = _receipts
                .Where(receipt => string.Equals(receipt.GroupId, groupId, StringComparison.OrdinalIgnoreCase))
                .ToArray();
            return new GroupContributionProjectionDto(
                GroupId: groupId,
                ReceiptCount: rows.Length,
                LandedSlices: rows.Count(receipt => string.Equals(receipt.EventKind, "slice_landed", StringComparison.OrdinalIgnoreCase)),
                EstimatedPoints: rows.Sum(Score),
                ActiveSponsorSessionIds: rows
                    .Select(receipt => receipt.SponsorSessionId)
                    .Where(static value => !string.IsNullOrWhiteSpace(value))
                    .Distinct(StringComparer.OrdinalIgnoreCase)
                    .Cast<string>()
                    .ToArray());
        }
    }

    public object LeaderboardProjection()
    {
        lock (_gate)
        {
            var individualRows = _receipts
                .Where(receipt => !string.IsNullOrWhiteSpace(receipt.UserId))
                .GroupBy(receipt => receipt.UserId!, StringComparer.OrdinalIgnoreCase)
                .Select(group => new LeaderboardRowDto(
                    Rank: 0,
                    UserId: group.Key,
                    DisplayName: group.Key,
                    Points: group.Sum(Score),
                    ContributionCount: group.Count(),
                    LandedSlices: group.Count(receipt => string.Equals(receipt.EventKind, "slice_landed", StringComparison.OrdinalIgnoreCase)),
                    VerifiedSlices: group.Count(receipt => receipt.Verified),
                    ParticipantTotalTokens: group.Sum(receipt => Math.Max(0, receipt.ParticipantTotalTokens)),
                    ParticipantCodexCode: group.Where(receipt => !string.IsNullOrWhiteSpace(receipt.ParticipantCodexCode)).Select(receipt => receipt.ParticipantCodexCode).LastOrDefault(),
                    BadgeCount: 0,
                    ActiveSessions: group.Select(receipt => receipt.SponsorSessionId).Distinct(StringComparer.OrdinalIgnoreCase).Count(static value => !string.IsNullOrWhiteSpace(value)),
                    Visibility: "group"))
                .OrderByDescending(row => row.Points)
                .Select((row, index) => row with { Rank = index + 1 })
                .ToArray();
            var groupRows = _receipts
                .Where(receipt => !string.IsNullOrWhiteSpace(receipt.GroupId))
                .GroupBy(receipt => receipt.GroupId!, StringComparer.OrdinalIgnoreCase)
                .Select(group => new GroupLeaderboardRowDto(
                    Rank: 0,
                    GroupId: group.Key,
                    GroupName: group.Key,
                    Points: group.Sum(Score),
                    LandedSlices: group.Count(receipt => string.Equals(receipt.EventKind, "slice_landed", StringComparison.OrdinalIgnoreCase)),
                    ActiveSessions: group.Select(receipt => receipt.SponsorSessionId).Distinct(StringComparer.OrdinalIgnoreCase).Count(static value => !string.IsNullOrWhiteSpace(value))))
                .OrderByDescending(row => row.Points)
                .Select((row, index) => row with { Rank = index + 1 })
                .ToArray();
            return new
            {
                individuals = individualRows,
                groups = groupRows,
                receipt_count = _receipts.Count,
            };
        }
    }

    private static int Score(ContributionReceiptDto receipt)
    {
        var eventKind = (receipt.EventKind ?? string.Empty).Trim().ToLowerInvariant();
        return eventKind switch
        {
            "lane_activated" => 1,
            "slice_reviewed" when receipt.Verified => 5,
            "slice_landed" when receipt.Verified && string.Equals(receipt.AcceptedOnRound, "1", StringComparison.OrdinalIgnoreCase) => 20,
            "slice_landed" when receipt.Verified => 15,
            _ => 0,
        };
    }

    private static string Fingerprint(ContributionReceiptDto receipt)
    {
        var payload = $"{receipt.ReceiptId}|{receipt.EventKind}|{receipt.ProjectId}|{receipt.UserId}|{receipt.GroupId}|{receipt.SponsorSessionId}";
        var hash = SHA256.HashData(Encoding.UTF8.GetBytes(payload));
        return Convert.ToHexString(hash[..8]).ToLowerInvariant();
    }
}
