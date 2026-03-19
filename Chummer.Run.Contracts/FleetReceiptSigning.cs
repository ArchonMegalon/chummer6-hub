using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace Chummer.Run.Contracts.Ledger;

public static class FleetReceiptSigning
{
    public static readonly JsonSerializerOptions SnakeCaseJsonOptions = new(JsonSerializerDefaults.Web)
    {
        PropertyNameCaseInsensitive = true,
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower
    };

    public static ContributionReceiptDto Deserialize(JsonElement payload)
        => JsonSerializer.Deserialize<ContributionReceiptDto>(payload.GetRawText(), SnakeCaseJsonOptions)
           ?? throw new ArgumentException("receipt payload is required.", nameof(payload));

    public static string ComputeHmacSignature(JsonElement payload, string sharedSecret)
    {
        var normalizedSecret = string.IsNullOrWhiteSpace(sharedSecret)
            ? throw new ArgumentException("sharedSecret is required.", nameof(sharedSecret))
            : sharedSecret.Trim();
        var serialized = CanonicalizePayload(payload);
        var digest = HMACSHA256.HashData(Encoding.UTF8.GetBytes(normalizedSecret), Encoding.UTF8.GetBytes(serialized));
        return $"hmac-sha256:{Convert.ToHexString(digest).ToLowerInvariant()}";
    }

    public static bool SignatureEquals(string? left, string? right)
    {
        var leftValue = string.IsNullOrWhiteSpace(left) ? string.Empty : left.Trim();
        var rightValue = string.IsNullOrWhiteSpace(right) ? string.Empty : right.Trim();
        return CryptographicOperations.FixedTimeEquals(
            Encoding.UTF8.GetBytes(leftValue),
            Encoding.UTF8.GetBytes(rightValue));
    }

    private static string CanonicalizePayload(JsonElement payload)
    {
        using var stream = new MemoryStream();
        using var writer = new Utf8JsonWriter(stream);
        WriteCanonical(writer, payload, omitSignedByFleet: true);
        writer.Flush();
        return Encoding.UTF8.GetString(stream.ToArray());
    }

    private static void WriteCanonical(Utf8JsonWriter writer, JsonElement payload, bool omitSignedByFleet)
    {
        switch (payload.ValueKind)
        {
            case JsonValueKind.Object:
                writer.WriteStartObject();
                foreach (var property in payload.EnumerateObject()
                             .Where(property => !(omitSignedByFleet && string.Equals(property.Name, "signed_by_fleet", StringComparison.Ordinal)))
                             .OrderBy(property => property.Name, StringComparer.Ordinal))
                {
                    writer.WritePropertyName(property.Name);
                    WriteCanonical(writer, property.Value, omitSignedByFleet: false);
                }

                writer.WriteEndObject();
                break;
            case JsonValueKind.Array:
                writer.WriteStartArray();
                foreach (var item in payload.EnumerateArray())
                {
                    WriteCanonical(writer, item, omitSignedByFleet: false);
                }

                writer.WriteEndArray();
                break;
            default:
                payload.WriteTo(writer);
                break;
        }
    }
}
