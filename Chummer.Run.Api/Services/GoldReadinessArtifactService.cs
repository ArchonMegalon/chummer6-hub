using System.Text.Json;

namespace Chummer.Run.Api.Services;

public sealed class GoldReadinessArtifactService
{
    private const string DefaultRelativePath = ".codex-studio/published/FINAL_GOLD_JANITOR.generated.json";
    private static readonly string[] ConfigKeys =
    [
        "CHUMMER_PUBLIC_FINAL_GOLD_JANITOR_FILE",
        "CHUMMER_PUBLIC_GOLD_JANITOR_FILE"
    ];

    private readonly IConfiguration _configuration;

    public GoldReadinessArtifactService(IConfiguration configuration)
    {
        _configuration = configuration;
    }

    public GoldReadinessSnapshot? LoadSnapshot()
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
            if (!string.Equals(contractName, "chummer.final_gold_janitor", StringComparison.Ordinal))
            {
                return null;
            }

            string? status = TryGetString(root, "status");
            string? verdict = TryGetString(root, "verdict");
            DateTimeOffset? generatedAtUtc = TryParseTimestamp(TryGetString(root, "generated_at_utc") ?? TryGetString(root, "generatedAtUtc"));
            IReadOnlyList<GoldReadinessRuleAuthorityBlocker> blockers = ReadRuleAuthorityBlockers(root);
            IReadOnlyList<string> failures = ReadStringArray(root, "failures");

            return new GoldReadinessSnapshot(
                Path: path,
                Status: status,
                Verdict: verdict,
                GeneratedAtUtc: generatedAtUtc,
                RuleAuthorityBlockers: blockers,
                Failures: failures);
        }
        catch
        {
            return null;
        }
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

        string relativePath = DefaultRelativePath.Replace('/', Path.DirectorySeparatorChar);
        return new[]
            {
                Path.GetFullPath(Path.Combine("/docker/chummercomplete/chummer.run-services", relativePath)),
                Path.GetFullPath(Path.Combine(Directory.GetCurrentDirectory(), relativePath)),
                Path.GetFullPath(Path.Combine(Directory.GetCurrentDirectory(), "..", relativePath)),
                Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, relativePath)),
                Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "..", "..", "..", "..", relativePath))
            }
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .FirstOrDefault(File.Exists);
    }

    private static IReadOnlyList<GoldReadinessRuleAuthorityBlocker> ReadRuleAuthorityBlockers(JsonElement root)
    {
        if (!root.TryGetProperty("required_gates", out JsonElement requiredGates)
            || requiredGates.ValueKind != JsonValueKind.Object
            || !requiredGates.TryGetProperty("rule_authority_minimum_coverage", out JsonElement ruleAuthorityGate)
            || ruleAuthorityGate.ValueKind != JsonValueKind.Object
            || !ruleAuthorityGate.TryGetProperty("rulesets", out JsonElement rulesets)
            || rulesets.ValueKind != JsonValueKind.Object)
        {
            return Array.Empty<GoldReadinessRuleAuthorityBlocker>();
        }

        List<GoldReadinessRuleAuthorityBlocker> blockers = [];
        foreach (JsonProperty rulesetProperty in rulesets.EnumerateObject())
        {
            if (rulesetProperty.Value.ValueKind != JsonValueKind.Object)
            {
                continue;
            }

            JsonElement value = rulesetProperty.Value;
            string? status = TryGetString(value, "status");
            if (!string.Equals(status, "fail", StringComparison.OrdinalIgnoreCase))
            {
                continue;
            }

            blockers.Add(new GoldReadinessRuleAuthorityBlocker(
                RulesetId: rulesetProperty.Name,
                FinalVerdict: TryGetString(value, "final_verdict"),
                RulefactCount: TryGetInt(value, "rulefact_count"),
                RowLevelMappingStatus: TryGetString(value, "row_level_mapping_status"),
                ErrataPostureStatus: TryGetString(value, "errata_posture_status"),
                RemainingGates: ReadStringArray(value, "remaining_gates")));
        }

        return blockers;
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
            if (item.ValueKind == JsonValueKind.String && !string.IsNullOrWhiteSpace(item.GetString()))
            {
                values.Add(item.GetString()!.Trim());
            }
        }

        return values;
    }

    private static int? TryGetInt(JsonElement element, string propertyName)
        => element.TryGetProperty(propertyName, out JsonElement valueElement) && valueElement.ValueKind == JsonValueKind.Number && valueElement.TryGetInt32(out int value)
            ? value
            : null;

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
}

public sealed record GoldReadinessSnapshot(
    string Path,
    string? Status,
    string? Verdict,
    DateTimeOffset? GeneratedAtUtc,
    IReadOnlyList<GoldReadinessRuleAuthorityBlocker> RuleAuthorityBlockers,
    IReadOnlyList<string> Failures);

public sealed record GoldReadinessRuleAuthorityBlocker(
    string RulesetId,
    string? FinalVerdict,
    int? RulefactCount,
    string? RowLevelMappingStatus,
    string? ErrataPostureStatus,
    IReadOnlyList<string> RemainingGates);
