using System.IO.Compression;
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
    IReadOnlyList<ReleasePromotionInstallClaim>? SignedInInstallClaims = null);

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
    private const string PromotionEvidenceRelativePath = "release-evidence/public-promotion.json";
    private const string PublicBaseUrlKey = "GOOGLE_OIDC_REDIRECT_URI";
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
        string? promotionEvidencePath = ResolveOptionalFile(bundleRoot, PromotionEvidenceRelativePath);

        PublicReleaseManifestDto incomingCompatibilityManifest = LoadCompatibilityManifest(compatibilityManifestPath);
        JsonObject incomingCanonicalManifest = LoadJsonObject(canonicalManifestPath);

        IReadOnlyList<CanonicalArtifactRecord> incomingCanonicalArtifacts = LoadCanonicalArtifacts(incomingCanonicalManifest);
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
        JsonObject? existingCanonicalManifest = File.Exists(liveCanonicalManifestPath)
            ? LoadJsonObject(liveCanonicalManifestPath)
            : null;

        IReadOnlySet<string> incomingArtifactIds = incomingCompatibilityManifest.Downloads
            .Select(static artifact => artifact.Id)
            .Where(static id => !string.IsNullOrWhiteSpace(id))
            .ToHashSet(StringComparer.OrdinalIgnoreCase);

        List<string> replacedFileNames = existingCompatibilityManifest?.Downloads
            .Where(download => incomingArtifactIds.Contains(download.Id))
            .Select(ResolveDownloadFileName)
            .Where(static fileName => !string.IsNullOrWhiteSpace(fileName))
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .ToList()
            ?? new List<string>();

        PublicReleaseManifestDto mergedCompatibilityManifest = MergeCompatibilityManifest(existingCompatibilityManifest, incomingCompatibilityManifest);
        JsonObject mergedCanonicalManifest = MergeCanonicalManifest(existingCanonicalManifest, incomingCanonicalManifest);

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

        HashSet<string> mergedFileNames = mergedCompatibilityManifest.Downloads
            .Select(ResolveDownloadFileName)
            .Where(static fileName => !string.IsNullOrWhiteSpace(fileName))
            .ToHashSet(StringComparer.OrdinalIgnoreCase);
        foreach (string replacedFileName in replacedFileNames)
        {
            if (mergedFileNames.Contains(replacedFileName))
            {
                continue;
            }

            string oldPath = Path.Combine(filesDestinationRoot, replacedFileName);
            if (File.Exists(oldPath))
            {
                File.Delete(oldPath);
            }
        }

        WriteJsonAtomically(liveCompatibilityManifestPath, mergedCompatibilityManifest);
        WriteJsonAtomically(liveCanonicalManifestPath, mergedCanonicalManifest);

        IReadOnlyList<string> promotedArtifactIds = incomingCompatibilityManifest.Downloads
            .Select(static artifact => artifact.Id)
            .Where(static id => !string.IsNullOrWhiteSpace(id))
            .ToArray();

        string baseUrl = ResolvePublicBaseUrl();
        PublicReleaseManifestDto publicShelfManifest = ValidatePublicShelfCoherence(
            downloadsRoot,
            liveCompatibilityManifestPath,
            liveCanonicalManifestPath,
            promotedArtifactIds);
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
                .ToArray());
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
        PublicReleaseManifestDto? manifest = JsonSerializer.Deserialize<PublicReleaseManifestDto>(File.ReadAllText(manifestPath), JsonOptions);
        return manifest ?? throw new InvalidDataException($"compatibility release manifest could not be parsed: {manifestPath}");
    }

    private static JsonObject LoadJsonObject(string path)
    {
        JsonNode? parsed = JsonNode.Parse(File.ReadAllText(path));
        return parsed?.AsObject() ?? throw new InvalidDataException($"json object could not be parsed: {path}");
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

        if (!string.Equals(artifactEvidence.StartupSmokeStatus, "pass", StringComparison.OrdinalIgnoreCase))
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

            if (!previewUnsignedAllowed)
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
        if (existingManifest is null)
        {
            return incomingManifest;
        }

        Dictionary<string, PublicReleaseArtifactDto> incomingById = incomingManifest.Downloads
            .ToDictionary(static artifact => artifact.Id, StringComparer.OrdinalIgnoreCase);

        List<PublicReleaseArtifactDto> mergedDownloads = new(existingManifest.Downloads.Count + incomingById.Count);
        HashSet<string> seen = new(StringComparer.OrdinalIgnoreCase);
        foreach (PublicReleaseArtifactDto existingArtifact in existingManifest.Downloads)
        {
            if (incomingById.TryGetValue(existingArtifact.Id, out PublicReleaseArtifactDto? replacement))
            {
                mergedDownloads.Add(replacement);
                seen.Add(existingArtifact.Id);
                continue;
            }

            mergedDownloads.Add(existingArtifact);
            seen.Add(existingArtifact.Id);
        }

        foreach ((string artifactId, PublicReleaseArtifactDto artifact) in incomingById)
        {
            if (!seen.Contains(artifactId))
            {
                mergedDownloads.Add(artifact);
            }
        }

        return incomingManifest with
        {
            Downloads = mergedDownloads
        };
    }

    private static JsonObject MergeCanonicalManifest(JsonObject? existingManifest, JsonObject incomingManifest)
    {
        JsonObject merged = existingManifest?.DeepClone().AsObject() ?? new JsonObject();
        foreach ((string propertyName, JsonNode? node) in incomingManifest)
        {
            if (string.Equals(propertyName, "artifacts", StringComparison.Ordinal)
                || string.Equals(propertyName, "runtimeBundleHeads", StringComparison.Ordinal))
            {
                continue;
            }

            merged[propertyName] = node?.DeepClone();
        }

        merged["artifacts"] = MergeArrayById(
            existingManifest?["artifacts"] as JsonArray,
            incomingManifest["artifacts"] as JsonArray,
            "artifactId");

        if (incomingManifest["runtimeBundleHeads"] is JsonArray incomingHeads)
        {
            merged["runtimeBundleHeads"] = MergeArrayById(
                existingManifest?["runtimeBundleHeads"] as JsonArray,
                incomingHeads,
                "headId");
        }

        return merged;
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
        using var sha = System.Security.Cryptography.SHA256.Create();
        using FileStream stream = File.OpenRead(path);
        return Convert.ToHexString(sha.ComputeHash(stream)).ToLowerInvariant();
    }

    private PublicReleaseManifestDto ValidatePublicShelfCoherence(
        string downloadsRoot,
        string liveCompatibilityManifestPath,
        string liveCanonicalManifestPath,
        IReadOnlyList<string> promotedArtifactIds)
    {
        if (!File.Exists(liveCompatibilityManifestPath))
        {
            throw new InvalidOperationException("promotion wrote no compatibility manifest.");
        }

        if (!File.Exists(liveCanonicalManifestPath))
        {
            throw new InvalidOperationException("promotion wrote no canonical manifest.");
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

        ReleaseSelectionService releaseSelection = new(new PublicCanonFileLoader(_configuration));
        return releaseSelection.ApplyAccessPolicy(liveCompatibilityManifest);
    }

    private sealed record CanonicalArtifactRecord(
        [property: JsonPropertyName("artifactId")] string ArtifactId,
        [property: JsonPropertyName("head")] string? Head,
        [property: JsonPropertyName("platform")] string? Platform,
        [property: JsonPropertyName("arch")] string? Arch,
        [property: JsonPropertyName("kind")] string? Kind,
        [property: JsonPropertyName("fileName")] string? FileName,
        [property: JsonPropertyName("downloadUrl")] string? DownloadUrl,
        [property: JsonPropertyName("sha256")] string? Sha256,
        [property: JsonPropertyName("sizeBytes")] long? SizeBytes);

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
