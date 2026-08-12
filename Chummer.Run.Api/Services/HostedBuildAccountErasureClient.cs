using System.Net.Http.Json;

namespace Chummer.Run.Api.Services;

public sealed record HostedBuildAccountErasureResult(
    bool Erased,
    int WorkspaceRowsRemoved,
    string ReceiptSha256);

public interface IHostedBuildAccountErasureClient
{
    Task<HostedBuildAccountErasureResult> EraseOwnerWorkspacesAsync(
        string subjectId,
        CancellationToken cancellationToken);
}

public sealed class HostedBuildAccountErasureClient : IHostedBuildAccountErasureClient
{
    private readonly HttpClient _httpClient;
    private readonly IConfiguration _configuration;
    private readonly ILogger<HostedBuildAccountErasureClient> _logger;

    public HostedBuildAccountErasureClient(
        HttpClient httpClient,
        IConfiguration configuration,
        ILogger<HostedBuildAccountErasureClient> logger)
    {
        _httpClient = httpClient;
        _configuration = configuration;
        _logger = logger;
    }

    public async Task<HostedBuildAccountErasureResult> EraseOwnerWorkspacesAsync(
        string subjectId,
        CancellationToken cancellationToken)
    {
        string normalizedSubject = string.IsNullOrWhiteSpace(subjectId)
            ? throw new ArgumentException("subjectId is required.", nameof(subjectId))
            : subjectId.Trim();
        string? baseUrl = NormalizeOptional(_configuration["CHUMMER_HOSTED_BUILD_BASE_URL"]);
        string? adminKey = NormalizeOptional(_configuration["CHUMMER_HOSTED_BUILD_PRIVACY_ADMIN_KEY"]);
        if (baseUrl is null || adminKey is null)
        {
            _logger.LogError(
                "Whole-account erasure is blocked because the first-party Hosted Build privacy bridge is not configured.");
            throw new HubRequestAuthException(
                StatusCodes.Status503ServiceUnavailable,
                "Account erasure is unavailable right now. Try again later.");
        }

        HttpResponseMessage response;
        try
        {
            using var request = new HttpRequestMessage(
                HttpMethod.Delete,
                $"{baseUrl.TrimEnd('/')}/api/internal/v1/privacy/owners/{Uri.EscapeDataString(normalizedSubject)}/workspaces");
            request.Headers.Add("X-Chummer-Privacy-Admin-Key", adminKey);
            response = await _httpClient.SendAsync(request, cancellationToken);
        }
        catch (HttpRequestException ex)
        {
            _logger.LogWarning(ex, "Hosted Build owner-workspace erasure request failed.");
            throw Unavailable();
        }
        catch (TaskCanceledException ex) when (!cancellationToken.IsCancellationRequested)
        {
            _logger.LogWarning(ex, "Hosted Build owner-workspace erasure request timed out.");
            throw Unavailable();
        }

        using (response)
        {
            if (!response.IsSuccessStatusCode)
            {
                string detail = await SafeReadBodyAsync(response, cancellationToken);
                _logger.LogError(
                    "Hosted Build owner-workspace erasure returned status {StatusCode}. Detail: {Detail}",
                    (int)response.StatusCode,
                    string.IsNullOrWhiteSpace(detail) ? "<empty>" : detail);
                throw Unavailable();
            }

            try
            {
                HostedBuildAccountErasureResult? result =
                    await response.Content.ReadFromJsonAsync<HostedBuildAccountErasureResult>(cancellationToken: cancellationToken);
                return result ?? throw new System.Text.Json.JsonException("Hosted Build erasure returned an empty payload.");
            }
            catch (Exception ex) when (ex is System.Text.Json.JsonException or NotSupportedException)
            {
                _logger.LogError(ex, "Hosted Build owner-workspace erasure returned an unreadable payload.");
                throw Unavailable();
            }
        }
    }

    private static HubRequestAuthException Unavailable()
        => new(
            StatusCodes.Status503ServiceUnavailable,
            "Account erasure is unavailable right now. Try again later.");

    private static string? NormalizeOptional(string? value)
        => string.IsNullOrWhiteSpace(value) ? null : value.Trim();

    private static async Task<string> SafeReadBodyAsync(
        HttpResponseMessage response,
        CancellationToken cancellationToken)
    {
        try
        {
            return await response.Content.ReadAsStringAsync(cancellationToken);
        }
        catch
        {
            return string.Empty;
        }
    }
}
