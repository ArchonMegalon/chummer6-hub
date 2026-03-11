using Chummer.Run.Contracts.Identity;
using System.Collections.Concurrent;
using System.Security.Cryptography;
using System.Text;

namespace Chummer.Run.Identity.Services;

public interface IIdentityAccessService
{
    IdentitySessionIssueResponse IssueSession(IdentitySessionIssueRequest request);
    IdentitySubjectResponse SetRoles(string subjectId, IdentityRoleSetRequest request);
    IdentitySubjectResponse? GetSubject(string subjectId);
    IdentityIntrospectionResponse Introspect(IdentityIntrospectionRequest request);
}

public sealed class IdentityAccessService : IIdentityAccessService
{
    private sealed class SubjectState
    {
        public required string SubjectId { get; init; }
        public required string DisplayName { get; set; }
        public string? Email { get; set; }
        public HashSet<string> Roles { get; } = new(StringComparer.OrdinalIgnoreCase);
        public DateTimeOffset UpdatedAtUtc { get; set; }
    }

    private sealed class SessionState
    {
        public required string SessionId { get; init; }
        public required string SubjectId { get; init; }
        public required string AccessToken { get; init; }
        public required string RefreshToken { get; init; }
        public required DateTimeOffset IssuedAtUtc { get; init; }
        public required DateTimeOffset ExpiresAtUtc { get; init; }
    }

    private readonly ConcurrentDictionary<string, SubjectState> _subjects = new(StringComparer.OrdinalIgnoreCase);
    private readonly ConcurrentDictionary<string, SessionState> _sessionsByAccessToken = new(StringComparer.Ordinal);
    private readonly object _mutate = new();

    public IdentitySessionIssueResponse IssueSession(IdentitySessionIssueRequest request)
    {
        var now = DateTimeOffset.UtcNow;
        var requestedRoles = request.RequestedRoles ?? Array.Empty<string>();
        var ttl = request.RequestedTtl is { } candidate && candidate > TimeSpan.Zero && candidate <= TimeSpan.FromDays(7)
            ? candidate
            : TimeSpan.FromHours(8);

        SubjectState subject;
        lock (_mutate)
        {
            subject = _subjects.GetOrAdd(request.SubjectId, _ => new SubjectState
            {
                SubjectId = request.SubjectId,
                DisplayName = string.IsNullOrWhiteSpace(request.DisplayName) ? request.SubjectId : request.DisplayName,
                Email = request.Email,
                UpdatedAtUtc = now
            });

            if (!string.IsNullOrWhiteSpace(request.DisplayName))
            {
                subject.DisplayName = request.DisplayName;
            }

            if (!string.IsNullOrWhiteSpace(request.Email))
            {
                subject.Email = request.Email;
            }

            foreach (var role in requestedRoles.Where(static role => !string.IsNullOrWhiteSpace(role)))
            {
                subject.Roles.Add(role.Trim());
            }

            if (subject.Roles.Count == 0)
            {
                subject.Roles.Add("player");
            }

            subject.UpdatedAtUtc = now;
        }

        var session = new SessionState
        {
            SessionId = $"sid_{Guid.NewGuid():N}",
            SubjectId = subject.SubjectId,
            AccessToken = BuildToken(subject.SubjectId, "access"),
            RefreshToken = BuildToken(subject.SubjectId, "refresh"),
            IssuedAtUtc = now,
            ExpiresAtUtc = now.Add(ttl)
        };

        _sessionsByAccessToken[session.AccessToken] = session;
        return new IdentitySessionIssueResponse(
            SessionId: session.SessionId,
            SubjectId: subject.SubjectId,
            DisplayName: subject.DisplayName,
            Email: subject.Email,
            Roles: subject.Roles.OrderBy(static role => role, StringComparer.OrdinalIgnoreCase).ToArray(),
            AccessToken: session.AccessToken,
            RefreshToken: session.RefreshToken,
            IssuedAtUtc: session.IssuedAtUtc,
            ExpiresAtUtc: session.ExpiresAtUtc);
    }

    public IdentitySubjectResponse SetRoles(string subjectId, IdentityRoleSetRequest request)
    {
        var now = DateTimeOffset.UtcNow;
        SubjectState subject;
        lock (_mutate)
        {
            subject = _subjects.GetOrAdd(subjectId, _ => new SubjectState
            {
                SubjectId = subjectId,
                DisplayName = subjectId,
                UpdatedAtUtc = now
            });

            subject.Roles.Clear();
            foreach (var role in request.Roles.Where(static role => !string.IsNullOrWhiteSpace(role)))
            {
                subject.Roles.Add(role.Trim());
            }

            if (subject.Roles.Count == 0)
            {
                subject.Roles.Add("player");
            }

            subject.UpdatedAtUtc = now;
        }

        return ToSubjectResponse(subject);
    }

    public IdentitySubjectResponse? GetSubject(string subjectId)
    {
        if (!_subjects.TryGetValue(subjectId, out var subject))
        {
            return null;
        }

        lock (_mutate)
        {
            return ToSubjectResponse(subject);
        }
    }

    public IdentityIntrospectionResponse Introspect(IdentityIntrospectionRequest request)
    {
        if (string.IsNullOrWhiteSpace(request.AccessToken))
        {
            return new IdentityIntrospectionResponse(false, null, null, null, null);
        }

        if (!_sessionsByAccessToken.TryGetValue(request.AccessToken, out var session))
        {
            return new IdentityIntrospectionResponse(false, null, null, null, null);
        }

        if (session.ExpiresAtUtc <= DateTimeOffset.UtcNow)
        {
            _sessionsByAccessToken.TryRemove(request.AccessToken, out _);
            return new IdentityIntrospectionResponse(false, session.SessionId, session.SubjectId, null, session.ExpiresAtUtc);
        }

        var subject = GetSubject(session.SubjectId);
        return new IdentityIntrospectionResponse(
            Active: true,
            SessionId: session.SessionId,
            SubjectId: session.SubjectId,
            Roles: subject?.Roles ?? Array.Empty<string>(),
            ExpiresAtUtc: session.ExpiresAtUtc);
    }

    private static string BuildToken(string subjectId, string tokenType)
    {
        var entropy = RandomNumberGenerator.GetBytes(24);
        var payload = $"{tokenType}:{subjectId}:{Convert.ToBase64String(entropy)}:{DateTimeOffset.UtcNow:O}";
        var bytes = Encoding.UTF8.GetBytes(payload);
        return Convert.ToBase64String(bytes)
            .TrimEnd('=')
            .Replace('+', '-')
            .Replace('/', '_');
    }

    private static IdentitySubjectResponse ToSubjectResponse(SubjectState subject) =>
        new(
            SubjectId: subject.SubjectId,
            DisplayName: subject.DisplayName,
            Email: subject.Email,
            Roles: subject.Roles.OrderBy(static role => role, StringComparer.OrdinalIgnoreCase).ToArray(),
            UpdatedAtUtc: subject.UpdatedAtUtc);
}
