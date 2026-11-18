using Chummer.Run.Contracts.BuildGhost;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using System.Net;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text.Json;

namespace Chummer.Run.AI.Services.BuildGhost;

public interface IBuildGhostPrivateToolAuthorityClient
{
    Task<string> ResolveAsync(
        BuildGhostPrivateToolRequest request,
        string toolContractDigest,
        CancellationToken cancellationToken);
}

public sealed class BuildGhostPrivateToolResolutionException(
    string reason,
    int statusCode = StatusCodes.Status502BadGateway) : Exception(reason)
{
    public string Reason { get; } = reason;
    public int StatusCode { get; } = statusCode;
}

public sealed class BuildGhostPrivateToolAuthorityClient : IBuildGhostPrivateToolAuthorityClient
{
    public const string AuthorityEndpointConfigurationKey = "CHUMMER_BUILD_GHOST_PRIVATE_TOOL_AUTHORITY_ENDPOINT";
    public const string ServiceTokenConfigurationKey = "CHUMMER_BUILD_GHOST_PRIVATE_TOOL_SERVICE_TOKEN";
    public const int MaximumResponseCharacters = 15_000;
    public const int TimeoutSeconds = 120;

    private readonly HttpClient httpClient;
    private readonly IConfiguration configuration;
    private readonly TimeSpan requestBudget;

    private static readonly HashSet<string> AllowedRequestKinds =
        ["current-build", "build-tips", "rule-explanation", "build-variants", "group-gaps"];

    private static readonly HashSet<string> ForbiddenPacketProperties = new(StringComparer.OrdinalIgnoreCase)
    {
        "rawXml",
        "characterXml",
        "privateNotes",
        "hiddenQualities",
        "secretGmMaterial",
        "providerCredentials",
        "packetAccessKey"
    };

    [ActivatorUtilitiesConstructor]
    public BuildGhostPrivateToolAuthorityClient(
        HttpClient httpClient,
        IConfiguration configuration)
        : this(httpClient, configuration, TimeSpan.FromSeconds(TimeoutSeconds))
    {
    }

    public BuildGhostPrivateToolAuthorityClient(
        HttpClient httpClient,
        IConfiguration configuration,
        TimeSpan requestBudget)
    {
        ArgumentNullException.ThrowIfNull(httpClient);
        ArgumentNullException.ThrowIfNull(configuration);
        if (requestBudget <= TimeSpan.Zero || requestBudget > TimeSpan.FromSeconds(TimeoutSeconds))
        {
            throw new ArgumentOutOfRangeException(nameof(requestBudget), "Private tool request budget must be positive and no greater than 120 seconds.");
        }

        this.httpClient = httpClient;
        this.configuration = configuration;
        this.requestBudget = requestBudget;
    }

    public async Task<string> ResolveAsync(
        BuildGhostPrivateToolRequest request,
        string toolContractDigest,
        CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(request);
        Uri endpoint = ResolveEndpoint();
        string serviceToken = configuration[ServiceTokenConfigurationKey]?.Trim() ?? string.Empty;
        if (serviceToken.Length < 32)
        {
            throw new BuildGhostPrivateToolResolutionException(
                "private-tool-service-auth-unavailable",
                StatusCodes.Status503ServiceUnavailable);
        }

        using HttpRequestMessage upstream = new(HttpMethod.Post, endpoint)
        {
            Content = JsonContent.Create(new BuildGhostPrivateToolAuthorityRequest(
                request.PacketAccessKey,
                request.PacketDigest,
                request.Locale,
                request.RequestKind))
        };
        upstream.Headers.Authorization = new AuthenticationHeaderValue("Bearer", serviceToken);
        upstream.Headers.TryAddWithoutValidation("X-Chummer-Build-Ghost-Tool-Contract", toolContractDigest);

        using CancellationTokenSource budgetCancellation =
            CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        budgetCancellation.CancelAfter(requestBudget);
        try
        {
            using HttpResponseMessage response = await httpClient.SendAsync(
                upstream,
                HttpCompletionOption.ResponseHeadersRead,
                budgetCancellation.Token).ConfigureAwait(false);
            if (!response.IsSuccessStatusCode)
            {
                int status = response.StatusCode is HttpStatusCode.Unauthorized
                    or HttpStatusCode.Forbidden
                    or HttpStatusCode.NotFound
                    ? StatusCodes.Status401Unauthorized
                    : response.StatusCode is HttpStatusCode.Conflict or HttpStatusCode.PreconditionFailed
                        ? StatusCodes.Status409Conflict
                        : response.StatusCode is HttpStatusCode.Gone
                            ? StatusCodes.Status410Gone
                        : StatusCodes.Status502BadGateway;
                throw new BuildGhostPrivateToolResolutionException("private-tool-authority-rejected", status);
            }

            string responseDigest = ReadSingleDigestHeader(response);
            string packetJson = await ReadBoundedAsync(response.Content, budgetCancellation.Token).ConfigureAwait(false);
            ValidatePacket(packetJson, responseDigest, request);
            return packetJson;
        }
        catch (OperationCanceledException) when (!cancellationToken.IsCancellationRequested)
        {
            throw new BuildGhostPrivateToolResolutionException(
                "private-tool-authority-timeout",
                StatusCodes.Status504GatewayTimeout);
        }
        catch (HttpRequestException)
        {
            throw new BuildGhostPrivateToolResolutionException("private-tool-authority-unavailable");
        }
    }

