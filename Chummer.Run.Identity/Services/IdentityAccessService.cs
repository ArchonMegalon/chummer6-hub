using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
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
        public required string AccessTokenHash { get; init; }
        public required string RefreshTokenHash { get; init; }
        public required DateTimeOffset IssuedAtUtc { get; init; }
        public required DateTimeOffset ExpiresAtUtc { get; init; }
    }

    private sealed class EmailTicketState
    {
        public required string TicketHash { get; init; }
        public required string SubjectId { get; init; }
        public required string Email { get; init; }
        public required string DisplayName { get; init; }
        public string? NextPath { get; init; }
        public required DateTimeOffset CreatedAtUtc { get; init; }
        public required DateTimeOffset ExpiresAtUtc { get; init; }
    }

    private sealed record EmailStartAttemptState(
        string Email,
        DateTimeOffset OccurredAtUtc);

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
        string SessionId = "",
        string SubjectId = "",
        string? AccessTokenHash = null,
        string? RefreshTokenHash = null,
        DateTimeOffset IssuedAtUtc = default,
        DateTimeOffset ExpiresAtUtc = default,
        string? AccessToken = null,
        string? RefreshToken = null);

    private sealed record IdentityEmailTicketSnapshot(
        string? TicketHash = null,
        string SubjectId = "",
        string Email = "",
        string DisplayName = "",
        string? NextPath = null,
        DateTimeOffset CreatedAtUtc = default,
        DateTimeOffset ExpiresAtUtc = default,
        string? TicketId = null);

    private readonly Dictionary<string, SubjectState> _subjects = new(StringComparer.OrdinalIgnoreCase);
    private readonly Dictionary<string, SessionState> _sessionsByAccessTokenHash = new(StringComparer.Ordinal);
    private readonly Dictionary<string, EmailTicketState> _emailTicketsByHash = new(StringComparer.Ordinal);
    private readonly List<EmailStartAttemptState> _recentEmailStartAttempts = new();
    private readonly object _mutate = new();
    private readonly IConfiguration _configuration;
    private readonly string _storagePath;
    private readonly string _emailStartPauseFlagPath;
    private readonly ILogger<IdentityAccessService> _logger;
    private readonly IIdentityEmailDeliveryService _emailDelivery;
    private readonly JsonSerializerOptions _jsonOptions = new(JsonSerializerDefaults.Web)
    {
        WriteIndented = true,
        DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull
    };

    public IdentityAccessService()
        : this(
            new ConfigurationBuilder().Build(),
            NullLogger<IdentityAccessService>.Instance,
            new IdentityEmailDeliveryService(new ConfigurationBuilder().Build(), NullLogger<IdentityEmailDeliveryService>.Instance))
    {
    }

    public IdentityAccessService(IConfiguration configuration, ILogger<IdentityAccessService> logger)
        : this(configuration, logger, new IdentityEmailDeliveryService(configuration, NullLogger<IdentityEmailDeliveryService>.Instance))
    {
    }

    public IdentityAccessService(IConfiguration configuration, ILogger<IdentityAccessService> logger, IIdentityEmailDeliveryService emailDelivery)
    {
        _configuration = configuration ?? throw new ArgumentNullException(nameof(configuration));
        _logger = logger ?? NullLogger<IdentityAccessService>.Instance;
        _emailDelivery = emailDelivery;
        _storagePath = ResolveStoragePath(configuration);
        _emailStartPauseFlagPath = ResolveEmailStartPauseFlagPath(configuration, _storagePath);
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
        var subjectId = IdentitySubjectDerivation.FromEmail(email);
        var nextPath = SanitizeNextPath(request.NextPath);

        lock (_mutate)
        {
            PurgeExpiredTicketsLocked();
            PurgeExpiredEmailStartAttemptsLocked(now);
            if (TryGetEmailStartPauseReason(out var pausePreviewNote))
            {
                _logger.LogWarning(
                    "Identity email start blocked for {Email}: paused by {PauseFlagPath}.",
                    email,
                    _emailStartPauseFlagPath);
                _emailDelivery.RecordStartGuardrailBlock(email, "email_start_paused", pausePreviewNote);
                return BuildRejectedEmailStartResponse(
                    subjectId,
                    email,
                    displayName,
                    nextPath,
                    now,
                    deliveryMode: "email_start_paused",
                    previewNote: pausePreviewNote);
            }

            if (!IsEmailStartEnabled())
            {
                const string disabledPreviewNote = "Email sign-in is disabled on this host.";
                _logger.LogWarning("Identity email start blocked for {Email}: disabled by IDENTITY_EMAIL_START_ENABLED.", email);
                _emailDelivery.RecordStartGuardrailBlock(email, "email_start_disabled", disabledPreviewNote);
                return BuildRejectedEmailStartResponse(
                    subjectId,
                    email,
                    displayName,
                    nextPath,
                    now,
                    deliveryMode: "email_start_disabled",
                    previewNote: disabledPreviewNote);
            }

            if (TryBuildEmailStartThrottleResponseLocked(email, displayName, subjectId, nextPath, now, out var blockedResponse))
            {
                return blockedResponse;
            }

            _recentEmailStartAttempts.Add(new EmailStartAttemptState(email, now));
            EnsureSubjectLocked(subjectId, displayName, email, new[] { "player" }, now);
            var ticketId = $"eml_{Guid.NewGuid():N}";
            var ticket = new EmailTicketState
            {
                TicketHash = HashSecret(ticketId),
                SubjectId = subjectId,
                Email = email,
                DisplayName = displayName,
                NextPath = nextPath,
                CreatedAtUtc = now,
                ExpiresAtUtc = now.AddMinutes(15)
            };
            _emailTicketsByHash[ticket.TicketHash] = ticket;
            PersistLocked();
            var delivery = _emailDelivery.DeliverMagicLink(ticket.Email, ticket.DisplayName, ticketId, ticket.NextPath, ticket.ExpiresAtUtc);
            if (!delivery.Delivered && !IsInlinePreviewDelivery(delivery.DeliveryMode))
            {
                _emailTicketsByHash.Remove(ticket.TicketHash);
                PersistLocked();
            }

            return new EmailAuthStartResponse(
                TicketId: IsInlinePreviewDelivery(delivery.DeliveryMode) && delivery.ExposeInlinePreviewTicket ? ticketId : string.Empty,
                SubjectId: ticket.SubjectId,
                Email: ticket.Email,
                DisplayName: ticket.DisplayName,
                NextPath: ticket.NextPath,
                CreatedAtUtc: ticket.CreatedAtUtc,
                ExpiresAtUtc: ticket.ExpiresAtUtc,
                DeliveryMode: delivery.DeliveryMode,
                PreviewNote: delivery.PreviewNote);
        }
    }

    public IdentitySessionIssueResponse CompleteEmailEntry(EmailAuthCompleteRequest request)
    {
        if (request is null)
        {
            throw new ArgumentNullException(nameof(request));
        }

        var ticketId = NormalizeRequired(request.TicketId);
        var ticketHash = HashSecret(ticketId);
        lock (_mutate)
        {
            PurgeExpiredTicketsLocked();
            if (!_emailTicketsByHash.TryGetValue(ticketHash, out var ticket))
            {
                throw new KeyNotFoundException($"Unknown or expired email entry ticket '{ticketId}'.");
            }

            _emailTicketsByHash.Remove(ticketHash);
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
        var accessTokenHash = HashSecret(accessToken);
        lock (_mutate)
        {
            if (!_sessionsByAccessTokenHash.TryGetValue(accessTokenHash, out var session))
            {
                return new IdentitySessionRevokeResponse(false, null, null, DateTimeOffset.UtcNow);
            }

            _sessionsByAccessTokenHash.Remove(accessTokenHash);
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
            var accessTokenHash = HashSecret(request.AccessToken);
            if (!_sessionsByAccessTokenHash.TryGetValue(accessTokenHash, out var session))
            {
                return new IdentityIntrospectionResponse(false, null, null, null, null);
            }

            if (session.ExpiresAtUtc <= DateTimeOffset.UtcNow)
            {
                _sessionsByAccessTokenHash.Remove(accessTokenHash);
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

        var accessToken = BuildToken(subject.SubjectId, "access");
        var refreshToken = BuildToken(subject.SubjectId, "refresh");
        var session = new SessionState
        {
            SessionId = $"sid_{Guid.NewGuid():N}",
            SubjectId = subject.SubjectId,
            AccessTokenHash = HashSecret(accessToken),
            RefreshTokenHash = HashSecret(refreshToken),
            IssuedAtUtc = now,
            ExpiresAtUtc = now.Add(ttl)
        };

        _sessionsByAccessTokenHash[session.AccessTokenHash] = session;
        PersistLocked();
        return new IdentitySessionIssueResponse(
            SessionId: session.SessionId,
            SubjectId: subject.SubjectId,
            DisplayName: subject.DisplayName,
            Email: subject.Email,
            Roles: subject.Roles.OrderBy(static role => role, StringComparer.OrdinalIgnoreCase).ToArray(),
            AccessToken: accessToken,
            RefreshToken: refreshToken,
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
            _sessionsByAccessTokenHash.Clear();
            _emailTicketsByHash.Clear();

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
                var accessTokenHash = NormalizeStoredSecretHash(session.AccessTokenHash, session.AccessToken);
                var refreshTokenHash = NormalizeStoredSecretHash(session.RefreshTokenHash, session.RefreshToken);
                if (string.IsNullOrWhiteSpace(session.SessionId)
                    || string.IsNullOrWhiteSpace(session.SubjectId)
                    || accessTokenHash is null
                    || refreshTokenHash is null)
                {
                    continue;
                }

                _sessionsByAccessTokenHash[accessTokenHash] = new SessionState
                {
                    SessionId = session.SessionId,
                    SubjectId = session.SubjectId,
                    AccessTokenHash = accessTokenHash,
                    RefreshTokenHash = refreshTokenHash,
                    IssuedAtUtc = session.IssuedAtUtc,
                    ExpiresAtUtc = session.ExpiresAtUtc
                };
            }

            foreach (var ticket in snapshot.EmailTickets)
            {
                var ticketHash = NormalizeStoredSecretHash(ticket.TicketHash, ticket.TicketId);
                if (ticketHash is null
                    || string.IsNullOrWhiteSpace(ticket.SubjectId)
                    || string.IsNullOrWhiteSpace(ticket.Email)
                    || string.IsNullOrWhiteSpace(ticket.DisplayName))
                {
                    continue;
                }

                _emailTicketsByHash[ticketHash] = new EmailTicketState
                {
                    TicketHash = ticketHash,
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
                _sessionsByAccessTokenHash.Count,
                _emailTicketsByHash.Count,
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
            Sessions: _sessionsByAccessTokenHash.Values
                .OrderBy(static item => item.SubjectId, StringComparer.OrdinalIgnoreCase)
                .ThenBy(static item => item.IssuedAtUtc)
                .Select(static item => new IdentitySessionSnapshot(
                    SessionId: item.SessionId,
                    SubjectId: item.SubjectId,
                    AccessTokenHash: item.AccessTokenHash,
                    RefreshTokenHash: item.RefreshTokenHash,
                    IssuedAtUtc: item.IssuedAtUtc,
                    ExpiresAtUtc: item.ExpiresAtUtc))
                .ToArray(),
            EmailTickets: _emailTicketsByHash.Values
                .OrderBy(static item => item.CreatedAtUtc)
                .Select(static item => new IdentityEmailTicketSnapshot(
                    TicketHash: item.TicketHash,
                    SubjectId: item.SubjectId,
                    Email: item.Email,
                    DisplayName: item.DisplayName,
                    NextPath: item.NextPath,
                    CreatedAtUtc: item.CreatedAtUtc,
                    ExpiresAtUtc: item.ExpiresAtUtc))
                .ToArray());

        var tempPath = $"{_storagePath}.tmp";
        File.WriteAllText(tempPath, JsonSerializer.Serialize(snapshot, _jsonOptions));
        File.Move(tempPath, _storagePath, true);
    }

    private void PurgeExpiredTicketsLocked()
    {
        var expired = _emailTicketsByHash
            .Where(static pair => pair.Value.ExpiresAtUtc <= DateTimeOffset.UtcNow)
            .Select(static pair => pair.Key)
            .ToArray();
        foreach (var ticketHash in expired)
        {
            _emailTicketsByHash.Remove(ticketHash);
        }

        var expiredSessions = _sessionsByAccessTokenHash
            .Where(static pair => pair.Value.ExpiresAtUtc <= DateTimeOffset.UtcNow)
            .Select(static pair => pair.Key)
            .ToArray();
        foreach (var accessTokenHash in expiredSessions)
        {
            _sessionsByAccessTokenHash.Remove(accessTokenHash);
        }

        if (expired.Length > 0 || expiredSessions.Length > 0)
        {
            PersistLocked();
        }
    }

    private static string ResolveStoragePath(IConfiguration configuration)
    {
        var configured = configuration["CHUMMER_IDENTITY_STORE_PATH"]?.Trim();
        if (!string.IsNullOrWhiteSpace(configured))
        {
            return Path.GetFullPath(configured);
        }

        return Path.Combine(ResolveDefaultStateRoot(configuration), "identity", "identity-store.json");
    }

    private static string ResolveEmailStartPauseFlagPath(IConfiguration configuration, string storagePath)
    {
        var configured = configuration["CHUMMER_AUTH_SIGNIN_AUTOMATION_PAUSE_FLAG"]?.Trim();
        if (!string.IsNullOrWhiteSpace(configured))
        {
            return Path.GetFullPath(configured);
        }

        var storageDirectory = Path.GetDirectoryName(storagePath);
        if (!string.IsNullOrWhiteSpace(storageDirectory))
        {
            return Path.Combine(storageDirectory, "auth_signin_automation_paused.flag");
        }

        return Path.Combine(ResolveDefaultStateRoot(configuration), "identity", "auth_signin_automation_paused.flag");
    }

    private static string ResolveDefaultStateRoot(IConfiguration configuration)
    {
        var configuredStateRoot = configuration["CHUMMER_IDENTITY_STATE_ROOT"]?.Trim()
                                  ?? configuration["CHUMMER_RUNTIME_STATE_ROOT"]?.Trim();
        if (!string.IsNullOrWhiteSpace(configuredStateRoot))
        {
            return Path.GetFullPath(configuredStateRoot);
        }

        var xdgStateHome = Environment.GetEnvironmentVariable("XDG_STATE_HOME");
        if (!string.IsNullOrWhiteSpace(xdgStateHome))
        {
            return Path.Combine(Path.GetFullPath(xdgStateHome), "chummer-run");
        }

        var localData = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
        if (!string.IsNullOrWhiteSpace(localData))
        {
            return Path.Combine(localData, "Chummer", "Run");
        }

        return Path.Combine(AppContext.BaseDirectory, ".chummer-state");
    }

    private static string? NormalizeStoredSecretHash(string? storedHash, string? legacyPlainSecret)
    {
        var normalizedHash = NormalizeOptional(storedHash);
        if (normalizedHash is not null)
        {
            if (TryNormalizeSha256Hash(normalizedHash, out var canonicalHash))
            {
                return canonicalHash;
            }

            return HashSecret(normalizedHash);
        }

        var legacySecret = NormalizeOptional(legacyPlainSecret);
        return legacySecret is null ? null : HashSecret(legacySecret);
    }

    private static bool TryNormalizeSha256Hash(string value, out string canonicalHash)
    {
        const string prefix = "sha256:";
        canonicalHash = string.Empty;
        if (!value.StartsWith(prefix, StringComparison.OrdinalIgnoreCase))
        {
            return false;
        }

        var hex = value[prefix.Length..];
        if (hex.Length != 64 || hex.Any(static ch => !Uri.IsHexDigit(ch)))
        {
            return false;
        }

        canonicalHash = $"{prefix}{hex.ToLowerInvariant()}";
        return true;
    }

    private static string HashSecret(string secret)
    {
        var bytes = SHA256.HashData(Encoding.UTF8.GetBytes(NormalizeRequired(secret)));
        return $"sha256:{Convert.ToHexString(bytes).ToLowerInvariant()}";
    }

    private bool TryGetEmailStartPauseReason(out string previewNote)
    {
        previewNote = string.Empty;

        try
        {
            if (!File.Exists(_emailStartPauseFlagPath))
            {
                return false;
            }

            previewNote = NormalizeOptional(File.ReadAllText(_emailStartPauseFlagPath))
                          ?? "Email sign-in is paused on this host.";
            return true;
        }
        catch (Exception ex)
        {
            _logger.LogWarning(
                ex,
                "Identity email start pause flag at {PauseFlagPath} could not be read; failing closed.",
                _emailStartPauseFlagPath);
            previewNote = "Email sign-in is paused on this host.";
            return true;
        }
    }

    private bool IsEmailStartEnabled()
        => ResolveBool(_configuration["IDENTITY_EMAIL_START_ENABLED"], defaultValue: false);

    private void PurgeExpiredEmailStartAttemptsLocked(DateTimeOffset now)
    {
        var retentionSeconds = Math.Max(
            ResolvePositiveInt(_configuration["IDENTITY_EMAIL_START_WINDOW_SECONDS"], defaultValue: 900),
            ResolveNonNegativeInt(_configuration["IDENTITY_EMAIL_START_MIN_SECONDS_BETWEEN_RECIPIENT_ATTEMPTS"], defaultValue: 120));
        var cutoff = now.AddSeconds(-Math.Max(retentionSeconds, 60));
        _recentEmailStartAttempts.RemoveAll(attempt => attempt.OccurredAtUtc < cutoff);
    }

    private bool TryBuildEmailStartThrottleResponseLocked(
        string email,
        string displayName,
        string subjectId,
        string? nextPath,
        DateTimeOffset now,
        out EmailAuthStartResponse response)
    {
        var windowSeconds = ResolvePositiveInt(_configuration["IDENTITY_EMAIL_START_WINDOW_SECONDS"], defaultValue: 900);
        var globalLimit = ResolveNonNegativeInt(_configuration["IDENTITY_EMAIL_START_MAX_ATTEMPTS_PER_WINDOW"], defaultValue: 60);
        var recipientLimit = ResolvePositiveInt(_configuration["IDENTITY_EMAIL_START_MAX_ATTEMPTS_PER_RECIPIENT_PER_WINDOW"], defaultValue: 3);
        var recipientCooldownSeconds = ResolveNonNegativeInt(_configuration["IDENTITY_EMAIL_START_MIN_SECONDS_BETWEEN_RECIPIENT_ATTEMPTS"], defaultValue: 120);
        var windowStart = now.AddSeconds(-windowSeconds);

        var globalAttempts = _recentEmailStartAttempts.Count(attempt => attempt.OccurredAtUtc >= windowStart);
        if (globalLimit > 0 && globalAttempts >= globalLimit)
        {
            const string previewNote = "Email sign-in is temporarily rate-limited on this host. Try again later.";
            _logger.LogWarning(
                "Identity email start blocked for {Email}: global limit {AttemptCount}/{Limit} in {WindowSeconds}s.",
                email,
                globalAttempts,
                globalLimit,
                windowSeconds);
            _emailDelivery.RecordStartGuardrailBlock(email, "email_start_rate_limited", previewNote);
            response = BuildRejectedEmailStartResponse(
                subjectId,
                email,
                displayName,
                nextPath,
                now,
                deliveryMode: "email_start_rate_limited",
                previewNote: previewNote);
            return true;
        }

        var recipientAttempts = _recentEmailStartAttempts
            .Where(attempt => string.Equals(attempt.Email, email, StringComparison.OrdinalIgnoreCase))
            .OrderByDescending(attempt => attempt.OccurredAtUtc)
            .ToArray();
        if (recipientCooldownSeconds > 0 && recipientAttempts.Length > 0)
        {
            var earliestNextAttemptAt = recipientAttempts[0].OccurredAtUtc.AddSeconds(recipientCooldownSeconds);
            if (earliestNextAttemptAt > now)
            {
                const string previewNote = "Email sign-in is cooling down for this address. Wait before requesting another link.";
                _logger.LogWarning(
                    "Identity email start blocked for {Email}: recipient cooldown active until {NextAttemptAtUtc:O}.",
                    email,
                    earliestNextAttemptAt);
                _emailDelivery.RecordStartGuardrailBlock(email, "email_start_rate_limited", previewNote);
                response = BuildRejectedEmailStartResponse(
                    subjectId,
                    email,
                    displayName,
                    nextPath,
                    now,
                    deliveryMode: "email_start_rate_limited",
                    previewNote: previewNote);
                return true;
            }
        }

        var recentRecipientAttempts = recipientAttempts.Count(attempt => attempt.OccurredAtUtc >= windowStart);
        if (recipientLimit > 0 && recentRecipientAttempts >= recipientLimit)
        {
            const string previewNote = "Email sign-in has reached the retry limit for this address. Try again later.";
            _logger.LogWarning(
                "Identity email start blocked for {Email}: recipient limit {AttemptCount}/{Limit} in {WindowSeconds}s.",
                email,
                recentRecipientAttempts,
                recipientLimit,
                windowSeconds);
            _emailDelivery.RecordStartGuardrailBlock(email, "email_start_rate_limited", previewNote);
            response = BuildRejectedEmailStartResponse(
                subjectId,
                email,
                displayName,
                nextPath,
                now,
                deliveryMode: "email_start_rate_limited",
                previewNote: previewNote);
            return true;
        }

        response = default!;
        return false;
    }

    private static EmailAuthStartResponse BuildRejectedEmailStartResponse(
        string subjectId,
        string email,
        string displayName,
        string? nextPath,
        DateTimeOffset now,
        string deliveryMode,
        string previewNote)
        => new(
            TicketId: string.Empty,
            SubjectId: subjectId,
            Email: email,
            DisplayName: displayName,
            NextPath: nextPath,
            CreatedAtUtc: now,
            ExpiresAtUtc: now,
            DeliveryMode: deliveryMode,
            PreviewNote: previewNote);

    private static bool IsInlinePreviewDelivery(string deliveryMode)
        => string.Equals(deliveryMode, "preview_inline_link", StringComparison.OrdinalIgnoreCase);

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

    private static bool ResolveBool(string? value, bool defaultValue)
        => bool.TryParse(value, out var parsed) ? parsed : defaultValue;

    private static int ResolvePositiveInt(string? value, int defaultValue)
        => int.TryParse(value, out var parsed) && parsed > 0 ? parsed : defaultValue;

    private static int ResolveNonNegativeInt(string? value, int defaultValue)
        => int.TryParse(value, out var parsed) && parsed >= 0 ? parsed : defaultValue;

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
