using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Hosting;
using Chummer.Run.Api.Services.InstallLinking;

namespace Chummer.Run.Api.Services;

public sealed class HubDeepReadinessService
{
    public const string ContractName = "chummer.run.api.deep_readiness.v2";
    public const string ActivationProtocolProbeName = "activation_protocol";
    public const string StorageAdmissionProbeName = "release_storage_admission";

    private static readonly string[] RequiredPublicationProbeNames =
    [
        ActivationProtocolProbeName,
        StorageAdmissionProbeName
    ];
    private static readonly TimeSpan PublicationProbeTimeout = TimeSpan.FromSeconds(1);
    private static readonly TimeSpan PublicationAssessmentLifetime = TimeSpan.FromSeconds(15);

    private readonly IConfiguration _configuration;
    private readonly IHostEnvironment _environment;
    private readonly PublicReleaseManifestService _releases;
    private readonly ReleaseShelfGenerationStore _releaseShelf;
    private readonly IReadOnlyList<IReleaseShelfPublicationReadinessProbe> _publicationProbes;
    private readonly IInstallLinkingStoreReadinessProbe? _installLinkingStore;
    private readonly DataProtectionKeyProtectionStatus? _dataProtectionKeyProtection;
    private readonly object _publicationAssessmentLock = new();
    private readonly SemaphoreSlim _publicationRefreshGate = new(initialCount: 1, maxCount: 1);
    private CachedPublicationAssessment? _cachedPublicationAssessment;

    public HubDeepReadinessService(
        IConfiguration configuration,
        IHostEnvironment environment,
        PublicReleaseManifestService releases,
        ReleaseShelfGenerationStore? releaseShelf = null,
        IEnumerable<IReleaseShelfPublicationReadinessProbe>? publicationProbes = null,
        IInstallLinkingStoreReadinessProbe? installLinkingStore = null,
        DataProtectionKeyProtectionStatus? dataProtectionKeyProtection = null)
    {
        ArgumentNullException.ThrowIfNull(configuration);
        ArgumentNullException.ThrowIfNull(environment);
        ArgumentNullException.ThrowIfNull(releases);
        _configuration = configuration;
        _environment = environment;
        _releases = releases;
        _releaseShelf = releaseShelf ?? new ReleaseShelfGenerationStore(configuration);
        _publicationProbes = (publicationProbes ?? [])
            .OrderBy(static probe => probe.Name, StringComparer.Ordinal)
            .ToArray();
        _installLinkingStore = installLinkingStore;
        _dataProtectionKeyProtection = dataProtectionKeyProtection;
    }

    public HubDeepReadinessReport Evaluate()
    {
        (HubDeepReadinessCheck shelfCheck, ReleaseShelfSnapshot? snapshot) = ProbeReleaseShelfServing();
        HubDeepReadinessCheck manifestCheck = ProbeCanonicalReleaseManifest(snapshot);
        HubDeepReadinessCheck installLinkingCheck = ProbeInstallLinkingStore();
        HubDeepReadinessCheck[] checks =
        [
            ProbeDurableDataProtectionStorage(),
            installLinkingCheck,
            shelfCheck,
            manifestCheck
        ];
        bool ready = checks.All(static check => check.Passed);
        bool servingReady = shelfCheck.Passed && manifestCheck.Passed && snapshot is not null;
        ReleaseShelfPublicationReadinessState publication = ResolveCachedPublicationReadiness(
            snapshot,
            servingReady,
            installLinkingCheck);
        ReleaseShelfReadinessState shelf = BuildShelfReadinessState(
            snapshot,
            shelfCheck,
            servingReady,
            publication);
        return new HubDeepReadinessReport(
            ContractName,
            Service: "chummer.run.api",
            Ready: ready,
            Status: ready ? "pass" : "fail",
            ServingReady: servingReady,
            PublicationReady: publication.Ready,
            PublicationChecksConfigured: publication.ChecksConfigured,
            GeneratedAt: DateTimeOffset.UtcNow,
            Checks: checks,
            ReleaseShelf: shelf);
    }

    private HubDeepReadinessCheck ProbeInstallLinkingStore()
    {
        if (_installLinkingStore is null)
        {
            return _environment.IsProduction()
                ? Failed("install_linking_store", "readiness_probe_missing")
                : Passed("install_linking_store", "readiness_probe_not_required");
        }

        try
        {
            InstallLinkingStoreReadiness readiness = _installLinkingStore.Evaluate();
            return readiness.Ready
                ? Passed("install_linking_store", readiness.Code)
                : Failed("install_linking_store", readiness.Code);
        }
        catch
        {
            return Failed("install_linking_store", "readiness_probe_failed");
        }
    }

