using System.Globalization;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.Json.Serialization;
using Chummer.Hub.Registry.Contracts.InstallLinking;
using Chummer.Run.Contracts.PublicSurface;

namespace Chummer.Run.Api.Services;

public sealed class PublicReleaseManifestService
{
    private const string DefaultManifestContractName = "Chummer.Hub.Registry.Contracts";
    private const string DefaultLocalProofRelativePath = ".codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json";
    private const string RegistryCurrentUrlKey = "CHUMMER_RELEASE_REGISTRY_CURRENT_URL";
    private const string RegistryBaseUrlKey = "CHUMMER_HUB_REGISTRY_BASE_URL";
    private const string PublicCanonRootKey = "CHUMMER_PUBLIC_CANON_ROOT";
    private const string LocalProofFileKey = "CHUMMER_HUB_LOCAL_RELEASE_PROOF_FILE";
    private const string PublicDisabledArtifactIdsKey = "CHUMMER_PUBLIC_DISABLED_ARTIFACT_IDS";
    private const string ReleaseDisabledArtifactIdsKey = "CHUMMER_RELEASE_DISABLED_ARTIFACT_IDS";
    private const string ForceAccountRequiredDownloadsKey = "CHUMMER_PUBLIC_FORCE_ACCOUNT_REQUIRED_DOWNLOADS";
    private static readonly string[] RequiredDesktopPlatforms = ["linux", "windows", "macos"];
    private static readonly string[] RequiredDesktopHeads = ["avalonia"];
    private static readonly TimeSpan ManifestCacheFreshTtl = TimeSpan.FromSeconds(30);
    private static readonly TimeSpan ManifestCacheStaleTtl = TimeSpan.FromMinutes(2);
    private static readonly TimeSpan RegistryRuntimeManifestFetchTimeout = TimeSpan.FromMilliseconds(800);
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
    private readonly ReleaseShelfGenerationStore _shelfStore;
    private readonly FlagshipReadinessArtifactService _flagshipReadiness;
    private readonly GoldReadinessArtifactService _goldReadiness;
    private readonly ImportRouteParityProofGuardService _importRouteParityProofGuard;
    private readonly TimeProvider _timeProvider;
    private readonly PrivacyLaunchGateSnapshot _privacyLaunchGate;
    private readonly object _manifestCacheLock = new();
    private readonly Dictionary<string, CachedManifestState> _manifestCache = new(StringComparer.Ordinal);

    public PublicReleaseManifestService(IConfiguration configuration)
        : this(
            configuration,
            httpClient: null,
            TimeProvider.System,
            PrivacyLaunchGate.Current,
            new ReleaseShelfGenerationStore(configuration))
    {
    }

    public PublicReleaseManifestService(IConfiguration configuration, HttpClient? httpClient)
        : this(
            configuration,
            httpClient,
            TimeProvider.System,
            PrivacyLaunchGate.Current,
            new ReleaseShelfGenerationStore(configuration))
    {
    }

    internal PublicReleaseManifestService(
        IConfiguration configuration,
        ReleaseShelfGenerationStore shelfStore)
        : this(
            configuration,
            httpClient: null,
            TimeProvider.System,
            PrivacyLaunchGate.Current,
            shelfStore)
    {
    }

    internal PublicReleaseManifestService(
        IConfiguration configuration,
        HttpClient? httpClient,
        TimeProvider timeProvider)
        : this(
            configuration,
            httpClient,
            timeProvider,
            PrivacyLaunchGate.Current,
            new ReleaseShelfGenerationStore(configuration))
    {
    }

    internal PublicReleaseManifestService(
        IConfiguration configuration,
        HttpClient? httpClient,
        TimeProvider timeProvider,
        PrivacyLaunchGateSnapshot privacyLaunchGate)
        : this(
            configuration,
            httpClient,
            timeProvider,
            privacyLaunchGate,
            new ReleaseShelfGenerationStore(configuration))
    {
    }

    internal PublicReleaseManifestService(
        IConfiguration configuration,
        HttpClient? httpClient,
        TimeProvider timeProvider,
        PrivacyLaunchGateSnapshot privacyLaunchGate,
        ReleaseShelfGenerationStore shelfStore)
    {
        _configuration = configuration;
        _httpClient = httpClient;
        _shelfStore = shelfStore ?? throw new ArgumentNullException(nameof(shelfStore));
        _flagshipReadiness = new FlagshipReadinessArtifactService(configuration);
        _goldReadiness = new GoldReadinessArtifactService(configuration);
        _importRouteParityProofGuard = new ImportRouteParityProofGuardService(configuration);
        _timeProvider = timeProvider ?? throw new ArgumentNullException(nameof(timeProvider));
        _privacyLaunchGate = privacyLaunchGate ?? throw new ArgumentNullException(nameof(privacyLaunchGate));
    }

    public PublicReleaseManifestDto LoadManifest()
        => LoadManifest(CaptureShelfSnapshot());

    public ReleaseShelfSnapshot CaptureShelfSnapshot()
        => _shelfStore.CaptureForCurrentRequest();

    /// <summary>
    /// Captures the currently active shelf without consulting the request generation
    /// pin. This is reserved for channel-wide safety truth, such as revocations, that
    /// must govern both current and retained-generation delivery routes.
    /// </summary>
    internal ReleaseShelfSnapshot CaptureUnpinnedActiveShelfSnapshot()
        => _shelfStore.Capture();

    public ReleaseShelfSnapshot CaptureShelfGeneration(string generationId)
        => _shelfStore.CaptureGenerationForCurrentRequest(generationId);

    public PublicReleaseManifestDto LoadManifest(ReleaseShelfSnapshot snapshot)
    {
        ArgumentNullException.ThrowIfNull(snapshot);
        DateTimeOffset now = _timeProvider.GetUtcNow();
        byte[]? generationCanonicalBytes = snapshot.IsLegacy
            ? null
            : snapshot.ReadVerifiedFileBytes(
                ReleaseShelfGenerationStore.CanonicalManifestFileName,
                ReleaseShelfGenerationStore.MaximumManifestBytes)
              ?? throw new InvalidDataException("Captured release shelf canonical manifest no longer matches its inventory binding.");

        PublicReleaseManifestDto? cachedManifest = TryGetCachedManifest(snapshot.CacheKey, now, allowStale: false);
        if (cachedManifest is not null
            && !CachedManifestProofFreshnessDrifts(cachedManifest, now)
            && !CachedManifestPrivacyReadinessDrifts(cachedManifest, _privacyLaunchGate))
        {
            return cachedManifest;
        }

        if (!snapshot.IsLegacy)
        {
            PublicReleaseManifestDto immutableManifest = BindGeneration(
                LoadRegistryReleaseManifestPayload(
                    FilterManifestPayload(
                        DecodeUtf8Manifest(
                            generationCanonicalBytes!,
                            ReleaseShelfGenerationStore.CanonicalManifestFileName)),
                    "registry"),
                snapshot);
            WriteManifestCache(snapshot.CacheKey, immutableManifest, now);
            return immutableManifest;
        }

        string root = snapshot.PhysicalRoot;
        string registryManifestPath = ResolveRegistryManifestPath(snapshot);
        bool registryManifestExists = snapshot.IsLegacy
            ? File.Exists(registryManifestPath)
            : generationCanonicalBytes is not null;
        bool preferLocalRegistryManifest = registryManifestExists && ShouldPreferLocalRegistryManifestInDevelopment();
        var registryManifestUrl = preferLocalRegistryManifest ? null : ResolveRegistryManifestUrl();
        PublicReleaseManifestDto? runtimeManifest = null;
        if (!string.IsNullOrWhiteSpace(registryManifestUrl))
        {
            runtimeManifest = TryLoadRegistryReleaseManifestFromUrl(registryManifestUrl, snapshot);
        }

        PublicReleaseManifestDto manifest;
        if (registryManifestExists)
        {
            string canonicalJson = snapshot.IsLegacy
                ? ReadLegacyManifestText(registryManifestPath)
                : DecodeUtf8Manifest(
                    generationCanonicalBytes!,
                    ReleaseShelfGenerationStore.CanonicalManifestFileName);
            var canonicalManifest = LoadRegistryReleaseManifestPayload(FilterManifestPayload(canonicalJson), "registry");
            manifest = ApplyImportRouteParityGuard(ApplyGoldReadinessGuard(ApplyFlagshipReadinessGuard(ApplyArtifactSuppressionPolicy(ApplyLocalReleaseProofFallback(ChoosePreferredRegistryManifest(runtimeManifest, canonicalManifest), snapshot)))));
            manifest = BindGeneration(manifest, snapshot);
            WriteManifestCache(snapshot.CacheKey, manifest, now);
            return manifest;
        }

        if (runtimeManifest is not null)
        {
            manifest = ApplyImportRouteParityGuard(ApplyGoldReadinessGuard(ApplyFlagshipReadinessGuard(ApplyArtifactSuppressionPolicy(ApplyLocalReleaseProofFallback(runtimeManifest, snapshot)))));
            manifest = BindGeneration(manifest, snapshot);
            WriteManifestCache(snapshot.CacheKey, manifest, now);
            return manifest;
        }

        var manifestPath = Path.Combine(root, ReleaseShelfGenerationStore.CompatibilityManifestFileName);
        if (snapshot.IsLegacy && !File.Exists(manifestPath))
        {
            manifest = ApplyImportRouteParityGuard(ApplyGoldReadinessGuard(ApplyFlagshipReadinessGuard(ApplyArtifactSuppressionPolicy(ApplyLocalReleaseProofFallback(new PublicReleaseManifestDto(
                Version: "unpublished",
                Channel: "preview",
                PublishedAt: now,
                Downloads: [],
                Source: "fallback",
                Status: "unpublished",
                Message: "No published desktop builds are available yet.",
                HasFallbackSource: false,
                GeneratedAt: now), snapshot)))));
            manifest = BindGeneration(manifest, snapshot);
            WriteManifestCache(snapshot.CacheKey, manifest, now);
            return manifest;
        }

        string compatibilityJson = ReadLegacyManifestText(manifestPath);
        manifest = ApplyImportRouteParityGuard(ApplyGoldReadinessGuard(ApplyFlagshipReadinessGuard(ApplyArtifactSuppressionPolicy(ApplyLocalReleaseProofFallback(LoadReleaseManifestPayload(FilterManifestPayload(compatibilityJson)), snapshot)))));
        manifest = BindGeneration(manifest, snapshot);
        WriteManifestCache(snapshot.CacheKey, manifest, now);
        return manifest;
    }

    /// <summary>
    /// Loads the immutable Registry artifact bindings without applying Hub display
    /// suppression. Delivery authorization must resolve the original binding first
    /// so a globally disabled or revoked artifact returns an explicit gone decision
    /// instead of being indistinguishable from an unknown route.
    /// </summary>
    internal PublicReleaseManifestDto LoadDeliveryManifest(ReleaseShelfSnapshot snapshot)
    {
        ArgumentNullException.ThrowIfNull(snapshot);
        if (snapshot.IsLegacy)
        {
            return LoadManifest(snapshot);
        }

        byte[] canonicalBytes = snapshot.ReadVerifiedFileBytes(
                ReleaseShelfGenerationStore.CanonicalManifestFileName,
                ReleaseShelfGenerationStore.MaximumManifestBytes)
            ?? throw new InvalidDataException(
                "Captured release shelf canonical manifest no longer matches its inventory binding.");
        return BindGeneration(
            LoadRegistryReleaseManifestPayload(
                DecodeUtf8Manifest(
                    canonicalBytes,
                    ReleaseShelfGenerationStore.CanonicalManifestFileName),
                "registry"),
            snapshot);
    }

