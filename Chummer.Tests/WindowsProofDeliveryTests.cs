using Chummer.Run.Api.Controllers;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.WindowsProof;
using Microsoft.AspNetCore.Mvc.Routing;
using Microsoft.Extensions.Configuration;
using System.Security.Cryptography;
using Xunit;

namespace Chummer.Tests;

public sealed class WindowsProofDeliveryTests
{
    [Fact]
    public void DeliveryAcceptsOnlyExplicitCfGatedProofOnlyPreviewAndBuildsRetainedUrls()
    {
        DeliveryFixture fixture = DeliveryFixture.Create();

        WindowsProofDeliverySnapshot? current = fixture.Service.CaptureCurrentProof();
        WindowsProofDeliverySnapshot? generation = fixture.Service.CaptureProofGeneration("sha256-generation");
        WindowsProofDeliverySnapshot? candidate = fixture.Service.CaptureProofCandidate("run-20260716-115521");

        Assert.NotNull(current);
        Assert.Same(current!.Source, generation!.Source);
        Assert.Same(current.Source, candidate!.Source);
        WindowsProofDeliveryArtifact payload = Assert.Single(
            candidate.Artifacts,
            artifact => artifact.Role == WindowsProofDeliveryRoles.BootstrapPayload);
        Assert.Equal(
            "/downloads/proof/windows/candidates/run-20260716-115521/artifacts/avalonia-win-x64-installer/payload",
            payload.CandidateDownloadUrl);
        Assert.Equal(payload, fixture.Service.FindProofArtifactByFileName(candidate, payload.FileName));
        Assert.Null(fixture.Service.FindProofArtifactByFileName(candidate, $"../{payload.FileName}"));
        using Stream? stream = fixture.Service.OpenVerifiedProofArtifact(candidate, payload);
        Assert.NotNull(stream);
        Assert.Equal(payload.SizeBytes, stream!.Length);
    }

    [Fact]
    public void DeliveryRejectsStableOptimisticOrImplicitUnsignedPostures()
    {
        DeliveryFixture stable = DeliveryFixture.Create(manifest => manifest with { Channel = "stable" });
        DeliveryFixture optimistic = DeliveryFixture.Create(manifest => manifest with
        {
            SupportabilityState = "preview_supported"
        });
        DeliveryFixture unsignedNotRecorded = DeliveryFixture.Create(manifest => manifest with
        {
            Signing = manifest.Signing with { ProofOnlyPolicyRecorded = false }
        });

        Assert.Null(stable.Service.CaptureCurrentProof());
        Assert.Null(optimistic.Service.CaptureCurrentProof());
        Assert.Null(unsignedNotRecorded.Service.CaptureCurrentProof());
    }

    [Fact]
    public void DeliveryAcceptsV2OnlyWhenProvenanceAndSbomRolesArePresent()
    {
        DeliveryFixture fixture = DeliveryFixture.Create(useV2: true);

        WindowsProofDeliverySnapshot proof = Assert.IsType<WindowsProofDeliverySnapshot>(
            fixture.Service.CaptureCurrentProof());
        Assert.NotNull(fixture.Service.FindUniqueProofArtifactByRole(
            proof,
            WindowsProofDeliveryRoles.BuildProvenance));
        Assert.NotNull(fixture.Service.FindUniqueProofArtifactByRole(
            proof,
            WindowsProofDeliveryRoles.Sbom));
    }

