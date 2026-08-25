using Chummer.Run.Contracts.Avatar;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace Chummer.Run.Api.Services.Avatar;

public enum AvatarGatewayCallStatus
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

public sealed record AvatarGatewayOperationResult<T>(
    AvatarGatewayCallStatus Status,
    T? Value)
{
    public bool Succeeded => Value is not null
        && Status is AvatarGatewayCallStatus.Created
            or AvatarGatewayCallStatus.Granted
            or AvatarGatewayCallStatus.IdempotentReplay
            or AvatarGatewayCallStatus.Revoked;
}

public interface IAvatarGatewayService
{
    AvatarGatewayOperationResult<AvatarSessionContextProjection> Mint(AvatarContextMintRequest? request);

    AvatarGatewayOperationResult<AvatarSessionContextProjection> GetContext(AvatarContextRequest? request);

    Task<AvatarGatewayOperationResult<AvatarRuleAnswerEnvelope>> ResolveRuleAsync(
        AvatarRuleQuestionRequest? request,
        CancellationToken cancellationToken);

    AvatarGatewayOperationResult<AvatarContextRevocationReceipt> Revoke(AvatarContextRevocationRequest? request);
}

internal sealed class AvatarGatewayService(
    AvatarContextStore contextStore,
    IAvatarRuleAuthorityClient ruleAuthorityClient,
    TimeProvider timeProvider,
    int maximumCachedOperations = 8_192) : IAvatarGatewayService
{
    private readonly int _maximumCachedOperations = maximumCachedOperations is > 0 and <= 65_536
        ? maximumCachedOperations
        : throw new ArgumentOutOfRangeException(nameof(maximumCachedOperations));

    private readonly object _gate = new();
    private readonly Dictionary<OperationKey, CachedContextProjection> _contextResponses = [];
    private readonly Dictionary<OperationKey, CachedRuleAnswer> _ruleResponses = [];
    private readonly Dictionary<string, ContextLifetime> _contextLifetimes = new(StringComparer.Ordinal);

    public AvatarGatewayOperationResult<AvatarSessionContextProjection> Mint(
        AvatarContextMintRequest? request)
    {
        lock (_gate)
        {
            SweepCachesUnsafe();
            AvatarContextMintResult minted = contextStore.Mint(request);
            if (!minted.Succeeded)
            {
                return new AvatarGatewayOperationResult<AvatarSessionContextProjection>(Map(minted.Status), null);
            }

            AvatarContextSnapshot context = minted.Context!;
            if (_contextLifetimes.ContainsKey(context.ContextRef))
            {
                return new AvatarGatewayOperationResult<AvatarSessionContextProjection>(AvatarGatewayCallStatus.InvalidState, null);
            }
            _contextLifetimes.Add(
                context.ContextRef,
                new ContextLifetime(new CancellationTokenSource(), context.ExpiresAt));
            return new AvatarGatewayOperationResult<AvatarSessionContextProjection>(
                Map(minted.Status),
                Project(context));
        }
    }

    public AvatarGatewayOperationResult<AvatarSessionContextProjection> GetContext(
        AvatarContextRequest? request)
    {
        string payloadDigest = ComputePayloadDigest(request);
        lock (_gate)
        {
            SweepCachesUnsafe();
            if (request is not null
                && CachedOperationCountUnsafe() >= _maximumCachedOperations
                && !_contextResponses.ContainsKey(new OperationKey(request.ContextRef, request.IdempotencyKey)))
            {
                AvatarContextAuthorizationResult probe = contextStore.Authorize(
                    request,
                    payloadDigest,
                    admitNewOperation: false);
                return new AvatarGatewayOperationResult<AvatarSessionContextProjection>(
                    probe.IsIdempotentReplay
                        ? AvatarGatewayCallStatus.InvalidState
                        : Map(probe.Status),
                    null);
            }
            AvatarContextAuthorizationResult authorization = contextStore.Authorize(request, payloadDigest);
            if (!authorization.Succeeded)
            {
                return new AvatarGatewayOperationResult<AvatarSessionContextProjection>(Map(authorization.Status), null);
            }

            OperationKey key = new(authorization.Context!.ContextRef, request!.IdempotencyKey);
            if (authorization.IsIdempotentReplay)
            {
                return _contextResponses.TryGetValue(key, out CachedContextProjection? cached)
                    ? new AvatarGatewayOperationResult<AvatarSessionContextProjection>(Map(authorization.Status), cached.Value)
                    : new AvatarGatewayOperationResult<AvatarSessionContextProjection>(AvatarGatewayCallStatus.InvalidState, null);
            }

            if (CachedOperationCountUnsafe() >= _maximumCachedOperations)
            {
                return new AvatarGatewayOperationResult<AvatarSessionContextProjection>(AvatarGatewayCallStatus.CapacityExceeded, null);
            }

            AvatarSessionContextProjection projection = Project(authorization.Context);
            _contextResponses.Add(key, new CachedContextProjection(projection, authorization.Context.ExpiresAt));
            return new AvatarGatewayOperationResult<AvatarSessionContextProjection>(Map(authorization.Status), projection);
        }
    }

    public async Task<AvatarGatewayOperationResult<AvatarRuleAnswerEnvelope>> ResolveRuleAsync(
        AvatarRuleQuestionRequest? request,
        CancellationToken cancellationToken)
    {
        string payloadDigest = ComputePayloadDigest(request);
        Task<AvatarRuleAnswerEnvelope> answerTask;
        AvatarContextSnapshot authorizedContext;
        AvatarGatewayCallStatus resultStatus;
        lock (_gate)
        {
            SweepCachesUnsafe();
            if (request is not null
                && CachedOperationCountUnsafe() >= _maximumCachedOperations
                && !_ruleResponses.ContainsKey(new OperationKey(request.ContextRef, request.IdempotencyKey)))
            {
                AvatarContextAuthorizationResult probe = contextStore.Authorize(
                    request,
                    payloadDigest,
                    admitNewOperation: false);
                return new AvatarGatewayOperationResult<AvatarRuleAnswerEnvelope>(
                    probe.IsIdempotentReplay
                        ? AvatarGatewayCallStatus.InvalidState
                        : Map(probe.Status),
                    null);
            }
            AvatarContextAuthorizationResult authorization = contextStore.Authorize(request, payloadDigest);
            if (!authorization.Succeeded)
            {
                return new AvatarGatewayOperationResult<AvatarRuleAnswerEnvelope>(Map(authorization.Status), null);
            }

            OperationKey key = new(authorization.Context!.ContextRef, request!.IdempotencyKey);
            authorizedContext = authorization.Context;
            if (!_contextLifetimes.TryGetValue(authorizedContext.ContextRef, out ContextLifetime? lifetime)
                || lifetime.Cancellation.IsCancellationRequested
                || lifetime.ExpiresAt != authorizedContext.ExpiresAt)
            {
                return new AvatarGatewayOperationResult<AvatarRuleAnswerEnvelope>(AvatarGatewayCallStatus.InvalidState, null);
            }
            resultStatus = Map(authorization.Status);
            if (authorization.IsIdempotentReplay)
            {
                if (!_ruleResponses.TryGetValue(key, out CachedRuleAnswer? cached))
                {
                    return new AvatarGatewayOperationResult<AvatarRuleAnswerEnvelope>(AvatarGatewayCallStatus.InvalidState, null);
                }
                answerTask = cached.Value;
            }
            else
            {
                if (CachedOperationCountUnsafe() >= _maximumCachedOperations)
                {
                    return new AvatarGatewayOperationResult<AvatarRuleAnswerEnvelope>(AvatarGatewayCallStatus.CapacityExceeded, null);
                }

                AvatarRuleAuthorityRequest authorityRequest = BuildAuthorityRequest(authorization.Context, request);
                answerTask = HasRuleCharacterScopes(authorization.Context)
                    ? ResolveRuleCoreAsync(authorityRequest, lifetime.Cancellation.Token)
                    : Task.FromResult(SafeScopeFailure(authorityRequest));
                _ruleResponses.Add(key, new CachedRuleAnswer(answerTask, authorization.Context.ExpiresAt));
            }
        }

        AvatarRuleAnswerEnvelope answer;
        try
        {
            answer = await answerTask.WaitAsync(cancellationToken).ConfigureAwait(false);
        }
        catch (OperationCanceledException) when (!cancellationToken.IsCancellationRequested)
        {
            return new AvatarGatewayOperationResult<AvatarRuleAnswerEnvelope>(AvatarGatewayCallStatus.Expired, null);
        }

        lock (_gate)
        {
            if (!_contextLifetimes.TryGetValue(authorizedContext.ContextRef, out ContextLifetime? lifetime)
                || lifetime.Cancellation.IsCancellationRequested
                || !contextStore.IsCurrent(authorizedContext))
            {
                return new AvatarGatewayOperationResult<AvatarRuleAnswerEnvelope>(AvatarGatewayCallStatus.Expired, null);
            }
            return new AvatarGatewayOperationResult<AvatarRuleAnswerEnvelope>(resultStatus, answer);
        }
    }

    public AvatarGatewayOperationResult<AvatarContextRevocationReceipt> Revoke(
        AvatarContextRevocationRequest? request)
    {
        lock (_gate)
        {
            AvatarContextRevocationResult revoked = contextStore.Revoke(request);
            if (!revoked.Succeeded || revoked.Receipts.Count != 1)
            {
                return new AvatarGatewayOperationResult<AvatarContextRevocationReceipt>(Map(revoked.Status), null);
            }

            if (request is not null)
            {
                if (_contextLifetimes.Remove(request.ContextRef, out ContextLifetime? lifetime))
                {
                    CancelAndDispose(lifetime.Cancellation);
                }
                RemoveContextCachesUnsafe(request.ContextRef);
            }
            return new AvatarGatewayOperationResult<AvatarContextRevocationReceipt>(
                Map(revoked.Status),
                revoked.Receipts[0]);
        }
    }

    private async Task<AvatarRuleAnswerEnvelope> ResolveRuleCoreAsync(
        AvatarRuleAuthorityRequest request,
        CancellationToken cancellationToken)
    {
        try
        {
            return await ruleAuthorityClient.ResolveAsync(request, cancellationToken).ConfigureAwait(false);
        }
        catch (AvatarRuleAuthorityException exception)
        {
            return exception.StatusCode switch
            {
                StatusCodes.Status409Conflict => SafeAuthorityConflict(request, exception.Reason),
                StatusCodes.Status410Gone => SafeAuthorityStale(request, exception.Reason),
                _ => AvatarRuleAnswerValidator.SafeUnavailable(request, exception.Reason)
            };
        }
        catch (Exception exception) when (exception is InvalidOperationException
            or IOException
            or JsonException
            or NotSupportedException)
        {
            return AvatarRuleAnswerValidator.SafeUnavailable(
                request,
                "avatar-rule-authority-unexpected-failure");
        }
    }

    private static AvatarRuleAnswerEnvelope SafeScopeFailure(AvatarRuleAuthorityRequest request)
        => AvatarRuleAnswerValidator.SafeFailure(
            request,
            AvatarGatewayStatuses.Forbidden,
            IsGerman(request.Locale)
                ? "Dieser Rook-Kontext ist nicht für charakterbezogene Regelfragen freigegeben."
                : "This Rook context is not authorized for character-bound rule questions.",
            IsGerman(request.Locale)
                ? "Regelabfrage nicht freigegeben."
                : "Rule question is not authorized.",
            "required-read-scopes-missing");

    private static AvatarRuleAnswerEnvelope SafeAuthorityConflict(
        AvatarRuleAuthorityRequest request,
        string reason)
        => AvatarRuleAnswerValidator.SafeFailure(
            request,
            AvatarGatewayStatuses.Conflict,
            IsGerman(request.Locale)
                ? "Der Charakter wurde seit Beginn dieser Analyse verändert. Bitte lade den aktuellen Kontext neu."
                : "The character changed after this analysis began. Reload the current context.",
            IsGerman(request.Locale)
                ? "Charakterkontext hat sich geändert."
                : "The character context changed.",
            reason);

    private static AvatarRuleAnswerEnvelope SafeAuthorityStale(
        AvatarRuleAuthorityRequest request,
        string reason)
        => AvatarRuleAnswerValidator.SafeFailure(
            request,
            AvatarGatewayStatuses.Stale,
            IsGerman(request.Locale)
                ? "Dieser Charakterkontext ist abgelaufen. Bitte öffne Rook erneut aus Chummer."
                : "This character context expired. Open Rook again from Chummer.",
            IsGerman(request.Locale)
                ? "Charakterkontext ist abgelaufen."
                : "The character context expired.",
            reason);

    private static bool IsGerman(string? locale)
        => locale?.StartsWith("de", StringComparison.OrdinalIgnoreCase) is true;

    private static AvatarRuleAuthorityRequest BuildAuthorityRequest(
        AvatarContextSnapshot context,
        AvatarRuleQuestionRequest request)
        => new(
            AvatarGatewayContractVersions.RuleAuthorityRequestV1,
            context.OwnerId,
            context.WorkspaceId,
            context.WorkspaceRevision,
            context.CharacterId,
            context.CampaignId,
            context.RulesetId,
            context.RuntimeFingerprint,
            context.SourceDigest,
            context.SourcebookFingerprint,
            context.CustomDataFingerprint,
            context.GmPolicyFingerprint,
            context.Locale,
            request.Question,
            request.SubjectId);

    private static AvatarSessionContextProjection Project(AvatarContextSnapshot context)
    {
        bool ruleQuestions = HasRuleCharacterScopes(context);
        IReadOnlyList<string> modes = ruleQuestions ? ["rule-question"] : [];
        bool german = context.Locale.StartsWith("de", StringComparison.OrdinalIgnoreCase);
        string summary = ruleQuestions
            ? german
                ? $"Ich habe {context.DisplayName} in {context.RulesetId} geladen. Regelfragen sind bereit."
                : $"I loaded {context.DisplayName} in {context.RulesetId}. Rule questions are ready."
            : german
                ? $"Ich habe {context.DisplayName} geladen, aber dieser Kontext erlaubt keine charakterbezogenen Regelfragen."
                : $"I loaded {context.DisplayName}, but this context does not permit character-bound rule questions.";
        return new AvatarSessionContextProjection(
            AvatarGatewayContractVersions.ContextResponseV1,
            context.ContextRef,
            context.RulesetId,
            context.DisplayName,
            context.CreationState,
            context.WorkspaceRevision,
            context.RuntimeFingerprint,
            context.SourceDigest,
            context.Locale,
            modes,
            summary,
            context.ExpiresAt);
    }

    private static bool HasRuleCharacterScopes(AvatarContextSnapshot context)
        => context.Scopes.Contains(AvatarGatewayScopes.RulesRead, StringComparer.Ordinal)
            && context.Scopes.Contains(AvatarGatewayScopes.CharacterRead, StringComparer.Ordinal);

    private static AvatarGatewayCallStatus Map(AvatarContextStoreStatus status)
        => status switch
        {
            AvatarContextStoreStatus.Created => AvatarGatewayCallStatus.Created,
            AvatarContextStoreStatus.Granted => AvatarGatewayCallStatus.Granted,
            AvatarContextStoreStatus.IdempotentReplay => AvatarGatewayCallStatus.IdempotentReplay,
            AvatarContextStoreStatus.Revoked => AvatarGatewayCallStatus.Revoked,
            AvatarContextStoreStatus.InvalidRequest => AvatarGatewayCallStatus.InvalidRequest,
            AvatarContextStoreStatus.NotFound => AvatarGatewayCallStatus.NotFound,
            AvatarContextStoreStatus.Expired => AvatarGatewayCallStatus.Expired,
            AvatarContextStoreStatus.ScenarioMismatch => AvatarGatewayCallStatus.ScenarioMismatch,
            AvatarContextStoreStatus.SessionMismatch => AvatarGatewayCallStatus.SessionMismatch,
            AvatarContextStoreStatus.NonceReplay => AvatarGatewayCallStatus.NonceReplay,
            AvatarContextStoreStatus.IdempotencyConflict => AvatarGatewayCallStatus.IdempotencyConflict,
            AvatarContextStoreStatus.RateLimited => AvatarGatewayCallStatus.RateLimited,
            AvatarContextStoreStatus.CapacityExceeded => AvatarGatewayCallStatus.CapacityExceeded,
            _ => AvatarGatewayCallStatus.InvalidState
        };

    private static string ComputePayloadDigest(AvatarContextRequest? request)
    {
        StringBuilder canonical = new();
        AddDigestField(canonical, "operation", "context");
        AddDigestField(canonical, "contract", request?.ContractName);
        AddDigestField(canonical, "context_ref", request?.ContextRef);
        AddDigestField(canonical, "scenario_id", request?.ScenarioId);
        AddDigestField(canonical, "session_id", request?.SessionId);
        AddDigestField(canonical, "idempotency_key", request?.IdempotencyKey);
        return HashCanonical(canonical);
    }

    private static string ComputePayloadDigest(AvatarRuleQuestionRequest? request)
    {
        StringBuilder canonical = new();
        AddDigestField(canonical, "operation", "rule-question");
        AddDigestField(canonical, "contract", request?.ContractName);
        AddDigestField(canonical, "context_ref", request?.ContextRef);
        AddDigestField(canonical, "scenario_id", request?.ScenarioId);
        AddDigestField(canonical, "session_id", request?.SessionId);
        AddDigestField(canonical, "idempotency_key", request?.IdempotencyKey);
        AddDigestField(canonical, "question", request?.Question);
        AddDigestField(canonical, "subject_id", request?.SubjectId);
        return HashCanonical(canonical);
    }

    private static void AddDigestField(StringBuilder canonical, string name, string? value)
    {
        value ??= string.Empty;
        canonical.Append(name.Length).Append(':').Append(name)
            .Append(':').Append(value.Length).Append(':').Append(value).Append('\n');
    }

    private static string HashCanonical(StringBuilder canonical)
        => $"sha256:{Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(canonical.ToString()))).ToLowerInvariant()}";

    private int CachedOperationCountUnsafe() => _contextResponses.Count + _ruleResponses.Count;

    private void SweepCachesUnsafe()
    {
        DateTimeOffset now;
        try
        {
            now = timeProvider.GetUtcNow();
        }
        catch
        {
            _contextResponses.Clear();
            _ruleResponses.Clear();
            foreach (ContextLifetime lifetime in _contextLifetimes.Values)
            {
                CancelAndDispose(lifetime.Cancellation);
            }
            _contextLifetimes.Clear();
            return;
        }

        foreach (OperationKey key in _contextResponses
                     .Where(pair => pair.Value.ExpiresAt <= now)
                     .Select(static pair => pair.Key)
                     .ToArray())
        {
            _contextResponses.Remove(key);
        }
        foreach (OperationKey key in _ruleResponses
                     .Where(pair => pair.Value.ExpiresAt <= now)
                     .Select(static pair => pair.Key)
                     .ToArray())
        {
            _ruleResponses.Remove(key);
        }
        foreach (string contextRef in _contextLifetimes
                     .Where(pair => pair.Value.ExpiresAt <= now)
                     .Select(static pair => pair.Key)
                     .ToArray())
        {
            ContextLifetime lifetime = _contextLifetimes[contextRef];
            _contextLifetimes.Remove(contextRef);
            CancelAndDispose(lifetime.Cancellation);
        }
    }

    private void RemoveContextCachesUnsafe(string contextRef)
    {
        foreach (OperationKey key in _contextResponses.Keys
                     .Where(key => StringComparer.Ordinal.Equals(key.ContextRef, contextRef))
                     .ToArray())
        {
            _contextResponses.Remove(key);
        }
        foreach (OperationKey key in _ruleResponses.Keys
                     .Where(key => StringComparer.Ordinal.Equals(key.ContextRef, contextRef))
                     .ToArray())
        {
            _ruleResponses.Remove(key);
        }
    }

    private static void CancelAndDispose(CancellationTokenSource cancellation)
    {
        try
        {
            cancellation.Cancel();
        }
        catch (AggregateException)
        {
            // The context remains revoked even if an upstream cancellation callback misbehaves.
        }
        catch (ObjectDisposedException)
        {
            // A prior fail-closed sweep already disposed this lifetime.
        }
        finally
        {
            cancellation.Dispose();
        }
    }

    private sealed record OperationKey(string ContextRef, string IdempotencyKey);

    private sealed record CachedContextProjection(
        AvatarSessionContextProjection Value,
        DateTimeOffset ExpiresAt);

    private sealed record CachedRuleAnswer(
        Task<AvatarRuleAnswerEnvelope> Value,
        DateTimeOffset ExpiresAt);

    private sealed record ContextLifetime(
        CancellationTokenSource Cancellation,
        DateTimeOffset ExpiresAt);
}
