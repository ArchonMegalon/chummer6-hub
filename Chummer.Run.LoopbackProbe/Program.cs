using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Net;
using System.Net.Http;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

internal static class Program
{
    private const int MaximumResponseBytes = 256 * 1024;
    private static readonly TimeSpan OverallTimeout = TimeSpan.FromSeconds(5);
    private static readonly Uri ReadyUri =
        new("http://127.0.0.1:8080/api/ready", UriKind.Absolute);
    private static readonly Uri PublicationUri =
        new("http://127.0.0.1:8080/api/ready/publication", UriKind.Absolute);
    private static readonly Uri InstallLinkingAuthorityUri =
        new(
            "http://127.0.0.1:8080/api/ready/install-linking-authority",
            UriKind.Absolute);

    public static async Task<int> Main(string[] args)
    {
        if (args.Length != 1 || !TryResolveEndpoint(args[0], out Uri? endpoint))
        {
            Console.Error.WriteLine(
                "Usage: Chummer.Run.LoopbackProbe.dll "
                + "</api/ready|/api/ready/publication|"
                + "/api/ready/install-linking-authority>");
            return 64;
        }

        try
        {
            using var handler = new SocketsHttpHandler
            {
                AllowAutoRedirect = false,
                AutomaticDecompression = DecompressionMethods.None,
                ConnectTimeout = TimeSpan.FromSeconds(2),
                MaxResponseHeadersLength = 32,
                UseCookies = false,
                UseProxy = false
            };
            using var client = new HttpClient(handler)
            {
                Timeout = OverallTimeout
            };
            using var request = new HttpRequestMessage(HttpMethod.Get, endpoint)
            {
                Version = HttpVersion.Version11,
                VersionPolicy = HttpVersionPolicy.RequestVersionExact
            };
            request.Headers.Host = "chummer.run";

            using var timeout = new CancellationTokenSource(OverallTimeout);
            using HttpResponseMessage response = await client.SendAsync(
                request,
                HttpCompletionOption.ResponseHeadersRead,
                timeout.Token);
            if (!ResponseHeadersAreValid(response))
            {
                return 1;
            }

            byte[]? payload = await ReadBoundedResponseAsync(
                response.Content,
                timeout.Token);
            if (payload is null)
            {
                return 1;
            }

            using JsonDocument document = JsonDocument.Parse(
                payload,
                new JsonDocumentOptions
                {
                    AllowTrailingCommas = false,
                    CommentHandling = JsonCommentHandling.Disallow,
                    MaxDepth = 32
                });
            if (!ValidatePayload(args[0], document.RootElement))
            {
                return 1;
            }

            await Console.OpenStandardOutput().WriteAsync(
                payload.AsMemory(),
                timeout.Token);
            return 0;
        }
        catch (Exception exception) when (
            exception is HttpRequestException
                or IOException
                or InvalidOperationException
                or JsonException
                or OperationCanceledException)
        {
            return 1;
        }
    }

    private static bool TryResolveEndpoint(string path, out Uri? endpoint)
    {
        endpoint = path switch
        {
            "/api/ready" => ReadyUri,
            "/api/ready/publication" => PublicationUri,
            "/api/ready/install-linking-authority" =>
                InstallLinkingAuthorityUri,
            _ => null
        };
        return endpoint is not null;
    }

    private static bool ResponseHeadersAreValid(HttpResponseMessage response)
    {
        if (response.StatusCode != HttpStatusCode.OK
            || response.Version != HttpVersion.Version11
            || response.Content.Headers.ContentEncoding.Count != 0)
        {
            return false;
        }

        var contentType = response.Content.Headers.ContentType;
        string? parameterName = null;
        foreach (var parameter in contentType?.Parameters ?? [])
        {
            parameterName = parameter.Name;
        }
        if (contentType is null
            || !string.Equals(
                contentType.MediaType,
                "application/json",
                StringComparison.OrdinalIgnoreCase)
            || contentType.Parameters.Count != 1
            || !string.Equals(
                parameterName,
                "charset",
                StringComparison.OrdinalIgnoreCase)
            || !string.Equals(
                contentType.CharSet?.Trim('"'),
                "utf-8",
                StringComparison.OrdinalIgnoreCase))
        {
            return false;
        }

        long? contentLength = response.Content.Headers.ContentLength;
        return contentLength is null
            || contentLength is >= 1 and <= MaximumResponseBytes;
    }

