using Chummer.Run.Contracts.Community;

namespace Chummer.Run.Api.Services.Community;

public sealed class AccountService
{
    private readonly CommunityStore _store;

    public AccountService(CommunityStore store)
    {
        _store = store;
    }

    public HubUserDto UpsertProfile(UpsertHubUserProfileRequest request)
    {
        var subjectId = NormalizeRequired(request.SubjectId, nameof(request.SubjectId));
        var now = DateTimeOffset.UtcNow;
        lock (_store.Gate)
        {
            if (_store.UserIdBySubjectId.TryGetValue(subjectId, out var existingUserId)
                && _store.UsersById.TryGetValue(existingUserId, out var existing))
            {
                var updated = existing with
                {
                    DisplayName = NormalizeOptional(request.DisplayName) ?? existing.DisplayName,
                    Handle = NormalizeOptional(request.Handle) ?? existing.Handle,
                    Visibility = NormalizeOptional(request.Visibility) ?? existing.Visibility,
                    Timezone = NormalizeOptional(request.Timezone) ?? existing.Timezone,
                    CountryCode = NormalizeOptional(request.CountryCode) ?? existing.CountryCode,
                    UpdatedAtUtc = now,
                };
                _store.UsersById[updated.UserId] = updated;
                return updated;
            }

            var created = new HubUserDto(
                UserId: NewId("usr"),
                SubjectId: subjectId,
                DisplayName: NormalizeOptional(request.DisplayName) ?? subjectId,
                Handle: NormalizeOptional(request.Handle) ?? subjectId.ToLowerInvariant().Replace(" ", "-"),
                Visibility: NormalizeOptional(request.Visibility) ?? "private",
                Timezone: NormalizeOptional(request.Timezone) ?? "UTC",
                CountryCode: NormalizeOptional(request.CountryCode) ?? "",
                LinkedPrincipals: new[] { subjectId },
                GroupIds: Array.Empty<string>(),
                CreatedAtUtc: now,
                UpdatedAtUtc: now);
            _store.UserIdBySubjectId[subjectId] = created.UserId;
            _store.UsersById[created.UserId] = created;
            return created;
        }
    }

    public HubUserDto EnsureUser(string subjectId, string? displayName = null)
    {
        var normalizedSubjectId = NormalizeRequired(subjectId, nameof(subjectId));
        lock (_store.Gate)
        {
            if (_store.UserIdBySubjectId.TryGetValue(normalizedSubjectId, out var existingUserId)
                && _store.UsersById.TryGetValue(existingUserId, out var existing))
            {
                return existing;
            }
        }

        return UpsertProfile(new UpsertHubUserProfileRequest(
            SubjectId: normalizedSubjectId,
            DisplayName: NormalizeOptional(displayName) ?? normalizedSubjectId));
    }

    public HubUserDto? GetBySubject(string subjectId)
    {
        var normalized = NormalizeOptional(subjectId);
        if (normalized is null)
        {
            return null;
        }

        lock (_store.Gate)
        {
            if (_store.UserIdBySubjectId.TryGetValue(normalized, out var userId)
                && _store.UsersById.TryGetValue(userId, out var user))
            {
                return user;
            }

            return null;
        }
    }

    public HubUserDto? GetById(string userId)
    {
        var normalized = NormalizeOptional(userId);
        if (normalized is null)
        {
            return null;
        }

        lock (_store.Gate)
        {
            return _store.UsersById.TryGetValue(normalized, out var user) ? user : null;
        }
    }

    public HubUserDto UpdateGroupMemberships(string userId, IReadOnlyList<string> groupIds)
    {
        var normalizedUserId = NormalizeRequired(userId, nameof(userId));
        lock (_store.Gate)
        {
            if (!_store.UsersById.TryGetValue(normalizedUserId, out var user))
            {
                throw new KeyNotFoundException($"Unknown user: {normalizedUserId}");
            }

            var updated = user with
            {
                GroupIds = groupIds
                    .Where(static value => !string.IsNullOrWhiteSpace(value))
                    .Select(static value => value.Trim())
                    .Distinct(StringComparer.OrdinalIgnoreCase)
                    .ToArray(),
                UpdatedAtUtc = DateTimeOffset.UtcNow,
            };
            _store.UsersById[normalizedUserId] = updated;
            return updated;
        }
    }

    internal static string NewId(string prefix)
        => $"{prefix}-{Guid.NewGuid():N}"[..Math.Min(prefix.Length + 13, prefix.Length + 1 + 12)];

    internal static string NormalizeRequired(string value, string name)
        => NormalizeOptional(value) ?? throw new ArgumentException($"{name} is required.", name);

    internal static string? NormalizeOptional(string? value)
    {
        var normalized = string.IsNullOrWhiteSpace(value) ? null : value.Trim();
        return string.IsNullOrWhiteSpace(normalized) ? null : normalized;
    }
}
