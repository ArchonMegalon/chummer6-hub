using System.Buffers;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using Chummer.Contracts.Workspaces;

namespace Chummer.Run.Api.Services.InstallLinking;

/// <summary>
/// Lossless transport of Core's workspace snapshot, not a rule/receipt validator
/// or permission to apply remote auxiliary state to a local workspace.
/// </summary>
public static class InstallLinkedWorkspaceSnapshotTransfer
{
    public const string DigestSemantics = "canonical-core-workspace-snapshot-json-sha256-v1";
    public const int MaxSnapshotBytes = 512 * 1024;
    private static readonly JsonSerializerOptions Options = new(JsonSerializerDefaults.Web)
    {
        PropertyNameCaseInsensitive = false,
        UnmappedMemberHandling = JsonUnmappedMemberHandling.Disallow,
        IgnoreReadOnlyProperties = true,
        MaxDepth = 32
    };

    public static JsonElement Encode(WorkspaceDocumentSnapshot snapshot)
        => JsonSerializer.SerializeToElement(snapshot, Options);

    public static string ComputeDigest(JsonElement snapshot)
    {
        ArrayBufferWriter<byte> buffer = new();
        using (Utf8JsonWriter writer = new(buffer))
        {
            writer.WriteStartObject();
            writer.WriteString("contract", DigestSemantics);
            writer.WritePropertyName("snapshot");
            WriteCanonical(snapshot, writer);
            writer.WriteEndObject();
        }
        return Convert.ToHexStringLower(SHA256.HashData(buffer.WrittenSpan));
    }

    public static WorkspaceDocumentSnapshot Decode(JsonElement json)
    {
        // WorkspaceDocument/State have several public constructors. Explicitly
        // reconstruct their Core-owned shape rather than introduce shadow DTOs.
        RequireProperties(json, "id", "document", "lastUpdatedUtc", "contentRevision", "savedRevision");
        JsonElement id = json.GetProperty("id");
        RequireProperties(id, "value");
        JsonElement document = json.GetProperty("document");
        RequireProperties(document, "state", "format");
        JsonElement state = document.GetProperty("state");
        RequireProperties(state, "rulesetId", "schemaVersion", "payloadKind", "payload", "auxiliaryState");
        JsonElement auxiliary = state.GetProperty("auxiliaryState");
        RejectDuplicateProperties(json, 0);
        WorkspaceDocumentAuxiliaryState typedAuxiliary = auxiliary.Deserialize<WorkspaceDocumentAuxiliaryState>(Options)
            ?? throw new JsonException("Auxiliary state is required.");
        // Reject properties a serializer would otherwise silently ignore,
        // including computed read-only properties anywhere in the receipt graph.
        RequirePreservedInput(auxiliary, JsonSerializer.SerializeToElement(typedAuxiliary, Options));
        return new WorkspaceDocumentSnapshot(
            new CharacterWorkspaceId(RequiredString(id, "value")),
            new WorkspaceDocument(new WorkspaceDocumentState(
                RequiredString(state, "rulesetId"), state.GetProperty("schemaVersion").GetInt32(),
                RequiredString(state, "payloadKind"), RequiredString(state, "payload"))
                { AuxiliaryState = typedAuxiliary },
                (WorkspaceDocumentFormat)document.GetProperty("format").GetInt32()),
            json.GetProperty("lastUpdatedUtc").GetDateTimeOffset(),
            json.GetProperty("contentRevision").GetInt64(),
            json.GetProperty("savedRevision").GetInt64());
    }

