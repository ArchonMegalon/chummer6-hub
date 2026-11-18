using System.Net;
using System.Net.Http.Headers;
using System.Net.Sockets;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace Chummer.Run.Api.Services.Community;

public interface IOriginSceneAccountErasure
{
    void EnsureAccountErasureSupported();
    int EraseForSubject(string subjectId);
}

/// <summary>
/// Private local Docker bridge; never a provider client or public download URL.
/// User/install authorization stays in Hub. Media owns rendering and retained bytes.
/// </summary>
public sealed class OriginSceneMediaClient(IConfiguration configuration) : IOriginSceneAccountErasure
{
    private static readonly JsonSerializerOptions Json = new(JsonSerializerDefaults.Web);
    private const int MaximumResponseBytes = 6 * 1024 * 1024;
    public bool IsConfigured => !string.IsNullOrEmpty(configuration["CHUMMER_ORIGIN_SCENE_MEDIA_SOCKET"])
        || !string.IsNullOrEmpty(configuration["CHUMMER_ORIGIN_SCENE_MEDIA_TOKEN_FILE"])
        || configuration["CHUMMER_ORIGIN_SCENE_MEDIA_REQUIRED"] == "true";

    public void EnsureAccountErasureSupported()
    {
        if (!IsConfigured) return; // Never-enabled deployments have no scene volume.
        JsonElement response = SendAsync("health", new { }, 4096, CancellationToken.None).GetAwaiter().GetResult();
        if (response.GetProperty("schema").GetString() != "chummer.media.origin-scene-worker/v1"
            || !response.GetProperty("accountErasureSupported").GetBoolean())
            throw new InvalidOperationException("Private scene erasure is unavailable.");
    }

    public int EraseForSubject(string subjectId)
    {
        if (!IsConfigured) return 0;
        string owner = OwnerDigest(subjectId);
        JsonElement response = SendAsync("erase-owner", new { OwnerDigest = owner }, 4096, CancellationToken.None)
            .GetAwaiter().GetResult();
        if (response.GetProperty("ownerDigest").GetString() != owner
            || !response.GetProperty("recordsRemoved").TryGetInt32(out int count) || count < 0)
            throw new InvalidDataException("Private scene erasure returned an invalid result.");
        return count;
    }

    public Task<JsonElement> ReadAsync(string subjectId, string assetId, Func<bool> stillAuthorized, CancellationToken ct)
    {
        RequireDigest(assetId);
        return WithOwnerAsync("read", new { OwnerDigest = OwnerDigest(subjectId), AssetId = assetId }, stillAuthorized, ct);
    }

    public async Task EnsureDispatchAvailableAsync(CancellationToken ct)
    {
        var response = await SendAsync("health", new { }, 4096, ct);
        if (response.GetProperty("schema").GetString() != "chummer.media.origin-scene-worker/v1"
            || !response.GetProperty("accountErasureSupported").GetBoolean()
            || !response.GetProperty("dispatchEnabled").GetBoolean())
            throw new InvalidOperationException("Private scene dispatch is unavailable; retained images remain readable.");
    }

    public Task<JsonElement> DecideAsync(string subjectId, string assetId, string expectedHash, bool approve,
        bool explicitlyConfirmed, Func<bool> stillAuthorized, CancellationToken ct)
    {
        RequireDigest(assetId);
        RequireDigest(expectedHash);
        if (!explicitlyConfirmed) throw new ArgumentException("Explicit image review is required.");
        return WithOwnerAsync("decide", new { OwnerDigest = OwnerDigest(subjectId), AssetId = assetId,
            ExpectedHash = expectedHash, Approve = approve, ExplicitlyConfirmed = true }, stillAuthorized, ct);
    }

    public Task<JsonElement> RenderAsync(string subjectId, HorizonArtifactRequestReceipt admitted,
        Func<bool> stillAuthorized, CancellationToken ct)
    {
        string owner = OwnerDigest(subjectId);
        // This method accepts an actual Hub receipt, not arbitrary phone input.
        // A compose-only receipt (Quota == null) cannot execute a paid job.
        if (admitted.Status != "accepted" || admitted.Quota is null || !admitted.ExternalProcessingConsent
            || admitted.Visibility != "private" || admitted.CapabilityId != "origin-dossier-media"
            || admitted.GovernedRenderRequest is not { } contract || contract.RequestedBy != "origin-owner:" + owner
            || contract.SourceRef != admitted.SourceRef || !admitted.SourceRef.StartsWith("origin-dossier:scene:", StringComparison.Ordinal))
            throw new InvalidOperationException("An exact consented, quota-admitted private scene receipt is required.");
        string receiptDigest = Convert.ToHexStringLower(SHA256.HashData(JsonSerializer.SerializeToUtf8Bytes(admitted, Json)));
        return WithOwnerAsync("render", new { OwnerDigest = owner, Contract = contract, AdmissionDigest = receiptDigest }, stillAuthorized, ct);
    }

