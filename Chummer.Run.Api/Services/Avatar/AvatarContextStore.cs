using System.Collections.ObjectModel;
using System.Globalization;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using Chummer.Run.Contracts.Avatar;

namespace Chummer.Run.Api.Services.Avatar;

internal enum AvatarContextStoreStatus
{
    Created,
    Granted,
    IdempotentReplay,
    Revoked,
    InvalidRequest,
    NotFound,
    Expired,
    ScenarioMismatch,
    SessionMismatch,
    NonceReplay,
    IdempotencyConflict,
    RateLimited,
    CapacityExceeded,
    InvalidState
}

internal sealed record AvatarContextSnapshot(
    string ContextRef,
    string OwnerId,
    string WorkspaceId,
    long WorkspaceRevision,
    string CharacterId,
    string? CampaignId,
    string RulesetId,
    string RuntimeFingerprint,
    string SourceDigest,
    string SourcebookFingerprint,
    string CustomDataFingerprint,
    string GmPolicyFingerprint,
    string ScenarioId,
    string DisplayName,
    string Locale,
    string CreationState,
    IReadOnlyList<string> Scopes,
    DateTimeOffset CreatedAt,
    DateTimeOffset ExpiresAt,
    string? BoundSessionId);

internal sealed record AvatarContextMintResult(
    AvatarContextStoreStatus Status,
    AvatarContextSnapshot? Context)
{
    public bool Succeeded => Status == AvatarContextStoreStatus.Created && Context is not null;
}

internal sealed record AvatarContextAuthorizationResult(
    AvatarContextStoreStatus Status,
    AvatarContextSnapshot? Context)
{
    public bool Succeeded =>
        Context is not null &&
        Status is AvatarContextStoreStatus.Granted or AvatarContextStoreStatus.IdempotentReplay;

    public bool IsIdempotentReplay => Status == AvatarContextStoreStatus.IdempotentReplay;
}

internal sealed record AvatarContextRevocationResult(
    AvatarContextStoreStatus Status,
    IReadOnlyList<AvatarContextRevocationReceipt> Receipts)
{
    public bool Succeeded => Status == AvatarContextStoreStatus.Revoked;
}

internal sealed class AvatarContextStoreOptions
{
    public int MaxContexts { get; init; } = 1_024;

    public int MaxContextsPerOwnerWorkspace { get; init; } = 8;

    public int MaxNoncesPerContext { get; init; } = 128;

    public int MaxIdempotencyEntriesPerContext { get; init; } = 64;

    public int MaxRequestsPerWindow { get; init; } = 60;

    public TimeSpan RateLimitWindow { get; init; } = TimeSpan.FromMinutes(1);
}

internal sealed class AvatarContextStore
{
    internal const int MaximumTtlSeconds = 3_600;

    private const int MaximumConfiguredContexts = 100_000;
    private const int MaximumConfiguredPerContextEntries = 4_096;
    private const int ContextReferenceBytes = 32;
    private const int ContextReferenceLength = 43;
    private const int MaximumIdentifierLength = 128;
    private const int MaximumDisplayNameLength = 160;
    private const int MaximumCreationStateLength = 128;
    private const int MaximumQuestionLength = 4_000;
    private const int ContextReferenceGenerationAttempts = 8;

    private static readonly Regex IdentifierPattern = new(
        "\\A[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\\z",
        RegexOptions.CultureInvariant | RegexOptions.NonBacktracking);

    private static readonly Regex Sha256Pattern = new(
        "\\Asha256:[0-9a-f]{64}\\z",
        RegexOptions.CultureInvariant | RegexOptions.NonBacktracking);

    private static readonly Regex LocalePattern = new(
        "\\A[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*\\z",
        RegexOptions.CultureInvariant | RegexOptions.NonBacktracking);

    private static readonly Regex ContextReferencePattern = new(
        "\\A[A-Za-z0-9_-]{43}\\z",
        RegexOptions.CultureInvariant | RegexOptions.NonBacktracking);

    private readonly object _gate = new();
    private readonly Dictionary<string, StoredContext> _contexts = new(StringComparer.Ordinal);
    private readonly TimeProvider _timeProvider;
    private readonly AvatarContextStoreOptions _options;
    private DateTimeOffset? _lastObservedAt;

