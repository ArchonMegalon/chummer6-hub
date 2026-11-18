using System.Text.Json;
using System.Text.Json.Serialization;

namespace Chummer.BuildGhost.CloudflareAccessEdge;

public static class BuildGhostProviderToolRequestContract
{
    public const string RequestSchema = "chummer.build_ghost.private_tool_request.v2";
    public const string Path = "/api/v2/ai/build-ghost/tool";
    public const int MaximumBodyBytes = 16 * 1024;
    public const int MaximumResponseBytes = 64 * 1024;

    private static readonly IReadOnlySet<string> CanonicalLocales = new HashSet<string>(StringComparer.Ordinal)
    {
        "de-DE",
        "en-US",
        "fr-FR",
        "ja-JP",
        "pt-BR",
        "zh-CN",
    };

    private static readonly IReadOnlySet<string> RequestKinds = new HashSet<string>(StringComparer.Ordinal)
    {
        "build-tips",
        "build-variants",
        "current-build",
        "group-gaps",
        "rule-explanation",
    };

    private static readonly IReadOnlySet<string> RequiredProperties = new HashSet<string>(StringComparer.Ordinal)
    {
        "schema",
        "packet_access_key",
        "packet_digest",
        "locale",
        "request_kind",
    };

    private static readonly IReadOnlySet<string> AllowedProperties = new HashSet<string>(
        RequiredProperties.Append("question"),
        StringComparer.Ordinal);

    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        PropertyNameCaseInsensitive = false,
        UnmappedMemberHandling = JsonUnmappedMemberHandling.Disallow,
    };

    public static bool TryParse(
        byte[] json,
        out BuildGhostProviderToolRequest? request,
        out IReadOnlyList<string> reasons)
    {
        request = null;
        List<string> validationReasons = [];
        try
        {
            using JsonDocument document = JsonDocument.Parse(json);
            if (document.RootElement.ValueKind != JsonValueKind.Object
                || !HasExactUniqueProperties(document.RootElement, RequiredProperties, AllowedProperties))
            {
                reasons = ["private-tool-provider-request-shape-invalid"];
                return false;
            }

            request = JsonSerializer.Deserialize<BuildGhostProviderToolRequest>(json, JsonOptions);
        }
        catch (JsonException)
        {
            reasons = ["private-tool-provider-request-json-invalid"];
            return false;
        }

        if (request is null)
        {
            reasons = ["private-tool-provider-request-required"];
            return false;
        }
        if (!string.Equals(request.Schema, RequestSchema, StringComparison.Ordinal))
        {
            validationReasons.Add("private-tool-provider-request-schema-invalid");
        }
        if (!IsCanonicalPacketAccessKey(request.PacketAccessKey))
        {
            validationReasons.Add("packet-access-key-invalid");
        }
        if (!IsCanonicalPacketDigest(request.PacketDigest))
        {
            validationReasons.Add("packet-digest-invalid");
        }
        if (!CanonicalLocales.Contains(request.Locale ?? string.Empty))
        {
            validationReasons.Add("locale-unsupported");
        }
        if (!RequestKinds.Contains(request.RequestKind ?? string.Empty))
        {
            validationReasons.Add("request-kind-unsupported");
        }
        if (request.Question is { Length: > 2_000 }
            || request.Question?.Any(char.IsControl) == true)
        {
            validationReasons.Add("question-invalid");
        }

        reasons = validationReasons;
        return validationReasons.Count == 0;
    }

    public static bool TryParseGrantResponse(
        byte[] json,
        out BuildGhostToolAccessGrantResponse? response)
    {
        response = null;
        try
        {
            using JsonDocument document = JsonDocument.Parse(json);
            HashSet<string> exact = new(StringComparer.Ordinal)
            {
                "packetAccessKey",
                "packetDigest",
                "expiresAtUtc",
            };
            if (document.RootElement.ValueKind != JsonValueKind.Object
                || !HasExactUniqueProperties(document.RootElement, exact, exact))
            {
                return false;
            }

            response = JsonSerializer.Deserialize<BuildGhostToolAccessGrantResponse>(json, JsonOptions);
            return response is not null
                && IsCanonicalPacketAccessKey(response.PacketAccessKey)
                && IsCanonicalPacketDigest(response.PacketDigest);
        }
        catch (JsonException)
        {
            return false;
        }
    }

    public static bool IsCanonicalPacketAccessKey(string? value)
        => value is { Length: 43 }
            && value.All(static character => char.IsAsciiLetterOrDigit(character) || character is '-' or '_')
            && "AEIMQUYcgkosw048".Contains(value[^1]);

    public static bool IsCanonicalPacketDigest(string? value)
        => value is { Length: 71 }
            && value.StartsWith("sha256:", StringComparison.Ordinal)
            && value.AsSpan(7).ToString().All(
                static character => character is >= '0' and <= '9' or >= 'a' and <= 'f');

    private static bool HasExactUniqueProperties(
        JsonElement root,
        IReadOnlySet<string> required,
        IReadOnlySet<string> allowed)
    {
        HashSet<string> seen = new(StringComparer.Ordinal);
        foreach (JsonProperty property in root.EnumerateObject())
        {
            if (!allowed.Contains(property.Name) || !seen.Add(property.Name))
            {
                return false;
            }
        }

        return required.All(seen.Contains);
    }
}

[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record BuildGhostProviderToolRequest(
    [property: JsonPropertyName("schema")] string Schema,
    [property: JsonPropertyName("packet_access_key")] string PacketAccessKey,
    [property: JsonPropertyName("packet_digest")] string PacketDigest,
    [property: JsonPropertyName("locale")] string Locale,
    [property: JsonPropertyName("request_kind")] string RequestKind,
    [property: JsonPropertyName("question")] string? Question);

[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record BuildGhostToolAccessGrantResponse(
    [property: JsonPropertyName("packetAccessKey")] string PacketAccessKey,
    [property: JsonPropertyName("packetDigest")] string PacketDigest,
    [property: JsonPropertyName("expiresAtUtc")] DateTimeOffset ExpiresAtUtc);