    private static PublicReleaseManifestDto BindGeneration(
        PublicReleaseManifestDto manifest,
        ReleaseShelfSnapshot snapshot)
        => snapshot.GenerationId is null
            ? manifest
            : manifest with
            {
                GenerationId = snapshot.GenerationId,
                Version = snapshot.ReleaseVersion ?? manifest.Version,
                Channel = snapshot.Channel ?? manifest.Channel,
                PublishedAt = snapshot.PublishedAt ?? manifest.PublishedAt
            };

    private static byte[] ReadBoundedLegacyBytes(string path, int maximumBytes, string label)
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
            long descriptorLength = stream.Length;
            if (descriptorLength <= 0 || descriptorLength > maximumBytes)
            {
                throw new InvalidDataException($"{label} exceeds the permitted manifest byte length.");
            }

            byte[] bytes = new byte[checked((int)descriptorLength)];
            stream.ReadExactly(bytes);
            if (stream.ReadByte() != -1 || stream.Length != descriptorLength)
            {
                throw new InvalidDataException($"{label} changed while it was being read.");
            }

            return bytes;
        }
        catch (EndOfStreamException exception)
        {
            throw new InvalidDataException($"{label} changed while it was being read.", exception);
        }
        catch (IOException exception)
        {
            throw new InvalidDataException($"{label} could not be read atomically.", exception);
        }
    }

    private static string DecodeUtf8Manifest(byte[] bytes, string label)
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

    private static string ReadLegacyManifestText(string path)
        => DecodeUtf8Manifest(
            ReadBoundedLegacyBytes(
                path,
                ReleaseShelfGenerationStore.MaximumManifestBytes,
                Path.GetFileName(path)),
            Path.GetFileName(path));

    public bool RequiresCanonicalManifestRewrite()
        => RequiresCanonicalManifestRewrite(CaptureShelfSnapshot());

    public bool RequiresCanonicalManifestRewrite(ReleaseShelfSnapshot snapshot)
    {
        ArgumentNullException.ThrowIfNull(snapshot);
        if (snapshot.IsExplicitGeneration)
        {
            return false;
        }
        if (ResolveDisabledArtifactIds().Count > 0 || ForceAccountRequiredDownloads())
        {
            return true;
        }

        string? manifestPath = ResolveCanonicalManifestFilePath(snapshot);
        if (string.IsNullOrWhiteSpace(manifestPath) || !File.Exists(manifestPath))
        {
            return false;
        }

        byte[]? manifestBytes = snapshot.ReadVerifiedFileBytes(
            ReleaseShelfGenerationStore.CanonicalManifestFileName,
            ReleaseShelfGenerationStore.MaximumManifestBytes);
        if (!snapshot.IsLegacy && manifestBytes is null)
        {
            throw new InvalidDataException("Captured release shelf canonical manifest no longer matches its inventory binding.");
        }

        string json = manifestBytes is null
            ? ReadLegacyManifestText(manifestPath)
            : DecodeUtf8Manifest(manifestBytes, ReleaseShelfGenerationStore.CanonicalManifestFileName);
        if (CanonicalManifestNeedsInstallAwareRewrite(json))
        {
            return true;
        }

        JsonObject? source = JsonNode.Parse(json)?.AsObject();
        if (source is null)
        {
            return false;
        }

        JsonObject projected = source.DeepClone().AsObject();
        ApplyProofFreshnessSupportabilityFloor(
            projected,
            _timeProvider.GetUtcNow(),
            _privacyLaunchGate);
        return !JsonNode.DeepEquals(source, projected);
    }

    public string? LoadCanonicalManifestJson()
        => LoadCanonicalManifestJson(CaptureShelfSnapshot());

    public string? LoadCanonicalManifestJson(ReleaseShelfSnapshot snapshot)
    {
        ArgumentNullException.ThrowIfNull(snapshot);
        byte[]? bytes;
        if (snapshot.IsLegacy)
        {
            string? path = ResolveCanonicalManifestFilePath(snapshot);
            bytes = path is null
                ? null
                : ReadBoundedLegacyBytes(
                    path,
                    ReleaseShelfGenerationStore.MaximumManifestBytes,
                    ReleaseShelfGenerationStore.CanonicalManifestFileName);
        }
        else
        {
            bytes = LoadGenerationCanonicalManifestBytes(snapshot);
        }
        if (bytes is null)
        {
            return null;
        }

        string json = DecodeUtf8Manifest(bytes, ReleaseShelfGenerationStore.CanonicalManifestFileName);
        // Layout-v1 bytes are immutable inputs, not permission to bypass the
        // runtime proof/privacy supportability floor. Project a response copy for
        // both legacy and generation shelves; generation-bound raw-byte routes
        // continue to use LoadGenerationCanonicalManifestBytes directly.
        return FilterManifestPayload(json);
    }

    public byte[]? LoadGenerationCanonicalManifestBytes(ReleaseShelfSnapshot snapshot)
        => LoadBoundManifestBytes(snapshot, ReleaseShelfGenerationStore.CanonicalManifestFileName);

    public byte[]? LoadGenerationCompatibilityManifestBytes(ReleaseShelfSnapshot snapshot)
        => LoadBoundManifestBytes(snapshot, ReleaseShelfGenerationStore.CompatibilityManifestFileName);

    private static byte[]? LoadBoundManifestBytes(ReleaseShelfSnapshot snapshot, string fileName)
    {
        ArgumentNullException.ThrowIfNull(snapshot);
        if (snapshot.IsLegacy)
        {
            throw new InvalidOperationException("Generation-bound manifest bytes require an active layout-v1 snapshot.");
        }

        return snapshot.ReadVerifiedFileBytes(fileName, ReleaseShelfGenerationStore.MaximumManifestBytes);
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
                   || RuntimeManifestDriftsCanonicalRegistryTruth(runtimeManifest, canonicalManifest)
                ? canonicalManifest
                : runtimeManifest;
        }

        if (canonicalManifest.Downloads.Count > 0)
        {
            return canonicalManifest;
        }

        return runtimeManifest ?? canonicalManifest;
    }

    private static bool CanonicalManifestNeedsInstallAwareRewrite(string json)
    {
        JsonObject? manifest = JsonNode.Parse(json)?.AsObject();
        if (manifest is null)
        {
            return false;
        }

        if (manifest["desktopTupleCoverage"] is not JsonObject coverage)
        {
            return false;
        }

        if (InstallAwareRegistryCurrentTruthDrifts(manifest, coverage))
        {
            return true;
        }
        List<ManifestArtifactShape> artifacts = CollectManifestArtifactShapes(manifest);
        string channelId = NormalizeToken(GetJsonString(manifest["channelId"]) ?? GetJsonString(manifest["channel"]));
        string releaseVersion = (GetJsonString(manifest["version"]) ?? string.Empty).Trim();
        JsonArray expected = BuildInstallAwareArtifactRegistry(artifacts, coverage, channelId, releaseVersion);
        JsonNode? current = manifest["installAwareArtifactRegistry"];
        if (!JsonNode.DeepEquals(current, expected))
        {
            return true;
        }

        JsonArray expectedDesktopSurfaceRefs = BuildDesktopSurfaceRefs(artifacts, coverage, channelId, releaseVersion);
        return !JsonNode.DeepEquals(manifest["desktopSurfaceRefs"], expectedDesktopSurfaceRefs);
    }

    private static bool InstallAwareRegistryCurrentTruthDrifts(JsonObject manifest, JsonObject coverage)
    {
        if (coverage["desktopRouteTruth"] is not JsonArray desktopRouteTruth)
        {
            return false;
        }

        if (manifest["installAwareArtifactRegistry"] is not JsonArray installAwareRegistry)
        {
            return desktopRouteTruth.OfType<JsonObject>().Any();
        }

        Dictionary<string, JsonObject> registryByTuple = installAwareRegistry
            .OfType<JsonObject>()
            .Select(row => new
            {
                TupleId = NormalizeToken(GetJsonString(row["tupleId"])),
                Row = row
            })
            .Where(static entry => !string.IsNullOrWhiteSpace(entry.TupleId))
            .GroupBy(static entry => entry.TupleId, StringComparer.OrdinalIgnoreCase)
            .ToDictionary(
                static group => group.Key,
                static group => group.First().Row,
                StringComparer.OrdinalIgnoreCase);

        int expectedRouteCount = 0;
        foreach (JsonObject routeRow in desktopRouteTruth.OfType<JsonObject>())
        {
            string tupleId = NormalizeToken(GetJsonString(routeRow["tupleId"]));
            if (string.IsNullOrWhiteSpace(tupleId))
            {
                continue;
            }

            expectedRouteCount++;
            if (!registryByTuple.TryGetValue(tupleId, out JsonObject? registryRow))
            {
                return true;
            }

            bool expectedCurrentForInstalledBuild =
                string.Equals(NormalizeToken(GetJsonString(routeRow["promotionState"])), "promoted", StringComparison.Ordinal)
                && !string.Equals(NormalizeToken(GetJsonString(routeRow["revokeState"])), "revoked", StringComparison.Ordinal);
            bool currentForInstalledBuild = registryRow["currentForInstalledBuild"]?.GetValue<bool>() ?? false;
            if (currentForInstalledBuild != expectedCurrentForInstalledBuild)
            {
                return true;
            }
        }

        return registryByTuple.Count != expectedRouteCount;
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

    private static bool RuntimeManifestDriftsCanonicalRegistryTruth(
        PublicReleaseManifestDto runtimeManifest,
        PublicReleaseManifestDto canonicalManifest)
        => ScalarDrifts(runtimeManifest.Version, canonicalManifest.Version)
           || ScalarDrifts(runtimeManifest.PublicVersion, canonicalManifest.PublicVersion)
           || ScalarDrifts(runtimeManifest.Channel, canonicalManifest.Channel)
           || ScalarDrifts(runtimeManifest.Status, canonicalManifest.Status)
           || ScalarDrifts(runtimeManifest.RolloutState, canonicalManifest.RolloutState)
           || ScalarDrifts(runtimeManifest.RolloutReason, canonicalManifest.RolloutReason)
           || ScalarDrifts(runtimeManifest.SupportabilityState, canonicalManifest.SupportabilityState)
           || ScalarDrifts(runtimeManifest.SupportabilitySummary, canonicalManifest.SupportabilitySummary)
           || ScalarDrifts(runtimeManifest.ProofStatus, canonicalManifest.ProofStatus)
           || ReleaseProofDrifts(runtimeManifest.ReleaseProof, canonicalManifest.ReleaseProof)
           || JsonElementDrifts(runtimeManifest.DesktopTupleCoverage, canonicalManifest.DesktopTupleCoverage)
           || JsonElementDrifts(runtimeManifest.RegistryBoundaryCoverage, canonicalManifest.RegistryBoundaryCoverage)
           || JsonElementDrifts(runtimeManifest.PublicTrustMetrics, canonicalManifest.PublicTrustMetrics)
           || JsonElementDrifts(runtimeManifest.InstallAwareArtifactRegistry, canonicalManifest.InstallAwareArtifactRegistry)
           || JsonElementDrifts(runtimeManifest.DesktopSurfaceRefs, canonicalManifest.DesktopSurfaceRefs)
           || JsonElementDrifts(runtimeManifest.ArtifactIdentityRegistry, canonicalManifest.ArtifactIdentityRegistry)
           || JsonElementDrifts(runtimeManifest.ArtifactPublicationBindings, canonicalManifest.ArtifactPublicationBindings)
           || JsonElementDrifts(runtimeManifest.ExchangeLineageRegistry, canonicalManifest.ExchangeLineageRegistry);

    private static bool ReleaseProofDrifts(
        PublicReleaseProofDto? runtimeProof,
        PublicReleaseProofDto? canonicalProof)
        => !JsonNode.DeepEquals(
            JsonSerializer.SerializeToNode(runtimeProof),
            JsonSerializer.SerializeToNode(canonicalProof));

    private static bool ScalarDrifts(string? runtimeValue, string? canonicalValue)
        => !string.Equals(
            NormalizeOptional(runtimeValue),
            NormalizeOptional(canonicalValue),
            StringComparison.OrdinalIgnoreCase);

    private static bool JsonElementDrifts(JsonElement? runtimeElement, JsonElement? canonicalElement)
    {
        if (runtimeElement is not JsonElement runtime)
        {
            return canonicalElement is JsonElement;
        }

        if (canonicalElement is not JsonElement canonical)
        {
            return true;
        }

        return !JsonNode.DeepEquals(
            JsonNode.Parse(runtime.GetRawText()),
            JsonNode.Parse(canonical.GetRawText()));
    }

    private static bool CachedManifestProofFreshnessDrifts(
        PublicReleaseManifestDto manifest,
        DateTimeOffset evaluationInstant)
    {
        if (manifest.PublicTrustMetrics is not JsonElement publicTrustMetricsElement
            || publicTrustMetricsElement.ValueKind != JsonValueKind.Object
            || JsonNode.Parse(publicTrustMetricsElement.GetRawText()) is not JsonObject publicTrustMetrics
            || publicTrustMetrics["proofFreshness"] is not JsonObject proofFreshness)
        {
            return false;
        }

        JsonObject? releaseProof = JsonSerializer.SerializeToNode(manifest.ReleaseProof)?.AsObject();
        if (releaseProof is not null && manifest.ProofGeneratedAt is DateTimeOffset proofGeneratedAt)
        {
            releaseProof["generatedAt"] = proofGeneratedAt
                .ToUniversalTime()
                .ToString("yyyy-MM-dd'T'HH:mm:ss'Z'", CultureInfo.InvariantCulture);
        }

        ReleaseProofFreshnessEvaluation freshness = ReleaseProofFreshnessEvaluator.Evaluate(
            proofFreshness,
            releaseProof,
            manifest.PublishedAt,
            evaluationInstant);
        string materializedStatus = NormalizeStateToken(GetJsonString(proofFreshness["status"]));
        return !string.Equals(
            materializedStatus,
            NormalizeStateToken(freshness.MaterializedStatus),
            StringComparison.Ordinal);
    }

    private static bool CachedManifestPrivacyReadinessDrifts(
        PublicReleaseManifestDto manifest,
        PrivacyLaunchGateSnapshot privacyLaunchGate)
    {
        if (!privacyLaunchGate.BlocksReleaseSupportability)
        {
            return false;
        }

        if (manifest.PublicTrustMetrics is not JsonElement publicTrustMetricsElement
            || publicTrustMetricsElement.ValueKind != JsonValueKind.Object
            || JsonNode.Parse(publicTrustMetricsElement.GetRawText()) is not JsonObject publicTrustMetrics
            || !JsonNode.DeepEquals(
                publicTrustMetrics["privacyReadiness"],
                privacyLaunchGate.ToJsonObject()))
        {
            return true;
        }

        return string.Equals(
                NormalizeStateToken(manifest.Status),
                "published",
                StringComparison.Ordinal)
            && NormalizeStateToken(manifest.SupportabilityState) is
                "gold_supported" or "preview_supported" or "supported";
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

    private static DateTimeOffset? TryGetJsonDateTimeOffset(JsonNode? node)
        => DateTimeOffset.TryParse(
            GetJsonString(node),
            CultureInfo.InvariantCulture,
            DateTimeStyles.RoundtripKind,
            out DateTimeOffset parsed)
            ? parsed
            : null;

    private static string AppendDistinctSentence(string? existing, string sentence)
    {
        if (string.IsNullOrWhiteSpace(existing))
        {
            return sentence;
        }

        if (existing.Contains(sentence, StringComparison.OrdinalIgnoreCase))
        {
            return existing;
        }

        return $"{existing.Trim().TrimEnd('.')} {sentence}";
    }

    private static bool HasBlockingRolloutState(string? rolloutState)
        => NormalizeOptional(rolloutState) is "coverage_incomplete"
            or "release_review_required"
            or "public_release_review_required"
            or "desktop_polish_needed"
            or "revoked";

    private static bool HasOnlyProofFreshnessRolloutBlocker(PublicReleaseManifestDto manifest)
        => string.Equals(
                NormalizeOptional(manifest.RolloutState),
                "public_release_review_required",
                StringComparison.OrdinalIgnoreCase)
            && manifest.RolloutReason?.Contains(
                "stale or incomplete proof receipts",
                StringComparison.OrdinalIgnoreCase) == true;

    public string? ResolveDownloadFilePath(string? path)
        => ResolveDownloadFilePath(CaptureShelfSnapshot(), path);

    public string? ResolveDownloadFilePath(ReleaseShelfSnapshot snapshot, string? path)
    {
        ArgumentNullException.ThrowIfNull(snapshot);
        if (string.IsNullOrWhiteSpace(path))
        {
            return null;
        }

        var relative = path.Trim().TrimStart('/').Replace('\\', '/');
        if (relative.Contains("..", StringComparison.Ordinal))
        {
            return null;
        }

        return snapshot.IsLegacy
            ? snapshot.ResolveLegacyFilePath($"files/{relative}")
            : null;
    }

    public string? ResolveReleaseEvidenceFilePath(string? path)
        => ResolveReleaseEvidenceFilePath(CaptureShelfSnapshot(), path);

    public string? ResolveReleaseEvidenceFilePath(ReleaseShelfSnapshot snapshot, string? path)
    {
        ArgumentNullException.ThrowIfNull(snapshot);
        if (string.IsNullOrWhiteSpace(path))
        {
            return null;
        }

        string relative = path.Trim().TrimStart('/').Replace('\\', '/');
        if (relative.Contains("..", StringComparison.Ordinal)
            || !relative.EndsWith(".json", StringComparison.OrdinalIgnoreCase))
        {
            return null;
        }

        return snapshot.IsLegacy
            ? snapshot.ResolveLegacyFilePath($"release-evidence/{relative}")
            : null;
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
        => ResolveDownloadFilePath(CaptureShelfSnapshot(), artifact);

    public string? ResolveDownloadFilePath(
        ReleaseShelfSnapshot snapshot,
        PublicReleaseArtifactDto artifact)
    {
        ArgumentNullException.ThrowIfNull(snapshot);
        ArgumentNullException.ThrowIfNull(artifact);
        var fileName = artifact.FileName;
        if (string.IsNullOrWhiteSpace(fileName))
        {
            var rawUrl = artifact.Url ?? string.Empty;
            var withoutQuery = rawUrl.Split('?', '#')[0];
            fileName = Path.GetFileName(withoutQuery);
        }

        return ResolveDownloadFilePath(snapshot, fileName);
    }

    public ReleaseShelfVerifiedFile? OpenVerifiedArtifactFile(
        ReleaseShelfSnapshot snapshot,
        PublicReleaseArtifactDto artifact,
        string? requestedRelativePath = null)
    {
        ArgumentNullException.ThrowIfNull(snapshot);
        ArgumentNullException.ThrowIfNull(artifact);
        if (snapshot.IsLegacy)
        {
            return null;
        }

        string fileName = (artifact.FileName ?? string.Empty).Trim();
        if (string.IsNullOrWhiteSpace(fileName))
        {
            fileName = Path.GetFileName((artifact.Url ?? string.Empty).Split('?', '#')[0]);
        }

        if (string.IsNullOrWhiteSpace(fileName)
            || !string.Equals(Path.GetFileName(fileName), fileName, StringComparison.Ordinal)
            || fileName.Contains('/', StringComparison.Ordinal)
            || fileName.Contains('\\', StringComparison.Ordinal))
        {
            return null;
        }

        if (requestedRelativePath is not null)
        {
            string requested = requestedRelativePath.Trim().TrimStart('/');
            if (!string.Equals(requested, fileName, StringComparison.Ordinal))
            {
                return null;
            }
        }

        ReleaseShelfVerifiedFile? verified = snapshot.OpenVerifiedFile($"files/{fileName}");
        if (verified is null
            || string.IsNullOrWhiteSpace(artifact.Sha256)
            || !string.Equals(verified.ExpectedSha256, artifact.Sha256.Trim(), StringComparison.OrdinalIgnoreCase)
            || (artifact.SizeBytes is long expectedSize && verified.SizeBytes != expectedSize))
        {
            verified?.Dispose();
            return null;
        }

        return verified;
    }

    public string? ResolveCanonicalManifestFilePath()
        => ResolveCanonicalManifestFilePath(CaptureShelfSnapshot());

    public string? ResolveCanonicalManifestFilePath(ReleaseShelfSnapshot snapshot)
    {
        ArgumentNullException.ThrowIfNull(snapshot);
        if (!snapshot.IsLegacy)
        {
            return null;
        }

        string path = ResolveRegistryManifestPath(snapshot);
        return File.Exists(path) ? path : null;
    }

    private PublicReleaseManifestDto ApplyLocalReleaseProofFallback(
        PublicReleaseManifestDto manifest,
        ReleaseShelfSnapshot snapshot)
    {
        if (!snapshot.IsLegacy)
        {
            // A generation must be self-contained. Never splice mutable repo-local proof
            // bytes into an activated immutable shelf generation.
            return EnsureContractName(manifest);
        }

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

    private string ResolveRegistryManifestPath(ReleaseShelfSnapshot snapshot)
        => snapshot.IsLegacy
           && _configuration["CHUMMER_RELEASE_REGISTRY_MANIFEST_FILE"]?.Trim() is { Length: > 0 } configured
            ? configured
            : Path.Combine(snapshot.PhysicalRoot, ReleaseShelfGenerationStore.CanonicalManifestFileName);

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

    private PublicReleaseManifestDto LoadReleaseManifest(string manifestPath)
        => LoadReleaseManifestPayload(File.ReadAllText(manifestPath));

    private PublicReleaseManifestDto LoadReleaseManifestPayload(string json)
    {
        DateTimeOffset fallbackInstant = _timeProvider.GetUtcNow();
        var options = new JsonSerializerOptions(JsonSerializerDefaults.Web)
        {
            PropertyNameCaseInsensitive = true
        };

        var parsed = LoadStoredCompatibilityManifestPayload(json, options, fallbackInstant);
        if (parsed is null)
        {
            return new PublicReleaseManifestDto(
                Version: "unpublished",
                Channel: "preview",
                PublishedAt: fallbackInstant,
                Downloads: [],
                Source: "manifest",
                Status: "manifest-error",
                Message: "Release manifest exists but could not be parsed.",
                HasFallbackSource: false,
                GeneratedAt: fallbackInstant);
        }

        var status = NormalizeOptional(parsed.Status)
            ?? (parsed.Downloads.Count > 0
                ? "published"
                : string.Equals(parsed.Version, "unpublished", StringComparison.OrdinalIgnoreCase)
                    ? "unpublished"
                    : "manifest-empty");
        var message = NormalizeOptional(parsed.Message)
            ?? (parsed.Downloads.Count > 0
                ? null
                : status == "unpublished"
                    ? "No published desktop builds are available yet."
                    : "Release manifest is present but contains no downloadable artifacts.");
        return parsed with
        {
            Source = "manifest",
            Status = status,
            Message = message,
            HasFallbackSource = false
        };
    }

    private PublicReleaseManifestDto LoadRegistryReleaseManifest(string manifestPath)
        => LoadRegistryReleaseManifestPayload(File.ReadAllText(manifestPath), "registry");

    private PublicReleaseManifestDto? TryLoadRegistryReleaseManifestFromUrl(
        string manifestUrl,
        ReleaseShelfSnapshot snapshot)
    {
        try
        {
            using var client = _httpClient is null ? new HttpClient() : null;
            using var timeoutCts = new CancellationTokenSource(RegistryRuntimeManifestFetchTimeout);
            string json = (_httpClient ?? client!).GetStringAsync(manifestUrl, timeoutCts.Token).GetAwaiter().GetResult();
            if (!RuntimeRegistryManifestMatchesSnapshot(json, snapshot))
            {
                return null;
            }

            return LoadRegistryReleaseManifestPayload(FilterManifestPayload(json), "registry_runtime");
        }
        catch
        {
            return null;
        }
    }

    private static bool RuntimeRegistryManifestMatchesSnapshot(
        string json,
        ReleaseShelfSnapshot snapshot)
    {
        if (snapshot.IsLegacy)
        {
            return true;
        }

        try
        {
            using JsonDocument document = JsonDocument.Parse(json);
            JsonElement root = document.RootElement;
            string? generationId = root.TryGetProperty("generationId", out JsonElement generationIdElement)
                ? generationIdElement.GetString()
                : null;
            string? version = root.TryGetProperty("version", out JsonElement versionElement)
                ? versionElement.GetString()
                : null;
            string? channel = root.TryGetProperty("channelId", out JsonElement channelElement)
                ? channelElement.GetString()
                : root.TryGetProperty("channel", out JsonElement canonicalChannelElement)
                    ? canonicalChannelElement.GetString()
                    : null;
            DateTimeOffset? publishedAt = root.TryGetProperty("publishedAt", out JsonElement publishedAtElement)
                && publishedAtElement.ValueKind == JsonValueKind.String
                && DateTimeOffset.TryParse(
                    publishedAtElement.GetString(),
                    CultureInfo.InvariantCulture,
                    DateTimeStyles.RoundtripKind,
                    out DateTimeOffset parsedPublishedAt)
                    ? parsedPublishedAt
                    : null;
            return string.Equals(generationId, snapshot.GenerationId, StringComparison.Ordinal)
                   && string.Equals(version, snapshot.ReleaseVersion, StringComparison.Ordinal)
                   && string.Equals(channel, snapshot.Channel, StringComparison.Ordinal)
                   && publishedAt?.ToUniversalTime() == snapshot.PublishedAt?.ToUniversalTime();
        }
        catch (JsonException)
        {
            return false;
        }
    }

    private bool ShouldPreferLocalRegistryManifestInDevelopment()
    {
        string environmentName = (_configuration["ASPNETCORE_ENVIRONMENT"] ?? _configuration["DOTNET_ENVIRONMENT"] ?? string.Empty).Trim();
        return string.Equals(environmentName, "Development", StringComparison.OrdinalIgnoreCase)
               || string.Equals(environmentName, "Local", StringComparison.OrdinalIgnoreCase);
    }

    private PublicReleaseManifestDto? TryGetCachedManifest(
        string cacheKey,
        DateTimeOffset now,
        bool allowStale)
    {
        lock (_manifestCacheLock)
        {
            if (!_manifestCache.TryGetValue(cacheKey, out CachedManifestState? state)
                || state.Manifest is null)
            {
                return null;
            }

            if (now <= state.FreshUntilUtc)
            {
                return state.Manifest;
            }

            return allowStale && now <= state.StaleUntilUtc
                ? state.Manifest
                : null;
        }
    }

    private void WriteManifestCache(
        string cacheKey,
        PublicReleaseManifestDto manifest,
        DateTimeOffset now)
    {
        lock (_manifestCacheLock)
        {
            _manifestCache[cacheKey] = new CachedManifestState(
                manifest,
                now.Add(ManifestCacheFreshTtl),
                now.Add(ManifestCacheStaleTtl));

            if (_manifestCache.Count > 8)
            {
                foreach (string expiredKey in _manifestCache
                             .Where(entry => entry.Value.StaleUntilUtc < now)
                             .Select(static entry => entry.Key)
                             .ToArray())
                {
                    _manifestCache.Remove(expiredKey);
                }
            }
        }
    }

    private sealed record CachedManifestState(
        PublicReleaseManifestDto? Manifest,
        DateTimeOffset FreshUntilUtc,
        DateTimeOffset StaleUntilUtc)
    {
    }

    private PublicReleaseManifestDto LoadRegistryReleaseManifestPayload(string json, string source)
    {
        DateTimeOffset fallbackInstant = _timeProvider.GetUtcNow();
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
                PublishedAt: fallbackInstant,
                Downloads: [],
                Source: source,
                Status: "manifest-error",
                Message: "Registry release manifest exists but could not be parsed.",
                HasFallbackSource: false,
                GeneratedAt: fallbackInstant);
        }

        string projectedChannel = parsed.ChannelId ?? parsed.Channel ?? "preview";
        var downloads = (parsed.Artifacts ?? [])
            .Where(item => !string.IsNullOrWhiteSpace(item.DownloadUrl))
            .Select(item => new PublicReleaseArtifactDto(
                Id: item.ArtifactId ?? item.FileName ?? "artifact",
                Platform: item.PlatformLabel ?? item.Platform ?? "Preview build",
                Url: item.DownloadUrl ?? "",
                Sha256: item.Sha256 ?? "",
                SizeBytes: item.SizeBytes,
                Head: item.Head,
                PlatformId: item.Platform ?? InferPlatformFromRid(item.Rid) ?? "unknown",
                Rid: item.Rid,
                Arch: item.Arch,
                Kind: item.Kind,
                FileName: item.FileName,
                InstallAccessClass: item.InstallAccessClass,
                PlatformLabel: item.PlatformLabel ?? item.Platform ?? "Preview build",
                Format: InferArtifactFormat(item.FileName, item.DownloadUrl),
                Flavor: InferArtifactFlavor(item.Kind, item.FileName, item.DownloadUrl),
                ChannelId: projectedChannel,
                Channel: projectedChannel,
                Version: parsed.Version,
                ReleaseVersion: parsed.Version,
                CompatibilityState: item.CompatibilityState,
                CompatibilityReason: item.CompatibilityReason,
                ArtifactId: item.ArtifactId ?? item.FileName ?? "artifact",
                InstallerMode: item.InstallerMode,
                PayloadFileName: item.PayloadFileName,
                PayloadDownloadUrl: item.PayloadDownloadUrl,
                PayloadSha256: item.PayloadSha256,
                PayloadSizeBytes: item.PayloadSizeBytes))
            .ToList();

        var status = NormalizeOptional(parsed.Status)
            ?? (downloads.Count > 0
                ? "published"
                : "unpublished");
        var message = NormalizeOptional(parsed.Message)
            ?? (downloads.Count > 0
                ? null
                : status == "unpublished"
                    ? "No published desktop builds are available yet."
                    : "Registry release manifest is present but contains no downloadable artifacts.");

        return new PublicReleaseManifestDto(
            Version: parsed.Version ?? "unpublished",
            Channel: projectedChannel,
            PublishedAt: parsed.PublishedAt ?? fallbackInstant,
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
                : parsed.ContractName,
            PublicVersion: parsed.PublicVersion)
        {
            ProofUiLocalizationReleaseGate = parsed.ReleaseProof?.UiLocalizationReleaseGate is JsonElement uiLocalizationReleaseGate
                ? uiLocalizationReleaseGate.Clone()
                : null,
            ProofFlagshipReadiness = parsed.ReleaseProof?.FlagshipReadiness is JsonElement flagshipReadiness
                ? flagshipReadiness.Clone()
                : null,
            DesktopTupleCoverage = parsed.DesktopTupleCoverage is JsonElement desktopTupleCoverage
                ? desktopTupleCoverage.Clone()
                : null,
            RegistryBoundaryCoverage = parsed.RegistryBoundaryCoverage is JsonElement registryBoundaryCoverage
                ? registryBoundaryCoverage.Clone()
                : null,
            PublicTrustMetrics = NormalizePublicTrustMetricsElement(parsed.PublicTrustMetrics)
                is JsonElement publicTrustMetrics
                ? publicTrustMetrics
                : null,
            InstallAwareArtifactRegistry = parsed.InstallAwareArtifactRegistry is JsonElement installAwareArtifactRegistry
                ? installAwareArtifactRegistry.Clone()
                : null,
            DesktopSurfaceRefs = parsed.DesktopSurfaceRefs is JsonElement desktopSurfaceRefs
                ? desktopSurfaceRefs.Clone()
                : null,
            ArtifactIdentityRegistry = parsed.ArtifactIdentityRegistry is JsonElement artifactIdentityRegistry
                ? artifactIdentityRegistry.Clone()
                : null,
            ArtifactPublicationBindings = parsed.ArtifactPublicationBindings is JsonElement artifactPublicationBindings
                ? artifactPublicationBindings.Clone()
                : null,
            ExchangeLineageRegistry = parsed.ExchangeLineageRegistry is JsonElement exchangeLineageRegistry
                ? exchangeLineageRegistry.Clone()
                : null
        };
    }

    private static PublicReleaseManifestDto? LoadStoredCompatibilityManifestPayload(
        string json,
        JsonSerializerOptions options,
        DateTimeOffset fallbackInstant)
    {
        CompatibilityReleaseManifest? parsed = JsonSerializer.Deserialize<CompatibilityReleaseManifest>(json, options);
        if (parsed is null)
        {
            return null;
        }

        return new PublicReleaseManifestDto(
            Version: parsed.Version ?? "unpublished",
            Channel: parsed.Channel ?? parsed.ChannelId ?? "preview",
            PublishedAt: parsed.PublishedAt ?? fallbackInstant,
            Downloads: parsed.Downloads ?? [],
            Source: parsed.Source ?? "manifest",
            Status: parsed.Status ?? string.Empty,
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
                : parsed.ContractName,
            PublicVersion: parsed.PublicVersion)
        {
            ProofUiLocalizationReleaseGate = parsed.ReleaseProof?.UiLocalizationReleaseGate is JsonElement uiLocalizationReleaseGate
                ? uiLocalizationReleaseGate.Clone()
                : null,
            ProofFlagshipReadiness = parsed.ReleaseProof?.FlagshipReadiness is JsonElement flagshipReadiness
                ? flagshipReadiness.Clone()
                : null,
            DesktopTupleCoverage = parsed.DesktopTupleCoverage is JsonElement desktopTupleCoverage
                ? desktopTupleCoverage.Clone()
                : null,
            RegistryBoundaryCoverage = parsed.RegistryBoundaryCoverage is JsonElement registryBoundaryCoverage
                ? registryBoundaryCoverage.Clone()
                : null,
            PublicTrustMetrics = NormalizePublicTrustMetricsElement(parsed.PublicTrustMetrics)
                is JsonElement publicTrustMetrics
                ? publicTrustMetrics
                : null,
            InstallAwareArtifactRegistry = parsed.InstallAwareArtifactRegistry is JsonElement installAwareArtifactRegistry
                ? installAwareArtifactRegistry.Clone()
                : null,
            DesktopSurfaceRefs = parsed.DesktopSurfaceRefs is JsonElement desktopSurfaceRefs
                ? desktopSurfaceRefs.Clone()
                : null,
            ArtifactIdentityRegistry = parsed.ArtifactIdentityRegistry is JsonElement artifactIdentityRegistry
                ? artifactIdentityRegistry.Clone()
                : null,
            ArtifactPublicationBindings = parsed.ArtifactPublicationBindings is JsonElement artifactPublicationBindings
                ? artifactPublicationBindings.Clone()
                : null,
            ExchangeLineageRegistry = parsed.ExchangeLineageRegistry is JsonElement exchangeLineageRegistry
                ? exchangeLineageRegistry.Clone()
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
        DateTimeOffset evaluationInstant = _timeProvider.GetUtcNow();
        HashSet<string> disabledArtifactIds = ResolveDisabledArtifactIds();
        bool forceAccountRequiredDownloads = ForceAccountRequiredDownloads();
        bool rewriteCoverageDerivedRegistries = CanonicalManifestNeedsInstallAwareRewrite(json);
        JsonObject? manifest = JsonNode.Parse(json)?.AsObject();
        if (manifest is null)
        {
            return json;
        }

        if (disabledArtifactIds.Count == 0 && !forceAccountRequiredDownloads && !rewriteCoverageDerivedRegistries)
        {
            bool rewroteManifest = false;
            if (manifest["desktopTupleCoverage"] is JsonObject passthroughCoverage)
            {
                List<ManifestArtifactShape> remainingArtifacts = CollectManifestArtifactShapes(manifest);
                RebuildCoverageDerivedRegistries(manifest, passthroughCoverage, remainingArtifacts);
                rewroteManifest = true;
            }

            rewroteManifest |= ApplyProofFreshnessSupportabilityFloor(
                manifest,
                evaluationInstant,
                _privacyLaunchGate);
            return rewroteManifest
                ? manifest.ToJsonString(new JsonSerializerOptions(JsonSerializerDefaults.Web))
                : json;
        }

        if (disabledArtifactIds.Count > 0)
        {
            ApplyArtifactSuppressionPolicy(manifest, disabledArtifactIds);
        }

        if (disabledArtifactIds.Count == 0 && manifest["desktopTupleCoverage"] is JsonObject coverage)
        {
            List<ManifestArtifactShape> remainingArtifacts = CollectManifestArtifactShapes(manifest);
            RebuildCoverageDerivedRegistries(manifest, coverage, remainingArtifacts);
        }

        if (forceAccountRequiredDownloads)
        {
            ApplyForcedAccountRequiredDownloadPolicy(manifest);
        }

        ApplyProofFreshnessSupportabilityFloor(
            manifest,
            evaluationInstant,
            _privacyLaunchGate);
        return manifest.ToJsonString(new JsonSerializerOptions(JsonSerializerDefaults.Web));
    }

    private static bool ApplyProofFreshnessSupportabilityFloor(
        JsonObject manifest,
        DateTimeOffset evaluationInstant,
        PrivacyLaunchGateSnapshot privacyLaunchGate)
    {
        JsonObject original = manifest.DeepClone().AsObject();
        JsonObject publicTrustMetrics = manifest["publicTrustMetrics"] as JsonObject ?? [];
        JsonObject proofFreshness = publicTrustMetrics["proofFreshness"] as JsonObject ?? [];
        DateTimeOffset? publishedAt = TryGetJsonDateTimeOffset(manifest["publishedAt"]);
        ReleaseProofFreshnessEvaluation freshness = ReleaseProofFreshnessEvaluator.Evaluate(
            proofFreshness,
            manifest["releaseProof"] as JsonObject,
            publishedAt,
            evaluationInstant);

        manifest["publicTrustMetrics"] = publicTrustMetrics;
        publicTrustMetrics["proofFreshness"] = proofFreshness;
        proofFreshness["status"] = freshness.MaterializedStatus;
        publicTrustMetrics["privacyReadiness"] = privacyLaunchGate.ToJsonObject();
        if (freshness.IsFresh && !privacyLaunchGate.BlocksReleaseSupportability)
        {
            return !JsonNode.DeepEquals(original, manifest);
        }

        const string reviewRolloutState = "public_release_review_required";
        string readinessBlocker = ReleaseReadinessBlockerClause(
            freshness.IsFresh,
            privacyLaunchGate);
        string reviewRolloutReason =
            $"Current shelf is published, but release posture stays review-required because {readinessBlocker}.";
        string reviewSupportabilitySummary =
            $"Treat the current release as review-required because {readinessBlocker}.";
        string reviewKnownIssueSummary = $"Known issue: {readinessBlocker}.";
        string reviewFixAvailabilitySummary =
            "Only send fixed notices after current launch-readiness blockers are cleared and the affected install "
            + "can receive the published channel artifact now on the release page.";

        string publicationStatus = NormalizeToken(GetJsonString(manifest["status"]));
        string existingRolloutState = NormalizeStateToken(GetJsonString(manifest["rolloutState"]));
        string effectiveRolloutState = ResolveNonFreshRolloutState(
            publicationStatus,
            existingRolloutState,
            reviewRolloutState);
        bool strongerRolloutState = IsStrongerThanProofReview(effectiveRolloutState);

        manifest["rolloutState"] = effectiveRolloutState;
        manifest["rolloutReason"] = PreserveOrReplaceNarrative(
            GetJsonString(manifest["rolloutReason"]),
            reviewRolloutReason,
            strongerRolloutState);

        string existingSupportabilityState = NormalizeStateToken(GetJsonString(manifest["supportabilityState"]));
        manifest["supportabilityState"] = ResolveNonFreshSupportabilityState(
            publicationStatus,
            effectiveRolloutState,
            existingSupportabilityState);
        manifest["supportabilitySummary"] = PreserveOrReplaceNarrative(
            GetJsonString(manifest["supportabilitySummary"]),
            reviewSupportabilitySummary,
            strongerRolloutState);
        manifest["knownIssueSummary"] = PreserveOrReplaceNarrative(
            GetJsonString(manifest["knownIssueSummary"]),
            reviewKnownIssueSummary,
            strongerRolloutState);
        manifest["fixAvailabilitySummary"] = PreserveOrReplaceNarrative(
            GetJsonString(manifest["fixAvailabilitySummary"]),
            reviewFixAvailabilitySummary,
            strongerRolloutState);

        JsonObject publicReleaseChannel = publicTrustMetrics["releaseChannel"] as JsonObject ?? [];
        publicTrustMetrics["releaseChannel"] = publicReleaseChannel;
        ApplyProofFreshnessReleaseChannelFloor(
            publicReleaseChannel,
            publicationStatus,
            effectiveRolloutState,
            "posture",
            $"Release channel remains review-required because {readinessBlocker}.");

        JsonObject registryBoundaryCoverage = manifest["registryBoundaryCoverage"] as JsonObject ?? [];
        manifest["registryBoundaryCoverage"] = registryBoundaryCoverage;
        JsonObject registryReleaseChannel = registryBoundaryCoverage["releaseChannel"] as JsonObject ?? [];
        registryBoundaryCoverage["releaseChannel"] = registryReleaseChannel;
        ApplyProofFreshnessReleaseChannelFloor(
            registryReleaseChannel,
            publicationStatus,
            effectiveRolloutState,
            "publicTrustPosture",
            $"Release-channel truth remains review-required because {readinessBlocker}.");

        return !JsonNode.DeepEquals(original, manifest);
    }

    private static string ReleaseReadinessBlockerClause(
        bool proofFresh,
        PrivacyLaunchGateSnapshot privacyLaunchGate)
        => (proofFresh, privacyLaunchGate.BlocksReleaseSupportability) switch
        {
            (false, true) => "stale or incomplete proof receipts and Hosted Build privacy, retention, recovery, and erasure review still block launch-readiness claims",
            (false, false) => "stale or incomplete proof receipts still block launch-readiness claims",
            (true, true) => "Hosted Build privacy, retention, recovery, and erasure review still blocks launch-readiness claims",
            _ => "launch-readiness review remains incomplete",
        };

    private static void ApplyProofFreshnessReleaseChannelFloor(
        JsonObject releaseChannel,
        string publicationStatus,
        string topLevelRolloutState,
        string publicTrustPosturePropertyName,
        string reviewSummary)
    {
        string existingRolloutState = NormalizeStateToken(GetJsonString(releaseChannel["rolloutState"]));
        string effectiveRolloutState = ResolveNonFreshRolloutState(
            publicationStatus,
            existingRolloutState,
            topLevelRolloutState);
        bool strongerRolloutState = IsStrongerThanProofReview(effectiveRolloutState);
        releaseChannel["rolloutState"] = effectiveRolloutState;
        releaseChannel["supportabilityState"] = ResolveNonFreshSupportabilityState(
            publicationStatus,
            effectiveRolloutState,
            NormalizeStateToken(GetJsonString(releaseChannel["supportabilityState"])));
        releaseChannel[publicTrustPosturePropertyName] = ResolveNonFreshPublicTrustPosture(
            publicationStatus,
            effectiveRolloutState,
            NormalizeStateToken(GetJsonString(releaseChannel[publicTrustPosturePropertyName])));
        releaseChannel["summary"] = PreserveOrReplaceNarrative(
            GetJsonString(releaseChannel["summary"]),
            reviewSummary,
            strongerRolloutState);
    }

    private static string ResolveNonFreshPublicTrustPosture(
        string publicationStatus,
        string effectiveRolloutState,
        string currentPublicTrustPosture)
        => string.Equals(publicationStatus, "revoked", StringComparison.Ordinal)
            || string.Equals(effectiveRolloutState, "revoked", StringComparison.Ordinal)
            || string.Equals(currentPublicTrustPosture, "revoked", StringComparison.Ordinal)
            ? "revoked"
            : "blocked";

    private static string ResolveNonFreshRolloutState(
        string publicationStatus,
        string currentRolloutState,
        string fallbackReviewState)
    {
        string terminalPublicationState = TerminalPublicationState(publicationStatus);
        if (!string.IsNullOrWhiteSpace(terminalPublicationState))
        {
            return IsTerminalOrUnknownRolloutState(currentRolloutState)
                ? currentRolloutState
                : terminalPublicationState;
        }

        return IsNonOptimisticState(currentRolloutState)
            ? currentRolloutState
            : fallbackReviewState;
    }

    private static string ResolveNonFreshSupportabilityState(
        string publicationStatus,
        string effectiveRolloutState,
        string currentSupportabilityState)
    {
        string terminalPublicationState = TerminalPublicationState(publicationStatus);
        if (!string.IsNullOrWhiteSpace(terminalPublicationState))
        {
            return IsTerminalOrUnknownSupportabilityState(currentSupportabilityState)
                ? currentSupportabilityState
                : terminalPublicationState;
        }

        if (IsNonOptimisticSupportabilityState(currentSupportabilityState))
        {
            return currentSupportabilityState;
        }

        return IsTerminalOrUnknownRolloutState(effectiveRolloutState)
            ? effectiveRolloutState
            : "review_required";
    }

    private static string PreserveOrReplaceNarrative(
        string? current,
        string reviewNarrative,
        bool preserveStrongerBlockerNarrative)
        => preserveStrongerBlockerNarrative
           && !string.IsNullOrWhiteSpace(current)
           && !NarrativeMakesOptimisticSupportClaim(current)
            ? current.Trim()
            : reviewNarrative;

    private static bool NarrativeMakesOptimisticSupportClaim(string value)
    {
        string normalized = value.Trim().ToLowerInvariant();
        return normalized.Contains("supported", StringComparison.Ordinal)
            || normalized.Contains("passed the local release", StringComparison.Ordinal)
            || normalized.Contains("available now", StringComparison.Ordinal)
            || normalized.Contains("release status is green", StringComparison.Ordinal)
            || normalized.Contains("no blocking release caveat", StringComparison.Ordinal)
            || normalized.Contains("ready for launch", StringComparison.Ordinal);
    }

    private static string TerminalPublicationState(string publicationStatus)
        => NormalizeStateToken(publicationStatus) switch
        {
            "revoked" => "revoked",
            "unpublished" or "draft" or "manifest_empty" or "manifest_error" => "unpublished",
            "disabled" => "disabled",
            "blocked" => "blocked",
            "quarantined" => "quarantined",
            "security_hold" => "security_hold",
            _ => string.Empty
        };

    private static bool IsNonOptimisticState(string state)
        => !string.IsNullOrWhiteSpace(state) && !IsOptimisticRolloutState(state);

    private static bool IsNonOptimisticSupportabilityState(string state)
        => !string.IsNullOrWhiteSpace(state)
            && state is not "gold_supported"
            && state is not "preview_supported"
            && state is not "supported";

    private static bool IsTerminalOrUnknownSupportabilityState(string state)
        => IsNonOptimisticSupportabilityState(state)
            && state is not "review_required"
            and not "limited";

    private static bool IsOptimisticRolloutState(string state)
        => state is "public_stable"
            or "stable"
            or "docker"
            or "promoted_preview"
            or "preview"
            or "published"
            or "live";

    private static bool IsStrongerThanProofReview(string rolloutState)
        => !string.IsNullOrWhiteSpace(rolloutState)
            && rolloutState is not "public_release_review_required"
            and not "release_review_required"
            and not "review_required"
            && !IsOptimisticRolloutState(rolloutState);

    private static bool IsTerminalOrUnknownRolloutState(string rolloutState)
        => IsStrongerThanProofReview(rolloutState)
            && rolloutState is not "coverage_incomplete"
            and not "desktop_polish_needed";

    private static string NormalizeStateToken(string? value)
        => NormalizeToken(value).Replace('-', '_');

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
            rolloutReason = $"The current release is published, but a few desktop combinations are still catching up: {coverageSummary}.";
            supportabilityState = "review_required";
            supportabilitySummary = $"This release is live. Some desktop combinations are still catching up: {coverageSummary}.";
            knownIssueSummary = "A few desktop downloads stay hidden until those combinations are current again.";
            fixAvailabilitySummary = "Check the live download page again after the updated build lands.";
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

    private PublicReleaseManifestDto ApplyFlagshipReadinessGuard(PublicReleaseManifestDto manifest)
    {
        if (ShouldPreserveCurrentGoldSupportability(manifest))
        {
            return EnsureContractName(manifest);
        }

        FlagshipReadinessSnapshot? readiness = _flagshipReadiness.LoadSnapshot();
        if (readiness is null || !readiness.MissingDesktopClientCoverage)
        {
            return EnsureContractName(manifest);
        }

        string gapSummary = readiness.DesktopClientGapSummary.Trim().TrimEnd('.');
        bool published = string.Equals(NormalizeOptional(manifest.Status), "published", StringComparison.OrdinalIgnoreCase);
        bool preserveBlockingRollout = HasBlockingRolloutState(manifest.RolloutState)
            && !HasOnlyProofFreshnessRolloutBlocker(manifest);
        string? rolloutState = published && !preserveBlockingRollout
            ? "desktop_polish_needed"
            : manifest.RolloutState;
        bool preserveRolloutReason = preserveBlockingRollout;
        bool preserveReviewContext = string.Equals(NormalizeOptional(manifest.SupportabilityState), "review_required", StringComparison.OrdinalIgnoreCase);
        return EnsureContractName(manifest with
        {
            RolloutState = rolloutState,
            RolloutReason = preserveRolloutReason
                ? AppendDistinctSentence(
                    manifest.RolloutReason,
                    $"The current release stays install-capable, but parity claims remain blocked because {gapSummary}.")
                : $"The current release stays install-capable, but parity claims remain blocked because {gapSummary}.",
            SupportabilityState = "review_required",
            SupportabilitySummary = preserveReviewContext
                ? AppendDistinctSentence(
                    manifest.SupportabilitySummary,
                    $"Treat the current release as limited because {gapSummary}.")
                : $"Treat the current release as limited because {gapSummary}.",
            KnownIssueSummary = preserveReviewContext
                ? AppendDistinctSentence(
                    manifest.KnownIssueSummary,
                    "Desktop polish is not current yet, so parity-sensitive routes stay with support.")
                : "Desktop polish is not current yet, so parity-sensitive routes stay with support.",
            FixAvailabilitySummary = preserveReviewContext
                ? AppendDistinctSentence(
                    manifest.FixAvailabilitySummary,
                    "Use linked-install recovery and Chummer support until the desktop experience is ready again.")
                : "Use linked-install recovery and Chummer support until the desktop experience is ready again."
        });
    }

    private PublicReleaseManifestDto ApplyGoldReadinessGuard(PublicReleaseManifestDto manifest)
    {
        if (ShouldPreserveCurrentGoldSupportability(manifest))
        {
            return EnsureContractName(manifest);
        }

        GoldReadinessSnapshot? readiness = _goldReadiness.LoadSnapshot();
        if (readiness is null || readiness.IsGoldReady)
        {
            return EnsureContractName(manifest);
        }

        string gapSummary = BuildGoldReadinessGapSummary(readiness).Trim().TrimEnd('.');
        bool published = string.Equals(NormalizeOptional(manifest.Status), "published", StringComparison.OrdinalIgnoreCase);
        bool preserveBlockingRollout = HasBlockingRolloutState(manifest.RolloutState)
            && !HasOnlyProofFreshnessRolloutBlocker(manifest);
        string? rolloutState = published && !preserveBlockingRollout
            ? "release_review_required"
            : manifest.RolloutState;
        bool preserveRolloutReason = preserveBlockingRollout;
        bool preserveReviewContext = string.Equals(NormalizeOptional(manifest.SupportabilityState), "review_required", StringComparison.OrdinalIgnoreCase);
        return EnsureContractName(manifest with
        {
            RolloutState = rolloutState,
            RolloutReason = preserveRolloutReason
                ? AppendDistinctSentence(
                    manifest.RolloutReason,
                    $"The current release remains available, but flagship readiness claims stay blocked because {gapSummary}.")
                : $"The current release remains available, but flagship readiness claims stay blocked because {gapSummary}.",
            SupportabilityState = "review_required",
            SupportabilitySummary = preserveReviewContext
                ? AppendDistinctSentence(
                    manifest.SupportabilitySummary,
                    $"Treat the current release as limited because {gapSummary}.")
                : $"Treat the current release as limited because {gapSummary}.",
            KnownIssueSummary = preserveReviewContext
                ? AppendDistinctSentence(
                    manifest.KnownIssueSummary,
                    "Final release checks are not current yet, so launch-sensitive claims stay review-required.")
                : "Final release checks are not current yet, so launch-sensitive claims stay review-required.",
            FixAvailabilitySummary = preserveReviewContext
                ? AppendDistinctSentence(
                    manifest.FixAvailabilitySummary,
                    "Use linked-install recovery and Chummer support until final release checks pass.")
                : "Use linked-install recovery and Chummer support until final release checks pass."
        });
    }

    private static string BuildGoldReadinessGapSummary(GoldReadinessSnapshot readiness)
        => readiness.PublicGapSummary;

    private PublicReleaseManifestDto ApplyImportRouteParityGuard(PublicReleaseManifestDto manifest)
    {
        if (ShouldPreserveCurrentGoldSupportability(manifest))
        {
            return EnsureContractName(manifest);
        }

        ImportRouteParityProofGuardSnapshot importRouteGuard = _importRouteParityProofGuard.Evaluate();
        if (importRouteGuard.IsCurrent || string.IsNullOrWhiteSpace(importRouteGuard.ReviewRequiredReason))
        {
            return EnsureContractName(manifest);
        }

        string gapSummary = importRouteGuard.ReviewRequiredReason!.Trim().TrimEnd('.');
        return EnsureContractName(manifest with
        {
            SupportabilityState = "review_required",
            SupportabilitySummary = AppendDistinctSentence(
                manifest.SupportabilitySummary,
                $"Treat the current release as limited because {gapSummary}."),
            KnownIssueSummary = AppendDistinctSentence(
                manifest.KnownIssueSummary,
                "Translator, XML amendment, Hero Lab, and adjacent import parity receipts are not current yet, so parity-sensitive routes stay with support."),
            FixAvailabilitySummary = AppendDistinctSentence(
                manifest.FixAvailabilitySummary,
                "Use linked-install recovery and Chummer support until translator, XML, Hero Lab, and import paths are current.")
        });
    }

    private bool ShouldPreserveCurrentGoldSupportability(PublicReleaseManifestDto manifest)
    {
        if (!string.Equals(NormalizeOptional(manifest.SupportabilityState), "gold_supported", StringComparison.OrdinalIgnoreCase))
        {
            return false;
        }

        FlagshipReadinessSnapshot? readiness = _flagshipReadiness.LoadSnapshot();
        GoldReadinessSnapshot? goldReadiness = _goldReadiness.LoadSnapshot();
        if (goldReadiness is not null && !goldReadiness.IsGoldReady)
        {
            return readiness is not null
                && readiness.IsFinalGoldClosureOnlyBlocked
                && goldReadiness.IsClosureReceiptCycleOnlyBlocked;
        }

        if (readiness is not null
            && string.Equals(NormalizeOptional(readiness.Status), "pass", StringComparison.OrdinalIgnoreCase)
            && !readiness.MissingDesktopClientCoverage)
        {
            return true;
        }

        if (readiness is not null
            && goldReadiness is not null
            && readiness.IsFinalGoldClosureOnlyBlocked
            && goldReadiness.IsClosureReceiptCycleOnlyBlocked)
        {
            return true;
        }

        string? normalizedProofStatus = NormalizeOptional(manifest.ProofStatus);
        bool canonicalProofPassed = !string.IsNullOrWhiteSpace(normalizedProofStatus)
            && (normalizedProofStatus.Contains("pass", StringComparison.OrdinalIgnoreCase)
                || string.Equals(normalizedProofStatus, "ready", StringComparison.OrdinalIgnoreCase));

        return canonicalProofPassed && manifest.ProofRoutes is { Count: > 0 };
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
            RebuildCoverageDerivedRegistries(manifest, coverage, remainingArtifacts);
            if (string.Equals(NormalizeToken(GetJsonString(manifest["status"])), "published", StringComparison.Ordinal))
            {
                bool coverageComplete = CoverageIsComplete(coverage);
                if (!coverageComplete)
                {
                    string coverageSummary = DesktopTupleCoverageGapSummary(JsonSerializer.SerializeToElement(coverage, new JsonSerializerOptions(JsonSerializerDefaults.Web)));
                    manifest["rolloutState"] = "coverage_incomplete";
                    manifest["rolloutReason"] = $"The current release is published, but a few desktop combinations are still catching up: {coverageSummary}.";
                    manifest["supportabilityState"] = "review_required";
                    manifest["supportabilitySummary"] = $"This release is live. Some desktop combinations are still catching up: {coverageSummary}.";
                    manifest["knownIssueSummary"] = "A few desktop downloads stay hidden until those combinations are current again.";
                    manifest["fixAvailabilitySummary"] = "Check the live download page again after the updated build lands.";
                }
            }
        }
    }

    private void ApplyForcedAccountRequiredDownloadPolicy(JsonObject manifest)
    {
        ApplyForcedAccountRequiredDownloadPolicy(manifest["artifacts"]);
        ApplyForcedAccountRequiredDownloadPolicy(manifest["downloads"]);
        ApplyForcedAccountRequiredDesktopSurfacePolicy(manifest["desktopSurfaceRefs"], manifest["artifacts"]);
        ApplyForcedAccountRequiredPublicTrustMetricsPolicy(manifest["publicTrustMetrics"], manifest["desktopTupleCoverage"], manifest["artifacts"]);
        ApplyForcedAccountRequiredRegistryBoundaryCoveragePolicy(manifest["registryBoundaryCoverage"], manifest["desktopSurfaceRefs"]);
    }

    private static void ApplyForcedAccountRequiredDownloadPolicy(JsonNode? node)
    {
        if (node is not JsonArray rows)
        {
            return;
        }

        foreach (JsonNode? rowNode in rows)
        {
            if (rowNode is not JsonObject row)
            {
                continue;
            }

            row["installAccessClass"] = InstallAccessClasses.AccountRequired;
        }
    }

    private static void ApplyForcedAccountRequiredDesktopSurfacePolicy(JsonNode? node, JsonNode? artifactsNode)
    {
        if (node is not JsonArray rows)
        {
            return;
        }

        HashSet<string> accountRequiredArtifactIds = new(StringComparer.OrdinalIgnoreCase);
        if (artifactsNode is JsonArray artifacts)
        {
            foreach (JsonNode? artifactNode in artifacts)
            {
                if (artifactNode is not JsonObject artifact)
                {
                    continue;
                }

                string? artifactId = GetJsonString(artifact["artifactId"]) ?? GetJsonString(artifact["id"]);
                if (string.IsNullOrWhiteSpace(artifactId))
                {
                    continue;
                }

                if (string.Equals(GetJsonString(artifact["installAccessClass"]), InstallAccessClasses.AccountRequired, StringComparison.OrdinalIgnoreCase))
                {
                    accountRequiredArtifactIds.Add(artifactId);
                }
            }
        }

        foreach (JsonNode? rowNode in rows)
        {
            if (rowNode is not JsonObject row)
            {
                continue;
            }

            string? artifactId = GetJsonString(row["artifactId"]);
            if (string.IsNullOrWhiteSpace(artifactId) || !accountRequiredArtifactIds.Contains(artifactId))
            {
                continue;
            }

            row["installAccessClass"] = InstallAccessClasses.AccountRequired;

            string rationale = GetJsonString(row["rationale"]) ?? string.Empty;
            if (string.IsNullOrWhiteSpace(rationale))
            {
                continue;
            }

            rationale = rationale
                .Replace("guest-readable", "entitlement-backed", StringComparison.OrdinalIgnoreCase)
                .Replace("available as a public download", "available as a linked download", StringComparison.OrdinalIgnoreCase)
                .Replace("retained as a public download", "retained as a linked download", StringComparison.OrdinalIgnoreCase)
                .Replace("listed as a public download", "listed as a linked download", StringComparison.OrdinalIgnoreCase)
                .Replace("visible as a public download", "visible as a linked download", StringComparison.OrdinalIgnoreCase);

            row["rationale"] = rationale;
        }
    }

    private static void ApplyForcedAccountRequiredPublicTrustMetricsPolicy(JsonNode? metricsNode, JsonNode? coverageNode, JsonNode? artifactsNode)
    {
        if (metricsNode is not JsonObject metrics || coverageNode is not JsonObject coverage)
        {
            return;
        }

        if (metrics["adoptionHealth"] is not JsonObject adoptionHealth || coverage["desktopRouteTruth"] is not JsonArray routeTruth)
        {
            return;
        }

        Dictionary<string, string> installAccessByArtifactId = new(StringComparer.OrdinalIgnoreCase);
        if (artifactsNode is JsonArray artifacts)
        {
            foreach (JsonNode? artifactNode in artifacts)
            {
                if (artifactNode is not JsonObject artifact)
                {
                    continue;
                }

                string? artifactId = GetJsonString(artifact["artifactId"]) ?? GetJsonString(artifact["id"]);
                string? installAccessClass = GetJsonString(artifact["installAccessClass"]);
                if (string.IsNullOrWhiteSpace(artifactId) || string.IsNullOrWhiteSpace(installAccessClass))
                {
                    continue;
                }

                installAccessByArtifactId[artifactId] = installAccessClass;
            }
        }

        int publicInstallCount = 0;
        int accountLinkedInstallCount = 0;

        foreach (JsonNode? routeNode in routeTruth)
        {
            if (routeNode is not JsonObject route)
            {
                continue;
            }

            if (!string.Equals(GetJsonString(route["routeRole"]), "primary", StringComparison.OrdinalIgnoreCase) ||
                !string.Equals(GetJsonString(route["promotionState"]), "promoted", StringComparison.OrdinalIgnoreCase) ||
                string.Equals(GetJsonString(route["revokeState"]), "revoked", StringComparison.OrdinalIgnoreCase))
            {
                continue;
            }

            string? artifactId = GetJsonString(route["artifactId"]);
            if (string.IsNullOrWhiteSpace(artifactId) || !installAccessByArtifactId.TryGetValue(artifactId, out string? installAccessClass))
            {
                publicInstallCount++;
                continue;
            }

            if (string.Equals(installAccessClass, InstallAccessClasses.AccountRequired, StringComparison.OrdinalIgnoreCase))
            {
                accountLinkedInstallCount++;
            }
            else
            {
                publicInstallCount++;
            }
        }

        adoptionHealth["publicInstallCount"] = publicInstallCount;
        adoptionHealth["accountLinkedInstallCount"] = accountLinkedInstallCount;
        adoptionHealth["summary"] =
            $"{GetJsonInt32(adoptionHealth["primaryPromotedCount"])} primary routes are promoted; " +
            $"{publicInstallCount} are direct downloads, " +
            $"{accountLinkedInstallCount} can start with sign-in and support attached, " +
            $"{GetJsonInt32(adoptionHealth["fallbackRecoveryCount"])} fallback recovery routes are promoted, " +
            $"and {GetJsonInt32(adoptionHealth["blockedRouteCount"])} routes are still blocked.";
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

        if (int.TryParse(GetJsonString(node), out value))
        {
            return value;
        }

        return 0;
    }

    private static void ApplyForcedAccountRequiredRegistryBoundaryCoveragePolicy(JsonNode? coverageNode, JsonNode? desktopSurfaceRefsNode)
    {
        if (coverageNode is not JsonObject coverage ||
            coverage["entitlement"] is not JsonObject entitlement ||
            desktopSurfaceRefsNode is not JsonArray desktopSurfaceRefs)
        {
            return;
        }

        int desktopSurfaceRefCount = 0;
        int openPublicSurfaceCount = 0;
        int accountRequiredSurfaceCount = 0;

        foreach (JsonNode? rowNode in desktopSurfaceRefs)
        {
            if (rowNode is not JsonObject row)
            {
                continue;
            }

            desktopSurfaceRefCount++;
            string? installAccessClass = GetJsonString(row["installAccessClass"]);
            if (string.Equals(installAccessClass, InstallAccessClasses.AccountRequired, StringComparison.OrdinalIgnoreCase))
            {
                accountRequiredSurfaceCount++;
            }
            else
            {
                openPublicSurfaceCount++;
            }
        }

        entitlement["desktopSurfaceRefCount"] = desktopSurfaceRefCount;
        entitlement["openPublicSurfaceCount"] = openPublicSurfaceCount;
        entitlement["accountRequiredSurfaceCount"] = accountRequiredSurfaceCount;
        entitlement["summary"] =
            $"Entitlement and install-hand-off truth spans {GetJsonInt32(entitlement["installAwareArtifactCount"])} install-aware registry rows, " +
            $"{desktopSurfaceRefCount} desktop surface refs, " +
            $"{openPublicSurfaceCount} open-public surfaces, and " +
            $"{accountRequiredSurfaceCount} account-required surfaces.";
    }

    private HashSet<string> ResolveDisabledArtifactIds()
    {
        HashSet<string> values = new(StringComparer.OrdinalIgnoreCase);
        AddDisabledArtifacts(values, _configuration[PublicDisabledArtifactIdsKey]);
        AddDisabledArtifacts(values, _configuration[ReleaseDisabledArtifactIdsKey]);
        return values;
    }

    private bool ForceAccountRequiredDownloads()
        => ParseBooleanSetting(_configuration[ForceAccountRequiredDownloadsKey]);

    private static bool ParseBooleanSetting(string? value)
        => value?.Trim().ToLowerInvariant() switch
        {
            "1" or "true" or "yes" or "on" => true,
            _ => false
        };

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
        List<string> requiredPlatforms = [.. RequiredDesktopPlatforms];
        List<string> requiredHeads = [.. RequiredDesktopHeads];

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

        List<string> sourceRequiredTupleIds = ToJsonStringList(coverage["requiredDesktopPlatformHeadRidTuples"])
            .Where(tupleId =>
            {
                string[] parts = tupleId.Split(':', 3, StringSplitOptions.TrimEntries | StringSplitOptions.RemoveEmptyEntries);
                return parts.Length == 3
                    && requiredHeads.Contains(parts[0], StringComparer.OrdinalIgnoreCase)
                    && requiredPlatforms.Contains(parts[2], StringComparer.OrdinalIgnoreCase)
                    && RidToPlatformArch.TryGetValue(parts[1], out (string Platform, string Arch) mapping)
                    && string.Equals(mapping.Platform, parts[2], StringComparison.OrdinalIgnoreCase);
            })
            .ToList();
        List<string> requiredTupleIds = BuildRequiredDesktopTupleIds(
                requiredPlatforms,
                requiredHeads,
                promotedPlatformHeadRidTuples)
            .Concat(sourceRequiredTupleIds)
            .OrderBy(static value => value, StringComparer.Ordinal)
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .ToList();

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

    private static JsonArray BuildInstallAwareArtifactRegistry(
        IReadOnlyList<ManifestArtifactShape> artifacts,
        JsonObject coverage,
        string channelId,
        string releaseVersion)
    {
        if (coverage["desktopRouteTruth"] is not JsonArray desktopRouteTruth)
        {
            return [];
        }

        Dictionary<string, ManifestArtifactShape> artifactById = artifacts
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

            if (!artifactById.ContainsKey(NormalizeToken(artifactId)))
            {
                continue;
            }

            string head = NormalizeToken(GetJsonString(routeRow["head"]));
            string platform = NormalizePlatformToken(GetJsonString(routeRow["platform"]));
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
            string kind = InstallAwareArtifactKind(artifactById, artifactId, routeRow);
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
            rows.OrderBy(static row => NormalizePlatformToken(GetJsonString(row["platform"])), StringComparer.Ordinal)
                .ThenBy(static row => NormalizeToken(GetJsonString(row["head"])), StringComparer.Ordinal)
                .ThenBy(static row => NormalizeToken(GetJsonString(row["rid"])), StringComparer.Ordinal)
                .ThenBy(static row => NormalizeToken(GetJsonString(row["artifactId"])), StringComparer.Ordinal)
                .Select(static row => (JsonNode)row)
                .ToArray());
    }

    private static JsonArray BuildDesktopSurfaceRefs(
        IReadOnlyList<ManifestArtifactShape> artifacts,
        JsonObject coverage,
        string channelId,
        string releaseVersion)
    {
        if (coverage["desktopRouteTruth"] is not JsonArray desktopRouteTruth)
        {
            return [];
        }

        Dictionary<string, ManifestArtifactShape> artifactById = artifacts
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

            if (!artifactById.ContainsKey(NormalizeToken(artifactId)))
            {
                continue;
            }

            string head = NormalizeToken(GetJsonString(routeRow["head"]));
            string platform = NormalizePlatformToken(GetJsonString(routeRow["platform"]));
            string rid = NormalizeToken(GetJsonString(routeRow["rid"]));
            string arch = NormalizeToken(GetJsonString(routeRow["arch"]));
            if (string.IsNullOrWhiteSpace(arch)
                && RidToPlatformArch.TryGetValue(rid, out (string Platform, string Arch) platformArch))
            {
                arch = platformArch.Arch;
            }

            string kind = InstallAwareArtifactKind(artifactById, artifactId, routeRow);
            string installAccessClass = DesktopSurfaceInstallAccessClass(artifactById, artifactId, platform, kind);
            string publicationBindingId = ArtifactPublicationBindingId(channelId, releaseVersion, routeRow);
            string? publicInstallRoute = (GetJsonString(routeRow["publicInstallRoute"]) ?? string.Empty).Trim();

            JsonObject row = new()
            {
                ["registryId"] = DesktopSurfaceRegistryId(channelId, releaseVersion, routeRow),
                ["artifactId"] = artifactId,
                ["channelId"] = channelId,
                ["releaseVersion"] = releaseVersion,
                ["tupleId"] = (GetJsonString(routeRow["tupleId"]) ?? string.Empty).Trim(),
                ["head"] = head,
                ["platform"] = platform,
                ["rid"] = rid,
                ["arch"] = arch,
                ["kind"] = kind,
                ["installAccessClass"] = installAccessClass,
                ["desktopChannelRef"] = DesktopSurfaceDesktopChannelRef(channelId, releaseVersion, routeRow),
                ["installGuidanceRef"] = DesktopSurfaceInstallGuidanceRef(channelId, releaseVersion, artifactId),
                ["participationReceiptRef"] = DesktopSurfaceParticipationReceiptRef(channelId, releaseVersion, routeRow),
                ["rewardPublicationRef"] = DesktopSurfaceRewardPublicationRef(publicationBindingId),
                ["publicationBindingId"] = publicationBindingId,
                ["rationale"] = DesktopSurfaceRationale(routeRow, channelId, installAccessClass),
            };
            row["publicInstallRoute"] = string.IsNullOrWhiteSpace(publicInstallRoute) ? null : publicInstallRoute;
            rows.Add(row);
        }

        return new JsonArray(
            rows.OrderBy(static row => NormalizePlatformToken(GetJsonString(row["platform"])), StringComparer.Ordinal)
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
        IReadOnlyDictionary<string, ManifestArtifactShape> artifactById,
        string artifactId,
        JsonObject routeRow)
    {
        if (artifactById.TryGetValue(NormalizeToken(artifactId), out ManifestArtifactShape? artifact))
        {
            string normalizedKind = NormalizeToken(artifact.Kind);
            if (!string.IsNullOrWhiteSpace(normalizedKind))
            {
                return normalizedKind;
            }
        }

        string routeKind = NormalizeToken(GetJsonString(routeRow["kind"]));
        return string.IsNullOrWhiteSpace(routeKind) ? "installer" : routeKind;
    }

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

        return $"Published {channelId} channel keeps {routeRole}-route {tupleId} blocked for installed build selector {installedBuildSelector} until installer and startup status are present.";
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

    private static string DesktopSurfaceInstallAccessClass(
        IReadOnlyDictionary<string, ManifestArtifactShape> artifactById,
        string artifactId,
        string platform,
        string kind)
    {
        if (artifactById.TryGetValue(NormalizeToken(artifactId), out ManifestArtifactShape? artifact))
        {
            string explicitAccessClass = NormalizeToken(artifact.InstallAccessClass);
            if (!string.IsNullOrWhiteSpace(explicitAccessClass))
            {
                return explicitAccessClass;
            }
        }

        bool accountRequiredPlatform = platform is "macos";
        bool accountRequiredKind = kind switch
        {
            _ => kind is "installer" or "dmg" or "pkg" or "msix"
        };
        return accountRequiredPlatform && accountRequiredKind
            ? InstallAccessClasses.AccountRequired
            : InstallAccessClasses.OpenPublic;
    }

    private static string DesktopSurfaceRegistryId(string channelId, string releaseVersion, JsonObject routeRow)
        => $"desktop-surface:{channelId}:{releaseVersion}:{(GetJsonString(routeRow["tupleId"]) ?? string.Empty).Trim()}";

    private static string DesktopSurfaceDesktopChannelRef(string channelId, string releaseVersion, JsonObject routeRow)
        => $"desktop-channel:{channelId}:{releaseVersion}:{(GetJsonString(routeRow["tupleId"]) ?? string.Empty).Trim()}";

    private static string DesktopSurfaceInstallGuidanceRef(string channelId, string releaseVersion, string artifactId)
        => $"install-guidance:{channelId}:{releaseVersion}:{artifactId}";

    private static string DesktopSurfaceParticipationReceiptRef(string channelId, string releaseVersion, JsonObject routeRow)
        => $"participation-receipt:{channelId}:{releaseVersion}:{(GetJsonString(routeRow["tupleId"]) ?? string.Empty).Trim()}";

    private static string DesktopSurfaceRewardPublicationRef(string publicationBindingId)
        => $"reward-publication:{publicationBindingId}";

    private static string ArtifactPublicationBindingId(string channelId, string releaseVersion, JsonObject routeRow)
        => $"binding:{channelId}:{releaseVersion}:{(GetJsonString(routeRow["tupleId"]) ?? string.Empty).Trim()}";

    private static string ArtifactPublicationState(JsonObject routeRow)
    {
        string explicitState = NormalizeToken(GetJsonString(routeRow["publicationState"]) ?? GetJsonString(routeRow["publication_state"]));
        if (explicitState is "preview" or "published" or "revoked" or "retained")
        {
            return explicitState;
        }

        string promotionState = NormalizeToken(GetJsonString(routeRow["promotionState"]));
        string revokeState = NormalizeToken(GetJsonString(routeRow["revokeState"]));
        string routeRole = NormalizeToken(GetJsonString(routeRow["routeRole"]));
        if (string.Equals(revokeState, "revoked", StringComparison.Ordinal))
        {
            return "revoked";
        }

        if (string.Equals(promotionState, "promoted", StringComparison.Ordinal))
        {
            return "published";
        }

        return string.Equals(routeRole, "fallback", StringComparison.Ordinal)
            ? "retained"
            : "preview";
    }

    private static string DesktopSurfaceRationale(JsonObject routeRow, string channelId, string installAccessClass)
    {
        string tupleId = (GetJsonString(routeRow["tupleId"]) ?? string.Empty).Trim();
        string routeRole = NormalizeToken(GetJsonString(routeRow["routeRole"]));
        string publicationState = ArtifactPublicationState(routeRow);
        string installPosture = string.Equals(installAccessClass, InstallAccessClasses.AccountRequired, StringComparison.OrdinalIgnoreCase)
            ? "entitlement-backed"
            : "guest-readable";

        return publicationState switch
        {
            "published" =>
                $"{channelId} keeps {tupleId} {installPosture} so desktop channel, install guidance, participation, and reward refs stay governed without exposing provider internals.",
            "retained" =>
                $"{channelId} keeps {(string.IsNullOrWhiteSpace(routeRole) ? "desktop" : routeRole)} tuple {tupleId} retained with {installPosture} install guidance so recovery participation and reward refs stay governed.",
            "revoked" =>
                $"{channelId} keeps revoked tuple {tupleId} on {installPosture} install guidance so desktop can explain claim, participation, and reward recovery without reopening installs.",
            _ =>
                $"{channelId} keeps preview tuple {tupleId} on {installPosture} install guidance so desktop can explain claim, participation, and reward posture before wider publication."
        };
    }

    private static List<ManifestArtifactShape> CollectManifestArtifactShapes(JsonObject manifest)
    {
        List<ManifestArtifactShape> artifacts = [];
        if (manifest["artifacts"] is JsonArray artifactRows)
        {
            artifacts.AddRange(artifactRows.OfType<JsonObject>().Select(BuildArtifactShape));
        }

        if (manifest["downloads"] is JsonArray downloadRows)
        {
            artifacts.AddRange(downloadRows.OfType<JsonObject>().Select(BuildArtifactShape));
        }

        return artifacts;
    }

    private static void RebuildCoverageDerivedRegistries(
        JsonObject manifest,
        JsonObject coverage,
        IReadOnlyList<ManifestArtifactShape> artifacts)
    {
        string channelId = NormalizeToken(GetJsonString(manifest["channelId"]) ?? GetJsonString(manifest["channel"]));
        string releaseVersion = (GetJsonString(manifest["version"]) ?? string.Empty).Trim();
        manifest["installAwareArtifactRegistry"] = BuildInstallAwareArtifactRegistry(
            artifacts,
            coverage,
            channelId,
            releaseVersion);
        manifest["desktopSurfaceRefs"] = BuildDesktopSurfaceRefs(
            artifacts,
            coverage,
            channelId,
            releaseVersion);
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
            DownloadUrl: downloadUrl,
            InstallAccessClass: NormalizeToken(GetJsonString(artifact["installAccessClass"]) ?? GetJsonString(artifact["install_access_class"])));
    }

    private static ManifestArtifactShape BuildArtifactShape(PublicReleaseArtifactDto artifact)
    {
        string rid = NormalizeRidToken(artifact.Rid);
        if (string.IsNullOrWhiteSpace(rid))
        {
            rid = NormalizeRidToken(artifact.PlatformId);
        }
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
            DownloadUrl: artifact.Url,
            InstallAccessClass: NormalizeToken(artifact.InstallAccessClass));
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

    private static string? InferPlatformFromRid(string? value)
    {
        string rid = NormalizeRidToken(value);
        return RidToPlatformArch.TryGetValue(rid, out (string Platform, string Arch) mapping)
            ? mapping.Platform
            : null;
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

    private static string? InferArtifactFormat(string? fileName, string? downloadUrl)
    {
        string candidate = !string.IsNullOrWhiteSpace(fileName)
            ? fileName
            : Path.GetFileName((downloadUrl ?? string.Empty).Split('?', '#')[0]);
        if (string.IsNullOrWhiteSpace(candidate))
        {
            return null;
        }

        return candidate.EndsWith(".tar.gz", StringComparison.OrdinalIgnoreCase)
            ? "tar.gz"
            : Path.GetExtension(candidate).TrimStart('.').ToLowerInvariant();
    }

    private static string? InferArtifactFlavor(string? kind, string? fileName, string? downloadUrl)
    {
        string normalizedKind = NormalizeToken(kind);
        if (normalizedKind.Length == 0)
        {
            string? format = InferArtifactFormat(fileName, downloadUrl);
            return format is "exe" or "deb" or "dmg" or "pkg" or "msix"
                ? "installer"
                : format is "zip" or "tar.gz"
                    ? "archive"
                    : null;
        }

        return normalizedKind switch
        {
            "installer" => "installer",
            "dmg" => "installer",
            "pkg" => "installer",
            "msix" => "installer",
            "archive" => "archive",
            "portable" => "portable",
            _ => normalizedKind
        };
    }

    private static JsonElement? NormalizePublicTrustMetricsElement(JsonElement? metricsElement)
    {
        if (metricsElement is not JsonElement metrics || metrics.ValueKind != JsonValueKind.Object)
        {
            return metricsElement;
        }

        JsonObject? root = JsonNode.Parse(metrics.GetRawText())?.AsObject();
        if (root is null)
        {
            return metricsElement;
        }

        if (root["proofFreshness"] is JsonObject proofFreshness)
        {
            NormalizeTimestampNode(proofFreshness, "releaseProofGeneratedAt");
        }

        return JsonSerializer.SerializeToElement(root, new JsonSerializerOptions(JsonSerializerDefaults.Web));
    }

    private static void NormalizeTimestampNode(JsonObject container, string key)
    {
        string? raw = GetJsonString(container[key]);
        if (string.IsNullOrWhiteSpace(raw) || !DateTimeOffset.TryParse(raw, out DateTimeOffset timestamp))
        {
            return;
        }

        container[key] = timestamp.ToUniversalTime().ToString("yyyy-MM-dd'T'HH:mm:sszzz", CultureInfo.InvariantCulture);
    }

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
        string? Channel,
        string? Version,
        string? PublicVersion,
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
        JsonElement? RegistryBoundaryCoverage,
        JsonElement? PublicTrustMetrics,
        JsonElement? InstallAwareArtifactRegistry,
        JsonElement? DesktopSurfaceRefs,
        JsonElement? ArtifactIdentityRegistry,
        JsonElement? ArtifactPublicationBindings,
        JsonElement? ExchangeLineageRegistry,
        IReadOnlyList<RegistryReleaseArtifact>? Artifacts);

    private sealed record RegistryReleaseProof(
        string? Status,
        DateTimeOffset? GeneratedAt,
        string? BaseUrl,
        IReadOnlyList<string>? JourneysPassed,
        IReadOnlyList<string>? ProofRoutes,
        JsonElement? UiLocalizationReleaseGate,
        JsonElement? FlagshipReadiness);

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
        string? PublicVersion,
        JsonElement? DesktopTupleCoverage,
        JsonElement? RegistryBoundaryCoverage,
        JsonElement? PublicTrustMetrics,
        JsonElement? InstallAwareArtifactRegistry,
        JsonElement? DesktopSurfaceRefs,
        JsonElement? ArtifactIdentityRegistry,
        JsonElement? ArtifactPublicationBindings,
        JsonElement? ExchangeLineageRegistry);

    private sealed record CompatibilityReleaseProof(
        string? Status,
        DateTimeOffset? GeneratedAt,
        string? BaseUrl,
        IReadOnlyList<string>? JourneysPassed,
        IReadOnlyList<string>? ProofRoutes,
        JsonElement? UiLocalizationReleaseGate,
        JsonElement? FlagshipReadiness);

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
        string? InstallAccessClass,
        string? CompatibilityState,
        string? CompatibilityReason,
        string? InstallerMode,
        string? PayloadFileName,
        string? PayloadDownloadUrl,
        string? PayloadSha256,
        long? PayloadSizeBytes);

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
        string? DownloadUrl,
        string? InstallAccessClass);
}