    [Fact]
    public void DeliveryFailsClosedWithoutRuntimeCfPolicyOrWhenArtifactIsGloballyDisabled()
    {
        DeliveryFixture noCf = DeliveryFixture.Create(runtimeCfGate: false);
        DeliveryFixture disabled = DeliveryFixture.Create(additionalSettings: new Dictionary<string, string?>
        {
            ["CHUMMER_PUBLIC_DISABLED_ARTIFACT_IDS"] = "avalonia-win-x64-installer"
        });
        DeliveryFixture revokedById = DeliveryFixture.Create(additionalSettings: new Dictionary<string, string?>
        {
            ["CHUMMER_RELEASE_REVOKED_ARTIFACT_IDS"] = "avalonia-win-x64-installer"
        });
        DeliveryFixture revokedByDigest = DeliveryFixture.Create(additionalSettings: new Dictionary<string, string?>
        {
            ["CHUMMER_RELEASE_REVOKED_SHA256"] = Convert.ToHexStringLower(
                SHA256.HashData("payload"u8.ToArray()))
        });

        Assert.Null(noCf.Service.CaptureCurrentProof());
        Assert.Null(disabled.Service.CaptureCurrentProof());
        Assert.Null(revokedById.Service.CaptureCurrentProof());
        Assert.Null(revokedByDigest.Service.CaptureCurrentProof());
        Assert.False(noCf.Service.LegacyShelfFallbackEnabled);
    }

    [Fact]
    public void EmbeddedPayloadProofRemainsDeliverableWithoutBootstrapSidecars()
    {
        DeliveryFixture fixture = DeliveryFixture.Create(includeBootstrap: false);

        WindowsProofDeliverySnapshot proof = Assert.IsType<WindowsProofDeliverySnapshot>(
            fixture.Service.CaptureCurrentProof());

        Assert.DoesNotContain(
            proof.Artifacts,
            artifact => artifact.Role is WindowsProofDeliveryRoles.BootstrapPayload
                or WindowsProofDeliveryRoles.BootstrapMetadata);
        Assert.NotNull(fixture.Service.FindUniqueProofArtifactByRole(
            proof,
            WindowsProofDeliveryRoles.Installer));
    }

    [Fact]
    public void CandidateFilenameAndCurrentGenerationRoutesAdvertiseGetAndHead()
    {
        AssertRoute(
            nameof(DownloadsCompatibilityController.DownloadCandidateWindowsProofFile),
            "/downloads/proof/windows/candidates/{candidateVersion}/files/{fileName}",
            "GET",
            "HEAD");
        AssertRoute(
            nameof(DownloadsCompatibilityController.DownloadCandidateWindowsProofArtifact),
            "/downloads/proof/windows/candidates/{candidateVersion}/artifacts/{artifactId}/{role}",
            "GET",
            "HEAD");
        AssertRoute(
            nameof(DownloadsCompatibilityController.DownloadCurrentWindowsProofArtifact),
            "/downloads/proof/windows/current/artifacts/{artifactId}/{role}",
            "GET",
            "HEAD");
        AssertRoute(
            nameof(DownloadsCompatibilityController.DownloadGenerationWindowsProofArtifact),
            "/downloads/proof/windows/generations/{generationId}/artifacts/{artifactId}/{role}",
            "GET",
            "HEAD");
    }

    private static void AssertRoute(string methodName, string template, params string[] methods)
    {
        var method = typeof(DownloadsCompatibilityController).GetMethod(methodName);
        Assert.NotNull(method);
        HttpMethodAttribute[] routes = method!
            .GetCustomAttributes(typeof(HttpMethodAttribute), inherit: true)
            .Cast<HttpMethodAttribute>()
            .Where(route => string.Equals(route.Template, template, StringComparison.Ordinal))
            .ToArray();
        foreach (string httpMethod in methods)
        {
            Assert.Contains(routes, route => route.HttpMethods.Contains(httpMethod, StringComparer.OrdinalIgnoreCase));
        }
    }

    private sealed class DeliveryFixture
    {
        private DeliveryFixture(
            WindowsProofInstallerService service,
            WindowsProofGenerationSnapshot snapshot)
        {
            Service = service;
            Snapshot = snapshot;
        }

        public WindowsProofInstallerService Service { get; }

        public WindowsProofGenerationSnapshot Snapshot { get; }

