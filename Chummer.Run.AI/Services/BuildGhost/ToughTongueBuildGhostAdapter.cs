using Chummer.Run.Contracts.BuildGhost;
using Microsoft.Extensions.Configuration;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace Chummer.Run.AI.Services.BuildGhost;

public interface IToughTongueBuildGhostAdapter
{
    Task<ToughTongueBuildGhostResult> ExplainAsync(
        ToughTongueBuildGhostRequest request,
        CancellationToken cancellationToken);
}

public interface IToughTongueBuildGhostTransport
{
    Task<ToughTongueBuildGhostTransportResult> ExplainAsync(
        ToughTongueBuildGhostTransportRequest request,
        string credential,
        CancellationToken cancellationToken);
}

public interface IBuildGhostClock
{
    DateTimeOffset UtcNow { get; }
}

public sealed class SystemBuildGhostClock : IBuildGhostClock
{
    public DateTimeOffset UtcNow => DateTimeOffset.UtcNow;
}

public sealed class ToughTongueBuildGhostAdapter : IToughTongueBuildGhostAdapter
{
    private const string RemoteEnabledKey = "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_REMOTE_EXECUTION_ENABLED";
    private const string ApiKeysKey = "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_API_KEYS";
    private const string AccountRefsKey = "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_ACCOUNT_REFS";
    private const string AgentIdKey = "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_AGENT_ID";
    private const string VoiceIdKey = "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_VOICE_ID";
    private const string DailyQuotaKey = "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_DAILY_QUOTA_PER_SLOT";
    private const string FailureThresholdKey = "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_CIRCUIT_FAILURE_THRESHOLD";
    private const string CooldownSecondsKey = "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_COOLDOWN_SECONDS";

    private static readonly JsonSerializerOptions ProviderSerializerOptions = new()
    {
        PropertyNameCaseInsensitive = true
    };

    private readonly IToughTongueBuildGhostTransport _transport;
    private readonly IBuildGhostClock _clock;
    private readonly bool _remoteEnabled;
    private readonly int _dailyQuota;
    private readonly int _failureThreshold;
    private readonly TimeSpan _cooldown;
    private readonly string _agentId;
    private readonly string _voiceId;
    private readonly CredentialSlotState[] _slots;
    private readonly Dictionary<string, ToughTongueBuildGhostResult> _idempotencyCache = new(StringComparer.Ordinal);
    private readonly SemaphoreSlim _gate = new(1, 1);
    private int _nextSlotIndex;

    public ToughTongueBuildGhostAdapter(
        IConfiguration configuration,
        IToughTongueBuildGhostTransport transport,
        IBuildGhostClock clock)
    {
        ArgumentNullException.ThrowIfNull(configuration);
        _transport = transport ?? throw new ArgumentNullException(nameof(transport));
        _clock = clock ?? throw new ArgumentNullException(nameof(clock));
        _remoteEnabled = ReadBoolean(configuration[RemoteEnabledKey], false);
        _dailyQuota = ReadBoundedInt(configuration[DailyQuotaKey], 100, 1, 100_000);
        _failureThreshold = ReadBoundedInt(configuration[FailureThresholdKey], 3, 1, 100);
        _cooldown = TimeSpan.FromSeconds(ReadBoundedInt(configuration[CooldownSecondsKey], 300, 1, 86_400));
        _agentId = NormalizeIdentifier(configuration[AgentIdKey]);
        _voiceId = NormalizeIdentifier(configuration[VoiceIdKey]);
        string[] credentials = SplitConfiguredList(configuration[ApiKeysKey]);
        string[] accountRefs = SplitConfiguredList(configuration[AccountRefsKey]);
        _slots = Enumerable.Range(0, 3).Select(index => new CredentialSlotState(
                index < accountRefs.Length ? accountRefs[index] : string.Empty,
                index < credentials.Length ? NormalizeSecret(credentials[index]) : null,
                _clock.UtcNow.UtcDateTime.Date))
            .ToArray();
    }

