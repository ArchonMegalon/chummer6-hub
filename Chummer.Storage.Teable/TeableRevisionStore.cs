using System.Net;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text;

namespace Chummer.Storage.Teable;

/// <summary>
/// Remote, append-only primary bytes. A UNIQUE, NOT NULL revision_key admits
/// exactly one successor. No check-then-PATCH and no local fallback. This is not
/// a read-lock/lease provider; callers must not infer revocation fencing from it.
/// </summary>
public sealed class TeableRevisionStore(HttpClient client, string tableId, string token) : IDisposable
{
    private bool _ownsClient;
    internal const int ChunkBytes = 32 * 1024;
    internal const int MaximumBytes = 64 * 1024 * 1024 + 64; // Includes a bounded store-specific header.
    private const int MaximumResponseBytes = 256 * 1024;
    private static readonly JsonSerializerOptions Json = new(JsonSerializerDefaults.Web) { MaxDepth = 12 };
    private string TablePath => ValidId(tableId, "tbl") ? $"api/table/{tableId}" : throw Invalid();

    public sealed record Head(long Revision, Guid Commit, string Sha256, byte[] Bytes);
    private sealed record Manifest(int Version, string Stream, long Revision, Guid Commit,
        string? PreviousSha256, int Length, string Sha256, int Chunks, string? InlineBase64 = null);

    public static TeableRevisionStore Open(Uri origin, string tableId, string token)
    {
        if (origin is not { IsAbsoluteUri: true, Scheme: "https", AbsolutePath: "/", UserInfo: "", Query: "", Fragment: "" }
            || !ValidId(tableId, "tbl") || string.IsNullOrWhiteSpace(token) || token.Length > 4096 || token.Any(char.IsControl))
            throw Invalid();
        var client = new HttpClient(new HttpClientHandler { AllowAutoRedirect = false, UseCookies = false })
            { BaseAddress = origin, Timeout = TimeSpan.FromSeconds(15) };
        return new(client, tableId, token) { _ownsClient = true };
    }

    public void Dispose() { if (_ownsClient) client.Dispose(); }

    public static TeableRevisionStore OpenFromPrivateTokenFile(Uri origin, string tableId, string tokenFile)
    {
        if (!Path.IsPathFullyQualified(tokenFile)) throw Invalid();
        LinuxSecureFile.ValidateExistingDirectory(Path.GetDirectoryName(tokenFile)!, ownerOnly: false, readOnlyFileSystem: false);
        byte[] bytes = LinuxSecureFile.ReadOwnerOnlyRegularFile(tokenFile, 4098, repairOwnerMode: false);
        try
        {
            string token = new UTF8Encoding(false, true).GetString(bytes).TrimEnd('\r', '\n');
            if (token.Any(c => c < '!' || c > '~')) throw Invalid();
            return Open(origin, tableId, token);
        }
        finally { CryptographicOperations.ZeroMemory(bytes); }
    }

    public async Task VerifySchemaAsync(CancellationToken ct = default)
    {
        using JsonDocument document = await GetAsync($"{TablePath}/field", ct);
        JsonElement[] fields = document.RootElement.EnumerateArray().ToArray();
        foreach ((string name, string type) in new[] { ("revision_key", "singleLineText"),
                     ("stream", "singleLineText"), ("kind", "singleLineText"),
                     ("revision", "number"), ("payload", "longText") })
        {
            JsonElement[] matches = fields.Where(f => f.GetProperty("name").GetString() == name).ToArray();
            if (matches.Length != 1 || matches[0].GetProperty("type").GetString() != type
                || name == "revision_key" && (!True(matches[0], "unique") || !True(matches[0], "notNull")))
                throw Invalid();
        }
    }

    public async Task<Head?> ReadAsync(string stream, CancellationToken ct = default)
    {
        ValidateStream(stream);
        JsonElement? record = await FindAsync(new[] { ("stream", stream), ("kind", "head") }, latest: true, ct);
        return record is null ? null : await DecodeAsync(record.Value, stream, ct);
    }

