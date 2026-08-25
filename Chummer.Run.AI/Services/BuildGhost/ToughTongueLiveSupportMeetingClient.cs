using Chummer.Run.Contracts.BuildGhost;
using Microsoft.Extensions.Configuration;
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
    public const int MaximumResponseBytes = 256 * 1024;

    private static readonly Regex ProviderId = new(
        "^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
        RegexOptions.CultureInvariant | RegexOptions.NonBacktracking);
    private static readonly Regex ScenarioId = new(
        "^[a-f0-9]{24}$",
        RegexOptions.CultureInvariant | RegexOptions.NonBacktracking);

    private readonly HttpClient _httpClient;
    private readonly string _apiKey;
    private readonly string _scenarioId;
    private readonly string _botName;

    public ToughTongueLiveSupportMeetingClient(HttpClient httpClient, IConfiguration configuration)
    {
        _httpClient = httpClient ?? throw new ArgumentNullException(nameof(httpClient));
        ArgumentNullException.ThrowIfNull(configuration);
        _apiKey = NormalizeSecret(configuration[ApiKeyConfigurationKey]);
        _scenarioId = (configuration[ScenarioIdConfigurationKey] ?? string.Empty).Trim();
        _botName = NormalizeBotName(configuration[BotNameConfigurationKey]);
    }

    public IReadOnlyList<string> BlockingReasons
        => _httpClient.BaseAddress is null
            || !ToughTongueBuildGhostScenarioClient.IsOfficialApiBaseAddress(_httpClient.BaseAddress)
            || string.IsNullOrEmpty(_apiKey)
            || !ScenarioId.IsMatch(_scenarioId)
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
        if (_httpClient.BaseAddress is null
            || !ToughTongueBuildGhostScenarioClient.IsOfficialApiBaseAddress(_httpClient.BaseAddress)
            || string.IsNullOrEmpty(_apiKey)
            || !ScenarioId.IsMatch(_scenarioId)
            || !ProviderId.IsMatch(command.RequestId)
            || !ProviderId.IsMatch(command.IdempotencyKey)
            || command.MeetingProvider is not (BuildGhostLiveMeetingProviders.Zoom or BuildGhostLiveMeetingProviders.Teams)
            || !command.JoinUrl.IsAbsoluteUri
            || !IsSha256(command.AccountScopeRefDigest)
            || !IsSha256(command.ScenarioRefDigest)
            || !FixedTimeDigestEquals(command.ScenarioRefDigest, ScenarioRefDigest)
            || !string.Equals(
                command.AvatarAlias,
                ToughTongueBuildGhostPersonaIds.StockDefaultAvatar,
                StringComparison.Ordinal)
            || !IsSha256(command.AvatarBindingDigest))
        {
            return Failed("tough-tongue-meeting-bot-configuration-invalid");
        }

        JsonObject payload = new()
        {
            ["scenario_id"] = _scenarioId,
            ["meeting_url"] = command.JoinUrl.AbsoluteUri,
            ["meeting_provider"] = command.MeetingProvider,
            ["account_scope_ref_digest"] = command.AccountScopeRefDigest,
            ["scenario_ref_digest"] = command.ScenarioRefDigest,
            ["avatar_alias"] = command.AvatarAlias,
            ["avatar_binding_digest"] = command.AvatarBindingDigest,
            ["scheduled_ts"] = null,
            ["bot_name"] = _botName
        };
        using HttpRequestMessage request = new(HttpMethod.Post, "v2/meeting-bots")
        {
            Content = new StringContent(
                payload.ToJsonString(new JsonSerializerOptions { WriteIndented = false }),
                Encoding.UTF8,
                "application/json")
        };
        request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", _apiKey);
        request.Headers.Accept.Add(new MediaTypeWithQualityHeaderValue("application/json"));
        request.Headers.CacheControl = new CacheControlHeaderValue { NoStore = true };
        request.Headers.TryAddWithoutValidation("Idempotency-Key", command.IdempotencyKey);

        try
        {
            using HttpResponseMessage response = await _httpClient.SendAsync(
                request,
                HttpCompletionOption.ResponseHeadersRead,
                cancellationToken).ConfigureAwait(false);
            if (response.StatusCode != HttpStatusCode.OK)
            {
                return Failed(
                    $"tough-tongue-meeting-bot-http-{(int)response.StatusCode}",
                    reconciliationRequired: response.IsSuccessStatusCode
                        || (int)response.StatusCode >= 500);
            }

            byte[] body = await ReadBoundedAsync(response.Content, cancellationToken).ConfigureAwait(false);
            string responseDigest = Digest(body);
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
                return Failed(
                    "tough-tongue-meeting-bot-response-invalid",
                    responseDigest,
                    reconciliationRequired: true);
            }

            JsonElement bot = bots[0];
            string botId = ReadProviderId(bot, "bot_id");
            string sessionId = ReadProviderId(bot, "session_id");
            string lifecycleStatus = ReadProviderId(bot, "lifecycle_status");
            string accountScopeRefDigest = ReadDigest(bot, "account_scope_ref_digest");
            string scenarioRefDigest = ReadDigest(bot, "scenario_ref_digest");
            string avatarAlias = ReadProviderId(bot, "avatar_alias");
            string avatarBindingDigest = ReadDigest(bot, "avatar_binding_digest");
            if (string.IsNullOrEmpty(botId)
                || string.IsNullOrEmpty(sessionId)
                || !string.Equals(lifecycleStatus, "joined", StringComparison.Ordinal)
                || !FixedTimeDigestEquals(accountScopeRefDigest, command.AccountScopeRefDigest)
                || !FixedTimeDigestEquals(scenarioRefDigest, command.ScenarioRefDigest)
                || !string.Equals(avatarAlias, command.AvatarAlias, StringComparison.Ordinal)
                || !FixedTimeDigestEquals(avatarBindingDigest, command.AvatarBindingDigest))
            {
                return Failed(
                    string.Equals(lifecycleStatus, "joined", StringComparison.Ordinal)
                        ? "tough-tongue-meeting-bot-authority-binding-invalid"
                        : "tough-tongue-meeting-bot-not-joined",
                    responseDigest,
                    reconciliationRequired: true);
            }

            string botRefDigest = Digest(Encoding.UTF8.GetBytes(botId));
            string sessionRefDigest = Digest(Encoding.UTF8.GetBytes(sessionId));
            string joinReceiptDigest = Digest(Encoding.UTF8.GetBytes(string.Join(
                '\n',
                "chummer.build_ghost.live_support_join_receipt.v1",
                command.MeetingProvider,
                command.JoinUrl.AbsoluteUri,
                botRefDigest,
                sessionRefDigest,
                lifecycleStatus,
                accountScopeRefDigest,
                scenarioRefDigest,
                avatarAlias,
                avatarBindingDigest,
                responseDigest)));
            return new BuildGhostToughTongueMeetingBotResult(
                true,
                false,
                "joined",
                1,
                lifecycleStatus,
                accountScopeRefDigest,
                scenarioRefDigest,
                avatarAlias,
                avatarBindingDigest,
                botRefDigest,
                sessionRefDigest,
                responseDigest,
                joinReceiptDigest);
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            throw;
        }
        catch (Exception exception) when (exception is HttpRequestException or IOException or JsonException or InvalidOperationException)
        {
            return Failed(
                "tough-tongue-meeting-bot-transport-failed-redacted",
                reconciliationRequired: true);
        }
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

    private static string ReadDigest(JsonElement element, string property)
    {
        if (element.ValueKind != JsonValueKind.Object
            || !element.TryGetProperty(property, out JsonElement value)
            || value.ValueKind != JsonValueKind.String)
        {
            return string.Empty;
        }

        string candidate = value.GetString()?.Trim() ?? string.Empty;
        return IsSha256(candidate) ? candidate : string.Empty;
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
}