    public AvatarContextStore(
        TimeProvider? timeProvider = null,
        AvatarContextStoreOptions? options = null)
    {
        _timeProvider = timeProvider ?? TimeProvider.System;
        _options = options ?? new AvatarContextStoreOptions();
        ValidateOptions(_options);
    }

    public int Count
    {
        get
        {
            lock (_gate)
            {
                if (!TryReadNow(out DateTimeOffset now))
                {
                    return 0;
                }

                SweepExpiredUnsafe(now);
                return _contexts.Count;
            }
        }
    }

    public AvatarContextMintResult Mint(AvatarContextMintRequest? request)
    {
        if (!IsValidMintRequest(request))
        {
            return new AvatarContextMintResult(AvatarContextStoreStatus.InvalidRequest, null);
        }

        lock (_gate)
        {
            if (!TryReadNow(out DateTimeOffset now))
            {
                return new AvatarContextMintResult(AvatarContextStoreStatus.InvalidState, null);
            }

            SweepExpiredUnsafe(now);
            if (_contexts.Count >= _options.MaxContexts ||
                _contexts.Values.Count(context =>
                    StringComparer.Ordinal.Equals(context.OwnerId, request!.OwnerId) &&
                    StringComparer.Ordinal.Equals(context.WorkspaceId, request.WorkspaceId)) >=
                _options.MaxContextsPerOwnerWorkspace)
            {
                return new AvatarContextMintResult(AvatarContextStoreStatus.CapacityExceeded, null);
            }

            string? contextRef = null;
            for (int attempt = 0; attempt < ContextReferenceGenerationAttempts; attempt++)
            {
                string candidate = GenerateContextReference();
                if (!_contexts.ContainsKey(candidate))
                {
                    contextRef = candidate;
                    break;
                }
            }

            if (contextRef is null)
            {
                return new AvatarContextMintResult(AvatarContextStoreStatus.InvalidState, null);
            }

            DateTimeOffset expiresAt;
            try
            {
                expiresAt = now.AddSeconds(request!.TtlSeconds);
            }
            catch (ArgumentOutOfRangeException)
            {
                return new AvatarContextMintResult(AvatarContextStoreStatus.InvalidState, null);
            }

            StoredContext stored = new(contextRef, request!, now, expiresAt);
            if (!stored.IsStructurallyValid(_options, now))
            {
                return new AvatarContextMintResult(AvatarContextStoreStatus.InvalidState, null);
            }

            _contexts.Add(contextRef, stored);
            return new AvatarContextMintResult(
                AvatarContextStoreStatus.Created,
                stored.CreateSnapshot());
        }
    }

    public AvatarContextAuthorizationResult Authorize(
        AvatarContextRequest? request,
        string? payloadDigest,
        bool admitNewOperation = true)
    {
        if (!IsValidContextRequest(request) || !IsSha256(payloadDigest))
        {
            return Denied(AvatarContextStoreStatus.InvalidRequest);
        }

        return AuthorizeCore(
            request!.ContextRef,
            request.ScenarioId,
            request.SessionId,
            request.Nonce,
            request.IdempotencyKey,
            payloadDigest!,
            admitNewOperation);
    }

    public AvatarContextAuthorizationResult Authorize(
        AvatarRuleQuestionRequest? request,
        string? payloadDigest,
        bool admitNewOperation = true)
    {
        if (!IsValidRuleQuestionRequest(request) || !IsSha256(payloadDigest))
        {
            return Denied(AvatarContextStoreStatus.InvalidRequest);
        }

        return AuthorizeCore(
            request!.ContextRef,
            request.ScenarioId,
            request.SessionId,
            request.Nonce,
            request.IdempotencyKey,
            payloadDigest!,
            admitNewOperation);
    }

