using System.Text.Json;
using System.Text.Json.Serialization;
using Chummer.Run.Contracts.PublicSurface;

namespace Chummer.Run.Api.Services;

public sealed class PublicReleaseManifestService
{
    private const string DefaultRoot = "/downloads-source";
    private const string DefaultLocalProofRelativePath = ".codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json";
    private const string RegistryCurrentUrlKey = "CHUMMER_RELEASE_REGISTRY_CURRENT_URL";
    private const string RegistryBaseUrlKey = "CHUMMER_HUB_REGISTRY_BASE_URL";
    private const string PublicCanonRootKey = "CHUMMER_PUBLIC_CANON_ROOT";
    private const string LocalProofFileKey = "CHUMMER_HUB_LOCAL_RELEASE_PROOF_FILE";
    private readonly IConfiguration _configuration;
    private readonly HttpClient? _httpClient;

    public PublicReleaseManifestService(IConfiguration configuration)
        : this(configuration, httpClient: null)
    {
    }

    public PublicReleaseManifestService(IConfiguration configuration, HttpClient? httpClient)
    {
        _configuration = configuration;
        _httpClient = httpClient;
    }

    public PublicReleaseManifestDto LoadManifest()
    {
        var root = ResolveDownloadsRoot();
        var registryManifestUrl = ResolveRegistryManifestUrl();
        PublicReleaseManifestDto? runtimeManifest = null;
        if (!string.IsNullOrWhiteSpace(registryManifestUrl))
        {
            runtimeManifest = TryLoadRegistryReleaseManifestFromUrl(registryManifestUrl);
        }

        var registryManifestPath = ResolveRegistryManifestPath(root);
        if (File.Exists(registryManifestPath))
        {
            var canonicalManifest = LoadRegistryReleaseManifest(registryManifestPath);
            return ApplyLocalReleaseProofFallback(ChoosePreferredRegistryManifest(runtimeManifest, canonicalManifest));
        }

        if (runtimeManifest is not null)
        {
            return ApplyLocalReleaseProofFallback(runtimeManifest);
        }

        var manifestPath = Path.Combine(root, "releases.json");
        if (!File.Exists(manifestPath))
        {
            return ApplyLocalReleaseProofFallback(new PublicReleaseManifestDto(
                Version: "unpublished",
                Channel: "preview",
                PublishedAt: DateTimeOffset.UtcNow,
                Downloads: [],
                Source: "fallback",
                Status: "unpublished",
                Message: "No published desktop builds are available yet.",
                HasFallbackSource: false));
        }

        return ApplyLocalReleaseProofFallback(LoadReleaseManifest(manifestPath));
    }

    private static PublicReleaseManifestDto ChoosePreferredRegistryManifest(
        PublicReleaseManifestDto? runtimeManifest,
        PublicReleaseManifestDto canonicalManifest)
    {
        if (runtimeManifest is { Downloads.Count: > 0 })
        {
            return canonicalManifest.Downloads.Count == 0 || runtimeManifest.PublishedAt >= canonicalManifest.PublishedAt
                ? runtimeManifest
                : canonicalManifest;
        }

        if (canonicalManifest.Downloads.Count > 0)
        {
            return canonicalManifest;
        }

        return runtimeManifest ?? canonicalManifest;
    }

    public string? ResolveDownloadFilePath(string? path)
    {
        if (string.IsNullOrWhiteSpace(path))
        {
            return null;
        }

        var root = Path.GetFullPath(ResolveDownloadsRoot());
        var relative = path.Trim().TrimStart('/').Replace('\\', '/');
        if (relative.Contains("..", StringComparison.Ordinal))
        {
            return null;
        }

        var candidate = Path.GetFullPath(Path.Combine(root, "files", relative.Replace('/', Path.DirectorySeparatorChar)));
        if (!candidate.StartsWith(root, StringComparison.Ordinal) || !File.Exists(candidate))
        {
            return null;
        }

        return candidate;
    }

