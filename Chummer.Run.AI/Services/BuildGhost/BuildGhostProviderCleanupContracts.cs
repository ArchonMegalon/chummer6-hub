using Chummer.Run.Contracts.BuildGhost;
using Microsoft.Extensions.Configuration;
using System.Net;
using System.Net.Http.Headers;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace Chummer.Run.AI.Services.BuildGhost;

public sealed class BuildGhostCartesiaVoiceDeletionClient
{
    public const string ExecuteEnabledConfigurationKey =
        "CHUMMER_BUILD_GHOST_CARTESIA_VOICE_DELETION_EXECUTE_ENABLED";
    public const string AuthorizedVoiceDigestConfigurationKey =
        "CHUMMER_BUILD_GHOST_CARTESIA_VOICE_DELETION_AUTHORIZED_VOICE_DIGEST";
    public const string ApiVersion = "2026-08-14";
    public const int MaximumOwnerListResponseBytes = 256 * 1024;

    private readonly HttpClient _httpClient;
    private readonly IConfiguration _configuration;
    private readonly IBuildGhostClock _clock;
    private readonly SemaphoreSlim _gate = new(1, 1);
    private readonly HashSet<string> _consumedAuthorizations = new(StringComparer.Ordinal);

    public BuildGhostCartesiaVoiceDeletionClient(
        HttpClient httpClient,
        IConfiguration configuration,
        IBuildGhostClock clock)
    {
        _httpClient = httpClient ?? throw new ArgumentNullException(nameof(httpClient));
        _configuration = configuration ?? throw new ArgumentNullException(nameof(configuration));
        _clock = clock ?? throw new ArgumentNullException(nameof(clock));
    }

    public async Task<BuildGhostCartesiaVoiceDeletionReceipt> DeleteAndVerifyAsync(
        string voiceId,
        string credential,
        CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        DateTimeOffset observedAt = _clock.UtcNow;
        string voiceIdDigest = IsExactVoiceId(voiceId) ? DigestText(voiceId) : string.Empty;
        List<string> blockers = [];
        bool executeEnabled = bool.TryParse(
            _configuration[ExecuteEnabledConfigurationKey],
            out bool enabled) && enabled;
        string authorizedDigest = _configuration[AuthorizedVoiceDigestConfigurationKey]?.Trim() ?? string.Empty;
        if (!executeEnabled) blockers.Add("cartesia-voice-deletion-execute-gate-disabled");
        if (string.IsNullOrEmpty(voiceIdDigest)) blockers.Add("cartesia-voice-deletion-voice-id-invalid");
        if (!IsSha256(authorizedDigest)
            || !FixedTimeEquals(authorizedDigest, voiceIdDigest))
        {
            blockers.Add("cartesia-voice-deletion-authorization-missing-or-mismatched");
        }
        if (!IsCredential(credential)) blockers.Add("cartesia-voice-deletion-credential-invalid");
        if (!IsOfficialApiBaseAddress(_httpClient.BaseAddress)) blockers.Add("cartesia-voice-deletion-api-boundary-invalid");
        if (blockers.Count != 0)
        {
            return Receipt("blocked", voiceIdDigest, blockers, observedAt);
        }

        await _gate.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            if (!_consumedAuthorizations.Add(authorizedDigest))
            {
                return Receipt(
                    "blocked",
                    voiceIdDigest,
                    ["cartesia-voice-deletion-authorization-replay-rejected"],
                    observedAt);
            }
        }
        finally
        {
            _gate.Release();
        }

