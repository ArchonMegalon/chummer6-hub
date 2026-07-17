using Chummer.Run.Contracts.Community;
using System;
using System.Linq;

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
    private readonly TeableUserProjectionService? _teableUsers;
    private const int MaxWorkspacePrepLibraryHistoryPerWorkspace = 10;
    private const int MaxWorkspacePrepLibraryHistoryItems = 30;

    public UserExperienceService(CommunityStore store, AccountService accounts, TeableUserProjectionService? teableUsers = null)
    {
        _store = store;
        _accounts = accounts;
        _teableUsers = teableUsers;
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
                WorkspacePrepLibrarySearchHistory: Array.Empty<WorkspacePrepLibrarySearchHistoryItem>(),
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
                WorkspacePrepLibrarySearchHistory: Array.Empty<WorkspacePrepLibrarySearchHistoryItem>(),
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
                    .Select(NormalizeBlackLedgerWorldKey)
                    .Where(static worldId => !string.IsNullOrWhiteSpace(worldId))
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
                WorkspacePrepLibrarySearchHistory = existing.WorkspacePrepLibrarySearchHistory ?? Array.Empty<WorkspacePrepLibrarySearchHistoryItem>(),
                BlackLedgerWorldsFollowed = blackLedgerWorldsFollowed,
                UpdatedAtUtc = now
            };

            _store.UserExperienceByUserId[user.UserId] = updated;
            _store.PersistLocked();
            return updated;
        }
    }

    private static string NormalizeBlackLedgerWorldKey(string? value)
        => string.IsNullOrWhiteSpace(value)
            ? string.Empty
            : value.Trim().Replace("_", "-", StringComparison.Ordinal).ToLowerInvariant();

    public HubUserExperienceDto RecordWorkspacePrepLibrarySearch(string subjectId, string workspaceId, string queryText)
    {
        var normalizedSubject = AccountService.NormalizeRequired(subjectId, nameof(subjectId));
        var normalizedWorkspaceId = AccountService.NormalizeRequired(workspaceId, nameof(workspaceId));
        var normalizedQuery = AccountService.NormalizeOptional(queryText)?.Trim();
        if (string.IsNullOrWhiteSpace(normalizedQuery))
        {
            return GetOrCreate(normalizedSubject);
        }

        HubUserDto user = _accounts.EnsureUser(normalizedSubject, normalizedSubject);
        var now = DateTimeOffset.UtcNow;
        HubUserExperienceDto updated;

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
                    WorkspacePrepLibrarySearchHistory: Array.Empty<WorkspacePrepLibrarySearchHistoryItem>(),
                    BlackLedgerWorldsFollowed: Array.Empty<string>());

            List<WorkspacePrepLibrarySearchHistoryItem> history = existing.WorkspacePrepLibrarySearchHistory is null
                ? []
                : existing.WorkspacePrepLibrarySearchHistory
                    .Where(item => !string.Equals(item.WorkspaceId, normalizedWorkspaceId, StringComparison.OrdinalIgnoreCase)
                        || !string.Equals(item.Query, normalizedQuery, StringComparison.OrdinalIgnoreCase))
                    .ToList();
            history.Add(new WorkspacePrepLibrarySearchHistoryItem(
                WorkspaceId: normalizedWorkspaceId,
                Query: normalizedQuery,
                LastUsedUtc: now));

            updated = existing with
            {
                WorkspacePrepLibrarySearchHistory = history
                    .OrderByDescending(item => item.LastUsedUtc)
                    .GroupBy(item => item.WorkspaceId, StringComparer.OrdinalIgnoreCase)
                    .SelectMany(group => group
                        .OrderByDescending(item => item.LastUsedUtc)
                        .Take(MaxWorkspacePrepLibraryHistoryPerWorkspace))
                    .OrderByDescending(item => item.LastUsedUtc)
                    .Take(MaxWorkspacePrepLibraryHistoryItems)
                    .ToArray(),
                UpdatedAtUtc = now
            };

            _store.UserExperienceByUserId[user.UserId] = updated;
            _store.PersistLocked();
        }

        _teableUsers?.QueueSyncUser(user);
        return updated;
    }
}
