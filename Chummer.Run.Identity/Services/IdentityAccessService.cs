using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Chummer.Run.Contracts.Identity;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;

namespace Chummer.Run.Identity.Services;

public interface IIdentityAccessService
{
    IdentitySessionIssueResponse IssueSession(IdentitySessionIssueRequest request);
    EmailAuthStartResponse StartEmailEntry(EmailAuthStartRequest request);
    IdentitySessionIssueResponse CompleteEmailEntry(EmailAuthCompleteRequest request);
    IdentitySessionRevokeResponse RevokeSession(IdentitySessionRevokeRequest request);
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

    private sealed class EmailTicketState
    {
        public required string TicketId { get; init; }
        public required string SubjectId { get; init; }
        public required string Email { get; init; }
        public required string DisplayName { get; init; }
        public string? NextPath { get; init; }
        public required DateTimeOffset CreatedAtUtc { get; init; }
        public required DateTimeOffset ExpiresAtUtc { get; init; }
    }

    private sealed record IdentitySnapshot(
        IReadOnlyList<IdentitySubjectSnapshot> Subjects,
        IReadOnlyList<IdentitySessionSnapshot> Sessions,
        IReadOnlyList<IdentityEmailTicketSnapshot> EmailTickets);

    private sealed record IdentitySubjectSnapshot(
        string SubjectId,
        string DisplayName,
        string? Email,
        IReadOnlyList<string> Roles,
        DateTimeOffset UpdatedAtUtc);

    private sealed record IdentitySessionSnapshot(
        string SessionId,
        string SubjectId,
        string AccessToken,
        string RefreshToken,
        DateTimeOffset IssuedAtUtc,
        DateTimeOffset ExpiresAtUtc);

    private sealed record IdentityEmailTicketSnapshot(
        string TicketId,
        string SubjectId,
        string Email,
        string DisplayName,
        string? NextPath,
        DateTimeOffset CreatedAtUtc,
        DateTimeOffset ExpiresAtUtc);

    private readonly Dictionary<string, SubjectState> _subjects = new(StringComparer.OrdinalIgnoreCase);
    private readonly Dictionary<string, SessionState> _sessionsByAccessToken = new(StringComparer.Ordinal);
    private readonly Dictionary<string, EmailTicketState> _emailTickets = new(StringComparer.OrdinalIgnoreCase);
    private readonly object _mutate = new();
    private readonly string _storagePath;
    private readonly ILogger<IdentityAccessService> _logger;
    private readonly JsonSerializerOptions _jsonOptions = new(JsonSerializerDefaults.Web)
    {
        WriteIndented = true
    };

    public IdentityAccessService()
        : this(new ConfigurationBuilder().Build(), NullLogger<IdentityAccessService>.Instance)
    {
    }

    public IdentityAccessService(IConfiguration configuration, ILogger<IdentityAccessService> logger)
    {
        _logger = logger ?? NullLogger<IdentityAccessService>.Instance;
        _storagePath = ResolveStoragePath(configuration);
        LoadSnapshot();
    }

    public IdentitySessionIssueResponse IssueSession(IdentitySessionIssueRequest request)
    {
        if (request is null)
        {
            throw new ArgumentNullException(nameof(request));
        }

        lock (_mutate)
        {
            PurgeExpiredTicketsLocked();
            return IssueSessionLocked(request);
        }
    }

    public EmailAuthStartResponse StartEmailEntry(EmailAuthStartRequest request)
    {
        if (request is null)
        {
            throw new ArgumentNullException(nameof(request));
        }

        var now = DateTimeOffset.UtcNow;
        var email = NormalizeRequired(request.Email).ToLowerInvariant();
        var displayName = NormalizeOptional(request.DisplayName) ?? DeriveDisplayNameFromEmail(email);
        var subjectId = BuildSubjectIdFromEmail(email);
        var nextPath = SanitizeNextPath(request.NextPath);

        lock (_mutate)
        {
            PurgeExpiredTicketsLocked();
            EnsureSubjectLocked(subjectId, displayName, email, new[] { "player" }, now);
            var ticket = new EmailTicketState
            {
                TicketId = $"eml_{Guid.NewGuid():N}",
                SubjectId = subjectId,
                Email = email,
                DisplayName = displayName,
                NextPath = nextPath,
                CreatedAtUtc = now,
                ExpiresAtUtc = now.AddMinutes(15)
            };
            _emailTickets[ticket.TicketId] = ticket;
            PersistLocked();
            return new EmailAuthStartResponse(
                TicketId: ticket.TicketId,
                SubjectId: ticket.SubjectId,
                Email: ticket.Email,
                DisplayName: ticket.DisplayName,
                NextPath: ticket.NextPath,
                CreatedAtUtc: ticket.CreatedAtUtc,
                ExpiresAtUtc: ticket.ExpiresAtUtc,
                DeliveryMode: "preview_inline_link",
                PreviewNote: "Transactional email is not configured in this build, so the callback link is shown directly after submit.");
        }
    }