    public static InstallLinkedWorkspaceSnapshotRecord Validate(InstallLinkedWorkspaceSnapshotRecord record, bool stored = false)
    {
        if (record.WorkspaceSnapshot is null && record.WorkspaceSnapshotDigest is null) return record;
        try
        {
            if (record.WorkspaceSnapshot is not { } json || !IsDigest(record.WorkspaceSnapshotDigest)
                || json.ValueKind != JsonValueKind.Object
                || Encoding.UTF8.GetByteCount(json.GetRawText()) > MaxSnapshotBytes
                || Encoding.UTF8.GetByteCount(record.Payload) + Encoding.UTF8.GetByteCount(json.GetRawText())
                    > InstallLinkedWorkspaceSnapshotService.MaxUpsertRequestBodyBytes)
                throw new JsonException("Invalid or oversized snapshot transport.");
            WorkspaceDocumentSnapshot snapshot = Decode(json);
            if (!string.Equals(snapshot.Id.Value, record.WorkspaceId, StringComparison.Ordinal)
                || !string.Equals(snapshot.Document.RulesetId, record.RulesetId, StringComparison.Ordinal)
                || snapshot.Document.SchemaVersion != record.SchemaVersion || record.SchemaVersion <= 0
                || !string.Equals(snapshot.Document.PayloadKind, record.PayloadKind, StringComparison.Ordinal)
                || !string.Equals(snapshot.Document.Content, record.Payload, StringComparison.Ordinal)
                || !Enum.TryParse(record.Format, out WorkspaceDocumentFormat format)
                || !Enum.IsDefined(snapshot.Document.Format) || snapshot.Document.Format != format
                || snapshot.LastUpdatedUtc == default || snapshot.LastUpdatedUtc != record.UpdatedAtUtc
                || snapshot.ContentRevision <= 0 || snapshot.SavedRevision < 0
                || snapshot.SavedRevision > snapshot.ContentRevision)
                throw new JsonException("Snapshot identity or revisions disagree with the transport.");
            JsonElement encoded = Encode(snapshot);
            if (!string.Equals(ComputeDigest(encoded), record.WorkspaceSnapshotDigest, StringComparison.Ordinal))
                throw new JsonException("Snapshot digest does not match.");
            // Own the bytes independently of the caller's JsonDocument lifetime.
            return record with { WorkspaceSnapshot = encoded };
        }
        catch (Exception ex) when (ex is JsonException or InvalidOperationException or FormatException
            or OverflowException or KeyNotFoundException or ArgumentException or NotSupportedException)
        {
            throw new InstallLinkingOperationException(
                stored ? StatusCodes.Status503ServiceUnavailable : StatusCodes.Status400BadRequest,
                stored ? "The stored complete workspace snapshot is invalid."
                    : "The complete workspace snapshot is unsupported, inconsistent, or exceeds its bounds.");
        }
    }

    private static bool IsDigest(string? value)
        => value is { Length: 64 } && value.All(static c => c is >= '0' and <= '9' or >= 'a' and <= 'f');

    private static string RequiredString(JsonElement json, string name)
        => json.GetProperty(name).GetString() ?? throw new JsonException("A snapshot string is missing.");

    private static void RequireProperties(JsonElement json, params string[] names)
    {
        if (json.ValueKind != JsonValueKind.Object || json.EnumerateObject().Count() != names.Length
            || names.Any(name => !json.TryGetProperty(name, out _)))
            throw new JsonException("Unexpected workspace snapshot shape.");
    }

    private static void RejectDuplicateProperties(JsonElement json, int depth)
    {
        if (depth > 32) throw new JsonException("Workspace snapshot is too deep.");
        if (json.ValueKind == JsonValueKind.Object)
        {
            // The wire contract is case-sensitive. Dictionary keys inside Core
            // state may legitimately differ only by case; preserve both.
            HashSet<string> names = new(StringComparer.Ordinal);
            foreach (JsonProperty property in json.EnumerateObject())
            {
                if (!names.Add(property.Name)) throw new JsonException("Duplicate workspace snapshot property.");
                RejectDuplicateProperties(property.Value, depth + 1);
            }
        }
        else if (json.ValueKind == JsonValueKind.Array)
            foreach (JsonElement item in json.EnumerateArray()) RejectDuplicateProperties(item, depth + 1);
    }

    private static void RequirePreservedInput(JsonElement input, JsonElement output)
    {
        if (input.ValueKind == JsonValueKind.Object && output.ValueKind == JsonValueKind.Object)
        {
            foreach (JsonProperty property in input.EnumerateObject())
            {
                if (!output.TryGetProperty(property.Name, out JsonElement value))
                    throw new JsonException("Workspace state would be discarded.");
                RequirePreservedInput(property.Value, value);
            }
        }
        else if (input.ValueKind == JsonValueKind.Array && output.ValueKind == JsonValueKind.Array)
        {
            if (input.GetArrayLength() != output.GetArrayLength()) throw new JsonException("Workspace state changed.");
            for (int i = 0; i < input.GetArrayLength(); i++) RequirePreservedInput(input[i], output[i]);
        }
        else if (!JsonElement.DeepEquals(input, output)) throw new JsonException("Workspace state changed.");
    }

    private static void WriteCanonical(JsonElement value, Utf8JsonWriter writer)
    {
        if (value.ValueKind == JsonValueKind.Object)
        {
            writer.WriteStartObject();
            foreach (JsonProperty property in value.EnumerateObject().OrderBy(static p => p.Name, StringComparer.Ordinal))
            { writer.WritePropertyName(property.Name); WriteCanonical(property.Value, writer); }
            writer.WriteEndObject();
        }
        else if (value.ValueKind == JsonValueKind.Array)
        {
            writer.WriteStartArray();
            foreach (JsonElement item in value.EnumerateArray()) WriteCanonical(item, writer);
            writer.WriteEndArray();
        }
        else value.WriteTo(writer);
    }
}
