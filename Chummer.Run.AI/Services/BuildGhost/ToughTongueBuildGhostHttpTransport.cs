using Chummer.Run.Contracts.BuildGhost;
using System.Net;
using System.Net.Http.Headers;
using System.Net.Http.Json;

namespace Chummer.Run.AI.Services.BuildGhost;

public sealed class ToughTongueBuildGhostHttpTransport(HttpClient httpClient) : IToughTongueBuildGhostTransport
{
    private const int MaximumResponseBytes = 256 * 1024;
    private readonly HttpClient _httpClient = httpClient ?? throw new ArgumentNullException(nameof(httpClient));

    public async Task<ToughTongueBuildGhostTransportResult> ExplainAsync(
        ToughTongueBuildGhostTransportRequest request,
        string credential,
        CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(request);
        ArgumentException.ThrowIfNullOrWhiteSpace(credential);
        using HttpRequestMessage message = new(HttpMethod.Post, "v1/build-ghost/explain")
        {
            Content = JsonContent.Create(request)
        };
        message.Headers.Authorization = new AuthenticationHeaderValue("Bearer", credential);
        message.Headers.TryAddWithoutValidation("Idempotency-Key", request.IdempotencyKey);
        message.Headers.TryAddWithoutValidation("X-Chummer-Packet-Digest", request.PacketDigest);

        using HttpResponseMessage response = await _httpClient.SendAsync(
            message,
            HttpCompletionOption.ResponseHeadersRead,
            cancellationToken).ConfigureAwait(false);
        if (response.StatusCode == HttpStatusCode.TooManyRequests)
        {
            return new ToughTongueBuildGhostTransportResult(false, "provider-quota-exhausted", null, QuotaExhausted: true);
        }

        if (!response.IsSuccessStatusCode)
        {
            bool retryable = response.StatusCode is HttpStatusCode.RequestTimeout
                or HttpStatusCode.BadGateway
                or HttpStatusCode.ServiceUnavailable
                or HttpStatusCode.GatewayTimeout;
            return new ToughTongueBuildGhostTransportResult(
                false,
                $"provider-http-{(int)response.StatusCode}",
                null,
                Retryable: retryable);
        }

        long? contentLength = response.Content.Headers.ContentLength;
        if (contentLength > MaximumResponseBytes)
        {
            return new ToughTongueBuildGhostTransportResult(false, "provider-response-too-large", null);
        }

        await using Stream stream = await response.Content.ReadAsStreamAsync(cancellationToken).ConfigureAwait(false);
        using MemoryStream buffer = new();
        byte[] chunk = new byte[16 * 1024];
        int read;
        while ((read = await stream.ReadAsync(chunk, cancellationToken).ConfigureAwait(false)) > 0)
        {
            if (buffer.Length + read > MaximumResponseBytes)
            {
                return new ToughTongueBuildGhostTransportResult(false, "provider-response-too-large", null);
            }

            await buffer.WriteAsync(chunk.AsMemory(0, read), cancellationToken).ConfigureAwait(false);
        }

        string json = System.Text.Encoding.UTF8.GetString(buffer.ToArray());
        return new ToughTongueBuildGhostTransportResult(true, "provider-response-received", json);
    }
}