        int? deleteStatus = null;
        int? readbackStatus = null;
        int? ownerListStatus = null;
        bool deleteAttempted = false;
        bool readbackAttempted = false;
        bool ownerListAttempted = false;
        bool ownerListAbsenceVerified = false;
        try
        {
            deleteAttempted = true;
            using HttpRequestMessage delete = CreateRequest(HttpMethod.Delete, $"voices/{voiceId}", credential);
            using HttpResponseMessage deleted = await _httpClient.SendAsync(delete, cancellationToken).ConfigureAwait(false);
            deleteStatus = (int)deleted.StatusCode;
            if (deleted.StatusCode != HttpStatusCode.NoContent)
            {
                blockers.Add("cartesia-voice-delete-http-status-invalid");
                return Receipt("failed", voiceIdDigest, blockers, observedAt,
                    deleteAttempted, deleteStatus, readbackAttempted, readbackStatus,
                    ownerListAttempted, ownerListStatus, ownerListAbsenceVerified);
            }

            readbackAttempted = true;
            using HttpRequestMessage readback = CreateRequest(HttpMethod.Get, $"voices/{voiceId}", credential);
            using HttpResponseMessage read = await _httpClient.SendAsync(readback, cancellationToken).ConfigureAwait(false);
            readbackStatus = (int)read.StatusCode;
            if (read.StatusCode != HttpStatusCode.NotFound)
            {
                blockers.Add("cartesia-deleted-voice-readback-not-absent");
                return Receipt("failed", voiceIdDigest, blockers, observedAt,
                    deleteAttempted, deleteStatus, readbackAttempted, readbackStatus,
                    ownerListAttempted, ownerListStatus, ownerListAbsenceVerified);
            }

            ownerListAttempted = true;
            using HttpRequestMessage ownerList = CreateRequest(HttpMethod.Get, "voices?is_owner=true&limit=100", credential);
            using HttpResponseMessage listed = await _httpClient.SendAsync(ownerList, cancellationToken).ConfigureAwait(false);
            ownerListStatus = (int)listed.StatusCode;
            if (listed.StatusCode != HttpStatusCode.OK)
            {
                blockers.Add("cartesia-owner-list-http-status-invalid");
            }
            else
            {
                byte[] body = await ReadBoundedAsync(listed.Content, cancellationToken).ConfigureAwait(false);
                ownerListAbsenceVerified = OwnerListProvesAbsence(body, voiceId, blockers);
            }
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            throw;
        }
        catch
        {
            blockers.Add("cartesia-voice-deletion-transport-or-response-failed-redacted");
        }

