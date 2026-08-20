using Chummer.Run.Contracts.BuildGhost;
namespace Chummer.Run.AI.Services.BuildGhost;

public sealed class ToughTongueBuildGhostHttpTransport(HttpClient httpClient) : IToughTongueBuildGhostTransport
{
    private readonly HttpClient _httpClient = httpClient ?? throw new ArgumentNullException(nameof(httpClient));

    public Task<ToughTongueBuildGhostTransportResult> ExplainAsync(
        ToughTongueBuildGhostTransportRequest request,
        string credential,
        CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(request);
        ArgumentException.ThrowIfNullOrWhiteSpace(credential);
        cancellationToken.ThrowIfCancellationRequested();
        _ = _httpClient.BaseAddress;
        return Task.FromResult(new ToughTongueBuildGhostTransportResult(
            false,
            "provider-interactive-session-required",
            null));
    }
}