    private async Task<JsonElement> WithOwnerAsync(string operation, object packet, Func<bool> current, CancellationToken ct)
    {
        if (!current()) throw new UnauthorizedAccessException();
        JsonElement result = await SendAsync(operation, packet, MaximumResponseBytes, ct);
        if (!current()) throw new UnauthorizedAccessException();
        return result;
    }

    private async Task<JsonElement> SendAsync(string operation, object packet, int maximumBytes, CancellationToken ct)
    {
        if (!OperatingSystem.IsLinux()) throw new InvalidOperationException("Private media uses the local Linux Docker socket.");
        string? socketPath = configuration["CHUMMER_ORIGIN_SCENE_MEDIA_SOCKET"];
        string? tokenPath = configuration["CHUMMER_ORIGIN_SCENE_MEDIA_TOKEN_FILE"];
        if (socketPath is null || tokenPath is null || !Path.IsPathFullyQualified(socketPath)
            || !Path.IsPathFullyQualified(tokenPath) || new FileInfo(tokenPath).LinkTarget is not null
            || ((int)File.GetUnixFileMode(tokenPath) & 0x3f) != 0)
            throw new InvalidOperationException("Private media requires its socket and dedicated private token file.");
        byte[] tokenBytes;
        using (var file = File.OpenRead(tokenPath))
        {
            if (file.Length is < 32 or > 256) throw new InvalidOperationException("Invalid private media token file.");
            tokenBytes = new byte[(int)file.Length];
            file.ReadExactly(tokenBytes);
        }
        try
        {
            if (tokenBytes.Any(static value => value is < 33 or > 126)) throw new InvalidOperationException("Invalid private media token.");
            using var timeout = CancellationTokenSource.CreateLinkedTokenSource(ct);
            timeout.CancelAfter(TimeSpan.FromSeconds(operation == "render" ? 120 : 15));
            using var handler = new SocketsHttpHandler
            {
                AllowAutoRedirect = false, UseProxy = false, UseCookies = false, AutomaticDecompression = DecompressionMethods.None,
                ConnectCallback = async (_, cancellation) =>
                {
                    var socket = new Socket(AddressFamily.Unix, SocketType.Stream, ProtocolType.Unspecified);
                    try
                    {
                        await socket.ConnectAsync(new UnixDomainSocketEndPoint(socketPath), cancellation);
                        return new NetworkStream(socket, ownsSocket: true);
                    }
                    catch { socket.Dispose(); throw; }
                }
            };
            using var http = new HttpClient(handler) { Timeout = Timeout.InfiniteTimeSpan };
            using var request = new HttpRequestMessage(HttpMethod.Post, "http://origin-scene-worker/v1/" + operation);
            request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", Encoding.ASCII.GetString(tokenBytes));
            byte[] body = JsonSerializer.SerializeToUtf8Bytes(packet, Json);
            if (body.Length > 64 * 1024) throw new ArgumentException("Scene request is too large.");
            request.Content = new ByteArrayContent(body);
            request.Content.Headers.ContentType = new MediaTypeHeaderValue("application/json");
            using var response = await http.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, timeout.Token);
            // Do not materialize/log error bodies, redirect URLs or provider details.
            if (response.StatusCode == HttpStatusCode.Forbidden) throw new UnauthorizedAccessException();
            if (response.StatusCode == HttpStatusCode.NotFound) throw new KeyNotFoundException();
            if (response.StatusCode != HttpStatusCode.OK || response.Content.Headers.ContentType?.MediaType != "application/json"
                || response.Content.Headers.ContentLength > maximumBytes)
                throw new InvalidDataException("Private media response is unavailable or oversized; read the same request before retrying.");
            using Stream input = await response.Content.ReadAsStreamAsync(timeout.Token);
            using var bounded = new MemoryStream();
            byte[] buffer = new byte[8192];
            while (true)
            {
                int read = await input.ReadAsync(buffer.AsMemory(0, Math.Min(buffer.Length, maximumBytes + 1 - (int)bounded.Length)), timeout.Token);
                if (read == 0) break;
                bounded.Write(buffer, 0, read);
                if (bounded.Length > maximumBytes) throw new InvalidDataException("Private media response is oversized.");
            }
            using var document = JsonDocument.Parse(bounded.ToArray(), new() { MaxDepth = 32 });
            return document.RootElement.Clone();
        }
        finally { CryptographicOperations.ZeroMemory(tokenBytes); }
    }

    private static string OwnerDigest(string subject)
    {
        if (string.IsNullOrWhiteSpace(subject) || subject.Contains('\0') || Encoding.UTF8.GetByteCount(subject) > 256)
            throw new ArgumentException("Invalid scene owner.");
        return Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(subject)));
    }

    private static void RequireDigest(string value)
    {
        if (value is not { Length: 64 } || value.Any(static c => c is not (>= '0' and <= '9') and not (>= 'a' and <= 'f')))
            throw new ArgumentException("A canonical scene digest is required.");
    }
}