    private static async Task<byte[]?> ReadBoundedResponseAsync(
        HttpContent content,
        CancellationToken cancellationToken)
    {
        await using Stream responseBody =
            await content.ReadAsStreamAsync(cancellationToken);
        using var boundedBody = new MemoryStream(capacity: 16 * 1024);
        byte[] buffer = new byte[8192];
        while (true)
        {
            int read = await responseBody.ReadAsync(
                buffer.AsMemory(),
                cancellationToken);
            if (read == 0)
            {
                break;
            }

            if (boundedBody.Length + read > MaximumResponseBytes)
            {
                return null;
            }

            await boundedBody.WriteAsync(
                buffer.AsMemory(0, read),
                cancellationToken);
        }

        return boundedBody.Length == 0 ? null : boundedBody.ToArray();
    }

    private static bool ValidatePayload(string path, JsonElement root)
        => path switch
        {
            "/api/ready" => ValidateReady(root),
            "/api/ready/publication" => ValidatePublication(root),
            "/api/ready/install-linking-authority" =>
                ValidateInstallLinkingAuthority(root),
            _ => false
        };

    private static bool ValidateReady(JsonElement root)
    {
        string[] rootProperties =
        [
            "ready",
            "status",
            "generatedAt",
            "hub",
            "playProjection",
            "deploymentIdentity"
        ];
        if (!HasExactProperties(root, rootProperties)
            || !HasBoolean(root, "ready", expected: true)
            || !HasString(root, "status", "ready")
            || !HasTimestamp(root, "generatedAt")
            || !root.TryGetProperty("hub", out JsonElement hub)
            || !ValidateHub(hub)
            || !root.TryGetProperty(
                "playProjection",
                out JsonElement playProjection)
            || !ValidatePlayProjection(playProjection)
            || !root.TryGetProperty(
                "deploymentIdentity",
                out JsonElement deploymentIdentity)
            || !ValidateDeploymentIdentity(deploymentIdentity))
        {
            return false;
        }

        return true;
    }

    private static bool ValidateHub(JsonElement hub)
    {
        string[] properties =
        [
            "contractName",
            "service",
            "ready",
            "status",
            "servingReady",
            "publicationReady",
            "publicationChecksConfigured",
            "generatedAt",
            "checks",
            "releaseShelf"
        ];
        if (!HasExactProperties(hub, properties)
            || !HasString(
                hub,
                "contractName",
                "chummer.run.api.deep_readiness.v2")
            || !HasString(hub, "service", "chummer.run.api")
            || !HasBoolean(hub, "ready", expected: true)
            || !HasString(hub, "status", "pass")
            || !HasBoolean(hub, "servingReady", expected: true)
            || !HasBooleanValue(hub, "publicationReady", out bool publicationReady)
            || !HasBooleanValue(
                hub,
                "publicationChecksConfigured",
                out bool publicationChecksConfigured)
            || !HasTimestamp(hub, "generatedAt")
            || !hub.TryGetProperty("checks", out JsonElement checks)
            || !ValidateHubChecks(checks)
            || !hub.TryGetProperty(
                "releaseShelf",
                out JsonElement releaseShelf)
            || !ValidateReleaseShelf(
                releaseShelf,
                publicationReady,
                publicationChecksConfigured))
        {
            return false;
        }

        return true;
    }

    private static bool ValidateHubChecks(JsonElement checks)
    {
        string[] requiredNames =
        [
            "data_protection_storage",
            "install_linking_store",
            "release_shelf",
            "canonical_release_manifest"
        ];
        if (checks.ValueKind != JsonValueKind.Array
            || checks.GetArrayLength() != requiredNames.Length)
        {
            return false;
        }

        var observedNames = new HashSet<string>(StringComparer.Ordinal);
        foreach (JsonElement check in checks.EnumerateArray())
        {
            string[] properties = ["name", "passed", "status", "code"];
            if (!HasExactProperties(check, properties)
                || !TryGetString(check, "name", out string? name)
                || !observedNames.Add(name)
                || !HasBoolean(check, "passed", expected: true)
                || !HasString(check, "status", "pass")
                || !TryGetString(check, "code", out string? code)
                || !IsSafeCode(code))
            {
                return false;
            }
        }

        return observedNames.SetEquals(requiredNames);
    }