    public IdentitySessionIssueResponse CompleteEmailEntry(EmailAuthCompleteRequest request)
    {
        if (request is null)
        {
            throw new ArgumentNullException(nameof(request));
        }

        var ticketId = NormalizeRequired(request.TicketId);
        lock (_mutate)
        {
            PurgeExpiredTicketsLocked();
            if (!_emailTickets.TryGetValue(ticketId, out var ticket))
            {
                throw new KeyNotFoundException($"Unknown or expired email entry ticket '{ticketId}'.");
            }

            _emailTickets.Remove(ticketId);
            var session = IssueSessionLocked(new IdentitySessionIssueRequest(
                SubjectId: ticket.SubjectId,
                DisplayName: ticket.DisplayName,
                Email: ticket.Email,
                RequestedRoles: new[] { "player" }));
            PersistLocked();
            return session;
        }
    }

    public IdentitySessionRevokeResponse RevokeSession(IdentitySessionRevokeRequest request)
    {
        if (request is null)
        {
            throw new ArgumentNullException(nameof(request));
        }

        var accessToken = NormalizeRequired(request.AccessToken);
        lock (_mutate)
        {
            if (!_sessionsByAccessToken.TryGetValue(accessToken, out var session))
            {
                return new IdentitySessionRevokeResponse(false, null, null, DateTimeOffset.UtcNow);
            }

            _sessionsByAccessToken.Remove(accessToken);
            PersistLocked();
            return new IdentitySessionRevokeResponse(true, session.SessionId, session.SubjectId, DateTimeOffset.UtcNow);
        }
    }

    public IdentitySubjectResponse SetRoles(string subjectId, IdentityRoleSetRequest request)
    {
        var now = DateTimeOffset.UtcNow;
        lock (_mutate)
        {
            var normalizedSubjectId = NormalizeRequired(subjectId);
            var subject = _subjects.TryGetValue(normalizedSubjectId, out var existing)
                ? existing
                : new SubjectState
                {
                    SubjectId = normalizedSubjectId,
                    DisplayName = normalizedSubjectId,
                    UpdatedAtUtc = now
                };

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
            _subjects[normalizedSubjectId] = subject;
            PersistLocked();
            return ToSubjectResponse(subject);
        }
    }

    public IdentitySubjectResponse? GetSubject(string subjectId)
    {
        lock (_mutate)
        {
            return _subjects.TryGetValue(subjectId, out var subject)
                ? ToSubjectResponse(subject)
                : null;
        }
    }

    public IdentityIntrospectionResponse Introspect(IdentityIntrospectionRequest request)
    {
        if (string.IsNullOrWhiteSpace(request.AccessToken))
        {
            return new IdentityIntrospectionResponse(false, null, null, null, null);
        }

        lock (_mutate)
        {
            if (!_sessionsByAccessToken.TryGetValue(request.AccessToken, out var session))
            {
                return new IdentityIntrospectionResponse(false, null, null, null, null);
            }

            if (session.ExpiresAtUtc <= DateTimeOffset.UtcNow)
            {
                _sessionsByAccessToken.Remove(request.AccessToken);
                PersistLocked();
                return new IdentityIntrospectionResponse(false, session.SessionId, session.SubjectId, null, session.ExpiresAtUtc);
            }

            var subject = _subjects.TryGetValue(session.SubjectId, out var existing)
                ? existing
                : null;
            return new IdentityIntrospectionResponse(
                Active: true,
                SessionId: session.SessionId,
                SubjectId: session.SubjectId,
                Roles: subject?.Roles.OrderBy(static role => role, StringComparer.OrdinalIgnoreCase).ToArray() ?? Array.Empty<string>(),
                ExpiresAtUtc: session.ExpiresAtUtc);
        }
    }