    public async Task<ReleaseShelfPublicationReadinessState> EvaluatePublicationReadinessAsync(
        CancellationToken cancellationToken = default)
    {
        await _publicationRefreshGate.WaitAsync(cancellationToken);
        try
        {
            return await EvaluatePublicationReadinessCoreAsync(cancellationToken);
        }
        finally
        {
            _publicationRefreshGate.Release();
        }
    }

    private async Task<ReleaseShelfPublicationReadinessState> EvaluatePublicationReadinessCoreAsync(
        CancellationToken cancellationToken)
    {
        (HubDeepReadinessCheck shelfCheck, ReleaseShelfSnapshot? snapshot) = ProbeReleaseShelfServing();
        HubDeepReadinessCheck manifestCheck = ProbeCanonicalReleaseManifest(snapshot);
        HubDeepReadinessCheck installLinkingCheck = ProbeInstallLinkingStore();
        bool servingReady = shelfCheck.Passed && manifestCheck.Passed && snapshot is not null;
        ReleaseShelfPublicationReadinessState assessment;
        if (!servingReady || snapshot is null)
        {
            assessment = BuildPublicationAssessment(
                snapshot,
                [
                    PublicationCheck(
                        "release_shelf_serving",
                        ready: false,
                        "release_shelf_not_serving")
                ],
                "release_shelf_not_serving");
        }
        else if (!installLinkingCheck.Passed)
        {
            assessment = BuildInstallLinkingBlockedPublicationAssessment(
                snapshot,
                installLinkingCheck);
        }
        else if (snapshot.IsLegacy)
        {
            assessment = BuildPublicationAssessment(
                snapshot,
                [
                    PublicationCheck("release_shelf_serving", ready: true, "verified_shelf_serving"),
                    PublicationCheck("layout_v1", ready: false, "layout_v1_activation_required")
                ],
                "layout_v1_activation_required");
        }
        else if (!PublicationChecksAreConfigured())
        {
            assessment = BuildPublicationAssessment(
                snapshot,
                [
                    PublicationCheck("release_shelf_serving", ready: true, "verified_shelf_serving"),
                    PublicationCheck("publication_probe_contract", ready: false, "required_probes_missing")
                ],
                "required_probes_missing");
        }
        else
        {
            var checks = new List<ReleaseShelfPublicationReadinessCheck>
            {
                PublicationCheck("release_shelf_serving", ready: true, "verified_shelf_serving"),
                PublicationCheck("publication_probe_contract", ready: true, "required_probes_configured")
            };
            Task<ReleaseShelfPublicationReadinessCheck>[] probeTasks = _publicationProbes
                .Select(probe => EvaluatePublicationProbeAsync(probe, snapshot, cancellationToken))
                .ToArray();
            checks.AddRange(await Task.WhenAll(probeTasks));
            string code = checks.FirstOrDefault(static check => !check.Ready)?.Code
                          ?? "publication_ready";
            assessment = BuildPublicationAssessment(snapshot, checks, code);
        }

        cancellationToken.ThrowIfCancellationRequested();
        lock (_publicationAssessmentLock)
        {
            _cachedPublicationAssessment = new CachedPublicationAssessment(
                snapshot?.CacheKey,
                assessment);
        }

        return assessment;
    }