    public AvatarContextRevocationResult Revoke(AvatarContextRevocationRequest? request)
    {
        if (!IsValidRevocationRequest(request))
        {
            return new AvatarContextRevocationResult(
                AvatarContextStoreStatus.InvalidRequest,
                Array.Empty<AvatarContextRevocationReceipt>());
        }

        lock (_gate)
        {
            if (!TryReadNow(out DateTimeOffset now))
            {
                return new AvatarContextRevocationResult(
                    AvatarContextStoreStatus.InvalidState,
                    Array.Empty<AvatarContextRevocationReceipt>());
            }

            SweepExpiredUnsafe(now);
            if (!_contexts.TryGetValue(request!.ContextRef, out StoredContext? stored) ||
                !StringComparer.Ordinal.Equals(stored.OwnerId, request.OwnerId) ||
                !StringComparer.Ordinal.Equals(stored.WorkspaceId, request.WorkspaceId))
            {
                return new AvatarContextRevocationResult(
                    AvatarContextStoreStatus.NotFound,
                    Array.Empty<AvatarContextRevocationReceipt>());
            }

            if (!stored.IsStructurallyValid(_options, now))
            {
                _contexts.Remove(request.ContextRef);
                return new AvatarContextRevocationResult(
                    AvatarContextStoreStatus.InvalidState,
                    Array.Empty<AvatarContextRevocationReceipt>());
            }

            _contexts.Remove(request.ContextRef);
            AvatarContextRevocationReceipt receipt = new(
                AvatarGatewayContractVersions.RevocationV1,
                ComputeDigest(request.ContextRef),
                Revoked: true,
                now);
            return new AvatarContextRevocationResult(
                AvatarContextStoreStatus.Revoked,
                Array.AsReadOnly(new[] { receipt }));
        }
    }

    public int SweepExpired()
    {
        lock (_gate)
        {
            return TryReadNow(out DateTimeOffset now) ? SweepExpiredUnsafe(now) : 0;
        }
    }

    public bool IsCurrent(AvatarContextSnapshot? expected)
    {
        if (expected is null)
        {
            return false;
        }

        lock (_gate)
        {
            if (!TryReadNow(out DateTimeOffset now))
            {
                return false;
            }
            if (!_contexts.TryGetValue(expected.ContextRef, out StoredContext? stored))
            {
                return false;
            }
            if (stored.ExpiresAt <= now)
            {
                _contexts.Remove(expected.ContextRef);
                return false;
            }
            if (!stored.IsStructurallyValid(_options, now))
            {
                _contexts.Remove(expected.ContextRef);
                return false;
            }

            AvatarContextSnapshot current = stored.CreateSnapshot();
            return current == expected
                || (StringComparer.Ordinal.Equals(current.ContextRef, expected.ContextRef)
                    && StringComparer.Ordinal.Equals(current.OwnerId, expected.OwnerId)
                    && StringComparer.Ordinal.Equals(current.WorkspaceId, expected.WorkspaceId)
                    && current.WorkspaceRevision == expected.WorkspaceRevision
                    && StringComparer.Ordinal.Equals(current.CharacterId, expected.CharacterId)
                    && StringComparer.Ordinal.Equals(current.CampaignId, expected.CampaignId)
                    && StringComparer.Ordinal.Equals(current.RulesetId, expected.RulesetId)
                    && StringComparer.Ordinal.Equals(current.RuntimeFingerprint, expected.RuntimeFingerprint)
                    && StringComparer.Ordinal.Equals(current.SourceDigest, expected.SourceDigest)
                    && StringComparer.Ordinal.Equals(current.SourcebookFingerprint, expected.SourcebookFingerprint)
                    && StringComparer.Ordinal.Equals(current.CustomDataFingerprint, expected.CustomDataFingerprint)
                    && StringComparer.Ordinal.Equals(current.GmPolicyFingerprint, expected.GmPolicyFingerprint)
                    && StringComparer.Ordinal.Equals(current.ScenarioId, expected.ScenarioId)
                    && StringComparer.Ordinal.Equals(current.DisplayName, expected.DisplayName)
                    && StringComparer.Ordinal.Equals(current.Locale, expected.Locale)
                    && StringComparer.Ordinal.Equals(current.CreationState, expected.CreationState)
                    && current.CreatedAt == expected.CreatedAt
                    && current.ExpiresAt == expected.ExpiresAt
                    && StringComparer.Ordinal.Equals(current.BoundSessionId, expected.BoundSessionId)
                    && current.Scopes.SequenceEqual(expected.Scopes, StringComparer.Ordinal));
        }
    }