    // A lost response is never repaired by replaying POST. Read back the unique
    // successor: return our exact commit, report conflict, or leave uncertainty.
    public async Task<Head> CompareExchangeAsync(string stream, Head? expected, Guid commit,
        ReadOnlyMemory<byte> bytes, CancellationToken ct = default)
    {
        ValidateStream(stream);
        if (commit == Guid.Empty || bytes.Length is < 1 or > MaximumBytes) throw Invalid();
        await VerifySchemaAsync(ct);
        Head? current = await ReadAsync(stream, ct);
        long revision = checked((expected?.Revision ?? 0) + 1);
        if (revision > 9_007_199_254_740_991L) throw Invalid(); // Teable number is a JS double.
        string hash = Hash(bytes.Span);
        if (current is not null && current.Revision == revision && current.Commit == commit && current.Sha256 == hash)
            return current;
        if (!Matches(current, expected)) throw new TeableRevisionConflictException();

        int count = (bytes.Length + ChunkBytes - 1) / ChunkBytes;
        for (int index = 0; index < count; index++)
        {
            var part = bytes.Slice(index * ChunkBytes, Math.Min(ChunkBytes, bytes.Length - index * ChunkBytes));
            string key = ChunkKey(stream, commit, index);
            string payload = Convert.ToBase64String(part.Span);
            await CreateOnceAsync(key, stream, "chunk", revision, payload, ct);
        }
        // Small states fit in the unique head itself, eliminating a dependent
        // HTTP read on every fresh authorization check. Keep v1 chunks as well:
        // existing readers can ignore this optional field during rollback.
        // This is current remote data, not a cached authorization decision.
        var manifest = new Manifest(1, stream, revision, commit, expected?.Sha256, bytes.Length, hash, count,
            bytes.Length <= ChunkBytes ? Convert.ToBase64String(bytes.Span) : null);
        string manifestKey = HeadKey(stream, revision);
        await CreateOnceAsync(manifestKey, stream, "head", revision, JsonSerializer.Serialize(manifest, Json), ct);
        JsonElement? winner = await FindAsync(new[] { ("revision_key", manifestKey) }, latest: false, ct);
        if (winner is null) throw new IOException("Teable commit acknowledgement is unavailable; reconcile before retry.");
        Head result = await DecodeAsync(winner.Value, stream, ct);
        if (result.Revision != revision || result.Commit != commit || result.Sha256 != hash)
            throw new TeableRevisionConflictException();
        return result;
    }

