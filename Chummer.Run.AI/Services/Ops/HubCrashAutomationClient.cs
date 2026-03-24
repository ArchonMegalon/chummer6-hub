using System.Net.Http.Json;
using Chummer.Run.Contracts.Support;

namespace Chummer.Run.AI.Services.Ops;

public interface IHubCrashAutomationClient
{
    Task<CrashClusterListResponse> ListCrashClustersAsync(string? status, CancellationToken cancellationToken);
    Task<CrashWorkItemListResponse> ListCrashWorkItemsAsync(string? status, string? candidateOwnerRepo, CancellationToken cancellationToken);
}

public sealed class HubCrashAutomationClient : IHubCrashAutomationClient
{
    private readonly HttpClient _httpClient;

    public HubCrashAutomationClient(HttpClient httpClient)
    {
        _httpClient = httpClient;
    }

    public Task<CrashClusterListResponse> ListCrashClustersAsync(string? status, CancellationToken cancellationToken)
        => GetAsync<CrashClusterListResponse>(BuildRelativePath(
            "api/v1/support/crashes/clusters",
            ("status", status)), cancellationToken);

    public Task<CrashWorkItemListResponse> ListCrashWorkItemsAsync(
        string? status,
        string? candidateOwnerRepo,
        CancellationToken cancellationToken)
        => GetAsync<CrashWorkItemListResponse>(BuildRelativePath(
            "api/v1/support/crashes/work-items",
            ("status", status),
            ("candidateOwnerRepo", candidateOwnerRepo)), cancellationToken);

    private async Task<TResponse> GetAsync<TResponse>(string relativePath, CancellationToken cancellationToken)
    {
        TResponse? response = await _httpClient.GetFromJsonAsync<TResponse>(relativePath, cancellationToken).ConfigureAwait(false);
        return response ?? throw new InvalidOperationException($"Hub crash automation endpoint '{relativePath}' returned an empty payload.");
    }

    private static string BuildRelativePath(string basePath, params (string Key, string? Value)[] query)
    {
        List<string> parts = [];
        foreach ((string key, string? value) in query)
        {
            if (!string.IsNullOrWhiteSpace(value))
            {
                parts.Add($"{Uri.EscapeDataString(key)}={Uri.EscapeDataString(value.Trim())}");
            }
        }

        return parts.Count == 0
            ? basePath
            : $"{basePath}?{string.Join('&', parts)}";
    }
}