    private AvatarContextAuthorizationResult AuthorizeCore(
        string contextRef,
        string scenarioId,
        string sessionId,
        string nonce,
        string idempotencyKey,
        string payloadDigest,
        bool admitNewOperation)
    {
        lock (_gate)
        {
            if (!TryReadNow(out DateTimeOffset now))
            {
                return Denied(AvatarContextStoreStatus.InvalidState);
            }

            if (!_contexts.TryGetValue(contextRef, out StoredContext? stored))
            {
                SweepExpiredUnsafe(now);
                return Denied(AvatarContextStoreStatus.NotFound);
            }

            if (stored.ExpiresAt <= now)
            {
                _contexts.Remove(contextRef);
                SweepExpiredUnsafe(now);
                return Denied(AvatarContextStoreStatus.Expired);
            }

            if (!stored.IsStructurallyValid(_options, now))
            {
                _contexts.Remove(contextRef);
                return Denied(AvatarContextStoreStatus.InvalidState);
            }

            SweepExpiredUnsafe(now, contextRef);
            if (!StringComparer.Ordinal.Equals(stored.ScenarioId, scenarioId))
            {
                return Denied(AvatarContextStoreStatus.ScenarioMismatch);
            }

            if (stored.BoundSessionId is not null &&
                !StringComparer.Ordinal.Equals(stored.BoundSessionId, sessionId))
            {
                return Denied(AvatarContextStoreStatus.SessionMismatch);
            }

            DateTimeOffset rateCutoff = now - _options.RateLimitWindow;
            while (stored.Requests.Count > 0 && stored.Requests.Peek() <= rateCutoff)
            {
                stored.Requests.Dequeue();
            }

            if (stored.Requests.Count >= _options.MaxRequestsPerWindow)
            {
                return Denied(AvatarContextStoreStatus.RateLimited);
            }

            if (stored.Nonces.Contains(nonce))
            {
                return Denied(AvatarContextStoreStatus.NonceReplay);
            }

            if (stored.Nonces.Count >= _options.MaxNoncesPerContext)
            {
                return Denied(AvatarContextStoreStatus.CapacityExceeded);
            }

            if (!admitNewOperation)
            {
                if (stored.Idempotency.TryGetValue(idempotencyKey, out string? existingDigest))
                {
                    return StringComparer.Ordinal.Equals(existingDigest, payloadDigest)
                        ? new AvatarContextAuthorizationResult(
                            AvatarContextStoreStatus.IdempotentReplay,
                            stored.CreateSnapshot())
                        : Denied(AvatarContextStoreStatus.IdempotencyConflict);
                }
                return Denied(AvatarContextStoreStatus.CapacityExceeded);
            }

            stored.Requests.Enqueue(now);
            stored.Nonces.Add(nonce);

            if (stored.Idempotency.TryGetValue(idempotencyKey, out string? priorDigest))
            {
                if (!StringComparer.Ordinal.Equals(priorDigest, payloadDigest))
                {
                    return Denied(AvatarContextStoreStatus.IdempotencyConflict);
                }

                stored.BoundSessionId ??= sessionId;
                return new AvatarContextAuthorizationResult(
                    AvatarContextStoreStatus.IdempotentReplay,
                    stored.CreateSnapshot());
            }

            if (stored.Idempotency.Count >= _options.MaxIdempotencyEntriesPerContext)
            {
                return Denied(AvatarContextStoreStatus.CapacityExceeded);
            }

            stored.Idempotency.Add(idempotencyKey, payloadDigest);
            stored.BoundSessionId ??= sessionId;
            return new AvatarContextAuthorizationResult(
                AvatarContextStoreStatus.Granted,
                stored.CreateSnapshot());
        }
    }

    private int SweepExpiredUnsafe(DateTimeOffset now, string? exceptContextRef = null)
    {
        string[] expired = _contexts.Values
            .Where(context =>
                !StringComparer.Ordinal.Equals(context.ContextRef, exceptContextRef) &&
                context.ExpiresAt <= now)
            .Select(static context => context.ContextRef)
            .ToArray();

        foreach (string contextRef in expired)
        {
            _contexts.Remove(contextRef);
        }

        return expired.Length;
    }

