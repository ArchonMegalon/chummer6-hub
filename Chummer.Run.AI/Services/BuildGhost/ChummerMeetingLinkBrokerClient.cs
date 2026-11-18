using Chummer.Run.Contracts.BuildGhost;
using Microsoft.Extensions.Configuration;
using System.Net;
using System.Net.Http.Headers;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Text.RegularExpressions;

namespace Chummer.Run.AI.Services.BuildGhost;

public sealed class ChummerMeetingLinkBrokerClient : IBuildGhostMeetingLinkBroker, IBuildGhostLiveSupportDependencyReadiness
{
    public const string BaseUrlConfigurationKey = "CHUMMER_BUILD_GHOST_MEETING_BROKER_BASE_URL";
    public const string ApiTokenConfigurationKey = "CHUMMER_BUILD_GHOST_MEETING_BROKER_API_TOKEN";
    public const int MaximumResponseBytes = 256 * 1024;

    private static readonly Regex SafeIdentifier = new(
        "^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
        RegexOptions.CultureInvariant | RegexOptions.NonBacktracking);
    private static readonly JsonSerializerOptions StrictJson = new(JsonSerializerDefaults.Web)
    {
        PropertyNameCaseInsensitive = false,
        UnmappedMemberHandling = JsonUnmappedMemberHandling.Disallow
    };

    private readonly HttpClient _httpClient;
    private readonly string _token;

    public ChummerMeetingLinkBrokerClient(HttpClient httpClient, IConfiguration configuration)
    {
        _httpClient = httpClient ?? throw new ArgumentNullException(nameof(httpClient));
        ArgumentNullException.ThrowIfNull(configuration);
        _token = NormalizeToken(configuration[ApiTokenConfigurationKey]);
    }

    public IReadOnlyList<string> BlockingReasons
        => _httpClient.BaseAddress is null
            || !IsAllowedBrokerBaseAddress(_httpClient.BaseAddress)
            || string.IsNullOrEmpty(_token)
            ? ["meeting-link-broker-configuration-invalid"]
            : [];

    public async Task<BuildGhostMeetingLinkProvisioningResult> CreateAsync(
        BuildGhostMeetingLinkProvisioningCommand command,
        CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(command);
        cancellationToken.ThrowIfCancellationRequested();
        if (BlockingReasons.Count != 0
            || !IsValidCommand(command))
        {
            return Failed(command.MeetingProvider, "meeting-link-broker-configuration-or-command-invalid");
        }

        BrokerCreateRequest payload = new(
            "chummer.meeting_link_broker.create_request.v1",
            command.RequestId,
            command.OwnerScopeHash,
            command.MeetingProvider,
            command.Locale,
            command.DurationMinutes,
            command.IdempotencyKey);
        using HttpRequestMessage request = CreateRequest(HttpMethod.Post, "api/v1/meetings", command.IdempotencyKey);
        request.Content = new StringContent(
            JsonSerializer.Serialize(payload, StrictJson),
            Encoding.UTF8,
            "application/json");

        try
        {
            using HttpResponseMessage response = await _httpClient.SendAsync(
                request,
                HttpCompletionOption.ResponseHeadersRead,
                cancellationToken).ConfigureAwait(false);
            byte[] body = await ReadBoundedAsync(response.Content, cancellationToken).ConfigureAwait(false);
            string responseDigest = Digest(body);
            if (response.StatusCode is not (HttpStatusCode.OK or HttpStatusCode.Created))
            {
                return Failed(
                    command.MeetingProvider,
                    $"meeting-link-broker-http-{(int)response.StatusCode}",
                    responseDigest,
                    reconciliationRequired: response.IsSuccessStatusCode
                        || (int)response.StatusCode >= 500);
            }

            BrokerCreateResponse? result = JsonSerializer.Deserialize<BrokerCreateResponse>(body, StrictJson);
            if (result is null
                || !result.Success
                || !SafeIdentifier.IsMatch(result.MeetingId ?? string.Empty)
                || !SafeIdentifier.IsMatch(result.CancellationHandle ?? string.Empty)
                || !Uri.TryCreate(result.JoinUrl, UriKind.Absolute, out Uri? joinUrl))
            {
                return Failed(
                    command.MeetingProvider,
                    "meeting-link-broker-response-invalid",
                    responseDigest,
                    reconciliationRequired: true);
            }

            string meetingId = result.MeetingId!;
            string cancellationHandle = result.CancellationHandle!;

            return new BuildGhostMeetingLinkProvisioningResult(
                true,
                false,
                "created",
                result.MeetingProvider,
                joinUrl,
                cancellationHandle,
                Digest(Encoding.UTF8.GetBytes(meetingId)),
                responseDigest,
                result.StartsAtUtc,
                result.ExpiresAtUtc);
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            throw;
        }
        catch (Exception exception) when (exception is HttpRequestException
            or IOException
            or JsonException
            or InvalidOperationException)
        {
            return Failed(
                command.MeetingProvider,
                "meeting-link-broker-transport-failed-redacted",
                reconciliationRequired: true);
        }
    }