    public static IReadOnlyList<string> ValidateRequest(BuildGhostPrivateToolRequest? request)
    {
        List<string> reasons = [];
        if (request is null)
        {
            return ["private-tool-request-required"];
        }

        if (!IsOpaqueKey(request.PacketAccessKey)) reasons.Add("packet-access-key-invalid");
        if (!IsSha256(request.PacketDigest)) reasons.Add("packet-digest-invalid");
        if (!ToughTongueBuildGhostScenarioContract.CanonicalLocales.Contains(request.Locale, StringComparer.Ordinal))
        {
            reasons.Add("locale-unsupported");
        }
        if (!AllowedRequestKinds.Contains(request.RequestKind ?? string.Empty)) reasons.Add("request-kind-unsupported");
        if (request.Question is { Length: > 2_000 } || request.Question?.Any(char.IsControl) == true)
        {
            reasons.Add("question-invalid");
        }
        return reasons;
    }

    public static IReadOnlyList<string> ValidateProviderRequest(
        BuildGhostPrivateToolProviderRequest? request)
    {
        if (request is null)
        {
            return ["private-tool-provider-request-required"];
        }
        List<string> reasons = [];
        if (request.Schema != ToughTongueBuildGhostContractVersions.PrivateToolRequestV2)
        {
            reasons.Add("private-tool-provider-request-schema-invalid");
        }
        if (!IsCanonicalPacketAccessKey(request.PacketAccessKey))
        {
            reasons.Add("packet-access-key-invalid");
        }
        if (!IsSha256(request.PacketDigest)) reasons.Add("packet-digest-invalid");
        if (!ToughTongueBuildGhostScenarioContract.CanonicalLocales.Contains(request.Locale, StringComparer.Ordinal))
        {
            reasons.Add("locale-unsupported");
        }
        if (!AllowedRequestKinds.Contains(request.RequestKind ?? string.Empty)) reasons.Add("request-kind-unsupported");
        if (request.Question is { Length: > 2_000 } || request.Question?.Any(char.IsControl) == true)
        {
            reasons.Add("question-invalid");
        }
        return reasons;
    }

    private Uri ResolveEndpoint()
    {
        string value = configuration[AuthorityEndpointConfigurationKey]?.Trim() ?? string.Empty;
        if (!Uri.TryCreate(value, UriKind.Absolute, out Uri? endpoint)
            || !string.Equals(endpoint.Scheme, Uri.UriSchemeHttps, StringComparison.OrdinalIgnoreCase)
            || (!string.Equals(endpoint.Host, "chummer.run", StringComparison.OrdinalIgnoreCase)
                && !endpoint.Host.EndsWith(".chummer.run", StringComparison.OrdinalIgnoreCase))
            || !string.Equals(endpoint.AbsolutePath, "/api/internal/build-ghost/tool/resolve", StringComparison.Ordinal)
            || !string.IsNullOrEmpty(endpoint.UserInfo)
            || !string.IsNullOrEmpty(endpoint.Query)
            || !string.IsNullOrEmpty(endpoint.Fragment))
        {
            throw new BuildGhostPrivateToolResolutionException(
                "private-tool-authority-endpoint-invalid",
                StatusCodes.Status503ServiceUnavailable);
        }
        return endpoint;
    }