    private HubDeepReadinessCheck ProbeDurableDataProtectionStorage()
    {
        string? probePath = null;
        try
        {
            string storagePath = HubRuntimePathDefaults.ResolveDataProtectionKeysPath(_configuration, _environment);
            if (HubRuntimePathDefaults.UsesTempFallback(storagePath))
            {
                return Failed("data_protection_storage", "temporary_storage_fallback");
            }

            if (_environment.IsProduction() && !HubRuntimePathDefaults.IsExplicitlyConfigured(_configuration))
            {
                return Failed("data_protection_storage", "production_storage_not_explicit");
            }

            if (_environment.IsProduction()
                && (_dataProtectionKeyProtection is null || !_dataProtectionKeyProtection.Ready))
            {
                return Failed(
                    "data_protection_storage",
                    _dataProtectionKeyProtection?.Code ?? "data_protection_key_encryptor_status_missing");
            }

            if (LinuxSecureFile.IsSupportedPlatform)
            {
                LinuxSecureFile.PrepareOwnerOnlyDirectory(storagePath);
            }
            else
            {
                Directory.CreateDirectory(storagePath);
            }

            if (_environment.IsProduction())
            {
                string? keyRingFailure = DataProtectionKeyProtectionConfigurator.ValidateEncryptedKeyRing(
                    storagePath,
                    repairOwnerMode: false);
                if (keyRingFailure is not null)
                {
                    return Failed("data_protection_storage", keyRingFailure);
                }
            }

            probePath = Path.Combine(storagePath, $".chummer-readiness-{Guid.NewGuid():N}.tmp");
            using (FileStream stream = new(
                       probePath,
                       FileMode.CreateNew,
                       FileAccess.Write,
                       FileShare.None,
                       bufferSize: 1,
                       FileOptions.WriteThrough))
            {
                stream.WriteByte(0x43);
                stream.Flush(flushToDisk: true);
            }

            File.Delete(probePath);
            probePath = null;
            return Passed("data_protection_storage", "durable_storage_writable");
        }
        catch
        {
            return Failed("data_protection_storage", "storage_probe_failed");
        }
        finally
        {
            if (probePath is not null)
            {
                try
                {
                    File.Delete(probePath);
                }
                catch
                {
                    // Readiness must report the failure without leaking a probe artifact exception.
                }
            }
        }
    }

    private (HubDeepReadinessCheck Check, ReleaseShelfSnapshot? Snapshot) ProbeReleaseShelfServing()
    {
        try
        {
            ReleaseShelfSnapshot snapshot = _releaseShelf.Capture();
            if (!snapshot.IsLegacy
                && (string.IsNullOrWhiteSpace(snapshot.GenerationId)
                    || string.IsNullOrWhiteSpace(snapshot.ActivationReceiptId)
                    || string.IsNullOrWhiteSpace(snapshot.InventoryDigest)))
            {
                return (Failed("release_shelf", "release_shelf_identity_incomplete"), null);
            }

            return (
                Passed(
                    "release_shelf",
                    snapshot.IsLegacy ? "legacy_shelf_loaded" : "generation_shelf_verified"),
                snapshot);
        }
        catch
        {
            return (Failed("release_shelf", "release_shelf_invalid"), null);
        }
    }

    private HubDeepReadinessCheck ProbeCanonicalReleaseManifest(ReleaseShelfSnapshot? snapshot)
    {
        if (snapshot is null)
        {
            return Failed("canonical_release_manifest", "release_shelf_unavailable");
        }

        try
        {
            bool canonicalAvailable = snapshot.IsLegacy
                ? _releases.ResolveCanonicalManifestFilePath(snapshot) is not null
                : _releases.LoadGenerationCanonicalManifestBytes(snapshot) is not null;
            if (!canonicalAvailable)
            {
                return Failed("canonical_release_manifest", "canonical_manifest_missing");
            }

            var manifest = _releases.LoadManifest(snapshot);
            if (!string.Equals(manifest.Status, "published", StringComparison.OrdinalIgnoreCase)
                || string.Equals(manifest.Version, "unpublished", StringComparison.OrdinalIgnoreCase)
                || manifest.Downloads.Count == 0)
            {
                return Failed("canonical_release_manifest", "canonical_manifest_not_published");
            }

            return Passed("canonical_release_manifest", "published_manifest_loaded");
        }
        catch
        {
            return Failed("canonical_release_manifest", "canonical_manifest_invalid");
        }
    }

    private ReleaseShelfPublicationReadinessState ResolveCachedPublicationReadiness(
        ReleaseShelfSnapshot? snapshot,
        bool servingReady,
        HubDeepReadinessCheck installLinkingCheck)
    {
        if (!servingReady || snapshot is null)
        {
            return BuildPublicationAssessment(
                snapshot,
                [PublicationCheck("release_shelf_serving", ready: false, "release_shelf_not_serving")],
                "release_shelf_not_serving");
        }

        if (!installLinkingCheck.Passed)
        {
            return BuildInstallLinkingBlockedPublicationAssessment(
                snapshot,
                installLinkingCheck);
        }

        if (snapshot.IsLegacy)
        {
            return BuildPublicationAssessment(
                snapshot,
                [
                    PublicationCheck("release_shelf_serving", ready: true, "verified_shelf_serving"),
                    PublicationCheck("layout_v1", ready: false, "layout_v1_activation_required")
                ],
                "layout_v1_activation_required");
        }

        if (!PublicationChecksAreConfigured())
        {
            return BuildPublicationAssessment(
                snapshot,
                [
                    PublicationCheck("release_shelf_serving", ready: true, "verified_shelf_serving"),
                    PublicationCheck("publication_probe_contract", ready: false, "required_probes_missing")
                ],
                "required_probes_missing");
        }

        lock (_publicationAssessmentLock)
        {
            if (_cachedPublicationAssessment is not null
                && string.Equals(
                    _cachedPublicationAssessment.SnapshotCacheKey,
                    snapshot.CacheKey,
                    StringComparison.Ordinal)
                && DateTimeOffset.UtcNow - _cachedPublicationAssessment.Assessment.ObservedAt
                <= PublicationAssessmentLifetime)
            {
                return _cachedPublicationAssessment.Assessment;
            }
        }

        return BuildPublicationAssessment(
            snapshot,
            [
                PublicationCheck("release_shelf_serving", ready: true, "verified_shelf_serving"),
                PublicationCheck("publication_probe_snapshot", ready: false, "publication_checks_pending")
            ],
            "publication_checks_pending");
    }

