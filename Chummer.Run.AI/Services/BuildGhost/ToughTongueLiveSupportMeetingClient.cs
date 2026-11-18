using Chummer.Run.Contracts.BuildGhost;
using Microsoft.Extensions.Configuration;
using System.Globalization;
using System.Net;
using System.Net.Http.Headers;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;

namespace Chummer.Run.AI.Services.BuildGhost;

public sealed class ToughTongueLiveSupportMeetingClient :
    IToughTongueLiveSupportMeetingClient,
    IToughTongueLiveSupportAuthorityBinding,
    IBuildGhostLiveSupportDependencyReadiness
{
    public const string ApiKeyConfigurationKey = "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_MEETING_BOT_API_KEY";
    public const string ScenarioIdConfigurationKey = "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_MEETING_BOT_SCENARIO_ID";
    public const string BotNameConfigurationKey = "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_MEETING_BOT_NAME";
    public const string PollAttemptsConfigurationKey = "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_MEETING_BOT_POLL_ATTEMPTS";
    public const string PollIntervalMillisecondsConfigurationKey = "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_MEETING_BOT_POLL_INTERVAL_MILLISECONDS";
    public const int MaximumResponseBytes = 256 * 1024;

    private const int DefaultPollAttempts = 12;
    private const int DefaultPollIntervalMilliseconds = 1000;
    private const int MaximumListedBots = 50;
    private static readonly Regex ProviderId = new(
        "^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
        RegexOptions.CultureInvariant | RegexOptions.NonBacktracking);
    private static readonly Regex ScenarioId = new(
        "^[a-f0-9]{24}$",
        RegexOptions.CultureInvariant | RegexOptions.NonBacktracking);
    private static readonly HashSet<string> KnownStatuses = new(StringComparer.Ordinal)
    {
        "pending",
        "scheduled",
        "in_call_recording",
        "call_ended",
        "done",
        "failed"
    };

    private readonly HttpClient _httpClient;
    private readonly string _apiKey;
    private readonly string _scenarioId;
    private readonly string _botName;
    private readonly string _accountScopeRefDigest;
    private readonly string _avatarBindingDigest;
    private readonly int _pollAttempts;
    private readonly int _pollIntervalMilliseconds;

    public ToughTongueLiveSupportMeetingClient(HttpClient httpClient, IConfiguration configuration)
    {
        _httpClient = httpClient ?? throw new ArgumentNullException(nameof(httpClient));
        ArgumentNullException.ThrowIfNull(configuration);
        _apiKey = NormalizeSecret(configuration[ApiKeyConfigurationKey]);
        _scenarioId = (configuration[ScenarioIdConfigurationKey] ?? string.Empty).Trim();
        _botName = NormalizeBotName(configuration[BotNameConfigurationKey]);
        _accountScopeRefDigest = (configuration[BuildGhostLiveSupportService.ExpectedAccountScopeDigestKey] ?? string.Empty).Trim();
        _avatarBindingDigest = (configuration[BuildGhostLiveSupportService.ExpectedAvatarBindingDigestKey] ?? string.Empty).Trim();
        _pollAttempts = ParseBoundedInt(
            configuration[PollAttemptsConfigurationKey],
            DefaultPollAttempts,
            minimum: 1,
            maximum: 30);
        _pollIntervalMilliseconds = ParseBoundedInt(
            configuration[PollIntervalMillisecondsConfigurationKey],
            DefaultPollIntervalMilliseconds,
            minimum: 1,
            maximum: 5000);
    }

    public IReadOnlyList<string> BlockingReasons
        => _httpClient.BaseAddress is null
            || !ToughTongueBuildGhostScenarioClient.IsOfficialApiBaseAddress(_httpClient.BaseAddress)
            || string.IsNullOrEmpty(_apiKey)
            || !ScenarioId.IsMatch(_scenarioId)
            || !IsSha256(_accountScopeRefDigest)
            || !IsSha256(_avatarBindingDigest)
            ? ["tough-tongue-meeting-bot-configuration-invalid"]
            : [];

    public string ScenarioRefDigest
        => ScenarioId.IsMatch(_scenarioId)
            ? Digest(Encoding.UTF8.GetBytes(_scenarioId))
            : string.Empty;

    public async Task<BuildGhostToughTongueMeetingBotResult> ScheduleAsync(
        BuildGhostToughTongueMeetingBotCommand command,
        CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(command);
        cancellationToken.ThrowIfCancellationRequested();
        if (BlockingReasons.Count != 0
            || !ProviderId.IsMatch(command.RequestId)
            || !ProviderId.IsMatch(command.IdempotencyKey)
            || command.MeetingProvider is not (BuildGhostLiveMeetingProviders.Zoom or BuildGhostLiveMeetingProviders.Teams)
            || !IsAllowedJoinUrl(command.JoinUrl, command.MeetingProvider)
            || !FixedTimeDigestEquals(command.AccountScopeRefDigest, _accountScopeRefDigest)
            || !FixedTimeDigestEquals(command.ScenarioRefDigest, ScenarioRefDigest)
            || !string.Equals(
                command.AvatarAlias,
                ToughTongueBuildGhostPersonaIds.StockDefaultAvatar,
                StringComparison.Ordinal)
            || !FixedTimeDigestEquals(command.AvatarBindingDigest, _avatarBindingDigest))
        {
            return Failed("tough-tongue-meeting-bot-configuration-invalid");
        }

        List<string> responseDigests = [];
        bool botMayExist = false;
        try
        {
            ProviderListResult initial = await ListAsync(cancellationToken).ConfigureAwait(false);
            AddDigest(responseDigests, initial.ResponseDigest);
            if (!initial.Success)
            {
                return Failed(initial.OutcomeCode, TranscriptDigest(responseDigests), reconciliationRequired: true);
            }

            IReadOnlyList<ListedBot> matchingLink = initial.Bots
                .Where(bot => UrlEquals(bot.MeetingUrl, command.JoinUrl))
                .ToArray();
            if (matchingLink.Count > 1)
            {
                return Failed(
                    "tough-tongue-meeting-bot-reconciliation-ambiguous",
                    TranscriptDigest(responseDigests),
                    reconciliationRequired: true);
            }

            ScheduledBotIdentity? identity = null;
            if (matchingLink.Count == 1)
            {
                ListedBot existing = matchingLink[0];
                botMayExist = true;
                if (!HasExpectedAuthority(existing, command))
                {
                    return Failed(
                        "tough-tongue-meeting-bot-authority-binding-invalid",
                        TranscriptDigest(responseDigests),
                        reconciliationRequired: true);
                }
                identity = new ScheduledBotIdentity(existing.Id, existing.SessionId);
                BuildGhostToughTongueMeetingBotResult? immediate = EvaluateBot(existing, command, responseDigests);
                if (immediate is not null)
                {
                    return immediate;
                }
            }

            if (identity is null)
            {
                // A transport failure after this point is ambiguous: the provider
                // may have accepted the scheduling request before the failure.
                botMayExist = true;
                ProviderScheduleResult scheduled = await PostScheduleAsync(command, cancellationToken).ConfigureAwait(false);
                AddDigest(responseDigests, scheduled.ResponseDigest);
                if (!scheduled.Success || scheduled.Identity is null)
                {
                    return Failed(
                        scheduled.OutcomeCode,
                        TranscriptDigest(responseDigests),
                        scheduled.ReconciliationRequired);
                }

                identity = scheduled.Identity;
                botMayExist = true;
            }

            for (int attempt = 0; attempt < _pollAttempts; attempt++)
            {
                if (attempt > 0)
                {
                    await Task.Delay(_pollIntervalMilliseconds, cancellationToken).ConfigureAwait(false);
                }

                ProviderListResult poll = await ListAsync(cancellationToken).ConfigureAwait(false);
                AddDigest(responseDigests, poll.ResponseDigest);
                if (!poll.Success)
                {
                    return Failed(
                        poll.OutcomeCode,
                        TranscriptDigest(responseDigests),
                        reconciliationRequired: true);
                }

                ListedBot[] linkMatches = poll.Bots
                    .Where(bot => UrlEquals(bot.MeetingUrl, command.JoinUrl))
                    .ToArray();
                if (linkMatches.Length > 1)
                {
                    return Failed(
                        "tough-tongue-meeting-bot-reconciliation-ambiguous",
                        TranscriptDigest(responseDigests),
                        reconciliationRequired: true);
                }
                if (linkMatches.Length == 1
                    && (!string.Equals(linkMatches[0].Id, identity.BotId, StringComparison.Ordinal)
                        || !string.Equals(linkMatches[0].SessionId, identity.SessionId, StringComparison.Ordinal)))
                {
                    return Failed(
                        "tough-tongue-meeting-bot-authority-binding-invalid",
                        TranscriptDigest(responseDigests),
                        reconciliationRequired: true);
                }

                ListedBot[] identityMatches = poll.Bots
                    .Where(bot => string.Equals(bot.Id, identity.BotId, StringComparison.Ordinal)
                        || string.Equals(bot.SessionId, identity.SessionId, StringComparison.Ordinal))
                    .ToArray();
                if (identityMatches.Length > 1)
                {
                    return Failed(
                        "tough-tongue-meeting-bot-reconciliation-ambiguous",
                        TranscriptDigest(responseDigests),
                        reconciliationRequired: true);
                }
                if (identityMatches.Length == 0)
                {
                    continue;
                }

                ListedBot target = identityMatches[0];
                if (!string.Equals(target.Id, identity.BotId, StringComparison.Ordinal)
                    || !string.Equals(target.SessionId, identity.SessionId, StringComparison.Ordinal)
                    || !HasExpectedAuthority(target, command))
                {
                    return Failed(
                        "tough-tongue-meeting-bot-authority-binding-invalid",
                        TranscriptDigest(responseDigests),
                        reconciliationRequired: true);
                }

                BuildGhostToughTongueMeetingBotResult? evaluated = EvaluateBot(target, command, responseDigests);
                if (evaluated is not null)
                {
                    return evaluated;
                }
            }

            return Failed(
                "tough-tongue-meeting-bot-join-timeout",
                TranscriptDigest(responseDigests),
                reconciliationRequired: true);
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            throw;
        }
        catch (Exception exception) when (exception is HttpRequestException
            or IOException
            or JsonException
            or InvalidOperationException
            or OperationCanceledException)
        {
            return Failed(
                "tough-tongue-meeting-bot-transport-failed-redacted",
                TranscriptDigest(responseDigests),
                reconciliationRequired: botMayExist);
        }
    }

    private async Task<ProviderScheduleResult> PostScheduleAsync(
        BuildGhostToughTongueMeetingBotCommand command,
        CancellationToken cancellationToken)
    {
        JsonObject payload = new()
        {
            ["scenario_id"] = _scenarioId,
            ["meeting_url"] = command.JoinUrl.AbsoluteUri,
            ["meeting_provider"] = command.MeetingProvider,
            ["bot_name"] = _botName
        };
        using HttpRequestMessage request = CreateRequest(HttpMethod.Post, "v2/meeting-bots");
        request.Headers.TryAddWithoutValidation("Idempotency-Key", command.IdempotencyKey);
        request.Content = new StringContent(
            payload.ToJsonString(new JsonSerializerOptions { WriteIndented = false }),
            Encoding.UTF8,
            "application/json");

        using HttpResponseMessage response = await _httpClient.SendAsync(
            request,
            HttpCompletionOption.ResponseHeadersRead,
            cancellationToken).ConfigureAwait(false);
        byte[] body = await ReadBoundedAsync(response.Content, cancellationToken).ConfigureAwait(false);
        string responseDigest = Digest(body);
        if (response.StatusCode != HttpStatusCode.OK)
        {
            return new ProviderScheduleResult(
                false,
                null,
                $"tough-tongue-meeting-bot-http-{(int)response.StatusCode}",
                responseDigest,
                response.IsSuccessStatusCode
                    || response.StatusCode == HttpStatusCode.Conflict
                    || (int)response.StatusCode >= 500);
        }

        using JsonDocument document = JsonDocument.Parse(body, new JsonDocumentOptions
        {
            AllowTrailingCommas = false,
            CommentHandling = JsonCommentHandling.Disallow
        });
        JsonElement root = document.RootElement;
        if (root.ValueKind != JsonValueKind.Object
            || !root.TryGetProperty("success", out JsonElement success)
            || success.ValueKind is not JsonValueKind.True
            || !root.TryGetProperty("bots", out JsonElement bots)
            || bots.ValueKind != JsonValueKind.Array
            || bots.GetArrayLength() != 1)
        {
            return new ProviderScheduleResult(
                false,
                null,
                "tough-tongue-meeting-bot-response-invalid",
                responseDigest,
                true);
        }

        JsonElement bot = bots[0];
        string botId = ReadProviderId(bot, "bot_id");
        string sessionId = ReadProviderId(bot, "session_id");
        return string.IsNullOrEmpty(botId) || string.IsNullOrEmpty(sessionId)
            ? new ProviderScheduleResult(
                false,
                null,
                "tough-tongue-meeting-bot-response-invalid",
                responseDigest,
                true)
            : new ProviderScheduleResult(
                true,
                new ScheduledBotIdentity(botId, sessionId),
                "scheduled",
                responseDigest,
                false);
    }

    private async Task<ProviderListResult> ListAsync(CancellationToken cancellationToken)
    {
        string path = string.Concat(
            "v2/meeting-bots?scenario_id=",
            Uri.EscapeDataString(_scenarioId),
            "&page=1&limit=",
            MaximumListedBots.ToString(CultureInfo.InvariantCulture));
        using HttpRequestMessage request = CreateRequest(HttpMethod.Get, path);
        using HttpResponseMessage response = await _httpClient.SendAsync(
            request,
            HttpCompletionOption.ResponseHeadersRead,
            cancellationToken).ConfigureAwait(false);
        byte[] body = await ReadBoundedAsync(response.Content, cancellationToken).ConfigureAwait(false);
        string responseDigest = Digest(body);
        if (response.StatusCode != HttpStatusCode.OK)
        {
            return new ProviderListResult(
                false,
                [],
                $"tough-tongue-meeting-bot-list-http-{(int)response.StatusCode}",
                responseDigest);
        }

        using JsonDocument document = JsonDocument.Parse(body, new JsonDocumentOptions
        {
            AllowTrailingCommas = false,
            CommentHandling = JsonCommentHandling.Disallow
        });
        JsonElement root = document.RootElement;
        if (root.ValueKind != JsonValueKind.Object
            || (root.TryGetProperty("success", out JsonElement success)
                && success.ValueKind is not JsonValueKind.True)
            || !root.TryGetProperty("bots", out JsonElement bots)
            || bots.ValueKind != JsonValueKind.Array
            || HasAdditionalOrInvalidPages(root, bots.GetArrayLength()))
        {
            return new ProviderListResult(
                false,
                [],
                "tough-tongue-meeting-bot-list-response-invalid",
                responseDigest);
        }

        List<ListedBot> listed = [];
        foreach (JsonElement element in bots.EnumerateArray())
        {
            string id = ReadProviderId(element, "id");
            string sessionId = ReadProviderId(element, "session_id");
            string status = ReadProviderId(element, "status");
            string scenarioId = ReadProviderId(element, "scenario_id");
            string provider = ReadProviderId(element, "meeting_provider");
            string botName = ReadBotName(element);
            DateTimeOffset? joinedAt = ReadTimestamp(element, "bot_joined_at");
            if (string.IsNullOrEmpty(id)
                || string.IsNullOrEmpty(sessionId)
                || !KnownStatuses.Contains(status)
                || !ScenarioId.IsMatch(scenarioId)
                || provider is not ("google-meet" or BuildGhostLiveMeetingProviders.Zoom or BuildGhostLiveMeetingProviders.Teams)
                || string.IsNullOrEmpty(botName)
                || !ReadMeetingUrl(element, out Uri? meetingUrl))
            {
                return new ProviderListResult(
                    false,
                    [],
                    "tough-tongue-meeting-bot-list-response-invalid",
                    responseDigest);
            }

            listed.Add(new ListedBot(
                id,
                sessionId,
                status,
                scenarioId,
                meetingUrl!,
                provider,
                botName,
                joinedAt));
        }

        return new ProviderListResult(true, listed, "listed", responseDigest);
    }

    private BuildGhostToughTongueMeetingBotResult? EvaluateBot(
        ListedBot bot,
        BuildGhostToughTongueMeetingBotCommand command,
        IReadOnlyList<string> responseDigests)
    {
        string transcriptDigest = TranscriptDigest(responseDigests);
        if (string.Equals(bot.Status, "failed", StringComparison.Ordinal))
        {
            return Failed("tough-tongue-meeting-bot-failed", transcriptDigest);
        }
        if (bot.Status is "call_ended" or "done")
        {
            return Failed("tough-tongue-meeting-bot-call-ended-before-ready", transcriptDigest);
        }
        if (!string.Equals(bot.Status, "in_call_recording", StringComparison.Ordinal)
            || bot.JoinedAtUtc is null)
        {
            return null;
        }

        string botRefDigest = Digest(Encoding.UTF8.GetBytes(bot.Id));
        string sessionRefDigest = Digest(Encoding.UTF8.GetBytes(bot.SessionId));
        string joinReceiptDigest = Digest(Encoding.UTF8.GetBytes(string.Join(
            '\n',
            "chummer.build_ghost.live_support_join_receipt.v1",
            command.MeetingProvider,
            command.JoinUrl.AbsoluteUri,
            botRefDigest,
            sessionRefDigest,
            bot.Status,
            _accountScopeRefDigest,
            command.ScenarioRefDigest,
            command.AvatarAlias,
            _avatarBindingDigest,
            transcriptDigest)));
        return new BuildGhostToughTongueMeetingBotResult(
            true,
            false,
            "joined",
            1,
            bot.Status,
            _accountScopeRefDigest,
            command.ScenarioRefDigest,
            command.AvatarAlias,
            _avatarBindingDigest,
            botRefDigest,
            sessionRefDigest,
            transcriptDigest,
            joinReceiptDigest);
    }

    private bool HasExpectedAuthority(ListedBot bot, BuildGhostToughTongueMeetingBotCommand command)
        => string.Equals(bot.ScenarioId, _scenarioId, StringComparison.Ordinal)
            && string.Equals(bot.MeetingProvider, command.MeetingProvider, StringComparison.Ordinal)
            && UrlEquals(bot.MeetingUrl, command.JoinUrl)
            && string.Equals(bot.BotName, _botName, StringComparison.Ordinal);

    private HttpRequestMessage CreateRequest(HttpMethod method, string path)
    {
        HttpRequestMessage request = new(method, path);
        request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", _apiKey);
        request.Headers.Accept.Add(new MediaTypeWithQualityHeaderValue("application/json"));
        request.Headers.CacheControl = new CacheControlHeaderValue { NoStore = true };
        return request;
    }

    private static bool ReadMeetingUrl(JsonElement element, out Uri? uri)
    {
        uri = null;
        return element.ValueKind == JsonValueKind.Object
            && element.TryGetProperty("meeting_url", out JsonElement value)
            && value.ValueKind == JsonValueKind.String
            && Uri.TryCreate(value.GetString(), UriKind.Absolute, out uri)
            && uri is not null
            && string.Equals(uri.Scheme, Uri.UriSchemeHttps, StringComparison.OrdinalIgnoreCase)
            && string.IsNullOrEmpty(uri.UserInfo)
            && string.IsNullOrEmpty(uri.Fragment)
            && uri.IsDefaultPort;
    }

    private static DateTimeOffset? ReadTimestamp(JsonElement element, string property)
    {
        if (element.ValueKind != JsonValueKind.Object
            || !element.TryGetProperty(property, out JsonElement value)
            || value.ValueKind == JsonValueKind.Null)
        {
            return null;
        }

        return value.ValueKind == JsonValueKind.String
            && DateTimeOffset.TryParse(
                value.GetString(),
                CultureInfo.InvariantCulture,
                DateTimeStyles.AssumeUniversal | DateTimeStyles.AdjustToUniversal,
                out DateTimeOffset timestamp)
            ? timestamp
            : null;
    }

    private static string ReadBotName(JsonElement element)
    {
        if (element.ValueKind != JsonValueKind.Object
            || !element.TryGetProperty("bot_name", out JsonElement value)
            || value.ValueKind != JsonValueKind.String)
        {
            return string.Empty;
        }

        string candidate = value.GetString()?.Trim() ?? string.Empty;
        return candidate.Length is > 0 and <= 80 && candidate.All(character => !char.IsControl(character))
            ? candidate
            : string.Empty;
    }

    private static bool HasAdditionalOrInvalidPages(JsonElement root, int botCount)
    {
        bool paginationObserved = false;
        if (root.TryGetProperty("page_meta", out JsonElement pageMeta))
        {
            if (pageMeta.ValueKind != JsonValueKind.Object)
            {
                return true;
            }
            paginationObserved = true;
            if (pageMeta.TryGetProperty("total_pages", out JsonElement totalPages)
                && (!totalPages.TryGetInt32(out int parsedTotalPages)
                    || parsedTotalPages < 0
                    || parsedTotalPages > 1))
            {
                return true;
            }
            if (pageMeta.TryGetProperty("has_next", out JsonElement nestedHasNext)
                && (nestedHasNext.ValueKind is not (JsonValueKind.True or JsonValueKind.False)
                    || nestedHasNext.ValueKind == JsonValueKind.True))
            {
                return true;
            }
        }

        if (root.TryGetProperty("has_next", out JsonElement hasNext))
        {
            paginationObserved = true;
            if (hasNext.ValueKind is not (JsonValueKind.True or JsonValueKind.False)
                || hasNext.ValueKind == JsonValueKind.True)
            {
                return true;
            }
        }

        // Without pagination metadata, a full page cannot prove that another
        // matching bot is not hidden on the next page.
        return !paginationObserved && botCount >= MaximumListedBots;
    }

    private static async Task<byte[]> ReadBoundedAsync(HttpContent content, CancellationToken cancellationToken)
    {
        await using Stream stream = await content.ReadAsStreamAsync(cancellationToken).ConfigureAwait(false);
        using MemoryStream buffer = new();
        byte[] chunk = new byte[16 * 1024];
        int total = 0;
        while (true)
        {
            int read = await stream.ReadAsync(chunk.AsMemory(0, chunk.Length), cancellationToken).ConfigureAwait(false);
            if (read == 0)
            {
                return buffer.ToArray();
            }

            total += read;
            if (total > MaximumResponseBytes)
            {
                throw new IOException("provider-response-too-large");
            }
            buffer.Write(chunk, 0, read);
        }
    }

    private static string ReadProviderId(JsonElement element, string property)
    {
        if (element.ValueKind != JsonValueKind.Object
            || !element.TryGetProperty(property, out JsonElement value)
            || value.ValueKind != JsonValueKind.String)
        {
            return string.Empty;
        }

        string candidate = value.GetString()?.Trim() ?? string.Empty;
        return ProviderId.IsMatch(candidate) ? candidate : string.Empty;
    }

    private static string NormalizeSecret(string? value)
    {
        string candidate = value?.Trim() ?? string.Empty;
        return candidate.Length is >= 16 and <= 4096
            && candidate.IndexOfAny(['\r', '\n', '\0']) < 0
            ? candidate
            : string.Empty;
    }

    private static string NormalizeBotName(string? value)
    {
        string candidate = string.IsNullOrWhiteSpace(value) ? "Chummer Live Support" : value.Trim();
        return candidate.Length <= 80 && candidate.All(character => !char.IsControl(character))
            ? candidate
            : "Chummer Live Support";
    }

    private static int ParseBoundedInt(string? value, int fallback, int minimum, int maximum)
        => int.TryParse(value, NumberStyles.None, CultureInfo.InvariantCulture, out int parsed)
            && parsed >= minimum
            && parsed <= maximum
            ? parsed
            : fallback;

    private static bool IsAllowedJoinUrl(Uri? uri, string provider)
    {
        if (uri is null
            || !uri.IsAbsoluteUri
            || !string.Equals(uri.Scheme, Uri.UriSchemeHttps, StringComparison.OrdinalIgnoreCase)
            || !string.IsNullOrEmpty(uri.UserInfo)
            || !string.IsNullOrEmpty(uri.Fragment)
            || !uri.IsDefaultPort)
        {
            return false;
        }

        string host = uri.IdnHost.TrimEnd('.').ToLowerInvariant();
        if (provider == BuildGhostLiveMeetingProviders.Zoom)
        {
            return host == "zoom.us" || host.EndsWith(".zoom.us", StringComparison.Ordinal);
        }

        return provider == BuildGhostLiveMeetingProviders.Teams
            && (host == "teams.microsoft.com" || host == "teams.live.com")
            && (uri.AbsolutePath.StartsWith("/l/meetup-join/", StringComparison.OrdinalIgnoreCase)
                || uri.AbsolutePath.StartsWith("/meet/", StringComparison.OrdinalIgnoreCase));
    }

    private static bool UrlEquals(Uri left, Uri right)
        => string.Equals(left.AbsoluteUri, right.AbsoluteUri, StringComparison.Ordinal);

    private static void AddDigest(ICollection<string> responseDigests, string digest)
    {
        if (IsSha256(digest))
        {
            responseDigests.Add(digest);
        }
    }

    private static string TranscriptDigest(IEnumerable<string> responseDigests)
    {
        string transcript = string.Join('\n', responseDigests);
        return string.IsNullOrEmpty(transcript)
            ? string.Empty
            : Digest(Encoding.ASCII.GetBytes(transcript));
    }

    private static BuildGhostToughTongueMeetingBotResult Failed(
        string reason,
        string responseDigest = "",
        bool reconciliationRequired = false)
        => new(
            false,
            reconciliationRequired,
            reason,
            0,
            string.Empty,
            string.Empty,
            string.Empty,
            string.Empty,
            string.Empty,
            string.Empty,
            string.Empty,
            responseDigest,
            string.Empty);

    private static bool IsSha256(string? value)
        => value is { Length: 71 }
            && value.StartsWith("sha256:", StringComparison.Ordinal)
            && value.AsSpan(7).IndexOfAnyExcept("0123456789abcdef") < 0;

    private static bool FixedTimeDigestEquals(string? left, string? right)
        => IsSha256(left)
            && IsSha256(right)
            && CryptographicOperations.FixedTimeEquals(
                Encoding.ASCII.GetBytes(left!),
                Encoding.ASCII.GetBytes(right!));

    private static string Digest(ReadOnlySpan<byte> value)
        => $"sha256:{Convert.ToHexString(SHA256.HashData(value)).ToLowerInvariant()}";

    private sealed record ScheduledBotIdentity(string BotId, string SessionId);

    private sealed record ListedBot(
        string Id,
        string SessionId,
        string Status,
        string ScenarioId,
        Uri MeetingUrl,
        string MeetingProvider,
        string BotName,
        DateTimeOffset? JoinedAtUtc);

    private sealed record ProviderScheduleResult(
        bool Success,
        ScheduledBotIdentity? Identity,
        string OutcomeCode,
        string ResponseDigest,
        bool ReconciliationRequired);

    private sealed record ProviderListResult(
        bool Success,
        IReadOnlyList<ListedBot> Bots,
        string OutcomeCode,
        string ResponseDigest);
}