    private static async Task<string> ReadBoundedAsync(HttpContent content, CancellationToken cancellationToken)
    {
        if (content.Headers.ContentLength is > MaximumResponseCharacters * 4L)
        {
            throw new BuildGhostPrivateToolResolutionException("private-tool-response-too-large");
        }

        await using Stream stream = await content.ReadAsStreamAsync(cancellationToken).ConfigureAwait(false);
        using StreamReader reader = new(stream, detectEncodingFromByteOrderMarks: true);
        char[] buffer = new char[MaximumResponseCharacters + 1];
        int total = 0;
        while (total < buffer.Length)
        {
            int read = await reader.ReadAsync(buffer.AsMemory(total, buffer.Length - total), cancellationToken).ConfigureAwait(false);
            if (read == 0) break;
            total += read;
        }
        if (total > MaximumResponseCharacters || await reader.ReadAsync(new char[1], cancellationToken).ConfigureAwait(false) != 0)
        {
            throw new BuildGhostPrivateToolResolutionException("private-tool-response-too-large");
        }
        return new string(buffer, 0, total);
    }

    private static string ReadSingleDigestHeader(HttpResponseMessage response)
    {
        if (!response.Headers.TryGetValues(
                "X-Chummer-Build-Ghost-Packet-Digest",
                out IEnumerable<string>? values))
        {
            return string.Empty;
        }

        string[] digests = values.Select(static value => value.Trim()).ToArray();
        if (digests.Length != 1 || string.IsNullOrEmpty(digests[0]))
        {
            throw new BuildGhostPrivateToolResolutionException("private-tool-packet-digest-header-invalid");
        }
        return digests[0];
    }

    private static void ValidatePacket(
        string packetJson,
        string responseDigest,
        BuildGhostPrivateToolRequest request)
    {
        JsonDocument packet;
        try
        {
            packet = JsonDocument.Parse(packetJson);
        }
        catch (JsonException)
        {
            throw new BuildGhostPrivateToolResolutionException("private-tool-packet-json-invalid");
        }

        using (packet)
        {
            JsonElement root = packet.RootElement;
            if (root.ValueKind != JsonValueKind.Object
                || Text(root, "schema") != ToughTongueBuildGhostContractVersions.AnalysisV1)
            {
                throw new BuildGhostPrivateToolResolutionException("private-tool-packet-schema-invalid");
            }
            string packetDigest = Text(root, "packetDigest");
            if (!IsSha256(responseDigest)
                || !string.Equals(responseDigest, request.PacketDigest, StringComparison.Ordinal)
                || !string.Equals(packetDigest, request.PacketDigest, StringComparison.Ordinal))
            {
                throw new BuildGhostPrivateToolResolutionException("private-tool-packet-digest-drift");
            }
            if (!string.Equals(Text(root, "locale"), request.Locale, StringComparison.Ordinal))
            {
                throw new BuildGhostPrivateToolResolutionException("private-tool-packet-locale-drift");
            }
            if (ContainsForbiddenProperty(root))
            {
                throw new BuildGhostPrivateToolResolutionException("private-tool-packet-privacy-rejected");
            }
        }
    }

    private static bool ContainsForbiddenProperty(JsonElement element)
    {
        if (element.ValueKind == JsonValueKind.Object)
        {
            foreach (JsonProperty property in element.EnumerateObject())
            {
                if (ForbiddenPacketProperties.Contains(property.Name) || ContainsForbiddenProperty(property.Value)) return true;
            }
        }
        else if (element.ValueKind == JsonValueKind.Array)
        {
            foreach (JsonElement child in element.EnumerateArray())
            {
                if (ContainsForbiddenProperty(child)) return true;
            }
        }
        return false;
    }

    private static string Text(JsonElement root, string property)
        => root.TryGetProperty(property, out JsonElement value) && value.ValueKind == JsonValueKind.String
            ? value.GetString()?.Trim() ?? string.Empty
            : string.Empty;

    private static bool IsOpaqueKey(string? value)
        => value is { Length: >= 32 and <= 512 }
            && !value.Contains('@', StringComparison.Ordinal)
            && !value.Contains("//", StringComparison.Ordinal)
            && value.All(static character => char.IsAsciiLetterOrDigit(character) || character is '-' or '_' or '.' or ':');

    private static bool IsCanonicalPacketAccessKey(string? value)
        => value is { Length: 43 }
            && value.All(static character => char.IsAsciiLetterOrDigit(character) || character is '-' or '_')
            // A 32-byte unpadded base64url value has four data bits in its final
            // character and therefore two canonical zero padding bits.
            && "AEIMQUYcgkosw048".Contains(value[^1]);

    private static bool IsSha256(string? value)
        => value is { Length: 71 }
            && value.StartsWith("sha256:", StringComparison.Ordinal)
            && value.AsSpan(7).ToString().All(static character => character is >= '0' and <= '9' or >= 'a' and <= 'f');
}
