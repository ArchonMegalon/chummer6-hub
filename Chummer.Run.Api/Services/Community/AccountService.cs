using System.Text;
using Chummer.Run.Contracts.Community;
using Microsoft.Extensions.Logging.Abstractions;

namespace Chummer.Run.Api.Services.Community;

public sealed record HubUserEnsureResult(
    HubUserDto User,
    bool Created,
    bool Changed);

public sealed class AccountService
{
    private static readonly UTF8Encoding ExactIdentityEncoding = new(false, true);
    private readonly CommunityStore _store;
    private readonly TeableUserProjectionService? _teableUsers;
    private readonly ILogger<AccountService> _logger;

    public AccountService(
        CommunityStore store,
        TeableUserProjectionService? teableUsers = null,
        ILogger<AccountService>? logger = null)
    {
        _store = store;
        _teableUsers = teableUsers;
        _logger = logger ?? NullLogger<AccountService>.Instance;
    }

    public HubUserDto UpsertProfile(UpsertHubUserProfileRequest request)
    {
        var subjectId = NormalizeRequired(request.SubjectId ?? string.Empty, nameof(request.SubjectId));
        var now = DateTimeOffset.UtcNow;
        var requestedDisplayName = NormalizeUserFacingDisplayName(request.DisplayName, subjectId);
        var requestedHandle = NormalizeUserFacingHandle(request.Handle, subjectId);
        HubUserDto result;
        using (_store.Enter())
        {
            if (_store.UserIdBySubjectId.TryGetValue(subjectId, out var existingUserId)
                && _store.UsersById.TryGetValue(existingUserId, out var existing))
            {
                var resolvedDisplayName = ResolveDisplayName(subjectId, requestedDisplayName, email: null, existing.DisplayName);
                var resolvedHandle = ResolveHandle(subjectId, requestedHandle, resolvedDisplayName, email: null, existing.Handle);
                var updated = existing with
                {
                    DisplayName = resolvedDisplayName,
                    Handle = resolvedHandle,
                    Visibility = NormalizeOptional(request.Visibility) ?? existing.Visibility,
                    Timezone = NormalizeOptional(request.Timezone) ?? existing.Timezone,
                    CountryCode = NormalizeOptional(request.CountryCode) ?? existing.CountryCode,
                    UpdatedAtUtc = now,
                };
                _store.UsersById[updated.UserId] = updated;
                _store.PersistLocked();
                result = updated;
            }
            else
            {
                var createdDisplayName = ResolveDisplayName(subjectId, requestedDisplayName, email: null);
                var createdHandle = ResolveHandle(subjectId, requestedHandle, createdDisplayName, email: null);
                var created = new HubUserDto(
                    UserId: NewId("usr"),
                    SubjectId: subjectId,
                    DisplayName: createdDisplayName,
                    Handle: createdHandle,
                    Visibility: NormalizeOptional(request.Visibility) ?? "private",
                    Timezone: NormalizeOptional(request.Timezone) ?? "UTC",
                    CountryCode: NormalizeOptional(request.CountryCode) ?? "",
                    LinkedPrincipals: new[] { subjectId },
                    GroupIds: Array.Empty<string>(),
                    CreatedAtUtc: now,
                    UpdatedAtUtc: now)
                {
                    Email = string.Empty,
                };
                _store.UserIdBySubjectId[subjectId] = created.UserId;
                _store.UsersById[created.UserId] = created;
                _store.PersistLocked();
                result = created;
            }
        }

        QueueTeableSync(result);
        return result;
    }

    public HubUserDto EnsureUser(string subjectId, string? displayName = null, string? email = null)
        => EnsureUserWithStatus(subjectId, displayName, email).User;