        return Receipt(
            blockers.Count == 0 && ownerListAbsenceVerified
                ? "deleted-and-absence-verified"
                : "failed",
            voiceIdDigest,
            blockers,
            observedAt,
            deleteAttempted,
            deleteStatus,
            readbackAttempted,
            readbackStatus,
            ownerListAttempted,
            ownerListStatus,
            ownerListAbsenceVerified);
    }

    public static bool IsOfficialApiBaseAddress(Uri? baseAddress)
        => baseAddress is not null
            && baseAddress.IsAbsoluteUri
            && string.Equals(baseAddress.Scheme, Uri.UriSchemeHttps, StringComparison.OrdinalIgnoreCase)
            && string.Equals(baseAddress.Host, "api.cartesia.ai", StringComparison.OrdinalIgnoreCase)
            && baseAddress.IsDefaultPort
            && string.Equals(baseAddress.AbsolutePath, "/", StringComparison.Ordinal)
            && string.IsNullOrEmpty(baseAddress.UserInfo)
            && string.IsNullOrEmpty(baseAddress.Query)
            && string.IsNullOrEmpty(baseAddress.Fragment);

    public static string VoiceIdDigest(string voiceId)
        => IsExactVoiceId(voiceId) ? DigestText(voiceId) : string.Empty;

    private static HttpRequestMessage CreateRequest(HttpMethod method, string relativePath, string credential)
    {
        HttpRequestMessage request = new(method, relativePath);
        request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", credential.Trim());
        request.Headers.TryAddWithoutValidation("Cartesia-Version", ApiVersion);
        request.Headers.TryAddWithoutValidation("Accept", "application/json");
        return request;
    }

    private static async Task<byte[]> ReadBoundedAsync(HttpContent content, CancellationToken cancellationToken)
    {
        if (content.Headers.ContentLength is > MaximumOwnerListResponseBytes)
        {
            throw new InvalidDataException("cartesia-owner-list-response-too-large");
        }
        byte[] body = await content.ReadAsByteArrayAsync(cancellationToken).ConfigureAwait(false);
        if (body.Length > MaximumOwnerListResponseBytes)
        {
            throw new InvalidDataException("cartesia-owner-list-response-too-large");
        }
        return body;
    }

    private static bool OwnerListProvesAbsence(byte[] body, string voiceId, ICollection<string> blockers)
    {
        JsonObject? payload;
        try
        {
            payload = JsonNode.Parse(body) as JsonObject;
        }
        catch (JsonException)
        {
            payload = null;
        }
        if (payload?["data"] is not JsonArray data
            || payload["has_more"] is not JsonValue hasMoreValue
            || !hasMoreValue.TryGetValue(out bool hasMore)
            || payload["next_page"] is not null and not JsonValue)
        {
            blockers.Add("cartesia-owner-list-schema-invalid");
            return false;
        }
        if (hasMore)
        {
            blockers.Add("cartesia-owner-list-incomplete");
            return false;
        }
        foreach (JsonNode? node in data)
        {
            if (node is not JsonObject voice
                || voice["id"] is not JsonValue idValue
                || !idValue.TryGetValue(out string? id)
                || string.IsNullOrWhiteSpace(id)
                || voice["is_owner"] is not JsonValue ownerValue
                || !ownerValue.TryGetValue(out bool isOwner)
                || !isOwner)
            {
                blockers.Add("cartesia-owner-list-schema-invalid");
                return false;
            }
            if (string.Equals(id, voiceId, StringComparison.Ordinal))
            {
                blockers.Add("cartesia-deleted-voice-remains-in-owner-list");
                return false;
            }
        }
        return true;
    }

    private static BuildGhostCartesiaVoiceDeletionReceipt Receipt(
        string outcome,
        string voiceIdDigest,
        IReadOnlyList<string> blockers,
        DateTimeOffset observedAt,
        bool deleteAttempted = false,
        int? deleteStatus = null,
        bool readbackAttempted = false,
        int? readbackStatus = null,
        bool ownerListAttempted = false,
        int? ownerListStatus = null,
        bool ownerListAbsenceVerified = false)
        => new(
            ToughTongueBuildGhostContractVersions.CartesiaVoiceDeletionReceiptV1,
            outcome,
            voiceIdDigest,
            deleteAttempted,
            deleteStatus,
            readbackAttempted,
            readbackStatus,
            ownerListAttempted,
            ownerListStatus,
            ownerListAbsenceVerified,
            RawResponseExposed: false,
            RawVoiceIdExposed: false,
            CredentialExposed: false,
            blockers.Distinct(StringComparer.Ordinal).OrderBy(static reason => reason, StringComparer.Ordinal).ToArray(),
            observedAt);

    private static bool IsExactVoiceId(string? value)
        => Guid.TryParseExact(value, "D", out Guid parsed)
            && string.Equals(parsed.ToString("D"), value, StringComparison.Ordinal);

    private static bool IsCredential(string? value)
        => !string.IsNullOrWhiteSpace(value)
            && value.Length <= 4096
            && value.IndexOfAny(['\r', '\n']) < 0;

    private static bool IsSha256(string? value)
        => value is { Length: 71 }
            && value.StartsWith("sha256:", StringComparison.Ordinal)
            && value.AsSpan(7).ToString().All(static character => character is >= '0' and <= '9' or >= 'a' and <= 'f');

    private static bool FixedTimeEquals(string left, string right)
    {
        byte[] leftBytes = Encoding.UTF8.GetBytes(left);
        byte[] rightBytes = Encoding.UTF8.GetBytes(right);
        return leftBytes.Length == rightBytes.Length
            && CryptographicOperations.FixedTimeEquals(leftBytes, rightBytes);
    }

    private static string DigestText(string value)
        => $"sha256:{Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(value))).ToLowerInvariant()}";
}

public static class ToughTongueBuildGhostScenarioCleanupContract
{
    public const string UndocumentedDeletionBlocker =
        "tough-tongue-scenario-deletion-contract-undocumented";

    public static ToughTongueBuildGhostScenarioDeletionBlockerReceipt CreateBlockedReceipt(
        string scenarioId,
        IBuildGhostClock clock)
    {
        ArgumentNullException.ThrowIfNull(clock);
        bool validId = scenarioId is { Length: 24 }
            && scenarioId.All(static character => character is >= '0' and <= '9' or >= 'a' and <= 'f');
        List<string> blockers = [UndocumentedDeletionBlocker];
        if (!validId) blockers.Add("tough-tongue-scenario-id-invalid");
        return new ToughTongueBuildGhostScenarioDeletionBlockerReceipt(
            ToughTongueBuildGhostContractVersions.ScenarioDeletionBlockerReceiptV1,
            "blocked",
            validId ? DigestText(scenarioId) : string.Empty,
            TransportAttempted: false,
            blockers.OrderBy(static reason => reason, StringComparer.Ordinal).ToArray(),
            clock.UtcNow);
    }

    private static string DigestText(string value)
        => $"sha256:{Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(value))).ToLowerInvariant()}";
}