    private static bool ValidateReleaseShelf(
        JsonElement shelf,
        bool expectedPublicationReady,
        bool expectedPublicationChecksConfigured)
    {
        string[] properties =
        [
            "mode",
            "servingReady",
            "publicationReady",
            "publicationChecksConfigured",
            "status",
            "code",
            "generationId",
            "activationReceiptId",
            "inventoryDigest",
            "releaseVersion",
            "channel",
            "publishedAt",
            "publicationChecks"
        ];
        if (!HasExactProperties(shelf, properties)
            || !HasString(shelf, "mode", "generation")
            || !HasBoolean(shelf, "servingReady", expected: true)
            || !HasBoolean(
                shelf,
                "publicationReady",
                expectedPublicationReady)
            || !HasBoolean(
                shelf,
                "publicationChecksConfigured",
                expectedPublicationChecksConfigured)
            || !HasString(shelf, "status", "serving")
            || !TryGetString(shelf, "code", out string? code)
            || !IsSafeCode(code)
            || !HasNonEmptyString(shelf, "generationId")
            || !HasNonEmptyString(shelf, "activationReceiptId")
            || !HasLowercaseSha256(shelf, "inventoryDigest")
            || !HasNonEmptyString(shelf, "releaseVersion")
            || !HasNonEmptyString(shelf, "channel")
            || !HasTimestamp(shelf, "publishedAt")
            || !shelf.TryGetProperty(
                "publicationChecks",
                out JsonElement checks)
            || !ValidatePublicationChecks(
                checks,
                requireAllReady: expectedPublicationReady,
                requireNamedContract: false))
        {
            return false;
        }

        return true;
    }

    private static bool ValidatePlayProjection(JsonElement projection)
    {
        string[] properties = ["status", "ready", "enabled", "detail"];
        return HasExactProperties(projection, properties)
            && HasBoolean(projection, "ready", expected: true)
            && TryGetString(projection, "status", out string? status)
            && IsSafeCode(status)
            && HasBooleanValue(projection, "enabled", out _)
            && HasNonEmptyString(projection, "detail");
    }

    private static bool ValidateDeploymentIdentity(JsonElement identity)
    {
        string[] properties =
        [
            "ready",
            "code",
            "sourceFingerprintSha256",
            "fullDeploymentDigestSha256"
        ];
        return HasExactProperties(identity, properties)
            && HasBoolean(identity, "ready", expected: true)
            && HasString(identity, "code", "overlay_identity_bound")
            && HasLowercaseSha256(identity, "sourceFingerprintSha256")
            && HasLowercaseSha256(identity, "fullDeploymentDigestSha256");
    }

    private static bool ValidatePublication(JsonElement root)
    {
        string[] properties =
        [
            "ready",
            "checksConfigured",
            "status",
            "code",
            "observedAt",
            "generationId",
            "activationReceiptId",
            "inventoryDigest",
            "checks"
        ];
        return HasExactProperties(root, properties)
            && HasBoolean(root, "ready", expected: true)
            && HasBoolean(root, "checksConfigured", expected: true)
            && HasString(root, "status", "ready")
            && HasString(root, "code", "publication_ready")
            && HasTimestamp(root, "observedAt")
            && HasNonEmptyString(root, "generationId")
            && HasNonEmptyString(root, "activationReceiptId")
            && HasLowercaseSha256(root, "inventoryDigest")
            && root.TryGetProperty("checks", out JsonElement checks)
            && ValidatePublicationChecks(
                checks,
                requireAllReady: true,
                requireNamedContract: true);
    }

    private static bool ValidatePublicationChecks(
        JsonElement checks,
        bool requireAllReady,
        bool requireNamedContract)
    {
        if (checks.ValueKind != JsonValueKind.Array
            || checks.GetArrayLength() == 0)
        {
            return false;
        }

        var observedNames = new HashSet<string>(StringComparer.Ordinal);
        foreach (JsonElement check in checks.EnumerateArray())
        {
            string[] properties = ["name", "ready", "status", "code"];
            if (!HasExactProperties(check, properties)
                || !TryGetString(check, "name", out string? name)
                || !IsSafeCode(name)
                || !observedNames.Add(name)
                || !HasBooleanValue(check, "ready", out bool ready)
                || (requireAllReady && !ready)
                || !HasString(check, "status", ready ? "ready" : "blocked")
                || !TryGetString(check, "code", out string? code)
                || !IsSafeCode(code))
            {
                return false;
            }
        }

        if (!requireNamedContract)
        {
            return true;
        }

        string[] requiredNames =
        [
            "release_shelf_serving",
            "publication_probe_contract",
            "activation_protocol",
            "release_storage_admission"
        ];
        foreach (string requiredName in requiredNames)
        {
            if (!observedNames.Contains(requiredName))
            {
                return false;
            }
        }

        return true;
    }