    public HubUserEnsureResult EnsureUserWithStatus(string subjectId, string? displayName = null, string? email = null)
    {
        var normalizedSubjectId = NormalizeRequired(subjectId, nameof(subjectId));
        var requestedDisplayName = NormalizeUserFacingDisplayName(displayName, normalizedSubjectId);
        var normalizedEmail = NormalizeOptional(email) ?? string.Empty;
        HubUserDto result;
        bool wasCreated;
        bool changed;
        using (_store.Enter())
        {
            if (_store.UserIdBySubjectId.TryGetValue(normalizedSubjectId, out var existingUserId)
                && _store.UsersById.TryGetValue(existingUserId, out var existing))
            {
                var resolvedDisplayName = ResolveDisplayName(normalizedSubjectId, requestedDisplayName, email, existing.DisplayName);
                var resolvedHandle = ResolveHandle(normalizedSubjectId, preferredHandle: null, resolvedDisplayName, email, existing.Handle);
                var resolvedTimezone = NormalizeOptional(existing.Timezone) ?? "UTC";
                var resolvedEmail = normalizedEmail.Length == 0
                    ? NormalizeOptional(existing.Email) ?? string.Empty
                    : normalizedEmail;
                if (string.Equals(existing.DisplayName, resolvedDisplayName, StringComparison.Ordinal)
                    && string.Equals(existing.Handle, resolvedHandle, StringComparison.Ordinal)
                    && string.Equals(existing.Timezone, resolvedTimezone, StringComparison.Ordinal)
                    && string.Equals(NormalizeOptional(existing.Email) ?? string.Empty, resolvedEmail, StringComparison.Ordinal))
                {
                    return new HubUserEnsureResult(existing, Created: false, Changed: false);
                }

                var updated = existing with
                {
                    DisplayName = resolvedDisplayName,
                    Handle = resolvedHandle,
                    Timezone = resolvedTimezone,
                    Email = resolvedEmail,
                    UpdatedAtUtc = DateTimeOffset.UtcNow
                };
                _store.UsersById[updated.UserId] = updated;
                _store.PersistLocked();
                result = updated;
                wasCreated = false;
                changed = true;
            }
            else
            {
                var createdDisplayName = ResolveDisplayName(normalizedSubjectId, requestedDisplayName, email);
                var createdHandle = ResolveHandle(normalizedSubjectId, preferredHandle: null, createdDisplayName, email);
                var now = DateTimeOffset.UtcNow;
                var createdUser = new HubUserDto(
                    UserId: NewId("usr"),
                    SubjectId: normalizedSubjectId,
                    DisplayName: createdDisplayName,
                    Handle: createdHandle,
                    Visibility: "private",
                    Timezone: "UTC",
                    CountryCode: "",
                    LinkedPrincipals: new[] { normalizedSubjectId },
                    GroupIds: Array.Empty<string>(),
                    CreatedAtUtc: now,
                    UpdatedAtUtc: now)
                {
                    Email = normalizedEmail,
                };
                _store.UserIdBySubjectId[normalizedSubjectId] = createdUser.UserId;
                _store.UsersById[createdUser.UserId] = createdUser;
                _store.PersistLocked();
                result = createdUser;
                wasCreated = true;
                changed = true;
            }
        }

        if (changed)
        {
            QueueTeableSync(result);
        }

        return new HubUserEnsureResult(result, wasCreated, changed);
    }

    public HubUserDto? GetBySubject(string subjectId)
    {
        var normalized = NormalizeOptional(subjectId);
        if (normalized is null)
        {
            return null;
        }

        using (_store.Enter())
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

        using (_store.Enter())
        {
            return _store.UsersById.TryGetValue(normalized, out var user) ? user : null;
        }
    }