        public static DeliveryFixture Create(
            Func<WindowsProofManifest, WindowsProofManifest>? mutateManifest = null,
            bool runtimeCfGate = true,
            bool includeBootstrap = true,
            bool useV2 = false,
            IReadOnlyDictionary<string, string?>? additionalSettings = null)
        {
            var settings = new Dictionary<string, string?>
            {
                ["CHUMMER_WINDOWS_PROOF_CF_ACCESS_GATED"] = runtimeCfGate ? "true" : "false",
                ["CHUMMER_DOWNLOADS_SOURCE_ROOT"] = Path.Combine(
                    Path.GetTempPath(),
                    "windows-proof-delivery-tests",
                    Guid.NewGuid().ToString("N"))
            };
            if (additionalSettings is not null)
            {
                foreach ((string key, string? value) in additionalSettings)
                {
                    settings[key] = value;
                }
            }

            IConfiguration configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(settings)
                .Build();
            IReadOnlyDictionary<string, byte[]> bytes = BuildArtifactBytes(includeBootstrap, useV2);
            WindowsProofInventoryEntry[] inventory = BuildInventory(bytes, includeBootstrap, useV2);
            WindowsProofManifest manifest = new(
                useV2
                    ? WindowsProofManifestValidator.ManifestSchemaVersion
                    : WindowsProofManifestValidator.LegacyManifestSchemaVersion,
                "run-20260716-115521",
                "preview",
                "proof_only",
                "review_required",
                "blocked",
                true,
                false,
                new WindowsProofOnlyPolicy(true, true, true),
                new WindowsProofSigningEvidence("skipped_preview", true, "avalonia-win-x64-installer"),
                new WindowsProofCompatibilitySmokeEvidence(
                    "pass",
                    "wine_compatibility",
                    false,
                    "avalonia-win-x64-installer",
                    "embedded"),
                new WindowsProofVisualExitGate("external_only", null),
                new WindowsProofNativeHostHandoff(
                    "ready_for_windows_host",
                    "visual_proof",
                    true,
                    "avalonia-win-x64-installer"),
                inventory,
                useV2 ? DateTimeOffset.UtcNow.AddMinutes(-1) : null,
                useV2 ? DateTimeOffset.UtcNow.AddHours(23) : null);
            manifest = mutateManifest?.Invoke(manifest) ?? manifest;
            var snapshot = new WindowsProofGenerationSnapshot(
                "sha256-generation",
                manifest,
                inventory,
                DateTimeOffset.Parse("2026-07-16T11:55:21Z"),
                DateTimeOffset.Parse("2026-07-16T12:00:00Z"),
                7,
                entry => new MemoryStream(bytes[entry.FileName], writable: false));
            var store = new FakeWindowsProofGenerationStore(snapshot);
            var service = new WindowsProofInstallerService(
                configuration,
                new ReleaseShelfGenerationStore(configuration),
                store);
            return new DeliveryFixture(service, snapshot);
        }

        private static IReadOnlyDictionary<string, byte[]> BuildArtifactBytes(
            bool includeBootstrap,
            bool useV2)
        {
            var bytes = new Dictionary<string, byte[]>(StringComparer.Ordinal)
            {
                ["chummer-avalonia-win-x64-installer.exe"] = "installer"u8.ToArray(),
                ["signing-avalonia-win-x64.receipt.json"] = "{\"status\":\"skipped_preview\"}"u8.ToArray(),
                ["startup-smoke-avalonia-win-x64.receipt.json"] = "{\"status\":\"pass\"}"u8.ToArray(),
                ["WINDOWS_INSTALLER_VISUAL_PROOF_HANDOFF.generated.json"] = "{\"status\":\"ready_for_windows_host\"}"u8.ToArray()
            };
            if (includeBootstrap)
            {
                bytes["chummer-avalonia-win-x64-payload.zip"] = "payload"u8.ToArray();
                bytes["chummer-avalonia-win-x64-payload.zip.json"] = "{\"contractName\":\"chummer6-ui.windows_bootstrap_payload\"}"u8.ToArray();
            }

            if (useV2)
            {
                bytes["run-20260716-115521.avalonia.win-x64.installer.json"] = "{}"u8.ToArray();
                bytes["desktop-avalonia.cdx.json"] = "{}"u8.ToArray();
            }

            return bytes;
        }