    public async Task<ToughTongueBuildGhostResult> ExplainAsync(
        ToughTongueBuildGhostRequest request,
        CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(request);
        cancellationToken.ThrowIfCancellationRequested();
        PacketAuthority authority = ValidateRequest(request);
        string cacheKey = $"{request.IdempotencyKey}\u001f{request.PacketDigest}";

        await _gate.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            if (_idempotencyCache.TryGetValue(cacheKey, out ToughTongueBuildGhostResult? cached))
            {
                return cached;
            }

            DateTimeOffset now = _clock.UtcNow;
            RefreshDailyQuota(now);
            if (!_remoteEnabled)
            {
                return Cache(cacheKey, Fallback(
                    request,
                    now,
                    "remote-disabled",
                    remoteAttempted: false,
                    slot: null,
                    ["remote-execution-disabled-by-default"]));
            }

            if (string.IsNullOrWhiteSpace(_agentId) || string.IsNullOrWhiteSpace(_voiceId))
            {
                return Cache(cacheKey, Fallback(
                    request,
                    now,
                    "provider-binding-unavailable",
                    remoteAttempted: false,
                    slot: null,
                    ["agent-or-voice-binding-missing"]));
            }

            CredentialSlotState? slot = SelectHealthySlot(now);
            if (slot is null)
            {
                return Cache(cacheKey, Fallback(
                    request,
                    now,
                    "no-healthy-credential-slot",
                    remoteAttempted: false,
                    slot: null,
                    ["all-configured-slots-missing-cooling-down-or-quota-exhausted"]));
            }

            slot.AttemptsToday++;
            ToughTongueBuildGhostTransportResult transportResult;
            try
            {
                transportResult = await _transport.ExplainAsync(
                    new ToughTongueBuildGhostTransportRequest(
                        ToughTongueBuildGhostContractVersions.RequestV1,
                        request.RequestId,
                        request.PacketDigest,
                        request.Locale,
                        request.AnalysisPacketJson,
                        request.IdempotencyKey),
                    slot.Credential!,
                    cancellationToken).ConfigureAwait(false);
            }
            catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
            {
                throw;
            }
            catch
            {
                MarkFailure(slot, now, quotaExhausted: false);
                return Cache(cacheKey, Fallback(
                    request,
                    now,
                    "transport-exception",
                    remoteAttempted: true,
                    slot,
                    ["provider-transport-exception-redacted"]));
            }

            if (!transportResult.Success || string.IsNullOrWhiteSpace(transportResult.ResponseJson))
            {
                MarkFailure(slot, now, transportResult.QuotaExhausted);
                return Cache(cacheKey, Fallback(
                    request,
                    now,
                    transportResult.QuotaExhausted ? "provider-quota-exhausted" : "provider-transport-failed",
                    remoteAttempted: true,
                    slot,
                    [NormalizeOutcomeCode(transportResult.OutcomeCode)],
                    transportResult));
            }

            ToughTongueBuildGhostProviderAnswer? answer;
            try
            {
                answer = JsonSerializer.Deserialize<ToughTongueBuildGhostProviderAnswer>(
                    transportResult.ResponseJson,
                    ProviderSerializerOptions);
            }
            catch (JsonException)
            {
                answer = null;
            }

            IReadOnlyList<string> validationReasons = ValidateProviderAnswer(request, authority, answer);
            if (validationReasons.Count > 0)
            {
                MarkFailure(slot, now, quotaExhausted: false);
                return Cache(cacheKey, Fallback(
                    request,
                    now,
                    "provider-answer-rejected",
                    remoteAttempted: true,
                    slot,
                    validationReasons,
                    transportResult));
            }

            slot.ConsecutiveFailures = 0;
            slot.CooldownUntilUtc = null;
            ToughTongueBuildGhostReceipt receipt = CreateReceipt(
                request,
                now,
                "validated-provider-answer",
                remoteAttempted: true,
                slot,
                [],
                transportResult);
            return Cache(cacheKey, new ToughTongueBuildGhostResult(
                "validated-provider-answer",
                answer!.Text,
                UsedDeterministicFallback: false,
                answer,
                receipt));
        }
        finally
        {
            _gate.Release();
        }
    }

    private PacketAuthority ValidateRequest(ToughTongueBuildGhostRequest request)
    {
        List<string> failures = [];
        Require(request.Schema, ToughTongueBuildGhostContractVersions.RequestV1, "request-schema-mismatch", failures);
        if (string.IsNullOrWhiteSpace(request.RequestId) || request.RequestId.Length > 128) failures.Add("request-id-invalid");
        if (!IsSha256(request.OwnerScopeHash)) failures.Add("owner-scope-hash-invalid");
        if (!IsSha256(request.PacketDigest)) failures.Add("packet-digest-invalid");
        if (string.IsNullOrWhiteSpace(request.IdempotencyKey) || request.IdempotencyKey.Length > 256) failures.Add("idempotency-key-invalid");
        if (string.IsNullOrWhiteSpace(request.DeterministicFallbackText) || request.DeterministicFallbackText.Length > 32_768) failures.Add("deterministic-fallback-invalid");
        if (string.IsNullOrWhiteSpace(request.AnalysisPacketJson) || request.AnalysisPacketJson.Length > 2 * 1024 * 1024) failures.Add("analysis-packet-size-invalid");
        JsonObject? packet = null;
        try
        {
            packet = JsonNode.Parse(request.AnalysisPacketJson) as JsonObject;
        }
        catch (JsonException)
        {
            failures.Add("analysis-packet-invalid-json");
        }

        if (packet is null)
        {
            failures.Add("analysis-packet-missing");
        }
        else
        {
            try
            {
                Require(Text(packet, "schema"), ToughTongueBuildGhostContractVersions.AnalysisV1, "analysis-schema-mismatch", failures);
                Require(Text(packet, "personaId"), ToughTongueBuildGhostPersonaIds.Rook, "persona-id-mismatch", failures);
                Require(Text(packet, "avatarId"), ToughTongueBuildGhostPersonaIds.RookAvatar, "avatar-id-mismatch", failures);
                Require(Text(packet, "voiceId"), ToughTongueBuildGhostPersonaIds.RookVoice, "voice-id-mismatch", failures);
                Require(Text(packet, "packetDigest"), request.PacketDigest, "packet-digest-binding-mismatch", failures);
                if (!string.Equals(Text(packet, "locale"), request.Locale, StringComparison.OrdinalIgnoreCase)) failures.Add("packet-locale-mismatch");
                string[] supportedLocales = Strings(packet, "supportedLocales").ToArray();
                string[] fallbackChain = Strings(packet, "localeFallbackChain").ToArray();
                if (!supportedLocales.Contains(request.Locale, StringComparer.OrdinalIgnoreCase)) failures.Add("locale-not-materialized");
                if (fallbackChain.Length == 0 || !string.Equals(fallbackChain[0], request.Locale, StringComparison.OrdinalIgnoreCase)) failures.Add("locale-fallback-chain-invalid");
                if (!string.Equals(ComputePacketDigest(packet), request.PacketDigest, StringComparison.Ordinal)) failures.Add("packet-digest-verification-failed");
            }
            catch (Exception exception) when (exception is InvalidOperationException or FormatException or ArgumentException)
            {
                failures.Add("analysis-packet-invalid-shape");
            }
        }

        if (failures.Count > 0)
        {
            throw new InvalidDataException(string.Join(";", failures.Distinct(StringComparer.Ordinal).OrderBy(static value => value, StringComparer.Ordinal)));
        }

        return PacketAuthority.Create(packet!);
    }

    private static IReadOnlyList<string> ValidateProviderAnswer(
        ToughTongueBuildGhostRequest request,
        PacketAuthority authority,
        ToughTongueBuildGhostProviderAnswer? answer)
    {
        List<string> failures = [];
        if (answer is null)
        {
            return ["provider-answer-invalid-json"];
        }

        Require(answer.Schema, ToughTongueBuildGhostContractVersions.ProviderAnswerV1, "provider-schema-mismatch", failures);
        Require(answer.RequestId, request.RequestId, "provider-request-id-mismatch", failures);
        Require(answer.PacketDigest, request.PacketDigest, "provider-packet-digest-mismatch", failures);
        if (!string.Equals(answer.Locale, request.Locale, StringComparison.OrdinalIgnoreCase)) failures.Add("provider-locale-mismatch");
        if (string.IsNullOrWhiteSpace(answer.Text)) failures.Add("provider-text-missing");
        AddUnknown(failures, "fact", answer.ReferencedFactIds, authority.FactIds);
        AddUnknown(failures, "strategy", answer.ReferencedStrategyIds, authority.StrategyIds);
        AddUnknown(failures, "rule-explanation", answer.ReferencedRuleExplanationIds, authority.RuleExplanationIds);
        AddUnknown(failures, "variant", answer.ReferencedVariantIds, authority.VariantIds);
        AddUnknown(failures, "member", answer.ReferencedMemberRefs, authority.MemberRefs);
        AddUnknown(failures, "source-anchor", answer.ReferencedSourceAnchorIds, authority.SourceAnchorIds);
        AddUnknown(failures, "action", answer.SuggestedActionIds, authority.ActionIds);
        AddUnknown(failures, "link", answer.Links, authority.Links);
        return failures.Distinct(StringComparer.Ordinal).OrderBy(static value => value, StringComparer.Ordinal).ToArray();
    }

    private ToughTongueBuildGhostResult Fallback(
        ToughTongueBuildGhostRequest request,
        DateTimeOffset now,
        string status,
        bool remoteAttempted,
        CredentialSlotState? slot,
        IReadOnlyList<string> reasons,
        ToughTongueBuildGhostTransportResult? transportResult = null)
        => new(
            status,
            request.DeterministicFallbackText,
            UsedDeterministicFallback: true,
            ProviderAnswer: null,
            CreateReceipt(request, now, status, remoteAttempted, slot, reasons, transportResult));

    private ToughTongueBuildGhostReceipt CreateReceipt(
        ToughTongueBuildGhostRequest request,
        DateTimeOffset now,
        string status,
        bool remoteAttempted,
        CredentialSlotState? slot,
        IReadOnlyList<string> reasons,
        ToughTongueBuildGhostTransportResult? transportResult = null)
    {
        DateTimeOffset completedAt = _clock.UtcNow;
        int configured = _slots.Count(static candidate => candidate.Credential is not null
            && !string.IsNullOrWhiteSpace(candidate.AccountRef));
        int healthy = _slots.Count(candidate => IsHealthy(candidate, now));
        return new ToughTongueBuildGhostReceipt(
            ToughTongueBuildGhostContractVersions.ReceiptV1,
            $"tough-tongue:{request.RequestId}:{Digest(request.PacketDigest + "\u001f" + request.IdempotencyKey)[..16]}",
            request.RequestId,
            request.PacketDigest,
            request.Locale,
            $"sha256:{Digest(request.IdempotencyKey)}",
            status,
            "tough-tongue",
            "not-applicable-session-orchestrator",
            _agentId,
            _voiceId,
            _remoteEnabled,
            remoteAttempted,
            slot?.AccountRef,
            slot is null ? "not-selected" : CircuitPosture(slot, now),
            configured,
            healthy,
            transportResult?.InputTokens,
            transportResult?.OutputTokens,
            transportResult?.MinutesUsed,
            status == "validated-provider-answer" ? null : status,
            reasons.Distinct(StringComparer.Ordinal).OrderBy(static value => value, StringComparer.Ordinal).ToArray(),
            now,
            completedAt,
            Math.Max(0, (long)(completedAt - now).TotalMilliseconds));
    }

    private CredentialSlotState? SelectHealthySlot(DateTimeOffset now)
    {
        for (int offset = 0; offset < _slots.Length; offset++)
        {
            int index = (_nextSlotIndex + offset) % _slots.Length;
            CredentialSlotState slot = _slots[index];
            if (!IsHealthy(slot, now))
            {
                continue;
            }

            _nextSlotIndex = (index + 1) % _slots.Length;
            return slot;
        }

        return null;
    }

    private bool IsHealthy(CredentialSlotState slot, DateTimeOffset now)
        => slot.Credential is not null
            && !string.IsNullOrWhiteSpace(slot.AccountRef)
            && slot.AttemptsToday < _dailyQuota
            && (slot.CooldownUntilUtc is null || slot.CooldownUntilUtc <= now);

    private void MarkFailure(CredentialSlotState slot, DateTimeOffset now, bool quotaExhausted)
    {
        if (quotaExhausted)
        {
            slot.AttemptsToday = _dailyQuota;
        }

        slot.ConsecutiveFailures++;
        if (slot.ConsecutiveFailures >= _failureThreshold || quotaExhausted)
        {
            slot.CooldownUntilUtc = now.Add(_cooldown);
        }
    }

    private void RefreshDailyQuota(DateTimeOffset now)
    {
        DateTime date = now.UtcDateTime.Date;
        foreach (CredentialSlotState slot in _slots)
        {
            if (slot.QuotaDate == date)
            {
                continue;
            }

            slot.QuotaDate = date;
            slot.AttemptsToday = 0;
        }
    }

    private string CircuitPosture(CredentialSlotState slot, DateTimeOffset now)
        => slot.CooldownUntilUtc > now ? "cooldown" : slot.AttemptsToday >= _dailyQuota ? "quota-exhausted" : "healthy";

    private ToughTongueBuildGhostResult Cache(string key, ToughTongueBuildGhostResult result)
    {
        _idempotencyCache[key] = result;
        return result;
    }

    private static void AddUnknown(List<string> failures, string kind, IEnumerable<string>? supplied, IReadOnlySet<string> allowed)
    {
        foreach (string value in supplied ?? [])
        {
            if (!string.IsNullOrWhiteSpace(value) && !allowed.Contains(value))
            {
                failures.Add($"unsupported-{kind}:{value}");
            }
        }
    }

    private static void Require(string? actual, string expected, string reason, List<string> failures)
    {
        if (!string.Equals(actual, expected, StringComparison.Ordinal)) failures.Add(reason);
    }

    private static string? NormalizeSecret(string? value)
        => string.IsNullOrWhiteSpace(value) ? null : value.Trim();

    private static string NormalizeIdentifier(string? value)
        => string.IsNullOrWhiteSpace(value) ? string.Empty : value.Trim();

    private static string[] SplitConfiguredList(string? value)
        => (value ?? string.Empty)
            .Split([',', ';', '\r', '\n'], StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
            .Where(static item => item.Length > 0)
            .Take(3)
            .ToArray();

    private static string NormalizeOutcomeCode(string? value)
    {
        if (string.IsNullOrWhiteSpace(value)) return "provider-transport-failed";
        string normalized = new(value.Trim().ToLowerInvariant().Select(character =>
            char.IsLetterOrDigit(character) || character is '-' or '_' ? character : '-').ToArray());
        return normalized.Length > 80 ? normalized[..80] : normalized;
    }

    private static bool ReadBoolean(string? value, bool fallback)
        => bool.TryParse(value, out bool parsed) ? parsed : fallback;

    private static int ReadBoundedInt(string? value, int fallback, int minimum, int maximum)
        => int.TryParse(value, out int parsed) && parsed >= minimum && parsed <= maximum ? parsed : fallback;

    private static string Digest(string value)
        => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(value))).ToLowerInvariant();

    private static bool IsSha256(string? value)
        => value is { Length: 71 }
            && value.StartsWith("sha256:", StringComparison.Ordinal)
            && value.Skip(7).All(Uri.IsHexDigit);

    private static string ComputePacketDigest(JsonObject packet)
    {
        JsonObject clone = (JsonObject)packet.DeepClone();
        string property = clone.Select(static pair => pair.Key)
            .FirstOrDefault(static key => string.Equals(key, "packetDigest", StringComparison.OrdinalIgnoreCase))
            ?? "packetDigest";
        clone[property] = string.Empty;
        using MemoryStream stream = new();
        using (Utf8JsonWriter writer = new(stream)) WriteCanonical(writer, clone);
        return $"sha256:{Convert.ToHexString(SHA256.HashData(stream.ToArray())).ToLowerInvariant()}";
    }

    private static void WriteCanonical(Utf8JsonWriter writer, JsonNode? node)
    {
        switch (node)
        {
            case null:
                writer.WriteNullValue();
                break;
            case JsonObject value:
                writer.WriteStartObject();
                foreach ((string key, JsonNode? child) in value.OrderBy(static pair => pair.Key, StringComparer.Ordinal))
                {
                    writer.WritePropertyName(key);
                    WriteCanonical(writer, child);
                }
                writer.WriteEndObject();
                break;
            case JsonArray value:
                writer.WriteStartArray();
                foreach (JsonNode? child in value) WriteCanonical(writer, child);
                writer.WriteEndArray();
                break;
            default:
                node.WriteTo(writer);
                break;
        }
    }

    private static JsonNode? Find(JsonObject? value, string property)
        => value?.FirstOrDefault(pair => string.Equals(pair.Key, property, StringComparison.OrdinalIgnoreCase)).Value;

    private static string Text(JsonObject? value, string property)
        => Find(value, property)?.GetValue<string>() ?? string.Empty;

    private static IEnumerable<JsonObject> Objects(JsonObject? value, string property)
        => (Find(value, property) as JsonArray ?? []).OfType<JsonObject>();

    private static IEnumerable<string> Strings(JsonObject? value, string property)
        => (Find(value, property) as JsonArray ?? [])
            .Select(static item => item?.GetValue<string>() ?? string.Empty)
            .Where(static item => item.Length > 0);

    private sealed class CredentialSlotState(string accountRef, string? credential, DateTime quotaDate)
    {
        public string AccountRef { get; } = accountRef;
        public string? Credential { get; } = credential;
        public DateTime QuotaDate { get; set; } = quotaDate;
        public int AttemptsToday { get; set; }
        public int ConsecutiveFailures { get; set; }
        public DateTimeOffset? CooldownUntilUtc { get; set; }
    }

    private sealed record PacketAuthority(
        IReadOnlySet<string> FactIds,
        IReadOnlySet<string> StrategyIds,
        IReadOnlySet<string> RuleExplanationIds,
        IReadOnlySet<string> VariantIds,
        IReadOnlySet<string> MemberRefs,
        IReadOnlySet<string> SourceAnchorIds,
        IReadOnlySet<string> ActionIds,
        IReadOnlySet<string> Links)
    {
        public static PacketAuthority Create(JsonObject packet)
            => new(
                Objects(Find(packet, "runner") as JsonObject, "facts").Select(static value => Text(value, "factId")).ToHashSet(StringComparer.Ordinal),
                Objects(packet, "optimizationStrategies").Select(static value => Text(value, "strategyId")).ToHashSet(StringComparer.Ordinal),
                Objects(packet, "ruleExplanations").Select(static value => Text(value, "explanationId")).ToHashSet(StringComparer.Ordinal),
                Objects(packet, "variants").Select(static value => Text(value, "variantId")).ToHashSet(StringComparer.Ordinal),
                Objects(Find(packet, "groupCapabilityPosture") as JsonObject, "visibleMembers").Select(static value => Text(value, "memberRef")).ToHashSet(StringComparer.Ordinal),
                Objects(packet, "sourceAnchors").Select(static value => Text(value, "anchorId")).ToHashSet(StringComparer.Ordinal),
                Objects(packet, "allowedSuggestedActions").Select(static value => Text(value, "actionId")).ToHashSet(StringComparer.Ordinal),
                Objects(packet, "ruleExplanations").Select(static value => Text(value, "sourceLookupRoute")).Where(static value => !string.IsNullOrWhiteSpace(value)).ToHashSet(StringComparer.Ordinal));
    }
}