    /// <summary>
    /// Observes an existing canonical principal-to-user mapping under one store
    /// lock. This does not authenticate the principal or create an account, and
    /// does not grant continuing authorization after the observation.
    /// </summary>
    internal string? GetExistingCanonicalUserIdBySubject(string subjectId)
    {
        string? normalized = NormalizeOptional(subjectId);
        if (normalized is null) return null;
        using (_store.Enter())
        {
            if (!_store.UserIdBySubjectId.TryGetValue(normalized, out string? indexedUserId)
                || string.IsNullOrWhiteSpace(indexedUserId)
                || !_store.UsersById.TryGetValue(indexedUserId, out HubUserDto? user)
                || user is null
                || !string.Equals(indexedUserId, user.UserId, StringComparison.OrdinalIgnoreCase))
                return null;

            // Load() builds this index from both the primary principal and
            // normalized historical linked principals, using ordinal-ignore-case.
            bool belongsToUser = string.Equals(NormalizeOptional(user.SubjectId), normalized, StringComparison.OrdinalIgnoreCase)
                || user.LinkedPrincipals?.Any(principal => string.Equals(
                    NormalizeOptional(principal), normalized, StringComparison.OrdinalIgnoreCase)) == true;
            return belongsToUser ? user.UserId : null;
        }
    }

    /// <summary>
    /// Guards an already authenticated, exact subject's existing canonical account for a
    /// bounded synchronous capture. This does not authenticate, create, or grant consent.
    /// The caller must enter this guard before any installation/authority/snapshot gate.
    /// A synchronous capture may wait for a fenced worker, but that worker must never
    /// reacquire this thread-owned account gate. No account mutations, provider HTTP,
    /// async callbacks or nested fire-and-forget work are permitted. A separately
    /// authorized installation-consent CAS may run here; synchronous work cannot be preempted.
    /// </summary>
    internal bool CaptureExistingCanonicalAccount(
        string exactSubjectId,
        string expectedUserId,
        Action capture)
    {
        ArgumentNullException.ThrowIfNull(capture);
        foreach (Delegate callback in capture.GetInvocationList())
        {
            if (callback.Method.IsDefined(
                    typeof(System.Runtime.CompilerServices.AsyncStateMachineAttribute), inherit: false))
                throw new ArgumentException("An account capture callback must be synchronous.", nameof(capture));
        }
        if (!IsExactAccountIdentity(exactSubjectId) || !IsExactAccountIdentity(expectedUserId))
            return false;

        using (_store.Enter())
        {
            if (!_store.UserIdBySubjectId.TryGetValue(exactSubjectId, out string? indexedUserId)
                || indexedUserId is null
                || !string.Equals(indexedUserId, expectedUserId, StringComparison.Ordinal)
                || !_store.UsersById.TryGetValue(indexedUserId, out HubUserDto? user)
                || user is null
                || !string.Equals(user.UserId, expectedUserId, StringComparison.Ordinal)
                || !(string.Equals(user.SubjectId, exactSubjectId, StringComparison.Ordinal)
                    || user.LinkedPrincipals?.Any(principal =>
                        string.Equals(principal, exactSubjectId, StringComparison.Ordinal)) == true))
                return false;

            capture();
            return true;
        }
    }

    private static bool IsExactAccountIdentity(string? value)
    {
        // Match the fresh-session identifier bound without trimming, folding, or replacing
        // malformed UTF-16. Legacy account lookups deliberately retain their old behavior.
        if (string.IsNullOrWhiteSpace(value) || value.Length > 128
            || value.Any(character => char.IsWhiteSpace(character) || char.IsControl(character)))
            return false;
        try { return ExactIdentityEncoding.GetByteCount(value) <= 128; }
        catch (EncoderFallbackException) { return false; }
    }