    public PublicReleaseArtifactDto? FindDownload(string? artifactId)
    {
        var normalized = string.IsNullOrWhiteSpace(artifactId) ? null : artifactId.Trim();
        if (normalized is null)
        {
            return null;
        }

        return LoadManifest().Downloads.FirstOrDefault(item => string.Equals(item.Id, normalized, StringComparison.OrdinalIgnoreCase));
    }

    public PublicReleaseArtifactDto? FindDownloadByPath(string? path)
    {
        var normalized = string.IsNullOrWhiteSpace(path) ? null : path.Trim().TrimStart('/');
        if (normalized is null)
        {
            return null;
        }

        var targetFile = Path.GetFileName(normalized.Split('?', '#')[0]);
        if (string.IsNullOrWhiteSpace(targetFile))
        {
            return null;
        }

        return LoadManifest().Downloads.FirstOrDefault(item =>
        {
            var fileName = item.FileName;
            if (string.IsNullOrWhiteSpace(fileName))
            {
                var rawUrl = item.Url ?? string.Empty;
                var withoutQuery = rawUrl.Split('?', '#')[0];
                fileName = Path.GetFileName(withoutQuery);
            }

            return string.Equals(fileName, targetFile, StringComparison.OrdinalIgnoreCase);
        });
    }

    public string? ResolveDownloadFilePath(PublicReleaseArtifactDto artifact)
    {
        var fileName = artifact.FileName;
        if (string.IsNullOrWhiteSpace(fileName))
        {
            var rawUrl = artifact.Url ?? string.Empty;
            var withoutQuery = rawUrl.Split('?', '#')[0];
            fileName = Path.GetFileName(withoutQuery);
        }

        return ResolveDownloadFilePath(fileName);
    }

    public string? ResolveCanonicalManifestFilePath()
    {
        var root = ResolveDownloadsRoot();
        var path = ResolveRegistryManifestPath(root);
        return File.Exists(path) ? path : null;
    }

    private string ResolveDownloadsRoot()
        => _configuration["CHUMMER_DOWNLOADS_SOURCE_ROOT"]?.Trim() is { Length: > 0 } configured
            ? configured
            : DefaultRoot;

    private PublicReleaseManifestDto ApplyLocalReleaseProofFallback(PublicReleaseManifestDto manifest)
    {
        var proofPath = ResolveLocalReleaseProofPath();
        if (string.IsNullOrWhiteSpace(proofPath) || !File.Exists(proofPath))
        {
            return manifest;
        }

        try
        {
            var options = new JsonSerializerOptions(JsonSerializerDefaults.Web)
            {
                PropertyNameCaseInsensitive = true
            };
            var parsed = JsonSerializer.Deserialize<LocalReleaseProof>(File.ReadAllText(proofPath), options);
            if (parsed is null || !string.Equals(parsed.ContractName, "chummer6-hub.local_release_proof", StringComparison.Ordinal))
            {
                return manifest;
            }

            var proofJourneys = manifest.ProofJourneys is { Count: > 0 } ? manifest.ProofJourneys : parsed.JourneysPassed;
            var proofRoutes = manifest.ProofRoutes is { Count: > 0 } ? manifest.ProofRoutes : parsed.ProofRoutes;
            return manifest with
            {
                ProofStatus = string.IsNullOrWhiteSpace(manifest.ProofStatus) ? parsed.Status : manifest.ProofStatus,
                ProofGeneratedAt = manifest.ProofGeneratedAt ?? parsed.GeneratedAt,
                ProofBaseUrl = string.IsNullOrWhiteSpace(manifest.ProofBaseUrl) ? parsed.BaseUrl : manifest.ProofBaseUrl,
                ProofJourneys = proofJourneys,
                ProofRoutes = proofRoutes
            };
        }
        catch
        {
            return manifest;
        }
    }

    private string ResolveRegistryManifestPath(string downloadsRoot)
        => _configuration["CHUMMER_RELEASE_REGISTRY_MANIFEST_FILE"]?.Trim() is { Length: > 0 } configured
            ? configured
            : Path.Combine(downloadsRoot, "RELEASE_CHANNEL.generated.json");

