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
    private static readonly UTF8Encoding StrictUtf8 = new(false, true);
    private static readonly JsonSerializerOptions Options = new(JsonSerializerDefaults.Web)
    {
        PropertyNameCaseInsensitive = false,
        UnmappedMemberHandling = JsonUnmappedMemberHandling.Disallow,
        IgnoreReadOnlyProperties = true,
        MaxDepth = 32
    };

    public static JsonElement Encode(WorkspaceDocumentSnapshot snapshot)
        => JsonSerializer.SerializeToElement(snapshot, Options);

    /// <summary>
    /// Versioned carrier binding shared with Android's account-owner authority.
    /// The exact authenticated subject is neither trimmed nor case-folded. This
    /// derives a storage identity, not a credential or a local restore admission.
    /// Legacy desktop owner identifiers require explicit migration, not relabeling.
    /// </summary>
    public static string ComputeContinuationOwnerId(string subjectId)
    {
        if (string.IsNullOrEmpty(subjectId))
            throw new ArgumentException("A full continuation requires an exact authenticated subject.", nameof(subjectId));
        return "install-account-v1:" + Convert.ToHexStringLower(SHA256.HashData(
            StrictUtf8.GetBytes("chummer-install-account-owner-v1\0" + subjectId)));
    }

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

    public static InstallLinkedWorkspaceSnapshotRecord Validate(InstallLinkedWorkspaceSnapshotRecord record,
        bool stored = false, string? expectedContinuationOwnerId = null)
    {
        if (record.WorkspaceContinuation is not null || record.WorkspaceContinuationDigest is not null)
            return ValidateContinuation(record, stored, expectedContinuationOwnerId);
        if (record.WorkspaceSnapshot is null && record.WorkspaceSnapshotDigest is null) return record;
        try
        {
            if (record.WorkspaceSnapshot is not { } json || !IsDigest(record.WorkspaceSnapshotDigest)
                || json.ValueKind != JsonValueKind.Object
                || (!stored && !IsWithinTransportBounds(record.Payload, json)))
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
            // Persistence adds indentation to JsonElement values. That whitespace
            // must not invalidate an already accepted snapshot after restart.
            // Conversely, a compact Unicode/sparse request may expand during our
            // canonical encoding. Check that stable representation before writing
            // and on every cold read; request-byte limits remain independent.
            if (!IsWithinTransportBounds(record.Payload, encoded))
                throw new JsonException("Canonical snapshot exceeds transport bounds.");
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

    private static InstallLinkedWorkspaceSnapshotRecord ValidateContinuation(
        InstallLinkedWorkspaceSnapshotRecord record, bool stored, string? expectedOwnerId)
    {
        try
        {
            if (record.WorkspaceContinuation is not { ValueKind: JsonValueKind.Object } json
                || !IsDigest(record.WorkspaceContinuationDigest) || string.IsNullOrWhiteSpace(expectedOwnerId))
                throw new JsonException("Full continuation and its authenticated owner are required.");

            // Stored JsonElements acquire indentation. Only incoming requests
            // have a raw byte cap; cold reads still enforce the same compact and
            // Core-canonical caps before exposing any saved history.
            byte[] bytes;
            if (stored)
                bytes = CompactContinuation(json);
            else
            {
                string raw = json.GetRawText();
                if (Encoding.UTF8.GetByteCount(raw) > MaxSnapshotBytes
                    || !WithinCombinedBounds(record, json))
                    throw new JsonException("Raw continuation exceeds transport bounds.");
                bytes = Encoding.UTF8.GetBytes(raw);
            }
            if (!WorkspaceContinuationCodec.TryDecodeCandidate(bytes, MaxSnapshotBytes, out var decoded)
                || !string.Equals(decoded.SnapshotDigest, record.WorkspaceContinuationDigest, StringComparison.Ordinal)
                || !string.Equals(decoded.Snapshot.OwnerId, expectedOwnerId, StringComparison.Ordinal))
                throw new JsonException("Core continuation or authenticated owner binding is invalid.");

            WorkspaceDocumentSnapshot workspace = decoded.Snapshot.Workspace;
            if (!string.Equals(workspace.Id.Value, record.WorkspaceId, StringComparison.Ordinal)
                || !string.Equals(workspace.Document.RulesetId, record.RulesetId, StringComparison.Ordinal)
                || workspace.Document.SchemaVersion != record.SchemaVersion
                || !string.Equals(workspace.Document.PayloadKind, record.PayloadKind, StringComparison.Ordinal)
                || !string.Equals(workspace.Document.Content, record.Payload, StringComparison.Ordinal)
                || !Enum.TryParse(record.Format, out WorkspaceDocumentFormat format)
                || workspace.Document.Format != format
                || workspace.LastUpdatedUtc == default || !workspace.LastUpdatedUtc.EqualsExact(record.UpdatedAtUtc))
                throw new JsonException("Continuation and public workspace projection disagree.");

            InstallLinkedWorkspaceSnapshotRecord validated = Validate(record with
            {
                WorkspaceContinuation = null,
                WorkspaceContinuationDigest = null
            }, stored);
            if (validated.WorkspaceSnapshot is { } projection
                && !JsonElement.DeepEquals(Encode(workspace), projection))
                throw new JsonException("The legacy projection does not exactly match the full continuation.");

            byte[] canonical = WorkspaceContinuationCodec.Encode(decoded, MaxSnapshotBytes);
            using JsonDocument captured = JsonDocument.Parse(canonical, new JsonDocumentOptions { MaxDepth = 128 });
            JsonElement owned = captured.RootElement.Clone();
            if (!WithinCombinedBounds(validated, owned))
                throw new JsonException("Canonical continuation exceeds combined transport bounds.");
            // Clone the actual full Core envelope. No receipt/history filtering,
            // source validation, local restore admission or replay grant occurs.
            return validated with
            {
                WorkspaceContinuation = owned,
                WorkspaceContinuationDigest = decoded.SnapshotDigest
            };
        }
        catch (Exception ex) when (ex is JsonException or InvalidOperationException or FormatException
            or OverflowException or KeyNotFoundException or ArgumentException or NotSupportedException)
        {
            throw new InstallLinkingOperationException(
                stored ? StatusCodes.Status503ServiceUnavailable : StatusCodes.Status400BadRequest,
                stored ? "The stored full workspace continuation is invalid."
                    : "The full workspace continuation is unsupported, inconsistent, or exceeds its bounds.");
        }
    }

    private static bool WithinCombinedBounds(InstallLinkedWorkspaceSnapshotRecord record, JsonElement continuation)
    {
        long count = Encoding.UTF8.GetByteCount(record.Payload)
            + (long)Encoding.UTF8.GetByteCount(continuation.GetRawText());
        if (record.WorkspaceSnapshot is { } projection)
            count += Encoding.UTF8.GetByteCount(projection.GetRawText());
        return count <= InstallLinkedWorkspaceSnapshotService.MaxUpsertRequestBodyBytes;
    }

    private static byte[] CompactContinuation(JsonElement json)
    {
        using BoundedContinuationBuffer buffer = new();
        using (Utf8JsonWriter writer = new(buffer, new JsonWriterOptions { MaxDepth = 128 }))
            json.WriteTo(writer);
        return buffer.ToArray();
    }

    private sealed class BoundedContinuationBuffer : MemoryStream
    {
        public override void Write(byte[] buffer, int offset, int count)
        {
            RequireCapacity(count);
            base.Write(buffer, offset, count);
        }

        public override void Write(ReadOnlySpan<byte> buffer)
        {
            RequireCapacity(buffer.Length);
            base.Write(buffer);
        }

        public override void WriteByte(byte value)
        {
            RequireCapacity(1);
            base.WriteByte(value);
        }

        private void RequireCapacity(int additionalBytes)
        {
            if (additionalBytes > MaxSnapshotBytes - Position)
                throw new JsonException("Compact continuation exceeds transport bounds.");
        }
    }

    private static bool IsWithinTransportBounds(string payload, JsonElement json)
    {
        int snapshotBytes = Encoding.UTF8.GetByteCount(json.GetRawText());
        return snapshotBytes <= MaxSnapshotBytes
            && (long)Encoding.UTF8.GetByteCount(payload) + snapshotBytes
                <= InstallLinkedWorkspaceSnapshotService.MaxUpsertRequestBodyBytes;
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