    private bool TryReadNow(out DateTimeOffset now)
    {
        try
        {
            now = _timeProvider.GetUtcNow();
        }
        catch
        {
            now = default;
            return false;
        }

        if (now == default || (_lastObservedAt.HasValue && now < _lastObservedAt.Value))
        {
            return false;
        }

        _lastObservedAt = now;
        return true;
    }

    private static AvatarContextAuthorizationResult Denied(AvatarContextStoreStatus status) =>
        new(status, null);

    private static bool IsValidMintRequest(AvatarContextMintRequest? request)
    {
        if (request is null ||
            !StringComparer.Ordinal.Equals(
                request.ContractName,
                AvatarGatewayContractVersions.SessionContextV1) ||
            !IsIdentifier(request.OwnerId) ||
            !IsIdentifier(request.WorkspaceId) ||
            request.WorkspaceRevision < 0 ||
            !IsIdentifier(request.CharacterId) ||
            (request.CampaignId is not null && !IsIdentifier(request.CampaignId)) ||
            !IsIdentifier(request.RulesetId) ||
            !IsSha256(request.RuntimeFingerprint) ||
            !IsSha256(request.SourceDigest) ||
            !IsSha256(request.SourcebookFingerprint) ||
            !IsSha256(request.CustomDataFingerprint) ||
            !IsSha256(request.GmPolicyFingerprint) ||
            !IsIdentifier(request.ScenarioId) ||
            !IsSafeText(request.DisplayName, MaximumDisplayNameLength) ||
            !IsLocale(request.Locale) ||
            !IsSafeText(request.CreationState, MaximumCreationStateLength) ||
            request.Scopes is null ||
            request.Scopes.Count == 0 ||
            request.Scopes.Count > AvatarGatewayScopes.Allowed.Count ||
            request.TtlSeconds <= 0 ||
            request.TtlSeconds > MaximumTtlSeconds)
        {
            return false;
        }

        HashSet<string> uniqueScopes = new(StringComparer.Ordinal);
        foreach (string? scope in request.Scopes)
        {
            if (scope is null ||
                !AvatarGatewayScopes.Allowed.Contains(scope) ||
                !uniqueScopes.Add(scope))
            {
                return false;
            }
        }

        return true;
    }

    private static bool IsValidContextRequest(AvatarContextRequest? request) =>
        request is not null &&
        StringComparer.Ordinal.Equals(request.ContractName, AvatarGatewayContractVersions.ContextRequestV1) &&
        IsContextReference(request.ContextRef) &&
        IsIdentifier(request.ScenarioId) &&
        IsIdentifier(request.SessionId) &&
        IsIdentifier(request.Nonce) &&
        IsIdentifier(request.IdempotencyKey);

    private static bool IsValidRuleQuestionRequest(AvatarRuleQuestionRequest? request) =>
        request is not null &&
        StringComparer.Ordinal.Equals(request.ContractName, AvatarGatewayContractVersions.RuleQuestionV1) &&
        IsContextReference(request.ContextRef) &&
        IsIdentifier(request.ScenarioId) &&
        IsIdentifier(request.SessionId) &&
        IsIdentifier(request.Nonce) &&
        IsIdentifier(request.IdempotencyKey) &&
        IsSafeQuestion(request.Question) &&
        (request.SubjectId is null || IsIdentifier(request.SubjectId));

    private static bool IsValidRevocationRequest(AvatarContextRevocationRequest? request) =>
        request is not null &&
        StringComparer.Ordinal.Equals(request.ContractName, AvatarGatewayContractVersions.RevocationV1) &&
        IsContextReference(request.ContextRef) &&
        IsIdentifier(request.OwnerId) &&
        IsIdentifier(request.WorkspaceId);

    private static bool IsIdentifier(string? value) =>
        value is { Length: > 0 and <= MaximumIdentifierLength } && IdentifierPattern.IsMatch(value);

    private static bool IsSha256(string? value) =>
        value is not null && Sha256Pattern.IsMatch(value);