    private static bool ValidateInstallLinkingAuthority(JsonElement root)
    {
        string[] properties =
        [
            "authorityIdentitySha256",
            "checkedAtUtc",
            "code",
            "contractName",
            "currentRoleMatches",
            "leastPrivilegeValid",
            "ready",
            "runtimeRoleSha256",
            "status"
        ];
        return HasExactProperties(root, properties)
            && HasLowercaseSha256(root, "authorityIdentitySha256")
            && HasTimestamp(root, "checkedAtUtc")
            && HasString(root, "code", "runtime_role_least_privilege")
            && HasString(
                root,
                "contractName",
                "chummer.install_linking_postgres_runtime_authority_readiness.v1")
            && HasBoolean(root, "currentRoleMatches", expected: true)
            && HasBoolean(root, "leastPrivilegeValid", expected: true)
            && HasBoolean(root, "ready", expected: true)
            && HasLowercaseSha256(root, "runtimeRoleSha256")
            && HasString(root, "status", "pass");
    }

    private static bool HasExactProperties(
        JsonElement element,
        IReadOnlyCollection<string> expectedProperties)
    {
        if (element.ValueKind != JsonValueKind.Object)
        {
            return false;
        }

        var expected = new HashSet<string>(
            expectedProperties,
            StringComparer.Ordinal);
        var observed = new HashSet<string>(StringComparer.Ordinal);
        foreach (JsonProperty property in element.EnumerateObject())
        {
            if (!expected.Contains(property.Name)
                || !observed.Add(property.Name))
            {
                return false;
            }
        }

        return observed.SetEquals(expected);
    }

    private static bool HasBoolean(
        JsonElement element,
        string propertyName,
        bool expected)
        => HasBooleanValue(element, propertyName, out bool actual)
           && actual == expected;

    private static bool HasBooleanValue(
        JsonElement element,
        string propertyName,
        out bool value)
    {
        value = false;
        if (!element.TryGetProperty(propertyName, out JsonElement property))
        {
            return false;
        }

        if (property.ValueKind == JsonValueKind.True)
        {
            value = true;
            return true;
        }

        return property.ValueKind == JsonValueKind.False;
    }

    private static bool HasString(
        JsonElement element,
        string propertyName,
        string expected)
        => TryGetString(element, propertyName, out string? actual)
           && string.Equals(actual, expected, StringComparison.Ordinal);

    private static bool HasNonEmptyString(
        JsonElement element,
        string propertyName)
        => TryGetString(element, propertyName, out string? value)
           && value.Length is >= 1 and <= 256
           && !string.IsNullOrWhiteSpace(value);

    private static bool HasLowercaseSha256(
        JsonElement element,
        string propertyName)
        => TryGetString(element, propertyName, out string? value)
           && value.Length == 64
           && IsLowercaseHex(value);

    private static bool TryGetString(
        JsonElement element,
        string propertyName,
        out string value)
    {
        value = string.Empty;
        if (!element.TryGetProperty(
                propertyName,
                out JsonElement property)
            || property.ValueKind != JsonValueKind.String)
        {
            return false;
        }

        string? observed = property.GetString();
        if (observed is null)
        {
            return false;
        }

        value = observed;
        return true;
    }

    private static bool HasTimestamp(
        JsonElement element,
        string propertyName)
    {
        if (!TryGetString(element, propertyName, out string? value)
            || value.Length is < 20 or > 40
            || value[10] != 'T'
            || !HasExplicitOffset(value))
        {
            return false;
        }

        return DateTimeOffset.TryParse(
            value,
            CultureInfo.InvariantCulture,
            DateTimeStyles.RoundtripKind,
            out _);
    }

    private static bool HasExplicitOffset(string value)
    {
        if (value.EndsWith('Z'))
        {
            return true;
        }

        int timeSeparator = value.IndexOf('T');
        return timeSeparator >= 0
            && (value.LastIndexOf('+') > timeSeparator
                || value.LastIndexOf('-') > timeSeparator);
    }

    private static bool IsLowercaseHex(string value)
    {
        foreach (char character in value)
        {
            if (character is not (>= '0' and <= '9')
                and not (>= 'a' and <= 'f'))
            {
                return false;
            }
        }

        return true;
    }

    private static bool IsSafeCode(string value)
    {
        if (value.Length is < 1 or > 96)
        {
            return false;
        }

        foreach (char character in value)
        {
            if (character is not (>= 'a' and <= 'z')
                and not (>= '0' and <= '9')
                and not '_')
            {
                return false;
            }
        }

        return true;
    }
}