    private IdentitySessionIssueResponse IssueSessionLocked(IdentitySessionIssueRequest request)
    {
        var now = DateTimeOffset.UtcNow;
        var requestedRoles = request.RequestedRoles ?? Array.Empty<string>();
        var ttl = request.RequestedTtl is { } candidate && candidate > TimeSpan.Zero && candidate <= TimeSpan.FromDays(7)
            ? candidate
            : TimeSpan.FromHours(8);

        var subjectId = NormalizeRequired(request.SubjectId);
        var subject = EnsureSubjectLocked(
            subjectId,
            NormalizeOptional(request.DisplayName) ?? subjectId,
            NormalizeOptional(request.Email),
            requestedRoles,
            now);

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
        PersistLocked();
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

    private SubjectState EnsureSubjectLocked(
        string subjectId,
        string displayName,
        string? email,
        IEnumerable<string> requestedRoles,
        DateTimeOffset now)
    {
        if (!_subjects.TryGetValue(subjectId, out var subject))
        {
            subject = new SubjectState
            {
                SubjectId = subjectId,
                DisplayName = displayName,
                Email = email,
                UpdatedAtUtc = now
            };
        }

        subject.DisplayName = string.IsNullOrWhiteSpace(displayName) ? subject.DisplayName : displayName;
        if (!string.IsNullOrWhiteSpace(email))
        {
            subject.Email = email;
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
        _subjects[subjectId] = subject;
        return subject;
    }

    private void LoadSnapshot()
    {
        lock (_mutate)
        {
            Directory.CreateDirectory(Path.GetDirectoryName(_storagePath)!);
            if (!File.Exists(_storagePath))
            {
                _logger.LogInformation("IdentityAccessService starting with an empty durable state at {StoragePath}.", _storagePath);
                return;
            }

            var json = File.ReadAllText(_storagePath);
            if (string.IsNullOrWhiteSpace(json))
            {
                return;
            }

            var snapshot = JsonSerializer.Deserialize<IdentitySnapshot>(json, _jsonOptions);
            if (snapshot is null)
            {
                return;
            }

            _subjects.Clear();
            _sessionsByAccessToken.Clear();
            _emailTickets.Clear();

            foreach (var subject in snapshot.Subjects)
            {
                var state = new SubjectState
                {
                    SubjectId = subject.SubjectId,
                    DisplayName = subject.DisplayName,
                    Email = subject.Email,
                    UpdatedAtUtc = subject.UpdatedAtUtc
                };
                foreach (var role in subject.Roles.Where(static role => !string.IsNullOrWhiteSpace(role)))
                {
                    state.Roles.Add(role);
                }

                _subjects[state.SubjectId] = state;
            }

            foreach (var session in snapshot.Sessions)
            {
                _sessionsByAccessToken[session.AccessToken] = new SessionState
                {
                    SessionId = session.SessionId,
                    SubjectId = session.SubjectId,
                    AccessToken = session.AccessToken,
                    RefreshToken = session.RefreshToken,
                    IssuedAtUtc = session.IssuedAtUtc,
                    ExpiresAtUtc = session.ExpiresAtUtc
                };
            }

            foreach (var ticket in snapshot.EmailTickets)
            {
                _emailTickets[ticket.TicketId] = new EmailTicketState
                {
                    TicketId = ticket.TicketId,
                    SubjectId = ticket.SubjectId,
                    Email = ticket.Email,
                    DisplayName = ticket.DisplayName,
                    NextPath = ticket.NextPath,
                    CreatedAtUtc = ticket.CreatedAtUtc,
                    ExpiresAtUtc = ticket.ExpiresAtUtc
                };
            }

            PurgeExpiredTicketsLocked();
            _logger.LogInformation(
                "IdentityAccessService loaded {SubjectCount} subjects, {SessionCount} sessions, and {EmailTicketCount} email tickets from {StoragePath}.",
                _subjects.Count,
                _sessionsByAccessToken.Count,
                _emailTickets.Count,
                _storagePath);
        }
    }

    private void PersistLocked()
    {
        Directory.CreateDirectory(Path.GetDirectoryName(_storagePath)!);
        var snapshot = new IdentitySnapshot(
            Subjects: _subjects.Values
                .OrderBy(static item => item.SubjectId, StringComparer.OrdinalIgnoreCase)
                .Select(static item => new IdentitySubjectSnapshot(
                    item.SubjectId,
                    item.DisplayName,
                    item.Email,
                    item.Roles.OrderBy(static role => role, StringComparer.OrdinalIgnoreCase).ToArray(),
                    item.UpdatedAtUtc))
                .ToArray(),
            Sessions: _sessionsByAccessToken.Values
                .OrderBy(static item => item.SubjectId, StringComparer.OrdinalIgnoreCase)
                .ThenBy(static item => item.IssuedAtUtc)
                .Select(static item => new IdentitySessionSnapshot(
                    item.SessionId,
                    item.SubjectId,
                    item.AccessToken,
                    item.RefreshToken,
                    item.IssuedAtUtc,
                    item.ExpiresAtUtc))
                .ToArray(),
            EmailTickets: _emailTickets.Values
                .OrderBy(static item => item.CreatedAtUtc)
                .Select(static item => new IdentityEmailTicketSnapshot(
                    item.TicketId,
                    item.SubjectId,
                    item.Email,
                    item.DisplayName,
                    item.NextPath,
                    item.CreatedAtUtc,
                    item.ExpiresAtUtc))
                .ToArray());

        var tempPath = $"{_storagePath}.tmp";
        File.WriteAllText(tempPath, JsonSerializer.Serialize(snapshot, _jsonOptions));
        File.Move(tempPath, _storagePath, true);
    }

    private void PurgeExpiredTicketsLocked()
    {
        var now = DateTimeOffset.UtcNow;
        var expired = _emailTickets
            .Where(static pair => pair.Value.ExpiresAtUtc <= DateTimeOffset.UtcNow)
            .Select(static pair => pair.Key)
            .ToArray();
        foreach (var ticketId in expired)
        {
            _emailTickets.Remove(ticketId);
        }

        var expiredSessions = _sessionsByAccessToken
            .Where(static pair => pair.Value.ExpiresAtUtc <= DateTimeOffset.UtcNow)
            .Select(static pair => pair.Key)
            .ToArray();
        foreach (var accessToken in expiredSessions)
        {
            _sessionsByAccessToken.Remove(accessToken);
        }

        if (expired.Length > 0 || expiredSessions.Length > 0)
        {
            PersistLocked();
        }
    }

    private static string ResolveStoragePath(IConfiguration configuration)
    {
        var configured = configuration["CHUMMER_IDENTITY_STORE_PATH"];
        if (!string.IsNullOrWhiteSpace(configured))
        {
            return Path.GetFullPath(configured);
        }

        return Path.Combine(Path.GetTempPath(), "chummer-run-identity", "identity-store.json");
    }

    private static string BuildSubjectIdFromEmail(string email)
    {
        var hash = SHA256.HashData(Encoding.UTF8.GetBytes(email.ToLowerInvariant()));
        return $"subject.email.{Convert.ToHexString(hash[..8]).ToLowerInvariant()}";
    }

    private static string DeriveDisplayNameFromEmail(string email)
    {
        var localPart = email.Split('@', 2, StringSplitOptions.TrimEntries | StringSplitOptions.RemoveEmptyEntries).FirstOrDefault();
        if (string.IsNullOrWhiteSpace(localPart))
        {
            return "Runner";
        }

        var words = localPart
            .Split(new[] { '.', '_', '-' }, StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
            .Select(static segment => char.ToUpperInvariant(segment[0]) + segment[1..])
            .ToArray();
        return words.Length == 0 ? "Runner" : string.Join(" ", words);
    }

    private static string SanitizeNextPath(string? nextPath)
    {
        if (string.IsNullOrWhiteSpace(nextPath))
        {
            return "/home";
        }

        var trimmed = nextPath.Trim();
        return trimmed.StartsWith("/", StringComparison.Ordinal) && !trimmed.StartsWith("//", StringComparison.Ordinal)
            ? trimmed
            : "/home";
    }

    private static string NormalizeRequired(string value)
        => string.IsNullOrWhiteSpace(value)
            ? throw new ArgumentException("A required identity value was blank.")
            : value.Trim();

    private static string? NormalizeOptional(string? value)
        => string.IsNullOrWhiteSpace(value) ? null : value.Trim();

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
