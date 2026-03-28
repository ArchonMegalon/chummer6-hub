using System.Text.Json;
using System.Text.Json.Serialization;

namespace Chummer.Run.Api.Services;

public sealed class CampaignOsLocalProofService
{
    private const string DefaultLocalProofRelativePath = ".codex-studio/published/HUB_CAMPAIGN_OS_LOCAL_PROOF.generated.json";
    private const string PublicCanonRootKey = "CHUMMER_PUBLIC_CANON_ROOT";
    private const string LocalProofFileKey = "CHUMMER_HUB_CAMPAIGN_OS_LOCAL_PROOF_FILE";
    private readonly IConfiguration _configuration;

    public CampaignOsLocalProofService(IConfiguration configuration)
    {
        _configuration = configuration;
    }

    public CampaignOsLocalProofSnapshot? LoadProof()
    {
        var proofPath = ResolveLocalProofPath();
        if (string.IsNullOrWhiteSpace(proofPath) || !File.Exists(proofPath))
        {
            return null;
        }

        try
        {
            var options = new JsonSerializerOptions(JsonSerializerDefaults.Web)
            {
                PropertyNameCaseInsensitive = true
            };
            var parsed = JsonSerializer.Deserialize<CampaignOsLocalProofPayload>(File.ReadAllText(proofPath), options);
            if (parsed is null || !string.Equals(parsed.ContractName, "chummer6-hub.campaign_os_local_proof", StringComparison.Ordinal))
            {
                return null;
            }

            return new CampaignOsLocalProofSnapshot(
                Status: parsed.Status ?? "unknown",
                GeneratedAt: parsed.GeneratedAt,
                ProofKind: parsed.ProofKind,
                SourceFile: parsed.SourceFile,
                JourneysPassed: parsed.JourneysPassed ?? Array.Empty<string>());
        }
        catch
        {
            return null;
        }
    }

    private string? ResolveLocalProofPath()
    {
        if (_configuration[LocalProofFileKey]?.Trim() is { Length: > 0 } configuredProofPath)
        {
            return configuredProofPath;
        }

        var relativePath = DefaultLocalProofRelativePath.Replace('/', Path.DirectorySeparatorChar);
        var candidates = new[]
        {
            _configuration[PublicCanonRootKey]?.Trim() is { Length: > 0 } canonRoot
                ? Path.Combine(canonRoot, relativePath)
                : null,
            Path.GetFullPath(Path.Combine(Directory.GetCurrentDirectory(), relativePath)),
            Path.GetFullPath(Path.Combine(Directory.GetCurrentDirectory(), "..", relativePath)),
            Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, relativePath)),
            Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "..", "..", "..", "..", relativePath))
        };

        return candidates.FirstOrDefault(candidate => !string.IsNullOrWhiteSpace(candidate) && File.Exists(candidate));
    }

    private sealed record CampaignOsLocalProofPayload(
        [property: JsonPropertyName("contract_name")] string? ContractName,
        [property: JsonPropertyName("status")] string? Status,
        [property: JsonPropertyName("generated_at")] DateTimeOffset? GeneratedAt,
        [property: JsonPropertyName("proof_kind")] string? ProofKind,
        [property: JsonPropertyName("source_file")] string? SourceFile,
        [property: JsonPropertyName("journeys_passed")] IReadOnlyList<string>? JourneysPassed);
}

public sealed record CampaignOsLocalProofSnapshot(
    string Status,
    DateTimeOffset? GeneratedAt,
    string? ProofKind,
    string? SourceFile,
    IReadOnlyList<string> JourneysPassed);
