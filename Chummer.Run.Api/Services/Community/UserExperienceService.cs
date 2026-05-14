using Chummer.Run.Contracts.Community;

namespace Chummer.Run.Api.Services.Community;

public sealed class UserExperienceService
{
    private static readonly string[] AllowedLanes =
    {
        "player",
        "gm",
        "creator"
    };

    private readonly CommunityStore _store;
    private readonly AccountService _accounts;

    public UserExperienceService(CommunityStore store, AccountService accounts)
    {
        _store = store;
        _accounts = accounts;
    }

    public HubUserExperienceDto GetOrCreate(string subjectId)
    {
        var user = _accounts.EnsureUser(subjectId, subjectId);
        lock (_store.Gate)
        {
            if (_store.UserExperienceByUserId.TryGetValue(user.UserId, out var existing))
            {
                return existing;
            }

            var created = new HubUserExperienceDto(
                UserId: user.UserId,
                LaneInterests: Array.Empty<string>(),
                FollowHorizons: false,
                BetaInterest: false,
                OnboardingCompleted: false,
                OnboardingCompletedAtUtc: null,
                UpdatedAtUtc: DateTimeOffset.UtcNow,
                ImpactCloseoutNotifications: false,
                PublicContributionProfileOptIn: false,
                BlackLedgerNewsEmail: false,
                BlackLedgerWorldsFollowed: Array.Empty<string>());
            _store.UserExperienceByUserId[user.UserId] = created;
            _store.PersistLocked();
            return created;
        }
    }

    public HubUserExperienceDto Upsert(UpsertHubUserExperienceRequest request)
    {
        var subjectId = AccountService.NormalizeRequired(request.SubjectId ?? string.Empty, nameof(request.SubjectId));
        var user = _accounts.EnsureUser(subjectId, subjectId);
        var now = DateTimeOffset.UtcNow;
        lock (_store.Gate)
        {
            var existing = _store.UserExperienceByUserId.TryGetValue(user.UserId, out var stored)
                ? stored
                : new HubUserExperienceDto(
                    UserId: user.UserId,
                    LaneInterests: Array.Empty<string>(),
                    FollowHorizons: false,
                    BetaInterest: false,
                    OnboardingCompleted: false,
                    OnboardingCompletedAtUtc: null,
                    UpdatedAtUtc: now,
                    ImpactCloseoutNotifications: false,
                    PublicContributionProfileOptIn: false,
                    BlackLedgerNewsEmail: false,
                    BlackLedgerWorldsFollowed: Array.Empty<string>());

            var laneInterests = request.LaneInterests is null
                ? existing.LaneInterests
                : request.LaneInterests
                    .Where(static lane => !string.IsNullOrWhiteSpace(lane))
                    .Select(static lane => lane.Trim().ToLowerInvariant())
                    .Where(static lane => AllowedLanes.Contains(lane, StringComparer.OrdinalIgnoreCase))
                    .Distinct(StringComparer.OrdinalIgnoreCase)
                    .ToArray();

            var onboardingCompleted = request.OnboardingCompleted ?? existing.OnboardingCompleted;
            var blackLedgerWorldsFollowed = request.BlackLedgerWorldsFollowed is null
                ? (existing.BlackLedgerWorldsFollowed ?? Array.Empty<string>())
                : request.BlackLedgerWorldsFollowed
                    .Where(static lane => !string.IsNullOrWhiteSpace(lane))
                    .Select(static lane => lane.Trim())
                    .Distinct(StringComparer.OrdinalIgnoreCase)
                    .ToArray();
            var updated = existing with
            {
                LaneInterests = laneInterests,
                FollowHorizons = request.FollowHorizons ?? existing.FollowHorizons,
                BetaInterest = request.BetaInterest ?? existing.BetaInterest,
                OnboardingCompleted = onboardingCompleted,
                OnboardingCompletedAtUtc = onboardingCompleted
                    ? existing.OnboardingCompletedAtUtc ?? now
                    : null,
                ImpactCloseoutNotifications = request.ImpactCloseoutNotifications ?? existing.ImpactCloseoutNotifications,
                PublicContributionProfileOptIn = request.PublicContributionProfileOptIn ?? existing.PublicContributionProfileOptIn,
                BlackLedgerNewsEmail = request.BlackLedgerNewsEmail ?? existing.BlackLedgerNewsEmail,
                BlackLedgerWorldsFollowed = blackLedgerWorldsFollowed,
                UpdatedAtUtc = now
            };

            _store.UserExperienceByUserId[user.UserId] = updated;
            _store.PersistLocked();
            return updated;
        }
    }
}