        private static WindowsProofInventoryEntry[] BuildInventory(
            IReadOnlyDictionary<string, byte[]> bytes,
            bool includeBootstrap,
            bool useV2)
        {
            var entries = new List<WindowsProofInventoryEntry>
            {
                Entry(WindowsProofArtifactKind.Installer, "files", "chummer-avalonia-win-x64-installer.exe", "application/vnd.microsoft.portable-executable", bytes),
                Entry(WindowsProofArtifactKind.SigningReceipt, "signing", "signing-avalonia-win-x64.receipt.json", "application/json", bytes),
                Entry(WindowsProofArtifactKind.StartupSmokeReceipt, "startup-smoke", "startup-smoke-avalonia-win-x64.receipt.json", "application/json", bytes),
                Entry(WindowsProofArtifactKind.VisualHandoff, "proof", "WINDOWS_INSTALLER_VISUAL_PROOF_HANDOFF.generated.json", "application/json", bytes)
            };
            if (includeBootstrap)
            {
                entries.Insert(1, Entry(WindowsProofArtifactKind.BootstrapPayload, "files", "chummer-avalonia-win-x64-payload.zip", "application/zip", bytes));
                entries.Insert(2, Entry(WindowsProofArtifactKind.BootstrapMetadata, "files", "chummer-avalonia-win-x64-payload.zip.json", "application/json", bytes));
            }

            if (useV2)
            {
                entries.Add(Entry(
                    WindowsProofArtifactKind.BuildProvenanceReceipt,
                    "proof/build-provenance/v1/invocations",
                    "run-20260716-115521.avalonia.win-x64.installer.json",
                    "application/json",
                    bytes));
                entries.Add(Entry(
                    WindowsProofArtifactKind.Sbom,
                    "proof/build-provenance/v1/sbom",
                    "desktop-avalonia.cdx.json",
                    "application/vnd.cyclonedx+json",
                    bytes));
            }

            return entries.ToArray();
        }

        private static WindowsProofInventoryEntry Entry(
            WindowsProofArtifactKind kind,
            string directory,
            string fileName,
            string contentType,
            IReadOnlyDictionary<string, byte[]> bytes)
        {
            byte[] content = bytes[fileName];
            return new WindowsProofInventoryEntry(
                kind,
                "avalonia-win-x64-installer",
                "avalonia",
                "win-x64",
                fileName,
                $"{directory}/{fileName}",
                contentType,
                content.LongLength,
                Convert.ToHexStringLower(SHA256.HashData(content)));
        }
    }

    private sealed class FakeWindowsProofGenerationStore : IWindowsProofGenerationStore
    {
        private readonly WindowsProofGenerationSnapshot _snapshot;

        public FakeWindowsProofGenerationStore(WindowsProofGenerationSnapshot snapshot)
        {
            _snapshot = snapshot;
        }

        public Task<WindowsProofPreparedGeneration> PrepareAsync(
            WindowsProofPrepareRequest request,
            CancellationToken cancellationToken = default)
            => throw new NotSupportedException();

        public Task<WindowsProofActivationReceipt> ActivateAsync(
            WindowsProofActivationRequest request,
            CancellationToken cancellationToken = default)
            => throw new NotSupportedException();

        public WindowsProofGenerationSnapshot? CaptureCurrent() => _snapshot;

        public WindowsProofGenerationSnapshot? CaptureGeneration(string generationId)
            => generationId == _snapshot.GenerationId ? _snapshot : null;

        public WindowsProofGenerationSnapshot? CaptureCandidate(string candidateVersion)
            => candidateVersion == _snapshot.CandidateVersion ? _snapshot : null;

        public Task<WindowsProofGenerationSnapshot?> CaptureCurrentAsync(
            CancellationToken cancellationToken = default)
            => Task.FromResult<WindowsProofGenerationSnapshot?>(_snapshot);

        public Task<WindowsProofGenerationSnapshot?> CaptureGenerationAsync(
            string generationId,
            CancellationToken cancellationToken = default)
            => Task.FromResult(CaptureGeneration(generationId));

        public Task<WindowsProofGenerationSnapshot?> CaptureCandidateAsync(
            string candidateVersion,
            CancellationToken cancellationToken = default)
            => Task.FromResult(CaptureCandidate(candidateVersion));
    }
}
