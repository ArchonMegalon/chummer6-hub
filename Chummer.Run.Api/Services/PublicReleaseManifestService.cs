using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.Json.Serialization;
using Chummer.Run.Contracts.PublicSurface;

namespace Chummer.Run.Api.Services;

public sealed class PublicReleaseManifestService
{
    private const string DefaultRoot = "/downloads-source";
    private const string DefaultManifestContractName = "Chummer.Hub.Registry.Contracts";
    private const string DefaultLocalProofRelativePath = ".codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json";
    private const string RegistryCurrentUrlKey = "CHUMMER_RELEASE_REGISTRY_CURRENT_URL";
    private const string RegistryBaseUrlKey = "CHUMMER_HUB_REGISTRY_BASE_URL";
    private const string PublicCanonRootKey = "CHUMMER_PUBLIC_CANON_ROOT";
    private const string LocalProofFileKey = "CHUMMER_HUB_LOCAL_RELEASE_PROOF_FILE";
    private const string PublicDisabledArtifactIdsKey = "CHUMMER_PUBLIC_DISABLED_ARTIFACT_IDS";
    private const string ReleaseDisabledArtifactIdsKey = "CHUMMER_RELEASE_DISABLED_ARTIFACT_IDS";
    private static readonly string[] RequiredDesktopPlatforms = ["linux", "windows", "macos"];
    private static readonly string[] RequiredDesktopHeads = ["avalonia"];
    private static readonly IReadOnlyDictionary<string, string[]> DefaultRequiredDesktopPlatformRids = new Dictionary<string, string[]>(StringComparer.OrdinalIgnoreCase)
    {
        ["linux"] = ["linux-x64"],
        ["windows"] = ["win-x64"],
        ["macos"] = ["osx-arm64"]
    };
    private static readonly IReadOnlyDictionary<string, (string Platform, string Arch)> RidToPlatformArch = new Dictionary<string, (string Platform, string Arch)>(StringComparer.OrdinalIgnoreCase)
    {
        ["linux-x64"] = ("linux", "x64"),
        ["linux-arm64"] = ("linux", "arm64"),
        ["win-x64"] = ("windows", "x64"),
        ["win-arm64"] = ("windows", "arm64"),
        ["osx-arm64"] = ("macos", "arm64"),
        ["osx-x64"] = ("macos", "x64")
    };
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
            var canonicalManifest = LoadRegistryReleaseManifestPayload(FilterManifestPayload(File.ReadAllText(registryManifestPath)), "registry");
            return ApplyArtifactSuppressionPolicy(ApplyLocalReleaseProofFallback(ChoosePreferredRegistryManifest(runtimeManifest, canonicalManifest)));
        }

        if (runtimeManifest is not null)
        {
            return ApplyArtifactSuppressionPolicy(ApplyLocalReleaseProofFallback(runtimeManifest));
        }

        var manifestPath = Path.Combine(root, "releases.json");
        if (!File.Exists(manifestPath))
        {
            return ApplyArtifactSuppressionPolicy(ApplyLocalReleaseProofFallback(new PublicReleaseManifestDto(
                Version: "unpublished",
                Channel: "preview",
                PublishedAt: DateTimeOffset.UtcNow,
                Downloads: [],
                Source: "fallback",
                Status: "unpublished",
                Message: "No published desktop builds are available yet.",
                HasFallbackSource: false,
                GeneratedAt: DateTimeOffset.UtcNow)));
        }

        return ApplyArtifactSuppressionPolicy(ApplyLocalReleaseProofFallback(LoadReleaseManifestPayload(FilterManifestPayload(File.ReadAllText(manifestPath)))));
    }

    public bool HasArtifactSuppressions()
        => ResolveDisabledArtifactIds().Count > 0;

    public string? LoadCanonicalManifestJson()
    {
        var manifestPath = ResolveCanonicalManifestFilePath();
        return manifestPath is null
            ? null
            : FilterManifestPayload(File.ReadAllText(manifestPath));
    }

    private static PublicReleaseManifestDto ChoosePreferredRegistryManifest(
        PublicReleaseManifestDto? runtimeManifest,
        PublicReleaseManifestDto canonicalManifest)
    {
        if (runtimeManifest is { Downloads.Count: > 0 })
        {
            if (canonicalManifest.Downloads.Count == 0)
            {
                return runtimeManifest;
            }

            if (runtimeManifest.PublishedAt > canonicalManifest.PublishedAt)
            {
                return runtimeManifest;
            }

            if (runtimeManifest.PublishedAt < canonicalManifest.PublishedAt)
            {
                return canonicalManifest;
            }

            return RuntimeManifestDropsCanonicalArtifacts(runtimeManifest, canonicalManifest)
                ? canonicalManifest
                : runtimeManifest;
        }

        if (canonicalManifest.Downloads.Count > 0)
        {
            return canonicalManifest;
        }

        return runtimeManifest ?? canonicalManifest;
    }

    private static bool RuntimeManifestDropsCanonicalArtifacts(
        PublicReleaseManifestDto runtimeManifest,
        PublicReleaseManifestDto canonicalManifest)
    {
        if (!string.Equals(
                NormalizeOptional(runtimeManifest.Channel),
                NormalizeOptional(canonicalManifest.Channel),
                StringComparison.OrdinalIgnoreCase)
            || !string.Equals(
                NormalizeOptional(runtimeManifest.Version),
                NormalizeOptional(canonicalManifest.Version),
                StringComparison.OrdinalIgnoreCase))
        {
            return false;
        }

        HashSet<string> runtimeDownloadIds = LoadArtifactIds(runtimeManifest.Downloads);
        HashSet<string> canonicalDownloadIds = LoadArtifactIds(canonicalManifest.Downloads);
        if (!canonicalDownloadIds.IsSubsetOf(runtimeDownloadIds))
        {
            return true;
        }

        HashSet<string> runtimeInstallerIds = LoadArtifactIds(runtimeManifest.Downloads, installersOnly: true);
        HashSet<string> canonicalInstallerIds = LoadArtifactIds(canonicalManifest.Downloads, installersOnly: true);
        return !canonicalInstallerIds.IsSubsetOf(runtimeInstallerIds);
    }

    private static HashSet<string> LoadArtifactIds(
        IEnumerable<PublicReleaseArtifactDto> downloads,
        bool installersOnly = false)
        => downloads
            .Where(download => !installersOnly || IsInstaller(download))
            .Select(download => NormalizeOptional(download.Id))
            .Where(static artifactId => artifactId is not null)
            .Select(static artifactId => artifactId!)
            .ToHashSet(StringComparer.OrdinalIgnoreCase);

    private static bool IsInstaller(PublicReleaseArtifactDto download)
    {
        string kind = NormalizeOptional(download.Kind) ?? string.Empty;
        if (kind.Length > 0)
        {
            return kind is "installer" or "dmg" or "pkg" or "msix";
        }

        string url = download.Url ?? string.Empty;
        return url.EndsWith(".exe", StringComparison.OrdinalIgnoreCase)
               || url.EndsWith(".deb", StringComparison.OrdinalIgnoreCase)
               || url.EndsWith(".msi", StringComparison.OrdinalIgnoreCase)
               || url.EndsWith(".dmg", StringComparison.OrdinalIgnoreCase)
               || url.EndsWith(".pkg", StringComparison.OrdinalIgnoreCase)
               || (download.Id?.Contains("installer", StringComparison.OrdinalIgnoreCase) ?? false);
    }

    private static string? NormalizeOptional(string? value)
        => string.IsNullOrWhiteSpace(value) ? null : value.Trim();
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
            return EnsureContractName(manifest);
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
                return EnsureContractName(manifest);
            }

            var proofJourneys = manifest.ProofJourneys is { Count: > 0 } ? manifest.ProofJourneys : parsed.JourneysPassed;
            var proofRoutes = manifest.ProofRoutes is { Count: > 0 } ? manifest.ProofRoutes : parsed.ProofRoutes;
            return EnsureContractName(manifest with
            {
                ProofStatus = string.IsNullOrWhiteSpace(manifest.ProofStatus)
                    ? NormalizeProofStatus(parsed.Status)
                    : NormalizeProofStatus(manifest.ProofStatus),
                ProofGeneratedAt = manifest.ProofGeneratedAt ?? parsed.GeneratedAt,
                ProofBaseUrl = string.IsNullOrWhiteSpace(manifest.ProofBaseUrl) ? parsed.BaseUrl : manifest.ProofBaseUrl,
                ProofJourneys = proofJourneys,
                ProofRoutes = proofRoutes
            });
        }
        catch
        {
            return EnsureContractName(manifest);
        }
    }

    private static PublicReleaseManifestDto EnsureContractName(PublicReleaseManifestDto manifest)
        => string.IsNullOrWhiteSpace(manifest.ContractName)
            ? manifest with { ContractName = DefaultManifestContractName }
            : manifest;

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
        => LoadReleaseManifestPayload(File.ReadAllText(manifestPath));

    private static PublicReleaseManifestDto LoadReleaseManifestPayload(string json)
    {
        var options = new JsonSerializerOptions(JsonSerializerDefaults.Web)
        {
            PropertyNameCaseInsensitive = true
        };

        var parsed = LoadStoredCompatibilityManifestPayload(json, options);
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
                HasFallbackSource: false,
                GeneratedAt: DateTimeOffset.UtcNow);
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
            return LoadRegistryReleaseManifestPayload(FilterManifestPayload(json), "registry_runtime");
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
                HasFallbackSource: false,
                GeneratedAt: DateTimeOffset.UtcNow);
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
                PlatformId: string.IsNullOrWhiteSpace(item.Rid) ? item.Platform : item.Rid,
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
            ProofStatus: NormalizeProofStatus(parsed.ReleaseProof?.Status),
            ProofGeneratedAt: parsed.ReleaseProof?.GeneratedAt,
            ProofBaseUrl: parsed.ReleaseProof?.BaseUrl,
            ProofJourneys: parsed.ReleaseProof?.JourneysPassed,
            ProofRoutes: parsed.ReleaseProof?.ProofRoutes,
            GeneratedAt: parsed.GeneratedAt,
            ContractName: string.IsNullOrWhiteSpace(parsed.ContractName)
                ? (string.IsNullOrWhiteSpace(parsed.ContractNameAlias) ? DefaultManifestContractName : parsed.ContractNameAlias)
                : parsed.ContractName)
        {
            ProofUiLocalizationReleaseGate = parsed.ReleaseProof?.UiLocalizationReleaseGate is JsonElement uiLocalizationReleaseGate
                ? uiLocalizationReleaseGate.Clone()
                : null,
            DesktopTupleCoverage = parsed.DesktopTupleCoverage is JsonElement desktopTupleCoverage
                ? desktopTupleCoverage.Clone()
                : null
        };
    }

    private static PublicReleaseManifestDto? LoadStoredCompatibilityManifestPayload(string json, JsonSerializerOptions options)
    {
        CompatibilityReleaseManifest? parsed = JsonSerializer.Deserialize<CompatibilityReleaseManifest>(json, options);
        if (parsed is null)
        {
            return null;
        }

        return new PublicReleaseManifestDto(
            Version: parsed.Version ?? "unpublished",
            Channel: parsed.Channel ?? parsed.ChannelId ?? "preview",
            PublishedAt: parsed.PublishedAt ?? DateTimeOffset.UtcNow,
            Downloads: parsed.Downloads ?? [],
            Source: parsed.Source ?? "manifest",
            Status: parsed.Status ?? "published",
            Message: parsed.Message,
            HasFallbackSource: parsed.HasFallbackSource,
            RolloutState: parsed.RolloutState,
            RolloutReason: parsed.RolloutReason,
            SupportabilityState: parsed.SupportabilityState,
            SupportabilitySummary: parsed.SupportabilitySummary,
            KnownIssueSummary: parsed.KnownIssueSummary,
            FixAvailabilitySummary: parsed.FixAvailabilitySummary,
            ProofStatus: NormalizeProofStatus(parsed.ReleaseProof?.Status),
            ProofGeneratedAt: parsed.ReleaseProof?.GeneratedAt,
            ProofBaseUrl: parsed.ReleaseProof?.BaseUrl,
            ProofJourneys: parsed.ReleaseProof?.JourneysPassed,
            ProofRoutes: parsed.ReleaseProof?.ProofRoutes,
            GeneratedAt: parsed.GeneratedAt ?? parsed.GeneratedAtAlias,
            ContractName: string.IsNullOrWhiteSpace(parsed.ContractName)
                ? parsed.ContractNameAlias
                : parsed.ContractName)
        {
            ProofUiLocalizationReleaseGate = parsed.ReleaseProof?.UiLocalizationReleaseGate is JsonElement uiLocalizationReleaseGate
                ? uiLocalizationReleaseGate.Clone()
                : null,
            DesktopTupleCoverage = parsed.DesktopTupleCoverage is JsonElement desktopTupleCoverage
                ? desktopTupleCoverage.Clone()
                : null
        };
    }

    private static string? NormalizeProofStatus(string? status)
    {
        if (string.IsNullOrWhiteSpace(status))
        {
            return null;
        }

        return status.Trim().ToLowerInvariant() switch
        {
            "pass" => "passed",
            "ready" => "passed",
            _ => status.Trim()
        };
    }

    private string FilterManifestPayload(string json)
    {
        HashSet<string> disabledArtifactIds = ResolveDisabledArtifactIds();
        if (disabledArtifactIds.Count == 0)
        {
            return json;
        }

        JsonObject? manifest = JsonNode.Parse(json)?.AsObject();
        if (manifest is null)
        {
            return json;
        }

        ApplyArtifactSuppressionPolicy(manifest, disabledArtifactIds);
        return manifest.ToJsonString(new JsonSerializerOptions(JsonSerializerDefaults.Web));
    }

    private PublicReleaseManifestDto ApplyArtifactSuppressionPolicy(PublicReleaseManifestDto manifest)
    {
        HashSet<string> disabledArtifactIds = ResolveDisabledArtifactIds();
        if (disabledArtifactIds.Count == 0)
        {
            return EnsureContractName(manifest);
        }

        PublicReleaseArtifactDto[] filteredDownloads = manifest.Downloads
            .Where(download => !disabledArtifactIds.Contains(NormalizeToken(download.Id)))
            .ToArray();
        HashSet<string> disabledRouteTokens = BuildDisabledRouteTokens(manifest.Downloads.Where(download => disabledArtifactIds.Contains(NormalizeToken(download.Id))));
        foreach (string disabledArtifactId in disabledArtifactIds)
        {
            disabledRouteTokens.Add(disabledArtifactId);
        }
        IReadOnlyList<string>? filteredProofRoutes = FilterProofRoutes(manifest.ProofRoutes, disabledRouteTokens);

        JsonElement? filteredCoverage = null;
        bool coverageComplete = true;
        if (manifest.DesktopTupleCoverage is JsonElement coverage && coverage.ValueKind == JsonValueKind.Object)
        {
            JsonObject? coverageObject = JsonNode.Parse(coverage.GetRawText())?.AsObject();
            if (coverageObject is not null)
            {
                RebuildDesktopTupleCoverage(coverageObject, filteredDownloads.Select(BuildArtifactShape).ToArray());
                coverageComplete = CoverageIsComplete(coverageObject);
                filteredCoverage = JsonSerializer.SerializeToElement(coverageObject, new JsonSerializerOptions(JsonSerializerDefaults.Web));
            }
        }

        string? rolloutState = manifest.RolloutState;
        string? rolloutReason = manifest.RolloutReason;
        string? supportabilityState = manifest.SupportabilityState;
        string? supportabilitySummary = manifest.SupportabilitySummary;
        string? knownIssueSummary = manifest.KnownIssueSummary;
        string? fixAvailabilitySummary = manifest.FixAvailabilitySummary;
        if (string.Equals(manifest.Status, "published", StringComparison.OrdinalIgnoreCase) && !coverageComplete)
        {
            string coverageSummary = DesktopTupleCoverageGapSummary(filteredCoverage);
            rolloutState = "coverage_incomplete";
            rolloutReason = $"Current shelf is published, but promotion stays blocked because {coverageSummary}.";
            supportabilityState = "review_required";
            supportabilitySummary = $"Current shelf is live, but support posture stays review_required because {coverageSummary}.";
            knownIssueSummary = "Public shelf intentionally suppresses disabled desktop artifacts until fresh platform proof is republished.";
            fixAvailabilitySummary = "Verify fix availability against the live channel artifact before closing support loops.";
        }

        return EnsureContractName(manifest with
        {
            Downloads = filteredDownloads,
            ProofRoutes = filteredProofRoutes,
            DesktopTupleCoverage = filteredCoverage,
            RolloutState = rolloutState,
            RolloutReason = rolloutReason,
            SupportabilityState = supportabilityState,
            SupportabilitySummary = supportabilitySummary,
            KnownIssueSummary = knownIssueSummary,
            FixAvailabilitySummary = fixAvailabilitySummary
        });
    }

    private void ApplyArtifactSuppressionPolicy(JsonObject manifest, IReadOnlySet<string> disabledArtifactIds)
    {
        List<ManifestArtifactShape> remainingArtifacts = [];
        HashSet<string> disabledRouteTokens = new(StringComparer.OrdinalIgnoreCase);

        if (manifest["artifacts"] is JsonArray artifacts)
        {
            remainingArtifacts.AddRange(FilterArtifactArray(artifacts, disabledArtifactIds, disabledRouteTokens));
        }

        if (manifest["downloads"] is JsonArray downloads)
        {
            remainingArtifacts.AddRange(FilterArtifactArray(downloads, disabledArtifactIds, disabledRouteTokens));
        }

        FilterProofRoutesInNode(manifest["proofRoutes"], disabledRouteTokens);
        if (manifest["releaseProof"] is JsonObject releaseProof)
        {
            FilterProofRoutesInNode(releaseProof["proofRoutes"], disabledRouteTokens);
        }

        if (manifest["desktopTupleCoverage"] is JsonObject coverage)
        {
            RebuildDesktopTupleCoverage(coverage, remainingArtifacts);
            if (string.Equals(NormalizeToken(GetJsonString(manifest["status"])), "published", StringComparison.Ordinal))
            {
                bool coverageComplete = CoverageIsComplete(coverage);
                if (!coverageComplete)
                {
                    string coverageSummary = DesktopTupleCoverageGapSummary(JsonSerializer.SerializeToElement(coverage, new JsonSerializerOptions(JsonSerializerDefaults.Web)));
                    manifest["rolloutState"] = "coverage_incomplete";
                    manifest["rolloutReason"] = $"Current shelf is published, but promotion stays blocked because {coverageSummary}.";
                    manifest["supportabilityState"] = "review_required";
                    manifest["supportabilitySummary"] = $"Current shelf is live, but support posture stays review_required because {coverageSummary}.";
                    manifest["knownIssueSummary"] = "Public shelf intentionally suppresses disabled desktop artifacts until fresh platform proof is republished.";
                    manifest["fixAvailabilitySummary"] = "Verify fix availability against the live channel artifact before closing support loops.";
                }
            }
        }
    }

    private HashSet<string> ResolveDisabledArtifactIds()
    {
        HashSet<string> values = new(StringComparer.OrdinalIgnoreCase);
        AddDisabledArtifacts(values, _configuration[PublicDisabledArtifactIdsKey]);
        AddDisabledArtifacts(values, _configuration[ReleaseDisabledArtifactIdsKey]);
        return values;
    }

    private static void AddDisabledArtifacts(HashSet<string> destination, string? rawValue)
    {
        if (string.IsNullOrWhiteSpace(rawValue))
        {
            return;
        }

        foreach (string value in rawValue.Split([',', ';', '\n', '\r', ' '], StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries))
        {
            string normalized = NormalizeToken(value);
            if (!string.IsNullOrWhiteSpace(normalized))
            {
                destination.Add(normalized);
            }
        }
    }

    private static IReadOnlyList<ManifestArtifactShape> FilterArtifactArray(
        JsonArray artifacts,
        IReadOnlySet<string> disabledArtifactIds,
        HashSet<string> disabledRouteTokens)
    {
        List<ManifestArtifactShape> remaining = [];
        for (int index = artifacts.Count - 1; index >= 0; index--)
        {
            if (artifacts[index] is not JsonObject artifact)
            {
                continue;
            }

            ManifestArtifactShape shape = BuildArtifactShape(artifact);
            if (disabledArtifactIds.Contains(shape.ArtifactId))
            {
                AddRouteTokens(disabledRouteTokens, shape.ArtifactId, shape.FileName, shape.DownloadUrl);
                artifacts.RemoveAt(index);
                continue;
            }

            remaining.Add(shape);
        }

        remaining.Reverse();
        return remaining;
    }

    private static HashSet<string> BuildDisabledRouteTokens(IEnumerable<PublicReleaseArtifactDto> artifacts)
    {
        HashSet<string> tokens = new(StringComparer.OrdinalIgnoreCase);
        foreach (PublicReleaseArtifactDto artifact in artifacts)
        {
            AddRouteTokens(tokens, artifact.Id, artifact.FileName, artifact.Url);
        }

        return tokens;
    }

    private static void AddRouteTokens(HashSet<string> tokens, string? artifactId, string? fileName, string? url)
    {
        if (!string.IsNullOrWhiteSpace(artifactId))
        {
            tokens.Add(artifactId.Trim());
        }

        if (!string.IsNullOrWhiteSpace(fileName))
        {
            tokens.Add(fileName.Trim());
        }

        if (string.IsNullOrWhiteSpace(url))
        {
            return;
        }

        string trimmedUrl = url.Trim();
        tokens.Add(trimmedUrl);
        string basename = Path.GetFileName(trimmedUrl.Split('?', '#')[0]);
        if (!string.IsNullOrWhiteSpace(basename))
        {
            tokens.Add(basename);
        }
    }

    private static IReadOnlyList<string>? FilterProofRoutes(IReadOnlyList<string>? routes, IReadOnlySet<string> disabledRouteTokens)
    {
        if (routes is null || routes.Count == 0 || disabledRouteTokens.Count == 0)
        {
            return routes;
        }

        string[] filtered = routes
            .Where(route => !RouteReferencesDisabledArtifact(route, disabledRouteTokens))
            .ToArray();
        return filtered.Length == 0 ? null : filtered;
    }

    private static void FilterProofRoutesInNode(JsonNode? node, IReadOnlySet<string> disabledRouteTokens)
    {
        if (node is not JsonArray routes || disabledRouteTokens.Count == 0)
        {
            return;
        }

        for (int index = routes.Count - 1; index >= 0; index--)
        {
            string? route = GetJsonString(routes[index]);
            if (RouteReferencesDisabledArtifact(route, disabledRouteTokens))
            {
                routes.RemoveAt(index);
            }
        }
    }

    private static bool RouteReferencesDisabledArtifact(string? route, IReadOnlySet<string> disabledRouteTokens)
    {
        if (string.IsNullOrWhiteSpace(route))
        {
            return false;
        }

        return disabledRouteTokens.Any(token => route.Contains(token, StringComparison.OrdinalIgnoreCase));
    }

    private static void RebuildDesktopTupleCoverage(JsonObject coverage, IReadOnlyList<ManifestArtifactShape> artifacts)
    {
        List<string> requiredPlatforms = ToJsonStringList(coverage["requiredDesktopPlatforms"]);
        if (requiredPlatforms.Count == 0)
        {
            requiredPlatforms = ToJsonStringList(coverage["requiredPlatformIds"]);
        }

        List<string> derivedRequiredPlatforms = DeriveRequiredDesktopPlatforms(artifacts);
        if (derivedRequiredPlatforms.Count > 0)
        {
            requiredPlatforms = derivedRequiredPlatforms;
        }
        else if (requiredPlatforms.Count == 0)
        {
            requiredPlatforms = [.. RequiredDesktopPlatforms];
        }

        List<string> requiredHeads = ToJsonStringList(coverage["requiredDesktopHeads"]);
        if (requiredHeads.Count == 0)
        {
            requiredHeads = [.. RequiredDesktopHeads];
        }

        List<Dictionary<string, string>> promotedInstallerTuples = [];
        HashSet<string> promotedPlatformTokens = new(StringComparer.OrdinalIgnoreCase);
        HashSet<string> promotedHeadTokens = new(StringComparer.OrdinalIgnoreCase);
        HashSet<string> promotedPairs = new(StringComparer.OrdinalIgnoreCase);
        HashSet<string> promotedPlatformHeadRidTuples = new(StringComparer.OrdinalIgnoreCase);
        Dictionary<string, SortedSet<string>> promotedPlatformHeads = requiredPlatforms.ToDictionary(
            static platform => platform,
            static _ => new SortedSet<string>(StringComparer.OrdinalIgnoreCase),
            StringComparer.OrdinalIgnoreCase);

        foreach (ManifestArtifactShape artifact in artifacts)
        {
            if (!requiredPlatforms.Contains(artifact.Platform, StringComparer.OrdinalIgnoreCase)
                || !IsDesktopInstallMedia(artifact.Platform, artifact.Kind))
            {
                continue;
            }

            string tupleId = $"{artifact.Head}:{artifact.Platform}:{artifact.Rid}";
            promotedInstallerTuples.Add(new Dictionary<string, string>(StringComparer.Ordinal)
            {
                ["tupleId"] = tupleId,
                ["head"] = artifact.Head,
                ["platform"] = artifact.Platform,
                ["rid"] = artifact.Rid,
                ["arch"] = artifact.Arch,
                ["kind"] = artifact.Kind,
                ["artifactId"] = artifact.ArtifactId
            });

            if (!string.IsNullOrWhiteSpace(artifact.Head))
            {
                promotedHeadTokens.Add(artifact.Head);
                promotedPairs.Add($"{artifact.Head}:{artifact.Platform}");
                promotedPlatformHeads[artifact.Platform].Add(artifact.Head);
            }

            if (!string.IsNullOrWhiteSpace(artifact.Head) && !string.IsNullOrWhiteSpace(artifact.Rid))
            {
                promotedPlatformHeadRidTuples.Add($"{artifact.Head}:{artifact.Rid}:{artifact.Platform}");
            }

            promotedPlatformTokens.Add(artifact.Platform);
        }

        List<string> requiredTupleIds = ToJsonStringList(coverage["requiredDesktopPlatformHeadRidTuples"]);
        if (requiredTupleIds.Count == 0)
        {
            requiredTupleIds = BuildRequiredDesktopTupleIds(requiredPlatforms, requiredHeads, promotedPlatformHeadRidTuples);
        }

        List<string> missingRequiredPlatforms = requiredPlatforms
            .Where(platform => !promotedPlatformTokens.Contains(platform))
            .ToList();
        List<string> missingRequiredHeads = requiredHeads
            .Where(head => !promotedHeadTokens.Contains(head))
            .ToList();
        List<string> missingRequiredPlatformHeadPairs = requiredPlatforms
            .SelectMany(platform => requiredHeads.Select(head => $"{head}:{platform}"))
            .Where(pair => !promotedPairs.Contains(pair))
            .ToList();
        List<string> promotedTupleIds = promotedPlatformHeadRidTuples
            .OrderBy(static value => value, StringComparer.Ordinal)
            .ToList();
        HashSet<string> promotedTupleSet = new(promotedTupleIds, StringComparer.OrdinalIgnoreCase);
        List<string> missingRequiredPlatformHeadRidTuples = requiredTupleIds
            .Where(tupleId => !promotedTupleSet.Contains(tupleId))
            .ToList();
        HashSet<string> missingTupleSet = new(missingRequiredPlatformHeadRidTuples, StringComparer.OrdinalIgnoreCase);

        coverage["requiredDesktopPlatforms"] = JsonSerializer.SerializeToNode(requiredPlatforms, new JsonSerializerOptions(JsonSerializerDefaults.Web));
        if (coverage.ContainsKey("requiredPlatformIds"))
        {
            coverage["requiredPlatformIds"] = JsonSerializer.SerializeToNode(requiredPlatforms, new JsonSerializerOptions(JsonSerializerDefaults.Web));
        }

        coverage["requiredDesktopHeads"] = JsonSerializer.SerializeToNode(requiredHeads, new JsonSerializerOptions(JsonSerializerDefaults.Web));
        coverage["promotedInstallerTuples"] = JsonSerializer.SerializeToNode(
            promotedInstallerTuples
                .OrderBy(static row => row["platform"], StringComparer.Ordinal)
                .ThenBy(static row => row["head"], StringComparer.Ordinal)
                .ThenBy(static row => row["rid"], StringComparer.Ordinal)
                .ThenBy(static row => row["artifactId"], StringComparer.Ordinal)
                .ToList(),
            new JsonSerializerOptions(JsonSerializerDefaults.Web));
        coverage["promotedPlatformHeads"] = JsonSerializer.SerializeToNode(
            promotedPlatformHeads.ToDictionary(
                static entry => entry.Key,
                static entry => (IReadOnlyList<string>)entry.Value.OrderBy(static value => value, StringComparer.Ordinal).ToArray(),
                StringComparer.OrdinalIgnoreCase),
            new JsonSerializerOptions(JsonSerializerDefaults.Web));
        coverage["requiredDesktopPlatformHeadRidTuples"] = JsonSerializer.SerializeToNode(requiredTupleIds, new JsonSerializerOptions(JsonSerializerDefaults.Web));
        coverage["promotedPlatformHeadRidTuples"] = JsonSerializer.SerializeToNode(promotedTupleIds, new JsonSerializerOptions(JsonSerializerDefaults.Web));
        coverage["missingRequiredPlatforms"] = JsonSerializer.SerializeToNode(missingRequiredPlatforms, new JsonSerializerOptions(JsonSerializerDefaults.Web));
        if (coverage.ContainsKey("missingPlatformIds"))
        {
            coverage["missingPlatformIds"] = JsonSerializer.SerializeToNode(missingRequiredPlatforms, new JsonSerializerOptions(JsonSerializerDefaults.Web));
        }

        coverage["missingRequiredHeads"] = JsonSerializer.SerializeToNode(missingRequiredHeads, new JsonSerializerOptions(JsonSerializerDefaults.Web));
        coverage["missingRequiredPlatformHeadPairs"] = JsonSerializer.SerializeToNode(missingRequiredPlatformHeadPairs, new JsonSerializerOptions(JsonSerializerDefaults.Web));
        if (coverage.ContainsKey("missingHeadPlatformPairs"))
        {
            coverage["missingHeadPlatformPairs"] = JsonSerializer.SerializeToNode(missingRequiredPlatformHeadPairs, new JsonSerializerOptions(JsonSerializerDefaults.Web));
        }

        coverage["missingRequiredPlatformHeadRidTuples"] = JsonSerializer.SerializeToNode(missingRequiredPlatformHeadRidTuples, new JsonSerializerOptions(JsonSerializerDefaults.Web));
        if (coverage.ContainsKey("missingRidPlatformTuples"))
        {
            coverage["missingRidPlatformTuples"] = JsonSerializer.SerializeToNode(missingRequiredPlatformHeadRidTuples, new JsonSerializerOptions(JsonSerializerDefaults.Web));
        }

        if (coverage["externalProofRequests"] is JsonArray requests)
        {
            FilterExternalProofRequests(requests, missingTupleSet);
        }

        if (coverage["desktopRouteTruth"] is JsonArray routeTruth)
        {
            FilterDesktopRouteTruth(routeTruth, artifacts.Select(static artifact => artifact.ArtifactId).ToHashSet(StringComparer.OrdinalIgnoreCase));
        }

        coverage["complete"] = missingRequiredPlatforms.Count == 0
            && missingRequiredHeads.Count == 0
            && missingRequiredPlatformHeadPairs.Count == 0
            && missingRequiredPlatformHeadRidTuples.Count == 0;
    }

    private static void FilterExternalProofRequests(JsonArray requests, IReadOnlySet<string> missingTupleIds)
    {
        for (int index = requests.Count - 1; index >= 0; index--)
        {
            if (requests[index] is not JsonObject request)
            {
                continue;
            }

            string tupleId = NormalizeToken(GetJsonString(request["tupleId"]));
            if (string.IsNullOrWhiteSpace(tupleId) || !missingTupleIds.Contains(tupleId))
            {
                requests.RemoveAt(index);
            }
        }
    }

    private static void FilterDesktopRouteTruth(JsonArray routeTruth, IReadOnlySet<string> allowedArtifactIds)
    {
        for (int index = routeTruth.Count - 1; index >= 0; index--)
        {
            if (routeTruth[index] is not JsonObject row)
            {
                continue;
            }

            string artifactId = NormalizeToken(GetJsonString(row["artifactId"]));
            if (!string.IsNullOrWhiteSpace(artifactId) && !allowedArtifactIds.Contains(artifactId))
            {
                routeTruth.RemoveAt(index);
            }
        }
    }

    private static List<string> BuildRequiredDesktopTupleIds(
        IReadOnlyList<string> requiredPlatforms,
        IReadOnlyList<string> requiredHeads,
        IReadOnlySet<string> promotedTupleIds)
    {
        Dictionary<string, SortedSet<string>> promotedRidsByPlatform = requiredPlatforms.ToDictionary(
            static platform => platform,
            static _ => new SortedSet<string>(StringComparer.OrdinalIgnoreCase),
            StringComparer.OrdinalIgnoreCase);
        foreach (string tupleId in promotedTupleIds)
        {
            string[] parts = tupleId.Split(':', 3, StringSplitOptions.TrimEntries | StringSplitOptions.RemoveEmptyEntries);
            if (parts.Length == 3 && promotedRidsByPlatform.TryGetValue(parts[2], out SortedSet<string>? rids))
            {
                rids.Add(parts[1]);
            }
        }

        return requiredPlatforms
            .SelectMany(platform =>
            {
                IEnumerable<string> rids = DefaultRequiredDesktopPlatformRids.TryGetValue(platform, out string[]? requiredRids)
                    ? requiredRids
                    : promotedRidsByPlatform.GetValueOrDefault(platform, new SortedSet<string>(StringComparer.OrdinalIgnoreCase));
                return requiredHeads.SelectMany(head => rids.Select(rid => $"{head}:{rid}:{platform}"));
            })
            .OrderBy(static value => value, StringComparer.Ordinal)
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .ToList();
    }

    private static List<string> DeriveRequiredDesktopPlatforms(IReadOnlyList<ManifestArtifactShape> artifacts)
    {
        HashSet<string> promotedPlatforms = artifacts
            .Where(artifact =>
                RequiredDesktopPlatforms.Contains(artifact.Platform, StringComparer.OrdinalIgnoreCase)
                && IsDesktopInstallMedia(artifact.Platform, artifact.Kind))
            .Select(artifact => artifact.Platform)
            .ToHashSet(StringComparer.OrdinalIgnoreCase);

        return RequiredDesktopPlatforms
            .Where(platform => promotedPlatforms.Contains(platform))
            .ToList();
    }

    private static bool CoverageIsComplete(JsonObject coverage)
        => ToJsonStringList(coverage["missingRequiredPlatforms"]).Count == 0
            && ToJsonStringList(coverage["missingRequiredHeads"]).Count == 0
            && ToJsonStringList(coverage["missingRequiredPlatformHeadPairs"]).Count == 0
            && ToJsonStringList(coverage["missingRequiredPlatformHeadRidTuples"]).Count == 0;

    private static string DesktopTupleCoverageGapSummary(JsonElement? coverageElement)
    {
        if (coverageElement is not JsonElement coverage || coverage.ValueKind != JsonValueKind.Object)
        {
            return "required desktop tuple coverage is unavailable";
        }

        JsonObject? coverageObject = JsonNode.Parse(coverage.GetRawText())?.AsObject();
        if (coverageObject is null)
        {
            return "required desktop tuple coverage is unavailable";
        }

        List<string> details = [];
        AddCoverageDetail(details, "platforms", ToJsonStringList(coverageObject["missingRequiredPlatforms"]));
        AddCoverageDetail(details, "heads", ToJsonStringList(coverageObject["missingRequiredHeads"]));
        AddCoverageDetail(details, "pairs", ToJsonStringList(coverageObject["missingRequiredPlatformHeadPairs"]));
        AddCoverageDetail(details, "tuples", ToJsonStringList(coverageObject["missingRequiredPlatformHeadRidTuples"]));
        return details.Count == 0
            ? "required desktop tuple coverage is complete"
            : "required desktop tuple coverage is incomplete (" + string.Join("; ", details) + ")";
    }

    private static void AddCoverageDetail(List<string> details, string label, IReadOnlyList<string> values)
    {
        if (values.Count > 0)
        {
            details.Add(label + ": " + string.Join(", ", values));
        }
    }

    private static ManifestArtifactShape BuildArtifactShape(JsonObject artifact)
    {
        string rid = NormalizeRidToken(GetJsonString(artifact["rid"]));
        if (string.IsNullOrWhiteSpace(rid))
        {
            rid = NormalizeRidToken(GetJsonString(artifact["platformId"]));
        }

        string platform = NormalizePlatformToken(GetJsonString(artifact["platform"]));
        if (string.IsNullOrWhiteSpace(platform))
        {
            string platformId = NormalizeToken(GetJsonString(artifact["platformId"]));
            string platformRid = NormalizeRidToken(platformId);
            platform = RidToPlatformArch.TryGetValue(platformRid, out (string Platform, string Arch) mapping)
                ? mapping.Platform
                : NormalizePlatformToken(platformId);
        }

        string arch = NormalizeToken(GetJsonString(artifact["arch"]));
        if (string.IsNullOrWhiteSpace(arch) && RidToPlatformArch.TryGetValue(rid, out (string Platform, string Arch) archMapping))
        {
            arch = archMapping.Arch;
        }

        if (string.IsNullOrWhiteSpace(rid))
        {
            rid = InferRid(platform, arch);
        }

        string? fileName = GetJsonString(artifact["fileName"]);
        string? downloadUrl = GetJsonString(artifact["downloadUrl"]) ?? GetJsonString(artifact["url"]);
        if (string.IsNullOrWhiteSpace(fileName) && !string.IsNullOrWhiteSpace(downloadUrl))
        {
            fileName = Path.GetFileName(downloadUrl.Split('?', '#')[0]);
        }

        return new ManifestArtifactShape(
            ArtifactId: NormalizeToken(GetJsonString(artifact["artifactId"]) ?? GetJsonString(artifact["id"])),
            Head: NormalizeToken(GetJsonString(artifact["head"])),
            Platform: platform,
            Rid: rid,
            Arch: arch,
            Kind: NormalizeToken(GetJsonString(artifact["kind"])),
            FileName: fileName,
            DownloadUrl: downloadUrl);
    }

    private static ManifestArtifactShape BuildArtifactShape(PublicReleaseArtifactDto artifact)
    {
        string rid = NormalizeRidToken(artifact.PlatformId);
        string platform = NormalizePlatformToken(artifact.PlatformId);
        if (string.IsNullOrWhiteSpace(platform))
        {
            platform = RidToPlatformArch.TryGetValue(rid, out (string Platform, string Arch) mapping)
                ? mapping.Platform
                : NormalizePlatformToken(artifact.Platform);
        }

        string arch = NormalizeToken(artifact.Arch);
        if (string.IsNullOrWhiteSpace(arch) && RidToPlatformArch.TryGetValue(rid, out (string Platform, string Arch) archMapping))
        {
            arch = archMapping.Arch;
        }

        if (string.IsNullOrWhiteSpace(rid))
        {
            rid = InferRid(platform, arch);
        }

        string? fileName = artifact.FileName;
        if (string.IsNullOrWhiteSpace(fileName) && !string.IsNullOrWhiteSpace(artifact.Url))
        {
            fileName = Path.GetFileName(artifact.Url.Split('?', '#')[0]);
        }

        return new ManifestArtifactShape(
            ArtifactId: NormalizeToken(artifact.Id),
            Head: NormalizeToken(artifact.Head),
            Platform: platform,
            Rid: rid,
            Arch: arch,
            Kind: NormalizeToken(artifact.Kind),
            FileName: fileName,
            DownloadUrl: artifact.Url);
    }

    private static bool IsDesktopInstallMedia(string platform, string kind)
        => string.Equals(platform, "macos", StringComparison.Ordinal)
            ? kind is "installer" or "dmg" or "pkg"
            : string.Equals(kind, "installer", StringComparison.Ordinal);

    private static string NormalizeToken(string? value)
        => string.IsNullOrWhiteSpace(value)
            ? string.Empty
            : value.Trim().ToLowerInvariant();

    private static string NormalizePlatformToken(string? value)
    {
        string normalized = NormalizeToken(value);
        return normalized switch
        {
            "win" => "windows",
            "osx" => "macos",
            _ => normalized is "linux" or "windows" or "macos" ? normalized : string.Empty
        };
    }

    private static string NormalizeRidToken(string? value)
    {
        string normalized = NormalizeToken(value);
        return normalized switch
        {
            "windows-x64" => "win-x64",
            "windows-arm64" => "win-arm64",
            "macos-x64" => "osx-x64",
            "macos-arm64" => "osx-arm64",
            _ => RidToPlatformArch.ContainsKey(normalized) ? normalized : string.Empty
        };
    }

    private static string InferRid(string platform, string arch)
        => platform switch
        {
            "windows" when string.Equals(arch, "arm64", StringComparison.Ordinal) => "win-arm64",
            "windows" => "win-x64",
            "macos" when string.Equals(arch, "x64", StringComparison.Ordinal) => "osx-x64",
            "macos" => "osx-arm64",
            "linux" when string.Equals(arch, "arm64", StringComparison.Ordinal) => "linux-arm64",
            "linux" => "linux-x64",
            _ => string.Empty
        };

    private static string? GetJsonString(JsonNode? node)
        => node switch
        {
            null => null,
            JsonValue value => value.TryGetValue<string>(out string? stringValue)
                ? stringValue
                : value.ToJsonString().Trim('"'),
            _ => node.ToJsonString()
        };

    private static List<string> ToJsonStringList(JsonNode? node)
    {
        if (node is not JsonArray array)
        {
            return [];
        }

        return array
            .Select(GetJsonString)
            .Where(static value => !string.IsNullOrWhiteSpace(value))
            .Select(static value => value!.Trim())
            .ToList();
    }

    private sealed record RegistryReleaseChannelManifest(
        string? ContractName,
        [property: JsonPropertyName("contract_name")] string? ContractNameAlias,
        string? Product,
        string? ChannelId,
        string? Version,
        DateTimeOffset? GeneratedAt,
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
        JsonElement? DesktopTupleCoverage,
        IReadOnlyList<RegistryReleaseArtifact>? Artifacts);

    private sealed record RegistryReleaseProof(
        string? Status,
        DateTimeOffset? GeneratedAt,
        string? BaseUrl,
        IReadOnlyList<string>? JourneysPassed,
        IReadOnlyList<string>? ProofRoutes,
        JsonElement? UiLocalizationReleaseGate);

    private sealed record CompatibilityReleaseManifest(
        string? Version,
        string? Channel,
        string? ChannelId,
        DateTimeOffset? PublishedAt,
        IReadOnlyList<PublicReleaseArtifactDto>? Downloads,
        string? Source,
        string? Status,
        string? Message,
        bool HasFallbackSource,
        string? RolloutState,
        string? RolloutReason,
        string? SupportabilityState,
        string? SupportabilitySummary,
        string? KnownIssueSummary,
        string? FixAvailabilitySummary,
        CompatibilityReleaseProof? ReleaseProof,
        DateTimeOffset? GeneratedAt,
        [property: JsonPropertyName("generated_at")] DateTimeOffset? GeneratedAtAlias,
        string? ContractName,
        [property: JsonPropertyName("contract_name")] string? ContractNameAlias,
        JsonElement? DesktopTupleCoverage);

    private sealed record CompatibilityReleaseProof(
        string? Status,
        DateTimeOffset? GeneratedAt,
        string? BaseUrl,
        IReadOnlyList<string>? JourneysPassed,
        IReadOnlyList<string>? ProofRoutes,
        JsonElement? UiLocalizationReleaseGate);

    private sealed record RegistryReleaseArtifact(
        string? ArtifactId,
        string? Head,
        string? Platform,
        string? Rid,
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

    private sealed record ManifestArtifactShape(
        string ArtifactId,
        string Head,
        string Platform,
        string Rid,
        string Arch,
        string Kind,
        string? FileName,
        string? DownloadUrl);
}
