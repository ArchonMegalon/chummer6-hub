using System.Text.Json;

namespace Chummer.Run.Api.Services;

public sealed class LocalReleaseProofArtifactService
{
    private const string DefaultLocalProofRelativePath = ".codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json";
    private static readonly string[] ConfigKeys =
    [
        "CHUMMER_HUB_LOCAL_RELEASE_PROOF_FILE",
        "CHUMMER_PUBLIC_LOCAL_RELEASE_PROOF_FILE"
    ];

    private readonly IConfiguration _configuration;

    public LocalReleaseProofArtifactService(IConfiguration configuration)
    {
        _configuration = configuration;
    }

    public LocalReleaseProofSnapshot? LoadSnapshot()
    {
        string? path = ResolvePath();
        if (string.IsNullOrWhiteSpace(path) || !File.Exists(path))
        {
            return null;
        }

        try
        {
            using JsonDocument document = JsonDocument.Parse(File.ReadAllText(path));
            JsonElement root = document.RootElement;
            string? contractName = TryGetString(root, "contract_name") ?? TryGetString(root, "contractName");
            if (!string.Equals(contractName, "chummer6-hub.local_release_proof", StringComparison.Ordinal))
            {
                return null;
            }

            DateTimeOffset? generatedAt = TryParseTimestamp(TryGetString(root, "generatedAt") ?? TryGetString(root, "generated_at"));
            LocalReleaseProofCurrentness currentness = EvaluateCurrentness(generatedAt);

            return new LocalReleaseProofSnapshot(
                Path: path,
                GeneratedAt: generatedAt,
                IsCurrent: currentness.IsCurrent,
                CurrentnessReason: currentness.Reason,
                Status: TryGetString(root, "status"),
                ProofRoutes: ReadStringArray(root, "proof_routes"),
                Receipts: ReadReceipts(root));
        }
        catch
        {
            return null;
        }
    }

    public LocalReleaseProofLookupResult FindReceipt(params string?[] routeCandidates)
    {
        LocalReleaseProofSnapshot? snapshot = LoadSnapshot();
        if (snapshot is null)
        {
            return new LocalReleaseProofLookupResult(null, null);
        }

        if (!snapshot.IsCurrent)
        {
            return new LocalReleaseProofLookupResult(null, snapshot.CurrentnessReason);
        }

        foreach (LocalReleaseProofReceipt receipt in snapshot.Receipts)
        {
            foreach (string publishedRoute in receipt.Routes)
            {
                foreach (string? routeCandidate in routeCandidates)
                {
                    string? normalizedCandidate = NormalizeOptionalRoute(routeCandidate);
                    if (normalizedCandidate is null)
                    {
                        continue;
                    }

                    if (string.Equals(publishedRoute, normalizedCandidate, StringComparison.OrdinalIgnoreCase))
                    {
                        return new LocalReleaseProofLookupResult(
                            new LocalProofReceiptMatch(
                                receipt.ReceiptId,
                                receipt.PackageId,
                                receipt.Summary,
                                publishedRoute,
                                "exact"),
                            null);
                    }
                }
            }
        }

        return new LocalReleaseProofLookupResult(null, null);
    }