    public HubUserDto UpdateGroupMemberships(string userId, IReadOnlyList<string> groupIds)
    {
        var normalizedUserId = NormalizeRequired(userId, nameof(userId));
        HubUserDto updated;
        using (_store.Enter())
        {
            if (!_store.UsersById.TryGetValue(normalizedUserId, out var user))
            {
                throw new KeyNotFoundException($"Unknown user: {normalizedUserId}");
            }

            updated = user with
            {
                GroupIds = groupIds
                    .Where(static value => !string.IsNullOrWhiteSpace(value))
                    .Select(static value => value.Trim())
                    .Distinct(StringComparer.OrdinalIgnoreCase)
                    .ToArray(),
                UpdatedAtUtc = DateTimeOffset.UtcNow,
            };
            _store.UsersById[normalizedUserId] = updated;
            _store.PersistLocked();
        }

        QueueTeableSync(updated);
        return updated;
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

    private static string ResolveDisplayName(string subjectId, string? preferredDisplayName, string? email, string? existingDisplayName = null)
        => NormalizeUserFacingDisplayName(preferredDisplayName, subjectId)
        ?? NormalizeUserFacingDisplayName(existingDisplayName, subjectId)
        ?? DeriveDisplayNameFromEmail(email)
        ?? "Runner";

    private static string ResolveHandle(string subjectId, string? preferredHandle, string displayName, string? email, string? existingHandle = null)
        => NormalizeUserFacingHandle(preferredHandle, subjectId)
        ?? NormalizeUserFacingHandle(existingHandle, subjectId)
        ?? SlugifyHandle(EmailLocalPart(email))
        ?? SlugifyHandle(displayName)
        ?? string.Empty;

    private static string? NormalizeUserFacingDisplayName(string? value, string subjectId)
    {
        var normalized = NormalizeOptional(value);
        return IsInternalPlaceholder(normalized, subjectId) ? null : normalized;
    }

    private static string? NormalizeUserFacingHandle(string? value, string subjectId)
    {
        var normalized = NormalizeOptional(value);
        return IsInternalPlaceholder(normalized, subjectId)
            ? null
            : SlugifyHandle(normalized) ?? normalized;
    }

    private static bool IsInternalPlaceholder(string? value, string subjectId)
        => !string.IsNullOrWhiteSpace(value)
            && (string.Equals(value, subjectId, StringComparison.OrdinalIgnoreCase)
                || value.StartsWith("subject.email.", StringComparison.OrdinalIgnoreCase)
                || value.StartsWith("subject.google.", StringComparison.OrdinalIgnoreCase));

    private static string? DeriveDisplayNameFromEmail(string? email)
    {
        var localPart = EmailLocalPart(email);
        if (localPart is null)
        {
            return null;
        }

        var words = localPart
            .Split(new[] { '.', '_', '-' }, StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
            .Where(static segment => segment.Length > 0)
            .Select(static segment => char.ToUpperInvariant(segment[0]) + segment[1..])
            .ToArray();
        return words.Length == 0 ? null : string.Join(" ", words);
    }

    private static string? EmailLocalPart(string? email)
    {
        var normalized = NormalizeOptional(email);
        if (normalized is null)
        {
            return null;
        }

        var separator = normalized.IndexOf('@');
        return separator <= 0 ? null : normalized[..separator];
    }

    private static string? SlugifyHandle(string? value)
    {
        var normalized = NormalizeOptional(value);
        if (normalized is null)
        {
            return null;
        }

        var builder = new StringBuilder(normalized.Length);
        var previousDash = false;
        foreach (var character in normalized.ToLowerInvariant())
        {
            if (char.IsLetterOrDigit(character))
            {
                builder.Append(character);
                previousDash = false;
            }
            else if (!previousDash)
            {
                builder.Append('-');
                previousDash = true;
            }
        }

        var slug = builder.ToString().Trim('-');
        return string.IsNullOrWhiteSpace(slug) || string.Equals(slug, "runner", StringComparison.Ordinal)
            ? null
            : slug;
    }

    private void QueueTeableSync(HubUserDto user)
    {
        if (_teableUsers is null)
        {
            return;
        }

        try
        {
            _teableUsers.QueueSyncUser(user);
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "hub user {UserId} persisted but could not be queued for Teable projection", user.UserId);
        }
    }
}
