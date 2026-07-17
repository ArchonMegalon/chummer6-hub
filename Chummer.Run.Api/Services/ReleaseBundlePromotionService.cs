using System.IO.Compression;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.Json.Serialization;
using Chummer.Run.Contracts.PublicSurface;

namespace Chummer.Run.Api.Services;

public sealed record ReleaseBundlePromotionResult(
    string Version,
    string Channel,
    DateTimeOffset PublishedAt,
    IReadOnlyList<string> PromotedArtifactIds,
    string DownloadsUrl,
    IReadOnlyList<string> InstallDispatchUrls,
    IReadOnlyList<string> DirectFileUrls,
    IReadOnlyList<ReleasePromotionInstallClaim>? SignedInInstallClaims = null,
    string? CanonicalManifestSha256 = null,
    string? CompatibilityManifestSha256 = null);

public sealed record ReleasePromotionInstallClaim(
    string ArtifactId,
    string InstallDispatchUrl,
    string ClaimCode,
    DateTimeOffset? ClaimCodeExpiresAtUtc);

public sealed class ReleaseBundlePromotionService
{
    private const string DownloadsRootKey = "CHUMMER_DOWNLOADS_SOURCE_ROOT";
    private const string DefaultDownloadsRoot = "/downloads-source";
    private const string CompatibilityManifestName = "releases.json";
    private const string CanonicalManifestName = "RELEASE_CHANNEL.generated.json";
    private const string RegistryContractName = "Chummer.Hub.Registry.Contracts";
    private const string ActivationReceiptName = ".release-channel-activation.json";
    private const string ActivationReceiptContractName = "chummer.run.registry_manifest_activation.v1";
    private const string PromotionEvidenceRelativePath = "release-evidence/public-promotion.json";
    private const string PublicBaseUrlKey = "GOOGLE_OIDC_REDIRECT_URI";
    private static readonly TimeSpan MaximumReleaseProofPublicationLag = TimeSpan.FromHours(24);
    private static readonly string[] RequiredDesktopPlatforms = ["linux", "windows", "macos"];
    private static readonly string[] RequiredDesktopHeads = ["avalonia"];
    private static readonly string[] RequiredDesktopPlatformHeadRidTuples =
    [
        "avalonia:linux-x64:linux",
        "avalonia:osx-arm64:macos",
        "avalonia:win-x64:windows"
    ];
    private static readonly string[] DesktopRouteTruthHeads = ["avalonia", "blazor-desktop"];
    private static readonly IReadOnlyDictionary<string, string> DesktopRouteRoles = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase)
    {
        ["avalonia"] = "primary",
        ["blazor-desktop"] = "fallback"
    };
    private static readonly IReadOnlyDictionary<string, string> AppLabels = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase)
    {
        ["avalonia"] = "Avalonia Desktop",
        ["blazor-desktop"] = "Blazor Desktop"
    };
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
    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web)
    {
        PropertyNameCaseInsensitive = true,
        WriteIndented = true
    };

    private readonly IConfiguration _configuration;
    private readonly ILogger<ReleaseBundlePromotionService> _logger;

    public ReleaseBundlePromotionService(
        IConfiguration configuration,
        ILogger<ReleaseBundlePromotionService> logger)
    {
        _configuration = configuration;
        _logger = logger;
    }

    public async Task<ReleaseBundlePromotionResult> PromoteAsync(
        string? uploadedFileName,
        Stream bundleStream,
        CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(bundleStream);

        string downloadsRoot = ResolveDownloadsRoot();
        EnsureDownloadsRootWritable(downloadsRoot);

        string tempRoot = Path.Combine(Path.GetTempPath(), "chummer-release-bundles", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempRoot);
        try
        {
            string bundleFileName = string.IsNullOrWhiteSpace(uploadedFileName) ? "bundle.zip" : Path.GetFileName(uploadedFileName);
            string bundlePath = Path.Combine(tempRoot, bundleFileName);
            await using (FileStream fileStream = File.Create(bundlePath))
            {
                await bundleStream.CopyToAsync(fileStream, cancellationToken);
            }

            string extractRoot = Path.Combine(tempRoot, "bundle");
            ZipFile.ExtractToDirectory(bundlePath, extractRoot);

            string bundleRoot = ResolveBundleRoot(extractRoot);
            return await PromotePreparedBundleAsync(bundleRoot, downloadsRoot, cancellationToken);
        }
        finally
        {
            try
            {
                if (Directory.Exists(tempRoot))
                {
                    Directory.Delete(tempRoot, recursive: true);
                }
            }
            catch (Exception ex)
            {
                _logger.LogWarning(ex, "Release bundle promotion cleanup failed for {TempRoot}.", tempRoot);
            }
        }
    }

    public async Task<ReleaseBundlePromotionResult> PromoteDirectoryAsync(
        string bundleRoot,
        CancellationToken cancellationToken)
    {
        if (string.IsNullOrWhiteSpace(bundleRoot))
        {
            throw new InvalidDataException("bundle root is required.");
        }

        cancellationToken.ThrowIfCancellationRequested();
        string downloadsRoot = ResolveDownloadsRoot();
        EnsureDownloadsRootWritable(downloadsRoot);
        return await PromotePreparedBundleAsync(bundleRoot, downloadsRoot, cancellationToken);
    }

    private Task<ReleaseBundlePromotionResult> PromotePreparedBundleAsync(
        string bundleRoot,
        string downloadsRoot,
        CancellationToken cancellationToken)
    {
        string compatibilityManifestPath = RequireSingleFile(bundleRoot, CompatibilityManifestName);
        string canonicalManifestPath = RequireSingleFile(bundleRoot, CanonicalManifestName);
        string filesRoot = RequireSiblingDirectory(compatibilityManifestPath, "files");
        string? startupSmokeRoot = ResolveSiblingDirectory(compatibilityManifestPath, "startup-smoke");
        string? proofRoot = ResolveSiblingDirectory(compatibilityManifestPath, "proof");
        string? promotionEvidencePath = ResolveOptionalFile(bundleRoot, PromotionEvidenceRelativePath);

        byte[] incomingCompatibilityBytes = ReadManifestBytes(
            compatibilityManifestPath,
            CompatibilityManifestName);
        byte[] incomingCanonicalBytes = ReadManifestBytes(
            canonicalManifestPath,
            CanonicalManifestName);
        PublicReleaseManifestDto incomingCompatibilityManifest = LoadCompatibilityManifest(
            incomingCompatibilityBytes,
            compatibilityManifestPath);
        JsonObject incomingCompatibilityJson = LoadJsonObject(
            incomingCompatibilityBytes,
            compatibilityManifestPath);
        JsonObject incomingCanonicalManifest = LoadJsonObject(
            incomingCanonicalBytes,
            canonicalManifestPath);

        IReadOnlyList<CanonicalArtifactRecord> incomingCanonicalArtifacts = LoadCanonicalArtifacts(incomingCanonicalManifest);
        ValidateRegistryAuthoredManifestPair(
            incomingCompatibilityJson,
            incomingCanonicalManifest,
            incomingCompatibilityManifest,
            incomingCanonicalArtifacts);
        ValidateIncomingBundle(
            incomingCompatibilityManifest,
            incomingCanonicalArtifacts,
            filesRoot,
            startupSmokeRoot,
            promotionEvidencePath);

        string liveCompatibilityManifestPath = Path.Combine(downloadsRoot, CompatibilityManifestName);
        string liveCanonicalManifestPath = Path.Combine(downloadsRoot, CanonicalManifestName);
        PublicReleaseManifestDto? existingCompatibilityManifest = File.Exists(liveCompatibilityManifestPath)
            ? LoadCompatibilityManifest(liveCompatibilityManifestPath)
            : null;

        List<string> existingFileNames = existingCompatibilityManifest?.Downloads
            .Select(ResolveDownloadFileName)
            .Where(static fileName => !string.IsNullOrWhiteSpace(fileName))
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .ToList()
            ?? new List<string>();

        string filesDestinationRoot = Path.Combine(downloadsRoot, "files");
        Directory.CreateDirectory(filesDestinationRoot);
        foreach (string sourcePath in Directory.GetFiles(filesRoot))
        {
            cancellationToken.ThrowIfCancellationRequested();
            string destinationPath = Path.Combine(filesDestinationRoot, Path.GetFileName(sourcePath));
            File.Copy(sourcePath, destinationPath, overwrite: true);
        }

        if (!string.IsNullOrWhiteSpace(startupSmokeRoot) && Directory.Exists(startupSmokeRoot))
        {
            CopyDirectoryContents(
                startupSmokeRoot,
                Path.Combine(downloadsRoot, "startup-smoke"),
                cancellationToken);
        }

        if (!string.IsNullOrWhiteSpace(proofRoot) && Directory.Exists(proofRoot))
        {
            MirrorDirectoryContents(
                proofRoot,
                Path.Combine(downloadsRoot, "proof"),
                cancellationToken);
        }

        HashSet<string> incomingFileNames = incomingCompatibilityManifest.Downloads
            .Select(ResolveDownloadFileName)
            .Where(static fileName => !string.IsNullOrWhiteSpace(fileName))
            .ToHashSet(StringComparer.OrdinalIgnoreCase);
        foreach (string replacedFileName in existingFileNames)
        {
            if (incomingFileNames.Contains(replacedFileName))
            {
                continue;
            }

            string oldPath = Path.Combine(filesDestinationRoot, replacedFileName);
            if (File.Exists(oldPath))
            {
                File.Delete(oldPath);
            }
        }

        WriteBytesAtomically(liveCompatibilityManifestPath, incomingCompatibilityBytes);
        WriteBytesAtomically(liveCanonicalManifestPath, incomingCanonicalBytes);

        string compatibilityManifestSha256 = Sha256For(incomingCompatibilityBytes);
        string canonicalManifestSha256 = Sha256For(incomingCanonicalBytes);

        IReadOnlyList<string> promotedArtifactIds = incomingCompatibilityManifest.Downloads
            .Select(static artifact => artifact.Id)
            .Where(static id => !string.IsNullOrWhiteSpace(id))
            .ToArray();

        string baseUrl = ResolvePublicBaseUrl();
        PublicReleaseManifestDto publicShelfManifest = ValidatePublicShelfCoherence(
            downloadsRoot,
            liveCompatibilityManifestPath,
            liveCanonicalManifestPath,
            promotedArtifactIds,
            compatibilityManifestSha256,
            canonicalManifestSha256);
        DateTimeOffset activatedAt = DateTimeOffset.UtcNow;
        WriteJsonAtomically(
            Path.Combine(downloadsRoot, ActivationReceiptName),
            new RegistryManifestActivationReceipt(
                ContractName: ActivationReceiptContractName,
                RegistryContractName: RegistryContractName,
                Version: incomingCompatibilityManifest.Version,
                Channel: incomingCompatibilityManifest.Channel,
                PublishedAt: incomingCompatibilityManifest.PublishedAt,
                ActivatedAt: activatedAt,
                CompatibilityManifestSha256: $"sha256:{compatibilityManifestSha256}",
                CanonicalManifestSha256: $"sha256:{canonicalManifestSha256}"));
        ReleaseBundlePromotionResult result = new(
            Version: incomingCompatibilityManifest.Version,
            Channel: incomingCompatibilityManifest.Channel,
            PublishedAt: incomingCompatibilityManifest.PublishedAt,
            PromotedArtifactIds: promotedArtifactIds,
            DownloadsUrl: $"{baseUrl}/downloads/",
            InstallDispatchUrls: promotedArtifactIds.Select(id => $"{baseUrl}/downloads/install/{Uri.EscapeDataString(id)}").ToArray(),
            DirectFileUrls: publicShelfManifest.Downloads
                .Where(download => promotedArtifactIds.Contains(download.Id, StringComparer.OrdinalIgnoreCase))
                .Select(download => $"{baseUrl}{NormalizePublicPath(download.Url)}")
                .ToArray(),
            CanonicalManifestSha256: $"sha256:{canonicalManifestSha256}",
            CompatibilityManifestSha256: $"sha256:{compatibilityManifestSha256}");
        return Task.FromResult(result);
    }

    private string ResolveDownloadsRoot()
        => _configuration[DownloadsRootKey]?.Trim() is { Length: > 0 } configured
            ? configured
            : DefaultDownloadsRoot;

    private string ResolvePublicBaseUrl()
    {
        string? configured = _configuration[PublicBaseUrlKey]?.Trim();
        if (Uri.TryCreate(configured, UriKind.Absolute, out Uri? redirectUri))
        {
            return $"{redirectUri.Scheme}://{redirectUri.Authority}";
        }

        return "https://chummer.run";
    }

    private static void EnsureDownloadsRootWritable(string downloadsRoot)
    {
        Directory.CreateDirectory(downloadsRoot);
        string probePath = Path.Combine(downloadsRoot, $".release-promotion-write-probe-{Guid.NewGuid():N}");
        try
        {
            File.WriteAllText(probePath, "ok");
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            throw new InvalidOperationException($"downloads root is not writable: {downloadsRoot}", ex);
        }
        finally
        {
            if (File.Exists(probePath))
            {
                File.Delete(probePath);
            }
        }
    }

    private static void CopyDirectoryContents(
        string sourceRoot,
        string destinationRoot,
        CancellationToken cancellationToken)
    {
        Directory.CreateDirectory(destinationRoot);
        foreach (string sourcePath in Directory.GetFiles(sourceRoot, "*", SearchOption.AllDirectories))
        {
            cancellationToken.ThrowIfCancellationRequested();
            string relativePath = Path.GetRelativePath(sourceRoot, sourcePath);
            string destinationPath = Path.Combine(destinationRoot, relativePath);
            string? destinationDirectory = Path.GetDirectoryName(destinationPath);
            if (!string.IsNullOrWhiteSpace(destinationDirectory))
            {
                Directory.CreateDirectory(destinationDirectory);
            }

            File.Copy(sourcePath, destinationPath, overwrite: true);
        }
    }

    private static void MirrorDirectoryContents(
        string sourceRoot,
        string destinationRoot,
        CancellationToken cancellationToken)
    {
        if (Directory.Exists(destinationRoot))
        {
            Directory.Delete(destinationRoot, recursive: true);
        }

        CopyDirectoryContents(sourceRoot, destinationRoot, cancellationToken);
    }

    private static string ResolveBundleRoot(string extractRoot)
    {
        string directCompatibilityManifest = Path.Combine(extractRoot, CompatibilityManifestName);
        string directCanonicalManifest = Path.Combine(extractRoot, CanonicalManifestName);
        if (File.Exists(directCompatibilityManifest) && File.Exists(directCanonicalManifest))
        {
            return extractRoot;
        }

        string[] children = Directory.GetDirectories(extractRoot);
        if (children.Length == 1)
        {
            string childCompatibilityManifest = Path.Combine(children[0], CompatibilityManifestName);
            string childCanonicalManifest = Path.Combine(children[0], CanonicalManifestName);
            if (File.Exists(childCompatibilityManifest) && File.Exists(childCanonicalManifest))
            {
                return children[0];
            }
        }

        return extractRoot;
    }

    private static string RequireSingleFile(string root, string fileName)
    {
        string[] matches = Directory.GetFiles(root, fileName, SearchOption.AllDirectories);
        return matches.Length switch
        {
            0 => throw new InvalidDataException($"bundle is missing required file: {fileName}"),
            > 1 => throw new InvalidDataException($"bundle contains more than one {fileName}; expected a single manifest"),
            _ => matches[0]
        };
    }

    private static string? ResolveOptionalFile(string root, string relativePath)
    {
        string directPath = Path.Combine(root, relativePath.Replace('/', Path.DirectorySeparatorChar));
        if (File.Exists(directPath))
        {
            return directPath;
        }

        string fileName = Path.GetFileName(relativePath);
        return Directory.GetFiles(root, fileName, SearchOption.AllDirectories).FirstOrDefault();
    }

    private static string RequireSiblingDirectory(string path, string siblingName)
    {
        string? root = Path.GetDirectoryName(path);
        if (root is null)
        {
            throw new InvalidDataException($"cannot resolve sibling directory {siblingName} for {path}");
        }

        string siblingPath = Path.Combine(root, siblingName);
        if (!Directory.Exists(siblingPath))
        {
            throw new InvalidDataException($"bundle is missing required directory: {siblingName}");
        }

        return siblingPath;
    }

    private static string? ResolveSiblingDirectory(string path, string siblingName)
    {
        string? root = Path.GetDirectoryName(path);
        if (root is null)
        {
            return null;
        }

        string siblingPath = Path.Combine(root, siblingName);
        return Directory.Exists(siblingPath) ? siblingPath : null;
    }

    private static PublicReleaseManifestDto LoadCompatibilityManifest(string manifestPath)
    {
        byte[] bytes = ReadManifestBytes(manifestPath, Path.GetFileName(manifestPath));
        return LoadCompatibilityManifest(bytes, manifestPath);
    }

    private static PublicReleaseManifestDto LoadCompatibilityManifest(byte[] bytes, string source)
    {
        CompatibilityManifestPayload? parsed = JsonSerializer.Deserialize<CompatibilityManifestPayload>(
            DecodeManifestUtf8(bytes, source),
            JsonOptions);
        PublicReleaseManifestDto? manifest = parsed is null
            ? null
            : new PublicReleaseManifestDto(
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
                ProofStatus: parsed.ReleaseProof?.Status,
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
                    : null,
                RegistryBoundaryCoverage = parsed.RegistryBoundaryCoverage is JsonElement registryBoundaryCoverage
                    ? registryBoundaryCoverage.Clone()
                    : null
            };
        return manifest ?? throw new InvalidDataException($"compatibility release manifest could not be parsed: {source}");
    }

    private static JsonObject LoadJsonObject(string path)
    {
        byte[] bytes = ReadManifestBytes(path, Path.GetFileName(path));
        return LoadJsonObject(bytes, path);
    }

    private static JsonObject LoadJsonObject(byte[] bytes, string source)
    {
        JsonNode? parsed = JsonNode.Parse(DecodeManifestUtf8(bytes, source));
        return parsed?.AsObject() ?? throw new InvalidDataException($"json object could not be parsed: {source}");
    }

    private static byte[] ReadManifestBytes(string path, string label)
    {
        try
        {
            using var stream = new FileStream(
                path,
                FileMode.Open,
                FileAccess.Read,
                FileShare.Read,
                bufferSize: 64 * 1024,
                FileOptions.SequentialScan);
            long length = stream.Length;
            if (length <= 0 || length > ReleaseShelfGenerationStore.MaximumManifestBytes)
            {
                throw new InvalidDataException($"{label} exceeds the permitted manifest byte length.");
            }

            byte[] bytes = new byte[checked((int)length)];
            stream.ReadExactly(bytes);
            if (stream.ReadByte() != -1 || stream.Length != length)
            {
                throw new InvalidDataException($"{label} changed while it was being read.");
            }

            _ = DecodeManifestUtf8(bytes, label);
            return bytes;
        }
        catch (EndOfStreamException exception)
        {
            throw new InvalidDataException($"{label} changed while it was being read.", exception);
        }
    }

    private static string DecodeManifestUtf8(byte[] bytes, string label)
    {
        try
        {
            return new UTF8Encoding(encoderShouldEmitUTF8Identifier: false, throwOnInvalidBytes: true)
                .GetString(bytes);
        }
        catch (DecoderFallbackException exception)
        {
            throw new InvalidDataException($"{label} is not valid UTF-8.", exception);
        }
    }

    private static IReadOnlyList<CanonicalArtifactRecord> LoadCanonicalArtifacts(JsonObject manifest)
    {
        JsonNode? artifactsNode = manifest["artifacts"];
        if (artifactsNode is not JsonArray artifactsArray)
        {
            throw new InvalidDataException("canonical release manifest is missing artifacts.");
        }

        List<CanonicalArtifactRecord> artifacts = new(artifactsArray.Count);
        foreach (JsonNode? artifactNode in artifactsArray)
        {
            CanonicalArtifactRecord? artifact = artifactNode?.Deserialize<CanonicalArtifactRecord>(JsonOptions);
            if (artifact is null || string.IsNullOrWhiteSpace(artifact.ArtifactId))
            {
                throw new InvalidDataException("canonical release manifest contains an invalid artifact row.");
            }

            artifacts.Add(artifact);
        }

        return artifacts;
    }

    private static void ValidateRegistryAuthoredManifestPair(
        JsonObject compatibility,
        JsonObject canonical,
        PublicReleaseManifestDto compatibilityManifest,
        IReadOnlyList<CanonicalArtifactRecord> canonicalArtifacts)
    {
        RequireRegistryContract(compatibility, CompatibilityManifestName);
        RequireRegistryContract(canonical, CanonicalManifestName);
        if (!string.Equals(
                NormalizeToken(GetJsonString(compatibility["source"])),
                "registry",
                StringComparison.Ordinal))
        {
            throw new InvalidDataException(
                $"{CompatibilityManifestName} must identify Registry as its source.");
        }

        string canonicalVersion = RequireAliasString(
            canonical,
            "version",
            "releaseVersion",
            CanonicalManifestName);
        string canonicalChannel = RequireAliasString(
            canonical,
            "channel",
            "channelId",
            CanonicalManifestName);
        RequireEqual(
            compatibilityManifest.Version,
            canonicalVersion,
            "release version");
        string compatibilityRolloutState = NormalizeToken(GetJsonString(compatibility["rolloutState"]));
        string expectedCompatibilityChannel = compatibilityRolloutState is
            "public_stable" or "stable" or "preview" or "local" or "docker"
                ? compatibilityRolloutState
                : canonicalChannel;
        RequireEqual(
            compatibilityManifest.Channel,
            expectedCompatibilityChannel,
            "release channel projection");
        RequireEqual(
            NormalizeToken(compatibilityManifest.Status),
            NormalizeToken(GetJsonString(canonical["status"])),
            "publication status");

        DateTimeOffset canonicalPublishedAt = RequireTimestamp(
            canonical,
            "publishedAt",
            CanonicalManifestName);
        if (canonicalPublishedAt.ToUniversalTime() != compatibilityManifest.PublishedAt.ToUniversalTime())
        {
            throw new InvalidDataException(
                "Registry canonical and compatibility manifests disagree about publishedAt.");
        }

        foreach (string fieldName in new[]
                 {
                     "rolloutState",
                     "rolloutReason",
                     "supportabilityState",
                     "supportabilitySummary",
                     "knownIssueSummary",
                     "fixAvailabilitySummary"
                 })
        {
            RequireEqual(
                GetJsonString(compatibility[fieldName]),
                GetJsonString(canonical[fieldName]),
                fieldName);
        }

        RequireEqualJsonProjection(
            compatibility["releaseProof"],
            canonical["releaseProof"],
            "releaseProof");
        RequireEqualJsonProjection(
            compatibility["desktopTupleCoverage"],
            canonical["desktopTupleCoverage"],
            "desktopTupleCoverage");
        ValidateRegistryArtifactProjection(compatibility, canonical);
        ValidateCanonicalPlatformFloor(canonical, canonicalArtifacts);
    }

    private static void RequireRegistryContract(JsonObject manifest, string label)
    {
        string contractName = GetJsonString(manifest["contractName"]) ?? string.Empty;
        string contractNameAlias = GetJsonString(manifest["contract_name"]) ?? string.Empty;
        if (!string.Equals(contractName, RegistryContractName, StringComparison.Ordinal)
            || !string.Equals(contractNameAlias, RegistryContractName, StringComparison.Ordinal))
        {
            throw new InvalidDataException(
                $"{label} must be materialized by {RegistryContractName} and preserve both contract aliases.");
        }
    }

    private static string RequireAliasString(
        JsonObject source,
        string firstName,
        string secondName,
        string label)
    {
        string first = GetJsonString(source[firstName])?.Trim() ?? string.Empty;
        string second = GetJsonString(source[secondName])?.Trim() ?? string.Empty;
        if (first.Length == 0 || second.Length == 0 || !string.Equals(first, second, StringComparison.Ordinal))
        {
            throw new InvalidDataException(
                $"{label} must preserve equal non-empty {firstName}/{secondName} aliases.");
        }

        return first;
    }

    private static DateTimeOffset RequireTimestamp(JsonObject source, string propertyName, string label)
    {
        string raw = GetJsonString(source[propertyName])?.Trim() ?? string.Empty;
        if (!DateTimeOffset.TryParse(
                raw,
                System.Globalization.CultureInfo.InvariantCulture,
                System.Globalization.DateTimeStyles.AssumeUniversal,
                out DateTimeOffset parsed))
        {
            throw new InvalidDataException($"{label} {propertyName} must be an ISO-8601 timestamp.");
        }

        return parsed;
    }

    private static void RequireEqual(string? left, string? right, string fieldName)
    {
        if (!string.Equals(left?.Trim(), right?.Trim(), StringComparison.Ordinal))
        {
            throw new InvalidDataException(
                $"Registry canonical and compatibility manifests disagree about {fieldName}.");
        }
    }

    private static void RequireEqualJsonProjection(JsonNode? left, JsonNode? right, string fieldName)
    {
        if (left is null || right is null || !JsonNode.DeepEquals(left, right))
        {
            throw new InvalidDataException(
                $"Registry canonical and compatibility manifests disagree about {fieldName}.");
        }
    }

    private static void ValidateRegistryArtifactProjection(JsonObject compatibility, JsonObject canonical)
    {
        if (compatibility["downloads"] is not JsonArray downloads
            || canonical["artifacts"] is not JsonArray artifacts)
        {
            throw new InvalidDataException(
                "Registry manifest pair must contain compatibility downloads and canonical artifacts.");
        }

        Dictionary<string, JsonObject> compatibilityById = IndexArtifactRows(
            downloads,
            CompatibilityManifestName);
        Dictionary<string, JsonObject> canonicalById = IndexArtifactRows(
            artifacts,
            CanonicalManifestName);
        if (!compatibilityById.Keys.Order(StringComparer.Ordinal).SequenceEqual(
                canonicalById.Keys.Order(StringComparer.Ordinal),
                StringComparer.Ordinal))
        {
            throw new InvalidDataException(
                "Registry canonical and compatibility manifests expose different artifact ids.");
        }

        foreach ((string artifactId, JsonObject canonicalArtifact) in canonicalById)
        {
            JsonObject compatibilityArtifact = compatibilityById[artifactId];
            RequireArtifactFieldEqual(canonicalArtifact, compatibilityArtifact, "head", artifactId);
            RequireArtifactFieldEqual(canonicalArtifact, compatibilityArtifact, "platform", artifactId);
            RequireArtifactFieldEqual(canonicalArtifact, compatibilityArtifact, "rid", artifactId);
            RequireArtifactFieldEqual(canonicalArtifact, compatibilityArtifact, "arch", artifactId);
            RequireArtifactFieldEqual(canonicalArtifact, compatibilityArtifact, "kind", artifactId);
            RequireArtifactFieldEqual(canonicalArtifact, compatibilityArtifact, "fileName", artifactId, normalize: false);
            RequireArtifactFieldEqual(canonicalArtifact, compatibilityArtifact, "sha256", artifactId);
            RequireArtifactFieldEqual(canonicalArtifact, compatibilityArtifact, "installAccessClass", artifactId);
            RequireArtifactAliasFieldEqual(
                canonicalArtifact,
                compatibilityArtifact,
                "downloadUrl",
                "url",
                artifactId,
                normalize: false);
            RequireArtifactAliasFieldEqual(
                canonicalArtifact,
                compatibilityArtifact,
                "version",
                "version",
                artifactId,
                normalize: false);
            RequireArtifactAliasFieldEqual(
                canonicalArtifact,
                compatibilityArtifact,
                "channelId",
                "channelId",
                artifactId);
            long canonicalSize = GetJsonInt64(canonicalArtifact["sizeBytes"]);
            long compatibilitySize = GetJsonInt64(compatibilityArtifact["sizeBytes"]);
            if (canonicalSize <= 0 || canonicalSize != compatibilitySize)
            {
                throw new InvalidDataException(
                    $"Registry canonical and compatibility manifests disagree about artifact {artifactId} sizeBytes.");
            }
        }
    }

    private static Dictionary<string, JsonObject> IndexArtifactRows(JsonArray rows, string label)
    {
        var indexed = new Dictionary<string, JsonObject>(StringComparer.Ordinal);
        foreach (JsonObject row in rows.OfType<JsonObject>())
        {
            string artifactId = (GetJsonString(row["artifactId"])
                                 ?? GetJsonString(row["id"])
                                 ?? string.Empty).Trim();
            if (artifactId.Length == 0 || !indexed.TryAdd(artifactId, row))
            {
                throw new InvalidDataException($"{label} contains a missing or duplicate artifact id.");
            }
        }

        if (indexed.Count != rows.Count)
        {
            throw new InvalidDataException($"{label} contains a non-object artifact row.");
        }

        return indexed;
    }

    private static void RequireArtifactFieldEqual(
        JsonObject canonical,
        JsonObject compatibility,
        string fieldName,
        string artifactId,
        bool normalize = true)
        => RequireArtifactAliasFieldEqual(
            canonical,
            compatibility,
            fieldName,
            fieldName,
            artifactId,
            normalize);

    private static void RequireArtifactAliasFieldEqual(
        JsonObject canonical,
        JsonObject compatibility,
        string canonicalFieldName,
        string compatibilityFieldName,
        string artifactId,
        bool normalize = true)
    {
        string canonicalValue = GetJsonString(canonical[canonicalFieldName])?.Trim() ?? string.Empty;
        string compatibilityValue = GetJsonString(compatibility[compatibilityFieldName])?.Trim() ?? string.Empty;
        if (normalize)
        {
            canonicalValue = NormalizeToken(canonicalValue);
            compatibilityValue = NormalizeToken(compatibilityValue);
        }

        if (canonicalValue.Length == 0
            || !string.Equals(canonicalValue, compatibilityValue, StringComparison.Ordinal))
        {
            throw new InvalidDataException(
                $"Registry canonical and compatibility manifests disagree about artifact {artifactId} {canonicalFieldName}.");
        }
    }

    private static void ValidateCanonicalPlatformFloor(
        JsonObject canonical,
        IReadOnlyList<CanonicalArtifactRecord> canonicalArtifacts)
    {
        JsonObject coverage = canonical["desktopTupleCoverage"] as JsonObject
            ?? throw new InvalidDataException(
                $"{CanonicalManifestName} must contain Registry desktopTupleCoverage.");
        RequireExactStringArray(
            coverage,
            "requiredDesktopPlatforms",
            RequiredDesktopPlatforms,
            "canonical desktop platform floor");
        RequireExactStringArray(
            coverage,
            "requiredDesktopHeads",
            RequiredDesktopHeads,
            "canonical desktop head floor");
        RequireExactStringArray(
            coverage,
            "requiredDesktopPlatformHeadRidTuples",
            RequiredDesktopPlatformHeadRidTuples,
            "canonical desktop platform/head/RID floor");

        HashSet<string> promotedPlatforms = new(StringComparer.Ordinal);
        HashSet<string> promotedHeads = new(StringComparer.Ordinal);
        HashSet<string> promotedPairs = new(StringComparer.Ordinal);
        HashSet<string> promotedRequiredTuples = new(StringComparer.Ordinal);
        HashSet<string> promotedAllTuples = new(StringComparer.Ordinal);
        HashSet<string> promotedInstallerTupleIds = new(StringComparer.Ordinal);
        foreach (CanonicalArtifactRecord artifact in canonicalArtifacts)
        {
            string platform = NormalizePlatform(artifact.Platform);
            string head = NormalizeToken(artifact.Head);
            string rid = NormalizeToken(artifact.Rid);
            if (rid.Length == 0)
            {
                rid = RidForPlatformAndArch(platform, NormalizeToken(artifact.Arch));
            }

            if (!RequiredDesktopPlatforms.Contains(platform, StringComparer.Ordinal)
                || !IsPromotedDesktopInstaller(artifact, platform)
                || head.Length == 0
                || rid.Length == 0)
            {
                continue;
            }

            promotedPlatforms.Add(platform);
            promotedHeads.Add(head);
            promotedPairs.Add($"{head}:{platform}");
            promotedAllTuples.Add($"{head}:{rid}:{platform}");
            promotedInstallerTupleIds.Add($"{head}:{platform}:{rid}");
            if (RequiredDesktopHeads.Contains(head, StringComparer.Ordinal))
            {
                promotedRequiredTuples.Add($"{head}:{rid}:{platform}");
            }
        }

        string[] missingPlatforms = RequiredDesktopPlatforms
            .Where(platform => !promotedPlatforms.Contains(platform))
            .ToArray();
        string[] missingHeads = RequiredDesktopHeads
            .Where(head => !promotedHeads.Contains(head))
            .ToArray();
        string[] missingPairs = RequiredDesktopPlatforms
            .SelectMany(platform => RequiredDesktopHeads.Select(head => $"{head}:{platform}"))
            .Where(pair => !promotedPairs.Contains(pair))
            .ToArray();
        string[] missingTuples = RequiredDesktopPlatformHeadRidTuples
            .Where(tuple => !promotedRequiredTuples.Contains(tuple))
            .ToArray();

        RequireExactStringArray(coverage, "missingRequiredPlatforms", missingPlatforms, "missing platform truth");
        RequireExactStringArray(coverage, "missingRequiredHeads", missingHeads, "missing head truth");
        RequireExactStringArray(coverage, "missingRequiredPlatformHeadPairs", missingPairs, "missing platform/head truth");
        RequireExactStringArray(coverage, "missingRequiredPlatformHeadRidTuples", missingTuples, "missing platform/head/RID truth");
        RequireExactStringArray(
            coverage,
            "promotedPlatformHeadRidTuples",
            promotedAllTuples.Order(StringComparer.Ordinal).ToArray(),
            "promoted platform/head/RID truth");

        string[] reportedInstallerTupleIds = ReadObjectStringArray(
                coverage,
                "promotedInstallerTuples",
                "tupleId")
            .Order(StringComparer.Ordinal)
            .ToArray();
        if (!reportedInstallerTupleIds.SequenceEqual(
                promotedInstallerTupleIds.Order(StringComparer.Ordinal),
                StringComparer.Ordinal))
        {
            throw new InvalidDataException(
                $"{CanonicalManifestName} desktopTupleCoverage.promotedInstallerTuples disagrees with Registry artifacts.");
        }

        bool expectedComplete = missingTuples.Length == 0;
        if (!TryGetJsonBoolean(coverage["complete"], out bool reportedComplete)
            || reportedComplete != expectedComplete)
        {
            throw new InvalidDataException(
                $"{CanonicalManifestName} desktopTupleCoverage.complete disagrees with the canonical platform floor.");
        }

        ValidateCanonicalPostureFloors(canonical, expectedComplete);
    }

    private static bool IsPromotedDesktopInstaller(CanonicalArtifactRecord artifact, string platform)
    {
        if (NormalizeToken(artifact.Status) == "revoked"
            || NormalizeToken(artifact.RolloutState) == "revoked"
            || NormalizeToken(artifact.RevokeState) == "revoked")
        {
            return false;
        }

        string kind = NormalizeToken(artifact.Kind);
        return platform == "macos"
            ? kind is "installer" or "dmg" or "pkg"
            : kind == "installer";
    }

    private static string RidForPlatformAndArch(string platform, string arch)
        => (platform, arch) switch
        {
            ("linux", "arm64") => "linux-arm64",
            ("linux", _) => "linux-x64",
            ("windows", "arm64") => "win-arm64",
            ("windows", _) => "win-x64",
            ("macos", "x64") => "osx-x64",
            ("macos", _) => "osx-arm64",
            _ => string.Empty
        };

    private static void ValidateCanonicalPostureFloors(JsonObject canonical, bool desktopCoverageComplete)
    {
        string status = NormalizeToken(GetJsonString(canonical["status"]));
        if (status != "published")
        {
            return;
        }

        string rolloutState = NormalizeToken(GetJsonString(canonical["rolloutState"]));
        string supportabilityState = NormalizeToken(GetJsonString(canonical["supportabilityState"]));
        JsonObject publicTrustMetrics = canonical["publicTrustMetrics"] as JsonObject
            ?? throw new InvalidDataException($"{CanonicalManifestName} must contain publicTrustMetrics.");
        JsonObject trustReleaseChannel = publicTrustMetrics["releaseChannel"] as JsonObject
            ?? throw new InvalidDataException(
                $"{CanonicalManifestName} must contain publicTrustMetrics.releaseChannel.");
        JsonObject proofFreshness = publicTrustMetrics["proofFreshness"] as JsonObject
            ?? throw new InvalidDataException(
                $"{CanonicalManifestName} must contain publicTrustMetrics.proofFreshness.");
        JsonObject registryBoundary = canonical["registryBoundaryCoverage"] as JsonObject
            ?? throw new InvalidDataException($"{CanonicalManifestName} must contain registryBoundaryCoverage.");
        if (NormalizeToken(GetJsonString(registryBoundary["owner"])) != "chummer6-hub-registry"
            || NormalizeToken(GetJsonString(registryBoundary["status"])) != "closed")
        {
            throw new InvalidDataException(
                $"{CanonicalManifestName} registryBoundaryCoverage must be closed and owned by chummer6-hub-registry.");
        }

        JsonObject registryReleaseChannel = registryBoundary["releaseChannel"] as JsonObject
            ?? throw new InvalidDataException(
                $"{CanonicalManifestName} must contain registryBoundaryCoverage.releaseChannel.");

        string trustSupportability = NormalizeToken(GetJsonString(trustReleaseChannel["supportabilityState"]));
        string registrySupportability = NormalizeToken(GetJsonString(registryReleaseChannel["supportabilityState"]));
        if (supportabilityState.Length == 0
            || trustSupportability != supportabilityState
            || registrySupportability != supportabilityState)
        {
            throw new InvalidDataException(
                $"{CanonicalManifestName} supportabilityState must agree across Registry truth projections.");
        }

        if (!TryGetJsonBoolean(registryReleaseChannel["desktopTupleComplete"], out bool registryComplete)
            || registryComplete != desktopCoverageComplete)
        {
            throw new InvalidDataException(
                $"{CanonicalManifestName} registryBoundaryCoverage.releaseChannel.desktopTupleComplete disagrees with desktopTupleCoverage.");
        }

        if (!desktopCoverageComplete)
        {
            if (rolloutState != "coverage_incomplete" || supportabilityState != "review_required")
            {
                throw new InvalidDataException(
                    $"{CanonicalManifestName} must remain coverage_incomplete/review_required while the canonical desktop floor is incomplete.");
            }

            return;
        }

        string freshnessStatus = NormalizeToken(GetJsonString(proofFreshness["status"]));
        if (freshnessStatus is not "stale" and not "missing")
        {
            return;
        }

        if (rolloutState != "public_release_review_required"
            || supportabilityState != "review_required"
            || NormalizeToken(GetJsonString(trustReleaseChannel["posture"])) != "blocked"
            || NormalizeToken(GetJsonString(registryReleaseChannel["publicTrustPosture"])) != "blocked")
        {
            throw new InvalidDataException(
                $"{CanonicalManifestName} stale or missing proof freshness must stay review-required with blocked public trust posture.");
        }

        foreach (string fieldName in new[]
                 {
                     "rolloutReason",
                     "supportabilitySummary",
                     "knownIssueSummary",
                     "fixAvailabilitySummary"
                 })
        {
            if (!(GetJsonString(canonical[fieldName]) ?? string.Empty).Contains(
                    "stale or incomplete proof receipts",
                    StringComparison.OrdinalIgnoreCase))
            {
                throw new InvalidDataException(
                    $"{CanonicalManifestName} {fieldName} must explain stale or incomplete proof receipts.");
            }
        }
    }

    private static void RequireExactStringArray(
        JsonObject source,
        string propertyName,
        IReadOnlyList<string> expected,
        string description)
    {
        string[] actual = ReadStringArray(source, propertyName);
        if (!actual.SequenceEqual(expected, StringComparer.Ordinal))
        {
            throw new InvalidDataException(
                $"{CanonicalManifestName} desktopTupleCoverage.{propertyName} does not match {description}.");
        }
    }

    private static string[] ReadStringArray(JsonObject source, string propertyName)
    {
        if (source[propertyName] is not JsonArray array)
        {
            throw new InvalidDataException(
                $"{CanonicalManifestName} desktopTupleCoverage.{propertyName} must be an array.");
        }

        string[] values = array
            .Select(GetJsonString)
            .Where(static value => value is not null)
            .Select(static value => value!.Trim())
            .ToArray();
        if (values.Length != array.Count || values.Any(static value => value.Length == 0))
        {
            throw new InvalidDataException(
                $"{CanonicalManifestName} desktopTupleCoverage.{propertyName} must contain non-empty strings.");
        }

        return values;
    }

    private static string[] ReadObjectStringArray(
        JsonObject source,
        string propertyName,
        string childPropertyName)
    {
        if (source[propertyName] is not JsonArray array)
        {
            throw new InvalidDataException(
                $"{CanonicalManifestName} desktopTupleCoverage.{propertyName} must be an array.");
        }

        string[] values = array
            .OfType<JsonObject>()
            .Select(row => GetJsonString(row[childPropertyName])?.Trim() ?? string.Empty)
            .ToArray();
        if (values.Length != array.Count || values.Any(static value => value.Length == 0))
        {
            throw new InvalidDataException(
                $"{CanonicalManifestName} desktopTupleCoverage.{propertyName} contains an invalid row.");
        }

        return values;
    }

    private static bool TryGetJsonBoolean(JsonNode? node, out bool value)
    {
        value = false;
        if (node is JsonValue jsonValue && jsonValue.TryGetValue<bool>(out value))
        {
            return true;
        }

        return bool.TryParse(GetJsonString(node), out value);
    }

    private static long GetJsonInt64(JsonNode? node)
    {
        if (node is JsonValue jsonValue && jsonValue.TryGetValue<long>(out long value))
        {
            return value;
        }

        return long.TryParse(GetJsonString(node), out value) ? value : 0;
    }

    private static void ValidateIncomingBundle(
        PublicReleaseManifestDto compatibilityManifest,
        IReadOnlyList<CanonicalArtifactRecord> canonicalArtifacts,
        string filesRoot,
        string? startupSmokeRoot,
        string? promotionEvidencePath)
    {
        if (compatibilityManifest.Downloads.Count == 0)
        {
            throw new InvalidDataException("bundle contains no downloadable artifacts.");
        }

        Dictionary<string, PublicReleaseArtifactDto> compatibilityById = compatibilityManifest.Downloads
            .ToDictionary(static artifact => artifact.Id, StringComparer.OrdinalIgnoreCase);
        Dictionary<string, CanonicalArtifactRecord> canonicalById = canonicalArtifacts
            .ToDictionary(static artifact => artifact.ArtifactId, StringComparer.OrdinalIgnoreCase);

        foreach (string artifactId in compatibilityById.Keys)
        {
            if (!canonicalById.ContainsKey(artifactId))
            {
                throw new InvalidDataException($"bundle manifests disagree about artifact id {artifactId}.");
            }
        }

        foreach (CanonicalArtifactRecord artifact in canonicalArtifacts)
        {
            if (!compatibilityById.ContainsKey(artifact.ArtifactId))
            {
                throw new InvalidDataException($"bundle manifests disagree about artifact id {artifact.ArtifactId}.");
            }

            string fileName = ResolveArtifactFileName(artifact.FileName, artifact.DownloadUrl);
            string filePath = Path.Combine(filesRoot, fileName);
            if (!File.Exists(filePath))
            {
                throw new InvalidDataException($"bundle is missing artifact file {fileName} for {artifact.ArtifactId}.");
            }

            long actualSize = new FileInfo(filePath).Length;
            if (artifact.SizeBytes.HasValue && artifact.SizeBytes.Value != actualSize)
            {
                throw new InvalidDataException($"artifact size mismatch for {artifact.ArtifactId}: expected {artifact.SizeBytes.Value}, got {actualSize}.");
            }

            string actualSha = Sha256For(filePath);
            if (!string.IsNullOrWhiteSpace(artifact.Sha256) && !string.Equals(artifact.Sha256, actualSha, StringComparison.OrdinalIgnoreCase))
            {
                throw new InvalidDataException($"artifact digest mismatch for {artifact.ArtifactId}.");
            }
        }

        List<CanonicalArtifactRecord> installerArtifacts = canonicalArtifacts.Where(IsInstallerArtifact).ToList();
        if (installerArtifacts.Count == 0)
        {
            return;
        }

        if (string.IsNullOrWhiteSpace(startupSmokeRoot) || !Directory.Exists(startupSmokeRoot))
        {
            throw new InvalidDataException("bundle is missing startup-smoke receipts for installer promotion.");
        }

        IReadOnlyList<StartupSmokeReceipt> startupSmokeReceipts = LoadStartupSmokeReceipts(startupSmokeRoot);
        PromotionEvidenceDocument promotionEvidence = LoadPromotionEvidence(promotionEvidencePath);

        foreach (CanonicalArtifactRecord artifact in installerArtifacts)
        {
            ValidateStartupSmokeReceipt(artifact, startupSmokeReceipts);
            ValidatePromotionEvidence(artifact, promotionEvidence, compatibilityManifest.Channel);
        }
    }

    private static IReadOnlyList<StartupSmokeReceipt> LoadStartupSmokeReceipts(string startupSmokeRoot)
    {
        List<StartupSmokeReceipt> receipts = new();
        foreach (string path in Directory.GetFiles(startupSmokeRoot, "startup-smoke-*.receipt.json", SearchOption.AllDirectories))
        {
            StartupSmokeReceipt? receipt = JsonSerializer.Deserialize<StartupSmokeReceipt>(File.ReadAllText(path), JsonOptions);
            if (receipt is null
                || string.IsNullOrWhiteSpace(receipt.HeadId)
                || string.IsNullOrWhiteSpace(receipt.Platform)
                || string.IsNullOrWhiteSpace(receipt.Arch))
            {
                continue;
            }

            receipts.Add(receipt);
        }

        return receipts;
    }

    private static PromotionEvidenceDocument LoadPromotionEvidence(string? promotionEvidencePath)
    {
        if (string.IsNullOrWhiteSpace(promotionEvidencePath) || !File.Exists(promotionEvidencePath))
        {
            throw new InvalidDataException("bundle is missing release-evidence/public-promotion.json.");
        }

        PromotionEvidenceDocument? evidence = JsonSerializer.Deserialize<PromotionEvidenceDocument>(File.ReadAllText(promotionEvidencePath), JsonOptions);
        if (evidence is null
            || !string.Equals(evidence.ContractName, "chummer.run.desktop_release_publication", StringComparison.Ordinal))
        {
            throw new InvalidDataException("bundle promotion evidence is missing or malformed.");
        }

        return evidence;
    }

    private static void ValidateStartupSmokeReceipt(CanonicalArtifactRecord artifact, IReadOnlyList<StartupSmokeReceipt> receipts)
    {
        string expectedPlatform = NormalizePlatform(artifact.Platform);
        string expectedArch = (artifact.Arch ?? string.Empty).Trim().ToLowerInvariant();
        string expectedHead = (artifact.Head ?? string.Empty).Trim();
        string expectedDigest = NormalizeArtifactDigest(artifact.Sha256);

        List<StartupSmokeReceipt> matches = receipts
            .Where(receipt =>
                string.Equals(receipt.HeadId, expectedHead, StringComparison.OrdinalIgnoreCase)
                && string.Equals(NormalizePlatform(receipt.Platform), expectedPlatform, StringComparison.OrdinalIgnoreCase)
                && string.Equals(receipt.Arch, expectedArch, StringComparison.OrdinalIgnoreCase))
            .ToList();
        if (matches.Count == 0)
        {
            throw new InvalidDataException($"startup smoke receipt is missing for {artifact.ArtifactId}.");
        }

        if (expectedDigest.Length == 0)
        {
            return;
        }

        bool digestMatches = matches.Any(receipt =>
            string.Equals(NormalizeArtifactDigest(receipt.ArtifactDigest), expectedDigest, StringComparison.OrdinalIgnoreCase)
            || string.Equals(NormalizeArtifactDigest(receipt.ArtifactSha256), expectedDigest, StringComparison.OrdinalIgnoreCase));
        if (!digestMatches)
        {
            throw new InvalidDataException($"startup smoke receipts for {artifact.ArtifactId} do not match the uploaded artifact digest.");
        }
    }

    private static void ValidatePromotionEvidence(CanonicalArtifactRecord artifact, PromotionEvidenceDocument evidence, string? channel)
    {
        PromotionArtifactEvidence? artifactEvidence = evidence.Artifacts.FirstOrDefault(item =>
            string.Equals(item.ArtifactId, artifact.ArtifactId, StringComparison.OrdinalIgnoreCase)
            || string.Equals(item.FileName, ResolveArtifactFileName(artifact.FileName, artifact.DownloadUrl), StringComparison.OrdinalIgnoreCase));
        if (artifactEvidence is null)
        {
            throw new InvalidDataException($"promotion evidence is missing for {artifact.ArtifactId}.");
        }

        if (!string.Equals(artifactEvidence.PromotionStatus, "pass", StringComparison.OrdinalIgnoreCase))
        {
            throw new InvalidDataException($"promotion evidence did not pass for {artifact.ArtifactId}.");
        }

        if (!string.Equals(artifactEvidence.StartupSmokeStatus, "pass", StringComparison.OrdinalIgnoreCase)
            && !string.Equals(artifactEvidence.StartupSmokeStatus, "skipped_incompatible_host", StringComparison.OrdinalIgnoreCase))
        {
            throw new InvalidDataException($"startup smoke evidence did not pass for {artifact.ArtifactId}.");
        }

        string platform = NormalizePlatform(artifact.Platform);
        if (string.Equals(platform, "windows", StringComparison.OrdinalIgnoreCase)
            && !string.Equals(artifactEvidence.SigningStatus, "pass", StringComparison.OrdinalIgnoreCase))
        {
            bool previewUnsignedAllowed =
                string.Equals(channel, "preview", StringComparison.OrdinalIgnoreCase)
                && string.Equals(artifactEvidence.SigningStatus, "skipped_preview", StringComparison.OrdinalIgnoreCase);
            bool explicitUnsignedReleaseAllowed =
                !string.Equals(channel, "preview", StringComparison.OrdinalIgnoreCase)
                && string.Equals(artifactEvidence.SigningStatus, "unsigned_public_release", StringComparison.OrdinalIgnoreCase);

            if (!previewUnsignedAllowed && !explicitUnsignedReleaseAllowed)
            {
                throw new InvalidDataException($"windows promotion requires signing proof for {artifact.ArtifactId}.");
            }
        }

        if (string.Equals(platform, "macos", StringComparison.OrdinalIgnoreCase))
        {
            bool previewUnsignedAllowed =
                string.Equals(channel, "preview", StringComparison.OrdinalIgnoreCase)
                && string.Equals(artifactEvidence.SigningStatus, "skipped_preview", StringComparison.OrdinalIgnoreCase)
                && string.Equals(artifactEvidence.NotarizationStatus, "skipped_preview", StringComparison.OrdinalIgnoreCase);

            if (previewUnsignedAllowed)
            {
                return;
            }

            if (!string.Equals(artifactEvidence.SigningStatus, "pass", StringComparison.OrdinalIgnoreCase))
            {
                throw new InvalidDataException($"macOS promotion requires signing proof for {artifact.ArtifactId}.");
            }

            if (!string.Equals(artifactEvidence.NotarizationStatus, "pass", StringComparison.OrdinalIgnoreCase))
            {
                throw new InvalidDataException($"macOS promotion requires notarization proof for {artifact.ArtifactId}.");
            }
        }
    }

    private static PublicReleaseManifestDto MergeCompatibilityManifest(
        PublicReleaseManifestDto? existingManifest,
        PublicReleaseManifestDto incomingManifest)
    {
        return incomingManifest;
    }

    private static JsonObject MergeCanonicalManifest(JsonObject? existingManifest, JsonObject incomingManifest)
    {
        return incomingManifest.DeepClone().AsObject();
    }

    private static (PublicReleaseManifestDto CompatibilityManifest, JsonObject CanonicalManifest) NormalizeMergedShelfProjection(
        PublicReleaseManifestDto mergedCompatibilityManifest,
        JsonObject mergedCanonicalManifest)
    {
        string normalizedProofStatus = NormalizeReleaseProofForPublication(
            mergedCanonicalManifest,
            mergedCompatibilityManifest.PublishedAt);
        string canonicalChannel = NormalizeToken(mergedCompatibilityManifest.Channel);
        string canonicalVersion = mergedCompatibilityManifest.Version?.Trim() ?? string.Empty;
        JsonArray mergedArtifacts = mergedCanonicalManifest["artifacts"] as JsonArray ?? [];
        JsonObject coverage = BuildDesktopTupleCoverage(
            mergedArtifacts,
            mergedCompatibilityManifest.DesktopTupleCoverage,
            channelStatus: mergedCompatibilityManifest.Status,
            rolloutState: mergedCompatibilityManifest.RolloutState,
            rolloutReason: mergedCompatibilityManifest.RolloutReason,
            knownIssueSummary: mergedCompatibilityManifest.KnownIssueSummary);

        bool desktopCoverageComplete = DesktopTupleCoverageIsComplete(coverage);
        string proofStatus = normalizedProofStatus;
        IReadOnlyList<string> proofJourneys = ExtractProofJourneys(mergedCanonicalManifest);
        bool proofPassed = ProofPassed(proofStatus);
        string rolloutState = DeriveRolloutState(
            mergedCompatibilityManifest.Channel,
            mergedCompatibilityManifest.Status,
            proofPassed,
            desktopCoverageComplete);
        string rolloutReason = DeriveRolloutReason(
            mergedCompatibilityManifest.Channel,
            mergedCompatibilityManifest.Status,
            proofPassed,
            desktopCoverageComplete,
            coverage);
        string supportabilityState = DeriveSupportabilityState(
            mergedCompatibilityManifest.Channel,
            mergedCompatibilityManifest.Status,
            proofPassed,
            desktopCoverageComplete);
        string supportabilitySummary = DeriveSupportabilitySummary(
            mergedCompatibilityManifest.Channel,
            mergedCompatibilityManifest.Status,
            proofPassed,
            desktopCoverageComplete,
            coverage,
            proofJourneys);
        string knownIssueSummary = DeriveKnownIssueSummary(
            mergedCompatibilityManifest.Channel,
            mergedCompatibilityManifest.Status,
            proofPassed,
            desktopCoverageComplete,
            coverage,
            proofJourneys);
        string fixAvailabilitySummary = DeriveFixAvailabilitySummary(
            mergedCompatibilityManifest.Status,
            proofPassed,
            desktopCoverageComplete);

        PublicReleaseManifestDto normalizedCompatibilityManifest = mergedCompatibilityManifest with
        {
            RolloutState = rolloutState,
            RolloutReason = rolloutReason,
            SupportabilityState = supportabilityState,
            SupportabilitySummary = supportabilitySummary,
            KnownIssueSummary = knownIssueSummary,
            FixAvailabilitySummary = fixAvailabilitySummary,
            ProofStatus = string.IsNullOrWhiteSpace(proofStatus)
                ? null
                : proofStatus,
            DesktopTupleCoverage = JsonSerializer.SerializeToElement(coverage, JsonOptions)
        };

        JsonObject normalizedCanonicalManifest = mergedCanonicalManifest.DeepClone().AsObject();
        JsonArray normalizedArtifacts = normalizedCanonicalManifest["artifacts"] as JsonArray ?? [];
        if (!string.IsNullOrWhiteSpace(canonicalChannel))
        {
            normalizedCanonicalManifest["channel"] = canonicalChannel;
            normalizedCanonicalManifest["channelId"] = canonicalChannel;
            foreach (JsonObject artifact in normalizedArtifacts.OfType<JsonObject>())
            {
                artifact["channel"] = canonicalChannel;
                artifact["channelId"] = canonicalChannel;
            }
        }

        if (!string.IsNullOrWhiteSpace(canonicalVersion))
        {
            normalizedCanonicalManifest["version"] = canonicalVersion;
            foreach (JsonObject artifact in normalizedArtifacts.OfType<JsonObject>())
            {
                artifact["version"] = canonicalVersion;
                artifact["releaseVersion"] = canonicalVersion;
            }
        }

        normalizedCanonicalManifest["desktopTupleCoverage"] = coverage.DeepClone();
        normalizedCanonicalManifest["installAwareArtifactRegistry"] = BuildInstallAwareArtifactRegistry(
            normalizedArtifacts,
            coverage,
            canonicalChannel,
            canonicalVersion);
        normalizedCanonicalManifest["rolloutState"] = rolloutState;
        normalizedCanonicalManifest["rolloutReason"] = rolloutReason;
        normalizedCanonicalManifest["supportabilityState"] = supportabilityState;
        normalizedCanonicalManifest["supportabilitySummary"] = supportabilitySummary;
        normalizedCanonicalManifest["knownIssueSummary"] = knownIssueSummary;
        normalizedCanonicalManifest["fixAvailabilitySummary"] = fixAvailabilitySummary;
        RefreshPublicTrustReleaseChannelMetrics(
            normalizedCanonicalManifest,
            coverage,
            canonicalChannel,
            GetJsonString(normalizedCanonicalManifest["status"]) ?? normalizedCompatibilityManifest.Status ?? string.Empty,
            rolloutState,
            supportabilityState);
        JsonObject registryBoundaryCoverage = NormalizeRegistryBoundaryCoverage(
            normalizedCanonicalManifest["registryBoundaryCoverage"] as JsonObject,
            normalizedCompatibilityManifest.Downloads.Count,
            normalizedCanonicalManifest,
            coverage,
            canonicalChannel,
            canonicalVersion,
            GetJsonString(normalizedCanonicalManifest["status"]) ?? normalizedCompatibilityManifest.Status ?? string.Empty,
            rolloutState,
            supportabilityState);
        normalizedCanonicalManifest["registryBoundaryCoverage"] = registryBoundaryCoverage.DeepClone();
        normalizedCompatibilityManifest = normalizedCompatibilityManifest with
        {
            RegistryBoundaryCoverage = JsonSerializer.SerializeToElement(registryBoundaryCoverage, JsonOptions)
        };

        return (normalizedCompatibilityManifest, normalizedCanonicalManifest);
    }

    private static void RefreshPublicTrustReleaseChannelMetrics(
        JsonObject manifest,
        JsonObject coverage,
        string channelId,
        string status,
        string rolloutState,
        string supportabilityState)
    {
        JsonObject metrics = manifest["publicTrustMetrics"] as JsonObject ?? new JsonObject();
        JsonObject releaseChannel = metrics["releaseChannel"] as JsonObject ?? new JsonObject();

        int recommendedRouteCount = GetJsonInt32(releaseChannel["recommendedRouteCount"]);
        int fallbackRouteCount = GetJsonInt32(releaseChannel["fallbackRecoveryRouteCount"]);
        int blockedRouteCount = GetJsonInt32(releaseChannel["blockedRouteCount"]);
        int revokedRouteCount = GetJsonInt32(releaseChannel["revokedRouteCount"]);

        if (coverage["desktopRouteTruth"] is JsonArray routeTruth)
        {
            List<JsonObject> rows = routeTruth.OfType<JsonObject>().ToList();
            recommendedRouteCount = rows.Count(static row =>
                string.Equals(NormalizeToken(GetJsonString(row["routeRole"])), "primary", StringComparison.Ordinal)
                && string.Equals(NormalizeToken(GetJsonString(row["promotionState"])), "promoted", StringComparison.Ordinal)
                && !string.Equals(NormalizeToken(GetJsonString(row["revokeState"])), "revoked", StringComparison.Ordinal));
            fallbackRouteCount = rows.Count(static row =>
                string.Equals(NormalizeToken(GetJsonString(row["routeRole"])), "fallback", StringComparison.Ordinal)
                && string.Equals(NormalizeToken(GetJsonString(row["promotionState"])), "promoted", StringComparison.Ordinal)
                && !string.Equals(NormalizeToken(GetJsonString(row["revokeState"])), "revoked", StringComparison.Ordinal));
            revokedRouteCount = rows.Count(static row =>
                string.Equals(NormalizeToken(GetJsonString(row["revokeState"])), "revoked", StringComparison.Ordinal));
            blockedRouteCount = rows.Count(static row =>
                !RouteTruthIsPreviewOnlyFallback(row)
                && !string.Equals(NormalizeToken(GetJsonString(row["revokeState"])), "revoked", StringComparison.Ordinal)
                && !(
                    string.Equals(NormalizeToken(GetJsonString(row["routeRole"])), "primary", StringComparison.Ordinal)
                    && string.Equals(NormalizeToken(GetJsonString(row["promotionState"])), "promoted", StringComparison.Ordinal)));
        }

        string normalizedChannel = NormalizeToken(channelId);
        string normalizedStatus = NormalizeToken(status);
        string normalizedRollout = NormalizeToken(rolloutState);
        string normalizedSupportability = NormalizeToken(supportabilityState);
        string posture = ReleaseChannelPublicPosture(normalizedStatus, normalizedRollout);

        releaseChannel["channelId"] = normalizedChannel;
        releaseChannel["posture"] = posture;
        releaseChannel["publicationStatus"] = normalizedStatus;
        releaseChannel["rolloutState"] = normalizedRollout;
        releaseChannel["supportabilityState"] = normalizedSupportability;
        releaseChannel["recommendedRouteCount"] = recommendedRouteCount;
        releaseChannel["blockedRouteCount"] = blockedRouteCount;
        releaseChannel["revokedRouteCount"] = revokedRouteCount;
        releaseChannel["summary"] =
            $"Channel {normalizedChannel} is {posture} with {recommendedRouteCount} recommended primary routes, " +
            $"{fallbackRouteCount} promoted fallback recovery routes, {blockedRouteCount} blocked routes, " +
            $"and {revokedRouteCount} active revocations.";

        metrics["releaseChannel"] = releaseChannel;
        manifest["publicTrustMetrics"] = metrics;
    }

    private static bool RouteTruthIsPreviewOnlyFallback(JsonObject row)
        => string.Equals(NormalizeToken(GetJsonString(row["routeRole"])), "fallback", StringComparison.Ordinal)
            && string.Equals(NormalizeToken(GetJsonString(row["promotionState"])), "proof_required", StringComparison.Ordinal)
            && string.Equals(NormalizeToken(GetJsonString(row["parityPosture"])), "explicit_fallback", StringComparison.Ordinal)
            && !string.Equals(NormalizeToken(GetJsonString(row["revokeState"])), "revoked", StringComparison.Ordinal);

    private static string ReleaseChannelPublicPosture(string status, string rolloutState)
    {
        string normalizedStatus = NormalizeToken(status);
        string normalizedRollout = NormalizeToken(rolloutState);
        if (string.Equals(normalizedStatus, "revoked", StringComparison.Ordinal)
            || string.Equals(normalizedRollout, "revoked", StringComparison.Ordinal))
        {
            return "revoked";
        }

        if (!string.Equals(normalizedStatus, "published", StringComparison.Ordinal))
        {
            return "blocked";
        }

        return string.Equals(normalizedRollout, "public_stable", StringComparison.Ordinal)
            ? "live"
            : "preview";
    }

    private static JsonObject NormalizeRegistryBoundaryCoverage(
        JsonObject? sourceCoverage,
        int publishedArtifactCount,
        JsonObject manifest,
        JsonObject desktopTupleCoverage,
        string channelId,
        string releaseVersion,
        string status,
        string rolloutState,
        string supportabilityState)
    {
        JsonObject coverage = sourceCoverage?.DeepClone().AsObject() ?? new JsonObject();
        JsonObject releaseChannel = coverage["releaseChannel"] as JsonObject ?? new JsonObject();
        JsonArray routeTruth = desktopTupleCoverage["desktopRouteTruth"] as JsonArray ?? [];
        JsonArray promotedInstallerTuples = desktopTupleCoverage["promotedInstallerTuples"] as JsonArray ?? [];
        string normalizedChannel = NormalizeToken(channelId);
        string normalizedVersion = string.IsNullOrWhiteSpace(releaseVersion)
            ? GetJsonString(manifest["version"]) ?? string.Empty
            : releaseVersion;
        string normalizedRollout = NormalizeToken(rolloutState);
        string publicTrustPosture = GetJsonString(manifest["publicTrustMetrics"]?["releaseChannel"]?["posture"])
            ?? ReleaseChannelPublicPosture(status, normalizedRollout);

        releaseChannel["publicationStatus"] = NormalizeToken(status);
        releaseChannel["rolloutState"] = normalizedRollout;
        releaseChannel["supportabilityState"] = NormalizeToken(supportabilityState);
        releaseChannel["desktopTupleComplete"] = GetJsonBoolean(desktopTupleCoverage["complete"]);
        releaseChannel["promotedInstallerTupleCount"] = promotedInstallerTuples.Count;
        releaseChannel["desktopRouteTruthCount"] = routeTruth.Count;
        releaseChannel["publicTrustPosture"] = NormalizeToken(publicTrustPosture);
        releaseChannel["summary"] =
            $"Release-channel truth for {normalizedChannel}/{normalizedVersion} keeps " +
            $"{promotedInstallerTuples.Count} promoted installer tuples and " +
            $"{routeTruth.Count} explicit desktop route-truth rows under " +
            $"{normalizedRollout} rollout posture.";
        coverage["releaseChannel"] = releaseChannel;

        JsonObject compatibility = coverage["compatibility"] as JsonObject ?? new JsonObject();
        int compatibleRuntimeBundleHeadCount = GetJsonInt32(compatibility["compatibleRuntimeBundleHeadCount"]);
        int compatibleExchangeArtifactCount = GetJsonInt32(compatibility["compatibleExchangeArtifactCount"]);
        int unknownRuntimeBundleHeadCount = GetJsonInt32(compatibility["unknownRuntimeBundleHeadCount"]);
        compatibility["compatibleArtifactCount"] = publishedArtifactCount;
        compatibility["compatibleRuntimeBundleHeadCount"] = compatibleRuntimeBundleHeadCount;
        compatibility["compatibleExchangeArtifactCount"] = compatibleExchangeArtifactCount;
        compatibility["unknownArtifactCount"] = 0;
        compatibility["unknownRuntimeBundleHeadCount"] = unknownRuntimeBundleHeadCount;
        compatibility["summary"] =
            $"Compatibility boundary tracks {publishedArtifactCount} compatible artifacts, " +
            $"{compatibleRuntimeBundleHeadCount} compatible runtime bundle heads, and " +
            $"{compatibleExchangeArtifactCount} compatible exchange-lineage rows while " +
            $"0 artifact rows and {unknownRuntimeBundleHeadCount} runtime bundle heads remain unknown.";
        coverage["compatibility"] = compatibility;
        return coverage;
    }

    private static int GetJsonInt32(JsonNode? node)
    {
        if (node is null)
        {
            return 0;
        }

        if (node is JsonValue jsonValue && jsonValue.TryGetValue<int>(out int value))
        {
            return value;
        }

        return int.TryParse(GetJsonString(node), out value) ? value : 0;
    }

    private static bool GetJsonBoolean(JsonNode? node)
    {
        if (node is null)
        {
            return false;
        }

        if (node is JsonValue jsonValue && jsonValue.TryGetValue<bool>(out bool value))
        {
            return value;
        }

        return bool.TryParse(GetJsonString(node), out value) && value;
    }

    private static JsonArray BuildInstallAwareArtifactRegistry(
        JsonArray artifacts,
        JsonObject coverage,
        string channelId,
        string releaseVersion)
    {
        if (coverage["desktopRouteTruth"] is not JsonArray desktopRouteTruth)
        {
            return [];
        }

        Dictionary<string, CanonicalArtifactState> artifactById = ExtractCanonicalArtifactRows(artifacts)
            .Where(static artifact => !string.IsNullOrWhiteSpace(artifact.ArtifactId))
            .GroupBy(static artifact => NormalizeToken(artifact.ArtifactId), StringComparer.OrdinalIgnoreCase)
            .ToDictionary(
                static group => group.Key,
                static group => group.OrderBy(static artifact => artifact.Kind, StringComparer.Ordinal).First(),
                StringComparer.OrdinalIgnoreCase);

        List<JsonObject> rows = [];
        foreach (JsonObject routeRow in desktopRouteTruth.OfType<JsonObject>())
        {
            string artifactId = ExpectedInstallerArtifactIdForRoute(routeRow);
            if (string.IsNullOrWhiteSpace(artifactId))
            {
                continue;
            }

            string head = NormalizeToken(GetJsonString(routeRow["head"]));
            string platform = NormalizePlatform(GetJsonString(routeRow["platform"]));
            string rid = NormalizeToken(GetJsonString(routeRow["rid"]));
            string arch = NormalizeToken(GetJsonString(routeRow["arch"]));
            if (string.IsNullOrWhiteSpace(arch)
                && RidToPlatformArch.TryGetValue(rid, out (string Platform, string Arch) platformArch))
            {
                arch = platformArch.Arch;
            }

            string installedBuildSelector = InstallAwareInstalledBuildSelector(
                channelId,
                releaseVersion,
                head,
                platform,
                arch);
            string tupleId = (GetJsonString(routeRow["tupleId"]) ?? string.Empty).Trim();
            string kind = InstallAwareArtifactKind(artifactById, artifactId);
            bool currentForInstalledBuild =
                string.Equals(NormalizeToken(GetJsonString(routeRow["promotionState"])), "promoted", StringComparison.Ordinal)
                && !string.Equals(NormalizeToken(GetJsonString(routeRow["revokeState"])), "revoked", StringComparison.Ordinal);

            JsonArray recoveryProofRefs =
            [
                (GetJsonString(routeRow["publicInstallRoute"]) ?? string.Empty).Trim(),
                $"startup-smoke/startup-smoke-{head}-{rid}.receipt.json",
                $"desktopTupleCoverage.desktopRouteTruth[{tupleId}]",
            ];

            JsonObject conciergeAssetRefs = new()
            {
                ["releaseExplainerPacket"] = $"concierge/release/{channelId}/{releaseVersion}/{artifactId}",
                ["supportClosurePacket"] = $"concierge/support/{channelId}/{releaseVersion}/{artifactId}",
                ["publicTrustWrapper"] = (GetJsonString(routeRow["publicInstallRoute"]) ?? string.Empty).Trim(),
            };

            rows.Add(new JsonObject
            {
                ["registryId"] = $"concierge:{channelId}:{releaseVersion}:{artifactId}",
                ["artifactId"] = artifactId,
                ["channelId"] = channelId,
                ["releaseVersion"] = releaseVersion,
                ["tupleId"] = tupleId,
                ["head"] = head,
                ["platform"] = platform,
                ["rid"] = rid,
                ["arch"] = arch,
                ["kind"] = kind,
                ["installedBuildSelector"] = installedBuildSelector,
                ["currentForInstalledBuild"] = currentForInstalledBuild,
                ["channelRationale"] = InstallAwareChannelRationale(routeRow, channelId, installedBuildSelector),
                ["correctnessReason"] = InstallAwareCorrectnessReason(routeRow, artifactId, installedBuildSelector),
                ["recoveryProofRefs"] = new JsonArray(
                    recoveryProofRefs
                        .Select(GetJsonString)
                        .Where(static value => !string.IsNullOrWhiteSpace(value))
                        .Select(static value => JsonValue.Create(value))
                        .ToArray()),
                ["conciergeAssetRefs"] = conciergeAssetRefs,
            });
        }

        return new JsonArray(
            rows.OrderBy(static row => NormalizePlatform(GetJsonString(row["platform"])), StringComparer.Ordinal)
                .ThenBy(static row => NormalizeToken(GetJsonString(row["head"])), StringComparer.Ordinal)
                .ThenBy(static row => NormalizeToken(GetJsonString(row["rid"])), StringComparer.Ordinal)
                .ThenBy(static row => NormalizeToken(GetJsonString(row["artifactId"])), StringComparer.Ordinal)
                .Select(static row => (JsonNode)row)
                .ToArray());
    }

    private static string ExpectedInstallerArtifactIdForRoute(JsonObject routeRow)
    {
        string artifactId = NormalizeToken(GetJsonString(routeRow["artifactId"]));
        if (!string.IsNullOrWhiteSpace(artifactId))
        {
            return artifactId;
        }

        string head = NormalizeToken(GetJsonString(routeRow["head"]));
        string rid = NormalizeToken(GetJsonString(routeRow["rid"]));
        return string.IsNullOrWhiteSpace(head) || string.IsNullOrWhiteSpace(rid)
            ? string.Empty
            : $"{head}-{rid}-installer";
    }

    private static string InstallAwareArtifactKind(
        IReadOnlyDictionary<string, CanonicalArtifactState> artifactById,
        string artifactId)
        => artifactById.TryGetValue(NormalizeToken(artifactId), out CanonicalArtifactState? artifact)
            ? NormalizeToken(artifact.Kind) switch
            {
                { Length: > 0 } kind => kind,
                _ => "installer",
            }
            : "installer";

    private static string InstallAwareInstalledBuildSelector(
        string channelId,
        string releaseVersion,
        string head,
        string platform,
        string arch)
        => $"{channelId}/{releaseVersion}/{head}/{platform}/{arch}";

    private static string InstallAwareChannelRationale(
        JsonObject routeRow,
        string channelId,
        string installedBuildSelector)
    {
        string tupleId = (GetJsonString(routeRow["tupleId"]) ?? string.Empty).Trim();
        string routeRole = NormalizeToken(GetJsonString(routeRow["routeRole"]));
        string promotionState = NormalizeToken(GetJsonString(routeRow["promotionState"]));
        string revokeState = NormalizeToken(GetJsonString(routeRow["revokeState"]));
        if (string.Equals(revokeState, "revoked", StringComparison.Ordinal))
        {
            return $"Published {channelId} channel blocks {routeRole}-route {tupleId} for installed build selector {installedBuildSelector} because registry revoke truth is active.";
        }

        if (string.Equals(promotionState, "promoted", StringComparison.Ordinal))
        {
            return string.Equals(routeRole, "fallback", StringComparison.Ordinal)
                ? $"Published {channelId} channel keeps fallback route {tupleId} current for installed build selector {installedBuildSelector} as recovery/manual routing."
                : $"Published {channelId} channel keeps primary-route {tupleId} current for installed build selector {installedBuildSelector}.";
        }

        return $"Published {channelId} channel keeps {routeRole}-route {tupleId} blocked for installed build selector {installedBuildSelector} until installer and startup verification are present.";
    }

    private static string InstallAwareCorrectnessReason(
        JsonObject routeRow,
        string artifactId,
        string installedBuildSelector)
    {
        string tupleId = (GetJsonString(routeRow["tupleId"]) ?? string.Empty).Trim();
        string promotionState = NormalizeToken(GetJsonString(routeRow["promotionState"]));
        string revokeState = NormalizeToken(GetJsonString(routeRow["revokeState"]));
        return string.Equals(promotionState, "promoted", StringComparison.Ordinal)
               && !string.Equals(revokeState, "revoked", StringComparison.Ordinal)
            ? $"Offer {artifactId} to installed build selector {installedBuildSelector} because tuple {tupleId} is currently promoted for this channel."
            : $"Do not offer {artifactId} to installed build selector {installedBuildSelector} because tuple {tupleId} is not currently promoted for this channel.";
    }

    private static string NormalizeReleaseProofForPublication(
        JsonObject manifest,
        DateTimeOffset publishedAt)
    {
        JsonObject? proof = manifest["releaseProof"] as JsonObject;
        string proofStatus = ExtractProofStatus(manifest);
        if (!ProofPassed(proofStatus))
        {
            return proofStatus;
        }

        DateTimeOffset? proofGeneratedAt = TryGetJsonDateTimeOffset(proof?["generatedAt"]);
        if (proofGeneratedAt is null
            || publishedAt - proofGeneratedAt.Value > MaximumReleaseProofPublicationLag)
        {
            if (proof is not null)
            {
                proof["status"] = "review_required";
            }

            return "review_required";
        }

        return proofStatus;
    }

    private static JsonObject BuildDesktopTupleCoverage(
        JsonArray artifacts,
        JsonElement? sourceCoverageElement,
        string? channelStatus,
        string? rolloutState,
        string? rolloutReason,
        string? knownIssueSummary)
    {
        JsonObject? sourceCoverage = sourceCoverageElement is JsonElement coverageElement
            && coverageElement.ValueKind == JsonValueKind.Object
            ? JsonNode.Parse(coverageElement.GetRawText())?.AsObject()
            : null;

        List<CanonicalArtifactState> artifactRows = ExtractCanonicalArtifactRows(artifacts);
        List<string> derivedRequiredDesktopPlatforms = DeriveRequiredDesktopPlatforms(artifactRows);
        List<string> requiredDesktopPlatforms = ReadSourceCoverageStringList(sourceCoverage, "requiredDesktopPlatforms");
        if (requiredDesktopPlatforms.Count == 0)
        {
            requiredDesktopPlatforms = derivedRequiredDesktopPlatforms.Count > 0
                ? derivedRequiredDesktopPlatforms
                : [.. RequiredDesktopPlatforms];
        }
        else if (derivedRequiredDesktopPlatforms.Count > 0)
        {
            requiredDesktopPlatforms = requiredDesktopPlatforms
                .Where(platform => derivedRequiredDesktopPlatforms.Contains(platform, StringComparer.OrdinalIgnoreCase))
                .Distinct(StringComparer.OrdinalIgnoreCase)
                .ToList();
        }
        List<string> requiredDesktopHeads = ReadSourceCoverageStringList(sourceCoverage, "requiredDesktopHeads");
        if (requiredDesktopHeads.Count == 0)
        {
            requiredDesktopHeads = [.. RequiredDesktopHeads];
        }
        List<Dictionary<string, string>> promotedInstallerTuples = [];
        HashSet<string> promotedHeadTokens = new(StringComparer.OrdinalIgnoreCase);
        HashSet<string> promotedPlatformTokens = new(StringComparer.OrdinalIgnoreCase);
        HashSet<string> promotedPairs = new(StringComparer.OrdinalIgnoreCase);
        HashSet<string> promotedPlatformHeadRidTuples = new(StringComparer.OrdinalIgnoreCase);
        Dictionary<string, List<string>> promotedPlatformHeads = requiredDesktopPlatforms.ToDictionary(
            static platform => platform,
            static _ => new List<string>(),
            StringComparer.OrdinalIgnoreCase);
        Dictionary<string, HashSet<string>> promotedPlatformHeadsSeen = requiredDesktopPlatforms.ToDictionary(
            static platform => platform,
            static _ => new HashSet<string>(StringComparer.OrdinalIgnoreCase),
            StringComparer.OrdinalIgnoreCase);

        foreach (CanonicalArtifactState artifact in artifactRows)
        {
            if (!requiredDesktopPlatforms.Contains(artifact.Platform, StringComparer.OrdinalIgnoreCase)
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
                if (promotedPlatformHeadsSeen[artifact.Platform].Add(artifact.Head))
                {
                    promotedPlatformHeads[artifact.Platform].Add(artifact.Head);
                }
            }

            if (!string.IsNullOrWhiteSpace(artifact.Head) && !string.IsNullOrWhiteSpace(artifact.Rid))
            {
                promotedPlatformHeadRidTuples.Add($"{artifact.Head}:{artifact.Rid}:{artifact.Platform}");
            }

            promotedPlatformTokens.Add(artifact.Platform);
        }

        promotedInstallerTuples = promotedInstallerTuples
            .OrderBy(static row => row["platform"], StringComparer.Ordinal)
            .ThenBy(static row => row["head"], StringComparer.Ordinal)
            .ThenBy(static row => row["rid"], StringComparer.Ordinal)
            .ThenBy(static row => row["artifactId"], StringComparer.Ordinal)
            .ToList();
        foreach (string platform in requiredDesktopPlatforms)
        {
            promotedPlatformHeads[platform] = promotedPlatformHeads[platform]
                .OrderBy(static value => value, StringComparer.Ordinal)
                .ToList();
        }

        List<string> missingRequiredPlatforms = requiredDesktopPlatforms
            .Where(platform => !promotedPlatformTokens.Contains(platform))
            .ToList();
        List<string> missingRequiredHeads = requiredDesktopHeads
            .Where(head => !promotedHeadTokens.Contains(head))
            .ToList();
        List<string> missingRequiredPlatformHeadPairs = requiredDesktopPlatforms
            .SelectMany(platform => requiredDesktopHeads.Select(head => $"{head}:{platform}"))
            .Where(pair => !promotedPairs.Contains(pair))
            .ToList();

        Dictionary<string, HashSet<string>> promotedRidsByPlatform = requiredDesktopPlatforms.ToDictionary(
            static platform => platform,
            static _ => new HashSet<string>(StringComparer.OrdinalIgnoreCase),
            StringComparer.OrdinalIgnoreCase);
        foreach (string tupleId in promotedPlatformHeadRidTuples)
        {
            string[] parts = tupleId.Split(':', 3, StringSplitOptions.TrimEntries | StringSplitOptions.RemoveEmptyEntries);
            if (parts.Length == 3 && promotedRidsByPlatform.TryGetValue(parts[2], out HashSet<string>? ridSet))
            {
                ridSet.Add(parts[1]);
            }
        }

        List<string> requiredDesktopPlatformHeadRidTuples = ReadSourceCoverageStringList(
            sourceCoverage,
            "requiredDesktopPlatformHeadRidTuples");
        if (requiredDesktopPlatformHeadRidTuples.Count > 0)
        {
            requiredDesktopPlatformHeadRidTuples = requiredDesktopPlatformHeadRidTuples
                .Where(tupleId =>
                {
                    string[] parts = tupleId.Split(':', 3, StringSplitOptions.TrimEntries | StringSplitOptions.RemoveEmptyEntries);
                    return parts.Length == 3
                        && requiredDesktopPlatforms.Contains(parts[2], StringComparer.OrdinalIgnoreCase);
                })
                .Distinct(StringComparer.OrdinalIgnoreCase)
                .ToList();
        }
        if (requiredDesktopPlatformHeadRidTuples.Count == 0)
        {
            requiredDesktopPlatformHeadRidTuples = requiredDesktopPlatforms
                .SelectMany(platform =>
                {
                    IEnumerable<string> rids = DefaultRequiredDesktopPlatformRids.TryGetValue(platform, out string[]? requiredRids)
                        && requiredRids.Length > 0
                            ? requiredRids
                            : promotedRidsByPlatform.GetValueOrDefault(platform, []).OrderBy(static value => value, StringComparer.Ordinal);
                    return requiredDesktopHeads.SelectMany(head =>
                        rids.Where(static rid => !string.IsNullOrWhiteSpace(rid))
                            .Select(rid => $"{head}:{rid}:{platform}"));
                })
                .OrderBy(static value => value, StringComparer.Ordinal)
                .Distinct(StringComparer.OrdinalIgnoreCase)
                .ToList();
        }
        List<string> promotedDesktopPlatformHeadRidTuples = promotedPlatformHeadRidTuples
            .OrderBy(static value => value, StringComparer.Ordinal)
            .ToList();
        HashSet<string> promotedTupleSet = new(promotedDesktopPlatformHeadRidTuples, StringComparer.OrdinalIgnoreCase);
        List<string> missingRequiredPlatformHeadRidTuples = requiredDesktopPlatformHeadRidTuples
            .Where(tupleId => !promotedTupleSet.Contains(tupleId))
            .ToList();
        HashSet<string> missingTupleSet = new(missingRequiredPlatformHeadRidTuples, StringComparer.OrdinalIgnoreCase);

        JsonObject coverage = new()
        {
            ["requiredDesktopPlatforms"] = JsonSerializer.SerializeToNode(requiredDesktopPlatforms, JsonOptions),
            ["requiredDesktopHeads"] = JsonSerializer.SerializeToNode(requiredDesktopHeads, JsonOptions),
            ["promotedInstallerTuples"] = JsonSerializer.SerializeToNode(promotedInstallerTuples, JsonOptions),
            ["promotedPlatformHeads"] = JsonSerializer.SerializeToNode(promotedPlatformHeads, JsonOptions),
            ["requiredDesktopPlatformHeadRidTuples"] = JsonSerializer.SerializeToNode(requiredDesktopPlatformHeadRidTuples, JsonOptions),
            ["promotedPlatformHeadRidTuples"] = JsonSerializer.SerializeToNode(promotedDesktopPlatformHeadRidTuples, JsonOptions),
            ["missingRequiredPlatforms"] = JsonSerializer.SerializeToNode(missingRequiredPlatforms, JsonOptions),
            ["missingRequiredHeads"] = JsonSerializer.SerializeToNode(missingRequiredHeads, JsonOptions),
            ["missingRequiredPlatformHeadPairs"] = JsonSerializer.SerializeToNode(missingRequiredPlatformHeadPairs, JsonOptions),
            ["missingRequiredPlatformHeadRidTuples"] = JsonSerializer.SerializeToNode(missingRequiredPlatformHeadRidTuples, JsonOptions),
            ["externalProofRequests"] = FilterExternalProofRequests(sourceCoverage, missingTupleSet),
            ["desktopRouteTruth"] = JsonSerializer.SerializeToNode(
                BuildDesktopRouteTruth(
                    artifactRows,
                    requiredDesktopPlatforms,
                    NormalizeToken(channelStatus),
                    NormalizeToken(rolloutState),
                    rolloutReason?.Trim() ?? string.Empty,
                    knownIssueSummary?.Trim() ?? string.Empty),
                JsonOptions),
            ["complete"] = missingRequiredPlatforms.Count == 0
                && missingRequiredHeads.Count == 0
                && missingRequiredPlatformHeadPairs.Count == 0
                && missingRequiredPlatformHeadRidTuples.Count == 0
        };

        return coverage;
    }

    private static List<string> ReadSourceCoverageStringList(JsonObject? sourceCoverage, string propertyName)
    {
        if (sourceCoverage?[propertyName] is not JsonArray values)
        {
            return [];
        }

        return values
            .Select(static value => NormalizeToken(GetJsonString(value)))
            .Where(static value => !string.IsNullOrWhiteSpace(value))
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .OrderBy(static value => value, StringComparer.Ordinal)
            .ToList();
    }

    private static List<string> DeriveRequiredDesktopPlatforms(IReadOnlyList<CanonicalArtifactState> artifacts)
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

    private static JsonArray FilterExternalProofRequests(JsonObject? sourceCoverage, HashSet<string> missingTupleIds)
    {
        JsonArray filtered = [];
        if (missingTupleIds.Count == 0)
        {
            return filtered;
        }

        if (sourceCoverage?["externalProofRequests"] is not JsonArray requests)
        {
            return filtered;
        }

        foreach (JsonNode? node in requests)
        {
            if (node is not JsonObject request)
            {
                continue;
            }

            string tupleId = NormalizeToken(GetJsonString(request["tupleId"]));
            if (string.IsNullOrWhiteSpace(tupleId) || !missingTupleIds.Contains(tupleId))
            {
                continue;
            }

            filtered.Add(request.DeepClone());
        }

        return filtered;
    }

    private static List<Dictionary<string, string>> BuildDesktopRouteTruth(
        IReadOnlyList<CanonicalArtifactState> artifacts,
        IReadOnlyList<string> requiredDesktopPlatforms,
        string channelStatus,
        string rolloutState,
        string rolloutReason,
        string knownIssueSummary)
    {
        Dictionary<string, CanonicalArtifactState> promotedByPlatformHeadRid = new(StringComparer.OrdinalIgnoreCase);
        Dictionary<string, HashSet<string>> requiredRidsByPlatform = requiredDesktopPlatforms.ToDictionary(
            static platform => platform,
            static platform => new HashSet<string>(
                DefaultRequiredDesktopPlatformRids.TryGetValue(platform, out string[]? rids) ? rids : [],
                StringComparer.OrdinalIgnoreCase),
            StringComparer.OrdinalIgnoreCase);

        foreach (CanonicalArtifactState artifact in artifacts)
        {
            if (!requiredDesktopPlatforms.Contains(artifact.Platform, StringComparer.OrdinalIgnoreCase)
                || !DesktopRouteTruthHeads.Contains(artifact.Head, StringComparer.OrdinalIgnoreCase)
                || string.IsNullOrWhiteSpace(artifact.Rid)
                || !IsDesktopInstallMedia(artifact.Platform, artifact.Kind))
            {
                continue;
            }

            requiredRidsByPlatform[artifact.Platform].Add(artifact.Rid);
            string key = $"{artifact.Platform}|{artifact.Head}|{artifact.Rid}";
            if (!promotedByPlatformHeadRid.TryGetValue(key, out CanonicalArtifactState? current)
                || CompareArtifactSelectionKey(artifact, current) < 0)
            {
                promotedByPlatformHeadRid[key] = artifact;
            }
        }

        List<Dictionary<string, string>> rows = [];
        foreach (string platform in requiredDesktopPlatforms)
        {
            IEnumerable<string> rids = requiredRidsByPlatform.TryGetValue(platform, out HashSet<string>? ridSet)
                ? ridSet.OrderBy(static value => value, StringComparer.Ordinal)
                : Enumerable.Empty<string>();
            foreach (string rid in rids)
            {
                foreach (string head in DesktopRouteTruthHeads)
                {
                    promotedByPlatformHeadRid.TryGetValue($"{platform}|{head}|{rid}", out CanonicalArtifactState? artifact);
                    string routeRole = DesktopRouteRoles[head];
                    string arch = artifact?.Arch
                        ?? (RidToPlatformArch.TryGetValue(rid, out (string Platform, string Arch) platformArch) ? platformArch.Arch : string.Empty);
                    string artifactId = artifact?.ArtifactId ?? string.Empty;
                    bool promoted = artifact is not null;
                    string tupleLabel = $"{platform}/{rid}";
                    string routeTupleLabel = $"{head}:{platform}:{rid}";
                    string fallbackRouteTupleLabel = $"blazor-desktop:{platform}:{rid}";
                    (string RevokeState, string RevokeReason) revoke = DesktopRouteRevokePosture(
                        artifact,
                        channelStatus,
                        rolloutState,
                        rolloutReason,
                        knownIssueSummary);
                    string revokeSource = artifact is null
                        ? string.Equals(revoke.RevokeState, "revoked", StringComparison.Ordinal)
                            ? "channel"
                            : "none"
                        : DesktopRouteArtifactIsRevoked(artifact)
                            ? "artifact"
                            : string.Equals(revoke.RevokeState, "revoked", StringComparison.Ordinal)
                                ? "channel"
                                : "none";
                    string revokeReason = revoke.RevokeState == "revoked"
                        ? $"Registry revoke marker is active for {routeTupleLabel}: {revoke.RevokeReason}"
                        : $"No registry revoke marker is active for {routeTupleLabel}.";

                    string promotionState;
                    string promotionReasonCode;
                    string promotionReason;
                    string installPosture;
                    string installPostureReason;
                    if (promoted)
                    {
                        promotionState = "promoted";
                        promotionReasonCode = "installer_smoke_and_release_proof_passed";
                        string promotionSubject = DesktopRoutePromotionSubject(head);
                        promotionReason = routeRole == "primary"
                            ? $"{promotionSubject} tuple {routeTupleLabel} for {tupleLabel} is promoted because the flagship head is present on the registry shelf and passed independent startup verification and release verification gates for this channel."
                            : $"{promotionSubject} tuple {routeTupleLabel} for {tupleLabel} is promoted for recovery/manual routing because it is present on the registry shelf and passed the current startup verification and release verification gates for this channel.";
                        installPosture = "installer_first";
                        installPostureReason = $"Promoted installer media {artifactId} is present for {AppLabels[head]} tuple {routeTupleLabel} on {tupleLabel}.";
                    }
                    else
                    {
                        promotionState = "proof_required";
                        promotionReasonCode = "missing_artifact_or_startup_smoke_proof";
                        string promotionSubject = DesktopRoutePromotionSubject(head);
                        promotionReason = routeRole == "primary"
                            ? $"{promotionSubject} tuple {routeTupleLabel} for {tupleLabel} is not promoted until the flagship head has matching artifact bytes and fresh startup verification for this channel."
                            : $"{promotionSubject} tuple {routeTupleLabel} for {tupleLabel} is retained for recovery/manual routing on {tupleLabel} but is not promoted until matching artifact bytes and fresh startup verification are present.";
                        installPosture = "proof_capture_required";
                        installPostureReason = $"Do not present {routeTupleLabel} as installable until the missing tuple proof is captured.";
                    }

                    string parityPosture;
                    string updateEligibility;
                    string updateEligibilityReason;
                    string rollbackState;
                    string rollbackReasonCode;
                    string rollbackReason;
                    if (routeRole == "primary")
                    {
                        parityPosture = "flagship_primary";
                        if (promoted)
                        {
                            updateEligibility = "eligible";
                            updateEligibilityReason = $"Primary-route {AppLabels[head]} tuple {routeTupleLabel} is promoted for {tupleLabel}.";
                        }
                        else
                        {
                            updateEligibility = "blocked_missing_proof";
                            updateEligibilityReason = $"Primary-route updates are blocked until {routeTupleLabel} is promoted.";
                        }

                        promotedByPlatformHeadRid.TryGetValue($"{platform}|blazor-desktop|{rid}", out CanonicalArtifactState? fallbackArtifact);
                        bool fallbackRevoked = DesktopRouteArtifactIsRevoked(fallbackArtifact);
                        bool fallbackPromoted = fallbackArtifact is not null && !fallbackRevoked;
                        if (fallbackPromoted)
                        {
                            rollbackState = "fallback_available";
                            rollbackReasonCode = "promoted_fallback_available";
                            rollbackReason = $"A promoted fallback route {fallbackRouteTupleLabel} exists for primary route {routeTupleLabel} on {tupleLabel}.";
                        }
                        else if (fallbackRevoked)
                        {
                            (string _, string FallbackRevokeReason) = DesktopRouteRevokePosture(
                                fallbackArtifact,
                                channelStatus,
                                rolloutState,
                                rolloutReason,
                                knownIssueSummary);
                            string fallbackRevokeReason = $"Registry revoke marker is active for {fallbackRouteTupleLabel}: {FallbackRevokeReason}";
                            rollbackState = "manual_recovery_required";
                            rollbackReasonCode = "fallback_revoked_for_tuple";
                            rollbackReason = $"Fallback route {fallbackRouteTupleLabel} is revoked for {tupleLabel}, so primary route {routeTupleLabel} requires manual recovery: {fallbackRevokeReason}";
                        }
                        else
                        {
                            if (promoted)
                            {
                                rollbackState = "primary_reinstall_available";
                                rollbackReasonCode = "primary_installer_reinstall_available";
                                rollbackReason = $"Fallback route {fallbackRouteTupleLabel} remains an unpromoted compatibility lane for {tupleLabel}; recover {routeTupleLabel} from the promoted primary installer {artifactId} until a separately proved fallback is published.";
                            }
                            else
                            {
                                rollbackState = "manual_recovery_required";
                                rollbackReasonCode = "fallback_missing_artifact_or_startup_smoke_proof";
                                rollbackReason = $"Fallback route {fallbackRouteTupleLabel} is not promoted for {tupleLabel} because matching artifact bytes and fresh startup verification are still required; primary route {routeTupleLabel} therefore requires manual recovery.";
                            }
                        }
                    }
                    else
                    {
                        parityPosture = "explicit_fallback";
                        if (promoted)
                        {
                            updateEligibility = "manual_fallback";
                            updateEligibilityReason = $"Fallback {AppLabels[head]} tuple {routeTupleLabel} is promoted for {tupleLabel} recovery/manual selection, not automatic primary updates.";
                            rollbackState = "fallback_available";
                            rollbackReasonCode = "fallback_promoted_for_recovery";
                            rollbackReason = $"Fallback {AppLabels[head]} tuple {routeTupleLabel} is promoted for {tupleLabel} rollback or recovery routing.";
                        }
                        else
                        {
                            updateEligibility = "blocked_missing_proof";
                            updateEligibilityReason = $"Fallback route {routeTupleLabel} is not update-eligible until promoted.";
                            rollbackState = "fallback_not_promoted";
                            rollbackReasonCode = "fallback_missing_artifact_or_startup_smoke_proof";
                            rollbackReason = $"Fallback route {routeTupleLabel} needs artifact and startup verification before rollback use.";
                        }
                    }

                    if (revoke.RevokeState == "revoked")
                    {
                        string routeRoleLabel = routeRole == "primary" ? "primary-route" : "fallback";
                        promotionState = "revoked";
                        promotionReasonCode = "registry_revoke_marker_active";
                        promotionReason = $"Registry revoke truth blocks {routeRoleLabel} promotion for {routeTupleLabel}: {revokeReason}";
                        updateEligibility = "blocked_revoked";
                        updateEligibilityReason = $"Updates are blocked because {routeTupleLabel} is revoked in registry truth: {revokeReason}";
                        rollbackState = "revoked";
                        rollbackReasonCode = "registry_revoke_marker_active";
                        rollbackReason = $"Do not use {routeTupleLabel} for rollback while its registry revoke marker is active: {revokeReason}";
                        installPosture = "revoked";
                        installPostureReason = $"Do not present {routeTupleLabel} as installable while revoked: {revokeReason}";
                    }

                    rows.Add(new Dictionary<string, string>(StringComparer.Ordinal)
                    {
                        ["tupleId"] = routeTupleLabel,
                        ["head"] = head,
                        ["platform"] = platform,
                        ["rid"] = rid,
                        ["arch"] = arch,
                        ["artifactId"] = artifactId,
                        ["routeRole"] = routeRole,
                        ["routeRoleReasonCode"] = DesktopRouteRoleReasonCode(head),
                        ["routeRoleReason"] = DesktopRouteRoleReason(head, platform, rid),
                        ["promotionState"] = promotionState,
                        ["promotionReasonCode"] = promotionReasonCode,
                        ["promotionReason"] = promotionReason,
                        ["parityPosture"] = parityPosture,
                        ["updateEligibility"] = updateEligibility,
                        ["updateEligibilityReason"] = updateEligibilityReason,
                        ["rollbackState"] = rollbackState,
                        ["rollbackReasonCode"] = rollbackReasonCode,
                        ["rollbackReason"] = rollbackReason,
                        ["revokeState"] = revoke.RevokeState,
                        ["revokeSource"] = revokeSource,
                        ["revokeReasonCode"] = revoke.RevokeState == "revoked"
                            ? "registry_revoke_marker_active"
                            : "no_registry_revoke_marker",
                        ["revokeReason"] = revokeReason,
                        ["installPosture"] = installPosture,
                        ["installPostureReason"] = installPostureReason,
                        ["publicInstallRoute"] = $"/downloads/install/{head}-{rid}-installer"
                    });
                }
            }
        }

        return rows
            .OrderBy(static row => row["platform"], StringComparer.Ordinal)
            .ThenBy(static row => row["head"], StringComparer.Ordinal)
            .ThenBy(static row => row["rid"], StringComparer.Ordinal)
            .ThenBy(static row => row["tupleId"], StringComparer.Ordinal)
            .ToList();
    }

    private static string DeriveRolloutState(string? channel, string? status, bool proofPassed, bool desktopCoverageComplete)
    {
        string normalizedStatus = NormalizeToken(status);
        if (!string.Equals(normalizedStatus, "published", StringComparison.Ordinal))
        {
            return "unpublished";
        }

        if (!desktopCoverageComplete)
        {
            return "coverage_incomplete";
        }

        string normalizedChannel = NormalizeToken(channel);
        if (proofPassed)
        {
            if (normalizedChannel is "stable" or "public_stable" or "docker")
            {
                return "public_stable";
            }

            return normalizedChannel == "preview"
                ? "promoted_preview"
                : normalizedChannel;
        }

        return normalizedChannel == "preview"
            ? "promoted_preview"
            : normalizedChannel;
    }

    private static string DeriveRolloutReason(
        string? channel,
        string? status,
        bool proofPassed,
        bool desktopCoverageComplete,
        JsonObject coverage)
    {
        string normalizedStatus = NormalizeToken(status);
        if (!string.Equals(normalizedStatus, "published", StringComparison.Ordinal))
        {
            return "No published artifact shelf exists yet.";
        }

        if (!desktopCoverageComplete)
        {
            return "Current shelf is published, but promotion stays blocked because "
                + DesktopTupleCoverageGapSummary(coverage)
                + ".";
        }

        if (proofPassed)
        {
            return "Current release shelf passed the local release run before publication.";
        }

        return string.Equals(NormalizeToken(channel), "preview", StringComparison.Ordinal)
            ? "Current preview shelf is published, but the release run should be repeated before widening trust claims."
            : "Current release shelf is published.";
    }

    private static string DeriveSupportabilityState(string? channel, string? status, bool proofPassed, bool desktopCoverageComplete)
    {
        string normalizedStatus = NormalizeToken(status);
        if (!string.Equals(normalizedStatus, "published", StringComparison.Ordinal))
        {
            return "unpublished";
        }

        if (!desktopCoverageComplete)
        {
            return "review_required";
        }

        return proofPassed
            ? NormalizeToken(channel) switch
            {
                "public_stable" => "gold_supported",
                "stable" => "gold_supported",
                "docker" => "gold_supported",
                _ => "preview_supported",
            }
            : "review_required";
    }

    private static string DeriveSupportabilitySummary(
        string? channel,
        string? status,
        bool proofPassed,
        bool desktopCoverageComplete,
        JsonObject coverage,
        IReadOnlyList<string>? proofJourneys)
    {
        string normalizedStatus = NormalizeToken(status);
        if (!string.Equals(normalizedStatus, "published", StringComparison.Ordinal))
        {
            return "No published channel support posture exists because no release page is live.";
        }

        if (!desktopCoverageComplete)
        {
            return "Treat the current release as review-required because "
                + DesktopTupleCoverageGapSummary(coverage)
                + ".";
        }

        if (!proofPassed)
        {
            return "Treat the current release as review-required until release status and support closure are ready.";
        }

        List<string> journeys = proofJourneys?
            .Select(NormalizeToken)
            .Where(static value => !string.IsNullOrWhiteSpace(value))
            .ToList()
            ?? [];
        if (journeys.Count == 0)
        {
            return NormalizeToken(channel) is "public_stable" or "stable" or "docker"
                ? "Current public release is supported on the promoted routes. Recent coverage includes install, bounded offline prefetch, and current support follow-up."
                : "Current preview release is supported on the promoted routes. Recent coverage includes install, bounded offline prefetch, and current support follow-up.";
        }

        List<string> proofNotes = [];
        if (journeys.Contains("build_explain_publish", StringComparer.Ordinal))
        {
            proofNotes.Add("install guidance");
        }

        if (journeys.Contains("campaign_session_recover_recap", StringComparer.Ordinal))
        {
            proofNotes.Add("session recovery");
        }

        if (journeys.Contains("install_claim_restore_continue", StringComparer.Ordinal))
        {
            proofNotes.Add("account return");
        }

        if (journeys.Contains("report_cluster_release_notify", StringComparer.Ordinal))
        {
            proofNotes.Add("release updates");
        }

        if (journeys.Contains("organize_community_and_close_loop", StringComparer.Ordinal))
        {
            proofNotes.Add("community wrap-up");
        }

        string proofNoteClause = proofNotes.Count > 0
            ? " Recent coverage includes " + string.Join(", ", proofNotes) + ","
            : " Recent coverage includes install,";
        return (NormalizeToken(channel) is "public_stable" or "stable" or "docker"
                ? "Current public release is supported on the promoted routes."
                : "Current preview release is supported on the promoted routes.")
            + proofNoteClause
            + " bounded offline prefetch, and current support follow-up.";
    }

    private static string DeriveKnownIssueSummary(
        string? channel,
        string? status,
        bool proofPassed,
        bool desktopCoverageComplete,
        JsonObject coverage,
        IReadOnlyList<string>? proofJourneys)
    {
        string normalizedStatus = NormalizeToken(status);
        if (!string.Equals(normalizedStatus, "published", StringComparison.Ordinal))
        {
            return "No active channel issues are published because the release page is still empty.";
        }

        if (!desktopCoverageComplete)
        {
            return "Known issue: " + DesktopTupleCoverageGapSummary(coverage) + ".";
        }

        if (!proofPassed)
        {
            return $"The {NormalizeToken(channel)} release page is visible, but known-issue review should stay front-and-center until the current verification is refreshed.";
        }

        List<string> journeys = proofJourneys?
            .Select(NormalizeToken)
            .Where(static value => !string.IsNullOrWhiteSpace(value))
            .ToList()
            ?? [];
        List<string> proofNotes = [];
        if (journeys.Contains("install_claim_restore_continue", StringComparer.Ordinal))
        {
            proofNotes.Add("account return");
        }

        if (journeys.Contains("report_cluster_release_notify", StringComparer.Ordinal))
        {
            proofNotes.Add("release updates");
        }

        if (journeys.Contains("organize_community_and_close_loop", StringComparer.Ordinal))
        {
            proofNotes.Add("community wrap-up");
        }

        string proofNoteClause = proofNotes.Count > 0
            ? ", " + string.Join(", ", proofNotes)
            : string.Empty;
        if (NormalizeToken(channel) is "public_stable" or "stable" or "docker")
        {
            return "No blocking release caveat is mirrored for the current public release. The promoted routes have recent install"
                + proofNoteClause
                + ", bounded offline prefetch, and current support follow-up coverage.";
        }

        return "Preview caveats still apply, but the current release has recent install"
            + proofNoteClause
            + ", bounded offline prefetch, and current support follow-up coverage.";
    }

    private static string DeriveFixAvailabilitySummary(string? status, bool proofPassed, bool desktopCoverageComplete)
    {
        string normalizedStatus = NormalizeToken(status);
        if (!string.Equals(normalizedStatus, "published", StringComparison.Ordinal))
        {
            return "Fix notices should stay pending until a published release exists.";
        }

        if (!desktopCoverageComplete)
        {
            return "Do not send fixed notices until required desktop build coverage is complete for the promoted release.";
        }

        return proofPassed
            ? "Only send fixed notices after the affected install can receive the published channel artifact now on the release page."
            : "Check the live release page before sending a fixed notice.";
    }

    private static bool DesktopTupleCoverageIsComplete(JsonObject coverage)
        => ToJsonStringList(coverage["missingRequiredPlatforms"]).Count == 0
            && ToJsonStringList(coverage["missingRequiredHeads"]).Count == 0
            && ToJsonStringList(coverage["missingRequiredPlatformHeadPairs"]).Count == 0
            && ToJsonStringList(coverage["missingRequiredPlatformHeadRidTuples"]).Count == 0;

    private static string DesktopTupleCoverageGapSummary(JsonObject? coverage)
    {
        if (coverage is null)
        {
            return "required desktop build coverage is unavailable";
        }

        List<string> details = [];
        List<string> missingPlatforms = ToJsonStringList(coverage["missingRequiredPlatforms"]);
        List<string> missingHeads = ToJsonStringList(coverage["missingRequiredHeads"]);
        List<string> missingPairs = ToJsonStringList(coverage["missingRequiredPlatformHeadPairs"]);
        List<string> missingTuples = ToJsonStringList(coverage["missingRequiredPlatformHeadRidTuples"]);
        if (missingPlatforms.Count > 0)
        {
            details.Add("platforms: " + string.Join(", ", missingPlatforms));
        }

        if (missingHeads.Count > 0)
        {
            details.Add("heads: " + string.Join(", ", missingHeads));
        }

        if (missingPairs.Count > 0)
        {
            details.Add("pairs: " + string.Join(", ", missingPairs));
        }

        if (missingTuples.Count > 0)
        {
            details.Add("build combinations: " + string.Join(", ", missingTuples));
        }

        return details.Count == 0
            ? "required desktop build coverage is complete"
            : "required desktop build coverage is incomplete (" + string.Join("; ", details) + ")";
    }

    private static bool ProofPassed(string? proofStatus)
        => string.Equals(NormalizeToken(proofStatus), "passed", StringComparison.Ordinal);

    private static DateTimeOffset? TryGetJsonDateTimeOffset(JsonNode? node)
    {
        string? raw = GetJsonString(node);
        return DateTimeOffset.TryParse(raw, out DateTimeOffset parsed)
            ? parsed
            : null;
    }

    private static string ExtractProofStatus(JsonObject manifest)
        => NormalizeToken(GetJsonString((manifest["releaseProof"] as JsonObject)?["status"]));

    private static IReadOnlyList<string> ExtractProofJourneys(JsonObject manifest)
        => ToJsonStringList((manifest["releaseProof"] as JsonObject)?["journeysPassed"])
            .Select(NormalizeToken)
            .Where(static value => !string.IsNullOrWhiteSpace(value))
            .ToArray();

    private static (string RevokeState, string RevokeReason) DesktopRouteRevokePosture(
        CanonicalArtifactState? artifact,
        string channelStatus,
        string rolloutState,
        string rolloutReason,
        string knownIssueSummary)
    {
        if (string.Equals(channelStatus, "revoked", StringComparison.Ordinal)
            || string.Equals(rolloutState, "revoked", StringComparison.Ordinal))
        {
            string reason = !string.IsNullOrWhiteSpace(rolloutReason)
                ? rolloutReason
                : !string.IsNullOrWhiteSpace(knownIssueSummary)
                    ? knownIssueSummary
                    : "The release channel is revoked for this desktop tuple.";
            return ("revoked", reason);
        }

        if (DesktopRouteArtifactIsRevoked(artifact))
        {
            string reason = artifact?.RevokeReason
                ?? artifact?.ArtifactRolloutReason
                ?? artifact?.CompatibilityReason
                ?? artifact?.ArtifactKnownIssueSummary
                ?? knownIssueSummary;
            if (string.IsNullOrWhiteSpace(reason))
            {
                reason = "The artifact registry state is revoked for this desktop tuple.";
            }

            return ("revoked", reason);
        }

        return ("not_revoked", "No registry revoke marker is active for this channel tuple.");
    }

    private static bool DesktopRouteArtifactIsRevoked(CanonicalArtifactState? artifact)
        => artifact is not null
            && (
                string.Equals(artifact.ArtifactStatus, "revoked", StringComparison.Ordinal)
                || string.Equals(artifact.ArtifactRolloutState, "revoked", StringComparison.Ordinal)
                || string.Equals(artifact.CompatibilityState, "revoked", StringComparison.Ordinal)
            );

    private static int CompareArtifactSelectionKey(CanonicalArtifactState left, CanonicalArtifactState right)
    {
        int revokedComparison = (DesktopRouteArtifactIsRevoked(left) ? 1 : 0)
            .CompareTo(DesktopRouteArtifactIsRevoked(right) ? 1 : 0);
        if (revokedComparison != 0)
        {
            return revokedComparison;
        }

        return string.Compare(left.ArtifactId, right.ArtifactId, StringComparison.Ordinal);
    }

    private static string DesktopRouteRoleReason(string head, string platform, string rid)
    {
        string tupleLabel = string.IsNullOrWhiteSpace(rid) ? platform : $"{platform}/{rid}";
        string routeTupleLabel = string.IsNullOrWhiteSpace(rid) ? $"{head}:{platform}" : $"{head}:{platform}:{rid}";
        if (string.Equals(DesktopRouteRoles[head], "primary", StringComparison.Ordinal))
        {
            return $"{AppLabels[head]} route {routeTupleLabel} is the flagship desktop route for {tupleLabel} and must carry independent startup verification before promotion.";
        }

        return $"{AppLabels[head]} route {routeTupleLabel} is retained as an explicit fallback route for {tupleLabel}; it cannot satisfy the primary-route promise.";
    }

    private static string DesktopRouteRoleReasonCode(string head)
        => string.Equals(DesktopRouteRoles[head], "primary", StringComparison.Ordinal)
            ? "primary_flagship_head"
            : "fallback_recovery_head";

    private static string DesktopRoutePromotionSubject(string head)
        => string.Equals(DesktopRouteRoles[head], "primary", StringComparison.Ordinal)
            ? $"Primary-route {AppLabels[head]}"
            : $"Fallback {AppLabels[head]}";

    private static bool IsDesktopInstallMedia(string platform, string kind)
        => string.Equals(platform, "macos", StringComparison.Ordinal)
            ? kind is "installer" or "dmg" or "pkg"
            : string.Equals(kind, "installer", StringComparison.Ordinal);

    private static List<CanonicalArtifactState> ExtractCanonicalArtifactRows(JsonArray artifacts)
    {
        List<CanonicalArtifactState> rows = [];
        foreach (JsonNode? node in artifacts)
        {
            if (node is not JsonObject artifact)
            {
                continue;
            }

            string rid = NormalizeToken(GetJsonString(artifact["rid"]));
            string platform = NormalizePlatformToken(GetJsonString(artifact["platform"]));
            if (string.IsNullOrWhiteSpace(platform)
                && RidToPlatformArch.TryGetValue(rid, out (string Platform, string Arch) platformArch))
            {
                platform = platformArch.Platform;
            }

            string arch = NormalizeToken(GetJsonString(artifact["arch"]));
            if (string.IsNullOrWhiteSpace(arch)
                && RidToPlatformArch.TryGetValue(rid, out (string Platform, string Arch) archMapping))
            {
                arch = archMapping.Arch;
            }
            if (string.IsNullOrWhiteSpace(rid))
            {
                rid = InferRid(platform, arch);
            }

            rows.Add(new CanonicalArtifactState(
                ArtifactId: NormalizeToken(GetJsonString(artifact["artifactId"]) ?? GetJsonString(artifact["id"])),
                Head: NormalizeToken(GetJsonString(artifact["head"])),
                Platform: platform,
                Rid: rid,
                Arch: arch,
                Kind: NormalizeToken(GetJsonString(artifact["kind"])),
                ArtifactStatus: NormalizeToken(GetJsonString(artifact["status"])),
                ArtifactRolloutState: NormalizeToken(GetJsonString(artifact["rolloutState"]) ?? GetJsonString(artifact["rollout_state"])),
                ArtifactRolloutReason: (GetJsonString(artifact["rolloutReason"]) ?? GetJsonString(artifact["rollout_reason"]) ?? string.Empty).Trim(),
                RevokeReason: (GetJsonString(artifact["revokeReason"]) ?? GetJsonString(artifact["revoke_reason"]) ?? string.Empty).Trim(),
                CompatibilityState: NormalizeToken(GetJsonString(artifact["compatibilityState"]) ?? GetJsonString(artifact["compatibility_state"])),
                CompatibilityReason: (GetJsonString(artifact["compatibilityReason"]) ?? GetJsonString(artifact["compatibility_reason"]) ?? string.Empty).Trim(),
                ArtifactKnownIssueSummary: (GetJsonString(artifact["knownIssueSummary"]) ?? GetJsonString(artifact["known_issue_summary"]) ?? string.Empty).Trim()));
        }

        return rows;
    }

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
            _ => normalized
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

    private static JsonArray MergeArrayById(JsonArray? existingArray, JsonArray? incomingArray, string idProperty)
    {
        JsonArray merged = new();
        if (incomingArray is null)
        {
            if (existingArray is not null)
            {
                foreach (JsonNode? item in existingArray)
                {
                    merged.Add(item?.DeepClone());
                }
            }

            return merged;
        }

        Dictionary<string, JsonObject> incomingById = incomingArray
            .OfType<JsonObject>()
            .Where(item => item[idProperty]?.GetValue<string>() is { Length: > 0 })
            .ToDictionary(item => item[idProperty]!.GetValue<string>(), item => item, StringComparer.OrdinalIgnoreCase);

        HashSet<string> seen = new(StringComparer.OrdinalIgnoreCase);
        if (existingArray is not null)
        {
            foreach (JsonObject existingItem in existingArray.OfType<JsonObject>())
            {
                string? id = existingItem[idProperty]?.GetValue<string>();
                if (!string.IsNullOrWhiteSpace(id) && incomingById.TryGetValue(id, out JsonObject? replacement))
                {
                    merged.Add(replacement.DeepClone());
                    seen.Add(id);
                    continue;
                }

                merged.Add(existingItem.DeepClone());
                if (!string.IsNullOrWhiteSpace(id))
                {
                    seen.Add(id);
                }
            }
        }

        foreach ((string id, JsonObject item) in incomingById)
        {
            if (!seen.Contains(id))
            {
                merged.Add(item.DeepClone());
            }
        }

        return merged;
    }

    private static void WriteJsonAtomically<T>(string path, T payload)
    {
        string tempPath = $"{path}.{Guid.NewGuid():N}.tmp";
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        File.WriteAllText(tempPath, JsonSerializer.Serialize(payload, JsonOptions));
        File.Move(tempPath, path, overwrite: true);
    }

    private static void WriteBytesAtomically(string path, byte[] bytes)
    {
        string tempPath = $"{path}.{Guid.NewGuid():N}.tmp";
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        try
        {
            using (var stream = new FileStream(
                       tempPath,
                       FileMode.CreateNew,
                       FileAccess.Write,
                       FileShare.None,
                       bufferSize: 64 * 1024,
                       FileOptions.WriteThrough))
            {
                stream.Write(bytes);
                stream.Flush(flushToDisk: true);
            }

            File.Move(tempPath, path, overwrite: true);
        }
        finally
        {
            if (File.Exists(tempPath))
            {
                File.Delete(tempPath);
            }
        }
    }

    private static string ResolveDownloadFileName(PublicReleaseArtifactDto artifact)
        => ResolveArtifactFileName(artifact.FileName, artifact.Url);

    private static string ResolveArtifactFileName(string? fileName, string? url)
    {
        if (!string.IsNullOrWhiteSpace(fileName))
        {
            return Path.GetFileName(fileName.Trim());
        }

        string normalizedUrl = NormalizePublicPath(url);
        string candidate = Path.GetFileName(normalizedUrl);
        if (!string.IsNullOrWhiteSpace(candidate))
        {
            return candidate;
        }

        throw new InvalidDataException("artifact is missing fileName/url.");
    }

    private static string NormalizePublicPath(string? url)
    {
        string raw = (url ?? string.Empty).Trim();
        if (raw.Length == 0)
        {
            return "/";
        }

        if (Uri.TryCreate(raw, UriKind.Absolute, out Uri? absoluteUri))
        {
            string pathAndQuery = absoluteUri.PathAndQuery;
            return string.IsNullOrWhiteSpace(pathAndQuery) ? "/" : pathAndQuery;
        }

        return raw.StartsWith("/") ? raw : $"/{raw}";
    }

    private static bool IsInstallerArtifact(CanonicalArtifactRecord artifact)
    {
        string kind = (artifact.Kind ?? string.Empty).Trim();
        if (kind.Length > 0)
        {
            return kind.Equals("installer", StringComparison.OrdinalIgnoreCase)
                || kind.Equals("dmg", StringComparison.OrdinalIgnoreCase)
                || kind.Equals("pkg", StringComparison.OrdinalIgnoreCase)
                || kind.Equals("msix", StringComparison.OrdinalIgnoreCase);
        }

        string fileName = ResolveArtifactFileName(artifact.FileName, artifact.DownloadUrl);
        return fileName.EndsWith(".exe", StringComparison.OrdinalIgnoreCase)
               || fileName.EndsWith(".deb", StringComparison.OrdinalIgnoreCase)
               || fileName.EndsWith(".dmg", StringComparison.OrdinalIgnoreCase)
               || fileName.EndsWith(".pkg", StringComparison.OrdinalIgnoreCase)
               || fileName.EndsWith(".msix", StringComparison.OrdinalIgnoreCase);
    }

    private static string NormalizePlatform(string? platform)
    {
        string normalized = (platform ?? string.Empty).Trim().ToLowerInvariant();
        if (normalized.Length > 0)
        {
            int separatorIndex = normalized.IndexOfAny(new[] { '-', '_', '/', ' ' });
            if (separatorIndex >= 0)
            {
                normalized = normalized[..separatorIndex];
            }
        }

        return normalized switch
        {
            "mac" or "macos" or "osx" or "darwin" => "macos",
            "win" or "windows" => "windows",
            "linux" => "linux",
            _ => normalized
        };
    }

    private static string NormalizeArtifactDigest(string? digest)
    {
        string normalized = (digest ?? string.Empty).Trim().ToLowerInvariant();
        return normalized.StartsWith("sha256:", StringComparison.OrdinalIgnoreCase)
            ? normalized[7..]
            : normalized;
    }

    private static string Sha256For(string path)
    {
        using var sha = SHA256.Create();
        using FileStream stream = File.OpenRead(path);
        return Convert.ToHexString(sha.ComputeHash(stream)).ToLowerInvariant();
    }

    private static string Sha256For(byte[] bytes)
        => Convert.ToHexStringLower(SHA256.HashData(bytes));

    private PublicReleaseManifestDto ValidatePublicShelfCoherence(
        string downloadsRoot,
        string liveCompatibilityManifestPath,
        string liveCanonicalManifestPath,
        IReadOnlyList<string> promotedArtifactIds,
        string expectedCompatibilitySha256,
        string expectedCanonicalSha256)
    {
        if (!File.Exists(liveCompatibilityManifestPath))
        {
            throw new InvalidOperationException("promotion wrote no compatibility manifest.");
        }

        if (!File.Exists(liveCanonicalManifestPath))
        {
            throw new InvalidOperationException("promotion wrote no canonical manifest.");
        }

        if (!FixedTimeDigestEquals(Sha256For(liveCompatibilityManifestPath), expectedCompatibilitySha256))
        {
            throw new InvalidOperationException(
                "public compatibility manifest bytes do not match the Registry-verified activation digest.");
        }

        if (!FixedTimeDigestEquals(Sha256For(liveCanonicalManifestPath), expectedCanonicalSha256))
        {
            throw new InvalidOperationException(
                "public canonical manifest bytes do not match the Registry-verified activation digest.");
        }

        PublicReleaseManifestDto liveCompatibilityManifest = LoadCompatibilityManifest(liveCompatibilityManifestPath);
        HashSet<string> liveCompatibilityIds = liveCompatibilityManifest.Downloads
            .Select(static artifact => artifact.Id)
            .Where(static id => !string.IsNullOrWhiteSpace(id))
            .ToHashSet(StringComparer.OrdinalIgnoreCase);

        JsonObject liveCanonicalManifest = LoadJsonObject(liveCanonicalManifestPath);
        HashSet<string> liveCanonicalIds = LoadCanonicalArtifacts(liveCanonicalManifest)
            .Select(static artifact => artifact.ArtifactId)
            .Where(static id => !string.IsNullOrWhiteSpace(id))
            .ToHashSet(StringComparer.OrdinalIgnoreCase);

        foreach (string artifactId in promotedArtifactIds)
        {
            if (!liveCompatibilityIds.Contains(artifactId))
            {
                throw new InvalidOperationException($"public compatibility manifest is missing promoted artifact {artifactId}.");
            }

            if (!liveCanonicalIds.Contains(artifactId))
            {
                throw new InvalidOperationException($"public canonical manifest is missing promoted artifact {artifactId}.");
            }
        }

        string filesRoot = Path.Combine(downloadsRoot, "files");
        foreach (PublicReleaseArtifactDto artifact in liveCompatibilityManifest.Downloads.Where(download => promotedArtifactIds.Contains(download.Id, StringComparer.OrdinalIgnoreCase)))
        {
            string fileName = ResolveDownloadFileName(artifact);
            string artifactPath = Path.Combine(filesRoot, fileName);
            if (!File.Exists(artifactPath))
            {
                throw new InvalidOperationException($"public downloads root is missing promoted artifact file {fileName}.");
            }
        }

        ValidateRegistryBoundaryCompatibilityCounts(liveCompatibilityManifest, liveCanonicalManifest);
        ReleaseSelectionService releaseSelection = new(new PublicCanonFileLoader(_configuration));
        return releaseSelection.ApplyAccessPolicy(liveCompatibilityManifest);
    }

    private static bool FixedTimeDigestEquals(string left, string right)
    {
        try
        {
            return CryptographicOperations.FixedTimeEquals(
                Convert.FromHexString(left),
                Convert.FromHexString(right));
        }
        catch (FormatException)
        {
            return false;
        }
    }

    private static void ValidateRegistryBoundaryCompatibilityCounts(
        PublicReleaseManifestDto compatibilityManifest,
        JsonObject canonicalManifest)
    {
        int publishedArtifactCount = compatibilityManifest.Downloads.Count;
        JsonObject? canonicalCoverage = canonicalManifest["registryBoundaryCoverage"] as JsonObject;
        JsonObject? canonicalPersistence = canonicalCoverage?["persistence"] as JsonObject;
        JsonObject? canonicalCompatibility = canonicalCoverage?["compatibility"] as JsonObject;
        int persistedArtifactCount = GetJsonInt32(canonicalPersistence?["artifactCount"]);
        int canonicalCompatible = GetJsonInt32(canonicalCompatibility?["compatibleArtifactCount"]);
        if (persistedArtifactCount != publishedArtifactCount)
        {
            throw new InvalidOperationException(
                $"RELEASE_CHANNEL.generated.json registryBoundaryCoverage.persistence.artifactCount must equal the published artifact count ({publishedArtifactCount}), got {persistedArtifactCount}");
        }

        if (canonicalCompatible < 0 || canonicalCompatible > publishedArtifactCount)
        {
            throw new InvalidOperationException(
                $"RELEASE_CHANNEL.generated.json registryBoundaryCoverage.compatibility.compatibleArtifactCount must be between zero and the published artifact count ({publishedArtifactCount}), got {canonicalCompatible}");
        }

        if (NormalizeToken(GetJsonString(canonicalManifest["supportabilityState"])) == "preview_supported"
            && canonicalCompatible != publishedArtifactCount)
        {
            throw new InvalidOperationException(
                $"RELEASE_CHANNEL.generated.json preview_supported release must keep registryBoundaryCoverage.compatibility.compatibleArtifactCount equal to published artifact count ({publishedArtifactCount}), got {canonicalCompatible}");
        }
    }

    private sealed record CanonicalArtifactState(
        string ArtifactId,
        string Head,
        string Platform,
        string Rid,
        string Arch,
        string Kind,
        string ArtifactStatus,
        string ArtifactRolloutState,
        string ArtifactRolloutReason,
        string RevokeReason,
        string CompatibilityState,
        string CompatibilityReason,
        string ArtifactKnownIssueSummary);

    private sealed record CompatibilityManifestPayload(
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
        CompatibilityProofPayload? ReleaseProof,
        DateTimeOffset? GeneratedAt,
        [property: JsonPropertyName("generated_at")] DateTimeOffset? GeneratedAtAlias,
        string? ContractName,
        [property: JsonPropertyName("contract_name")] string? ContractNameAlias,
        JsonElement? DesktopTupleCoverage,
        JsonElement? RegistryBoundaryCoverage);

    private sealed record CompatibilityProofPayload(
        string? Status,
        DateTimeOffset? GeneratedAt,
        string? BaseUrl,
        IReadOnlyList<string>? JourneysPassed,
        IReadOnlyList<string>? ProofRoutes,
        JsonElement? UiLocalizationReleaseGate);

    private sealed record CanonicalArtifactRecord(
        [property: JsonPropertyName("artifactId")] string ArtifactId,
        [property: JsonPropertyName("head")] string? Head,
        [property: JsonPropertyName("platform")] string? Platform,
        [property: JsonPropertyName("rid")] string? Rid,
        [property: JsonPropertyName("arch")] string? Arch,
        [property: JsonPropertyName("kind")] string? Kind,
        [property: JsonPropertyName("status")] string? Status,
        [property: JsonPropertyName("rolloutState")] string? RolloutState,
        [property: JsonPropertyName("revokeState")] string? RevokeState,
        [property: JsonPropertyName("fileName")] string? FileName,
        [property: JsonPropertyName("downloadUrl")] string? DownloadUrl,
        [property: JsonPropertyName("sha256")] string? Sha256,
        [property: JsonPropertyName("sizeBytes")] long? SizeBytes);

    private sealed record RegistryManifestActivationReceipt(
        string ContractName,
        string RegistryContractName,
        string Version,
        string Channel,
        DateTimeOffset PublishedAt,
        DateTimeOffset ActivatedAt,
        string CompatibilityManifestSha256,
        string CanonicalManifestSha256);

    private sealed record StartupSmokeReceipt(
        [property: JsonPropertyName("headId")] string HeadId,
        [property: JsonPropertyName("platform")] string Platform,
        [property: JsonPropertyName("arch")] string Arch,
        [property: JsonPropertyName("artifactDigest")] string? ArtifactDigest,
        [property: JsonPropertyName("artifactSha256")] string? ArtifactSha256);

    private sealed record PromotionEvidenceDocument(
        [property: JsonPropertyName("contractName")] string ContractName,
        [property: JsonPropertyName("generatedAt")] DateTimeOffset GeneratedAt,
        [property: JsonPropertyName("artifacts")] IReadOnlyList<PromotionArtifactEvidence> Artifacts);

    private sealed record PromotionArtifactEvidence(
        [property: JsonPropertyName("artifactId")] string ArtifactId,
        [property: JsonPropertyName("fileName")] string? FileName,
        [property: JsonPropertyName("platform")] string? Platform,
        [property: JsonPropertyName("promotionStatus")] string PromotionStatus,
        [property: JsonPropertyName("startupSmokeStatus")] string StartupSmokeStatus,
        [property: JsonPropertyName("signingStatus")] string? SigningStatus,
        [property: JsonPropertyName("notarizationStatus")] string? NotarizationStatus);
}
