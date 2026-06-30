using System.Text.Json;
using System.Text.Json.Serialization;

namespace Chummer.Run.Api.Services;

public sealed class FlagshipReadinessArtifactService
{
    private const string DefaultReadinessRelativePath = ".codex-studio/published/FLAGSHIP_PRODUCT_READINESS.generated.json";
    private const string ReadinessFileKey = "CHUMMER_PUBLIC_FLAGSHIP_READINESS_FILE";
    private const string ReadinessFallbackFileKey = "CHUMMER_PUBLIC_FLAGSHIP_READINESS_FALLBACK_FILE";
    private const string ContainerFleetReadinessPath = "/fleet-artifacts/FLAGSHIP_PRODUCT_READINESS.generated.json";
    private const string DefaultFleetReadinessPath = "/docker/fleet/.codex-studio/published/FLAGSHIP_PRODUCT_READINESS.generated.json";
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

            var blockedJourneyEvidence = CollectBlockedJourneyEvidence(path);
            string? reason = FirstNonEmpty(
                payload.FlagshipReadinessAudit?.Reason,
                payload.CompletionAudit?.Reason);

            return new FlagshipReadinessSnapshot(
                Status: payload.Status,
                Reason: reason,
                WarningCoverageKeys: payload.FlagshipReadinessAudit?.WarningCoverageKeys ?? Array.Empty<string>(),
                ScopedWarningCoverageKeys: payload.FlagshipReadinessAudit?.ScopedWarningCoverageKeys ?? Array.Empty<string>(),
                MissingCoverageKeys: payload.FlagshipReadinessAudit?.MissingCoverageKeys ?? Array.Empty<string>(),
                ScopedMissingCoverageKeys: payload.FlagshipReadinessAudit?.ScopedMissingCoverageKeys ?? Array.Empty<string>(),
                BlockedJourneyEvidenceCount: blockedJourneyEvidence.Count,
                BlockedJourneyEvidenceSamples: blockedJourneyEvidence.Take(5).ToArray());
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
        string? canonRoot = _configuration["CHUMMER_PUBLIC_CANON_ROOT"]?.Trim();
        string? configuredFallbackPath = _configuration[ReadinessFallbackFileKey]?.Trim();
        string[] candidates = new string?[]
            {
                !string.IsNullOrWhiteSpace(canonRoot) ? Path.GetFullPath(Path.Combine(canonRoot, relativePath)) : null,
                Path.GetFullPath(Path.Combine(Directory.GetCurrentDirectory(), relativePath)),
                Path.GetFullPath(Path.Combine(Directory.GetCurrentDirectory(), "..", relativePath)),
                Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, relativePath)),
                Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "..", "..", "..", "..", relativePath)),
                !string.IsNullOrWhiteSpace(configuredFallbackPath) ? Path.GetFullPath(configuredFallbackPath) : null,
                ContainerFleetReadinessPath,
                DefaultFleetReadinessPath
            }
            .OfType<string>()
            .Where(static candidate => !string.IsNullOrWhiteSpace(candidate))
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .ToArray();
        return ResolveFreshestReadinessPath(candidates)
            ?? candidates.FirstOrDefault(File.Exists);
    }

    private static string? ResolveFreshestReadinessPath(IEnumerable<string> candidates)
    {
        string? selectedPath = null;
        DateTimeOffset? selectedGeneratedAt = null;
        bool selectedIsPass = false;
        foreach (string candidate in candidates)
        {
            if (!TryReadMetadata(candidate, out DateTimeOffset generatedAt, out bool isPass))
            {
                continue;
            }

            if (selectedGeneratedAt is null
                || (isPass && !selectedIsPass)
                || (isPass == selectedIsPass && generatedAt > selectedGeneratedAt.Value))
            {
                selectedPath = candidate;
                selectedGeneratedAt = generatedAt;
                selectedIsPass = isPass;
            }
        }

        return selectedPath;
    }

    private static bool TryReadMetadata(string path, out DateTimeOffset generatedAt, out bool isPass)
    {
        generatedAt = default;
        isPass = false;
        if (!File.Exists(path))
        {
            return false;
        }

        try
        {
            using JsonDocument document = JsonDocument.Parse(File.ReadAllText(path));
            JsonElement root = document.RootElement;
            if (!root.TryGetProperty("contract_name", out JsonElement contractNameElement)
                || !string.Equals(contractNameElement.GetString(), "fleet.flagship_product_readiness", StringComparison.Ordinal))
            {
                return false;
            }

            string? rawGeneratedAt = null;
            if (root.TryGetProperty("generated_at", out JsonElement generatedAtElement))
            {
                rawGeneratedAt = generatedAtElement.GetString();
            }
            else if (root.TryGetProperty("generatedAt", out JsonElement camelGeneratedAtElement))
            {
                rawGeneratedAt = camelGeneratedAtElement.GetString();
            }

            isPass = root.TryGetProperty("status", out JsonElement statusElement)
                && string.Equals(statusElement.GetString(), "pass", StringComparison.OrdinalIgnoreCase);
            return DateTimeOffset.TryParse(rawGeneratedAt, out generatedAt);
        }
        catch
        {
            return false;
        }
    }

    private static string? FirstNonEmpty(params string?[] values)
        => values.FirstOrDefault(static value => !string.IsNullOrWhiteSpace(value));

    private static IReadOnlyList<string> CollectBlockedJourneyEvidence(string path)
    {
        try
        {
            using JsonDocument document = JsonDocument.Parse(File.ReadAllText(path));
            List<string> evidence = [];
            CollectBlockedJourneyEvidence(document.RootElement, "$", evidence);
            return evidence;
        }
        catch
        {
            return Array.Empty<string>();
        }
    }

    private static void CollectBlockedJourneyEvidence(JsonElement element, string path, ICollection<string> evidence)
    {
        switch (element.ValueKind)
        {
            case JsonValueKind.Object:
                foreach (JsonProperty property in element.EnumerateObject())
                {
                    string propertyPath = $"{path}.{property.Name}";
                    if (property.Value.ValueKind == JsonValueKind.String
                        && string.Equals(property.Value.GetString(), "blocked", StringComparison.OrdinalIgnoreCase)
                        && IsJourneyEvidenceProperty(property.Name))
                    {
                        evidence.Add(propertyPath);
                    }

                    CollectBlockedJourneyEvidence(property.Value, propertyPath, evidence);
                }

                break;
            case JsonValueKind.Array:
                int index = 0;
                foreach (JsonElement child in element.EnumerateArray())
                {
                    CollectBlockedJourneyEvidence(child, $"{path}[{index}]", evidence);
                    index++;
                }

                break;
        }
    }

    private static bool IsJourneyEvidenceProperty(string propertyName)
    {
        string normalized = propertyName.Trim();
        return normalized.Equals("journey_state", StringComparison.OrdinalIgnoreCase)
               || normalized.Equals("journey_overall_state", StringComparison.OrdinalIgnoreCase)
               || normalized.Equals("install_claim_restore_continue", StringComparison.OrdinalIgnoreCase)
               || normalized.Equals("build_explain_publish", StringComparison.OrdinalIgnoreCase)
               || normalized.Equals("report_cluster_release_notify", StringComparison.OrdinalIgnoreCase)
               || normalized.Equals("organize_community_and_close_loop", StringComparison.OrdinalIgnoreCase)
               || normalized.Equals("campaign_session_recover_recap", StringComparison.OrdinalIgnoreCase)
               || normalized.Equals("recover_from_sync_conflict", StringComparison.OrdinalIgnoreCase);
    }

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
    IReadOnlyList<string> ScopedMissingCoverageKeys,
    int BlockedJourneyEvidenceCount,
    IReadOnlyList<string> BlockedJourneyEvidenceSamples)
{
    public bool MissingDesktopClientCoverage
        => WarningCoverageKeys.Contains("desktop_client", StringComparer.OrdinalIgnoreCase)
           || ScopedWarningCoverageKeys.Contains("desktop_client", StringComparer.OrdinalIgnoreCase)
           || MissingCoverageKeys.Contains("desktop_client", StringComparer.OrdinalIgnoreCase)
           || ScopedMissingCoverageKeys.Contains("desktop_client", StringComparer.OrdinalIgnoreCase);

    public bool HasBlockedJourneyEvidence => BlockedJourneyEvidenceCount > 0;

    public bool RequiresReview => MissingDesktopClientCoverage || HasBlockedJourneyEvidence;

    public string DesktopClientGapSummary
        => !string.IsNullOrWhiteSpace(Reason)
            ? Reason!
            : "desktop client coverage is still missing from the current flagship readiness proof";

    public string ReviewRequiredSummary
        => MissingDesktopClientCoverage
            ? DesktopClientGapSummary
            : HasBlockedJourneyEvidence
                ? $"{BlockedJourneyEvidenceCount} flagship journey blocker{(BlockedJourneyEvidenceCount == 1 ? "" : "s")} remain"
                : Reason ?? "flagship readiness is not fully proven";
}