    private static bool IsLocale(string? value)
    {
        if (value is null || value.Length > 35 || !LocalePattern.IsMatch(value))
        {
            return false;
        }

        try
        {
            return StringComparer.Ordinal.Equals(CultureInfo.GetCultureInfo(value).Name, value);
        }
        catch (CultureNotFoundException)
        {
            return false;
        }
    }

    private static bool IsSafeText(string? value, int maximumLength) =>
        value is { Length: > 0 } &&
        value.Length <= maximumLength &&
        !value.Any(char.IsControl);

    private static bool IsSafeQuestion(string? value) =>
        value is { Length: > 0 and <= MaximumQuestionLength } &&
        value.Any(static character => !char.IsWhiteSpace(character)) &&
        !value.Any(static character => char.IsControl(character) && character is not '\r' and not '\n' and not '\t');

    private static string GenerateContextReference()
    {
        byte[] bytes = RandomNumberGenerator.GetBytes(ContextReferenceBytes);
        return Convert.ToBase64String(bytes)
            .TrimEnd('=')
            .Replace('+', '-')
            .Replace('/', '_');
    }

    private static bool IsContextReference(string? contextRef)
    {
        if (contextRef is null ||
            contextRef.Length != ContextReferenceLength ||
            !ContextReferencePattern.IsMatch(contextRef))
        {
            return false;
        }

        try
        {
            string standard = contextRef.Replace('-', '+').Replace('_', '/') + "=";
            byte[] decoded = Convert.FromBase64String(standard);
            if (decoded.Length != ContextReferenceBytes)
            {
                return false;
            }

            string canonical = Convert.ToBase64String(decoded)
                .TrimEnd('=')
                .Replace('+', '-')
                .Replace('/', '_');
            return StringComparer.Ordinal.Equals(canonical, contextRef);
        }
        catch (FormatException)
        {
            return false;
        }
    }

    private static string ComputeDigest(string value)
    {
        byte[] digest = SHA256.HashData(Encoding.UTF8.GetBytes(value));
        return $"sha256:{Convert.ToHexString(digest).ToLowerInvariant()}";
    }

    private static void ValidateOptions(AvatarContextStoreOptions options)
    {
        ArgumentNullException.ThrowIfNull(options);
        if (options.MaxContexts is <= 0 or > MaximumConfiguredContexts)
        {
            throw new ArgumentOutOfRangeException(nameof(options.MaxContexts));
        }

        if (options.MaxContextsPerOwnerWorkspace <= 0 ||
            options.MaxContextsPerOwnerWorkspace > options.MaxContexts)
        {
            throw new ArgumentOutOfRangeException(nameof(options.MaxContextsPerOwnerWorkspace));
        }

        if (options.MaxNoncesPerContext is <= 0 or > MaximumConfiguredPerContextEntries)
        {
            throw new ArgumentOutOfRangeException(nameof(options.MaxNoncesPerContext));
        }

        if (options.MaxIdempotencyEntriesPerContext is <= 0 or > MaximumConfiguredPerContextEntries)
        {
            throw new ArgumentOutOfRangeException(nameof(options.MaxIdempotencyEntriesPerContext));
        }

        if (options.MaxRequestsPerWindow is <= 0 or > MaximumConfiguredPerContextEntries)
        {
            throw new ArgumentOutOfRangeException(nameof(options.MaxRequestsPerWindow));
        }

        if (options.RateLimitWindow <= TimeSpan.Zero ||
            options.RateLimitWindow > TimeSpan.FromSeconds(MaximumTtlSeconds))
        {
            throw new ArgumentOutOfRangeException(nameof(options.RateLimitWindow));
        }
    }

    private sealed class StoredContext
    {
        private readonly ReadOnlyCollection<string> _scopes;

        public StoredContext(
            string contextRef,
            AvatarContextMintRequest request,
            DateTimeOffset createdAt,
            DateTimeOffset expiresAt)
        {
            ContextRef = contextRef;
            OwnerId = request.OwnerId;
            WorkspaceId = request.WorkspaceId;
            WorkspaceRevision = request.WorkspaceRevision;
            CharacterId = request.CharacterId;
            CampaignId = request.CampaignId;
            RulesetId = request.RulesetId;
            RuntimeFingerprint = request.RuntimeFingerprint;
            SourceDigest = request.SourceDigest;
            SourcebookFingerprint = request.SourcebookFingerprint;
            CustomDataFingerprint = request.CustomDataFingerprint;
            GmPolicyFingerprint = request.GmPolicyFingerprint;
            ScenarioId = request.ScenarioId;
            DisplayName = request.DisplayName;
            Locale = request.Locale;
            CreationState = request.CreationState;
            _scopes = Array.AsReadOnly(request.Scopes.ToArray());
            CreatedAt = createdAt;
            ExpiresAt = expiresAt;
        }