    private string? ResolveLocalReleaseProofPath()
    {
        if (_configuration[LocalProofFileKey]?.Trim() is { Length: > 0 } configuredProofPath)
        {
            return configuredProofPath;
        }

        var candidates = new[]
        {
            _configuration[PublicCanonRootKey]?.Trim() is { Length: > 0 } canonRoot
                ? Path.Combine(canonRoot, DefaultLocalProofRelativePath.Replace('/', Path.DirectorySeparatorChar))
                : null,
            Path.GetFullPath(Path.Combine(Directory.GetCurrentDirectory(), DefaultLocalProofRelativePath.Replace('/', Path.DirectorySeparatorChar))),
            Path.GetFullPath(Path.Combine(Directory.GetCurrentDirectory(), "..", DefaultLocalProofRelativePath.Replace('/', Path.DirectorySeparatorChar))),
            Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, DefaultLocalProofRelativePath.Replace('/', Path.DirectorySeparatorChar))),
            Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "..", "..", "..", "..", DefaultLocalProofRelativePath.Replace('/', Path.DirectorySeparatorChar)))
        };

        return candidates.FirstOrDefault(candidate => !string.IsNullOrWhiteSpace(candidate) && File.Exists(candidate));
    }

    private string? ResolveRegistryManifestUrl()
    {
        if (_configuration[RegistryCurrentUrlKey]?.Trim() is { Length: > 0 } currentUrl)
        {
            return currentUrl;
        }

        if (_configuration[RegistryBaseUrlKey]?.Trim() is not { Length: > 0 } baseUrl)
        {
            return null;
        }

        return $"{baseUrl.TrimEnd('/')}/api/v1/registry/release-channel/current";
    }

    private static PublicReleaseManifestDto LoadReleaseManifest(string manifestPath)
    {
        var options = new JsonSerializerOptions(JsonSerializerDefaults.Web)
        {
            PropertyNameCaseInsensitive = true
        };

        var json = File.ReadAllText(manifestPath);
        var parsed = JsonSerializer.Deserialize<PublicReleaseManifestDto>(json, options);
        if (parsed is null)
        {
            return new PublicReleaseManifestDto(
                Version: "unpublished",
                Channel: "preview",
                PublishedAt: DateTimeOffset.UtcNow,
                Downloads: [],
                Source: "manifest",
                Status: "manifest-error",
                Message: "Release manifest exists but could not be parsed.",
                HasFallbackSource: false);
        }

        var status = parsed.Downloads.Count > 0
            ? "published"
            : string.Equals(parsed.Version, "unpublished", StringComparison.OrdinalIgnoreCase)
                ? "unpublished"
                : "manifest-empty";
        var message = parsed.Downloads.Count > 0
            ? null
            : status == "unpublished"
                ? "No published desktop builds are available yet."
                : "Release manifest is present but contains no downloadable artifacts.";
        return parsed with
        {
            Source = "manifest",
            Status = status,
            Message = message,
            HasFallbackSource = false
        };
    }

    private static PublicReleaseManifestDto LoadRegistryReleaseManifest(string manifestPath)
        => LoadRegistryReleaseManifestPayload(File.ReadAllText(manifestPath), "registry");

    private PublicReleaseManifestDto? TryLoadRegistryReleaseManifestFromUrl(string manifestUrl)
    {
        try
        {
            using var client = _httpClient is null ? new HttpClient() : null;
            string json = (_httpClient ?? client!).GetStringAsync(manifestUrl).GetAwaiter().GetResult();
            return LoadRegistryReleaseManifestPayload(json, "registry_runtime");
        }
        catch
        {
            return null;
        }
    }

    private static PublicReleaseManifestDto LoadRegistryReleaseManifestPayload(string json, string source)
    {
        var options = new JsonSerializerOptions(JsonSerializerDefaults.Web)
        {
            PropertyNameCaseInsensitive = true
        };

        var parsed = JsonSerializer.Deserialize<RegistryReleaseChannelManifest>(json, options);
        if (parsed is null)
        {
            return new PublicReleaseManifestDto(
                Version: "unpublished",
                Channel: "preview",
                PublishedAt: DateTimeOffset.UtcNow,
                Downloads: [],
                Source: source,
                Status: "manifest-error",
                Message: "Registry release manifest exists but could not be parsed.",
                HasFallbackSource: false);
        }

        var downloads = (parsed.Artifacts ?? [])
            .Where(item => !string.IsNullOrWhiteSpace(item.DownloadUrl))
            .Select(item => new PublicReleaseArtifactDto(
                Id: item.ArtifactId ?? item.FileName ?? "artifact",
                Platform: item.PlatformLabel ?? item.Platform ?? "Preview build",
                Url: item.DownloadUrl ?? "",
                Sha256: item.Sha256 ?? "",
                SizeBytes: item.SizeBytes,
                Head: item.Head,
                PlatformId: item.Platform,
                Arch: item.Arch,
                Kind: item.Kind,
                FileName: item.FileName,
                InstallAccessClass: item.InstallAccessClass))
            .ToList();

        var status = downloads.Count > 0
            ? "published"
            : string.Equals(parsed.Status, "manifest-empty", StringComparison.OrdinalIgnoreCase)
                ? "manifest-empty"
                : "unpublished";
        var message = downloads.Count > 0
            ? parsed.Message
            : status == "unpublished"
                ? "No published desktop builds are available yet."
                : "Registry release manifest is present but contains no downloadable artifacts.";

        return new PublicReleaseManifestDto(
            Version: parsed.Version ?? "unpublished",
            Channel: parsed.ChannelId ?? "preview",
            PublishedAt: parsed.PublishedAt ?? DateTimeOffset.UtcNow,
            Downloads: downloads,
            Source: source,
            Status: status,
            Message: message,
            HasFallbackSource: false,
            RolloutState: parsed.RolloutState,
            RolloutReason: parsed.RolloutReason,
            SupportabilityState: parsed.SupportabilityState,
            SupportabilitySummary: parsed.SupportabilitySummary,
            KnownIssueSummary: parsed.KnownIssueSummary,
            FixAvailabilitySummary: parsed.FixAvailabilitySummary,
            ProofStatus: parsed.ReleaseProof?.Status,
            ProofGeneratedAt: parsed.ReleaseProof?.GeneratedAt,
            ProofBaseUrl: parsed.ReleaseProof?.BaseUrl,
            ProofJourneys: parsed.ReleaseProof?.JourneysPassed,
            ProofRoutes: parsed.ReleaseProof?.ProofRoutes);
    }

    private sealed record RegistryReleaseChannelManifest(
        string? Product,
        string? ChannelId,
        string? Version,
        DateTimeOffset? PublishedAt,
        string? Status,
        string? Message,
        string? RolloutState,
        string? RolloutReason,
        string? SupportabilityState,
        string? SupportabilitySummary,
        string? KnownIssueSummary,
        string? FixAvailabilitySummary,
        RegistryReleaseProof? ReleaseProof,
        IReadOnlyList<RegistryReleaseArtifact>? Artifacts);

    private sealed record RegistryReleaseProof(
        string? Status,
        DateTimeOffset? GeneratedAt,
        string? BaseUrl,
        IReadOnlyList<string>? JourneysPassed,
        IReadOnlyList<string>? ProofRoutes);

    private sealed record RegistryReleaseArtifact(
        string? ArtifactId,
        string? Head,
        string? Platform,
        string? Arch,
        string? Kind,
        string? PlatformLabel,
        string? FileName,
        string? DownloadUrl,
        string? Sha256,
        long? SizeBytes,
        string? InstallAccessClass);

    private sealed record LocalReleaseProof(
        [property: JsonPropertyName("contract_name")] string? ContractName,
        [property: JsonPropertyName("status")] string? Status,
        [property: JsonPropertyName("base_url")] string? BaseUrl,
        [property: JsonPropertyName("generated_at")] DateTimeOffset? GeneratedAt,
        [property: JsonPropertyName("journeys_passed")] IReadOnlyList<string>? JourneysPassed,
        [property: JsonPropertyName("proof_routes")] IReadOnlyList<string>? ProofRoutes);
}