    public async Task<BuildGhostMeetingLinkCancellationResult> CancelAsync(
        BuildGhostMeetingLinkCancellationCommand command,
        CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(command);
        cancellationToken.ThrowIfCancellationRequested();
        if (BlockingReasons.Count != 0
            || !SafeIdentifier.IsMatch(command.RequestId ?? string.Empty)
            || !SafeIdentifier.IsMatch(command.CancellationHandle ?? string.Empty)
            || !SafeIdentifier.IsMatch(command.IdempotencyKey ?? string.Empty))
        {
            return new BuildGhostMeetingLinkCancellationResult(false, "meeting-link-cancellation-command-invalid", string.Empty);
        }

        string requestId = command.RequestId!;
        string cancellationHandle = command.CancellationHandle!;
        string idempotencyKey = command.IdempotencyKey!;

        using HttpRequestMessage request = CreateRequest(
            HttpMethod.Post,
            $"api/v1/meetings/{Uri.EscapeDataString(cancellationHandle)}/cancel",
            idempotencyKey);
        request.Content = new StringContent(
            JsonSerializer.Serialize(
                new BrokerCancelRequest(
                    "chummer.meeting_link_broker.cancel_request.v1",
                    requestId,
                    command.MeetingProvider,
                    idempotencyKey),
                StrictJson),
            Encoding.UTF8,
            "application/json");
        try
        {
            using HttpResponseMessage response = await _httpClient.SendAsync(
                request,
                HttpCompletionOption.ResponseHeadersRead,
                cancellationToken).ConfigureAwait(false);
            byte[] body = await ReadBoundedAsync(response.Content, cancellationToken).ConfigureAwait(false);
            string responseDigest = Digest(body);
            if (!response.IsSuccessStatusCode)
            {
                return new BuildGhostMeetingLinkCancellationResult(
                    false,
                    $"meeting-link-cancellation-http-{(int)response.StatusCode}",
                    responseDigest);
            }

            BrokerCancelResponse? result = JsonSerializer.Deserialize<BrokerCancelResponse>(body, StrictJson);
            return result is { Success: true }
                ? new BuildGhostMeetingLinkCancellationResult(true, "cancelled", responseDigest)
                : new BuildGhostMeetingLinkCancellationResult(false, "meeting-link-cancellation-response-invalid", responseDigest);
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            throw;
        }
        catch (Exception exception) when (exception is HttpRequestException
            or IOException
            or JsonException
            or InvalidOperationException)
        {
            return new BuildGhostMeetingLinkCancellationResult(
                false,
                "meeting-link-cancellation-transport-failed-redacted",
                string.Empty);
        }
    }