    private ReleaseShelfPublicationReadinessState BuildInstallLinkingBlockedPublicationAssessment(
        ReleaseShelfSnapshot snapshot,
        HubDeepReadinessCheck installLinkingCheck)
    {
        string code = NormalizeProbeCode(installLinkingCheck.Code, ready: false);
        return BuildPublicationAssessment(
            snapshot,
            [
                PublicationCheck("release_shelf_serving", ready: true, "verified_shelf_serving"),
                PublicationCheck("install_linking_store", ready: false, code)
            ],
            code);
    }

    private bool PublicationChecksAreConfigured()
    {
        string[] configuredNames = _publicationProbes
            .Select(static probe => probe.Name)
            .ToArray();
        return configuredNames.All(ProbeNameIsSafe)
               && configuredNames.Distinct(StringComparer.Ordinal).Count() == configuredNames.Length
               && RequiredPublicationProbeNames.All(required =>
                   configuredNames.Contains(required, StringComparer.Ordinal));
    }

    private static bool ProbeNameIsSafe(string? name)
        => name is { Length: >= 1 and <= 64 }
           && name.All(static character =>
               character is >= 'a' and <= 'z'
               || character is >= '0' and <= '9'
               || character == '_');

    private static async Task<ReleaseShelfPublicationReadinessCheck> EvaluatePublicationProbeAsync(
        IReleaseShelfPublicationReadinessProbe probe,
        ReleaseShelfSnapshot snapshot,
        CancellationToken cancellationToken)
    {
        string name = ProbeNameIsSafe(probe.Name) ? probe.Name : "invalid_probe_name";
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        timeout.CancelAfter(PublicationProbeTimeout);
        try
        {
            Task<ReleaseShelfPublicationReadinessProbeResult> task = probe
                .EvaluateAsync(snapshot, timeout.Token)
                .AsTask();
            ReleaseShelfPublicationReadinessProbeResult result = await task.WaitAsync(
                PublicationProbeTimeout,
                cancellationToken);
            return PublicationCheck(name, result.Ready, NormalizeProbeCode(result.Code, result.Ready));
        }
        catch (OperationCanceledException) when (!cancellationToken.IsCancellationRequested)
        {
            return PublicationCheck(name, ready: false, "probe_timeout");
        }
        catch (OperationCanceledException)
        {
            throw;
        }
        catch (TimeoutException)
        {
            return PublicationCheck(name, ready: false, "probe_timeout");
        }
        catch
        {
            return PublicationCheck(name, ready: false, "probe_failed");
        }
    }

    private ReleaseShelfPublicationReadinessState BuildPublicationAssessment(
        ReleaseShelfSnapshot? snapshot,
        IReadOnlyList<ReleaseShelfPublicationReadinessCheck> checks,
        string code)
    {
        bool configured = PublicationChecksAreConfigured();
        bool ready = snapshot is { IsLegacy: false }
                     && configured
                     && checks.Count > 0
                     && checks.All(static check => check.Ready);
        return new ReleaseShelfPublicationReadinessState(
            Ready: ready,
            ChecksConfigured: configured,
            Status: ready ? "ready" : "blocked",
            Code: NormalizeProbeCode(code, ready),
            ObservedAt: DateTimeOffset.UtcNow,
            GenerationId: snapshot?.GenerationId,
            ActivationReceiptId: snapshot?.ActivationReceiptId,
            InventoryDigest: snapshot?.InventoryDigest,
            Checks: checks);
    }

    private static ReleaseShelfPublicationReadinessCheck PublicationCheck(
        string name,
        bool ready,
        string code)
        => new(
            Name: name,
            Ready: ready,
            Status: ready ? "ready" : "blocked",
            Code: code);

