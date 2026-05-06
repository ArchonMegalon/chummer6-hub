using System.Text.Json;
using System.Text.Json.Serialization;

namespace Chummer.Run.Api.Services;

public sealed class FlagshipReadinessArtifactService
{
    private const string DefaultReadinessRelativePath = ".codex-studio/published/FLAGSHIP_PRODUCT_READINESS.generated.json";
    private const string ReadinessFileKey = "CHUMMER_PUBLIC_FLAGSHIP_READINESS_FILE";
    private readonly IConfiguration _configuration;

    public FlagshipReadinessArtifactService(IConfiguration configuration)
    {
        _configuration = configuration;
    }

    public FlagshipReadinessSnapshot? LoadSnapshot()
    {
        string? path = ResolveReadinessPath();
        if (string.IsNullOrWhiteSpace(path) || !File.Exists(path))
        {
            return null;
        }

        try
        {
            var options = new JsonSerializerOptions(JsonSerializerDefaults.Web);
            var payload = JsonSerializer.Deserialize<FlagshipReadinessPayload>(File.ReadAllText(path), options);
            if (payload is null
                || !string.Equals(payload.ContractName, "fleet.flagship_product_readiness", StringComparison.Ordinal))
            {
                return null;
            }

            string? reason = FirstNonEmpty(
                payload.FlagshipReadinessAudit?.Reason,
                payload.CompletionAudit?.Reason);

            return new FlagshipReadinessSnapshot(
                Status: payload.Status,
                Reason: reason,
                WarningCoverageKeys: payload.FlagshipReadinessAudit?.WarningCoverageKeys ?? Array.Empty<string>(),
                ScopedWarningCoverageKeys: payload.FlagshipReadinessAudit?.ScopedWarningCoverageKeys ?? Array.Empty<string>(),
                MissingCoverageKeys: payload.FlagshipReadinessAudit?.MissingCoverageKeys ?? Array.Empty<string>(),
                ScopedMissingCoverageKeys: payload.FlagshipReadinessAudit?.ScopedMissingCoverageKeys ?? Array.Empty<string>());
        }
        catch
        {
            return null;
        }
    }

    private string? ResolveReadinessPath()
    {
        if (_configuration[ReadinessFileKey]?.Trim() is { Length: > 0 } configuredPath)
        {
            return configuredPath;
        }

        var relativePath = DefaultReadinessRelativePath.Replace('/', Path.DirectorySeparatorChar);
        return new[]
            {
                Path.GetFullPath(Path.Combine(Directory.GetCurrentDirectory(), relativePath)),
                Path.GetFullPath(Path.Combine(Directory.GetCurrentDirectory(), "..", relativePath)),
                Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, relativePath)),
                Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "..", "..", "..", "..", relativePath)),
                Path.GetFullPath(Path.Combine("/docker/fleet", relativePath))
            }
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .FirstOrDefault(File.Exists);
    }

    private static string? FirstNonEmpty(params string?[] values)
        => values.FirstOrDefault(static value => !string.IsNullOrWhiteSpace(value));

    private sealed record FlagshipReadinessPayload(
        [property: JsonPropertyName("contract_name")] string? ContractName,
        [property: JsonPropertyName("status")] string? Status,
        [property: JsonPropertyName("completion_audit")] FlagshipReadinessAuditPayload? CompletionAudit,
        [property: JsonPropertyName("flagship_readiness_audit")] FlagshipReadinessAuditPayload? FlagshipReadinessAudit);

    private sealed record FlagshipReadinessAuditPayload(
        [property: JsonPropertyName("reason")] string? Reason,
        [property: JsonPropertyName("warning_coverage_keys")] IReadOnlyList<string>? WarningCoverageKeys,
        [property: JsonPropertyName("scoped_warning_coverage_keys")] IReadOnlyList<string>? ScopedWarningCoverageKeys,
        [property: JsonPropertyName("missing_coverage_keys")] IReadOnlyList<string>? MissingCoverageKeys,
        [property: JsonPropertyName("scoped_missing_coverage_keys")] IReadOnlyList<string>? ScopedMissingCoverageKeys);
}

public sealed record FlagshipReadinessSnapshot(
    string? Status,
    string? Reason,
    IReadOnlyList<string> WarningCoverageKeys,
    IReadOnlyList<string> ScopedWarningCoverageKeys,
    IReadOnlyList<string> MissingCoverageKeys,
    IReadOnlyList<string> ScopedMissingCoverageKeys)
{
    public bool MissingDesktopClientCoverage
        => WarningCoverageKeys.Contains("desktop_client", StringComparer.OrdinalIgnoreCase)
           || ScopedWarningCoverageKeys.Contains("desktop_client", StringComparer.OrdinalIgnoreCase)
           || MissingCoverageKeys.Contains("desktop_client", StringComparer.OrdinalIgnoreCase)
           || ScopedMissingCoverageKeys.Contains("desktop_client", StringComparer.OrdinalIgnoreCase);

    public string DesktopClientGapSummary
        => !string.IsNullOrWhiteSpace(Reason)
            ? Reason!
            : "desktop client coverage is still missing from the current flagship readiness proof";
}