    private string? ResolvePath()
    {
        foreach (string key in ConfigKeys)
        {
            if (_configuration[key]?.Trim() is { Length: > 0 } configuredPath)
            {
                return configuredPath;
            }
        }

        string relativePath = DefaultLocalProofRelativePath.Replace('/', Path.DirectorySeparatorChar);
        return new[]
            {
                Path.GetFullPath(Path.Combine(Directory.GetCurrentDirectory(), relativePath)),
                Path.GetFullPath(Path.Combine(Directory.GetCurrentDirectory(), "..", relativePath)),
                Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, relativePath)),
                Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "..", "..", "..", "..", relativePath)),
                Path.GetFullPath(Path.Combine("/docker/chummercomplete/chummer.run-services", relativePath))
            }
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .FirstOrDefault(File.Exists);
    }

    private static LocalReleaseProofCurrentness EvaluateCurrentness(DateTimeOffset? generatedAt)
    {
        if (generatedAt is null)
        {
            return new LocalReleaseProofCurrentness(
                false,
                "the local release-proof package is missing a usable generated timestamp, so direct proof receipts are not current");
        }

        int maxAgeSeconds = ParseNonNegativeIntEnv(
            "CHUMMER_VERIFY_RELEASE_PROOF_MAX_AGE_SECONDS",
            "CHUMMER_RELEASE_PROOF_MAX_AGE_SECONDS",
            defaultValue: 86400);
        int maxFutureSkewSeconds = ParseNonNegativeIntEnv(
            "CHUMMER_VERIFY_RELEASE_PROOF_MAX_FUTURE_SKEW_SECONDS",
            "CHUMMER_RELEASE_PROOF_MAX_FUTURE_SKEW_SECONDS",
            defaultValue: 300);

        int ageSeconds = (int)(DateTimeOffset.UtcNow - generatedAt.Value).TotalSeconds;
        if (ageSeconds > maxAgeSeconds)
        {
            return new LocalReleaseProofCurrentness(
                false,
                "the local release-proof package is stale, so direct proof receipts are not current");
        }

        if (ageSeconds < 0 && Math.Abs(ageSeconds) > maxFutureSkewSeconds)
        {
            return new LocalReleaseProofCurrentness(
                false,
                "the local release-proof package is timestamped in the future, so direct proof receipts are not current");
        }

        return new LocalReleaseProofCurrentness(true, null);
    }

    private static int ParseNonNegativeIntEnv(string primaryName, string secondaryName, int defaultValue)
    {
        foreach (string name in new[] { primaryName, secondaryName })
        {
            string? rawValue = Environment.GetEnvironmentVariable(name);
            if (!string.IsNullOrWhiteSpace(rawValue) && int.TryParse(rawValue, out int parsedValue) && parsedValue >= 0)
            {
                return parsedValue;
            }
        }

        return defaultValue;
    }

    private static IReadOnlyList<LocalReleaseProofReceipt> ReadReceipts(JsonElement root)
    {
        if (!root.TryGetProperty("proof_receipts", out JsonElement receiptsElement) || receiptsElement.ValueKind != JsonValueKind.Array)
        {
            return Array.Empty<LocalReleaseProofReceipt>();
        }

        List<LocalReleaseProofReceipt> receipts = [];
        foreach (JsonElement receiptElement in receiptsElement.EnumerateArray())
        {
            string receiptId = TryGetString(receiptElement, "receipt_id") ?? "unknown";
            string packageId = TryGetString(receiptElement, "package_id") ?? "unknown";
            string summary = TryGetString(receiptElement, "summary") ?? "No summary was published for this proof receipt.";
            IReadOnlyList<string> routes = ReadStringArray(receiptElement, "routes");
            receipts.Add(new LocalReleaseProofReceipt(receiptId, packageId, summary, routes));
        }

        return receipts;
    }

    private static IReadOnlyList<string> ReadStringArray(JsonElement root, string propertyName)
    {
        if (!root.TryGetProperty(propertyName, out JsonElement arrayElement) || arrayElement.ValueKind != JsonValueKind.Array)
        {
            return Array.Empty<string>();
        }

        List<string> values = [];
        foreach (JsonElement item in arrayElement.EnumerateArray())
        {
            string? value = NormalizeOptionalRoute(item.GetString());
            if (value is not null)
            {
                values.Add(value);
            }
        }

        return values;
    }

    private static DateTimeOffset? TryParseTimestamp(string? value)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return null;
        }

        return DateTimeOffset.TryParse(value.Trim(), out DateTimeOffset parsed)
            ? parsed
            : null;
    }

    private static string? TryGetString(JsonElement element, string propertyName)
        => element.TryGetProperty(propertyName, out JsonElement valueElement) && valueElement.ValueKind == JsonValueKind.String
            ? valueElement.GetString()
            : null;

    private static string? NormalizeOptionalRoute(string? value)
        => string.IsNullOrWhiteSpace(value) ? null : value.Trim();

    private sealed record LocalReleaseProofCurrentness(bool IsCurrent, string? Reason);
}

public sealed record LocalReleaseProofSnapshot(
    string Path,
    DateTimeOffset? GeneratedAt,
    bool IsCurrent,
    string? CurrentnessReason,
    string? Status,
    IReadOnlyList<string> ProofRoutes,
    IReadOnlyList<LocalReleaseProofReceipt> Receipts);

public sealed record LocalReleaseProofReceipt(
    string ReceiptId,
    string PackageId,
    string Summary,
    IReadOnlyList<string> Routes);

public sealed record LocalProofReceiptMatch(
    string ReceiptId,
    string PackageId,
    string Summary,
    string MatchedRoute,
    string MatchMode);

public sealed record LocalReleaseProofLookupResult(
    LocalProofReceiptMatch? ReceiptMatch,
    string? CurrentnessFailureReason);