    private static ReleaseShelfReadinessState BuildShelfReadinessState(
        ReleaseShelfSnapshot? snapshot,
        HubDeepReadinessCheck shelfCheck,
        bool servingReady,
        ReleaseShelfPublicationReadinessState publication)
        => new(
            Mode: snapshot?.IsLegacy == true ? "legacy" : snapshot is null ? "unavailable" : "generation",
            ServingReady: servingReady,
            PublicationReady: publication.Ready,
            PublicationChecksConfigured: publication.ChecksConfigured,
            Status: servingReady ? "serving" : "not_serving",
            Code: shelfCheck.Code,
            GenerationId: snapshot?.GenerationId,
            ActivationReceiptId: snapshot?.ActivationReceiptId,
            InventoryDigest: snapshot?.InventoryDigest,
            ReleaseVersion: snapshot?.ReleaseVersion,
            Channel: snapshot?.Channel,
            PublishedAt: snapshot?.PublishedAt,
            PublicationChecks: publication.Checks);

    private static string NormalizeProbeCode(string? code, bool ready)
    {
        string normalized = (code ?? string.Empty).Trim();
        if (normalized.Length is < 1 or > 96
            || normalized.Any(static character =>
                !(character is >= 'a' and <= 'z'
                  || character is >= '0' and <= '9'
                  || character == '_')))
        {
            return ready ? "ready" : "blocked";
        }

        return normalized;
    }

    private static HubDeepReadinessCheck Passed(string name, string code)
        => new(name, Passed: true, Status: "pass", Code: code);

    private static HubDeepReadinessCheck Failed(string name, string code)
        => new(name, Passed: false, Status: "fail", Code: code);

    private sealed record CachedPublicationAssessment(
        string? SnapshotCacheKey,
        ReleaseShelfPublicationReadinessState Assessment);
}

public sealed class ReleaseShelfPublicationReadinessRefreshService(
    HubDeepReadinessService readiness,
    ILogger<ReleaseShelfPublicationReadinessRefreshService> logger)
    : BackgroundService
{
    private static readonly TimeSpan RefreshInterval = TimeSpan.FromSeconds(5);

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                await readiness.EvaluatePublicationReadinessAsync(stoppingToken);
            }
            catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
            {
                break;
            }
            catch
            {
                logger.LogWarning(
                    "Release publication readiness refresh failed; publication remains fail-closed until a bounded refresh succeeds.");
            }

            try
            {
                await Task.Delay(RefreshInterval, stoppingToken);
            }
            catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
            {
                break;
            }
        }
    }
}

public sealed record HubDeepReadinessReport(
    string ContractName,
    string Service,
    bool Ready,
    string Status,
    bool ServingReady,
    bool PublicationReady,
    bool PublicationChecksConfigured,
    DateTimeOffset GeneratedAt,
    IReadOnlyList<HubDeepReadinessCheck> Checks,
    ReleaseShelfReadinessState ReleaseShelf);

public sealed record HubDeepReadinessCheck(
    string Name,
    bool Passed,
    string Status,
    string Code);

public interface IReleaseShelfPublicationReadinessProbe
{
    string Name { get; }

    ValueTask<ReleaseShelfPublicationReadinessProbeResult> EvaluateAsync(
        ReleaseShelfSnapshot snapshot,
        CancellationToken cancellationToken);
}

public sealed record ReleaseShelfPublicationReadinessProbeResult(
    bool Ready,
    string Code);

public sealed record ReleaseShelfPublicationReadinessCheck(
    string Name,
    bool Ready,
    string Status,
    string Code);

public sealed record ReleaseShelfPublicationReadinessState(
    bool Ready,
    bool ChecksConfigured,
    string Status,
    string Code,
    DateTimeOffset ObservedAt,
    string? GenerationId,
    string? ActivationReceiptId,
    string? InventoryDigest,
    IReadOnlyList<ReleaseShelfPublicationReadinessCheck> Checks);

public sealed record ReleaseShelfReadinessState(
    string Mode,
    bool ServingReady,
    bool PublicationReady,
    bool PublicationChecksConfigured,
    string Status,
    string Code,
    string? GenerationId,
    string? ActivationReceiptId,
    string? InventoryDigest,
    string? ReleaseVersion,
    string? Channel,
    DateTimeOffset? PublishedAt,
    IReadOnlyList<ReleaseShelfPublicationReadinessCheck> PublicationChecks);