    private async Task CreateOnceAsync(string key, string stream, string kind, long revision, string payload,
        CancellationToken ct)
    {
        using HttpRequestMessage request = Request(HttpMethod.Post, $"{TablePath}/record");
        request.Content = JsonContent.Create(new { fieldKeyType = "name", records = new[] { new { fields =
            new Dictionary<string, object> { ["revision_key"] = key, ["stream"] = stream,
                ["kind"] = kind, ["revision"] = revision, ["payload"] = payload } } } }, options: Json);
        try
        {
            using HttpResponseMessage response = await client.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, ct);
            // Successful responses can be large/hostile too. Bound before parsing.
            if (response.StatusCode == HttpStatusCode.Created)
            {
                using JsonDocument ignored = await ReadJsonAsync(response, ct);
                return;
            }
            if (response.StatusCode is not (HttpStatusCode.BadRequest or HttpStatusCode.Conflict))
                throw new IOException("Teable write failed; reconcile before retry.");
        }
        catch (HttpRequestException)
        {
            // Do not log the HTTP exception: diagnostics may contain request data.
        }
        JsonElement? existing = await FindAsync(new[] { ("revision_key", key) }, latest: false, ct);
        if (existing is null) throw new IOException("Teable write was not acknowledged; reconcile before retry.");
        JsonElement fields = existing.Value.GetProperty("fields");
        if (fields.GetProperty("payload").GetString() != payload || fields.GetProperty("stream").GetString() != stream
            || fields.GetProperty("kind").GetString() != kind || fields.GetProperty("revision").GetInt64() != revision)
            throw new TeableRevisionConflictException();
    }

    private async Task<Head> DecodeAsync(JsonElement record, string stream, CancellationToken ct)
    {
        JsonElement fields = record.GetProperty("fields");
        string payload = fields.GetProperty("payload").GetString() ?? throw Invalid();
        Manifest manifest = JsonSerializer.Deserialize<Manifest>(payload, Json) ?? throw Invalid();
        if (manifest.Version != 1 || manifest.Stream != stream || manifest.Revision < 1
            || manifest.Revision > 9_007_199_254_740_991L || manifest.Commit == Guid.Empty
            || manifest.Length is < 1 or > MaximumBytes || !Digest(manifest.Sha256)
            || manifest.Revision == 1 && manifest.PreviousSha256 is not null
            || manifest.Revision > 1 && !Digest(manifest.PreviousSha256)
            || manifest.Chunks != (manifest.Length + ChunkBytes - 1) / ChunkBytes
            || manifest.InlineBase64 is not null && manifest.Length > ChunkBytes
            || fields.GetProperty("revision_key").GetString() != HeadKey(stream, manifest.Revision)
            || fields.GetProperty("stream").GetString() != stream || fields.GetProperty("kind").GetString() != "head"
            || fields.GetProperty("revision").GetInt64() != manifest.Revision)
            throw Invalid();

        byte[] bytes = new byte[manifest.Length];
        try
        {
            if (manifest.InlineBase64 is not null)
            {
                // Malformed inline bytes must not fall back to a different
                // representation. Both formats use the same exact length/hash.
                if (!Convert.TryFromBase64String(manifest.InlineBase64, bytes, out int used)
                    || used != manifest.Length) throw Invalid();
            }
            else for (int index = 0; index < manifest.Chunks; index++)
            {
                string key = ChunkKey(stream, manifest.Commit, index);
                JsonElement part = await FindAsync(new[] { ("revision_key", key) }, latest: false, ct) ?? throw Invalid();
                JsonElement values = part.GetProperty("fields");
                if (values.GetProperty("stream").GetString() != stream || values.GetProperty("kind").GetString() != "chunk"
                    || values.GetProperty("revision").GetInt64() != manifest.Revision) throw Invalid();
                int length = Math.Min(ChunkBytes, manifest.Length - index * ChunkBytes);
                if (!Convert.TryFromBase64String(values.GetProperty("payload").GetString() ?? "",
                        bytes.AsSpan(index * ChunkBytes, length), out int used) || used != length) throw Invalid();
            }
            if (Hash(bytes) != manifest.Sha256) throw Invalid();
            return new(manifest.Revision, manifest.Commit, manifest.Sha256, bytes);
        }
        catch { CryptographicOperations.ZeroMemory(bytes); throw; }
    }

    private async Task<JsonElement?> FindAsync((string Field, string Value)[] predicates, bool latest, CancellationToken ct)
    {
        string filter = JsonSerializer.Serialize(new { conjunction = "and", filterSet = predicates.Select(p =>
            new { fieldId = p.Field, @operator = "is", value = p.Value }) });
        string query = $"fieldKeyType=name&take={(latest ? 1 : 2)}&filter={Uri.EscapeDataString(filter)}";
        if (latest) query += "&orderBy=" + Uri.EscapeDataString("[{\"fieldId\":\"revision\",\"order\":\"desc\"}]");
        using JsonDocument document = await GetAsync($"{TablePath}/record?{query}", ct);
        JsonElement records = document.RootElement.GetProperty("records");
        if (records.GetArrayLength() > 1) throw Invalid();
        if (records.GetArrayLength() == 0) return null;
        JsonElement row = records[0];
        foreach (var predicate in predicates)
            if (row.GetProperty("fields").GetProperty(predicate.Field).GetString() != predicate.Value) throw Invalid();
        return row.Clone();
    }

    private async Task<JsonDocument> GetAsync(string path, CancellationToken ct)
    {
        using var request = Request(HttpMethod.Get, path);
        using var response = await client.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, ct);
        if (response.StatusCode != HttpStatusCode.OK) throw new IOException("Teable primary read failed.");
        return await ReadJsonAsync(response, ct);
    }

    private HttpRequestMessage Request(HttpMethod method, string path)
    {
        if (client.BaseAddress is not { Scheme: "https", AbsolutePath: "/", UserInfo: "" }
            || string.IsNullOrWhiteSpace(token)) throw Invalid();
        var request = new HttpRequestMessage(method, path);
        request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", token);
        return request;
    }

    private static async Task<JsonDocument> ReadJsonAsync(HttpResponseMessage response, CancellationToken ct)
    {
        if (response.Content.Headers.ContentLength > MaximumResponseBytes) throw Invalid();
        using var stream = await response.Content.ReadAsStreamAsync(ct);
        byte[] bytes = new byte[MaximumResponseBytes + 1];
        try
        {
            int used = 0, read;
            while (used < bytes.Length && (read = await stream.ReadAsync(bytes.AsMemory(used), ct)) != 0) used += read;
            if (used > MaximumResponseBytes) throw Invalid();
            // Parse(Stream) owns a copy; Parse(ReadOnlyMemory) would retain the
            // buffer that we deliberately clear in finally.
            using var buffered = new MemoryStream(bytes, 0, used, writable: false);
            return JsonDocument.Parse(buffered, new JsonDocumentOptions { MaxDepth = 16 });
        }
        finally { CryptographicOperations.ZeroMemory(bytes); }
    }

    private static bool True(JsonElement field, string name)
        => field.TryGetProperty(name, out JsonElement value) && value.ValueKind == JsonValueKind.True;
    private static bool Matches(Head? a, Head? b)
        => a is null ? b is null : b is not null && a.Revision == b.Revision && a.Commit == b.Commit && a.Sha256 == b.Sha256;
    private static string HeadKey(string stream, long revision) => $"{stream}:head:{revision}";
    private static string ChunkKey(string stream, Guid commit, int index) => $"{stream}:chunk:{commit:N}:{index}";
    private static bool ValidId(string id, string prefix)
        => id.Length == 19 && id.StartsWith(prefix, StringComparison.Ordinal) && id.All(char.IsAsciiLetterOrDigit);
    private static void ValidateStream(string stream)
    {
        if (stream.Length is < 1 or > 128 || stream.Any(c => !char.IsAsciiLetterOrDigit(c) && c is not ('-' or '_')))
            throw Invalid();
    }
    private static bool Digest(string? value)
        => value is { Length: 64 } && value.All(c => c is >= '0' and <= '9' or >= 'a' and <= 'f');
    private static string Hash(ReadOnlySpan<byte> bytes) => Convert.ToHexStringLower(SHA256.HashData(bytes));
    private static InvalidDataException Invalid() => new("Teable primary storage contract is invalid.");
}

public sealed class TeableRevisionConflictException() : IOException("The remote state changed; reload before a new command.");