        public string ContextRef { get; }

        public string OwnerId { get; }

        public string WorkspaceId { get; }

        public long WorkspaceRevision { get; }

        public string CharacterId { get; }

        public string? CampaignId { get; }

        public string RulesetId { get; }

        public string RuntimeFingerprint { get; }

        public string SourceDigest { get; }

        public string SourcebookFingerprint { get; }

        public string CustomDataFingerprint { get; }

        public string GmPolicyFingerprint { get; }

        public string ScenarioId { get; }

        public string DisplayName { get; }

        public string Locale { get; }

        public string CreationState { get; }

        public DateTimeOffset CreatedAt { get; }

        public DateTimeOffset ExpiresAt { get; }

        public string? BoundSessionId { get; set; }

        public HashSet<string> Nonces { get; } = new(StringComparer.Ordinal);

        public Dictionary<string, string> Idempotency { get; } = new(StringComparer.Ordinal);

        public Queue<DateTimeOffset> Requests { get; } = new();

        public AvatarContextSnapshot CreateSnapshot() => new(
            ContextRef,
            OwnerId,
            WorkspaceId,
            WorkspaceRevision,
            CharacterId,
            CampaignId,
            RulesetId,
            RuntimeFingerprint,
            SourceDigest,
            SourcebookFingerprint,
            CustomDataFingerprint,
            GmPolicyFingerprint,
            ScenarioId,
            DisplayName,
            Locale,
            CreationState,
            Array.AsReadOnly(_scopes.ToArray()),
            CreatedAt,
            ExpiresAt,
            BoundSessionId);

        public bool IsStructurallyValid(AvatarContextStoreOptions options, DateTimeOffset now)
        {
            if (!IsContextReference(ContextRef) ||
                !IsIdentifier(OwnerId) ||
                !IsIdentifier(WorkspaceId) ||
                WorkspaceRevision < 0 ||
                !IsIdentifier(CharacterId) ||
                (CampaignId is not null && !IsIdentifier(CampaignId)) ||
                !IsIdentifier(RulesetId) ||
                !IsSha256(RuntimeFingerprint) ||
                !IsSha256(SourceDigest) ||
                !IsSha256(SourcebookFingerprint) ||
                !IsSha256(CustomDataFingerprint) ||
                !IsSha256(GmPolicyFingerprint) ||
                !IsIdentifier(ScenarioId) ||
                !IsSafeText(DisplayName, MaximumDisplayNameLength) ||
                !IsLocale(Locale) ||
                !IsSafeText(CreationState, MaximumCreationStateLength) ||
                _scopes.Count == 0 ||
                _scopes.Count > AvatarGatewayScopes.Allowed.Count ||
                _scopes.Any(scope => !AvatarGatewayScopes.Allowed.Contains(scope)) ||
                _scopes.Distinct(StringComparer.Ordinal).Count() != _scopes.Count ||
                ExpiresAt <= CreatedAt ||
                ExpiresAt - CreatedAt > TimeSpan.FromSeconds(MaximumTtlSeconds) ||
                CreatedAt > now ||
                (BoundSessionId is not null && !IsIdentifier(BoundSessionId)) ||
                Nonces.Count > options.MaxNoncesPerContext ||
                Nonces.Any(nonce => !IsIdentifier(nonce)) ||
                Idempotency.Count > options.MaxIdempotencyEntriesPerContext ||
                Idempotency.Any(pair => !IsIdentifier(pair.Key) || !IsSha256(pair.Value)) ||
                Requests.Count > options.MaxRequestsPerWindow ||
                Requests.Any(timestamp => timestamp < CreatedAt || timestamp > now))
            {
                return false;
            }

            return true;
        }
    }
}