    public static bool IsAllowedBrokerBaseAddress(Uri uri)
    {
        if (!uri.IsAbsoluteUri
            || !string.IsNullOrEmpty(uri.UserInfo)
            || !string.IsNullOrEmpty(uri.Query)
            || !string.IsNullOrEmpty(uri.Fragment)
            || uri.AbsolutePath is not ("" or "/"))
        {
            return false;
        }

        if (string.Equals(uri.Scheme, Uri.UriSchemeHttps, StringComparison.OrdinalIgnoreCase))
        {
            return true;
        }

        return string.Equals(uri.Scheme, Uri.UriSchemeHttp, StringComparison.OrdinalIgnoreCase)
            && (uri.IsLoopback
                || uri.Host.EndsWith(".internal", StringComparison.OrdinalIgnoreCase)
                || (!uri.Host.Contains('.', StringComparison.Ordinal) && uri.Host.Length > 0));
    }

    private static bool IsValidCommand(BuildGhostMeetingLinkProvisioningCommand command)
        => SafeIdentifier.IsMatch(command.RequestId ?? string.Empty)
            && SafeIdentifier.IsMatch(command.IdempotencyKey ?? string.Empty)
            && command.OwnerScopeHash is { Length: 71 }
            && command.OwnerScopeHash.StartsWith("sha256:", StringComparison.Ordinal)
            && command.MeetingProvider is BuildGhostLiveMeetingProviders.Zoom or BuildGhostLiveMeetingProviders.Teams
            && command.DurationMinutes is >= 5 and <= 60;

    private HttpRequestMessage CreateRequest(HttpMethod method, string path, string idempotencyKey)
    {
        HttpRequestMessage request = new(method, path);
        request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", _token);
        request.Headers.Accept.Add(new MediaTypeWithQualityHeaderValue("application/json"));
        request.Headers.CacheControl = new CacheControlHeaderValue { NoStore = true };
        request.Headers.TryAddWithoutValidation("Idempotency-Key", idempotencyKey);
        return request;
    }

    private static async Task<byte[]> ReadBoundedAsync(
        HttpContent content,
        CancellationToken cancellationToken)
    {
        await using Stream stream = await content.ReadAsStreamAsync(cancellationToken).ConfigureAwait(false);
        using MemoryStream buffer = new();
        byte[] chunk = new byte[16 * 1024];
        int total = 0;
        while (true)
        {
            int read = await stream.ReadAsync(chunk.AsMemory(), cancellationToken).ConfigureAwait(false);
            if (read == 0)
            {
                return buffer.ToArray();
            }
            total += read;
            if (total > MaximumResponseBytes)
            {
                throw new IOException("meeting-link-broker-response-too-large");
            }
            buffer.Write(chunk, 0, read);
        }
    }

    private static string NormalizeToken(string? configured)
    {
        string token = configured?.Trim() ?? string.Empty;
        return token.Length is >= 32 and <= 4096 && token.IndexOfAny(['\r', '\n', '\0']) < 0
            ? token
            : string.Empty;
    }

    private static BuildGhostMeetingLinkProvisioningResult Failed(
        string provider,
        string code,
        string responseDigest = "",
        bool reconciliationRequired = false)
        => new(false, reconciliationRequired, code, provider, null, string.Empty, string.Empty, responseDigest, null, null);

    private static string Digest(ReadOnlySpan<byte> bytes)
        => $"sha256:{Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant()}";

    private sealed record BrokerCreateRequest(
        string Schema,
        string RequestId,
        string OwnerScopeHash,
        string MeetingProvider,
        string Locale,
        int DurationMinutes,
        string IdempotencyKey);

    private sealed record BrokerCreateResponse(
        bool Success,
        string MeetingProvider,
        string MeetingId,
        string CancellationHandle,
        string JoinUrl,
        DateTimeOffset? StartsAtUtc,
        DateTimeOffset? ExpiresAtUtc);

    private sealed record BrokerCancelRequest(
        string Schema,
        string RequestId,
        string MeetingProvider,
        string IdempotencyKey);

    private sealed record BrokerCancelResponse(bool Success);
}
